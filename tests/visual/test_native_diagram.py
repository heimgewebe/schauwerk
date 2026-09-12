from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.visual.grammar import GRAMMAR_SCHEMA_VERSION
from schauwerk.visual.native_diagram import _xml_escape, render_native_diagram
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
                assert re.fullmatch(r"url\(#native-arrow-[a-z_]+\)", value)


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
    landscape_edge = next(
        element
        for element in landscape.iter()
        if element.attrib.get("data-source-kind") == "edge"
    )
    edge_text = landscape_edge.find(f"{{{SVG_NAMESPACE}}}text")
    assert edge_text is not None
    assert edge_text.attrib["font-size"] == "15"

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


def test_wide_dynamic_text_is_bounded_inside_renderer_boxes() -> None:
    raw = _load("decision-flow-v1.json")
    raw["nodes"][0]["label"] = "W" * 20
    raw["nodes"][0]["summary"] = "W" * 28
    raw["edges"][0]["label"] = "W" * 24

    root = _parse(render_native_diagram(raw))
    request = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "request"
        and element.attrib.get("data-source-kind") == "node"
    )
    request_texts = request.findall(f"{{{SVG_NAMESPACE}}}text")
    for text_node in request_texts[1:]:
        for tspan in text_node.findall(f"{{{SVG_NAMESPACE}}}tspan"):
            assert float(tspan.attrib["textLength"]) <= 214.0
            assert tspan.attrib["lengthAdjust"] == "spacingAndGlyphs"

    flow01 = next(
        element
        for element in root.iter()
        if element.attrib.get("data-source-id") == "flow01"
        and element.attrib.get("data-source-kind") == "edge"
    )
    edge_text = flow01.find(f"{{{SVG_NAMESPACE}}}text")
    assert edge_text is not None
    edge_tspan = edge_text.find(f"{{{SVG_NAMESPACE}}}tspan")
    assert edge_tspan is not None
    assert float(edge_tspan.attrib["textLength"]) <= 196.0
    assert edge_tspan.attrib["lengthAdjust"] == "spacingAndGlyphs"
