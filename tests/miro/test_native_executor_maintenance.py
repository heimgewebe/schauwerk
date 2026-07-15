from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest

from schauwerk.surfaces.miro.errors import MiroConnectionError
from schauwerk.surfaces.miro.native_executor import (
    NativeExecutionError,
    execute_native_bundle,
    required_tools,
    validate_native_bundle,
)
from schauwerk.surfaces.miro.native_runtime import _validated_upload_url

BOARD_URL = "https://miro.com/app/board/uXjVMaintenanceTest=/"
DOC_URL = f"{BOARD_URL}?moveToWidget=document"
CODE_A_URL = f"{BOARD_URL}?moveToWidget=code-a"
CODE_B_URL = f"{BOARD_URL}?moveToWidget=code-b"
PROTOTYPE_URL = f"{BOARD_URL}?moveToWidget=prototype"


def catalogue(*names: str) -> list[dict]:
    return [
        {
            "name": name,
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
        }
        for name in names
    ]


def digest_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return hashlib.sha256(normalized.encode()).hexdigest()


class MaintenanceMiro:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.uploads: list[tuple[str, bytes]] = []
        self.document = "# Betriebsstand\n\nAlt"
        self.document_version = 4
        self.prototype_created = False
        self.widgets = {
            CODE_A_URL: {
                "miro_url": CODE_A_URL,
                "code": "flowchart LR\n  A --> B",
                "language": "Mermaid",
                "title": "Quelle A",
                "line_numbers_visible": True,
                "width": 800,
                "height": 400,
                "x": 100,
                "y": 200,
                "success": True,
                "message": "ok",
            },
            CODE_B_URL: {
                "miro_url": CODE_B_URL,
                "code": "flowchart LR\n  B --> C",
                "language": "Mermaid",
                "title": "Quelle B",
                "line_numbers_visible": True,
                "width": 800,
                "height": 400,
                "x": 500,
                "y": 200,
                "success": True,
                "message": "ok",
            },
        }

    async def upload(self, url: str, payload: bytes) -> None:
        self.uploads.append((url, payload))

    async def __call__(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, copy.deepcopy(arguments)))
        if tool == "user_who_am_i":
            return {
                "org_id": "org",
                "team_id": "team",
                "user_id": "user",
                "workspace_id": "workspace",
            }
        if tool == "board_list_items":
            items = [
                {"id": "document", "type": "doc_format"},
                *[{"id": url.rsplit("=", 1)[-1], "type": "code"} for url in sorted(self.widgets)],
            ]
            if self.prototype_created:
                items.append({"id": "prototype", "type": "preview"})
            return {
                "data": items,
                "total": len(items),
                "has_more": False,
                "nextCursor": None,
            }
        if tool == "context_explore":
            return {"items": [{"miro_url": DOC_URL, "title": "Betriebsstand", "type": "document"}]}
        if tool == "doc_get":
            return {
                "miro_url": arguments["miro_url"],
                "content": self.document,
                "content_version": self.document_version,
                "success": True,
                "message": "ok",
            }
        if tool == "doc_update":
            old = arguments["old_content"]
            count = -1 if arguments.get("replace_all") else 1
            self.document = self.document.replace(old, arguments["new_content"], count)
            self.document_version += 1
            return {
                "miro_url": arguments["miro_url"],
                "content_version": self.document_version,
                "success": True,
                "message": "updated",
            }
        if tool == "table_get_latest_update_history":
            return {
                "miro_url": arguments["miro_url"],
                "entries": [
                    {
                        "text": "Erfasst",
                        "author_id": "user",
                        "created_at": "2026-07-15T05:00:00Z",
                        "modified_at": "2026-07-15T05:00:00Z",
                    },
                    {
                        "text": "Verifiziert",
                        "author_id": "user",
                        "created_at": "2026-07-15T05:01:00Z",
                        "modified_at": "2026-07-15T05:01:00Z",
                    },
                ],
                "total": 2,
            }
        if tool == "code_widget_list_items":
            ordered = [copy.deepcopy(self.widgets[url]) for url in sorted(self.widgets)]
            cursor = arguments.get("cursor")
            if len(ordered) > 1 and cursor is None:
                page = ordered[:1]
                next_cursor = "page-2"
            elif cursor == "page-2":
                page = ordered[1:]
                next_cursor = None
            else:
                page = ordered
                next_cursor = None
            return {
                "items": page,
                "cursor": next_cursor,
                "total": len(ordered),
                "success": True,
                "message": "ok",
            }
        if tool == "code_widget_get":
            return copy.deepcopy(self.widgets[arguments["miro_url"]])
        if tool == "code_widget_update":
            widget = self.widgets[arguments["miro_url"]]
            for key in (
                "code",
                "language",
                "title",
                "line_numbers_visible",
                "width",
                "x",
                "y",
            ):
                if key in arguments:
                    widget[key] = arguments[key]
            return {
                "miro_url": arguments["miro_url"],
                "width": widget["width"],
                "x": widget["x"],
                "y": widget["y"],
                "success": True,
                "message": "updated",
            }
        if tool == "code_widget_delete":
            del self.widgets[arguments["miro_url"]]
            return {"success": True, "message": "deleted"}
        if tool == "prototype_get_upload_url":
            return {
                "result": [
                    {
                        "upload_url": "https://upload.invalid/screen-1",
                        "token": "single-use-token",
                        "expires_in": 300,
                    }
                ]
            }
        if tool == "prototype_create":
            assert arguments["html_tokens"] == ["single-use-token"]
            self.prototype_created = True
            return {
                "miro_url": PROTOTYPE_URL,
                "success": True,
                "message": "created",
                "successful_image_count": 0,
                "failed_image_count": 0,
                "failed_image_reason": None,
                "x": arguments.get("x"),
                "y": arguments.get("y"),
            }
        if tool == "context_get":
            return {
                "miro_url": arguments["miro_url"],
                "content": "Prototype with one verified tablet screen",
            }
        raise AssertionError(f"unexpected tool: {tool}")


def maintenance_bundle(screen_sha256: str) -> dict:
    return {
        "schema_version": "schauwerk-miro-native-bundle.v1",
        "bundle_id": "native-maintenance-test-v1",
        "operations": [
            {
                "operation_id": "update-document",
                "kind": "document_update",
                "target_miro_url": DOC_URL,
                "expected_content_sha256": digest_text("# Betriebsstand\n\nAlt"),
                "old_content": "Alt",
                "new_content": "Neu",
                "replace_all": False,
            },
            {
                "operation_id": "read-table-history",
                "kind": "table_history",
                "target_miro_url": f"{BOARD_URL}?moveToWidget=table",
                "row_id": "row_1",
                "expected_min_entries": 2,
                "expected_latest_text": "Verifiziert",
            },
            {
                "operation_id": "inventory-code-widgets",
                "kind": "code_widget_inventory",
                "expected_min_count": 2,
            },
            {
                "operation_id": "update-code-widget",
                "kind": "code_widget_update",
                "target_miro_url": CODE_A_URL,
                "expected_before": {
                    "code": "flowchart LR\n  A --> B",
                    "title": "Quelle A",
                    "width": 800,
                },
                "set": {
                    "code": "flowchart LR\n  A --> C",
                    "title": "Quelle A – aktualisiert",
                    "width": 900,
                },
            },
            {
                "operation_id": "create-prototype",
                "kind": "prototype",
                "screens": [{"path": "screen.html", "sha256": screen_sha256}],
                "device_type": "tablet",
                "orientation": "landscape",
                "x": 1200,
                "y": 400,
            },
            {
                "operation_id": "delete-code-widget",
                "kind": "code_widget_delete",
                "target_miro_url": CODE_B_URL,
                "expected_before": {
                    "code": "flowchart LR\n  B --> C",
                    "title": "Quelle B",
                },
            },
        ],
    }


def test_all_seven_remaining_miro_tools_execute_with_bound_readbacks(tmp_path: Path) -> None:
    screen = b"<!doctype html><html><body><main>Schauwerk</main></body></html>"
    (tmp_path / "screen.html").write_bytes(screen)
    bundle = validate_native_bundle(maintenance_bundle(hashlib.sha256(screen).hexdigest()))
    fake = MaintenanceMiro()

    receipt = asyncio.run(
        execute_native_bundle(
            call_tool=fake,
            tool_catalogue=catalogue(*required_tools(bundle)),
            board_alias="maintenance-test",
            board_url=BOARD_URL,
            bundle=bundle,
            bundle_root=tmp_path,
            upload_html=fake.upload,
        )
    )

    assert receipt["success"] is True
    assert receipt["completed_operation_count"] == 6
    assert receipt["expected_created_item_count"] == 1
    assert receipt["expected_deleted_item_count"] == 1
    assert receipt["expected_net_item_count_delta"] == 0
    assert receipt["observed_item_count_delta"] == 0
    assert fake.document.endswith("Neu")
    assert fake.widgets[CODE_A_URL]["title"] == "Quelle A – aktualisiert"
    assert CODE_B_URL not in fake.widgets
    assert fake.uploads == [("https://upload.invalid/screen-1", screen)]
    required = set(receipt["required_tools"])
    assert {
        "doc_update",
        "table_get_latest_update_history",
        "code_widget_list_items",
        "code_widget_update",
        "code_widget_delete",
        "prototype_get_upload_url",
        "prototype_create",
    } <= required
    serialized = json.dumps(receipt)
    assert "single-use-token" not in serialized
    assert "upload.invalid" not in serialized


def test_document_update_fails_before_mutation_when_content_digest_drifted(
    tmp_path: Path,
) -> None:
    screen = b"<html><body>safe</body></html>"
    (tmp_path / "screen.html").write_bytes(screen)
    raw = maintenance_bundle(hashlib.sha256(screen).hexdigest())
    raw["operations"] = [raw["operations"][0]]
    raw["operations"][0]["expected_content_sha256"] = "0" * 64
    bundle = validate_native_bundle(raw)
    fake = MaintenanceMiro()

    with pytest.raises(NativeExecutionError, match="preflight digest"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=catalogue(*required_tools(bundle)),
                board_alias="maintenance-test",
                board_url=BOARD_URL,
                bundle=bundle,
                bundle_root=tmp_path,
                upload_html=fake.upload,
            )
        )

    assert fake.document.endswith("Alt")
    assert all(tool != "doc_update" for tool, _arguments in fake.calls)


def test_prototype_rejects_local_assets_before_reservation(tmp_path: Path) -> None:
    screen = b'<html><body><img src="./local.png"></body></html>'
    (tmp_path / "screen.html").write_bytes(screen)
    raw = maintenance_bundle(hashlib.sha256(screen).hexdigest())
    raw["operations"] = [raw["operations"][4]]
    bundle = validate_native_bundle(raw)
    fake = MaintenanceMiro()

    with pytest.raises(NativeExecutionError, match="local asset references"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=catalogue(*required_tools(bundle)),
                board_alias="maintenance-test",
                board_url=BOARD_URL,
                bundle=bundle,
                bundle_root=tmp_path,
                upload_html=fake.upload,
            )
        )

    assert all(tool != "prototype_get_upload_url" for tool, _arguments in fake.calls)


def test_prototype_rejects_scripted_html_before_reservation(tmp_path: Path) -> None:
    screen = b'<html><body onclick="alert(1)"><script>alert(1)</script></body></html>'
    (tmp_path / "screen.html").write_bytes(screen)
    raw = maintenance_bundle(hashlib.sha256(screen).hexdigest())
    raw["operations"] = [raw["operations"][4]]
    bundle = validate_native_bundle(raw)
    fake = MaintenanceMiro()

    with pytest.raises(NativeExecutionError, match="static HTML"):
        asyncio.run(
            execute_native_bundle(
                call_tool=fake,
                tool_catalogue=catalogue(*required_tools(bundle)),
                board_alias="maintenance-test",
                board_url=BOARD_URL,
                bundle=bundle,
                bundle_root=tmp_path,
                upload_html=fake.upload,
            )
        )

    assert all(tool != "prototype_get_upload_url" for tool, _arguments in fake.calls)


def test_prototype_upload_url_rejects_private_or_credentialed_targets() -> None:
    assert _validated_upload_url("https://uploads.example.com/object?signature=abc") == (
        "https://uploads.example.com/object?signature=abc"
    )
    for unsafe in (
        "http://uploads.example.com/object",
        "https://127.0.0.1/object",
        "https://10.0.0.1/object",
        "https://user:secret@uploads.example.com/object",
        "https://uploads.local/object",
        "https://uploads.example.com:8443/object",
    ):
        with pytest.raises(MiroConnectionError, match="unsafe"):
            _validated_upload_url(unsafe)
