from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

from schauwerk.visual.native_document import json_canvas_to_editing_document
from schauwerk.visual.native_viewer import build_native_viewer


def test_native_canvas_edge_labels_on_demand_in_chrome(tmp_path: Path) -> None:
    """Real Chrome evaluates computed label visibility, touch selection and unchanged source."""
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("Chrome unavailable for native edge-label UI regression")
        pytest.skip("Chrome unavailable for native edge-label UI regression")

    source = {
        "nodes": [
            {"id": "alpha", "type": "text", "x": 0, "y": 0, "width": 180,
             "height": 90, "text": "Erste Handlung"},
            {"id": "beta", "type": "text", "x": 460, "y": 0, "width": 180,
             "height": 90, "text": "Zweite Handlung"},
        ],
        "edges": [
            {"id": "e1", "fromNode": "alpha", "toNode": "beta",
             "label": "Verbindung bleibt lesbar", "toEnd": "arrow"}
        ],
    }
    output = tmp_path / "native-labels"
    build_native_viewer(json_canvas_to_editing_document(source), output)
    path = output / "index.html"
    html = path.read_text(encoding="utf-8")
    script = r"""
<script type="module">
const result = document.documentElement.dataset;
const finish = (state, why = "") => {result.labelProbe = state; result.labelProbeError = why;};
const wait = ms => new Promise(resolve=>setTimeout(resolve,ms));
try {
  for (let i=0;i<150 &&
       !document.querySelector("#nativeCanvas")?.style.transform.includes("scale(");i++) {
    await wait(20);
  }
  const host = document.querySelector("#nativeCanvas");
  const svg = document.querySelector("#nativeDiagram");
  const edge = svg?.querySelector('[data-source-kind="edge"][data-source-id="e1"]');
  const label = edge?.querySelector(":scope > text");
  const plate = edge?.querySelector(":scope > rect");
  const line = edge?.querySelector(":scope > path:not(.native-edge-hit)");
  const toggle = document.querySelector("#labelsOnDemand");
  const model = document.querySelector("#nativeModel")?.textContent;
  const viewBox = svg?.getAttribute("viewBox");
  const check = (okay, text) => { if (!okay) throw Error(text); };
  check(window.innerWidth === 390, "Chrome viewport is not 390 CSS px: " + innerWidth);
  check(host && svg && edge && plate && label && line &&
    toggle instanceof HTMLButtonElement, "Canvas/label/toggle DOM missing");
  check(!host.classList.contains("is-labels-on-demand") &&
    toggle.getAttribute("aria-pressed")==="false", "Opt-in must be off by default");
  check(getComputedStyle(label).opacity==="1" &&
    getComputedStyle(plate).opacity==="1", "Default labels not shown");
  toggle.click();
  check(toggle.getAttribute("aria-pressed")==="true" &&
    host.classList.contains("is-labels-on-demand"), "Toggle did not enable");
  check(getComputedStyle(label).opacity==="0" &&
    getComputedStyle(plate).opacity==="0", "Inactive label is still visible");
  check(getComputedStyle(line).stroke !== "none" &&
    Boolean(edge.querySelector("title")?.textContent) &&
    Boolean(edge.querySelector("path.native-edge-hit")),
    "Line, title or hit target was lost");
  check(!svg.classList.contains("is-labels-on-demand") &&
    !new XMLSerializer().serializeToString(svg).includes("is-labels-on-demand"),
    "Transient label mode leaked into SVG export source");
  const viewport = document.querySelector("#nativeViewport");
  viewport.setPointerCapture = () => {};
  viewport.releasePointerCapture = () => {};
  line.dispatchEvent(new PointerEvent("pointerdown", {
    bubbles:true, cancelable:true, pointerId:23, pointerType:"touch", button:0
  }));
  check(edge.classList.contains("is-selected"), "Touch-style pointer did not select edge");
  check(getComputedStyle(label).opacity==="1" &&
    getComputedStyle(plate).opacity==="1", "Selected edge label not revealed");
  // HTML preview uses observation mode, so edge selection is unavailable.
  // Native label filtering must not hide every HTML edge chip permanently.
  const preview = document.querySelector("#hybridPreview");
  check(preview instanceof HTMLButtonElement && !preview.hidden,
    "HTML preview control unavailable");
  preview.click();
  const htmlLabel = document.querySelector('.hybrid-edge-label[data-source-id="e1"]');
  check(preview.getAttribute("aria-pressed")==="true" &&
    htmlLabel instanceof HTMLElement, "HTML preview edge label missing");
  check(getComputedStyle(htmlLabel).opacity==="1" &&
    getComputedStyle(htmlLabel).display!=="none" &&
    htmlLabel.getClientRects().length>0,
    "On-demand native label mode hid read-only HTML preview label");
  check(toggle.disabled, "Unavailable label toggle remains actionable in HTML preview");
  preview.click();
  check(!toggle.disabled && host.classList.contains("is-labels-on-demand"),
    "Native label mode did not recover after preview");
  toggle.click();
  check(toggle.getAttribute("aria-pressed")==="false" &&
    getComputedStyle(label).opacity==="1", "Switching off did not restore labels");
  check(document.querySelector("#nativeModel").textContent === model &&
    svg.getAttribute("viewBox") === viewBox,
    "View-only mode changed source model or geometry");
  finish("pass");
} catch(e) { finish("fail", String(e && (e.stack || e.message) || e)); }
</script>
"""
    assert html.count("</body>") == 1
    path.write_text(html.replace("</body>", script + "\n</body>"), encoding="utf-8")
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass
    handler = partial(QuietHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from websockets.sync.client import connect

    profile = tmp_path / "chrome-profile"
    debugger_file = profile / "DevToolsActivePort"
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--no-first-run", "--no-sandbox",
         "--disable-gpu", "--disable-dev-shm-usage",
         "--remote-allow-origins=http://localhost", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(100):
            try:
                port = int(debugger_file.read_text(encoding="utf-8").splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    tab = next(
                        (row for row in json.load(response) if row.get("type") == "page"),
                        None,
                    )
                if tab:
                    break
            except (OSError, TimeoutError, ValueError, IndexError):
                pass
            time.sleep(0.12)
        assert tab is not None, "Chrome CDP endpoint did not become ready"
        with connect(tab["webSocketDebuggerUrl"], origin="http://localhost") as ws:
            request_id = 0

            def cdp(method: str, params: dict | None = None) -> dict:
                nonlocal request_id
                request_id += 1
                current_id = request_id
                ws.send(json.dumps({
                    "id": current_id, "method": method, "params": params or {},
                }))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    packet = json.loads(ws.recv(timeout=max(
                        0.1, deadline - time.monotonic(),
                    )))
                    if packet.get("id") == current_id:
                        assert "error" not in packet, packet.get("error")
                        return packet.get("result", {})
                raise AssertionError("Chrome CDP timeout: " + method)

            cdp("Page.enable")
            cdp("Runtime.enable")
            cdp("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844,
                "deviceScaleFactor": 1, "mobile": False,
            })
            cdp("Page.navigate", {
                "url": f"http://127.0.0.1:{server.server_address[1]}/index.html",
            })
            for _ in range(140):
                state = cdp("Runtime.evaluate", {
                    "expression": (
                        "({width:innerWidth,state:document.documentElement.dataset.labelProbe||'',"
                        "error:document.documentElement.dataset.labelProbeError||''})"
                    ),
                    "returnByValue": True,
                }).get("result", {}).get("value", {})
                if state.get("state") == "fail":
                    pytest.fail(str(state.get("error")))
                if state.get("state") == "pass":
                    assert state.get("width") == 390, state
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Native edge-label E2E did not finish at 390 CSS pixels")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
