from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from schauwerk.operator.live_apply import compile_live_operation_bundle, enable_kill_switch
from schauwerk.regie.model import (
    compile_decision_receipt,
    compile_regie_context,
    compile_review_bundle,
    write_private_json,
)
from schauwerk.regie.service import RegieController

EVIDENCE = Path("docs/operators/evidence/sw009-live-executor-20260711")
MARKER = "schauwerk-region:managed-summary"
OLD_ONE = f"[{MARKER}] OLD FIXTURE SUMMARY"
NEW_ONE = f"[{MARKER}] NEW FIXTURE SUMMARY"
OLD_TWO = f"[{MARKER}] OLD FIXTURE DETAIL"
NEW_TWO = f"[{MARKER}] NEW FIXTURE DETAIL"
BEFORE_DIGEST = "a" * 64
AFTER_DIGEST = "b" * 64


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def review() -> dict:
    context = compile_regie_context(
        {
            "review_id": "regie-service-test",
            "title": "Regie service test",
            "summary": "Review two operations and apply one selected change.",
            "instructions": ["Decide every operation before effect."],
            "sources": [
                {
                    "source_id": "repo-main",
                    "title": "Repository main",
                    "revision": "b54f3ef1",
                    "observed_at": "2026-07-11T01:50:00Z",
                    "freshness": "fresh",
                    "visibility": "internal",
                    "citation": "repo:schauwerk@b54f3ef1",
                    "uncertainty": 0.02,
                }
            ],
            "context": [
                {
                    "label": "Scope",
                    "value": "One managed region",
                    "state": "constraint",
                    "source_id": "repo-main",
                }
            ],
        }
    )
    original = read("operation-bundle.json")
    draft = {
        key: value
        for key, value in original.items()
        if key not in {"schema_version", "bundle_digest", "operations"}
    }
    draft["schema_version"] = "typed-region-live-operation-draft.v1"
    draft["operations"] = [
        original["operations"][0],
        {
            "operation_id": "replace-reviewed-detail",
            "action": "replace-text",
            "region_id": original["region_id"],
            "old_text": OLD_TWO,
            "new_text": NEW_TWO,
        },
    ]
    return compile_review_bundle(
        context=context,
        gate_receipt=read("gate-receipt.json"),
        operation_bundle=compile_live_operation_bundle(draft),
        created_at=datetime(2026, 7, 11, 2, 0, tzinfo=UTC),
    )


class FakeProvider:
    def __init__(self) -> None:
        self.dsl = f"{OLD_ONE}\n{OLD_TWO}"
        self.replace_calls = 0
        self.snapshot_calls = 0

    def capabilities(self) -> set[str]:
        return {"layout_read", "layout_update"}

    async def snapshot(self, *, alias: str, output_path: Path) -> dict:
        self.snapshot_calls += 1
        digest = BEFORE_DIGEST if "NEW FIXTURE" not in self.dsl else AFTER_DIGEST
        return {
            "board_alias": alias,
            "content_digest": digest,
            "item_count": 2,
            "comment_count": 0,
            "item_pages": 1,
            "comment_pages": 0,
            "repeatability_verified": True,
            "output_path": str(output_path),
            "sanitized_references": True,
            "mutation_attempted": False,
        }

    async def read_dsl(self, *, alias: str) -> str:
        return self.dsl

    async def replace_text(self, *, alias: str, old_text: str, new_text: str) -> dict:
        self.replace_calls += 1
        if self.dsl.count(old_text) != 1:
            raise ValueError("old text is not unique")
        self.dsl = self.dsl.replace(old_text, new_text, 1)
        return {
            "success": True,
            "created_count": 0,
            "updated_count": 1,
            "deleted_count": 0,
            "result_dsl_digest": hashlib.sha256(self.dsl.encode()).hexdigest(),
            "sanitized_references": True,
        }


def controller(tmp_path: Path, provider: FakeProvider, calls: dict[str, int]) -> RegieController:
    async def factory() -> FakeProvider:
        calls["provider"] += 1
        return provider

    return RegieController(
        review_bundle=review(),
        state_root=tmp_path / "regie",
        journal_root=tmp_path / "transactions",
        kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
        provider_factory=factory,
    )


def decision_payload() -> dict:
    return {
        "decisions": {
            "replace-reviewed-summary": "approve",
            "replace-reviewed-detail": "reject",
        },
        "approved_by": "alex",
        "approval_reference": "bureau:schauwerk-t008",
        "confirmation": "APPROVE_LIVE_APPLY",
        "valid_minutes": 60,
    }


def test_decision_is_owner_only_immutable_and_does_not_touch_provider(tmp_path: Path) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    initial = active.state()
    assert initial["phase"] == "review"
    assert initial["controls"]["can_decide"] is True
    receipt = active.decide(decision_payload())
    assert receipt["approved_operation_ids"] == ["replace-reviewed-summary"]
    assert calls["provider"] == 0
    assert active.decision_path.stat().st_mode & 0o077 == 0
    assert active.bundle_path.stat().st_mode & 0o077 == 0
    assert active.authorization_path.stat().st_mode & 0o077 == 0
    assert active.plan_path.stat().st_mode & 0o077 == 0
    state = active.state()
    assert state["phase"] == "approved"
    assert state["controls"]["decision_immutable"] is True
    replay = active.decide(decision_payload())
    assert replay["replayed_without_change"] is True
    changed = decision_payload()
    changed["decisions"]["replace-reviewed-detail"] = "defer"
    with pytest.raises(ValueError, match="already immutable"):
        active.decide(changed)


def test_apply_requires_second_confirmation_and_returns_sanitized_receipt(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    with pytest.raises(ValueError, match="confirmation is invalid"):
        asyncio.run(active.apply({"confirmation": "approve"}))
    assert calls["provider"] == 0
    result = asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    assert result["ok"] is True
    assert result["operation_count"] == 1
    assert result["applied_operation_ids"] == ["replace-reviewed-summary"]
    assert "journal_path" not in result
    assert "output_path" not in result
    assert calls["provider"] == 1
    assert NEW_ONE in provider.dsl
    assert OLD_TWO in provider.dsl
    state = active.state()
    assert state["phase"] == "applied"
    assert state["controls"]["can_restore"] is True
    replay = asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    assert replay["replayed_without_mutation"] is True
    assert calls["provider"] == 1


def test_restore_requires_third_confirmation_and_uses_same_context(tmp_path: Path) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    with pytest.raises(ValueError, match="confirmation is invalid"):
        asyncio.run(active.restore({"confirmation": "restore"}))
    result = asyncio.run(active.restore({"confirmation": "RESTORE_LIVE_APPLY"}))
    assert result["ok"] is True
    assert result["restored_operation_count"] == 1
    assert result["restored_to_before_snapshot"] is True
    assert "journal_path" not in result
    assert OLD_ONE in provider.dsl
    assert active.state()["phase"] == "restored"
    assert calls["provider"] == 2


def test_kill_switch_is_visible_and_blocks_apply_before_provider(tmp_path: Path) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    enable_kill_switch(active.kill_switch_path, reason="operator stop")
    state = active.state()
    assert state["controls"]["kill_switch_enabled"] is True
    assert state["controls"]["can_apply"] is False
    with pytest.raises(ValueError, match="kill switch is enabled"):
        asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    assert calls["provider"] == 0


def test_tampered_transaction_receipt_is_rejected_before_projection(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    value = json.loads(active.transaction_path.read_text(encoding="utf-8"))
    value["operation_count"] = 99
    active.transaction_path.write_text(json.dumps(value), encoding="utf-8")
    active.transaction_path.chmod(0o600)
    with pytest.raises(ValueError, match="digest mismatch"):
        active.state()


def test_expired_decision_disables_apply_without_provider_access(tmp_path: Path) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    decisions = {
        "replace-reviewed-summary": "approve",
        "replace-reviewed-detail": "reject",
    }
    receipt = compile_decision_receipt(
        review_bundle=active.review,
        decisions=decisions,
        approved_by="alex",
        approval_reference="bureau:schauwerk-t008",
        confirmation="APPROVE_LIVE_APPLY",
        valid_minutes=1,
        decided_at=datetime(2026, 7, 11, 2, 0, tzinfo=UTC),
    )
    write_private_json(active.decision_path, receipt, label="decision")
    state = active.state(now=datetime(2026, 7, 11, 2, 2, tzinfo=UTC))
    assert state["controls"]["authorization_expired"] is True
    assert state["controls"]["can_apply"] is False
    with pytest.raises(ValueError, match="has expired"):
        asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    assert calls["provider"] == 0


def test_failed_restore_with_recovered_after_state_can_be_retried(tmp_path: Path) -> None:
    class FlakyRestoreProvider(FakeProvider):
        fail_inverse_once = True

        async def replace_text(self, *, alias: str, old_text: str, new_text: str) -> dict:
            if self.fail_inverse_once and old_text == NEW_ONE and new_text == OLD_ONE:
                self.fail_inverse_once = False
                raise ValueError("fixture inverse failure")
            return await super().replace_text(alias=alias, old_text=old_text, new_text=new_text)

    provider = FlakyRestoreProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    asyncio.run(active.apply({"confirmation": "EXECUTE_LIVE_APPLY"}))
    failed = asyncio.run(active.restore({"confirmation": "RESTORE_LIVE_APPLY"}))
    assert failed["ok"] is False
    assert failed["rollback_to_after_succeeded"] is True
    assert failed["still_restore_ready"] is True
    state = active.state()
    assert state["phase"] == "restore-failed"
    assert state["controls"]["can_restore"] is True
    restored = asyncio.run(active.restore({"confirmation": "RESTORE_LIVE_APPLY"}))
    assert restored["ok"] is True
    assert active.state()["phase"] == "restored"
    assert calls["provider"] == 3


def test_immutable_decision_replay_rejects_unknown_operation_and_wrong_confirmation(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    calls = {"provider": 0}
    active = controller(tmp_path, provider, calls)
    active.decide(decision_payload())
    extra = decision_payload()
    extra["decisions"]["unknown-operation"] = "approve"
    with pytest.raises(ValueError, match="cover every operation"):
        active.decide(extra)
    wrong = decision_payload()
    wrong["confirmation"] = "approve"
    with pytest.raises(ValueError, match="confirmation is invalid"):
        active.decide(wrong)
    changed_duration = decision_payload()
    changed_duration["valid_minutes"] = 61
    with pytest.raises(ValueError, match="already immutable"):
        active.decide(changed_duration)
    assert calls["provider"] == 0
