"""Command handlers for the Schauwerk CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .surfaces.miro.client import MiroMCPClient


def handle_status(client: MiroMCPClient | None = None) -> dict[str, Any]:
    return (client or MiroMCPClient()).status()


def handle_login(
    *, open_browser: bool, manual_callback: bool, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    return asyncio.run(
        active.login(open_browser=open_browser, manual_callback=manual_callback)
    ).to_dict()


def handle_tools(client: MiroMCPClient | None = None) -> dict[str, Any]:
    return asyncio.run((client or MiroMCPClient()).tools()).to_dict()


def handle_inspect(
    *,
    query: str,
    owned_by_me: bool,
    limit: int,
    max_pages: int,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    report = asyncio.run(
        (client or MiroMCPClient()).inspect(
            query=query, owned_by_me=owned_by_me, limit=limit, max_pages=max_pages
        )
    )
    return report.to_dict()


def handle_board_add(
    *, alias: str, miro_url: str, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    return (client or MiroMCPClient()).board_add(alias, miro_url).to_dict()


def handle_board_list(client: MiroMCPClient | None = None) -> dict[str, Any]:
    boards = (client or MiroMCPClient()).board_list()
    return {"count": len(boards), "boards": [board.to_dict() for board in boards]}


def handle_board_remove(
    *, alias: str, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    return {"alias": alias, "removed": (client or MiroMCPClient()).board_remove(alias)}


def handle_snapshot(
    *,
    alias: str,
    output: str | None,
    item_limit: int,
    comment_limit: int,
    max_pages: int,
    include_comments: bool,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    receipt = asyncio.run(
        (client or MiroMCPClient()).snapshot(
            alias=alias,
            output_path=Path(output) if output else None,
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )
    )
    return receipt.to_dict()


def handle_logout(client: MiroMCPClient | None = None) -> dict[str, bool]:
    return (client or MiroMCPClient()).logout()
