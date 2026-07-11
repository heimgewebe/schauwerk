"""Loopback-only read-only server for overview and live views."""

from __future__ import annotations

import asyncio
import json
import secrets
import webbrowser
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from schauwerk.surfaces.miro.errors import redact_text

from .html import APP_JS, STYLE_CSS, render_index

SnapshotFactory = Callable[[], Awaitable[dict[str, Any]]]
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})


def _host_name(value: str) -> str:
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.split(":", 1)[0]


def make_overview_handler(
    snapshot_factory: SnapshotFactory, *, session_token: str
) -> type[BaseHTTPRequestHandler]:
    if len(session_token) < 32:
        raise ValueError("overview session token is too short")
    token = session_token

    class Handler(BaseHTTPRequestHandler):
        server_version = "SchauwerkOverview/1"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'none'",
            )

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self._headers(content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, value: Any) -> None:
            body = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()
            self._send(status, body, "application/json; charset=utf-8")

        def _valid_host(self) -> bool:
            return _host_name(self.headers.get("Host", "")) in _ALLOWED_HOSTS

        def _authorized(self) -> bool:
            return secrets.compare_digest(
                self.headers.get("X-Schauwerk-Session", ""), token
            )

        def do_GET(self) -> None:
            if not self._valid_host():
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid loopback host"})
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(
                    HTTPStatus.OK,
                    render_index().encode(),
                    "text/html; charset=utf-8",
                )
                return
            if path == "/style.css":
                self._send(
                    HTTPStatus.OK, STYLE_CSS.encode(), "text/css; charset=utf-8"
                )
                return
            if path == "/app.js":
                self._send(
                    HTTPStatus.OK,
                    APP_JS.encode(),
                    "text/javascript; charset=utf-8",
                )
                return
            if path == "/healthz":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "schauwerk-overview",
                        "loopback_only": True,
                        "read_only": True,
                    },
                )
                return
            if path != "/api/state":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if not self._authorized():
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid overview session"})
                return
            try:
                value = asyncio.run(snapshot_factory())
            except Exception as exc:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"overview collection failed: {redact_text(exc)}"},
                )
                return
            self._json(HTTPStatus.OK, value)

        def do_POST(self) -> None:
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read-only service"})

    return Handler


def build_overview_server(
    snapshot_factory: SnapshotFactory,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    session_token: str | None = None,
) -> tuple[HTTPServer, str, str]:
    if host != "127.0.0.1":
        raise ValueError("overview server must bind to 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("overview port is invalid")
    token = session_token or secrets.token_urlsafe(32)
    server = HTTPServer(
        (host, port),
        make_overview_handler(snapshot_factory, session_token=token),
    )
    address = f"http://{host}:{server.server_address[1]}/#{token}"
    return server, address, token


def serve_overview(
    snapshot_factory: SnapshotFactory,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> None:
    server, address, _token = build_overview_server(snapshot_factory, port=port)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
