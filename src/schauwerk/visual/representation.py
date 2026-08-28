"""Renderer-independent representation router with Mermaid, JSON Canvas and Miro outputs."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from schauwerk.surfaces.miro.execution_plan import compile_miro_execution_plan

from .composer_v2 import (
    clip_text,
    connector_object,
    frame,
    shape_object,
    text_object,
)
from .delivery import (
    compile_representation_native_bundle,
    render_representation_document,
    render_representation_table,
)
from .system_v2 import (
    finalize_board_spec,
    render_board_dsl,
    validate_board_spec,
)

INPUT_SCHEMA = "schauwerk-representation-input.v1"
PLAN_SCHEMA = "schauwerk-representation-plan.v1"
PACKAGE_SCHEMA = "schauwerk-representation-package.v1"
RECEIPT_SCHEMA = "schauwerk-representation-receipt.v1"
MERMAID_PROFILE = "mermaid-11.16.0-strict-source.v1"
JSON_CANVAS_PROFILE = "json-canvas-1.0.v1"
MIRO_PROFILE = "miro-native-composition.v1"

_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SUPPORTED_INTENTS = {
    "architecture",
    "process",
    "sequence",
    "state",
    "timeline",
    "comparison",
    "knowledge_map",
    "narrative",
    "presentation",
    "mixed",
}
_SUPPORTED_NODE_KINDS = {
    "human",
    "system",
    "service",
    "store",
    "decision",
    "risk",
    "action",
    "evidence",
    "concept",
}
_SUPPORTED_EDGE_KINDS = {
    "authority",
    "flow",
    "evidence",
    "feedback",
    "risk",
    "association",
}
_SUPPORTED_FORMATS = {"mermaid", "canvas", "miro_native", "table", "document"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "title",
        "purpose",
        "intent",
        "groups",
        "nodes",
        "edges",
        "requirements",
        "requested_formats",
    }
)
_GROUP_FIELDS = frozenset({"id", "label"})
_NODE_FIELDS = frozenset({"id", "label", "kind", "group", "summary"})
_EDGE_FIELDS = frozenset({"id", "from", "to", "label", "kind"})
_REQUIREMENT_KEYS = (
    "formal_relations",
    "free_spatial_layout",
    "presentation",
    "collaboration",
    "rich_text",
    "structured_comparison",
    "portable_offline",
)
_REQUIREMENT_FIELDS = frozenset(_REQUIREMENT_KEYS)
_IDENTITY_CONTRACT = (
    "coverage, when present, measures stable source-id materialization in the "
    "emitted renderer artifact; it does not establish semantic or visual completeness"
)
_RENAME_NOREPLACE = 1


class RepresentationError(ValueError):
    pass


def _require_fields(
    value: Mapping[Any, Any],
    *,
    field: str,
    allowed: frozenset[str],
    required: frozenset[str],
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    if missing:
        raise RepresentationError(f"{field} is missing required fields: {', '.join(missing)}")
    unknown = sorted(keys - allowed, key=str)
    if unknown:
        raise RepresentationError(
            f"{field} contains unknown fields: {', '.join(str(item) for item in unknown)}"
        )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise RepresentationError(f"{field} must be a string")
    if len(value) > maximum:
        raise RepresentationError(f"{field} exceeds {maximum} characters")
    text = " ".join(value.split())
    if not text:
        raise RepresentationError(f"{field} must not be empty")
    return text


def _safe_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RepresentationError(f"{field} must match {_SAFE_ID.pattern}")
    return value


def _normalize_representation_input(
    value: Mapping[str, Any], *, allow_input_digest: bool
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RepresentationError("representation input root must be an object")
    allowed_fields = _PUBLIC_ROOT_FIELDS | ({"input_digest"} if allow_input_digest else set())
    _require_fields(
        value,
        field="representation input",
        allowed=frozenset(allowed_fields),
        required=_PUBLIC_ROOT_FIELDS,
    )
    if value.get("schema_version") != INPUT_SCHEMA:
        raise RepresentationError(f"schema_version must be {INPUT_SCHEMA}")
    identifier = _safe_id(value.get("id"), field="id")
    title = _clean_text(value.get("title"), field="title", maximum=160)
    purpose = _clean_text(value.get("purpose"), field="purpose", maximum=500)
    intent = value.get("intent")
    if intent not in _SUPPORTED_INTENTS:
        raise RepresentationError(f"intent must be one of {sorted(_SUPPORTED_INTENTS)}")

    raw_groups = value["groups"]
    if not isinstance(raw_groups, list):
        raise RepresentationError("groups must be a list")
    groups: list[dict[str, str]] = []
    group_ids: set[str] = set()
    for index, raw_group in enumerate(raw_groups):
        if not isinstance(raw_group, Mapping):
            raise RepresentationError(f"groups[{index}] must be an object")
        _require_fields(
            raw_group,
            field=f"groups[{index}]",
            allowed=_GROUP_FIELDS,
            required=_GROUP_FIELDS,
        )
        group_id = _safe_id(raw_group.get("id"), field=f"groups[{index}].id")
        if group_id in group_ids:
            raise RepresentationError(f"duplicate group id: {group_id}")
        group_ids.add(group_id)
        groups.append(
            {
                "id": group_id,
                "label": _clean_text(
                    raw_group.get("label"), field=f"groups[{index}].label", maximum=100
                ),
            }
        )

    raw_nodes = value["nodes"]
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise RepresentationError("nodes must be a non-empty list")
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, Mapping):
            raise RepresentationError(f"nodes[{index}] must be an object")
        _require_fields(
            raw_node,
            field=f"nodes[{index}]",
            allowed=_NODE_FIELDS,
            required=frozenset({"id", "label", "kind"}),
        )
        node_id = _safe_id(raw_node.get("id"), field=f"nodes[{index}].id")
        if node_id in node_ids:
            raise RepresentationError(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        kind = raw_node.get("kind")
        if kind not in _SUPPORTED_NODE_KINDS:
            raise RepresentationError(
                f"nodes[{index}].kind must be one of {sorted(_SUPPORTED_NODE_KINDS)}"
            )
        group = raw_node.get("group")
        if group is not None and group not in group_ids:
            raise RepresentationError(f"nodes[{index}].group references unknown group: {group}")
        summary = raw_node.get("summary", "")
        if not isinstance(summary, str) or len(summary) > 500:
            raise RepresentationError(
                f"nodes[{index}].summary must be a string up to 500 characters"
            )
        nodes.append(
            {
                "id": node_id,
                "label": _clean_text(
                    raw_node.get("label"), field=f"nodes[{index}].label", maximum=120
                ),
                "kind": kind,
                "group": group,
                "summary": " ".join(summary.split()),
            }
        )

    raw_edges = value["edges"]
    if not isinstance(raw_edges, list):
        raise RepresentationError("edges must be a list")
    edges: list[dict[str, str]] = []
    edge_ids: set[str] = set()
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, Mapping):
            raise RepresentationError(f"edges[{index}] must be an object")
        _require_fields(
            raw_edge,
            field=f"edges[{index}]",
            allowed=_EDGE_FIELDS,
            required=_EDGE_FIELDS,
        )
        edge_id = _safe_id(raw_edge.get("id"), field=f"edges[{index}].id")
        if edge_id in edge_ids:
            raise RepresentationError(f"duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        source = raw_edge.get("from")
        target = raw_edge.get("to")
        if source not in node_ids or target not in node_ids:
            raise RepresentationError(f"edges[{index}] references an unknown node")
        kind = raw_edge.get("kind")
        if kind not in _SUPPORTED_EDGE_KINDS:
            raise RepresentationError(
                f"edges[{index}].kind must be one of {sorted(_SUPPORTED_EDGE_KINDS)}"
            )
        edges.append(
            {
                "id": edge_id,
                "from": str(source),
                "to": str(target),
                "label": _clean_text(
                    raw_edge.get("label"), field=f"edges[{index}].label", maximum=120
                ),
                "kind": str(kind),
            }
        )

    raw_requirements = value["requirements"]
    if not isinstance(raw_requirements, Mapping):
        raise RepresentationError("requirements must be an object")
    _require_fields(
        raw_requirements,
        field="requirements",
        allowed=_REQUIREMENT_FIELDS,
        required=frozenset(),
    )
    requirements: dict[str, bool] = {}
    for key in _REQUIREMENT_KEYS:
        raw_requirement = raw_requirements.get(key, False)
        if not isinstance(raw_requirement, bool):
            raise RepresentationError(f"requirements.{key} must be a boolean")
        requirements[key] = raw_requirement

    raw_requested = value["requested_formats"]
    if not isinstance(raw_requested, list) or any(
        not isinstance(item, str) or item not in _SUPPORTED_FORMATS for item in raw_requested
    ):
        raise RepresentationError(f"requested_formats must use {sorted(_SUPPORTED_FORMATS)}")
    if len(set(raw_requested)) != len(raw_requested):
        raise RepresentationError("requested_formats must not contain duplicates")
    requested = sorted(raw_requested)

    normalized: dict[str, Any] = {
        "schema_version": INPUT_SCHEMA,
        "id": identifier,
        "title": title,
        "purpose": purpose,
        "intent": intent,
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
        "requirements": requirements,
        "requested_formats": requested,
    }
    computed_digest = _digest(normalized)
    supplied_digest = value.get("input_digest")
    if allow_input_digest and (
        not isinstance(supplied_digest, str)
        or _SHA256.fullmatch(supplied_digest) is None
        or supplied_digest != computed_digest
    ):
        raise RepresentationError("input_digest does not match normalized representation input")
    normalized["input_digest"] = computed_digest
    return normalized


def validate_representation_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one public representation-input document and normalize it."""

    return _normalize_representation_input(value, allow_input_digest=False)


def _validate_representation_model(value: Mapping[str, Any]) -> dict[str, Any]:
    """Revalidate an internal normalized model including its exact digest."""

    return _normalize_representation_input(value, allow_input_digest=True)


def load_representation_input(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepresentationError(f"representation input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RepresentationError(f"representation input is invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, Mapping):
        raise RepresentationError("representation input root must be an object")
    return validate_representation_input(raw)


def route_representation(model: Mapping[str, Any]) -> dict[str, Any]:
    normalized = (
        _validate_representation_model(model)
        if "input_digest" in model
        else validate_representation_input(model)
    )
    intent = normalized["intent"]
    requirements = normalized["requirements"]
    node_count = len(normalized["nodes"])
    edge_count = len(normalized["edges"])
    group_count = len(normalized["groups"])

    scores = {name: 0 for name in _SUPPORTED_FORMATS}
    reasons: dict[str, list[str]] = {name: [] for name in _SUPPORTED_FORMATS}

    formal_intents = {"architecture", "process", "sequence", "state", "timeline"}
    if intent in formal_intents:
        scores["mermaid"] += 8
        reasons["mermaid"].append(f"intent {intent} is a formal graph")
    if requirements["formal_relations"] or edge_count >= max(3, node_count // 2):
        scores["mermaid"] += 5
        reasons["mermaid"].append("relations require deterministic graph syntax")

    if intent == "knowledge_map" or requirements["free_spatial_layout"]:
        scores["canvas"] += 8
        reasons["canvas"].append("free spatial exploration is required")
    if group_count >= 2 or node_count >= 8:
        scores["canvas"] += 4
        reasons["canvas"].append("groups or scale benefit from an infinite canvas")
    if requirements["portable_offline"]:
        scores["canvas"] += 3
        reasons["canvas"].append("portable offline composition is required")

    if intent == "presentation" or requirements["presentation"]:
        scores["miro_native"] += 8
        reasons["miro_native"].append("a controlled presentation path is required")
    if requirements["collaboration"]:
        scores["miro_native"] += 5
        reasons["miro_native"].append("editable collaborative objects are required")
    if intent in {"mixed", "knowledge_map", "architecture"}:
        scores["miro_native"] += 3
        reasons["miro_native"].append("Miro can integrate overview and detail surfaces")

    if intent == "comparison" or requirements["structured_comparison"]:
        scores["table"] += 8
        reasons["table"].append("the information is a structured comparison")
    if any(node["kind"] in {"decision", "risk"} for node in normalized["nodes"]):
        scores["table"] += 2
        reasons["table"].append("decision and risk inventories benefit from tabular review")

    if intent == "narrative" or requirements["rich_text"]:
        scores["document"] += 8
        reasons["document"].append("long-form explanation is required")
    if any(len(node["summary"]) > 140 for node in normalized["nodes"]):
        scores["document"] += 3
        reasons["document"].append("node explanations exceed diagram-label density")

    if intent == "mixed":
        for name in ("mermaid", "canvas", "miro_native", "document"):
            scores[name] += 4
            reasons[name].append("mixed intent requires complementary representations")

    requested = set(normalized["requested_formats"])
    for name in requested:
        scores[name] += 100
        reasons[name].append("explicitly requested")

    selected = sorted(name for name, score in scores.items() if score >= 5)
    if not selected:
        selected = ["document"]
        scores["document"] = 5
        reasons["document"].append("fallback preserves readable content")
    ranked = sorted(selected, key=lambda name: (-scores[name], name))
    primary = ranked[0]
    decisions = {
        name: {
            "selected": name in ranked,
            "score": scores[name],
            "threshold": 5,
            "reasons": reasons[name] or ["score below selection threshold"],
        }
        for name in sorted(scores)
    }
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "input_digest": normalized["input_digest"],
        "intent": intent,
        "primary_format": primary,
        "selected_formats": ranked,
        "hybrid": len(ranked) > 1,
        "scores": {name: scores[name] for name in sorted(scores)},
        "reasons": {name: reasons[name] for name in ranked},
        "decisions": decisions,
        "profiles": {
            "mermaid": MERMAID_PROFILE,
            "canvas": JSON_CANVAS_PROFILE,
            "miro_native": MIRO_PROFILE,
        },
        "does_not_establish": [
            "aesthetic_quality",
            "provider_rendering_without_live_readback",
            "semantic_truth_of_source_claims",
        ],
    }
    plan["plan_digest"] = _digest(plan)
    return plan


def _validate_route_plan(
    normalized: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise RepresentationError("route plan must be an object")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise RepresentationError(f"route plan schema_version must be {PLAN_SCHEMA}")
    if plan.get("input_digest") != normalized["input_digest"]:
        raise RepresentationError("route plan is bound to another representation input")
    supplied_digest = plan.get("plan_digest")
    body = {key: item for key, item in plan.items() if key != "plan_digest"}
    if (
        not isinstance(supplied_digest, str)
        or _SHA256.fullmatch(supplied_digest) is None
        or supplied_digest != _digest(body)
    ):
        raise RepresentationError("route plan digest mismatch")
    expected = route_representation(normalized)
    if _canonical(plan) != _canonical(expected):
        raise RepresentationError("route plan does not match deterministic router decision")
    return dict(plan)


def _mermaid_text(value: str) -> str:
    return (
        value.replace("<", "‹")
        .replace(">", "›")
        .replace('"', "'")
        .replace("|", "¦")
        .replace("`", "'")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _mermaid_node_id(identifier: str) -> str:
    return f"sw_node_{identifier}"


def _mermaid_group_id(identifier: str) -> str:
    return f"sw_group_{identifier}"


def _mermaid_node(node: Mapping[str, Any]) -> str:
    identifier = _mermaid_node_id(str(node["id"]))
    label = _mermaid_text(str(node["label"]))
    kind = str(node["kind"])
    wrappers = {
        "human": ('(["', '"])'),
        "system": ('["', '"]'),
        "service": ('[["', '"]]'),
        "store": ('[("', '")]'),
        "evidence": ('[("', '")]'),
        "decision": ('{"', '"}'),
        "risk": ('{{"', '"}}'),
        "action": ('(["', '"])'),
        "concept": ('("', '")'),
    }
    opening, closing = wrappers[kind]
    return f"{identifier}{opening}{label}{closing}"


_MERMAID_ARROWS = {
    "authority": "==>",
    "flow": "-->",
    "evidence": "-.->",
    "feedback": "-.->",
    "risk": "--x",
    "association": "---",
}

def _mermaid_edge_line(edge: Mapping[str, Any]) -> str:
    label = _mermaid_text(str(edge["label"]))
    return (
        f"{_mermaid_node_id(str(edge['from']))} "
        f"{_MERMAID_ARROWS[str(edge['kind'])]}|{label}| "
        f"{_mermaid_node_id(str(edge['to']))}"
    )


def render_mermaid(model: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    normalized = (
        _validate_representation_model(model)
        if "input_digest" in model
        else validate_representation_input(model)
    )
    plan = _validate_route_plan(normalized, plan)
    direction = "TD" if normalized["intent"] in {"sequence", "timeline", "process"} else "LR"
    lines = [
        f"%% profile: {MERMAID_PROFILE}",
        f"%% input-digest: {normalized['input_digest']}",
        f"flowchart {direction}",
    ]
    grouped: dict[str | None, list[Mapping[str, Any]]] = defaultdict(list)
    for node in normalized["nodes"]:
        grouped[node["group"]].append(node)
    for group in normalized["groups"]:
        lines.append(
            f'  subgraph {_mermaid_group_id(str(group["id"]))}["{_mermaid_text(group["label"])}"]'
        )
        for node in grouped[group["id"]]:
            lines.append(f"    %% source-node-id: {node['id']}")
            lines.append(f"    {_mermaid_node(node)}")
        lines.append("  end")
    for node in grouped[None]:
        lines.append(f"  %% source-node-id: {node['id']}")
        lines.append(f"  {_mermaid_node(node)}")

    for edge in normalized["edges"]:
        lines.append(f"  %% source-edge-id: {edge['id']}")
        lines.append(f"  {_mermaid_edge_line(edge)}")

    class_styles = {
        "human": "fill:#E6F6F8,stroke:#147D92,color:#0B3C49",
        "system": "fill:#F8FAFC,stroke:#52606D,color:#102A43",
        "service": "fill:#F8FAFC,stroke:#52606D,color:#102A43",
        "store": "fill:#EAF8F0,stroke:#2F855A,color:#173B2D",
        "evidence": "fill:#EAF8F0,stroke:#2F855A,color:#173B2D",
        "decision": "fill:#FFF8DD,stroke:#B7791F,color:#3C2F12",
        "risk": "fill:#FFE8E8,stroke:#C53030,color:#4A1010",
        "action": "fill:#FFF8DD,stroke:#B7791F,color:#3C2F12",
        "concept": "fill:#F8FAFC,stroke:#BCCCDC,color:#102A43",
    }
    for kind, style in class_styles.items():
        lines.append(f"  classDef {kind} {style};")
    for node in normalized["nodes"]:
        lines.append(f"  class {_mermaid_node_id(str(node['id']))} {node['kind']};")
    lines.append(f"%% route-plan-digest: {plan['plan_digest']}")
    return "\n".join(lines) + "\n"




def _canvas_node_id(source_id: str) -> str:
    return f"canvas_node:{source_id}"


def _canvas_edge_id(source_id: str) -> str:
    return f"canvas_edge:{source_id}"


def _canvas_group_id(source_id: str) -> str:
    return f"canvas_group:{source_id}"

def render_json_canvas(model: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    normalized = (
        _validate_representation_model(model)
        if "input_digest" in model
        else validate_representation_input(model)
    )
    _validate_route_plan(normalized, plan)
    nodes_by_group: dict[str | None, list[Mapping[str, Any]]] = defaultdict(list)
    for node in normalized["nodes"]:
        nodes_by_group[node["group"]].append(node)
    group_order = [group["id"] for group in normalized["groups"]]
    if nodes_by_group[None]:
        group_order.append(None)

    canvas_nodes: list[dict[str, Any]] = []
    positions: dict[str, tuple[int, int]] = {}
    color_by_kind = {
        "human": "4",
        "system": "6",
        "service": "6",
        "store": "5",
        "evidence": "5",
        "decision": "3",
        "risk": "1",
        "action": "3",
        "concept": "2",
    }
    for column, group_id in enumerate(group_order):
        members = nodes_by_group[group_id]
        base_x = column * 520
        base_y = 100
        if group_id is not None:
            height = max(360, 140 + len(members) * 220)
            label = next(
                group["label"] for group in normalized["groups"] if group["id"] == group_id
            )
            canvas_nodes.append(
                {
                    "id": _canvas_group_id(str(group_id)),
                    "type": "group",
                    "x": base_x,
                    "y": 0,
                    "width": 440,
                    "height": height,
                    "label": label,
                }
            )
        for row, node in enumerate(members):
            x = base_x + 40
            y = base_y + row * 210
            positions[node["id"]] = (x, y)
            summary = f"\n\n{node['summary']}" if node["summary"] else ""
            canvas_nodes.append(
                {
                    "id": _canvas_node_id(str(node["id"])),
                    "type": "text",
                    "text": f"# {node['label']}{summary}",
                    "x": x,
                    "y": y,
                    "width": 360,
                    "height": 150,
                    "color": color_by_kind[node["kind"]],
                }
            )

    edge_colors = {
        "authority": "4",
        "flow": "6",
        "evidence": "5",
        "feedback": "3",
        "risk": "1",
        "association": "2",
    }
    canvas_edges: list[dict[str, Any]] = []
    for edge in normalized["edges"]:
        source_x, source_y = positions[edge["from"]]
        target_x, target_y = positions[edge["to"]]
        if edge["from"] == edge["to"]:
            from_side, to_side = "right", "top"
        elif source_x == target_x:
            if source_y <= target_y:
                from_side, to_side = "bottom", "top"
            else:
                from_side, to_side = "top", "bottom"
        elif source_x < target_x:
            from_side, to_side = "right", "left"
        else:
            from_side, to_side = "left", "right"
        canvas_edges.append(
            {
                "id": _canvas_edge_id(str(edge["id"])),
                "fromNode": _canvas_node_id(str(edge["from"])),
                "fromSide": from_side,
                "toNode": _canvas_node_id(str(edge["to"])),
                "toSide": to_side,
                "toEnd": "none" if edge["kind"] == "association" else "arrow",
                "label": edge["label"],
                "color": edge_colors[edge["kind"]],
            }
        )
    return {"nodes": canvas_nodes, "edges": canvas_edges}


def _miro_role(kind: str) -> tuple[str, str]:
    if kind == "human":
        return "orientation", "structure"
    if kind in {"store", "evidence"}:
        return "evidence", "evidence"
    if kind == "decision":
        return "decision", "decision"
    if kind == "risk":
        return "risk", "risk"
    if kind == "action":
        return "action", "decision"
    return "entity", "structure"


def _miro_node_object_id(source_id: str) -> str:
    return f"source_node_{source_id}"


def _miro_edge_object_id(source_id: str) -> str:
    return f"source_edge_{source_id}"


def _frame_nodes(
    frame_id: str,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Lay out a readable four-node relation strip without inventing semantics.

    Miro positions connector captions independently of node geometry. Relation
    text therefore lives in one bounded legend while connectors remain semantic
    but unlabelled. Source identities are carried as metadata and renderer-local
    ids live in a disjoint namespace so decorative objects cannot impersonate
    source coverage.
    """

    result: list[dict[str, Any]] = []
    selected = list(nodes[:4])
    selected_ids = {str(node["id"]) for node in selected}
    labels = {str(node["id"]): str(node["label"]) for node in selected}
    for index, node in enumerate(selected):
        source_id = str(node["id"])
        role, color = _miro_role(str(node["kind"]))
        rendered = shape_object(
            _miro_node_object_id(source_id),
            role,
            80 + index * 360,
            340,
            240,
            140,
            str(node["label"]),
            color=color,
        )
        rendered["source_kind"] = "node"
        rendered["source_id"] = source_id
        result.append(rendered)

    relevant_edges = [
        edge
        for edge in edges
        if str(edge["from"]) in selected_ids and str(edge["to"]) in selected_ids
    ]
    connector_room = min(2, max(0, 7 - len(result)))
    relation_rows: list[str] = []
    self_loop_index = 0
    processed_edge_count = min(2, len(relevant_edges))
    for edge in relevant_edges[:processed_edge_count]:
        source_id = str(edge["from"])
        target_id = str(edge["to"])
        source_label = clip_text(labels[source_id], 28)
        target_label = clip_text(labels[target_id], 28)
        relation_label = clip_text(str(edge["label"]), 36)
        if source_id == target_id:
            loop = text_object(
                _miro_edge_object_id(str(edge["id"])),
                "caption",
                80,
                500 + self_loop_index * 60,
                620,
                40,
                f"{source_label} ↺: {relation_label}",
                font="caption",
            )
            loop["relation_type"] = edge["kind"]
            loop["source_kind"] = "edge"
            loop["source_id"] = str(edge["id"])
            result.append(loop)
            self_loop_index += 1
            continue
        if connector_room:
            connector = connector_object(
                _miro_edge_object_id(str(edge["id"])),
                _miro_node_object_id(source_id),
                _miro_node_object_id(target_id),
                "→",
            )
            connector["relation_type"] = edge["kind"]
            connector["source_kind"] = "edge"
            connector["source_id"] = str(edge["id"])
            result.append(connector)
            connector_room -= 1
        relation_rows.append(f"{source_label} → {target_label}: {relation_label}")

    omitted = len(relevant_edges) - processed_edge_count
    if relation_rows or omitted > 0:
        separator = " · "
        rows_text = separator.join(relation_rows)
        if omitted > 0:
            notice = f"+{omitted} weitere Beziehungen"
            if rows_text:
                row_budget = 220 - len(separator) - len(notice)
                legend = f"{clip_text(rows_text, row_budget)}{separator}{notice}"
            else:
                legend = notice
        else:
            legend = clip_text(rows_text, 220)
        result.append(
            text_object(
                f"{frame_id}_relations",
                "caption",
                80,
                260,
                1360,
                60,
                legend,
                font="caption",
            )
        )
    if not result:
        result.append(
            text_object(
                f"{frame_id}_empty",
                "caption",
                80,
                300,
                900,
                80,
                "Keine darstellbaren Elemente.",
                font="caption",
            )
        )
    return result

def render_miro_board(model: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    normalized = (
        _validate_representation_model(model)
        if "input_digest" in model
        else validate_representation_input(model)
    )
    plan = _validate_route_plan(normalized, plan)
    nodes = normalized["nodes"]
    edges = normalized["edges"]
    frames = [
        frame(
            "route_cover",
            1,
            "cover",
            normalized["title"],
            "Ein Inhalt, mehrere begründete Darstellungen.",
            0,
        ),
        frame(
            "route_map",
            2,
            "map",
            "Kanonische Übersicht",
            "Die Kernelemente bleiben über alle Renderer hinweg identisch adressierbar.",
            1240,
        ),
        frame(
            "route_architecture",
            3,
            "architecture",
            "Formales Modell",
            "Beziehungen tragen Bedeutung und werden nicht nur beschriftet.",
            2480,
        ),
        frame(
            "route_decision",
            4,
            "decision",
            "Darstellungsentscheidung",
            "Der Router erklärt, warum ein Format gewählt oder verworfen wurde.",
            3720,
        ),
        frame(
            "route_delivery",
            5,
            "delivery",
            "Ausgabepaket",
            "Mermaid, Canvas und Miro ergänzen sich statt einander zu ersetzen.",
            4960,
        ),
        frame(
            "route_evidence",
            6,
            "evidence",
            "Beleg und Grenzen",
            "Digests beweisen Identität; Ästhetik bleibt eine getrennte Prüfung.",
            6200,
        ),
    ]
    for index, item in enumerate(frames):
        item["x"] = index * 1640
        item["w"] = 1520
        item["h"] = 760

    frames[0]["objects"].append(
        shape_object(
            "route_entry",
            "orientation",
            380,
            300,
            360,
            140,
            f"Primär: {plan['primary_format']}",
            color="structure",
        )
    )
    frames[1]["objects"].extend(_frame_nodes("route_map", nodes[:4], edges))
    frames[2]["objects"].extend(_frame_nodes("route_architecture", nodes[4:8], edges))
    route_rows = tuple(
        (
            name,
            "primär" if name == plan["primary_format"] else "ergänzend",
            str(plan["reasons"][name][0])[:72],
        )
        for name in plan["selected_formats"][:5]
    )
    for index, (name, role, reason) in enumerate(route_rows):
        frames[3]["objects"].append(
            shape_object(
                f"route_choice_{index + 1}",
                "decision",
                80 + (index % 3) * 480,
                300 + (index // 3) * 180,
                400,
                120,
                f"{name}\n{role} · {reason}",
                color="decision",
                shape="rhombus",
            )
        )
    for index, name in enumerate(plan["selected_formats"][:4]):
        frames[4]["objects"].append(
            shape_object(
                f"delivery_{name}",
                "action",
                80 + index * 360,
                300,
                280,
                140,
                name,
                color="decision",
            )
        )
    for index, node in enumerate(nodes[8:10]):
        source_id = str(node["id"])
        role, color = _miro_role(str(node["kind"]))
        rendered = shape_object(
            _miro_node_object_id(source_id),
            role,
            160 + index * 600,
            520,
            520,
            100,
            str(node["label"]),
            color=color,
        )
        rendered["source_kind"] = "node"
        rendered["source_id"] = source_id
        frames[4]["objects"].append(rendered)
    materialized = _miro_coverage(normalized, {"frames": frames})
    evidence_summary = (
        "Repräsentationspaket\n"
        f"Eingabe {normalized['input_digest'][:12]}… · Plan {plan['plan_digest'][:12]}…\n"
        f"Miro-Auszug {materialized['node_count']}/{len(nodes)} Knoten · "
        f"{materialized['edge_count']}/{len(edges)} Beziehungen\n"
        "Identität geprüft; vollständige Semantik bleibt im Paket. "
        "Visuelle Freigabe separat."
    )
    frames[5]["objects"].append(
        shape_object(
            "route_evidence_card",
            "evidence",
            80,
            300,
            1360,
            300,
            evidence_summary,
            color="evidence",
            shape="can",
        )
    )
    return finalize_board_spec(
        title=normalized["title"],
        purpose=normalized["purpose"],
        frames=frames,
    )


def _reject_output_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    for component in reversed([candidate, *candidate.parents]):
        try:
            is_symlink = component.is_symlink()
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                raise RepresentationError(
                    "representation output target name is too long"
                ) from exc
            raise
        if is_symlink:
            raise RepresentationError("representation output path must not contain symlinks")


def _close_fd_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


class _OwnedArtifactLedger(dict[str, int]):
    def __init__(self) -> None:
        super().__init__()
        self.integrity: dict[str, tuple[int, str]] = {}

    def record(self, name: str, descriptor: int, payload: bytes) -> None:
        self[name] = descriptor
        self.integrity[name] = (len(payload), hashlib.sha256(payload).hexdigest())


def _write_payload_at(
    output_fd: int,
    name: str,
    payload: bytes,
    *,
    owned_fds: dict[str, int] | None = None,
) -> None:
    if not name or Path(name).name != name:
        raise RepresentationError("representation artifact name must be one safe path component")
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=output_fd)
    retained = False
    if owned_fds is not None:
        if name in owned_fds:
            _close_fd_quietly(descriptor)
            raise RepresentationError("representation artifact ownership ledger is inconsistent")
        if isinstance(owned_fds, _OwnedArtifactLedger):
            owned_fds.record(name, descriptor, payload)
        else:
            owned_fds[name] = descriptor
        retained = True
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short representation artifact write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if not retained:
            _close_fd_quietly(descriptor)


def _write_text(
    output_fd: int,
    name: str,
    content: str,
    *,
    owned_fds: dict[str, int] | None = None,
) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    _write_payload_at(output_fd, name, encoded, owned_fds=owned_fds)
    return {"path": name, "bytes": len(encoded), "sha256": _text_digest(content)}


def _write_json(
    output_fd: int,
    name: str,
    value: Mapping[str, Any],
    *,
    owned_fds: dict[str, int] | None = None,
) -> dict[str, Any]:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = content.encode("utf-8")
    _write_payload_at(output_fd, name, encoded, owned_fds=owned_fds)
    return {"path": name, "bytes": len(encoded), "sha256": _text_digest(content)}


def _coverage(
    *,
    model: Mapping[str, Any],
    node_ids: Sequence[str],
    edge_ids: Sequence[str],
) -> dict[str, Any]:
    source_nodes = {str(node["id"]) for node in model["nodes"]}
    source_edges = {str(edge["id"]) for edge in model["edges"]}
    covered_nodes = sorted(set(node_ids) & source_nodes)
    covered_edges = sorted(set(edge_ids) & source_edges)
    return {
        "node_ids": covered_nodes,
        "edge_ids": covered_edges,
        "node_count": len(covered_nodes),
        "edge_count": len(covered_edges),
        "complete_nodes": set(covered_nodes) == source_nodes,
        "complete_edges": set(covered_edges) == source_edges,
        "coverage_kind": "source_id_materialization",
    }


def _mermaid_coverage(model: Mapping[str, Any], source: str) -> dict[str, Any]:
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        node_prefix = "%% source-node-id: "
        edge_prefix = "%% source-edge-id: "
        if stripped.startswith(node_prefix):
            node_ids.append(stripped[len(node_prefix) :])
        elif stripped.startswith(edge_prefix):
            edge_ids.append(stripped[len(edge_prefix) :])
    return _coverage(model=model, node_ids=node_ids, edge_ids=edge_ids)


def _canvas_coverage(model: Mapping[str, Any], canvas: Mapping[str, Any]) -> dict[str, Any]:
    node_prefix = "canvas_node:"
    edge_prefix = "canvas_edge:"
    node_ids = [
        str(item["id"])[len(node_prefix) :]
        for item in canvas.get("nodes", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and str(item["id"]).startswith(node_prefix)
    ]
    edge_ids = [
        str(item["id"])[len(edge_prefix) :]
        for item in canvas.get("edges", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and str(item["id"]).startswith(edge_prefix)
    ]
    return _coverage(model=model, node_ids=node_ids, edge_ids=edge_ids)


def _miro_coverage(model: Mapping[str, Any], board: Mapping[str, Any]) -> dict[str, Any]:
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for current_frame in board["frames"]:
        for item in current_frame["objects"]:
            source_kind = item.get("source_kind")
            source_id = item.get("source_id")
            if source_kind == "node" and isinstance(source_id, str):
                node_ids.append(source_id)
            elif source_kind == "edge" and isinstance(source_id, str):
                edge_ids.append(source_id)
    return _coverage(model=model, node_ids=node_ids, edge_ids=edge_ids)


def _compile_representation_package_into(
    *, input_path: Path, output_fd: int, owned_fds: dict[str, int]
) -> dict[str, Any]:
    model = load_representation_input(input_path)
    plan = route_representation(model)
    all_node_ids = [str(node["id"]) for node in model["nodes"]]
    all_edge_ids = [str(edge["id"]) for edge in model["edges"]]
    artifacts: list[dict[str, Any]] = []
    mermaid_source: str | None = None
    layout_dsl: str | None = None
    document_source: str | None = None
    public_input = {key: model[key] for key in _PUBLIC_ROOT_FIELDS}
    artifacts.append(
        {
            "role": "normalized_input",
            **_write_json(
                output_fd, "input.json", public_input, owned_fds=owned_fds
            ),
        }
    )
    artifacts.append(
        {
            "role": "route_plan",
            **_write_json(
                output_fd, "route-plan.json", plan, owned_fds=owned_fds
            ),
        }
    )

    if "mermaid" in plan["selected_formats"]:
        mermaid_source = render_mermaid(model, plan)
        artifacts.append(
            {
                "role": "mermaid_source",
                "coverage": _mermaid_coverage(model, mermaid_source),
                **_write_text(output_fd, "diagram.mmd", mermaid_source, owned_fds=owned_fds),
            }
        )
    if "canvas" in plan["selected_formats"]:
        canvas = render_json_canvas(model, plan)
        artifacts.append(
            {
                "role": "json_canvas",
                "coverage": _canvas_coverage(model, canvas),
                **_write_json(output_fd, "composition.canvas", canvas, owned_fds=owned_fds),
            }
        )
    if "miro_native" in plan["selected_formats"]:
        execution_plan = compile_miro_execution_plan(model, plan)
        artifacts.append(
            {
                "role": "miro_execution_plan",
                **_write_json(
                    output_fd,
                    "miro-execution-plan.json",
                    execution_plan,
                    owned_fds=owned_fds,
                ),
            }
        )
        board = render_miro_board(model, plan)
        quality = validate_board_spec(board)
        layout_dsl = render_board_dsl(board)
        miro_coverage = _miro_coverage(model, board)
        artifacts.append(
            {
                "role": "miro_board_spec",
                "coverage": miro_coverage,
                **_write_json(output_fd, "miro-board.json", board, owned_fds=owned_fds),
            }
        )
        artifacts.append(
            {
                "role": "miro_layout_dsl",
                **_write_text(output_fd, "miro-board.dsl", layout_dsl, owned_fds=owned_fds),
            }
        )
        artifacts.append(
            {
                "role": "miro_quality",
                **_write_json(
                    output_fd, "miro-quality.json", quality, owned_fds=owned_fds
                ),
            }
        )
    if "document" in plan["selected_formats"]:
        document_source = render_representation_document(model)
        artifacts.append(
            {
                "role": "narrative_document",
                "coverage": _coverage(model=model, node_ids=[], edge_ids=[]),
                **_write_text(output_fd, "overview.md", document_source, owned_fds=owned_fds),
            }
        )
    if "table" in plan["selected_formats"]:
        artifacts.append(
            {
                "role": "node_table",
                "coverage": _coverage(model=model, node_ids=all_node_ids, edge_ids=[]),
                **_write_text(
                    output_fd,
                    "nodes.tsv",
                    render_representation_table(model),
                    owned_fds=owned_fds,
                ),
            }
        )

    native_bundle = compile_representation_native_bundle(
        model,
        plan,
        layout_dsl=layout_dsl,
        mermaid_source=mermaid_source,
        document_source=document_source,
    )
    if native_bundle is not None:
        artifacts.append(
            {
                "role": "miro_native_bundle",
                **_write_json(
                    output_fd,
                    "miro-native-bundle.json",
                    native_bundle,
                    owned_fds=owned_fds,
                ),
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": PACKAGE_SCHEMA,
        "input_id": model["id"],
        "input_digest": model["input_digest"],
        "plan_digest": plan["plan_digest"],
        "primary_format": plan["primary_format"],
        "selected_formats": plan["selected_formats"],
        "hybrid": plan["hybrid"],
        "artifacts": artifacts,
        "source_ids": {
            "node_ids": sorted(all_node_ids),
            "edge_ids": sorted(all_edge_ids),
        },
        "identity_contract": _IDENTITY_CONTRACT,
        "does_not_establish": plan["does_not_establish"],
    }
    manifest["package_digest"] = _digest(manifest)
    manifest_artifact = _write_json(output_fd, "manifest.json", manifest, owned_fds=owned_fds)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "input_digest": model["input_digest"],
        "plan_digest": plan["plan_digest"],
        "package_digest": manifest["package_digest"],
        "manifest_sha256": manifest_artifact["sha256"],
        "artifact_count": len(artifacts) + 1,
        "selected_formats": plan["selected_formats"],
        "primary_format": plan["primary_format"],
        "hybrid": plan["hybrid"],
        "mutation_attempted": False,
        "ok": True,
    }
    receipt["receipt_digest"] = _digest(receipt)
    _write_json(output_fd, "receipt.json", receipt, owned_fds=owned_fds)
    os.fsync(output_fd)
    return receipt


def _safe_parent_snapshot(path: Path) -> os.stat_result:
    current = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode):
        raise RepresentationError("representation output parent is not a directory")
    owner_private = current.st_uid == os.getuid() and not current.st_mode & 0o022
    root_sticky = (
        current.st_uid == 0
        and bool(current.st_mode & stat.S_ISVTX)
        and bool(current.st_mode & 0o002)
    )
    if not (owner_private or root_sticky):
        raise RepresentationError("representation output parent is unsafe")
    return current


def _same_path_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
        and left.st_gid == right.st_gid
    )


def _target_must_be_absent(parent_fd: int, target_name: str) -> None:
    try:
        os.stat(target_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        if exc.errno == errno.ENAMETOOLONG:
            raise RepresentationError(
                "representation output target name is too long"
            ) from exc
        raise
    raise RepresentationError("representation output target must be absent")


def _rename_noreplace(parent_fd: int, source_name: str, target_name: str) -> None:
    """Publish one directory atomically without replacing a concurrent target."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RepresentationError("atomic no-replace directory publication is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source_name),
        parent_fd,
        os.fsencode(target_name),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise RepresentationError("representation output target appeared while publishing")
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise RepresentationError("atomic no-replace directory publication is unavailable")
    raise OSError(error_number, os.strerror(error_number), target_name)


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _create_private_staging(
    parent_fd: int, target_name: str
) -> tuple[str, int, os.stat_result]:
    try:
        name_max = os.fpathconf(parent_fd, "PC_NAME_MAX")
    except (OSError, ValueError):
        name_max = -1
    staging_probe = f".{target_name}.tmp-{'0' * 16}"
    if name_max > 0 and len(os.fsencode(staging_probe)) > name_max:
        raise RepresentationError(
            "representation output target name is too long for private staging"
        )
    for _ in range(64):
        staging_name = f".{target_name}.tmp-{secrets.token_hex(8)}"
        try:
            os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                raise RepresentationError(
                    "representation output target name is too long for private staging"
                ) from exc
            raise
        staging_fd: int | None = None
        try:
            staging_fd = os.open(
                staging_name, _directory_open_flags(), dir_fd=parent_fd
            )
            os.fchmod(staging_fd, 0o700)
            opened = os.fstat(staging_fd)
            linked = os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not _same_path_identity(opened, linked)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o700
                or opened.st_nlink < 1
            ):
                raise RepresentationError("representation staging directory is unsafe")
            os.fsync(parent_fd)
            return staging_name, staging_fd, opened
        except BaseException:
            if staging_fd is not None:
                _close_fd_quietly(staging_fd)
            # Directory-name deletion cannot be made inode-conditional here.
            # Leave an empty private tombstone rather than risk deleting a substitute.
            raise
    raise RepresentationError("could not allocate a private representation staging directory")


def _digest_open_fd(descriptor: int, expected_size: int) -> str | None:
    digest = hashlib.sha256()
    offset = 0
    try:
        while offset < expected_size:
            chunk = os.pread(
                descriptor, min(1024 * 1024, expected_size - offset), offset
            )
            if not chunk:
                return None
            digest.update(chunk)
            offset += len(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _verify_bound_artifacts(
    directory_fd: int, owned_fds: _OwnedArtifactLedger
) -> bool:
    if set(owned_fds) != set(owned_fds.integrity):
        return False
    try:
        observed_names = set(os.listdir(directory_fd))
    except OSError:
        return False
    if observed_names != set(owned_fds):
        return False
    for name, descriptor in owned_fds.items():
        expected_size, expected_digest = owned_fds.integrity[name]
        try:
            owned = os.fstat(descriptor)
            linked = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError:
            return False
        if (
            not stat.S_ISREG(owned.st_mode)
            or not _same_path_identity(owned, linked)
            or owned.st_size != expected_size
            or linked.st_size != expected_size
            or _digest_open_fd(descriptor, expected_size) != expected_digest
        ):
            return False
    return True


def _cleanup_bound_directory(
    parent_fd: int,
    name: str,
    directory_fd: int,
    expected: os.stat_result,
    owned_fds: Mapping[str, int],
) -> tuple[bool, bool]:
    """Scrub only invocation-owned file inodes; never unlink a mutable name."""

    scrubbed_all = True
    for descriptor in owned_fds.values():
        try:
            artifact = os.fstat(descriptor)
            if not stat.S_ISREG(artifact.st_mode):
                scrubbed_all = False
                continue
            os.ftruncate(descriptor, 0)
            os.fsync(descriptor)
        except OSError:
            scrubbed_all = False
    try:
        os.fsync(directory_fd)
    except OSError:
        scrubbed_all = False

    try:
        opened = os.fstat(directory_fd)
    except OSError:
        namespace_clean = False
    else:
        namespace_clean = _same_path_identity(expected, opened)
    try:
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        namespace_clean = False
    else:
        namespace_clean = _same_path_identity(expected, linked)

    try:
        observed_names = set(os.listdir(directory_fd))
    except OSError:
        namespace_clean = False
        observed_names = set()
    if observed_names != set(owned_fds):
        namespace_clean = False

    for artifact_name, descriptor in owned_fds.items():
        try:
            bound = os.stat(artifact_name, dir_fd=directory_fd, follow_symlinks=False)
            owned = os.fstat(descriptor)
        except OSError:
            namespace_clean = False
            continue
        if not _same_path_identity(owned, bound) or bound.st_size != 0:
            namespace_clean = False

    return scrubbed_all, namespace_clean


def _clear_bound_directory(
    parent_fd: int,
    name: str,
    directory_fd: int,
    expected: os.stat_result,
    owned_fds: Mapping[str, int],
) -> str:
    """Best-effort scrub that never masks the fault which triggered cleanup."""

    try:
        scrubbed_all, namespace_clean = _cleanup_bound_directory(
            parent_fd, name, directory_fd, expected, owned_fds
        )
    except Exception:
        return "bound compiler bytes could not be scrubbed completely"
    if not scrubbed_all:
        return "bound compiler bytes could not be scrubbed completely"
    if namespace_clean:
        return (
            "bound compiler bytes were scrubbed; zero-length private tombstone "
            "entries may remain"
        )
    return (
        "bound compiler bytes were scrubbed; concurrent entries or name changes "
        "were preserved"
    )


def compile_representation_package(*, input_path: Path, output_dir: Path) -> dict[str, Any]:
    """Compile through fd-bound private staging and publish with NOREPLACE."""

    target = output_dir.expanduser().absolute()
    _reject_output_symlink_chain(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_output_symlink_chain(target)
    parent_before = _safe_parent_snapshot(target.parent)
    parent_fd = os.open(target.parent, _directory_open_flags())
    staging_name: str | None = None
    staging_fd: int | None = None
    staging_before: os.stat_result | None = None
    owned_fds = _OwnedArtifactLedger()
    published = False
    try:
        parent_opened = os.fstat(parent_fd)
        if not _same_path_identity(parent_before, parent_opened):
            raise RepresentationError("representation output parent identity changed")
        _target_must_be_absent(parent_fd, target.name)

        staging_name, staging_fd, staging_before = _create_private_staging(
            parent_fd, target.name
        )
        receipt = _compile_representation_package_into(
            input_path=input_path, output_fd=staging_fd, owned_fds=owned_fds
        )
        if not _verify_bound_artifacts(staging_fd, owned_fds):
            raise RepresentationError(
                "representation staging artifact integrity changed before publication"
            )

        parent_path_before_publish = _safe_parent_snapshot(target.parent)
        parent_opened_before_publish = os.fstat(parent_fd)
        if (
            not _same_path_identity(parent_before, parent_path_before_publish)
            or not _same_path_identity(parent_before, parent_opened_before_publish)
        ):
            raise RepresentationError("representation output parent identity changed")
        staging_opened = os.fstat(staging_fd)
        staging_linked = os.stat(
            staging_name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            not _same_path_identity(staging_before, staging_opened)
            or not _same_path_identity(staging_before, staging_linked)
        ):
            raise RepresentationError("representation staging identity changed")
        _target_must_be_absent(parent_fd, target.name)

        _rename_noreplace(parent_fd, staging_name, target.name)
        published = True

        try:
            published_stat = os.stat(
                target.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError:
            published_readback_ok = False
        else:
            published_readback_ok = (
                _same_path_identity(staging_before, published_stat)
                and _verify_bound_artifacts(staging_fd, owned_fds)
            )
        if not published_readback_ok:
            outcome = _clear_bound_directory(
                parent_fd, target.name, staging_fd, staging_before, owned_fds
            )
            published = False
            staging_name = None
            raise RepresentationError(
                "published representation package identity could not be verified; "
                f"{outcome}"
            )
        try:
            parent_path_after_publish = _safe_parent_snapshot(target.parent)
            parent_opened_after_publish = os.fstat(parent_fd)
        except (OSError, RepresentationError):
            parent_readback_ok = False
        else:
            parent_readback_ok = (
                _same_path_identity(parent_before, parent_path_after_publish)
                and _same_path_identity(parent_before, parent_opened_after_publish)
            )
        if not parent_readback_ok:
            outcome = _clear_bound_directory(
                parent_fd, target.name, staging_fd, staging_before, owned_fds
            )
            published = False
            staging_name = None
            raise RepresentationError(
                "representation output parent identity changed during publication; "
                f"{outcome}"
            )
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            outcome = _clear_bound_directory(
                parent_fd, target.name, staging_fd, staging_before, owned_fds
            )
            published = False
            staging_name = None
            raise RepresentationError(
                "representation package publication durability sync failed; "
                f"{outcome}"
            ) from exc

        try:
            final_parent_path = _safe_parent_snapshot(target.parent)
            final_parent_opened = os.fstat(parent_fd)
            final_target_path = target.stat(follow_symlinks=False)
            final_target_bound = os.stat(
                target.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except (OSError, RepresentationError):
            final_readback_ok = False
        else:
            final_readback_ok = (
                _same_path_identity(parent_before, final_parent_path)
                and _same_path_identity(parent_before, final_parent_opened)
                and _same_path_identity(staging_before, final_target_path)
                and _same_path_identity(staging_before, final_target_bound)
                and _verify_bound_artifacts(staging_fd, owned_fds)
            )
        if not final_readback_ok:
            outcome = _clear_bound_directory(
                parent_fd, target.name, staging_fd, staging_before, owned_fds
            )
            published = False
            staging_name = None
            raise RepresentationError(
                "representation final publication readback failed after durability sync; "
                f"{outcome}"
            )
        return receipt
    except BaseException:
        if (
            not published
            and staging_name is not None
            and staging_fd is not None
            and staging_before is not None
        ):
            _clear_bound_directory(
                parent_fd, staging_name, staging_fd, staging_before, owned_fds
            )
        raise
    finally:
        for descriptor in owned_fds.values():
            _close_fd_quietly(descriptor)
        if staging_fd is not None:
            _close_fd_quietly(staging_fd)
        _close_fd_quietly(parent_fd)
