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

from schauwerk.visual.native_diagram import _canvas_edge_geometry, render_native_diagram
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


def test_native_viewer_manifest_binds_integrated_reverse_proxy_context(
    tmp_path: Path,
) -> None:
    manifest = build_native_viewer(
        _load(),
        tmp_path / "integrated",
        serve_binding="trusted-reverse-proxy-private-ingress",
        public_base_path="/schaubild",
    )

    assert manifest["network_boundary"] == {
        "bundle": "server-managed-local-bundle",
        "external_requests_required": False,
        "serve_binding": "trusted-reverse-proxy-private-ingress",
        "public_base_path": "/schaubild",
        "delivery": "integrated-schaubild-runtime",
    }
    assert "production-readiness" not in manifest["does_not_establish"]
    assert "phase-3-cutover-acceptance" not in manifest["does_not_establish"]
    assert "consumer-deployment-readiness" in manifest["does_not_establish"]
    assert "public-edge-acceptance" in manifest["does_not_establish"]


def test_native_viewer_rejects_incoherent_serving_context(tmp_path: Path) -> None:
    with pytest.raises(NativeViewerError, match="loopback"):
        build_native_viewer(
            _load(),
            tmp_path / "bad-loopback",
            serve_binding="127.0.0.1-only",
            public_base_path="/schaubild",
        )
    with pytest.raises(NativeViewerError, match="unsupported"):
        build_native_viewer(
            _load(),
            tmp_path / "bad-binding",
            serve_binding="public-internet",
        )


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
    assert first["interactions"] == [
        "pan",
        "zoom",
        "selection",
        "node-drag",
        "live-edge-rerouting",
    ]
    assert first["interaction_contract"]["edge_rerouting"] is True
    assert first["interaction_contract"]["edge_geometry_after_node_drag"] == (
        "live-route-preserving-overlay"
    )
    assert first["interaction_contract"]["two_pointer_pinch_zoom"] is True
    assert first["network_boundary"] == {
        "bundle": "server-managed-local-bundle",
        "external_requests_required": False,
        "serve_binding": "127.0.0.1-only",
        "public_base_path": "/",
        "delivery": "development-loopback",
    }
    assert "production-readiness" in first["does_not_establish"]
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
    assert 'edgeState.path.setAttribute("d"' in app
    assert "function updateIncidentEdges(sourceId)" in app
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
    assert "const documentEditorHosted = documentMode && window.parent !== window;" in app
    assert "if (documentEditorHosted)" in app
    assert "Dokumentansicht · Bearbeiten im Schaubild-Host" in app
    assert "else if (persistOverrides())" in app
    assert 'event.ctrlKey || event.metaKey' in app
    assert 'view = panBy(view, -event.deltaX * modeScale, -event.deltaY * modeScale);' in app
    assert 'event.key === "Enter" || event.key === " "' in app
    assert 'if (event.key !== "Escape") return;' in app
    escape_handler = app[app.index('window.addEventListener("keydown"') :]
    assert "edgeCreateSource = null;" in escape_handler
    assert "edgeReattach = null;" in escape_handler
    assert "Kantenaktion abgebrochen" in escape_handler
    assert "touch-action: none" in styles


def test_native_viewer_title_markers_cannot_capture_svg_template_slot(
    tmp_path: Path,
) -> None:
    raw = _load()
    raw["title"] = "Marker __SCHAUWERK_NATIVE_SVG__ and __SCHAUWERK_NATIVE_TITLE__"
    output = tmp_path / "viewer"

    build_native_viewer(raw, output)

    index = (output / "index.html").read_text(encoding="utf-8")
    assert f"<title>{raw['title']}</title>" in index
    assert f"<strong>{raw['title']}</strong>" in index
    assert (
        '<div class="native-canvas" id="nativeCanvas">\n'
        '<svg id="nativeDiagram" class="native-diagram" ' in index
    )
    assert index.count('<svg id="nativeDiagram" class="native-diagram" ') == 1


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
    python_canvas_path, _, _, python_canvas_route, _ = _canvas_edge_geometry(
        {"id": "source", "x": 0, "y": 0, "width": 100, "height": 60},
        {"id": "target", "x": 300, "y": 100, "width": 120, "height": 80},
        {"id": "edge", "from_side": None, "to_side": None},
        lane=18.0,
    )
    assert python_canvas_route == "canvas-cubic"
    python_canvas_path_json = json.dumps(python_canvas_path)
    python_explicit_loop_path, _, _, explicit_loop_route, _ = _canvas_edge_geometry(
        {"id": "loop", "x": 20, "y": 30, "width": 100, "height": 80},
        {"id": "loop", "x": 20, "y": 30, "width": 100, "height": 80},
        {"from_side": "top", "to_side": "left"},
        lane=0,
    )
    assert explicit_loop_route == "canvas-self-loop"
    python_explicit_loop_path_json = json.dumps(python_explicit_loop_path)
    (
        python_opposite_loop_path,
        opposite_label_x,
        _opposite_label_y,
        opposite_loop_route,
        _opposite_bounds,
    ) = _canvas_edge_geometry(
        {"id": "loop", "x": 20, "y": 30, "width": 100, "height": 80},
        {"id": "loop", "x": 20, "y": 30, "width": 100, "height": 80},
        {"from_side": "top", "to_side": "bottom"},
        lane=0,
    )
    assert opposite_loop_route == "canvas-self-loop"
    assert opposite_label_x > 120
    python_opposite_loop_path_json = json.dumps(python_opposite_loop_path)

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
const canvasCubic = m.liveEdgeGeometry(
  {{x: 0, y: 0, width: 100, height: 60}},
  {{x: 300, y: 100, width: 120, height: 80}},
  {{route: 'canvas-cubic', lane: 0, fromSide: 'right', toSide: 'left'}}
);
if (canvasCubic.path !== 'M 100.0 30.0 C 179.9 30.0, 220.1 140.0, 300.0 140.0') {{
  throw new Error(`canvas cubic parity drift: ${{canvasCubic.path}}`);
}}
const canvasDefaultLane = m.liveEdgeGeometry(
  {{x: 0, y: 0, width: 100, height: 60}},
  {{x: 300, y: 100, width: 120, height: 80}},
  {{route: 'canvas-cubic', lane: 18}}
);
if (canvasDefaultLane.path !== {python_canvas_path_json}) {{
  throw new Error('canvas cubic Python/JS parity drift: ' + canvasDefaultLane.path);
}}
const canvasLoop = m.liveEdgeGeometry(
  {{x: 20, y: 30, width: 100, height: 80}},
  {{x: 20, y: 30, width: 100, height: 80}},
  {{route: 'canvas-self-loop', lane: 18, selfLoop: true}}
);
if (canvasLoop.path !== 'M 120.0 58.0 C 204.0 12.0, 204.0 128.0, 120.0 87.6') {{
  throw new Error(`canvas self-loop parity drift: ${{canvasLoop.path}}`);
}}
const explicitCanvasLoop = m.liveEdgeGeometry(
  {{x: 20, y: 30, width: 100, height: 80}},
  {{x: 20, y: 30, width: 100, height: 80}},
  {{route: 'canvas-self-loop', lane: 0, selfLoop: true, fromSide: 'top', toSide: 'left'}}
);
if (explicitCanvasLoop.path !== {python_explicit_loop_path_json}) {{
  throw new Error('explicit canvas self-loop Python/JS parity drift: ' + explicitCanvasLoop.path);
}}
const oppositeCanvasLoop = m.liveEdgeGeometry(
  {{x: 20, y: 30, width: 100, height: 80}},
  {{x: 20, y: 30, width: 100, height: 80}},
  {{route: 'canvas-self-loop', lane: 0, selfLoop: true, fromSide: 'top', toSide: 'bottom'}}
);
if (oppositeCanvasLoop.path !== {python_opposite_loop_path_json}) {{
  throw new Error('opposite canvas self-loop Python/JS parity drift: ' + oppositeCanvasLoop.path);
}}
if (!(oppositeCanvasLoop.labelX > 120)) {{
  throw new Error('opposite canvas self-loop label fell back inside the node');
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
