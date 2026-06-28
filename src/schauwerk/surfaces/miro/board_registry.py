"""Owner-only local allowlist for Miro boards."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .credentials import write_json_owner_only
from .errors import MiroCredentialError

_ALIAS = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")


@dataclass(frozen=True)
class AllowlistedBoard:
    alias: str
    reference_digest: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def validate_alias(alias: str) -> str:
    value = alias.strip().lower()
    if not _ALIAS.fullmatch(value):
        raise ValueError(
            "alias must be 1-64 lowercase letters, digits, dots, underscores, or hyphens"
        )
    return value


def validate_board_url(value: str) -> str:
    url = value.strip()
    if not url.startswith("https://miro.com/app/board/"):
        raise ValueError("board URL must use https://miro.com/app/board/")
    return url


def reference_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _read_owner_only(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MiroCredentialError("Board allowlist path is unsafe")
    if metadata.st_mode & 0o077:
        raise MiroCredentialError("Board allowlist must have mode 0600")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MiroCredentialError("Board allowlist is unreadable or corrupt") from exc
    if not isinstance(document, dict):
        raise MiroCredentialError("Board allowlist must contain a JSON object")
    return document


class BoardAllowlist:
    """Map local aliases to private board URLs without echoing those URLs."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _document(self) -> dict[str, Any]:
        document = _read_owner_only(self.path)
        if not document:
            return {"schema_version": 1, "boards": {}}
        if document.get("schema_version") != 1 or not isinstance(document.get("boards"), dict):
            raise MiroCredentialError("Board allowlist has an unsupported shape")
        return document

    def add(self, alias: str, miro_url: str, *, replace: bool = False) -> AllowlistedBoard:
        name = validate_alias(alias)
        url = validate_board_url(miro_url)
        boards = dict(self._document()["boards"])
        current = boards.get(name)
        if current is not None:
            if not isinstance(current, Mapping) or not isinstance(current.get("miro_url"), str):
                raise MiroCredentialError("Board allowlist contains an invalid entry")
            current_url = validate_board_url(current["miro_url"])
            if current_url != url and not replace:
                raise MiroCredentialError(
                    "Board alias already refers to a different board; use --replace explicitly"
                )
            if current_url == url:
                return AllowlistedBoard(name, reference_digest(url))
        boards[name] = {"miro_url": url}
        write_json_owner_only(
            self.path,
            {"schema_version": 1, "boards": dict(sorted(boards.items()))},
        )
        return AllowlistedBoard(name, reference_digest(url))

    def remove(self, alias: str) -> bool:
        name = validate_alias(alias)
        boards = dict(self._document()["boards"])
        removed = boards.pop(name, None) is not None
        if removed:
            write_json_owner_only(
                self.path,
                {"schema_version": 1, "boards": dict(sorted(boards.items()))},
            )
        return removed

    def resolve(self, alias: str) -> str:
        name = validate_alias(alias)
        entry = self._document()["boards"].get(name)
        if not isinstance(entry, Mapping) or not isinstance(entry.get("miro_url"), str):
            raise MiroCredentialError(f"Board alias is not allowlisted: {name}")
        return validate_board_url(entry["miro_url"])

    def list(self) -> tuple[AllowlistedBoard, ...]:
        result = []
        for alias, entry in sorted(self._document()["boards"].items()):
            if isinstance(entry, Mapping) and isinstance(entry.get("miro_url"), str):
                result.append(AllowlistedBoard(alias, reference_digest(entry["miro_url"])))
        return tuple(result)
