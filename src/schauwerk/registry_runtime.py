"""Deterministic loading and inspection for the Git-versioned registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .registry_validation import REGISTRIES, RegistryValidationError, validate_registry


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_registry(repo_root: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    root = repo_root or repository_root()
    validate_registry(root)
    loaded: dict[str, list[dict[str, Any]]] = {}
    for spec in REGISTRIES:
        raw = yaml.safe_load((root / "registry" / spec.filename).read_text(encoding="utf-8"))
        items = raw[spec.key]
        loaded[spec.key] = items
    return loaded


def registry_digest(registry: dict[str, list[dict[str, Any]]]) -> str:
    encoded = json.dumps(registry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def registry_status(repo_root: Path | None = None) -> dict[str, Any]:
    registry = load_registry(repo_root)
    return {
        "schema_version": "schauwerk-registry-status.v1",
        "counts": {key: len(value) for key, value in registry.items()},
        "ids": {key: [item["id"] for item in value] for key, value in registry.items()},
        "registry_digest": registry_digest(registry),
        "valid": True,
    }


def registry_show(
    kind: str, identifier: str | None = None, repo_root: Path | None = None
) -> dict[str, Any]:
    registry = load_registry(repo_root)
    if kind not in registry:
        raise RegistryValidationError(f"unknown registry kind: {kind}")
    items = registry[kind]
    if identifier is None:
        return {"kind": kind, "count": len(items), "items": items}
    for item in items:
        if item["id"] == identifier:
            return {"kind": kind, "item": item}
    raise RegistryValidationError(f"unknown {kind} id: {identifier}")
