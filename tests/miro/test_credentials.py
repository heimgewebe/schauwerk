from __future__ import annotations

import asyncio
import json
import os

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from schauwerk.surfaces.miro.credentials import FileTokenStorage, write_json_owner_only
from schauwerk.surfaces.miro.errors import MiroCredentialError


def sample_token() -> OAuthToken:
    return OAuthToken(
        access_token="test-access-value",
        token_type="Bearer",
        expires_in=3600,
        scope="boards:read boards:write",
        refresh_token="test-refresh-value",
    )


def sample_client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="test-client",
        client_secret="test-secret-value",
        redirect_uris=[AnyUrl("http://127.0.0.1:41739/callback")],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="Schauwerk test",
    )


def test_round_trip_is_atomic_and_owner_only(tmp_path) -> None:
    path = tmp_path / "state" / "oauth.json"
    storage = FileTokenStorage(path)
    asyncio.run(storage.set_tokens(sample_token()))
    asyncio.run(storage.set_client_info(sample_client()))

    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
    assert asyncio.run(storage.get_tokens()).access_token == "test-access-value"
    assert asyncio.run(storage.get_client_info()).client_id == "test-client"
    assert storage.summary()["has_tokens"] is True
    assert storage.summary()["has_client_info"] is True
    assert "test-access-value" not in repr(storage)


def test_corrupt_state_fails_without_echoing_content(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text("not-json-test-access-value", encoding="utf-8")
    os.chmod(path, 0o600)
    storage = FileTokenStorage(path)

    with pytest.raises(MiroCredentialError) as captured:
        asyncio.run(storage.get_tokens())
    assert "test-access-value" not in str(captured.value)


def test_insecure_permissions_are_rejected(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text("{}\n", encoding="utf-8")
    os.chmod(path, 0o644)

    with pytest.raises(MiroCredentialError, match="unsafe permissions"):
        FileTokenStorage(path).summary()


def test_clear_removes_only_owned_state(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    sibling = tmp_path / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")
    storage = FileTokenStorage(path)
    asyncio.run(storage.set_tokens(sample_token()))

    assert storage.clear() is True
    assert storage.clear() is False
    assert not path.exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_owner_only_json_writer(tmp_path) -> None:
    path = tmp_path / "catalogue.json"
    write_json_owner_only(path, {"tools": ["one"]})

    assert json.loads(path.read_text(encoding="utf-8")) == {"tools": ["one"]}
    assert path.stat().st_mode & 0o077 == 0
