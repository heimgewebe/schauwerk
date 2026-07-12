"""Private, receipt-bound review models for the local Regie interface."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from schauwerk.operator.live_apply import (
    LIVE_OPERATION_DRAFT_SCHEMA,
    _validate_gate_receipt,
    compile_live_apply_plan,
    compile_live_authorization,
    compile_live_operation_bundle,
    validate_live_apply_plan,
    validate_live_authorization,
    validate_live_operation_bundle,
)

REGIE_CONTEXT_SCHEMA = "schauwerk-regie-context.v1"
REGIE_REVIEW_SCHEMA = "schauwerk-regie-review-bundle.v1"
REGIE_DECISION_SCHEMA = "schauwerk-regie-decision-receipt.v1"
REGIE_STATE_SCHEMA = "schauwerk-regie-state.v1"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,80}$")
_HEX = re.compile(r"^[a-f0-9]{64}$")
_FORBIDDEN_REFERENCE = re.compile(r"(?i)(?:https?://|miro\.com|moveToWidget=)")
_MAX_PRIVATE_FILE_BYTES = 4 * 1024 * 1024
_MAX_LINE_BYTES = 16 * 1024
_MAX_LIST_ITEMS = 100
_FRESHNESS = frozenset({"fresh", "stale", "partial", "failed", "unknown"})
_VISIBILITY = frozenset({"private", "internal", "public"})
_DECISIONS = frozenset({"approve", "reject", "defer"})


def stable_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def manifest_digest(value: Mapping[str, Any], key: str) -> str:
    return stable_digest({name: item for name, item in value.items() if name != key})


def _safe_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value.strip()):
        raise ValueError(f"{label} has an unsafe identifier shape")
    return value.strip()


def _digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return value


def _line(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{label} must not be empty")
    if "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{label} must be a single line")
    if len(normalized.encode("utf-8")) > _MAX_LINE_BYTES:
        raise ValueError(f"{label} exceeds the 16 KiB limit")
    if _FORBIDDEN_REFERENCE.search(normalized):
        raise ValueError(f"{label} contains a provider or network reference")
    return normalized


def _timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00").astimezone(UTC)
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp") from exc
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _owner_only_path(path: Path, *, label: str, must_exist: bool) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError(f"{label} path is unsafe")
    if must_exist:
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ValueError(f"{label} is unreadable") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise ValueError(f"{label} must be an owner-only regular file")
        if metadata.st_size > _MAX_PRIVATE_FILE_BYTES:
            raise ValueError(f"{label} exceeds the 4 MiB limit")
    else:
        candidate.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if any(parent.is_symlink() for parent in candidate.parents):
            raise ValueError(f"{label} path is unsafe")
    return candidate


def read_private_json(path: Path, *, label: str) -> dict[str, Any]:
    candidate = _owner_only_path(path, label=label, must_exist=True)
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    return value


def write_private_json(path: Path, value: Mapping[str, Any], *, label: str) -> Path:
    destination = _owner_only_path(path, label=label, must_exist=False)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _normalize_source(value: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    expected = {
        "source_id",
        "title",
        "revision",
        "observed_at",
        "freshness",
        "visibility",
        "citation",
        "uncertainty",
    }
    if set(value) != expected:
        raise ValueError(f"sources[{index}] fields are invalid")
    freshness = value.get("freshness")
    if freshness not in _FRESHNESS:
        raise ValueError(f"sources[{index}].freshness is invalid")
    visibility = value.get("visibility")
    if visibility not in _VISIBILITY:
        raise ValueError(f"sources[{index}].visibility is invalid")
    uncertainty = value.get("uncertainty")
    if isinstance(uncertainty, bool) or not isinstance(uncertainty, (int, float)):
        raise ValueError(f"sources[{index}].uncertainty is invalid")
    if not 0 <= float(uncertainty) <= 1:
        raise ValueError(f"sources[{index}].uncertainty is invalid")
    return {
        "source_id": _safe_id(value.get("source_id"), label=f"sources[{index}].source_id"),
        "title": _line(value.get("title"), label=f"sources[{index}].title"),
        "revision": _line(value.get("revision"), label=f"sources[{index}].revision"),
        "observed_at": _timestamp(value.get("observed_at"), label=f"sources[{index}].observed_at"),
        "freshness": freshness,
        "visibility": visibility,
        "citation": _line(value.get("citation"), label=f"sources[{index}].citation"),
        "uncertainty": round(float(uncertainty), 4),
    }


def _normalize_context_item(
    value: Mapping[str, Any], *, index: int, source_ids: set[str]
) -> dict[str, Any]:
    expected = {"label", "value", "state", "source_id"}
    if set(value) != expected:
        raise ValueError(f"context[{index}] fields are invalid")
    state = value.get("state")
    if state not in {"fact", "constraint", "risk", "assumption", "instruction"}:
        raise ValueError(f"context[{index}].state is invalid")
    source_id = _safe_id(value.get("source_id"), label=f"context[{index}].source_id")
    if source_id not in source_ids:
        raise ValueError(f"context[{index}].source_id is unknown")
    return {
        "label": _line(value.get("label"), label=f"context[{index}].label"),
        "value": _line(value.get("value"), label=f"context[{index}].value"),
        "state": state,
        "source_id": source_id,
    }


def validate_regie_context(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "review_id",
        "title",
        "summary",
        "instructions",
        "sources",
        "context",
        "boundary",
        "context_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("Regie context fields are invalid")
    if value.get("schema_version") != REGIE_CONTEXT_SCHEMA:
        raise ValueError("Regie context has an unsupported schema")
    raw_sources = value.get("sources")
    if (
        not isinstance(raw_sources, Sequence)
        or isinstance(raw_sources, (str, bytes))
        or not raw_sources
        or len(raw_sources) > _MAX_LIST_ITEMS
    ):
        raise ValueError("Regie context sources are invalid")
    sources = [
        _normalize_source(item, index=index)
        for index, item in enumerate(raw_sources)
        if isinstance(item, Mapping)
    ]
    if len(sources) != len(raw_sources):
        raise ValueError("Regie context sources are invalid")
    source_ids = {source["source_id"] for source in sources}
    if len(source_ids) != len(sources):
        raise ValueError("Regie context source ids must be unique")
    raw_context = value.get("context")
    if (
        not isinstance(raw_context, Sequence)
        or isinstance(raw_context, (str, bytes))
        or len(raw_context) > _MAX_LIST_ITEMS
    ):
        raise ValueError("Regie context items are invalid")
    context = [
        _normalize_context_item(item, index=index, source_ids=source_ids)
        for index, item in enumerate(raw_context)
        if isinstance(item, Mapping)
    ]
    if len(context) != len(raw_context):
        raise ValueError("Regie context items are invalid")
    raw_instructions = value.get("instructions")
    if (
        not isinstance(raw_instructions, Sequence)
        or isinstance(raw_instructions, (str, bytes))
        or not raw_instructions
        or len(raw_instructions) > 50
    ):
        raise ValueError("Regie instructions are invalid")
    instructions = [
        _line(item, label=f"instructions[{index}]") for index, item in enumerate(raw_instructions)
    ]
    expected_boundary = {
        "local_private_only": True,
        "no_mutation_authority": True,
        "provider_identifiers_excluded": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("Regie context boundary is invalid")
    normalized = {
        "schema_version": REGIE_CONTEXT_SCHEMA,
        "review_id": _safe_id(value.get("review_id"), label="review_id"),
        "title": _line(value.get("title"), label="title"),
        "summary": _line(value.get("summary"), label="summary"),
        "instructions": instructions,
        "sources": sources,
        "context": context,
        "boundary": expected_boundary,
    }
    declared = _digest(value.get("context_digest"), label="context_digest")
    actual = manifest_digest(normalized, "context_digest")
    if declared != actual:
        raise ValueError("Regie context digest mismatch")
    normalized["context_digest"] = actual
    return normalized


def compile_regie_context(value: Mapping[str, Any]) -> dict[str, Any]:
    draft = dict(value)
    draft["schema_version"] = REGIE_CONTEXT_SCHEMA
    draft.setdefault(
        "boundary",
        {
            "local_private_only": True,
            "no_mutation_authority": True,
            "provider_identifiers_excluded": True,
        },
    )
    draft["context_digest"] = manifest_digest(draft, "context_digest")
    return validate_regie_context(draft)


def load_regie_context(path: Path) -> dict[str, Any]:
    return validate_regie_context(read_private_json(path, label="Regie context"))


def _diff_segments(old_text: str, new_text: str) -> list[dict[str, str]]:
    matcher = difflib.SequenceMatcher(a=old_text.split(), b=new_text.split(), autojunk=False)
    segments: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old = " ".join(old_text.split()[i1:i2])
        new = " ".join(new_text.split()[j1:j2])
        if tag == "equal":
            segments.append({"kind": "equal", "text": old})
        elif tag == "delete":
            segments.append({"kind": "delete", "text": old})
        elif tag == "insert":
            segments.append({"kind": "insert", "text": new})
        else:
            if old:
                segments.append({"kind": "delete", "text": old})
            if new:
                segments.append({"kind": "insert", "text": new})
    return segments


def compile_review_bundle(
    *,
    context: Mapping[str, Any],
    gate_receipt: Mapping[str, Any],
    operation_bundle: Mapping[str, Any],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    review_context = validate_regie_context(context)
    gate, declaration = _validate_gate_receipt(gate_receipt)
    bundle = validate_live_operation_bundle(operation_bundle)
    if bundle["surface_alias"] != declaration.surface_alias:
        raise ValueError("Regie bundle alias does not match the gate")
    if bundle["region_id"] != declaration.region_id:
        raise ValueError("Regie bundle region does not match the gate")
    if bundle["expected_snapshot_digest"] != declaration.expected_snapshot_digest:
        raise ValueError("Regie bundle revision does not match the gate")
    if bundle["operation"] != gate.get("operation"):
        raise ValueError("Regie bundle operation does not match the gate")
    operations = [
        {
            **operation,
            "semantic_summary": f"Replace reviewed text in {bundle['region_id']}",
            "visual_diff": _diff_segments(operation["old_text"], operation["new_text"]),
            "default_decision": "defer",
        }
        for operation in bundle["operations"]
    ]
    sources = review_context["sources"]
    observed = (created_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    value = {
        "schema_version": REGIE_REVIEW_SCHEMA,
        "review_id": review_context["review_id"],
        "title": review_context["title"],
        "summary": review_context["summary"],
        "created_at": observed.isoformat().replace("+00:00", "Z"),
        "surface_alias": bundle["surface_alias"],
        "region_id": bundle["region_id"],
        "expected_snapshot_digest": bundle["expected_snapshot_digest"],
        "instructions": review_context["instructions"],
        "sources": sources,
        "context": review_context["context"],
        "stale_source_ids": sorted(
            source["source_id"] for source in sources if source["freshness"] != "fresh"
        ),
        "maximum_uncertainty": max(source["uncertainty"] for source in sources),
        "operations": operations,
        "gate_receipt": gate,
        "operation_bundle": bundle,
        "source_receipts": {
            "context_digest": review_context["context_digest"],
            "gate_receipt_digest": gate["receipt_digest"],
            "operation_bundle_digest": bundle["bundle_digest"],
        },
        "boundary": {
            "local_private_only": True,
            "no_mutation_authority": True,
            "partial_approval_required": True,
            "provider_identifiers_excluded": True,
        },
    }
    value["review_digest"] = manifest_digest(value, "review_digest")
    return validate_review_bundle(value)


def validate_review_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "review_id",
        "title",
        "summary",
        "created_at",
        "surface_alias",
        "region_id",
        "expected_snapshot_digest",
        "instructions",
        "sources",
        "context",
        "stale_source_ids",
        "maximum_uncertainty",
        "operations",
        "gate_receipt",
        "operation_bundle",
        "source_receipts",
        "boundary",
        "review_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("Regie review bundle fields are invalid")
    if value.get("schema_version") != REGIE_REVIEW_SCHEMA:
        raise ValueError("Regie review bundle has an unsupported schema")
    context = compile_regie_context(
        {
            "review_id": value.get("review_id"),
            "title": value.get("title"),
            "summary": value.get("summary"),
            "instructions": value.get("instructions"),
            "sources": value.get("sources"),
            "context": value.get("context"),
            "boundary": {
                "local_private_only": True,
                "no_mutation_authority": True,
                "provider_identifiers_excluded": True,
            },
        }
    )
    gate, declaration = _validate_gate_receipt(value.get("gate_receipt"))
    bundle = validate_live_operation_bundle(value.get("operation_bundle"))
    if value.get("surface_alias") != declaration.surface_alias:
        raise ValueError("Regie review alias mismatch")
    if value.get("region_id") != declaration.region_id:
        raise ValueError("Regie review region mismatch")
    snapshot_digest = _digest(
        value.get("expected_snapshot_digest"), label="expected_snapshot_digest"
    )
    if snapshot_digest != declaration.expected_snapshot_digest:
        raise ValueError("Regie review revision mismatch")
    operations = value.get("operations")
    if not isinstance(operations, list) or len(operations) != len(bundle["operations"]):
        raise ValueError("Regie review operations are invalid")
    expected_operations = []
    for base, presented in zip(bundle["operations"], operations, strict=True):
        expected_presented = {
            **base,
            "semantic_summary": f"Replace reviewed text in {bundle['region_id']}",
            "visual_diff": _diff_segments(base["old_text"], base["new_text"]),
            "default_decision": "defer",
        }
        if presented != expected_presented:
            raise ValueError("Regie review operation presentation mismatch")
        expected_operations.append(expected_presented)
    stale_source_ids = value.get("stale_source_ids")
    expected_stale = sorted(
        source["source_id"] for source in context["sources"] if source["freshness"] != "fresh"
    )
    if stale_source_ids != expected_stale:
        raise ValueError("Regie review stale source projection mismatch")
    maximum_uncertainty = value.get("maximum_uncertainty")
    expected_uncertainty = max(source["uncertainty"] for source in context["sources"])
    if maximum_uncertainty != expected_uncertainty:
        raise ValueError("Regie review uncertainty projection mismatch")
    expected_sources = {
        "context_digest": context["context_digest"],
        "gate_receipt_digest": gate["receipt_digest"],
        "operation_bundle_digest": bundle["bundle_digest"],
    }
    if value.get("source_receipts") != expected_sources:
        raise ValueError("Regie review source receipts are invalid")
    expected_boundary = {
        "local_private_only": True,
        "no_mutation_authority": True,
        "partial_approval_required": True,
        "provider_identifiers_excluded": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("Regie review boundary is invalid")
    created_at = _timestamp(value.get("created_at"), label="created_at")
    normalized = {
        **dict(value),
        "review_id": context["review_id"],
        "title": context["title"],
        "summary": context["summary"],
        "created_at": created_at,
        "surface_alias": declaration.surface_alias,
        "region_id": declaration.region_id,
        "expected_snapshot_digest": snapshot_digest,
        "instructions": context["instructions"],
        "sources": context["sources"],
        "context": context["context"],
        "operations": expected_operations,
        "gate_receipt": gate,
        "operation_bundle": bundle,
        "source_receipts": expected_sources,
        "boundary": expected_boundary,
    }
    declared = _digest(value.get("review_digest"), label="review_digest")
    actual = manifest_digest(normalized, "review_digest")
    if declared != actual:
        raise ValueError("Regie review bundle digest mismatch")
    normalized["review_digest"] = actual
    return normalized


def load_review_bundle(path: Path) -> dict[str, Any]:
    return validate_review_bundle(read_private_json(path, label="Regie review bundle"))


def _selected_bundle(review: Mapping[str, Any], approved_ids: set[str]) -> dict[str, Any]:
    original = validate_live_operation_bundle(review["operation_bundle"])
    selected = [
        operation
        for operation in original["operations"]
        if operation["operation_id"] in approved_ids
    ]
    if not selected:
        raise ValueError("Regie decision must approve at least one operation")
    draft = {
        key: item
        for key, item in original.items()
        if key not in {"bundle_digest", "schema_version", "operations", "bundle_id"}
    }
    draft.update(
        {
            "schema_version": LIVE_OPERATION_DRAFT_SCHEMA,
            "bundle_id": f"regie-{review['review_digest'][:24]}-selected",
            "operations": selected,
        }
    )
    return compile_live_operation_bundle(draft)


def compile_decision_receipt(
    *,
    review_bundle: Mapping[str, Any],
    decisions: Mapping[str, Any],
    approved_by: str,
    approval_reference: str,
    confirmation: str,
    valid_minutes: int,
    decided_at: datetime | None = None,
) -> dict[str, Any]:
    review = validate_review_bundle(review_bundle)
    expected_ids = [operation["operation_id"] for operation in review["operations"]]
    if set(decisions) != set(expected_ids):
        raise ValueError("Regie decisions must cover every operation exactly once")
    normalized_decisions = []
    for operation_id in expected_ids:
        decision = decisions.get(operation_id)
        if decision not in _DECISIONS:
            raise ValueError(f"Regie decision for {operation_id} is invalid")
        normalized_decisions.append({"operation_id": operation_id, "decision": decision})
    approved_ids = {
        item["operation_id"] for item in normalized_decisions if item["decision"] == "approve"
    }
    selected_bundle = _selected_bundle(review, approved_ids)
    if confirmation != "APPROVE_LIVE_APPLY":
        raise ValueError("Regie live approval confirmation is invalid")
    if isinstance(valid_minutes, bool) or not isinstance(valid_minutes, int):
        raise ValueError("Regie authorization duration is invalid")
    if not 1 <= valid_minutes <= 1440:
        raise ValueError("Regie authorization duration is invalid")
    current = (decided_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    authorization = compile_live_authorization(
        gate_receipt=review["gate_receipt"],
        operation_bundle=selected_bundle,
        approved_by=_line(approved_by, label="approved_by"),
        approval_reference=_line(approval_reference, label="approval_reference"),
        confirmation=confirmation,
        approved_at=current,
        expires_at=current + timedelta(minutes=valid_minutes),
        authorization_id=f"regie-{review['review_digest'][:24]}-authorization",
    )
    plan = compile_live_apply_plan(
        gate_receipt=review["gate_receipt"],
        operation_bundle=selected_bundle,
        authorization=authorization,
        now=current,
    )
    value = {
        "schema_version": REGIE_DECISION_SCHEMA,
        "review_id": review["review_id"],
        "review_digest": review["review_digest"],
        "decided_at": current.isoformat().replace("+00:00", "Z"),
        "approved_by": authorization["approved_by"],
        "approval_reference": authorization["approval_reference"],
        "decisions": normalized_decisions,
        "approved_operation_ids": sorted(approved_ids),
        "rejected_operation_ids": sorted(
            item["operation_id"] for item in normalized_decisions if item["decision"] == "reject"
        ),
        "deferred_operation_ids": sorted(
            item["operation_id"] for item in normalized_decisions if item["decision"] == "defer"
        ),
        "selected_bundle": selected_bundle,
        "authorization": authorization,
        "plan": plan,
        "source_receipts": {
            "review_digest": review["review_digest"],
            "selected_bundle_digest": selected_bundle["bundle_digest"],
            "authorization_digest": authorization["authorization_digest"],
            "plan_digest": plan["plan_digest"],
        },
        "boundary": {
            "partial_approval_applied": True,
            "no_provider_mutation": True,
            "explicit_apply_still_required": True,
            "provider_identifiers_excluded": True,
        },
    }
    value["decision_digest"] = manifest_digest(value, "decision_digest")
    return validate_decision_receipt(value)


def validate_decision_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "review_id",
        "review_digest",
        "decided_at",
        "approved_by",
        "approval_reference",
        "decisions",
        "approved_operation_ids",
        "rejected_operation_ids",
        "deferred_operation_ids",
        "selected_bundle",
        "authorization",
        "plan",
        "source_receipts",
        "boundary",
        "decision_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("Regie decision receipt fields are invalid")
    if value.get("schema_version") != REGIE_DECISION_SCHEMA:
        raise ValueError("Regie decision receipt has an unsupported schema")
    review_id = _safe_id(value.get("review_id"), label="review_id")
    review_digest = _digest(value.get("review_digest"), label="review_digest")
    decided_at = _timestamp(value.get("decided_at"), label="decided_at")
    bundle = validate_live_operation_bundle(value.get("selected_bundle"))
    authorization = validate_live_authorization(value.get("authorization"))
    plan = validate_live_apply_plan(value.get("plan"))
    if plan["operations"] != bundle["operations"]:
        raise ValueError("Regie decision plan does not match selected operations")
    expected_plan_authorization = {
        key: authorization[key]
        for key in (
            "authorization_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "approval_reference",
        )
    }
    if plan["authorization"] != expected_plan_authorization:
        raise ValueError("Regie decision plan does not match authorization")
    if plan["source_receipts"]["authorization_digest"] != authorization["authorization_digest"]:
        raise ValueError("Regie decision plan authorization digest mismatch")
    decisions = value.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Regie decision entries are invalid")
    normalized_decisions = []
    identifiers: set[str] = set()
    for index, item in enumerate(decisions):
        if not isinstance(item, Mapping) or set(item) != {"operation_id", "decision"}:
            raise ValueError(f"decisions[{index}] is invalid")
        operation_id = _safe_id(item.get("operation_id"), label=f"decisions[{index}].operation_id")
        if operation_id in identifiers:
            raise ValueError("Regie decision operation ids must be unique")
        identifiers.add(operation_id)
        decision = item.get("decision")
        if decision not in _DECISIONS:
            raise ValueError(f"decisions[{index}].decision is invalid")
        normalized_decisions.append({"operation_id": operation_id, "decision": decision})
    approved = sorted(
        item["operation_id"] for item in normalized_decisions if item["decision"] == "approve"
    )
    rejected = sorted(
        item["operation_id"] for item in normalized_decisions if item["decision"] == "reject"
    )
    deferred = sorted(
        item["operation_id"] for item in normalized_decisions if item["decision"] == "defer"
    )
    if value.get("approved_operation_ids") != approved or not approved:
        raise ValueError("Regie approved operation projection is invalid")
    if value.get("rejected_operation_ids") != rejected:
        raise ValueError("Regie rejected operation projection is invalid")
    if value.get("deferred_operation_ids") != deferred:
        raise ValueError("Regie deferred operation projection is invalid")
    if approved != sorted(operation["operation_id"] for operation in bundle["operations"]):
        raise ValueError("Regie selected bundle does not match approved decisions")
    expected_sources = {
        "review_digest": review_digest,
        "selected_bundle_digest": bundle["bundle_digest"],
        "authorization_digest": authorization["authorization_digest"],
        "plan_digest": plan["plan_digest"],
    }
    if value.get("source_receipts") != expected_sources:
        raise ValueError("Regie decision source receipts are invalid")
    expected_boundary = {
        "partial_approval_applied": True,
        "no_provider_mutation": True,
        "explicit_apply_still_required": True,
        "provider_identifiers_excluded": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("Regie decision boundary is invalid")
    normalized = {
        **dict(value),
        "review_id": review_id,
        "review_digest": review_digest,
        "decided_at": decided_at,
        "approved_by": _line(value.get("approved_by"), label="approved_by"),
        "approval_reference": _line(value.get("approval_reference"), label="approval_reference"),
        "decisions": normalized_decisions,
        "selected_bundle": bundle,
        "authorization": authorization,
        "plan": plan,
        "source_receipts": expected_sources,
        "boundary": expected_boundary,
    }
    declared = _digest(value.get("decision_digest"), label="decision_digest")
    actual = manifest_digest(normalized, "decision_digest")
    if declared != actual:
        raise ValueError("Regie decision receipt digest mismatch")
    normalized["decision_digest"] = actual
    return normalized


def load_decision_receipt(path: Path) -> dict[str, Any]:
    return validate_decision_receipt(read_private_json(path, label="Regie decision receipt"))
