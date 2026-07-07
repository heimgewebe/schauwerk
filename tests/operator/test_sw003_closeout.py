from __future__ import annotations

from typing import Any

from schauwerk.operator.receipts import _stable_digest, _without_runtime_fields
from schauwerk.operator.regions import (
    compile_region_apply_receipt,
    compile_region_apply_scaffold,
    compile_region_postflight_receipt,
    compile_region_restore_receipt,
    compile_sw003_closeout_receipt,
    evaluate_sw003_live_gate_claim,
    load_sw003_closeout_receipt,
    parse_region_declaration,
    required_sw003_live_gate_evidence,
)

MARKER = "schauwerk-sw003-20260629T050000Z-abc123"


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


def snapshot(alias: str, digest: str) -> dict:
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


def ready_restore_receipt() -> dict:
    declaration = parse_region_declaration(managed_region())
    preflight = {
        "schema_version": "typed-region-preflight.v1",
        "ok": True,
        "ready_for_apply": True,
        "mutation_attempted": False,
        "operation": "render-update",
        "region": declaration.to_dict(),
        "snapshot": snapshot(declaration.surface_alias, "a" * 64),
        "blocked_reasons": [],
        "boundary": {"no_miro_mutation": True},
    }
    scaffold = compile_region_apply_scaffold(preflight=preflight)
    apply_receipt = compile_region_apply_receipt(
        scaffold=scaffold, fixture_operations=fixture_operations()
    )
    after = snapshot(declaration.surface_alias, "e" * 64) | {
        "fixture_operations_digest": apply_receipt["source_receipts"][
            "fixture_operations_digest"
        ],
        "idempotency_key": apply_receipt["idempotency"]["key"],
        "idempotency_verified": True,
    }
    postflight = compile_region_postflight_receipt(
        apply_receipt=apply_receipt,
        after_snapshot=after,
    )
    return compile_region_restore_receipt(
        postflight_receipt=postflight,
        restored_snapshot=snapshot(declaration.surface_alias, "a" * 64),
    )


def closeout_evidence(
    marker: str = MARKER, *, restore_receipt: dict[str, Any] | None = None
) -> dict:
    restore = restore_receipt or ready_restore_receipt()
    restore_digest = _stable_digest(_without_runtime_fields(restore))
    region = restore["region"]
    return {
        "restore_receipt_digest": restore_digest,
        "marker": marker,
        "region": {
            "region_id": region["region_id"],
            "surface_alias": region["surface_alias"],
        },
        "verification": {
            "create_verified": True,
            "create_evidence_digest": "1" * 64,
            "read_verified": True,
            "read_evidence_digest": "2" * 64,
            "update_verified": True,
            "update_evidence_digest": "3" * 64,
            "marker_scope_verified": True,
            "marker_scope_evidence_digest": "4" * 64,
            "idempotency_verified": True,
            "idempotency_key": "fixture-idempotency-key",
            "idempotency_evidence_digest": "5" * 64,
        },
        "cleanup": {
            "mode": "explicit-boundary",
            "remote_cleanup_supported": False,
            "remote_cleanup_attempted": False,
            "boundary_reason": "miro_remote_cleanup_unavailable",
            "restore_receipt_digest": restore_digest,
        },
    }


def complete_live_gate_claim() -> dict[str, Any]:
    return {
        "claim_closes_live_sw003_gate": True,
        "live_create_attempted": True,
        "live_create_verified": True,
        "live_create_evidence_digest": "6" * 64,
        "live_read_after_create_verified": True,
        "live_read_after_create_evidence_digest": "7" * 64,
        "live_update_verified": True,
        "live_update_evidence_digest": "8" * 64,
        "marker_scope_uniqueness_verified": True,
        "marker_scope_evidence_digest": "9" * 64,
        "idempotency_verified": True,
        "idempotency_evidence_digest": "a" * 64,
        "cleanup_attempted": True,
        "cleanup_verified": True,
        "cleanup_evidence_digest": "b" * 64,
        "provider_identifiers_sanitized": True,
        "board_scope": {
            "surface_alias": "sw003-live-proof",
            "allowlisted": True,
        },
        "board_scope_evidence_digest": "c" * 64,
    }


def test_sw003_closeout_receipt_ready_with_boundary() -> None:
    restore_receipt = ready_restore_receipt()
    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=closeout_evidence(restore_receipt=restore_receipt),
        marker=MARKER,
    )

    assert result["schema_version"] == "typed-region-sw003-closeout-receipt.v1"
    assert result["ok"] is True
    assert result["ready_for_sw003_tracker_update"] is True
    assert result["closes_live_sw003_gate"] is False
    assert result["cleanup_complete"] is False
    assert result["cleanup_boundary_accepted"] is True
    assert result["boundary"] == {
        "fixture_only": True,
        "sw003_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def test_sw003_closeout_receipt_blocks_wrong_restore_digest() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["restore_receipt_digest"] = "f" * 64

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "evidence_restore_receipt_digest_mismatch" in result["blocked_reasons"]


def test_sw003_closeout_receipt_blocks_wrong_region_binding() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["region"]["region_id"] = "other-region"

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "evidence_region_id_mismatch" in result["blocked_reasons"]


def test_sw003_closeout_receipt_blocks_missing_update_evidence_digest() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["verification"].pop("update_evidence_digest")

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "evidence_update_evidence_digest_missing" in result["blocked_reasons"]


def test_sw003_closeout_receipt_blocks_cleanup_digest_mismatch() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["cleanup"]["restore_receipt_digest"] = "f" * 64

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "cleanup_restore_receipt_digest_mismatch" in result["blocked_reasons"]


def test_sw003_closeout_receipt_blocks_remote_cleanup_claim() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["cleanup"]["remote_cleanup_supported"] = True

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "cleanup_boundary_remote_supported_claimed" in result["blocked_reasons"]


def test_sw003_closeout_receipt_blocks_and_sanitizes_freeform_cleanup_reason() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["cleanup"]["boundary_reason"] = "https://miro.com/app/board/private-id"

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert "cleanup_boundary_reason_unsafe" in result["blocked_reasons"]
    assert "miro.com" not in result["cleanup"]["boundary_reason"]


def test_sw003_closeout_receipt_marks_restored_snapshot_cleanup_complete() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    restore_digest = evidence["restore_receipt_digest"]
    evidence["cleanup"] = {
        "mode": "restored-snapshot",
        "verified": True,
        "restore_receipt_digest": restore_digest,
    }

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is True
    assert result["cleanup_complete"] is True
    assert result["cleanup_boundary_accepted"] is False


def test_sw003_closeout_receipt_writes_and_loads(tmp_path) -> None:
    restore_receipt = ready_restore_receipt()
    output = tmp_path / "sw003-closeout.json"

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=closeout_evidence(restore_receipt=restore_receipt),
        marker=MARKER,
        output_path=output,
    )
    loaded = load_sw003_closeout_receipt(output)

    assert result["ok"] is True
    assert loaded["schema_version"] == "typed-region-sw003-closeout-receipt.v1"
    assert loaded["marker"] == MARKER


def test_sw003_closeout_receipt_exposes_live_gate_requirements_without_closing() -> None:
    restore_receipt = ready_restore_receipt()
    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=closeout_evidence(restore_receipt=restore_receipt),
        marker=MARKER,
    )

    required_keys = {item["key"] for item in required_sw003_live_gate_evidence()}
    assert "live_create_attempted" in required_keys
    assert "cleanup_verified_or_boundary_accepted" in required_keys
    assert result["closes_live_sw003_gate"] is False
    assert result["live_gate"]["claim_present"] is False
    assert result["live_gate"]["candidate_closes_live_sw003_gate"] is False
    assert result["live_gate"]["fixture_only_receipt_closes_live_gate"] is False
    assert "sw003_live_gate_closure" in result["non_claims"]


def test_sw003_live_gate_claim_blocks_incomplete_evidence() -> None:
    claim = complete_live_gate_claim()
    claim.pop("live_update_evidence_digest")
    claim["idempotency_verified"] = False

    result = evaluate_sw003_live_gate_claim(claim)

    assert result["claim_present"] is True
    assert result["claim_valid"] is False
    assert result["candidate_closes_live_sw003_gate"] is False
    assert "evidence_live_update_evidence_digest_missing" in result["blocked_reasons"]
    assert "evidence_idempotency_verified_missing_or_false" in result["blocked_reasons"]


def test_sw003_live_gate_claim_accepts_complete_sanitized_evidence() -> None:
    result = evaluate_sw003_live_gate_claim(complete_live_gate_claim())

    assert result["claim_valid"] is True
    assert result["candidate_closes_live_sw003_gate"] is True
    assert result["normalized"]["board_scope"] == {
        "surface_alias": "sw003-live-proof",
        "allowlisted": True,
    }


def test_sw003_live_gate_claim_blocks_and_sanitizes_provider_identifiers() -> None:
    claim = complete_live_gate_claim()
    claim["cleanup_verified"] = False
    claim["cleanup_boundary_accepted"] = True
    claim["cleanup_boundary_reason"] = "https://miro.com/app/board/private-id"

    result = evaluate_sw003_live_gate_claim(claim)
    rendered = repr(result)

    assert result["claim_valid"] is False
    assert result["candidate_closes_live_sw003_gate"] is False
    assert "provider_identifier_present_in_live_gate_claim" in result["blocked_reasons"]
    assert "cleanup_boundary_reason_unsafe" in result["blocked_reasons"]
    assert "miro.com" not in rendered
    assert "private-id" not in rendered
    assert (
        result["normalized"]["cleanup"]["cleanup_boundary_reason"]
        == "unsafe-live-gate-reason-rejected"
    )



def test_sw003_live_gate_claim_never_echoes_invalid_digest_provider_data() -> None:
    claim = complete_live_gate_claim()
    claim["live_create_evidence_digest"] = "https://miro.com/app/board/private-id"

    result = evaluate_sw003_live_gate_claim(claim)
    rendered = repr(result)

    assert result["claim_valid"] is False
    assert result["candidate_closes_live_sw003_gate"] is False
    assert "evidence_live_create_evidence_digest_invalid" in result["blocked_reasons"]
    assert result["normalized"]["evidence_digests"]["live_create_evidence_digest"] is None
    assert "miro.com" not in rendered
    assert "private-id" not in rendered


def test_sw003_closeout_receipt_rejects_embedded_live_gate_claim() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    evidence["live_gate_claim"] = complete_live_gate_claim()

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert result["closes_live_sw003_gate"] is False
    assert result["live_gate"]["candidate_closes_live_sw003_gate"] is True
    assert result["live_gate"]["fixture_only_receipt_closes_live_gate"] is False
    assert result["live_gate"].get("closes_live_sw003_gate") is None
    assert "live_gate_claim_not_allowed_in_fixture_closeout" in result["blocked_reasons"]


def test_sw003_closeout_receipt_rejects_invalid_embedded_live_gate_claim() -> None:
    restore_receipt = ready_restore_receipt()
    evidence = closeout_evidence(restore_receipt=restore_receipt)
    claim = complete_live_gate_claim()
    claim.pop("cleanup_evidence_digest")
    evidence["live_gate_claim"] = claim

    result = compile_sw003_closeout_receipt(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=MARKER,
    )

    assert result["ok"] is False
    assert result["live_gate"]["candidate_closes_live_sw003_gate"] is False
    assert "live_gate_claim_not_allowed_in_fixture_closeout" in result["blocked_reasons"]
    assert "live_gate_claim_invalid_in_fixture_closeout" in result["blocked_reasons"]
