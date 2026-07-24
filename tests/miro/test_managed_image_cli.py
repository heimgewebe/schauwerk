from __future__ import annotations

import json
from pathlib import Path

from schauwerk import runner
from schauwerk.cli_handlers import (
    handle_capability_audit,
    handle_managed_image_check,
    handle_rest_status,
    handle_rest_token_install,
)
from schauwerk.surfaces.miro.managed_image_runtime import (
    ManagedImageIdentity,
    source_sha256,
)
from schauwerk.surfaces.miro.rest_client import MiroRestClient
from schauwerk.surfaces.miro.rest_credentials import (
    MiroRestSettings,
    MiroRestTokenStorage,
)

TOKEN = "rest-token-abcdefghijklmnopqrstuvwxyz-0123456789"


def write_identity(tmp_path: Path) -> Path:
    path = tmp_path / "identity.json"
    value = ManagedImageIdentity(
        board_alias="operator-map",
        asset_key="operator-core",
        item_id="100",
        parent_id="10",
        source_sha256=source_sha256(b"old"),
        x=1200,
        y=920,
        width=2200,
    ).to_document()
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_handlers_install_status_and_check_without_network(tmp_path: Path) -> None:
    settings = MiroRestSettings(state_root=tmp_path / "rest-state")
    storage = MiroRestTokenStorage(settings)
    source = tmp_path / "source-token"
    source.write_text(TOKEN + "\n", encoding="utf-8")
    source.chmod(0o600)

    installed = handle_rest_token_install(source=str(source), storage=storage)
    status = handle_rest_status(MiroRestClient(settings, storage))
    identity = write_identity(tmp_path)
    image = tmp_path / "new.svg"
    image.write_bytes(b"new")
    checked = handle_managed_image_check(
        alias="operator-map",
        identity=str(identity),
        image=str(image),
        content_type="image/svg+xml",
    )

    assert installed["installed"] is True
    assert status["credential"]["exists"] is True
    assert status["live_authorized_known"] is False
    assert TOKEN not in repr(installed)
    assert TOKEN not in repr(status)
    assert checked["source_changed"] is True


def test_capability_handler_uses_live_rest_capability_status() -> None:
    class ToolResult:
        def to_dict(self):
            return {
                "tools": [
                    {"name": name, "input_schema": {"type": "object"}}
                    for name in (
                        "board_list_items",
                        "image_create",
                        "image_get_upload_url",
                    )
                ],
                "protocol_version": "test",
                "server_name": "Miro MCP",
                "server_version": "test",
            }

    class FakeMiro:
        async def tools(self):
            return ToolResult()

    class FakeRest:
        async def capability_status(self):
            return {
                "credential": {"exists": True},
                "live_authorized_known": True,
                "live_authorized": True,
                "boards_write_authorized": True,
            }

    report = handle_capability_audit(FakeMiro(), FakeRest())

    assert report["cross_surface_lanes"]["managed_image_lifecycle"]["available"] is True
    assert report["high_value_lanes"]["managed_image_lifecycle"]["mode"] == "cross_surface"


def test_runner_dispatches_rest_commands(monkeypatch, capsys) -> None:
    observed: list[tuple[str, object]] = []

    monkeypatch.setattr(
        runner,
        "handle_rest_status",
        lambda: {"schema_version": "rest-status", "ok": True},
    )

    def install(*, source: str, replace: bool):
        observed.append((source, replace))
        return {"installed": True}

    monkeypatch.setattr(runner, "handle_rest_token_install", install)

    def doctor(*, require_write: bool):
        observed.append(("doctor", require_write))
        return {"boards_write_authorized": require_write}

    monkeypatch.setattr(runner, "handle_rest_doctor", doctor)

    assert runner.main(["miro", "rest", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert runner.main(["miro", "rest", "token-install", "source.file", "--replace", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] is True
    assert runner.main(["miro", "rest", "doctor", "--require-write", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["boards_write_authorized"] is True
    assert observed == [("source.file", True), ("doctor", True)]


def test_runner_dispatches_managed_image_commands(monkeypatch, capsys) -> None:
    observed: list[tuple[str, dict]] = []

    def checked(**kwargs):
        observed.append(("check", kwargs))
        return {"ok": True}

    def replaced(**kwargs):
        observed.append(("replace", kwargs))
        return {"success": True}

    def deleted(**kwargs):
        observed.append(("delete", kwargs))
        return {"success": True}

    monkeypatch.setattr(runner, "handle_managed_image_check", checked)
    monkeypatch.setattr(runner, "handle_managed_image_replace", replaced)
    monkeypatch.setattr(runner, "handle_managed_image_delete", deleted)

    assert (
        runner.main(
            [
                "miro",
                "managed-image",
                "check",
                "operator-map",
                "identity.json",
                "--image",
                "new.svg",
                "--content-type",
                "image/svg+xml",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True

    assert (
        runner.main(
            [
                "miro",
                "managed-image",
                "replace",
                "operator-map",
                "identity.json",
                "new.svg",
                "--content-type",
                "image/svg+xml",
                "--title",
                "Operator core",
                "--receipt-output",
                "receipt.json",
                "--identity-output",
                "next.json",
                "--max-pages",
                "12",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["success"] is True

    assert (
        runner.main(
            [
                "miro",
                "managed-image",
                "delete",
                "operator-map",
                "identity.json",
                "--receipt-output",
                "delete.json",
                "--max-pages",
                "9",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["success"] is True

    assert observed == [
        (
            "check",
            {
                "alias": "operator-map",
                "identity": "identity.json",
                "image": "new.svg",
                "content_type": "image/svg+xml",
            },
        ),
        (
            "replace",
            {
                "alias": "operator-map",
                "identity": "identity.json",
                "image": "new.svg",
                "content_type": "image/svg+xml",
                "title": "Operator core",
                "receipt_output": "receipt.json",
                "identity_output": "next.json",
                "max_pages": 12,
            },
        ),
        (
            "delete",
            {
                "alias": "operator-map",
                "identity": "identity.json",
                "receipt_output": "delete.json",
                "max_pages": 9,
            },
        ),
    ]
