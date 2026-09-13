from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.visual.grammar import GRAMMAR_SCHEMA_VERSION
from schauwerk.visual.native_diagram import (
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


@pytest.mark.parametrize(
    ("fixture_name", "edge_id"),
    (("system-landscape-v1.json", "land09"), ("narrative-journey-v1.json", "journey07")),
)
def test_non_process_feedback_label_stays_outside_every_card(
    fixture_name: str, edge_id: str
) -> None:
    root = _parse(render_native_diagram(_load(fixture_name)))
    node_boxes: list[tuple[float, float, float, float]] = []
    for element in root.iter():
        if element.attrib.get("data-source-kind") != "node":
            continue
        rect = element.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes.append(
            tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        )

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
    lx, ly, lw, lh = (
        float(label_rect.attrib[key]) for key in ("x", "y", "width", "height")
    )
    assert lw >= 230
    assert len(label_text.findall(f"{{{SVG_NAMESPACE}}}tspan")) == 1
    assert all(
        not (lx < x + width and lx + lw > x and ly < y + height and ly + lh > y)
        for x, y, width, height in node_boxes
    )

    points = [
        (float(x), float(y))
        for x, y in re.findall(r"[ML] ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(points) == 4
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
            raise AssertionError("feedback corridor must remain orthogonal")


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
    node_boxes: list[tuple[float, float, float, float]] = []
    for element in root.iter():
        if element.attrib.get("data-source-kind") != "node":
            continue
        rect = element.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes.append(
            tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
        )

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
    lx, ly, lw, lh = (
        float(label_rect.attrib[key]) for key in ("x", "y", "width", "height")
    )
    assert all(
        not (lx < x + width and lx + lw > x and ly < y + height and ly + lh > y)
        for x, y, width, height in node_boxes
    )
    canvas_height = float(root.attrib["viewBox"].split()[3])
    assert 0 <= ly and ly + lh <= canvas_height

    points = [
        (float(x), float(y))
        for x, y in re.findall(r"[ML] ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert len(points) in {4, 6}
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


def test_single_long_process_branch_preserves_legacy_gutter_contract() -> None:
    raw = _minimal_process_model(8)
    baseline = _parse(render_native_diagram(raw))
    baseline_width = float(baseline.attrib["viewBox"].split()[2])
    raw["edges"] = [
        {
            "id": "single_long",
            "from": "n0",
            "to": "n7",
            "label": "x",
            "kind": "risk",
        }
    ]
    root = _parse(render_native_diagram(raw))
    assert float(root.attrib["viewBox"].split()[2]) == baseline_width
    edge = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "single_long"
    )
    path = edge.find(f"{{{SVG_NAMESPACE}}}path")
    rect = edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None and rect is not None
    line_points = [
        (float(x), float(y))
        for x, y in re.findall(r"L ([-0-9.]+) ([-0-9.]+)", path.attrib["d"])
    ]
    assert line_points[0][0] == baseline_width - 40.0
    assert line_points[1][0] == baseline_width - 40.0
    assert float(rect.attrib["width"]) == 48.0


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
    for index in range(6):
        edges.append(
            {
                "id": f"long{index + 1}",
                "from": f"n{index + 6}",
                "to": f"n{12 + ((index + 1) % 6)}",
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
    assert len(forward_geometry) == 7
    assert len({values[0] for values in forward_geometry.values()}) == 7

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
