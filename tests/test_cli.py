from __future__ import annotations

import json

from schauwerk import runner


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
