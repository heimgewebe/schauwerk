from __future__ import annotations

import json
from pathlib import Path

from schauwerk.surfaces.miro.execution_plan import compile_miro_execution_plan
from schauwerk.visual.representation import load_representation_input, route_representation

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-representation-v1.json"


def operations(plan: dict) -> dict[str, dict]:
    return {item["operation_id"]: item for item in plan["operations"]}


def test_mixed_model_uses_complementary_native_miro_lanes() -> None:
    model = load_representation_input(FIXTURE)
    route = route_representation(model)
    plan = compile_miro_execution_plan(model, route)
    selected = operations(plan)

    assert plan["schema_version"] == "schauwerk-miro-execution-plan.v1"
    assert selected["discover_context"]["tool"] == "context_explore"
    assert selected["create_native_diagram"]["parameters"] == {"diagram_type": "flowchart"}
    assert selected["create_living_document"]["tool"] == "doc_create"
    assert selected["select_data_view"]["parameters"]["layout"] == "table"
    assert selected["create_mermaid_source_widget"]["parameters"]["language"] == "Mermaid"
    assert selected["create_interactive_prototype"]["parameters"] == {
        "device_type": "tablet",
        "orientation": "landscape",
    }
    assert selected["open_review_comment"]["tool"] == "comment_create"
    assert plan["provider_gap_contract"] == {
        "managed_image_delete_required_for_atomic_image_replace": True,
        "layout_update_may_not_delete_unsupported_image_items": True,
    }
    assert len(plan["execution_plan_digest"]) == 64
    from schauwerk.surfaces.miro.capability_audit import TOOL_FAMILIES

    live_baseline = set().union(*TOOL_FAMILIES.values()) - {"image_delete"}
    assert set(plan["all_tools"]) == live_baseline


def test_timeline_selects_native_timeline_with_dependencies() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["intent"] = "timeline"
    raw["requested_formats"] = ["miro_native", "table"]
    raw["requirements"] = {
        "formal_relations": True,
        "structured_comparison": True,
        "collaboration": False,
    }
    from schauwerk.visual.representation import validate_representation_input

    model = validate_representation_input(raw)
    plan = compile_miro_execution_plan(model, route_representation(model))
    view = operations(plan)["select_data_view"]

    assert view["parameters"] == {
        "layout": "timeline",
        "timeline_date_unit": "month",
        "timeline_dependencies_enabled": True,
        "timeline_nesting_enabled": True,
    }


def test_execution_plan_is_deterministic() -> None:
    model = load_representation_input(FIXTURE)
    route = route_representation(model)

    assert compile_miro_execution_plan(model, route) == compile_miro_execution_plan(model, route)
