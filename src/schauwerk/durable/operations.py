"""SW-017 deterministic operation, backup and recovery contracts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .common import (
    DurableError,
    bind_digest,
    bounded_text,
    parse_timestamp,
    read_json,
    require_bound_digest,
    safe_digest,
    safe_identifier,
    safe_relative_path,
    stable_digest,
)

PROFILE_SCHEMA = "schauwerk-operation-profiles.v1"
HEALTH_INPUT_SCHEMA = "schauwerk-health-input.v1"
HEALTH_SCHEMA = "schauwerk-health-receipt.v1"
BACKUP_DECLARATION_SCHEMA = "schauwerk-backup-declaration.v1"
BACKUP_SCHEMA = "schauwerk-backup-manifest.v1"
RESTORE_SCHEMA = "schauwerk-restore-verification.v1"
ROTATION_INPUT_SCHEMA = "schauwerk-oauth-rotation-input.v1"
ROTATION_SCHEMA = "schauwerk-oauth-rotation-plan.v1"
DRILL_INPUT_SCHEMA = "schauwerk-kill-switch-drill-input.v1"
DRILL_SCHEMA = "schauwerk-kill-switch-drill.v1"
_SECRET = re.compile(
    r"(^|[._/-])(secret|token|credential|oauth-state|private-key|\.env|key)([._/-]|$)", re.I
)
_RETENTION = {"short", "standard", "long", "immutable"}
_MAX_BACKUP_FILE_BYTES = 64 * 1024 * 1024


def operation_profiles() -> dict[str, Any]:
    profiles = [
        {
            "id": "maintenance",
            "purpose": "compile source-change proposals without provider effects",
            "network": "none",
            "mutation": "proposal-only",
            "health_path": "local-contract",
        },
        {
            "id": "overview",
            "purpose": "serve read-only local operational views",
            "network": "loopback-only",
            "mutation": "none",
            "health_path": "local-and-optional-provider-probe",
        },
        {
            "id": "publication",
            "purpose": "serve verified immutable local publications",
            "network": "loopback-only",
            "mutation": "local-store-only",
            "health_path": "manifest-and-object-verification",
        },
        {
            "id": "regie",
            "purpose": "review proposals and explicitly dispatch approved effects",
            "network": "loopback-and-explicit-provider",
            "mutation": "review-gated",
            "health_path": "local-session-and-provider-readiness",
        },
    ]
    profiles.sort(key=lambda item: item["id"])
    value = {
        "schema_version": PROFILE_SCHEMA,
        "installation_performed": False,
        "profiles": profiles,
        "profile_digest": "",
    }
    return bind_digest(value, "profile_digest")


def compile_health_receipt(input_value: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    if not isinstance(input_value, Mapping) or set(input_value) != {"schema_version", "components"}:
        raise DurableError("health input fields are invalid")
    if input_value.get("schema_version") != HEALTH_INPUT_SCHEMA:
        raise DurableError("health input schema is unsupported")
    components = input_value.get("components")
    if not isinstance(components, list) or not components:
        raise DurableError("health input requires components")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(components):
        if not isinstance(item, Mapping) or set(item) != {
            "id",
            "required",
            "state",
            "evidence_sha256",
            "detail",
        }:
            raise DurableError(f"components[{index}] fields are invalid")
        identifier = safe_identifier(item.get("id"), label=f"components[{index}].id")
        if identifier in seen:
            raise DurableError("health component ids are duplicated")
        seen.add(identifier)
        if not isinstance(item.get("required"), bool):
            raise DurableError("health component required flag is invalid")
        state = item.get("state")
        if state not in {"healthy", "degraded", "failed", "disabled"}:
            raise DurableError("health component state is invalid")
        normalized.append(
            {
                "id": identifier,
                "required": item["required"],
                "state": state,
                "evidence_sha256": safe_digest(
                    item.get("evidence_sha256"), label="component evidence_sha256"
                ),
                "detail": bounded_text(item.get("detail"), label="component detail"),
            }
        )
    normalized.sort(key=lambda item: item["id"])
    required_failed = [
        item["id"] for item in normalized if item["required"] and item["state"] == "failed"
    ]
    required_degraded = [
        item["id"] for item in normalized if item["required"] and item["state"] == "degraded"
    ]
    any_nonhealthy = any(item["state"] != "healthy" for item in normalized)
    state = "failed" if required_failed else "degraded" if any_nonhealthy else "ready"
    value = {
        "schema_version": HEALTH_SCHEMA,
        "observed_at": parse_timestamp(observed_at, label="observed_at"),
        "state": state,
        "ready": state != "failed",
        "components": normalized,
        "required_failed": required_failed,
        "required_degraded": required_degraded,
        "mutation_attempted": False,
        "health_digest": "",
    }
    return bind_digest(value, "health_digest")


def _declared_entries(value: Mapping[str, Any]) -> list[dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"schema_version", "entries"}:
        raise DurableError("backup declaration fields are invalid")
    if value.get("schema_version") != BACKUP_DECLARATION_SCHEMA:
        raise DurableError("backup declaration schema is unsupported")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise DurableError("backup declaration requires entries")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping) or set(item) != {"path", "retention", "class"}:
            raise DurableError(f"backup entries[{index}] fields are invalid")
        relative = safe_relative_path(item.get("path"), label=f"backup entries[{index}].path")
        if _SECRET.search(relative):
            raise DurableError(f"backup path is secret-like and forbidden: {relative}")
        if relative in seen:
            raise DurableError("backup paths are duplicated")
        seen.add(relative)
        retention = item.get("retention")
        if retention not in _RETENTION:
            raise DurableError("backup retention is invalid")
        item_class = safe_identifier(item.get("class"), label="backup entry class")
        normalized.append({"path": relative, "retention": retention, "class": item_class})
    return sorted(normalized, key=lambda item: item["path"])


def compile_backup_manifest(
    declaration: Mapping[str, Any], *, root: Path, created_at: str
) -> dict[str, Any]:
    base = root.expanduser().absolute()
    if base.is_symlink() or not base.is_dir():
        raise DurableError("backup root must be a non-symlink directory")
    entries: list[dict[str, Any]] = []
    for declared in _declared_entries(declaration):
        candidate = base / declared["path"]
        if candidate.is_symlink() or not candidate.is_file():
            raise DurableError(f"backup entry must be a regular file: {declared['path']}")
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(base.resolve(strict=True))
        except ValueError as exc:
            raise DurableError("backup entry escapes the root") from exc
        size = resolved.stat().st_size
        if size > _MAX_BACKUP_FILE_BYTES:
            raise DurableError(f"backup entry exceeds size limit: {declared['path']}")
        payload = resolved.read_bytes()
        entries.append(
            {
                **declared,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    value = {
        "schema_version": BACKUP_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "root_identity_digest": stable_digest(str(base)),
        "entries": entries,
        "secret_material_included": False,
        "copy_performed": False,
        "mutation_attempted": False,
        "manifest_digest": "",
    }
    return bind_digest(value, "manifest_digest")


def validate_backup_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "created_at",
        "root_identity_digest",
        "entries",
        "secret_material_included",
        "copy_performed",
        "mutation_attempted",
        "manifest_digest",
    }:
        raise DurableError("backup manifest fields are invalid")
    if value.get("schema_version") != BACKUP_SCHEMA:
        raise DurableError("backup manifest schema is unsupported")
    parse_timestamp(value.get("created_at"), label="created_at")
    safe_digest(value.get("root_identity_digest"), label="root_identity_digest")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise DurableError("backup manifest entries are invalid")
    paths = [item.get("path") for item in entries if isinstance(item, Mapping)]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise DurableError("backup manifest entries are not canonical")
    for item in entries:
        if not isinstance(item, Mapping) or set(item) != {
            "path",
            "retention",
            "class",
            "bytes",
            "sha256",
        }:
            raise DurableError("backup manifest entry fields are invalid")
        safe_relative_path(item.get("path"), label="backup manifest path")
        if _SECRET.search(str(item["path"])):
            raise DurableError("backup manifest contains a secret-like path")
        if item.get("retention") not in _RETENTION:
            raise DurableError("backup manifest retention is invalid")
        safe_identifier(item.get("class"), label="backup manifest class")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            raise DurableError("backup manifest byte count is invalid")
        safe_digest(item.get("sha256"), label="backup manifest sha256")
    if (
        value.get("secret_material_included") is not False
        or value.get("copy_performed") is not False
    ):
        raise DurableError("backup manifest effect boundary is invalid")
    if value.get("mutation_attempted") is not False:
        raise DurableError("backup manifest must not report mutation")
    require_bound_digest(value, "manifest_digest", label="backup manifest")
    return dict(value)


def verify_staged_restore(
    manifest_value: Mapping[str, Any], *, staged_root: Path, verified_at: str
) -> dict[str, Any]:
    manifest = validate_backup_manifest(manifest_value)
    root = staged_root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise DurableError("staged restore root must be a non-symlink directory")
    checks: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        candidate = root / entry["path"]
        ok = False
        actual_digest: str | None = None
        actual_bytes: int | None = None
        if candidate.is_symlink():
            raise DurableError(f"staged restore entry is a symlink: {entry['path']}")
        if candidate.is_file():
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(root.resolve(strict=True))
            except ValueError as exc:
                raise DurableError("staged restore entry escapes the root") from exc
            size = resolved.stat().st_size
            if size > _MAX_BACKUP_FILE_BYTES:
                raise DurableError(f"staged restore entry exceeds size limit: {entry['path']}")
            payload = resolved.read_bytes()
            actual_bytes = len(payload)
            actual_digest = hashlib.sha256(payload).hexdigest()
            ok = actual_bytes == entry["bytes"] and actual_digest == entry["sha256"]
        checks.append(
            {
                "path": entry["path"],
                "ok": ok,
                "expected_sha256": entry["sha256"],
                "actual_sha256": actual_digest,
                "expected_bytes": entry["bytes"],
                "actual_bytes": actual_bytes,
            }
        )
    value = {
        "schema_version": RESTORE_SCHEMA,
        "verified_at": parse_timestamp(verified_at, label="verified_at"),
        "manifest_digest": manifest["manifest_digest"],
        "checks": checks,
        "verified": all(item["ok"] for item in checks),
        "live_overwrite_performed": False,
        "mutation_attempted": False,
        "verification_digest": "",
    }
    return bind_digest(value, "verification_digest")


def compile_oauth_rotation_plan(
    input_value: Mapping[str, Any], *, created_at: str
) -> dict[str, Any]:
    expected = {
        "schema_version",
        "identity_digest",
        "target_team",
        "target_space",
        "board_aliases",
        "rollback_reference",
    }
    if not isinstance(input_value, Mapping) or set(input_value) != expected:
        raise DurableError("OAuth rotation input fields are invalid")
    if input_value.get("schema_version") != ROTATION_INPUT_SCHEMA:
        raise DurableError("OAuth rotation input schema is unsupported")
    aliases = input_value.get("board_aliases")
    if not isinstance(aliases, list) or aliases != sorted(set(aliases)):
        raise DurableError("OAuth rotation board aliases are invalid")
    aliases = [safe_identifier(item, label="OAuth rotation board alias") for item in aliases]
    value = {
        "schema_version": ROTATION_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "identity_digest": safe_digest(input_value.get("identity_digest"), label="identity_digest"),
        "target_team": bounded_text(input_value.get("target_team"), label="target_team"),
        "target_space": bounded_text(input_value.get("target_space"), label="target_space"),
        "board_aliases": aliases,
        "rollback_reference": bounded_text(
            input_value.get("rollback_reference"), label="rollback_reference"
        ),
        "steps": [
            "snapshot current identity and allowlist metadata",
            "authorize replacement identity interactively",
            "verify team and space assignment out of band",
            "prove exact board searches and read-only snapshots",
            "retain rollback metadata until postflight acceptance",
        ],
        "token_accessed": False,
        "rotation_performed": False,
        "external_effect_required": True,
        "plan_digest": "",
    }
    return bind_digest(value, "plan_digest")


def compile_kill_switch_drill(input_value: Mapping[str, Any], *, created_at: str) -> dict[str, Any]:
    expected = {
        "schema_version",
        "switch_before",
        "blocked_apply_proved",
        "switch_after",
        "before_evidence",
        "blocked_evidence",
        "after_evidence",
    }
    if not isinstance(input_value, Mapping) or set(input_value) != expected:
        raise DurableError("kill-switch drill input fields are invalid")
    if input_value.get("schema_version") != DRILL_INPUT_SCHEMA:
        raise DurableError("kill-switch drill input schema is unsupported")
    for key in ("switch_before", "blocked_apply_proved", "switch_after"):
        if not isinstance(input_value.get(key), bool):
            raise DurableError(f"{key} must be boolean")
    evidence = {
        key: safe_digest(input_value.get(key), label=key)
        for key in ("before_evidence", "blocked_evidence", "after_evidence")
    }
    passed = (
        input_value["switch_before"] is False
        and input_value["blocked_apply_proved"] is True
        and input_value["switch_after"] is False
    )
    value = {
        "schema_version": DRILL_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "passed": passed,
        "evidence": evidence,
        "live_switch_changed_by_compiler": False,
        "mutation_attempted": False,
        "drill_digest": "",
    }
    return bind_digest(value, "drill_digest")


def load_backup_manifest(path: Path) -> dict[str, Any]:
    return validate_backup_manifest(read_json(path, label="backup manifest"))
