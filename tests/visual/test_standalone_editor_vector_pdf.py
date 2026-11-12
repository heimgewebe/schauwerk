# ruff: noqa: E501
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest
from websockets.sync.client import connect

from schauwerk.visual.standalone_editor import _EditorRequestHandler, build_standalone_editor


def test_vector_pdf_print_is_separate_from_raster_download(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    html = (output / "index.html").read_text()
    css = (output / "styles.css").read_text()
    js = (output / "app.js").read_text()
    assert html.count('data-export="pdf"') == 1
    assert html.count('data-export="pdf-vector"') == 1
    assert 'PDF (Bild)' in html and 'PDF (Vektor)' in html
    assert 'body.schaubild-vector-print' in css
    assert 'body.schaubild-vector-print > svg' in css
    assert 'body.schaubild-vector-print > .print-instruction,' in css
    assert 'body.schaubild-vector-print > .print-button { display: none' in css
    assert 'function printNativeVectorPdf()' in js
    assert 'if (format === "pdf-vector")' in js
    assert 'printNativeVectorPdf();' in js
    assert 'new DOMParser().parseFromString(liveSvg, "image/svg+xml")' in js
    assert 'printDocument.importNode(vector, true)' in js
    assert 'manualPrint.addEventListener("click"' in js
    assert 'for (const element of [vector, ...vector.querySelectorAll("*")])' in js
    assert 'printWindow.print()' in js
    assert 'window.open("", "_blank")' in js
    assert '@page schauwerk-a3 { size: A3 landscape; margin: 8mm; }' in css
    assert 'page: schauwerk-a3;' in css
    assert 'max-height: 270mm;' in css
    assert 'body.schaubild-vector-print-tiled .print-tile-page' in css
    assert 'function planReadableA3Tiles(svg)' in js
    assert 'function buildReadableA3Tiles(printDocument, vector, plan)' in js
    assert 'A3-Lesefassung (' in js
    assert 'printDocument.body.classList.add("schaubild-vector-print-tiled")' in js
    assert 'renderedImageToPdfBlob(' in js  # existing image-PDF unaffected
    assert 'jpegToPdfBlob(bytes, canvas.width, canvas.height)' in js


def test_a3_readable_tile_plan_has_finite_limits(tmp_path: Path) -> None:
    if not shutil.which("node"):
        pytest.skip("Node.js is unavailable")
    output = tmp_path / "editor"
    build_standalone_editor(output)
    source = (output / "app.js").read_text(encoding="utf-8")
    begin = source.index("function planReadableA3Tiles(svg) {")
    end = source.index("/** Only the print copy", begin)
    logic = source[begin:end]
    script = logic + """
const viewboxes = [
  "-546 -916 2909 2813", "0 0 900 700", "0 0 1000000 1000000",
  "0 0 -3 100", "0 0 NaN 100", "", "0 0 1850 1200"
];
const plans = viewboxes.map((value) => planReadableA3Tiles({
  getAttribute() { return value; }
}));
if (!plans[0] || plans[0].columns !== 2 || plans[0].rows !== 3
    || plans.slice(1).some((plan) => plan !== null)) {
  throw Error("A3 plan must reject invalid, small or excessive viewBoxes");
}
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_native_vector_pdf_print_browser_preserves_document(
    tmp_path: Path, width: int, height: int,
) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("browser print gate is exercised in Python 3.12 CI")
    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if chrome is None:
        pytest.skip("Chrome browser not available")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    script = r"""
const wait = async (pred, label) => {
  for (let n = 0; n < 400; n++) {
    if (pred()) return;
    await new Promise((done) => setTimeout(done, 35));
  }
  throw new Error("timeout: " + label);
};
(async () => {
  const input = {
    nodes: [
      {id: "start", type: "text", x: 0, y: 0, width: 230, height: 100, text: "Start"},
      {id: "end", type: "text", x: 320, y: 100, width: 230, height: 100, text: "Ziel"}
    ],
    edges: [{id: "flow", fromNode: "start", toNode: "end", label: "Verbindung"}]
  };
  await wait(() => document.querySelector("#openPasteButton"), "open button");
  await new Promise((done) => setTimeout(done, 150));
  document.querySelector("#sourceInput").value = JSON.stringify(input);
  document.querySelector("#openPasteButton").click();
  const frame = document.querySelector("#editorFrame");
  await wait(() => frame.contentDocument?.querySelector("#nativeViewport")
    && !document.querySelector("#workspace").hidden, "native viewport");
  const previousFrame = frame.getAttribute("src");
  const previousDraft = localStorage.getItem("schauwerk.native-schaubild.draft.v1");
  const previousUndo = document.querySelector("#nativeUndoButton").disabled;
  const originalOpen = window.open;
  const childDoc = document.implementation.createHTMLDocument("Vector-PDF-Test");
  const child = {document: childDoc, closed: false, opener: window,
    focused: false, printed: 0, focus() {this.focused = true;},
    print() {this.printed += 1;}};
  window.open = () => child;
  try {
    const button = document.querySelector('[data-export="pdf-vector"]');
    button.closest("details").open = true;
    button.click();
    await wait(() => childDoc.body.querySelector("svg"), "vector SVG");
    const link = childDoc.querySelector("link[rel=stylesheet]");
    if (!link) throw new Error("print stylesheet missing");
    link.dispatchEvent(new Event("load"));
    await wait(() => child.printed === 1, "print call");
    const fallbackButton = childDoc.body.querySelector("button.print-button");
    if (!fallbackButton) throw new Error("manual Safari print fallback missing");
    fallbackButton.click();
    await wait(() => child.printed === 2, "manual print call");
    const svg = childDoc.body.querySelector("svg");
    if (svg.namespaceURI !== "http://www.w3.org/2000/svg"
        || svg.querySelector("image, script, foreignObject")
        || !svg.querySelector("rect")
        || !svg.querySelector("text")) {
      throw new Error("pure vector SVG missing");
    }
    if (!child.focused || child.opener !== null) throw new Error("print popup not isolated");
    if (!document.body.textContent.includes("Vektor-PDF: Im Druckdialog")) {
      throw new Error("print workflow explanation missing");
    }
    if (frame.getAttribute("src") !== previousFrame
        || localStorage.getItem("schauwerk.native-schaubild.draft.v1") !== previousDraft
        || document.querySelector("#nativeUndoButton").disabled !== previousUndo) {
      throw new Error("native state changed during vector PDF print");
    }
    window.open = () => null;
    button.click();
    await wait(() => document.body.textContent.includes("Druckfenster blockiert"),
      "blocked popup feedback");

    // A very dense SVG must offer readable A3 details without silently
    // changing the original source, and it must wait for an explicit choice.
    const sourceSvg = frame.contentDocument.querySelector("#nativeDiagram");
    const originalViewBox = sourceSvg.getAttribute("viewBox");
    sourceSvg.setAttribute("viewBox", "-546 -916 2909 2813");
    const denseDoc = document.implementation.createHTMLDocument("A3-Details");
    const denseWindow = {document: denseDoc, closed: false, opener: window,
      printed: 0, focus() {}, print() {this.printed += 1;}};
    window.open = () => denseWindow;
    try {
      button.click();
      await wait(() => denseDoc.body.querySelector(".print-button")
        && denseDoc.body.querySelectorAll("svg").length === 1,
        "dense vector print window");
      const detailButton = [...denseDoc.body.querySelectorAll("button")]
        .find((item) => item.textContent === "A3-Lesefassung (6 Seiten)");
      if (!detailButton || denseWindow.printed !== 0) {
        throw new Error("dense print did not offer an explicit A3 detail choice");
      }
      detailButton.click();
      await wait(() => denseDoc.body.querySelectorAll(".print-tile-page svg").length === 6
        && denseWindow.printed === 1, "six A3 vector pages");
      const sheets = [...denseDoc.body.querySelectorAll(".print-tile-page svg")];
      if (new Set(sheets.map((sheet) => sheet.getAttribute("viewBox"))).size !== 6
          || sheets.some((sheet) => !sheet.querySelector("text")
            || sheet.querySelector("image, script, foreignObject"))) {
        throw new Error("A3 print pages are missing passive vector content");
      }
      if (sourceSvg.getAttribute("viewBox") !== "-546 -916 2909 2813"
          || frame.getAttribute("src") !== previousFrame
          || localStorage.getItem("schauwerk.native-schaubild.draft.v1") !== previousDraft
          || document.querySelector("#nativeUndoButton").disabled !== previousUndo) {
        throw new Error("readable A3 print changed editor state");
      }
      denseDoc.body.querySelector("button.print-button").click();
      await wait(() => denseWindow.printed === 2
        && !denseDoc.body.classList.contains("schaubild-vector-print-tiled"),
        "overview print remains available");
    } finally {
      if (originalViewBox === null) sourceSvg.removeAttribute("viewBox");
      else sourceSvg.setAttribute("viewBox", originalViewBox);
    }
    document.documentElement.dataset.vectorPdfPrintRegression = "pass";
  } finally {
    window.open = originalOpen;
  }
})().catch((error) => {
  document.documentElement.dataset.vectorPdfPrintRegression = "fail";
  document.documentElement.dataset.vectorPdfPrintError = String(error?.message || error);
});
"""
    (output / "vector-pdf-smoke.js").write_text(script)
    index = output / "index.html"
    markup = index.read_text()
    assert markup.count("</body>") == 1
    index.write_text(markup.replace(
        "</body>", '<script type="module" src="vector-pdf-smoke.js"></script></body>'
    ))
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_EditorRequestHandler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome-profile"
    proc = subprocess.Popen(
        [
            chrome, "--headless=new", "--no-first-run", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-sandbox",
            "--disable-background-networking",
            "--remote-allow-origins=http://localhost",
            "--remote-debugging-port=0", f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail("Chrome exited before CDP startup")
            try:
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    tab = next(
                        (item for item in json.load(response) if item.get("type") == "page"),
                        None,
                    )
                if tab:
                    break
            except (OSError, ValueError, IndexError, TimeoutError):
                pass
            time.sleep(0.12)
        assert tab is not None, "Chrome CDP endpoint failed to launch"
        with connect(tab["webSocketDebuggerUrl"], origin="http://localhost") as ws:
            next_id = 0

            def cdp(method: str, parameters: dict | None = None) -> dict:
                nonlocal next_id
                next_id += 1
                request_id = next_id
                ws.send(json.dumps({
                    "id": request_id, "method": method, "params": parameters or {},
                }))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    message = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
                    if message.get("id") == request_id:
                        assert "error" not in message, message.get("error")
                        return message.get("result", {})
                raise AssertionError("CDP request timed out: " + method)

            cdp("Page.enable")
            cdp("Runtime.enable")
            cdp("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 500,
            })
            cdp("Page.navigate", {"url": f"http://127.0.0.1:{server.server_address[1]}/"})
            outcome = {}
            for _ in range(160):
                evaluated = cdp("Runtime.evaluate", {
                    "expression": (
                        "({state:document.documentElement.dataset.vectorPdfPrintRegression||'',"
                        "error:document.documentElement.dataset.vectorPdfPrintError||''})"
                    ),
                    "returnByValue": True,
                })
                outcome = evaluated.get("result", {}).get("value", {})
                if outcome.get("state") == "fail":
                    pytest.fail("Vector PDF E2E: " + str(outcome.get("error")))
                if outcome.get("state") == "pass":
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Vector PDF E2E CDP timed out: " + str(outcome))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=6)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
