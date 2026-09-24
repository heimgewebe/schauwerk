from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

import pytest

from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import (
    NativeDocumentError,
    editing_document_to_json_canvas,
    json_canvas_to_editing_document,
    validate_json_canvas,
)

SVG_NS = "{http://www.w3.org/2000/svg}"


def _canvas() -> dict:
    return {
        "customTopLevel": {"kept": True},
        "nodes": [
            {
                "id": "gruppe",
                "type": "group",
                "x": -120,
                "y": 20,
                "width": 720,
                "height": 420,
                "label": "Bereich",
                "customNode": "keep",
            },
            {
                "id": "a",
                "type": "text",
                "x": -60,
                "y": 100,
                "width": 220,
                "height": 120,
                "text": "Äpfel & Öl",
                "color": "5",
            },
            {
                "id": "b",
                "type": "text",
                "x": 280,
                "y": 150,
                "width": 260,
                "height": 140,
                "text": "Ziel",
            },
        ],
        "edges": [
            {
                "id": "e1",
                "fromNode": "a",
                "fromSide": "right",
                "toNode": "b",
                "toSide": "left",
                "toEnd": "arrow",
                "label": "führt zu",
                "customEdge": 7,
            }
        ],
    }


@pytest.mark.parametrize(
    "background_fields",
    [
        {"background": "assets/background.png"},
        {"background": "assets/background.png", "backgroundStyle": "cover"},
        {"backgroundStyle": "repeat"},
    ],
)
def test_json_canvas_rejects_group_backgrounds_instead_of_silently_dropping_them(
    background_fields: dict[str, str],
) -> None:
    source = {
        "nodes": [
            {
                "id": "group",
                "type": "group",
                "x": 0,
                "y": 0,
                "width": 320,
                "height": 220,
                **background_fields,
            }
        ],
        "edges": [],
    }

    with pytest.raises(
        NativeDocumentError,
        match="group backgrounds are not supported by the native editor",
    ):
        json_canvas_to_editing_document(source, title="Unsupported background")


def test_json_canvas_markdown_is_normalized_for_display_without_roundtrip_loss() -> None:
    markdown = "# Heading\n[OpenAI](https://openai.com) **bold** __strong__ \x60code\x60"
    source = {
        "nodes": [
            {
                "id": "markdown",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 420,
                "height": 180,
                "text": markdown,
            }
        ],
        "edges": [],
    }

    document = json_canvas_to_editing_document(source, title="Markdown")
    assert document["nodes"][0]["label"] == markdown
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    rendered_text = "\n".join(
        (element.text or "")
        for element in root.findall(f".//{SVG_NS}text")
        if element.attrib.get("data-node-label") == "true"
    )
    assert "Heading" in rendered_text
    assert "OpenAI" in rendered_text
    assert "bold" in rendered_text
    assert "strong" in rendered_text
    assert "code" in rendered_text
    assert "# Heading" not in rendered_text
    assert "[OpenAI](https://openai.com)" not in rendered_text
    assert "**bold**" not in rendered_text
    assert "__strong__" not in rendered_text
    assert "\x60code\x60" not in rendered_text


def test_json_canvas_roundtrip_preserves_geometry_ids_order_and_extensions() -> None:
    source = _canvas()
    document = json_canvas_to_editing_document(source, title="Probe")

    geometry = [
        (node["x"], node["y"], node["width"], node["height"])
        for node in document["nodes"]
    ]
    assert geometry == [
        (-120, 20, 720, 420),
        (-60, 100, 220, 120),
        (280, 150, 260, 140),
    ]
    assert editing_document_to_json_canvas(document) == source


def test_editing_document_projects_geometry_text_and_edges_back_to_canvas() -> None:
    document = json_canvas_to_editing_document(_canvas(), title="Probe")
    by_id = {node["id"]: node for node in document["nodes"]}
    by_id["a"]["x"] += 41
    by_id["a"]["y"] -= 17
    by_id["a"]["label"] = "Geändert – 東京"
    document["edges"][0]["label"] = "neu"
    document["edges"].append(
        {
            "id": "e2",
            "from": "b",
            "to": "a",
            "label": "zurück",
            "from_side": None,
            "to_side": None,
            "from_end": "none",
            "to_end": "arrow",
            "source": {},
        }
    )

    output = editing_document_to_json_canvas(document)
    output_by_id = {node["id"]: node for node in output["nodes"]}
    assert output_by_id["a"]["x"] == -19
    assert output_by_id["a"]["y"] == 83
    assert output_by_id["a"]["text"] == "Geändert – 東京"
    assert output_by_id["gruppe"]["customNode"] == "keep"
    assert output["edges"][0]["customEdge"] == 7
    assert output["edges"][1] == {
        "id": "e2",
        "fromNode": "b",
        "toNode": "a",
        "label": "zurück",
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["nodes"].append(
                {
                    "id": "a",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 10,
                    "height": 10,
                    "text": "dup",
                }
            ),
            "duplicate",
        ),
        (
            lambda value: value["edges"][0].update({"toNode": "missing"}),
            "unknown node",
        ),
        (
            lambda value: value["nodes"][1].update({"type": "video"}),
            "unsupported",
        ),
        (
            lambda value: value["nodes"][1].update({"width": 0}),
            "between 1",
        ),
        (
            lambda value: value["nodes"][1].update({"x": 10.5}),
            "must be an integer",
        ),
    ],
)
def test_json_canvas_fails_closed_for_invalid_core(mutator, message: str) -> None:
    value = copy.deepcopy(_canvas())
    mutator(value)
    with pytest.raises(NativeDocumentError, match=message):
        validate_json_canvas(value)


def test_native_document_renderer_uses_canvas_bounds_and_edge_endpoints() -> None:
    document = json_canvas_to_editing_document(_canvas(), title="Probe")
    svg = render_native_editing_document(document)
    root = ET.fromstring(svg)

    assert root.attrib["data-document-mode"] == "json-canvas"
    assert root.attrib["data-renderer"] == "schauwerk-native-diagram-v1"
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-kind") == "node"
    }
    rect = next(child for child in nodes["a"] if child.tag == f"{SVG_NS}rect")
    assert rect.attrib["x"] == "-60"
    assert rect.attrib["y"] == "100"
    assert rect.attrib["width"] == "220"
    assert rect.attrib["height"] == "120"

    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "e1"
    )
    path = next(child for child in edge if child.tag == f"{SVG_NS}path")
    assert path.attrib["d"].startswith("M 160.0 160.0 C ")
    assert path.attrib["marker-end"] == "url(#canvas-arrow-0)"
    assert edge.attrib["data-route"] == "canvas-cubic"



def test_native_document_source_arrow_uses_start_aware_marker_direction() -> None:
    source = copy.deepcopy(_canvas())
    source["edges"][0]["fromEnd"] = "arrow"
    source["edges"][0]["toEnd"] = "none"
    document = json_canvas_to_editing_document(source, title="Source arrow")
    root = ET.fromstring(render_native_editing_document(document))

    marker = next(root.iter(f"{SVG_NS}marker"))
    assert marker.attrib["orient"] == "auto-start-reverse"
    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "e1"
    )
    path = next(child for child in edge if child.tag == f"{SVG_NS}path")
    assert path.attrib["marker-start"] == "url(#canvas-arrow-0)"
    assert "marker-end" not in path.attrib


def test_empty_json_canvas_roundtrips_and_renders_editable_workspace() -> None:
    document = json_canvas_to_editing_document({}, title="Leer")
    assert editing_document_to_json_canvas(document) == {}
    svg = render_native_editing_document(document)
    root = ET.fromstring(svg)
    assert root.attrib["data-document-mode"] == "json-canvas"
    assert root.attrib["viewBox"] == "0 0 1200 800"


def test_json_canvas_roundtrip_preserves_absent_group_label_and_explicit_default_ends() -> None:
    source = {
        "nodes": [
            {
                "id": "group",
                "type": "group",
                "x": 0,
                "y": 0,
                "width": 320,
                "height": 220,
            },
            {
                "id": "a",
                "type": "text",
                "x": 40,
                "y": 50,
                "width": 120,
                "height": 80,
                "text": "A",
            },
        ],
        "edges": [
            {
                "id": "loop",
                "fromNode": "a",
                "toNode": "a",
                "fromEnd": "none",
                "toEnd": "arrow",
            }
        ],
    }

    document = json_canvas_to_editing_document(source, title="Preservation")
    assert document["nodes"][0]["label"] == ""
    assert editing_document_to_json_canvas(document) == source



def test_native_document_reciprocal_edges_use_distinct_physical_lanes() -> None:
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "A",
            },
            {
                "id": "b",
                "type": "text",
                "x": 360,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "B",
            },
        ],
        "edges": [
            {"id": "ab", "fromNode": "a", "toNode": "b", "label": "hin"},
            {"id": "ba", "fromNode": "b", "toNode": "a", "label": "zurück"},
        ],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Reciprocal")
        )
    )
    edge_groups = {
        element.attrib["data-source-id"]: element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-kind") == "edge"
    }
    labels = {}
    paths = {}
    for edge_id, group in edge_groups.items():
        labels[edge_id] = next(
            child for child in group if child.tag == f"{SVG_NS}text"
        )
        paths[edge_id] = next(
            child for child in group if child.tag == f"{SVG_NS}path"
        )
    assert paths["ab"].attrib["d"] != paths["ba"].attrib["d"]
    assert labels["ab"].attrib["y"] != labels["ba"].attrib["y"]


def test_native_document_parallel_self_loops_use_distinct_routes() -> None:
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "A",
            }
        ],
        "edges": [
            {"id": f"loop-{index}", "fromNode": "a", "toNode": "a", "label": str(index)}
            for index in range(4)
        ],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Loops")
        )
    )
    paths = [
        next(child for child in group if child.tag == f"{SVG_NS}path").attrib["d"]
        for group in root.iter(f"{SVG_NS}g")
        if group.attrib.get("data-source-kind") == "edge"
    ]
    assert len(set(paths)) == 4


def test_native_document_self_loop_honors_explicit_endpoint_sides() -> None:
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 20,
                "y": 30,
                "width": 100,
                "height": 80,
                "text": "A",
            }
        ],
        "edges": [
            {
                "id": "loop",
                "fromNode": "a",
                "toNode": "a",
                "fromSide": "top",
                "toSide": "left",
            }
        ],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Explicit loop sides")
        )
    )
    edge_group = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "loop"
    )
    path = next(child for child in edge_group if child.tag == f"{SVG_NS}path")
    assert edge_group.attrib["data-route"] == "canvas-self-loop"
    assert path.attrib["d"] == (
        "M 55.0 30.0 C 55.0 -36.0, -46.0 87.6, 20.0 87.6"
    )


def test_native_document_viewbox_contains_outward_routed_edge_controls() -> None:
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
                "text": "A",
            },
            {
                "id": "b",
                "type": "text",
                "x": 300,
                "y": 0,
                "width": 100,
                "height": 100,
                "text": "B",
            },
        ],
        "edges": [
            {
                "id": "outward",
                "fromNode": "a",
                "fromSide": "left",
                "toNode": "b",
                "toSide": "right",
                "label": "outward route",
            }
        ],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Bounds")
        )
    )
    view_x, _view_y, view_width, _view_height = map(
        float, root.attrib["viewBox"].split()
    )
    assert view_x <= -140.0
    assert view_x + view_width >= 540.0




def test_native_document_groups_render_below_edges_and_ordinary_nodes() -> None:
    source = {
        "nodes": [
            {
                "id": "group",
                "type": "group",
                "x": -40,
                "y": -40,
                "width": 520,
                "height": 220,
                "label": "Bereich",
            },
            {
                "id": "a",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "A",
            },
            {
                "id": "b",
                "type": "text",
                "x": 300,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "B",
            },
        ],
        "edges": [
            {
                "id": "e",
                "fromNode": "a",
                "toNode": "b",
                "label": "A nach B",
            }
        ],
    }
    svg = render_native_editing_document(
        json_canvas_to_editing_document(source, title="Layering")
    )

    group_index = svg.index('id="native-node-group"')
    edge_index = svg.index('id="native-edge-e"')
    node_index = svg.index('id="native-node-a"')
    assert group_index < edge_index < node_index




def test_json_canvas_rejects_ids_that_would_collapse_in_xml() -> None:
    for invalid_id in ("same\x01", "same\x02"):
        source = {
            "nodes": [
                {
                    "id": invalid_id,
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 120,
                    "height": 80,
                    "text": "invalid id",
                }
            ]
        }
        with pytest.raises(NativeDocumentError, match="XML 1.0-compatible"):
            validate_json_canvas(source)


@pytest.mark.parametrize(
    ("invalid_id", "normalized_peer"),
    [
        ("a\tb", "a b"),
        ("a\nb", "a b"),
        ("a\rb", "a b"),
    ],
)
def test_json_canvas_rejects_ids_that_xml_attributes_would_normalize_together(
    invalid_id: str,
    normalized_peer: str,
) -> None:
    source = {
        "nodes": [
            {
                "id": invalid_id,
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "normalized",
            },
            {
                "id": normalized_peer,
                "type": "text",
                "x": 180,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "peer",
            },
        ]
    }

    with pytest.raises(NativeDocumentError, match="attribute-stable"):
        validate_json_canvas(source)


def test_native_document_long_edge_label_is_clipped_to_reserved_box() -> None:
    source = {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "A",
            },
            {
                "id": "b",
                "type": "text",
                "x": 360,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "B",
            },
        ],
        "edges": [
            {
                "id": "long",
                "fromNode": "a",
                "toNode": "b",
                "label": "X" * 500,
            }
        ],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Long label")
        )
    )
    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "long"
    )
    text = next(child for child in edge if child.tag == f"{SVG_NS}text")
    visible_rect = next(child for child in edge if child.tag == f"{SVG_NS}rect")
    clip = next(edge.iter(f"{SVG_NS}clipPath"))
    clip_rect = next(clip.iter(f"{SVG_NS}rect"))

    assert text.attrib["clip-path"].startswith("url(#canvas-edge-label-")
    assert float(visible_rect.attrib["width"]) == 260.0
    assert clip_rect.attrib["width"] == visible_rect.attrib["width"]
    assert clip_rect.attrib["height"] == visible_rect.attrib["height"]




def test_native_document_node_labels_are_clipped_to_node_box() -> None:
    source = {
        "nodes": [
            {
                "id": "wide",
                "type": "text",
                "x": 20,
                "y": 30,
                "width": 1000,
                "height": 100,
                "text": "W" * 500,
            }
        ]
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Wide node label")
        )
    )
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "wide"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]
    assert texts
    assert all(
        item.attrib["clip-path"] == "url(#canvas-node-label-0)"
        for item in texts
    )
    clip = next(node.iter(f"{SVG_NS}clipPath"))
    clip_rect = next(clip.iter(f"{SVG_NS}rect"))
    assert clip_rect.attrib == {
        "x": "20",
        "y": "30",
        "width": "1000",
        "height": "100",
    }



def test_native_document_renderer_sanitizes_xml_forbidden_text_and_markup() -> None:
    source = {
        "nodes": [
            {
                "id": "hostile",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 260,
                "height": 120,
                "text": "</text><script>alert(1)</script>\x01",
            }
        ]
    }
    document = json_canvas_to_editing_document(source, title="XML")
    svg = render_native_editing_document(document)
    root = ET.fromstring(svg)

    assert list(root.iter(f"{SVG_NS}script")) == []
    assert "<script>" not in svg
    assert "\ufffd" in svg
