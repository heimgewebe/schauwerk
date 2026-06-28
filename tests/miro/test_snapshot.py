from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroConnectionError
from schauwerk.surfaces.miro.snapshot import read_board_snapshot, read_items


def result(payload):
    return SimpleNamespace(structuredContent=payload, content=[], isError=False)


def test_snapshot_reads_item_cursor_and_comment_offsets() -> None:
    calls = []

    async def call_tool(name, arguments):
        calls.append((name, arguments.copy()))
        if name == "board_list_items":
            if arguments.get("cursor") is None:
                return result(
                    {
                        "data": [{"id": "b", "type": "text", "data": {"content": "B"}}],
                        "has_more": True,
                        "nextCursor": "next",
                    }
                )
            return result(
                {
                    "data": [{"id": "a", "type": "text", "data": {"content": "A"}}],
                    "has_more": False,
                    "nextCursor": None,
                }
            )
        if arguments["offset"] == 0:
            return result(
                {
                    "data": [{"id": "c1", "content": "one"}],
                    "has_more": True,
                }
            )
        return result(
            {
                "data": [{"id": "c2", "content": "two"}],
                "has_more": False,
            }
        )

    snapshot = asyncio.run(
        read_board_snapshot(
            call_tool,
            miro_url="https://miro.com/app/board/private",
            item_limit=10,
            comment_limit=1,
        )
    )

    assert snapshot.item_pages == 2
    assert snapshot.comment_pages == 2
    assert len(snapshot.items) == 2
    assert len(snapshot.comments) == 2
    assert [name for name, _ in calls] == [
        "board_list_items",
        "board_list_items",
        "comment_list_comments",
        "comment_list_comments",
    ]
    assert calls[-1][1]["offset"] == 1


def test_item_reader_rejects_repeated_cursor() -> None:
    async def call_tool(_name, _arguments):
        return result(
            {
                "data": [{"id": "a", "type": "text"}],
                "has_more": True,
                "nextCursor": "same",
            }
        )

    with pytest.raises(MiroConnectionError, match="repeated item"):
        asyncio.run(
            read_items(
                call_tool,
                miro_url="https://miro.com/app/board/private",
                limit=10,
                max_pages=3,
            )
        )


def test_snapshot_can_skip_comments() -> None:
    calls = []

    async def call_tool(name, _arguments):
        calls.append(name)
        return result({"data": [], "has_more": False, "nextCursor": None})

    snapshot = asyncio.run(
        read_board_snapshot(
            call_tool,
            miro_url="https://miro.com/app/board/private",
            include_comments=False,
        )
    )

    assert calls == ["board_list_items"]
    assert snapshot.comments == ()
    assert snapshot.comment_pages == 0


def test_item_reader_rejects_duplicate_reference_across_pages() -> None:
    calls = 0

    async def call_tool(_name, _arguments):
        nonlocal calls
        calls += 1
        return result(
            {
                "data": [{"id": "same", "type": "text", "data": {"content": f"version-{calls}"}}],
                "has_more": calls == 1,
                "nextCursor": "next" if calls == 1 else None,
            }
        )

    with pytest.raises(MiroConnectionError, match="duplicate item reference"):
        asyncio.run(
            read_items(
                call_tool, miro_url="https://miro.com/app/board/private", limit=10, max_pages=3
            )
        )
