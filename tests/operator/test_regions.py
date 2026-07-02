from __future__ import annotations

import json

import pytest

from schauwerk.operator.regions import (
    compile_region_operation_plan,
    load_region_declaration,
    parse_region_declaration,
)


def managed_region() -> dict:
    return {
        "region": {
            "view_id": "learning:photosynthese",
            "region_id": "cluster-goals",
            "mode": "managed",
            "surface_alias": "nicole-mt-zoom-chunked-20260701-211733",
            "expected_snapshot_digest": "a" * 64,
            "expected_source_digest": "b" * 64,
            "owner": "schauwerk",
            "visibility": "classroom",
        }
    }


def test_managed_region_is_ready_for_preflight_without_mutation() -> None:
    declaration = parse_region_declaration(managed_region())
    plan = compile_region_operation_plan(declaration=declaration)

    assert plan["schema_version"] == "typed-region-plan.v1"
    assert plan["ok"] is True
    assert plan["mutation_attempted"] is False
    assert plan["ready_for_preflight"] is True
    assert plan["blocked_reasons"] == []
    assert "capture_before_snapshot" in plan["required_preflight"]
    assert "verify_idempotency_receipt" in plan["postflight_required"]
    assert plan["restore_required"] is True


def test_manual_region_blocks_mutation_plan() -> None:
    data = managed_region()
    data["region"]["mode"] = "manual"
    declaration = parse_region_declaration(data)
    plan = compile_region_operation_plan(declaration=declaration)

    assert plan["ok"] is False
    assert plan["ready_for_preflight"] is False
    assert plan["blocked_reasons"] == ["manual_region_is_human_owned"]
    assert plan["mutation_attempted"] is False


def test_region_declaration_rejects_unsafe_alias() -> None:
    data = managed_region()
    data["region"]["surface_alias"] = "bad/alias"

    with pytest.raises(ValueError, match="surface_alias"):
        parse_region_declaration(data)


def test_region_plan_writes_receipt(tmp_path) -> None:
    path = tmp_path / "region.yml"
    output = tmp_path / "plan.json"
    path.write_text(
        """
region:
  view_id: learning:photosynthese
  region_id: cluster-goals
  mode: managed
  surface_alias: nicole-mt-zoom-chunked-20260701-211733
  expected_snapshot_digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  expected_source_digest: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  visibility: classroom
""".strip(),
        encoding="utf-8",
    )

    declaration = load_region_declaration(path)
    plan = compile_region_operation_plan(declaration=declaration, output_path=output)

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["ok"] is True
    assert plan["output_path"] == str(output.absolute())
