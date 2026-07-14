"""Drift-aware audit of the live Miro MCP tool catalogue."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

AUDIT_SCHEMA = "schauwerk-miro-capability-audit.v1"

# Families describe product roles, not a frozen provider contract. Unknown tools are
# preserved and reported instead of being rejected when Miro evolves.
TOOL_FAMILIES: dict[str, frozenset[str]] = {
    "identity_and_boards": frozenset(
        {"user_who_am_i", "board_search_boards", "board_create", "board_list_items"}
    ),
    "context": frozenset({"context_explore", "context_get"}),
    "layout": frozenset({"layout_get_dsl", "layout_create", "layout_read", "layout_update"}),
    "diagrams": frozenset({"diagram_get_dsl", "diagram_create"}),
    "documents": frozenset({"doc_create", "doc_get", "doc_update"}),
    "tables": frozenset(
        {
            "table_create",
            "table_list_rows",
            "table_sync_rows",
            "table_update_view",
            "table_get_latest_update_history",
        }
    ),
    "code_widgets": frozenset(
        {
            "code_widget_create",
            "code_widget_get",
            "code_widget_list_items",
            "code_widget_update",
            "code_widget_delete",
        }
    ),
    "prototypes": frozenset({"prototype_get_upload_url", "prototype_create"}),
    "images": frozenset(
        {"image_get_upload_url", "image_create", "image_get_data", "image_get_url"}
    ),
    "collaboration": frozenset({"comment_create", "comment_list_comments"}),
}

PLANNER_TOOLS = frozenset().union(*TOOL_FAMILIES.values()) - {"image_delete"}

# Tools already used by a production Schauwerk path before this audit. This is
# intentionally explicit so integration drift becomes reviewable.
INTEGRATED_TOOLS = frozenset(
    {
        "user_who_am_i",
        "board_search_boards",
        "board_create",
        "board_list_items",
        "layout_create",
        "layout_read",
        "layout_update",
        "comment_list_comments",
        "image_get_upload_url",
        "image_create",
        "image_get_data",
        "image_get_url",
    }
)

HIGH_VALUE_LANES: dict[str, tuple[str, ...]] = {
    "context_first_read": ("context_explore", "context_get"),
    "native_diagram": ("diagram_get_dsl", "diagram_create"),
    "living_document": ("doc_create", "doc_get", "doc_update"),
    "structured_data_views": (
        "table_create",
        "table_sync_rows",
        "table_list_rows",
        "table_update_view",
    ),
    "executable_source_view": (
        "code_widget_create",
        "code_widget_get",
        "code_widget_update",
        "code_widget_delete",
    ),
    "interactive_prototype": ("prototype_get_upload_url", "prototype_create"),
    "review_comments": ("comment_create", "comment_list_comments"),
    "managed_image_lifecycle": (
        "image_get_upload_url",
        "image_create",
        "image_get_data",
        "image_get_url",
        "image_delete",
    ),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _tool_names(catalogue: Mapping[str, Any]) -> tuple[str, ...]:
    tools = catalogue.get("tools")
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        raise ValueError("Miro tool catalogue must contain a tools list")
    names: list[str] = []
    for index, item in enumerate(tools):
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError(f"Miro tool catalogue entry {index} is invalid")
        name = item["name"].strip()
        if not name:
            raise ValueError(f"Miro tool catalogue entry {index} has an empty name")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("Miro tool catalogue contains duplicate tool names")
    return tuple(sorted(names))


def _lane_status(observed: set[str], tools: tuple[str, ...]) -> dict[str, Any]:
    available = [name for name in tools if name in observed]
    missing = [name for name in tools if name not in observed]
    return {
        "available": not missing,
        "available_tools": available,
        "missing_tools": missing,
        "coverage_percent": round(100 * len(available) / len(tools), 1),
    }


def audit_tool_catalogue(catalogue: Mapping[str, Any]) -> dict[str, Any]:
    """Compare one observed catalogue with Schauwerk's explicit integration surface."""

    names = _tool_names(catalogue)
    observed = set(names)
    known = set().union(*TOOL_FAMILIES.values())
    family_by_tool = {tool: family for family, tools in TOOL_FAMILIES.items() for tool in tools}
    family_tools: dict[str, list[str]] = defaultdict(list)
    for name in names:
        family_tools[family_by_tool.get(name, "provider_extension")].append(name)

    families: dict[str, Any] = {}
    for family in [*TOOL_FAMILIES, "provider_extension"]:
        available = sorted(family_tools.get(family, []))
        expected = sorted(TOOL_FAMILIES.get(family, frozenset()))
        families[family] = {
            "observed_tools": available,
            "observed_count": len(available),
            "known_family_tools": expected,
            "known_family_coverage_percent": (
                round(100 * len(set(available) & set(expected)) / len(expected), 1)
                if expected
                else None
            ),
        }

    integrated = sorted(observed & INTEGRATED_TOOLS)
    planned = sorted(observed & PLANNER_TOOLS)
    incorporated = sorted(observed & (INTEGRATED_TOOLS | PLANNER_TOOLS))
    unincorporated = sorted(observed - (INTEGRATED_TOOLS | PLANNER_TOOLS))
    lanes = {
        lane: _lane_status(observed, tools) for lane, tools in sorted(HIGH_VALUE_LANES.items())
    }
    unavailable_lanes = sorted(name for name, value in lanes.items() if not value["available"])

    priorities: list[dict[str, Any]] = []
    priority_order = (
        "context_first_read",
        "native_diagram",
        "structured_data_views",
        "living_document",
        "executable_source_view",
        "interactive_prototype",
        "review_comments",
        "managed_image_lifecycle",
    )
    for rank, lane in enumerate(priority_order, start=1):
        status = lanes[lane]
        priorities.append(
            {
                "rank": rank,
                "lane": lane,
                "provider_available": status["available"],
                "missing_tools": status["missing_tools"],
                "recommendation": (
                    "integrate into the representation execution planner"
                    if status["available"]
                    else "keep fail-closed and track as provider capability gap"
                ),
            }
        )

    report: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA,
        "protocol_version": catalogue.get("protocol_version"),
        "server_name": catalogue.get("server_name"),
        "server_version": catalogue.get("server_version"),
        "observed_tool_count": len(names),
        "observed_tools": list(names),
        "known_tools_absent": sorted(known - observed),
        "provider_extensions": sorted(observed - known),
        "families": families,
        "adapter_integration": {
            "runtime_integrated_tools": integrated,
            "runtime_integrated_observed_count": len(integrated),
            "runtime_integration_coverage_percent": (
                round(100 * len(integrated) / len(names), 1) if names else 0.0
            ),
            "execution_planner_tools": planned,
            "incorporated_observed_tools": incorporated,
            "unincorporated_observed_tools": unincorporated,
            "incorporation_coverage_percent": (
                round(100 * len(incorporated) / len(names), 1) if names else 0.0
            ),
        },
        "high_value_lanes": lanes,
        "unavailable_lanes": unavailable_lanes,
        "priorities": priorities,
        "platform_layers": {
            "mcp": {
                "status": "live_operational",
                "role": "agent-facing content discovery, creation, maintenance, and readback",
            },
            "rest_api": {
                "status": "separate_application_credentials_required",
                "role": "board lifecycle, sharing, membership, and provider administration",
                "incorporation": "architectural boundary documented; not authorized by MCP OAuth",
            },
            "web_sdk": {
                "status": "embedded_board_application_required",
                "role": (
                    "viewport, selection, UI panels, realtime events, attention, "
                    "sessions, storage, groups, history, and custom tools"
                ),
                "incorporation": "reserved for a separate interactive Schauwerk companion app",
            },
        },
        "truth_boundary": {
            "operational_authority": "live MCP catalogue",
            "product_reference": "official Miro MCP, REST API, and Web SDK documentation",
            "image_delete_available": "image_delete" in observed,
            "layout_can_delete_unsupported_images": False,
        },
        "does_not_establish": [
            "permission to mutate a board",
            "support for capabilities absent from the live MCP catalogue",
            "visual quality of generated output",
            "availability of Web SDK or REST credentials",
        ],
    }
    report["audit_digest"] = _digest(report)
    return report
