from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from schauwerk.cli_handlers import handle_learn_live_test
from schauwerk.surfaces.miro.live_test_index import read_live_test_records


class Receipt:
    def __init__(self, value: dict) -> None:
        self.value = value

    def to_dict(self) -> dict:
        return dict(self.value)


class FakeClient:
    def __init__(self, snapshots_root: Path) -> None:
        self.settings = SimpleNamespace(snapshots_root=snapshots_root)
        self.calls = []

    async def board_create(self, **kwargs):
        self.calls.append(("board_create", kwargs))
        return Receipt({"alias": kwargs["alias"], "reference_digest": "board-digest"})

    async def snapshot(self, **kwargs):
        self.calls.append(("snapshot", kwargs))
        return Receipt(
            {
                "board_alias": kwargs["alias"],
                "output_path": str(kwargs["output_path"]),
                "repeatability_verified": True,
                "item_count": 0 if len([c for c in self.calls if c[0] == "snapshot"]) == 1 else 20,
            }
        )

    async def layout_create(self, **kwargs):
        self.calls.append(("layout_create", kwargs))
        return Receipt(
            {"board_alias": kwargs["alias"], "success": True, "created_count": 25}
        )

    async def layout_read_summary(self, **kwargs):
        self.calls.append(("layout_read_summary", kwargs))
        return Receipt(
            {"line_count": 10, "connector_count": 5, "success": True}
        )


def test_learning_live_test_runs_fresh_board_cycle(tmp_path) -> None:
    source = tmp_path / "lesson.yml"
    source.write_text(
        """
learn:
  topic: Photosynthese
  audience: Lerngruppe
  guiding_question: Wie wird aus Licht Energie?
  goals:
    - Stoffe benennen
  steps:
    - title: Start
      activity: Sammeln
""".strip(),
        encoding="utf-8",
    )
    client = FakeClient(tmp_path / "snapshots")

    result = handle_learn_live_test(
        input_path=str(source),
        alias="live-fixture",
        board_name="Live Fixture",
        output_dir=str(tmp_path / "out"),
        replace_alias=True,
        item_limit=100,
        comment_limit=10,
        max_pages=5,
        include_comments=False,
        client=client,
    )

    assert result["alias"] == "live-fixture"
    assert result["board"]["reference_digest"] == "board-digest"
    assert result["before"]["repeatability_verified"] is True
    assert result["layout"]["created_count"] == 25
    assert result["after"]["item_count"] == 20
    assert result["layout_read"]["connector_count"] == 5
    assert result["output_dir"] == str(tmp_path / "out")
    assert [name for name, _ in client.calls] == [
        "board_create",
        "snapshot",
        "layout_create",
        "snapshot",
        "layout_read_summary",
    ]
    assert client.calls[0][1]["replace_alias"] is True
    assert client.calls[1][1]["include_comments"] is False
    assert result["live_test_record"]["alias"] == "live-fixture"
    assert result["live_test_record"]["reference_digest"] == "board-digest"
    assert result["remote_cleanup_supported"] is False
    assert result["remote_cleanup_attempted"] is False
    assert [record.alias for record in read_live_test_records(client.settings)] == ["live-fixture"]
