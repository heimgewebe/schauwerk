from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.visual.native_diagram import render_native_diagram
from schauwerk.visual.native_viewer import (
    MANIFEST_SCHEMA,
    NativeViewerError,
    build_native_viewer,
)
from schauwerk.visual.representation import validate_representation_input

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/system-landscape-v1.json"


def _load() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _source_ids(svg: bytes, kind: str) -> set[str]:
    root = ET.fromstring(svg)
    return {
        element.attrib["data-source-id"]
        for element in root.iter()
        if element.attrib.get("data-source-kind") == kind
    }


def test_native_viewer_build_is_deterministic_and_keeps_semantic_truth_read_only(
    tmp_path: Path,
) -> None:
    raw = _load()
    original = copy.deepcopy(raw)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = build_native_viewer(raw, first_root)
    second = build_native_viewer(copy.deepcopy(raw), second_root)

    assert raw == original
    assert first == second
    assert first["schema_version"] == MANIFEST_SCHEMA
    assert first["semantic_authority"]["mode"] == "read-only"
    assert first["layout_overlay"] == {
        "authority": "browser-local-only",
        "storage": "localStorage",
        "binding": "input_digest",
        "semantic_writeback": False,
        "cross_device_persistence": False,
    }
    assert first["interactions"] == ["pan", "zoom", "selection", "node-drag"]
    assert first["interaction_contract"]["two_pointer_pinch_zoom"] is True
    assert first["interaction_contract"]["edge_geometry_after_node_drag"] == "frozen-gate1-svg"
    assert first["interaction_contract"]["edge_rerouting"] is False
    assert first["network_boundary"]["external_requests_required"] is False
    assert "phase-3-cutover-acceptance" in first["does_not_establish"]

    normalized = validate_representation_input(raw)
    expected_svg = render_native_diagram(normalized).encode("utf-8")
    representation_payload = (first_root / "representation.json").read_bytes()
    assert (first_root / "diagram.svg").read_bytes() == expected_svg
    assert first["renderer_authority"]["bytes_modified_by_viewer"] is False
    assert first["renderer_authority"]["sha256"] == hashlib.sha256(expected_svg).hexdigest()
    assert first["semantic_authority"]["sha256"] == hashlib.sha256(
        representation_payload
    ).hexdigest()
    assert json.loads(representation_payload) == normalized
    assert first["input_digest"] == normalized["input_digest"]

    manifest_files = {item["path"]: item for item in first["files"]}
    assert set(manifest_files) == {
        "app.js",
        "diagram.svg",
        "index.html",
        "interaction.js",
        "representation.json",
        "styles.css",
    }
    for name, record in manifest_files.items():
        assert (first_root / name).stat().st_size == record["bytes"]
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes()
    assert (first_root / "manifest.json").read_bytes() == (
        second_root / "manifest.json"
    ).read_bytes()

    index = (first_root / "index.html").read_text(encoding="utf-8")
    app = (first_root / "app.js").read_text(encoding="utf-8")
    styles = (first_root / "styles.css").read_text(encoding="utf-8")
    assert '<svg id="nativeDiagram" class="native-diagram"' in index
    assert f'data-input-digest="{normalized["input_digest"]}"' in index
    assert "<iframe" not in index
    assert "diagrams.net" not in index
    assert "schauwerk.native-viewer.layout.v1.${inputDigest}" in app
    assert 'Native viewer input digest is missing or invalid' in app
    assert 'svg.dataset.inputDigest || "unbound"' not in app
    assert '/^[0-9a-f]{64}$/.test(inputDigest)' in app
    assert 'querySelectorAll(\'[data-source-kind="node"]\')' in app
    assert 'querySelector(\'[data-source-kind="edge"]\')' not in app
    assert 'setAttribute("d"' not in app
    assert 'addEventListener("pointerdown"' in app
    assert 'addEventListener("wheel"' in app
    assert 'gesture = { kind: "pinch"' in app
    assert 'pointers.some((pointer) => !pointer.background)' not in app
    assert 'if (gesture?.kind === "drag")' in app
    assert 'const DRAG_THRESHOLD_PX = 4;' in app
    assert (
        'if (!gesture.moved && Math.hypot(screenDx, screenDy) < DRAG_THRESHOLD_PX) return;'
        in app
    )
    assert 'endedGesture.moved && persistOverrides()' in app
    assert 'event.ctrlKey || event.metaKey' in app
    assert 'view = panBy(view, -event.deltaX * modeScale, -event.deltaY * modeScale);' in app
    assert 'event.key === "Enter" || event.key === " "' in app
    assert "touch-action: none" in styles


def test_native_viewer_canonical_svg_materializes_stable_source_ids(tmp_path: Path) -> None:
    raw = _load()
    output = tmp_path / "viewer"
    build_native_viewer(raw, output)
    svg = (output / "diagram.svg").read_bytes()

    assert _source_ids(svg, "node") == {node["id"] for node in raw["nodes"]}
    assert _source_ids(svg, "edge") == {edge["id"] for edge in raw["edges"]}
    assert _source_ids(svg, "group") == {group["id"] for group in raw["groups"]}


def test_native_viewer_interaction_math_is_browser_independent(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable")

    output = tmp_path / "viewer"
    build_native_viewer(_load(), output)
    module_source = (output / "interaction.js").read_bytes()
    module_url = json.dumps(
        "data:text/javascript;base64," + base64.b64encode(module_source).decode("ascii")
    )
    script = f"""
const m = await import({module_url});
const view = {{x: 10, y: 20, scale: 2}};
const anchor = {{x: 210, y: 120}};
const before = {{x: (anchor.x-view.x)/view.scale, y: (anchor.y-view.y)/view.scale}};
const zoomed = m.zoomAt(view, 3, anchor);
const after = {{x: (anchor.x-zoomed.x)/zoomed.scale, y: (anchor.y-zoomed.y)/zoomed.scale}};
if (
  Math.abs(before.x-after.x) > 1e-9 ||
  Math.abs(before.y-after.y) > 1e-9
) throw new Error('zoom anchor drift');
const delta = m.screenDeltaToSvg({{scale: 2}}, 40, -10);
if (delta.x !== 20 || delta.y !== -5) throw new Error('drag delta is not scale aware');
const panned = m.panBy(view, 7, -9);
if (panned.x !== 17 || panned.y !== 11) throw new Error('pan math drifted');
if (m.clampScale(99) !== 4 || m.clampScale(0.01) !== 0.25) {{
  throw new Error('zoom bounds drifted');
}}
const safe = m.sanitizeOverrides({{
  a: {{x: 20000, y: -20000}},
  bad: {{x: 'no', y: 1}},
}});
if (
  safe.a.x !== 10000 || safe.a.y !== -10000 || safe.bad !== undefined ||
  Object.getPrototypeOf(safe) !== null
) throw new Error('override sanitization drifted');
const sameWorking = m.updateNodeOffset(safe, 'a', 3, 4);
if (sameWorking !== safe || m.nodeOffset(safe, 'a').x !== 3 || m.nodeOffset(safe, 'a').y !== 4) {{
  throw new Error('working override update should be in-place and O(1)');
}}
const fitted = m.fitView(1000, 500, 800, 600, 20);
if (!(
  fitted.scale > 0 &&
  fitted.scale <= 4 &&
  Number.isFinite(fitted.x) &&
  Number.isFinite(fitted.y)
)) throw new Error('fit math invalid');
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def test_native_viewer_rejects_nonempty_or_symlinked_output(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(NativeViewerError, match="must be empty"):
        build_native_viewer(_load(), occupied)

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(NativeViewerError, match="must not contain symlinks"):
        build_native_viewer(_load(), link / "viewer")
