"""Small deterministic SVG renderer for Schauwerk representation input."""

from __future__ import annotations

import math
import textwrap
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

from .grammar import GRAMMAR_SCHEMA_VERSION
from .native_document import NATIVE_DOCUMENT_SCHEMA, NativeDocumentError
from .representation import RepresentationError, validate_representation_input

__all__ = ["render_native_diagram", "render_native_editing_document"]

_NODE_WIDTH = 250
_NODE_HEIGHT = 166
_GROUP_WIDTH = 284
_GROUP_GAP = 172
_PROCESS_HORIZONTAL_GAP = 52
_PROCESS_ROW_GAP = 52
_PROCESS_EDGE_GUTTER = 80
_PROCESS_LANE_STEP = 14
_PROCESS_GUTTER_LANE_STEP = 18
_PROCESS_LONG_BRANCH_GUTTER = 240
_SELF_LOOP_BASE_REACH = 78.0
_PROCESS_SELF_LOOP_MAX_LANE_REACH = 2.0 * _PROCESS_LANE_STEP
_CORRIDOR_GUTTER_OFFSET = 12.0
_PAGE_MARGIN = 48
_CONTENT_TOP = 140
_ROW_GAP = 52
_EDGE_GUTTER = 128
_NARRATIVE_NODE_WIDTH = 320
_NARRATIVE_GROUP_WIDTH = 354
_NARRATIVE_GROUP_GAP = 67
_NARRATIVE_REGION_BOTTOM_PADDING = 12
_NARRATIVE_FEEDBACK_CHANNEL_OFFSET = 14.0
_NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE = 20
_NARRATIVE_FEEDBACK_LABEL_TARGET_GAP = 12.0
_NARRATIVE_SINGLE_FEEDBACK_TOP_Y = _CONTENT_TOP - 20
_KNOWLEDGE_MAP_GROUP_GAP = 92
_UNGROUPED_PROCESS_HORIZONTAL_GAP = 166
_NON_PROCESS_ROW_GAP = 70
_FEEDBACK_LABEL_LANE_STEP = 56
_PROCESS_LABEL_MAX_WIDTH = 212
_PROCESS_LABEL_MIN_WIDTH = 48
_PROCESS_LABEL_BASE_HEIGHT = 29
_NARRATIVE_LABEL_BASE_HEIGHT = 28
_DEFAULT_LABEL_BASE_HEIGHT = 26
_FEEDBACK_LABEL_WIDTH = 236
_VERTICAL_LABEL_MAX_WIDTH = 190
_DIAGONAL_LABEL_MAX_WIDTH = 206
_VERTICAL_LABEL_MIN_WIDTH = 70
_DIAGONAL_LABEL_MIN_WIDTH = 84
_NARROW_CHARS = frozenset("ilI.,'`:;!|[](){}")
_WIDE_CHARS = frozenset("MW@#%&QGmwo")

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


def _character_width_units(
    character: str,
    *,
    non_ascii: float,
    uppercase: float,
    default: float,
) -> float:
    if character.isspace() or character in _NARROW_CHARS:
        return 0.35
    if character in _WIDE_CHARS:
        return 1.12
    if ord(character) > 0x7F:
        return non_ascii
    if character.isupper():
        return uppercase
    return default


def _estimated_width(
    value: str,
    *,
    size: int,
    non_ascii: float,
    uppercase: float,
    default: float,
) -> float:
    units = sum(
        _character_width_units(
            character,
            non_ascii=non_ascii,
            uppercase=uppercase,
            default=default,
        )
        for character in value
    )
    return units * size


def _estimated_text_width(value: str, *, size: int) -> float:
    """Keep the established conservative estimate for optional process compression."""

    return _estimated_width(
        value, size=size, non_ascii=1.0, uppercase=0.76, default=0.62
    )


def _estimated_wrap_width(value: str, *, size: int) -> float:
    """Estimate natural browser width for wrapping; clip paths remain authoritative."""

    return _estimated_width(
        value, size=size, non_ascii=0.9, uppercase=0.86, default=0.58
    )


def _split_token_to_width(value: str, *, size: int, max_width: float) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    current_width = 0.0
    for character in value:
        character_width = (
            _character_width_units(
                character, non_ascii=0.9, uppercase=0.86, default=0.58
            )
            * size
        )
        if current and current_width + character_width > max_width:
            pieces.append("".join(current))
            current = [character]
            current_width = character_width
        else:
            current.append(character)
            current_width += character_width
    if current:
        pieces.append("".join(current))
    return pieces or [value]


def _ellipsize_to_width(value: str, *, size: int, max_width: float) -> str:
    ellipsis = "…"
    if _estimated_wrap_width(ellipsis, size=size) > max_width:
        return ""
    candidate = value.rstrip()
    while candidate and _estimated_wrap_width(candidate + ellipsis, size=size) > max_width:
        candidate = candidate[:-1].rstrip()
    return candidate + ellipsis if candidate else ellipsis


def _bounded_wrapped(
    value: str,
    *,
    width: int,
    limit: int,
    size: int,
    max_width: float,
) -> list[str]:
    """Wrap for readability while keeping a clip path as the final overflow guard."""

    initial = textwrap.wrap(
        value,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
    )
    refined: list[str] = []
    for initial_line in initial:
        current = ""
        for word in initial_line.split():
            pieces = (
                [word]
                if _estimated_wrap_width(word, size=size) <= max_width
                else _split_token_to_width(word, size=size, max_width=max_width)
            )
            for piece_index, piece in enumerate(pieces):
                separator = " " if current and piece_index == 0 else ""
                candidate = current + separator + piece
                if current and _estimated_wrap_width(candidate, size=size) > max_width:
                    refined.append(current)
                    current = piece
                else:
                    current = candidate
                if piece_index < len(pieces) - 1 and current:
                    refined.append(current)
                    current = ""
        if current:
            refined.append(current)

    if len(refined) > limit:
        refined = refined[:limit]
        refined[-1] = _ellipsize_to_width(
            refined[-1], size=size, max_width=max_width
        )
    return refined


def _rebalance_single_word_lines(
    lines: Sequence[str], *, size: int, max_width: float
) -> list[str]:
    """Avoid a non-final orphan word when one preceding word can safely join it."""

    balanced = list(lines)
    for index in range(1, len(balanced) - 1):
        if len(balanced[index].split()) != 1:
            continue
        previous_words = balanced[index - 1].split()
        # Moving one word must not merely relocate the orphan to the
        # preceding non-final line. Keep at least two words behind.
        if len(previous_words) < 3:
            continue
        candidate = f"{previous_words[-1]} {balanced[index]}"
        if _estimated_wrap_width(candidate, size=size) > max_width:
            continue
        balanced[index - 1] = " ".join(previous_words[:-1])
        balanced[index] = candidate
    return balanced


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
    clip_id: str | None = None,
    allow_glyph_compression: bool = False,
) -> list[str]:
    if not lines:
        return []
    clip_attribute = (
        f' clip-path="url(#{_xml_escape(clip_id)})"' if clip_id is not None else ""
    )
    rendered = [
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}"{clip_attribute}>'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        length_limit = (
            f' textLength="{max_width:.1f}" lengthAdjust="spacingAndGlyphs"'
            if allow_glyph_compression
            and max_width is not None
            and _estimated_text_width(line, size=size) > max_width
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
    is_narrative = model["intent"] == "narrative"
    node_width = _NARRATIVE_NODE_WIDTH if is_narrative else _NODE_WIDTH
    group_width = _NARRATIVE_GROUP_WIDTH if is_narrative else _GROUP_WIDTH
    group_gap = (
        _NARRATIVE_GROUP_GAP
        if is_narrative
        else (
            _KNOWLEDGE_MAP_GROUP_GAP
            if model["intent"] == "knowledge_map"
            else _GROUP_GAP
        )
    )
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
        region_bottom_padding = _NARRATIVE_REGION_BOTTOM_PADDING if is_narrative else 28
        maximum_region_height = (
            64
            + maximum_rows * _NODE_HEIGHT
            + (maximum_rows - 1) * _ROW_GAP
            + region_bottom_padding
        )
        for column, (group_id, label, column_nodes) in enumerate(columns):
            region_x = _PAGE_MARGIN + column * (group_width + group_gap)
            row_count = max(1, len(column_nodes))
            region_height = (
                64
                + row_count * _NODE_HEIGHT
                + (row_count - 1) * _ROW_GAP
                + region_bottom_padding
                if is_narrative
                else maximum_region_height
            )
            regions.append((group_id, label, region_x, _CONTENT_TOP, group_width, region_height))
            for row, node in enumerate(column_nodes):
                positions[node["id"]] = (
                    region_x + (group_width - node_width) // 2,
                    _CONTENT_TOP + 56 + row * (_NODE_HEIGHT + _ROW_GAP),
                )
        width = max(
            900,
            _PAGE_MARGIN * 2
            + len(columns) * group_width
            + max(0, len(columns) - 1) * group_gap,
        ) + _EDGE_GUTTER
        height = _CONTENT_TOP + maximum_region_height + _PAGE_MARGIN
        return positions, regions, width, height

    process_like = model["intent"] in {"process", "sequence", "state", "timeline", "narrative"}
    column_count = min(len(nodes), 6 if process_like else 4)
    horizontal_gap = _UNGROUPED_PROCESS_HORIZONTAL_GAP if process_like else 112
    for index, node in enumerate(nodes):
        column = index % column_count
        row = index // column_count
        positions[node["id"]] = (
            _PAGE_MARGIN + column * (node_width + horizontal_gap),
            _CONTENT_TOP + row * (_NODE_HEIGHT + _NON_PROCESS_ROW_GAP),
        )
    row_count = (len(nodes) + column_count - 1) // column_count
    width = max(
        900,
        _PAGE_MARGIN * 2 + column_count * node_width + (column_count - 1) * horizontal_gap,
    ) + _EDGE_GUTTER
    height = (
        _CONTENT_TOP
        + row_count * _NODE_HEIGHT
        + max(0, row_count - 1) * _NON_PROCESS_ROW_GAP
        + _PAGE_MARGIN
    )
    return positions, regions, width, height


def _clip_definition(
    clip_id: str, *, x: float, y: float, width: float, height: float
) -> str:
    return (
        f'<defs><clipPath id="{_xml_escape(clip_id)}"><rect x="{x:.1f}" y="{y:.1f}" '
        f'width="{width:.1f}" height="{height:.1f}"/></clipPath></defs>'
    )


def _marker_definitions() -> list[str]:
    lines = ["<defs>"]
    for kind, (color, _, _) in _EDGE_STYLE.items():
        if kind == "association":
            continue
        lines.extend(
            (
                f'<marker id="native-arrow-{kind}" viewBox="0 0 8 8" refX="7" refY="4" '
                'markerWidth="6" markerHeight="6" orient="auto" '
                'markerUnits="strokeWidth">',
                f'<path d="M 0 0 L 8 4 L 0 8 L 2 4 Z" fill="{color}"/>',
                "</marker>",
            )
        )
    lines.append("</defs>")
    return lines


@dataclass(frozen=True)
class _EdgeLabelMetrics:
    size: int
    line_height: int
    lines: tuple[str, ...]
    width: int
    height: int
    clip_padding: int
    allow_glyph_compression: bool


def _edge_label_metrics(
    edge: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    intent: str,
) -> _EdgeLabelMetrics:
    """Compute the single canonical label box used by packing and rendering."""
    kind = str(edge["kind"])
    source_position = positions[str(edge["from"])]
    target_position = positions[str(edge["to"])]
    if intent == "process":
        size = 17
        line_height = 19
        lines = tuple(_wrapped(str(edge["label"]), width=24, limit=2))
        width = min(
            _PROCESS_LABEL_MAX_WIDTH,
            max(
                _PROCESS_LABEL_MIN_WIDTH,
                max(len(line) for line in lines) * 8 + 22,
            ),
        )
        height = (
            _PROCESS_LABEL_BASE_HEIGHT
            + max(0, len(lines) - 1) * line_height
        )
        return _EdgeLabelMetrics(
            size=size,
            line_height=line_height,
            lines=lines,
            width=width,
            height=height,
            clip_padding=6,
            allow_glyph_compression=True,
        )

    size = 17 if intent == "narrative" else 15
    line_height = 19 if intent == "narrative" else 17
    vertical = source_position[0] == target_position[0]
    feedback_label = kind == "feedback"
    compact_narrative_label = False
    compact_knowledge_label = False
    width_cap = (
        _FEEDBACK_LABEL_WIDTH
        if feedback_label
        else (
            _VERTICAL_LABEL_MAX_WIDTH
            if vertical
            else _DIAGONAL_LABEL_MAX_WIDTH
        )
    )
    minimum_width = (
        _FEEDBACK_LABEL_WIDTH
        if feedback_label
        else (
            _VERTICAL_LABEL_MIN_WIDTH
            if vertical
            else _DIAGONAL_LABEL_MIN_WIDTH
        )
    )
    if not feedback_label and not vertical:
        node_width = (
            _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
        )
        horizontal_gap = abs(target_position[0] - source_position[0]) - node_width
        vertical_corridor = (
            abs(target_position[1] - source_position[1]) - _NODE_HEIGHT
        )
        use_narrative_vertical_corridor = (
            intent == "narrative"
            and _ROW_GAP <= vertical_corridor <= _NON_PROCESS_ROW_GAP
        )
        if horizontal_gap > 0 and not use_narrative_vertical_corridor:
            corridor_margin = 8 if intent == "knowledge_map" else 16
            width_cap = min(
                width_cap,
                max(48, int(horizontal_gap - corridor_margin)),
            )
            minimum_width = min(minimum_width, width_cap)
            compact_narrative_label = (
                intent == "narrative"
                and vertical_corridor > _NON_PROCESS_ROW_GAP
            )
            compact_knowledge_label = (
                intent == "knowledge_map" and width_cap <= 118
            )
            if compact_narrative_label:
                size = 15
            elif compact_knowledge_label:
                size = 14
                line_height = 16
    provisional = _wrapped(str(edge["label"]), width=24, limit=2)
    width = min(
        width_cap,
        max(minimum_width, max(len(line) for line in provisional) * 8 + 24),
    )
    clip_padding = (
        4
        if compact_knowledge_label
        else (
            6
            if compact_narrative_label
            else (7 if intent == "narrative" else 8)
        )
    )
    lines = tuple(
        _bounded_wrapped(
            str(edge["label"]),
            width=24,
            limit=2,
            size=size,
            max_width=width - 2 * clip_padding,
        )
    )
    base_height = (
        _NARRATIVE_LABEL_BASE_HEIGHT
        if intent == "narrative"
        else _DEFAULT_LABEL_BASE_HEIGHT
    )
    height = base_height + max(0, len(lines) - 1) * line_height
    return _EdgeLabelMetrics(
        size=size,
        line_height=line_height,
        lines=lines,
        width=width,
        height=height,
        clip_padding=clip_padding,
        allow_glyph_compression=False,
    )


def _process_row_corridor_bounds(
    row_y: int,
    positions: Mapping[str, tuple[int, int]],
    *,
    direction: int,
) -> tuple[int, int] | None:
    """Return the real card-to-card gap immediately above or below one process row."""
    row_levels = sorted({y for _, y in positions.values()})
    try:
        index = row_levels.index(row_y)
    except ValueError:
        return None
    if direction > 0:
        if index + 1 >= len(row_levels):
            return None
        return row_y + _NODE_HEIGHT, row_levels[index + 1]
    if index == 0:
        return None
    return row_levels[index - 1] + _NODE_HEIGHT, row_y


def _row_corridor_containing(
    label_y: float,
    positions: Mapping[str, tuple[int, int]],
) -> tuple[int, int] | None:
    """Return the real card-to-card gap that holds one label centre, if any."""
    row_levels = sorted({y for _, y in positions.values()})
    for upper, lower in zip(row_levels, row_levels[1:]):
        upper_bottom = upper + _NODE_HEIGHT
        if upper_bottom <= label_y <= lower:
            return upper_bottom, lower
    return None


def _process_label_corridor_above(
    row_y: int,
    positions: Mapping[str, tuple[int, int]],
    *,
    header_corridor: tuple[int, int],
) -> tuple[int, int]:
    """Include the header rail in label occupancy without changing card-to-card gaps."""
    corridor = _process_row_corridor_bounds(row_y, positions, direction=-1)
    return corridor if corridor is not None else header_corridor


def _anchored_corridor_label_x(
    source_x: int,
    *,
    self_loop: bool,
    self_loop_max_lane_reach: float = _PROCESS_SELF_LOOP_MAX_LANE_REACH,
    long_branch_gutter_x: float | None = None,
) -> tuple[float, float]:
    """Return the centre and the extra width of one anchored label's x bound."""
    if self_loop:
        # A self-loop label rides its Bezier midpoint outside the card column.
        # The reach depends on the rendered lane, so bound every possible lane.
        nearest = source_x + _NODE_WIDTH + 0.75 * _SELF_LOOP_BASE_REACH
        farthest = nearest + 0.75 * self_loop_max_lane_reach
        return (nearest + farthest) / 2, farthest - nearest
    if long_branch_gutter_x is not None:
        # A singleton long branch centres its label between the source card
        # and the outer process gutter it leaves through.
        return (source_x + _NODE_WIDTH / 2 + long_branch_gutter_x) / 2, 0.0
    center_x = source_x + _NODE_WIDTH / 2
    gutter_x = source_x + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET
    return (center_x + gutter_x) / 2, 0.0


def _stable_lane_ranks(model: Mapping[str, Any]) -> dict[str, int]:
    """Order-independent lane ranks for relations that fall back to a plain lane.

    The generic Bezier route expresses its lane only through the offset of its
    control points, so co-routed relations need distinct lanes. Deriving that
    lane from the position of a relation in the input list let a permuted
    relation list move control points, which breaks the determinism contract.
    Ranking the relation ids instead keeps the lane a function of the relation
    set while preserving the accepted spread of the established diagrams.
    """
    return {
        edge_id: rank
        for rank, edge_id in enumerate(
            sorted(str(edge["id"]) for edge in model["edges"])
        )
    }


def _process_anchor_order_key(edge: Mapping[str, Any]) -> tuple[str, str, str]:
    """Order process self-loops by meaning; preserve other relations' id order."""
    if edge["from"] == edge["to"]:
        return str(edge["label"]), str(edge["kind"]), str(edge["id"])
    return "", "", str(edge["id"])


def _bezier_self_loop_lanes(
    model: Mapping[str, Any],
    *,
    intent: str,
    narrative_self_loop_gutter_x: Mapping[str, float],
) -> dict[str, int]:
    """Deterministic lanes for the self-loops that render as a Bezier arc.

    Such a loop expresses its lane only through the reach of the arc, so two
    loops on one card would otherwise coincide. Every other route ignores the
    lane of a self-loop. Process loops use the same semantic order as their
    label anchors; other intents retain the established relation-id order.
    """
    lane_step = _PROCESS_LANE_STEP if intent == "process" else 8
    stacked: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for edge in model["edges"]:
        edge_id = str(edge["id"])
        if (
            edge["from"] != edge["to"]
            or str(edge["kind"]) == "feedback"
            or edge_id in narrative_self_loop_gutter_x
        ):
            continue
        stacked[str(edge["from"])].append(edge)
    lanes: dict[str, int] = {}
    for edges in stacked.values():
        ordered = sorted(
            edges,
            key=_process_anchor_order_key if intent == "process" else lambda edge: str(edge["id"]),
        )
        for slot, edge in enumerate(ordered):
            # Keep the established first three process lanes byte-for-byte, but
            # do not collapse deeper stacks onto the third arc. The process
            # corridor planner expands the self-loop envelope for overflow lanes.
            lanes[str(edge["id"])] = slot * lane_step
    return lanes


def _process_long_branch_ids(
    model: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    *,
    process_row_gap: int,
) -> list[str]:
    """Ids of the process relations that leave through the long-branch gutter."""
    row_step = _NODE_HEIGHT + process_row_gap
    long_branches: list[str] = []
    for edge in model["edges"]:
        if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
            continue
        source = positions[str(edge["from"])]
        target = positions[str(edge["to"])]
        if (
            source[0] != target[0]
            and source[1] != target[1]
            and abs(target[1] - source[1]) > row_step
        ):
            long_branches.append(str(edge["id"]))
    return sorted(long_branches)


def _process_anchored_corridor_labels(
    model: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    *,
    process_row_gap: int,
    long_vertical_gutter_x: Mapping[str, float],
    canvas_width: int,
    header_corridor: tuple[int, int],
) -> list[tuple[tuple[int, int], float, str, float, int]]:
    """Process labels whose physical row corridor is fixed by their own route.

    Self-loops keep the same-row label slot above their card, long same-column
    relations keep the source-side row corridor, and a singleton long branch
    keeps the source-side row corridor between its card and the outer process
    gutter. They keep their anchors unless overlapping occupants require an
    outer lane; they cannot be repacked inside the corridor.
    """
    long_branch_ids = _process_long_branch_ids(
        model, positions, process_row_gap=process_row_gap
    )
    self_loop_counts: dict[str, int] = defaultdict(int)
    for relation in model["edges"]:
        if str(relation["kind"]) != "feedback" and relation["from"] == relation["to"]:
            self_loop_counts[str(relation["from"])] += 1
    anchored: list[tuple[tuple[int, int], float, str, float, int]] = []
    for edge in model["edges"]:
        if str(edge["kind"]) == "feedback":
            continue
        edge_id = str(edge["id"])
        source = positions[str(edge["from"])]
        target = positions[str(edge["to"])]
        self_loop = edge["from"] == edge["to"]
        long_branch_gutter_x: float | None = None
        if self_loop:
            corridor = _process_label_corridor_above(
                source[1], positions, header_corridor=header_corridor
            )
        elif long_branch_ids == [edge_id]:
            # The sole long branch renders its label in the source row corridor
            # instead of the shared outer label pack, so it occupies that
            # physical corridor exactly like an anchored same-column relation.
            long_branch_gutter_x = canvas_width - _PROCESS_EDGE_GUTTER / 2
            corridor = _process_row_corridor_bounds(
                source[1], positions, direction=1 if source[1] < target[1] else -1
            )
        elif (
            source[0] != target[0]
            or source[1] == target[1]
            or abs(target[1] - source[1]) <= _NODE_HEIGHT + process_row_gap
            or edge_id in long_vertical_gutter_x
        ):
            continue
        else:
            corridor = _process_row_corridor_bounds(
                source[1], positions, direction=1 if source[1] < target[1] else -1
            )
        if corridor is None:
            continue
        metrics = _edge_label_metrics(edge, positions, "process")
        self_loop_max_lane_reach = _PROCESS_SELF_LOOP_MAX_LANE_REACH
        if self_loop:
            self_loop_max_lane_reach = max(
                self_loop_max_lane_reach,
                (self_loop_counts[str(edge["from"])] - 1) * _PROCESS_LANE_STEP,
            )
        natural_x, extra_width = _anchored_corridor_label_x(
            source[0],
            self_loop=self_loop,
            self_loop_max_lane_reach=self_loop_max_lane_reach,
            long_branch_gutter_x=long_branch_gutter_x,
        )
        anchored.append(
            (corridor, natural_x, edge_id, metrics.width + extra_width, metrics.height)
        )
    return anchored


def _preserve_same_row_process_feedback_return(
    source_position: tuple[int, int],
    target_position: tuple[int, int],
    positions: Mapping[str, tuple[int, int]],
) -> bool:
    """Whether reverse same-row feedback can keep the accepted bottom return lane."""
    if (
        source_position[0] <= target_position[0]
        or source_position[1] != target_position[1]
    ):
        return False
    endpoint_xs = (
        source_position[0] + _NODE_WIDTH / 2,
        target_position[0] + _NODE_WIDTH / 2,
    )
    return not any(
        node_y > source_position[1]
        and any(node_x < endpoint_x < node_x + _NODE_WIDTH for endpoint_x in endpoint_xs)
        for node_x, node_y in positions.values()
    )


def _midpoint(
    first: tuple[float, float], second: tuple[float, float]
) -> tuple[float, float]:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def _cubic_hull_intersects_box(
    points: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
    box: tuple[float, float, float, float],
    *,
    depth: int = 0,
) -> bool:
    left, top, width, height = box
    right = left + width
    bottom = top + height
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if max(xs) <= left or min(xs) >= right or max(ys) <= top or min(ys) >= bottom:
        return False
    if depth >= 12 or (max(xs) - min(xs) <= 0.5 and max(ys) - min(ys) <= 0.5):
        return True
    p0, p1, p2, p3 = points
    p01 = _midpoint(p0, p1)
    p12 = _midpoint(p1, p2)
    p23 = _midpoint(p2, p3)
    p012 = _midpoint(p01, p12)
    p123 = _midpoint(p12, p23)
    center = _midpoint(p012, p123)
    return _cubic_hull_intersects_box(
        (p0, p01, p012, center), box, depth=depth + 1
    ) or _cubic_hull_intersects_box(
        (center, p123, p23, p3), box, depth=depth + 1
    )


def _edge_geometry(
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    self_loop: bool,
    lane: int,
    kind: str,
    canvas_width: int,
    canvas_height: int,
    intent: str,
    process_row_gap: int = _PROCESS_ROW_GAP,
    non_process_row_gap: int = _ROW_GAP,
    long_branch_slot: int | None = None,
    long_branch_count: int = 0,
    long_branch_label_y: float | None = None,
    anchored_branch_gutter_x: float | None = None,
    long_vertical_gutter_x: float | None = None,
    long_vertical_label_y: float | None = None,
    process_branch_gutter_x: float | None = None,
    narrative_parallel_gutter_x: float | None = None,
    narrative_self_loop_gutter_x: float | None = None,
    generic_self_loop_gutter_x: float | None = None,
    label_height: int = 0,
    label_width: int = 0,
    feedback_label_y: float | None = None,
    max_node_bottom: float = 0.0,
    preserve_same_row_feedback_footer: bool = True,
    obstacle_positions: Sequence[tuple[int, int]] = (),
) -> tuple[str, float, float, str]:
    source_x, source_y = source
    target_x, target_y = target
    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
    route = "standard"
    label_offset_x = 0.0
    label_offset_y = 0.0
    if kind == "feedback" and intent == "process":
        route = "feedback-return"
        if (
            source_x > target_x
            and source_y == target_y
            and not self_loop
            and preserve_same_row_feedback_footer
        ):
            # Preserve the accepted same-row reverse-feedback geometry when its
            # vertical endpoint legs have no lower-row card beneath them.
            start_x = source_x + node_width / 2
            start_y = source_y + _NODE_HEIGHT
            end_x = target_x + node_width / 2
            end_y = target_y + _NODE_HEIGHT
            baseline_y = (
                feedback_label_y
                if feedback_label_y is not None
                else canvas_height - 40 + max(-8.0, min(8.0, lane / 2))
            )
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

        # Other process-feedback directions leave through the nearest row gap,
        # travel in the outer gutter, and re-enter through the target row gap.
        # This avoids vertical runs through cards in the same column.
        start_x = source_x + node_width / 2
        end_x = target_x + node_width / 2
        bend = 18.0
        if source_y < target_y:
            start_y = source_y + _NODE_HEIGHT
            end_y = target_y
            source_corridor_y = start_y + process_row_gap / 2
            target_corridor_y = end_y - process_row_gap / 2
            start_bend = bend
            end_bend = -bend
        elif source_y > target_y:
            start_y = source_y
            end_y = target_y + _NODE_HEIGHT
            source_corridor_y = start_y - process_row_gap / 2
            target_corridor_y = end_y + process_row_gap / 2
            start_bend = -bend
            end_bend = bend
        else:
            start_y = end_y = source_y + _NODE_HEIGHT
            source_corridor_y = target_corridor_y = start_y + process_row_gap / 2
            start_bend = end_bend = bend
        gutter_x = canvas_width - _PROCESS_EDGE_GUTTER / 2
        if feedback_label_y is not None:
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_y + start_bend:.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {feedback_label_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_y + end_bend:.1f}, {end_x:.1f} {end_y:.1f}"
            )
            return path, gutter_x, feedback_label_y, route
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"C {start_x:.1f} {start_y + start_bend:.1f}, "
            f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
            f"L {gutter_x:.1f} {source_corridor_y:.1f} "
            f"L {gutter_x:.1f} {target_corridor_y:.1f} "
            f"L {end_x:.1f} {target_corridor_y:.1f} "
            f"C {end_x:.1f} {target_corridor_y:.1f}, "
            f"{end_x:.1f} {end_y + end_bend:.1f}, {end_x:.1f} {end_y:.1f}"
        )
        return path, (start_x + gutter_x) / 2, source_corridor_y, route
    elif kind == "feedback" and intent != "process":
        route = "feedback-return"
        upper_bottom = min(source_y, target_y) + _NODE_HEIGHT
        lower_top = max(source_y, target_y)
        corridor_gap = lower_top - upper_bottom
        adjacent_rows = (
            abs(source_y - target_y) <= _NODE_HEIGHT + non_process_row_gap
        )
        if (
            source_y != target_y
            and adjacent_rows
            and corridor_gap >= label_height + 12
            and feedback_label_y is None
        ):
            # Any non-process feedback relation may use the whitespace between
            # rows. Vertical legs stop at card boundaries, so same-column and
            # left-to-right feedback are as safe as the accepted reverse route.
            start_x = source_x + node_width / 2
            end_x = target_x + node_width / 2
            if source_y > target_y:
                start_y = source_y
                end_y = target_y + _NODE_HEIGHT
            else:
                start_y = source_y + _NODE_HEIGHT
                end_y = target_y
            corridor_y = (upper_bottom + lower_top) / 2
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"L {start_x:.1f} {corridor_y:.1f} "
                f"L {end_x:.1f} {corridor_y:.1f} "
                f"L {end_x:.1f} {end_y:.1f}"
            )
            return path, (start_x + end_x) / 2, corridor_y, route

        # Same-row or narrow-gap feedback leaves on the outer side of both
        # cards, then travels below the complete card field. For the historical
        # right-to-left case this intentionally preserves the accepted geometry.
        channel_offset = (
            _NARRATIVE_FEEDBACK_CHANNEL_OFFSET if intent == "narrative" else 28.0
        )
        start_y = source_y + _NODE_HEIGHT / 2
        end_y = target_y + _NODE_HEIGHT / 2
        if source_x > target_x:
            start_x = source_x + node_width
            end_x = target_x
            source_channel_x = min(canvas_width - 16.0, start_x + channel_offset)
            target_channel_x = max(16.0, end_x - channel_offset)
        elif source_x < target_x:
            start_x = source_x
            end_x = target_x + node_width
            source_channel_x = max(16.0, start_x - channel_offset)
            target_channel_x = min(canvas_width - 16.0, end_x + channel_offset)
        else:
            start_x = end_x = source_x + node_width
            source_channel_x = target_channel_x = min(
                canvas_width - 16.0, start_x + channel_offset
            )
        bottom_clearance = (
            _NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE if intent == "narrative" else 10
        )
        safe_center = max_node_bottom + label_height / 2 + bottom_clearance
        baseline_y = (
            feedback_label_y
            if feedback_label_y is not None
            else min(canvas_height - label_height / 2 - 8, safe_center)
        )
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"L {source_channel_x:.1f} {start_y:.1f} "
            f"L {source_channel_x:.1f} {baseline_y:.1f} "
            f"L {target_channel_x:.1f} {baseline_y:.1f} "
            f"L {target_channel_x:.1f} {end_y:.1f} "
            f"L {end_x:.1f} {end_y:.1f}"
        )
        if intent == "narrative":
            half_label_width = label_width / 2
            if source_x > target_x:
                label_x = target_channel_x + half_label_width + _NARRATIVE_FEEDBACK_LABEL_TARGET_GAP
            else:
                label_x = target_channel_x - half_label_width - _NARRATIVE_FEEDBACK_LABEL_TARGET_GAP
            label_x = min(
                max(label_x, half_label_width + 8),
                canvas_width - half_label_width - 8,
            )
        else:
            label_x = (source_channel_x + target_channel_x) / 2
        return path, label_x, baseline_y, route
    elif (
        self_loop
        and intent == "narrative"
        and narrative_self_loop_gutter_x is not None
    ):
        route = "narrative-self-loop"
        start_x = source_x + node_width * 0.35
        end_x = source_x + node_width * 0.65
        start_y = end_y = source_y + _NODE_HEIGHT
        corridor_y = start_y + non_process_row_gap / 2
        gutter_x = narrative_self_loop_gutter_x
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"L {start_x:.1f} {corridor_y:.1f} "
            f"L {gutter_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {end_y:.1f}"
        )
        return path, gutter_x + 8 + label_width / 2, corridor_y, route
    elif (
        self_loop
        and intent not in {"process", "narrative"}
        and generic_self_loop_gutter_x is not None
    ):
        route = "generic-self-loop"
        start_x = source_x + node_width * 0.35
        end_x = source_x + node_width * 0.65
        start_y = end_y = source_y + _NODE_HEIGHT
        corridor_y = start_y + non_process_row_gap / 2
        gutter_x = generic_self_loop_gutter_x
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"L {start_x:.1f} {corridor_y:.1f} "
            f"L {gutter_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {end_y:.1f}"
        )
        return path, gutter_x + 8 + label_width / 2, corridor_y, route
    elif self_loop:
        start_x = source_x + node_width
        start_y = source_y + _NODE_HEIGHT * 0.35
        end_x = source_x + node_width
        end_y = source_y + _NODE_HEIGHT * 0.72
        reach = _SELF_LOOP_BASE_REACH + abs(lane)
        control_one = (start_x + reach, start_y - 44)
        control_two = (end_x + reach, end_y + 44)
    elif intent == "narrative" and narrative_parallel_gutter_x is not None:
        route = "narrative-parallel"
        gutter_x = narrative_parallel_gutter_x
        if source_y != target_y:
            direction = 1.0 if source_y < target_y else -1.0
            start_x = source_x + node_width / 2
            end_x = target_x + node_width / 2
            start_y = source_y + _NODE_HEIGHT if direction > 0 else source_y
            end_y = target_y if direction > 0 else target_y + _NODE_HEIGHT
            source_corridor_y = start_y + direction * non_process_row_gap / 2
            target_corridor_y = end_y - direction * non_process_row_gap / 2
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"L {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {end_y:.1f}"
            )
            label_y = (source_corridor_y + target_corridor_y) / 2
        else:
            start_x = source_x + node_width / 2
            end_x = target_x + node_width / 2
            start_y = source_y + _NODE_HEIGHT
            end_y = target_y + _NODE_HEIGHT
            corridor_y = start_y + non_process_row_gap / 2
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"L {start_x:.1f} {corridor_y:.1f} "
                f"L {gutter_x:.1f} {corridor_y:.1f} "
                f"L {end_x:.1f} {corridor_y:.1f} "
                f"L {end_x:.1f} {end_y:.1f}"
            )
            label_y = corridor_y
        return path, gutter_x + 8 + label_width / 2, label_y, route
    elif (
        intent == "process"
        and process_branch_gutter_x is not None
        and source_y == target_y
        and not self_loop
    ):
        route = "process-row-gutter"
        start_x = source_x + node_width / 2
        end_x = target_x + node_width / 2
        start_y = end_y = source_y
        corridor_y = source_y - process_row_gap / 2
        gutter_x = process_branch_gutter_x
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"L {start_x:.1f} {corridor_y:.1f} "
            f"L {gutter_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {corridor_y:.1f} "
            f"L {end_x:.1f} {end_y:.1f}"
        )
        return path, gutter_x + 8 + label_width / 2, corridor_y, route
    elif source_x == target_x:
        route = "vertical"
        center_x = source_x + node_width / 2
        if source_y < target_y:
            start_x = end_x = center_x
            start_y = source_y + _NODE_HEIGHT
            end_y = target_y
        else:
            start_x = end_x = center_x
            start_y = source_y
            end_y = target_y + _NODE_HEIGHT
        vertical_row_gap = process_row_gap if intent == "process" else non_process_row_gap
        row_step = _NODE_HEIGHT + vertical_row_gap
        if (
            intent == "process"
            and process_branch_gutter_x is not None
            and abs(target_y - source_y) <= row_step
        ):
            corridor_y = (start_y + end_y) / 2
            gutter_x = process_branch_gutter_x
            path = (
                f"M {center_x:.1f} {start_y:.1f} "
                f"L {center_x:.1f} {corridor_y:.1f} "
                f"L {gutter_x:.1f} {corridor_y:.1f} "
                f"L {center_x:.1f} {corridor_y:.1f} "
                f"L {center_x:.1f} {end_y:.1f}"
            )
            return path, gutter_x + 8 + label_width / 2, corridor_y, "process-row-gutter"
        if abs(target_y - source_y) > row_step:
            # A direct vertical span across multiple rows would pass through an
            # intervening card and place its label there. Leave through the
            # nearest row-gap corridor, travel just outside the card column, and
            # re-enter through the target-side row gap instead.
            direction = 1.0 if end_y > start_y else -1.0
            source_corridor_y = start_y + direction * vertical_row_gap / 2
            target_corridor_y = end_y - direction * vertical_row_gap / 2
            if intent == "process" and process_branch_gutter_x is not None:
                long_vertical_gutter_x = process_branch_gutter_x
                long_vertical_label_y = source_corridor_y
            gutter_x = (
                long_vertical_gutter_x
                if long_vertical_gutter_x is not None
                else source_x + node_width + _CORRIDOR_GUTTER_OFFSET
            )
            path = (
                f"M {center_x:.1f} {start_y:.1f} "
                f"L {center_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {center_x:.1f} {target_corridor_y:.1f} "
                f"L {center_x:.1f} {end_y:.1f}"
            )
            if long_vertical_gutter_x is not None:
                label_y = (
                    long_vertical_label_y
                    if long_vertical_label_y is not None
                    else (source_corridor_y + target_corridor_y) / 2
                )
                return path, gutter_x + 8 + label_width / 2, label_y, route
            return path, (center_x + gutter_x) / 2, source_corridor_y, route
        distance = abs(end_y - start_y)
        bend = max(28.0, distance * 0.42)
        direction = 1.0 if end_y > start_y else -1.0
        control_one = (center_x, start_y + direction * bend)
        control_two = (center_x, end_y - direction * bend)
        # Adjacent vertical labels remain centered on the inter-row corridor.
        label_offset_x = 0.0
    elif intent == "narrative" and source_x != target_x:
        route = "narrative-curve"
        start_y = source_y + _NODE_HEIGHT / 2
        end_y = target_y + _NODE_HEIGHT / 2
        if source_x < target_x:
            start_x = source_x + node_width
            end_x = target_x
        else:
            start_x = source_x
            end_x = target_x + node_width
        channel_x = (start_x + end_x) / 2
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"C {channel_x:.1f} {start_y:.1f}, "
            f"{channel_x:.1f} {end_y:.1f}, {end_x:.1f} {end_y:.1f}"
        )
        label_x = channel_x
        if source_y != target_y:
            upper_bottom = min(source_y, target_y) + _NODE_HEIGHT
            lower_top = max(source_y, target_y)
            vertical_clearance = lower_top - upper_bottom
            adjacent_rows = (
                abs(source_y - target_y) <= _NODE_HEIGHT + non_process_row_gap
            )
            if adjacent_rows and vertical_clearance >= label_height + 4:
                label_y = (upper_bottom + lower_top) / 2
            else:
                label_y = (start_y + end_y) / 2
        else:
            label_y = start_y
        return path, label_x, label_y, route
    elif intent == "process" and source_y != target_y:
        route = "process-branch"
        source_center_x = source_x + node_width / 2
        target_center_x = target_x + node_width / 2
        row_step = _NODE_HEIGHT + process_row_gap
        spans_intervening_row = abs(target_y - source_y) > row_step
        if spans_intervening_row and long_branch_slot is not None:
            stable_count = max(1, long_branch_count)
            centered_slot = long_branch_slot - (stable_count - 1) / 2
            lane_offset = max(-8.0, min(8.0, centered_slot * 4.0))
        else:
            lane_offset = max(-8.0, min(8.0, lane / 2))
        if source_y < target_y:
            start_x = source_center_x
            start_y = source_y + _NODE_HEIGHT
            end_x = target_center_x
            end_y = target_y
            source_corridor_y = start_y + process_row_gap / 2 + lane_offset
            target_corridor_y = end_y - process_row_gap / 2 + lane_offset
            label_offset_y = -16.0
        else:
            start_x = source_center_x
            start_y = source_y
            end_x = target_center_x
            end_y = target_y + _NODE_HEIGHT
            source_corridor_y = start_y - process_row_gap / 2 + lane_offset
            target_corridor_y = end_y + process_row_gap / 2 + lane_offset
            label_offset_y = 16.0
        if process_branch_gutter_x is not None:
            gutter_x = process_branch_gutter_x
            bend = 18.0
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_y + (bend if source_y < target_y else -bend):.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_y + (-bend if source_y < target_y else bend):.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
            return (
                path,
                gutter_x + 8 + label_width / 2,
                (source_corridor_y + target_corridor_y) / 2,
                route,
            )
        if spans_intervening_row:
            slot = long_branch_slot or 0
            count = max(1, long_branch_count)
            if count == 1:
                # Keep the established single-branch gutter width, but use the
                # stable long-branch slot above. The label stays centered in the
                # source row gap so it cannot drift into an intervening card.
                gutter_x = (
                    anchored_branch_gutter_x
                    if anchored_branch_gutter_x is not None
                    else canvas_width - _PROCESS_EDGE_GUTTER / 2
                )
            else:
                gutter_x = canvas_width - 20 - slot * _PROCESS_GUTTER_LANE_STEP
            bend = 18.0
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_y + (bend if source_y < target_y else -bend):.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_y + (-bend if source_y < target_y else bend):.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
            if count == 1:
                label_x = (start_x + gutter_x) / 2
                label_y = source_corridor_y
            else:
                process_gutter_width = (
                    _PROCESS_LONG_BRANCH_GUTTER
                    + (count - 1) * _PROCESS_GUTTER_LANE_STEP
                )
                label_x = canvas_width - process_gutter_width / 2
                label_y = (
                    long_branch_label_y
                    if long_branch_label_y is not None
                    else (source_corridor_y + target_corridor_y) / 2
                )
            return path, label_x, label_y, route
        corridor_y = (start_y + end_y) / 2 + lane_offset
        control_one = (start_x, corridor_y)
        control_two = (end_x, corridor_y)
    elif source_x < target_x:
        start_x = source_x + node_width
        start_y = source_y + _NODE_HEIGHT / 2
        end_x = target_x
        end_y = target_y + _NODE_HEIGHT / 2
        reach = max(52.0, (end_x - start_x) * 0.42)
        control_one = (start_x + reach, start_y + lane)
        control_two = (end_x - reach, end_y + lane)
    else:
        start_x = source_x
        start_y = source_y + _NODE_HEIGHT / 2
        end_x = target_x + node_width
        end_y = target_y + _NODE_HEIGHT / 2
        reach = max(52.0, (start_x - end_x) * 0.42)
        control_one = (start_x - reach, start_y + lane)
        control_two = (end_x + reach, end_y + lane)

    if (
        route == "standard"
        and intent == "knowledge_map"
        and source_y != target_y
        and abs(source_y - target_y) <= _NODE_HEIGHT + non_process_row_gap
    ):
        upper_bottom = min(source_y, target_y) + _NODE_HEIGHT
        lower_top = max(source_y, target_y)
        vertical_clearance = lower_top - upper_bottom
        default_points = (
            (float(start_x), float(start_y)),
            (float(control_one[0]), float(control_one[1])),
            (float(control_two[0]), float(control_two[1])),
            (float(end_x), float(end_y)),
        )
        blocking_boxes = [
            (float(x), float(y), float(node_width), float(_NODE_HEIGHT))
            for x, y in obstacle_positions
            if _cubic_hull_intersects_box(
                default_points,
                (float(x), float(y), float(node_width), float(_NODE_HEIGHT)),
            )
        ]
        if vertical_clearance >= label_height + 8 and blocking_boxes:
            corridor_y = (upper_bottom + lower_top) / 2
            route = "knowledge-map-card-safe"
            if source_x < target_x:
                # Keep the detour inside the whitespace between adjacent rows.
                # A small inset from the card boundary leaves visible clearance
                # for labels that legitimately occupy the same row gap.
                clearance = 8.0
                lower_safe_y = lower_top - clearance
                upper_safe_y = upper_bottom + 6.0
                blocking_left = min(box[0] for box in blocking_boxes)
                blocking_right = max(box[0] + box[2] for box in blocking_boxes)
                bridge_start_x = max(start_x + 52.0, blocking_left - clearance)
                bridge_end_x = min(end_x - 52.0, blocking_right + clearance)
                if bridge_end_x - bridge_start_x > 96.0:
                    approach_reach = max(52.0, (bridge_start_x - start_x) * 0.42)
                    exit_reach = max(36.0, (end_x - bridge_end_x) * 0.45)
                    shelf_in_x = bridge_start_x + 40.0
                    shelf_out_x = bridge_end_x - 40.0
                    path = (
                        f"M {start_x:.1f} {start_y:.1f} "
                        f"C {start_x + approach_reach:.1f} {start_y:.1f}, "
                        f"{bridge_start_x - approach_reach:.1f} {lower_safe_y:.1f}, "
                        f"{bridge_start_x:.1f} {lower_safe_y:.1f} "
                        f"C {bridge_start_x + 12.0:.1f} {lower_safe_y:.1f}, "
                        f"{bridge_start_x + 24.0:.1f} {upper_safe_y:.1f}, "
                        f"{shelf_in_x:.1f} {upper_safe_y:.1f} "
                        f"L {shelf_out_x:.1f} {upper_safe_y:.1f} "
                        f"C {bridge_end_x - 24.0:.1f} {upper_safe_y:.1f}, "
                        f"{bridge_end_x - 12.0:.1f} {lower_safe_y:.1f}, "
                        f"{bridge_end_x:.1f} {lower_safe_y:.1f} "
                        f"C {bridge_end_x + exit_reach:.1f} {lower_safe_y:.1f}, "
                        f"{end_x - exit_reach:.1f} {end_y:.1f}, "
                        f"{end_x:.1f} {end_y:.1f}"
                    )
                    return path, (start_x + end_x) / 2, corridor_y, route

            direction = 1.0 if target_y > source_y else -1.0
            excursion = max(40.0, min(96.0, abs(end_y - start_y) * 0.34))
            control_one = (start_x, corridor_y + direction * excursion)
            control_two = (end_x, corridor_y - direction * excursion)

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
    lane_rank: int,
    canvas_width: int,
    canvas_height: int,
    intent: str,
    process_row_gap: int = _PROCESS_ROW_GAP,
    non_process_row_gap: int = _ROW_GAP,
    long_branch_slot: int | None = None,
    long_branch_count: int = 0,
    long_branch_label_y: float | None = None,
    anchored_branch_gutter_x: float | None = None,
    long_vertical_gutter_x: float | None = None,
    long_vertical_label_y: float | None = None,
    process_branch_gutter_x: float | None = None,
    process_adjacent_slot: int | None = None,
    process_adjacent_count: int = 0,
    process_adjacent_label_y: float | None = None,
    row_corridor_label_x: float | None = None,
    narrative_parallel_gutter_x: float | None = None,
    narrative_self_loop_gutter_x: float | None = None,
    generic_self_loop_gutter_x: float | None = None,
    self_loop_lane: int | None = None,
    feedback_slot: int | None = None,
    feedback_count: int = 0,
    feedback_base_bottom: float | None = None,
    force_feedback_footer: bool = False,
) -> list[str]:
    kind = str(edge["kind"])
    color, dash, width = _EDGE_STYLE[kind]
    lane_step = _PROCESS_LANE_STEP if intent == "process" else 8
    if self_loop_lane is not None:
        lane = self_loop_lane
    elif (
        intent == "process"
        and kind != "feedback"
        and process_adjacent_slot is not None
        and process_adjacent_count > 1
    ):
        centered_slot = process_adjacent_slot - (process_adjacent_count - 1) / 2
        lane = int(centered_slot * lane_step)
    elif kind == "feedback" and feedback_slot is not None and feedback_count > 1:
        centered_slot = feedback_slot - (feedback_count - 1) / 2
        lane = int(centered_slot * lane_step)
    else:
        lane = ((lane_rank % 5) - 2) * lane_step
    source_position = positions[str(edge["from"])]
    target_position = positions[str(edge["to"])]

    metrics = _edge_label_metrics(edge, positions, intent)
    label_size = metrics.size
    label_line_height = metrics.line_height
    label_lines = metrics.lines
    label_width = metrics.width
    label_height = metrics.height
    allow_glyph_compression = metrics.allow_glyph_compression

    max_node_bottom = max(y + _NODE_HEIGHT for _, y in positions.values())
    feedback_origin_bottom = (
        feedback_base_bottom if feedback_base_bottom is not None else max_node_bottom
    )
    feedback_label_y = None
    if (
        kind == "feedback"
        and intent == "narrative"
        and feedback_slot is not None
        and feedback_count == 1
    ):
        # A one-line narrative feedback relation reads cleanly as a
        # return-to-origin cue in the narrow header strip. Wrapped feedback
        # labels cannot fit there without covering the purpose block, so they
        # use the already-reserved footer instead.
        if label_height <= 28:
            feedback_label_y = _NARRATIVE_SINGLE_FEEDBACK_TOP_Y
        else:
            feedback_label_y = (
                feedback_origin_bottom
                + _NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE
                + label_height / 2
            )
    elif (
        kind == "feedback"
        and feedback_slot is not None
        and (
            intent != "process"
            or feedback_count > 1
            or force_feedback_footer
        )
    ):
        feedback_label_y = (
            feedback_origin_bottom
            + 10
            + feedback_slot * _FEEDBACK_LABEL_LANE_STEP
            + label_height / 2
        )
    preserve_same_row_feedback_footer = (
        edge["from"] != edge["to"]
        and _preserve_same_row_process_feedback_return(
            source_position, target_position, positions
        )
    )


    path, label_x, label_y, route = _edge_geometry(
        source_position,
        target_position,
        self_loop=edge["from"] == edge["to"],
        lane=lane,
        kind=kind,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        intent=intent,
        process_row_gap=process_row_gap,
        non_process_row_gap=non_process_row_gap,
        long_branch_slot=long_branch_slot,
        long_branch_count=long_branch_count,
        long_branch_label_y=long_branch_label_y,
        anchored_branch_gutter_x=anchored_branch_gutter_x,
        long_vertical_gutter_x=long_vertical_gutter_x,
        long_vertical_label_y=long_vertical_label_y,
        process_branch_gutter_x=process_branch_gutter_x,
        narrative_parallel_gutter_x=narrative_parallel_gutter_x,
        narrative_self_loop_gutter_x=narrative_self_loop_gutter_x,
        generic_self_loop_gutter_x=generic_self_loop_gutter_x,
        label_height=label_height,
        label_width=label_width,
        feedback_label_y=feedback_label_y,
        max_node_bottom=max_node_bottom,
        preserve_same_row_feedback_footer=preserve_same_row_feedback_footer,
        obstacle_positions=tuple(
            position
            for node_id, position in positions.items()
            if node_id not in {str(edge["from"]), str(edge["to"])}
        ),
    )
    dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
    path_opacity_attribute = (
        ' stroke-opacity="0.42"'
        if intent == "narrative" and kind == "feedback" and feedback_count == 1
        else ""
    )
    marker_attribute = "" if kind == "association" else f' marker-end="url(#native-arrow-{kind})"'
    same_process_row = (
        intent == "process"
        and source_position[1] == target_position[1]
        and (
            route == "standard"
            or (
                route == "process-row-gutter"
                and source_position[1] == min(y for _, y in positions.values())
            )
        )
    )
    if same_process_row:
        # A first-row gutter label shares the header rail's safe vertical slot;
        # centering a wrapped box on the path could cover the purpose block.
        row_top = min(source_position[1], target_position[1])
        if process_adjacent_label_y is not None:
            label_y = process_adjacent_label_y
        elif label_height > 29:
            label_y = row_top - label_height / 2 - 4
        else:
            # Keep the accepted one-line placement byte-for-byte.
            label_y = row_top - 18
        if edge["from"] == edge["to"] and process_branch_gutter_x is not None:
            # Conflicting loop labels use the packed outer lane while their
            # Bezier arcs keep distinct semantic lanes, including overflow stacks.
            label_x = process_branch_gutter_x + 8 + label_width / 2
    if (
        intent != "process"
        and kind != "feedback"
        and route != "narrative-parallel"
        and source_position[0] != target_position[0]
        and source_position[1] != target_position[1]
    ):
        node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
        left_card_right = min(source_position[0], target_position[0]) + node_width
        right_card_left = max(source_position[0], target_position[0])
        upper_card_bottom = min(source_position[1], target_position[1]) + _NODE_HEIGHT
        lower_card_top = max(source_position[1], target_position[1])
        horizontal_clearance = right_card_left - left_card_right
        vertical_clearance = lower_card_top - upper_card_bottom
        if (
            intent == "narrative"
            and _ROW_GAP <= vertical_clearance <= _NON_PROCESS_ROW_GAP
            and vertical_clearance >= label_height + 4
        ):
            # An adjacent-row vertical corridor is sufficient even when the label
            # is wider than the inter-column gap. Multi-row relations keep their
            # narrow horizontal channel because intervening cards occupy the rows.
            label_y = (upper_card_bottom + lower_card_top) / 2
        elif (
            horizontal_clearance >= label_width + 8
            and vertical_clearance >= label_height + 8
        ):
            label_x = (left_card_right + right_card_left) / 2
            label_y = (upper_card_bottom + lower_card_top) / 2
    if (
        intent == "process"
        and route in {"process-branch", "vertical"}
        and source_position[1] != target_position[1]
        and abs(source_position[1] - target_position[1])
        <= _NODE_HEIGHT + process_row_gap
    ):
        upper_bottom = min(source_position[1], target_position[1]) + _NODE_HEIGHT
        lower_top = max(source_position[1], target_position[1])
        if process_adjacent_label_y is not None:
            label_y = process_adjacent_label_y
        elif lower_top - upper_bottom >= label_height + 8:
            label_y = (upper_bottom + lower_top) / 2
    if (
        intent != "process"
        and route != "narrative-parallel"
        and row_corridor_label_x is not None
    ):
        label_x = row_corridor_label_x
    if edge["from"] == edge["to"] and intent != "process" and route == "standard":
        # A generic Bezier self-loop owns its arc geometry, but its label must
        # clear the card independently of the lane reach. Use the rendered
        # label width rather than inflating the loop lane, which could merely
        # move the collision to a neighbouring card.
        node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
        half_label_width = label_width / 2
        label_x = max(
            label_x,
            source_position[0] + node_width + half_label_width + 8,
        )
    if intent == "process" and route == "standard":
        # Self-loops can place their Bézier midpoint beyond the rightmost card.
        # Clamp only the label box; in-bounds standard labels remain unchanged.
        half_label_width = label_width / 2
        label_x = min(
            max(label_x, half_label_width + 8),
            canvas_width - half_label_width - 8,
        )
    if kind == "feedback":
        half_label_width = label_width / 2
        label_x = min(
            max(label_x, half_label_width + 8),
            canvas_width - half_label_width - 8,
        )
    if route == "vertical" and kind != "feedback":
        # Vertical labels sit to the right of their edge. Clamp only when the
        # computed label box would leave the SVG canvas; normal placement stays
        # byte-for-byte unchanged.
        half_label_width = label_width / 2
        label_x = min(
            max(label_x, half_label_width + 8),
            canvas_width - half_label_width - 8,
        )
    label_top = label_y - label_height / 2
    # Short process labels should remain natural text when they already fit.
    # Give their clip guard 2 px more breathing room per side instead of
    # forcing glyph compression merely because the estimate was optimistic.
    clip_padding = metrics.clip_padding
    source_id = str(edge["id"])
    source_id_xml = _xml_escape(source_id)
    kind_xml = _xml_escape(kind)
    clip_id = f"native-clip-edge-{source_id}"
    lines = [
        f'<g id="native-edge-{source_id_xml}" data-source-kind="edge" '
        f'data-source-id="{source_id_xml}" data-kind="{kind_xml}" '
        f'data-route="{route}">',
        _clip_definition(
            clip_id,
            x=label_x - label_width / 2 + clip_padding,
            y=label_top + 3,
            width=label_width - 2 * clip_padding,
            height=label_height - 6,
        ),
        f"<title>{_xml_escape(str(edge['label']))}</title>",
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width:.1f}" '
        f'stroke-linecap="round" stroke-linejoin="round"{dash_attribute}'
        f'{path_opacity_attribute}{marker_attribute}/>',
        f'<rect x="{label_x - label_width / 2:.1f}" y="{label_top:.1f}" '
        f'width="{label_width}" height="{label_height}" rx="9" fill="#f8fafc" '
        'fill-opacity="0.94"/>',
    ]
    lines.extend(
        _svg_text_lines(
            label_lines,
            x=label_x,
            y=label_top + (20 if intent in {"process", "narrative"} else 18),
            line_height=label_line_height,
            size=label_size,
            weight=600,
            color=color,
            anchor="middle",
            max_width=label_width - 2 * clip_padding,
            clip_id=clip_id,
            allow_glyph_compression=allow_glyph_compression,
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
    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
    label_size = 22
    label_line_height = 23
    if intent == "process":
        summary_size = 19
        summary_line_height = 20
        label_lines = _wrapped(str(node["label"]), width=20, limit=2)
        summary_lines = _wrapped(str(node["summary"]), width=28, limit=3)
        summary_y = y + 61 + len(label_lines) * label_line_height
    else:
        # Natural wrapping is preferable to horizontal glyph compression. Knowledge
        # maps can retain the accepted 17 px scale without losing Golden-case copy.
        summary_size = 19 if intent == "narrative" else (17 if intent == "knowledge_map" else 16)
        summary_line_height = 19 if intent == "narrative" else summary_size
        label_lines = _bounded_wrapped(
            str(node["label"]),
            width=24 if intent == "narrative" else 20,
            limit=2,
            size=label_size,
            max_width=node_width - 36,
        )
        summary_y = y + 57 + len(label_lines) * label_line_height
        available_lines = max(
            1,
            int((y + _NODE_HEIGHT - 6 - summary_y) // summary_line_height) + 1,
        )
        summary_lines = _bounded_wrapped(
            str(node["summary"]),
            # Narrative copy should be packed by the same pixel-width estimator
            # that guards the SVG clip. A character-count pre-wrap can create
            # avoidable one-word orphan lines even when the next visual line has
            # ample room.
            width=1000 if intent == "narrative" else 28,
            limit=available_lines,
            size=summary_size,
            max_width=node_width - 36,
        )
        if intent == "narrative":
            summary_lines = _rebalance_single_word_lines(
                summary_lines,
                size=summary_size,
                max_width=node_width - 36,
            )
    source_id_xml = _xml_escape(source_id)
    kind_xml = _xml_escape(kind)
    clip_id = f"native-clip-node-{source_id}"
    lines = [
        f'<g id="native-node-{source_id_xml}" data-source-kind="node" '
        f'data-source-id="{source_id_xml}" data-kind="{kind_xml}">',
        _clip_definition(
            clip_id,
            x=x + 18,
            y=y + 32,
            width=node_width - 36,
            height=_NODE_HEIGHT - 34,
        ),
        f"<title>{_xml_escape(str(node['label']))}</title>",
        f'<rect x="{x}" y="{y}" width="{node_width}" height="{_NODE_HEIGHT}" '
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
            max_width=node_width - 36,
            clip_id=clip_id,
            allow_glyph_compression=intent == "process",
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
            max_width=node_width - 36,
            clip_id=clip_id,
            allow_glyph_compression=intent == "process",
        )
    )
    lines.append("</g>")
    return lines


def render_native_diagram(value: Mapping[str, Any]) -> str:
    """Validate representation input and return one deterministic, standalone SVG."""

    model = _normalized_input(value)
    positions, regions, width, height = _layout(model)
    intent = str(model["intent"])
    process_row_gap = _PROCESS_ROW_GAP if regions else _NON_PROCESS_ROW_GAP
    if intent == "process":
        # Standard same-row process labels sit above their cards. One-line
        # labels already fit the established header gap, but a two-line label
        # needs extra headroom so it clears both the purpose block and cards.
        same_row_label_heights = [
            29 + max(0, len(_wrapped(str(edge["label"]), width=24, limit=2)) - 1) * 19
            for edge in model["edges"]
            if str(edge["kind"]) != "feedback"
            and positions[str(edge["from"])][1] == positions[str(edge["to"])][1]
        ]
        if same_row_label_heights:
            tallest_label = max(same_row_label_heights)
            if tallest_label > 29:
                purpose_bottom = 104
                required_first_row_top = purpose_bottom + 8 + tallest_label
                if regions:
                    # Group headers occupy the first 44 px of each region.
                    # A two-line same-row label sits `label_height + 4` above
                    # its card, so reserve another 8 px below the separator.
                    group_header_bottom = max(
                        region_y + 44 for _, _, _, region_y, _, _ in regions
                    )
                    required_first_row_top = max(
                        required_first_row_top,
                        group_header_bottom + 12 + tallest_label,
                    )
                first_row_top = min(y for _, y in positions.values())
                top_shift = max(0, required_first_row_top - first_row_top)
                if top_shift:
                    positions = {
                        node_id: (x, y + top_shift)
                        for node_id, (x, y) in positions.items()
                    }
                    if regions:
                        regions = [
                            (group_id, label, x, y, region_width, region_height + top_shift)
                            for group_id, label, x, y, region_width, region_height in regions
                        ]
                    height += top_shift
    non_process_row_gap = _ROW_GAP if regions else _NON_PROCESS_ROW_GAP
    long_vertical_gutter_x: dict[str, float] = {}
    long_vertical_label_y: dict[str, float] = {}
    packed_process_label_bounds: list[tuple[float, float, float, float]] = []
    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
    vertical_row_gap = process_row_gap if intent == "process" else non_process_row_gap
    row_step = _NODE_HEIGHT + vertical_row_gap
    corridor_use_count: dict[tuple[int, float], int] = defaultdict(int)
    corridor_groups: dict[
        tuple[int, float],
        list[tuple[float, str, int, int]],
    ] = defaultdict(list)
    for edge in model["edges"]:
        if str(edge["kind"]) == "feedback":
            continue
        source = positions[str(edge["from"])]
        target = positions[str(edge["to"])]
        if edge["from"] == edge["to"]:
            # A process self-loop parks its label in the same-row slot above its
            # card. That is the very corridor a long same-column relation would
            # otherwise occupy at this column, and neither label can be moved
            # inside it, so count the self-loop as a corridor user.
            if intent == "process" and _process_row_corridor_bounds(
                source[1], positions, direction=-1
            ) is not None:
                corridor_use_count[
                    (source[0], source[1] - vertical_row_gap / 2)
                ] += 1
            continue
        if source[0] != target[0] or source[1] == target[1]:
            continue
        direction = 1 if source[1] < target[1] else -1
        start_y = source[1] + _NODE_HEIGHT if direction > 0 else source[1]
        source_corridor_y = start_y + direction * vertical_row_gap / 2
        corridor_key = (source[0], source_corridor_y)
        corridor_use_count[corridor_key] += 1
        if abs(target[1] - source[1]) <= row_step:
            continue
        end_y = target[1] if direction > 0 else target[1] + _NODE_HEIGHT
        target_corridor_y = end_y - direction * vertical_row_gap / 2
        natural_y = (source_corridor_y + target_corridor_y) / 2
        metrics = _edge_label_metrics(edge, positions, intent)
        label_width = metrics.width
        label_height = metrics.height
        corridor_groups[corridor_key].append(
            (natural_y, str(edge["id"]), label_width, label_height)
        )

    shared_long_verticals = [
        item
        for corridor_key, items in corridor_groups.items()
        if corridor_use_count[corridor_key] > 1
        for item in items
    ]
    long_vertical_pack_bottom = 0.0
    if shared_long_verticals:
        obstacle_right = max(x + node_width for x, _ in positions.values())
        if regions:
            obstacle_right = max(
                obstacle_right,
                max(x + region_width for _, _, x, _, region_width, _ in regions),
            )
        previous_bottom = 0.0
        required_right = float(width)
        for slot, (natural_y, edge_id, label_width, label_height) in enumerate(
            sorted(shared_long_verticals, key=lambda item: (item[0], item[1]))
        ):
            gutter_x = obstacle_right + 12.0 + slot * _PROCESS_GUTTER_LANE_STEP
            packed_y = max(
                natural_y,
                previous_bottom + 8 + label_height / 2,
            )
            long_vertical_gutter_x[edge_id] = gutter_x
            long_vertical_label_y[edge_id] = packed_y
            previous_bottom = packed_y + label_height / 2
            if intent == "process":
                packed_process_label_bounds.append(
                    (
                        gutter_x + 8,
                        packed_y - label_height / 2,
                        gutter_x + 8 + label_width,
                        previous_bottom,
                    )
                )
            required_right = max(
                required_right,
                gutter_x + 8 + label_width + _PAGE_MARGIN,
            )
        width = max(width, math.ceil(required_right))
        long_vertical_pack_bottom = previous_bottom
        height = max(height, math.ceil(previous_bottom + 8))

    row_corridor_label_x: dict[str, float] = {}
    if intent != "process":
        row_corridor_groups: dict[
            float,
            list[tuple[float, str, int, int]],
        ] = defaultdict(list)
        adjacent_step = _NODE_HEIGHT + non_process_row_gap
        # A singleton long same-column relation still consumes its source row
        # corridor even though it does not need the shared outer-gutter packer.
        # Register its natural label box here so adjacent-row labels occupying
        # the same physical corridor are packed against it as well.
        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            edge_id = str(edge["id"])
            if (
                source[0] != target[0]
                or source[1] == target[1]
                or abs(target[1] - source[1]) <= adjacent_step
                or edge_id in long_vertical_gutter_x
            ):
                continue
            direction = 1 if source[1] < target[1] else -1
            start_y = source[1] + _NODE_HEIGHT if direction > 0 else source[1]
            corridor_y = start_y + direction * non_process_row_gap / 2
            metrics = _edge_label_metrics(edge, positions, intent)
            center_x = source[0] + node_width / 2
            default_gutter_x = source[0] + node_width + _CORRIDOR_GUTTER_OFFSET
            natural_x = (center_x + default_gutter_x) / 2
            row_corridor_groups[corridor_y].append(
                (natural_x, edge_id, metrics.width, metrics.height)
            )

        # A long diagonal spanning an odd number of rows renders its label in
        # the middle physical corridor rather than over an intervening card.
        # Register it there so adjacent-row labels are packed against it.
        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if (
                source[0] == target[0]
                or source[1] == target[1]
                or abs(target[1] - source[1]) <= adjacent_step
            ):
                continue
            metrics = _edge_label_metrics(edge, positions, intent)
            left_card_right = min(source[0], target[0]) + node_width
            right_card_left = max(source[0], target[0])
            upper_bottom = min(source[1], target[1]) + _NODE_HEIGHT
            lower_top = max(source[1], target[1])
            if (
                right_card_left - left_card_right < metrics.width + 8
                or lower_top - upper_bottom < metrics.height + 8
            ):
                continue
            label_y = (upper_bottom + lower_top) / 2
            corridor = _row_corridor_containing(label_y, positions)
            if corridor is None:
                continue
            row_corridor_groups[(corridor[0] + corridor[1]) / 2].append(
                (
                    (left_card_right + right_card_left) / 2,
                    str(edge["id"]),
                    metrics.width,
                    metrics.height,
                )
            )

        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if (
                source[1] == target[1]
                or abs(target[1] - source[1]) > adjacent_step
            ):
                continue
            vertical = source[0] == target[0]
            metrics = _edge_label_metrics(edge, positions, intent)
            label_width = metrics.width
            label_height = metrics.height
            upper_bottom = min(source[1], target[1]) + _NODE_HEIGHT
            lower_top = max(source[1], target[1])
            vertical_clearance = lower_top - upper_bottom
            if vertical:
                if vertical_clearance < label_height:
                    continue
                natural_x = source[0] + node_width / 2
            else:
                left_card_right = min(source[0], target[0]) + node_width
                right_card_left = max(source[0], target[0])
                horizontal_clearance = right_card_left - left_card_right
                narrative_corridor = (
                    intent == "narrative"
                    and _ROW_GAP <= vertical_clearance <= _NON_PROCESS_ROW_GAP
                    and vertical_clearance >= label_height + 4
                )
                generic_corridor = (
                    horizontal_clearance >= label_width + 8
                    and vertical_clearance >= label_height + 8
                )
                if not (narrative_corridor or generic_corridor):
                    continue
                natural_x = (left_card_right + right_card_left) / 2
            corridor_y = (upper_bottom + lower_top) / 2
            row_corridor_groups[corridor_y].append(
                (natural_x, str(edge["id"]), label_width, label_height)
            )

        feedback_channel_segments: list[tuple[float, float]] = []
        if intent == "knowledge_map":
            channel_offset = 28.0
            for edge in model["edges"]:
                if str(edge["kind"]) != "feedback" or edge["from"] == edge["to"]:
                    continue
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                start_y = source[1] + _NODE_HEIGHT / 2
                end_y = target[1] + _NODE_HEIGHT / 2
                if source[0] > target[0]:
                    start_x = source[0] + node_width
                    end_x = target[0]
                    source_channel_x = min(width - 16.0, start_x + channel_offset)
                    target_channel_x = max(16.0, end_x - channel_offset)
                elif source[0] < target[0]:
                    start_x = source[0]
                    end_x = target[0] + node_width
                    source_channel_x = max(16.0, start_x - channel_offset)
                    target_channel_x = min(width - 16.0, end_x + channel_offset)
                else:
                    start_x = source[0] + node_width
                    source_channel_x = target_channel_x = min(
                        width - 16.0, start_x + channel_offset
                    )
                feedback_channel_segments.extend(
                    ((source_channel_x, start_y), (target_channel_x, end_y))
                )

        def clear_feedback_channels(
            center_x: float, label_width: int, label_height: int, corridor_y: float
        ) -> float:
            half_width = label_width / 2
            half_height = label_height / 2
            adjusted_x = center_x
            for channel_x, endpoint_y in sorted(feedback_channel_segments):
                if corridor_y + half_height < endpoint_y:
                    continue
                if (
                    adjusted_x - half_width < channel_x + 8
                    and adjusted_x + half_width > channel_x - 8
                ):
                    left_x = channel_x - 8 - half_width
                    right_x = channel_x + 8 + half_width
                    candidates = [
                        candidate
                        for candidate in (left_x, right_x)
                        if half_width + 8 <= candidate <= width - half_width - 8
                    ]
                    if candidates:
                        adjusted_x = min(
                            candidates, key=lambda candidate: abs(candidate - adjusted_x)
                        )
            return adjusted_x

        required_right = float(width)
        for corridor_y, items in row_corridor_groups.items():
            adjusted_items = []
            for natural_x, edge_id, label_width, label_height in items:
                adjusted_x = clear_feedback_channels(
                    natural_x, label_width, label_height, corridor_y
                )
                if adjusted_x != natural_x:
                    row_corridor_label_x[edge_id] = adjusted_x
                adjusted_items.append(
                    (adjusted_x, edge_id, label_width, label_height)
                )
            if len(adjusted_items) <= 1:
                if adjusted_items:
                    natural_x, _, label_width, _ = adjusted_items[0]
                    required_right = max(
                        required_right, natural_x + label_width / 2 + _PAGE_MARGIN
                    )
                continue
            previous_right: float | None = None
            for natural_x, edge_id, label_width, _ in sorted(
                adjusted_items, key=lambda item: (item[0], item[1])
            ):
                packed_x = natural_x
                if (
                    previous_right is not None
                    and natural_x - label_width / 2 < previous_right + 8
                ):
                    packed_x = previous_right + 8 + label_width / 2
                    row_corridor_label_x[edge_id] = packed_x
                previous_right = packed_x + label_width / 2
                required_right = max(
                    required_right, previous_right + _PAGE_MARGIN
                )
        if row_corridor_label_x:
            width = max(width, math.ceil(required_right))

    process_branch_gutter_x: dict[str, float] = {}
    anchored_branch_gutter_x: dict[str, float] = {}
    process_adjacent_slot: dict[str, int] = {}
    process_adjacent_count: dict[str, int] = {}
    process_adjacent_label_y: dict[str, float] = {}
    occupied_process_adjacent_corridors: set[tuple[int, int]] = set()
    process_outer_label_right = max(
        (right for _, _, right, _ in packed_process_label_bounds),
        default=0.0,
    )
    if intent == "process":
        process_lane_ranks = _stable_lane_ranks(model)
        long_branch_ids = _process_long_branch_ids(
            model, positions, process_row_gap=process_row_gap
        )
        if len(long_branch_ids) == 1:
            # A singleton long branch is canvas-relative, so bind its gutter to
            # the planning width before any unrelated outer-lane allocation can
            # enlarge the final canvas and move the accepted route underneath it.
            anchored_branch_gutter_x[long_branch_ids[0]] = (
                width - _PROCESS_EDGE_GUTTER / 2
            )
        header_corridor = (
            max([104, *(y + 44 for _, _, _, y, _, _ in regions)]),
            min(y for _, y in positions.values()),
        )
        unsafe_adjacent_branches: set[str] = set()
        unsafe_corridors: set[tuple[int, int]] = set()
        process_adjacent_step = _NODE_HEIGHT + process_row_gap
        edges_by_id = {str(edge["id"]): edge for edge in model["edges"]}
        corridor_groups: dict[
            tuple[int, int],
            list[tuple[float, str, float, int, bool]],
        ] = defaultdict(list)
        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if source[1] == target[1]:
                corridor = _process_label_corridor_above(
                    source[1], positions, header_corridor=header_corridor
                )
            elif abs(target[1] - source[1]) <= process_adjacent_step:
                upper_bottom = min(source[1], target[1]) + _NODE_HEIGHT
                lower_top = max(source[1], target[1])
                if lower_top <= upper_bottom:
                    continue
                corridor = (upper_bottom, lower_top)
            else:
                continue
            occupied_process_adjacent_corridors.add(corridor)
            metrics = _edge_label_metrics(edge, positions, intent)
            natural_x = (source[0] + target[0] + _NODE_WIDTH) / 2
            corridor_groups[corridor].append(
                (natural_x, str(edge["id"]), float(metrics.width), metrics.height, False)
            )

        anchored_corridor_labels = _process_anchored_corridor_labels(
            model,
            positions,
            process_row_gap=process_row_gap,
            long_vertical_gutter_x=long_vertical_gutter_x,
            canvas_width=width,
            header_corridor=header_corridor,
        )
        for corridor, natural_x, edge_id, label_width, label_height in (
            anchored_corridor_labels
        ):
            # Anchored labels are physical corridor occupants like every other
            # corridor user, so feedback routing has to see them here as well.
            occupied_process_adjacent_corridors.add(corridor)
            corridor_groups[corridor].append(
                (natural_x, edge_id, label_width, label_height, True)
            )

        for corridor, items in corridor_groups.items():
            upper_bottom, lower_top = corridor
            available_height = lower_top - upper_bottom
            ordered = sorted(items, key=lambda item: (item[0], item[1]))
            clusters: list[list[tuple[float, str, float, int, bool]]] = []
            current: list[tuple[float, str, float, int, bool]] = []
            current_right: float | None = None
            for item in ordered:
                natural_x, _, label_width, _, _ = item
                left = natural_x - label_width / 2
                right = natural_x + label_width / 2
                if current and current_right is not None and left >= current_right + 8:
                    clusters.append(current)
                    current = []
                    current_right = None
                current.append(item)
                current_right = right if current_right is None else max(current_right, right)
            if current:
                clusters.append(current)

            for cluster in clusters:
                cluster = sorted(cluster, key=lambda item: item[1])
                movable = [item for item in cluster if not item[4]]
                if len(movable) != len(cluster):
                    # Keep self-loop envelopes and fixed-column anchors before
                    # canvas-relative long branches: growing an outer gutter
                    # must not shift the anchor that the other labels yield to.
                    anchored = sorted(
                        (item for item in cluster if item[4]),
                        key=lambda item: (
                            edges_by_id[item[1]]["from"] != edges_by_id[item[1]]["to"],
                            positions[str(edges_by_id[item[1]]["from"])][0]
                            != positions[str(edges_by_id[item[1]]["to"])][0],
                            _process_anchor_order_key(edges_by_id[item[1]]),
                        ),
                    )
                    retained: list[tuple[float, str, float, int, bool]] = []
                    for item in anchored:
                        natural_x, edge_id, label_width, _, _ = item
                        if any(
                            natural_x - label_width / 2 < other_x + other_width / 2
                            and natural_x + label_width / 2 > other_x - other_width / 2
                            for other_x, _, other_width, _, _ in retained
                        ):
                            # Only a real overlap displaces an anchor, not the
                            # extra 8 px clearance used to form packing clusters.
                            movable.append(item)
                        else:
                            retained.append(item)
                    # Movable and conflicting anchored occupants share the
                    # existing deterministic outer-gutter allocator.
                    unsafe_adjacent_branches.update(item[1] for item in movable)
                    if movable:
                        unsafe_corridors.add(corridor)
                    continue
                count = len(cluster)
                if count == 1:
                    _, edge_id, _, label_height, _ = cluster[0]
                    # The header already reserves the established singleton
                    # slot; only collisions there require a geometry change.
                    if corridor != header_corridor and label_height + 8 > available_height:
                        unsafe_adjacent_branches.add(edge_id)
                        unsafe_corridors.add(corridor)
                    continue
                for slot, (_, edge_id, _, _, _) in enumerate(cluster):
                    process_adjacent_slot[edge_id] = slot
                    process_adjacent_count[edge_id] = count
                required_height = (
                    sum(item[3] for item in cluster) + 8 * (count - 1)
                )
                if required_height <= available_height:
                    cursor_y = upper_bottom + (available_height - required_height) / 2
                    for _, edge_id, _, label_height, _ in cluster:
                        process_adjacent_label_y[edge_id] = cursor_y + label_height / 2
                        cursor_y += label_height + 8
                else:
                    unsafe_adjacent_branches.update(item[1] for item in cluster)
                    unsafe_corridors.add(corridor)

        # Short labels may be horizontally disjoint from one another while still
        # masking a sibling branch line. Prefer the branch's own vertical lane
        # inside the existing row gap; only fall back to the outer gutter when
        # the gap cannot provide real clearance.
        def adjacent_route_y(edge_id: str, corridor: tuple[int, int]) -> float:
            count = process_adjacent_count.get(edge_id, 0)
            slot = process_adjacent_slot.get(edge_id)
            if slot is not None and count > 1:
                centered_slot = slot - (count - 1) / 2
                lane = int(centered_slot * _PROCESS_LANE_STEP)
            else:
                lane = (
                    (process_lane_ranks[edge_id] % 5) - 2
                ) * _PROCESS_LANE_STEP
            lane_offset = max(-8.0, min(8.0, lane / 2))
            return (corridor[0] + corridor[1]) / 2 + lane_offset

        for corridor, items in corridor_groups.items():
            corridor_center = (corridor[0] + corridor[1]) / 2
            movable_items = [item for item in items if not item[4]]
            for natural_x, edge_id, label_width, label_height, _ in movable_items:
                if edge_id in process_adjacent_label_y:
                    continue
                edge = edges_by_id[edge_id]
                half_width = label_width / 2
                half_height = label_height / 2
                label_left = natural_x - half_width
                label_right = natural_x + half_width
                endpoints = {str(edge["from"]), str(edge["to"])}
                own_route_y = adjacent_route_y(edge_id, corridor)
                lower_bound = corridor[0] + half_height + 2
                upper_bound = corridor[1] - half_height - 2
                masks_peer = False
                for _, peer_id, _, _, _ in movable_items:
                    if peer_id == edge_id:
                        continue
                    peer = edges_by_id[peer_id]
                    if not endpoints.intersection(
                        {str(peer["from"]), str(peer["to"])}
                    ):
                        continue
                    peer_source = positions[str(peer["from"])]
                    peer_target = positions[str(peer["to"])]
                    peer_left = min(peer_source[0], peer_target[0]) + _NODE_WIDTH / 2
                    peer_right = max(peer_source[0], peer_target[0]) + _NODE_WIDTH / 2
                    if label_right <= peer_left or label_left >= peer_right:
                        continue
                    peer_route_y = adjacent_route_y(peer_id, corridor)
                    if not (
                        corridor_center - half_height
                        < peer_route_y
                        < corridor_center + half_height
                    ):
                        continue
                    masks_peer = True
                    if own_route_y < peer_route_y:
                        upper_bound = min(
                            upper_bound, peer_route_y - half_height - 2
                        )
                    elif own_route_y > peer_route_y:
                        lower_bound = max(
                            lower_bound, peer_route_y + half_height + 2
                        )
                    else:
                        lower_bound = upper_bound + 1
                        break
                if not masks_peer:
                    continue
                if lower_bound <= upper_bound:
                    process_adjacent_label_y[edge_id] = min(
                        max(own_route_y, lower_bound), upper_bound
                    )
                else:
                    unsafe_adjacent_branches.add(edge_id)
                    unsafe_corridors.add(corridor)

        if unsafe_adjacent_branches:
            obstacle_right = max(x + _NODE_WIDTH for x, _ in positions.values())
            if regions:
                obstacle_right = max(
                    obstacle_right,
                    max(x + region_width for _, _, x, _, region_width, _ in regions),
                )
            # Outer-gutter lanes share the corridor y of the labels they take
            # over, so they must also clear anchored labels reaching past the
            # card column in exactly those corridors.
            for corridor, natural_x, _, label_width, _ in anchored_corridor_labels:
                if corridor in unsafe_corridors:
                    obstacle_right = max(obstacle_right, natural_x + label_width / 2)
            cursor = max(obstacle_right + 12.0, width - _PAGE_MARGIN + 12.0)
            required_right = float(width)
            for edge_id in sorted(
                unsafe_adjacent_branches,
                key=lambda edge_id: _process_anchor_order_key(edges_by_id[edge_id]),
            ):
                process_branch_gutter_x[edge_id] = cursor
                actual_label_right = (
                    cursor
                    + 8
                    + _edge_label_metrics(edges_by_id[edge_id], positions, intent).width
                )
                process_outer_label_right = max(
                    process_outer_label_right, actual_label_right
                )
                # Keep the established fixed-width lane reservation so existing
                # process-gutter geometry does not move merely because this
                # cross-packer occupancy bound became explicit.
                label_right = cursor + 8 + _PROCESS_LABEL_MAX_WIDTH
                required_right = max(required_right, label_right + _PAGE_MARGIN)
                cursor = label_right + 12
            width = max(width, math.ceil(required_right))

    generic_self_loop_gutter_x: dict[str, float] = {}
    if intent not in {"process", "narrative"}:
        generic_self_loops: list[Mapping[str, Any]] = []
        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] != edge["to"]:
                continue
            source_id = str(edge["from"])
            source_x, source_y = positions[source_id]
            metrics = _edge_label_metrics(edge, positions, intent)
            natural_left = source_x + node_width + 8
            natural_right = natural_left + metrics.width
            collides_with_peer = any(
                node_id != source_id
                and node_y == source_y
                and natural_left < node_x + node_width
                and natural_right > node_x
                for node_id, (node_x, node_y) in positions.items()
            )
            if collides_with_peer or natural_right > width - 8:
                generic_self_loops.append(edge)
        if generic_self_loops:
            obstacle_right = max(x + node_width for x, _ in positions.values())
            if regions:
                obstacle_right = max(
                    obstacle_right,
                    max(x + region_width for _, _, x, _, region_width, _ in regions),
                )
            cursor = max(obstacle_right + 12.0, width - _PAGE_MARGIN + 12.0)
            required_right = float(width)
            required_bottom = float(height)
            for edge in sorted(generic_self_loops, key=lambda item: str(item["id"])):
                metrics = _edge_label_metrics(edge, positions, intent)
                edge_id = str(edge["id"])
                generic_self_loop_gutter_x[edge_id] = cursor
                required_right = max(
                    required_right,
                    cursor + 8 + metrics.width + _PAGE_MARGIN,
                )
                source_y = positions[str(edge["from"])][1]
                corridor_y = source_y + _NODE_HEIGHT + non_process_row_gap / 2
                required_bottom = max(
                    required_bottom,
                    corridor_y + metrics.height / 2 + 8,
                )
                cursor += 8 + metrics.width + 12
            width = max(width, math.ceil(required_right))
            height = max(height, math.ceil(required_bottom))

    narrative_parallel_gutter_x: dict[str, float] = {}
    if intent == "narrative":
        parallel_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
        for edge in model["edges"]:
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            endpoint_key = tuple(sorted((str(edge["from"]), str(edge["to"]))))
            parallel_groups[endpoint_key].append(str(edge["id"]))
        parallel_edge_ids = sorted(
            edge_id
            for edge_ids in parallel_groups.values()
            if len(edge_ids) > 1
            for edge_id in edge_ids
        )
        if parallel_edge_ids:
            obstacle_right = max(x + _NARRATIVE_NODE_WIDTH for x, _ in positions.values())
            if regions:
                obstacle_right = max(
                    obstacle_right,
                    max(x + region_width for _, _, x, _, region_width, _ in regions),
                )
            cursor = max(obstacle_right + 12.0, width - _PAGE_MARGIN + 12.0)
            required_right = float(width)
            for edge_id in parallel_edge_ids:
                narrative_parallel_gutter_x[edge_id] = cursor
                label_right = cursor + 8 + _DIAGONAL_LABEL_MAX_WIDTH
                required_right = max(required_right, label_right + _PAGE_MARGIN)
                cursor = label_right + 12
            width = max(width, math.ceil(required_right))
            same_row_parallel = any(
                positions[str(edge["from"])][1] == positions[str(edge["to"])][1]
                and str(edge["id"]) in narrative_parallel_gutter_x
                for edge in model["edges"]
            )
            if same_row_parallel:
                max_node_bottom = max(y + _NODE_HEIGHT for _, y in positions.values())
                height = max(
                    height,
                    math.ceil(max_node_bottom + non_process_row_gap / 2 + 32),
                )

    narrative_self_loop_gutter_x: dict[str, float] = {}
    if intent == "narrative":
        narrative_self_loops = sorted(
            (
                edge
                for edge in model["edges"]
                if str(edge["kind"]) != "feedback" and edge["from"] == edge["to"]
            ),
            key=lambda edge: str(edge["id"]),
        )
        if narrative_self_loops:
            obstacle_right = max(x + _NARRATIVE_NODE_WIDTH for x, _ in positions.values())
            if regions:
                obstacle_right = max(
                    obstacle_right,
                    max(x + region_width for _, _, x, _, region_width, _ in regions),
                )
            cursor = max(obstacle_right + 12.0, width - _PAGE_MARGIN + 12.0)
            required_right = float(width)
            required_bottom = float(height)
            for edge in narrative_self_loops:
                metrics = _edge_label_metrics(edge, positions, intent)
                label_width = metrics.width
                label_height = metrics.height
                edge_id = str(edge["id"])
                narrative_self_loop_gutter_x[edge_id] = cursor
                required_right = max(
                    required_right,
                    cursor + 8 + label_width + _PAGE_MARGIN,
                )
                source_y = positions[str(edge["from"])][1]
                corridor_y = source_y + _NODE_HEIGHT + non_process_row_gap / 2
                required_bottom = max(
                    required_bottom,
                    corridor_y + label_height / 2 + 8,
                )
                cursor += 8 + label_width + 12
            width = max(width, math.ceil(required_right))
            height = max(height, math.ceil(required_bottom))

    self_loop_lanes = _bezier_self_loop_lanes(
        model,
        intent=intent,
        narrative_self_loop_gutter_x=narrative_self_loop_gutter_x,
    )
    lane_ranks = _stable_lane_ranks(model)

    long_branch_slots: dict[str, int] = {}
    long_branch_label_y: dict[str, float] = {}
    long_branch_pack_bottom = 0.0
    if intent == "process":
        row_step = _NODE_HEIGHT + process_row_gap
        long_branches: list[tuple[float, str, Mapping[str, Any]]] = []
        for edge in model["edges"]:
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if (
                str(edge["kind"]) != "feedback"
                and edge["from"] != edge["to"]
                and source[0] != target[0]
                and source[1] != target[1]
                and abs(target[1] - source[1]) > row_step
            ):
                natural_y = (source[1] + target[1] + _NODE_HEIGHT) / 2
                long_branches.append((natural_y, str(edge["id"]), edge))
        long_branches.sort(key=lambda item: (item[0], item[1]))
        for slot, (_, edge_id, _) in enumerate(long_branches):
            long_branch_slots[edge_id] = slot
        if len(long_branches) > 1:
            required_gutter = (
                _PROCESS_LONG_BRANCH_GUTTER
                + (len(long_branches) - 1) * _PROCESS_GUTTER_LANE_STEP
            )
            width += max(0, required_gutter - _PROCESS_EDGE_GUTTER)
            if process_outer_label_right:
                widest_long_branch_label = max(
                    _edge_label_metrics(edge, positions, intent).width
                    for _, _, edge in long_branches
                )
                # The long-branch packer runs after the adjacent/anchored outer
                # lanes. Keep its whole label column to the right of the actual
                # earlier label extent instead of assuming the historical 80 px
                # edge gutter is still empty.
                width = max(
                    width,
                    math.ceil(
                        process_outer_label_right
                        + 8
                        + widest_long_branch_label / 2
                        + required_gutter / 2
                    ),
                )
            previous_bottom = 0.0
            for natural_y, edge_id, edge in long_branches:
                slot = long_branch_slots[edge_id]
                centered_slot = slot - (len(long_branches) - 1) / 2
                stable_lane_offset = max(-8.0, min(8.0, centered_slot * 4.0))
                metrics = _edge_label_metrics(edge, positions, intent)
                label_height = metrics.height
                packed_y = max(
                    natural_y + stable_lane_offset,
                    previous_bottom + 8 + label_height / 2,
                )
                long_branch_label_y[edge_id] = packed_y
                previous_bottom = packed_y + label_height / 2
                label_x = width - required_gutter / 2
                packed_process_label_bounds.append(
                    (
                        label_x - metrics.width / 2,
                        packed_y - label_height / 2,
                        label_x + metrics.width / 2,
                        previous_bottom,
                    )
                )
            long_branch_pack_bottom = previous_bottom
            height = max(height, math.ceil(previous_bottom + 8))
    feedback_edges = sorted(
        (edge for edge in model["edges"] if str(edge["kind"]) == "feedback"),
        key=lambda edge: (
            min(str(edge["from"]), str(edge["to"])),
            max(str(edge["from"]), str(edge["to"])),
            str(edge["id"]),
        ),
    )
    feedback_slots = {str(edge["id"]): slot for slot, edge in enumerate(feedback_edges)}
    feedback_footer_ids: set[str] = set()
    if intent == "process" and occupied_process_adjacent_corridors:
        for edge in feedback_edges:
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            feedback_corridors: set[tuple[int, int]] = set()
            if source[1] < target[1]:
                source_corridor = _process_row_corridor_bounds(
                    source[1], positions, direction=1
                )
                target_corridor = _process_row_corridor_bounds(
                    target[1], positions, direction=-1
                )
                if source_corridor is not None:
                    feedback_corridors.add(source_corridor)
                if target_corridor is not None:
                    feedback_corridors.add(target_corridor)
            elif source[1] > target[1]:
                source_corridor = _process_row_corridor_bounds(
                    source[1], positions, direction=-1
                )
                target_corridor = _process_row_corridor_bounds(
                    target[1], positions, direction=1
                )
                if source_corridor is not None:
                    feedback_corridors.add(source_corridor)
                if target_corridor is not None:
                    feedback_corridors.add(target_corridor)
            else:
                if (
                    edge["from"] != edge["to"]
                    and _preserve_same_row_process_feedback_return(
                        source, target, positions
                    )
                ):
                    continue
                source_corridor = _process_row_corridor_bounds(
                    source[1], positions, direction=1
                )
                if source_corridor is not None:
                    feedback_corridors.add(source_corridor)
            if feedback_corridors & occupied_process_adjacent_corridors:
                feedback_footer_ids.add(str(edge["id"]))
    feedback_count = len(feedback_edges)
    feedback_base_bottom = max(y + _NODE_HEIGHT for _, y in positions.values())
    if feedback_count:
        # A single feedback relation keeps the established footer/corridor
        # geometry. Multiple feedback labels receive semantic, id-stable footer
        # lanes so list ordering can never collapse them onto each other.
        max_node_bottom = max(y + _NODE_HEIGHT for _, y in positions.values())
        feedback_base_bottom = (
            max(max_node_bottom, long_branch_pack_bottom, long_vertical_pack_bottom)
            if intent == "process"
            else max_node_bottom
        )
        feedback_heights = [
            _edge_label_metrics(edge, positions, intent).height
            for edge in feedback_edges
        ]
        if feedback_count > 1:
            height = max(
                height,
                math.ceil(
                    feedback_base_bottom
                    + 10
                    + feedback_count * _FEEDBACK_LABEL_LANE_STEP
                    + 8
                ),
            )
        elif intent == "process":
            height = max(
                height,
                math.ceil(feedback_base_bottom + 58 + feedback_heights[0] / 2),
            )
        elif intent == "narrative":
            height = max(
                height,
                max_node_bottom
                + _NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE
                + feedback_heights[0]
                + 8,
            )
        else:
            height = max(height, max_node_bottom + 18 + feedback_heights[0])

    if intent == "process" and feedback_count == 1 and packed_process_label_bounds:
        edge = feedback_edges[0]
        edge_id = str(edge["id"])
        if edge_id not in feedback_footer_ids:
            # Packed labels occupy their rendered rectangles, not every row
            # corridor in the diagram. Check the unforced feedback label after
            # canvas sizing so the accepted reverse return uses its real footer.
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            metrics = _edge_label_metrics(edge, positions, intent)
            _, label_x, label_y, _ = _edge_geometry(
                source,
                target,
                self_loop=edge["from"] == edge["to"],
                lane=((lane_ranks[edge_id] % 5) - 2) * _PROCESS_LANE_STEP,
                kind="feedback",
                canvas_width=width,
                canvas_height=height,
                intent=intent,
                process_row_gap=process_row_gap,
                preserve_same_row_feedback_footer=(
                    edge["from"] != edge["to"]
                    and _preserve_same_row_process_feedback_return(source, target, positions)
                ),
            )
            half_width = metrics.width / 2
            half_height = metrics.height / 2
            label_x = min(max(label_x, half_width + 8), width - half_width - 8)
            if any(
                label_x - half_width < right + 8
                and label_x + half_width > left - 8
                and label_y - half_height < bottom + 8
                and label_y + half_height > top - 8
                for left, top, right, bottom in packed_process_label_bounds
            ):
                feedback_footer_ids.add(edge_id)

    purpose_max_width = width - 2 * _PAGE_MARGIN
    title_lines = _bounded_wrapped(
        str(model["title"]),
        width=max(32, min(96, width // 14)),
        limit=1,
        size=28,
        max_width=purpose_max_width,
    )
    purpose_lines = _bounded_wrapped(
        str(model["purpose"]),
        width=max(72, min(150, width // 9)),
        limit=2,
        size=15,
        max_width=purpose_max_width,
    )
    title_clip_id = "native-clip-title"
    purpose_clip_id = "native-clip-purpose"
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
    lines.append(
        _clip_definition(
            title_clip_id,
            x=_PAGE_MARGIN,
            y=20,
            width=purpose_max_width,
            height=40,
        )
    )
    lines.append(
        _clip_definition(
            purpose_clip_id,
            x=_PAGE_MARGIN,
            y=64,
            width=purpose_max_width,
            height=40,
        )
    )
    lines.extend(
        _svg_text_lines(
            title_lines,
            x=_PAGE_MARGIN,
            y=52,
            line_height=32,
            size=28,
            weight=750,
            color="#172033",
            max_width=purpose_max_width,
            clip_id=title_clip_id,
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
            max_width=purpose_max_width,
            clip_id=purpose_clip_id,
        )
    )

    for region_index, (group_id, label, x, y, region_width, region_height) in enumerate(regions):
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
        group_clip_id = f"native-clip-region-{region_index}"
        lines.append(
            _clip_definition(
                group_clip_id,
                x=x + 20,
                y=y + 10,
                width=region_width - 40,
                height=28,
            )
        )
        group_lines = (
            [label]
            if intent == "process"
            else _bounded_wrapped(
                label,
                width=32,
                limit=1,
                size=16,
                max_width=region_width - 40,
            )
        )
        lines.extend(
            _svg_text_lines(
                group_lines,
                x=x + 20,
                y=y + 29,
                line_height=15,
                size=16,
                weight=700,
                color="#334155",
                max_width=region_width - 40,
                clip_id=group_clip_id,
                allow_glyph_compression=intent == "process",
            )
        )
        lines.append("</g>")

    for edge in model["edges"]:
        lines.extend(
            _render_edge(
                edge,
                positions,
                lane_rank=lane_ranks[str(edge["id"])],
                canvas_width=width,
                canvas_height=height,
                intent=intent,
                process_row_gap=process_row_gap,
                non_process_row_gap=non_process_row_gap,
                long_branch_slot=long_branch_slots.get(str(edge["id"])),
                long_branch_count=len(long_branch_slots),
                long_branch_label_y=long_branch_label_y.get(str(edge["id"])),
                anchored_branch_gutter_x=anchored_branch_gutter_x.get(str(edge["id"])),
                long_vertical_gutter_x=long_vertical_gutter_x.get(str(edge["id"])),
                long_vertical_label_y=long_vertical_label_y.get(str(edge["id"])),
                process_branch_gutter_x=process_branch_gutter_x.get(str(edge["id"])),
                process_adjacent_slot=process_adjacent_slot.get(str(edge["id"])),
                process_adjacent_count=process_adjacent_count.get(str(edge["id"]), 0),
                process_adjacent_label_y=process_adjacent_label_y.get(str(edge["id"])),
                row_corridor_label_x=row_corridor_label_x.get(str(edge["id"])),
                narrative_parallel_gutter_x=narrative_parallel_gutter_x.get(str(edge["id"])),
                narrative_self_loop_gutter_x=narrative_self_loop_gutter_x.get(str(edge["id"])),
                generic_self_loop_gutter_x=generic_self_loop_gutter_x.get(str(edge["id"])),
                self_loop_lane=self_loop_lanes.get(str(edge["id"])),
                feedback_slot=feedback_slots.get(str(edge["id"])),
                feedback_count=feedback_count,
                feedback_base_bottom=feedback_base_bottom,
                force_feedback_footer=str(edge["id"]) in feedback_footer_ids,
            )
        )
    for node in model["nodes"]:
        lines.extend(
            _render_node(
                node,
                positions[str(node["id"])],
                intent=intent,
            )
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"

_CANVAS_PALETTE = {
    "1": ("#fff1f0", "#b85450"),
    "2": ("#fff4e6", "#d97706"),
    "3": ("#fff9db", "#b08900"),
    "4": ("#edf8ed", "#4d8a4d"),
    "5": ("#e9f5fb", "#3d7f91"),
    "6": ("#f2ecf6", "#806090"),
}


def _canvas_xml(value: Any) -> str:
    return _xml_escape(str(value))


def _canvas_color(value: Any) -> tuple[str, str]:
    text = str(value) if value is not None else ""
    if text in _CANVAS_PALETTE:
        return _CANVAS_PALETTE[text]
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
        except ValueError:
            pass
        else:
            return "#ffffff", text.lower()
    return "#ffffff", "#64748b"


def _canvas_anchor(
    node: Mapping[str, Any],
    side: str | None,
    *,
    toward: tuple[float, float],
) -> tuple[float, float, tuple[float, float]]:
    x = float(node["x"])
    y = float(node["y"])
    width = float(node["width"])
    height = float(node["height"])
    cx = x + width / 2
    cy = y + height / 2
    chosen = side
    if chosen is None:
        dx = toward[0] - cx
        dy = toward[1] - cy
        if abs(dx) >= abs(dy):
            chosen = "right" if dx >= 0 else "left"
        else:
            chosen = "bottom" if dy >= 0 else "top"
    points = {
        "left": (x, cy, (-1.0, 0.0)),
        "right": (x + width, cy, (1.0, 0.0)),
        "top": (cx, y, (0.0, -1.0)),
        "bottom": (cx, y + height, (0.0, 1.0)),
    }
    return points[chosen]


def _canvas_edge_geometry(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    edge: Mapping[str, Any],
    *,
    lane: float,
) -> tuple[str, float, float, str]:
    source_center = (
        float(source["x"]) + float(source["width"]) / 2,
        float(source["y"]) + float(source["height"]) / 2,
    )
    target_center = (
        float(target["x"]) + float(target["width"]) / 2,
        float(target["y"]) + float(target["height"]) / 2,
    )
    if source["id"] == target["id"]:
        x = float(source["x"])
        y = float(source["y"])
        width = float(source["width"])
        height = float(source["height"])
        start = (x + width, y + height * 0.35)
        end = (x + width, y + height * 0.72)
        reach = 66.0 + abs(lane)
        c1 = (start[0] + reach, y - 18.0)
        c2 = (end[0] + reach, y + height + 18.0)
        path = (
            f"M {start[0]:.1f} {start[1]:.1f} "
            f"C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, "
            f"{end[0]:.1f} {end[1]:.1f}"
        )
        label_x = (start[0] + 3 * c1[0] + 3 * c2[0] + end[0]) / 8 + 18
        label_y = (start[1] + 3 * c1[1] + 3 * c2[1] + end[1]) / 8
        return path, label_x, label_y, "canvas-self-loop"

    sx, sy, sv = _canvas_anchor(source, edge.get("from_side"), toward=target_center)
    tx, ty, tv = _canvas_anchor(target, edge.get("to_side"), toward=source_center)
    distance = max(42.0, min(160.0, math.hypot(tx - sx, ty - sy) * 0.35))
    c1 = (sx + sv[0] * distance, sy + sv[1] * distance)
    c2 = (tx + tv[0] * distance, ty + tv[1] * distance)
    if lane:
        dx = tx - sx
        dy = ty - sy
        magnitude = max(1.0, math.hypot(dx, dy))
        nx = -dy / magnitude
        ny = dx / magnitude
        c1 = (c1[0] + nx * lane, c1[1] + ny * lane)
        c2 = (c2[0] + nx * lane, c2[1] + ny * lane)
    path = (
        f"M {sx:.1f} {sy:.1f} "
        f"C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, "
        f"{tx:.1f} {ty:.1f}"
    )
    label_x = (sx + 3 * c1[0] + 3 * c2[0] + tx) / 8
    label_y = (sy + 3 * c1[1] + 3 * c2[1] + ty) / 8
    return path, label_x, label_y, "canvas-cubic"


def _canvas_wrap(value: str, width_px: int, height_px: int) -> list[str]:
    chars = max(4, width_px // 8)
    line_count = max(1, min(10, height_px // 20))
    lines: list[str] = []
    for paragraph in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        wrapped = textwrap.wrap(
            paragraph,
            width=chars,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        lines.extend(wrapped)
        if len(lines) >= line_count:
            break
    if len(lines) > line_count:
        lines = lines[:line_count]
    return lines[:line_count]


def render_native_editing_document(document: Mapping[str, Any]) -> str:
    """Render one explicit-geometry document using the native editor SVG contract."""

    if document.get("schema_version") != NATIVE_DOCUMENT_SCHEMA:
        raise NativeDocumentError("unsupported native editing document schema")
    nodes = document.get("nodes")
    edges = document.get("edges")
    if not isinstance(nodes, list):
        raise NativeDocumentError("native editing document nodes are invalid")
    if not isinstance(edges, list):
        raise NativeDocumentError("native editing document edges are invalid")

    node_by_id = {str(node["id"]): node for node in nodes}
    margin = 88
    if nodes:
        min_x = min(int(node["x"]) for node in nodes)
        min_y = min(int(node["y"]) for node in nodes)
        max_x = max(int(node["x"]) + int(node["width"]) for node in nodes)
        max_y = max(int(node["y"]) + int(node["height"]) for node in nodes)
        view_x = min_x - margin
        view_y = min_y - margin
        view_width = max(1, max_x - min_x + 2 * margin)
        view_height = max(1, max_y - min_y + 2 * margin)
    else:
        view_x = 0
        view_y = 0
        view_width = 1200
        view_height = 800

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{view_x} {view_y} {view_width} {view_height}" '
            f'width="{view_width}" height="{view_height}" '
            f'data-renderer="schauwerk-native-diagram-v1" '
            f'data-intent="freeform" data-document-mode="json-canvas" '
            f'data-input-digest="{_canvas_xml(document["source_digest"])}">'
        ),
        f"<title>{_canvas_xml(document.get('title', 'Schaubild'))}</title>",
        "<defs>",
    ]
    for index, edge in enumerate(edges):
        _, stroke = _canvas_color(edge.get("source", {}).get("color"))
        lines.extend(
            [
                (
                    f'<marker id="canvas-arrow-{index}" viewBox="0 0 8 8" refX="7" refY="4" '
                    'markerWidth="6" markerHeight="6" orient="auto-start-reverse" '
                    'markerUnits="strokeWidth">'
                ),
                f'<path d="M 0 0 L 8 4 L 0 8 L 2 4 Z" fill="{stroke}"/>',
                "</marker>",
            ]
        )
    lines.append("</defs>")

    pair_counts: dict[tuple[str, str], int] = {}
    pair_slots: dict[tuple[str, str], int] = {}
    for edge in edges:
        key = tuple(sorted((str(edge["from"]), str(edge["to"]))))
        pair_counts[key] = pair_counts.get(key, 0) + 1

    for index, edge in enumerate(edges):
        source = node_by_id[str(edge["from"])]
        target = node_by_id[str(edge["to"])]
        key = tuple(sorted((str(edge["from"]), str(edge["to"]))))
        slot = pair_slots.get(key, 0)
        pair_slots[key] = slot + 1
        lane = (slot - (pair_counts[key] - 1) / 2) * 18.0
        path, label_x, label_y, route = _canvas_edge_geometry(
            source, target, edge, lane=lane
        )
        _, stroke = _canvas_color(edge.get("source", {}).get("color"))
        label = str(edge.get("label", ""))
        label_width = max(42, min(260, len(label) * 8 + 20))
        label_height = 28
        marker_start = (
            f' marker-start="url(#canvas-arrow-{index})"'
            if edge.get("from_end") == "arrow"
            else ""
        )
        marker_end = (
            f' marker-end="url(#canvas-arrow-{index})"'
            if edge.get("to_end") != "none"
            else ""
        )
        lines.extend(
            [
                (
                    f'<g id="native-edge-{_canvas_xml(edge["id"])}" data-source-kind="edge" '
                    f'data-source-id="{_canvas_xml(edge["id"])}" data-kind="flow" '
                    f'data-route="{route}" data-lane="{lane:.1f}">'
                ),
                f"<title>{_canvas_xml(label)}</title>",
                (
                    f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{marker_start}{marker_end}/>'
                ),
            ]
        )
        if label:
            lines.extend(
                [
                    (
                        f'<rect x="{label_x - label_width / 2:.1f}" '
                        f'y="{label_y - label_height / 2:.1f}" width="{label_width}" '
                        f'height="{label_height}" rx="9" fill="#f8fafc" fill-opacity="0.94"/>'
                    ),
                    (
                        f'<text x="{label_x:.1f}" y="{label_y + 5:.1f}" '
                        f'text-anchor="middle" font-family="Inter, sans-serif" '
                        f'font-size="14" font-weight="600" fill="{stroke}">'
                        f'{_canvas_xml(label)}</text>'
                    ),
                ]
            )
        else:
            lines.append(
                f'<rect x="{label_x:.1f}" y="{label_y:.1f}" width="0" height="0" fill="none"/>'
            )
        lines.append("</g>")

    for node in nodes:
        node_type = str(node["type"])
        raw = node.get("source") if isinstance(node.get("source"), Mapping) else {}
        fill, stroke = _canvas_color(raw.get("color"))
        if node_type == "group":
            fill = "#f8fafc"
        x = int(node["x"])
        y = int(node["y"])
        width = int(node["width"])
        height = int(node["height"])
        label = str(node.get("label", ""))
        lines.append(
            f'<g id="native-node-{_canvas_xml(node["id"])}" data-source-kind="node" '
            f'data-source-id="{_canvas_xml(node["id"])}" data-kind="concept" '
            f'data-canvas-type="{_canvas_xml(node_type)}">'
        )
        lines.append(f"<title>{_canvas_xml(label)}</title>")
        dash = ' stroke-dasharray="8 6"' if node_type == "group" else ""
        fill_opacity = "0.28" if node_type == "group" else "1"
        lines.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
            f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{stroke}" '
            f'stroke-width="1.8"{dash}/>'
        )
        text_x = x + 14
        text_y = y + 28
        for line_index, line in enumerate(_canvas_wrap(label, width - 28, height - 24)):
            weight = "700" if line_index == 0 or node_type == "group" else "500"
            lines.append(
                f'<text data-node-label="true" x="{text_x}" '
                f'y="{text_y + line_index * 20}" font-family="Inter, sans-serif" '
                f'font-size="16" font-weight="{weight}" fill="#172033">{_canvas_xml(line)}</text>'
            )
        lines.append("</g>")

    lines.append("</svg>")
    return "\n".join(lines) + "\n"