"""Runtime for verified Miro board snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .board_registry import BoardAllowlist, validate_alias
from .credentials import FileTokenStorage
from .discovery import build_oauth_provider
from .errors import (
    MiroAuthorizationRequired,
    MiroConnectionError,
    MiroCredentialError,
    MiroError,
    find_nested_miro_error,
    redact_text,
)
from .models import MiroSettings
from .runtime import threadless_dns_resolution
from .snapshot import read_board_snapshot
from .snapshot_model import SnapshotRead, SnapshotReceipt, content_digest


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def prepare_snapshot_destination(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise MiroCredentialError("Snapshot output path is unsafe")
    return destination



def write_snapshot_json(path: Path, value: dict) -> None:
    """Atomically write one snapshot file without changing an existing parent mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise

def verify_snapshot_pair(
    first: SnapshotRead, second: SnapshotRead, *, alias: str
) -> tuple[dict, str]:
    first_content = first.content(alias)
    second_content = second.content(alias)
    digest = content_digest(second_content)
    if content_digest(first_content) != digest:
        raise MiroConnectionError(
            "Unchanged-board repeatability check failed between consecutive reads"
        )
    if (first.item_pages, first.comment_pages) != (second.item_pages, second.comment_pages):
        raise MiroConnectionError("pagination repeatability check failed")
    return second_content, digest


def write_snapshot_pair(
    first: SnapshotRead,
    second: SnapshotRead,
    *,
    alias: str,
    destination: Path,
) -> SnapshotReceipt:
    destination = prepare_snapshot_destination(destination)
    content, digest = verify_snapshot_pair(first, second, alias=alias)
    write_snapshot_json(
        destination,
        {
            **content,
            "content_digest": digest,
            "repeatability_verified": True,
            "verified_reads": 2,
            "sanitized_references": True,
        },
    )
    return SnapshotReceipt(
        board_alias=alias,
        content_digest=digest,
        item_count=len(second.items),
        comment_count=len(second.comments),
        item_pages=second.item_pages,
        comment_pages=second.comment_pages,
        repeatability_verified=True,
        output_path=str(destination),
    )


async def run_verified_snapshot(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    output_path: Path | None = None,
    item_limit: int = 100,
    comment_limit: int = 50,
    max_pages: int = 20,
    include_comments: bool = True,
) -> SnapshotReceipt:
    name = validate_alias(alias)
    miro_url = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    destination = prepare_snapshot_destination(
        output_path or settings.snapshots_root / f"{name}.json"
    )
    oauth = build_oauth_provider(
        settings, storage, _authorization_required, _authorization_required
    )
    try:
        async with threadless_dns_resolution():
            async with httpx.AsyncClient(
                auth=oauth,
                follow_redirects=True,
                timeout=httpx.Timeout(settings.network_timeout_seconds),
                headers={"User-Agent": "schauwerk/0.1"},
            ) as http_client:
                async with streamable_http_client(settings.server_url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                    _session_id,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        arguments = {
                            "miro_url": miro_url,
                            "item_limit": item_limit,
                            "comment_limit": comment_limit,
                            "max_pages": max_pages,
                            "include_comments": include_comments,
                        }
                        first = await read_board_snapshot(session.call_tool, **arguments)
                        second = await read_board_snapshot(session.call_tool, **arguments)
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(f"Miro board snapshot failed: {redact_text(exc)}") from exc

    return write_snapshot_pair(first, second, alias=name, destination=destination)
