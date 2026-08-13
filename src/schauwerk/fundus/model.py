"""Versioned contracts for the Miro-independent Schauwerk Fundus."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .pathio import read_regular_bytes

ASSET_SCHEMA = "schauwerk-fundus-asset.v1"
FAMILY_SCHEMA = "schauwerk-fundus-family.v1"
RECIPE_SCHEMA = "schauwerk-fundus-recipe.v1"
BUILD_SCHEMA = "schauwerk-fundus-build.v1"
ACCEPTANCE_SCHEMA = "schauwerk-fundus-acceptance.v1"
PACKAGE_SCHEMA = "schauwerk-fundus-package.v1"
INGEST_SCHEMA = "schauwerk-fundus-ingest.v1"
PREVIEW_SCHEMA = "schauwerk-fundus-preview.v1"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SOURCE_ROLES = {"original", "trace_source", "texture_source", "reference"}
OUTPUT_ROLES = {"vector", "mask", "outline", "raster", "texture", "preview"}
RIGHTS_STATUSES = {"owned", "licensed", "unknown", "restricted"}


def canonical_json(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not canonical JSON") from exc
    return rendered.encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(
    value: dict[str, Any],
    *,
    allowed: set[str],
    required: set[str],
    label: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(missing)}")


def checked_id(value: Any, *, label: str = "id") -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must match {_ID_RE.pattern}")
    return value


def checked_sha256(value: Any, *, label: str = "sha256") -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def checked_filename(value: Any, *, label: str = "filename") -> str:
    if not isinstance(value, str) or _FILENAME_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a safe bounded basename")
    if value in {".", ".."}:
        raise ValueError(f"{label} is unsafe")
    return value


def _bounded_text(
    value: Any,
    *,
    label: str,
    maximum: int,
    required: bool = True,
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    return text


def load_json(path: Path, *, maximum_bytes: int = 1_048_576) -> dict[str, Any]:
    payload = read_regular_bytes(
        path,
        maximum_bytes=maximum_bytes,
        label="manifest",
    )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid UTF-8 JSON manifest: {path}") from exc

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"invalid JSON manifest: {path}") from exc
    return _mapping(value, label="manifest")


def validate_family(value: Any) -> dict[str, Any]:
    doc = _mapping(value, label="family")
    _exact_keys(
        doc,
        allowed={"schema_version", "id", "title", "tags"},
        required={"schema_version", "id", "title", "tags"},
        label="family",
    )
    if doc.get("schema_version") != FAMILY_SCHEMA:
        raise ValueError(f"family schema_version must be {FAMILY_SCHEMA}")
    checked_id(doc.get("id"), label="family id")
    _bounded_text(doc.get("title"), label="family title", maximum=240)
    tags = doc.get("tags")
    if not isinstance(tags, list) or len(tags) > 32:
        raise ValueError("family tags must be an array with at most 32 entries")
    checked_tags: list[str] = []
    for index, item in enumerate(tags):
        tag = _bounded_text(item, label=f"family tag {index}", maximum=80)
        assert tag is not None
        checked_tags.append(tag)
    if len(set(checked_tags)) != len(checked_tags):
        raise ValueError("family tags must be unique")
    return doc


def validate_asset(value: Any) -> dict[str, Any]:
    doc = _mapping(value, label="asset")
    _exact_keys(
        doc,
        allowed={
            "schema_version",
            "id",
            "family",
            "recipe",
            "sources",
            "properties",
        },
        required={"schema_version", "id", "recipe", "sources"},
        label="asset",
    )
    if doc.get("schema_version") != ASSET_SCHEMA:
        raise ValueError(f"asset schema_version must be {ASSET_SCHEMA}")
    checked_id(doc.get("id"), label="asset id")
    checked_id(doc.get("recipe"), label="recipe id")
    family = doc.get("family")
    if family is not None:
        checked_id(family, label="family id")
    sources = doc.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
        raise ValueError("asset sources must contain between 1 and 8 entries")
    seen_roles: set[str] = set()
    for index, raw in enumerate(sources):
        source = _mapping(raw, label=f"asset source {index}")
        _exact_keys(
            source,
            allowed={
                "role",
                "sha256",
                "media_type",
                "origin",
                "rights_status",
            },
            required={"role", "sha256", "media_type"},
            label=f"asset source {index}",
        )
        role = source.get("role")
        if role not in SOURCE_ROLES or role in seen_roles:
            raise ValueError(
                f"asset source role is invalid or duplicated: {role}"
            )
        seen_roles.add(role)
        checked_sha256(
            source.get("sha256"),
            label=f"asset source {index} sha256",
        )
        _bounded_text(
            source.get("media_type"),
            label="media_type",
            maximum=100,
        )
        if "origin" in source:
            _bounded_text(
                source.get("origin"),
                label="origin",
                maximum=200,
            )
        if source.get("rights_status", "unknown") not in RIGHTS_STATUSES:
            raise ValueError("rights_status is invalid")
    properties = doc.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("asset properties must be an object")
    allowed_properties = {
        "mirror_safe",
        "rotate_safe",
        "recolor_safe",
        "mask_safe",
        "tile_safe",
    }
    if set(properties) - allowed_properties:
        raise ValueError("asset properties contain unknown fields")
    if any(not isinstance(item, bool) for item in properties.values()):
        raise ValueError("asset properties must be booleans")
    return doc


def validate_recipe(value: Any) -> dict[str, Any]:
    doc = _mapping(value, label="recipe")
    _exact_keys(
        doc,
        allowed={
            "schema_version",
            "id",
            "transform",
            "source_role",
            "output",
            "parameters",
        },
        required={
            "schema_version",
            "id",
            "transform",
            "source_role",
            "output",
            "parameters",
        },
        label="recipe",
    )
    if doc.get("schema_version") != RECIPE_SCHEMA:
        raise ValueError(f"recipe schema_version must be {RECIPE_SCHEMA}")
    checked_id(doc.get("id"), label="recipe id")
    if doc.get("transform") != "sanitize_svg":
        raise ValueError("V1 supports only the sanitize_svg transform")
    if doc.get("source_role") not in SOURCE_ROLES:
        raise ValueError("recipe source_role is invalid")
    output = _mapping(doc.get("output"), label="recipe output")
    _exact_keys(
        output,
        allowed={"role", "filename", "media_type"},
        required={"role", "filename", "media_type"},
        label="recipe output",
    )
    if output.get("role") not in OUTPUT_ROLES:
        raise ValueError("recipe output role is invalid")
    checked_filename(
        output.get("filename"),
        label="recipe output filename",
    )
    if output.get("media_type") != "image/svg+xml":
        raise ValueError("sanitize_svg output must use image/svg+xml")
    parameters = _mapping(
        doc.get("parameters"),
        label="recipe parameters",
    )
    _exact_keys(
        parameters,
        allowed={"profile"},
        required={"profile"},
        label="recipe parameters",
    )
    if parameters.get("profile") not in {
        "svg.mask.v1",
        "svg.decorative.v1",
    }:
        raise ValueError("unknown SVG profile")
    return doc
