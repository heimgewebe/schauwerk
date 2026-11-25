"""Regressions for labeled Sinn knowledge maps in the native SVG renderer."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

import pytest

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


def test_knowledge_map_layout_removes_simple_crossing() -> None:
    """An avoidable two-column X should align its two relations instead."""
    from schauwerk.visual.native_diagram import _layout

    model = {
        "intent": "knowledge_map",
        "groups": [
            {"id": "sources", "label": "Sources"},
            {"id": "results", "label": "Results"},
        ],
        "nodes": [
            {"id": "a", "label": "A", "kind": "concept", "group": "sources"},
            {"id": "b", "label": "B", "kind": "concept", "group": "sources"},
            {"id": "c", "label": "C", "kind": "concept", "group": "results"},
            {"id": "d", "label": "D", "kind": "concept", "group": "results"},
        ],
        "edges": [
            {"id": "e1", "from": "a", "to": "d", "label": "leads to", "kind": "flow"},
            {"id": "e2", "from": "b", "to": "c", "label": "leads to", "kind": "flow"},
        ],
    }
    positions, regions, _, _ = _layout(model)
    assert [region[0] for region in regions] == ["sources", "results"]
    assert positions["a"][0] == positions["b"][0]
    assert positions["c"][0] == positions["d"][0]
    assert (
        (positions["a"][1] - positions["b"][1])
        * (positions["d"][1] - positions["c"][1])
    ) > 0
    # Automatic ordering is deterministic and must not mutate the source.
    assert _layout(copy.deepcopy(model)) == _layout(model)
    assert [node["id"] for node in model["nodes"]] == ["a", "b", "c", "d"]


def test_knowledge_map_layout_preserves_order_without_relations() -> None:
    from schauwerk.visual.native_diagram import _layout

    model = {
        "intent": "knowledge_map",
        "groups": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
        "nodes": [
            {"id": "n1", "label": "One", "kind": "concept", "group": "a"},
            {"id": "n2", "label": "Two", "kind": "concept", "group": "a"},
            {"id": "n3", "label": "Three", "kind": "concept", "group": "b"},
            {"id": "n4", "label": "Four", "kind": "concept", "group": "b"},
        ],
        "edges": [],
    }
    positions, _, _, _ = _layout(model)
    assert positions["n1"][1] < positions["n2"][1]
    assert positions["n3"][1] < positions["n4"][1]


def test_non_knowledge_map_grouped_layout_is_unchanged() -> None:
    from schauwerk.visual.native_diagram import _layout

    model = {
        "intent": "architecture",
        "groups": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B"},
        ],
        "nodes": [
            {"id": "n1", "label": "One", "kind": "concept", "group": "a"},
            {"id": "n2", "label": "Two", "kind": "concept", "group": "a"},
            {"id": "n3", "label": "Three", "kind": "concept", "group": "b"},
            {"id": "n4", "label": "Four", "kind": "concept", "group": "b"},
        ],
        "edges": [
            {"id": "e1", "from": "n1", "to": "n4", "label": "to", "kind": "flow"},
            {"id": "e2", "from": "n2", "to": "n3", "label": "to", "kind": "flow"},
        ],
    }
    positions, _, _, _ = _layout(model)
    assert positions["n1"][1] < positions["n2"][1]
    assert positions["n3"][1] < positions["n4"][1]


def test_knowledge_map_group_heights_follow_content() -> None:
    """An almost-empty group must not appear as a full-height blank column."""
    from schauwerk.visual.native_diagram import _layout

    model = _sinn_model()
    positions, regions, _, height = _layout(model)
    by_group = {group_id: (top, group_height) for group_id, _, _, top, _, group_height in regions}
    assert by_group["sinnbildung"][1] < by_group["grundlagen"][1]
    assert by_group["grundlagen"][1] < by_group["sinnerleben"][1]
    # Content and the outer viewBox still cover every real node.
    assert all(y + 116 < height for _, y in positions.values())


def test_knowledge_map_keeps_semantic_flow_order() -> None:
    """Fewer crossings must not turn a conceptual process upside down."""
    from schauwerk.visual.native_diagram import _layout

    groups = [
        {"id": "steps", "label": "Steps"},
        {"id": "anchors", "label": "Anchors"},
    ]
    nodes = [
        {"id": name, "label": name, "kind": "action", "group": group}
        for group, names in (
            ("steps", ("p0", "p1", "p2", "p3")),
            ("anchors", ("a0", "a1", "a2", "a3")),
        )
        for name in names
    ]
    edges = [
        {"id": f"f{i}", "from": f"p{i}", "to": f"p{i + 1}",
         "kind": "flow", "label": "then"} for i in range(3)
    ] + [
        {"id": f"g{i}", "from": f"a{i}", "to": f"a{i + 1}",
         "kind": "flow", "label": "then"} for i in range(3)
    ] + [
        {"id": f"x{i}", "from": f"p{i}", "to": f"a{3 - i}",
         "kind": "association", "label": "connects"} for i in range(4)
    ]
    model = {"intent": "knowledge_map", "groups": groups, "nodes": nodes, "edges": edges}
    positions, _, _, _ = _layout(model)
    assert [positions[f"p{i}"][1] for i in range(4)] == sorted(
        positions[f"p{i}"][1] for i in range(4)
    )
    assert [positions[f"a{i}"][1] for i in range(4)] == sorted(
        positions[f"a{i}"][1] for i in range(4)
    )


@pytest.mark.parametrize("row_count", [3, 4])
def test_knowledge_map_long_diagonals_clear_foreign_cards(row_count: int) -> None:
    """Across four columns a long Bezier used to pierce several intermediate cards."""
    from schauwerk.visual.native_diagram import (
        _NODE_HEIGHT,
        _NODE_WIDTH,
        _layout,
        _process_paths_share_physical_stroke,
        _process_svg_path_hits_box,
    )

    groups = [{"id": f"g{k}", "label": f"Gruppe {k}"} for k in range(4)]
    nodes = [
        {"id": f"n{k}_{row}", "label": f"Knoten {k}/{row}",
         "kind": "concept", "group": f"g{k}"}
        for k in range(4) for row in range(row_count)
    ]
    edges = [
        {"id": f"chain_{k}_{row}", "from": f"n{k}_{row}",
         "to": f"n{k}_{row + 1}", "label": "leitet", "kind": "flow"}
        for k in range(4) for row in range(row_count - 1)
    ] + [
        {"id": "long_right", "from": "n0_0", "to": f"n3_{row_count-1}",
         "label": "lange diagonale Verbindung", "kind": "association"},
        {"id": "long_left", "from": "n3_0", "to": f"n0_{row_count-1}",
         "label": "gegengerichtete weite Verbindung", "kind": "association"},
    ]
    model = {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "knowledge_map_diagonal_fixture",
        "title": "Wissensnetzwerk",
        "purpose": "Kartenübergreifende diagonale Beziehungen",
        "intent": "knowledge_map",
        "groups": groups, "nodes": nodes, "edges": edges,
        "requirements": {}, "requested_formats": [],
    }
    positions, _, _, _ = _layout(model)
    root = ET.fromstring(render_native_diagram(model))
    rendered = _edges(root)
    long_paths = []
    label_boxes = []
    for edge_id in ("long_right", "long_left"):
        edge = rendered[edge_id]
        path = edge.find(SVG + "path")
        label = edge.find(SVG + "rect")
        assert path is not None and label is not None
        data = path.get("d", "")
        long_paths.append(data)
        ends = next(
            {relation["from"], relation["to"]}
            for relation in edges if relation["id"] == edge_id
        )
        for node in nodes:
            if node["id"] in ends:
                continue
            x, y = positions[node["id"]]
            assert not _process_svg_path_hits_box(
                data, (float(x), float(y),
                       float(_NODE_WIDTH), float(_NODE_HEIGHT)),
                padding=2,
            ), (edge_id, node["id"], data)
        label_boxes.append(tuple(
            float(label.get(key, "0")) for key in ("x", "y", "width", "height")
        ))
    # Opposite-direction relations must not paint the same physical stroke.
    assert not _process_paths_share_physical_stroke(*long_paths)
    a, b = label_boxes
    assert not (
        a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
        and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
    )
    assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))


def _crowded_sinn_model() -> dict:
    groups = [
        ("dimensionen", "Dimensionen des Sinns"),
        ("quellen", "Quellen des Sinns"),
        ("entstehung", "Wie Sinn entsteht"),
        ("grenzen", "Grenzen und Widersprüche"),
    ]
    nodespec = [
        ("verstehen", "Verstehen", "concept", "dimensionen"),
        ("orientierung", "Orientierung", "concept", "dimensionen"),
        ("bedeutsamkeit", "Bedeutsamkeit", "concept", "dimensionen"),
        ("werte", "Werte", "concept", "quellen"),
        ("beziehungen", "Beziehungen", "concept", "quellen"),
        ("wirksamkeit", "Wirksamkeit", "concept", "quellen"),
        ("erfahrung", "Erfahrung", "concept", "quellen"),
        ("beitrag", "Beitrag", "action", "quellen"),
        ("wahrnehmung", "Wahrnehmung", "concept", "entstehung"),
        ("deutung", "Deutung", "action", "entstehung"),
        ("entscheidung", "Entscheidung", "action", "entstehung"),
        ("handeln", "Handeln", "action", "entstehung"),
        ("reflexion", "Reflexion", "action", "entstehung"),
        ("freiheit", "Freiheit", "concept", "grenzen"),
        ("zufall", "Zufall", "concept", "grenzen"),
        ("sinnkrise", "Sinnkrise", "risk", "grenzen"),
        ("absurditaet", "Absurdität", "concept", "grenzen"),
        ("vorgegeben", "Vorgegebener Sinn?", "decision", "grenzen"),
        ("sinn", "Sinn", "concept", None),
    ]
    edgepairs = [
        ("werte", "orientierung", "geben Maßstäbe", "association"),
        ("werte", "deutung", "bilden Zusammenhänge", "association"),
        ("beziehungen", "bedeutsamkeit", "stiften Verbindungen", "association"),
        ("beziehungen", "sinn", "schaffen Zugehörigkeit", "association"),
        ("verstehen", "sinn", "führt zum Sinn", "association"),
        ("erfahrung", "wahrnehmung", "prägt Wahrnehmung", "association"),
        ("wahrnehmung", "deutung", "liefert Erfahrungen", "flow"),
        ("deutung", "entscheidung", "eröffnet Möglichkeiten", "flow"),
        ("entscheidung", "handeln", "führt zu", "flow"),
        ("handeln", "reflexion", "regt an", "flow"),
        ("reflexion", "wahrnehmung", "prüft und verändert", "feedback"),
        ("handeln", "wirksamkeit", "ermöglicht", "flow"),
        ("wirksamkeit", "bedeutsamkeit", "erzeugt Relevanz", "association"),
        ("erfahrung", "wirksamkeit", "stärkt", "association"),
        ("beitrag", "beziehungen", "stiftet Verbundenheit", "association"),
        ("beitrag", "sinn", "kann auslösen", "association"),
        ("orientierung", "entscheidung", "gibt Richtung", "flow"),
        ("sinn", "orientierung", "gibt Orientierung", "feedback"),
        ("freiheit", "entscheidung", "eröffnet Wahl", "association"),
        ("zufall", "deutung", "öffnet Möglichkeiten", "association"),
        ("deutung", "sinn", "konstruiert Bedeutung", "flow"),
        ("sinnkrise", "sinn", "stellt infrage", "risk"),
        ("absurditaet", "sinnkrise", "verschärft", "risk"),
        ("vorgegeben", "sinn", "fragt nach Ursprung", "association"),
        ("sinn", "freiheit", "relativiert Vorgaben", "association"),
        ("sinn", "bedeutsamkeit", "erzeugt Bedeutung", "feedback"),
        ("reflexion", "sinn", "fragt nach Sinn", "association"),
    ]
    model = {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "sinn_screen_approx_qc",
        "title": "Sinn – Was macht etwas bedeutsam?",
        "purpose": "Verstehen, Erfahrung, Deutung, Handeln und ihre Widersprüche.",
        "intent": "knowledge_map",
        "groups": [{"id": i, "label": v} for i, v in groups],
        "nodes": [
            {"id": i, "label": label, "kind": kind, "group": group}
            for i, label, kind, group in nodespec
        ],
        "edges": [
            {"id": f"e{k:02d}", "from": a, "to": b, "label": label, "kind": kind}
            for k, (a, b, label, kind) in enumerate(edgepairs, 1)
        ],
        "requirements": {},
        "requested_formats": [],
    }

    return model


def test_crowded_sinn_map_has_no_label_overlaps_or_card_piercings() -> None:
    """The screenshot-like 19/27 map must avoid cards and label collisions."""
    from schauwerk.visual.native_diagram import _process_svg_path_hits_box

    model = _crowded_sinn_model()
    root = ET.fromstring(render_native_diagram(model))
    rects = {}
    for group in root.iter():
        if group.attrib.get("data-source-kind") != "node":
            continue
        rect = next((element for element in group if element.tag == SVG + "rect"), None)
        assert rect is not None
        rects[group.attrib["data-source-id"]] = tuple(
            float(rect.get(key, "0")) for key in ("x", "y", "width", "height")
        )

    labels = {}
    by_id = {edge["id"]: edge for edge in model["edges"]}
    for edge_id, edge in _edges(root).items():
        path = next((item for item in edge if item.tag == SVG + "path"), None)
        label = edge.find(SVG + "rect")
        assert path is not None and label is not None
        labels[edge_id] = tuple(
            float(label.get(key, "0")) for key in ("x", "y", "width", "height")
        )
        for node_id, box in rects.items():
            if node_id in {by_id[edge_id]["from"], by_id[edge_id]["to"]}:
                continue
            assert not _process_svg_path_hits_box(path.get("d", ""), box, padding=0), (
                edge_id, node_id,
            )

    assert len(rects) == 19 and len(labels) == 27
    for idx, (left_id, a) in enumerate(labels.items()):
        for right_id, b in list(labels.items())[idx + 1:]:
            assert not (
                a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
            ), (left_id, right_id)
    assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))


def _reported_sinn_19_26_model() -> dict:
    """The exact 19-node/26-edge relations from the user's A3-PDF report."""
    model = _crowded_sinn_model()
    model["id"] = "sinn_und_bedeutung"
    model["purpose"] = (
        "Eine philosophische Wissenskarte über die Entstehung, Erfahrung, "
        "Suche und mögliche Grenzen von Sinn."
    )
    model["groups"] = [
        {"id": "dimensionen", "label": "Dimensionen des Sinns"},
        {"id": "quellen", "label": "Quellen des Sinns"},
        {"id": "sinnbildung", "label": "Wie Sinn entsteht"},
        {"id": "spannungen", "label": "Grenzen und Widersprüche"},
    ]
    for node in model["nodes"]:
        if node["group"] == "entstehung":
            node["group"] = "sinnbildung"
        elif node["group"] == "grenzen":
            node["group"] = "spannungen"
        if node["id"] == "vorgegeben":
            node["id"] = "offene_frage"
        if node["id"] == "sinn":
            node["summary"] = (
                "Das Erleben oder Erkennen von Zusammenhang, "
                "Richtung und Bedeutsamkeit."
            )
    # Preserve the original source order and full node descriptions as well.
    model["nodes"].sort(key=lambda node: 0 if node["id"] == "sinn" else 1)
    summaries = {
        "sinn": "Das Erleben oder Erkennen von Zusammenhang, Richtung und Bedeutsamkeit.",
        "verstehen": "Ereignisse und Erfahrungen in einen nachvollziehbaren Zusammenhang bringen.",
        "orientierung": "Wissen, worauf das eigene Handeln gerichtet ist.",
        "bedeutsamkeit": "Etwas als wichtig und wertvoll erfahren.",
        "werte": "Überzeugungen darüber, was wichtig und erstrebenswert ist.",
        "beziehungen": "Liebe, Verbundenheit, Anerkennung und gemeinsames Leben.",
        "wirksamkeit": "Durch eigenes Handeln etwas verändern oder gestalten.",
        "erfahrung": (
            "Sinn kann im unmittelbaren Erleben von Natur, Kunst, Freude "
            "oder Begegnung liegen."
        ),
        "beitrag": "Etwas für andere oder für eine als wertvoll betrachtete Sache tun.",
        "wahrnehmung": "Die Welt und das eigene Leben bewusst erfahren.",
        "deutung": "Erlebnisse interpretieren und in größere Zusammenhänge einordnen.",
        "entscheidung": "Zwischen Möglichkeiten wählen und Prioritäten setzen.",
        "handeln": "Gewählte Werte und Ziele praktisch verwirklichen.",
        "reflexion": "Erfahrungen, Überzeugungen und Ziele kritisch hinterfragen.",
        "freiheit": (
            "Sinn kann selbst gestaltet werden, ohne vollständig frei "
            "von Bedingungen zu sein."
        ),
        "zufall": "Nicht jedes Ereignis folgt einem erkennbaren Zweck.",
        "sinnkrise": "Bisher tragende Bedeutungen und Ziele verlieren ihre Überzeugungskraft.",
        "absurditaet": (
            "Spannung zwischen menschlicher Sinnsuche und einer Welt "
            "ohne erkennbaren vorgegebenen Gesamtzweck."
        ),
        "offene_frage": (
            "Ist Sinn bereits in der Welt vorhanden, wird er entdeckt "
            "oder erst von Menschen geschaffen?"
        ),
    }
    for node in model["nodes"]:
        node["summary"] = summaries[node["id"]]
    model["nodes"][0].pop("group", None)

    pairs = [
        ("sinn", "verstehen", "Zusammenhang", "association"),
        ("sinn", "orientierung", "Richtung", "association"),
        ("sinn", "bedeutsamkeit", "Wichtigkeit", "association"),
        ("werte", "orientierung", "geben Maßstäbe", "association"),
        ("beziehungen", "bedeutsamkeit", "stiften Verbundenheit", "association"),
        ("wirksamkeit", "bedeutsamkeit", "erzeugt Relevanz", "association"),
        ("erfahrung", "sinn", "macht erfahrbar", "association"),
        ("beitrag", "beziehungen", "stärkt", "association"),
        ("beitrag", "wirksamkeit", "ermöglicht", "flow"),
        ("wahrnehmung", "deutung", "liefert Erfahrungen", "flow"),
        ("deutung", "verstehen", "bildet Zusammenhänge", "flow"),
        ("werte", "entscheidung", "leiten", "association"),
        ("entscheidung", "handeln", "führt zu", "flow"),
        ("handeln", "wirksamkeit", "ermöglicht", "flow"),
        ("handeln", "erfahrung", "schafft", "flow"),
        ("erfahrung", "reflexion", "regt an", "feedback"),
        ("reflexion", "werte", "prüft und verändert", "feedback"),
        ("reflexion", "deutung", "korrigiert", "feedback"),
        ("freiheit", "entscheidung", "eröffnet Möglichkeiten", "association"),
        ("zufall", "orientierung", "durchkreuzt Pläne", "risk"),
        ("sinnkrise", "sinn", "stellt infrage", "risk"),
        ("sinnkrise", "reflexion", "kann auslösen", "feedback"),
        ("absurditaet", "offene_frage", "verschärft", "association"),
        ("offene_frage", "sinn", "fragt nach Ursprung", "association"),
        ("freiheit", "sinn", "ermöglicht Sinngebung", "association"),
        ("deutung", "sinn", "konstruiert Bedeutung", "flow"),
    ]
    model["edges"] = [
        {
            "id": f"e{index:02d}", "from": source, "to": target,
            "label": label, "kind": kind,
        }
        for index, (source, target, label, kind) in enumerate(pairs, 1)
    ]
    model["requirements"] = {
        "formal_relations": True, "free_spatial_layout": False,
        "presentation": True, "collaboration": False, "rich_text": False,
        "structured_comparison": False, "portable_offline": False,
    }
    return model


def test_reported_sinn_model_renders_all_26_relations_deterministically() -> None:
    model = _reported_sinn_19_26_model()
    root = ET.fromstring(render_native_diagram(model))
    assert len(model["nodes"]) == 19
    assert len(_edges(root)) == 26
    assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))


def test_reported_sinn_dominant_ungrouped_hub_is_visually_central() -> None:
    """The semantic hub is no longer put in an unrelated rightmost column."""
    from schauwerk.visual.native_diagram import _layout
    from schauwerk.visual.representation import validate_representation_input

    model = validate_representation_input(_reported_sinn_19_26_model())
    positions, regions, _, _ = _layout(model)
    assert len(regions) == 5
    assert (
        positions["deutung"][0] < positions["zufall"][0]
        < positions["sinn"][0] < positions["orientierung"][0]
        < positions["werte"][0]
    )
    assert regions[2][1] == "Leitbegriff"
    assert render_native_diagram(model) == render_native_diagram(copy.deepcopy(model))


def test_knowledge_map_does_not_move_an_undergrounded_small_hub() -> None:
    """Keep the author's thematic order if no node clearly dominates."""
    from schauwerk.visual.native_diagram import _layout
    from schauwerk.visual.representation import validate_representation_input

    model = _reported_sinn_19_26_model()
    model["edges"] = [
        edge for edge in model["edges"]
        if edge["from"] != "sinn" and edge["to"] != "sinn"
    ]
    positions, regions, _, _ = _layout(validate_representation_input(model))
    assert regions[-1][1] == "Ungruppiert"
    assert positions["sinn"][0] == max(x for x, _ in positions.values())


def test_reported_sinn_without_groups_centers_dominant_node() -> None:
    """A group-free input also need not pin its strongest node top-left."""
    from schauwerk.visual.native_diagram import _layout
    from schauwerk.visual.representation import validate_representation_input

    model = _reported_sinn_19_26_model()
    model["groups"] = []
    for node in model["nodes"]:
        node.pop("group", None)
    normalized = validate_representation_input(model)
    positions, regions, _, _ = _layout(normalized)
    assert regions == []
    assert positions["sinn"][0] in {410, 772}
    assert positions["sinn"][1] > min(y for _, y in positions.values())
    svg = render_native_diagram(normalized)
    root = ET.fromstring(svg)
    assert len(_edges(root)) == 26


def test_reported_sinn_long_same_column_route_stays_near_its_cards() -> None:
    """A short adjacent peer must not push a long relation to the far page edge."""
    from schauwerk.visual.native_diagram import _process_svg_stroke_segments

    model = _reported_sinn_19_26_model()
    root = ET.fromstring(render_native_diagram(model))
    edge = _edges(root)["e08"]  # Beitrag -> Beziehungen (e09 starts in the same gap).
    # A mirrored thematic arrangement can keep the same short, card-safe
    # side lane as an ordinary vertical route. Geometry is the acceptance.
    assert edge.get("data-route") in {
        "knowledge-map-readable-gutter", "vertical",
    }
    path = edge.find(SVG + "path")
    assert path is not None
    segments = _process_svg_stroke_segments(path.get("d", ""))
    assert segments is not None and all(len(segment) == 2 for segment in segments)

    points = [point for segment in segments for point in segment]
    length = sum(
        ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
        for segment in segments
        for left, right in zip(segment, segment[1:])
    )
    # The former global return traversed both sides of the canvas (3379 units)
    # despite both cards belonging to the same column. Preserve a local side lane.
    assert length < 1500
    assert max(x for x, _ in points) - min(x for x, _ in points) < 300


def test_reported_sinn_routes_avoid_foreign_cards_and_labels() -> None:
    """The actual PDF example must have legible routes, not just visible nodes."""
    from schauwerk.visual.native_diagram import _process_svg_path_hits_box

    model = _reported_sinn_19_26_model()
    root = ET.fromstring(render_native_diagram(model))
    edges = _edges(root)
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
    }

    def box(element: ET.Element) -> tuple[float, float, float, float]:
        rectangle = next(child for child in element if child.tag == SVG + "rect")
        return tuple(
            float(rectangle.get(attribute, "0"))
            for attribute in ("x", "y", "width", "height")
        )

    node_boxes = {node_id: box(element) for node_id, element in nodes.items()}
    label_boxes = {edge_id: box(element) for edge_id, element in edges.items()}

    def overlap(
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> bool:
        return (
            left[0] < right[0] + right[2]
            and right[0] < left[0] + left[2]
            and left[1] < right[1] + right[3]
            and right[1] < left[1] + left[3]
        )

    relations = {str(edge["id"]): edge for edge in model["edges"]}
    for edge_id, group in edges.items():
        stroke = group.find(SVG + "path")
        assert stroke is not None
        for node_id, boundary in node_boxes.items():
            if node_id in {relations[edge_id]["from"], relations[edge_id]["to"]}:
                continue
            assert not _process_svg_path_hits_box(
                stroke.get("d", ""), boundary, padding=0
            ), (edge_id, node_id)

    for index, (edge_id, boundary) in enumerate(label_boxes.items()):
        for other_id, other_boundary in list(label_boxes.items())[index + 1:]:
            assert not overlap(boundary, other_boundary), (edge_id, other_id)

    # Edge-label cutouts must never erase node cards or peer arrowheads.
    from schauwerk.visual.native_diagram import _process_svg_stroke_segments

    for edge_id, label in label_boxes.items():
        assert all(
            not overlap(label, node_box)
            for node_box in node_boxes.values()
        ), f"{edge_id} label covers a node card"
        for peer_id, peer_group in edges.items():
            if peer_id == edge_id:
                continue
            peer_path = peer_group.find(SVG + "path")
            assert peer_path is not None
            segments = _process_svg_stroke_segments(peer_path.get("d", ""))
            assert segments
            for point in (segments[0][0], segments[-1][-1]):
                assert not (
                    label[0] <= point[0] <= label[0] + label[2]
                    and label[1] <= point[1] <= label[1] + label[3]
                ), (edge_id, peer_id, "arrowhead obscured by label")

    # The central-hub layout may choose either certified orthogonal route or
    # a card-safe curve. The geometry assertions above remain authoritative.
    assert edges["e11"].attrib["data-route"] in {
        "knowledge-map-readable-gutter", "knowledge-map-row-card-detour",
    }
    assert edges["e26"].attrib["data-route"] in {
        "knowledge-map-readable-gutter", "knowledge-map-card-safe",
        "knowledge-map-row-card-detour",
    }
    assert edges["e20"].attrib["data-kind"] == "risk"
    # With shorter same-group spans a normal curve is also safe; the full
    # SVG card/label and arrowhead geometry above is the acceptance criterion.
    assert edges["e20"].attrib["data-route"] in {
        "knowledge-map-readable-gutter", "standard",
    }
    # The high-visibility risk edge no longer needs a giant cross-row diagonal.
    assert node_boxes["zufall"][1] == node_boxes["orientierung"][1]


def _reported_sinn_16_24_model() -> dict:
    """Exactly the 16-node, 24-relation Sinn model reported on 2026-11-22."""
    groups=[{'id':x,'label':y} for x,y in [
     ('dimensionen','Dimensionen des Sinns'),('quellen','Quellen des Sinns'),
     ('sinnbildung','Wie Sinn entsteht'),('spannungen','Grenzen und Widersprüche')]]
    nodes_data = [
        ('sinn', 'Sinn', 'concept', None,
            'Die erfahrene oder angenommene Bedeutsamkeit von Leben, Handlungen und '
            'Ereignissen.'
        ),
        ('bedeutsamkeit', 'Bedeutsamkeit', 'concept', 'dimensionen',
            'Etwas zählt, besitzt Wert oder ist nicht gleichgültig.'
        ),
        ('kohaerenz', 'Zusammenhang', 'concept', 'dimensionen',
            'Erfahrungen und Ereignisse erscheinen als verständliches Ganzes.'
        ),
        ('orientierung', 'Orientierung', 'concept', 'dimensionen',
            'Sinn bietet Richtung für Entscheidungen und Lebensführung.'
        ),
        ('beziehungen', 'Beziehungen', 'concept', 'quellen',
            'Liebe, Zugehörigkeit und Anerkennung können Sinn erfahrbar machen.'
        ),
        ('werte', 'Werte', 'concept', 'quellen',
            'Überzeugungen darüber, was wichtig und erstrebenswert ist.'
        ),
        ('handeln', 'Handeln', 'action', 'quellen',
            'Sinn kann durch Gestaltung, Arbeit, Fürsorge und gesellschaftliche '
            'Praxis entstehen.'
        ),
        ('erfahrung', 'Erfahrung', 'concept', 'sinnbildung',
            'Das unmittelbare Erleben bildet einen Ausgangspunkt der Sinnbildung.'
        ),
        ('deutung', 'Deutung', 'action', 'sinnbildung',
            'Menschen interpretieren Erlebnisse und ordnen sie in Zusammenhänge ein.'
        ),
        ('entscheidung', 'Entscheidung', 'action', 'sinnbildung',
            'Durch Entscheidungen werden Möglichkeiten ausgewählt und Prioritäten '
            'gesetzt.'
        ),
        ('verantwortung', 'Verantwortung', 'concept', 'sinnbildung',
            'Die Übernahme von Verantwortung kann Handlungen über das eigene '
            'Interesse hinaus bedeutsam machen.'
        ),
        ('vorgefundener_sinn', 'Sinn entdecken', 'concept', 'spannungen',
            'Die Auffassung, dass Sinn unabhängig vom Individuum besteht und entdeckt '
            'werden kann.'
        ),
        ('geschaffener_sinn', 'Sinn schaffen', 'concept', 'spannungen',
            'Die Auffassung, dass Menschen Sinn durch Deutung, Wahl und Handeln '
            'hervorbringen.'
        ),
        ('leid', 'Leid', 'risk', 'spannungen',
            'Verlust, Schmerz und Ungerechtigkeit können bisherige Sinnzusammenhänge '
            'erschüttern.'
        ),
        ('absurditaet', 'Absurdität', 'concept', 'spannungen',
            'Der mögliche Widerspruch zwischen menschlichem Sinnverlangen und einer '
            'Welt ohne erkennbare letzte Antwort.'
        ),
        ('sinnlosigkeit', 'Sinnlosigkeit', 'concept', 'spannungen',
            'Das Erleben fehlender Bedeutung, Richtung oder Verständlichkeit; nicht '
            'zwingend der Beweis objektiver Sinnlosigkeit.'
        ),
    ]
    nodes = [
        {
            "id": nid, "label": label, "kind": kind,
            "summary": summary,
            **({"group": group} if group else {}),
        }
        for nid, label, kind, group, summary in nodes_data
    ]
    pairs=[
    ('bedeutsamkeit','sinn','Wert','association'),
    ('kohaerenz','sinn','Verständlichkeit','association'),
    ('orientierung','sinn','Richtung','association'),
    ('beziehungen','bedeutsamkeit','stiften','flow'),
    ('werte','orientierung','geben','flow'),
    ('handeln','bedeutsamkeit','verwirklicht','flow'),
    ('erfahrung','deutung','wird interpretiert','flow'),
    ('deutung','kohaerenz','stellt her','flow'),
    ('werte','entscheidung','leiten','flow'),
    ('entscheidung','handeln','führt zu','flow'),
    ('handeln','erfahrung','erzeugt','feedback'),
    ('verantwortung','handeln','prägt','flow'),
    ('beziehungen','verantwortung','begründen','association'),
    ('deutung','geschaffener_sinn','ermöglicht','flow'),
    ('vorgefundener_sinn','geschaffener_sinn','entdecken oder schaffen?','association'),
    ('vorgefundener_sinn','sinn','als gegeben','association'),
    ('geschaffener_sinn','sinn','als hervorgebracht','association'),
    ('leid','kohaerenz','erschüttert','risk'),
    ('leid','deutung','fordert heraus','feedback'),
    ('absurditaet','vorgefundener_sinn','stellt infrage','risk'),
    ('absurditaet','sinnlosigkeit','kann auslösen','risk'),
    ('sinnlosigkeit','orientierung','schwächt','risk'),
    ('sinnlosigkeit','deutung','kann erneute Suche anstoßen','feedback'),
    ('verantwortung','sinn','kann begründen','association')]
    return {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "sinn_und_bedeutung",
        "title": "Sinn – Was macht etwas bedeutsam?",
        "purpose": (
            "Philosophische Wissenskarte über die Dimensionen, Quellen und "
            "Entstehung von Sinn sowie grundlegende Widersprüche zwischen "
            "Sinnfindung, Sinnstiftung und Sinnlosigkeit."
        ),
        "intent": "knowledge_map",
        "groups": groups,
        "nodes": nodes,
        "edges": [
            {
                "id": f"e{i:02d}",
                "from": a,
                "to": b,
                "label": label,
                "kind": kind,
            }
            for i, (a, b, label, kind) in enumerate(pairs, 1)
        ],
        "requirements": {},
        "requested_formats": [],
    }



def test_reported_sinn_16_24_hub_has_unique_degree_and_theme_breadth() -> None:
    """The user's newer Sinn model has degree 6 versus Deutung 5.

    That is a unique thematic hub, even though the previous 1.5x dominance
    threshold missed it. The weaker fallback must not reorder theme columns.
    """
    from schauwerk.visual.native_diagram import (
        _knowledge_map_leading_node,
        _layout,
    )
    from schauwerk.visual.representation import validate_representation_input

    source = _reported_sinn_16_24_model()
    assert len(source["nodes"]) == 16
    assert len(source["edges"]) == 24
    assert _knowledge_map_leading_node(source["nodes"], source["edges"]) is None
    assert (
        _knowledge_map_leading_node(
            source["nodes"], source["edges"], allow_unique_max=True
        )
        == "sinn"
    )
    positions, regions, width, _ = _layout(validate_representation_input(source))
    assert [region[0] for region in regions] == [
        "dimensionen", "quellen", None, "sinnbildung", "spannungen",
    ]
    assert regions[2][1] == "Leitbegriff"
    assert abs(positions["sinn"][0] + 125 - width / 2) < 150


def test_unconnected_sources_do_not_move_existing_sinn_nodes_at_compact_boundary() -> None:
    """Appending a disconnected card must not change the connected graph's layout."""
    from schauwerk.visual.native_diagram import _layout
    from schauwerk.visual.representation import validate_representation_input

    model = _reported_sinn_16_24_model()
    original_ids = {node["id"] for node in model["nodes"]}
    positions, regions, _, _ = _layout(validate_representation_input(model))
    baseline = {node_id: positions[node_id] for node_id in original_ids}
    for index in range(3):
        model["nodes"].append({
            "id": f"quelle_extra_{index}", "label": f"Weitere Quelle {index}",
            "kind": "concept", "group": "quellen",
        })
        positions, current_regions, _, _ = _layout(validate_representation_input(model))
        assert {node_id: positions[node_id] for node_id in original_ids} == baseline
        assert [r[:2] for r in current_regions] == [r[:2] for r in regions]
    assert len(model["nodes"]) == 19
    root = ET.fromstring(render_native_diagram(model))
    assert not any(e.get("data-renderer-region") == "ungrouped" for e in root.iter())


def test_audit_minimal_knowledge_map_raw_svg_has_no_overlapping_labels() -> None:
    """Original 23 November audit reproduction: e12 and e21 overlapped by 1976."""
    from schauwerk.visual.native_diagram import (
        _process_label_path_distance_sq,
        _process_svg_path_hits_box,
    )

    model = {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "audit_routing", "title": "Audit Kanten",
        "purpose": "Prüfung zulässiger Kantenkonstellationen", "intent": "knowledge_map",
        "groups": [{"id": f"g{i}", "label": f"Thema {i}"} for i in range(4)],
        "nodes": [
            {"id": f"n{i}", "label": f"Begriff {i}", "kind": "concept", "group": f"g{i%4}"}
            for i in (0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 14, 15)
        ],
        "edges": [
            {"id": f"e{i}", "from": f"n{a}", "to": f"n{b}",
             "label": f"Bezug {i}", "kind": kind}
            for i, a, b, kind in [
                (1, 14, 7, "risk"), (2, 0, 15, "feedback"),
                (3, 1, 9, "association"), (4, 1, 7, "association"),
                (6, 14, 3, "risk"), (12, 5, 3, "flow"),
                (14, 10, 5, "association"), (15, 3, 10, "flow"),
                (17, 0, 10, "flow"), (18, 9, 14, "flow"),
                (19, 11, 9, "feedback"), (20, 2, 11, "flow"),
                (21, 7, 5, "risk"), (23, 6, 11, "feedback"),
            ]
        ],
        "requirements": {}, "requested_formats": [],
    }
    svg = render_native_diagram(model)
    root = ET.fromstring(svg)
    edges = _edges(root)

    def box(element):
        rect = element.find(SVG + "rect")
        return tuple(float(rect.get(key)) for key in ("x", "y", "width", "height"))

    labels = {key: box(value) for key, value in edges.items()}
    paths = {key: value.find(SVG + "path").get("d") for key, value in edges.items()}
    cards = [box(e) for e in root.iter() if e.get("data-source-kind") == "node"]
    def overlap(a, b):
        return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])

    assert len(labels) == 14
    for edge_id, bounds in labels.items():
        assert not any(overlap(bounds, other) for key, other in labels.items() if key != edge_id)
        assert not any(overlap(bounds, card) for card in cards)
    for edge_id in ("e12", "e21"):
        assert _process_label_path_distance_sq(paths[edge_id], labels[edge_id]) <= 320**2
    # Only the actually relocated label needs the full collision assertion;
    # the pre-existing peer label must not be displaced by a second pass.
    assert any(
        all(not _process_svg_path_hits_box(path, labels[edge_id])
            for key, path in paths.items() if key != edge_id)
        for edge_id in ("e12", "e21")
    )
    assert svg == render_native_diagram(copy.deepcopy(model))


def test_reported_sinn_16_24_central_render_has_no_foreign_card_or_label_hits() -> None:
    """A central hub is useful only if all paths and captions remain readable."""
    from math import dist

    from schauwerk.visual.native_diagram import (
        _process_svg_path_hits_box,
        _process_svg_stroke_segments,
    )

    source = _reported_sinn_16_24_model()
    content = render_native_diagram(source)
    root = ET.fromstring(content)
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.get("data-source-kind") == "node"
    }
    edges = _edges(root)
    assert len(nodes) == 16 and len(edges) == 24

    def rectangle(element: ET.Element) -> tuple[float, float, float, float]:
        box = element.find(SVG + "rect")
        assert box is not None
        return tuple(
            float(box.get(key, "0"))
            for key in ("x", "y", "width", "height")
        )

    def overlaps(
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> bool:
        return (
            left[0] < right[0] + right[2]
            and right[0] < left[0] + left[2]
            and left[1] < right[1] + right[3]
            and right[1] < left[1] + left[3]
        )

    cards = {key: rectangle(element) for key, element in nodes.items()}
    labels = {key: rectangle(element) for key, element in edges.items()}
    hub = cards["sinn"]
    assert abs(hub[0] + hub[2] / 2 - float(root.get("width", "0")) / 2) < 150
    relations = {edge["id"]: edge for edge in source["edges"]}

    for edge_id, element in edges.items():
        path = element.find(SVG + "path")
        assert path is not None
        for node_id, bounds in cards.items():
            if node_id in {relations[edge_id]["from"], relations[edge_id]["to"]}:
                continue
            assert not _process_svg_path_hits_box(
                path.get("d", ""), bounds, padding=0
            ), (edge_id, node_id)
        for bounds in cards.values():
            assert not overlaps(labels[edge_id], bounds), edge_id
        for other_id, other_bounds in labels.items():
            if edge_id != other_id:
                assert not overlaps(labels[edge_id], other_bounds), (
                    edge_id, other_id,
                )

    path = edges["e08"].find(SVG + "path")
    assert path is not None
    segments = _process_svg_stroke_segments(path.get("d", ""))
    assert segments
    assert sum(
        dist(start, end)
        for segment in segments for start, end in zip(segment, segment[1:])
    ) < 1550
    assert content == render_native_diagram(copy.deepcopy(source))


def test_reported_sinn_16_24_clears_recoverable_ambiguous_labels() -> None:
    """Label rescue must distinguish its own line from the nearby foreign stroke."""
    from math import sqrt

    from schauwerk.visual.native_diagram import (
        _process_label_path_distance_sq,
        _process_svg_path_hits_box,
    )

    root = ET.fromstring(render_native_diagram(_reported_sinn_16_24_model()))
    edges = _edges(root)
    paths = {key: value.find(SVG + "path").get("d", "") for key, value in edges.items()}
    for edge_id in ("e06", "e10", "e15", "e21"):
        rect = edges[edge_id].find(SVG + "rect")
        assert rect is not None
        box = tuple(float(rect.get(key, "0")) for key in ("x", "y", "width", "height"))
        own = sqrt(_process_label_path_distance_sq(paths[edge_id], box))
        assert own <= 100
        for other_id, path in paths.items():
            if other_id != edge_id:
                assert not _process_svg_path_hits_box(path, box)
                assert sqrt(_process_label_path_distance_sq(path, box)) > own + 8


def test_reported_sinn_16_24_equal_degree_is_not_forced_into_the_center() -> None:
    """A tie is ambiguous and must not receive an invented central concept."""
    from schauwerk.visual.native_diagram import _knowledge_map_leading_node

    model = _reported_sinn_16_24_model()
    model["edges"].append({
        "id": "e25",
        "from": "deutung",
        "to": "verantwortung",
        "label": "verbindet",
        "kind": "association",
    })
    assert (
        _knowledge_map_leading_node(
            model["nodes"], model["edges"], allow_unique_max=True
        )
        is None
    )


def test_reported_sinn_16_24_long_card_label_follows_own_path() -> None:
    """A certified long card-safe detour must not leave its caption detached."""
    from schauwerk.visual.native_diagram import _process_label_path_distance_sq

    root = ET.fromstring(render_native_diagram(_reported_sinn_16_24_model()))
    edge = _edges(root)["e12"]  # Verantwortung -> Handeln ("prägt")
    assert edge.get("data-route") in {
        "knowledge-map-long-card-safe", "knowledge-map-card-safe",
    }
    path = edge.find(SVG + "path")
    label = edge.find(SVG + "rect")
    assert path is not None and label is not None
    box = tuple(float(label.get(key, "0")) for key in ("x", "y", "width", "height"))
    distance_squared = _process_label_path_distance_sq(path.get("d", ""), box)
    assert distance_squared is not None
    assert distance_squared <= (box[2] / 2 + 12) ** 2, (
        distance_squared**0.5, box,
    )


def test_reported_sinn_16_24_layout_reduces_crossings_without_inventing_group() -> None:
    """The grouped map must prioritize legibility over a rigid top-row hub."""
    from math import dist

    from schauwerk.visual.native_diagram import _layout
    from schauwerk.visual.representation import validate_representation_input

    source = _reported_sinn_16_24_model()
    positions, regions, _width, _height = _layout(
        validate_representation_input(source)
    )
    centers = {
        node_id: (x + 125.0, y + 83.0)
        for node_id, (x, y) in positions.items()
    }

    def crosses(first: dict, second: dict) -> bool:
        a, b = first["from"], first["to"]
        c, d = second["from"], second["to"]
        if len({a, b, c, d}) != 4:
            return False
        x1, y1 = centers[a]
        x2, y2 = centers[b]
        x3, y3 = centers[c]
        x4, y4 = centers[d]
        vx, vy = x2 - x1, y2 - y1
        wx, wy = x4 - x3, y4 - y3
        denominator = vx * wy - vy * wx
        if not denominator:
            return False
        t = ((x3 - x1) * wy - (y3 - y1) * wx) / denominator
        u = ((x3 - x1) * vy - (y3 - y1) * vx) / denominator
        return 0.005 < t < 0.995 and 0.005 < u < 0.995

    edges = source["edges"]
    crossings = sum(
        crosses(first, second)
        for index, first in enumerate(edges)
        for second in edges[index + 1 :]
    )
    weighted_distance = sum(
        dist(centers[edge["from"]], centers[edge["to"]])
        * {"flow": 2.0, "feedback": 0.55, "association": 1.25,
           "risk": 1.25}.get(edge["kind"], 1.0)
        for edge in edges
    )
    assert crossings <= 10, crossings
    assert weighted_distance < 24000, weighted_distance
    assert positions["sinn"][1] >= positions["kohaerenz"][1]
    assert abs(
        positions["vorgefundener_sinn"][1]
        - positions["geschaffener_sinn"][1]
    ) <= 218
    assert [region[0] for region in regions] == [
        "dimensionen", "quellen", None, "sinnbildung", "spannungen",
    ]
    # The placeholder column may position an ungrouped concept, not create
    # another semantic group or display an invented thematic header.
    svg = render_native_diagram(source)
    assert "<title>Leitbegriff</title>" not in svg
    assert 'data-renderer-region="ungrouped"' not in svg

    # The layout proxy alone is insufficient: verify that actual physical
    # SVG routes, including feedback return gutters, become shorter overall.
    from schauwerk.visual.native_diagram import _process_svg_stroke_segments

    travel = 0.0
    for group in _edges(ET.fromstring(svg)).values():
        path = group.find(SVG + "path")
        assert path is not None
        for segment in _process_svg_stroke_segments(path.get("d", "")):
            travel += sum(
                dist(start, end)
                for start, end in zip(segment, segment[1:])
            )
    assert travel < 22000, travel

    # The final orthogonal/curved paths may cross differently from the
    # straight-line layout proxy. Measure actual unrelated stroke segments.
    routed = _edges(ET.fromstring(svg))
    strokes = {}
    for edge_id, group in routed.items():
        path = group.find(SVG + "path")
        assert path is not None
        strokes[edge_id] = [
            (start, end)
            for segment in _process_svg_stroke_segments(path.get("d", ""))
            for start, end in zip(segment, segment[1:])
        ]

    def intersect(a, b, c, d) -> bool:
        vx, vy = b[0] - a[0], b[1] - a[1]
        wx, wy = d[0] - c[0], d[1] - c[1]
        den = vx * wy - vy * wx
        if abs(den) < 1e-7:
            return False
        t = ((c[0] - a[0]) * wy - (c[1] - a[1]) * wx) / den
        u = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / den
        return 0.0005 < t < 0.9995 and 0.0005 < u < 0.9995

    routed_crossings = sum(
        any(
            intersect(start, end, peer_start, peer_end)
            for start, end in strokes[first["id"]]
            for peer_start, peer_end in strokes[second["id"]]
        )
        for index, first in enumerate(edges)
        for second in edges[index + 1 :]
        if len({first["from"], first["to"], second["from"], second["to"]}) == 4
    )
    assert routed_crossings <= 25, routed_crossings


def test_reported_sinn_long_forward_feedback_uses_clear_local_corridor() -> None:
    """A long same-row return should not traverse the entire card field."""
    from math import dist

    from schauwerk.visual.native_diagram import (
        _process_svg_path_hits_box,
        _process_svg_stroke_segments,
    )

    root = ET.fromstring(render_native_diagram(_reported_sinn_16_24_model()))
    edges = _edges(root)
    path = edges["e11"].find(SVG + "path")
    assert path is not None
    d = path.get("d", "")
    segments = _process_svg_stroke_segments(d)
    length = sum(dist(a, b) for seg in segments for a, b in zip(seg, seg[1:]))
    assert length < 1000
    for edge_id, edge in edges.items():
        if edge_id == "e11":
            continue
        rect = edge.find(SVG + "rect")
        assert rect is not None
        box = tuple(float(rect.get(key, "0")) for key in ("x", "y", "width", "height"))
        assert not _process_svg_path_hits_box(d, box)
