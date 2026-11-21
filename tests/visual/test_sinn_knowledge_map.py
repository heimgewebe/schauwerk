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


def test_reported_sinn_long_same_column_route_stays_near_its_cards() -> None:
    """A short adjacent peer must not push a long relation to the far page edge."""
    from schauwerk.visual.native_diagram import _process_svg_stroke_segments

    model = _reported_sinn_19_26_model()
    root = ET.fromstring(render_native_diagram(model))
    edge = _edges(root)["e08"]  # Beitrag -> Beziehungen (e09 starts in the same gap).
    assert edge.get("data-route") == "knowledge-map-readable-gutter"
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

    assert edges["e11"].attrib["data-route"] == "knowledge-map-readable-gutter"
    assert edges["e26"].attrib["data-route"] == "knowledge-map-readable-gutter"
    assert edges["e20"].attrib["data-kind"] == "risk"
    assert edges["e20"].attrib["data-route"] == "knowledge-map-readable-gutter"
    # The high-visibility risk edge no longer needs a giant cross-row diagonal.
    assert node_boxes["zufall"][1] == node_boxes["orientierung"][1]
