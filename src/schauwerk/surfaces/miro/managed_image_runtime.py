"""Fail-closed orchestration for replacing Schauwerk-managed Miro images."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from .errors import MiroToolError
from .inspection import result_payload

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]
ByteUploader = Callable[[str, str, bytes], Awaitable[bool]]

_REQUIRED_TOOLS = frozenset(
    {"board_list_items", "image_get_upload_url", "image_create", "image_delete"}
)


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
        if not self.board_alias or not self.asset_key:
            raise ValueError("managed image identity requires board_alias and asset_key")
        if not self.item_id.isdigit() or not self.parent_id.isdigit():
            raise ValueError("managed image identity requires numeric Miro item ids")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("source_sha256 must be lowercase SHA-256")
        if self.width <= 0:
            raise ValueError("managed image width must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ManagedImageReplaceReceipt:
    success: bool
    old_item_id: str
    new_item_id: str
    source_sha256: str
    before_count: int
    after_count: int
    old_item_absent: bool
    new_item_present: bool
    geometry_matches: bool
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_replace_capabilities(capabilities: set[str]) -> None:
    missing = sorted(_REQUIRED_TOOLS - capabilities)
    if missing:
        raise MiroToolError(
            "Miro managed image replacement is unavailable; missing provider tools: "
            + ", ".join(missing)
        )


def _items(result: Any) -> list[dict[str, Any]]:
    if bool(getattr(result, "isError", False)):
        raise MiroToolError("Miro image inventory reported an error")
    payload = result_payload(result)
    data = payload.get("data")
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise MiroToolError("Miro image inventory returned an invalid payload")
    return data


def _item_id_from_url(value: Any) -> str:
    if not isinstance(value, str) or "moveToWidget=" not in value:
        raise MiroToolError("Miro image create did not return an item URL")
    item_id = value.split("moveToWidget=", 1)[1].split("&", 1)[0]
    if not item_id.isdigit():
        raise MiroToolError("Miro image create returned an invalid item id")
    return item_id


def _same_geometry(item: dict[str, Any], identity: ManagedImageIdentity) -> bool:
    position = item.get("position")
    geometry = item.get("geometry")
    parent = item.get("parent")
    if not isinstance(position, dict) or not isinstance(geometry, dict):
        return False
    if not isinstance(parent, dict) or str(parent.get("id")) != identity.parent_id:
        return False
    values = (position.get("x"), position.get("y"), geometry.get("width"))
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        return False
    return (
        abs(float(values[0]) - identity.x) < 0.01
        and abs(float(values[1]) - identity.y) < 0.01
        and abs(float(values[2]) - identity.width) < 0.01
    )


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
) -> tuple[ManagedImageIdentity, ManagedImageReplaceReceipt]:
    """Create, verify, delete, and re-verify one managed image.

    The old image is deleted only after the new item is visible with exact parent,
    position, and width. Any unsupported or ambiguous provider response fails closed.
    """

    require_replace_capabilities(capabilities)
    digest = source_sha256(image_bytes)
    if digest == identity.source_sha256:
        raise MiroToolError("managed image replacement requires changed source bytes")

    inventory_args = {
        "miro_url": board_url,
        "limit": 100,
        "item_type": "image",
        "invocation_source": "schauwerk-managed-image-replace",
        "is_repository": True,
    }
    before = _items(await call_tool("board_list_items", inventory_args))
    before_ids = {str(item.get("id")) for item in before}
    if identity.item_id not in before_ids:
        raise MiroToolError("managed image precondition failed: old item is absent")

    parent_url = board_url.rstrip("/") + "/?moveToWidget=" + identity.parent_id
    upload = await call_tool(
        "image_get_upload_url",
        {
            "miro_url": parent_url,
            "content_type": content_type,
            "title": title,
            "x": identity.x,
            "y": identity.y,
            "width": identity.width,
            "invocation_source": "schauwerk-managed-image-replace",
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

    transferred = await upload_bytes(upload_url, content_type, image_bytes)
    if transferred is not True:
        raise MiroToolError("Miro image byte upload did not succeed")

    created = await call_tool(
        "image_create",
        {
            "miro_url": parent_url,
            "image_token": image_token,
            "invocation_source": "schauwerk-managed-image-replace",
            "is_repository": True,
        },
    )
    if bool(getattr(created, "isError", False)):
        raise MiroToolError("Miro image create reported an error")
    new_item_id = _item_id_from_url(result_payload(created).get("miro_url"))

    staged = _items(await call_tool("board_list_items", inventory_args))
    staged_by_id = {str(item.get("id")): item for item in staged}
    new_item = staged_by_id.get(new_item_id)
    if new_item is None or not _same_geometry(new_item, identity):
        raise MiroToolError("new managed image failed geometry readback; old item retained")

    deleted = await call_tool(
        "image_delete",
        {
            "miro_url": board_url.rstrip("/") + "/?moveToWidget=" + identity.item_id,
            "invocation_source": "schauwerk-managed-image-replace",
            "is_repository": True,
        },
    )
    if (
        bool(getattr(deleted, "isError", False))
        or result_payload(deleted).get("success") is not True
    ):
        raise MiroToolError("old managed image deletion failed after new image creation")

    after = _items(await call_tool("board_list_items", inventory_args))
    after_by_id = {str(item.get("id")): item for item in after}
    old_absent = identity.item_id not in after_by_id
    new_present = new_item_id in after_by_id
    geometry_matches = new_present and _same_geometry(after_by_id[new_item_id], identity)
    if not old_absent or not new_present or not geometry_matches or len(after) != len(before):
        raise MiroToolError("managed image replacement postcondition failed")

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
    receipt = ManagedImageReplaceReceipt(
        success=True,
        old_item_id=identity.item_id,
        new_item_id=new_item_id,
        source_sha256=digest,
        before_count=len(before),
        after_count=len(after),
        old_item_absent=old_absent,
        new_item_present=new_present,
        geometry_matches=geometry_matches,
    )
    return replacement, receipt
