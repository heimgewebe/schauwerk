from __future__ import annotations

import pytest

from schauwerk.visual.composer_v2 import bounded_rows, clip_text, frame, table_object


def test_bounded_rows_exposes_omitted_items() -> None:
    values = [{"title": f"Item {index}", "status": "active"} for index in range(6)]

    rows = bounded_rows(values, ("title", "status"), maximum_rows=2)

    assert rows == (
        ("Item 0", "active"),
        ("Item 1", "active"),
        ("+ 4 weitere im Snapshot", "—"),
    )


def test_bounded_rows_rejects_invalid_contract() -> None:
    with pytest.raises(ValueError, match="fields must not be empty"):
        bounded_rows([], ())
    with pytest.raises(ValueError, match="maximum_rows must be positive"):
        bounded_rows([{"title": "Item"}], ("title",), maximum_rows=0)


def test_table_object_rejects_row_width_drift() -> None:
    with pytest.raises(ValueError, match="rows must match"):
        table_object(
            "table",
            "comparison",
            80,
            300,
            620,
            220,
            "Comparison",
            ("Name", "Status"),
            (("Only one cell",),),
        )


def test_frame_provides_one_title_and_thesis() -> None:
    value = frame("chapter", 2, "map", "Title", "Thesis", 1300)

    assert value["id"] == "chapter"
    assert value["number"] == 2
    assert [item["role"] for item in value["objects"]] == ["title", "thesis"]
    assert value["w"] == 1120
    assert value["h"] == 630


def test_clip_text_rejects_impossible_limit() -> None:
    with pytest.raises(ValueError, match="at least two"):
        clip_text("content", 1)
