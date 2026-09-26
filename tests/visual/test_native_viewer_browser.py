from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.native_document import (
    MAX_NATIVE_ABS_COORDINATE,
    json_canvas_to_editing_document,
)
from schauwerk.visual.native_viewer import build_native_viewer

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/system-landscape-v1.json"


def _chrome() -> str | None:
    for candidate in ("google-chrome", "google-chrome-stable"):
        if executable := shutil.which(candidate):
            return executable
    return None


def _skip_or_fail_browser(message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail(message)
    pytest.skip(message)




def _write_document_probe_host(output: Path) -> None:
    (output / "host.html").write_text(
        r"""<!doctype html>
<html>
<body>
<iframe id="viewer"></iframe>
<script>
const frame = document.querySelector("#viewer");
window.addEventListener("message", (event) => {
  if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
  if (
    event.data?.event === "native-document-change" ||
    event.data?.event === "native-document-rebuild"
  ) {
    frame.contentWindow.postMessage(event.data, window.location.origin);
  }
});
window.setInterval(() => {
  const child = frame.contentDocument?.documentElement;
  if (!child) return;
  for (const key of [
    "canvasBrowserRegression",
    "canvasBrowserRegressionError",
    "limitBrowserRegression",
    "limitBrowserRegressionError",
    "emptyCanvasBrowserRegression",
    "emptyCanvasBrowserRegressionError",
    "coordinateBrowserRegression",
    "coordinateBrowserRegressionError",
  ]) {
    if (child.dataset[key]) document.documentElement.dataset[key] = child.dataset[key];
  }
}, 20);
// Install the message listener before navigation so the viewer's initial
// requestAnimationFrame publication cannot outrun the parent harness.
frame.src = "index.html";
</script>
</body>
</html>
""",
        encoding="utf-8",
    )


def test_native_viewer_browser_keeps_dragged_nodes_reachable_and_continues_pan_after_pinch(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    if chrome is None:
        _skip_or_fail_browser("Google Chrome is unavailable for native viewer browser regression")
        raise AssertionError("unreachable")

    output = tmp_path / "viewer"
    build_native_viewer(json.loads(GOLDEN.read_text(encoding="utf-8")), output)
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    app_tag = '<script type="module" src="app.js"></script>'
    assert index.count(app_tag) == 1

    browser_probe = r"""
<script>
Element.prototype.setPointerCapture = function () {};
Element.prototype.releasePointerCapture = function () {};
const probeSvg = document.querySelector("#nativeDiagram");
const probeNode = probeSvg.querySelector('[data-source-kind="node"]');
localStorage.setItem(
  `schauwerk.native-viewer.layout.v1.${probeSvg.dataset.inputDigest}`,
  JSON.stringify({ [probeNode.dataset.sourceId]: { x: 10000, y: 0 } }),
);
window.__schauwerkOriginalStorageSetItem = Storage.prototype.setItem;
Storage.prototype.setItem = function () {
  throw new Error("blocked for startup repair probe");
};
</script>
<script type="module" src="app.js"></script>
<script type="module">
// Timers are deliberate: Chrome --dump-dom virtual time can starve rAF-only waits.
const waitForViewerReady = async (status, canvas, attempts = 200) => {
  for (let index = 0; index < attempts; index += 1) {
    if (
      status?.textContent?.includes("Speichern nicht möglich") &&
      canvas?.style?.transform?.includes("scale(")
    ) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error("viewer startup readiness timed out");
};
const firePointer = (target, type, pointerId, clientX, clientY) => target.dispatchEvent(
  new PointerEvent(type, {
    bubbles: true,
    pointerId,
    pointerType: "touch",
    clientX,
    clientY,
    button: 0,
    buttons: type === "pointerup" ? 0 : 1,
    isPrimary: pointerId === 11 || pointerId === 21,
  }),
);
const insideSvg = (node, svg) => {
  const nodeRect = node.getBoundingClientRect();
  const svgRect = svg.getBoundingClientRect();
  return (
    nodeRect.left >= svgRect.left - 1 &&
    nodeRect.right <= svgRect.right + 1 &&
    nodeRect.top >= svgRect.top - 1 &&
    nodeRect.bottom <= svgRect.bottom + 1
  );
};
try {
  const viewport = document.querySelector("#nativeViewport");
  const canvas = document.querySelector("#nativeCanvas");
  const svg = document.querySelector("#nativeDiagram");
  const status = document.querySelector("#status");
  await waitForViewerReady(status, canvas);
  Storage.prototype.setItem = window.__schauwerkOriginalStorageSetItem;
  if (!status?.textContent?.includes("Speichern nicht möglich")) {
    throw new Error("startup repair persistence failure was hidden by fit status");
  }
  if (!canvas.style.transform || !canvas.style.transform.includes("scale(")) {
    throw new Error("startup fit did not run after repair persistence failure");
  }

  const embeddedModel = JSON.parse(document.querySelector("#nativeModel")?.textContent || "{}");
  const connectedIds = new Set(
    (embeddedModel.edges || []).flatMap((edge) => [String(edge.from), String(edge.to)]),
  );
  const node = [...svg.querySelectorAll('[data-source-kind="node"]')]
    .filter((item) => connectedIds.has(String(item.dataset.sourceId || "")))
    .sort(
      (left, right) =>
        right.getBoundingClientRect().right - left.getBoundingClientRect().right,
    )[0];
  if (!node) throw new Error("browser probe found no connected node");
  const edgeModel = (embeddedModel.edges || []).find(
    (item) =>
      String(item.from) === node.dataset.sourceId ||
      String(item.to) === node.dataset.sourceId,
  );
  const incidentEdge = edgeModel
    ? [...svg.querySelectorAll('[data-source-kind="edge"]')].find(
        (item) => item.dataset.sourceId === String(edgeModel.id),
      )
    : null;
  const edgePath = incidentEdge
    ? [...incidentEdge.children].find((item) => item instanceof SVGPathElement)
    : null;
  const edgeLabelRect = incidentEdge
    ? [...incidentEdge.children].find((item) => item instanceof SVGRectElement)
    : null;
  if (!(edgePath instanceof SVGPathElement) || !(edgeLabelRect instanceof SVGRectElement)) {
    throw new Error("browser probe found no incident edge geometry");
  }
  const baseEdgePath = edgePath.getAttribute("d") || "";
  const baseMarkerEnd = edgePath.getAttribute("marker-end") || "";
  const allNodes = [...svg.querySelectorAll('[data-source-kind="node"]')];
  if (!allNodes.every((item) => insideSvg(item, svg))) {
    throw new Error("persisted out-of-bounds layout was not repaired on load");
  }

  const nodeRect = node.getBoundingClientRect();
  const nodeX = (nodeRect.left + nodeRect.right) / 2;
  const nodeY = (nodeRect.top + nodeRect.bottom) / 2;
  firePointer(node, "pointerdown", 11, nodeX, nodeY);
  firePointer(viewport, "pointermove", 11, nodeX - 2000, nodeY);
  const clampedRect = node.getBoundingClientRect();
  if (!insideSvg(node, svg)) throw new Error("dragged node escaped SVG bounds");
  if (!insideSvg(edgePath, svg)) throw new Error("dragged incident edge escaped SVG bounds");
  if (!insideSvg(edgeLabelRect, svg)) {
    throw new Error("dragged incident edge label escaped SVG bounds");
  }
  if ((edgePath.getAttribute("d") || "") === baseEdgePath) {
    throw new Error("incident edge path did not update during node drag");
  }
  if ((edgePath.getAttribute("marker-end") || "") !== baseMarkerEnd) {
    throw new Error("incident edge arrow marker binding changed during node drag");
  }
  if (!(edgeLabelRect.getAttribute("transform") || "").includes("translate(")) {
    throw new Error("incident edge label did not move during node drag");
  }

  firePointer(viewport, "pointermove", 11, nodeX - 1950, nodeY);
  const reversedRect = node.getBoundingClientRect();
  if (!(reversedRect.left > clampedRect.left + 20)) {
    throw new Error("clamped node stayed sticky after reversing the active drag");
  }
  if (!insideSvg(node, svg)) throw new Error("reversed node escaped SVG bounds");
  if (!insideSvg(edgePath, svg)) throw new Error("reversed incident edge escaped SVG bounds");
  if (!insideSvg(edgeLabelRect, svg)) {
    throw new Error("reversed incident edge label escaped SVG bounds");
  }
  firePointer(viewport, "pointerup", 11, nodeX - 1950, nodeY);

  const storageKeys = Object.keys(localStorage).filter(
    (key) => key.startsWith("schauwerk.native-viewer.layout.v1."),
  );
  if (storageKeys.length !== 1) {
    throw new Error("dragged node layout was not persisted exactly once");
  }
  const stored = JSON.parse(localStorage.getItem(storageKeys[0]));
  const storedOffset = stored[node.dataset.sourceId];
  if (!storedOffset || !Number.isFinite(storedOffset.x) || !Number.isFinite(storedOffset.y)) {
    throw new Error("persisted node offset is invalid");
  }

  const takeoverStartTransform = node.getAttribute("transform") || "";
  const takeoverStartEdgePath = edgePath.getAttribute("d") || "";
  const takeoverRect = node.getBoundingClientRect();
  const takeoverX = (takeoverRect.left + takeoverRect.right) / 2;
  const takeoverY = (takeoverRect.top + takeoverRect.bottom) / 2;
  firePointer(node, "pointerdown", 21, takeoverX, takeoverY);
  firePointer(viewport, "pointermove", 21, takeoverX + 80, takeoverY);
  const duringDragTransform = node.getAttribute("transform") || "";
  if (duringDragTransform === takeoverStartTransform) {
    throw new Error("node did not move before pinch takeover");
  }

  const secondX = takeoverX + 200;
  const secondY = takeoverY + 40;
  firePointer(viewport, "pointerdown", 22, secondX, secondY);
  const rollbackTransform = node.getAttribute("transform") || "";
  if (rollbackTransform !== takeoverStartTransform) {
    throw new Error("pinch takeover did not roll node drag back to its original offset");
  }
  if ((edgePath.getAttribute("d") || "") !== takeoverStartEdgePath) {
    throw new Error("pinch takeover did not roll incident edge geometry back");
  }

  firePointer(viewport, "pointermove", 22, secondX + 80, secondY);
  const afterPinch = canvas.style.transform;
  firePointer(viewport, "pointerup", 22, secondX + 80, secondY);
  firePointer(viewport, "pointermove", 21, takeoverX + 180, takeoverY + 50);
  const afterRemainingPointerPan = canvas.style.transform;
  if (afterRemainingPointerPan === afterPinch) {
    throw new Error("remaining pointer did not transition from pinch to pan");
  }
  if ((node.getAttribute("transform") || "") !== rollbackTransform) {
    throw new Error("old node drag resumed after pinch transitioned to one-finger pan");
  }
  firePointer(viewport, "pointerup", 21, takeoverX + 180, takeoverY + 50);
  document.documentElement.dataset.browserRegression = "pass";
} catch (error) {
  Storage.prototype.setItem = window.__schauwerkOriginalStorageSetItem;
  document.documentElement.dataset.browserRegression = "fail";
  document.documentElement.dataset.browserRegressionError = String(error?.message || error);
}
</script>
"""
    index_path.write_text(index.replace(app_tag, browser_probe), encoding="utf-8")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    handler = partial(QuietHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        try:
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    f"--user-data-dir={tmp_path / 'chrome-profile'}",
                    "--no-first-run",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=12000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            _skip_or_fail_browser("Google Chrome headless probe did not become usable in time")
            raise AssertionError("unreachable")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert 'data-browser-regression="pass"' in completed.stdout, completed.stdout
    assert 'data-browser-regression="fail"' not in completed.stdout, completed.stdout


def test_native_canvas_document_browser_drag_updates_edge_and_document_state(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    if chrome is None:
        _skip_or_fail_browser("Google Chrome is unavailable for native canvas browser regression")
        raise AssertionError("unreachable")

    canvas_source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 40,
                "y": 60,
                "width": 180,
                "height": 100,
                "text": "A",
            },
            {
                "id": "b",
                "type": "text",
                "x": 420,
                "y": 160,
                "width": 200,
                "height": 110,
                "text": "B",
            },
            {
                "id": "edge_1",
                "type": "text",
                "x": 700,
                "y": 260,
                "width": 180,
                "height": 100,
                "text": "Ziel",
            },
            {
                "id": "group",
                "type": "group",
                "x": 10,
                "y": 20,
                "width": 900,
                "height": 380,
            },
        ],
        "edges": [
            {
                "id": "e",
                "fromNode": "a",
                "fromSide": "right",
                "fromEnd": "none",
                "toNode": "b",
                "toSide": "left",
                "toEnd": "arrow",
                "label": "W" * 600,
            },
            {
                "id": "node_1",
                "fromNode": "a",
                "toNode": "b",
            },
        ],
    }
    document = json_canvas_to_editing_document(canvas_source, title="Canvas Browser Probe")
    output = tmp_path / "canvas-viewer"
    build_native_viewer(document, output)
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    app_tag = '<script type="module" src="app.js"></script>'
    assert index.count(app_tag) == 1

    browser_probe = r"""
<script>
Element.prototype.setPointerCapture = function () {};
Element.prototype.releasePointerCapture = function () {};
window.__nativeDocumentMessages = [];
window.addEventListener("message", (event) => {
  if (
    event.data?.event === "native-document-change" ||
    event.data?.event === "native-document-rebuild"
  ) {
    window.__nativeDocumentMessages.push(event.data);
  }
});
</script>
<script type="module" src="app.js"></script>
<script type="module">
const waitUntil = async (predicate, label, attempts = 200) => {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(label);
};
const firePointer = (target, type, pointerId, clientX, clientY) => target.dispatchEvent(
  new PointerEvent(type, {
    bubbles: true,
    pointerId,
    pointerType: "touch",
    clientX,
    clientY,
    button: 0,
    buttons: type === "pointerup" ? 0 : 1,
    isPrimary: true,
  }),
);
try {
  const viewport = document.querySelector("#nativeViewport");
  const canvas = document.querySelector("#nativeCanvas");
  const svg = document.querySelector("#nativeDiagram");
  const fitViewButton = document.querySelector("#fitView");
  const resetLayoutButton = document.querySelector("#resetLayout");
  if (
    !(fitViewButton instanceof HTMLButtonElement) ||
    !(resetLayoutButton instanceof HTMLButtonElement)
  ) {
    throw new Error("canvas readiness controls missing");
  }
  // Chrome --dump-dom virtual time can starve the viewer's initial rAF.
  // Exercise the real controls after app.js installed its handlers so both
  // view initialization and document publication have deterministic signals.
  fitViewButton.click();
  resetLayoutButton.click();
  await waitUntil(
    () =>
      canvas?.style?.transform?.includes("scale(") &&
      window.__nativeDocumentMessages.length > 0,
    "canvas viewer deterministic readiness timed out",
  );
  window.__nativeDocumentMessages.length = 0;

  const node = svg.querySelector('[data-source-kind="node"][data-source-id="a"]');
  const edge = svg.querySelector('[data-source-kind="edge"][data-source-id="e"]');
  const edgePath = edge ? [...edge.children].find((item) => item instanceof SVGPathElement) : null;
  const edgeLabelRect = edge
    ? [...edge.children].find((item) => item instanceof SVGRectElement)
    : null;
  if (
    !(node instanceof SVGGElement) ||
    !(edgePath instanceof SVGPathElement) ||
    !(edgeLabelRect instanceof SVGRectElement)
  ) {
    throw new Error("canvas browser probe DOM contract missing");
  }

  const basePath = edgePath.getAttribute("d") || "";
  const baseMarker = edgePath.getAttribute("marker-end") || "";
  const rect = node.getBoundingClientRect();
  const x = (rect.left + rect.right) / 2;
  const y = (rect.top + rect.bottom) / 2;
  firePointer(node, "pointerdown", 31, x, y);
  firePointer(viewport, "pointermove", 31, x + 120, y + 45);

  if ((edgePath.getAttribute("d") || "") === basePath) {
    throw new Error("canvas incident edge path did not update during drag");
  }
  if ((edgePath.getAttribute("marker-end") || "") !== baseMarker) {
    throw new Error("canvas edge marker binding changed during drag");
  }
  if (!(edgeLabelRect.getAttribute("transform") || "").includes("translate(")) {
    throw new Error("canvas edge label did not follow drag");
  }

  firePointer(viewport, "pointerup", 31, x + 120, y + 45);
  await waitUntil(
    () => window.__nativeDocumentMessages.length > 0,
    "canvas document change message was not published",
  );
  const latest = window.__nativeDocumentMessages.at(-1);
  const movedNode = latest?.document?.nodes?.find((item) => item.id === "a");
  const movedCanvasNode = latest?.canvas?.nodes?.find((item) => item.id === "a");
  if (!movedNode || !movedCanvasNode || movedNode.x === 40 || movedCanvasNode.x !== movedNode.x) {
    throw new Error("canvas document state did not capture dragged geometry");
  }
  const explicitEdge = latest?.canvas?.edges?.find((item) => item.id === "e");
  if (
    !explicitEdge ||
    !Object.prototype.hasOwnProperty.call(explicitEdge, "fromEnd") ||
    explicitEdge.fromEnd !== "none" ||
    !Object.prototype.hasOwnProperty.call(explicitEdge, "toEnd") ||
    explicitEdge.toEnd !== "arrow"
  ) {
    throw new Error("explicit default edge ends were not preserved");
  }
  const groupNode = latest?.canvas?.nodes?.find((item) => item.id === "group");
  if (!groupNode || Object.prototype.hasOwnProperty.call(groupNode, "label")) {
    throw new Error("absent group label was materialized");
  }

  const editButton = document.querySelector("#editText");
  const textDialog = document.querySelector("#textDialog");
  const textInput = document.querySelector("#textInput");
  const saveText = document.querySelector("#saveText");
  const status = document.querySelector("#status");
  if (
    !(editButton instanceof HTMLButtonElement) ||
    !(textDialog instanceof HTMLDialogElement) ||
    !(textInput instanceof HTMLTextAreaElement) ||
    !(saveText instanceof HTMLButtonElement)
  ) {
    throw new Error("canvas text editor controls missing");
  }
  if (editButton.hidden) {
    throw new Error("hosted canvas text editor control remained hidden");
  }
  editButton.click();
  await waitUntil(() => textDialog.open, "canvas text editor did not open");
  const rebuildsBeforeEmptyText = window.__nativeDocumentMessages.filter(
    (message) => message.event === "native-document-rebuild",
  ).length;
  textInput.value = "";
  saveText.click();
  await waitUntil(
    () =>
      window.__nativeDocumentMessages.filter(
        (message) => message.event === "native-document-rebuild",
      ).length > rebuildsBeforeEmptyText,
    "empty text edit did not rebuild document",
  );
  const emptyTextRebuild = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  const emptyTextNode = emptyTextRebuild?.canvas?.nodes?.find((item) => item.id === "a");
  if (!emptyTextNode || emptyTextNode.text !== "") {
    throw new Error("valid empty text was not projected to canvas");
  }
  editButton.click();
  await waitUntil(() => textDialog.open, "canvas text editor did not reopen");
  textInput.value = "Quelle geändert";
  saveText.click();
  await waitUntil(
    () =>
      window.__nativeDocumentMessages.filter(
        (message) => message.event === "native-document-rebuild",
      ).length > rebuildsBeforeEmptyText + 1,
    "valid text edit did not rebuild document",
  );
  const textRebuild = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  const editedNode = textRebuild?.canvas?.nodes?.find((item) => item.id === "a");
  if (!editedNode || editedNode.text !== "Quelle geändert") {
    throw new Error("valid text edit was not projected to canvas");
  }

  const addNodeButton = document.querySelector("#addNode");
  if (!(addNodeButton instanceof HTMLButtonElement)) {
    throw new Error("canvas add-node control missing");
  }
  const rebuildsBeforeAddNode = window.__nativeDocumentMessages.filter(
    (message) => message.event === "native-document-rebuild",
  ).length;
  addNodeButton.click();
  await waitUntil(
    () =>
      window.__nativeDocumentMessages.filter(
        (message) => message.event === "native-document-rebuild",
      ).length > rebuildsBeforeAddNode,
    "add-node did not rebuild document",
  );
  const addNodeRebuild = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  if (addNodeRebuild?.document?.nodes?.some((item) => item.id === "node_1")) {
    throw new Error("new node collided with existing edge id");
  }
  let allIds = [
    ...(addNodeRebuild?.document?.nodes || []).map((item) => item.id),
    ...(addNodeRebuild?.document?.edges || []).map((item) => item.id),
  ];
  if (new Set(allIds).size !== allIds.length) {
    throw new Error("add-node produced duplicate global ids");
  }

  firePointer(node, "pointerdown", 41, x, y);
  firePointer(viewport, "pointerup", 41, x, y);
  const addEdgeButton = document.querySelector("#addEdge");
  if (!(addEdgeButton instanceof HTMLButtonElement) || addEdgeButton.hidden) {
    throw new Error("hosted canvas add-edge control missing");
  }
  const rebuildsBeforeSelfLoop = window.__nativeDocumentMessages.filter(
    (message) => message.event === "native-document-rebuild",
  ).length;
  addEdgeButton.click();
  firePointer(node, "pointerdown", 42, x, y);
  await waitUntil(
    () =>
      window.__nativeDocumentMessages.filter(
        (message) => message.event === "native-document-rebuild",
      ).length > rebuildsBeforeSelfLoop,
    "self-loop add-edge did not rebuild document",
  );
  const selfLoopRebuild = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  if (!selfLoopRebuild?.document?.edges?.some((item) => item.from === "a" && item.to === "a")) {
    throw new Error("self-loop edge was not created");
  }

  firePointer(node, "pointerdown", 43, x, y);
  firePointer(viewport, "pointerup", 43, x, y);
  const edgeIdTarget = svg.querySelector(
    '[data-source-kind="node"][data-source-id="edge_1"]',
  );
  if (!(edgeIdTarget instanceof SVGGElement)) {
    throw new Error("canvas add-edge target missing");
  }
  const rebuildsBeforeAddEdge = window.__nativeDocumentMessages.filter(
    (message) => message.event === "native-document-rebuild",
  ).length;
  addEdgeButton.click();
  const targetRect = edgeIdTarget.getBoundingClientRect();
  firePointer(
    edgeIdTarget,
    "pointerdown",
    44,
    (targetRect.left + targetRect.right) / 2,
    (targetRect.top + targetRect.bottom) / 2,
  );
  await waitUntil(
    () =>
      window.__nativeDocumentMessages.filter(
        (message) => message.event === "native-document-rebuild",
      ).length > rebuildsBeforeAddEdge,
    "add-edge did not rebuild document",
  );
  const addEdgeRebuild = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  const addedEdge = addEdgeRebuild?.document?.edges?.find(
    (item) => item.from === "a" && item.to === "edge_1",
  );
  if (!addedEdge || addedEdge.id === "edge_1") {
    throw new Error("new edge collided with existing node id");
  }
  allIds = [
    ...(addEdgeRebuild?.document?.nodes || []).map((item) => item.id),
    ...(addEdgeRebuild?.document?.edges || []).map((item) => item.id),
  ];
  if (new Set(allIds).size !== allIds.length) {
    throw new Error("add-edge produced duplicate global ids");
  }

  if (
    Object.keys(localStorage).some((key) =>
      key.startsWith("schauwerk.native-viewer.layout.v1."),
    )
  ) {
    throw new Error("document-backed canvas drag leaked into local layout storage");
  }
  document.documentElement.dataset.canvasBrowserRegression = "pass";
} catch (error) {
  document.documentElement.dataset.canvasBrowserRegression = "fail";
  document.documentElement.dataset.canvasBrowserRegressionError = String(error?.message || error);
}
</script>
"""
    index_path.write_text(index.replace(app_tag, browser_probe), encoding="utf-8")
    _write_document_probe_host(output)

    class QuietCanvasHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    handler = partial(QuietCanvasHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        try:
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    f"--user-data-dir={tmp_path / 'canvas-chrome-profile'}",
                    "--no-first-run",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=12000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/host.html",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            _skip_or_fail_browser("Google Chrome canvas probe did not become usable in time")
            raise AssertionError("unreachable")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert 'data-canvas-browser-regression="pass"' in completed.stdout, completed.stdout
    assert 'data-canvas-browser-regression="fail"' not in completed.stdout, completed.stdout



def test_native_canvas_browser_clamps_dragged_coordinates_to_document_budget(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    if chrome is None:
        _skip_or_fail_browser("Google Chrome is unavailable for canvas coordinate regression")
        raise AssertionError("unreachable")

    canvas_source = {
        "nodes": [
            {
                "id": "boundary",
                "type": "text",
                "x": MAX_NATIVE_ABS_COORDINATE,
                "y": MAX_NATIVE_ABS_COORDINATE,
                "width": 180,
                "height": 90,
                "text": "Boundary",
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(canvas_source)
    output = tmp_path / "canvas-coordinate-viewer"
    build_native_viewer(
        document,
        output,
        serve_binding="127.0.0.1-only",
        public_base_path="",
    )

    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    app_tag = '<script type="module" src="app.js"></script>'
    assert app_tag in index
    browser_probe = r"""
<script>
Element.prototype.setPointerCapture = function () {};
Element.prototype.releasePointerCapture = function () {};
</script>
<script type="module" src="app.js"></script>
<script type="module">
window.__nativeDocumentMessages = [];
window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  if (
    event.data?.event === "native-document-change" ||
    event.data?.event === "native-document-rebuild"
  ) {
    window.__nativeDocumentMessages.push(event.data);
  }
});
const waitUntil = async (predicate, label) => {
  const deadline = performance.now() + 6000;
  while (performance.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(label);
};
const firePointer = (target, type, pointerId, clientX, clientY) => {
  target.dispatchEvent(new PointerEvent(type, {
    pointerId,
    clientX,
    clientY,
    bubbles: true,
    cancelable: true,
    pointerType: "mouse",
    buttons: type === "pointerup" ? 0 : 1,
  }));
};
try {
  await waitUntil(
    () =>
      document.querySelector('[data-source-kind="node"][data-source-id="boundary"]') &&
      document.querySelector("#nativeCanvas")?.style?.transform?.includes("scale(") &&
      window.__nativeDocumentMessages.length > 0,
    "boundary viewer did not become interaction-ready",
  );
  const node = document.querySelector(
    '[data-source-kind="node"][data-source-id="boundary"]',
  );
  const viewport = document.querySelector("#nativeViewport");
  if (!(node instanceof SVGGElement) || !(viewport instanceof HTMLElement)) {
    throw new Error("coordinate regression controls missing");
  }
  const limits = JSON.parse(document.querySelector("#nativeLimits")?.textContent || "{}");
  const limit = limits.max_abs_coordinate;
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("coordinate budget was not embedded");
  }

  window.__nativeDocumentMessages.length = 0;
  const rect = node.getBoundingClientRect();
  const x = (rect.left + rect.right) / 2;
  const y = (rect.top + rect.bottom) / 2;
  firePointer(node, "pointerdown", 71, x, y);
  firePointer(viewport, "pointermove", 71, x + 40, y + 40);
  firePointer(viewport, "pointerup", 71, x + 40, y + 40);
  await waitUntil(
    () => window.__nativeDocumentMessages.some(
      (message) => message.event === "native-document-change",
    ),
    "coordinate drag did not publish document state",
  );
  const latest = window.__nativeDocumentMessages
    .filter((message) => message.event === "native-document-change")
    .at(-1);
  const documentNode = latest?.document?.nodes?.find((item) => item.id === "boundary");
  const canvasNode = latest?.canvas?.nodes?.find((item) => item.id === "boundary");
  if (
    !documentNode ||
    !canvasNode ||
    documentNode.x !== limit ||
    documentNode.y !== limit ||
    canvasNode.x !== limit ||
    canvasNode.y !== limit
  ) {
    throw new Error("drag published coordinates outside the accepted document range");
  }
  document.documentElement.dataset.coordinateBrowserRegression = "pass";
} catch (error) {
  document.documentElement.dataset.coordinateBrowserRegression = "fail";
  document.documentElement.dataset.coordinateBrowserRegressionError = String(
    error?.message || error,
  );
}
</script>
"""
    index_path.write_text(index.replace(app_tag, browser_probe), encoding="utf-8")
    _write_document_probe_host(output)

    class QuietCoordinateHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    handler = partial(QuietCoordinateHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        try:
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    f"--user-data-dir={tmp_path / 'coordinate-chrome-profile'}",
                    "--no-first-run",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=8000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/host.html",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            _skip_or_fail_browser("Google Chrome coordinate probe did not become usable in time")
            raise AssertionError("unreachable")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert 'data-coordinate-browser-regression="pass"' in completed.stdout, completed.stdout
    assert 'data-coordinate-browser-regression="fail"' not in completed.stdout, completed.stdout


def test_native_canvas_browser_blocks_node_creation_past_product_limit(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    if chrome is None:
        _skip_or_fail_browser("Google Chrome is unavailable for canvas limit regression")
        raise AssertionError("unreachable")

    canvas_source = {
        "nodes": [
            {
                "id": f"node-{index}",
                "type": "text",
                "x": (index % 16) * 150,
                "y": (index // 16) * 100,
                "width": 120,
                "height": 70,
                "text": f"Node {index}",
            }
            for index in range(128)
        ]
    }
    document = json_canvas_to_editing_document(
        canvas_source,
        title="Canvas Limit Browser Probe",
    )
    output = tmp_path / "canvas-limit-viewer"
    build_native_viewer(document, output)
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    app_tag = '<script type="module" src="app.js"></script>'
    assert index.count(app_tag) == 1

    browser_probe = r"""
<script>
Element.prototype.setPointerCapture = function () {};
Element.prototype.releasePointerCapture = function () {};
window.__nativeLimitMessages = [];
window.addEventListener("message", (event) => {
  if (
    event.data?.event === "native-document-change" ||
    event.data?.event === "native-document-rebuild"
  ) {
    window.__nativeLimitMessages.push(event.data);
  }
});
</script>
<script type="module" src="app.js"></script>
<script type="module">
const waitUntil = async (predicate, label, attempts = 200) => {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(label);
};
try {
  const svg = document.querySelector("#nativeDiagram");
  // Chrome --dump-dom virtual time can starve the viewer's one-shot initial
  // requestAnimationFrame publication. Reuse the real hosted reset control
  // after app.js installed its handler to synchronously republish the same
  // authoritative document state before exercising the product-limit path.
  const resetLayoutButton = document.querySelector("#resetLayout");
  if (!(resetLayoutButton instanceof HTMLButtonElement)) {
    throw new Error("limit probe reset control missing");
  }
  resetLayoutButton.click();
  await waitUntil(
    () =>
      svg?.querySelectorAll('[data-source-kind="node"]').length === 128 &&
      window.__nativeLimitMessages.length > 0,
    "limit probe deterministic startup timed out",
  );
  window.__nativeLimitMessages.length = 0;

  const addNode = document.querySelector("#addNode");
  const status = document.querySelector("#status");
  const deleteSelection = document.querySelector("#deleteSelection");
  if (
    !(addNode instanceof HTMLButtonElement) ||
    !(deleteSelection instanceof HTMLButtonElement) ||
    !(status instanceof HTMLElement)
  ) {
    throw new Error("limit probe controls missing");
  }

  addNode.click();
  await new Promise((resolve) => setTimeout(resolve, 100));
  const blockedRebuilds = window.__nativeLimitMessages.filter(
    (message) => message.event === "native-document-rebuild",
  );
  if (blockedRebuilds.length !== 0) {
    throw new Error("129th node escaped the product-limit precheck");
  }
  if (!status.textContent.includes("maximal 128 Knoten")) {
    throw new Error("node limit was not explained in the viewer status");
  }
  if (svg.querySelectorAll('[data-source-kind="node"]').length !== 128) {
    throw new Error("blocked node creation mutated the visible generation");
  }

  const survivor = svg.querySelector(
    '[data-source-kind="node"][data-source-id="node-0"]',
  );
  if (!(survivor instanceof SVGGElement)) {
    throw new Error("existing node missing after blocked creation");
  }
  survivor.dispatchEvent(new MouseEvent("dblclick", {
    bubbles: true,
    cancelable: true,
    view: window,
  }));
  const dialog = document.querySelector("#textDialog");
  if (dialog?.open) dialog.close();
  deleteSelection.click();

  await waitUntil(
    () =>
      window.__nativeLimitMessages.some(
        (message) =>
          message.event === "native-document-rebuild" &&
          message.document?.nodes?.length === 127 &&
          message.canvas?.nodes?.length === 127,
      ),
    "valid deletion was not available after blocked node creation",
  );
  const validRebuild = window.__nativeLimitMessages
    .filter((message) => message.event === "native-document-rebuild")
    .at(-1);
  if (
    validRebuild.document.nodes.some((item) => item.id === "node-0") ||
    validRebuild.canvas.nodes.some((item) => item.id === "node-0")
  ) {
    throw new Error("valid post-limit deletion did not reach document/canvas state");
  }

  document.documentElement.dataset.limitBrowserRegression = "pass";
} catch (error) {
  document.documentElement.dataset.limitBrowserRegression = "fail";
  document.documentElement.dataset.limitBrowserRegressionError = String(
    error?.message || error,
  );
}
</script>
"""
    index_path.write_text(index.replace(app_tag, browser_probe), encoding="utf-8")
    _write_document_probe_host(output)

    class QuietLimitHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    handler = partial(QuietLimitHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        try:
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    f"--user-data-dir={tmp_path / 'canvas-limit-chrome-profile'}",
                    "--no-first-run",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=12000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/host.html",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            _skip_or_fail_browser("Google Chrome canvas limit probe timed out")
            raise AssertionError("unreachable")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert 'data-limit-browser-regression="pass"' in completed.stdout, completed.stdout
    assert 'data-limit-browser-regression="fail"' not in completed.stdout, completed.stdout


def test_native_canvas_document_browser_preserves_absent_empty_arrays(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    if chrome is None:
        _skip_or_fail_browser("Google Chrome is unavailable for empty canvas browser regression")
        raise AssertionError("unreachable")

    document = json_canvas_to_editing_document({}, title="Empty Canvas Browser Probe")
    output = tmp_path / "empty-canvas-viewer"
    build_native_viewer(document, output)
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    app_tag = '<script type="module" src="app.js"></script>'
    assert index.count(app_tag) == 1

    browser_probe = r"""
<script>
window.__nativeEmptyMessages = [];
window.addEventListener("message", (event) => {
  if (event.data?.event === "native-document-change") {
    window.__nativeEmptyMessages.push(event.data);
  }
});
</script>
<script type="module" src="app.js"></script>
<script type="module">
const waitUntil = async (predicate, label, attempts = 200) => {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(label);
};
try {
  // The initial requestAnimationFrame publication may be starved by Chrome
  // --dump-dom virtual time. Trigger the existing hosted reset action after
  // app.js has installed its handlers to request the same authoritative state
  // through a deterministic synchronous publication.
  const resetLayoutButton = document.querySelector("#resetLayout");
  if (!(resetLayoutButton instanceof HTMLButtonElement)) {
    throw new Error("empty canvas reset control missing");
  }
  resetLayoutButton.click();
  await waitUntil(
    () => window.__nativeEmptyMessages.length > 0,
    "empty canvas state publication timed out",
  );
  const latest = window.__nativeEmptyMessages.at(-1);
  if (!latest?.canvas || typeof latest.canvas !== "object") {
    throw new Error("empty canvas message missing");
  }
  if (
    Object.prototype.hasOwnProperty.call(latest.canvas, "nodes") ||
    Object.prototype.hasOwnProperty.call(latest.canvas, "edges")
  ) {
    throw new Error("empty canvas materialized optional nodes or edges");
  }
  document.documentElement.dataset.emptyCanvasBrowserRegression = "pass";
} catch (error) {
  document.documentElement.dataset.emptyCanvasBrowserRegression = "fail";
  document.documentElement.dataset.emptyCanvasBrowserRegressionError = String(
    error?.message || error,
  );
}
</script>
"""
    index_path.write_text(index.replace(app_tag, browser_probe), encoding="utf-8")
    _write_document_probe_host(output)

    class QuietEmptyCanvasHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    handler = partial(QuietEmptyCanvasHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        try:
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    f"--user-data-dir={tmp_path / 'empty-canvas-chrome-profile'}",
                    "--no-first-run",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=12000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/host.html",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            _skip_or_fail_browser("Google Chrome empty canvas probe did not become usable in time")
            raise AssertionError("unreachable")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stderr
    assert (
        'data-empty-canvas-browser-regression="pass"' in completed.stdout
    ), completed.stdout
    assert (
        'data-empty-canvas-browser-regression="fail"' not in completed.stdout
    ), completed.stdout