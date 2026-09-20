from __future__ import annotations

import base64
import urllib.parse
import zlib

import pytest

from schauwerk.visual.drawio_import import (
    DrawioImportError,
    drawio_xml_to_representation,
)
from schauwerk.visual.representation import validate_representation_input

MODEL = """<mxGraphModel><root>
<mxCell id="0"/>
<mxCell id="1" parent="0"/>
<mxCell
  id="ali"
  value="Fallbeispiel: Ali&lt;br&gt;Kernfrage: Verhalten verstehen"
  style="rounded=1;whiteSpace=wrap;html=1;"
  vertex="1"
  parent="1"
>
  <mxGeometry x="40" y="40" width="320" height="120" as="geometry"/>
</mxCell>
<mxCell
  id="resources"
  value="5. Ressourcen&lt;br&gt;- logisches Denken&lt;br&gt;- interessierte Eltern"
  style="rounded=1;whiteSpace=wrap;html=1;"
  vertex="1"
  parent="1"
>
  <mxGeometry x="520" y="40" width="320" height="160" as="geometry"/>
</mxCell>
<mxCell
  id="relation"
  value="verfügt über"
  style="edgeStyle=orthogonalEdgeStyle;endArrow=classic;"
  edge="1"
  parent="1"
  source="ali"
  target="resources"
>
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
</root></mxGraphModel>"""


def _compressed_mxfile(model: str) -> str:
    encoded = urllib.parse.quote(model, safe="~()*!.'").encode("ascii")
    compressor = zlib.compressobj(level=9, wbits=-15)
    payload = compressor.compress(encoded) + compressor.flush()
    return (
        '<mxfile host="app.diagrams.net">'
        '<diagram id="page-1" name="Fallbeispiel Ali">'
        + base64.b64encode(payload).decode("ascii")
        + "</diagram></mxfile>"
    )


def test_imports_graph_model_as_valid_native_representation() -> None:
    imported = drawio_xml_to_representation(
        MODEL,
        title="Fallbeispiel_Ali_Uebersicht.drawio",
    )
    normalized = validate_representation_input(imported)

    assert normalized["schema_version"] == "schauwerk-representation-input.v1"
    assert normalized["title"] == "Fallbeispiel_Ali_Uebersicht.drawio"
    assert normalized["intent"] == "process"
    assert [node["label"] for node in normalized["nodes"]] == [
        "Fallbeispiel: Ali",
        "5. Ressourcen",
    ]
    assert normalized["nodes"][0]["summary"] == "Kernfrage: Verhalten verstehen"
    assert "logisches Denken" in normalized["nodes"][1]["summary"]
    assert len(normalized["edges"]) == 1
    assert normalized["edges"][0]["label"] == "verfügt über"
    assert normalized["edges"][0]["kind"] == "flow"


def test_imports_uncompressed_single_page_mxfile() -> None:
    source = f'<mxfile><diagram name="Ali">{MODEL}</diagram></mxfile>'
    imported = drawio_xml_to_representation(source)

    assert imported["title"] == "Ali"
    assert len(imported["nodes"]) == 2
    assert len(imported["edges"]) == 1


def test_imports_standard_compressed_single_page_mxfile() -> None:
    imported = drawio_xml_to_representation(_compressed_mxfile(MODEL))

    assert imported["title"] == "Fallbeispiel Ali"
    assert {node["label"] for node in imported["nodes"]} == {
        "Fallbeispiel: Ali",
        "5. Ressourcen",
    }
    validate_representation_input(imported)


def test_rejects_compressed_diagram_with_trailing_payload_after_deflate_stream() -> None:
    encoded = urllib.parse.quote(MODEL, safe="~()*!.'").encode("ascii")
    compressor = zlib.compressobj(level=9, wbits=-15)
    payload = compressor.compress(encoded) + compressor.flush() + b"trailing"
    source = (
        '<mxfile><diagram name="Ali">'
        + base64.b64encode(payload).decode("ascii")
        + "</diagram></mxfile>"
    )

    with pytest.raises(DrawioImportError, match="ambiguous DEFLATE boundary"):
        drawio_xml_to_representation(source)


def test_imports_object_wrapped_cell_label_shape_and_wrapper_identity() -> None:
    source = """<mxGraphModel><root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <object id="d" label="Entscheidung">
      <mxCell style="rhombus;html=1;" vertex="1" parent="1">
        <mxGeometry/>
      </mxCell>
    </object>
    </root></mxGraphModel>"""

    imported = drawio_xml_to_representation(source)
    assert imported["nodes"][0]["label"] == "Entscheidung"
    assert imported["nodes"][0]["kind"] == "decision"


def test_object_wrapper_ids_are_used_for_edge_endpoints() -> None:
    source = """<mxGraphModel><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <object id="a" label="Ali">
      <mxCell vertex="1" parent="1"><mxGeometry/></mxCell>
    </object>
    <object id="b" label="Ressourcen">
      <mxCell vertex="1" parent="1"><mxGeometry/></mxCell>
    </object>
    <mxCell id="e" value="nutzt" edge="1" parent="1" source="a" target="b">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
    </root></mxGraphModel>"""

    imported = drawio_xml_to_representation(source)
    assert [node["label"] for node in imported["nodes"]] == ["Ali", "Ressourcen"]
    assert imported["edges"][0]["label"] == "nutzt"


def test_decorative_unconnected_unlabelled_vertex_is_ignored() -> None:
    decoration = (
        '<mxCell id="decoration" value="" vertex="1" parent="1">'
        "<mxGeometry/></mxCell>"
    )
    source = MODEL.replace('<mxCell\n  id="relation"', decoration + '<mxCell\n  id="relation"')
    imported = drawio_xml_to_representation(source)
    assert len(imported["nodes"]) == 2


@pytest.mark.parametrize(
    "source",
    [
        """<mxGraphModel><root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell value="Ali" vertex="1" parent="1"><mxGeometry/></mxCell>
        </root></mxGraphModel>""",
        """<mxGraphModel><root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="a" value="Ali" vertex="1" parent="1"><mxGeometry/></mxCell>
        <mxCell id="b" value="Ressourcen" vertex="1" parent="1"><mxGeometry/></mxCell>
        <mxCell value="nutzt" edge="1" parent="1" source="a" target="b">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        </root></mxGraphModel>""",
    ],
)
def test_rejects_semantic_cell_without_cell_or_wrapper_id(source: str) -> None:
    with pytest.raises(DrawioImportError, match="semantic mxCell requires an id"):
        drawio_xml_to_representation(source)


def test_rejects_unlabelled_edge_without_inventing_semantics() -> None:
    source = MODEL.replace('value="verfügt über"', 'value=""')

    with pytest.raises(DrawioImportError, match="edge without semantic text"):
        drawio_xml_to_representation(source)


def test_rejects_duplicate_mxcell_ids() -> None:
    duplicate = (
        '<mxCell id="resources" value="Doppelte Ressource" vertex="1" parent="1">'
        "<mxGeometry/></mxCell>"
    )
    source = MODEL.replace("</root>", duplicate + "</root>")

    with pytest.raises(DrawioImportError, match="duplicate mxCell id: resources"):
        drawio_xml_to_representation(source)


@pytest.mark.parametrize(
    "container_source",
    [
        """<mxGraphModel><root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="group" value="Gruppe" vertex="1" parent="1"><mxGeometry/></mxCell>
        <mxCell id="child" value="Kind" vertex="1" parent="group"><mxGeometry/></mxCell>
        </root></mxGraphModel>""",
        """<mxGraphModel><root>
        <mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="lane" value="Swimlane" style="swimlane;" vertex="1" parent="1">
          <mxGeometry/>
        </mxCell>
        </root></mxGraphModel>""",
    ],
)
def test_rejects_nested_or_container_vertex_semantics(container_source: str) -> None:
    with pytest.raises(DrawioImportError, match="nested/container semantics"):
        drawio_xml_to_representation(container_source)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            (
                f'<mxfile><diagram name="one">{MODEL}</diagram>'
                f'<diagram name="two">{MODEL}</diagram></mxfile>'
            ),
            "exactly one diagram page",
        ),
        (
            (
                '<!DOCTYPE x [<!ENTITY boom "x">]>'
                '<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>'
            ),
            "DTD/entity",
        ),
        (
            MODEL.replace(
                'value="5. Ressourcen&lt;br&gt;- logisches Denken'
                '&lt;br&gt;- interessierte Eltern"',
                'value=""',
            ),
            "connected vertex without semantic text",
        ),
        (
            MODEL.replace('target="resources"', 'target="missing"'),
            "unsupported or non-semantic vertex",
        ),
    ],
)
def test_unsupported_or_unsafe_drawio_fails_closed(
    source: str,
    message: str,
) -> None:
    with pytest.raises(DrawioImportError, match=message):
        drawio_xml_to_representation(source)


def test_import_is_deterministic_for_same_source() -> None:
    first = drawio_xml_to_representation(MODEL, title="Ali")
    second = drawio_xml_to_representation(MODEL, title="Ali")

    assert first == second
    assert first["id"].startswith("drawio_")
