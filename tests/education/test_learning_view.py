from __future__ import annotations

import pytest

from schauwerk.education.view import (
    learning_render_receipt,
    parse_learning_view,
    render_learning_dsl,
)


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

    assert 'root FRAME x=0 y=0 w=2600 h=1300 "Schauwerk Learning View"' in rendered
    assert "question SHAPE parent=root" in rendered
    assert "concepts FRAME" in rendered
    assert "overview_doc DOC parent=concepts" in rendered
    assert "goals_table TABLE parent=concepts" in rendered
    assert "terms_table TABLE parent=concepts" in rendered
    assert "step1 STICKY parent=flow" in rendered
    assert "e3 CONNECTOR from=step2 to=check" in rendered
    assert "personenbezogenen Daten" in rendered


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
