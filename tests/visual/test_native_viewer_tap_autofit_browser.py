"""Real Chromium/CDP regression for native-viewer pointer-owned auto-fit."""
from __future__ import annotations

import json
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

websockets = pytest.importorskip("websockets.sync.client")


def test_native_viewer_restores_auto_fit_after_tap_only_pointer_sequences(tmp_path: Path) -> None:
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if not chrome:
        pytest.skip("Chrome unavailable for native viewer CDP pointer regression")
    source = {
        "nodes": [
            {"id": "a", "type": "text", "x": 0, "y": 0, "width": 180, "height": 100, "text": "A"},
            {
                "id": "b", "type": "text", "x": 3900, "y": 0,
                "width": 180, "height": 100, "text": "B",
            },
        ],
        "edges": [{"id": "e", "fromNode": "a", "toNode": "b"}],
    }
    output = tmp_path / "viewer"
    build_native_viewer(json_canvas_to_editing_document(source), output)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(output)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome-profile"
    proc = subprocess.Popen(
        [
            chrome, "--headless=new", "--no-first-run", "--disable-gpu",
            "--disable-dev-shm-usage", "--no-sandbox",
            "--remote-allow-origins=http://localhost",
            "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(100):
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
        assert tab, "Chrome CDP endpoint failed to start"
        with websockets.connect(tab["webSocketDebuggerUrl"], origin="http://localhost") as ws:
            counter = 0
            def cdp(method: str, params: dict | None = None) -> dict:
                nonlocal counter
                counter += 1
                current = counter
                ws.send(json.dumps({"id": current, "method": method, "params": params or {}}))
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    message = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
                    if message.get("id") == current:
                        assert "error" not in message, message.get("error")
                        return message.get("result", {})
                raise AssertionError(f"CDP timeout: {method}")

            def eval_js(expr: str):
                value = cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                assert "exceptionDetails" not in value, value.get("exceptionDetails")
                return value.get("result", {}).get("value")

            def metrics(width: int):
                cdp("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": 844, "deviceScaleFactor": 1, "mobile": False,
                })
                time.sleep(0.2)

            def transform() -> str:
                return eval_js("document.querySelector('#nativeCanvas')?.style.transform || ''")

            def setup():
                metrics(390)
                eval_js("document.querySelector('#fitView').click()")
                time.sleep(0.12)

            def expect_resized(after_tap: bool, label: str):
                before = transform()
                metrics(320)
                after = transform()
                if after_tap:
                    assert after != before, (
                        f"{label}: tap-only pointer permanently disabled auto-fit"
                    )
                else:
                    assert after == before, f"{label}: manual view was unexpectedly auto-fitted"

            def pointer(
                target: str, event: str, pointer_id: int, dx: int = 0,
                dy: int = 0, pointer_type: str = "mouse",
            ):
                expr = f"""(() => {{
                  const viewport = document.querySelector('#nativeViewport');
                  const target = {target};
                  if (!target) throw new Error('pointer target unavailable');
                  const rect = target.getBoundingClientRect();
                  const x = (rect.left + rect.right) / 2 + {dx};
                  const y = (rect.top + rect.bottom) / 2 + {dy};
                  target.dispatchEvent(new PointerEvent('{event}', {{
                    pointerId: {pointer_id}, pointerType: '{pointer_type}',
                    clientX: x, clientY: y, bubbles: true, cancelable: true,
                    button: 0, buttons: {0 if event in ('pointerup', 'pointercancel') else 1},
                  }}));
                }})()"""
                eval_js(expr)

            node = "document.querySelector('[data-source-kind=\"node\"][data-source-id=\"a\"]')"
            edge = "document.querySelector('[data-source-kind=\"edge\"] path')"
            background = "document.querySelector('#nativeViewport')"
            cdp("Page.enable")
            cdp("Runtime.enable")
            metrics(390)
            cdp("Page.navigate", {"url": f"http://127.0.0.1:{server.server_address[1]}/"})
            for _ in range(120):
                if eval_js(
                    "document.querySelector('#nativeCanvas')?.style.transform?.includes('scale(')"
                ):
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Native viewer did not initialize in Chrome")
            eval_js("Element.prototype.setPointerCapture=function(){};Element.prototype.releasePointerCapture=function(){}")

            setup()
            pointer(node, "pointerdown", 71)
            held = transform()
            metrics(360)
            assert transform() == held, "Held-node gesture lost resize ownership"
            pointer(background, "pointerup", 71)
            time.sleep(0.12)
            assert transform() != held, "Deferred held-pointer resize did not run after pure tap"
            expect_resized(True, "node tap")

            setup()
            pointer(edge, "pointerdown", 72)
            pointer(background, "pointerup", 72)
            expect_resized(True, "edge selection")

            setup()
            pointer(background, "pointerdown", 73)
            pointer(background, "pointerup", 73)
            expect_resized(True, "background tap")

            setup()
            pointer(background, "pointerdown", 81, pointer_type="touch")
            before_jitter = transform()
            pointer(background, "pointermove", 81, dx=2, dy=1, pointer_type="touch")
            assert transform() == before_jitter, (
                "Touch-tap jitter moved the viewport before pan threshold"
            )
            pointer(background, "pointerup", 81, dx=2, dy=1, pointer_type="touch")
            expect_resized(True, "background tap with 2px jitter")

            setup()
            pointer(background, "pointerdown", 74)
            pointer(background, "pointercancel", 74)
            expect_resized(True, "motionless pointer cancellation")

            setup()
            eval_js("document.querySelector('#zoomIn').click()")
            pointer(node, "pointerdown", 75)
            pointer(background, "pointerup", 75)
            expect_resized(False, "prior manual zoom")

            setup()
            pointer(background, "pointerdown", 76)
            pointer(background, "pointermove", 76, dx=30)
            pointer(background, "pointerup", 76, dx=30)
            expect_resized(False, "confirmed pan")

            setup()
            pointer(node, "pointerdown", 77)
            pointer(background, "pointermove", 77, dx=24)
            pointer(background, "pointerup", 77, dx=24)
            expect_resized(False, "confirmed node drag")

            setup()
            pointer(node, "pointerdown", 78)
            pointer(background, "pointermove", 78, dx=24)
            pointer(background, "pointercancel", 78, dx=24)
            expect_resized(True, "fully rolled-back node drag")

            setup()
            pointer(node, "pointerdown", 79)
            pointer(background, "pointermove", 79, dx=24)
            pointer(background, "pointerdown", 80, dx=80)
            pointer(background, "pointerup", 80, dx=80)
            pointer(background, "pointerup", 79, dx=24)
            expect_resized(True, "drag-to-pinch rollback without view change")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
