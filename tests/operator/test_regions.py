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


def snapshot_receipt(alias: str, digest: str) -> dict:
    return {
        "board_alias": alias,
        "content_digest": digest,
        "item_count": 4,
        "repeatability_verified": True,
        "sanitized_references": True,
    }


def test_region_preflight_passes_for_allowlisted_matching_snapshot(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_preflight

    data = managed_region()
    declaration = parse_region_declaration(data)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(snapshot_receipt(declaration.surface_alias, "a" * 64)), encoding="utf-8"
    )

    result = compile_region_preflight(
        declaration=declaration,
        allowlisted_aliases={declaration.surface_alias},
        snapshot_path=snapshot,
    )

    assert result["schema_version"] == "typed-region-preflight.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["ready_for_apply"] is True
    assert result["blocked_reasons"] == []
    assert result["checks"] == {
        "surface_alias_allowlisted": True,
        "snapshot_digest_matches": True,
        "snapshot_board_alias_matches": True,
        "snapshot_repeatability_verified": True,
        "snapshot_references_sanitized": True,
    }


def test_region_preflight_blocks_missing_allowlist_and_digest_mismatch(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_preflight

    declaration = parse_region_declaration(managed_region())
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(snapshot_receipt(declaration.surface_alias, "c" * 64)), encoding="utf-8"
    )

    result = compile_region_preflight(
        declaration=declaration,
        allowlisted_aliases=set(),
        snapshot_path=snapshot,
    )

    assert result["ok"] is False
    assert result["checks"]["surface_alias_allowlisted"] is False
    assert result["checks"]["snapshot_digest_matches"] is False
    assert "surface_alias_not_allowlisted" in result["blocked_reasons"]
    assert "snapshot_digest_mismatch" in result["blocked_reasons"]


def test_region_preflight_blocks_unverified_snapshot(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_preflight

    declaration = parse_region_declaration(managed_region())
    receipt = snapshot_receipt(declaration.surface_alias, "a" * 64)
    receipt["repeatability_verified"] = False
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(receipt), encoding="utf-8")

    result = compile_region_preflight(
        declaration=declaration,
        allowlisted_aliases={declaration.surface_alias},
        snapshot_path=snapshot,
    )

    assert result["ok"] is False
    assert "snapshot_repeatability_unverified" in result["blocked_reasons"]


def test_region_preflight_rejects_snapshot_symlink(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_preflight

    declaration = parse_region_declaration(managed_region())
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(snapshot_receipt(declaration.surface_alias, "a" * 64)), encoding="utf-8"
    )
    link = tmp_path / "snapshot-link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="unsafe"):
        compile_region_preflight(
            declaration=declaration,
            allowlisted_aliases={declaration.surface_alias},
            snapshot_path=link,
        )
