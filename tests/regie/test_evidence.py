from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from schauwerk.regie.model import (
    validate_decision_receipt,
    validate_regie_context,
    validate_review_bundle,
)

ROOT = Path("docs/operators/evidence/sw010-regie-20260711")


def read(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_regie_fixture_evidence_is_bound_expired_and_non_authoritative() -> None:
    context = validate_regie_context(read("context.json"))
    review = validate_review_bundle(read("review-bundle.json"))
    decision = validate_decision_receipt(read("decision-receipt.json"))
    assert review["source_receipts"]["context_digest"] == context["context_digest"]
    assert decision["review_digest"] == review["review_digest"]
    assert decision["approved_operation_ids"] == ["replace-reviewed-summary"]
    assert decision["rejected_operation_ids"] == ["replace-reviewed-detail"]
    expires = datetime.fromisoformat(
        decision["authorization"]["expires_at"].removesuffix("Z") + "+00:00"
    ).astimezone(UTC)
    assert expires < datetime(2026, 7, 11, 3, 0, tzinfo=UTC)
    assert decision["boundary"]["no_provider_mutation"] is True


def test_interface_and_failure_evidence_cover_t008_acceptance() -> None:
    interface = read("interface-contract.json")
    assert interface["bind_host"] == "127.0.0.1"
    assert interface["serial_http"] is True
    assert interface["partial_approval"] is True
    assert interface["decision_immutable"] is True
    assert interface["provider_identifiers_in_ui"] is False
    assert interface["mutation_attempted"] is False
    matrix = read("failure-matrix.json")
    text = " ".join(matrix["cases"])
    for phrase in (
        "stale",
        "every operation",
        "expired authorization",
        "kill switch",
        "session token",
        "tampered transaction",
        "apply replay",
        "restore replay",
    ):
        assert phrase in text
    assert matrix["productive_provider_mutation_attempted"] is False


def test_regie_evidence_contains_no_sensitive_runtime_reference() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.iterdir()
        if path.is_file()
    )
    patterns = (
        r"(?i)(?:/home/|/Users/|[A-Z]:\\)",
        r"(?i)https?://(?:www\.)?miro\.com|moveToWidget=",
        r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]",
        r"(?i)widget[_-]?id|item[_-]?id",
        r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b",
    )
    assert not any(re.search(pattern, text) for pattern in patterns)
