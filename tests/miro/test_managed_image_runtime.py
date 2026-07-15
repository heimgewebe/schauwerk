from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
from schauwerk.surfaces.miro.managed_image_runtime import (
    ManagedImageIdentity,
    ManagedImageReconciliationRequired,
    delete_managed_image,
    list_all_images,
    replace_managed_image,
    require_delete_capabilities,
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
    item_id: str,
    *,
    parent_id: str = "10",
    x: float = 1200,
    y: float = 920,
    width: float = 2200,
) -> dict:
    return {
        "id": item_id,
        "type": "image",
        "parent": {"id": parent_id},
        "position": {"x": x, "y": y},
        "geometry": {"width": width, "height": 1000},
        "miro_url": f"https://miro.com/app/board/x/?moveToWidget={item_id}",
    }


def capabilities(*, native_delete: bool = True) -> set[str]:
    values = {"board_list_items", "image_get_upload_url", "image_create"}
    if native_delete:
        values.add("image_delete")
    return values


def test_replace_and_delete_accept_separate_delete_authority() -> None:
    require_replace_capabilities(capabilities(native_delete=False), external_delete_available=True)
    require_delete_capabilities({"board_list_items"}, external_delete_available=True)
    with pytest.raises(MiroToolError, match="separate REST deleter"):
        require_replace_capabilities(capabilities(native_delete=False))


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
    assert receipt.globally_atomic is False
    assert receipt.provider_semantics == "create-verify-delete-saga"
    assert calls == [
        "board_list_items",
        "image_get_upload_url",
        "image_create",
        "board_list_items",
        "image_delete",
        "board_list_items",
    ]


def test_wrong_geometry_is_compensated_and_old_item_is_proven_retained() -> None:
    inventories = [
        [image("100")],
        [image("100"), image("200", x=999)],
        [image("100")],
    ]
    deleted: list[tuple[str, bool]] = []

    async def call_tool(name: str, _arguments: dict):
        if name == "board_list_items":
            return result({"data": inventories.pop(0)})
        if name == "image_get_upload_url":
            return result({"upload_url": "https://upload.invalid/one", "token": "token"})
        if name == "image_create":
            return result({"miro_url": "https://miro.com/app/board/x/?moveToWidget=200"})
        raise AssertionError(name)

    async def delete(item_id: str, allow_absent: bool) -> dict:
        deleted.append((item_id, allow_absent))
        return {
            "success": True,
            "item_id": item_id,
            "preflight_present": False,
            "delete_status": None,
            "postflight_absent": True,
            "reconciled_after_uncertain_delete": False,
        }

    with pytest.raises(MiroToolError, match="safely compensated"):
        asyncio.run(
            replace_managed_image(
                call_tool,
                lambda *_args: asyncio.sleep(0, result=True),
                capabilities=capabilities(native_delete=False),
                board_url="https://miro.com/app/board/x=/",
                identity=identity(),
                image_bytes=b"new",
                title="Operator core",
                delete_image=delete,
            )
        )
    assert deleted == [("200", True)]


def test_failed_compensation_requires_manual_reconciliation() -> None:
    inventories = [[image("100")], [image("100"), image("200", x=999)]]

    async def call_tool(name: str, _arguments: dict):
        if name == "board_list_items":
            return result({"data": inventories.pop(0)})
        if name == "image_get_upload_url":
            return result({"upload_url": "https://upload.invalid/one", "token": "token"})
        if name == "image_create":
            return result({"miro_url": "https://miro.com/app/board/x/?moveToWidget=200"})
        raise AssertionError(name)

    async def delete(_item_id: str, _allow_absent: bool) -> dict:
        raise MiroToolError("delete uncertain")

    with pytest.raises(ManagedImageReconciliationRequired, match="manual reconciliation"):
        asyncio.run(
            replace_managed_image(
                call_tool,
                lambda *_args: asyncio.sleep(0, result=True),
                capabilities=capabilities(native_delete=False),
                board_url="https://miro.com/app/board/x=/",
                identity=identity(),
                image_bytes=b"new",
                title="Operator core",
                delete_image=delete,
            )
        )


def test_inventory_paginates_and_rejects_repeated_cursor_or_duplicate_id() -> None:
    pages = [
        {"data": [image("100")], "has_more": True, "nextCursor": "next"},
        {"data": [image("200")], "has_more": False},
    ]

    async def paged(_name: str, _arguments: dict):
        return result(pages.pop(0))

    items, count = asyncio.run(list_all_images(paged, board_url="https://miro.com/app/board/x=/"))
    assert [item["id"] for item in items] == ["100", "200"]
    assert count == 2

    repeated = [
        {"data": [image("100")], "has_more": True, "nextCursor": "same"},
        {"data": [image("200")], "has_more": True, "nextCursor": "same"},
    ]

    async def repeated_cursor(_name: str, _arguments: dict):
        return result(repeated.pop(0))

    with pytest.raises(MiroToolError, match="repeated image cursor"):
        asyncio.run(list_all_images(repeated_cursor, board_url="https://miro.com/app/board/x=/"))

    duplicate = [{"data": [image("100"), image("100")], "has_more": False}]

    async def duplicate_id(_name: str, _arguments: dict):
        return result(duplicate.pop(0))

    with pytest.raises(MiroToolError, match="duplicate item id"):
        asyncio.run(list_all_images(duplicate_id, board_url="https://miro.com/app/board/x=/"))


def test_delete_uses_only_inventory_and_external_delete_authority() -> None:
    inventories = [[image("100")], []]

    async def call_tool(name: str, _arguments: dict):
        assert name == "board_list_items"
        return result({"data": inventories.pop(0)})

    async def delete(item_id: str, allow_absent: bool) -> dict:
        assert item_id == "100"
        assert allow_absent is False
        return {
            "success": True,
            "item_id": item_id,
            "preflight_present": True,
            "delete_status": 204,
            "postflight_absent": True,
            "reconciled_after_uncertain_delete": False,
        }

    receipt = asyncio.run(
        delete_managed_image(
            call_tool,
            capabilities={"board_list_items"},
            board_url="https://miro.com/app/board/x=/",
            identity=identity(),
            delete_image=delete,
        )
    )
    assert receipt.success is True
    assert receipt.before_count == 1
    assert receipt.after_count == 0


def test_postcondition_rejects_count_drift_as_manual_reconciliation() -> None:
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

    with pytest.raises(ManagedImageReconciliationRequired, match="postcondition"):
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


def test_external_delete_receipt_must_match_expected_item() -> None:
    inventories = [[image("100")]]

    async def call_tool(name: str, _arguments: dict):
        assert name == "board_list_items"
        return result({"data": inventories.pop(0)})

    async def delete(_item_id: str, _allow_absent: bool) -> dict:
        return {
            "success": True,
            "item_id": "999",
            "preflight_present": True,
            "delete_status": 204,
            "postflight_absent": True,
            "reconciled_after_uncertain_delete": False,
        }

    with pytest.raises(ManagedImageReconciliationRequired, match="uncertain"):
        asyncio.run(
            delete_managed_image(
                call_tool,
                capabilities={"board_list_items"},
                board_url="https://miro.com/app/board/x=/",
                identity=identity(),
                delete_image=delete,
            )
        )


@pytest.mark.parametrize(
    "override",
    [
        {"item_id": "1" * 33},
        {"parent_id": "2" * 33},
        {"x": float("nan")},
        {"y": float("inf")},
        {"width": 1_000_001},
    ],
)
def test_identity_rejects_values_outside_schema_contract(override: dict) -> None:
    values = {
        "board_alias": "operator-map",
        "asset_key": "operator-core",
        "item_id": "100",
        "parent_id": "10",
        "source_sha256": source_sha256(b"old"),
        "x": 1200,
        "y": 920,
        "width": 2200,
    }
    values.update(override)
    with pytest.raises(ValueError):
        ManagedImageIdentity(**values)
