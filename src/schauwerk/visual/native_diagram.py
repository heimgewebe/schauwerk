"""Small deterministic SVG renderer for Schauwerk representation input."""

from __future__ import annotations

import io
import math
import re
import textwrap
import unicodedata
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

from .grammar import GRAMMAR_SCHEMA_VERSION
from .grapheme import (
    MAX_GRAPHEME_CLUSTER_CODEPOINTS,
    bounded_grapheme_prefix,
    is_extended_pictographic,
    iter_grapheme_clusters,
)
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
_CANVAS_WRAP_DEFAULT_WIDTH_UNITS = 0.70
_CANVAS_BOLD_FALLBACK_OPERATORS = frozenset("+<=>^~")
_CANVAS_BOLD_FALLBACK_OPERATOR_WIDTH_UNITS = 0.85
_CANVAS_BOLD_FALLBACK_DEFAULT_CHARS = frozenset("bdghnpqu{}")
_CANVAS_BOLD_FALLBACK_DEFAULT_WIDTH_UNITS = 0.72
_CANVAS_MAX_NODE_TEXT_LINES = 2048
_CANVAS_MAX_EMITTED_TEXT_BYTES = 1 * 1024 * 1024
_CANVAS_MAX_ELEMENT_TITLE_BYTES = 4096

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


def _xml_10_character_allowed(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint in {0x09, 0x0A, 0x0D}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _xml_escape(value: str) -> str:
    """Replace XML 1.0-forbidden code points, then escape markup characters."""

    compatible = [
        character if _xml_10_character_allowed(character) else "\uFFFD"
        for character in value
    ]
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
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
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
) -> tuple[str, float, float, str, tuple[float, float, float, float]]:
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
        reach = 66.0 + abs(lane)
        from_side = edge.get("from_side")
        to_side = edge.get("to_side")
        if from_side is None and to_side is None:
            start = (x + width, y + height * 0.35)
            end = (x + width, y + height * 0.72)
            c1 = (start[0] + reach, y - 18.0)
            c2 = (end[0] + reach, y + height + 18.0)
            label_offset_x = 18.0
            label_offset_y = 0.0
        else:
            def loop_anchor(
                side: str | None, fraction: float
            ) -> tuple[float, float, tuple[float, float]]:
                chosen = side or "right"
                points = {
                    "left": (x, y + height * fraction, (-1.0, 0.0)),
                    "right": (x + width, y + height * fraction, (1.0, 0.0)),
                    "top": (x + width * fraction, y, (0.0, -1.0)),
                    "bottom": (x + width * fraction, y + height, (0.0, 1.0)),
                }
                return points[chosen]

            sx, sy, source_vector = loop_anchor(from_side, 0.35)
            tx, ty, target_vector = loop_anchor(to_side, 0.72)
            start = (sx, sy)
            end = (tx, ty)
            c1 = (
                sx + source_vector[0] * reach,
                sy + source_vector[1] * reach,
            )
            c2 = (
                tx + target_vector[0] * reach,
                ty + target_vector[1] * reach,
            )
            chosen_from = from_side or "right"
            chosen_to = to_side or "right"
            if {chosen_from, chosen_to} == {"top", "bottom"}:
                outside_bias = reach + width / 2
                c1 = (c1[0] + outside_bias, c1[1])
                c2 = (c2[0] + outside_bias, c2[1])
            elif {chosen_from, chosen_to} == {"left", "right"}:
                outside_bias = reach + height / 2
                c1 = (c1[0], c1[1] - outside_bias)
                c2 = (c2[0], c2[1] - outside_bias)
            label_offset_x = 9.0 * (source_vector[0] + target_vector[0])
            label_offset_y = 9.0 * (source_vector[1] + target_vector[1])
        path = (
            f"M {start[0]:.1f} {start[1]:.1f} "
            f"C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, "
            f"{end[0]:.1f} {end[1]:.1f}"
        )
        label_x = (
            (start[0] + 3 * c1[0] + 3 * c2[0] + end[0]) / 8
            + label_offset_x
        )
        label_y = (
            (start[1] + 3 * c1[1] + 3 * c2[1] + end[1]) / 8
            + label_offset_y
        )
        points = (start, c1, c2, end)
        bounds = (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )
        return path, label_x, label_y, "canvas-self-loop", bounds

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
    points = ((sx, sy), c1, c2, (tx, ty))
    bounds = (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )
    return path, label_x, label_y, "canvas-cubic", bounds



def _canvas_strip_markdown_links(value: str) -> str:
    """Strip legacy Markdown links with monotonic linear scanning."""

    output: list[str] = []
    cursor = 0
    length = len(value)
    while cursor < length:
        opening = value.find("[", cursor)
        if opening < 0:
            output.append(value[cursor:])
            break
        output.append(value[cursor:opening])
        closing = value.find("]", opening + 1)
        if closing < 0:
            output.append(value[opening:])
            break
        if closing == opening + 1 or closing + 1 >= length or value[closing + 1] != "(":
            output.append(value[opening : closing + 1])
            cursor = closing + 1
            continue
        target_end = value.find(")", closing + 2)
        if target_end < 0:
            output.append(value[opening:])
            break
        if target_end == closing + 2:
            output.append(value[opening : target_end + 1])
            cursor = target_end + 1
            continue
        output.append(value[opening + 1 : closing])
        cursor = target_end + 1
    return "".join(output)


def _canvas_plain_markdown(value: str) -> str:
    """Normalize the bounded Markdown subset already used by the legacy Canvas path."""

    text = re.sub(r"^#{1,6}\s+", "", str(value), flags=re.MULTILINE)
    text = _canvas_strip_markdown_links(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\x60([^\x60]+)\x60", r"\1", text)
    return text.strip(" \t\r\n")


@dataclass(frozen=True)
class _CanvasTextLayout:
    size: int
    lines: tuple[tuple[str, int], ...]
    truncated: bool


def _canvas_iter_source_lines(value: str):
    """Yield normalized source lines without materializing an unbounded split list."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        yield ""
        return
    stream = io.StringIO(normalized)
    for raw_line in stream:
        yield raw_line[:-1] if raw_line.endswith("\n") else raw_line
    if normalized.endswith("\n"):
        yield ""


def _canvas_legacy_lines(
    value: str, width_px: int, *, max_lines: int
) -> tuple[list[str], bool]:
    """Return bounded historical wrapping and whether source text was omitted."""

    if max_lines <= 0:
        return [], bool(value)
    chars = max(4, width_px // 8)
    lines: list[str] = []
    for paragraph in _canvas_iter_source_lines(value):
        remaining = max_lines - len(lines)
        if remaining <= 0:
            return lines, True
        if not paragraph:
            lines.append("")
            continue
        sample_limit = max(chars, chars * (remaining + 1))
        sample = paragraph[:sample_limit]
        wrapped = textwrap.wrap(
            sample,
            width=chars,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        if len(wrapped) > remaining:
            lines.extend(wrapped[:remaining])
            return lines, True
        lines.extend(wrapped)
        if len(sample) < len(paragraph):
            return lines, True
    return lines, False


_CANVAS_ZWNJ = "\u200c"
_CANVAS_ZWJ = "\u200d"
_CANVAS_EMOJI_PRESENTATION_SELECTOR = "\ufe0f"
_CANVAS_KEYCAP = "\u20e3"
_CANVAS_BIDI_ZERO_ADVANCE_CODEPOINTS = frozenset(
    {
        0x061C,  # ARABIC LETTER MARK
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
        0x206A,  # INHIBIT SYMMETRIC SWAPPING
        0x206B,  # ACTIVATE SYMMETRIC SWAPPING
        0x206C,  # INHIBIT ARABIC FORM SHAPING
        0x206D,  # ACTIVATE ARABIC FORM SHAPING
        0x206E,  # NATIONAL DIGIT SHAPES
        0x206F,  # NOMINAL DIGIT SHAPES
    }
)
_CANVAS_BIDI_EMBED_OPENERS = frozenset({"\u202a", "\u202b", "\u202d", "\u202e"})
_CANVAS_BIDI_ISOLATE_OPENERS = frozenset({"\u2066", "\u2067"})
_CANVAS_BIDI_FSI = "\u2068"
_CANVAS_BIDI_PDF = "\u202c"
_CANVAS_BIDI_PDI = "\u2069"
_CANVAS_MAX_BIDI_SCOPE_DEPTH = 125
_CANVAS_INVISIBLE_ZERO_ADVANCE_CODEPOINTS = frozenset(
    {
        0x00AD,  # SOFT HYPHEN
        0x180E,  # MONGOLIAN VOWEL SEPARATOR
        0x200B,  # ZERO WIDTH SPACE
        0x2060,  # WORD JOINER
        0x2061,  # FUNCTION APPLICATION
        0x2062,  # INVISIBLE TIMES
        0x2063,  # INVISIBLE SEPARATOR
        0x2064,  # INVISIBLE PLUS
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE
    }
)
_MAX_CANVAS_TEXT_PROBE_CLUSTERS = 32_768
_MAX_CANVAS_TEXT_PROBE_CODEPOINTS = 65_536
_CANVAS_SPACING_MARK_WIDTH_UNITS = 0.60
_CANVAS_SCRIPT_ZWJ_MIN_WIDTH_UNITS = 1.50
_CANVAS_SPACING_MARK_CLUSTER_WIDTH_RANGES = (
    (0x0900, 0x097F, 1.20),  # Devanagari
    (0x0980, 0x09FF, 1.25),  # Bengali
    (0x0A00, 0x0A7F, 1.15),  # Gurmukhi
    (0x0A80, 0x0AFF, 1.15),  # Gujarati
    (0x0B00, 0x0B7F, 1.15),  # Oriya
    (0x0B80, 0x0BFF, 1.25),  # Tamil
    (0x0C80, 0x0CFF, 1.15),  # Kannada
    (0x0D00, 0x0D7F, 1.65),  # Malayalam
    (0x0D80, 0x0DFF, 1.50),  # Sinhala
    (0x1780, 0x17FF, 1.10),  # Khmer
    (0x1B00, 0x1B7F, 1.55),  # Balinese
)
_CANVAS_ZWJ_SHAPING_SCRIPT_RANGES = (
    (0x0600, 0x08FF),  # Arabic-family joining scripts
    (0x0900, 0x0DFF),  # Indic scripts covered by the native Canvas renderer
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0x1A20, 0x1AAF),  # Tai Tham
    (0x1B00, 0x1B7F),  # Balinese
)
# Isolated shaping-script letters whose measured bold fallback advance exceeds
# the 1.5em composite-cluster floor. Keep only the widest member of a shaped
# ZWJ cluster; summing per-letter fallback advances overbudgets conjuncts.
_CANVAS_ZWJ_SHAPING_WIDE_LETTER_WIDTH_RANGES = (
    (0x0B94, 0x0B94, 1.60),
    (0x0C60, 0x0C60, 1.80),
    (0x0CE0, 0x0CE0, 1.60),
    (0x0D06, 0x0D06, 1.55),
    (0x0D08, 0x0D08, 1.75),
    (0x0D10, 0x0D10, 1.95),
    (0x0D1D, 0x0D1D, 1.55),
    (0x0D8E, 0x0D8E, 1.75),
    (0x0D90, 0x0D90, 1.60),
    (0x102A, 0x102A, 2.50),
    (0x103F, 0x103F, 1.60),
    (0x1B08, 0x1B08, 1.55),
    (0x1B12, 0x1B12, 1.55),
    (0x1B46, 0x1B46, 1.80),
    (0x1B4B, 0x1B4B, 1.85),
)
# Per-base floors for multi-letter shaping-ZWJ graphemes that remain one
# extended grapheme cluster. The 0.75em default preserves the short shaped
# conjunct floor; higher script floors are rounded above exhaustive repeated-
# letter Chrome/DejaVu probes so missing/partial shaping cannot collapse the
# whole cluster to the width of only its widest member.
_CANVAS_ZWJ_LINEAR_FALLBACK_DEFAULT_WIDTH_UNITS = 0.75
_CANVAS_ZWJ_LINEAR_FALLBACK_LETTER_WIDTH_RANGES = (
    (0x0A80, 0x0AFF, 1.00),
    (0x0B00, 0x0B7F, 1.00),
    (0x0C00, 0x0C7F, 1.30),
    (0x0D00, 0x0D7F, 1.55),
    (0x1000, 0x109F, 2.50),
    (0x1780, 0x17FF, 1.30),
    (0x1A20, 0x1AAF, 1.40),
    (0x1B00, 0x1B7F, 2.00),
)
_CANVAS_XML_REPLACEMENT_WIDTH_UNITS = 1.15
_CANVAS_CYRILLIC_WIDTH_UNITS = 1.25
_CANVAS_FALLBACK_LETTER_WIDTH_UNITS = 0.90
_CANVAS_EAST_ASIAN_WIDE_WIDTH_UNITS = 1.05
_CANVAS_SUPPLEMENTARY_PICTOGRAPHIC_WIDTH_UNITS = 1.65
_CANVAS_EMOJI_PRESENTATION_WIDTH_UNITS = 1.25
# The generic non-ASCII letter estimate stays at the historical 0.9em. Only
# measured fallback outliers receive a higher floor, which avoids applying the
# previous 1.0em safety floor to every alphabetic code point.
_CANVAS_FALLBACK_LETTER_FLOOR_RANGES = (
    (0x0126, 0x0126, 1.00),
    (0x0149, 0x0149, 1.00),
    (0x0175, 0x0175, 0.95),
    (0x018A, 0x018A, 0.95),
    (0x01A3, 0x01A3, 0.95),
    (0x026F, 0x0271, 1.05),
    (0x0276, 0x0277, 0.95),
    (0x0289, 0x0289, 0.95),
    (0x028D, 0x028D, 0.95),
    (0x02A6, 0x02A6, 1.00),
    (0x02A8, 0x02A8, 0.95),
    (0x02A9, 0x02A9, 1.05),
    (0x038E, 0x038E, 1.00),
    (0x039C, 0x039C, 1.00),
    (0x03C9, 0x03C9, 0.95),
    (0x03CE, 0x03CE, 0.95),
    (0x03D3, 0x03D3, 1.00),
    (0x03D6, 0x03D6, 0.95),
    (0x03E0, 0x03E0, 0.95),
    (0x03E6, 0x03E6, 0.95),
    (0x03FA, 0x03FA, 1.00),
    (0x0539, 0x0539, 0.95),
    (0x053D, 0x053D, 1.00),
    (0x0560, 0x0560, 0.95),
    (0x0561, 0x0561, 1.00),
    (0x056D, 0x056D, 1.00),
    (0x057A, 0x057A, 1.00),
    (0x057F, 0x057F, 1.00),
    (0x0583, 0x0583, 1.00),
    (0x079F, 0x079F, 1.00),
    (0x090B, 0x090B, 0.95),
    (0x0B06, 0x0B06, 1.00),
    (0x0B10, 0x0B10, 1.00),
    (0x0B14, 0x0B14, 1.00),
    (0x0B2B, 0x0B2B, 1.00),
    (0x1100, 0x11FF, 0.95),  # Hangul Jamo
    (0x1700, 0x177F, 1.10),  # Tagalog/Hanunoo/Buhid/Tagbanwa
    (0x18B0, 0x18FF, 1.05),  # Canadian Syllabics Extended
    (0x1905, 0x1905, 0.95),
    (0x1CFA, 0x1CFA, 1.05),
    (0x1D02, 0x1D02, 1.05),
    (0x1D14, 0x1D14, 1.10),
    (0x1D1E, 0x1D1E, 0.95),
    (0x1D21, 0x1D21, 0.95),
    (0x2D00, 0x2D2F, 1.05),  # Georgian Supplement
    (0xA4DF, 0xA4DF, 1.00),
    (0xA4EA, 0xA4EA, 1.15),
    (0xA6E1, 0xA6E1, 0.95),
    (0xA808, 0xA808, 1.00),
    (0xA80F, 0xA80F, 0.95),
    (0xA815, 0xA815, 0.95),
    (0xA81A, 0xA81A, 0.95),
    (0xA89A, 0xA89A, 0.95),
    (0xA944, 0xA944, 0.95),
    (0xAB3A, 0xAB42, 0.95),  # Latin Extended-E measured tail
    (0xABC0, 0xABC0, 0.95),
    (0xABC4, 0xABC4, 1.00),
    (0xABC9, 0xABC9, 0.95),
    (0xD7B0, 0xD7FF, 0.95),  # Hangul Jamo Extended-B
    (0xFFA0, 0xFFDC, 0.95),  # Halfwidth Hangul letters
)
# Letter fallback glyphs whose isolated bold advance exceeds the generic
# non-ASCII budget in DejaVu Sans Bold or the headless-Chrome
# Inter/Arial/sans-serif fallback stack. Ranges are script/block aware and
# rounded upward to 0.05em.
_CANVAS_WIDE_FALLBACK_LETTER_WIDTH_RANGES = (
    (0x00C6, 0x00C6, 1.10),  # LATIN CAPITAL LETTER AE
    (0x00E6, 0x00E6, 1.05),  # LATIN SMALL LETTER AE
    (0x0152, 0x0152, 1.20),  # LATIN CAPITAL LIGATURE OE
    (0x0153, 0x0153, 1.10),  # LATIN SMALL LIGATURE OE
    (0x0174, 0x0174, 1.15),  # LATIN CAPITAL LETTER W WITH CIRCUMFLEX
    (0x0195, 0x0195, 1.05),
    (0x019C, 0x019C, 1.05),
    (0x01A2, 0x01A2, 1.10),
    (0x01C4, 0x01CC, 1.60),  # Latin DZ/LJ/NJ digraph family
    (0x01E2, 0x01E2, 1.10),
    (0x01E3, 0x01E3, 1.05),
    (0x01F1, 0x01F3, 1.60),  # Latin DZ digraph family
    (0x01F6, 0x01F6, 1.30),
    (0x01FC, 0x01FC, 1.10),
    (0x01FD, 0x01FD, 1.05),
    (0x0238, 0x0239, 1.10),
    (0x02A3, 0x02A5, 1.30),  # IPA digraphs
    (0x0372, 0x0372, 1.05),
    (0x0389, 0x0389, 1.05),
    (0x03E2, 0x03E2, 1.10),
    (0x0429, 0x0429, 1.35),
    (0x0468, 0x0468, 1.40),
    (0x0478, 0x0478, 1.40),
    (0x047C, 0x047C, 1.45),
    (0x04A6, 0x04A6, 1.30),
    (0x050A, 0x050A, 1.30),
    (0x0514, 0x0514, 1.30),
    (0x0520, 0x0520, 1.30),
    (0x0522, 0x0522, 1.30),
    (0x0590, 0x05FF, 1.05),  # Hebrew
    (0x0600, 0x06FF, 1.40),  # Arabic
    (0x0750, 0x077F, 1.40),  # Arabic Supplement
    (0x07C0, 0x07FF, 1.05),  # NKo
    (0x0800, 0x083F, 1.10),  # Samaritan
    (0x0840, 0x085F, 1.15),  # Mandaic
    (0x0860, 0x08FF, 1.35),  # Syriac/Arabic Extended
    (0x0A00, 0x0A7F, 1.25),  # Gurmukhi
    (0x0A80, 0x0AFF, 1.30),  # Gujarati
    (0x0B80, 0x0BFF, 1.60),  # Tamil
    (0x0C00, 0x0C7F, 1.80),  # Telugu
    (0x0C80, 0x0CFF, 1.60),  # Kannada
    (0x0D00, 0x0D7F, 1.95),  # Malayalam
    (0x0D80, 0x0DFF, 1.75),  # Sinhala
    (0x0E80, 0x0EFF, 1.40),  # Lao
    (0x1000, 0x1028, 1.35),  # Myanmar common letters
    (0x1029, 0x1029, 1.40),  # MYANMAR LETTER O
    (0x102A, 0x102A, 2.50),  # MYANMAR LETTER AU
    (0x102B, 0x103E, 1.35),  # Myanmar common letters
    (0x103F, 0x103F, 1.60),  # MYANMAR LETTER GREAT SA
    (0x1040, 0x109F, 1.35),  # Myanmar remainder
    (0x10A0, 0x10FF, 1.10),  # Georgian
    (0x1200, 0x137F, 1.35),  # Ethiopic
    (0x1380, 0x139F, 1.30),  # Ethiopic Supplement
    (0x13A0, 0x13FF, 1.20),  # Cherokee
    (0x1400, 0x151C, 1.30),  # Canadian Aboriginal Syllabics
    (0x151D, 0x1524, 1.45),
    (0x1525, 0x158D, 1.30),
    (0x158E, 0x1590, 1.60),
    (0x1591, 0x1592, 1.30),
    (0x1593, 0x1594, 1.60),
    (0x1595, 0x166F, 1.30),
    (0x1670, 0x1670, 1.60),
    (0x1671, 0x1672, 2.05),
    (0x1673, 0x1674, 1.75),
    (0x1675, 0x1676, 2.05),
    (0x1680, 0x169F, 1.90),  # Ogham
    (0x1780, 0x17FF, 1.30),  # Khmer
    (0x1800, 0x18AF, 1.25),  # Mongolian
    (0x1980, 0x19DF, 1.30),  # New Tai Lue
    (0x1A00, 0x1A1F, 1.25),  # Buginese
    (0x1A20, 0x1AAF, 1.40),  # Tai Tham
    (0x1B00, 0x1B7F, 1.85),  # Balinese
    (0x1B80, 0x1BBF, 1.65),  # Sundanese
    (0x1BC0, 0x1BFF, 1.15),  # Batak
    (0x1C00, 0x1C4F, 1.10),  # Lepcha
    (0x1C90, 0x1CBF, 1.15),  # Georgian Extended
    (0x1E00, 0x1EFF, 1.15),  # Latin Extended Additional
    (0x1F00, 0x1FFF, 1.30),  # Greek Extended
    (0x2100, 0x214F, 1.20),  # Letterlike Symbols (letter-category members)
    (0x2C00, 0x2C5F, 1.25),  # Glagolitic
    (0x2C60, 0x2C7F, 1.25),  # Latin Extended-C
    (0x2C80, 0x2CFF, 1.05),  # Coptic
    (0x2D30, 0x2D7F, 1.05),  # Tifinagh
    (0x2D80, 0x2DDF, 1.40),  # Ethiopic Extended
    (0xA500, 0xA63F, 1.35),  # Vai
    (0xA640, 0xA69F, 1.45),  # Cyrillic Extended-B
    (0xA720, 0xA7FF, 1.45),  # Latin Extended-D
    (0xA840, 0xA87F, 1.20),  # Phags-pa
    (0xA980, 0xA9DF, 1.50),  # Javanese
    (0xA9E0, 0xA9FF, 1.30),  # Myanmar Extended-B
    (0xAA00, 0xAA5F, 1.60),  # Cham
    (0xAA60, 0xAA7F, 1.45),  # Myanmar Extended-A
    (0xAA80, 0xAADF, 1.25),  # Tai Viet
    (0xAAE0, 0xAAFF, 1.15),  # Meetei Mayek Extensions
    (0xAB00, 0xAB2F, 1.30),  # Ethiopic Extended-A
    (0xAB70, 0xABBF, 1.05),  # Cherokee Supplement
    (0xFB00, 0xFB4F, 1.75),  # Alphabetic Presentation Forms
    (0xFB50, 0xFDFF, 2.15),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF, 1.45),  # Arabic Presentation Forms-B
)
# Supplementary-plane Unicode L-category fallback calibration for the same
# headless-Chrome Inter/Arial/sans-serif and DejaVu Sans Bold acceptance
# population as the BMP verifier. Each 0x20-aligned range uses the largest
# measured width in that block, rounded upward to 0.05em. The bound 87,761-
# letter scan reports zero underestimates while avoiding a per-codepoint table.
_CANVAS_SUPPLEMENTARY_FALLBACK_LETTER_WIDTH_RANGES = (
    (0x10000, 0x1001F, 1.00),
    (0x10040, 0x1005F, 1.05),
    (0x10080, 0x1009F, 1.25),
    (0x100A0, 0x100BF, 1.65),
    (0x100C0, 0x100DF, 1.95),
    (0x100E0, 0x100FF, 1.40),
    (0x102A0, 0x102DF, 0.95),
    (0x10300, 0x1031F, 1.45),
    (0x10360, 0x1037F, 0.95),
    (0x10380, 0x1039F, 1.25),
    (0x103A0, 0x103DF, 1.40),
    (0x10480, 0x1049F, 1.10),
    (0x10560, 0x105BF, 1.05),
    (0x10600, 0x1061F, 1.00),
    (0x10620, 0x1063F, 1.05),
    (0x10640, 0x1065F, 1.00),
    (0x10660, 0x1067F, 1.25),
    (0x10680, 0x106DF, 1.20),
    (0x106E0, 0x106FF, 1.15),
    (0x10700, 0x1071F, 1.00),
    (0x10720, 0x1073F, 1.30),
    (0x10740, 0x1075F, 1.25),
    (0x10780, 0x107BF, 1.05),
    (0x10800, 0x1081F, 1.00),
    (0x10820, 0x1085F, 0.95),
    (0x10920, 0x1093F, 0.95),
    (0x10980, 0x1099F, 1.55),
    (0x109A0, 0x109BF, 0.95),
    (0x10AC0, 0x10ADF, 1.25),
    (0x10AE0, 0x10AFF, 1.20),
    (0x10B00, 0x10B1F, 1.35),
    (0x10B20, 0x10B3F, 1.15),
    (0x10B40, 0x10B5F, 1.20),
    (0x10B80, 0x10B9F, 1.10),
    (0x10C20, 0x10C3F, 0.95),
    (0x10C80, 0x10CBF, 1.05),
    (0x10F00, 0x10F1F, 1.05),
    (0x10F20, 0x10F3F, 1.25),
    (0x10F40, 0x10F5F, 1.10),
    (0x10F60, 0x10FDF, 1.05),
    (0x10FE0, 0x10FFF, 1.20),
    (0x11020, 0x1103F, 1.00),
    (0x11060, 0x1107F, 1.05),
    (0x11100, 0x1111F, 1.15),
    (0x11120, 0x1113F, 1.05),
    (0x11140, 0x1117F, 1.10),
    (0x111C0, 0x111DF, 1.10),
    (0x11200, 0x1121F, 1.15),
    (0x11220, 0x1123F, 1.10),
    (0x11240, 0x1125F, 1.05),
    (0x11280, 0x1129F, 0.95),
    (0x112A0, 0x112BF, 1.25),
    (0x112C0, 0x112DF, 1.05),
    (0x11300, 0x1131F, 2.80),
    (0x11320, 0x1133F, 1.70),
    (0x11340, 0x1135F, 1.20),
    (0x11360, 0x1137F, 1.80),
    (0x11400, 0x1141F, 0.95),
    (0x11460, 0x1147F, 1.40),
    (0x11480, 0x1149F, 1.05),
    (0x114C0, 0x114DF, 1.05),
    (0x11580, 0x1159F, 0.95),
    (0x11700, 0x1171F, 1.15),
    (0x11740, 0x1175F, 1.05),
    (0x11800, 0x1181F, 1.00),
    (0x11900, 0x1195F, 1.05),
    (0x119A0, 0x119FF, 1.05),
    (0x11A00, 0x11A1F, 1.15),
    (0x11A80, 0x11A9F, 1.25),
    (0x11AA0, 0x11ABF, 1.05),
    (0x11C00, 0x11C1F, 1.10),
    (0x11C20, 0x11C3F, 0.95),
    (0x11D00, 0x11D1F, 1.00),
    (0x11D20, 0x11D3F, 1.20),
    (0x11D60, 0x11D7F, 1.00),
    (0x11EE0, 0x11F3F, 1.05),
    (0x11FA0, 0x11FBF, 1.05),
    (0x12000, 0x1201F, 2.10),
    (0x12020, 0x1203F, 3.65),
    (0x12040, 0x1205F, 3.25),
    (0x12060, 0x1207F, 2.65),
    (0x12080, 0x1209F, 2.40),
    (0x120A0, 0x120BF, 1.80),
    (0x120C0, 0x120DF, 1.60),
    (0x120E0, 0x120FF, 2.15),
    (0x12100, 0x1211F, 2.30),
    (0x12120, 0x1213F, 3.15),
    (0x12140, 0x1215F, 3.10),
    (0x12160, 0x1217F, 2.25),
    (0x12180, 0x1219F, 2.50),
    (0x121A0, 0x121BF, 2.00),
    (0x121C0, 0x121DF, 1.10),
    (0x121E0, 0x121FF, 1.95),
    (0x12200, 0x1221F, 4.05),
    (0x12220, 0x1223F, 2.35),
    (0x12240, 0x1225F, 2.45),
    (0x12260, 0x1227F, 2.60),
    (0x12280, 0x1229F, 2.90),
    (0x122A0, 0x122BF, 2.20),
    (0x122C0, 0x122DF, 2.35),
    (0x122E0, 0x122FF, 1.90),
    (0x12300, 0x1231F, 2.25),
    (0x12320, 0x1233F, 2.55),
    (0x12340, 0x1235F, 2.85),
    (0x12360, 0x1237F, 2.65),
    (0x12380, 0x1239F, 2.50),
    (0x12480, 0x1249F, 3.25),
    (0x124A0, 0x124BF, 2.45),
    (0x124C0, 0x124DF, 2.50),
    (0x124E0, 0x124FF, 2.70),
    (0x12500, 0x1251F, 2.95),
    (0x12520, 0x1253F, 2.45),
    (0x12540, 0x1255F, 2.25),
    (0x12F80, 0x12FFF, 1.05),
    (0x13000, 0x1301F, 1.40),
    (0x13020, 0x1303F, 1.30),
    (0x13040, 0x1307F, 1.25),
    (0x13080, 0x1309F, 1.55),
    (0x130A0, 0x130DF, 1.90),
    (0x130E0, 0x1311F, 1.75),
    (0x13120, 0x1313F, 1.25),
    (0x13140, 0x1315F, 1.55),
    (0x13160, 0x1317F, 1.85),
    (0x13180, 0x131BF, 1.65),
    (0x131C0, 0x131DF, 2.05),
    (0x131E0, 0x131FF, 1.40),
    (0x13200, 0x1321F, 1.50),
    (0x13220, 0x1323F, 1.30),
    (0x13240, 0x1325F, 1.40),
    (0x13260, 0x1327F, 1.60),
    (0x13280, 0x1329F, 1.45),
    (0x132A0, 0x132BF, 1.40),
    (0x132C0, 0x1331F, 1.45),
    (0x13320, 0x1333F, 1.40),
    (0x13340, 0x1337F, 1.55),
    (0x13380, 0x1339F, 1.75),
    (0x133A0, 0x133BF, 1.30),
    (0x133C0, 0x133DF, 1.35),
    (0x133E0, 0x133FF, 1.45),
    (0x13400, 0x1341F, 1.50),
    (0x13420, 0x1343F, 1.25),
    (0x13440, 0x1345F, 1.05),
    (0x14400, 0x1441F, 1.60),
    (0x14420, 0x1443F, 1.40),
    (0x14440, 0x1445F, 1.50),
    (0x14460, 0x1447F, 1.55),
    (0x14480, 0x1449F, 1.35),
    (0x144A0, 0x144DF, 1.55),
    (0x144E0, 0x144FF, 1.45),
    (0x14500, 0x1451F, 1.25),
    (0x14520, 0x1453F, 1.15),
    (0x14540, 0x1455F, 1.40),
    (0x14560, 0x1457F, 1.45),
    (0x14580, 0x1459F, 1.25),
    (0x145A0, 0x145BF, 1.45),
    (0x145C0, 0x145DF, 1.25),
    (0x145E0, 0x145FF, 1.10),
    (0x14600, 0x1461F, 1.60),
    (0x14620, 0x1463F, 1.30),
    (0x14640, 0x1465F, 1.60),
    (0x16800, 0x1681F, 1.10),
    (0x16820, 0x1683F, 1.20),
    (0x16840, 0x1687F, 1.15),
    (0x16880, 0x1689F, 1.45),
    (0x168A0, 0x168BF, 1.00),
    (0x168C0, 0x168DF, 1.25),
    (0x168E0, 0x168FF, 0.95),
    (0x16900, 0x1691F, 1.00),
    (0x16920, 0x1693F, 1.15),
    (0x16940, 0x1695F, 1.20),
    (0x16960, 0x1697F, 1.45),
    (0x16980, 0x1699F, 1.00),
    (0x169A0, 0x169BF, 1.20),
    (0x169C0, 0x169DF, 1.10),
    (0x169E0, 0x169FF, 1.00),
    (0x16A00, 0x16A1F, 1.30),
    (0x16A20, 0x16A5F, 1.00),
    (0x16A60, 0x16ABF, 1.05),
    (0x16AE0, 0x16AFF, 1.05),
    (0x16B00, 0x16B1F, 0.95),
    (0x16E40, 0x16E5F, 1.20),
    (0x1B2A0, 0x1B2BF, 1.10),
    (0x1B2E0, 0x1B2FF, 1.10),
    (0x1BC00, 0x1BC1F, 1.25),
    (0x1BC20, 0x1BC3F, 1.35),
    (0x1BC60, 0x1BC7F, 0.95),
    (0x1D400, 0x1D41F, 1.00),
    (0x1D4A0, 0x1D4BF, 1.00),
    (0x1D4C0, 0x1D4DF, 1.05),
    (0x1D4E0, 0x1D4FF, 1.00),
    (0x1D500, 0x1D51F, 0.95),
    (0x1D540, 0x1D55F, 1.15),
    (0x1D560, 0x1D59F, 0.95),
    (0x1D5A0, 0x1D5DF, 1.00),
    (0x1D5E0, 0x1D5FF, 1.15),
    (0x1D600, 0x1D63F, 1.00),
    (0x1D640, 0x1D65F, 1.15),
    (0x1D660, 0x1D67F, 1.05),
    (0x1D6A0, 0x1D6BF, 0.95),
    (0x1D760, 0x1D79F, 1.00),
    (0x1DF00, 0x1DF3F, 1.05),
    (0x1E020, 0x1E07F, 1.05),
    (0x1E280, 0x1E2BF, 1.05),
    (0x1E4C0, 0x1E4FF, 1.05),
    (0x1E7E0, 0x1E7FF, 1.05),
    (0x1E800, 0x1E81F, 1.35),
    (0x1E820, 0x1E83F, 1.15),
    (0x1E840, 0x1E85F, 1.20),
    (0x1E860, 0x1E89F, 1.25),
    (0x1E8A0, 0x1E8BF, 1.15),
    (0x1E8C0, 0x1E8DF, 1.00),
    (0x1E900, 0x1E91F, 1.00),
    (0x1EE00, 0x1EE1F, 1.25),
    (0x1EE40, 0x1EE5F, 1.30),
    (0x1EE60, 0x1EE7F, 1.20),
    (0x1EE80, 0x1EEBF, 1.15),
)
# Non-ASCII numeric glyphs use a conservative 1.0em floor. The ordered
# calibration ranges cover every Nd/Nl/No code point whose measured Bold
# advance exceeds 1.0em in the acceptance browser/font population. Each
# bound is the strict next 0.05em above the larger of the single-glyph
# advance and the per-glyph advance of a ten-glyph repeated run.
_CANVAS_FALLBACK_NUMERIC_WIDTH_UNITS = 1.00
_CANVAS_WIDE_FALLBACK_NUMERIC_WIDTH_RANGES = (
    (0xBC, 0xBE, 1.05),
    (0xD58, 0xD58, 1.25),
    (0xD59, 0xD59, 1.15),
    (0xD5A, 0xD5A, 1.10),
    (0xD5C, 0xD5C, 1.55),
    (0xD5D, 0xD5D, 2.05),
    (0xD5E, 0xD5E, 1.40),
    (0xD69, 0xD69, 1.05),
    (0xD6C, 0xD6C, 1.25),
    (0xD70, 0xD70, 1.25),
    (0xD72, 0xD72, 1.35),
    (0xD75, 0xD75, 1.05),
    (0xD76, 0xD76, 1.40),
    (0xD77, 0xD77, 1.75),
    (0xD78, 0xD78, 2.20),
    (0xDE8, 0xDE8, 1.20),
    (0xDE9, 0xDE9, 1.55),
    (0xDEF, 0xDEF, 1.20),
    (0x1A93, 0x1A93, 1.05),
    (0x1A99, 0x1A99, 1.05),
    (0x1B51, 0x1B51, 1.25),
    (0x1B57, 0x1B57, 1.05),
    (0x2150, 0x2151, 1.05),
    (0x2152, 0x2152, 1.50),
    (0x2153, 0x215E, 1.05),
    (0x2163, 0x2163, 1.10),
    (0x2165, 0x2165, 1.10),
    (0x2166, 0x2166, 1.40),
    (0x2167, 0x2167, 1.70),
    (0x2168, 0x2168, 1.15),
    (0x216A, 0x216A, 1.15),
    (0x216B, 0x216B, 1.45),
    (0x2176, 0x2176, 1.25),
    (0x2177, 0x2177, 1.50),
    (0x217B, 0x217B, 1.25),
    (0x217F, 0x217F, 1.05),
    (0x2180, 0x2180, 1.30),
    (0x2182, 0x2182, 1.30),
    (0x2188, 0x2188, 1.25),
    (0x2189, 0x2189, 1.05),
    (0x2460, 0x2468, 1.40),
    (0x24EA, 0x24EA, 1.40),
    (0x2780, 0x2788, 1.40),
    (0xA9D3, 0xA9D3, 1.40),
    (0xA9D7, 0xA9D7, 1.20),
    (0xA9D8, 0xA9D8, 1.05),
    (0xA9D9, 0xA9D9, 1.40),
    (0xA9F9, 0xA9F9, 1.15),
    (0xAA58, 0xAA58, 1.05),
    (0xAA59, 0xAA59, 1.10),
    (0x10169, 0x1016A, 1.05),
    (0x1016B, 0x1016B, 1.15),
    (0x1016D, 0x1016D, 1.20),
    (0x1016E, 0x1016E, 1.40),
    (0x10177, 0x10177, 1.10),
    (0x1018A, 0x1018A, 1.05),
    (0x102E2, 0x102E2, 1.10),
    (0x102E3, 0x102E3, 1.55),
    (0x102E6, 0x102E6, 1.05),
    (0x102F1, 0x102F1, 1.05),
    (0x102F4, 0x102F4, 1.25),
    (0x1087E, 0x1087E, 1.15),
    (0x109BC, 0x109BC, 1.65),
    (0x109C6, 0x109C6, 1.30),
    (0x109C9, 0x109C9, 1.30),
    (0x109CA, 0x109CA, 1.35),
    (0x109CC, 0x109CC, 1.50),
    (0x109CD, 0x109CD, 1.30),
    (0x109CE, 0x109CE, 1.50),
    (0x109CF, 0x109CF, 1.40),
    (0x109D2, 0x109DA, 1.60),
    (0x109DB, 0x109E1, 1.55),
    (0x109E2, 0x109E2, 1.75),
    (0x109E3, 0x109E3, 1.70),
    (0x109E4, 0x109EC, 1.30),
    (0x109ED, 0x109F5, 1.45),
    (0x109FC, 0x109FF, 1.05),
    (0x10B7B, 0x10B7B, 1.20),
    (0x10BAC, 0x10BAC, 1.20),
    (0x10BAF, 0x10BAF, 1.25),
    (0x10E62, 0x10E62, 1.10),
    (0x10E6D, 0x10E6D, 1.20),
    (0x10E78, 0x10E78, 1.05),
    (0x10E7C, 0x10E7C, 1.15),
    (0x10E7D, 0x10E7E, 1.10),
    (0x10F20, 0x10F20, 1.05),
    (0x10F21, 0x10F21, 1.30),
    (0x10F25, 0x10F25, 1.20),
    (0x10F54, 0x10F54, 1.65),
    (0x10FC5, 0x10FCB, 1.05),
    (0x1105B, 0x1105B, 1.05),
    (0x111E2, 0x111E2, 1.20),
    (0x111E3, 0x111E3, 1.35),
    (0x111E5, 0x111E5, 1.55),
    (0x111E9, 0x111E9, 1.45),
    (0x111EA, 0x111EA, 1.40),
    (0x111ED, 0x111ED, 1.50),
    (0x111EE, 0x111EE, 1.05),
    (0x111EF, 0x111EF, 1.10),
    (0x111F0, 0x111F0, 2.00),
    (0x111F3, 0x111F3, 1.40),
    (0x111F4, 0x111F4, 1.15),
    (0x11734, 0x11734, 1.30),
    (0x11735, 0x11735, 1.05),
    (0x11738, 0x11738, 1.30),
    (0x1173A, 0x1173A, 1.10),
    (0x1173B, 0x1173B, 1.30),
    (0x11950, 0x11959, 1.05),
    (0x11C61, 0x11C61, 1.05),
    (0x11F50, 0x11F59, 1.05),
    (0x11FC0, 0x11FC0, 1.85),
    (0x11FC3, 0x11FC3, 1.35),
    (0x11FC4, 0x11FC4, 1.10),
    (0x11FC5, 0x11FC5, 1.35),
    (0x11FC6, 0x11FC6, 1.45),
    (0x11FC7, 0x11FC7, 1.35),
    (0x11FC9, 0x11FC9, 1.40),
    (0x11FCA, 0x11FCA, 1.30),
    (0x11FCC, 0x11FCC, 1.90),
    (0x11FCD, 0x11FCD, 1.10),
    (0x11FCE, 0x11FCE, 1.55),
    (0x11FCF, 0x11FCF, 1.10),
    (0x11FD2, 0x11FD2, 1.15),
    (0x11FD3, 0x11FD3, 1.30),
    (0x11FD4, 0x11FD4, 1.05),
    (0x12401, 0x12401, 1.35),
    (0x12403, 0x12404, 1.35),
    (0x12405, 0x12406, 1.70),
    (0x12407, 0x12407, 2.05),
    (0x1240C, 0x1240D, 1.20),
    (0x1240E, 0x1240E, 1.45),
    (0x12412, 0x12413, 1.15),
    (0x12414, 0x12414, 1.35),
    (0x12417, 0x12417, 1.20),
    (0x12419, 0x1241A, 1.20),
    (0x1241B, 0x1241C, 1.50),
    (0x1241D, 0x1241D, 1.80),
    (0x1241F, 0x1241F, 1.10),
    (0x12420, 0x12420, 1.55),
    (0x12422, 0x12422, 1.20),
    (0x12423, 0x12423, 2.05),
    (0x12424, 0x12424, 2.90),
    (0x12425, 0x12426, 2.05),
    (0x12427, 0x12428, 2.90),
    (0x12429, 0x1242A, 3.80),
    (0x1242B, 0x1242B, 4.65),
    (0x1242C, 0x1242C, 1.15),
    (0x1242D, 0x1242D, 2.05),
    (0x1242E, 0x1242E, 2.90),
    (0x1242F, 0x12430, 2.05),
    (0x12431, 0x12431, 2.90),
    (0x12432, 0x12433, 1.15),
    (0x12435, 0x12435, 1.05),
    (0x12436, 0x12436, 1.45),
    (0x12437, 0x12438, 1.05),
    (0x12439, 0x12439, 1.45),
    (0x1243A, 0x1243A, 1.05),
    (0x1243D, 0x1243D, 1.15),
    (0x12440, 0x12440, 1.05),
    (0x12441, 0x12441, 1.50),
    (0x12443, 0x12443, 1.20),
    (0x12445, 0x12445, 1.50),
    (0x12447, 0x12447, 1.35),
    (0x1244D, 0x12450, 1.05),
    (0x1245A, 0x1245C, 1.15),
    (0x12461, 0x12461, 1.60),
    (0x12462, 0x12462, 1.40),
    (0x12465, 0x12465, 1.25),
    (0x12466, 0x12466, 1.50),
    (0x12467, 0x12468, 1.05),
    (0x16AC0, 0x16AC9, 1.05),
    (0x1D2C0, 0x1D2D3, 1.05),
    (0x1E4F0, 0x1E4F9, 1.05),
    (0x1EC71, 0x1EC71, 1.25),
    (0x1EC72, 0x1EC72, 1.20),
    (0x1EC73, 0x1EC73, 1.40),
    (0x1EC74, 0x1EC74, 1.10),
    (0x1EC76, 0x1EC76, 1.40),
    (0x1EC78, 0x1EC78, 1.40),
    (0x1EC7A, 0x1EC7A, 1.95),
    (0x1EC7B, 0x1EC7B, 2.00),
    (0x1EC7C, 0x1EC7C, 1.90),
    (0x1EC7D, 0x1EC7D, 2.20),
    (0x1EC7E, 0x1EC7E, 2.00),
    (0x1EC7F, 0x1EC7F, 1.95),
    (0x1EC80, 0x1EC80, 2.05),
    (0x1EC81, 0x1EC81, 1.80),
    (0x1EC82, 0x1EC82, 1.95),
    (0x1EC8C, 0x1EC8C, 1.90),
    (0x1EC8D, 0x1EC8D, 2.00),
    (0x1EC8E, 0x1EC8E, 1.85),
    (0x1EC8F, 0x1EC8F, 2.15),
    (0x1EC90, 0x1EC90, 2.05),
    (0x1EC91, 0x1EC93, 2.00),
    (0x1EC94, 0x1EC94, 1.90),
    (0x1EC95, 0x1EC95, 2.00),
    (0x1EC96, 0x1EC96, 2.10),
    (0x1EC97, 0x1EC97, 1.95),
    (0x1EC98, 0x1EC98, 2.15),
    (0x1EC99, 0x1EC99, 2.00),
    (0x1EC9A, 0x1EC9A, 1.95),
    (0x1EC9B, 0x1EC9B, 2.05),
    (0x1EC9C, 0x1EC9C, 1.80),
    (0x1EC9D, 0x1EC9D, 1.90),
    (0x1EC9E, 0x1EC9E, 1.20),
    (0x1EC9F, 0x1EC9F, 1.70),
    (0x1ECA0, 0x1ECA0, 1.30),
    (0x1ECA1, 0x1ECA1, 1.15),
    (0x1ECA2, 0x1ECA2, 1.70),
    (0x1ECB3, 0x1ECB3, 2.00),
    (0x1ECB4, 0x1ECB4, 1.25),
    (0x1ED01, 0x1ED2D, 1.05),
    (0x1ED2F, 0x1ED3D, 1.05),
)


# Rare punctuation/symbol fallback glyphs that exceed the generic 0.9em budget
# in DejaVu Sans Bold. Values are checked against the headless-Chrome
# Inter/Arial/sans-serif fallback stack and conservatively rounded upward
# to 0.05em.
_CANVAS_WIDE_FALLBACK_WIDTH_RANGES = (
    (0x00A9, 0x00A9, 1.05),
    (0x00AE, 0x00AE, 1.05),
    (0x060A, 0x060A, 1.20),
    (0x2014, 0x2015, 1.05),
    (0x2026, 0x2026, 1.05),
    (0x2030, 0x2030, 1.45),
    (0x2031, 0x2031, 1.90),
    (0x203B, 0x203B, 1.00),
    (0x2042, 0x2042, 1.05),
    (0x2047, 0x2047, 1.15),
    (0x2053, 0x2053, 1.05),
    (0x20A0, 0x20A0, 0.95),
    (0x20A5, 0x20A5, 1.05),
    (0x20A7, 0x20A7, 1.55),
    (0x20A8, 0x20A8, 1.25),
    (0x20A9, 0x20A9, 1.15),
    (0x20AA, 0x20AA, 0.95),
    (0x20AF, 0x20AF, 1.45),
    (0x2100, 0x2100, 1.15),
    (0x2101, 0x2101, 1.20),
    (0x2103, 0x2103, 1.25),
    (0x2105, 0x2105, 1.10),
    (0x2106, 0x2106, 1.15),
    (0x2109, 0x2109, 1.10),
    (0x2114, 0x2114, 1.00),
    (0x2116, 0x2116, 1.25),
    (0x2117, 0x2117, 1.05),
    (0x2120, 0x2120, 1.05),
    (0x2121, 0x2121, 1.30),
    (0x2122, 0x2122, 1.05),
    (0x213A, 0x213A, 0.95),
    (0x213B, 0x213B, 1.35),
    (0x222C, 0x222C, 0.95),
    (0x222D, 0x222D, 1.30),
    (0x222F, 0x222F, 1.00),
    (0x2230, 0x2230, 1.35),
    (0x2254, 0x2255, 1.10),
    (0x226A, 0x226B, 1.05),
    (0x22A2, 0x22A5, 0.95),
    (0x22A8, 0x22AF, 0.95),
    (0x22B6, 0x22B7, 1.05),
    (0x22C8, 0x22CC, 1.05),
    (0x22D8, 0x22D9, 1.45),
    (0x22EE, 0x22F1, 1.05),
    (0x22F2, 0x22F2, 1.20),
    (0x22FA, 0x22FA, 1.20),
    (0x2318, 0x2318, 1.00),
    (0x2324, 0x2325, 1.20),
    (0x2326, 0x2326, 1.45),
    (0x2327, 0x2327, 1.20),
    (0x2328, 0x2328, 1.45),
    (0x232B, 0x232B, 1.45),
    (0x2387, 0x2387, 1.20),
    (0x23CF, 0x23CF, 0.95),
    (0x25A0, 0x25A9, 0.95),
    (0x25AC, 0x25AC, 1.05),
    (0x25AD, 0x25AD, 0.95),
    (0x25D9, 0x25DB, 1.00),
    (0x25E7, 0x25EB, 0.95),
    (0x25EF, 0x25EF, 1.45),
    (0x25F0, 0x25F3, 0.95),
    (0x2601, 0x2601, 1.05),
    (0x260D, 0x260D, 1.05),
    (0x260E, 0x260F, 1.30),
    (0x2639, 0x263A, 1.05),
    (0x263B, 0x263B, 1.10),
    (0x26A2, 0x26A2, 1.05),
    (0x26A3, 0x26A3, 1.10),
    (0x26A4, 0x26A4, 1.20),
    (0x26A5, 0x26A5, 0.95),
    (0x27F4, 0x27F4, 1.20),
    (0x27F5, 0x27F6, 1.45),
    (0x27F7, 0x27F7, 1.80),
    (0x27F8, 0x27F9, 1.45),
    (0x27FA, 0x27FA, 1.80),
    (0x27FB, 0x27FF, 1.45),
    (0x29CF, 0x29D5, 1.05),
    (0x2A00, 0x2A02, 1.05),
    (0x2A0C, 0x2A0C, 1.70),
    (0x2B12, 0x2B15, 0.95),
    (0x2B1A, 0x2B1A, 0.95),
    (0x2B24, 0x2B24, 1.15),
    (0xFFFD, 0xFFFD, 1.15),
)
_CANVAS_NON_COLLAPSIBLE_WHITESPACE_WIDTH_UNITS = {
    0x0085: 0.0,  # NEXT LINE
    0x00A0: 0.35,  # NO-BREAK SPACE
    0x1680: 0.50,  # OGHAM SPACE MARK
    0x2000: 0.60,  # EN QUAD
    0x2001: 1.12,  # EM QUAD
    0x2002: 0.55,  # EN SPACE
    0x2003: 1.05,  # EM SPACE
    0x2004: 0.35,  # THREE-PER-EM SPACE
    0x2005: 0.28,  # FOUR-PER-EM SPACE
    0x2006: 0.20,  # SIX-PER-EM SPACE
    0x2007: 0.70,  # FIGURE SPACE
    0x2008: 0.35,  # PUNCTUATION SPACE
    0x2009: 0.22,  # THIN SPACE
    0x200A: 0.12,  # HAIR SPACE
    0x2028: 0.35,  # LINE SEPARATOR
    0x2029: 0.35,  # PARAGRAPH SEPARATOR
    0x202F: 0.22,  # NARROW NO-BREAK SPACE
    0x205F: 0.32,  # MEDIUM MATHEMATICAL SPACE
    0x3000: 1.05,  # IDEOGRAPHIC SPACE
}


def _canvas_is_grapheme_extend(character: str) -> bool:
    codepoint = ord(character)
    return (
        unicodedata.category(character) in {"Mn", "Me"}
        or 0xFE00 <= codepoint <= 0xFE0F
        or 0xE0100 <= codepoint <= 0xE01EF
        or 0x1F3FB <= codepoint <= 0x1F3FF
        or 0xE0020 <= codepoint <= 0xE007F
    )


def _canvas_is_regional_indicator(character: str) -> bool:
    return 0x1F1E6 <= ord(character) <= 0x1F1FF


def _canvas_xml_compatible_text(value: str) -> str:
    """Replace XML 1.0-forbidden code points before layout-sensitive processing."""

    return "".join(
        character if _xml_10_character_allowed(character) else "\uFFFD"
        for character in value
    )


def _canvas_bounded_xml_compatible_prefix(
    value: str,
    *,
    max_clusters: int | None,
    max_codepoints: int,
) -> tuple[str, bool]:
    """Bound grapheme work while matching the XML text that will be emitted."""

    scan_limit = max(1, max_codepoints) + MAX_GRAPHEME_CLUSTER_CODEPOINTS + 1
    source_probe = value[:scan_limit]
    if any(not _xml_10_character_allowed(character) for character in source_probe):
        normalized_probe = _canvas_xml_compatible_text(source_probe)
        prefix, truncated = bounded_grapheme_prefix(
            normalized_probe,
            max_clusters=max_clusters,
            max_codepoints=max_codepoints,
        )
        return prefix, truncated or len(value) > scan_limit
    return bounded_grapheme_prefix(
        value,
        max_clusters=max_clusters,
        max_codepoints=max_codepoints,
    )


def _canvas_collapse_inline_whitespace(value: str) -> str:
    """Match SVG's default inline space/tab collapsing without removing newlines."""

    return re.sub(r"[ \t]+", " ", value)


def _canvas_is_collapsible_inline_whitespace(cluster: str) -> bool:
    return cluster in {" ", "\t"}


def _canvas_has_collapsible_inline_whitespace_prefix(cluster: str) -> bool:
    return bool(cluster) and cluster[0] in {" ", "\t"}


def _canvas_is_single_line_collapsible_whitespace(cluster: str) -> bool:
    return cluster in {" ", "\t", "\r", "\n", "\r\n"}


def _canvas_is_non_collapsible_whitespace(character: str) -> bool:
    return character.isspace() and character not in {" ", "\t", "\r", "\n"}


def _canvas_has_non_collapsible_whitespace(value: str) -> bool:
    return any(_canvas_is_non_collapsible_whitespace(character) for character in value)


def _canvas_has_layout_content(value: str) -> bool:
    return bool(value.strip(" \t\r\n"))


def _canvas_resolve_fsi_opener_normalized(value: str, start_index: int) -> str:
    """Resolve FSI from an already XML-compatible source."""

    nested_isolates = 0
    for index in range(start_index + 1, len(value)):
        character = value[index]
        bidi_class = unicodedata.bidirectional(character)
        if bidi_class == "B":
            break
        if (
            character in _CANVAS_BIDI_ISOLATE_OPENERS
            or character == _CANVAS_BIDI_FSI
        ):
            nested_isolates += 1
            continue
        if character == _CANVAS_BIDI_PDI:
            if nested_isolates:
                nested_isolates -= 1
                continue
            break
        if nested_isolates:
            continue
        if bidi_class == "L":
            return "\u2066"
        if bidi_class in {"R", "AL"}:
            return "\u2067"
    return "\u2066"


def _canvas_resolve_fsi_opener(value: str, start_index: int) -> str:
    """Resolve FSI from its first strong character outside nested isolates."""

    return _canvas_resolve_fsi_opener_normalized(
        _canvas_xml_compatible_text(value),
        start_index,
    )


def _canvas_resolve_fsi_opener_bounded(
    value: str,
    start_index: int,
    *,
    max_scan_codepoints: int,
) -> tuple[str | None, int]:
    """Resolve one FSI with a caller-owned total scan budget."""

    nested_isolates = 0
    scanned = 0
    index = start_index + 1
    while index < len(value):
        if scanned >= max_scan_codepoints:
            return None, scanned
        character = value[index]
        scanned += 1
        index += 1
        if not _xml_10_character_allowed(character):
            character = "�"
        bidi_class = unicodedata.bidirectional(character)
        if bidi_class == "B":
            return "⁦", scanned
        if (
            character in _CANVAS_BIDI_ISOLATE_OPENERS
            or character == _CANVAS_BIDI_FSI
        ):
            nested_isolates += 1
            continue
        if character == _CANVAS_BIDI_PDI:
            if nested_isolates:
                nested_isolates -= 1
                continue
            return "⁦", scanned
        if nested_isolates:
            continue
        if bidi_class == "L":
            return "⁦", scanned
        if bidi_class in {"R", "AL"}:
            return "⁧", scanned
    return "⁦", scanned


def _canvas_project_bidi_wrapped_lines(
    wrapped: Sequence[str],
    *,
    fsi_source: str | None = None,
) -> tuple[list[str], bool]:
    """Make each wrapped SVG text line an independent bidi-safe paragraph."""

    if not wrapped:
        return [], False

    wrapped = tuple(_canvas_xml_compatible_text(line) for line in wrapped)
    if fsi_source is not None:
        fsi_source = _canvas_xml_compatible_text(fsi_source)

    flattened = "".join(wrapped)
    fsi_source_cursor = 0
    remaining_fsi_scan = _MAX_CANVAS_TEXT_PROBE_CODEPOINTS
    stack: list[tuple[str, str, str]] = []
    projected: list[str] = []
    cursor = 0

    for line in wrapped:
        rendered = [entry[0] for entry in stack]
        for offset, character in enumerate(line):
            if character in _CANVAS_BIDI_EMBED_OPENERS:
                if len(stack) >= _CANVAS_MAX_BIDI_SCOPE_DEPTH:
                    return ["…"], True
                rendered.append(character)
                stack.append((character, _CANVAS_BIDI_PDF, "embedding"))
                continue
            if character in _CANVAS_BIDI_ISOLATE_OPENERS:
                if len(stack) >= _CANVAS_MAX_BIDI_SCOPE_DEPTH:
                    return ["…"], True
                rendered.append(character)
                stack.append((character, _CANVAS_BIDI_PDI, "isolate"))
                continue
            if character == _CANVAS_BIDI_FSI:
                if len(stack) >= _CANVAS_MAX_BIDI_SCOPE_DEPTH:
                    return ["…"], True
                if fsi_source is None:
                    resolved, scanned = _canvas_resolve_fsi_opener_bounded(
                        flattened,
                        cursor + offset,
                        max_scan_codepoints=remaining_fsi_scan,
                    )
                else:
                    source_index = fsi_source.find(
                        _CANVAS_BIDI_FSI, fsi_source_cursor
                    )
                    if source_index < 0:
                        return ["…"], True
                    fsi_source_cursor = source_index + 1
                    resolved, scanned = _canvas_resolve_fsi_opener_bounded(
                        fsi_source,
                        source_index,
                        max_scan_codepoints=remaining_fsi_scan,
                    )
                remaining_fsi_scan = max(0, remaining_fsi_scan - scanned)
                if resolved is None:
                    return ["…"], True
                rendered.append(resolved)
                stack.append((resolved, _CANVAS_BIDI_PDI, "isolate"))
                continue

            if unicodedata.bidirectional(character) == "B":
                rendered.extend(entry[1] for entry in reversed(stack))
                stack.clear()
                rendered.append(character)
                continue

            rendered.append(character)
            if character == _CANVAS_BIDI_PDF:
                if stack and stack[-1][2] == "embedding":
                    stack.pop()
                continue
            if character == _CANVAS_BIDI_PDI:
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index][2] == "isolate":
                        del stack[index:]
                        break

        rendered.extend(entry[1] for entry in reversed(stack))
        projected.append("".join(rendered))
        cursor += len(line)

    return projected, False


def _canvas_grapheme_clusters(value: str) -> Iterator[str]:
    """Yield Unicode extended grapheme clusters without materializing the input."""

    yield from iter_grapheme_clusters(value)


def _canvas_has_extended_graphemes(value: str) -> bool:
    if value.isascii() and "\r" not in value and "\n" not in value:
        return False
    return any(len(cluster) > 1 for cluster in _canvas_grapheme_clusters(value))


def _canvas_fallback_letter_width_units(character: str) -> float | None:
    codepoint = ord(character)
    if codepoint <= 0x7F or not unicodedata.category(character).startswith("L"):
        return None
    width_units = _CANVAS_FALLBACK_LETTER_WIDTH_UNITS
    for first, last, floor_units in _CANVAS_FALLBACK_LETTER_FLOOR_RANGES:
        if codepoint < first:
            break
        if codepoint <= last:
            width_units = max(width_units, floor_units)
            break
    for first, last, calibrated_units in _CANVAS_WIDE_FALLBACK_LETTER_WIDTH_RANGES:
        if codepoint < first:
            break
        if codepoint <= last:
            width_units = max(width_units, calibrated_units)
            break
    if codepoint > 0xFFFF:
        for first, last, calibrated_units in _CANVAS_SUPPLEMENTARY_FALLBACK_LETTER_WIDTH_RANGES:
            if codepoint < first:
                break
            if codepoint <= last:
                width_units = max(width_units, calibrated_units)
                break
    return width_units


def _canvas_fallback_numeric_width_units(character: str) -> float | None:
    codepoint = ord(character)
    if codepoint <= 0x7F or unicodedata.category(character) not in {"Nd", "Nl", "No"}:
        return None
    width_units = _CANVAS_FALLBACK_NUMERIC_WIDTH_UNITS
    low = 0
    high = len(_CANVAS_WIDE_FALLBACK_NUMERIC_WIDTH_RANGES)
    while low < high:
        middle = (low + high) // 2
        first, last, calibrated_units = _CANVAS_WIDE_FALLBACK_NUMERIC_WIDTH_RANGES[middle]
        if codepoint < first:
            high = middle
        elif codepoint > last:
            low = middle + 1
        else:
            return max(width_units, calibrated_units)
    return width_units


def _canvas_character_width_units(character: str) -> float:
    if not _xml_10_character_allowed(character):
        return _CANVAS_XML_REPLACEMENT_WIDTH_UNITS
    if _canvas_is_collapsible_inline_whitespace(character):
        return 0.35
    if character in {"\r", "\n"}:
        return 0.0
    if _canvas_is_non_collapsible_whitespace(character):
        return _CANVAS_NON_COLLAPSIBLE_WHITESPACE_WIDTH_UNITS.get(
            ord(character),
            1.0,
        )
    if character in _CANVAS_BOLD_FALLBACK_OPERATORS:
        return _CANVAS_BOLD_FALLBACK_OPERATOR_WIDTH_UNITS
    if character in _CANVAS_BOLD_FALLBACK_DEFAULT_CHARS:
        return _CANVAS_BOLD_FALLBACK_DEFAULT_WIDTH_UNITS
    if character in _NARROW_CHARS:
        return _CANVAS_WRAP_DEFAULT_WIDTH_UNITS
    codepoint = ord(character)
    letter_width = _canvas_fallback_letter_width_units(character)
    numeric_width = _canvas_fallback_numeric_width_units(character)
    fallback_width = max(letter_width or 0.0, numeric_width or 0.0)
    if 0x0400 <= codepoint <= 0x052F:
        return max(_CANVAS_CYRILLIC_WIDTH_UNITS, fallback_width)
    if codepoint >= 0x1F000 and is_extended_pictographic(character):
        return max(_CANVAS_SUPPLEMENTARY_PICTOGRAPHIC_WIDTH_UNITS, fallback_width)
    if codepoint > 0x7F and unicodedata.east_asian_width(character) in {"W", "F"}:
        return max(_CANVAS_EAST_ASIAN_WIDE_WIDTH_UNITS, fallback_width)
    for first, last, width_units in _CANVAS_WIDE_FALLBACK_WIDTH_RANGES:
        if codepoint < first:
            break
        if codepoint <= last:
            return max(width_units, fallback_width)
    if letter_width is not None:
        return letter_width
    if numeric_width is not None:
        return numeric_width
    return _character_width_units(
        character,
        non_ascii=0.9,
        uppercase=0.86,
        default=_CANVAS_WRAP_DEFAULT_WIDTH_UNITS,
    )


def _canvas_is_zero_advance_control(character: str) -> bool:
    codepoint = ord(character)
    return (
        character in {_CANVAS_ZWNJ, _CANVAS_ZWJ}
        or codepoint in _CANVAS_BIDI_ZERO_ADVANCE_CODEPOINTS
        or codepoint in _CANVAS_INVISIBLE_ZERO_ADVANCE_CODEPOINTS
        or 0xFE00 <= codepoint <= 0xFE0F
        or 0xE0100 <= codepoint <= 0xE01EF
        or 0xE0020 <= codepoint <= 0xE007F
    )


def _canvas_spacing_mark_cluster_width_units(visible: list[str]) -> float:
    spacing_marks = [
        character for character in visible if unicodedata.category(character) == "Mc"
    ]
    fallback = sum(_canvas_character_width_units(character) for character in visible)
    if len(spacing_marks) != 1:
        return fallback

    base_width = sum(
        _canvas_character_width_units(character)
        for character in visible
        if unicodedata.category(character) != "Mc"
    )
    if base_width == 0.0:
        return fallback

    codepoint = ord(spacing_marks[0])
    for first, last, calibrated_width in _CANVAS_SPACING_MARK_CLUSTER_WIDTH_RANGES:
        if first <= codepoint <= last:
            return max(base_width, min(fallback, calibrated_width))
    return fallback


def _canvas_zwj_uses_shaping_script(cluster: str) -> bool:
    return any(
        first <= ord(character) <= last
        for character in cluster
        if character not in {_CANVAS_ZWNJ, _CANVAS_ZWJ}
        for first, last in _CANVAS_ZWJ_SHAPING_SCRIPT_RANGES
    )


def _canvas_shaping_zwj_wide_letter_width_units(character: str) -> float:
    codepoint = ord(character)
    for first, last, width_units in _CANVAS_ZWJ_SHAPING_WIDE_LETTER_WIDTH_RANGES:
        if codepoint < first:
            break
        if codepoint <= last:
            return width_units
    return 0.0


def _canvas_shaping_zwj_linear_letter_width_units(character: str) -> float:
    codepoint = ord(character)
    for first, last, width_units in _CANVAS_ZWJ_LINEAR_FALLBACK_LETTER_WIDTH_RANGES:
        if codepoint < first:
            break
        if codepoint <= last:
            return width_units
    return _CANVAS_ZWJ_LINEAR_FALLBACK_DEFAULT_WIDTH_UNITS


def _canvas_grapheme_width_units(cluster: str) -> float:
    if cluster and all(_canvas_is_zero_advance_control(item) for item in cluster):
        return 0.0
    visible = [
        character
        for character in cluster
        if not _canvas_is_zero_advance_control(character)
        and not _canvas_is_grapheme_extend(character)
    ]
    if not visible:
        return _CANVAS_WRAP_DEFAULT_WIDTH_UNITS
    widths = [
        (
            _CANVAS_SPACING_MARK_WIDTH_UNITS
            if unicodedata.category(character) == "Mc"
            else _canvas_character_width_units(character)
        )
        for character in visible
    ]
    if _CANVAS_ZWJ in cluster:
        if any(is_extended_pictographic(item) for item in cluster):
            return max(2.0, max(widths))
        if _canvas_zwj_uses_shaping_script(cluster):
            shaping_widths = [
                (
                    _CANVAS_SPACING_MARK_WIDTH_UNITS
                    if unicodedata.category(character) == "Mc"
                    else (
                        _character_width_units(
                            character,
                            non_ascii=0.9,
                            uppercase=0.86,
                            default=_CANVAS_WRAP_DEFAULT_WIDTH_UNITS,
                        )
                        if unicodedata.category(character).startswith("L")
                        else _canvas_character_width_units(character)
                    )
                )
                for character in visible
            ]
            wide_letter_width = max(
                (
                    _canvas_shaping_zwj_wide_letter_width_units(character)
                    for character in visible
                ),
                default=0.0,
            )
            shaping_letters = [
                character
                for character in visible
                if unicodedata.category(character).startswith("L")
            ]
            linear_fallback_width = (
                sum(
                    max(
                        _canvas_shaping_zwj_linear_letter_width_units(character),
                        _canvas_character_width_units(character),
                    )
                    for character in shaping_letters
                )
                if shaping_letters
                else 0.0
            )
            return max(
                _CANVAS_SCRIPT_ZWJ_MIN_WIDTH_UNITS,
                max(shaping_widths),
                wide_letter_width,
                linear_fallback_width,
            )
        return sum(widths)
    if len(visible) == 2 and all(_canvas_is_regional_indicator(item) for item in visible):
        return max(2.0, max(widths))
    if (
        _CANVAS_EMOJI_PRESENTATION_SELECTOR in cluster or _CANVAS_KEYCAP in cluster
    ):
        # VS16/keycap presentation selects the browser emoji fallback rather than
        # the plain base-glyph fallback. Chromium SVG/Canvas scans bound that
        # presentation path at 1.25em for the accepted font stacks.
        return _CANVAS_EMOJI_PRESENTATION_WIDTH_UNITS
    if any(unicodedata.category(character) == "Mc" for character in visible):
        return _canvas_spacing_mark_cluster_width_units(visible)
    return sum(widths)


def _canvas_svg_cluster_width_units(
    cluster: str, *, previous_cluster: str | None
) -> float:
    if _canvas_is_collapsible_inline_whitespace(cluster):
        if (
            previous_cluster is not None
            and _canvas_is_collapsible_inline_whitespace(previous_cluster)
        ):
            return 0.0
        return _canvas_grapheme_width_units(" ")
    return _canvas_grapheme_width_units(cluster)


def _canvas_single_line_cluster_width_units(
    cluster: str, *, previous_cluster: str | None
) -> float:
    if _canvas_is_single_line_collapsible_whitespace(cluster):
        if (
            previous_cluster is not None
            and _canvas_is_single_line_collapsible_whitespace(previous_cluster)
        ):
            return 0.0
        return _canvas_grapheme_width_units(" ")
    return _canvas_grapheme_width_units(cluster)


def _estimated_canvas_single_line_width(value: str, *, size: int) -> float:
    units = 0.0
    previous_cluster: str | None = None
    for cluster in _canvas_grapheme_clusters(value):
        units += _canvas_single_line_cluster_width_units(
            cluster,
            previous_cluster=previous_cluster,
        )
        previous_cluster = cluster
    return units * size


def _estimated_canvas_wrap_width(value: str, *, size: int) -> float:
    value = _canvas_collapse_inline_whitespace(value)
    units = sum(
        _canvas_grapheme_width_units(cluster)
        for cluster in _canvas_grapheme_clusters(value)
    )
    return units * size


def _canvas_escaped_text_bytes(value: str) -> int:
    return len(_canvas_xml(value).encode("utf-8"))


def _canvas_ellipsize_to_limits(
    value: str,
    *,
    size: int,
    max_width: float,
    max_bytes: int | None = None,
    single_line_svg_whitespace: bool = False,
) -> str:
    ellipsis = "…"
    ellipsis_width = _estimated_canvas_wrap_width(ellipsis, size=size)
    ellipsis_bytes = _canvas_escaped_text_bytes(ellipsis)
    if ellipsis_width > max_width or (
        max_bytes is not None and ellipsis_bytes > max_bytes
    ):
        return ""
    width_budget = max_width - ellipsis_width
    byte_budget = None if max_bytes is None else max_bytes - ellipsis_bytes
    selected: list[str] = []
    width_used = 0.0
    bytes_used = 0
    for cluster in _canvas_grapheme_clusters(value.rstrip(" \t")):
        width_function = (
            _canvas_single_line_cluster_width_units
            if single_line_svg_whitespace
            else _canvas_svg_cluster_width_units
        )
        cluster_width = (
            width_function(
                cluster,
                previous_cluster=selected[-1] if selected else None,
            )
            * size
        )
        cluster_bytes = _canvas_escaped_text_bytes(cluster)
        if width_used + cluster_width > width_budget:
            break
        if byte_budget is not None and bytes_used + cluster_bytes > byte_budget:
            break
        selected.append(cluster)
        width_used += cluster_width
        bytes_used += cluster_bytes
    candidate = "".join(selected).rstrip(" \t")
    return candidate + ellipsis if candidate else ellipsis


def _canvas_ellipsize_to_width(value: str, *, size: int, max_width: float) -> str:
    return _canvas_ellipsize_to_limits(
        value,
        size=size,
        max_width=max_width,
    )


def _canvas_ellipsize_to_escaped_bytes(value: str, *, max_bytes: int) -> str:
    value, grapheme_truncated = bounded_grapheme_prefix(
        value,
        max_clusters=max(1, max_bytes + 1),
        max_codepoints=min(
            _MAX_CANVAS_TEXT_PROBE_CODEPOINTS,
            max(1, max_bytes) + MAX_GRAPHEME_CLUSTER_CODEPOINTS + 1,
        ),
    )
    if grapheme_truncated:
        return _canvas_ellipsize_to_limits(
            value,
            size=1,
            max_width=float("inf"),
            max_bytes=max_bytes,
        )
    if _canvas_escaped_text_bytes(value) <= max_bytes:
        return value
    return _canvas_ellipsize_to_limits(
        value,
        size=1,
        max_width=float("inf"),
        max_bytes=max_bytes,
    )


def _canvas_fit_single_line_unprojected(
    value: str,
    *,
    size: int,
    max_width: float,
    max_bytes: int,
) -> tuple[str, bool]:
    """Fit one Canvas label before bidi-scope projection."""

    if not value:
        return "", False
    value, grapheme_truncated = _canvas_bounded_xml_compatible_prefix(
        value,
        max_clusters=max(1, max_bytes + 1),
        max_codepoints=min(
            _MAX_CANVAS_TEXT_PROBE_CODEPOINTS,
            max(1, max_bytes) + MAX_GRAPHEME_CLUSTER_CODEPOINTS + 1,
        ),
    )
    if grapheme_truncated:
        return (
            _canvas_ellipsize_to_limits(
                value,
                size=size,
                max_width=max_width,
                max_bytes=max_bytes,
                single_line_svg_whitespace=True,
            ),
            True,
        )
    if (
        _estimated_canvas_single_line_width(value, size=size) <= max_width
        and _canvas_escaped_text_bytes(value) <= max_bytes
    ):
        return value, False
    return (
        _canvas_ellipsize_to_limits(
            value,
            size=size,
            max_width=max_width,
            max_bytes=max_bytes,
            single_line_svg_whitespace=True,
        ),
        True,
    )


def _canvas_project_truncated_single_line_bidi(
    value: str,
    fitted: str,
) -> tuple[str, bool]:
    """Project only the admitted truncated prefix, with bounded FSI lookahead."""

    has_scope_opener = any(
        character in _CANVAS_BIDI_EMBED_OPENERS
        or character in _CANVAS_BIDI_ISOLATE_OPENERS
        or character == _CANVAS_BIDI_FSI
        for character in fitted
    )
    if not has_scope_opener:
        return fitted, False

    remaining_scan = _MAX_CANVAS_TEXT_PROBE_CODEPOINTS
    source_cursor = 0
    source_search_limit = min(
        len(value),
        _MAX_CANVAS_TEXT_PROBE_CODEPOINTS
        + MAX_GRAPHEME_CLUSTER_CODEPOINTS
        + 1,
    )
    resolved: list[str] = []
    for character in fitted:
        if character != _CANVAS_BIDI_FSI:
            resolved.append(character)
            continue
        source_index = value.find(
            _CANVAS_BIDI_FSI,
            source_cursor,
            source_search_limit,
        )
        if source_index < 0:
            return "…", True
        source_cursor = source_index + 1
        opener, scanned = _canvas_resolve_fsi_opener_bounded(
            value,
            source_index,
            max_scan_codepoints=remaining_scan,
        )
        remaining_scan = max(0, remaining_scan - scanned)
        if opener is None:
            return "…", True
        resolved.append(opener)

    projected, projection_truncated = _canvas_project_bidi_wrapped_lines(
        ["".join(resolved)]
    )
    return (projected[0] if projected else ""), projection_truncated


def _canvas_fit_single_line(
    value: str,
    *,
    size: int,
    max_width: float,
    max_bytes: int,
) -> tuple[str, bool]:
    """Fit one Canvas label without silent clipping or broken bidi scopes."""

    fitted, truncated = _canvas_fit_single_line_unprojected(
        value,
        size=size,
        max_width=max_width,
        max_bytes=max_bytes,
    )
    if not truncated:
        return fitted, False

    fitted, bidi_projection_truncated = _canvas_project_truncated_single_line_bidi(
        value,
        fitted,
    )
    if bidi_projection_truncated:
        marker = "…"
        if (
            _estimated_canvas_single_line_width(marker, size=size) <= max_width
            and _canvas_escaped_text_bytes(marker) <= max_bytes
        ):
            return marker, True
        return "", True

    if (
        _estimated_canvas_single_line_width(fitted, size=size) <= max_width
        and _canvas_escaped_text_bytes(fitted) <= max_bytes
    ):
        return fitted, True

    refitted = _canvas_ellipsize_to_limits(
        fitted,
        size=size,
        max_width=max_width,
        max_bytes=max_bytes,
        single_line_svg_whitespace=True,
    )
    if refitted:
        reprojected, refit_projection_truncated = _canvas_project_bidi_wrapped_lines(
            [refitted]
        )
        final = reprojected[0] if reprojected else ""
        if (
            not refit_projection_truncated
            and _estimated_canvas_single_line_width(final, size=size) <= max_width
            and _canvas_escaped_text_bytes(final) <= max_bytes
        ):
            return final, True

    marker = "…"
    if (
        _estimated_canvas_single_line_width(marker, size=size) <= max_width
        and _canvas_escaped_text_bytes(marker) <= max_bytes
    ):
        return marker, True
    return "", True


def _canvas_wrap_source_line(
    value: str, *, size: int, max_width: float, max_lines: int
) -> tuple[list[str], bool]:
    """Wrap one line incrementally without splitting display graphemes."""

    if max_lines <= 0:
        return [], bool(value)
    value = _canvas_collapse_inline_whitespace(value).strip(" \t")
    if not value:
        return [], False
    lines: list[str] = []
    current: list[str] = []
    current_width = 0.0
    last_space_index = -1

    for cluster in _canvas_grapheme_clusters(value):
        if not current:
            cluster = cluster.lstrip(" \t")
            if not cluster:
                continue
        cluster_width = (
            _canvas_svg_cluster_width_units(
                cluster,
                previous_cluster=current[-1] if current else None,
            )
            * size
        )
        while current and current_width + cluster_width > max_width:
            if last_space_index >= 0:
                emitted_clusters = current[:last_space_index]
                break_cluster = current[last_space_index]
                carry = current[last_space_index + 1 :]
                carry_prefix = break_cluster.lstrip(" \t")
                if carry_prefix:
                    carry.insert(0, carry_prefix)
            else:
                emitted_clusters = current
                carry = []
            emitted = "".join(emitted_clusters).strip(" \t")
            if emitted:
                lines.append(emitted)
                if len(lines) >= max_lines:
                    return lines, True
            carry_text = "".join(carry).strip(" \t")
            current = list(_canvas_grapheme_clusters(carry_text))
            current_width = _estimated_canvas_wrap_width(carry_text, size=size)
            last_space_index = -1
            for index, item in enumerate(current):
                if _canvas_has_collapsible_inline_whitespace_prefix(item):
                    last_space_index = index
            while current and current_width > max_width:
                fitted_carry: list[str] = []
                fitted_width = 0.0
                for item in current:
                    item_width = (
                        _canvas_svg_cluster_width_units(
                            item,
                            previous_cluster=(
                                fitted_carry[-1] if fitted_carry else None
                            ),
                        )
                        * size
                    )
                    if fitted_carry and fitted_width + item_width > max_width:
                        break
                    if not fitted_carry and item_width > max_width:
                        if len(lines) < max_lines:
                            lines.append(item)
                        return lines, True
                    fitted_carry.append(item)
                    fitted_width += item_width

                if not fitted_carry or len(fitted_carry) == len(current):
                    break
                emitted_carry = "".join(fitted_carry).strip(" \t")
                if emitted_carry:
                    lines.append(emitted_carry)
                    if len(lines) >= max_lines:
                        return lines, True
                current = current[len(fitted_carry) :]
                carry_text = "".join(current).strip(" \t")
                current = list(_canvas_grapheme_clusters(carry_text))
                current_width = _estimated_canvas_wrap_width(carry_text, size=size)
                last_space_index = -1
                for index, item in enumerate(current):
                    if _canvas_has_collapsible_inline_whitespace_prefix(item):
                        last_space_index = index

            if not current:
                cluster = cluster.lstrip(" \t")
                if not cluster:
                    cluster_width = 0.0
                    break
            cluster_width = (
                _canvas_svg_cluster_width_units(
                    cluster,
                    previous_cluster=current[-1] if current else None,
                )
                * size
            )
        if not cluster:
            continue
        if not current and cluster_width > max_width:
            if len(lines) < max_lines:
                lines.append(cluster)
            return lines, True
        current.append(cluster)
        current_width += cluster_width
        if _canvas_has_collapsible_inline_whitespace_prefix(cluster):
            last_space_index = len(current) - 1

    trailing = "".join(current).strip(" \t")
    if trailing:
        if len(lines) >= max_lines:
            return lines, True
        lines.append(trailing)

    if (
        len(lines) >= 2
        and not any(
            _canvas_is_collapsible_inline_whitespace(character)
            for character in value
        )
    ):
        donor = list(_canvas_grapheme_clusters(lines[-2]))
        fragment = list(_canvas_grapheme_clusters(lines[-1]))
        while len(fragment) < 4 and len(donor) > 4:
            candidate = donor[-1] + "".join(fragment)
            if _estimated_canvas_wrap_width(candidate, size=size) > max_width:
                break
            fragment.insert(0, donor.pop())
        lines[-2] = "".join(donor)
        lines[-1] = "".join(fragment)
    return lines, False

def _canvas_adaptive_lines(
    value: str, *, size: int, max_width: float, max_lines: int
) -> tuple[list[tuple[str, bool]], bool]:
    """Wrap visible source text under an explicit line budget."""

    lines: list[tuple[str, bool]] = []
    paragraph_gap_pending = False
    for source_line in _canvas_iter_source_lines(value):
        if len(lines) >= max_lines:
            return lines, True
        if not source_line.strip(" \t"):
            if lines:
                paragraph_gap_pending = True
            continue
        wrapped, source_truncated = _canvas_wrap_source_line(
            source_line,
            size=size,
            max_width=max_width,
            max_lines=max_lines - len(lines),
        )
        projected, bidi_projection_truncated = _canvas_project_bidi_wrapped_lines(
            wrapped,
            fsi_source=source_line,
        )
        for wrapped_index, line in enumerate(projected):
            lines.append(
                (
                    line,
                    paragraph_gap_pending and wrapped_index == 0,
                )
            )
            paragraph_gap_pending = False
        if source_truncated or bidi_projection_truncated:
            return lines, True
    return lines, False


def _canvas_position_adaptive_lines(
    lines: Sequence[tuple[str, bool]], *, size: int
) -> tuple[tuple[str, int], ...]:
    baseline = size + 12
    line_height = size + 4
    paragraph_gap = max(6, size // 2)
    positioned: list[tuple[str, int]] = []
    for index, (line, gap_before) in enumerate(lines):
        if index:
            baseline += line_height
            if gap_before:
                baseline += paragraph_gap
        positioned.append((line, baseline))
    return tuple(positioned)


def _canvas_truncated_lines(
    lines: tuple[tuple[str, int], ...], *, size: int, max_width: float
) -> tuple[tuple[str, int], ...]:
    if not lines:
        return ()
    last_text, last_y = lines[-1]
    if last_text == "…":
        return (
            lines
            if _estimated_canvas_wrap_width(last_text, size=size) <= max_width
            else lines[:-1]
        )
    marker = _canvas_ellipsize_to_width(
        last_text,
        size=size,
        max_width=max_width,
    )
    if not marker:
        return lines[:-1]
    return (*lines[:-1], (marker, last_y))


def _canvas_limit_text_layout_bytes(
    layout: _CanvasTextLayout,
    *,
    max_width: float,
    max_bytes: int,
) -> _CanvasTextLayout:
    """Bound escaped visible label bytes while preserving grapheme boundaries."""

    remaining = max(0, max_bytes)
    limited: list[tuple[str, int]] = []
    byte_truncated = False
    for line, baseline in layout.lines:
        projected, bidi_projection_truncated = _canvas_project_bidi_wrapped_lines(
            [line]
        )
        safe_line = projected[0] if projected else ""
        if bidi_projection_truncated:
            byte_truncated = True
        line_bytes = _canvas_escaped_text_bytes(safe_line)
        if line_bytes <= remaining:
            limited.append((safe_line, baseline))
            remaining -= line_bytes
            continue
        marker = _canvas_ellipsize_to_limits(
            line,
            size=layout.size,
            max_width=max_width,
            max_bytes=remaining,
        )
        if marker:
            projected_marker, marker_projection_truncated = (
                _canvas_project_bidi_wrapped_lines([marker])
            )
            safe_marker = projected_marker[0] if projected_marker else ""
            if marker_projection_truncated:
                safe_marker = "…"
            if (
                safe_marker
                and _canvas_escaped_text_bytes(safe_marker) <= remaining
            ):
                limited.append((safe_marker, baseline))
            elif (
                _canvas_escaped_text_bytes("…") <= remaining
                and _estimated_canvas_wrap_width("…", size=layout.size)
                <= max_width
            ):
                limited.append(("…", baseline))
        byte_truncated = True
        break
    if len(limited) < len(layout.lines):
        byte_truncated = True
    return _CanvasTextLayout(
        size=layout.size,
        lines=tuple(limited),
        truncated=layout.truncated or byte_truncated,
    )

def _canvas_text_probe_cluster_limit(
    *, max_width: float, max_lines: int, max_bytes: int, min_size: int
) -> int:
    """Bound grapheme work to clusters that could affect visible output."""

    minimum_cluster_width = max(
        0.001,
        _canvas_character_width_units(" ") * min_size,
    )
    clusters_per_line = max(
        1,
        math.ceil(max_width / minimum_cluster_width) + 1,
    )
    geometry_limit = max(
        1,
        max_lines * clusters_per_line + max_lines + 1,
    )
    byte_limit = max(1, max_bytes + 1)
    return min(
        geometry_limit,
        byte_limit,
        _MAX_CANVAS_TEXT_PROBE_CLUSTERS,
    )


def _canvas_bounded_text_probe_prefix(
    value: str,
    *,
    geometry_cluster_limit: int,
    work_cluster_limit: int,
    max_codepoints: int,
) -> tuple[str, bool]:
    """Bound probe work without charging control-only clusters to geometry."""

    geometry_prefix, geometry_truncated = _canvas_bounded_xml_compatible_prefix(
        value,
        max_clusters=min(geometry_cluster_limit, work_cluster_limit),
        max_codepoints=max_codepoints,
    )
    if not any(
        _canvas_is_zero_advance_control(character)
        or _canvas_character_width_units(character) == 0.0
        for character in geometry_prefix
    ):
        return geometry_prefix, geometry_truncated

    prefix, work_truncated = _canvas_bounded_xml_compatible_prefix(
        value,
        max_clusters=work_cluster_limit,
        max_codepoints=max_codepoints,
    )
    selected: list[str] = []
    geometry_clusters = 0
    for cluster in _canvas_grapheme_clusters(prefix):
        consumes_geometry = _canvas_grapheme_width_units(cluster) > 0.0
        if consumes_geometry and geometry_clusters >= geometry_cluster_limit:
            return "".join(selected), True
        selected.append(cluster)
        if consumes_geometry:
            geometry_clusters += 1
    return prefix, work_truncated


def _canvas_text_layout(
    value: str,
    width_px: int,
    height_px: int,
    *,
    max_lines: int,
    max_bytes: int,
) -> _CanvasTextLayout:
    """Fit Canvas text inside explicit geometry without changing that geometry."""

    max_width = max(1.0, float(width_px))
    bottom_limit = max(1, height_px - 5)
    min_size = 12

    def truncation_marker_line() -> tuple[tuple[str, int], ...]:
        marker_y = min_size + 12
        if (
            marker_y > bottom_limit
            or _estimated_canvas_wrap_width("…", size=min_size) > max_width
        ):
            return ()
        return (("…", marker_y),)

    had_visible_text = bool(value.strip(" \t\r\n"))
    height_line_limit = max(1, height_px // (min_size + 4) + 2)
    effective_max_lines = min(max_lines, height_line_limit)
    if effective_max_lines <= 0 or max_bytes <= 0:
        return _CanvasTextLayout(size=16, lines=(), truncated=had_visible_text)
    probe_cluster_limit = _canvas_text_probe_cluster_limit(
        max_width=max_width,
        max_lines=effective_max_lines,
        max_bytes=max_bytes,
        min_size=min_size,
    )
    probe_work_cluster_limit = min(
        max(1, max_bytes + 1),
        _MAX_CANVAS_TEXT_PROBE_CLUSTERS,
    )
    collapsed_probe = _canvas_collapse_inline_whitespace(value)
    probe_prefix, probe_truncated = _canvas_bounded_text_probe_prefix(
        collapsed_probe,
        geometry_cluster_limit=probe_cluster_limit,
        work_cluster_limit=probe_work_cluster_limit,
        max_codepoints=_MAX_CANVAS_TEXT_PROBE_CODEPOINTS,
    )
    if collapsed_probe == value:
        value = probe_prefix
        grapheme_truncated = probe_truncated
    elif probe_truncated:
        value = probe_prefix
        grapheme_truncated = True
    else:
        source_prefix, source_truncated = _canvas_bounded_xml_compatible_prefix(
            value,
            max_clusters=None,
            max_codepoints=_MAX_CANVAS_TEXT_PROBE_CODEPOINTS,
        )
        if source_truncated:
            value = probe_prefix
            grapheme_truncated = probe_truncated
        else:
            value = source_prefix
            grapheme_truncated = False
    if not value.strip(" \t\r\n"):
        if not had_visible_text:
            return _CanvasTextLayout(size=16, lines=(), truncated=False)
        return _CanvasTextLayout(
            size=min_size,
            lines=truncation_marker_line(),
            truncated=True,
        )

    if (
        not _canvas_has_extended_graphemes(value)
        and not any(_canvas_is_zero_advance_control(character) for character in value)
        and _canvas_collapse_inline_whitespace(value) == value
        and not _canvas_has_non_collapsible_whitespace(value)
    ):
        legacy, legacy_truncated = _canvas_legacy_lines(
            value,
            width_px,
            max_lines=effective_max_lines,
        )
        legacy_positioned = tuple(
            (line, 28 + index * 20) for index, line in enumerate(legacy)
        )
        legacy_width_safe = all(
            not line or _estimated_canvas_wrap_width(line, size=16) <= max_width
            for line in legacy
        )
        if (
            not legacy_truncated
            and legacy_positioned
            and legacy_width_safe
            and legacy_positioned[-1][1] <= bottom_limit
        ):
            if grapheme_truncated:
                return _CanvasTextLayout(
                    size=16,
                    lines=_canvas_truncated_lines(
                        legacy_positioned,
                        size=16,
                        max_width=max_width,
                    ),
                    truncated=True,
                )
            return _CanvasTextLayout(size=16, lines=legacy_positioned, truncated=False)
    else:
        legacy_truncated = False

    candidate: tuple[tuple[str, int], ...] = ()
    candidate_truncated = legacy_truncated or grapheme_truncated
    candidate_size = min_size
    candidate_sizes = (
        (min_size,) if grapheme_truncated else range(16, min_size - 1, -1)
    )
    for size in candidate_sizes:
        wrapped, wrapped_truncated = _canvas_adaptive_lines(
            value,
            size=size,
            max_width=max_width,
            max_lines=effective_max_lines,
        )
        candidate = _canvas_position_adaptive_lines(wrapped, size=size)
        candidate_truncated = wrapped_truncated or grapheme_truncated
        candidate_size = size
        if (
            not wrapped_truncated
            and not grapheme_truncated
            and (not candidate or candidate[-1][1] <= bottom_limit)
        ):
            return _CanvasTextLayout(size=size, lines=candidate, truncated=False)

    visible = tuple(line for line in candidate if line[1] <= bottom_limit)
    if not visible:
        return _CanvasTextLayout(
            size=min_size,
            lines=truncation_marker_line(),
            truncated=True,
        )

    truncated = candidate_truncated or len(visible) < len(candidate)
    if truncated:
        visible = _canvas_truncated_lines(
            visible,
            size=candidate_size,
            max_width=max_width,
        )
    return _CanvasTextLayout(
        size=candidate_size,
        lines=visible,
        truncated=truncated,
    )


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

    pair_counts: dict[tuple[str, str], int] = {}
    pair_slots: dict[tuple[str, str], int] = {}
    for edge in edges:
        key = tuple(sorted((str(edge["from"]), str(edge["to"]))))
        pair_counts[key] = pair_counts.get(key, 0) + 1

    edge_layouts = []
    for index, edge in enumerate(edges):
        source_id = str(edge["from"])
        target_id = str(edge["to"])
        source = node_by_id[source_id]
        target = node_by_id[target_id]
        key = tuple(sorted((source_id, target_id)))
        slot = pair_slots.get(key, 0)
        pair_slots[key] = slot + 1
        if source_id == target_id:
            lane = slot * 18.0
        else:
            lane = (slot - (pair_counts[key] - 1) / 2) * 18.0
            if source_id > target_id:
                lane = -lane
        path, label_x, label_y, route, edge_bounds = _canvas_edge_geometry(
            source, target, edge, lane=lane
        )
        label = str(edge.get("label", ""))
        label_width = max(42, min(260, len(label) * 8 + 20))
        label_height = 28
        edge_layouts.append(
            (
                index,
                edge,
                lane,
                path,
                label_x,
                label_y,
                route,
                edge_bounds,
                label,
                label_width,
                label_height,
            )
        )

    margin = 88
    if nodes:
        min_x = min(float(node["x"]) for node in nodes)
        min_y = min(float(node["y"]) for node in nodes)
        max_x = max(float(node["x"]) + float(node["width"]) for node in nodes)
        max_y = max(float(node["y"]) + float(node["height"]) for node in nodes)
        for layout in edge_layouts:
            edge_bounds = layout[7]
            min_x = min(min_x, edge_bounds[0])
            min_y = min(min_y, edge_bounds[1])
            max_x = max(max_x, edge_bounds[2])
            max_y = max(max_y, edge_bounds[3])
            if layout[8]:
                label_x = layout[4]
                label_y = layout[5]
                label_width = layout[9]
                label_height = layout[10]
                min_x = min(min_x, label_x - label_width / 2)
                min_y = min(min_y, label_y - label_height / 2)
                max_x = max(max_x, label_x + label_width / 2)
                max_y = max(max_y, label_y + label_height / 2)
        view_x = math.floor(min_x - margin)
        view_y = math.floor(min_y - margin)
        view_right = math.ceil(max_x + margin)
        view_bottom = math.ceil(max_y + margin)
        view_width = max(1, view_right - view_x)
        view_height = max(1, view_bottom - view_y)
    else:
        view_x = 0
        view_y = 0
        view_width = 1200
        view_height = 800

    document_title = str(document.get("title", "Schaubild"))
    rendered_document_title = _canvas_ellipsize_to_escaped_bytes(
        document_title,
        max_bytes=_CANVAS_MAX_ELEMENT_TITLE_BYTES,
    )
    document_title_truncated_attribute = (
        ' data-title-truncated="true"'
        if rendered_document_title != document_title
        else ""
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{view_x} {view_y} {view_width} {view_height}" '
            f'width="{view_width}" height="{view_height}" '
            f'data-renderer="schauwerk-native-diagram-v1" '
            f'data-intent="freeform" data-document-mode="json-canvas" '
            f'data-input-digest="{_canvas_xml(document["source_digest"])}"'
            f'{document_title_truncated_attribute}>'
        ),
        f"<title>{_canvas_xml(rendered_document_title)}</title>",
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
    canvas_node_render_order = [
        (node_index, node)
        for node_index, node in enumerate(nodes)
        if str(node["type"]) == "group"
    ] + [
        (node_index, node)
        for node_index, node in enumerate(nodes)
        if str(node["type"]) != "group"
    ]
    remaining_canvas_text_lines = _CANVAS_MAX_NODE_TEXT_LINES
    remaining_canvas_text_bytes = _CANVAS_MAX_EMITTED_TEXT_BYTES
    remaining_labeled_canvas_items = sum(
        _canvas_has_layout_content(
            _canvas_plain_markdown(str(node.get("label", "")))
            if str(node["type"]) == "text"
            else str(node.get("label", ""))
        )
        for _, node in canvas_node_render_order
    ) + sum(_canvas_has_layout_content(layout[8]) for layout in edge_layouts)

    def fair_text_byte_budget(*, has_visible_label: bool) -> int:
        if (
            not has_visible_label
            or remaining_canvas_text_bytes <= 0
            or remaining_labeled_canvas_items <= 0
        ):
            return 0
        return remaining_canvas_text_bytes // remaining_labeled_canvas_items

    def append_canvas_node(node: Mapping[str, Any], node_index: int) -> None:
        nonlocal remaining_canvas_text_lines
        nonlocal remaining_canvas_text_bytes
        nonlocal remaining_labeled_canvas_items
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
        display_label = _canvas_plain_markdown(label) if node_type == "text" else label
        has_visible_label = _canvas_has_layout_content(display_label)
        reserve_for_later = max(
            0,
            remaining_labeled_canvas_items - (1 if has_visible_label else 0),
        )
        node_line_budget = max(
            0,
            remaining_canvas_text_lines - reserve_for_later,
        )
        node_text_byte_budget = fair_text_byte_budget(
            has_visible_label=has_visible_label
        )
        inner_text_width = max(1.0, float(width - 28))
        text_layout = _canvas_text_layout(
            display_label,
            width - 28,
            height,
            max_lines=node_line_budget,
            max_bytes=node_text_byte_budget,
        )
        text_layout = _canvas_limit_text_layout_bytes(
            text_layout,
            max_width=inner_text_width,
            max_bytes=node_text_byte_budget,
        )
        remaining_canvas_text_lines = max(
            0, remaining_canvas_text_lines - len(text_layout.lines)
        )
        remaining_canvas_text_bytes = max(
            0,
            remaining_canvas_text_bytes
            - sum(_canvas_escaped_text_bytes(line) for line, _ in text_layout.lines),
        )
        if has_visible_label:
            remaining_labeled_canvas_items = max(
                0, remaining_labeled_canvas_items - 1
            )
        truncated_attribute = (
            ' data-text-truncated="true"' if text_layout.truncated else ""
        )
        lines.append(
            f'<g id="native-node-{_canvas_xml(node["id"])}" data-source-kind="node" '
            f'data-source-id="{_canvas_xml(node["id"])}" data-kind="concept" '
            f'data-canvas-type="{_canvas_xml(node_type)}"{truncated_attribute}>'
        )
        title_label = _canvas_ellipsize_to_escaped_bytes(
            display_label,
            max_bytes=_CANVAS_MAX_ELEMENT_TITLE_BYTES,
        )
        lines.append(f"<title>{_canvas_xml(title_label)}</title>")
        label_clip_id = f"canvas-node-label-{node_index}"
        lines.append(
            f'<defs><clipPath id="{label_clip_id}">'
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}"/>'
            "</clipPath></defs>"
        )
        dash = ' stroke-dasharray="8 6"' if node_type == "group" else ""
        fill_opacity = "0.28" if node_type == "group" else "1"
        lines.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
            f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{stroke}" '
            f'stroke-width="1.8"{dash}/>'
        )
        text_x = x + 14
        for line_index, (line, baseline_offset) in enumerate(text_layout.lines):
            weight = "700" if line_index == 0 or node_type == "group" else "500"
            lines.append(
                f'<text data-node-label="true" x="{text_x}" '
                f'y="{y + baseline_offset}" font-family="Inter, sans-serif" '
                f'font-size="{text_layout.size}" font-weight="{weight}" fill="#172033" '
                f'clip-path="url(#{label_clip_id})">{_canvas_xml(line)}</text>'
            )
        lines.append("</g>")

    for node_index, node in canvas_node_render_order:
        if str(node["type"]) == "group":
            append_canvas_node(node, node_index)

    for (
        index,
        edge,
        lane,
        path,
        label_x,
        label_y,
        route,
        _edge_bounds,
        label,
        label_width,
        label_height,
    ) in edge_layouts:
        _, stroke = _canvas_color(edge.get("source", {}).get("color"))
        has_visible_label = _canvas_has_layout_content(label)
        reserve_for_later = max(
            0,
            remaining_labeled_canvas_items - (1 if has_visible_label else 0),
        )
        edge_text_byte_budget = fair_text_byte_budget(
            has_visible_label=has_visible_label
        )
        edge_line_budget = max(
            0,
            remaining_canvas_text_lines - reserve_for_later,
        )
        rendered_edge_label = ""
        edge_label_truncated = False
        if has_visible_label:
            if edge_line_budget <= 0:
                edge_label_truncated = True
            else:
                rendered_edge_label, edge_label_truncated = _canvas_fit_single_line(
                    label,
                    size=14,
                    max_width=max(1.0, float(label_width - 20)),
                    max_bytes=edge_text_byte_budget,
                )
        if rendered_edge_label:
            remaining_canvas_text_lines = max(0, remaining_canvas_text_lines - 1)
            remaining_canvas_text_bytes = max(
                0,
                remaining_canvas_text_bytes
                - _canvas_escaped_text_bytes(rendered_edge_label),
            )
        if has_visible_label:
            remaining_labeled_canvas_items = max(
                0, remaining_labeled_canvas_items - 1
            )
        edge_truncated_attribute = (
            ' data-text-truncated="true"' if edge_label_truncated else ""
        )
        edge_title = _canvas_ellipsize_to_escaped_bytes(
            label,
            max_bytes=_CANVAS_MAX_ELEMENT_TITLE_BYTES,
        )
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
                    f'data-route="{route}" data-lane="{lane:.1f}"'
                    f'{edge_truncated_attribute}>'
                ),
                f"<title>{_canvas_xml(edge_title)}</title>",
                (
                    f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{marker_start}{marker_end}/>'
                ),
            ]
        )
        if has_visible_label:
            clip_id = f"canvas-edge-label-{index}"
            lines.extend(
                [
                    (
                        f'<defs><clipPath id="{clip_id}">'
                        f'<rect x="{label_x - label_width / 2:.1f}" '
                        f'y="{label_y - label_height / 2:.1f}" width="{label_width}" '
                        f'height="{label_height}"/></clipPath></defs>'
                    ),
                    (
                        f'<rect x="{label_x - label_width / 2:.1f}" '
                        f'y="{label_y - label_height / 2:.1f}" width="{label_width}" '
                        f'height="{label_height}" rx="9" fill="#f8fafc" fill-opacity="0.94"/>'
                    ),
                    (
                        f'<text x="{label_x:.1f}" y="{label_y + 5:.1f}" '
                        f'text-anchor="middle" font-family="Inter, sans-serif" '
                        f'font-size="14" font-weight="600" fill="{stroke}" '
                        f'clip-path="url(#{clip_id})">{_canvas_xml(rendered_edge_label)}</text>'
                    ),
                ]
            )
        else:
            lines.append(
                f'<rect x="{label_x:.1f}" y="{label_y:.1f}" width="0" height="0" fill="none"/>'
            )
        lines.append("</g>")

    for node_index, node in canvas_node_render_order:
        if str(node["type"]) != "group":
            append_canvas_node(node, node_index)

    lines.append("</svg>")
    return "\n".join(lines) + "\n"
