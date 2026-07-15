"""High-level, receipt-bound managed-image operations across Miro MCP and REST."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    MiroToolError,
    find_nested_miro_error,
    redact_text,
)
from .managed_image_runtime import (
    ManagedImageIdentity,
    ManagedImageReconciliationRequired,
    delete_managed_image,
    load_managed_image_identity,
    read_managed_image_bytes,
    replace_managed_image,
    source_sha256,
    validate_content_type,
    validate_image_title,
)
from .models import MiroSettings
from .native_runtime import (
    _validated_upload_url,
    native_asset_lock,
    native_board_lock,
    native_receipt_lock,
)
from .rest_client import MiroRestClient, validate_rest_board_id
from .rest_credentials import MiroRestTokenStorage
from .runtime import quiet_provider_stderr, threadless_dns_resolution
from .snapshot_runtime import prepare_snapshot_destination


async def _authorization_required(_value: str = "") -> tuple[str, str | None]:
    raise MiroAuthorizationRequired("Miro login must be renewed")


def board_id_from_url(board_url: str) -> str:
    """Extract one REST board identifier from an allowlisted Miro board URL."""
    try:
        parsed = urlsplit(board_url)
    except ValueError as exc:
        raise MiroCredentialError("allowlisted Miro board URL is invalid") from exc
    prefix = "/app/board/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "miro.com"
        or not parsed.path.startswith(prefix)
    ):
        raise MiroCredentialError("allowlisted Miro board URL is invalid")
    board_id = parsed.path[len(prefix) :].strip("/")
    if "/" in board_id:
        raise MiroCredentialError("allowlisted Miro board URL is invalid")
    try:
        return validate_rest_board_id(board_id)
    except ValueError as exc:
        raise MiroCredentialError("allowlisted Miro board id is invalid") from exc


def check_managed_image(
    *,
    alias: str,
    identity_path: Path,
    image_path: Path | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Validate local managed-image inputs without contacting Miro."""
    name = validate_alias(alias)
    identity = load_managed_image_identity(identity_path)
    if identity.board_alias != name:
        raise MiroCredentialError("managed image identity board alias does not match")
    result: dict[str, Any] = {
        "schema_version": "schauwerk-miro-managed-image-check.v1",
        "ok": True,
        "board_alias": name,
        "asset_key": identity.asset_key,
        "item_id": identity.item_id,
        "parent_id": identity.parent_id,
        "identity_source_sha256": identity.source_sha256,
        "mutation_attempted": False,
        "sanitized_references": True,
    }
    if image_path is None and content_type is not None:
        raise ValueError("content_type requires an image source")
    if image_path is not None:
        if content_type is None:
            raise ValueError("content_type is required when an image source is checked")
        payload = read_managed_image_bytes(image_path)
        digest = source_sha256(payload)
        result.update(
            {
                "content_type": validate_content_type(content_type),
                "source_sha256": digest,
                "source_bytes": len(payload),
                "source_changed": digest != identity.source_sha256,
            }
        )
    return result


def _protected_paths(
    settings: MiroSettings,
    rest_storage: MiroRestTokenStorage,
    *,
    identity_input: Path,
    source_image: Path | None,
) -> set[Path]:
    values = {
        settings.credentials_path,
        settings.catalogue_path,
        settings.auth_health_path,
        settings.auth_history_path,
        settings.board_allowlist_path,
        rest_storage.settings.token_path,
        rest_storage.settings.lock_path,
        identity_input,
    }
    if source_image is not None:
        values.add(source_image)
    return {value.expanduser().absolute() for value in values}


def _new_output(path: Path, *, protected: set[Path], label: str) -> Path:
    destination = prepare_snapshot_destination(path)
    if destination in protected:
        raise MiroCredentialError(f"{label} collides with a protected input")
    if destination.exists() or destination.is_symlink():
        raise MiroCredentialError(f"{label} already exists")
    return destination


def _write_new_private_json(
    path: Path,
    value: dict[str, Any],
    *,
    label: str,
) -> Path:
    """Atomically publish one owner-only JSON file without replacing any path."""
    destination = prepare_snapshot_destination(path)
    parent = destination.parent
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise MiroCredentialError(f"{label} parent is unavailable") from exc
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        directory_descriptor = os.open(parent, directory_flags)
    except OSError as exc:
        raise MiroCredentialError(f"{label} parent is unsafe") from exc
    temporary_name = f".{destination.name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        directory_metadata = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(directory_metadata.st_mode)
            or directory_metadata.st_uid != os.getuid()
            or directory_metadata.st_mode & 0o022
        ):
            raise MiroCredentialError(f"{label} parent must be owner-controlled")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        temporary_exists = True
        payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        if len(payload) > 1024 * 1024:
            raise MiroCredentialError(f"{label} exceeds the supported byte bound")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short JSON write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(
                temporary_name,
                destination.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise MiroCredentialError(f"{label} already exists") from exc
        os.unlink(temporary_name, dir_fd=directory_descriptor)
        temporary_exists = False
        os.fsync(directory_descriptor)
    except OSError as exc:
        raise MiroCredentialError(f"{label} could not be published") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
        os.close(directory_descriptor)
    return destination


def _recorded_exception(exc: BaseException) -> Exception:
    if isinstance(exc, Exception):
        return exc
    return ManagedImageReconciliationRequired(
        "managed image operation was interrupted; manual reconciliation required"
    )


def _sanitized_failure_message(exc: Exception) -> str:
    message = redact_text(exc)
    return re.sub(r"https?://[^\s]+", "<redacted-url>", message)


def _failure_receipt(
    *,
    operation: str,
    identity: ManagedImageIdentity,
    source_digest: str | None,
    exc: Exception,
) -> dict[str, Any]:
    manual = isinstance(exc, ManagedImageReconciliationRequired)
    return {
        "schema_version": f"schauwerk-miro-managed-image-{operation}.v1",
        "success": False,
        "status": "manual_reconciliation_required" if manual else "failed",
        "board_alias": identity.board_alias,
        "asset_key": identity.asset_key,
        "old_item_id": identity.item_id,
        "source_sha256": source_digest,
        "provider_semantics": (
            "create-verify-delete-saga"
            if operation == "replace"
            else "single-rest-delete-with-readback"
        ),
        "globally_atomic": False,
        "manual_reconciliation_required": manual,
        "error_type": type(exc).__name__,
        "error": _sanitized_failure_message(exc),
        "sanitized_references": True,
    }


@asynccontextmanager
async def _live_mcp(
    settings: MiroSettings,
    storage: FileTokenStorage,
) -> AsyncIterator[tuple[Any, set[str], httpx.AsyncClient]]:
    oauth = build_oauth_provider(
        settings,
        storage,
        _authorization_required,
        _authorization_required,
    )
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
                    async with streamable_http_client(
                        settings.server_url,
                        http_client=http_client,
                    ) as (read_stream, write_stream, _session_id):
                        async with ClientSession(read_stream, write_stream) as session:
                            await session.initialize()
                            tools = await list_all_tools(session)
                            yield session.call_tool, {tool.name for tool in tools}, upload_client
    except MiroError:
        raise
    except BaseException as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            raise nested from exc
        if not isinstance(exc, Exception):
            raise
        raise MiroConnectionError(f"Miro managed image session failed: {redact_text(exc)}") from exc


async def _upload_bytes(
    client: httpx.AsyncClient,
    upload_url: str,
    content_type: str,
    payload: bytes,
) -> bool:
    try:
        response = await client.put(
            _validated_upload_url(upload_url),
            content=payload,
            headers={"Content-Type": content_type},
        )
    except httpx.HTTPError as exc:
        raise MiroConnectionError("Miro managed image upload failed") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise MiroConnectionError(
            f"Miro managed image upload failed with HTTP {response.status_code}"
        )
    return True


async def run_managed_image_replace(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    identity_path: Path,
    image_path: Path,
    content_type: str,
    title: str,
    receipt_path: Path,
    identity_output_path: Path,
    rest_client: MiroRestClient | None = None,
    max_pages: int = 100,
) -> dict[str, Any]:
    """Replace one managed image through a receipt-bound MCP/REST saga."""
    name = validate_alias(alias)
    identity_input = identity_path.expanduser().absolute()
    source_input = image_path.expanduser().absolute()
    identity = load_managed_image_identity(identity_input)
    if identity.board_alias != name:
        raise MiroCredentialError("managed image identity board alias does not match")
    payload = read_managed_image_bytes(source_input)
    digest = source_sha256(payload)
    media_type = validate_content_type(content_type)
    safe_title = validate_image_title(title)
    if digest == identity.source_sha256:
        raise MiroToolError("managed image replacement requires changed source bytes")
    if not 1 <= max_pages <= 100:
        raise ValueError("managed image max_pages must be between 1 and 100")
    active_rest = rest_client or MiroRestClient()
    protected = _protected_paths(
        settings,
        active_rest.storage,
        identity_input=identity_input,
        source_image=source_input,
    )
    receipt_destination = _new_output(
        receipt_path,
        protected=protected,
        label="managed image receipt output",
    )
    protected.add(receipt_destination)
    identity_destination = _new_output(
        identity_output_path,
        protected=protected,
        label="managed image identity output",
    )
    board_url = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    board_id = board_id_from_url(board_url)
    await active_rest.doctor(require_write=True)

    with native_board_lock(settings, board_url):
        with native_asset_lock(
            settings,
            board_url=board_url,
            asset_key=identity.asset_key,
        ):
            with native_receipt_lock(settings, receipt_destination):
                with native_receipt_lock(settings, identity_destination):
                    try:
                        async with _live_mcp(settings, storage) as (
                            call_tool,
                            capabilities,
                            upload_client,
                        ):

                            async def upload(
                                upload_url: str,
                                current_content_type: str,
                                current_payload: bytes,
                            ) -> bool:
                                return await _upload_bytes(
                                    upload_client,
                                    upload_url,
                                    current_content_type,
                                    current_payload,
                                )

                            async def delete(item_id: str, allow_absent: bool) -> Any:
                                return await active_rest.delete_image(
                                    board_id,
                                    item_id,
                                    allow_absent=allow_absent,
                                )

                            replacement, receipt = await replace_managed_image(
                                call_tool,
                                upload,
                                capabilities=capabilities,
                                board_url=board_url,
                                identity=identity,
                                image_bytes=payload,
                                content_type=media_type,
                                title=safe_title,
                                delete_image=delete,
                                max_pages=max_pages,
                            )
                    except BaseException as exc:
                        recorded = _recorded_exception(exc)
                        try:
                            _write_new_private_json(
                                receipt_destination,
                                _failure_receipt(
                                    operation="replace",
                                    identity=identity,
                                    source_digest=digest,
                                    exc=recorded,
                                ),
                                label="managed image failure receipt",
                            )
                        except Exception as publication_error:
                            raise ManagedImageReconciliationRequired(
                                "managed image operation failed and its failure receipt "
                                "could not be published; manual reconciliation required"
                            ) from publication_error
                        raise
                    try:
                        _write_new_private_json(
                            identity_destination,
                            replacement.to_document(),
                            label="managed image identity output",
                        )
                    except Exception as publication_error:
                        checkpoint_error = ManagedImageReconciliationRequired(
                            "managed image replacement succeeded, but the new identity "
                            "could not be published; manual reconciliation required"
                        )
                        checkpoint = {
                            **_failure_receipt(
                                operation="replace",
                                identity=identity,
                                source_digest=digest,
                                exc=checkpoint_error,
                            ),
                            "new_item_id": replacement.item_id,
                        }
                        try:
                            _write_new_private_json(
                                receipt_destination,
                                checkpoint,
                                label="managed image reconciliation receipt",
                            )
                        except Exception as receipt_error:
                            raise ManagedImageReconciliationRequired(
                                "managed image replacement succeeded, but neither the new "
                                "identity nor its reconciliation receipt could be published"
                            ) from receipt_error
                        raise checkpoint_error from publication_error
                    try:
                        _write_new_private_json(
                            receipt_destination,
                            receipt.to_dict(),
                            label="managed image success receipt",
                        )
                    except Exception as publication_error:
                        raise ManagedImageReconciliationRequired(
                            "managed image replacement succeeded and its new identity was "
                            "published, but the success receipt could not be published; "
                            "retain the identity output for recovery"
                        ) from publication_error
                    return {
                        **receipt.to_dict(),
                        "receipt_output": str(receipt_destination),
                        "identity_output": str(identity_destination),
                    }


async def run_managed_image_delete(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    alias: str,
    identity_path: Path,
    receipt_path: Path,
    rest_client: MiroRestClient | None = None,
    max_pages: int = 100,
) -> dict[str, Any]:
    """Delete one exact managed image through REST and prove absence through MCP."""
    name = validate_alias(alias)
    identity_input = identity_path.expanduser().absolute()
    identity = load_managed_image_identity(identity_input)
    if identity.board_alias != name:
        raise MiroCredentialError("managed image identity board alias does not match")
    if not 1 <= max_pages <= 100:
        raise ValueError("managed image max_pages must be between 1 and 100")
    active_rest = rest_client or MiroRestClient()
    protected = _protected_paths(
        settings,
        active_rest.storage,
        identity_input=identity_input,
        source_image=None,
    )
    receipt_destination = _new_output(
        receipt_path,
        protected=protected,
        label="managed image receipt output",
    )
    board_url = BoardAllowlist(settings.board_allowlist_path).resolve(name)
    board_id = board_id_from_url(board_url)
    await active_rest.doctor(require_write=True)

    with native_board_lock(settings, board_url):
        with native_asset_lock(
            settings,
            board_url=board_url,
            asset_key=identity.asset_key,
        ):
            with native_receipt_lock(settings, receipt_destination):
                try:
                    async with _live_mcp(settings, storage) as (
                        call_tool,
                        capabilities,
                        _upload_client,
                    ):

                        async def delete(item_id: str, allow_absent: bool) -> Any:
                            return await active_rest.delete_image(
                                board_id,
                                item_id,
                                allow_absent=allow_absent,
                            )

                        receipt = await delete_managed_image(
                            call_tool,
                            capabilities=capabilities,
                            board_url=board_url,
                            identity=identity,
                            delete_image=delete,
                            max_pages=max_pages,
                        )
                except BaseException as exc:
                    recorded = _recorded_exception(exc)
                    try:
                        _write_new_private_json(
                            receipt_destination,
                            _failure_receipt(
                                operation="delete",
                                identity=identity,
                                source_digest=None,
                                exc=recorded,
                            ),
                            label="managed image failure receipt",
                        )
                    except Exception as publication_error:
                        raise ManagedImageReconciliationRequired(
                            "managed image operation failed and its failure receipt "
                            "could not be published; manual reconciliation required"
                        ) from publication_error
                    raise
                try:
                    _write_new_private_json(
                        receipt_destination,
                        receipt.to_dict(),
                        label="managed image success receipt",
                    )
                except Exception as publication_error:
                    raise ManagedImageReconciliationRequired(
                        "managed image deletion succeeded, but its success receipt could "
                        "not be published; the identity now references an absent item"
                    ) from publication_error
                return {
                    **receipt.to_dict(),
                    "receipt_output": str(receipt_destination),
                }
