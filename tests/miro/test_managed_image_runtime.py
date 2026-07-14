from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
from schauwerk.surfaces.miro.managed_image_runtime import (
    ManagedImageIdentity,
    replace_managed_image,
    require_replace_capabilities,
    source_sha256,
)


def result(payload: dict, *, error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=error, structuredContent=payload, content=[])


def identity() -> ManagedImageIdentity:
    return ManagedImageIdentity(
        board_alias="operator-map",
        asset_key="operator-core",
        item_id="100",
        parent_id="10",
        source_sha256=source_sha256(b"old"),
        x=1200,
        y=920,
        width=2200,
    )


def image(
    item_id: str, *, parent_id: str = "10", x: float = 1200, y: float = 920, width: float = 2200
) -> dict:
    return {
        "id": item_id,
        "parent": {"id": parent_id},
        "position": {"x": x, "y": y},
        "geometry": {"width": width, "height": 1000},
        "miro_url": f"https://miro.com/app/board/x/?moveToWidget={item_id}",
    }


def capabilities() -> set[str]:
    return {
        "board_list_items",
        "image_get_upload_url",
        "image_create",
        "image_delete",
    }


def test_requires_real_delete_capability() -> None:
    with pytest.raises(MiroToolError, match="image_delete"):
        require_replace_capabilities(capabilities() - {"image_delete"})


def test_replace_managed_image_is_exact_and_read_back() -> None:
    calls: list[str] = []
    inventories = [[image("100")], [image("100"), image("200")], [image("200")]]

    async def call_tool(name: str, arguments: dict):
        calls.append(name)
        if name == "board_list_items":
            return result({"data": inventories.pop(0)})
        if name == "image_get_upload_url":
            assert arguments["x"] == 1200
            return result({"upload_url": "https://upload.invalid/one", "token": "token"})
        if name == "image_create":
            return result({"miro_url": "https://miro.com/app/board/x/?moveToWidget=200"})
        if name == "image_delete":
            assert arguments["miro_url"].endswith("moveToWidget=100")
            return result({"success": True})
        raise AssertionError(name)

    async def upload_bytes(url: str, content_type: str, data: bytes) -> bool:
        assert url == "https://upload.invalid/one"
        assert content_type == "image/svg+xml"
        assert data == b"new"
        return True

    replacement, receipt = asyncio.run(
        replace_managed_image(
            call_tool,
            upload_bytes,
            capabilities=capabilities(),
            board_url="https://miro.com/app/board/x=/",
            identity=identity(),
            image_bytes=b"new",
            title="Operator core",
        )
    )

    assert replacement.item_id == "200"
    assert replacement.source_sha256 == source_sha256(b"new")
    assert receipt.success is True
    assert receipt.before_count == receipt.after_count == 1
    assert receipt.old_item_absent is True
    assert receipt.new_item_present is True
    assert receipt.geometry_matches is True
    assert calls == [
        "board_list_items",
        "image_get_upload_url",
        "image_create",
        "board_list_items",
        "image_delete",
        "board_list_items",
    ]


def test_old_item_is_retained_when_new_geometry_is_wrong() -> None:
    deleted = False
    inventories = [[image("100")], [image("100"), image("200", x=999)]]

    async def call_tool(name: str, _arguments: dict):
        nonlocal deleted
        if name == "board_list_items":
            return result({"data": inventories.pop(0)})
        if name == "image_get_upload_url":
            return result({"upload_url": "https://upload.invalid/one", "token": "token"})
        if name == "image_create":
            return result({"miro_url": "https://miro.com/app/board/x/?moveToWidget=200"})
        if name == "image_delete":
            deleted = True
            return result({"success": True})
        raise AssertionError(name)

    with pytest.raises(MiroToolError, match="geometry readback"):
        asyncio.run(
            replace_managed_image(
                call_tool,
                lambda *_args: asyncio.sleep(0, result=True),
                capabilities=capabilities(),
                board_url="https://miro.com/app/board/x=/",
                identity=identity(),
                image_bytes=b"new",
                title="Operator core",
            )
        )
    assert deleted is False


def test_postcondition_rejects_count_drift() -> None:
    inventories = [
        [image("100")],
        [image("100"), image("200")],
        [image("200"), image("300")],
    ]

    async def call_tool(name: str, _arguments: dict):
        if name == "board_list_items":
            return result({"data": inventories.pop(0)})
        if name == "image_get_upload_url":
            return result({"upload_url": "https://upload.invalid/one", "token": "token"})
        if name == "image_create":
            return result({"miro_url": "https://miro.com/app/board/x/?moveToWidget=200"})
        if name == "image_delete":
            return result({"success": True})
        raise AssertionError(name)

    with pytest.raises(MiroToolError, match="postcondition"):
        asyncio.run(
            replace_managed_image(
                call_tool,
                lambda *_args: asyncio.sleep(0, result=True),
                capabilities=capabilities(),
                board_url="https://miro.com/app/board/x=/",
                identity=identity(),
                image_bytes=b"new",
                title="Operator core",
            )
        )
