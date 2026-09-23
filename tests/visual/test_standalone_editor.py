# ruff: noqa: E501
from __future__ import annotations

import base64
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import schauwerk.visual.standalone_editor as standalone_editor
from schauwerk.visual.standalone_editor import (
    EDITOR_ORIGIN,
    MANIFEST_SCHEMA,
    NATIVE_API_PATH,
    NATIVE_RENDERER,
    StandaloneEditorError,
    _content_security_policy,
    _EditorRequestHandler,
    _native_product_input,
    _normalize_bind_host,
    _normalize_public_base_path,
    build_standalone_editor,
)


def _js_string_constant(source: str, name: str) -> str:
    match = re.search(
        rf'^const {re.escape(name)} = (?P<value>"[^"\r\n]+")\s*;$',
        source,
        flags=re.MULTILINE,
    )
    assert match is not None
    return str(json.loads(match.group("value")))


def test_build_standalone_editor_writes_deterministic_bundle(tmp_path: Path) -> None:
    output = tmp_path / "editor"

    manifest = build_standalone_editor(output)

    assert manifest["schema_version"] == MANIFEST_SCHEMA
    assert manifest["editor_origin"] == EDITOR_ORIGIN
    assert manifest["editor_engine"] == NATIVE_RENDERER
    assert manifest["legacy_editor_engine"] == "diagrams.net-embed"
    assert manifest["cutover_status"] == "native-primary-with-legacy-compatibility"
    assert manifest["engine_delivery"] == "remote-browser-iframe"
    assert manifest["network_boundary"] == {
        "shell": "local-static-files",
        "native_render_api": "same-origin-integrated-serve-only",
        "native_viewer_external_requests_required": False,
        "legacy_editor_runtime": EDITOR_ORIGIN,
        "public_embed_runtime": True,
        "operator_configured_editor_runtime": False,
        "offline_mode_requested": False,
        "offline_complete": False,
    }
    assert manifest["supported_inputs"] == [
        "schauwerk-representation-input.v1",
        "mermaid",
        "json-canvas-1.0",
        "drawio-xml",
    ]
    assert manifest["native_renderer"]["admission_scope"] == {
        "key": "client-ip",
        "max_pinned_entries_per_client": standalone_editor.MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT,
        "max_active_build_windows_per_client": (
            standalone_editor.MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT
        ),
        "max_client_keys_per_digest": standalone_editor.MAX_NATIVE_CLIENT_KEYS_PER_DIGEST,
        "trusted_proxy_header": "X-Forwarded-For",
        "trusted_proxy_source_cidr_required": True,
    }
    assert "representation-knowledge-map-native-cutover" in manifest["does_not_establish"]
    assert {item["path"] for item in manifest["files"]} == {
        "app.js",
        "canvas-import.js",
        "index.html",
        "styles.css",
    }
    on_disk = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    helper_js = (output / "canvas-import.js").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "EDITOR_ORIGIN") == EDITOR_ORIGIN
    assert _js_string_constant(app_js, "EDITOR_URL") == manifest["editor_url"]
    assert "offline=1" not in _js_string_constant(app_js, "EDITOR_URL")
    assert "jsonCanvasToDrawioXml" in helper_js
    assert "READABLE_NODE_FONT_SIZE = 18" in helper_js
    assert "READABLE_EDGE_FONT_SIZE = 16" in helper_js
    assert "COLLISION_SAFE_LAYOUT_CONFIG = Object.freeze" in helper_js
    assert '"elk.spacing.edgeNode": "28"' in helper_js
    assert '"elk.layered.spacing.edgeNodeBetweenLayers": "32"' in helper_js
    assert '"elk.layered.edgeLabels.centerLabelPlacementStrategy": "SPACE_EFFICIENT_LAYER"' in helper_js
    assert "MIN_READABLE_SCALE = 0.65" in helper_js
    assert helper_js.count("fontSize=${fontSize}") >= 2
    assert "event.origin !== EDITOR_ORIGIN" in app_js
    assert "event.source !== elements.frame.contentWindow" in app_js
    assert 'headers["X-Schauwerk-Native-Supersede"] = nativeSupersedeToken' in app_js
    assert 'querySelector("#nativeDiagram")' in app_js
    assert 'clone.removeAttribute("data-input-digest")' in app_js
    assert "SVG aus aktuellem Canvas-Dokument bereit" in app_js
    assert "Aktuelle SVG-Ausgabe konnte nicht gelesen werden" in app_js
    assert "maxFitScale: 1" in app_js
    assert re.search(
        r'^import \{[^}]*\bREADABILITY_ZOOM_FACTOR\b[^}]*\} from "\./canvas-import\.js";$',
        app_js,
        flags=re.MULTILINE,
    )
    assert "zoomFactor: READABILITY_ZOOM_FACTOR" in app_js
    assert "MIN_CONFIGURABLE_FONT_SIZE = 8" in helper_js
    assert "MAX_CONFIGURABLE_FONT_SIZE = 72" in helper_js
    assert 'FONT_PREFERENCE_KEY = "schauwerk.standalone-editor.font-size.v1"' in app_js
    assert "defaultVertexStyle: { fontSize: String(preferredNodeFontSize) }" in app_js
    assert "defaultEdgeStyle: {" in app_js
    assert "fontSize: String(edgeFontSizeFor(preferredNodeFontSize))" in app_js
    assert 'sourcePerimeterSpacing: "12"' in app_js
    assert 'targetPerimeterSpacing: "12"' in app_js
    assert 'labelBackgroundColor: "#ffffff"' in app_js
    assert 'actionName: "decreaseFontSize"' in app_js
    assert 'actionName: "increaseFontSize"' in app_js
    assert 'actionName: "format"' in app_js
    assert 'actionName: "selectAll"' in app_js
    assert app_js.index("preferredNodeFontSize = readFontPreference();") < app_js.index('initialQuery.get("new") === "1"')
    assert "function enforceReadableInitialScale(scale)" in app_js
    assert "enforceReadableInitialScale(message.scale);" in app_js
    assert 'actionName: "zoomIn"' in app_js
    assert 'format: "xml"' not in app_js
    assert "validateExportDataUri(message.data, wanted)" in app_js
    assert "exportDataUriToBlob(validatedData, wanted)" in app_js
    assert "downloadDataUri(" not in app_js
    assert "preparedDownloadUrl = URL.createObjectURL(blob)" in app_js
    assert "if (wanted === null) return;" in app_js
    assert 'setStatus(`Export bereit · „${label} speichern“ tippen`)' in app_js
    assert "if (saveDraft(validateDiagramXml(message.xml)))" in app_js
    assert "if (!editorReady)" in app_js
    assert 'setStatus("Editor ist noch nicht bereit")' in app_js
    assert app_js.index("if (!editorReady)") < app_js.index("pendingExport = format;")
    assert "if (pendingExport !== null)" in app_js
    assert 'setStatus("Export läuft bereits …")' in app_js
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    assert "KI-Ergebnis hier einfügen" in index_html
    assert 'id="downloadLink" hidden' in index_html
    assert 'id="fullscreenButton"' in index_html
    assert 'id="fontDefaultInput" type="number" min="8" max="72" step="1"' in index_html
    assert 'id="fontDecreaseButton"' in index_html
    assert 'id="fontPanelButton"' in index_html
    assert 'id="fontIncreaseButton"' in index_html
    assert 'id="fontAllButton"' in index_html
    file_input = re.search(r'<input\b[^>]*\bid="fileInput"[^>]*>', index_html)
    assert file_input is not None
    assert re.search(r"\baccept\s*=", file_input.group(0), flags=re.IGNORECASE) is None
    assert "schauwerk-representation-input.v1" in index_html
    assert "Legacy leer" in index_html
    assert "Renderer-Cutover:" in index_html
    assert 'aria-pressed="false"' in index_html
    assert 'aria-label="Vollbildmodus aktivieren"' in index_html
    assert "body.editor-focus .topline" in styles_css
    assert "body.editor-focus .workspace-bar > :not(.fullscreen-toggle)" in styles_css
    assert "height: 100dvh" in styles_css
    assert 'fullscreenButton: document.querySelector("#fullscreenButton")' in app_js
    assert 'if (detected.kind === "drawio")' in app_js
    assert 'schema_version: NATIVE_IMPORT_SCHEMA' in app_js
    assert 'format: "drawio-xml"' in app_js
    assert "legacyXml: xml" in app_js
    assert "function launchLegacy(load)" in app_js
    assert 'elements.legacyEditButton.addEventListener("click"' in app_js
    assert 'elements.legacyFallbackButton.addEventListener("click"' in app_js
    assert 'id="legacyEditButton"' in index_html
    assert 'id="legacyFallbackButton"' in index_html
    assert "function replaceEditorFrame()" in app_js
    assert "const frame = previous.cloneNode(false);" in app_js
    assert "frame.inert = false;" in app_js
    assert "previous.replaceWith(frame);" in app_js
    assert "elements.frame = frame;" in app_js
    assert "if (elements.frame !== frame) return;" in app_js
    assert "let loadIntentGeneration = 0;" in app_js
    assert "let nativeLaunchTail = Promise.resolve();" in app_js
    assert 'let nativeSupersedeToken = "";' in app_js
    assert "let nativeCanvasRenderStale = false;" in app_js
    assert "let pendingInitialCollisionSafeLayout = false;" in app_js
    assert "function invalidateLoadIntents()" in app_js
    assert "const loadIntent = invalidateLoadIntents();" in app_js
    assert 'elements.fileInput.value = "";' in app_js
    file_change = app_js.index('elements.fileInput.addEventListener("change"')
    file_reset = app_js.index('elements.fileInput.value = "";', file_change)
    file_open = app_js.index("if (file) openFile(file);", file_reset)
    assert file_change < file_reset < file_open
    assert "if (loadIntent !== loadIntentGeneration) return;" in app_js
    open_file = app_js.index("async function openFile(file)")
    open_file_end = app_js.index("function exportDiagram(format)", open_file)
    open_file_source = app_js[open_file:open_file_end]
    assert open_file_source.count("if (loadIntent !== loadIntentGeneration) return;") == 2
    launch_start = app_js.index("function launch(load)")
    launch_end = app_js.index("function loadPendingIntoEditor()", launch_start)
    launch_source = app_js[launch_start:launch_end]
    assert "invalidateLoadIntents();" in launch_source
    native_start = launch_source.index("async function launchNative(load, options = {})")
    native_source = launch_source[native_start:]
    assert "options.preserveActiveFrame && editorReady && currentNativeUrl" in native_source
    assert "frame.inert = true;" in native_source
    assert "currentNativeUrl = activeNativeUrl;" in native_source
    assert "Bestehende Ansicht bleibt sichtbar und weiter bearbeitbar" in native_source
    assert "activeFrame.inert = false;" in native_source
    assert "{ preserveActiveFrame: true }" in app_js
    assert "const previousLaunch = nativeLaunchTail;" in native_source
    assert "await previousLaunch;" in native_source
    assert native_source.index("await previousLaunch;") < native_source.index(
        "const response = await fetch(NATIVE_API_PATH"
    )
    assert native_source.index(
        "if (loadIntent !== loadIntentGeneration) return;"
    ) < native_source.index("const response = await fetch(NATIVE_API_PATH")
    token_update = native_source.index("nativeSupersedeToken = nativeToken;")
    stale_after_response = native_source.index(
        "if (loadIntent !== loadIntentGeneration) return;",
        token_update,
    )
    assert token_update < stale_after_response
    success_url = native_source.index("currentNativeUrl = nativeUrl;")
    preserved_swap = native_source.index("frame = replaceEditorFrame();", success_url)
    assert success_url < preserved_swap
    export_start = app_js.index("async function exportNative(format)")
    export_end = app_js.index("function exportDiagram(format)", export_start)
    export_source = app_js[export_start:export_end]
    canvas_export = export_source.index('if (format === "drawio")')
    stale_svg_guard = export_source.index("if (nativeCanvasRenderStale)")
    live_svg = export_source.index("serializeNativeFrameSvg()")
    assert canvas_export < stale_svg_guard < live_svg
    assert ".canvas bleibt verfügbar" in export_source
    assert "releaseLaunchTurn();" in native_source
    assert 'pendingInitialCollisionSafeLayout = load?.sourceMetadata?.value === "mermaid";' in launch_source
    assert "function toggleEditorFullscreen()" in app_js
    assert "const active = !editorFocusActive;" in app_js
    assert "setEditorFocus(active);" in app_js
    assert "requestFullscreen" not in app_js
    assert "exitFullscreen" not in app_js
    assert "fullscreenElement" not in app_js
    assert "fullscreenchange" not in app_js
    assert "nativeFullscreenActive" not in app_js
    assert "fullscreenTransitionActive" not in app_js
    assert "function showStart()" in app_js
    show_start = app_js.index("function showStart()")
    show_start_end = app_js.index("function showWorkspace()", show_start)
    show_start_source = app_js[show_start:show_start_end]
    assert "setEditorFocus(false);" in show_start_source
    assert "invalidateLoadIntents();" in show_start_source
    assert "pendingLoad = null;" in show_start_source
    assert "pendingExport = null;" in show_start_source
    assert "editorReady = false;" in show_start_source
    assert "replaceEditorFrame();" in show_start_source
    assert show_start_source.index("replaceEditorFrame();") < show_start_source.index("elements.workspace.hidden = true;")
    assert "elements.sourceInput.focus({ preventScroll: true });" in show_start_source
    assert "pendingInitialCollisionSafeLayout = false;" in show_start_source
    load_event_start = app_js.index('if (message.event === "load")')
    load_event_end = app_js.index('if (message.event === "autosave"', load_event_start)
    load_event_source = app_js[load_event_start:load_event_end]
    assert "const shouldAutoLayout = pendingInitialCollisionSafeLayout;" in load_event_source
    assert load_event_source.index("pendingInitialCollisionSafeLayout = false;") < load_event_source.index("requestCollisionSafeLayout();")
    assert 'layouts: [{ layout: "elkLayered", config: COLLISION_SAFE_LAYOUT_CONFIG }]' in app_js
    assert app_js.count("config: COLLISION_SAFE_LAYOUT_CONFIG") == 1
    assert '"elk.spacing.nodeNode": "40"' not in app_js
    assert 'event.key === "Escape"' not in app_js


def test_native_document_rebuild_preserves_active_frame_across_render_failure(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")
    native_start = app_js.index("function nativeTokenFromUrl")
    native_end = app_js.index("function loadPendingIntoEditor()", native_start)
    native_source = app_js[native_start:native_end]

    script = r"""
const PUBLIC_BASE_PATH = "";
const NATIVE_API_PATH = "/api/native-viewer";
let loadIntentGeneration = 0;
let nativeLaunchTail = Promise.resolve();
let nativeSupersedeToken = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
let nativeCanvasRenderStale = false;
let pendingExport = null;
let pendingLoad = null;
let pendingInitialCollisionSafeLayout = false;
let pendingCreationDefaults = false;
let currentXml = null;
let currentRepresentation = null;
let currentNativeDocument = {version: 1};
let currentNativeCanvas = {version: 1};
let currentLegacyXml = null;
let pendingLegacyFallback = null;
let currentNativeUrl = "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html";
let editorReady = true;
let statusText = "";
let errorText = "";
let replaceCalls = 0;
let workspaceCalls = 0;
const oldFrame = {
  inert: false,
  blurred: false,
  blur() { this.blurred = true; },
};
const replacementFrame = {
  inert: false,
  src: "",
  blur() {},
};
const elements = {
  frame: oldFrame,
  legacyFallbackButton: {hidden: true},
};
function invalidateLoadIntents() {
  loadIntentGeneration += 1;
  return loadIntentGeneration;
}
function clearPreparedDownload() {}
function setEngineMode() {}
function setStatus(value) { statusText = String(value); }
function setError(value) { errorText = String(value); }
function showWorkspace() { workspaceCalls += 1; }
function replaceEditorFrame() {
  replaceCalls += 1;
  replacementFrame.inert = false;
  elements.frame = replacementFrame;
  return replacementFrame;
}
function saveNativeDraft() { return true; }
function saveDraft() { return true; }
""" + native_source + r"""
const failedDocument = {version: 2};
const failedCanvas = {version: 2};
globalThis.fetch = async (_url, options) => {
  if (
    options.headers["X-Schauwerk-Native-Supersede"]
    !== "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  ) {
    throw new Error("missing supersede token on failed rebuild");
  }
  return {
    ok: false,
    async json() { return {error: "synthetic rebuild failure"}; },
  };
};
await launchNative(
  {nativeDocument: failedDocument, nativeCanvas: failedCanvas},
  {preserveActiveFrame: true},
);
if (replaceCalls !== 0) throw new Error("active frame replaced before successful render");
if (elements.frame !== oldFrame) throw new Error("active frame identity changed after render failure");
if (oldFrame.inert || !oldFrame.blurred) {
  throw new Error("preserved frame was not re-enabled after render failure");
}
if (currentNativeUrl !== "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html") {
  throw new Error("active native URL was lost after render failure");
}
if (!editorReady) throw new Error("canvas export readiness was lost after render failure");
if (!nativeCanvasRenderStale) throw new Error("stale SVG state was not recorded");
if (currentNativeCanvas.version !== 2 || currentNativeDocument.version !== 2) {
  throw new Error("latest document state was not retained after render failure");
}
if (!errorText.includes(".canvas-Export enthält den aktuellen Dokumentzustand")) {
  throw new Error("render failure did not preserve an export recovery path");
}
if (!errorText.includes("weiter bearbeitbar") || !statusText.includes("bleibt bearbeitbar")) {
  throw new Error("render failure did not restore editor interactivity");
}

const successfulDocument = {version: 3};
const successfulCanvas = {version: 3};
const successfulUrl = "/native/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/index.html";
globalThis.fetch = async (_url, options) => {
  if (
    options.headers["X-Schauwerk-Native-Supersede"]
    !== "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  ) {
    throw new Error("supersede token drifted before successful rebuild");
  }
  return {
    ok: true,
    async json() {
      return {
        url: successfulUrl,
        renderer: "schauwerk-native-diagram-v1",
        input_digest: "c".repeat(64),
      };
    },
  };
};
await launchNative(
  {nativeDocument: successfulDocument, nativeCanvas: successfulCanvas},
  {preserveActiveFrame: true},
);
if (replaceCalls !== 1 || workspaceCalls !== 1) {
  throw new Error("replacement frame was not swapped exactly once after success");
}
if (elements.frame !== replacementFrame || replacementFrame.src !== successfulUrl) {
  throw new Error("successful rebuild did not activate replacement frame");
}
if (nativeCanvasRenderStale) throw new Error("successful rebuild left SVG marked stale");
if (currentNativeUrl !== successfulUrl || !editorReady) {
  throw new Error("successful rebuild did not become authoritative");
}
if (currentNativeCanvas.version !== 3 || currentNativeDocument.version !== 3) {
  throw new Error("successful rebuild lost latest document state");
}
if (nativeSupersedeToken !== "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") {
  throw new Error("successful rebuild did not advance supersede token");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def _golden_representation(name: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "docs" / "operators" / "fixtures" / "golden" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_base_path_is_bound_into_manifest_and_client_urls(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(output, public_base_path="/schaubild")

    assert manifest["native_renderer"]["api_path"] == "/schaubild/api/native-viewer"
    assert manifest["native_renderer"]["public_base_path"] == "/schaubild"
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "PUBLIC_BASE_PATH") == "/schaubild"
    assert "PUBLIC_BASE_PATH}/api/native-viewer" in app_js
    assert "PUBLIC_BASE_PATH}/native/" in app_js


@pytest.mark.parametrize("value", ["/schaubild/", "schaubild", "/a//b", "/../x", "/a\\b", "/a?b"])
def test_public_base_path_rejects_ambiguous_or_noncanonical_values(value: str) -> None:
    with pytest.raises(StandaloneEditorError):
        _normalize_public_base_path(value)


def test_public_base_path_canonicalizes_root_to_empty_prefix() -> None:
    assert _normalize_public_base_path("") == ""
    assert _normalize_public_base_path("/") == ""
    assert _normalize_public_base_path("/schaubild") == "/schaubild"


def test_nonloopback_bind_requires_explicit_trusted_reverse_proxy() -> None:
    assert _normalize_bind_host("localhost", trusted_reverse_proxy=False) == "127.0.0.1"
    assert _normalize_bind_host("127.0.0.1", trusted_reverse_proxy=False) == "127.0.0.1"
    with pytest.raises(StandaloneEditorError, match="direct loopback bind"):
        _normalize_bind_host("127.0.0.2", trusted_reverse_proxy=False)
    assert _normalize_bind_host("127.0.0.2", trusted_reverse_proxy=True) == "127.0.0.2"
    with pytest.raises(StandaloneEditorError, match="IPv4"):
        _normalize_bind_host("::1", trusted_reverse_proxy=False)
    with pytest.raises(StandaloneEditorError, match="trusted-reverse-proxy"):
        _normalize_bind_host("0.0.0.0", trusted_reverse_proxy=False)
    assert _normalize_bind_host("0.0.0.0", trusted_reverse_proxy=True) == "0.0.0.0"


def test_trusted_proxy_source_cidrs_are_explicit_bounded_and_canonical() -> None:
    networks = standalone_editor._normalize_trusted_proxy_source_cidrs(
        ("127.0.0.0/8", "172.16.0.0/12")
    )
    assert [str(item) for item in networks] == ["127.0.0.0/8", "172.16.0.0/12"]
    with pytest.raises(StandaloneEditorError, match="canonical"):
        standalone_editor._normalize_trusted_proxy_source_cidrs(("172.17.0.1/12",))
    with pytest.raises(StandaloneEditorError, match="unique"):
        standalone_editor._normalize_trusted_proxy_source_cidrs(
            ("172.16.0.0/12", "172.16.0.0/12")
        )
    with pytest.raises(StandaloneEditorError, match="IPv4"):
        standalone_editor._normalize_trusted_proxy_source_cidrs(("::1/128",))


def test_trusted_reverse_proxy_requires_source_cidr_before_server_start(
    tmp_path: Path,
) -> None:
    with pytest.raises(StandaloneEditorError, match="trusted-proxy-source-cidr"):
        standalone_editor.serve_standalone_editor(
            port=0,
            build_dir=tmp_path / "editor",
            bind_host="0.0.0.0",
            trusted_reverse_proxy=True,
        )


def test_prefixed_runtime_requires_trusted_reverse_proxy_before_server_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server_started = False

    class UnexpectedServer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            nonlocal server_started
            server_started = True
            raise AssertionError("server must not start for incompatible prefix/bind contract")

    monkeypatch.setattr(standalone_editor, "_BoundedThreadingHTTPServer", UnexpectedServer)

    with pytest.raises(StandaloneEditorError, match="public base path requires"):
        standalone_editor.serve_standalone_editor(
            port=0,
            build_dir=tmp_path / "editor",
            public_base_path="/schaubild",
        )

    assert server_started is False


def test_prefixed_native_render_response_stays_bound_to_internal_endpoint(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output, public_base_path="/schaubild")

    handler_class = type(
        "PrefixedEditorRequestHandler",
        (_EditorRequestHandler,),
        {
            "editor_origin": EDITOR_ORIGIN,
            "public_base_path": "/schaubild",
            "native_serve_binding": "trusted-reverse-proxy-private-ingress",
            "trusted_proxy_networks": (ipaddress.ip_network("127.0.0.0/8"),),
        },
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                "X-Forwarded-For": "203.0.113.7",
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert re.fullmatch(r"/schaubild/native/[0-9a-f]{32}/index\.html", body["url"])

        internal_viewer_path = body["url"].removeprefix("/schaubild")
        connection.request(
            "GET",
            internal_viewer_path,
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        viewer_response = connection.getresponse()
        assert viewer_response.status == 200
        assert 'id="nativeViewport"' in viewer_response.read().decode("utf-8")

        internal_manifest_path = internal_viewer_path.replace("index.html", "manifest.json")
        connection.request(
            "GET",
            internal_manifest_path,
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        manifest_response = connection.getresponse()
        manifest = json.loads(manifest_response.read().decode("utf-8"))
        assert manifest_response.status == 200
        assert manifest["network_boundary"]["serve_binding"] == (
            "trusted-reverse-proxy-private-ingress"
        )
        assert manifest["network_boundary"]["public_base_path"] == "/schaubild"
        assert manifest["network_boundary"]["delivery"] == "integrated-schaubild-runtime"
        assert "production-readiness" not in manifest["does_not_establish"]
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

def test_native_product_admission_rejects_excessive_graph_cardinality() -> None:
    too_many_nodes = _golden_representation("decision-flow-v1.json")
    too_many_nodes["groups"] = []
    too_many_nodes["nodes"] = [
        {"id": f"n{index}", "label": f"Node {index}", "kind": "concept"}
        for index in range(standalone_editor.MAX_NATIVE_NODES + 1)
    ]
    too_many_nodes["edges"] = []
    with pytest.raises(StandaloneEditorError, match="complexity limits"):
        _native_product_input(too_many_nodes)

    too_many_edges = _golden_representation("decision-flow-v1.json")
    too_many_edges["groups"] = []
    too_many_edges["nodes"] = [
        {"id": "source", "label": "Source", "kind": "concept"},
        {"id": "target", "label": "Target", "kind": "concept"},
    ]
    too_many_edges["edges"] = [
        {
            "id": f"e{index}",
            "from": "source",
            "to": "target",
            "label": f"Edge {index}",
            "kind": "flow",
        }
        for index in range(standalone_editor.MAX_NATIVE_EDGES + 1)
    ]
    with pytest.raises(StandaloneEditorError, match="complexity limits"):
        _native_product_input(too_many_edges)


def test_native_product_admission_rejects_excessive_routing_pair_work() -> None:
    value = _golden_representation("decision-flow-v1.json")
    value["groups"] = []
    value["nodes"] = [
        {"id": "source", "label": "Source", "kind": "concept"},
        {"id": "target", "label": "Target", "kind": "concept"},
    ]
    edge_count = 182
    assert edge_count <= standalone_editor.MAX_NATIVE_EDGES
    assert edge_count * edge_count > standalone_editor.MAX_NATIVE_ROUTING_PAIRS
    value["edges"] = [
        {
            "id": f"e{index}",
            "from": "source",
            "to": "target",
            "label": f"Edge {index}",
            "kind": "flow",
        }
        for index in range(edge_count)
    ]
    with pytest.raises(StandaloneEditorError, match="complexity limits"):
        _native_product_input(value)


def test_native_product_admission_accepts_process_and_fails_closed_for_knowledge_map() -> None:
    process = _golden_representation("decision-flow-v1.json")
    accepted = _native_product_input(process)
    assert accepted["intent"] == "process"
    assert re.fullmatch(r"[0-9a-f]{64}", str(accepted["input_digest"]))

    knowledge_map = _golden_representation("system-landscape-v1.json")
    with pytest.raises(StandaloneEditorError, match="knowledge_map remains on the legacy"):
        _native_product_input(knowledge_map)


def test_native_product_admission_imports_bounded_drawio_request() -> None:
    source = """<mxGraphModel><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="ali" value="Fallbeispiel: Ali" vertex="1" parent="1"><mxGeometry/></mxCell>
    <mxCell id="resources" value="5. Ressourcen" vertex="1" parent="1"><mxGeometry/></mxCell>
    <mxCell id="edge" value="verfügt über" edge="1" parent="1" source="ali" target="resources"><mxGeometry relative="1" as="geometry"/></mxCell>
    </root></mxGraphModel>"""
    accepted = _native_product_input(
        {
            "schema_version": standalone_editor.NATIVE_IMPORT_SCHEMA,
            "format": "drawio-xml",
            "source": source,
            "title": "Fallbeispiel_Ali_Uebersicht.drawio",
        }
    )

    assert accepted["schema_version"] == "schauwerk-representation-input.v1"
    assert accepted["title"] == "Fallbeispiel_Ali_Uebersicht.drawio"
    assert accepted["intent"] == "process"
    assert [node["label"] for node in accepted["nodes"]] == [
        "Fallbeispiel: Ali",
        "5. Ressourcen",
    ]
    assert accepted["edges"][0]["label"] == "verfügt über"
    assert re.fullmatch(r"[0-9a-f]{64}", str(accepted["input_digest"]))


def test_native_product_admission_rejects_unsupported_drawio_without_guessing() -> None:
    source = """<mxfile>
    <diagram name="Seite-1"><mxGraphModel><root><mxCell id="0"/></root></mxGraphModel></diagram>
    <diagram name="Seite-2"><mxGraphModel><root><mxCell id="0"/></root></mxGraphModel></diagram>
    </mxfile>"""
    with pytest.raises(StandaloneEditorError, match="exactly one diagram page"):
        _native_product_input(
            {
                "schema_version": standalone_editor.NATIVE_IMPORT_SCHEMA,
                "format": "drawio-xml",
                "source": source,
            }
        )


def test_native_render_endpoint_accepts_drawio_import_request(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    source = """<mxGraphModel><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="a" value="Ali" vertex="1" parent="1"><mxGeometry/></mxCell>
    <mxCell id="b" value="Ressourcen" vertex="1" parent="1"><mxGeometry/></mxCell>
    <mxCell id="e" value="nutzen" edge="1" parent="1" source="a" target="b"><mxGeometry relative="1" as="geometry"/></mxCell>
    </root></mxGraphModel>"""
    payload = json.dumps(
        {
            "schema_version": standalone_editor.NATIVE_IMPORT_SCHEMA,
            "format": "drawio-xml",
            "source": source,
            "title": "Ali.drawio",
        }
    ).encode("utf-8")

    handler_class = type(
        "DrawioImportEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["renderer"] == NATIVE_RENDERER
        assert re.fullmatch(r"/native/[0-9a-f]{32}/index\.html", body["url"])

        connection.request("GET", body["url"])
        viewer_response = connection.getresponse()
        viewer_html = viewer_response.read().decode("utf-8")
        assert viewer_response.status == 200
        assert 'id="nativeViewport"' in viewer_html
        assert "Ali.drawio" in viewer_html
        assert "Ressourcen" in viewer_html
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_render_endpoint_rejects_non_loopback_host_before_rendering(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "HostGuardEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.putrequest("POST", NATIVE_API_PATH, skip_host=True)
        connection.putheader("Host", "attacker.example")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders(payload)
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 421
        assert body == {"error": "local Schaubild server accepts loopback Host headers only"}
        assert not (output / ".native-cache").exists()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_artifact_get_and_head_reject_non_loopback_host(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "ArtifactHostGuardEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        rendered = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        representation_path = rendered["url"].replace("index.html", "representation.json")

        connection.putrequest("GET", representation_path, skip_host=True)
        connection.putheader("Host", "attacker.example")
        connection.endheaders()
        get_response = connection.getresponse()
        get_body = json.loads(get_response.read().decode("ascii"))
        assert get_response.status == 421
        assert get_body == {"error": "local Schaubild server accepts loopback Host headers only"}

        connection.putrequest("HEAD", representation_path, skip_host=True)
        connection.putheader("Host", "attacker.example")
        connection.endheaders()
        head_response = connection.getresponse()
        assert head_response.status == 421
        assert int(head_response.getheader("Content-Length", "0")) > 0
        assert head_response.read() == b""
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_render_endpoint_returns_422_for_lone_unicode_surrogate(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "UnicodeGuardEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        representation = _golden_representation("decision-flow-v1.json")
        representation["nodes"][0]["label"] = "\ud800"
        payload = json.dumps(representation).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 422
        assert isinstance(body.get("error"), str)
        assert body["error"]
        assert not (output / ".native-cache").exists()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_render_endpoint_ascii_escapes_surrogate_in_validation_error(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "ErrorEncodingEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        representation = _golden_representation("decision-flow-v1.json")
        representation["\ud800"] = "unexpected"
        payload = json.dumps(representation).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        raw_body = response.read()
        raw_body.decode("ascii")
        body = json.loads(raw_body)
        assert response.status == 422
        assert "unknown fields" in body["error"]
        assert not (output / ".native-cache").exists()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_static_fallback_never_exposes_private_cache_via_encoded_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "PrivateCacheGuardEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        representation = _golden_representation("decision-flow-v1.json")
        payload = json.dumps(representation).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 200
        assert (output / ".native-cache").is_dir()

        for private_path in (
            "/.native-cache/",
            "/%2enative-cache/",
            "/%2Enative-cache/",
            "/%2e%6eative-cache/",
            "/%252enative-cache/",
            "/foo/..%252f.native-cache/",
            "/%252enative-cache/representation.json",
            "/../.native-cache/",
        ):
            connection.request("GET", private_path)
            private_response = connection.getresponse()
            private_body = private_response.read()
            assert private_response.status == 404
            assert b"bundle-" not in private_body
            assert b"representation.json" not in private_body
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_build_releases_cache_lock_during_renderer_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    lock_observations: list[bool] = []

    def observed_subprocess_build(**_kwargs: object) -> None:
        acquired = standalone_editor._NATIVE_CACHE_LOCK.acquire(blocking=False)
        lock_observations.append(acquired)
        if acquired:
            standalone_editor._NATIVE_CACHE_LOCK.release()

    monkeypatch.setattr(
        standalone_editor,
        "_run_native_viewer_build",
        observed_subprocess_build,
    )
    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=str(normalized["input_digest"]),
        value=value,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key=standalone_editor._LOCAL_ADMISSION_KEY,
        deadline_monotonic=time.monotonic() + 5,
    )

    assert created is True
    assert record.path.is_dir()
    assert lock_observations == [True]


def test_native_renderer_child_failure_logs_bounded_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "bundle"
    target.mkdir()
    noisy = "x" * 5000 + "TAIL_MARKER"

    class FailedProcess:
        def __init__(self) -> None:
            self.stderr = io.BytesIO(noisy.encode("utf-8"))

        def wait(self, timeout: float | None = None) -> int:
            return 1

        def kill(self) -> None:
            raise AssertionError("nonzero renderer exit must not require a kill")

    monkeypatch.setattr(
        standalone_editor.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FailedProcess(),
    )
    with pytest.raises(
        standalone_editor.NativeViewerError,
        match="subprocess build failed",
    ):
        standalone_editor._run_native_viewer_build(
            value=_golden_representation("decision-flow-v1.json"),
            target=target,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            timeout_seconds=5,
        )

    stderr = capsys.readouterr().err
    assert "native viewer subprocess failed:" in stderr
    assert "TAIL_MARKER" in stderr
    assert len(stderr) < 4300


def test_native_build_lock_wait_respects_absolute_request_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    renderer_called = False

    def unexpected_renderer(**_kwargs: object) -> None:
        nonlocal renderer_called
        renderer_called = True
        raise AssertionError("renderer must not start after request deadline expires")

    monkeypatch.setattr(standalone_editor, "_run_native_viewer_build", unexpected_renderer)
    assert standalone_editor._NATIVE_BUILD_LOCK.acquire(blocking=False)
    try:
        deadline = time.monotonic() + 0.05
        started = time.monotonic()
        with pytest.raises(
            standalone_editor.NativeRequestDeadlineError,
            match="deadline expired while waiting",
        ):
            standalone_editor._build_native_cache_record(
                output,
                digest=str(normalized["input_digest"]),
                value=value,
                serve_binding="127.0.0.1-only",
                public_base_path="",
                admission_key="127.0.0.1",
                deadline_monotonic=deadline,
            )
        assert time.monotonic() - started < 0.5
        assert renderer_called is False
    finally:
        standalone_editor._NATIVE_BUILD_LOCK.release()


def test_native_runtime_import_has_no_third_party_dependency_closure() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                "import sys; "
                "import schauwerk.visual.standalone_editor; "
                "blocked={'mcp','httpx','jsonschema','pydantic','platformdirs'}; "
                "loaded=sorted(blocked.intersection(sys.modules)); "
                "assert not loaded, loaded"
            ),
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr


def test_runtime_dockerfile_copies_only_native_runtime_closure() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")

    assert "pip install" not in dockerfile
    assert "COPY src ./src" not in dockerfile
    assert "RUN chmod -R a=rX /app/src" in dockerfile
    for required in (
        "src/schauwerk/visual/standalone_editor.py",
        "src/schauwerk/visual/drawio_import.py",
        "src/schauwerk/visual/native_viewer.py",
        "src/schauwerk/visual/native_diagram.py",
        "src/schauwerk/visual/native_document.py",
        "src/schauwerk/visual/representation.py",
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
    ):
        assert required in dockerfile
    for excluded in (
        "src/schauwerk/surfaces",
        "src/schauwerk/publication",
        "src/schauwerk/fundus",
    ):
        assert excluded not in dockerfile


def test_runtime_workflow_applies_declared_container_hardening_to_both_smokes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github/workflows/native-schaubild-image.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("--cap-drop ALL") == 2
    assert workflow.count("--security-opt no-new-privileges") == 2
    assert workflow.count("--read-only") == 2
    assert workflow.count("--tmpfs /tmp:rw,noexec,nosuid,size=64m") == 2


def test_runtime_publication_requires_exact_manual_dispatch_and_nonconsumer_candidate() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github/workflows/native-schaubild-image.yml").read_text(
        encoding="utf-8"
    )

    assert "expected_sha:" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert 'test "$EXPECTED_SHA" = "$GITHUB_SHA"' in workflow
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" not in workflow
    assert "ghcr.io/heimgewebe/schauwerk-schaubild-candidates" in workflow
    assert workflow.count("--trusted-proxy-source-cidr 172.16.0.0/12") == 2


def test_consumer_plan_requires_exact_trusted_proxy_source_cidr_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plan = (repo_root / "docs/plans/standalone-diagram-editor-spike-v1.md").read_text(
        encoding="utf-8"
    )

    assert (
        "--trusted-reverse-proxy --trusted-proxy-source-cidr <proxy-cidr> "
        "--public-base-path /schaubild"
    ) in plan
    assert "direkten** Consumer-Proxys" in plan
    assert "Docker-Catch-all ist kein Produktionsnachweis" in plan


def test_native_bundle_stream_releases_cache_lock_before_copy(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    lock_observations: list[bool] = []

    class LockProbeEditorRequestHandler(_EditorRequestHandler):
        editor_origin = EDITOR_ORIGIN

        def copyfile(self, source: object, outputfile: object) -> None:
            acquired = standalone_editor._NATIVE_CACHE_LOCK.acquire(blocking=False)
            lock_observations.append(acquired)
            if acquired:
                standalone_editor._NATIVE_CACHE_LOCK.release()
            super().copyfile(source, outputfile)

    handler = partial(LockProbeEditorRequestHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        value = _golden_representation("decision-flow-v1.json")
        payload = json.dumps(value).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200

        connection.request("GET", str(body["url"]))
        viewer = connection.getresponse()
        assert viewer.status == 200
        assert 'id="nativeViewport"' in viewer.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert lock_observations == [True]


def test_bounded_runtime_rejects_excess_workers_and_enforces_absolute_request_deadline(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "TimeoutBoundedEditorRequestHandler",
        (_EditorRequestHandler,),
        {
            "editor_origin": EDITOR_ORIGIN,
            "request_timeout_seconds": 0.2,
        },
    )
    server_class = type(
        "SingleWorkerEditorHTTPServer",
        (standalone_editor._BoundedThreadingHTTPServer,),
        {"max_workers": 1},
    )
    handler = partial(handler_class, directory=str(output))
    server = server_class(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    slow = socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=5)
    try:
        slow.sendall(
            b"POST /api/native-viewer HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 100\r\n"
            b"Connection: close\r\n\r\n"
            b"{"
        )

        excess = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        excess.request("GET", "/manifest.json")
        excess_response = excess.getresponse()
        excess_response.read()
        assert excess_response.status == 503
        excess.close()

        started = time.monotonic()
        for _ in range(8):
            time.sleep(0.04)
            try:
                slow.sendall(b" ")
            except OSError:
                break
        assert time.monotonic() - started < 0.6
        slow.settimeout(1)
        assert slow.recv(4096) == b""

        healthy = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        healthy.request("GET", "/manifest.json")
        healthy_response = healthy.getresponse()
        healthy_response.read()
        assert healthy_response.status == 200
        healthy.close()
    finally:
        slow.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_render_endpoint_preserves_active_grace_when_pin_reserve_is_full(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    clock = [100.0]
    monkeypatch.setattr(standalone_editor.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 2)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_GRACE_SECONDS", 60.0)
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_MAX_PIN_SECONDS", 120.0)

    handler_class = type(
        "PinAdmissionEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)

        def post(representation_id: str) -> tuple[int, dict[str, object]]:
            value = _golden_representation("decision-flow-v1.json")
            value["id"] = representation_id
            payload = json.dumps(value).encode("utf-8")
            connection.request(
                "POST",
                NATIVE_API_PATH,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body

        def record_for(url: str) -> standalone_editor._NativeCacheRecord:
            match = re.fullmatch(r"/native/([0-9a-f]{32})/index\.html", url)
            assert match is not None
            record = standalone_editor._native_cache_by_token(output, match.group(1))
            assert record is not None
            return record

        first_status, first_body = post("first_flow")
        assert first_status == 200
        first_url = str(first_body["url"])
        first_record = record_for(first_url)
        assert first_record.pinned_until == 160.0
        assert first_record.max_pinned_until == 220.0

        original_renderer_build = standalone_editor._run_native_viewer_build
        blocked_render_calls = 0

        def reject_unnecessary_render(**_kwargs: object) -> None:
            nonlocal blocked_render_calls
            blocked_render_calls += 1
            raise AssertionError("known pin saturation must reject before renderer work")

        monkeypatch.setattr(
            standalone_editor,
            "_run_native_viewer_build",
            reject_unnecessary_render,
        )
        clock[0] = 101.0
        second_status, second_body = post("second_flow")
        assert second_status == 503
        assert "pin capacity" in str(second_body["error"])
        assert first_record.pinned_until == 160.0
        assert blocked_render_calls == 0
        monkeypatch.setattr(
            standalone_editor,
            "_run_native_viewer_build",
            original_renderer_build,
        )

        clock[0] = 150.0
        connection.request("GET", first_url)
        first_viewer = connection.getresponse()
        assert first_viewer.status == 200
        assert 'id="nativeViewport"' in first_viewer.read().decode("utf-8")
        assert first_record.pinned_until == 210.0

        clock[0] = 161.0
        second_status, second_body = post("second_flow")
        assert second_status == 503
        assert "pin capacity" in str(second_body["error"])
        assert first_record.pinned_until == 210.0

        clock[0] = 211.0
        second_status, second_body = post("second_flow")
        assert second_status == 200
        second_url = str(second_body["url"])
        second_record = record_for(second_url)
        assert first_record.pinned_until == 210.0
        assert second_record.pinned_until == 271.0

        clock[0] = 212.0
        connection.request("GET", first_url)
        no_pin_response = connection.getresponse()
        no_pin_response.read()
        assert no_pin_response.status == 503
        assert first_record.pinned_until == 210.0
        assert second_record.pinned_until == 271.0

        clock[0] = 221.0
        connection.request("GET", first_url)
        expired_viewer = connection.getresponse()
        expired_viewer.read()
        assert expired_viewer.status == 410

        first_retry_status, first_retry_body = post("first_flow")
        assert first_retry_status == 503
        assert "pin capacity" in str(first_retry_body["error"])
        assert second_record.pinned_until == 271.0

        clock[0] = 272.0
        refreshed_status, refreshed_body = post("first_flow")
        assert refreshed_status == 200
        refreshed_url = str(refreshed_body["url"])
        assert refreshed_body["input_digest"] == first_body["input_digest"]
        assert refreshed_url != first_url

        connection.request("GET", refreshed_url)
        refreshed_viewer = connection.getresponse()
        assert refreshed_viewer.status == 200
        assert 'id="nativeViewport"' in refreshed_viewer.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    cache_root = output / ".native-cache"
    assert cache_root.is_dir()
    assert len(list(cache_root.iterdir())) <= 2


def test_loopback_runtime_is_not_subject_to_shared_client_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 1)

    handler_class = type(
        "LocalQuotaEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        for index in range(5):
            value = _golden_representation("decision-flow-v1.json")
            value["id"] = f"local_flow_{index}"
            payload = json.dumps(value).encode("utf-8")
            connection.request(
                "POST",
                NATIVE_API_PATH,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            response.read()
            assert response.status == 200
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_digest_client_key_sets_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CLIENT_KEYS_PER_DIGEST", 2)

    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    digest = str(normalized["input_digest"])
    first, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key="198.51.100.1",
    )
    assert created is True
    second, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key="198.51.100.2",
    )
    assert second is first
    assert created is False
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="digest client capacity",
    ):
        standalone_editor._build_native_cache_record(
            output,
            digest=digest,
            value=value,
            serve_binding="trusted-reverse-proxy-private-ingress",
            public_base_path="/schaubild",
            admission_key="198.51.100.3",
        )
    assert set(first.pin_leases) == {"198.51.100.1", "198.51.100.2"}

    root_key = standalone_editor._native_root_key(output)
    window = standalone_editor._NATIVE_PIN_WINDOWS[(root_key, digest)]
    assert window.admission_keys == {"198.51.100.1"}
    window.admission_keys.add("198.51.100.2")
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="digest client capacity",
    ):
        standalone_editor._native_pin_window(
            output,
            digest=digest,
            admission_key="198.51.100.3",
            now=time.monotonic(),
        )


def test_failed_rebuild_does_not_consume_digest_client_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CLIENT_KEYS_PER_DIGEST", 2)

    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    digest = str(normalized["input_digest"])
    client_a = "198.51.100.1"
    client_b = "198.51.100.2"
    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client_a,
    )
    assert created is True
    root_key = standalone_editor._native_root_key(output)
    window = standalone_editor._NATIVE_PIN_WINDOWS[(root_key, digest)]
    assert window.admission_keys == {client_a}

    standalone_editor._forget_native_cache_record(record, remove_files=True)
    original_build = standalone_editor.build_native_viewer

    def failed_build(*_args: object, **_kwargs: object) -> object:
        raise standalone_editor.NativeViewerError("synthetic renderer failure")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", failed_build)
    with pytest.raises(standalone_editor.NativeViewerError, match="synthetic renderer failure"):
        standalone_editor._build_native_cache_record(
            output,
            digest=digest,
            value=value,
            serve_binding="trusted-reverse-proxy-private-ingress",
            public_base_path="/schaubild",
            admission_key=client_b,
        )
    assert window.admission_keys == {client_a}

    monkeypatch.setattr(standalone_editor, "build_native_viewer", original_build)
    rebuilt, rebuilt_created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client_b,
    )
    assert rebuilt_created is True
    assert rebuilt.admission_key == client_b
    assert window.admission_keys == {client_a, client_b}


def test_trusted_proxy_rejects_unallowlisted_peer_and_cross_client_capability(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output, public_base_path="/schaubild")
    payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")

    blocked_handler = type(
        "BlockedProxyEditorRequestHandler",
        (_EditorRequestHandler,),
        {
            "editor_origin": EDITOR_ORIGIN,
            "public_base_path": "/schaubild",
            "native_serve_binding": "trusted-reverse-proxy-private-ingress",
            "trusted_proxy_networks": (ipaddress.ip_network("192.0.2.0/24"),),
        },
    )
    blocked_server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(blocked_handler, directory=str(output)),
    )
    blocked_thread = threading.Thread(target=blocked_server.serve_forever, daemon=True)
    blocked_thread.start()
    try:
        connection = HTTPConnection(
            "127.0.0.1", int(blocked_server.server_address[1]), timeout=5
        )
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                "X-Forwarded-For": "203.0.113.1",
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 400
        connection.close()
    finally:
        blocked_server.shutdown()
        blocked_server.server_close()
        blocked_thread.join(timeout=5)

    allowed_handler = type(
        "AllowedProxyEditorRequestHandler",
        (_EditorRequestHandler,),
        {
            "editor_origin": EDITOR_ORIGIN,
            "public_base_path": "/schaubild",
            "native_serve_binding": "trusted-reverse-proxy-private-ingress",
            "trusted_proxy_networks": (ipaddress.ip_network("127.0.0.0/8"),),
        },
    )
    allowed_server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(allowed_handler, directory=str(output)),
    )
    allowed_thread = threading.Thread(target=allowed_server.serve_forever, daemon=True)
    allowed_thread.start()
    try:
        connection = HTTPConnection(
            "127.0.0.1", int(allowed_server.server_address[1]), timeout=5
        )
        headers_a = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
            "X-Forwarded-For": "203.0.113.1",
        }
        connection.request("POST", NATIVE_API_PATH, body=payload, headers=headers_a)
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        viewer_path = str(body["url"]).removeprefix("/schaubild")

        connection.request("GET", viewer_path, headers={"X-Forwarded-For": "203.0.113.2"})
        foreign = connection.getresponse()
        foreign.read()
        assert foreign.status == 404

        headers_b = dict(headers_a)
        headers_b["X-Forwarded-For"] = "203.0.113.2"
        connection.request("POST", NATIVE_API_PATH, body=payload, headers=headers_b)
        cache_hit = connection.getresponse()
        cache_hit.read()
        assert cache_hit.status == 200

        connection.request("GET", viewer_path, headers={"X-Forwarded-For": "203.0.113.2"})
        authorized = connection.getresponse()
        authorized.read()
        assert authorized.status == 200
        connection.close()
    finally:
        allowed_server.shutdown()
        allowed_server.server_close()
        allowed_thread.join(timeout=5)




def test_trusted_proxy_native_supersede_allows_sequential_rebuilds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output, public_base_path="/schaubild")
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 1)

    handler_class = type(
        "SupersedeProxyEditorRequestHandler",
        (_EditorRequestHandler,),
        {
            "editor_origin": EDITOR_ORIGIN,
            "public_base_path": "/schaubild",
            "native_serve_binding": "trusted-reverse-proxy-private-ingress",
            "trusted_proxy_networks": (ipaddress.ip_network("127.0.0.0/8"),),
        },
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(handler_class, directory=str(output)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = "203.0.113.77"
    previous_token = ""
    try:
        connection = HTTPConnection(
            "127.0.0.1", int(server.server_address[1]), timeout=5
        )
        for index in range(6):
            value = _golden_representation("decision-flow-v1.json")
            value["id"] = f"supersede_flow_{index}"
            payload = json.dumps(value).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                "X-Forwarded-For": client,
            }
            if previous_token:
                headers[standalone_editor.NATIVE_SUPERSEDE_HEADER] = previous_token
            connection.request(
                "POST",
                NATIVE_API_PATH,
                body=payload,
                headers=headers,
            )
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            assert response.status == 200, body
            match = re.search(r"/native/([0-9a-f]{32})/index\.html$", str(body["url"]))
            assert match is not None
            token = match.group(1)
            if previous_token:
                previous = standalone_editor._native_cache_by_token(output, previous_token)
                if previous is not None:
                    assert previous.pin_leases.get(client, 0.0) <= time.monotonic()
            previous_token = token

            pinned = [
                record
                for record in standalone_editor._native_cache_records(output)
                if record.pin_leases.get(client, 0.0) > time.monotonic()
            ]
            assert len(pinned) == 1
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_supersede_cannot_release_foreign_client_and_old_bundle_can_repin(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    client_a = "198.51.100.10"
    client_b = "198.51.100.20"
    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=str(normalized["input_digest"]),
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client_a,
    )
    assert created is True

    assert (
        standalone_editor._release_native_superseded_lease(
            output,
            token=record.token,
            admission_key=client_b,
            next_digest="f" * 64,
        )
        is False
    )
    assert record.pin_leases[client_a] > time.monotonic()

    assert (
        standalone_editor._release_native_superseded_lease(
            output,
            token=record.token,
            admission_key=client_a,
            next_digest="f" * 64,
        )
        is True
    )
    assert record.pin_leases.get(client_a, 0.0) <= time.monotonic()

    standalone_editor._pin_native_cache_record(
        output,
        record,
        admission_key=client_a,
    )
    assert record.pin_leases[client_a] > time.monotonic()


def test_native_build_admission_limits_one_client_before_renderer_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 1)

    first = _golden_representation("decision-flow-v1.json")
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key="198.51.100.10",
    )
    assert first_created is True
    assert first_record.admission_key == "198.51.100.10"

    second = _golden_representation("decision-flow-v1.json")
    second["id"] = "other_flow"
    second_normalized = _native_product_input(second)
    renderer_called = False

    def unexpected_build(*_args: object, **_kwargs: object) -> object:
        nonlocal renderer_called
        renderer_called = True
        raise AssertionError("per-client saturation must reject before renderer work")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", unexpected_build)
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="per-client pin capacity",
    ):
        standalone_editor._build_native_cache_record(
            output,
            digest=str(second_normalized["input_digest"]),
            value=second,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            admission_key="198.51.100.10",
        )
    assert renderer_called is False


def test_cache_hit_pin_is_charged_to_current_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 1)

    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "client_a_flow"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key="198.51.100.10",
    )
    assert first_created is True
    standalone_editor._abandon_native_cache_record(
        output,
        first_record,
        admission_key="198.51.100.10",
    )
    assert first_record.pin_leases == {}

    second = _golden_representation("decision-flow-v1.json")
    second["id"] = "client_b_flow"
    second_normalized = _native_product_input(second)
    second_record, second_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(second_normalized["input_digest"]),
        value=second,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key="198.51.100.20",
    )
    assert second_created is True
    assert second_record.pin_leases["198.51.100.20"] > time.monotonic()

    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="pin capacity",
    ):
        standalone_editor._build_native_cache_record(
            output,
            digest=str(first_normalized["input_digest"]),
            value=first,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            admission_key="198.51.100.20",
        )

    assert "198.51.100.20" not in first_record.pin_leases
    assert first_record.admission_key == "198.51.100.10"


def test_undelivered_native_record_is_unpinned_but_reusable_without_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)

    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=str(normalized["input_digest"]),
        value=value,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key="127.0.0.1",
    )
    assert created is True
    assert record.pinned_until > time.monotonic()

    standalone_editor._abandon_native_cache_record(output, record)

    assert standalone_editor._native_cache_by_digest(
        output, str(normalized["input_digest"])
    ) is record
    assert standalone_editor._native_cache_by_token(output, record.token) is record
    assert record.pinned_until <= time.monotonic()

    def unexpected_rebuild(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("retry for an undelivered digest must reuse completed bytes")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", unexpected_rebuild)
    retried, retried_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(normalized["input_digest"]),
        value=value,
        serve_binding="127.0.0.1-only",
        public_base_path="",
        admission_key="127.0.0.1",
    )
    assert retried is record
    assert retried_created is False
    assert retried.pinned_until > time.monotonic()


def test_undelivered_unique_digests_still_consume_client_build_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 2)

    admission_key = "198.51.100.77"
    for index in range(2):
        value = _golden_representation("decision-flow-v1.json")
        value["id"] = f"abandoned_flow_{index}"
        normalized = _native_product_input(value)
        record, created = standalone_editor._build_native_cache_record(
            output,
            digest=str(normalized["input_digest"]),
            value=value,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            admission_key=admission_key,
        )
        assert created is True
        standalone_editor._abandon_native_cache_record(output, record)
        assert record.pinned_until <= time.monotonic()

    renderer_called = False

    def unexpected_build(*_args: object, **_kwargs: object) -> object:
        nonlocal renderer_called
        renderer_called = True
        raise AssertionError("client build budget must reject before renderer work")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", unexpected_build)
    third = _golden_representation("decision-flow-v1.json")
    third["id"] = "abandoned_flow_2"
    third_normalized = _native_product_input(third)
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="per-client build capacity",
    ):
        standalone_editor._build_native_cache_record(
            output,
            digest=str(third_normalized["input_digest"]),
            value=third,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            admission_key=admission_key,
        )
    assert renderer_called is False


def test_native_render_endpoint_allows_same_digest_after_absolute_lifetime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    clock = [100.0]
    monkeypatch.setattr(standalone_editor.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_GRACE_SECONDS", 60.0)
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_MAX_PIN_SECONDS", 120.0)

    handler_class = type(
        "ExpiredSameDigestEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Content-Length": str(len(payload))}

        connection.request("POST", NATIVE_API_PATH, body=payload, headers=headers)
        first_response = connection.getresponse()
        first_body = json.loads(first_response.read().decode("utf-8"))
        assert first_response.status == 200
        first_url = str(first_body["url"])

        clock[0] = 221.0
        connection.request("GET", first_url)
        expired_response = connection.getresponse()
        expired_response.read()
        assert expired_response.status == 410

        connection.request("POST", NATIVE_API_PATH, body=payload, headers=headers)
        refreshed_response = connection.getresponse()
        refreshed_body = json.loads(refreshed_response.read().decode("utf-8"))
        assert refreshed_response.status == 200
        refreshed_url = str(refreshed_body["url"])
        assert refreshed_body["input_digest"] == first_body["input_digest"]
        assert refreshed_url != first_url

        connection.request("GET", first_url)
        replaced_response = connection.getresponse()
        replaced_response.read()
        assert replaced_response.status == 404

        connection.request("GET", refreshed_url)
        refreshed_viewer = connection.getresponse()
        assert refreshed_viewer.status == 200
        assert 'id="nativeViewport"' in refreshed_viewer.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    cache_root = output / ".native-cache"
    assert cache_root.is_dir()
    assert len(list(cache_root.iterdir())) == 1


def test_native_render_endpoint_passes_canonical_public_input_to_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    source = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(source)
    expected = {key: item for key, item in normalized.items() if key != "input_digest"}
    captured: list[dict[str, object]] = []

    def capture_build(
        *,
        value: dict[str, object],
        target: Path,
        serve_binding: str,
        public_base_path: str,
        timeout_seconds: float,
    ) -> None:
        assert target.is_dir()
        assert serve_binding == "127.0.0.1-only"
        assert public_base_path == ""
        assert timeout_seconds > 0
        captured.append(value)

    monkeypatch.setattr(standalone_editor, "_run_native_viewer_build", capture_build)

    handler_class = type(
        "CanonicalInputEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(source).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 200
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert captured == [expected]
    assert "input_digest" not in captured[0]


def test_integrated_native_render_endpoint_builds_existing_renderer_bundle(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "TestConfiguredEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        payload = json.dumps(_golden_representation("decision-flow-v1.json")).encode("utf-8")
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["renderer"] == NATIVE_RENDERER
        assert re.fullmatch(r"/native/[0-9a-f]{32}/index\.html", body["url"])

        connection.request("GET", body["url"])
        viewer_response = connection.getresponse()
        viewer_html = viewer_response.read().decode("utf-8")
        assert viewer_response.status == 200
        assert "id=\"nativeViewport\"" in viewer_html

        diagram_url = body["url"].replace("index.html", "diagram.svg")
        connection.request("GET", diagram_url)
        diagram_response = connection.getresponse()
        diagram_svg = diagram_response.read().decode("utf-8")
        assert diagram_response.status == 200
        assert "<svg" in diagram_svg

        blocked = json.dumps(_golden_representation("system-landscape-v1.json")).encode("utf-8")
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=blocked,
            headers={"Content-Type": "application/json", "Content-Length": str(len(blocked))},
        )
        blocked_response = connection.getresponse()
        blocked_body = json.loads(blocked_response.read().decode("utf-8"))
        assert blocked_response.status == 422
        assert "knowledge_map remains on the legacy" in blocked_body["error"]
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("editor_origin", "expected_origin", "expected_public", "expected_https_zero"),
    [
        ("https://embed.diagrams.net:443", EDITOR_ORIGIN, True, False),
        ("http://127.0.0.1:80", "http://127.0.0.1", False, True),
        ("http://[::1]:80", "http://[::1]", False, True),
    ],
)
def test_build_canonicalizes_default_origin_ports(
    tmp_path: Path,
    editor_origin: str,
    expected_origin: str,
    expected_public: bool,
    expected_https_zero: bool,
) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(output, editor_origin=editor_origin)

    assert manifest["editor_origin"] == expected_origin
    assert manifest["network_boundary"]["public_embed_runtime"] is expected_public
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "EDITOR_ORIGIN") == expected_origin
    editor_url = _js_string_constant(app_js, "EDITOR_URL")
    assert editor_url == manifest["editor_url"]
    assert ("&https=0" in editor_url) is expected_https_zero
    if expected_public:
        assert "&offline=1" not in editor_url
    else:
        assert "&offline=1" in editor_url


@pytest.mark.parametrize(
    ("editor_origin", "expected_origin"),
    [
        ("http://[0:0:0:0:0:0:0:1]:8878", "http://[::1]:8878"),
        (
            "https://[2001:0db8:0:0:0:0:0:1]:8443",
            "https://[2001:db8::1]:8443",
        ),
    ],
)
def test_build_canonicalizes_ip_host_spelling(
    tmp_path: Path,
    editor_origin: str,
    expected_origin: str,
) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(output, editor_origin=editor_origin)

    assert manifest["editor_origin"] == expected_origin
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "EDITOR_ORIGIN") == expected_origin
    assert _js_string_constant(app_js, "EDITOR_URL") == manifest["editor_url"]


def test_build_supports_loopback_self_hosted_editor(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(
        output,
        editor_origin="http://127.0.0.1:8878/",
    )

    assert manifest["editor_origin"] == "http://127.0.0.1:8878"
    assert manifest["engine_delivery"] == "operator-configured-browser-iframe"
    assert manifest["network_boundary"] == {
        "shell": "local-static-files",
        "native_render_api": "same-origin-integrated-serve-only",
        "native_viewer_external_requests_required": False,
        "legacy_editor_runtime": "http://127.0.0.1:8878",
        "public_embed_runtime": False,
        "operator_configured_editor_runtime": True,
        "offline_mode_requested": True,
        "offline_complete": False,
    }
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "EDITOR_ORIGIN") == "http://127.0.0.1:8878"
    editor_url = _js_string_constant(app_js, "EDITOR_URL")
    assert editor_url == manifest["editor_url"]
    assert editor_url.startswith("http://127.0.0.1:8878/?embed=1&proto=json&configure=1")
    assert "&offline=1" in editor_url
    assert "&https=0" in editor_url
    policy = _content_security_policy(str(manifest["editor_origin"]))
    assert "frame-src 'self' http://127.0.0.1:8878;" in policy
    assert "connect-src 'self';" in policy


def test_build_canonicalizes_ascii_hostname_case(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(
        output,
        editor_origin="https://DRAWIO.SCHOOL.EXAMPLE:8443",
    )

    assert manifest["editor_origin"] == "https://drawio.school.example:8443"
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert _js_string_constant(app_js, "EDITOR_ORIGIN") == manifest["editor_origin"]


def test_build_allows_numeric_prefix_when_dns_label_is_unambiguous(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(
        output,
        editor_origin="https://1.2.3.example:8443",
    )

    assert manifest["editor_origin"] == "https://1.2.3.example:8443"


def test_build_supports_https_self_hosted_editor(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(
        output,
        editor_origin="https://drawio.school.example:8443",
    )

    assert manifest["editor_origin"] == "https://drawio.school.example:8443"
    assert manifest["engine_delivery"] == "operator-configured-browser-iframe"
    assert manifest["network_boundary"]["operator_configured_editor_runtime"] is True
    editor_url = str(manifest["editor_url"])
    assert "&offline=1" in editor_url
    assert "&https=0" not in editor_url


@pytest.mark.parametrize(
    "editor_origin",
    [
        "javascript:alert(1)",
        "http://drawio.example.org",
        "https://user@example.org",
        "https://example.org/path",
        "https://example.org?mode=1",
        "https://example.org/#fragment",
        " https://example.org",
        "https://exa mple.org",
        "https://example.org:99999",
        "https://127.1:8443",
        "https://127.000.000.001:8443",
        "https://0x7f000001:8443",
        "https://2130706433:8443",
        "https://0177.0000.0000.0001:8443",
        "https://[0:0:0:0:0:ffff:7f00:1]:8443",
        "https://straße.example:8443",
        "https://exämple.org:8443",
        "http://[::1%25eth0]:8878",
        "http://[127.0.0.1]:8878",
        "https://drawio.example.org.:8443",
        "https://[v1.fe80]:8443",
        "https://1.2.3.4.5:8443",
        "https://example.1:8443",
    ],
)
def test_build_rejects_unsafe_editor_origins_before_writing(
    tmp_path: Path,
    editor_origin: str,
) -> None:
    output = tmp_path / "editor"

    with pytest.raises(StandaloneEditorError):
        build_standalone_editor(output, editor_origin=editor_origin)

    assert not output.exists()


def test_build_rejects_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    output.mkdir()
    (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(StandaloneEditorError, match="must be empty"):
        build_standalone_editor(output)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_build_rejects_file_output_with_domain_error(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    output.write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(StandaloneEditorError, match="must be a directory"):
        build_standalone_editor(output)

    assert output.read_text(encoding="utf-8") == "do not overwrite"


def test_canvas_import_module_converts_basic_json_canvas_when_node_available(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI for standalone-editor JavaScript coverage")
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    module_source = (output / "canvas-import.js").read_bytes()
    module_url = "data:text/javascript;base64," + base64.b64encode(module_source).decode("ascii")

    code = f"""
import {{ COLLISION_SAFE_LAYOUT_CONFIG, MAX_CONFIGURABLE_FONT_SIZE, MAX_INPUT_BYTES, MIN_CONFIGURABLE_FONT_SIZE, READABLE_EDGE_FONT_SIZE, READABLE_NODE_FONT_SIZE, detectInput, exportDataUriToBlob, jsonCanvasToDrawioXml, readabilityZoomStepCount, validateExportDataUri, validateInputText }} from {module_url!r};
if (READABLE_NODE_FONT_SIZE !== 18 || READABLE_EDGE_FONT_SIZE !== 16) throw new Error('readability font profile drifted');
if (MIN_CONFIGURABLE_FONT_SIZE !== 8 || MAX_CONFIGURABLE_FONT_SIZE !== 72) throw new Error('configurable font bounds drifted');
if (COLLISION_SAFE_LAYOUT_CONFIG["elk.spacing.edgeNode"] !== "28") throw new Error('edge-node spacing drifted');
if (COLLISION_SAFE_LAYOUT_CONFIG["elk.layered.spacing.nodeNodeBetweenLayers"] !== "84") throw new Error('layer corridor drifted');
if (COLLISION_SAFE_LAYOUT_CONFIG["elk.layered.edgeLabels.centerLabelPlacementStrategy"] !== "SPACE_EFFICIENT_LAYER") throw new Error('edge-label placement drifted');
if (readabilityZoomStepCount(0.4) !== 3) throw new Error('40 percent fit should zoom three steps');
if (readabilityZoomStepCount(0.65) !== 0) throw new Error('readability floor should not zoom');
if (readabilityZoomStepCount('not-a-scale') !== 0) throw new Error('invalid scale should not zoom');
if (readabilityZoomStepCount(0.1) !== 8) throw new Error('extreme fit should respect zoom safety cap');
const source = JSON.stringify({{
  nodes: [
    {{id: 'group', type: 'group', x: -200, y: -100, width: 500, height: 300, label: 'Thema'}},
    {{id: 'a', type: 'text', x: -150, y: -40, width: 220, height: 100, text: '# Bindung', color: '4'}},
    {{id: 'b', type: 'text', x: 180, y: 120, width: 220, height: 100, text: 'Exploration'}}
  ],
  edges: [{{id: 'ab', fromNode: 'a', toNode: 'b', fromSide: 'right', toSide: 'left', toEnd: 'arrow', label: 'ermöglicht'}}]
}});
const detected = detectInput(source);
if (detected.kind !== 'json-canvas') throw new Error(`wrong kind: ${{detected.kind}}`);
const nativeRepresentation = JSON.stringify({{
  schema_version: 'schauwerk-representation-input.v1',
  title: 'Native',
  intent: 'process',
  nodes: [],
  edges: [],
  groups: []
}});
if (detectInput(nativeRepresentation).kind !== 'representation') throw new Error('native representation not detected');
const nodesOnly = JSON.stringify({{nodes: [{{id: 'solo', type: 'text', x: 0, y: 0, width: 200, height: 100, text: 'Solo'}}]}});
if (detectInput(nodesOnly).kind !== 'json-canvas') throw new Error('nodes-only JSON Canvas rejected');
if (!jsonCanvasToDrawioXml(nodesOnly).includes('jsonCanvasId="solo"')) throw new Error('nodes-only JSON Canvas did not convert');
const edgesOnly = JSON.stringify({{edges: []}});
if (detectInput(edgesOnly).kind !== 'json-canvas') throw new Error('edges-only JSON Canvas rejected');
if (!jsonCanvasToDrawioXml(edgesOnly).includes('<mxGraphModel')) throw new Error('edges-only JSON Canvas did not convert');
if (detectInput('{{}}').kind !== 'json-canvas') throw new Error('empty JSON Canvas rejected');
if (detectInput('{{"unrelated":true}}').kind !== 'unknown') throw new Error('arbitrary JSON misdetected as JSON Canvas');
if (detectInput(JSON.stringify({{nodes: [{{id: 'a'}}], links: [{{source: 'a', target: 'a'}}]}})).kind !== 'unknown') throw new Error('foreign nodes JSON misdetected as JSON Canvas');
if (detectInput(JSON.stringify({{nodes: [{{name: 'x'}}]}})).kind !== 'unknown') throw new Error('malformed nodes JSON misdetected as JSON Canvas');
for (const foreignNode of [
  {{id: 'a', type: 'server', x: 0, y: 0, width: 100, height: 50}},
  {{id: 'a', type: 'text', x: 0, y: 0, width: 100, height: 50}},
  {{id: 'a', type: 'file', x: 0, y: 0, width: 100, height: 50}},
  {{id: 'a', type: 'link', x: 0, y: 0, width: 100, height: 50}},
]) {{
  if (detectInput(JSON.stringify({{nodes: [foreignNode]}})).kind !== 'unknown') throw new Error('invalid typed Canvas node accepted');
}}
const fence = '`'.repeat(3);
for (const inlineCanvas of [
  fence + 'canvas\\n' + nodesOnly + '\\n' + fence,
  fence + '.canvas\\n' + nodesOnly + '\\n' + fence,
  'Hier ist das Schaubild:\\n\\n' + fence + 'json-canvas\\n' + nodesOnly + '\\n' + fence + '\\n\\nDu kannst es bearbeiten.',
  'Hinweis:\\n' + fence + 'json\\n{{"unrelated":true}}\\n' + fence + '\\nSchaubild:\\n' + fence + 'canvas\\n' + nodesOnly + '\\n' + fence,
  'Schaubild:\\r\\n' + fence + '.canvas\\r\\n' + nodesOnly + '\\r\\n' + fence,
]) {{
  if (detectInput(inlineCanvas).kind !== 'json-canvas') throw new Error(`inline JSON Canvas rejected: ${{inlineCanvas}}`);
}}
const ambiguousCanvas = fence + 'canvas\\n' + nodesOnly + '\\n' + fence + '\\n' + fence + 'mermaid\\nflowchart TD\\n A --> B\\n' + fence;
if (detectInput(ambiguousCanvas).kind !== 'unknown') throw new Error('ambiguous multi-diagram paste should remain unknown');
if (!jsonCanvasToDrawioXml(fence + 'canvas\\n' + nodesOnly + '\\n' + fence).includes('jsonCanvasId="solo"')) throw new Error('fenced string conversion path failed');
for (const mermaid of [
  '%% comment\\nflowchart TD\\n  A --> B',
  '%%{{init: {{"theme":"neutral"}}}}%%\\nsequenceDiagram\\n  A->>B: Hallo',
  '---\\ntitle: Beispiel\\n---\\n%% comment\\ngraph LR\\n  A --> B',
]) {{
  const detectedMermaid = detectInput(mermaid);
  if (detectedMermaid.kind !== 'mermaid') throw new Error(`commented Mermaid rejected: ${{detectedMermaid.kind}}`);
}}
for (const validDrawio of [
  '<mxfile><diagram/></mxfile>',
  '<mxfile />',
  '<mxGraphModel foo="bar"/>',
  '<?xml version="1.0"?>\\n<mxfile/>',
  '<?xml version="1.1" encoding="UTF-8" standalone="yes"?>\\n<mxGraphModel/>',
  "<?xml version='1.0' encoding='UTF-8' standalone='no'?>\\n<mxfile/>",
]) {{
  if (detectInput(validDrawio).kind !== 'drawio') throw new Error(`valid drawio rejected: ${{validDrawio}}`);
}}
for (const invalidDrawio of [
  '<mxfile-evil/>',
  '<mxfileSuffix/>',
  '<mxfile:foreign/>',
  '<mxGraphModel-evil/>',
  '<mxGraphModelSuffix/>',
  '<mxGraphModel:foreign/>',
  '<MXFILE/>',
  '<?xml-not-a-declaration?><mxfile/>',
  '<?xml version="1.0"><mxfile/>',
  '<?xml foo="bar"?><mxfile/>',
  '<?xml version="2.0"?><mxfile/>',
]) {{
  if (detectInput(invalidDrawio).kind === 'drawio') throw new Error(`drawio near-miss accepted: ${{invalidDrawio}}`);
}}
const xml = jsonCanvasToDrawioXml(detected.value);
if (!xml.includes('<mxGraphModel')) throw new Error('missing graph model');
if (!xml.includes('jsonCanvasId="a"')) throw new Error('missing source id');
if (!xml.includes('ermöglicht')) throw new Error('missing edge label');
if (!xml.includes('exitX=1')) throw new Error('missing source-side binding');
if (!xml.includes('entryX=0')) throw new Error('missing target-side binding');
if (!xml.includes('sourcePerimeterSpacing=12')) throw new Error('missing source perimeter clearance');
if (!xml.includes('targetPerimeterSpacing=12')) throw new Error('missing target perimeter clearance');
if (!xml.includes('spacing=6')) throw new Error('missing edge-label spacing');
if (!xml.includes('labelBackgroundColor=#ffffff')) throw new Error('missing edge-label background');
if (!xml.includes('fontSize=18')) throw new Error('missing readable node font size');
if (!xml.includes('fontSize=16')) throw new Error('missing readable edge font size');
const customFontXml = jsonCanvasToDrawioXml(detected.value, {{nodeFontSize: 24, edgeFontSize: 22}});
if (!customFontXml.includes('fontSize=24')) throw new Error('custom node font size missing');
if (!customFontXml.includes('fontSize=22')) throw new Error('custom edge font size missing');
const invalidFontXml = jsonCanvasToDrawioXml(detected.value, {{nodeFontSize: 7, edgeFontSize: 73}});
if (!invalidFontXml.includes('fontSize=18')) throw new Error('invalid node font size did not fall back');
if (!invalidFontXml.includes('fontSize=16')) throw new Error('invalid edge font size did not fall back');
const png = 'data:image/png;base64,AA==';
const svg = 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=';
if (validateExportDataUri(png, 'png') !== png) throw new Error('png export rejected');
if (validateExportDataUri(svg, 'svg') !== svg) throw new Error('svg export rejected');
const pngBlob = exportDataUriToBlob(png, 'png');
if (pngBlob.type !== 'image/png' || pngBlob.size !== 1) throw new Error('png blob preparation failed');
const svgBlob = exportDataUriToBlob(svg, 'svg');
if (svgBlob.type !== 'image/svg+xml') throw new Error('svg blob type is wrong');
if (await svgBlob.text() !== '<svg></svg>') throw new Error('svg blob payload is wrong');
if (validateInputText('abc') !== 'abc') throw new Error('small input rejected');
if (new TextEncoder().encode(validateInputText('ä')).byteLength !== 2) throw new Error('UTF-8 input sizing drifted');
for (const invalid of [
  () => validateExportDataUri('javascript:alert(1)', 'svg'),
  () => validateExportDataUri('data:image/svg+xml;base64,%%%=', 'svg'),
  () => validateExportDataUri(png, 'svg'),
  () => validateInputText('x'.repeat(MAX_INPUT_BYTES + 1)),
  () => validateInputText('ä'.repeat(Math.floor(MAX_INPUT_BYTES / 2) + 1)),
  () => jsonCanvasToDrawioXml({{
    nodes: [
      {{id: 'a', type: 'text', x: 0, y: 0, width: 100, height: 50, text: 'A'}},
      {{id: 'a', type: 'text', x: 120, y: 0, width: 100, height: 50, text: 'B'}},
    ],
    edges: [],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [
      {{id: 'a', type: 'text', x: 0, y: 0, width: 100, height: 50, text: 'A'}},
      {{id: 'b', type: 'text', x: 120, y: 0, width: 100, height: 50, text: 'B'}},
    ],
    edges: [
      {{id: 'same', fromNode: 'a', toNode: 'b'}},
      {{id: 'same', fromNode: 'b', toNode: 'a'}},
    ],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [
      {{id: 'a', type: 'text', x: 0, y: 0, width: 100, height: 50, text: 'A'}},
      {{id: 'b', type: 'text', x: 120, y: 0, width: 100, height: 50, text: 'B'}},
    ],
    edges: [
      {{id: 'edge_2', fromNode: 'a', toNode: 'b'}},
      {{id: 'edge_2', fromNode: 'b', toNode: 'a'}},
    ],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [{{id: 'a', type: 'text', x: 0, y: 0, width: 100, height: 50, text: 'A'}}],
    edges: [{{id: 'dangling', fromNode: 'a', toNode: 'missing'}}],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [
      {{id: 'a', type: 'text', x: -Number.MAX_VALUE, y: 0, width: 100, height: 50, text: 'A'}},
      {{id: 'b', type: 'text', x: Number.MAX_VALUE, y: 0, width: 100, height: 50, text: 'B'}},
    ],
    edges: [],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [{{id: 'x-overflow', type: 'text', x: Number.MAX_VALUE, y: 0, width: Number.MAX_VALUE, height: 50, text: 'X'}}],
  }}),
  () => jsonCanvasToDrawioXml({{
    nodes: [{{id: 'y-overflow', type: 'text', x: 0, y: Number.MAX_VALUE, width: 100, height: Number.MAX_VALUE, text: 'Y'}}],
  }}),
]) {{
  let rejected = false;
  try {{ invalid(); }} catch (_) {{ rejected = true; }}
  if (!rejected) throw new Error('invalid standalone-editor payload accepted');
}}
const hostileXml = jsonCanvasToDrawioXml({{
  nodes: [{{
    id: 'a"><mxCell id="0"/>',
    type: 'text',
    x: 0,
    y: 0,
    width: 100,
    height: 50,
    text: 'A' + String.fromCharCode(7, 9, 13, 10, 0xd800, 0xdfff, 0xfffe, 0xffff) + '<&😀',
  }}],
}});
const highSurrogate = String.fromCharCode(0xd800);
const lowSurrogate = String.fromCharCode(0xdfff);
const replacementCharacter = '\uFFFD';
const identityXml = jsonCanvasToDrawioXml({{
  nodes: [
    {{id: highSurrogate, type: 'text', x: 0, y: 0, width: 100, height: 50, text: 'High'}},
    {{id: lowSurrogate, type: 'text', x: 120, y: 0, width: 100, height: 50, text: 'Low'}},
    {{id: replacementCharacter, type: 'text', x: 240, y: 0, width: 100, height: 50, text: 'Replacement'}},
    {{id: '😀', type: 'text', x: 360, y: 0, width: 100, height: 50, text: 'Emoji'}},
  ],
  edges: [
    {{id: highSurrogate, fromNode: highSurrogate, toNode: lowSurrogate}},
    {{id: lowSurrogate, fromNode: lowSurrogate, toNode: replacementCharacter}},
    {{id: replacementCharacter, fromNode: replacementCharacter, toNode: '😀'}},
  ],
}});
console.log(JSON.stringify({{status: 'ok', hostileXml, identityXml}}));
"""
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "ok"
    assert "\x07" not in result["hostileXml"]
    assert chr(0xFFFE) not in result["hostileXml"]
    assert chr(0xFFFF) not in result["hostileXml"]
    assert not any(0xD800 <= ord(character) <= 0xDFFF for character in result["hostileXml"])
    assert "😀" in result["hostileXml"]
    assert "�" in result["hostileXml"]
    ET.fromstring(result["hostileXml"])

    identity_root = ET.fromstring(result["identityXml"])
    node_ids = [element.attrib["id"] for element in identity_root.findall(".//object")]
    edge_ids = [
        element.attrib["id"]
        for element in identity_root.findall(".//mxCell")
        if element.attrib.get("edge") == "1"
    ]
    assert len(node_ids) == 4
    assert len(node_ids) == len(set(node_ids))
    assert len(edge_ids) == 3
    assert len(edge_ids) == len(set(edge_ids))
    assert {"jc_d800", "jc_dfff", "jc_fffd", "jc_d83dde00"} <= set(node_ids)
    assert {"jce_d800", "jce_dfff", "jce_fffd"} <= set(edge_ids)



def test_canvas_import_browser_xml_validation_when_chrome_available(tmp_path: Path) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if chrome is None:
        pytest.skip("Chrome/Chromium is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    harness = output / "xml-validation-test.html"
    harness.write_text(
        """<!doctype html><meta charset=\"utf-8\"><pre id=\"result\">pending</pre><script type=\"module\">
import { validateDiagramXml } from './canvas-import.js';
const valid = [
  '<mxfile><diagram/></mxfile>',
  '<mxGraphModel><root/></mxGraphModel>',
  '<?xml version=\"1.0\"?><mxfile/>',
];
const invalid = [
  '<mxfile><diagram></mxfile>',
  '<mxGraphModel/><mxfile/>',
  '<mxfile/>trailing',
  '<!DOCTYPE mxfile><mxfile/>',
];
let ok = true;
for (const value of valid) {
  try { validateDiagramXml(value); } catch (_) { ok = false; }
}
for (const value of invalid) {
  let rejected = false;
  try { validateDiagramXml(value); } catch (_) { rejected = true; }
  if (!rejected) ok = false;
}
document.querySelector('#result').textContent = ok ? 'PASS' : 'FAIL';
</script>""",
        encoding="utf-8",
    )
    chrome_env = dict(os.environ)
    local_profile_args: list[str] = []
    if not os.environ.get("CI"):
        chrome_env.update(
            {
                "HOME": str(tmp_path / "home"),
                "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
                "XDG_CACHE_HOME": str(tmp_path / "xdg-cache"),
            }
        )
        local_profile_args = [f"--user-data-dir={tmp_path / 'chrome-profile'}"]
    chrome_base = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ]
    if not os.environ.get("CI"):
        try:
            preflight = subprocess.run(
                [
                    *chrome_base,
                    *local_profile_args,
                    "--dump-dom",
                    "about:blank",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=chrome_env,
            )
        except subprocess.TimeoutExpired:
            pytest.skip("Chrome is installed but headless execution is unavailable")
        if preflight.returncode != 0:
            pytest.skip("Chrome is installed but headless execution is unavailable")

    completed = subprocess.run(
        [
            *chrome_base,
            *local_profile_args,
            "--allow-file-access-from-files",
            "--virtual-time-budget=3000",
            "--dump-dom",
            harness.as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env=chrome_env,
    )
    assert completed.returncode == 0, completed.stderr
    assert '<pre id="result">PASS</pre>' in completed.stdout
