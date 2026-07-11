from __future__ import annotations

import asyncio
import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from schauwerk.operator.core import RegionDeclaration
from schauwerk.operator.live_apply import (
    _manifest_digest,
    _receipt_digest,
    compile_live_apply_plan,
    compile_live_authorization,
    compile_live_operation_bundle,
    compile_live_operation_bundle_template,
    disable_kill_switch,
    enable_kill_switch,
    execute_live_apply,
    kill_switch_status,
    restore_live_apply,
    validate_live_operation_bundle,
    validate_live_transaction_failure_receipt,
)
from schauwerk.surfaces.miro.credentials import write_json_owner_only

NOW = datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
ALIAS = "sw009-test-board"
REGION_ID = "managed-summary"
MARKER = f"schauwerk-region:{REGION_ID}"
BEFORE_DIGEST = "a" * 64
AFTER_DIGEST = "b" * 64


def region() -> RegionDeclaration:
    return RegionDeclaration(
        view_id="test:managed-view",
        region_id=REGION_ID,
        mode="managed",
        surface_alias=ALIAS,
        expected_snapshot_digest=BEFORE_DIGEST,
        expected_source_digest="c" * 64,
        owner="schauwerk",
        visibility="private",
    )


def gate_receipt() -> dict:
    value = {
        "schema_version": "typed-region-sw009-live-apply-gate-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_live_apply": True,
        "blocked_reasons": [],
        "operation": "render-update",
        "region": region().to_dict(),
        "snapshot": {
            "board_alias": ALIAS,
            "content_digest": BEFORE_DIGEST,
            "repeatability_verified": True,
            "sanitized_references": True,
        },
        "boundary": {
            "local_gate_only": True,
            "does_not_execute_live_apply": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_sw003_live_gate": True,
            "requires_human_operator_apply": True,
        },
    }
    value["receipt_digest"] = _receipt_digest(value)
    return value


def operation_bundle(*, count: int = 1) -> dict:
    draft = compile_live_operation_bundle_template(
        region=region(), bundle_id="sw009-live-bundle-test"
    )
    draft["operations"] = []
    for index in range(count):
        draft["operations"].append(
            {
                "operation_id": f"replace-text-{index + 1}",
                "action": "replace-text",
                "region_id": REGION_ID,
                "old_text": f"[{MARKER}] OLD {index + 1}",
                "new_text": f"[{MARKER}] NEW {index + 1}",
            }
        )
    return compile_live_operation_bundle(draft)


def authorization(bundle: dict) -> dict:
    return compile_live_authorization(
        gate_receipt=gate_receipt(),
        operation_bundle=bundle,
        approved_by="alex",
        approval_reference="bureau:schauwerk-t007",
        confirmation="APPROVE_LIVE_APPLY",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        authorization_id="sw009-live-authorization-test",
    )


def plan(*, count: int = 1) -> dict:
    bundle = operation_bundle(count=count)
    return compile_live_apply_plan(
        gate_receipt=gate_receipt(),
        operation_bundle=bundle,
        authorization=authorization(bundle),
        now=NOW + timedelta(minutes=1),
    )


class FakeProvider:
    def __init__(
        self,
        *,
        operation_count: int = 1,
        capabilities: set[str] | None = None,
        fail_after_mutation_call: int | None = None,
    ) -> None:
        self.dsl = "\n".join(
            f"item-{index + 1} TEXT content=\"[{MARKER}] OLD {index + 1}\""
            for index in range(operation_count)
        )
        self._capabilities = capabilities or {"layout_read", "layout_update"}
        self.fail_after_mutation_call = fail_after_mutation_call
        self.replace_calls = 0
        self.snapshot_calls = 0
        self.failed_once = False
        self.forced_snapshot_digest: str | None = None

    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    async def snapshot(self, *, alias: str, output_path: Path) -> dict:
        self.snapshot_calls += 1
        assert alias == ALIAS
        digest = self.forced_snapshot_digest or (
            AFTER_DIGEST if f"[{MARKER}] NEW" in self.dsl else BEFORE_DIGEST
        )
        value = {
            "board_alias": alias,
            "content_digest": digest,
            "item_count": len(self.dsl.splitlines()),
            "repeatability_verified": True,
            "sanitized_references": True,
        }
        write_json_owner_only(output_path, value)
        return value

    async def read_dsl(self, *, alias: str) -> str:
        assert alias == ALIAS
        return self.dsl

    async def replace_text(self, *, alias: str, old_text: str, new_text: str) -> dict:
        assert alias == ALIAS
        self.replace_calls += 1
        if self.dsl.count(old_text) != 1:
            raise RuntimeError("old text not unique")
        self.dsl = self.dsl.replace(old_text, new_text, 1)
        if (
            self.fail_after_mutation_call == self.replace_calls
            and not self.failed_once
        ):
            self.failed_once = True
            raise RuntimeError("provider response lost after mutation")
        return {
            "success": True,
            "created_count": 0,
            "updated_count": 1,
            "deleted_count": 0,
            "result_dsl_digest": hashlib.sha256(self.dsl.encode("utf-8")).hexdigest(),
            "sanitized_references": True,
        }


def test_bundle_rejects_provider_reference_and_scope_loss() -> None:
    value = operation_bundle()
    value["operations"][0]["new_text"] = "https://miro.com/app/board/private"
    value["bundle_digest"] = _manifest_digest(value, "bundle_digest")
    with pytest.raises(ValueError, match="provider or network reference"):
        validate_live_operation_bundle(value)

    value = operation_bundle()
    value["operations"][0]["new_text"] = "NEW WITHOUT MARKER"
    value["bundle_digest"] = _manifest_digest(value, "bundle_digest")
    with pytest.raises(ValueError, match="preserve the managed-region marker"):
        validate_live_operation_bundle(value)


def test_authorization_is_digest_bound_and_expires() -> None:
    bundle = operation_bundle()
    approved = authorization(bundle)
    result = compile_live_apply_plan(
        gate_receipt=gate_receipt(),
        operation_bundle=bundle,
        authorization=approved,
        now=NOW + timedelta(minutes=30),
    )
    assert result["ready_for_live_apply"] is True
    assert result["source_receipts"]["operation_bundle_digest"] == bundle["bundle_digest"]

    with pytest.raises(ValueError, match="expired"):
        compile_live_apply_plan(
            gate_receipt=gate_receipt(),
            operation_bundle=bundle,
            authorization=approved,
            now=NOW + timedelta(hours=2),
        )

    bundle["operations"][0]["new_text"] += " changed"
    bundle["bundle_digest"] = _manifest_digest(bundle, "bundle_digest")
    with pytest.raises(ValueError, match="operation bundle binding mismatch"):
        compile_live_apply_plan(
            gate_receipt=gate_receipt(),
            operation_bundle=bundle,
            authorization=approved,
            now=NOW + timedelta(minutes=30),
        )


def test_live_apply_and_restore_are_verified_and_owner_only(tmp_path: Path) -> None:
    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )

    assert transaction["ok"] is True
    assert transaction["semantic_verification_passed"] is True
    assert transaction["idempotency_verified"] is True
    assert transaction["postflight_verified"] is True
    assert transaction["restore_ready"] is True
    assert "miro.com" not in json.dumps(transaction)
    assert f"[{MARKER}] NEW 1" in provider.dsl
    assert stat.S_IMODE((tmp_path / "transaction.json").stat().st_mode) == 0o600
    journal = Path(transaction["journal_path"])
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600

    restored = asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    assert restored["ok"] is True
    assert restored["restored_to_before_snapshot"] is True
    assert f"[{MARKER}] OLD 1" in provider.dsl

    replay = asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    assert replay["replayed_without_mutation"] is True


def test_kill_switch_blocks_before_provider_access(tmp_path: Path) -> None:
    provider = FakeProvider()
    switch = tmp_path / "LIVE_APPLY_DISABLED"
    enabled = enable_kill_switch(switch, reason="operator stop", now=NOW)
    assert enabled["enabled"] is True
    assert kill_switch_status(switch)["enabled"] is True
    with pytest.raises(ValueError, match="kill switch is enabled"):
        asyncio.run(
            execute_live_apply(
                plan=plan(),
                provider=provider,
                journal_root=tmp_path / "transactions",
                kill_switch_path=switch,
                output_path=tmp_path / "transaction.json",
                now=NOW + timedelta(minutes=2),
            )
        )
    assert provider.snapshot_calls == 0
    with pytest.raises(ValueError, match="confirmation"):
        disable_kill_switch(switch, confirmation="wrong")
    assert disable_kill_switch(switch, confirmation="ENABLE_LIVE_APPLY")["enabled"] is False


def test_response_loss_after_mutation_is_reconstructed_and_rolled_back(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(operation_count=2, fail_after_mutation_call=2)
    result = asyncio.run(
        execute_live_apply(
            plan=plan(count=2),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )

    assert result["ok"] is False
    assert result["rollback_succeeded"] is True
    assert result["restore_ready"] is False
    assert f"[{MARKER}] OLD 1" in provider.dsl
    assert f"[{MARKER}] OLD 2" in provider.dsl
    journal = json.loads(Path(result["journal_path"]).read_text(encoding="utf-8"))
    assert journal["status"] == "rolled_back"


def test_missing_provider_capability_fails_before_snapshot(tmp_path: Path) -> None:
    provider = FakeProvider(capabilities={"layout_read"})
    with pytest.raises(ValueError, match="layout_update"):
        asyncio.run(
            execute_live_apply(
                plan=plan(),
                provider=provider,
                journal_root=tmp_path / "transactions",
                kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
                output_path=tmp_path / "transaction.json",
                now=NOW + timedelta(minutes=2),
            )
        )
    assert provider.snapshot_calls == 0


def test_operation_bundle_rejects_overlapping_replacements() -> None:
    value = operation_bundle(count=2)
    value["operations"][1]["old_text"] = value["operations"][0]["old_text"] + " suffix"
    value["bundle_digest"] = _manifest_digest(value, "bundle_digest")
    with pytest.raises(ValueError, match="texts overlap"):
        validate_live_operation_bundle(value)


def test_execution_rechecks_authorization_expiry_before_provider_access(
    tmp_path: Path,
) -> None:
    expired = plan()
    expired["authorization"]["expires_at"] = (NOW + timedelta(seconds=30)).isoformat().replace(
        "+00:00", "Z"
    )
    expired["plan_digest"] = _manifest_digest(expired, "plan_digest")
    provider = FakeProvider()
    with pytest.raises(ValueError, match="expired"):
        asyncio.run(
            execute_live_apply(
                plan=expired,
                provider=provider,
                journal_root=tmp_path / "transactions",
                kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
                output_path=tmp_path / "transaction.json",
                now=NOW + timedelta(minutes=2),
            )
        )
    assert provider.snapshot_calls == 0


def test_authorization_reservation_is_atomic_and_replay_uses_canonical_receipt(
    tmp_path: Path,
) -> None:
    active_plan = plan()
    auth_digest = active_plan["source_receipts"]["authorization_digest"]
    reservation = tmp_path / "transactions" / auth_digest
    reservation.mkdir(parents=True, mode=0o700)
    provider = FakeProvider()
    with pytest.raises(ValueError, match="reservation is incomplete or active"):
        asyncio.run(
            execute_live_apply(
                plan=active_plan,
                provider=provider,
                journal_root=tmp_path / "transactions",
                kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
                output_path=tmp_path / "transaction.json",
                now=NOW + timedelta(minutes=2),
            )
        )
    assert provider.snapshot_calls == 0

    reservation.rmdir()
    first = asyncio.run(
        execute_live_apply(
            plan=active_plan,
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    calls = provider.replace_calls
    replay = asyncio.run(
        execute_live_apply(
            plan=active_plan,
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "different-output.json",
            now=NOW + timedelta(minutes=3),
        )
    )
    assert first["ok"] is True
    assert replay["replayed_without_mutation"] is True
    assert replay["receipt_digest"] == first["receipt_digest"]
    assert provider.replace_calls == calls
    assert not (tmp_path / "different-output.json").exists()


def test_live_apply_rejects_symlinked_output_parent(tmp_path: Path) -> None:
    provider = FakeProvider()
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="output path is unsafe"):
        asyncio.run(
            execute_live_apply(
                plan=plan(),
                provider=provider,
                journal_root=tmp_path / "transactions",
                kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
                output_path=linked / "transaction.json",
                now=NOW + timedelta(minutes=2),
            )
        )
    assert provider.snapshot_calls == 0
    assert not (real / "transaction.json").exists()


def test_restore_blocks_external_snapshot_drift_before_mutation(tmp_path: Path) -> None:
    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    calls = provider.replace_calls
    provider.forced_snapshot_digest = "f" * 64
    with pytest.raises(ValueError, match="external board drift"):
        asyncio.run(
            restore_live_apply(
                transaction_receipt_path=tmp_path / "transaction.json",
                provider=provider,
                output_path=tmp_path / "restore.json",
            )
        )
    assert transaction["ok"] is True
    assert provider.replace_calls == calls


def test_restore_response_loss_recovers_committed_after_state(tmp_path: Path) -> None:
    provider = FakeProvider(operation_count=2)
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(count=2),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    provider.fail_after_mutation_call = provider.replace_calls + 2
    provider.failed_once = False
    result = asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    assert transaction["ok"] is True
    assert result["ok"] is False
    assert result["rollback_to_after_succeeded"] is True
    assert result["still_restore_ready"] is True
    assert f"[{MARKER}] NEW 1" in provider.dsl
    assert f"[{MARKER}] NEW 2" in provider.dsl
    journal = json.loads(Path(result["journal_path"]).read_text(encoding="utf-8"))
    assert journal["status"] == "committed"
    retry = asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    assert retry["ok"] is True
    assert f"[{MARKER}] OLD 1" in provider.dsl
    assert f"[{MARKER}] OLD 2" in provider.dsl


def test_plan_and_transaction_receipt_reject_unknown_fields(tmp_path: Path) -> None:
    from schauwerk.operator.live_apply import (
        validate_live_apply_plan,
        validate_live_transaction_receipt,
    )

    active_plan = plan()
    active_plan["unexpected"] = True
    active_plan["plan_digest"] = _manifest_digest(active_plan, "plan_digest")
    with pytest.raises(ValueError, match="plan fields"):
        validate_live_apply_plan(active_plan)

    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    persisted = json.loads((tmp_path / "transaction.json").read_text(encoding="utf-8"))
    persisted["unexpected"] = True
    persisted["receipt_digest"] = _receipt_digest(persisted)
    with pytest.raises(ValueError, match="receipt fields"):
        validate_live_transaction_receipt(persisted)
    assert transaction["ok"] is True


def test_private_live_inputs_require_owner_only_permissions(tmp_path: Path) -> None:
    from schauwerk.operator.live_apply import (
        load_live_authorization,
        load_live_operation_bundle,
    )

    bundle = operation_bundle()
    approved = authorization(bundle)
    bundle_path = tmp_path / "bundle.json"
    authorization_path = tmp_path / "authorization.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    authorization_path.write_text(json.dumps(approved), encoding="utf-8")
    bundle_path.chmod(0o644)
    authorization_path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        load_live_operation_bundle(bundle_path)
    with pytest.raises(ValueError, match="owner-only"):
        load_live_authorization(authorization_path)
    bundle_path.chmod(0o600)
    authorization_path.chmod(0o600)
    assert load_live_operation_bundle(bundle_path)["bundle_digest"] == bundle["bundle_digest"]
    assert (
        load_live_authorization(authorization_path)["authorization_digest"]
        == approved["authorization_digest"]
    )


def test_bundle_rejects_dsl_delimiters() -> None:
    value = operation_bundle()
    value["operations"][0]["new_text"] += ' "injection"'
    value["bundle_digest"] = _manifest_digest(value, "bundle_digest")
    with pytest.raises(ValueError, match="DSL delimiter"):
        validate_live_operation_bundle(value)


def test_core_authorization_compiler_requires_exact_confirmation() -> None:
    bundle = operation_bundle()
    with pytest.raises(ValueError, match="confirmation is invalid"):
        compile_live_authorization(
            gate_receipt=gate_receipt(),
            operation_bundle=bundle,
            approved_by="alex",
            approval_reference="bureau:schauwerk-t007",
            confirmation="approve",
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            authorization_id="sw009-live-authorization-test",
        )


def test_unexpected_dsl_side_effect_is_detected_and_rolled_back(
    tmp_path: Path,
) -> None:
    class SideEffectProvider(FakeProvider):
        injected = False

        async def read_dsl(self, *, alias: str) -> str:
            value = await super().read_dsl(alias=alias)
            if f"[{MARKER}] NEW" in value and not self.injected:
                self.injected = True
                return value + "\nunrelated TEXT content=UNDECLARED"
            return value

    provider = SideEffectProvider()
    result = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    assert result["ok"] is False
    assert "outside the declared operations" in result["failure"]
    assert result["rollback_succeeded"] is True
    assert f"[{MARKER}] OLD 1" in provider.dsl


def test_restore_blocks_external_dsl_drift_before_inverse_mutation(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    calls = provider.replace_calls
    provider.dsl += "\nunrelated TEXT content=EXTERNAL"
    with pytest.raises(ValueError, match="external DSL drift"):
        asyncio.run(
            restore_live_apply(
                transaction_receipt_path=tmp_path / "transaction.json",
                provider=provider,
                output_path=tmp_path / "restore.json",
            )
        )
    assert transaction["ok"] is True
    assert provider.replace_calls == calls


def test_restore_rejects_rehashed_journal_not_bound_to_transaction(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    journal_path = Path(transaction["journal_path"])
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["region_id"] = "different-managed-region"
    journal["journal_digest"] = _manifest_digest(journal, "journal_digest")
    write_json_owner_only(journal_path, journal)
    calls = provider.replace_calls
    with pytest.raises(ValueError, match="committed journal digest mismatch"):
        asyncio.run(
            restore_live_apply(
                transaction_receipt_path=tmp_path / "transaction.json",
                provider=provider,
                output_path=tmp_path / "restore.json",
            )
        )
    assert provider.replace_calls == calls


def test_restore_replay_rejects_corrupted_canonical_receipt(tmp_path: Path) -> None:
    provider = FakeProvider()
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    canonical = Path(transaction["journal_path"]).parent / "restore-receipt.json"
    corrupted = json.loads(canonical.read_text(encoding="utf-8"))
    corrupted["restored_operation_count"] = 99
    write_json_owner_only(canonical, corrupted)
    with pytest.raises(ValueError, match="digest mismatch"):
        asyncio.run(
            restore_live_apply(
                transaction_receipt_path=tmp_path / "transaction.json",
                provider=provider,
                output_path=tmp_path / "restore.json",
            )
        )


def test_provider_intermediate_dsl_digest_mismatch_triggers_rollback(
    tmp_path: Path,
) -> None:
    class WrongDigestProvider(FakeProvider):
        async def replace_text(
            self, *, alias: str, old_text: str, new_text: str
        ) -> dict:
            receipt = await super().replace_text(
                alias=alias, old_text=old_text, new_text=new_text
            )
            if old_text.startswith(f"[{MARKER}] OLD"):
                receipt["result_dsl_digest"] = "f" * 64
            return receipt

    provider = WrongDigestProvider()
    result = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    assert result["ok"] is False
    assert "provider DSL digest mismatch" in result["failure"]
    assert result["rollback_succeeded"] is True
    assert f"[{MARKER}] OLD 1" in provider.dsl


def test_live_draft_requires_managed_region_and_render_update() -> None:
    human = RegionDeclaration(
        view_id="test:human-view",
        region_id="human-notes",
        mode="human",
        surface_alias=ALIAS,
        expected_snapshot_digest=BEFORE_DIGEST,
        expected_source_digest="c" * 64,
        owner="operator",
        visibility="private",
    )
    with pytest.raises(ValueError, match="require a managed region"):
        compile_live_operation_bundle_template(region=human)

    value = operation_bundle()
    value["operation"] = "replace-region"
    value["bundle_digest"] = _manifest_digest(value, "bundle_digest")
    with pytest.raises(ValueError, match="only render-update"):
        validate_live_operation_bundle(value)


def test_loaded_authorization_can_compile_plan_without_internal_fields(
    tmp_path: Path,
) -> None:
    from schauwerk.operator.live_apply import load_live_authorization

    bundle = operation_bundle()
    approved = authorization(bundle)
    path = tmp_path / "authorization.json"
    write_json_owner_only(path, approved)
    loaded = load_live_authorization(path)

    assert set(loaded) == set(approved)
    assert "approved_at_parsed" not in loaded
    assert "expires_at_parsed" not in loaded
    compiled = compile_live_apply_plan(
        gate_receipt=gate_receipt(),
        operation_bundle=bundle,
        authorization=loaded,
        now=NOW + timedelta(minutes=1),
    )
    assert compiled["ready_for_live_apply"] is True


def test_restore_retry_rejects_failure_receipt_alias_mismatch(tmp_path: Path) -> None:
    provider = FakeProvider(operation_count=2)
    transaction = asyncio.run(
        execute_live_apply(
            plan=plan(count=2),
            provider=provider,
            journal_root=tmp_path / "transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=tmp_path / "transaction.json",
            now=NOW + timedelta(minutes=2),
        )
    )
    provider.fail_after_mutation_call = provider.replace_calls + 2
    provider.failed_once = False
    failed = asyncio.run(
        restore_live_apply(
            transaction_receipt_path=tmp_path / "transaction.json",
            provider=provider,
            output_path=tmp_path / "restore.json",
        )
    )
    assert transaction["ok"] is True
    assert failed["still_restore_ready"] is True
    canonical = Path(failed["journal_path"]).parent / "restore-receipt.json"
    value = json.loads(canonical.read_text(encoding="utf-8"))
    value["surface_alias"] = "different-test-board"
    value["receipt_digest"] = _receipt_digest(value)
    write_json_owner_only(canonical, value)
    with pytest.raises(ValueError, match="committed journal digest mismatch"):
        asyncio.run(
            restore_live_apply(
                transaction_receipt_path=tmp_path / "transaction.json",
                provider=provider,
                output_path=tmp_path / "restore.json",
            )
        )


def test_transaction_failure_receipts_are_strictly_validated(tmp_path: Path) -> None:
    preflight_provider = FakeProvider()
    preflight_provider.forced_snapshot_digest = "f" * 64
    preflight_path = tmp_path / "preflight-transaction.json"
    preflight = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=preflight_provider,
            journal_root=tmp_path / "preflight-transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=preflight_path,
            now=NOW + timedelta(minutes=2),
        )
    )
    persisted_preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert preflight["ok"] is False
    assert validate_live_transaction_failure_receipt(persisted_preflight)["ok"] is False
    persisted_preflight["unexpected"] = True
    persisted_preflight["receipt_digest"] = _receipt_digest(persisted_preflight)
    with pytest.raises(ValueError, match="fields are invalid"):
        validate_live_transaction_failure_receipt(persisted_preflight)

    apply_provider = FakeProvider(fail_after_mutation_call=1)
    apply_path = tmp_path / "apply-transaction.json"
    apply_failure = asyncio.run(
        execute_live_apply(
            plan=plan(),
            provider=apply_provider,
            journal_root=tmp_path / "apply-transactions",
            kill_switch_path=tmp_path / "LIVE_APPLY_DISABLED",
            output_path=apply_path,
            now=NOW + timedelta(minutes=2),
        )
    )
    persisted_apply = json.loads(apply_path.read_text(encoding="utf-8"))
    assert apply_failure["rollback_succeeded"] is True
    assert validate_live_transaction_failure_receipt(persisted_apply)[
        "manual_recovery_required"
    ] is False
    persisted_apply["manual_recovery_required"] = True
    persisted_apply["receipt_digest"] = _receipt_digest(persisted_apply)
    with pytest.raises(ValueError, match="recovery state is invalid"):
        validate_live_transaction_failure_receipt(persisted_apply)
