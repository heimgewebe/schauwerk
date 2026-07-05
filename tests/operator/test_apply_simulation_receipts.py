from __future__ import annotations

import json

import pytest

from schauwerk.operator.regions import (
    compile_region_apply_scaffold,
    compile_region_apply_simulation_receipt,
    compile_region_operation_contract,
    load_region_apply_simulation_receipt,
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
