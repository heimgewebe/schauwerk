"""Shared typed region contracts and receipt helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

_ALLOWED_MODES = {
    "manual",
    "cooperative",
    "suggest-only",
    "approval-required",
    "managed",
    "read-only",
    "public-copy",
}
_ALLOWED_VISIBILITIES = {"private", "shared", "classroom", "public", "archived"}
_ALLOWED_OPERATIONS = {"render-update", "replace-region"}
_ALLOWED_FIXTURE_ACTIONS = {"create-item", "delete-item", "replace-region", "update-item"}
_FIXTURE_OPERATION_KEYS = {
    "action",
    "local_ref",
    "operation_id",
    "payload_digest",
    "region_id",
}
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,80}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{16,128}$")


@dataclass(frozen=True)
class RegionDeclaration:
    view_id: str
    region_id: str
    mode: str
    surface_alias: str
    expected_snapshot_digest: str
    expected_source_digest: str | None = None
    owner: str = "schauwerk"
    visibility: str = "private"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"region.{key} must be a non-empty string")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"region.{key} must be a non-empty string when present")
    return value.strip()


def _validate_safe_id(value: str, *, label: str) -> str:
    if not _SAFE_ID.match(value):
        raise ValueError(f"region.{label} has an unsafe identifier shape")
    return value


def _validate_digest(value: str, *, label: str) -> str:
    if not _HEX_DIGEST.match(value):
        raise ValueError(f"region.{label} must be a 16-128 char lowercase hex digest")
    return value


def parse_region_declaration(data: dict[str, Any]) -> RegionDeclaration:
    source = data.get("region", data)
    if not isinstance(source, dict):
        raise ValueError("operator input must contain a region object")

    view_id = _validate_safe_id(_required_text(source, "view_id"), label="view_id")
    region_id = _validate_safe_id(_required_text(source, "region_id"), label="region_id")
    surface_alias = _validate_safe_id(
        _required_text(source, "surface_alias"), label="surface_alias"
    )
    mode = _required_text(source, "mode")
    if mode not in _ALLOWED_MODES:
        raise ValueError(f"region.mode must be one of {sorted(_ALLOWED_MODES)}")
    visibility = _optional_text(source, "visibility") or "private"
    if visibility not in _ALLOWED_VISIBILITIES:
        raise ValueError(f"region.visibility must be one of {sorted(_ALLOWED_VISIBILITIES)}")
    expected_snapshot_digest = _validate_digest(
        _required_text(source, "expected_snapshot_digest"),
        label="expected_snapshot_digest",
    )
    expected_source_digest = _optional_text(source, "expected_source_digest")
    if expected_source_digest is not None:
        expected_source_digest = _validate_digest(
            expected_source_digest, label="expected_source_digest"
        )
    owner = _validate_safe_id(_optional_text(source, "owner") or "schauwerk", label="owner")
    return RegionDeclaration(
        view_id=view_id,
        region_id=region_id,
        mode=mode,
        surface_alias=surface_alias,
        expected_snapshot_digest=expected_snapshot_digest,
        expected_source_digest=expected_source_digest,
        owner=owner,
        visibility=visibility,
    )


def load_region_declaration(path: Path) -> RegionDeclaration:
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("operator input must contain an object")
    return parse_region_declaration(raw)




def _load_json_or_yaml(path: Path, *, label: str) -> Any:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError(f"{label} path is unsafe")
    try:
        text = candidate.read_text(encoding="utf-8")
        return json.loads(text) if candidate.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{label} receipt is unreadable") from exc
