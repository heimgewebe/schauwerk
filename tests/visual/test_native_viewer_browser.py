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
const waitFrames = async (count = 4) => {
  for (let index = 0; index < count; index += 1) {
    await new Promise(requestAnimationFrame);
  }
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
  await waitFrames();
  const viewport = document.querySelector("#nativeViewport");
  const canvas = document.querySelector("#nativeCanvas");
  const svg = document.querySelector("#nativeDiagram");
  const status = document.querySelector("#status");
  Storage.prototype.setItem = window.__schauwerkOriginalStorageSetItem;
  if (!status?.textContent?.includes("Speichern nicht möglich")) {
    throw new Error("startup repair persistence failure was hidden by fit status");
  }

  const node = [...svg.querySelectorAll('[data-source-kind="node"]')]
    .sort(
      (left, right) =>
        right.getBoundingClientRect().right - left.getBoundingClientRect().right,
    )[0];
  if (!node) throw new Error("browser probe found no node");
  const allNodes = [...svg.querySelectorAll('[data-source-kind="node"]')];
  if (!allNodes.every((item) => insideSvg(item, svg))) {
    throw new Error("persisted out-of-bounds layout was not repaired on load");
  }

  const nodeRect = node.getBoundingClientRect();
  const nodeX = (nodeRect.left + nodeRect.right) / 2;
  const nodeY = (nodeRect.top + nodeRect.bottom) / 2;
  firePointer(node, "pointerdown", 11, nodeX, nodeY);
  firePointer(viewport, "pointermove", 11, nodeX + 2000, nodeY);
  const clampedRect = node.getBoundingClientRect();
  if (!insideSvg(node, svg)) throw new Error("dragged node escaped SVG bounds");

  firePointer(viewport, "pointermove", 11, nodeX + 1950, nodeY);
  const reversedRect = node.getBoundingClientRect();
  if (!(reversedRect.left < clampedRect.left - 20)) {
    throw new Error("clamped node stayed sticky after reversing the active drag");
  }
  if (!insideSvg(node, svg)) throw new Error("reversed node escaped SVG bounds");
  firePointer(viewport, "pointerup", 11, nodeX + 1950, nodeY);

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
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=4000",
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=15,
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
