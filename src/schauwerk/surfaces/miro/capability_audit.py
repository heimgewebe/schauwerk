"""Drift-aware audit of the live Miro MCP tool catalogue."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .capability_fallbacks import CREATION_FALLBACKS, LAYOUT_TOOLS

AUDIT_SCHEMA = "schauwerk-miro-capability-audit.v1"
REFERENCE_SCHEMA = "schauwerk-miro-mcp-tool-reference.v1"
REFERENCE_RESOURCE = "miro-mcp-tools-reference.v1.json"
REFERENCE_SCHEMA_RESOURCE = "miro-mcp-tool-reference.v1.schema.json"

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
        "layout_get_dsl",
        "layout_create",
        "layout_read",
        "layout_update",
        "context_explore",
        "context_get",
        "diagram_get_dsl",
        "diagram_create",
        "doc_create",
        "doc_get",
        "doc_update",
        "table_create",
        "table_sync_rows",
        "table_list_rows",
        "table_update_view",
        "table_get_latest_update_history",
        "code_widget_create",
        "code_widget_get",
        "code_widget_list_items",
        "code_widget_update",
        "code_widget_delete",
        "prototype_get_upload_url",
        "prototype_create",
        "comment_create",
        "comment_list_comments",
        "image_get_upload_url",
        "image_create",
        "image_get_data",
        "image_get_url",
    }
)

SUPPLEMENTAL_INTEGRATED_TOOLS = frozenset({"preview_resource_poll"})
INTENTIONALLY_UNINCORPORATED_TOOLS = frozenset({"record_ui_feedback"})
PROVIDER_EXTENSION_ROLES: dict[str, dict[str, Any]] = {
    "preview_resource_poll": {
        "role": "supplemental_provider_preview",
        "integration": "native_executor_optional",
        "authoritative": False,
    },
    "record_ui_feedback": {
        "role": "mcp_ui_feedback_telemetry",
        "integration": "intentionally_not_integrated",
        "authoritative": False,
    },
}


HIGH_VALUE_LANES: dict[str, tuple[str, ...]] = {
    "context_first_read": ("context_explore", "context_get"),
    "native_diagram": ("diagram_get_dsl", "diagram_create"),
    "living_document": ("doc_create", "doc_get", "doc_update"),
    "structured_data_views": (
        "table_create",
        "table_sync_rows",
        "table_list_rows",
        "table_update_view",
        "table_get_latest_update_history",
    ),
    "executable_source_view": (
        "code_widget_create",
        "code_widget_get",
        "code_widget_list_items",
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

LANE_FALLBACK_KINDS: dict[str, str] = {
    "living_document": "document",
    "structured_data_views": "table",
    "executable_source_view": "code_widget",
    "interactive_prototype": "prototype",
}

LANE_FALLBACK_COVERED_TOOLS: dict[str, frozenset[str]] = {
    "living_document": frozenset({"doc_create", "doc_get"}),
    "structured_data_views": frozenset(
        {"table_create", "table_sync_rows", "table_update_view", "table_list_rows"}
    ),
    "executable_source_view": frozenset({"code_widget_create", "code_widget_get"}),
    "interactive_prototype": frozenset(
        {"prototype_get_upload_url", "prototype_create", "context_get"}
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


def _load_tool_reference(reference: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if reference is None:
        resource = resources.files("schauwerk.schemas").joinpath(REFERENCE_RESOURCE)
        try:
            value = json.loads(resource.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Miro tool reference must be UTF-8 JSON") from exc
    else:
        value = dict(reference)
    schema_resource = resources.files("schauwerk.schemas").joinpath(REFERENCE_SCHEMA_RESOURCE)
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        raise ValueError(f"invalid Miro tool reference at {location}: {error.message}")
    tools = value["tools"]
    if len(tools) != len(set(tools)):
        raise ValueError("Miro tool reference contains duplicate tool names")
    normalized = dict(value)
    normalized["tools"] = sorted(tools)
    return normalized


def _lane_status(observed: set[str], lane: str, tools: tuple[str, ...]) -> dict[str, Any]:
    available = [name for name in tools if name in observed]
    missing = [name for name in tools if name not in observed]
    missing_set = set(missing)
    fallback_kind = LANE_FALLBACK_KINDS.get(lane)
    covered_tools = LANE_FALLBACK_COVERED_TOOLS.get(lane, frozenset())
    fallback_covered_missing = sorted(missing_set & covered_tools)
    uncovered_missing = sorted(missing_set - covered_tools)
    layout_available = LAYOUT_TOOLS.issubset(observed)
    fallback_available = bool(
        fallback_covered_missing and fallback_kind in CREATION_FALLBACKS and layout_available
    )
    effective_available = not uncovered_missing and (
        not fallback_covered_missing or fallback_available
    )
    if not missing:
        mode = "native"
    elif fallback_available and uncovered_missing:
        mode = "fallback_with_gaps"
    elif fallback_available:
        mode = "fallback"
    elif uncovered_missing and not fallback_covered_missing:
        mode = "native_with_gaps"
    else:
        mode = "blocked"
    return {
        "available": not missing,
        "effective_available": effective_available,
        "creation_fallback_available": fallback_available,
        "mode": mode,
        "fallback": CREATION_FALLBACKS.get(fallback_kind) if fallback_available else None,
        "fallback_covered_missing_tools": fallback_covered_missing,
        "uncovered_missing_tools": uncovered_missing,
        "available_tools": available,
        "missing_tools": missing,
        "coverage_percent": round(100 * len(available) / len(tools), 1),
    }


def audit_tool_catalogue(
    catalogue: Mapping[str, Any],
    *,
    rest_status: Mapping[str, Any] | None = None,
    reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare one observed catalogue with Schauwerk's explicit integration surface."""

    names = _tool_names(catalogue)
    observed = set(names)
    tool_reference = _load_tool_reference(reference)
    reference_names = tuple(tool_reference["tools"])
    referenced = set(reference_names)
    adapter_surface = INTEGRATED_TOOLS | PLANNER_TOOLS | SUPPLEMENTAL_INTEGRATED_TOOLS
    reference_integrated = sorted(referenced & adapter_surface)
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

    integrated_surface = INTEGRATED_TOOLS | SUPPLEMENTAL_INTEGRATED_TOOLS
    incorporated_surface = integrated_surface | PLANNER_TOOLS
    integrated = sorted(observed & integrated_surface)
    planned = sorted(observed & PLANNER_TOOLS)
    incorporated = sorted(observed & incorporated_surface)
    unincorporated = sorted(observed - incorporated_surface)
    intentionally_unincorporated = sorted(
        observed & INTENTIONALLY_UNINCORPORATED_TOOLS & set(unincorporated)
    )
    actionable_unincorporated = sorted(set(unincorporated) - set(intentionally_unincorporated))
    actionable_observed = observed - set(intentionally_unincorporated)
    lanes = {
        lane: _lane_status(observed, lane, tools)
        for lane, tools in sorted(HIGH_VALUE_LANES.items())
    }
    credential = rest_status.get("credential") if isinstance(rest_status, Mapping) else None
    credential_configured = (
        credential.get("exists") is True if isinstance(credential, Mapping) else False
    )
    rest_live_known = (
        rest_status.get("live_authorized_known") is True
        if isinstance(rest_status, Mapping)
        else False
    )
    rest_live_authorized = (
        rest_status.get("live_authorized") is True if isinstance(rest_status, Mapping) else False
    )
    rest_write_authorized = (
        rest_status.get("boards_write_authorized") is True
        if isinstance(rest_status, Mapping)
        else False
    )
    managed_cross_surface_available = (
        {"image_get_upload_url", "image_create", "board_list_items"}.issubset(observed)
        and credential_configured
        and rest_live_known
        and rest_live_authorized
        and rest_write_authorized
    )
    if managed_cross_surface_available:
        managed = dict(lanes["managed_image_lifecycle"])
        managed.update(
            {
                "effective_available": True,
                "mode": "cross_surface",
                "fallback": "separate_rest_delete_adapter",
                "fallback_covered_missing_tools": ["image_delete"],
                "uncovered_missing_tools": [],
            }
        )
        lanes["managed_image_lifecycle"] = managed
    unavailable_lanes = sorted(
        name for name, value in lanes.items() if not value["effective_available"]
    )

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
                "effective_available": status["effective_available"],
                "mode": status["mode"],
                "fallback": status["fallback"],
                "missing_tools": status["missing_tools"],
                "fallback_covered_missing_tools": status["fallback_covered_missing_tools"],
                "uncovered_missing_tools": status["uncovered_missing_tools"],
                "recommendation": (
                    "integrate into the representation execution planner"
                    if status["available"]
                    else (
                        "use MCP create/readback with the separately authorized REST delete adapter"
                    )
                    if status["mode"] == "cross_surface"
                    else "use the deterministic editable layout fallback"
                    if status["effective_available"]
                    else (
                        "use the creation fallback and keep uncovered maintenance operations "
                        "fail-closed"
                    )
                    if status["creation_fallback_available"]
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
        "official_reference": {
            "schema_version": tool_reference["schema_version"],
            "source_url": tool_reference["source_url"],
            "observed_at": tool_reference["observed_at"],
            "operational_authority": tool_reference["operational_authority"],
            "tool_count": len(reference_names),
            "tools": list(reference_names),
            "reference_missing_live": sorted(referenced - observed),
            "live_not_in_reference": sorted(observed - referenced),
            "reference_integrated_tools": reference_integrated,
            "reference_not_integrated": sorted(referenced - adapter_surface),
            "live_reference_coverage_percent": (
                round(100 * len(observed & referenced) / len(referenced), 1) if referenced else 0.0
            ),
            "adapter_reference_coverage_percent": (
                round(100 * len(reference_integrated) / len(referenced), 1) if referenced else 0.0
            ),
            "diagnostic_only": True,
        },
        "known_tools_absent": sorted(known - observed),
        "provider_extensions": sorted(observed - known),
        "provider_extension_roles": {
            name: PROVIDER_EXTENSION_ROLES[name]
            for name in sorted(observed & set(PROVIDER_EXTENSION_ROLES))
        },
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
            "intentionally_unincorporated_observed_tools": intentionally_unincorporated,
            "actionable_unincorporated_observed_tools": actionable_unincorporated,
            "incorporation_coverage_percent": (
                round(100 * len(incorporated) / len(names), 1) if names else 0.0
            ),
            "actionable_incorporation_coverage_percent": (
                round(
                    100 * len(set(incorporated) & actionable_observed) / len(actionable_observed),
                    1,
                )
                if actionable_observed
                else 100.0
            ),
        },
        "high_value_lanes": lanes,
        "cross_surface_lanes": {
            "managed_image_lifecycle": {
                "adapter_implemented": True,
                "mcp_image_create_available": {
                    "image_get_upload_url",
                    "image_create",
                    "board_list_items",
                }.issubset(observed),
                "mcp_image_delete_available": "image_delete" in observed,
                "rest_delete_adapter": "implemented_fail_closed",
                "rest_credential_configured": credential_configured,
                "rest_live_authorized_known": rest_live_known,
                "rest_live_authorized": rest_live_authorized,
                "rest_boards_write_authorized": rest_write_authorized,
                "rest_required_scope": "boards:write",
                "provider_semantics": "create-verify-delete-saga",
                "globally_atomic": False,
                "available": managed_cross_surface_available,
            }
        },
        "provider_fallbacks": {
            "layout_tools_available": LAYOUT_TOOLS.issubset(observed),
            "creation_only": True,
            "mappings": {
                lane: {
                    "native_kind": kind,
                    "fallback": CREATION_FALLBACKS[kind],
                    "mode": lanes[lane]["mode"],
                }
                for lane, kind in sorted(LANE_FALLBACK_KINDS.items())
            },
            "maintenance_operations_fail_closed": True,
        },
        "unavailable_lanes": unavailable_lanes,
        "priorities": priorities,
        "platform_layers": {
            "mcp": {
                "status": "live_operational",
                "role": "agent-facing content discovery, creation, maintenance, and readback",
            },
            "rest_api": {
                "status": (
                    "live_write_authorized"
                    if managed_cross_surface_available
                    else "separate_application_credentials_required"
                ),
                "role": ("separately authorized image read/delete plus provider administration"),
                "incorporation": (
                    "managed image GET/DELETE adapter implemented; MCP OAuth is never reused"
                ),
            },
            "web_sdk": {
                "status": "embedded_board_application_required",
                "role": (
                    "viewport, selection, UI panels, realtime events, attention, "
                    "sessions, storage, groups, history, and custom tools"
                ),
                "incorporation": (
                    "interactive companion with explicit, user-confirmed write actions"
                ),
            },
        },
        "truth_boundary": {
            "operational_authority": (
                "live MCP catalogue plus live separate REST doctor for cross-surface lanes"
                if managed_cross_surface_available
                else "live MCP catalogue"
            ),
            "product_reference": "official Miro MCP, REST API, and Web SDK documentation",
            "image_delete_available": "image_delete" in observed,
            "layout_can_delete_unsupported_images": False,
            "managed_image_rest_adapter_implemented": True,
            "managed_image_globally_atomic": False,
            "managed_image_provider_semantics": "create-verify-delete-saga",
        },
        "does_not_establish": [
            "permission to mutate a board",
            "support for capabilities absent from the live MCP catalogue",
            "provider availability inferred from the documentation reference",
            "visual quality of generated output",
            "aesthetic acceptance from provider preview resources",
            "source truth from MCP UI feedback telemetry",
            "availability of Web SDK credentials",
            "future validity of the separately configured REST authorization",
            "provider-global atomic image replacement",
        ],
    }
    report["audit_digest"] = _digest(report)
    return report
