from __future__ import annotations

import json
from pathlib import Path

from schauwerk.operator.live_apply import (
    _validate_gate_receipt,
    compile_live_operation_bundle,
    validate_live_apply_plan,
    validate_live_authorization,
    validate_live_operation_bundle,
)

ROOT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "operators"
    / "evidence"
    / "sw009-live-executor-20260711"
)


def read(name: str) -> dict:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_sw009_acceptance_evidence_is_cross_bound_and_non_authoritative() -> None:
    gate, region = _validate_gate_receipt(read("gate-receipt.json"))
    draft = read("operation-draft.json")
    bundle = validate_live_operation_bundle(read("operation-bundle.json"))
    authorization = validate_live_authorization(read("authorization.json"))
    plan = validate_live_apply_plan(read("live-plan.json"))

    assert compile_live_operation_bundle(draft) == bundle
    assert bundle["surface_alias"] == region.surface_alias == "sw009-fixture-board"
    assert authorization["gate_receipt_digest"] == gate["receipt_digest"]
    assert authorization["operation_bundle_digest"] == bundle["bundle_digest"]
    assert plan["source_receipts"]["authorization_digest"] == authorization[
        "authorization_digest"
    ]
    assert authorization["expires_at"] == "2026-07-11T00:15:00Z"
    assert plan["mutation_attempted"] is False
    assert plan["live_apply_attempted"] is False


def test_sw009_provider_capability_evidence_is_sanitized() -> None:
    evidence = read("provider-capabilities.json")
    assert evidence["required_tools_present"] is True
    assert evidence["observed_required_tools"] == ["layout_read", "layout_update"]
    assert evidence["provider_identifiers_included"] is False
    assert evidence["mutation_attempted"] is False


def test_sw009_failure_matrix_is_fixture_only() -> None:
    matrix = read("failure-matrix.json")
    assert matrix["fixture_only"] is True
    assert matrix["productive_provider_mutation_attempted"] is False
    assert len(matrix["cases"]) >= 12
