from __future__ import annotations

from types import SimpleNamespace

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
from schauwerk.surfaces.miro.managed_region_runtime import (
    parse_layout_read_result,
    parse_layout_update_result,
)


def result(payload: dict, *, error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=error, structuredContent=payload, content=[])


def test_layout_read_returns_raw_dsl_only_inside_runtime_boundary() -> None:
    dsl = "https://miro.com/app/board/private/?moveToWidget=1 TEXT content=secret"
    assert (
        parse_layout_read_result(
            result(
                {
                    "success": True,
                    "dsl": dsl,
                    "item_count": 1,
                    "skipped_count": 0,
                }
            )
        )
        == dsl
    )


def test_layout_update_receipt_is_sanitized() -> None:
    receipt = parse_layout_update_result(
        result(
            {
                "success": True,
                "created_count": 0,
                "updated_count": 1,
                "deleted_count": 0,
                "result_dsl": "https://miro.com/app/board/private/?moveToWidget=1 TEXT",
                "miro_url": "https://miro.com/app/board/private/",
            }
        )
    ).to_dict()
    assert receipt["success"] is True
    assert receipt["updated_count"] == 1
    assert "miro" not in str(receipt).lower()
    assert receipt["result_dsl_digest"] is not None


def test_layout_update_rejects_provider_failure_and_invalid_counts() -> None:
    with pytest.raises(MiroToolError, match="failed"):
        parse_layout_update_result(result({"success": False, "message": "private url"}))
    with pytest.raises(MiroToolError, match="updated_count"):
        parse_layout_update_result(
            result(
                {
                    "success": True,
                    "created_count": 0,
                    "updated_count": -1,
                    "deleted_count": 0,
                }
            )
        )


def test_layout_read_rejects_skipped_or_invalid_item_counts() -> None:
    with pytest.raises(MiroToolError, match="skipped unsupported"):
        parse_layout_read_result(
            result(
                {
                    "success": True,
                    "dsl": "item TEXT",
                    "item_count": 2,
                    "skipped_count": 1,
                }
            )
        )
    with pytest.raises(MiroToolError, match="item_count"):
        parse_layout_read_result(
            result(
                {
                    "success": True,
                    "dsl": "item TEXT",
                    "item_count": -1,
                    "skipped_count": 0,
                }
            )
        )


def test_layout_results_reject_oversized_dsl(monkeypatch) -> None:
    import schauwerk.surfaces.miro.managed_region_runtime as runtime

    monkeypatch.setattr(runtime, "_MAX_DSL_BYTES", 8)
    with pytest.raises(MiroToolError, match="layout_read DSL exceeds"):
        parse_layout_read_result(
            result(
                {
                    "success": True,
                    "dsl": "123456789",
                    "item_count": 1,
                    "skipped_count": 0,
                }
            )
        )
    with pytest.raises(MiroToolError, match="layout_update DSL exceeds"):
        parse_layout_update_result(
            result(
                {
                    "success": True,
                    "created_count": 0,
                    "updated_count": 1,
                    "deleted_count": 0,
                    "result_dsl": "123456789",
                }
            )
        )
