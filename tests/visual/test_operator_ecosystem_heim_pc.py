from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from schauwerk.visual.preview import analyze_visual_board
from schauwerk.visual.representation import (
    load_representation_input,
    render_miro_board,
    route_representation,
)
from schauwerk.visual.system_v2 import validate_board_spec

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-heim-pc-v1.json"


def test_operator_ecosystem_heim_pc_is_a_complete_clean_visual_model() -> None:
    schema = json.loads((ROOT / "schemas/representation-input.v1.schema.json").read_text())
    raw = json.loads(FIXTURE.read_text())

    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(raw)) == []

    model = load_representation_input(FIXTURE)
    plan = route_representation(model)
    board = render_miro_board(model, plan)
    quality = validate_board_spec(board)
    preview = analyze_visual_board(board, package_digest="0" * 64)

    node_ids = {node["id"] for node in model["nodes"]}
    edge_ids = {edge["id"] for edge in model["edges"]}

    assert {
        "alex",
        "bureau",
        "grabowski",
        "systemkatalog",
        "primary_observation",
        "leitstand",
        "schauwerk",
        "projection_gap",
    } <= node_ids
    assert {"e01", "e03", "e20", "e25", "e31", "e32"} <= edge_ids
    assert plan["primary_format"] == "miro_native"
    assert plan["selected_formats"] == ["miro_native", "mermaid"]
    assert quality["ok"] is True
    assert quality["score"] == 100
    assert quality["provider_auto_sized_count"] == 0
    assert quality["visual_risks"] == []
    assert quality["visual_acceptance"]["authenticated_provider_capture_required"] is True
    assert all(
        item["kind"] not in {"doc", "table"}
        for frame in board["frames"]
        for item in frame["objects"]
    )
    assert preview["ok"] is True
    assert preview["blocker_count"] == 0
    assert preview["warning_count"] == 0
