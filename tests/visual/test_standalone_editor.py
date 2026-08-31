# ruff: noqa: E501
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.visual.standalone_editor import (
    EDITOR_ORIGIN,
    MANIFEST_SCHEMA,
    StandaloneEditorError,
    _content_security_policy,
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
    assert manifest["engine_delivery"] == "remote-browser-iframe"
    assert manifest["network_boundary"] == {
        "shell": "local-static-files",
        "editor_runtime": EDITOR_ORIGIN,
        "public_embed_runtime": True,
        "operator_configured_editor_runtime": False,
        "offline_mode_requested": False,
        "offline_complete": False,
    }
    assert manifest["supported_inputs"] == ["mermaid", "json-canvas-1.0", "drawio-xml"]
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
    assert "MIN_READABLE_SCALE = 0.65" in helper_js
    assert "fontSize=${READABLE_NODE_FONT_SIZE}" in helper_js
    assert "fontSize=${READABLE_EDGE_FONT_SIZE}" in helper_js
    assert "event.origin !== EDITOR_ORIGIN" in app_js
    assert "event.source !== elements.frame.contentWindow" in app_js
    assert "maxFitScale: 1" in app_js
    assert re.search(
        r'^import \{[^}]*\bREADABILITY_ZOOM_FACTOR\b[^}]*\} from "\./canvas-import\.js";$',
        app_js,
        flags=re.MULTILINE,
    )
    assert "zoomFactor: READABILITY_ZOOM_FACTOR" in app_js
    assert "defaultVertexStyle: { fontSize: String(READABLE_NODE_FONT_SIZE) }" in app_js
    assert "defaultEdgeStyle: { fontSize: String(READABLE_EDGE_FONT_SIZE) }" in app_js
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
    file_input = re.search(r'<input\b[^>]*\bid="fileInput"[^>]*>', index_html)
    assert file_input is not None
    assert re.search(r"\baccept\s*=", file_input.group(0), flags=re.IGNORECASE) is None
    assert "placeholder=\"Zum Beispiel:&#10;flowchart TD&#10;" in index_html
    assert 'aria-pressed="false"' in index_html
    assert 'aria-label="Vollbildmodus aktivieren"' in index_html
    assert "body.editor-focus .topline" in styles_css
    assert "body.editor-focus .workspace-bar > :not(.fullscreen-toggle)" in styles_css
    assert "height: 100dvh" in styles_css
    assert 'fullscreenButton: document.querySelector("#fullscreenButton")' in app_js
    assert "return { xml: validateDiagramXml(detected.text) };" in app_js
    assert "function replaceEditorFrame()" in app_js
    assert "const frame = previous.cloneNode(false);" in app_js
    assert "previous.replaceWith(frame);" in app_js
    assert "elements.frame = frame;" in app_js
    assert "if (elements.frame !== frame) return;" in app_js
    assert "let loadIntentGeneration = 0;" in app_js
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
    assert "invalidateLoadIntents();" in app_js[launch_start:launch_end]
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
    assert 'event.key === "Escape"' not in app_js


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
        "editor_runtime": "http://127.0.0.1:8878",
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
    assert "frame-src http://127.0.0.1:8878;" in _content_security_policy(
        str(manifest["editor_origin"])
    )


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
import {{ MAX_INPUT_BYTES, READABLE_EDGE_FONT_SIZE, READABLE_NODE_FONT_SIZE, detectInput, exportDataUriToBlob, jsonCanvasToDrawioXml, readabilityZoomStepCount, validateExportDataUri, validateInputText }} from {module_url!r};
if (READABLE_NODE_FONT_SIZE !== 18 || READABLE_EDGE_FONT_SIZE !== 16) throw new Error('readability font profile drifted');
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
if (!xml.includes('fontSize=18')) throw new Error('missing readable node font size');
if (!xml.includes('fontSize=16')) throw new Error('missing readable edge font size');
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
    completed = subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--virtual-time-budget=3000",
            "--dump-dom",
            harness.as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert '<pre id="result">PASS</pre>' in completed.stdout
