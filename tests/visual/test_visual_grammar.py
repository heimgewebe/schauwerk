from __future__ import annotations

import pytest

from schauwerk.visual import miro_dsl as dsl
from schauwerk.visual.grammar import learning_template, primitive_by_name, primitive_names


def test_miro_visual_grammar_v1_catalog_is_complete() -> None:
    assert primitive_names() == (
        "frame",
        "banner_shape",
        "text",
        "sticky",
        "connector",
        "doc",
        "table",
        "card",
        "code_widget",
        "image",
        "comment",
        "diagram",
        "prototype",
    )


def test_learning_template_prefers_rich_layout_primitives() -> None:
    template = learning_template()

    assert template.name == "learning-view-v1-rich"
    assert "doc" in template.primitives
    assert "table" in template.primitives
    assert "sticky" in template.primitives
    assert "longer explanation uses doc, not sticky notes" in template.invariants


def test_primitive_lookup_fails_closed() -> None:
    assert primitive_by_name("table").density == "high"
    with pytest.raises(KeyError):
        primitive_by_name("unknown")


def test_miro_dsl_helpers_emit_deterministic_lines_and_blocks() -> None:
    text = dsl.line("heading", "TEXT", x=1, y=2, content='A "quote"')
    document = dsl.doc("guide", parent="root", x=10, y=20, markdown="# Guide")
    rendered_table = dsl.table(
        "rubric",
        parent="root",
        x=30,
        y=40,
        title="Rubric",
        columns=("A", "B"),
        rows=(("x|y", "z"),),
    )

    assert text == 'heading TEXT x=1 y=2 "A &quot;quote&quot;"'
    assert document == "guide DOC parent=root x=10 y=20 <<<\n# Guide\n>>>"
    assert 'rubric TABLE parent=root x=30 y=40 "Rubric"' in rendered_table
    assert "A:text | B:text\n---\nx/y | z" in rendered_table
    assert dsl.bullets(("one", "two")) == "- one\n- two"


def test_miro_dsl_table_preserves_explicit_column_types() -> None:
    rendered_table = dsl.table(
        "rubric",
        parent="root",
        x=30,
        y=40,
        title="Rubric",
        columns=("Status:select(Done#00FF00, Blocked#FF0000)", "Updated:latest_update"),
        rows=(("Done", "today"),),
    )

    assert "Status:select(Done#00FF00, Blocked#FF0000) | Updated:latest_update" in rendered_table
