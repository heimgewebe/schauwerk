"""Fail-closed runtime for package-bound representation delivery."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from schauwerk.surfaces.miro.native_executor import (
    load_native_resume_receipt,
    validate_native_bundle,
)

from .delivery import (
    RECEIPT_SCHEMA,
    NativeDeliveryClient,
    RepresentationDeliveryError,
    _bytes_digest,
    _digest,
    validate_representation_package,
)


def _reject_symlink_chain(path: Path, *, label: str) -> None:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise RepresentationDeliveryError(f"{label} path must not contain symlinks")


def _assert_output_outside_package(*, package_root: Path, output_dir: Path) -> Path:
    destination = output_dir.expanduser().absolute()
    try:
        destination.relative_to(package_root)
    except ValueError:
        return destination
    raise RepresentationDeliveryError("delivery output must be outside the representation package")


def _prepare_output_dir(path: Path, *, resume: bool) -> Path:
    destination = path.expanduser().absolute()
    _reject_symlink_chain(destination, label="delivery output")
    if destination.exists():
        if not destination.is_dir():
            raise RepresentationDeliveryError("delivery output path is not a directory")
        current = destination.stat(follow_symlinks=False)
        if current.st_uid != os.getuid() or current.st_mode & 0o077:
            raise RepresentationDeliveryError("delivery output directory must be owner-only")
        names = {item.name for item in destination.iterdir()}
        required = {"native-bundle.json", "native-execution.json"}
        if resume:
            if names - (required | {"delivery.lock"}) or not required <= names:
                raise RepresentationDeliveryError(
                    "delivery resume directory has an unexpected file set"
                )
        elif names:
            raise RepresentationDeliveryError("delivery output directory must be absent or empty")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_chain(destination, label="delivery output")
        destination.mkdir(mode=0o700)
    return destination


@contextmanager
def _delivery_lock(destination: Path):
    lock_path = destination / "delivery.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise RepresentationDeliveryError("delivery lock is unavailable") from exc
    identity: tuple[int, int] | None = None
    acquired = False
    try:
        current = os.fstat(descriptor)
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_uid != os.getuid()
            or current.st_nlink != 1
            or current.st_mode & 0o077
        ):
            raise RepresentationDeliveryError("delivery lock is unsafe")
        identity = (current.st_dev, current.st_ino)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RepresentationDeliveryError("another delivery owns this output") from exc
        acquired = True
        yield lock_path
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
        if acquired and identity is not None:
            try:
                observed = lock_path.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (observed.st_dev, observed.st_ino) == identity:
                    lock_path.unlink()


def _write_new_bytes(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short delivery write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_new_bytes(path, payload)


def _read_private_file(path: Path, *, label: str, maximum_bytes: int = 4_000_000) -> bytes:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RepresentationDeliveryError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
        ):
            raise RepresentationDeliveryError(f"{label} is unsafe")
        if before.st_size > maximum_bytes:
            raise RepresentationDeliveryError(f"{label} exceeds its size limit")
        payload = bytearray()
        while len(payload) < before.st_size:
            chunk = os.read(descriptor, min(65_536, before.st_size - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity or len(payload) != before.st_size:
            raise RepresentationDeliveryError(f"{label} changed while being read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _freeze_native_bundle(
    *,
    path: Path,
    payload: bytes,
    expected_sha256: str,
    expected_digest: str,
    resume: bool,
) -> None:
    if resume:
        observed = _read_private_file(path, label="frozen native bundle")
    else:
        _write_new_bytes(path, payload)
        observed = _read_private_file(path, label="frozen native bundle")
    if _bytes_digest(observed) != expected_sha256:
        raise RepresentationDeliveryError("frozen native bundle digest mismatch")
    try:
        value = json.loads(observed)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepresentationDeliveryError("frozen native bundle is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RepresentationDeliveryError("frozen native bundle must be an object")
    validated = validate_native_bundle(value)
    if validated["bundle_digest"] != expected_digest:
        raise RepresentationDeliveryError("frozen native bundle belongs to another package")


async def deliver_representation_package(
    *,
    alias: str,
    package_dir: Path,
    output_dir: Path,
    client: NativeDeliveryClient,
    resume: bool = False,
) -> dict[str, Any]:
    """Validate one package and execute its frozen native bundle with checkpoints."""

    package = validate_representation_package(package_dir)
    bundle = package["bundle"]
    bundle_payload = package["native_bundle_payload"]
    if bundle is None or not isinstance(bundle_payload, bytes):
        raise RepresentationDeliveryError("representation package has no native Miro bundle")
    destination = _assert_output_outside_package(
        package_root=package["root"], output_dir=output_dir
    )
    destination = _prepare_output_dir(destination, resume=resume)
    frozen_bundle_path = destination / "native-bundle.json"
    native_path = destination / "native-execution.json"
    delivery_path = destination / "delivery-receipt.json"

    with _delivery_lock(destination):
        _freeze_native_bundle(
            path=frozen_bundle_path,
            payload=bundle_payload,
            expected_sha256=package["native_bundle_sha256"],
            expected_digest=bundle["bundle_digest"],
            resume=resume,
        )
        if resume:
            resume_receipt = load_native_resume_receipt(native_path)
            if resume_receipt["bundle_digest"] != bundle["bundle_digest"]:
                raise RepresentationDeliveryError(
                    "delivery resume receipt belongs to another package"
                )
        native_receipt = await client.native_apply(
            alias=alias,
            input_path=frozen_bundle_path,
            output_path=native_path,
            resume_path=native_path if resume else None,
        )
        native_payload = _read_private_file(native_path, label="native execution receipt")
        try:
            persisted_native_receipt = json.loads(native_payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RepresentationDeliveryError("native execution receipt is invalid JSON") from exc
        if not isinstance(persisted_native_receipt, dict):
            raise RepresentationDeliveryError("native execution receipt must be an object")
        if persisted_native_receipt != native_receipt:
            raise RepresentationDeliveryError(
                "native execution result does not match its persisted receipt"
            )
        native_receipt = persisted_native_receipt
        if (
            native_receipt.get("success") is not True
            or native_receipt.get("execution_state") != "complete"
        ):
            raise RepresentationDeliveryError("native execution did not complete successfully")
        if native_receipt.get("bundle_digest") != bundle["bundle_digest"]:
            raise RepresentationDeliveryError("native execution receipt bundle binding mismatch")
        if native_receipt.get("completed_operation_count") != len(bundle["operations"]):
            raise RepresentationDeliveryError("native execution receipt operation count mismatch")
        postflight = native_receipt.get("postflight")
        if not isinstance(postflight, Mapping) or not isinstance(
            postflight.get("inventory"), Mapping
        ):
            raise RepresentationDeliveryError("native execution receipt lacks postflight inventory")

        receipt: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA,
            "success": True,
            "package_digest": package["manifest"]["package_digest"],
            "manifest_sha256": package["manifest_sha256"],
            "input_digest": package["model"]["input_digest"],
            "plan_digest": package["plan"]["plan_digest"],
            "native_bundle_digest": bundle["bundle_digest"],
            "native_bundle_sha256": package["native_bundle_sha256"],
            "native_execution_digest": native_receipt["execution_digest"],
            "native_receipt_sha256": _bytes_digest(native_payload),
            "board_alias": alias,
            "selected_formats": package["plan"]["selected_formats"],
            "native_operation_count": len(bundle["operations"]),
            "completed_operation_count": native_receipt["completed_operation_count"],
            "quality_score": (package["quality"]["score"] if package["quality"] else None),
            "provider_readback_verified": True,
            "resumed": resume,
            "mutation_attempted": bool(native_receipt.get("mutation_attempted")),
            "globally_atomic": False,
            "truth_boundary": {
                "provider_operations_are_sequential": True,
                "rollback_available_for_all_item_types": False,
                "package_integrity_recomputed_before_provider_contact": True,
                "provider_payload_frozen_before_provider_contact": True,
                "aesthetic_quality_requires_human_review": True,
            },
        }
        receipt["delivery_digest"] = _digest(receipt)
        try:
            _write_new_json(delivery_path, receipt)
        except OSError as exc:
            raise RepresentationDeliveryError(
                "provider execution succeeded but delivery receipt publication failed; "
                "reconcile from native-execution.json"
            ) from exc
    return {
        **receipt,
        "output_dir": str(destination),
        "native_bundle": str(frozen_bundle_path),
        "native_receipt": str(native_path),
        "delivery_receipt": str(delivery_path),
    }
