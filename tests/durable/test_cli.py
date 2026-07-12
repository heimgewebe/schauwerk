from __future__ import annotations

import json

from schauwerk import runner


def test_runner_dispatches_durable_adapter_catalog(monkeypatch, capsys) -> None:
    observed = {}

    def fake_catalog(*, output):
        observed["output"] = output
        return {"schema_version": "schauwerk-adapter-catalog.v1", "catalog_digest": "a" * 64}

    monkeypatch.setattr(runner, "handle_durable_adapter_catalog", fake_catalog)
    code = runner.main(["durable", "adapter-catalog", "--json"])
    assert code == 0
    assert observed == {"output": None}
    assert json.loads(capsys.readouterr().out)["catalog_digest"] == "a" * 64


def test_runner_dispatches_durable_maintenance(monkeypatch, capsys) -> None:
    observed = {}

    def fake_maintenance(**kwargs):
        observed.update(kwargs)
        return {"schema_version": "schauwerk-durable-write-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_durable_maintenance", fake_maintenance)
    code = runner.main(
        [
            "durable",
            "maintenance-propose",
            "before.json",
            "after.json",
            "--region",
            "grabowski.operator-overview.managed",
            "--created-at",
            "2026-07-12T09:00:00Z",
            "--output",
            "proposal.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "previous": "before.json",
        "current": "after.json",
        "region": "grabowski.operator-overview.managed",
        "created_at": "2026-07-12T09:00:00Z",
        "output": "proposal.json",
    }
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_runner_dispatches_durable_backup(monkeypatch, capsys) -> None:
    observed = {}

    def fake_backup(**kwargs):
        observed.update(kwargs)
        return {"schema_version": "schauwerk-durable-write-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_durable_backup", fake_backup)
    code = runner.main(
        [
            "durable",
            "backup-manifest",
            "backup.json",
            "--root",
            "/staged/source",
            "--created-at",
            "2026-07-12T09:00:00Z",
            "--output",
            "manifest.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "declaration": "backup.json",
        "root": "/staged/source",
        "created_at": "2026-07-12T09:00:00Z",
        "output": "manifest.json",
    }
    assert json.loads(capsys.readouterr().out)["ok"] is True
