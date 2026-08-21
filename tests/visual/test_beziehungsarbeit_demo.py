from __future__ import annotations

import json
from pathlib import Path

from schauwerk.surfaces.miro.native_executor import validate_native_bundle
from schauwerk.visual.representation import validate_representation_input

ROOT = Path(__file__).resolve().parents[2]
REPRESENTATION = ROOT / "demos" / "education" / "beziehungsarbeit-representation-v1.json"
MIRO_BUNDLE = ROOT / "demos" / "education" / "beziehungsarbeit-miro-native-v1.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_beziehungsarbeit_representation_contract() -> None:
    representation = validate_representation_input(_load(REPRESENTATION))

    assert representation["intent"] == "knowledge_map"
    assert {group["id"] for group in representation["groups"]} == {
        "grundlage",
        "offenheit_halt",
        "containment",
        "professionalitaet",
        "reflexion",
    }
    assert {node["id"] for node in representation["nodes"]} >= {
        "beziehungsarbeit",
        "halt",
        "lernen",
        "professionelle_beziehung",
        "supervision",
        "qualitaet",
    }


def test_beziehungsarbeit_native_miro_bundle_contract() -> None:
    bundle = validate_native_bundle(_load(MIRO_BUNDLE))

    assert [operation["kind"] for operation in bundle["operations"]] == [
        "diagram",
        "diagram",
        "table",
        "document",
    ]
    assert bundle["operations"][0]["title"] == "Beziehungsarbeit – Wissenskarte"
    assert bundle["operations"][1]["title"] == "Containment – haltende Beziehungsfunktion"
    assert bundle["operations"][2]["table_title"] == (
        "Spannungsfelder professioneller Beziehungsarbeit"
    )
    assert "Wahrheitsgrenze des Schauwerks" in bundle["operations"][3]["content"]


def test_beziehungsarbeit_central_axis_label_fidelity() -> None:
    representation = validate_representation_input(_load(REPRESENTATION))
    central_edges = [
        edge
        for edge in representation["edges"]
        if edge["from"] == "beziehungsarbeit"
        and edge["to"] == "inhalte_aktivitaeten"
    ]
    assert [edge["label"] for edge in central_edges] == ["ist nicht trennbar von"]

    bundle = validate_native_bundle(_load(MIRO_BUNDLE))
    knowledge_map_lines = bundle["operations"][0]["diagram_dsl"].splitlines()
    assert knowledge_map_lines.count("c n1 ist nicht trennbar von n18") == 1
    assert "c n1 untrennbar n18" not in knowledge_map_lines
