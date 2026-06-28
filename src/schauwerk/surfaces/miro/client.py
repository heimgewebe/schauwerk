"""High-level direct Miro MCP client used by the Schauwerk CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .auth import interactive_handlers
from .board_registry import AllowlistedBoard, BoardAllowlist
from .credentials import FileTokenStorage, write_json_owner_only
from .discovery import discover_tools
from .errors import MiroCredentialError, redact_text
from .inspection import ReadOnlyInspection
from .models import MiroSettings, ToolCatalogue
from .readonly import run_read_only_inspection
from .safe_logout import safe_logout
from .snapshot_model import SnapshotReceipt
from .snapshot_runtime import run_verified_snapshot


class MiroMCPClient:
    """Own local auth state and expose non-model-dependent Miro operations."""

    def __init__(
        self,
        settings: MiroSettings | None = None,
        storage: FileTokenStorage | None = None,
    ) -> None:
        self.settings = settings or MiroSettings()
        self.storage = storage or FileTokenStorage(self.settings.credentials_path)

    def status(self) -> dict[str, Any]:
        """Return local authorization state without network access or login."""
        try:
            credentials = self.storage.summary()
            credential_error = None
        except MiroCredentialError as exc:
            credentials_path = self.settings.credentials_path
            credentials = {
                "path": str(credentials_path),
                "exists": credentials_path.exists() or credentials_path.is_symlink(),
                "secure": False,
                "has_tokens": False,
                "has_client_info": False,
            }
            credential_error = redact_text(exc)
        catalogue_path = self.settings.catalogue_path
        return {
            "server_url": self.settings.server_url,
            "scope": self.settings.scope,
            "redirect_uri": self.settings.redirect_uri,
            "credentials": credentials,
            "credential_error": credential_error,
            "catalogue_path": str(catalogue_path),
            "catalogue_exists": (catalogue_path.is_file() and not catalogue_path.is_symlink()),
            "authorized_locally": bool(
                credential_error is None
                and credentials["has_tokens"]
                and credentials["has_client_info"]
            ),
        }

    async def login(
        self, *, open_browser: bool = True, manual_callback: bool = False
    ) -> ToolCatalogue:
        async with interactive_handlers(
            self.settings,
            open_browser=open_browser,
            manual_callback=manual_callback,
        ) as handlers:
            catalogue = await discover_tools(self.settings, self.storage, *handlers)
        write_json_owner_only(self.settings.catalogue_path, catalogue.to_dict())
        return catalogue

    async def tools(self) -> ToolCatalogue:
        async def stop(_value: str = "") -> tuple[str, str | None]:
            raise MiroCredentialError("Miro login must be renewed")

        result = await discover_tools(self.settings, self.storage, stop, stop)
        write_json_owner_only(self.settings.catalogue_path, result.to_dict())
        return result

    async def inspect(
        self,
        *,
        query: str = "",
        owned_by_me: bool = False,
        limit: int = 20,
        max_pages: int = 5,
    ) -> ReadOnlyInspection:
        """Run the sanitized, mutation-free operational inspection."""
        return await run_read_only_inspection(
            self.settings,
            self.storage,
            query=query,
            owned_by_me=owned_by_me,
            limit=limit,
            max_pages=max_pages,
        )

    def board_add(self, alias: str, miro_url: str, *, replace: bool = False) -> AllowlistedBoard:
        return BoardAllowlist(self.settings.board_allowlist_path).add(
            alias, miro_url, replace=replace
        )

    def board_list(self) -> tuple[AllowlistedBoard, ...]:
        return BoardAllowlist(self.settings.board_allowlist_path).list()

    def board_remove(self, alias: str) -> bool:
        return BoardAllowlist(self.settings.board_allowlist_path).remove(alias)

    async def snapshot(
        self,
        *,
        alias: str,
        output_path: Path | None = None,
        item_limit: int = 100,
        comment_limit: int = 50,
        max_pages: int = 20,
        include_comments: bool = True,
    ) -> SnapshotReceipt:
        return await run_verified_snapshot(
            self.settings,
            self.storage,
            alias=alias,
            output_path=output_path,
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )

    def cached_tools(self) -> dict[str, Any]:
        path = self.settings.catalogue_path
        if not path.is_file() or path.is_symlink():
            raise MiroCredentialError("No safe cached tool catalogue exists")
        if path.stat().st_mode & 0o077:
            raise MiroCredentialError("Cached tool catalogue has unsafe permissions")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MiroCredentialError("Cached tool catalogue is unreadable") from exc
        if not isinstance(value, dict):
            raise MiroCredentialError("Cached tool catalogue is invalid")
        return value

    def logout(self) -> dict[str, bool]:
        """Remove local client state without following symlinks."""
        return safe_logout(self)
