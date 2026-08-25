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
    assert "event.origin !== EDITOR_ORIGIN" in app_js
    assert "event.source !== elements.frame.contentWindow" in app_js
    assert 'format: "xml"' not in app_js
    assert "validateExportDataUri(message.data, wanted)" in app_js
    assert "saveDraft(validateDiagramXml(message.xml))" in app_js
    assert "KI-Ergebnis hier einfügen" in (output / "index.html").read_text(encoding="utf-8")


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
