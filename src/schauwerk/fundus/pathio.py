"""Descriptor-relative filesystem primitives for the Fundus trust boundary."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from .errors import FundusError


def normalized_absolute(path: str | Path, *, label: str = "path") -> Path:
    """Return an absolute lexical path while rejecting ambiguous traversal."""
    candidate = Path(path).expanduser()
    raw = os.fspath(candidate)
    if "\x00" in raw:
        raise FundusError(f"{label} contains a NUL byte")
    if any(part == ".." for part in candidate.parts):
        raise FundusError(f"{label} must not contain '..' traversal")
    return Path(os.path.abspath(raw))


def _directory_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _file_read_flags() -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _file_write_flags() -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _open_child_directory(parent_fd: int, name: str, *, display: Path) -> int:
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FundusError(
                f"unsafe symlink or non-directory path component: {display}"
            ) from exc
        raise
    try:
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(linked.st_mode) or not stat.S_ISDIR(opened.st_mode):
            raise FundusError(f"path component is not a directory: {display}")
        if linked.st_nlink < 1 or opened.st_nlink < 1:
            raise FundusError(f"directory identity is invalid: {display}")
        if (linked.st_dev, linked.st_ino) != (opened.st_dev, opened.st_ino):
            raise FundusError(f"directory identity changed while opening: {display}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_directory_chain(
    path: str | Path,
    *,
    create: bool = False,
    private_root: str | Path | None = None,
) -> int:
    """Open a directory one component at a time without following symlinks."""
    target = normalized_absolute(path, label="directory path")
    private = (
        normalized_absolute(private_root, label="private root")
        if private_root is not None
        else None
    )
    if private == Path("/"):
        raise FundusError("private root must not be the filesystem root")
    if private is not None and target != private and private not in target.parents:
        raise FundusError("directory escaped the configured private root")

    descriptor = os.open("/", _directory_flags())
    current = Path("/")
    try:
        for part in target.parts[1:]:
            next_path = current / part
            try:
                child = _open_child_directory(descriptor, part, display=next_path)
            except FileNotFoundError:
                if not create:
                    raise FundusError(f"directory does not exist: {next_path}") from None
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
                child = _open_child_directory(descriptor, part, display=next_path)

            enforce_private = private is not None and (
                next_path == private or private in next_path.parents
            )
            if enforce_private:
                opened = os.fstat(child)
                if opened.st_uid != os.geteuid() or opened.st_nlink < 1:
                    os.close(child)
                    raise FundusError(f"private directory ownership is unsafe: {next_path}")
                if stat.S_IMODE(opened.st_mode) != 0o700:
                    os.fchmod(child, 0o700)
                    os.fsync(child)
                    opened = os.fstat(child)
                if stat.S_IMODE(opened.st_mode) != 0o700:
                    os.close(child)
                    raise FundusError(f"private directory must be owner-only: {next_path}")

            os.close(descriptor)
            descriptor = child
            current = next_path
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_at(
    parent_fd: int,
    name: str,
    *,
    maximum_bytes: int,
    label: str,
    require_owner: bool,
    forbidden_mode_bits: int,
) -> bytes:
    if maximum_bytes < 0:
        raise FundusError("read limit must not be negative")
    try:
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        raise FundusError(f"{label} does not exist") from None
    if not stat.S_ISREG(linked.st_mode) or linked.st_nlink != 1:
        raise FundusError(f"{label} must be one regular non-linked file")
    if require_owner and linked.st_uid != os.geteuid():
        raise FundusError(f"{label} owner is unsafe")
    if stat.S_IMODE(linked.st_mode) & forbidden_mode_bits:
        raise FundusError(f"{label} permissions are unsafe")
    if linked.st_size > maximum_bytes:
        raise FundusError(f"{label} exceeds read limit")

    try:
        descriptor = os.open(name, _file_read_flags(), dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise FundusError(f"{label} must not be a symlink") from exc
        raise
    try:
        opened = os.fstat(descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_nlink,
            opened.st_uid,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        linked_identity = (
            linked.st_dev,
            linked.st_ino,
            linked.st_mode,
            linked.st_nlink,
            linked.st_uid,
            linked.st_size,
            linked.st_mtime_ns,
            linked.st_ctime_ns,
        )
        if identity != linked_identity:
            raise FundusError(f"{label} identity changed while opening")

        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = maximum_bytes + 1 - total
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise FundusError(f"{label} exceeds read limit")
            chunks.append(chunk)

        after = os.fstat(descriptor)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if after_identity != identity:
            raise FundusError(f"{label} changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_regular_bytes(
    path: str | Path,
    *,
    maximum_bytes: int,
    label: str,
    require_owner: bool = False,
    forbidden_mode_bits: int = 0,
    private_root: str | Path | None = None,
) -> bytes:
    """Read one regular file through a descriptor-bound, bounded path."""
    target = normalized_absolute(path, label=f"{label} path")
    private = (
        normalized_absolute(private_root, label="private root")
        if private_root is not None
        else None
    )
    if private is not None and private not in target.parents:
        raise FundusError(f"{label} escaped the configured private root")
    parent_fd = open_directory_chain(
        target.parent,
        create=False,
        private_root=private,
    )
    try:
        return _read_regular_at(
            parent_fd,
            target.name,
            maximum_bytes=maximum_bytes,
            label=label,
            require_owner=require_owner,
            forbidden_mode_bits=forbidden_mode_bits,
        )
    finally:
        os.close(parent_fd)


def write_create_or_verify(
    path: str | Path,
    payload: bytes,
    *,
    private_root: str | Path,
    mode: int = 0o600,
) -> None:
    """Create one immutable private file, or verify an identical existing file."""
    target = normalized_absolute(path, label="artifact path")
    private = normalized_absolute(private_root, label="private root")
    if private not in target.parents:
        raise FundusError("artifact escaped the configured private root")
    parent_fd = open_directory_chain(
        target.parent,
        create=True,
        private_root=private,
    )
    descriptor: int | None = None
    created = False
    try:
        try:
            descriptor = os.open(target.name, _file_write_flags(), mode, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            existing = _read_regular_at(
                parent_fd,
                target.name,
                maximum_bytes=max(len(payload), 1) + 1,
                label="Fundus artifact",
                require_owner=True,
                forbidden_mode_bits=0o077,
            )
            if existing != payload:
                raise FundusError(f"create-only Fundus artifact drifted: {target}")
            return

        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short Fundus artifact write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(parent_fd)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(target.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(parent_fd)
