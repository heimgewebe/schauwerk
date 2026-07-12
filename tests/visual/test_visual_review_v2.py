from __future__ import annotations

import copy

import pytest

from schauwerk.visual.system_v2 import compile_visual_review, reference_board_spec


def _live_receipt() -> dict:
    spec = reference_board_spec()
    return {
        "schema_version": "schauwerk-visual-system-live-test.v2",
        "alias": "visual-v2-fixture",
        "board": {"reference_digest": "a" * 16},
        "local_quality": {
            "ok": True,
            "score": 100,
            "board_digest": spec["board_digest"],
            "quality_digest": "b" * 64,
        },
        "remote_conformance": {
            "ok": True,
            "observed": {
                "connector_count": 7,
                "doc_count": 1,
                "frame_count": 7,
                "remote_item_count": 38,
                "table_count": 3,
            },
            "mismatches": {},
        },
    }


def _review_input() -> dict:
    finding = "The reviewed deterministic preview and exact remote conformance support this axis."
    axes = {
        axis: {"verdict": "PASS", "finding": finding}
        for axis in (
            "information_architecture",
            "hierarchy",
            "object_selection",
            "density_and_whitespace",
            "palette_and_consistency",
            "readability",
            "aesthetic_character",
        )
    }
    return {
        "schema_version": "schauwerk-visual-review-input.v2",
        "reviewed_at": "2026-07-12T22:00:00Z",
        "reviewer": "fixture reviewer",
        "board_digest": reference_board_spec()["board_digest"],
        "method": {
            "design_surface": "deterministic board-spec visual preview",
            "provider_binding": "exact remote item-type and connector-count conformance",
            "authenticated_provider_screenshot": "not_available",
            "excluded_capture": "Unauthenticated access page was excluded.",
        },
        "axes": axes,
        "verdict": "PASS",
        "non_claims": ["universal aesthetic preference", "pixel-identical provider rendering"],
    }


def test_visual_review_binds_human_axes_to_live_receipt() -> None:
    value = compile_visual_review(_live_receipt(), _review_input())
    assert value["schema_version"] == "schauwerk-visual-review.v2"
    assert value["verdict"] == "PASS"
    assert value["failed_axes"] == []
    assert value["automatic_quality"]["automatic_aesthetic_claim"] is False
    assert value["remote_conformance"]["observed"]["remote_item_count"] == 38
    assert value["mutation_attempted"] is False
    assert len(value["review_digest"]) == 64


def test_passing_review_rejects_failed_axis() -> None:
    review = _review_input()
    review["axes"]["readability"]["verdict"] = "FAIL"
    with pytest.raises(ValueError, match="cannot contain failed axes"):
        compile_visual_review(_live_receipt(), review)


def test_review_rejects_stale_board_and_remote_mismatch() -> None:
    review = _review_input()
    review["board_digest"] = "0" * 64
    with pytest.raises(ValueError, match="does not match"):
        compile_visual_review(_live_receipt(), review)

    live = copy.deepcopy(_live_receipt())
    live["remote_conformance"]["mismatches"] = {"frame_count": {"expected": 7, "observed": 6}}
    with pytest.raises(ValueError, match="not exact"):
        compile_visual_review(live, _review_input())


def test_review_timestamp_and_method_are_fail_closed() -> None:
    review = _review_input()
    review["reviewed_at"] = "2026-07-12T22:00:00+00:00"
    with pytest.raises(ValueError, match="canonical UTC"):
        compile_visual_review(_live_receipt(), review)

    review = _review_input()
    review["method"]["design_surface"] = "automatic score"
    with pytest.raises(ValueError, match="deterministic design surface"):
        compile_visual_review(_live_receipt(), review)


def test_visual_review_rejects_invalid_local_quality_binding() -> None:
    live = _live_receipt()
    live["local_quality"]["quality_digest"] = "not-a-digest"
    with pytest.raises(ValueError, match="quality digest"):
        compile_visual_review(live, _review_input())

    live = _live_receipt()
    live["local_quality"]["score"] = 89
    with pytest.raises(ValueError, match="quality score"):
        compile_visual_review(live, _review_input())
