"""Fail-closed SVG profiles for reusable Fundus output."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 512 * 1024
MAX_ELEMENTS = 2_000
MAX_DEPTH = 32
MAX_PATH_CHARS = 200_000
MAX_ATTRIBUTE_CHARS = 16_384
MAX_VIEWBOX_EXTENT = 100_000.0

_BASIC_TAGS = {
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
}
_DECORATIVE_TAGS = _BASIC_TAGS | {
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
}
_COMMON_ATTRS = {
    "viewBox",
    "width",
    "height",
    "preserveAspectRatio",
    "fill",
    "fill-rule",
    "clip-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "transform",
    "d",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "points",
}
_DECORATIVE_ATTRS = _COMMON_ATTRS | {
    "id",
    "gradientUnits",
    "gradientTransform",
    "fx",
    "fy",
    "fr",
    "offset",
    "stop-color",
    "stop-opacity",
    "clip-path",
    "mask",
    "maskUnits",
    "clipPathUnits",
}
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_URL_RE = re.compile(
    r"^url\(#([A-Za-z][A-Za-z0-9_.:-]{0,127})\)$"
)
_PATH_RE = re.compile(r"^[MmZzLlHhVvCcSsQqTtAa0-9+\-.,eE\s]*$")


def _local(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _namespace(value: str) -> str | None:
    if value.startswith("{") and "}" in value:
        return value[1:].split("}", 1)[0]
    return None


def _depth(root: ET.Element) -> int:
    maximum = 1
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        maximum = max(maximum, depth)
        stack.extend((child, depth + 1) for child in list(element))
    return maximum


def _validate_view_box(value: str) -> None:
    try:
        numbers = [
            float(item)
            for item in value.replace(",", " ").split()
        ]
    except ValueError as exc:
        raise ValueError("SVG viewBox contains invalid numbers") from exc
    if len(numbers) != 4:
        raise ValueError("SVG viewBox must contain four finite numbers")
    if any(not math.isfinite(number) for number in numbers):
        raise ValueError("SVG viewBox must contain four finite numbers")
    if numbers[2] <= 0 or numbers[3] <= 0:
        raise ValueError("SVG viewBox dimensions must be positive")
    if abs(numbers[0]) > MAX_VIEWBOX_EXTENT:
        raise ValueError("SVG viewBox origin exceeds the Fundus limit")
    if abs(numbers[1]) > MAX_VIEWBOX_EXTENT:
        raise ValueError("SVG viewBox origin exceeds the Fundus limit")
    if numbers[2] > MAX_VIEWBOX_EXTENT:
        raise ValueError("SVG viewBox dimensions exceed the Fundus limit")
    if numbers[3] > MAX_VIEWBOX_EXTENT:
        raise ValueError("SVG viewBox dimensions exceed the Fundus limit")


def sanitize_svg(payload: bytes, *, profile: str) -> bytes:
    if not payload or len(payload) > MAX_SVG_BYTES:
        raise ValueError(
            "SVG is empty or exceeds the Fundus SVG size limit"
        )
    upper = payload.upper()
    forbidden_declarations = (
        b"<!DOCTYPE",
        b"<!ENTITY",
        b"<?XML-STYLESHEET",
    )
    if any(item in upper for item in forbidden_declarations):
        raise ValueError(
            "SVG doctypes, entities and stylesheets are forbidden"
        )
    if profile == "svg.mask.v1":
        allowed_tags = _BASIC_TAGS
        allowed_attrs = _COMMON_ATTRS
        allow_internal_urls = False
    elif profile == "svg.decorative.v1":
        allowed_tags = _DECORATIVE_TAGS
        allowed_attrs = _DECORATIVE_ATTRS
        allow_internal_urls = True
    else:
        raise ValueError("unknown SVG security profile")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("SVG is not well-formed XML") from exc
    if _local(root.tag) != "svg":
        raise ValueError("SVG root element is missing")
    if _depth(root) > MAX_DEPTH:
        raise ValueError("SVG nesting exceeds the Fundus limit")
    elements = list(root.iter())
    if len(elements) > MAX_ELEMENTS:
        raise ValueError("SVG element count exceeds the Fundus limit")
    if "viewBox" not in root.attrib:
        raise ValueError("production SVG requires a viewBox")
    _validate_view_box(root.attrib["viewBox"])

    ids: set[str] = set()
    references: set[str] = set()
    path_chars = 0
    for element in elements:
        if not isinstance(element.tag, str):
            raise ValueError("non-element SVG nodes are forbidden")
        namespace = _namespace(element.tag)
        if namespace not in {None, SVG_NS}:
            raise ValueError("foreign SVG namespaces are forbidden")
        tag = _local(element.tag)
        if tag not in allowed_tags:
            raise ValueError(
                f"SVG element is forbidden by {profile}: {tag}"
            )
        normalized_attrs: dict[str, str] = {}
        for raw_name, raw_value in element.attrib.items():
            name = _local(raw_name)
            if _namespace(raw_name) not in {None, SVG_NS}:
                raise ValueError("foreign SVG attributes are forbidden")
            if name.lower().startswith("on"):
                raise ValueError(
                    f"active SVG attribute is forbidden: {name}"
                )
            if name in {"href", "style"}:
                raise ValueError(
                    f"active SVG attribute is forbidden: {name}"
                )
            if name not in allowed_attrs:
                raise ValueError(
                    f"SVG attribute is forbidden by {profile}: {name}"
                )
            value = raw_value.strip()
            # Path data has its own aggregate complexity budget below. Applying
            # the generic per-attribute cap here makes that dedicated budget
            # unreachable for legitimate compact traces with one long path.
            if name != "d" and len(value) > MAX_ATTRIBUTE_CHARS:
                raise ValueError(
                    "SVG attribute value is invalid or too large"
                )
            if any(
                ord(char) < 0x20 and char not in "\t\n\r"
                for char in value
            ):
                raise ValueError(
                    "SVG attribute value is invalid or too large"
                )
            lowered = value.lower()
            if any(
                token in lowered
                for token in (
                    "javascript:",
                    "data:",
                    "http:",
                    "https:",
                    "file:",
                )
            ):
                raise ValueError(
                    "external or active SVG references are forbidden"
                )
            if name == "id":
                if _ID_RE.fullmatch(value) is None or value in ids:
                    raise ValueError("SVG id is invalid or duplicated")
                ids.add(value)
            if "url(" in lowered:
                match = _URL_RE.fullmatch(value)
                if not allow_internal_urls or match is None:
                    raise ValueError(
                        "SVG URL references are forbidden "
                        "by the active profile"
                    )
                references.add(match.group(1))
            if name == "d":
                path_chars += len(value)
                if _PATH_RE.fullmatch(value) is None:
                    raise ValueError(
                        "SVG path data contains unsupported characters"
                    )
            normalized_attrs[name] = value
        element.tag = f"{{{SVG_NS}}}{tag}"
        element.attrib.clear()
        for name in sorted(normalized_attrs):
            element.attrib[name] = normalized_attrs[name]
        if element.text and element.text.strip():
            raise ValueError(
                "text content is forbidden in Fundus SVG geometry"
            )
        element.text = None
        element.tail = None
    if path_chars > MAX_PATH_CHARS:
        raise ValueError("SVG path complexity exceeds the Fundus limit")
    if references - ids:
        raise ValueError("SVG contains unresolved internal references")
    ET.register_namespace("", SVG_NS)
    rendered = (
        ET.tostring(
            root,
            encoding="utf-8",
            short_empty_elements=True,
        )
        + b"\n"
    )
    if len(rendered) > MAX_SVG_BYTES:
        raise ValueError("normalized SVG exceeds the Fundus size limit")
    return rendered
