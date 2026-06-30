from __future__ import annotations

import asyncio

from schauwerk.surfaces.miro.client import MiroMCPClient
from schauwerk.surfaces.miro.errors import MiroCredentialError
from schauwerk.surfaces.miro.models import ToolCatalogue


def test_live_status_reports_success(monkeypatch) -> None:
    client = MiroMCPClient()

    async def fake_tools():
        return ToolCatalogue(
            protocol_version="2025-06-18",
            server_name="Miro MCP",
            server_version="1",
            tools=(),
        )

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.live_status())

    assert result == {
        "checked": True,
        "ok": True,
        "renewal_required": False,
        "server_name": "Miro MCP",
        "tool_count": 0,
    }


def test_live_status_reports_renewal_required(monkeypatch) -> None:
    client = MiroMCPClient()

    async def fake_tools():
        raise MiroCredentialError("Miro login must be renewed")

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.live_status())

    assert result["checked"] is True
    assert result["ok"] is False
    assert result["renewal_required"] is True
    assert "renewed" in result["error"]
