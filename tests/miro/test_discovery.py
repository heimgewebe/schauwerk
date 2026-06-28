from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.discovery import (
    find_authorization_error,
    list_all_tools,
    normalize_tool,
)
from schauwerk.surfaces.miro.errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    redact_text,
)


def tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=f"Title {name}",
        description=f"Description {name}",
        inputSchema={"type": "object"},
        outputSchema=None,
    )


def test_normalize_tool() -> None:
    normalized = normalize_tool(tool("board_read"))
    assert normalized.name == "board_read"
    assert normalized.title == "Title board_read"
    assert normalized.input_schema == {"type": "object"}


def test_normalize_tool_requires_schema() -> None:
    with pytest.raises(MiroConnectionError, match="lacks an input schema"):
        normalize_tool(SimpleNamespace(name="broken", inputSchema=None))


def test_paginated_tool_listing() -> None:
    class Session:
        async def list_tools(self, cursor=None):
            if cursor is None:
                return SimpleNamespace(tools=[tool("b")], nextCursor="next")
            return SimpleNamespace(tools=[tool("a")], nextCursor=None)

    result = asyncio.run(list_all_tools(Session()))
    assert [item.name for item in result] == ["b", "a"]


def test_repeated_cursor_is_rejected() -> None:
    class Session:
        async def list_tools(self, cursor=None):
            return SimpleNamespace(tools=[tool(str(cursor))], nextCursor="same")

    with pytest.raises(MiroConnectionError, match="repeated"):
        asyncio.run(list_all_tools(Session()))


def test_duplicate_names_are_rejected() -> None:
    class Session:
        async def list_tools(self, cursor=None):
            if cursor is None:
                return SimpleNamespace(tools=[tool("same")], nextCursor="next")
            return SimpleNamespace(tools=[tool("same")], nextCursor=None)

    with pytest.raises(MiroConnectionError, match="duplicate"):
        asyncio.run(list_all_tools(Session()))


def test_authorization_error_is_found_inside_exception_group() -> None:
    expected = MiroAuthorizationRequired("renew login")
    nested = ExceptionGroup("outer", [RuntimeError("other"), ExceptionGroup("inner", [expected])])

    assert find_authorization_error(nested) is expected


def test_authorization_error_is_found_through_cause() -> None:
    expected = MiroAuthorizationRequired("renew login")
    wrapper = RuntimeError("wrapper")
    wrapper.__cause__ = expected

    assert find_authorization_error(wrapper) is expected


def test_redaction_removes_common_secret_forms() -> None:
    message = redact_text(
        "access_token=secret-value Authorization: Bearer header-value refresh_token=other"
    )
    assert "secret-value" not in message
    assert "header-value" not in message
    assert "other" not in message
