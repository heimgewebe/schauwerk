"""SW-017 deterministic operation, backup and recovery contracts."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
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
_MAX_BACKUP_PATH_DEPTH = 64
_BACKUP_READ_CHUNK_BYTES = 1024 * 1024

_FileIdentity = tuple[int, int]
_DirectoryChain = list[tuple[int, str | None, _FileIdentity]]


def _file_identity(value: os.stat_result) -> _FileIdentity:
    return (value.st_dev, value.st_ino)


def _directory_open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None:
        raise DurableError("descriptor-relative no-follow directory access is unavailable")
    return os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)


def _verify_directory_chain(chain: _DirectoryChain, *, label: str) -> None:
    for index, (descriptor, name, identity) in enumerate(chain):
        try:
            opened = os.fstat(descriptor)
        except OSError as exc:
            raise DurableError(f"{label} directory identity became unavailable") from exc
        if not stat.S_ISDIR(opened.st_mode) or _file_identity(opened) != identity:
            raise DurableError(f"{label} directory identity changed")
        if index == 0:
            continue
        assert name is not None
        parent_descriptor = chain[index - 1][0]
        try:
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except OSError as exc:
            raise DurableError(f"{label} directory path identity changed") from exc
        if not stat.S_ISDIR(current.st_mode) or _file_identity(current) != identity:
            raise DurableError(f"{label} directory path identity changed")


@contextmanager
def _open_safe_root(root: Path, *, label: str) -> Iterator[tuple[Path, _DirectoryChain]]:
    base = root.expanduser().absolute()
    parts = base.parts
    if not base.is_absolute() or not parts or parts[0] != os.sep:
        raise DurableError(f"{label} must be an absolute directory")
    if len(parts) - 1 > _MAX_BACKUP_PATH_DEPTH:
        raise DurableError(f"{label} path exceeds the depth limit")
    flags = _directory_open_flags()
    chain: _DirectoryChain = []
    try:
        descriptor = os.open(os.sep, flags)
        root_stat = os.fstat(descriptor)
        chain.append((descriptor, None, _file_identity(root_stat)))
        for part in parts[1:]:
            if part in {"", ".", ".."}:
                raise DurableError(f"{label} path is not normalized")
            try:
                descriptor = os.open(part, flags, dir_fd=chain[-1][0])
            except OSError as exc:
                raise DurableError(
                    f"{label} must be a directory with no symlinks in its path"
                ) from exc
            opened = os.fstat(descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(descriptor)
                raise DurableError(f"{label} must be a directory")
            chain.append((descriptor, part, _file_identity(opened)))
        _verify_directory_chain(chain, label=label)
        yield base, chain
    finally:
        for descriptor, _, _ in reversed(chain):
            os.close(descriptor)


def _verify_relative_directories(
    root_chain: _DirectoryChain,
    relative_chain: _DirectoryChain,
    *,
    label: str,
) -> None:
    _verify_directory_chain(root_chain, label=label)
    if relative_chain:
        _verify_directory_chain([root_chain[-1], *relative_chain], label=label)


def _hash_regular_file(
    root_chain: _DirectoryChain,
    relative: str,
    *,
    label: str,
    missing_ok: bool,
) -> tuple[int, str] | None:
    parts = Path(relative).parts
    if not parts or len(parts) > _MAX_BACKUP_PATH_DEPTH:
        raise DurableError(f"{label} path exceeds the depth limit")
    directory_flags = _directory_open_flags()
    nofollow = getattr(os, "O_NOFOLLOW", None)
    assert nofollow is not None
    file_flags = (
        os.O_RDONLY
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    relative_chain: _DirectoryChain = []
    file_descriptor: int | None = None
    try:
        parent_descriptor = root_chain[-1][0]
        for part in parts[:-1]:
            try:
                descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise DurableError(
                    f"{label} must be a regular file with no symlinks in its path"
                ) from None
            except OSError as exc:
                raise DurableError(
                    f"{label} must be a regular file with no symlinks in its path"
                ) from exc
            opened = os.fstat(descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(descriptor)
                raise DurableError(f"{label} path contains a non-directory component")
            relative_chain.append((descriptor, part, _file_identity(opened)))
            parent_descriptor = descriptor

        try:
            file_descriptor = os.open(parts[-1], file_flags, dir_fd=parent_descriptor)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise DurableError(
                f"{label} must be a regular file with no symlinks in its path"
            ) from None
        except OSError as exc:
            raise DurableError(
                f"{label} must be a regular file with no symlinks in its path"
            ) from exc

        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise DurableError(f"{label} must be a regular file")
        if before.st_size > _MAX_BACKUP_FILE_BYTES:
            raise DurableError(f"{label} exceeds the size limit")

        digest = hashlib.sha256()
        total = 0
        while True:
            try:
                chunk = os.read(
                    file_descriptor,
                    min(_BACKUP_READ_CHUNK_BYTES, _MAX_BACKUP_FILE_BYTES + 1 - total),
                )
            except InterruptedError:
                continue
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BACKUP_FILE_BYTES:
                raise DurableError(f"{label} exceeds the size limit")
            digest.update(chunk)

        after = os.fstat(file_descriptor)
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if stable_before != stable_after or total != after.st_size:
            raise DurableError(f"{label} changed while it was being read")

        _verify_relative_directories(root_chain, relative_chain, label=label)
        try:
            current = os.stat(parts[-1], dir_fd=parent_descriptor, follow_symlinks=False)
        except OSError as exc:
            raise DurableError(f"{label} path identity changed while it was being read") from exc
        if not stat.S_ISREG(current.st_mode) or _file_identity(current) != _file_identity(before):
            raise DurableError(f"{label} path identity changed while it was being read")
        return total, digest.hexdigest()
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor, _, _ in reversed(relative_chain):
            os.close(descriptor)


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
    entries: list[dict[str, Any]] = []
    with _open_safe_root(root, label="backup root") as (base, root_chain):
        for declared in _declared_entries(declaration):
            hashed = _hash_regular_file(
                root_chain,
                declared["path"],
                label=f"backup entry {declared['path']}",
                missing_ok=False,
            )
            assert hashed is not None
            byte_count, sha256 = hashed
            entries.append({**declared, "bytes": byte_count, "sha256": sha256})
        _verify_directory_chain(root_chain, label="backup root")
        root_identity_digest = stable_digest(str(base))
    value = {
        "schema_version": BACKUP_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "root_identity_digest": root_identity_digest,
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
    checks: list[dict[str, Any]] = []
    with _open_safe_root(staged_root, label="staged restore root") as (_, root_chain):
        for entry in manifest["entries"]:
            hashed = _hash_regular_file(
                root_chain,
                entry["path"],
                label=f"staged restore entry {entry['path']}",
                missing_ok=True,
            )
            actual_bytes, actual_digest = hashed if hashed is not None else (None, None)
            checks.append(
                {
                    "path": entry["path"],
                    "ok": actual_bytes == entry["bytes"]
                    and actual_digest == entry["sha256"],
                    "expected_sha256": entry["sha256"],
                    "actual_sha256": actual_digest,
                    "expected_bytes": entry["bytes"],
                    "actual_bytes": actual_bytes,
                }
            )
        _verify_directory_chain(root_chain, label="staged restore root")
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
