from __future__ import annotations

import json

from schauwerk import runner


def test_runner_dispatches_read_only_inspection(monkeypatch, capsys) -> None:
    observed = {}

    def fake_inspect(*, query, owned_by_me, max_pages):
        observed.update(query=query, owned=owned_by_me, pages=max_pages)
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
    assert observed == {"query": "grabowski", "owned": True, "pages": 3}
    assert json.loads(capsys.readouterr().out) == {
        "read_only": True,
        "boards": {"returned_count": 0},
    }
