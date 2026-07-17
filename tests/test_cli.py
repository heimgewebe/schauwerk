from __future__ import annotations

import json

from schauwerk import runner


def _ready_region_for_cli_chain() -> dict:
    return {
        "view_id": "learning:photosynthese",
        "region_id": "cluster-goals",
        "mode": "managed",
        "surface_alias": "nicole-mt-zoom-chunked-20260701-211733",
        "expected_snapshot_digest": "a" * 64,
        "expected_source_digest": "b" * 64,
        "owner": "schauwerk",
        "visibility": "classroom",
    }


def _ready_apply_scaffold_for_cli_chain() -> dict:
    region = _ready_region_for_cli_chain()
    return {
        "schema_version": "typed-region-apply-scaffold.v1",
        "ok": True,
        "mutation_attempted": False,
        "ready_for_fixture_apply": True,
        "ready_for_live_apply": False,
        "operation": "render-update",
        "region": region,
        "snapshot": {
            "board_alias": region["surface_alias"],
            "content_digest": "a" * 64,
            "item_count": 4,
            "repeatability_verified": True,
            "sanitized_references": True,
        },
        "blocked_reasons": [],
        "boundary": {
            "scaffold_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
    }


def _fixture_operations_for_cli_chain() -> list[dict[str, str]]:
    return [
        {
            "operation_id": "create-title",
            "action": "create-item",
            "region_id": "cluster-goals",
            "local_ref": "title-card",
            "payload_digest": "c" * 64,
        },
        {
            "operation_id": "update-body",
            "action": "update-item",
            "region_id": "cluster-goals",
            "local_ref": "body-card",
            "payload_digest": "d" * 64,
        },
    ]


def _write_json(path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_runner_dispatches_read_only_inspection(monkeypatch, capsys) -> None:
    observed = {}

    def fake_inspect(*, query, owned_by_me, limit, max_pages):
        observed.update(query=query, owned=owned_by_me, limit=limit, pages=max_pages)
        return {"read_only": True, "boards": {"returned_count": 0}}

    monkeypatch.setattr(runner, "handle_inspect", fake_inspect)

    exit_code = runner.main(
        [
            "miro",
            "inspect",
            "--query",
            "grabowski",
            "--owned-by-me",
            "--max-pages",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    assert observed == {"query": "grabowski", "owned": True, "limit": 20, "pages": 3}
    assert json.loads(capsys.readouterr().out) == {
        "read_only": True,
        "boards": {"returned_count": 0},
    }


def test_runner_dispatches_board_add(monkeypatch, capsys) -> None:
    observed = {}

    def fake_add(*, alias, miro_url, replace):
        observed.update(alias=alias, miro_url=miro_url, replace=replace)
        return {"alias": alias, "reference_digest": "digest"}

    monkeypatch.setattr(runner, "handle_board_add", fake_add)
    code = runner.main(
        ["miro", "board", "add", "fixture", "https://miro.com/app/board/private", "--json"]
    )
    assert code == 0
    assert observed["alias"] == "fixture"
    assert observed["replace"] is False
    assert "miro.com" not in capsys.readouterr().out


def test_runner_dispatches_snapshot(monkeypatch, capsys) -> None:
    observed = {}

    def fake_snapshot(**kwargs):
        observed.update(kwargs)
        return {"board_alias": kwargs["alias"], "repeatability_verified": True}

    monkeypatch.setattr(runner, "handle_snapshot", fake_snapshot)
    code = runner.main(
        ["miro", "snapshot", "fixture", "--item-limit", "50", "--no-comments", "--json"]
    )
    assert code == 0
    assert observed == {
        "alias": "fixture",
        "output": None,
        "item_limit": 50,
        "comment_limit": 50,
        "max_pages": 20,
        "include_comments": False,
    }
    assert json.loads(capsys.readouterr().out)["repeatability_verified"] is True


def test_runner_dispatches_learning_render(monkeypatch, capsys) -> None:
    observed = {}

    def fake_render(*, input_path, output, template):
        observed.update(input_path=input_path, output=output, template=template)
        return {"topic": "fixture", "dsl_line_count": 3}

    monkeypatch.setattr(runner, "handle_learn_render", fake_render)
    code = runner.main(["miro", "learn", "render", "topic.yml", "--output", "out.dsl", "--json"])

    assert code == 0
    assert observed == {"input_path": "topic.yml", "output": "out.dsl", "template": "classic"}
    assert json.loads(capsys.readouterr().out)["dsl_line_count"] == 3


def test_runner_dispatches_learning_apply(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply(*, input_path, alias, template):
        observed.update(input_path=input_path, alias=alias, template=template)
        return {
            "topic": "fixture",
            "layout": {"board_alias": alias, "success": True, "created_count": 3},
        }

    monkeypatch.setattr(runner, "handle_learn_apply", fake_apply)
    code = runner.main(["miro", "learn", "apply", "board-a", "topic.yml", "--json"])

    assert code == 0
    assert observed == {"input_path": "topic.yml", "alias": "board-a", "template": "classic"}
    result = json.loads(capsys.readouterr().out)
    assert result["layout"]["board_alias"] == "board-a"
    assert result["layout"]["success"] is True


def test_runner_dispatches_live_status(monkeypatch, capsys) -> None:
    observed = {}

    def fake_status(*, live):
        observed["live"] = live
        return {"authorized_locally": True, "live": {"checked": live, "ok": True}}

    monkeypatch.setattr(runner, "handle_status", fake_status)
    code = runner.main(["miro", "status", "--live", "--json"])

    assert code == 0
    assert observed == {"live": True}
    result = json.loads(capsys.readouterr().out)
    assert result["live"] == {"checked": True, "ok": True}


def test_runner_dispatches_doctor_without_live(monkeypatch, capsys) -> None:
    observed = {}

    def fake_doctor(*, live):
        observed["live"] = live
        return {"schema_version": "miro-auth-doctor.v1", "checked_live": live}

    monkeypatch.setattr(runner, "handle_doctor", fake_doctor)
    code = runner.main(["miro", "doctor", "--no-live", "--json"])

    assert code == 0
    assert observed == {"live": False}
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "miro-auth-doctor.v1",
        "checked_live": False,
    }


def test_runner_dispatches_doctor_with_live_by_default(monkeypatch, capsys) -> None:
    observed = {}

    def fake_doctor(*, live):
        observed["live"] = live
        return {"schema_version": "miro-auth-doctor.v1", "checked_live": live}

    monkeypatch.setattr(runner, "handle_doctor", fake_doctor)
    code = runner.main(["miro", "doctor", "--json"])

    assert code == 0
    assert observed == {"live": True}
    assert json.loads(capsys.readouterr().out)["checked_live"] is True


def test_runner_dispatches_learning_live_test(monkeypatch, capsys) -> None:
    observed = {}

    def fake_live_test(**kwargs):
        observed.update(kwargs)
        return {
            "alias": kwargs["alias"],
            "layout": {"success": True, "created_count": 3},
            "layout_read": {"connector_count": 1},
        }

    monkeypatch.setattr(runner, "handle_learn_live_test", fake_live_test)
    code = runner.main(
        [
            "miro",
            "learn",
            "live-test",
            "topic.yml",
            "--alias",
            "live-a",
            "--board-name",
            "Live A",
            "--output-dir",
            "/tmp/live-a",
            "--replace-alias",
            "--no-comments",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "input_path": "topic.yml",
        "alias": "live-a",
        "board_name": "Live A",
        "output_dir": "/tmp/live-a",
        "replace_alias": True,
        "item_limit": 200,
        "comment_limit": 50,
        "max_pages": 20,
        "include_comments": False,
        "template": "classic",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["layout"]["success"] is True
    assert result["layout_read"]["connector_count"] == 1


def test_runner_dispatches_quality(monkeypatch, capsys) -> None:
    observed = {}

    def fake_quality(**kwargs):
        observed.update(kwargs)
        return {"board_alias": kwargs["alias"], "ok": True, "score": 100}

    monkeypatch.setattr(runner, "handle_quality", fake_quality)
    code = runner.main(
        [
            "miro",
            "quality",
            "live-a",
            "after.json",
            "--output",
            "quality.json",
            "--expected-min-connectors",
            "2",
            "--expected-min-docs",
            "1",
            "--expected-min-tables",
            "2",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "alias": "live-a",
        "snapshot": "after.json",
        "output": "quality.json",
        "expected_min_connectors": 2,
        "expected_min_docs": 1,
        "expected_min_tables": 2,
    }
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_runner_dispatches_region_plan(monkeypatch, capsys) -> None:
    observed = {}

    def fake_region_plan(*, input_path, operation, output):
        observed.update(input_path=input_path, operation=operation, output=output)
        return {"schema_version": "typed-region-plan.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_plan", fake_region_plan)
    code = runner.main(
        [
            "miro",
            "region",
            "plan",
            "region.yml",
            "--operation",
            "replace-region",
            "--output",
            "plan.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "input_path": "region.yml",
        "operation": "replace-region",
        "output": "plan.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == "typed-region-plan.v1"


def test_runner_dispatches_region_preflight(monkeypatch, capsys) -> None:
    observed = {}

    def fake_region_preflight(*, input_path, snapshot, operation, output):
        observed.update(
            input_path=input_path, snapshot=snapshot, operation=operation, output=output
        )
        return {"schema_version": "typed-region-preflight.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_preflight", fake_region_preflight)
    code = runner.main(
        [
            "miro",
            "region",
            "preflight",
            "region.yml",
            "--snapshot",
            "before.json",
            "--operation",
            "replace-region",
            "--output",
            "preflight.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "input_path": "region.yml",
        "snapshot": "before.json",
        "operation": "replace-region",
        "output": "preflight.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == "typed-region-preflight.v1"


def test_runner_dispatches_region_apply_scaffold(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply_scaffold(*, preflight, output):
        observed.update(preflight=preflight, output=output)
        return {"schema_version": "typed-region-apply-scaffold.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_apply_scaffold", fake_apply_scaffold)
    code = runner.main(
        ["miro", "region", "apply-scaffold", "preflight.json", "--output", "apply.json", "--json"]
    )

    assert code == 0
    assert observed == {"preflight": "preflight.json", "output": "apply.json"}
    assert json.loads(capsys.readouterr().out)["schema_version"] == "typed-region-apply-scaffold.v1"


def test_runner_dispatches_region_apply_receipt(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply_receipt(*, scaffold, fixture, output):
        observed.update(scaffold=scaffold, fixture=fixture, output=output)
        return {"schema_version": "typed-region-apply-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_apply_receipt", fake_apply_receipt)
    code = runner.main(
        [
            "miro",
            "region",
            "apply-receipt",
            "apply-scaffold.json",
            "--fixture",
            "fixture-ops.yml",
            "--output",
            "apply-receipt.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "scaffold": "apply-scaffold.json",
        "fixture": "fixture-ops.yml",
        "output": "apply-receipt.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == "typed-region-apply-receipt.v1"


def test_runner_dispatches_region_operation_contract(monkeypatch, capsys) -> None:
    observed = {}

    def fake_operation_contract(*, scaffold, fixture, output):
        observed.update(scaffold=scaffold, fixture=fixture, output=output)
        return {"schema_version": "typed-region-operation-contract.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_operation_contract", fake_operation_contract)
    code = runner.main(
        [
            "miro",
            "region",
            "operation-contract",
            "apply-scaffold.json",
            "--fixture",
            "fixture-ops.yml",
            "--output",
            "operation-contract.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "scaffold": "apply-scaffold.json",
        "fixture": "fixture-ops.yml",
        "output": "operation-contract.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-operation-contract.v1"
    )


def test_runner_dispatches_region_apply_simulation(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply_simulation(*, operation_contract, after_snapshot, output):
        observed.update(
            operation_contract=operation_contract,
            after_snapshot=after_snapshot,
            output=output,
        )
        return {"schema_version": "typed-region-apply-simulation-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_apply_simulation", fake_apply_simulation)
    code = runner.main(
        [
            "miro",
            "region",
            "apply-simulation",
            "operation-contract.json",
            "--after-snapshot",
            "after.json",
            "--output",
            "apply-simulation.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "operation_contract": "operation-contract.json",
        "after_snapshot": "after.json",
        "output": "apply-simulation.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-apply-simulation-receipt.v1"
    )


def test_region_operation_contract_cli_writes_real_receipt(tmp_path, capsys) -> None:
    scaffold = tmp_path / "apply-scaffold.json"
    fixture = tmp_path / "fixture-ops.json"
    output = tmp_path / "operation-contract.json"
    _write_json(scaffold, _ready_apply_scaffold_for_cli_chain())
    _write_json(fixture, {"fixture_operations": _fixture_operations_for_cli_chain()})

    code = runner.main(
        [
            "miro",
            "region",
            "operation-contract",
            str(scaffold),
            "--fixture",
            str(fixture),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_receipt["schema_version"] == "typed-region-operation-contract.v1"
    assert written["schema_version"] == "typed-region-operation-contract.v1"
    assert written["ok"] is True
    assert written["boundary"] == {
        "fixture_only": True,
        "simulation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_region_apply_simulation_cli_writes_real_receipt(tmp_path, capsys) -> None:
    scaffold = tmp_path / "apply-scaffold.json"
    fixture = tmp_path / "fixture-ops.json"
    contract_path = tmp_path / "operation-contract.json"
    after_snapshot_path = tmp_path / "after.json"
    output = tmp_path / "apply-simulation.json"
    _write_json(scaffold, _ready_apply_scaffold_for_cli_chain())
    _write_json(fixture, {"fixture_operations": _fixture_operations_for_cli_chain()})

    assert runner.main(
        [
            "miro",
            "region",
            "operation-contract",
            str(scaffold),
            "--fixture",
            str(fixture),
            "--output",
            str(contract_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _write_json(
        after_snapshot_path,
        {
            "board_alias": contract["region"]["surface_alias"],
            "content_digest": "e" * 64,
            "item_count": 6,
            "repeatability_verified": True,
            "sanitized_references": True,
            "operation_contract_digest": contract["contract_digest"],
            "operation_contract_operations_digest": contract["operations_digest"],
            "idempotency_key": contract["idempotency"]["key"],
            "idempotency_verified": True,
        },
    )

    code = runner.main(
        [
            "miro",
            "region",
            "apply-simulation",
            str(contract_path),
            "--after-snapshot",
            str(after_snapshot_path),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_receipt["schema_version"] == "typed-region-apply-simulation-receipt.v1"
    assert written["schema_version"] == "typed-region-apply-simulation-receipt.v1"
    assert written["ok"] is True
    assert written["boundary"]["simulation_only"] is True
    assert "after_snapshot_input_digest" in written["source_receipts"]


def test_region_simulation_cli_chain_reaches_restore_receipt(tmp_path, capsys) -> None:
    scaffold = tmp_path / "apply-scaffold.json"
    fixture = tmp_path / "fixture-ops.json"
    contract_path = tmp_path / "operation-contract.json"
    after_snapshot_path = tmp_path / "after.json"
    apply_simulation_path = tmp_path / "apply-simulation.json"
    output = tmp_path / "simulation-postflight.json"
    restored_snapshot_path = tmp_path / "restored.json"
    restore_output = tmp_path / "restore.json"
    closeout_output = tmp_path / "simulation-closeout.json"
    _write_json(scaffold, _ready_apply_scaffold_for_cli_chain())
    _write_json(fixture, {"fixture_operations": _fixture_operations_for_cli_chain()})

    assert runner.main(
        [
            "miro",
            "region",
            "operation-contract",
            str(scaffold),
            "--fixture",
            str(fixture),
            "--output",
            str(contract_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _write_json(
        after_snapshot_path,
        {
            "board_alias": contract["region"]["surface_alias"],
            "content_digest": "e" * 64,
            "item_count": 6,
            "repeatability_verified": True,
            "sanitized_references": True,
            "operation_contract_digest": contract["contract_digest"],
            "operation_contract_operations_digest": contract["operations_digest"],
            "idempotency_key": contract["idempotency"]["key"],
            "idempotency_verified": True,
        },
    )
    assert runner.main(
        [
            "miro",
            "region",
            "apply-simulation",
            str(contract_path),
            "--after-snapshot",
            str(after_snapshot_path),
            "--output",
            str(apply_simulation_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    code = runner.main(
        [
            "miro",
            "region",
            "simulation-postflight",
            str(apply_simulation_path),
            "--output",
            str(output),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_receipt["schema_version"] == "typed-region-postflight-receipt.v1"
    assert written["schema_version"] == "typed-region-postflight-receipt.v1"
    assert written["ok"] is True
    assert written["ready_for_restore"] is True
    assert written["boundary"]["simulation_only"] is True
    assert "apply_simulation_receipt_digest" in written["source_receipts"]

    _write_json(
        restored_snapshot_path,
        {
            "board_alias": written["pre_apply_snapshot"]["board_alias"],
            "content_digest": written["pre_apply_snapshot"]["content_digest"],
            "item_count": written["pre_apply_snapshot"]["item_count"],
            "repeatability_verified": True,
            "sanitized_references": True,
        },
    )

    assert runner.main(
        [
            "miro",
            "region",
            "restore-receipt",
            str(output),
            "--restored-snapshot",
            str(restored_snapshot_path),
            "--output",
            str(restore_output),
            "--json",
        ]
    ) == 0
    restore_stdout = json.loads(capsys.readouterr().out)
    restore_written = json.loads(restore_output.read_text(encoding="utf-8"))
    assert restore_stdout["schema_version"] == "typed-region-restore-receipt.v1"
    assert restore_written["schema_version"] == "typed-region-restore-receipt.v1"
    assert restore_written["ok"] is True
    assert restore_written["live_restore_attempted"] is False
    assert restore_written["ready_for_closeout"] is True
    assert restore_written["boundary"]["simulation_only"] is True

    assert runner.main(
        [
            "miro",
            "region",
            "simulation-closeout",
            str(restore_output),
            "--output",
            str(closeout_output),
            "--json",
        ]
    ) == 0
    closeout_stdout = json.loads(capsys.readouterr().out)
    closeout_written = json.loads(closeout_output.read_text(encoding="utf-8"))
    assert closeout_stdout["schema_version"] == (
        "typed-region-sw009-simulation-closeout-receipt.v1"
    )
    assert closeout_written["ok"] is True
    assert closeout_written["ready_for_live_apply"] is False
    assert closeout_written["closes_live_sw003_gate"] is False
    assert closeout_written["live_apply_gate"]["blocked_reasons"] == [
        "dedicated_live_apply_gate_required"
    ]
    assert closeout_written["boundary"] == {
        "fixture_only": True,
        "simulation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "does_not_close_sw003_live_gate": True,
    }


def test_region_apply_simulation_cli_rejects_wrong_contract_schema(tmp_path, capsys) -> None:
    contract_path = tmp_path / "operation-contract.json"
    after_snapshot_path = tmp_path / "after.json"
    _write_json(contract_path, {"schema_version": "wrong"})
    _write_json(after_snapshot_path, {"content_digest": "e" * 64, "board_alias": "fixture"})

    code = runner.main(
        [
            "miro",
            "region",
            "apply-simulation",
            str(contract_path),
            "--after-snapshot",
            str(after_snapshot_path),
            "--json",
        ]
    )

    assert code == 2
    assert "unsupported schema" in capsys.readouterr().err


def test_runner_dispatches_region_simulation_postflight(monkeypatch, capsys) -> None:
    observed = {}

    def fake_simulation_postflight(*, apply_simulation_receipt, output):
        observed.update(
            apply_simulation_receipt=apply_simulation_receipt, output=output
        )
        return {"schema_version": "typed-region-postflight-receipt.v1", "ok": True}

    monkeypatch.setattr(
        runner, "handle_region_simulation_postflight", fake_simulation_postflight
    )
    code = runner.main(
        [
            "miro",
            "region",
            "simulation-postflight",
            "apply-simulation.json",
            "--output",
            "simulation-postflight.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "apply_simulation_receipt": "apply-simulation.json",
        "output": "simulation-postflight.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-postflight-receipt.v1"
    )


def test_runner_dispatches_region_simulation_closeout(monkeypatch, capsys) -> None:
    observed = {}

    def fake_closeout(*, restore_receipt, output):
        observed.update(restore_receipt=restore_receipt, output=output)
        return {
            "schema_version": "typed-region-sw009-simulation-closeout-receipt.v1",
            "ok": True,
        }

    monkeypatch.setattr(runner, "handle_region_simulation_closeout", fake_closeout)
    code = runner.main(
        [
            "miro",
            "region",
            "simulation-closeout",
            "restore.json",
            "--output",
            "simulation-closeout.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "restore_receipt": "restore.json",
        "output": "simulation-closeout.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-sw009-simulation-closeout-receipt.v1"
    )


def test_runner_dispatches_region_postflight(monkeypatch, capsys) -> None:
    observed = {}

    def fake_postflight(*, apply_receipt, after_snapshot, output):
        observed.update(
            apply_receipt=apply_receipt, after_snapshot=after_snapshot, output=output
        )
        return {"schema_version": "typed-region-postflight-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_postflight", fake_postflight)
    code = runner.main(
        [
            "miro",
            "region",
            "postflight",
            "apply-receipt.json",
            "--after-snapshot",
            "after.json",
            "--output",
            "postflight.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "apply_receipt": "apply-receipt.json",
        "after_snapshot": "after.json",
        "output": "postflight.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-postflight-receipt.v1"
    )


def test_runner_dispatches_region_restore_receipt(monkeypatch, capsys) -> None:
    observed = {}

    def fake_restore(*, postflight, restored_snapshot, output):
        observed.update(
            postflight=postflight, restored_snapshot=restored_snapshot, output=output
        )
        return {"schema_version": "typed-region-restore-receipt.v1", "ok": True}

    monkeypatch.setattr(runner, "handle_region_restore_receipt", fake_restore)
    code = runner.main(
        [
            "miro",
            "region",
            "restore-receipt",
            "postflight.json",
            "--restored-snapshot",
            "restored.json",
            "--output",
            "restore.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "postflight": "postflight.json",
        "restored_snapshot": "restored.json",
        "output": "restore.json",
    }
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "typed-region-restore-receipt.v1"
    )


def test_runner_dispatches_region_sw003_live_gate(monkeypatch, capsys) -> None:
    observed = {}

    def fake_live_gate(*, evidence, output):
        observed.update(evidence=evidence, output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-evaluation.v1",
            "claim_present": True,
            "claim_valid": False,
            "mutation_attempted": False,
            "closes_live_sw003_gate": False,
        }

    monkeypatch.setattr(runner, "handle_region_sw003_live_gate", fake_live_gate)
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            "live-gate-evidence.json",
            "--output",
            "live-gate-evaluation.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "evidence": "live-gate-evidence.json",
        "output": "live-gate-evaluation.json",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-evaluation.v1"
    assert result["mutation_attempted"] is False


def test_runner_dispatches_region_sw003_live_gate_status(monkeypatch, capsys) -> None:
    observed = {}

    def fake_live_gate_status(*, evaluation_receipt, output):
        observed.update(evaluation_receipt=evaluation_receipt, output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-status.v1",
            "ready_for_live_apply": False,
            "closes_live_sw003_gate": False,
        }

    monkeypatch.setattr(
        runner, "handle_region_sw003_live_gate_status", fake_live_gate_status
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-status",
            "live-gate-evaluation.json",
            "--output",
            "live-gate-status.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "evaluation_receipt": "live-gate-evaluation.json",
        "output": "live-gate-status.json",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-status.v1"
    assert result["ready_for_live_apply"] is False


def test_runner_dispatches_region_sw003_live_gate_review_packet(monkeypatch, capsys) -> None:
    observed = {}

    def fake_review_packet(*, status_receipt, output):
        observed.update(status_receipt=status_receipt, output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-review-packet.v1",
            "ready_for_live_apply": False,
            "closes_live_sw003_gate": False,
        }

    monkeypatch.setattr(
        runner, "handle_region_sw003_live_gate_review_packet", fake_review_packet
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-review-packet",
            "live-gate-status.json",
            "--output",
            "review-packet.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "status_receipt": "live-gate-status.json",
        "output": "review-packet.json",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-review-packet.v1"
    assert result["ready_for_live_apply"] is False


def test_runner_dispatches_region_sw003_live_gate_evidence_packet(monkeypatch, capsys) -> None:
    observed = {}

    def fake_evidence_packet(*, review_packet, output):
        observed.update(review_packet=review_packet, output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-evidence-packet.v1",
            "ready_for_live_apply": False,
            "closes_live_sw003_gate": False,
        }

    monkeypatch.setattr(
        runner, "handle_region_sw003_live_gate_evidence_packet", fake_evidence_packet
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-evidence-packet",
            "live-gate-review-packet.json",
            "--output",
            "evidence-packet.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "review_packet": "live-gate-review-packet.json",
        "output": "evidence-packet.json",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-evidence-packet.v1"
    assert result["ready_for_live_apply"] is False


def test_runner_dispatches_region_sw009_live_apply_gate(monkeypatch, capsys) -> None:
    observed = {}

    def fake_gate(*, scaffold, sw003_evidence_packet, output, acknowledgements):
        observed.update(
            scaffold=scaffold,
            sw003_evidence_packet=sw003_evidence_packet,
            output=output,
            acknowledgements=acknowledgements,
        )
        return {
            "schema_version": "typed-region-sw009-live-apply-gate-receipt.v1",
            "ready_for_live_apply": True,
            "live_apply_attempted": False,
        }

    monkeypatch.setattr(runner, "handle_region_sw009_live_apply_gate", fake_gate)
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-gate",
            "apply-scaffold.json",
            "--sw003-evidence-packet",
            "sw003-evidence-packet.json",
            "--ack-allowlisted-scope",
            "--ack-preflight-receipt-digest",
            "--ack-before-snapshot",
            "--ack-review-packet",
            "--ack-restore-strategy",
            "--ack-postflight-plan",
            "--ack-provider-redaction",
            "--output",
            "live-gate.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed["scaffold"] == "apply-scaffold.json"
    assert observed["sw003_evidence_packet"] == "sw003-evidence-packet.json"
    assert observed["output"] == "live-gate.json"
    assert all(observed["acknowledgements"].values())
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw009-live-apply-gate-receipt.v1"
    assert result["ready_for_live_apply"] is True


def test_runner_dispatches_region_sw009_live_apply_candidate_template(
    monkeypatch, capsys
) -> None:
    observed = {}

    def fake_template(*, output):
        observed["output"] = output
        return {
            "schema_version": "typed-region-sw009-live-apply-candidate.v1",
            "mutation_attempted": False,
        }

    monkeypatch.setattr(
        runner, "handle_region_sw009_live_apply_candidate_template", fake_template
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-candidate-template",
            "--output",
            "candidate.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {"output": "candidate.json"}
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw009-live-apply-candidate.v1"
    assert result["mutation_attempted"] is False


def test_runner_dispatches_region_sw009_live_apply_candidate_check(
    monkeypatch, capsys
) -> None:
    observed = {}

    def fake_check(*, candidate_path, output):
        observed.update(candidate_path=candidate_path, output=output)
        return {
            "schema_version": "typed-region-sw009-live-apply-candidate-receipt.v1",
            "ready_for_live_apply": True,
            "live_apply_attempted": False,
        }

    monkeypatch.setattr(
        runner, "handle_region_sw009_live_apply_candidate_check", fake_check
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-candidate-check",
            "candidate.json",
            "--output",
            "candidate-receipt.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {
        "candidate_path": "candidate.json",
        "output": "candidate-receipt.json",
    }
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == (
        "typed-region-sw009-live-apply-candidate-receipt.v1"
    )
    assert result["ready_for_live_apply"] is True
    assert result["live_apply_attempted"] is False


def test_runner_dispatches_region_sw003_live_gate_requirements(monkeypatch, capsys) -> None:
    observed = {}

    def fake_requirements(*, output):
        observed.update(output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-requirements.v1",
            "ok": True,
            "requirements": [],
        }

    monkeypatch.setattr(
        runner, "handle_region_sw003_live_gate_requirements", fake_requirements
    )
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-requirements",
            "--output",
            "requirements.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {"output": "requirements.json"}
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-requirements.v1"


def test_runner_dispatches_region_sw003_live_gate_template(monkeypatch, capsys) -> None:
    observed = {}

    def fake_template(*, output):
        observed.update(output=output)
        return {
            "schema_version": "typed-region-sw003-live-gate-template.v1",
            "ok": True,
            "template_only": True,
        }

    monkeypatch.setattr(runner, "handle_region_sw003_live_gate_template", fake_template)
    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-template",
            "--output",
            "template.json",
            "--json",
        ]
    )

    assert code == 0
    assert observed == {"output": "template.json"}
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "typed-region-sw003-live-gate-template.v1"


def test_registry_status_cli(capsys) -> None:
    assert runner.main(["registry", "status", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True
    assert result["counts"]["projects"] == 3


def test_registry_show_cli(capsys) -> None:
    assert runner.main(["registry", "show", "views", "grabowski.operator-overview", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["item"]["project_id"] == "grabowski"


def test_grabowski_pilot_cli(tmp_path, capsys) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": "Bounded operator contract.",
                "capabilities": [
                    {"id": "read", "category": "repo", "risk_class": "low", "read_only": True}
                ],
                "runtime_contract": {"expected_tools": ["read"]},
                "policy_contract": {"active_profile": "observe", "mode": "observe"},
                "operating_protocol": {"name": "Operator Relay v0"},
            }
        ),
        encoding="utf-8",
    )
    snapshot = tmp_path / "snapshot.json"
    dsl = tmp_path / "view.dsl"
    assert runner.main(
        [
            "pilot",
            "grabowski",
            str(source),
            "--snapshot-output",
            str(snapshot),
            "--dsl-output",
            str(dsl),
            "--json",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider_mutation_attempted"] is False
    assert snapshot.is_file()
    assert dsl.is_file()


def test_grabowski_operational_pilot_cli(tmp_path, capsys) -> None:
    context = tmp_path / "operator-context.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": "Bounded operator contract.",
                "capabilities": [
                    {"id": "read", "category": "repo", "risk_class": "low", "read_only": True}
                ],
                "runtime_contract": {"expected_tools": ["read"]},
                "policy_contract": {"active_profile": "observe", "mode": "observe"},
                "operating_protocol": {"name": "Operator Relay v0"},
            }
        ),
        encoding="utf-8",
    )
    static = tmp_path / "static.json"
    assert (
        runner.main(
            ["pilot", "grabowski", str(context), "--snapshot-output", str(static), "--json"]
        )
        == 0
    )
    capsys.readouterr()
    observed = "2026-07-10T05:30:00Z"
    observation = tmp_path / "observation.json"
    observation.write_text(
        json.dumps(
            {
                "schema_version": "grabowski-operational-observation.v1",
                "evaluated_at": "2026-07-10T05:31:00Z",
                "channels": {
                    "hosts": {
                        "source_id": "grabowski.fleet-observation",
                        "authority": "operational",
                        "observed_at": observed,
                        "stale_after_seconds": 900,
                        "collection_status": "unavailable",
                        "error_code": "fixture_unavailable",
                        "summary": None,
                    },
                    "runtime": {
                        "source_id": "grabowski.runtime-observation",
                        "authority": "operational",
                        "observed_at": observed,
                        "stale_after_seconds": 300,
                        "collection_status": "unavailable",
                        "error_code": "fixture_unavailable",
                        "summary": None,
                    },
                    "work": {
                        "source_id": "bureau.grabowski-work-observation",
                        "authority": "operational",
                        "observed_at": observed,
                        "stale_after_seconds": 300,
                        "collection_status": "unavailable",
                        "error_code": "fixture_unavailable",
                        "summary": None,
                    },
                    "gaps": {
                        "source_id": "bureau.grabowski-gap-observation",
                        "authority": "derived",
                        "observed_at": observed,
                        "stale_after_seconds": 1800,
                        "collection_status": "unavailable",
                        "error_code": "fixture_unavailable",
                        "summary": None,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "operational.json"
    dsl = tmp_path / "operational.dsl"
    assert (
        runner.main(
            [
                "pilot",
                "grabowski-operational",
                str(static),
                str(observation),
                "--snapshot-output",
                str(output),
                "--dsl-output",
                str(dsl),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["overall_status"] == "unavailable"
    assert result["provider_mutation_attempted"] is False


def test_runner_dispatches_generic_software_pilot(monkeypatch, capsys) -> None:
    observed = {}

    def fake_software(
        *,
        input_path,
        snapshot_output,
        dsl_output,
        visual_spec_output,
        visual_quality_output,
        visual_dsl_output,
    ):
        observed.update(
            input_path=input_path,
            snapshot_output=snapshot_output,
            dsl_output=dsl_output,
            visual_spec_output=visual_spec_output,
            visual_quality_output=visual_quality_output,
            visual_dsl_output=visual_dsl_output,
        )
        return {"project_id": "repoground", "provider_mutation_attempted": False}

    monkeypatch.setattr(runner, "handle_software_pilot", fake_software)
    code = runner.main(
        [
            "pilot",
            "software",
            "input.json",
            "--snapshot-output",
            "snapshot.json",
            "--dsl-output",
            "view.dsl",
            "--visual-spec-output",
            "visual.json",
            "--visual-quality-output",
            "quality.json",
            "--visual-dsl-output",
            "visual.dsl",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "input_path": "input.json",
        "snapshot_output": "snapshot.json",
        "dsl_output": "view.dsl",
        "visual_spec_output": "visual.json",
        "visual_quality_output": "quality.json",
        "visual_dsl_output": "visual.dsl",
    }
    assert json.loads(capsys.readouterr().out)["project_id"] == "repoground"


def test_runner_dispatches_education_variant(monkeypatch, capsys) -> None:
    observed = {}

    def fake_render(*, input_path, variant, output):
        observed.update(input_path=input_path, variant=variant, output=output)
        return {"variant": variant, "network_dependencies": False}

    monkeypatch.setattr(runner, "handle_education_render", fake_render)
    code = runner.main(
        [
            "education",
            "render",
            "lesson.json",
            "--variant",
            "student",
            "--output",
            "student.html",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "input_path": "lesson.json",
        "variant": "student",
        "output": "student.html",
    }
    assert json.loads(capsys.readouterr().out)["network_dependencies"] is False


def test_runner_dispatches_education_offline(monkeypatch, capsys) -> None:
    observed = {}

    def fake_offline(*, input_path, output_dir, variant):
        observed.update(input_path=input_path, output_dir=output_dir, variant=variant)
        return {"file_count": 3, "miro_required": False}

    monkeypatch.setattr(runner, "handle_education_offline", fake_offline)
    code = runner.main(
        [
            "education",
            "offline",
            "lesson.json",
            "--variant",
            "student",
            "--output-dir",
            "offline",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "input_path": "lesson.json",
        "output_dir": "offline",
        "variant": "student",
    }
    assert json.loads(capsys.readouterr().out)["miro_required"] is False


def test_runner_dispatches_visual_grammar(monkeypatch, capsys) -> None:
    observed = {}

    def fake_visual(*, output):
        observed["output"] = output
        return {"grammar_version": "schauwerk-visual-grammar.v1", "valid": True}

    monkeypatch.setattr(runner, "handle_visual_grammar", fake_visual)
    code = runner.main(["visual", "grammar", "--output", "grammar.json", "--json"])
    assert code == 0
    assert observed == {"output": "grammar.json"}
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_runner_dispatches_sw009_live_plan(monkeypatch, capsys) -> None:
    observed = {}

    def fake_plan(*, gate_path, bundle_path, authorization_path, output):
        observed.update(
            gate_path=gate_path,
            bundle_path=bundle_path,
            authorization_path=authorization_path,
            output=output,
        )
        return {"ready_for_live_apply": True, "mutation_attempted": False}

    monkeypatch.setattr(runner, "handle_region_sw009_live_plan", fake_plan)
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-plan",
            "gate.json",
            "--bundle",
            "bundle.json",
            "--authorization",
            "authorization.json",
            "--output",
            "plan.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "gate_path": "gate.json",
        "bundle_path": "bundle.json",
        "authorization_path": "authorization.json",
        "output": "plan.json",
    }
    assert json.loads(capsys.readouterr().out)["ready_for_live_apply"] is True


def test_runner_dispatches_sw009_live_apply_and_restore(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply(
        *, gate_path, bundle_path, authorization_path, plan_path, output
    ):
        observed["apply"] = {
            "gate_path": gate_path,
            "bundle_path": bundle_path,
            "authorization_path": authorization_path,
            "plan_path": plan_path,
            "output": output,
        }
        return {"ok": True, "live_apply_attempted": True}

    def fake_restore(*, transaction_receipt, output):
        observed["restore"] = {
            "transaction_receipt": transaction_receipt,
            "output": output,
        }
        return {"ok": True, "live_restore_attempted": True}

    monkeypatch.setattr(runner, "handle_region_sw009_live_apply", fake_apply)
    monkeypatch.setattr(runner, "handle_region_sw009_live_restore", fake_restore)
    apply_code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply",
            "gate.json",
            "--bundle",
            "bundle.json",
            "--authorization",
            "authorization.json",
            "--plan",
            "plan.json",
            "--output",
            "transaction.json",
            "--json",
        ]
    )
    apply_output = json.loads(capsys.readouterr().out)
    restore_code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-restore",
            "transaction.json",
            "--output",
            "restore.json",
            "--json",
        ]
    )
    restore_output = json.loads(capsys.readouterr().out)
    assert apply_code == restore_code == 0
    assert observed["apply"]["output"] == "transaction.json"
    assert observed["restore"] == {
        "transaction_receipt": "transaction.json",
        "output": "restore.json",
    }
    assert apply_output["live_apply_attempted"] is True
    assert restore_output["live_restore_attempted"] is True


def test_runner_dispatches_sw009_kill_switch(monkeypatch, capsys) -> None:
    observed = {}

    def fake_switch(*, action, reason, confirmation):
        observed.update(action=action, reason=reason, confirmation=confirmation)
        return {"enabled": True, "mutation_attempted": True}

    monkeypatch.setattr(runner, "handle_region_sw009_kill_switch", fake_switch)
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-kill-switch",
            "enable",
            "--reason",
            "operator stop",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "action": "enable",
        "reason": "operator stop",
        "confirmation": None,
    }
    assert json.loads(capsys.readouterr().out)["enabled"] is True


def test_runner_dispatches_sw009_bundle_compile(monkeypatch, capsys) -> None:
    observed = {}

    def fake_compile(*, draft_path, output):
        observed.update(draft_path=draft_path, output=output)
        return {
            "schema_version": "typed-region-live-operation-bundle-compile-receipt.v1",
            "ok": True,
            "mutation_attempted": False,
        }

    monkeypatch.setattr(runner, "handle_region_sw009_live_bundle_compile", fake_compile)
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-bundle-compile",
            "draft.json",
            "--output",
            "bundle.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {"draft_path": "draft.json", "output": "bundle.json"}
    assert json.loads(capsys.readouterr().out)["ok"] is True

def test_runner_dispatches_visual_system_v2(monkeypatch, capsys) -> None:
    observed = {}

    def fake_system(*, output):
        observed["output"] = output
        return {"schema_version": "schauwerk-visual-system.v2", "manifest_digest": "a" * 64}

    monkeypatch.setattr(runner, "handle_visual_system_v2", fake_system)
    code = runner.main(["visual", "system-v2", "--output", "system.json", "--json"])
    assert code == 0
    assert observed == {"output": "system.json"}
    assert json.loads(capsys.readouterr().out)["schema_version"] == "schauwerk-visual-system.v2"


def test_runner_dispatches_visual_reference_v2(monkeypatch, capsys) -> None:
    observed = {}

    def fake_reference(**kwargs):
        observed.update(kwargs)
        return {"schema_version": "schauwerk-visual-reference-compile.v2", "frame_count": 7}

    monkeypatch.setattr(runner, "handle_visual_reference_v2", fake_reference)
    code = runner.main(
        [
            "visual",
            "reference-v2",
            "--spec-output",
            "spec.json",
            "--dsl-output",
            "board.dsl",
            "--quality-output",
            "quality.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "spec_output": "spec.json",
        "dsl_output": "board.dsl",
        "quality_output": "quality.json",
    }
    assert json.loads(capsys.readouterr().out)["frame_count"] == 7


def test_runner_dispatches_visual_v2_live_test(monkeypatch, capsys) -> None:
    observed = {}

    def fake_live(**kwargs):
        observed.update(kwargs)
        return {"schema_version": "schauwerk-visual-system-live-test.v2", "alias": kwargs["alias"]}

    monkeypatch.setattr(runner, "handle_visual_v2_live_test", fake_live)
    code = runner.main(
        [
            "miro",
            "visual-v2-live-test",
            "--alias",
            "visual-v2-a",
            "--board-name",
            "Visual v2 A",
            "--output-dir",
            "/tmp/visual-v2-a",
            "--spec-input",
            "software-board.json",
            "--no-comments",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "alias": "visual-v2-a",
        "board_name": "Visual v2 A",
        "output_dir": "/tmp/visual-v2-a",
        "spec_input": "software-board.json",
        "replace_alias": False,
        "reuse_existing_alias": False,
        "resume_after_layout": False,
        "item_limit": 200,
        "comment_limit": 50,
        "max_pages": 20,
        "include_comments": False,
    }
    assert json.loads(capsys.readouterr().out)["alias"] == "visual-v2-a"


def test_runner_dispatches_visual_review_v2(monkeypatch, capsys) -> None:
    observed = {}

    def fake_review(**kwargs):
        observed.update(kwargs)
        return {
            "schema_version": "schauwerk-visual-review-write-receipt.v2",
            "verdict": "PASS",
        }

    monkeypatch.setattr(runner, "handle_visual_review_v2", fake_review)
    code = runner.main(
        [
            "visual",
            "review-v2",
            "live.json",
            "review-input.json",
            "--output",
            "review.json",
            "--json",
        ]
    )
    assert code == 0
    assert observed == {
        "live_receipt": "live.json",
        "review_input": "review-input.json",
        "output": "review.json",
    }
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
