"""Canonical Miro snapshot model."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

_VOLATILE = {
    "created_at",
    "createdat",
    "created_by",
    "createdby",
    "modified_at",
    "modifiedat",
    "modified_by",
    "modifiedby",
    "updated_at",
    "updatedat",
    "last_modified",
    "lastmodified",
    "tracking",
}
_URL_KEYS = {"miro_url", "url", "board_url", "share_url", "href"}
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")
_IDENTITY_KEYS = {"user_id", "team_id", "workspace_id", "org_id"}


@dataclass(frozen=True)
class SnapshotRead:
    items: tuple[dict[str, Any], ...]
    comments: tuple[dict[str, Any], ...]
    item_pages: int
    comment_pages: int

    def content(self, alias: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "board_alias": alias,
            "items": list(self.items),
            "comments": list(self.comments),
        }


@dataclass(frozen=True)
class SnapshotReceipt:
    board_alias: str
    content_digest: str
    item_count: int
    comment_count: int
    item_pages: int
    comment_pages: int
    repeatability_verified: bool
    output_path: str
    sanitized_references: bool = True
    mutation_attempted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_reference(value: Any) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def normalize_key(key: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", key).replace("-", "_").lower()


def normalize_value(value: Any, key: str | None = None) -> Any:
    name = normalize_key(key) if key else None
    if name in _VOLATILE or name in _IDENTITY_KEYS:
        return None
    if name in _URL_KEYS or (name and name.endswith("_url")):
        return {"reference_digest": stable_reference(value)} if value else None
    if name == "id" or (name and name.endswith("_id")):
        return stable_reference(value) if value is not None else None
    if isinstance(value, Mapping):
        result = {}
        for raw_key, raw_value in sorted(value.items(), key=lambda pair: str(pair[0])):
            child_key = str(raw_key)
            child_name = normalize_key(child_key)
            if child_name in _VOLATILE or child_name in _IDENTITY_KEYS:
                continue
            child = normalize_value(raw_value, child_key)
            if child is not None:
                result[child_key] = child
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_value(item) for item in value]
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 8)
    return value


def normalize_item(record: Mapping[str, Any]) -> dict[str, Any]:
    raw_id = record.get("id")
    normalized = {
        "ref": stable_reference(raw_id if raw_id is not None else canonical_json(record)),
        "type": str(record.get("type", "unknown")),
    }
    for key in ("parent", "data", "geometry", "position", "style"):
        if record.get(key) is not None:
            normalized[key] = normalize_value(record[key], key)
    return normalized


def normalize_comment(record: Mapping[str, Any]) -> dict[str, Any]:
    value = normalize_value(record)
    assert isinstance(value, dict)
    return value


def content_digest(content: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(content).encode()).hexdigest()


def unique_sorted(records: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    unique = {canonical_json(record): record for record in records}
    return tuple(unique[key] for key in sorted(unique))
