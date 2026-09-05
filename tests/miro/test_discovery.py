from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from schauwerk.surfaces.miro.discovery import (
    find_authorization_error,
    list_all_tools,
    normalize_tool,
    serialized_oauth_provider,
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


def test_persistent_provider_restores_expiry_for_stored_tokens(tmp_path) -> None:
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
    from pydantic import AnyUrl

    from schauwerk.surfaces.miro.credentials import FileTokenStorage
    from schauwerk.surfaces.miro.discovery import build_oauth_provider
    from schauwerk.surfaces.miro.models import MiroSettings

    storage = FileTokenStorage(tmp_path / "oauth.json")
    settings = MiroSettings(state_root=tmp_path / "state")
    token = OAuthToken(
        access_token="access",
        token_type="Bearer",
        expires_in=30,
        refresh_token="refresh",
    )
    client_info = OAuthClientInformationFull(
        client_id="client",
        client_secret="client-secret",
        redirect_uris=[AnyUrl("http://127.0.0.1:41739/callback")],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="Schauwerk test",
    )
    asyncio.run(storage.set_tokens(token))
    asyncio.run(storage.set_client_info(client_info))

    async def redirect(_url: str) -> None:
        raise AssertionError("redirect should not be used")

    async def callback():
        raise AssertionError("callback should not be used")

    provider = build_oauth_provider(settings, storage, redirect, callback)
    asyncio.run(provider._initialize())

    assert provider.context.token_expiry_time is not None
    assert provider.context.can_refresh_token() is True


def test_serialized_oauth_provider_blocks_a_second_live_session(tmp_path) -> None:
    from schauwerk.surfaces.miro.credentials import FileTokenStorage
    from schauwerk.surfaces.miro.models import MiroSettings

    settings = MiroSettings(state_root=tmp_path / "state")
    first = FileTokenStorage(settings.credentials_path)
    second = FileTokenStorage(settings.credentials_path)

    async def redirect(_url: str) -> None:
        return None

    async def callback():
        return "code", "state"

    async def scenario() -> None:
        async with serialized_oauth_provider(
            settings, first, redirect, callback, lock_timeout_seconds=0.5
        ):
            with pytest.raises(MiroConnectionError, match="OAuth flow is busy"):
                async with serialized_oauth_provider(
                    settings, second, redirect, callback, lock_timeout_seconds=0.05
                ):
                    raise AssertionError("second live OAuth session must not enter")

    asyncio.run(scenario())


def test_refresh_response_preserves_omitted_refresh_token_and_scope(tmp_path) -> None:
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
    from pydantic import AnyUrl

    from schauwerk.surfaces.miro.credentials import FileTokenStorage
    from schauwerk.surfaces.miro.discovery import build_oauth_provider
    from schauwerk.surfaces.miro.models import MiroSettings

    storage = FileTokenStorage(tmp_path / "oauth.json")
    settings = MiroSettings(state_root=tmp_path / "state")
    prior = OAuthToken(
        access_token="old-access",
        token_type="Bearer",
        expires_in=1,
        refresh_token="old-refresh",
        scope="boards:read boards:write",
    )
    client_info = OAuthClientInformationFull(
        client_id="client",
        client_secret="client-secret",
        redirect_uris=[AnyUrl("http://127.0.0.1:41739/callback")],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="Schauwerk test",
    )
    asyncio.run(storage.set_tokens(prior))
    asyncio.run(storage.set_client_info(client_info))

    async def redirect(_url: str) -> None:
        raise AssertionError("redirect should not be used")

    async def callback():
        raise AssertionError("callback should not be used")

    async def scenario() -> None:
        provider = build_oauth_provider(settings, storage, redirect, callback)
        await provider._initialize()
        response = httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
        assert await provider._handle_refresh_response(response) is True
        saved = await storage.get_tokens()
        assert saved is not None
        assert saved.access_token == "new-access"
        assert saved.refresh_token == "old-refresh"
        assert saved.scope == "boards:read boards:write"

    asyncio.run(scenario())
