from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from schauwerk import runner
from schauwerk.cli_handlers import handle_overview_snapshot
from schauwerk.overview.model import read_snapshot


class FakeClient:
    def __init__(self, state_root: Path) -> None:
        self.settings = SimpleNamespace(state_root=state_root)
        self.live_calls = 0

    def status(self) -> dict:
        return {"local_state_present": True}

    def cached_auth_health(self) -> dict:
        return {
            "observed_at": "2026-07-11T03:00:00Z",
            "safe_for_live_board_operations": True,
        }

    async def live_status(self) -> dict:
        self.live_calls += 1
        return {
            "checked": True,
            "ok": True,
            "renewal_required": False,
            "tool_count": 32,
        }


def test_snapshot_handler_writes_owner_only_valid_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    import schauwerk.cli_handlers as handlers

    client = FakeClient(tmp_path / "miro")
    monkeypatch.setattr(handlers, "MiroMCPClient", lambda: client)
    output = tmp_path / "overview.json"
    receipt = handle_overview_snapshot(output=str(output), probe_provider=False)
    assert receipt["ok"] is True
    assert receipt["mutation_attempted"] is False
    assert receipt["provider_state"] == "ok"
    assert receipt["project_count"] == 3
    assert output.stat().st_mode & 0o077 == 0
    snapshot = read_snapshot(output)
    assert snapshot["snapshot_digest"] == receipt["snapshot_digest"]
    assert client.live_calls == 0


def test_runner_dispatches_overview_snapshot_and_serve(monkeypatch, capsys) -> None:
    observed = {}

    def fake_snapshot(*, output, probe_provider):
        observed["snapshot"] = {
            "output": output,
            "probe_provider": probe_provider,
        }
        return {"ok": True, "mutation_attempted": False}

    def fake_serve(*, port, probe_provider, open_browser):
        observed["serve"] = {
            "port": port,
            "probe_provider": probe_provider,
            "open_browser": open_browser,
        }
        return {"ok": True, "read_only": True}

    monkeypatch.setattr(runner, "handle_overview_snapshot", fake_snapshot)
    monkeypatch.setattr(runner, "handle_overview_serve", fake_serve)
    assert (
        runner.main(
            [
                "overview",
                "snapshot",
                "--output",
                "overview.json",
                "--probe-provider",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert (
        runner.main(
            [
                "overview",
                "serve",
                "--port",
                "8124",
                "--no-browser",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["read_only"] is True
    assert observed == {
        "snapshot": {
            "output": "overview.json",
            "probe_provider": True,
        },
        "serve": {
            "port": 8124,
            "probe_provider": False,
            "open_browser": False,
        },
    }
