"""Deterministic single-file offline HTML for validated native JSON Canvas documents.

The Canvas document stays the only authority. The HTML file is a derived,
read-only view: a passive, allowlist-sanitised copy of the rendered native SVG
plus a fixed viewer script. It is never an import source. Active SVG content,
foreign URLs and unknown attributes are rejected visibly instead of silently
dropped; only editor-only state (selection classes, tab stops, ARIA state) is
removed on purpose.
"""

# ruff: noqa: E501

from __future__ import annotations

import base64
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from schauwerk.resources.native_offline_html.assets import VIEWER_CSS, VIEWER_JS
from schauwerk.visual.native_document import (
    MAX_NATIVE_EDGES,
    MAX_NATIVE_GROUPS,
    MAX_NATIVE_NODES,
    MAX_NATIVE_ROUTING_PAIRS,
    NativeDocumentError,
    json_canvas_to_editing_document,
)
from schauwerk.visual.native_viewer import _bounded_html_title

__all__ = [
    "MAX_OFFLINE_HTML_BYTES",
    "MAX_OFFLINE_SVG_BYTES",
    "OFFLINE_HTML_SCHEMA",
    "OfflineHtmlError",
    "OfflineHtmlResult",
    "build_offline_html",
    "content_security_policy",
    "SanitizedSvg",
    "sanitize_native_svg",
]

OFFLINE_HTML_SCHEMA: Final = "schauwerk-native-offline-html.v1"
MAX_OFFLINE_SVG_BYTES: Final = 8 * 1024 * 1024
MAX_OFFLINE_HTML_BYTES: Final = 12 * 1024 * 1024
MAX_SVG_ELEMENTS: Final = 120_000
MAX_SVG_DEPTH: Final = 12
MAX_TEXT_CHARS: Final = 1_000_000
MAX_ID_CHARS: Final = 65_536
MAX_ATTRIBUTE_CHARS: Final = 2_048
MAX_PATH_CHARS: Final = 262_144
_SVG_NS: Final = "http://www.w3.org/2000/svg"
_RESERVED_ID_PREFIX: Final = "ofh-"

_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_NUMBER_RE = re.compile(rf"{_NUM}")
_LENGTH_RE = re.compile(rf"{_NUM}(?:px|em|%)?")
_NUMBER_LIST_RE = re.compile(rf"(?:none|{_NUM}(?:[\s,]+{_NUM})*)")
_VIEWBOX_RE = re.compile(rf"{_NUM}(?:[\s,]+{_NUM}){{3}}")
_PATH_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]*")
_TRANSFORM_RE = re.compile(
    rf"(?:\s*(?:translate|scale)\(\s*{_NUM}(?:[\s,]+{_NUM})?\s*\)"
    rf"|\s*matrix\(\s*{_NUM}(?:[\s,]+{_NUM}){{5}}\s*\))+\s*"
)
_COLOR_RE = re.compile(
    r"(?:none|currentColor|transparent|#[0-9a-fA-F]{3,8}|[A-Za-z]{3,24}"
    r"|rgba?\(\s*[\d.,%\s/]+\))"
)
_URL_REF_RE = re.compile(r"url\(#([A-Za-z0-9_-]{1,64})\)")
_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_FONT_FAMILY_RE = re.compile(r"[A-Za-z0-9 ,'\"_-]{1,200}")
_FONT_WEIGHT_RE = re.compile(r"(?:normal|bold|bolder|lighter|[1-9]00)")
_DATA_NAME_RE = re.compile(r"data-[a-z0-9]+(?:-[a-z0-9]+){0,5}")
_XML_DECLARATION_RE = re.compile(
    r'\A\s*<\?xml\s+version="1\.0"(?:\s+encoding="UTF-8")?\s*\?>\s*'
)

# Editor-only runtime state that the live SVG may carry. It is removed on
# purpose; every other unknown attribute is a visible rejection.
_EDITOR_ONLY_ATTRIBUTES: Final = frozenset(
    {
        "class",
        "tabindex",
        "role",
        "pointer-events",
        "focusable",
        "data-input-digest",
        "data-routing-pending",
        "data-routing-conflict",
        "data-label-conflict",
        "data-canonical-stroke",
        "data-canonical-dash",
        "data-connection-handles",
        "data-connection-handle",
    }
)

_CONTAINER_ELEMENTS: Final = frozenset({"svg", "g", "defs", "marker", "clipPath"})
_TEXT_ELEMENTS: Final = frozenset({"text", "tspan", "title", "desc"})
_SHAPE_ELEMENTS: Final = frozenset({"path", "rect", "circle", "ellipse"})
_ALLOWED_ELEMENTS: Final = _CONTAINER_ELEMENTS | _TEXT_ELEMENTS | _SHAPE_ELEMENTS

_Validator = Callable[[str], bool]


def _matches(pattern: re.Pattern[str], limit: int = MAX_ATTRIBUTE_CHARS) -> _Validator:
    return lambda value: len(value) <= limit and pattern.fullmatch(value) is not None


def _enum(*allowed: str) -> _Validator:
    return lambda value: value in allowed


def _url_ref(value: str) -> bool:
    return _URL_REF_RE.fullmatch(value) is not None


def _paint(value: str) -> bool:
    return _COLOR_RE.fullmatch(value) is not None or _url_ref(value)


def _orient(value: str) -> bool:
    return value in {"auto", "auto-start-reverse"} or _NUMBER_RE.fullmatch(value) is not None


_PRESENTATION: Final[dict[str, _Validator]] = {
    "fill": _paint,
    "stroke": _paint,
    "fill-opacity": _matches(_NUMBER_RE),
    "stroke-opacity": _matches(_NUMBER_RE),
    "opacity": _matches(_NUMBER_RE),
    "stroke-width": _matches(_LENGTH_RE),
    "stroke-dasharray": _matches(_NUMBER_LIST_RE),
    "stroke-linecap": _enum("butt", "round", "square"),
    "stroke-linejoin": _enum("miter", "round", "bevel"),
    "clip-path": _url_ref,
    "marker-start": _url_ref,
    "marker-end": _url_ref,
    "transform": _matches(_TRANSFORM_RE),
}
_TEXT_ATTRIBUTES: Final[dict[str, _Validator]] = {
    "x": _matches(_LENGTH_RE),
    "y": _matches(_LENGTH_RE),
    "dx": _matches(_LENGTH_RE),
    "dy": _matches(_LENGTH_RE),
    "text-anchor": _enum("start", "middle", "end"),
    "font-family": _matches(_FONT_FAMILY_RE),
    "font-size": _matches(_LENGTH_RE),
    "font-weight": _matches(_FONT_WEIGHT_RE),
    "font-style": _enum("normal", "italic"),
    "textLength": _matches(_LENGTH_RE),
    "lengthAdjust": _enum("spacing", "spacingAndGlyphs"),
    "dominant-baseline": _enum("auto", "middle", "central", "hanging", "alphabetic"),
}
_ELEMENT_ATTRIBUTES: Final[dict[str, dict[str, _Validator]]] = {
    "svg": {"viewBox": _matches(_VIEWBOX_RE)},
    "g": {**_PRESENTATION},
    "defs": {},
    "clipPath": {},
    "title": {},
    "desc": {},
    "marker": {
        **_PRESENTATION,
        "viewBox": _matches(_VIEWBOX_RE),
        "refX": _matches(_LENGTH_RE),
        "refY": _matches(_LENGTH_RE),
        "markerWidth": _matches(_LENGTH_RE),
        "markerHeight": _matches(_LENGTH_RE),
        "orient": _orient,
        "markerUnits": _enum("strokeWidth", "userSpaceOnUse"),
    },
    "path": {**_PRESENTATION, "d": _matches(_PATH_RE, MAX_PATH_CHARS)},
    "rect": {
        **_PRESENTATION,
        **{name: _matches(_LENGTH_RE) for name in ("x", "y", "width", "height", "rx", "ry")},
    },
    "circle": {
        **_PRESENTATION,
        **{name: _matches(_LENGTH_RE) for name in ("cx", "cy", "r")},
    },
    "ellipse": {
        **_PRESENTATION,
        **{name: _matches(_LENGTH_RE) for name in ("cx", "cy", "rx", "ry")},
    },
    "text": {**_PRESENTATION, **_TEXT_ATTRIBUTES},
    "tspan": {**_PRESENTATION, **_TEXT_ATTRIBUTES},
}
# Presentation-only attributes that the renderer places on the SVG root are
# replaced by the viewer; width and height must not pin a fixed pixel size.
_ROOT_DROPPED: Final = frozenset({"width", "height", "version", "id", "preserveAspectRatio"})


class OfflineHtmlError(ValueError):
    """Raised when a document cannot be exported as an offline HTML file."""


@dataclass(frozen=True)
class OfflineHtmlResult:
    """The generated bytes plus the digests that bind them to their source."""

    html: bytes
    sha256: str
    source_sha256: str
    svg_sha256: str
    node_count: int
    edge_count: int


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _csp_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def content_security_policy() -> str:
    """Return the hash-bound CSP: no network, no eval, no foreign origin, no forms."""

    return (
        "default-src 'none'; "
        f"script-src {_csp_hash(VIEWER_JS)}; "
        f"style-src {_csp_hash(VIEWER_CSS)}; "
        "img-src 'none'; font-src 'none'; connect-src 'none'; frame-src 'none'; "
        "object-src 'none'; media-src 'none'; worker-src 'none'; manifest-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        raise OfflineHtmlError("SVG contains a non-element node")
    if tag.startswith("{"):
        namespace, _, name = tag[1:].partition("}")
        if namespace != _SVG_NS:
            raise OfflineHtmlError(f"SVG element is outside the SVG namespace: {name}")
        return name
    raise OfflineHtmlError(f"SVG element has no namespace: {tag}")


def _attribute_value_is_clean(value: str) -> bool:
    return not any(ord(character) < 32 and character not in "\t\n\r" for character in value)


def _sanitize_attributes(name: str, element: ET.Element, *, is_root: bool) -> list[tuple[str, str]]:
    allowed = _ELEMENT_ATTRIBUTES[name]
    kept: list[tuple[str, str]] = []
    for raw_name, value in element.attrib.items():
        if raw_name.startswith("{"):
            raise OfflineHtmlError(f"SVG attribute is namespaced and not allowed: {raw_name}")
        if raw_name.casefold().startswith("on"):
            raise OfflineHtmlError(f"SVG event attribute is not allowed: {raw_name}")
        if raw_name in _EDITOR_ONLY_ATTRIBUTES or raw_name.startswith("aria-"):
            continue
        if is_root and raw_name in _ROOT_DROPPED:
            continue
        if raw_name == "id":
            continue  # handled below with the element context
        if _DATA_NAME_RE.fullmatch(raw_name) is not None:
            limit = MAX_ID_CHARS if raw_name == "data-source-id" else MAX_ATTRIBUTE_CHARS
            if len(value) > limit or not _attribute_value_is_clean(value):
                raise OfflineHtmlError(f"SVG attribute value is not allowed: {raw_name}")
            kept.append((raw_name, value))
            continue
        validator = allowed.get(raw_name)
        if validator is None:
            raise OfflineHtmlError(f"SVG attribute is not allowed on <{name}>: {raw_name}")
        if not _attribute_value_is_clean(value) or not validator(value):
            raise OfflineHtmlError(f"SVG attribute value is not allowed: {raw_name}")
        kept.append((raw_name, value))
    return kept


def _checked_id(element: ET.Element, attributes: list[tuple[str, str]]) -> str | None:
    value = element.attrib.get("id")
    if value is None:
        return None
    data = dict(attributes)
    kind = data.get("data-source-kind")
    source_id = data.get("data-source-id")
    if kind is not None:
        if kind not in {"node", "edge"} or source_id is None:
            raise OfflineHtmlError("SVG source element has an invalid source kind or id")
        if value != f"native-{kind}-{source_id}":
            raise OfflineHtmlError("SVG source element id does not match its source id")
    elif _ID_RE.fullmatch(value) is None:
        raise OfflineHtmlError("SVG element id is not allowed")
    if value.casefold().startswith(_RESERVED_ID_PREFIX):
        raise OfflineHtmlError("SVG element id uses the reserved viewer prefix")
    if not _attribute_value_is_clean(value):
        raise OfflineHtmlError("SVG element id is not allowed")
    return value


@dataclass
class SanitizedSvg:
    markup: str
    view_box: tuple[float, float, float, float]
    nodes: dict[str, str]
    edges: set[str]
    edge_markers: dict[str, set[str]]
    element_count: int


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attribute(value: str) -> str:
    return _escape_text(value).replace('"', "&quot;")


def sanitize_native_svg(svg: str) -> SanitizedSvg:
    """Parse, allowlist-validate and re-serialise one rendered native SVG."""

    if not isinstance(svg, str):
        raise OfflineHtmlError("SVG must be text")
    payload = svg.encode("utf-8", errors="strict")
    if len(payload) > MAX_OFFLINE_SVG_BYTES:
        raise OfflineHtmlError("SVG exceeds the offline export size limit")
    declaration = _XML_DECLARATION_RE.match(svg)
    body = svg[declaration.end():] if declaration else svg
    folded = body.casefold()
    if "<!doctype" in folded or "<!entity" in folded or "<?" in body:
        raise OfflineHtmlError("SVG must not contain a DTD, entities or processing instructions")
    try:
        root = ET.fromstring(body.encode("utf-8"))
    except ET.ParseError as exc:
        raise OfflineHtmlError(f"SVG is not well-formed XML: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise OfflineHtmlError("SVG root element is not <svg>")

    seen_ids: set[str] = set()
    nodes: dict[str, str] = {}
    edges: set[str] = set()
    edge_markers: dict[str, set[str]] = {}
    references: list[str] = []
    element_count = 0
    view_box: tuple[float, float, float, float] | None = None
    text_total = 0

    def emit(element: ET.Element, depth: int, owner_edge: str | None) -> str:
        nonlocal element_count, view_box, text_total
        if depth > MAX_SVG_DEPTH:
            raise OfflineHtmlError("SVG nesting is too deep")
        element_count += 1
        if element_count > MAX_SVG_ELEMENTS:
            raise OfflineHtmlError("SVG contains too many elements")
        name = _local_name(element.tag)
        if name not in _ALLOWED_ELEMENTS:
            raise OfflineHtmlError(f"SVG element is not allowed: {name}")
        if name == "svg" and depth != 0:
            raise OfflineHtmlError("nested <svg> elements are not allowed")
        attributes = _sanitize_attributes(name, element, is_root=depth == 0)
        # The root id is replaced by the viewer's own id below.
        identifier = None if depth == 0 else _checked_id(element, attributes)
        if identifier is not None:
            if identifier in seen_ids:
                raise OfflineHtmlError("SVG element ids are not unique")
            seen_ids.add(identifier)
            attributes.insert(0, ("id", identifier))
        data = dict(attributes)
        kind = data.get("data-source-kind")
        if kind is not None:
            if name != "g":
                raise OfflineHtmlError("SVG source markers are only allowed on <g>")
            source_id = data["data-source-id"]
            if kind == "node":
                if source_id in nodes:
                    raise OfflineHtmlError("SVG contains a duplicate node id")
                nodes[source_id] = data.get("data-canvas-type", "")
            else:
                if source_id in edges:
                    raise OfflineHtmlError("SVG contains a duplicate edge id")
                edges.add(source_id)
                edge_markers[source_id] = set()
                owner_edge = source_id
        if owner_edge is not None:
            for marker_name in ("marker-start", "marker-end"):
                if marker_name in data:
                    edge_markers[owner_edge].add(marker_name)
        for attribute_name in ("clip-path", "marker-start", "marker-end", "fill", "stroke"):
            reference = data.get(attribute_name)
            if reference is not None and reference.startswith("url("):
                references.append(reference[5:-1])
        if depth == 0:
            box = tuple(float(part) for part in re.split(r"[\s,]+", data.get("viewBox", "")) if part)
            if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                raise OfflineHtmlError("SVG root needs a positive viewBox")
            view_box = (box[0], box[1], box[2], box[3])
            attributes.append(("preserveAspectRatio", "xMidYMid meet"))
            attributes.append(("id", "ofh-diagram"))
            attributes.append(("focusable", "false"))

        text = element.text or ""
        if name in _TEXT_ELEMENTS:
            text_total += len(text)
            if text_total > MAX_TEXT_CHARS:
                raise OfflineHtmlError("SVG text exceeds the offline export limit")
        elif text.strip():
            raise OfflineHtmlError(f"SVG <{name}> contains unexpected text")
        else:
            text = ""
        parts: list[str] = []
        if text:
            parts.append(_escape_text(text))
        for child in element:
            parts.append(emit(child, depth + 1, owner_edge))
            tail = child.tail or ""
            if tail.strip():
                raise OfflineHtmlError("SVG contains unexpected text between elements")
            if name in _TEXT_ELEMENTS and tail:
                parts.append(_escape_text(tail))
        rendered_attributes = "".join(
            f' {key}="{_escape_attribute(value)}"' for key, value in attributes
        )
        if depth == 0:
            rendered_attributes = f' xmlns="{_SVG_NS}"' + rendered_attributes
        inner = "".join(parts)
        return f"<{name}{rendered_attributes}>{inner}</{name}>"

    markup = emit(root, 0, None)
    for reference in references:
        if reference not in seen_ids:
            raise OfflineHtmlError("SVG references an element that does not exist")
    if view_box is None:  # pragma: no cover - guarded by the root check above
        raise OfflineHtmlError("SVG root needs a positive viewBox")
    return SanitizedSvg(
        markup=markup,
        view_box=view_box,
        nodes=nodes,
        edges=edges,
        edge_markers=edge_markers,
        element_count=element_count,
    )


def _assert_canvas_limits(canvas: Mapping[str, Any]) -> None:
    nodes = canvas.get("nodes", [])
    edges = canvas.get("edges", [])
    groups = sum(1 for node in nodes if node.get("type") == "group")
    if (
        len(nodes) > MAX_NATIVE_NODES
        or len(edges) > MAX_NATIVE_EDGES
        or len(edges) * len(edges) > MAX_NATIVE_ROUTING_PAIRS
        or groups > MAX_NATIVE_GROUPS
    ):
        raise OfflineHtmlError("JSON Canvas document exceeds the product complexity limits")


_TYPE_LABELS: Final = {"text": "Text", "file": "Datei", "link": "Link", "group": "Gruppe"}


def _node_text(node: Mapping[str, Any]) -> str:
    node_type = node["type"]
    if node_type == "text":
        return str(node.get("text", ""))
    if node_type == "file":
        subpath = node.get("subpath")
        return str(node["file"]) + (str(subpath) if subpath else "")
    if node_type == "link":
        return str(node["url"])
    return str(node.get("label", ""))


def _assert_svg_matches_canvas(canvas: Mapping[str, Any], sanitized: SanitizedSvg) -> None:
    node_types = {str(node["id"]): str(node["type"]) for node in canvas.get("nodes", [])}
    edge_by_id = {str(edge["id"]): edge for edge in canvas.get("edges", [])}
    if set(sanitized.nodes) != set(node_types):
        raise OfflineHtmlError("SVG nodes do not match the Canvas document")
    if set(sanitized.edges) != set(edge_by_id):
        raise OfflineHtmlError("SVG edges do not match the Canvas document")
    for node_id, node_type in node_types.items():
        if sanitized.nodes[node_id] != node_type:
            raise OfflineHtmlError("SVG node type does not match the Canvas document")
    for edge_id, edge in edge_by_id.items():
        markers = sanitized.edge_markers[edge_id]
        if edge.get("toEnd", "arrow") == "arrow" and "marker-end" not in markers:
            raise OfflineHtmlError("SVG lost an edge end marker of the Canvas document")
        if edge.get("fromEnd", "none") == "arrow" and "marker-start" not in markers:
            raise OfflineHtmlError("SVG lost an edge start marker of the Canvas document")


def _render_items(canvas: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for node in canvas.get("nodes", []):
        node_id = str(node["id"])
        node_type = str(node["type"])
        text = _node_text(node)
        rows.append(
            f'<li data-node-id="{html.escape(node_id, quote=True)}" '
            f'data-node-type="{html.escape(_TYPE_LABELS[node_type], quote=True)}">'
            f'<button class="ofh-item" type="button">'
            f'<span class="ofh-kind">{html.escape(_TYPE_LABELS[node_type])}</span>'
            f'<span class="ofh-text">{html.escape(text)}</span></button></li>'
        )
    return "\n".join(rows)


def build_offline_html(
    canvas: Mapping[str, Any], svg: str, *, title: str = "Schaubild"
) -> OfflineHtmlResult:
    """Return one self-contained offline HTML file for a validated Canvas and its SVG.

    The output depends only on the arguments: no clock, randomness or environment.
    """

    if not isinstance(title, str):
        raise OfflineHtmlError("title must be text")
    try:
        document = json_canvas_to_editing_document(canvas, title=title)
    except NativeDocumentError as exc:
        raise OfflineHtmlError(f"JSON Canvas document is invalid: {exc}") from exc
    validated = document["source"]
    _assert_canvas_limits(validated)
    sanitized = sanitize_native_svg(svg)
    _assert_svg_matches_canvas(validated, sanitized)

    source_sha256 = str(document["source_digest"])
    svg_sha256 = _sha256_hex(sanitized.markup.encode("utf-8"))
    safe_title = html.escape(_bounded_html_title(title.strip() or "Schaubild"))
    node_count = len(validated.get("nodes", []))
    edge_count = len(validated.get("edges", []))
    items = _render_items(validated)
    page = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{html.escape(content_security_policy())}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="generator" content="Schauwerk Schaubild offline HTML">
<meta name="schauwerk:schema" content="{OFFLINE_HTML_SCHEMA}">
<meta name="schauwerk:source-sha256" content="{source_sha256}">
<meta name="schauwerk:svg-sha256" content="{svg_sha256}">
<title>{safe_title}</title>
<style>{VIEWER_CSS}</style>
</head>
<body>
<header class="ofh-bar">
<h1>{safe_title}</h1>
<span class="ofh-badge">Nur Ansicht · offline</span>
<div class="ofh-tools" role="group" aria-label="Ansicht">
<button class="ofh-button" id="ofh-zoom-out" type="button" aria-label="Verkleinern" title="Verkleinern (−)">−</button>
<button class="ofh-button" id="ofh-zoom-in" type="button" aria-label="Vergrößern" title="Vergrößern (+)">+</button>
<button class="ofh-button" id="ofh-fit" type="button" title="Ansicht einpassen (0)">Einpassen</button>
</div>
</header>
<div class="ofh-body">
<main id="ofh-stage" tabindex="0" role="region" aria-label="Schaubild: {safe_title}" aria-describedby="ofh-help">
{sanitized.markup}
</main>
<aside class="ofh-side" aria-label="Suche und Fokus">
<div class="ofh-search" role="search">
<input id="ofh-search" type="search" placeholder="Knoten suchen (/)" aria-label="Knoten suchen" autocomplete="off" spellcheck="false">
<button class="ofh-button" id="ofh-prev" type="button" aria-label="Voriger Treffer" title="Voriger Treffer (Umschalt+Eingabe)">↑</button>
<button class="ofh-button" id="ofh-next" type="button" aria-label="Nächster Treffer" title="Nächster Treffer (Eingabe)">↓</button>
</div>
<p id="ofh-status" role="status" aria-live="polite">{node_count} Knoten</p>
<p id="ofh-help" class="ofh-badge">Ziehen verschiebt · Mausrad oder +/− zoomt · 0 passt ein · Pfeiltasten verschieben</p>
<ul id="ofh-results" aria-label="Knoten">
{items}
</ul>
<section id="ofh-detail" aria-live="polite">
<h2>Auswahl</h2>
<p id="ofh-detail-meta"></p>
<pre id="ofh-detail-text"></pre>
</section>
</aside>
</div>
<footer class="ofh-foot">Schauwerk Schaubild · {node_count} Knoten · {edge_count} Verbindungen · Quelle sha256:{source_sha256[:16]} · Abgeleitete Nur-Lese-Ansicht, kein Importformat</footer>
<script>{VIEWER_JS}</script>
</body>
</html>
"""
    payload = page.encode("utf-8")
    if len(payload) > MAX_OFFLINE_HTML_BYTES:
        raise OfflineHtmlError("offline HTML exceeds the export size limit")
    return OfflineHtmlResult(
        html=payload,
        sha256=_sha256_hex(payload),
        source_sha256=source_sha256,
        svg_sha256=svg_sha256,
        node_count=node_count,
        edge_count=edge_count,
    )
