from __future__ import annotations

import copy

import pytest

from schauwerk.surfaces.miro.capability_audit import audit_tool_catalogue


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
