"""Build and serve the Schaubild product shell.

New canonical Schauwerk representation inputs are rendered by Schauwerk's native
renderer and interaction viewer. Mermaid, JSON Canvas and draw.io remain explicit
compatibility inputs backed by the diagrams.net embed runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import threading
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from schauwerk.resources.standalone_editor.assets import ASSETS
from schauwerk.visual.native_viewer import NativeViewerError, build_native_viewer
from schauwerk.visual.representation import RepresentationError, validate_representation_input

MANIFEST_SCHEMA: Final = "schauwerk-standalone-editor-manifest.v2"
NATIVE_RENDERER: Final = "schauwerk-native-diagram-v1"
NATIVE_API_PATH: Final = "/api/native-viewer"
MAX_NATIVE_REQUEST_BYTES: Final = 5 * 1024 * 1024
EDITOR_ORIGIN: Final = "https://embed.diagrams.net"
EMBED_QUERY: Final = (
    "embed=1&proto=json&configure=1&spin=1&lang=de&ui=simple&dark=auto&pages=0&grid=0&"
    "plugins=0&math=0&pwa=0&drafts=0&splash=0&suppressNewWindows=1"
)
AI_HANDOFF_PROMPT: Final = (
    "Erstelle aus dem Auftrag ein Schaubild im kanonischen Schauwerk-Repräsentationsformat.\n\n"
    "Gib genau einen json-Codeblock aus. Das JSON muss exakt dem Schema "
    "schauwerk-representation-input.v1 entsprechen. Auf Root-Ebene sind genau diese "
    "Felder erforderlich: schema_version, id, title, purpose, intent, groups, nodes, "
    "edges, requirements und requested_formats. id sowie alle Group-, Node- und Edge-IDs "
    "müssen mit einem Kleinbuchstaben beginnen und danach nur Kleinbuchstaben, Ziffern "
    "oder Unterstriche enthalten. nodes muss mindestens einen Knoten enthalten.\n\n"
    "Gruppen enthalten genau id und label. Knoten benötigen id, label und kind; optional "
    "sind group und summary. Erlaubte Knoten-kinds sind human, system, service, store, "
    "decision, risk, action, evidence und concept. Kanten enthalten genau id, from, to, "
    "label und kind; erlaubte Kanten-kinds sind authority, flow, evidence, feedback, risk "
    "und association. Jede Kante muss auf vorhandene Knoten verweisen.\n\n"
    "requirements ist ein Objekt und darf nur diese booleschen Felder enthalten: "
    "formal_relations, free_spatial_layout, presentation, collaboration, rich_text, "
    "structured_comparison und portable_offline. Nicht benötigte Felder können fehlen. "
    "requested_formats ist eine Liste ohne Duplikate aus mermaid, canvas, miro_native, "
    "table und document; für ein reines natives Schaubild darf sie leer sein.\n\n"
    "Für den nativen Schaubild-Produktpfad sind derzeit alle schema-gültigen Intents "
    "außer knowledge_map zugelassen. Verwende process, sequence, state, timeline oder "
    "narrative, wenn das fachlich passt. Für eine echte freie Wissens-/Konzeptkarte "
    "(knowledge_map) gib stattdessen genau einen gültigen JSON-Canvas-1.0-json-Codeblock "
    "aus; dieser läuft bewusst über den Legacy-Pfad, bis die allgemeine native "
    "Routinggrenze gehärtet ist.\n\n"
    "Beachte die inhaltlichen und gestalterischen Wünsche des Nutzers. Verwende kurze, "
    "gut lesbare Beschriftungen und strukturiere das Schaubild so, dass die wesentlichen "
    "Zusammenhänge schnell erkennbar sind. Kein Vorwort, keine Erklärung und keine "
    "zusätzliche Variante."
)
_EDITOR_ORIGIN_MARKER: Final = 'const EDITOR_ORIGIN = "__SCHAUWERK_EDITOR_ORIGIN__";'
_EDITOR_URL_MARKER: Final = 'const EDITOR_URL = "__SCHAUWERK_EDITOR_URL__";'
_HANDOFF_BUTTON_ANCHOR: Final = (
    '        <button class="button ghost" id="blankButton" type="button">Legacy leer</button>'
)
_HANDOFF_BUTTON_HTML: Final = (
    '        <button class="button ghost" id="copyAiGuideButton" type="button">'
    "KI-Anleitung kopieren</button>"
)


class StandaloneEditorError(ValueError):
    """Raised when a standalone editor build violates a local safety contract."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _reject_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    for component in reversed([candidate, *candidate.parents]):
        if component.exists() and component.is_symlink():
            raise StandaloneEditorError("standalone editor output path must not contain symlinks")


def _normalize_editor_origin(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ch.isspace() for ch in value)
    ):
        raise StandaloneEditorError("editor origin must be one exact http(s) origin")
    if not value.isascii():
        raise StandaloneEditorError("editor origin must use ASCII host syntax")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise StandaloneEditorError("editor origin is not a valid URL origin") from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise StandaloneEditorError("editor origin must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise StandaloneEditorError("editor origin must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise StandaloneEditorError("editor origin must not contain path, query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise StandaloneEditorError("editor origin contains an invalid port") from exc

    host = hostname.casefold()
    if "%" in host:
        raise StandaloneEditorError("editor origin must not use an IPv6 zone identifier")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
        if parsed.netloc.startswith("["):
            raise StandaloneEditorError("bracketed editor origin host must be IPv6")
        last_label = host.rsplit(".", 1)[-1]
        numeric_last_label = re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", last_label)
        if numeric_last_label is not None:
            raise StandaloneEditorError("editor origin contains an ambiguous numeric hostname")
        if host != "localhost" and re.fullmatch(
            r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host
        ) is None:
            raise StandaloneEditorError("editor origin contains an invalid hostname")
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        raise StandaloneEditorError("editor origin must not use IPv4-mapped IPv6")
    canonical_host = ip.compressed if ip is not None else host
    is_loopback = host == "localhost" or bool(ip and ip.is_loopback)
    if parsed.scheme == "http" and not is_loopback:
        raise StandaloneEditorError("plain-http editor origins are allowed only on loopback")

    if (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80):
        port = None

    display_host = f"[{canonical_host}]" if ip and ip.version == 6 else canonical_host
    netloc = display_host if port is None else f"{display_host}:{port}"
    return f"{parsed.scheme}://{netloc}"


def _editor_url(editor_origin: str) -> tuple[str, bool]:
    custom_origin = editor_origin != EDITOR_ORIGIN
    query = EMBED_QUERY
    if custom_origin:
        query += "&offline=1"
        if editor_origin.startswith("http://"):
            query += "&https=0"
    return f"{editor_origin}/?{query}", custom_origin


def _render_assets(*, editor_origin: str, editor_url: str) -> dict[str, str]:
    rendered = dict(ASSETS)
    app_js = rendered["app.js"]
    if app_js.count(_EDITOR_ORIGIN_MARKER) != 1 or app_js.count(_EDITOR_URL_MARKER) != 1:
        raise StandaloneEditorError("standalone editor asset template has drifted")
    app_js = app_js.replace(
        _EDITOR_ORIGIN_MARKER,
        f"const EDITOR_ORIGIN = {json.dumps(editor_origin, ensure_ascii=False)};",
        1,
    )
    app_js = app_js.replace(
        _EDITOR_URL_MARKER,
        f"const EDITOR_URL = {json.dumps(editor_url, ensure_ascii=False)};",
        1,
    )

    index_html = rendered["index.html"]
    if index_html.count(_HANDOFF_BUTTON_ANCHOR) != 1:
        raise StandaloneEditorError("standalone editor handoff button anchor has drifted")
    rendered["index.html"] = index_html.replace(
        _HANDOFF_BUTTON_ANCHOR,
        f"{_HANDOFF_BUTTON_ANCHOR}\n{_HANDOFF_BUTTON_HTML}",
        1,
    )

    prompt_json = json.dumps(AI_HANDOFF_PROMPT, ensure_ascii=False)
    app_js += f"""

const AI_HANDOFF_PROMPT = {prompt_json};
const copyAiGuideButton = document.querySelector("#copyAiGuideButton");
copyAiGuideButton.addEventListener("click", async () => {{
  setError("");
  try {{
    if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {{
      throw new Error("clipboard unavailable");
    }}
    await navigator.clipboard.writeText(AI_HANDOFF_PROMPT);
    copyAiGuideButton.textContent = "Anleitung kopiert";
    setStatus("KI-Anleitung kopiert");
    window.setTimeout(() => {{
      copyAiGuideButton.textContent = "KI-Anleitung kopieren";
    }}, 1800);
  }} catch (_) {{
    setError("KI-Anleitung konnte nicht kopiert werden. Bitte Zwischenablage-Zugriff erlauben.");
  }}
}});
"""
    rendered["app.js"] = app_js
    return rendered


def _content_security_policy(editor_origin: str) -> str:
    return (
        "default-src 'self'; "
        "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        f"frame-src 'self' {editor_origin}; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


def _native_product_input(value: Any) -> dict[str, Any]:
    """Validate canonical representation input and enforce the Phase-3 admission gate."""

    if not isinstance(value, dict):
        raise StandaloneEditorError("native representation input must be one JSON object")
    try:
        normalized = validate_representation_input(value)
    except RepresentationError as exc:
        raise StandaloneEditorError(f"native representation input is invalid: {exc}") from exc
    if normalized["intent"] == "knowledge_map":
        raise StandaloneEditorError(
            "knowledge_map remains on the legacy compatibility path until the "
            "general native same-row/parallel routing boundary is hardened"
        )
    return normalized


def build_standalone_editor(
    output_dir: Path,
    *,
    editor_origin: str = EDITOR_ORIGIN,
) -> dict[str, object]:
    """Write a deterministic static product shell into an empty directory."""

    normalized_origin = _normalize_editor_origin(editor_origin)
    editor_url, custom_origin = _editor_url(normalized_origin)
    assets = _render_assets(editor_origin=normalized_origin, editor_url=editor_url)

    output_dir = output_dir.expanduser().absolute()
    _reject_symlink_chain(output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise StandaloneEditorError(f"output path must be a directory: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise StandaloneEditorError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)

    written: list[dict[str, object]] = []
    for filename, text in sorted(assets.items()):
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
        "product_surface": "schaubild",
        "cutover_status": "native-primary-with-legacy-compatibility",
        "editor_engine": NATIVE_RENDERER,
        "native_renderer": {
            "renderer": NATIVE_RENDERER,
            "viewer": "schauwerk-native-svg-phase2",
            "runtime": "integrated-loopback-serve",
            "api_path": NATIVE_API_PATH,
            "admission": "schema-valid-except-knowledge-map",
            "semantic_authority": "schauwerk-representation-input.v1",
            "supported_outputs": ["schauwerk-representation-input.v1", "svg"],
        },
        "legacy_editor_engine": "diagrams.net-embed",
        "editor_origin": normalized_origin,
        "editor_url": editor_url,
        "engine_delivery": (
            "operator-configured-browser-iframe" if custom_origin else "remote-browser-iframe"
        ),
        "local_state": "browser-localStorage",
        "supported_inputs": [
            "schauwerk-representation-input.v1",
            "mermaid",
            "json-canvas-1.0",
            "drawio-xml",
        ],
        "supported_outputs": ["drawio-xml", "png", "svg"],
        "network_boundary": {
            "shell": "local-static-files",
            "native_render_api": "same-origin-loopback-serve-only",
            "native_viewer_external_requests_required": False,
            "legacy_editor_runtime": normalized_origin,
            "public_embed_runtime": not custom_origin,
            "operator_configured_editor_runtime": custom_origin,
            "offline_mode_requested": custom_origin,
            "offline_complete": False,
        },
        "files": written,
        "does_not_establish": [
            "native-semantic-mutation",
            "native-edge-rerouting-after-node-drag",
            "native-png-export",
            "native-static-host-render-api",
            "general-knowledge-map-native-cutover",
            "bundled-legacy-editor-runtime",
            "static-host-security-header-enforcement",
            (
                "operator-control-of-legacy-editor-runtime"
                if custom_origin
                else "provider-independence-of-legacy-compatibility"
            ),
            "lossless-json-canvas-roundtrip",
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
    """Static product handler plus one bounded same-origin native-render endpoint."""

    editor_origin: str = EDITOR_ORIGIN
    native_build_lock = threading.Lock()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", _content_security_policy(self.editor_origin))
        super().end_headers()

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _has_valid_loopback_host(self) -> bool:
        raw_host = self.headers.get("Host")
        if not raw_host or raw_host != raw_host.strip():
            return False
        host = raw_host.casefold()
        port = int(self.server.server_address[1])
        return host in {
            "127.0.0.1",
            f"127.0.0.1:{port}",
            "localhost",
            f"localhost:{port}",
        }

    def do_POST(self) -> None:  # noqa: N802
        if self.path != NATIVE_API_PATH:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        if not self._has_valid_loopback_host():
            self._send_json(
                HTTPStatus.MISDIRECTED_REQUEST,
                {"error": "native render endpoint accepts loopback Host headers only"},
            )
            return
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
        if media_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "native render endpoint requires application/json"},
            )
            return
        length_header = self.headers.get("Content-Length")
        try:
            content_length = int(length_header) if length_header is not None else -1
        except ValueError:
            content_length = -1
        if content_length < 0:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "valid Content-Length required"})
            return
        if content_length > MAX_NATIVE_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "native representation exceeds 5 MB"},
            )
            return
        payload = self.rfile.read(content_length)
        if len(payload) != content_length:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "incomplete request body"})
            return
        try:
            value = json.loads(payload.decode("utf-8"))
            normalized = _native_product_input(value)
            digest = str(normalized["input_digest"])
            root = Path(self.directory).resolve()
            target = root / "native" / digest
            with self.native_build_lock:
                if not target.exists():
                    build_native_viewer(value, target)
                elif not (target / "manifest.json").is_file():
                    raise StandaloneEditorError("native viewer cache is incomplete")
        except (
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
            StandaloneEditorError,
            NativeViewerError,
        ) as exc:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "input_digest": digest,
                "renderer": NATIVE_RENDERER,
                "url": f"/native/{digest}/index.html",
            },
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def serve_standalone_editor(
    *,
    port: int = 8765,
    build_dir: Path | None = None,
    editor_origin: str = EDITOR_ORIGIN,
) -> None:
    """Serve the product shell on loopback only.

    A caller-supplied build directory must either be absent or empty. When no
    directory is supplied, a process-local temporary directory is created and
    removed after the server stops.
    """

    if not 0 <= port <= 65535:
        raise StandaloneEditorError("port must be between 0 and 65535")
    normalized_origin = _normalize_editor_origin(editor_origin)
    _, custom_origin = _editor_url(normalized_origin)

    temporary = build_dir is None
    if temporary:
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="schauwerk-editor-"))
    else:
        root = build_dir.expanduser().absolute()

    try:
        build_standalone_editor(root, editor_origin=normalized_origin)
        handler_class = type(
            "ConfiguredEditorRequestHandler",
            (_EditorRequestHandler,),
            {"editor_origin": normalized_origin},
        )
        handler = partial(handler_class, directory=str(root))
        with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
            actual_port = int(server.server_address[1])
            print(f"standalone editor: http://127.0.0.1:{actual_port}/")
            mode = "operator-configured editor origin" if custom_origin else "public embed runtime"
            print(f"editor engine: {normalized_origin} ({mode})")
            server.serve_forever()
    finally:
        if temporary:
            shutil.rmtree(root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m schauwerk.visual.standalone_editor")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write the static editor shell")
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--editor-origin", default=EDITOR_ORIGIN)

    serve = commands.add_parser("serve", help="serve the editor shell on loopback")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--build-dir", type=Path)
    serve.add_argument("--editor-origin", default=EDITOR_ORIGIN)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_standalone_editor(args.output_dir, editor_origin=args.editor_origin)
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve_standalone_editor(
            port=args.port,
            build_dir=args.build_dir,
            editor_origin=args.editor_origin,
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
