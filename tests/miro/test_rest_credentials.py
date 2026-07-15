from __future__ import annotations

import os
from pathlib import Path

import pytest

from schauwerk.surfaces.miro.errors import MiroCredentialError
from schauwerk.surfaces.miro.rest_credentials import (
    MiroRestSettings,
    MiroRestTokenStorage,
)

TOKEN = "rest-token-abcdefghijklmnopqrstuvwxyz-0123456789"


def storage(tmp_path: Path) -> MiroRestTokenStorage:
    return MiroRestTokenStorage(MiroRestSettings(state_root=tmp_path / "rest-state"))


def private_source(tmp_path: Path, value: str = TOKEN) -> Path:
    path = tmp_path / "source-token"
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_status_is_sanitized_and_missing_by_default(tmp_path: Path) -> None:
    active = storage(tmp_path)
    result = active.summary()

    assert result["exists"] is False
    assert result["secure"] is True
    assert TOKEN not in repr(result)
    assert "reference_digest" not in result
    assert active.settings.state_root.exists() is False


def test_replace_flag_reports_only_an_actual_replacement(tmp_path: Path) -> None:
    active = MiroRestTokenStorage(
        MiroRestSettings(state_root=tmp_path / "fresh-rest-state")
    )
    source = private_source(tmp_path)
    receipt = active.install_from_file(source, replace=True)
    assert receipt["replaced"] is False


def test_install_is_atomic_private_and_requires_explicit_replace(tmp_path: Path) -> None:
    active = storage(tmp_path)
    source = private_source(tmp_path)

    receipt = active.install_from_file(source)

    assert receipt["installed"] is True
    assert receipt["replaced"] is False
    assert TOKEN not in repr(receipt)
    assert active.read_access_token() == TOKEN
    assert active.settings.token_path.stat().st_mode & 0o777 == 0o600
    assert active.settings.token_path.stat().st_nlink == 1
    assert active.settings.state_root.stat().st_mode & 0o777 == 0o700

    with pytest.raises(MiroCredentialError, match="explicit replacement"):
        active.install_from_file(source)

    replacement = private_source(tmp_path, TOKEN + "-new")
    replacement.rename(tmp_path / "replacement-token")
    replacement = tmp_path / "replacement-token"
    receipt = active.install_from_file(replacement, replace=True)
    assert receipt["replaced"] is True
    assert active.read_access_token() == TOKEN + "-new"


def test_install_rejects_unsafe_source_shapes(tmp_path: Path) -> None:
    active = storage(tmp_path)
    public = private_source(tmp_path)
    public.chmod(0o644)
    with pytest.raises(MiroCredentialError, match="mode 0600"):
        active.install_from_file(public)

    source = private_source(tmp_path)
    link = tmp_path / "token-link"
    link.symlink_to(source)
    with pytest.raises(MiroCredentialError, match="unsafe"):
        active.install_from_file(link)

    hardlink = tmp_path / "token-hardlink"
    os.link(source, hardlink)
    with pytest.raises(MiroCredentialError, match="unlinked"):
        active.install_from_file(source)


def test_install_rejects_multiline_or_short_tokens(tmp_path: Path) -> None:
    active = storage(tmp_path)
    multiline = private_source(tmp_path, TOKEN + "\nsecond-line")
    with pytest.raises(MiroCredentialError, match="one line"):
        active.install_from_file(multiline)

    short = private_source(tmp_path, "too-short")
    short.rename(tmp_path / "short-token")
    with pytest.raises(MiroCredentialError, match="length"):
        active.install_from_file(tmp_path / "short-token")
