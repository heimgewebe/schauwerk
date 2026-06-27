"""Command handlers for the Schauwerk CLI."""

from __future__ import annotations

import asyncio
from typing import Any

from .surfaces.miro.client import MiroMCPClient


def handle_status(client: MiroMCPClient | None = None) -> dict[str, Any]:
    return (client or MiroMCPClient()).status()


def handle_login(
    *,
    open_browser: bool,
    manual_callback: bool,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    result = asyncio.run(
        active.login(open_browser=open_browser, manual_callback=manual_callback)
    )
    return result.to_dict()


def handle_tools(client: MiroMCPClient | None = None) -> dict[str, Any]:
    active = client or MiroMCPClient()
    return asyncio.run(active.tools()).to_dict()


def handle_logout(client: MiroMCPClient | None = None) -> dict[str, bool]:
    return (client or MiroMCPClient()).logout()
