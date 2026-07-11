"""Atomic local publication store with immutable objects and mutable stable links."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import mimetypes
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .model import (
    PUBLICATION_LINK_SCHEMA,
    PUBLICATION_OBJECT_SCHEMA,
    PUBLICATION_PREVIEW_SCHEMA,
    PublicationError,
    _digest,
    _read_json,
    _reject_control_strings,
    _safe_identifier,
    _safe_version,
    compile_preview,
    digest_mapping,
    parse_timestamp,
    timestamp_value,
    validate_declaration,
    validate_preview,
)

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _directory_identity(path: Path) -> tuple[int, int]:
    value = path.stat(follow_symlinks=False)
    return value.st_dev, value.st_ino


def _renameat2(source: Path, destination: Path, flags: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise PublicationError("atomic publication rename is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        flags,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
        raise PublicationError("atomic publication rename is unavailable")
    raise OSError(error_number, os.strerror(error_number), destination)


def _publish_directory_noreplace(source: Path, destination: Path) -> None:
    try:
        _renameat2(source, destination, _RENAME_NOREPLACE)
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
            raise PublicationError("immutable publication version already exists") from exc
        raise


def _make_tree_removable(path: Path) -> None:
    if not path.exists():
        return
    for item in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            item.chmod(0o700 if item.is_dir() else 0o600, follow_symlinks=False)
        except (FileNotFoundError, NotImplementedError):
            pass
    try:
        path.chmod(0o700)
    except FileNotFoundError:
        pass


def _remove_owned_directory(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        if _directory_identity(path) != identity:
            return
    except FileNotFoundError:
        return
    _make_tree_removable(path)
    shutil.rmtree(path, ignore_errors=True)


def _json_payload(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _write_json_temporary(
    directory: Path,
    *,
    prefix: str,
    value: Mapping[str, Any],
    mode: int,
) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_payload(value))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        return temporary
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_link_compare_and_swap(
    path: Path,
    value: Mapping[str, Any],
    *,
    expected_link_digest: str | None,
) -> dict[str, Any] | None:
    validated = validate_link(value)
    temporary = _write_json_temporary(
        path.parent,
        prefix=f".{path.name}.",
        value=validated,
        mode=0o644,
    )
    exchanged = False
    try:
        if expected_link_digest is None:
            try:
                _renameat2(temporary, path, _RENAME_NOREPLACE)
            except OSError as exc:
                if exc.errno in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise PublicationError("stable link appeared after review") from exc
                raise
            return None

        try:
            _renameat2(temporary, path, _RENAME_EXCHANGE)
            exchanged = True
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise PublicationError("stable link disappeared after review") from exc
            raise
        try:
            previous = _read_link_file(temporary)
            if previous["link_digest"] != expected_link_digest:
                raise PublicationError("stable link changed after review")
        except BaseException:
            try:
                _renameat2(temporary, path, _RENAME_EXCHANGE)
                exchanged = False
            except BaseException as rollback_exc:
                raise PublicationError(
                    "stable link compare-and-swap rollback failed"
                ) from rollback_exc
            raise
        exchanged = False
        try:
            temporary.unlink()
        except OSError:
            pass
        path.chmod(0o644)
        return previous
    finally:
        if exchanged:
            # The old path is preserved at ``temporary``. Do not unlink either side.
            pass
        else:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _remove_link_compare_and_swap(path: Path, *, expected_link_digest: str) -> None:
    descriptor, marker_name = tempfile.mkstemp(prefix=f".{path.name}.remove.", dir=path.parent)
    os.close(descriptor)
    marker = Path(marker_name)
    exchanged = False
    try:
        try:
            _renameat2(marker, path, _RENAME_EXCHANGE)
            exchanged = True
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise PublicationError("stable link disappeared during rollback") from exc
            raise
        try:
            current = _read_link_file(marker)
            if current["link_digest"] != expected_link_digest:
                raise PublicationError("stable link changed during rollback")
        except BaseException:
            try:
                _renameat2(marker, path, _RENAME_EXCHANGE)
                exchanged = False
            except BaseException as rollback_exc:
                raise PublicationError("stable link removal rollback failed") from rollback_exc
            raise
        try:
            path.unlink()
        except BaseException:
            try:
                _renameat2(marker, path, _RENAME_EXCHANGE)
                exchanged = False
            except BaseException as rollback_exc:
                raise PublicationError("stable link removal rollback failed") from rollback_exc
            raise
        exchanged = False
        try:
            marker.unlink()
        except OSError:
            pass
    finally:
        if not exchanged:
            try:
                marker.unlink()
            except FileNotFoundError:
                pass


def _restore_link_after_failure(
    path: Path,
    *,
    failed_link_digest: str,
    previous_link: Mapping[str, Any] | None,
) -> None:
    if previous_link is None:
        _remove_link_compare_and_swap(path, expected_link_digest=failed_link_digest)
        return
    _write_link_compare_and_swap(
        path,
        previous_link,
        expected_link_digest=failed_link_digest,
    )


def _open_directory_nofollow(path: Path) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise PublicationError("safe publication output traversal is unavailable")
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, os.O_RDONLY | directory_flag)
    try:
        for part in absolute.parts[1:]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | directory_flag | nofollow,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise PublicationError("publication output parent is not a directory")
        return descriptor
    except FileNotFoundError as exc:
        os.close(descriptor)
        raise PublicationError("publication output parent does not exist") from exc
    except OSError as exc:
        os.close(descriptor)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PublicationError("publication output parent is unsafe") from exc
        raise
    except BaseException:
        os.close(descriptor)
        raise


def write_new_json(path: Path, value: Mapping[str, Any], *, mode: int = 0o644) -> Path:
    if path.name in {"", ".", ".."}:
        raise PublicationError("publication output name is invalid")
    parent_descriptor = _open_directory_nofollow(path.parent)
    descriptor: int | None = None
    created = False
    try:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise PublicationError("safe publication output creation is unavailable")
        try:
            descriptor = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                mode,
                dir_fd=parent_descriptor,
            )
            created = True
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ELOOP}:
                raise PublicationError("output already exists or is unsafe") from exc
            raise
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(_json_payload(value))
            handle.flush()
            os.fsync(handle.fileno())
        return path
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(path.name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(parent_descriptor)


def _store_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "objects": root / "objects",
        "links": root / "links",
        "receipts": root / "receipts",
    }


def _open_child_directory(
    parent_descriptor: int,
    name: str,
    *,
    create: bool,
    mode: int,
    label: str,
) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise PublicationError("safe publication store traversal is unavailable")
    if create:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | directory_flag | nofollow,
            dir_fd=parent_descriptor,
        )
    except FileNotFoundError as exc:
        raise PublicationError(f"{label} is missing") from exc
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PublicationError(f"{label} is unsafe") from exc
        raise
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise PublicationError(f"{label} is not a directory")
        if create:
            os.fchmod(descriptor, mode)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _validate_store_root_entries(root_descriptor: int) -> None:
    allowed = {".lock", "objects", "links", "receipts"}
    unexpected = set(os.listdir(root_descriptor)) - allowed
    if unexpected:
        raise PublicationError("publication store root contains unexpected entries")


def _open_store(root: Path) -> dict[str, Path]:
    try:
        root_descriptor = _open_directory_nofollow(root)
    except PublicationError as exc:
        raise PublicationError("publication store root is missing or unsafe") from exc
    try:
        _validate_store_root_entries(root_descriptor)
        for name in ("objects", "links", "receipts"):
            descriptor = _open_child_directory(
                root_descriptor,
                name,
                create=False,
                mode=0o700,
                label=f"publication store {name} path",
            )
            os.close(descriptor)
    finally:
        os.close(root_descriptor)
    return _store_paths(root)


def _ensure_store(root: Path) -> dict[str, Path]:
    absolute = Path(os.path.abspath(root))
    if absolute.name in {"", ".", ".."}:
        raise PublicationError("publication store root name is invalid")
    parent_descriptor = _open_directory_nofollow(absolute.parent)
    root_created = False
    try:
        try:
            os.mkdir(absolute.name, mode=0o700, dir_fd=parent_descriptor)
            root_created = True
        except FileExistsError:
            pass
        root_descriptor = _open_child_directory(
            parent_descriptor,
            absolute.name,
            create=False,
            mode=0o700,
            label="publication store root",
        )
    finally:
        os.close(parent_descriptor)
    try:
        _validate_store_root_entries(root_descriptor)
        if root_created or stat.S_IMODE(os.fstat(root_descriptor).st_mode) != 0o700:
            os.fchmod(root_descriptor, 0o700)
        for name in ("objects", "links", "receipts"):
            descriptor = _open_child_directory(
                root_descriptor,
                name,
                create=True,
                mode=0o700,
                label=f"publication store {name} path",
            )
            os.close(descriptor)
    finally:
        os.close(root_descriptor)
    return _store_paths(absolute)


def _open_lock_descriptor(root: Path, *, exclusive: bool) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise PublicationError("safe publication store locking is unavailable")
    root_descriptor = _open_directory_nofollow(root)
    flags = (os.O_RDWR | os.O_CREAT) if exclusive else os.O_RDONLY
    try:
        try:
            descriptor = os.open(
                ".lock",
                flags | nofollow,
                0o600,
                dir_fd=root_descriptor,
            )
        except FileNotFoundError as exc:
            raise PublicationError("publication store lock is missing") from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise PublicationError("publication store lock is unsafe") from exc
            raise
    finally:
        os.close(root_descriptor)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PublicationError("publication store lock must be a regular file")
        if exclusive:
            os.fchmod(descriptor, 0o600)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _store_lock(root: Path, *, exclusive: bool) -> Iterator[dict[str, Path]]:
    paths = _ensure_store(root) if exclusive else _open_store(root)
    descriptor = _open_lock_descriptor(root, exclusive=exclusive)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield paths
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _object_manifest(preview: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": PUBLICATION_OBJECT_SCHEMA,
        "publication_id": preview["publication_id"],
        "stable_slug": preview["stable_slug"],
        "version": preview["version"],
        "view_id": preview["view_id"],
        "audience": preview["audience"],
        "entrypoint": preview["entrypoint"],
        "lifecycle": preview["lifecycle"],
        "source_package": preview["source_package"],
        "files": preview["files"],
        "privacy_checks": preview["privacy_checks"],
        "declaration_digest": preview["declaration_digest"],
        "preview_digest": preview["preview_digest"],
        "object_digest": "",
    }
    value["object_digest"] = digest_mapping(value, "object_digest")
    return value


def validate_object_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "publication_id",
        "stable_slug",
        "version",
        "view_id",
        "audience",
        "entrypoint",
        "lifecycle",
        "source_package",
        "files",
        "privacy_checks",
        "declaration_digest",
        "preview_digest",
        "object_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PublicationError("publication object manifest fields are invalid")
    if value.get("schema_version") != PUBLICATION_OBJECT_SCHEMA:
        raise PublicationError("publication object schema is unsupported")
    preview = {
        **{
            key: item
            for key, item in value.items()
            if key not in {"schema_version", "object_digest"}
        },
        "schema_version": PUBLICATION_PREVIEW_SCHEMA,
    }
    validated_preview = validate_preview(preview)
    declared = _digest(value.get("object_digest"), label="object_digest")
    if declared != digest_mapping(value, "object_digest"):
        raise PublicationError("publication object digest mismatch")
    normalized = {
        **validated_preview,
        "schema_version": PUBLICATION_OBJECT_SCHEMA,
        "object_digest": declared,
    }
    return json.loads(json.dumps(normalized, ensure_ascii=False, sort_keys=True))


def _link_value(
    *,
    preview: Mapping[str, Any],
    object_digest: str,
    previous_link_digest: str | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": PUBLICATION_LINK_SCHEMA,
        "stable_slug": preview["stable_slug"],
        "publication_id": preview["publication_id"],
        "version": preview["version"],
        "object_digest": object_digest,
        "state": "active",
        "published_at": preview["lifecycle"]["published_at"],
        "expires_at": preview["lifecycle"]["expires_at"],
        "updated_at": preview["lifecycle"]["published_at"],
        "withdrawn_at": None,
        "withdrawal_reason": None,
        "previous_link_digest": previous_link_digest,
        "link_digest": "",
    }
    value["link_digest"] = digest_mapping(value, "link_digest")
    return value


def validate_link(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "stable_slug",
        "publication_id",
        "version",
        "object_digest",
        "state",
        "published_at",
        "expires_at",
        "updated_at",
        "withdrawn_at",
        "withdrawal_reason",
        "previous_link_digest",
        "link_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PublicationError("publication link fields are invalid")
    if value.get("schema_version") != PUBLICATION_LINK_SCHEMA:
        raise PublicationError("publication link schema is unsupported")
    _safe_identifier(value.get("stable_slug"), label="stable_slug")
    _safe_identifier(value.get("publication_id"), label="publication_id")
    _safe_version(value.get("version"))
    _digest(value.get("object_digest"), label="object_digest")
    if value.get("state") not in {"active", "withdrawn"}:
        raise PublicationError("publication link state is invalid")
    published_at = parse_timestamp(value.get("published_at"), label="published_at")
    expires_at = parse_timestamp(value.get("expires_at"), label="expires_at", nullable=True)
    updated_at = parse_timestamp(value.get("updated_at"), label="updated_at")
    if (
        value.get("published_at") != published_at
        or value.get("expires_at") != expires_at
        or value.get("updated_at") != updated_at
    ):
        raise PublicationError("publication link timestamps are not canonical")
    if expires_at is not None and timestamp_value(expires_at) <= timestamp_value(published_at):
        raise PublicationError("publication link expiry is invalid")
    previous = value.get("previous_link_digest")
    if previous is not None:
        _digest(previous, label="previous_link_digest")
    if value["state"] == "active":
        if updated_at != published_at:
            raise PublicationError("active publication link update must equal publication time")
        if value.get("withdrawn_at") is not None or value.get("withdrawal_reason") is not None:
            raise PublicationError("active publication link contains withdrawal metadata")
    else:
        withdrawn_at = parse_timestamp(value.get("withdrawn_at"), label="withdrawn_at")
        if value.get("withdrawn_at") != withdrawn_at:
            raise PublicationError("withdrawal timestamp is not canonical")
        reason = value.get("withdrawal_reason")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
            raise PublicationError("withdrawal reason is invalid")
        _reject_control_strings(reason, label="withdrawal reason")
        if withdrawn_at != updated_at:
            raise PublicationError("withdrawal and update timestamps must match")
    declared = _digest(value.get("link_digest"), label="link_digest")
    if declared != digest_mapping(value, "link_digest"):
        raise PublicationError("publication link digest mismatch")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _read_link_file(path: Path) -> dict[str, Any]:
    return validate_link(_read_json(path, label="publication link"))


def _link_path(paths: Mapping[str, Path], slug: str) -> Path:
    return paths["links"] / f"{_safe_identifier(slug, label='stable_slug')}.json"


def _object_path(paths: Mapping[str, Path], publication_id: str, version: str) -> Path:
    return (
        paths["objects"]
        / _safe_identifier(publication_id, label="publication_id")
        / _safe_version(version)
    )


def _verify_object_from_paths(
    paths: Mapping[str, Path], publication_id: str, version: str
) -> dict[str, Any]:
    object_root = _object_path(paths, publication_id, version)
    if object_root.is_symlink() or not object_root.is_dir():
        raise PublicationError("immutable publication object is missing or unsafe")
    bundle = object_root / "bundle"
    manifest_path = object_root / "publication.json"
    if bundle.is_symlink() or not bundle.is_dir():
        raise PublicationError("publication bundle directory is missing or unsafe")
    manifest = validate_object_manifest(_read_json(manifest_path, label="publication object"))
    if manifest["publication_id"] != publication_id or manifest["version"] != version:
        raise PublicationError("publication object path binding mismatch")
    if {item.name for item in object_root.iterdir()} != {"bundle", "publication.json"}:
        raise PublicationError("publication object root file set mismatch")
    if stat.S_IMODE(object_root.stat().st_mode) & 0o222:
        raise PublicationError("publication object directory is writable")
    if stat.S_IMODE(bundle.stat().st_mode) & 0o222:
        raise PublicationError("publication bundle directory is writable")
    if stat.S_IMODE(manifest_path.stat().st_mode) & 0o222:
        raise PublicationError("publication object manifest is writable")
    actual_names = {item.name for item in bundle.iterdir()}
    if actual_names != set(manifest["files"]):
        raise PublicationError("publication object file set mismatch")
    for name, record in manifest["files"].items():
        path = bundle / name
        if path.is_symlink() or not path.is_file():
            raise PublicationError(f"publication object file {name} is unsafe")
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise PublicationError(f"publication object file {name} is writable")
        payload = path.read_bytes()
        if len(payload) != record["bytes"]:
            raise PublicationError(f"publication object file {name} size mismatch")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise PublicationError(f"publication object file {name} digest mismatch")
    return manifest


def verify_object(root: Path, publication_id: str, version: str) -> dict[str, Any]:
    return _verify_object_from_paths(_open_store(root), publication_id, version)


def _owned_object_matches_expected(
    path: Path,
    expected_manifest: Mapping[str, Any],
) -> bool:
    try:
        if path.is_symlink() or not path.is_dir():
            return False
        manifest_path = path / "publication.json"
        bundle = path / "bundle"
        if (
            manifest_path.is_symlink()
            or not manifest_path.is_file()
            or bundle.is_symlink()
            or not bundle.is_dir()
        ):
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest != expected_manifest:
            return False
        if {item.name for item in path.iterdir()} != {"bundle", "publication.json"}:
            return False
        if {item.name for item in bundle.iterdir()} != set(expected_manifest["files"]):
            return False
        for name, record in expected_manifest["files"].items():
            file_path = bundle / name
            if file_path.is_symlink() or not file_path.is_file():
                return False
            payload = file_path.read_bytes()
            if len(payload) != record["bytes"]:
                return False
            if hashlib.sha256(payload).hexdigest() != record["sha256"]:
                return False
        return True
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return False


def _remove_verified_owned_object(
    *,
    path: Path,
    identity: tuple[int, int] | None,
    expected_manifest: Mapping[str, Any],
) -> None:
    if identity is None:
        return
    try:
        if _directory_identity(path) != identity:
            return
    except FileNotFoundError:
        return
    if not _owned_object_matches_expected(path, expected_manifest):
        return
    _remove_owned_directory(path, identity)


def _record_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        existing = _read_json(path, label="publication receipt")
        if existing != receipt:
            raise PublicationError("publication receipt digest collision")
        return
    write_new_json(path, receipt, mode=0o600)


def _release_receipt(
    *,
    paths: Mapping[str, Path],
    reviewed: Mapping[str, Any],
    verified: Mapping[str, Any],
    link: Mapping[str, Any],
    object_created: bool,
    link_updated: bool,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": "schauwerk-publication-release-receipt.v1",
        "ok": True,
        "publication_id": reviewed["publication_id"],
        "stable_slug": reviewed["stable_slug"],
        "stable_path": f"/p/{reviewed['stable_slug']}/",
        "version": reviewed["version"],
        "object_digest": verified["object_digest"],
        "link_digest": link["link_digest"],
        "preview_digest": reviewed["preview_digest"],
        "expires_at": link["expires_at"],
        "immutable_object_created": object_created,
        "stable_link_updated": link_updated,
        "source_truth_mutated": False,
        "provider_mutation_attempted": False,
        "read_only_delivery": True,
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = digest_mapping(receipt, "receipt_digest")
    receipt_path = paths["receipts"] / f"release-{receipt['receipt_digest']}.json"
    _record_receipt(receipt_path, receipt)
    return receipt


def release_publication(
    *,
    declaration: Mapping[str, Any],
    preview: Mapping[str, Any],
    source_dir: Path,
    store_root: Path,
) -> dict[str, Any]:
    declared = validate_declaration(declaration)
    reviewed = validate_preview(preview)
    fresh, payloads = compile_preview(declared, source_dir)
    if fresh != reviewed:
        raise PublicationError("reviewed preview does not match fresh source compilation")

    object_manifest = _object_manifest(reviewed)
    with _store_lock(store_root, exclusive=True) as paths:
        link_path = _link_path(paths, reviewed["stable_slug"])
        existing_link = (
            _read_link_file(link_path) if link_path.exists() or link_path.is_symlink() else None
        )
        if existing_link is not None:
            if existing_link["publication_id"] != reviewed["publication_id"]:
                raise PublicationError("stable link belongs to a different publication")
            if existing_link["version"] == reviewed["version"]:
                existing_object = verify_object(
                    store_root,
                    reviewed["publication_id"],
                    reviewed["version"],
                )
                if existing_object != object_manifest:
                    raise PublicationError(
                        "stable link version exists with different immutable content"
                    )
                if existing_link["object_digest"] != object_manifest["object_digest"]:
                    raise PublicationError("stable link object digest mismatch")
                if existing_link["state"] != "active":
                    raise PublicationError("withdrawn publication cannot be reactivated by retry")
                if (
                    existing_link["published_at"] != reviewed["lifecycle"]["published_at"]
                    or existing_link["expires_at"] != reviewed["lifecycle"]["expires_at"]
                ):
                    raise PublicationError("stable link lifecycle differs from reviewed preview")
                return _release_receipt(
                    paths=paths,
                    reviewed=reviewed,
                    verified=existing_object,
                    link=existing_link,
                    object_created=True,
                    link_updated=True,
                )

        lifecycle = reviewed["lifecycle"]
        if existing_link is None:
            if (
                lifecycle["replaces_version"] is not None
                or lifecycle["expected_link_digest"] is not None
            ):
                raise PublicationError("publication expected a stable link that does not exist")
        else:
            if lifecycle["replaces_version"] != existing_link["version"]:
                raise PublicationError("stable link version changed after review")
            if lifecycle["expected_link_digest"] != existing_link["link_digest"]:
                raise PublicationError("stable link digest changed after review")
            if timestamp_value(lifecycle["published_at"]) <= timestamp_value(
                existing_link["published_at"]
            ):
                raise PublicationError(
                    "replacement publication time must follow the previous version"
                )

        target = _object_path(paths, reviewed["publication_id"], reviewed["version"])
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.is_symlink():
            raise PublicationError("publication object parent is unsafe")

        published_identity: tuple[int, int] | None = None
        object_created = False
        if target.exists() or target.is_symlink():
            existing_object = verify_object(
                store_root,
                reviewed["publication_id"],
                reviewed["version"],
            )
            if existing_object != object_manifest:
                raise PublicationError(
                    "immutable publication version already exists with other content"
                )
        else:
            temporary = Path(tempfile.mkdtemp(prefix=f".{reviewed['version']}.", dir=target.parent))
            try:
                bundle = temporary / "bundle"
                bundle.mkdir(mode=0o755)
                for name, payload in payloads.items():
                    path = bundle / name
                    descriptor = os.open(
                        path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o444,
                    )
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    path.chmod(0o444)
                manifest_path = temporary / "publication.json"
                descriptor = os.open(
                    manifest_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o444,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(_json_payload(object_manifest))
                    handle.flush()
                    os.fsync(handle.fileno())
                manifest_path.chmod(0o444)
                bundle.chmod(0o555)
                temporary.chmod(0o555)
                identity = _directory_identity(temporary)
                _publish_directory_noreplace(temporary, target)
                published_identity = identity
                object_created = True
            finally:
                if temporary.exists():
                    _make_tree_removable(temporary)
                    shutil.rmtree(temporary, ignore_errors=True)

        previous_digest = existing_link["link_digest"] if existing_link else None
        link = _link_value(
            preview=reviewed,
            object_digest=object_manifest["object_digest"],
            previous_link_digest=previous_digest,
        )
        link_committed = False
        previous_link: dict[str, Any] | None = None
        try:
            previous_link = _write_link_compare_and_swap(
                link_path,
                link,
                expected_link_digest=previous_digest,
            )
            link_committed = True
            verified = verify_object(
                store_root,
                reviewed["publication_id"],
                reviewed["version"],
            )
            return _release_receipt(
                paths=paths,
                reviewed=reviewed,
                verified=verified,
                link=link,
                object_created=object_created,
                link_updated=True,
            )
        except BaseException:
            rollback_error: BaseException | None = None
            if link_committed:
                try:
                    _restore_link_after_failure(
                        link_path,
                        failed_link_digest=link["link_digest"],
                        previous_link=previous_link,
                    )
                except BaseException as exc:
                    rollback_error = exc
            if object_created and rollback_error is None:
                _remove_verified_owned_object(
                    path=target,
                    identity=published_identity,
                    expected_manifest=object_manifest,
                )
            if rollback_error is not None:
                raise PublicationError(
                    "publication release rollback failed; immutable object was preserved"
                ) from rollback_error
            raise


def _publication_status_from_paths(
    paths: Mapping[str, Path],
    stable_slug: str,
    *,
    observed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    link = _read_link_file(_link_path(paths, stable_slug))
    manifest = _verify_object_from_paths(paths, link["publication_id"], link["version"])
    if manifest["object_digest"] != link["object_digest"]:
        raise PublicationError("stable link object digest mismatch")
    if manifest["stable_slug"] != link["stable_slug"]:
        raise PublicationError("stable link slug mismatch")
    lifecycle_state = link["state"]
    if lifecycle_state == "active":
        if timestamp_value(observed_at) < timestamp_value(link["published_at"]):
            lifecycle_state = "scheduled"
        elif link["expires_at"] is not None and timestamp_value(observed_at) >= timestamp_value(
            link["expires_at"]
        ):
            lifecycle_state = "expired"
    status = {
        "schema_version": "schauwerk-publication-status.v1",
        "publication_id": link["publication_id"],
        "stable_slug": link["stable_slug"],
        "stable_path": f"/p/{link['stable_slug']}/",
        "version": link["version"],
        "state": lifecycle_state,
        "published_at": link["published_at"],
        "expires_at": link["expires_at"],
        "withdrawn_at": link["withdrawn_at"],
        "withdrawal_reason": link["withdrawal_reason"],
        "observed_at": observed_at,
        "link_digest": link["link_digest"],
        "object_digest": manifest["object_digest"],
        "entrypoint": manifest["entrypoint"],
        "integrity": "verified",
        "read_only": True,
    }
    return status, manifest


def publication_status(
    store_root: Path,
    stable_slug: str,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    observed_at = parse_timestamp(now or _utc_now(), label="observed_at")
    with _store_lock(store_root, exclusive=False) as paths:
        status, _ = _publication_status_from_paths(
            paths,
            stable_slug,
            observed_at=observed_at,
        )
        return status


def withdraw_publication(
    store_root: Path,
    stable_slug: str,
    *,
    expected_link_digest: str,
    reason: str,
    withdrawn_at: str | None = None,
) -> dict[str, Any]:
    expected = _digest(expected_link_digest, label="expected_link_digest")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise PublicationError("withdrawal reason is invalid")
    _reject_control_strings(reason, label="withdrawal reason")
    at = parse_timestamp(withdrawn_at or _utc_now(), label="withdrawn_at")
    with _store_lock(store_root, exclusive=True) as paths:
        path = _link_path(paths, stable_slug)
        current = _read_link_file(path)
        if current["link_digest"] != expected:
            raise PublicationError("stable link changed after withdrawal review")
        if current["state"] == "withdrawn":
            raise PublicationError("publication is already withdrawn")
        updated = {
            **current,
            "state": "withdrawn",
            "updated_at": at,
            "withdrawn_at": at,
            "withdrawal_reason": reason,
            "previous_link_digest": current["link_digest"],
            "link_digest": "",
        }
        updated["link_digest"] = digest_mapping(updated, "link_digest")
        updated = validate_link(updated)
        link_committed = False
        try:
            previous = _write_link_compare_and_swap(
                path,
                updated,
                expected_link_digest=current["link_digest"],
            )
            if previous != current:
                raise PublicationError("withdrawal compare-and-swap returned unexpected link")
            link_committed = True
            manifest = verify_object(
                store_root,
                current["publication_id"],
                current["version"],
            )
            receipt: dict[str, Any] = {
                "schema_version": "schauwerk-publication-withdrawal-receipt.v1",
                "ok": True,
                "publication_id": current["publication_id"],
                "stable_slug": current["stable_slug"],
                "version": current["version"],
                "object_digest": manifest["object_digest"],
                "previous_link_digest": current["link_digest"],
                "link_digest": updated["link_digest"],
                "withdrawn_at": at,
                "reason": reason,
                "immutable_object_preserved": True,
                "source_truth_mutated": False,
                "provider_mutation_attempted": False,
                "receipt_digest": "",
            }
            receipt["receipt_digest"] = digest_mapping(receipt, "receipt_digest")
            receipt_path = paths["receipts"] / f"withdraw-{receipt['receipt_digest']}.json"
            _record_receipt(receipt_path, receipt)
            return receipt
        except BaseException:
            if link_committed:
                try:
                    _write_link_compare_and_swap(
                        path,
                        current,
                        expected_link_digest=updated["link_digest"],
                    )
                except BaseException as rollback_exc:
                    raise PublicationError(
                        "publication withdrawal rollback failed"
                    ) from rollback_exc
            raise


def resolve_publication_file(
    store_root: Path,
    stable_slug: str,
    relative_name: str | None,
    *,
    now: str | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    observed_at = parse_timestamp(now or _utc_now(), label="observed_at")
    with _store_lock(store_root, exclusive=False) as paths:
        status, manifest = _publication_status_from_paths(
            paths,
            stable_slug,
            observed_at=observed_at,
        )
        if status["state"] != "active":
            raise PublicationError(f"publication is {status['state']}")
        name = relative_name or manifest["entrypoint"]
        if not isinstance(name, str) or name not in manifest["files"]:
            raise PublicationError("publication file is not declared")
        path = _object_path(paths, status["publication_id"], status["version"]) / "bundle" / name
        if path.is_symlink() or not path.is_file():
            raise PublicationError("publication file became unsafe during delivery")
        payload = path.read_bytes()
        record = manifest["files"][name]
        if len(payload) != record["bytes"]:
            raise PublicationError("publication file size changed during delivery")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise PublicationError("publication file digest changed during delivery")
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if mime.startswith("text/"):
            mime += "; charset=utf-8"
        return status, payload, mime
