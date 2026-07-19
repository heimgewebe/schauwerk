from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.companion_server import (
    MAX_FILE_BYTES,
    CompanionRequestHandler,
    CompanionServerError,
    create_companion_server,
    verify_server_bundle,
)
from schauwerk.surfaces.miro.web_sdk_companion import build_companion

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/miro-web-sdk-companion-v1.json"


def test_server_script_remains_standalone_executable() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src/schauwerk/surfaces/miro/companion_server.py"),
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "--bundle-root" in completed.stdout


def _bundle(tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=output)
    return output


def _request(bundle: dict, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    request = (f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").encode(
        "ascii"
    )
    client, server_socket = socket.socketpair()
    try:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        CompanionRequestHandler(
            server_socket,
            ("127.0.0.1", 43100),
            SimpleNamespace(
                security_headers=bundle["headers"],
                build_digest=bundle["build_digest"],
                payloads=bundle["payloads"],
                server_name="127.0.0.1",
                server_port=0,
            ),
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
    headers = {
        name.lower(): value.strip()
        for name, value in (line.split(":", 1) for line in lines[1:] if ":" in line)
    }
    return status, headers, body


def test_server_delivers_only_verified_bundle_bytes_with_miro_headers(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    verified = verify_server_bundle(bundle)
    status, headers, body = _request(verified, "GET", "/?_miro=opaque")
    assert status == 200
    assert body == (bundle / "index.html").read_bytes()
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert (
        "frame-ancestors https://miro.com https://*.miro.com" in headers["content-security-policy"]
    )
    assert "camera=()" in headers["permissions-policy"]
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["strict-transport-security"].startswith("max-age=31536000")
    assert len(headers["x-schauwerk-build-digest"]) == 64

    status, headers, body = _request(verified, "HEAD", "/panel.html?_miro=opaque")
    assert status == 200
    assert body == b""
    assert headers["content-length"] == str((bundle / "panel.html").stat().st_size)


def test_server_rejects_internal_files_traversal_and_writes(tmp_path: Path) -> None:
    verified = verify_server_bundle(_bundle(tmp_path))
    for path in ("/_headers", "/../config.json", "/%2e%2e/config.json", "//config.json"):
        status, _headers, body = _request(verified, "GET", path)
        assert status == 404, path
        assert b"not_found" in body
    status, headers, body = _request(verified, "POST", "/")
    assert status == 405
    assert headers["allow"] == "GET, HEAD"
    assert b"read_only" in body


def test_server_uses_verified_in_memory_bytes_after_start(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    expected = (bundle / "app.js").read_bytes()
    verified = verify_server_bundle(bundle)
    (bundle / "app.js").write_bytes(b"tampered")
    status, _headers, body = _request(verified, "GET", "/app.js")
    assert status == 200
    assert body == expected


def test_server_fails_closed_for_tampered_bundle_or_non_loopback_bind(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "panel.js").write_bytes(b"tampered")
    with pytest.raises(CompanionServerError, match="digest mismatch"):
        verify_server_bundle(bundle)

    clean = _bundle(tmp_path / "clean")
    with pytest.raises(CompanionServerError, match="loopback"):
        create_companion_server(clean, bind="0.0.0.0")


def test_server_rejects_noncanonical_receipt_and_oversized_file(tmp_path: Path) -> None:
    receipt_bundle = _bundle(tmp_path / "receipt")
    receipt_path = receipt_bundle / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_path.write_text(json.dumps(receipt, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(CompanionServerError, match="not canonical"):
        verify_server_bundle(receipt_bundle)

    oversized_bundle = _bundle(tmp_path / "oversized")
    (oversized_bundle / "app.js").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(CompanionServerError, match="size limit"):
        verify_server_bundle(oversized_bundle)


def test_server_rejects_symlinks_hardlinks_and_unexpected_entries(tmp_path: Path) -> None:
    symlink_bundle = _bundle(tmp_path / "symlink")
    symlink_target = tmp_path / "symlink-app.js"
    symlink_target.write_bytes((symlink_bundle / "app.js").read_bytes())
    (symlink_bundle / "app.js").unlink()
    (symlink_bundle / "app.js").symlink_to(symlink_target)
    with pytest.raises(CompanionServerError, match="unsafe or missing"):
        verify_server_bundle(symlink_bundle)

    hardlink_bundle = _bundle(tmp_path / "hardlink")
    hardlink_target = tmp_path / "hardlink-app.js"
    hardlink_target.write_bytes((hardlink_bundle / "app.js").read_bytes())
    (hardlink_bundle / "app.js").unlink()
    (hardlink_bundle / "app.js").hardlink_to(hardlink_target)
    with pytest.raises(CompanionServerError, match="independent regular file"):
        verify_server_bundle(hardlink_bundle)

    unexpected_bundle = _bundle(tmp_path / "unexpected")
    (unexpected_bundle / "operator-note.txt").write_text("not public", encoding="utf-8")
    with pytest.raises(CompanionServerError, match="unexpected entry"):
        verify_server_bundle(unexpected_bundle)
