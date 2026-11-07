"""Live and saved JSON Canvas smart-edge routing contract tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.resources.native_viewer.assets import ASSETS
from schauwerk.visual.native_canvas_smart_router import route_edge
from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import (
    NativeDocumentError,
    editing_document_to_json_canvas,
    json_canvas_to_editing_document,
    normalize_editing_document,
    validate_json_canvas,
)

SVG = "{http://www.w3.org/2000/svg}"


def canvas(*, routing: str | None = "smart", obstacle: bool = True) -> dict:
    nodes = [
        {"id": "start", "type": "text", "x": 0, "y": 0, "width": 100,
         "height": 80, "text": "Start"},
        {"id": "end", "type": "text", "x": 400, "y": 0, "width": 100,
         "height": 80, "text": "Ende"},
    ]
    if obstacle:
        nodes.append({"id": "blocker", "type": "text", "x": 200, "y": 0,
                      "width": 100, "height": 80, "text": "Hindernis"})
    source = {
        "nodes": nodes,
        "edges": [{"id": "e", "fromNode": "start", "toNode": "end",
                   "label": "Eine Beziehung", "toEnd": "arrow"}],
    }
    if routing is not None:
        source["schauwerk"] = {"edgeRouting": routing}
    return source


def render(source: dict) -> ET.Element:
    return ET.fromstring(render_native_editing_document(
        json_canvas_to_editing_document(source)
    ))


def edge_group(root: ET.Element) -> ET.Element:
    return next(g for g in root.iter(SVG + "g")
                if g.get("data-source-kind") == "edge")


def path_data(root: ET.Element) -> str:
    path = edge_group(root).find(SVG + "path")
    assert path is not None
    return str(path.get("d"))


def test_legacy_canvas_routes_are_not_migrated_silently() -> None:
    legacy = render(canvas(routing=None))
    simple = render(canvas(routing="simple"))
    smart = render(canvas(routing="smart"))
    assert legacy.get("data-edge-routing") is None
    assert simple.get("data-edge-routing") is None
    assert smart.get("data-edge-routing") == "smart"
    assert path_data(legacy) == path_data(simple)
    assert edge_group(legacy).get("data-route") != "canvas-smart"
    assert edge_group(smart).get("data-route") == "canvas-smart"
    assert path_data(smart) != path_data(simple)


def test_smart_render_avoids_blocking_node_and_keeps_label_visible() -> None:
    source = canvas()
    rendered = render(source)
    group = edge_group(rendered)
    original_nodes = source["nodes"]
    expected = route_edge(original_nodes[0], original_nodes[1], original_nodes)
    assert expected is not None
    assert path_data(rendered) == expected.path
    assert group.get("data-routing-conflict") is None
    assert group.get("data-canonical-stroke")
    label = next(r for r in group.findall(SVG + "rect")
                 if float(r.get("width", "0")) > 0)
    label_box = (
        float(label.get("x", "0")), float(label.get("y", "0")),
        float(label.get("x", "0")) + float(label.get("width", "0")),
        float(label.get("y", "0")) + float(label.get("height", "0")),
    )
    b = source["nodes"][2]
    obstacle_box = (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])
    assert not (
        label_box[0] < obstacle_box[2] and label_box[2] > obstacle_box[0]
        and label_box[1] < obstacle_box[3] and label_box[3] > obstacle_box[1]
    )


def test_manual_ports_remain_respected_through_source_roundtrip() -> None:
    source = canvas()
    source["edges"][0]["fromSide"] = "top"
    source["edges"][0]["toSide"] = "bottom"
    doc = json_canvas_to_editing_document(source)
    doc["edges"][0]["label"] = "Bearbeitet"
    refreshed = normalize_editing_document(doc)
    roundtrip = editing_document_to_json_canvas(refreshed)
    assert roundtrip["schauwerk"] == {"edgeRouting": "smart"}
    assert roundtrip["edges"][0]["fromSide"] == "top"
    assert roundtrip["edges"][0]["toSide"] == "bottom"
    result = edge_group(render(roundtrip))
    assert result.get("data-route") == "canvas-smart"
    assert result.get("data-routing-conflict") is None
    assert result.find(SVG + "title").text == "Bearbeitet"


def test_routing_mode_rejects_invalid_extension_values() -> None:
    for invalid in ("fast", None, False, 2, ["smart"], {"mode": "smart"}):
        source = canvas()
        source["schauwerk"]["edgeRouting"] = invalid
        with pytest.raises(NativeDocumentError):
            validate_json_canvas(source)
    source = canvas()
    source["schauwerk"] = "smart"
    with pytest.raises(NativeDocumentError):
        validate_json_canvas(source)


def test_unresolvable_smart_path_is_marked_as_conflict() -> None:
    source = canvas()
    source["nodes"].append({
        "id": "wall", "type": "text", "x": -200, "y": -200,
        "width": 900, "height": 500, "text": "Blockierter Bereich",
    })
    result = edge_group(render(source))
    assert result.get("data-route") == "canvas-smart-conflict"
    assert result.get("data-routing-conflict") == "true"
    path = result.find(SVG + "path")
    assert path is not None and path.get("stroke-dasharray") == "6 4"
    assert "Kein hindernisfreier Weg" in (result.find(SVG + "title").text or "")


def test_browser_router_resource_is_bundled_without_external_dependency() -> None:
    assert "smart-router.js" in ASSETS
    assert "export function smartEdgeGeometry(" in ASSETS["smart-router.js"]
    assert 'import { smartEdgeGeometry } from "./smart-router.js";' in ASSETS["app.js"]
    assert "documentSnapshot()" in ASSETS["app.js"]
    assert 'id="smartRouting"' in ASSETS["styles.css"] or 'id="smartRouting"' in __import__(
        "schauwerk.resources.native_viewer.assets",
        fromlist=["INDEX_HTML"],
    ).INDEX_HTML


def test_javascript_router_tracks_python_geometry_on_fixture(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not available for standalone JavaScript geometry check")
    script = tmp_path / "smart-router.mjs"
    script.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    a, b, blocker = canvas()["nodes"]
    runner = tmp_path / "check.mjs"
    runner.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps([a, b, blocker])};\n"
        "console.log(JSON.stringify(smartEdgeGeometry(nodes[0],nodes[1],nodes)));\n",
        encoding="utf-8",
    )
    outcome = subprocess.run([node, str(runner)], capture_output=True,
                             text=True, timeout=10, check=True)
    actual = json.loads(outcome.stdout)
    expected = route_edge(a, b, [a, b, blocker])
    assert actual is not None and expected is not None
    assert actual["fromSide"] == expected.from_side
    assert actual["toSide"] == expected.to_side
    assert actual["collisionFree"] is True
    assert actual["path"] == expected.path


def test_relation_direction_and_type_survive_canvas_and_svg_roundtrip() -> None:
    source = canvas()
    edge = source["edges"][0]
    edge["fromEnd"] = "arrow"
    edge["toEnd"] = "none"
    edge["schauwerk"] = {"kind": "association"}
    document = json_canvas_to_editing_document(source)
    exported = editing_document_to_json_canvas(normalize_editing_document(document))
    assert exported["edges"] == source["edges"]
    assert exported["schauwerk"]["edgeRouting"] == "smart"
    rendered = edge_group(render(exported))
    assert rendered.get("data-relation-kind") == "association"
    assert rendered.get("data-route") == "canvas-smart"
    path = rendered.find(SVG + "path")
    assert path is not None
    assert path.get("marker-start", "").startswith("url(")
    assert path.get("marker-end") is None
    assert path.get("stroke-dasharray") == "3 5"

    edge["schauwerk"]["kind"] = "feedback"
    feedback = edge_group(render(source))
    assert feedback.get("data-relation-kind") == "feedback"
    assert feedback.find(SVG + "path").get("stroke-dasharray") == "10 5"


def test_relation_kind_validation_rejects_unsupported_values() -> None:
    for kind in ("unknown", [], None, 3, False):
        source = canvas()
        source["edges"][0]["schauwerk"] = {"kind": kind}
        with pytest.raises(NativeDocumentError):
            validate_json_canvas(source)
    source = canvas()
    source["edges"][0]["schauwerk"] = "association"
    with pytest.raises(NativeDocumentError):
        validate_json_canvas(source)
    source = canvas()
    source["edges"][0]["schauwerk"] = {"kind": "association", "future": "preserved"}
    normalized = validate_json_canvas(source)
    assert normalized["edges"][0]["schauwerk"]["future"] == "preserved"
