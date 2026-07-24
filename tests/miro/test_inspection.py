from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
from schauwerk.surfaces.miro.inspection import (
    checked_payload,
    inspect_boards,
    inspect_identity,
    inspect_read_only,
    result_resource_links,
)


def result(payload: dict, *, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        structuredContent=payload,
        content=[],
        isError=is_error,
    )


def test_result_resource_links_reads_typed_and_mapping_items() -> None:
    typed = SimpleNamespace(type="resource_link", uri="miro-preview://create/abcdefghijklmnop")
    response = SimpleNamespace(
        structuredContent={"success": True},
        content=[
            typed,
            {"type": "resource_link", "uri": "https://example.invalid/resource"},
            SimpleNamespace(type="text", text="ignored"),
        ],
        isError=False,
    )

    assert result_resource_links(response) == (
        "miro-preview://create/abcdefghijklmnop",
        "https://example.invalid/resource",
    )


def test_identity_inspection_never_returns_identity_values() -> None:
    values = {
        "org_id": "secret-org",
        "team_id": "secret-team",
        "user_id": "secret-user",
        "workspace_id": "secret-workspace",
    }

    async def call_tool(name: str, arguments: dict) -> SimpleNamespace:
        assert name == "user_who_am_i"
        assert arguments == {"is_repository": True}
        return result(values)

    inspection = asyncio.run(inspect_identity(call_tool))
    encoded = json.dumps(inspection.to_dict(), sort_keys=True)

    assert inspection.complete is True
    assert inspection.present_field_count == 4
    assert inspection.missing_fields == ()
    assert all(value not in encoded for value in values.values())


def test_board_pagination_uses_offsets_and_diagnoses_opaque_cursor() -> None:
    offsets = []
    private_values = (
        "Board Alpha",
        "Board Beta",
        "Board Gamma",
        "https://miro.invalid",
    )

    async def call_tool(name: str, arguments: dict) -> SimpleNamespace:
        assert name == "board_search_boards"
        offsets.append(arguments["offset"])
        if arguments["offset"] == 0:
            return result(
                {
                    "data": [
                        {"name": private_values[0], "miro_url": private_values[3]},
                        {"name": private_values[1], "miro_url": private_values[3]},
                    ],
                    "total": 3,
                    "has_more": True,
                    "nextCursor": "opaque-cursor",
                }
            )
        return result(
            {
                "data": [
                    {"name": private_values[2], "miro_url": private_values[3]},
                ],
                "total": 3,
                "has_more": False,
                "nextCursor": None,
            }
        )

    inspection = asyncio.run(inspect_boards(call_tool, limit=2, max_pages=5))
    encoded = json.dumps(inspection.to_dict(), sort_keys=True)

    assert offsets == [0, 2]
    assert inspection.pagination_complete is True
    assert inspection.records_seen == 3
    assert inspection.unique_records == 3
    assert inspection.consistent is False
    assert "opaque_cursor_for_offset_input" in inspection.anomalies
    assert all(value not in encoded for value in private_values)


def test_board_total_contradiction_is_explicit() -> None:
    async def call_tool(_name: str, _arguments: dict) -> SimpleNamespace:
        return result(
            {
                "data": [{"name": "one", "miro_url": "private"}],
                "total": 2,
                "has_more": False,
                "nextCursor": None,
            }
        )

    inspection = asyncio.run(inspect_boards(call_tool))

    assert inspection.pagination_complete is True
    assert inspection.consistent is False
    assert "reported_total_record_count_mismatch" in inspection.anomalies
    assert "reported_total_unique_count_mismatch" in inspection.anomalies


def test_provider_declared_error_is_typed_without_details() -> None:
    provider_secret = "private-board-identifier"
    response = result(
        {
            "error_code": "BOARD_NOT_FOUND",
            "details": {"board_id": provider_secret},
        }
    )

    with pytest.raises(MiroToolError) as captured:
        checked_payload(response, "board_search_boards")

    assert provider_secret not in str(captured.value)


def test_full_inspection_calls_only_read_only_tools() -> None:
    calls = []

    async def call_tool(name: str, arguments: dict) -> SimpleNamespace:
        calls.append((name, arguments))
        if name == "user_who_am_i":
            return result(
                {
                    "org_id": "org",
                    "team_id": "team",
                    "user_id": "user",
                    "workspace_id": "workspace",
                }
            )
        return result(
            {
                "data": [],
                "total": 0,
                "has_more": False,
                "nextCursor": None,
            }
        )

    inspection = asyncio.run(inspect_read_only(call_tool))

    assert [name for name, _arguments in calls] == [
        "user_who_am_i",
        "board_search_boards",
    ]
    assert inspection.ok is True
    assert inspection.mutation_attempted is False
    assert inspection.sanitized is True
