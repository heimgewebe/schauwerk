from __future__ import annotations

import json

from schauwerk.surfaces.miro.snapshot_model import (
    SnapshotRead,
    content_digest,
    normalize_comment,
    normalize_item,
)


def test_item_normalization_is_deterministic_and_redacts_provider_references() -> None:
    first = {
        "id": "private-id",
        "type": "sticky_note",
        "miro_url": "https://miro.com/app/board/private",
        "data": {"content": "stable", "updated_at": "yesterday"},
        "position": {"y": 2.0, "x": 1.0},
        "createdBy": {"user_id": "private-user"},
    }
    second = {
        "position": {"x": 1, "y": 2},
        "data": {"updated_at": "today", "content": "stable"},
        "type": "sticky_note",
        "id": "private-id",
    }

    left = normalize_item(first)
    right = normalize_item(second)
    encoded = json.dumps(left, sort_keys=True)

    assert left == right
    assert "private-id" not in encoded
    assert "private-user" not in encoded
    assert "miro.com" not in encoded
    assert "updated_at" not in encoded


def test_comment_normalization_removes_identity_and_timestamps() -> None:
    normalized = normalize_comment(
        {
            "id": "comment-id",
            "content": "stable",
            "created_at": "now",
            "created_by": {"user_id": "user"},
            "miro_url": "https://miro.com/private",
        }
    )
    encoded = json.dumps(normalized, sort_keys=True)

    assert "comment-id" not in encoded
    assert "user" not in encoded
    assert "now" not in encoded
    assert "miro.com" not in encoded
    assert normalized["content"] == "stable"


def test_snapshot_digest_ignores_input_order_after_normalization() -> None:
    one = SnapshotRead(
        items=(normalize_item({"id": "a", "type": "text", "data": {"content": "A"}}),),
        comments=(),
        item_pages=1,
        comment_pages=0,
    )
    two = SnapshotRead(
        items=(normalize_item({"data": {"content": "A"}, "type": "text", "id": "a"}),),
        comments=(),
        item_pages=1,
        comment_pages=0,
    )

    assert content_digest(one.content("fixture")) == content_digest(two.content("fixture"))


def test_comment_normalization_handles_camel_case_private_keys() -> None:
    normalized = normalize_comment(
        {
            "content": "stable",
            "createdBy": {"userId": "private-user"},
            "itemId": "private-item",
            "previewUrl": "https://example.invalid/private",
        }
    )
    encoded = json.dumps(normalized, sort_keys=True)

    assert "private-user" not in encoded
    assert "private-item" not in encoded
    assert "example.invalid" not in encoded
    assert normalized["content"] == "stable"
    assert "reference_digest" in encoded
