from __future__ import annotations

import json

import pytest

from schauwerk.surfaces.miro.errors import MiroConnectionError, MiroCredentialError
from schauwerk.surfaces.miro.snapshot_model import SnapshotRead, normalize_item
from schauwerk.surfaces.miro.snapshot_runtime import write_snapshot_pair


def sample(content: str, *, item_pages: int = 1) -> SnapshotRead:
    return SnapshotRead(
        items=(normalize_item({"id": "item", "type": "text", "data": {"content": content}}),),
        comments=(),
        item_pages=item_pages,
        comment_pages=0,
    )


def test_verified_artifact_is_owner_only(tmp_path) -> None:
    destination = tmp_path / "snapshot.json"
    receipt = write_snapshot_pair(
        sample("stable"), sample("stable"), alias="fixture", destination=destination
    )
    artifact = json.loads(destination.read_text(encoding="utf-8"))
    assert receipt.repeatability_verified is True
    assert artifact["content_digest"] == receipt.content_digest
    assert artifact["verified_reads"] == 2
    assert destination.stat().st_mode & 0o077 == 0


def test_changed_pair_is_rejected(tmp_path) -> None:
    with pytest.raises(MiroConnectionError, match="repeatability"):
        write_snapshot_pair(
            sample("before"),
            sample("after"),
            alias="fixture",
            destination=tmp_path / "snapshot.json",
        )


def test_changed_pagination_is_rejected(tmp_path) -> None:
    with pytest.raises(MiroConnectionError, match="pagination"):
        write_snapshot_pair(
            sample("stable", item_pages=1),
            sample("stable", item_pages=2),
            alias="fixture",
            destination=tmp_path / "snapshot.json",
        )


def test_snapshot_destination_rejects_symlink(tmp_path) -> None:
    target = tmp_path / "target.json"
    target.write_text("unchanged", encoding="utf-8")
    destination = tmp_path / "snapshot.json"
    destination.symlink_to(target)

    with pytest.raises(MiroCredentialError, match="unsafe"):
        write_snapshot_pair(
            sample("stable"),
            sample("stable"),
            alias="fixture",
            destination=destination,
        )

    assert target.read_text(encoding="utf-8") == "unchanged"
