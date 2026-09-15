from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/schauwerk/visual/native_diagram.py"
TESTS = ROOT / "tests/visual/test_native_diagram.py"
WORKFLOW = ROOT / ".github/workflows/pr184-followup-fix.yml"
SELF = Path(__file__)
BASE_HEAD = "19479c5d4a6e0b292096db6fd20068d664f779c9"
BRANCH = "fix/native-diagram-gate1-terminal-20260912"
NS = "http://www.w3.org/2000/svg"
GOLDENS = (
    "system-landscape-v1.json",
    "decision-flow-v1.json",
    "narrative-journey-v1.json",
)


def run(*argv: str) -> None:
    subprocess.run(argv, cwd=ROOT, check=True)


def output(*argv: str) -> str:
    return subprocess.check_output(argv, cwd=ROOT, text=True).strip()


def load(name: str) -> dict:
    return json.loads(
        (ROOT / "docs/operators/fixtures/golden" / name).read_text(encoding="utf-8")
    )


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def node_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    result = {}
    for node in root.iter():
        if node.attrib.get("data-source-kind") != "node":
            continue
        rect = node.find(f"{{{NS}}}rect")
        assert rect is not None
        result[node.attrib["data-source-id"]] = tuple(
            float(rect.attrib[key]) for key in ("x", "y", "width", "height")
        )
    return result


def edge_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    result = {}
    for edge in root.iter():
        if edge.attrib.get("data-source-kind") != "edge":
            continue
        rect = edge.find(f"{{{NS}}}rect")
        assert rect is not None
        result[edge.attrib["data-source-id"]] = tuple(
            float(rect.attrib[key]) for key in ("x", "y", "width", "height")
        )
    return result


def overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def repro() -> dict:
    raw = load("system-landscape-v1.json")
    raw["id"] = "pr184_generic_self_loop_neighbor"
    raw["title"] = "Generic self loop neighbor collision"
    raw["purpose"] = "A generic self-loop must not put its label underneath the next card."
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
    return raw


def golden_hashes() -> dict[str, str]:
    from schauwerk.visual.native_diagram import render_native_diagram

    return {
        name: hashlib.sha256(render_native_diagram(load(name)).encode("utf-8")).hexdigest()
        for name in GOLDENS
    }


def prove_failure() -> None:
    from schauwerk.visual.native_diagram import render_native_diagram

    root = parse(render_native_diagram(repro()))
    loop_box = edge_boxes(root)["loop"]
    next_box = node_boxes(root)["n4"]
    collision = overlap(loop_box, next_box)
    print(json.dumps({"loop_box": loop_box, "next_box": next_box, "collision": collision}))
    if not collision:
        raise SystemExit("exact-head generic self-loop/neighbor collision did not reproduce")


def patch_source() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    def replace_once(old: str, new: str) -> None:
        nonlocal source
        count = source.count(old)
        if count != 1:
            raise SystemExit(f"expected one source match, got {count}: {old[:80]!r}")
        source = source.replace(old, new, 1)

    replace_once(
        '''    if intent not in {"process", "narrative"}:\n        # Generic non-process self-loop labels are pushed fully to the right of\n        # their source card during rendering. Reserve that exact label bound in\n        # the viewBox up front so a loop on the rightmost card cannot be clipped.\n        required_self_loop_right = float(width)\n        for edge in model["edges"]:\n            if str(edge["kind"]) == "feedback" or edge["from"] != edge["to"]:\n                continue\n            metrics = _edge_label_metrics(edge, positions, intent)\n            source_x = positions[str(edge["from"])][0]\n            label_right = source_x + node_width + metrics.width + 8\n            required_self_loop_right = max(\n                required_self_loop_right,\n                label_right + 8,\n            )\n        width = max(width, math.ceil(required_self_loop_right))\n''',
        '',
    )

    replace_once(
        '''    narrative_parallel_gutter_x: dict[str, float] = {}\n''',
        '''    generic_self_loop_gutter_x: dict[str, float] = {}\n    if intent not in {"process", "narrative"}:\n        generic_self_loops: list[Mapping[str, Any]] = []\n        for edge in model["edges"]:\n            if str(edge["kind"]) == "feedback" or edge["from"] != edge["to"]:\n                continue\n            source_id = str(edge["from"])\n            source_x, source_y = positions[source_id]\n            metrics = _edge_label_metrics(edge, positions, intent)\n            natural_left = source_x + node_width + 8\n            natural_right = natural_left + metrics.width\n            collides_with_peer = any(\n                node_id != source_id\n                and node_y == source_y\n                and natural_left < node_x + node_width\n                and natural_right > node_x\n                for node_id, (node_x, node_y) in positions.items()\n            )\n            if collides_with_peer or natural_right > width - 8:\n                generic_self_loops.append(edge)\n        if generic_self_loops:\n            obstacle_right = max(x + node_width for x, _ in positions.values())\n            if regions:\n                obstacle_right = max(\n                    obstacle_right,\n                    max(x + region_width for _, _, x, _, region_width, _ in regions),\n                )\n            cursor = max(obstacle_right + 12.0, width - _PAGE_MARGIN + 12.0)\n            required_right = float(width)\n            required_bottom = float(height)\n            for edge in sorted(generic_self_loops, key=lambda item: str(item["id"])):\n                metrics = _edge_label_metrics(edge, positions, intent)\n                edge_id = str(edge["id"])\n                generic_self_loop_gutter_x[edge_id] = cursor\n                required_right = max(\n                    required_right,\n                    cursor + 8 + metrics.width + _PAGE_MARGIN,\n                )\n                source_y = positions[str(edge["from"])][1]\n                corridor_y = source_y + _NODE_HEIGHT + non_process_row_gap / 2\n                required_bottom = max(\n                    required_bottom,\n                    corridor_y + metrics.height / 2 + 8,\n                )\n                cursor += 8 + metrics.width + 12\n            width = max(width, math.ceil(required_right))\n            height = max(height, math.ceil(required_bottom))\n\n    narrative_parallel_gutter_x: dict[str, float] = {}\n''',
    )

    replace_once(
        '''    narrative_parallel_gutter_x: float | None = None,\n    narrative_self_loop_gutter_x: float | None = None,\n    label_height: int = 0,\n''',
        '''    narrative_parallel_gutter_x: float | None = None,\n    narrative_self_loop_gutter_x: float | None = None,\n    generic_self_loop_gutter_x: float | None = None,\n    label_height: int = 0,\n''',
    )

    replace_once(
        '''        return path, gutter_x + 8 + label_width / 2, corridor_y, route\n    elif self_loop:\n''',
        '''        return path, gutter_x + 8 + label_width / 2, corridor_y, route\n    elif (\n        self_loop\n        and intent not in {"process", "narrative"}\n        and generic_self_loop_gutter_x is not None\n    ):\n        route = "generic-self-loop"\n        start_x = source_x + node_width * 0.35\n        end_x = source_x + node_width * 0.65\n        start_y = end_y = source_y + _NODE_HEIGHT\n        corridor_y = start_y + non_process_row_gap / 2\n        gutter_x = generic_self_loop_gutter_x\n        path = (\n            f"M {start_x:.1f} {start_y:.1f} "\n            f"L {start_x:.1f} {corridor_y:.1f} "\n            f"L {gutter_x:.1f} {corridor_y:.1f} "\n            f"L {end_x:.1f} {corridor_y:.1f} "\n            f"L {end_x:.1f} {end_y:.1f}"\n        )\n        return path, gutter_x + 8 + label_width / 2, corridor_y, route\n    elif self_loop:\n''',
    )

    replace_once(
        '''    narrative_parallel_gutter_x: float | None = None,\n    narrative_self_loop_gutter_x: float | None = None,\n    self_loop_lane: int | None = None,\n''',
        '''    narrative_parallel_gutter_x: float | None = None,\n    narrative_self_loop_gutter_x: float | None = None,\n    generic_self_loop_gutter_x: float | None = None,\n    self_loop_lane: int | None = None,\n''',
    )

    replace_once(
        '''        narrative_parallel_gutter_x=narrative_parallel_gutter_x,\n        narrative_self_loop_gutter_x=narrative_self_loop_gutter_x,\n        label_height=label_height,\n''',
        '''        narrative_parallel_gutter_x=narrative_parallel_gutter_x,\n        narrative_self_loop_gutter_x=narrative_self_loop_gutter_x,\n        generic_self_loop_gutter_x=generic_self_loop_gutter_x,\n        label_height=label_height,\n''',
    )

    replace_once(
        '''                narrative_self_loop_gutter_x=narrative_self_loop_gutter_x.get(str(edge["id"])),\n                self_loop_lane=self_loop_lanes.get(str(edge["id"])),\n''',
        '''                narrative_self_loop_gutter_x=narrative_self_loop_gutter_x.get(str(edge["id"])),\n                generic_self_loop_gutter_x=generic_self_loop_gutter_x.get(str(edge["id"])),\n                self_loop_lane=self_loop_lanes.get(str(edge["id"])),\n''',
    )

    SOURCE.write_text(source, encoding="utf-8")


def append_test() -> None:
    tests = TESTS.read_text(encoding="utf-8")
    marker = "def test_generic_non_process_self_loop_routes_clear_of_next_card()"
    if marker in tests:
        raise SystemExit("follow-up regression already present")
    tests += r'''


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
'''
    TESTS.write_text(tests, encoding="utf-8")


def main() -> None:
    run("git", "merge-base", "--is-ancestor", BASE_HEAD, "HEAD")
    changed = set(output("git", "diff", "--name-only", BASE_HEAD, "HEAD").splitlines())
    allowed = {
        ".github/pr184_followup_fix.py",
        ".github/workflows/pr184-followup-fix.yml",
    }
    if changed - allowed:
        raise SystemExit(f"unexpected concurrent changes: {sorted(changed - allowed)}")

    before = golden_hashes()
    prove_failure()
    patch_source()
    append_test()

    run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/visual/test_native_diagram.py",
        "-k",
        "generic_non_process_self_loop",
    )
    run("python", "-m", "pytest", "-q", "tests/visual/test_native_diagram.py")
    run("make", "validate")
    after = golden_hashes()
    print(json.dumps({"golden_before": before, "golden_after": after}, sort_keys=True))
    if before != after:
        raise SystemExit("accepted Golden SVG bytes changed")

    WORKFLOW.unlink()
    SELF.unlink()
    run("git", "diff", "--check")
    run("git", "config", "user.name", "grabowski-pr184-fix")
    run("git", "config", "user.email", "actions@users.noreply.github.com")
    run(
        "git",
        "add",
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_diagram.py",
        ".github/workflows/pr184-followup-fix.yml",
        ".github/pr184_followup_fix.py",
    )
    run("git", "diff", "--cached", "--check")
    run("git", "commit", "-m", "fix(visual): route generic self-loops clear of peers")
    run("git", "push", "origin", f"HEAD:{BRANCH}")


if __name__ == "__main__":
    main()
