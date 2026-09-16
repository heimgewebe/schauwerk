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


def _path_points(path: str) -> list[tuple[float, float]]:
    tokens = re.findall(r"[MCL]|-?[0-9.]+", path)
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    index = 0
    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command == "M":
            current = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            points.append(current)
        elif command == "L":
            target = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            start = current
            points.extend(
                (
                    start[0] + (target[0] - start[0]) * step / 128,
                    start[1] + (target[1] - start[1]) * step / 128,
                )
                for step in range(1, 129)
            )
            current = target
        elif command == "C":
            control_one = (float(tokens[index]), float(tokens[index + 1]))
            control_two = (float(tokens[index + 2]), float(tokens[index + 3]))
            target = (float(tokens[index + 4]), float(tokens[index + 5]))
            index += 6
            start = current
            for step in range(1, 257):
                t = step / 256
                u = 1 - t
                points.append(
                    (
                        u**3 * start[0]
                        + 3 * u * u * t * control_one[0]
                        + 3 * u * t * t * control_two[0]
                        + t**3 * target[0],
                        u**3 * start[1]
                        + 3 * u * u * t * control_one[1]
                        + 3 * u * t * t * control_two[1]
                        + t**3 * target[1],
                    )
                )
            current = target
        else:
            raise AssertionError(f"unsupported SVG path command: {command}")
    return points


def test_system_landscape_paths_do_not_enter_unrelated_cards() -> None:
    raw = _load("system-landscape-v1.json")
    rendered = render_native_diagram(raw)
    assert rendered == render_native_diagram(copy.deepcopy(raw))
    root = ET.fromstring(rendered)
    source_edges = {edge["id"]: edge for edge in raw["edges"]}
    node_boxes: dict[str, tuple[float, float, float, float]] = {}
    for node in root.iter():
        if node.attrib.get("data-source-kind") != "node":
            continue
        rect = node.find(f"{{{SVG_NAMESPACE}}}rect")
        assert rect is not None
        node_boxes[node.attrib["data-source-id"]] = _rect_box(rect)

    for edge in root.iter():
        edge_id = edge.attrib.get("data-source-id")
        if edge.attrib.get("data-source-kind") != "edge" or edge_id is None:
            continue
        path = edge.find(f"{{{SVG_NAMESPACE}}}path")
        assert path is not None
        source = source_edges[edge_id]
        unrelated = {
            node_id: box
            for node_id, box in node_boxes.items()
            if node_id not in {source["from"], source["to"]}
        }
        for px, py in _path_points(path.attrib["d"]):
            assert all(
                not (x < px < x + width and y < py < y + height)
                for x, y, width, height in unrelated.values()
            ), f"{edge_id} enters an unrelated card near {(px, py)}"

    land08 = next(
        edge
        for edge in root.iter()
        if edge.attrib.get("data-source-kind") == "edge"
        and edge.attrib.get("data-source-id") == "land08"
    )
    assert land08.attrib["data-route"] == "knowledge-map-card-safe"

    land08_path = land08.find(f"{{{SVG_NAMESPACE}}}path")
    assert land08_path is not None
    land05 = next(
        edge
        for edge in root.iter()
        if edge.attrib.get("data-source-kind") == "edge"
        and edge.attrib.get("data-source-id") == "land05"
    )
    land05_label = land05.find(f"{{{SVG_NAMESPACE}}}rect")
    assert land05_label is not None
    label_x, label_y, label_width, label_height = _rect_box(land05_label)
    clearance = 4.0
    expanded_label = (
        label_x - clearance,
        label_y - clearance,
        label_width + 2 * clearance,
        label_height + 2 * clearance,
    )
    for px, py in _path_points(land08_path.attrib["d"]):
        x, y, width, height = expanded_label
        assert not (x < px < x + width and y < py < y + height), (
            f"land08 lacks visual clearance from land05 label near {(px, py)}"
        )


def _edge_group(root: ET.Element, edge_id: str) -> ET.Element:
    return next(
        edge
        for edge in root.iter()
        if edge.attrib.get("data-source-kind") == "edge"
        and edge.attrib.get("data-source-id") == edge_id
    )


def _assert_path_clears_label(
    root: ET.Element, path_edge_id: str, label_edge_id: str, *, clearance: float = 1.0
) -> None:
    path_edge = _edge_group(root, path_edge_id)
    label_edge = _edge_group(root, label_edge_id)
    path = path_edge.find(f"{{{SVG_NAMESPACE}}}path")
    label = label_edge.find(f"{{{SVG_NAMESPACE}}}rect")
    assert path is not None
    assert label is not None
    x, y, width, height = _rect_box(label)
    expanded = (
        x - clearance,
        y - clearance,
        width + 2 * clearance,
        height + 2 * clearance,
    )
    ex, ey, ew, eh = expanded
    for px, py in _path_points(path.attrib["d"]):
        assert not (ex < px < ex + ew and ey < py < ey + eh), (
            f"{path_edge_id} is masked by {label_edge_id} near {(px, py)}"
        )


def test_gate1_edge_labels_do_not_mask_unrelated_routes() -> None:
    cases = {
        "system-landscape-v1.json": (("land09", "land02"),),
        "decision-flow-v1.json": (
            ("flow04", "flow06"),
            ("flow06", "flow04"),
        ),
    }
    for fixture_name, pairs in cases.items():
        raw = _load(fixture_name)
        candidates = [copy.deepcopy(raw), copy.deepcopy(raw)]
        candidates[1]["edges"] = list(reversed(candidates[1]["edges"]))
        observations = []
        for candidate in candidates:
            root = ET.fromstring(render_native_diagram(candidate))
            for path_edge_id, label_edge_id in pairs:
                _assert_path_clears_label(root, path_edge_id, label_edge_id)
            observations.append(
                {
                    edge_id: _rect_box(_edge_group(root, edge_id).find(f"{{{SVG_NAMESPACE}}}rect"))
                    for _, edge_id in pairs
                }
            )
        assert observations[0] == observations[1]


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
