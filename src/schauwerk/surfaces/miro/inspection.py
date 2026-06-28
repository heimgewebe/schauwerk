"""Sanitized, typed interpretation of read-only Miro tool results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .errors import MiroToolError

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]
_IDENTITY_FIELDS = ("org_id", "team_id", "user_id", "workspace_id")


@dataclass(frozen=True)
class IdentityInspection:
    """Presence-only identity proof; never contains identity values."""

    call_ok: bool
    expected_field_count: int
    present_field_count: int
    missing_fields: tuple[str, ...]
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoardSearchInspection:
    """Structural board-search proof without names, URLs, IDs, or board content."""

    query_applied: bool
    owned_by_me: bool
    pages_read: int
    reported_total: int | None
    records_seen: int
    unique_records: int
    duplicate_records: int
    pagination_complete: bool
    consistent: bool
    anomalies: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadOnlyInspection:
    """One bounded, mutation-free Miro operational inspection."""

    identity: IdentityInspection
    boards: BoardSearchInspection
    mutation_attempted: bool = False
    sanitized: bool = True

    @property
    def ok(self) -> bool:
        return self.identity.complete and self.boards.pagination_complete and self.boards.consistent

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mutation_attempted": self.mutation_attempted,
            "sanitized": self.sanitized,
            "identity": self.identity.to_dict(),
            "boards": self.boards.to_dict(),
        }


def result_payload(result: Any) -> dict[str, Any]:
    """Read structured MCP output or a JSON text fallback."""
    if isinstance(result, Mapping):
        return dict(result)
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, Mapping):
        return dict(structured)
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return {}


def checked_payload(result: Any, tool_name: str) -> dict[str, Any]:
    """Reject MCP/provider-declared failures without echoing provider details."""
    if bool(getattr(result, "isError", False)):
        raise MiroToolError(f"Miro tool {tool_name} reported an error")
    payload = result_payload(result)
    if payload.get("success") is False or payload.get("error_code"):
        raise MiroToolError(f"Miro tool {tool_name} reported an error")
    return payload


def _record_fingerprint(record: Mapping[str, Any]) -> str:
    """Create an internal comparison key without exposing provider values."""
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def inspect_identity(call_tool: ToolCaller) -> IdentityInspection:
    result = await call_tool("user_who_am_i", {"is_repository": True})
    payload = checked_payload(result, "user_who_am_i")
    missing = tuple(field for field in _IDENTITY_FIELDS if not payload.get(field))
    return IdentityInspection(
        call_ok=True,
        expected_field_count=len(_IDENTITY_FIELDS),
        present_field_count=len(_IDENTITY_FIELDS) - len(missing),
        missing_fields=missing,
        complete=not missing,
    )


async def inspect_boards(
    call_tool: ToolCaller,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> BoardSearchInspection:
    """Follow bounded offset pagination and diagnose contradictory responses."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if not 1 <= max_pages <= 20:
        raise ValueError("max_pages must be between 1 and 20")

    offset = 0
    seen_offsets: set[int] = set()
    seen_records: set[str] = set()
    seen_pages: set[tuple[str, ...]] = set()
    reported_total: int | None = None
    anomalies: set[str] = set()
    records_seen = 0
    duplicate_records = 0
    has_more = False
    pages = 0

    while pages < max_pages:
        if offset in seen_offsets:
            anomalies.add("repeated_offset")
            break
        seen_offsets.add(offset)
        pages += 1

        result = await call_tool(
            "board_search_boards",
            {
                "query": query,
                "include_content": False,
                "owned_by_me": owned_by_me,
                "limit": limit,
                "offset": offset,
                "is_repository": True,
            },
        )
        payload = checked_payload(result, "board_search_boards")

        total = payload.get("total")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            anomalies.add("invalid_reported_total")
        elif reported_total is not None and total != reported_total:
            anomalies.add("reported_total_changed")
        else:
            reported_total = total

        raw_records = payload.get("data")
        if not isinstance(raw_records, list):
            anomalies.add("invalid_data_shape")
            records: list[Mapping[str, Any]] = []
        else:
            records = [record for record in raw_records if isinstance(record, Mapping)]
            if len(records) != len(raw_records):
                anomalies.add("invalid_record_shape")

        page_fingerprints = tuple(_record_fingerprint(record) for record in records)
        if page_fingerprints and page_fingerprints in seen_pages:
            anomalies.add("repeated_page")
            break
        seen_pages.add(page_fingerprints)

        records_seen += len(records)
        for fingerprint in page_fingerprints:
            if fingerprint in seen_records:
                duplicate_records += 1
            else:
                seen_records.add(fingerprint)
        if duplicate_records:
            anomalies.add("duplicate_records_across_pages")

        raw_has_more = payload.get("has_more")
        if not isinstance(raw_has_more, bool):
            anomalies.add("invalid_has_more")
        has_more = bool(raw_has_more)
        cursor = payload.get("nextCursor")

        if not has_more:
            if cursor not in (None, ""):
                anomalies.add("cursor_without_more_results")
            break

        if not records:
            anomalies.add("empty_page_with_more_results")
            break
        if len(records) < limit:
            anomalies.add("short_page_with_more_results")
        if cursor in (None, ""):
            anomalies.add("more_results_without_cursor")
        elif isinstance(cursor, str):
            try:
                cursor_offset = int(cursor)
            except ValueError:
                anomalies.add("opaque_cursor_for_offset_input")
            else:
                expected_offset = offset + len(records)
                if cursor_offset != expected_offset:
                    anomalies.add("cursor_offset_mismatch")
        else:
            anomalies.add("invalid_next_cursor")

        next_offset = offset + len(records)
        if next_offset <= offset:
            anomalies.add("non_advancing_offset")
            break
        offset = next_offset

    if has_more and pages >= max_pages:
        anomalies.add("page_limit_reached")

    pagination_complete = not has_more
    if pagination_complete and reported_total is not None:
        if records_seen != reported_total:
            anomalies.add("reported_total_record_count_mismatch")
        if len(seen_records) != reported_total:
            anomalies.add("reported_total_unique_count_mismatch")
    elif reported_total is not None and records_seen >= reported_total and has_more:
        anomalies.add("more_results_after_reported_total")

    ordered_anomalies = tuple(sorted(anomalies))
    return BoardSearchInspection(
        query_applied=bool(query),
        owned_by_me=owned_by_me,
        pages_read=pages,
        reported_total=reported_total,
        records_seen=records_seen,
        unique_records=len(seen_records),
        duplicate_records=duplicate_records,
        pagination_complete=pagination_complete,
        consistent=not ordered_anomalies,
        anomalies=ordered_anomalies,
    )


async def inspect_read_only(
    call_tool: ToolCaller,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> ReadOnlyInspection:
    identity = await inspect_identity(call_tool)
    boards = await inspect_boards(
        call_tool,
        query=query,
        owned_by_me=owned_by_me,
        limit=limit,
        max_pages=max_pages,
    )
    return ReadOnlyInspection(identity=identity, boards=boards)
