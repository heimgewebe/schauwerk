"""Small helpers for authoring current Miro layout DSL."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def quote(value: str) -> str:
    escaped = value.strip().replace("\n", "<br>").replace(chr(34), "&quot;")
    return chr(34) + escaped + chr(34)


def line(
    identifier: str,
    kind: str,
    *,
    parent: str | None = None,
    content: str,
    **attrs: object,
) -> str:
    parts = [identifier, kind]
    if parent:
        parts.append(f"parent={parent}")
    for key, value in attrs.items():
        parts.append(f"{key}={value}")
    parts.append(quote(content))
    return " ".join(parts)


def doc(identifier: str, *, parent: str | None, x: int, y: int, markdown: str) -> str:
    parent_part = f" parent={parent}" if parent else ""
    return f"{identifier} DOC{parent_part} x={x} y={y} <<<\n{markdown.strip()}\n>>>"


def table(
    identifier: str,
    *,
    parent: str | None,
    x: int,
    y: int,
    title: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> str:
    parent_part = f" parent={parent}" if parent else ""
    header = " | ".join(columns)
    body = "\n".join(" | ".join(cell.replace("|", "/") for cell in row) for row in rows)
    return (
        f"{identifier} TABLE{parent_part} x={x} y={y} {quote(title)} <<<\n"
        f"{header}\n---\n{body}\n>>>"
    )


def bullets(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
