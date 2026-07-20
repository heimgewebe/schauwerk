from __future__ import annotations

import pytest

from schauwerk.surfaces.miro.layout_dsl import (
    LayoutDslParseError,
    summarize_layout_dsl,
)


def test_layout_dsl_summary_counts_known_declaration_positions() -> None:
    summary = summarize_layout_dsl(
        "root FRAME x=0 y=0 w=100 h=100\n"
        "a SHAPE x=0 y=0 w=20 h=20 A\n"
        "ab CONNECTOR from=a to=root label=very long connector text\n"
        "doc DOC x=0 y=0 w=20 h=20"
    )

    assert summary.line_count == 4
    assert summary.count("FRAME") == 1
    assert summary.count("SHAPE") == 1
    assert summary.count("CONNECTOR") == 1
    assert summary.count("DOC") == 1


def test_layout_dsl_summary_accepts_empty_and_comment_only_input() -> None:
    assert summarize_layout_dsl("").line_count == 0
    summary = summarize_layout_dsl("  # ab CONNECTOR from=a to=b\n// c CONNECTOR from=b to=c")

    assert summary.line_count == 0
    assert summary.count("CONNECTOR") == 0


def test_layout_dsl_summary_rejects_bare_connector_keyword() -> None:
    with pytest.raises(LayoutDslParseError, match="reference before CONNECTOR"):
        summarize_layout_dsl("CONNECTOR id=ab from=a to=b")


def test_layout_dsl_summary_does_not_match_connector_like_kinds() -> None:
    summary = summarize_layout_dsl("ab CONNECTOR_LABEL from=a to=b")

    assert summary.count("CONNECTOR") == 0
    assert summary.count("CONNECTOR_LABEL") == 1
