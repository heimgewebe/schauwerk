"""Native document model for editable JSON Canvas input.

The model preserves JSON Canvas source fields and explicit geometry.  It is the
document-backed seam used by the native editor; the existing Representation
renderer remains authoritative for semantic auto-layout inputs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, Final

__all__ = [
    "NATIVE_DOCUMENT_SCHEMA",
    "MAX_NATIVE_GROUPS",
    "MAX_NATIVE_NODES",
    "MAX_NATIVE_EDGES",
    "MAX_NATIVE_ROUTING_PAIRS",
    "MAX_NATIVE_ABS_COORDINATE",
    "NativeDocumentError",
    "editing_document_to_json_canvas",
    "json_canvas_to_editing_document",
    "normalize_editing_document",
    "validate_json_canvas",
]

NATIVE_DOCUMENT_SCHEMA: Final = "schauwerk-native-editing-document.v1"
JSON_CANVAS_FORMAT: Final = "json-canvas-1.0"
MAX_NATIVE_GROUPS: Final = 32
MAX_NATIVE_NODES: Final = 128
MAX_NATIVE_EDGES: Final = 256
MAX_NATIVE_ROUTING_PAIRS: Final = 32_768
_ALLOWED_NODE_TYPES: Final = frozenset({"text", "file", "link", "group"})
_ALLOWED_SIDES: Final = frozenset({"top", "right", "bottom", "left"})
_ALLOWED_ENDS: Final = frozenset({"none", "arrow"})
MAX_NATIVE_ABS_COORDINATE: Final = 10_000_000
_MAX_DIMENSION: Final = 1_000_000
_MAX_JAVASCRIPT_SAFE_INTEGER: Final = (1 << 53) - 1


class NativeDocumentError(ValueError):
    """Raised when editable document input violates the bounded contract."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeDocumentError(f"{field} must be an integer")
    return value


def _geometry_integer(value: Any, *, field: str) -> int:
    parsed = _integer(value, field=field)
    if abs(parsed) > MAX_NATIVE_ABS_COORDINATE:
        raise NativeDocumentError(f"{field} exceeds the coordinate budget")
    return parsed


def _dimension(value: Any, *, field: str) -> int:
    parsed = _integer(value, field=field)
    if parsed <= 0 or parsed > _MAX_DIMENSION:
        raise NativeDocumentError(f"{field} must be between 1 and {_MAX_DIMENSION}")
    return parsed


def _required_text(value: Mapping[str, Any], field: str, *, context: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise NativeDocumentError(f"{context}.{field} must be non-empty text")
    return candidate


def _xml_10_compatible(value: str) -> bool:
    return all(
        ord(character) in {0x09, 0x0A, 0x0D}
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
        for character in value
    )


def _required_id(value: Mapping[str, Any], field: str, *, context: str) -> str:
    candidate = _required_text(value, field, context=context)
    if not _xml_10_compatible(candidate) or any(
        character in candidate for character in "\t\n\r"
    ):
        raise NativeDocumentError(
            f"{context}.{field} must be XML 1.0-compatible, attribute-stable text"
        )
    return candidate


def _optional_text(value: Mapping[str, Any], field: str, *, context: str) -> None:
    if field in value and not isinstance(value[field], str):
        raise NativeDocumentError(f"{context}.{field} must be text")


def _assert_javascript_safe_integers(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, bool) or item is None or isinstance(item, str):
            continue
        if isinstance(item, float):
            if not math.isfinite(item):
                raise NativeDocumentError("JSON Canvas numbers must be finite")
            if item.is_integer() and abs(item) > _MAX_JAVASCRIPT_SAFE_INTEGER:
                raise NativeDocumentError(
                    "JSON Canvas integers must fit the JavaScript safe-integer range"
                )
            continue
        if isinstance(item, int):
            if abs(item) > _MAX_JAVASCRIPT_SAFE_INTEGER:
                raise NativeDocumentError(
                    "JSON Canvas integers must fit the JavaScript safe-integer range"
                )
            continue
        if isinstance(item, Mapping):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def validate_json_canvas(value: Any) -> dict[str, Any]:
    """Validate the supported JSON Canvas 1.0 core without discarding extensions."""

    if not isinstance(value, Mapping):
        raise NativeDocumentError("JSON Canvas input must be one object")
    _assert_javascript_safe_integers(value)
    nodes_value = value.get("nodes", [])
    edges_value = value.get("edges", [])
    if not isinstance(nodes_value, list) or not isinstance(edges_value, list):
        raise NativeDocumentError("JSON Canvas nodes and edges must be arrays")

    normalized = copy.deepcopy(dict(value))
    normalized_nodes = copy.deepcopy(nodes_value)
    normalized_edges = copy.deepcopy(edges_value)
    if "nodes" in value:
        normalized["nodes"] = normalized_nodes
    if "edges" in value:
        normalized["edges"] = normalized_edges

    all_ids: set[str] = set()
    node_ids: set[str] = set()
    for index, node in enumerate(normalized_nodes):
        context = f"nodes[{index}]"
        if not isinstance(node, dict):
            raise NativeDocumentError(f"{context} must be an object")
        node_id = _required_id(node, "id", context=context)
        if node_id in all_ids:
            raise NativeDocumentError(f"duplicate JSON Canvas id: {node_id}")
        all_ids.add(node_id)
        node_ids.add(node_id)
        node_type = _required_text(node, "type", context=context)
        if node_type not in _ALLOWED_NODE_TYPES:
            raise NativeDocumentError(f"{context}.type is unsupported: {node_type}")
        node["x"] = _geometry_integer(node.get("x"), field=f"{context}.x")
        node["y"] = _geometry_integer(node.get("y"), field=f"{context}.y")
        node["width"] = _dimension(node.get("width"), field=f"{context}.width")
        node["height"] = _dimension(node.get("height"), field=f"{context}.height")
        _optional_text(node, "color", context=context)
        if node_type == "text":
            if not isinstance(node.get("text"), str):
                raise NativeDocumentError(f"{context}.text must be text")
        elif node_type == "file":
            _required_text(node, "file", context=context)
            _optional_text(node, "subpath", context=context)
        elif node_type == "link":
            _required_text(node, "url", context=context)
        elif node_type == "group":
            _optional_text(node, "label", context=context)
            if "background" in node or "backgroundStyle" in node:
                raise NativeDocumentError(
                    f"{context} group backgrounds are not supported by the native editor"
                )

    for index, edge in enumerate(normalized_edges):
        context = f"edges[{index}]"
        if not isinstance(edge, dict):
            raise NativeDocumentError(f"{context} must be an object")
        edge_id = _required_id(edge, "id", context=context)
        if edge_id in all_ids:
            raise NativeDocumentError(f"duplicate JSON Canvas id: {edge_id}")
        all_ids.add(edge_id)
        source = _required_text(edge, "fromNode", context=context)
        target = _required_text(edge, "toNode", context=context)
        if source not in node_ids or target not in node_ids:
            raise NativeDocumentError(
                f"{context} references an unknown node: {source!r} -> {target!r}"
            )
        for field in ("fromSide", "toSide"):
            if field in edge and edge[field] not in _ALLOWED_SIDES:
                raise NativeDocumentError(f"{context}.{field} is invalid")
        for field in ("fromEnd", "toEnd"):
            if field in edge and edge[field] not in _ALLOWED_ENDS:
                raise NativeDocumentError(f"{context}.{field} is invalid")
        _optional_text(edge, "label", context=context)
        _optional_text(edge, "color", context=context)

    return normalized


def _node_label(node: Mapping[str, Any]) -> str:
    node_type = str(node["type"])
    if node_type == "text":
        return str(node.get("text", ""))
    if node_type == "file":
        return str(node.get("file", ""))
    if node_type == "link":
        return str(node.get("url", ""))
    return str(node.get("label", ""))


def json_canvas_to_editing_document(
    value: Any, *, title: str = "Schaubild"
) -> dict[str, Any]:
    """Create the explicit-geometry internal document while retaining source fields."""

    canvas = validate_json_canvas(value)
    nodes = [
        {
            "id": str(node["id"]),
            "type": str(node["type"]),
            "x": int(node["x"]),
            "y": int(node["y"]),
            "width": int(node["width"]),
            "height": int(node["height"]),
            "label": _node_label(node),
            "source": copy.deepcopy(node),
        }
        for node in canvas.get("nodes", [])
    ]
    edges = [
        {
            "id": str(edge["id"]),
            "from": str(edge["fromNode"]),
            "to": str(edge["toNode"]),
            "label": str(edge.get("label", "")),
            "from_side": edge.get("fromSide"),
            "to_side": edge.get("toSide"),
            "from_end": edge.get("fromEnd", "none"),
            "to_end": edge.get("toEnd", "arrow"),
            "source": copy.deepcopy(edge),
        }
        for edge in canvas.get("edges", [])
    ]
    source_digest = _digest(canvas)
    return {
        "schema_version": NATIVE_DOCUMENT_SCHEMA,
        "source_format": JSON_CANVAS_FORMAT,
        "title": title,
        "input_digest": source_digest,
        "source_digest": source_digest,
        "source": canvas,
        "nodes": nodes,
        "edges": edges,
    }


def editing_document_to_json_canvas(document: Mapping[str, Any]) -> dict[str, Any]:
    """Project editable document state back to JSON Canvas without ID churn."""

    if document.get("schema_version") != NATIVE_DOCUMENT_SCHEMA:
        raise NativeDocumentError("unsupported native editing document schema")
    if document.get("source_format") != JSON_CANVAS_FORMAT:
        raise NativeDocumentError("native editing document is not JSON Canvas-backed")
    source = document.get("source")
    if not isinstance(source, Mapping):
        raise NativeDocumentError("native editing document source is missing")
    canvas = validate_json_canvas(source)

    nodes = document.get("nodes")
    edges = document.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise NativeDocumentError("native editing document nodes and edges are invalid")

    output_nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for index, item in enumerate(nodes):
        if not isinstance(item, Mapping):
            raise NativeDocumentError(f"editing nodes[{index}] must be an object")
        node_id = _required_text(item, "id", context=f"editing nodes[{index}]")
        if node_id in seen_nodes:
            raise NativeDocumentError(f"duplicate editing node id: {node_id}")
        seen_nodes.add(node_id)
        raw = item.get("source")
        if not isinstance(raw, Mapping):
            raw = {"id": node_id, "type": item.get("type", "text")}
        node = copy.deepcopy(dict(raw))
        node["id"] = node_id
        node["type"] = str(item.get("type", node.get("type", "text")))
        node["x"] = _geometry_integer(item.get("x"), field=f"editing nodes[{index}].x")
        node["y"] = _geometry_integer(item.get("y"), field=f"editing nodes[{index}].y")
        node["width"] = _dimension(
            item.get("width"), field=f"editing nodes[{index}].width"
        )
        node["height"] = _dimension(
            item.get("height"), field=f"editing nodes[{index}].height"
        )
        label = item.get("label")
        if not isinstance(label, str):
            raise NativeDocumentError(f"editing nodes[{index}].label must be text")
        if node["type"] == "text":
            node["text"] = label
        elif node["type"] == "group":
            if label or "label" in node:
                node["label"] = label
            else:
                node.pop("label", None)
        elif node["type"] == "file":
            node["file"] = label
        elif node["type"] == "link":
            node["url"] = label
        output_nodes.append(node)

    output_edges: list[dict[str, Any]] = []
    seen_ids = set(seen_nodes)
    for index, item in enumerate(edges):
        if not isinstance(item, Mapping):
            raise NativeDocumentError(f"editing edges[{index}] must be an object")
        edge_id = _required_text(item, "id", context=f"editing edges[{index}]")
        if edge_id in seen_ids:
            raise NativeDocumentError(f"duplicate editing edge id: {edge_id}")
        seen_ids.add(edge_id)
        source_id = _required_text(item, "from", context=f"editing edges[{index}]")
        target_id = _required_text(item, "to", context=f"editing edges[{index}]")
        if source_id not in seen_nodes or target_id not in seen_nodes:
            raise NativeDocumentError(f"editing edge {edge_id} references an unknown node")
        raw = item.get("source")
        edge = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
        edge.update({"id": edge_id, "fromNode": source_id, "toNode": target_id})
        label = item.get("label", "")
        if not isinstance(label, str):
            raise NativeDocumentError(f"editing edges[{index}].label must be text")
        if label or "label" in edge:
            edge["label"] = label
        else:
            edge.pop("label", None)
        for internal, external, allowed in (
            ("from_side", "fromSide", _ALLOWED_SIDES),
            ("to_side", "toSide", _ALLOWED_SIDES),
            ("from_end", "fromEnd", _ALLOWED_ENDS),
            ("to_end", "toEnd", _ALLOWED_ENDS),
        ):
            value = item.get(internal)
            if value is None and external in {"fromSide", "toSide"}:
                edge.pop(external, None)
                continue
            if value not in allowed:
                raise NativeDocumentError(f"editing edge {edge_id} has invalid {internal}")
            if external == "fromEnd" and value == "none" and external not in edge:
                continue
            if external == "toEnd" and value == "arrow" and external not in edge:
                continue
            edge[external] = value
        output_edges.append(edge)

    result = copy.deepcopy(canvas)
    if output_nodes or "nodes" in canvas:
        result["nodes"] = output_nodes
    else:
        result.pop("nodes", None)
    if output_edges or "edges" in canvas:
        result["edges"] = output_edges
    else:
        result.pop("edges", None)
    return validate_json_canvas(result)

def normalize_editing_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebind source and digests to the current editable document state."""

    canvas = editing_document_to_json_canvas(document)
    normalized = copy.deepcopy(dict(document))
    source_digest = _digest(canvas)
    normalized["source"] = canvas
    normalized["input_digest"] = source_digest
    normalized["source_digest"] = source_digest
    return normalized
