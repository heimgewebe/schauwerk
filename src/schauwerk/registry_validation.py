"""Validation for the Git-versioned Schauwerk registry."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from schauwerk.fundus.model import (
    digest_json,
    load_json,
    validate_asset,
    validate_family,
    validate_image_brief,
)


@dataclass(frozen=True)
class RegistrySpec:
    filename: str
    key: str
    schema_filename: str | None


REGISTRIES = (
    RegistrySpec("sources.yaml", "sources", "source.v1.schema.json"),
    RegistrySpec("projects.yaml", "projects", "project.v1.schema.json"),
    RegistrySpec("surfaces.yaml", "surfaces", "surface.v1.schema.json"),
    RegistrySpec("views.yaml", "views", "view.v1.schema.json"),
    RegistrySpec("regions.yaml", "regions", "region.v1.schema.json"),
    RegistrySpec("policies.yaml", "policies", "policy.v1.schema.json"),
    RegistrySpec("publications.yaml", "publications", "publication.v1.schema.json"),
)

FORBIDDEN_KEYS = {
    "access_token",
    "refresh_token",
    "client_secret",
    "board_access_token",
    "password",
}


class RegistryValidationError(ValueError):
    """Raised when registry content violates a contract."""


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryValidationError(f"{path}: expected mapping")
    if raw.get("schema_version") != 1:
        raise RegistryValidationError(f"{path}: schema_version must be 1")
    return raw


def _check_forbidden_keys(value: Any, location: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise RegistryValidationError(f"{location}: forbidden key {key!r}")
            _check_forbidden_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_forbidden_keys(child, f"{location}[{index}]")


def _load_fundus_documents(
    directory: Path,
    *,
    label: str,
    validator: Callable[[Any], dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], str, Path]]:
    if not directory.is_dir():
        raise RegistryValidationError(f"{directory}: Fundus {label} registry is missing")

    loaded: dict[str, tuple[dict[str, Any], str, Path]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            value = load_json(path, maximum_bytes=256_000)
            validator(value)
            digest = digest_json(value)
        except (OSError, ValueError) as exc:
            raise RegistryValidationError(f"{path}: {exc}") from exc

        identifier = value["id"]
        if path.stem != identifier:
            raise RegistryValidationError(
                f"{path}: {label} id {identifier!r} does not match registry filename"
            )
        if identifier in loaded:
            raise RegistryValidationError(f"{directory}: duplicate {label} id {identifier!r}")
        loaded[identifier] = (value, digest, path)
    return loaded


def _validate_fundus_briefs(repo_root: Path) -> int:
    fundus_root = repo_root / "registry" / "fundus"
    assets = _load_fundus_documents(
        fundus_root / "assets",
        label="asset",
        validator=validate_asset,
    )
    families = _load_fundus_documents(
        fundus_root / "families",
        label="family",
        validator=validate_family,
    )
    briefs = _load_fundus_documents(
        fundus_root / "briefs",
        label="image brief",
        validator=validate_image_brief,
    )

    briefs_by_digest: dict[str, tuple[dict[str, Any], Path]] = {}
    for brief, brief_digest, path in briefs.values():
        duplicate = briefs_by_digest.get(brief_digest)
        if duplicate is not None:
            raise RegistryValidationError(
                f"{path}: duplicate canonical image brief digest {brief_digest}"
            )
        briefs_by_digest[brief_digest] = (brief, path)

        family = brief.get("family")
        if family is not None and family not in families:
            raise RegistryValidationError(
                f"{path}: unknown Fundus family {family!r}"
            )
        asset_entry = assets.get(brief["asset_id"])
        if asset_entry is not None and family is not None:
            asset = asset_entry[0]
            if asset.get("family") != family:
                raise RegistryValidationError(
                    f"{path}: image brief family {family!r} conflicts with "
                    f"asset family {asset.get('family')!r}"
                )

    for asset, _, asset_path in assets.values():
        for source in asset["sources"]:
            source_mode = source.get("source_mode", "unknown")
            if source_mode not in {"generated", "edited"}:
                continue

            brief_digest = source["image_brief_sha256"]
            binding = briefs_by_digest.get(brief_digest)
            if binding is None:
                raise RegistryValidationError(
                    f"{asset_path}: {source_mode} source role {source['role']!r} "
                    f"references missing committed image brief {brief_digest}"
                )
            brief, brief_path = binding

            if brief["asset_id"] != asset["id"]:
                raise RegistryValidationError(
                    f"{asset_path}: image brief {brief_path.name!r} binds asset "
                    f"{brief['asset_id']!r}, expected {asset['id']!r}"
                )
            if brief["source_role"] != source["role"]:
                raise RegistryValidationError(
                    f"{asset_path}: image brief {brief_path.name!r} source_role "
                    f"{brief['source_role']!r} conflicts with bound source role "
                    f"{source['role']!r}"
                )

            expected_operation = "generate" if source_mode == "generated" else "edit"
            if brief["operation"] != expected_operation:
                raise RegistryValidationError(
                    f"{asset_path}: image brief {brief_path.name!r} operation "
                    f"{brief['operation']!r} conflicts with source_mode {source_mode!r}"
                )

            brief_family = brief.get("family")
            if brief_family is not None and brief_family != asset.get("family"):
                raise RegistryValidationError(
                    f"{asset_path}: image brief {brief_path.name!r} family "
                    f"{brief_family!r} conflicts with asset family {asset.get('family')!r}"
                )

            asset_properties = asset.get("properties", {})
            for key, expected in brief["properties"].items():
                if asset_properties.get(key) is not expected:
                    raise RegistryValidationError(
                        f"{asset_path}: image brief {brief_path.name!r} property {key!r} "
                        f"is {expected!r}, asset declares {asset_properties.get(key)!r}"
                    )

    return len(briefs)


def validate_registry(repo_root: Path) -> dict[str, int]:
    """Validate schemas, registry items, uniqueness, and references."""
    schema_dir = repo_root / "schemas"
    registry_dir = repo_root / "registry"
    loaded: dict[str, list[dict[str, Any]]] = {}

    for spec in REGISTRIES:
        document = _load_yaml(registry_dir / spec.filename)
        _check_forbidden_keys(document, spec.filename)
        items = document.get(spec.key)
        if not isinstance(items, list):
            raise RegistryValidationError(f"{spec.filename}: {spec.key} must be a list")

        if spec.schema_filename:
            schema = json.loads((schema_dir / spec.schema_filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for index, item in enumerate(items):
                errors = sorted(validator.iter_errors(item), key=lambda error: list(error.path))
                if errors:
                    detail = "; ".join(error.message for error in errors)
                    raise RegistryValidationError(f"{spec.filename}[{index}]: {detail}")

        ids = [item.get("id") for item in items if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            raise RegistryValidationError(f"{spec.filename}: duplicate ids")
        if ids != sorted(ids):
            raise RegistryValidationError(f"{spec.filename}: items must be sorted by id")
        loaded[spec.key] = items

    def require_safe_relative_path(value: str, *, location: str) -> None:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RegistryValidationError(f"{location}: path must be repository-relative")

    source_ids = {item["id"] for item in loaded["sources"]}
    project_ids = {item["id"] for item in loaded["projects"]}
    surface_ids = {item["id"] for item in loaded["surfaces"]}
    view_ids = {item["id"] for item in loaded["views"]}
    policy_ids = {item["id"] for item in loaded["policies"]}

    def require_known(values: list[str], known: set[str], *, location: str, field: str) -> None:
        for value in values:
            if value not in known:
                raise RegistryValidationError(
                    f"{location}: unknown {field} value {value!r}"
                )

    for item in loaded["sources"]:
        require_known(
            item.get("depends_on", []),
            source_ids,
            location=f"sources.yaml:{item['id']}",
            field="depends_on",
        )
        if item["id"] in item.get("depends_on", []):
            raise RegistryValidationError(
                f"sources.yaml:{item['id']}: source cannot depend on itself"
            )

        if item["kind"] in {"generated-artifact", "document", "local-artifact"}:
            require_safe_relative_path(
                item["reference"], location=f"sources.yaml:{item['id']}.reference"
            )

    source_dependencies = {
        item["id"]: tuple(item.get("depends_on", [])) for item in loaded["sources"]
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_source(source_id: str) -> None:
        if source_id in visited:
            return
        if source_id in visiting:
            raise RegistryValidationError(
                f"sources.yaml: dependency cycle includes {source_id!r}"
            )
        visiting.add(source_id)
        for dependency in source_dependencies[source_id]:
            visit_source(dependency)
        visiting.remove(source_id)
        visited.add(source_id)

    for source_id in source_dependencies:
        visit_source(source_id)

    for item in loaded["projects"]:
        require_known(
            item.get("source_ids", []),
            source_ids,
            location=f"projects.yaml:{item['id']}",
            field="source_id",
        )

    aliases = [item.get("alias") for item in loaded["surfaces"] if item.get("alias")]
    if len(aliases) != len(set(aliases)):
        raise RegistryValidationError("surfaces.yaml: duplicate aliases")

    for item in loaded["surfaces"]:
        if item.get("output_path") is not None:
            require_safe_relative_path(
                item["output_path"], location=f"surfaces.yaml:{item['id']}.output_path"
            )

    for item in loaded["views"]:
        if item["project_id"] not in project_ids:
            raise RegistryValidationError(
                f"views.yaml: unknown project_id {item['project_id']!r} for {item['id']!r}"
            )
        require_known(
            item.get("source_ids", []),
            source_ids,
            location=f"views.yaml:{item['id']}",
            field="source_id",
        )
        if item.get("surface_ref") not in surface_ids:
            raise RegistryValidationError(
                f"views.yaml: unknown surface_ref {item.get('surface_ref')!r} for {item['id']!r}"
            )

    for item in loaded["regions"]:
        if item["view_id"] not in view_ids:
            raise RegistryValidationError(
                f"regions.yaml: unknown view_id {item['view_id']!r} for {item['id']!r}"
            )
        if item["surface_ref"] not in surface_ids:
            raise RegistryValidationError(
                f"regions.yaml: unknown surface_ref {item['surface_ref']!r} for {item['id']!r}"
            )
        if item["policy_id"] not in policy_ids:
            raise RegistryValidationError(
                f"regions.yaml: unknown policy_id {item['policy_id']!r} for {item['id']!r}"
            )

        policy = next(
            candidate for candidate in loaded["policies"] if candidate["id"] == item["policy_id"]
        )
        if item["management_mode"] == "read-only" and policy["mutation_mode"] != "read-only":
            raise RegistryValidationError(
                f"regions.yaml:{item['id']}: read-only region requires read-only policy"
            )
        if item["management_mode"] != "read-only" and policy["mutation_mode"] == "read-only":
            raise RegistryValidationError(
                f"regions.yaml:{item['id']}: mutable region cannot use read-only policy"
            )

    for item in loaded["publications"]:
        if item.get("artifact_path") is not None:
            require_safe_relative_path(
                item["artifact_path"],
                location=f"publications.yaml:{item['id']}.artifact_path",
            )
        if item["view_id"] not in view_ids:
            raise RegistryValidationError(
                f"publications.yaml: unknown view_id {item['view_id']!r} for {item['id']!r}"
            )

    _validate_fundus_briefs(repo_root)
    return {key: len(items) for key, items in loaded.items()}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    counts = validate_registry(repo_root)
    summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"registry valid: {summary}")


if __name__ == "__main__":
    main()
