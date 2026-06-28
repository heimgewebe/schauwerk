"""Hardened MCP discovery that preserves typed failures from exception groups."""

from __future__ import annotations

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .auth import CallbackHandler, RedirectHandler
from .credentials import FileTokenStorage
from .discovery import build_oauth_provider, list_all_tools
from .errors import MiroConnectionError, MiroError, find_nested_miro_error, redact_text
from .models import MiroSettings, ToolCatalogue


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
            timeout=httpx.Timeout(settings.network_timeout_seconds),
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
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        raise MiroConnectionError(
            f"Miro MCP discovery failed: {redact_text(exc)}"
        ) from exc

    return ToolCatalogue(
        protocol_version=str(initialized.protocolVersion),
        server_name=initialized.serverInfo.name,
        server_version=initialized.serverInfo.version,
        tools=tuple(sorted(tools, key=lambda tool: tool.name)),
    )
