"""Loopback-only static delivery for a verified Miro companion bundle."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import stat
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

MIRO_STATIC_SCRIPT_SOURCE = "https://miro.com/app/static/"
PUBLIC_FILES = (
    "index.html",
    "panel.html",
    "app.js",
    "panel.js",
    "core.js",
    "styles.css",
    "app-icon-outline.svg",
    "app-icon-color.svg",
    "config.json",
    "build-receipt.json",
)
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}
REQUIRED_HEADERS = {
    "Content-Security-Policy",
    "Permissions-Policy",
    "Referrer-Policy",
    "X-Content-Type-Options",
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_BYTES = 8 * 1024 * 1024


class CompanionServerError(ValueError):
    """The server input or verified bundle is unsafe."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_root(path: str | Path) -> Path:
    root = Path(path).expanduser().absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise CompanionServerError("bundle root is unsafe")
    if not root.is_dir():
        raise CompanionServerError("bundle root is missing")
    return root


def _open_bundle_root(root: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(root, flags)
    except OSError as exc:
        raise CompanionServerError("bundle root cannot be opened safely") from exc


def _read_regular_file(directory_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise CompanionServerError(f"bundle file is unsafe or missing: {name}") from exc
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise CompanionServerError(f"bundle file is not an independent regular file: {name}")
        if before.st_size > MAX_FILE_BYTES:
            raise CompanionServerError(f"bundle file exceeds the size limit: {name}")
        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining:
            chunk = os.read(file_fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(file_fd)
        stable = (
            before.st_ino == after.st_ino
            and before.st_dev == after.st_dev
            and before.st_size == after.st_size == len(payload)
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns
        )
        if not stable:
            raise CompanionServerError(f"bundle file changed while being read: {name}")
        if len(payload) > MAX_FILE_BYTES:
            raise CompanionServerError(f"bundle file exceeds the size limit: {name}")
        return payload
    finally:
        os.close(file_fd)


def _parse_headers(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CompanionServerError("header contract must be UTF-8") from exc
    if not lines or lines[0] != "/*":
        raise CompanionServerError("header contract must contain one global rule")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line.startswith("  ") or ":" not in line:
            raise CompanionServerError("header contract contains an invalid line")
        name, value = line.strip().split(":", 1)
        value = value.strip()
        invalid_control = any(ord(character) < 32 or ord(character) == 127 for character in value)
        if not name or not value or name in headers or invalid_control:
            raise CompanionServerError("header contract contains an invalid header")
        headers[name] = value
    if set(headers) != REQUIRED_HEADERS:
        raise CompanionServerError("header contract does not match the required response headers")
    csp = headers["Content-Security-Policy"]
    required_csp = (
        "default-src 'self'",
        MIRO_STATIC_SCRIPT_SOURCE,
        "frame-ancestors https://miro.com https://*.miro.com",
    )
    if any(token not in csp for token in required_csp):
        raise CompanionServerError("header contract does not permit the required Miro embedding")
    if headers["X-Content-Type-Options"].lower() != "nosniff":
        raise CompanionServerError("header contract must disable content sniffing")
    return headers


def verify_server_bundle(path: str | Path) -> dict[str, Any]:
    root = _safe_root(path)
    expected_files = {*PUBLIC_FILES[:-1], "_headers"}
    allowed = {*expected_files, "build-receipt.json"}
    directory_fd = _open_bundle_root(root)
    try:
        try:
            observed = set(os.listdir(directory_fd))
        except OSError as exc:
            raise CompanionServerError("bundle directory cannot be inventoried safely") from exc
        if observed != allowed:
            raise CompanionServerError("bundle directory contains an unexpected entry")
        all_payloads = {name: _read_regular_file(directory_fd, name) for name in sorted(allowed)}
    finally:
        os.close(directory_fd)
    if sum(map(len, all_payloads.values())) > MAX_BUNDLE_BYTES:
        raise CompanionServerError("bundle exceeds the total size limit")
    receipt_payload = all_payloads["build-receipt.json"]
    try:
        receipt = json.loads(receipt_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionServerError("build receipt must be UTF-8 JSON") from exc
    if receipt_payload != _canonical(receipt):
        raise CompanionServerError("build receipt is not canonical")
    files = receipt.get("files")
    if receipt.get("schema_version") != "schauwerk-miro-web-sdk-companion-build.v1":
        raise CompanionServerError("unsupported build receipt")
    if not isinstance(files, dict) or set(files) != expected_files:
        raise CompanionServerError("build receipt inventory does not match the server contract")
    for name, expected_digest in files.items():
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise CompanionServerError(f"invalid digest in build receipt: {name}")
        if _digest(all_payloads[name]) != expected_digest:
            raise CompanionServerError(f"bundle digest mismatch: {name}")
    unsigned = dict(receipt)
    build_digest = unsigned.pop("build_digest", None)
    if build_digest != _digest(_canonical(unsigned)):
        raise CompanionServerError("build receipt digest does not match")
    headers = _parse_headers(all_payloads["_headers"])
    payloads = {name: all_payloads[name] for name in PUBLIC_FILES}
    return {
        "root": root,
        "headers": headers,
        "build_digest": build_digest,
        "payloads": payloads,
    }


class CompanionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], bundle: dict[str, Any]):
        self.bundle_root: Path = bundle["root"]
        self.security_headers: dict[str, str] = bundle["headers"]
        self.build_digest: str = bundle["build_digest"]
        self.payloads: dict[str, bytes] = bundle["payloads"]
        super().__init__(address, CompanionRequestHandler)


class CompanionRequestHandler(BaseHTTPRequestHandler):
    server: CompanionHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "SchauwerkCompanion"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, content_type: str, length: int) -> None:
        for name, value in self.server.security_headers.items():
            self.send_header(name, value)
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Schauwerk-Build-Digest", self.server.build_digest)

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str, *, head: bool) -> None:
        self.send_response(status)
        self._headers(content_type, len(payload))
        self.end_headers()
        if not head:
            self.wfile.write(payload)

    def _error(self, status: HTTPStatus, error: str, *, head: bool) -> None:
        payload = _canonical({"error": error})
        self._send(status, payload, "application/json; charset=utf-8", head=head)

    def _route(self, *, head: bool) -> None:
        request_parts = self.requestline.split(" ", 2)
        raw_target = request_parts[1] if len(request_parts) == 3 else self.path
        if raw_target.startswith(("//", "http://", "https://")) or "\\" in raw_target:
            self._error(HTTPStatus.NOT_FOUND, "not_found", head=head)
            return
        parsed = urlsplit(raw_target)
        try:
            decoded = unquote_to_bytes(parsed.path).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_path", head=head)
            return
        if decoded == "/":
            name = "index.html"
        elif decoded.startswith("/") and decoded.count("/") == 1:
            name = decoded[1:]
        else:
            name = ""
        if name not in PUBLIC_FILES:
            self._error(HTTPStatus.NOT_FOUND, "not_found", head=head)
            return
        payload = self.server.payloads[name]
        self._send(HTTPStatus.OK, payload, CONTENT_TYPES[Path(name).suffix], head=head)

    def do_GET(self) -> None:
        self._route(head=False)

    def do_HEAD(self) -> None:
        self._route(head=True)

    def _reject_write(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        payload = _canonical({"error": "read_only"})
        self._headers("application/json; charset=utf-8", len(payload))
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    do_POST = _reject_write
    do_PUT = _reject_write
    do_PATCH = _reject_write
    do_DELETE = _reject_write
    do_OPTIONS = _reject_write


def create_companion_server(
    bundle_root: str | Path, *, bind: str = "127.0.0.1", port: int = 0
) -> CompanionHTTPServer:
    try:
        address = ipaddress.ip_address(bind)
    except ValueError as exc:
        raise CompanionServerError("bind address must be a loopback IP") from exc
    if not address.is_loopback:
        raise CompanionServerError("bind address must be loopback-only")
    if not 0 <= port <= 65535:
        raise CompanionServerError("port is outside the valid range")
    return CompanionHTTPServer((bind, port), verify_server_bundle(bundle_root))


def serve_companion(bundle_root: str | Path, *, bind: str, port: int) -> None:
    server = create_companion_server(bundle_root, bind=bind, port=port)
    receipt = {
        "schema_version": "schauwerk-companion-server-start.v1",
        "bind": server.server_address[0],
        "port": server.server_address[1],
        "build_digest": server.build_digest,
        "loopback_only": True,
        "read_only": True,
    }
    print(json.dumps(receipt, sort_keys=True), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)
    serve_companion(args.bundle_root, bind=args.bind, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
