"""Small deterministic SVG renderer for Schauwerk representation input."""

from __future__ import annotations

import textwrap
from collections import defaultdict
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

from .grammar import GRAMMAR_SCHEMA_VERSION
from .representation import RepresentationError, validate_representation_input

__all__ = ["render_native_diagram"]

_NODE_WIDTH = 250
_NODE_HEIGHT = 166
_GROUP_WIDTH = 284
_GROUP_GAP = 172
_PROCESS_HORIZONTAL_GAP = 52
_PROCESS_ROW_GAP = 52
_PROCESS_EDGE_GUTTER = 80
_PROCESS_LANE_STEP = 14
_PAGE_MARGIN = 48
_CONTENT_TOP = 140
_ROW_GAP = 52
_EDGE_GUTTER = 128

_NODE_STYLE = {
    "human": ("#e6f6f8", "#147d92", 28),
    "system": ("#f1f5f9", "#475569", 10),
    "service": ("#eaf2ff", "#2563eb", 18),
    "store": ("#eaf8f0", "#2f855a", 10),
    "decision": ("#fff8dd", "#b7791f", 10),
    "risk": ("#ffe8e8", "#c53030", 10),
    "action": ("#fff4d6", "#a16207", 28),
    "evidence": ("#e7f7f3", "#0f766e", 10),
    "concept": ("#f3efff", "#7c3aed", 32),
}

_EDGE_STYLE = {
    "authority": ("#7c3aed", "", 2.2),
    "flow": ("#475569", "", 2.0),
    "evidence": ("#0f766e", "2 4", 2.0),
    "feedback": ("#2563eb", "7 5", 1.8),
    "risk": ("#b91c1c", "4 4", 2.0),
    "association": ("#64748b", "2 6", 1.8),
}

_KIND_LABEL = {
    "human": "MENSCH",
    "system": "SYSTEM",
    "service": "DIENST",
    "store": "SPEICHER",
    "decision": "ENTSCHEIDUNG",
    "risk": "RISIKO",
    "action": "HANDLUNG",
    "evidence": "EVIDENZ",
    "concept": "KONZEPT",
}


def _xml_escape(value: str) -> str:
    """Replace XML 1.0-forbidden code points, then escape markup characters."""

    compatible: list[str] = []
    for character in value:
        codepoint = ord(character)
        allowed = (
            codepoint in {0x09, 0x0A, 0x0D}
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )
        compatible.append(character if allowed else "\uFFFD")
    return escape("".join(compatible), quote=True)


def _reject_unicode_surrogates(value: Any) -> None:
    """Reject surrogate code points before the semantic validator computes its digest."""

    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise RepresentationError(
                    "representation input contains Unicode surrogate code points"
                )
            continue
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            pending.extend(item)


def _normalized_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """Use the existing public validator for both raw and normalized inputs."""

    _reject_unicode_surrogates(value)
    public_value = dict(value)
    has_digest = "input_digest" in public_value
    supplied_digest = public_value.pop("input_digest", None)
    normalized = validate_representation_input(public_value)
    if has_digest and supplied_digest != normalized["input_digest"]:
        raise RepresentationError("input_digest does not match normalized representation input")
    return normalized


def _wrapped(value: str, *, width: int, limit: int) -> list[str]:
    lines = textwrap.wrap(
        value,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
    )
    if not lines:
        return []
    if len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = f"{lines[-1][:-1].rstrip()}…" if lines[-1] else "…"
    return lines


def _estimated_text_width(value: str, *, size: int) -> float:
    """Estimate rendered width conservatively without introducing a font dependency."""

    narrow = set("ilI.,'`:;!|[](){}")
    wide = set("MW@#%&QGmwo")
    units = 0.0
    for character in value:
        if character.isspace():
            units += 0.35
        elif character in narrow:
            units += 0.35
        elif character in wide:
            units += 1.12
        elif ord(character) > 0x7F:
            units += 1.0
        elif character.isupper():
            units += 0.76
        else:
            units += 0.62
    return units * size


def _svg_text_lines(
    lines: Sequence[str],
    *,
    x: float,
    y: float,
    line_height: int,
    size: int,
    weight: int,
    color: str,
    anchor: str = "start",
    max_width: float | None = None,
) -> list[str]:
    if not lines:
        return []
    rendered = [
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        length_limit = (
            f' textLength="{max_width:.1f}" lengthAdjust="spacingAndGlyphs"'
            if max_width is not None and _estimated_text_width(line, size=size) > max_width
            else ""
        )
        rendered.append(
            f'<tspan x="{x:.1f}" dy="{dy}"{length_limit}>{_xml_escape(line)}</tspan>'
        )
    rendered.append("</text>")
    return rendered


def _grouped_process_layout(
    model: Mapping[str, Any],
) -> tuple[
    dict[str, tuple[int, int]],
    list[tuple[str | None, str, int, int, int, int]],
    int,
    int,
] | None:
    """Lay out a safe acyclic grouped process by graph rank."""

    nodes = list(model["nodes"])
    groups = list(model["groups"])
    if not nodes or not groups:
        return None

    node_ids = [str(node["id"]) for node in nodes]
    node_by_id = {str(node["id"]): node for node in nodes}
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    members: dict[str | None, list[str]] = defaultdict(list)
    for node in nodes:
        members[node["group"]].append(str(node["id"]))

    if members[None] or any(not members[str(group["id"])] for group in groups):
        return None

    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for edge in model["edges"]:
        source_id = str(edge["from"])
        target_id = str(edge["to"])
        if str(edge["kind"]) == "feedback" or source_id == target_id:
            continue
        outgoing[source_id].append(edge)
        indegree[target_id] += 1

    ranks = {node_id: 0 for node_id in node_ids}
    ready = sorted(
        (node_id for node_id, degree in indegree.items() if degree == 0),
        key=node_index.__getitem__,
    )
    processed: list[str] = []
    while ready:
        source_id = ready.pop(0)
        processed.append(source_id)
        for edge in outgoing[source_id]:
            target_id = str(edge["to"])
            ranks[target_id] = max(ranks[target_id], ranks[source_id] + 1)
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
                ready.sort(key=node_index.__getitem__)

    if len(processed) != len(node_ids):
        return None

    previous_end = -1
    for group in groups:
        group_ranks = [ranks[node_id] for node_id in members[str(group["id"])]]
        start_rank = min(group_ranks)
        end_rank = max(group_ranks)
        if start_rank <= previous_end:
            return None
        previous_end = end_rank

    buckets: dict[int, list[str]] = defaultdict(list)
    for node_id in node_ids:
        buckets[ranks[node_id]].append(node_id)

    def row_priority(node_id: str) -> tuple[int, int, int]:
        has_progressive_relation = any(
            str(edge["kind"]) not in {"feedback", "risk"}
            and ranks[str(edge["to"])] > ranks[node_id]
            for edge in outgoing[node_id]
        )
        return (
            0 if has_progressive_relation else 1,
            1 if str(node_by_id[node_id]["kind"]) == "risk" else 0,
            node_index[node_id],
        )

    positions: dict[str, tuple[int, int]] = {}
    for rank in sorted(buckets):
        bucket = sorted(buckets[rank], key=row_priority)
        for row, node_id in enumerate(bucket):
            positions[node_id] = (
                _PAGE_MARGIN + 24 + rank * (_NODE_WIDTH + _PROCESS_HORIZONTAL_GAP),
                _CONTENT_TOP + 82 + row * (_NODE_HEIGHT + _PROCESS_ROW_GAP),
            )

    regions: list[tuple[str | None, str, int, int, int, int]] = []
    for group in groups:
        group_id = str(group["id"])
        group_positions = [positions[node_id] for node_id in members[group_id]]
        region_x = min(x for x, _ in group_positions) - 24
        region_right = max(x + _NODE_WIDTH for x, _ in group_positions) + 24
        region_bottom = max(y + _NODE_HEIGHT for _, y in group_positions) + 28
        regions.append(
            (
                group_id,
                str(group["label"]),
                region_x,
                _CONTENT_TOP,
                region_right - region_x,
                region_bottom - _CONTENT_TOP,
            )
        )

    width = max(
        900,
        max(region_x + region_width for _, _, region_x, _, region_width, _ in regions)
        + _PAGE_MARGIN,
    ) + _PROCESS_EDGE_GUTTER
    height = max(
        region_y + region_height
        for _, _, _, region_y, _, region_height in regions
    ) + _PAGE_MARGIN
    return positions, regions, width, height


def _layout(
    model: Mapping[str, Any],
) -> tuple[dict[str, tuple[int, int]], list[tuple[str | None, str, int, int, int, int]], int, int]:
    nodes = model["nodes"]
    groups = model["groups"]
    positions: dict[str, tuple[int, int]] = {}
    regions: list[tuple[str | None, str, int, int, int, int]] = []

    if groups:
        if model["intent"] == "process":
            process_layout = _grouped_process_layout(model)
            if process_layout is not None:
                return process_layout

        members: dict[str | None, list[Mapping[str, Any]]] = defaultdict(list)
        for node in nodes:
            members[node["group"]].append(node)
        columns: list[tuple[str | None, str, list[Mapping[str, Any]]]] = [
            (group["id"], group["label"], members[group["id"]]) for group in groups
        ]
        if members[None]:
            columns.append((None, "Ungruppiert", members[None]))

        maximum_rows = max(1, *(len(column_nodes) for _, _, column_nodes in columns))
        region_height = 64 + maximum_rows * _NODE_HEIGHT + (maximum_rows - 1) * _ROW_GAP + 28
        for column, (group_id, label, column_nodes) in enumerate(columns):
            region_x = _PAGE_MARGIN + column * (_GROUP_WIDTH + _GROUP_GAP)
            regions.append((group_id, label, region_x, _CONTENT_TOP, _GROUP_WIDTH, region_height))
            for row, node in enumerate(column_nodes):
                positions[node["id"]] = (
                    region_x + (_GROUP_WIDTH - _NODE_WIDTH) // 2,
                    _CONTENT_TOP + 56 + row * (_NODE_HEIGHT + _ROW_GAP),
                )
        width = max(
            900,
            _PAGE_MARGIN * 2
            + len(columns) * _GROUP_WIDTH
            + max(0, len(columns) - 1) * _GROUP_GAP,
        ) + _EDGE_GUTTER
        height = _CONTENT_TOP + region_height + _PAGE_MARGIN
        return positions, regions, width, height

    process_like = model["intent"] in {"process", "sequence", "state", "timeline", "narrative"}
    column_count = min(len(nodes), 6 if process_like else 4)
    horizontal_gap = 166 if process_like else 112
    for index, node in enumerate(nodes):
        column = index % column_count
        row = index // column_count
        positions[node["id"]] = (
            _PAGE_MARGIN + column * (_NODE_WIDTH + horizontal_gap),
            _CONTENT_TOP + row * (_NODE_HEIGHT + 70),
        )
    row_count = (len(nodes) + column_count - 1) // column_count
    width = max(
        900,
        _PAGE_MARGIN * 2 + column_count * _NODE_WIDTH + (column_count - 1) * horizontal_gap,
    ) + _EDGE_GUTTER
    height = _CONTENT_TOP + row_count * _NODE_HEIGHT + max(0, row_count - 1) * 70 + _PAGE_MARGIN
    return positions, regions, width, height


def _marker_definitions() -> list[str]:
    lines = ["<defs>"]
    for kind, (color, _, _) in _EDGE_STYLE.items():
        if kind == "association":
            continue
        lines.extend(
            (
                f'<marker id="native-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" '
                'markerWidth="6" markerHeight="6" orient="auto" markerUnits="strokeWidth">',
                f'<path d="M 0 0 L 8 4 L 0 8 L 2 4 Z" fill="{color}"/>',
                "</marker>",
            )
        )
    lines.append("</defs>")
    return lines


def _edge_geometry(
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    self_loop: bool,
    lane: int,
    kind: str,
    canvas_height: int,
    intent: str,
) -> tuple[str, float, float, str]:
    source_x, source_y = source
    target_x, target_y = target
    route = "standard"
    label_offset_x = 0.0
    label_offset_y = 0.0
    if self_loop:
        start_x = source_x + _NODE_WIDTH
        start_y = source_y + _NODE_HEIGHT * 0.35
        end_x = source_x + _NODE_WIDTH
        end_y = source_y + _NODE_HEIGHT * 0.72
        reach = 78 + abs(lane)
        control_one = (start_x + reach, start_y - 44)
        control_two = (end_x + reach, end_y + 44)
    elif kind == "feedback" and source_x > target_x and intent == "process":
        # Process feedback leaves the cards vertically, crosses below every node,
        # then returns vertically. This avoids cutting through branch outcomes.
        route = "feedback-return"
        start_x = source_x + _NODE_WIDTH / 2
        start_y = source_y + _NODE_HEIGHT
        end_x = target_x + _NODE_WIDTH / 2
        end_y = target_y + _NODE_HEIGHT
        baseline_y = canvas_height - 40 + max(-8.0, min(8.0, lane / 2))
        bend = 34.0
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"C {start_x:.1f} {start_y + bend:.1f}, {start_x:.1f} {baseline_y:.1f}, "
            f"{start_x:.1f} {baseline_y:.1f} "
            f"L {end_x:.1f} {baseline_y:.1f} "
            f"C {end_x:.1f} {baseline_y:.1f}, {end_x:.1f} {end_y + bend:.1f}, "
            f"{end_x:.1f} {end_y:.1f}"
        )
        return path, (start_x + end_x) / 2, baseline_y, route
    elif kind == "feedback" and source_x > target_x:
        route = "feedback-return"
        start_x = source_x
        start_y = source_y + _NODE_HEIGHT / 2
        end_x = target_x + _NODE_WIDTH
        end_y = target_y + _NODE_HEIGHT / 2
        baseline_y = canvas_height - _PAGE_MARGIN - 22 + lane
        reach = max(112.0, min(190.0, (start_x - end_x) * 0.18))
        control_one = (start_x, baseline_y)
        control_two = (end_x, baseline_y)
    elif source_x == target_x:
        route = "vertical"
        center_x = source_x + _NODE_WIDTH / 2
        if source_y < target_y:
            start_x = end_x = center_x
            start_y = source_y + _NODE_HEIGHT
            end_y = target_y
        else:
            start_x = end_x = center_x
            start_y = source_y
            end_y = target_y + _NODE_HEIGHT
        distance = abs(end_y - start_y)
        bend = max(28.0, distance * 0.42)
        direction = 1.0 if end_y > start_y else -1.0
        control_one = (center_x, start_y + direction * bend)
        control_two = (center_x, end_y - direction * bend)
        label_offset_x = _NODE_WIDTH / 2 + 100.0
    elif intent == "process" and source_y != target_y:
        route = "process-branch"
        source_center_x = source_x + _NODE_WIDTH / 2
        target_center_x = target_x + _NODE_WIDTH / 2
        if source_y < target_y:
            start_x = source_center_x
            start_y = source_y + _NODE_HEIGHT
            end_x = target_center_x
            end_y = target_y
        else:
            start_x = source_center_x
            start_y = source_y
            end_x = target_center_x
            end_y = target_y + _NODE_HEIGHT
        corridor_y = (start_y + end_y) / 2 + max(-8.0, min(8.0, lane / 2))
        control_one = (start_x, corridor_y)
        control_two = (end_x, corridor_y)
        label_offset_y = -16.0 if source_y < target_y else 16.0
    elif source_x < target_x:
        start_x = source_x + _NODE_WIDTH
        start_y = source_y + _NODE_HEIGHT / 2
        end_x = target_x
        end_y = target_y + _NODE_HEIGHT / 2
        reach = max(52.0, (end_x - start_x) * 0.42)
        control_one = (start_x + reach, start_y + lane)
        control_two = (end_x - reach, end_y + lane)
    else:
        start_x = source_x
        start_y = source_y + _NODE_HEIGHT / 2
        end_x = target_x + _NODE_WIDTH
        end_y = target_y + _NODE_HEIGHT / 2
        reach = max(52.0, (start_x - end_x) * 0.42)
        control_one = (start_x - reach, start_y + lane)
        control_two = (end_x + reach, end_y + lane)

    control_one_x, control_one_y = control_one
    control_two_x, control_two_y = control_two
    path = (
        f"M {start_x:.1f} {start_y:.1f} C {control_one_x:.1f} {control_one_y:.1f}, "
        f"{control_two_x:.1f} {control_two_y:.1f}, {end_x:.1f} {end_y:.1f}"
    )
    label_x = (start_x + 3 * control_one_x + 3 * control_two_x + end_x) / 8 + label_offset_x
    label_y = (start_y + 3 * control_one_y + 3 * control_two_y + end_y) / 8 + label_offset_y
    return path, label_x, label_y, route


def _render_edge(
    edge: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    *,
    index: int,
    canvas_height: int,
    intent: str,
) -> list[str]:
    kind = str(edge["kind"])
    color, dash, width = _EDGE_STYLE[kind]
    lane_step = _PROCESS_LANE_STEP if intent == "process" else 8
    lane = ((index % 5) - 2) * lane_step
    path, label_x, label_y, route = _edge_geometry(
        positions[str(edge["from"])],
        positions[str(edge["to"])],
        self_loop=edge["from"] == edge["to"],
        lane=lane,
        kind=kind,
        canvas_height=canvas_height,
        intent=intent,
    )
    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    marker_attribute = "" if kind == "association" else f' marker-end="url(#native-arrow-{kind})"'
    label_lines = _wrapped(str(edge["label"]), width=24, limit=2)
    if intent == "process":
        label_size = 17
        label_line_height = 19
        label_width = min(212, max(48, max(len(line) for line in label_lines) * 8 + 22))
        label_height = 29 + max(0, len(label_lines) - 1) * label_line_height
    else:
        label_size = 17 if intent == "narrative" else 15
        label_line_height = 19 if intent == "narrative" else 17
        label_width = min(
            190 if route == "vertical" else 206,
            max(
                70 if route == "vertical" else 84,
                max(len(line) for line in label_lines) * 8 + 24,
            ),
        )
        label_height = (28 if intent == "narrative" else 26) + max(
            0, len(label_lines) - 1
        ) * label_line_height
    same_process_row = (
        intent == "process"
        and route == "standard"
        and positions[str(edge["from"])][1] == positions[str(edge["to"])][1]
    )
    if same_process_row:
        label_y = min(
            positions[str(edge["from"])][1], positions[str(edge["to"])][1]
        ) - 18
    label_top = label_y - label_height / 2
    source_id = str(edge["id"])
    source_id_xml = _xml_escape(source_id)
    kind_xml = _xml_escape(kind)
    lines = [
        f'<g id="native-edge-{source_id_xml}" data-source-kind="edge" '
        f'data-source-id="{source_id_xml}" data-kind="{kind_xml}" '
        f'data-route="{route}">',
        f"<title>{_xml_escape(str(edge['label']))}</title>",
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width:.1f}" '
        f'stroke-linecap="round" stroke-linejoin="round"{dash_attribute}{marker_attribute}/>',
        f'<rect x="{label_x - label_width / 2:.1f}" y="{label_top:.1f}" '
        f'width="{label_width}" height="{label_height}" rx="9" fill="#f8fafc" '
        'fill-opacity="0.94"/>',
    ]
    lines.extend(
        _svg_text_lines(
            label_lines,
            x=label_x,
            y=label_top + (20 if intent == "process" else (20 if intent == "narrative" else 18)),
            line_height=label_line_height,
            size=label_size,
            weight=600,
            color=color,
            anchor="middle",
            max_width=label_width - 16 if intent == "process" else None,
        )
    )
    lines.append("</g>")
    return lines


def _badge(kind: str, x: int, y: int, color: str) -> str:
    center_x = x + 24
    center_y = y + 23
    if kind == "decision":
        return (
            f'<path d="M {center_x:.1f} {center_y - 7:.1f} L {center_x + 7:.1f} '
            f'{center_y:.1f} L {center_x:.1f} {center_y + 7:.1f} L {center_x - 7:.1f} '
            f'{center_y:.1f} Z" fill="none" stroke="{color}" stroke-width="1.8"/>'
        )
    if kind == "risk":
        return (
            f'<path d="M {center_x:.1f} {center_y - 8:.1f} L {center_x + 8:.1f} '
            f'{center_y + 7:.1f} L {center_x - 8:.1f} {center_y + 7:.1f} Z" '
            f'fill="none" stroke="{color}" stroke-width="1.8"/>'
        )
    if kind in {"store", "evidence"}:
        return (
            f'<ellipse cx="{center_x:.1f}" cy="{center_y - 5:.1f}" rx="8" ry="3.5" '
            f'fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<path d="M {center_x - 8:.1f} {center_y - 5:.1f} V {center_y + 6:.1f} '
            f'C {center_x - 8:.1f} {center_y + 10:.1f}, {center_x + 8:.1f} '
            f'{center_y + 10:.1f}, {center_x + 8:.1f} {center_y + 6:.1f} V '
            f'{center_y - 5:.1f}" fill="none" stroke="{color}" stroke-width="1.6"/>'
        )
    if kind == "human":
        return (
            f'<circle cx="{center_x:.1f}" cy="{center_y - 5:.1f}" r="4" fill="none" '
            f'stroke="{color}" stroke-width="1.6"/>'
            f'<path d="M {center_x - 7:.1f} {center_y + 8:.1f} C {center_x - 6:.1f} '
            f'{center_y:.1f}, {center_x + 6:.1f} {center_y:.1f}, {center_x + 7:.1f} '
            f'{center_y + 8:.1f}" fill="none" stroke="{color}" stroke-width="1.6"/>'
        )
    return (
        f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="7" fill="none" '
        f'stroke="{color}" stroke-width="1.8"/>'
    )


def _render_node(
    node: Mapping[str, Any],
    position: tuple[int, int],
    *,
    intent: str,
) -> list[str]:
    x, y = position
    kind = str(node["kind"])
    fill, stroke, radius = _NODE_STYLE[kind]
    source_id = str(node["id"])
    label_lines = _wrapped(str(node["label"]), width=20, limit=2)
    summary_lines = _wrapped(str(node["summary"]), width=28, limit=3)
    label_size = 22
    label_line_height = 23
    summary_size = 19 if intent in {"process", "narrative"} else 17
    summary_line_height = 20 if intent in {"process", "narrative"} else 18
    summary_y = y + 61 + len(label_lines) * label_line_height
    source_id_xml = _xml_escape(source_id)
    kind_xml = _xml_escape(kind)
    lines = [
        f'<g id="native-node-{source_id_xml}" data-source-kind="node" '
        f'data-source-id="{source_id_xml}" data-kind="{kind_xml}">',
        f"<title>{_xml_escape(str(node['label']))}</title>",
        f'<rect x="{x}" y="{y}" width="{_NODE_WIDTH}" height="{_NODE_HEIGHT}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>',
        f'<path d="M {x + 5} {y + 18} V {y + _NODE_HEIGHT - 18}" stroke="{stroke}" '
        'stroke-width="3" stroke-linecap="round"/>',
        _badge(kind, x, y, stroke),
    ]
    lines.extend(
        _svg_text_lines(
            [_KIND_LABEL[kind]],
            x=x + 42,
            y=y + 27,
            line_height=13,
            size=10,
            weight=700,
            color=stroke,
        )
    )
    lines.extend(
        _svg_text_lines(
            label_lines,
            x=x + 18,
            y=y + 54,
            line_height=label_line_height,
            size=label_size,
            weight=700,
            color="#172033",
            max_width=_NODE_WIDTH - 36 if intent == "process" else None,
        )
    )
    lines.extend(
        _svg_text_lines(
            summary_lines,
            x=x + 18,
            y=summary_y,
            line_height=summary_line_height,
            size=summary_size,
            weight=400,
            color="#52606d",
            max_width=_NODE_WIDTH - 36 if intent == "process" else None,
        )
    )
    lines.append("</g>")
    return lines


def render_native_diagram(value: Mapping[str, Any]) -> str:
    """Validate representation input and return one deterministic, standalone SVG."""

    model = _normalized_input(value)
    positions, regions, width, height = _layout(model)
    purpose_lines = _wrapped(str(model["purpose"]), width=max(72, min(150, width // 9)), limit=2)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-labelledby="native-diagram-title" '
        f'data-renderer="schauwerk-native-diagram-v1" '
        f'data-visual-grammar="{_xml_escape(GRAMMAR_SCHEMA_VERSION)}" '
        f'data-intent="{_xml_escape(str(model["intent"]))}" '
        f'data-input-digest="{_xml_escape(str(model["input_digest"]))}">',
        f'<title id="native-diagram-title">{_xml_escape(str(model["title"]))}</title>',
        f'<desc>{_xml_escape(str(model["purpose"]))}</desc>',
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
    ]
    lines.extend(_marker_definitions())
    lines.extend(
        _svg_text_lines(
            [str(model["title"])],
            x=_PAGE_MARGIN,
            y=52,
            line_height=32,
            size=28,
            weight=750,
            color="#172033",
        )
    )
    lines.extend(
        _svg_text_lines(
            purpose_lines,
            x=_PAGE_MARGIN,
            y=82,
            line_height=19,
            size=15,
            weight=400,
            color="#52606d",
        )
    )

    for group_id, label, x, y, region_width, region_height in regions:
        identity = (
            ' data-renderer-region="ungrouped"'
            if group_id is None
            else (
                f' id="native-group-{_xml_escape(group_id)}" data-source-kind="group" '
                f'data-source-id="{_xml_escape(group_id)}"'
            )
        )
        lines.extend(
            (
                f"<g{identity}>",
                f"<title>{_xml_escape(label)}</title>",
                f'<rect x="{x}" y="{y}" width="{region_width}" height="{region_height}" '
                'rx="18" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>',
                f'<path d="M {x + 18} {y + 44} H {x + region_width - 18}" stroke="#e2e8f0"/>',
            )
        )
        lines.extend(
            _svg_text_lines(
                [label],
                x=x + 20,
                y=y + 29,
                line_height=15,
                size=16,
                weight=700,
                color="#334155",
                max_width=(
                    region_width - 40 if str(model["intent"]) == "process" else None
                ),
            )
        )
        lines.append("</g>")

    for index, edge in enumerate(model["edges"]):
        lines.extend(
            _render_edge(
                edge,
                positions,
                index=index,
                canvas_height=height,
                intent=str(model["intent"]),
            )
        )
    for node in model["nodes"]:
        lines.extend(
            _render_node(
                node,
                positions[str(node["id"])],
                intent=str(model["intent"]),
            )
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"
