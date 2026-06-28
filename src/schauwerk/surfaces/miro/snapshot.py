"""Canonical board reads for deterministic Miro snapshots."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from .errors import MiroConnectionError
from .inspection import checked_payload
from .snapshot_model import (
    SnapshotRead,
    canonical_json,
    content_digest,
    normalize_comment,
    normalize_item,
)

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]


def _ordered_records(
    records: Sequence[dict[str, Any]], *, kind: str, identity_key: str
) -> tuple[dict[str, Any], ...]:
    by_content = {}
    identities = set()
    for record in records:
        identity = record.get(identity_key)
        if isinstance(identity, str):
            if identity in identities:
                raise MiroConnectionError(f"Miro returned a duplicate {kind} reference")
            identities.add(identity)
        marker = canonical_json(record)
        if marker in by_content:
            raise MiroConnectionError(f"Miro returned a duplicate {kind} record")
        by_content[marker] = record
    return tuple(by_content[key] for key in sorted(by_content))


async def read_items(
    call_tool: ToolCaller,
    *,
    miro_url: str,
    limit: int = 100,
    max_pages: int = 20,
) -> tuple[tuple[dict[str, Any], ...], int]:
    if not 10 <= limit <= 1000:
        raise ValueError("item limit must be between 10 and 1000")
    cursor: str | None = None
    seen_cursors: set[str] = set()
    seen_pages: set[str] = set()
    items: list[dict[str, Any]] = []
    pages = 0
    has_more = False
    while pages < max_pages:
        arguments: dict[str, Any] = {
            "miro_url": miro_url,
            "limit": limit,
            "is_repository": True,
        }
        if cursor:
            arguments["cursor"] = cursor
        payload = checked_payload(
            await call_tool("board_list_items", arguments), "board_list_items"
        )
        pages += 1
        records = payload.get("data")
        if not isinstance(records, list) or any(
            not isinstance(record, Mapping) for record in records
        ):
            raise MiroConnectionError("Miro item page has an invalid data shape")
        marker = content_digest({"records": records})
        if marker in seen_pages:
            raise MiroConnectionError("Miro returned a repeated item page")
        seen_pages.add(marker)
        items.extend(normalize_item(record) for record in records)
        has_more = payload.get("has_more") is True
        next_cursor = payload.get("nextCursor")
        if not has_more:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise MiroConnectionError("Miro item pagination has no next cursor")
        if next_cursor in seen_cursors:
            raise MiroConnectionError("Miro returned a repeated item cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if has_more:
        raise MiroConnectionError("Miro item pagination exceeded the page limit")
    return _ordered_records(items, kind="item", identity_key="ref"), pages


async def read_comments(
    call_tool: ToolCaller,
    *,
    miro_url: str,
    limit: int = 50,
    max_pages: int = 20,
) -> tuple[tuple[dict[str, Any], ...], int]:
    if not 1 <= limit <= 50:
        raise ValueError("comment limit must be between 1 and 50")
    offset = 0
    comments: list[dict[str, Any]] = []
    pages = 0
    has_more = False
    while pages < max_pages:
        payload = checked_payload(
            await call_tool(
                "comment_list_comments",
                {
                    "miro_url": miro_url,
                    "limit": limit,
                    "offset": offset,
                    "is_repository": True,
                },
            ),
            "comment_list_comments",
        )
        pages += 1
        records = payload.get("data", [])
        if not isinstance(records, list) or any(
            not isinstance(record, Mapping) for record in records
        ):
            raise MiroConnectionError("Miro comment page has an invalid data shape")
        comments.extend(normalize_comment(record) for record in records)
        has_more = payload.get("has_more") is True
        if not has_more:
            break
        if not records:
            raise MiroConnectionError("Miro returned an empty comment page with more data")
        offset += len(records)
    if has_more:
        raise MiroConnectionError("Miro comment pagination exceeded the page limit")
    return _ordered_records(comments, kind="comment", identity_key="id"), pages


async def read_board_snapshot(
    call_tool: ToolCaller,
    *,
    miro_url: str,
    item_limit: int = 100,
    comment_limit: int = 50,
    max_pages: int = 20,
    include_comments: bool = True,
) -> SnapshotRead:
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")
    items, item_pages = await read_items(
        call_tool, miro_url=miro_url, limit=item_limit, max_pages=max_pages
    )
    if include_comments:
        comments, comment_pages = await read_comments(
            call_tool, miro_url=miro_url, limit=comment_limit, max_pages=max_pages
        )
    else:
        comments, comment_pages = (), 0
    return SnapshotRead(items, comments, item_pages, comment_pages)
