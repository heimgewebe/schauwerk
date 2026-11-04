# ruff: noqa: E501
from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.standalone_editor import _EditorRequestHandler, build_standalone_editor


def test_pdf_export_menu_and_browser_wiring(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    html = (output / "index.html").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")
    helper_js = (output / "canvas-import.js").read_text(encoding="utf-8")
    for entry in ('data-export="pdf"', 'data-export="png"', 'data-export="svg"', 'id="projectButton"'):
        assert entry in html
    assert "function jpegToPdfBlob(" in helper_js
    assert "async function renderedImageToPdfBlob(" in app_js
    assert "async function renderedImageToPngBlob(" in app_js
    assert "async function renderedImageToRasterCanvas(" in app_js
    assert 'pngButton.disabled = native' not in app_js
    assert 'pngButton.hidden = native' not in app_js
    assert 'PNG ist für dieses Schaubild noch nicht verfügbar' not in app_js
    assert 'format === "png" || format === "pdf"' in app_js
    assert 'wanted === "png" || wanted === "svg" || wanted === "pdf"' in app_js
    assert 'validateExportDataUri(message.data, wanted)' in app_js


def test_pdf_jpeg_blob_layout_and_xref(tmp_path: Path) -> None:
    if not shutil.which("node"):
        pytest.skip("node is not installed")

    from PIL import Image

    output = tmp_path / "editor"
    build_standalone_editor(output)
    js = (output / "canvas-import.js").read_bytes()
    module_url = "data:text/javascript;base64," + base64.b64encode(js).decode("ascii")
    image_buffer = io.BytesIO()
    Image.new("RGB", (4, 2), (250, 250, 250)).save(image_buffer, format="JPEG")
    jpeg64 = base64.b64encode(image_buffer.getvalue()).decode("ascii")

    code = """
import { jpegToPdfBlob } from __MODULE__;
const jpeg = Uint8Array.from(Buffer.from(__JPEG__, "base64"));
for (const [w, h, media] of [
  [1800, 900, "/MediaBox [0 0 1190.55 841.89]"],
  [900, 1800, "/MediaBox [0 0 841.89 1190.55]"]
]) {
  const blob = jpegToPdfBlob(jpeg, w, h);
  if (blob.type !== "application/pdf") throw new Error("wrong MIME");
  const data = Buffer.from(await blob.arrayBuffer());
  const text = data.toString("latin1");
  if (!text.startsWith("%PDF-1.4\\n") || !text.endsWith("%%EOF\\n"))
    throw new Error("invalid PDF header/footer");
  if (!text.includes(media) || !text.includes("/Count 1")
      || !text.includes("/Width " + w + " /Height " + h)
      || !text.includes("/Filter /DCTDecode"))
    throw new Error("missing page/image metadata");
  if (data.indexOf(Buffer.from(jpeg)) < 0)
    throw new Error("JPEG stream not embedded");
  const match = /startxref\\n(\\d+)\\n%%EOF/.exec(text);
  if (!match || text.slice(Number(match[1]), Number(match[1]) + 5) !== "xref\\n")
    throw new Error("bad cross-reference pointer");
  const lines = text.slice(Number(match[1])).split("\\n");
  if (lines[1] !== "0 6") throw new Error("bad cross-reference count");
  for (let n = 1; n <= 5; n++) {
    const offset = Number(lines[n + 2].slice(0, 10));
    if (!text.startsWith(n + " 0 obj\\n", offset))
      throw new Error("wrong cross-reference offset: " + n);
  }
}
for (const invalid of [
  () => jpegToPdfBlob(Uint8Array.from([0, 1, 2, 3]), 4, 2),
  () => jpegToPdfBlob(jpeg, 0, 2),
  () => jpegToPdfBlob(jpeg, 9000, 2),
]) {
  try { invalid(); throw new Error("invalid input accepted"); }
  catch (error) { if (error.message === "invalid input accepted") throw error; }
}
""".replace("__MODULE__", repr(module_url)).replace("__JPEG__", repr(jpeg64))
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code],
        text=True, capture_output=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stderr[-1000:]


@pytest.mark.parametrize("width,height", [(1366, 900), (390, 844)])
@pytest.mark.parametrize("format_name", ["pdf", "png"])
def test_native_raster_export_real_chromium_download(
    tmp_path: Path, width: int, height: int, format_name: str,
) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("Raster export is covered on the Python 3.12 CI lane")

    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome is required for raster browser smoke")
        pytest.skip("Chrome is not installed")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    probe_js = r"""
const wait = async (predicate, label) => {
  for (let i = 0; i < 500; i++) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(label);
};
(async () => {
  const exportFormat = "__FORMAT__";
  const exportMime = exportFormat === "pdf" ? "application/pdf" : "image/png";
  let exportBlob = null;
  const originalCreate = URL.createObjectURL;
  URL.createObjectURL = (blob) => {
    if (blob.type === exportMime) exportBlob = blob;
    return originalCreate.call(URL, blob);
  };
  const input = {
    nodes: [
      {id: "a", type: "text", x: 0, y: 0, width: 260, height: 100, text: "Start"},
      {id: "b", type: "text", x: 350, y: 150, width: 250, height: 100, text: "Ende"}
    ],
    edges: [{id: "ab", fromNode: "a", toNode: "b", toEnd: "arrow", label: "Verbindung"}]
  };
  document.querySelector("#sourceInput").value = JSON.stringify(input);
  document.querySelector("#openPasteButton").click();
  await wait(() => {
    const frame = document.querySelector("#editorFrame");
    return !document.querySelector("#workspace").hidden
      && frame.contentDocument?.querySelector("#nativeDiagram");
  }, "native document did not load");
  const menu = document.querySelector(".workspace-export-menu");
  menu.open = true;
  const button = document.querySelector('[data-export="' + exportFormat + '"]');
  if (!button || button.hidden || button.disabled) throw new Error("Export action unavailable");
  const rect = button.getBoundingClientRect();
  const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
  if (rect.height < 40 || !hit || !(hit === button || button.contains(hit))) {
    throw new Error("Export action inaccessible");
  }
  button.click();
  await wait(() => {
    const download = document.querySelector("#downloadLink");
    return !download.hidden && download.download.endsWith("." + exportFormat) && exportBlob;
  }, "Native image download was not prepared");
  if (menu.open) throw new Error("Export selection did not close the menu");
  if (exportBlob.type !== exportMime || exportBlob.size < 100)
    throw new Error("Export MIME or image size invalid");
  const bytes = new Uint8Array(await exportBlob.arrayBuffer());
  if (exportFormat === "pdf") {
    const prefix = new TextDecoder().decode(bytes.slice(0, 9));
    if (!prefix.startsWith("%PDF-1.4")) throw new Error("PDF header missing");
    const contents = new TextDecoder("latin1").decode(bytes);
    if (!contents.includes("/Type /Page ")
        || !contents.includes("/MediaBox [0 0")
        || !contents.includes("/Count 1")
        || !contents.includes("/Filter /DCTDecode")) {
      throw new Error("PDF page/image stream missing");
    }
  } else {
    const magic = [137, 80, 78, 71, 13, 10, 26, 10];
    if (!magic.every((byte, i) => bytes[i] === byte)) throw new Error("PNG header missing");
    if (bytes.length < 24) throw new Error("PNG is truncated");
    const data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const width = data.getUint32(16);
    const height = data.getUint32(20);
    if (!(width > 0 && height > 0 && width <= 5200 && height <= 5200
          && width * height <= 16000000)) {
      throw new Error("PNG raster dimensions are invalid");
    }
  }
  document.documentElement.dataset.rasterExportSmoke = "pass";
})().catch((error) => {
  document.documentElement.dataset.rasterExportSmoke = "fail";
  document.documentElement.dataset.rasterExportError = String(error?.message || error);
});
""".replace("__FORMAT__", format_name)
    (output / "raster-export-smoke.js").write_text(probe_js, encoding="utf-8")
    index_path = output / "index.html"
    markup = index_path.read_text(encoding="utf-8")
    index_path.write_text(
        markup.replace("</body>", '<script type="module" src="raster-export-smoke.js"></script></body>'),
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_EditorRequestHandler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    chrome_env = dict(os.environ)
    chrome_env.update({
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
        "XDG_CACHE_HOME": str(tmp_path / "xdg-cache"),
    })
    try:
        result = subprocess.run(
            [
                chrome, "--headless=new",
                f"--user-data-dir={tmp_path / 'chrome-profile'}",
                "--no-first-run", "--disable-gpu", "--disable-dev-shm-usage",
                "--no-sandbox", "--run-all-compositor-stages-before-draw",
                f"--window-size={width},{height}",
                "--virtual-time-budget=20000", "--dump-dom",
                f"http://127.0.0.1:{server.server_address[1]}/",
            ],
            capture_output=True, text=True, timeout=90, env=chrome_env, check=False,
        )
        assert result.returncode == 0, result.stderr[-1800:]
        assert 'data-raster-export-smoke="pass"' in result.stdout, result.stdout[:2500]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

@pytest.mark.parametrize("format_name,mime", [
    ("pdf", "application/pdf"), ("png", "image/png"),
])
def test_pending_native_raster_is_discarded_after_document_switch(
    tmp_path: Path, format_name: str, mime: str,
) -> None:
    """An async conversion of diagram A must never become diagram B's download."""
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    output = tmp_path / "editor"
    build_standalone_editor(output)
    app = (output / "app.js").read_text(encoding="utf-8")
    invalidate = app[
        app.index("function invalidateLoadIntents()"):
        app.index("function setStatus(")
    ]
    native = app[
        app.index("async function exportNative(format)"):
        app.index("function exportDiagram(format)")
    ]
    assert "invalidateLoadIntents();" in app[
        app.index("function launchLegacy(load)"):app.index("function nativeTokenFromUrl(")
    ]
    assert "invalidateLoadIntents();" in app[
        app.index("async function launchNative(load, options = {})"):
        app.index("const preserveActiveFrame", app.index("async function launchNative("))
    ]
    change_event = app[
        app.index('if (message.event === "native-document-change")'):
        app.index('if (message.event === "native-document-rebuild")')
    ]
    assert "exportRequestVersion += 1;" in change_event
    assert "clearPreparedDownload();" in change_event

    code = r"""
let loadIntentGeneration = 0;
let exportRequestVersion = 0;
let editorReady = true;
let currentRepresentation = {title: "First"};
let currentNativeDocument = null;
let currentNativeCanvas = null;
let currentLegacyXml = null;
let currentNativeUrl = "/native/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html";
let currentTitle = "First";
let nativeCanvasRenderStale = false;
let prepared = null;
let pendingRaster = null;
function setStatus() {}
function clearPreparedDownload() { prepared = null; }
function prepareDownload(blob, filename, label) {
  prepared = {blob, filename, label};
}
function safeFilename(title) { return title; }
function serializeNativeFrameSvg() { return '<svg xmlns="http://www.w3.org/2000/svg"/>'; }
function nativeCanvasDiffersFromRendered() { return false; }
function renderedImageToPdfBlob() {
  return new Promise((resolve) => { pendingRaster = resolve; });
}
function renderedImageToPngBlob() {
  return new Promise((resolve) => { pendingRaster = resolve; });
}
""" + invalidate + native + r"""
const oldExport = exportNative("__FORMAT__");
if (typeof pendingRaster !== "function") throw new Error("first export did not begin");
invalidateLoadIntents();
currentTitle = "Second";
currentRepresentation = {title: "Second"};
pendingRaster(new Blob(["data"], {type: "__MIME__"}));
await oldExport;
if (prepared !== null) throw new Error("stale image attached to new document");

pendingRaster = null;
const newExport = exportNative("__FORMAT__");
if (typeof pendingRaster !== "function") throw new Error("second export did not begin");
pendingRaster(new Blob(["data"], {type: "__MIME__"}));
await newExport;
if (!prepared || prepared.filename !== "Second.__FORMAT__" || prepared.label !== "__LABEL__") {
  throw new Error("current raster export was incorrectly rejected");
}
"""
    code = (code.replace("__FORMAT__", format_name)
        .replace("__MIME__", mime).replace("__LABEL__", format_name.upper()))
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]
