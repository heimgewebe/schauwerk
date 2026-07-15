"""Separate owner-only authorization state for the Miro REST API."""

from __future__ import annotations

import fcntl
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_state_path

from .errors import MiroCredentialError

_MAX_TOKEN_BYTES = 8 * 1024
_MIN_TOKEN_CHARS = 20
_MAX_TOKEN_CHARS = 4096


@dataclass(frozen=True)
class MiroRestSettings:
    """Connection settings for a separately authorized Miro REST application."""

    api_origin: str = "https://api.miro.com"
    network_timeout_seconds: float = 30.0
    state_root: Path = field(
        default_factory=lambda: user_state_path("schauwerk", ensure_exists=False) / "miro-rest"
    )

    @property
    def token_path(self) -> Path:
        return self.state_root / "access-token"

    @property
    def lock_path(self) -> Path:
        return self.state_root / "access-token.lock"


class MiroRestTokenStorage:
    """Store one REST access token without sharing the MCP OAuth state."""

    def __init__(self, settings: MiroRestSettings | None = None) -> None:
        self.settings = settings or MiroRestSettings()

    @staticmethod
    def _private_regular(path: Path, *, label: str) -> os.stat_result:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MiroCredentialError(f"{label} must be a regular non-symlink file")
        if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
            raise MiroCredentialError(f"{label} must be owner-controlled and unlinked")
        if metadata.st_mode & 0o077:
            raise MiroCredentialError(f"{label} must have mode 0600")
        if metadata.st_size < 1 or metadata.st_size > _MAX_TOKEN_BYTES:
            raise MiroCredentialError(f"{label} size is outside the supported bound")
        return metadata

    def _ensure_root(self) -> Path:
        root = self.settings.state_root.expanduser().absolute()
        if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
            raise MiroCredentialError("Miro REST state root is unsafe")
        try:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            metadata = root.lstat()
        except OSError as exc:
            raise MiroCredentialError("Miro REST state root is unavailable") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise MiroCredentialError("Miro REST state root must be owner-only")
        return root

    @staticmethod
    def _open_directory(path: Path) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise MiroCredentialError("Miro REST state root is unavailable") from exc
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            os.close(descriptor)
            raise MiroCredentialError("Miro REST state root must be owner-only")
        return descriptor

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        root = self._ensure_root()
        directory_descriptor = self._open_directory(root)
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            try:
                descriptor = os.open(
                    self.settings.lock_path.name,
                    flags,
                    0o600,
                    dir_fd=directory_descriptor,
                )
            except OSError as exc:
                raise MiroCredentialError("Miro REST credential lock is unavailable") from exc
            try:
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or metadata.st_nlink != 1
                    or metadata.st_mode & 0o077
                ):
                    raise MiroCredentialError("Miro REST credential lock is unsafe")
                mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                try:
                    fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise MiroCredentialError("Miro REST credential state is busy") from exc
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_descriptor)

    @staticmethod
    def _validate_token_bytes(payload: bytes) -> str:
        if b"\x00" in payload:
            raise MiroCredentialError("Miro REST credential contains invalid bytes")
        try:
            value = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MiroCredentialError("Miro REST credential must be UTF-8") from exc
        token = value.rstrip("\r\n")
        if value not in {token, token + "\n", token + "\r\n"}:
            raise MiroCredentialError("Miro REST credential must contain one line")
        if "\n" in token or "\r" in token:
            raise MiroCredentialError("Miro REST credential must contain one line")
        if not _MIN_TOKEN_CHARS <= len(token) <= _MAX_TOKEN_CHARS:
            raise MiroCredentialError("Miro REST credential length is invalid")
        if any(character.isspace() or ord(character) < 0x21 for character in token):
            raise MiroCredentialError("Miro REST credential contains whitespace or controls")
        return token

    @staticmethod
    def _read_private(path: Path, *, label: str) -> tuple[bytes, os.stat_result]:
        candidate = path.expanduser().absolute()
        if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
            raise MiroCredentialError(f"{label} path is unsafe")
        metadata = MiroRestTokenStorage._private_regular(candidate, label=label)
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(candidate, flags)
        except OSError as exc:
            raise MiroCredentialError(f"{label} is unreadable") from exc
        try:
            opened = os.fstat(descriptor)
            identity = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
            observed = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            if identity != observed or opened.st_nlink != 1:
                raise MiroCredentialError(f"{label} changed during read")
            payload = bytearray()
            while len(payload) <= _MAX_TOKEN_BYTES:
                chunk = os.read(
                    descriptor,
                    min(4096, _MAX_TOKEN_BYTES + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) > _MAX_TOKEN_BYTES:
                raise MiroCredentialError(f"{label} exceeds the supported bound")
            return bytes(payload), opened
        finally:
            os.close(descriptor)

    def read_access_token(self) -> str:
        with self._lock(exclusive=False):
            try:
                payload, _metadata = self._read_private(
                    self.settings.token_path,
                    label="Miro REST credential",
                )
            except FileNotFoundError as exc:
                raise MiroCredentialError("Miro REST credential is not installed") from exc
            return self._validate_token_bytes(payload)

    def summary(self) -> dict[str, object]:
        path = self.settings.token_path
        root = self.settings.state_root.expanduser().absolute()
        if not root.exists() and not root.is_symlink():
            return {
                "path": str(path),
                "exists": False,
                "secure": True,
                "bytes": 0,
            }
        with self._lock(exclusive=False):
            try:
                payload, metadata = self._read_private(path, label="Miro REST credential")
            except FileNotFoundError:
                return {
                    "path": str(path),
                    "exists": False,
                    "secure": True,
                    "bytes": 0,
                }
            self._validate_token_bytes(payload)
            return {
                "path": str(path),
                "exists": True,
                "secure": True,
                "bytes": metadata.st_size,
            }

    def install_from_file(self, source_path: Path, *, replace: bool = False) -> dict[str, object]:
        source = source_path.expanduser().absolute()
        destination = self.settings.token_path.expanduser().absolute()
        if source in {destination, self.settings.lock_path.expanduser().absolute()}:
            raise MiroCredentialError("Miro REST credential source collides with managed state")
        payload, _metadata = self._read_private(source, label="credential source")
        token = self._validate_token_bytes(payload)
        normalized = (token + "\n").encode()
        root = self._ensure_root()
        destination_existed = False
        with self._lock(exclusive=True):
            destination_existed = destination.exists() or destination.is_symlink()
            if destination_existed:
                self._private_regular(destination, label="Miro REST credential")
                if not replace:
                    raise MiroCredentialError(
                        "Miro REST credential already exists; use explicit replacement"
                    )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".access-token.", suffix=".tmp", dir=root
            )
            temporary = Path(temporary_name)
            try:
                os.fchmod(descriptor, 0o600)
                offset = 0
                while offset < len(normalized):
                    written = os.write(descriptor, normalized[offset:])
                    if written <= 0:
                        raise OSError("short credential write")
                    offset += written
                os.fsync(descriptor)
                os.close(descriptor)
                descriptor = -1
                os.replace(temporary, destination)
                os.chmod(destination, 0o600)
                directory_descriptor = self._open_directory(root)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            except Exception:
                if descriptor >= 0:
                    os.close(descriptor)
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                raise
        result = self.summary()
        result["installed"] = True
        result["replaced"] = destination_existed
        return result
