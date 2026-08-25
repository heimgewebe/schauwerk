"""Build and serve the bounded standalone diagram-editor product spike.

The spike deliberately keeps the editor engine outside Schauwerk.  Schauwerk owns
only the small product shell and import/export boundary; the interactive editor is
loaded from the documented diagrams.net embed origin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

from schauwerk.resources.standalone_editor.assets import ASSETS

MANIFEST_SCHEMA: Final = "schauwerk-standalone-editor-manifest.v1"
EDITOR_ORIGIN: Final = "https://embed.diagrams.net"


class StandaloneEditorError(ValueError):
    """Raised when a standalone editor build violates a local safety contract."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _reject_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    for component in reversed([candidate, *candidate.parents]):
        if component.exists() and component.is_symlink():
            raise StandaloneEditorError("standalone editor output path must not contain symlinks")


def build_standalone_editor(output_dir: Path) -> dict[str, object]:
    """Write a deterministic static product shell into an empty directory."""

    output_dir = output_dir.expanduser().absolute()
    _reject_symlink_chain(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise StandaloneEditorError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)

    written: list[dict[str, object]] = []
    for filename, text in sorted(ASSETS.items()):
        target = output_dir / filename
        encoded = text.encode("utf-8")
        target.write_bytes(encoded)
        os.chmod(target, 0o600)
        written.append(
            {
                "path": filename,
                "bytes": len(encoded),
                "sha256": _sha256(encoded),
            }
        )

    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "editor_engine": "diagrams.net-embed",
        "editor_origin": EDITOR_ORIGIN,
        "engine_delivery": "remote-browser-iframe",
        "local_state": "browser-localStorage",
        "supported_inputs": ["mermaid", "json-canvas-1.0", "drawio-xml"],
        "supported_outputs": ["drawio-xml", "png", "svg"],
        "network_boundary": {
            "shell": "local-static-files",
            "editor_runtime": EDITOR_ORIGIN,
            "offline_complete": False,
        },
        "files": written,
        "does_not_establish": [
            "offline-editor-runtime",
            "provider-independence-of-the-spike",
            "lossless-json-canvas-roundtrip",
            "production-readiness",
        ],
    }
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o600)
    return manifest


class _EditorRequestHandler(SimpleHTTPRequestHandler):
    """Static handler with no-store and a narrow browser security boundary."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            f"frame-src {EDITOR_ORIGIN}; connect-src 'none'; object-src 'none'; "
            "base-uri 'none'; form-action 'none'",
        )
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def serve_standalone_editor(*, port: int = 8765, build_dir: Path | None = None) -> None:
    """Serve the spike on loopback only.

    A caller-supplied build directory must either be absent or empty.  When no
    directory is supplied, a process-local temporary directory is created and
    removed after the server stops.
    """

    if not 0 <= port <= 65535:
        raise StandaloneEditorError("port must be between 0 and 65535")

    temporary = build_dir is None
    if temporary:
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="schauwerk-editor-"))
    else:
        root = build_dir.expanduser().absolute()

    try:
        build_standalone_editor(root)
        handler = partial(_EditorRequestHandler, directory=str(root))
        with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
            actual_port = int(server.server_address[1])
            print(f"standalone editor: http://127.0.0.1:{actual_port}/")
            print(f"editor engine: {EDITOR_ORIGIN} (network required for this spike)")
            server.serve_forever()
    finally:
        if temporary:
            shutil.rmtree(root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m schauwerk.visual.standalone_editor")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write the static editor shell")
    build.add_argument("--output-dir", required=True, type=Path)

    serve = commands.add_parser("serve", help="serve the editor shell on loopback")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--build-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_standalone_editor(args.output_dir)
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve_standalone_editor(port=args.port, build_dir=args.build_dir)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
