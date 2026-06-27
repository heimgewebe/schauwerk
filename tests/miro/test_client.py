from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

from schauwerk.surfaces.miro import client as client_module
from schauwerk.surfaces.miro.client import MiroMCPClient
from schauwerk.surfaces.miro.models import MiroSettings, ToolCatalogue, ToolInfo


def test_status_without_state_is_local_and_false(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    status = MiroMCPClient(settings=settings).status()
    assert status["authorized_locally"] is False
    assert status["credentials"]["exists"] is False
    assert status["catalogue_exists"] is False


def test_status_reports_corrupt_state(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    settings.state_root.mkdir(parents=True)
    settings.credentials_path.write_text("not-json", encoding="utf-8")
    os.chmod(settings.credentials_path, 0o600)

    status = MiroMCPClient(settings=settings).status()
    assert status["authorized_locally"] is False
    assert status["credential_error"]


def test_login_wires_handlers_and_persists_catalogue(tmp_path, monkeypatch) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    client = MiroMCPClient(settings=settings)
    observed = {}

    @asynccontextmanager
    async def fake_handlers(_settings, *, open_browser, manual_callback):
        observed.update(browser=open_browser, manual=manual_callback)

        async def redirect(_url: str) -> None:
            return None

        async def callback() -> tuple[str, str | None]:
            return "code", "state"

        yield redirect, callback

    async def fake_discover(_settings, _storage, _redirect, _callback):
        return ToolCatalogue(
            protocol_version="2025-06-18",
            server_name="Miro",
            server_version="test",
            tools=(
                ToolInfo(
                    name="board_read",
                    title="Read board",
                    description="Read a board",
                    input_schema={"type": "object"},
                    output_schema=None,
                ),
            ),
        )

    monkeypatch.setattr(client_module, "interactive_handlers", fake_handlers)
    monkeypatch.setattr(client_module, "discover_tools", fake_discover)

    result = asyncio.run(client.login(open_browser=False, manual_callback=True))
    assert result.tools[0].name == "board_read"
    assert observed == {"browser": False, "manual": True}
    cached = json.loads(settings.catalogue_path.read_text(encoding="utf-8"))
    assert cached["tool_count"] == 1
    assert settings.catalogue_path.stat().st_mode & 0o077 == 0
