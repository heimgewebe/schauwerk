"""Restrictive, atomic OAuth state storage for the Miro MCP client."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import ValidationError

from .errors import MiroCredentialError


class FileTokenStorage(TokenStorage):
    """Persist MCP OAuth material in one owner-only JSON file.

    The object never exposes token values through ``repr`` or status methods.
    Writes are serialized, fsynced, and atomically replaced in the same directory.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def __repr__(self) -> str:
        return f"FileTokenStorage(path={self.path!s})"

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        self._ensure_parent()
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _assert_owner_only(path: Path) -> None:
        if path.stat().st_mode & 0o077:
            raise MiroCredentialError(
                f"OAuth state has unsafe permissions: {path}; expected mode 0600"
            )

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        self._assert_owner_only(self.path)
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MiroCredentialError("OAuth state is unreadable or corrupt") from exc
        if not isinstance(value, dict):
            raise MiroCredentialError("OAuth state must contain a JSON object")
        return value

    def _write_unlocked(self, value: dict[str, Any]) -> None:
        self._ensure_parent()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    def _read(self) -> dict[str, Any]:
        with self._lock(exclusive=False):
            return self._read_unlocked()

    def _update(self, key: str, value: dict[str, Any]) -> None:
        with self._lock(exclusive=True):
            document = self._read_unlocked()
            document[key] = value
            self._write_unlocked(document)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        if raw is None:
            return None
        try:
            return OAuthToken.model_validate(raw)
        except ValidationError as exc:
            raise MiroCredentialError("Stored OAuth tokens are invalid") from exc

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._update("tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        if raw is None:
            return None
        try:
            return OAuthClientInformationFull.model_validate(raw)
        except ValidationError as exc:
            raise MiroCredentialError("Stored OAuth client registration is invalid") from exc

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._update("client_info", client_info.model_dump(mode="json", exclude_none=True))

    def summary(self) -> dict[str, Any]:
        """Return credential presence and permission metadata, never values."""
        document = self._read()
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "secure": not self.path.exists() or not bool(self.path.stat().st_mode & 0o077),
            "has_tokens": isinstance(document.get("tokens"), dict),
            "has_client_info": isinstance(document.get("client_info"), dict),
        }

    def clear(self) -> bool:
        """Remove only this client's state and return whether it existed."""
        with self._lock(exclusive=True):
            existed = self.path.exists()
            if existed:
                self._assert_owner_only(self.path)
                self.path.unlink()
                directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return existed


def write_json_owner_only(path: Path, value: dict[str, Any]) -> None:
    """Write non-secret state with the same atomic owner-only discipline."""
    storage = FileTokenStorage(path)
    with storage._lock(exclusive=True):
        storage._write_unlocked(value)
