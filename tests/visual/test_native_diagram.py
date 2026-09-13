from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.visual.grammar import GRAMMAR_SCHEMA_VERSION
from schauwerk.visual.native_diagram import (
    _NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE,
    _ellipsize_to_width,
    _estimated_wrap_width,
    _rebalance_single_word_lines,
    _split_token_to_width,
    _xml_escape,
    render_native_diagram,
)
from schauwerk.visual.representation import RepresentationError, validate_representation_input

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = ROOT / "docs/operators/fixtures/golden"
GOLDEN_FILES = (
    "system-landscape-v1.json",
    "decision-flow-v1.json",
    "narrative-journey-v1.json",
)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def _load(name: str) -> dict:
    return json.loads((GOLDEN_ROOT / name).read_text(encoding="utf-8"))


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _source_ids(root: ET.Element, source_kind: str) -> list[str]:
    return [
        element.attrib["data-source-id"]
        for element in root.iter()
        if element.attrib.get("data-source-kind") == source_kind
    ]


def _rect_box(rect: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))


def _boxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _node_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for node in root.iter():
        if node.attrib.get("data-source-kind") != "node":
            continue
        rect = node.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        boxes[node.attrib["data-source-id"]] = _rect_box(rect)
    return boxes


def _edge_label_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for edge in root.iter():
        if edge.attrib.get("data-source-kind") != "edge":
            continue
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        boxes[edge.attrib["data-source-id"]] = _rect_box(rect)
    return boxes


def _point_on_box_boundary(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
    *,
    tolerance: float = 0.1,
) -> bool:
    px, py = point
    x, y, width, height = box
    on_vertical = (
        abs(px - x) <= tolerance or abs(px - (x + width)) <= tolerance
    ) and y - tolerance <= py <= y + height + tolerance
    on_horizontal = (
        abs(py - y) <= tolerance or abs(py - (y + height)) <= tolerance
    ) and x - tolerance <= px <= x + width + tolerance
    return on_vertical or on_horizontal


def test_native_diagram_is_byte_deterministic_for_raw_and_normalized_input() -> None:
    raw = _load("system-landscape-v1.json")
    normalized = validate_representation_input(raw)

    first = render_native_diagram(raw)
    second = render_native_diagram(copy.deepcopy(raw))
    from_normalized = render_native_diagram(normalized)

    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.encode("utf-8") == from_normalized.encode("utf-8")


@pytest.mark.parametrize("fixture_name", GOLDEN_FILES)
def test_golden_diagram_is_parseable_and_materializes_every_source_id(
    fixture_name: str,
) -> None:
    raw = _load(fixture_name)
    svg = render_native_diagram(raw)
    root = _parse(svg)

    assert root.tag == f"{{{SVG_NAMESPACE}}}svg"
    assert root.attrib["data-visual-grammar"] == GRAMMAR_SCHEMA_VERSION
    assert root.attrib["data-intent"] == raw["intent"]
    assert sorted(_source_ids(root, "node")) == sorted(node["id"] for node in raw["nodes"])
    assert sorted(_source_ids(root, "edge")) == sorted(edge["id"] for edge in raw["edges"])
    assert sorted(_source_ids(root, "group")) == sorted(group["id"] for group in raw["groups"])


def test_all_supported_node_and_edge_kinds_have_explicit_visual_materialization() -> None:
    raw = _load("system-landscape-v1.json")
    raw["nodes"] = [
        {"id": kind, "label": kind.title(), "kind": kind, "group": None}
        for kind in (
            "human",
            "system",
            "service",
            "store",
            "decision",
            "risk",
            "action",
            "evidence",
            "concept",
        )
    ]
    raw["groups"] = []
    raw["edges"] = [
        {
            "id": f"edge_{kind}",
            "from": raw["nodes"][index]["id"],
            "to": raw["nodes"][index + 1]["id"],
            "label": kind,
            "kind": kind,
        }
        for index, kind in enumerate(
            ("authority", "flow", "evidence", "feedback", "risk", "association")
        )
    ]
    root = _parse(render_native_diagram(raw))

    node_kinds = {
        element.attrib["data-kind"]
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
    }
    edge_kinds = {
        element.attrib["data-kind"]
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    assert node_kinds == {node["kind"] for node in raw["nodes"]}
    assert edge_kinds == {edge["kind"] for edge in raw["edges"]}


def test_edges_use_curved_paths_and_quiet_local_arrow_markers() -> None:
    raw = _load("decision-flow-v1.json")
    root = _parse(render_native_diagram(raw))
    edge_groups = [
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    ]
    markers = root.findall(f".//{{{SVG_NAMESPACE}}}marker")

    assert {marker.attrib["id"] for marker in markers} == {
        "native-arrow-authority",
        "native-arrow-evidence",
        "native-arrow-feedback",
        "native-arrow-flow",
        "native-arrow-risk",
    }
    for group in edge_groups:
        path = group.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        commands = set(re.findall(r"[A-Z]", path.attrib["d"]))
        assert path.attrib["d"].startswith("M ")
        assert "C" in commands
        assert commands <= {"M", "C", "L"}
        assert path.attrib["marker-end"] == f"url(#native-arrow-{group.attrib['data-kind']})"


@pytest.mark.parametrize("fixture_name", GOLDEN_FILES)
def test_svg_has_no_external_or_active_resources(fixture_name: str) -> None:
    root = _parse(render_native_diagram(_load(fixture_name)))
    forbidden_tags = {"a", "audio", "embed", "foreignObject", "iframe", "image", "script", "video"}

    for element in root.iter():
        assert element.tag.rsplit("}", 1)[-1] not in forbidden_tags
        for name, value in element.attrib.items():
            local_name = name.rsplit("}", 1)[-1].lower()
            assert local_name not in {"href", "src"}
            assert not local_name.startswith("on")
            assert not re.search(r"(?:data|file|https?|javascript):", value, re.IGNORECASE)
            if "url(" in value:
                assert re.fullmatch(
                    r"url\(#native-(?:arrow-[a-z_]+|clip-[A-Za-z0-9_.:-]+)\)",
                    value,
                )


def test_hostile_looking_labels_are_escaped_as_inert_text() -> None:
    raw = _load("decision-flow-v1.json")
    hostile = '</text><script onload="alert(1)">& external https://evil.invalid'
    raw["title"] = hostile
    raw["purpose"] = "<foreignObject><iframe src='data:text/html,bad'></iframe></foreignObject>"
    raw["groups"][0]["label"] = "<image href='https://evil.invalid/a.svg'>"
    raw["nodes"][0]["label"] = hostile
    raw["nodes"][0]["summary"] = "<a href='javascript:alert(1)'>bad</a>"
    raw["edges"][0]["label"] = "<script>bad()</script>"

    svg = render_native_diagram(raw)
    root = _parse(svg)
    text = "".join(root.itertext())

    assert hostile in text
    assert "<script" not in svg.lower()
    assert "<foreignobject" not in svg.lower()
    assert "<iframe" not in svg.lower()
    assert "<image" not in svg.lower()
    assert "<a " not in svg.lower()
    assert "&lt;script" in svg.lower()


def test_xml_forbidden_codepoints_are_replaced_and_supplementary_unicode_survives() -> None:
    raw = _load("decision-flow-v1.json")
    raw["title"] = "Title\x00🛰"
    raw["purpose"] = "Purpose\x01𐐷"
    raw["groups"][0]["label"] = "Group\x02🦉"
    raw["nodes"][0]["label"] = "Node\x03🚀"
    raw["nodes"][0]["summary"] = "Summary\x04🧭"
    raw["edges"][0]["label"] = "Edge\x05🛡"

    svg = render_native_diagram(raw)
    root = _parse(svg)
    text = "".join(root.itertext())

    assert not any(character in svg for character in "\x00\x01\x02\x03\x04\x05")
    for expected in (
        "Title�🛰",
        "Purpose�𐐷",
        "Group�🦉",
        "Node�🚀",
        "Summary�🧭",
        "Edge�🛡",
    ):
        assert expected in text


def test_unpaired_unicode_surrogate_fails_closed_before_rendering() -> None:
    raw = _load("decision-flow-v1.json")
    raw["nodes"][0]["summary"] = "Unpaired high surrogate: \ud800"

    with pytest.raises(
        RepresentationError,
        match=r"^representation input contains Unicode surrogate code points$",
    ):
        render_native_diagram(raw)


def test_xml_escape_preserves_allowed_whitespace_and_valid_unicode() -> None:
    allowed = "\t\n\rValid BMP ä and supplementary 🛰 𐐷"

    assert _xml_escape(allowed) == allowed


def test_process_layout_uses_graph_rank_and_readable_typography() -> None:
    root = _parse(render_native_diagram(_load("decision-flow-v1.json")))
    view_box = [float(value) for value in root.attrib["viewBox"].split()]
    assert view_box[2] <= 2000
    assert view_box[3] <= 700

    node_groups = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
    }

    def node_xy(node_id: str) -> tuple[float, float]:
        rect = node_groups[node_id].find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        return float(rect.attrib["x"]), float(rect.attrib["y"])

    request_x, request_y = node_xy("request")
    live_x, live_y = node_xy("live_state")
    scope_x, scope_y = node_xy("scope_check")
    evidence_x, evidence_y = node_xy("evidence_gate")
    risk_x, risk_y = node_xy("risk_gate")
    stop_x, stop_y = node_xy("stop")
    execute_x, execute_y = node_xy("execute")
    readback_x, readback_y = node_xy("readback")

    assert request_x == live_x
    assert live_y > request_y
    assert request_x < scope_x < evidence_x < risk_x < execute_x < readback_x
    assert scope_y == evidence_y == risk_y == execute_y == readback_y
    assert stop_x == execute_x
    assert stop_y > execute_y

    edge_groups = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    for branch_id in ("flow02", "flow04", "flow06"):
        assert edge_groups[branch_id].attrib["data-route"] == "process-branch"
        branch_path = edge_groups[branch_id].find(f"{{{SVG_NAMESPACE}}}path")
        assert branch_path is not None
        branch_values = [
            float(value) for value in re.findall(r"-?[0-9.]+", branch_path.attrib["d"])
        ]
        branch_y_values = branch_values[1::2]
        assert min(branch_y_values) >= execute_y + 166
        assert max(branch_y_values) <= stop_y

    assert edge_groups["flow09"].attrib["data-route"] == "feedback-return"
    feedback_path = edge_groups["flow09"].find(f"{{{SVG_NAMESPACE}}}path")
    assert feedback_path is not None
    assert " L " in feedback_path.attrib["d"]
    line_match = re.search(r" L [-0-9.]+ ([-0-9.]+) ", feedback_path.attrib["d"])
    assert line_match is not None
    feedback_baseline_y = float(line_match.group(1))
    deepest_node_bottom = max(live_y, stop_y) + 166
    assert feedback_baseline_y > deepest_node_bottom

    for group in node_groups.values():
        text_nodes = group.findall(f"{{{SVG_NAMESPACE}}}text")
        assert [node.attrib["font-size"] for node in text_nodes] == ["10", "22", "19"]

    for group in edge_groups.values():
        text_node = group.find(f"{{{SVG_NAMESPACE}}}text")
        assert text_node is not None
        assert text_node.attrib["font-size"] == "17"

    landscape = _parse(render_native_diagram(_load("system-landscape-v1.json")))
    landscape_node = next(
        element
        for element in landscape.iter()
        if element.attrib.get("data-source-kind") == "node"
    )
    landscape_text = landscape_node.findall(f"{{{SVG_NAMESPACE}}}text")
    assert [node.attrib["font-size"] for node in landscape_text] == ["10", "22", "17"]
    landscape_view_box = [float(value) for value in landscape.attrib["viewBox"].split()]
    assert landscape_view_box[2] <= 1650
    landscape_edge = next(
        element
        for element in landscape.iter()
        if element.attrib.get("data-source-kind") == "edge"
    )
    edge_text = landscape_edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert edge_text is not None
    assert edge_text.attrib["font-size"] == "15"

    narrative = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    narrative_node = next(
        element
        for element in narrative.iter()
        if element.attrib.get("data-source-kind") == "node"
    )
    narrative_rect = narrative_node.find(f"{{{SVG_NAMESPACE}}}rect")
    assert narrative_rect is not None
    assert float(narrative_rect.attrib["width"]) == 320
    narrative_text = narrative_node.findall(f"{{{SVG_NAMESPACE}}}text")
    assert [node.attrib["font-size"] for node in narrative_text] == ["10", "22", "19"]
    narrative_view_box = [float(value) for value in narrative.attrib["viewBox"].split()]
    assert narrative_view_box[2] <= 1450

def test_narrative_groups_follow_their_content_height_and_cross_column_edges_use_elbows() -> None:
    root = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    groups = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "group"
    }
    region_heights = {}
    for group_id, group in groups.items():
        rect = group.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        region_heights[group_id] = float(rect.attrib["height"])
    assert region_heights["orientation"] == region_heights["proof"]
    assert region_heights["orientation"] < region_heights["movement"]

    edges = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    for edge_id in ("journey02", "journey05"):
        edge = edges[edge_id]
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        assert edge.attrib["data-route"] == "narrative-elbow"
        assert " L " in path.attrib["d"]
        assert " C " not in path.attrib["d"]


def test_narrative_feedback_loop_hugs_content_and_labels_the_return_near_target() -> None:
    root = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    nodes = _node_boxes(root)
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == "journey07"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and label is not None
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", path.attrib["d"])]
    xs = numbers[0::2]
    ys = numbers[1::2]
    question = nodes["question"]
    meaning = nodes["meaning"]
    label_box = _rect_box(label)
    assert min(xs) >= question[0] - 14.1
    assert max(xs) <= meaning[0] + meaning[2] + 14.1
    assert min(ys) == 120.0
    assert label_box[1] + label_box[3] < question[1]
    assert label_box[0] < question[0] + question[2]
    other_labels = [
        box
        for edge_id, box in _edge_label_boxes(root).items()
        if edge_id != "journey07"
    ]
    assert min(ys) < min(box[1] for box in other_labels)
    assert not any(_boxes_overlap(label_box, box) for box in nodes.values())


def test_narrow_knowledge_map_labels_remain_complete_without_ellipsis() -> None:
    raw = _load("system-landscape-v1.json")
    root = _parse(render_native_diagram(raw))
    edges = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    source_edges = {edge["id"]: edge for edge in raw["edges"]}
    for edge_id in ("land02", "land06"):
        edge = edges[edge_id]
        text = edge.find(f"{{{SVG_NAMESPACE}}}text")
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert text is not None and rect is not None
        lines = [
            "".join(tspan.itertext())
            for tspan in text.findall(f"{{{SVG_NAMESPACE}}}tspan")
        ]
        assert " ".join(lines) == source_edges[edge_id]["label"]
        assert "…" not in "".join(lines)
        assert text.attrib["font-size"] == "14"
        assert float(rect.attrib["width"]) <= 118.0


def test_narrative_summary_wrapping_avoids_nonfinal_single_word_orphans() -> None:
    root = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    for node in root.iter():
        if node.attrib.get("data-source-kind") != "node":
            continue
        texts = node.findall(f"{{{SVG_NAMESPACE}}}text")
        assert texts
        summary_lines = [
            "".join(tspan.itertext())
            for tspan in texts[-1].findall(f"{{{SVG_NAMESPACE}}}tspan")
        ]
        assert summary_lines
        assert all(len(line.split()) >= 2 for line in summary_lines[:-1])


def test_single_narrative_feedback_path_is_visually_subordinate() -> None:
    root = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == "journey07"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert path is not None
    assert path.attrib["stroke-opacity"] == "0.42"


def test_grouped_vertical_relations_and_feedback_use_quiet_routes() -> None:
    landscape = _parse(render_native_diagram(_load("system-landscape-v1.json")))
    edges = {
        element.attrib["data-source-id"]: element
        for element in landscape.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    assert edges["land01"].attrib["data-route"] == "vertical"
    assert edges["land04"].attrib["data-route"] == "vertical"
    assert edges["land05"].attrib["data-route"] == "vertical"
    assert edges["land07"].attrib["data-route"] == "vertical"
    assert edges["land09"].attrib["data-route"] == "feedback-return"

    narrative = _parse(render_native_diagram(_load("narrative-journey-v1.json")))
    narrative_edges = {
        element.attrib["data-source-id"]: element
        for element in narrative.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    assert narrative_edges["journey01"].attrib["data-route"] == "vertical"
    assert narrative_edges["journey03"].attrib["data-route"] == "vertical"
    assert narrative_edges["journey04"].attrib["data-route"] == "vertical"
    assert narrative_edges["journey06"].attrib["data-route"] == "vertical"
    assert narrative_edges["journey07"].attrib["data-route"] == "feedback-return"


def test_narrative_diagonal_edge_labels_use_vertical_corridors_without_word_breaks() -> None:
    raw = _load("narrative-journey-v1.json")
    root = _parse(render_native_diagram(raw))
    node_boxes = _node_boxes(root)
    edges = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    expected_lines = {
        "journey02": ["macht Bruch", "sichtbar"],
        "journey05": ["erzeugt", "Beleg"],
    }
    edge_by_id = {edge["id"]: edge for edge in raw["edges"]}

    for edge_id, expected in expected_lines.items():
        edge = edges[edge_id]
        label_rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        label_text = edge.find(f"{{{SVG_NAMESPACE}}}text")
        assert label_rect is not None and label_text is not None
        lines = [
            "".join(tspan.itertext())
            for tspan in label_text.findall(f"{{{SVG_NAMESPACE}}}tspan")
        ]
        assert lines == expected
        assert "…" not in "".join(lines)
        if edge_id == "journey05":
            assert label_text.attrib["font-size"] == "15"
            assert float(label_rect.attrib["width"]) == 85.0

        source = edge_by_id[edge_id]
        source_box = node_boxes[source["from"]]
        target_box = node_boxes[source["to"]]
        label_box = _rect_box(label_rect)
        assert all(
            not _boxes_overlap(label_box, node_box)
            for node_box in node_boxes.values()
        )
        if edge_id == "journey02":
            upper = min(source_box, target_box, key=lambda box: box[1])
            lower = max(source_box, target_box, key=lambda box: box[1])
            upper_bottom = upper[1] + upper[3]
            lower_top = lower[1]
            assert upper_bottom < label_box[1]
            assert label_box[1] + label_box[3] < lower_top


@pytest.mark.parametrize(
    ("fixture_name", "edge_id"),
    (("system-landscape-v1.json", "land09"), ("narrative-journey-v1.json", "journey07")),
)
def test_non_process_feedback_label_stays_outside_every_card(
    fixture_name: str, edge_id: str
) -> None:
    raw_model = _load(fixture_name)
    root = _parse(render_native_diagram(raw_model))
    node_boxes = _node_boxes(root)
    source = next(edge for edge in raw_model["edges"] if edge["id"] == edge_id)

    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == edge_id
    )
    label_rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    label_text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert label_rect is not None
    assert label_text is not None
    assert path is not None
    lx, ly, lw, lh = _rect_box(label_rect)
    assert lw >= 230
    assert len(label_text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 1
    _assert_feedback_route_avoids_cards(root, edge_id)

    points = [
        (float(x), float(y))
        for x, y in re.findall(r"[ML] ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(points) >= 2
    assert _point_on_box_boundary(points[0], node_boxes[source["from"]])
    assert _point_on_box_boundary(points[-1], node_boxes[source["to"]])
    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert all(0 <= x <= canvas_width and 0 <= y <= canvas_height for x, y in points)

    label_center_y = ly + lh / 2
    if raw_model["intent"] == "narrative":
        min_node_top = min(y for _, y, _, _ in node_boxes.values())
        return_segments = [
            (x1, x2, y1)
            for (x1, y1), (x2, y2) in zip(points, points[1:])
            if y1 == y2 and y1 < min_node_top
        ]
    else:
        max_node_bottom = max(y + height for _, y, _, height in node_boxes.values())
        return_segments = [
            (x1, x2, y1)
            for (x1, y1), (x2, y2) in zip(points, points[1:])
            if y1 == y2 and y1 > max_node_bottom
        ]
    assert return_segments
    assert any(abs(y - label_center_y) <= 0.1 for _, _, y in return_segments)


@pytest.mark.parametrize(
    ("fixture_name", "minimum_average_ratio"),
    (("system-landscape-v1.json", 0.98), ("narrative-journey-v1.json", 0.95)),
)
def test_non_process_summaries_preserve_readable_content(
    fixture_name: str, minimum_average_ratio: float
) -> None:
    raw = _load(fixture_name)
    root = _parse(render_native_diagram(raw))
    ratios: list[float] = []
    for node_source in raw["nodes"]:
        node = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-kind") == "node"
            and element.attrib.get("data-source-id") == node_source["id"]
        )
        summary = node.findall(f"{{{SVG_NAMESPACE}}}text")[2]
        rendered = " ".join(
            "".join(tspan.itertext())
            for tspan in summary.findall(f"{{{SVG_NAMESPACE}}}tspan")
        ).replace("…", "")
        ratios.append(len(rendered) / len(node_source["summary"]))
        assert all(
            "textLength" not in tspan.attrib
            for tspan in summary.findall(f"{{{SVG_NAMESPACE}}}tspan")
        )
    assert sum(ratios) / len(ratios) >= minimum_average_ratio


@pytest.mark.parametrize("fixture_name", GOLDEN_FILES)
def test_wide_dynamic_text_is_bounded_inside_renderer_boxes(fixture_name: str) -> None:
    raw = _load(fixture_name)
    node_id = raw["nodes"][0]["id"]
    edge_id = raw["edges"][0]["id"]
    group_id = raw["groups"][0]["id"]
    raw["nodes"][0]["label"] = "W" * 20
    raw["nodes"][0]["summary"] = "W" * 28
    raw["edges"][0]["label"] = "W" * 24
    raw["groups"][0]["label"] = "W" * 30

    def assert_bounded(text_node: ET.Element, max_width: float) -> None:
        assert text_node.attrib.get("clip-path", "").startswith("url(#native-clip-")
        for tspan in text_node.findall(f"{{{SVG_NAMESPACE}}}tspan"):
            if "textLength" in tspan.attrib:
                assert float(tspan.attrib["textLength"]) <= max_width
                assert tspan.attrib["lengthAdjust"] == "spacingAndGlyphs"
            else:
                assert text_node.attrib["clip-path"].startswith("url(#native-clip-")

    root = _parse(render_native_diagram(raw))
    node = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == node_id
        and element.attrib.get("data-source-kind") == "node"
    )
    node_rect = node.find(f"{{{SVG_NAMESPACE}}}rect")
    assert node_rect is not None
    node_max_width = float(node_rect.attrib["width"]) - 36
    node_texts = node.findall(f"{{{SVG_NAMESPACE}}}text")
    for text_node in node_texts[1:]:
        assert_bounded(text_node, node_max_width)

    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == edge_id
        and element.attrib.get("data-source-kind") == "edge"
    )
    edge_rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    edge_text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    edge_clip_rect = edge.find(
        f".//{{{SVG_NAMESPACE}}}clipPath/{{{SVG_NAMESPACE}}}rect"
    )
    assert edge_rect is not None
    assert edge_text is not None
    assert edge_clip_rect is not None
    assert_bounded(edge_text, float(edge_clip_rect.attrib["width"]))

    group = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == group_id
        and element.attrib.get("data-source-kind") == "group"
    )
    group_rect = group.find(f"{{{SVG_NAMESPACE}}}rect")
    group_text = group.find(f"{{{SVG_NAMESPACE}}}text")
    assert group_rect is not None
    assert group_text is not None
    assert_bounded(group_text, float(group_rect.attrib["width"]) - 40)


def test_existing_non_process_wide_card_label_wraps_without_glyph_compression() -> None:
    root = _parse(render_native_diagram(_load("system-landscape-v1.json")))
    node = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
        and (title := element.find(f"{{{SVG_NAMESPACE}}}title")) is not None
        and "".join(title.itertext()) == "Produktive Laufzeit"
    )
    label_text = node.findall(f"{{{SVG_NAMESPACE}}}text")[1]
    tspans = label_text.findall(f"{{{SVG_NAMESPACE}}}tspan")

    assert label_text.attrib["clip-path"].startswith("url(#native-clip-node-")
    assert tspans
    assert all("textLength" not in tspan.attrib for tspan in tspans)
    assert len(tspans) >= 2


def test_uppercase_width_regression_has_a_hard_clip_bound() -> None:
    raw = _load("system-landscape-v1.json")
    node_id = raw["nodes"][0]["id"]
    raw["nodes"][0]["label"] = "O" * 12

    root = _parse(render_native_diagram(raw))
    node = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
        and element.attrib.get("data-source-id") == node_id
    )
    label_text = node.findall(f"{{{SVG_NAMESPACE}}}text")[1]
    clip_reference = label_text.attrib["clip-path"]
    assert clip_reference.startswith("url(#native-clip-node-")
    clip_id = clip_reference[5:-1]
    clip = root.find(f".//{{{SVG_NAMESPACE}}}clipPath[@id='{clip_id}']")
    assert clip is not None
    clip_rect = clip.find(f"{{{SVG_NAMESPACE}}}rect")
    assert clip_rect is not None
    assert float(clip_rect.attrib["width"]) == 214.0
    assert label_text.findall(f"{{{SVG_NAMESPACE}}}tspan")


def test_process_branch_spanning_multiple_rows_uses_outer_gutter() -> None:
    raw = _load("decision-flow-v1.json")
    raw["nodes"].append(
        {
            "id": "defer",
            "label": "Später entscheiden",
            "kind": "risk",
            "group": "outcome",
            "summary": "Dritter Ausgang für einen mehrzeiligen Nebenpfad.",
        }
    )
    raw["edges"].append(
        {
            "id": "flow10",
            "from": "risk_gate",
            "to": "defer",
            "label": "später",
            "kind": "risk",
        }
    )

    root = _parse(render_native_diagram(raw))
    node_boxes = []
    for element in root.iter():
        if element.attrib.get("data-source-kind") != "node":
            continue
        rect = element.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes.append(
            (
                float(rect.attrib["x"]),
                float(rect.attrib["y"]),
                float(rect.attrib["width"]),
                float(rect.attrib["height"]),
            )
        )

    branch = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "flow10"
        and element.attrib.get("data-source-kind") == "edge"
    )
    assert branch.attrib["data-route"] == "process-branch"
    path = branch.find(f"{{{SVG_NAMESPACE}}}path")
    assert path is not None
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(line_points) == 3
    gutter_x = line_points[0][0]
    assert line_points[1][0] == gutter_x
    assert gutter_x > max(x + width for x, _, width, _ in node_boxes)
    for corridor_y in (line_points[0][1], line_points[1][1]):
        assert all(
            not (y < corridor_y < y + height)
            for _, y, _, height in node_boxes
        )


def test_multiple_long_process_branches_use_distinct_gutter_lanes_and_labels() -> None:
    raw = _load("decision-flow-v1.json")
    raw["nodes"].extend(
        [
            {
                "id": "defer",
                "label": "Später entscheiden",
                "kind": "risk",
                "group": "outcome",
                "summary": "Dritter Ausgang für einen mehrzeiligen Nebenpfad.",
            },
            {
                "id": "escalate",
                "label": "Eskalieren",
                "kind": "risk",
                "group": "outcome",
                "summary": "Vierter Ausgang für einen zweiten langen Nebenpfad.",
            },
        ]
    )
    raw["edges"].extend(
        [
            {
                "id": "flow10",
                "from": "risk_gate",
                "to": "defer",
                "label": "später",
                "kind": "risk",
            },
            {
                "id": "flow11",
                "from": "risk_gate",
                "to": "escalate",
                "label": "eskalieren",
                "kind": "risk",
            },
        ]
    )

    root = _parse(render_native_diagram(raw))
    node_boxes = []
    for element in root.iter():
        if element.attrib.get("data-source-kind") != "node":
            continue
        rect = element.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes.append(
            tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        )
    max_node_right = max(x + width for x, _, width, _ in node_boxes)

    branches = []
    for edge_id in ("flow10", "flow11"):
        edge = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-kind") == "edge"
            and element.attrib.get("data-source-id") == edge_id
        )
        assert edge.attrib["data-route"] == "process-branch"
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None
        assert rect is not None
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
        ]
        assert len(line_points) == 3
        gutter_x = line_points[0][0]
        assert line_points[1][0] == gutter_x
        assert gutter_x > max_node_right
        branches.append(
            (
                gutter_x,
                tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height")),
            )
        )

    assert branches[0][0] != branches[1][0]
    (ax, ay, aw, ah), (bx, by, bw, bh) = branches[0][1], branches[1][1]
    assert ax > max_node_right and bx > max_node_right
    assert not (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)



def _assert_feedback_route_avoids_cards(root: ET.Element, edge_id: str) -> None:
    node_boxes = list(_node_boxes(root).values())
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == edge_id
    )
    assert edge.attrib["data-route"] == "feedback-return"
    label_rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert label_rect is not None
    assert path is not None
    label_box = _rect_box(label_rect)
    assert all(not _boxes_overlap(label_box, node_box) for node_box in node_boxes)
    _, ly, _, lh = label_box
    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert 0 <= ly and ly + lh <= canvas_height

    points = [
        (float(x), float(y))
        for x, y in re.findall(r"[ML] ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(points) >= 2
    assert all(0 <= x <= canvas_width and 0 <= y <= canvas_height for x, y in points)
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 == x2:
            segment_top, segment_bottom = sorted((y1, y2))
            assert all(
                not (
                    x < x1 < x + width
                    and segment_top < y + height
                    and segment_bottom > y
                )
                for x, y, width, height in node_boxes
            )
        elif y1 == y2:
            segment_left, segment_right = sorted((x1, x2))
            assert all(
                not (
                    y < y1 < y + height
                    and segment_left < x + width
                    and segment_right > x
                )
                for x, y, width, height in node_boxes
            )
        else:
            raise AssertionError("feedback route must remain orthogonal")


def _feedback_model(*, grouped: bool, source: str, target: str, label: str) -> dict:
    raw = _load("system-landscape-v1.json")
    raw["id"] = f"feedback_{'grouped' if grouped else 'ungrouped'}_{source}_{target}"
    if grouped:
        raw["groups"] = [
            {"id": "left", "label": "Links"},
            {"id": "right", "label": "Rechts"},
        ]
        raw["nodes"] = [
            {
                "id": f"a{row}",
                "label": f"A{row}",
                "kind": "system",
                "group": "left",
                "summary": "Karte links.",
            }
            for row in range(3)
        ] + [
            {
                "id": f"b{row}",
                "label": f"B{row}",
                "kind": "system",
                "group": "right",
                "summary": "Karte rechts.",
            }
            for row in range(3)
        ]
    else:
        raw["groups"] = []
        raw["nodes"] = [
            {
                "id": f"u{index}",
                "label": f"U{index}",
                "kind": "system",
                "group": None,
                "summary": "Ungruppierte Karte.",
            }
            for index in range(9)
        ]
    raw["edges"] = [
        {
            "id": "feedback_case",
            "from": source,
            "to": target,
            "label": label,
            "kind": "feedback",
        }
    ]
    return raw


def test_wide_purpose_is_naturally_wrapped_and_hard_clipped() -> None:
    raw = _load("system-landscape-v1.json")
    raw["purpose"] = "W" * 400
    root = _parse(render_native_diagram(raw))

    purpose = next(
        element
        for element in root.findall(f"{{{SVG_NAMESPACE}}}text")
        if element.attrib.get("clip-path") == "url(#native-clip-purpose)"
    )
    tspans = purpose.findall(f"{{{SVG_NAMESPACE}}}tspan")
    assert 1 <= len(tspans) <= 2
    assert all("textLength" not in tspan.attrib for tspan in tspans)
    clip = root.find(
        f".//{{{SVG_NAMESPACE}}}clipPath[@id='native-clip-purpose']"
    )
    assert clip is not None
    rect = clip.find(f"{{{SVG_NAMESPACE}}}rect")
    assert rect is not None
    view_width = float(root.attrib["viewBox"].split()[2])
    assert float(rect.attrib["x"]) == 48.0
    assert float(rect.attrib["width"]) == view_width - 96.0


@pytest.mark.parametrize(
    ("grouped", "source", "target"),
    (
        (True, "a0", "a1"),
        (True, "a0", "a2"),
        (True, "a0", "b0"),
        (True, "b0", "a0"),
        (False, "u0", "u4"),
        (False, "u0", "u8"),
        (False, "u4", "u5"),
        (False, "u5", "u4"),
    ),
)
def test_non_process_feedback_all_directions_avoid_cards(
    grouped: bool, source: str, target: str
) -> None:
    raw = _feedback_model(
        grouped=grouped,
        source=source,
        target=target,
        label="Rückmeldung bleibt außerhalb der Karten",
    )
    root = _parse(render_native_diagram(raw))
    _assert_feedback_route_avoids_cards(root, "feedback_case")


def test_ungrouped_bottom_row_two_line_feedback_reserves_footer() -> None:
    raw = _load("system-landscape-v1.json")
    raw["id"] = "feedback_bottom_footer"
    raw["groups"] = []
    raw["nodes"] = [
        {
            "id": f"u{index}",
            "label": f"U{index}",
            "kind": "system",
            "group": None,
            "summary": "Ungruppierte Karte.",
        }
        for index in range(8)
    ]
    raw["edges"] = [
        {
            "id": "bottom_feedback",
            "from": "u4",
            "to": "u7",
            "label": "Eine absichtlich lange Rückmeldung mit zwei Zeilen",
            "kind": "feedback",
        }
    ]
    root = _parse(render_native_diagram(raw))
    _assert_feedback_route_avoids_cards(root, "bottom_feedback")
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "bottom_feedback"
    )
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert label is not None and text is not None
    assert len(text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 2
    max_node_bottom = max(
        float(rect.attrib["y"]) + float(rect.attrib["height"])
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    )
    assert float(label.attrib["y"]) >= max_node_bottom + 10


def _minimal_process_model(node_count: int) -> dict:
    raw = _load("decision-flow-v1.json")
    raw["id"] = f"process_{node_count}"
    raw["groups"] = []
    raw["nodes"] = [
        {
            "id": f"n{index}",
            "label": f"N{index}",
            "kind": "action",
            "group": None,
            "summary": "Prozesskarte.",
        }
        for index in range(node_count)
    ]
    raw["edges"] = []
    return raw


def test_adjacent_ungrouped_process_branch_stays_in_row_corridor() -> None:
    raw = _minimal_process_model(8)
    raw["edges"] = [
        {
            "id": "adjacent_branch",
            "from": "n0",
            "to": "n7",
            "label": "x",
            "kind": "risk",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "adjacent_branch"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and rect is not None
    assert edge.attrib["data-route"] == "process-branch"
    assert " L " not in path.attrib["d"]
    node_boxes = [
        tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    ]
    rows = sorted({y for _, y, _, _ in node_boxes})
    assert len(rows) == 2
    upper_bottom = rows[0] + 166.0
    lower_top = rows[1]
    assert lower_top - upper_bottom == 70.0
    label_y = float(rect.attrib["y"])
    label_height = float(rect.attrib["height"])
    assert upper_bottom < label_y and label_y + label_height < lower_top

def test_single_long_process_branch_is_card_safe_and_order_independent() -> None:
    raw = _minimal_process_model(18)
    long_edge = {
        "id": "single_long",
        "from": "n0",
        "to": "n13",
        "label": "W" * 120,
        "kind": "risk",
    }
    fillers = [
        {
            "id": f"filler{index}",
            "from": f"n{index + 1}",
            "to": f"n{index + 1}",
            "label": "a",
            "kind": "association",
        }
        for index in range(4)
    ]

    def geometry(edges: list[dict]) -> tuple[str, tuple[float, float, float, float], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = edges
        root = _parse(render_native_diagram(candidate))
        edge = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == "single_long"
        )
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None and rect is not None
        box = tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        return path.attrib["d"], box, root

    forward_path, forward_box, forward_root = geometry([long_edge, *fillers])
    reverse_path, reverse_box, _ = geometry([*fillers, long_edge])
    assert forward_path == reverse_path
    assert forward_box == reverse_box
    assert " L " in forward_path

    lx, ly, lw, lh = forward_box
    node_boxes = [
        tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        for node in forward_root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    ]
    assert all(
        not (lx < x + width and lx + lw > x and ly < y + height and ly + lh > y)
        for x, y, width, height in node_boxes
    )
    first_row_bottom = min(y for _, y, _, _ in node_boxes) + 166.0
    second_row_top = sorted({y for _, y, _, _ in node_boxes})[1]
    assert first_row_bottom < ly and ly + lh < second_row_top


def _many_long_branches_model() -> dict:
    raw = _minimal_process_model(18)
    edges = [
        {
            "id": "long0",
            "from": "n0",
            "to": "n13",
            "label": "weiter Bogen",
            "kind": "risk",
        }
    ]
    long_label = "absichtlich sehr lange zweizeilige Verzweigungsbeschriftung"
    for index in range(8):
        edges.append(
            {
                "id": f"long{index + 1}",
                "from": f"n{index % 6}",
                "to": f"n{12 + ((index + 2 + index // 6) % 6)}",
                "label": long_label if index % 2 else "kurz",
                "kind": "risk",
            }
        )
    raw["edges"] = edges
    return raw


def _long_branch_geometry(root: ET.Element) -> dict[str, tuple[float, float, float, float, float]]:
    result: dict[str, tuple[float, float, float, float, float]] = {}
    for edge in root.iter():
        edge_id = edge.attrib.get("data-source-id", "")
        if not edge_id.startswith("long"):
            continue
        assert edge.attrib["data-route"] == "process-branch"
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None and rect is not None
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
        ]
        assert len(line_points) == 3
        result[edge_id] = (
            line_points[0][0],
            float(rect.attrib["x"]),
            float(rect.attrib["y"]),
            float(rect.attrib["width"]),
            float(rect.attrib["height"]),
        )
    return result


def test_many_long_process_branch_labels_pack_order_independently_and_expand_canvas() -> None:
    raw = _many_long_branches_model()
    no_edges = copy.deepcopy(raw)
    no_edges["edges"] = []
    baseline_height = float(
        _parse(render_native_diagram(no_edges)).attrib["viewBox"].split()[3]
    )
    forward = _parse(render_native_diagram(raw))
    reversed_raw = copy.deepcopy(raw)
    reversed_raw["edges"] = list(reversed(reversed_raw["edges"]))
    reverse = _parse(render_native_diagram(reversed_raw))

    forward_geometry = _long_branch_geometry(forward)
    reverse_geometry = _long_branch_geometry(reverse)
    assert forward_geometry == reverse_geometry
    assert len(forward_geometry) == 9
    assert len({values[0] for values in forward_geometry.values()}) == 9

    boxes = [values[1:] for values in forward_geometry.values()]
    for index, (ax, ay, aw, ah) in enumerate(boxes):
        for bx, by, bw, bh in boxes[index + 1 :]:
            assert not (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)
    canvas_height = float(forward.attrib["viewBox"].split()[3])
    assert canvas_height > baseline_height
    assert all(y + height <= canvas_height for _, y, _, height in boxes)
    assert {height for _, _, _, height in boxes} >= {29.0, 48.0}


def test_short_process_label_keeps_natural_text_inside_clip_guard() -> None:
    root = _parse(render_native_diagram(_load("decision-flow-v1.json")))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == "flow04"
    )
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    clip_rect = edge.find(f".//{{{SVG_NAMESPACE}}}clipPath/{{{SVG_NAMESPACE}}}rect")
    assert text is not None and clip_rect is not None
    tspans = text.findall(f"{{{SVG_NAMESPACE}}}tspan")
    assert [tspan.text for tspan in tspans] == ["nein"]
    assert all("textLength" not in tspan.attrib for tspan in tspans)
    assert float(clip_rect.attrib["width"]) >= 42.0


def test_wide_title_is_naturally_bounded_and_hard_clipped() -> None:
    raw = _load("system-landscape-v1.json")
    raw["title"] = "W" * 160
    root = _parse(render_native_diagram(raw))

    title_text = next(
        element
        for element in root.findall(f"{{{SVG_NAMESPACE}}}text")
        if element.attrib.get("font-size") == "28"
    )
    assert title_text.attrib["clip-path"] == "url(#native-clip-title)"
    tspans = title_text.findall(f"{{{SVG_NAMESPACE}}}tspan")
    assert len(tspans) == 1
    assert all("textLength" not in tspan.attrib for tspan in tspans)
    assert tspans[0].text is not None and tspans[0].text.endswith("…")
    assert len(tspans[0].text) < len(raw["title"])
    clip = root.find(f".//{{{SVG_NAMESPACE}}}clipPath[@id='native-clip-title']")
    assert clip is not None
    rect = clip.find(f"{{{SVG_NAMESPACE}}}rect")
    assert rect is not None
    view_width = float(root.attrib["viewBox"].split()[2])
    assert float(rect.attrib["width"]) == view_width - 96.0


def test_non_process_feedback_self_loop_uses_safe_outer_route() -> None:
    raw = _feedback_model(
        grouped=False,
        source="u0",
        target="u0",
        label="Rückmeldung bleibt außerhalb der Karte",
    )
    root = _parse(render_native_diagram(raw))
    _assert_feedback_route_avoids_cards(root, "feedback_case")


def test_process_same_column_feedback_uses_outer_gutter() -> None:
    raw = _minimal_process_model(18)
    raw["edges"] = [
        {
            "id": "vertical_feedback",
            "from": "n0",
            "to": "n12",
            "label": "zurück",
            "kind": "feedback",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "vertical_feedback"
    )
    assert edge.attrib["data-route"] == "feedback-return"
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and label is not None
    node_boxes = [
        tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    ]
    max_node_right = max(x + width for x, _, width, _ in node_boxes)
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(line_points) == 3
    assert line_points[0][0] == line_points[1][0] > max_node_right
    for corridor_y in (line_points[0][1], line_points[1][1]):
        assert all(not (y < corridor_y < y + height) for _, y, _, height in node_boxes)
    lx, ly, lw, lh = (
        float(label.attrib[key]) for key in ("x", "y", "width", "height")
    )
    assert all(
        not (lx < x + width and lx + lw > x and ly < y + height and ly + lh > y)
        for x, y, width, height in node_boxes
    )


def test_process_bottom_row_two_line_feedback_reserves_footer() -> None:
    raw = _minimal_process_model(8)
    raw["edges"] = [
        {
            "id": "bottom_feedback",
            "from": "n7",
            "to": "n6",
            "label": "Eine absichtlich lange Rückmeldung mit zwei Zeilen",
            "kind": "feedback",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "bottom_feedback"
    )
    assert edge.attrib["data-route"] == "feedback-return"
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert label is not None and text is not None
    assert len(text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 2
    max_node_bottom = max(
        float(rect.attrib["y"]) + float(rect.attrib["height"])
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    )
    assert float(label.attrib["y"]) >= max_node_bottom + 10
    assert float(label.attrib["y"]) + float(label.attrib["height"]) <= float(
        root.attrib["viewBox"].split()[3]
    )


def test_group_header_clip_ids_do_not_collide_with_real_ungrouped_group_id() -> None:
    raw = _load("system-landscape-v1.json")
    raw["groups"] = [{"id": "ungrouped", "label": "Echte Gruppe"}]
    raw["nodes"] = [
        {
            "id": "inside",
            "label": "Drinnen",
            "kind": "system",
            "group": "ungrouped",
            "summary": "In der echten Gruppe.",
        },
        {
            "id": "outside",
            "label": "Draußen",
            "kind": "system",
            "group": None,
            "summary": "Im synthetischen Bereich.",
        },
    ]
    raw["edges"] = []
    root = _parse(render_native_diagram(raw))
    clip_ids = [
        clip.attrib["id"]
        for clip in root.findall(f".//{{{SVG_NAMESPACE}}}clipPath")
    ]
    assert len(clip_ids) == len(set(clip_ids))
    region_clips = [clip_id for clip_id in clip_ids if clip_id.startswith("native-clip-region-")]
    assert len(region_clips) == 2
    assert len(set(region_clips)) == 2


def test_process_upper_row_reverse_feedback_uses_row_gap_and_outer_gutter() -> None:
    raw = _minimal_process_model(12)
    raw["edges"] = [
        {
            "id": "upper_reverse_feedback",
            "from": "n1",
            "to": "n0",
            "label": "zurück",
            "kind": "feedback",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "upper_reverse_feedback"
    )
    assert edge.attrib["data-route"] == "feedback-return"
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and label is not None
    node_boxes = [
        tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    ]
    max_node_right = max(x + width for x, _, width, _ in node_boxes)
    first_row_bottom = min(y for _, y, _, _ in node_boxes) + 166.0
    second_row_top = sorted({y for _, y, _, _ in node_boxes})[1]
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(line_points) == 3
    assert line_points[0][0] == line_points[1][0] > max_node_right
    corridor_y = line_points[0][1]
    assert first_row_bottom < corridor_y < second_row_top
    assert line_points[1][1] == corridor_y == line_points[2][1]
    lx, ly, lw, lh = (
        float(label.attrib[key]) for key in ("x", "y", "width", "height")
    )
    assert first_row_bottom < ly and ly + lh < second_row_top
    assert all(
        not (lx < x + width and lx + lw > x and ly < y + height and ly + lh > y)
        for x, y, width, height in node_boxes
    )


@pytest.mark.parametrize(
    ("intent", "source", "target"),
    (("process", "n5", "n11"), ("architecture", "n3", "n7"), ("narrative", "n5", "n11")),
)
def test_long_vertical_edge_label_stays_inside_canvas(
    intent: str, source: str, target: str
) -> None:
    raw = _minimal_process_model(12)
    raw["intent"] = intent
    raw["edges"] = [
        {
            "id": "vertical_long_label",
            "from": source,
            "to": target,
            "label": "W" * 120,
            "kind": "risk",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "vertical_long_label"
    )
    assert edge.attrib["data-route"] == "vertical"
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    clip = edge.find(f".//{{{SVG_NAMESPACE}}}clipPath/{{{SVG_NAMESPACE}}}rect")
    assert label is not None and clip is not None
    canvas_width = float(root.attrib["viewBox"].split()[2])
    for rect in (label, clip):
        x = float(rect.attrib["x"])
        width = float(rect.attrib["width"])
        assert 0 <= x
        assert x + width <= canvas_width


def test_two_line_same_row_process_label_clears_header_and_cards() -> None:
    raw = _minimal_process_model(6)
    raw["edges"] = [
        {
            "id": "wide_same_row",
            "from": "n0",
            "to": "n1",
            "label": "W" * 120,
            "kind": "risk",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "wide_same_row"
    )
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    purpose_clip = root.find(
        f".//{{{SVG_NAMESPACE}}}clipPath[@id='native-clip-purpose']/{{{SVG_NAMESPACE}}}rect"
    )
    assert label is not None and text is not None and purpose_clip is not None
    assert len(text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 2
    label_top = float(label.attrib["y"])
    label_bottom = label_top + float(label.attrib["height"])
    purpose_bottom = float(purpose_clip.attrib["y"]) + float(purpose_clip.attrib["height"])
    first_row_top = min(
        float(rect.attrib["y"])
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    )
    assert label_top >= purpose_bottom + 4
    assert label_bottom <= first_row_top - 4


def test_two_line_rightmost_process_self_loop_label_stays_inside_canvas_and_card() -> None:
    raw = _minimal_process_model(6)
    raw["edges"] = [
        {
            "id": "wide_loop",
            "from": "n5",
            "to": "n5",
            "label": "W" * 120,
            "kind": "risk",
        }
    ]
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "wide_loop"
    )
    node = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "node"
        and element.attrib.get("data-source-id") == "n5"
    )
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    clip = edge.find(f".//{{{SVG_NAMESPACE}}}clipPath/{{{SVG_NAMESPACE}}}rect")
    node_rect = node.find(f"{{{SVG_NAMESPACE}}}rect")
    assert label is not None and clip is not None and node_rect is not None
    canvas_width = float(root.attrib["viewBox"].split()[2])
    for rect in (label, clip):
        x = float(rect.attrib["x"])
        width = float(rect.attrib["width"])
        assert 0 <= x
        assert x + width <= canvas_width
    lx, ly, lw, lh = (float(label.attrib[key]) for key in ("x", "y", "width", "height"))
    nx, ny, nw, nh = (
        float(node_rect.attrib[key]) for key in ("x", "y", "width", "height")
    )
    assert not (lx < nx + nw and lx + lw > nx and ly < ny + nh and ly + lh > ny)


def test_two_line_grouped_process_label_clears_region_headers_and_cards() -> None:
    raw = _load("decision-flow-v1.json")
    flow = next(edge for edge in raw["edges"] if edge["id"] == "flow01")
    flow["label"] = "W" * 120
    root = _parse(render_native_diagram(raw))
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "flow01"
    )
    label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert label is not None and text is not None
    assert len(text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 2
    label_top = float(label.attrib["y"])
    label_bottom = label_top + float(label.attrib["height"])
    group_rects = [
        group.find(f"{{{SVG_NAMESPACE}}}rect")
        for group in root.iter()
        if group.attrib.get("data-source-kind") == "group"
    ]
    assert group_rects and all(rect is not None for rect in group_rects)
    group_header_bottom = max(
        float(rect.attrib["y"]) + 44 for rect in group_rects if rect is not None
    )
    endpoint_ids = {flow["from"], flow["to"]}
    endpoint_tops = [
        float(rect.attrib["y"])
        for node in root.iter()
        if node.attrib.get("data-source-kind") == "node"
        and node.attrib.get("data-source-id") in endpoint_ids
        for rect in [node.find(f"{{{SVG_NAMESPACE}}}rect")]
        if rect is not None
    ]
    assert len(endpoint_tops) == 2
    assert label_top >= group_header_bottom + 8
    assert label_bottom <= min(endpoint_tops) - 4

@pytest.mark.parametrize("fixture_name", GOLDEN_FILES)
def test_golden_edge_labels_clear_every_card(fixture_name: str) -> None:
    root = _parse(render_native_diagram(_load(fixture_name)))
    nodes = _node_boxes(root)
    labels = _edge_label_boxes(root)
    collisions = [
        (edge_id, node_id)
        for edge_id, label_box in labels.items()
        for node_id, node_box in nodes.items()
        if _boxes_overlap(label_box, node_box)
    ]
    assert collisions == []


@pytest.mark.parametrize("fixture_name", GOLDEN_FILES)
def test_golden_edge_labels_do_not_overlap_each_other(fixture_name: str) -> None:
    root = _parse(render_native_diagram(_load(fixture_name)))
    labels = list(_edge_label_boxes(root).items())
    collisions = [
        (edge_id, other_id)
        for index, (edge_id, label_box) in enumerate(labels)
        for other_id, other_box in labels[index + 1 :]
        if _boxes_overlap(label_box, other_box)
    ]
    assert collisions == []


def _feedback_geometry(
    raw: dict, edges: list[dict]
) -> tuple[dict[str, tuple[str, tuple[float, float, float, float]]], ET.Element]:
    candidate = copy.deepcopy(raw)
    candidate["edges"] = copy.deepcopy(edges)
    root = _parse(render_native_diagram(candidate))
    geometry: dict[str, tuple[str, tuple[float, float, float, float]]] = {}
    for edge in root.iter():
        edge_id = edge.attrib.get("data-source-id")
        if edge.attrib.get("data-source-kind") != "edge" or edge_id is None:
            continue
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None and rect is not None
        geometry[edge_id] = (path.attrib["d"], _rect_box(rect))
    return geometry, root


def _assert_feedback_geometry_is_distinct_and_order_independent(
    raw: dict, edges: list[dict]
) -> None:
    forward, root = _feedback_geometry(raw, edges)
    reverse, _ = _feedback_geometry(raw, list(reversed(edges)))
    assert forward == reverse
    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert len(boxes) == len(edges)
    assert len(set(boxes.values())) == len(edges)
    pairs = list(boxes.items())
    assert all(
        not _boxes_overlap(box, other_box)
        for index, (_, box) in enumerate(pairs)
        for _, other_box in pairs[index + 1 :]
    )
    node_boxes = list(_node_boxes(root).values())
    assert all(
        not _boxes_overlap(box, node_box)
        for box in boxes.values()
        for node_box in node_boxes
    )


def test_multiple_non_process_feedback_edges_use_distinct_stable_footer_lanes() -> None:
    raw = _feedback_model(
        grouped=False,
        source="u0",
        target="u4",
        label="placeholder",
    )
    edges = [
        {"id": "feedback_a", "from": "u0", "to": "u4", "label": "zurück A", "kind": "feedback"},
        {"id": "feedback_b", "from": "u4", "to": "u0", "label": "zurück B", "kind": "feedback"},
        {"id": "feedback_c", "from": "u1", "to": "u5", "label": "zurück C", "kind": "feedback"},
    ]
    _assert_feedback_geometry_is_distinct_and_order_independent(raw, edges)


def test_multiple_process_feedback_edges_use_distinct_stable_footer_lanes() -> None:
    raw = _minimal_process_model(18)
    edges = [
        {"id": "feedback_a", "from": "n0", "to": "n12", "label": "zurück A", "kind": "feedback"},
        {"id": "feedback_b", "from": "n12", "to": "n0", "label": "zurück B", "kind": "feedback"},
        {"id": "feedback_c", "from": "n1", "to": "n13", "label": "zurück C", "kind": "feedback"},
    ]
    _assert_feedback_geometry_is_distinct_and_order_independent(raw, edges)


def test_ellipsize_returns_empty_when_even_ellipsis_does_not_fit() -> None:
    size = 17
    ellipsis_width = _estimated_wrap_width("…", size=size)
    assert _ellipsize_to_width("abcdef", size=size, max_width=ellipsis_width - 0.1) == ""


@pytest.mark.parametrize(
    ("value", "max_width", "expected"),
    (
        ("MiWi.i", 25.0, ["Mi", "Wi", ".i"]),
        ("MiWi.i", 55.0, ["MiWi", ".i"]),
        ("MiWi.i", 95.0, ["MiWi.i"]),
        ("Übergrößenprüfung", 25.0, ["Ü", "be", "rg", "r", "ö", "ß", "en", "pr", "ü", "fu", "ng"]),
        ("Übergrößenprüfung", 55.0, ["Überg", "röße", "nprüf", "ung"]),
        ("Übergrößenprüfung", 95.0, ["Übergrö", "ßenprüfu", "ng"]),
        ("MWMWiiii[]{}", 25.0, ["M", "W", "M", "Wi", "iii[", "]{}"]),
        ("MWMWiiii[]{}", 55.0, ["MW", "MWii", "ii[]{}"]),
        ("MWMWiiii[]{}", 95.0, ["MWMWiii", "i[]{}"]),
    ),
)
def test_incremental_token_split_matches_legacy_width_contract(
    value: str, max_width: float, expected: list[str]
) -> None:
    def legacy_width(text: str) -> float:
        units = 0.0
        for character in text:
            if character == " " or character in "ilI.,'`:;!|[](){}":
                units += 0.35
            elif character in "MW@#%&QGmwo":
                units += 1.12
            elif ord(character) > 127:
                units += 0.9
            elif character.isupper():
                units += 0.86
            else:
                units += 0.58
        return units * 17

    pieces = _split_token_to_width(value, size=17, max_width=max_width)
    assert pieces == expected
    assert "".join(pieces) == value
    assert all(pieces)
    assert all(legacy_width(piece) <= max_width or len(piece) == 1 for piece in pieces)



def test_narrative_orphan_rebalance_does_not_relocate_an_orphan() -> None:
    assert _rebalance_single_word_lines(
        ["alpha beta", "gamma", "delta epsilon"],
        size=19,
        max_width=240.0,
    ) == ["alpha beta", "gamma", "delta epsilon"]
    assert _rebalance_single_word_lines(
        ["alpha beta gamma", "delta", "epsilon zeta"],
        size=19,
        max_width=240.0,
    ) == ["alpha beta", "gamma delta", "epsilon zeta"]


def test_long_vertical_non_process_edge_routes_around_intervening_card() -> None:
    raw = _feedback_model(grouped=True, source="a0", target="a2", label="unused")
    raw["edges"] = [
        {
            "id": "long_vertical",
            "from": "a0",
            "to": "a2",
            "label": "lange vertikale Beziehung",
            "kind": "evidence",
        }
    ]
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    nodes = _node_boxes(root)
    assert not _boxes_overlap(labels["long_vertical"], nodes["a1"])
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "long_vertical"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert path is not None
    assert edge.attrib["data-route"] == "vertical"
    assert path.attrib["d"].count(" L ") == 5


def test_process_feedback_lanes_start_after_long_branch_label_pack() -> None:
    raw = _many_long_branches_model()
    raw["edges"].extend(
        [
            {
                "id": "fba",
                "from": "n17",
                "to": "n0",
                "label": "erste Rückmeldung",
                "kind": "feedback",
            },
            {
                "id": "fbb",
                "from": "n16",
                "to": "n1",
                "label": "zweite Rückmeldung",
                "kind": "feedback",
            },
        ]
    )
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    long_bottom = max(
        y + height
        for edge_id, (_, y, _, height) in labels.items()
        if edge_id.startswith("long")
    )
    feedback_top = min(labels[edge_id][1] for edge_id in ("fba", "fbb"))
    assert feedback_top >= long_bottom + 10
    assert all(
        not _boxes_overlap(labels[long_id], labels[feedback_id])
        for long_id in labels
        if long_id.startswith("long")
        for feedback_id in ("fba", "fbb")
    )


def test_wrapped_single_narrative_feedback_uses_footer_not_purpose_strip() -> None:
    raw = _load("narrative-journey-v1.json")
    raw["purpose"] = (
        "Absichtlich zweizeiliger Purpose mit genug Text, damit dieser Bereich "
        "sicher zwei sichtbare Zeilen verwendet und geprüft werden kann."
    )
    feedback = next(edge for edge in raw["edges"] if edge["kind"] == "feedback")
    feedback["label"] = "Diese absichtlich lange Rückmeldung braucht sicher zwei Zeilen"
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    label = labels[feedback["id"]]
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == feedback["id"]
    )
    text = edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert text is not None
    assert len(text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 2
    max_node_bottom = max(
        y + height for _, y, _, height in _node_boxes(root).values()
    )
    assert label[1] >= max_node_bottom + _NARRATIVE_FEEDBACK_BOTTOM_CLEARANCE

def test_shared_long_vertical_non_process_labels_use_stable_outer_lanes() -> None:
    raw = _feedback_model(grouped=True, source="a0", target="a2", label="unused")
    raw["nodes"].extend(
        [
            {
                "id": "a3",
                "label": "A3",
                "kind": "system",
                "group": "left",
                "summary": "Vierte Karte links.",
            },
            {
                "id": "b3",
                "label": "B3",
                "kind": "system",
                "group": "right",
                "summary": "Vierte Karte rechts.",
            },
        ]
    )
    edges = [
        {
            "id": "long_a",
            "from": "a0",
            "to": "a2",
            "label": "erste lange Beziehung",
            "kind": "evidence",
        },
        {
            "id": "long_b",
            "from": "a0",
            "to": "a3",
            "label": "zweite lange Beziehung",
            "kind": "risk",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[str, tuple[float, float, float, float]]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        result = {}
        for edge in root.iter():
            edge_id = edge.attrib.get("data-source-id")
            if edge_id not in {"long_a", "long_b"}:
                continue
            path = edge.find(f"{{{SVG_NAMESPACE}}}path")
            rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
            assert path is not None and rect is not None
            result[edge_id] = (path.attrib["d"], _rect_box(rect))
        return result, root

    forward, root = geometry(edges)
    reverse, _ = geometry(list(reversed(edges)))
    assert forward == reverse
    assert set(forward) == {"long_a", "long_b"}

    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert not _boxes_overlap(boxes["long_a"], boxes["long_b"])
    node_boxes = list(_node_boxes(root).values())
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in boxes.values()
        for node_box in node_boxes
    )

    max_node_right = max(x + width for x, _, width, _ in node_boxes)
    gutter_xs = []
    for path, _ in forward.values():
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
        ]
        assert len(line_points) == 5
        gutter_xs.append(line_points[1][0])
        assert line_points[1][0] == line_points[2][0] > max_node_right
    assert len(set(gutter_xs)) == 2

    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert all(
        0 <= x and x + width <= canvas_width and 0 <= y and y + height <= canvas_height
        for x, y, width, height in boxes.values()
    )

def test_short_and_long_same_column_edges_share_corridor_without_label_overlap() -> None:
    raw = _feedback_model(grouped=True, source="a0", target="a2", label="unused")
    edges = [
        {
            "id": "short_a",
            "from": "a0",
            "to": "a1",
            "label": "kurze Beziehung",
            "kind": "evidence",
        },
        {
            "id": "long_a",
            "from": "a0",
            "to": "a2",
            "label": "lange Beziehung",
            "kind": "risk",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[str, tuple[float, float, float, float]]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        result = {}
        for edge in root.iter():
            edge_id = edge.attrib.get("data-source-id")
            if edge_id not in {"short_a", "long_a"}:
                continue
            path = edge.find(f"{{{SVG_NAMESPACE}}}path")
            rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
            assert path is not None and rect is not None
            result[edge_id] = (path.attrib["d"], _rect_box(rect))
        return result, root

    forward, root = geometry(edges)
    reverse, _ = geometry(list(reversed(edges)))
    assert forward == reverse
    assert set(forward) == {"short_a", "long_a"}

    short_only, _ = geometry([edges[0]])
    assert forward["short_a"] == short_only["short_a"]

    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert not _boxes_overlap(boxes["short_a"], boxes["long_a"])
    node_boxes = list(_node_boxes(root).values())
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in boxes.values()
        for node_box in node_boxes
    )

    max_node_right = max(x + width for x, _, width, _ in node_boxes)
    long_path = forward["long_a"][0]
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", long_path)
    ]
    assert len(line_points) == 5
    assert line_points[1][0] == line_points[2][0] > max_node_right

    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert all(
        0 <= x and x + width <= canvas_width and 0 <= y and y + height <= canvas_height
        for x, y, width, height in boxes.values()
    )

def test_opposite_direction_long_vertical_edges_share_physical_corridor() -> None:
    raw = _feedback_model(grouped=True, source="a0", target="a2", label="unused")
    raw["nodes"].extend(
        [
            {
                "id": "a3",
                "label": "A3",
                "kind": "system",
                "group": "left",
                "summary": "Vierte Karte links.",
            },
            {
                "id": "b3",
                "label": "B3",
                "kind": "system",
                "group": "right",
                "summary": "Vierte Karte rechts.",
            },
        ]
    )
    edges = [
        {
            "id": "down",
            "from": "a1",
            "to": "a3",
            "label": "abwärts im geteilten Korridor",
            "kind": "evidence",
        },
        {
            "id": "up",
            "from": "a2",
            "to": "a0",
            "label": "aufwärts im geteilten Korridor",
            "kind": "risk",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[str, tuple[float, float, float, float]]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        result = {}
        for edge in root.iter():
            edge_id = edge.attrib.get("data-source-id")
            if edge_id not in {"down", "up"}:
                continue
            path = edge.find(f"{{{SVG_NAMESPACE}}}path")
            rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
            assert path is not None and rect is not None
            result[edge_id] = (path.attrib["d"], _rect_box(rect))
        return result, root

    forward, root = geometry(edges)
    reverse, _ = geometry(list(reversed(edges)))
    assert forward == reverse
    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert not _boxes_overlap(boxes["down"], boxes["up"])

    node_boxes = list(_node_boxes(root).values())
    max_node_right = max(x + width for x, _, width, _ in node_boxes)
    gutter_xs = []
    for path, label_box in forward.values():
        assert all(not _boxes_overlap(label_box, node_box) for node_box in node_boxes)
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
        ]
        assert len(line_points) == 5
        gutter_xs.append(line_points[1][0])
        assert line_points[1][0] == line_points[2][0] > max_node_right
    assert len(set(gutter_xs)) == 2


def test_long_vertical_process_edge_routes_around_intervening_card() -> None:
    raw = _minimal_process_model(18)
    raw["edges"] = [
        {
            "id": "process_long_vertical",
            "from": "n0",
            "to": "n12",
            "label": "lange vertikale Prozessbeziehung",
            "kind": "evidence",
        }
    ]
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    nodes = _node_boxes(root)
    assert not _boxes_overlap(labels["process_long_vertical"], nodes["n6"])

    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "process_long_vertical"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert path is not None
    assert edge.attrib["data-route"] == "vertical"
    assert path.attrib["d"].count(" L ") == 5



def test_process_feedback_starts_after_packed_long_vertical_labels() -> None:
    raw = _minimal_process_model(30)
    raw["edges"] = [
        {
            "id": f"vertical_{index}",
            "from": "n24",
            "to": "n12",
            "label": f"lange vertikale Beziehung {index}",
            "kind": "evidence",
        }
        for index in range(4)
    ] + [
        {
            "id": "feedback",
            "from": "n29",
            "to": "n0",
            "label": "Rückmeldung zum Anfang",
            "kind": "feedback",
        }
    ]

    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    feedback = labels["feedback"]
    verticals = [labels[f"vertical_{index}"] for index in range(4)]
    assert all(not _boxes_overlap(feedback, box) for box in verticals)
    vertical_bottom = max(y + height for _, y, _, height in verticals)
    assert feedback[1] >= vertical_bottom + 10


def test_wrapped_adjacent_process_branches_use_outer_card_safe_lanes() -> None:
    raw = _load("decision-flow-v1.json")
    long_label = ("x " * 60).strip()
    assert len(long_label) == 119

    for edge_id in ("flow02", "flow04", "flow06"):
        candidate = copy.deepcopy(raw)
        edge = next(edge for edge in candidate["edges"] if edge["id"] == edge_id)
        edge["label"] = long_label
        root = _parse(render_native_diagram(candidate))
        labels = _edge_label_boxes(root)
        nodes = _node_boxes(root)
        label_box = labels[edge_id]
        assert all(not _boxes_overlap(label_box, node_box) for node_box in nodes.values())

        edge_group = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == edge_id
        )
        path = edge_group.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        assert edge_group.attrib["data-route"] == "process-branch"
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
        ]
        max_node_right = max(x + width for x, _, width, _ in nodes.values())
        assert any(x > max_node_right for x, _ in line_points)
        canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
        x, y, width, height = label_box
        assert 0 <= x and x + width <= canvas_width
        assert 0 <= y and y + height <= canvas_height


def test_single_long_process_branch_forces_feedback_below_card_field() -> None:
    raw = _minimal_process_model(14)
    long_edge = {
        "id": "long",
        "from": "n0",
        "to": "n13",
        "label": "lange prozessbeziehung",
        "kind": "flow",
    }
    feedback_edge = {
        "id": "feedback",
        "from": "n0",
        "to": "n13",
        "label": "rueckmeldung",
        "kind": "feedback",
    }
    raw["edges"] = [long_edge, feedback_edge]
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    nodes = _node_boxes(root)

    assert not _boxes_overlap(labels["long"], labels["feedback"])
    max_node_bottom = max(y + height for _, y, _, height in nodes.values())
    assert labels["feedback"][1] >= max_node_bottom + 10

    long_only = _minimal_process_model(14)
    long_only["edges"] = [copy.deepcopy(long_edge)]
    long_only_root = _parse(render_native_diagram(long_only))
    assert labels["long"] == _edge_label_boxes(long_only_root)["long"]


def test_parallel_narrative_relations_use_stable_outer_lanes() -> None:
    raw = _load("narrative-journey-v1.json")
    original = copy.deepcopy(next(edge for edge in raw["edges"] if edge["id"] == "journey01"))
    parallel = copy.deepcopy(original)
    parallel["id"] = "parallel_copy"
    parallel["label"] = "zweite parallele beziehung"
    remaining = [edge for edge in raw["edges"] if edge["id"] != "journey01"]

    def geometry(
        ordered: list[dict],
    ) -> tuple[dict[str, tuple[str, tuple[float, float, float, float]]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered + remaining)
        root = _parse(render_native_diagram(candidate))
        result = {}
        for edge in root.iter():
            edge_id = edge.attrib.get("data-source-id")
            if edge_id not in {"journey01", "parallel_copy"}:
                continue
            path = edge.find(f"{{{SVG_NAMESPACE}}}path")
            rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
            assert path is not None and rect is not None
            result[edge_id] = (path.attrib["d"], _rect_box(rect))
            assert edge.attrib["data-route"] == "narrative-parallel"
        return result, root

    forward, root = geometry([original, parallel])
    reverse, _ = geometry([parallel, original])
    assert forward == reverse
    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert not _boxes_overlap(boxes["journey01"], boxes["parallel_copy"])
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in boxes.values()
        for node_box in nodes.values()
    )
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    gutters = []
    for path, label_box in forward.values():
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
        ]
        gutter_x = max(x for x, _ in line_points)
        gutters.append(gutter_x)
        assert gutter_x > max_node_right
        canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
        x, y, width, height = label_box
        assert 0 <= x and x + width <= canvas_width
        assert 0 <= y and y + height <= canvas_height
    assert len(set(gutters)) == 2


def test_parallel_same_row_narrative_relations_use_row_gap_outer_lanes() -> None:
    raw = _load("narrative-journey-v1.json")
    raw["edges"] = [
        {
            "id": "same_a",
            "from": "question",
            "to": "tension",
            "label": "erste parallele beziehung",
            "kind": "flow",
        },
        {
            "id": "same_b",
            "from": "question",
            "to": "tension",
            "label": "zweite parallele beziehung",
            "kind": "flow",
        },
    ]
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    nodes = _node_boxes(root)
    assert not _boxes_overlap(labels["same_a"], labels["same_b"])
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in labels.values()
        for node_box in nodes.values()
    )

    row_bottom = nodes["question"][1] + nodes["question"][3]
    next_row_top = min(
        y
        for _, y, _, _ in nodes.values()
        if y > nodes["question"][1]
    )
    for edge_id in ("same_a", "same_b"):
        group = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == edge_id
        )
        path = group.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
        ]
        corridor_ys = {y for _, y in points[:-1]}
        assert len(corridor_ys) == 1
        corridor_y = next(iter(corridor_ys))
        assert row_bottom < corridor_y < next_row_top
