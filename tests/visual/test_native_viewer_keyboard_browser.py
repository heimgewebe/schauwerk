# ruff: noqa: E501
"""Real keyboard and pointer interactions through Chrome and the native editor."""

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

from schauwerk.visual.standalone_editor import (
    _EditorRequestHandler,
    build_standalone_editor,
)


@pytest.mark.parametrize("scenario", ["keyboard", "process-loop-drag", "process-dense-loop-drag", "process-mixed-loop-drag"])
def test_keyboard_connection_activation_and_focus_in_chrome(tmp_path: Path, scenario: str) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("keyboard interaction is covered on the Python 3.12 CI lane")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        if os.environ.get("CI"):
            pytest.fail("Chrome required for keyboard connection regression")
        pytest.skip("Chrome unavailable")
    from websockets.sync.client import connect

    source = {
        "nodes": [
            {"id": "a", "type": "text", "text": "Alpha",
             "x": 30, "y": 30, "width": 180, "height": 100},
            {"id": "b", "type": "text", "text": "Beta",
             "x": 380, "y": 30, "width": 180, "height": 100},
            {"id": "c", "type": "text", "text": "Gamma",
             "x": 380, "y": 290, "width": 180, "height": 100},
        ],
        "edges": [
            {"id": "e", "fromNode": "a", "toNode": "b",
             "toEnd": "arrow", "label": "Relation"},
        ],
        "schauwerk": {"edgeRouting": "smart"},
    }
    if scenario.startswith("process-"):
        loop_count = 8 if scenario != "process-loop-drag" else 2
        source = {
            "schema_version": "schauwerk-representation-input.v1",
            "id": "self_process_minimal2",
            "title": "Selbstbezüge im Prozess",
            "purpose": "Zwei Selbstbezüge an derselben Karte",
            "intent": "process", "groups": [],
            "nodes": [
                {"id": "a", "label": "Ausgangspunkt", "kind": "concept"},
                {"id": "b", "label": "Unbeteiligter Knoten", "kind": "concept"},
            ],
            "edges": [
                {"id": f"e{i}", "from": "a", "to": "a",
                 "label": f"Selbstbezug {i}" + (
                     " mit längerem Text" if loop_count > 2 and i % 2 else ""
                 ), "kind": "flow"}
                for i in range(loop_count)
            ],
            "requirements": {}, "requested_formats": [],
        }
    if scenario == "process-mixed-loop-drag":
        source["nodes"].extend(
            {"id": f"n{i}", "label": f"Karte {i}", "kind": "concept"}
            for i in range(2, 8)
        )
        source["edges"].extend([
            {"id": "peer_0", "from": "a", "to": "b", "label": "Prozessbeziehung 0", "kind": "flow"},
            {"id": "peer_1", "from": "b", "to": "a", "label": "Prozessbeziehung 1", "kind": "feedback"},
        ])
    output = tmp_path / "editor"
    build_standalone_editor(output)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_EditorRequestHandler, directory=str(output))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome"
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--no-first-run", "--disable-gpu",
         "--disable-dev-shm-usage", "--no-sandbox", "--disable-background-networking",
         "--remote-allow-origins=http://localhost", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "--window-size=1366,900", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tab = None
        for _ in range(160):
            assert proc.poll() is None, "Chrome exited before CDP startup"
            try:
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    tab = next(
                        (item for item in json.load(response) if item.get("type") == "page"),
                        None,
                    )
                if tab:
                    break
            except (OSError, ValueError, IndexError):
                pass
            time.sleep(0.1)
        assert tab is not None
        with connect(tab["webSocketDebuggerUrl"], origin="http://localhost",
                     max_size=16 * 1024 * 1024) as ws:
            sequence = 0

            def cdp(method, params=None):
                nonlocal sequence
                sequence += 1
                request_id = sequence
                ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    response = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
                    if response.get("id") == request_id:
                        assert "error" not in response, response
                        return response.get("result", {})
                raise AssertionError(f"CDP timeout: {method}")

            def evaluate(expression):
                result = cdp("Runtime.evaluate", {
                    "expression": expression, "returnByValue": True, "awaitPromise": True,
                })
                assert "exceptionDetails" not in result, result.get("exceptionDetails")
                return result["result"].get("value")

            def wait(expression, label, seconds=12):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if evaluate(expression):
                        return
                    time.sleep(0.08)
                raise AssertionError("timed out waiting for " + label + ": " + str(evaluate("""JSON.stringify({error:document.querySelector('#error')?.textContent,status:document.querySelector('#status')?.textContent,frame:document.querySelector('#editorFrame')?.src,body:document.querySelector('#editorFrame')?.contentDocument?.body?.className,childError:document.querySelector('#editorFrame')?.contentDocument?.querySelector('#status')?.textContent})""")))

            def key(name, *, repeat=False):
                code, number, text = {
                    "Enter": ("Enter", 13, "\r"),
                    " ": ("Space", 32, " "),
                    "Tab": ("Tab", 9, ""),
                    "Escape": ("Escape", 27, ""),
                }[name]
                params = {"key": name, "code": code, "windowsVirtualKeyCode": number,
                          "nativeVirtualKeyCode": number}
                cdp("Input.dispatchKeyEvent", {
                    **params, "type": "keyDown", **({"text": text} if text else {}),
                })
                if repeat:
                    cdp("Input.dispatchKeyEvent", {
                        **params, "type": "keyDown", "autoRepeat": True,
                        **({"text": text} if text else {}),
                    })
                cdp("Input.dispatchKeyEvent", {**params, "type": "keyUp"})

            doc = "document.querySelector('#editorFrame')?.contentDocument"
            model = f"JSON.parse({doc}?.querySelector('#nativeModel')?.textContent || '{{}}')"

            def focus(selector):
                assert evaluate(
                    f"(()=>{{const d={doc};const e=d.querySelector({json.dumps(selector)});"
                    "e.focus({preventScroll:true});return d.activeElement===e;})()"
                ), selector

            def node(identifier):
                return f'[data-source-kind="node"][data-source-id="{identifier}"]'

            def edge(identifier):
                return f'[data-source-kind="edge"][data-source-id="{identifier}"]'

            def active(identifier):
                return evaluate(f"{doc}?.activeElement?.dataset?.sourceId") == identifier

            def tab_to(identifier):
                for _ in range(40):
                    if active(identifier):
                        return
                    key("Tab")
                raise AssertionError("keyboard tab sequence did not reach " + identifier)

            def toolbar_action(button, activation="Enter"):
                focus(".edit-controls > summary")
                key("Enter")
                assert evaluate(f"{doc}.querySelector('.edit-controls').open")
                focus(button)
                key(activation)

            def select(identifier, selector=None):
                selector = selector or node(identifier)
                focus(selector)
                key("Enter")
                assert evaluate(f"{doc}.querySelector({json.dumps(selector)}).getAttribute('aria-selected')") == "true"

            def snapshot():
                return evaluate(model)

            def wait_edges(count, label):
                wait(f"{doc}?.body?.classList.contains('document-editor-hosted') && {model}.edges?.length === {count} && !document.querySelector('#editorFrame').inert", label)

            def click_node(identifier):
                x, y = evaluate(
                    f"(()=>{{const f=document.querySelector('#editorFrame');"
                    f"const r=f.contentDocument.querySelector({json.dumps(node(identifier) + ' > rect')}).getBoundingClientRect();"
                    "const p=f.getBoundingClientRect();return [p.x+r.x+r.width/2,p.y+r.y+r.height/2];})()"
                )
                for event, buttons in (("mousePressed", 1), ("mouseReleased", 0)):
                    cdp("Input.dispatchMouseEvent", {"type": event, "x": x, "y": y,
                                                    "button": "left", "buttons": buttons, "clickCount": 1})

            cdp("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/"})
            wait("document.readyState === 'complete' && !!document.querySelector('#sourceInput')", "editor")
            evaluate("document.querySelector('#sourceInput').value=" + json.dumps(json.dumps(source)))
            evaluate("document.querySelector('#openPasteButton').click()")
            if scenario.startswith("process-"):
                wait(f"!!{doc}?.querySelector('#nativeDiagram') && !!{doc}?.querySelector('#nativeCanvas')?.style.transform",
                     "process viewer")
                measure = """(()=>{
                    const d=document.querySelector('#editorFrame').contentDocument;
                    const groups=[...d.querySelectorAll('[data-source-kind=edge]')];
                    const paths=groups.map(e=>e.querySelector('path[fill=none]'));
                    const labels=groups.map(e=>[...e.children].find(c=>c.tagName==='rect'&&c.getAttribute('rx')==='9').getBoundingClientRect());
                    const nodes=[...d.querySelectorAll('[data-source-kind=node] > rect')].map(n=>n.getBoundingClientRect());
                    const svg=d.querySelector('#nativeDiagram'),view=svg.viewBox.baseVal;
                    const frame=svg.getScreenCTM(),inverse=frame.inverse();
                    const cardIds=[...d.querySelectorAll('[data-source-kind=node] > rect')].map(n=>n.parentElement.dataset.sourceId);
                    const relations=__SOURCE_RELATIONS__;
                    
                    const overlap=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom;
                    const dist=(p,x,y)=>{
                        const m=p.getScreenCTM(),len=p.getTotalLength();
                        let min=Infinity;
                        for(let i=0;i<=500;i++){
                            const q=p.getPointAtLength(len*i/500).matrixTransform(m);
                            min=Math.min(min,Math.hypot(q.x-x,q.y-y));
                        }
                        return min;
                    };
                    return groups.map((e,i)=>{
                        const b=labels[i],x=b.x+b.width/2,y=b.y+b.height/2;
                        const distances=paths.map(p=>dist(p,x,y));
                        const relation=relations.find(r=>r.id===e.dataset.sourceId);
                        const p=paths[i],m=p.getScreenCTM(),len=p.getTotalLength();
                        const count=Math.max(500,Math.ceil(len/2));
                        let cardHit=false,outside=false;
                        for(let k=0;k<=count;k++){
                            const q=p.getPointAtLength(len*k/count).matrixTransform(m);
                            const v=q.matrixTransform(inverse);
                            if(v.x<view.x-.2||v.y<view.y-.2||v.x>view.x+view.width+.2||v.y>view.y+view.height+.2) outside=true;
                            if(nodes.some((r,j)=>cardIds[j]!==relation.from&&cardIds[j]!==relation.to&&q.x>r.left+.2&&q.x<r.right-.2&&q.y>r.top+.2&&q.y<r.bottom-.2)) cardHit=true;
                        }
                        return {id:e.dataset.sourceId,path:p.getAttribute('d'),
                            own:distances[i],worldOwn:distances[i]/Math.hypot(m.a,m.b),
                            other:Math.min(...distances.filter((_,j)=>j!==i)),
                            loop:relation.from===relation.to,cardHit,outside,
                            overlap:[...nodes,...labels.filter((_,j)=>j!==i)].some(r=>overlap(b,r)),
                            conflict:e.hasAttribute('data-routing-conflict')};
                    });
                })()""".replace("__SOURCE_RELATIONS__", json.dumps(source["edges"]))
                def check_geometry():
                    result = evaluate(measure)
                    if scenario == "process-mixed-loop-drag":
                        print("MIXED_BROWSER_GEOMETRY", json.dumps(result), flush=True)
                    assert len(result) == len(source["edges"]), result
                    assert len({e["path"] for e in result}) == len(source["edges"]), result
                    assert all((e["worldOwn"] <= 1 if e["loop"] else e["worldOwn"] <= 40)
                               and e["other"] > e["own"] and not e["cardHit"] and not e["outside"]
                               and not e["overlap"] and not e["conflict"] for e in result), result
                    return result

                before = check_geometry()
                x, y = evaluate(
                    f"(()=>{{const f=document.querySelector('#editorFrame');"
                    f"const r=f.contentDocument.querySelector({json.dumps(node('a') + ' > rect')}).getBoundingClientRect();"
                    "const p=f.getBoundingClientRect();return [p.x+r.x+r.width/2,p.y+r.y+r.height/2];})()"
                )
                transform = f"{doc}.querySelector({json.dumps(node('a'))}).getAttribute('transform')"
                previous_transform = evaluate(transform)
                def mouse(kind, px, py, buttons):
                    cdp("Input.dispatchMouseEvent", {
                        "type": kind, "x": px, "y": py,
                        "button": "none" if kind == "mouseMoved" else "left",
                        "buttons": buttons, "clickCount": 0 if kind == "mouseMoved" else 1,
                    })
                mouse("mouseMoved", x, y, 0)
                mouse("mousePressed", x, y, 1)
                dx, dy = (12, 0) if scenario == "process-mixed-loop-drag" else (
                    (24, 0) if loop_count > 2 else (-24, 64)
                )
                for i in range(1, 9):
                    mouse("mouseMoved", x + dx*i/8, y + dy*i/8, 1)
                    time.sleep(0.03)
                mouse("mouseReleased", x + dx, y + dy, 0)
                wait(f"{transform} !== {json.dumps(previous_transform)}", "card drag")
                after = check_geometry()
                assert {e["path"] for e in after} != {e["path"] for e in before}
                return
            wait(f"{doc}?.body?.classList.contains('document-editor-hosted') && !!{doc}?.querySelector('#nativeModel')",
                 "hosted native viewer")
            wait_edges(1, "initial document")

            # Normal selection, Enter creation, and repeated keydown must create exactly one edge.
            select("a")
            toolbar_action("#addEdge")
            assert active("a"), "new relation mode lost keyboard focus"
            tab_to("b")
            key("Enter", repeat=True)
            wait_edges(2, "Enter connection creation")
            assert [(e["from"], e["to"]) for e in snapshot()["edges"] if e["id"] != "e"] == [("a", "b")]
            wait(f"{doc}.activeElement?.dataset?.sourceId === 'b'", "focus restored after rebuild")

            # Space is the same semantic activation, not another edge operation.
            select("b")
            toolbar_action("#addEdge", " ")
            assert active("b")
            tab_to("c")
            key(" ")
            wait_edges(3, "Space connection creation")
            assert any(e["from"] == "b" and e["to"] == "c" for e in snapshot()["edges"])

            # Reattach both endpoints using the keyboard, preserving edge identity and label.
            select("e", edge("e"))
            toolbar_action("#reattachSource")
            assert active("a")
            tab_to("c")
            key("Enter")
            wait(f"{model}.edges?.some(e=>e.id==='e' && e.from==='c') && !document.querySelector('#editorFrame').inert",
                 "source endpoint reattachment")
            select("e", edge("e"))
            toolbar_action("#reattachTarget")
            assert active("b")
            tab_to("a")
            key(" ")
            wait(f"{model}.edges?.some(e=>e.id==='e' && e.to==='a') && !document.querySelector('#editorFrame').inert",
                 "target endpoint reattachment")
            relation = next(e for e in snapshot()["edges"] if e["id"] == "e")
            assert (relation["from"], relation["to"], relation["label"]) == ("c", "a", "Relation")
            assert len(snapshot()["edges"]) == 3

            # Escape restores keyboard navigation; a subsequent activation just selects.
            select("a")
            toolbar_action("#addEdge")
            key("Escape")
            assert active("a")
            tab_to("b")
            key("Enter")
            assert evaluate(f"{doc}.querySelector({json.dumps(node('b'))}).getAttribute('aria-selected')") == "true"
            assert len(snapshot()["edges"]) == 3

            # The same pending operation still completes when the destination is clicked.
            toolbar_action("#addEdge")
            click_node("c")
            wait_edges(4, "pointer completion")
            assert sum(e["from"] == "b" and e["to"] == "c" for e in snapshot()["edges"]) == 2
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
