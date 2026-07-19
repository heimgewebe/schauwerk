from __future__ import annotations

from schauwerk.surfaces.miro.capability_fallbacks import (
    BASELINE_TOOLS,
    LAYOUT_TOOLS,
    compile_creation_fallback,
    resolve_bundle_operations,
)


def creation_operations() -> list[dict]:
    return [
        {
            "operation_id": "doc",
            "kind": "document",
            "content": 'Titel\nText mit "Zitat" und <b>Markup</b>',
            "x": 10,
            "y": 20,
        },
        {
            "operation_id": "table",
            "kind": "table",
            "table_title": "Status",
            "columns": [
                {"column_type": "text", "column_title": "Name", "isTitle": True},
                {"column_type": "text", "column_title": "Wert"},
            ],
            "rows": [
                {
                    "cells": [
                        {"columnTitle": "Name", "value": "Qualität"},
                        {"columnTitle": "Wert", "value": "100"},
                    ]
                }
            ],
            "view": {"type": "group_by", "column": "Name"},
        },
        {
            "operation_id": "code",
            "kind": "code_widget",
            "title": "Prüfung",
            "language": "Python",
            "code": "print('ok')",
        },
        {
            "operation_id": "prototype",
            "kind": "prototype",
            "screens": [{"path": "screen.html", "sha256": "a" * 64}],
            "device_type": "desktop",
            "orientation": "landscape",
        },
    ]


def test_creation_fallbacks_are_deterministic_layout_operations() -> None:
    for operation in creation_operations():
        first = compile_creation_fallback(operation)
        second = compile_creation_fallback(operation)
        assert first == second
        assert first["operation_id"] == operation["operation_id"]
        assert first["kind"] == "layout"
        assert first["dsl"]
        assert first["provider_fallback"]["original_kind"] == operation["kind"]
        assert len(first["provider_fallback"]["source_operation_digest"]) == 64
        assert "<b>" not in first["dsl"]
        if operation["kind"] == "table":
            assert "Ansicht:" in first["dsl"]
            assert "group_by" in first["dsl"]


def test_resolution_uses_fallback_only_when_native_tools_are_missing() -> None:
    observed = set(BASELINE_TOOLS | LAYOUT_TOOLS)
    report = resolve_bundle_operations(creation_operations(), observed)
    assert report["blocked_count"] == 0
    assert report["native_count"] == 0
    assert report["fallback_count"] == 4
    assert {item["mode"] for item in report["operation_resolutions"]} == {"fallback"}
    assert {item["kind"] for item in report["execution_operations"]} == {"layout"}
    assert report["truth_boundary"]["fallbacks_are_creation_only"] is True
    assert report["truth_boundary"]["fallbacks_preserve_native_item_type"] is False


def test_native_toolset_wins_over_fallback() -> None:
    operation = creation_operations()[0]
    observed = set(BASELINE_TOOLS | LAYOUT_TOOLS | {"doc_create", "doc_get"})
    report = resolve_bundle_operations([operation], observed)
    assert report["native_count"] == 1
    assert report["fallback_count"] == 0
    assert report["execution_operations"] == [operation]


def test_updates_deletes_and_history_remain_fail_closed() -> None:
    operations = [
        {
            "operation_id": "doc-update",
            "kind": "document_update",
            "target_miro_url": "https://miro.com/app/board/x/item/y/",
            "expected_content_sha256": "a" * 64,
            "old_content": "old",
            "new_content": "new",
        },
        {
            "operation_id": "history",
            "kind": "table_history",
            "target_miro_url": "https://miro.com/app/board/x/item/y/",
            "row_id": "row",
        },
        {
            "operation_id": "delete",
            "kind": "code_widget_delete",
            "target_miro_url": "https://miro.com/app/board/x/item/y/",
            "expected_before": {"code": "x"},
        },
    ]
    report = resolve_bundle_operations(operations, set(BASELINE_TOOLS | LAYOUT_TOOLS))
    assert report["fallback_count"] == 0
    assert report["blocked_count"] == 3
    assert all(item["mode"] == "blocked" for item in report["operation_resolutions"])


def test_missing_baseline_blocks_every_operation() -> None:
    report = resolve_bundle_operations([creation_operations()[0]], set(LAYOUT_TOOLS))
    assert report["blocked_count"] == 1
    assert report["baseline_missing_tools"]
