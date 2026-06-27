"""High-level direct Miro MCP client used by the Schauwerk CLI."""

from __future__ import annotations

from typing import Any

from .auth import interactive_handlers
from .credentials import FileTokenStorage, write_json_owner_only
from .discovery import discover_tools
from .errors import MiroCredentialError, redact_text
from .models import MiroSettings, ToolCatalogue


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
            credentials = {
                "path": str(self.settings.credentials_path),
                "exists": self.settings.credentials_path.exists(),
                "secure": False,
                "has_tokens": False,
                "has_client_info": False,
            }
            credential_error = redact_text(exc)
        return {
            "server_url": self.settings.server_url,
            "scope": self.settings.scope,
            "redirect_uri": self.settings.redirect_uri,
            "credentials": credentials,
            "credential_error": credential_error,
            "catalogue_path": str(self.settings.catalogue_path),
            "catalogue_exists": self.settings.catalogue_path.is_file(),
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

    def cached_tools(self) -> dict[str, Any]:
        path = self.settings.catalogue_path
        if not path.is_file() or path.is_symlink():
            raise MiroCredentialError("No safe cached tool catalogue exists")
        if path.stat().st_mode & 0o077:
            raise MiroCredentialError("Cached tool catalogue has unsafe permissions")
        value = __import__("json").loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise MiroCredentialError("Cached tool catalogue is invalid")
        return value

    def logout(self) -> dict[str, bool]:
        state_removed = self.storage.clear()
        path = self.settings.catalogue_path
        cache_removed = False
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise MiroCredentialError("Refusing unsafe cache path")
            path.unlink()
            cache_removed = True
        return {"state_removed": state_removed, "cache_removed": cache_removed}
