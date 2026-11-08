"""Opt-in read-only HTML/SVG hybrid preview for native JSON Canvas documents."""
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest

from schauwerk.resources.native_viewer.assets import ASSETS, INDEX_HTML
from schauwerk.resources.native_viewer.hybrid_preview import HYBRID_PREVIEW_JS
from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import json_canvas_to_editing_document
from schauwerk.visual.native_viewer import _content_security_policy, build_native_viewer
from schauwerk.visual.standalone_editor import _NATIVE_BUNDLE_FILES

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/system-landscape-v1.json"
HOSTILE_TEXT = '<img src=x onerror="window.__pwn=1">\nZweite Zeile & "Quote" </script><b>x</b>'
HOSTILE_LABEL = "Kante <script>window.__pwn=2</script> & Co"


def _canvas(routing: str) -> dict:
    return {
        "nodes": [
            {"id": "a", "type": "text", "x": 30, "y": 60, "width": 160, "height": 110,
             "text": HOSTILE_TEXT},
            {"id": "b", "type": "text", "x": 520, "y": 65, "width": 140, "height": 90,
             "text": "B", "color": "4"},
            {"id": "blocker", "type": "text", "x": 280, "y": 210, "width": 140,
             "height": 90, "text": "Blocker"},
            {"id": "g", "type": "group", "x": 0, "y": 340, "width": 330, "height": 170,
             "label": "Gruppe"},
        ],
        "edges": [
            {"id": "e", "fromNode": "a", "toNode": "b", "label": HOSTILE_LABEL,
             "toEnd": "arrow"},
            {"id": "plain", "fromNode": "b", "toNode": "blocker", "toEnd": "arrow"},
        ],
        "schauwerk": {"edgeRouting": routing},
    }


def _chrome() -> str:
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("Google Chrome required for the hybrid preview acceptance")
        pytest.skip("Chrome unavailable")
    return chrome


PROLOGUE_JS = (
    "Element.prototype.setPointerCapture = function() {};\n"
    "Element.prototype.releasePointerCapture = function() {};\n"
)
PROLOGUE = '<script src="prologue.js"></script>\n'
MARKER = '<script type="module" src="app.js"></script>'


def _install_probe(output: Path, probe: str | None) -> None:
    """Add the pointer-capture stub (and an optional probe) as same-origin scripts."""
    (output / "prologue.js").write_text(PROLOGUE_JS, encoding="utf-8")
    tail = ""
    if probe is not None:
        (output / "probe.js").write_text(probe, encoding="utf-8")
        tail = '\n<script type="module" src="probe.js"></script>'
    index = output / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8").replace(MARKER, PROLOGUE + MARKER + tail),
        encoding="utf-8",
    )

PROBE_COMMON = r"""
const HOSTILE = __HOSTILE__;
const failures = [];
const check = (name, ok, detail) => { if (!ok) failures.push(name + (detail === undefined ? "" : " " + JSON.stringify(detail))); };
const wait = async (predicate, description) => {
  for (let i = 0; i < 300; ++i) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error("timed out waiting for " + description);
};
const settle = () => new Promise(resolve => setTimeout(resolve, 60));
const done = () => {
  document.documentElement.dataset.hybridResult = encodeURIComponent(JSON.stringify(failures));
};
const fire = (win, target, type, id, x, y) => target.dispatchEvent(
  new win.PointerEvent(type, {
    bubbles: true, pointerId: id, pointerType: "mouse", clientX: x, clientY: y,
    button: 0, buttons: type === "pointerup" ? 0 : 1, isPrimary: true,
  })
);
const centerOf = (rect) => [(rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2];
"""

# The probe runs against `doc`/`win`, which are either this page (standalone)
# or the embedded viewer frame (hosted).
PROBE_BODY = r"""
async function probe(doc, win, hosted, routing) {
  const viewport = doc.querySelector("#nativeViewport");
  const canvas = doc.querySelector("#nativeCanvas");
  const svg = doc.querySelector("#nativeDiagram");
  const button = doc.querySelector("#hybridPreview");
  const modeMenu = doc.querySelector(".view-mode-controls");
  const modeSummary = modeMenu?.querySelector("summary");
  const visible = (element) => {
    if (!(element instanceof win.HTMLElement)) return false;
    const rect = element.getBoundingClientRect();
    const style = win.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 &&
      style.display !== "none" && style.visibility !== "hidden" &&
      rect.top >= 0 && rect.bottom <= win.innerHeight &&
      rect.left >= 0 && rect.right <= win.innerWidth;
  };
  const activateVisible = async (element, name) => {
    check(name + " visible", visible(element));
    if (!visible(element)) throw new Error(name + " is inaccessible");
    const [x, y] = centerOf(element.getBoundingClientRect());
    const hit = doc.elementFromPoint(x, y);
    check(name + " hit-test", hit === element || element.contains(hit),
      hit?.tagName + "." + hit?.className);
    if (hit !== element && !element.contains(hit)) throw new Error(name + " is covered");
    hit.click();
    await settle();
  };
  const chooseMode = async () => {
    if (!modeMenu?.open) await activateVisible(modeSummary, "view menu summary");
    check("view menu open", modeMenu?.open === true);
    await activateVisible(button, "view mode toggle");
  };
  const model = JSON.parse(doc.querySelector("#nativeModel").textContent);
  await wait(() => canvas.style.transform.includes("scale("), "viewer startup");
  await settle();

  // --- Native stays the default; the preview is an explicit, labelled opt-in.
  check("view mode menu accessible initially", modeMenu && !modeMenu.hidden && visible(modeSummary));
  check("view mode menu uses shared compact styles", modeMenu.querySelector(".view-mode-menu") !== null);
  check("button enabled for preview", button && !button.hidden && !button.disabled);
  check("button labelled as preview", /Vorschau/.test(button.textContent) && /schreibgesch/.test(button.getAttribute("aria-label") + button.title));
  check("button off by default", button.getAttribute("aria-pressed") === "false");
  check("no layer by default", !doc.querySelector(".hybrid-layer"));
  check("no active class by default", !canvas.classList.contains("hybrid-preview-active"));
  check("native svg text visible by default", win.getComputedStyle(svg.querySelector("[data-node-label]")).visibility === "visible");
  // The existing viewer rescales the invisible edge hit width with zoom; nothing else may differ.
  const svgState = () => svg.outerHTML.replace(/stroke="transparent" stroke-width="[\d.]+"/g, 'stroke="transparent"');
  const svgBefore = svgState();
  const dBefore = [...svg.querySelectorAll('[data-source-kind="edge"] > path:not(.native-edge-hit)')].map(p => p.getAttribute("d"));
  const nodeTransformsBefore = [...svg.querySelectorAll('[data-source-kind="node"]')].map(n => n.getAttribute("transform"));

  // --- Opt in.
  await chooseMode();
  const layer = doc.querySelector(".hybrid-layer");
  check("layer created inside shared canvas", layer && layer.parentElement === canvas);
  check("button reverts to native", /Native/.test(button.textContent) && button.getAttribute("aria-pressed") === "true");
  check("observation toggle locked", doc.querySelector("#observationMode").disabled);
  check("status says read only", /schreibgesch/.test(doc.querySelector("#status").textContent));
  check("footer states native authority", /Native bleibt ma/.test(doc.querySelector("#authorityHint").textContent));
  check("viewport is in view-only mode", viewport.classList.contains("is-observing"));
  check("edit menu closed", doc.querySelector(".edit-controls").hidden);
  check("view menu survives observation mode", visible(modeSummary) && !modeMenu.hidden);
  check("view menu reflects HTML mode", modeSummary.textContent === "HTML");
  check("native svg text hidden", win.getComputedStyle(svg.querySelector("[data-node-label]")).visibility === "hidden");

  // --- DOM labels come from the validated model, as text only.
  for (const item of model.nodes) {
    const element = layer.querySelector('.hybrid-node[data-source-id="' + item.id + '"] .hybrid-node-text');
    check("node text " + item.id, element && element.textContent === item.label, element && element.textContent);
    check("node id bound " + item.id, !!svg.querySelector('[data-source-kind="node"][data-source-id="' + item.id + '"]'));
  }
  for (const item of model.edges) {
    const chip = layer.querySelector('.hybrid-edge-label[data-source-id="' + item.id + '"]');
    if (item.label) check("edge label " + item.id, chip && chip.textContent === item.label, chip && chip.textContent);
    else check("no chip for unlabeled edge", !chip);
  }
  check("no foreign markup became elements", layer.querySelectorAll("img,script,b,svg,style,a").length === 0);
  check("no script side effect", win.__pwn === undefined);
  check("only expected classes", [...layer.querySelectorAll("*")].every(e => /^hybrid-/.test(e.className)));
  check("layer is read only", layer.querySelectorAll("[contenteditable],input,textarea,button").length === 0);

  // --- SVG curves/arrows stay exactly what the router produced.
  const dDuring = [...svg.querySelectorAll('[data-source-kind="edge"] > path:not(.native-edge-hit)')].map(p => p.getAttribute("d"));
  check("svg edge paths unchanged", JSON.stringify(dBefore) === JSON.stringify(dDuring));
  check("svg bytes unchanged in preview", svgState() === svgBefore);
  check("svg arrows retained", !!svg.querySelector("marker") && !!svg.querySelector("path[marker-end]"));
  check("edge routing mode preserved", model.source.schauwerk.edgeRouting === routing);

  // --- One transformation matrix: DOM boxes equal SVG boxes at every view.
  const parity = (label) => {
    const origin = svg.getBoundingClientRect();
    const layerRect = layer.getBoundingClientRect();
    check(label + " layer origin", Math.abs(layerRect.left - origin.left) < 0.6 && Math.abs(layerRect.top - origin.top) < 0.6, [layerRect.toJSON(), origin.toJSON()]);
    check(label + " layer scale", Math.abs(layerRect.width - origin.width) < 0.6, [layerRect.width, origin.width]);
    for (const item of model.nodes) {
      const dom = layer.querySelector('.hybrid-node[data-source-id="' + item.id + '"]').getBoundingClientRect();
      const shape = svg.querySelector('[data-source-kind="node"][data-source-id="' + item.id + '"] > rect').getBoundingClientRect();
      check(label + " node box " + item.id, Math.abs(dom.left - shape.left) < 2.2 && Math.abs(dom.top - shape.top) < 2.2 && Math.abs(dom.width - shape.width) < 2.6 && Math.abs(dom.height - shape.height) < 2.6, [dom.toJSON(), shape.toJSON()]);
    }
    const labelShape = svg.querySelector('[data-source-kind="edge"][data-source-id="e"] > rect').getBoundingClientRect();
    const chip = layer.querySelector('.hybrid-edge-label[data-source-id="e"]').getBoundingClientRect();
    check(label + " edge label box", Math.abs(chip.left - labelShape.left) < 1.6 && Math.abs(chip.top - labelShape.top) < 1.6 && Math.abs(chip.width - labelShape.width) < 1.6, [chip.toJSON(), labelShape.toJSON()]);
  };
  parity("initial");

  // --- Zoom and pan keep both layers locked together.
  const scaleOf = () => Number(/scale\(([^)]+)\)/.exec(canvas.style.transform)[1]);
  const translateOf = () => /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(canvas.style.transform).slice(1).map(Number);
  const scale0 = scaleOf();
  doc.querySelector("#zoomIn").click();
  doc.querySelector("#zoomIn").click();
  await settle();
  check("zoom changed", scaleOf() > scale0 * 1.2, [scale0, scaleOf()]);
  parity("zoomed");
  const translate0 = translateOf();
  const bar = doc.querySelector(".viewer-bar").getBoundingClientRect();
  const sx = win.innerWidth / 2, sy = Math.min(win.innerHeight - 90, bar.bottom + 40);
  fire(win, viewport, "pointerdown", 7, sx, sy);
  fire(win, viewport, "pointermove", 7, sx - 70, sy - 40);
  fire(win, viewport, "pointerup", 7, sx - 70, sy - 40);
  await settle();
  const translate1 = translateOf();
  check("pan moved view", Math.abs(translate1[0] - (translate0[0] - 70)) < 1.5 && Math.abs(translate1[1] - (translate0[1] - 40)) < 1.5, [translate0, translate1]);
  parity("panned");

  // --- Drag on node text pans; it must not mutate the document.
  const nodeText = layer.querySelector('.hybrid-node[data-source-id="blocker"] .hybrid-node-text');
  const [nx, ny] = centerOf(nodeText.getBoundingClientRect());
  fire(win, nodeText, "pointerdown", 8, nx, ny);
  fire(win, viewport, "pointermove", 8, nx + 60, ny + 30);
  fire(win, viewport, "pointerup", 8, nx + 60, ny + 30);
  await settle();
  const transformsDuring = [...svg.querySelectorAll('[data-source-kind="node"]')].map(n => n.getAttribute("transform"));
  check("node drag locked", JSON.stringify(transformsDuring) === JSON.stringify(nodeTransformsBefore), transformsDuring);
  check("no node selected in preview", !svg.querySelector(".is-selected"));
  parity("after locked drag");
  const keyTarget = svg.querySelector('[data-source-kind="node"][data-source-id="a"]');
  keyTarget.dispatchEvent(new win.KeyboardEvent("keydown", {key: "Enter", bubbles: true}));
  win.dispatchEvent(new win.KeyboardEvent("keydown", {key: "z", ctrlKey: true, bubbles: true}));
  check("keyboard selection locked", !svg.querySelector(".is-selected"));
  doc.querySelector("#observationMode").click();
  check("observation toggle cannot unlock", doc.querySelector("#observationMode").disabled && viewport.classList.contains("is-observing"));
  check("svg bytes unchanged after gestures", svgState() === svgBefore);

  // --- Live geometry: a moved SVG label moves the chip and is never covered by a node.
  const labelRect = svg.querySelector('[data-source-kind="edge"][data-source-id="e"] > rect');
  // Prefer an unobscured foreign node over the top toolbar on short landscape screens.
  const bNode = svg.querySelector('[data-source-kind="node"][data-source-id="blocker"] > rect');
  const bx = Number(bNode.getAttribute("x")), by = Number(bNode.getAttribute("y"));
  const lx = Number(labelRect.getAttribute("x")), ly = Number(labelRect.getAttribute("y"));
  const savedTransform = labelRect.getAttribute("transform");
  labelRect.setAttribute("transform", "translate(" + (bx + 8 - lx) + " " + (by + 8 - ly) + ")");
  await settle();
  const chipEl = layer.querySelector('.hybrid-edge-label[data-source-id="e"]');
  const [cx, cy] = centerOf(chipEl.getBoundingClientRect());
  const stack = doc.elementsFromPoint(cx, cy);
  check("moved label chip follows live svg geometry", Math.abs(chipEl.getBoundingClientRect().left - labelRect.getBoundingClientRect().left) < 1.6);
  check("label chip over foreign node", stack[0] === chipEl || chipEl.contains(stack[0]), stack.slice(0, 4).map(e => e.tagName + "." + (e.className.baseVal ?? e.className)));
  check("chip is above every node text", doc.defaultView.getComputedStyle(chipEl).zIndex === "2");
  if (savedTransform === null) labelRect.removeAttribute("transform"); else labelRect.setAttribute("transform", savedTransform);
  await settle();

  // --- Select and copy come from the DOM text.
  const selectBy = async (element) => {
    const [px, py] = centerOf(element.getBoundingClientRect());
    viewport.dispatchEvent(new win.MouseEvent("dblclick", {bubbles: true, clientX: px, clientY: py}));
    await settle();
    return win.getSelection().toString();
  };
  const nodeA = layer.querySelector('.hybrid-node[data-source-id="a"] .hybrid-node-text');
  check("user-select text on node", win.getComputedStyle(nodeA).userSelect === "text");
  check("node text selectable", (await selectBy(nodeA)) === HOSTILE, win.getSelection().toString());
  check("edge label selectable", (await selectBy(chipEl)) === model.edges[0].label, win.getSelection().toString());
  win.getSelection().removeAllRanges();

  // --- Hosted: a mutation reached the parent? (counted by the host page.)
  // --- Back to native: exact byte-level restoration.
  await chooseMode();
  check("layer removed", !doc.querySelector(".hybrid-layer"));
  check("active class removed", !canvas.classList.contains("hybrid-preview-active"));
  check("button native again", button.getAttribute("aria-pressed") === "false" && /^HTML-Vorschau$/.test(button.textContent));
  check("observation toggle free again", !doc.querySelector("#observationMode").disabled && doc.querySelector("#observationMode").getAttribute("aria-pressed") === "false");
  check("svg bytes restored", svgState() === svgBefore);
  check("svg text visible again", win.getComputedStyle(svg.querySelector("[data-node-label]")).visibility === "visible");
  check("no selection left", win.getSelection().toString() === "");
  // Opt in twice keeps working and leaves exactly one layer.
  await chooseMode(); await chooseMode();
  check("repeatable opt in", !doc.querySelector(".hybrid-layer") && svgState() === svgBefore);
  return failures;
}
"""

STANDALONE_PROBE = PROBE_COMMON + PROBE_BODY + r"""
(async () => {
  try {
    await probe(document, window, false, "__ROUTING__");
  } catch (error) {
    failures.push("exception " + String(error?.stack || error));
  }
  done();
})();
"""

HOST_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"></head><body style="margin:0">
<iframe id="viewer" style="display:block;width:100vw;height:100vh;border:0"></iframe>
<script>
""" + PROBE_COMMON + PROBE_BODY + r"""
const frame = document.querySelector("#viewer");
const events = [];
window.addEventListener("message", event => {
  if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
  events.push({event: event.data?.event, startup: event.data?.startup === true, enabled: event.data?.enabled});
});
(async () => {
  try {
    await wait(() => frame.contentDocument?.querySelector("#nativeCanvas")?.style?.transform.includes("scale("), "frame");
    await settle();
    const startupEvents = events.length;
    await probe(frame.contentDocument, frame.contentWindow, true, "__ROUTING__");
    const after = events.slice(startupEvents);
    const mutating = after.filter(e => /^native-document-/.test(e.event));
    check("no document mutation reached the host", mutating.length === 0, mutating);
    const modes = after.filter(e => e.event === "native-observation-mode").map(e => e.enabled);
    check("host history lock follows preview", modes[0] === true && modes[modes.length - 1] === false, modes);
  } catch (error) {
    failures.push("exception " + String(error?.stack || error));
  }
  done();
})();
frame.src = "index.html";
</script></body></html>"""


def _js(value: str) -> str:
    return json.dumps(value).replace("</", "<\\/")


def _probe(source: str, routing: str) -> str:
    return source.replace("__HOSTILE__", _js(HOSTILE_TEXT)).replace("__ROUTING__", routing)


def _serve(directory: Path):
    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            # The viewer document runs under the production CSP (no inline script/style).
            if self.path.split("?", 1)[0].endswith("index.html"):
                self.send_header("Content-Security-Policy", _content_security_policy())
            super().end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _run_chrome(tmp_path: Path, output: Path, page: str, width: int = 1120, height: int = 850) -> list[str]:
    server, thread = _serve(output)
    try:
        result = subprocess.run(
            [
                _chrome(), "--headless=new", f"--user-data-dir={tmp_path / 'chrome'}",
                "--no-first-run", "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox",
                "--run-all-compositor-stages-before-draw", f"--window-size={width},{height}",
                "--virtual-time-budget=20000", "--dump-dom",
                f"http://127.0.0.1:{server.server_address[1]}/{page}",
            ],
            capture_output=True, text=True, timeout=60, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr[-1000:]
    found = re.search(r'data-hybrid-result="([^"]*)"', result.stdout)
    assert found, result.stdout[:1500]
    return json.loads(unquote(found.group(1)))


def _build(tmp_path: Path, routing: str) -> Path:
    output = tmp_path / "viewer"
    build_native_viewer(json_canvas_to_editing_document(_canvas(routing)), output)
    assert (output / "index.html").read_text(encoding="utf-8").count(MARKER) == 1
    return output


# ---------------------------------------------------------------- contracts


def test_hybrid_preview_ships_as_bundle_file_without_changing_native_default(tmp_path: Path) -> None:
    model = json_canvas_to_editing_document(_canvas("smart"))
    output = tmp_path / "bundle"
    manifest = build_native_viewer(model, output)
    names = {item["path"] for item in manifest["files"]}
    assert "hybrid-preview.js" in names
    assert (output / "hybrid-preview.js").read_text(encoding="utf-8") == ASSETS["hybrid-preview.js"]
    assert _NATIVE_BUNDLE_FILES["hybrid-preview.js"] == "hybrid-preview.js"
    # Native SVG is byte-identical to the authoritative renderer: the preview adds nothing.
    assert (output / "diagram.svg").read_bytes() == render_native_editing_document(model).encode()
    index = (output / "index.html").read_text(encoding="utf-8")
    assert "hybrid-layer" not in index.split("<script", 1)[0]
    assert 'id="hybridPreview"' in index
    assert index.index('class="view-mode-menu"') < index.index('id="hybridPreview"')
    # Opt-in button starts hidden and unpressed until the viewer proves document support.
    button = re.search(r'<button id="hybridPreview"[^>]*>', INDEX_HTML)
    assert button and " hidden" in button.group(0) and 'aria-pressed="false"' in button.group(0)
    assert "Vorschau" in button.group(0)
    assert manifest["renderer_authority"]["bytes_modified_by_viewer"] is False


def test_hybrid_preview_module_has_no_markup_sink_network_or_write_path() -> None:
    forbidden = [
        "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
        "contenteditable", "fetch(", "XMLHttpRequest", "localStorage", "sessionStorage",
        "postMessage", "createContextualFragment", "DOMParser",
    ]
    for token in forbidden:
        assert token not in HYBRID_PREVIEW_JS, token
    assert "textContent" in HYBRID_PREVIEW_JS
    # The wiring never routes edges itself: geometry comes from the existing router/SVG.
    assert "smartEdgeGeometry" not in HYBRID_PREVIEW_JS
    assert "getModel" in HYBRID_PREVIEW_JS and "sourceModel" not in HYBRID_PREVIEW_JS
    app = ASSETS["app.js"]
    assert 'import { createHybridPreview, hybridPreviewSupported } from "./hybrid-preview.js"' in app
    assert "boundsInSvg: nodeBoundsInSvg" in app


# ---------------------------------------------------------------- real Chrome


@pytest.mark.parametrize("routing", ["smart", "simple"])
@pytest.mark.parametrize("width,height", [(1120, 850), (844, 390), (500, 760)])
def test_hybrid_preview_standalone_viewer_in_chrome(tmp_path: Path, routing: str, width: int, height: int) -> None:
    output = _build(tmp_path, routing)
    _install_probe(output, _probe(STANDALONE_PROBE, routing))
    failures = _run_chrome(tmp_path, output, "index.html", width, height)
    assert failures == [], "\n".join(failures)


@pytest.mark.parametrize("routing", ["smart", "simple"])
@pytest.mark.parametrize("width,height", [(1120, 850), (844, 390), (500, 760)])
def test_hybrid_preview_hosted_in_editor_frame_keeps_document_authority(
    tmp_path: Path, routing: str, width: int, height: int,
) -> None:
    output = _build(tmp_path, routing)
    _install_probe(output, None)
    (output / "host.html").write_text(_probe(HOST_PAGE, routing), encoding="utf-8")
    failures = _run_chrome(tmp_path, output, "host.html", width, height)
    assert failures == [], "\n".join(failures)


def test_hybrid_preview_is_not_offered_for_representation_inputs(tmp_path: Path) -> None:
    output = tmp_path / "representation"
    build_native_viewer(json.loads(GOLDEN.read_text(encoding="utf-8")), output)
    _install_probe(output, """const failures = [];
(async () => {
  try {
    for (let i = 0; i < 100 && !document.querySelector("#nativeCanvas").style.transform; ++i)
      await new Promise(resolve => setTimeout(resolve, 20));
    const button = document.querySelector("#hybridPreview");
    if (!button || !button.hidden) failures.push("button visible for representation input");
    if (document.querySelector(".hybrid-layer")) failures.push("layer present");
  } catch (error) { failures.push(String(error)); }
  document.documentElement.dataset.hybridResult = encodeURIComponent(JSON.stringify(failures));
})();
""")
    assert _run_chrome(tmp_path, output, "index.html") == []
