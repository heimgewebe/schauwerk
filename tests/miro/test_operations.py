from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroConnectionError
from schauwerk.surfaces.miro.operations import (
    ensure_success,
    inspect_boards,
    inspect_identity,
    result_payload,
)


def result(payload, *, error=False):
    return SimpleNamespace(structuredContent=payload, content=[], isError=error)


def test_result_payload_falls_back_to_text_content() -> None:
    item = SimpleNamespace(text=json.dumps({"total": 1}))
    value = SimpleNamespace(structuredContent=None, content=[item], isError=False)

    assert result_payload(value) == {"total": 1}


def test_tool_error_is_rejected_without_provider_payload() -> None:
    with pytest.raises(MiroConnectionError, match="board_search_boards"):
        ensure_success(
            result({"secret": "not-exposed"}, error=True),
            "board_search_boards",
        )


def test_identity_reports_only_field_presence() -> None:
    async def call_tool(_name, _arguments):
        return result(
            {
                "user_id": "user-value",
                "team_id": "team-value",
                "workspace_id": "workspace-value",
                "org_id": "org-value",
            }
        )

    inspected = asyncio.run(inspect_identity(call_tool))

    assert inspected["complete"] is True
    assert sorted(inspected["present_fields"]) == [
        "org_id",
        "team_id",
        "user_id",
        "workspace_id",
    ]
    assert "user-value" not in repr(inspected)


def test_board_inspection_paginates_and_returns_names_only() -> None:
    pages = {
        0: {
            "data": [{"name": "grabowski", "miro_url": "hidden"}],
            "total": 2,
            "has_more": True,
            "nextCursor": "20",
        },
        20: {
            "data": [{"name": "grabowski 2", "id": "hidden"}],
            "total": 2,
            "has_more": False,
            "nextCursor": None,
        },
    }

    async def call_tool(_name, arguments):
        return result(pages[arguments["offset"]])

    inspected = asyncio.run(inspect_boards(call_tool, query="grabowski"))

    assert inspected["complete"] is True
    assert inspected["board_names"] == ["grabowski", "grabowski 2"]
    assert inspected["reported_total"] == 2
    assert "hidden" not in repr(inspected)


def test_board_inspection_reports_empty_page_anomaly() -> None:
    pages = {
        0: {"data": [], "total": 2, "has_more": True, "nextCursor": "20"},
        20: {"data": [], "total": 2, "has_more": False, "nextCursor": None},
    }

    async def call_tool(_name, arguments):
        return result(pages[arguments["offset"]])

    inspected = asyncio.run(inspect_boards(call_tool, query="grabowski"))

    assert inspected["complete"] is False
    assert inspected["pages_read"] == 2
    assert inspected["returned_count"] == 0
    assert "reported_results_without_records" in inspected["anomalies"]


def test_board_inspection_rejects_non_advancing_cursor() -> None:
    async def call_tool(_name, _arguments):
        return result(
            {"data": [], "total": 1, "has_more": True, "nextCursor": "0"}
        )

    inspected = asyncio.run(inspect_boards(call_tool))

    assert "non_advancing_next_cursor" in inspected["anomalies"]
