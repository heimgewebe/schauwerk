from __future__ import annotations

import asyncio
import socket

from schauwerk.surfaces.miro.runtime import threadless_dns_resolution


def test_threadless_dns_resolution_uses_socket_without_executor(monkeypatch) -> None:
    calls = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        calls.append((host, port, args, kwargs))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    async def probe() -> None:
        loop = asyncio.get_running_loop()
        original = loop.getaddrinfo
        async with threadless_dns_resolution():
            result = await loop.getaddrinfo("example.invalid", 443)
        restored = getattr(loop.getaddrinfo, "__func__", loop.getaddrinfo)
        previous = getattr(original, "__func__", original)
        assert calls[0][0] == "example.invalid"
        assert result[0][4] == ("127.0.0.1", 443)
        assert restored is previous

    asyncio.run(probe())
