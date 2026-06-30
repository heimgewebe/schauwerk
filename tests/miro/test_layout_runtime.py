from __future__ import annotations

import pytest

from schauwerk.surfaces.miro.errors import MiroToolError
from schauwerk.surfaces.miro.layout_runtime import _receipt


def test_layout_receipt_sanitizes_provider_references() -> None:
    receipt = _receipt(
        "lesson-demo",
        {
            "success": True,
            "created_count": 4,
            "failed_items": [],
            "message": "ok",
            "miro_url": "https://miro.com/app/board/private=/",
            "result_dsl": "https://miro.com/app/board/private=/?moveToWidget=1 TEXT x=0 y=0 w=10 x",
        },
    ).to_dict()

    assert receipt["board_alias"] == "lesson-demo"
    assert receipt["created_count"] == 4
    assert receipt["failed_count"] == 0
    assert receipt["success"] is True
    assert receipt["sanitized_references"] is True
    assert "miro" not in str(receipt).lower()
    assert receipt["result_dsl_digest"] is not None


def test_layout_receipt_rejects_provider_failure() -> None:
    with pytest.raises(MiroToolError, match="layout"):
        _receipt(
            "lesson-demo",
            {
                "success": False,
                "created_count": 0,
                "failed_items": [{"id": "x", "type": "TEXT", "reason": "bad"}],
                "message": "bad syntax",
            },
        )
