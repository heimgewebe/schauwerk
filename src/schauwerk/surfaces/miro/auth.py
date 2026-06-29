"""Interactive OAuth callback handling for the direct Miro MCP client."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .errors import MiroAuthorizationError
from .models import MiroSettings

RedirectHandler = Callable[[str], Awaitable[None]]
CallbackHandler = Callable[[], Awaitable[tuple[str, str | None]]]


@dataclass(frozen=True)
class CallbackResult:
    code: str
    state: str | None




def _open_browser_nonblocking(url: str) -> bool:
    """Launch a local browser without blocking the asyncio event loop."""
    commands: list[list[str]] = []
    if sys.platform == "darwin":
        commands.append(["open", url])
    elif sys.platform.startswith("linux"):
        xdg_open = shutil.which("xdg-open")
        if xdg_open:
            commands.append([xdg_open, url])
        gio = shutil.which("gio")
        if gio:
            commands.append([gio, "open", url])

    for command in commands:
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    return False

def parse_callback_url(value: str, *, expected_path: str | None = None) -> CallbackResult:
    """Parse a full callback URL or request target without exposing its contents."""
    parsed = urlsplit(value.strip())
    if expected_path is not None and parsed.path != expected_path:
        raise MiroAuthorizationError("OAuth callback used an unexpected path")
    parameters = parse_qs(parsed.query, keep_blank_values=True)
    if "error" in parameters:
        description = parameters.get("error_description", parameters["error"])[0]
        raise MiroAuthorizationError(f"Miro authorization was denied: {description[:200]}")
    code = parameters.get("code", [""])[0]
    if not code:
        raise MiroAuthorizationError("OAuth callback did not contain an authorization code")
    state = parameters.get("state", [None])[0]
    return CallbackResult(code=code, state=state)


class LoopbackCallbackServer:
    """Single-use loopback HTTP callback server with bounded input."""

    def __init__(self, settings: MiroSettings) -> None:
        self.settings = settings
        self._server: asyncio.AbstractServer | None = None
        self._future: asyncio.Future[CallbackResult] | None = None

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("callback server already started")
        self._future = asyncio.get_running_loop().create_future()
        try:
            self._server = await asyncio.start_server(
                self._handle_connection,
                self.settings.callback_host,
                self.settings.callback_port,
            )
        except OSError as exc:
            raise MiroAuthorizationError(
                f"Cannot bind OAuth callback on {self.settings.redirect_uri}"
            ) from exc

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def wait(self) -> tuple[str, str | None]:
        if self._future is None:
            raise RuntimeError("callback server has not started")
        try:
            result = await asyncio.wait_for(
                asyncio.shield(self._future),
                timeout=self.settings.authorization_timeout_seconds,
            )
        except TimeoutError as exc:
            duration = self.settings.authorization_timeout_seconds
            raise MiroAuthorizationError(
                "Timed out waiting for Miro authorization "
                f"after {duration:g} seconds"
            ) from exc
        return result.code, result.state

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        status = "400 Bad Request"
        body = "Miro authorization failed. You may close this tab."
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if len(request_line) > 8192:
                raise MiroAuthorizationError("OAuth callback request was too large")
            parts = request_line.decode("ascii", errors="replace").strip().split(" ")
            if len(parts) != 3 or parts[0] != "GET":
                raise MiroAuthorizationError("OAuth callback must be an HTTP GET request")
            target = parts[1]
            total_header_bytes = 0
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                total_header_bytes += len(line)
                if total_header_bytes > 32768:
                    raise MiroAuthorizationError("OAuth callback headers were too large")
                if line in (b"\r\n", b"\n", b""):
                    break
            result = parse_callback_url(target, expected_path=self.settings.callback_path)
            if self._future is not None and not self._future.done():
                self._future.set_result(result)
            status = "200 OK"
            body = "Miro authorization complete. You may close this tab."
        except Exception as exc:
            error = exc if isinstance(exc, MiroAuthorizationError) else MiroAuthorizationError(
                "Invalid OAuth callback"
            )
            if self._future is not None and not self._future.done():
                self._future.set_exception(error)
        finally:
            encoded = body.encode("utf-8")
            response = (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                "Cache-Control: no-store\r\n"
                f"Content-Length: {len(encoded)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + encoded
            writer.write(response)
            with contextlib.suppress(ConnectionError):
                await writer.drain()
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()


@contextlib.asynccontextmanager
async def interactive_handlers(
    settings: MiroSettings,
    *,
    open_browser: bool,
    manual_callback: bool,
) -> AsyncIterator[tuple[RedirectHandler, CallbackHandler]]:
    """Create redirect/callback handlers for one authorization attempt."""
    server: LoopbackCallbackServer | None = None
    if not manual_callback:
        server = LoopbackCallbackServer(settings)
        await server.start()

    async def redirect_handler(url: str) -> None:
        if open_browser:
            opened = _open_browser_nonblocking(url)
            if opened:
                print("Opened Miro authorization in the local browser.", file=sys.stderr)
                return
        print("Open this Miro authorization URL:", file=sys.stderr)
        print(url, file=sys.stderr)

    async def callback_handler() -> tuple[str, str | None]:
        if manual_callback:
            value = input("Paste the final callback URL from the browser: ")
            result = parse_callback_url(value, expected_path=settings.callback_path)
            return result.code, result.state
        if server is None:
            raise RuntimeError("callback server is unavailable")
        return await server.wait()

    try:
        yield redirect_handler, callback_handler
    finally:
        if server is not None:
            await server.close()
