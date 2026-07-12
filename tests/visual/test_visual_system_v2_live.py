from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from schauwerk.cli_handlers import handle_visual_v2_live_test
from schauwerk.surfaces.miro.live_test_index import read_live_test_records


class Receipt:
    def __init__(self, value: dict) -> None:
        self.value = value

    def to_dict(self) -> dict:
        return dict(self.value)


class FakeClient:
    def __init__(self, snapshots_root: Path) -> None:
        self.settings = SimpleNamespace(snapshots_root=snapshots_root)
        self.calls: list[tuple[str, dict]] = []

    async def board_create(self, **kwargs):
        self.calls.append(("board_create", kwargs))
        return Receipt({"alias": kwargs["alias"], "reference_digest": "board-digest"})

    async def snapshot(self, **kwargs):
        self.calls.append(("snapshot", kwargs))
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "board_alias": kwargs["alias"],
                    "items": (
                        []
                        if len([call for call in self.calls if call[0] == "snapshot"]) == 1
                        else [
                            *({"type": "frame"} for _ in range(7)),
                            *({"type": "doc_format"} for _ in range(1)),
                            *({"type": "data_table_format"} for _ in range(3)),
                            *({"type": "shape"} for _ in range(13)),
                            *({"type": "text"} for _ in range(14)),
                        ]
                    ),
                    "comments": [],
                    "repeatability_verified": True,
                    "verified_reads": 2,
                    "sanitized_references": True,
                }
            ),
            encoding="utf-8",
        )
        snapshots = [call for call in self.calls if call[0] == "snapshot"]
        return Receipt(
            {
                "board_alias": kwargs["alias"],
                "output_path": str(output_path),
                "repeatability_verified": True,
                "item_count": 0 if len(snapshots) == 1 else 31,
            }
        )

    async def layout_create(self, **kwargs):
        self.calls.append(("layout_create", kwargs))
        assert "STICKY" not in kwargs["dsl"]
        return Receipt({"board_alias": kwargs["alias"], "success": True, "created_count": 38})

    async def layout_read_summary(self, **kwargs):
        self.calls.append(("layout_read_summary", kwargs))
        return Receipt(
            {
                "frame_count": 7,
                "connector_count": 7,
                "doc_count": 1,
                "table_count": 3,
                "success": True,
            }
        )


def test_visual_v2_live_test_binds_local_quality_and_remote_conformance(tmp_path: Path) -> None:
    client = FakeClient(tmp_path / "snapshots")
    output = tmp_path / "out"

    result = handle_visual_v2_live_test(
        alias="visual-v2-fixture",
        board_name="Visual v2 fixture",
        output_dir=str(output),
        replace_alias=False,
        reuse_existing_alias=False,
        resume_after_layout=False,
        item_limit=100,
        comment_limit=10,
        max_pages=5,
        include_comments=False,
        client=client,
    )

    assert result["schema_version"] == "schauwerk-visual-system-live-test.v2"
    assert result["local_quality"]["score"] == 100
    assert result["local_quality"]["blockers"] == []
    assert result["remote_conformance"]["ok"] is True
    assert result["remote_conformance"]["geometry_used_for_aesthetic_score"] is False
    assert result["existing_board_mutation_attempted"] is False
    assert result["partial_live_run_recovered"] is False
    assert result["resumed_after_layout"] is False
    assert result["remote_conformance"]["observed"]["remote_item_count"] == 38
    assert result["visual_review"]["automatic_score_prohibited"] is True
    assert [name for name, _ in client.calls] == [
        "board_create",
        "snapshot",
        "layout_create",
        "snapshot",
        "layout_read_summary",
    ]
    assert client.calls[0][1]["replace_alias"] is False
    assert client.calls[1][1]["include_comments"] is False
    assert (output / "visual-system.json").stat().st_mode & 0o077 == 0
    assert (output / "board-spec.json").exists()
    assert (output / "board.dsl").exists()
    assert (output / "quality-v2.json").exists()
    assert (output / "live-test-receipt.json").exists()
    records = read_live_test_records(client.settings)
    assert [record.alias for record in records] == ["visual-v2-fixture"]
