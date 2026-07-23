"""Deterministic repository contract for Miro Developer App icon assets."""

from __future__ import annotations

import hashlib
import re
from importlib import resources
from typing import Any
from xml.etree import ElementTree as ET

ASSET_SCHEMA = "schauwerk-miro-app-asset-receipt.v1"
EXPECTED_DIGESTS = {
    "outline": "103f8d1a4bf894f9b87f20019b1bbe68104a9d914fa680f5d35655bdf0188168",
    "color": "b9a6625731a53101a2891f75a8482a49bb9ad69ffa3a2d16ef2175ece63485df",
}
ASSET_FILES = {"outline": "app-icon-outline.svg", "color": "app-icon-color.svg"}
_ALLOWED_TAGS = {"svg", "rect", "path", "circle", "ellipse", "line", "polyline", "polygon", "g"}
_SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "cookie",
    "session",
    "authorization",
    "bearer",
    "api_key",
    "apikey",
)
_MAX_SVG_BYTES = 128 * 1024
_ALLOWED_ATTRS = {
    "viewBox",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linejoin",
    "stroke-linecap",
    "x",
    "y",
    "width",
    "height",
    "rx",
    "ry",
    "cx",
    "cy",
    "r",
    "d",
    "points",
    "transform",
}
_COLOR_RE = re.compile(r"^(?:#[0-9a-fA-F]{3,8}|[A-Za-z]+)$")


class AppAssetError(ValueError):
    """The canonical Miro app asset contract is invalid."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _looks_sensitive_text(value: str) -> bool:
    lowered = value.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _reject_sensitive_keys(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS):
                raise AppAssetError(f"sensitive receipt key is forbidden at {path}.{key}")
            _reject_sensitive_keys(child, path=f"{path}.{key}")
    elif isinstance(value, str):
        if _looks_sensitive_text(value):
            raise AppAssetError(f"sensitive receipt value is forbidden at {path}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, path=f"{path}[{index}]")


def validate_svg_bytes(data: bytes, *, role: str) -> dict[str, Any]:
    if role not in ASSET_FILES:
        raise AppAssetError("unsupported icon role")
    if len(data) > _MAX_SVG_BYTES:
        raise AppAssetError("SVG exceeds maximum allowed size")
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise AppAssetError("SVG declarations and entities are forbidden")
    if not data.endswith(b"\n") or data.endswith(b"\n\n"):
        raise AppAssetError("SVG bytes must end with exactly one newline")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise AppAssetError("icon must be valid SVG XML") from exc
    if _local(root.tag) != "svg":
        raise AppAssetError("root element must be svg")

    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise AppAssetError("icon must declare a four-number viewBox")
    try:
        _, _, width, height = (float(part) for part in view_box)
    except ValueError as exc:
        raise AppAssetError("viewBox must contain numbers") from exc
    if width <= 0 or height <= 0 or width != height:
        raise AppAssetError("icon viewBox must be positive and square")

    colors: set[str] = set()
    for element in root.iter():
        tag = _local(element.tag)
        if tag not in _ALLOWED_TAGS:
            raise AppAssetError(f"unsupported SVG element: {tag}")
        for name, value in element.attrib.items():
            local_name = _local(name)
            if local_name not in _ALLOWED_ATTRS:
                raise AppAssetError(f"unsupported SVG attribute: {local_name}")
            if local_name in {"fill", "stroke"} and value not in {"none", "transparent"}:
                if value.startswith("url(") or not _COLOR_RE.match(value):
                    raise AppAssetError("SVG paint must use a direct color")
                colors.add(value.lower())
    if role == "outline" and len(colors) != 1:
        raise AppAssetError("outline icon must be monochrome")
    return {
        "role": role,
        "sha256": _digest(data),
        "view_box": view_box,
        "colors": sorted(colors),
    }


def validate_canonical_assets() -> dict[str, Any]:
    package = resources.files("schauwerk.web_sdk_assets")
    assets: dict[str, Any] = {}
    for role, filename in ASSET_FILES.items():
        data = package.joinpath(filename).read_bytes()
        result = validate_svg_bytes(data, role=role)
        if result["sha256"] != EXPECTED_DIGESTS[role]:
            raise AppAssetError(f"canonical {role} icon digest mismatch")
        assets[role] = result
    return {"schema_version": "schauwerk-miro-app-assets.v1", "assets": assets}


def build_asset_receipt(
    *,
    app_id: str,
    app_url: str,
    scopes: list[str],
    upload_responses: dict[str, Any],
    provider_readback: dict[str, Any],
) -> dict[str, Any]:
    if not app_id.strip():
        raise AppAssetError("app_id is required")
    if scopes != ["boards:read"]:
        raise AppAssetError("Miro app scope contract must remain exactly boards:read")
    if not app_url.startswith("https://"):
        raise AppAssetError("app_url must use HTTPS")
    _reject_sensitive_keys(upload_responses, path="upload_responses")
    _reject_sensitive_keys(provider_readback, path="provider_readback")
    assets = validate_canonical_assets()["assets"]
    return {
        "schema_version": ASSET_SCHEMA,
        "app_id": app_id,
        "app_url": app_url,
        "scopes": scopes,
        "assets": {
            role: {"sha256": value["sha256"], "filename": ASSET_FILES[role]}
            for role, value in assets.items()
        },
        "upload_responses": upload_responses,
        "provider_readback": provider_readback,
        "credential_material_included": False,
    }
