"""Private raw-DSL Miro operations for the reviewed managed-region executor."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
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
from .runtime import quiet_provider_stderr, threadless_dns_resolution
from .snapshot_runtime import run_verified_snapshot

_MAX_DSL_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class ManagedRegionMutationReceipt:
    success: bool
    created_count: int
    updated_count: int
    deleted_count: int
    result_dsl_digest: str | None
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MiroToolError(f"Miro layout update returned an invalid {key}")
    return value


def parse_layout_read_result(result: Any) -> str:
    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro layout_read reported an error")
    payload = result_payload(result)
    if payload.get("success") is not True:
        raise MiroToolError("Miro layout_read did not succeed")
    dsl = payload.get("dsl")
    if not isinstance(dsl, str):
        raise MiroToolError("Miro layout_read did not return DSL")
    if len(dsl.encode("utf-8")) > _MAX_DSL_BYTES:
        raise MiroToolError("Miro layout_read DSL exceeds the 16 MiB limit")
    _integer(payload, "item_count")
    skipped_count = _integer(payload, "skipped_count")
    if skipped_count != 0:
        raise MiroToolError("Miro layout_read skipped unsupported board items")
    return dsl


def parse_layout_update_result(result: Any) -> ManagedRegionMutationReceipt:
    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro layout_update reported an error")
    payload = result_payload(result)
    if payload.get("success") is not True:
        message = payload.get("message") if isinstance(payload.get("message"), str) else ""
        raise MiroToolError(f"Miro layout_update failed: {redact_text(message)}")
    result_dsl = payload.get("result_dsl")
    if isinstance(result_dsl, str) and len(result_dsl.encode("utf-8")) > _MAX_DSL_BYTES:
        raise MiroToolError("Miro layout_update DSL exceeds the 16 MiB limit")
    return ManagedRegionMutationReceipt(
        success=True,
        created_count=_integer(payload, "created_count"),
        updated_count=_integer(payload, "updated_count"),
        deleted_count=_integer(payload, "deleted_count"),
        result_dsl_digest=_digest(result_dsl)
        if isinstance(result_dsl, str) and result_dsl
        else None,
    )


async def _call_layout_tool(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    name = validate_alias(alias)
    board_reference = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    oauth = build_oauth_provider(
        settings, storage, _authorization_required, _authorization_required
    )
    payload = {
        "miro_url": board_reference,
        "invocation_source": "schauwerk-sw009-live-executor",
        "is_repository": True,
        **arguments,
    }
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
                            return await session.call_tool(tool_name, payload)
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(
            f"Miro managed-region operation failed: {redact_text(exc)}"
        ) from exc


async def run_layout_read_dsl(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
) -> str:
    result = await _call_layout_tool(
        settings,
        storage,
        alias=alias,
        tool_name="layout_read",
        arguments={"mode": "full"},
    )
    return parse_layout_read_result(result)


async def run_layout_replace_text(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    old_text: str,
    new_text: str,
) -> ManagedRegionMutationReceipt:
    result = await _call_layout_tool(
        settings,
        storage,
        alias=alias,
        tool_name="layout_update",
        arguments={
            "old_string": old_text,
            "new_string": new_text,
            "replace_all": False,
        },
    )
    return parse_layout_update_result(result)


class MiroManagedRegionProvider:
    """Adapter that keeps raw provider DSL inside the transaction boundary."""

    def __init__(
        self,
        settings: MiroSettings,
        storage: FileTokenStorage,
        *,
        cached_tools: dict[str, Any],
    ) -> None:
        self.settings = settings
        self.storage = storage
        tools = cached_tools.get("tools") if isinstance(cached_tools, dict) else None
        self._capabilities = {
            item.get("name")
            for item in tools or []
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }

    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    async def snapshot(self, *, alias: str, output_path: Path) -> dict[str, Any]:
        return (
            await run_verified_snapshot(
                self.settings,
                self.storage,
                alias=alias,
                output_path=output_path,
            )
        ).to_dict()

    async def read_dsl(self, *, alias: str) -> str:
        return await run_layout_read_dsl(self.settings, self.storage, alias=alias)

    async def replace_text(
        self, *, alias: str, old_text: str, new_text: str
    ) -> dict[str, Any]:
        return (
            await run_layout_replace_text(
                self.settings,
                self.storage,
                alias=alias,
                old_text=old_text,
                new_text=new_text,
            )
        ).to_dict()
