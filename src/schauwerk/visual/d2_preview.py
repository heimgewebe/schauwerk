"""Optional D2/TALA preview for validated canonical Schaubild representations.

The native editor retains source and editing authority. The alternative
rendering is strictly passive and never changes the document or its history.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from .representation import validate_representation_input

RENDERER_ID: Final = "d2-tala"
EXPECTED_VERSION: Final = "v0.9.0"
SUPPORTED_INTENTS: Final = frozenset({"process", "architecture"})
MAX_SOURCE_BYTES: Final = 256 * 1024
MAX_SVG_BYTES: Final = 2 * 1024 * 1024
RENDER_TIMEOUT_SECONDS: Final = 7
SVG_NS: Final = "http://www.w3.org/2000/svg"
_SAFE_TAGS: Final = frozenset({
    "svg", "g", "defs", "rect", "path", "polygon", "polyline",
    "line", "circle", "ellipse", "text", "tspan", "title", "desc",
    "style", "marker", "mask", "clipPath", "linearGradient",
    "radialGradient", "stop",
})
_D2_CONNECTION_KEY = re.compile(
    r"^(?:(?P<scope>g_[a-z0-9_]+)\.)?\("
    r"(?P<source>(?:g_[a-z0-9_]+\.)?n_[a-z0-9_]+)"
    r" -> "
    r"(?P<target>(?:g_[a-z0-9_]+\.)?n_[a-z0-9_]+)"
    r"\)\[(?P<ordinal>\d+)\]$"
)
_CSS_URL = re.compile(r"url\(\s*([\"']?)(.*?)\1\s*\)", re.IGNORECASE)


class D2PreviewError(ValueError):
    """An alternative SVG cannot be proven source-bound and passive."""


def _d2_quoted(value: str) -> str:
    # D2 expands variable interpolations in double-quoted strings. Escape
    # them only after JSON-style quoting, preserving slashes and both quotes.
    quoted = json.dumps(value.replace("\r", " ").replace("\n", " "), ensure_ascii=False)
    return quoted.replace("$" + "{", "\\" + "$" + "{")


def _display_node(node: Mapping[str, Any]) -> str:
    label = str(node["label"])
    kind = str(node["kind"])
    summary = str(node.get("summary") or "")
    return f"{label} [{kind}]" + (f" — {summary}" if summary else "")


def _display_edge(edge: Mapping[str, Any]) -> str:
    return f"{edge['label']} [{edge['kind']}]"


def d2_source(model: Mapping[str, Any]) -> str:
    """Compile one normalized representation without changing its authority."""
    lines = ["direction: right", f"# Source document: {model['id']}"]
    node_keys: dict[str, str] = {}
    groups: dict[str | None, list[Mapping[str, Any]]] = {None: []}
    for group in model["groups"]:
        groups[str(group["id"])] = []
    for node in model["nodes"]:
        group = str(node["group"]) if node.get("group") else None
        groups[group].append(node)
        node_keys[str(node["id"])] = (
            f"g_{group}.n_{node['id']}" if group else f"n_{node['id']}"
        )
    for node in groups[None]:
        lines.append(f"n_{node['id']}: {_d2_quoted(_display_node(node))}")
    for group in model["groups"]:
        gid = str(group["id"])
        lines.append(f"g_{gid}: {_d2_quoted(str(group['label']))} {{")
        for node in groups[gid]:
            lines.append(f"  n_{node['id']}: {_d2_quoted(_display_node(node))}")
        lines.append("}")
    for edge in model["edges"]:
        lines.append(
            f"{node_keys[str(edge['from'])]} -> {node_keys[str(edge['to'])]}: "
            f"{_d2_quoted(_display_edge(edge))}"
        )
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=4)
def _probe_binary(configured: str) -> Path | None:
    candidate = Path(configured)
    if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate, os.X_OK):
        return None
    try:
        result = subprocess.run(
            [str(candidate), "--version"],
            timeout=2,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode != 0 or version != EXPECTED_VERSION:
        return None
    return candidate


def configured_binary() -> Path | None:
    """Explicit opt-in: no unpinned PATH fallback or implicit production enablement."""
    configured = os.environ.get("SCHAUWERK_D2_PREVIEW_BINARY", "").strip()
    return _probe_binary(configured) if configured else None


def _svg_keys(root: ET.Element) -> set[str]:
    keys: set[str] = set()
    for item in root.iter():
        if item.tag != f"{{{SVG_NS}}}g":
            continue
        for token in item.get("class", "").split():
            if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", token):
                continue
            try:
                raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=True)
                keys.add(html.unescape(raw.decode("utf-8")))
            except (UnicodeError, ValueError):
                continue
    return keys


def _edge_signature(key: str) -> tuple[str, str, int] | None:
    match = _D2_CONNECTION_KEY.fullmatch(key)
    if match is None:
        return None
    scope = match.group("scope")
    source, target = match.group("source"), match.group("target")
    if scope:
        if "." not in source:
            source = f"{scope}.{source}"
        if "." not in target:
            target = f"{scope}.{target}"
    return source, target, int(match.group("ordinal"))


def _assert_passive_svg(svg: bytes) -> ET.Element:
    if not svg or len(svg) > MAX_SVG_BYTES:
        raise D2PreviewError("D2 SVG exceeds the bounded output size")
    lower = svg.lower()
    if b"<!doctype" in lower or b"<!entity" in lower:
        raise D2PreviewError("D2 SVG must not contain document declarations")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise D2PreviewError("D2 produced invalid SVG") from exc
    if root.tag != f"{{{SVG_NS}}}svg" or root.get("data-d2-version") != EXPECTED_VERSION:
        raise D2PreviewError("D2 SVG root/version contract drifted")
    for item in root.iter():
        local = item.tag.removeprefix(f"{{{SVG_NS}}}")
        if local not in _SAFE_TAGS:
            raise D2PreviewError(f"D2 SVG contains unsupported active/unknown element: {local}")
        for name, value in item.attrib.items():
            field = name.rsplit("}", 1)[-1].casefold()
            if field.startswith("on") or field in {"href", "src"}:
                raise D2PreviewError("D2 SVG includes executable or linked attributes")
            if "url(" in value.casefold():
                for match in _CSS_URL.finditer(value):
                    location = match.group(2).strip()
                    if not (location.startswith("#") or location.startswith("data:")):
                        raise D2PreviewError("D2 SVG includes an external URL")
        if local == "style":
            css = item.text or ""
            if re.search(r"@import\b|javascript:|https?://", css, re.IGNORECASE):
                raise D2PreviewError("D2 SVG includes an external/active style")
            for match in _CSS_URL.finditer(css):
                location = match.group(2).strip()
                if not (location.startswith("#") or location.startswith("data:")):
                    raise D2PreviewError("D2 SVG stylesheet includes an external URL")
    return root


def _assert_structure(root: ET.Element, model: Mapping[str, Any]) -> None:
    keys = _svg_keys(root)
    node_keys: dict[str, str] = {}
    for node in model["nodes"]:
        gid = node.get("group")
        node_keys[str(node["id"])] = (
            f"g_{gid}.n_{node['id']}" if gid else f"n_{node['id']}"
        )
    expected_groups = {f"g_{group['id']}" for group in model["groups"]}
    expected_nodes = set(node_keys.values())
    seen_groups = keys & expected_groups
    seen_nodes = keys & expected_nodes

    ordinals: Counter[tuple[str, str]] = Counter()
    expected_edges: set[tuple[str, str, int]] = set()
    for edge in model["edges"]:
        pair = (node_keys[str(edge["from"])], node_keys[str(edge["to"])])
        expected_edges.add((*pair, ordinals[pair]))
        ordinals[pair] += 1
    actual_edges = {
        signature for key in keys if (signature := _edge_signature(key)) is not None
    }
    expected_labels = {
        *(str(group["label"]) for group in model["groups"]),
        *(_display_node(node) for node in model["nodes"]),
        *(_display_edge(edge) for edge in model["edges"]),
    }
    visible_labels = {
        "".join(item.itertext())
        for item in root.iter()
        if item.tag == f"{{{SVG_NS}}}text"
    }
    if (
        seen_nodes != expected_nodes
        or seen_groups != expected_groups
        or actual_edges != expected_edges
        or not expected_labels.issubset(visible_labels)
    ):
        raise D2PreviewError("D2 SVG is incomplete or has drifted from its source")
    # The original edge ID remains in the source, not in the SVG; consequently
    # the preview is strictly read-only and cannot become an editing surface.


def render_d2_tala(value: Mapping[str, Any], binary: Path) -> tuple[bytes, str]:
    model = validate_representation_input(value)
    if model["intent"] not in SUPPORTED_INTENTS:
        raise D2PreviewError("D2/TALA preview is not available for this diagram type")
    if (
        len(model["groups"]) > 32
        or len(model["nodes"]) > 128
        or len(model["edges"]) > 128
    ):
        raise D2PreviewError("D2/TALA preview exceeds its complexity limits")
    source = d2_source(model).encode("utf-8")
    if len(source) > MAX_SOURCE_BYTES:
        raise D2PreviewError("D2/TALA preview source exceeds its size limit")
    try:
        result = subprocess.run(
            [str(binary), "--layout=tala", "-", "-"],
            input=source,
            capture_output=True,
            timeout=RENDER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise D2PreviewError("D2/TALA preview timed out") from exc
    except OSError as exc:
        raise D2PreviewError("D2/TALA binary is unavailable") from exc
    if result.returncode != 0:
        raise D2PreviewError("D2/TALA rejected this diagram")
    root = _assert_passive_svg(result.stdout)
    _assert_structure(root, model)
    return result.stdout, str(model["input_digest"])