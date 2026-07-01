from __future__ import annotations

from pathlib import Path

from schauwerk.surfaces.miro.live_test_index import (
    LiveTestRecord,
    prune_live_tests,
    read_live_test_records,
    write_live_test_records,
)
from schauwerk.surfaces.miro.models import MiroSettings


def test_prune_dry_run_never_mutates_local_index_or_dirs(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    out = settings.snapshots_root / "live-tests" / "old-a"
    out.mkdir(parents=True)
    record = LiveTestRecord(
        alias="old-a",
        reference_digest="digest",
        topic="topic",
        board_name="board",
        output_dir=str(out),
        created_at="2026-01-01T00:00:00Z",
    )
    write_live_test_records(settings, [record])

    receipt = prune_live_tests(settings, keep=0, dry_run=True)

    assert receipt.remote_cleanup_supported is False
    assert receipt.remote_cleanup_attempted is False
    assert receipt.records_pruned == 1
    assert receipt.output_dirs_retired == ()
    assert receipt.index_updated is False
    assert Path(record.output_dir).exists()
    assert read_live_test_records(settings) == (record,)
