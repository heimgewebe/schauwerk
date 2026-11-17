"""Regression tests for long labels seen on a tablet knowledge-map preview."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from schauwerk.visual.native_diagram import render_native_diagram

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "docs/operators/fixtures/golden/system-landscape-v1.json"
)
SVG = "{http://www.w3.org/2000/svg}"


def _visible_lines(item: ET.Element) -> list[str]:
    return [
        "".join(span.itertext())
        for text in item.findall(SVG + "text")
        for span in text.findall(SVG + "tspan")
    ]


def test_knowledge_map_long_titles_descriptions_and_group_headers_remain_complete():
    model = json.loads(FIXTURE.read_text(encoding="utf-8"))
    group_label = "Philosophische & psychologische Ansätze"
    titles_and_copy = {
        "world": (
            "Logotherapie (Viktor Frankl)",
            "Die Suche nach Sinn als primäre Antriebskraft des Menschen.",
        ),
        "catalog": (
            "Existenzialismus",
            "Ansatz (u. a. Sartre, Camus), dass Sinn durch "
            "eigenverantwortliches Handeln selbst geschaffen wird.",
        ),
        "bureau": (
            "Sinn",
            "Das zentrale Gefühl von Bedeutung, Zweck und innerer Ausrichtung.",
        ),
    }
    model["groups"][0]["label"] = group_label
    for node in model["nodes"]:
        if node["id"] in titles_and_copy:
            node["label"], node["summary"] = titles_and_copy[node["id"]]
    model["edges"][7]["label"] = "motiviert"

    svg = render_native_diagram(model)
    root = ET.fromstring(svg)
    groups = {
        elem.attrib["data-source-id"]: elem
        for elem in root.iter()
        if elem.attrib.get("data-source-kind") == "group"
    }
    assert " ".join(_visible_lines(groups["truth"])) == group_label

    nodes = {
        elem.attrib["data-source-id"]: elem
        for elem in root.iter()
        if elem.attrib.get("data-source-kind") == "node"
    }
    for node_id, (title, summary) in titles_and_copy.items():
        rendered = nodes[node_id].findall(SVG + "text")
        assert len(rendered) >= 3
        assert " ".join(
            "".join(span.itertext()) for span in rendered[1].findall(SVG + "tspan")
        ) == title
        assert " ".join(
            "".join(span.itertext()) for span in rendered[2].findall(SVG + "tspan")
        ) == summary
        assert "…" not in " ".join(_visible_lines(nodes[node_id]))

    edges = {
        elem.attrib["data-source-id"]: elem
        for elem in root.iter()
        if elem.attrib.get("data-source-kind") == "edge"
    }
    assert _visible_lines(edges["land08"]) == ["motiviert"]

    # SVG structure, geometry and source data still have a stable readback.
    assert svg == render_native_diagram(model)
    assert root.attrib["data-intent"] == "knowledge_map"


def test_knowledge_map_card_and_group_clip_keep_glyph_ascenders():
    # Chromium measured title ascenders 2-3 SVG units outside the old top.
    # Check the clip rectangle expands upward only, never into other cards.
    model = json.loads(FIXTURE.read_text(encoding="utf-8"))
    root = ET.fromstring(render_native_diagram(model))

    def clip_and_card(kind: str, item_id: str):
        group = next(
            item for item in root.iter()
            if item.attrib.get("data-source-kind") == kind
            and item.attrib.get("data-source-id") == item_id
        )
        clip = group.find("./" + SVG + "defs/" + SVG + "clipPath/" + SVG + "rect")
        card = group.find(SVG + "rect")
        assert clip is not None and card is not None
        return clip, card

    for node in model["nodes"]:
        clip, card = clip_and_card("node", node["id"])
        assert float(clip.attrib["y"]) - float(card.attrib["y"]) == 28
        assert (
            float(clip.attrib["y"]) + float(clip.attrib["height"])
            == float(card.attrib["y"]) + float(card.attrib["height"]) - 2
        )
    for group in model["groups"]:
        clip, card = clip_and_card("group", group["id"])
        assert float(clip.attrib["y"]) - float(card.attrib["y"]) == 6
        assert float(clip.attrib["y"]) + float(clip.attrib["height"]) == float(
            card.attrib["y"]
        ) + 50
