from __future__ import annotations

from datetime import UTC, datetime

import pytest

from schauwerk.surfaces.miro.change_control import (
    build_plan,
    failure_receipt,
    make_marker,
    marked_lines,
    marker_present,
    prepare_receipt_destination,
    validate_marker,
)
from schauwerk.surfaces.miro.errors import MiroCredentialError


def test_marker_shape_is_strict() -> None:
    marker = make_marker(datetime(2026, 6, 29, 5, 0, 0, tzinfo=UTC), suffix="abc123")
    assert marker == "schauwerk-sw003-20260629T050000Z-abc123"
    assert validate_marker(marker) == marker
    with pytest.raises(MiroCredentialError):
        validate_marker("schauwerk-sw003-bad")


def test_plan_marks_every_line() -> None:
    marker = "schauwerk-sw003-20260629T050000Z-abc123"
    plan = build_plan(board_alias="fixture", marker=marker)
    lines = plan["create_dsl"].splitlines()
    assert len(lines) == 3
    assert all(marker in line for line in lines)
    assert plan["create_token"] in plan["create_dsl"]


def test_marker_detection_and_cleanup_scope() -> None:
    marker = "schauwerk-sw003-20260629T050000Z-abc123"
    assert marker_present({"items": [{"data": {"content": marker}}]}, marker)
    layout = "keep\nremove " + marker + "\nkeep again"
    assert marked_lines(layout, marker) == "remove " + marker


def test_failure_receipt_is_sanitized() -> None:
    receipt = failure_receipt(
        alias="fixture",
        marker="schauwerk-sw003-20260629T050000Z-abc123",
        stage="connect",
        exc=RuntimeError("secret detail"),
    )
    assert receipt["ok"] is False
    assert receipt["mutation_attempted"] is False
    assert receipt["failed_stage"] == "connect"


def test_receipt_destination_rejects_symlink(tmp_path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "receipt.json"
    link.symlink_to(target)

    with pytest.raises(MiroCredentialError, match="unsafe"):
        prepare_receipt_destination(link)
