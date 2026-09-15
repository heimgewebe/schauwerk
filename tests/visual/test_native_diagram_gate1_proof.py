from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from schauwerk.visual.native_diagram import render_native_diagram
from schauwerk.visual.representation import validate_representation_input

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


def _rect_box(rect: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height"))


def _boxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def test_gate1_narrative_cubic_relations_are_exact_and_deterministic() -> None:
    raw = _load("narrative-journey-v1.json")
    rendered = render_native_diagram(raw)

    assert rendered == render_native_diagram(copy.deepcopy(raw))
    assert rendered == render_native_diagram(validate_representation_input(raw))

    root = ET.fromstring(rendered)
    edges = {
        element.attrib["data-source-id"]: element
        for element in root.iter()
        if element.attrib.get("data-source-kind") == "edge"
    }
    assert sorted(edges) == sorted(edge["id"] for edge in raw["edges"])

    node_boxes = []
    for node in root.iter():
        if node.attrib.get("data-source-kind") != "node":
            continue
        rect = node.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes.append(_rect_box(rect))

    for edge_id in ("journey02", "journey05"):
        edge = edges[edge_id]
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        assert edge.attrib["data-route"] == "narrative-curve"
        assert " C " in path.attrib["d"]
        assert " L " not in path.attrib["d"]

        values = [float(value) for value in re.findall(r"-?[0-9.]+", path.attrib["d"])]
        start_x, start_y, control_x, control_y, _, _, end_x, end_y = values
        cross_product = (
            (control_x - start_x) * (end_y - start_y)
            - (control_y - start_y) * (end_x - start_x)
        )
        assert abs(cross_product) > 0.001

        label = edge.find(f"{{{SVG_NAMESPACE}}}rect")
        assert label is not None
        label_box = _rect_box(label)
        assert all(not _boxes_overlap(label_box, node_box) for node_box in node_boxes)


def test_gate1_goldens_have_only_inactive_local_svg_resources() -> None:
    forbidden_tags = {"a", "audio", "embed", "foreignObject", "iframe", "image", "script", "video"}

    for fixture_name in GOLDEN_FILES:
        root = ET.fromstring(render_native_diagram(_load(fixture_name)))
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
