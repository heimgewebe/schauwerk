"""Validation for the Git-versioned Schauwerk registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


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
                raise RegistryValidationError(f"{location}: unknown {field} value {value!r}")

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
            raise RegistryValidationError(f"sources.yaml: dependency cycle includes {source_id!r}")
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

    return {key: len(items) for key, items in loaded.items()}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    counts = validate_registry(repo_root)
    summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"registry valid: {summary}")


if __name__ == "__main__":
    main()
