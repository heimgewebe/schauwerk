"""Loopback-only read-only HTTP delivery for SW-013 publication links."""

from __future__ import annotations

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .model import PublicationError
from .store import resolve_publication_file


class PublicationHTTPServer(HTTPServer):
    def __init__(self, address: tuple[str, int], store_root: Path):
        self.store_root = store_root
        super().__init__(address, PublicationRequestHandler)


class PublicationRequestHandler(BaseHTTPRequestHandler):
    server: PublicationHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        payload: bytes,
        content_type: str,
        *,
        head_only: bool = False,
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_json(
        self, status: HTTPStatus, value: dict[str, Any], *, head_only: bool = False
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        self._send_bytes(
            status,
            payload,
            "application/json; charset=utf-8",
            head_only=head_only,
        )

    def _route(self, *, head_only: bool) -> None:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": "query_not_supported"}, head_only=head_only
            )
            return
        decoded = unquote(parsed.path)
        if decoded == "/":
            self._send_json(
                HTTPStatus.OK,
                {
                    "schema_version": "schauwerk-publication-service.v1",
                    "service": "schauwerk-publication",
                    "loopback_only": True,
                    "read_only": True,
                    "publication_path_template": "/p/{stable_slug}/",
                },
                head_only=head_only,
            )
            return
        parts = decoded.split("/")
        if len(parts) < 4 or parts[0] != "" or parts[1] != "p" or not parts[2]:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, head_only=head_only)
            return
        slug = parts[2]
        tail = parts[3:]
        if any(item in {"", ".", ".."} for item in tail[:-1]) or len(tail) > 1:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, head_only=head_only)
            return
        name = tail[0] if tail and tail[0] else None
        try:
            status, payload, content_type = resolve_publication_file(
                self.server.store_root,
                slug,
                name,
            )
        except PublicationError as exc:
            message = str(exc)
            if message in {"publication is withdrawn", "publication is expired"}:
                code = HTTPStatus.GONE
            elif message == "publication is scheduled":
                code = HTTPStatus.TOO_EARLY
            elif "does not exist" in message or "not declared" in message:
                code = HTTPStatus.NOT_FOUND
            else:
                code = HTTPStatus.CONFLICT
            self._send_json(code, {"error": message}, head_only=head_only)
            return
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("ETag", f'"{status["object_digest"]}"')
        self.send_header("X-Schauwerk-Publication-Version", status["version"])
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def do_GET(self) -> None:
        self._route(head_only=False)

    def do_HEAD(self) -> None:
        self._route(head_only=True)

    def _reject_write(self) -> None:
        payload = b'{"error":"read_only"}\n'
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self._security_headers()
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Connection", "close")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_POST(self) -> None:
        self._reject_write()

    def do_PUT(self) -> None:
        self._reject_write()

    def do_PATCH(self) -> None:
        self._reject_write()

    def do_DELETE(self) -> None:
        self._reject_write()

    def do_OPTIONS(self) -> None:
        self._reject_write()


def create_publication_server(store_root: Path, *, port: int = 0) -> PublicationHTTPServer:
    return PublicationHTTPServer(("127.0.0.1", port), store_root)


def serve_publications(
    store_root: Path, *, port: int = 0, open_browser: bool = True
) -> dict[str, Any]:
    server = create_publication_server(store_root, port=port)
    host, actual_port = server.server_address
    url = f"http://{host}:{actual_port}/"
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {
        "schema_version": "schauwerk-publication-server-stop-receipt.v1",
        "ok": True,
        "loopback_only": True,
        "read_only": True,
        "provider_mutation_attempted": False,
    }
