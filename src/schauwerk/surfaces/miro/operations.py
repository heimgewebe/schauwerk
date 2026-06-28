"""Compatibility facade for sanitized read-only Miro operations."""

from __future__ import annotations

from typing import Any

from .credentials import FileTokenStorage
from .inspection import (
    checked_payload,
)
from .inspection import (
    inspect_boards as _inspect_boards,
)
from .inspection import (
    inspect_identity as _inspect_identity,
)
from .inspection import (
    result_payload as _result_payload,
)
from .models import MiroSettings
from .readonly import run_read_only_inspection


def result_payload(result: Any) -> dict[str, Any]:
    """Extract structured MCP output without interpretation."""
    return _result_payload(result)


def ensure_success(result: Any, tool_name: str) -> dict[str, Any]:
    """Validate a tool result without exposing provider payloads."""
    return checked_payload(result, tool_name)


async def inspect_identity(call_tool) -> dict[str, Any]:
    """Return presence-only identity evidence."""
    return (await _inspect_identity(call_tool)).to_dict()


async def inspect_boards(
    call_tool,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> dict[str, Any]:
    """Return structural board-search evidence without provider values."""
    report = await _inspect_boards(
        call_tool,
        query=query,
        owned_by_me=owned_by_me,
        limit=limit,
        max_pages=max_pages,
    )
    return report.to_dict()


async def inspect_miro(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    query: str = "",
    owned_by_me: bool = False,
    limit: int = 20,
    max_pages: int = 5,
) -> dict[str, Any]:
    """Run the typed inspection and expose only its sanitized dictionary."""
    report = await run_read_only_inspection(
        settings,
        storage,
        query=query,
        owned_by_me=owned_by_me,
        limit=limit,
        max_pages=max_pages,
    )
    return report.to_dict()
