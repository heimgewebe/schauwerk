"""Provider-neutral restore evidence for the current Fundus data-root inventory."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .errors import FundusError
from .model import canonical_json, digest_bytes, digest_json
from .pathio import (
    _open_child_directory,
    _read_regular_at,
    normalized_absolute,
    open_directory_chain,
    read_regular_bytes,
)

DURABILITY_EVIDENCE_SCHEMA = "schauwerk-fundus-durability-evidence.v1"
DURABILITY_EVIDENCE_SCHEMA_FILE = "fundus-durability-evidence.v1.schema.json"
INVENTORY_SCHEMA = "schauwerk-fundus-inventory.v1"
VERIFICATION_MODE = "staged_restore_exact_snapshot"
MAX_EVIDENCE_BYTES = 64 * 1024
MAX_INVENTORY_FILES = 1_000_000


def _validator() -> Draft202012Validator:
    schema = json.loads(
        resources.files("schauwerk.schemas")
        .joinpath(DURABILITY_EVIDENCE_SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def _parse_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FundusError(f"{label} is invalid JSON") from exc

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FundusError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise FundusError(f"{label} must be an object")
    return value


def _checked_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise FundusError("durability evidence verified_at is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FundusError("durability evidence verified_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FundusError("durability evidence verified_at must include a timezone")
    return value


def _safe_root(root: str | Path) -> tuple[Path, int, tuple[int, int]]:
    target = normalized_absolute(root, label="Fundus data root")
    descriptor: int | None = None
    try:
        descriptor = open_directory_chain(target)
        linked = os.stat(target, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except (OSError, FundusError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise FundusError(f"Fundus data root is unavailable: {exc}") from exc
    if (
        not stat.S_ISDIR(linked.st_mode)
        or stat.S_ISLNK(linked.st_mode)
        or linked.st_uid != os.geteuid()
        or linked.st_nlink < 1
        or stat.S_IMODE(linked.st_mode) & 0o077
        or (linked.st_dev, linked.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise FundusError("Fundus data root is unsafe")
    return target, descriptor, (opened.st_dev, opened.st_ino)


def fundus_inventory(root: str | Path) -> dict[str, Any]:
    """Return a deterministic, race-aware inventory of every Fundus state file."""
    target, root_fd, root_identity = _safe_root(root)

    def scan() -> tuple[list[dict[str, Any]], dict[str, tuple[int, ...]]]:
        files: list[dict[str, Any]] = []
        identities: dict[str, tuple[int, ...]] = {}

        def walk(directory_fd: int, prefix: Path) -> None:
            try:
                with os.scandir(directory_fd) as handle:
                    entries = sorted(handle, key=lambda item: item.name)
            except OSError as exc:
                raise FundusError(f"cannot enumerate Fundus inventory: {exc}") from exc
            for entry in entries:
                relative = prefix / entry.name
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise FundusError(
                        f"cannot stat Fundus inventory path: {relative.as_posix()}"
                    ) from exc
                if stat.S_ISLNK(metadata.st_mode):
                    raise FundusError(
                        f"Fundus inventory contains a symlink: {relative.as_posix()}"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    child = _open_child_directory(
                        directory_fd,
                        entry.name,
                        display=target / relative,
                    )
                    try:
                        opened = os.fstat(child)
                        identities[relative.as_posix() + "/"] = (
                            opened.st_dev,
                            opened.st_ino,
                            opened.st_mode,
                            opened.st_uid,
                            opened.st_mtime_ns,
                            opened.st_ctime_ns,
                        )
                        walk(child, relative)
                    finally:
                        os.close(child)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise FundusError(
                        f"Fundus inventory contains a special file: {relative.as_posix()}"
                    )
                if len(files) >= MAX_INVENTORY_FILES:
                    raise FundusError("Fundus inventory file budget exceeded")
                payload = _read_regular_at(
                    directory_fd,
                    entry.name,
                    maximum_bytes=max(metadata.st_size, 0),
                    label=f"Fundus inventory path {relative.as_posix()}",
                    require_owner=True,
                    forbidden_mode_bits=0,
                )
                opened = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                identities[relative.as_posix()] = (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mode,
                    opened.st_nlink,
                    opened.st_uid,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                files.append(
                    {
                        "path": relative.as_posix(),
                        "bytes": len(payload),
                        "sha256": digest_bytes(payload),
                    }
                )

        walk(root_fd, Path())
        return files, identities

    try:
        files, identities = scan()
        postflight_files, postflight_identities = scan()
        if files != postflight_files or identities != postflight_identities:
            raise FundusError("Fundus inventory changed between verification passes")
        try:
            linked = os.stat(target, follow_symlinks=False)
        except OSError as exc:
            raise FundusError("Fundus data root changed during inventory") from exc
        if (
            stat.S_ISLNK(linked.st_mode)
            or (linked.st_dev, linked.st_ino) != root_identity
            or (os.fstat(root_fd).st_dev, os.fstat(root_fd).st_ino) != root_identity
        ):
            raise FundusError("Fundus data root changed during inventory")
        files = postflight_files
    finally:
        os.close(root_fd)
    document = {"schema_version": INVENTORY_SCHEMA, "files": files}
    return {
        "schema_version": INVENTORY_SCHEMA,
        "inventory_sha256": digest_bytes(canonical_json(document)),
        "file_count": len(files),
        "total_bytes": sum(int(item["bytes"]) for item in files),
        "files": files,
    }


def build_durability_evidence(
    inventory: dict[str, Any],
    *,
    producer: str,
    evidence_ref: str,
    verified_at: str,
) -> dict[str, Any]:
    """Build one pure evidence document; this function never writes it."""
    if inventory.get("schema_version") != INVENTORY_SCHEMA:
        raise FundusError("durability evidence inventory schema is unsupported")
    producer = producer.strip()
    evidence_ref = evidence_ref.strip()
    if not producer or len(producer) > 200:
        raise FundusError("durability evidence producer is invalid")
    if not evidence_ref or len(evidence_ref) > 500:
        raise FundusError("durability evidence reference is invalid")
    verified_at = _checked_timestamp(verified_at)
    body = {
        "schema_version": DURABILITY_EVIDENCE_SCHEMA,
        "inventory_algorithm": INVENTORY_SCHEMA,
        "inventory_sha256": inventory["inventory_sha256"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
        "verification": VERIFICATION_MODE,
        "producer": producer,
        "evidence_ref": evidence_ref,
        "verified_at": verified_at,
    }
    return {**body, "receipt_digest": digest_json(body)}


def validate_durability_evidence(value: dict[str, Any]) -> dict[str, Any]:
    try:
        _validator().validate(value)
    except ValidationError as exc:
        raise FundusError(
            f"durability evidence schema validation failed: {exc.message}"
        ) from exc
    _checked_timestamp(value["verified_at"])
    body = {key: item for key, item in value.items() if key != "receipt_digest"}
    if digest_json(body) != value["receipt_digest"]:
        raise FundusError("durability evidence receipt digest mismatch")
    return value


def default_evidence_path() -> Path:
    explicit = os.environ.get("SCHAUWERK_FUNDUS_DURABILITY_EVIDENCE")
    if explicit:
        return normalized_absolute(explicit, label="Fundus durability evidence path")
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return normalized_absolute(
        base / "schauwerk" / "fundus" / "durability" / "current.json",
        label="Fundus durability evidence path",
    )


def durability_status(
    fundus_root: str | Path,
    *,
    evidence_path: str | Path | None = None,
    use_default_evidence: bool = True,
) -> dict[str, Any]:
    root = normalized_absolute(fundus_root, label="Fundus data root")
    if evidence_path is not None:
        path: Path | None = normalized_absolute(
            evidence_path, label="Fundus durability evidence path"
        )
    elif use_default_evidence:
        path = default_evidence_path()
    else:
        path = None

    if path is not None and (path == root or root in path.parents):
        return {
            "schema_version": "schauwerk-fundus-durability-status.v1",
            "evidence_path": str(path),
            "evidence_present": path.exists(),
            "evidence_valid": False,
            "current": False,
            "restore_verified_current": False,
            "inventory_algorithm": INVENTORY_SCHEMA,
            "inventory_sha256": None,
            "file_count": None,
            "total_bytes": None,
            "evidence_inventory_sha256": None,
            "producer": None,
            "evidence_ref": None,
            "verified_at": None,
            "error": "durability evidence must live outside the Fundus data root",
        }
    if not root.exists():
        evidence_present = path.exists() if path is not None else False
        return {
            "schema_version": "schauwerk-fundus-durability-status.v1",
            "evidence_path": str(path) if path is not None else None,
            "evidence_present": evidence_present,
            "evidence_valid": None if not evidence_present else False,
            "current": False,
            "restore_verified_current": False,
            "inventory_algorithm": INVENTORY_SCHEMA,
            "inventory_sha256": None,
            "file_count": None,
            "total_bytes": None,
            "evidence_inventory_sha256": None,
            "producer": None,
            "evidence_ref": None,
            "verified_at": None,
            "error": None if not evidence_present else "Fundus data root is missing",
        }

    inventory = fundus_inventory(root)
    base = {
        "schema_version": "schauwerk-fundus-durability-status.v1",
        "evidence_path": str(path) if path is not None else None,
        "inventory_algorithm": INVENTORY_SCHEMA,
        "inventory_sha256": inventory["inventory_sha256"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
    }
    if path is None:
        return {
            **base,
            "evidence_present": False,
            "evidence_valid": None,
            "current": False,
            "restore_verified_current": False,
            "evidence_inventory_sha256": None,
            "producer": None,
            "evidence_ref": None,
            "verified_at": None,
            "error": None,
        }

    if not path.exists():
        return {
            **base,
            "evidence_present": False,
            "evidence_valid": None,
            "current": False,
            "restore_verified_current": False,
            "evidence_inventory_sha256": None,
            "producer": None,
            "evidence_ref": None,
            "verified_at": None,
            "error": None,
        }

    try:
        payload = read_regular_bytes(
            path,
            maximum_bytes=MAX_EVIDENCE_BYTES,
            label="Fundus durability evidence",
            require_owner=True,
            forbidden_mode_bits=0o077,
        )
        evidence = _parse_json_object(payload, label="Fundus durability evidence")
        if payload != canonical_json(evidence) + b"\n":
            raise FundusError("Fundus durability evidence JSON is not canonical")
        validate_durability_evidence(evidence)
    except (FundusError, OSError) as exc:
        return {
            **base,
            "evidence_present": True,
            "evidence_valid": False,
            "current": False,
            "restore_verified_current": False,
            "evidence_inventory_sha256": None,
            "producer": None,
            "evidence_ref": None,
            "verified_at": None,
            "error": str(exc)[:500],
        }

    current = bool(
        evidence["inventory_sha256"] == inventory["inventory_sha256"]
        and evidence["file_count"] == inventory["file_count"]
        and evidence["total_bytes"] == inventory["total_bytes"]
        and evidence["verification"] == VERIFICATION_MODE
    )
    try:
        postflight_inventory = fundus_inventory(root)
    except FundusError as exc:
        return {
            **base,
            "evidence_present": True,
            "evidence_valid": True,
            "current": False,
            "restore_verified_current": False,
            "evidence_inventory_sha256": evidence["inventory_sha256"],
            "producer": evidence["producer"],
            "evidence_ref": evidence["evidence_ref"],
            "verified_at": evidence["verified_at"],
            "error": str(exc)[:500],
        }
    if postflight_inventory != inventory:
        return {
            **base,
            "inventory_sha256": postflight_inventory["inventory_sha256"],
            "file_count": postflight_inventory["file_count"],
            "total_bytes": postflight_inventory["total_bytes"],
            "evidence_present": True,
            "evidence_valid": True,
            "current": False,
            "restore_verified_current": False,
            "evidence_inventory_sha256": evidence["inventory_sha256"],
            "producer": evidence["producer"],
            "evidence_ref": evidence["evidence_ref"],
            "verified_at": evidence["verified_at"],
            "error": "Fundus inventory changed before durability status return",
        }
    return {
        **base,
        "evidence_present": True,
        "evidence_valid": True,
        "current": current,
        "restore_verified_current": current,
        "evidence_inventory_sha256": evidence["inventory_sha256"],
        "producer": evidence["producer"],
        "evidence_ref": evidence["evidence_ref"],
        "verified_at": evidence["verified_at"],
        "error": None,
    }
