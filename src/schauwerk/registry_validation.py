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
    RegistrySpec("projects.yaml", "projects", "project.v1.schema.json"),
    RegistrySpec("views.yaml", "views", "view.v1.schema.json"),
    RegistrySpec("surfaces.yaml", "surfaces", None),
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
        loaded[spec.key] = items

    project_ids = {item["id"] for item in loaded["projects"]}
    view_ids = {item["id"] for item in loaded["views"]}
    for item in loaded["views"]:
        if item["project_id"] not in project_ids:
            raise RegistryValidationError(
                f"views.yaml: unknown project_id {item['project_id']!r} for {item['id']!r}"
            )
    for item in loaded["publications"]:
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
