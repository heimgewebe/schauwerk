"""Renderer-independent representation router with Mermaid, JSON Canvas and Miro outputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from schauwerk.surfaces.miro.execution_plan import compile_miro_execution_plan

from .composer_v2 import (
    connector_object,
    document_object,
    frame,
    shape_object,
    table_object,
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
from .system_v2 import (
    write_json as write_visual_json,
)
from .system_v2 import (
    write_text as write_visual_text,
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


class RepresentationError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise RepresentationError(f"{field} must be a string")
    text = " ".join(value.split())
    if not text:
        raise RepresentationError(f"{field} must not be empty")
    if len(text) > maximum:
        raise RepresentationError(f"{field} exceeds {maximum} characters")
    return text


def _safe_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RepresentationError(f"{field} must match {_SAFE_ID.pattern}")
    return value


def validate_representation_input(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != INPUT_SCHEMA:
        raise RepresentationError(f"schema_version must be {INPUT_SCHEMA}")
    identifier = _safe_id(value.get("id"), field="id")
    title = _clean_text(value.get("title"), field="title", maximum=160)
    purpose = _clean_text(value.get("purpose"), field="purpose", maximum=500)
    intent = value.get("intent")
    if intent not in _SUPPORTED_INTENTS:
        raise RepresentationError(f"intent must be one of {sorted(_SUPPORTED_INTENTS)}")

    raw_groups = value.get("groups", [])
    if not isinstance(raw_groups, list):
        raise RepresentationError("groups must be a list")
    groups: list[dict[str, str]] = []
    group_ids: set[str] = set()
    for index, raw in enumerate(raw_groups):
        if not isinstance(raw, Mapping):
            raise RepresentationError(f"groups[{index}] must be an object")
        group_id = _safe_id(raw.get("id"), field=f"groups[{index}].id")
        if group_id in group_ids:
            raise RepresentationError(f"duplicate group id: {group_id}")
        group_ids.add(group_id)
        groups.append(
            {
                "id": group_id,
                "label": _clean_text(raw.get("label"), field=f"groups[{index}].label", maximum=100),
            }
        )

    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise RepresentationError("nodes must be a non-empty list")
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, Mapping):
            raise RepresentationError(f"nodes[{index}] must be an object")
        node_id = _safe_id(raw.get("id"), field=f"nodes[{index}].id")
        if node_id in node_ids:
            raise RepresentationError(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        kind = raw.get("kind")
        if kind not in _SUPPORTED_NODE_KINDS:
            raise RepresentationError(
                f"nodes[{index}].kind must be one of {sorted(_SUPPORTED_NODE_KINDS)}"
            )
        group = raw.get("group")
        if group is not None and group not in group_ids:
            raise RepresentationError(f"nodes[{index}].group references unknown group: {group}")
        summary = raw.get("summary", "")
        if not isinstance(summary, str) or len(summary) > 500:
            raise RepresentationError(
                f"nodes[{index}].summary must be a string up to 500 characters"
            )
        nodes.append(
            {
                "id": node_id,
                "label": _clean_text(raw.get("label"), field=f"nodes[{index}].label", maximum=120),
                "kind": kind,
                "group": group,
                "summary": " ".join(summary.split()),
            }
        )

    raw_edges = value.get("edges", [])
    if not isinstance(raw_edges, list):
        raise RepresentationError("edges must be a list")
    edges: list[dict[str, str]] = []
    edge_ids: set[str] = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, Mapping):
            raise RepresentationError(f"edges[{index}] must be an object")
        edge_id = _safe_id(raw.get("id"), field=f"edges[{index}].id")
        if edge_id in edge_ids:
            raise RepresentationError(f"duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        source = raw.get("from")
        target = raw.get("to")
        if source not in node_ids or target not in node_ids:
            raise RepresentationError(f"edges[{index}] references an unknown node")
        kind = raw.get("kind", "flow")
        if kind not in _SUPPORTED_EDGE_KINDS:
            raise RepresentationError(
                f"edges[{index}].kind must be one of {sorted(_SUPPORTED_EDGE_KINDS)}"
            )
        edges.append(
            {
                "id": edge_id,
                "from": str(source),
                "to": str(target),
                "label": _clean_text(raw.get("label"), field=f"edges[{index}].label", maximum=120),
                "kind": str(kind),
            }
        )

    raw_requirements = value.get("requirements", {})
    if not isinstance(raw_requirements, Mapping):
        raise RepresentationError("requirements must be an object")
    requirements = {
        key: bool(raw_requirements.get(key, False))
        for key in (
            "formal_relations",
            "free_spatial_layout",
            "presentation",
            "collaboration",
            "rich_text",
            "structured_comparison",
            "portable_offline",
        )
    }
    raw_requested = value.get("requested_formats", [])
    if not isinstance(raw_requested, list) or any(
        not isinstance(item, str) or item not in _SUPPORTED_FORMATS for item in raw_requested
    ):
        raise RepresentationError(f"requested_formats must use {sorted(_SUPPORTED_FORMATS)}")
    requested = sorted(set(str(item) for item in raw_requested))

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
    normalized["input_digest"] = _digest(normalized)
    return normalized


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
    normalized = validate_representation_input(model)
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


def _mermaid_node(node: Mapping[str, Any]) -> str:
    identifier = str(node["id"])
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


def render_mermaid(model: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    normalized = validate_representation_input(model)
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
        lines.append(f'  subgraph group_{group["id"]}["{_mermaid_text(group["label"])}"]')
        for node in grouped[group["id"]]:
            lines.append(f"    {_mermaid_node(node)}")
        lines.append("  end")
    for node in grouped[None]:
        lines.append(f"  {_mermaid_node(node)}")

    arrows = {
        "authority": "==>",
        "flow": "-->",
        "evidence": "-.->",
        "feedback": "-.->",
        "risk": "--x",
        "association": "---",
    }
    for edge in normalized["edges"]:
        label = _mermaid_text(edge["label"])
        lines.append(f"  {edge['from']} {arrows[edge['kind']]}|{label}| {edge['to']}")

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
        lines.append(f"  class {node['id']} {node['kind']};")
    lines.append(f"%% route-plan-digest: {plan['plan_digest']}")
    return "\n".join(lines) + "\n"


def render_json_canvas(model: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_representation_input(model)
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
                    "id": f"canvas_group_{group_id}",
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
                    "id": node["id"],
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
        source_x, _ = positions[edge["from"]]
        target_x, _ = positions[edge["to"]]
        from_side = "right" if source_x <= target_x else "left"
        to_side = "left" if source_x <= target_x else "right"
        canvas_edges.append(
            {
                "id": edge["id"],
                "fromNode": edge["from"],
                "fromSide": from_side,
                "toNode": edge["to"],
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


def _frame_nodes(
    frame_id: str,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    selected = list(nodes[:4])
    selected_ids = {node["id"] for node in selected}
    for index, node in enumerate(selected):
        role, color = _miro_role(str(node["kind"]))
        result.append(
            shape_object(
                node["id"],
                role,
                80 + index * 240,
                300,
                200,
                120,
                str(node["label"]),
                color=color,
            )
        )
    room = max(0, 7 - len(result))
    for edge in edges:
        if room == 0:
            break
        if edge["from"] in selected_ids and edge["to"] in selected_ids:
            connector = connector_object(edge["id"], edge["from"], edge["to"], edge["label"])
            connector["relation_type"] = edge["kind"]
            result.append(connector)
            room -= 1
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
    normalized = validate_representation_input(model)
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
    frames[3]["objects"].append(
        table_object(
            "route_matrix",
            "comparison",
            140,
            260,
            800,
            160,
            "Ausgewählte Renderer",
            ("Format", "Rolle", "Begründung"),
            route_rows,
        )
    )
    for index, node in enumerate(nodes[8:10]):
        role, color = _miro_role(str(node["kind"]))
        frames[3]["objects"].append(
            shape_object(
                str(node["id"]),
                role,
                140 + index * 440,
                460,
                360,
                80,
                str(node["label"]),
                color=color,
            )
        )
    for index, name in enumerate(plan["selected_formats"][:4]):
        frames[4]["objects"].append(
            shape_object(
                f"delivery_{name}",
                "action",
                80 + index * 240,
                300,
                200,
                120,
                name,
                color="decision",
            )
        )
    evidence_markdown = (
        "# Repräsentationspaket\n\n"
        f"- Eingabe: `{normalized['input_digest']}`\n"
        f"- Plan: `{plan['plan_digest']}`\n"
        f"- Knoten: {len(nodes)}\n"
        f"- Beziehungen: {len(edges)}\n"
        "- Automatische Gates bewerten Vertrag und Identität, nicht universelle Ästhetik."
    )
    frames[5]["objects"].append(
        document_object("route_evidence_doc", 140, 280, 820, 220, evidence_markdown)
    )
    return finalize_board_spec(
        title=normalized["title"],
        purpose=normalized["purpose"],
        frames=frames,
    )


def _reject_output_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    for component in reversed([candidate, *candidate.parents]):
        if component.exists() and component.is_symlink():
            raise RepresentationError("representation output path must not contain symlinks")


def _write_text(path: Path, content: str) -> dict[str, Any]:
    write_visual_text(path, content)
    encoded = content.encode("utf-8")
    return {"path": path.name, "bytes": len(encoded), "sha256": _text_digest(content)}


def _write_json(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    write_visual_json(path, value)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = content.encode("utf-8")
    return {"path": path.name, "bytes": len(encoded), "sha256": _text_digest(content)}


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
    }


def _miro_coverage(model: Mapping[str, Any], board: Mapping[str, Any]) -> dict[str, Any]:
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for current_frame in board["frames"]:
        for item in current_frame["objects"]:
            if item["kind"] == "connector":
                edge_ids.append(str(item["id"]))
            else:
                node_ids.append(str(item["id"]))
    return _coverage(model=model, node_ids=node_ids, edge_ids=edge_ids)


def compile_representation_package(*, input_path: Path, output_dir: Path) -> dict[str, Any]:
    _reject_output_symlink_chain(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RepresentationError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    model = load_representation_input(input_path)
    plan = route_representation(model)
    all_node_ids = [str(node["id"]) for node in model["nodes"]]
    all_edge_ids = [str(edge["id"]) for edge in model["edges"]]
    full_coverage = _coverage(model=model, node_ids=all_node_ids, edge_ids=all_edge_ids)
    artifacts: list[dict[str, Any]] = []
    mermaid_source: str | None = None
    layout_dsl: str | None = None
    document_source: str | None = None
    artifacts.append({"role": "normalized_input", **_write_json(output_dir / "input.json", model)})
    artifacts.append({"role": "route_plan", **_write_json(output_dir / "route-plan.json", plan)})

    if "mermaid" in plan["selected_formats"]:
        mermaid_source = render_mermaid(model, plan)
        artifacts.append(
            {
                "role": "mermaid_source",
                "coverage": full_coverage,
                **_write_text(output_dir / "diagram.mmd", mermaid_source),
            }
        )
    if "canvas" in plan["selected_formats"]:
        canvas = render_json_canvas(model, plan)
        artifacts.append(
            {
                "role": "json_canvas",
                "coverage": full_coverage,
                **_write_json(output_dir / "composition.canvas", canvas),
            }
        )
    if "miro_native" in plan["selected_formats"]:
        execution_plan = compile_miro_execution_plan(model, plan)
        artifacts.append(
            {
                "role": "miro_execution_plan",
                **_write_json(output_dir / "miro-execution-plan.json", execution_plan),
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
                **_write_json(output_dir / "miro-board.json", board),
            }
        )
        artifacts.append(
            {
                "role": "miro_layout_dsl",
                **_write_text(output_dir / "miro-board.dsl", layout_dsl),
            }
        )
        artifacts.append(
            {"role": "miro_quality", **_write_json(output_dir / "miro-quality.json", quality)}
        )
    if "document" in plan["selected_formats"]:
        document_source = render_representation_document(model)
        artifacts.append(
            {
                "role": "narrative_document",
                "coverage": full_coverage,
                **_write_text(output_dir / "overview.md", document_source),
            }
        )
    if "table" in plan["selected_formats"]:
        artifacts.append(
            {
                "role": "node_table",
                "coverage": _coverage(model=model, node_ids=all_node_ids, edge_ids=[]),
                **_write_text(output_dir / "nodes.tsv", render_representation_table(model)),
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
                **_write_json(output_dir / "miro-native-bundle.json", native_bundle),
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
        "identity_contract": (
            "stable source ids are preserved wherever an item is materialized; "
            "coverage is explicit per renderer artifact"
        ),
        "does_not_establish": plan["does_not_establish"],
    }
    manifest["package_digest"] = _digest(manifest)
    manifest_artifact = _write_json(output_dir / "manifest.json", manifest)
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
    _write_json(output_dir / "receipt.json", receipt)
    return receipt
