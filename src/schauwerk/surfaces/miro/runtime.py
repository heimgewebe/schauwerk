"""Runtime guards for constrained Miro MCP executions."""

from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncIterator
from typing import Any


@contextlib.asynccontextmanager
async def threadless_dns_resolution() -> AsyncIterator[None]:
    """Resolve DNS in the event-loop thread instead of allocating executor threads."""
    loop = asyncio.get_running_loop()
    had_getaddrinfo = "getaddrinfo" in loop.__dict__
    had_getnameinfo = "getnameinfo" in loop.__dict__
    original_getaddrinfo = loop.__dict__.get("getaddrinfo")
    original_getnameinfo = loop.__dict__.get("getnameinfo")

    async def getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        return socket.getaddrinfo(host, port, *args, **kwargs)

    async def getnameinfo(sockaddr: tuple[Any, ...], flags: int = 0) -> tuple[str, str]:
        return socket.getnameinfo(sockaddr, flags)

    loop.getaddrinfo = getaddrinfo  # type: ignore[method-assign]
    loop.getnameinfo = getnameinfo  # type: ignore[method-assign]
    try:
        yield
    finally:
        if had_getaddrinfo:
            loop.getaddrinfo = original_getaddrinfo  # type: ignore[method-assign]
        else:
            del loop.getaddrinfo
        if had_getnameinfo:
            loop.getnameinfo = original_getnameinfo  # type: ignore[method-assign]
        else:
            del loop.getnameinfo
