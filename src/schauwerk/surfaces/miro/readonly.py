"""Stored-session, read-only Miro operations."""

from __future__ import annotations

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .credentials import FileTokenStorage
from .discovery import build_oauth_provider
from .errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    MiroError,
    find_nested_miro_error,
    redact_text,
)
from .inspection import ReadOnlyInspection, inspect_read_only
from .models import MiroSettings


async def _authorization_redirect_required(_url: str) -> None:
    raise MiroAuthorizationRequired("Miro login must be renewed")


async def _authorization_callback_required() -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


async def run_read_only_inspection(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> ReadOnlyInspection:
    """Inspect identity and board-search behavior without surface mutation."""
    oauth = build_oauth_provider(
        settings,
        storage,
        _authorization_redirect_required,
        _authorization_callback_required,
    )
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
                    await session.initialize()
                    return await inspect_read_only(
                        session.call_tool,
                        query=query,
                        owned_by_me=owned_by_me,
                        limit=limit,
                        max_pages=max_pages,
                    )
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(
            f"Miro read-only inspection failed: {redact_text(exc)}"
        ) from exc


async def inspect_default(
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> ReadOnlyInspection:
    """Run the inspection with Schauwerk's default local Miro settings."""
    settings = MiroSettings()
    storage = FileTokenStorage(settings.credentials_path)
    return await run_read_only_inspection(
        settings,
        storage,
        query=query,
        owned_by_me=owned_by_me,
        limit=limit,
        max_pages=max_pages,
    )
