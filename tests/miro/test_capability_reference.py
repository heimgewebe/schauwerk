from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path

import pytest

from schauwerk.surfaces.miro.capability_audit import TOOL_FAMILIES, audit_tool_catalogue


def _catalogue(*names: str) -> dict:
    return {
        "protocol_version": "2025-11-25",
        "server_name": "Miro MCP",
        "server_version": "3.2.4",
        "tools": [{"name": name, "input_schema": {"type": "object"}} for name in names],
    }


def _reference() -> dict:
    resource = resources.files("schauwerk.schemas").joinpath("miro-mcp-tools-reference.v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def test_live_baseline_reports_documentation_drift_without_claiming_availability() -> None:
    live_names = sorted(set().union(*TOOL_FAMILIES.values()))
    report = audit_tool_catalogue(_catalogue(*live_names))

    reference = report["official_reference"]
    assert reference["tool_count"] == 31
    assert reference["reference_missing_live"] == [
        "comment_reply",
        "comment_resolve",
        "prototype_read",
    ]
    assert reference["live_not_in_reference"] == [
        "comment_create",
        "prototype_get_upload_url",
        "table_get_latest_update_history",
        "table_update_view",
        "user_who_am_i",
    ]
    assert reference["reference_not_integrated"] == [
        "comment_reply",
        "comment_resolve",
        "prototype_read",
    ]
    assert reference["diagnostic_only"] is True
    assert report["truth_boundary"]["operational_authority"] == "live MCP catalogue"
    assert "comment_reply" not in report["observed_tools"]


def test_reference_validation_rejects_duplicate_and_malformed_records() -> None:
    duplicate = _reference()
    duplicate["tools"].append(duplicate["tools"][0])
    with pytest.raises(ValueError, match="duplicate|unique"):
        audit_tool_catalogue(_catalogue("board_create"), reference=duplicate)

    malformed = _reference()
    malformed["source_url"] = "https://example.invalid/reference"
    with pytest.raises(ValueError, match="source_url"):
        audit_tool_catalogue(_catalogue("board_create"), reference=malformed)


def test_reference_order_is_normalized_and_digest_stays_deterministic() -> None:
    first = _reference()
    second = copy.deepcopy(first)
    second["tools"].reverse()

    assert audit_tool_catalogue(
        _catalogue("board_create"), reference=first
    ) == audit_tool_catalogue(_catalogue("board_create"), reference=second)


def test_public_and_packaged_reference_schema_are_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    public = root / "schemas/miro-mcp-tool-reference.v1.schema.json"
    packaged = root / "src/schauwerk/schemas/miro-mcp-tool-reference.v1.schema.json"
    assert public.read_bytes() == packaged.read_bytes()
