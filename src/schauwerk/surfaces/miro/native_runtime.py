"""Live Miro MCP session for the validated native bundle executor."""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .board_registry import BoardAllowlist, validate_alias
from .credentials import FileTokenStorage
from .discovery import build_oauth_provider, list_all_tools
from .errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    MiroCredentialError,
    MiroError,
    find_nested_miro_error,
    redact_text,
)
from .models import MiroSettings
from .native_executor import (
    execute_native_bundle,
    load_native_bundle,
    load_native_resume_receipt,
)
from .runtime import quiet_provider_stderr, threadless_dns_resolution
from .snapshot_runtime import prepare_snapshot_destination, write_snapshot_json


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def _validated_upload_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise MiroConnectionError("Miro prototype upload URL is invalid") from exc
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
        or "." not in hostname
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise MiroConnectionError("Miro prototype upload URL is unsafe")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise MiroConnectionError("Miro prototype upload URL is unsafe")
    return value


def _tool_document(tools: list[Any]) -> list[dict[str, Any]]:
    return [tool.to_dict() for tool in tools]


@contextmanager
def _native_scope_lock(settings: MiroSettings, *, scope: str, material: str) -> Iterator[Path]:
    directory = settings.state_root / "native-execution-locks"
    if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents):
        raise MiroCredentialError("native execution lock directory is unsafe")
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_descriptor = os.open(directory, directory_flags)
    except OSError as exc:
        raise MiroCredentialError("native execution lock directory is unavailable") from exc
    try:
        directory_stat = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise MiroCredentialError("native execution lock path is not a directory")
        if directory_stat.st_uid != os.getuid() or directory_stat.st_mode & 0o077:
            raise MiroCredentialError("native execution lock directory is not owner-only")
        key = hashlib.sha256(f"{scope}\0{material}".encode()).hexdigest()
        lock_name = f"{scope}-{key}.lock"
        lock_path = directory / lock_name
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_name, flags, 0o600, dir_fd=directory_descriptor)
        except OSError as exc:
            raise MiroCredentialError("native execution lock is unavailable") from exc
        try:
            lock_stat = os.fstat(descriptor)
            if not stat.S_ISREG(lock_stat.st_mode):
                raise MiroCredentialError("native execution lock is not a regular file")
            if lock_stat.st_uid != os.getuid() or lock_stat.st_mode & 0o077:
                raise MiroCredentialError("native execution lock is not owner-only")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise MiroConnectionError(
                    f"another native Miro execution is already active for this {scope}"
                ) from exc
            try:
                yield lock_path
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory_descriptor)


@contextmanager
def native_board_lock(settings: MiroSettings, board_url: str) -> Iterator[Path]:
    with _native_scope_lock(settings, scope="board", material=board_url) as lock_path:
        yield lock_path


@contextmanager
def native_receipt_lock(settings: MiroSettings, receipt_path: Path) -> Iterator[Path]:
    material = str(receipt_path.expanduser().absolute())
    with _native_scope_lock(settings, scope="receipt", material=material) as lock_path:
        yield lock_path


def prepare_native_destination(
    settings: MiroSettings,
    *,
    input_path: Path,
    output_path: Path,
) -> Path:
    destination = prepare_snapshot_destination(output_path)
    protected = {
        input_path.expanduser().absolute(),
        settings.credentials_path.expanduser().absolute(),
        settings.catalogue_path.expanduser().absolute(),
        settings.auth_health_path.expanduser().absolute(),
        settings.auth_history_path.expanduser().absolute(),
        settings.board_allowlist_path.expanduser().absolute(),
    }
    if destination in protected:
        raise MiroCredentialError("native receipt output collides with a protected input")
    return destination


async def run_native_bundle(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    input_path: Path,
    output_path: Path,
    resume_path: Path | None = None,
) -> dict[str, Any]:
    """Apply one bundle to an allowlisted board and persist checkpoint evidence."""

    name = validate_alias(alias)
    destination = prepare_native_destination(
        settings,
        input_path=input_path,
        output_path=output_path,
    )
    board_url = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    with native_board_lock(settings, board_url):
        with native_receipt_lock(settings, destination):
            bundle = load_native_bundle(input_path)
            resume_receipt = load_native_resume_receipt(resume_path) if resume_path else None
            oauth = build_oauth_provider(
                settings, storage, _authorization_required, _authorization_required
            )

            def checkpoint(receipt: dict[str, Any]) -> None:
                write_snapshot_json(destination, receipt)

            try:
                with quiet_provider_stderr():
                    async with threadless_dns_resolution():
                        async with (
                            httpx.AsyncClient(
                                auth=oauth,
                                follow_redirects=True,
                                timeout=httpx.Timeout(settings.network_timeout_seconds),
                                headers={"User-Agent": "schauwerk/0.1"},
                            ) as http_client,
                            httpx.AsyncClient(
                                follow_redirects=False,
                                timeout=httpx.Timeout(settings.network_timeout_seconds),
                                headers={"User-Agent": "schauwerk/0.1"},
                                trust_env=False,
                            ) as upload_client,
                        ):

                            async def upload_html(upload_url: str, payload: bytes) -> None:
                                try:
                                    response = await upload_client.put(
                                        _validated_upload_url(upload_url),
                                        content=payload,
                                        headers={"Content-Type": "text/html"},
                                    )
                                except httpx.HTTPError as exc:
                                    raise MiroConnectionError(
                                        "Miro prototype HTML upload failed"
                                    ) from exc
                                if response.status_code < 200 or response.status_code >= 300:
                                    raise MiroConnectionError(
                                        "Miro prototype HTML upload failed with HTTP "
                                        f"{response.status_code}"
                                    )

                            async with streamable_http_client(
                                settings.server_url, http_client=http_client
                            ) as (read_stream, write_stream, _session_id):
                                async with ClientSession(read_stream, write_stream) as session:
                                    await session.initialize()
                                    tools = await list_all_tools(session)
                                    return await execute_native_bundle(
                                        call_tool=session.call_tool,
                                        tool_catalogue=_tool_document(tools),
                                        board_alias=name,
                                        board_url=board_url,
                                        bundle=bundle,
                                        checkpoint=checkpoint,
                                        resume_receipt=resume_receipt,
                                        bundle_root=input_path.expanduser().absolute().parent,
                                        upload_html=upload_html,
                                    )
            except MiroError:
                raise
            except BaseException as exc:
                nested = find_nested_miro_error(exc)
                if nested is not None:
                    raise nested from exc
                if not isinstance(exc, Exception):
                    raise
                raise MiroConnectionError(
                    f"Miro native bundle execution failed: {redact_text(exc)}"
                ) from exc
