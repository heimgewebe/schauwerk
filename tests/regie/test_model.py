from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from schauwerk.operator.live_apply import compile_live_operation_bundle
from schauwerk.regie.model import (
    REGIE_CONTEXT_SCHEMA,
    REGIE_DECISION_SCHEMA,
    REGIE_REVIEW_SCHEMA,
    compile_decision_receipt,
    compile_regie_context,
    compile_review_bundle,
    load_regie_context,
    manifest_digest,
    validate_decision_receipt,
    validate_regie_context,
    validate_review_bundle,
    write_private_json,
)

EVIDENCE = Path("docs/operators/evidence/sw009-live-executor-20260711")
NOW = datetime(2026, 7, 11, 2, 0, tzinfo=UTC)


def read(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def context() -> dict:
    return compile_regie_context(
        {
            "review_id": "regie-review-test",
            "title": "Managed summary review",
            "summary": "Review two bounded text replacements before any provider effect.",
            "instructions": [
                "Check source freshness before approval.",
                "Approve each operation independently.",
            ],
            "sources": [
                {
                    "source_id": "repo-main",
                    "title": "Repository main",
                    "revision": "b54f3ef1",
                    "observed_at": "2026-07-11T01:50:00Z",
                    "freshness": "fresh",
                    "visibility": "internal",
                    "citation": "repo:schauwerk@b54f3ef1",
                    "uncertainty": 0.02,
                },
                {
                    "source_id": "provider-snapshot",
                    "title": "Provider snapshot",
                    "revision": "a" * 64,
                    "observed_at": "2026-07-10T20:00:00Z",
                    "freshness": "stale",
                    "visibility": "private",
                    "citation": "snapshot:fixture-before",
                    "uncertainty": 0.35,
                },
            ],
            "context": [
                {
                    "label": "Target",
                    "value": "One allowlisted managed summary region",
                    "state": "constraint",
                    "source_id": "repo-main",
                },
                {
                    "label": "Revision risk",
                    "value": "Provider snapshot requires a current preflight read",
                    "state": "risk",
                    "source_id": "provider-snapshot",
                },
            ],
        }
    )


def review() -> dict:
    original = read("operation-bundle.json")
    first = original["operations"][0]
    draft = {
        key: value
        for key, value in original.items()
        if key not in {"schema_version", "bundle_digest", "operations"}
    }
    draft["schema_version"] = "typed-region-live-operation-draft.v1"
    draft["operations"] = [
        first,
        {
            "operation_id": "replace-reviewed-detail",
            "action": "replace-text",
            "region_id": original["region_id"],
            "old_text": "[schauwerk-region:managed-summary] OLD FIXTURE DETAIL",
            "new_text": "[schauwerk-region:managed-summary] NEW FIXTURE DETAIL",
        },
    ]
    return compile_review_bundle(
        context=context(),
        gate_receipt=read("gate-receipt.json"),
        operation_bundle=compile_live_operation_bundle(draft),
        created_at=NOW,
    )


def test_context_is_digest_bound_and_owner_only_loadable(tmp_path: Path) -> None:
    value = context()
    assert value["schema_version"] == REGIE_CONTEXT_SCHEMA
    assert value["context_digest"] == manifest_digest(value, "context_digest")
    path = write_private_json(tmp_path / "context.json", value, label="context")
    assert path.stat().st_mode & 0o077 == 0
    assert load_regie_context(path) == value
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        load_regie_context(path)


def test_review_projects_stale_sources_uncertainty_and_visual_diff() -> None:
    value = review()
    assert value["schema_version"] == REGIE_REVIEW_SCHEMA
    assert value["stale_source_ids"] == ["provider-snapshot"]
    assert value["maximum_uncertainty"] == 0.35
    assert value["boundary"]["no_mutation_authority"] is True
    operation = value["operations"][0]
    assert operation["default_decision"] == "defer"
    assert {segment["kind"] for segment in operation["visual_diff"]} >= {
        "equal",
        "delete",
        "insert",
    }
    assert validate_review_bundle(value) == value


def test_partial_approval_compiles_new_bundle_authorization_and_plan() -> None:
    value = review()
    first, second = [item["operation_id"] for item in value["operations"]]
    decision = compile_decision_receipt(
        review_bundle=value,
        decisions={first: "approve", second: "reject"},
        approved_by="alex",
        approval_reference="bureau:schauwerk-t008",
        confirmation="APPROVE_LIVE_APPLY",
        valid_minutes=60,
        decided_at=NOW,
    )
    assert decision["schema_version"] == REGIE_DECISION_SCHEMA
    assert decision["approved_operation_ids"] == [first]
    assert decision["rejected_operation_ids"] == [second]
    assert decision["deferred_operation_ids"] == []
    assert [
        operation["operation_id"] for operation in decision["selected_bundle"]["operations"]
    ] == [first]
    assert decision["plan"]["operations"] == decision["selected_bundle"]["operations"]
    assert (
        decision["plan"]["authorization"]["authorization_id"]
        == decision["authorization"]["authorization_id"]
    )
    assert (
        decision["plan"]["source_receipts"]["authorization_digest"]
        == decision["authorization"]["authorization_digest"]
    )
    assert decision["boundary"]["no_provider_mutation"] is True
    assert validate_decision_receipt(decision) == decision


def test_decision_requires_total_coverage_one_approval_and_exact_confirmation() -> None:
    value = review()
    first, second = [item["operation_id"] for item in value["operations"]]
    common = {
        "review_bundle": value,
        "approved_by": "alex",
        "approval_reference": "bureau:schauwerk-t008",
        "valid_minutes": 60,
        "decided_at": NOW,
    }
    with pytest.raises(ValueError, match="cover every operation"):
        compile_decision_receipt(
            decisions={first: "approve"}, confirmation="APPROVE_LIVE_APPLY", **common
        )
    with pytest.raises(ValueError, match="approve at least one"):
        compile_decision_receipt(
            decisions={first: "reject", second: "defer"},
            confirmation="APPROVE_LIVE_APPLY",
            **common,
        )
    with pytest.raises(ValueError, match="confirmation is invalid"):
        compile_decision_receipt(
            decisions={first: "approve", second: "defer"},
            confirmation="approve",
            **common,
        )


def test_review_rejects_tampered_stale_projection() -> None:
    value = review()
    value["stale_source_ids"] = []
    value["review_digest"] = manifest_digest(value, "review_digest")
    with pytest.raises(ValueError, match="stale source projection"):
        validate_review_bundle(value)


def test_context_rejects_provider_references_and_unknown_sources() -> None:
    value = context()
    value["sources"][0]["citation"] = "https://miro.com/private"
    value["context_digest"] = manifest_digest(value, "context_digest")
    with pytest.raises(ValueError, match="provider or network reference"):
        validate_regie_context(value)

    value = context()
    value["context"][0]["source_id"] = "missing-source"
    value["context_digest"] = manifest_digest(value, "context_digest")
    with pytest.raises(ValueError, match="unknown"):
        validate_regie_context(value)


def test_long_review_id_uses_digest_based_effect_identifiers() -> None:
    base = review()
    long_context = compile_regie_context(
        {
            "review_id": "r" * 80,
            "title": base["title"],
            "summary": base["summary"],
            "instructions": base["instructions"],
            "sources": base["sources"],
            "context": base["context"],
        }
    )
    value = compile_review_bundle(
        context=long_context,
        gate_receipt=base["gate_receipt"],
        operation_bundle=base["operation_bundle"],
        created_at=NOW,
    )
    first, second = [item["operation_id"] for item in value["operations"]]
    decision = compile_decision_receipt(
        review_bundle=value,
        decisions={first: "approve", second: "defer"},
        approved_by="alex",
        approval_reference="bureau:schauwerk-t008",
        confirmation="APPROVE_LIVE_APPLY",
        valid_minutes=60,
        decided_at=NOW,
    )
    assert decision["selected_bundle"]["bundle_id"].startswith("regie-")
    assert len(decision["selected_bundle"]["bundle_id"]) < 81
    assert len(decision["authorization"]["authorization_id"]) < 81
