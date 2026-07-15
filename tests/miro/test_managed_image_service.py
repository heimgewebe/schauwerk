from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import schauwerk.surfaces.miro.managed_image_service as service
from schauwerk.surfaces.miro.board_registry import BoardAllowlist
from schauwerk.surfaces.miro.credentials import FileTokenStorage
from schauwerk.surfaces.miro.errors import (
    MiroConnectionError,
    MiroCredentialError,
    MiroToolError,
)
from schauwerk.surfaces.miro.managed_image_runtime import (
    ManagedImageIdentity,
    ManagedImageReconciliationRequired,
    source_sha256,
)
from schauwerk.surfaces.miro.models import MiroSettings
from schauwerk.surfaces.miro.native_runtime import native_asset_lock
from schauwerk.surfaces.miro.rest_client import RestImageDeleteReceipt
from schauwerk.surfaces.miro.rest_credentials import (
    MiroRestSettings,
    MiroRestTokenStorage,
)

BOARD_URL = "https://miro.com/app/board/uXjVManagedTest=/"


def result(payload: dict, *, error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=error, structuredContent=payload, content=[])


def image(item_id: str, *, x: float = 1200) -> dict:
    return {
        "id": item_id,
        "type": "image",
        "parent": {"id": "10"},
        "position": {"x": x, "y": 920},
        "geometry": {"width": 2200, "height": 1000},
    }


def identity_document(item_id: str = "100") -> dict:
    return ManagedImageIdentity(
        board_alias="operator-map",
        asset_key="operator-core",
        item_id=item_id,
        parent_id="10",
        source_sha256=source_sha256(b"old"),
        x=1200,
        y=920,
        width=2200,
    ).to_document()


def write_identity(tmp_path: Path) -> Path:
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(identity_document()), encoding="utf-8")
    path.chmod(0o600)
    return path


def miro_settings(tmp_path: Path) -> MiroSettings:
    settings = MiroSettings(state_root=tmp_path / "miro-state")
    BoardAllowlist(settings.board_allowlist_path).add("operator-map", BOARD_URL)
    return settings


class FakeRest:
    def __init__(self, tmp_path: Path) -> None:
        self.storage = MiroRestTokenStorage(MiroRestSettings(state_root=tmp_path / "rest-state"))
        self.deleted: list[str] = []
        self.doctor_calls = 0

    async def doctor(self, *, require_write: bool = False) -> dict:
        self.doctor_calls += 1
        assert require_write is True
        return {"live_authorized": True, "boards_write_authorized": True}

    async def get_image(self, _board_id: str, item_id: str) -> dict | None:
        return {"id": item_id, "type": "image"}

    async def delete_image(
        self,
        _board_id: str,
        item_id: str,
        *,
        allow_absent: bool = False,
    ) -> RestImageDeleteReceipt:
        self.deleted.append(item_id)
        return RestImageDeleteReceipt(
            success=True,
            item_id=item_id,
            preflight_present=True,
            delete_status=204,
            postflight_absent=True,
            reconciled_after_uncertain_delete=False,
        )


def install_fake_live(monkeypatch: pytest.MonkeyPatch, inventories: list[list[dict]]) -> None:
    async def call_tool(name: str, _arguments: dict):
        if name == "board_list_items":
            return result({"data": inventories.pop(0), "has_more": False})
        if name == "image_get_upload_url":
            return result(
                {"upload_url": "https://upload.example.invalid/image", "token": "image-token"}
            )
        if name == "image_create":
            return result({"miro_url": f"{BOARD_URL}?moveToWidget=200"})
        raise AssertionError(name)

    @asynccontextmanager
    async def fake_live(_settings, _storage):
        yield call_tool, {"board_list_items", "image_get_upload_url", "image_create"}, object()

    async def fake_upload(_client, _url: str, _content_type: str, _payload: bytes) -> bool:
        return True

    monkeypatch.setattr(service, "_live_mcp", fake_live)
    monkeypatch.setattr(service, "_upload_bytes", fake_upload)


def test_check_binds_alias_and_source_digest(tmp_path: Path) -> None:
    identity = write_identity(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"new")

    checked = service.check_managed_image(
        alias="operator-map",
        identity_path=identity,
        image_path=source,
        content_type="image/svg+xml",
    )
    assert checked["source_sha256"] == source_sha256(b"new")
    assert checked["source_changed"] is True
    assert checked["mutation_attempted"] is False

    with pytest.raises(MiroCredentialError, match="board alias"):
        service.check_managed_image(alias="other", identity_path=identity)


def test_replace_publishes_private_identity_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = miro_settings(tmp_path)
    identity = write_identity(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"new")
    receipt = tmp_path / "replace-receipt.json"
    identity_output = tmp_path / "replacement-identity.json"
    rest = FakeRest(tmp_path)
    install_fake_live(
        monkeypatch,
        [[image("100")], [image("100"), image("200")], [image("200")]],
    )

    value = asyncio.run(
        service.run_managed_image_replace(
            settings,
            FileTokenStorage(settings.credentials_path),
            alias="operator-map",
            identity_path=identity,
            image_path=source,
            content_type="image/svg+xml",
            title="Operator core",
            receipt_path=receipt,
            identity_output_path=identity_output,
            rest_client=rest,
        )
    )

    assert value["success"] is True
    assert value["globally_atomic"] is False
    assert value["provider_semantics"] == "create-verify-delete-saga"
    assert rest.deleted == ["100"]
    assert rest.doctor_calls == 1
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert identity_output.stat().st_mode & 0o777 == 0o600
    new_identity = json.loads(identity_output.read_text())
    assert new_identity["item_id"] == "200"
    rendered = receipt.read_text()
    assert BOARD_URL not in rendered
    assert "image-token" not in rendered


def test_failed_staging_is_compensated_and_checkpointed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = miro_settings(tmp_path)
    identity = write_identity(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"new")
    receipt = tmp_path / "failed-receipt.json"
    identity_output = tmp_path / "unused-identity.json"
    rest = FakeRest(tmp_path)
    install_fake_live(
        monkeypatch,
        [[image("100")], [image("100"), image("200", x=999)], [image("100")]],
    )

    with pytest.raises(MiroToolError, match="safely compensated"):
        asyncio.run(
            service.run_managed_image_replace(
                settings,
                FileTokenStorage(settings.credentials_path),
                alias="operator-map",
                identity_path=identity,
                image_path=source,
                content_type="image/svg+xml",
                title="Operator core",
                receipt_path=receipt,
                identity_output_path=identity_output,
                rest_client=rest,
            )
        )
    assert rest.deleted == ["200"]
    assert identity_output.exists() is False
    checkpoint = json.loads(receipt.read_text())
    assert checkpoint["success"] is False
    assert checkpoint["status"] == "failed"
    assert checkpoint["manual_reconciliation_required"] is False


def test_output_collision_fails_before_network(tmp_path: Path) -> None:
    settings = miro_settings(tmp_path)
    identity = write_identity(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"new")
    rest = FakeRest(tmp_path)

    with pytest.raises(MiroCredentialError, match="protected input"):
        asyncio.run(
            service.run_managed_image_replace(
                settings,
                FileTokenStorage(settings.credentials_path),
                alias="operator-map",
                identity_path=identity,
                image_path=source,
                content_type="image/svg+xml",
                title="Operator core",
                receipt_path=identity,
                identity_output_path=tmp_path / "out.json",
                rest_client=rest,
            )
        )
    assert rest.doctor_calls == 0


def test_asset_lock_is_nonblocking(tmp_path: Path) -> None:
    settings = MiroSettings(state_root=tmp_path / "miro-state")
    with native_asset_lock(settings, board_url=BOARD_URL, asset_key="operator-core"):
        with pytest.raises(MiroConnectionError, match="already active"):
            with native_asset_lock(
                settings,
                board_url=BOARD_URL,
                asset_key="operator-core",
            ):
                pass


def test_private_json_publication_is_create_only(tmp_path: Path) -> None:
    destination = tmp_path / "receipt.json"
    service._write_new_private_json(
        destination,
        {"schema_version": "fixture.v1", "value": 1},
        label="fixture receipt",
    )
    original = destination.read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600

    with pytest.raises(MiroCredentialError, match="already exists"):
        service._write_new_private_json(
            destination,
            {"schema_version": "fixture.v1", "value": 2},
            label="fixture receipt",
        )
    assert destination.read_bytes() == original


def test_replace_identity_publication_failure_writes_reconciliation_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = miro_settings(tmp_path)
    identity = write_identity(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"new")
    receipt = tmp_path / "reconciliation-receipt.json"
    identity_output = tmp_path / "replacement-identity.json"
    rest = FakeRest(tmp_path)
    install_fake_live(
        monkeypatch,
        [[image("100")], [image("100"), image("200")], [image("200")]],
    )
    original_write = service._write_new_private_json

    def fail_identity(path: Path, value: dict, *, label: str) -> Path:
        if path == identity_output:
            raise MiroCredentialError("synthetic identity publication failure")
        return original_write(path, value, label=label)

    monkeypatch.setattr(service, "_write_new_private_json", fail_identity)
    with pytest.raises(ManagedImageReconciliationRequired, match="identity"):
        asyncio.run(
            service.run_managed_image_replace(
                settings,
                FileTokenStorage(settings.credentials_path),
                alias="operator-map",
                identity_path=identity,
                image_path=source,
                content_type="image/svg+xml",
                title="Operator core",
                receipt_path=receipt,
                identity_output_path=identity_output,
                rest_client=rest,
            )
        )
    assert identity_output.exists() is False
    checkpoint = json.loads(receipt.read_text())
    assert checkpoint["success"] is False
    assert checkpoint["manual_reconciliation_required"] is True
    assert checkpoint["new_item_id"] == "200"


def test_delete_receipt_publication_failure_requires_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = miro_settings(tmp_path)
    identity = write_identity(tmp_path)
    receipt = tmp_path / "delete-receipt.json"
    rest = FakeRest(tmp_path)
    install_fake_live(monkeypatch, [[image("100")], []])

    def fail_write(_path: Path, _value: dict, *, label: str) -> Path:
        raise MiroCredentialError(f"synthetic {label} failure")

    monkeypatch.setattr(service, "_write_new_private_json", fail_write)
    with pytest.raises(ManagedImageReconciliationRequired, match="deletion succeeded"):
        asyncio.run(
            service.run_managed_image_delete(
                settings,
                FileTokenStorage(settings.credentials_path),
                alias="operator-map",
                identity_path=identity,
                receipt_path=receipt,
                rest_client=rest,
            )
        )
    assert rest.deleted == ["100"]
    assert receipt.exists() is False
