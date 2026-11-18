"""Regressions for labeled Sinn knowledge maps in the native SVG renderer."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from schauwerk.visual.native_diagram import render_native_diagram

SVG = "{http://www.w3.org/2000/svg}"


def _sinn_model() -> dict:
    groups = [
        ("grundlagen", "Grundlagen des Sinns"),
        ("sinnbildung", "Entstehung von Sinn"),
        ("sinnerleben", "Dimensionen des Sinnerlebens"),
        ("wirkung", "Wirkung im Leben"),
    ]
    nodes = [
        ("erfahrung", "Erfahrung", "concept", "grundlagen"),
        ("werte", "Werte", "concept", "grundlagen"),
        ("beziehungen", "Beziehungen", "concept", "grundlagen"),
        ("deutung", "Deutung", "action", "sinnbildung"),
        ("kohaerenz", "Zusammenhang", "concept", "sinnbildung"),
        ("sinn", "Sinn", "concept", "sinnerleben"),
        ("bedeutsamkeit", "Bedeutsamkeit", "concept", "sinnerleben"),
        ("zugehoerigkeit", "Zugehörigkeit", "concept", "sinnerleben"),
        ("wirksamkeit", "Wirksamkeit", "concept", "sinnerleben"),
        ("orientierung", "Orientierung", "concept", "wirkung"),
        ("ziele", "Ziele", "concept", "wirkung"),
        ("handeln", "Handeln", "action", "wirkung"),
    ]
    edges = [
        ("erfahrung", "deutung", "wird interpretiert", "flow"),
        ("werte", "deutung", "geben Maßstäbe", "association"),
        ("deutung", "kohaerenz", "schafft Zusammenhang", "flow"),
        ("kohaerenz", "sinn", "fördert Verständnis", "association"),
        ("werte", "bedeutsamkeit", "prägen", "association"),
        ("beziehungen", "zugehoerigkeit", "ermöglichen", "association"),
        ("bedeutsamkeit", "sinn", "trägt zum Sinn bei", "association"),
        ("zugehoerigkeit", "sinn", "stärkt", "association"),
        ("wirksamkeit", "sinn", "stärkt", "association"),
        ("sinn", "orientierung", "gibt Richtung", "flow"),
        ("orientierung", "ziele", "prägt", "flow"),
        ("ziele", "handeln", "leiten", "flow"),
        ("handeln", "wirksamkeit", "ermöglicht", "feedback"),
        ("handeln", "erfahrung", "schafft neue Erfahrungen", "feedback"),
    ]
    return {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "sinn_renderer_regression",
        "title": "Sinn – Entstehung, Erfahrung und Wirkung",
        "purpose": (
            "Veranschaulicht, wie Menschen Sinn durch Erfahrungen, Deutung, "
            "Werte, Beziehungen und Handeln entwickeln und wie Sinn "
            "wiederum Orientierung ermöglicht."
        ),
        "intent": "knowledge_map",
        "groups": [{"id": gid, "label": name} for gid, name in groups],
        "nodes": [
            {"id": nid, "label": label, "kind": kind, "group": group}
            for nid, label, kind, group in nodes
        ],
        "edges": [
            {
                "id": f"e{index:02d}",
                "from": source,
                "to": target,
                "label": label,
                "kind": kind,
            }
            for index, (source, target, label, kind) in enumerate(edges, 1)
        ],
        "requirements": {},
        "requested_formats": [],
    }


def _edges(root: ET.Element) -> dict[str, ET.Element]:
    return {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }


def test_sinn_paths_cannot_paint_over_any_relation_label() -> None:
    source = _sinn_model()
    root = ET.fromstring(render_native_diagram(source))
    assert root.get("data-intent") == "knowledge_map"
    edges = _edges(root)
    assert len(edges) == 14
    clip = root.find(
        ".//" + SVG + "clipPath[@id='native-clip-edge-label-protection']"
    )
    assert clip is not None
    hole_path = clip.find(SVG + "path")
    assert hole_path is not None
    assert hole_path.get("clip-rule") == "evenodd"
    # Every stroke is clipped below all labels, including earlier edge
    # groups: e07 must remain legible after e08/e09 are painted.
    for edge in edges.values():
        stroke = edge.find(SVG + "path")
        label = edge.find(SVG + "rect")
        assert stroke is not None and label is not None
        assert stroke.get("clip-path") == (
            "url(#native-clip-edge-label-protection)"
        )
        assert label.get("rx") == "9"
    assert "trägt zum Sinn bei" in render_native_diagram(source)


def test_sinn_adjacent_feedback_uses_row_gap_instead_of_footer() -> None:
    source = _sinn_model()
    root = ET.fromstring(render_native_diagram(source))
    edges = _edges(root)
    adjacent = edges["e13"]
    distant = edges["e14"]
    assert adjacent.get("data-route") == "feedback-return"
    assert distant.get("data-route") == "feedback-return"
    adjacent_path = adjacent.find(SVG + "path")
    distant_path = distant.find(SVG + "path")
    assert adjacent_path is not None and distant_path is not None
    # Short adjacent return stays between rows. The truly long-distance
    # return still follows a separate footer and preserves its arrow.
    assert adjacent_path.get("d", "").count(" L ") == 3
    assert distant_path.get("d", "").count(" L ") >= 5
    assert render_native_diagram(source) == render_native_diagram(copy.deepcopy(source))


def test_sinn_edge_label_boxes_never_overlap() -> None:
    """Adjacent return text must not mask the Wirksamkeit-to-Sinn label."""
    root = ET.fromstring(render_native_diagram(_sinn_model()))
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for edge_id, edge in _edges(root).items():
        label = edge.find(SVG + "rect")
        assert label is not None
        x, y, width, height = (
            float(label.attrib[attr]) for attr in ("x", "y", "width", "height")
        )
        boxes[edge_id] = (x, y, x + width, y + height)
    for first_id, first in boxes.items():
        for second_id, second in boxes.items():
            if first_id >= second_id:
                continue
            overlaps = (
                first[0] < second[2] and first[2] > second[0]
                and first[1] < second[3] and first[3] > second[1]
            )
            assert not overlaps, (first_id, second_id, first, second)


def test_sinn_relation_labels_do_not_overlap_each_other() -> None:
    root = ET.fromstring(render_native_diagram(_sinn_model()))
    edges = _edges(root)
    boxes = {}
    for edge_id, edge in edges.items():
        rect = edge.find(SVG + "rect")
        assert rect is not None
        x, y, width, height = (
            float(rect.get(name, "0"))
            for name in ("x", "y", "width", "height")
        )
        boxes[edge_id] = (x, y, x + width, y + height)
    overlaps = [
        (one, two)
        for index, (one, a) in enumerate(boxes.items())
        for two, b in list(boxes.items())[index + 1:]
        if a[0] < b[2] and b[0] < a[2]
        and a[1] < b[3] and b[1] < a[3]
    ]
    # A stroke cutout does not protect an earlier label from a later
    # label background (originally e09 "stärkt" vs e13 "ermöglicht").
    assert overlaps == []


def test_sinn_parallel_adjacent_feedback_keeps_distinct_labels() -> None:
    """Crowded local return corridor must fall back to separate footer lanes."""
    for source_id, target_id in (
        ("handeln", "wirksamkeit"), ("wirksamkeit", "handeln")
    ):
        model = _sinn_model()
        model["edges"].append({
            "id": "e15",
            "from": source_id,
            "to": target_id,
            "label": "Eine andere lange Rückkopplung",
            "kind": "feedback",
        })
        root = ET.fromstring(render_native_diagram(model))
        labels = []
        for edge_id in ("e13", "e15"):
            edge = _edges(root)[edge_id]
            rect = edge.find(SVG + "rect")
            path = edge.find(SVG + "path")
            assert rect is not None and path is not None
            x, y, width, height = (
                float(rect.get(attr, "0"))
                for attr in ("x", "y", "width", "height")
            )
            labels.append((x, y, x + width, y + height))
            assert path.get("d", "").count(" L ") >= 5, edge_id
        left, right = labels
        assert not (
            left[0] < right[2] and right[0] < left[2]
            and left[1] < right[3] and right[1] < left[3]
        ), labels
        assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))


def test_sinn_unplaceable_local_feedback_falls_back_to_footer() -> None:
    """If every local label slot hits peers, use a real outer return lane."""
    model = _sinn_model()
    model["edges"].append({
        "id": "e15",
        "from": "erfahrung",
        "to": "kohaerenz",
        "label": "Eine andere lange Rückkopplung",
        "kind": "feedback",
    })
    root = ET.fromstring(render_native_diagram(model))
    boxes = {}
    for edge_id, edge in _edges(root).items():
        rect = edge.find(SVG + "rect")
        assert rect is not None
        x, y, width, height = (
            float(rect.get(key, "0"))
            for key in ("x", "y", "width", "height")
        )
        boxes[edge_id] = (x, y, x + width, y + height)
    for left_id, a in boxes.items():
        for right_id, b in boxes.items():
            if left_id >= right_id:
                continue
            assert not (
                a[0] < b[2] and b[0] < a[2]
                and a[1] < b[3] and b[1] < a[3]
            ), (left_id, right_id, a, b)
    path = _edges(root)["e15"].find(SVG + "path")
    assert path is not None
    assert path.get("d", "").count(" L ") >= 5
    assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))
