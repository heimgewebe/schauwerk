from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from schauwerk.regie.html import APP_JS, STYLE_CSS, render_index
from schauwerk.regie.server import build_regie_server, make_regie_handler


class StubController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def state(self) -> dict:
        return {
            "schema_version": "schauwerk-regie-state.v1",
            "phase": "review",
            "review": {"title": "Private title"},
            "controls": {},
            "boundary": {"local_loopback_only": True},
        }

    def decide(self, payload: dict) -> dict:
        self.calls.append(("decision", payload))
        return {"ok": True, "decision_digest": "a" * 64}

    async def apply(self, payload: dict) -> dict:
        self.calls.append(("apply", payload))
        return {"ok": True, "receipt_digest": "b" * 64}

    async def restore(self, payload: dict) -> dict:
        self.calls.append(("restore", payload))
        return {"ok": True, "receipt_digest": "c" * 64}


def raw_request(
    handler: type,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    host: str = "127.0.0.1",
    content_type: str = "application/json",
) -> tuple[int, dict[str, str], bytes]:
    raw_body = b""
    headers = [f"Host: {host}", "Connection: close"]
    if token:
        headers.append(f"X-Schauwerk-Session: {token}")
    if body is not None:
        raw_body = json.dumps(body).encode("utf-8")
        headers.extend(
            [
                f"Content-Type: {content_type}",
                f"Content-Length: {len(raw_body)}",
            ]
        )
    request = (f"{method} {path} HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n").encode(
        "ascii"
    ) + raw_body

    client, server_socket = socket.socketpair()
    try:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        handler(
            server_socket,
            ("127.0.0.1", 43210),
            SimpleNamespace(server_name="127.0.0.1", server_port=0),
        )
        server_socket.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        client.close()
        server_socket.close()
    raw = b"".join(chunks)
    head, response_body = raw.split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    status = int(lines[0].split()[1])
    response_headers = {
        key.lower(): value.strip()
        for key, value in (line.split(":", 1) for line in lines[1:] if ":" in line)
    }
    return status, response_headers, response_body


@pytest.fixture
def handler_and_controller():
    controller = StubController()
    token = "s" * 40
    return make_regie_handler(controller, session_token=token), controller, token


def test_assets_are_local_accessible_and_do_not_embed_review_content(
    handler_and_controller,
) -> None:
    handler, _controller, token = handler_and_controller
    status, headers, body = raw_request(handler, "GET", "/")
    assert status == 200
    page = body.decode("utf-8")
    assert token not in page
    assert "Private title" not in page
    assert "https://" not in page
    assert headers["content-security-policy"].startswith("default-src 'self'")
    assert headers["cache-control"] == "no-store"

    status, _headers, body = raw_request(handler, "GET", "/style.css")
    assert status == 200
    assert body.decode("utf-8") == STYLE_CSS
    status, _headers, body = raw_request(handler, "GET", "/app.js")
    assert status == 200
    assert body.decode("utf-8") == APP_JS
    assert "X-Schauwerk-Session" in APP_JS
    assert "APPROVE_LIVE_APPLY" in render_index()
    assert "sessionStorage" in APP_JS


def test_private_state_requires_session_and_valid_loopback_host(
    handler_and_controller,
) -> None:
    handler, _controller, token = handler_and_controller
    status, _headers, body = raw_request(handler, "GET", "/api/state")
    assert status == 403
    assert json.loads(body)["error"] == "invalid Regie session"

    status, _headers, body = raw_request(handler, "GET", "/api/state", token=token)
    assert status == 200
    assert json.loads(body)["review"]["title"] == "Private title"

    status, _headers, body = raw_request(
        handler,
        "GET",
        "/api/state",
        token=token,
        host="evil.example",
    )
    assert status == 400
    assert json.loads(body)["error"] == "invalid loopback host"


def test_post_routes_require_json_token_and_dispatch_exact_payload(
    handler_and_controller,
) -> None:
    handler, controller, token = handler_and_controller
    decision = {"decisions": {"one": "approve"}}
    status, _headers, body = raw_request(
        handler,
        "POST",
        "/api/decision",
        token=token,
        body=decision,
    )
    assert status == 200
    assert json.loads(body)["decision_digest"] == "a" * 64

    status, _headers, body = raw_request(
        handler,
        "POST",
        "/api/apply",
        token=token,
        body={"confirmation": "EXECUTE_LIVE_APPLY"},
    )
    assert status == 200
    assert json.loads(body)["receipt_digest"] == "b" * 64

    status, _headers, body = raw_request(
        handler,
        "POST",
        "/api/restore",
        token=token,
        body={"confirmation": "RESTORE_LIVE_APPLY"},
    )
    assert status == 200
    assert json.loads(body)["receipt_digest"] == "c" * 64
    assert controller.calls == [
        ("decision", decision),
        ("apply", {"confirmation": "EXECUTE_LIVE_APPLY"}),
        ("restore", {"confirmation": "RESTORE_LIVE_APPLY"}),
    ]

    status, _headers, body = raw_request(
        handler,
        "POST",
        "/api/decision",
        token=token,
        body={"x": 1},
        content_type="text/plain",
    )
    assert status == 409
    assert "application/json" in json.loads(body)["error"]


def test_server_refuses_non_loopback_bind_and_uses_serial_http() -> None:
    with pytest.raises(ValueError, match="must bind"):
        build_regie_server(StubController(), host="0.0.0.0")
    server, address, _token = build_regie_server(StubController(), port=0, session_token="s" * 40)
    try:
        assert server.__class__.__name__ == "HTTPServer"
        assert address.startswith("http://127.0.0.1:")
        assert address.endswith("#" + "s" * 40)
    finally:
        server.server_close()
