from __future__ import annotations

import re

import pytest

from schauwerk.education.view import (
    learning_render_receipt,
    parse_learning_view,
    render_learning_dsl,
)


def _line_for(rendered: str, identifier: str) -> str:
    return next(line for line in rendered.splitlines() if line.startswith(identifier + " "))


def _number(rendered: str, identifier: str, attr: str) -> int:
    match = re.search(rf"\b{attr}=(-?\d+)\b", _line_for(rendered, identifier))
    assert match is not None
    return int(match.group(1))


def sample() -> dict:
    return {
        "topic": "Photosynthese",
        "audience": "Lerngruppe",
        "guiding_question": "Wie wird aus Licht Energie?",
        "goals": ["Stoffe benennen", "Ablauf erklaeren"],
        "key_terms": ["Chlorophyll", "Glucose"],
        "steps": [
            {"title": "Vorwissen", "activity": "Begriffe sammeln", "minutes": 5},
            {
                "title": "Erklaeren",
                "activity": "Ablauf mit Pfeilen darstellen",
                "output": "Mini-Schaubild",
            },
        ],
    }


def test_learning_view_renders_visual_grammar_v1_miro_dsl() -> None:
    view = parse_learning_view(sample())
    rendered = render_learning_dsl(view)

    assert 'root FRAME x=0 y=0 w=3400 h=2200 "Schauwerk Learning View"' in rendered
    assert "question SHAPE parent=root" in rendered
    assert "concepts FRAME" in rendered
    assert "overview_doc DOC parent=concepts" in rendered
    assert "goals_table TABLE parent=concepts" in rendered
    assert "terms_table TABLE parent=concepts" in rendered
    assert "step1 STICKY parent=flow" in rendered
    assert "e_step_1 CONNECTOR from=step1 to=step2" in rendered
    assert "e3 CONNECTOR from=step2 to=check" in rendered
    assert "personenbezogenen Daten" in rendered


def test_learning_view_v1_1_centres_banners_and_expands_columns() -> None:
    rendered = render_learning_dsl(parse_learning_view(sample()))

    assert _number(rendered, "root", "w") == 3400
    assert _number(rendered, "root", "h") == 2200
    assert _number(rendered, "title", "x") == 1700
    assert _number(rendered, "question", "x") == 1700
    assert _number(rendered, "privacy", "x") == 1700
    assert _number(rendered, "privacy", "y") == 2050
    assert _number(rendered, "concepts", "w") == 760


def test_learning_view_v1_1_keeps_dense_doc_and_tables_apart() -> None:
    rendered = render_learning_dsl(parse_learning_view(sample()))

    assert _number(rendered, "overview_doc", "x") == 380
    assert _number(rendered, "goals_table", "x") == 380
    assert _number(rendered, "terms_table", "x") == 380
    assert _number(rendered, "goals_table", "y") - _number(rendered, "overview_doc", "y") >= 350
    assert _number(rendered, "terms_table", "y") - _number(rendered, "goals_table", "y") >= 350


def test_learning_view_v1_1_spaces_six_learning_steps_without_overlap() -> None:
    data = sample()
    data["steps"] = [
        {"title": f"Schritt {index}", "activity": "arbeiten", "minutes": 5}
        for index in range(1, 7)
    ]
    rendered = render_learning_dsl(parse_learning_view(data))

    step_y_values = [_number(rendered, f"step{index}", "y") for index in range(1, 7)]
    assert all(
        (next_y - current_y) >= 250
        for current_y, next_y in zip(step_y_values, step_y_values[1:])
    )
    assert _number(rendered, "step6", "y") < _number(rendered, "flow", "h")
    assert "e_step_5 CONNECTOR from=step5 to=step6" in rendered
    assert "e3 CONNECTOR from=step6 to=check" in rendered


def test_learning_view_rejects_missing_required_fields() -> None:
    data = sample()
    del data["goals"]
    with pytest.raises(ValueError, match="goals"):
        parse_learning_view(data)


def test_learning_view_escapes_quotes() -> None:
    data = sample()
    data["topic"] = 'Licht "und" Energie'
    rendered = render_learning_dsl(parse_learning_view(data))
    assert "&quot;und&quot;" in rendered


def test_learning_view_can_parse_learn_wrapper() -> None:
    view = parse_learning_view({"learn": sample()})
    assert view.topic == "Photosynthese"
    assert len(view.steps) == 2


def test_learning_render_receipt_reports_visual_template() -> None:
    view = parse_learning_view(sample())
    rendered = render_learning_dsl(view)
    receipt = learning_render_receipt(view, rendered, output_path=None)

    assert receipt["template"] == "learning-view-v1-rich"
    assert receipt["used_primitives"] == [
        "frame",
        "banner_shape",
        "text",
        "table",
        "doc",
        "sticky",
        "connector",
    ]
    assert receipt["privacy_note_present"] is True
