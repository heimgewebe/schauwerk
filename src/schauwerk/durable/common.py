"""Shared deterministic, fail-closed helpers for SW-014 through SW-017."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON_BYTES = 4 * 1024 * 1024
_VISIBILITIES = ("private", "shared", "classroom", "public", "archived")


class DurableError(ValueError):
    """A durable-foundation input violated a deterministic safety contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_digest(value: Any, *, digest_field: str | None = None) -> str:
    if digest_field is not None:
        if not isinstance(value, Mapping):
            raise DurableError("digest-bound value must be an object")
        value = {key: item for key, item in value.items() if key != digest_field}
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def bind_digest(value: dict[str, Any], digest_field: str) -> dict[str, Any]:
    value[digest_field] = stable_digest(value, digest_field=digest_field)
    return value


def require_bound_digest(value: Mapping[str, Any], digest_field: str, *, label: str) -> str:
    declared = safe_digest(value.get(digest_field), label=f"{label} {digest_field}")
    if declared != stable_digest(value, digest_field=digest_field):
        raise DurableError(f"{label} {digest_field} mismatch")
    return declared


def _reject_symlink_chain(path: Path, *, include_leaf: bool = True) -> None:
    candidate = path.expanduser().absolute()
    checks = [candidate, *candidate.parents] if include_leaf else list(candidate.parents)
    for current in checks:
        if current.exists() and current.is_symlink():
            raise DurableError(f"unsafe symlink path: {path}")


def read_json(path: Path, *, label: str) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    _reject_symlink_chain(candidate)
    try:
        stat = candidate.stat()
    except FileNotFoundError as exc:
        raise DurableError(f"{label} does not exist") from exc
    if not candidate.is_file():
        raise DurableError(f"{label} must be a regular non-symlink file")
    if stat.st_size > _MAX_JSON_BYTES:
        raise DurableError(f"{label} exceeds the size limit")
    try:
        raw = candidate.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DurableError(f"{label} must contain an object")
    return value


def write_json(path: Path, value: Mapping[str, Any], *, mode: int = 0o600) -> Path:
    destination = path.expanduser().absolute()
    _reject_symlink_chain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _reject_symlink_chain(destination, include_leaf=False)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, destination)
        destination.chmod(mode)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return destination


def safe_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DurableError(f"{label} is invalid")
    return value


def safe_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DurableError(f"{label} is invalid")
    return value


def safe_visibility(value: Any, *, label: str) -> str:
    if value not in _VISIBILITIES:
        raise DurableError(f"{label} is invalid")
    return str(value)


def visibility_allows(requested: str, item: str) -> bool:
    """Return whether a request scope may see an item.

    Private is the broadest authenticated scope. Public is the narrowest. Archived
    material is intentionally visible only to private requests.
    """

    safe_visibility(requested, label="requested visibility")
    safe_visibility(item, label="item visibility")
    if item == "archived":
        return requested == "private"
    allowed = {
        "private": {"private", "shared", "classroom", "public"},
        "shared": {"shared", "classroom", "public"},
        "classroom": {"classroom", "public"},
        "public": {"public"},
        "archived": {"archived"},
    }
    return item in allowed[requested]


def bounded_text(value: Any, *, label: str, maximum: int = 1000, allow_empty: bool = False) -> str:
    minimum = 0 if allow_empty else 1
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise DurableError(f"{label} is invalid")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise DurableError(f"{label} contains control characters")
    return value


def parse_timestamp(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DurableError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DurableError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise DurableError(f"{label} must be UTC")
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_value(value: str) -> datetime:
    parsed = parse_timestamp(value, label="timestamp")
    assert parsed is not None
    return datetime.fromisoformat(parsed[:-1] + "+00:00")


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_relative_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise DurableError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DurableError(f"{label} must be a normalized relative path")
    return path.as_posix()


def safe_scalar(value: Any, *, label: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise DurableError(f"{label} is invalid")
        return value
    if isinstance(value, str):
        return bounded_text(value, label=label, maximum=4000, allow_empty=True)
    raise DurableError(f"{label} must be a JSON scalar")
