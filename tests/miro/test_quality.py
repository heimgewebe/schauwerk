from __future__ import annotations

import json
import os

from schauwerk.surfaces.miro.quality import (
    inspect_snapshot_quality,
    write_quality_receipt_from_snapshot_file,
)


def item(
    kind: str,
    *,
    ref: str,
    x: int,
    y: int,
    w: int,
    h: int,
    parent: str | None = None,
    content: str = "stable",
) -> dict:
    value = {
        "ref": ref,
        "type": kind,
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
        "data": {"content": content},
    }
    if parent is not None:
        value["parent"] = {"id": parent}
    return value


def snapshot(items: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "board_alias": "fixture",
        "items": items,
        "comments": [],
        "content_digest": "digest",
        "repeatability_verified": True,
        "verified_reads": 2,
        "sanitized_references": True,
    }


def finding_codes(receipt) -> set[str]:
    return {finding.code for finding in receipt.findings}


def test_quality_detects_major_overlap_without_echoing_content() -> None:
    sensitive_text = "classroom note that should stay in the snapshot only"
    receipt = inspect_snapshot_quality(
        snapshot(
            [
                item(
                    "text", ref="a", x=0, y=0, w=100, h=100, parent="frame", content=sensitive_text
                ),
                item("text", ref="b", x=20, y=20, w=100, h=100, parent="frame"),
            ]
        )
    )
    encoded = json.dumps(receipt.to_dict(), sort_keys=True)

    assert receipt.ok is False
    assert receipt.overlap_pair_count == 1
    assert "visual_overlap" in finding_codes(receipt)
    assert sensitive_text not in encoded


def test_quality_fails_declared_connector_doc_table_expectations() -> None:
    receipt = inspect_snapshot_quality(
        snapshot(
            [
                item("frame", ref="root", x=0, y=0, w=1000, h=800),
                item("text", ref="title", x=0, y=-300, w=600, h=80, parent="root"),
            ]
        ),
        expected_min_connectors=1,
        expected_min_docs=1,
        expected_min_tables=1,
    )

    assert receipt.ok is False
    assert {
        "connector_observability_unavailable",
        "doc_count_below_expectation",
        "table_count_below_expectation",
    }.issubset(finding_codes(receipt))
    assert receipt.connector_count is None
    assert receipt.connector_observability == "unavailable"


def test_quality_accepts_structured_learning_like_snapshot() -> None:
    receipt = inspect_snapshot_quality(
        snapshot(
            [
                item("frame", ref="root", x=0, y=0, w=3400, h=2200),
                item("frame", ref="flow", x=-400, y=250, w=620, h=1500),
                item("text", ref="title", x=0, y=-950, w=2200, h=90, parent="root"),
                item("sticky_note", ref="step1", x=-400, y=100, w=230, h=180, parent="flow"),
                item("sticky_note", ref="step2", x=-400, y=360, w=230, h=180, parent="flow"),
                {"ref": "edge", "type": "connector", "data": {"content": "weiter"}},
                item("doc_format", ref="doc", x=1200, y=100, w=600, h=250, parent="root"),
                item("data_table_format", ref="table1", x=1200, y=470, w=640, h=260, parent="root"),
                item("data_table_format", ref="table2", x=1200, y=820, w=640, h=260, parent="root"),
            ]
        ),
        expected_min_connectors=1,
        expected_min_docs=1,
        expected_min_tables=2,
    )

    assert receipt.ok is True
    assert receipt.score == 100
    assert receipt.connector_count == 1
    assert receipt.connector_observability == "snapshot"
    assert receipt.doc_count == 1
    assert receipt.table_count == 2
    assert receipt.findings == ()


def test_quality_can_use_layout_read_counts_as_rich_item_evidence() -> None:
    receipt = inspect_snapshot_quality(
        snapshot(
            [
                item("frame", ref="root", x=0, y=0, w=1200, h=900),
                item("text", ref="title", x=0, y=-300, w=900, h=80, parent="root"),
            ]
        ),
        expected_min_connectors=2,
        expected_min_docs=1,
        expected_min_tables=2,
        layout_read={"connector_count": 2, "doc_count": 1, "table_count": 2},
    )

    assert receipt.ok is True
    assert receipt.connector_count == 2
    assert receipt.connector_observability == "layout_read"
    assert receipt.doc_count == 1
    assert receipt.table_count == 2


def test_quality_reports_malformed_layout_connector_count_as_unavailable() -> None:
    receipt = inspect_snapshot_quality(
        snapshot([item("frame", ref="root", x=0, y=0, w=1000, h=800)]),
        layout_read={"connector_count": "2"},
    )

    assert receipt.ok is True
    assert receipt.connector_count is None
    assert receipt.connector_observability == "unavailable"
    assert "connector_observability_unavailable" in finding_codes(receipt)


def test_quality_accepts_explicit_zero_from_layout_read() -> None:
    receipt = inspect_snapshot_quality(
        snapshot([item("frame", ref="root", x=0, y=0, w=1000, h=800)]),
        layout_read={"connector_count": 0},
    )

    assert receipt.ok is True
    assert receipt.connector_count == 0
    assert receipt.connector_observability == "layout_read"
    assert "connector_observability_unavailable" not in finding_codes(receipt)


def test_quality_receipt_write_is_owner_only(tmp_path) -> None:
    snapshot_path = tmp_path / "after.json"
    snapshot_path.write_text(
        json.dumps(
            snapshot(
                [
                    item("frame", ref="root", x=0, y=0, w=1000, h=800),
                    item("doc_format", ref="doc", x=0, y=0, w=500, h=260, parent="root"),
                ]
            )
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "quality.json"

    receipt = write_quality_receipt_from_snapshot_file(
        snapshot_path=snapshot_path,
        destination=destination,
        expected_min_docs=1,
    )

    written = json.loads(destination.read_text(encoding="utf-8"))
    assert receipt.output_path == str(destination)
    assert written["mutation_attempted"] is False
    assert written["sanitized_references"] is True
    assert destination.stat().st_mode & 0o077 == 0
    os.chmod(destination, 0o600)


def test_quality_understands_native_diagrams_and_provider_opaque_geometry() -> None:
    items = [
        item("frame", ref="stage", x=0, y=0, w=4000, h=2400),
        item("diagram", ref="diagram", x=-800, y=-300, w=1200, h=700),
        item("code", ref="code", x=800, y=500, w=1000, h=600),
        {
            "ref": "doc",
            "type": "doc_format",
            "position": {"x": 800, "y": -300},
            "data": {"content": "living document"},
        },
        {
            "ref": "table",
            "type": "data_table_format",
            "position": {"x": -800, "y": 500},
            "data": {"content": "structured data"},
        },
    ]
    for index in range(4):
        items.append(
            {
                "ref": f"text-{index}",
                "type": "text",
                "position": {"x": index * 100, "y": -900},
                "parent": {"id": "stage"},
                "data": {"content": "orientation"},
            }
        )

    receipt = inspect_snapshot_quality(
        snapshot(items),
        expected_min_docs=1,
        expected_min_tables=1,
    )

    assert receipt.ok is True
    assert receipt.score == 100
    assert receipt.native_diagram_count == 1
    assert receipt.geometry_eligible_item_count == 3
    assert receipt.geometry_coverage_percent == 100
    assert "geometry_coverage_low" not in finding_codes(receipt)
    assert "no_connectors_on_dense_board" not in finding_codes(receipt)
