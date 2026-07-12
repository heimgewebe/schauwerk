from __future__ import annotations

import hashlib
import json

import pytest

from schauwerk.operator.regions import (
    compile_region_apply_scaffold,
    compile_region_apply_simulation_receipt,
    compile_region_operation_contract,
    compile_region_restore_receipt,
    compile_region_simulation_closeout_receipt,
    compile_region_simulation_postflight_receipt,
    load_region_apply_simulation_receipt,
    load_region_simulation_closeout_receipt,
    parse_region_declaration,
)


def _stable_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt_digest(value: dict) -> str:
    return _stable_digest(
        {key: item for key, item in value.items() if key not in {"output_path", "receipt_digest"}}
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


def snapshot_receipt(alias: str, digest: str) -> dict:
    return {
        "board_alias": alias,
        "content_digest": digest,
        "item_count": 4,
        "repeatability_verified": True,
        "sanitized_references": True,
    }


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


def ready_operation_contract() -> dict:
    declaration = parse_region_declaration(managed_region())
    preflight = {
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
    scaffold = compile_region_apply_scaffold(preflight=preflight)
    return compile_region_operation_contract(
        scaffold=scaffold, fixture_operations=fixture_operations()
    )


def after_snapshot(contract: dict) -> dict:
    alias = contract["region"]["surface_alias"]
    return {
        "board_alias": alias,
        "content_digest": "e" * 64,
        "item_count": 6,
        "repeatability_verified": True,
        "sanitized_references": True,
        "operation_contract_digest": contract["contract_digest"],
        "operation_contract_operations_digest": contract["operations_digest"],
        "idempotency_key": contract["idempotency"]["key"],
        "idempotency_verified": True,
    }


def ready_apply_simulation_receipt() -> dict:
    contract = ready_operation_contract()
    return compile_region_apply_simulation_receipt(
        operation_contract=contract,
        after_snapshot=after_snapshot(contract),
    )


def ready_simulation_restore_receipt() -> dict:
    postflight = compile_region_simulation_postflight_receipt(
        apply_simulation_receipt=ready_apply_simulation_receipt()
    )
    restored = dict(postflight["pre_apply_snapshot"])
    restored["repeatability_verified"] = True
    restored["sanitized_references"] = True
    return compile_region_restore_receipt(
        postflight_receipt=postflight,
        restored_snapshot=restored,
    )


def test_apply_simulation_receipt_passes_for_matching_contract_evidence() -> None:
    contract = ready_operation_contract()

    result = compile_region_apply_simulation_receipt(
        operation_contract=contract,
        after_snapshot=after_snapshot(contract),
    )

    assert result["schema_version"] == "typed-region-apply-simulation-receipt.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["live_apply_attempted"] is False
    assert result["ready_for_postflight"] is True
    assert result["blocked_reasons"] == []
    assert result["verification"] == {
        "operation_contract_digest": contract["contract_digest"],
        "operation_contract_operations_digest": contract["operations_digest"],
        "idempotency_key": contract["idempotency"]["key"],
        "idempotency_verified": True,
    }
    assert result["boundary"] == {
        "fixture_only": True,
        "simulation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }
    assert result["restore_required"] is True
    assert "after_snapshot_input_digest" in result["source_receipts"]


def test_apply_simulation_receipt_blocks_mismatched_contract_evidence() -> None:
    contract = ready_operation_contract()
    snapshot = after_snapshot(contract)
    snapshot["operation_contract_operations_digest"] = "f" * 64
    snapshot["idempotency_verified"] = False

    result = compile_region_apply_simulation_receipt(
        operation_contract=contract,
        after_snapshot=snapshot,
    )

    assert result["ok"] is False
    assert result["ready_for_postflight"] is False
    assert result["mutation_attempted"] is False
    assert "after_snapshot_operations_digest_mismatch" in result["blocked_reasons"]
    assert "after_snapshot_idempotency_unverified" in result["blocked_reasons"]


def test_apply_simulation_receipt_writes_and_loads_receipt(tmp_path) -> None:
    contract = ready_operation_contract()
    output = tmp_path / "apply-simulation.json"

    result = compile_region_apply_simulation_receipt(
        operation_contract=contract,
        after_snapshot=after_snapshot(contract),
        output_path=output,
    )
    loaded = load_region_apply_simulation_receipt(output)

    assert result["ok"] is True
    assert loaded["schema_version"] == "typed-region-apply-simulation-receipt.v1"
    assert loaded["ok"] is True


def test_load_region_apply_simulation_receipt_rejects_wrong_schema(tmp_path) -> None:
    source = tmp_path / "apply-simulation.json"
    source.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema"):
        load_region_apply_simulation_receipt(source)


def test_simulation_postflight_receipt_is_restore_ready() -> None:
    simulation = ready_apply_simulation_receipt()

    result = compile_region_simulation_postflight_receipt(apply_simulation_receipt=simulation)

    assert result["schema_version"] == "typed-region-postflight-receipt.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["live_postflight_attempted"] is False
    assert result["ready_for_restore"] is True
    assert result["boundary"] == {
        "fixture_only": True,
        "simulation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }
    assert "apply_simulation_receipt_digest" in result["source_receipts"]

    restored = dict(result["pre_apply_snapshot"])
    restored["repeatability_verified"] = True
    restored["sanitized_references"] = True
    restore = compile_region_restore_receipt(
        postflight_receipt=result,
        restored_snapshot=restored,
    )
    assert restore["ok"] is True
    assert restore["ready_for_closeout"] is True


def test_simulation_postflight_receipt_blocks_unready_simulation() -> None:
    simulation = ready_apply_simulation_receipt()
    simulation["ok"] = False
    simulation["ready_for_postflight"] = False
    simulation["blocked_reasons"] = ["after_snapshot_idempotency_unverified"]

    result = compile_region_simulation_postflight_receipt(apply_simulation_receipt=simulation)

    assert result["ok"] is False
    assert result["ready_for_restore"] is False
    assert "apply_simulation_receipt_not_ready" in result["blocked_reasons"]


def test_simulation_postflight_receipt_writes_receipt(tmp_path) -> None:
    output = tmp_path / "simulation-postflight.json"

    result = compile_region_simulation_postflight_receipt(
        apply_simulation_receipt=ready_apply_simulation_receipt(),
        output_path=output,
    )
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert loaded["schema_version"] == "typed-region-postflight-receipt.v1"
    assert loaded["receipt_digest"] == result["receipt_digest"]


def test_simulation_restore_receipt_preserves_simulation_boundary() -> None:
    restore = ready_simulation_restore_receipt()

    assert restore["ok"] is True
    assert restore["boundary"] == {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "simulation_only": True,
    }


def test_simulation_closeout_receipt_closes_only_simulation_chain() -> None:
    restore = ready_simulation_restore_receipt()

    result = compile_region_simulation_closeout_receipt(restore_receipt=restore)

    assert result["schema_version"] == "typed-region-sw009-simulation-closeout-receipt.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
    assert result["live_closeout_attempted"] is False
    assert result["ready_for_sw009_simulation_closeout"] is True
    assert result["ready_for_live_apply"] is False
    assert result["closes_live_sw003_gate"] is False
    assert result["live_apply_gate"]["blocked_reasons"] == ["dedicated_live_apply_gate_required"]
    assert result["boundary"] == {
        "fixture_only": True,
        "simulation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "does_not_close_sw003_live_gate": True,
    }
    assert result["verification"] == {
        "restore_receipt_ok": True,
        "restore_receipt_ready_for_closeout": True,
        "restore_receipt_ready": True,
        "simulation_boundary_valid": True,
        "simulation_provenance_valid": True,
        "restored_to_pre_apply_snapshot": True,
    }
    assert "restore_receipt_digest" in result["source_receipts"]
    assert "apply_simulation_receipt_digest" in result["source_receipts"]


def test_simulation_closeout_blocks_non_simulation_restore_boundary() -> None:
    restore = ready_simulation_restore_receipt()
    restore["boundary"] = {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }

    result = compile_region_simulation_closeout_receipt(restore_receipt=restore)

    assert result["ok"] is False
    assert result["ready_for_sw009_simulation_closeout"] is False
    assert "restore_receipt_simulation_boundary_missing" in result["blocked_reasons"]


def test_simulation_closeout_receipt_writes_and_loads(tmp_path) -> None:
    output = tmp_path / "simulation-closeout.json"

    result = compile_region_simulation_closeout_receipt(
        restore_receipt=ready_simulation_restore_receipt(),
        output_path=output,
    )
    loaded = load_region_simulation_closeout_receipt(output)

    assert result["ok"] is True
    assert loaded["schema_version"] == "typed-region-sw009-simulation-closeout-receipt.v1"
    assert loaded["receipt_digest"] == result["receipt_digest"]


def test_simulation_restore_receipt_carries_simulation_provenance_and_digest() -> None:
    restore = ready_simulation_restore_receipt()

    assert "apply_simulation_receipt_digest" in restore["source_receipts"]
    assert restore["receipt_digest"] == _receipt_digest(restore)

    changed = dict(restore)
    changed["boundary"] = {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }
    assert _receipt_digest(changed) != restore["receipt_digest"]


def test_simulation_closeout_blocks_forged_simulation_boundary_without_provenance() -> None:
    restore = ready_simulation_restore_receipt()
    restore["source_receipts"] = {
        key: value
        for key, value in restore["source_receipts"].items()
        if key != "apply_simulation_receipt_digest"
    }

    result = compile_region_simulation_closeout_receipt(restore_receipt=restore)

    assert result["ok"] is False
    assert "restore_receipt_simulation_provenance_missing" in result["blocked_reasons"]
    assert result["verification"]["simulation_provenance_valid"] is False


def test_simulation_closeout_blocks_missing_ready_and_state_fields() -> None:
    cases = [
        ("ready_for_closeout", "restore_receipt_not_ready_for_closeout"),
        ("mutation_attempted", "restore_receipt_mutation_state_invalid"),
        ("live_restore_attempted", "restore_receipt_live_state_invalid"),
    ]

    for field, reason in cases:
        restore = ready_simulation_restore_receipt()
        restore.pop(field)

        result = compile_region_simulation_closeout_receipt(restore_receipt=restore)

        assert result["ok"] is False
        assert reason in result["blocked_reasons"]


def test_simulation_closeout_digest_binds_safety_fields() -> None:
    result = compile_region_simulation_closeout_receipt(
        restore_receipt=ready_simulation_restore_receipt()
    )

    assert result["receipt_digest"] == _receipt_digest(result)

    for field, value in [
        ("ready_for_live_apply", True),
        ("closes_live_sw003_gate", True),
        ("boundary", {"fixture_only": True}),
        ("live_apply_gate", {"ready_for_live_apply": True}),
    ]:
        mutated = dict(result)
        mutated[field] = value
        assert _receipt_digest(mutated) != result["receipt_digest"]


def test_simulation_closeout_blocks_incomplete_snapshot_identity() -> None:
    restore = ready_simulation_restore_receipt()
    restore["pre_apply_snapshot"] = {}
    restore["restored_snapshot"] = {
        "repeatability_verified": True,
        "sanitized_references": True,
    }

    result = compile_region_simulation_closeout_receipt(restore_receipt=restore)

    assert result["ok"] is False
    assert "restore_receipt_not_restored_to_pre_apply_snapshot" in result["blocked_reasons"]
