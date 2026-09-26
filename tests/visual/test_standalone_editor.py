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
from http import HTTPStatus
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
    assert 'if (stripInputDigest) clone.removeAttribute("data-input-digest")' in app_js
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
    assert r"allowExtensionOnlyCanvas: /\.canvas$/i.test(String(title))" in app_js
    assert "legacyXml: xml" in app_js
    assert "function launchLegacy(load)" in app_js
    assert 'elements.legacyEditButton.addEventListener("click"' in app_js
    assert 'elements.legacyFallbackButton.addEventListener("click"' in app_js
    assert 'id="legacyEditButton"' in index_html
    assert 'id="legacyFallbackButton"' in index_html
    assert 'id="nativeRetryButton"' in index_html
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
    assert "Bestehende Ansicht bleibt sichtbar und gesperrt" in native_source
    assert "async function retryNativeCanvasRender()" in native_source
    assert "elements.nativeRetryButton.hidden = false;" in native_source
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
    snapshot_bind = native_source.index(
        "renderedNativeCanvasSnapshot = nativeCanvasSnapshot(currentNativeCanvas);",
        success_url,
    )
    preserved_swap = native_source.index("frame = replaceEditorFrame();", success_url)
    assert success_url < snapshot_bind < preserved_swap
    export_start = app_js.index("async function exportNative(format)")
    export_end = app_js.index("function exportDiagram(format)", export_start)
    export_source = app_js[export_start:export_end]
    canvas_export = export_source.index('if (format === "drawio")')
    stale_svg_guard = export_source.index("if (currentNativeCanvas && nativeCanvasRenderStale)")
    live_svg = export_source.index("serializeNativeFrameSvg({")
    digest_sync = export_source.index(
        "stripInputDigest: nativeCanvasDiffersFromRendered(currentNativeCanvas)",
        live_svg,
    )
    asset_fallback = export_source.index("const assetUrl =", live_svg)
    assert canvas_export < stale_svg_guard < live_svg < digest_sync < asset_fallback
    assert ".canvas bleibt verfügbar" in export_source
    assert "SVG aus aktueller nativer Darstellung bereit" in export_source
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



def test_native_svg_serializer_preserves_synchronized_digest_and_strips_stale_canvas_digest(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")
    serialize_start = app_js.index("function nativeCanvasSnapshot(")
    serialize_end = app_js.index("async function exportNative(format)", serialize_start)
    serialize_source = app_js[serialize_start:serialize_end]

    script = r"""
const makeSvg = () => ({
  namespaceURI: "http://www.w3.org/2000/svg",
  localName: "svg",
  attrs: new Map([["data-input-digest", "a".repeat(64)]]),
  cloneNode() {
    return {
      attrs: new Map(this.attrs),
      setAttribute(name, value) { this.attrs.set(name, String(value)); },
      removeAttribute(name) { this.attrs.delete(name); },
    };
  },
});
let sourceSvg = makeSvg();
let renderedNativeCanvasSnapshot = null;
const elements = {
  frame: {
    contentDocument: {
      querySelector(selector) {
        return selector === "#nativeDiagram" ? sourceSvg : null;
      },
    },
  },
};
globalThis.XMLSerializer = class {
  serializeToString(node) {
    const digest = node.attrs.get("data-input-digest");
    const digestAttr = digest ? ' data-input-digest="' + digest + '"' : "";
    return "<svg" + digestAttr + "></svg>";
  }
};
""" + serialize_source + r"""
renderedNativeCanvasSnapshot = nativeCanvasSnapshot({
  edges: [],
  nodes: [{id: "a", type: "text"}],
});
if (nativeCanvasDiffersFromRendered({
  nodes: [{type: "text", id: "a"}],
  edges: [],
})) {
  throw new Error("key-reordered unchanged Canvas was marked digest-stale");
}
if (!nativeCanvasDiffersFromRendered({
  nodes: [{type: "text", id: "b"}],
  edges: [],
})) {
  throw new Error("changed Canvas was not marked digest-stale");
}
if (nativeCanvasDiffersFromRendered(null)) {
  throw new Error("non-Canvas export was marked digest-stale");
}
const synchronized = serializeNativeFrameSvg();
if (!synchronized?.includes('data-input-digest="' + "a".repeat(64) + '"')) {
  throw new Error("synchronized native SVG lost its source digest");
}
const staleCanvas = serializeNativeFrameSvg({stripInputDigest: true});
if (staleCanvas?.includes("data-input-digest=")) {
  throw new Error("stale live Canvas SVG retained an obsolete source digest");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def test_native_svg_export_prefers_loaded_frame_and_keeps_server_fallback(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")
    export_start = app_js.index("async function exportNative(format)")
    export_end = app_js.index("function exportDiagram(format)", export_start)
    export_source = app_js[export_start:export_end]

    script = r"""
let editorReady = true;
let currentRepresentation = {schema_version: "schauwerk-representation-input.v1"};
let currentNativeDocument = null;
let currentNativeCanvas = null;
let currentLegacyXml = null;
let currentNativeUrl = "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html";
let nativeCanvasRenderStale = false;
let currentTitle = "Representation";
let liveSvgValue = '<svg xmlns="http://www.w3.org/2000/svg" id="live"></svg>';
let statusText = "";
let prepared = null;
let fetchCalls = 0;
let stripInputDigestSeen = null;
function clearPreparedDownload() {}
function setStatus(value) { statusText = String(value); }
function safeFilename() { return "representation"; }
function nativeCanvasDiffersFromRendered(canvas) { return Boolean(canvas?.dirty); }
function serializeNativeFrameSvg(options = {}) {
  stripInputDigestSeen = Boolean(options.stripInputDigest);
  return liveSvgValue;
}
function prepareDownload(blob, filename, label) {
  prepared = {blob, filename, label};
}
globalThis.fetch = async () => {
  fetchCalls += 1;
  throw new Error("live-frame export must not refetch the native bundle");
};
""" + export_source + r"""
await exportNative("svg");
if (fetchCalls !== 0) throw new Error("live native SVG export refetched the bundle");
if (!prepared || prepared.filename !== "representation.svg" || prepared.label !== "SVG") {
  throw new Error("live native SVG export was not prepared");
}
if (!(await prepared.blob.text()).includes('id="live"')) {
  throw new Error("live native SVG bytes were not exported");
}
if (!statusText.includes("aktueller nativer Darstellung")) {
  throw new Error("live native SVG export status missing");
}
if (stripInputDigestSeen) {
  throw new Error("synchronized Representation export requested digest stripping");
}

prepared = null;
statusText = "";
currentRepresentation = null;
currentNativeCanvas = {dirty: true};
liveSvgValue = '<svg xmlns="http://www.w3.org/2000/svg" id="dirty"></svg>';
await exportNative("svg");
if (!stripInputDigestSeen) {
  throw new Error("live-modified Canvas export did not request digest stripping");
}
if (!(await prepared.blob.text()).includes('id="dirty"')) {
  throw new Error("live-modified Canvas SVG bytes were not exported");
}

prepared = null;
statusText = "";
currentNativeCanvas = null;
currentRepresentation = {schema_version: "schauwerk-representation-input.v1"};
liveSvgValue = null;
globalThis.fetch = async (url, options) => {
  fetchCalls += 1;
  if (url !== "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/diagram.svg") {
    throw new Error("unexpected fallback URL: " + url);
  }
  if (options?.cache !== "no-store") {
    throw new Error("fallback fetch lost no-store policy");
  }
  return {
    ok: true,
    async text() {
      return '<svg xmlns="http://www.w3.org/2000/svg" id="fallback"></svg>';
    },
  };
};
await exportNative("svg");
if (fetchCalls !== 1) throw new Error("unreadable frame did not use server fallback exactly once");
if (!prepared || !(await prepared.blob.text()).includes('id="fallback"')) {
  throw new Error("server SVG fallback was not prepared");
}
if (statusText !== "SVG bereit") throw new Error("server SVG fallback status drifted");
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def test_native_canvas_document_change_persists_restoreable_native_draft(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")
    draft_start = app_js.index("function saveDraft(")
    draft_end = app_js.index("function clearPreparedDownload()", draft_start)
    draft_source = app_js[draft_start:draft_end]

    assert "const draftSaved = saveNativeCanvasDraft(message.document, message.canvas);" in app_js
    assert '"Native Änderung aktiv · lokales Speichern nicht möglich"' in app_js
    assert "if (draft.nativeDocument && draft.nativeCanvas)" in app_js
    assert "nativeDocument: draft.nativeDocument" in app_js
    assert "nativeCanvas: draft.nativeCanvas" in app_js
    assert 'value: "json-canvas-1.0"' in app_js

    script = r"""
const DRAFT_KEY = "legacy";
const NATIVE_DRAFT_KEY = "native";
let currentXml = null;
let currentRepresentation = null;
let currentTitle = "Native Canvas";
let statusText = "";
const elements = {restoreButton: {hidden: true}};
function setStatus(value) { statusText = String(value); }
const store = new Map();
globalThis.localStorage = {
  setItem(key, value) { store.set(String(key), String(value)); },
  getItem(key) { return store.has(String(key)) ? store.get(String(key)) : null; },
};
let now = 1000;
Date.now = () => now;
""" + draft_source + r"""
if (!saveDraft("<mxGraphModel/>")) throw new Error("legacy draft setup failed");
now = 1001;
const nativeDocument = {
  schema_version: "schauwerk-native-editing-document.v1",
  source_digest: "a".repeat(64),
  documentExtension: {keep: true},
};
const nativeCanvas = {
  nodes: [{id: "n", type: "text", x: 17, y: 23, width: 100, height: 50, text: "edited"}],
  edges: [],
  canvasExtension: {keep: true},
};
if (!saveNativeCanvasDraft(nativeDocument, nativeCanvas)) {
  throw new Error("native canvas draft was not persisted");
}
const stored = JSON.parse(store.get(NATIVE_DRAFT_KEY));
if (stored.nativeDocument.documentExtension.keep !== true) {
  throw new Error("native document extension was lost from persisted draft");
}
if (stored.nativeCanvas.canvasExtension.keep !== true || stored.nativeCanvas.nodes[0].x !== 17) {
  throw new Error("edited JSON Canvas state was lost from persisted draft");
}
const latest = readLatestDraft();
if (!latest || latest.kind !== "native") {
  throw new Error("newer native canvas draft did not outrank legacy fallback draft");
}
if (latest.nativeDocument !== undefined && latest.nativeDocument.documentExtension.keep !== true) {
  throw new Error("native document identity was not restored from the draft");
}
if (latest.nativeCanvas.nodes[0].text !== "edited") {
  throw new Error("native canvas draft did not round-trip through readLatestDraft");
}
now = 1002;
store.set(
  NATIVE_DRAFT_KEY,
  JSON.stringify({
    title: "Representation",
    representation: {schema_version: "schauwerk-representation-input.v1"},
    savedAt: now,
  }),
);
const representationDraft = readNativeDraft();
if (!representationDraft?.representation) {
  throw new Error("existing representation draft compatibility regressed");
}
globalThis.localStorage.setItem = () => { throw new Error("quota"); };
if (saveNativeCanvasDraft(nativeDocument, nativeCanvas)) {
  throw new Error("native canvas draft save did not fail closed on storage error");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )



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
let renderedNativeCanvasSnapshot = null;
function nativeCanvasSnapshot(canvas) {
  return canvas ? JSON.stringify(canvas) : null;
}
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
let nativeCanvasDraftSaveSucceeds = false;
const nativeCanvasDraftSaves = [];
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
  nativeRetryButton: {hidden: true},
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
function saveNativeCanvasDraft(documentValue, canvasValue) {
  nativeCanvasDraftSaves.push({
    documentVersion: documentValue?.version,
    canvasVersion: canvasValue?.version,
  });
  return nativeCanvasDraftSaveSucceeds;
}
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
if (!oldFrame.inert || !oldFrame.blurred) throw new Error("stale frame remained interactive");
if (currentNativeUrl !== "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html") {
  throw new Error("active native URL was lost after render failure");
}
if (!editorReady) throw new Error("canvas export readiness was lost after render failure");
if (!nativeCanvasRenderStale) throw new Error("stale SVG state was not recorded");
if (currentNativeCanvas.version !== 2 || currentNativeDocument.version !== 2) {
  throw new Error("latest document state was not retained after render failure");
}
if (
  nativeCanvasDraftSaves.length !== 1
  || nativeCanvasDraftSaves[0].documentVersion !== 2
  || nativeCanvasDraftSaves[0].canvasVersion !== 2
) {
  throw new Error("transient rebuild candidate was not persisted as a native canvas draft");
}
if (!errorText.includes("konnte nicht lokal als Entwurf gespeichert werden")) {
  throw new Error("transient draft storage failure was not reported truthfully");
}
if (!statusText.includes("Entwurf lokal nicht speicherbar")) {
  throw new Error("transient draft storage failure was missing from status");
}
if (!errorText.includes(".canvas-Export enthält den aktuellen Dokumentzustand")) {
  throw new Error("render failure did not preserve an export recovery path");
}
if (!errorText.includes("Neu rendern") || !statusText.includes("Neu rendern")) {
  throw new Error("render failure did not offer an explicit retry path");
}
if (elements.nativeRetryButton.hidden) {
  throw new Error("render retry control stayed hidden after failure");
}

nativeCanvasDraftSaveSucceeds = true;
const successfulUrl = "/native/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/index.html";
globalThis.fetch = async (_url, options) => {
  if (
    options.headers["X-Schauwerk-Native-Supersede"]
    !== "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  ) {
    throw new Error("supersede token drifted before successful retry");
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
await retryNativeCanvasRender();
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
if (currentNativeCanvas.version !== 2 || currentNativeDocument.version !== 2) {
  throw new Error("successful retry did not render the latest retained document state");
}
if (!elements.nativeRetryButton.hidden) {
  throw new Error("successful retry did not hide the retry control");
}
if (nativeSupersedeToken !== "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") {
  throw new Error("successful rebuild did not advance supersede token");
}
if (nativeCanvasDraftSaves.length !== 2) {
  throw new Error("successful retry did not persist the retained candidate exactly once more");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )



def test_json_canvas_native_rejection_exposes_legacy_fallback(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert "jsonCanvasToDrawioXml" in app_js.splitlines()[0]
    assert "fallbackXml = jsonCanvasToDrawioXml(currentNativeCanvas" in app_js

    native_start = app_js.index("function nativeTokenFromUrl")
    native_end = app_js.index("function loadPendingIntoEditor()", native_start)
    native_source = app_js[native_start:native_end]

    script = r"""
const PUBLIC_BASE_PATH = "";
const NATIVE_API_PATH = "/api/native-viewer";
let loadIntentGeneration = 0;
let nativeLaunchTail = Promise.resolve();
let nativeSupersedeToken = "";
let nativeCanvasRenderStale = false;
let renderedNativeCanvasSnapshot = null;
function nativeCanvasSnapshot(canvas) {
  return canvas ? JSON.stringify(canvas) : null;
}
let pendingExport = null;
let pendingLoad = null;
let pendingInitialCollisionSafeLayout = false;
let pendingCreationDefaults = false;
let currentXml = null;
let currentRepresentation = null;
let currentNativeDocument = null;
let currentNativeCanvas = null;
let currentLegacyXml = null;
let pendingLegacyFallback = null;
let currentNativeUrl = null;
let editorReady = false;
let statusText = "";
let errorText = "";
const legacyXml = "<mxGraphModel><root/></mxGraphModel>";
let legacyConverterCalls = 0;
const preferredNodeFontSize = 24;
function edgeFontSizeFor() { return 22; }
function jsonCanvasToDrawioXml() {
  legacyConverterCalls += 1;
  return legacyXml;
}
const replacementFrame = {inert: false, src: "", blur() {}};
const elements = {
  frame: replacementFrame,
  workspace: {hidden: true},
  startView: {hidden: false},
  legacyFallbackButton: {hidden: true},
  nativeRetryButton: {hidden: true},
};
function invalidateLoadIntents() {
  loadIntentGeneration += 1;
  return loadIntentGeneration;
}
function clearPreparedDownload() {}
function setEngineMode() {}
function setStatus(value) { statusText = String(value); }
function setError(value) { errorText = String(value); }
function showWorkspace() {
  elements.startView.hidden = true;
  elements.workspace.hidden = false;
}
function replaceEditorFrame() {
  elements.frame = replacementFrame;
  return replacementFrame;
}
function saveNativeDraft() { return true; }
function saveNativeCanvasDraft() { return true; }
function saveDraft() { return true; }
""" + native_source + r"""
const canvas = {
  nodes: [{
    id: "g",
    type: "group",
    x: 0,
    y: 0,
    width: 400,
    height: 240,
    label: "Group",
    background: "image.png",
  }],
  edges: [],
};
globalThis.fetch = async () => {
  if (legacyConverterCalls !== 0) {
    throw new Error("legacy converter ran before native rejection");
  }
  return {
    ok: false,
    status: 422,
    async json() {
      return {error: "group backgrounds are not supported by the native editor"};
    },
  };
};
await launchNative({
  nativeImport: {
    schema_version: "schauwerk-native-import-request.v1",
    format: "json-canvas-1.0",
    source: canvas,
    title: "fallback",
  },
  nativeCanvas: canvas,
});
if (legacyConverterCalls !== 1) {
  throw new Error("native rejection did not invoke the legacy converter exactly once");
}
if (pendingLegacyFallback !== legacyXml) {
  throw new Error("native JSON Canvas rejection did not retain legacy fallback XML");
}
if (elements.legacyFallbackButton.hidden) {
  throw new Error("native JSON Canvas rejection did not expose the legacy fallback control");
}
if (!elements.workspace.hidden || elements.startView.hidden) {
  throw new Error("native JSON Canvas rejection did not return to the recoverable start view");
}
if (!errorText.includes("Das Original wurde nicht verändert")) {
  throw new Error("native JSON Canvas rejection did not explain source preservation");
}
if (!statusText.includes("Nativer Import abgelehnt") || !statusText.includes("Legacy verfügbar")) {
  throw new Error("native JSON Canvas rejection did not report generic legacy availability");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def test_native_rebuild_422_rerenders_last_live_valid_state(
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
let renderedNativeCanvasSnapshot = null;
function nativeCanvasSnapshot(canvas) {
  return canvas ? JSON.stringify(canvas) : null;
}
let pendingExport = null;
let pendingLoad = null;
let pendingInitialCollisionSafeLayout = false;
let pendingCreationDefaults = false;
let currentXml = null;
let currentRepresentation = null;
// Version 1 is the persisted bundle URL, while version 2 is a later live drag.
let currentNativeDocument = {version: 2};
let currentNativeCanvas = {version: 2};
let currentLegacyXml = null;
let pendingLegacyFallback = null;
let currentNativeUrl = "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html";
let editorReady = true;
let statusText = "";
let errorText = "";
let replaceCalls = 0;
let workspaceCalls = 0;
const nativeCanvasDraftVersions = [];
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
  nativeRetryButton: {hidden: true},
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
function saveNativeCanvasDraft(documentValue) {
  nativeCanvasDraftVersions.push(documentValue?.version);
  return true;
}
function saveDraft() { return true; }
""" + native_source + r"""
const rejectedDocument = {version: 3};
const rejectedCanvas = {version: 3};
const successfulUrl = "/native/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/index.html";
let fetchCalls = 0;
const sentVersions = [];
globalThis.fetch = async (_url, options) => {
  fetchCalls += 1;
  if (
    options.headers["X-Schauwerk-Native-Supersede"]
    !== "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  ) {
    throw new Error("supersede token drifted during rejection recovery");
  }
  sentVersions.push(JSON.parse(options.body).version);
  if (fetchCalls === 1) {
    return {
      ok: false,
      status: 422,
      async json() {
        return {error: "native JSON Canvas document exceeds product complexity limits"};
      },
    };
  }
  return {
    ok: true,
    status: 200,
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
  {nativeDocument: rejectedDocument, nativeCanvas: rejectedCanvas},
  {preserveActiveFrame: true},
);
if (fetchCalls !== 2 || sentVersions.join(",") !== "3,2") {
  throw new Error("permanent rejection did not re-render exactly the pre-candidate live state");
}
if (replaceCalls !== 1 || workspaceCalls !== 1) {
  throw new Error("recovery did not swap in exactly one fresh valid frame");
}
if (elements.frame !== replacementFrame || replacementFrame.src !== successfulUrl) {
  throw new Error("recovery did not activate the re-rendered live-valid bundle");
}
if (currentNativeDocument.version !== 2 || currentNativeCanvas.version !== 2) {
  throw new Error("permanent rejection did not retain the live-valid dragged state");
}
if (nativeCanvasRenderStale) {
  throw new Error("successful permanent-rejection recovery remained marked stale");
}
if (!editorReady) {
  throw new Error("successful permanent-rejection recovery lost editor readiness");
}
if (!elements.nativeRetryButton.hidden) {
  throw new Error("successful permanent-rejection recovery exposed a retry control");
}
if (!errorText.includes("abgelehnte Änderung wurde verworfen")) {
  throw new Error("permanent rejection did not explain candidate rollback");
}
if (!statusText.includes("letzter gültiger Dokumentzustand wiederhergestellt")) {
  throw new Error("permanent rejection did not report the restored live-valid state");
}
if (nativeSupersedeToken !== "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") {
  throw new Error("successful recovery did not advance the supersede token");
}
if (nativeCanvasDraftVersions.includes(3)) {
  throw new Error("permanently rejected candidate was persisted as a native canvas draft");
}
if (nativeCanvasDraftVersions.join(",") !== "2") {
  throw new Error("permanent rejection recovery did not persist exactly the restored live-valid state");
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def test_native_rebuild_failure_keeps_inconsistent_frame_inert_until_retry(
    tmp_path: Path,
) -> None:
    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome/Chromium is required in CI for native rebuild recovery")
        pytest.skip("Chrome/Chromium is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)

    probe_js = r"""
const waitUntil = async (predicate, label, attempts = 500) => {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(label);
};

try {
  const source = {
    nodes: [
      {id: "a", type: "text", x: 0, y: 0, width: 220, height: 120, text: "A"},
      {id: "b", type: "text", x: 320, y: 0, width: 220, height: 120, text: "B"},
    ],
    edges: [
      {id: "ab", fromNode: "a", toNode: "b", toEnd: "arrow"},
    ],
  };
  let initialNativeReadyFrame = null;
  const onInitialNativeReady = (event) => {
    const frame = document.querySelector("#editorFrame");
    const message = event.data;
    if (
      event.origin !== window.location.origin ||
      event.source !== frame?.contentWindow ||
      !message ||
      typeof message !== "object" ||
      message.event !== "native-document-change" ||
      message.document?.schema_version !== "schauwerk-native-editing-document.v1" ||
      !message.canvas ||
      typeof message.canvas !== "object"
    ) {
      return;
    }
    const nodeIds = new Set(
      Array.isArray(message.canvas.nodes)
        ? message.canvas.nodes.map((node) => node?.id)
        : []
    );
    if (!nodeIds.has("a") || !nodeIds.has("b")) return;
    initialNativeReadyFrame = frame;
  };
  window.addEventListener("message", onInitialNativeReady);
  document.querySelector("#sourceInput").value = JSON.stringify(source);
  document.querySelector("#openPasteButton").click();

  let loadedNativeFrame = null;
  await waitUntil(() => {
    const frame = document.querySelector("#editorFrame");
    if (
      !frame?.src?.includes("/native/") ||
      frame.contentDocument?.readyState !== "complete" ||
      !frame.contentDocument?.querySelector('[data-source-id="a"]') ||
      !frame.contentDocument?.querySelector("#deleteSelection") ||
      !frame.contentDocument?.querySelector("#resetLayout")
    ) {
      return false;
    }
    loadedNativeFrame = frame;
    return true;
  }, "initial native frame did not become ready");

  // Chrome --dump-dom virtual time can starve the viewer's one-shot initial
  // requestAnimationFrame publication. Ask the already-loaded real viewer to
  // republish its authoritative document state through an existing control.
  loadedNativeFrame.contentDocument.querySelector("#resetLayout").click();
  await waitUntil(
    () => initialNativeReadyFrame === loadedNativeFrame,
    "initial native viewer did not publish deterministic ready state",
  );
  window.removeEventListener("message", onInitialNativeReady);

  const firstFrame = document.querySelector("#editorFrame");
  const viewer = firstFrame.contentDocument;
  const nodeA = viewer.querySelector('[data-source-id="a"]');
  nodeA.dispatchEvent(new MouseEvent("dblclick", {
    bubbles: true,
    cancelable: true,
    view: firstFrame.contentWindow,
  }));
  await waitUntil(
    () => nodeA.classList.contains("is-selected"),
    "node selection did not become active",
  );
  const dialog = viewer.querySelector("#textDialog");
  if (dialog?.open) dialog.close();
  viewer.querySelector("#deleteSelection").click();

  await waitUntil(() => {
    const retry = document.querySelector("#nativeRetryButton");
    return (
      document.querySelector("#editorFrame") === firstFrame &&
      firstFrame.inert === true &&
      retry &&
      retry.hidden === false
    );
  }, "failed rebuild did not preserve an inert frame with retry");

  if (!firstFrame.contentDocument.querySelector('[data-source-id="a"]')) {
    throw new Error("stale frame DOM unexpectedly changed generation");
  }
  if (!document.querySelector("#error").textContent.includes(
    ".canvas-Export enthält den aktuellen Dokumentzustand"
  )) {
    throw new Error("failed rebuild lost the latest document export contract");
  }

  document.querySelector("#nativeRetryButton").click();

  await waitUntil(() => {
    const current = document.querySelector("#editorFrame");
    return (
      current !== firstFrame &&
      current?.src?.includes("/native/") &&
      current.contentDocument?.querySelector("#nativeDiagram")
    );
  }, "successful retry did not swap in a fresh native frame");

  const recoveredFrame = document.querySelector("#editorFrame");
  if (recoveredFrame.inert) {
    throw new Error("successful retry left the replacement frame inert");
  }
  if (recoveredFrame.contentDocument.querySelector('[data-source-id="a"]')) {
    throw new Error("successful retry did not render the retained deletion");
  }
  if (!recoveredFrame.contentDocument.querySelector('[data-source-id="b"]')) {
    throw new Error("successful retry lost the surviving node");
  }
  if (!document.querySelector("#nativeRetryButton").hidden) {
    throw new Error("successful retry left the retry control visible");
  }

  document.documentElement.dataset.rebuildRecoveryBrowserRegression = "pass";
} catch (error) {
  document.documentElement.dataset.rebuildRecoveryBrowserRegression = "fail";
  document.documentElement.dataset.rebuildRecoveryBrowserRegressionError = String(
    error?.message || error
  );
}
"""
    (output / "rebuild-recovery-browser.js").write_text(probe_js, encoding="utf-8")
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    assert index.count("</body>") == 1
    index_path.write_text(
        index.replace(
            "</body>",
            '<script type="module" src="rebuild-recovery-browser.js"></script></body>',
        ),
        encoding="utf-8",
    )

    class FailSecondNativeRenderHandler(_EditorRequestHandler):
        editor_origin = EDITOR_ORIGIN
        post_count = 0
        failed_payload: dict[str, object] | None = None

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_POST(self) -> None:  # noqa: N802
            cls = type(self)
            if self.path == NATIVE_API_PATH:
                cls.post_count += 1
                if cls.post_count == 2:
                    raw_length = self.headers.get("Content-Length", "0")
                    length = int(raw_length)
                    payload = self.rfile.read(length)
                    cls.failed_payload = json.loads(payload.decode("utf-8"))
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "synthetic rebuild failure"},
                    )
                    return
            super().do_POST()

    handler = partial(FailSecondNativeRenderHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

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

    try:
        completed = subprocess.run(
            [
                chrome,
                "--headless=new",
                *local_profile_args,
                "--no-first-run",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=18000",
                "--dump-dom",
                f"http://127.0.0.1:{port}/",
            ],
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
            env=chrome_env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert (
        'data-rebuild-recovery-browser-regression="pass"' in completed.stdout
    ), completed.stdout
    assert (
        'data-rebuild-recovery-browser-regression="fail"' not in completed.stdout
    ), completed.stdout
    assert FailSecondNativeRenderHandler.post_count >= 3
    failed_payload = FailSecondNativeRenderHandler.failed_payload
    assert isinstance(failed_payload, dict)
    failed_nodes = failed_payload.get("nodes")
    assert isinstance(failed_nodes, list)
    assert {str(node["id"]) for node in failed_nodes if isinstance(node, dict)} == {"b"}


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


def test_native_product_admission_rejects_oversized_embedded_canvas_before_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = {
        "schema_version": standalone_editor.NATIVE_DOCUMENT_SCHEMA,
        "source_format": "json-canvas-1.0",
        "title": "Oversized source",
        "input_digest": "a" * 64,
        "source_digest": "a" * 64,
        "source": {
            "nodes": [
                {"id": f"source-{index}", "type": "text"}
                for index in range(standalone_editor.MAX_NATIVE_NODES + 1)
            ],
            "edges": [],
        },
        "nodes": [],
        "edges": [],
    }

    normalization_called = False

    def unexpected_normalization(_value: object) -> dict[str, object]:
        nonlocal normalization_called
        normalization_called = True
        raise AssertionError("oversized embedded source must fail before normalization")

    monkeypatch.setattr(
        standalone_editor,
        "normalize_editing_document",
        unexpected_normalization,
    )

    with pytest.raises(StandaloneEditorError, match="complexity limits"):
        _native_product_input(value)
    assert normalization_called is False


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
        ("127.0.0.1", 0),        partial(blocked_handler, directory=str(output)),
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
                    release_deadline = time.monotonic() + 1.0
                    while (
                        previous.pin_leases.get(client, 0.0) > time.monotonic()
                        and time.monotonic() < release_deadline
                    ):
                        time.sleep(0.001)
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


@pytest.mark.parametrize("limit_mode", ["entries", "bytes"])
def test_native_supersede_projects_exclusive_lease_from_global_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_mode: str,
) -> None:
    output = tmp_path / f"exclusive-global-{limit_mode}"
    build_standalone_editor(output)

    client = "203.0.113.77"
    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_aaaa"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert first_created is True

    if limit_mode == "entries":
        monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 2)
        monkeypatch.setattr(
            standalone_editor,
            "MAX_NATIVE_CACHE_BYTES",
            64 * 1024 * 1024,
        )
    else:
        monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 32)
        monkeypatch.setattr(
            standalone_editor,
            "MAX_NATIVE_CACHE_BYTES",
            first_record.size_bytes + standalone_editor.MAX_NATIVE_BUNDLE_BYTES,
        )

    second = _golden_representation("decision-flow-v1.json")
    second["id"] = "flow_bbbb"
    second_normalized = _native_product_input(second)
    second_record, second_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(second_normalized["input_digest"]),
        value=second,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
        superseded_record=first_record,
    )

    assert second_created is True
    assert first_record.pin_leases[client] > time.monotonic()
    assert second_record.pin_leases[client] > time.monotonic()
    assert (
        standalone_editor._release_native_superseded_lease(
            output,
            token=first_record.token,
            admission_key=client,
            next_digest=second_record.digest,
        )
        is True
    )
    assert first_record.pin_leases.get(client, 0.0) <= time.monotonic()


def test_native_supersede_projection_carries_through_prune_byte_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "exclusive-prune-bytes"
    build_standalone_editor(output)

    client = "203.0.113.77"
    other_client = "203.0.113.88"

    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_superseded"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert first_created is True

    other = _golden_representation("decision-flow-v1.json")
    other["id"] = "flow_other"
    other_normalized = _native_product_input(other)
    other_record, other_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(other_normalized["input_digest"]),
        value=other,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=other_client,
    )
    assert other_created is True

    first_record.size_bytes = 2 * 1024 * 1024
    other_record.size_bytes = 15 * 1024 * 1024
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 32)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_BYTES", 32 * 1024 * 1024)

    replacement = _golden_representation("decision-flow-v1.json")
    replacement["id"] = "flow_replacement"
    replacement_normalized = _native_product_input(replacement)
    replacement_record, replacement_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(replacement_normalized["input_digest"]),
        value=replacement,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
        superseded_record=first_record,
    )

    assert replacement_created is True
    assert replacement_record is not first_record
    assert first_record.pin_leases.get(client, 0.0) > time.monotonic()
    assert other_record.pin_leases.get(other_client, 0.0) > time.monotonic()
    assert replacement_record.pin_leases.get(client, 0.0) > time.monotonic()


def test_native_supersede_projection_reaches_post_build_prune(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "post-build-prune-projection"
    build_standalone_editor(output)
    client = "203.0.113.77"

    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_superseded"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert first_created is True

    original_prune = standalone_editor._prune_native_cache
    prune_calls: list[
        tuple[
            standalone_editor._NativeCacheRecord | None,
            standalone_editor._NativeCacheRecord | None,
            str | None,
        ]
    ] = []

    def observed_prune(root: Path, **kwargs: object) -> None:
        original_prune(root, **kwargs)
        prune_calls.append(
            (
                kwargs.get("keep"),
                kwargs.get("superseded_record"),
                kwargs.get("admission_key"),
            )
        )

    monkeypatch.setattr(standalone_editor, "_prune_native_cache", observed_prune)

    replacement = _golden_representation("decision-flow-v1.json")
    replacement["id"] = "flow_replacement"
    replacement_normalized = _native_product_input(replacement)
    replacement_record, replacement_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(replacement_normalized["input_digest"]),
        value=replacement,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
        superseded_record=first_record,
    )

    assert replacement_created is True
    assert len(prune_calls) == 2
    assert prune_calls[0] == (None, first_record, client)
    assert prune_calls[1] == (replacement_record, first_record, client)


def test_successful_native_supersede_prunes_released_projection_after_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "post-delivery-supersede-prune"
    build_standalone_editor(output, public_base_path="/schaubild")
    client = "203.0.113.77"
    other_client = "203.0.113.88"

    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_superseded"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert first_created is True

    other = _golden_representation("decision-flow-v1.json")
    other["id"] = "flow_other"
    other_normalized = _native_product_input(other)
    other_record, other_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(other_normalized["input_digest"]),
        value=other,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=other_client,
    )
    assert other_created is True
    standalone_editor._abandon_native_cache_record(
        output,
        other_record,
        admission_key=other_client,
    )
    assert other_record.pin_leases == {}
    assert other_record.consumer_counts == {}

    first_record.size_bytes = 16 * 1024 * 1024
    other_record.size_bytes = 15 * 1024 * 1024
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 32)
    monkeypatch.setattr(
        standalone_editor,
        "MAX_NATIVE_CACHE_BYTES",
        32 * 1024 * 1024,
    )
    monkeypatch.setattr(
        standalone_editor,
        "_native_bundle_size",
        lambda _path: 16 * 1024 * 1024,
    )

    handler_class = type(
        "PostDeliverySupersedePruneHandler",
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
    try:
        replacement = _golden_representation("decision-flow-v1.json")
        replacement["id"] = "flow_replacement"
        payload = json.dumps(replacement).encode("utf-8")
        connection = HTTPConnection(
            "127.0.0.1",
            int(server.server_address[1]),
            timeout=5,
        )
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
                "X-Forwarded-For": client,
                standalone_editor.NATIVE_SUPERSEDE_HEADER: first_record.token,
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200, body
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    records = standalone_editor._native_cache_records(output)
    assert sum(record.size_bytes for record in records) <= standalone_editor.MAX_NATIVE_CACHE_BYTES
    assert len(records) == 2
    assert sum(
        record is candidate
        for record in records
        for candidate in (first_record, other_record)
    ) == 1
    assert first_record.path.exists() != other_record.path.exists()


def test_native_prune_revalidates_supersede_projection_after_foreign_repin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "prune-revalidate-supersede"
    build_standalone_editor(output)
    client_a = "203.0.113.77"
    client_b = "203.0.113.88"
    other_client = "203.0.113.99"

    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_superseded"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client_a,
    )
    assert first_created is True

    other = _golden_representation("decision-flow-v1.json")
    other["id"] = "flow_other"
    other_normalized = _native_product_input(other)
    other_record, other_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(other_normalized["input_digest"]),
        value=other,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=other_client,
    )
    assert other_created is True

    standalone_editor._pin_native_cache_record(
        output,
        first_record,
        admission_key=client_b,
    )
    first_record.size_bytes = 2 * 1024 * 1024
    other_record.size_bytes = 15 * 1024 * 1024
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 32)
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_BYTES", 32 * 1024 * 1024)
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="temporarily pinned",
    ):
        standalone_editor._prune_native_cache(
            output,
            keep=None,
            reserve_bytes=standalone_editor.MAX_NATIVE_BUNDLE_BYTES,
            reserve_entries=1,
            superseded_record=first_record,
            admission_key=client_a,
        )


@pytest.mark.parametrize("limit_mode", ["entries", "bytes"])
def test_native_supersede_keeps_shared_record_in_global_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_mode: str,
) -> None:
    output = tmp_path / f"shared-global-{limit_mode}"
    build_standalone_editor(output)

    client_a = "203.0.113.77"
    client_b = "203.0.113.88"
    first = _golden_representation("decision-flow-v1.json")
    first["id"] = "flow_aaaa"
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client_a,
    )
    assert first_created is True
    standalone_editor._pin_native_cache_record(
        output,
        first_record,
        admission_key=client_b,
    )

    if limit_mode == "entries":
        monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 2)
        monkeypatch.setattr(
            standalone_editor,
            "MAX_NATIVE_CACHE_BYTES",
            64 * 1024 * 1024,
        )
    else:
        monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 32)
        monkeypatch.setattr(
            standalone_editor,
            "MAX_NATIVE_CACHE_BYTES",
            first_record.size_bytes + standalone_editor.MAX_NATIVE_BUNDLE_BYTES,
        )

    second = _golden_representation("decision-flow-v1.json")
    second["id"] = "flow_bbbb"
    second_normalized = _native_product_input(second)
    renderer_called = False

    def unexpected_build(*_args: object, **_kwargs: object) -> object:
        nonlocal renderer_called
        renderer_called = True
        raise AssertionError("shared superseded bundle must still consume global capacity")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", unexpected_build)
    with pytest.raises(
        standalone_editor.NativeCacheCapacityError,
        match="pin capacity",
    ):
        standalone_editor._build_native_cache_record(
            output,
            digest=str(second_normalized["input_digest"]),
            value=second,
            serve_binding="trusted-reverse-proxy-private-ingress",
            public_base_path="/schaubild",
            admission_key=client_a,
            superseded_record=first_record,
        )

    assert renderer_called is False
    assert first_record.pin_leases[client_a] > time.monotonic()
    assert first_record.pin_leases[client_b] > time.monotonic()


def test_trusted_proxy_native_supersede_preserves_live_bundle_on_renderer_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "renderer-failure-editor"
    build_standalone_editor(output, public_base_path="/schaubild")
    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_PINNED_ENTRIES_PER_CLIENT", 1)

    client = "203.0.113.77"
    first = _golden_representation("decision-flow-v1.json")
    first_normalized = _native_product_input(first)
    first_record, first_created = standalone_editor._build_native_cache_record(
        output,
        digest=str(first_normalized["input_digest"]),
        value=first,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert first_created is True
    assert first_record.pin_leases[client] > time.monotonic()

    def failed_build(**_kwargs: object) -> None:
        raise standalone_editor.NativeViewerError("synthetic renderer failure")

    monkeypatch.setattr(standalone_editor, "_run_native_viewer_build", failed_build)
    second = _golden_representation("decision-flow-v1.json")
    second["id"] = "supersede_renderer_failure"
    second_payload = json.dumps(second).encode("utf-8")

    handler = object.__new__(_EditorRequestHandler)
    handler.path = NATIVE_API_PATH
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(second_payload)),
        standalone_editor.NATIVE_SUPERSEDE_HEADER: first_record.token,
    }
    handler.rfile = io.BytesIO(second_payload)
    handler.directory = str(output)
    handler.native_serve_binding = "trusted-reverse-proxy-private-ingress"
    handler.public_base_path = "/schaubild"
    handler._request_deadline_expired = False
    handler._request_deadline_at = time.monotonic() + 5
    handler.close_connection = False
    monkeypatch.setattr(handler, "_reject_non_loopback_host", lambda: False)
    monkeypatch.setattr(handler, "_native_admission_key", lambda: client)
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def capture_json(
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        write_body: bool = True,
    ) -> bool:
        del write_body
        responses.append((status, payload))
        return True

    monkeypatch.setattr(handler, "_send_json", capture_json)
    handler.do_POST()

    assert responses
    status, body = responses[-1]
    assert status == HTTPStatus.SERVICE_UNAVAILABLE, body
    assert "synthetic renderer failure" in str(body["error"])
    assert first_record.pin_leases.get(client, 0.0) > time.monotonic()
    assert standalone_editor._native_cache_by_token(output, first_record.token) is first_record


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


def test_native_render_endpoint_rejects_lossy_json_canvas_number_tokens(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "CanvasNumberFidelityEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
        for token, expected_error in (
            ("9007199254740990.5", "would change during JavaScript roundtrip"),
            ("1e400", "finite JavaScript number range"),
        ):
            payload = (
                '{"schema_version":"schauwerk-native-import-request.v1",'
                '"format":"json-canvas-1.0","source":{"nodes":[],"edges":[],'
                '"plugin":{"revision":__TOKEN__}}}'
            ).replace("__TOKEN__", token).encode()
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
            assert response.status == 422
            assert expected_error in body["error"]

        safe_payload = (
            b'{"schema_version":"schauwerk-native-import-request.v1",'
            b'"format":"json-canvas-1.0","source":{"nodes":[],"edges":[],'
            b'"plugin":{"revision":0.1,"numericText":"9007199254740990.5"}}}'
        )
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=safe_payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(safe_payload)),
            },
        )
        safe_response = connection.getresponse()
        safe_body = json.loads(safe_response.read().decode("utf-8"))
        assert safe_response.status == 200, safe_body
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
const extensionOnly = JSON.stringify({{customTopLevel: {{kept: true}}}});
if (detectInput(extensionOnly).kind !== 'unknown') throw new Error('extension-only arbitrary JSON was auto-detected without Canvas context');
const explicitExtensionOnly = detectInput(extensionOnly, {{allowExtensionOnlyCanvas: true}});
if (explicitExtensionOnly.kind !== 'json-canvas') throw new Error('extension-only JSON Canvas rejected with explicit context');
if (explicitExtensionOnly.value?.customTopLevel?.kept !== true) throw new Error('extension-only JSON Canvas data was not preserved');
const unsafeIntegerCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":9007199254740993}}}}';
if (detectInput(unsafeIntegerCanvas).kind !== 'unknown') throw new Error('unsafe JSON integer Canvas was accepted after numeric rounding');
const roundedFractionCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":9007199254740990.5}}}}';
if (detectInput(roundedFractionCanvas).kind !== 'unknown') throw new Error('rounded JSON fraction Canvas was accepted after numeric rounding');
const overflowingExponentCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":1e400}}}}';
if (detectInput(overflowingExponentCanvas).kind !== 'unknown') throw new Error('overflowing JSON exponent Canvas was accepted');
const safeFractionCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":0.1}}}}';
const safeFractionDetected = detectInput(safeFractionCanvas);
if (safeFractionDetected.kind !== 'json-canvas') throw new Error('roundtrip-stable JSON fraction Canvas was rejected');
if (safeFractionDetected.value?.plugin?.revision !== 0.1) throw new Error('roundtrip-stable JSON fraction changed value');
const numericStringCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":"9007199254740990.5"}}}}';
if (detectInput(numericStringCanvas).kind !== 'json-canvas') throw new Error('numeric text was mistaken for a JSON number token');
const safeIntegerCanvas = '{{"nodes":[],"edges":[],"plugin":{{"revision":9007199254740991}}}}';
const safeIntegerDetected = detectInput(safeIntegerCanvas);
if (safeIntegerDetected.kind !== 'json-canvas') throw new Error('maximum safe JSON integer Canvas was rejected');
if (safeIntegerDetected.value?.plugin?.revision !== Number.MAX_SAFE_INTEGER) throw new Error('maximum safe JSON integer changed value');
if (detectInput(JSON.stringify({{theme: 'dark'}})).kind !== 'unknown') throw new Error('arbitrary JSON misdetected as JSON Canvas');
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
const explicitExtensionFence = fence + 'canvas\\n' + extensionOnly + '\\n' + fence;
const detectedExtensionFence = detectInput(explicitExtensionFence);
if (detectedExtensionFence.kind !== 'json-canvas') throw new Error('extension-only Canvas fence rejected');
if (detectedExtensionFence.value?.customTopLevel?.kept !== true) throw new Error('Canvas-fenced extension data was not preserved');
const genericExtensionFence = fence + 'json\\n' + extensionOnly + '\\n' + fence;
if (detectInput(genericExtensionFence).kind !== 'unknown') throw new Error('generic JSON fence granted Canvas extension context');
for (const inlineCanvas of [
  fence + 'canvas\\n' + nodesOnly + '\\n' + fence,
  fence + '.canvas\\n' + nodesOnly + '\\n' + fence,
  'Hier ist das Schaubild:\\n\\n' + fence + 'json-canvas\\n' + nodesOnly + '\\n' + fence + '\\n\\nDu kannst es bearbeiten.',
  'Hinweis:\\n' + fence + 'json\\n' + extensionOnly + '\\n' + fence + '\\nSchaubild:\\n' + fence + 'canvas\\n' + nodesOnly + '\\n' + fence,
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


def test_same_ip_supersede_releases_only_one_native_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "same-ip-consumers"
    build_standalone_editor(output)
    client = "203.0.113.77"
    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    digest = str(normalized["input_digest"])

    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert created is True
    same_record, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert same_record is record
    assert created is False
    assert record.consumer_counts == {client: 2}

    standalone_editor._pin_native_cache_record(
        output,
        record,
        admission_key=client,
        acquire_consumer=False,
    )
    assert record.consumer_counts == {client: 2}

    assert standalone_editor._release_native_superseded_lease(
        output,
        token=record.token,
        admission_key=client,
        next_digest="f" * 64,
    )
    assert record.consumer_counts == {client: 1}
    assert record.pin_leases.get(client, 0.0) > time.monotonic()
    root_key = standalone_editor._native_root_key(output)
    window = standalone_editor._NATIVE_PIN_WINDOWS[(root_key, digest)]
    assert window.terminally_released is False

    monkeypatch.setattr(standalone_editor, "MAX_NATIVE_CACHE_ENTRIES", 1)
    with pytest.raises(standalone_editor.NativeCacheCapacityError, match="temporarily pinned"):
        standalone_editor._prune_native_cache(
            output,
            keep=None,
            reserve_entries=1,
        )
    assert standalone_editor._native_cache_by_token(output, record.token) is record

    assert standalone_editor._release_native_superseded_lease(
        output,
        token=record.token,
        admission_key=client,
        next_digest="e" * 64,
    )
    assert record.consumer_counts == {}
    assert record.pin_leases.get(client, 0.0) <= time.monotonic()
    assert window.terminally_released is True


def test_expired_native_client_lease_drops_stale_consumer_before_reacquire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "expired-client-lease"
    build_standalone_editor(output)
    client = "198.51.100.10"
    clock = [100.0]
    monkeypatch.setattr(standalone_editor.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_GRACE_SECONDS", 60.0)
    monkeypatch.setattr(standalone_editor, "NATIVE_CACHE_MAX_PIN_SECONDS", 120.0)

    value = _golden_representation("decision-flow-v1.json")
    normalized = _native_product_input(value)
    digest = str(normalized["input_digest"])
    record, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert created is True
    assert record.pin_leases == {client: 160.0}
    assert record.consumer_counts == {client: 1}
    assert record.max_pinned_until == 220.0

    clock[0] = 161.0
    same_record, created = standalone_editor._build_native_cache_record(
        output,
        digest=digest,
        value=value,
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
        admission_key=client,
    )
    assert same_record is record
    assert created is False
    assert record.pin_leases == {client: 220.0}
    assert record.consumer_counts == {client: 1}

    assert standalone_editor._release_native_superseded_lease(
        output,
        token=record.token,
        admission_key=client,
        next_digest="f" * 64,
    )
    assert record.consumer_counts == {}
    assert record.pin_leases.get(client, 0.0) <= clock[0]
    root_key = standalone_editor._native_root_key(output)
    assert standalone_editor._NATIVE_PIN_WINDOWS[(root_key, digest)].terminally_released is True


def test_terminal_supersede_history_does_not_block_129th_normal_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "pin-window-history"
    build_standalone_editor(output)

    def fake_build(
        _value: dict[str, object],
        target: Path,
        **_kwargs: object,
    ) -> None:
        (target / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(standalone_editor, "build_native_viewer", fake_build)
    previous = None
    for index in range(standalone_editor.MAX_NATIVE_PIN_WINDOWS + 1):
        value = _golden_representation("decision-flow-v1.json")
        value["id"] = f"history_flow_{index}"
        normalized = _native_product_input(value)
        digest = str(normalized["input_digest"])
        record, created = standalone_editor._build_native_cache_record(
            output,
            digest=digest,
            value=value,
            serve_binding="127.0.0.1-only",
            public_base_path="",
            admission_key=standalone_editor._LOCAL_ADMISSION_KEY,
            superseded_record=previous,
        )
        assert created is True
        if previous is not None:
            assert standalone_editor._release_native_superseded_lease(
                output,
                token=previous.token,
                admission_key=standalone_editor._LOCAL_ADMISSION_KEY,
                next_digest=digest,
            )
        previous = record

    root_key = standalone_editor._native_root_key(output)
    root_windows = [
        window
        for (window_root, _digest), window in standalone_editor._NATIVE_PIN_WINDOWS.items()
        if window_root == root_key
    ]
    assert len(root_windows) <= standalone_editor.MAX_NATIVE_PIN_WINDOWS
    assert previous is not None
    assert previous.consumer_counts == {standalone_editor._LOCAL_ADMISSION_KEY: 1}


def test_normalized_json_canvas_overflow_is_422_before_renderer_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "normalized-overflow"
    build_standalone_editor(output)
    value = {
        "schema_version": standalone_editor.NATIVE_IMPORT_SCHEMA,
        "format": "json-canvas-1.0",
        "title": "Probe.canvas",
        "source": {
            "nodes": [
                {
                    "id": "big",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 320,
                    "height": 180,
                    "text": "x" * 1_800_000,
                }
            ],
            "edges": [],
        },
    }
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(payload) < standalone_editor.MAX_NATIVE_REQUEST_BYTES
    normalized = _native_product_input(value)
    assert (
        standalone_editor._native_viewer_input_size(normalized)
        > standalone_editor.MAX_NATIVE_VIEWER_INPUT_BYTES
    )

    renderer_called = False

    def unexpected_renderer(**_kwargs: object) -> None:
        nonlocal renderer_called
        renderer_called = True
        raise AssertionError("deterministic oversized normalized input must not spawn renderer")

    monkeypatch.setattr(standalone_editor, "_run_native_viewer_build", unexpected_renderer)
    handler = object.__new__(_EditorRequestHandler)
    handler.path = NATIVE_API_PATH
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(payload)),
    }
    handler.rfile = io.BytesIO(payload)
    handler.directory = str(output)
    handler.native_serve_binding = "127.0.0.1-only"
    handler.public_base_path = ""
    handler._request_deadline_expired = False
    handler._request_deadline_at = time.monotonic() + 5
    handler.close_connection = False
    monkeypatch.setattr(handler, "_reject_non_loopback_host", lambda: False)
    monkeypatch.setattr(
        handler,
        "_native_admission_key",
        lambda: standalone_editor._LOCAL_ADMISSION_KEY,
    )
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def capture_json(
        status: HTTPStatus,
        body: dict[str, object],
        *,
        write_body: bool = True,
    ) -> bool:
        del write_body
        responses.append((status, body))
        return True

    monkeypatch.setattr(handler, "_send_json", capture_json)
    handler.do_POST()

    assert responses
    status, body = responses[-1]
    assert status == HTTPStatus.UNPROCESSABLE_ENTITY, body
    assert "exceeds 5 MB after normalization" in str(body["error"])
    assert renderer_called is False


def test_undelivered_cache_hit_releases_its_consumer_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "undelivered-cache-hit"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    payload = json.dumps(value).encode("utf-8")

    handler = object.__new__(_EditorRequestHandler)
    handler.path = NATIVE_API_PATH
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(payload)),
    }
    handler.directory = str(output)
    handler.native_serve_binding = "127.0.0.1-only"
    handler.public_base_path = ""
    handler.close_connection = False
    monkeypatch.setattr(handler, "_reject_non_loopback_host", lambda: False)
    monkeypatch.setattr(
        handler,
        "_native_admission_key",
        lambda: standalone_editor._LOCAL_ADMISSION_KEY,
    )
    monkeypatch.setattr(handler, "_send_json", lambda *_args, **_kwargs: False)

    for _attempt in range(2):
        handler.rfile = io.BytesIO(payload)
        handler._request_deadline_expired = False
        handler._request_deadline_at = time.monotonic() + 5
        handler.do_POST()
        records = standalone_editor._native_cache_records(output)
        assert len(records) == 1
        assert records[0].consumer_counts == {}
        assert records[0].pin_leases == {}


def test_same_digest_supersede_does_not_leak_native_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "same-digest-supersede"
    build_standalone_editor(output)
    value = _golden_representation("decision-flow-v1.json")
    payload = json.dumps(value).encode("utf-8")

    def fake_renderer(
        *,
        value: dict[str, object],
        target: Path,
        serve_binding: str,
        public_base_path: str,
        timeout_seconds: float,
    ) -> None:
        del value, serve_binding, public_base_path, timeout_seconds
        (target / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(standalone_editor, "_run_native_viewer_build", fake_renderer)

    def post(supersede_token: str = "") -> dict[str, object]:
        handler = object.__new__(_EditorRequestHandler)
        handler.path = NATIVE_API_PATH
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        }
        if supersede_token:
            headers[standalone_editor.NATIVE_SUPERSEDE_HEADER] = supersede_token
        handler.headers = headers
        handler.rfile = io.BytesIO(payload)
        handler.directory = str(output)
        handler.native_serve_binding = "127.0.0.1-only"
        handler.public_base_path = ""
        handler._request_deadline_expired = False
        handler._request_deadline_at = time.monotonic() + 5
        handler.close_connection = False
        monkeypatch.setattr(handler, "_reject_non_loopback_host", lambda: False)
        monkeypatch.setattr(
            handler,
            "_native_admission_key",
            lambda: standalone_editor._LOCAL_ADMISSION_KEY,
        )
        responses: list[tuple[HTTPStatus, dict[str, object]]] = []

        def capture_json(
            status: HTTPStatus,
            body: dict[str, object],
            *,
            write_body: bool = True,
        ) -> bool:
            del write_body
            responses.append((status, body))
            return True

        monkeypatch.setattr(handler, "_send_json", capture_json)
        handler.do_POST()
        assert responses
        status, body = responses[-1]
        assert status == HTTPStatus.OK, body
        return body

    first = post()
    token = str(first["url"]).split("/native/", 1)[1].split("/", 1)[0]
    record = standalone_editor._native_cache_by_token(output, token)
    assert record is not None
    assert record.consumer_counts == {standalone_editor._LOCAL_ADMISSION_KEY: 1}

    second = post(token)
    assert second["url"] == first["url"]
    assert record.consumer_counts == {standalone_editor._LOCAL_ADMISSION_KEY: 1}

    # A fully released old token may legitimately reacquire the same digest:
    # the sole new consumer must not be mistaken for a duplicate.
    assert standalone_editor._release_native_superseded_lease(
        output,
        token=token,
        admission_key=standalone_editor._LOCAL_ADMISSION_KEY,
        next_digest="f" * 64,
    )
    assert record.consumer_counts == {}
    third = post(token)
    assert third["url"] == first["url"]
    assert record.consumer_counts == {standalone_editor._LOCAL_ADMISSION_KEY: 1}
