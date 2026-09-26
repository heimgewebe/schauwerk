"""Build and serve the local native SVG viewer/editor bundle.

Representation input remains immutable and uses a browser-local layout overlay.
JSON Canvas is normalized into a document-backed editing model; both modes render
through the authoritative native_diagram renderer family.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
from collections.abc import Mapping
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

from schauwerk.resources.native_viewer.assets import ASSETS, INDEX_HTML

from .json_fidelity import (
    JsonFidelityError,
    assert_javascript_roundtrip_json_numbers,
    parse_json_with_unique_object_members,
)
from .native_diagram import render_native_diagram, render_native_editing_document
from .native_document import (
    MAX_NATIVE_ABS_COORDINATE,
    MAX_NATIVE_EDGES,
    MAX_NATIVE_GROUPS,
    MAX_NATIVE_NODES,
    MAX_NATIVE_ROUTING_PAIRS,
    NATIVE_DOCUMENT_SCHEMA,
    NativeDocumentError,
    editing_document_to_json_canvas,
    json_canvas_to_editing_document,
)
from .representation import validate_representation_input

MANIFEST_SCHEMA: Final = "schauwerk-native-viewer-manifest.v1"
MAX_INPUT_BYTES: Final = 5 * 1024 * 1024
_TITLE_MARKER: Final = "__SCHAUWERK_NATIVE_TITLE__"
_SVG_MARKER: Final = "__SCHAUWERK_NATIVE_SVG__"
_MODEL_MARKER: Final = "__SCHAUWERK_NATIVE_MODEL__"
_LIMITS_MARKER: Final = "__SCHAUWERK_NATIVE_LIMITS__"


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


def _render_index(*, title: str, svg: str, model: Mapping[str, Any]) -> str:
    if (
        INDEX_HTML.count(_SVG_MARKER) != 1
        or INDEX_HTML.count(_TITLE_MARKER) != 2
        or INDEX_HTML.count(_MODEL_MARKER) != 1
        or INDEX_HTML.count(_LIMITS_MARKER) != 1
    ):
        raise NativeViewerError("native viewer HTML template markers drifted")
    embedded_model = json.dumps(
        model, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    embedded_model = (
        embedded_model.replace("&", r"\u0026")
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
    )
    embedded_limits = json.dumps(
        {
            "max_abs_coordinate": MAX_NATIVE_ABS_COORDINATE,
            "max_edges": MAX_NATIVE_EDGES,
            "max_groups": MAX_NATIVE_GROUPS,
            "max_nodes": MAX_NATIVE_NODES,
            "max_routing_pairs": MAX_NATIVE_ROUTING_PAIRS,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    replacements = {
        _TITLE_MARKER: html.escape(title),
        _SVG_MARKER: _inline_svg(svg),
        _MODEL_MARKER: embedded_model,
        _LIMITS_MARKER: embedded_limits,
    }
    marker_pattern = re.compile(
        "|".join(re.escape(marker) for marker in replacements)
    )
    return marker_pattern.sub(lambda match: replacements[match.group(0)], INDEX_HTML)


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
    *,
    serve_binding: str = "127.0.0.1-only",
    public_base_path: str = "",
) -> dict[str, object]:
    """Build one deterministic, fully local interaction bundle.

    ``diagram.svg`` is the exact Gate-1 renderer output. The HTML contains an
    augmented inline copy only so browser interaction can address stable source IDs.
    Browser code never writes semantic representation bytes or renderer bytes.
    """

    if serve_binding not in {
        "127.0.0.1-only",
        "trusted-reverse-proxy-private-ingress",
    }:
        raise NativeViewerError("unsupported native viewer serve binding")
    if (
        not isinstance(public_base_path, str)
        or public_base_path != public_base_path.strip()
        or ("?" in public_base_path or "#" in public_base_path)
        or (
            public_base_path
            and (
                not public_base_path.startswith("/")
                or public_base_path.endswith("/")
                or "//" in public_base_path
                or "/../" in f"{public_base_path}/"
                or "/./" in f"{public_base_path}/"
            )
        )
    ):
        raise NativeViewerError("native viewer public base path is invalid")
    if serve_binding == "127.0.0.1-only" and public_base_path:
        raise NativeViewerError("loopback native viewer must not declare a public base path")

    document_mode = source.get("schema_version") == NATIVE_DOCUMENT_SCHEMA
    if document_mode:
        try:
            canvas = editing_document_to_json_canvas(source)
            model = json_canvas_to_editing_document(
                canvas, title=str(source.get("title") or "Schaubild")
            )
            svg = render_native_editing_document(model)
        except NativeDocumentError as exc:
            raise NativeViewerError(f"native editing document is invalid: {exc}") from exc
        semantic_filename = "document.json"
        semantic_mode = "editable-document"
    else:
        model = validate_representation_input(source)
        svg = render_native_diagram(model)
        semantic_filename = "representation.json"
        semantic_mode = "read-only"
    svg_payload = svg.encode("utf-8")
    semantic_payload = _canonical_json(model)
    index_payload = _render_index(title=str(model["title"]), svg=svg, model=model).encode("utf-8")

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
        semantic_filename: semantic_payload,
        "styles.css": ASSETS["styles.css"].encode("utf-8"),
    }
    for filename, payload in sorted(payloads.items()):
        target = root / filename
        target.write_bytes(payload)
        os.chmod(target, 0o600)

    files = [_file_record(root / name, root) for name in sorted(payloads)]
    diagram_sha256 = _sha256(svg_payload)
    semantic_sha256 = _sha256(semantic_payload)
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA,
        "viewer": "schauwerk-native-svg-phase2",
        "input_digest": str(model.get("input_digest") or model.get("source_digest")),
        "semantic_authority": {
            "artifact": semantic_filename,
            "sha256": semantic_sha256,
            "mode": semantic_mode,
            "source_format": model.get("source_format", "schauwerk-representation-input.v1"),
        },
        "renderer_authority": {
            "artifact": "diagram.svg",
            "sha256": diagram_sha256,
            "renderer": "schauwerk-native-diagram-v1",
            "bytes_modified_by_viewer": False,
        },
        "layout_overlay": {
            "authority": "document-state" if document_mode else "browser-local-only",
            "storage": (
                "document-memory+parent-state" if document_mode else "localStorage"
            ),
            "binding": "source_digest" if document_mode else "input_digest",
            "semantic_writeback": document_mode,
            "cross_device_persistence": False,
        },
        "interactions": ["pan", "zoom", "selection", "node-drag", "live-edge-rerouting"],
        "interaction_contract": {
            "mouse_pointer_events": True,
            "touch_pointer_events": True,
            "two_pointer_pinch_zoom": True,
            "keyboard_node_selection": True,
            "edge_geometry_after_node_drag": "live-route-preserving-overlay",
            "edge_rerouting": True,
            "routing_authority": "native-diagram-canonical+browser-live-deformation",
        },
        "network_boundary": {
            "bundle": "server-managed-local-bundle",
            "external_requests_required": False,
            "serve_binding": serve_binding,
            "public_base_path": public_base_path or "/",
            "delivery": (
                "integrated-schaubild-runtime"
                if serve_binding == "trusted-reverse-proxy-private-ingress"
                else "development-loopback"
            ),
        },
        "files": files,
        "does_not_establish": [
            *(
                ["consumer-deployment-readiness", "public-edge-acceptance"]
                if serve_binding == "trusted-reverse-proxy-private-ingress"
                else ["production-readiness", "phase-3-cutover-acceptance"]
            ),
            *([] if document_mode else ["semantic-mutation", "document-backed-editing"]),
            "cross-device-layout-persistence",
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
        payload_text = payload.decode("utf-8")
        value = parse_json_with_unique_object_members(payload_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeViewerError("native viewer input is not valid UTF-8 JSON") from exc
    except JsonFidelityError as exc:
        raise NativeViewerError(f"native viewer input {exc}") from exc
    if not isinstance(value, dict):
        raise NativeViewerError("native viewer input must be one JSON object")
    if value.get("schema_version") == NATIVE_DOCUMENT_SCHEMA:
        try:
            assert_javascript_roundtrip_json_numbers(payload_text)
        except JsonFidelityError as exc:
            raise NativeViewerError(f"native editing document {exc}") from exc
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
    build.add_argument("--serve-binding", default="127.0.0.1-only")
    build.add_argument("--public-base-path", default="")

    serve = commands.add_parser("serve", help="serve one local native viewer on loopback")
    serve.add_argument("--input", required=True, type=Path)
    serve.add_argument("--port", type=int, default=8785)
    serve.add_argument("--build-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_native_viewer(
            _read_representation(args.input),
            args.output_dir,
            serve_binding=args.serve_binding,
            public_base_path=args.public_base_path,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve_native_viewer(args.input, port=args.port, build_dir=args.build_dir)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
