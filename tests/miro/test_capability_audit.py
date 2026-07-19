from __future__ import annotations

import copy

import pytest

from schauwerk.surfaces.miro.capability_audit import TOOL_FAMILIES, audit_tool_catalogue


def catalogue(*names: str) -> dict:
    return {
        "protocol_version": "2025-11-25",
        "server_name": "Miro MCP",
        "server_version": "3.2.4",
        "tools": [{"name": name, "input_schema": {"type": "object"}} for name in names],
    }


def test_audit_preserves_extensions_and_marks_real_provider_gaps() -> None:
    report = audit_tool_catalogue(
        catalogue(
            "user_who_am_i",
            "board_list_items",
            "context_explore",
            "context_get",
            "layout_create",
            "layout_read",
            "layout_update",
            "diagram_get_dsl",
            "diagram_create",
            "image_get_upload_url",
            "image_create",
            "provider_future_tool",
        )
    )

    assert report["observed_tool_count"] == 12
    assert report["provider_extensions"] == ["provider_future_tool"]
    assert report["families"]["provider_extension"]["observed_tools"] == ["provider_future_tool"]
    assert report["high_value_lanes"]["native_diagram"]["available"] is True
    assert report["high_value_lanes"]["managed_image_lifecycle"]["available"] is False
    assert report["high_value_lanes"]["managed_image_lifecycle"]["missing_tools"] == [
        "image_get_data",
        "image_get_url",
        "image_delete",
    ]
    assert report["truth_boundary"]["image_delete_available"] is False
    assert report["truth_boundary"]["layout_can_delete_unsupported_images"] is False
    cross_surface = report["cross_surface_lanes"]["managed_image_lifecycle"]
    assert cross_surface["adapter_implemented"] is True
    assert cross_surface["rest_delete_adapter"] == "implemented_fail_closed"
    assert cross_surface["rest_credential_configured"] is False
    assert cross_surface["available"] is False
    assert cross_surface["globally_atomic"] is False
    assert len(report["audit_digest"]) == 64


def test_audit_is_deterministic_and_order_independent() -> None:
    first = catalogue("layout_update", "layout_read", "layout_create")
    second = copy.deepcopy(first)
    second["tools"].reverse()

    assert audit_tool_catalogue(first) == audit_tool_catalogue(second)


def test_audit_rejects_duplicate_or_invalid_tool_records() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        audit_tool_catalogue(catalogue("layout_read", "layout_read"))

    with pytest.raises(ValueError, match="entry 0"):
        audit_tool_catalogue({"tools": [{}]})


def test_live_baseline_reports_complete_native_runtime_coverage() -> None:
    names = sorted(set().union(*TOOL_FAMILIES.values()))
    report = audit_tool_catalogue(catalogue(*names))

    integration = report["adapter_integration"]
    assert report["observed_tool_count"] == 33
    assert integration["runtime_integrated_observed_count"] == 33
    assert integration["runtime_integration_coverage_percent"] == 100.0
    assert integration["unincorporated_observed_tools"] == []
    assert "diagram_create" in integration["runtime_integrated_tools"]
    assert "table_get_latest_update_history" in integration["runtime_integrated_tools"]
    assert "code_widget_update" in integration["runtime_integrated_tools"]
    assert "prototype_create" in integration["runtime_integrated_tools"]


def test_audit_reports_separate_rest_authority_without_changing_mcp_truth() -> None:
    names = sorted(set().union(*TOOL_FAMILIES.values()))
    report = audit_tool_catalogue(
        catalogue(*names),
        rest_status={
            "credential": {"exists": True},
            "live_authorized_known": True,
            "live_authorized": True,
        },
    )

    assert report["observed_tool_count"] == 33
    assert report["high_value_lanes"]["managed_image_lifecycle"]["available"] is False
    cross_surface = report["cross_surface_lanes"]["managed_image_lifecycle"]
    assert cross_surface["available"] is True
    assert cross_surface["mcp_image_delete_available"] is False
    assert cross_surface["rest_credential_configured"] is True
    assert cross_surface["rest_live_authorized"] is True
    assert cross_surface["provider_semantics"] == "create-verify-delete-saga"


def test_missing_creation_tools_resolve_to_explicit_layout_fallbacks() -> None:
    report = audit_tool_catalogue(
        catalogue(
            "user_who_am_i",
            "board_list_items",
            "context_explore",
            "layout_get_dsl",
            "layout_create",
            "layout_read",
        )
    )
    living = report["high_value_lanes"]["living_document"]
    assert living["available"] is False
    assert living["effective_available"] is False
    assert living["creation_fallback_available"] is True
    assert living["mode"] == "fallback_with_gaps"
    assert living["fallback"] == "layout_document"
    assert living["fallback_covered_missing_tools"] == ["doc_create", "doc_get"]
    assert living["uncovered_missing_tools"] == ["doc_update"]
    table = report["high_value_lanes"]["structured_data_views"]
    assert table["fallback"] == "layout_grid"
    assert "table_get_latest_update_history" in table["uncovered_missing_tools"]
    prototype = report["high_value_lanes"]["interactive_prototype"]
    assert prototype["effective_available"] is True
    assert prototype["mode"] == "fallback"
    assert report["provider_fallbacks"]["layout_tools_available"] is True
    assert report["provider_fallbacks"]["maintenance_operations_fail_closed"] is True
    assert "living_document" in report["unavailable_lanes"]
    assert "interactive_prototype" not in report["unavailable_lanes"]


def test_fallbacks_remain_blocked_without_layout_toolset() -> None:
    report = audit_tool_catalogue(
        catalogue("user_who_am_i", "board_list_items", "context_explore")
    )
    assert report["high_value_lanes"]["living_document"]["mode"] == "blocked"
    assert report["high_value_lanes"]["living_document"]["effective_available"] is False
    assert "living_document" in report["unavailable_lanes"]
