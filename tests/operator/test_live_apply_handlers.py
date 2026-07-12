from __future__ import annotations

from pathlib import Path

import pytest

from schauwerk.cli_handlers import handle_region_sw009_live_authorization_create


def test_live_authorization_handler_requires_exact_confirmation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="confirmation is invalid"):
        handle_region_sw009_live_authorization_create(
            gate_path=str(tmp_path / "missing-gate.json"),
            bundle_path=str(tmp_path / "missing-bundle.json"),
            authorization_id="sw009-auth-test",
            approved_by="alex",
            approval_reference="bureau:test",
            confirmation="approve",
            valid_minutes=60,
            output=str(tmp_path / "authorization.json"),
        )
    assert not (tmp_path / "authorization.json").exists()


def test_apply_kill_switch_blocks_before_live_tool_discovery(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import schauwerk.cli_handlers as handlers
    from schauwerk.operator.live_apply import enable_kill_switch

    calls = {"tools": 0}

    class FakeClient:
        settings = SimpleNamespace(state_root=tmp_path)
        storage = object()

        async def tools(self):
            calls["tools"] += 1
            raise AssertionError("tool discovery must not run")

    reviewed = {"schema_version": "typed-region-live-apply-plan.v1"}
    monkeypatch.setattr(handlers, "_compile_live_plan_from_paths", lambda **_kwargs: reviewed)
    monkeypatch.setattr(handlers, "load_live_apply_plan", lambda _path: reviewed)
    enable_kill_switch(tmp_path / "LIVE_APPLY_DISABLED", reason="operator stop")
    with pytest.raises(ValueError, match="kill switch is enabled"):
        handlers.handle_region_sw009_live_apply(
            gate_path="gate.json",
            bundle_path="bundle.json",
            authorization_path="authorization.json",
            plan_path="plan.json",
            output=str(tmp_path / "transaction.json"),
            client=FakeClient(),
        )
    assert calls["tools"] == 0


def test_restore_rejects_invalid_local_receipt_before_live_tool_discovery(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    import schauwerk.cli_handlers as handlers

    calls = {"tools": 0}

    class FakeClient:
        settings = SimpleNamespace(state_root=tmp_path)
        storage = object()

        async def tools(self):
            calls["tools"] += 1
            raise AssertionError("tool discovery must not run")

    with pytest.raises(ValueError, match="unreadable"):
        handlers.handle_region_sw009_live_restore(
            transaction_receipt=str(tmp_path / "missing.json"),
            output=str(tmp_path / "restore.json"),
            client=FakeClient(),
        )
    assert calls["tools"] == 0


def test_apply_rejects_reviewed_plan_mismatch_before_live_tool_discovery(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace

    import schauwerk.cli_handlers as handlers

    calls = {"tools": 0}

    class FakeClient:
        settings = SimpleNamespace(state_root=tmp_path)
        storage = object()

        async def tools(self):
            calls["tools"] += 1
            raise AssertionError("tool discovery must not run")

    monkeypatch.setattr(
        handlers,
        "_compile_live_plan_from_paths",
        lambda **_kwargs: {"plan_digest": "a" * 64},
    )
    monkeypatch.setattr(
        handlers,
        "load_live_apply_plan",
        lambda _path: {"plan_digest": "b" * 64},
    )
    with pytest.raises(ValueError, match="no longer matches"):
        handlers.handle_region_sw009_live_apply(
            gate_path="gate.json",
            bundle_path="bundle.json",
            authorization_path="authorization.json",
            plan_path="plan.json",
            output=str(tmp_path / "transaction.json"),
            client=FakeClient(),
        )
    assert calls["tools"] == 0
