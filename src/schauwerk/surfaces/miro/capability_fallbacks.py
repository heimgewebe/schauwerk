"""Deterministic, creation-only fallbacks for unavailable native Miro tools."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

FALLBACK_SCHEMA = "schauwerk-miro-provider-resolution.v1"
BASELINE_TOOLS = frozenset({"user_who_am_i", "context_explore", "board_list_items"})
LAYOUT_TOOLS = frozenset({"layout_get_dsl", "layout_create", "layout_read"})

NATIVE_OPERATION_TOOLS: dict[str, frozenset[str]] = {
    "layout": LAYOUT_TOOLS,
    "diagram": frozenset({"diagram_get_dsl", "diagram_create", "context_get"}),
    "document": frozenset({"doc_create", "doc_get"}),
    "document_update": frozenset({"doc_get", "doc_update"}),
    "table": frozenset({"table_create", "table_list_rows"}),
    "table_history": frozenset({"table_get_latest_update_history"}),
    "code_widget": frozenset({"code_widget_create", "code_widget_get"}),
    "code_widget_inventory": frozenset({"code_widget_list_items"}),
    "code_widget_update": frozenset({"code_widget_get", "code_widget_update"}),
    "code_widget_delete": frozenset(
        {"code_widget_get", "code_widget_list_items", "code_widget_delete"}
    ),
    "prototype": frozenset({"prototype_get_upload_url", "prototype_create", "context_get"}),
    "comment": frozenset({"comment_create", "comment_list_comments"}),
}

CREATION_FALLBACKS: dict[str, str] = {
    "document": "layout_document",
    "table": "layout_grid",
    "code_widget": "layout_code_panel",
    "prototype": "ordered_frames",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _plain(value: Any, *, limit: int = 1200) -> str:
    text = str(value) if value is not None else ""
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _quoted(value: Any, *, limit: int = 1200) -> str:
    return _plain(value, limit=limit).replace("\\", "\\\\").replace('"', '\\"')


def _position(operation: Mapping[str, Any]) -> tuple[float, float]:
    x = operation.get("x", 0)
    y = operation.get("y", 0)
    return float(x) if isinstance(x, int | float) else 0.0, float(y) if isinstance(
        y, int | float
    ) else 0.0


def _layout_operation(operation: Mapping[str, Any], *, dsl: str, fallback: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "operation_id": operation["operation_id"],
        "kind": "layout",
        "dsl": dsl,
        "provider_fallback": {
            "schema_version": FALLBACK_SCHEMA,
            "original_kind": operation["kind"],
            "fallback": fallback,
            "source_operation_digest": _digest(dict(operation)),
        },
    }
    target = operation.get("target_miro_url")
    if isinstance(target, str):
        value["target_miro_url"] = target
    return value


def compile_creation_fallback(operation: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one supported creation operation to an editable layout representation."""

    kind = operation.get("kind")
    if kind not in CREATION_FALLBACKS:
        raise ValueError(f"no deterministic creation fallback for operation kind: {kind}")
    x, y = _position(operation)
    root = f"fallback-{operation['operation_id']}"

    if kind == "document":
        content = _quoted(operation.get("content"), limit=5000)
        dsl = "\n".join(
            [
                f'{root} FRAME x={x:g} y={y:g} w=1000 h=620 "Dokument · Ersatzdarstellung"',
                f'{root}-title TEXT parent={root} x={x:g} y={y - 250:g} w=900 "Dokument"',
                f'{root}-body TEXT parent={root} x={x:g} y={y:g} w=900 "{content}"',
            ]
        )
        return _layout_operation(operation, dsl=dsl, fallback=CREATION_FALLBACKS[kind])

    if kind == "table":
        columns = [str(column.get("column_title", "")) for column in operation.get("columns", [])]
        lines = [" | ".join(_plain(column, limit=80) for column in columns)]
        for row in operation.get("rows", [])[:40]:
            cells = {
                str(cell.get("columnTitle", "")): cell.get("value", "")
                for cell in row.get("cells", [])
                if isinstance(cell, Mapping)
            }
            lines.append(" | ".join(_plain(cells.get(column, ""), limit=100) for column in columns))
        view = operation.get("view")
        if isinstance(view, Mapping):
            lines.append(f"Ansicht: {_plain(view, limit=600)}")
        table_text = _quoted("\n".join(lines), limit=6000)
        title = _quoted(operation.get("table_title", "Tabelle"), limit=160)
        dsl = "\n".join(
            [
                f'{root} FRAME x={x:g} y={y:g} w=1200 h=720 "Tabelle · Ersatzdarstellung"',
                f'{root}-title TEXT parent={root} x={x:g} y={y - 300:g} w=1080 "{title}"',
                f'{root}-grid TEXT parent={root} x={x:g} y={y:g} w=1080 "{table_text}"',
            ]
        )
        return _layout_operation(operation, dsl=dsl, fallback=CREATION_FALLBACKS[kind])

    if kind == "code_widget":
        title = _quoted(operation.get("title") or "Quelltext", limit=160)
        language = _quoted(operation.get("language") or "PlainText", limit=50)
        code = _quoted(operation.get("code"), limit=6000)
        dsl = "\n".join(
            [
                f'{root} FRAME x={x:g} y={y:g} w=1100 h=720 "Code · Ersatzdarstellung"',
                (
                    f'{root}-title TEXT parent={root} x={x:g} y={y - 300:g} '
                    f'w=980 "{title} · {language}"'
                ),
                f'{root}-code TEXT parent={root} x={x:g} y={y:g} w=980 "{code}"',
            ]
        )
        return _layout_operation(operation, dsl=dsl, fallback=CREATION_FALLBACKS[kind])

    screens = operation.get("screens", [])
    labels = [
        (
            f"{index + 1}. {_plain(screen.get('path', 'Screen'), limit=120)} · "
            f"{str(screen.get('sha256', ''))[:12]}"
        )
        for index, screen in enumerate(screens)
        if isinstance(screen, Mapping)
    ]
    summary = _quoted("\n".join(labels), limit=5000)
    device = _quoted(operation.get("device_type", "desktop"), limit=40)
    orientation = _quoted(operation.get("orientation", "landscape"), limit=40)
    dsl = "\n".join(
        [
            f'{root} FRAME x={x:g} y={y:g} w=1200 h=720 "Prototyp · geordnete Frames"',
            (
                f'{root}-title TEXT parent={root} x={x:g} y={y - 300:g} '
                f'w=1080 "{device} · {orientation}"'
            ),
            f'{root}-screens TEXT parent={root} x={x:g} y={y:g} w=1080 "{summary}"',
        ]
    )
    return _layout_operation(operation, dsl=dsl, fallback=CREATION_FALLBACKS[kind])


def operation_tools(operation: Mapping[str, Any]) -> frozenset[str]:
    kind = operation.get("kind")
    tools = set(NATIVE_OPERATION_TOOLS.get(str(kind), frozenset()))
    if kind == "table":
        if operation.get("rows"):
            tools.add("table_sync_rows")
        if operation.get("view"):
            tools.add("table_update_view")
    return frozenset(tools)


def resolve_bundle_operations(
    operations: Sequence[Mapping[str, Any]], observed_tools: Sequence[str] | set[str]
) -> dict[str, Any]:
    """Resolve each operation to native, deterministic fallback, or blocked before mutation."""

    observed = set(observed_tools)
    baseline_missing = sorted(BASELINE_TOOLS - observed)
    resolved: list[dict[str, Any]] = []
    execution_operations: list[dict[str, Any]] = []
    blocked_tools: set[str] = set(baseline_missing)

    for operation in operations:
        native_tools = operation_tools(operation)
        missing_native = sorted(native_tools - observed)
        kind = str(operation.get("kind"))
        if not missing_native:
            mode = "native"
            execution = dict(operation)
            fallback = None
        elif kind in CREATION_FALLBACKS and not (LAYOUT_TOOLS - observed):
            mode = "fallback"
            fallback = CREATION_FALLBACKS[kind]
            execution = compile_creation_fallback(operation)
        else:
            mode = "blocked"
            fallback = None
            execution = dict(operation)
            blocked_tools.update(missing_native)
        resolved.append(
            {
                "operation_id": operation.get("operation_id"),
                "original_kind": kind,
                "mode": mode,
                "fallback": fallback,
                "native_tools": sorted(native_tools),
                "missing_native_tools": missing_native,
                "execution_kind": execution.get("kind"),
            }
        )
        execution_operations.append(execution)

    if baseline_missing:
        for item in resolved:
            item["mode"] = "blocked"
            item["fallback"] = None

    report: dict[str, Any] = {
        "schema_version": FALLBACK_SCHEMA,
        "baseline_missing_tools": baseline_missing,
        "operation_resolutions": resolved,
        "blocked_tools": sorted(blocked_tools),
        "native_count": sum(item["mode"] == "native" for item in resolved),
        "fallback_count": sum(item["mode"] == "fallback" for item in resolved),
        "blocked_count": sum(item["mode"] == "blocked" for item in resolved),
        "execution_operations": execution_operations,
        "truth_boundary": {
            "fallbacks_are_creation_only": True,
            "maintenance_operations_remain_fail_closed": True,
            "fallbacks_preserve_native_item_type": False,
            "fallbacks_remain_editable_layout_items": True,
        },
    }
    digest_input = {key: value for key, value in report.items() if key != "execution_operations"}
    report["resolution_digest"] = _digest(digest_input)
    return report
