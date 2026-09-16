"""Build and serve the local Phase-2 native SVG interaction proof.

The semantic representation and canonical Gate-1 SVG remain immutable inputs.
Interactive node positions are a browser-local, input-digest-bound layout overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
from collections.abc import Mapping
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

from schauwerk.resources.native_viewer.assets import ASSETS, INDEX_HTML

from .native_diagram import render_native_diagram
from .representation import validate_representation_input

MANIFEST_SCHEMA: Final = "schauwerk-native-viewer-manifest.v1"
MAX_INPUT_BYTES: Final = 5 * 1024 * 1024
_TITLE_MARKER: Final = "__SCHAUWERK_NATIVE_TITLE__"
_SVG_MARKER: Final = "__SCHAUWERK_NATIVE_SVG__"


class NativeViewerError(ValueError):
    """Raised when the local native viewer violates its bounded build contract."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _reject_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    for component in reversed([candidate, *candidate.parents]):
        if component.exists() and component.is_symlink():
            raise NativeViewerError("native viewer output path must not contain symlinks")


def _inline_svg(svg: str) -> str:
    if not svg.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<svg '):
        raise NativeViewerError("native renderer SVG prolog/root contract drifted")
    body = svg.split("\n", 1)[1]
    if body.count("<svg ") != 1:
        raise NativeViewerError("native renderer SVG root contract drifted")
    return body.replace(
        "<svg ",
        '<svg id="nativeDiagram" class="native-diagram" ',
        1,
    )


def _render_index(*, title: str, svg: str) -> str:
    if INDEX_HTML.count(_SVG_MARKER) != 1 or INDEX_HTML.count(_TITLE_MARKER) != 2:
        raise NativeViewerError("native viewer HTML template markers drifted")
    return INDEX_HTML.replace(_TITLE_MARKER, html.escape(title)).replace(
        _SVG_MARKER,
        _inline_svg(svg),
        1,
    )


def _file_record(path: Path, root: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def build_native_viewer(
    source: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, object]:
    """Build one deterministic, fully local interaction bundle.

    ``diagram.svg`` is the exact Gate-1 renderer output. The HTML contains an
    augmented inline copy only so browser interaction can address stable source IDs.
    Browser code never writes semantic representation bytes or renderer bytes.
    """

    model = validate_representation_input(source)
    svg = render_native_diagram(model)
    svg_payload = svg.encode("utf-8")
    representation_payload = _canonical_json(model)
    index_payload = _render_index(title=str(model["title"]), svg=svg).encode("utf-8")

    root = output_dir.expanduser().absolute()
    _reject_symlink_chain(root)
    if root.exists() and not root.is_dir():
        raise NativeViewerError(f"output path must be a directory: {root}")
    if root.exists() and any(root.iterdir()):
        raise NativeViewerError(f"output directory must be empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)

    payloads: dict[str, bytes] = {
        "app.js": ASSETS["app.js"].encode("utf-8"),
        "diagram.svg": svg_payload,
        "index.html": index_payload,
        "interaction.js": ASSETS["interaction.js"].encode("utf-8"),
        "representation.json": representation_payload,
        "styles.css": ASSETS["styles.css"].encode("utf-8"),
    }
    for filename, payload in sorted(payloads.items()):
        target = root / filename
        target.write_bytes(payload)
        os.chmod(target, 0o600)

    files = [_file_record(root / name, root) for name in sorted(payloads)]
    diagram_sha256 = _sha256(svg_payload)
    representation_sha256 = _sha256(representation_payload)
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "viewer": "schauwerk-native-svg-phase2",
        "input_digest": str(model["input_digest"]),
        "semantic_authority": {
            "artifact": "representation.json",
            "sha256": representation_sha256,
            "mode": "read-only",
        },
        "renderer_authority": {
            "artifact": "diagram.svg",
            "sha256": diagram_sha256,
            "renderer": "schauwerk-native-diagram-v1",
            "bytes_modified_by_viewer": False,
        },
        "layout_overlay": {
            "authority": "browser-local-only",
            "storage": "localStorage",
            "binding": "input_digest",
            "semantic_writeback": False,
            "cross_device_persistence": False,
        },
        "interactions": ["pan", "zoom", "selection", "node-drag"],
        "interaction_contract": {
            "mouse_pointer_events": True,
            "touch_pointer_events": True,
            "two_pointer_pinch_zoom": True,
            "keyboard_node_selection": True,
            "edge_geometry_after_node_drag": "frozen-gate1-svg",
            "edge_rerouting": False,
        },
        "network_boundary": {
            "bundle": "local-static-files",
            "external_requests_required": False,
            "serve_binding": "127.0.0.1-only",
        },
        "files": files,
        "does_not_establish": [
            "production-readiness",
            "semantic-mutation",
            "edge-rerouting-after-node-drag",
            "cross-device-layout-persistence",
            "phase-3-cutover-acceptance",
        ],
    }
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = _sha256(canonical.encode("utf-8"))
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o600)
    return manifest


def _content_security_policy() -> str:
    return (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'none'; frame-src 'none'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'"
    )


class _NativeViewerRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", _content_security_policy())
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def _read_representation(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or not candidate.is_file():
        raise NativeViewerError("native viewer input must be one regular JSON file")
    payload = candidate.read_bytes()
    if len(payload) > MAX_INPUT_BYTES:
        raise NativeViewerError("native viewer input exceeds 5 MB")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeViewerError("native viewer input is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise NativeViewerError("native viewer input must be one JSON object")
    return value


def serve_native_viewer(
    input_path: Path,
    *,
    port: int = 8785,
    build_dir: Path | None = None,
) -> None:
    """Build and serve one viewer on loopback only."""

    if not 0 <= port <= 65535:
        raise NativeViewerError("port must be between 0 and 65535")
    source = _read_representation(input_path)
    temporary = build_dir is None
    if temporary:
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="schauwerk-native-viewer-"))
    else:
        root = build_dir.expanduser().absolute()

    try:
        build_native_viewer(source, root)
        handler = partial(_NativeViewerRequestHandler, directory=str(root))
        with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
            actual_port = int(server.server_address[1])
            print(f"native viewer: http://127.0.0.1:{actual_port}/", flush=True)
            server.serve_forever()
    finally:
        if temporary:
            shutil.rmtree(root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m schauwerk.visual.native_viewer")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write one local native viewer bundle")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)

    serve = commands.add_parser("serve", help="serve one local native viewer on loopback")
    serve.add_argument("--input", required=True, type=Path)
    serve.add_argument("--port", type=int, default=8785)
    serve.add_argument("--build-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_native_viewer(_read_representation(args.input), args.output_dir)
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve_native_viewer(args.input, port=args.port, build_dir=args.build_dir)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
