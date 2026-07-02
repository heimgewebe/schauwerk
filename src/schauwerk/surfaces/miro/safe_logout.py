"""Symlink-safe cleanup for local Miro client state."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import MiroCredentialError

if TYPE_CHECKING:
    from .client import MiroMCPClient


def _unlink_entry(path: Path, *, label: str) -> bool:
    """Unlink a regular file or a symlink itself, never the symlink target."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
        raise MiroCredentialError(f"Refusing unsafe {label} path")
    path.unlink()
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return True


def safe_logout(client: MiroMCPClient) -> dict[str, bool]:
    """Clear local state while handling broken and live symlinks safely."""
    state_path = client.storage.path
    if state_path.is_symlink():
        state_removed = _unlink_entry(state_path, label="OAuth state")
    else:
        state_removed = client.storage.clear()
    cache_removed = _unlink_entry(client.settings.catalogue_path, label="tool catalogue")
    auth_health_removed = _unlink_entry(
        client.settings.auth_health_path, label="auth health receipt"
    )
    return {
        "state_removed": state_removed,
        "cache_removed": cache_removed,
        "auth_health_removed": auth_health_removed,
    }
