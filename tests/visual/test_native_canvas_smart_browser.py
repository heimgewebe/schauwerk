"""Real Chrome pointer interaction for smart Canvas node and edge grips."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.native_document import json_canvas_to_editing_document
from schauwerk.visual.native_viewer import build_native_viewer


@pytest.mark.parametrize("action", ["create", "reattach"])
def test_smart_canvas_connection_handles_commit_through_document_state(
    tmp_path: Path, action: str,
) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("Google Chrome required for direct Canvas connection acceptance")
        pytest.skip("Chrome unavailable")
    source = {
        "nodes": [
            {"id": "a", "type": "text", "x": 30, "y": 60,
             "width": 140, "height": 90, "text": "A"},
            {"id": "b", "type": "text", "x": 500, "y": 65,
             "width": 140, "height": 90, "text": "B"},
            {"id": "blocker", "type": "text", "x": 280, "y": 210,
             "width": 140, "height": 90, "text": "Blocker"},
        ],
        "edges": [
            {"id": "e", "fromNode": "a", "toNode": "b",
             "label": "Verbindung", "toEnd": "arrow"},
        ],
        "schauwerk": {"edgeRouting": "smart"},
    }
    output = tmp_path / "viewer"
    build_native_viewer(json_canvas_to_editing_document(source), output)
    index = output / "index.html"
    marker = '<script type="module" src="app.js"></script>'
    original = index.read_text(encoding="utf-8")
    assert original.count(marker) == 1
    index.write_text(
        original.replace(
            marker,
            '<script>Element.prototype.setPointerCapture = function() {};\n'
            'Element.prototype.releasePointerCapture = function() {};</script>\n' + marker,
        ), encoding="utf-8",
    )

    host = r"""<!doctype html>
<html><head><meta charset="utf-8"></head><body style="margin:0">
<iframe id="viewer" style="display:block;width:100vw;height:100vh;border:0"></iframe>
<script>
const frame = document.querySelector("#viewer");
const events = [];
window.addEventListener("message", event => {
  if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
  if (event.data?.event === "native-document-rebuild") events.push(event.data);
});
const wait = async (predicate, description) => {
  for (let i = 0; i < 230; ++i) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error("timed out waiting for " + description);
};
const fire = (win, target, type, id, x, y) => target.dispatchEvent(
  new win.PointerEvent(type, {
    bubbles: true, pointerId: id, pointerType: "mouse",
    clientX: x, clientY: y, button: 0,
    buttons: type === "pointerup" || type === "pointercancel" ? 0 : 1,
    isPrimary: true,
  })
);
const center = elem => {
  const rect = elem.getBoundingClientRect();
  return [(rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2];
};
(async () => {
  try {
    await wait(() => frame.contentDocument?.querySelector("#nativeDiagram") &&
      frame.contentDocument?.querySelector("#nativeCanvas")?.style?.transform.includes("scale("),
      "viewer startup");
    const doc = frame.contentDocument, win = frame.contentWindow;
    const viewport = doc.querySelector("#nativeViewport");
    const element = doc.querySelector(
      '__ACTION__' === 'create'
        ? '[data-source-kind="node"][data-source-id="a"]'
        : '[data-source-kind="edge"][data-source-id="e"]'
    );
    if (!element) throw new Error("selection fixture missing");
    let [sx, sy] = center(element);
    fire(win, element, "pointerdown", 41, sx, sy);
    fire(win, viewport, "pointerup", 41, sx, sy);
    const handleKind = '__ACTION__' === 'create' ? 'create' : 'to';
    const handleSelector = '[data-connection-handle="' + handleKind + '"]';
    await wait(() => doc.querySelector(handleSelector), "selected SVG connector handle");
    const handle = doc.querySelector(handleSelector);
    if (handle.getAttribute("aria-label") === null)
      throw new Error("connection handle missing accessible explanation");
    const [hx, hy] = center(handle);
    const dropId = '__ACTION__' === 'create' ? 'b' : 'blocker';
    const target = doc.querySelector(
      '[data-source-kind="node"][data-source-id="' + dropId + '"] rect'
    );
    if (!target) throw new Error("drop target missing");
    const [tx, ty] = center(target);
    fire(win, handle, "pointerdown", 44, hx, hy);
    fire(win, viewport, "pointermove", 44, tx, ty);
    const preview = doc.querySelector(".native-connection-preview");
    if (!preview?.getAttribute("d")?.includes(" Q ")) {
      throw new Error("curved live connection preview not visible");
    }
    const hitStack = doc.elementsFromPoint(tx, ty);
    const underNode = hitStack
      .map(item => item.closest?.('[data-source-kind="node"]'))
      .find(item => item?.dataset?.sourceId === dropId);
    if (!underNode) {
      throw new Error("drop location is not over target node: " + JSON.stringify({
        dropId, tx, ty,
        hitStack: hitStack.slice(0, 12).map(item =>
          item.tagName + "/" + (item.getAttribute("data-source-id") || "")
        ),
        targetRect: target.getBoundingClientRect().toJSON(),
        viewportRect: viewport.getBoundingClientRect().toJSON(),
      }));
    }
    fire(win, viewport, "pointerup", 44, tx, ty);
    await wait(() => events.length === 1, "host document rebuild");
    const latest = events[0].document;
    if (latest?.schema_version !== "schauwerk-native-editing-document.v1")
      throw new Error("host did not receive native document");
    if ('__ACTION__' === 'create') {
      if (latest.edges.length !== 2 ||
          !latest.edges.some(edge => edge.from === "a" && edge.to === "b" && edge.id !== "e"))
        throw new Error("drag-to-connect did not create source-bound edge");
    } else {
      const edge = latest.edges.find(edge => edge.id === "e");
      if (!edge || edge.from !== "a" || edge.to !== "blocker" || edge.label !== "Verbindung")
        throw new Error("end handle changed edge identity or failed to reattach");
    }
    if (latest.source?.schauwerk?.edgeRouting !== "smart")
      throw new Error("smart mode not retained in rebuild snapshot");
    document.documentElement.dataset.connectionRegression = "pass";
  } catch (error) {
    document.documentElement.dataset.connectionRegression = "fail";
    document.documentElement.dataset.connectionRegressionError = String(error?.stack || error);
  }
})();
frame.src = "index.html";
</script></body></html>""".replace("__ACTION__", action)
    (output / "host.html").write_text(host, encoding="utf-8")

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                chrome, "--headless=new",
                f"--user-data-dir={tmp_path / 'chrome'}",
                "--no-first-run", "--disable-gpu", "--disable-dev-shm-usage",
                "--no-sandbox", "--run-all-compositor-stages-before-draw",
                "--window-size=1120,850",
                "--virtual-time-budget=16000", "--dump-dom",
                f"http://127.0.0.1:{server.server_address[1]}/host.html",
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr[-1000:]
    assert 'data-connection-regression="pass"' in result.stdout, result.stdout[:2000]
    assert 'data-connection-regression="fail"' not in result.stdout
