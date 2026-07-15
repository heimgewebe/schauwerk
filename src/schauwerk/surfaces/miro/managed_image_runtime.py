"""Receipt-bound orchestration for Schauwerk-managed Miro image lifecycles."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .board_registry import validate_alias
from .errors import MiroCredentialError, MiroToolError
from .inspection import result_payload

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]
ByteUploader = Callable[[str, str, bytes], Awaitable[bool]]
ImageDeleter = Callable[[str, bool], Awaitable[Any]]

MANAGED_IMAGE_SCHEMA = "schauwerk-miro-managed-image.v1"
REPLACE_RECEIPT_SCHEMA = "schauwerk-miro-managed-image-replace.v1"
DELETE_RECEIPT_SCHEMA = "schauwerk-miro-managed-image-delete.v1"
_REQUIRED_MCP_TOOLS = frozenset({"board_list_items", "image_get_upload_url", "image_create"})
_REQUIRED_DELETE_MCP_TOOLS = frozenset({"board_list_items"})
_ASSET_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ITEM_ID = re.compile(r"^[0-9]{1,32}$")
_ALLOWED_CONTENT_TYPES = frozenset({"image/svg+xml", "image/png", "image/jpeg", "image/webp"})
_MAX_IMAGE_BYTES = 25 * 1024 * 1024


class ManagedImageReconciliationRequired(MiroToolError):
    """The provider outcome is not safely reducible to one managed identity."""


@dataclass(frozen=True)
class ManagedImageIdentity:
    board_alias: str
    asset_key: str
    item_id: str
    parent_id: str
    source_sha256: str
    x: float
    y: float
    width: float

    def __post_init__(self) -> None:
        validate_alias(self.board_alias)
        if _ASSET_KEY.fullmatch(self.asset_key) is None:
            raise ValueError("managed image identity requires a safe bounded asset_key")
        if _ITEM_ID.fullmatch(self.item_id) is None or _ITEM_ID.fullmatch(self.parent_id) is None:
            raise ValueError("managed image identity requires bounded numeric Miro item ids")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("source_sha256 must be lowercase SHA-256")
        for label, value in (("x", self.x), ("y", self.y), ("width", self.width)):
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
            ):
                raise ValueError(f"managed image {label} must be one finite number")
        if abs(self.x) > 1_000_000 or abs(self.y) > 1_000_000:
            raise ValueError("managed image position exceeds the supported bound")
        if not 0 < self.width <= 1_000_000:
            raise ValueError("managed image width is outside the supported bound")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_document(self) -> dict[str, Any]:
        return {"schema_version": MANAGED_IMAGE_SCHEMA, **self.to_dict()}


@dataclass(frozen=True)
class ManagedImageReplaceReceipt:
    success: bool
    board_alias: str
    asset_key: str
    old_item_id: str
    new_item_id: str
    source_sha256: str
    before_count: int
    after_count: int
    old_item_absent: bool
    new_item_present: bool
    geometry_matches: bool
    inventory_pages: int
    delete_receipt: dict[str, Any]
    schema_version: str = REPLACE_RECEIPT_SCHEMA
    status: str = "verified"
    provider_semantics: str = "create-verify-delete-saga"
    globally_atomic: bool = False
    manual_reconciliation_required: bool = False
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManagedImageDeleteReceipt:
    success: bool
    board_alias: str
    asset_key: str
    old_item_id: str
    before_count: int
    after_count: int
    old_item_absent: bool
    inventory_pages: int
    delete_receipt: dict[str, Any]
    schema_version: str = DELETE_RECEIPT_SCHEMA
    status: str = "verified"
    provider_semantics: str = "single-rest-delete-with-readback"
    globally_atomic: bool = False
    manual_reconciliation_required: bool = False
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_replace_capabilities(
    capabilities: set[str], *, external_delete_available: bool = False
) -> None:
    missing = sorted(_REQUIRED_MCP_TOOLS - capabilities)
    if missing:
        raise MiroToolError(
            "Miro managed image replacement is unavailable; missing MCP tools: "
            + ", ".join(missing)
        )
    if not external_delete_available and "image_delete" not in capabilities:
        raise MiroToolError(
            "Miro managed image replacement requires image_delete or a separate REST deleter"
        )


def require_delete_capabilities(
    capabilities: set[str], *, external_delete_available: bool = False
) -> None:
    missing = sorted(_REQUIRED_DELETE_MCP_TOOLS - capabilities)
    if missing:
        raise MiroToolError(
            "Miro managed image deletion is unavailable; missing MCP tools: " + ", ".join(missing)
        )
    if not external_delete_available and "image_delete" not in capabilities:
        raise MiroToolError(
            "Miro managed image deletion requires image_delete or a separate REST deleter"
        )


def validate_content_type(value: str) -> str:
    content_type = value.strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported managed image content type")
    return content_type


def validate_image_title(value: str) -> str:
    title = value.strip()
    if not 1 <= len(title) <= 200:
        raise ValueError("managed image title must contain 1-200 characters")
    if any(ord(character) < 0x20 and character != "\t" for character in title):
        raise ValueError("managed image title contains control characters")
    return title


def read_managed_image_bytes(path: Path) -> bytes:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise MiroCredentialError("managed image source path is unsafe")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError as exc:
        raise MiroCredentialError("managed image source is missing") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size < 1
        or metadata.st_size > _MAX_IMAGE_BYTES
    ):
        raise MiroCredentialError("managed image source must be one bounded regular file")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise MiroCredentialError("managed image source is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        before = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        observed = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if before != observed or opened.st_nlink != 1:
            raise MiroCredentialError("managed image source changed during read")
        payload = bytearray()
        while len(payload) <= _MAX_IMAGE_BYTES:
            chunk = os.read(descriptor, min(1024 * 1024, _MAX_IMAGE_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > _MAX_IMAGE_BYTES:
            raise MiroCredentialError("managed image source exceeds the byte bound")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _strict_identity(document: Any) -> ManagedImageIdentity:
    required = {
        "schema_version",
        "board_alias",
        "asset_key",
        "item_id",
        "parent_id",
        "source_sha256",
        "x",
        "y",
        "width",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise MiroCredentialError("managed image identity has an invalid shape")
    if document.get("schema_version") != MANAGED_IMAGE_SCHEMA:
        raise MiroCredentialError("managed image identity schema is unsupported")
    try:
        return ManagedImageIdentity(
            board_alias=document["board_alias"],
            asset_key=document["asset_key"],
            item_id=document["item_id"],
            parent_id=document["parent_id"],
            source_sha256=document["source_sha256"],
            x=document["x"],
            y=document["y"],
            width=document["width"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MiroCredentialError("managed image identity is invalid") from exc


def load_managed_image_identity(path: Path) -> ManagedImageIdentity:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise MiroCredentialError("managed image identity path is unsafe")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError as exc:
        raise MiroCredentialError("managed image identity is missing") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o077
        or metadata.st_size < 1
        or metadata.st_size > 64 * 1024
    ):
        raise MiroCredentialError("managed image identity must be one bounded regular file")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise MiroCredentialError("managed image identity is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        expected = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        observed = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        if expected != observed or opened.st_nlink != 1:
            raise MiroCredentialError("managed image identity changed during read")
        payload = bytearray()
        while len(payload) <= 64 * 1024:
            chunk = os.read(descriptor, min(4096, 64 * 1024 + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > 64 * 1024:
            raise MiroCredentialError("managed image identity exceeds the byte bound")
    finally:
        os.close(descriptor)
    try:
        document = json.loads(bytes(payload).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MiroCredentialError("managed image identity is unreadable") from exc
    return _strict_identity(document)


def _items(result: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro image inventory reported an error")
    payload = result_payload(result)
    data = payload.get("data")
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise MiroToolError("Miro image inventory returned an invalid payload")
    return data, payload


def _page_digest(records: list[dict[str, Any]]) -> str:
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def list_all_images(
    call_tool: ToolCaller,
    *,
    board_url: str,
    limit: int = 100,
    max_pages: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    if not 10 <= limit <= 1000 or not 1 <= max_pages <= 100:
        raise ValueError("managed image pagination bounds are invalid")
    cursor: str | None = None
    seen_cursors: set[str] = set()
    seen_pages: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    pages = 0
    has_more = False
    while pages < max_pages:
        arguments: dict[str, Any] = {
            "miro_url": board_url,
            "limit": limit,
            "item_type": "image",
            "invocation_source": "schauwerk-managed-image-lifecycle",
            "is_repository": True,
        }
        if cursor:
            arguments["cursor"] = cursor
        records, payload = _items(await call_tool("board_list_items", arguments))
        pages += 1
        marker = _page_digest(records)
        if marker in seen_pages:
            raise MiroToolError("Miro returned a repeated managed image page")
        seen_pages.add(marker)
        for record in records:
            item_id = str(record.get("id", ""))
            if _ITEM_ID.fullmatch(item_id) is None:
                raise MiroToolError("Miro image inventory returned an invalid item id")
            if item_id in by_id:
                raise MiroToolError("Miro image inventory returned a duplicate item id")
            if record.get("type") not in {None, "image"}:
                raise MiroToolError("Miro image inventory returned a non-image item")
            by_id[item_id] = record
        has_more = payload.get("has_more") is True
        next_cursor = payload.get("nextCursor")
        if not has_more:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise MiroToolError("Miro image pagination has no next cursor")
        if next_cursor in seen_cursors:
            raise MiroToolError("Miro returned a repeated image cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if has_more:
        raise MiroToolError("Miro image pagination exceeded the page limit")
    return [by_id[item_id] for item_id in sorted(by_id, key=int)], pages


def _item_id_from_url(value: Any) -> str:
    if not isinstance(value, str):
        raise MiroToolError("Miro image create did not return an item URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise MiroToolError("Miro image create returned an invalid item URL") from exc
    if parsed.scheme != "https" or parsed.hostname != "miro.com":
        raise MiroToolError("Miro image create returned an unexpected item origin")
    values = parse_qs(parsed.query, keep_blank_values=True).get("moveToWidget", [])
    if len(values) != 1 or _ITEM_ID.fullmatch(values[0]) is None:
        raise MiroToolError("Miro image create returned an invalid item id")
    return values[0]


def _item_url(board_url: str, item_id: str) -> str:
    if _ITEM_ID.fullmatch(item_id) is None:
        raise ValueError("managed Miro item id must be bounded and numeric")
    parsed = urlsplit(board_url)
    if parsed.scheme != "https" or parsed.hostname != "miro.com":
        raise ValueError("managed board URL is invalid")
    query = urlencode({"moveToWidget": item_id})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _same_geometry(item: Mapping[str, Any], identity: ManagedImageIdentity) -> bool:
    position = item.get("position")
    geometry = item.get("geometry")
    parent = item.get("parent")
    if not isinstance(position, Mapping) or not isinstance(geometry, Mapping):
        return False
    if not isinstance(parent, Mapping) or str(parent.get("id")) != identity.parent_id:
        return False
    values = (position.get("x"), position.get("y"), geometry.get("width"))
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        return False
    return (
        abs(float(values[0]) - identity.x) < 0.01
        and abs(float(values[1]) - identity.y) < 0.01
        and abs(float(values[2]) - identity.width) < 0.01
    )


def _indexed(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in items}


def _delete_document(value: Any, *, expected_item_id: str) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict) or value.get("success") is not True:
        raise MiroToolError("managed image deleter did not prove success")
    if str(value.get("item_id", "")) != expected_item_id:
        raise MiroToolError("managed image deleter returned a different item id")
    preflight_present = value.get("preflight_present")
    if not isinstance(preflight_present, bool):
        raise MiroToolError("managed image deleter returned an invalid preflight state")
    delete_status = value.get("delete_status")
    if delete_status is not None and (
        isinstance(delete_status, bool)
        or not isinstance(delete_status, int)
        or not 100 <= delete_status <= 599
    ):
        raise MiroToolError("managed image deleter returned an invalid HTTP status")
    if value.get("postflight_absent") is not True:
        raise MiroToolError("managed image deleter did not prove item absence")
    reconciled = value.get("reconciled_after_uncertain_delete")
    if not isinstance(reconciled, bool):
        raise MiroToolError("managed image deleter returned an invalid reconciliation state")
    return {
        "success": True,
        "provider": "rest",
        "item_id": expected_item_id,
        "preflight_present": preflight_present,
        "delete_status": delete_status,
        "postflight_absent": True,
        "reconciled_after_uncertain_delete": reconciled,
        "sanitized_references": True,
    }


async def _delete_item(
    call_tool: ToolCaller,
    *,
    capabilities: set[str],
    board_url: str,
    item_id: str,
    delete_image: ImageDeleter | None,
    allow_absent: bool,
) -> dict[str, Any]:
    if delete_image is not None:
        return _delete_document(
            await delete_image(item_id, allow_absent),
            expected_item_id=item_id,
        )
    if "image_delete" not in capabilities:
        raise MiroToolError("no managed image delete authority is available")
    deleted = await call_tool(
        "image_delete",
        {
            "miro_url": _item_url(board_url, item_id),
            "invocation_source": "schauwerk-managed-image-lifecycle",
            "is_repository": True,
        },
    )
    if bool(getattr(deleted, "isError", False)):
        raise MiroToolError("Miro image delete reported an error")
    payload = result_payload(deleted)
    if payload.get("success") is not True:
        raise MiroToolError("Miro image delete did not prove success")
    return {
        "success": True,
        "provider": "mcp",
        "item_id": item_id,
        "preflight_present": True,
        "delete_status": None,
        "postflight_absent": False,
        "reconciled_after_uncertain_delete": False,
        "sanitized_references": True,
    }


async def _compensate_new_image(
    call_tool: ToolCaller,
    *,
    capabilities: set[str],
    board_url: str,
    identity: ManagedImageIdentity,
    new_item_id: str,
    delete_image: ImageDeleter | None,
    before_count: int,
    max_pages: int,
) -> None:
    try:
        await _delete_item(
            call_tool,
            capabilities=capabilities,
            board_url=board_url,
            item_id=new_item_id,
            delete_image=delete_image,
            allow_absent=True,
        )
        current, _pages = await list_all_images(call_tool, board_url=board_url, max_pages=max_pages)
        by_id = _indexed(current)
        old = by_id.get(identity.item_id)
        if (
            old is None
            or not _same_geometry(old, identity)
            or new_item_id in by_id
            or len(current) != before_count
        ):
            raise MiroToolError("compensation readback failed")
    except Exception as exc:
        raise ManagedImageReconciliationRequired(
            "new managed image could not be safely compensated; manual reconciliation required"
        ) from exc


async def replace_managed_image(
    call_tool: ToolCaller,
    upload_bytes: ByteUploader,
    *,
    capabilities: set[str],
    board_url: str,
    identity: ManagedImageIdentity,
    image_bytes: bytes,
    content_type: str = "image/svg+xml",
    title: str,
    delete_image: ImageDeleter | None = None,
    max_pages: int = 100,
) -> tuple[ManagedImageIdentity, ManagedImageReplaceReceipt]:
    """Run a create-verify-delete saga; no provider-global atomicity is claimed."""

    require_replace_capabilities(capabilities, external_delete_available=delete_image is not None)
    media_type = validate_content_type(content_type)
    safe_title = validate_image_title(title)
    if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
        raise MiroToolError("managed image bytes are outside the supported bound")
    digest = source_sha256(image_bytes)
    if digest == identity.source_sha256:
        raise MiroToolError("managed image replacement requires changed source bytes")

    before, before_pages = await list_all_images(
        call_tool, board_url=board_url, max_pages=max_pages
    )
    before_by_id = _indexed(before)
    old_item = before_by_id.get(identity.item_id)
    if old_item is None:
        raise MiroToolError("managed image precondition failed: old item is absent")
    if not _same_geometry(old_item, identity):
        raise MiroToolError("managed image precondition failed: old geometry drifted")

    parent_url = _item_url(board_url, identity.parent_id)
    upload = await call_tool(
        "image_get_upload_url",
        {
            "miro_url": parent_url,
            "content_type": media_type,
            "title": safe_title,
            "x": identity.x,
            "y": identity.y,
            "width": identity.width,
            "invocation_source": "schauwerk-managed-image-lifecycle",
            "is_repository": True,
        },
    )
    if bool(getattr(upload, "isError", False)):
        raise MiroToolError("Miro image upload URL reported an error")
    upload_payload = result_payload(upload)
    upload_url = upload_payload.get("upload_url")
    image_token = upload_payload.get("token")
    if not isinstance(upload_url, str) or not isinstance(image_token, str):
        raise MiroToolError("Miro image upload contract is invalid")

    transferred = await upload_bytes(upload_url, media_type, image_bytes)
    if transferred is not True:
        raise MiroToolError("Miro image byte upload did not succeed")

    try:
        created = await call_tool(
            "image_create",
            {
                "miro_url": parent_url,
                "image_token": image_token,
                "invocation_source": "schauwerk-managed-image-lifecycle",
                "is_repository": True,
            },
        )
    except Exception as exc:
        raise ManagedImageReconciliationRequired(
            "Miro image creation outcome is uncertain; manual reconciliation required"
        ) from exc
    if bool(getattr(created, "isError", False)):
        raise ManagedImageReconciliationRequired(
            "Miro image creation reported an uncertain outcome; manual reconciliation required"
        )
    try:
        new_item_id = _item_id_from_url(result_payload(created).get("miro_url"))
    except MiroToolError as exc:
        raise ManagedImageReconciliationRequired(
            "Miro image creation returned no reconcilable item id"
        ) from exc
    if new_item_id in before_by_id:
        raise ManagedImageReconciliationRequired(
            "Miro image create reused an existing item id; manual reconciliation required"
        )

    try:
        staged, staged_pages = await list_all_images(
            call_tool, board_url=board_url, max_pages=max_pages
        )
    except Exception:
        await _compensate_new_image(
            call_tool,
            capabilities=capabilities,
            board_url=board_url,
            identity=identity,
            new_item_id=new_item_id,
            delete_image=delete_image,
            before_count=len(before),
            max_pages=max_pages,
        )
        raise MiroToolError("new managed image staging readback failed and was safely compensated")
    staged_by_id = _indexed(staged)
    new_item = staged_by_id.get(new_item_id)
    old_still_present = staged_by_id.get(identity.item_id)
    staged_valid = (
        new_item is not None
        and _same_geometry(new_item, identity)
        and old_still_present is not None
        and _same_geometry(old_still_present, identity)
        and len(staged) == len(before) + 1
    )
    if not staged_valid:
        await _compensate_new_image(
            call_tool,
            capabilities=capabilities,
            board_url=board_url,
            identity=identity,
            new_item_id=new_item_id,
            delete_image=delete_image,
            before_count=len(before),
            max_pages=max_pages,
        )
        raise MiroToolError("new managed image failed staging readback and was safely compensated")

    try:
        delete_receipt = await _delete_item(
            call_tool,
            capabilities=capabilities,
            board_url=board_url,
            item_id=identity.item_id,
            delete_image=delete_image,
            allow_absent=False,
        )
    except Exception as exc:
        raise ManagedImageReconciliationRequired(
            "old managed image deletion is uncertain; manual reconciliation required"
        ) from exc

    after, after_pages = await list_all_images(call_tool, board_url=board_url, max_pages=max_pages)
    after_by_id = _indexed(after)
    old_absent = identity.item_id not in after_by_id
    new_present = new_item_id in after_by_id
    geometry_matches = new_present and _same_geometry(after_by_id[new_item_id], identity)
    if not old_absent or not new_present or not geometry_matches or len(after) != len(before):
        raise ManagedImageReconciliationRequired(
            "managed image replacement postcondition failed; manual reconciliation required"
        )

    replacement = ManagedImageIdentity(
        board_alias=identity.board_alias,
        asset_key=identity.asset_key,
        item_id=new_item_id,
        parent_id=identity.parent_id,
        source_sha256=digest,
        x=identity.x,
        y=identity.y,
        width=identity.width,
    )
    delete_receipt = {**delete_receipt, "postflight_absent": True}
    receipt = ManagedImageReplaceReceipt(
        success=True,
        board_alias=identity.board_alias,
        asset_key=identity.asset_key,
        old_item_id=identity.item_id,
        new_item_id=new_item_id,
        source_sha256=digest,
        before_count=len(before),
        after_count=len(after),
        old_item_absent=old_absent,
        new_item_present=new_present,
        geometry_matches=bool(geometry_matches),
        inventory_pages=before_pages + staged_pages + after_pages,
        delete_receipt=delete_receipt,
    )
    return replacement, receipt


async def delete_managed_image(
    call_tool: ToolCaller,
    *,
    capabilities: set[str],
    board_url: str,
    identity: ManagedImageIdentity,
    delete_image: ImageDeleter | None = None,
    max_pages: int = 100,
) -> ManagedImageDeleteReceipt:
    """Delete only the exact image represented by one managed identity."""

    require_delete_capabilities(capabilities, external_delete_available=delete_image is not None)
    before, before_pages = await list_all_images(
        call_tool, board_url=board_url, max_pages=max_pages
    )
    before_by_id = _indexed(before)
    old = before_by_id.get(identity.item_id)
    if old is None or not _same_geometry(old, identity):
        raise MiroToolError("managed image delete precondition failed")
    try:
        delete_receipt = await _delete_item(
            call_tool,
            capabilities=capabilities,
            board_url=board_url,
            item_id=identity.item_id,
            delete_image=delete_image,
            allow_absent=False,
        )
    except Exception as exc:
        raise ManagedImageReconciliationRequired(
            "managed image delete outcome is uncertain; manual reconciliation required"
        ) from exc
    after, after_pages = await list_all_images(call_tool, board_url=board_url, max_pages=max_pages)
    old_absent = identity.item_id not in _indexed(after)
    if not old_absent or len(after) != len(before) - 1:
        raise ManagedImageReconciliationRequired(
            "managed image delete postcondition failed; manual reconciliation required"
        )
    delete_receipt = {**delete_receipt, "postflight_absent": True}
    return ManagedImageDeleteReceipt(
        success=True,
        board_alias=identity.board_alias,
        asset_key=identity.asset_key,
        old_item_id=identity.item_id,
        before_count=len(before),
        after_count=len(after),
        old_item_absent=True,
        inventory_pages=before_pages + after_pages,
        delete_receipt=delete_receipt,
    )
