"""Fresh-board live tests for Miro learning-view rendering."""

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
from .layout_dsl import LayoutDslParseError, summarize_layout_dsl
from .models import MiroSettings
from .runtime import quiet_provider_stderr, threadless_dns_resolution


@dataclass(frozen=True)
class BoardCreateReceipt:
    alias: str
    reference_digest: str
    name: str
    created: bool = True
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayoutReadSummary:
    line_count: int
    frame_count: int
    connector_count: int
    table_count: int
    doc_count: int
    result_dsl_digest: str | None
    success: bool
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _board_url_from_payload(payload: dict[str, Any], content_texts: list[str]) -> str:
    candidates: list[str] = []
    for key in ("miro_url", "board_url", "url", "viewLink", "view_link"):
        value = payload.get(key)
        if isinstance(value, str):
            candidates.append(value)
    candidates.extend(content_texts)
    for value in candidates:
        if value.startswith("https://miro.com/app/board/"):
            return value
    raise MiroToolError("Miro board_create did not return a board URL")


def _content_texts(result: Any) -> list[str]:
    texts = []
    for item in getattr(result, "content", ()) or ():
        text = getattr(item, "text", None)
        if isinstance(text, str):
            texts.append(text)
    return texts


def _layout_text(result: Any, payload: dict[str, Any]) -> str:
    value = payload.get("dsl")
    if isinstance(value, str):
        return value
    return "\n".join(_content_texts(result))


async def run_board_create(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    name: str,
    description: str | None = None,
    replace_alias: bool = False,
    invocation_source: str = "schauwerk",
) -> BoardCreateReceipt:
    """Create a fresh Miro board and store it under a local allowlist alias."""

    validated_alias = validate_alias(alias)
    oauth = build_oauth_provider(
        settings, storage, _authorization_required, _authorization_required
    )
    try:
        with quiet_provider_stderr():
            async with threadless_dns_resolution():
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
                            arguments: dict[str, Any] = {
                                "name": name,
                                "invocation_source": invocation_source,
                                "is_repository": True,
                            }
                            if description:
                                arguments["description"] = description
                            result = await session.call_tool("board_create", arguments)
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(f"Miro board creation failed: {redact_text(exc)}") from exc

    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro board_create reported an error")
    payload = result_payload(result)
    url = _board_url_from_payload(payload, _content_texts(result))
    board = BoardAllowlist(settings.board_allowlist_path).add(
        validated_alias, url, replace=replace_alias
    )
    return BoardCreateReceipt(
        alias=board.alias,
        reference_digest=board.reference_digest,
        name=name,
    )


async def run_layout_read_summary(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    invocation_source: str = "schauwerk",
) -> LayoutReadSummary:
    """Read live board DSL and return a redacted structural summary."""

    validated_alias = validate_alias(alias)
    miro_url = BoardAllowlist(settings.board_allowlist_path).resolve(validated_alias)
    oauth = build_oauth_provider(
        settings, storage, _authorization_required, _authorization_required
    )
    try:
        with quiet_provider_stderr():
            async with threadless_dns_resolution():
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
                            result = await session.call_tool(
                                "layout_read",
                                {
                                    "miro_url": miro_url,
                                    "mode": "full",
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
        raise MiroConnectionError(f"Miro layout read failed: {redact_text(exc)}") from exc

    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro layout_read reported an error")
    payload = result_payload(result)
    if payload.get("success") is False or payload.get("error_code"):
        raise MiroToolError("Miro layout_read reported an error")
    text = _layout_text(result, payload)
    try:
        summary = summarize_layout_dsl(text)
    except LayoutDslParseError as exc:
        raise MiroToolError(f"Miro layout_read returned invalid DSL: {exc}") from exc
    return LayoutReadSummary(
        line_count=summary.line_count,
        frame_count=summary.count("FRAME"),
        connector_count=summary.count("CONNECTOR"),
        table_count=summary.count("TABLE"),
        doc_count=summary.count("DOC"),
        result_dsl_digest=_digest(text) if text else None,
        success=True,
    )
