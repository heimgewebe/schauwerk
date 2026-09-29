from __future__ import annotations

import copy
import re
import unicodedata
import xml.etree.ElementTree as ET

import pytest

import schauwerk.visual.native_diagram as native_diagram
from schauwerk.visual.grapheme import (
    MAX_GRAPHEME_CLUSTER_CODEPOINTS,
    bounded_grapheme_prefix,
    iter_grapheme_clusters,
)
from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import (
    NativeDocumentError,
    editing_document_to_json_canvas,
    json_canvas_to_editing_document,
    validate_json_canvas,
)

SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("\r\n", ["\r\n"]),
        ("\u1100\u1161\u11A8", ["\u1100\u1161\u11A8"]),
        ("\u0600A", ["\u0600A"]),
        ("A\u0903", ["A\u0903"]),
        ("🇩🇪🇺🇸", ["🇩🇪", "🇺🇸"]),
        ("क्ष", ["क्ष"]),
        ("👨‍👩‍👧‍👦", ["👨‍👩‍👧‍👦"]),
    ],
)
def test_stdlib_grapheme_segmenter_covers_uax29_rules(
    value: str,
    expected: list[str],
) -> None:
    assert list(iter_grapheme_clusters(value)) == expected


def test_bounded_grapheme_prefix_stops_before_pathological_cluster() -> None:
    accepted = "e" + "\u0301" * (MAX_GRAPHEME_CLUSTER_CODEPOINTS - 1)
    bounded_accepted, accepted_truncated = bounded_grapheme_prefix(accepted)
    assert bounded_accepted == accepted
    assert accepted_truncated is False

    prefix = "safe "
    value = (
        prefix
        + "e"
        + "\u0301" * MAX_GRAPHEME_CLUSTER_CODEPOINTS
        + " remains hidden"
    )

    bounded, truncated = bounded_grapheme_prefix(value)

    assert truncated is True
    assert bounded == prefix
    assert list(iter_grapheme_clusters(bounded)) == list(prefix)


def test_bounded_grapheme_prefix_stops_at_cluster_limit_without_splitting() -> None:
    family = "👨‍👩‍👧‍👦"
    value = family * 3

    bounded, truncated = bounded_grapheme_prefix(value, max_clusters=2)

    assert truncated is True
    assert bounded == family * 2
    assert list(iter_grapheme_clusters(bounded)) == [family, family]


def test_bounded_grapheme_prefix_cluster_limit_handles_ascii_crlf() -> None:
    bounded, truncated = bounded_grapheme_prefix("a\r\nbc", max_clusters=2)

    assert truncated is True
    assert bounded == "a\r\n"


def test_bounded_grapheme_prefix_codepoint_limit_preserves_cluster_boundaries() -> None:
    family = "👨‍👩‍👧‍👦"
    bounded, truncated = bounded_grapheme_prefix(
        family * 2,
        max_codepoints=len(family) + 2,
    )

    assert truncated is True
    assert bounded == family

    ascii_bounded, ascii_truncated = bounded_grapheme_prefix(
        "a\r\nb",
        max_codepoints=2,
    )
    assert ascii_truncated is True
    assert ascii_bounded == "a"


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


@pytest.mark.parametrize("unsafe_integer", [1 << 53, -(1 << 53)])
def test_json_canvas_rejects_unsafe_extension_integers_before_roundtrip(
    unsafe_integer: int,
) -> None:
    source = _canvas()
    source["customTopLevel"] = {"nested": [{"revision": unsafe_integer}]}

    with pytest.raises(NativeDocumentError, match="JavaScript safe-integer range"):
        validate_json_canvas(source)

    source["customTopLevel"]["nested"][0]["revision"] = (1 << 53) - 1
    assert (
        validate_json_canvas(source)["customTopLevel"]["nested"][0]["revision"]
        == (1 << 53) - 1
    )


@pytest.mark.parametrize(
    ("unsafe_number", "message"),
    [
        (float(1 << 53), "safe-integer range"),
        (-float(1 << 53), "safe-integer range"),
        (float("inf"), "must be finite"),
        (float("-inf"), "must be finite"),
    ],
)
def test_json_canvas_rejects_unsafe_extension_float_numbers(
    unsafe_number: float,
    message: str,
) -> None:
    source = _canvas()
    source["customTopLevel"] = {"nested": [{"revision": unsafe_number}]}

    with pytest.raises(NativeDocumentError, match=message):
        validate_json_canvas(source)

    source["customTopLevel"]["nested"][0]["revision"] = 0.1
    assert validate_json_canvas(source)["customTopLevel"]["nested"][0]["revision"] == 0.1


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


def test_native_document_marks_pathological_edge_grapheme_as_truncated() -> None:
    label = "e" + "\u0301" * (MAX_GRAPHEME_CLUSTER_CODEPOINTS + 4096)
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
                "id": "pathological-edge",
                "fromNode": "a",
                "toNode": "b",
                "label": label,
            }
        ],
    }

    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Pathological edge cluster")
        )
    )
    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "pathological-edge"
    )
    text = next(child for child in edge if child.tag == f"{SVG_NS}text")

    assert edge.attrib["data-text-truncated"] == "true"
    assert text.text == "…"


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




@pytest.mark.parametrize(
    ("node_id", "width", "height", "label", "needles"),
    [
        (
            "start",
            280,
            180,
            "# Start\n\nDies ist eine **JSON-Canvas-Testdatei** für Schaubild."
            "\n\n- Markdown\n- Unicode: ä ö ü ß → ✓\n- Mehrzeiliger Text",
            ("Unicode: ä ö ü ß → ✓", "Mehrzeiliger Text"),
        ),
        (
            "special",
            200,
            170,
            "### Zeichen\n\n\x60<tag>\x60\n\n\x60A & B\x60\n\n"
            "\"Quotes\" & 'Apostrophes'\n\n🙂",
            ("Apostrophes", "🙂"),
        ),
    ],
)
def test_native_document_adaptively_fits_live_canvas_text_without_geometry_change(
    node_id: str,
    width: int,
    height: int,
    label: str,
    needles: tuple[str, ...],
) -> None:
    source = {
        "nodes": [
            {
                "id": node_id,
                "type": "text",
                "x": 20,
                "y": 30,
                "width": width,
                "height": height,
                "text": label,
            }
        ]
    }
    document = json_canvas_to_editing_document(source, title="Live clipping regression")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == node_id
    )
    assert "data-text-truncated" not in node.attrib

    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]
    assert texts
    rendered = "".join(item.text or "" for item in texts)
    def compact(value: str) -> str:
        return re.sub(r"\s+", "", value)

    for needle in needles:
        assert compact(needle) in compact(rendered)

    font_sizes = {int(item.attrib["font-size"]) for item in texts}
    assert min(font_sizes) >= 12
    assert max(font_sizes) <= 16
    assert all(float(item.attrib["y"]) <= 30 + height - 5 for item in texts)

    clip = next(node.iter(f"{SVG_NS}clipPath"))
    clip_rect = next(clip.iter(f"{SVG_NS}rect"))
    assert clip_rect.attrib == {
        "x": "20",
        "y": "30",
        "width": str(width),
        "height": str(height),
    }


def test_native_document_canvas_text_fit_handles_cjk_emoji_url_and_long_token() -> None:
    label = (
        "日本語の長い文章テスト🙂\n\n"
        "https://example.com/very/long/path/without-breaks\n\n"
        "SUPERCALIFRAGILISTICEXPIALIDOCIOUS"
    )
    source = {
        "nodes": [
            {
                "id": "i18n",
                "type": "text",
                "x": -10,
                "y": 5,
                "width": 280,
                "height": 200,
                "text": label,
            }
        ]
    }
    document = json_canvas_to_editing_document(source, title="Unicode wrapping")
    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "i18n"
    )
    assert "data-text-truncated" not in node.attrib
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]
    rendered_compact = re.sub(r"\s+", "", "".join(texts))
    for token in (
        "日本語の長い文章テスト🙂",
        "https://example.com/very/long/path/without-breaks",
        "SUPERCALIFRAGILISTICEXPIALIDOCIOUS",
    ):
        assert re.sub(r"\s+", "", token) in rendered_compact
    assert all(len(line) >= 4 for line in texts if line)



def test_native_document_canvas_text_output_is_bounded_across_document() -> None:
    first = "\n".join(f"first-{index}" for index in range(1500))
    second = "\n".join(f"second-{index}" for index in range(1500))
    source = {
        "nodes": [
            {
                "id": "first",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 240,
                "height": 1_000_000,
                "text": first,
            },
            {
                "id": "second",
                "type": "text",
                "x": 320,
                "y": 0,
                "width": 240,
                "height": 1_000_000,
                "text": second,
            },
        ]
    }

    svg = render_native_editing_document(
        json_canvas_to_editing_document(source, title="Bounded amplification")
    )
    root = ET.fromstring(svg)
    rendered_lines = [
        element
        for element in root.iter(f"{SVG_NS}text")
        if element.attrib.get("data-node-label") == "true"
    ]
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") in {"first", "second"}
    }

    assert len(rendered_lines) == 2048
    assert "data-text-truncated" not in nodes["first"].attrib
    assert nodes["second"].attrib["data-text-truncated"] == "true"
    assert len(svg.encode("utf-8")) < 2_000_000


def test_native_document_canvas_full_width_glyphs_fit_conservative_width() -> None:
    label = "漢" * 20
    source = {
        "nodes": [
            {
                "id": "cjk",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 316,
                "height": 100,
                "text": label,
            }
        ]
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="CJK width")
        )
    )
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "cjk"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(item.text or "" for item in texts) == label
    assert texts
    assert all(
        len(item.text or "") * int(item.attrib["font-size"]) <= 288
        for item in texts
    )




@pytest.mark.parametrize("label", ["1\ufe0f\u20e3", "\u00a9\ufe0f"])
def test_native_document_canvas_emoji_presentation_clusters_use_full_width_budget(
    label: str,
) -> None:
    source = {
        "nodes": [
            {
                "id": "emoji-presentation",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 40,
                "height": 50,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(
        source, title="Emoji presentation width"
    )
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "emoji-presentation"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert [item.text or "" for item in texts] == [label]
    assert all(int(item.attrib["font-size"]) <= 12 for item in texts)


def test_native_document_canvas_zwnj_clusters_do_not_consume_visible_width() -> None:
    cluster = "a\u200c"
    label = cluster * 10
    source = {
        "nodes": [
            {
                "id": "zwnj",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 128,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="ZWNJ grapheme width")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "zwnj"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label
    assert texts


@pytest.mark.parametrize(
    "control",
    [
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
        "\u206a",
        "\u206b",
        "\u206c",
        "\u206d",
        "\u206e",
        "\u206f",
    ],
)
def test_canvas_bidi_format_controls_have_zero_advance(control: str) -> None:
    assert native_diagram._estimated_canvas_wrap_width(control * 10, size=12) == 0.0


def test_native_document_canvas_zero_advance_bidi_controls_bypass_legacy_wrap() -> None:
    label = "\u200f" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "bidi-zero-advance",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 148,
                "height": 60,
                "text": label,
            }
        ],
        "edges": [],
    }
    assert native_diagram._estimated_canvas_wrap_width(label, size=16) <= 120

    document = json_canvas_to_editing_document(source, title="Bidi zero advance")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "bidi-zero-advance"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert texts == [label]


def test_canvas_bidi_scope_projection_reopens_wrapped_override() -> None:
    projected, truncated = native_diagram._canvas_project_bidi_wrapped_lines(
        ["\u202eabcd", "efgh", "ijkl", "mno\u202c"]
    )

    assert truncated is False
    assert projected == [
        "\u202eabcd\u202c",
        "\u202eefgh\u202c",
        "\u202eijkl\u202c",
        "\u202emno\u202c",
    ]


def test_canvas_bidi_scope_projection_resolves_fsi_across_wrapped_lines() -> None:
    projected, truncated = native_diagram._canvas_project_bidi_wrapped_lines(
        ["\u2068---", "אבג", "\u2069"]
    )

    assert truncated is False
    assert projected == [
        "\u2067---\u2069",
        "\u2067אבג\u2069",
        "\u2067\u2069",
    ]


def test_canvas_adaptive_lines_resolves_truncated_fsi_from_complete_source() -> None:
    value = "\u2068" + "12345678901234567890" + "אבג" + "\u2069"

    lines, truncated = native_diagram._canvas_adaptive_lines(
        value,
        size=12,
        max_width=48,
        max_lines=1,
    )

    assert truncated is True
    assert lines
    rendered = lines[0][0]
    assert rendered.startswith("\u2067")
    assert rendered.endswith("\u2069")
    assert "אבג" not in rendered


@pytest.mark.parametrize(
    "separator",
    ["\u001c", "\u001d", "\u001e", "\u0085", "\u2029"],
)
def test_canvas_bidi_scope_projection_resets_at_unicode_paragraph_boundary(
    separator: str,
) -> None:
    assert unicodedata.bidirectional(separator) == "B"

    projected, truncated = native_diagram._canvas_project_bidi_wrapped_lines(
        [f"\u202eAB{separator}", "CD"]
    )

    assert truncated is False
    assert projected == [f"\u202eAB\u202c{separator}", "CD"]


def test_canvas_fsi_resolution_stops_at_unicode_paragraph_boundary() -> None:
    value = "\u2068---\u2029אבג\u2069"

    assert native_diagram._canvas_resolve_fsi_opener(value, 0) == "\u2066"
    projected, truncated = native_diagram._canvas_project_bidi_wrapped_lines(
        ["\u2068---\u2029", "אבג\u2069"]
    )

    assert truncated is False
    assert projected == ["\u2066---\u2069\u2029", "אבג\u2069"]


def test_canvas_bidi_scope_projection_resets_at_source_line_boundary() -> None:
    lines, truncated = native_diagram._canvas_adaptive_lines(
        "\u202eabcd\nEFGH",
        size=16,
        max_width=200,
        max_lines=8,
    )

    assert truncated is False
    assert [line for line, _ in lines] == ["\u202eabcd\u202c", "EFGH"]


def test_canvas_bidi_scope_projection_fails_closed_past_depth_limit() -> None:
    label = (
        "\u202e" * (native_diagram._CANVAS_MAX_BIDI_SCOPE_DEPTH + 1)
        + "a"
        + "\u202c" * (native_diagram._CANVAS_MAX_BIDI_SCOPE_DEPTH + 1)
    )

    projected, truncated = native_diagram._canvas_project_bidi_wrapped_lines([label])

    assert truncated is True
    assert projected == ["…"]


def test_canvas_bidi_scope_byte_limit_keeps_emitted_line_balanced() -> None:
    layout = native_diagram._CanvasTextLayout(
        size=16,
        lines=(("\u202eabcdefghijklmno\u202c", 28),),
        truncated=False,
    )

    limited = native_diagram._canvas_limit_text_layout_bytes(
        layout,
        max_width=200,
        max_bytes=18,
    )

    assert limited.truncated is True
    assert limited.lines
    rendered = limited.lines[0][0]
    assert native_diagram._canvas_escaped_text_bytes(rendered) <= 18
    assert rendered == "…" or (
        rendered.startswith("\u202e") and rendered.endswith("\u202c")
    )


def test_native_document_canvas_preserves_bidi_scope_across_wrapped_lines() -> None:
    label = "\u202eabcdefghijklmno\u202c"
    source = {
        "nodes": [
            {
                "id": "bidi-scope",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 80,
                "height": 120,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Bidi scope")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "bidi-scope"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert texts == [
        "\u202eabcd\u202c",
        "\u202eefgh\u202c",
        "\u202eijkl\u202c",
        "\u202emno\u202c",
    ]
    assert "".join(item[1:-1] for item in texts) == "abcdefghijklmno"


@pytest.mark.parametrize(
    ("character", "expected_width"),
    [
        ("\u000b", 1.15),
        ("\u0085", 0.0),
        ("\u00a0", 0.35),
        ("\u1680", 0.50),
        ("\u2000", 0.60),
        ("\u2001", 1.12),
        ("\u2002", 0.55),
        ("\u2003", 1.05),
        ("\u2004", 0.35),
        ("\u2005", 0.28),
        ("\u2006", 0.20),
        ("\u2007", 0.70),
        ("\u2008", 0.35),
        ("\u2009", 0.22),
        ("\u200a", 0.12),
        ("\u2028", 0.35),
        ("\u2029", 0.35),
        ("\u202f", 0.22),
        ("\u205f", 0.32),
        ("\u3000", 1.05),
    ],
)
def test_native_document_canvas_noncollapsible_whitespace_width_is_conservative(
    character: str,
    expected_width: float,
) -> None:
    assert native_diagram._canvas_is_non_collapsible_whitespace(character) is True
    assert native_diagram._canvas_is_collapsible_inline_whitespace(character) is False
    assert native_diagram._canvas_character_width_units(character) == pytest.approx(
        expected_width
    )
    assert native_diagram._estimated_canvas_wrap_width(
        character, size=16
    ) == pytest.approx(expected_width * 16)


def test_canvas_single_line_edge_whitespace_matches_svg_collapse() -> None:
    label = "\n".join(["a"] * 24)

    assert native_diagram._estimated_canvas_wrap_width(label, size=14) == pytest.approx(
        235.2
    )
    assert native_diagram._estimated_canvas_single_line_width(
        label, size=14
    ) > 240

    fitted, truncated = native_diagram._canvas_fit_single_line(
        label,
        size=14,
        max_width=240,
        max_bytes=2048,
    )

    assert truncated is True
    assert fitted.endswith("…")
    assert "\n" in fitted


def test_native_document_canvas_edge_line_breaks_are_marked_when_truncated() -> None:
    label = "\n".join(["a"] * 24)
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
                "x": 480,
                "y": 0,
                "width": 120,
                "height": 80,
                "text": "B",
            },
        ],
        "edges": [
            {
                "id": "edge-line-breaks",
                "fromNode": "a",
                "toNode": "b",
                "label": label,
            }
        ],
    }
    document = json_canvas_to_editing_document(source, title="Edge line breaks")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "edge-line-breaks"
    )
    texts = [child.text or "" for child in edge if child.tag == f"{SVG_NS}text"]

    assert edge.attrib.get("data-text-truncated") == "true"
    assert len(texts) == 1
    assert texts[0].endswith("…")
    assert texts[0] != label


def test_canvas_xml_forbidden_controls_measure_replacement_glyph() -> None:
    label = "\x01" * 8

    assert native_diagram._xml_10_character_allowed("\x01") is False
    assert native_diagram._xml_escape("\x01") == "\uFFFD"
    assert native_diagram._canvas_character_width_units("\x01") == pytest.approx(
        native_diagram._CANVAS_XML_REPLACEMENT_WIDTH_UNITS
    )
    assert native_diagram._estimated_canvas_wrap_width(label, size=14) > 80

    fitted, truncated = native_diagram._canvas_fit_single_line(
        label,
        size=14,
        max_width=80,
        max_bytes=2048,
    )

    assert truncated is True
    assert fitted.endswith("…")


def test_native_document_canvas_nonbreaking_space_is_not_a_wrap_separator() -> None:
    label = "AAAA\u00a0BBBB"

    assert native_diagram._canvas_collapse_inline_whitespace(label) == label
    assert native_diagram._canvas_has_non_collapsible_whitespace(label) is True
    assert native_diagram._canvas_plain_markdown("\u00a0A\u00a0") == "\u00a0A\u00a0"

    wrapped, wrapped_truncated = native_diagram._canvas_wrap_source_line(
        label,
        size=16,
        max_width=42,
        max_lines=4,
    )
    assert wrapped_truncated is False
    assert "".join(wrapped) == label
    assert sum(line.count("\u00a0") for line in wrapped) == 1

    layout = native_diagram._canvas_text_layout(
        label,
        42,
        100,
        max_lines=5,
        max_bytes=256,
    )
    assert "\u00a0" in "".join(line for line, _ in layout.lines)

    source = {
        "nodes": [
            {
                "id": "nbsp",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 70,
                "height": 70,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="NBSP")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "nbsp"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "".join(texts) == label
    assert "".join(texts).count("\u00a0") == 1


@pytest.mark.parametrize("label", ["\u00a0", "\u202f"])
def test_native_document_canvas_noncollapsible_whitespace_only_node_label_is_preserved(
    label: str,
) -> None:
    assert native_diagram._canvas_has_layout_content(label) is True
    assert native_diagram._canvas_has_layout_content(" \t\r\n") is False

    source = {
        "nodes": [
            {
                "id": "noncollapsible-whitespace",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 60,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(
        source, title="Non-collapsible whitespace node"
    )
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "noncollapsible-whitespace"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert texts == [label]


@pytest.mark.parametrize("label", ["\u00a0", "\u202f"])
def test_native_document_canvas_noncollapsible_whitespace_only_edge_label_is_preserved(
    label: str,
) -> None:
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
                "id": "noncollapsible-whitespace-edge",
                "fromNode": "a",
                "toNode": "b",
                "label": label,
            }
        ],
    }
    document = json_canvas_to_editing_document(
        source, title="Non-collapsible whitespace edge"
    )
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    edge = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id")
        == "noncollapsible-whitespace-edge"
    )
    texts = [
        child.text or ""
        for child in edge
        if child.tag == f"{SVG_NS}text"
    ]

    assert "data-text-truncated" not in edge.attrib
    assert texts == [label]


@pytest.mark.parametrize(
    ("label", "display"),
    [
        ("abc          def", "abc def"),
        ("abc\t\tdef", "abc def"),
    ],
)
def test_native_document_canvas_collapses_inline_svg_whitespace_for_layout(
    label: str,
    display: str,
) -> None:
    assert native_diagram._estimated_canvas_wrap_width(
        label, size=16
    ) == native_diagram._estimated_canvas_wrap_width(display, size=16)
    fitted, truncated = native_diagram._canvas_fit_single_line(
        label,
        size=16,
        max_width=92,
        max_bytes=256,
    )
    assert fitted == label
    assert truncated is False
    wrapped, wrapped_truncated = native_diagram._canvas_wrap_source_line(
        label,
        size=16,
        max_width=92,
        max_lines=2,
    )
    assert wrapped == [label]
    assert wrapped_truncated is False

    source = {
        "nodes": [
            {
                "id": "collapsible-whitespace",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Collapsible whitespace")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "collapsible-whitespace"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert texts == [label]
    assert native_diagram._canvas_collapse_inline_whitespace(texts[0]) == display


@pytest.mark.parametrize(
    "control",
    [
        "\u00ad",
        "\u180e",
        "\u200b",
        "\u2060",
        "\u2061",
        "\u2062",
        "\u2063",
        "\u2064",
        "\ufeff",
    ],
)
def test_canvas_invisible_format_controls_have_zero_advance(control: str) -> None:
    assert native_diagram._estimated_canvas_wrap_width(control * 10, size=12) == 0.0


def test_native_document_canvas_mongolian_vowel_separator_keeps_visible_text() -> None:
    label = "\u180e" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "mongolian-vowel-separator",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Mongolian vowel separator")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "mongolian-vowel-separator"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_soft_hyphen_keeps_visible_text() -> None:
    label = "\u00ad" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "soft-hyphen",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Soft hyphen")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "soft-hyphen"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_canvas_spacing_combining_mark_uses_script_cluster_calibration() -> None:
    base = "\u0915"
    spacing_mark = "\u093e"
    cluster = base + spacing_mark
    size = 12

    base_width = native_diagram._estimated_canvas_wrap_width(base, size=size)
    cluster_width = native_diagram._estimated_canvas_wrap_width(cluster, size=size)
    full_mark_width = native_diagram._canvas_character_width_units(spacing_mark) * size

    assert base_width < cluster_width < base_width + full_mark_width
    assert cluster_width == pytest.approx(1.20 * size)


def test_canvas_spacing_mark_unknown_script_falls_back_to_full_width() -> None:
    cluster = "\ua984\ua9b4"
    visible = list(cluster)

    assert native_diagram._canvas_grapheme_width_units(cluster) == pytest.approx(
        sum(native_diagram._canvas_character_width_units(item) for item in visible)
    )


def test_native_document_canvas_spacing_marks_do_not_force_premature_truncation() -> None:
    label = "का" * 6
    source = {
        "nodes": [
            {
                "id": "spacing-marks",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }

    document = json_canvas_to_editing_document(source, title="Spacing marks")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "spacing-marks"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_zero_width_space_preserves_visible_text() -> None:
    label = "\u200b" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "zero-width-space",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Zero-width space")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "zero-width-space"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_deprecated_bidi_controls_preserve_visible_text() -> None:
    label = "\u206a" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "deprecated-bidi-controls",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Deprecated bidi controls")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "deprecated-bidi-controls"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_bidi_controls_do_not_consume_visible_width() -> None:
    label = "\u200f" * 10 + "abcdefghij"
    source = {
        "nodes": [
            {
                "id": "bidi-controls",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Bidi controls width")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "bidi-controls"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_control_only_zwnj_cluster_has_zero_width() -> None:
    label = "\u200c" * 10 + "a" * 10
    source = {
        "nodes": [
            {
                "id": "zwnj-only",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 118,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(
        source,
        title="Control-only ZWNJ width",
    )
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "zwnj-only"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_canvas_non_pictographic_zwj_uses_script_width_not_emoji_width() -> None:
    malayalam_chillu = "\u0d23\u0d4d\u200d"
    devanagari_conjunct = "\u0915\u094d\u200d\u0937"
    emoji_family = "👨‍👩‍👧‍👦"

    assert native_diagram._canvas_grapheme_width_units(malayalam_chillu) == pytest.approx(
        native_diagram._CANVAS_SCRIPT_ZWJ_MIN_WIDTH_UNITS
    )
    assert native_diagram._canvas_grapheme_width_units(devanagari_conjunct) == pytest.approx(1.8)
    assert native_diagram._canvas_grapheme_width_units(emoji_family) == pytest.approx(2.0)


def test_native_document_canvas_non_pictographic_zwj_does_not_force_truncation() -> None:
    cluster = "\u0d23\u0d4d\u200d"
    label = cluster * 4
    source = {
        "nodes": [
            {
                "id": "script-zwj",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 120,
                "height": 40,
                "text": label,
            }
        ],
        "edges": [],
    }

    document = json_canvas_to_editing_document(source, title="Script ZWJ")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "script-zwj"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label


def test_native_document_canvas_wrap_preserves_zwj_grapheme_clusters() -> None:
    family = "👨‍👩‍👧‍👦"
    label = family * 5
    source = {
        "nodes": [
            {
                "id": "family",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 250,
                "height": 50,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="ZWJ grapheme wrapping")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "family"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert texts == [label]
    assert all(not line.startswith("\u200d") and not line.endswith("\u200d") for line in texts)


def test_native_document_marks_pathological_grapheme_cluster_as_truncated() -> None:
    label = "e" + "\u0301" * (MAX_GRAPHEME_CLUSTER_CODEPOINTS + 4096)
    source = {
        "nodes": [
            {
                "id": "pathological-cluster",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 180,
                "height": 80,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Pathological cluster")
    assert editing_document_to_json_canvas(document) == source

    svg = render_native_editing_document(document)
    root = ET.fromstring(svg)
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "pathological-cluster"
    )
    rendered = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert node.attrib["data-text-truncated"] == "true"
    assert rendered == ["…"]
    assert len(svg.encode("utf-8")) < 20_000


def test_native_document_canvas_wrap_preserves_combining_mark_clusters() -> None:
    cluster = "e\u0301"
    label = cluster * 24
    source = {
        "nodes": [
            {
                "id": "combining",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 140,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Combining mark wrapping")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "combining"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label
    assert len(texts) >= 2
    assert all(
        line
        and not line.startswith("\u0301")
        and line.count("e") == line.count("\u0301")
        for line in texts
    )


def test_native_document_canvas_wrap_preserves_indic_conjunct_grapheme_clusters() -> None:
    conjunct = "\u0915\u094d\u0937"
    label = conjunct * 8
    source = {
        "nodes": [
            {
                "id": "indic-conjunct",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 60,
                "height": 220,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Indic conjunct wrapping")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "indic-conjunct"
    )
    texts = [
        child.text or ""
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(texts) == label
    assert len(texts) >= 2
    assert all(line and line.replace(conjunct, "") == "" for line in texts)


def test_native_document_numeric_run_uses_conservative_bold_fallback_width() -> None:
    label = "0" * 30
    source = {
        "nodes": [
            {
                "id": "digits",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 307,
                "height": 80,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Numeric fallback width")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "digits"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(item.text or "" for item in texts) == label
    assert len(texts) >= 2
    assert texts[0].attrib["font-weight"] == "700"
    assert all(
        len(item.text or "") * int(item.attrib["font-size"]) * 0.70 <= 279
        for item in texts
    )


def test_native_document_narrow_punctuation_uses_conservative_fallback_width() -> None:
    label = "{" * 40
    source = {
        "nodes": [
            {
                "id": "punctuation",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 307,
                "height": 80,
                "text": label,
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Punctuation fallback width")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "punctuation"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert "data-text-truncated" not in node.attrib
    assert "".join(item.text or "" for item in texts) == label
    assert len(texts) >= 2
    assert all(
        len(item.text or "") * int(item.attrib["font-size"]) * 0.70 <= 279
        for item in texts
    )


def test_native_document_canvas_text_budget_reserves_later_visible_labels() -> None:
    source = {
        "nodes": [
            {
                "id": "huge",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 240,
                "height": 1_000_000,
                "text": "\n".join(f"line-{index}" for index in range(2048)),
            },
            {
                "id": "later",
                "type": "text",
                "x": 320,
                "y": 0,
                "width": 240,
                "height": 100,
                "text": "Visible label",
            },
        ],
        "edges": [],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Fair text budget")
        )
    )
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") in {"huge", "later"}
    }
    all_text = [
        element
        for element in root.iter(f"{SVG_NS}text")
        if element.attrib.get("data-node-label") == "true"
    ]
    later_text = [
        element.text or ""
        for element in nodes["later"]
        if element.tag == f"{SVG_NS}text"
        and element.attrib.get("data-node-label") == "true"
    ]

    assert len(all_text) == 2048
    assert nodes["huge"].attrib["data-text-truncated"] == "true"
    assert "data-text-truncated" not in nodes["later"].attrib
    assert later_text == ["Visible label"]


def test_native_document_canvas_text_byte_budget_is_fair_across_labels() -> None:
    later_label = "L" * 108
    source = {
        "nodes": [
            {
                "id": "huge",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 1_000_000,
                "height": 200,
                "text": "x" * 1_100_000,
            },
            {
                "id": "later",
                "type": "text",
                "x": 0,
                "y": 300,
                "width": 1_000,
                "height": 100,
                "text": later_label,
            },
        ],
        "edges": [],
    }
    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Fair byte budget")
        )
    )
    nodes = {
        element.attrib["data-source-id"]: element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") in {"huge", "later"}
    }
    huge_text = "".join(
        element.text or ""
        for element in nodes["huge"]
        if element.tag == f"{SVG_NS}text"
        and element.attrib.get("data-node-label") == "true"
    )
    later_text = "".join(
        element.text or ""
        for element in nodes["later"]
        if element.tag == f"{SVG_NS}text"
        and element.attrib.get("data-node-label") == "true"
    )

    assert nodes["huge"].attrib["data-text-truncated"] == "true"
    assert len(huge_text.encode("utf-8")) <= 512 * 1024
    assert "data-text-truncated" not in nodes["later"].attrib
    assert later_text == later_label


def test_native_document_bounds_grapheme_probe_independently_of_geometry(
    monkeypatch,
) -> None:
    observed_clusters = 0
    original_iter = native_diagram.iter_grapheme_clusters
    original_bounded_prefix = native_diagram.bounded_grapheme_prefix

    def bounded_prefix(value: str, **kwargs):
        if len(value) > 10_000:
            assert (
                kwargs.get("max_clusters")
                <= native_diagram._MAX_CANVAS_TEXT_PROBE_CLUSTERS
            )
            assert kwargs.get("max_codepoints") is not None
            assert (
                0
                < kwargs["max_codepoints"]
                <= native_diagram._MAX_CANVAS_TEXT_PROBE_CODEPOINTS
            )
        return original_bounded_prefix(value, **kwargs)

    def counting_iter(value: str):
        nonlocal observed_clusters
        for cluster in original_iter(value):
            observed_clusters += 1
            if observed_clusters > 4 * native_diagram._MAX_CANVAS_TEXT_PROBE_CLUSTERS:
                raise AssertionError("grapheme probing exceeded independent work budget")
            yield cluster

    monkeypatch.setattr(
        native_diagram,
        "bounded_grapheme_prefix",
        bounded_prefix,
    )
    monkeypatch.setattr(native_diagram, "iter_grapheme_clusters", counting_iter)
    source = {
        "nodes": [
            {
                "id": "bounded-probe",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 1_000_000,
                "height": 100,
                "text": "é" * 800_000,
            }
        ],
        "edges": [],
    }

    root = ET.fromstring(
        render_native_editing_document(
            json_canvas_to_editing_document(source, title="Bounded grapheme probe")
        )
    )
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "bounded-probe"
    )

    assert node.attrib["data-text-truncated"] == "true"
    assert observed_clusters <= 4 * native_diagram._MAX_CANVAS_TEXT_PROBE_CLUSTERS


def test_native_document_marks_atomic_glyph_too_wide_for_minimum_font_as_truncated() -> None:
    source = {
        "nodes": [
            {
                "id": "narrow",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 35,
                "height": 80,
                "text": "A",
            }
        ],
        "edges": [],
    }
    document = json_canvas_to_editing_document(source, title="Atomic glyph clipping")
    assert editing_document_to_json_canvas(document) == source

    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "narrow"
    )
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]

    assert node.attrib["data-text-truncated"] == "true"
    assert all(not (item.text or "") for item in texts)
    assert next(node.iter(f"{SVG_NS}title")).text == "A"


def test_native_document_canvas_text_fit_marks_unavoidably_truncated_content() -> None:
    source = {
        "nodes": [
            {
                "id": "tiny",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 80,
                "height": 40,
                "text": "X" * 500,
            }
        ]
    }
    document = json_canvas_to_editing_document(source, title="Bounded truncation")
    assert editing_document_to_json_canvas(document) == source
    root = ET.fromstring(render_native_editing_document(document))
    node = next(
        element
        for element in root.iter(f"{SVG_NS}g")
        if element.attrib.get("data-source-id") == "tiny"
    )
    assert node.attrib["data-text-truncated"] == "true"
    texts = [
        child
        for child in node
        if child.tag == f"{SVG_NS}text"
        and child.attrib.get("data-node-label") == "true"
    ]
    assert texts
    assert texts[-1].text is not None and texts[-1].text.endswith("…")
    assert {item.attrib["font-size"] for item in texts} == {"12"}


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
