"""Bounded draw.io/XML import into the canonical Schauwerk representation model."""

from __future__ import annotations

import base64
import hashlib
import html
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser
from typing import Any

MAX_DRAWIO_SOURCE_BYTES = 5 * 1024 * 1024
MAX_DRAWIO_XML_ELEMENTS = 4096
MAX_DRAWIO_NODES = 128
MAX_DRAWIO_EDGES = 256
_IMPORT_SCHEMA = "schauwerk-representation-input.v1"


class DrawioImportError(ValueError):
    """Raised when a draw.io document cannot be imported without guessing."""


class _LabelTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"br", "div", "p", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"div", "p", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _reject_unsafe_xml_text(text: str) -> None:
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise DrawioImportError("draw.io import rejects DTD/entity declarations")


def _parse_xml(text: str) -> ET.Element:
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_DRAWIO_SOURCE_BYTES:
        raise DrawioImportError("draw.io source exceeds 5 MiB")
    _reject_unsafe_xml_text(text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DrawioImportError(f"draw.io XML is invalid: {exc}") from exc
    if sum(1 for _ in root.iter()) > MAX_DRAWIO_XML_ELEMENTS:
        raise DrawioImportError("draw.io XML exceeds the bounded element budget")
    return root


def _inflate_diagram_payload(payload: str) -> str:
    compact = "".join(payload.split())
    if not compact:
        raise DrawioImportError("draw.io diagram payload is empty")
    try:
        compressed = base64.b64decode(compact, validate=True)
    except (ValueError, TypeError) as exc:
        raise DrawioImportError("draw.io compressed diagram is not valid base64") from exc
    if len(compressed) > MAX_DRAWIO_SOURCE_BYTES:
        raise DrawioImportError("draw.io compressed diagram exceeds 5 MiB")
    decoder = zlib.decompressobj(-15)
    try:
        inflated = decoder.decompress(compressed, MAX_DRAWIO_SOURCE_BYTES + 1)
        if decoder.unconsumed_tail or len(inflated) > MAX_DRAWIO_SOURCE_BYTES:
            raise DrawioImportError("draw.io inflated diagram exceeds 5 MiB")
        remaining = MAX_DRAWIO_SOURCE_BYTES + 1 - len(inflated)
        inflated += decoder.flush(remaining)
    except zlib.error as exc:
        raise DrawioImportError("draw.io compressed diagram cannot be inflated") from exc
    if len(inflated) > MAX_DRAWIO_SOURCE_BYTES:
        raise DrawioImportError("draw.io inflated diagram exceeds 5 MiB")
    if not decoder.eof or decoder.unused_data:
        raise DrawioImportError("draw.io compressed diagram has an ambiguous DEFLATE boundary")
    try:
        encoded_xml = inflated.decode("ascii")
        xml_bytes = urllib.parse.unquote_to_bytes(encoded_xml)
        xml_text = xml_bytes.decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
        raise DrawioImportError("draw.io compressed diagram has invalid text encoding") from exc
    return xml_text


def _extract_graph_model(source: str) -> tuple[ET.Element, str | None]:
    root = _parse_xml(source)
    root_name = _local_name(root.tag)
    if root_name == "mxGraphModel":
        return root, None
    if root_name != "mxfile":
        raise DrawioImportError("draw.io root must be mxfile or mxGraphModel")

    diagrams = [child for child in root if _local_name(child.tag) == "diagram"]
    if len(diagrams) != 1:
        raise DrawioImportError("native draw.io import requires exactly one diagram page")
    diagram = diagrams[0]
    name = diagram.get("name")
    child_models = [child for child in diagram if _local_name(child.tag) == "mxGraphModel"]
    if len(child_models) == 1:
        return child_models[0], name
    if child_models:
        raise DrawioImportError("draw.io diagram contains multiple graph models")

    payload = (diagram.text or "").strip()
    if not payload:
        raise DrawioImportError("draw.io diagram has no graph model")
    if payload.startswith("<"):
        return _parse_xml(payload), name
    return _parse_xml(_inflate_diagram_payload(payload)), name


def _plain_text(raw: object) -> str:
    if raw is None:
        return ""
    value = html.unescape(str(raw))
    parser = _LabelTextParser()
    try:
        parser.feed(value)
        parser.close()
    except Exception as exc:
        raise DrawioImportError("draw.io label cannot be normalized") from exc
    joined = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in joined.splitlines()]
    return "\n".join(line for line in lines if line)


def _node_text(raw: object) -> tuple[str, str] | None:
    text = _plain_text(raw)
    if not text:
        return None
    lines = text.splitlines()
    if len(lines[0]) <= 120:
        label = lines[0]
        summary = " ".join(lines[1:])
    else:
        flattened = " ".join(lines)
        split_at = flattened.rfind(" ", 0, 121)
        if split_at < 40:
            split_at = 120
        label = flattened[:split_at].strip()
        summary = flattened[split_at:].strip()
    if len(label) > 120 or len(summary) > 500:
        raise DrawioImportError("draw.io node text exceeds native representation limits")
    return label, summary


def _edge_label(raw: object) -> str:
    label = " ".join(_plain_text(raw).split())
    if not label:
        raise DrawioImportError(
            "draw.io graph contains an edge without semantic text"
        )
    if len(label) > 120:
        raise DrawioImportError("draw.io edge label exceeds native representation limits")
    return label


def _stable_id(prefix: str, source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _style_map(style: object) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in str(style or "").split(";"):
        token = item.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            values[key.casefold()] = value.casefold()
        else:
            values[token.casefold()] = "1"
    return values


def _node_kind(style: object) -> str:
    values = _style_map(style)
    shape = values.get("shape", "")
    if values.get("rhombus") == "1" or "decision" in shape:
        return "decision"
    if values.get("cylinder") == "1" or "cylinder" in shape or "database" in shape:
        return "store"
    if "actor" in shape or "person" in shape:
        return "human"
    if "process" in shape:
        return "action"
    return "concept"


def _edge_kind(style: object) -> str:
    values = _style_map(style)
    if values.get("endarrow") in {"none", ""} and values.get("startarrow") in {"none", ""}:
        return "association"
    return "flow"


def _cell_label(cell: ET.Element, parent_by_id: dict[int, ET.Element]) -> object:
    if cell.get("value") not in {None, ""}:
        return cell.get("value")
    parent = parent_by_id.get(id(cell))
    if parent is not None and _local_name(parent.tag) in {"object", "UserObject"}:
        for key in ("label", "value", "name"):
            if parent.get(key) not in {None, ""}:
                return parent.get(key)
    return ""


def _cell_identity(cell: ET.Element, parent_by_id: dict[int, ET.Element]) -> str | None:
    cell_id = cell.get("id")
    if cell_id:
        return cell_id
    parent = parent_by_id.get(id(cell))
    if parent is not None and _local_name(parent.tag) in {"object", "UserObject"}:
        wrapper_id = parent.get("id")
        if wrapper_id:
            return wrapper_id
    return None


def drawio_xml_to_representation(source: str, *, title: str | None = None) -> dict[str, Any]:
    """Convert one bounded draw.io graph page into the native semantic model.

    Graph structure and text are preserved as the semantic source. draw.io-specific
    styling and exact geometry are intentionally not treated as authoritative.
    """

    if not isinstance(source, str):
        raise DrawioImportError("draw.io source must be text")
    model, page_name = _extract_graph_model(source)
    if _local_name(model.tag) != "mxGraphModel":
        raise DrawioImportError("draw.io payload does not contain mxGraphModel")

    parent_by_id = {id(child): parent for parent in model.iter() for child in parent}
    cells = [element for element in model.iter() if _local_name(element.tag) == "mxCell"]
    if not cells:
        raise DrawioImportError("draw.io graph contains no mxCell elements")

    vertex_cells: dict[str, ET.Element] = {}
    edge_cells: list[ET.Element] = []
    seen_cell_ids: set[str] = set()
    for cell in cells:
        semantic_cell = cell.get("vertex") == "1" or cell.get("edge") == "1"
        cell_id = _cell_identity(cell, parent_by_id)
        if not cell_id:
            if semantic_cell:
                raise DrawioImportError(
                    "draw.io semantic mxCell requires an id on the cell or its object wrapper"
                )
            continue
        if cell_id in seen_cell_ids:
            raise DrawioImportError(f"draw.io graph contains duplicate mxCell id: {cell_id}")
        seen_cell_ids.add(cell_id)
        if cell.get("vertex") == "1":
            vertex_cells[cell_id] = cell
        elif cell.get("edge") == "1":
            edge_cells.append(cell)

    if len(vertex_cells) > MAX_DRAWIO_NODES or len(edge_cells) > MAX_DRAWIO_EDGES:
        raise DrawioImportError("draw.io graph exceeds native import complexity limits")

    for source_id, cell in vertex_cells.items():
        parent_id = cell.get("parent")
        style = _style_map(cell.get("style"))
        shape = style.get("shape", "")
        uses_container_semantics = (
            parent_id in vertex_cells
            or style.get("container") == "1"
            or "swimlane" in style
            or "swimlane" in shape
        )
        if uses_container_semantics:
            raise DrawioImportError(
                f"draw.io vertex {source_id} uses nested/container semantics "
                "outside the native import subset"
            )

    connected_ids: set[str] = set()
    for edge in edge_cells:
        source_id = edge.get("source")
        target_id = edge.get("target")
        if source_id:
            connected_ids.add(source_id)
        if target_id:
            connected_ids.add(target_id)

    nodes: list[dict[str, Any]] = []
    node_id_map: dict[str, str] = {}
    for source_id, cell in vertex_cells.items():
        normalized_text = _node_text(_cell_label(cell, parent_by_id))
        if normalized_text is None:
            if source_id in connected_ids:
                raise DrawioImportError(
                    "draw.io graph contains a connected vertex without semantic text"
                )
            continue
        label, summary = normalized_text
        node_id = _stable_id("node", source_id)
        node_id_map[source_id] = node_id
        nodes.append(
            {
                "id": node_id,
                "label": label,
                "kind": _node_kind(cell.get("style")),
                "group": None,
                "summary": summary,
            }
        )

    if not nodes:
        raise DrawioImportError("draw.io graph has no importable semantic nodes")

    edges: list[dict[str, str]] = []
    for cell in edge_cells:
        source_id = cell.get("source")
        target_id = cell.get("target")
        if source_id is None and target_id is None:
            continue
        if source_id not in node_id_map or target_id not in node_id_map:
            raise DrawioImportError(
                "draw.io edge references an unsupported or non-semantic vertex"
            )
        original_id = _cell_identity(cell, parent_by_id)
        if original_id is None:
            raise DrawioImportError("draw.io semantic edge identity unexpectedly missing")
        edges.append(
            {
                "id": _stable_id("edge", original_id),
                "from": node_id_map[source_id],
                "to": node_id_map[target_id],
                "label": _edge_label(_cell_label(cell, parent_by_id)),
                "kind": _edge_kind(cell.get("style")),
            }
        )

    raw_title = title if isinstance(title, str) and title.strip() else page_name
    normalized_title = " ".join((raw_title or "Importiertes Schaubild").split())
    if not normalized_title or len(normalized_title) > 160:
        raise DrawioImportError("draw.io title exceeds native representation limits")

    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return {
        "schema_version": _IMPORT_SCHEMA,
        "id": f"drawio_{source_digest[:16]}",
        "title": normalized_title,
        "purpose": (
            "Aus draw.io/XML nativ importiert. Graphstruktur und Text bleiben semantische "
            "Quelle; draw.io-spezifische Gestaltung und exakte Geometrie sind nicht autoritativ."
        ),
        "intent": "process" if edges else "presentation",
        "groups": [],
        "nodes": nodes,
        "edges": edges,
        "requirements": {
            "formal_relations": bool(edges),
            "free_spatial_layout": False,
            "presentation": True,
            "collaboration": False,
            "rich_text": False,
            "structured_comparison": False,
            "portable_offline": True,
        },
        "requested_formats": [],
    }
