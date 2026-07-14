"""Local visual-quality receipts for sanitized Miro snapshots."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .snapshot_model import canonical_json
from .snapshot_runtime import prepare_snapshot_destination, write_snapshot_json

Severity = Literal["info", "warn", "fail"]
_CHECKED_DIMENSIONS = (
    "frame_structure",
    "overlap",
    "readability",
    "connectors",
    "doc_table_effect",
    "sticky_balance",
)
_CONNECTOR_TYPES = {"connector", "line", "arrow"}
_DOC_TYPES = {"doc", "doc_format", "document"}
_TABLE_TYPES = {"data_table_format", "table"}
_FRAME_TYPES = {"frame"}
_NATIVE_DIAGRAM_TYPES = {"diagram"}
_STICKY_TYPES = {"sticky", "sticky_note"}
_TEXTUAL_TYPES = _STICKY_TYPES | {"text", "shape"} | _DOC_TYPES | _TABLE_TYPES
_GEOMETRY_OPTIONAL_TYPES = _DOC_TYPES | _TABLE_TYPES | {"text"}
_TEXT_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class QualityFinding:
    """Sanitized quality finding; evidence contains only counts, ratios and booleans."""

    severity: Severity
    code: str
    message: str
    evidence: Mapping[str, int | float | str | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoardQualityReceipt:
    """One local, mutation-free quality interpretation of a verified board snapshot."""

    board_alias: str
    ok: bool
    score: int
    checked_dimensions: tuple[str, ...]
    item_count: int
    visual_item_count: int
    geometry_eligible_item_count: int
    geometry_coverage_percent: int
    frame_count: int
    connector_count: int
    native_diagram_count: int
    sticky_count: int
    doc_count: int
    table_count: int
    overlap_pair_count: int
    max_overlap_ratio: float
    readability_warning_count: int
    findings: tuple[QualityFinding, ...]
    output_path: str | None = None
    mutation_attempted: bool = False
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _item_type(item: Mapping[str, Any]) -> str:
    return str(item.get("type", "unknown")).lower().replace("-", "_")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _nested_number(item: Mapping[str, Any], *paths: tuple[str, str]) -> float | None:
    for first, second in paths:
        value = _number(_mapping(item.get(first)).get(second))
        if value is not None:
            return value
    return None


def _box(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    x = _nested_number(item, ("position", "x"), ("geometry", "x"))
    y = _nested_number(item, ("position", "y"), ("geometry", "y"))
    width = _nested_number(item, ("geometry", "width"), ("geometry", "w"))
    height = _nested_number(item, ("geometry", "height"), ("geometry", "h"))
    if None in (x, y, width, height) or width <= 0 or height <= 0:
        return None
    assert x is not None and y is not None and width is not None and height is not None
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap_ratio(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    if overlap <= 0:
        return 0.0
    smaller = min(_area(first), _area(second))
    return 0.0 if smaller <= 0 else overlap / smaller


def _parent_key(item: Mapping[str, Any]) -> str:
    parent = item.get("parent")
    if parent is None:
        return ""
    return canonical_json(parent)


def _text_length(value: Any) -> int:
    if isinstance(value, str):
        return len(_TEXT_TAG.sub(" ", value).strip())
    if isinstance(value, Mapping):
        return sum(_text_length(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return sum(_text_length(child) for child in value)
    return 0


def _summary_count(layout_read: Mapping[str, Any] | None, key: str) -> int:
    if not layout_read:
        return 0
    value = layout_read.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _snapshot_items(snapshot: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = snapshot.get("items")
    if not isinstance(raw, list):
        raise ValueError("quality snapshot must contain an items list")
    if any(not isinstance(item, Mapping) for item in raw):
        raise ValueError("quality snapshot items must be objects")
    return tuple(raw)


def inspect_snapshot_quality(
    snapshot: Mapping[str, Any],
    *,
    board_alias: str | None = None,
    expected_min_connectors: int = 0,
    expected_min_docs: int = 0,
    expected_min_tables: int = 0,
    layout_read: Mapping[str, Any] | None = None,
    output_path: Path | None = None,
) -> BoardQualityReceipt:
    """Inspect a sanitized snapshot artifact without exposing item text or provider IDs."""

    for value, name in (
        (expected_min_connectors, "expected_min_connectors"),
        (expected_min_docs, "expected_min_docs"),
        (expected_min_tables, "expected_min_tables"),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    alias = board_alias or str(snapshot.get("board_alias") or "unknown")
    items = _snapshot_items(snapshot)
    findings: list[QualityFinding] = []
    type_counts: dict[str, int] = {}
    for item in items:
        item_type = _item_type(item)
        type_counts[item_type] = type_counts.get(item_type, 0) + 1

    connector_count = sum(
        count for item_type, count in type_counts.items() if item_type in _CONNECTOR_TYPES
    )
    native_diagram_count = sum(
        count for item_type, count in type_counts.items() if item_type in _NATIVE_DIAGRAM_TYPES
    )
    doc_count = sum(count for item_type, count in type_counts.items() if item_type in _DOC_TYPES)
    table_count = sum(
        count for item_type, count in type_counts.items() if item_type in _TABLE_TYPES
    )
    frame_count = sum(
        count for item_type, count in type_counts.items() if item_type in _FRAME_TYPES
    )
    sticky_count = sum(
        count for item_type, count in type_counts.items() if item_type in _STICKY_TYPES
    )
    connector_count = max(connector_count, _summary_count(layout_read, "connector_count"))
    doc_count = max(doc_count, _summary_count(layout_read, "doc_count"))
    table_count = max(table_count, _summary_count(layout_read, "table_count"))
    frame_count = max(frame_count, _summary_count(layout_read, "frame_count"))

    visual_items = [item for item in items if _item_type(item) not in _CONNECTOR_TYPES]
    visual_item_count = len(visual_items)
    boxes = [(item, _box(item)) for item in visual_items]
    boxed_items = [(item, box) for item, box in boxes if box is not None]
    geometry_eligible_items = [
        item for item in visual_items if _item_type(item) not in _GEOMETRY_OPTIONAL_TYPES
    ]
    geometry_eligible_item_count = len(geometry_eligible_items)
    geometry_eligible_boxes = [item for item in geometry_eligible_items if _box(item) is not None]
    geometry_coverage = (
        100
        if not geometry_eligible_items
        else round(100 * len(geometry_eligible_boxes) / len(geometry_eligible_items))
    )

    if geometry_eligible_items and geometry_coverage < 80:
        findings.append(
            QualityFinding(
                severity="warn",
                code="geometry_coverage_low",
                message="Too few visual items expose geometry for reliable overlap checks.",
                evidence={
                    "visual_item_count": visual_item_count,
                    "geometry_eligible_item_count": geometry_eligible_item_count,
                    "boxed_eligible_item_count": len(geometry_eligible_boxes),
                    "geometry_coverage_percent": geometry_coverage,
                },
            )
        )

    overlap_pair_count = 0
    max_overlap_ratio = 0.0
    for index, (first, first_box) in enumerate(boxed_items):
        first_type = _item_type(first)
        for second, second_box in boxed_items[index + 1 :]:
            second_type = _item_type(second)
            if _parent_key(first) != _parent_key(second):
                continue
            if first_type in _FRAME_TYPES or second_type in _FRAME_TYPES:
                continue
            ratio = _overlap_ratio(first_box, second_box)
            if ratio >= 0.2:
                overlap_pair_count += 1
                max_overlap_ratio = max(max_overlap_ratio, ratio)

    if overlap_pair_count:
        findings.append(
            QualityFinding(
                severity="fail" if max_overlap_ratio >= 0.45 else "warn",
                code="visual_overlap",
                message="Visual items overlap above the quality threshold.",
                evidence={
                    "overlap_pair_count": overlap_pair_count,
                    "max_overlap_ratio_percent": round(max_overlap_ratio * 100),
                },
            )
        )

    readability_warning_count = 0
    for item, box in boxed_items:
        if _item_type(item) not in _TEXTUAL_TYPES:
            continue
        text_length = _text_length(item.get("data"))
        if text_length < 80:
            continue
        area = _area(box)
        width = max(0.0, box[2] - box[0])
        density = 0 if area <= 0 else text_length / area
        if width < 160 or (text_length > 180 and density > 0.018):
            readability_warning_count += 1
    if readability_warning_count:
        findings.append(
            QualityFinding(
                severity="warn",
                code="readability_pressure",
                message="Some text-heavy items are likely too narrow or dense.",
                evidence={"readability_warning_count": readability_warning_count},
            )
        )

    if frame_count == 0 and visual_item_count > 3:
        findings.append(
            QualityFinding(
                severity="warn",
                code="missing_frame_structure",
                message="The board has several visual items but no detected frame structure.",
                evidence={"visual_item_count": visual_item_count},
            )
        )

    if connector_count < expected_min_connectors:
        findings.append(
            QualityFinding(
                severity="fail",
                code="connector_count_below_expectation",
                message="Detected connector count is below the declared expectation.",
                evidence={
                    "connector_count": connector_count,
                    "expected_min_connectors": expected_min_connectors,
                },
            )
        )
    elif connector_count == 0 and native_diagram_count == 0 and visual_item_count > 6:
        findings.append(
            QualityFinding(
                severity="warn",
                code="no_connectors_on_dense_board",
                message="The board is visually dense but has no detected connectors.",
                evidence={"visual_item_count": visual_item_count},
            )
        )

    if doc_count < expected_min_docs:
        findings.append(
            QualityFinding(
                severity="fail",
                code="doc_count_below_expectation",
                message="Detected DOC count is below the declared expectation.",
                evidence={"doc_count": doc_count, "expected_min_docs": expected_min_docs},
            )
        )
    if table_count < expected_min_tables:
        findings.append(
            QualityFinding(
                severity="fail",
                code="table_count_below_expectation",
                message="Detected TABLE count is below the declared expectation.",
                evidence={"table_count": table_count, "expected_min_tables": expected_min_tables},
            )
        )
    if doc_count == 0 and table_count == 0 and visual_item_count > 6:
        findings.append(
            QualityFinding(
                severity="warn",
                code="rich_items_absent",
                message="No DOC or TABLE items were detected on a non-trivial board.",
                evidence={"visual_item_count": visual_item_count},
            )
        )

    rich_count = doc_count + table_count
    if visual_item_count:
        sticky_ratio = sticky_count / visual_item_count
        if sticky_ratio > 0.55 and rich_count == 0:
            findings.append(
                QualityFinding(
                    severity="warn",
                    code="sticky_dominance",
                    message="Sticky notes dominate without richer DOC/TABLE structure.",
                    evidence={
                        "sticky_count": sticky_count,
                        "visual_item_count": visual_item_count,
                        "sticky_ratio_percent": round(sticky_ratio * 100),
                    },
                )
            )

    fail_count = sum(finding.severity == "fail" for finding in findings)
    warn_count = sum(finding.severity == "warn" for finding in findings)
    score = max(0, 100 - fail_count * 25 - warn_count * 8)
    return BoardQualityReceipt(
        board_alias=alias,
        ok=fail_count == 0,
        score=score,
        checked_dimensions=_CHECKED_DIMENSIONS,
        item_count=len(items),
        visual_item_count=visual_item_count,
        geometry_eligible_item_count=geometry_eligible_item_count,
        geometry_coverage_percent=geometry_coverage,
        frame_count=frame_count,
        connector_count=connector_count,
        native_diagram_count=native_diagram_count,
        sticky_count=sticky_count,
        doc_count=doc_count,
        table_count=table_count,
        overlap_pair_count=overlap_pair_count,
        max_overlap_ratio=round(max_overlap_ratio, 4),
        readability_warning_count=readability_warning_count,
        findings=tuple(findings),
        output_path=str(output_path) if output_path else None,
    )


def load_snapshot_artifact(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("quality snapshot artifact is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("quality snapshot artifact must be an object")
    return value


def write_quality_receipt_from_snapshot_file(
    *,
    snapshot_path: Path,
    destination: Path,
    board_alias: str | None = None,
    expected_min_connectors: int = 0,
    expected_min_docs: int = 0,
    expected_min_tables: int = 0,
    layout_read: Mapping[str, Any] | None = None,
) -> BoardQualityReceipt:
    """Read a verified snapshot artifact and write an owner-only quality receipt."""

    destination = prepare_snapshot_destination(destination)
    snapshot = load_snapshot_artifact(snapshot_path)
    receipt = inspect_snapshot_quality(
        snapshot,
        board_alias=board_alias,
        expected_min_connectors=expected_min_connectors,
        expected_min_docs=expected_min_docs,
        expected_min_tables=expected_min_tables,
        layout_read=layout_read,
        output_path=destination,
    )
    write_snapshot_json(destination, receipt.to_dict())
    return receipt
