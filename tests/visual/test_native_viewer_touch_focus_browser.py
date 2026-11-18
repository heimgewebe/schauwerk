"""Real-Chrome touch regression for the compact Sinn knowledge-map overview."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_sinn_knowledge_map import _sinn_model

from schauwerk.visual.native_viewer import build_native_viewer


def test_compact_knowledge_map_tap_focus_preserves_drag_and_overview(tmp_path: Path) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("Chrome must be installed for real touch navigation")
        pytest.skip("Chrome not installed")

    output = tmp_path / "viewer"
    build_native_viewer(_sinn_model(), output)
    html_path = output / "index.html"
    html = html_path.read_text(encoding="utf-8")
    app_script = '<script type="module" src="app.js"></script>'
    assert html.count(app_script) == 1
    probe = r"""
<script type="module">
Element.prototype.setPointerCapture = function () {};
Element.prototype.releasePointerCapture = function () {};
const ready = async () => {
  for (let i = 0; i < 220; i++) {
    if (document.readyState === "complete" &&
        document.querySelector("#nativeCanvas")?.style.transform.includes("scale("))
      return;
    await new Promise(resolve => {
      requestAnimationFrame(resolve);
      setTimeout(resolve, 25);
    });
  }
  throw new Error("viewer fit not ready");
};
const dispatch = (target, kind, id, x, y) => target.dispatchEvent(
  new PointerEvent(kind, {
    bubbles: true, pointerId: id, pointerType: "touch",
    clientX: x, clientY: y, button: 0,
    buttons: kind === "pointerup" ? 0 : 1, isPrimary: true,
  })
);
const zoom = () => Number(
  /scale\(([^)]+)\)/.exec(document.querySelector("#nativeCanvas").style.transform)?.[1]
);
const tap = (target, id, x, y) => {
  dispatch(target, "pointerdown", id, x, y);
  dispatch(document.querySelector("#nativeViewport"), "pointerup", id, x, y);
};
try {
  await ready();
  const svg = document.querySelector("#nativeDiagram");
  const viewport = document.querySelector("#nativeViewport");
  const fitButton = document.querySelector("#fitView");
  const node = svg.querySelector('[data-source-kind="node"][data-source-id="handeln"]');
  const group = svg.querySelector('[data-source-kind="group"][data-source-id="wirkung"]');
  const groupRect = group?.querySelector("rect");
  const edge = svg.querySelector('[data-source-kind="edge"][data-source-id="e13"]');
  const clip = svg.querySelector("#native-clip-edge-label-protection > path");
  if (!node || !groupRect || !edge || !clip) throw new Error("fixture incomplete");
  const overviewZoom = zoom();
  if (!(overviewZoom > 0 && overviewZoom < 0.75))
    throw new Error("fixture did not produce a small tablet overview");
  const groupBounds = groupRect.getBoundingClientRect();
  const groupX = groupBounds.left + Math.min(45, groupBounds.width / 2);
  const groupY = groupBounds.top + Math.min(18, groupBounds.height / 4);
  tap(groupRect, 41, groupX, groupY);
  if (zoom() < 0.9 || fitButton.textContent.trim() !== "Übersicht")
    throw new Error("tapping a group did not zoom to readable detail");
  if (!group.querySelector("title")?.textContent.includes("Wirkung"))
    throw new Error("wrong group focused");
  fitButton.click();
  if (Math.abs(zoom() - overviewZoom) > 0.015 || fitButton.textContent.trim() !== "Einpassen")
    throw new Error("single-click overview restore lost original fit");
  const beforePan = document.querySelector("#nativeCanvas").style.transform;
  dispatch(groupRect, "pointerdown", 42, groupX, groupY);
  dispatch(viewport, "pointermove", 42, groupX + 50, groupY + 40);
  dispatch(viewport, "pointerup", 42, groupX + 50, groupY + 40);
  if (Math.abs(zoom() - overviewZoom) > 0.015 ||
      document.querySelector("#nativeCanvas").style.transform === beforePan)
    throw new Error("group drag must pan, never trigger tap zoom");
  fitButton.click();

  const nodeBounds = node.getBoundingClientRect();
  const nodeX = (nodeBounds.left + nodeBounds.right) / 2;
  const nodeY = (nodeBounds.top + nodeBounds.bottom) / 2;
  const beforeNode = node.getAttribute("transform");
  const beforeEdge = edge.querySelector("path")?.getAttribute("d");
  const beforeClip = clip.getAttribute("d");
  tap(node, 43, nodeX, nodeY);
  if (zoom() < 0.9 || fitButton.textContent.trim() !== "Übersicht")
    throw new Error("tapping a small node did not zoom to its detail");
  if (node.getAttribute("transform") !== beforeNode ||
      edge.querySelector("path")?.getAttribute("d") !== beforeEdge ||
      clip.getAttribute("d") !== beforeClip)
    throw new Error("tap-to-focus modified node or edge source geometry");

  const zoomAfterFirstTap = zoom();
  const detailNode = node.getBoundingClientRect();
  const detailX = (detailNode.left + detailNode.right) / 2;
  const detailY = (detailNode.top + detailNode.bottom) / 2;
  tap(node, 44, detailX, detailY);
  if (Math.abs(zoom() - zoomAfterFirstTap) > 0.001)
    throw new Error("second tap unexpectedly increased an already readable zoom");

  dispatch(node, "pointerdown", 45, detailX, detailY);
  dispatch(viewport, "pointermove", 45, detailX - 85, detailY + 25);
  dispatch(viewport, "pointerup", 45, detailX - 85, detailY + 25);
  if (node.getAttribute("transform") === beforeNode ||
      edge.querySelector("path")?.getAttribute("d") === beforeEdge ||
      clip.getAttribute("d") === beforeClip)
    throw new Error("focused node no longer drags with live routed/clip geometry");
  if (Math.abs(zoom() - zoomAfterFirstTap) > 0.001)
    throw new Error("node drag must not trigger tap-to-focus zoom");
  fitButton.click();
  if (Math.abs(zoom() - overviewZoom) > 0.015)
    throw new Error("overview is not reachable after node drag");
  document.documentElement.dataset.tabletFocusRegression = "pass";
} catch (error) {
  document.documentElement.dataset.tabletFocusRegression = "fail";
  document.documentElement.dataset.tabletFocusRegressionError = String(error?.message || error);
}
</script>
"""
    html_path.write_text(html.replace(app_script, app_script + probe), encoding="utf-8")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage",
                f"--user-data-dir={tmp_path / 'chrome'}",
                "--window-size=820,1180", "--virtual-time-budget=12000",
                "--dump-dom",
                f"http://127.0.0.1:{server.server_address[1]}/index.html",
            ],
            capture_output=True, text=True, timeout=55, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr[-1200:]
    assert 'data-tablet-focus-regression="pass"' in result.stdout, (
        result.stdout[result.stdout.find('data-tablet-focus-regression=') - 50:
                      result.stdout.find('data-tablet-focus-regression=') + 350]
    )