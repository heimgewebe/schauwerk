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
RECIPE_SCHEMA_V2 = "schauwerk-fundus-recipe.v2"
RECIPE_SCHEMA_V3 = "schauwerk-fundus-recipe.v3"
BUILD_SCHEMA = "schauwerk-fundus-build.v1"
BUILD_SCHEMA_V2 = "schauwerk-fundus-build.v2"
ACCEPTANCE_SCHEMA = "schauwerk-fundus-acceptance.v1"
ACCEPTANCE_SCHEMA_V2 = "schauwerk-fundus-acceptance.v2"
PACKAGE_SCHEMA = "schauwerk-fundus-package.v1"
PACKAGE_SCHEMA_V2 = "schauwerk-fundus-package.v2"
INGEST_SCHEMA = "schauwerk-fundus-ingest.v1"
PREVIEW_SCHEMA = "schauwerk-fundus-preview.v1"
IMAGE_BRIEF_SCHEMA = "schauwerk-fundus-image-brief.v1"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SOURCE_ROLES = {"original", "trace_source", "texture_source", "reference"}
OUTPUT_ROLES = {"vector", "mask", "outline", "raster", "texture", "preview"}
RIGHTS_STATUSES = {"owned", "licensed", "unknown", "restricted"}
SOURCE_MODES = {"manual", "generated", "edited", "unknown"}
IMAGE_OPERATIONS = {"generate", "edit"}


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
                "source_mode",
                "image_brief_sha256",
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
        source_mode = source.get("source_mode", "unknown")
        if source_mode not in SOURCE_MODES:
            raise ValueError("source_mode is invalid")
        image_brief_sha256 = source.get("image_brief_sha256")
        if source_mode in {"generated", "edited"}:
            checked_sha256(
                image_brief_sha256,
                label=f"asset source {index} image brief sha256",
            )
        elif image_brief_sha256 is not None:
            raise ValueError(
                "image_brief_sha256 requires generated or edited source_mode"
            )
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


def validate_image_brief(value: Any) -> dict[str, Any]:
    doc = _mapping(value, label="image brief")
    _exact_keys(
        doc,
        allowed={
            "schema_version",
            "id",
            "intent",
            "asset_id",
            "family",
            "operation",
            "input_sha256",
            "source_role",
            "desired_output_roles",
            "requirements",
            "forbidden",
            "properties",
            "acceptance",
        },
        required={
            "schema_version",
            "id",
            "intent",
            "asset_id",
            "operation",
            "source_role",
            "desired_output_roles",
            "requirements",
            "forbidden",
            "properties",
            "acceptance",
        },
        label="image brief",
    )
    if doc.get("schema_version") != IMAGE_BRIEF_SCHEMA:
        raise ValueError(
            f"image brief schema_version must be {IMAGE_BRIEF_SCHEMA}"
        )
    checked_id(doc.get("id"), label="image brief id")
    checked_id(doc.get("asset_id"), label="image brief asset id")
    family = doc.get("family")
    if family is not None:
        checked_id(family, label="image brief family")
    if doc.get("intent") not in {"reusable_asset", "production_asset"}:
        raise ValueError("image brief intent is invalid")
    operation = doc.get("operation")
    if operation not in IMAGE_OPERATIONS:
        raise ValueError("image brief operation is invalid")
    input_sha256 = doc.get("input_sha256")
    if operation == "edit":
        checked_sha256(input_sha256, label="image brief input sha256")
    elif input_sha256 is not None:
        raise ValueError("generate image brief must not declare input_sha256")
    if doc.get("source_role") not in SOURCE_ROLES:
        raise ValueError("image brief source_role is invalid")

    output_roles = doc.get("desired_output_roles")
    if not isinstance(output_roles, list) or not 1 <= len(output_roles) <= 6:
        raise ValueError(
            "image brief desired_output_roles must contain 1 to 6 entries"
        )
    if any(item not in OUTPUT_ROLES for item in output_roles):
        raise ValueError("image brief desired_output_roles are invalid")
    if len(set(output_roles)) != len(output_roles):
        raise ValueError("image brief desired_output_roles must be unique")

    for field in ("requirements", "forbidden"):
        values = doc.get(field)
        if not isinstance(values, list) or len(values) > 32:
            raise ValueError(f"image brief {field} must contain at most 32 entries")
        checked: list[str] = []
        for index, item in enumerate(values):
            text = _bounded_text(
                item,
                label=f"image brief {field} {index}",
                maximum=240,
            )
            assert text is not None
            checked.append(text)
        if len(set(checked)) != len(checked):
            raise ValueError(f"image brief {field} must be unique")

    properties = _mapping(doc.get("properties"), label="image brief properties")
    allowed_properties = {
        "mirror_safe",
        "rotate_safe",
        "recolor_safe",
        "mask_safe",
        "tile_safe",
    }
    _exact_keys(
        properties,
        allowed=allowed_properties,
        required=set(),
        label="image brief properties",
    )
    if any(not isinstance(item, bool) for item in properties.values()):
        raise ValueError("image brief properties must be booleans")

    acceptance = _mapping(doc.get("acceptance"), label="image brief acceptance")
    _exact_keys(
        acceptance,
        allowed={"visual_review_required", "inheritance"},
        required={"visual_review_required", "inheritance"},
        label="image brief acceptance",
    )
    if acceptance.get("visual_review_required") is not True:
        raise ValueError("generative image briefs require visual review")
    if acceptance.get("inheritance") not in {
        "none",
        "deterministic_recipe_only",
    }:
        raise ValueError("image brief acceptance inheritance is invalid")
    return doc


def _validate_recipe_operation(value: Any, *, label: str) -> dict[str, Any]:
    operation = _mapping(value, label=label)
    _exact_keys(
        operation,
        allowed={"transform", "source_role", "output", "parameters"},
        required={"transform", "source_role", "output", "parameters"},
        label=label,
    )
    transform = operation.get("transform")
    if transform not in {"sanitize_svg", "raster_normalize", "trace_vtracer"}:
        raise ValueError("recipe transform is unsupported")
    if operation.get("source_role") not in SOURCE_ROLES:
        raise ValueError("recipe source_role is invalid")

    output = _mapping(operation.get("output"), label=f"{label} output")
    _exact_keys(
        output,
        allowed={"role", "filename", "media_type"},
        required={"role", "filename", "media_type"},
        label=f"{label} output",
    )
    if output.get("role") not in OUTPUT_ROLES:
        raise ValueError("recipe output role is invalid")
    checked_filename(output.get("filename"), label="recipe output filename")

    parameters = _mapping(operation.get("parameters"), label=f"{label} parameters")
    _exact_keys(
        parameters,
        allowed={"profile"},
        required={"profile"},
        label=f"{label} parameters",
    )
    profile = parameters.get("profile")

    if transform == "sanitize_svg":
        if output.get("media_type") != "image/svg+xml":
            raise ValueError("sanitize_svg output must use image/svg+xml")
        if profile not in {"svg.mask.v1", "svg.decorative.v1"}:
            raise ValueError("unknown SVG profile")
    elif transform == "raster_normalize":
        if output.get("media_type") != "image/png":
            raise ValueError("raster_normalize output must use image/png")
        if output.get("role") not in {"raster", "texture", "preview"}:
            raise ValueError("raster_normalize output role must remain raster-like")
        if profile != "raster.png.rgba.v1":
            raise ValueError("unknown raster profile")
    else:
        if output.get("media_type") != "image/svg+xml":
            raise ValueError("trace_vtracer output must use image/svg+xml")
        if output.get("role") not in {"vector", "outline", "mask"}:
            raise ValueError("trace_vtracer output role must be vector-like")
        if profile not in {
            "trace.vtracer.color.v1",
            "trace.vtracer.alpha-mask.v1",
        }:
            raise ValueError("unknown trace profile")
    return operation


def validate_recipe(value: Any) -> dict[str, Any]:
    doc = _mapping(value, label="recipe")
    schema = doc.get("schema_version")
    if schema == RECIPE_SCHEMA:
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
        checked_id(doc.get("id"), label="recipe id")
        _validate_recipe_operation(
            {
                "transform": doc["transform"],
                "source_role": doc["source_role"],
                "output": doc["output"],
                "parameters": doc["parameters"],
            },
            label="recipe",
        )
        return doc

    if schema in {RECIPE_SCHEMA_V2, RECIPE_SCHEMA_V3}:
        version = "v2" if schema == RECIPE_SCHEMA_V2 else "v3"
        required = {"schema_version", "id", "operations"}
        allowed = set(required)
        if schema == RECIPE_SCHEMA_V3:
            required.add("acceptance")
            allowed.add("acceptance")
        _exact_keys(
            doc,
            allowed=allowed,
            required=required,
            label="recipe",
        )
        checked_id(doc.get("id"), label="recipe id")
        operations = doc.get("operations")
        if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
            raise ValueError(
                f"recipe {version} operations must contain between 1 and 8 entries"
            )
        seen_roles: set[str] = set()
        seen_filenames: set[str] = set()
        for index, raw in enumerate(operations):
            operation = _validate_recipe_operation(raw, label=f"recipe operation {index}")
            output = operation["output"]
            role = output["role"]
            filename = output["filename"]
            if role in seen_roles:
                raise ValueError(
                    f"recipe {version} output role is duplicated: {role}"
                )
            if filename in seen_filenames:
                raise ValueError(
                    f"recipe {version} output filename is duplicated: {filename}"
                )
            seen_roles.add(role)
            seen_filenames.add(filename)
        if schema == RECIPE_SCHEMA_V3:
            acceptance = _mapping(
                doc.get("acceptance"), label="recipe acceptance"
            )
            _exact_keys(
                acceptance,
                allowed={"inheritance"},
                required={"inheritance"},
                label="recipe acceptance",
            )
            if acceptance.get("inheritance") != (
                "identical_sources_and_outputs_only"
            ):
                raise ValueError("recipe acceptance inheritance is invalid")
        return doc

    raise ValueError(
        "recipe schema_version must be "
        f"{RECIPE_SCHEMA}, {RECIPE_SCHEMA_V2} or {RECIPE_SCHEMA_V3}"
    )
