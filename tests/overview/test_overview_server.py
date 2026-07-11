from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from schauwerk.overview.html import APP_JS, STYLE_CSS, render_index
from schauwerk.overview.server import build_overview_server, make_overview_handler


async def snapshot_factory() -> dict:
    return {
        "schema_version": "schauwerk-overview-snapshot.v1",
        "summary": {"project_count": 3, "provider_state": "error"},
        "projects": [{"project_id": "schauwerk"}],
    }


def raw_request(
    handler: type,
    method: str,
    path: str,
    *,
    token: str | None = None,
    host: str = "127.0.0.1",
) -> tuple[int, dict[str, str], bytes]:
    headers = [f"Host: {host}", "Connection: close"]
    if token:
        headers.append(f"X-Schauwerk-Session: {token}")
    request = (
        f"{method} {path} HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n"
    ).encode("ascii")
    client, server_socket = socket.socketpair()
    try:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        handler(
            server_socket,
            ("127.0.0.1", 43100),
            SimpleNamespace(server_name="127.0.0.1", server_port=0),
        )
        server_socket.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        client.close()
        server_socket.close()
    raw = b"".join(chunks)
    head, body = raw.split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    status = int(lines[0].split()[1])
    headers_out = {
        key.lower(): value.strip()
        for key, value in (line.split(":", 1) for line in lines[1:] if ":" in line)
    }
    return status, headers_out, body


@pytest.fixture
def handler_token():
    token = "o" * 40
    return make_overview_handler(snapshot_factory, session_token=token), token


def test_assets_are_local_token_free_and_profile_capable(handler_token) -> None:
    handler, token = handler_token
    status, headers, body = raw_request(handler, "GET", "/")
    page = body.decode()
    assert status == 200
    assert token not in page
    assert "https://" not in page
    assert headers["cache-control"] == "no-store"
    assert "form-action 'none'" in headers["content-security-policy"]

    status, _headers, body = raw_request(handler, "GET", "/style.css")
    assert status == 200
    assert body.decode() == STYLE_CSS
    status, _headers, body = raw_request(handler, "GET", "/app.js")
    assert status == 200
    assert body.decode() == APP_JS
    for marker in (
        "sessionStorage",
        "requestFullscreen",
        "refresh_seconds",
        "maximum_items_per_section",
        "profile-select",
    ):
        assert marker in APP_JS
    assert "Anzeigeprofil" in render_index()


def test_state_requires_token_and_loopback_host(handler_token) -> None:
    handler, token = handler_token
    status, _headers, body = raw_request(handler, "GET", "/api/state")
    assert status == 403
    assert json.loads(body)["error"] == "invalid overview session"
    status, _headers, body = raw_request(
        handler, "GET", "/api/state", token=token
    )
    assert status == 200
    assert json.loads(body)["summary"]["provider_state"] == "error"
    status, _headers, body = raw_request(
        handler, "GET", "/api/state", token=token, host="evil.example"
    )
    assert status == 400
    assert json.loads(body)["error"] == "invalid loopback host"


def test_service_is_read_only(handler_token) -> None:
    handler, token = handler_token
    status, _headers, body = raw_request(
        handler, "POST", "/api/state", token=token
    )
    assert status == 405
    assert json.loads(body)["error"] == "read-only service"


def test_collection_exception_is_redacted_and_bounded() -> None:
    async def exploding() -> dict:
        raise RuntimeError("fixture collection failure")

    handler = make_overview_handler(exploding, session_token="o" * 40)
    status, _headers, body = raw_request(
        handler, "GET", "/api/state", token="o" * 40
    )
    assert status == 500
    assert json.loads(body)["error"] == (
        "overview collection failed: fixture collection failure"
    )


def test_server_refuses_non_loopback_and_fragment_contains_token() -> None:
    with pytest.raises(ValueError, match="must bind"):
        build_overview_server(snapshot_factory, host="0.0.0.0")
    server, address, token = build_overview_server(
        snapshot_factory, port=0, session_token="o" * 40
    )
    try:
        assert server.__class__.__name__ == "HTTPServer"
        assert address.endswith("#" + token)
        assert address.startswith("http://127.0.0.1:")
    finally:
        server.server_close()
