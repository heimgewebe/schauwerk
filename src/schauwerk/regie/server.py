"""Loopback-only HTTP server for the local Regie interface."""

from __future__ import annotations

import asyncio
import json
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from schauwerk.surfaces.miro.errors import redact_text

from .html import APP_JS, STYLE_CSS, render_index
from .service import RegieController

_MAX_REQUEST_BYTES = 128 * 1024
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})


def _host_name(value: str) -> str:
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.split(":", 1)[0]


def make_regie_handler(
    controller: RegieController, *, session_token: str
) -> type[BaseHTTPRequestHandler]:
    token = session_token
    if len(token) < 32:
        raise ValueError("Regie session token is too short")

    class Handler(BaseHTTPRequestHandler):
        server_version = "SchauwerkRegie/1"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _security_headers(self, *, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'self'",
            )

        def _send_bytes(self, status: HTTPStatus, body: bytes, *, content_type: str) -> None:
            self.send_response(status)
            self._security_headers(content_type=content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, value: Any) -> None:
            body = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            self._send_bytes(status, body, content_type="application/json; charset=utf-8")

        def _valid_host(self) -> bool:
            return _host_name(self.headers.get("Host", "")) in _ALLOWED_HOSTS

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-Schauwerk-Session", "")
            return secrets.compare_digest(supplied, token)

        def _reject_if_invalid_host(self) -> bool:
            if self._valid_host():
                return False
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid loopback host"})
            return True

        def _require_session(self) -> bool:
            if self._authorized():
                return True
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid Regie session"})
            return False

        def _read_json(self) -> dict[str, Any]:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Regie requests require application/json")
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "")
            except ValueError as exc:
                raise ValueError("Regie request length is invalid") from exc
            if not 2 <= length <= _MAX_REQUEST_BYTES:
                raise ValueError("Regie request size is invalid")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("Regie request JSON is invalid") from exc
            if not isinstance(value, dict):
                raise ValueError("Regie request must contain an object")
            return value

        def do_GET(self) -> None:
            if self._reject_if_invalid_host():
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send_bytes(
                    HTTPStatus.OK,
                    render_index().encode("utf-8"),
                    content_type="text/html; charset=utf-8",
                )
                return
            if path == "/style.css":
                self._send_bytes(
                    HTTPStatus.OK,
                    STYLE_CSS.encode("utf-8"),
                    content_type="text/css; charset=utf-8",
                )
                return
            if path == "/app.js":
                self._send_bytes(
                    HTTPStatus.OK,
                    APP_JS.encode("utf-8"),
                    content_type="text/javascript; charset=utf-8",
                )
                return
            if path == "/healthz":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "schauwerk-regie",
                        "loopback_only": True,
                    },
                )
                return
            if path == "/api/state":
                if not self._require_session():
                    return
                self._json(HTTPStatus.OK, controller.state())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            if self._reject_if_invalid_host() or not self._require_session():
                return
            path = self.path.split("?", 1)[0]
            try:
                payload = self._read_json()
                if path == "/api/decision":
                    result = controller.decide(payload)
                elif path == "/api/apply":
                    result = asyncio.run(controller.apply(payload))
                elif path == "/api/restore":
                    result = asyncio.run(controller.restore(payload))
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
            except ValueError as exc:
                self._json(HTTPStatus.CONFLICT, {"error": redact_text(exc)})
                return
            except Exception as exc:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"Regie operation failed: {redact_text(exc)}"},
                )
                return
            self._json(HTTPStatus.OK, result)

    return Handler


def build_regie_server(
    controller: RegieController,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    session_token: str | None = None,
) -> tuple[HTTPServer, str, str]:
    if host != "127.0.0.1":
        raise ValueError("Regie server must bind to 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Regie port is invalid")
    token = session_token or secrets.token_urlsafe(32)
    handler = make_regie_handler(controller, session_token=token)
    server = HTTPServer((host, port), handler)
    address = f"http://{host}:{server.server_address[1]}/#{token}"
    return server, address, token


def serve_regie(
    controller: RegieController,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> None:
    server, address, _token = build_regie_server(controller, host=host, port=port)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
