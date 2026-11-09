# ruff: noqa: E501
"""Offline HTML export of native JSON Canvas documents: generator, route and real Chrome."""

from __future__ import annotations

import copy
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from functools import partial
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pytest

from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import json_canvas_to_editing_document
from schauwerk.visual.native_offline_html import (
    MAX_OFFLINE_HTML_BYTES,
    OFFLINE_HTML_SCHEMA,
    OfflineHtmlError,
    build_offline_html,
    content_security_policy,
    sanitize_native_svg,
)
from schauwerk.visual.standalone_editor import _EditorRequestHandler, build_standalone_editor

ROOT = Path(__file__).resolve().parents[2]
INJECTION_TEXT = '<img src=x onerror="window.__pwn=1"></script><script>window.__pwn=2</script>'
HOSTILE_ID = 'n"><script>window.__pwn=3</script>&amp;'


def _canvas() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "grp", "type": "group", "label": "Phase <1> & 2", "x": -40, "y": -40, "width": 760, "height": 340},
            {"id": "a", "type": "text", "text": "Willkommen Welt\nzweite Zeile ✓ 日本語 مرحبا", "x": 0, "y": 0, "width": 240, "height": 100, "color": "4"},
            {"id": "b", "type": "file", "file": "notes/ziel.md", "subpath": "#Abschnitt", "x": 400, "y": 0, "width": 240, "height": 100},
            {"id": "c", "type": "link", "url": "https://example.invalid/pfad?x=1&y=2", "x": 400, "y": 160, "width": 240, "height": 100},
            {"id": HOSTILE_ID, "type": "text", "text": INJECTION_TEXT, "x": 0, "y": 160, "width": 240, "height": 100},
        ],
        "edges": [
            {"id": "e1", "fromNode": "a", "toNode": "b", "label": "führt zu", "toEnd": "arrow"},
            {"id": "e2", "fromNode": "b", "toNode": "c", "fromEnd": "arrow", "toEnd": "none"},
            {"id": "e3", "fromNode": HOSTILE_ID, "toNode": "a", "label": "</title><script>1</script>"},
        ],
    }


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def _markup(page: str) -> list[tuple[str, dict[str, str | None]]]:
    collector = _TagCollector()
    collector.feed(page)
    return collector.tags


def _svg(canvas: dict[str, Any]) -> str:
    return render_native_editing_document(json_canvas_to_editing_document(canvas, title="T"))


def _build(canvas: dict[str, Any] | None = None, *, title: str = "Probe <Schaubild>") -> bytes:
    canvas = canvas or _canvas()
    return build_offline_html(canvas, _svg(canvas), title=title).html


# ---------------------------------------------------------------- generator


def test_offline_html_is_deterministic_and_csp_hashes_bind_inline_assets() -> None:
    canvas = _canvas()
    first = build_offline_html(canvas, _svg(canvas), title="Probe")
    second = build_offline_html(copy.deepcopy(canvas), _svg(canvas), title="Probe")
    assert first.html == second.html
    assert first.sha256 == hashlib.sha256(first.html).hexdigest()
    page = first.html.decode("utf-8")
    csp = content_security_policy()
    assert csp in page.replace("&#x27;", "'")
    # Exactly one inline script and one inline style, each bound by hash.
    assert page.count("<script") == 1 and page.count("<style") == 1
    from schauwerk.resources.native_offline_html.assets import VIEWER_CSS, VIEWER_JS

    assert f"<script>{VIEWER_JS}</script>" in page
    assert f"<style>{VIEWER_CSS}</style>" in page
    for directive in ("default-src 'none'", "connect-src 'none'", "base-uri 'none'", "form-action 'none'", "object-src 'none'"):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "http" not in csp
    assert csp.count("sha256-") == 2


def test_offline_html_viewer_assets_have_no_network_eval_storage_or_dynamic_markup() -> None:
    from schauwerk.resources.native_offline_html.assets import VIEWER_CSS, VIEWER_JS

    for forbidden in (
        "fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts",
        "eval(", "new Function", "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
        "localStorage", "sessionStorage", "indexedDB", "document.cookie", "window.open",
        "location.", "import(", "</script",
    ):
        assert forbidden not in VIEWER_JS, forbidden
    assert not re.search(r"https?:|//[a-z]|@import|url\(", VIEWER_CSS.replace("/*", ""))
    assert "http" not in VIEWER_JS


def test_offline_html_preserves_ids_edges_markers_and_escapes_every_text() -> None:
    page = _build().decode("utf-8")
    for source_id in ("grp", "a", "b", "c", "e1", "e2", "e3"):
        assert f'data-source-id="{source_id}"' in page
    assert page.count('<g id="native-node-') == 5
    assert page.count('<g id="native-edge-') == 3
    assert page.count("marker-end=") == 2 and page.count("marker-start=") == 1
    # Source ids and node text can never become markup or a second script.
    assert "<script>window.__pwn" not in page and "<img " not in page
    assert page.count("<script") == 1
    assert "&lt;img src=x onerror=&quot;window.__pwn=1&quot;&gt;" in page or "&lt;img src=x onerror=" in page
    assert 'data-node-id="n&quot;&gt;&lt;script&gt;window.__pwn=3&lt;/script&gt;&amp;amp;"' in page
    assert "Willkommen Welt" in page and "日本語" in page and "مرحبا" in page
    assert "notes/ziel.md#Abschnitt" in page
    # Link nodes are visible text only; the page never carries a navigable URL.
    assert "https://example.invalid/pfad?x=1&amp;y=2" in page
    tags = _markup(page)
    assert not {"a", "img", "iframe", "form", "link", "object", "embed", "image", "use", "foreignobject"} & {tag for tag, _ in tags}
    for tag, attributes in tags:
        assert not {"href", "src", "srcset", "action", "formaction", "style", "xlink:href"} & set(attributes), tag
        assert not any(name.startswith("on") for name in attributes), tag
    assert "Probe &lt;Schaubild&gt;" in page


def test_offline_html_drops_private_canvas_extensions_and_editor_state() -> None:
    canvas = _canvas()
    canvas["schauwerk"] = {"edgeRouting": "smart", "private": "do-not-export"}
    canvas["nodes"][1]["secretMetadata"] = "private-token-123"
    svg = _svg(canvas).replace("<svg ", '<svg id="nativeDiagram" class="native-diagram" ', 1).replace(
        '<g id="native-node-a" ',
        '<g id="native-node-a" class="is-selected" tabindex="0" role="button" aria-label="geheim-label" aria-selected="true" ',
    )
    page = build_offline_html(canvas, svg, title="T").html.decode("utf-8")
    for leaked in ("private-token-123", "do-not-export", "geheim-label", "is-selected", "aria-selected"):
        assert leaked not in page
    svg_markup = re.search(r"<svg .*</svg>", page, re.S).group(0)
    for tag, attributes in _markup(svg_markup):
        assert not {"class", "tabindex", "role"} & set(attributes), (tag, attributes)
    assert 'data-source-id="a"' in page and "data-input-digest" not in page
    assert "nativeDiagram" not in page and page.count('id="ofh-diagram"') == 1
    root = next(attributes for tag, attributes in _markup(svg_markup) if tag == "svg")
    assert root["id"] == "ofh-diagram"
    # Duplicate attributes would be silently resolved by the HTML parser; forbid them outright.
    for match in re.finditer(r"<([a-zA-Z]+)((?:\s+[^\s=>/]+=\"[^\"]*\")*)\s*/?>", svg_markup):
        names = re.findall(r"\s([^\s=]+)=", match.group(2))
        assert len(names) == len(set(names)), match.group(0)[:200]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.replace("</svg>", "<script>alert(1)</script></svg>"),
        lambda s: s.replace("</svg>", "<foreignObject><div>x</div></foreignObject></svg>"),
        lambda s: s.replace("</svg>", '<image href="https://evil.invalid/x.png"/></svg>'),
        lambda s: s.replace("</svg>", '<a href="https://evil.invalid/"><rect width="1" height="1"/></a></svg>'),
        lambda s: s.replace("</svg>", '<use href="#native-node-a"/></svg>'),
        lambda s: s.replace("</svg>", "<style>*{fill:url(https://evil.invalid/)}</style></svg>"),
        lambda s: s.replace("</svg>", '<animate attributeName="x" to="1"/></svg>'),
        lambda s: s.replace("<rect ", '<rect onload="alert(1)" ', 1),
        lambda s: s.replace("<rect ", '<rect style="fill:url(https://evil.invalid/x)" ', 1),
        lambda s: s.replace("<rect ", '<rect href="javascript:alert(1)" ', 1),
        lambda s: s.replace("<rect ", '<rect fill="url(https://evil.invalid/x)" ', 1),
        lambda s: s.replace('fill="#', 'fill="javascript:alert(1)" data-x="', 1),
        lambda s: s.replace("<rect ", '<rect xlink:href="x" ', 1),
        lambda s: s.replace("<rect ", '<rect unknown-attribute="1" ', 1),
        lambda s: s.replace("<rect ", '<rect fill="url(#missing)" ', 1),
        lambda s: s.replace('xmlns="http://www.w3.org/2000/svg"', 'xmlns="http://www.w3.org/1999/xhtml"', 1),
        lambda s: s.replace("<svg ", '<!DOCTYPE svg [<!ENTITY x "y">]><svg ', 1),
        lambda s: s.replace("<defs>", "<?php echo 1 ?><defs>", 1),
        lambda s: s.replace("</svg>", "<svg><g/></svg></svg>"),
        lambda s: s.replace("</svg>", "</svg>trailing"),
        lambda s: s.replace("<g id=\"native-edge-e1\"", "<g id=\"native-edge-zz\"", 1),
        lambda s: s.replace('data-source-id="e1"', 'data-source-id="e1x"', 1),
        lambda s: s.replace('<marker id="canvas-arrow-0"', '<marker id="ofh-diagram"', 1),
        lambda s: s.replace('data-canvas-type="text"', 'data-canvas-type="file"', 1),
        lambda s: s.replace('<g id="native-node-a"', '<g id="native-node-a"><text onclick="1"/></g><g id="native-node-a"', 1),
        lambda s: s.replace(' marker-end="url(#canvas-arrow-0)"', "", 1),
        lambda s: "not xml",
        lambda s: s.replace(' d="M', ' d="javascript:M', 1),
        lambda s: "<g/>",
    ],
)
def test_offline_html_rejects_active_foreign_or_incoherent_svg_visibly(mutation) -> None:
    canvas = _canvas()
    svg = mutation(_svg(canvas))
    with pytest.raises(OfflineHtmlError):
        build_offline_html(canvas, svg, title="T")


def test_offline_html_rejects_svg_that_lost_or_gained_a_node_or_start_marker() -> None:
    canvas = _canvas()
    svg = _svg(canvas)
    smaller = copy.deepcopy(canvas)
    smaller["nodes"] = [node for node in smaller["nodes"] if node["id"] != "c"]
    smaller["edges"] = [edge for edge in smaller["edges"] if edge["id"] != "e2"]
    with pytest.raises(OfflineHtmlError, match="do not match"):
        build_offline_html(smaller, svg, title="T")
    with pytest.raises(OfflineHtmlError, match="do not match"):
        build_offline_html(canvas, _svg(smaller), title="T")
    assert "marker-start" in svg
    with pytest.raises(OfflineHtmlError, match="start marker"):
        build_offline_html(canvas, svg.replace(" marker-start=", " data-lost=", 1), title="T")


@pytest.mark.parametrize("field", ["node", "edge", "svg-text"])
def test_offline_html_rejects_stale_canvas_or_svg_text_even_with_matching_ids(field: str) -> None:
    canvas = _canvas()
    svg = _svg(canvas)
    if field == "node":
        canvas["nodes"][1]["text"] = "Aktuell bearbeiteter Knotentext"
    elif field == "edge":
        canvas["edges"][0]["label"] = "Aktuelle Kantenbeschriftung"
    else:
        assert "führt zu" in svg
        svg = svg.replace("führt zu", "veralteter Text", 1)
    with pytest.raises(OfflineHtmlError, match="text"):
        build_offline_html(canvas, svg, title="T")


def test_offline_html_rejects_invalid_canvas_oversize_and_depth() -> None:
    canvas = _canvas()
    svg = _svg(canvas)
    with pytest.raises(OfflineHtmlError, match="invalid"):
        build_offline_html({"nodes": [{"id": "x", "type": "text"}]}, svg, title="T")
    with pytest.raises(OfflineHtmlError, match="size limit"):
        build_offline_html(canvas, svg + " " * (9 * 1024 * 1024), title="T")
    deep = svg.replace("<defs>", "<g>" * 20 + "</g>" * 20 + "<defs>", 1)
    with pytest.raises(OfflineHtmlError, match="deep"):
        build_offline_html(canvas, deep, title="T")
    with pytest.raises(OfflineHtmlError, match="text"):
        build_offline_html(canvas, svg, title=None)  # type: ignore[arg-type]
    big = copy.deepcopy(canvas)
    big["nodes"].extend(
        {"id": f"n{index}", "type": "text", "text": "x", "x": index, "y": 0, "width": 10, "height": 10}
        for index in range(200)
    )
    with pytest.raises(OfflineHtmlError, match="complexity"):
        build_offline_html(big, svg, title="T")


def test_offline_html_keeps_long_unicode_text_and_bounded_title() -> None:
    canvas = _canvas()
    canvas["nodes"][1]["text"] = ("Ünïcödé 😀 é " * 4000) + "ENDE"
    page = build_offline_html(canvas, _svg(canvas), title="T" * 5000 + "😀").html.decode("utf-8")
    assert "ENDE" in page  # the detail list keeps the full text; the SVG may clip visually
    assert len(re.search(r"<title>(.*?)</title>", page, re.S).group(1).encode("utf-8")) <= 4096
    assert len(page.encode("utf-8")) < MAX_OFFLINE_HTML_BYTES


@pytest.mark.parametrize(
    "mutator",
    [
        lambda canvas: canvas["schauwerk"].update({"edgeRouting": "smart"}) if "schauwerk" in canvas else canvas.update({"schauwerk": {"edgeRouting": "smart"}}),
        lambda canvas: canvas["edges"].append({"id": "loop", "fromNode": "a", "toNode": "a", "label": "Schleife"}),
        lambda canvas: canvas["edges"].append({"id": "back", "fromNode": "b", "toNode": "a", "fromSide": "top", "toSide": "top", "color": "2", "schauwerk": {"kind": "feedback"}}),
        lambda canvas: canvas["edges"].append({"id": "assoc", "fromNode": "a", "toNode": "c", "fromEnd": "arrow", "toEnd": "arrow", "schauwerk": {"kind": "association"}}),
        lambda canvas: canvas["nodes"].append({"id": "ünï", "type": "text", "text": "", "x": 900, "y": 900, "width": 20, "height": 20}),
    ],
)
def test_offline_html_accepts_what_the_real_renderer_emits(mutator) -> None:
    canvas = _canvas()
    mutator(canvas)
    result = build_offline_html(canvas, _svg(canvas), title="T")
    assert result.node_count == len(canvas["nodes"]) and result.edge_count == len(canvas["edges"])


def test_offline_html_handles_the_product_maximum_in_bounded_time() -> None:
    canvas = {
        "nodes": [
            {"id": f"n{index}", "type": "text", "text": f"Knoten {index} " + "wort " * 40, "x": (index % 16) * 300, "y": (index // 16) * 160, "width": 240, "height": 120}
            for index in range(128)
        ],
        "edges": [
            {"id": f"e{index}", "fromNode": f"n{index % 128}", "toNode": f"n{(index * 7 + 1) % 128}", "label": f"k{index}"}
            for index in range(180)
        ],
    }
    started = time.monotonic()
    result = build_offline_html(canvas, _svg(canvas), title="Maximum")
    assert time.monotonic() - started < 20
    assert result.node_count == 128 and result.edge_count == 180
    assert len(result.html) < MAX_OFFLINE_HTML_BYTES


def test_sanitized_svg_has_no_xml_declaration_and_one_root_with_viewer_id() -> None:
    sanitized = sanitize_native_svg(_svg(_canvas()))
    assert sanitized.markup.startswith('<svg xmlns="http://www.w3.org/2000/svg" ')
    assert sanitized.markup.count("<svg") == 1 and 'id="ofh-diagram"' in sanitized.markup
    assert "<?xml" not in sanitized.markup and ' width="' not in sanitized.markup.split(">", 1)[0]


# ------------------------------------------------------------------- route


def _serve(tmp_path: Path):
    output = tmp_path / "editor"
    build_standalone_editor(output)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_EditorRequestHandler, directory=str(output)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post(server, body: bytes, *, content_type: str = "application/json", host: str | None = None, path: str = "/api/native-offline-html", declared_length: int | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=20)
    try:
        headers = {"Content-Type": content_type, "Content-Length": str(len(body) if declared_length is None else declared_length)}
        connection.putrequest("POST", path, skip_host=host is not None)
        if host is not None:
            connection.putheader("Host", host)
        for key, value in headers.items():
            connection.putheader(key, value)
        connection.endheaders(body if declared_length is None else b"")
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _request(canvas: dict[str, Any] | None = None, **overrides: Any) -> bytes:
    canvas = canvas or _canvas()
    payload = {
        "schema_version": "schauwerk-native-offline-html-request.v1",
        "title": "Route",
        "canvas": canvas,
        "svg": _svg(canvas),
        **overrides,
    }
    return json.dumps(payload).encode("utf-8")


def test_offline_html_route_returns_exact_generator_bytes_with_download_headers(tmp_path: Path) -> None:
    server, thread = _serve(tmp_path)
    try:
        status, headers, body = _post(server, _request())
        assert status == 200
        expected = build_offline_html(_canvas(), _svg(_canvas()), title="Route")
        assert body == expected.html
        assert headers["Content-Type"] == "application/octet-stream"
        assert headers["X-Schauwerk-Offline-Html-Schema"] == OFFLINE_HTML_SCHEMA
        assert headers["X-Schauwerk-Output-SHA256"] == expected.sha256
        assert headers["X-Schauwerk-Source-SHA256"] == expected.source_sha256
        assert headers["Content-Disposition"].startswith("attachment;")
        assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_offline_html_route_enforces_input_boundaries(tmp_path: Path) -> None:
    server, thread = _serve(tmp_path)
    try:
        assert _post(server, _request(), content_type="text/plain")[0] == 415
        assert _post(server, _request(), content_type="application/x-www-form-urlencoded")[0] == 415
        assert _post(server, _request(), host="evil.example")[0] == 421
        assert _post(server, b"{", )[0] == 422
        assert _post(server, b"\xff\xfe")[0] == 422
        assert _post(server, json.dumps({"schema_version": "other"}).encode())[0] == 422
        assert _post(server, _request(extra=1))[0] == 422
        assert _post(server, _request(title=5))[0] == 422
        assert _post(server, _request(svg="<svg/>"))[0] == 422
        duplicate = b'{"schema_version":"schauwerk-native-offline-html-request.v1","title":"a","title":"b","canvas":{},"svg":""}'
        assert _post(server, duplicate)[0] == 422
        hostile = _canvas()
        status, _, body = _post(server, _request(hostile, svg=_svg(hostile).replace("</svg>", "<script>1</script></svg>")))
        assert status == 422 and b"not allowed" in body
        # An unsafe number token is refused instead of being rounded silently.
        unsafe = _request().decode().replace('"x": 0', '"x": 9007199254740993', 1).encode()
        assert _post(server, unsafe)[0] == 422
        assert _post(server, b"", declared_length=14 * 1024 * 1024 + 1)[0] == 413
        # Only POST on the exact path is served; the editor tree stays static.
        assert _post(server, _request(), path="/api/native-offline-html/x")[0] == 404
        with pytest.raises(Exception) as excinfo:
            urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/native-offline-html", timeout=5)
        assert "404" in str(excinfo.value) or "501" in str(excinfo.value)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_editor_offers_offline_html_only_through_guarded_native_canvas_path(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index = (output / "index.html").read_text(encoding="utf-8")
    script = (output / "app.js").read_text(encoding="utf-8")
    assert index.count('data-export="html-offline"') == 1
    button = re.search(r'<button[^>]*id="offlineHtmlButton"[^>]*>', index).group(0)
    assert " hidden" in button and "HTML (offline)" in index
    assert 'elements.offlineHtmlButton.hidden = !nativeCanvas;' in script
    assert 'activeEngine !== "native" || !currentNativeCanvas' in script
    assert 'format === "html-offline" && activeEngine !== "native"' in script
    # Export uses the live model and live SVG, then the shared prepareDownload path.
    assert "canvas: currentNativeCanvas," in script and "svg: liveSvg," in script
    assert 'serializeNativeFrameSvg({ stripInputDigest: true })' in script
    assert 'safeFilename(currentTitle) + ".html"' in script
    assert "requestedVersion !== exportRequestVersion" in script
    assert "/api/native-offline-html" in script
    # The route accepts the exact shared fidelity and size boundaries.
    assert "OFFLINE_HTML_MAX_REQUEST_BYTES = 14 * 1024 * 1024" in script


def test_dockerfile_copies_every_offline_html_runtime_module() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for path in (
        "src/schauwerk/visual/native_offline_html.py",
        "src/schauwerk/resources/native_offline_html/__init__.py",
        "src/schauwerk/resources/native_offline_html/assets.py",
    ):
        assert (ROOT / path).is_file()
        assert dockerfile.count(path) == 1, path
    assert "/app/src/schauwerk/resources/native_offline_html" in dockerfile
    assert "COPY src " not in dockerfile and "COPY . " not in dockerfile


# --------------------------------------------------------------- real Chrome


def _chrome() -> str | None:
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if found is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome/Chromium is required in CI for the offline HTML browser tests")
        pytest.skip("Chrome/Chromium is not installed")
    return found


class _Cdp:
    def __init__(self, chrome: str, profile: Path) -> None:
        from websockets.sync.client import connect

        self.proc = subprocess.Popen(
            [
                chrome, "--headless=new", "--no-first-run", "--disable-gpu", "--disable-dev-shm-usage",
                "--no-sandbox", "--disable-background-networking", "--remote-allow-origins=http://localhost",
                "--remote-debugging-port=0", f"--user-data-dir={profile}", "--window-size=1200,800", "about:blank",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        tab = None
        for _ in range(200):
            if self.proc.poll() is not None:
                pytest.fail("Chrome exited before CDP startup")
            try:
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    tab = next((item for item in json.load(response) if item.get("type") == "page"), None)
                if tab:
                    break
            except (OSError, ValueError, IndexError):
                pass
            time.sleep(0.1)
        assert tab is not None, "Chrome CDP endpoint failed to start"
        self.ws = connect(tab["webSocketDebuggerUrl"], origin="http://localhost", max_size=None)
        self.next_id = 0
        self.events: list[dict[str, Any]] = []
        for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            self.send(method)

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.next_id += 1
        request_id = self.next_id
        self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = json.loads(self.ws.recv(timeout=max(0.1, deadline - time.monotonic())))
            if message.get("id") == request_id:
                assert "error" not in message, message.get("error")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)
        raise AssertionError("CDP request timed out: " + method)

    def pump(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                message = json.loads(self.ws.recv(timeout=0.1))
            except TimeoutError:
                continue
            if "method" in message:
                self.events.append(message)

    def evaluate(self, expression: str) -> Any:
        result = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        assert "exceptionDetails" not in result, result.get("exceptionDetails")
        return result["result"].get("value")

    def wait_for(self, expression: str, label: str, seconds: float = 15) -> Any:
        end = time.monotonic() + seconds
        value = None
        while time.monotonic() < end:
            # Page.navigate can leave a transient execution context without
            # documentElement. Do not evaluate page selectors until DOM ready;
            # genuine JavaScript exceptions after load still fail immediately.
            value = self.evaluate(
                f"document.readyState === 'complete' && ({expression})"
            )
            if value:
                return value
            self.pump(0.1)
        raise AssertionError(f"timed out waiting for {label}: {value!r}")

    def navigate(self, url: str) -> None:
        self.send("Page.navigate", {"url": url})

    def key(self, key: str, *, text: str | None = None, shift: bool = False, code: str | None = None) -> None:
        modifiers = 8 if shift else 0
        base = {"key": key, "modifiers": modifiers, "code": code or key}
        self.send("Input.dispatchKeyEvent", {**base, "type": "keyDown", **({"text": text} if text else {})})
        self.send("Input.dispatchKeyEvent", {**base, "type": "keyUp"})

    def mouse(self, kind: str, x: float, y: float, **extra: Any) -> None:
        self.send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1, **extra})

    def violations(self) -> list[Any]:
        return self.evaluate("JSON.parse(JSON.stringify(window.__cspViolations || []))")

    def close(self) -> None:
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=6)


_VIOLATION_RECORDER = """
window.__cspViolations = [];
document.addEventListener('securitypolicyviolation', (event) => {
  window.__cspViolations.push({directive: event.violatedDirective, blocked: event.blockedURI});
});
"""


def _open(tmp_path: Path, name: str, payload: bytes) -> _Cdp:
    path = tmp_path / name
    path.write_bytes(payload)
    cdp = _Cdp(_chrome(), tmp_path / f"profile-{name}")
    cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": _VIOLATION_RECORDER})
    cdp.navigate(path.as_uri())
    return cdp


def _view_box(cdp: _Cdp) -> list[float]:
    return [float(part) for part in cdp.evaluate("document.getElementById('ofh-diagram').getAttribute('viewBox')").split()]


def _problems(cdp: _Cdp, document_url: str) -> list[str]:
    problems: list[str] = []
    for event in cdp.events:
        method, params = event["method"], event.get("params", {})
        if method == "Network.requestWillBeSent" and params["request"]["url"] != document_url:
            problems.append("request:" + params["request"]["url"][:120])
        if method == "Runtime.exceptionThrown":
            problems.append("exception:" + json.dumps(params)[:200])
        if method == "Log.entryAdded" and params["entry"]["level"] in {"error", "warning"}:
            problems.append("log:" + params["entry"]["text"][:200])
        if method == "Runtime.consoleAPICalled" and params["type"] in {"error", "warning"}:
            problems.append("console:" + json.dumps(params)[:200])
    return problems


@pytest.mark.parametrize("width,height", [(844, 390), (320, 700)])
def test_offline_html_file_url_side_panel_help_wraps_without_horizontal_overflow(
    tmp_path: Path, width: int, height: int,
) -> None:
    """Mobile file:// viewer must not hide help text behind horizontal scrolling."""
    cdp = _open(tmp_path, "responsive.html", _build())
    try:
        cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
        })
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "offline ready")
        cdp.pump(0.2)
        geometry = cdp.evaluate("""(() => {
          const side = document.querySelector('.ofh-side');
          const help = document.querySelector('#ofh-help');
          const headerBadge = document.querySelector('.ofh-bar .ofh-badge');
          return {
            viewport: window.innerWidth,
            clientWidth: side.clientWidth,
            scrollWidth: side.scrollWidth,
            helpWhiteSpace: getComputedStyle(help).whiteSpace,
            helpOverflowWrap: getComputedStyle(help).overflowWrap,
            headerWhiteSpace: getComputedStyle(headerBadge).whiteSpace
          };
        })()""")
        assert geometry["viewport"] == width
        assert geometry["clientWidth"] > 0
        assert geometry["scrollWidth"] <= geometry["clientWidth"] + 1, geometry
        assert geometry["helpWhiteSpace"] == "normal"
        assert geometry["helpOverflowWrap"] == "anywhere"
        assert geometry["headerWhiteSpace"] == "nowrap"
        assert cdp.violations() == []
    finally:
        cdp.close()


def test_offline_html_file_url_chrome_is_usable_read_only_and_makes_no_requests(tmp_path: Path) -> None:
    html = _build()
    cdp = _open(tmp_path, "viewer.html", html)
    url = (tmp_path / "viewer.html").as_uri()
    try:
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "viewer ready")
        assert cdp.evaluate("location.protocol") == "file:"
        fitted = _view_box(cdp)
        assert cdp.evaluate("document.querySelectorAll('[data-source-kind=node]').length") == 5
        assert cdp.evaluate("document.querySelectorAll('[data-source-kind=edge]').length") == 3
        assert cdp.evaluate("document.querySelectorAll('marker').length") >= 1
        assert cdp.evaluate("document.querySelectorAll('script').length") == 1
        assert cdp.evaluate("document.querySelectorAll('a[href],img,iframe,form,link,object,embed').length") == 0
        assert cdp.evaluate("document.querySelectorAll('[contenteditable],textarea').length") == 0
        # The drawn card text really is part of the page, rendered from the passive SVG.
        assert "Willkommen" in cdp.evaluate("document.getElementById('ofh-diagram').textContent")

        rect = cdp.evaluate("(()=>{const r=document.getElementById('ofh-stage').getBoundingClientRect();return [r.left,r.top,r.width,r.height]})()")
        centre_x, centre_y = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2

        # Wheel zoom around the pointer.
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": centre_x, "y": centre_y, "deltaX": 0, "deltaY": -400})
        cdp.pump(0.2)
        zoomed = _view_box(cdp)
        assert zoomed[2] < fitted[2] * 0.9 and zoomed[3] < fitted[3] * 0.9

        # Drag pans in the direction of the pointer.
        cdp.mouse("mousePressed", centre_x, centre_y)
        cdp.mouse("mouseMoved", centre_x + 60, centre_y + 30)
        cdp.mouse("mouseMoved", centre_x + 120, centre_y + 60)
        cdp.mouse("mouseReleased", centre_x + 120, centre_y + 60, buttons=0)
        cdp.pump(0.2)
        panned = _view_box(cdp)
        assert panned[0] < zoomed[0] and panned[1] < zoomed[1]
        assert panned[2] == pytest.approx(zoomed[2], rel=1e-6)

        # Keyboard: focus, zoom, pan, fit.
        cdp.evaluate("document.getElementById('ofh-stage').focus()")
        cdp.key("+", text="+")
        assert _view_box(cdp)[2] < panned[2]
        cdp.key("ArrowRight", code="ArrowRight")
        cdp.key("0", text="0")
        assert _view_box(cdp) == pytest.approx(fitted, rel=1e-4)
        cdp.key("-", text="-")
        assert _view_box(cdp)[2] > fitted[2]
        cdp.evaluate("document.getElementById('ofh-fit').click()")
        assert _view_box(cdp) == pytest.approx(fitted, rel=1e-4)
        cdp.evaluate("document.getElementById('ofh-zoom-in').click()")
        assert _view_box(cdp)[2] < fitted[2]
        cdp.evaluate("document.getElementById('ofh-fit').click()")

        # Pinch with two synthetic pointers zooms in.
        pinch = cdp.evaluate(
            """(()=>{const s=document.getElementById('ofh-stage');
            s.setPointerCapture=()=>{};
            const w0=document.getElementById('ofh-diagram').viewBox.baseVal.width;
            const ev=(t,id,x,y)=>s.dispatchEvent(new PointerEvent(t,{pointerId:id,pointerType:'touch',clientX:x,clientY:y,bubbles:true,isPrimary:id===1,button:0}));
            ev('pointerdown',1,400,300);ev('pointerdown',2,500,300);
            ev('pointermove',2,700,300);ev('pointerup',1,400,300);ev('pointerup',2,700,300);
            return w0/document.getElementById('ofh-diagram').viewBox.baseVal.width})()"""
        )
        assert pinch > 1.5
        cdp.evaluate("document.getElementById('ofh-fit').click()")

        # Search with "/" focus, filtering, focus-on-node and the full-text detail.
        cdp.evaluate("document.getElementById('ofh-stage').focus()")
        cdp.key("/", text="/")
        assert cdp.evaluate("document.activeElement.id") == "ofh-search"
        cdp.send("Input.insertText", {"text": "Welt"})
        cdp.pump(0.2)
        assert cdp.evaluate("document.getElementById('ofh-status').textContent") == "1 von 5 Knoten gefunden"
        assert cdp.evaluate("[...document.querySelectorAll('#ofh-results li:not([hidden])')].map(li=>li.dataset.nodeId)") == ["a"]
        assert cdp.evaluate("document.getElementById('ofh-diagram').classList.contains('ofh-searching')")
        cdp.key("Enter", code="Enter", text="\r")
        assert cdp.evaluate("document.querySelector('g.ofh-focus').dataset.sourceId") == "a"
        assert _view_box(cdp)[2] < fitted[2]
        assert "zweite Zeile ✓ 日本語 مرحبا" in cdp.evaluate("document.getElementById('ofh-detail-text').textContent")
        cdp.key("Escape", code="Escape")
        assert cdp.evaluate("document.activeElement.id") == "ofh-stage"
        assert cdp.evaluate("document.getElementById('ofh-search').value") == ""
        assert cdp.evaluate("document.querySelectorAll('#ofh-results li[hidden]').length") == 0

        # IDs with hostile characters are searchable and focusable as plain data.
        cdp.evaluate("document.getElementById('ofh-search').focus()")
        cdp.send("Input.insertText", {"text": "pwn=3"})
        cdp.pump(0.2)
        cdp.key("Enter", code="Enter", text="\r")
        assert cdp.evaluate("document.querySelector('g.ofh-focus').dataset.sourceId") == HOSTILE_ID
        cdp.evaluate("document.getElementById('ofh-search').value=''")

        # Read-only: nothing the viewer exposes changes the document markup.
        before = cdp.evaluate("document.getElementById('ofh-diagram').innerHTML.length")
        cdp.key("Delete", code="Delete")
        cdp.key("Backspace", code="Backspace")
        assert cdp.evaluate("document.getElementById('ofh-diagram').innerHTML.length") == before

        # Offline emulation plus reload: still fully usable, still no request.
        cdp.send("Network.emulateNetworkConditions", {"offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0})
        cdp.events.clear()
        cdp.navigate(url)
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "offline reload ready")
        cdp.pump(0.5)
        assert cdp.violations() == []
        assert _problems(cdp, url) == []
    finally:
        cdp.close()


def test_offline_html_chrome_keeps_hostile_text_and_ids_inert(tmp_path: Path) -> None:
    html = _build()
    cdp = _open(tmp_path, "hostile.html", html)
    url = (tmp_path / "hostile.html").as_uri()
    try:
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "viewer ready")
        cdp.pump(0.5)
        assert cdp.evaluate("typeof window.__pwn") == "undefined"
        assert cdp.evaluate("document.querySelectorAll('script').length") == 1
        assert cdp.evaluate("document.querySelectorAll('img').length") == 0
        shown = cdp.evaluate("[...document.querySelectorAll('#ofh-results .ofh-text')].map(e=>e.textContent)")
        assert INJECTION_TEXT in shown
        assert HOSTILE_ID in cdp.evaluate("[...document.querySelectorAll('#ofh-results li')].map(e=>e.dataset.nodeId)")
        assert cdp.violations() == []
        assert _problems(cdp, url) == []
    finally:
        cdp.close()


def test_offline_html_chrome_csp_hash_binding_blocks_a_tampered_file(tmp_path: Path) -> None:
    html = _build().decode("utf-8")
    injected = html.replace("</body>", "<script>window.__pwn=9</script></body>")
    assert injected != html
    cdp = _open(tmp_path, "tampered.html", injected.encode("utf-8"))
    try:
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "hash-bound viewer script still runs")
        cdp.pump(0.5)
        # The unlisted inline script is refused under file://; the bound one ran.
        assert cdp.evaluate("typeof window.__pwn") == "undefined"
        assert any(item["directive"].startswith("script-src") for item in cdp.violations())
    finally:
        cdp.close()
    changed = html.replace("function fit()", "function fit_()")
    assert changed != html
    cdp = _open(tmp_path, "edited-script.html", changed.encode("utf-8"))
    try:
        cdp.pump(1.0)
        assert not cdp.evaluate("document.documentElement.classList.contains('ofh-ready')")
        assert any(item["directive"].startswith("script-src") for item in cdp.violations())
    finally:
        cdp.close()


def test_offline_html_chrome_loads_the_product_maximum(tmp_path: Path) -> None:
    canvas = {
        "nodes": [
            {"id": f"n{index}", "type": "text", "text": f"Knoten {index}", "x": (index % 16) * 300, "y": (index // 16) * 160, "width": 240, "height": 120}
            for index in range(128)
        ],
        "edges": [
            {"id": f"e{index}", "fromNode": f"n{index % 128}", "toNode": f"n{(index * 7 + 1) % 128}"}
            for index in range(180)
        ],
    }
    cdp = _open(tmp_path, "maximum.html", _build(canvas, title="Maximum"))
    try:
        cdp.wait_for("document.documentElement.classList.contains('ofh-ready')", "maximum viewer ready", 30)
        assert cdp.evaluate("document.querySelectorAll('[data-source-kind=node]').length") == 128
        cdp.evaluate("document.getElementById('ofh-search').focus()")
        cdp.send("Input.insertText", {"text": "knoten 127"})
        cdp.pump(0.2)
        assert cdp.evaluate("document.getElementById('ofh-status').textContent") == "1 von 128 Knoten gefunden"
        assert cdp.violations() == []
    finally:
        cdp.close()


def test_editor_exports_the_current_edited_canvas_as_working_offline_html(tmp_path: Path) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("editor browser export runs in the Python 3.12 CI lane")
    server, thread = _serve(tmp_path)
    canvas = {
        "nodes": [
            {"id": "a", "type": "text", "text": "Alpha", "x": 0, "y": 0, "width": 200, "height": 90},
            {"id": "b", "type": "text", "text": "Beta", "x": 360, "y": 40, "width": 200, "height": 90},
        ],
        "edges": [{"id": "e", "fromNode": "a", "toNode": "b", "label": "weiter"}],
    }
    cdp = _Cdp(_chrome(), tmp_path / "profile-editor")
    try:
        # The editor CSP forbids fetch(blob:); record the prepared Blob objects instead.
        cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": (
            "window.__blobs = new Map(); const create = URL.createObjectURL.bind(URL);"
            "URL.createObjectURL = (blob) => { const url = create(blob); window.__blobs.set(url, blob); return url; };"
        )})
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        cdp.navigate(f"http://127.0.0.1:{server.server_address[1]}/")
        cdp.wait_for("document.readyState === 'complete' && !!document.querySelector('#openPasteButton')", "editor shell")
        cdp.evaluate(
            "document.querySelector('#sourceInput').value = " + json.dumps(json.dumps(canvas))
            + "; document.querySelector('#openPasteButton').click(); true"
        )
        cdp.wait_for(
            "!document.querySelector('#workspace').hidden && document.querySelector('#editorFrame').src.includes('/native/')"
            " && !!document.querySelector('#editorFrame').contentDocument?.querySelector('[data-source-id=\"a\"]')",
            "native canvas ready", 30,
        )
        cdp.wait_for("!document.querySelector('#offlineHtmlButton').hidden", "offline button offered for Canvas")
        cdp.wait_for("!document.querySelector('#offlineHtmlButton').disabled", "offline button enabled")

        # Edit the live document: drag node "a" in the hosted viewer.
        cdp.evaluate(
            """(async () => {
              const doc = document.querySelector('#editorFrame').contentDocument;
              const win = document.querySelector('#editorFrame').contentWindow;
              win.Element.prototype.setPointerCapture = function () {};
              const node = doc.querySelector('[data-source-kind="node"][data-source-id="a"]');
              const viewport = doc.querySelector('#nativeViewport');
              const r = node.getBoundingClientRect();
              const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
              const fire = (target, type, px, py) => target.dispatchEvent(new win.PointerEvent(type, {
                bubbles: true, pointerId: 41, pointerType: 'touch', clientX: px, clientY: py,
                button: 0, buttons: type === 'pointerup' ? 0 : 1, isPrimary: true }));
              fire(node, 'pointerdown', x, y);
              fire(viewport, 'pointermove', x + 40, y + 160);
              fire(viewport, 'pointermove', x + 60, y + 220);
              fire(viewport, 'pointerup', x + 60, y + 220);
              await new Promise(r => setTimeout(r, 400));
              return true;
            })()"""
        )
        cdp.wait_for("document.querySelector('#editorFrame').contentDocument.querySelector('[data-source-id=\"a\"]') !== null", "frame after edit")

        # Export from the Export menu; the download is a blob prepared by prepareDownload.
        cdp.evaluate("document.querySelector('.workspace-export-menu').open = true; document.querySelector('#offlineHtmlButton').click(); true")
        cdp.wait_for("!document.querySelector('#downloadLink').hidden", "prepared download", 30)
        assert cdp.evaluate("document.querySelector('#downloadLink').download") == "Schaubild.html"
        assert cdp.evaluate("document.querySelector('#downloadLink .download-caption').textContent") == "HTML (offline) speichern"
        exported = cdp.evaluate("window.__blobs.get(document.querySelector('#downloadLink').href).text()")
        assert cdp.evaluate("window.__blobs.get(document.querySelector('#downloadLink').href).type") == "text/html;charset=utf-8"
        assert exported.startswith("<!doctype html>") and 'data-source-id="a"' in exported and 'data-source-id="b"' in exported
        # The export reflects the dragged position, not the originally pasted one.
        exported_a = re.search(r'<g id="native-node-a"[^>]*transform="translate\((-?[\d.]+) (-?[\d.]+)\)"', exported)
        assert exported_a is not None, "dragged node position missing from the export"
        assert float(exported_a.group(2)) > 100
        assert 'class="is-selected' not in exported and "aria-selected" not in exported
        assert 'data-source-id="b"' in exported and 'data-source-id="e"' in exported
        # Load the downloaded bytes through file:// in a fresh browser (http -> file navigation is blocked).
        viewer = _open(tmp_path, "exported.html", exported.encode("utf-8"))
        try:
            viewer.wait_for("document.documentElement.classList.contains('ofh-ready')", "exported file ready via file://")
            viewer.pump(0.4)
            assert viewer.violations() == []
            assert _problems(viewer, (tmp_path / "exported.html").as_uri()) == []
            assert viewer.evaluate("[...document.querySelectorAll('#ofh-results .ofh-text')].map(e=>e.textContent)") == ["Alpha", "Beta"]
            assert "translate(" in viewer.evaluate("document.querySelector('g[data-source-id=a]').getAttribute('transform')")
        finally:
            viewer.close()
    finally:
        cdp.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_editor_hides_offline_html_for_non_canvas_sources(tmp_path: Path) -> None:
    if os.environ.get("CI") and sys.version_info[:2] != (3, 12):
        pytest.skip("editor browser export runs in the Python 3.12 CI lane")
    server, thread = _serve(tmp_path)
    xml = (
        '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="a" value="Ali" vertex="1" parent="1"><mxGeometry x="20" y="20" width="140" height="60" as="geometry"/>'
        "</mxCell></root></mxGraphModel>"
    )
    cdp = _Cdp(_chrome(), tmp_path / "profile-editor2")
    try:
        cdp.navigate(f"http://127.0.0.1:{server.server_address[1]}/")
        cdp.wait_for("document.readyState === 'complete' && !!document.querySelector('#openPasteButton')", "editor shell")
        cdp.evaluate(
            "document.querySelector('#sourceInput').value = " + json.dumps(xml)
            + "; document.querySelector('#openPasteButton').click(); true"
        )
        cdp.wait_for("!document.querySelector('#workspace').hidden && document.querySelector('#editorFrame').src.includes('/native/')", "draw.io import ready", 30)
        assert cdp.evaluate("document.querySelector('#offlineHtmlButton').hidden") is True
        # Even a forced click on a hidden action cannot produce a file.
        cdp.evaluate("document.querySelector('#offlineHtmlButton').click(); true")
        cdp.pump(0.5)
        assert cdp.evaluate("document.querySelector('#downloadLink').hidden") is True
    finally:
        cdp.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
