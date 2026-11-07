"""Known-red geometry regression for follow-up obstacle-aware Canvas edge routing."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.standalone_editor import NATIVE_IMPORT_SCHEMA, _native_product_input


@pytest.mark.xfail(
    strict=True,
    reason="E0 baseline: a native Canvas edge label overlaps an intervening node",
)
def test_native_canvas_edge_label_avoids_intervening_node() -> None:
    """Require obstacle-free labels once the smart-routing slice is implemented."""
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 0, "y": 0, "width": 120, "height": 80, "text": "Start",
            },
            {
                "id": "blocker",
                "type": "text",
                "x": 230, "y": 0, "width": 120, "height": 80,
                "text": "Zwischenknoten",
            },
            {
                "id": "b",
                "type": "text",
                "x": 400, "y": 0, "width": 120, "height": 80, "text": "Ziel",
            },
        ],
        "edges": [
            {
                "id": "edge", "fromNode": "a", "toNode": "b",
                "label": "Verbindung", "toEnd": "arrow",
            }
        ],
    }
    request = {
        "schema_version": NATIVE_IMPORT_SCHEMA,
        "format": "json-canvas-1.0",
        "source": source,
        "title": "Routing-Regression.canvas",
    }
    svg = render_native_editing_document(_native_product_input(request))
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    edge = next(
        item for item in root.iter(ns + "g")
        if item.get("data-source-kind") == "edge"
        and item.get("data-source-id") == "edge"
    )
    blocker = next(
        item for item in root.iter(ns + "g")
        if item.get("data-source-kind") == "node"
        and item.get("data-source-id") == "blocker"
    )
    label = next(
        rect for rect in edge.findall(ns + "rect")
        if float(rect.get("width", "0")) > 0
    )
    node_rect = blocker.find(ns + "rect")
    assert node_rect is not None

    def bounds(rect: ET.Element) -> tuple[float, float, float, float]:
        x = float(rect.get("x", "0"))
        y = float(rect.get("y", "0"))
        return (
            x, y,
            x + float(rect.get("width", "0")),
            y + float(rect.get("height", "0")),
        )

    ax, ay, ar, ab = bounds(label)
    bx, by, br, bb = bounds(node_rect)
    assert not (ax < br and ar > bx and ay < bb and ab > by)


def test_native_viewer_edge_hit_targets_follow_real_path() -> None:
    """Keyboard and pointer affordances are viewer-only and retained on reroute."""
    from schauwerk.resources.native_viewer.assets import ASSETS

    app = ASSETS["app.js"]
    styles = ASSETS["styles.css"]
    assert 'edgeState.hitPath.setAttribute("d", geometry.path)' in app
    assert 'edgeState.hitPath.setAttribute("d", edgeState.basePath)' in app
    assert 'hitPath.setAttribute("vector-effect", "non-scaling-stroke")' in app
    assert 'edgeGroup.insertBefore(hitPath, labelRect)' in app
    assert 'edgeGroup.setAttribute("tabindex", "0")' in app
    assert 'edgeGroup.setAttribute("role", "button")' in app
    assert 'path.native-edge-hit' in styles
    assert 'stroke-width: 24px !important;' in styles
