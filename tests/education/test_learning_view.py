from __future__ import annotations

import pytest

from schauwerk.education.view import parse_learning_view, render_learning_dsl


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


def test_learning_view_renders_current_miro_dsl() -> None:
    view = parse_learning_view(sample())
    dsl = render_learning_dsl(view)

    assert 'root FRAME x=0 y=0 w=2000 h=1300 "Schauwerk Learning View"' in dsl
    assert "question SHAPE parent=root" in dsl
    assert "step1 STICKY parent=flow" in dsl
    assert "e3 CONNECTOR from=step2 to=check" in dsl
    assert "personenbezogenen Daten" in dsl


def test_learning_view_rejects_missing_required_fields() -> None:
    data = sample()
    del data["goals"]
    with pytest.raises(ValueError, match="goals"):
        parse_learning_view(data)


def test_learning_view_escapes_quotes() -> None:
    data = sample()
    data["topic"] = 'Licht "und" Energie'
    dsl = render_learning_dsl(parse_learning_view(data))
    assert "&quot;und&quot;" in dsl


def test_learning_view_can_parse_learn_wrapper() -> None:
    view = parse_learning_view({"learn": sample()})
    assert view.topic == "Photosynthese"
    assert len(view.steps) == 2
