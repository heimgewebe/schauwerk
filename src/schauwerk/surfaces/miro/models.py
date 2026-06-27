"""Provider-neutral data returned by the direct Miro MCP client."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_state_path


@dataclass(frozen=True)
class MiroSettings:
    """Stable connection settings for the canonical Schauwerk Miro client."""

    server_url: str = "https://mcp.miro.com/"
    scope: str = "boards:read boards:write"
    callback_host: str = "127.0.0.1"
    callback_port: int = 41739
    callback_path: str = "/callback"
    client_name: str = "Schauwerk Miro MCP Client"
    timeout_seconds: float = 60.0
    state_root: Path = field(
        default_factory=lambda: user_state_path("schauwerk", ensure_exists=False) / "miro"
    )

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.callback_host}:{self.callback_port}{self.callback_path}"

    @property
    def credentials_path(self) -> Path:
        return self.state_root / "oauth.json"

    @property
    def catalogue_path(self) -> Path:
        return self.state_root / "tools.json"


@dataclass(frozen=True)
class ToolInfo:
    """Normalized MCP tool metadata without provider runtime objects."""

    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolCatalogue:
    """Normalized result of MCP initialization and paginated tool discovery."""

    protocol_version: str
    server_name: str
    server_version: str
    tools: tuple[ToolInfo, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "server_name": self.server_name,
            "server_version": self.server_version,
            "tool_count": len(self.tools),
            "tools": [tool.to_dict() for tool in self.tools],
        }
