"""Typed Miro layout application from rendered DSL."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .board_registry import BoardAllowlist, validate_alias
from .credentials import FileTokenStorage
from .discovery import build_oauth_provider
from .errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    MiroError,
    MiroToolError,
    find_nested_miro_error,
    redact_text,
)
from .inspection import result_payload
from .models import MiroSettings
from .runtime import threadless_dns_resolution


@dataclass(frozen=True)
class LayoutReceipt:
    board_alias: str
    created_count: int
    failed_count: int
    success: bool
    message: str
    result_dsl_digest: str | None
    mutation_attempted: bool = True
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _receipt(alias: str, payload: dict[str, Any]) -> LayoutReceipt:
    failed_items = payload.get("failed_items", [])
    if not isinstance(failed_items, list):
        failed_items = []
    created_count = payload.get("created_count", 0)
    if isinstance(created_count, bool) or not isinstance(created_count, int):
        created_count = 0
    success = payload.get("success") is True
    message = payload.get("message") if isinstance(payload.get("message"), str) else ""
    result_dsl = payload.get("result_dsl")
    if not success or failed_items:
        raise MiroToolError(f"Miro layout application failed: {redact_text(message)}")
    return LayoutReceipt(
        board_alias=alias,
        created_count=created_count,
        failed_count=len(failed_items),
        success=success,
        message=message,
        result_dsl_digest=_digest(result_dsl)
        if isinstance(result_dsl, str) and result_dsl
        else None,
    )


async def run_layout_create(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    dsl: str,
    invocation_source: str = "schauwerk",
) -> LayoutReceipt:
    """Apply rendered DSL to one allowlisted board and return a redacted receipt."""
    name = validate_alias(alias)
    board_reference = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    oauth = build_oauth_provider(
        settings, storage, _authorization_required, _authorization_required
    )
    try:
        async with threadless_dns_resolution():
            async with httpx.AsyncClient(
                auth=oauth,
                follow_redirects=True,
                timeout=httpx.Timeout(settings.network_timeout_seconds),
                headers={"User-Agent": "schauwerk/0.1"},
            ) as http_client:
                async with streamable_http_client(settings.server_url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                    _session_id,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            "layout_" + "create",
                            {
                                "miro_" + "url": board_reference,
                                "dsl": dsl,
                                "invocation_source": invocation_source,
                                "is_repository": True,
                            },
                        )
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(f"Miro layout application failed: {redact_text(exc)}") from exc
    return _receipt(name, result_payload(result))
