"""Regression tests for Canvas edge labels that were hidden by other nodes."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from schauwerk.visual.native_diagram import (
    _canvas_edge_geometry,
    render_native_editing_document,
)
from schauwerk.visual.standalone_editor import NATIVE_IMPORT_SCHEMA, _native_product_input

SVG_NS = "{http://www.w3.org/2000/svg}"


def _canvas(*, blocker: bool, parallel: bool = False, group: bool = False) -> dict:
    nodes = [
        {"id": "start", "type": "text", "x": 0, "y": 0,
         "width": 120, "height": 80, "text": "Anfang"},
        {"id": "end", "type": "text", "x": 400, "y": 0,
         "width": 120, "height": 80, "text": "Ende"},
    ]
    if blocker:
        nodes.append(
            {"id": "obstacle", "type": "text", "x": 230, "y": 0,
             "width": 120, "height": 80, "text": "Anderer Knoten"}
        )
    if group:
        nodes.insert(
            0,
            {"id": "group", "type": "group", "x": -30, "y": -35,
             "width": 580, "height": 170},
        )
    edges = [
        {"id": "e1", "fromNode": "start", "toNode": "end",
         "label": "Erste Verbindung", "toEnd": "arrow"},
    ]
    if parallel:
        edges.append(
            {"id": "e2", "fromNode": "start", "toNode": "end",
             "label": "Zweite Verbindung", "toEnd": "arrow"}
        )
    return {"nodes": nodes, "edges": edges}


def _render(source: dict) -> ET.Element:
    document = _native_product_input(
        {
            "schema_version": NATIVE_IMPORT_SCHEMA,
            "format": "json-canvas-1.0",
            "source": source,
            "title": "Kanten-Beschriftungen.canvas",
        }
    )
    return ET.fromstring(render_native_editing_document(document))


def _groups(root: ET.Element, kind: str) -> dict[str, ET.Element]:
    return {
        str(element.get("data-source-id")): element
        for element in root.iter(SVG_NS + "g")
        if element.get("data-source-kind") == kind
    }


def _box(rect: ET.Element) -> tuple[float, float, float, float]:
    x = float(rect.get("x", "0"))
    y = float(rect.get("y", "0"))
    return x, y, x + float(rect.get("width", "0")), y + float(rect.get("height", "0"))


def _label_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    result = {}
    for identifier, edge in _groups(root, "edge").items():
        label = next(
            rect for rect in edge.findall(SVG_NS + "rect")
            if float(rect.get("width", "0")) > 0
        )
        result[identifier] = _box(label)
    return result


def _intersects(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def test_edge_label_is_not_hidden_by_an_intervening_node() -> None:
    root = _render(_canvas(blocker=True))
    labels = _label_boxes(root)
    obstacles = _groups(root, "node")
    assert set(labels) == {"e1"}
    for node_id, node in obstacles.items():
        if node_id == "group":
            continue
        rect = node.find(SVG_NS + "rect")
        assert rect is not None
        assert not _intersects(labels["e1"], _box(rect)), node_id


def test_parallel_edge_labels_do_not_overlap_each_other_or_nodes() -> None:
    root = _render(_canvas(blocker=True, parallel=True, group=True))
    labels = _label_boxes(root)
    assert set(labels) == {"e1", "e2"}
    assert not _intersects(labels["e1"], labels["e2"])
    for edge_box in labels.values():
        for node_id, node in _groups(root, "node").items():
            if node_id == "group":
                continue
            rect = node.find(SVG_NS + "rect")
            assert rect is not None
            assert not _intersects(edge_box, _box(rect)), node_id


def test_clear_edge_label_keeps_its_original_curve_midpoint() -> None:
    source = _canvas(blocker=False, group=True)
    root = _render(source)
    label_box = _label_boxes(root)["e1"]
    nodes = {node["id"]: node for node in source["nodes"]}
    _path, x, y, _route, _bounds = _canvas_edge_geometry(
        nodes["start"], nodes["end"], {"from_side": None, "to_side": None},
        lane=0,
    )
    assert abs((label_box[0] + label_box[2]) / 2 - x) < 0.11
    assert abs((label_box[1] + label_box[3]) / 2 - y) < 0.11


def test_label_placement_is_deterministic() -> None:
    source = _canvas(blocker=True, parallel=True)
    first = _render(source)
    second = _render(source)
    assert ET.tostring(first) == ET.tostring(second)
