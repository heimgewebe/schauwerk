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
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote, urlsplit

from schauwerk.resources.standalone_editor.assets import ASSETS
from schauwerk.visual.drawio_import import DrawioImportError, drawio_xml_to_representation
from schauwerk.visual.native_viewer import NativeViewerError, build_native_viewer
from schauwerk.visual.representation import RepresentationError, validate_representation_input

MANIFEST_SCHEMA: Final = "schauwerk-standalone-editor-manifest.v2"
NATIVE_RENDERER: Final = "schauwerk-native-diagram-v1"
NATIVE_API_PATH: Final = "/api/native-viewer"
NATIVE_IMPORT_SCHEMA: Final = "schauwerk-native-import-request.v1"
MAX_NATIVE_REQUEST_BYTES: Final = 5 * 1024 * 1024
MAX_NATIVE_GROUPS: Final = 32
MAX_NATIVE_NODES: Final = 128
MAX_NATIVE_EDGES: Final = 256
MAX_NATIVE_ROUTING_PAIRS: Final = 32_768
MAX_NATIVE_BUNDLE_BYTES: Final = 16 * 1024 * 1024
MAX_NATIVE_CACHE_BYTES: Final = 32 * 1024 * 1024
MAX_NATIVE_CACHE_ENTRIES: Final = 32
NATIVE_CACHE_GRACE_SECONDS: Final = 60.0
NATIVE_CACHE_MAX_PIN_SECONDS: Final = 2 * NATIVE_CACHE_GRACE_SECONDS
MAX_NATIVE_PIN_WINDOWS: Final = 4 * MAX_NATIVE_CACHE_ENTRIES
MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT: Final = 4
MAX_NATIVE_CLIENT_KEYS_PER_DIGEST: Final = 32
MAX_TRUSTED_PROXY_SOURCE_CIDRS: Final = 8
_LOCAL_ADMISSION_KEY: Final = "local"
NATIVE_REQUEST_TIMEOUT_SECONDS: Final = 30.0
NATIVE_SERVER_MAX_WORKERS: Final = 32
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
_PUBLIC_BASE_PATH_MARKER: Final = (
    'const PUBLIC_BASE_PATH = "__SCHAUWERK_PUBLIC_BASE_PATH__";'
)
_HANDOFF_BUTTON_ANCHOR: Final = (
    '        <button class="button ghost" id="blankButton" type="button">Legacy leer</button>'
)
_HANDOFF_BUTTON_HTML: Final = (
    '        <button class="button ghost" id="copyAiGuideButton" type="button">'
    "KI-Anleitung kopieren</button>"
)


class StandaloneEditorError(ValueError):
    """Raised when a standalone editor build violates a local safety contract."""


class NativeCacheCapacityError(StandaloneEditorError):
    """Raised when all bounded cache capacity is temporarily pinned."""


class NativeRequestDeadlineError(StandaloneEditorError):
    """Raised when one native-render request has exhausted its absolute lifetime."""


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


def _normalize_public_base_path(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise StandaloneEditorError("public base path must be one canonical absolute path")
    if value in {"", "/"}:
        return ""
    if (
        not value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or "?" in value
        or "#" in value
        or "\\" in value
    ):
        raise StandaloneEditorError(
            "public base path must be slash-prefixed without trailing slash"
        )
    segments = value[1:].split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or re.fullmatch(r"[A-Za-z0-9._~-]+", segment) is None
        for segment in segments
    ):
        raise StandaloneEditorError("public base path contains an invalid segment")
    return value


def _normalize_trusted_proxy_source_cidrs(
    values: tuple[str, ...],
) -> tuple[ipaddress.IPv4Network, ...]:
    if len(values) > MAX_TRUSTED_PROXY_SOURCE_CIDRS:
        raise StandaloneEditorError(
            f"at most {MAX_TRUSTED_PROXY_SOURCE_CIDRS} trusted proxy source CIDRs are allowed"
        )
    networks: list[ipaddress.IPv4Network] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value != value.strip():
            raise StandaloneEditorError("trusted proxy source CIDR must be canonical IPv4 CIDR")
        try:
            network = ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            raise StandaloneEditorError(
                "trusted proxy source CIDR must be canonical IPv4 CIDR"
            ) from exc
        if not isinstance(network, ipaddress.IPv4Network):
            raise StandaloneEditorError("trusted proxy source CIDR must use IPv4")
        canonical = str(network)
        if canonical in seen:
            raise StandaloneEditorError("trusted proxy source CIDRs must be unique")
        seen.add(canonical)
        networks.append(network)
    return tuple(networks)


def _client_quota_applies(admission_key: str) -> bool:
    return admission_key != _LOCAL_ADMISSION_KEY


def _normalize_bind_host(value: str, *, trusted_reverse_proxy: bool) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StandaloneEditorError("bind host must be one exact local address")
    if value.casefold() == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise StandaloneEditorError("bind host must be localhost or an IP literal") from exc
    if address.version != 4:
        raise StandaloneEditorError("bind host must use IPv4 syntax")
    if address.is_loopback:
        if address.compressed != "127.0.0.1" and not trusted_reverse_proxy:
            raise StandaloneEditorError(
                "direct loopback bind must use 127.0.0.1; other addresses require "
                "--trusted-reverse-proxy"
            )
        return address.compressed
    if not trusted_reverse_proxy:
        raise StandaloneEditorError(
            "non-loopback bind requires --trusted-reverse-proxy and a private ingress boundary"
        )
    return address.compressed


def _editor_url(editor_origin: str) -> tuple[str, bool]:
    custom_origin = editor_origin != EDITOR_ORIGIN
    query = EMBED_QUERY
    if custom_origin:
        query += "&offline=1"
        if editor_origin.startswith("http://"):
            query += "&https=0"
    return f"{editor_origin}/?{query}", custom_origin


def _render_assets(
    *,
    editor_origin: str,
    editor_url: str,
    public_base_path: str,
) -> dict[str, str]:
    rendered = dict(ASSETS)
    app_js = rendered["app.js"]
    if (
        app_js.count(_EDITOR_ORIGIN_MARKER) != 1
        or app_js.count(_EDITOR_URL_MARKER) != 1
        or app_js.count(_PUBLIC_BASE_PATH_MARKER) != 1
    ):
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
    app_js = app_js.replace(
        _PUBLIC_BASE_PATH_MARKER,
        f"const PUBLIC_BASE_PATH = {json.dumps(public_base_path, ensure_ascii=False)};",
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
    """Normalize one canonical representation or bounded native import request."""

    if not isinstance(value, dict):
        raise StandaloneEditorError("native representation input must be one JSON object")

    candidate: Any = value
    if value.get("schema_version") == NATIVE_IMPORT_SCHEMA:
        allowed = {"schema_version", "format", "source", "title"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise StandaloneEditorError(
                "native import request contains unknown fields: " + ", ".join(unknown)
            )
        if value.get("format") != "drawio-xml":
            raise StandaloneEditorError("native import request format must be drawio-xml")
        source = value.get("source")
        if not isinstance(source, str):
            raise StandaloneEditorError("native draw.io import source must be text")
        title = value.get("title")
        if title is not None and not isinstance(title, str):
            raise StandaloneEditorError("native draw.io import title must be text")
        try:
            candidate = drawio_xml_to_representation(source, title=title)
        except DrawioImportError as exc:
            raise StandaloneEditorError(f"native draw.io import is unsupported: {exc}") from exc

    try:
        normalized = validate_representation_input(candidate)
    except RepresentationError as exc:
        raise StandaloneEditorError(f"native representation input is invalid: {exc}") from exc
    if normalized["intent"] == "knowledge_map":
        raise StandaloneEditorError(
            "knowledge_map remains on the legacy compatibility path until the "
            "general native same-row/parallel routing boundary is hardened"
        )
    group_count = len(normalized["groups"])
    node_count = len(normalized["nodes"])
    edge_count = len(normalized["edges"])
    routing_pairs = edge_count * edge_count
    if (
        group_count > MAX_NATIVE_GROUPS
        or node_count > MAX_NATIVE_NODES
        or edge_count > MAX_NATIVE_EDGES
        or routing_pairs > MAX_NATIVE_ROUTING_PAIRS
    ):
        raise StandaloneEditorError(
            "native representation exceeds product complexity limits "
            f"(groups<={MAX_NATIVE_GROUPS}, nodes<={MAX_NATIVE_NODES}, "
            f"edges<={MAX_NATIVE_EDGES}, edge-pairs<={MAX_NATIVE_ROUTING_PAIRS})"
        )
    return normalized


def build_standalone_editor(
    output_dir: Path,
    *,
    editor_origin: str = EDITOR_ORIGIN,
    public_base_path: str = "",
) -> dict[str, object]:
    """Write a deterministic static product shell into an empty directory."""

    normalized_origin = _normalize_editor_origin(editor_origin)
    normalized_base_path = _normalize_public_base_path(public_base_path)
    editor_url, custom_origin = _editor_url(normalized_origin)
    assets = _render_assets(
        editor_origin=normalized_origin,
        editor_url=editor_url,
        public_base_path=normalized_base_path,
    )

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
            "runtime": "integrated-serve",
            "api_path": f"{normalized_base_path}{NATIVE_API_PATH}",
            "public_base_path": normalized_base_path,
            "admission": "representation-or-bounded-drawio-except-knowledge-map",
            "admission_scope": {
                "key": "client-ip",
                "max_pinned_entries_per_client": MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT,
                "max_active_build_windows_per_client": MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT,
                "max_client_keys_per_digest": MAX_NATIVE_CLIENT_KEYS_PER_DIGEST,
                "trusted_proxy_header": "X-Forwarded-For",
                "trusted_proxy_source_cidr_required": True,
            },
            "semantic_authority": "schauwerk-representation-input.v1",
            "supported_inputs": ["schauwerk-representation-input.v1", "drawio-xml"],
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
            "native_render_api": "same-origin-integrated-serve-only",
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
            "lossless-drawio-roundtrip",
            "drawio-visual-style-preservation",
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


@dataclass(slots=True)
class _NativeCacheRecord:
    root_key: str
    digest: str
    token: str
    path: Path
    size_bytes: int
    created_at: float
    last_access: float
    pinned_until: float
    max_pinned_until: float
    admission_key: str
    pin_leases: dict[str, float]


@dataclass(slots=True)
class _NativePinWindow:
    max_pinned_until: float
    reacquire_after: float
    admission_keys: set[str]


_NATIVE_CACHE_LOCK = threading.RLock()
_NATIVE_BUILD_LOCK = threading.Lock()
_NATIVE_CACHE_BY_DIGEST: dict[tuple[str, str], _NativeCacheRecord] = {}
_NATIVE_CACHE_BY_TOKEN: dict[tuple[str, str], _NativeCacheRecord] = {}
_NATIVE_PIN_WINDOWS: dict[tuple[str, str], _NativePinWindow] = {}
_NATIVE_BUNDLE_FILES: Final = {
    "app.js": "app.js",
    "diagram.svg": "diagram.svg",
    "index.html": "index.html",
    "interaction.js": "interaction.js",
    "manifest.json": "manifest.json",
    "representation.json": "representation.json",
    "styles.css": "styles.css",
}


def _native_root_key(root: Path) -> str:
    return str(root.resolve())


def _native_bundle_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_symlink():
            raise StandaloneEditorError("native viewer cache must not contain symlinks")
        if entry.is_file():
            total += entry.stat().st_size
    return total


def _forget_native_cache_record(record: _NativeCacheRecord, *, remove_files: bool) -> None:
    _NATIVE_CACHE_BY_DIGEST.pop((record.root_key, record.digest), None)
    _NATIVE_CACHE_BY_TOKEN.pop((record.root_key, record.token), None)
    if remove_files and record.path.exists():
        if record.path.is_symlink() or not record.path.is_dir():
            raise StandaloneEditorError("native viewer cache record path is unsafe")
        shutil.rmtree(record.path)


def _refresh_native_record_pin_state(record: _NativeCacheRecord, *, now: float) -> None:
    for admission_key, pinned_until in list(record.pin_leases.items()):
        if pinned_until <= now:
            record.pin_leases.pop(admission_key, None)
    if record.pin_leases:
        record.pinned_until = max(record.pin_leases.values())
    else:
        record.pinned_until = min(record.pinned_until, now)


def _native_cache_records(root: Path) -> list[_NativeCacheRecord]:
    root_key = _native_root_key(root)
    records: list[_NativeCacheRecord] = []
    now = time.monotonic()
    for key, record in list(_NATIVE_CACHE_BY_DIGEST.items()):
        if key[0] != root_key:
            continue
        if record.path.is_symlink() or not record.path.is_dir():
            _forget_native_cache_record(record, remove_files=False)
            continue
        _refresh_native_record_pin_state(record, now=now)
        records.append(record)
    return records


def _native_pin_window(
    root: Path,
    *,
    digest: str,
    admission_key: str,
    now: float,
) -> tuple[_NativePinWindow, bool]:
    root_key = _native_root_key(root)
    for key, window in list(_NATIVE_PIN_WINDOWS.items()):
        if key[0] == root_key and window.reacquire_after <= now:
            _NATIVE_PIN_WINDOWS.pop(key, None)

    key = (root_key, digest)
    existing = _NATIVE_PIN_WINDOWS.get(key)
    if existing is not None:
        if now >= existing.max_pinned_until:
            raise NativeCacheCapacityError(
                "native viewer digest pin lifetime is exhausted; retry after cooldown"
            )
        if (
            _client_quota_applies(admission_key)
            and admission_key not in existing.admission_keys
            and len(existing.admission_keys) >= MAX_NATIVE_CLIENT_KEYS_PER_DIGEST
        ):
            raise NativeCacheCapacityError(
                "native viewer digest client capacity is temporarily exhausted; retry later"
            )
        return existing, False

    root_windows = sum(1 for key in _NATIVE_PIN_WINDOWS if key[0] == root_key)
    if root_windows >= MAX_NATIVE_PIN_WINDOWS:
        raise NativeCacheCapacityError(
            "native viewer pin-lifetime history is temporarily full; retry later"
        )
    window = _NativePinWindow(
        max_pinned_until=now + NATIVE_CACHE_MAX_PIN_SECONDS,
        reacquire_after=now + NATIVE_CACHE_MAX_PIN_SECONDS,
        admission_keys=set(),
    )
    return window, True


def _assert_native_digest_reacquisition_allowed(
    root: Path,
    *,
    digest: str,
    now: float,
) -> None:
    """Preserve the absolute digest lifetime/cooldown before shared admission checks."""

    with _NATIVE_CACHE_LOCK:
        window = _NATIVE_PIN_WINDOWS.get((_native_root_key(root), digest))
        if (
            window is not None
            and now >= window.max_pinned_until
            and now < window.reacquire_after
        ):
            raise NativeCacheCapacityError(
                "native viewer digest pin lifetime is exhausted; retry after cooldown"
            )


def _assert_native_build_admission(
    root: Path,
    *,
    digest: str,
    admission_key: str,
    now: float,
) -> None:
    """Reject render work whose pin admission is already known to be impossible."""

    with _NATIVE_CACHE_LOCK:
        pinned = [item for item in _native_cache_records(root) if item.pinned_until > now]
        max_pinned_entries = max(0, MAX_NATIVE_CACHE_ENTRIES - 1)
        max_pinned_bytes = max(0, MAX_NATIVE_CACHE_BYTES - MAX_NATIVE_BUNDLE_BYTES)
        if (
            len(pinned) + 1 > max_pinned_entries
            or sum(item.size_bytes for item in pinned) >= max_pinned_bytes
        ):
            raise NativeCacheCapacityError(
                "native viewer pin capacity is already saturated; retry later"
            )
        if _client_quota_applies(admission_key):
            client_pinned = [
                item
                for item in pinned
                if item.pin_leases.get(admission_key, 0.0) > now
            ]
            if len(client_pinned) >= MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT:
                raise NativeCacheCapacityError(
                    "native viewer per-client pin capacity is temporarily exhausted; retry later"
                )

            root_key = _native_root_key(root)
            other_client_build_windows = [
                window
                for (window_root, window_digest), window in _NATIVE_PIN_WINDOWS.items()
                if window_root == root_key
                and window_digest != digest
                and window.max_pinned_until > now
                and admission_key in window.admission_keys
            ]
            if len(other_client_build_windows) >= MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT:
                raise NativeCacheCapacityError(
                    "native viewer per-client build capacity is temporarily exhausted; retry later"
                )


def _assert_native_pin_capacity(
    root: Path,
    *,
    record: _NativeCacheRecord,
    admission_key: str,
    now: float,
) -> None:
    with _NATIVE_CACHE_LOCK:
        pinned = [
            item
            for item in _native_cache_records(root)
            if item is not record and item.pinned_until > now
        ]
        max_pinned_entries = max(0, MAX_NATIVE_CACHE_ENTRIES - 1)
        max_pinned_bytes = max(0, MAX_NATIVE_CACHE_BYTES - MAX_NATIVE_BUNDLE_BYTES)
        client_pinned = (
            [
                item
                for item in pinned
                if item.pin_leases.get(admission_key, 0.0) > now
            ]
            if _client_quota_applies(admission_key)
            else []
        )
        if (
            len(pinned) + 1 > max_pinned_entries
            or sum(item.size_bytes for item in pinned) + record.size_bytes > max_pinned_bytes
            or (
                _client_quota_applies(admission_key)
                and len(client_pinned) + 1 > MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT
            )
        ):
            raise NativeCacheCapacityError(
                "native viewer pin capacity is temporarily reserved; retry later"
            )


def _pin_native_cache_record(
    root: Path,
    record: _NativeCacheRecord,
    *,
    admission_key: str,
) -> None:
    now = time.monotonic()
    _refresh_native_record_pin_state(record, now=now)
    current_pinned_until = record.pin_leases.get(admission_key, 0.0)
    if (
        admission_key not in record.pin_leases
        and _client_quota_applies(admission_key)
        and len(record.pin_leases) >= MAX_NATIVE_CLIENT_KEYS_PER_DIGEST
    ):
        raise NativeCacheCapacityError(
            "native viewer digest client capacity is temporarily exhausted; retry later"
        )
    next_pinned_until = min(
        max(current_pinned_until, now + NATIVE_CACHE_GRACE_SECONDS),
        record.max_pinned_until,
    )
    if current_pinned_until <= now and next_pinned_until > now:
        _assert_native_pin_capacity(
            root,
            record=record,
            admission_key=admission_key,
            now=now,
        )
    record.last_access = now
    record.pin_leases[admission_key] = next_pinned_until
    record.pinned_until = max(record.pin_leases.values(), default=now)


def _prune_native_cache(
    root: Path,
    *,
    keep: _NativeCacheRecord | None,
    reserve_bytes: int = 0,
    reserve_entries: int = 0,
) -> None:
    victim_paths: list[Path] = []
    with _NATIVE_CACHE_LOCK:
        records = _native_cache_records(root)
        total = sum(item.size_bytes for item in records)
        now = time.monotonic()
        candidates = sorted(
            (
                record
                for record in records
                if record is not keep and record.pinned_until <= now
            ),
            key=lambda item: (item.last_access, item.token),
        )
        while candidates and (
            len(records) + reserve_entries > MAX_NATIVE_CACHE_ENTRIES
            or total + reserve_bytes > MAX_NATIVE_CACHE_BYTES
        ):
            victim = candidates.pop(0)
            victim_paths.append(victim.path)
            _forget_native_cache_record(victim, remove_files=False)
            total -= victim.size_bytes
            records.remove(victim)
        if (
            len(records) + reserve_entries > MAX_NATIVE_CACHE_ENTRIES
            or total + reserve_bytes > MAX_NATIVE_CACHE_BYTES
        ):
            raise NativeCacheCapacityError(
                "native viewer cache capacity is temporarily pinned; retry later"
            )

    for victim_path in victim_paths:
        if (
            victim_path.exists()
            and victim_path.is_dir()
            and not victim_path.is_symlink()
        ):
            shutil.rmtree(victim_path)


def _native_cache_by_digest(root: Path, digest: str) -> _NativeCacheRecord | None:
    with _NATIVE_CACHE_LOCK:
        record = _NATIVE_CACHE_BY_DIGEST.get((_native_root_key(root), digest))
        if record is None:
            return None
        if record.path.is_symlink() or not record.path.is_dir():
            _forget_native_cache_record(record, remove_files=False)
            return None
        return record


def _native_cache_by_token(root: Path, token: str) -> _NativeCacheRecord | None:
    with _NATIVE_CACHE_LOCK:
        record = _NATIVE_CACHE_BY_TOKEN.get((_native_root_key(root), token))
        if record is None:
            return None
        if record.path.is_symlink() or not record.path.is_dir():
            _forget_native_cache_record(record, remove_files=False)
            return None
        return record


def _run_native_viewer_build(
    *,
    value: dict[str, Any],
    target: Path,
    serve_binding: str,
    public_base_path: str,
    timeout_seconds: float,
) -> None:
    """Build in a killable child so the absolute request deadline bounds render CPU."""

    if timeout_seconds <= 0:
        raise NativeRequestDeadlineError("native render request deadline expired before build")
    input_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".native-input-",
            suffix=".json",
            dir=target.parent,
            text=True,
        )
        input_path = Path(raw_path)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.chmod(input_path, 0o600)
        stderr_tail = bytearray()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "schauwerk.visual.native_viewer",
                "build",
                "--input",
                str(input_path),
                "--output-dir",
                str(target),
                "--serve-binding",
                serve_binding,
                "--public-base-path",
                public_base_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if process.stderr is None:
            process.kill()
            process.wait()
            raise NativeViewerError("native viewer subprocess stderr pipe unavailable")

        def drain_stderr() -> None:
            while True:
                chunk = process.stderr.read(8192)
                if not chunk:
                    return
                stderr_tail.extend(chunk)
                if len(stderr_tail) > 4096:
                    del stderr_tail[:-4096]

        stderr_reader = threading.Thread(
            target=drain_stderr,
            name="schauwerk-native-render-stderr",
            daemon=True,
        )
        stderr_reader.start()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            stderr_reader.join()
            raise NativeRequestDeadlineError(
                "native render request deadline expired during renderer build"
            ) from exc
        stderr_reader.join()
        if returncode != 0:
            stderr = bytes(stderr_tail).decode("utf-8", errors="replace").strip()
            if stderr:
                print(
                    f"native viewer subprocess failed: {stderr}",
                    file=sys.stderr,
                )
            raise NativeViewerError("native viewer subprocess build failed")
    finally:
        if input_path is not None:
            try:
                input_path.unlink()
            except FileNotFoundError:
                pass


def _abandon_native_cache_record(
    root: Path,
    record: _NativeCacheRecord,
    *,
    admission_key: str | None = None,
) -> None:
    """Release only the undelivered client's lease while keeping reusable bytes."""

    with _NATIVE_CACHE_LOCK:
        key = (record.root_key, record.digest)
        if _NATIVE_CACHE_BY_DIGEST.get(key) is not record:
            return
        now = time.monotonic()
        lease_key = admission_key or record.admission_key
        record.pin_leases.pop(lease_key, None)
        record.last_access = now
        _refresh_native_record_pin_state(record, now=now)
        # Keep both the cache record and digest pin window. The bytes remain
        # reusable, while another client's active lease is never revoked by
        # this request's failed response.


def _build_native_cache_record(
    root: Path,
    *,
    digest: str,
    value: dict[str, Any],
    serve_binding: str,
    public_base_path: str,
    admission_key: str = "local",
    deadline_monotonic: float | None = None,
) -> tuple[_NativeCacheRecord, bool]:
    with _NATIVE_CACHE_LOCK:
        now = time.monotonic()
        if deadline_monotonic is not None and now >= deadline_monotonic:
            raise NativeRequestDeadlineError(
                "native render request deadline expired before cache lookup"
            )
        existing = _native_cache_by_digest(root, digest)
        if existing is not None and existing.max_pinned_until > now:
            _pin_native_cache_record(root, existing, admission_key=admission_key)
            return existing, False
        _assert_native_digest_reacquisition_allowed(root, digest=digest, now=now)
        _assert_native_build_admission(
            root,
            digest=digest,
            admission_key=admission_key,
            now=now,
        )

    lock_timeout = NATIVE_REQUEST_TIMEOUT_SECONDS
    if deadline_monotonic is not None:
        lock_timeout = min(lock_timeout, max(0.0, deadline_monotonic - time.monotonic()))
        if lock_timeout <= 0:
            raise NativeRequestDeadlineError(
                "native render request deadline expired before build admission"
            )
    if not _NATIVE_BUILD_LOCK.acquire(timeout=lock_timeout):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise NativeRequestDeadlineError(
                "native render request deadline expired while waiting for renderer capacity"
            )
        raise NativeCacheCapacityError(
            "native viewer build capacity is temporarily busy; retry later"
        )
    try:
        with _NATIVE_CACHE_LOCK:
            now = time.monotonic()
            if deadline_monotonic is not None and now >= deadline_monotonic:
                raise NativeRequestDeadlineError(
                    "native render request deadline expired before renderer build"
                )
            existing = _native_cache_by_digest(root, digest)
            if existing is not None and existing.max_pinned_until > now:
                _pin_native_cache_record(root, existing, admission_key=admission_key)
                return existing, False
            _assert_native_digest_reacquisition_allowed(root, digest=digest, now=now)
            _assert_native_build_admission(
                root,
                digest=digest,
                admission_key=admission_key,
                now=now,
            )
            pin_window, new_pin_window = _native_pin_window(
                root,
                digest=digest,
                admission_key=admission_key,
                now=now,
            )

        _prune_native_cache(
            root,
            keep=None,
            reserve_bytes=MAX_NATIVE_BUNDLE_BYTES,
            reserve_entries=1,
        )
        cache_root = root / ".native-cache"
        if cache_root.exists() and (
            cache_root.is_symlink() or not cache_root.is_dir()
        ):
            raise StandaloneEditorError("native viewer cache root is unsafe")
        cache_root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(cache_root, 0o700)

        with _NATIVE_CACHE_LOCK:
            token = secrets.token_hex(16)
            while (_native_root_key(root), token) in _NATIVE_CACHE_BY_TOKEN:
                token = secrets.token_hex(16)
        target = Path(tempfile.mkdtemp(prefix="bundle-", dir=cache_root))

        try:
            if deadline_monotonic is None:
                build_native_viewer(
                    value,
                    target,
                    serve_binding=serve_binding,
                    public_base_path=public_base_path,
                )
            else:
                remaining = deadline_monotonic - time.monotonic()
                _run_native_viewer_build(
                    value=value,
                    target=target,
                    serve_binding=serve_binding,
                    public_base_path=public_base_path,
                    timeout_seconds=remaining,
                )
                if time.monotonic() >= deadline_monotonic:
                    raise NativeRequestDeadlineError(
                        "native render request deadline expired after renderer build"
                    )
            bundle_size = _native_bundle_size(target)
            if bundle_size > MAX_NATIVE_BUNDLE_BYTES:
                raise StandaloneEditorError(
                    "native viewer bundle exceeds the 16 MiB cache budget"
                )
        except Exception:
            if target.exists() and target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            raise

        stale_path: Path | None = None
        winner: _NativeCacheRecord | None = None
        try:
            with _NATIVE_CACHE_LOCK:
                now = time.monotonic()
                if deadline_monotonic is not None and now >= deadline_monotonic:
                    raise NativeRequestDeadlineError(
                        "native render request deadline expired before cache registration"
                    )
                if now >= pin_window.max_pinned_until:
                    raise NativeCacheCapacityError(
                        "native viewer digest pin lifetime expired during build"
                    )
                existing = _native_cache_by_digest(root, digest)
                if existing is not None and existing.max_pinned_until > now:
                    _pin_native_cache_record(root, existing, admission_key=admission_key)
                    winner = existing
                else:
                    record = _NativeCacheRecord(
                        root_key=_native_root_key(root),
                        digest=digest,
                        token=token,
                        path=target,
                        size_bytes=bundle_size,
                        created_at=now,
                        last_access=now,
                        pinned_until=min(
                            now + NATIVE_CACHE_GRACE_SECONDS,
                            pin_window.max_pinned_until,
                        ),
                        max_pinned_until=pin_window.max_pinned_until,
                        admission_key=admission_key,
                        pin_leases={
                            admission_key: min(
                                now + NATIVE_CACHE_GRACE_SECONDS,
                                pin_window.max_pinned_until,
                            )
                        },
                    )
                    _assert_native_pin_capacity(
                        root,
                        record=record,
                        admission_key=admission_key,
                        now=now,
                    )
                    if (
                        _client_quota_applies(admission_key)
                        and admission_key not in pin_window.admission_keys
                    ):
                        if (
                            len(pin_window.admission_keys)
                            >= MAX_NATIVE_CLIENT_KEYS_PER_DIGEST
                        ):
                            raise NativeCacheCapacityError(
                                "native viewer digest client capacity is temporarily "
                                "exhausted; retry later"
                            )
                        pin_window.admission_keys.add(admission_key)
                    if existing is not None:
                        stale_path = existing.path
                        _forget_native_cache_record(existing, remove_files=False)
                    if new_pin_window:
                        _NATIVE_PIN_WINDOWS[(record.root_key, digest)] = pin_window
                    _NATIVE_CACHE_BY_DIGEST[(record.root_key, digest)] = record
                    _NATIVE_CACHE_BY_TOKEN[(record.root_key, token)] = record
                    winner = record
        except Exception:
            if target.exists() and target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            raise

        if winner is not None and winner.path != target:
            if target.exists() and target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            return winner, False

        _prune_native_cache(root, keep=winner)
        if (
            stale_path is not None
            and stale_path != target
            and stale_path.exists()
            and stale_path.is_dir()
            and not stale_path.is_symlink()
        ):
            shutil.rmtree(stale_path)
        if winner is None:
            raise AssertionError("native cache build did not select a winner")
        return winner, True
    finally:
        _NATIVE_BUILD_LOCK.release()


class _EditorRequestHandler(SimpleHTTPRequestHandler):
    """Static product handler plus one bounded same-origin native-render endpoint."""

    editor_origin: str = EDITOR_ORIGIN
    public_base_path: str = ""
    native_serve_binding: str = "127.0.0.1-only"
    trusted_proxy_networks: tuple[ipaddress.IPv4Network, ...] = ()
    request_timeout_seconds: float = NATIVE_REQUEST_TIMEOUT_SECONDS

    def setup(self) -> None:
        super().setup()
        self._request_deadline_expired = False
        self._request_deadline_at = time.monotonic() + self.request_timeout_seconds
        self.connection.settimeout(self.request_timeout_seconds)
        self._request_deadline_timer = threading.Timer(
            self.request_timeout_seconds,
            self._expire_request_connection,
        )
        self._request_deadline_timer.daemon = True
        self._request_deadline_timer.start()

    def _expire_request_connection(self) -> None:
        self._request_deadline_expired = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _request_deadline_is_expired(self) -> bool:
        if self._request_deadline_expired:
            return True
        if time.monotonic() >= self._request_deadline_at:
            self._request_deadline_expired = True
            return True
        return False

    def _native_admission_key(self) -> str | None:
        if self.native_serve_binding == "trusted-reverse-proxy-private-ingress":
            try:
                peer = ipaddress.ip_address(str(self.client_address[0]))
            except ValueError:
                return None
            if not isinstance(peer, ipaddress.IPv4Address) or not any(
                peer in network for network in self.trusted_proxy_networks
            ):
                return None
            raw_values = self.headers.get_all("X-Forwarded-For", [])
            if len(raw_values) != 1:
                return None
            raw = raw_values[0]
            if not raw or raw != raw.strip() or "," in raw:
                return None
            try:
                address = ipaddress.ip_address(raw)
            except ValueError:
                return None
            return address.compressed
        return _LOCAL_ADMISSION_KEY

    def finish(self) -> None:
        timer = getattr(self, "_request_deadline_timer", None)
        if timer is not None:
            timer.cancel()
        try:
            super().finish()
        except OSError:
            if not getattr(self, "_request_deadline_expired", False):
                raise

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", _content_security_policy(self.editor_origin))
        super().end_headers()

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        write_body: bool = True,
    ) -> bool:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("ascii")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if write_body:
                self.wfile.write(encoded)
        except OSError:
            self.close_connection = True
            return False
        return True

    def _has_valid_loopback_host(self) -> bool:
        raw_hosts = self.headers.get_all("Host", [])
        if len(raw_hosts) != 1:
            return False
        raw_host = raw_hosts[0]
        if not raw_host or raw_host != raw_host.strip():
            return False
        host = raw_host.casefold()
        port = int(self.server.server_address[1])
        return host in {
            "127.0.0.1",
            f"127.0.0.1:{port}",
            "localhost",
            f"localhost:{port}",
            "[::1]",
            f"[::1]:{port}",
        }

    def _reject_non_loopback_host(self, *, write_body: bool = True) -> bool:
        if self._has_valid_loopback_host():
            return False
        self._send_json(
            HTTPStatus.MISDIRECTED_REQUEST,
            {"error": "local Schaubild server accepts loopback Host headers only"},
            write_body=write_body,
        )
        return True

    def _decoded_request_path(self) -> str | None:
        raw_path = urlsplit(self.path).path
        try:
            decoded = unquote(raw_path, encoding="utf-8", errors="strict")
        except UnicodeError:
            return None
        if "\x00" in decoded:
            return None
        return decoded

    def _reject_private_cache_path(self, *, write_body: bool = True) -> bool:
        decoded = self._decoded_request_path()
        if decoded is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "request path is not canonical UTF-8"},
                write_body=write_body,
            )
            return True
        segments = [part for part in decoded.split("/") if part not in {"", ".", ".."}]
        if ".native-cache" in segments:
            self.send_error(HTTPStatus.NOT_FOUND)
            return True
        return False

    def _native_request_parts(self) -> tuple[str, str] | None:
        path = self._decoded_request_path()
        if path is None:
            return ("", "")
        match = re.fullmatch(r"/native/([0-9a-f]{32})/([^/]+)", path)
        if match is None:
            return None
        filename = _NATIVE_BUNDLE_FILES.get(match.group(2))
        if filename is None:
            return ("", "")
        return match.group(1), filename

    def _serve_native_bundle(self, *, head_only: bool) -> bool:
        parts = self._native_request_parts()
        if parts is None:
            return False
        token, filename = parts
        if not token or not filename:
            self.send_error(HTTPStatus.NOT_FOUND)
            return True
        admission_key = self._native_admission_key()
        if admission_key is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": (
                        "trusted reverse proxy source must be allowlisted and provide "
                        "exactly one canonical X-Forwarded-For client IP"
                    )
                },
                write_body=not head_only,
            )
            return True

        root = Path(self.directory).resolve()
        status: HTTPStatus | None = None
        handle = None
        stat_result = None
        content_type = "application/octet-stream"
        with _NATIVE_CACHE_LOCK:
            record = _native_cache_by_token(root, token)
            if record is None:
                status = HTTPStatus.NOT_FOUND
            elif record.max_pinned_until <= time.monotonic():
                status = HTTPStatus.GONE
            else:
                now = time.monotonic()
                _refresh_native_record_pin_state(record, now=now)
                if (
                    admission_key != record.admission_key
                    and admission_key not in record.pin_leases
                ):
                    status = HTTPStatus.NOT_FOUND
                else:
                    try:
                        _pin_native_cache_record(
                            root,
                            record,
                            admission_key=admission_key,
                        )
                    except NativeCacheCapacityError:
                        status = HTTPStatus.SERVICE_UNAVAILABLE
                    else:
                        target = record.path / filename
                        if (
                            target.is_symlink()
                            or not target.is_file()
                            or target.parent != record.path
                        ):
                            status = HTTPStatus.NOT_FOUND
                        else:
                            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                            try:
                                descriptor = os.open(target, flags)
                                stat_result = os.fstat(descriptor)
                                handle = os.fdopen(descriptor, "rb")
                                content_type = self.guess_type(str(target))
                            except OSError:
                                status = HTTPStatus.NOT_FOUND

        if status is not None:
            self.send_error(status)
            return True
        if handle is None or stat_result is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return True

        try:
            if self._request_deadline_is_expired():
                self.close_connection = True
                return True
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(stat_result.st_size))
            self.send_header(
                "Last-Modified",
                self.date_time_string(stat_result.st_mtime),
            )
            self.end_headers()
            if not head_only:
                self.copyfile(handle, self.wfile)
        except OSError:
            self.close_connection = True
        finally:
            handle.close()
        return True

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_non_loopback_host():
            return
        if self._reject_private_cache_path():
            return
        if self._serve_native_bundle(head_only=False):
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._reject_non_loopback_host(write_body=False):
            return
        if self._reject_private_cache_path(write_body=False):
            return
        if self._serve_native_bundle(head_only=True):
            return
        super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != NATIVE_API_PATH:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        if self._reject_non_loopback_host():
            return
        admission_key = self._native_admission_key()
        if admission_key is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": (
                        "trusted reverse proxy must provide exactly one canonical "
                        "X-Forwarded-For client IP"
                    )
                },
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
        try:
            payload = self.rfile.read(content_length)
        except TimeoutError:
            self.close_connection = True
            try:
                self._send_json(
                    HTTPStatus.REQUEST_TIMEOUT,
                    {"error": "native render request body timed out"},
                )
            except OSError:
                pass
            return
        except OSError:
            if self._request_deadline_expired:
                self.close_connection = True
                return
            raise
        if self._request_deadline_expired:
            self.close_connection = True
            return
        if len(payload) != content_length:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "incomplete request body"})
            return
        try:
            value = json.loads(payload.decode("utf-8"))
            normalized = _native_product_input(value)
            digest = str(normalized["input_digest"])
            canonical_input = {
                key: item for key, item in normalized.items() if key != "input_digest"
            }
            root = Path(self.directory).resolve()
            record, created = _build_native_cache_record(
                root,
                digest=digest,
                value=canonical_input,
                serve_binding=self.native_serve_binding,
                public_base_path=self.public_base_path,
                admission_key=admission_key,
                deadline_monotonic=self._request_deadline_at,
            )
            token = record.token
        except NativeRequestDeadlineError:
            self.close_connection = True
            return
        except NativeCacheCapacityError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            return
        except (
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
            StandaloneEditorError,
            NativeViewerError,
        ) as exc:
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return

        if self._request_deadline_is_expired():
            if created:
                _abandon_native_cache_record(
                    root,
                    record,
                    admission_key=admission_key,
                )
            self.close_connection = True
            return
        delivered = self._send_json(
            HTTPStatus.OK,
            {
                "input_digest": digest,
                "renderer": NATIVE_RENDERER,
                "url": f"{self.public_base_path}/native/{token}/index.html",
            },
        )
        if not delivered and created:
            _abandon_native_cache_record(
                root,
                record,
                admission_key=admission_key,
            )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server with a hard cap on concurrent request workers."""

    daemon_threads = True
    block_on_close = False
    max_workers: int = NATIVE_SERVER_MAX_WORKERS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self._worker_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()


def serve_standalone_editor(
    *,
    port: int = 8765,
    build_dir: Path | None = None,
    editor_origin: str = EDITOR_ORIGIN,
    bind_host: str = "127.0.0.1",
    public_base_path: str = "",
    trusted_reverse_proxy: bool = False,
    trusted_proxy_source_cidrs: tuple[str, ...] = (),
) -> None:
    """Serve the product shell.

    Loopback remains the default. A non-loopback bind is admitted only when the
    caller explicitly declares a trusted private reverse-proxy boundary. The
    container port must remain private to that proxy. The loopback Host check is
    defense in depth and is not a substitute for an unexposed service port.

    A caller-supplied build directory must either be absent or empty. When no
    directory is supplied, a process-local temporary directory is created and
    removed after the server stops.
    """

    if not 0 <= port <= 65535:
        raise StandaloneEditorError("port must be between 0 and 65535")
    normalized_origin = _normalize_editor_origin(editor_origin)
    normalized_bind_host = _normalize_bind_host(
        bind_host,
        trusted_reverse_proxy=trusted_reverse_proxy,
    )
    normalized_base_path = _normalize_public_base_path(public_base_path)
    trusted_proxy_networks = _normalize_trusted_proxy_source_cidrs(
        trusted_proxy_source_cidrs
    )
    if trusted_reverse_proxy and not trusted_proxy_networks:
        raise StandaloneEditorError(
            "--trusted-reverse-proxy requires at least one --trusted-proxy-source-cidr"
        )
    if not trusted_reverse_proxy and trusted_proxy_networks:
        raise StandaloneEditorError(
            "--trusted-proxy-source-cidr requires --trusted-reverse-proxy"
        )
    if normalized_base_path and not trusted_reverse_proxy:
        raise StandaloneEditorError(
            "public base path requires --trusted-reverse-proxy serving context"
        )
    _, custom_origin = _editor_url(normalized_origin)

    temporary = build_dir is None
    if temporary:
        root = Path(tempfile.mkdtemp(prefix="schauwerk-editor-"))
    else:
        root = build_dir.expanduser().absolute()

    try:
        build_standalone_editor(
            root,
            editor_origin=normalized_origin,
            public_base_path=normalized_base_path,
        )
        handler_class = type(
            "ConfiguredEditorRequestHandler",
            (_EditorRequestHandler,),
            {
                "editor_origin": normalized_origin,
                "public_base_path": normalized_base_path,
                "native_serve_binding": (
                    "trusted-reverse-proxy-private-ingress"
                    if trusted_reverse_proxy
                    else "127.0.0.1-only"
                ),
                "trusted_proxy_networks": trusted_proxy_networks,
            },
        )
        handler = partial(handler_class, directory=str(root))
        with _BoundedThreadingHTTPServer((normalized_bind_host, port), handler) as server:
            actual_port = int(server.server_address[1])
            print(
                f"standalone editor: http://{normalized_bind_host}:{actual_port}/ "
                f"public_base_path={normalized_base_path or '/'}"
            )
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
    build.add_argument("--public-base-path", default="")

    serve = commands.add_parser("serve", help="serve the editor shell")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--build-dir", type=Path)
    serve.add_argument("--editor-origin", default=EDITOR_ORIGIN)
    serve.add_argument("--bind-host", default="127.0.0.1")
    serve.add_argument("--public-base-path", default="")
    serve.add_argument("--trusted-reverse-proxy", action="store_true")
    serve.add_argument(
        "--trusted-proxy-source-cidr",
        action="append",
        default=[],
        help="canonical IPv4 CIDR allowed to supply trusted proxy headers; repeatable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        manifest = build_standalone_editor(
            args.output_dir,
            editor_origin=args.editor_origin,
            public_base_path=args.public_base_path,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve_standalone_editor(
            port=args.port,
            build_dir=args.build_dir,
            editor_origin=args.editor_origin,
            bind_host=args.bind_host,
            public_base_path=args.public_base_path,
            trusted_reverse_proxy=args.trusted_reverse_proxy,
            trusted_proxy_source_cidrs=tuple(args.trusted_proxy_source_cidr),
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())