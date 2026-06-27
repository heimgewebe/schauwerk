"""MCP initialization and normalized Miro tool discovery."""

from __future__ import annotations

from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl

from .auth import CallbackHandler, RedirectHandler
from .credentials import FileTokenStorage
from .errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    MiroError,
    redact_text,
)
from .models import MiroSettings, ToolCatalogue, ToolInfo


def build_oauth_provider(
    settings: MiroSettings,
    storage: FileTokenStorage,
    redirect_handler: RedirectHandler,
    callback_handler: CallbackHandler,
) -> OAuthClientProvider:
    metadata = OAuthClientMetadata(
        client_name=settings.client_name,
        redirect_uris=[AnyUrl(settings.redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=settings.scope,
    )
    return OAuthClientProvider(
        server_url=settings.server_url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=settings.timeout_seconds,
    )


def normalize_tool(tool: Any) -> ToolInfo:
    input_schema = getattr(tool, "inputSchema", None)
    output_schema = getattr(tool, "outputSchema", None)
    name = str(getattr(tool, "name", "<unknown>"))
    if not isinstance(input_schema, dict):
        raise MiroConnectionError(f"Tool {name} lacks an input schema")
    return ToolInfo(
        name=name,
        title=str(tool.title) if getattr(tool, "title", None) else None,
        description=str(tool.description) if getattr(tool, "description", None) else None,
        input_schema=input_schema,
        output_schema=output_schema if isinstance(output_schema, dict) else None,
    )


async def list_all_tools(session: ClientSession) -> list[ToolInfo]:
    cursor: str | None = None
    seen_cursors: set[str] = set()
    tools: list[ToolInfo] = []
    while True:
        page = await session.list_tools(cursor=cursor)
        tools.extend(normalize_tool(tool) for tool in page.tools)
        cursor = getattr(page, "nextCursor", None)
        if not cursor:
            break
        if cursor in seen_cursors:
            raise MiroConnectionError("Miro returned a repeated tool pagination cursor")
        seen_cursors.add(cursor)
    names = [tool.name for tool in tools]
    if len(names) != len(set(names)):
        raise MiroConnectionError("Miro returned duplicate tool names")
    return tools


def find_authorization_error(exc: BaseException) -> MiroAuthorizationRequired | None:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, MiroAuthorizationRequired):
            return current
        current = current.__cause__ or current.__context__
    return None


async def discover_tools(
    settings: MiroSettings,
    storage: FileTokenStorage,
    redirect_handler: RedirectHandler,
    callback_handler: CallbackHandler,
) -> ToolCatalogue:
    oauth = build_oauth_provider(settings, storage, redirect_handler, callback_handler)
    try:
        async with httpx.AsyncClient(
            auth=oauth,
            follow_redirects=True,
            timeout=httpx.Timeout(settings.timeout_seconds),
            headers={"User-Agent": "schauwerk/0.1"},
        ) as http_client:
            async with streamable_http_client(
                settings.server_url, http_client=http_client
            ) as (read_stream, write_stream, _session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    tools = await list_all_tools(session)
    except MiroError:
        raise
    except Exception as exc:
        authorization_error = find_authorization_error(exc)
        if authorization_error is not None:
            raise authorization_error from exc
        raise MiroConnectionError(
            f"Miro MCP discovery failed: {redact_text(exc)}"
        ) from exc

    return ToolCatalogue(
        protocol_version=str(initialized.protocolVersion),
        server_name=initialized.serverInfo.name,
        server_version=initialized.serverInfo.version,
        tools=tuple(sorted(tools, key=lambda tool: tool.name)),
    )
