"""Portable verification and consumer-lock contracts for immutable Fundus packages."""

from __future__ import annotations

import json
import os
import stat
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .errors import FundusError
from .media import inspect_media
from .model import canonical_json, digest_bytes, digest_json
from .pathio import normalized_absolute, read_regular_bytes

PACKAGE_SCHEMA_FILES = {
    "schauwerk-fundus-package.v1": "fundus-package.v1.schema.json",
    "schauwerk-fundus-package.v2": "fundus-package.v2.schema.json",
}
CONSUMER_LOCK_SCHEMA = "schauwerk-fundus-consumer-lock.v1"
CONSUMER_LOCK_SCHEMA_FILE = "fundus-consumer-lock.v1.schema.json"
MAX_PACKAGE_FILES = 256
MAX_PACKAGE_DIRECTORIES = 512
MAX_PACKAGE_DEPTH = 16
MAX_PACKAGE_FILE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_PACKAGE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_SUMS_BYTES = 256 * 1024
MAX_CONSUMER_LOCK_BYTES = 2 * 1024 * 1024


def _validator(schema_file: str) -> Draft202012Validator:
    schema = json.loads(
        resources.files("schauwerk.schemas").joinpath(schema_file).read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def _validate(value: dict[str, Any], schema_file: str, *, label: str) -> None:
    try:
        _validator(schema_file).validate(value)
    except ValidationError as exc:
        raise FundusError(f"{label} schema validation failed: {exc.message}") from exc


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


def _checked_relative_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise FundusError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FundusError(f"{label} must be a canonical relative path")
    if path.as_posix() != value:
        raise FundusError(f"{label} is not canonical")
    return value


def _safe_root(directory: str | Path, *, label: str) -> Path:
    root = normalized_absolute(directory, label=label)
    if root.is_symlink() or not root.is_dir():
        raise FundusError(f"{label} is missing or unsafe")
    metadata = root.lstat()
    if (
        metadata.st_uid != os.geteuid()
        or metadata.st_nlink < 1
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FundusError(f"{label} ownership or permissions are unsafe")
    return root


def _read_package_file(root: Path, relative: str, *, maximum_bytes: int, label: str) -> bytes:
    return read_regular_bytes(
        root / relative,
        maximum_bytes=maximum_bytes,
        label=label,
        require_owner=True,
        forbidden_mode_bits=0o022,
    )


def _inventory(root: Path) -> set[str]:
    actual: set[str] = set()
    directory_count = 0

    def walk(directory: Path, prefix: PurePosixPath, depth: int) -> None:
        nonlocal directory_count
        if depth > MAX_PACKAGE_DEPTH:
            raise FundusError("Fundus package directory depth exceeds the allowed limit")
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise FundusError("Fundus package directory cannot be enumerated") from exc
        entries.sort(key=lambda item: item.name)
        for entry in entries:
            relative = (prefix / entry.name).as_posix()
            try:
                linked = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise FundusError(f"package path cannot be inspected: {relative}") from exc
            if stat.S_ISLNK(linked.st_mode):
                raise FundusError(f"package path is a symlink: {relative}")
            if stat.S_ISDIR(linked.st_mode):
                directory_count += 1
                if directory_count > MAX_PACKAGE_DIRECTORIES:
                    raise FundusError("Fundus package directory count exceeds the allowed limit")
                if (
                    linked.st_uid != os.geteuid()
                    or linked.st_nlink < 1
                    or stat.S_IMODE(linked.st_mode) & 0o022
                ):
                    raise FundusError(f"package directory is unsafe: {relative}")
                walk(Path(entry.path), prefix / entry.name, depth + 1)
                continue
            if not stat.S_ISREG(linked.st_mode):
                raise FundusError(f"package path is not a regular file: {relative}")
            actual.add(relative)
            if len(actual) > MAX_PACKAGE_FILES + 2:
                raise FundusError("Fundus package file count exceeds the allowed limit")
            if (
                linked.st_uid != os.geteuid()
                or linked.st_nlink != 1
                or stat.S_IMODE(linked.st_mode) & 0o022
            ):
                raise FundusError(f"package file is unsafe: {relative}")

    walk(root, PurePosixPath(), 0)
    return actual


def verify_package_directory(directory: str | Path) -> dict[str, Any]:
    """Verify an immutable Fundus package without consulting live Fundus state."""
    root = _safe_root(directory, label="Fundus package directory")
    manifest_bytes = _read_package_file(
        root,
        "fundus-package.json",
        maximum_bytes=MAX_PACKAGE_MANIFEST_BYTES,
        label="Fundus package manifest",
    )
    manifest = _parse_json_object(
        manifest_bytes, label="Fundus package manifest"
    )
    if manifest_bytes != canonical_json(manifest) + b"\n":
        raise FundusError(
            "Fundus package manifest serialization is not canonical"
        )
    schema_version = manifest.get("schema_version")
    schema_file = PACKAGE_SCHEMA_FILES.get(schema_version)
    if schema_file is None:
        raise FundusError("Fundus package schema_version is unsupported")
    _validate(manifest, schema_file, label="Fundus package")

    body = dict(manifest)
    package_digest = body.pop("package_digest")
    if digest_json(body) != package_digest:
        raise FundusError("Fundus package manifest digest mismatch")
    if manifest.get("consumer_runtime_dependency") is not False:
        raise FundusError("Fundus package has a runtime dependency")

    file_records = manifest["files"]
    if not 1 <= len(file_records) <= MAX_PACKAGE_FILES:
        raise FundusError("Fundus package file count is outside the allowed range")
    paths = [
        _checked_relative_path(item["path"], label="Fundus package file path")
        for item in file_records
    ]
    if len(paths) != len(set(paths)):
        raise FundusError("Fundus package file paths are not unique")
    if sum(item["bytes"] for item in file_records) > MAX_PACKAGE_TOTAL_BYTES:
        raise FundusError("Fundus package exceeds the total byte limit")

    expected_files = {"fundus-package.json", "SHA256SUMS", *paths}
    if _inventory(root) != expected_files:
        raise FundusError("Fundus package file set mismatch")

    verified_files: list[dict[str, Any]] = []
    for item in file_records:
        payload = _read_package_file(
            root,
            item["path"],
            maximum_bytes=MAX_PACKAGE_FILE_BYTES,
            label=f"Fundus package file {item['path']}",
        )
        if len(payload) != item["bytes"] or digest_bytes(payload) != item["sha256"]:
            raise FundusError(f"Fundus package file drifted: {item['path']}")
        if inspect_media(payload).media_type != item["media_type"]:
            raise FundusError(f"Fundus package media_type drifted: {item['path']}")
        verified_files.append(dict(item))

    expected_sums = [f"{item['sha256']}  {item['path']}" for item in file_records]
    expected_sums.append(f"{digest_bytes(manifest_bytes)}  fundus-package.json")
    sums_bytes = _read_package_file(
        root,
        "SHA256SUMS",
        maximum_bytes=MAX_PACKAGE_SUMS_BYTES,
        label="Fundus package SHA256SUMS",
    )
    if sums_bytes != ("\n".join(expected_sums) + "\n").encode("utf-8"):
        raise FundusError("Fundus package SHA256SUMS mismatch")

    return {
        **manifest,
        "ok": True,
        "package_path": str(root),
        "package_manifest_sha256": digest_bytes(manifest_bytes),
        "verified_files": verified_files,
    }


def consumer_lock_manifest(package: dict[str, Any]) -> dict[str, Any]:
    """Create a portable lock body from one already verified package result."""
    if package.get("ok") is not True:
        raise FundusError("consumer lock requires a verified Fundus package")
    files = []
    for item in package["verified_files"]:
        files.append(
            {
                "path": item["path"],
                "role": item["role"],
                **({"source_role": item["source_role"]} if "source_role" in item else {}),
                "media_type": item["media_type"],
                "sha256": item["sha256"],
                "bytes": item["bytes"],
            }
        )
    body = {
        "schema_version": CONSUMER_LOCK_SCHEMA,
        "asset_id": package["asset_id"],
        "package_schema_version": package["schema_version"],
        "package_digest": package["package_digest"],
        "build_digest": package["build_digest"],
        "acceptance_digest": package["acceptance_digest"],
        "package_manifest_sha256": package["package_manifest_sha256"],
        "files": files,
        "consumer_runtime_dependency": False,
    }
    lock = {**body, "lock_digest": digest_json(body)}
    _validate(lock, CONSUMER_LOCK_SCHEMA_FILE, label="Fundus consumer lock")
    return lock


def load_consumer_lock(path: str | Path) -> dict[str, Any]:
    lock_path = normalized_absolute(path, label="Fundus consumer lock")
    payload = read_regular_bytes(
        lock_path,
        maximum_bytes=MAX_CONSUMER_LOCK_BYTES,
        label="Fundus consumer lock",
        require_owner=True,
        forbidden_mode_bits=0o022,
    )
    lock = _parse_json_object(payload, label="Fundus consumer lock")
    if payload != canonical_consumer_lock_bytes(lock):
        raise FundusError(
            "Fundus consumer lock serialization is not canonical"
        )
    _validate(lock, CONSUMER_LOCK_SCHEMA_FILE, label="Fundus consumer lock")
    paths = [
        _checked_relative_path(item["path"], label="Fundus consumer lock file path")
        for item in lock["files"]
    ]
    if len(paths) != len(set(paths)):
        raise FundusError("Fundus consumer lock file paths are not unique")
    body = dict(lock)
    declared = body.pop("lock_digest")
    if digest_json(body) != declared:
        raise FundusError("Fundus consumer lock digest mismatch")
    return lock


def verify_consumer_lock(lock_path: str | Path, package_dir: str | Path) -> dict[str, Any]:
    """Verify a vendored package against one portable Fundus consumer lock."""
    lock = load_consumer_lock(lock_path)
    package = verify_package_directory(package_dir)
    bindings = (
        ("asset_id", "asset_id"),
        ("package_schema_version", "schema_version"),
        ("package_digest", "package_digest"),
        ("build_digest", "build_digest"),
        ("acceptance_digest", "acceptance_digest"),
        ("package_manifest_sha256", "package_manifest_sha256"),
    )
    for lock_key, package_key in bindings:
        if lock[lock_key] != package[package_key]:
            raise FundusError(f"Fundus consumer lock binding mismatch: {lock_key}")
    package_files = []
    for item in package["verified_files"]:
        package_files.append(
            {
                "path": item["path"],
                "role": item["role"],
                **({"source_role": item["source_role"]} if "source_role" in item else {}),
                "media_type": item["media_type"],
                "sha256": item["sha256"],
                "bytes": item["bytes"],
            }
        )
    if lock["files"] != package_files:
        raise FundusError("Fundus consumer lock file binding mismatch")
    return {
        **lock,
        "ok": True,
        "package_path": package["package_path"],
        "consumer_runtime_dependency": False,
    }


def canonical_consumer_lock_bytes(lock: dict[str, Any]) -> bytes:
    """Return the immutable serialized lock representation."""
    return canonical_json(lock) + b"\n"
