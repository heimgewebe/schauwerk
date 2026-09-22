from __future__ import annotations

import json
import re
import threading
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from schauwerk.visual.native_document import (
    NATIVE_DOCUMENT_SCHEMA,
    editing_document_to_json_canvas,
)
from schauwerk.visual.standalone_editor import (
    EDITOR_ORIGIN,
    NATIVE_API_PATH,
    NATIVE_IMPORT_SCHEMA,
    NATIVE_RENDERER,
    StandaloneEditorError,
    _EditorRequestHandler,
    _native_product_input,
    build_standalone_editor,
)


def _canvas() -> dict:
    return {
        "customTopLevel": {"keep": True},
        "nodes": [
            {
                "id": "group-a",
                "type": "group",
                "x": -200,
                "y": 30,
                "width": 760,
                "height": 430,
                "label": "Bereich",
            },
            {
                "id": "source",
                "type": "text",
                "x": -120,
                "y": 120,
                "width": 240,
                "height": 130,
                "text": "Quelle – 東京",
                "color": "5",
                "customNode": 17,
            },
            {
                "id": "target",
                "type": "text",
                "x": 260,
                "y": 160,
                "width": 280,
                "height": 150,
                "text": "Ziel",
            },
        ],
        "edges": [
            {
                "id": "edge-a",
                "fromNode": "source",
                "fromSide": "right",
                "toNode": "target",
                "toSide": "left",
                "toEnd": "arrow",
                "label": "führt zu",
                "customEdge": "keep",
            }
        ],
    }


def _request(canvas: dict | None = None) -> dict:
    return {
        "schema_version": NATIVE_IMPORT_SCHEMA,
        "format": "json-canvas-1.0",
        "source": _canvas() if canvas is None else canvas,
        "title": "Probe.canvas",
    }


def test_native_product_input_accepts_canvas_without_losing_geometry_or_extensions() -> None:
    source = _canvas()
    document = _native_product_input(_request(source))

    assert document["schema_version"] == NATIVE_DOCUMENT_SCHEMA
    assert document["source_format"] == "json-canvas-1.0"
    assert document["title"] == "Probe.canvas"
    assert [
        (node["id"], node["x"], node["y"], node["width"], node["height"])
        for node in document["nodes"]
    ] == [
        ("group-a", -200, 30, 760, 430),
        ("source", -120, 120, 240, 130),
        ("target", 260, 160, 280, 150),
    ]
    assert editing_document_to_json_canvas(document) == source


def test_native_product_input_rebinds_digest_to_current_document_state() -> None:
    document = _native_product_input(_request())
    original_digest = document["source_digest"]

    unchanged = _native_product_input(json.loads(json.dumps(document)))
    assert unchanged["source_digest"] == original_digest

    edited = json.loads(json.dumps(document))
    edited["nodes"][1]["x"] += 37
    edited["documentExtension"] = {"keep": True}
    rebound = _native_product_input(edited)

    assert rebound["source_digest"] != original_digest
    assert rebound["input_digest"] == rebound["source_digest"]
    assert rebound["source"]["customTopLevel"] == {"keep": True}
    assert rebound["documentExtension"] == {"keep": True}
    assert editing_document_to_json_canvas(rebound)["nodes"][1]["x"] == -83


def test_native_product_input_rejects_unsupported_canvas_node_type() -> None:
    source = _canvas()
    source["nodes"][1]["type"] = "video"
    with pytest.raises(StandaloneEditorError, match="unsupported"):
        _native_product_input(_request(source))


def test_standalone_shell_routes_json_canvas_to_native_document_not_drawio(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    manifest = build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")

    canvas_start = app_js.index('if (detected.kind === "json-canvas")')
    drawio_start = app_js.index('if (detected.kind === "drawio")', canvas_start)
    canvas_branch = app_js[canvas_start:drawio_start]

    assert 'format: "json-canvas-1.0"' in canvas_branch
    assert "nativeCanvas: detected.value" in canvas_branch
    assert "jsonCanvasToDrawioXml" not in canvas_branch
    assert "native-document-change" in app_js
    assert "native-document-rebuild" in app_js
    assert 'safeFilename(currentTitle) + ".canvas"' in app_js
    assert "json-canvas-1.0" in manifest["native_renderer"]["supported_inputs"]
    assert "json-canvas-1.0" in manifest["native_renderer"]["supported_outputs"]


def test_integrated_native_canvas_endpoint_preserves_layout_and_serves_editing_contract(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "NativeCanvasEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(_request(), ensure_ascii=False).encode("utf-8")
        connection = HTTPConnection(
            "127.0.0.1", int(server.server_address[1]), timeout=5
        )
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert body["renderer"] == NATIVE_RENDERER
        assert re.fullmatch(r"[0-9a-f]{64}", body["input_digest"])
        assert re.fullmatch(r"/native/[0-9a-f]{32}/index\.html", body["url"])

        connection.request("GET", body["url"])
        viewer_response = connection.getresponse()
        viewer_html = viewer_response.read().decode("utf-8")
        assert viewer_response.status == 200
        assert 'data-document-mode="json-canvas"' in viewer_html
        assert 'id="addNode"' in viewer_html
        assert 'id="addEdge"' in viewer_html
        assert 'id="editText"' in viewer_html
        assert 'id="reattachSource"' in viewer_html
        assert 'id="reattachTarget"' in viewer_html
        assert 'id="deleteSelection"' in viewer_html

        viewer_app_url = body["url"].replace("index.html", "app.js")
        connection.request("GET", viewer_app_url)
        viewer_app_response = connection.getresponse()
        viewer_app = viewer_app_response.read().decode("utf-8")
        assert viewer_app_response.status == 200
        assert (
            "const documentEditorHosted = documentMode && window.parent !== window;"
            in viewer_app
        )
        assert "if (documentEditorHosted) {" in viewer_app
        assert "Dokumentansicht · Bearbeiten im Schaubild-Host" in viewer_app
        assert 'reattachSourceButton?.addEventListener("click"' in viewer_app
        assert 'reattachTargetButton?.addEventListener("click"' in viewer_app

        document_url = body["url"].replace("index.html", "document.json")
        connection.request("GET", document_url)
        document_response = connection.getresponse()
        document = json.loads(document_response.read().decode("utf-8"))
        assert document_response.status == 200
        by_id = {node["id"]: node for node in document["nodes"]}
        assert (
            by_id["source"]["x"],
            by_id["source"]["y"],
            by_id["source"]["width"],
            by_id["source"]["height"],
        ) == (-120, 120, 240, 130)
        assert editing_document_to_json_canvas(document) == _canvas()

        original_digest = body["input_digest"]
        original_url = body["url"]
        edited_source = next(
            node for node in document["nodes"] if node["id"] == "source"
        )
        edited_source["x"] = -83
        rebuild_payload = json.dumps(document, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=rebuild_payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(rebuild_payload)),
            },
        )
        rebuild_response = connection.getresponse()
        rebuild_body = json.loads(rebuild_response.read().decode("utf-8"))
        assert rebuild_response.status == 200
        assert rebuild_body["input_digest"] != original_digest
        assert rebuild_body["url"] != original_url

        rebuilt_document_url = rebuild_body["url"].replace(
            "index.html", "document.json"
        )
        connection.request("GET", rebuilt_document_url)
        rebuilt_document_response = connection.getresponse()
        rebuilt_document = json.loads(
            rebuilt_document_response.read().decode("utf-8")
        )
        assert rebuilt_document_response.status == 200
        rebuilt_by_id = {
            node["id"]: node for node in rebuilt_document["nodes"]
        }
        assert rebuilt_by_id["source"]["x"] == -83
        assert rebuilt_document["source_digest"] == rebuild_body["input_digest"]
        assert rebuilt_document["input_digest"] == rebuild_body["input_digest"]

        diagram_url = body["url"].replace("index.html", "diagram.svg")
        connection.request("GET", diagram_url)
        diagram_response = connection.getresponse()
        diagram_svg = diagram_response.read().decode("utf-8")
        assert diagram_response.status == 200
        assert 'data-document-mode="json-canvas"' in diagram_svg
        assert 'x="-120" y="120" width="240" height="130"' in diagram_svg
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)




def test_integrated_native_canvas_cache_identity_includes_title(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    handler_class = type(
        "NativeCanvasTitleCacheRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(handler_class, directory=str(output)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(
            "127.0.0.1", int(server.server_address[1]), timeout=5
        )
        results: list[dict] = []
        for title in ("Erste.canvas", "Zweite.canvas"):
            request = _request()
            request["title"] = title
            payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
            connection.request(
                "POST",
                NATIVE_API_PATH,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
            )
            response = connection.getresponse()
            result = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            results.append(result)

        assert results[0]["input_digest"] == results[1]["input_digest"]
        assert results[0]["url"] != results[1]["url"]

        for result, expected_title in zip(
            results, ("Erste.canvas", "Zweite.canvas"), strict=True
        ):
            connection.request("GET", result["url"])
            response = connection.getresponse()
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert f"<title>{expected_title}</title>" in html
            assert f"<strong>{expected_title}</strong>" in html
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_integrated_native_canvas_endpoint_fails_closed_for_unknown_reference(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    source = _canvas()
    source["edges"][0]["toNode"] = "missing"

    handler_class = type(
        "InvalidNativeCanvasEditorRequestHandler",
        (_EditorRequestHandler,),
        {"editor_origin": EDITOR_ORIGIN},
    )
    handler = partial(handler_class, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(_request(source)).encode("utf-8")
        connection = HTTPConnection(
            "127.0.0.1", int(server.server_address[1]), timeout=5
        )
        connection.request(
            "POST",
            NATIVE_API_PATH,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 422
        assert "unknown node" in body["error"]
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)