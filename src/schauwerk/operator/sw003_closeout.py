"""SW-003 closeout receipts for isolated write-proof evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schauwerk.operator.core import _load_json_or_yaml, _validate_digest
from schauwerk.operator.receipts import _stable_digest, _without_runtime_fields
from schauwerk.surfaces.miro.board_registry import validate_alias
from schauwerk.surfaces.miro.change_control import validate_marker

SCHEMA_VERSION = "typed-region-sw003-closeout-receipt.v1"
_VERIFICATION_DIGEST_FIELDS = (
    "create_evidence_digest",
    "read_evidence_digest",
    "update_evidence_digest",
    "marker_scope_evidence_digest",
    "idempotency_evidence_digest",
)
_CLEANUP_BOUNDARY_REASON_CODES = frozenset({"miro_remote_cleanup_unavailable"})
_UNSAFE_CLEANUP_BOUNDARY_REASON = "unsafe-boundary-reason-rejected"


_LIVE_GATE_REQUIREMENTS = (
    {
        "key": "live_create_attempted",
        "description": "live create path was attempted in a bounded SW-003 scope",
    },
    {
        "key": "live_create_verified",
        "description": "created object state was verified after the live create step",
    },
    {
        "key": "live_read_after_create_verified",
        "description": "a live read after create observed the expected marked scope",
    },
    {
        "key": "live_update_verified",
        "description": "a live update changed the same marked scope instead of duplicating it",
    },
    {
        "key": "marker_scope_uniqueness_verified",
        "description": "the SW-003 marker is unique inside the declared board/scope",
    },
    {
        "key": "idempotency_verified",
        "description": "repeating the same marker/scope operation is idempotent",
    },
    {
        "key": "cleanup_verified_or_boundary_accepted",
        "description": "cleanup was verified or a live cleanup boundary was explicitly accepted",
    },
    {
        "key": "provider_identifiers_sanitized",
        "description": "public evidence exposes no board URLs or provider object identifiers",
    },
    {
        "key": "board_scope_allowlisted",
        "description": "the live board/scope is represented by an allowlisted local alias",
    },
)
_LIVE_GATE_DIGEST_FIELDS = (
    "live_create_evidence_digest",
    "live_read_after_create_evidence_digest",
    "live_update_evidence_digest",
    "marker_scope_evidence_digest",
    "idempotency_evidence_digest",
    "cleanup_evidence_digest",
    "board_scope_evidence_digest",
)
_LIVE_GATE_BOOLEAN_FIELDS = (
    "live_create_attempted",
    "live_create_verified",
    "live_read_after_create_verified",
    "live_update_verified",
    "marker_scope_uniqueness_verified",
    "idempotency_verified",
    "provider_identifiers_sanitized",
)
_LIVE_CLEANUP_BOUNDARY_REASON_CODES = frozenset({"live_cleanup_boundary_accepted"})
_PROVIDER_IDENTIFIER_MARKERS = (
    "https://miro.com/app/board/",
    "http://miro.com/app/board/",
    "miro.com/app/board/",
    "/app/board/",
)
_UNSAFE_LIVE_GATE_REASON = "unsafe-live-gate-reason-rejected"


def required_sw003_live_gate_evidence() -> list[dict[str, str]]:
    """Return the public evidence checklist required for a future SW-003 live gate."""
    return [dict(item) for item in _LIVE_GATE_REQUIREMENTS]


def _contains_provider_identifier(value: object) -> bool:
    if isinstance(value, str):
        lower_value = value.lower()
        return any(marker in lower_value for marker in _PROVIDER_IDENTIFIER_MARKERS)
    if isinstance(value, dict):
        return any(_contains_provider_identifier(item) for item in value.values())
    if isinstance(value, list | tuple | set):
        return any(_contains_provider_identifier(item) for item in value)
    return False


def _normalized_live_gate_scope(
    value: object, blocked_reasons: list[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        blocked_reasons.append("board_scope_evidence_missing")
        return {"surface_alias": None, "allowlisted": False}

    alias = value.get("surface_alias")
    if not isinstance(alias, str):
        blocked_reasons.append("board_scope_surface_alias_missing")
        safe_alias = None
    else:
        try:
            safe_alias = validate_alias(alias)
        except ValueError:
            blocked_reasons.append("board_scope_surface_alias_invalid")
            safe_alias = None

    allowlisted = value.get("allowlisted") is True
    if not allowlisted:
        blocked_reasons.append("board_scope_not_allowlisted")
    return {"surface_alias": safe_alias, "allowlisted": allowlisted}


def evaluate_sw003_live_gate_claim(evidence: object) -> dict[str, Any]:
    """Evaluate whether a future SW-003 live-closeout claim is evidence-complete.

    The evaluator is deliberately local and provider-neutral. It never talks to Miro,
    never mutates provider state, and never echoes board URLs or provider object IDs.
    """
    requirements = required_sw003_live_gate_evidence()
    if evidence is None:
        return {
            "claim_present": False,
            "claim_valid": False,
            "closes_live_sw003_gate": False,
            "blocked_reasons": ["live_gate_claim_missing"],
            "requirements": requirements,
            "normalized": {},
        }
    if not isinstance(evidence, dict):
        return {
            "claim_present": True,
            "claim_valid": False,
            "closes_live_sw003_gate": False,
            "blocked_reasons": ["live_gate_claim_not_object"],
            "requirements": requirements,
            "normalized": {},
        }

    blocked_reasons: list[str] = []
    if _contains_provider_identifier(evidence):
        blocked_reasons.append("provider_identifier_present_in_live_gate_claim")

    claim_requested = evidence.get("claim_closes_live_sw003_gate") is True
    if not claim_requested:
        blocked_reasons.append("live_gate_claim_not_requested")

    normalized_flags = {}
    for key in _LIVE_GATE_BOOLEAN_FIELDS:
        verified = evidence.get(key) is True
        normalized_flags[key] = verified
        if not verified:
            blocked_reasons.append(f"evidence_{key}_missing_or_false")

    evidence_digests = {
        key: _evidence_digest(evidence, key, blocked_reasons)
        for key in _LIVE_GATE_DIGEST_FIELDS
    }
    board_scope = _normalized_live_gate_scope(evidence.get("board_scope"), blocked_reasons)

    cleanup_verified = evidence.get("cleanup_verified") is True
    cleanup_boundary_accepted = evidence.get("cleanup_boundary_accepted") is True
    raw_boundary_reason = evidence.get("cleanup_boundary_reason")
    boundary_reason = None
    if cleanup_boundary_accepted:
        if not isinstance(raw_boundary_reason, str) or not raw_boundary_reason.strip():
            blocked_reasons.append("cleanup_boundary_reason_missing")
        else:
            candidate = raw_boundary_reason.strip()
            if candidate in _LIVE_CLEANUP_BOUNDARY_REASON_CODES:
                boundary_reason = candidate
            else:
                blocked_reasons.append("cleanup_boundary_reason_unsafe")
                boundary_reason = _UNSAFE_LIVE_GATE_REASON
    if cleanup_verified and evidence.get("cleanup_attempted") is not True:
        blocked_reasons.append("cleanup_attempt_missing")
    if not cleanup_verified and not cleanup_boundary_accepted:
        blocked_reasons.append("cleanup_verified_or_boundary_missing")

    claim_valid = not blocked_reasons
    return {
        "claim_present": True,
        "claim_requested": claim_requested,
        "claim_valid": claim_valid,
        "closes_live_sw003_gate": claim_valid,
        "blocked_reasons": blocked_reasons,
        "requirements": requirements,
        "normalized": {
            "flags": normalized_flags,
            "evidence_digests": evidence_digests,
            "board_scope": board_scope,
            "cleanup": {
                "cleanup_attempted": evidence.get("cleanup_attempted") is True,
                "cleanup_verified": cleanup_verified,
                "cleanup_boundary_accepted": cleanup_boundary_accepted,
                "cleanup_boundary_reason": boundary_reason,
            },
        },
    }



def load_sw003_closeout_evidence(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="SW-003 closeout evidence")
    if not isinstance(raw, dict):
        raise ValueError("SW-003 closeout evidence must contain an object")
    return raw


def load_sw003_closeout_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="SW-003 closeout receipt")
    if not isinstance(raw, dict):
        raise ValueError("SW-003 closeout receipt must contain an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SW-003 closeout receipt has an unsupported schema")
    return raw


def _verified(value: dict[str, Any], key: str, blocked_reasons: list[str]) -> bool:
    verified = value.get(key) is True
    if not verified:
        blocked_reasons.append(f"evidence_{key}_missing_or_false")
    return verified


def _evidence_digest(
    value: dict[str, Any], key: str, blocked_reasons: list[str]
) -> str | None:
    raw = value.get(key)
    if not isinstance(raw, str):
        blocked_reasons.append(f"evidence_{key}_missing")
        return None
    try:
        return _validate_digest(raw, label=f"sw003.{key}")
    except ValueError:
        blocked_reasons.append(f"evidence_{key}_invalid")
        return raw


def _evidence_text(
    value: dict[str, Any], key: str, blocked_reasons: list[str]
) -> str | None:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        blocked_reasons.append(f"evidence_{key}_missing")
        return None
    return raw.strip()


def _normalized_cleanup(cleanup: object, blocked_reasons: list[str]) -> dict[str, Any]:
    if not isinstance(cleanup, dict):
        blocked_reasons.append("cleanup_evidence_missing")
        return {}
    mode = cleanup.get("mode")
    restore_receipt_digest = cleanup.get("restore_receipt_digest")
    digest_fields = (
        {"restore_receipt_digest": restore_receipt_digest}
        if isinstance(restore_receipt_digest, str)
        else {}
    )
    if mode == "restored-snapshot":
        verified = cleanup.get("verified") is True
        if not verified:
            blocked_reasons.append("cleanup_restored_snapshot_unverified")
        return {"mode": mode, "verified": verified, **digest_fields}
    if mode == "explicit-boundary":
        remote_supported = cleanup.get("remote_cleanup_supported") is True
        remote_attempted = cleanup.get("remote_cleanup_attempted") is True
        reason = cleanup.get("boundary_reason")
        if remote_supported:
            blocked_reasons.append("cleanup_boundary_remote_supported_claimed")
        if remote_attempted:
            blocked_reasons.append("cleanup_boundary_remote_attempted")
        if not isinstance(reason, str) or not reason.strip():
            blocked_reasons.append("cleanup_boundary_reason_missing")
            reason_code = ""
        else:
            reason_code = reason.strip()
            if reason_code not in _CLEANUP_BOUNDARY_REASON_CODES:
                blocked_reasons.append("cleanup_boundary_reason_unsafe")
                reason_code = _UNSAFE_CLEANUP_BOUNDARY_REASON
        return {
            "mode": mode,
            "remote_cleanup_supported": remote_supported,
            "remote_cleanup_attempted": remote_attempted,
            "boundary_reason": reason_code,
            **digest_fields,
        }
    blocked_reasons.append("cleanup_mode_unsupported")
    return {"mode": mode, **digest_fields}


def _bound_restore_region(
    restore_receipt: dict[str, Any],
    evidence: dict[str, Any],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    restore_region = restore_receipt.get("region")
    if not isinstance(restore_region, dict):
        blocked_reasons.append("restore_receipt_region_missing")
        restore_region = {}
    restore_region_id = restore_region.get("region_id")
    restore_surface_alias = restore_region.get("surface_alias")
    restore_region_valid = isinstance(restore_region_id, str) and isinstance(
        restore_surface_alias, str
    )
    if not restore_region_valid and "restore_receipt_region_missing" not in blocked_reasons:
        blocked_reasons.append("restore_receipt_region_missing")

    evidence_region = evidence.get("region")
    if not isinstance(evidence_region, dict):
        blocked_reasons.append("evidence_region_missing")
        evidence_region = {}
    evidence_region_id = evidence_region.get("region_id")
    evidence_surface_alias = evidence_region.get("surface_alias")
    evidence_region_valid = isinstance(evidence_region_id, str) and isinstance(
        evidence_surface_alias, str
    )
    if not evidence_region_valid and "evidence_region_missing" not in blocked_reasons:
        blocked_reasons.append("evidence_region_missing")

    if restore_region_valid and evidence_region_valid:
        if evidence_region_id != restore_region_id:
            blocked_reasons.append("evidence_region_id_mismatch")
        if evidence_surface_alias != restore_surface_alias:
            blocked_reasons.append("evidence_surface_alias_mismatch")
    return restore_region


def compile_sw003_closeout_receipt(
    *,
    restore_receipt: dict[str, Any],
    evidence: dict[str, Any],
    marker: str,
    output_path: Path | None = None,
) -> dict[str, Any]:
    safe_marker = validate_marker(marker)
    if not isinstance(restore_receipt, dict):
        raise ValueError("restore receipt must contain an object")
    if not isinstance(evidence, dict):
        raise ValueError("SW-003 closeout evidence must contain an object")

    blocked_reasons: list[str] = []
    restore_digest = _stable_digest(_without_runtime_fields(restore_receipt))
    if restore_receipt.get("schema_version") != "typed-region-restore-receipt.v1":
        blocked_reasons.append("restore_receipt_schema_unsupported")
    restore_ready = (
        restore_receipt.get("ok") is True
        and restore_receipt.get("ready_for_closeout") is True
    )
    if not restore_ready:
        blocked_reasons.append("restore_receipt_not_ready")
    if restore_receipt.get("mutation_attempted") is not False:
        blocked_reasons.append("restore_receipt_mutation_state_invalid")
    if restore_receipt.get("live_restore_attempted") is not False:
        blocked_reasons.append("restore_receipt_live_state_invalid")
    boundary = restore_receipt.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("fixture_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("restore_receipt_boundary_missing")

    if evidence.get("restore_receipt_digest") != restore_digest:
        blocked_reasons.append("evidence_restore_receipt_digest_mismatch")
    region = _bound_restore_region(restore_receipt, evidence, blocked_reasons)

    evidence_marker = evidence.get("marker")
    if not isinstance(evidence_marker, str):
        blocked_reasons.append("evidence_marker_missing")
    elif validate_marker(evidence_marker) != safe_marker:
        blocked_reasons.append("evidence_marker_mismatch")

    verification = evidence.get("verification")
    if not isinstance(verification, dict):
        blocked_reasons.append("verification_evidence_missing")
        verification = {}
    normalized_verification = {
        "create_verified": _verified(verification, "create_verified", blocked_reasons),
        "read_verified": _verified(verification, "read_verified", blocked_reasons),
        "update_verified": _verified(verification, "update_verified", blocked_reasons),
        "marker_scope_verified": _verified(
            verification, "marker_scope_verified", blocked_reasons
        ),
        "idempotency_verified": _verified(
            verification, "idempotency_verified", blocked_reasons
        ),
    }
    normalized_verification.update(
        {
            key: _evidence_digest(verification, key, blocked_reasons)
            for key in _VERIFICATION_DIGEST_FIELDS
        }
    )
    normalized_verification["idempotency_key"] = _evidence_text(
        verification, "idempotency_key", blocked_reasons
    )

    cleanup = _normalized_cleanup(evidence.get("cleanup"), blocked_reasons)
    if cleanup.get("restore_receipt_digest") != restore_digest:
        blocked_reasons.append("cleanup_restore_receipt_digest_mismatch")
    live_gate = evaluate_sw003_live_gate_claim(evidence.get("live_gate_claim"))

    source_receipts = {
        "restore_receipt_digest": restore_digest,
        "closeout_evidence_digest": _stable_digest(evidence),
    }
    ready = not blocked_reasons
    cleanup_complete = cleanup.get("mode") == "restored-snapshot" and cleanup.get(
        "verified"
    ) is True
    cleanup_boundary_accepted = cleanup.get("mode") == "explicit-boundary" and ready
    value = {
        "schema_version": SCHEMA_VERSION,
        "ok": ready,
        "mutation_attempted": False,
        "live_closeout_attempted": False,
        "ready_for_sw003_tracker_update": ready,
        "closes_live_sw003_gate": False,
        "cleanup_complete": cleanup_complete,
        "cleanup_boundary_accepted": cleanup_boundary_accepted,
        "blocked_reasons": blocked_reasons,
        "marker": safe_marker,
        "operation": restore_receipt.get("operation"),
        "region": region,
        "verification": normalized_verification,
        "cleanup": cleanup,
        "live_gate": {
            **live_gate,
            "fixture_only_receipt_closes_live_gate": False,
        },
        "source_receipts": source_receipts,
        "non_claims": [
            "live_miro_write_acceptance",
            "remote_miro_cleanup",
            "issue_8_closure",
            "sw003_live_gate_closure",
        ],
        "boundary": {
            "fixture_only": True,
            "sw003_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
        "receipt_digest": _stable_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "marker": safe_marker,
                "region": region,
                "verification": normalized_verification,
                "cleanup": cleanup,
                "live_gate": live_gate,
                "cleanup_complete": cleanup_complete,
                "cleanup_boundary_accepted": cleanup_boundary_accepted,
                "source_receipts": source_receipts,
            }
        ),
    }
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        value["output_path"] = str(destination)
    else:
        value["output_path"] = None
    return value
