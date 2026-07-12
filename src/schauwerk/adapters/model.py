"""SW-014 provider-neutral source adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

ADAPTER_OBSERVATION_SCHEMA = "adapter-observation.v1"
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


class AdapterError(ValueError):
    """Adapter input or state violated a fail-closed contract."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_mapping(value: Mapping[str, Any], digest_field: str) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            _canonical_bytes({key: item for key, item in value.items() if key != digest_field})
        ).hexdigest()
    )


def _safe_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise AdapterError(f"{label} is invalid")
    return value


def parse_timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AdapterError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AdapterError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise AdapterError(f"{label} must be UTC")
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterError("observation must contain an object")
    expected = {
        "schema_version",
        "adapter_id",
        "observed_at",
        "stale_after_seconds",
        "status",
        "error_code",
        "payload_digest",
        "payload",
    }
    if set(value) != expected:
        raise AdapterError("observation fields are invalid")
    if value.get("schema_version") != ADAPTER_OBSERVATION_SCHEMA:
        raise AdapterError("observation schema is unsupported")

    adapter_id = _safe_identifier(value.get("adapter_id"), label="adapter_id")
    observed_at = parse_timestamp(value.get("observed_at"), label="observed_at")

    stale_after = value.get("stale_after_seconds")
    if not isinstance(stale_after, int) or stale_after < 1:
        raise AdapterError("stale_after_seconds is invalid")

    status = value.get("status")
    if status not in ("healthy", "stale", "partial", "failed"):
        raise AdapterError("status is invalid")

    error_code = value.get("error_code")
    if error_code is not None:
        if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
            raise AdapterError("error_code is invalid")
    elif status in ("partial", "failed"):
        raise AdapterError(f"error_code is required for status {status}")

    payload = value.get("payload")
    if payload is not None and not isinstance(payload, Mapping):
        raise AdapterError("payload must be an object or null")

    declared_digest = value.get("payload_digest")
    if not isinstance(declared_digest, str) or not _SHA256.fullmatch(declared_digest):
        raise AdapterError("payload_digest is invalid")

    actual_digest = (
        "sha256:"
        + hashlib.sha256(b"null" if payload is None else _canonical_bytes(payload)).hexdigest()
    )

    if declared_digest != actual_digest:
        raise AdapterError("payload_digest mismatch")

    return {
        "schema_version": ADAPTER_OBSERVATION_SCHEMA,
        "adapter_id": adapter_id,
        "observed_at": observed_at,
        "stale_after_seconds": stale_after,
        "status": status,
        "error_code": error_code,
        "payload_digest": actual_digest,
        "payload": payload,
    }


def create_observation(
    adapter_id: str,
    observed_at: str,
    stale_after_seconds: int,
    status: str,
    error_code: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observation = {
        "schema_version": ADAPTER_OBSERVATION_SCHEMA,
        "adapter_id": adapter_id,
        "observed_at": observed_at,
        "stale_after_seconds": stale_after_seconds,
        "status": status,
        "error_code": error_code,
        "payload": payload,
        "payload_digest": "sha256:"
        + hashlib.sha256(b"null" if payload is None else _canonical_bytes(payload)).hexdigest(),
    }
    return validate_observation(observation)
