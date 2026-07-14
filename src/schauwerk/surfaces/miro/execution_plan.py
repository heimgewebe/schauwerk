"""Compile native Miro execution lanes from a representation model and route plan."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

EXECUTION_PLAN_SCHEMA = "schauwerk-miro-execution-plan.v1"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _operation(
    operation_id: str,
    *,
    phase: str,
    tool: str,
    reason: str,
    readback_tool: str | None = None,
    required: bool = True,
    parameters: Mapping[str, Any] | None = None,
    fallback: str | None = None,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "phase": phase,
        "tool": tool,
        "required": required,
        "reason": reason,
        "parameters": dict(parameters or {}),
        "readback_tool": readback_tool,
        "fallback": fallback,
    }


def _diagram_type(intent: str) -> str:
    if intent == "sequence":
        return "uml_sequence"
    return "flowchart"


def _table_view(intent: str) -> dict[str, Any]:
    if intent == "timeline":
        return {
            "layout": "timeline",
            "timeline_date_unit": "month",
            "timeline_dependencies_enabled": True,
            "timeline_nesting_enabled": True,
        }
    if intent == "knowledge_map":
        return {"layout": "tree", "tree_direction": "left_to_right"}
    if intent in {"process", "state"}:
        return {"layout": "kanban", "group_by_column": "Status"}
    return {"layout": "table", "table_nesting_enabled": True}


def compile_miro_execution_plan(
    model: Mapping[str, Any], route_plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Select complementary native Miro tools without performing mutations."""

    intent = str(model["intent"])
    requirements = model["requirements"]
    selected_formats = set(route_plan["selected_formats"])
    operations: list[dict[str, Any]] = []

    operations.extend(
        [
            _operation(
                "verify_operator_identity",
                phase="preflight",
                tool="user_who_am_i",
                reason="bind board work to the authenticated Miro user, team, and workspace",
                readback_tool=None,
            ),
            _operation(
                "resolve_target_board",
                phase="preflight",
                tool="board_search_boards",
                reason="resolve the intended board before any content read or mutation",
                readback_tool=None,
            ),
            _operation(
                "create_board_if_authorized",
                phase="preflight",
                tool="board_create",
                reason=(
                    "create a dedicated board only when the execution contract "
                    "explicitly authorizes it"
                ),
                readback_tool="board_search_boards",
                required=False,
                fallback="use an existing allowlisted board",
            ),
            _operation(
                "discover_context",
                phase="preflight",
                tool="context_explore",
                reason=(
                    "identify existing frames, documents, diagrams, tables, and "
                    "prototypes before placement"
                ),
                readback_tool="context_get",
                required=False,
                fallback="use allowlisted board snapshot and layout_read",
            ),
            _operation(
                "read_layout_contract",
                phase="prepare",
                tool="layout_get_dsl",
                reason="bind generated layout syntax to the current provider grammar",
                readback_tool=None,
            ),
            _operation(
                "compose_native_layout",
                phase="compose",
                tool="layout_create",
                reason=(
                    "materialize the editable spatial overview, frames, shapes, "
                    "connectors, documents, and tables"
                ),
                readback_tool="layout_read",
                parameters={"mode": "full"},
            ),
            _operation(
                "update_managed_layout_region",
                phase="maintain",
                tool="layout_update",
                reason=(
                    "apply exact source-bound replacements or deletions for layout-supported items"
                ),
                readback_tool="layout_read",
                required=False,
                fallback="create a reviewed replacement region and retain the prior region",
            ),
        ]
    )

    if intent in {"architecture", "process", "sequence", "state"} or requirements.get(
        "formal_relations"
    ):
        operations.extend(
            [
                _operation(
                    "read_diagram_contract",
                    phase="prepare",
                    tool="diagram_get_dsl",
                    reason=(
                        "bind the generated formal model to Miro's current native diagram grammar"
                    ),
                    readback_tool=None,
                    parameters={"diagram_type": _diagram_type(intent)},
                ),
                _operation(
                    "create_native_diagram",
                    phase="compose",
                    tool="diagram_create",
                    reason=(
                        "keep formal relations editable as a native Miro diagram "
                        "instead of a flattened image"
                    ),
                    readback_tool="context_get",
                    parameters={"diagram_type": _diagram_type(intent)},
                    fallback="retain Mermaid source and editable layout connectors",
                ),
            ]
        )

    if "document" in selected_formats or intent == "narrative" or requirements.get("rich_text"):
        operations.extend(
            [
                _operation(
                    "create_living_document",
                    phase="compose",
                    tool="doc_create",
                    reason="place long-form explanation in an editable native document",
                    readback_tool="doc_get",
                    fallback="use the document object emitted by layout_create",
                ),
                _operation(
                    "update_living_document",
                    phase="maintain",
                    tool="doc_update",
                    reason=(
                        "support exact source-bound updates without replacing the "
                        "whole board region"
                    ),
                    readback_tool="doc_get",
                    required=False,
                ),
            ]
        )

    if (
        "table" in selected_formats
        or intent in {"comparison", "timeline", "knowledge_map", "process", "state"}
        or requirements.get("structured_comparison")
    ):
        operations.extend(
            [
                _operation(
                    "create_structured_table",
                    phase="compose",
                    tool="table_create",
                    reason=(
                        "represent source records with typed text, select, date, "
                        "link, and person columns"
                    ),
                    readback_tool="table_list_rows",
                ),
                _operation(
                    "sync_structured_rows",
                    phase="compose",
                    tool="table_sync_rows",
                    reason="insert or update source-bound records by stable row identifiers",
                    readback_tool="table_list_rows",
                ),
                _operation(
                    "select_data_view",
                    phase="compose",
                    tool="table_update_view",
                    reason=(
                        "use Miro's native table, timeline, kanban, or tree view "
                        "according to semantic intent"
                    ),
                    readback_tool="table_get_latest_update_history",
                    parameters=_table_view(intent),
                ),
            ]
        )

    if "mermaid" in selected_formats:
        operations.extend(
            [
                _operation(
                    "create_mermaid_source_widget",
                    phase="compose",
                    tool="code_widget_create",
                    reason=(
                        "keep the exact Mermaid source visible and syntax-highlighted "
                        "beside the rendered model"
                    ),
                    readback_tool="code_widget_get",
                    parameters={"language": "Mermaid", "line_numbers_visible": True},
                ),
                _operation(
                    "update_mermaid_source_widget",
                    phase="maintain",
                    tool="code_widget_update",
                    reason="update source text and geometry without adding duplicate widgets",
                    readback_tool="code_widget_get",
                    required=False,
                ),
                _operation(
                    "inventory_mermaid_source_widgets",
                    phase="maintain",
                    tool="code_widget_list_items",
                    reason="find prior managed source widgets before creating or retiring one",
                    readback_tool=None,
                    required=False,
                ),
                _operation(
                    "retire_stale_mermaid_source_widget",
                    phase="maintain",
                    tool="code_widget_delete",
                    reason=(
                        "remove a specifically identified stale code widget after "
                        "its replacement is verified"
                    ),
                    readback_tool="code_widget_list_items",
                    required=False,
                ),
            ]
        )

    if "mermaid" in selected_formats or "canvas" in selected_formats:
        operations.extend(
            [
                _operation(
                    "reserve_visual_artifact_upload",
                    phase="prepare",
                    tool="image_get_upload_url",
                    reason=(
                        "upload rendered SVG or canvas previews without requiring public hosting"
                    ),
                    readback_tool=None,
                    required=False,
                ),
                _operation(
                    "create_visual_artifact_image",
                    phase="compose",
                    tool="image_create",
                    reason="place a rendered visual artifact beside editable native source objects",
                    readback_tool="image_get_data",
                    required=False,
                    fallback="retain native diagram, code widget, and layout objects only",
                ),
                _operation(
                    "verify_visual_artifact_url",
                    phase="verify",
                    tool="image_get_url",
                    reason="verify that the provider can return the created image resource",
                    readback_tool="image_get_data",
                    required=False,
                ),
            ]
        )

    if intent in {"presentation", "mixed"} or requirements.get("presentation"):
        operations.extend(
            [
                _operation(
                    "reserve_prototype_uploads",
                    phase="prepare",
                    tool="prototype_get_upload_url",
                    reason="keep potentially large HTML screens outside the model context",
                    readback_tool=None,
                    required=False,
                    parameters={"count": "screen_count"},
                    fallback="use ordered presentation frames",
                ),
                _operation(
                    "create_interactive_prototype",
                    phase="compose",
                    tool="prototype_create",
                    reason=(
                        "embed an interactive multi-screen desktop, tablet, or "
                        "mobile walkthrough when interaction matters"
                    ),
                    readback_tool="context_get",
                    required=False,
                    parameters={"device_type": "tablet", "orientation": "landscape"},
                    fallback="use ordered presentation frames",
                ),
            ]
        )

    if requirements.get("collaboration"):
        operations.append(
            _operation(
                "open_review_comment",
                phase="review",
                tool="comment_create",
                reason="anchor review questions or acceptance notes to the affected board region",
                readback_tool="comment_list_comments",
                required=False,
                fallback="record review only in Schauwerk's receipt-bound Regie surface",
            )
        )

    operations.extend(
        [
            _operation(
                "verify_board_inventory",
                phase="verify",
                tool="board_list_items",
                reason=(
                    "verify item identities, types, parents, positions, and geometry "
                    "after composition"
                ),
                readback_tool=None,
            ),
            _operation(
                "verify_semantic_context",
                phase="verify",
                tool="context_get",
                reason=(
                    "verify that native rich items remain discoverable as coherent board context"
                ),
                readback_tool=None,
                required=False,
            ),
            _operation(
                "verify_collaboration_state",
                phase="verify",
                tool="comment_list_comments",
                reason="include unresolved review comments in the final acceptance boundary",
                readback_tool=None,
                required=False,
            ),
        ]
    )

    required_tools = sorted(
        {item["tool"] for item in operations if item["required"]}
        | {
            item["readback_tool"]
            for item in operations
            if item["required"] and item["readback_tool"] is not None
        }
    )
    optional_tools = sorted(
        (
            {item["tool"] for item in operations if not item["required"]}
            | {
                item["readback_tool"]
                for item in operations
                if not item["required"] and item["readback_tool"] is not None
            }
        )
        - set(required_tools)
    )
    all_tools = sorted(set(required_tools) | set(optional_tools))
    plan: dict[str, Any] = {
        "schema_version": EXECUTION_PLAN_SCHEMA,
        "input_digest": model["input_digest"],
        "route_plan_digest": route_plan["plan_digest"],
        "intent": intent,
        "primary_format": route_plan["primary_format"],
        "selected_formats": list(route_plan["selected_formats"]),
        "operation_count": len(operations),
        "operations": operations,
        "required_tools": required_tools,
        "optional_tools": optional_tools,
        "all_tools": all_tools,
        "provider_gap_contract": {
            "managed_image_delete_required_for_atomic_image_replace": True,
            "layout_update_may_not_delete_unsupported_image_items": True,
        },
        "does_not_establish": [
            "provider capability availability without a live catalogue audit",
            "permission to mutate a board",
            "successful rendering without post-mutation readback",
            "aesthetic quality without visual review",
        ],
    }
    plan["execution_plan_digest"] = _digest(plan)
    return plan
