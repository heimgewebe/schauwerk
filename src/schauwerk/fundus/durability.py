"""Provider-neutral restore evidence for the current Fundus data-root inventory."""

from __future__ import annotations

import hashlib
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
from .pathio import normalized_absolute, read_regular_bytes

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


def _safe_root(root: str | Path) -> Path:
    target = normalized_absolute(root, label="Fundus data root")
    try:
        linked = target.lstat()
    except OSError as exc:
        raise FundusError(f"Fundus data root is unavailable: {exc}") from exc
    if (
        not stat.S_ISDIR(linked.st_mode)
        or stat.S_ISLNK(linked.st_mode)
        or linked.st_uid != os.geteuid()
        or linked.st_nlink < 1
        or stat.S_IMODE(linked.st_mode) & 0o077
    ):
        raise FundusError("Fundus data root is unsafe")
    return target


def fundus_inventory(root: str | Path) -> dict[str, Any]:
    """Return a deterministic, race-aware inventory of every Fundus state file."""
    target = _safe_root(root)
    files: list[dict[str, Any]] = []

    def walk(directory: Path, prefix: Path) -> None:
        try:
            with os.scandir(directory) as handle:
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
                walk(Path(entry.path), relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise FundusError(
                    f"Fundus inventory contains a special file: {relative.as_posix()}"
                )
            if len(files) >= MAX_INVENTORY_FILES:
                raise FundusError("Fundus inventory file budget exceeded")

            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(entry.path, flags)
            except OSError as exc:
                raise FundusError(
                    f"cannot open Fundus inventory path: {relative.as_posix()}"
                ) from exc
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino)
                    != (metadata.st_dev, metadata.st_ino)
                    or opened.st_uid != os.geteuid()
                ):
                    raise FundusError(
                        f"Fundus inventory path changed while opening: {relative.as_posix()}"
                    )
                digest = hashlib.sha256()
                total = 0
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total += len(chunk)
                after = os.fstat(descriptor)
                if (
                    after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or total != after.st_size
                ):
                    raise FundusError(
                        f"Fundus inventory file changed while hashing: {relative.as_posix()}"
                    )
            finally:
                os.close(descriptor)
            files.append(
                {
                    "path": relative.as_posix(),
                    "bytes": total,
                    "sha256": digest.hexdigest(),
                }
            )

    walk(target, Path())
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
) -> dict[str, Any]:
    root = normalized_absolute(fundus_root, label="Fundus data root")
    path = (
        normalized_absolute(evidence_path, label="Fundus durability evidence path")
        if evidence_path is not None
        else default_evidence_path()
    )
    if path == root or root in path.parents:
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
        return {
            "schema_version": "schauwerk-fundus-durability-status.v1",
            "evidence_path": str(path),
            "evidence_present": path.exists(),
            "evidence_valid": None if not path.exists() else False,
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
            "error": None if not path.exists() else "Fundus data root is missing",
        }

    inventory = fundus_inventory(root)
    base = {
        "schema_version": "schauwerk-fundus-durability-status.v1",
        "evidence_path": str(path),
        "inventory_algorithm": INVENTORY_SCHEMA,
        "inventory_sha256": inventory["inventory_sha256"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
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
