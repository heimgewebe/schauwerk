"""Deterministic offline visual previews and semantic regression receipts."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import stat
import textwrap
from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .delivery import validate_representation_package
from .representation import render_miro_board
from .system_v2 import COLOR_ROLES, validate_board_spec

PREVIEW_SCHEMA = "schauwerk-visual-preview.v1"
REGRESSION_SCHEMA = "schauwerk-visual-regression.v1"

_FONT_SIZES = {"display": 38, "heading": 24, "body": 18, "caption": 14}
_BLOCKER_CODES = {
    "empty_content",
    "object_clipped",
    "object_overlap",
    "text_overflow",
    "missing_connector_endpoint",
}


class VisualPreviewError(ValueError):
    """The visual preview input or output boundary is unsafe or inconsistent."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_document(value: Any, *, schema_name: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisualPreviewError(f"{label} must be an object")
    schema = json.loads(
        files("schauwerk.schemas").joinpath(schema_name).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        location = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        raise VisualPreviewError(f"{label} violates its schema at {location}")
    return value


def _read_private_bytes(path: Path, *, label: str, maximum_bytes: int) -> bytes:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise VisualPreviewError(f"{label} path must not contain symlinks")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise VisualPreviewError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
        ):
            raise VisualPreviewError(f"{label} file is unsafe")
        if before.st_size > maximum_bytes:
            raise VisualPreviewError(f"{label} exceeds its size limit")
        payload = bytearray()
        while len(payload) < before.st_size:
            chunk = os.read(descriptor, min(65_536, before.st_size - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity or len(payload) != before.st_size:
            raise VisualPreviewError(f"{label} changed while being read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _validate_preview_semantics(value: Mapping[str, Any]) -> None:
    frame_ids: set[str] = set()
    frame_numbers: set[int] = set()
    svg_paths: set[str] = set()
    object_count = 0
    blocker_count = 0
    warning_count = 0
    issue_counts: dict[str, int] = {}
    for frame in value["frames"]:
        frame_id = str(frame["id"])
        frame_number = int(frame["number"])
        svg_path = str(frame["svg_path"])
        if frame_id in frame_ids or frame_number in frame_numbers or svg_path in svg_paths:
            raise VisualPreviewError("visual preview frame identities are not unique")
        frame_ids.add(frame_id)
        frame_numbers.add(frame_number)
        svg_paths.add(svg_path)
        frame_body = dict(frame)
        observed_frame_digest = frame_body.pop("frame_digest")
        frame_body.pop("svg_path")
        frame_body.pop("svg_sha256")
        frame_body.pop("svg_bytes")
        if _digest(frame_body) != observed_frame_digest:
            raise VisualPreviewError(f"visual preview frame {frame_id} digest mismatch")
        issue_codes_by_object: dict[str, list[str]] = {}
        for issue in frame["issues"]:
            issue_body = dict(issue)
            observed_fingerprint = issue_body.pop("fingerprint")
            if _digest(issue_body) != observed_fingerprint:
                raise VisualPreviewError(
                    f"visual preview frame {frame_id} issue fingerprint mismatch"
                )
            code = str(issue["code"])
            issue_counts[code] = issue_counts.get(code, 0) + 1
            if issue["severity"] == "blocker":
                blocker_count += 1
            else:
                warning_count += 1
            for object_id in issue["object_ids"]:
                issue_codes_by_object.setdefault(str(object_id), []).append(code)
        object_ids: set[str] = set()
        for item in frame["objects"]:
            object_id = str(item["id"])
            if object_id in object_ids:
                raise VisualPreviewError(
                    f"visual preview frame {frame_id} has duplicate object ids"
                )
            object_ids.add(object_id)
            object_body = dict(item)
            observed_object_digest = object_body.pop("object_digest")
            if _digest(object_body) != observed_object_digest:
                raise VisualPreviewError(
                    f"visual preview object {frame_id}/{object_id} digest mismatch"
                )
            expected_codes = sorted(set(issue_codes_by_object.get(object_id, [])))
            if item["issue_codes"] != expected_codes:
                raise VisualPreviewError(
                    f"visual preview object {frame_id}/{object_id} issue binding mismatch"
                )
        referenced = set(issue_codes_by_object)
        if not referenced <= object_ids:
            raise VisualPreviewError(f"visual preview frame {frame_id} has unknown issue objects")
        object_count += len(frame["objects"])
    if int(value["frame_count"]) != len(value["frames"]):
        raise VisualPreviewError("visual preview frame count mismatch")
    if int(value["object_count"]) != object_count:
        raise VisualPreviewError("visual preview object count mismatch")
    if int(value["blocker_count"]) != blocker_count:
        raise VisualPreviewError("visual preview blocker count mismatch")
    if int(value["warning_count"]) != warning_count:
        raise VisualPreviewError("visual preview warning count mismatch")
    expected_issue_counts = {key: issue_counts[key] for key in sorted(issue_counts)}
    if value["issue_counts"] != expected_issue_counts:
        raise VisualPreviewError("visual preview issue count mismatch")
    if bool(value["ok"]) != (blocker_count == 0):
        raise VisualPreviewError("visual preview status does not match its blockers")


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _object_text(item: Mapping[str, Any]) -> str:
    kind = item.get("kind")
    if kind == "table":
        parts = [str(item.get("title", ""))]
        parts.extend(str(value) for value in item.get("columns", []))
        for row in item.get("rows", []):
            parts.extend(str(value) for value in row)
        return _normalized_text(" ".join(parts))
    return _normalized_text(item.get("content", ""))


def _font_size(item: Mapping[str, Any]) -> int:
    return _FONT_SIZES.get(str(item.get("font_level", "body")), _FONT_SIZES["body"])


def _wrap_lines(value: str, *, width: float, font_size: int) -> list[str]:
    normalized = _normalized_text(value)
    if not normalized:
        return []
    characters = max(1, int(max(1.0, width - 24.0) / max(1.0, font_size * 0.55)))
    return textwrap.wrap(
        normalized,
        width=characters,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=True,
        drop_whitespace=True,
    ) or [normalized]


def _declared_box(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    if item.get("kind") == "connector":
        return None
    try:
        return (
            float(item["x"]),
            float(item["y"]),
            float(item["w"]),
            float(item["h"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualPreviewError(
            f"object {item.get('id', '<unknown>')} has invalid geometry"
        ) from exc


def _estimated_box(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    box = _declared_box(item)
    if box is None:
        return None
    x, y, width, height = box
    kind = item.get("kind")
    if kind == "table":
        rows = item.get("rows", [])
        columns = item.get("columns", [])
        estimated_height = 52.0 + (len(rows) + 1) * 34.0
        column_width = max(120.0, width / max(1, len(columns)))
        longest = 0
        for value in [item.get("title", ""), *columns]:
            longest = max(longest, len(_normalized_text(value)))
        for row in rows:
            for value in row:
                longest = max(longest, len(_normalized_text(value)))
        estimated_width = max(
            width, min(1080.0, column_width * max(1, len(columns)), longest * 8.5)
        )
        return (x, y, estimated_width, max(height, estimated_height))
    if kind == "doc":
        lines = _wrap_lines(_object_text(item), width=width, font_size=_font_size(item))
        estimated_height = 36.0 + len(lines) * (_font_size(item) * 1.35)
        return (x, y, width, max(height, estimated_height))
    return box


def _intersection_area(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_x, left_y, left_w, left_h = left
    right_x, right_y, right_w, right_h = right
    width = min(left_x + left_w, right_x + right_w) - max(left_x, right_x)
    height = min(left_y + left_h, right_y + right_h) - max(left_y, right_y)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def _line_intersects_box(
    start: tuple[float, float],
    end: tuple[float, float],
    box: tuple[float, float, float, float],
) -> bool:
    x1, y1 = start
    x2, y2 = end
    x, y, width, height = box
    if x <= x1 <= x + width and y <= y1 <= y + height:
        return True
    if x <= x2 <= x + width and y <= y2 <= y + height:
        return True
    steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / 20.0))
    for index in range(1, steps):
        ratio = index / steps
        sample_x = x1 + (x2 - x1) * ratio
        sample_y = y1 + (y2 - y1) * ratio
        if x <= sample_x <= x + width and y <= sample_y <= y + height:
            return True
    return False


def _issue(
    code: str,
    *,
    frame_id: str,
    object_ids: Sequence[str],
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "code": code,
        "severity": "blocker" if code in _BLOCKER_CODES else "warning",
        "frame_id": frame_id,
        "object_ids": sorted(set(object_ids)),
        "message": message,
    }
    if details:
        value["details"] = dict(details)
    value["fingerprint"] = _digest(value)
    return value


def _object_record(item: Mapping[str, Any], issues: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    object_id = str(item["id"])
    declared = _declared_box(item)
    estimated = _estimated_box(item)
    record: dict[str, Any] = {
        "id": object_id,
        "kind": str(item["kind"]),
        "role": str(item["role"]),
        "content_digest": _digest(_object_text(item)),
        "declared_box": list(declared) if declared is not None else None,
        "estimated_box": list(estimated) if estimated is not None else None,
        "issue_codes": sorted(
            {str(issue["code"]) for issue in issues if object_id in issue.get("object_ids", [])}
        ),
    }
    record["object_digest"] = _digest(record)
    return record


def analyze_visual_board(board: Mapping[str, Any], *, package_digest: str) -> dict[str, Any]:
    """Analyze one validated board using deterministic, renderer-independent geometry."""

    quality = validate_board_spec(board)
    if quality.get("ok") is not True:
        raise VisualPreviewError("visual preview requires a passing Visual System v2 board")
    board_digest = board.get("board_digest")
    if not isinstance(board_digest, str) or len(board_digest) != 64:
        raise VisualPreviewError("visual preview board digest is invalid")

    frame_records: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []
    for frame in board["frames"]:
        frame_id = str(frame["id"])
        frame_width = float(frame["w"])
        frame_height = float(frame["h"])
        objects = list(frame["objects"])
        object_by_id = {str(item["id"]): item for item in objects}
        frame_issues: list[dict[str, Any]] = []

        for item in objects:
            object_id = str(item["id"])
            kind = str(item["kind"])
            content = _object_text(item)
            if not content:
                frame_issues.append(
                    _issue(
                        "empty_content",
                        frame_id=frame_id,
                        object_ids=[object_id],
                        message="visible object content is empty",
                    )
                )
            box = _estimated_box(item)
            if box is None:
                continue
            x, y, width, height = box
            if x < 0 or y < 0 or x + width > frame_width or y + height > frame_height:
                frame_issues.append(
                    _issue(
                        "object_clipped",
                        frame_id=frame_id,
                        object_ids=[object_id],
                        message="estimated object geometry exceeds its frame",
                        details={"estimated_box": [x, y, width, height]},
                    )
                )
            if kind in {"text", "shape", "sticky"}:
                font_size = _font_size(item)
                lines = _wrap_lines(content, width=width, font_size=font_size)
                max_lines = max(1, int(max(1.0, height - 16.0) / (font_size * 1.3)))
                if len(lines) > max_lines:
                    frame_issues.append(
                        _issue(
                            "text_overflow",
                            frame_id=frame_id,
                            object_ids=[object_id],
                            message=(
                                "estimated text requires more lines than the declared box permits"
                            ),
                            details={"estimated_lines": len(lines), "maximum_lines": max_lines},
                        )
                    )
            if item.get("provider_geometry") == "auto_sized":
                declared = _declared_box(item)
                if declared is not None and box != declared:
                    frame_issues.append(
                        _issue(
                            "provider_auto_size_risk",
                            frame_id=frame_id,
                            object_ids=[object_id],
                            message=(
                                "provider auto-sizing may enlarge the object beyond "
                                "its declared design box"
                            ),
                            details={"declared_box": list(declared), "estimated_box": list(box)},
                        )
                    )

        boxed = [item for item in objects if _estimated_box(item) is not None]
        for index, left in enumerate(boxed):
            for right in boxed[index + 1 :]:
                left_box = _estimated_box(left)
                right_box = _estimated_box(right)
                assert left_box is not None and right_box is not None
                area = _intersection_area(left_box, right_box)
                if area > 0:
                    frame_issues.append(
                        _issue(
                            "object_overlap",
                            frame_id=frame_id,
                            object_ids=[str(left["id"]), str(right["id"])],
                            message="estimated visual boxes overlap",
                            details={"overlap_area": round(area, 3)},
                        )
                    )

        for connector in (item for item in objects if item.get("kind") == "connector"):
            connector_id = str(connector["id"])
            source_id = str(connector.get("from", ""))
            target_id = str(connector.get("to", ""))
            source = object_by_id.get(source_id)
            target = object_by_id.get(target_id)
            if source is None or target is None:
                frame_issues.append(
                    _issue(
                        "missing_connector_endpoint",
                        frame_id=frame_id,
                        object_ids=[connector_id],
                        message="connector endpoint is missing from the frame",
                        details={
                            "missing_endpoints": sorted(
                                endpoint
                                for endpoint in (source_id, target_id)
                                if endpoint not in object_by_id
                            )
                        },
                    )
                )
                continue
            source_box = _estimated_box(source)
            target_box = _estimated_box(target)
            if source_box is None or target_box is None:
                continue
            start = (source_box[0] + source_box[2] / 2.0, source_box[1] + source_box[3] / 2.0)
            end = (target_box[0] + target_box[2] / 2.0, target_box[1] + target_box[3] / 2.0)
            obstructing = []
            for item in boxed:
                item_id = str(item["id"])
                if item_id in {source_id, target_id}:
                    continue
                box = _estimated_box(item)
                assert box is not None
                if _line_intersects_box(start, end, box):
                    obstructing.append(item_id)
            if obstructing:
                frame_issues.append(
                    _issue(
                        "connector_obstruction",
                        frame_id=frame_id,
                        object_ids=[connector_id, *obstructing],
                        message="straight-line preview crosses an unrelated object",
                        details={"obstructing_objects": sorted(obstructing)},
                    )
                )

        frame_issues.sort(key=lambda item: (item["severity"], item["code"], item["fingerprint"]))
        records = [_object_record(item, frame_issues) for item in objects]
        frame_record: dict[str, Any] = {
            "id": frame_id,
            "number": int(frame["number"]),
            "role": str(frame["role"]),
            "title": str(frame["title"]),
            "width": frame_width,
            "height": frame_height,
            "objects": records,
            "issues": frame_issues,
        }
        frame_record["frame_digest"] = _digest(frame_record)
        frame_records.append(frame_record)
        all_issues.extend(frame_issues)

    issue_counts: dict[str, int] = {}
    for issue in all_issues:
        issue_counts[issue["code"]] = issue_counts.get(issue["code"], 0) + 1
    blocker_count = sum(issue["severity"] == "blocker" for issue in all_issues)
    warning_count = len(all_issues) - blocker_count
    value: dict[str, Any] = {
        "schema_version": PREVIEW_SCHEMA,
        "ok": blocker_count == 0,
        "package_digest": package_digest,
        "board_digest": board_digest,
        "quality_digest": quality["quality_digest"],
        "quality_score": quality["score"],
        "frame_count": len(frame_records),
        "object_count": sum(len(frame["objects"]) for frame in frame_records),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "issue_counts": {key: issue_counts[key] for key in sorted(issue_counts)},
        "frames": frame_records,
        "does_not_establish": [
            "provider pixel rendering",
            "font metrics identical to Miro clients",
            "absence of every possible connector crossing",
            "human aesthetic acceptance",
            "permission to mutate a provider board",
        ],
    }
    value["preview_digest"] = _digest(value)
    return value


def _svg_text(
    *,
    item: Mapping[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
) -> str:
    font_size = _font_size(item)
    lines = _wrap_lines(_object_text(item), width=width, font_size=font_size)
    max_lines = max(1, int(max(1.0, height - 16.0) / (font_size * 1.3)))
    rendered = lines[:max_lines]
    if len(lines) > max_lines and rendered:
        rendered[-1] = rendered[-1][:-1] + "…" if len(rendered[-1]) > 1 else "…"
    tspans = []
    baseline = y + 12.0 + font_size
    for index, line in enumerate(rendered):
        tspans.append(
            f'<tspan x="{x + 12.0:.1f}" y="{baseline + index * font_size * 1.3:.1f}">'
            f"{html.escape(line)}</tspan>"
        )
    return (
        f'<text font-family="sans-serif" font-size="{font_size}" fill="{color}" '
        f'aria-label="{html.escape(_object_text(item))}">{"".join(tspans)}</text>'
    )


def _shape_svg(item: Mapping[str, Any], issue_codes: set[str]) -> str:
    box = _estimated_box(item)
    if box is None:
        return ""
    x, y, width, height = box
    role = str(item.get("color_role", "ink"))
    palette = COLOR_ROLES.get(role, COLOR_ROLES["ink"])
    stroke = "#C53030" if issue_codes & _BLOCKER_CODES else palette["border"]
    stroke_width = 4 if issue_codes & _BLOCKER_CODES else 2
    kind = str(item["kind"])
    shape = str(item.get("shape", "round_rectangle"))
    if kind == "shape" and shape == "circle":
        geometry = (
            f'<ellipse cx="{x + width / 2:.1f}" cy="{y + height / 2:.1f}" '
            f'rx="{width / 2:.1f}" ry="{height / 2:.1f}" fill="{palette["background"]}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    elif kind == "shape" and shape in {"rhombus", "diamond"}:
        points = (
            f"{x + width / 2:.1f},{y:.1f} {x + width:.1f},{y + height / 2:.1f} "
            f"{x + width / 2:.1f},{y + height:.1f} {x:.1f},{y + height / 2:.1f}"
        )
        geometry = (
            f'<polygon points="{points}" fill="{palette["background"]}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    elif kind == "shape" and shape in {"octagon", "hexagon"}:
        inset = min(width, height) * (0.18 if shape == "octagon" else 0.24)
        points = (
            f"{x + inset:.1f},{y:.1f} {x + width - inset:.1f},{y:.1f} "
            f"{x + width:.1f},{y + inset:.1f} {x + width:.1f},{y + height - inset:.1f} "
            f"{x + width - inset:.1f},{y + height:.1f} {x + inset:.1f},{y + height:.1f} "
            f"{x:.1f},{y + height - inset:.1f} {x:.1f},{y + inset:.1f}"
        )
        geometry = (
            f'<polygon points="{points}" fill="{palette["background"]}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    else:
        radius = 18 if kind == "shape" else 4
        geometry = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'rx="{radius}" fill="{palette["background"]}" stroke="{stroke}" '
            f'stroke-width="{stroke_width}"/>'
        )
    return geometry + _svg_text(
        item=item,
        x=x,
        y=y,
        width=width,
        height=height,
        color=palette["foreground"],
    )


def render_frame_svg(frame: Mapping[str, Any], frame_record: Mapping[str, Any]) -> str:
    issue_codes_by_object: dict[str, set[str]] = {}
    for issue in frame_record["issues"]:
        for object_id in issue["object_ids"]:
            issue_codes_by_object.setdefault(str(object_id), set()).add(str(issue["code"]))
    object_by_id = {str(item["id"]): item for item in frame["objects"]}
    connectors = [item for item in frame["objects"] if item["kind"] == "connector"]
    bodies = [item for item in frame["objects"] if item["kind"] != "connector"]
    elements = [
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
        'orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#147D92"/></marker></defs>',
        f'<rect x="0" y="0" width="{float(frame["w"]):.1f}" height="{float(frame["h"]):.1f}" '
        'fill="#F8FAFC" stroke="#BCCCDC" stroke-width="2"/>',
    ]
    for connector in connectors:
        source = object_by_id.get(str(connector.get("from", "")))
        target = object_by_id.get(str(connector.get("to", "")))
        if source is None or target is None:
            continue
        source_box = _estimated_box(source)
        target_box = _estimated_box(target)
        if source_box is None or target_box is None:
            continue
        x1 = source_box[0] + source_box[2] / 2.0
        y1 = source_box[1] + source_box[3] / 2.0
        x2 = target_box[0] + target_box[2] / 2.0
        y2 = target_box[1] + target_box[3] / 2.0
        elements.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            'stroke="#147D92" stroke-width="3" marker-end="url(#arrow)"/>'
        )
        label = html.escape(_object_text(connector))
        elements.append(
            f'<text x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2 - 8:.1f}" '
            f'font-family="sans-serif" font-size="14" fill="#102A43">{label}</text>'
        )
    for item in bodies:
        elements.append(_shape_svg(item, issue_codes_by_object.get(str(item["id"]), set())))
    if frame_record["issues"]:
        summary = ", ".join(
            f"{code}: {sum(issue['code'] == code for issue in frame_record['issues'])}"
            for code in sorted({issue["code"] for issue in frame_record["issues"]})
        )
        elements.append(
            f'<text x="20" y="{float(frame["h"]) - 18:.1f}" font-family="sans-serif" '
            f'font-size="13" fill="#C53030">{html.escape(summary)}</text>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{html.escape(str(frame["title"]))}" '
        f'viewBox="0 0 {float(frame["w"]):.1f} {float(frame["h"]):.1f}">'
        f"{''.join(elements)}</svg>\n"
    )


def _write_new_bytes(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short visual preview write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _assert_safe_output_parent(path: Path, *, label: str) -> None:
    current = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode):
        raise VisualPreviewError(f"{label} is not a directory")
    owner_private = current.st_uid == os.getuid() and not current.st_mode & 0o022
    root_sticky = (
        current.st_uid == 0
        and bool(current.st_mode & stat.S_ISVTX)
        and bool(current.st_mode & 0o002)
    )
    if not (owner_private or root_sticky):
        raise VisualPreviewError(f"{label} is unsafe")


def _prepare_output_dir(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise VisualPreviewError("visual preview output path must not contain symlinks")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_safe_output_parent(
        destination.parent,
        label="visual preview output parent",
    )
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise VisualPreviewError("visual preview output must be absent") from exc
    return destination


def _index_html(manifest: Mapping[str, Any]) -> str:
    cards = []
    for frame in manifest["frames"]:
        path = frame["svg_path"]
        issues = frame["issues"]
        issue_text = (
            "keine Befunde"
            if not issues
            else ", ".join(
                f"{code}: {sum(item['code'] == code for item in issues)}"
                for code in sorted({item["code"] for item in issues})
            )
        )
        cards.append(
            "<section><h2>"
            + html.escape(f"{frame['number']}. {frame['title']}")
            + "</h2><p>"
            + html.escape(issue_text)
            + f'</p><img src="{html.escape(path)}" alt="{html.escape(frame["title"])}"></section>'
        )
    status = "PASS" if manifest["ok"] else "BLOCKED"
    return (
        '<!doctype html><html lang="de"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Schauwerk Visual Preview — {status}</title>"
        "<style>body{font:16px system-ui,sans-serif;margin:0;background:#eef2f6;color:#102a43}"
        "header,section{max-width:1180px;margin:24px auto;background:#fff;"
        "padding:24px;border-radius:16px}"
        "img{display:block;width:100%;height:auto;border:1px solid #bcccdc}"
        "h1,h2{margin-top:0}.blocked{color:#c53030}.pass{color:#2f855a}</style>"
        f'<header><h1 class="{"pass" if manifest["ok"] else "blocked"}">{status}</h1>'
        f"<p>Frames: {manifest['frame_count']} · Objekte: {manifest['object_count']} · "
        f"Blocker: {manifest['blocker_count']} · Warnungen: {manifest['warning_count']}</p>"
        f"<code>{manifest['board_digest']}</code></header>{''.join(cards)}</html>\n"
    )


def build_visual_preview(*, package_dir: Path, output_dir: Path) -> dict[str, Any]:
    package = validate_representation_package(package_dir)
    if "miro_native" not in package["plan"]["selected_formats"]:
        raise VisualPreviewError("visual preview requires a package with Miro-native output")
    board = render_miro_board(package["model"], package["plan"])
    manifest = analyze_visual_board(
        board,
        package_digest=str(package["manifest"]["package_digest"]),
    )
    frame_by_id = {str(frame["id"]): frame for frame in board["frames"]}
    emitted_frames: list[dict[str, Any]] = []
    svg_payloads: dict[str, bytes] = {}
    for frame_record in manifest["frames"]:
        name = f"frame-{int(frame_record['number']):02d}-{frame_record['id']}.svg"
        svg = render_frame_svg(frame_by_id[frame_record["id"]], frame_record).encode("utf-8")
        svg_payloads[name] = svg
        emitted = dict(frame_record)
        emitted["svg_path"] = name
        emitted["svg_sha256"] = _bytes_digest(svg)
        emitted["svg_bytes"] = len(svg)
        emitted_frames.append(emitted)
    manifest = {**manifest, "frames": emitted_frames}
    manifest.pop("preview_digest", None)
    index_payload = _index_html(manifest).encode("utf-8")
    manifest["index_path"] = "index.html"
    manifest["index_sha256"] = _bytes_digest(index_payload)
    manifest["index_bytes"] = len(index_payload)
    manifest["preview_digest"] = _digest(manifest)
    manifest = _validate_document(
        manifest,
        schema_name="visual-preview.v1.schema.json",
        label="visual preview",
    )
    _validate_preview_semantics(manifest)
    destination = _prepare_output_dir(output_dir)
    for name, svg in svg_payloads.items():
        _write_new_bytes(destination / name, svg)
    _write_new_bytes(destination / "index.html", index_payload)
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_new_bytes(destination / "preview.json", manifest_payload)
    directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {
        "schema_version": PREVIEW_SCHEMA,
        "ok": manifest["ok"],
        "output_dir": str(destination),
        "preview": str(destination / "preview.json"),
        "index": str(destination / "index.html"),
        "preview_digest": manifest["preview_digest"],
        "package_digest": manifest["package_digest"],
        "frame_count": manifest["frame_count"],
        "object_count": manifest["object_count"],
        "blocker_count": manifest["blocker_count"],
        "warning_count": manifest["warning_count"],
        "mutation_attempted": False,
    }


def load_visual_preview(path: Path) -> dict[str, Any]:
    payload = _read_private_bytes(path, label="visual preview", maximum_bytes=4_000_000)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisualPreviewError("visual preview is invalid JSON") from exc
    value = _validate_document(
        value,
        schema_name="visual-preview.v1.schema.json",
        label="visual preview",
    )
    observed = value["preview_digest"]
    body = dict(value)
    body.pop("preview_digest")
    if _digest(body) != observed:
        raise VisualPreviewError("visual preview digest mismatch")
    _validate_preview_semantics(value)
    root = path.expanduser().absolute().parent
    current_root = root.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(current_root.st_mode)
        or current_root.st_uid != os.getuid()
        or current_root.st_mode & 0o077
    ):
        raise VisualPreviewError("visual preview directory is unsafe")
    expected_names = {"preview.json", value["index_path"]}
    expected_names.update(str(frame["svg_path"]) for frame in value["frames"])
    if set(os.listdir(root)) != expected_names:
        raise VisualPreviewError("visual preview file set is not exact")
    index_payload = _read_private_bytes(
        root / value["index_path"],
        label="visual preview index",
        maximum_bytes=2_000_000,
    )
    if (
        len(index_payload) != value["index_bytes"]
        or _bytes_digest(index_payload) != value["index_sha256"]
    ):
        raise VisualPreviewError("visual preview index does not match its receipt")
    for frame in value["frames"]:
        svg_payload = _read_private_bytes(
            root / frame["svg_path"],
            label=f"visual preview frame {frame['id']}",
            maximum_bytes=2_000_000,
        )
        if (
            len(svg_payload) != frame["svg_bytes"]
            or _bytes_digest(svg_payload) != frame["svg_sha256"]
        ):
            raise VisualPreviewError(
                f"visual preview frame {frame['id']} does not match its receipt"
            )
    return value


def compare_visual_previews(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    baseline = _validate_document(
        baseline,
        schema_name="visual-preview.v1.schema.json",
        label="visual regression baseline",
    )
    candidate = _validate_document(
        candidate,
        schema_name="visual-preview.v1.schema.json",
        label="visual regression candidate",
    )
    for label, value in (("baseline", baseline), ("candidate", candidate)):
        observed = value["preview_digest"]
        body = dict(value)
        body.pop("preview_digest")
        if _digest(body) != observed:
            raise VisualPreviewError(f"visual regression {label} digest mismatch")
        _validate_preview_semantics(value)
    baseline_objects = {
        f"{frame['id']}/{item['id']}": item
        for frame in baseline["frames"]
        for item in frame["objects"]
    }
    candidate_objects = {
        f"{frame['id']}/{item['id']}": item
        for frame in candidate["frames"]
        for item in frame["objects"]
    }
    added = sorted(set(candidate_objects) - set(baseline_objects))
    removed = sorted(set(baseline_objects) - set(candidate_objects))
    changed = sorted(
        key
        for key in set(baseline_objects) & set(candidate_objects)
        if baseline_objects[key]["object_digest"] != candidate_objects[key]["object_digest"]
    )
    moved = sorted(
        key
        for key in set(baseline_objects) & set(candidate_objects)
        if baseline_objects[key]["estimated_box"] != candidate_objects[key]["estimated_box"]
    )
    baseline_blockers = {
        issue["fingerprint"]
        for frame in baseline["frames"]
        for issue in frame["issues"]
        if issue["severity"] == "blocker"
    }
    candidate_blockers = {
        issue["fingerprint"]
        for frame in candidate["frames"]
        for issue in frame["issues"]
        if issue["severity"] == "blocker"
    }
    new_blockers = sorted(candidate_blockers - baseline_blockers)
    resolved_blockers = sorted(baseline_blockers - candidate_blockers)
    regression = bool(
        new_blockers or int(candidate["blocker_count"]) > int(baseline["blocker_count"])
    )
    value: dict[str, Any] = {
        "schema_version": REGRESSION_SCHEMA,
        "ok": not regression,
        "regression": regression,
        "baseline_preview_digest": baseline["preview_digest"],
        "candidate_preview_digest": candidate["preview_digest"],
        "baseline_package_digest": baseline["package_digest"],
        "candidate_package_digest": candidate["package_digest"],
        "baseline_blocker_count": baseline["blocker_count"],
        "candidate_blocker_count": candidate["blocker_count"],
        "new_blockers": new_blockers,
        "resolved_blockers": resolved_blockers,
        "added_objects": added,
        "removed_objects": removed,
        "changed_objects": changed,
        "moved_objects": moved,
        "does_not_establish": [
            "pixel-identical provider rendering",
            "semantic correctness of intentional content changes",
            "human aesthetic acceptance",
        ],
    }
    value["regression_digest"] = _digest(value)
    return _validate_document(
        value,
        schema_name="visual-regression.v1.schema.json",
        label="visual regression",
    )


def write_visual_regression(
    *, baseline_path: Path, candidate_path: Path, output: Path
) -> dict[str, Any]:
    baseline = load_visual_preview(baseline_path)
    candidate = load_visual_preview(candidate_path)
    value = compare_visual_previews(baseline, candidate)
    destination = output.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise VisualPreviewError("visual regression output path must not contain symlinks")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_safe_output_parent(
        destination.parent,
        label="visual regression output parent",
    )
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        _write_new_bytes(destination, payload)
    except FileExistsError as exc:
        raise VisualPreviewError("visual regression output must be absent") from exc
    return {**value, "output": str(destination), "mutation_attempted": False}
