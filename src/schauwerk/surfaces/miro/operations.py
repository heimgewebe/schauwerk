"""Read-only stored-session Miro operations."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .credentials import FileTokenStorage
from .discovery import build_oauth_provider, find_authorization_error
from .errors import MiroAuthorizationRequired, MiroConnectionError, MiroError, redact_text
from .models import MiroSettings

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]
IDENTITY_FIELDS = ("org_id", "team_id", "user_id", "workspace_id")


async def _reject_auth(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired(
        "Stored Miro authorization is unavailable; run `schauwerk miro login`"
    )


def result_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return {}


def ensure_success(result: Any, tool_name: str) -> dict[str, Any]:
    if bool(getattr(result, "isError", False)):
        raise MiroConnectionError(f"Miro tool {tool_name} reported an error")
    return result_payload(result)


async def inspect_identity(call_tool: ToolCaller) -> dict[str, Any]:
    payload = ensure_success(
        await call_tool("user_who_am_i", {"is_repository": True}),
        "user_who_am_i",
    )
    present = sorted(field for field in IDENTITY_FIELDS if payload.get(field))
    return {
        "call_ok": True,
        "expected_fields": list(IDENTITY_FIELDS),
        "present_fields": present,
        "complete": present == sorted(IDENTITY_FIELDS),
    }


async def inspect_boards(
    call_tool: ToolCaller,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> dict[str, Any]:
    if not 1 <= limit <= 50 or not 1 <= max_pages <= 20:
        raise ValueError("invalid inspection bounds")
    offset = 0
    seen: set[int] = set()
    names: list[str] = []
    total: int | None = None
    has_more = False
    cursor_present = False
    pages = 0
    anomalies: list[str] = []
    while pages < max_pages:
        if offset in seen:
            anomalies.append("repeated_offset")
            break
        seen.add(offset)
        pages += 1
        payload = ensure_success(
            await call_tool(
                "board_search_boards",
                {
                    "query": query,
                    "include_content": False,
                    "owned_by_me": owned_by_me,
                    "limit": limit,
                    "offset": offset,
                    "is_repository": True,
                },
            ),
            "board_search_boards",
        )
        reported = payload.get("total")
        if isinstance(reported, int):
            if total is not None and reported != total:
                anomalies.append("reported_total_changed")
            total = reported
        records = payload.get("data")
        for record in records if isinstance(records, list) else []:
            if isinstance(record, dict) and isinstance(record.get("name"), str):
                if record["name"] not in names:
                    names.append(record["name"])
        has_more = bool(payload.get("has_more"))
        cursor = payload.get("nextCursor")
        cursor_present = isinstance(cursor, str)
        if not has_more:
            break
        if not cursor_present:
            anomalies.append("missing_next_cursor")
            break
        try:
            next_offset = int(cursor)
        except ValueError:
            anomalies.append("non_numeric_next_cursor")
            break
        if next_offset <= offset:
            anomalies.append("non_advancing_next_cursor")
            break
        offset = next_offset
    if has_more and pages >= max_pages:
        anomalies.append("page_limit_reached")
    if total is not None and len(names) < total:
        anomalies.append("reported_results_without_records")
    return {
        "query": query,
        "owned_by_me": owned_by_me,
        "pages_read": pages,
        "reported_total": total,
        "returned_count": len(names),
        "board_names": names,
        "has_more": has_more,
        "next_cursor_present": cursor_present,
        "complete": not anomalies and not has_more,
        "anomalies": sorted(set(anomalies)),
    }


async def inspect_miro(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    query: str = "",
    owned_by_me: bool = False,
    max_pages: int = 5,
) -> dict[str, Any]:
    oauth = build_oauth_provider(settings, storage, _reject_auth, _reject_auth)
    try:
        async with httpx.AsyncClient(
            auth=oauth,
            follow_redirects=True,
            timeout=httpx.Timeout(settings.network_timeout_seconds),
            headers={"User-Agent": "schauwerk/0.1"},
        ) as http_client:
            async with streamable_http_client(
                settings.server_url, http_client=http_client
            ) as (read_stream, write_stream, _session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    identity = await inspect_identity(session.call_tool)
                    boards = await inspect_boards(
                        session.call_tool,
                        query=query,
                        owned_by_me=owned_by_me,
                        max_pages=max_pages,
                    )
    except MiroError:
        raise
    except Exception as exc:
        authorization_error = find_authorization_error(exc)
        if authorization_error is not None:
            raise authorization_error from exc
        raise MiroConnectionError(
            f"Miro inspection failed: {redact_text(exc)}"
        ) from exc
    return {
        "server": {
            "name": initialized.serverInfo.name,
            "version": initialized.serverInfo.version,
            "protocol_version": str(initialized.protocolVersion),
        },
        "identity": identity,
        "boards": boards,
        "read_only": True,
    }
