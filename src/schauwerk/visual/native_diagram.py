"""Small deterministic SVG renderer for Schauwerk representation input."""

from __future__ import annotations

import io
import math
import re
import textwrap
import unicodedata
from bisect import bisect_right
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
_CANVAS_PRIVATE_USE_WIDTH_UNITS = 1.40
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
    local_group_branch_gutter_x: Mapping[str, float] | None = None,
) -> list[str]:
    """Ids of the process relations that leave through the long-branch gutter."""
    row_step = _NODE_HEIGHT + process_row_gap
    long_branches: list[str] = []
    for edge in model["edges"]:
        edge_id = str(edge["id"])
        if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
            continue
        if local_group_branch_gutter_x and edge_id in local_group_branch_gutter_x:
            continue
        source = positions[str(edge["from"])]
        target = positions[str(edge["to"])]
        if (
            source[0] != target[0]
            and source[1] != target[1]
            and abs(target[1] - source[1]) > row_step
        ):
            long_branches.append(edge_id)
    return sorted(long_branches)


def _process_local_group_branch_gutter_x(
    model: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    regions: Sequence[tuple[str | None, str, int, int, int, int]],
    *,
    process_row_gap: int,
) -> dict[str, float]:
    """Return safe local channels between adjacent process groups.

    Ordinary forward relations may reuse the card-free horizontal gap between
    consecutive process groups instead of the global outer gutter. Risk
    branches retain the established outer-gutter semantics. Multiple local
    long branches receive distinct deterministic lanes when the card gap can
    hold them; otherwise the ordinary global long-branch fallback remains.
    """
    if not model["groups"] or not regions:
        return {}

    group_order = {
        str(group["id"]): index for index, group in enumerate(model["groups"])
    }
    node_group = {str(node["id"]): node["group"] for node in model["nodes"]}
    group_nodes: dict[str, list[str]] = defaultdict(list)
    for node_id, group_id in node_group.items():
        if group_id is not None:
            group_nodes[str(group_id)].append(node_id)
    region_ids = {str(group_id) for group_id, *_ in regions if group_id is not None}
    row_step = _NODE_HEIGHT + process_row_gap
    candidates: dict[tuple[str, str], list[str]] = defaultdict(list)

    for edge in model["edges"]:
        if str(edge["kind"]) in {"feedback", "risk"} or edge["from"] == edge["to"]:
            continue
        source_id = str(edge["from"])
        target_id = str(edge["to"])
        source_group = node_group[source_id]
        target_group = node_group[target_id]
        if source_group is None or target_group is None or source_group == target_group:
            continue
        source_group_id = str(source_group)
        target_group_id = str(target_group)
        source_group_index = group_order.get(source_group_id)
        target_group_index = group_order.get(target_group_id)
        if (
            source_group_index is None
            or target_group_index != source_group_index + 1
            or source_group_id not in region_ids
            or target_group_id not in region_ids
        ):
            continue

        source = positions[source_id]
        target = positions[target_id]
        if (
            source[0] >= target[0]
            or source[1] == target[1]
            or abs(target[1] - source[1]) <= row_step
        ):
            continue
        candidates[(source_group_id, target_group_id)].append(str(edge["id"]))

    gutters: dict[str, float] = {}
    edges_by_id = {str(edge["id"]): edge for edge in model["edges"]}
    lane_ranks = _stable_lane_ranks(model)
    clearance = 8.0
    for (source_group_id, target_group_id), edge_ids in sorted(candidates.items()):
        source_right = max(
            positions[node_id][0] + _NODE_WIDTH for node_id in group_nodes[source_group_id]
        )
        target_left = min(
            positions[node_id][0] for node_id in group_nodes[target_group_id]
        )
        usable_left = source_right + clearance
        usable_right = target_left - clearance
        ordered_ids = sorted(edge_ids)
        # A later label pack can demote one of two parallel long routes into
        # an outer gutter. Its source leg would cross the retained local label.
        # Route the entire parallel set through the existing outer fallback.
        endpoints = [
            (str(edges_by_id[edge_id]["from"]), str(edges_by_id[edge_id]["to"]))
            for edge_id in ordered_ids
        ]
        if len(set(endpoints)) != len(endpoints):
            continue
        required_span = (len(ordered_ids) - 1) * _PROCESS_LANE_STEP
        if usable_right < usable_left or required_span > usable_right - usable_left:
            continue

        center_x = (source_right + target_left) / 2
        proposed: dict[str, float] = {}
        for slot, edge_id in enumerate(ordered_ids):
            centered_slot = slot - (len(ordered_ids) - 1) / 2
            proposed[edge_id] = center_x + centered_slot * _PROCESS_LANE_STEP
        # Clear the actual source-gap label of shorter nested returns
        # sharing a target before accepting the existing local gutter.
        nested_labels: list[tuple[float, float, float, float, str]] = []
        for edge_id in sorted(
            ordered_ids,
            key=lambda edge_id: (
                str(edges_by_id[edge_id]["to"]),
                abs(
                    positions[str(edges_by_id[edge_id]["from"])][1]
                    - positions[str(edges_by_id[edge_id]["to"])][1]
                ),
                edge_id,
            ),
        ):
            edge = edges_by_id[edge_id]
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            direction = 1 if source[1] < target[1] else -1
            offset = max(
                -8.0, min(
                    8.0, ((lane_ranks[edge_id] % 5) - 2) * _PROCESS_LANE_STEP / 2
                ),
            )
            start_y = source[1] + (_NODE_HEIGHT if direction > 0 else 0)
            end_y = target[1] + (0 if direction > 0 else _NODE_HEIGHT)
            source_y = start_y + direction * process_row_gap / 2 + offset
            target_y = end_y - direction * process_row_gap / 2 + offset
            for left, top, right, bottom, peer_target in sorted(nested_labels):
                if (
                    peer_target == str(edge["to"])
                    and top < max(source_y, target_y)
                    and bottom > min(source_y, target_y)
                    and left - 2 < proposed[edge_id] < right + 2
                ):
                    proposed[edge_id] = right + 4
            metrics = _edge_label_metrics(edge, positions, "process")
            nested_labels.append((
                proposed[edge_id] - metrics.width / 2,
                source_y - metrics.height / 2,
                proposed[edge_id] + metrics.width / 2,
                source_y + metrics.height / 2,
                str(edge["to"]),
            ))
        remaining_outer = _process_long_branch_ids(
            model,
            positions,
            process_row_gap=process_row_gap,
            local_group_branch_gutter_x={**gutters, **proposed},
        )
        # The global gutter lies to the right of all cards, so every outer
        # branch traverses the source/target corridor on its way there.
        outer_reach = max(x + _NODE_WIDTH for x, _ in positions.values())

        def label_overlaps_node_or_outer_leg(edge_id: str) -> bool:
            edge = edges_by_id[edge_id]
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            metrics = _edge_label_metrics(edge, positions, "process")
            lane = ((lane_ranks[edge_id] % 5) - 2) * _PROCESS_LANE_STEP
            lane_offset = max(-8.0, min(8.0, lane / 2))
            if source[1] < target[1]:
                label_y = (
                    source[1]
                    + _NODE_HEIGHT
                    + process_row_gap / 2
                    + lane_offset
                )
            else:
                label_y = source[1] - process_row_gap / 2 + lane_offset
            label_left = proposed[edge_id] - metrics.width / 2
            label_right = proposed[edge_id] + metrics.width / 2
            label_top = label_y - metrics.height / 2
            label_bottom = label_y + metrics.height / 2
            if any(
                label_left < node_x + _NODE_WIDTH
                and label_right > node_x
                and label_top < node_y + _NODE_HEIGHT
                and label_bottom > node_y
                for node_x, node_y in positions.values()
            ):
                return True

            # A shifted local gutter may not enter a foreign card column
            # within the full source-to-target vertical return span.
            direction = 1 if source[1] < target[1] else -1
            source_leg_y = source[1] + (_NODE_HEIGHT if direction > 0 else 0)
            source_leg_y += direction * process_row_gap / 2 + lane_offset
            target_leg_y = target[1] + (0 if direction > 0 else _NODE_HEIGHT)
            target_leg_y -= direction * process_row_gap / 2 - lane_offset
            if (
                proposed[edge_id] > outer_reach
                or any(
                    node_x - 2 < proposed[edge_id] < node_x + _NODE_WIDTH + 2
                    and node_y - 2 < max(source_leg_y, target_leg_y)
                    and node_y + _NODE_HEIGHT + 2 > min(source_leg_y, target_leg_y)
                    for node_x, node_y in positions.values()
                )
            ):
                return True

            # An adjacent relation in either direction may share an endpoint
            # and a row-gap with a local long branch. Forward peers anchor
            # labels over their upper source card, whereas reverse peers use
            # the inter-column center; both can mask a real horizontal leg.
            local_gutter_x = proposed[edge_id]
            if source[1] < target[1]:
                local_source_y = (
                    source[1] + _NODE_HEIGHT + process_row_gap / 2
                )
                local_target_y = target[1] - process_row_gap / 2
            else:
                local_source_y = source[1] - process_row_gap / 2
                local_target_y = (
                    target[1] + _NODE_HEIGHT + process_row_gap / 2
                )
            for other_id, other in edges_by_id.items():
                if (
                    other_id == edge_id
                    or str(other["kind"]) == "feedback"
                    or not (
                        str(other["from"]) in {str(edge["from"]), str(edge["to"])}
                        or str(other["to"]) in {str(edge["from"]), str(edge["to"])}
                    )
                ):
                    continue
                peer_source = positions[str(other["from"])]
                peer_target = positions[str(other["to"])]
                if (
                    peer_source[1] == peer_target[1]
                    or abs(peer_source[1] - peer_target[1]) > row_step
                ):
                    continue
                peer_gap_top = (
                    min(peer_source[1], peer_target[1]) + _NODE_HEIGHT
                )
                peer_gap_bottom = max(peer_source[1], peer_target[1])
                if peer_gap_top >= peer_gap_bottom:
                    continue
                peer_metrics = _edge_label_metrics(other, positions, "process")
                if (
                    peer_source[0] < peer_target[0]
                    and peer_metrics.height + 8
                    <= peer_gap_bottom - peer_gap_top
                ):
                    # This forward relation leaves a narrow, real free row
                    # lane; keep the local branch and select that lane after
                    # all label positions are packed, not an outer detour.
                    continue
                peer_x = (
                    peer_source[0] + _NODE_WIDTH / 2
                    if peer_source[0] < peer_target[0]
                    else (peer_source[0] + peer_target[0] + _NODE_WIDTH) / 2
                )
                peer_y = (peer_gap_top + peer_gap_bottom) / 2
                left = peer_x - peer_metrics.width / 2 - 2
                right = peer_x + peer_metrics.width / 2 + 2
                top = peer_y - peer_metrics.height / 2 - 2
                bottom = peer_y + peer_metrics.height / 2 + 2
                if (
                    left < local_gutter_x < right
                    and top < max(local_source_y, local_target_y)
                    and bottom > min(local_source_y, local_target_y)
                ):
                    return True
                for end_x, leg_y in (
                    (source[0] + _NODE_WIDTH / 2, local_source_y),
                    (target[0] + _NODE_WIDTH / 2, local_target_y),
                ):
                    if (
                        top < leg_y < bottom
                        and left < max(end_x, local_gutter_x)
                        and right > min(end_x, local_gutter_x)
                    ):
                        return True

            # Short adjacent-row paths can later be routed into the outer
            # gutter, but their full horizontal legs still cross this gap.
            # Avoid anchoring a long-branch label underneath those legs.
            for other_id, other in edges_by_id.items():
                if other_id == edge_id or str(other["kind"]) == "feedback":
                    continue
                other_source = positions[str(other["from"])]
                other_target = positions[str(other["to"])]
                # The reproduced hazard is the reverse adjacent branch whose
                # outer return crosses the local anchor. Keep ordinary forward
                # process links local; otherwise normal 18-node diagrams widen.
                if other_source[0] <= other_target[0]:
                    continue
                if (
                    other_source[1] == other_target[1]
                    or abs(other_target[1] - other_source[1]) > row_step
                ):
                    continue
                gap_top = min(other_source[1], other_target[1]) + _NODE_HEIGHT
                gap_bottom = max(other_source[1], other_target[1])
                if gap_bottom <= gap_top:
                    continue
                center_y = (gap_top + gap_bottom) / 2
                left_x = min(other_source[0], other_target[0]) + _NODE_WIDTH / 2
                right_x = max(other_source[0], other_target[0]) + _NODE_WIDTH / 2
                if (
                    label_left < right_x
                    and label_right > left_x
                    and label_top < center_y + 8
                    and label_bottom > center_y - 8
                ):
                    return True

            # The existing outer fallback is safer when its long-branch
            # horizontal source/target leg would cross this proposed label.
            # Account for its bounded lane offset before accepting a local
            # route; otherwise the later outer-lane allocator masks the label.
            for other_id in remaining_outer:
                other = edges_by_id[other_id]
                outer_source = positions[str(other["from"])]
                outer_target = positions[str(other["to"])]
                if outer_source[1] < outer_target[1]:
                    source_y = outer_source[1] + _NODE_HEIGHT + process_row_gap / 2
                    target_y = outer_target[1] - process_row_gap / 2
                else:
                    source_y = outer_source[1] - process_row_gap / 2
                    target_y = outer_target[1] + _NODE_HEIGHT + process_row_gap / 2
                for endpoint_x, corridor_y in (
                    (outer_source[0] + _NODE_WIDTH / 2, source_y),
                    (outer_target[0] + _NODE_WIDTH / 2, target_y),
                ):
                    if (
                        label_left < outer_reach
                        and label_right > endpoint_x
                        and label_top < corridor_y + 8
                        and label_bottom > corridor_y - 8
                    ):
                        return True
            return False

        if any(label_overlaps_node_or_outer_leg(edge_id) for edge_id in ordered_ids):
            continue
        gutters.update(proposed)

    return gutters


def _process_anchored_corridor_labels(
    model: Mapping[str, Any],
    positions: Mapping[str, tuple[int, int]],
    *,
    process_row_gap: int,
    long_vertical_gutter_x: Mapping[str, float],
    local_group_branch_gutter_x: Mapping[str, float],
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
        model,
        positions,
        process_row_gap=process_row_gap,
        local_group_branch_gutter_x=local_group_branch_gutter_x,
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
        local_branch_gutter_x = local_group_branch_gutter_x.get(edge_id)
        if self_loop:
            corridor = _process_label_corridor_above(
                source[1], positions, header_corridor=header_corridor
            )
        elif local_branch_gutter_x is not None:
            long_branch_gutter_x = local_branch_gutter_x
            corridor = _process_row_corridor_bounds(
                source[1], positions, direction=1 if source[1] < target[1] else -1
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
        if local_branch_gutter_x is not None:
            # A grouped local long branch owns the vertical channel between the
            # two group regions. Anchor its label on that channel, not midway
            # back toward the source card; this leaves the same row corridor
            # available to short cross-group relations.
            natural_x = local_branch_gutter_x
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



def _process_feedback_parallel_port_y_offset(slot: int) -> float:
    """Stable, non-repeating card-side port offsets within the node height."""
    if slot <= 0:
        return 0.0
    ordinal = (slot + 1) // 2
    maximum = _NODE_HEIGHT / 2 - 9
    magnitude = maximum * (1 - (1 - 7 / maximum) ** ordinal)
    return magnitude if slot % 2 else -magnitude


def _safe_process_feedback_outer_ports(
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    canvas_width: int,
    canvas_height: int,
    label_width: int,
    obstacles: Sequence[tuple[float, float, float, float]],
    parallel_route_slot: int = 0,
    label_only_obstacles: Sequence[tuple[float, float, float, float]] = (),
    reserved_verticals: Sequence[tuple[float, float, float]] = (),
    label_y: float | None = None,
    label_height: float = 0.0,
) -> tuple[float, float, float, float, float] | None:
    """Choose side-port gutters against the entire return-to-footer geometry.

    Each endpoint gets a short horizontal exit and an independent vertical
    gutter. Only the footer, below the other cards and relation labels,
    connects their gutters. All candidates are deterministic and bounded by
    actual existing canvas space; a blocked local gutter is never reused as a
    nominally safe outer fallback.
    """
    clearance = 3.5
    port_y_offset = _process_feedback_parallel_port_y_offset(parallel_route_slot)
    # Each semantic peer gets a dedicated horizontal return lane. A distinct
    # gutter x alone can still leave overlapping horizontal footer strokes.
    footer_y = float(canvas_height) - 28.0 - 12.0 * parallel_route_slot
    max_x = float(canvas_width) - 16.0

    def segment_clear(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        skip: tuple[float, float, float, float] | None = None,
    ) -> bool:
        for left, top, right, bottom in obstacles:
            if skip is not None and (left, top, right, bottom) == skip:
                continue
            if x1 == x2:
                if (
                    left - clearance < x1 < right + clearance
                    and max(min(y1, y2), top - clearance)
                    < min(max(y1, y2), bottom + clearance)
                ):
                    return False
            elif y1 == y2:
                if (
                    top - clearance < y1 < bottom + clearance
                    and max(min(x1, x2), left - clearance)
                    < min(max(x1, x2), right + clearance)
                ):
                    return False
        return True

    def channel(
        node: tuple[int, int],
        preferred_side: int,
    ) -> list[tuple[float, int, float, float]]:
        x, y = node
        middle_y = y + _NODE_HEIGHT / 2 + port_y_offset
        own = (float(x), float(y), float(x + _NODE_WIDTH), float(y + _NODE_HEIGHT))
        candidates: list[tuple[float, int, float, float]] = []
        for side_index, side in enumerate((preferred_side, -preferred_side)):
            port = float(x + _NODE_WIDTH if side > 0 else x)
            # Two semantic feedback relations sharing both endpoints need
            # separate visible stems, even when their labels occupy different
            # footer lanes. Only later deterministic peers take an offset;
            # the first edge preserves its accepted geometry byte-for-byte.
            preferred = port + side * (
                _CORRIDOR_GUTTER_OFFSET + 12 * parallel_route_slot
            )
            xs = {preferred, 16.0, max_x}
            # A peer gutter cannot be reserved merely by shifting the
            # preferred x: blocked peers can select the same obstacle edge.
            # Try explicit, bounded alternative x positions around the port.
            for step in range(1, min(32, 2 * len(reserved_verticals)) + 1):
                xs.update((preferred + 8 * step, preferred - 8 * step))
            for left, top, right, bottom in obstacles:
                if top - clearance < footer_y and bottom + clearance > middle_y:
                    xs.update((left - clearance, right + clearance))
            for gutter in sorted(xs):
                if not 16.0 <= gutter <= max_x:
                    continue
                if side * (gutter - port) < clearance:
                    continue
                if not segment_clear(port, middle_y, gutter, middle_y, skip=own):
                    continue
                if not segment_clear(gutter, middle_y, gutter, footer_y):
                    continue
                if any(
                    abs(gutter - prior_x) < 7.0
                    and max(min(middle_y, footer_y), prior_top)
                    < min(max(middle_y, footer_y), prior_bottom)
                    for prior_x, prior_top, prior_bottom in reserved_verticals
                ):
                    continue
                score = abs(gutter - preferred) + 24 * side_index
                candidates.append((score, side_index, gutter, port))
        return sorted(candidates)

    start_side = 1 if source[0] <= target[0] else -1
    end_side = -start_side if source[0] != target[0] else 1
    starts = channel(source, start_side)
    ends = channel(target, end_side)
    if not starts or not ends:
        return None

    # Candidate stems must be chosen *together*: individually optimal
    # gutters can leave an obstructed footer, even though another valid
    # pair of independently clear channels exists.
    for _, _, start_gutter, start_port in starts:
        for _, _, end_gutter, end_port in ends:
            if abs(start_gutter - end_gutter) < 7:
                continue
            if not segment_clear(start_gutter, footer_y, end_gutter, footer_y):
                continue
            left, right = sorted((start_gutter, end_gutter))
            preferred_label_x = (left + right) / 2
            # Later feedback labels must not be put across the stems of
            # previously allocated peers: those stems are already fixed.
            half = label_width / 2
            choices = {
                preferred_label_x,
                right + half + 12,
                left - half - 12,
                half + 8,
                canvas_width - half - 8,
            }
            if label_y is not None:
                label_top = label_y - label_height / 2
                label_bottom = label_y + label_height / 2
                for prior_x, prior_top, prior_bottom in reserved_verticals:
                    if max(label_top, prior_top) < min(label_bottom, prior_bottom):
                        choices.update((prior_x - half - 8, prior_x + half + 8))
                for box_left, box_top, box_right, box_bottom in (*obstacles, *label_only_obstacles):
                    if max(label_top, box_top) < min(label_bottom, box_bottom):
                        choices.update((
                            box_left - half - 8, box_right + half + 8
                        ))
            legal_label_x = [
                value for value in choices
                if value - half >= 8
                and value + half <= canvas_width - 8
                and abs(value - start_gutter) >= half + 8
                and abs(value - end_gutter) >= half + 8
                and (
                    label_y is None
                    or all(
                        abs(value - prior_x) >= half + 7
                        or max(label_top, prior_top)
                        >= min(label_bottom, prior_bottom)
                        for prior_x, prior_top, prior_bottom in reserved_verticals
                    )
                )
                and (
                    label_y is None
                    or all(
                        not (
                            box_left - clearance < value + half
                            and box_right + clearance > value - half
                            and box_top - clearance < label_bottom
                            and box_bottom + clearance > label_top
                        )
                        for box_left, box_top, box_right, box_bottom in (
                            *obstacles, *label_only_obstacles
                        )
                    )
                )
            ]
            if legal_label_x:
                label_x = min(
                    legal_label_x,
                    key=lambda value: (abs(value - preferred_label_x), value),
                )
                return (
                    start_port, start_gutter, end_gutter, end_port, label_x
                )
    return None



def _process_svg_path_hits_box(
    path: str,
    box: tuple[float, float, float, float],
    *,
    padding: float = 1.5,
) -> bool:
    """Check the rendered M/L/C strokes against a label or process card."""
    left, top, width, height = box
    expanded = (
        left - padding, top - padding,
        width + 2 * padding, height + 2 * padding,
    )
    commands = re.findall(r"[MLC]|-?\d+(?:\.\d+)?", path)
    cursor: tuple[float, float] | None = None
    index = 0
    while index < len(commands):
        command = commands[index]
        index += 1
        arity = 6 if command == "C" else 2
        if command not in {"M", "L", "C"} or index + arity > len(commands):
            return True  # Unknown SVG geometry must never be treated as clear.
        values = tuple(float(value) for value in commands[index:index + arity])
        index += arity
        endpoint = (values[-2], values[-1])
        if cursor is not None:
            if command == "C":
                curve = (cursor, (values[0], values[1]), (values[2], values[3]), endpoint)
            elif command == "L":
                curve = (cursor, cursor, endpoint, endpoint)
            else:
                curve = None
            if curve is not None and _cubic_hull_intersects_box(curve, expanded):
                return True
        cursor = endpoint
    return False

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
    long_branch_route_count: int | None = None,
    long_branch_label_y: float | None = None,
    anchored_branch_gutter_x: float | None = None,
    long_vertical_gutter_x: float | None = None,
    long_vertical_label_y: float | None = None,
    process_branch_gutter_x: float | None = None,
    process_adjacent_route_y: float | tuple[float, float] | None = None,
    process_same_row_target_port_x: float | None = None,
    process_same_row_source_port_x: float | None = None,
    narrative_parallel_gutter_x: float | None = None,
    narrative_self_loop_gutter_x: float | None = None,
    generic_self_loop_gutter_x: float | None = None,
    label_height: int = 0,
    label_width: int = 0,
    feedback_label_y: float | None = None,
    max_node_bottom: float = 0.0,
    preserve_same_row_feedback_footer: bool = True,
    feedback_path_y: float | tuple[float, float] | None = None,
    feedback_path_footer: bool = False,
    feedback_local_gutter_x: float | None = None,
    feedback_outer_footer: bool = False,
    feedback_outer_parallel_slot: int = 0,
    feedback_outer_preplanned_ports: tuple[float, float, float, float, float] | None = None,
    feedback_outer_obstacles: Sequence[tuple[float, float, float, float]] = (),
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
        if feedback_outer_footer:
            planned_footer_label_x: float | None = None
            if feedback_outer_preplanned_ports is not None:
                # Never silently recalculate without the previously reserved
                # vertical lanes. The fixed-point plan owns the rendered SVG.
                safe_ports = feedback_outer_preplanned_ports
            elif feedback_outer_obstacles:
                safe_ports = _safe_process_feedback_outer_ports(
                    source, target,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    label_width=label_width,
                    obstacles=feedback_outer_obstacles,
                    parallel_route_slot=feedback_outer_parallel_slot,
                )
            else:
                safe_ports = None
            if feedback_outer_obstacles and safe_ports is None:
                raise ValueError("no collision-free process feedback side-port route")
            if safe_ports is not None:
                (
                    planned_start_x, planned_start_gutter,
                    planned_end_gutter, planned_end_x, planned_footer_label_x,
                ) = safe_ports
            # A genuinely saturated row gap has no safe source/target
            # horizontal leg. Leave the cards through their side ports and
            # meet at a dedicated footer below every card and packed label.
            # Adjacent group gutters are intentionally selected on the facing
            # sides of the two endpoints, never through a foreign card column.
            if planned_footer_label_x is not None:
                start_x, start_gutter = planned_start_x, planned_start_gutter
                end_gutter, end_x = planned_end_gutter, planned_end_x
            elif source_x > target_x:
                start_x, end_x = source_x, target_x + node_width
                start_gutter = source_x - _CORRIDOR_GUTTER_OFFSET
                end_gutter = target_x + node_width + _CORRIDOR_GUTTER_OFFSET
            elif source_x < target_x:
                start_x, end_x = source_x + node_width, target_x
                start_gutter = source_x + node_width + _CORRIDOR_GUTTER_OFFSET
                end_gutter = target_x - _CORRIDOR_GUTTER_OFFSET
            else:
                start_x = end_x = source_x + node_width
                start_gutter = end_gutter = (
                    source_x + node_width + _CORRIDOR_GUTTER_OFFSET
                )
            port_y_offset = _process_feedback_parallel_port_y_offset(
                feedback_outer_parallel_slot
            )
            start_y, end_y = (
                source_y + _NODE_HEIGHT / 2 + port_y_offset,
                target_y + _NODE_HEIGHT / 2 + port_y_offset,
            )
            footer_y = (
                canvas_height - 28.0 - 12.0 * feedback_outer_parallel_slot
            )
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"L {start_gutter:.1f} {start_y:.1f} "
                f"L {start_gutter:.1f} {footer_y:.1f} "
                f"L {end_gutter:.1f} {footer_y:.1f} "
                f"L {end_gutter:.1f} {end_y:.1f} "
                f"L {end_x:.1f} {end_y:.1f}"
            )
            return (
                path,
                (
                    planned_footer_label_x
                    if planned_footer_label_x is not None
                    else (start_gutter + end_gutter) / 2
                ),
                feedback_label_y if feedback_label_y is not None
                else footer_y - 45.0, route,
            )
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
        # use one local lane immediately to the right of the actual endpoint span,
        # and re-enter through the target row gap. The process layout reserves
        # enough inter-column whitespace for this lane, so unrelated later nodes
        # never force a feedback relation out to the global canvas edge.
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
        # The text retains its accepted row-gap slot even when path legs
        # choose different safe heights closer to a card boundary.
        label_corridor_y = source_corridor_y
        if isinstance(feedback_path_y, tuple):
            # The ungrouped return can have a different free lane on each
            # endpoint; neither horizontal leg may mask a corridor label.
            source_corridor_y, target_corridor_y = feedback_path_y
        elif feedback_path_y is not None and source_y == target_y:
            source_corridor_y = target_corridor_y = feedback_path_y
        # A safe horizontal lane can sit close to the card. Fixed-size
        # cubic bends must not overshoot that lane back through an occupied
        # label rectangle; keep each control inside its physical stub span.
        start_control_y = min(
            max(start_y + start_bend, min(start_y, source_corridor_y)),
            max(start_y, source_corridor_y),
        )
        end_control_y = min(
            max(end_y + end_bend, min(end_y, target_corridor_y)),
            max(end_y, target_corridor_y),
        )
        gutter_x = (
            feedback_local_gutter_x
            if feedback_local_gutter_x is not None
            else min(
                canvas_width - 16.0,
                max(source_x, target_x) + node_width + _CORRIDOR_GUTTER_OFFSET,
            )
        )
        if (
            feedback_label_y is not None
            and feedback_path_footer
            and source_y == target_y
            and source_x > target_x
        ):
            target_channel_x = max(
                16.0, target_x - _CORRIDOR_GUTTER_OFFSET
            )
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_control_y:.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {feedback_label_y:.1f} "
                f"L {target_channel_x:.1f} {feedback_label_y:.1f} "
                f"L {target_channel_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_control_y:.1f}, {end_x:.1f} {end_y:.1f}"
            )
            return path, gutter_x, feedback_label_y, route
        # A moved footer label is independent of the local return geometry.
        # Extending the line down to that label and back masks the next
        # semantic footer label without adding a useful connection.
        path = (
            f"M {start_x:.1f} {start_y:.1f} "
            f"C {start_x:.1f} {start_control_y:.1f}, "
            f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
            f"L {gutter_x:.1f} {source_corridor_y:.1f} "
            f"L {gutter_x:.1f} {target_corridor_y:.1f} "
            f"L {end_x:.1f} {target_corridor_y:.1f} "
            f"C {end_x:.1f} {target_corridor_y:.1f}, "
            f"{end_x:.1f} {end_control_y:.1f}, {end_x:.1f} {end_y:.1f}"
        )
        if feedback_label_y is not None:
            return path, gutter_x, feedback_label_y, route
        label_x = (
            (gutter_x + end_x) / 2
            if source_y == target_y and source_x > target_x
            else (start_x + gutter_x) / 2
        )
        return path, label_x, label_corridor_y, route
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
        end_x = (
            process_same_row_target_port_x
            if process_same_row_target_port_x is not None
            else target_x + node_width / 2
        )
        start_y = end_y = source_y
        corridor_y = (
            process_adjacent_route_y[0]
            if isinstance(process_adjacent_route_y, tuple)
            else source_y - process_row_gap / 2
        )
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
            label_corridor_y = (start_y + end_y) / 2
            gutter_x = process_branch_gutter_x
            if isinstance(process_adjacent_route_y, tuple):
                source_corridor_y, target_corridor_y = process_adjacent_route_y
                path = (
                    f"M {center_x:.1f} {start_y:.1f} "
                    f"L {center_x:.1f} {source_corridor_y:.1f} "
                    f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                    f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                    f"L {center_x:.1f} {target_corridor_y:.1f} "
                    f"L {center_x:.1f} {end_y:.1f}"
                )
            else:
                corridor_y = (
                    process_adjacent_route_y
                    if process_adjacent_route_y is not None else label_corridor_y
                )
                path = (
                    f"M {center_x:.1f} {start_y:.1f} "
                    f"L {center_x:.1f} {corridor_y:.1f} "
                    f"L {gutter_x:.1f} {corridor_y:.1f} "
                    f"L {center_x:.1f} {corridor_y:.1f} "
                    f"L {center_x:.1f} {end_y:.1f}"
                )
            return path, gutter_x + 8 + label_width / 2, label_corridor_y, "process-row-gutter"
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
        target_center_x = (
            process_same_row_target_port_x
            if process_same_row_target_port_x is not None and source_y < target_y
            else target_x + node_width / 2
        )
        row_step = _NODE_HEIGHT + process_row_gap
        spans_intervening_row = abs(target_y - source_y) > row_step
        if spans_intervening_row and long_branch_slot is not None:
            stable_count = max(1, (
                long_branch_route_count
                if long_branch_route_count is not None else long_branch_count
            ))
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
        # The label retains its established centered row-gap position; only
        # the long branch's physical source leg may move around a peer label.
        source_label_corridor_y = source_corridor_y
        if process_adjacent_route_y is not None:
            if isinstance(process_adjacent_route_y, tuple):
                source_corridor_y, target_corridor_y = process_adjacent_route_y
            else:
                source_corridor_y = process_adjacent_route_y
        # Actual safe lanes may sit closer than the standard bend to a card.
        # Monotone endpoint curves may not overshoot that lane into a label.
        bend = 18.0
        direction_bend = bend if source_y < target_y else -bend
        start_control_y = min(
            max(start_y + direction_bend, min(start_y, source_corridor_y)),
            max(start_y, source_corridor_y),
        )
        end_control_y = min(
            max(end_y - direction_bend, min(end_y, target_corridor_y)),
            max(end_y, target_corridor_y),
        )
        if process_branch_gutter_x is not None:
            gutter_x = process_branch_gutter_x
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_control_y:.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_control_y:.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
            return (
                path,
                gutter_x + 8 + label_width / 2,
                (source_label_corridor_y + target_corridor_y) / 2,
                route,
            )
        if (
            spans_intervening_row
            and long_branch_slot is None
            and anchored_branch_gutter_x is not None
        ):
            gutter_x = anchored_branch_gutter_x
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_control_y:.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_control_y:.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
            return path, gutter_x, source_label_corridor_y, route
        if spans_intervening_row:
            slot = long_branch_slot or 0
            count = max(1, long_branch_count)
            route_count = max(1, (
                long_branch_route_count
                if long_branch_route_count is not None else long_branch_count
            ))
            if route_count == 1:
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
            path = (
                f"M {start_x:.1f} {start_y:.1f} "
                f"C {start_x:.1f} {start_control_y:.1f}, "
                f"{start_x:.1f} {source_corridor_y:.1f}, {start_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {source_corridor_y:.1f} "
                f"L {gutter_x:.1f} {target_corridor_y:.1f} "
                f"L {end_x:.1f} {target_corridor_y:.1f} "
                f"C {end_x:.1f} {target_corridor_y:.1f}, "
                f"{end_x:.1f} {end_control_y:.1f}, "
                f"{end_x:.1f} {end_y:.1f}"
            )
            if count == 1:
                label_x = (start_x + gutter_x) / 2
                label_y = source_label_corridor_y
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
        corridor_y = (
            process_adjacent_route_y
            if process_adjacent_route_y is not None
            else (start_y + end_y) / 2 + lane_offset
        )
        control_one = (start_x, corridor_y)
        control_two = (end_x, corridor_y)
    elif (
        intent == "process"
        and not self_loop
        and source_y == target_y
        and isinstance(process_adjacent_route_y, (int, float))
        and process_branch_gutter_x is None
        and any(
            min(source_x, target_x) + node_width <= x
            and x + node_width <= max(source_x, target_x)
            and y < source_y + _NODE_HEIGHT
            and y + _NODE_HEIGHT > source_y
            for x, y in obstacle_positions
        )
    ):
        route = "process-row-card-detour"
        start_x = (
            process_same_row_source_port_x
            if process_same_row_source_port_x is not None
            else source_x + node_width / 2
        )
        end_x = (
            process_same_row_target_port_x
            if process_same_row_target_port_x is not None
            else target_x + node_width / 2
        )
        port_y = (
            source_y if process_adjacent_route_y < source_y
            else source_y + _NODE_HEIGHT
        )
        channel_y = process_adjacent_route_y
        path = (
            f"M {start_x:.1f} {port_y:.1f} "
            f"L {start_x:.1f} {channel_y:.1f} "
            f"L {end_x:.1f} {channel_y:.1f} "
            f"L {end_x:.1f} {port_y:.1f}"
        )
        return path, (start_x + end_x) / 2, channel_y, route
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
    long_branch_route_count: int | None = None,
    long_branch_label_y: float | None = None,
    anchored_branch_gutter_x: float | None = None,
    long_vertical_gutter_x: float | None = None,
    long_vertical_label_y: float | None = None,
    long_vertical_label_x: float | None = None,
    process_branch_gutter_x: float | None = None,
    process_adjacent_slot: int | None = None,
    process_adjacent_count: int = 0,
    process_adjacent_label_x: float | None = None,
    process_adjacent_label_y: float | None = None,
    process_adjacent_route_y: float | tuple[float, float] | None = None,
    process_same_row_target_port_x: float | None = None,
    process_same_row_source_port_x: float | None = None,
    row_corridor_label_x: float | None = None,
    narrative_parallel_gutter_x: float | None = None,
    narrative_self_loop_gutter_x: float | None = None,
    generic_self_loop_gutter_x: float | None = None,
    self_loop_lane: int | None = None,
    feedback_slot: int | None = None,
    feedback_count: int = 0,
    feedback_base_bottom: float | None = None,
    force_feedback_footer: bool = False,
    feedback_footer_label_x_override: float | None = None,
    feedback_path_y: float | tuple[float, float] | None = None,
    force_feedback_path_footer: bool = False,
    feedback_local_gutter_x: float | None = None,
    feedback_outer_footer: bool = False,
    feedback_outer_parallel_slot: int = 0,
    feedback_outer_preplanned_ports: tuple[float, float, float, float, float] | None = None,
    feedback_outer_obstacles: Sequence[tuple[float, float, float, float]] = (),
    final_label_override: tuple[float, float] | None = None,
    process_row_card_side_path: str | None = None,
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
        long_branch_route_count=long_branch_route_count,
        long_branch_label_y=long_branch_label_y,
        anchored_branch_gutter_x=anchored_branch_gutter_x,
        long_vertical_gutter_x=long_vertical_gutter_x,
        long_vertical_label_y=long_vertical_label_y,
        process_branch_gutter_x=process_branch_gutter_x,
        process_adjacent_route_y=process_adjacent_route_y,
        process_same_row_target_port_x=process_same_row_target_port_x,
        process_same_row_source_port_x=process_same_row_source_port_x,
        narrative_parallel_gutter_x=narrative_parallel_gutter_x,
        narrative_self_loop_gutter_x=narrative_self_loop_gutter_x,
        generic_self_loop_gutter_x=generic_self_loop_gutter_x,
        label_height=label_height,
        label_width=label_width,
        feedback_label_y=feedback_label_y,
        max_node_bottom=max_node_bottom,
        preserve_same_row_feedback_footer=preserve_same_row_feedback_footer,
        feedback_path_y=feedback_path_y,
        feedback_path_footer=force_feedback_path_footer,
        feedback_local_gutter_x=feedback_local_gutter_x,
        feedback_outer_footer=feedback_outer_footer,
        feedback_outer_parallel_slot=feedback_outer_parallel_slot,
        feedback_outer_preplanned_ports=feedback_outer_preplanned_ports,
        feedback_outer_obstacles=feedback_outer_obstacles,
        obstacle_positions=tuple(
            position
            for node_id, position in positions.items()
            if node_id not in {str(edge["from"]), str(edge["to"])}
        ),
    )
    if process_row_card_side_path is not None:
        if (
            intent != "process" or kind == "feedback"
            or source_position[1] != target_position[1]
            or edge["from"] == edge["to"]
        ):
            raise ValueError("invalid process card side-port detour")
        path = process_row_card_side_path
        route = "process-row-card-side-detour"
    if long_vertical_label_x is not None and route == "vertical":
        label_x = long_vertical_label_x
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
            route in {"standard", "process-row-card-detour"}
            or (
                route == "process-row-gutter"
                and source_position[1] == min(y for _, y in positions.values())
            )
        )
    )
    if same_process_row:
        # A first-row gutter label shares the header rail's safe vertical slot;
        # centering a wrapped box on the path could cover the purpose block.
        if process_adjacent_label_x is not None:
            label_x = process_adjacent_label_x
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
        route == "process-row-gutter"
        and process_same_row_target_port_x is not None
        and isinstance(process_adjacent_route_y, tuple)
        and process_adjacent_label_y is not None
    ):
        # A shared-target lane may move the physical rail without moving its
        # already packed semantic label across a foreign edge.
        label_y = process_adjacent_label_y
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
        if process_adjacent_label_x is not None:
            label_x = process_adjacent_label_x
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
        # A preplanned peer-footer relocation is part of the outer-route
        # collision model; render that exact accepted label rectangle.
        if feedback_footer_label_x_override is not None and feedback_label_y is not None:
            label_x = feedback_footer_label_x_override
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
    if intent == "process" and final_label_override is not None:
        # The rendered route is immutable; move only a demonstrably blocked
        # outer-gutter label after checking every other physical SVG stroke.
        label_x, label_y = final_label_override
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


def render_native_diagram(
    value: Mapping[str, Any], *, _process_group_gap_extra: int = 0
) -> str:
    """Validate representation input and return one deterministic, standalone SVG."""

    model = _normalized_input(value)
    positions, regions, width, height = _layout(model)
    intent = str(model["intent"])
    if _process_group_gap_extra:
        # Only a failed grouped side-port plan invokes this internal retry.
        # Shift whole regions including nodes; width-only growth cannot open
        # a corridor trapped between the existing card columns.
        if intent != "process" or not regions:
            raise ValueError("process gap expansion requires grouped regions")
        if len(regions) > 1:
            order = {
                region[0]: index for index, region in enumerate(
                    sorted(regions, key=lambda region: (region[2], str(region[0])))
                )
            }
            node_group = {str(node["id"]): node["group"] for node in model["nodes"]}
            positions = {
                node_id: (x + _process_group_gap_extra * order[node_group[node_id]], y)
                for node_id, (x, y) in positions.items()
            }
            regions = [
                (group_id, label, x + _process_group_gap_extra * order[group_id],
                 y, region_width, region_height)
                for group_id, label, x, y, region_width, region_height in regions
            ]
            width += _process_group_gap_extra * (len(regions) - 1)
        else:
            # A single group can contain several graph-rank columns. Only
            # after its safe side-port search fails, open actual space between
            # those columns rather than widening the page without clearance.
            columns = sorted({x for x, _ in positions.values()})
            if len(columns) < 2:
                raise ValueError("no separate process rank columns to expand")
            rank = {x: index for index, x in enumerate(columns)}
            positions = {
                node_id: (x + _process_group_gap_extra * rank[x], y)
                for node_id, (x, y) in positions.items()
            }
            added = _process_group_gap_extra * (len(columns) - 1)
            regions = [
                (group_id, label, x, y, region_width + added, region_height)
                for group_id, label, x, y, region_width, region_height in regions
            ]
            width += added
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
    long_vertical_label_x: dict[str, float] = {}
    packed_process_label_bounds: list[tuple[float, float, float, float]] = []
    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH
    vertical_row_gap = process_row_gap if intent == "process" else non_process_row_gap
    row_step = _NODE_HEIGHT + vertical_row_gap
    corridor_use_count: dict[tuple[int, float], int] = defaultdict(int)
    diagonal_target_corridor_uses: dict[tuple[int, float], int] = defaultdict(int)
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
        # Only the diagonal target leg shares the receiving row corridor
        # with long vertical peers. Counting source legs here would repack
        # labels on otherwise collision-free vertical connections.
        if intent == "process" and source[0] != target[0] and source[1] != target[1]:
            direction = 1 if source[1] < target[1] else -1
            for endpoint, leg_direction in ((target, -direction),):
                endpoint_y = endpoint[1] + (
                    _NODE_HEIGHT if leg_direction > 0 else 0
                )
                corridor_key = (
                    endpoint[0], endpoint_y + leg_direction * vertical_row_gap / 2
                )
                corridor_use_count[corridor_key] += 1
                diagonal_target_corridor_uses[corridor_key] += 1
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
    # A diagonal target counts as a label-corridor occupant, but it is not
    # another same-column return path. Only in that case keep the short
    # local return while relocating its competing label to the outer pack.
    diagonal_only_shared_ids = {
        edge_id
        for corridor_key, items in corridor_groups.items()
        if diagonal_target_corridor_uses[corridor_key]
        and corridor_use_count[corridor_key] - diagonal_target_corridor_uses[corridor_key] == 1
        for _, edge_id, _, _ in items
    }
    long_vertical_pack_bottom = 0.0
    if shared_long_verticals:
        # Group backgrounds are not path obstacles. Use the real card boundary
        # for the adjacent gutter; adding the group frame width can move a
        # previously safe long return through an unrelated self-loop label.
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
            label_gutter_x = obstacle_right + 12.0 + slot * _PROCESS_GUTTER_LANE_STEP
            gutter_x = label_gutter_x
            packed_y = max(
                natural_y,
                previous_bottom + 8 + label_height / 2,
            )
            if edge_id in diagonal_only_shared_ids:
                packed_edge = next(
                    edge for edge in model["edges"] if str(edge["id"]) == edge_id
                )
                edge_source = positions[str(packed_edge["from"])]
                edge_target = positions[str(packed_edge["to"])]
                gutter_x = edge_source[0] + node_width + _CORRIDOR_GUTTER_OFFSET
                long_vertical_label_x[edge_id] = (
                    label_gutter_x + 8 + label_width / 2
                )
                # An intermediate self-loop's real Bezier reach can cross the
                # middle of a packed label even when its return stays local.
                # Keep that label in a clear endpoint row corridor instead.
                loop_tops = [
                    position[1]
                    for relation in model["edges"]
                    if str(relation["kind"]) != "feedback"
                    and relation["from"] == relation["to"]
                    and min(edge_source[1], edge_target[1]) < (
                        position := positions[str(relation["from"])]
                    )[1]
                    < max(edge_source[1], edge_target[1])
                    and label_gutter_x + 8
                    < position[0] + node_width + _SELF_LOOP_BASE_REACH
                    + _PROCESS_SELF_LOOP_MAX_LANE_REACH
                    and label_gutter_x + 8 + label_width > position[0] + node_width
                ]
                if loop_tops and any(
                    top - 44 < packed_y + label_height / 2
                    and top + _NODE_HEIGHT + 44 > packed_y - label_height / 2
                    for top in loop_tops
                ):
                    direction = 1 if edge_source[1] < edge_target[1] else -1
                    source_gap_y = (
                        edge_source[1] + (_NODE_HEIGHT if direction > 0 else 0)
                        + direction * vertical_row_gap / 2
                    )
                    target_gap_y = (
                        edge_target[1] + (_NODE_HEIGHT if direction < 0 else 0)
                        - direction * vertical_row_gap / 2
                    )
                    if label_height + 8 <= vertical_row_gap:
                        safe_gap_y = max(
                            (source_gap_y, target_gap_y),
                            key=lambda y: (min(abs(y - top) for top in loop_tops), y),
                        )
                        packed_y = max(
                            safe_gap_y, previous_bottom + 8 + label_height / 2
                        )
            if (
                edge_id in diagonal_only_shared_ids
                and edge_source[1] > edge_target[1]
            ):
                packed_y = max(packed_y, edge_source[1] - vertical_row_gap / 2)
            long_vertical_gutter_x[edge_id] = gutter_x
            long_vertical_label_y[edge_id] = packed_y
            previous_bottom = packed_y + label_height / 2
            if intent == "process":
                packed_process_label_bounds.append(
                    (
                        label_gutter_x + 8,
                        packed_y - label_height / 2,
                        label_gutter_x + 8 + label_width,
                        previous_bottom,
                    )
                )
            required_right = max(
                required_right,
                label_gutter_x + 8 + label_width + _PAGE_MARGIN,
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

    local_group_branch_gutter_x = (
        _process_local_group_branch_gutter_x(
            model,
            positions,
            regions,
            process_row_gap=process_row_gap,
        )
        if intent == "process"
        else {}
    )
    process_branch_gutter_x: dict[str, float] = {}
    anchored_branch_gutter_x: dict[str, float] = dict(local_group_branch_gutter_x)
    process_adjacent_slot: dict[str, int] = {}
    process_adjacent_count: dict[str, int] = {}
    process_adjacent_label_x: dict[str, float] = {}
    process_adjacent_label_y: dict[str, float] = {}
    process_adjacent_route_y: dict[str, float | tuple[float, float]] = {}
    process_adjacent_target_port_x: dict[str, float] = {}
    occupied_process_adjacent_corridors: set[tuple[int, int]] = set()
    process_outer_label_right = max(
        (right for _, _, right, _ in packed_process_label_bounds),
        default=0.0,
    )
    if intent == "process":
        process_lane_ranks = _stable_lane_ranks(model)
        long_branch_ids = _process_long_branch_ids(
            model,
            positions,
            process_row_gap=process_row_gap,
            local_group_branch_gutter_x=local_group_branch_gutter_x,
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
            local_group_branch_gutter_x=local_group_branch_gutter_x,
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

        # Successful horizontal packs reserve their actual label rectangles
        # across the whole corridor, not just their original x-cluster.
        packed_corridor_label_boxes: dict[
            tuple[int, int], list[tuple[float, float, float, float]]
        ] = defaultdict(list)

        def fixed_long_peer_stems(
            excluded_ids: set[str],
            *,
            shared_source: str | None = None,
        ) -> list[tuple[float, float, float]]:
            """Physical centered endpoint stems of noncandidate long columns."""
            spans: list[tuple[float, float, float]] = []
            for other in model["edges"]:
                if (
                    str(other["kind"]) == "feedback"
                    or other["from"] == other["to"]
                    or str(other["id"]) in excluded_ids
                    or (
                        shared_source is not None
                        and str(other["from"]) != shared_source
                    )
                ):
                    continue
                other_source = positions[str(other["from"])]
                other_target = positions[str(other["to"])]
                if (
                    other_source[0] != other_target[0]
                    or abs(other_source[1] - other_target[1])
                    <= _NODE_HEIGHT + process_row_gap
                ):
                    continue
                descending = other_source[1] < other_target[1]
                start_y = (
                    other_source[1] + _NODE_HEIGHT if descending
                    else other_source[1]
                )
                end_y = (
                    other_target[1] if descending
                    else other_target[1] + _NODE_HEIGHT
                )
                direction = 1 if descending else -1
                for a, b in (
                    (start_y, start_y + direction * process_row_gap / 2),
                    (end_y - direction * process_row_gap / 2, end_y),
                ):
                    spans.append((
                        other_source[0] + _NODE_WIDTH / 2,
                        min(a, b), max(a, b),
                    ))
            return spans

        def try_horizontal_adjacent_pack(
            movable_items: Sequence[tuple[float, str, float, int, bool]],
            fixed_items: Sequence[tuple[float, str, float, int, bool]],
            corridor: tuple[int, int],
        ) -> bool:
            """Keep an overcrowded row corridor local when x-space is available."""
            if (
                not model["groups"]
                or not movable_items
                or any(item[4] for item in movable_items)
            ):
                return False
            upper_bottom, lower_top = corridor
            available_height = lower_top - upper_bottom
            if any(item[3] + 4 > available_height for item in movable_items):
                return False

            corridor_center = (upper_bottom + lower_top) / 2
            candidates: list[tuple[float, str, float]] = []
            candidate_heights: dict[str, int] = {}
            for _, edge_id, label_width, label_height, _ in movable_items:
                edge = edges_by_id[edge_id]
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                upper = source if source[1] <= target[1] else target
                preferred_x = upper[0] + _NODE_WIDTH / 2
                candidates.append((preferred_x, edge_id, label_width))
                candidate_heights[edge_id] = label_height

            def direct_process_cubic(
                edge_id: str,
                route_y: float | None = None,
                target_port_x: float | None = None,
            ) -> tuple[
                tuple[float, float],
                tuple[float, float],
                tuple[float, float],
                tuple[float, float],
            ]:
                edge = edges_by_id[edge_id]
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                slot = process_adjacent_slot.get(edge_id)
                count = process_adjacent_count.get(edge_id, 0)
                if slot is not None and count > 1:
                    centered_slot = slot - (count - 1) / 2
                    lane = int(centered_slot * _PROCESS_LANE_STEP)
                else:
                    lane = (
                        (process_lane_ranks[edge_id] % 5) - 2
                    ) * _PROCESS_LANE_STEP

                if source[1] != target[1]:
                    start_x = source[0] + _NODE_WIDTH / 2
                    end_x = (
                        target_port_x
                        if target_port_x is not None and source[1] < target[1]
                        else target[0] + _NODE_WIDTH / 2
                    )
                    if source[1] < target[1]:
                        start_y = source[1] + _NODE_HEIGHT
                        end_y = target[1]
                    else:
                        start_y = source[1]
                        end_y = target[1] + _NODE_HEIGHT
                    lane_offset = max(-8.0, min(8.0, lane / 2))
                    resolved_route_y = (
                        route_y
                        if route_y is not None
                        else (start_y + end_y) / 2 + lane_offset
                    )
                    return (
                        (float(start_x), float(start_y)),
                        (float(start_x), float(resolved_route_y)),
                        (float(end_x), float(resolved_route_y)),
                        (float(end_x), float(end_y)),
                    )

                start_y = end_y = source[1] + _NODE_HEIGHT / 2
                if source[0] < target[0]:
                    start_x = source[0] + _NODE_WIDTH
                    end_x = target[0]
                    reach = max(52.0, (end_x - start_x) * 0.42)
                    control_one = (start_x + reach, start_y + lane)
                    control_two = (end_x - reach, end_y + lane)
                else:
                    start_x = source[0]
                    end_x = target[0] + _NODE_WIDTH
                    reach = max(52.0, (start_x - end_x) * 0.42)
                    control_one = (start_x - reach, start_y + lane)
                    control_two = (end_x + reach, end_y + lane)
                return (
                    (float(start_x), float(start_y)),
                    (float(control_one[0]), float(control_one[1])),
                    (float(control_two[0]), float(control_two[1])),
                    (float(end_x), float(end_y)),
                )

            candidate_boxes = {
                edge_id: (
                    candidate_x - label_width / 2,
                    corridor_center - candidate_heights[edge_id] / 2,
                    label_width,
                    float(candidate_heights[edge_id]),
                )
                for candidate_x, edge_id, label_width in candidates
            }
            # Earlier successful horizontal packs reserve their actual label
            # rectangles; anchored labels keep the pre-existing fixed-item
            # contract, rather than blocking an entire row corridor.
            foreign_boxes = list(packed_corridor_label_boxes[corridor])
            # Anchors in another x-cluster reserve label positions but do not
            # change the pre-existing route-hull contract for fixed labels.
            candidate_ids = {edge_id for _, edge_id, _ in candidates}
            anchored_boxes = [
                (
                    natural_x - label_width / 2,
                    corridor_center - label_height / 2,
                    label_width,
                    float(label_height),
                )
                for natural_x, edge_id, label_width, label_height, anchored
                in corridor_groups[corridor]
                if anchored and edge_id not in candidate_ids
            ]
            # A packed label cannot cover the outer source/target leg of a
            # long branch routed later in this same corridor. Preserve the
            # established +/-8 px long-branch lane envelope when checking.
            for long_id in sorted(set(long_branch_ids) | set(long_vertical_gutter_x)):
                long_edge = edges_by_id[long_id]
                long_source = positions[str(long_edge["from"])]
                long_target = positions[str(long_edge["to"])]
                if long_source[1] == long_target[1]:
                    continue
                direction = 1 if long_source[1] < long_target[1] else -1
                outer_x = long_vertical_gutter_x.get(
                    long_id,
                    anchored_branch_gutter_x.get(long_id, float(width) - 16.0),
                )
                endpoint_legs = (
                    (
                        long_source[0] + _NODE_WIDTH / 2,
                        (
                            long_source[1] + _NODE_HEIGHT
                            if direction > 0 else long_source[1]
                        ) + direction * process_row_gap / 2,
                    ),
                    (
                        long_target[0] + _NODE_WIDTH / 2,
                        (
                            long_target[1] if direction > 0
                            else long_target[1] + _NODE_HEIGHT
                        ) - direction * process_row_gap / 2,
                    ),
                )
                for endpoint_x, corridor_y in endpoint_legs:
                    leg_left, leg_right = sorted((endpoint_x, outer_x))
                    if any(
                        candidate_id != long_id
                        and box_left < leg_right
                        and box_left + box_width > leg_left
                        and box_top < corridor_y + 8.0
                        and box_top + box_height > corridor_y - 8.0
                        for candidate_id, (
                            box_left, box_top, box_width, box_height
                        ) in candidate_boxes.items()
                    ):
                        return False

            fixed_long_stems = fixed_long_peer_stems(candidate_ids)

            # Only same-column adjacent branches have node-centered
            # vertical endpoint stems across an entire row-gap corridor.
            # Move only a label that actually covers such a stem; demoting
            # the whole cluster can make unrelated return paths intersect.
            stems: set[float] = set()
            for other in model["edges"]:
                if (
                    str(other["id"]) in candidate_ids
                    or str(other["kind"]) == "feedback"
                    or other["from"] == other["to"]
                ):
                    continue
                other_source = positions[str(other["from"])]
                other_target = positions[str(other["to"])]
                if (
                    other_source[0] != other_target[0]
                    or other_source[1] == other_target[1]
                    or abs(other_source[1] - other_target[1])
                    > _NODE_HEIGHT + process_row_gap
                    or (
                        min(other_source[1], other_target[1]) + _NODE_HEIGHT,
                        max(other_source[1], other_target[1]),
                    ) != corridor
                ):
                    continue
                stems.add(other_source[0] + _NODE_WIDTH / 2)
            for candidate_id, box in sorted(candidate_boxes.items()):
                box_left, box_top, box_width, box_height = box
                blocking = [
                    x for x in sorted(stems)
                    if box_left < x < box_left + box_width
                    and box_top < corridor[1]
                    and box_top + box_height > corridor[0]
                ]
                if not blocking:
                    continue
                choices = (
                    max(x + 8 for x in blocking),
                    min(x - box_width - 8 for x in blocking),
                )
                fixed_boxes = (
                    *foreign_boxes,
                    *anchored_boxes,
                    *(
                        (
                            fixed_x - fixed_width / 2,
                            corridor_center - fixed_height / 2,
                            fixed_width,
                            float(fixed_height),
                        )
                        for fixed_x, _, fixed_width, fixed_height, _ in fixed_items
                    ),
                )
                new_left = next(
                    (
                        value for value in choices
                        if value >= 8 and value + box_width <= width - 8
                        and all(not value < stem < value + box_width for stem in stems)
                        and all(
                            peer_id == candidate_id
                            or value >= peer_left + peer_width + 8
                            or value + box_width + 8 <= peer_left
                            or box_top >= peer_top + peer_height + 8
                            or box_top + box_height + 8 <= peer_top
                            for peer_id, (
                                peer_left, peer_top, peer_width, peer_height
                            ) in candidate_boxes.items()
                        )
                        and all(
                            value >= peer_left + peer_width + 8
                            or value + box_width + 8 <= peer_left
                            or box_top >= peer_top + peer_height + 8
                            or box_top + box_height + 8 <= peer_top
                            for peer_left, peer_top, peer_width, peer_height
                            in fixed_boxes
                        )
                    ),
                    None,
                )
                if new_left is None:
                    return False
                candidate_boxes[candidate_id] = (
                    new_left, box_top, box_width, box_height
                )
                candidates = [
                    (new_left + box_width / 2, edge_id, width)
                    if edge_id == candidate_id else (x, edge_id, width)
                    for x, edge_id, width in candidates
                ]

            candidate_route_y: dict[str, float] = {}
            for _, edge_id, _ in candidates:
                edge = edges_by_id[edge_id]
                points = direct_process_cubic(edge_id)
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                peer_boxes = [
                    peer_box
                    for peer_id, peer_box in candidate_boxes.items()
                    if peer_id != edge_id
                ]
                peer_boxes.extend(foreign_boxes)
                # Self-loop labels are fixed above their source card. A
                # branch sharing that endpoint must not cut their text.
                # Other anchored branch labels follow their own established
                # corridor planner and must not demote locally safe routes.
                endpoint_ids = {str(edge["from"]), str(edge["to"])}
                fixed_selfloop_hit = False
                for x, anchor_id, box_width, box_height, fixed in (
                    corridor_groups[corridor]
                ):
                    if not fixed or anchor_id in candidate_ids:
                        continue
                    anchor_edge = edges_by_id[anchor_id]
                    if anchor_edge["from"] != anchor_edge["to"]:
                        continue
                    # Either forward or reverse cubics can cross this
                    # single-line anchored self-loop label band. Multiline
                    # fixed labels retain their separate physical planner.
                    if box_height > 29:
                        continue
                    if str(anchor_edge["from"]) not in endpoint_ids:
                        continue
                    # The fixed one-line self-loop is rendered at
                    # row_top - 18, not at the corridor midpoint. Using
                    # the midpoint falsely accepts lower cubics through
                    # its actual text; keep the existing lane envelope.
                    loop_label_y = positions[str(anchor_edge["from"])][1] - 18
                    box = (
                        x - box_width / 2,
                        loop_label_y - box_height / 2,
                        box_width, float(box_height),
                    )
                    if _cubic_hull_intersects_box(points, box):
                        fixed_selfloop_hit = True
                        peer_boxes.append(box)
                if source[1] == target[1]:
                    endpoints = {str(edge["from"]), str(edge["to"])}
                    if any(
                        node_id not in endpoints
                        and _cubic_hull_intersects_box(
                            points,
                            (
                                float(node_x),
                                float(node_y),
                                float(_NODE_WIDTH),
                                float(_NODE_HEIGHT),
                            ),
                        )
                        for node_id, (node_x, node_y) in positions.items()
                    ):
                        return False
                    if any(
                        _cubic_hull_intersects_box(points, peer_box)
                        for peer_box in peer_boxes
                    ):
                        return False
                    continue

                if not any(
                    _cubic_hull_intersects_box(points, peer_box)
                    for peer_box in peer_boxes
                ):
                    continue

                lower_route_y = float(upper_bottom)
                upper_route_y = float(lower_top)
                default_route_y = points[1][1]
                route_candidates = [
                    lower_route_y + step / 2
                    for step in range(
                        int(round((upper_route_y - lower_route_y) * 2)) + 1
                    )
                ]
                route_candidates.sort(
                    key=lambda value: (abs(value - default_route_y), value)
                )
                def safe_local_cubic(
                    route_y: float, target_port_x: float | None = None
                ) -> bool:
                    trial = direct_process_cubic(
                        edge_id, route_y, target_port_x=target_port_x
                    )
                    if any(
                        _cubic_hull_intersects_box(trial, peer_box)
                        for peer_box in peer_boxes
                    ):
                        return False
                    return not fixed_selfloop_hit or not any(
                        abs(endpoint[0] - fixed_x) < 4
                        and min(max(endpoint[1], control[1]), fixed_high)
                        - max(min(endpoint[1], control[1]), fixed_low) > 4
                        for endpoint, control in (
                            (trial[0], trial[1]), (trial[3], trial[2])
                        )
                        for fixed_x, fixed_low, fixed_high in fixed_long_stems
                    )

                safe_route_y = next(
                    (value for value in route_candidates if safe_local_cubic(value)),
                    None,
                )
                if (
                    safe_route_y is None
                    and fixed_selfloop_hit
                    and fixed_long_stems
                    and source[1] < target[1]
                ):
                    # Keep the same row-gap cubic. The existing target-card
                    # port override offers real in-card entrances when its
                    # center is occupied by a fixed long peer's endpoint stem.
                    for target_port_x in (
                        target[0] + 16.0,
                        target[0] + _NODE_WIDTH - 16.0,
                    ):
                        safe_route_y = next(
                            (
                                value for value in route_candidates
                                if safe_local_cubic(value, target_port_x)
                            ),
                            None,
                        )
                        if safe_route_y is not None:
                            process_adjacent_target_port_x[edge_id] = target_port_x
                            break
                if safe_route_y is None:
                    return False
                candidate_route_y[edge_id] = safe_route_y

            def separated(
                first_x: float,
                first_width: float,
                second_x: float,
                second_width: float,
            ) -> bool:
                return (
                    first_x + first_width / 2 + 8 <= second_x - second_width / 2
                    or second_x + second_width / 2 + 8 <= first_x - first_width / 2
                )

            fixed = [(item[0], item[2]) for item in fixed_items]
            fixed.extend(
                (left + box_width / 2, box_width)
                for left, _, box_width, _ in (*foreign_boxes, *anchored_boxes)
            )
            for index, (candidate_x, _, candidate_width) in enumerate(candidates):
                if any(
                    not separated(candidate_x, candidate_width, fixed_x, fixed_width)
                    for fixed_x, fixed_width in fixed
                ):
                    return False
                if any(
                    not separated(
                        candidate_x,
                        candidate_width,
                        other_x,
                        other_width,
                    )
                    for other_x, _, other_width in candidates[index + 1 :]
                ):
                    return False

            process_adjacent_label_x.update(
                {edge_id: candidate_x for candidate_x, edge_id, _ in candidates}
            )
            process_adjacent_label_y.update(
                {edge_id: corridor_center for _, edge_id, _ in candidates}
            )
            process_adjacent_route_y.update(candidate_route_y)
            packed_corridor_label_boxes[corridor].extend(candidate_boxes.values())
            return True

        singleton_fixed_long_label_ids: set[str] = set()
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
                    if try_horizontal_adjacent_pack(movable, retained, corridor):
                        continue
                    # Movable and conflicting anchored occupants share the
                    # existing deterministic outer-gutter allocator.
                    unsafe_adjacent_branches.update(item[1] for item in movable)
                    if movable:
                        unsafe_corridors.add(corridor)
                    continue
                count = len(cluster)
                if count == 1:
                    natural_x, edge_id, label_width, label_height, _ = cluster[0]
                    center_y = (upper_bottom + lower_top) / 2
                    collides_with_packed = any(
                        natural_x - label_width / 2 < left + box_width
                        and natural_x + label_width / 2 > left
                        and center_y - label_height / 2 < top + box_height
                        and center_y + label_height / 2 > top
                        for left, top, box_width, box_height
                        in packed_corridor_label_boxes[corridor]
                    )
                    # A natural singleton can cover a longer peer's fixed
                    # source/target stem even without a second local label.
                    # Reuse the existing movable pack before outer fallback.
                    fixed_stem_hit = any(
                        natural_x - label_width / 2 - 1.5 < x
                        < natural_x + label_width / 2 + 1.5
                        and center_y - label_height / 2 - 1.5 < high
                        and center_y + label_height / 2 + 1.5 > low
                        for x, low, high in fixed_long_peer_stems(
                            {edge_id},
                            shared_source=str(edges_by_id[edge_id]["from"]),
                        )
                    )
                    if fixed_stem_hit:
                        # Keep the established route. The later final-layout
                        # pass can move only a label that a real peer stroke
                        # still intersects, without repacking the whole edge.
                        singleton_fixed_long_label_ids.add(edge_id)
                    # Later one-item clusters must also honor earlier packs.
                    # The header still reserves the singleton slot if clear.
                    if (
                        collides_with_packed
                        or (
                            corridor != header_corridor
                            and label_height + 8 > available_height
                        )
                    ):
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
                elif not try_horizontal_adjacent_pack(cluster, (), corridor):
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

        # Local long branches are planned before adjacent labels are packed.
        # Inspect the *actual* completed target-corridor label locations:
        # natural key positions can be moved by horizontal/vertical packing.
        # A disjoint destination label must not be cut by the local return.
        for local_id, gutter_x in local_group_branch_gutter_x.items():
            speculative_label_x: dict[str, float] = {}
            edge = edges_by_id[local_id]
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            descending = source[1] < target[1]
            target_corridor = _process_row_corridor_bounds(
                target[1], positions, direction=-1 if descending else 1
            )
            if target_corridor is None:
                continue
            lane = ((process_lane_ranks[local_id] % 5) - 2) * _PROCESS_LANE_STEP
            lane_offset = max(-8.0, min(8.0, lane / 2))
            source_route_y = (
                source[1] + _NODE_HEIGHT + process_row_gap / 2
                if descending else source[1] - process_row_gap / 2
            ) + lane_offset
            target_route_y = (
                target[1] - process_row_gap / 2
                if descending else target[1] + _NODE_HEIGHT + process_row_gap / 2
            ) + lane_offset
            target_center_x = target[0] + _NODE_WIDTH / 2
            # A local long branch traverses every intervening row gap, not
            # just the gap adjacent to its target. Adjacent-edge labels are
            # packed by corridor and may sit directly on that vertical return.
            # Inspect each *actual* label rectangle before preserving a local
            # gutter. If any segment overlaps, use the existing outer lane.
            for occupied_corridor, occupants in corridor_groups.items():
                for natural_x, peer_id, label_width, label_height, fixed in occupants:
                    peer = edges_by_id[peer_id]
                    # Shared endpoints do not exempt peer label rectangles:
                    # the actual local long-leg segments may still cut them.
                    if peer_id == local_id or peer_id in unsafe_adjacent_branches:
                        continue
                    actual_x = speculative_label_x.get(
                        peer_id, process_adjacent_label_x.get(peer_id, natural_x)
                    )
                    if peer_id in process_adjacent_label_y:
                        actual_y = process_adjacent_label_y[peer_id]
                    elif positions[str(peer["from"])][1] == positions[str(peer["to"])][1]:
                        row_top = positions[str(peer["from"])][1]
                        actual_y = (
                            row_top - label_height / 2 - 4
                            if label_height > 29
                            else row_top - 18
                        )
                    else:
                        actual_y = (occupied_corridor[0] + occupied_corridor[1]) / 2
                    left = actual_x - label_width / 2
                    right = actual_x + label_width / 2
                    top = actual_y - label_height / 2
                    bottom = actual_y + label_height / 2
                    vertical_hit = (
                        left < gutter_x < right
                        and top < max(source_route_y, target_route_y)
                        and bottom > min(source_route_y, target_route_y)
                    )
                    horizontal_hit = (
                        occupied_corridor == target_corridor
                        and top < target_route_y < bottom
                        and left < max(gutter_x, target_center_x)
                        and right > min(gutter_x, target_center_x)
                    )
                    if (
                        vertical_hit
                        and not fixed
                        and (
                            (not horizontal_hit and occupied_corridor != target_corridor)
                            or (
                                occupied_corridor == target_corridor
                                and str(edge["to"]) == str(peer["to"])
                            )
                        )
                        and peer_id not in process_adjacent_label_x
                        and peer_id not in speculative_label_x
                    ):
                        peer_source = positions[str(peer["from"])]
                        peer_target = positions[str(peer["to"])]
                        if peer_source[0] < peer_target[0]:
                            # Before widening an otherwise accepted diagram,
                            # relocate a movable adjacent label to the free
                            # row gap directly above its own source column.
                            # This clears the long vertical return without
                            # changing its geometry or the canvas width.
                            new_x = peer_source[0] + _NODE_WIDTH / 2
                            new_left = new_x - label_width / 2
                            new_right = new_x + label_width / 2
                            packed_clear = all(
                                new_left >= box_right + 4
                                or new_right + 4 <= box_left
                                or top >= box_bottom + 4
                                or bottom + 4 <= box_top
                                for box_left, box_top, box_right, box_bottom
                                in packed_process_label_bounds
                            )
                            peers_clear = all(
                                other_id == peer_id
                                or (
                                    new_left >= (
                                        speculative_label_x.get(
                                            other_id,
                                            process_adjacent_label_x.get(
                                                other_id, other_natural_x
                                            ),
                                        ) + other_width / 2 + 4
                                    )
                                    or new_right + 4 <= (
                                        speculative_label_x.get(
                                            other_id,
                                            process_adjacent_label_x.get(
                                                other_id, other_natural_x
                                            ),
                                        ) - other_width / 2
                                    )
                                    or top >= (
                                        process_adjacent_label_y.get(
                                            other_id, sum(occupied_corridor) / 2
                                        ) + other_height / 2 + 4
                                    )
                                    or bottom + 4 <= (
                                        process_adjacent_label_y.get(
                                            other_id, sum(occupied_corridor) / 2
                                        ) - other_height / 2
                                    )
                                )
                                for other_natural_x, other_id, other_width,
                                other_height, _ in occupants
                            )
                            nodes_clear = all(
                                new_left >= node_x + _NODE_WIDTH + 2
                                or new_right + 2 <= node_x
                                or top >= node_y + _NODE_HEIGHT + 2
                                or bottom + 2 <= node_y
                                for node_x, node_y in positions.values()
                            )
                            if (
                                (new_right + 2 <= gutter_x
                                 or new_left >= gutter_x + 2)
                                and packed_clear and peers_clear and nodes_clear
                            ):
                                speculative_label_x[peer_id] = new_x
                                continue
                    if vertical_hit or horizontal_hit:
                        unsafe_adjacent_branches.add(local_id)
                        unsafe_corridors.add(occupied_corridor)
                        anchored_branch_gutter_x.pop(local_id, None)
                        break
                if local_id in unsafe_adjacent_branches:
                    break
            if local_id not in unsafe_adjacent_branches:
                process_adjacent_label_x.update(speculative_label_x)

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
                # The projected label height must match the later rendered
                # label before selecting a clear horizontal route ordinate.
                relation = edges_by_id[edge_id]
                edge_source = positions[str(relation["from"])]
                edge_target = positions[str(relation["to"])]
                if (
                    edge_source[0] != edge_target[0]
                    and 0 < abs(edge_source[1] - edge_target[1])
                    <= _NODE_HEIGHT + process_row_gap
                ):
                    corridor = (
                        min(edge_source[1], edge_target[1]) + _NODE_HEIGHT,
                        max(edge_source[1], edge_target[1]),
                    )
                    label_y = sum(corridor) / 2
                    metrics = _edge_label_metrics(relation, positions, intent)
                    if metrics.height + 8 > corridor[1] - corridor[0]:
                        label_y = adjacent_route_y(edge_id, corridor)
                    process_adjacent_label_y.setdefault(edge_id, label_y)
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
    effective_long_branch_count = 0
    long_branch_pack_bottom = 0.0
    if intent == "process":
        row_step = _NODE_HEIGHT + process_row_gap
        long_branches: list[tuple[float, str, Mapping[str, Any]]] = []
        for edge in model["edges"]:
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if str(edge["id"]) in long_branch_ids:
                natural_y = (source[1] + target[1] + _NODE_HEIGHT) / 2
                long_branches.append((natural_y, str(edge["id"]), edge))
        long_branches.sort(key=lambda item: (item[0], item[1]))
        # A local long vertical with a shared diagonal target also occupies
        # a global label slot, despite retaining its collision-free local path.
        # The synthetic second slot affects only the global label pack, not
        # the physical number of long return paths.
        effective_long_branch_count = len(long_branches) + int(
            len(long_branches) == 1 and bool(diagonal_only_shared_ids)
        )
        for slot, (_, edge_id, _) in enumerate(long_branches):
            long_branch_slots[edge_id] = slot
        if effective_long_branch_count > 1:
            required_gutter = (
                _PROCESS_LONG_BRANCH_GUTTER
                + (effective_long_branch_count - 1) * _PROCESS_GUTTER_LANE_STEP
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

    if intent == "process" and model["groups"] and (
        long_branch_slots or local_group_branch_gutter_x or process_branch_gutter_x
    ):
        # Full source legs of both long and displaced adjacent branches must
        # clear every rendered label in their row corridor. Prefer an unused
        # horizontal ordinate, leaving label anchors and canvas size intact.
        candidates_by_id = sorted(
            set(long_branch_slots) | set(local_group_branch_gutter_x)
            | set(process_branch_gutter_x)
        )
        for long_id in candidates_by_id:
            if long_id in process_adjacent_route_y:
                continue
            long_edge = edges_by_id[long_id]
            source = positions[str(long_edge["from"])]
            target = positions[str(long_edge["to"])]
            descending = source[1] < target[1]
            corridor = _process_row_corridor_bounds(
                source[1], positions, direction=1 if descending else -1
            )
            if corridor is None:
                continue
            low, high = float(corridor[0]) + 2, float(corridor[1]) - 2
            if high <= low:
                continue
            slot = long_branch_slots.get(long_id)
            if slot is not None:
                offset = (slot - (len(long_branch_slots) - 1) / 2) * 4.0
            else:
                offset = ((lane_ranks[long_id] % 5) - 2) * _PROCESS_LANE_STEP / 2
            preferred = sum(corridor) / 2 + max(-8.0, min(8.0, offset))
            endpoint_x = source[0] + _NODE_WIDTH / 2
            gutter_x = process_branch_gutter_x.get(
                long_id,
                anchored_branch_gutter_x.get(
                    long_id, width - _PROCESS_EDGE_GUTTER / 2
                ),
            )
            # A singleton's earlier anchor is not its rendered lane once
            # a diagonal-shared label increases the effective branch count.
            if (
                slot is not None
                and len(long_branch_slots) > 1
                and long_id not in process_branch_gutter_x
            ):
                gutter_x = width - 20 - slot * _PROCESS_GUTTER_LANE_STEP
            left_x, right_x = sorted((endpoint_x, gutter_x))
            blockers: list[tuple[float, float]] = []
            for other_corridor, items in corridor_groups.items():
                if other_corridor != corridor:
                    continue
                for natural_x, other_id, label_width, label_height, _ in items:
                    if other_id == long_id:
                        continue
                    # The source leg crosses the full horizontal span, not
                    # just a peer sharing its endpoint. Every rendered label
                    # in this row corridor, including an anchored local long
                    # branch, is an obstacle if its rectangle intersects.
                    other_x = process_adjacent_label_x.get(other_id, natural_x)
                    if other_id in process_branch_gutter_x:
                        other_x = (
                            process_branch_gutter_x[other_id]
                            + 8 + label_width / 2
                        )
                    if (
                        other_x - label_width / 2 - 2 >= right_x
                        or other_x + label_width / 2 + 2 <= left_x
                    ):
                        continue
                    if other_id in process_adjacent_label_y:
                        other_y = process_adjacent_label_y[other_id]
                    elif edges_by_id[other_id]["from"] == edges_by_id[other_id]["to"]:
                        peer_y = positions[str(edges_by_id[other_id]["from"])][1]
                        other_y = (
                            peer_y - label_height / 2 - 4
                            if label_height > 29 else peer_y - 18
                        )
                    else:
                        other_y = sum(other_corridor) / 2
                    blockers.append((
                        other_y - label_height / 2 - 2,
                        other_y + label_height / 2 + 2,
                    ))
            # Source legs must see packed outer long-branch labels as well
            # as labels still occupying the original corridor.
            for left, top, right, bottom in packed_process_label_bounds:
                if left - 2 < right_x and right + 2 > left_x:
                    blockers.append((top - 2, bottom + 2))
            if not blockers or all(
                not top < preferred < bottom for top, bottom in blockers
            ):
                continue
            ordinates = [max(low, min(high, preferred)), low, high]
            for top, bottom in blockers:
                ordinates.extend((
                    max(low, min(high, top)),
                    max(low, min(high, bottom)),
                ))
            safe_y = next(
                (
                    y for y in sorted(
                        set(ordinates), key=lambda y: (abs(y - preferred), y)
                    )
                    if all(not top < y < bottom for top, bottom in blockers)
                ),
                None,
            )
            if safe_y is None:
                # Moving an adjacent/parallel peer after other branches and
                # footer routes have been planned can invalidate their
                # already-sealed labels. Only a sole long return owns this
                # bounded near-gutter rescue; crowded peers keep their plan.
                if (
                    long_id not in long_branch_ids
                    or len(long_branch_ids) != 1
                    or any(str(edge["kind"]) == "feedback" for edge in model["edges"])
                ):
                    continue
                # The outer rail may be separated from the source by a packed
                # two-line label filling the entire row gap. Before accepting a
                # collision, reuse the nearer card-exterior gutter already used
                # by local vertical branches, but only when its entire vertical
                # return and both adjacent leg rectangles remain unobstructed.
                near = (
                    max(x + _NODE_WIDTH for x, _ in positions.values())
                    + _CORRIDOR_GUTTER_OFFSET
                )
                if (
                    near + 2 < gutter_x
                    and near > max(source[0], target[0]) + _NODE_WIDTH / 2
                ):
                    path_top = min(source[1], target[1])
                    path_bottom = max(source[1], target[1]) + _NODE_HEIGHT
                    peer_boxes = list(packed_process_label_bounds)
                    for other_corridor, occupants in corridor_groups.items():
                        for natural_x, peer_id, box_width, box_height, _ in occupants:
                            if peer_id == long_id:
                                continue
                            peer_x = process_adjacent_label_x.get(peer_id, natural_x)
                            if peer_id in process_branch_gutter_x:
                                peer_x = (
                                    process_branch_gutter_x[peer_id]
                                    + 8 + box_width / 2
                                )
                            if peer_id in process_adjacent_label_y:
                                peer_y = process_adjacent_label_y[peer_id]
                            elif edges_by_id[peer_id]["from"] == edges_by_id[peer_id]["to"]:
                                row_y = positions[str(edges_by_id[peer_id]["from"])][1]
                                peer_y = (
                                    row_y - box_height / 2 - 4
                                    if box_height > 29 else row_y - 18
                                )
                            else:
                                peer_y = sum(other_corridor) / 2
                            peer_boxes.append((
                                peer_x - box_width / 2,
                                peer_y - box_height / 2,
                                peer_x + box_width / 2,
                                peer_y + box_height / 2,
                            ))
                    if all(
                        not (
                            left - 2 < near < right + 2
                            and top - 2 < path_bottom
                            and bottom + 2 > path_top
                        )
                        for left, top, right, bottom in peer_boxes
                    ):
                        near_left, near_right = sorted((endpoint_x, near))
                        near_blockers = [
                            (top - 2, bottom + 2)
                            for left, top, right, bottom in peer_boxes
                            if left - 2 < near_right and right + 2 > near_left
                        ]
                        near_ordinates = [max(low, min(high, preferred)), low, high]
                        for top, bottom in near_blockers:
                            near_ordinates.extend((
                                max(low, min(high, top)),
                                max(low, min(high, bottom)),
                            ))
                        near_safe = next((
                            y for y in sorted(
                                set(near_ordinates),
                                key=lambda y: (abs(y - preferred), y),
                            )
                            if all(not top < y < bottom for top, bottom in near_blockers)
                        ), None)
                        if near_safe is not None:
                            process_branch_gutter_x[long_id] = near
                            process_adjacent_route_y[long_id] = near_safe
                continue
            if safe_y != preferred:
                process_adjacent_route_y[long_id] = safe_y

        # The existing source-leg scan is not sufficient for upward, long
        # branches: their target leg can cross an anchored label in the
        # destination row gap. Reuse its bounded ordinate search there too.
        for long_id in candidates_by_id:
            edge = edges_by_id[long_id]
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if (
                source[1] == target[1]
                or source[0] == target[0]
                or (
                    abs(source[1] - target[1])
                    <= _NODE_HEIGHT + process_row_gap
                    and long_id not in process_branch_gutter_x
                )
            ):
                continue
            descending = source[1] < target[1]
            corridor = _process_row_corridor_bounds(
                target[1], positions, direction=-1 if descending else 1
            )
            if corridor is None:
                continue
            low, high = float(corridor[0]) + 2, float(corridor[1]) - 2
            if low >= high:
                continue
            slot = long_branch_slots.get(long_id)
            if slot is not None:
                lane_offset = (slot - (len(long_branch_slots) - 1) / 2) * 4.0
            else:
                lane_offset = ((lane_ranks[long_id] % 5) - 2) * _PROCESS_LANE_STEP / 2
            lane_offset = max(-8.0, min(8.0, lane_offset))
            end_y = target[1] if descending else target[1] + _NODE_HEIGHT
            preferred = end_y - (1 if descending else -1) * process_row_gap / 2
            preferred += lane_offset
            gutter_x = process_branch_gutter_x.get(
                long_id, anchored_branch_gutter_x.get(long_id)
            )
            if gutter_x is None:
                gutter_x = (
                    width - 20 - slot * _PROCESS_GUTTER_LANE_STEP
                    if slot is not None and len(long_branch_slots) > 1
                    else width - _PROCESS_EDGE_GUTTER / 2
                )
            endpoint_x = target[0] + _NODE_WIDTH / 2
            # A singleton's earlier anchor is not its rendered lane once
            # a diagonal-shared label increases the effective branch count.
            if (
                slot is not None
                and len(long_branch_slots) > 1
                and long_id not in process_branch_gutter_x
            ):
                gutter_x = width - 20 - slot * _PROCESS_GUTTER_LANE_STEP
            left_x, right_x = sorted((endpoint_x, gutter_x))
            blockers: list[tuple[float, float]] = []
            for other_corridor, items in corridor_groups.items():
                if other_corridor != corridor:
                    continue
                for natural_x, other_id, label_width, label_height, _ in items:
                    if other_id == long_id:
                        continue
                    other_x = process_adjacent_label_x.get(other_id, natural_x)
                    if other_id in process_branch_gutter_x:
                        other_x = (
                            process_branch_gutter_x[other_id]
                            + 8 + label_width / 2
                        )
                    if (
                        other_x - label_width / 2 - 2 >= right_x
                        or other_x + label_width / 2 + 2 <= left_x
                    ):
                        continue
                    if other_id in process_adjacent_label_y:
                        other_y = process_adjacent_label_y[other_id]
                    elif edges_by_id[other_id]["from"] == edges_by_id[other_id]["to"]:
                        peer_y = positions[str(edges_by_id[other_id]["from"])][1]
                        other_y = (
                            peer_y - label_height / 2 - 4
                            if label_height > 29 else peer_y - 18
                        )
                    else:
                        other_y = sum(corridor) / 2
                    blockers.append((
                        other_y - label_height / 2 - 2,
                        other_y + label_height / 2 + 2,
                    ))
            # Long-branch labels already packed outside corridor_groups are
            # physical obstacles too; avoid moving the target leg into them.
            for box_left, box_top, box_right, box_bottom in packed_process_label_bounds:
                if box_left - 2 < right_x and box_right + 2 > left_x:
                    blockers.append((box_top - 2, box_bottom + 2))
            if not any(top < preferred < bottom for top, bottom in blockers):
                continue
            candidates = [max(low, min(high, preferred)), low, high]
            for top, bottom in blockers:
                candidates.extend((
                    max(low, min(high, top)),
                    max(low, min(high, bottom)),
                ))
            safe_y = next(
                (
                    y for y in sorted(
                        set(candidates), key=lambda y: (abs(y - preferred), y)
                    )
                    if all(not top < y < bottom for top, bottom in blockers)
                ),
                None,
            )
            if safe_y is None:
                # When two adjacent cross-group endpoints share one saturated
                # row gap, every ordinary ordinate can be occupied by loop
                # labels. A rail 1.5 px off the *actual* card edge is still
                # clear if every rendered label and both endpoint stems are
                # checked. Only movable labels can yield to a shared stem.
                source_corridor = _process_row_corridor_bounds(
                    source[1], positions, direction=1 if descending else -1
                )
                source_center_x = source[0] + _NODE_WIDTH / 2
                target_center_x = target[0] + _NODE_WIDTH / 2
                if (
                    source_corridor == corridor
                    and long_id in process_branch_gutter_x
                    and left_x <= source_center_x <= right_x
                    and abs(source[1] - target[1])
                    <= _NODE_HEIGHT + process_row_gap
                ):
                    boundary_y = high + 0.5 if descending else low - 0.5
                    span_left = min(source_center_x, target_center_x, gutter_x)
                    span_right = max(source_center_x, target_center_x, gutter_x)
                    gap_boxes: list[
                        tuple[str | None, float, float, float, float, bool]
                    ] = []
                    for peer_x, peer_id, peer_width, peer_height, fixed in (
                        corridor_groups.get(corridor, ())
                    ):
                        if peer_id == long_id:
                            continue
                        peer = edges_by_id[peer_id]
                        center_x = process_adjacent_label_x.get(peer_id, peer_x)
                        if peer_id in process_branch_gutter_x:
                            center_x = (
                                process_branch_gutter_x[peer_id]
                                + 8 + peer_width / 2
                            )
                        center_y = process_adjacent_label_y.get(peer_id)
                        if center_y is None:
                            if peer["from"] == peer["to"]:
                                peer_top = positions[str(peer["from"])][1]
                                center_y = (
                                    peer_top - peer_height / 2 - 4
                                    if peer_height > 29 else peer_top - 18
                                )
                            else:
                                center_y = sum(corridor) / 2
                        gap_boxes.append((
                            peer_id, center_x - peer_width / 2,
                            center_y - peer_height / 2,
                            center_x + peer_width / 2,
                            center_y + peer_height / 2,
                            fixed or peer_id in process_branch_gutter_x,
                        ))
                    gap_boxes.extend(
                        (None, left, top, right, bottom, True)
                        for left, top, right, bottom
                        in packed_process_label_bounds
                    )
                    if all(
                        not (
                            left - 2 < span_right
                            and right + 2 > span_left
                            and top - 2 < boundary_y < bottom + 2
                        )
                        for _, left, top, right, bottom, _ in gap_boxes
                    ):
                        proposals: dict[str, float] = {}
                        blocked_stem = False
                        source_port = (
                            source[1] + _NODE_HEIGHT
                            if descending else source[1]
                        )
                        target_port = (
                            target[1] if descending
                            else target[1] + _NODE_HEIGHT
                        )
                        for stem_x, port_y in (
                            (source_center_x, source_port),
                            (target_center_x, target_port),
                        ):
                            for (
                                peer_id, left, top, right, bottom, fixed
                            ) in gap_boxes:
                                if (
                                    peer_id in proposals
                                    or not left - 2 < stem_x < right + 2
                                    or not top - 2 < max(port_y, boundary_y)
                                    or not bottom + 2 > min(port_y, boundary_y)
                                ):
                                    continue
                                if peer_id is None or fixed:
                                    blocked_stem = True
                                    break
                                half_width = (right - left) / 2
                                choices = (
                                    stem_x + half_width + 8,
                                    stem_x - half_width - 8,
                                )
                                relocated_x = next((
                                    candidate for candidate in choices
                                    if candidate - half_width >= 8
                                    and candidate + half_width <= width - 8
                                    and all(
                                        other_id == peer_id
                                        or candidate - half_width
                                        >= other_right + 4
                                        or candidate + half_width + 4
                                        <= other_left
                                        or top >= other_bottom + 4
                                        or bottom + 4 <= other_top
                                        for (
                                            other_id, other_left, other_top,
                                            other_right, other_bottom, _
                                        ) in gap_boxes
                                    )
                                ), None)
                                if relocated_x is None:
                                    blocked_stem = True
                                    break
                                proposals[peer_id] = relocated_x
                            if blocked_stem:
                                break
                        if not blocked_stem:
                            process_adjacent_label_x.update(proposals)
                            process_adjacent_route_y[long_id] = (
                                boundary_y, boundary_y
                            )
                            continue
                near = max(x + _NODE_WIDTH for x, _ in positions.values()) + _CORRIDOR_GUTTER_OFFSET
                if (
                    near < gutter_x
                    and near > max(source[0], target[0]) + _NODE_WIDTH / 2
                    and all(left > near + 2 for left, _, _, _ in packed_process_label_bounds)
                    and all(
                        process_adjacent_label_x.get(
                            peer_id,
                            process_branch_gutter_x[peer_id] + 8 + label_width / 2
                            if peer_id in process_branch_gutter_x else natural_x,
                        ) - label_width / 2 > near + 2
                        for _, occupants in corridor_groups.items()
                        for natural_x, peer_id, label_width, _, _ in occupants
                        if peer_id != long_id
                        and peer_id not in long_branch_slots
                        and peer_id not in long_vertical_label_x
                    )
                ):
                    metrics = _edge_label_metrics(edge, positions, intent)
                    process_adjacent_label_x.setdefault(
                        long_id, gutter_x + 8 + metrics.width / 2
                    )
                    process_branch_gutter_x[long_id] = near
                continue
            existing = process_adjacent_route_y.get(long_id)
            if isinstance(existing, tuple):
                source_route_y = existing[0]
            elif existing is not None:
                source_route_y = existing
            else:
                start_y = (
                    source[1] + _NODE_HEIGHT if descending else source[1]
                )
                source_route_y = (
                    start_y
                    + (1 if descending else -1) * process_row_gap / 2
                    + lane_offset
                )
            process_adjacent_route_y[long_id] = (source_route_y, safe_y)

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
    feedback_path_y: dict[str, float | tuple[float, float]] = {}
    feedback_path_footer_ids: set[str] = set()
    feedback_outer_footer_ids: set[str] = set()
    has_parallel_feedback_peers = False
    # Same directed endpoints yield coincident local feedback strokes.
    # Route semantic peers through the existing stable outer side-port lanes.
    if intent == "process" and model["groups"]:
        by_endpoints: dict[tuple[str, str], list[str]] = defaultdict(list)
        for edge in feedback_edges:
            by_endpoints[(str(edge["from"]), str(edge["to"]))].append(
                str(edge["id"])
            )
        for peer_ids in by_endpoints.values():
            if len(peer_ids) > 1:
                has_parallel_feedback_peers = True
                feedback_outer_footer_ids.update(peer_ids)
                feedback_footer_ids.update(peer_ids)
    feedback_local_gutter_x: dict[str, float] = {}
    anchored_feedback_label_ids = (
        {edge_id for _, _, edge_id, _, _ in anchored_corridor_labels}
        if intent == "process" else set()
    )

    def actual_feedback_obstacle_y(
        edge_id: str,
        corridor: tuple[int, int],
        label_height: int,
    ) -> float:
        """Match the *rendered* anchored label lane, not just its row gap."""
        packed = process_adjacent_label_y.get(edge_id)
        if packed is not None:
            return packed
        edge = edges_by_id[edge_id]
        edge_source = positions[str(edge["from"])]
        edge_target = positions[str(edge["to"])]
        if edge_source[1] == edge_target[1]:
            return (
                edge_source[1] - label_height / 2 - 4
                if label_height > 29 else edge_source[1] - 18
            )
        center = sum(corridor) / 2
        if edge_id not in anchored_feedback_label_ids:
            return center
        if (
            edge_source[0] == edge_target[0]
            and abs(edge_source[1] - edge_target[1])
            > _NODE_HEIGHT + process_row_gap
        ):
            # Same-column long branches render the anchored source-gap label
            # at its exact midpoint, without a semantic lane offset.
            return center
        slot = long_branch_slots.get(edge_id)
        if slot is not None:
            centered_slot = slot - (len(long_branch_slots) - 1) / 2
            offset = centered_slot * 4.0
        else:
            lane = ((lane_ranks[edge_id] % 5) - 2) * _PROCESS_LANE_STEP
            offset = lane / 2
        return center + max(-8.0, min(8.0, offset))
    if intent == "process" and not model["groups"]:
        # A feedback return crosses multiple row corridors. Reserving only
        # the endpoint card span can put its vertical line through an unrelated
        # relation label (or through the next column of cards). Reuse the actual
        # row-label pack before choosing a free local channel.
        occupied_boxes = [
            (float(x), float(y), float(x + _NODE_WIDTH), float(y + _NODE_HEIGHT))
            for x, y in positions.values()
        ]
        occupied_boxes.extend(packed_process_label_bounds)
        for corridor, items in corridor_groups.items():
            for natural_x, occupant_id, label_width, label_height, _ in items:
                occupant = edges_by_id[occupant_id]
                source_y = positions[str(occupant["from"])][1]
                target_y = positions[str(occupant["to"])][1]
                occupant_x = process_adjacent_label_x.get(occupant_id, natural_x)
                if occupant_id in process_branch_gutter_x:
                    occupant_x = (
                        process_branch_gutter_x[occupant_id] + 8 + label_width / 2
                    )
                occupant_y = process_adjacent_label_y.get(occupant_id)
                if occupant_y is None and source_y == target_y:
                    occupant_y = (
                        source_y - label_height / 2 - 4
                        if label_height > 29
                        else source_y - 18
                    )
                elif occupant_y is None:
                    occupant_y = (corridor[0] + corridor[1]) / 2
                occupied_boxes.append(
                    (
                        occupant_x - label_width / 2,
                        occupant_y - label_height / 2,
                        occupant_x + label_width / 2,
                        occupant_y + label_height / 2,
                    )
                )

        def free_horizontal_gap_y(
            corridor: tuple[int, int], from_x: float, to_x: float
        ) -> float | None:
            # A free vertical gutter alone is not sufficient: both horizontal
            # endpoint legs must avoid every rendered node/label rectangle.
            low = float(corridor[0]) + 2
            high = float(corridor[1]) - 2
            if low > high:
                return None
            preferred = (float(corridor[0]) + float(corridor[1])) / 2
            left_x, right_x = sorted((from_x, to_x))
            blockers = [
                (top - 2, bottom + 2)
                for left, top, right, bottom in occupied_boxes
                if left - 2 < right_x and right + 2 > left_x
            ]
            candidates = [min(max(preferred, low), high), low, high]
            for top, bottom in blockers:
                candidates.extend(
                    (min(max(top, low), high), min(max(bottom, low), high))
                )
            return next(
                (
                    y
                    for y in sorted(
                        set(candidates),
                        key=lambda value: (abs(value - preferred), value),
                    )
                    if all(not (top < y < bottom) for top, bottom in blockers)
                ),
                None,
            )

        for edge in feedback_edges:
            if edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if source[1] == target[1]:
                continue
            gutter_x = min(
                width - 16.0,
                max(source[0], target[0])
                + _NODE_WIDTH
                + _CORRIDOR_GUTTER_OFFSET,
            )
            # Conservatively cover the whole vertical feedback return. This
            # avoids routing into cards when escaping a label collision.
            span_top = min(source[1], target[1])
            span_bottom = max(source[1], target[1]) + _NODE_HEIGHT
            occupied_x = sorted(
                (left, right)
                for left, top, right, bottom in occupied_boxes
                if top - 2 < span_bottom and bottom + 2 > span_top
            )
            candidate = gutter_x
            while True:
                blocked_right = max(
                    (
                        right
                        for left, right in occupied_x
                        if left - 2 <= candidate <= right + 2
                    ),
                    default=None,
                )
                if blocked_right is None:
                    break
                candidate = max(candidate + 1, blocked_right + 8)
            if candidate > gutter_x:
                feedback_local_gutter_x[str(edge["id"])] = candidate
                width = max(width, math.ceil(candidate + 16))
            source_direction = 1 if source[1] < target[1] else -1
            source_corridor = _process_row_corridor_bounds(
                source[1], positions, direction=source_direction
            )
            target_corridor = _process_row_corridor_bounds(
                target[1], positions, direction=-source_direction
            )
            if source_corridor is not None and target_corridor is not None:
                source_y = free_horizontal_gap_y(
                    source_corridor, source[0] + _NODE_WIDTH / 2, candidate
                )
                target_y = free_horizontal_gap_y(
                    target_corridor, target[0] + _NODE_WIDTH / 2, candidate
                )
                if source_y is None or target_y is None:
                    # No source/target row-gap lane exists: use side ports
                    # and a dedicated path beneath the complete layout.
                    feedback_outer_footer_ids.add(str(edge["id"]))
                    feedback_footer_ids.add(str(edge["id"]))
                    feedback_local_gutter_x.pop(str(edge["id"]), None)
                    feedback_path_y.pop(str(edge["id"]), None)
                    continue
                source_default_y = sum(source_corridor) / 2
                target_default_y = sum(target_corridor) / 2
                if (source_y, target_y) != (source_default_y, target_default_y):
                    feedback_path_y[str(edge["id"])] = (source_y, target_y)

    if intent == "process" and model["groups"] and feedback_edges:
        # Endpoint-only corridor checks miss an intermediate label when the
        # feedback's vertical return crosses several grouped rows.  Include
        # every already-packed relation label and each card rectangle before
        # selecting a right-hand local gutter.
        feedback_obstacles = list(packed_process_label_bounds)
        feedback_obstacles.extend(
            (float(x), float(y), float(x + _NODE_WIDTH), float(y + _NODE_HEIGHT))
            for x, y in positions.values()
        )
        for corridor, items in corridor_groups.items():
            for natural_x, peer_id, peer_width, peer_height, _ in items:
                peer = edges_by_id[peer_id]
                peer_source = positions[str(peer["from"])]
                peer_target = positions[str(peer["to"])]
                peer_x = process_adjacent_label_x.get(peer_id, natural_x)
                if peer_id in process_branch_gutter_x:
                    peer_x = process_branch_gutter_x[peer_id] + 8 + peer_width / 2
                peer_y = actual_feedback_obstacle_y(
                    peer_id, corridor, peer_height
                )
                feedback_obstacles.append((
                    peer_x - peer_width / 2, peer_y - peer_height / 2,
                    peer_x + peer_width / 2, peer_y + peer_height / 2,
                ))
        for edge in feedback_edges:
            if edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if source[1] == target[1]:
                continue
            edge_id = str(edge["id"])
            current = min(
                width - 16.0,
                max(source[0], target[0])
                + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET,
            )
            span_top = min(source[1], target[1]) - process_row_gap / 2
            span_bottom = (
                max(source[1], target[1])
                + _NODE_HEIGHT + process_row_gap / 2
            )
            # Each rightward detour can meet a different rectangle; iterate
            # to the first collision-free corridor in a deterministic order.
            candidate = current
            while True:
                next_x = max(
                    (
                        right + 8
                        for left, top, right, bottom in feedback_obstacles
                        if top - 2 < span_bottom and bottom + 2 > span_top
                        and left - 2 <= candidate <= right + 2
                    ),
                    default=None,
                )
                if next_x is None:
                    break
                candidate = max(candidate + 1, next_x)
            if candidate > current:
                feedback_local_gutter_x[edge_id] = candidate
                width = max(width, math.ceil(candidate + 16))
            # The global scan also has to choose both full horizontal legs:
            # long-branch labels are not necessarily in endpoint corridors
            # recorded by the adjacent-edge-only planner below.
            direction = 1 if source[1] < target[1] else -1
            endpoints = (
                (
                    _process_row_corridor_bounds(
                        source[1], positions, direction=direction
                    ),
                    source[0] + _NODE_WIDTH / 2,
                    source[1] + (_NODE_HEIGHT if direction > 0 else 0),
                ),
                (
                    _process_row_corridor_bounds(
                        target[1], positions, direction=-direction
                    ),
                    target[0] + _NODE_WIDTH / 2,
                    target[1] + (0 if direction > 0 else _NODE_HEIGHT),
                ),
            )
            free_legs: list[float] = []
            for corridor, endpoint_x, port_y in endpoints:
                if corridor is None:
                    break
                low, high = corridor[0] + 2.0, corridor[1] - 2.0
                preferred = sum(corridor) / 2
                left_x, right_x = sorted((endpoint_x, candidate))
                blockers = [
                    (top - 2, bottom + 2)
                    for left, top, right, bottom in feedback_obstacles
                    if left - 2 < right_x and right + 2 > left_x
                ]
                candidates = [preferred, low, high]
                for top, bottom in blockers:
                    candidates.extend((
                        min(max(top, low), high),
                        min(max(bottom, low), high),
                    ))
                best = next(
                    (
                        y for y in sorted(
                            set(candidates),
                            key=lambda value: (abs(value - preferred), value),
                        )
                        if all(not top < y < bottom for top, bottom in blockers)
                        and all(
                            not (
                                left < endpoint_x < right
                                and top < max(port_y, y)
                                and bottom > min(port_y, y)
                            )
                            for left, top, right, bottom in feedback_obstacles
                        )
                    ),
                    None,
                )
                if best is None:
                    break
                free_legs.append(best)
            if len(free_legs) != 2:
                feedback_outer_footer_ids.add(edge_id)
                feedback_footer_ids.add(edge_id)
                feedback_local_gutter_x.pop(edge_id, None)
            elif (
                free_legs[0] != sum(endpoints[0][0]) / 2
                or free_legs[1] != sum(endpoints[1][0]) / 2
            ):
                feedback_path_y[edge_id] = (
                    free_legs[0], free_legs[1]
                )

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
                target_corridor = source_corridor
                if source_corridor is not None:
                    feedback_corridors.add(source_corridor)
            shared_corridors = (
                feedback_corridors & occupied_process_adjacent_corridors
            )
            if not shared_corridors:
                continue

            edge_id = str(edge["id"])
            if edge_id in feedback_outer_footer_ids:
                continue
            # A crowded, already rejected row-gap pack remains saturated
            # after its labels move outward: retain the existing safe footer
            # sideports rather than speculatively reusing the local channel.
            if (
                model["groups"] and source[1] != target[1]
                and any(
                    corridor in unsafe_corridors
                    and any(
                        peer_id in unsafe_adjacent_branches
                        and peer_height + 4 >= corridor[1] - corridor[0]
                        for _, peer_id, _, peer_height, _ in corridor_groups[corridor]
                    )
                    for corridor in shared_corridors
                )
            ):
                feedback_outer_footer_ids.add(edge_id)
                feedback_footer_ids.add(edge_id)
                feedback_local_gutter_x.pop(edge_id, None)
                feedback_path_y.pop(edge_id, None)
                continue
            local_grouped_reverse_return = (
                len(feedback_edges) == 1
                and bool(model["groups"])
                and source[1] == target[1]
                and source[0] > target[0]
            )
            if not local_grouped_reverse_return:
                feedback_footer_ids.add(edge_id)
                if model["groups"] and edge["from"] != edge["to"]:
                    # A footer moves the TEXT, not its horizontal or vertical
                    # return path. First reserve the entire vertical gutter
                    # against actual rectangles of other labels, including
                    # labels already sent to the outer process gutter.
                    # Keep the whole-span, node-aware decision. Reverting
                    # to the original local x here could detour the vertical
                    # return straight into another group's card column.
                    current_gutter_x = feedback_local_gutter_x.get(
                        edge_id,
                        min(
                            width - 16.0,
                            max(source[0], target[0])
                            + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET,
                        ),
                    )
                    # Late footer detours must clear cards as well as labels.
                    # Reuse the existing node-aware obstacle inventory.
                    label_boxes = list(feedback_obstacles)
                    for other_corridor, other_items in corridor_groups.items():
                        for natural_x, other_id, label_width, label_height, _ in other_items:
                            other = edges_by_id[other_id]
                            other_source = positions[str(other["from"])]
                            other_target = positions[str(other["to"])]
                            actual_x = process_adjacent_label_x.get(other_id, natural_x)
                            if other_id in process_branch_gutter_x:
                                actual_x = (
                                    process_branch_gutter_x[other_id]
                                    + 8 + label_width / 2
                                )
                            actual_y = actual_feedback_obstacle_y(
                                other_id, other_corridor, label_height
                            )
                            label_boxes.append((
                                actual_x - label_width / 2,
                                actual_y - label_height / 2,
                                actual_x + label_width / 2,
                                actual_y + label_height / 2,
                            ))
                    candidate_gutter_x = current_gutter_x
                    # Sorting by left edge makes the monotonic detour bounded:
                    # each rectangle is visited at most once.
                    for left, top, right, bottom in sorted(label_boxes):
                        if (
                            bottom > min(source[1], target[1])
                            and top < height
                            and left - 2 < candidate_gutter_x < right + 2
                        ):
                            candidate_gutter_x = max(candidate_gutter_x, right + 8)
                    if candidate_gutter_x > width - 16:
                        feedback_outer_footer_ids.add(edge_id)
                        feedback_local_gutter_x.pop(edge_id, None)
                        continue
                    if candidate_gutter_x != current_gutter_x:
                        feedback_local_gutter_x[edge_id] = candidate_gutter_x

                    # Each horizontal leg uses a real row-gap corridor; a
                    # same-row return needs both endpoint legs checked too.
                    safe_legs: list[float] = []
                    for corridor, endpoint_x, port_y in (
                        (
                            source_corridor, source[0] + _NODE_WIDTH / 2,
                            source[1] + (
                                _NODE_HEIGHT if source[1] <= target[1] else 0
                            ),
                        ),
                        (
                            target_corridor, target[0] + _NODE_WIDTH / 2,
                            target[1] + (
                                0 if source[1] < target[1] else _NODE_HEIGHT
                            ),
                        ),
                    ):
                        if corridor is None:
                            feedback_outer_footer_ids.add(edge_id)
                            break
                        default_y = (corridor[0] + corridor[1]) / 2
                        left_x, right_x = sorted((
                            endpoint_x, candidate_gutter_x,
                        ))
                        blockers: list[tuple[float, float]] = []
                        for (
                            natural_x, peer_id, peer_width, peer_height, _
                        ) in corridor_groups.get(corridor, ()):
                            peer_x = process_adjacent_label_x.get(
                                peer_id, natural_x
                            )
                            if peer_id in process_branch_gutter_x:
                                peer_x = (
                                    process_branch_gutter_x[peer_id]
                                    + 8 + peer_width / 2
                                )
                            peer_y = actual_feedback_obstacle_y(
                                peer_id, corridor, peer_height
                            )
                            if (
                                peer_x - peer_width / 2 < right_x + 2
                                and peer_x + peer_width / 2 > left_x - 2
                            ):
                                blockers.append((
                                    peer_y - peer_height / 2 - 2,
                                    peer_y + peer_height / 2 + 2,
                                ))
                        # Long-branch and externally packed labels are not
                        # present in corridor_groups, but the complete endpoint
                        # horizontal segment can still cross their rectangles.
                        for label_left, label_top, label_right, label_bottom in (
                            feedback_obstacles
                        ):
                            if (
                                label_left - 2 < right_x
                                and label_right + 2 > left_x
                            ):
                                blockers.append((
                                    label_top - 2, label_bottom + 2
                                ))
                        low, high = corridor[0] + 2.0, corridor[1] - 2.0
                        candidates = [default_y, low, high]
                        for block_low, block_high in blockers:
                            candidates.extend((block_low, block_high))
                        best_y = next(
                            (
                                y for y in sorted(
                                    {min(max(value, low), high) for value in candidates},
                                    key=lambda value: (abs(value - default_y), value),
                                )
                                if all(
                                    not block_low < y < block_high
                                    for block_low, block_high in blockers
                                )
                                and all(
                                    not (
                                        left < endpoint_x < right
                                        and top < max(port_y, y)
                                        and bottom > min(port_y, y)
                                    )
                                    for left, top, right, bottom in label_boxes
                                )
                            ),
                            None,
                        )
                        if best_y is None:
                            # All local heights are occupied.  Do not
                            # intersect the peer label or abort rendering.
                            feedback_outer_footer_ids.add(edge_id)
                            break
                        safe_legs.append(best_y)
                    if edge_id in feedback_outer_footer_ids:
                        feedback_local_gutter_x.pop(edge_id, None)
                        feedback_path_y.pop(edge_id, None)
                    else:
                        feedback_path_y[edge_id] = (
                            safe_legs[0], safe_legs[1]
                        )
                continue
            metrics = _edge_label_metrics(edge, positions, intent)
            _, feedback_label_x, feedback_label_y, _ = _edge_geometry(
                source,
                target,
                self_loop=edge["from"] == edge["to"],
                lane=((lane_ranks[edge_id] % 5) - 2) * _PROCESS_LANE_STEP,
                kind="feedback",
                canvas_width=width,
                canvas_height=height,
                intent=intent,
                process_row_gap=process_row_gap,
                label_height=metrics.height,
                label_width=metrics.width,
                preserve_same_row_feedback_footer=False,
            )
            feedback_left = feedback_label_x - metrics.width / 2
            feedback_right = feedback_label_x + metrics.width / 2
            feedback_top = feedback_label_y - metrics.height / 2
            feedback_bottom = feedback_label_y + metrics.height / 2
            collision = False
            feedback_segment_left = min(
                source[0] + _NODE_WIDTH / 2,
                target[0] + _NODE_WIDTH / 2,
            )
            feedback_segment_right = min(
                width - 16.0,
                max(source[0], target[0])
                + _NODE_WIDTH
                + _CORRIDOR_GUTTER_OFFSET,
            )
            blocked_by_corridor: dict[tuple[int, int], list[tuple[float, float]]] = (
                defaultdict(list)
            )
            for corridor in shared_corridors:
                for (
                    natural_x,
                    occupant_id,
                    occupant_width,
                    occupant_height,
                    _,
                ) in corridor_groups.get(corridor, ()):
                    occupant_edge = edges_by_id[occupant_id]
                    if occupant_edge["from"] == occupant_edge["to"]:
                        collision = True
                        continue
                    occupant_x = process_adjacent_label_x.get(
                        occupant_id, natural_x
                    )
                    if occupant_id in process_branch_gutter_x:
                        occupant_x = (
                            process_branch_gutter_x[occupant_id]
                            + 8
                            + occupant_width / 2
                        )
                    if occupant_id in process_adjacent_label_y:
                        occupant_y = process_adjacent_label_y[occupant_id]
                    elif corridor[1] - corridor[0] >= occupant_height + 8:
                        occupant_y = (corridor[0] + corridor[1]) / 2
                    else:
                        occupant_y = adjacent_route_y(occupant_id, corridor)
                    occupant_left = occupant_x - occupant_width / 2
                    occupant_right = occupant_x + occupant_width / 2
                    occupant_top = occupant_y - occupant_height / 2
                    occupant_bottom = occupant_y + occupant_height / 2
                    if (
                        feedback_left < occupant_right
                        and feedback_right > occupant_left
                        and feedback_top < occupant_bottom
                        and feedback_bottom > occupant_top
                    ):
                        collision = True
                    if (
                        feedback_segment_left < occupant_right + 2
                        and feedback_segment_right > occupant_left - 2
                    ):
                        blocked_by_corridor[corridor].append(
                            (occupant_top - 2, occupant_bottom + 2)
                        )

            path_collision = False
            for corridor in shared_corridors:
                blocked = sorted(blocked_by_corridor.get(corridor, ()))
                if not blocked:
                    continue
                lower = corridor[0] + 2
                upper = corridor[1] - 2
                merged: list[tuple[float, float]] = []
                for block_start, block_end in blocked:
                    block_start = max(lower, block_start)
                    block_end = min(upper, block_end)
                    if block_end <= lower or block_start >= upper:
                        continue
                    if merged and block_start <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], block_end))
                    else:
                        merged.append((block_start, block_end))
                gaps: list[tuple[float, float]] = []
                cursor = lower
                for block_start, block_end in merged:
                    if cursor < block_start:
                        gaps.append((cursor, block_start))
                    cursor = max(cursor, block_end)
                if cursor < upper:
                    gaps.append((cursor, upper))
                if not gaps:
                    path_collision = True
                    continue
                preferred = (corridor[0] + corridor[1]) / 2
                candidate = min(
                    (
                        min(max(preferred, gap_start), gap_end)
                        for gap_start, gap_end in gaps
                        if gap_end - gap_start >= 2
                    ),
                    key=lambda value: (abs(value - preferred), value),
                    default=None,
                )
                if candidate is None:
                    path_collision = True
                else:
                    feedback_path_y[edge_id] = candidate
            if path_collision:
                feedback_footer_ids.add(edge_id)
                feedback_path_footer_ids.add(edge_id)
            elif collision:
                feedback_footer_ids.add(edge_id)
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
    if feedback_outer_footer_ids:
        # Reserve a path-only footer below the semantic feedback label
        # pack.  The extra strip is requested only for saturated rows.
        height = max(
            height, math.ceil(
                feedback_base_bottom
                + 112 + feedback_count * _FEEDBACK_LABEL_LANE_STEP
            ),
        )

    if intent == "process" and feedback_count == 1:
        edge = feedback_edges[0]
        edge_id = str(edge["id"])
        source = positions[str(edge["from"])]
        target = positions[str(edge["to"])]
        preserve_local_footer = (
            edge["from"] != edge["to"]
            and _preserve_same_row_process_feedback_return(
                source, target, positions
            )
        )
        if edge_id not in feedback_footer_ids:
            # Packed labels occupy their rendered rectangles, not every row
            # corridor in the diagram. Check the unforced feedback label after
            # canvas sizing so the accepted reverse return uses its real footer.
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
                preserve_same_row_feedback_footer=preserve_local_footer,
            )
            half_width = metrics.width / 2
            half_height = metrics.height / 2
            label_x = min(max(label_x, half_width + 8), width - half_width - 8)
            label_left = label_x - half_width
            label_right = label_x + half_width
            label_top = label_y - half_height
            label_bottom = label_y + half_height
            collides_with_packed_label = any(
                label_left < right + 8
                and label_right > left - 8
                and label_top < bottom + 8
                and label_bottom > top - 8
                for left, top, right, bottom in packed_process_label_bounds
            )
            collides_with_node = any(
                label_left < node_x + _NODE_WIDTH + 8
                and label_right > node_x - 8
                and label_top < node_y + _NODE_HEIGHT + 8
                and label_bottom > node_y - 8
                for node_x, node_y in positions.values()
            )
            # Long branches have both source and target horizontal legs.
            # A cross-group branch can cross this feedback label even when
            # its endpoints occupy different columns (the old test skipped it).
            collides_with_edge_leg = False
            for other in (model["edges"] if model["groups"] else ()):
                if str(other["kind"]) == "feedback" or other["from"] == other["to"]:
                    continue
                other_source = positions[str(other["from"])]
                other_target = positions[str(other["to"])]
                if (
                    abs(other_target[1] - other_source[1])
                    <= _NODE_HEIGHT + process_row_gap
                ):
                    continue
                other_id = str(other["id"])
                direction = 1 if other_source[1] < other_target[1] else -1
                start_y = (
                    other_source[1] + _NODE_HEIGHT
                    if direction > 0
                    else other_source[1]
                )
                end_y = (
                    other_target[1]
                    if direction > 0
                    else other_target[1] + _NODE_HEIGHT
                )
                if other_source[0] == other_target[0]:
                    # Vertical same-column branches use their own outer lanes
                    # without the id-dependent cross-column lane offset.
                    gutter_x = process_branch_gutter_x.get(
                        other_id,
                        long_vertical_gutter_x.get(
                            other_id,
                            other_source[0]
                            + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET,
                        ),
                    )
                    lane_offset = 0.0
                else:
                    # Mirror the cross-group long branch's actual routed x
                    # and y; checking only the source leg misses its target.
                    gutter_x = process_branch_gutter_x.get(
                        other_id, anchored_branch_gutter_x.get(other_id)
                    )
                    slot = long_branch_slots.get(other_id)
                    if gutter_x is None:
                        gutter_x = (
                            width - _PROCESS_EDGE_GUTTER / 2
                            if slot is None or len(long_branch_slots) <= 1
                            else width - 20 - slot * _PROCESS_GUTTER_LANE_STEP
                        )
                    if slot is not None:
                        centered_slot = slot - (len(long_branch_slots) - 1) / 2
                        lane_offset = max(-8.0, min(8.0, centered_slot * 4.0))
                    else:
                        lane = ((lane_ranks[other_id] % 5) - 2) * _PROCESS_LANE_STEP
                        lane_offset = max(-8.0, min(8.0, lane / 2))
                source_leg_y = (
                    start_y + direction * process_row_gap / 2 + lane_offset
                )
                target_leg_y = (
                    end_y - direction * process_row_gap / 2 + lane_offset
                )
                for endpoint_x, corridor_y in (
                    (other_source[0] + _NODE_WIDTH / 2, source_leg_y),
                    (other_target[0] + _NODE_WIDTH / 2, target_leg_y),
                ):
                    left_x, right_x = sorted((endpoint_x, gutter_x))
                    if (
                        label_left < right_x
                        and label_right > left_x
                        and label_top < corridor_y < label_bottom
                    ):
                        collides_with_edge_leg = True
                        break
                # The orthogonal long branch also has a vertical gutter
                # connecting those endpoint legs. The feedback label must not
                # overlap its actual y-span at the planned gutter x.
                if (
                    not collides_with_edge_leg
                    and label_left < gutter_x < label_right
                    and label_top < max(source_leg_y, target_leg_y)
                    and label_bottom > min(source_leg_y, target_leg_y)
                ):
                    collides_with_edge_leg = True
                if collides_with_edge_leg:
                    break

            if collides_with_packed_label or collides_with_node or collides_with_edge_leg:
                feedback_footer_ids.add(edge_id)
                if (
                    model["groups"]
                    and edge["from"] != edge["to"]
                    and not preserve_local_footer
                    and edge_id not in feedback_outer_footer_ids
                ):
                    # Moving only the label to the footer also extends the
                    # feedback return down its current vertical gutter. If
                    # that gutter meets any actual peer label or card in the
                    # extended span, switch the path to the reserved side-port
                    # footer route rather than drawing through the obstacle.
                    gutter_x = feedback_local_gutter_x.get(
                        edge_id,
                        min(
                            width - 16.0,
                            max(source[0], target[0])
                            + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET,
                        ),
                    )
                    span_top = min(source[1], target[1]) + _NODE_HEIGHT
                    if any(
                        left - 2 < gutter_x < right + 2
                        and top - 2 < height
                        and bottom + 2 > span_top
                        for left, top, right, bottom in feedback_obstacles
                    ):
                        feedback_outer_footer_ids.add(edge_id)
                        feedback_local_gutter_x.pop(edge_id, None)
                        feedback_path_y.pop(edge_id, None)
                        height = max(
                            height,
                            math.ceil(
                                feedback_base_bottom
                                + 112
                                + feedback_count * _FEEDBACK_LABEL_LANE_STEP
                            ),
                        )

    grouped_feedback_rail_replanned = False
    feedback_rail_exhausted = False
    # Grouped feedback peer routes can occupy the same physical row-gap rail
    # even with distinct endpoint pairs. Resolve only overlapping local legs
    # after the existing label/side-port planners have fixed their decisions.
    # This uses their true corridor and obstacle geometry, without a new SVG
    # postprocessor or changing unrelated accepted paths.
    if intent == "process" and model["groups"] and feedback_edges:
        reserved_feedback_legs: list[tuple[float, float, float]] = []
        reserved_feedback_gutters: list[tuple[float, float, float]] = []
        # Same-row feedbacks are already physically routed. They are not
        # eligible for this replanning, but their actual drawn L legs must
        # reserve the lane before cross-row peers select a new ordinate.
        for fixed_edge in feedback_edges:
            fixed_id = str(fixed_edge["id"])
            fixed_source = positions[str(fixed_edge["from"])]
            fixed_target = positions[str(fixed_edge["to"])]
            if (
                fixed_id in feedback_outer_footer_ids
                or (
                    fixed_source[1] != fixed_target[1]
                    and fixed_id not in feedback_path_footer_ids
                )
            ):
                continue
            fixed_slot = feedback_slots[fixed_id]
            fixed_metrics = _edge_label_metrics(fixed_edge, positions, intent)
            fixed_lane = (
                self_loop_lanes[fixed_id] if fixed_id in self_loop_lanes
                else int((fixed_slot - (feedback_count - 1) / 2) * _PROCESS_LANE_STEP)
                if feedback_count > 1
                else ((lane_ranks[fixed_id] % 5) - 2) * _PROCESS_LANE_STEP
            )
            fixed_label_y = (
                feedback_base_bottom + 10
                + fixed_slot * _FEEDBACK_LABEL_LANE_STEP
                + fixed_metrics.height / 2
                if feedback_count > 1 or fixed_id in feedback_footer_ids
                else None
            )
            fixed_path, _, _, _ = _edge_geometry(
                fixed_source, fixed_target,
                self_loop=fixed_edge["from"] == fixed_edge["to"],
                lane=fixed_lane, kind="feedback",
                canvas_width=width, canvas_height=height, intent=intent,
                process_row_gap=process_row_gap,
                label_width=fixed_metrics.width,
                label_height=fixed_metrics.height,
                feedback_label_y=fixed_label_y,
                feedback_path_y=feedback_path_y.get(fixed_id),
                feedback_path_footer=fixed_id in feedback_path_footer_ids,
                feedback_local_gutter_x=feedback_local_gutter_x.get(fixed_id),
                preserve_same_row_feedback_footer=(
                    _preserve_same_row_process_feedback_return(
                        fixed_source, fixed_target, positions
                    )
                ),
            )
            cubic_end = re.search(
                r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
                r"([-0-9.]+) ([-0-9.]+) L ",
                fixed_path,
            )
            if cubic_end:
                fixed_points = [
                    (float(cubic_end.group(1)), float(cubic_end.group(2)))
                ]
                fixed_points.extend(
                    (float(x), float(y))
                    for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", fixed_path)
                )
            else:
                fixed_points = [
                    (float(x), float(y))
                    for x, y in re.findall(
                        r"(?:M|L) ([-0-9.]+) ([-0-9.]+)", fixed_path
                    )
                ]
            fixed_legs = [
                (min(x0, x1), max(x0, x1), y0)
                for (x0, y0), (x1, y1) in zip(fixed_points, fixed_points[1:])
                if abs(y0 - y1) < 0.01 and abs(x0 - x1) > 4
            ]
            fixed_gutters = [
                (x0, min(y0, y1), max(y0, y1))
                for (x0, y0), (x1, y1) in zip(fixed_points, fixed_points[1:])
                if abs(x0 - x1) < 0.01 and abs(y0 - y1) > 4
            ]
            if (
                any(
                    min(right, peer_right) - max(left, peer_left) > 4
                    and abs(y - peer_y) < 4
                    for left, right, y in fixed_legs
                    for peer_left, peer_right, peer_y in reserved_feedback_legs
                )
                or any(
                    abs(x - peer_x) < 4
                    and min(high, peer_high) - max(low, peer_low) > 4
                    for x, low, high in fixed_gutters
                    for peer_x, peer_low, peer_high in reserved_feedback_gutters
                )
            ):
                # Two immutable same-row plans cannot own one semantic stroke.
                # Reuse the existing collision-checked outer footer for the
                # later sorted relation; never merely change SVG paint order.
                feedback_rail_exhausted = True
                grouped_feedback_rail_replanned = True
                feedback_outer_footer_ids.add(fixed_id)
                feedback_footer_ids.add(fixed_id)
                feedback_path_y.pop(fixed_id, None)
                feedback_local_gutter_x.pop(fixed_id, None)
                height = max(
                    height,
                    math.ceil(
                        feedback_base_bottom
                        + 112 + feedback_count * _FEEDBACK_LABEL_LANE_STEP
                    ),
                )
                continue
            reserved_feedback_legs.extend(fixed_legs)
            reserved_feedback_gutters.extend(fixed_gutters)
        for edge in feedback_edges:
            edge_id = str(edge["id"])
            if (
                edge_id in feedback_outer_footer_ids
                or edge_id in feedback_path_footer_ids
                or edge["from"] == edge["to"]
            ):
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if source[1] == target[1]:
                continue
            direction = 1 if source[1] < target[1] else -1
            source_gap = _process_row_corridor_bounds(
                source[1], positions, direction=direction
            )
            target_gap = _process_row_corridor_bounds(
                target[1], positions, direction=-direction
            )
            if source_gap is None or target_gap is None:
                continue
            original = feedback_path_y.get(edge_id)
            base_source, base_target = (
                original if isinstance(original, tuple)
                else (sum(source_gap) / 2, sum(target_gap) / 2)
            )
            source_x = float(source[0] + _NODE_WIDTH / 2)
            target_x = float(target[0] + _NODE_WIDTH / 2)
            gutter_x = feedback_local_gutter_x.get(
                edge_id,
                min(
                    width - 16.0,
                    max(source[0], target[0])
                    + _NODE_WIDTH + _CORRIDOR_GUTTER_OFFSET,
                ),
            )
            source_span = (min(source_x, gutter_x), max(source_x, gutter_x))
            target_span = (min(target_x, gutter_x), max(target_x, gutter_x))
            for shift in (0, -4, 4, -8, 8, -12, 12, -16, 16, -20, 20, -24, 24):
                source_rail, target_rail = base_source + shift, base_target + shift
                proposed = (
                    (source_span[0], source_span[1], source_rail),
                    (target_span[0], target_span[1], target_rail),
                )
                proposed_gutter = (
                    gutter_x, min(source_rail, target_rail),
                    max(source_rail, target_rail),
                )
                if (
                    not source_gap[0] + 2 <= source_rail <= source_gap[1] - 2
                    or not target_gap[0] + 2 <= target_rail <= target_gap[1] - 2
                    or any(
                        min(right, other_right) - max(left, other_left) > 4
                        and abs(y - other_y) < 4
                        for left, right, y in proposed
                        for other_left, other_right, other_y in reserved_feedback_legs
                    )
                    or any(
                        abs(proposed_gutter[0] - peer_x) < 4
                        and min(proposed_gutter[2], peer_high)
                        - max(proposed_gutter[1], peer_low) > 4
                        for peer_x, peer_low, peer_high in reserved_feedback_gutters
                    )
                    or any(
                        left < box_right + 2 and right > box_left - 2
                        and box_top - 2 < y < box_bottom + 2
                        for left, right, y in proposed
                        for box_left, box_top, box_right, box_bottom in feedback_obstacles
                    )
                ):
                    continue
                if shift:
                    feedback_path_y[edge_id] = (source_rail, target_rail)
                    grouped_feedback_rail_replanned = True
                reserved_feedback_legs.extend(proposed)
                if proposed_gutter[2] - proposed_gutter[1] > 4:
                    reserved_feedback_gutters.append(proposed_gutter)
                break
            else:
                # The finite local search is exhausted. Promote this relation
                # before the existing, collision-checked outer side-port
                # planner runs; never render a rejected original rail.
                feedback_rail_exhausted = True
                feedback_outer_footer_ids.add(edge_id)
                feedback_footer_ids.add(edge_id)
                feedback_local_gutter_x.pop(edge_id, None)
                feedback_path_y.pop(edge_id, None)
                height = max(
                    height,
                    math.ceil(
                        feedback_base_bottom
                        + 112 + feedback_count * _FEEDBACK_LABEL_LANE_STEP
                    ),
                )

    # Reserve only as much extra edge gutter as crowded semantic feedback
    # footers require. All planning happens before constructing the SVG header
    # so an expanded canvas never clips a route or misstates its viewBox.
    outer_feedback_obstacles: Sequence[tuple[float, float, float, float]] = ()
    outer_feedback_obstacles_by_id: dict[
        str, Sequence[tuple[float, float, float, float]]
    ] = {}
    outer_feedback_parallel_slots: dict[str, int] = {}
    outer_feedback_ports_by_id: dict[
        str, tuple[float, float, float, float, float]
    ] = {}
    outer_peer_footer_label_x: dict[str, float] = {}
    if intent == "process" and feedback_outer_footer_ids:
        # Every outer-feedback return receives a unique global rail, even
        # when different or reversed endpoint pairs share the same footer.
        # Sorted semantic relation ids make allocation order-independent.
        for peer in feedback_edges:
            peer_id = str(peer["id"])
            if peer_id in feedback_outer_footer_ids:
                outer_feedback_parallel_slots[peer_id] = len(
                    outer_feedback_parallel_slots
                )
        # The original 80px path-only strip comfortably holds up to five
        # parallel rails. Grow only if there are more than five distinct
        # semantics sharing directed endpoints; never run the highest rail
        # through a semantic footer label.
        highest_parallel_slot = max(outer_feedback_parallel_slots.values(), default=0)
        if highest_parallel_slot > 4:
            height += 12 * (highest_parallel_slot - 4)
        packed_obstacles = (
            tuple(feedback_obstacles) if model["groups"]
            else tuple(occupied_boxes)
        )
        # Preserve every already accepted page geometry: exhaust the original
        # 33 width-only plans first. Only if all of those remain impossible,
        # restart from the same canvas and replan a non-outer footer label.
        # Replanning makes formerly sealed vertical corridors available
        # without ever relaxing card/label obstacle clearance.
        initial_outer_width, initial_outer_height = width, height
        for attempt in range(66):
            if attempt == 33:
                width, height = initial_outer_width, initial_outer_height
            extra_gutter = attempt % 33
            relayout_phase = attempt >= 33
            peer_feedback_boxes: list[tuple[float, float, float, float]] = []
            peer_horizontal_strokes: list[tuple[float, float, float, float]] = []
            peer_footer_trial: dict[str, float] = {}
            peer_layout_safe = True
            for peer in feedback_edges:
                peer_id = str(peer["id"])
                if peer_id in feedback_outer_footer_ids:
                    continue
                peer_source = positions[str(peer["from"])]
                peer_target = positions[str(peer["to"])]
                peer_metrics = _edge_label_metrics(peer, positions, intent)
                peer_slot = feedback_slots[peer_id]
                if peer_id in self_loop_lanes:
                    peer_lane = self_loop_lanes[peer_id]
                elif feedback_count > 1:
                    peer_lane = int(
                        (peer_slot - (feedback_count - 1) / 2)
                        * _PROCESS_LANE_STEP
                    )
                else:
                    peer_lane = (
                        (lane_ranks[peer_id] % 5) - 2
                    ) * _PROCESS_LANE_STEP
                peer_footer_y = (
                    feedback_base_bottom
                    + 10
                    + peer_slot * _FEEDBACK_LABEL_LANE_STEP
                    + peer_metrics.height / 2
                    if feedback_count > 1 or peer_id in feedback_footer_ids
                    else None
                )
                peer_path, peer_x, peer_y, _ = _edge_geometry(
                    peer_source,
                    peer_target,
                    self_loop=peer["from"] == peer["to"],
                    lane=peer_lane,
                    kind="feedback",
                    canvas_width=width,
                    canvas_height=height,
                    intent=intent,
                    process_row_gap=process_row_gap,
                    label_width=peer_metrics.width,
                    label_height=peer_metrics.height,
                    feedback_label_y=peer_footer_y,
                    max_node_bottom=max(
                        y + _NODE_HEIGHT for _, y in positions.values()
                    ),
                    preserve_same_row_feedback_footer=(
                        peer["from"] != peer["to"]
                        and _preserve_same_row_process_feedback_return(
                            peer_source, peer_target, positions
                        )
                    ),
                    feedback_path_y=feedback_path_y.get(peer_id),
                    feedback_path_footer=peer_id in feedback_path_footer_ids,
                    feedback_local_gutter_x=feedback_local_gutter_x.get(peer_id),
                )
                # Non-outer feedback paths keep their local strokes. Reserve
                # actual axis-aligned C endpoint stubs and L rails before
                # placing any outer label; a label cannot hide a peer line.
                tokens = re.findall(r"[MCL]|-?\d+(?:\.\d+)?", peer_path)
                cursor = None
                index = 0
                while index < len(tokens):
                    command = tokens[index]
                    index += 1
                    count = 6 if command == "C" else 2
                    values = [float(v) for v in tokens[index:index + count]]
                    index += count
                    endpoint = (values[-2], values[-1])
                    if cursor is not None:
                        if command == "L":
                            if abs(cursor[1] - endpoint[1]) < 0.01:
                                peer_horizontal_strokes.append((
                                    min(cursor[0], endpoint[0]),
                                    endpoint[1] - 1,
                                    max(cursor[0], endpoint[0]),
                                    endpoint[1] + 1,
                                ))
                            elif abs(cursor[0] - endpoint[0]) < 0.01:
                                peer_horizontal_strokes.append((
                                    endpoint[0] - 1,
                                    min(cursor[1], endpoint[1]),
                                    endpoint[0] + 1,
                                    max(cursor[1], endpoint[1]),
                                ))
                        elif command == "C":
                            xs = (cursor[0], values[0], values[2], endpoint[0])
                            if max(xs) - min(xs) < 0.01:
                                peer_horizontal_strokes.append((
                                    cursor[0] - 1,
                                    min(cursor[1], values[1], values[3], endpoint[1]),
                                    cursor[0] + 1,
                                    max(cursor[1], values[1], values[3], endpoint[1]),
                                ))
                    cursor = endpoint
                peer_x = min(
                    max(peer_x, peer_metrics.width / 2 + 8),
                    width - peer_metrics.width / 2 - 8,
                )
                if relayout_phase and peer_footer_y is not None and extra_gutter:
                    # The formerly fixed non-outer feedback footer label may
                    # seal an otherwise free source-to-footer vertical gutter.
                    # Try a bounded rightward relayout only after the accepted
                    # initial geometry fails; widened width is not by itself
                    # a change to any occupied rectangle.
                    peer_x = min(
                        peer_x + 16.0 * extra_gutter,
                        width - peer_metrics.width / 2 - 8,
                    )
                peer_box = (
                    peer_x - peer_metrics.width / 2,
                    peer_y - peer_metrics.height / 2,
                    peer_x + peer_metrics.width / 2,
                    peer_y + peer_metrics.height / 2,
                )
                if relayout_phase and extra_gutter and any(
                    peer_box[0] < right + 3.5
                    and peer_box[2] > left - 3.5
                    and peer_box[1] < bottom + 3.5
                    and peer_box[3] > top - 3.5
                    for left, top, right, bottom in (
                        *packed_obstacles, *peer_feedback_boxes
                    )
                ):
                    peer_layout_safe = False
                    break
                peer_feedback_boxes.append(peer_box)
                if peer_footer_y is not None:
                    peer_footer_trial[peer_id] = peer_x
            if not peer_layout_safe:
                width += 16
                continue

            common_obstacles = (*packed_obstacles, *peer_feedback_boxes)
            # Reserve every global rail below the lowest real relation label,
            # including a long-branch pack that extends below its cards.
            lowest_bottom = max(
                (bottom for _, _, _, bottom in common_obstacles),
                default=0.0,
            )
            height = max(
                height,
                math.ceil(
                    lowest_bottom + 40 + 12 * highest_parallel_slot
                ),
            )
            # Side-port labels themselves can move when another footer forces
            # a different free gutter. Iterate against all *other* planned
            # labels until positions agree; never trust an obsolete candidate
            # geometry or the model's original edge declaration order.
            outer_labels: dict[str, tuple[float, float, float, float]] = {}
            solved: dict[str, Sequence[tuple[float, float, float, float]]] = {}
            solved_ports: dict[
                str, tuple[float, float, float, float, float]
            ] = {}
            stable = False
            for _ in range(12):
                future_labels = {}
                future_routes = {}
                future_ports: dict[
                    str, tuple[float, float, float, float, float]
                ] = {}
                # Fixed local feedback L legs and straight C stubs already
                # occupy the canvas. Reserve them against outer sideport
                # gutters as well as against footer labels.
                reserved_verticals: list[tuple[float, float, float]] = [
                    ((left + right) / 2, top, bottom)
                    for left, top, right, bottom in peer_horizontal_strokes
                    if right - left <= 2.1 and bottom - top > 4
                ]
                for edge in feedback_edges:
                    edge_id = str(edge["id"])
                    if edge_id not in feedback_outer_footer_ids:
                        continue
                    metrics = _edge_label_metrics(edge, positions, intent)
                    # Reuse already updated labels from this same stable
                    # id-ordered pass. Pure simultaneous (Jacobi) updates can
                    # alternate between two otherwise feasible configurations
                    # indefinitely, yielding a false "no safe route" on valid
                    # grouped diagrams. Preserve the fixed-point equality
                    # check: a one-pass approximation is not merge evidence.
                    proposed_labels = {**outer_labels, **future_labels}
                    blockers = (
                        *common_obstacles,
                        *(
                            proposed_labels[other_id]
                            for other_id in sorted(proposed_labels)
                            if other_id != edge_id
                        ),
                    )
                    ports = _safe_process_feedback_outer_ports(
                        positions[str(edge["from"])],
                        positions[str(edge["to"])],
                        canvas_width=width,
                        canvas_height=height,
                        label_width=metrics.width,
                        obstacles=blockers,
                        label_only_obstacles=peer_horizontal_strokes,
                        parallel_route_slot=outer_feedback_parallel_slots[edge_id],
                        reserved_verticals=reserved_verticals,
                        label_y=(
                            feedback_base_bottom + 10
                            + feedback_slots[edge_id] * _FEEDBACK_LABEL_LANE_STEP
                            + metrics.height / 2
                        ),
                        label_height=metrics.height,
                    )
                    if ports is None:
                        break
                    future_ports[edge_id] = ports
                    footer_y = (
                        height - 28.0
                        - 12 * outer_feedback_parallel_slots[edge_id]
                    )
                    port_y_offset = _process_feedback_parallel_port_y_offset(
                        outer_feedback_parallel_slots[edge_id]
                    )
                    for endpoint_y, gutter_x in (
                        (
                            positions[str(edge["from"])][1]
                            + _NODE_HEIGHT / 2 + port_y_offset,
                            ports[1],
                        ),
                        (
                            positions[str(edge["to"])][1]
                            + _NODE_HEIGHT / 2 + port_y_offset,
                            ports[2],
                        ),
                    ):
                        reserved_verticals.append((
                            gutter_x,
                            min(endpoint_y, footer_y),
                            max(endpoint_y, footer_y),
                        ))
                    label_x = ports[4]
                    label_y = (
                        feedback_base_bottom
                        + 10
                        + feedback_slots[edge_id] * _FEEDBACK_LABEL_LANE_STEP
                        + metrics.height / 2
                    )
                    future_labels[edge_id] = (
                        label_x - metrics.width / 2,
                        label_y - metrics.height / 2,
                        label_x + metrics.width / 2,
                        label_y + metrics.height / 2,
                    )
                    future_routes[edge_id] = blockers
                if len(future_labels) != len(feedback_outer_footer_ids):
                    break
                # Each newly planned route avoids earlier peer labels; each
                # new label avoids every reserved earlier route segment.
                # A complete first pass is therefore geometrically closed
                # without requiring potentially oscillating Jacobi iterations.
                if not outer_labels or future_labels == outer_labels:
                    solved = future_routes
                    solved_ports = future_ports
                    stable = True
                    break
                outer_labels = future_labels
            if stable:
                outer_feedback_obstacles = common_obstacles
                outer_feedback_obstacles_by_id = solved
                outer_feedback_ports_by_id = solved_ports
                outer_peer_footer_label_x = peer_footer_trial
                break
            width += 16
        else:
            # Width-only replans cannot free a target trapped between dense
            # group columns. Retry with actual free horizontal group space.
            # The finite limit derives from card and edge-label geometry,
            # never a constant number of attempts unrelated to the model.
            if regions and (
                len(regions) > 1
                or len({x for x, _ in positions.values()}) > 1
            ):
                clearance_budget = 2 * _NODE_WIDTH + sum(
                    _edge_label_metrics(edge, positions, intent).width + 16
                    for edge in model["edges"]
                )
                next_gap = (
                    8 if _process_group_gap_extra == 0
                    else 2 * _process_group_gap_extra
                )
                if next_gap <= clearance_budget:
                    return render_native_diagram(
                        value, _process_group_gap_extra=next_gap
                    )
            # Never silently reuse a route through a card or relation label.
            raise ValueError("no collision-free process feedback side-port route")

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

    # Group-gap fallback and parallel feedback peers can cross other strokes.
    # Use a stable painter order only in those cases; preserve older SVG output.
    paint_edges = (
        sorted(model["edges"], key=lambda edge: str(edge["id"]))
        if (
            _process_group_gap_extra
            or has_parallel_feedback_peers
            or grouped_feedback_rail_replanned
        )
        else model["edges"]
    )
    # Reserve distinct physical entrances for semantics sharing one target:
    # row gutters approach its top, as do downward process branches. Use the
    # existing target-port override during original path planning; no SVG
    # paint-order trick or global postprocessor can recover hidden stems.
    shared_target_port_x: dict[str, float] = {}
    shared_target_route_y: dict[str, tuple[float, float]] = {}
    shared_target_label_y: dict[str, float] = {}
    if intent == "process" and model["groups"]:
        edges_by_target: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for edge in model["edges"]:
            if str(edge["kind"]) != "feedback" and edge["from"] != edge["to"]:
                edges_by_target[str(edge["to"])].append(edge)
        for target_id in sorted(edges_by_target):
            target = positions[target_id]
            candidates = edges_by_target[target_id]
            branches = sorted(
                (
                    edge for edge in candidates
                    if positions[str(edge["from"])][1] < target[1]
                    and positions[str(edge["from"])][0] != target[0]
                ),
                key=lambda edge: str(edge["id"]),
            )
            row_gutters = sorted(
                (
                    edge for edge in candidates
                    if positions[str(edge["from"])][1] == target[1]
                    and str(edge["id"]) in process_branch_gutter_x
                ),
                key=lambda edge: str(edge["id"]),
            )
            # Same-column vertical relations retain their established center
            # entrance. Otherwise preserve one existing long-branch center
            # route, preferring the longest accepted semantic relation: only
            # its competing peers need a new entrance port.
            vertical_center = any(
                positions[str(edge["from"])][1] < target[1]
                and positions[str(edge["from"])][0] == target[0]
                for edge in candidates
            )
            center_branch_id = None
            if not vertical_center and branches and (
                len(branches) + len(row_gutters) > 1
            ):
                center_branch_id = str(max(
                    branches,
                    key=lambda edge: (
                        target[1] - positions[str(edge["from"])][1],
                        str(edge["id"]),
                    ),
                )["id"])
            moving = sorted(
                (
                    edge for edge in (*branches, *row_gutters)
                    if str(edge["id"]) != center_branch_id
                ),
                key=lambda edge: str(edge["id"]),
            )
            fixed_center = vertical_center or center_branch_id is not None
            if len(moving) + int(fixed_center) < 2:
                continue
            count = len(moving) + int(fixed_center)
            offsets = [
                _NODE_WIDTH * (index + 1) / (count + 1)
                for index in range(count)
            ]
            if fixed_center:
                center_slot = min(
                    range(len(offsets)),
                    key=lambda index: (abs(offsets[index] - _NODE_WIDTH / 2), index),
                )
                del offsets[center_slot]
            for edge, offset in zip(moving, offsets):
                shared_target_port_x[str(edge["id"])] = target[0] + offset
            if len(row_gutters) > 1:
                # Reuse actual free gap height rather than stacking every
                # same-row return on the historical single midpoint rail.
                rail_step = min(
                    8.0, (process_row_gap - 8.0) / (len(row_gutters) - 1)
                )
                for index, edge in enumerate(row_gutters):
                    edge_id = str(edge["id"])
                    line_y = (
                        target[1] - process_row_gap / 2
                        + (index - (len(row_gutters) - 1) / 2) * rail_step
                    )
                    shared_target_route_y[edge_id] = (line_y, line_y)
                    if target[1] != min(y for _, y in positions.values()):
                        # Keep accepted labels fixed while only rails change.
                        shared_target_label_y[edge_id] = (
                            target[1] - process_row_gap / 2
                        )

    def render_planned_edge(
        edge: Mapping[str, Any],
        *,
        label_x_override: float | None = None,
        route_y_override: float | tuple[float, float] | None = None,
        label_position_override: tuple[float, float] | None = None,
        card_target_port_x: float | None = None,
        card_source_port_x: float | None = None,
        card_side_route_path: str | None = None,
    ) -> list[str]:
        return _render_edge(
                edge,
                positions,
                lane_rank=lane_ranks[str(edge["id"])],
                canvas_width=width,
                canvas_height=height,
                intent=intent,
                process_row_gap=process_row_gap,
                non_process_row_gap=non_process_row_gap,
                long_branch_slot=long_branch_slots.get(str(edge["id"])),
                long_branch_count=effective_long_branch_count,
                long_branch_route_count=len(long_branch_slots),
                long_branch_label_y=long_branch_label_y.get(str(edge["id"])),
                anchored_branch_gutter_x=anchored_branch_gutter_x.get(str(edge["id"])),
                long_vertical_gutter_x=long_vertical_gutter_x.get(str(edge["id"])),
                long_vertical_label_y=long_vertical_label_y.get(str(edge["id"])),
                long_vertical_label_x=long_vertical_label_x.get(str(edge["id"])),
                process_branch_gutter_x=process_branch_gutter_x.get(str(edge["id"])),
                process_adjacent_slot=process_adjacent_slot.get(str(edge["id"])),
                process_adjacent_count=process_adjacent_count.get(str(edge["id"]), 0),
                process_adjacent_label_x=(
                    label_x_override
                    if label_x_override is not None
                    else process_adjacent_label_x.get(str(edge["id"]))
                ),
                process_adjacent_label_y=process_adjacent_label_y.get(
                    str(edge["id"]), shared_target_label_y.get(str(edge["id"]))
                ),
                process_adjacent_route_y=(
                    route_y_override
                    if route_y_override is not None
                    else shared_target_route_y.get(
                        str(edge["id"]),
                        process_adjacent_route_y.get(str(edge["id"])),
                    )
                ),
                process_same_row_source_port_x=card_source_port_x,
                process_same_row_target_port_x=(
                    card_target_port_x if card_target_port_x is not None
                    else process_adjacent_target_port_x.get(
                        str(edge["id"]), shared_target_port_x.get(str(edge["id"]))
                    )
                ),
                row_corridor_label_x=row_corridor_label_x.get(str(edge["id"])),
                narrative_parallel_gutter_x=narrative_parallel_gutter_x.get(str(edge["id"])),
                narrative_self_loop_gutter_x=narrative_self_loop_gutter_x.get(str(edge["id"])),
                generic_self_loop_gutter_x=generic_self_loop_gutter_x.get(str(edge["id"])),
                self_loop_lane=self_loop_lanes.get(str(edge["id"])),
                feedback_slot=feedback_slots.get(str(edge["id"])),
                feedback_count=feedback_count,
                feedback_base_bottom=feedback_base_bottom,
                force_feedback_footer=str(edge["id"]) in feedback_footer_ids,
                feedback_footer_label_x_override=outer_peer_footer_label_x.get(
                    str(edge["id"])
                ),
                feedback_path_y=feedback_path_y.get(str(edge["id"])),
                force_feedback_path_footer=(
                    str(edge["id"]) in feedback_path_footer_ids
                ),
                feedback_local_gutter_x=feedback_local_gutter_x.get(str(edge["id"])),
                feedback_outer_footer=(
                    str(edge["id"]) in feedback_outer_footer_ids
                ),
                feedback_outer_parallel_slot=outer_feedback_parallel_slots.get(
                    str(edge["id"]), 0
                ),
                feedback_outer_preplanned_ports=outer_feedback_ports_by_id.get(
                    str(edge["id"])
                ),
                feedback_outer_obstacles=outer_feedback_obstacles_by_id.get(
                    str(edge["id"]), outer_feedback_obstacles
                ),
                final_label_override=label_position_override,
                process_row_card_side_path=card_side_route_path,
            )

    # Keep the established renderer byte-for-byte for all unaffected edges.
    # Only an actual cross-card same-row curve needs a second, label-aware pass.
    planned_edge_lines = {
        str(edge["id"]): render_planned_edge(edge) for edge in paint_edges
    }
    if intent == "process" and model["groups"]:
        import xml.etree.ElementTree as ET

        def planned_svg_parts(
            edge_lines: list[str],
        ) -> tuple[str, tuple[float, float, float, float]]:
            group = ET.fromstring("\n".join(edge_lines))
            route = next(
                element.attrib["d"]
                for element in group.iter("path")
                if element.attrib.get("fill") == "none"
            )
            label = next(
                element
                for element in group.iter("rect")
                if element.attrib.get("rx") == "9"
                and element.attrib.get("fill") == "#f8fafc"
            )
            return route, tuple(
                float(label.attrib[name]) for name in ("x", "y", "width", "height")
            )

        candidates: list[Mapping[str, Any]] = []
        for edge in sorted(paint_edges, key=lambda item: str(item["id"])):
            if str(edge["kind"]) == "feedback" or edge["from"] == edge["to"]:
                continue
            source = positions[str(edge["from"])]
            target = positions[str(edge["to"])]
            if source[1] != target[1]:
                continue
            if process_branch_gutter_x.get(str(edge["id"])) is not None:
                continue
            start_x, end_x = sorted((source[0], target[0]))
            in_between = (
                (node_id, (float(node_x), float(node_y),
                           float(_NODE_WIDTH), float(_NODE_HEIGHT)))
                for node_id, (node_x, node_y) in positions.items()
                if node_id not in {str(edge["from"]), str(edge["to"])}
                and node_x >= start_x + _NODE_WIDTH
                and node_x + _NODE_WIDTH <= end_x
                and node_y < source[1] + _NODE_HEIGHT
                and node_y + _NODE_HEIGHT > source[1]
            )
            foreign_cards = tuple(in_between)
            if not foreign_cards:
                continue
            old_path, _ = planned_svg_parts(planned_edge_lines[str(edge["id"])])
            if any(
                _process_svg_path_hits_box(old_path, card, padding=0.0)
                for _, card in foreign_cards
            ):
                candidates.append(edge)

        if candidates:
            # A newly drawn card-safe detour can cross an existing stroke.
            # Preserve stable SVG paint semantics under input reordering,
            # as for the established group-gap and feedback-peer fallbacks.
            paint_edges = sorted(paint_edges, key=lambda edge: str(edge["id"]))
            layouts = {
                edge_id: planned_svg_parts(fragment)
                for edge_id, fragment in planned_edge_lines.items()
            }
            card_boxes = {
                node_id: (float(x), float(y),
                          float(_NODE_WIDTH), float(_NODE_HEIGHT))
                for node_id, (x, y) in positions.items()
            }
            # A detour must not cover physical rails already emitted by any
            # other planner (including process-row-gutter), not just earlier
            # card detours. Ignore initial layouts of candidate edges because
            # their known-invalid routes are replaced below.
            def horizontal_strokes(
                path: str,
            ) -> list[tuple[float, float, float]]:
                tokens = re.findall(r"[MLC]|-?\d+(?:\.\d+)?", path)
                cursor: tuple[float, float] | None = None
                spans: list[tuple[float, float, float]] = []
                index = 0
                while index < len(tokens):
                    command = tokens[index]
                    index += 1
                    arity = 6 if command == "C" else 2
                    if command not in {"M", "L", "C"} or index + arity > len(tokens):
                        break
                    coords = tuple(float(v) for v in tokens[index:index + arity])
                    index += arity
                    endpoint = (coords[-2], coords[-1])
                    if (
                        command == "L"
                        and cursor is not None
                        and abs(cursor[1] - endpoint[1]) < 0.01
                        and abs(cursor[0] - endpoint[0]) > 4
                    ):
                        spans.append((
                            cursor[1], min(cursor[0], endpoint[0]),
                            max(cursor[0], endpoint[0]),
                        ))
                    cursor = endpoint
                return spans

            # A shifted target port must also leave already emitted vertical
            # stems visible, including straight cubic endpoint segments.
            def vertical_strokes(
                path: str,
            ) -> list[tuple[float, float, float]]:
                tokens = re.findall(r"[MLC]|-?\d+(?:\.\d+)?", path)
                cursor: tuple[float, float] | None = None
                spans: list[tuple[float, float, float]] = []
                index = 0
                while index < len(tokens):
                    command = tokens[index]
                    index += 1
                    arity = 6 if command == "C" else 2
                    if command not in {"M", "L", "C"} or index + arity > len(tokens):
                        break
                    coords = tuple(float(v) for v in tokens[index:index + arity])
                    index += arity
                    endpoint = (coords[-2], coords[-1])
                    if cursor is not None and command in {"L", "C"}:
                        points = (
                            (cursor, endpoint) if command == "L" else (
                                cursor, (coords[0], coords[1]),
                                (coords[2], coords[3]), endpoint
                            )
                        )
                        if all(abs(x - cursor[0]) < 0.01 for x, _ in points):
                            low = min(y for _, y in points)
                            high = max(y for _, y in points)
                            if high - low > 4:
                                spans.append((cursor[0], low, high))
                    cursor = endpoint
                return spans

            candidate_ids = {str(edge["id"]) for edge in candidates}
            reserved_detour_rails = [
                span
                for other_id, (other_path, _) in layouts.items()
                if other_id not in candidate_ids
                for span in horizontal_strokes(other_path)
            ]
            reserved_detour_verticals = [
                span
                for other_id, (other_path, _) in layouts.items()
                if other_id not in candidate_ids
                for span in vertical_strokes(other_path)
            ]
            # Every accepted new detour also reserves its physical rails and stems.
            for edge in candidates:
                edge_id = str(edge["id"])
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                original_box = layouts[edge_id][1]
                left, top, label_width, label_height = original_box
                own_center = left + label_width / 2
                source_center = source[0] + _NODE_WIDTH / 2
                target_center = target[0] + _NODE_WIDTH / 2
                label_step = label_width / 2 + 8
                external_label_center = max(
                    (
                        other_box[0] + other_box[2]
                        for other_id, (_, other_box) in layouts.items()
                        if other_id != edge_id
                    ),
                    default=own_center,
                ) + label_step
                label_centers = tuple(dict.fromkeys((
                    own_center,
                    own_center - label_step,
                    own_center + label_step,
                    source_center, target_center,
                    external_label_center,
                    width - _PAGE_MARGIN - label_width / 2,
                )))
                accepted = False
                source_stem_fallback = None
                source_port_fallback = None
                for direction in (-1, 1):
                    corridor = _process_row_corridor_bounds(
                        source[1], positions, direction=direction
                    )
                    if corridor is None:
                        if (
                            direction < 0
                            and source[1] == min(y for _, y in positions.values())
                        ):
                            # The first row has no preceding card, but the
                            # existing gap below group headings is a real
                            # short rail. Stay below their title text and
                            # above the card tops, and check all SVG labels.
                            corridor = (
                                float(max(_CONTENT_TOP + 44, source[1] - process_row_gap)),
                                float(source[1]),
                            )
                        else:
                            # The final row can reuse the existing footer.
                            bottom = source[1] + _NODE_HEIGHT
                            if (
                                direction != 1
                                or any(
                                    node_y + _NODE_HEIGHT > bottom
                                    for _, node_y in positions.values()
                                )
                                or bottom + 4 >= height - 8
                            ):
                                continue
                            corridor = (
                                float(bottom),
                                float(min(bottom + process_row_gap, height - 8)),
                            )
                    low, high = map(float, corridor)
                    offsets = (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0)
                    ys = (
                        (low + high) / 2,
                        *(high - offset for offset in offsets),
                        *(low + offset for offset in offsets),
                    )
                    port = (
                        float(source[1]) if direction < 0
                        else float(source[1] + _NODE_HEIGHT)
                    )
                    # A pinned label can occupy the target's center top
                    # port even when the rail is clear. Try the straight
                    # part of that same card's top boundary before failing.
                    # No peer route/label or group geometry is displaced.
                    target_ports = tuple(sorted(
                        dict.fromkeys((
                            target_center,
                            target[0] + 16.0,
                            target[0] + _NODE_WIDTH - 16.0,
                        )),
                        # Shared endpoints may use the center only when no
                        # clear alternative exists. Try physically free ports
                        # first rather than shrinking a hidden final stem.
                        key=lambda x: any(
                            abs(x - peer_x) < 4.0
                            and peer_low - 2.0 <= port <= peer_high + 2.0
                            for peer_x, peer_low, peer_high in reserved_detour_verticals
                        ),
                    ))
                    for source_port_x, target_port_x, channel_y in (
                        (source_x, port_x, y)
                        # Prefer the accepted centered source entrance;
                        # try both in-card insets only when it is obstructed.
                        for source_x in (
                            source_center, source[0] + 16.0,
                            source[0] + _NODE_WIDTH - 16.0,
                        )
                        for port_x in target_ports for y in ys
                    ):
                        if not low + 1.5 < channel_y < high - 1.5:
                            continue
                        candidate_verticals = (
                            (source_port_x, min(port, channel_y), max(port, channel_y)),
                            (target_port_x, min(port, channel_y), max(port, channel_y)),
                        )
                        source_stem_overlap = any(
                            abs(x - peer_x) < 4.0
                            and min(high, peer_high) - max(low, peer_low) > 4.0
                            for x, low, high in candidate_verticals[:1]
                            for peer_x, peer_low, peer_high in reserved_detour_verticals
                        )
                        # A candidate may move either card entrance without
                        # touching peer routes. Reject target overlap now;
                        # seek a clean source inset before accepting a
                        # fallback with overlapping source stems.
                        if any(
                            abs(x - peer_x) < 4.0
                            and min(high, peer_high) - max(low, peer_low) > 4.0
                            for x, low, high in candidate_verticals[1:]
                            for peer_x, peer_low, peer_high in reserved_detour_verticals
                        ):
                            continue
                        rail_left = min(source_port_x, target_port_x)
                        rail_right = max(source_port_x, target_port_x)
                        if any(
                            abs(channel_y - peer_y) < 4.0
                            and min(rail_right, peer_right)
                            - max(rail_left, peer_left) > 4.0
                            for peer_y, peer_left, peer_right in reserved_detour_rails
                        ):
                            continue
                        path = (
                            f"M {source_port_x:.1f} {port:.1f} "
                            f"L {source_port_x:.1f} {channel_y:.1f} "
                            f"L {target_port_x:.1f} {channel_y:.1f} "
                            f"L {target_port_x:.1f} {port:.1f}"
                        )
                        if any(
                            _process_svg_path_hits_box(path, card)
                            for node_id, card in card_boxes.items()
                            if node_id not in {
                                str(edge["from"]), str(edge["to"])
                            }
                        ):
                            continue
                        # A valid path can have no available label slot at
                        # its old ordinate. Pack only this edge's actual label
                        # into the same row corridor; never move peer labels.
                        label_y_centers = (
                            top + label_height / 2,
                            channel_y,
                            channel_y - label_height / 2 - 4,
                            channel_y + label_height / 2 + 4,
                        )
                        trial_label_centers = label_centers
                        if (
                            direction < 0
                            and source[1] == min(y for _, y in positions.values())
                        ):
                            # The first row's top rail lies below the group
                            # titles. A label on the old mid-card ordinate
                            # otherwise escapes all the way beyond the final
                            # group. Prefer an actual inter-card column gap
                            # at a readable distance above this new rail.
                            row_cards = sorted({
                                (float(x), float(x + _NODE_WIDTH))
                                for x, y in positions.values()
                                if y == source[1]
                            })
                            intergroup_centers = sorted(
                                (
                                    (right + next_left) / 2
                                    for (_, right), (next_left, _) in zip(
                                        row_cards, row_cards[1:]
                                    )
                                    if next_left - right >= label_width + 8
                                ),
                                key=lambda x: (abs(x - own_center), x),
                            )
                            trial_label_centers = tuple(dict.fromkeys((
                                *intergroup_centers, *label_centers,
                            )))
                            label_y_centers = (
                                channel_y - label_height / 2 - 4,
                                top + label_height / 2,
                                channel_y + label_height / 2 + 4,
                                channel_y,
                            )
                        for candidate_x, candidate_y in (
                            (x, y)
                            for y in label_y_centers
                            for x in trial_label_centers
                        ):
                            label_box = (
                                candidate_x - label_width / 2,
                                candidate_y - label_height / 2,
                                label_width, label_height,
                            )
                            if (
                                label_box[0] < 8
                                or label_box[0] + label_width > width - 8
                                or label_box[1] < 112
                                or label_box[1] + label_height > height - 8
                            ):
                                continue
                            if _process_svg_path_hits_box(path, label_box):
                                continue
                            if any(
                                _process_svg_path_hits_box(path, other_box)
                                for other_id, (_, other_box) in layouts.items()
                                if other_id != edge_id
                            ):
                                continue
                            if any(
                                _process_svg_path_hits_box(other_path, label_box)
                                for other_id, (other_path, _) in layouts.items()
                                if other_id != edge_id
                            ):
                                continue
                            if any(
                                label_box[0] < other_box[0] + other_box[2] + 2
                                and other_box[0] < label_box[0] + label_width + 2
                                and label_box[1] < other_box[1] + other_box[3] + 2
                                and other_box[1] < label_box[1] + label_height + 2
                                for other_id, (_, other_box) in layouts.items()
                                if other_id != edge_id
                            ):
                                continue
                            if any(
                                label_box[0] < bx + bw + 1.5
                                and bx - 1.5 < label_box[0] + label_width
                                and label_box[1] < by + bh + 1.5
                                and by - 1.5 < label_box[1] + label_height
                                for bx, by, bw, bh in card_boxes.values()
                            ):
                                continue
                            rerendered = render_planned_edge(
                                edge,
                                label_x_override=candidate_x,
                                route_y_override=channel_y,
                                label_position_override=(candidate_x, candidate_y),
                                card_target_port_x=target_port_x,
                                card_source_port_x=source_port_x,
                            )
                            reroute, rendered_box = planned_svg_parts(rerendered)
                            if (
                                reroute != path
                                or any(abs(a - b) > 0.01 for a, b in zip(
                                    rendered_box, label_box
                                ))
                            ):
                                continue
                            if source_stem_overlap:
                                # Remember an otherwise valid route, but first
                                # seek an overlap-free rail in either corridor.
                                if source_stem_fallback is None:
                                    source_stem_fallback = (
                                        reroute, rendered_box, rerendered,
                                        channel_y, rail_left, rail_right,
                                        candidate_verticals,
                                    )
                                continue
                            if source_port_x != source_center:
                                # A safe centered port in the other corridor
                                # retains the accepted geometry. Use side
                                # insets only after both center routes fail.
                                if source_port_fallback is None:
                                    source_port_fallback = (
                                        reroute, rendered_box, rerendered,
                                        channel_y, rail_left, rail_right,
                                        candidate_verticals,
                                    )
                                continue
                            layouts[edge_id] = reroute, rendered_box
                            planned_edge_lines[edge_id] = rerendered
                            reserved_detour_rails.append((
                                channel_y, rail_left, rail_right,
                            ))
                            reserved_detour_verticals.extend(candidate_verticals)
                            accepted = True
                            break
                        if accepted:
                            break
                    if accepted:
                        break
                # Only when existing centered and inset card detours cannot
                # use either row gap, try the adjacent intergroup sideports.
                if (
                    not accepted and source_port_fallback is None
                    and source_stem_fallback is None
                ):
                    columns = sorted({x for x, _ in positions.values()})
                    source_col = columns.index(source[0])
                    target_col = columns.index(target[0])
                    if abs(source_col - target_col) >= 2:
                        backward = source_col > target_col
                        start_side = float(
                            source[0] if backward else source[0] + _NODE_WIDTH
                        )
                        end_side = float(
                            target[0] + _NODE_WIDTH if backward else target[0]
                        )
                        start_neighbor = (
                            columns[source_col - 1] + _NODE_WIDTH
                            if backward else columns[source_col + 1]
                        )
                        end_neighbor = (
                            columns[target_col + 1] if backward
                            else columns[target_col - 1] + _NODE_WIDTH
                        )
                        start_gap = (start_side + start_neighbor) / 2
                        end_gap = (end_side + end_neighbor) / 2
                        center_port_y = float(source[1] + _NODE_HEIGHT / 2)
                        # The center side-port is preferred, but another peer
                        # may already own that exact row ordinate.
                        port_ys = (
                            center_port_y,
                            center_port_y - 8.0,
                            center_port_y + 8.0,
                            center_port_y - 16.0,
                            center_port_y + 16.0,
                        )
                        start_label_x = (start_side + start_gap) / 2
                        end_label_x = (end_side + end_gap) / 2
                        # The label midpoint may be just 0.5 px from the
                        # source/target card. Keep it first, then shift only
                        # 3 px into the free side gap to honor the existing
                        # 1.5 px card-clearance budget.
                        # Wrapped labels fit a genuine inter-card gap at
                        # its midpoint, not a quarter-gap candidate. A label
                        # wider than that gap can reuse the existing outer
                        # label slot instead of making a valid model fail.
                        label_xs = (
                            start_label_x, end_label_x,
                            start_label_x + (3.0 if start_gap > start_side else -3.0),
                            end_label_x + (3.0 if end_gap > end_side else -3.0),
                            *(
                                (start_gap,)
                                if abs(start_neighbor - start_side) >= label_width + 8
                                else ()
                            ),
                            *(
                                (end_gap,)
                                if abs(end_neighbor - end_side) >= label_width + 8
                                else ()
                            ),
                            external_label_center,
                            width - _PAGE_MARGIN - label_width / 2,
                        )
                        for gap_direction, port_y in (
                            (direction, port)
                            for port in port_ys
                            for direction in (-1, 1)
                        ):
                            bounds = _process_row_corridor_bounds(
                                source[1], positions, direction=gap_direction
                            )
                            if bounds is None:
                                continue
                            low, high = map(float, bounds)
                            label_ys = (
                                port_y - label_height - 18,
                                port_y + label_height + 18,
                                (low + high) / 2,
                            )
                            offsets = (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0)
                            rails = (
                                (low + high) / 2,
                                *(high - offset for offset in offsets),
                                *(low + offset for offset in offsets),
                            )
                            for side_y in rails:
                                if not low + 1.5 < side_y < high - 1.5:
                                    continue
                                side_path = (
                                    f"M {start_side:.1f} {port_y:.1f} "
                                    f"L {start_gap:.1f} {port_y:.1f} "
                                    f"L {start_gap:.1f} {side_y:.1f} "
                                    f"L {end_gap:.1f} {side_y:.1f} "
                                    f"L {end_gap:.1f} {port_y:.1f} "
                                    f"L {end_side:.1f} {port_y:.1f}"
                                )
                                horizontal = horizontal_strokes(side_path)
                                vertical = vertical_strokes(side_path)
                                if any(
                                    abs(y - other_y) < 4
                                    and min(right, other_right)
                                    - max(left, other_left) > 4
                                    for y, left, right in horizontal
                                    for other_y, other_left, other_right
                                    in reserved_detour_rails
                                ):
                                    continue
                                if any(
                                    abs(x - other_x) < 4
                                    and min(high_y, other_high)
                                    - max(low_y, other_low) > 4
                                    for x, low_y, high_y in vertical
                                    for other_x, other_low, other_high
                                    in reserved_detour_verticals
                                ):
                                    continue
                                if any(
                                    _process_svg_path_hits_box(side_path, box)
                                    for node_id, box in card_boxes.items()
                                    if node_id not in {
                                        str(edge["from"]), str(edge["to"])
                                    }
                                ) or any(
                                    _process_svg_path_hits_box(side_path, box)
                                    for other_id, (_, box) in layouts.items()
                                    if other_id != edge_id
                                ):
                                    continue
                                # Rectangular reservations of straight L
                                # spans do not cover curved C peer strokes.
                                # Check the actual peer Bezier hull against
                                # each 3px-wide physical detour segment too.
                                curve_peer_paths = (
                                    path for other_id, (path, _) in layouts.items()
                                    if other_id != edge_id and " C " in path
                                )
                                peer_stroke_boxes = (
                                    *(
                                        (left - 1.5, y - 1.5,
                                         right - left + 3.0, 3.0)
                                        for y, left, right in horizontal
                                    ),
                                    *(
                                        (x - 1.5, low_y - 1.5,
                                         3.0, high_y - low_y + 3.0)
                                        for x, low_y, high_y in vertical
                                    ),
                                )
                                if any(
                                    _process_svg_path_hits_box(peer_path, stroke_box, padding=0.0)
                                    for peer_path in curve_peer_paths
                                    for stroke_box in peer_stroke_boxes
                                ):
                                    continue
                                for label_x in label_xs:
                                    for label_y in label_ys:
                                        box = (
                                            label_x - label_width / 2,
                                            label_y - label_height / 2,
                                            label_width, label_height,
                                        )
                                        if (
                                            box[0] < 8
                                            or box[0] + label_width > width - 8
                                            or box[1] < 112
                                            or box[1] + label_height > height - 8
                                            or _process_svg_path_hits_box(
                                                side_path, box
                                            )
                                        ):
                                            continue
                                        if any(
                                            _process_svg_path_hits_box(path, box)
                                            or (
                                                box[0] < peer[0] + peer[2] + 2
                                                and peer[0]
                                                < box[0] + label_width + 2
                                                and box[1]
                                                < peer[1] + peer[3] + 2
                                                and peer[1]
                                                < box[1] + label_height + 2
                                            )
                                            for other_id, (path, peer)
                                            in layouts.items()
                                            if other_id != edge_id
                                        ):
                                            continue
                                        if any(
                                            box[0] < bx + bw + 1.5
                                            and bx - 1.5
                                            < box[0] + label_width
                                            and box[1] < by + bh + 1.5
                                            and by - 1.5
                                            < box[1] + label_height
                                            for bx, by, bw, bh
                                            in card_boxes.values()
                                        ):
                                            continue
                                        fragment = render_planned_edge(
                                            edge,
                                            label_position_override=(
                                                label_x, label_y
                                            ),
                                            card_side_route_path=side_path,
                                        )
                                        reroute, rendered_box = planned_svg_parts(
                                            fragment
                                        )
                                        if reroute != side_path or any(
                                            abs(a - b) > 0.01
                                            for a, b in zip(rendered_box, box)
                                        ):
                                            continue
                                        layouts[edge_id] = reroute, rendered_box
                                        planned_edge_lines[edge_id] = fragment
                                        reserved_detour_rails.extend(horizontal)
                                        reserved_detour_verticals.extend(vertical)
                                        accepted = True
                                        break
                                    if accepted:
                                        break
                                if accepted:
                                    break
                            if accepted:
                                break
                if not accepted and (
                    source_port_fallback is not None
                    or source_stem_fallback is not None
                ):
                    # Prefer a clear side inset to shared physical stems;
                    # retain the fixed-source fallback only as last resort.
                    fallback = source_port_fallback or source_stem_fallback
                    assert fallback is not None
                    (fallback_path, fallback_label, fallback_frag,
                     fallback_y, fallback_left, fallback_right,
                     fallback_stems) = fallback
                    layouts[edge_id] = fallback_path, fallback_label
                    planned_edge_lines[edge_id] = fallback_frag
                    reserved_detour_rails.append(
                        (fallback_y, fallback_left, fallback_right)
                    )
                    reserved_detour_verticals.extend(fallback_stems)
                    accepted = True
                if not accepted:
                    # The observed route crosses a real foreign card. Never
                    # silently publish that known-invalid curve.
                    raise ValueError("no collision-free process same-row card route")

        # A same-row outer fallback can still cut through a fixed self-loop
        # label. Move only its horizontal rail within the already available
        # row gap, leaving every physical label and card in place.
        if process_branch_gutter_x:
            latest_layout = {
                edge_id: planned_svg_parts(fragment)
                for edge_id, fragment in planned_edge_lines.items()
            }
            for edge in sorted(paint_edges, key=lambda item: str(item["id"])):
                edge_id = str(edge["id"])
                source = positions[str(edge["from"])]
                target = positions[str(edge["to"])]
                if (
                    edge_id not in process_branch_gutter_x
                    or str(edge["kind"]) == "feedback"
                    or edge["from"] == edge["to"]
                    or source[1] != target[1]
                    or 'data-route="process-row-gutter"' not in (
                        planned_edge_lines[edge_id][0]
                    )
                ):
                    continue
                path, own_box = latest_layout[edge_id]
                if not any(
                    _process_svg_path_hits_box(path, other_box)
                    for other_id, (_, other_box) in latest_layout.items()
                    if other_id != edge_id
                ):
                    continue
                corridor = _process_row_corridor_bounds(
                    source[1], positions, direction=-1
                )
                if corridor is None:
                    continue
                low, high = map(float, corridor)
                preferred = (low + high) / 2
                ys = {low + 2, high - 2, preferred}
                for _, (_, other_box) in latest_layout.items():
                    _, top, _, label_height = other_box
                    ys.update((top - 2, top + label_height + 2))
                ordered_ys = sorted(
                    (y for y in ys if low + 1.5 < y < high - 1.5),
                    key=lambda y: (abs(y - preferred), y),
                )
                for lane_y in ordered_ys:
                    fragment = render_planned_edge(
                        edge,
                        route_y_override=(lane_y, lane_y),
                        label_position_override=(
                            own_box[0] + own_box[2] / 2,
                            own_box[1] + own_box[3] / 2,
                        ),
                    )
                    new_path, new_box = planned_svg_parts(fragment)
                    if new_path == path or new_box != own_box:
                        continue
                    if any(
                        _process_svg_path_hits_box(new_path, other_box)
                        for _, other_box in latest_layout.values()
                    ):
                        continue
                    if any(
                        _process_svg_path_hits_box(
                            new_path,
                            (float(x), float(y),
                             float(_NODE_WIDTH), float(_NODE_HEIGHT)),
                        )
                        for node_id, (x, y) in positions.items()
                        if node_id not in {
                            str(edge["from"]), str(edge["to"])
                        }
                    ):
                        continue
                    planned_edge_lines[edge_id] = fragment
                    latest_layout[edge_id] = new_path, new_box
                    break

        # An overflow label can be forced into the leg of an unrelated long
        # return even though its own path has a clear right-hand gutter.
        # Resolve only actual collisions caused by a repacked label or a
        # long return: paths and unrelated label anchors remain unchanged.
        if (
            process_branch_gutter_x or long_vertical_label_x
            or long_branch_slots or feedback_rail_exhausted
            or singleton_fixed_long_label_ids
        ):
            final_layout = {
                edge_id: planned_svg_parts(fragment)
                for edge_id, fragment in planned_edge_lines.items()
            }
            affected_routes = (
                set(process_branch_gutter_x)
                | set(long_vertical_gutter_x)
                | set(long_branch_slots)
            )
            # A newly moved target entrance can remove the old reason that
            # triggered label repacking, even though another already visible
            # peer route still crosses the label. Check every actual peer path
            # for labels of that shared target before accepting the SVG.
            shifted_entrance_targets = {
                str(edge["to"])
                for edge in paint_edges
                if str(edge["id"]) in shared_target_port_x
            }
            for edge in sorted(paint_edges, key=lambda item: str(item["id"])):
                edge_id = str(edge["id"])
                if (
                    str(edge["kind"]) == "feedback"
                    or edge["from"] == edge["to"]
                ):
                    continue
                path, old_box = final_layout[edge_id]
                if (
                    edge_id not in singleton_fixed_long_label_ids
                    and edge_id not in process_branch_gutter_x
                    and edge_id not in long_vertical_label_x
                    and str(edge["to"]) not in shifted_entrance_targets
                    and not any(
                        (other_id in affected_routes or feedback_rail_exhausted)
                        and _process_svg_path_hits_box(other_path, old_box)
                        for other_id, (other_path, _) in final_layout.items()
                        if other_id != edge_id
                    )
                ):
                    continue
                left, top, box_width, box_height = old_box
                hit_foreign_path = any(
                    _process_svg_path_hits_box(other_path, old_box)
                    for other_id, (other_path, _) in final_layout.items()
                    if other_id != edge_id
                )
                overlaps_peer_label = any(
                    old_box[0] < other[0] + other[2]
                    and other[0] < old_box[0] + box_width
                    and old_box[1] < other[1] + other[3]
                    and other[1] < old_box[1] + box_height
                    for other_id, (_, other) in final_layout.items()
                    if other_id != edge_id
                )
                if not hit_foreign_path and not overlaps_peer_label:
                    continue
                x_center = left + box_width / 2
                y_center = top + box_height / 2
                vertical_offsets = (
                    8, -8, 16, -16, 24, -24, 32, -32,
                    40, -40, 48, -48, 56, -56, 64, -64,
                )
                horizontal_offsets = (
                    8, -8, 16, -16, 24, -24, 32, -32,
                    40, -40, 48, -48, 56, -56, 64, -64,
                    80, -80, 96, -96, 128, -128, 160, -160,
                )
                placements = (
                    *((0, dy) for dy in vertical_offsets),
                    *(
                        (dx, dy)
                        for dx in horizontal_offsets
                        for dy in (
                            (0, *vertical_offsets)
                            if feedback_rail_exhausted
                            else (0, 8, -8, 16, -16, 24, -24)
                        )
                    ),
                )
                for dx, dy in placements:
                    new_box = (left + dx, top + dy, box_width, box_height)
                    if (
                        new_box[0] < 8
                        or new_box[0] + box_width > width - 8
                        or new_box[1] < 104
                        or new_box[1] + box_height > height - 8
                    ):
                        continue
                    if _process_svg_path_hits_box(path, new_box):
                        continue
                    if any(
                        _process_svg_path_hits_box(other_path, new_box)
                        for other_id, (other_path, _) in final_layout.items()
                        if other_id != edge_id
                    ):
                        continue
                    if any(
                        new_box[0] < other[0] + other[2] + 2
                        and other[0] < new_box[0] + box_width + 2
                        and new_box[1] < other[1] + other[3] + 2
                        and other[1] < new_box[1] + box_height + 2
                        for other_id, (_, other) in final_layout.items()
                        if other_id != edge_id
                    ):
                        continue
                    if any(
                        new_box[0] < bx + _NODE_WIDTH + 1.5
                        and bx - 1.5 < new_box[0] + box_width
                        and new_box[1] < by + _NODE_HEIGHT + 1.5
                        and by - 1.5 < new_box[1] + box_height
                        for bx, by in positions.values()
                    ):
                        continue
                    fragment = render_planned_edge(
                        edge,
                        label_position_override=(x_center + dx, y_center + dy),
                    )
                    new_path, actual_box = planned_svg_parts(fragment)
                    if (
                        new_path != path
                        or any(
                            abs(a - b) > 0.01
                            for a, b in zip(actual_box, new_box)
                        )
                    ):
                        continue
                    planned_edge_lines[edge_id] = fragment
                    final_layout[edge_id] = new_path, actual_box
                    break

    # A reserved shared-target entrance may reach a *final* peer label even
    # after the earlier label pack has finished. Change only its actual target
    # port using the existing path renderer; never relocate another edge or label.
    # This also covers straight C stems, not just explicit L segments.
    if intent == "process" and model["groups"] and shared_target_port_x:
        final_layout = {
            edge_id: planned_svg_parts(fragment)
            for edge_id, fragment in planned_edge_lines.items()
        }
        by_id = {str(edge["id"]): edge for edge in paint_edges}
        for edge in sorted(paint_edges, key=lambda item: str(item["id"])):
            edge_id = str(edge["id"])
            if edge_id not in shared_target_port_x:
                continue
            old_path, old_box = final_layout[edge_id]
            if not any(
                _process_svg_path_hits_box(old_path, peer_box)
                for peer_id, (_, peer_box) in final_layout.items()
                if peer_id != edge_id
            ):
                continue

            target_id = str(edge["to"])
            target = positions[target_id]
            original_port = shared_target_port_x[edge_id]
            offsets = (*range(16, int(_NODE_WIDTH) - 15, 8), _NODE_WIDTH - 16)
            ports = sorted(
                {target[0] + offset for offset in offsets},
                key=lambda port: (abs(port - original_port), port),
            )
            for port in ports:
                if abs(port - original_port) < 4:
                    continue
                # Respect straight shared-endpoint C stems and L entrances.
                if any(
                    str(by_id[peer_id]["to"]) == target_id
                    and (
                        end := re.search(
                            r"([-0-9.]+) ([-0-9.]+)$", peer_path
                        )
                    )
                    and abs(float(end.group(1)) - port) < 4
                    for peer_id, (peer_path, _) in final_layout.items()
                    if peer_id != edge_id
                ):
                    continue

                own_label_center = (
                    old_box[0] + old_box[2] / 2,
                    old_box[1] + old_box[3] / 2,
                )
                fragment = render_planned_edge(
                    edge,
                    card_target_port_x=port,
                    label_position_override=own_label_center,
                )
                candidate_path, candidate_box = planned_svg_parts(fragment)
                if candidate_box != old_box:
                    continue
                if any(
                    _process_svg_path_hits_box(candidate_path, peer_box)
                    for peer_id, (_, peer_box) in final_layout.items()
                    if peer_id != edge_id
                ):
                    continue
                if any(
                    _process_svg_path_hits_box(
                        candidate_path,
                        (
                            float(x), float(y),
                            float(_NODE_WIDTH), float(_NODE_HEIGHT),
                        ),
                    )
                    for node_id, (x, y) in positions.items()
                    if node_id not in {str(edge["from"]), target_id}
                ):
                    continue
                planned_edge_lines[edge_id] = fragment
                final_layout[edge_id] = candidate_path, candidate_box
                shared_target_port_x[edge_id] = port
                break
            # If every alternative fails, preserve the previously renderable
            # geometry. A blanket exception here regressed 318 valid inputs
            # in the four deterministic 5,000-model differential cohorts.

    for edge in paint_edges:
        lines.extend(planned_edge_lines[str(edge["id"])])
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
# Supplementary neutral symbols that still reach the generic 0.9em path can
# select wider bold fallback glyphs in Chromium. These sorted, non-overlapping
# ranges are rounded upward to 0.05em from the maximum measured advance across
# the Inter/Arial/sans-serif and explicit DejaVu Sans acceptance stacks.
_CANVAS_SUPPLEMENTARY_SYMBOL_WIDTH_RANGES = (
    (0x1013F, 0x1013F, 1.05),
    (0x10185, 0x10185, 0.95),
    (0x10198, 0x10198, 1.15),
    (0x1019C, 0x1019C, 1.00),
    (0x1173F, 0x1173F, 0.95),
    (0x11FD5, 0x11FD5, 1.40),
    (0x11FD6, 0x11FD6, 1.50),
    (0x11FD7, 0x11FD7, 1.25),
    (0x11FD8, 0x11FD8, 1.20),
    (0x11FD9, 0x11FD9, 1.60),
    (0x11FDB, 0x11FDB, 1.60),
    (0x11FDC, 0x11FDC, 1.35),
    (0x11FE1, 0x11FE1, 1.60),
    (0x11FE2, 0x11FE2, 1.80),
    (0x11FE3, 0x11FE3, 1.70),
    (0x11FE4, 0x11FE4, 1.40),
    (0x11FE5, 0x11FE5, 1.30),
    (0x11FE6, 0x11FE6, 1.35),
    (0x11FE7, 0x11FE7, 1.45),
    (0x11FE8, 0x11FE8, 1.55),
    (0x11FE9, 0x11FE9, 1.15),
    (0x11FEA, 0x11FEA, 1.35),
    (0x11FEB, 0x11FEB, 1.25),
    (0x11FEC, 0x11FEC, 1.05),
    (0x11FED, 0x11FED, 1.65),
    (0x11FEE, 0x11FEE, 1.45),
    (0x11FEF, 0x11FEF, 1.35),
    (0x11FF0, 0x11FF0, 1.45),
    (0x11FF1, 0x11FF1, 1.70),
    (0x1CF50, 0x1CFC3, 1.05),
    (0x1D004, 0x1D004, 1.05),
    (0x1D006, 0x1D006, 0.95),
    (0x1D008, 0x1D008, 1.30),
    (0x1D009, 0x1D009, 1.20),
    (0x1D00C, 0x1D00C, 1.05),
    (0x1D013, 0x1D013, 1.25),
    (0x1D025, 0x1D025, 0.95),
    (0x1D027, 0x1D027, 1.05),
    (0x1D028, 0x1D028, 1.25),
    (0x1D029, 0x1D029, 1.10),
    (0x1D02A, 0x1D02A, 1.20),
    (0x1D02B, 0x1D02B, 1.45),
    (0x1D02C, 0x1D02C, 1.15),
    (0x1D02D, 0x1D02D, 1.10),
    (0x1D02E, 0x1D02E, 1.20),
    (0x1D02F, 0x1D02F, 0.95),
    (0x1D031, 0x1D031, 1.00),
    (0x1D032, 0x1D032, 1.50),
    (0x1D033, 0x1D033, 1.10),
    (0x1D034, 0x1D034, 1.25),
    (0x1D035, 0x1D035, 1.05),
    (0x1D037, 0x1D037, 1.10),
    (0x1D03B, 0x1D03B, 1.50),
    (0x1D03D, 0x1D03D, 1.50),
    (0x1D03E, 0x1D03E, 1.05),
    (0x1D03F, 0x1D03F, 1.10),
    (0x1D043, 0x1D043, 1.50),
    (0x1D044, 0x1D044, 0.95),
    (0x1D045, 0x1D045, 1.30),
    (0x1D04B, 0x1D04C, 1.05),
    (0x1D05B, 0x1D05B, 0.95),
    (0x1D060, 0x1D060, 1.00),
    (0x1D061, 0x1D061, 1.05),
    (0x1D062, 0x1D062, 0.95),
    (0x1D065, 0x1D065, 0.95),
    (0x1D06C, 0x1D06D, 0.95),
    (0x1D06E, 0x1D06E, 1.05),
    (0x1D070, 0x1D071, 0.95),
    (0x1D075, 0x1D075, 1.50),
    (0x1D079, 0x1D079, 0.95),
    (0x1D07B, 0x1D07B, 1.05),
    (0x1D138, 0x1D139, 1.20),
    (0x1D192, 0x1D193, 1.40),
    (0x1D1DA, 0x1D1DA, 1.10),
    (0x1D1DC, 0x1D1DC, 0.95),
    (0x1D1E1, 0x1D1E1, 1.45),
    (0x1D1E9, 0x1D1EA, 1.05),
    (0x1D20C, 0x1D20C, 0.95),
    (0x1D800, 0x1D9FF, 1.00),
    (0x1DA37, 0x1DA3A, 1.00),
    (0x1DA6D, 0x1DA74, 1.00),
    (0x1DA76, 0x1DA83, 1.00),
    (0x1DA85, 0x1DA86, 1.00),
    (0x1ED2E, 0x1ED2E, 1.05),
    (0x1F030, 0x1F061, 1.40),
    (0x1F0A0, 0x1F0AE, 1.05),
    (0x1F0B1, 0x1F0BE, 1.05),
    (0x1F0C1, 0x1F0CE, 1.05),
    (0x1F0D1, 0x1F0DF, 1.05),
    (0x1F110, 0x1F12E, 1.00),
    (0x1F12F, 0x1F12F, 0.95),
    (0x1F130, 0x1F149, 1.40),
    (0x1F14A, 0x1F169, 1.00),
    (0x1F172, 0x1F17D, 1.00),
    (0x1F180, 0x1F18D, 1.00),
    (0x1F18F, 0x1F190, 1.00),
    (0x1F19B, 0x1F1AC, 1.00),
    (0x1F1E6, 0x1F1FF, 1.25),
    (0x1F394, 0x1F394, 1.10),
    (0x1F395, 0x1F395, 0.95),
    (0x1F398, 0x1F398, 1.10),
    (0x1F39C, 0x1F39C, 1.00),
    (0x1F39D, 0x1F39D, 0.95),
    (0x1F3F6, 0x1F3F6, 0.95),
    (0x1F4FE, 0x1F4FE, 1.15),
    (0x1F53E, 0x1F53F, 0.95),
    (0x1F540, 0x1F541, 1.00),
    (0x1F542, 0x1F544, 0.95),
    (0x1F568, 0x1F56A, 1.10),
    (0x1F56B, 0x1F56B, 1.00),
    (0x1F56C, 0x1F56C, 1.30),
    (0x1F56E, 0x1F56E, 1.20),
    (0x1F571, 0x1F571, 1.00),
    (0x1F572, 0x1F572, 1.10),
    (0x1F57C, 0x1F57C, 1.05),
    (0x1F57E, 0x1F580, 1.00),
    (0x1F582, 0x1F584, 1.20),
    (0x1F585, 0x1F585, 1.30),
    (0x1F586, 0x1F586, 1.20),
    (0x1F588, 0x1F588, 0.95),
    (0x1F589, 0x1F589, 1.10),
    (0x1F58E, 0x1F58E, 1.20),
    (0x1F58F, 0x1F58F, 1.10),
    (0x1F591, 0x1F591, 1.10),
    (0x1F592, 0x1F593, 1.00),
    (0x1F598, 0x1F59D, 1.25),
    (0x1F5A6, 0x1F5A6, 1.00),
    (0x1F5A7, 0x1F5A7, 1.15),
    (0x1F5AD, 0x1F5AD, 1.20),
    (0x1F5AE, 0x1F5AE, 1.00),
    (0x1F5B3, 0x1F5B3, 1.35),
    (0x1F5B4, 0x1F5B4, 1.05),
    (0x1F5B5, 0x1F5B5, 1.10),
    (0x1F5B6, 0x1F5B8, 0.95),
    (0x1F5BD, 0x1F5BE, 1.10),
    (0x1F5BF, 0x1F5C0, 1.00),
    (0x1F5C1, 0x1F5C1, 1.25),
    (0x1F5C7, 0x1F5C7, 0.95),
    (0x1F5CA, 0x1F5CA, 0.95),
    (0x1F5CD, 0x1F5CD, 1.00),
    (0x1F5D0, 0x1F5D0, 1.00),
    (0x1F5D4, 0x1F5D4, 1.10),
    (0x1F5D6, 0x1F5D7, 0.95),
    (0x1F5DA, 0x1F5DB, 1.25),
    (0x1F5E0, 0x1F5E0, 1.05),
    (0x1F5E2, 0x1F5E2, 1.05),
    (0x1F5E4, 0x1F5E7, 1.00),
    (0x1F5E9, 0x1F5E9, 1.15),
    (0x1F5EA, 0x1F5EA, 1.25),
    (0x1F5EB, 0x1F5EB, 1.35),
    (0x1F5EC, 0x1F5ED, 1.10),
    (0x1F5EE, 0x1F5EE, 1.25),
    (0x1F5F0, 0x1F5F1, 1.20),
    (0x1F5F2, 0x1F5F2, 0.95),
    (0x1F5F6, 0x1F5F6, 0.95),
    (0x1F651, 0x1F652, 0.95),
    (0x1F654, 0x1F654, 0.95),
    (0x1F657, 0x1F657, 0.95),
    (0x1F658, 0x1F65B, 1.00),
    (0x1F65C, 0x1F65F, 1.15),
    (0x1F660, 0x1F663, 1.00),
    (0x1F664, 0x1F667, 1.10),
    (0x1F668, 0x1F66B, 1.05),
    (0x1F66C, 0x1F66C, 1.10),
    (0x1F66E, 0x1F66E, 1.10),
    (0x1F670, 0x1F671, 1.30),
    (0x1F675, 0x1F675, 1.30),
    (0x1F67C, 0x1F67F, 1.20),
    (0x1F6C6, 0x1F6C6, 1.00),
    (0x1F6C7, 0x1F6C8, 1.05),
    (0x1F6D3, 0x1F6D4, 1.00),
    (0x1F6E7, 0x1F6E7, 0.95),
    (0x1F6E8, 0x1F6E8, 1.05),
    (0x1F6F1, 0x1F6F1, 1.00),
    (0x1F6F2, 0x1F6F2, 1.15),
    (0x1F700, 0x1F700, 1.20),
    (0x1F705, 0x1F705, 1.15),
    (0x1F706, 0x1F706, 1.20),
    (0x1F707, 0x1F707, 1.10),
    (0x1F712, 0x1F712, 1.00),
    (0x1F713, 0x1F713, 1.15),
    (0x1F719, 0x1F719, 1.20),
    (0x1F71A, 0x1F71A, 1.05),
    (0x1F71B, 0x1F71B, 0.95),
    (0x1F71C, 0x1F71C, 1.15),
    (0x1F71D, 0x1F71D, 1.00),
    (0x1F721, 0x1F721, 1.00),
    (0x1F724, 0x1F724, 1.40),
    (0x1F732, 0x1F732, 0.95),
    (0x1F733, 0x1F733, 1.10),
    (0x1F738, 0x1F738, 0.95),
    (0x1F73A, 0x1F73A, 0.95),
    (0x1F73C, 0x1F73D, 1.00),
    (0x1F740, 0x1F740, 1.00),
    (0x1F744, 0x1F744, 1.00),
    (0x1F747, 0x1F747, 1.50),
    (0x1F748, 0x1F748, 1.00),
    (0x1F749, 0x1F749, 0.95),
    (0x1F750, 0x1F750, 1.25),
    (0x1F751, 0x1F752, 0.95),
    (0x1F756, 0x1F756, 0.95),
    (0x1F759, 0x1F75A, 1.05),
    (0x1F75B, 0x1F75B, 1.00),
    (0x1F75C, 0x1F75C, 1.20),
    (0x1F75D, 0x1F75D, 0.95),
    (0x1F75E, 0x1F75F, 1.05),
    (0x1F760, 0x1F760, 1.40),
    (0x1F764, 0x1F764, 0.95),
    (0x1F76A, 0x1F76A, 1.15),
    (0x1F76B, 0x1F76B, 1.05),
    (0x1F76C, 0x1F76C, 0.95),
    (0x1F76E, 0x1F76E, 1.00),
    (0x1F770, 0x1F770, 1.00),
    (0x1F772, 0x1F776, 1.05),
    (0x1F77B, 0x1F77F, 1.05),
    (0x1F79A, 0x1F79C, 1.15),
    (0x1F7D2, 0x1F7D4, 0.95),
    (0x1F7D9, 0x1F7D9, 1.05),
    (0x1F808, 0x1F808, 0.95),
    (0x1F80A, 0x1F80A, 0.95),
    (0x1F830, 0x1F830, 1.05),
    (0x1F832, 0x1F832, 1.05),
    (0x1F841, 0x1F841, 1.05),
    (0x1F843, 0x1F847, 1.05),
    (0x1F850, 0x1F850, 2.70),
    (0x1F852, 0x1F852, 2.70),
    (0x1F858, 0x1F858, 1.10),
    (0x1F8A0, 0x1F8AB, 1.05),
    (0x1F8B0, 0x1F8B1, 1.00),
    (0x1F900, 0x1F90B, 1.05),
    (0x1F946, 0x1F946, 1.05),
    (0x1FA00, 0x1FA53, 1.00),
    (0x1FA60, 0x1FA6D, 1.00),
    (0x1FB00, 0x1FB92, 1.00),
    (0x1FB94, 0x1FBC4, 1.00),
)
_CANVAS_SUPPLEMENTARY_SYMBOL_WIDTH_STARTS = tuple(
    first for first, _last, _width in _CANVAS_SUPPLEMENTARY_SYMBOL_WIDTH_RANGES
)
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


def _canvas_fallback_supplementary_symbol_width_units(
    character: str,
) -> float | None:
    codepoint = ord(character)
    if codepoint <= 0xFFFF or unicodedata.category(character) != "So":
        return None
    index = bisect_right(_CANVAS_SUPPLEMENTARY_SYMBOL_WIDTH_STARTS, codepoint) - 1
    if index < 0:
        return None
    _first, last, calibrated_units = _CANVAS_SUPPLEMENTARY_SYMBOL_WIDTH_RANGES[index]
    return calibrated_units if codepoint <= last else None


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
    supplementary_symbol_width = _canvas_fallback_supplementary_symbol_width_units(
        character
    )
    fallback_width = max(
        letter_width or 0.0,
        numeric_width or 0.0,
        supplementary_symbol_width or 0.0,
    )
    if unicodedata.category(character) == "Co":
        return max(_CANVAS_PRIVATE_USE_WIDTH_UNITS, fallback_width)
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
    if supplementary_symbol_width is not None:
        return supplementary_symbol_width
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


def _canvas_edge_label_box_width(value: str) -> int:
    """Size an edge-label box from the same bounded width model used to fit it."""

    probe, truncated = _canvas_bounded_xml_compatible_prefix(
        value,
        max_clusters=_MAX_CANVAS_TEXT_PROBE_CLUSTERS,
        max_codepoints=_MAX_CANVAS_TEXT_PROBE_CODEPOINTS,
    )
    if truncated:
        return 260
    return max(
        42,
        min(
            260,
            math.ceil(_estimated_canvas_single_line_width(probe, size=14)) + 20,
        ),
    )


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
        label_width = _canvas_edge_label_box_width(label)
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
