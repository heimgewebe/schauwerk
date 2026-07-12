"""High-level direct Miro MCP client used by the Schauwerk CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .auth import interactive_handlers
from .board_registry import AllowlistedBoard, BoardAllowlist
from .credentials import FileTokenStorage, write_json_owner_only
from .discovery import discover_tools
from .errors import MiroAuthorizationRequired, MiroCredentialError, MiroError, redact_text
from .inspection import ReadOnlyInspection
from .layout_runtime import LayoutReceipt, run_layout_create
from .live_test_runtime import (
    BoardCreateReceipt,
    LayoutReadSummary,
    run_board_create,
    run_layout_read_summary,
)
from .models import MiroSettings, ToolCatalogue
from .readonly import run_read_only_inspection
from .runtime import quiet_provider_stderr
from .safe_logout import safe_logout
from .snapshot_model import SnapshotReceipt
from .snapshot_runtime import run_verified_snapshot

MIRO_AUTH_HEALTH_SCHEMA_VERSION = "miro-auth-health.v1"
MIRO_AUTH_HISTORY_SCHEMA_VERSION = "miro-auth-history.v1"
MIRO_AUTH_DOCTOR_SCHEMA_VERSION = "miro-auth-doctor.v1"


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
        local_state_present = bool(
            credential_error is None
            and credentials["has_tokens"]
            and credentials["has_client_info"]
        )
        return {
            "server_url": self.settings.server_url,
            "scope": self.settings.scope,
            "redirect_uri": self.settings.redirect_uri,
            "credentials": credentials,
            "credential_error": credential_error,
            "catalogue_path": str(catalogue_path),
            "catalogue_exists": (catalogue_path.is_file() and not catalogue_path.is_symlink()),
            "auth_health_path": str(self.settings.auth_health_path),
            "auth_health_exists": (
                self.settings.auth_health_path.is_file()
                and not self.settings.auth_health_path.is_symlink()
            ),
            "auth_history_path": str(self.settings.auth_history_path),
            "auth_history_exists": (
                self.settings.auth_history_path.is_file()
                and not self.settings.auth_history_path.is_symlink()
            ),
            "local_state_present": local_state_present,
            "authorized_locally": local_state_present,
            "authorized_locally_note": (
                "local OAuth state only; use `miro status --live` or `miro doctor` "
                "to prove live authorization"
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

    def cached_auth_health(self) -> dict[str, Any] | None:
        """Return the latest persisted live-auth health receipt, if present."""
        path = self.settings.auth_health_path
        try:
            if path.is_symlink():
                raise MiroCredentialError("Cached auth health receipt is unsafe")
            if not path.exists():
                return None
            if not path.is_file():
                raise MiroCredentialError("Cached auth health receipt is unsafe")
            if path.stat().st_mode & 0o077:
                raise MiroCredentialError("Cached auth health receipt has unsafe permissions")
            value = json.loads(path.read_text(encoding="utf-8"))
        except MiroCredentialError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MiroCredentialError("Cached auth health receipt is unreadable") from exc
        if not isinstance(value, dict):
            raise MiroCredentialError("Cached auth health receipt is invalid")
        if value.get("schema_version") != MIRO_AUTH_HEALTH_SCHEMA_VERSION:
            raise MiroCredentialError("Cached auth health receipt has an unsupported schema")
        return value

    def cached_auth_history(self) -> dict[str, Any]:
        """Return bounded auth-health history without exposing OAuth material."""
        path = self.settings.auth_history_path
        try:
            if path.is_symlink():
                raise MiroCredentialError("Cached auth history is unsafe")
            if not path.exists():
                return {"schema_version": MIRO_AUTH_HISTORY_SCHEMA_VERSION, "entries": []}
            if not path.is_file():
                raise MiroCredentialError("Cached auth history is unsafe")
            if path.stat().st_mode & 0o077:
                raise MiroCredentialError("Cached auth history has unsafe permissions")
            value = json.loads(path.read_text(encoding="utf-8"))
        except MiroCredentialError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MiroCredentialError("Cached auth history is unreadable") from exc
        if not isinstance(value, dict):
            raise MiroCredentialError("Cached auth history is invalid")
        if value.get("schema_version") != MIRO_AUTH_HISTORY_SCHEMA_VERSION:
            raise MiroCredentialError("Cached auth history has an unsupported schema")
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise MiroCredentialError("Cached auth history is invalid")
        return value

    def _persist_auth_history(self, receipt: dict[str, Any], *, keep: int = 100) -> dict[str, Any]:
        history = self.cached_auth_history()
        entries = [entry for entry in history.get("entries", []) if isinstance(entry, dict)]
        entries.append(receipt)
        value = {
            "schema_version": MIRO_AUTH_HISTORY_SCHEMA_VERSION,
            "entries": entries[-keep:],
        }
        write_json_owner_only(self.settings.auth_history_path, value)
        return value

    def _auth_history_report(self, history: dict[str, Any]) -> dict[str, Any]:
        entries = [entry for entry in history.get("entries", []) if isinstance(entry, dict)]
        return {
            "path": str(self.settings.auth_history_path),
            "count": len(entries),
            "recent": entries[-5:],
        }

    def _recommend_next_command(
        self, local_status: dict[str, Any], live_status: dict[str, Any]
    ) -> str:
        if live_status.get("checked") and live_status.get("ok") is True:
            return "Proceed with live Miro operations."
        if local_status.get("credential_error"):
            return "Inspect local OAuth state permissions, then run `schauwerk miro login`."
        if not local_status.get("local_state_present"):
            return "Run `schauwerk miro login --no-browser --manual-callback --json`."
        if not live_status.get("checked"):
            return "Run `schauwerk miro doctor --json` before live board operations."
        if live_status.get("renewal_required") is True:
            return (
                "Run `schauwerk miro login --no-browser --manual-callback --json`, "
                "then rerun `schauwerk miro doctor --json`."
            )
        return "Inspect the live MCP/network error before live board operations."

    def _persist_auth_health(
        self, live_status: dict[str, Any], local_status: dict[str, Any]
    ) -> dict[str, Any]:
        checked_live = bool(live_status.get("checked"))
        live_authorized = live_status.get("ok") if checked_live else None
        renewal_required = live_status.get("renewal_required") if checked_live else None
        receipt = {
            "schema_version": MIRO_AUTH_HEALTH_SCHEMA_VERSION,
            "observed_at": datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "local_state_present": bool(local_status.get("local_state_present")),
            "live_authorized": live_authorized,
            "live_authorized_known": checked_live,
            "renewal_required": renewal_required,
            "renewal_required_known": checked_live,
            "safe_for_live_board_operations": live_authorized is True,
            "recommended_next_command": self._recommend_next_command(local_status, live_status),
            "live": live_status,
        }
        write_json_owner_only(self.settings.auth_health_path, receipt)
        return receipt

    async def live_status(self) -> dict[str, Any]:
        """Check whether stored Miro credentials work against the live MCP server."""
        try:
            with quiet_provider_stderr():
                catalogue = await self.tools()
        except MiroError as exc:
            return {
                "checked": True,
                "ok": False,
                "renewal_required": isinstance(
                    exc, (MiroAuthorizationRequired, MiroCredentialError)
                ),
                "error": redact_text(exc),
            }
        return {
            "checked": True,
            "ok": True,
            "renewal_required": False,
            "server_name": catalogue.server_name,
            "tool_count": len(catalogue.tools),
        }

    async def doctor(self, *, check_live: bool = True) -> dict[str, Any]:
        """Report local and live Miro auth state with an operational recommendation."""
        local_status = self.status()
        live_status = await self.live_status() if check_live else {"checked": False}
        checked_live = bool(live_status.get("checked"))
        live_authorized = live_status.get("ok") if checked_live else None
        renewal_required = live_status.get("renewal_required") if checked_live else None
        health_error = None
        auth_history_error = None
        auth_history = None
        if check_live:
            try:
                last_health = self._persist_auth_health(live_status, local_status)
                local_status["auth_health_exists"] = True
            except MiroCredentialError as exc:
                last_health = None
                health_error = redact_text(exc)
            if last_health is not None:
                try:
                    auth_history = self._persist_auth_history(last_health)
                    local_status["auth_history_exists"] = True
                except MiroCredentialError as exc:
                    auth_history_error = redact_text(exc)
        else:
            try:
                last_health = self.cached_auth_health()
            except MiroCredentialError as exc:
                last_health = None
                health_error = redact_text(exc)
            try:
                auth_history = self.cached_auth_history()
            except MiroCredentialError as exc:
                auth_history_error = redact_text(exc)
        auth_history_report = (
            self._auth_history_report(auth_history) if auth_history is not None else None
        )
        return {
            "schema_version": MIRO_AUTH_DOCTOR_SCHEMA_VERSION,
            "checked_live": checked_live,
            "live_authorized_known": checked_live,
            "renewal_required_known": checked_live,
            "local_state_present": bool(local_status.get("local_state_present")),
            "live_authorized": live_authorized,
            "renewal_required": renewal_required,
            "safe_for_live_board_operations": live_authorized is True,
            "recommended_next_command": self._recommend_next_command(local_status, live_status),
            "local": local_status,
            "live": live_status,
            "last_health": last_health,
            "health_error": health_error,
            "auth_history": auth_history_report,
            "auth_history_error": auth_history_error,
        }

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

    async def layout_create(
        self,
        *,
        alias: str,
        dsl: str,
        invocation_source: str = "schauwerk",
    ) -> LayoutReceipt:
        return await run_layout_create(
            self.settings,
            self.storage,
            alias=alias,
            dsl=dsl,
            invocation_source=invocation_source,
        )

    async def board_create(self, **kwargs: Any) -> BoardCreateReceipt:
        return await run_board_create(self.settings, self.storage, **kwargs)

    async def layout_read_summary(self, **kwargs: Any) -> LayoutReadSummary:
        return await run_layout_read_summary(self.settings, self.storage, **kwargs)

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
