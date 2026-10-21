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
    _cubic_hull_intersects_box,
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


def _edge_paths(root: ET.Element) -> dict[str, str]:
    paths: dict[str, str] = {}
    for edge in root.iter():
        if edge.attrib.get("data-source-kind") != "edge":
            continue
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        paths[edge.attrib["data-source-id"]] = path.attrib["d"]
    return paths


def _cubic_path_intersects_box(
    path: str,
    box: tuple[float, float, float, float],
) -> bool:
    match = re.fullmatch(
        (
            r"M ([-0-9.]+) ([-0-9.]+) "
            r"C ([-0-9.]+) ([-0-9.]+), "
            r"([-0-9.]+) ([-0-9.]+), "
            r"([-0-9.]+) ([-0-9.]+)"
        ),
        path,
    )
    assert match is not None
    values = [float(value) for value in match.groups()]
    points = (
        (values[0], values[1]),
        (values[2], values[3]),
        (values[4], values[5]),
        (values[6], values[7]),
    )
    return _cubic_hull_intersects_box(points, box)


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

def test_narrative_groups_follow_their_content_height() -> None:
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


def test_process_same_column_feedback_uses_local_column_gutter() -> None:
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

    nodes = _node_boxes(root)
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in ("n0", "n12")
    )
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(line_points) == 3
    gutter_x = line_points[0][0]
    assert gutter_x == line_points[1][0]
    assert endpoint_right < gutter_x <= endpoint_right + 16
    assert gutter_x < max_node_right
    for corridor_y in (line_points[0][1], line_points[1][1]):
        assert all(
            not (y < corridor_y < y + height)
            for _, y, _, height in nodes.values()
        )

    label_box = _rect_box(label)
    assert all(not _boxes_overlap(label_box, box) for box in nodes.values())


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


def test_process_upper_row_reverse_feedback_uses_local_row_gap_lane() -> None:
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

    nodes = _node_boxes(root)
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in ("n0", "n1")
    )
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    first_row_bottom = min(y for _, y, _, _ in nodes.values()) + 166.0
    second_row_top = sorted({y for _, y, _, _ in nodes.values()})[1]
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(line_points) == 3
    gutter_x = line_points[0][0]
    assert gutter_x == line_points[1][0]
    assert endpoint_right < gutter_x <= endpoint_right + 16
    assert gutter_x < max_node_right
    corridor_y = line_points[0][1]
    assert first_row_bottom < corridor_y < second_row_top
    assert line_points[1][1] == corridor_y == line_points[2][1]

    label_box = _rect_box(label)
    _, ly, _, lh = label_box
    assert first_row_bottom < ly and ly + lh < second_row_top
    assert all(not _boxes_overlap(label_box, box) for box in nodes.values())


def test_process_feedback_return_stays_local_to_its_cycle_block() -> None:
    raw = _load("decision-flow-v1.json")
    raw["id"] = "konzeptentwicklung_kinder_jugendarbeit_feedback_regression"
    raw["title"] = "Konzeptentwicklung in der Kinder- und Jugendarbeit"
    raw["purpose"] = "Lernzyklus mit lokalen Vorwärtsbeziehungen und Rückkopplung."
    raw["groups"] = [
        {"id": "auftrag_rahmen", "label": "Auftrag und Rahmen"},
        {"id": "analyse_ziele", "label": "Analyse und Ziele"},
        {"id": "fachliche_ansaetze", "label": "Fachliche Ansätze"},
        {"id": "lernzyklus", "label": "Lern- und Entwicklungszyklus"},
        {"id": "qualitaet_verantwortung", "label": "Qualität und Verantwortung"},
    ]
    node_specs = [
        ("konzeptentwicklung", "Konzeptentwicklung", "concept", "auftrag_rahmen"),
        ("rechtlicher_auftrag", "Rechtlicher Auftrag", "concept", "auftrag_rahmen"),
        (
            "lebenswelt_bedarfsanalyse",
            "Lebenswelt- und Bedarfsanalyse",
            "evidence",
            "analyse_ziele",
        ),
        ("adressatenanalyse", "Adressatenanalyse", "evidence", "analyse_ziele"),
        ("sozialraumanalyse", "Sozialraumanalyse", "evidence", "analyse_ziele"),
        ("rahmenanalyse", "Rahmen analysieren", "evidence", "analyse_ziele"),
        (
            "sozialpaedagogische_haltung",
            "Sozialpädagogische Haltung",
            "concept",
            "fachliche_ansaetze",
        ),
        ("partizipation", "Partizipation", "concept", "fachliche_ansaetze"),
        ("fachliche_ausrichtung", "Fachliche Ausrichtung", "concept", "fachliche_ansaetze"),
        ("zielentwicklung", "Ziele entwickeln", "action", "fachliche_ansaetze"),
        ("planung", "Planung", "action", "lernzyklus"),
        ("umsetzung", "Umsetzung", "action", "lernzyklus"),
        ("reflexion", "Reflexion", "action", "lernzyklus"),
        ("revision", "Revision und Veränderung", "action", "lernzyklus"),
        ("qualitaetsimpuls", "Qualitätsimpuls", "evidence", "lernzyklus"),
        ("qualitaet", "Qualität sichern", "evidence", "qualitaet_verantwortung"),
        ("verantwortung", "Verantwortung", "concept", "qualitaet_verantwortung"),
        ("transfer", "Transfer", "action", "qualitaet_verantwortung"),
    ]
    raw["nodes"] = [
        {"id": node_id, "label": label, "kind": kind, "group": group}
        for node_id, label, kind, group in node_specs
    ]
    edge_specs = [
        ("e_konzept_analyse", "konzeptentwicklung", "rahmenanalyse", "liefert Analyse", "flow"),
        (
            "e_recht_lebenswelt",
            "rechtlicher_auftrag",
            "lebenswelt_bedarfsanalyse",
            "rahmt",
            "authority",
        ),
        ("e_konzept_adressaten", "konzeptentwicklung", "adressatenanalyse", "fokussiert", "flow"),
        ("e_recht_sozialraum", "rechtlicher_auftrag", "sozialraumanalyse", "begrenzt", "authority"),
        (
            "e_analyse_haltung",
            "lebenswelt_bedarfsanalyse",
            "sozialpaedagogische_haltung",
            "informiert",
            "evidence",
        ),
        (
            "e_adressaten_partizipation",
            "adressatenanalyse",
            "partizipation",
            "begründet",
            "evidence",
        ),
        (
            "e_sozialraum_ausrichtung",
            "sozialraumanalyse",
            "fachliche_ausrichtung",
            "orientiert",
            "evidence",
        ),
        ("e_rahmen_ziel", "rahmenanalyse", "zielentwicklung", "führt zu", "flow"),
        ("e_haltung_planung", "sozialpaedagogische_haltung", "planung", "prägt", "flow"),
        ("e_partizipation_planung", "partizipation", "planung", "beteiligt", "flow"),
        ("e_ausrichtung_planung", "fachliche_ausrichtung", "planung", "richtet aus", "flow"),
        ("e_ziel_planung", "zielentwicklung", "planung", "konkretisiert", "flow"),
        ("e_planung_umsetzung", "planung", "umsetzung", "führt zu", "flow"),
        ("e_umsetzung_reflexion", "umsetzung", "reflexion", "wird ausgewertet", "flow"),
        ("e_reflexion_revision", "reflexion", "revision", "führt zu", "flow"),
        ("e_reflexion_qualitaet", "reflexion", "qualitaetsimpuls", "liefert Evidenz", "evidence"),
        ("e_revision_qualitaet", "revision", "qualitaet", "sichert", "flow"),
        ("e_impuls_verantwortung", "qualitaetsimpuls", "verantwortung", "stärkt", "flow"),
        ("e_impuls_transfer", "qualitaetsimpuls", "transfer", "überführt", "flow"),
        ("e_revision_planung", "revision", "planung", "neue Planung", "feedback"),
    ]
    raw["edges"] = [
        {"id": edge_id, "from": source, "to": target, "label": label, "kind": kind}
        for edge_id, source, target, label, kind in edge_specs
    ]
    raw["requirements"] = {
        "formal_relations": True,
        "free_spatial_layout": False,
        "presentation": True,
    }
    raw["requested_formats"] = []

    first = render_native_diagram(raw)
    root = _parse(first)
    assert first == render_native_diagram(copy.deepcopy(raw))
    nodes = _node_boxes(root)
    assert len(nodes) == 18

    canvas_width = float(root.attrib["viewBox"].split()[2])
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    assert canvas_width <= max_node_right + 200

    for edge_id in ("e_konzept_analyse", "e_ausrichtung_planung", "e_ziel_planung"):
        edge = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == edge_id
        )
        assert edge.attrib["data-route"] == "process-branch"
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None and label is not None
        line_points = [
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
        ]
        assert line_points
        assert max(x for x, _ in line_points) < max_node_right
        assert all(
            not _boxes_overlap(_rect_box(label), node_box)
            for node_box in nodes.values()
        )

    revision_right = nodes["revision"][0] + nodes["revision"][2]
    later_group_left = nodes["qualitaet"][0]
    feedback = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "e_revision_planung"
    )
    assert feedback.attrib["data-route"] == "feedback-return"
    path = feedback.find(f"{{{SVG_NAMESPACE}}}path")
    label = feedback.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and label is not None
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert max(x for x, _ in line_points) <= revision_right + 32
    assert max(x for x, _ in line_points) < later_group_left
    feedback_box = _rect_box(label)
    assert all(
        not _boxes_overlap(feedback_box, node_box)
        for node_box in nodes.values()
    )
    max_node_bottom = max(y + height for _, y, _, height in nodes.values())
    assert feedback_box[1] + feedback_box[3] / 2 < max_node_bottom


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


def test_first_row_process_labels_pack_shared_header_rail() -> None:
    raw = _minimal_process_model(6)
    label = "abcdefghijklmnopqrstuv abcdefghijklmnopqrstuv"
    self_loop = {
        "id": "loop",
        "from": "n4",
        "to": "n4",
        "label": label,
        "kind": "flow",
    }
    same_row = {
        "id": "row",
        "from": "n5",
        "to": "n3",
        "label": label,
        "kind": "flow",
    }

    def geometry(ordered_edges: list[dict]) -> tuple[dict, dict, ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root

    # On c57c6a8 the combined model left both labels at these singleton boxes:
    # their 14.5 px horizontal overlap filled the entire 48 px label height.
    before_boxes = {
        "loop": (1921.5, 108.0, 198.0, 48.0),
        "row": (1738.0, 108.0, 198.0, 48.0),
    }
    assert _boxes_overlap(before_boxes["loop"], before_boxes["row"])
    singleton_loop, loop_paths, _ = geometry([self_loop])
    singleton_row, row_paths, singleton_root = geometry([same_row])
    assert singleton_loop == {"loop": before_boxes["loop"]}
    assert singleton_row == {"row": before_boxes["row"]}
    assert loop_paths["loop"] == (
        "M 1962.0 218.1 C 2040.0 174.1, 2040.0 323.5, 1962.0 279.5"
    )
    assert row_paths["row"] == (
        "M 2128.0 243.0 C 1883.6 215.0, 1790.4 215.0, 1546.0 243.0"
    )

    forward_boxes, forward_paths, root = geometry([self_loop, same_row])
    reverse_boxes, reverse_paths, reverse_root = geometry([same_row, self_loop])
    assert forward_boxes == reverse_boxes
    assert forward_paths == reverse_paths
    assert root.attrib["viewBox"] == reverse_root.attrib["viewBox"]
    assert forward_boxes["loop"] == singleton_loop["loop"]
    assert forward_paths["loop"] == loop_paths["loop"]
    assert all(box[2:] == (198.0, 48.0) for box in forward_boxes.values())
    assert not _boxes_overlap(forward_boxes["loop"], forward_boxes["row"])

    nodes = _node_boxes(root)
    assert len({y for _, y, _, _ in nodes.values()}) == 1
    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert canvas_width > float(singleton_root.attrib["viewBox"].split()[2])
    header_boxes = [
        _rect_box(rect)
        for clip_id in ("native-clip-title", "native-clip-purpose")
        for rect in root.findall(
            f".//{{{SVG_NAMESPACE}}}clipPath[@id='{clip_id}']/{{{SVG_NAMESPACE}}}rect"
        )
    ]
    assert len(header_boxes) == 2
    for label_box in forward_boxes.values():
        assert all(
            not _boxes_overlap(label_box, obstacle)
            for obstacle in [*nodes.values(), *header_boxes]
        )
        x, y, width, height = label_box
        assert 0 <= x < x + width <= canvas_width
        assert 0 <= y < y + height <= canvas_height


@pytest.mark.parametrize("edge_ids", (("loop",), ("row",), ("loop", "row")))
def test_uncrowded_first_row_process_labels_keep_geometry(edge_ids: tuple[str, ...]) -> None:
    raw = _minimal_process_model(6)
    edges = {
        "loop": {"id": "loop", "from": "n4", "to": "n4", "label": "x", "kind": "flow"},
        "row": {"id": "row", "from": "n5", "to": "n3", "label": "x", "kind": "flow"},
    }
    raw["edges"] = [edges[edge_id] for edge_id in edge_ids]
    root = _parse(render_native_diagram(raw))
    # These exact preimage boxes and paths cover both isolated first-row
    # occupants and a noncolliding pair, including the narrower one-line rail.
    expected_boxes = {
        "loop": (1996.5, 107.5, 48.0, 29.0),
        "row": (1813.0, 107.5, 48.0, 29.0),
    }
    expected_paths = {
        "loop": "M 1962.0 198.1 C 2040.0 154.1, 2040.0 303.5, 1962.0 259.5",
        "row": (
            "M 2128.0 223.0 C 1883.6 209.0, 1790.4 209.0, 1546.0 223.0"
            if len(edge_ids) == 2
            else "M 2128.0 223.0 C 1883.6 195.0, 1790.4 195.0, 1546.0 223.0"
        ),
    }
    assert _edge_label_boxes(root) == {edge_id: expected_boxes[edge_id] for edge_id in edge_ids}
    assert _edge_paths(root) == {edge_id: expected_paths[edge_id] for edge_id in edge_ids}
    assert root.attrib["viewBox"] == "0 0 2554 354"


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


def test_narrative_cjk_wrap_uses_legacy_narrative_width_metric() -> None:
    assert _estimated_wrap_width("漢" * 15, size=17) == pytest.approx(
        15 * 0.9 * 17
    )


def test_narrative_orphan_rebalance_uses_legacy_narrative_width_metric() -> None:
    assert _rebalance_single_word_lines(
        [
            "alpha beta ccccccccccccc",
            "dddddddddddd",
            "epsilon zeta",
        ],
        size=17,
        max_width=284.0,
    ) == [
        "alpha beta",
        "ccccccccccccc dddddddddddd",
        "epsilon zeta",
    ]


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



def test_process_feedback_avoids_packed_long_vertical_labels_without_global_footer() -> None:
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
    nodes = _node_boxes(root)
    feedback_box = labels["feedback"]
    verticals = [labels[f"vertical_{index}"] for index in range(4)]
    assert all(not _boxes_overlap(feedback_box, box) for box in verticals)
    assert all(not _boxes_overlap(feedback_box, box) for box in nodes.values())

    source_corridor_y = (nodes["n18"][1] + nodes["n18"][3] + nodes["n24"][1]) / 2
    assert feedback_box[1] + feedback_box[3] / 2 == source_corridor_y

    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "feedback"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    assert path is not None
    route_x = max(
        float(x)
        for x, _ in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    )
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in ("n29", "n0")
    )
    assert endpoint_right < route_x <= endpoint_right + 16


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


def _review_regression_model(
    intent: str,
    node_count: int,
    edges: list[tuple[int, int, str, str]],
    *,
    grouped: bool = False,
) -> dict:
    return {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "review_pr184",
        "title": "PR184 independent regression test",
        "purpose": "Relationship label boxes must not cover each other or node cards.",
        "intent": intent,
        "groups": (
            [{"id": "g0", "label": "A"}, {"id": "g1", "label": "B"}]
            if grouped
            else []
        ),
        "nodes": [
            {
                "id": f"n{index}",
                "label": f"Node {index}",
                "summary": "Review node.",
                "kind": "concept",
                "group": ("g0" if index < node_count // 2 else "g1") if grouped else None,
            }
            for index in range(node_count)
        ],
        "edges": [
            {
                "id": f"e{index}",
                "from": f"n{source}",
                "to": f"n{target}",
                "label": label,
                "kind": kind,
            }
            for index, (source, target, label, kind) in enumerate(edges)
        ],
        "requirements": {
            "formal_relations": True,
            "free_spatial_layout": True,
            "presentation": True,
            "collaboration": True,
            "rich_text": False,
            "structured_comparison": False,
            "portable_offline": True,
        },
        "requested_formats": ["canvas"],
    }


def test_long_parallel_narrative_labels_keep_allocated_outer_positions() -> None:
    raw = _review_regression_model(
        "narrative",
        6,
        [
            (0, 5, "First explanation of relationship", "flow"),
            (0, 5, "Second explanation of relationship", "association"),
        ],
        grouped=True,
    )
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)

    assert not _boxes_overlap(labels["e0"], labels["e1"])
    for edge_id in ("e0", "e1"):
        group = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == edge_id
        )
        assert group.attrib["data-route"] == "narrative-parallel"


def test_single_architecture_self_loop_label_box_clears_its_own_card() -> None:
    raw = _review_regression_model(
        "architecture",
        1,
        [(0, 0, "Relation label", "flow")],
    )
    root = _parse(render_native_diagram(raw))
    label = _edge_label_boxes(root)["e0"]
    node = _node_boxes(root)["n0"]

    assert not _boxes_overlap(label, node)


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


def test_grouped_crossing_two_line_process_labels_stay_inside_row_corridor() -> None:
    raw = _minimal_process_model(4)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 2 else "g1"
    raw["edges"] = [
        {
            "id": "cross_down",
            "from": "n0",
            "to": "n3",
            "label": "zweizeilige prozessbeziehung mit langem text",
            "kind": "flow",
        },
        {
            "id": "cross_up",
            "from": "n2",
            "to": "n1",
            "label": "zweizeilige gegenbeziehung mit langem text",
            "kind": "flow",
        },
    ]
    root = _parse(render_native_diagram(raw))
    nodes = _node_boxes(root)
    labels = _edge_label_boxes(root)
    upper_bottom = nodes["n0"][1] + nodes["n0"][3]
    lower_top = nodes["n1"][1]
    for edge_id in ("cross_down", "cross_up"):
        x, y, width, height = labels[edge_id]
        assert upper_bottom < y
        assert y + height < lower_top
        assert all(
            not _boxes_overlap((x, y, width, height), node_box)
            for node_box in nodes.values()
        )

    paths = _edge_paths(root)
    assert not _cubic_path_intersects_box(
        paths["cross_down"], labels["cross_up"]
    )
    assert not _cubic_path_intersects_box(
        paths["cross_up"], labels["cross_down"]
    )


def test_grouped_same_row_span_routes_around_intermediate_card() -> None:
    raw = _minimal_process_model(6)
    raw["groups"] = [
        {"id": "g0", "label": "G0"},
        {"id": "g1", "label": "G1"},
        {"id": "g2", "label": "G2"},
    ]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 2}"
    edges = [
        {
            "id": "span",
            "from": "n1",
            "to": "n5",
            "label": "lange gleiche zeile",
            "kind": "flow",
        },
        {
            "id": "vertical",
            "from": "n3",
            "to": "n2",
            "label": "x",
            "kind": "flow",
        },
    ]

    def geometry(ordered_edges: list[dict]) -> tuple[str, str, ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        edge = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == "span"
        )
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        return edge.attrib["data-route"], path.attrib["d"], root

    forward_route, forward_path, root = geometry(edges)
    reverse_route, reverse_path, _ = geometry(list(reversed(edges)))
    assert (forward_route, forward_path) == (reverse_route, reverse_path)
    assert forward_route == "process-row-gutter"
    nodes = _node_boxes(root)
    line_xs = [
        float(x)
        for x, _ in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", forward_path)
    ]
    assert max(line_xs) > max(x + width for x, _, width, _ in nodes.values())


def test_grouped_same_row_horizontal_pack_applies_packed_x_positions() -> None:
    raw = _minimal_process_model(4)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 2 else "g1"
    edges = [
        {
            "id": "wide",
            "from": "n0",
            "to": "n2",
            "label": "W" * 120,
            "kind": "flow",
        },
        {
            "id": "short",
            "from": "n2",
            "to": "n0",
            "label": "x",
            "kind": "flow",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], dict[str, str]]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    forward_labels, forward_paths = geometry(edges)
    reverse_labels, reverse_paths = geometry(list(reversed(edges)))
    assert forward_labels == reverse_labels
    assert forward_paths == reverse_paths
    assert not _boxes_overlap(forward_labels["wide"], forward_labels["short"])


def test_grouped_crossing_adjacent_relations_use_safe_local_lanes() -> None:
    raw = _minimal_process_model(4)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 2 else "g1"
    edges = [
        {
            "id": "cross_up",
            "from": "n1",
            "to": "n2",
            "label": "short relation",
            "kind": "flow",
        },
        {
            "id": "cross_down",
            "from": "n0",
            "to": "n3",
            "label": "x",
            "kind": "flow",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[
        dict[str, str],
        dict[str, tuple[float, float, float, float]],
        ET.Element,
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_paths(root), _edge_label_boxes(root), root

    forward_paths, forward_labels, root = geometry(edges)
    reverse_paths, reverse_labels, _ = geometry(list(reversed(edges)))
    assert forward_paths == reverse_paths
    assert forward_labels == reverse_labels
    assert " L " not in forward_paths["cross_up"]
    assert " L " not in forward_paths["cross_down"]
    assert not _cubic_path_intersects_box(
        forward_paths["cross_up"], forward_labels["cross_down"]
    )
    assert not _cubic_path_intersects_box(
        forward_paths["cross_down"], forward_labels["cross_up"]
    )

def test_grouped_packed_route_clears_anchored_long_branch_label() -> None:
    raw = _minimal_process_model(9)
    raw["groups"] = [
        {"id": f"g{index}", "label": f"Group {index}"}
        for index in range(3)
    ]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "anchor", "from": "n0", "to": "n5",
         "label": "lange lokale beziehung", "kind": "flow"},
        {"id": "reverse", "from": "n3", "to": "n1",
         "label": "kurz", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[
        dict[str, tuple[float, float, float, float]], dict[str, str]
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    path = paths["reverse"]
    if " L " not in path:
        assert not _cubic_path_intersects_box(path, labels["anchor"])
    else:
        # The safer outer-gutter fallback has cubic entry/exit connectors and
        # orthogonal L legs; check the full straight route, not only a cubic.
        match = re.search(
            r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
            r"([-0-9.]+) ([-0-9.]+) L ",
            path,
        )
        assert match is not None
        points = [tuple(float(v) for v in match.groups())]
        points.extend(
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
        )
        left, top, width, height = labels["anchor"]
        right, bottom = left + width, top + height
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            horizontal_overlap = (
                y1 == y2
                and top < y1 < bottom
                and max(min(x1, x2), left) < min(max(x1, x2), right)
            )
            vertical_overlap = (
                x1 == x2
                and left < x1 < right
                and max(min(y1, y2), top) < min(max(y1, y2), bottom)
            )
            assert not horizontal_overlap
            assert not vertical_overlap


def test_grouped_horizontal_packs_reserve_other_corridor_clusters() -> None:
    raw = _minimal_process_model(6)
    raw["groups"] = [
        {"id": f"g{index}", "label": f"Group {index}"}
        for index in range(3)
    ]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 2}"
    edges = [
        {"id": "left_forward", "from": "n0", "to": "n2",
         "label": "x", "kind": "flow"},
        {"id": "left_reverse", "from": "n2", "to": "n0",
         "label": "short", "kind": "flow"},
        {"id": "right_forward", "from": "n2", "to": "n4",
         "label": "lange prozessbeziehung mit zweitzeiligem text", "kind": "flow"},
        {"id": "right_reverse", "from": "n4", "to": "n2",
         "label": "x", "kind": "flow"},
    ]

    def labels_for(ordered: list[dict]) -> dict[
        str, tuple[float, float, float, float]
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        return _edge_label_boxes(_parse(render_native_diagram(candidate)))

    labels = labels_for(edges)
    assert labels == labels_for(list(reversed(edges)))
    for left in ("left_forward", "left_reverse"):
        for right in ("right_forward", "right_reverse"):
            assert not _boxes_overlap(labels[left], labels[right])


def test_parallel_group_long_branches_keep_outer_legs_clear_of_peer_labels() -> None:
    # A late label-pack demotion must not leave one local label underneath the
    # source corridor of its parallel peer's outer branch.
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 3 else "g1"
    edges = [
        {"id": "parallel_a", "from": "n0", "to": "n5",
         "label": "erster Weg", "kind": "flow"},
        {"id": "parallel_b", "from": "n0", "to": "n5",
         "label": "zweiter Weg", "kind": "flow"},
    ]

    def geometry(ordered_edges: list[dict]) -> tuple[
        dict[str, tuple[float, float, float, float]], dict[str, str]
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    for edge_id, path in paths.items():
        peer = "parallel_b" if edge_id == "parallel_a" else "parallel_a"
        match = re.search(
            r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
            r"([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+)",
            path,
        )
        assert match is not None
        start_x, start_y, end_x, end_y = map(float, match.groups())
        left, top, width, height = labels[peer]
        assert not (
            start_y == end_y
            and top < start_y < top + height
            and max(min(start_x, end_x), left)
            < min(max(start_x, end_x), left + width)
        )


def test_local_long_branch_label_clears_other_outer_branch_source_path() -> None:
    raw = _minimal_process_model(9)
    raw["groups"] = [
        {"id": f"g{index}", "label": f"Group {index}"}
        for index in range(3)
    ]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "local", "from": "n0", "to": "n5",
         "label": "short branch", "kind": "flow"},
        {"id": "outer", "from": "n0", "to": "n8",
         "label": "outer branch", "kind": "flow"},
    ]

    def geometry(ordered_edges: list[dict]) -> tuple[
        tuple[float, float, float, float], str
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root)["local"], _edge_paths(root)["outer"]

    box, outer_path = geometry(edges)
    assert (box, outer_path) == geometry(list(reversed(edges)))
    match = re.search(
        r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
        r"([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+)",
        outer_path,
    )
    assert match is not None
    start_x, start_y, end_x, end_y = map(float, match.groups())
    left, top, width, height = box
    assert not (
        start_y == end_y
        and top < start_y < top + height
        and max(min(start_x, end_x), left)
        < min(max(start_x, end_x), left + width)
    )


def test_local_group_long_branch_rejects_gutter_when_label_cannot_fit() -> None:
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 3 else "g1"
    raw["edges"] = [
        {
            "id": "long",
            "from": "n0",
            "to": "n5",
            "label": "W" * 120,
            "kind": "flow",
        }
    ]
    root = _parse(render_native_diagram(raw))
    nodes = _node_boxes(root)
    label = _edge_label_boxes(root)["long"]
    assert all(not _boxes_overlap(label, node_box) for node_box in nodes.values())
    path = _edge_paths(root)["long"]
    path_xs = [
        float(x)
        for x, _ in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
    ]
    assert max(path_xs) > max(x + width for x, _, width, _ in nodes.values())




def test_local_group_long_branch_clears_target_corridor_label() -> None:
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 3 else "g1"
    edges = [
        {
            "id": "long",
            "from": "n0",
            "to": "n5",
            "label": "lange lokale beziehung",
            "kind": "flow",
        },
        {
            "id": "short",
            "from": "n1",
            "to": "n5",
            "label": "kurze zielbeziehung im korridor",
            "kind": "flow",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, str], dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_paths(root), _edge_label_boxes(root), root

    forward_paths, forward_labels, root = geometry(edges)
    reverse_paths, reverse_labels, _ = geometry(list(reversed(edges)))
    assert forward_paths == reverse_paths
    assert forward_labels == reverse_labels

    nodes = _node_boxes(root)
    for label_box in forward_labels.values():
        assert all(
            not _boxes_overlap(label_box, node_box)
            for node_box in nodes.values()
        )
    assert not _boxes_overlap(forward_labels["long"], forward_labels["short"])

    short_left, short_top, short_width, short_height = forward_labels["short"]
    short_right = short_left + short_width
    short_bottom = short_top + short_height
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(
            r"L ([-0-9.]+) ([-0-9.]+)",
            forward_paths["long"],
        )
    ]
    for (x1, y1), (x2, y2) in zip(line_points, line_points[1:]):
        horizontal_hit = (
            y1 == y2
            and short_top < y1 < short_bottom
            and max(min(x1, x2), short_left) < min(max(x1, x2), short_right)
        )
        vertical_hit = (
            x1 == x2
            and short_left < x1 < short_right
            and max(min(y1, y2), short_top) < min(max(y1, y2), short_bottom)
        )
        assert not horizontal_hit
        assert not vertical_hit


def test_opposite_direction_adjacent_process_edges_use_stable_label_lanes() -> None:
    raw = _minimal_process_model(12)
    edges = [
        {
            "id": "down",
            "from": "n1",
            "to": "n6",
            "label": "abwärts",
            "kind": "flow",
        },
        {
            "id": "up",
            "from": "n6",
            "to": "n1",
            "label": "aufwärts",
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
            assert edge.attrib["data-route"] == "process-branch"
        return result, root

    forward, root = geometry(edges)
    reverse, _ = geometry(list(reversed(edges)))
    assert forward == reverse
    boxes = {edge_id: box for edge_id, (_, box) in forward.items()}
    assert not _boxes_overlap(boxes["down"], boxes["up"])
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in boxes.values()
        for node_box in nodes.values()
    )
    upper_bottom = min(nodes["n1"][1], nodes["n6"][1]) + nodes["n1"][3]
    lower_top = max(nodes["n1"][1], nodes["n6"][1])
    assert all(
        upper_bottom <= y and y + height <= lower_top
        for _, y, _, height in boxes.values()
    )


def test_narrative_self_loop_uses_stable_outer_row_gap_lane() -> None:
    raw = _load("narrative-journey-v1.json")
    loop = {
        "id": "loop",
        "from": "question",
        "to": "question",
        "label": "mehrstufige reflexive beziehung",
        "kind": "flow",
    }
    companion = copy.deepcopy(next(edge for edge in raw["edges"] if edge["id"] == "journey02"))

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[str, tuple[float, float, float, float], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        group = next(
            element
            for element in root.iter()
            if element.attrib.get("data-source-id") == "loop"
        )
        path = group.find(f"{{{SVG_NAMESPACE}}}path")
        rect = group.find(f"{{{SVG_NAMESPACE}}}rect")
        assert path is not None and rect is not None
        assert group.attrib["data-route"] == "narrative-self-loop"
        return path.attrib["d"], _rect_box(rect), root

    forward_path, forward_box, root = geometry([loop, companion])
    reverse_path, reverse_box, _ = geometry([companion, loop])
    assert (forward_path, forward_box) == (reverse_path, reverse_box)
    nodes = _node_boxes(root)
    assert all(not _boxes_overlap(forward_box, node_box) for node_box in nodes.values())
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    x, y, width, height = forward_box
    assert x > max_node_right
    line_points = [
        (float(px), float(py))
        for px, py in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", forward_path)
    ]
    assert len(line_points) == 4
    corridor_y = line_points[0][1]
    assert all(py == corridor_y for _, py in line_points[:-1])
    assert max(px for px, _ in line_points) > max_node_right
    source_bottom = nodes["question"][1] + nodes["question"][3]
    next_row_top = min(
        node_y
        for _, node_y, _, _ in nodes.values()
        if node_y > nodes["question"][1]
    )
    assert source_bottom < corridor_y < next_row_top
    canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
    assert 0 <= x and x + width <= canvas_width
    assert 0 <= y and y + height <= canvas_height


def test_adjacent_vertical_and_diagonal_non_process_labels_pack_same_row_corridor() -> None:
    raw = _minimal_process_model(6)
    raw["intent"] = "architecture"
    raw["id"] = "architecture_6"
    edges = [
        {
            "id": "vertical",
            "from": "n1",
            "to": "n5",
            "label": "vertikale beziehung im korridor",
            "kind": "flow",
        },
        {
            "id": "diagonal",
            "from": "n2",
            "to": "n4",
            "label": "diagonale beziehung im korridor",
            "kind": "risk",
        },
    ]

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        labels = _edge_label_boxes(root)
        return {edge["id"]: labels[edge["id"]] for edge in edges}, root

    forward, root = boxes(edges)
    reverse, _ = boxes(list(reversed(edges)))
    assert forward == reverse
    assert not _boxes_overlap(forward["vertical"], forward["diagonal"])
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in forward.values()
        for node_box in nodes.values()
    )
    upper_bottom = nodes["n1"][1] + nodes["n1"][3]
    lower_top = nodes["n5"][1]
    assert all(
        upper_bottom <= y and y + height <= lower_top
        for _, y, _, height in forward.values()
    )


def test_process_feedback_self_loop_avoids_occupied_adjacent_branch_corridor() -> None:
    raw = _minimal_process_model(7)
    feedback = {
        "id": "feedback",
        "from": "n0",
        "to": "n0",
        "label": "rückmeldung",
        "kind": "feedback",
    }
    branch = {
        "id": "branch",
        "from": "n5",
        "to": "n6",
        "label": "zweizeilige prozessbeziehung mit langem text",
        "kind": "flow",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        labels = _edge_label_boxes(root)
        return {edge_id: labels[edge_id] for edge_id in ("feedback", "branch")}, root

    forward, root = boxes([feedback, branch])
    reverse, _ = boxes([branch, feedback])
    assert forward == reverse
    assert not _boxes_overlap(forward["feedback"], forward["branch"])
    nodes = _node_boxes(root)
    max_node_bottom = max(y + height for _, y, _, height in nodes.values())
    assert forward["feedback"][1] >= max_node_bottom + 10

    branch_only = copy.deepcopy(raw)
    branch_only["edges"] = [copy.deepcopy(branch)]
    assert forward["branch"] == _edge_label_boxes(
        _parse(render_native_diagram(branch_only))
    )["branch"]


def test_process_feedback_non_self_loop_avoids_occupied_adjacent_branch_corridor() -> None:
    raw = _minimal_process_model(7)
    feedback = {
        "id": "feedback_non_self",
        "from": "n6",
        "to": "n5",
        "label": "rückmeldung",
        "kind": "feedback",
    }
    branch = {
        "id": "branch",
        "from": "n5",
        "to": "n6",
        "label": "zweizeilige prozessbeziehung mit langem text",
        "kind": "flow",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        labels = _edge_label_boxes(root)
        return {edge_id: labels[edge_id] for edge_id in ("feedback_non_self", "branch")}, root

    forward, root = boxes([feedback, branch])
    reverse, _ = boxes([branch, feedback])
    assert forward == reverse
    assert not _boxes_overlap(forward["feedback_non_self"], forward["branch"])
    nodes = _node_boxes(root)
    max_node_bottom = max(y + height for _, y, _, height in nodes.values())
    assert forward["feedback_non_self"][1] >= max_node_bottom + 10


def test_grouped_feedback_path_uses_safe_lane_when_corridor_label_is_crossed() -> None:
    raw = _minimal_process_model(4)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 2 else "g1"
    raw["edges"] = [
        {
            "id": "feedback",
            "from": "n2",
            "to": "n0",
            "label": "rückmeldung",
            "kind": "feedback",
        },
        {
            "id": "branch",
            "from": "n2",
            "to": "n1",
            "label": "x",
            "kind": "flow",
        },
    ]
    first = _parse(render_native_diagram(raw))
    raw["edges"].reverse()
    second = _parse(render_native_diagram(raw))
    assert _edge_label_boxes(first) == _edge_label_boxes(second)
    assert _edge_paths(first) == _edge_paths(second)

    labels = _edge_label_boxes(first)
    paths = _edge_paths(first)
    nodes = _node_boxes(first)
    feedback_box = labels["feedback"]
    branch_box = labels["branch"]
    assert not _boxes_overlap(feedback_box, branch_box)
    assert feedback_box[1] > max(y + height for _, y, _, height in nodes.values())

    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", paths["feedback"])
    ]
    branch_left, branch_top, branch_width, branch_height = branch_box
    branch_right = branch_left + branch_width
    branch_bottom = branch_top + branch_height
    for (x1, y1), (x2, y2) in zip(line_points, line_points[1:]):
        if y1 != y2 or not (branch_top < y1 < branch_bottom):
            continue
        assert max(min(x1, x2), branch_left) >= min(
            max(x1, x2), branch_right
        )



def test_ungrouped_process_feedback_channel_clears_unrelated_flow_label() -> None:
    raw = _minimal_process_model(18)
    edges = [
        {
            "id": "branch",
            "from": "n6",
            "to": "n7",
            "label": "Nebenprozess mit Titel",
            "kind": "flow",
        },
        {
            "id": "feedback",
            "from": "n12",
            "to": "n0",
            "label": "Rueckmeldung",
            "kind": "feedback",
        },
    ]

    def render(ordered_edges: list[dict]) -> tuple[tuple[float, float, float, float], str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root)["branch"], _edge_paths(root)["feedback"]

    label_box, feedback_path = render(edges)
    assert (label_box, feedback_path) == render(list(reversed(edges)))

    left, top, width, height = label_box
    right = left + width
    bottom = top + height
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", feedback_path)
    ]
    assert len(line_points) >= 3
    for (x1, y1), (x2, y2) in zip(line_points, line_points[1:]):
        if x1 != x2:
            continue
        assert not (
            left - 2 < x1 < right + 2
            and max(min(y1, y2), top - 2) < min(max(y1, y2), bottom + 2)
        )


def test_ungrouped_feedback_full_horizontal_route_clears_other_labels() -> None:
    # Moving only the vertical gutter can route the source leg through a
    # different, two-line corridor label that was never a vertical obstacle.
    raw = _minimal_process_model(18)
    edges = [
        {"id": "short", "from": "n6", "to": "n7",
         "label": "Nebenprozess mit Titel", "kind": "flow"},
        {"id": "tall", "from": "n13", "to": "n14",
         "label": "zweizeilige prozessbeziehung mit langem text", "kind": "flow"},
        {"id": "feedback", "from": "n12", "to": "n0",
         "label": "Rueckmeldung", "kind": "feedback"},
    ]

    def geometry(ordered: list[dict]) -> tuple[
        dict[str, tuple[float, float, float, float]], str
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)["feedback"]

    labels, path = geometry(edges)
    assert (labels, path) == geometry(list(reversed(edges)))
    initial = re.search(
        r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
        r"([-0-9.]+) ([-0-9.]+) L ",
        path,
    )
    assert initial is not None
    points = [tuple(map(float, initial.groups()))]
    points.extend(
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
    )
    for edge_id in ("short", "tall"):
        left, top, width, height = labels[edge_id]
        right, bottom = left + width, top + height
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            horizontal_hit = (
                y1 == y2
                and top < y1 < bottom
                and max(min(x1, x2), left) < min(max(x1, x2), right)
            )
            vertical_hit = (
                x1 == x2
                and left < x1 < right
                and max(min(y1, y2), top) < min(max(y1, y2), bottom)
            )
            assert not horizontal_hit
            assert not vertical_hit


def test_feedback_label_avoids_long_same_column_return_leg() -> None:
    # The existing label-only occupancy test misses an already routed edge.
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = "g0" if index < 3 else "g1"
    edges = [
        {"id": "long", "from": "n0", "to": "n2",
         "label": "langer pfad", "kind": "flow"},
        {"id": "feedback", "from": "n2", "to": "n1",
         "label": "rückmeldung", "kind": "feedback"},
    ]

    def geometry(ordered: list[dict]) -> tuple[
        tuple[float, float, float, float], str
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root)["feedback"], _edge_paths(root)["long"]

    box, path = geometry(edges)
    assert (box, path) == geometry(list(reversed(edges)))
    match = re.match(r"M ([-0-9.]+) ([-0-9.]+) L ", path)
    assert match is not None
    points = [tuple(map(float, match.groups()))]
    points.extend(
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
    )
    left, top, width, height = box
    right, bottom = left + width, top + height
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        assert not (
            y1 == y2
            and top < y1 < bottom
            and max(min(x1, x2), left) < min(max(x1, x2), right)
        )


def test_ungrouped_process_feedback_uses_actual_row_gap() -> None:
    raw = _minimal_process_model(7)
    raw["edges"] = [
        {
            "id": "feedback",
            "from": "n6",
            "to": "n5",
            "label": "rückmeldung",
            "kind": "feedback",
        }
    ]
    root = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(root)
    nodes = _node_boxes(root)
    _, label_top, _, label_height = labels["feedback"]
    physical_gap_center = (nodes["n5"][1] + nodes["n5"][3] + nodes["n6"][1]) / 2
    assert label_top + label_height / 2 == physical_gap_center


def test_ungrouped_forward_same_row_process_feedback_uses_actual_row_gap() -> None:
    raw = _minimal_process_model(14)
    feedback = {
        "id": "feedback",
        "from": "n0",
        "to": "n1",
        "label": "rückmeldung",
        "kind": "feedback",
    }
    geometry, root = _feedback_geometry(raw, [feedback])
    repeated, _ = _feedback_geometry(copy.deepcopy(raw), [copy.deepcopy(feedback)])
    assert geometry == repeated

    nodes = _node_boxes(root)
    source_bottom = nodes["n0"][1] + nodes["n0"][3]
    physical_gap_center = (source_bottom + nodes["n6"][1]) / 2
    path, label_box = geometry["feedback"]
    assert source_bottom == 306.0
    assert physical_gap_center == 341.0
    assert label_box[1] + label_box[3] / 2 == physical_gap_center
    assert all(not _boxes_overlap(label_box, node_box) for node_box in nodes.values())

    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
    ]
    route_x = max(x for x, _ in line_points)
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in ("n0", "n1")
    )
    max_node_right = max(x + width for x, _, width, _ in nodes.values())
    assert endpoint_right < route_x <= endpoint_right + 16
    assert route_x < max_node_right


def test_distant_singleton_long_branch_preserves_forward_same_row_feedback() -> None:
    raw = _minimal_process_model(14)
    feedback = {
        "id": "feedback",
        "from": "n0",
        "to": "n1",
        "label": "rückmeldung",
        "kind": "feedback",
    }
    long_branch = {
        "id": "long_branch",
        "from": "n12",
        "to": "n1",
        "label": "lange diagonale prozessbeziehung mit text",
        "kind": "flow",
    }
    solo, _ = _feedback_geometry(raw, [feedback])
    combined, root = _feedback_geometry(raw, [feedback, long_branch])
    reordered, _ = _feedback_geometry(raw, [long_branch, feedback])

    assert combined["feedback"] == solo["feedback"]
    assert combined == reordered
    assert not _boxes_overlap(combined["feedback"][1], combined["long_branch"][1])

    nodes = _node_boxes(root)
    feedback_path, feedback_box = solo["feedback"]
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", feedback_path)
    ]
    route_x = max(x for x, _ in line_points)
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in ("n0", "n1")
    )
    assert endpoint_right < route_x <= endpoint_right + 16
    assert all(
        not _boxes_overlap(label_box, node_box)
        for _, label_box in combined.values()
        for node_box in nodes.values()
    )


@pytest.mark.parametrize("pack_target", ("n12", "n13"), ids=("long_vertical", "long_branch"))
@pytest.mark.parametrize("feedback_source", ("n24", "n29"), ids=("left_source", "right_source"))
def test_process_feedback_packed_label_bounds_respect_local_x_separation(
    pack_target: str, feedback_source: str
) -> None:
    raw = _minimal_process_model(30)
    packed_edges = [
        {
            "id": f"packed_{index}",
            "from": "n24",
            "to": pack_target,
            "label": f"lange vertikale Beziehung {index}",
            "kind": "evidence",
        }
        for index in range(4)
    ]
    feedback = {
        "id": "feedback",
        "from": feedback_source,
        "to": "n0",
        "label": "Rückmeldung zum Anfang",
        "kind": "feedback",
    }
    edges = [*packed_edges, feedback]
    geometry, root = _feedback_geometry(raw, edges)
    reordered, _ = _feedback_geometry(raw, list(reversed(edges)))
    assert geometry == reordered

    feedback_path, feedback_box = geometry["feedback"]
    packed_boxes = [geometry[edge["id"]][1] for edge in packed_edges]
    nodes = _node_boxes(root)
    assert all(not _boxes_overlap(feedback_box, box) for box in packed_boxes)
    assert all(not _boxes_overlap(feedback_box, box) for box in nodes.values())

    source_corridor_y = (nodes["n18"][1] + nodes["n18"][3] + nodes["n24"][1]) / 2
    assert feedback_box[1] + feedback_box[3] / 2 == source_corridor_y == 1049.0
    # Packed labels may share the same y range. Their x-separation now keeps the
    # local feedback lane usable instead of forcing an unrelated global footer.
    assert any(
        feedback_box[1] < y + height and feedback_box[1] + feedback_box[3] > y
        for _, y, _, height in packed_boxes
    )

    route_x = max(
        float(x)
        for x, _ in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", feedback_path)
    )
    endpoint_right = max(
        nodes[node_id][0] + nodes[node_id][2] for node_id in (feedback_source, "n0")
    )
    assert endpoint_right < route_x <= endpoint_right + 16


def test_long_vertical_and_adjacent_non_process_labels_pack_same_row_corridor() -> None:
    raw = _minimal_process_model(10)
    raw["intent"] = "architecture"
    raw["id"] = "long_adjacent_corridor"
    long_vertical = {
        "id": "long_vertical",
        "from": "n0",
        "to": "n8",
        "label": "lange vertikale relation im gemeinsamen korridor",
        "kind": "flow",
    }
    adjacent_diagonal = {
        "id": "adjacent_diagonal",
        "from": "n0",
        "to": "n5",
        "label": "diagonale relation im gemeinsamen korridor",
        "kind": "risk",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        labels = _edge_label_boxes(root)
        return {
            edge_id: labels[edge_id]
            for edge_id in ("long_vertical", "adjacent_diagonal")
        }, root

    forward, root = boxes([long_vertical, adjacent_diagonal])
    reverse, _ = boxes([adjacent_diagonal, long_vertical])
    assert forward == reverse
    assert not _boxes_overlap(forward["long_vertical"], forward["adjacent_diagonal"])
    nodes = _node_boxes(root)
    for label_box in forward.values():
        assert all(not _boxes_overlap(label_box, node_box) for node_box in nodes.values())

    long_only = copy.deepcopy(raw)
    long_only["edges"] = [copy.deepcopy(long_vertical)]
    assert forward["long_vertical"] == _edge_label_boxes(
        _parse(render_native_diagram(long_only))
    )["long_vertical"]


def test_crossing_adjacent_process_branches_pack_shared_physical_corridor() -> None:
    raw = _minimal_process_model(14)
    first = {
        "id": "cross_a",
        "from": "n12",
        "to": "n7",
        "label": "erste kreuzende prozessbeziehung mit langem text",
        "kind": "flow",
    }
    second = {
        "id": "cross_b",
        "from": "n6",
        "to": "n13",
        "label": "zweite kreuzende prozessbeziehung mit langem text",
        "kind": "risk",
    }

    def boxes(ordered_edges: list[dict]) -> dict[str, tuple[float, float, float, float]]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        return _edge_label_boxes(_parse(render_native_diagram(candidate)))

    forward = boxes([first, second])
    reverse = boxes([second, first])
    assert forward == reverse
    assert not _boxes_overlap(forward["cross_a"], forward["cross_b"])


def test_same_row_process_label_packs_with_adjacent_vertical_corridor() -> None:
    raw = _minimal_process_model(12)
    same_row = {
        "id": "same_row",
        "from": "n7",
        "to": "n11",
        "label": "gleiche zeile mit ausreichend langem zweizeiligen label",
        "kind": "flow",
    }
    adjacent_vertical = {
        "id": "adj_vertical",
        "from": "n3",
        "to": "n9",
        "label": "vertikale relation mit ausreichend langem zweizeiligen label",
        "kind": "risk",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([same_row, adjacent_vertical])
    reverse, _ = boxes([adjacent_vertical, same_row])
    assert forward == reverse
    assert not _boxes_overlap(forward["same_row"], forward["adj_vertical"])
    nodes = _node_boxes(root)
    for edge_id in ("same_row", "adj_vertical"):
        assert all(
            not _boxes_overlap(forward[edge_id], node_box)
            for node_box in nodes.values()
        )


def test_forward_same_row_process_feedback_avoids_occupied_corridor() -> None:
    raw = _minimal_process_model(10)
    feedback = {
        "id": "feedback_fwd",
        "from": "n0",
        "to": "n1",
        "label": "rückmeldung",
        "kind": "feedback",
    }
    adjacent_vertical = {
        "id": "adj_vertical",
        "from": "n9",
        "to": "n3",
        "label": "vertikale relation mit langem text",
        "kind": "flow",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([feedback, adjacent_vertical])
    reverse, _ = boxes([adjacent_vertical, feedback])
    assert forward == reverse
    assert not _boxes_overlap(forward["feedback_fwd"], forward["adj_vertical"])
    nodes = _node_boxes(root)
    max_node_bottom = max(y + height for _, y, _, height in nodes.values())
    assert forward["feedback_fwd"][1] >= max_node_bottom + 10


def test_long_vertical_process_label_packs_with_same_row_corridor() -> None:
    raw = _minimal_process_model(18)
    long_vertical = {
        "id": "long_vertical",
        "from": "n0",
        "to": "n12",
        "label": "lange vertikale prozessrelation mit langem text",
        "kind": "flow",
    }
    same_row = {
        "id": "same_row",
        "from": "n6",
        "to": "n7",
        "label": "gleiche zeile",
        "kind": "risk",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([long_vertical, same_row])
    reverse, _ = boxes([same_row, long_vertical])
    assert forward == reverse
    assert not _boxes_overlap(forward["long_vertical"], forward["same_row"])
    nodes = _node_boxes(root)
    for edge_id in ("long_vertical", "same_row"):
        assert all(
            not _boxes_overlap(forward[edge_id], node_box)
            for node_box in nodes.values()
        )

    # The long vertical relation is anchored on its source row corridor, so the
    # same-row label yields instead of displacing the accepted singleton box.
    singleton, _ = boxes([long_vertical])
    assert singleton["long_vertical"] == forward["long_vertical"]


def test_long_diagonal_non_process_label_packs_shared_row_corridor() -> None:
    raw = _minimal_process_model(16)
    raw["intent"] = "architecture"
    raw["id"] = "long_diagonal_corridor"
    long_diagonal = {
        "id": "long_diagonal",
        "from": "n0",
        "to": "n13",
        "label": "lange diagonale relation",
        "kind": "flow",
    }
    adjacent_diagonal = {
        "id": "adjacent_diagonal",
        "from": "n4",
        "to": "n9",
        "label": "kurze diagonale relation",
        "kind": "risk",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([long_diagonal, adjacent_diagonal])
    reverse, _ = boxes([adjacent_diagonal, long_diagonal])
    assert forward == reverse
    assert not _boxes_overlap(forward["long_diagonal"], forward["adjacent_diagonal"])
    nodes = _node_boxes(root)
    for edge_id in ("long_diagonal", "adjacent_diagonal"):
        assert all(
            not _boxes_overlap(forward[edge_id], node_box)
            for node_box in nodes.values()
        )

    # Packing keeps both labels in the shared corridor and only shifts the
    # id-stable later one sideways; the earlier label keeps its accepted box.
    singleton_long, _ = boxes([long_diagonal])
    singleton_adjacent, _ = boxes([adjacent_diagonal])
    assert singleton_adjacent["adjacent_diagonal"] == forward["adjacent_diagonal"]
    assert singleton_long["long_diagonal"][1:] == forward["long_diagonal"][1:]
    assert singleton_long["long_diagonal"][0] < forward["long_diagonal"][0]


def test_crowded_process_row_gutter_lanes_clear_two_line_self_loop() -> None:
    raw = _minimal_process_model(12)
    crowded = "sehr lange prozessbeziehung mit erklaerendem text"
    first_row_edge = {
        "id": "row_a",
        "from": "n6",
        "to": "n9",
        "label": crowded,
        "kind": "flow",
    }
    second_row_edge = {
        "id": "row_b",
        "from": "n7",
        "to": "n8",
        "label": crowded,
        "kind": "risk",
    }
    self_loop = {
        "id": "loop",
        "from": "n11",
        "to": "n11",
        "label": "zweizeiliger selbstbezug der karte",
        "kind": "flow",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([first_row_edge, second_row_edge, self_loop])
    reverse, reverse_root = boxes([self_loop, second_row_edge, first_row_edge])
    # The outer-gutter allocation is derived from bounds, not from list order,
    # and the self-loop arc keeps its own card-scoped lane.
    for edge_id in ("row_a", "row_b", "loop"):
        assert forward[edge_id] == reverse[edge_id]
    assert forward["row_a"][3] > 29  # the crowded labels really do wrap
    assert forward["loop"][3] > 29
    for labels, tree in ((forward, root), (reverse, reverse_root)):
        for edge_id in ("row_a", "row_b"):
            assert not _boxes_overlap(labels["loop"], labels[edge_id])
        nodes = _node_boxes(tree)
        for edge_id in ("row_a", "row_b", "loop"):
            assert all(
                not _boxes_overlap(labels[edge_id], node_box)
                for node_box in nodes.values()
            )


def test_long_vertical_process_edge_yields_corridor_to_self_loop_label() -> None:
    raw = _minimal_process_model(24)
    long_vertical = {
        "id": "long_vertical",
        "from": "n0",
        "to": "n12",
        "label": "eine mittellange beziehung",
        "kind": "flow",
    }
    self_loop = {
        "id": "self_loop",
        "from": "n6",
        "to": "n6",
        "label": "zweizeiliger selbstbezug der karte",
        "kind": "risk",
    }

    def boxes(
        ordered_edges: list[dict],
    ) -> tuple[dict[str, tuple[float, float, float, float]], ET.Element]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), root

    forward, root = boxes([long_vertical, self_loop])
    reverse, reverse_root = boxes([self_loop, long_vertical])
    # The self-loop owns the same-row slot of that column corridor, so the long
    # same-column relation takes the shared outer lane regardless of list order.
    assert forward["long_vertical"] == reverse["long_vertical"]
    singleton, _ = boxes([long_vertical])
    assert singleton["long_vertical"][0] < forward["long_vertical"][0]
    for labels, tree in ((forward, root), (reverse, reverse_root)):
        assert not _boxes_overlap(labels["long_vertical"], labels["self_loop"])
        nodes = _node_boxes(tree)
        for edge_id in ("long_vertical", "self_loop"):
            assert all(
                not _boxes_overlap(labels[edge_id], node_box)
                for node_box in nodes.values()
            )


def test_crowded_process_self_loop_geometry_is_independent_of_relation_order() -> None:
    raw = _minimal_process_model(12)
    crowded = "sehr lange prozessbeziehung mit erklaerendem text"
    first_row_edge = {
        "id": "row_a",
        "from": "n9",
        "to": "n10",
        "label": crowded,
        "kind": "flow",
    }
    second_row_edge = {
        "id": "row_b",
        "from": "n11",
        "to": "n8",
        "label": crowded,
        "kind": "risk",
    }
    self_loop = {
        "id": "loop",
        "from": "n11",
        "to": "n11",
        "label": "zweizeiliger selbstbezug der karte",
        "kind": "flow",
    }

    def rendered(
        ordered_edges: list[dict],
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, str],
        ET.Element,
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root

    forward_boxes, forward_paths, root = rendered(
        [first_row_edge, second_row_edge, self_loop]
    )
    reverse_boxes, reverse_paths, reverse_root = rendered(
        [self_loop, second_row_edge, first_row_edge]
    )

    # A self-loop arc expresses its lane through its reach, so the relation
    # list order must not decide where the loop or its label lands.
    for edge_id in ("row_a", "row_b", "loop"):
        assert forward_boxes[edge_id] == reverse_boxes[edge_id]
        assert forward_paths[edge_id] == reverse_paths[edge_id]

    assert forward_boxes["row_a"][3] > 29  # the crowded labels really do wrap
    assert forward_boxes["loop"][3] > 29
    for labels, tree in ((forward_boxes, root), (reverse_boxes, reverse_root)):
        nodes = _node_boxes(tree)
        for edge_id in ("row_a", "row_b", "loop"):
            assert all(
                not _boxes_overlap(labels[edge_id], node_box)
                for node_box in nodes.values()
            )
        for first, second in (("loop", "row_a"), ("loop", "row_b"), ("row_a", "row_b")):
            assert not _boxes_overlap(labels[first], labels[second])


def test_stacked_process_self_loops_keep_distinct_stable_arcs() -> None:
    raw = _minimal_process_model(6)
    loops = [
        {
            "id": f"loop_{suffix}",
            "from": "n3",
            "to": "n3",
            "label": f"selbstbezug {suffix}",
            "kind": "flow",
        }
        for suffix in ("a", "b", "c", "d")
    ]

    def paths(ordered_edges: list[dict]) -> dict[str, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        return _edge_paths(_parse(render_native_diagram(candidate)))

    forward = paths(loops)
    reverse = paths(list(reversed(loops)))
    assert forward == reverse
    # Loops on one card stay apart instead of collapsing onto a shared arc.
    assert len(set(forward.values())) == len(loops)


def test_long_diagonal_and_vertical_non_process_geometry_is_edge_order_independent() -> None:
    raw = _minimal_process_model(14)
    raw["intent"] = "architecture"
    raw["id"] = "architecture_14"
    edges = [
        {
            "id": "diag",
            "from": "n9",
            "to": "n1",
            "label": "lange diagonale beziehung",
            "kind": "flow",
        },
        {
            "id": "vertical",
            "from": "n12",
            "to": "n2",
            "label": "lange vertikale beziehung",
            "kind": "risk",
        },
    ]

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, str],
        ET.Element,
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root

    forward_boxes, forward_paths, root = geometry(edges)
    reverse_boxes, reverse_paths, _ = geometry(list(reversed(edges)))

    # The generic Bezier route carries its lane in the control points, so a
    # permuted relation list must not move the curve, only the label box.
    assert forward_boxes == reverse_boxes
    assert forward_paths == reverse_paths

    # The accepted geometry of both relations is preserved.
    assert forward_paths["diag"] == (
        "M 535.0 612.0 L 535.0 577.0 L 672.0 577.0 "
        "L 672.0 341.0 L 535.0 341.0 L 535.0 306.0"
    )
    assert forward_paths["vertical"] == (
        "M 298.0 931.0 C 497.1 923.0, 572.9 215.0, 772.0 223.0"
    )

    assert not _boxes_overlap(forward_boxes["diag"], forward_boxes["vertical"])
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in forward_boxes.values()
        for node_box in nodes.values()
    )


def test_long_process_branch_occupies_its_source_corridor_against_adjacent_branch() -> None:
    raw = _minimal_process_model(14)
    long_branch = {
        "id": "long_branch",
        "from": "n12",
        "to": "n1",
        "label": "lange diagonale prozessbeziehung mit text",
        "kind": "flow",
    }
    adjacent = {
        "id": "adjacent",
        "from": "n13",
        "to": "n11",
        "label": "benachbarte prozessbeziehung mit langem text",
        "kind": "risk",
    }

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, str],
        ET.Element,
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root

    forward_boxes, forward_paths, root = geometry([long_branch, adjacent])
    reverse_boxes, reverse_paths, _ = geometry([adjacent, long_branch])

    assert forward_boxes == reverse_boxes
    assert forward_paths == reverse_paths

    # Both labels really do wrap, which is what made them collide before the
    # long branch was registered as a physical corridor occupant.
    assert forward_boxes["long_branch"][3] > 29
    assert forward_boxes["adjacent"][3] > 29
    assert not _boxes_overlap(
        forward_boxes["long_branch"], forward_boxes["adjacent"]
    )
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in forward_boxes.values()
        for node_box in nodes.values()
    )

    # An unaffected singleton long branch keeps its accepted geometry.
    solo_boxes, solo_paths, _ = geometry([long_branch])
    assert solo_boxes["long_branch"] == (1252.5, 553.0, 182.0, 48.0)
    assert solo_paths["long_branch"] == (
        "M 173.0 612.0 C 173.0 594.0, 173.0 577.0, 173.0 577.0 "
        "L 2514.0 577.0 L 2514.0 341.0 L 589.0 341.0 "
        "C 589.0 341.0, 589.0 324.0, 589.0 306.0"
    )


def test_process_feedback_yields_to_anchored_self_loop_corridor() -> None:
    raw = _minimal_process_model(12)
    self_loop = {
        "id": "self_loop",
        "from": "n8",
        "to": "n8",
        "label": "zweizeilige selbstbeziehung mit langem text",
        "kind": "flow",
    }
    feedback = {
        "id": "feedback",
        "from": "n0",
        "to": "n9",
        "label": "rueckmeldung mit langem text",
        "kind": "feedback",
    }

    def geometry(
        ordered_edges: list[dict],
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, str],
        ET.Element,
    ]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered_edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root

    forward_boxes, forward_paths, root = geometry([self_loop, feedback])
    reverse_boxes, reverse_paths, _ = geometry([feedback, self_loop])

    assert forward_boxes == reverse_boxes
    assert forward_paths == reverse_paths

    assert forward_boxes["self_loop"][3] > 29
    assert not _boxes_overlap(forward_boxes["self_loop"], forward_boxes["feedback"])
    nodes = _node_boxes(root)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in forward_boxes.values()
        for node_box in nodes.values()
    )
    # The feedback label leaves the corridor the anchored loop owns and lands
    # in the reserved footer below the complete card field.
    assert forward_boxes["feedback"][1] > max(
        y + height for _, y, _, height in nodes.values()
    )

    # Without the anchored corridor user, the feedback relation stays local to
    # its own endpoints and uses the ordinary row gap.
    solo_boxes, solo_paths, solo_root = geometry([feedback])
    solo_nodes = _node_boxes(solo_root)
    solo_box = solo_boxes["feedback"]
    assert all(not _boxes_overlap(solo_box, box) for box in solo_nodes.values())

    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", solo_paths["feedback"])
    ]
    route_x = max(x for x, _ in line_points)
    endpoint_right = max(
        solo_nodes[node_id][0] + solo_nodes[node_id][2] for node_id in ("n0", "n9")
    )
    assert endpoint_right < route_x <= endpoint_right + 16


def _anchored_process_labels_model() -> dict:
    raw = _minimal_process_model(18)
    label = "abcdefghijklmnopqrstuv abcdefghijklmnopqrstuv"
    raw["edges"] = [
        {"id": "diag", "from": "n0", "to": "n15", "label": label, "kind": "flow"},
        {"id": "vert", "from": "n3", "to": "n15", "label": label, "kind": "risk"},
    ]
    return raw


@pytest.mark.parametrize("edge_ids", [("diag", "vert"), ("z_diagonal", "a_vertical")])
def test_colliding_anchored_process_labels_use_stable_outer_lanes(
    edge_ids: tuple[str, str],
) -> None:
    raw = _anchored_process_labels_model()
    for edge, edge_id in zip(raw["edges"], edge_ids):
        edge["id"] = edge_id
    forward = _parse(render_native_diagram(raw))
    raw["edges"].reverse()
    reverse = _parse(render_native_diagram(raw))
    labels = _edge_label_boxes(forward)
    paths = _edge_paths(forward)

    assert labels == _edge_label_boxes(reverse)
    assert paths == _edge_paths(reverse)
    assert forward.attrib["viewBox"] == reverse.attrib["viewBox"]
    for root in (forward, reverse):
        assert {
            edge.attrib["data-source-id"]: edge.attrib["data-route"]
            for edge in root.iter()
            if edge.attrib.get("data-source-kind") == "edge"
        } == {edge_ids[0]: "process-branch", edge_ids[1]: "vertical"}

    # On 9e753b4 these 198x48 boxes started at x=1244.5 and x=1390.5,
    # both at y=317, so the two opaque labels overlapped by 52 px.
    assert {box[2:] for box in labels.values()} == {(198.0, 48.0)}
    assert not _boxes_overlap(labels[edge_ids[0]], labels[edge_ids[1]])
    nodes = _node_boxes(forward)
    assert all(
        not _boxes_overlap(label_box, node_box)
        for label_box in labels.values()
        for node_box in nodes.values()
    )
    _, _, canvas_width, canvas_height = map(float, forward.attrib["viewBox"].split())
    assert all(
        0 <= x and 0 <= y and x + width <= canvas_width and y + height <= canvas_height
        for x, y, width, height in labels.values()
    )

    # Keep the fixed-column anchor exactly; the canvas-relative diagonal takes
    # an outer lane regardless of either input order or relation-id priority.
    assert labels[edge_ids[1]] == (1390.5, 317.0, 198.0, 48.0)
    assert paths[edge_ids[1]] == (
        "M 1421.0 306.0 L 1421.0 341.0 L 1558.0 341.0 "
        "L 1558.0 577.0 L 1421.0 577.0 L 1421.0 612.0"
    )
    assert labels[edge_ids[0]][0] > max(x + width for x, _, width, _ in nodes.values())


@pytest.mark.parametrize("edge_id", ["diag", "vert"])
def test_singleton_anchored_process_label_keeps_preimage_geometry(edge_id: str) -> None:
    raw = _anchored_process_labels_model()
    raw["edges"] = [edge for edge in raw["edges"] if edge["id"] == edge_id]
    root = _parse(render_native_diagram(raw))
    expected_boxes = {
        "diag": (1244.5, 317.0, 198.0, 48.0),
        "vert": (1390.5, 317.0, 198.0, 48.0),
    }
    expected_paths = {
        "diag": (
            "M 173.0 306.0 C 173.0 324.0, 173.0 341.0, 173.0 341.0 "
            "L 2514.0 341.0 L 2514.0 577.0 L 1421.0 577.0 "
            "C 1421.0 577.0, 1421.0 594.0, 1421.0 612.0"
        ),
        "vert": (
            "M 1421.0 306.0 L 1421.0 341.0 L 1558.0 341.0 "
            "L 1558.0 577.0 L 1421.0 577.0 L 1421.0 612.0"
        ),
    }
    assert _edge_label_boxes(root) == {edge_id: expected_boxes[edge_id]}
    assert _edge_paths(root) == {edge_id: expected_paths[edge_id]}
    assert root.attrib["viewBox"] == "0 0 2554 826"


@pytest.mark.parametrize("close_pair", [False, True])
def test_nonoverlapping_anchored_process_labels_keep_preimage_geometry(close_pair: bool) -> None:
    raw = _anchored_process_labels_model()
    if close_pair:
        # A 4 px gap puts both anchors in the same packing cluster without an
        # actual overlap. The usual 8 px packing clearance must not move them.
        for edge in raw["edges"]:
            edge["label"] = "abcdefghijklmno"
        expected_boxes = {
            "diag": (1272.5, 326.5, 142.0, 29.0),
            "vert": (1418.5, 326.5, 142.0, 29.0),
        }
        center_x, gutter_x = "1421.0", "1558.0"
    else:
        raw["edges"][1].update({"from": "n2", "to": "n14"})
        expected_boxes = {
            "diag": (1244.5, 317.0, 198.0, 48.0),
            "vert": (974.5, 317.0, 198.0, 48.0),
        }
        center_x, gutter_x = "1005.0", "1142.0"
    expected_paths = {
        "diag": (
            "M 173.0 306.0 C 173.0 324.0, 173.0 341.0, 173.0 341.0 "
            "L 2514.0 341.0 L 2514.0 577.0 L 1421.0 577.0 "
            "C 1421.0 577.0, 1421.0 594.0, 1421.0 612.0"
        ),
        "vert": (
            f"M {center_x} 306.0 L {center_x} 341.0 L {gutter_x} 341.0 "
            f"L {gutter_x} 577.0 L {center_x} 577.0 L {center_x} 612.0"
        ),
    }
    for edges in (raw["edges"], list(reversed(raw["edges"]))):
        raw["edges"] = edges
        root = _parse(render_native_diagram(raw))
        assert _edge_label_boxes(root) == expected_boxes
        assert _edge_paths(root) == expected_paths
        assert root.attrib["viewBox"] == "0 0 2554 826"
    assert not _boxes_overlap(expected_boxes["diag"], expected_boxes["vert"])


def _rightmost_singleton_branch_model() -> dict:
    raw = _minimal_process_model(18)
    label = "abcdefghijklmnopqrstuvw abcdefghijklmnopqrstuvw"
    raw["edges"] = [
        {"id": "branch", "from": "n5", "to": "n13", "label": label, "kind": "flow"},
        {"id": "vertical", "from": "n11", "to": "n5", "label": label, "kind": "risk"},
    ]
    return raw


def _assert_process_pair_labels_are_safe_and_semantically_stable(raw: dict) -> ET.Element:
    forward = _parse(render_native_diagram(raw))

    def geometry(model: dict, root: ET.Element) -> dict:
        labels, paths = _edge_label_boxes(root), _edge_paths(root)
        return {
            (edge["from"], edge["to"], edge["kind"], edge["label"]): (
                labels[edge["id"]], paths[edge["id"]]
            )
            for edge in model["edges"]
        }

    expected = geometry(raw, forward)
    for reverse, swap_ids in ((False, False), (True, False), (False, True), (True, True)):
        candidate = copy.deepcopy(raw)
        if swap_ids:
            first, second = candidate["edges"]
            first["id"], second["id"] = second["id"], first["id"]
        if reverse:
            candidate["edges"].reverse()
        root = _parse(render_native_diagram(candidate))
        assert geometry(candidate, root) == expected
        assert root.attrib["viewBox"] == forward.attrib["viewBox"]
        assert _node_boxes(root) == _node_boxes(forward)
        labels = list(_edge_label_boxes(root).values())
        assert len(labels) == 2
        assert not _boxes_overlap(*labels)
        header_boxes = [
            _rect_box(rect)
            for clip_id in ("native-clip-title", "native-clip-purpose")
            for rect in root.findall(
                f".//{{{SVG_NAMESPACE}}}clipPath[@id='{clip_id}']/{{{SVG_NAMESPACE}}}rect"
            )
        ]
        assert all(
            not _boxes_overlap(label, obstacle)
            for label in labels
            for obstacle in [*_node_boxes(root).values(), *header_boxes]
        )
        canvas_width, canvas_height = map(float, root.attrib["viewBox"].split()[2:])
        assert all(
            0 <= x < x + width <= canvas_width and 0 <= y < y + height <= canvas_height
            for x, y, width, height in labels
        )
    return forward


def test_singleton_branch_anchor_survives_adjacent_vertical_canvas_growth() -> None:
    raw = _rightmost_singleton_branch_model()
    # On 7c9b41e these 206x48 boxes began at x=2396.5 and x=2526,
    # both at y=317: growing the canvas moved the anchor into a 76.5 px overlap.
    root = _assert_process_pair_labels_are_safe_and_semantically_stable(raw)
    solo = copy.deepcopy(raw)
    solo["edges"] = solo["edges"][:1]
    singleton = _parse(render_native_diagram(solo))
    assert _edge_label_boxes(root)["branch"] == _edge_label_boxes(singleton)["branch"]
    assert _edge_paths(root)["branch"] == _edge_paths(singleton)["branch"]
    assert float(root.attrib["viewBox"].split()[2]) > float(
        singleton.attrib["viewBox"].split()[2]
    )


@pytest.mark.parametrize("edge_id", ["branch", "vertical"])
def test_rightmost_branch_corridor_singletons_keep_preimage_geometry(edge_id: str) -> None:
    raw = _rightmost_singleton_branch_model()
    raw["edges"] = [edge for edge in raw["edges"] if edge["id"] == edge_id]
    root = _parse(render_native_diagram(raw))
    expected_boxes = {
        "branch": (2280.5, 317.0, 206.0, 48.0),
        "vertical": (2150.0, 317.0, 206.0, 48.0),
    }
    expected_paths = {
        "branch": (
            "M 2253.0 306.0 C 2253.0 324.0, 2253.0 341.0, 2253.0 341.0 "
            "L 2514.0 341.0 L 2514.0 577.0 L 589.0 577.0 "
            "C 589.0 577.0, 589.0 594.0, 589.0 612.0"
        ),
        "vertical": "M 2253.0 376.0 C 2253.0 346.6, 2253.0 335.4, 2253.0 306.0",
    }
    assert _edge_label_boxes(root) == {edge_id: expected_boxes[edge_id]}
    assert _edge_paths(root) == {edge_id: expected_paths[edge_id]}
    assert root.attrib["viewBox"] == "0 0 2554 826"


def test_noncolliding_rightmost_branch_corridor_keeps_preimage_geometry() -> None:
    raw = _rightmost_singleton_branch_model()
    for edge in raw["edges"]:
        edge["label"] = "x"
    root = _assert_process_pair_labels_are_safe_and_semantically_stable(raw)
    assert _edge_label_boxes(root) == {
        "branch": (2359.5, 326.5, 48.0, 29.0),
        "vertical": (2229.0, 326.5, 48.0, 29.0),
    }
    assert _edge_paths(root) == {
        "branch": (
            "M 2253.0 306.0 C 2253.0 324.0, 2253.0 341.0, 2253.0 341.0 "
            "L 2514.0 341.0 L 2514.0 577.0 L 589.0 577.0 "
            "C 589.0 577.0, 589.0 594.0, 589.0 612.0"
        ),
        "vertical": "M 2253.0 376.0 C 2253.0 346.6, 2253.0 335.4, 2253.0 306.0",
    }
    assert root.attrib["viewBox"] == "0 0 2554 826"


def test_uncontested_singleton_branch_keeps_geometry_when_another_corridor_grows() -> None:
    raw = _rightmost_singleton_branch_model()
    label = raw["edges"][0]["label"]
    raw["edges"] = raw["edges"][:1] + [
        {"id": "row_a", "from": "n6", "to": "n13", "label": label, "kind": "flow"},
        {"id": "row_b", "from": "n7", "to": "n12", "label": label, "kind": "risk"},
    ]
    solo = copy.deepcopy(raw)
    solo["edges"] = solo["edges"][:1]
    singleton = _parse(render_native_diagram(solo))
    for edges in (raw["edges"], list(reversed(raw["edges"]))):
        raw["edges"] = edges
        root = _parse(render_native_diagram(raw))
        # Unrelated outer-lane packing may grow the final canvas, but it must
        # not redefine the canvas-relative singleton branch anchor afterwards.
        assert _edge_label_boxes(root)["branch"] == _edge_label_boxes(singleton)["branch"]
        assert _edge_paths(root)["branch"] == _edge_paths(singleton)["branch"]
        assert root.attrib["viewBox"] == "0 0 3018 826"


def test_singleton_branch_anchor_is_frozen_before_unrelated_outer_lane_growth() -> None:
    label = "abcdefghijklmnopqrstuvwx abcdefghijklmnopqrstuvwx"
    id_variants = (
        {"branch": "branch", "adjacent": "adjacent", "row": "row"},
        {"branch": "z_branch", "adjacent": "a_adjacent", "row": "m_row"},
    )
    expected_semantic_geometry = None
    expected_view_box = None

    for ids in id_variants:
        raw = _minimal_process_model(13)
        raw["edges"] = [
            {"id": ids["branch"], "from": "n5", "to": "n12", "label": label, "kind": "flow"},
            {"id": ids["adjacent"], "from": "n11", "to": "n3", "label": label, "kind": "risk"},
            {"id": ids["row"], "from": "n11", "to": "n10", "label": label, "kind": "flow"},
        ]
        role_by_id = {edge_id: role for role, edge_id in ids.items()}
        solo = copy.deepcopy(raw)
        solo["edges"] = solo["edges"][:1]
        singleton = _parse(render_native_diagram(solo))
        singleton_box = _edge_label_boxes(singleton)[ids["branch"]]
        singleton_path = _edge_paths(singleton)[ids["branch"]]
        variant_geometry = None
        variant_view_box = None

        for ordered in (raw["edges"], list(reversed(raw["edges"]))):
            candidate = copy.deepcopy(raw)
            candidate["edges"] = copy.deepcopy(ordered)
            root = _parse(render_native_diagram(candidate))
            boxes = _edge_label_boxes(root)
            paths = _edge_paths(root)
            semantic_geometry = {
                role_by_id[edge["id"]]: (boxes[edge["id"]], paths[edge["id"]])
                for edge in candidate["edges"]
            }
            if variant_geometry is None:
                variant_geometry = semantic_geometry
                variant_view_box = root.attrib["viewBox"]
            else:
                assert semantic_geometry == variant_geometry
                assert root.attrib["viewBox"] == variant_view_box

            branch_box = boxes[ids["branch"]]
            assert branch_box[0] == singleton_box[0]
            assert branch_box[2:] == singleton_box[2:]
            assert "L 2514.0" in paths[ids["branch"]]
            assert "L 2514.0" in singleton_path
            assert float(root.attrib["viewBox"].split()[2]) > float(
                singleton.attrib["viewBox"].split()[2]
            )
            pairs = (
                (ids["branch"], ids["adjacent"]),
                (ids["branch"], ids["row"]),
                (ids["adjacent"], ids["row"]),
            )
            assert all(not _boxes_overlap(boxes[first], boxes[second]) for first, second in pairs)
            nodes = _node_boxes(root)
            assert all(
                not _boxes_overlap(label_box, node_box)
                for label_box in boxes.values()
                for node_box in nodes.values()
            )

        if expected_semantic_geometry is None:
            expected_semantic_geometry = variant_geometry
            expected_view_box = variant_view_box
        else:
            assert variant_geometry == expected_semantic_geometry
            assert variant_view_box == expected_view_box


def _two_process_self_loops_model(node_count: int = 1) -> dict:
    raw = _minimal_process_model(node_count)
    node_id = f"n{node_count - 1}"
    raw["edges"] = [
        {
            "id": f"loop_{suffix}",
            "from": node_id,
            "to": node_id,
            "label": label,
            "kind": "flow",
        }
        for suffix, label in (
            ("a", "erster selbstbezug mit langem text"),
            ("b", "zweizeiliger selbstbezug der karte"),
        )
    ]
    return raw


@pytest.mark.parametrize("node_count", [1, 12])
def test_two_process_self_loop_labels_pack_without_changing_arc_lanes(node_count: int) -> None:
    raw = _two_process_self_loops_model(node_count)
    # The minimal one-node model on 7c9b41e put 198x48 and 212x48 labels
    # at (257.5, 108) and (261, 108): centres only 10.5 px apart.
    root = _assert_process_pair_labels_are_safe_and_semantically_stable(raw)
    assert {box[2:] for box in _edge_label_boxes(root).values()} == {
        (198.0, 48.0), (212.0, 48.0)
    }
    solo = copy.deepcopy(raw)
    solo["edges"] = solo["edges"][:1]
    singleton = _parse(render_native_diagram(solo))
    assert _edge_label_boxes(root)["loop_a"] == _edge_label_boxes(singleton)["loop_a"]
    assert _edge_paths(root)["loop_a"] == _edge_paths(singleton)["loop_a"]
    assert len(set(_edge_paths(root).values())) == 2
    if node_count == 1:
        assert _edge_paths(root) == {
            "loop_a": "M 298.0 218.1 C 376.0 174.1, 376.0 323.5, 298.0 279.5",
            "loop_b": "M 298.0 218.1 C 390.0 174.1, 390.0 323.5, 298.0 279.5",
        }


@pytest.mark.parametrize("edge_id", ["loop_a", "loop_b"])
def test_two_process_self_loop_singletons_keep_exact_preimage_geometry(edge_id: str) -> None:
    raw = _two_process_self_loops_model()
    raw["edges"] = [edge for edge in raw["edges"] if edge["id"] == edge_id]
    root = _parse(render_native_diagram(raw))
    expected_boxes = {
        "loop_a": (257.5, 108.0, 198.0, 48.0),
        "loop_b": (250.5, 108.0, 212.0, 48.0),
    }
    assert _edge_label_boxes(root) == {edge_id: expected_boxes[edge_id]}
    assert _edge_paths(root) == {
        edge_id: "M 298.0 218.1 C 376.0 174.1, 376.0 323.5, 298.0 279.5"
    }
    assert root.attrib["viewBox"] == "0 0 1028 374"


@pytest.mark.parametrize("label", ["", "   "])
def test_empty_process_edge_label_is_rejected_before_label_metrics(label: str) -> None:
    raw = _minimal_process_model(2)
    raw["edges"] = [
        {
            "id": "edge_a",
            "from": "n0",
            "to": "n1",
            "label": label,
            "kind": "flow",
        }
    ]
    with pytest.raises(RepresentationError, match=r"edges\[0\]\.label must not be empty"):
        render_native_diagram(raw)


@pytest.mark.parametrize("edge_id", ["edge space", "edge#fragment", "edge/slash"])
def test_svg_fragment_source_id_must_use_representation_safe_id(edge_id: str) -> None:
    raw = _minimal_process_model(2)
    raw["edges"] = [
        {
            "id": edge_id,
            "from": "n0",
            "to": "n1",
            "label": "sichere beziehung",
            "kind": "flow",
        }
    ]
    with pytest.raises(RepresentationError, match=r"edges\[0\]\.id must match"):
        render_native_diagram(raw)



def test_process_long_branch_labels_clear_existing_outer_lanes() -> None:
    raw = _load("decision-flow-v1.json")
    raw["id"] = "pr184_outer_long_regression"
    raw["title"] = "Outer and long branch regression"
    raw["purpose"] = "Keep independently allocated process labels out of each other's lanes."
    raw["intent"] = "process"
    raw["groups"] = []
    raw["nodes"] = [
        {
            "id": f"n{index}",
            "label": f"Node {index}",
            "kind": "action",
            "group": None,
            "summary": "Regression node",
        }
        for index in range(20)
    ]
    label = (
        "Diese Verbindung beschreibt einen bewusst langen Prozessschritt "
        "zwischen weit entfernten Knoten im Diagramm"
    )
    raw["edges"] = [
        {"id": "a0", "from": "n6", "to": "n13", "label": label, "kind": "flow"},
        {"id": "a1", "from": "n7", "to": "n12", "label": label, "kind": "flow"},
        {"id": "z0", "from": "n0", "to": "n19", "label": label, "kind": "flow"},
        {"id": "z1", "from": "n1", "to": "n18", "label": label, "kind": "flow"},
    ]

    root = _parse(render_native_diagram(raw))
    boxes = _edge_label_boxes(root)
    for outer_id in ("a0", "a1"):
        for long_id in ("z0", "z1"):
            assert not _boxes_overlap(boxes[outer_id], boxes[long_id])

    reversed_raw = copy.deepcopy(raw)
    reversed_raw["edges"].reverse()
    reversed_root = _parse(render_native_diagram(reversed_raw))
    assert boxes == _edge_label_boxes(reversed_root)
    assert _edge_paths(root) == _edge_paths(reversed_root)


def test_generic_non_process_self_loop_label_stays_inside_canvas() -> None:
    raw = _load("system-landscape-v1.json")
    raw["id"] = "pr184_self_loop_canvas_regression"
    raw["title"] = "Generic self-loop canvas regression"
    raw["purpose"] = "Keep a rightmost non-process self-loop label inside the SVG viewBox."
    raw["intent"] = "architecture"
    raw["groups"] = []
    raw["nodes"] = [
        {
            "id": f"n{index}",
            "label": f"Node {index}",
            "kind": "system",
            "group": None,
            "summary": "Regression node",
        }
        for index in range(4)
    ]
    raw["edges"] = [
        {
            "id": "loop",
            "from": "n3",
            "to": "n3",
            "label": "Breite Beziehung zur rechten Diagrammkante mit mehreren Worten",
            "kind": "flow",
        }
    ]

    svg = render_native_diagram(raw)
    root = _parse(svg)
    label_box = _edge_label_boxes(root)["loop"]
    source_box = _node_boxes(root)["n3"]
    _, _, canvas_width, _ = (float(value) for value in root.attrib["viewBox"].split())
    x, _, width, _ = label_box

    assert x >= 0
    assert x + width <= canvas_width
    assert not _boxes_overlap(label_box, source_box)
    assert svg == render_native_diagram(copy.deepcopy(raw))



def test_generic_non_process_self_loop_routes_clear_of_next_card() -> None:
    raw = _load("system-landscape-v1.json")
    raw["id"] = "generic_self_loop_neighbor_regression"
    raw["title"] = "Generic self loop neighbor regression"
    raw["purpose"] = "Keep a generic self-loop label clear of the next card."
    raw["intent"] = "state"
    raw["groups"] = []
    raw["nodes"] = [
        {
            "id": f"n{index}",
            "label": f"Node {index}",
            "kind": "system",
            "group": None,
            "summary": "Regression node",
        }
        for index in range(6)
    ]
    raw["edges"] = [
        {
            "id": "loop",
            "from": "n3",
            "to": "n3",
            "label": "Breite Beziehung zur nächsten Karte mit mehreren Worten",
            "kind": "flow",
        }
    ]

    svg = render_native_diagram(raw)
    root = _parse(svg)
    label_box = _edge_label_boxes(root)["loop"]
    node_boxes = _node_boxes(root)
    _, _, canvas_width, canvas_height = (
        float(value) for value in root.attrib["viewBox"].split()
    )
    x, y, width, height = label_box
    edge_group = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
        and element.attrib.get("data-source-id") == "loop"
    )

    assert edge_group.attrib["data-route"] == "generic-self-loop"
    assert not _boxes_overlap(label_box, node_boxes["n3"])
    assert not _boxes_overlap(label_box, node_boxes["n4"])
    assert all(not _boxes_overlap(label_box, box) for box in node_boxes.values())
    assert 0 <= x and x + width <= canvas_width
    assert 0 <= y and y + height <= canvas_height
    assert svg == render_native_diagram(copy.deepcopy(raw))

def test_grouped_pack_reserves_later_singleton_label_other_cluster() -> None:
    """P2: a later one-edge cluster must not overprint an earlier packed box."""
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "packed", "from": "n5", "to": "n2", "label": "short relation", "kind": "flow"},
        {"id": "long", "from": "n2", "to": "n0", "label": "lange lokale beziehung", "kind": "flow"},
        {"id": "singleton", "from": "n4", "to": "n5", "label": "x", "kind": "flow"},
    ]
    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)
    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    assert not _boxes_overlap(labels["packed"], labels["singleton"])


def test_grouped_pack_reserves_anchored_label_in_foreign_cluster() -> None:
    """P2: every anchored corridor occupant must reserve its actual label box."""
    raw = _minimal_process_model(8)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 4}"
    edges = [
        {"id": "forward", "from": "n7", "to": "n3", "label": "x", "kind": "flow"},
        {"id": "reverse", "from": "n3", "to": "n7", "label": "x", "kind": "flow"},
        {"id": "anchored", "from": "n3", "to": "n1", "label": "short relation", "kind": "flow"},
    ]
    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)
    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    assert not _boxes_overlap(labels["reverse"], labels["anchored"])


def test_local_group_long_branch_target_leg_clears_other_corridor_label() -> None:
    """P2: the full local L-route must clear even unrelated target labels."""
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "long", "from": "n0", "to": "n5", "label": "x", "kind": "flow"},
        {"id": "short", "from": "n2", "to": "n4", "label": "x", "kind": "flow"},
    ]
    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)
    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    left, top, width, height = labels["short"]
    right, bottom = left + width, top + height
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", paths["long"])
    ]
    assert len(line_points) >= 3
    for (x1, y1), (x2, y2) in zip(line_points, line_points[1:]):
        horizontal_hit = (
            y1 == y2 and top < y1 < bottom
            and max(min(x1, x2), left) < min(max(x1, x2), right)
        )
        vertical_hit = (
            x1 == x2 and left < x1 < right
            and max(min(y1, y2), top) < min(max(y1, y2), bottom)
        )
        assert not horizontal_hit and not vertical_hit


def test_grouped_cross_row_feedback_target_leg_clears_foreign_flow_label() -> None:
    """P2: moving feedback text to footer must not ignore a crossed target leg."""
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "feedback", "from": "n5", "to": "n0",
         "label": "return to start", "kind": "feedback"},
        {"id": "flow", "from": "n3", "to": "n1",
         "label": "short relation", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    left, top, width, height = labels["flow"]
    right, bottom = left + width, top + height
    linear_points = [
        (float(x), float(y))
        for x, y in re.findall(
            r"L ([-0-9.]+) ([-0-9.]+)", paths["feedback"]
        )
    ]
    assert len(linear_points) >= 3
    for (x1, y1), (x2, y2) in zip(linear_points, linear_points[1:]):
        horizontal_hit = (
            y1 == y2 and top < y1 < bottom
            and max(min(x1, x2), left) < min(max(x1, x2), right)
        )
        vertical_hit = (
            x1 == x2 and left < x1 < right
            and max(min(y1, y2), top) < min(max(y1, y2), bottom)
        )
        assert not horizontal_hit and not vertical_hit


@pytest.mark.parametrize(
    ("return_from", "return_to", "peer_from", "peer_to"),
    [
        ("n1", "n4", "n4", "n5"),  # Same-row forward return crosses the peer label
        ("n4", "n5", "n5", "n0"),  # Vertical return gutter crosses the peer label
    ],
)
def test_grouped_feedback_entire_footer_route_clears_peer_label(
    return_from: str,
    return_to: str,
    peer_from: str,
    peer_to: str,
) -> None:
    """P2: footer labels never license source, target or vertical path overlap."""
    raw = _minimal_process_model(6)
    raw["groups"] = [{"id": "g0", "label": "G0"}, {"id": "g1", "label": "G1"}]
    for index, node in enumerate(raw["nodes"]):
        node["group"] = f"g{index // 3}"
    edges = [
        {"id": "feedback", "from": return_from, "to": return_to,
         "label": "return to start", "kind": "feedback"},
        {"id": "peer", "from": peer_from, "to": peer_to,
         "label": "short relation", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(model))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    left, top, width, height = labels["peer"]
    right, bottom = left + width, top + height
    points = [
        (float(x), float(y))
        for x, y in re.findall(
            r"L ([-0-9.]+) ([-0-9.]+)", paths["feedback"]
        )
    ]
    assert len(points) >= 3
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        horizontal_hit = (
            y1 == y2 and top < y1 < bottom
            and max(min(x1, x2), left) < min(max(x1, x2), right)
        )
        vertical_hit = (
            x1 == x2 and left < x1 < right
            and max(min(y1, y2), top) < min(max(y1, y2), bottom)
        )
        assert not horizontal_hit and not vertical_hit


def _p2_feedback_geometry_model(group_sizes: tuple[int, ...]) -> dict:
    raw = _minimal_process_model(sum(group_sizes))
    if group_sizes:
        raw["groups"] = [
            {"id": f"g{idx}", "label": f"Group {idx}"}
            for idx in range(len(group_sizes))
        ]
        groups = [
            f"g{group_idx}"
            for group_idx, count in enumerate(group_sizes)
            for _ in range(count)
        ]
        for node, group in zip(raw["nodes"], groups):
            node["group"] = group
    return raw


def _p2_orthogonal_segments(path: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    # The first Bezier ends in a true row corridor, followed by the L legs.
    first = re.search(
        r"C [-0-9.]+ [-0-9.]+, [-0-9.]+ [-0-9.]+, "
        r"([-0-9.]+) ([-0-9.]+) L ",
        path,
    )
    if first is None:
        # Side-port outer-footer fallbacks are pure M/L polylines. They must
        # be checked too; an empty segment list would silently pass anything.
        points = [
            (float(x), float(y))
            for x, y in re.findall(r"(?:M|L) ([-0-9.]+) ([-0-9.]+)", path)
        ]
    else:
        points = [tuple(float(value) for value in first.groups())]
        points.extend(
            (float(x), float(y))
            for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path)
        )
    return list(zip(points, points[1:]))


def _p2_linear_path_clears_box(
    path: str, box: tuple[float, float, float, float]
) -> bool:
    left, top, width, height = box
    right, bottom = left + width, top + height
    for (x1, y1), (x2, y2) in _p2_orthogonal_segments(path):
        if y1 == y2 and top < y1 < bottom:
            if max(min(x1, x2), left) < min(max(x1, x2), right):
                return False
        if x1 == x2 and left < x1 < right:
            if max(min(y1, y2), top) < min(max(y1, y2), bottom):
                return False
    return True


def _p2_cubic_path_clears_box(
    path: str, box: tuple[float, float, float, float]
) -> bool:
    """Check the actual Bezier endpoint stubs, not just intervening L legs."""
    for match in re.finditer(
        r"(?:M|L) ([-0-9.]+) ([-0-9.]+) "
        r"C ([-0-9.]+) ([-0-9.]+), ([-0-9.]+) ([-0-9.]+), "
        r"([-0-9.]+) ([-0-9.]+)",
        path,
    ):
        values = tuple(float(value) for value in match.groups())
        points = tuple(
            (values[index], values[index + 1])
            for index in (0, 2, 4, 6)
        )
        if _cubic_hull_intersects_box(points, box):
            return False
    return True


def test_pr204_p2_shared_endpoint_local_branch_clears_foreign_label() -> None:
    """An endpoint shared with a second relation does not excuse a real collision."""
    raw = _p2_feedback_geometry_model((3, 3))
    raw["edges"] = [
        {"id": "local", "from": "n2", "to": "n3", "label": "x", "kind": "flow"},
        {"id": "peer", "from": "n3", "to": "n1", "label": "x", "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    assert _p2_orthogonal_segments(paths["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["peer"])
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (labels, paths) == (_edge_label_boxes(reordered), _edge_paths(reordered))


def test_pr204_p2_grouped_saturated_endpoint_renders_fallback() -> None:
    """A two-line long-branch label must not make a valid model unrenderable."""
    raw = _p2_feedback_geometry_model((4, 4, 4))
    raw["edges"] = [
        {"id": "feedback", "from": "n4", "to": "n2",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "long", "from": "n0", "to": "n11",
         "label": "Ein sehr langer Verbindungstext fuer zwei Zeilen zum Vorhaben",
         "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    assert "feedback" in _edge_paths(root)
    assert _p2_linear_path_clears_box(
        _edge_paths(root)["feedback"], _edge_label_boxes(root)["long"]
    )


def test_pr204_p2_grouped_intermediate_label_clears_feedback_return() -> None:
    """Check the full vertical return, not just source and target row corridors."""
    raw = _p2_feedback_geometry_model((4, 4, 4))
    raw["edges"] = [
        {"id": "feedback", "from": "n7", "to": "n4",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "long", "from": "n2", "to": "n8",
         "label": "Ein sehr langer Verbindungstext fuer zwei Zeilen zum Vorhaben",
         "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    assert _p2_orthogonal_segments(_edge_paths(root)["feedback"])
    assert _p2_linear_path_clears_box(
        _edge_paths(root)["feedback"], _edge_label_boxes(root)["long"]
    )
    # Match the SVG's true straight legs after its cubic entry, rather
    # than interpreting the Bezier's start/end as one diagonal segment.
    for card in _node_boxes(root).values():
        assert _p2_linear_path_clears_box(_edge_paths(root)["feedback"], card)


def test_pr204_p2_ungrouped_saturated_endpoint_renders_fallback() -> None:
    """A full pair of row gaps cannot justify dropping the whole SVG."""
    raw = _p2_feedback_geometry_model(())
    raw["nodes"] = _minimal_process_model(15)["nodes"]
    raw["edges"] = [
        {"id": "flow1", "from": "n0", "to": "n8", "label": "x", "kind": "flow"},
        {"id": "flow2", "from": "n8", "to": "n2", "label": "y", "kind": "flow"},
        {"id": "risk", "from": "n7", "to": "n9", "label": "z", "kind": "risk"},
        {"id": "feedback", "from": "n14", "to": "n1",
         "label": "Rueckmeldung", "kind": "feedback"},
    ]
    root = _parse(render_native_diagram(raw))
    assert "feedback" in _edge_paths(root)
    _assert_feedback_route_avoids_cards(root, "feedback")
    for key, box in _edge_label_boxes(root).items():
        if key != "feedback":
            assert _p2_linear_path_clears_box(_edge_paths(root)["feedback"], box)


def test_pr204_p2_detoured_feedback_never_enters_foreign_card_column() -> None:
    """A single-line long relation must not move its return into g1 cards."""
    raw = _p2_feedback_geometry_model((7, 6))
    raw["edges"] = [
        {"id": "flow", "from": "n3", "to": "n12",
         "label": "Diese lange Verbindung", "kind": "flow"},
        {"id": "feedback", "from": "n4", "to": "n3",
         "label": "Rueckmeldung", "kind": "feedback"},
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    path = paths["feedback"]
    assert _p2_orthogonal_segments(path)
    assert _p2_linear_path_clears_box(path, labels["flow"])
    for node_id, card in _node_boxes(root).items():
        if node_id not in {"n3", "n4"}:
            assert _p2_linear_path_clears_box(path, card), node_id

    raw["edges"].reverse()
    alternate = _parse(render_native_diagram(raw))
    assert (labels, paths) == (
        _edge_label_boxes(alternate), _edge_paths(alternate)
    )

def _pr204_named_group_model(rows_per_group: int) -> dict:
    """Use the exact two-group stable ids from the external P2 reproducers."""
    raw = _p2_feedback_geometry_model((rows_per_group, rows_per_group))
    names = {
        node["id"]: f"n{index // rows_per_group}_{index % rows_per_group}"
        for index, node in enumerate(raw["nodes"])
    }
    for node in raw["nodes"]:
        node["id"] = names[node["id"]]
    return raw


def test_pr204_postreview_p2_footer_clears_crossgroup_long_label() -> None:
    """Moving feedback text to the footer must not retain a crossing path."""
    raw = _pr204_named_group_model(4)
    raw["edges"] = [
        {
            "id": "feedback",
            "from": "n0_0",
            "to": "n1_0",
            "label": "Eine sehr lange Rueckmeldung mit mehreren Woertern",
            "kind": "feedback",
        },
        {
            "id": "branch",
            "from": "n1_3",
            "to": "n0_1",
            "label": "Long relation with process branch",
            "kind": "flow",
        },
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    assert _p2_orthogonal_segments(paths["feedback"])
    assert _p2_linear_path_clears_box(paths["feedback"], labels["branch"])
    for node_id, box in _node_boxes(root).items():
        if node_id not in {"n0_0", "n1_0"}:
            assert _p2_linear_path_clears_box(paths["feedback"], box), node_id
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (labels, paths) == (_edge_label_boxes(reordered), _edge_paths(reordered))


def test_pr204_postreview_p2_feedback_label_clears_crossgroup_long_leg() -> None:
    """A cross-group long-branch target leg is a label collision, too."""
    raw = _pr204_named_group_model(5)
    raw["edges"] = [
        {
            "id": "feedback",
            "from": "n0_3",
            "to": "n1_4",
            "label": "sync",
            "kind": "feedback",
        },
        {
            "id": "branch",
            "from": "n0_1",
            "to": "n1_4",
            "label": "long return",
            "kind": "flow",
        },
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    assert _p2_orthogonal_segments(paths["branch"])
    assert _p2_linear_path_clears_box(paths["branch"], labels["feedback"])
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (labels, paths) == (_edge_label_boxes(reordered), _edge_paths(reordered))


@pytest.mark.parametrize(
    "peer_label",
    [
        "a long two-line relation label",
        "Nebenprozess mit Titel",
    ],
)
def test_pr204_p2_forward_shared_endpoint_local_leg_clears_peer_label(
    peer_label: str,
) -> None:
    """A forward adjacent edge sharing source n0 can own the local source gap."""
    raw = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "local", "from": "n0", "to": "n5",
         "label": "x", "kind": "flow"},
        {"id": "peer", "from": "n0", "to": "n4",
         "label": peer_label, "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(edges)
    assert (labels, paths) == geometry(list(reversed(edges)))
    assert _p2_orthogonal_segments(paths["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["peer"])


@pytest.mark.parametrize("peer_label", ["x", "Intervening flow label"])
def test_pr204_p2_local_long_branch_clears_intermediate_label(
    peer_label: str,
) -> None:
    """A local inter-group return cannot cross an intermediate row-gap label."""
    raw = _p2_feedback_geometry_model((4, 4))
    original_edges = [
        {"id": "local", "from": "n0", "to": "n7",
         "label": "x", "kind": "flow"},
        {"id": "peer", "from": "n1", "to": "n6",
         "label": peer_label, "kind": "flow"},
    ]

    def geometry(edges: list[dict]) -> tuple[dict, dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(edges)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root)

    labels, paths = geometry(original_edges)
    assert (labels, paths) == geometry(list(reversed(original_edges)))
    assert _p2_orthogonal_segments(paths["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["peer"])


@pytest.mark.parametrize("later_peer_label", ["x", "Intervening flow label"])
def test_pr204_p2_speculative_peer_relocation_rolls_back_on_outer_route(
    later_peer_label: str,
) -> None:
    """A later blocker must not leave a speculative label move after fallback."""
    raw = _p2_feedback_geometry_model((4, 4))
    edges = [
        {"id": "local", "from": "n0", "to": "n7",
         "label": "x", "kind": "flow"},
        {"id": "a", "from": "n1", "to": "n6",
         "label": "Intervening flow label", "kind": "flow"},
        {"id": "b", "from": "n3", "to": "n6",
         "label": later_peer_label, "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return (
            _edge_label_boxes(root),
            _edge_paths(root),
            root.attrib["viewBox"],
        )

    labels, paths, canvas = geometry(edges)
    assert (labels, paths, canvas) == geometry(list(reversed(edges)))
    # The later blocker rejects the local route; the label keeps its packed
    # anchor rather than a leftover move that only made sense for that route.
    assert labels["a"][0] == 319.0
    assert _p2_orthogonal_segments(paths["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["a"])
    assert _p2_linear_path_clears_box(paths["local"], labels["b"])


@pytest.mark.parametrize("peer_label", ["x", "Intervening flow label"])
def test_pr204_p2_shared_target_adjacent_label_clears_local_branch(
    peer_label: str,
) -> None:
    """A shared target cannot exempt an adjacent peer's visible label."""
    raw = _p2_feedback_geometry_model((4, 4))
    edges = [
        {"id": "local", "from": "n0", "to": "n6",
         "label": "x", "kind": "flow"},
        {"id": "peer", "from": "n1", "to": "n6",
         "label": peer_label, "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root.attrib["viewBox"]

    labels, paths, canvas = geometry(edges)
    assert (labels, paths, canvas) == geometry(list(reversed(edges)))
    assert _p2_orthogonal_segments(paths["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["peer"])


@pytest.mark.parametrize("feedback_label", ["short relations", "short relation x"])
def test_pr204_p2_long_vertical_gutter_clears_feedback_label(
    feedback_label: str,
) -> None:
    """The long branch's vertical return leg must not bisect feedback text."""
    raw = _p2_feedback_geometry_model((2, 4))
    edges = [
        {"id": "feedback", "from": "n1", "to": "n3",
         "label": feedback_label, "kind": "feedback"},
        {"id": "long", "from": "n0", "to": "n5",
         "label": "x", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root.attrib["viewBox"]

    labels, paths, canvas = geometry(edges)
    assert (labels, paths, canvas) == geometry(list(reversed(edges)))
    assert _p2_orthogonal_segments(paths["long"])
    assert _p2_linear_path_clears_box(paths["long"], labels["feedback"])


@pytest.mark.parametrize("same_column", [False, True])
def test_pr204_p2_sideport_footer_clears_all_labels_and_cards(
    same_column: bool,
) -> None:
    """A footer fallback must clear its own label and every foreign obstacle."""
    if same_column:
        raw = _p2_feedback_geometry_model((4, 4))
        raw["edges"] = [
            {"id": "feedback", "from": "n2", "to": "n0",
             "label": "Rueckmeldung", "kind": "feedback"},
            {"id": "flow0", "from": "n5", "to": "n3",
             "label": "Ein sehr langer Verbindungstext fuer zwei Zeilen zum Vorhaben",
             "kind": "flow"},
            {"id": "flow1", "from": "n6", "to": "n1",
             "label": "Nebenprozess mit Titel", "kind": "flow"},
        ]
    else:
        raw = _p2_feedback_geometry_model((4, 4, 4))
        raw["edges"] = [
            {"id": "feedback", "from": "n4", "to": "n2",
             "label": "Rueckmeldung", "kind": "feedback"},
            {"id": "long", "from": "n0", "to": "n11",
             "label": "Ein sehr langer Verbindungstext fuer zwei Zeilen zum Vorhaben",
             "kind": "flow"},
            {"id": "peer", "from": "n1", "to": "n6",
             "label": "Nebenprozess mit Titel", "kind": "flow"},
        ]

    def geometry(edges: list[dict]) -> tuple[dict, dict, str, dict]:
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(edges)
        root = _parse(render_native_diagram(model))
        return (
            _edge_label_boxes(root),
            _edge_paths(root),
            root.attrib["viewBox"],
            _node_boxes(root),
        )

    labels, paths, canvas, cards = geometry(raw["edges"])
    assert (labels, paths, canvas, cards) == geometry(list(reversed(raw["edges"])))
    path = paths["feedback"]
    assert " C " not in path  # The actual all-orthogonal outer-footer fallback.
    assert len(_p2_orthogonal_segments(path)) >= 4
    for edge_id, label in labels.items():
        assert _p2_linear_path_clears_box(path, label), edge_id
    endpoints = {
        str(raw["edges"][0]["from"]),
        str(raw["edges"][0]["to"]),
    }
    for node_id, box in cards.items():
        if node_id not in endpoints:
            assert _p2_linear_path_clears_box(path, box), node_id

def test_pr204_p2_outer_feedback_never_crosses_peer_feedback_footer_label() -> None:
    """The outer side-port route must see the *other feedback's* final footer label."""
    raw = _p2_feedback_geometry_model((4, 4, 5, 5))
    raw["edges"] = [
        {"id": "feedback0", "from": "n17", "to": "n10",
         "label": "x", "kind": "feedback"},
        {"id": "feedback1", "from": "n14", "to": "n2",
         "label": "x", "kind": "feedback"},
        {"id": "feedback2", "from": "n2", "to": "n1",
         "label": "x", "kind": "feedback"},
        {"id": "feedback3", "from": "n9", "to": "n0",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "feedback4", "from": "n3", "to": "n1",
         "label": "x", "kind": "feedback"},
        {"id": "flow0", "from": "n2", "to": "n6",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow1", "from": "n6", "to": "n8",
         "label": "E", "kind": "flow"},
        {"id": "flow2", "from": "n15", "to": "n13",
         "label": "E" * 70, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    # This is a genuine grouped side-port fallback with one global footer.
    assert " C " not in paths["feedback1"]
    assert _p2_orthogonal_segments(paths["feedback1"])
    assert _p2_linear_path_clears_box(
        paths["feedback1"], labels["feedback2"]
    ), "outer feedback must not cut through the other feedback's footer text"
    for other_id, label in labels.items():
        if other_id != "feedback1":
            assert _p2_linear_path_clears_box(
                paths["feedback1"], label
            ), other_id
    for node_id, card in _node_boxes(root).items():
        if node_id not in {"n14", "n2"}:
            assert _p2_linear_path_clears_box(paths["feedback1"], card), node_id
    raw["edges"].reverse()
    reversed_root = _parse(render_native_diagram(raw))
    assert (labels, paths) == (
        _edge_label_boxes(reversed_root), _edge_paths(reversed_root)
    )

def test_pr204_p2_two_outer_feedback_returns_clear_each_others_footer_labels() -> None:
    """Two side-port returns in one grouped model may not cut through peer text."""
    raw = _p2_feedback_geometry_model((2, 2, 4))
    raw["edges"] = [
        {"id": "feedback0", "from": "n3", "to": "n0",
         "label": "x", "kind": "feedback"},
        {"id": "feedback1", "from": "n3", "to": "n2",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "feedback2", "from": "n2", "to": "n0",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "feedback3", "from": "n7", "to": "n5",
         "label": "x", "kind": "feedback"},
        {"id": "flow0", "from": "n4", "to": "n3",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow1", "from": "n2", "to": "n5",
         "label": "E", "kind": "flow"},
        {"id": "flow2", "from": "n5", "to": "n4",
         "label": "E" * 45, "kind": "flow"},
        {"id": "flow3", "from": "n4", "to": "n2",
         "label": "E" * 70, "kind": "risk"},
        {"id": "flow4", "from": "n0", "to": "n2",
         "label": "E" * 45, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    for outer_id in ("feedback0", "feedback1"):
        assert " C " not in paths[outer_id]
        for other_id, box in labels.items():
            if outer_id != other_id:
                assert _p2_linear_path_clears_box(paths[outer_id], box), (
                    outer_id, other_id
                )
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (labels, paths) == (_edge_label_boxes(reordered), _edge_paths(reordered))

def test_pr204_p2_dense_feedback_outer_needs_only_bounded_gutter_growth() -> None:
    """Crowded labels must not make a valid process diagram unrenderable."""
    raw = _p2_feedback_geometry_model((12, 5))
    raw["edges"] = [
        {"id": "feedback0", "from": "n8", "to": "n5",
         "label": "x", "kind": "feedback"},
        {"id": "feedback1", "from": "n16", "to": "n7",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "feedback2", "from": "n11", "to": "n0",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "feedback3", "from": "n4", "to": "n0",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "feedback4", "from": "n2", "to": "n1",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "flow0", "from": "n1", "to": "n9",
         "label": "E" * 22, "kind": "risk"},
        {"id": "flow1", "from": "n1", "to": "n10",
         "label": "E" * 45, "kind": "flow"},
        {"id": "flow2", "from": "n5", "to": "n13",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow3", "from": "n10", "to": "n1",
         "label": "E" * 45, "kind": "risk"},
        {"id": "flow4", "from": "n7", "to": "n10",
         "label": "E" * 5, "kind": "flow"},
        {"id": "flow5", "from": "n16", "to": "n9",
         "label": "E" * 45, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    width = float(root.attrib["viewBox"].split()[2])
    assert width <= 1150, "bounded gutter fix may not grow the canvas without limit"
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    assert " C " not in paths["feedback1"]
    for label_id, box in labels.items():
        if label_id != "feedback1":
            assert _p2_linear_path_clears_box(paths["feedback1"], box), label_id
    for node_id, box in _node_boxes(root).items():
        if node_id not in {"n16", "n7"}:
            assert _p2_linear_path_clears_box(paths["feedback1"], box), node_id

def test_pr204_p2_parallel_outer_feedbacks_have_distinct_routes() -> None:
    """Different feedback semantics must not be visually erased by identical paths."""
    raw = _p2_feedback_geometry_model((2, 3))
    raw["edges"] = [
        {"id": "first", "from": "n2", "to": "n0",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "second", "from": "n2", "to": "n0",
         "label": "x", "kind": "feedback"},
        {"id": "flow", "from": "n3", "to": "n1",
         "label": "x", "kind": "flow"},
        {"id": "long", "from": "n0", "to": "n3",
         "label": "E" * 70, "kind": "risk"},
    ]
    root = _parse(render_native_diagram(raw))
    labels, paths = _edge_label_boxes(root), _edge_paths(root)
    assert " C " not in paths["first"]
    assert " C " not in paths["second"]
    assert paths["first"] != paths["second"]
    for edge_id in ("first", "second"):
        for foreign, box in labels.items():
            if foreign != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, foreign
                )
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (labels, paths) == (
        _edge_label_boxes(reordered), _edge_paths(reordered)
    )

def test_pr204_p2_five_parallel_feedbacks_have_distinct_visible_routes() -> None:
    """Five semantic peers sharing endpoints must retain distinguishable rails."""
    raw = _p2_feedback_geometry_model((3, 4))
    raw["edges"] = [
        {"id": f"feedback{index}", "from": "n3", "to": "n1",
         "label": label, "kind": "feedback"}
        for index, label in enumerate((
            "Mehrzeilige Feedbackkommunikation 12345",
            "Mehrzeilige Feedbackkommunikation 12345",
            "Rueckmeldung", "x", "x",
        ))
    ] + [
        {"id": "flow0", "from": "n5", "to": "n6",
         "label": "E" * 45, "kind": "flow"},
        {"id": "flow1", "from": "n1", "to": "n6",
         "label": "E" * 45, "kind": "flow"},
        {"id": "flow2", "from": "n4", "to": "n0",
         "label": "E" * 45, "kind": "flow"},
        {"id": "flow3", "from": "n6", "to": "n0",
         "label": "E" * 70, "kind": "risk"},
        {"id": "flow4", "from": "n4", "to": "n1",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow5", "from": "n1", "to": "n2",
         "label": "E", "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    paths, labels, cards = (
        _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
    )
    outer = [
        f"feedback{index}"
        for index in range(5)
        if " C " not in paths[f"feedback{index}"]
        and paths[f"feedback{index}"].count(" L ") >= 4
    ]
    assert len(outer) >= 2
    assert len({paths[edge_id] for edge_id in outer}) == len(outer)
    for edge_id in outer:
        for foreign, box in labels.items():
            if foreign != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, foreign
                )
        for card_id, box in cards.items():
            if card_id not in {"n3", "n1"}:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, card_id
                )
    # Different paths can still share long vertical strokes and erase a peer.
    for index, first in enumerate(outer):
        for second in outer[index + 1:]:
            for (a, b) in _p2_orthogonal_segments(paths[first]):
                for (c, d) in _p2_orthogonal_segments(paths[second]):
                    if abs(a[0] - b[0]) >= 0.01 or abs(c[0] - d[0]) >= 0.01:
                        continue
                    overlap = min(max(a[1], b[1]), max(c[1], d[1])) - max(
                        min(a[1], b[1]), min(c[1], d[1])
                    )
                    assert abs(a[0] - c[0]) >= 4 or overlap <= 4, (
                        first, second, "overlapping vertical feedback stems"
                    )
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (paths, labels) == (
        _edge_paths(reordered), _edge_label_boxes(reordered)
    )

def test_pr204_p2_outer_peer_label_solver_converges_for_three_feedbacks() -> None:
    """Valid grouped three-peer feedback must not fail due to label oscillation."""
    raw = _p2_feedback_geometry_model((5, 2))
    raw["edges"] = [
        {"id": "fb0", "from": "n6", "to": "n3",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "fb1", "from": "n6", "to": "n3",
         "label": "x", "kind": "feedback"},
        {"id": "fb2", "from": "n6", "to": "n3",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "flow0", "from": "n3", "to": "n6",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow1", "from": "n3", "to": "n0",
         "label": "E" * 45, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    for edge_id in ("fb0", "fb1", "fb2"):
        assert " C " not in paths[edge_id]
        for other_id, box in labels.items():
            if other_id != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, other_id
                )
        for node_id, box in _node_boxes(root).items():
            if node_id not in {"n6", "n3"}:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, node_id
                )
    assert len({paths[key] for key in ("fb0", "fb1", "fb2")}) == 3
    raw["edges"].reverse()
    other = _parse(render_native_diagram(raw))
    assert (paths, labels) == (_edge_paths(other), _edge_label_boxes(other))


def test_pr204_p2_seven_parallel_feedbacks_do_not_exhaust_safe_outer_routes() -> None:
    """Seed 918134: valid seven-peer grouped feedback must render safely."""
    raw = _p2_feedback_geometry_model((4, 2))
    raw["edges"] = [
        {"id": f"fb{index}", "from": "n5", "to": "n3",
         "label": label, "kind": "feedback"}
        for index, label in enumerate((
            "Mehrzeilige Feedbackkommunikation 12345", "x",
            "Rueckmeldung", "Rueckmeldung", "Rueckmeldung", "x",
            "Rueckmeldung",
        ))
    ] + [
        {"id": "flow0", "from": "n0", "to": "n3",
         "label": "E" * 45, "kind": "risk"},
        {"id": "flow1", "from": "n5", "to": "n3",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow2", "from": "n1", "to": "n4",
         "label": "E" * 22, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    paths, labels, cards = (
        _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
    )
    outer = [
        f"fb{index}" for index in range(7)
        if " C " not in paths[f"fb{index}"]
        and paths[f"fb{index}"].count(" L ") >= 4
    ]
    assert len(outer) >= 2
    assert len({paths[edge_id] for edge_id in outer}) == len(outer)
    for edge_id in outer:
        for other_id, box in labels.items():
            if other_id != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, other_id
                )
        for card_id, box in cards.items():
            if card_id not in {"n5", "n3"}:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, card_id
                )
    for idx, first in enumerate(outer):
        for second in outer[idx + 1:]:
            for (start_a, end_a) in _p2_orthogonal_segments(paths[first]):
                for (start_b, end_b) in _p2_orthogonal_segments(paths[second]):
                    if abs(start_a[0] - end_a[0]) < 0.01 and abs(start_b[0] - end_b[0]) < 0.01:
                        overlap = min(max(start_a[1], end_a[1]), max(start_b[1], end_b[1])) - max(
                            min(start_a[1], end_a[1]), min(start_b[1], end_b[1])
                        )
                        assert abs(start_a[0] - start_b[0]) >= 4 or overlap <= 4, (
                            first, second, "vertical overlap"
                        )
                    if abs(start_a[1] - end_a[1]) < 0.01 and abs(start_b[1] - end_b[1]) < 0.01:
                        overlap = min(max(start_a[0], end_a[0]), max(start_b[0], end_b[0])) - max(
                            min(start_a[0], end_a[0]), min(start_b[0], end_b[0])
                        )
                        assert abs(start_a[1] - start_b[1]) >= 4 or overlap <= 4, (
                            first, second, "horizontal overlap"
                        )
    raw["edges"].reverse()
    other = _parse(render_native_diagram(raw))
    assert (paths, labels) == (_edge_paths(other), _edge_label_boxes(other))


def test_pr204_p2_grouped_side_ports_survive_dense_intercolumn_labels() -> None:
    """Dense grouped labels must not mask otherwise local feedback paths."""
    raw = _p2_feedback_geometry_model((4, 3, 2))
    raw["edges"] = [
        {"id": "feedback0", "from": "n4", "to": "n3",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "feedback1", "from": "n0", "to": "n6",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "flow0", "from": "n3", "to": "n5",
         "label": "E" * 70, "kind": "flow"},
        {"id": "flow1", "from": "n2", "to": "n6",
         "label": "E" * 22, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    paths = _edge_paths(root)
    labels = _edge_label_boxes(root)
    cards = _node_boxes(root)
    endpoints = {"feedback0": {"n4", "n3"}, "feedback1": {"n0", "n6"}}
    for edge_id in endpoints:
        for other_id, box in labels.items():
            if other_id != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, other_id
                )
        for card_id, box in cards.items():
            if card_id not in endpoints[edge_id]:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, card_id
                )
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (paths, labels) == (
        _edge_paths(reordered), _edge_label_boxes(reordered)
    )

@pytest.mark.parametrize(
    ("flow_kind", "label_size"),
    [("risk", 45), ("risk", 70), ("flow", 70)],
)
def test_pr204_p2_risk_label_saturation_has_safe_outer_feedback_routes(
    flow_kind: str, label_size: int,
) -> None:
    """A risk-branch label must not make a valid grouped process fail to render."""
    raw = _p2_feedback_geometry_model((4, 3, 2))
    raw["edges"] = [
        {"id": "feedback0", "from": "n4", "to": "n3",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "feedback1", "from": "n0", "to": "n6",
         "label": "Mehrzeilige Feedbackkommunikation 12345", "kind": "feedback"},
        {"id": "flow0", "from": "n3", "to": "n5",
         "label": "E" * label_size, "kind": flow_kind},
        {"id": "flow1", "from": "n2", "to": "n6",
         "label": "E" * 22, "kind": "flow"},
    ]
    root = _parse(render_native_diagram(raw))
    paths, labels, cards = (
        _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
    )
    endpoints = {"feedback0": {"n4", "n3"}, "feedback1": {"n0", "n6"}}
    for edge_id, own in endpoints.items():
        for other_id, box in labels.items():
            if other_id != edge_id:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, other_id
                )
        for card_id, box in cards.items():
            if card_id not in own:
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    edge_id, card_id
                )
    raw["edges"].reverse()
    reordered = _parse(render_native_diagram(raw))
    assert (paths, labels) == (
        _edge_paths(reordered), _edge_label_boxes(reordered)
    )


@pytest.mark.parametrize("peer_label", ["W" * 120])
def test_pr204_p2_outer_forward_source_leg_clears_local_long_label(
    peer_label: str,
) -> None:
    """A displaced forward branch's full source leg cannot cross a long-branch label."""
    raw = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "local", "from": "n0", "to": "n5",
         "label": "x", "kind": "flow"},
        {"id": "wide", "from": "n0", "to": "n4",
         "label": peer_label, "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return _edge_label_boxes(root), _edge_paths(root), root.attrib["viewBox"]

    labels, paths, canvas = geometry(edges)
    assert (labels, paths, canvas) == geometry(list(reversed(edges)))
    assert _p2_orthogonal_segments(paths["wide"])
    assert _p2_linear_path_clears_box(paths["wide"], labels["local"])
    assert _p2_linear_path_clears_box(paths["local"], labels["wide"])

def test_pr204_p2_saturated_side_ports_expand_only_needed_group_gap() -> None:
    """A feasible grouped feedback layout must not fail after 66 width-only retries."""
    raw = _p2_feedback_geometry_model((7, 5, 1, 2))
    edges = [
        {"id": "risk", "from": "n13", "to": "n5",
         "label": "R" * 25, "kind": "risk"},
        {"id": "far", "from": "n2", "to": "n14",
         "label": "W" * 22, "kind": "flow"},
        {"id": "near", "from": "n0", "to": "n11",
         "label": "L" * 22, "kind": "flow"},
        {"id": "feedback", "from": "n14", "to": "n7",
         "label": "x", "kind": "feedback"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths = _edge_paths(root)
        labels = _edge_label_boxes(root)
        cards = _node_boxes(root)
        assert _p2_orthogonal_segments(paths["feedback"])
        for edge_id, box in labels.items():
            if edge_id != "feedback":
                assert _p2_linear_path_clears_box(paths["feedback"], box), edge_id
        for node_id, box in cards.items():
            if node_id not in {"n14", "n7"}:
                assert _p2_linear_path_clears_box(paths["feedback"], box), node_id
        assert float(root.attrib["viewBox"].split()[2]) <= 1950
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

    def painter_order(ordered: list[dict]) -> list[str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        return [
            child.attrib["data-source-id"]
            for child in root
            if child.attrib.get("data-source-kind") == "edge"
        ]

    # Crossing paths do not commute: the top-painted stroke must not depend
    # on an arbitrary edge input list order even if geometry dicts compare equal.
    assert painter_order(edges) == painter_order(list(reversed(edges)))

def test_pr204_p2_parallel_same_endpoints_have_separate_visible_routes() -> None:
    """Two semantic feedback edges may never publish the same SVG stroke."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "feedback0", "from": "n2", "to": "n0",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "feedback1", "from": "n2", "to": "n0",
         "label": "x", "kind": "feedback"},
        {"id": "flow", "from": "n3", "to": "n1",
         "label": "x", "kind": "flow"},
        {"id": "risk", "from": "n0", "to": "n3",
         "label": "x", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        assert paths["feedback0"] != paths["feedback1"]
        for edge_id in ("feedback0", "feedback1"):
            assert _p2_orthogonal_segments(paths[edge_id])
            for other_id, box in labels.items():
                if other_id != edge_id:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, other_id
                    )
            for card_id, box in cards.items():
                if card_id not in {"n2", "n0"}:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, card_id
                    )
        assert float(root.attrib["viewBox"].split()[2]) <= 1950
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_parallel_feedback_self_loops_do_not_coincide() -> None:
    """Two semantically different return-to-self edges need visible routes."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "loop0", "from": "n2", "to": "n2",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "loop1", "from": "n2", "to": "n2",
         "label": "x", "kind": "feedback"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths = _edge_paths(root)
        labels = _edge_label_boxes(root)
        cards = _node_boxes(root)
        assert paths["loop0"] != paths["loop1"]
        for edge_id in ("loop0", "loop1"):
            assert _p2_orthogonal_segments(paths[edge_id])
            for peer_id, box in labels.items():
                if peer_id != edge_id:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, peer_id
                    )
            for node_id, box in cards.items():
                if node_id != "n2":
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, node_id
                    )
        assert float(root.attrib["viewBox"].split()[2]) <= 1950
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_selfloop_peer_crossings_have_stable_paint_order() -> None:
    """An equivalent edge permutation must not change which crossing is painted first."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "loop0", "from": "n2", "to": "n2",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "loop1", "from": "n2", "to": "n2",
         "label": "x", "kind": "feedback"},
        {"id": "loop2", "from": "n2", "to": "n2",
         "label": "weitere Rueckmeldung", "kind": "feedback"},
        {"id": "flow", "from": "n3", "to": "n1",
         "label": "x", "kind": "flow"},
    ]

    def rendered(ordered: list[dict]) -> tuple[list[str], dict]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        painted = [
            node.attrib["data-source-id"]
            for node in root
            if node.attrib.get("data-source-kind") == "edge"
        ]
        paths = _edge_paths(root)
        assert len({paths[edge_id] for edge_id in ("loop0", "loop1", "loop2")}) == 3
        return painted, paths

    assert rendered(edges) == rendered(list(reversed(edges)))

def test_pr204_p2_late_shifted_feedback_gutter_avoids_foreign_cards() -> None:
    """A label-forced late detour must also reserve card rectangles."""
    raw = _p2_feedback_geometry_model((6, 7, 2))
    edges = [
        {"id": "feedback", "from": "n0", "to": "n2",
         "label": "Rueckmeldung", "kind": "feedback"},
        {"id": "flow0", "from": "n3", "to": "n11",
         "label": "F" * 22, "kind": "flow"},
        {"id": "flow1", "from": "n7", "to": "n8",
         "label": "E" * 22, "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        for other_id, box in labels.items():
            if other_id != "feedback":
                assert _p2_linear_path_clears_box(paths["feedback"], box), other_id
        for node_id, box in cards.items():
            if node_id not in {"n0", "n2"}:
                assert _p2_linear_path_clears_box(paths["feedback"], box), node_id
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr204_p2_packed_adjacent_label_clears_outer_risk_target_leg() -> None:
    """Horizontal label packing must reserve the outer long-risk target leg."""
    raw = _p2_feedback_geometry_model((2, 2, 5, 5))
    edges = [
        {"id": "outer", "from": "n1", "to": "n13",
         "label": "R" * 70, "kind": "risk"},
        {"id": "a", "from": "n8", "to": "n12",
         "label": "L" * 70, "kind": "flow"},
        {"id": "b", "from": "n8", "to": "n13",
         "label": "x", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["outer"], labels["a"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def _p2_named_group_model(group_sizes: tuple[int, ...]) -> dict:
    """Use stable semantic node ids from the independent P2 reproductions."""
    raw = _p2_feedback_geometry_model(group_sizes)
    for node, node_id in zip(raw["nodes"], "abcdefghijklmnopqrstuvxyz"):
        node["id"] = node_id
        node["label"] = node_id
    return raw


def test_pr205_p2_single_group_rank_space_recovers_sideport_exhaustion() -> None:
    """A single group with multiple rank columns must remain renderable."""
    raw = _p2_named_group_model((5,))
    edges = [
        {"id": "e0", "from": "b", "to": "b", "label": "link", "kind": "feedback"},
        {"id": "e1", "from": "b", "to": "b", "label": "link", "kind": "feedback"},
        {"id": "e2", "from": "a", "to": "b", "label": "link", "kind": "risk"},
        {"id": "e3", "from": "a", "to": "e", "label": "link", "kind": "flow"},
        {"id": "e4", "from": "b", "to": "d", "label": "link", "kind": "flow"},
        {"id": "e5", "from": "b", "to": "c",
         "label": "a somewhat longer relation label", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        assert paths["e0"] != paths["e1"]
        for edge_id in ("e0", "e1"):
            for other_id, box in labels.items():
                if other_id != edge_id:
                    assert _p2_linear_path_clears_box(paths[edge_id], box)
            for node_id, box in cards.items():
                if node_id != "b":
                    assert _p2_linear_path_clears_box(paths[edge_id], box)
        assert float(root.attrib["viewBox"].split()[2]) <= 2400
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_outgoing_shared_target_label_clears_local_long_leg() -> None:
    """A shared endpoint cannot exempt its outgoing label from the gutter."""
    raw = _p2_named_group_model((3, 3))
    edges = [
        {"id": "e0", "from": "a", "to": "a", "label": "link", "kind": "flow"},
        {"id": "e1", "from": "d", "to": "d", "label": "link", "kind": "flow"},
        {"id": "e2", "from": "a", "to": "f",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e3", "from": "f", "to": "c", "label": "link", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e2"], labels["e3"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_packed_label_clears_noncandidate_endpoint_stem() -> None:
    """Moving a label must not mask an adjacent noncandidate node stem."""
    raw = _p2_named_group_model((2, 3))
    edges = [
        {"id": "e0", "from": "d", "to": "b", "label": "link", "kind": "risk"},
        {"id": "e2", "from": "d", "to": "c", "label": "link", "kind": "flow"},
        {"id": "e3", "from": "a", "to": "e", "label": "link", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e2"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_natural_process_anchor_label_clears_feedback_and_outer_leg() -> None:
    """Browser-visible anchored labels must clear both feedback and long flow."""
    raw = _p2_feedback_geometry_model((3, 3, 3))
    edges = [
        {"id": "request", "from": "n0", "to": "n3",
         "label": "Antrag weiterleiten", "kind": "flow"},
        {"id": "approval", "from": "n3", "to": "n6",
         "label": "Freigabe", "kind": "flow"},
        {"id": "outcome", "from": "n6", "to": "n8",
         "label": "Ergebnis prüfen", "kind": "flow"},
        {"id": "revision", "from": "n5", "to": "n1",
         "label": "Neue Planung", "kind": "feedback"},
        {"id": "risk", "from": "n4", "to": "n7",
         "label": "Qualitätsrisiko", "kind": "risk"},
        {"id": "audit", "from": "n7", "to": "n3",
         "label": "Erneute Freigabe", "kind": "feedback"},
        {"id": "checks", "from": "n2", "to": "n6",
         "label": "Technische Prüfung", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        for edge_id in ("audit", "checks"):
            assert _p2_linear_path_clears_box(paths[edge_id], labels["outcome"]), edge_id
            assert _p2_cubic_path_clears_box(paths[edge_id], labels["outcome"]), edge_id
        assert float(root.attrib["viewBox"].split()[2]) <= 1800
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_dont_block_clear_diagonal_stems_in_label_pack() -> None:
    """A diagonal risk curve has no full-height stem in the adjacent row gap."""
    raw = _p2_feedback_geometry_model((2, 2, 2))
    edges = [
        {"id": "e0", "from": "n3", "to": "n1",
         "label": "link", "kind": "feedback"},
        {"id": "e1", "from": "n3", "to": "n5",
         "label": "Approve", "kind": "flow"},
        {"id": "e2", "from": "n5", "to": "n3",
         "label": "Approve", "kind": "flow"},
        {"id": "e3", "from": "n3", "to": "n0",
         "label": "link", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e2"], labels["e1"])
        assert _p2_cubic_path_clears_box(paths["e2"], labels["e1"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_target_leg_clears_packed_long_branch_peer_label() -> None:
    """A target-leg replan must see the already packed global risk labels."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "e1", "from": "n4", "to": "n0",
         "label": "a somewhat longer relation label", "kind": "risk"},
        {"id": "e2", "from": "n0", "to": "n4",
         "label": "link", "kind": "flow"},
        {"id": "e3", "from": "n4", "to": "n0",
         "label": "link", "kind": "risk"},
        {"id": "e4", "from": "n4", "to": "n3",
         "label": "Approve", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e2"], labels["e3"])
        assert _p2_cubic_path_clears_box(paths["e2"], labels["e3"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_forced_footer_clears_local_selfloop_stroke() -> None:
    """An outer feedback label must not obscure a non-outer selfloop rail."""
    raw = _p2_feedback_geometry_model((2, 2, 2))
    edges = [
        {"id": "e0", "from": "n3", "to": "n3",
         "label": "link", "kind": "feedback"},
        {"id": "e1", "from": "n1", "to": "n4",
         "label": "Approve", "kind": "feedback"},
        {"id": "e2", "from": "n3", "to": "n4",
         "label": "a somewhat longer relation label", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        assert _p2_linear_path_clears_box(paths["e0"], labels["e1"])
        assert _p2_cubic_path_clears_box(paths["e0"], labels["e1"])
        assert paths["e0"] != paths["e1"]
        endpoints = {"e0": {"n3"}, "e1": {"n1", "n4"}}
        for edge_id, excluded in endpoints.items():
            for node_id, card in cards.items():
                if node_id not in excluded:
                    assert _p2_linear_path_clears_box(paths[edge_id], card)
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_packed_stem_does_not_force_peer_label_crossing() -> None:
    """A relocated label must not demote a safe peer into a foreign label."""
    raw = _p2_feedback_geometry_model((2, 2))
    edges = [
        {"id": "e0", "from": "n0", "to": "n1",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e2", "from": "n0", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "risk"},
        {"id": "e3", "from": "n3", "to": "n1",
         "label": "link", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e3"], labels["e0"])
        assert _p2_cubic_path_clears_box(paths["e3"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_source_leg_clears_packed_long_branch_label() -> None:
    """The long-branch source leg must reserve already packed outer labels."""
    raw = _p2_feedback_geometry_model((3, 4))
    edges = [
        {"id": "e0", "from": "n0", "to": "n6",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e1", "from": "n1", "to": "n6",
         "label": "Approve", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e0"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_target_leg_uses_actual_selfloop_label_ordinate() -> None:
    """Selfloop labels occupy actual above-card slots, not row midpoints."""
    raw = _p2_feedback_geometry_model((2, 2, 2))
    edges = [
        {"id": "e0", "from": "n1", "to": "n4",
         "label": "link", "kind": "flow"},
        {"id": "e1", "from": "n5", "to": "n2",
         "label": "link", "kind": "flow"},
        {"id": "e2", "from": "n3", "to": "n3",
         "label": "Approve", "kind": "risk"},
        {"id": "e3", "from": "n4", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e5", "from": "n5", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e2"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e2"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_outer_footer_label_clears_local_feedback_stub() -> None:
    """Forced outer labels must clear locally retained non-selfloop cubics."""
    raw = _p2_feedback_geometry_model((2, 2, 2))
    edges = [
        {"id": "e0", "from": "n5", "to": "n0",
         "label": "link", "kind": "feedback"},
        {"id": "e1", "from": "n3", "to": "n1",
         "label": "Approve", "kind": "feedback"},
        {"id": "e5", "from": "n1", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e0"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_stroke_obstacles_do_not_exhaust_safe_outer_routes() -> None:
    """A peer line may not forbid otherwise safe feedback port geometry."""
    raw = _p2_feedback_geometry_model((3, 4))
    edges = [
        {"id": "a", "from": "n6", "to": "n4",
         "label": "link", "kind": "feedback"},
        {"id": "b", "from": "n6", "to": "n0",
         "label": "a somewhat longer relation label", "kind": "feedback"},
        {"id": "c", "from": "n5", "to": "n2",
         "label": "a somewhat longer relation label", "kind": "feedback"},
        {"id": "d", "from": "n5", "to": "n1",
         "label": "a somewhat longer relation label", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert set(paths) == {"a", "b", "c", "d"}
        for feedback in ("a", "b", "c"):
            for peer_id, box in labels.items():
                if peer_id != feedback:
                    assert _p2_linear_path_clears_box(paths[feedback], box), (
                        feedback, peer_id
                    )
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_stem_pack_preserves_safe_peer_lane() -> None:
    """Right-of-stem labels must not demote safe peers to crossing outer rails."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "e2", "from": "n1", "to": "n2",
         "label": "a somewhat longer relation label", "kind": "risk"},
        {"id": "e4", "from": "n0", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e5", "from": "n2", "to": "n3",
         "label": "Approve", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e5"], labels["e4"])
        assert _p2_cubic_path_clears_box(paths["e5"], labels["e4"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_target_blocked_corridor_preserves_local_return() -> None:
    """An exhausted label-aware target search cannot accept an unsafe rail."""
    raw = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "e0", "from": "n0", "to": "n1",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e1", "from": "n3", "to": "n5",
         "label": "a somewhat longer relation label", "kind": "risk"},
        {"id": "e2", "from": "n2", "to": "n3",
         "label": "link", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e2"], labels["e0"])
        assert _p2_cubic_path_clears_box(paths["e2"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_failed_stem_pack_does_not_mask_anchored_peer() -> None:
    """Rejecting a pack cannot mask another local relation's retained label."""
    raw = _p2_feedback_geometry_model((2, 2))
    edges = [
        {"id": "e0", "from": "n3", "to": "n1",
         "label": "link", "kind": "flow"},
        {"id": "e1", "from": "n0", "to": "n3",
         "label": "a somewhat longer relation label", "kind": "risk"},
        {"id": "e2", "from": "n1", "to": "n1",
         "label": "link", "kind": "flow"},
        {"id": "e3", "from": "n1", "to": "n0",
         "label": "link", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e0"], labels["e2"])
        assert _p2_cubic_path_clears_box(paths["e0"], labels["e2"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_source_leg_uses_rendered_selfloop_label_height() -> None:
    """The source-leg search must see the actual above-card selfloop label."""
    raw = _p2_feedback_geometry_model((4,))
    edges = [
        {"id": "e0", "from": "n3", "to": "n0",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e1", "from": "n1", "to": "n2",
         "label": "link", "kind": "flow"},
        {"id": "e3", "from": "n3", "to": "n3",
         "label": "link", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e3"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e3"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_p2_diagonal_source_count_preserves_vertical_peer_label() -> None:
    """Extra source corridor accounting may not move a peer label onto a rail."""
    raw = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "e0", "from": "n5", "to": "n0",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e1", "from": "n5", "to": "n3",
         "label": "link", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e0"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e0"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_long_return_respects_actual_same_row_label() -> None:
    """An adjacent same-row label's rendered y wins over a row-gap midpoint."""
    raw = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "e1", "from": "n0", "to": "n5",
         "label": "a somewhat longer relation label", "kind": "flow"},
        {"id": "e3", "from": "n5", "to": "n2",
         "label": "Approve", "kind": "flow"},
        {"id": "e4", "from": "n4", "to": "n1",
         "label": "a somewhat longer relation label", "kind": "risk"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e4"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e4"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_repacked_vertical_return_clears_selfloop_label() -> None:
    """Diagonal target occupancy cannot repack a clear return into a peer loop label."""
    raw = _p2_feedback_geometry_model((2, 3))
    edges = [
        {"id": "e0", "from": "n1", "to": "n2",
         "label": "Approve", "kind": "flow"},
        {"id": "e1", "from": "n2", "to": "n4",
         "label": "Approve", "kind": "risk"},
        {"id": "e2", "from": "n4", "to": "n4",
         "label": "Approve", "kind": "flow"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(paths["e1"], labels["e2"])
        assert _p2_cubic_path_clears_box(paths["e1"], labels["e2"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("sizes", "relations", "blocked"),
    [
        ((2, 3), [
            ("n4", "n2", "flow", "link"),
            ("n2", "n1", "risk", "link"),
            ("n1", "n4", "flow", "Approve"),
            ("n3", "n3", "flow", "link"),
        ], [("e3", "e0")]),
        ((3, 3, 3), [
            ("n2", "n0", "risk", "link"),
            ("n8", "n1", "flow", "link"),
        ], [("e0", "e1")]),
        ((3, 3, 3), [
            ("n8", "n7", "flow", "link"),
            ("n0", "n2", "flow", "link"),
            ("n8", "n1", "flow", "link"),
            ("n6", "n1", "risk", "Approve"),
        ], [("e1", "e2"), ("e1", "e3")]),
    ],
)
def test_pr205_p2_diagonal_target_pack_keeps_foreign_labels_clear(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    blocked: list[tuple[str, str]],
) -> None:
    """Diagonal-target sharing must not route through unrelated peer labels."""
    raw = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{i}", "from": source, "to": target, "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        for edge_id, label_id in blocked:
            assert _p2_linear_path_clears_box(paths[edge_id], labels[label_id]), (
                edge_id, label_id
            )
            assert _p2_cubic_path_clears_box(paths[edge_id], labels[label_id]), (
                edge_id, label_id
            )
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("relations", "crossing"),
    [
        (
            [
                ("n1", "n6", "risk", "link"),
                ("n5", "n3", "risk", "short relation"),
                ("n6", "n4", "flow", "Approve"),
                ("n6", "n3", "feedback", "link"),
            ],
            ("e2", "e1"),
        ),
        (
            [
                ("n6", "n0", "flow", "short relation"),
                ("n6", "n4", "risk", "short relation"),
                ("n3", "n5", "flow", "short relation"),
                ("n1", "n2", "feedback", "short relation"),
            ],
            ("e1", "e0"),
        ),
    ],
)
def test_pr205_p2_long_return_clears_newly_natural_outer_label(
    relations: list[tuple[str, str, str, str]],
    crossing: tuple[str, str],
) -> None:
    """A local vertical return must not cover a displaced long-branch label."""
    raw = _p2_feedback_geometry_model((4, 3))
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "label": label, "kind": kind}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        path_id, label_id = crossing
        assert _p2_linear_path_clears_box(paths[path_id], labels[label_id])
        assert _p2_cubic_path_clears_box(paths[path_id], labels[label_id])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))



@pytest.mark.parametrize(
    ("group_sizes", "relations", "crossings"),
    [
        (
            (4,),
            [
                ("n3", "n1", "flow", "link"),
                ("n3", "n0", "flow", "Approve"),
                ("n1", "n3", "flow", "a somewhat longer relation label"),
            ],
            [("e1", "e2")],
        ),
        (
            (3, 4),
            [
                ("n6", "n3", "flow", "a somewhat longer relation label"),
                ("n0", "n6", "flow", "a somewhat longer relation label"),
                ("n1", "n2", "flow", "a somewhat longer relation label"),
            ],
            [("e2", "e0"), ("e1", "e0")],
        ),
        (
            (3, 3),
            [
                ("n1", "n5", "flow", "a somewhat longer relation label"),
                ("n1", "n2", "flow", "a somewhat longer relation label"),
                ("n4", "n2", "flow", "link"),
            ],
            [("e2", "e0"), ("e2", "e1"), ("e0", "e2")],
        ),
    ],
)
def test_pr205_p2_repacked_target_path_and_label_remain_separate(
    group_sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    crossings: list[tuple[str, str]],
) -> None:
    """Current route and label pack must clear actual foreign SVG strokes."""
    raw = _p2_feedback_geometry_model(group_sizes)
    edges = [
        {"id": f"e{i}", "from": start, "to": end,
         "kind": kind, "label": label}
        for i, (start, end, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        for path_id, label_id in crossings:
            assert _p2_linear_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id
            )
            assert _p2_cubic_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id
            )
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("group_sizes", "relations", "path_id", "label_id"),
    [
        (
            (3, 4),
            [
                ("n4", "n6", "flow", "a somewhat longer relation label"),
                ("n2", "n4", "flow", "link"),
                ("n5", "n1", "risk", "a somewhat longer relation label"),
            ],
            "e0", "e1",
        ),
        (
            (3, 3),
            [
                ("n3", "n2", "flow", "Approve"),
                ("n2", "n0", "flow", "link"),
                ("n5", "n1", "risk", "a somewhat longer relation label"),
            ],
            "e0", "e2",
        ),
        (
            (3, 3),
            [
                ("n0", "n2", "flow", "Approve"),
                ("n4", "n4", "risk", "link"),
                ("n3", "n1", "risk", "link"),
            ],
            "e1", "e0",
        ),
        (
            (2, 2),
            [
                ("n3", "n2", "risk", "Approve"),
                ("n1", "n1", "flow", "a somewhat longer relation label"),
                ("n3", "n3", "risk", "link"),
                ("n2", "n1", "flow", "a somewhat longer relation label"),
            ],
            "e3", "e0",
        ),
    ],
)
def test_pr205_p2_reviewed_return_clears_actual_foreign_label(
    group_sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    path_id: str,
    label_id: str,
) -> None:
    """No packed label may conceal a rendered endpoint, return, or self-loop."""
    raw = _p2_feedback_geometry_model(group_sizes)
    edges = [
        {"id": f"e{i}", "from": start, "to": end,
         "kind": kind, "label": label}
        for i, (start, end, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(
            paths[path_id], labels[label_id]
        ), (path_id, label_id, paths[path_id], labels[label_id])
        assert _p2_cubic_path_clears_box(
            paths[path_id], labels[label_id]
        ), (path_id, label_id, paths[path_id], labels[label_id])
        if group_sizes == (2, 2) and path_id == "e3":
            # The same saturated row gap also contains both fixed self-loops.
            for loop_id in ("e1", "e2"):
                assert _p2_linear_path_clears_box(
                    paths[path_id], labels[loop_id]
                ), (path_id, loop_id)
                assert _p2_cubic_path_clears_box(
                    paths[path_id], labels[loop_id]
                ), (path_id, loop_id)
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_p2_same_row_multi_group_curve_clears_intermediate_card() -> None:
    """A same-row cubic must not tunnel through a third group's process card."""
    raw = _p2_feedback_geometry_model((2, 3, 4))
    edges = [
        {"id": "e0", "from": "n7", "to": "n8",
         "kind": "flow", "label": "Approve"},
        {"id": "e1", "from": "n2", "to": "n4",
         "kind": "risk", "label": "a somewhat longer relation label"},
        {"id": "e2", "from": "n1", "to": "n6",
         "kind": "flow", "label": "link"},
        {"id": "e3", "from": "n6", "to": "n2",
         "kind": "flow", "label": "a somewhat longer relation label"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, boxes = _edge_paths(root), _node_boxes(root)
        assert _p2_linear_path_clears_box(
            paths["e2"], boxes["n3"]
        ), (paths["e2"], boxes["n3"])
        assert _p2_cubic_path_clears_box(
            paths["e2"], boxes["n3"]
        ), (paths["e2"], boxes["n3"])
        label_boxes = _edge_label_boxes(root)
        for foreign_edge in ("e1", "e3"):
            assert _p2_linear_path_clears_box(
                paths[foreign_edge], label_boxes["e2"]
            ), (foreign_edge, paths[foreign_edge], label_boxes["e2"])
            assert _p2_cubic_path_clears_box(
                paths[foreign_edge], label_boxes["e2"]
            ), (foreign_edge, paths[foreign_edge], label_boxes["e2"])
        return paths, boxes, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_review_same_row_card_detour_clears_selfloop_label() -> None:
    """A detour around a third card cannot replace it with a label collision."""
    raw = _p2_feedback_geometry_model((3, 3, 3))
    edges = [
        {"id": "detour", "from": "n1", "to": "n7",
         "kind": "flow", "label": "Approve"},
        {"id": "loop", "from": "n1", "to": "n1",
         "kind": "flow", "label": "a somewhat longer relation label"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(
            paths["detour"], labels["loop"]
        ), (paths["detour"], labels["loop"])
        assert _p2_cubic_path_clears_box(
            paths["detour"], labels["loop"]
        ), (paths["detour"], labels["loop"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_review_repacked_vertical_keeps_other_source_leg_clear() -> None:
    """When a vertical label moves, a shared source rail needs its new box."""
    raw = _p2_feedback_geometry_model((3, 4))
    edges = [
        {"id": "return", "from": "n2", "to": "n3",
         "kind": "risk", "label": "link"},
        {"id": "peer", "from": "n2", "to": "n5",
         "kind": "flow", "label": "Approve"},
        {"id": "vertical", "from": "n3", "to": "n6",
         "kind": "risk", "label": "a somewhat longer relation label"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(
            paths["return"], labels["peer"]
        ), (paths["return"], labels["peer"])
        assert _p2_cubic_path_clears_box(
            paths["return"], labels["peer"]
        ), (paths["return"], labels["peer"])
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("sizes", "relations", "route_id", "label_id"),
    [
        (
            (4, 4, 4, 4),
            [
                ("n10", "n0", "flow", "Approve"),
                ("n12", "n9", "feedback", "a somewhat longer relation label"),
                ("n9", "n8", "flow", "a somewhat longer relation label"),
                ("n0", "n2", "flow", "link"),
                ("n2", "n6", "risk", "link"),
            ],
            "e0", "e2",
        ),
        (
            (4, 4, 4),
            [
                ("n1", "n6", "flow", "a somewhat longer relation label"),
                ("n0", "n11", "flow", "a somewhat longer relation label"),
                ("n11", "n4", "flow", "Approve"),
                ("n11", "n7", "flow", "a somewhat longer relation label"),
            ],
            "e0", "e1",
        ),
    ],
)
def test_pr205_p2_differential_outer_label_clears_foreign_return(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    route_id: str,
    label_id: str,
) -> None:
    """Global long returns may not conceal packed process labels."""
    raw = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def layout(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, boxes = _edge_paths(root), _edge_label_boxes(root)
        assert _p2_linear_path_clears_box(
            paths[route_id], boxes[label_id]
        ), (route_id, label_id, paths[route_id], boxes[label_id])
        assert _p2_cubic_path_clears_box(
            paths[route_id], boxes[label_id]
        ), (route_id, label_id, paths[route_id], boxes[label_id])
        return paths, boxes, root.attrib["viewBox"]

    assert layout(edges) == layout(list(reversed(edges)))


@pytest.mark.parametrize(
    ("sizes", "relations", "expected"),
    [
        (
            (2, 3, 4),
            [
                ("n3", "n6", "flow", "a somewhat longer relation label"),
                ("n8", "n2", "risk", "link"),
                ("n8", "n0", "flow", "Approve"),
            ],
            ("label-pair", "e1", "e2"),
        ),
        (
            (3, 3),
            [
                ("n2", "n0", "flow", "Approve"),
                ("n2", "n2", "flow", "short relation"),
                ("n5", "n2", "risk", "link"),
            ],
            ("path-label", "e2", "e1"),
        ),
        (
            (3, 3),
            [
                ("n4", "n2", "flow", "short relation"),
                ("n0", "n5", "flow", "Approve"),
                ("n2", "n0", "flow", "a somewhat longer relation label"),
            ],
            ("path-label", "e1", "e2"),
        ),
    ],
)
def test_pr205_review_actual_outer_labels_and_fallback_strokes_clear(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    expected: tuple[str, str, str],
) -> None:
    """No fallback rail may hide a fixed label or collapse two packed labels."""
    raw = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, boxes = _edge_paths(root), _edge_label_boxes(root)
        mode, first, second = expected
        if mode == "label-pair":
            left, top, width, height = boxes[first]
            other_left, other_top, other_width, other_height = boxes[second]
            assert (
                left >= other_left + other_width
                or other_left >= left + width
                or top >= other_top + other_height
                or other_top >= top + height
            ), (first, boxes[first], second, boxes[second])
        else:
            assert _p2_linear_path_clears_box(
                paths[first], boxes[second]
            ), (first, second, paths[first], boxes[second])
            assert _p2_cubic_path_clears_box(
                paths[first], boxes[second]
            ), (first, second, paths[first], boxes[second])
        return paths, boxes, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("sizes", "relations", "crossings"),
    [
        (
            (3, 3),
            [
                ('n2', 'n0', 'flow', 'a somewhat longer relation label'),
                ('n5', 'n1', 'flow', 'a somewhat longer relation label'),
                ('n5', 'n3', 'risk', 'a somewhat longer relation label'),
                ('n5', 'n3', 'risk', 'link'),
                ('n5', 'n2', 'feedback', 'Approve'),
            ],
            [
                ('e2', 'e0'),
                ('e3', 'e0'),
            ],
        ),
        (
            (4, 4, 4, 3),
            [
                ('n4', 'n7', 'flow', 'a somewhat longer relation label'),
                ('n5', 'n3', 'flow', 'a somewhat longer relation label'),
                ('n3', 'n8', 'flow', 'Approve'),
                ('n4', 'n5', 'risk', 'a somewhat longer relation label'),
                ('n6', 'n8', 'feedback', 'link'),
            ],
            [
                ('e0', 'e2'),
            ],
        ),
        (
            (4, 2),
            [
                ('n1', 'n0', 'flow', 'a somewhat longer relation label'),
                ('n3', 'n5', 'flow', 'a somewhat longer relation label'),
                ('n0', 'n3', 'flow', 'link'),
                ('n5', 'n3', 'risk', 'link'),
                ('n3', 'n2', 'risk', 'a somewhat longer relation label'),
            ],
            [
                ('e2', 'e3'),
            ],
        ),
        (
            (3, 3, 2),
            [
                ('n5', 'n5', 'flow', 'link'),
                ('n5', 'n4', 'risk', 'Approve'),
                ('n4', 'n4', 'risk', 'a somewhat longer relation label'),
                ('n2', 'n5', 'risk', 'a somewhat longer relation label'),
                ('n5', 'n6', 'flow', 'Approve'),
            ],
            [
                ('e4', 'e1'),
            ],
        ),
        (
            (2, 3, 4, 2),
            [
                ('n10', 'n3', 'feedback', 'Approve'),
                ('n3', 'n4', 'risk', 'link'),
                ('n0', 'n7', 'risk', 'link'),
                ('n7', 'n5', 'flow', 'link'),
                ('n4', 'n10', 'flow', 'Approve'),
            ],
            [
                ('e2', 'e4'),
                ('e3', 'e4'),
            ],
        ),
        (
            (3, 4, 4, 4),
            [
                ('n13', 'n4', 'flow', 'link'),
                ('n8', 'n10', 'flow', 'a somewhat longer relation label'),
                ('n6', 'n14', 'feedback', 'a somewhat longer relation label'),
                ('n11', 'n9', 'flow', 'link'),
            ],
            [
                ('e1', 'e0'),
                ('e3', 'e0'),
            ],
        ),
        (
            (3, 2, 2),
            [
                ('n1', 'n4', 'risk', 'a somewhat longer relation label'),
                ('n3', 'n3', 'feedback', 'a somewhat longer relation label'),
                ('n4', 'n3', 'flow', 'link'),
                ('n3', 'n2', 'flow', 'a somewhat longer relation label'),
                ('n2', 'n0', 'risk', 'link'),
            ],
            [
                ('e3', 'e2'),
            ],
        ),
    ],
)
def test_pr205_p2_seed20_full_label_path_clearance(
    sizes: list[int],
    relations: list[list[str]],
    crossings: list[list[str]],
) -> None:
    """An unchanged or repacked route must not cross a foreign process label."""
    raw = _p2_feedback_geometry_model(tuple(sizes))
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        for path_id, label_id in crossings:
            assert _p2_linear_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id, paths[path_id], labels[label_id]
            )
            assert _p2_cubic_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id, paths[path_id], labels[label_id]
            )
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))


@pytest.mark.parametrize(
    ("sizes", "relations", "obstacles"),
    [
        (
            (3, 3, 3),
            [
                ("n2", "n8", "flow", "Approve"),
                ("n2", "n3", "flow", "short relation"),
                ("n3", "n5", "flow", "a somewhat longer relation label"),
                ("n5", "n2", "flow", "link"),
            ],
            [("card", "e0", "n5")],
        ),
        (
            (2, 3, 4),
            [
                ("n1", "n6", "flow", "a somewhat longer relation label"),
                ("n0", "n4", "risk", "Approve"),
                ("n5", "n7", "flow", "short relation"),
                ("n4", "n2", "risk", "link"),
            ],
            [("label", "e1", "e0"), ("label", "e1", "e2")],
        ),
        (
            (3, 4),
            [
                ("n3", "n2", "flow", "link"),
                ("n2", "n0", "flow", "link"),
                ("n2", "n1", "risk", "a somewhat longer relation label"),
                ("n6", "n0", "risk", "link"),
            ],
            [("label", "e1", "e0")],
        ),
    ],
)
def test_pr205_review_unsupported_card_and_synthetic_long_gutter_clearance(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
    obstacles: list[tuple[str, str, str]],
) -> None:
    """Real routes must stay clear when a row-gap plan or label-only pack saturates."""
    model = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]

    def layout(ordered: list[dict]) -> tuple[dict, dict, str]:
        candidate = copy.deepcopy(model)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths = _edge_paths(root)
        labels = _edge_label_boxes(root)
        cards = _node_boxes(root)
        for box_kind, path_id, box_id in obstacles:
            box = (cards if box_kind == "card" else labels)[box_id]
            assert _p2_linear_path_clears_box(paths[path_id], box), (
                box_kind, path_id, box_id, paths[path_id], box
            )
            assert _p2_cubic_path_clears_box(paths[path_id], box), (
                box_kind, path_id, box_id, paths[path_id], box
            )
        return paths, labels, root.attrib["viewBox"]

    assert layout(edges) == layout(list(reversed(edges)))

@pytest.mark.parametrize(
    ("sizes", "relations"),
    [
        (
            (3, 2, 2),
            [
                ("n4", "n5", "risk", "link"),
                ("n1", "n6", "flow", "Approve"),
                ("n4", "n4", "feedback", "Approve"),
                ("n6", "n5", "flow", "link"),
                ("n2", "n5", "risk", "a somewhat longer relation label"),
            ],
        ),
        (
            (3, 4, 3),
            [
                ("n0", "n9", "flow", "a somewhat longer relation label"),
                ("n3", "n7", "feedback", "a somewhat longer relation label"),
                ("n2", "n9", "flow", "Approve"),
                ("n3", "n2", "flow", "Approve"),
                ("n1", "n8", "flow", "Approve"),
            ],
        ),
        (
            (4, 4, 4, 4),
            [
                ("n3", "n11", "risk", "link"),
                ("n6", "n12", "flow", "a somewhat longer relation label"),
                ("n4", "n3", "risk", "Approve"),
            ],
        ),
        (
            (3, 3, 4, 4),
            [
                ("n2", "n12", "flow", "link"),
                ("n0", "n13", "flow", "link"),
                ("n1", "n9", "flow", "a somewhat longer relation label"),
                ("n10", "n10", "flow", "Approve"),
            ],
        ),
    ],
)
def test_pr205_p2_failclosed_same_row_card_routes(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
) -> None:
    """An exhausted same-row detour must render without crossing foreign geometry."""
    raw = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{index}", "from": source, "to": target,
         "kind": kind, "label": label}
        for index, (source, target, kind, label) in enumerate(relations)
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, str]:
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(model))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        for edge in edges:
            edge_id = edge["id"]
            if edge["from"] == edge["to"]:
                continue
            for node_id, box in cards.items():
                if node_id in {edge["from"], edge["to"]}:
                    continue
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    "card", edge_id, node_id, paths[edge_id], box
                )
                assert _p2_cubic_path_clears_box(paths[edge_id], box), (
                    "card", edge_id, node_id, paths[edge_id], box
                )
            for other_id, box in labels.items():
                if other_id == edge_id:
                    continue
                assert _p2_linear_path_clears_box(paths[edge_id], box), (
                    "label", edge_id, other_id, paths[edge_id], box
                )
                assert _p2_cubic_path_clears_box(paths[edge_id], box), (
                    "label", edge_id, other_id, paths[edge_id], box
                )
        return paths, labels, root.attrib["viewBox"]

    assert geometry(edges) == geometry(list(reversed(edges)))

def test_pr205_codex_first_row_cross_card_uses_safe_detour() -> None:
    """Even the first process row cannot send a curve through an intervening card."""
    raw = _p2_feedback_geometry_model((2, 2, 2))
    raw["edges"] = [
        {"id": "e0", "from": "n0", "to": "n4",
         "kind": "flow", "label": "link"},
    ]
    root = _parse(render_native_diagram(raw))
    path = _edge_paths(root)["e0"]
    intermediate_card = _node_boxes(root)["n2"]
    assert _p2_linear_path_clears_box(path, intermediate_card), path
    assert _p2_cubic_path_clears_box(path, intermediate_card), path
    assert "process-row-card-detour" in [
        node.attrib.get("data-route", "")
        for node in root if node.attrib.get("data-source-kind") == "edge"
    ]


def test_pr205_codex_same_row_card_detour_stabilizes_paint_order() -> None:
    """Foreign-stroke crossings created by a detour must paint in stable ID order."""
    raw = _p2_feedback_geometry_model((2, 3, 4))
    edges = [
        {"id": "e0", "from": "n7", "to": "n8",
         "kind": "flow", "label": "Approve"},
        {"id": "e1", "from": "n2", "to": "n4",
         "kind": "risk", "label": "a somewhat longer relation label"},
        {"id": "e2", "from": "n1", "to": "n6",
         "kind": "flow", "label": "link"},
        {"id": "e3", "from": "n6", "to": "n2",
         "kind": "flow", "label": "a somewhat longer relation label"},
    ]

    def geometry(ordered: list[dict]) -> tuple[list[str], dict, dict]:
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(model))
        paths = _edge_paths(root)
        labels = _edge_label_boxes(root)
        cards = _node_boxes(root)
        painted = [
            node.attrib["data-source-id"]
            for node in root if node.attrib.get("data-source-kind") == "edge"
        ]
        assert any(
            node.attrib.get("data-source-id") == "e2"
            and node.attrib.get("data-route") == "process-row-card-detour"
            for node in root
        )
        for box_id, box in cards.items():
            if box_id not in {"n1", "n6"}:
                assert _p2_linear_path_clears_box(paths["e2"], box), box_id
                assert _p2_cubic_path_clears_box(paths["e2"], box), box_id
        for edge_id, box in labels.items():
            if edge_id != "e2":
                assert _p2_linear_path_clears_box(paths["e2"], box), edge_id
                assert _p2_cubic_path_clears_box(paths["e2"], box), edge_id
        return painted, paths, labels

    assert geometry(edges) == geometry(list(reversed(edges)))

@pytest.mark.parametrize(
    ("sizes", "relations"),
    [
        (
            (3, 4, 3),
            [
                ("n3", "n9", "risk", "a somewhat longer relation label"),
                ("n8", "n1", "flow", "Approve"),
                ("n6", "n8", "flow", "a somewhat longer relation label"),
                ("n7", "n0", "flow", "link"),
            ],
        ),
        (
            (3, 2, 4, 3),
            [
                ("n5", "n7", "risk", "a somewhat longer relation label"),
                ("n6", "n11", "risk", "a somewhat longer relation label"),
                ("n5", "n0", "flow", "link"),
            ],
        ),
        (
            (2, 4, 3, 3),
            [
                ("n0", "n11", "flow", "a somewhat longer relation label"),
                ("n9", "n2", "flow", "a somewhat longer relation label"),
            ],
        ),
        (
            (2, 3, 2),
            [
                ("n2", "n5", "feedback", "a somewhat longer relation label"),
                ("n0", "n4", "flow", "a somewhat longer relation label"),
                ("n2", "n1", "flow", "a somewhat longer relation label"),
                ("n5", "n0", "flow", "Approve"),
                ("n1", "n0", "flow", "a somewhat longer relation label"),
            ],
        ),
    ],
)
def test_pr205_codex_first_row_differential_failures(
    sizes: tuple[int, ...],
    relations: list[tuple[str, str, str, str]],
) -> None:
    """Previously renderable valid first-row routes must not become exceptions."""
    raw = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]
    for ordering in (edges, list(reversed(edges))):
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(ordering)
        root = _parse(render_native_diagram(model))
        assert len(_edge_paths(root)) == len(edges)


def test_pr205_codex_first_row_differential_label_clearance() -> None:
    """First-row reroutes cannot newly obscure another edge's physical label."""
    model = _p2_feedback_geometry_model((2, 2, 4, 3))
    edges = [
        ("n7", "n2", "flow", "link"),
        ("n0", "n5", "flow", "link"),
        ("n10", "n0", "risk", "link"),
        ("n1", "n2", "flow", "link"),
        ("n8", "n0", "risk", "Approve"),
    ]
    model["edges"] = [
        {"id": f"e{i}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(edges)
    ]
    for ordering in (model["edges"], list(reversed(model["edges"]))):
        candidate = copy.deepcopy(model)
        candidate["edges"] = copy.deepcopy(ordering)
        root = _parse(render_native_diagram(candidate))
        paths, labels = _edge_paths(root), _edge_label_boxes(root)
        for path_id, label_id in (("e0", "e1"), ("e3", "e1")):
            assert _p2_linear_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id, paths[path_id], labels[label_id]
            )
            assert _p2_cubic_path_clears_box(paths[path_id], labels[label_id]), (
                path_id, label_id, paths[path_id], labels[label_id]
            )

@pytest.mark.parametrize("label", ("link", "a somewhat longer relation label"))
def test_pr205_first_row_label_stays_in_intergroup_gap(label: str) -> None:
    """A safe first-row detour must not abandon its label beyond the final group."""
    model = _p2_feedback_geometry_model((2, 2, 2))
    model["edges"] = [
        {"id": "e0", "from": "n0", "to": "n4",
         "kind": "flow", "label": label},
    ]
    root = _parse(render_native_diagram(model))
    path = _edge_paths(root)["e0"]
    cards = _node_boxes(root)
    left, top, width, height = _edge_label_boxes(root)["e0"]
    assert path.startswith("M ") and " L " in path
    gap_0 = (cards["n0"][0] + cards["n0"][2], cards["n2"][0])
    gap_1 = (cards["n2"][0] + cards["n2"][2], cards["n4"][0])
    assert any(
        gap_left + 4 <= left and left + width <= gap_right - 4
        for gap_left, gap_right in (gap_0, gap_1)
    ), (label, path, (left, top, width, height), (gap_0, gap_1))
    for node_id, box in cards.items():
        if node_id not in {"n0", "n4"}:
            assert _p2_linear_path_clears_box(path, box), node_id
            assert _p2_cubic_path_clears_box(path, box), node_id


def test_pr205_codex_first_row_detours_reserve_distinct_rails() -> None:
    """A second first-row card detour must not hide a peer's horizontal stroke."""
    raw = _p2_feedback_geometry_model((2, 2, 2, 2, 2))
    edges = [
        {"id": "e0", "from": "n0", "to": "n4", "kind": "flow", "label": "x"},
        {"id": "e1", "from": "n2", "to": "n8", "kind": "risk", "label": "x"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, list[str]]:
        candidate = copy.deepcopy(raw)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        horizontal = {}
        for edge in edges:
            edge_id = edge["id"]
            horizontal[edge_id] = [
                (min(start[0], end[0]), max(start[0], end[0]), start[1])
                for start, end in _p2_orthogonal_segments(paths[edge_id])
                if abs(start[1] - end[1]) < 0.01
                and abs(start[0] - end[0]) > 4
            ]
            for card_id, box in cards.items():
                if card_id not in {edge["from"], edge["to"]}:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, card_id
                    )
            for peer_id, box in labels.items():
                if peer_id != edge_id:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, peer_id
                    )
        assert horizontal["e0"] and horizontal["e1"]
        for x0, x1, y in horizontal["e0"]:
            for xx0, xx1, yy in horizontal["e1"]:
                overlap = min(x1, xx1) - max(x0, xx0)
                assert overlap <= 4 or abs(y - yy) >= 4, (
                    "overlapping first-row rails", paths, overlap, y, yy
                )
        painted = [
            item.attrib["data-source-id"] for item in root
            if item.attrib.get("data-source-kind") == "edge"
        ]
        return paths, labels, painted

    assert geometry(edges) == geometry(list(reversed(edges)))


def test_pr205_codex_card_detour_does_not_cover_preplanned_gutter_rail() -> None:
    """A first-row rescue must preserve visible strokes from earlier planners."""
    model = _p2_feedback_geometry_model((2, 3, 4, 2, 4, 2))
    edges = [
        {"id": "e0", "from": "n2", "to": "n11", "kind": "risk",
         "label": "a somewhat longer relation label"},
        {"id": "e4", "from": "n9", "to": "n15", "kind": "flow", "label": "x"},
        {"id": "e5", "from": "n11", "to": "n0", "kind": "flow", "label": "Approve"},
    ]

    def readback(ordered: list[dict]) -> tuple[dict, dict, list[str]]:
        candidate = copy.deepcopy(model)
        candidate["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(candidate))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        rails = {}
        for edge_id in ("e0", "e4"):
            rails[edge_id] = [
                (min(start[0], end[0]), max(start[0], end[0]), start[1])
                for start, end in _p2_orthogonal_segments(paths[edge_id])
                if abs(start[1] - end[1]) < 0.01
                and abs(start[0] - end[0]) > 4
            ]
        assert rails["e0"] and rails["e4"]
        for a, b, y in rails["e0"]:
            for c, d, yy in rails["e4"]:
                shared = min(b, d) - max(a, c)
                assert shared <= 4 or abs(y - yy) >= 4, (
                    "detour masked preplanned gutter", shared, paths
                )
        for edge in edges:
            eid = edge["id"]
            for node_id, card in cards.items():
                if node_id not in (edge["from"], edge["to"]):
                    assert _p2_linear_path_clears_box(paths[eid], card), (eid, node_id)
            for peer_id, box in labels.items():
                if peer_id != eid:
                    assert _p2_linear_path_clears_box(paths[eid], box), (eid, peer_id)
        painted = [
            element.attrib["data-source-id"] for element in root
            if element.attrib.get("data-source-kind") == "edge"
        ]
        return paths, labels, painted

    assert readback(edges) == readback(list(reversed(edges)))


def test_pr204_p2_distinct_local_feedback_pairs_keep_separate_physical_rails() -> None:
    """Different feedback endpoints must not hide on one same-row return stroke."""
    raw = _p2_feedback_geometry_model((3, 4))
    edges = [
        {"id": "f0", "from": "n3", "to": "n1",
         "kind": "feedback", "label": "Rueckmeldung"},
        {"id": "f1", "from": "n4", "to": "n0",
         "kind": "feedback", "label": "x"},
    ]

    def geometry(ordered: list[dict]) -> tuple[dict, dict, list[str]]:
        model = copy.deepcopy(raw)
        model["edges"] = copy.deepcopy(ordered)
        root = _parse(render_native_diagram(model))
        paths, labels, cards = (
            _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
        )
        rails = {}
        for edge in edges:
            edge_id = edge["id"]
            rails[edge_id] = [
                (min(start[0], end[0]), max(start[0], end[0]), start[1])
                for start, end in _p2_orthogonal_segments(paths[edge_id])
                if abs(start[1] - end[1]) < 0.01
                and abs(start[0] - end[0]) > 4
            ]
            for node_id, card in cards.items():
                if node_id not in {edge["from"], edge["to"]}:
                    assert _p2_linear_path_clears_box(paths[edge_id], card), (
                        edge_id, node_id
                    )
            for peer_id, box in labels.items():
                if edge_id != peer_id:
                    assert _p2_linear_path_clears_box(paths[edge_id], box), (
                        edge_id, peer_id
                    )
        assert rails["f0"] and rails["f1"]
        for left, right, y in rails["f0"]:
            for other_left, other_right, other_y in rails["f1"]:
                overlap = min(right, other_right) - max(left, other_left)
                assert overlap <= 4 or abs(y - other_y) >= 4, (
                    "semantic feedback peer strokes overlap", paths, overlap
                )
        painted = [
            element.attrib["data-source-id"]
            for element in root
            if element.attrib.get("data-source-kind") == "edge"
        ]
        return paths, labels, painted

    assert geometry(edges) == geometry(list(reversed(edges)))

def _pr205_assert_distinct_horizontal_strokes(
    paths: dict[str, str], first: str, second: str
) -> None:
    """An overpainted physical stroke cannot represent two different relations."""
    def rails(edge_id: str) -> list[tuple[float, float, float]]:
        return [
            (min(start[0], end[0]), max(start[0], end[0]), start[1])
            for start, end in _p2_orthogonal_segments(paths[edge_id])
            if abs(start[1] - end[1]) < 0.01
            and abs(start[0] - end[0]) > 4
        ]

    assert rails(first) and rails(second)
    for left, right, y in rails(first):
        for other_left, other_right, other_y in rails(second):
            overlap = min(right, other_right) - max(left, other_left)
            assert overlap <= 4 or abs(y - other_y) >= 4, (
                first, second, "hidden semantic feedback stroke", overlap,
                y, other_y, paths
            )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_codex_preplanned_same_row_feedback_stroke_reserved(
    reversed_order: bool,
) -> None:
    """A fixed same-row rail must block subsequent grouped feedback replans."""
    raw = _p2_feedback_geometry_model((2, 3, 4))
    edges = [
        {"id": "e00", "from": "n0", "to": "n4",
         "kind": "feedback", "label": "Rueckmeldung"},
        {"id": "e01", "from": "n4", "to": "n0",
         "kind": "feedback", "label": "Rueckmeldung"},
        {"id": "e02", "from": "n4", "to": "n1",
         "kind": "feedback", "label": "Pruefung und Rueckmeldung"},
        {"id": "e03", "from": "n3", "to": "n4",
         "kind": "feedback", "label": "x"},
        {"id": "e07", "from": "n1", "to": "n6",
         "kind": "feedback", "label": "Langes Label"},
        {"id": "loop", "from": "n7", "to": "n7",
         "kind": "risk", "label": "Langes Label"},
    ]
    raw["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(raw)))
    _pr205_assert_distinct_horizontal_strokes(paths, "e03", "e07")


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_codex_feedback_rail_search_exhaustion_is_safe(
    reversed_order: bool,
) -> None:
    """Fourteen competing feedbacks must not silently reuse a rejected rail."""
    raw = _p2_feedback_geometry_model((2,) * 14)
    edges = [
        {"id": f"e{index:02d}", "from": f"n{2 * index}",
         "to": f"n{2 * (13 - index) + 1}",
         "kind": "feedback", "label": "x"}
        for index in range(14)
    ]
    raw["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(raw)))
    _pr205_assert_distinct_horizontal_strokes(paths, "e00", "e12")

@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_differential_feedback_outer_keeps_process_label_clear(
    reversed_order: bool,
) -> None:
    """Promoting peer feedbacks to outer paths cannot expose a flow-label collision."""
    raw = _p2_feedback_geometry_model((4, 3, 4))
    edges = [
        {"id": name, "from": source, "to": target,
         "kind": kind, "label": label}
        for name, source, target, kind, label in (
            ("f0", "n4", "n2", "feedback", "Rueckmeldung"),
            ("f1", "n4", "n5", "feedback", "link"),
            ("f2", "n2", "n0", "feedback", "Rueckmeldung"),
            ("f3", "n5", "n0", "feedback", "Rueckmeldung"),
            ("f4", "n3", "n8", "feedback", "Rueckmeldung"),
            ("f5", "n5", "n4", "feedback", "Rueckmeldung"),
            ("other0", "n0", "n8", "flow", "link"),
            ("other1", "n7", "n5", "risk", "link"),
            ("other2", "n4", "n6", "risk", "Approve"),
        )
    ]
    raw["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(raw))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert _p2_linear_path_clears_box(paths["other2"], labels["other0"])
    assert _p2_cubic_path_clears_box(paths["other2"], labels["other0"])


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_differential_feedback_selfloop_reserves_physical_rail(
    reversed_order: bool,
) -> None:
    """A fixed same-row feedback selfloop also occupies its actual horizontal rail."""
    raw = _p2_feedback_geometry_model((5, 2, 4))
    edges = [
        {"id": name, "from": source, "to": target,
         "kind": kind, "label": label}
        for name, source, target, kind, label in (
            ("f0", "n5", "n0", "feedback", "link"),
            ("f1", "n6", "n6", "feedback", "a somewhat longer relation label"),
            ("f2", "n2", "n7", "feedback", "x"),
            ("f3", "n5", "n10", "feedback", "x"),
            ("f4", "n9", "n5", "feedback", "link"),
            ("other0", "n5", "n5", "risk", "Approve"),
            ("other1", "n9", "n1", "risk", "Approve"),
            ("other2", "n9", "n1", "risk", "link"),
        )
    ]
    raw["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(raw)))
    _pr205_assert_distinct_horizontal_strokes(paths, "f1", "f2")

@pytest.mark.parametrize(
    ("sizes", "records", "pair"),
    [
        (
            (4, 5, 3, 3),
            [
                ("f0", "n5", "n13", "feedback", "Rueckmeldung"),
                ("f1", "n1", "n13", "feedback", "link"),
                ("f2", "n3", "n9", "feedback", "a somewhat longer relation label"),
                ("f3", "n8", "n0", "feedback", "Rueckmeldung"),
                ("other0", "n6", "n8", "risk", "a somewhat longer relation label"),
            ],
            ("f0", "f1"),
        ),
        (
            (5, 2, 3, 2, 2),
            [
                ("f0", "n5", "n12", "feedback", "link"),
                ("f1", "n12", "n5", "feedback", "link"),
                ("f2", "n10", "n4", "feedback", "Rueckmeldung"),
                ("f3", "n2", "n1", "feedback", "Rueckmeldung"),
                ("f4", "n13", "n3", "feedback", "Rueckmeldung"),
                ("f5", "n13", "n11", "feedback", "a somewhat longer relation label"),
                ("other0", "n10", "n8", "risk", "Approve"),
                ("other1", "n12", "n7", "risk", "a somewhat longer relation label"),
            ],
            ("f0", "f1"),
        ),
        (
            (5, 3, 3, 2, 4),
            [
                ("f0", "n11", "n8", "feedback", "a somewhat longer relation label"),
                ("f1", "n12", "n14", "feedback", "a somewhat longer relation label"),
                ("f2", "n3", "n8", "feedback", "Rueckmeldung"),
                ("f3", "n5", "n13", "feedback", "x"),
                ("f4", "n5", "n1", "feedback", "a somewhat longer relation label"),
                ("other0", "n7", "n3", "flow", "Approve"),
                ("other1", "n16", "n13", "flow", "link"),
            ],
            ("f0", "f3"),
        ),
        (
            (5, 3),
            [
                ("f0", "n6", "n6", "feedback", "link"),
                ("f1", "n5", "n3", "feedback", "a somewhat longer relation label"),
                ("f2", "n6", "n3", "feedback", "x"),
                ("f3", "n2", "n3", "feedback", "x"),
                ("f4", "n1", "n6", "feedback", "Rueckmeldung"),
                ("f5", "n4", "n7", "feedback", "x"),
                ("other0", "n4", "n4", "flow", "link"),
            ],
            ("f0", "f4"),
        ),
    ],
)
@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_grouped_fixed_same_row_feedback_rails_do_not_overpaint(
    sizes: tuple[int, ...],
    records: list[tuple[str, str, str, str, str]],
    pair: tuple[str, str],
    reversed_order: bool,
) -> None:
    """Fixed grouped feedback routes must account for *each other's* L strokes."""
    model = _p2_feedback_geometry_model(sizes)
    edges = [
        {"id": edge_id, "from": source, "to": target,
         "kind": kind, "label": label}
        for edge_id, source, target, kind, label in records
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))
    _pr205_assert_distinct_horizontal_strokes(paths, *pair)

@pytest.mark.parametrize(
    ("records", "pair"),
    [
        (
            [
                ("e00", "n12", "n2", "feedback", "link"),
                ("e03", "n6", "n12", "feedback", "x"),
                ("e07", "n11", "n8", "feedback", "x"),
                ("e01", "n11", "n0", "feedback", "a somewhat longer relation label"),
                ("e02", "n2", "n10", "feedback", "Rueckmeldung"),
                ("e05", "n2", "n0", "feedback", "link"),
            ],
            ("e00", "e07"),
        ),
        (
            [
                ("other1", "n6", "n4", "flow", "Approve"),
                ("other0", "n3", "n1", "risk", "Approve"),
                ("e06", "n0", "n4", "feedback", "Rueckmeldung"),
                ("e04", "n4", "n11", "feedback", "a somewhat longer relation label"),
                ("e01", "n10", "n0", "feedback", "Rueckmeldung"),
                ("e07", "n11", "n8", "feedback", "Rueckmeldung"),
                ("e03", "n6", "n12", "feedback", "a somewhat longer relation label"),
                ("e00", "n12", "n2", "feedback", "a somewhat longer relation label"),
            ],
            ("e03", "e04"),
        ),
        (
            [
                ("other1", "n9", "n4", "risk", "link"),
                ("other0", "n4", "n12", "risk", "a somewhat longer relation label"),
                ("e06", "n3", "n12", "feedback", "a somewhat longer relation label"),
                ("e02", "n10", "n10", "feedback", "link"),
                ("e01", "n9", "n3", "feedback", "x"),
                ("e07", "n11", "n8", "feedback", "Rueckmeldung"),
                ("e03", "n6", "n12", "feedback", "Rueckmeldung"),
                ("e00", "n12", "n2", "feedback", "a somewhat longer relation label"),
            ],
            ("e01", "e03"),
        ),
    ],
)
@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_codex_new_vertical_gutter_overlaps_are_reserved(
    records: list[tuple[str, str, str, str, str]],
    pair: tuple[str, str],
    reversed_order: bool,
) -> None:
    """Changing feedback rail y also changes its physical vertical gutter span."""
    model = _p2_feedback_geometry_model((4, 4, 5))
    edges = [
        {"id": edge_id, "from": source, "to": target,
         "kind": kind, "label": label}
        for edge_id, source, target, kind, label in records
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))

    def verticals(edge_id: str) -> list[tuple[float, float, float]]:
        return [
            (start[0], min(start[1], end[1]), max(start[1], end[1]))
            for start, end in _p2_orthogonal_segments(paths[edge_id])
            if abs(start[0] - end[0]) < 0.01
            and abs(start[1] - end[1]) > 4
        ]

    assert verticals(pair[0]) and verticals(pair[1])
    for first_x, first_low, first_high in verticals(pair[0]):
        for peer_x, peer_low, peer_high in verticals(pair[1]):
            overlap = min(first_high, peer_high) - max(first_low, peer_low)
            assert abs(first_x - peer_x) >= 4 or overlap <= 4, (
                "two feedback relations share a vertical physical stem",
                pair, first_x, peer_x, overlap, paths
            )

@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_codex_outer_footer_reserves_preplanned_local_vertical_feedback(
    reversed_order: bool,
) -> None:
    """Outer sideport gutters must not repaint already accepted local feedback stems."""
    model = _p2_feedback_geometry_model((3, 5, 7, 4))
    records = (
        ("e01", "n10", "n15", "feedback", "Rueckmeldung zur Planung"),
        ("e03", "n15", "n13", "feedback", "a somewhat longer relation label"),
        ("e04", "n11", "n17", "feedback", "x"),
        ("e09", "n14", "n8", "feedback", "Rueckmeldung zur Planung"),
        ("e10", "n11", "n17", "feedback", "Approve"),
        ("e11", "n12", "n15", "flow", "Approve"),
        ("e14", "n13", "n2", "flow", "Rueckmeldung zur Planung"),
        ("extra0", "n16", "n12", "feedback", "Rueckmeldung zur Planung"),
        ("extra1", "n12", "n17", "feedback", "long label"),
    )
    edges = [
        {"id": edge_id, "from": source, "to": target,
         "kind": kind, "label": label}
        for edge_id, source, target, kind, label in records
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))

    # Reproduced on 80f7334: outer e04 and local e09 both use x=1239
    # for 545px, despite safe horizontal feedback rails.
    assert " C " not in paths["e04"]  # outer-footer M/L route
    assert " C " in paths["e09"]  # still-local feedback route

    def verticals(edge_id: str) -> list[tuple[float, float, float]]:
        return [
            (start[0], min(start[1], end[1]), max(start[1], end[1]))
            for start, end in _p2_orthogonal_segments(paths[edge_id])
            if abs(start[0] - end[0]) < 0.01
            and abs(start[1] - end[1]) > 4
        ]

    assert verticals("e04") and verticals("e09")
    for outer_x, outer_low, outer_high in verticals("e04"):
        for local_x, local_low, local_high in verticals("e09"):
            overlap = min(outer_high, local_high) - max(outer_low, local_low)
            assert abs(outer_x - local_x) >= 4 or overlap <= 4, (
                "outer feedback route hides local semantic stem",
                outer_x, local_x, overlap, paths["e04"], paths["e09"],
            )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_codex_detour_target_port_reserves_preplanned_vertical_stroke(
    reversed_order: bool,
) -> None:
    """A same-row card detour must not mask a fixed peer's cubic target stem."""
    model = _p2_feedback_geometry_model((5, 5, 6, 2, 4))
    edges = [
        {"id": "e01", "from": "n8", "to": "n21",
         "kind": "risk", "label": "x"},
        {"id": "e04", "from": "n17", "to": "n21",
         "kind": "flow", "label": "x"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths = _edge_paths(root)

    def actual_vertical_strokes(
        path: str,
    ) -> list[tuple[float, float, float]]:
        tokens = re.findall(r"[MLC]|-?\d+(?:\.\d+)?", path)
        cursor: tuple[float, float] | None = None
        segments: list[tuple[float, float, float]] = []
        offset = 0
        while offset < len(tokens):
            command = tokens[offset]
            offset += 1
            arity = 6 if command == "C" else 2
            assert command in {"M", "L", "C"}
            coords = tuple(float(value) for value in tokens[offset:offset + arity])
            offset += arity
            endpoint = coords[-2], coords[-1]
            if cursor is not None:
                points = (
                    (cursor, endpoint) if command == "L" else (
                        (cursor, (coords[0], coords[1]),
                         (coords[2], coords[3]), endpoint)
                        if command == "C" else ()
                    )
                )
                if points and all(abs(point[0] - cursor[0]) < 0.01 for point in points):
                    ys = [point[1] for point in points]
                    if max(ys) - min(ys) > 0.0:
                        segments.append((cursor[0], min(ys), max(ys)))
            cursor = endpoint
        return segments

    detour_stems = actual_vertical_strokes(paths["e01"])
    peer_stems = actual_vertical_strokes(paths["e04"])
    assert detour_stems and peer_stems, paths
    for x, low, high in detour_stems:
        for other_x, other_low, other_high in peer_stems:
            physical_overlap = min(high, other_high) - max(low, other_low)
            assert abs(x - other_x) >= 4 or physical_overlap <= 0.0, (
                "preplanned target port physically obscured",
                x, other_x, physical_overlap, paths,
            )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_shared_target_row_gutter_and_branch_have_visible_target_stems(
    reversed_order: bool,
) -> None:
    """Two incoming relations must not share a long physical target-side stroke."""
    model = _p2_feedback_geometry_model((6, 3, 5))
    edges = [
        {"id": "e01", "from": "n3", "to": "n12",
         "kind": "risk", "label": "a somewhat longer relation label"},
        {"id": "e04", "from": "n7", "to": "n12",
         "kind": "flow", "label": "link"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))
    assert " C " not in paths["e01"] and " C " in paths["e04"]
    row = [
        (a[0], min(a[1], b[1]), max(a[1], b[1]))
        for a, b in _p2_orthogonal_segments(paths["e01"])
        if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) > 4
    ]
    branch_match = re.search(
        r"C ([-0-9.]+) ([-0-9.]+), ([-0-9.]+) ([-0-9.]+), "
        r"([-0-9.]+) ([-0-9.]+)$",
        paths["e04"],
    )
    assert branch_match is not None
    bx1, by1, bx2, by2, bx3, by3 = map(float, branch_match.groups())
    assert abs(bx1 - bx2) < 0.01 and abs(bx2 - bx3) < 0.01
    branch_low, branch_high = min(by1, by2, by3), max(by1, by2, by3)
    assert row
    for x, low, high in row:
        overlap = min(high, branch_high) - max(low, branch_low)
        assert abs(x - bx3) >= 4 or overlap <= 4, (
            "incoming target stem hides a second semantic edge",
            x, bx3, overlap, paths,
        )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_distinct_same_row_gutters_to_shared_target_keep_both_stems(
    reversed_order: bool,
) -> None:
    """Separate semantics entering one card must retain distinct physical top legs."""
    model = _p2_feedback_geometry_model((6, 6, 6))
    edges = [
        {"id": "e01", "from": "n0", "to": "n12",
         "kind": "risk", "label": "Approve"},
        {"id": "e04", "from": "n6", "to": "n12",
         "kind": "flow", "label": "x"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))
    assert all(" C " not in paths[k] for k in ("e01", "e04"))
    def physical_verticals(edge_id: str) -> list[tuple[float, float, float]]:
        return [
            (a[0], min(a[1], b[1]), max(a[1], b[1]))
            for a, b in _p2_orthogonal_segments(paths[edge_id])
            if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) > 4
        ]
    first, second = physical_verticals("e01"), physical_verticals("e04")
    assert first and second
    for x, lo, hi in first:
        for xx, low, high in second:
            overlap = min(hi, high) - max(lo, low)
            assert abs(x - xx) >= 4 or overlap <= 4, (
                "different semantic edges converge on same painted stem", overlap, paths,
            )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_distinct_shared_target_row_gutters_keep_horizontal_rails(
    reversed_order: bool,
) -> None:
    """Two distinct routes to one top port must not overwrite one horizontal rail."""
    model = _p2_feedback_geometry_model((6, 6, 6))
    edges = [
        {"id": "e01", "from": "n0", "to": "n12",
         "kind": "risk", "label": "Approve"},
        {"id": "e04", "from": "n6", "to": "n12",
         "kind": "flow", "label": "x"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))
    def rails(edge_id: str) -> list[tuple[float, float, float]]:
        return [
            (a[1], min(a[0], b[0]), max(a[0], b[0]))
            for a, b in _p2_orthogonal_segments(paths[edge_id])
            if abs(a[1] - b[1]) < 0.01 and abs(a[0] - b[0]) > 4
        ]
    assert rails("e01") and rails("e04")
    for y, left, right in rails("e01"):
        for yy, other_left, other_right in rails("e04"):
            overlap = min(right, other_right) - max(left, other_left)
            assert abs(y - yy) >= 4 or overlap <= 4, (
                "distinct row-gutter semantic rails physically overwrite",
                overlap, paths,
            )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_shared_target_process_branches_separate_cubic_target_stems(
    reversed_order: bool,
) -> None:
    """Different long branches entering one card cannot hide on a common C stem."""
    model = _p2_feedback_geometry_model((5, 4, 4, 3, 5))
    edges = [
        {"id": "e01", "from": "n8", "to": "n20",
         "kind": "risk", "label": "a somewhat longer relation label"},
        {"id": "e04", "from": "n15", "to": "n20",
         "kind": "flow", "label": "a somewhat longer relation label"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    paths = _edge_paths(_parse(render_native_diagram(model)))
    curves = []
    for eid in ("e01", "e04"):
        last = re.search(
            r"C ([-0-9.]+) ([-0-9.]+), ([-0-9.]+) ([-0-9.]+), "
            r"([-0-9.]+) ([-0-9.]+)$",
            paths[eid],
        )
        assert last, (eid, paths[eid])
        v = tuple(float(value) for value in last.groups())
        assert abs(v[0] - v[2]) < 0.01 and abs(v[2] - v[4]) < 0.01
        curves.append((v[4], min(v[1], v[3], v[5]), max(v[1], v[3], v[5])))
    (x1, low1, high1), (x2, low2, high2) = curves
    overlap = min(high1, high2) - max(low1, low2)
    assert abs(x1 - x2) >= 4 or overlap <= 4, (
        "incoming branch hides another target-side semantic C-stem", overlap, paths,
    )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_shared_target_branch_ports_preserve_foreign_label_clearance(
    reversed_order: bool,
) -> None:
    """Moving a shared branch entrance must not expose a previously clear label."""
    model = _p2_feedback_geometry_model((2, 3, 2, 2, 2))
    edges = [
        {"id": "extra2", "from": "n0", "to": "n10",
         "kind": "flow", "label": "Approve"},
        {"id": "extra1", "from": "n8", "to": "n6",
         "kind": "risk", "label": "Approve"},
        {"id": "extra0", "from": "n7", "to": "n3",
         "kind": "flow", "label": "Approve"},
        {"id": "e04", "from": "n7", "to": "n10",
         "kind": "flow", "label": "Approve"},
        {"id": "e01", "from": "n3", "to": "n10",
         "kind": "risk", "label": "link"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert _p2_linear_path_clears_box(paths["extra2"], labels["extra0"]), (
        "shared target replan crosses an existing unrelated label",
        paths["extra2"], labels["extra0"],
    )
    assert _p2_cubic_path_clears_box(paths["extra2"], labels["extra0"])


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_shared_target_port_preserves_earlier_foreign_label(
    reversed_order: bool,
) -> None:
    """A shifted incoming target port may not newly enter a peer label."""
    model = _p2_feedback_geometry_model((3, 3))
    edges = [
        {"id": "e0", "from": "n4", "to": "n5", "kind": "risk", "label": "Approve"},
        {"id": "e1", "from": "n3", "to": "n5", "kind": "flow", "label": "Approve"},
        {"id": "e2", "from": "n2", "to": "n1", "kind": "feedback", "label": "link"},
        {"id": "e3", "from": "n0", "to": "n5", "kind": "flow",
         "label": "a somewhat longer relation label"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert _p2_linear_path_clears_box(paths["e1"], labels["e0"])
    assert _p2_cubic_path_clears_box(paths["e1"], labels["e0"])


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr205_shared_target_port_keeps_unrelated_forward_label_clear(
    reversed_order: bool,
) -> None:
    """Moving a target C-stem must not obscure an unrelated same-row label."""
    model = _p2_feedback_geometry_model((4, 2))
    edges = [
        {"id": "e0", "from": "n3", "to": "n1", "kind": "flow", "label": "Approve"},
        {"id": "e1", "from": "n1", "to": "n4", "kind": "flow", "label": "Approve"},
        {"id": "e2", "from": "n1", "to": "n2", "kind": "flow", "label": "Approve"},
        {"id": "e3", "from": "n4", "to": "n2", "kind": "flow",
         "label": "a somewhat longer relation label"},
        {"id": "e4", "from": "n3", "to": "n4", "kind": "feedback", "label": "link"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert _p2_linear_path_clears_box(paths["e0"], labels["e2"])
    assert _p2_cubic_path_clears_box(paths["e0"], labels["e2"])



@pytest.mark.parametrize("reversed_order", [False, True])
@pytest.mark.parametrize("case", ["grouped", "with-feedback", "seeded-fuzz"])
def test_pr205_shared_target_ports_preserve_final_peer_labels(
    case: str, reversed_order: bool,
) -> None:
    """Shared-target C-stems must not obscure labels in the final rendered SVG."""
    cases = {
        "grouped": (
            (4, 4, 2),
            [
                {"id": "e0", "from": "n6", "to": "n3",
                 "kind": "risk", "label": "Approve"},
                {"id": "e1", "from": "n0", "to": "n3",
                 "kind": "flow", "label": "link"},
                {"id": "e2", "from": "n1", "to": "n2",
                 "kind": "risk", "label": "link"},
                {"id": "e3", "from": "n2", "to": "n7",
                 "kind": "flow", "label": "Approve"},
            ],
            "e0", "e3",
        ),
        "with-feedback": (
            (3, 2, 2),
            [
                {"id": "e0", "from": "n0", "to": "n6",
                 "kind": "risk", "label": "Approve"},
                {"id": "e1", "from": "n5", "to": "n6",
                 "kind": "flow", "label": "Approve"},
                {"id": "e2", "from": "n4", "to": "n4",
                 "kind": "feedback", "label": "Approve"},
                {"id": "e3", "from": "n2", "to": "n0",
                 "kind": "flow", "label": "link"},
                {"id": "e4", "from": "n3", "to": "n4",
                 "kind": "flow", "label": "Approve"},
            ],
            "e0", "e4",
        ),
        "seeded-fuzz": (
            (2, 3, 3, 3),
            [
                {"id": "e0", "from": "n3", "to": "n10",
                 "kind": "risk", "label": "link"},
                {"id": "e1", "from": "n9", "to": "n10",
                 "kind": "flow", "label": "link"},
                {"id": "e2", "from": "n8", "to": "n0",
                 "kind": "feedback", "label": "link"},
                {"id": "e3", "from": "n6", "to": "n7",
                 "kind": "risk", "label": "link"},
            ],
            "e0", "e3",
        ),
    }
    group_sizes, edges, crossing_edge, foreign_label = cases[case]
    model = _p2_feedback_geometry_model(group_sizes)
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert _p2_linear_path_clears_box(
        paths[crossing_edge], labels[foreign_label]
    ), (case, crossing_edge, foreign_label, paths)
    assert _p2_cubic_path_clears_box(
        paths[crossing_edge], labels[foreign_label]
    ), (case, crossing_edge, foreign_label, paths)

    model["edges"] = list(reversed(model["edges"]))
    reversed_root = _parse(render_native_diagram(model))
    assert (paths, labels) == (
        _edge_paths(reversed_root), _edge_label_boxes(reversed_root)
    )


@pytest.mark.parametrize("reverse_order", [False, True])
def test_pr206_codex_fixed_source_stem_remains_renderable(
    reverse_order: bool,
) -> None:
    """Fixed source stems must not exhaust a safe same-row card detour.

    The source entrance cannot move with the detour's target port. Reserving
    that fixed entrance as an avoidable new candidate rejected this valid
    four-edge process in both paint orders.
    """
    model = _p2_feedback_geometry_model((6, 4, 5, 3))
    edges = [
        {"id": "e00", "from": "n8", "to": "n17",
         "kind": "risk", "label": "Approve"},
        {"id": "e03", "from": "n13", "to": "n0",
         "kind": "risk", "label": "Approve"},
        {"id": "e05", "from": "n16", "to": "n9",
         "kind": "risk", "label": "link"},
        {"id": "e07", "from": "n7", "to": "n5",
         "kind": "flow", "label": "link"},
    ]
    model["edges"] = list(reversed(edges)) if reverse_order else edges
    root = _parse(render_native_diagram(model))
    paths = _edge_paths(root)
    labels = _edge_label_boxes(root)
    cards = _node_boxes(root)
    detour = paths["e00"]
    assert " L " in detour
    assert _p2_linear_path_clears_box(detour, labels["e03"])
    assert _p2_linear_path_clears_box(detour, labels["e05"])
    assert _p2_linear_path_clears_box(detour, labels["e07"])
    assert all(
        _p2_linear_path_clears_box(detour, box)
        for node_id, box in cards.items()
        if node_id not in {"n8", "n17"}
    )
    model["edges"] = list(reversed(model["edges"]))
    reversed_root = _parse(render_native_diagram(model))
    assert (paths, labels) == (
        _edge_paths(reversed_root), _edge_label_boxes(reversed_root)
    )


@pytest.mark.parametrize("reverse_order", [False, True])
def test_pr206_codex_fixed_source_stem_prefers_overlap_free_detour(
    reverse_order: bool,
) -> None:
    """When another gap is safe, do not share a physical source stem."""
    model = _p2_feedback_geometry_model((3, 4, 4, 6, 3))
    edges = [
        {"id": "e0", "from": "n18", "to": "n7",
         "kind": "risk", "label": "Approve"},
        {"id": "e1", "from": "n12", "to": "n7",
         "kind": "risk", "label": "Approve"},
        {"id": "e2", "from": "n14", "to": "n7",
         "kind": "flow", "label": "link"},
        {"id": "e3", "from": "n18", "to": "n1",
         "kind": "risk", "label": "Approve"},
    ]
    model["edges"] = list(reversed(edges)) if reverse_order else edges
    root = _parse(render_native_diagram(model))
    paths = _edge_paths(root)
    labels = _edge_label_boxes(root)
    # The other free row corridor leaves e0's x=2014 upper stem visible;
    # choosing the near/upper corridor would mask it.
    assert paths["e3"].startswith(
        "M 2014.0 580.0 L 2014.0 606.0 L 190.0 606.0"
    )
    model["edges"] = list(reversed(model["edges"]))
    reversed_root = _parse(render_native_diagram(model))
    assert (paths, labels) == (
        _edge_paths(reversed_root), _edge_label_boxes(reversed_root)
    )


@pytest.mark.parametrize("reverse_order", [False, True])
def test_pr206_codex_saturated_same_row_card_can_shift_source_port(
    reverse_order: bool,
) -> None:
    """A fixed center source port must not make a valid process unrenderable.

    The long preplanned peer label blocks the upper rail; a peer label and
    feedback stroke occupy the centered lower entrance. A safe alternate
    source-side card port and lower rail still exist for both input orders.
    """
    model = _p2_feedback_geometry_model((5, 2, 3, 5))
    edges = [
        {"id": "e0", "from": "n5", "to": "n12",
         "kind": "flow", "label": "a somewhat longer relation label"},
        {"id": "e1", "from": "n6", "to": "n11",
         "kind": "flow", "label": "x"},
        {"id": "e2", "from": "n9", "to": "n2",
         "kind": "risk", "label": "x"},
        {"id": "e3", "from": "n2", "to": "n6",
         "kind": "flow", "label": "x"},
    ]
    model["edges"] = list(reversed(edges)) if reverse_order else edges
    root = _parse(render_native_diagram(model))
    paths = _edge_paths(root)
    labels = _edge_label_boxes(root)
    cards = _node_boxes(root)
    assert len(paths) == len(edges)
    # n6 center x=646 is occupied; its available left port x=537 is not.
    assert paths["e1"].startswith("M 537.0 580.0 L 537.0 ")
    for node_id, card in cards.items():
        if node_id not in {"n6", "n11"}:
            assert _p2_linear_path_clears_box(paths["e1"], card), node_id
    for other_id, label in labels.items():
        if other_id != "e1":
            assert _p2_linear_path_clears_box(paths["e1"], label), other_id
    model["edges"] = list(reversed(model["edges"]))
    reversed_root = _parse(render_native_diagram(model))
    assert (paths, labels) == (
        _edge_paths(reversed_root), _edge_label_boxes(reversed_root)
    )


@pytest.mark.parametrize("label", ["link", "Approve"])
@pytest.mark.parametrize("reverse_order", [False, True])
def test_pr206_codex_three_group_saturation_finds_clear_side_gap(
    label: str, reverse_order: bool,
) -> None:
    """A valid grouped process needs its semantic relation even when row rails fill."""
    model = _p2_feedback_geometry_model((3, 3, 4))
    relations = (
        ("n3", "n1", "risk"),
        ("n3", "n2", "flow"),
        ("n5", "n8", "flow"),
        ("n8", "n0", "flow"),
        ("n7", "n1", "flow"),
        ("n8", "n3", "risk"),
        ("n2", "n8", "risk"),
    )
    edges = [
        {"id": f"e{i}", "from": a, "to": b, "kind": kind, "label": label}
        for i, (a, b, kind) in enumerate(relations)
    ]
    model["edges"] = list(reversed(edges)) if reverse_order else edges
    root = _parse(render_native_diagram(model))
    paths = _edge_paths(root)
    labels = _edge_label_boxes(root)
    cards = _node_boxes(root)
    assert len(paths) == len(relations)
    rerouted = paths["e4"]
    assert rerouted.startswith("M 977.0 497.0 L ")
    assert rerouted.endswith("L 315.0 497.0")
    assert any(
        item.attrib.get("data-source-id") == "e4"
        and item.attrib.get("data-route") == "process-row-card-side-detour"
        for item in root.iter()
    )
    for node_id, card in cards.items():
        if node_id not in {"n7", "n1"}:
            assert _p2_linear_path_clears_box(rerouted, card), node_id
    for edge_id, box in labels.items():
        assert _p2_linear_path_clears_box(rerouted, box), edge_id
    for edge_id, path in paths.items():
        if edge_id != "e4":
            assert _p2_linear_path_clears_box(path, labels["e4"]), edge_id
            assert _p2_cubic_path_clears_box(path, labels["e4"]), edge_id
    model["edges"] = list(reversed(model["edges"]))
    rerendered = _parse(render_native_diagram(model))
    assert (paths, labels) == (
        _edge_paths(rerendered), _edge_label_boxes(rerendered)
    )


def test_pr206_independent_p1_vertical_adjacent_gutter_handles_dual_y() -> None:
    """An explicit two-ordinate local gutter must not be formatted as a float."""
    from schauwerk.visual.native_diagram import _edge_geometry

    path, _, _, route = _edge_geometry(
        (65, 414),
        (65, 632),
        self_loop=False,
        lane=0,
        kind="flow",
        canvas_width=1848,
        canvas_height=1100,
        intent="process",
        process_branch_gutter_x=418.0,
        process_adjacent_route_y=(596.0, 616.0),
    )
    assert route == "process-row-gutter"
    assert path == (
        "M 190.0 580.0 L 190.0 596.0 L 418.0 596.0 "
        "L 418.0 616.0 L 190.0 616.0 L 190.0 632.0"
    )


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr206_codex_four_group_saturated_source_sideport_stays_renderable(
    reversed_order: bool,
) -> None:
    """An occupied shared source port must not invalidate a safe alternate."""
    model = _p2_feedback_geometry_model((4, 5, 4, 2))
    relations = (
        ("n10", "n2", "feedback", "x"),
        ("n10", "n11", "flow", "Approve"),
        ("n0", "n8", "risk", "x"),
        ("n13", "n3", "feedback", "Approve"),
        ("n7", "n1", "flow", "link"),
        ("n0", "n12", "feedback", "long label"),
        ("n1", "n8", "flow", "x"),
        ("n2", "n11", "flow", "x"),
        ("n13", "n8", "flow", "long label"),
    )
    edges = [
        {"id": f"e{i:02}", "from": source, "to": target,
         "kind": kind, "label": label}
        for i, (source, target, kind, label) in enumerate(relations)
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels, cards = (
        _edge_paths(root), _edge_label_boxes(root), _node_boxes(root)
    )
    assert len(paths) == len(edges)
    assert paths["e07"].startswith("M 315.0 ")
    assert paths["e07"].endswith("L 977.0 707.0")
    for node_id, box in cards.items():
        if node_id not in {"n2", "n11"}:
            assert _p2_linear_path_clears_box(paths["e07"], box), node_id
    for edge_id, box in labels.items():
        assert _p2_linear_path_clears_box(paths["e07"], box), edge_id
    model["edges"] = list(reversed(model["edges"]))
    other = _parse(render_native_diagram(model))
    assert (paths, labels) == (_edge_paths(other), _edge_label_boxes(other))


@pytest.mark.parametrize("reversed_order", [False, True])
def test_pr206_codex_adjacent_cubic_clears_anchored_selfloop_label(
    reversed_order: bool,
) -> None:
    """An anchored self-loop label is a physical obstacle to a peer cubic."""
    model = _p2_feedback_geometry_model((3, 2))
    edges = [
        {"id": "e0", "from": "n1", "to": "n3",
         "kind": "flow", "label": "Approve"},
        {"id": "e1", "from": "n1", "to": "n1",
         "kind": "risk", "label": "x"},
    ]
    model["edges"] = list(reversed(edges)) if reversed_order else edges
    root = _parse(render_native_diagram(model))
    paths, labels = _edge_paths(root), _edge_label_boxes(root)
    assert len(paths) == 2
    assert _p2_cubic_path_clears_box(paths["e0"], labels["e1"])
    assert _p2_linear_path_clears_box(paths["e0"], labels["e1"])
    model["edges"] = list(reversed(model["edges"]))
    other = _parse(render_native_diagram(model))
    assert (paths, labels) == (_edge_paths(other), _edge_label_boxes(other))
