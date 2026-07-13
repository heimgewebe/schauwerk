"""Reusable constructors for caller-composed Visual System v2 boards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def clip_text(value: str, maximum: int = 48) -> str:
    """Normalize and visibly truncate one display cell."""

    if maximum < 2:
        raise ValueError("visual text maximum must be at least two characters")
    text = " ".join(value.split())
    if len(text) <= maximum:
        return text
    return text[: maximum - 1].rstrip() + "…"


def bounded_rows(
    values: Sequence[Mapping[str, str]],
    fields: tuple[str, ...],
    *,
    maximum_rows: int = 3,
    maximum_cell_characters: int = 48,
) -> tuple[tuple[str, ...], ...]:
    """Select readable rows and expose, rather than hide, omitted items."""

    if not fields:
        raise ValueError("visual table fields must not be empty")
    if maximum_rows < 1:
        raise ValueError("visual table maximum_rows must be positive")
    shown = values[:maximum_rows]
    rows = [
        tuple(clip_text(item[field], maximum_cell_characters) for field in fields) for item in shown
    ]
    omitted = len(values) - len(shown)
    if omitted:
        rows.append(tuple([f"+ {omitted} weitere im Snapshot"] + ["—" for _ in fields[1:]]))
    return tuple(rows)


def text_object(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    content: str,
    *,
    font: str,
    color: str = "ink",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "text",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": content,
        "font_level": font,
        "color_role": color,
    }


def shape_object(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    content: str,
    *,
    color: str,
    shape: str = "round_rectangle",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "shape",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": content,
        "font_level": "body",
        "color_role": color,
        "shape": shape,
    }


def table_object(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    *,
    color: str = "ink",
) -> dict[str, Any]:
    if not columns or not rows:
        raise ValueError("visual tables require columns and rows")
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("visual table rows must match the declared columns")
    return {
        "id": identifier,
        "kind": "table",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "title": title,
        "columns": list(columns),
        "rows": [list(row) for row in rows],
        "content": " ".join([title, *columns, *(cell for row in rows for cell in row)]),
        "font_level": "body",
        "color_role": color,
        "provider_geometry": "auto_sized",
    }


def document_object(
    identifier: str,
    x: int,
    y: int,
    w: int,
    h: int,
    markdown: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "doc",
        "role": "source",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": markdown,
        "font_level": "body",
        "color_role": "evidence",
        "provider_geometry": "auto_sized",
    }


def connector_object(identifier: str, source: str, target: str, label: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "connector",
        "role": "relation",
        "from": source,
        "to": target,
        "content": label,
        "font_level": "caption",
        "color_role": "structure",
    }


def frame(
    identifier: str,
    number: int,
    role: str,
    title: str,
    thesis: str,
    x: int,
) -> dict[str, Any]:
    """Create one canonical 1120×630 narrative frame with title and thesis."""

    return {
        "id": identifier,
        "number": number,
        "role": role,
        "title": title,
        "x": x,
        "y": 0,
        "w": 1120,
        "h": 630,
        "background_role": "ink",
        "objects": [
            text_object(
                f"{identifier}_title",
                "title",
                80,
                60,
                960,
                80,
                title,
                font="display",
            ),
            text_object(
                f"{identifier}_thesis",
                "thesis",
                80,
                160,
                960,
                80,
                thesis,
                font="heading",
            ),
        ],
    }
