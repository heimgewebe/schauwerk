from __future__ import annotations

import re

from schauwerk.education.view import parse_learning_view
from schauwerk.education.zoomlandkarte import render_learning_zoomlandkarte_dsl


def sample() -> dict:
    return {
        "topic": "Photosynthese",
        "audience": "Lerngruppe",
        "guiding_question": "Wie wird aus Licht Energie?",
        "goals": ["Stoffe benennen", "Ablauf erklaeren"],
        "key_terms": ["Chlorophyll", "Glucose"],
        "materials": ["Tafelbild", "Pflanzenskizze"],
        "steps": [
            {"title": "Vorwissen", "activity": "Begriffe sammeln", "minutes": 5},
            {"title": "Erklaeren", "activity": "Pfeile setzen", "output": "Mini-Schaubild"},
        ],
    }


def _line_for(rendered: str, identifier: str) -> str:
    return next(line for line in rendered.splitlines() if line.startswith(identifier + " "))


def _number(rendered: str, identifier: str, attr: str) -> int:
    match = re.search(rf"\b{attr}=(-?\d+)\b", _line_for(rendered, identifier))
    assert match is not None
    return int(match.group(1))


def test_zoomlandkarte_has_macro_canvas_and_named_cluster_frames() -> None:
    rendered = render_learning_zoomlandkarte_dsl(parse_learning_view(sample()))

    assert _number(rendered, "zoom_root", "w") >= 17000
    assert _number(rendered, "zoom_root", "h") >= 11000
    assert "macro_overview FRAME" in rendered
    assert "production_lane FRAME" in rendered
    assert "risk_legend FRAME" in rendered
    assert "cluster_goals FRAME" in rendered
    assert "cluster_terms FRAME" in rendered
    assert "cluster_path FRAME" in rendered
    assert "cluster_transfer FRAME" in rendered
    assert "cluster_risks FRAME" in rendered
    assert "cluster_sources FRAME" in rendered


def test_zoomlandkarte_uses_zoom_in_detail_primitives() -> None:
    rendered = render_learning_zoomlandkarte_dsl(parse_learning_view(sample()))

    assert "goals_doc DOC parent=cluster_goals" in rendered
    assert "terms_zoom_table TABLE parent=cluster_terms" in rendered
    assert "path_zoom_table TABLE parent=cluster_path" in rendered
    assert "sources_doc DOC parent=cluster_sources" in rendered
    assert "zoom_edge_6 CONNECTOR" in rendered
    assert "zoom_privacy_footer SHAPE parent=zoom_root" in rendered


def test_zoomlandkarte_detail_items_are_small_relative_to_cluster() -> None:
    rendered = render_learning_zoomlandkarte_dsl(parse_learning_view(sample()))

    assert _number(rendered, "cluster_goals", "w") == 3800
    assert _number(rendered, "cluster_goals", "h") == 3000
    assert _number(rendered, "goals_zoom_table", "x") == 1900
    assert _number(rendered, "terms_relation", "w") < _number(rendered, "cluster_terms", "w")
