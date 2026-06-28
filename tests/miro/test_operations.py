from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
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
    with pytest.raises(MiroToolError, match="board_search_boards"):
        ensure_success(
            result({"secret": "not-exposed"}, error=True),
            "board_search_boards",
        )


def test_identity_reports_only_field_presence() -> None:
    values = {
        "user_id": "user-value",
        "team_id": "team-value",
        "workspace_id": "workspace-value",
        "org_id": "org-value",
    }

    async def call_tool(_name, _arguments):
        return result(values)

    inspected = asyncio.run(inspect_identity(call_tool))

    assert inspected["complete"] is True
    assert inspected["present_field_count"] == 4
    assert inspected["missing_fields"] == ()
    assert all(value not in repr(inspected) for value in values.values())


def test_board_inspection_paginates_without_returning_names() -> None:
    pages = {
        0: {
            "data": [{"name": "private-one", "miro_url": "hidden"}],
            "total": 2,
            "has_more": True,
            "nextCursor": "1",
        },
        1: {
            "data": [{"name": "private-two", "id": "hidden"}],
            "total": 2,
            "has_more": False,
            "nextCursor": None,
        },
    }

    async def call_tool(_name, arguments):
        return result(pages[arguments["offset"]])

    inspected = asyncio.run(inspect_boards(call_tool, query="private", limit=1))

    assert inspected["pagination_complete"] is True
    assert inspected["consistent"] is True
    assert inspected["records_seen"] == 2
    assert inspected["unique_records"] == 2
    assert "private-one" not in repr(inspected)
    assert "private-two" not in repr(inspected)
    assert "hidden" not in repr(inspected)


def test_board_inspection_reports_empty_page_anomaly() -> None:
    async def call_tool(_name, _arguments):
        return result(
            {"data": [], "total": 2, "has_more": True, "nextCursor": "1"}
        )

    inspected = asyncio.run(inspect_boards(call_tool))

    assert inspected["pagination_complete"] is False
    assert inspected["pages_read"] == 1
    assert "empty_page_with_more_results" in inspected["anomalies"]


def test_board_inspection_reports_cursor_mismatch() -> None:
    async def call_tool(_name, _arguments):
        return result(
            {
                "data": [{"name": "private"}],
                "total": 2,
                "has_more": True,
                "nextCursor": "0",
            }
        )

    inspected = asyncio.run(inspect_boards(call_tool, limit=1, max_pages=1))

    assert "cursor_offset_mismatch" in inspected["anomalies"]
    assert "page_limit_reached" in inspected["anomalies"]
