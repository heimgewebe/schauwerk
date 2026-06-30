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

    def fake_render(*, input_path, output):
        observed.update(input_path=input_path, output=output)
        return {"topic": "fixture", "dsl_line_count": 3}

    monkeypatch.setattr(runner, "handle_learn_render", fake_render)
    code = runner.main(["miro", "learn", "render", "topic.yml", "--output", "out.dsl", "--json"])

    assert code == 0
    assert observed == {"input_path": "topic.yml", "output": "out.dsl"}
    assert json.loads(capsys.readouterr().out)["dsl_line_count"] == 3


def test_runner_dispatches_learning_apply(monkeypatch, capsys) -> None:
    observed = {}

    def fake_apply(*, input_path, alias):
        observed.update(input_path=input_path, alias=alias)
        return {
            "topic": "fixture",
            "layout": {"board_alias": alias, "success": True, "created_count": 3},
        }

    monkeypatch.setattr(runner, "handle_learn_apply", fake_apply)
    code = runner.main(["miro", "learn", "apply", "board-a", "topic.yml", "--json"])

    assert code == 0
    assert observed == {"input_path": "topic.yml", "alias": "board-a"}
    result = json.loads(capsys.readouterr().out)
    assert result["layout"]["board_alias"] == "board-a"
    assert result["layout"]["success"] is True
