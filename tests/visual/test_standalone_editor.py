# ruff: noqa: E501
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from schauwerk.visual.standalone_editor import (
    EDITOR_ORIGIN,
    MANIFEST_SCHEMA,
    StandaloneEditorError,
    build_standalone_editor,
)


def test_build_standalone_editor_writes_deterministic_bundle(tmp_path: Path) -> None:
    output = tmp_path / "editor"

    manifest = build_standalone_editor(output)

    assert manifest["schema_version"] == MANIFEST_SCHEMA
    assert manifest["editor_origin"] == EDITOR_ORIGIN
    assert manifest["network_boundary"]["offline_complete"] is False
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
    editor_origin_match = re.search(
        r'^const EDITOR_ORIGIN = (?P<value>"[^"\r\n]+")\s*;$',
        app_js,
        flags=re.MULTILINE,
    )
    assert editor_origin_match is not None
    assert json.loads(editor_origin_match.group("value")) == EDITOR_ORIGIN
    assert "jsonCanvasToDrawioXml" in helper_js
    assert "event.origin !== EDITOR_ORIGIN" in app_js
    assert "event.source !== elements.frame.contentWindow" in app_js
    assert 'format: "xml"' not in app_js
    assert "validateExportDataUri(message.data, wanted)" in app_js
    assert "if (saveDraft(validateDiagramXml(message.xml)))" in app_js
    assert "if (pendingExport !== null)" in app_js
    assert 'setStatus("Export läuft bereits …")' in app_js
    assert "KI-Ergebnis hier einfügen" in (output / "index.html").read_text(encoding="utf-8")


def test_build_rejects_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    output.mkdir()
    (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(StandaloneEditorError, match="must be empty"):
        build_standalone_editor(output)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_canvas_import_module_converts_basic_json_canvas_when_node_available(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    module_source = (output / "canvas-import.js").read_bytes()
    module_url = "data:text/javascript;base64," + base64.b64encode(module_source).decode("ascii")

    code = f"""
import {{ detectInput, jsonCanvasToDrawioXml, validateDiagramXml, validateExportDataUri }} from {module_url!r};
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
for (const mermaid of [
  '%% comment\\nflowchart TD\\n  A --> B',
  '%%{{init: {{"theme":"neutral"}}}}%%\\nsequenceDiagram\\n  A->>B: Hallo',
  '---\\ntitle: Beispiel\\n---\\n%% comment\\ngraph LR\\n  A --> B',
]) {{
  const detectedMermaid = detectInput(mermaid);
  if (detectedMermaid.kind !== 'mermaid') throw new Error(`commented Mermaid rejected: ${{detectedMermaid.kind}}`);
}}
const xml = jsonCanvasToDrawioXml(detected.value);
if (!xml.includes('<mxGraphModel')) throw new Error('missing graph model');
if (!xml.includes('jsonCanvasId="a"')) throw new Error('missing source id');
if (!xml.includes('ermöglicht')) throw new Error('missing edge label');
if (!xml.includes('exitX=1')) throw new Error('missing source-side binding');
const png = 'data:image/png;base64,AA==';
const svg = 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=';
if (validateExportDataUri(png, 'png') !== png) throw new Error('png export rejected');
if (validateExportDataUri(svg, 'svg') !== svg) throw new Error('svg export rejected');
if (validateDiagramXml('<mxfile><diagram/></mxfile>') !== '<mxfile><diagram/></mxfile>') throw new Error('project xml rejected');
for (const invalid of [
  () => validateExportDataUri('javascript:alert(1)', 'svg'),
  () => validateExportDataUri('data:image/svg+xml;base64,%%%=', 'svg'),
  () => validateExportDataUri(png, 'svg'),
  () => validateDiagramXml('<svg></svg>'),
]) {{
  let rejected = false;
  try {{ invalid(); }} catch (_) {{ rejected = true; }}
  if (!rejected) throw new Error('unsafe export payload accepted');
}}
console.log('ok');
"""
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
