from __future__ import annotations

import json
import os

import pytest

from schauwerk.surfaces.miro.board_registry import BoardAllowlist
from schauwerk.surfaces.miro.errors import MiroCredentialError

URL = "https://miro.com/app/board/uXjVFixture=/"


def test_allowlist_add_list_resolve_and_remove(tmp_path) -> None:
    path = tmp_path / "boards.json"
    allowlist = BoardAllowlist(path)

    entry = allowlist.add("fixture", URL)

    assert entry.alias == "fixture"
    assert URL not in repr(entry)
    assert allowlist.resolve("fixture") == URL
    assert allowlist.list() == (entry,)
    assert path.stat().st_mode & 0o077 == 0
    assert allowlist.remove("fixture") is True
    assert allowlist.list() == ()


def test_allowlist_output_never_contains_url(tmp_path) -> None:
    allowlist = BoardAllowlist(tmp_path / "boards.json")
    allowlist.add("fixture", URL)

    encoded = json.dumps([entry.to_dict() for entry in allowlist.list()])

    assert URL not in encoded
    assert "reference_digest" in encoded


def test_allowlist_rejects_symlink(tmp_path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"schema_version": 1, "boards": {}}\n', encoding="utf-8")
    path = tmp_path / "boards.json"
    path.symlink_to(target)

    with pytest.raises(MiroCredentialError, match="unsafe"):
        BoardAllowlist(path).list()


def test_allowlist_rejects_group_readable_file(tmp_path) -> None:
    path = tmp_path / "boards.json"
    path.write_text('{"schema_version": 1, "boards": {}}\n', encoding="utf-8")
    os.chmod(path, 0o640)

    with pytest.raises(MiroCredentialError, match="0600"):
        BoardAllowlist(path).list()


def test_allowlist_requires_explicit_alias_replacement(tmp_path) -> None:
    allowlist = BoardAllowlist(tmp_path / "boards.json")
    other = "https://miro.com/app/board/uXjVOther=/"
    allowlist.add("fixture", URL)

    with pytest.raises(MiroCredentialError, match="--replace"):
        allowlist.add("fixture", other)

    assert allowlist.resolve("fixture") == URL
    allowlist.add("fixture", other, replace=True)
    assert allowlist.resolve("fixture") == other
