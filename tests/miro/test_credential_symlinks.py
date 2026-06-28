from __future__ import annotations

import pytest

from schauwerk.surfaces.miro.credentials import FileTokenStorage
from schauwerk.surfaces.miro.errors import MiroCredentialError


def test_summary_rejects_live_state_symlink(tmp_path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    path = tmp_path / "oauth.json"
    path.symlink_to(target)

    with pytest.raises(MiroCredentialError, match="must not be a symlink"):
        FileTokenStorage(path).summary()

    assert target.read_text(encoding="utf-8") == "{}\n"


def test_summary_rejects_broken_state_symlink(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.symlink_to(tmp_path / "missing.json")

    with pytest.raises(MiroCredentialError, match="must not be a symlink"):
        FileTokenStorage(path).summary()


def test_lock_symlink_is_rejected_without_touching_target(tmp_path) -> None:
    storage = FileTokenStorage(tmp_path / "oauth.json")
    target = tmp_path / "lock-target"
    target.write_text("preserve\n", encoding="utf-8")
    storage.lock_path.symlink_to(target)

    with pytest.raises(MiroCredentialError, match="lock path is unsafe"):
        storage.summary()

    assert target.read_text(encoding="utf-8") == "preserve\n"
