"""Regression boundaries for bounded JSON Canvas undo/redo."""
from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_native_history_protocol_and_limits(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    html = (output / "index.html").read_text(encoding="utf-8")
    host = (output / "app.js").read_text(encoding="utf-8")
    viewer = (output / "native").exists()
    assert 'id="nativeHistoryControls"' in html
    assert 'id="nativeUndoButton"' in html
    assert 'id="nativeRedoButton"' in html
    assert "NATIVE_HISTORY_MAX_STATES = 24" in host
    assert "NATIVE_HISTORY_MAX_TOTAL_CHARS = 8 * 1024 * 1024" in host
    assert "nativeHistoryObservationMode" in host
    assert "let nativeFrameReady = false;" in host
    assert "!nativeFrameReady || !editorReady || nativeCanvasRenderStale" in host
    assert 'if (startupSync && activeEngine === "native" && !nativeCanvasRenderStale)' in host
    assert "nativeFrameReady = true;" in host
    assert "pendingNativeReadyStatus = null;" in host
    assert "readyStatus = pendingNativeReadyStatus;" in host
    assert 'setStatus("Ansicht wird geladen …");' in host
    assert "if (!preserveActiveFrame) resetNativeHistory();" in host
    assert 'message.event === "native-document-rebuild"' in host
    assert 'message.event === "native-document-change"' in host
    assert 'message.event === "native-observation-mode"' in host
    assert 'message.event === "native-history-command"' in host
    assert "pendingNativeRebuildHistory = pendingRebuild;" in host
    assert "if (pendingNativeRebuildHistory !== pendingRebuild) return;" in host
    assert "pushNativeHistory(nativeUndoStack, pendingRebuild.previous);" in host
    assert "nativeUndoStack = [];" in host
    assert "nativeRedoStack = [];" in host
    assert not viewer  # Native viewer remains served by the API, not bundled in the shell.


def test_native_viewer_exposes_observer_and_history_keyboard_contract() -> None:
    from schauwerk.resources.native_viewer.assets import ASSETS

    script = ASSETS["app.js"]
    if isinstance(script, bytes):
        script = script.decode("utf-8")
    assert 'event: "native-observation-mode"' in script
    assert 'event: "native-history-command"' in script
    assert 'window.parent.postMessage(' in script
    assert 'event.altKey || event.isComposing || textDialog?.open' in script



def test_native_history_browser_undo_redo(tmp_path: Path, monkeypatch) -> None:
    """Exercise actual Canvas edits, history and observer mode through the served shell."""
    import json
    import os
    import shutil
    import subprocess
    import threading
    import time
    from functools import partial
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen

    import pytest
    from websockets.sync.client import connect

    from schauwerk.visual.standalone_editor import _EditorRequestHandler

    if os.environ.get("CI") and __import__("sys").version_info[:2] != (3, 12):
        pytest.skip("full Chrome native history runs in the 3.12 CI lane")
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Google Chrome required in the native history CI lane")
        pytest.skip("Google Chrome unavailable")

    # The API spawns an isolated native-viewer process; both processes must
    # import *this checkout*, not a previously editable-installed repository.
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2] / "src"))
    output = tmp_path / "editor"
    build_standalone_editor(output)
    probe = r"""
const wait = async (predicate, label) => {
  for (let attempt = 0; attempt < 450; attempt += 1) {
    try { if (predicate()) return; } catch (_) { /* frame is being replaced */ }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(label + " | state=" + JSON.stringify({
    nodeCount: nodeCount(),
    undoDisabled: document.querySelector("#nativeUndoButton")?.disabled,
    redoDisabled: document.querySelector("#nativeRedoButton")?.disabled,
    frameReadyState: frameDoc()?.readyState,
    frameStatus: frameDoc()?.querySelector("#status")?.textContent,
    frameAddDisabled: frameDoc()?.querySelector("#addNode")?.disabled,
    status: document.querySelector("#status")?.textContent,
    error: document.querySelector("#error")?.textContent,
    frameInert: document.querySelector("#editorFrame")?.inert,
    frameUrl: frameDoc()?.URL,
  }));
};
const frameDoc = () => document.querySelector("#editorFrame")?.contentDocument;
const nodeCount = () => frameDoc()?.querySelectorAll('[data-source-kind="node"]').length;
try {
  const undo = document.querySelector("#nativeUndoButton");
  const redo = document.querySelector("#nativeRedoButton");
  const menu = document.querySelector(".workspace-tools-menu");
  if (!undo || !redo || !menu) throw new Error("History buttons are missing");
  document.querySelector("#blankButton").click();
  await wait(() => {
    const viewer = frameDoc();
    const add = viewer?.querySelector("#addNode");
    return viewer?.readyState === "complete" && add &&
      !add.hidden && !add.disabled &&
      viewer.querySelector("#status")?.textContent?.includes("Ansicht angepasst");
  }, "Native viewer module was not ready for edits");
  if (!menu.hidden || !undo.disabled || !redo.disabled) {
    throw new Error("Empty native workspace exposed enabled history");
  }
  if (!frameDoc().querySelector("#observationMode")) {
    throw new Error("Current native viewer observation mode is missing");
  }

  frameDoc().querySelector("#addNode").click();
  await wait(() => nodeCount() === 0 && undo.disabled &&
    !document.querySelector("#nativeRetryButton")?.hidden &&
    document.querySelector("#editorFrame")?.inert,
    "Rejected rebuild did not expose an inert original frame and retry");
  const pendingDraft = JSON.parse(
    localStorage.getItem("schauwerk.native-schaubild.draft.v1") || "null"
  );
  if (pendingDraft?.nativeCanvas?.nodes?.length !== 1) {
    throw new Error("Failed rebuild did not preserve its edited candidate");
  }
  document.querySelector("#nativeRetryButton").click();
  await wait(() => nodeCount() === 1 && !undo.disabled &&
    document.querySelector("#nativeRetryButton")?.hidden &&
    !document.querySelector("#editorFrame")?.inert,
    "Successful rebuild retry did not commit the undo preimage");
  if (menu.hidden || !redo.disabled) throw new Error("New edit history state invalid");

  // A rejected user import must preserve the currently active history.
  document.querySelector("#sourceInput").value = "{invalid json";
  document.querySelector("#openPasteButton").click();
  if (nodeCount() !== 1 || undo.disabled || !redo.disabled ||
      !document.querySelector("#error")?.textContent?.includes("Format nicht erkannt")) {
    throw new Error("Invalid import discarded active native document or history");
  }

  // The test server also rejects the first undo render once. The original
  // rendered frame, history entry and locally saved draft must survive.
  undo.click();
  await wait(() => nodeCount() === 1 && !undo.disabled && redo.disabled &&
    !document.querySelector("#editorFrame")?.inert &&
    document.querySelector("#nativeRetryButton")?.hidden &&
    document.querySelector("#error")?.textContent?.includes(
      "Rückgängig konnte nicht übernommen werden"),
    "Rejected undo did not restore the previous live state");
  const retainedDraft = JSON.parse(
    localStorage.getItem("schauwerk.native-schaubild.draft.v1") || "null"
  );
  if (retainedDraft?.nativeCanvas?.nodes?.length !== 1) {
    throw new Error("Rejected undo lost the previous saved document");
  }

  // Manual zoom/pan is view-only. Undo and Redo must retain its exact
  // transform even though the native renderer replaces the document iframe.
  const priorFitView = frameDoc().querySelector("#nativeCanvas").style.transform;
  frameDoc().querySelector("#zoomIn").click();
  const manualView = frameDoc().querySelector("#nativeCanvas").style.transform;
  if (!manualView || manualView === priorFitView) {
    throw new Error("Manual zoom did not change the native viewport");
  }
  undo.click();
  await wait(() => nodeCount() === 0 && !redo.disabled &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform === manualView,
    "Undo lost the user's manual viewport");
  redo.click();
  await wait(() => nodeCount() === 1 && !undo.disabled &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform === manualView,
    "Redo lost the user's manual viewport");
  undo.click();
  await wait(() => nodeCount() === 0 && !redo.disabled &&
    !document.querySelector("#editorFrame")?.inert &&
    frameDoc()?.querySelector("#addNode")?.disabled === false &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform === manualView,
    "Second undo did not preserve the manual viewport or an editable Canvas");
  frameDoc().querySelector("#addNode").click();
  await wait(() => nodeCount() === 1 && redo.disabled && !undo.disabled,
    "New branch kept stale redo");

  const viewer = frameDoc();
  const source = viewer.querySelector("#nativeModel").textContent;
  viewer.querySelector("#observationMode").click();
  await wait(() => undo.disabled, "Observation did not disable undo");
  if (viewer.querySelector("#nativeModel").textContent !== source) {
    throw new Error("Observation changed document source");
  }
  viewer.querySelector("#observationMode").click();
  await wait(() => !undo.disabled, "Editing mode did not reenable undo");

  frameDoc().defaultView.dispatchEvent(new KeyboardEvent("keydown", {
    key: "z", ctrlKey: true, bubbles: true, cancelable: true,
  }));
  await wait(() => nodeCount() === 0 && !redo.disabled &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform === manualView,
    "Ctrl+Z from viewer lost the manual view");
  // Starting a separate diagram must not inherit the previous document's zoom.
  document.querySelector("#homeLink").click();
  await wait(() => document.querySelector("#startView")?.hidden === false,
    "Returning home did not close the old native document");
  document.querySelector("#blankButton").click();
  await wait(() => frameDoc()?.readyState === "complete" &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform &&
    frameDoc()?.querySelector("#nativeCanvas")?.style.transform !== manualView,
    "A new diagram incorrectly inherited the previous document's manual view");
  document.documentElement.dataset.nativeHistoryBrowser = "pass";
} catch (error) {
  document.documentElement.dataset.nativeHistoryBrowser = "fail";
  document.documentElement.dataset.nativeHistoryError = String(error?.message || error);
}
"""
    class _OneTransientHistoryFailure(_EditorRequestHandler):
        render_requests = 0

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/native-viewer":
                type(self).render_requests += 1
                if type(self).render_requests in {2, 4}:
                    self._send_json(503, {"error": "synthetic transient render failure"})
                    return
            super().do_POST()

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_OneTransientHistoryFailure, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome-profile"
    active_port = profile / "DevToolsActivePort"
    proc = subprocess.Popen(
        [
            chrome, "--headless=new", "--no-first-run", "--no-sandbox",
            "--disable-gpu", "--disable-dev-shm-usage",
            "--remote-allow-origins=http://localhost",
            "--remote-debugging-port=0", f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(100):
            try:
                port = int(active_port.read_text(encoding="utf-8").splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    pages = json.load(response)
                tab = next((item for item in pages if item.get("type") == "page"), None)
                if tab is not None:
                    break
            except (OSError, ValueError, IndexError):
                pass
            time.sleep(0.12)
        assert tab is not None, "Chrome did not launch"

        with connect(tab["webSocketDebuggerUrl"], origin="http://localhost") as ws:
            counter = 0

            def cdp(method: str, params: dict) -> dict:
                nonlocal counter
                counter += 1
                expected = counter
                ws.send(json.dumps({"id": expected, "method": method, "params": params}))
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline:
                    try:
                        message = json.loads(ws.recv(timeout=10))
                    except TimeoutError:
                        continue
                    if message.get("id") == expected:
                        assert "error" not in message, message["error"]
                        return message.get("result", {})
                raise AssertionError("Chrome CDP timed out: " + method)

            cdp("Page.navigate", {"url": f"http://127.0.0.1:{server.server_address[1]}/"})
            expression = (
                "(async()=>{ await new Promise(resolve=>{"
                "if(document.readyState==='complete')resolve();"
                "else window.addEventListener('load',resolve,{once:true});"
                "});" + probe
                + "return {state:document.documentElement.dataset.nativeHistoryBrowser,"
                "error:document.documentElement.dataset.nativeHistoryError};})()"
            )
            evaluated = cdp("Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            })
            assert "exceptionDetails" not in evaluated, evaluated.get("exceptionDetails")
            result = evaluated.get("result", {}).get("value", {})
            if result.get("state") != "pass":
                print("BROWSER_DIAG", json.dumps(result, ensure_ascii=False), flush=True)
            assert result.get("state") == "pass", result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
