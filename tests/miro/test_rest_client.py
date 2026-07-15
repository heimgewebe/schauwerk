from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from schauwerk.surfaces.miro.errors import MiroConnectionError, MiroCredentialError
from schauwerk.surfaces.miro.rest_client import MiroRestClient
from schauwerk.surfaces.miro.rest_credentials import (
    MiroRestSettings,
    MiroRestTokenStorage,
)

TOKEN = "rest-token-abcdefghijklmnopqrstuvwxyz-0123456789"
BOARD = "uXjVBoard="
ITEM = "123456789"


def credential(tmp_path: Path) -> tuple[MiroRestSettings, MiroRestTokenStorage]:
    settings = MiroRestSettings(state_root=tmp_path / "rest-state")
    storage = MiroRestTokenStorage(settings)
    source = tmp_path / "source-token"
    source.write_text(TOKEN + "\n", encoding="utf-8")
    source.chmod(0o600)
    storage.install_from_file(source)
    return settings, storage


def client(tmp_path: Path, handler) -> MiroRestClient:
    settings, storage = credential(tmp_path)
    return MiroRestClient(
        settings,
        storage,
        transport=httpx.MockTransport(handler),
    )


def test_doctor_reports_scopes_without_exposing_token_or_raw_ids(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/oauth-token"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            json={
                "scopes": ["boards:read", "boards:write"],
                "team": {"id": "team-private"},
                "user": {"id": "user-private"},
                "client": {"id": "client-private"},
                "type": "access_token",
            },
        )

    result = asyncio.run(client(tmp_path, handler).doctor(require_write=True))
    rendered = repr(result)
    assert result["boards_write_authorized"] is True
    assert result["scopes"] == ["boards:read", "boards:write"]
    assert result["separate_from_mcp_oauth"] is True
    assert TOKEN not in rendered
    assert "team-private" not in rendered
    assert "user-private" not in rendered
    assert "client-private" not in rendered


def test_doctor_rejects_missing_write_scope(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"scopes": ["boards:read"]})

    with pytest.raises(MiroCredentialError, match="lacks boards:write"):
        asyncio.run(client(tmp_path, handler).doctor(require_write=True))


def test_delete_reads_before_and_after_and_accepts_only_proven_absence(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/v1/oauth-token":
            return httpx.Response(200, json={"scopes": ["boards:write"]})
        if request.method == "GET" and len(calls) == 2:
            return httpx.Response(200, json={"id": ITEM, "type": "image"})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    receipt = asyncio.run(client(tmp_path, handler).delete_image(BOARD, ITEM))
    assert receipt.success is True
    assert receipt.preflight_present is True
    assert receipt.delete_status == 204
    assert receipt.postflight_absent is True
    assert receipt.reconciled_after_uncertain_delete is False
    assert calls == [
        ("GET", "/v1/oauth-token"),
        ("GET", f"/v2/boards/{BOARD}/images/{ITEM}"),
        ("DELETE", f"/v2/boards/{BOARD}/images/{ITEM}"),
        ("GET", f"/v2/boards/{BOARD}/images/{ITEM}"),
    ]


def test_uncertain_delete_is_success_only_after_absence_readback(tmp_path: Path) -> None:
    image_reads = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal image_reads
        if request.url.path == "/v1/oauth-token":
            return httpx.Response(200, json={"scopes": ["boards:write"]})
        if request.method == "DELETE":
            raise httpx.ReadTimeout("uncertain", request=request)
        image_reads += 1
        if image_reads == 1:
            return httpx.Response(200, json={"id": ITEM, "type": "image"})
        return httpx.Response(404)

    receipt = asyncio.run(client(tmp_path, handler).delete_image(BOARD, ITEM))
    assert receipt.success is True
    assert receipt.delete_status is None
    assert receipt.reconciled_after_uncertain_delete is True


def test_uncertain_delete_fails_when_item_remains(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth-token":
            return httpx.Response(200, json={"scopes": ["boards:write"]})
        if request.method == "DELETE":
            raise httpx.ReadTimeout("uncertain", request=request)
        return httpx.Response(200, json={"id": ITEM, "type": "image"})

    with pytest.raises(MiroConnectionError, match="remained present"):
        asyncio.run(client(tmp_path, handler).delete_image(BOARD, ITEM))


def test_provider_response_body_is_not_reflected_in_errors(tmp_path: Path) -> None:
    secret_body = f"provider body Authorization: Bearer {TOKEN}"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth-token":
            return httpx.Response(200, json={"scopes": ["boards:write"]})
        return httpx.Response(500, text=secret_body)

    with pytest.raises(MiroConnectionError) as captured:
        asyncio.run(client(tmp_path, handler).delete_image(BOARD, ITEM))
    assert TOKEN not in str(captured.value)
    assert secret_body not in str(captured.value)


def test_allow_absent_compensation_skips_delete(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/v1/oauth-token":
            return httpx.Response(200, json={"scopes": ["boards:write"]})
        return httpx.Response(404)

    receipt = asyncio.run(client(tmp_path, handler).delete_image(BOARD, ITEM, allow_absent=True))
    assert receipt.success is True
    assert receipt.preflight_present is False
    assert receipt.delete_status is None
    assert receipt.postflight_absent is True
    assert calls == [
        ("GET", "/v1/oauth-token"),
        ("GET", f"/v2/boards/{BOARD}/images/{ITEM}"),
    ]
