"""Read-only D2/TALA preview: source integrity, passive SVG and HTTP admission."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.d2_preview import (
    D2PreviewError,
    _assert_passive_svg,
    _d2_quoted,
    _probe_binary,
    configured_binary,
    d2_source,
    render_d2_tala,
)
from schauwerk.visual.representation import validate_representation_input
from schauwerk.visual.standalone_editor import (
    _EditorRequestHandler,
    build_standalone_editor,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/decision-flow-v1.json"
D2_BINARY = os.environ.get("SCHAUWERK_D2_PREVIEW_BINARY", "")


def model() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_compiler_preserves_source_text_including_literal_variable_syntax() -> None:
    src = model()
    literal = "$" + "{unexpanded_variable}"
    src["nodes"][0]["label"] = 'Test "zitiert" & ' + literal
    src["nodes"][0]["summary"] = "Schrägstrich \\ & Unicode ä 🧪"
    src["edges"][0]["label"] = "Weg " + literal
    normalized = validate_representation_input(src)
    d2 = d2_source(normalized)
    assert _d2_quoted(literal) == '"' + "\\" + literal + '"'
    assert d2.count("\\" + literal) == 2
    assert "Schrägstrich" in d2
    assert normalized["nodes"][0]["label"] == src["nodes"][0]["label"]


@pytest.mark.parametrize(
    "malicious",
    [
        '<script>alert(1)</script>',
        '<foreignObject><p xmlns="http://www.w3.org/1999/xhtml">X</p></foreignObject>',
        '<g onclick="evil()"/>',
        '<a href="https://outside.example"><g/></a>',
        '<style>@import url(https://outside.example/style.css)</style>',
        '<rect fill="url(https://outside.example/x)"/>',
        '<style>.x { font-family: url(data:text/html;base64,PGgxPkJBRDwvaDE+); }</style>',
        '<style>.x { font-family: url(data:image/svg+xml;base64,PHN2Zy8+); }</style>',
        '<rect fill="url(data:text/html;base64,PGgxPkJBRDwvaDE+)"/>',
        '<rect fill="url(data:image/svg+xml;base64,PHN2Zy8+)"/>',
    ],
)
def test_passive_svg_rejects_active_or_external_content(malicious: str) -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" data-d2-version="v0.9.0">'
        + malicious + "</svg>"
    ).encode("utf-8")
    with pytest.raises(D2PreviewError):
        _assert_passive_svg(source)


@pytest.mark.parametrize(
    "location",
    [
        "#mk-d2-123",
        "data:application/font-woff;base64,d09GRgABAAAA",
        "data:font/woff;base64,d09GRgABAAAA",
    ],
)
def test_passive_svg_preserves_d2_embedded_fonts_and_local_urls(location: str) -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" data-d2-version="v0.9.0">'
        + f'<style>.x {{ font-family: url({location}); }}</style>'
        + f'<rect fill="url({location})"/>'
        + "</svg>"
    ).encode("utf-8")
    _assert_passive_svg(source)


def test_preview_requires_explicit_pinned_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHAUWERK_D2_PREVIEW_BINARY", raising=False)
    assert configured_binary() is None
    monkeypatch.setenv("SCHAUWERK_D2_PREVIEW_BINARY", "/does/not/exist")
    assert configured_binary() is None


def test_preview_rejects_wrong_binary_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "d2"
    marker.write_bytes(b"not an actual binary")
    marker.chmod(0o700)
    _probe_binary.cache_clear()

    class Incorrect:
        returncode = 0
        stdout = b"v0.8.0"

    import schauwerk.visual.d2_preview as preview

    monkeypatch.setattr(preview.subprocess, "run", lambda *_a, **_kw: Incorrect())
    assert _probe_binary(str(marker)) is None
    _probe_binary.cache_clear()


def _start_server(output: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = partial(_EditorRequestHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_preview_unconfigured_does_not_change_native_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCHAUWERK_D2_PREVIEW_BINARY", raising=False)
    output = tmp_path / "editor"
    build_standalone_editor(output, public_base_path="/schaubild")
    html = (output / "index.html").read_text(encoding="utf-8")
    app = (output / "app.js").read_text(encoding="utf-8")
    css = (output / "styles.css").read_text(encoding="utf-8")
    assert 'id="d2PreviewButton"' in html
    assert 'id="d2PreviewDialog"' in html
    assert "D2_CAPABILITIES_PATH" in app
    assert "D2_PREVIEW_API_PATH" in app
    assert "elements.d2PreviewDialog.showModal()" in app
    assert "d2PreviewController?.abort()" in app
    assert ".d2-preview-stage" in css

    server, thread = _start_server(output)
    connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
    try:
        connection.request("GET", "/api/renderer-capabilities")
        response = connection.getresponse()
        data = json.loads(response.read())
        assert response.status == 200
        assert data["schema_version"] == "schauwerk-renderer-capabilities.v1"
        assert data["renderers"] == []

        connection.request(
            "POST", "/api/d2-preview", body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        unavailable = connection.getresponse()
        assert unavailable.status == 503
        assert b"not available" in unavailable.read()

        source = json.dumps(model()).encode("utf-8")
        connection.request(
            "POST", "/api/native-viewer", body=source,
            headers={"Content-Type": "application/json"},
        )
        original = connection.getresponse()
        output_data = json.loads(original.read())
        assert original.status == 200
        assert output_data["renderer"] == "schauwerk-native-diagram-v1"
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("invalid_json", [b"{", b'{"renderer":'])
def test_d2_preview_malformed_json_returns_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_json: bytes,
) -> None:
    # Binary discovery succeeded; only the JSON admission path is under test.
    import schauwerk.visual.standalone_editor as editor
    monkeypatch.setattr(editor, "configured_d2_binary", lambda: Path("/not-executed/d2"))
    output = tmp_path / "editor"
    build_standalone_editor(output)
    server, thread = _start_server(output)
    connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=5)
    try:
        connection.request(
            "POST", "/api/d2-preview", body=invalid_json,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 422
        assert isinstance(payload.get("error"), str) and payload["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(
    not D2_BINARY or not Path(D2_BINARY).is_file(),
    reason="D2 v0.9.0 binary optional",
)
def test_real_d2_preview_retains_source_and_svg_structure() -> None:
    original = model()
    before = json.dumps(original, sort_keys=True)
    binary = configured_binary()
    assert binary is not None
    svg, digest = render_d2_tala(original, binary)
    root = ET.fromstring(svg)
    assert root.attrib["data-d2-version"] == "v0.9.0"
    assert digest == validate_representation_input(original)["input_digest"]
    assert json.dumps(original, sort_keys=True) == before


@pytest.mark.skipif(
    not D2_BINARY or not Path(D2_BINARY).is_file(),
    reason="D2 v0.9.0 binary optional",
)
def test_real_http_preview_is_read_only_and_digest_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHAUWERK_D2_PREVIEW_BINARY", D2_BINARY)
    source = model()
    output = tmp_path / "editor"
    build_standalone_editor(output)
    server, thread = _start_server(output)
    connection = HTTPConnection("127.0.0.1", int(server.server_address[1]), timeout=12)
    try:
        connection.request("GET", "/api/renderer-capabilities")
        response = connection.getresponse()
        catalog = json.loads(response.read())
        assert response.status == 200
        assert catalog["renderers"][0]["id"] == "d2-tala"
        assert catalog["renderers"][0]["read_only"] is True

        request = {
            "schema_version": "schauwerk-renderer-preview-request.v1",
            "renderer": "d2-tala",
            "representation": source,
        }
        data = json.dumps(request, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST", "/api/d2-preview", body=data,
            headers={"Content-Type": "application/json"},
        )
        svg_response = connection.getresponse()
        svg = svg_response.read()
        assert svg_response.status == 200, svg[:600]
        assert svg_response.getheader("Content-Type").startswith("image/svg+xml")
        assert svg_response.getheader("X-Schauwerk-Renderer") == "d2-tala-v0.9.0"
        assert re.fullmatch(
            "[0-9a-f]{64}", svg_response.getheader("X-Schauwerk-Output-SHA256")
        )
        assert svg_response.getheader("X-Schauwerk-Input-Digest") == (
            validate_representation_input(source)["input_digest"]
        )
        assert ET.fromstring(svg).attrib["data-d2-version"] == "v0.9.0"
        assert source == model()

        source["intent"] = "knowledge_map"
        data = json.dumps({**request, "representation": source}).encode()
        connection.request(
            "POST", "/api/d2-preview", body=data,
            headers={"Content-Type": "application/json"},
        )
        unsupported = connection.getresponse()
        assert unsupported.status == 422
        assert b"not available" in unsupported.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(
    not D2_BINARY or not Path(D2_BINARY).is_file(),
    reason="D2 v0.9.0 is required for browser E2E",
)
@pytest.mark.parametrize(("width", "height"), [(1280, 800), (390, 844)])
def test_real_browser_preview_preserves_original_native_workspace(
    tmp_path: Path, width: int, height: int,
) -> None:
    chrome = os.environ.get("SCHAUWERK_BROWSER_CHROME") or shutil.which("google-chrome")
    if not chrome or not Path(chrome).is_file():
        pytest.skip("local Chrome unavailable")
    output = tmp_path / "editor"
    build_standalone_editor(output)
    source = model()
    probe = r"""
const source = __SOURCE__;
const check = (condition, description) => { if (!condition) throw new Error(description); };
const until = async (checkReady) => {
  for (let n = 0; n < 200; n += 1) {
    if (checkReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 35));
  }
  throw new Error("D2 preview browser readiness timed out");
};
(async () => {
  const input = document.querySelector("#sourceInput");
  input.value = JSON.stringify(source);
  document.querySelector("#openPasteButton").click();
  const previewButton = document.querySelector("#d2PreviewButton");
  const previewDialog = document.querySelector("#d2PreviewDialog");
  const frame = document.querySelector("#editorFrame");
  await until(() => !previewButton.hidden
    && frame.contentDocument?.querySelector("#nativeViewport"));
  const originalFrameUrl = frame.getAttribute("src");
  const originalDraft = localStorage.getItem("schauwerk.native-schaubild.draft.v1");
  const undoDisabled = document.querySelector("#nativeUndoButton").disabled;
  previewButton.closest("details").open = true;
  previewButton.click();
  await until(() => previewDialog.open
    && document.querySelector("#d2PreviewImage").naturalWidth > 0);
  check(previewDialog.querySelector("img").src.startsWith("blob:"), "image blob missing");
  check(document.querySelector("#d2PreviewDownload").href.startsWith("blob:"),
    "SVG export missing");
  document.querySelector("#d2PreviewCloseButton").click();
  await until(() => !previewDialog.open);
  check(frame.getAttribute("src") === originalFrameUrl, "native frame was replaced");
  check(
    localStorage.getItem("schauwerk.native-schaubild.draft.v1") === originalDraft,
    "original draft changed during preview"
  );
  check(document.querySelector("#nativeUndoButton").disabled === undoDisabled,
    "native undo state changed during preview");
  document.documentElement.dataset.d2PreviewBrowserRegression = "pass";
})().catch((error) => {
  document.documentElement.dataset.d2PreviewBrowserRegression = "fail";
  document.documentElement.dataset.d2PreviewBrowserError = String(error?.message || error);
});
""".replace("__SOURCE__", json.dumps(source, ensure_ascii=False))
    (output / "d2-browser-smoke.js").write_text(probe, encoding="utf-8")
    index = output / "index.html"
    markup = index.read_text(encoding="utf-8")
    assert markup.count("</body>") == 1
    index.write_text(
        markup.replace(
            "</body>", '<script type="module" src="d2-browser-smoke.js"></script></body>',
        ),
        encoding="utf-8",
    )

    server, thread = _start_server(output)
    port = int(server.server_address[1])
    try:
        run = subprocess.run(
            [
                chrome, "--headless=new", "--no-first-run", "--disable-gpu",
                "--disable-dev-shm-usage", "--no-sandbox",
                "--run-all-compositor-stages-before-draw",
                f"--user-data-dir={tmp_path / 'chrome-profile'}",
                f"--window-size={width},{height}",
                "--virtual-time-budget=18000",
                "--dump-dom",
                f"http://127.0.0.1:{port}/",
            ],
            timeout=35,
            capture_output=True,
            check=False,
            text=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert run.returncode == 0, run.stderr[-2000:]
    assert 'data-d2-preview-browser-regression="pass"' in run.stdout, run.stdout[-3500:]