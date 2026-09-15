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
WORKFLOW = ROOT / ".github/workflows/pr184-gate1-fix.yml"
SELF = Path(__file__)
BASE_HEAD = "8d4fb0551b5f8ff1babae204d999843a3deedd60"
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


def edge_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for edge in root.iter():
        if edge.attrib.get("data-source-kind") != "edge":
            continue
        rect = edge.find(f"{{{NS}}}rect")
        assert rect is not None
        boxes[edge.attrib["data-source-id"]] = tuple(
            float(rect.attrib[key]) for key in ("x", "y", "width", "height")
        )
    return boxes


def overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def process_repro() -> dict:
    raw = load("decision-flow-v1.json")
    raw["id"] = "pr184_outer_long_repro"
    raw["title"] = "PR 184 outer long repro"
    raw["purpose"] = (
        "Reproduces independent process label allocators sharing the same outer area."
    )
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
    return raw


def self_loop_repro() -> dict:
    raw = load("system-landscape-v1.json")
    raw["id"] = "pr184_self_loop_canvas_repro"
    raw["title"] = "PR 184 self loop canvas repro"
    raw["purpose"] = (
        "Reproduces a rightmost generic self-loop label leaving the SVG viewBox."
    )
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
    return raw


def golden_hashes() -> dict[str, str]:
    from schauwerk.visual.native_diagram import render_native_diagram

    hashes: dict[str, str] = {}
    for name in GOLDENS:
        svg = render_native_diagram(load(name))
        hashes[name] = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    return hashes


def prove_current_failures() -> None:
    from schauwerk.visual.native_diagram import render_native_diagram

    process_boxes = edge_boxes(parse(render_native_diagram(process_repro())))
    process_overlap = any(
        overlap(process_boxes[outer], process_boxes[long])
        for outer in ("a0", "a1")
        for long in ("z0", "z1")
    )

    architecture_root = parse(render_native_diagram(self_loop_repro()))
    loop_box = edge_boxes(architecture_root)["loop"]
    viewbox_width = float(architecture_root.attrib["viewBox"].split()[2])
    loop_overflow = loop_box[0] + loop_box[2] > viewbox_width

    print(
        json.dumps(
            {
                "process_outer_long_overlap": process_overlap,
                "self_loop_overflow": loop_overflow,
                "loop_box": loop_box,
                "viewbox_width": viewbox_width,
            },
            sort_keys=True,
        )
    )
    if not process_overlap:
        raise SystemExit("current-head process outer/long overlap did not reproduce")
    if not loop_overflow:
        raise SystemExit("current-head generic self-loop overflow did not reproduce")


def patch_source() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    def replace_once(old: str, new: str) -> None:
        nonlocal source
        count = source.count(old)
        if count != 1:
            raise SystemExit(
                f"expected exactly one source match, got {count}: {old[:90]!r}"
            )
        source = source.replace(old, new, 1)

    replace_once(
        '    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH\n'
        '    vertical_row_gap = process_row_gap if intent == "process" else non_process_row_gap\n',
        '    node_width = _NARRATIVE_NODE_WIDTH if intent == "narrative" else _NODE_WIDTH\n'
        '    if intent not in {"process", "narrative"}:\n'
        '        # Generic non-process self-loop labels are pushed fully to the right of\n'
        '        # their source card during rendering. Reserve that exact label bound in\n'
        '        # the viewBox up front so a loop on the rightmost card cannot be clipped.\n'
        '        required_self_loop_right = float(width)\n'
        '        for edge in model["edges"]:\n'
        '            if str(edge["kind"]) == "feedback" or edge["from"] != edge["to"]:\n'
        '                continue\n'
        '            metrics = _edge_label_metrics(edge, positions, intent)\n'
        '            source_x = positions[str(edge["from"])][0]\n'
        '            label_right = source_x + node_width + metrics.width + 8\n'
        '            required_self_loop_right = max(\n'
        '                required_self_loop_right,\n'
        '                label_right + 8,\n'
        '            )\n'
        '        width = max(width, math.ceil(required_self_loop_right))\n'
        '    vertical_row_gap = process_row_gap if intent == "process" else non_process_row_gap\n',
    )

    replace_once(
        '    process_adjacent_label_y: dict[str, float] = {}\n'
        '    occupied_process_adjacent_corridors: set[tuple[int, int]] = set()\n'
        '    if intent == "process":\n',
        '    process_adjacent_label_y: dict[str, float] = {}\n'
        '    occupied_process_adjacent_corridors: set[tuple[int, int]] = set()\n'
        '    process_outer_label_right = max(\n'
        '        (right for _, _, right, _ in packed_process_label_bounds),\n'
        '        default=0.0,\n'
        '    )\n'
        '    if intent == "process":\n',
    )

    replace_once(
        '                process_branch_gutter_x[edge_id] = cursor\n'
        '                label_right = cursor + 8 + _PROCESS_LABEL_MAX_WIDTH\n'
        '                required_right = max(required_right, label_right + _PAGE_MARGIN)\n'
        '                cursor = label_right + 12\n',
        '                process_branch_gutter_x[edge_id] = cursor\n'
        '                actual_label_right = (\n'
        '                    cursor\n'
        '                    + 8\n'
        '                    + _edge_label_metrics(edges_by_id[edge_id], positions, intent).width\n'
        '                )\n'
        '                process_outer_label_right = max(\n'
        '                    process_outer_label_right, actual_label_right\n'
        '                )\n'
        '                # Keep the established fixed-width lane reservation so existing\n'
        '                # process-gutter geometry does not move merely because this\n'
        '                # cross-packer occupancy bound became explicit.\n'
        '                label_right = cursor + 8 + _PROCESS_LABEL_MAX_WIDTH\n'
        '                required_right = max(required_right, label_right + _PAGE_MARGIN)\n'
        '                cursor = label_right + 12\n',
    )

    replace_once(
        '            width += max(0, required_gutter - _PROCESS_EDGE_GUTTER)\n'
        '            previous_bottom = 0.0\n',
        '            width += max(0, required_gutter - _PROCESS_EDGE_GUTTER)\n'
        '            if process_outer_label_right:\n'
        '                widest_long_branch_label = max(\n'
        '                    _edge_label_metrics(edge, positions, intent).width\n'
        '                    for _, _, edge in long_branches\n'
        '                )\n'
        '                # The long-branch packer runs after the adjacent/anchored outer\n'
        '                # lanes. Keep its whole label column to the right of the actual\n'
        '                # earlier label extent instead of assuming the historical 80 px\n'
        '                # edge gutter is still empty.\n'
        '                width = max(\n'
        '                    width,\n'
        '                    math.ceil(\n'
        '                        process_outer_label_right\n'
        '                        + 8\n'
        '                        + widest_long_branch_label / 2\n'
        '                        + required_gutter / 2\n'
        '                    ),\n'
        '                )\n'
        '            previous_bottom = 0.0\n',
    )

    SOURCE.write_text(source, encoding="utf-8")


def append_tests() -> None:
    tests = TESTS.read_text(encoding="utf-8")
    marker = "def test_process_long_branch_labels_clear_existing_outer_lanes()"
    if marker in tests:
        raise SystemExit("PR184 regression tests already present unexpectedly")
    tests += r'''


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
'''
    TESTS.write_text(tests, encoding="utf-8")


def main() -> None:
    run("git", "merge-base", "--is-ancestor", BASE_HEAD, "HEAD")
    extra = set(output("git", "diff", "--name-only", BASE_HEAD, "HEAD").splitlines())
    allowed = {
        ".github/workflows/pr184-gate1-fix.yml",
        ".github/pr184_gate1_fix.py",
    }
    if extra - allowed:
        raise SystemExit(f"unexpected concurrent changes before fix: {sorted(extra - allowed)}")

    before = golden_hashes()
    prove_current_failures()
    patch_source()
    append_tests()

    run(
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/visual/test_native_diagram.py",
        "-k",
        "process_long_branch_labels_clear_existing_outer_lanes or generic_non_process_self_loop_label_stays_inside_canvas",
    )
    run("python", "-m", "pytest", "-q", "tests/visual/test_native_diagram.py")
    run("make", "validate")
    after = golden_hashes()
    print(json.dumps({"golden_before": before, "golden_after": after}, sort_keys=True))
    if after != before:
        raise SystemExit("accepted Golden SVG bytes changed")

    WORKFLOW.unlink()
    SELF.unlink()
    run("git", "diff", "--check")
    run(
        "git",
        "config",
        "user.name",
        "grabowski-pr184-fix",
    )
    run("git", "config", "user.email", "actions@users.noreply.github.com")
    run(
        "git",
        "add",
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_diagram.py",
        ".github/workflows/pr184-gate1-fix.yml",
        ".github/pr184_gate1_fix.py",
    )
    run("git", "diff", "--cached", "--check")
    run("git", "commit", "-m", "fix(visual): close remaining Gate 1 label gaps")
    run("git", "push", "origin", f"HEAD:{BRANCH}")


if __name__ == "__main__":
    main()
