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


def ready_preflight() -> dict:
    declaration = parse_region_declaration(managed_region())
    return {
        "schema_version": "typed-region-preflight.v1",
        "ok": True,
        "ready_for_apply": True,
        "mutation_attempted": False,
        "operation": "render-update",
        "region": declaration.to_dict(),
        "snapshot": snapshot_receipt(declaration.surface_alias, "a" * 64),
        "blocked_reasons": [],
        "boundary": {"no_miro_mutation": True},
    }


def test_apply_scaffold_allows_ready_preflight_without_mutation() -> None:
    from schauwerk.operator.regions import compile_region_apply_scaffold

    result = compile_region_apply_scaffold(preflight=ready_preflight())

    assert result["schema_version"] == "typed-region-apply-scaffold.v1"
    assert result["ok"] is True
    assert result["ready_for_live_apply"] is True
    assert result["mutation_attempted"] is False
    assert result["blocked_reasons"] == []
    assert "miro_doctor_safe_for_live_board_operations" in result["required_live_preconditions"]
    assert result["boundary"] == {
        "scaffold_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_apply_scaffold_blocks_failed_preflight() -> None:
    from schauwerk.operator.regions import compile_region_apply_scaffold

    preflight = ready_preflight()
    preflight["ok"] = False
    preflight["ready_for_apply"] = False
    preflight["blocked_reasons"] = ["snapshot_digest_mismatch"]

    result = compile_region_apply_scaffold(preflight=preflight)

    assert result["ok"] is False
    assert result["ready_for_live_apply"] is False
    assert "preflight_not_ready" in result["blocked_reasons"]
    assert "preflight:snapshot_digest_mismatch" in result["blocked_reasons"]


def test_apply_scaffold_loads_preflight_and_writes_receipt(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_apply_scaffold, load_region_preflight

    source = tmp_path / "preflight.json"
    output = tmp_path / "apply.json"
    source.write_text(json.dumps(ready_preflight()), encoding="utf-8")

    preflight = load_region_preflight(source)
    result = compile_region_apply_scaffold(preflight=preflight, output_path=output)

    assert result["ok"] is True
    assert output.exists()
    assert (
        json.loads(output.read_text(encoding="utf-8"))["schema_version"]
        == "typed-region-apply-scaffold.v1"
    )


def test_load_region_preflight_rejects_wrong_schema(tmp_path) -> None:
    from schauwerk.operator.regions import load_region_preflight

    source = tmp_path / "preflight.json"
    source.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema"):
        load_region_preflight(source)


def fixture_operations(region_id: str = "cluster-goals") -> list[dict[str, str]]:
    return [
        {
            "operation_id": "create-title",
            "action": "create-item",
            "region_id": region_id,
            "local_ref": "title-card",
            "payload_digest": "c" * 64,
        },
        {
            "operation_id": "update-body",
            "action": "update-item",
            "region_id": region_id,
            "local_ref": "body-card",
            "payload_digest": "d" * 64,
        },
    ]


def ready_apply_scaffold() -> dict:
    from schauwerk.operator.regions import compile_region_apply_scaffold

    return compile_region_apply_scaffold(preflight=ready_preflight())


def test_apply_receipt_is_fixture_only_and_deterministic() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    first = compile_region_apply_receipt(
        scaffold=ready_apply_scaffold(), fixture_operations=fixture_operations()
    )
    second = compile_region_apply_receipt(
        scaffold=ready_apply_scaffold(), fixture_operations=fixture_operations()
    )

    assert first["schema_version"] == "typed-region-apply-receipt.v1"
    assert first["ok"] is True
    assert first["mutation_attempted"] is False
    assert first["live_apply_attempted"] is False
    assert first["ready_for_live_apply"] is False
    assert first["ready_for_postflight"] is True
    assert first["blocked_reasons"] == []
    assert first["fixture"]["operation_count"] == 2
    assert first["receipt_digest"] == second["receipt_digest"]
    assert first["source_receipts"] == second["source_receipts"]
    assert "verify_fixture_operation_digest" in first["postflight_required"]
    assert first["boundary"] == {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_apply_receipt_blocks_failed_scaffold_without_mutation() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    scaffold = ready_apply_scaffold()
    scaffold["ok"] = False
    scaffold["ready_for_live_apply"] = False
    scaffold["blocked_reasons"] = ["preflight_not_ready"]

    result = compile_region_apply_receipt(
        scaffold=scaffold, fixture_operations=fixture_operations()
    )

    assert result["ok"] is False
    assert result["mutation_attempted"] is False
    assert result["live_apply_attempted"] is False
    assert result["ready_for_postflight"] is False
    assert "apply_scaffold_not_ready" in result["blocked_reasons"]
    assert "apply_scaffold:preflight_not_ready" in result["blocked_reasons"]


def test_apply_receipt_rejects_undeclared_region_target() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    with pytest.raises(ValueError, match="undeclared region"):
        compile_region_apply_receipt(
            scaffold=ready_apply_scaffold(),
            fixture_operations=fixture_operations(region_id="other-region"),
        )


def test_apply_receipt_rejects_external_reference_keys() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    operations = fixture_operations()
    operations[0]["external_ref"] = "item-123"

    with pytest.raises(ValueError, match="unsupported keys"):
        compile_region_apply_receipt(
            scaffold=ready_apply_scaffold(), fixture_operations=operations
        )


def test_apply_receipt_blocks_snapshot_digest_mismatch() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    scaffold = ready_apply_scaffold()
    scaffold["snapshot"]["content_digest"] = "e" * 64

    result = compile_region_apply_receipt(
        scaffold=scaffold, fixture_operations=fixture_operations()
    )

    assert result["ok"] is False
    assert result["ready_for_postflight"] is False
    assert "apply_scaffold_snapshot_digest_mismatch" in result["blocked_reasons"]


def test_apply_receipt_blocks_non_managed_region() -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    scaffold = ready_apply_scaffold()
    scaffold["region"]["mode"] = "manual"

    result = compile_region_apply_receipt(
        scaffold=scaffold, fixture_operations=fixture_operations()
    )

    assert result["ok"] is False
    assert result["ready_for_postflight"] is False
    assert "apply_scaffold_region_not_managed" in result["blocked_reasons"]


def test_apply_receipt_writes_receipt(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_apply_receipt

    output = tmp_path / "apply-receipt.json"
    result = compile_region_apply_receipt(
        scaffold=ready_apply_scaffold(),
        fixture_operations=fixture_operations(),
        output_path=output,
    )

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == "typed-region-apply-receipt.v1"
    assert written["receipt_digest"] == result["receipt_digest"]
    assert result["output_path"] == str(output.absolute())


def test_load_region_apply_scaffold_accepts_schema(tmp_path) -> None:
    from schauwerk.operator.regions import load_region_apply_scaffold

    source = tmp_path / "apply-scaffold.json"
    source.write_text(json.dumps(ready_apply_scaffold()), encoding="utf-8")

    loaded = load_region_apply_scaffold(source)

    assert loaded["schema_version"] == "typed-region-apply-scaffold.v1"
    assert loaded["ok"] is True


def test_load_region_apply_scaffold_rejects_wrong_schema(tmp_path) -> None:
    from schauwerk.operator.regions import load_region_apply_scaffold

    source = tmp_path / "apply-scaffold.json"
    source.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema"):
        load_region_apply_scaffold(source)


def test_load_fixture_operations_accepts_wrapped_yaml(tmp_path) -> None:
    from schauwerk.operator.regions import load_fixture_operations

    source = tmp_path / "fixture-ops.yml"
    source.write_text(
        """
fixture_operations:
  - operation_id: create-title
    action: create-item
    region_id: cluster-goals
    local_ref: title-card
    payload_digest: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
""".strip(),
        encoding="utf-8",
    )

    loaded = load_fixture_operations(source)

    assert loaded == [
        {
            "operation_id": "create-title",
            "action": "create-item",
            "region_id": "cluster-goals",
            "local_ref": "title-card",
            "payload_digest": "c" * 64,
        }
    ]


def test_load_fixture_operations_rejects_non_list(tmp_path) -> None:
    from schauwerk.operator.regions import load_fixture_operations

    source = tmp_path / "fixture-ops.json"
    source.write_text(json.dumps({"fixture_operations": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a list"):
        load_fixture_operations(source)


def ready_apply_receipt() -> dict:
    from schauwerk.operator.regions import compile_region_apply_receipt

    return compile_region_apply_receipt(
        scaffold=ready_apply_scaffold(), fixture_operations=fixture_operations()
    )


def after_snapshot_receipt(digest: str = "e" * 64, alias: str | None = None) -> dict:
    declaration = parse_region_declaration(managed_region())
    return {
        "board_alias": alias or declaration.surface_alias,
        "content_digest": digest,
        "item_count": 6,
        "repeatability_verified": True,
        "sanitized_references": True,
    }


def test_postflight_receipt_is_fixture_only_and_ready_for_restore() -> None:
    from schauwerk.operator.regions import compile_region_postflight_receipt

    result = compile_region_postflight_receipt(
        apply_receipt=ready_apply_receipt(), after_snapshot=after_snapshot_receipt()
    )

    assert result["schema_version"] == "typed-region-postflight-receipt.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["live_postflight_attempted"] is False
    assert result["ready_for_restore"] is True
    assert result["blocked_reasons"] == []
    assert result["pre_apply_snapshot"]["content_digest"] == "a" * 64
    assert result["after_snapshot"]["content_digest"] == "e" * 64
    assert result["boundary"] == {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_postflight_receipt_blocks_alias_mismatch() -> None:
    from schauwerk.operator.regions import compile_region_postflight_receipt

    result = compile_region_postflight_receipt(
        apply_receipt=ready_apply_receipt(),
        after_snapshot=after_snapshot_receipt(alias="other-board"),
    )

    assert result["ok"] is False
    assert result["ready_for_restore"] is False
    assert "after_snapshot_board_alias_mismatch" in result["blocked_reasons"]


def test_postflight_receipt_writes_receipt(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_postflight_receipt

    output = tmp_path / "postflight.json"
    result = compile_region_postflight_receipt(
        apply_receipt=ready_apply_receipt(),
        after_snapshot=after_snapshot_receipt(),
        output_path=output,
    )

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == "typed-region-postflight-receipt.v1"
    assert written["receipt_digest"] == result["receipt_digest"]


def ready_postflight_receipt() -> dict:
    from schauwerk.operator.regions import compile_region_postflight_receipt

    return compile_region_postflight_receipt(
        apply_receipt=ready_apply_receipt(), after_snapshot=after_snapshot_receipt()
    )


def test_restore_receipt_is_fixture_only_and_ready_for_closeout() -> None:
    from schauwerk.operator.regions import compile_region_restore_receipt

    result = compile_region_restore_receipt(
        postflight_receipt=ready_postflight_receipt(),
        restored_snapshot=after_snapshot_receipt(digest="a" * 64),
    )

    assert result["schema_version"] == "typed-region-restore-receipt.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["live_restore_attempted"] is False
    assert result["ready_for_closeout"] is True
    assert result["blocked_reasons"] == []
    assert result["restored_snapshot"]["content_digest"] == "a" * 64
    assert result["boundary"] == {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_restore_receipt_blocks_digest_mismatch() -> None:
    from schauwerk.operator.regions import compile_region_restore_receipt

    result = compile_region_restore_receipt(
        postflight_receipt=ready_postflight_receipt(),
        restored_snapshot=after_snapshot_receipt(digest="f" * 64),
    )

    assert result["ok"] is False
    assert result["ready_for_closeout"] is False
    assert "restored_snapshot_digest_mismatch" in result["blocked_reasons"]


def test_restore_receipt_writes_receipt(tmp_path) -> None:
    from schauwerk.operator.regions import compile_region_restore_receipt

    output = tmp_path / "restore.json"
    result = compile_region_restore_receipt(
        postflight_receipt=ready_postflight_receipt(),
        restored_snapshot=after_snapshot_receipt(digest="a" * 64),
        output_path=output,
    )

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == "typed-region-restore-receipt.v1"
    assert written["receipt_digest"] == result["receipt_digest"]


def test_load_region_postflight_receipt_rejects_wrong_schema(tmp_path) -> None:
    from schauwerk.operator.regions import load_region_postflight_receipt

    source = tmp_path / "postflight.json"
    source.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema"):
        load_region_postflight_receipt(source)
