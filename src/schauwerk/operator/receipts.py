"""Typed receipt stages for managed Schauwerk regions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from schauwerk.operator.core import (
    _ALLOWED_FIXTURE_ACTIONS,
    _FIXTURE_OPERATION_KEYS,
    RegionDeclaration,
    _load_json_or_yaml,
    _validate_digest,
    _validate_safe_id,
    parse_region_declaration,
)


def load_region_preflight(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="preflight")
    if not isinstance(raw, dict):
        raise ValueError("preflight receipt must contain an object")
    if raw.get("schema_version") != "typed-region-preflight.v1":
        raise ValueError("preflight receipt has an unsupported schema")
    return raw


def load_region_apply_scaffold(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="apply scaffold")
    if not isinstance(raw, dict):
        raise ValueError("apply scaffold receipt must contain an object")
    if raw.get("schema_version") != "typed-region-apply-scaffold.v1":
        raise ValueError("apply scaffold receipt has an unsupported schema")
    return raw


def load_fixture_operations(path: Path) -> list[dict[str, Any]]:
    raw = _load_json_or_yaml(path, label="fixture operations")
    if isinstance(raw, dict):
        raw = raw.get("fixture_operations")
    if not isinstance(raw, list):
        raise ValueError("fixture operations file must contain a list")
    return raw




def _sw003_live_gate_requirements() -> list[dict[str, str]]:
    from schauwerk.operator.sw003_closeout import required_sw003_live_gate_evidence

    return required_sw003_live_gate_evidence()


def _sw009_live_apply_gate() -> dict[str, Any]:
    return {
        "ready_for_live_apply": False,
        "blocked_reasons": ["dedicated_live_apply_gate_required"],
        "required_evidence": _sw003_live_gate_requirements(),
        "boundary": {
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_sw003_live_gate": True,
        },
    }


_SW009_LIVE_APPLY_ACKNOWLEDGEMENTS = (
    "operator_confirms_allowlisted_scope",
    "operator_confirms_preflight_receipt_digest",
    "operator_confirms_before_snapshot",
    "operator_confirms_review_packet",
    "operator_confirms_restore_strategy",
    "operator_confirms_postflight_plan",
    "operator_confirms_provider_redaction",
)


SW009_LIVE_APPLY_CANDIDATE_SCHEMA_VERSION = (
    "typed-region-sw009-live-apply-candidate.v1"
)
SW009_LIVE_APPLY_CANDIDATE_RECEIPT_SCHEMA_VERSION = (
    "typed-region-sw009-live-apply-candidate-receipt.v1"
)


def _stable_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _without_runtime_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"output_path", "receipt_digest"}
    }


def _fixture_boundary() -> dict[str, bool]:
    return {
        "fixture_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
    }


def _simulation_boundary() -> dict[str, bool]:
    return {
        **_fixture_boundary(),
        "simulation_only": True,
    }


def _sw009_simulation_closeout_boundary() -> dict[str, bool]:
    return {
        **_simulation_boundary(),
        "does_not_close_sw003_live_gate": True,
    }


def _has_simulation_boundary(receipt: dict[str, Any]) -> bool:
    boundary = receipt.get("boundary")
    return (
        isinstance(boundary, dict)
        and boundary.get("fixture_only") is True
        and boundary.get("simulation_only") is True
        and boundary.get("no_miro_mutation") is True
        and boundary.get("no_provider_ids_returned") is True
    )


def _is_sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _receipt_digest(value: dict[str, Any]) -> str:
    return _stable_digest(_without_runtime_fields(value))


def _required_fixture_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fixture operation {key} must be a non-empty string")
    return value.strip()


def _normalized_fixture_operations(
    value: list[dict[str, Any]],
    *,
    region_id: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("fixture_operations must contain at least one operation")

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("fixture operation must be an object")
        unknown_keys = sorted(set(raw) - _FIXTURE_OPERATION_KEYS)
        if unknown_keys:
            raise ValueError(
                f"fixture operation contains unsupported keys: {', '.join(unknown_keys)}"
            )
        operation_id = _validate_safe_id(
            _required_fixture_text(raw, "operation_id"), label="operation_id"
        )
        if operation_id in seen:
            raise ValueError("fixture operation_id values must be unique")
        seen.add(operation_id)
        action = _required_fixture_text(raw, "action")
        if action not in _ALLOWED_FIXTURE_ACTIONS:
            raise ValueError(
                f"fixture operation action must be one of {sorted(_ALLOWED_FIXTURE_ACTIONS)}"
            )
        operation_region_id = _validate_safe_id(
            _required_fixture_text(raw, "region_id"), label="operation.region_id"
        )
        if operation_region_id != region_id:
            raise ValueError("fixture operation targets undeclared region")
        local_ref = _validate_safe_id(
            _required_fixture_text(raw, "local_ref"), label="operation.local_ref"
        )
        payload_digest = _validate_digest(
            _required_fixture_text(raw, "payload_digest"), label="operation.payload_digest"
        )
        normalized.append(
            {
                "operation_id": operation_id,
                "action": action,
                "region_id": operation_region_id,
                "local_ref": local_ref,
                "payload_digest": payload_digest,
            }
        )
    return normalized


def compile_region_apply_receipt(
    *,
    scaffold: dict[str, Any],
    fixture_operations: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(scaffold, dict):
        raise ValueError("apply scaffold must contain an object")

    blocked_reasons: list[str] = []
    if scaffold.get("schema_version") != "typed-region-apply-scaffold.v1":
        blocked_reasons.append("apply_scaffold_schema_unsupported")
    fixture_ready = scaffold.get("ready_for_fixture_apply") is True
    if scaffold.get("ok") is not True or not fixture_ready:
        blocked_reasons.append("apply_scaffold_not_ready")
    if scaffold.get("ready_for_live_apply") is not False:
        blocked_reasons.append("apply_scaffold_live_gate_not_closed")
    if scaffold.get("mutation_attempted") is not False:
        blocked_reasons.append("apply_scaffold_mutation_state_invalid")

    region = scaffold.get("region")
    declaration: RegionDeclaration | None = None
    if not isinstance(region, dict):
        blocked_reasons.append("apply_scaffold_region_missing")
        region = {}
    else:
        try:
            declaration = parse_region_declaration({"region": region})
        except ValueError:
            blocked_reasons.append("apply_scaffold_region_invalid")

    snapshot = scaffold.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("apply_scaffold_snapshot_missing")
        snapshot = {}

    boundary = scaffold.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("scaffold_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("apply_scaffold_boundary_missing")

    scaffold_blocks = scaffold.get("blocked_reasons", [])
    if scaffold_blocks:
        blocked_reasons.extend(
            f"apply_scaffold:{reason}" for reason in scaffold_blocks if isinstance(reason, str)
        )

    if declaration is None:
        raise ValueError("apply scaffold region is required for fixture validation")
    if declaration.mode != "managed":
        blocked_reasons.append("apply_scaffold_region_not_managed")
    snapshot_digest = snapshot.get("content_digest")
    if snapshot_digest != declaration.expected_snapshot_digest:
        blocked_reasons.append("apply_scaffold_snapshot_digest_mismatch")
    normalized_operations = _normalized_fixture_operations(
        fixture_operations, region_id=declaration.region_id
    )
    scaffold_digest = _stable_digest(_without_runtime_fields(scaffold))
    fixture_digest = _stable_digest(normalized_operations)
    receipt_material = {
        "schema_version": "typed-region-apply-receipt.v1",
        "operation": scaffold.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "scaffold_digest": scaffold_digest,
        "fixture_operations_digest": fixture_digest,
    }
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-apply-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_live_apply": False,
        "ready_for_postflight": ready,
        "blocked_reasons": blocked_reasons,
        "operation": scaffold.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "source_receipts": {
            "apply_scaffold_digest": scaffold_digest,
            "fixture_operations_digest": fixture_digest,
        },
        "fixture": {
            "operation_count": len(normalized_operations),
            "operations": normalized_operations,
        },
        "idempotency": {
            "method": "fixture_operations_digest",
            "key": f"{declaration.view_id}:{declaration.region_id}:{fixture_digest}",
        },
        "postflight_required": [
            "capture_after_snapshot",
            "verify_region_marker_scope",
            "verify_fixture_operation_digest",
            "verify_idempotency_receipt",
            "write_quality_receipt",
        ],
        "restore_required": True,
        "restore_strategy": scaffold.get("restore_strategy", "use_preflight_snapshot_path"),
        "boundary": {
            "fixture_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
        "receipt_digest": _stable_digest(receipt_material),
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


def compile_region_apply_scaffold(
    *,
    preflight: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    preflight_ok = preflight.get("ok") is True
    ready_for_apply = preflight.get("ready_for_apply") is True
    if not preflight_ok or not ready_for_apply:
        blocked_reasons.append("preflight_not_ready")
    if preflight.get("mutation_attempted") is not False:
        blocked_reasons.append("preflight_mutation_state_invalid")
    region = preflight.get("region")
    if not isinstance(region, dict):
        blocked_reasons.append("preflight_region_missing")
        region = {}
    snapshot = preflight.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("preflight_snapshot_missing")
        snapshot = {}
    boundary = preflight.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("no_miro_mutation") is not True:
        blocked_reasons.append("preflight_boundary_missing")
    preflight_blocks = preflight.get("blocked_reasons", [])
    if preflight_blocks:
        blocked_reasons.extend(
            f"preflight:{reason}" for reason in preflight_blocks if isinstance(reason, str)
        )

    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-apply-scaffold.v1",
        "ok": ready,
        "mutation_attempted": False,
        "ready_for_fixture_apply": ready,
        "ready_for_live_apply": False,
        "live_apply_gate": _sw009_live_apply_gate(),
        "blocked_reasons": blocked_reasons,
        "operation": preflight.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "required_live_preconditions": [
            "sw003_live_gate_evidence_complete",
            "miro_doctor_safe_for_live_board_operations",
            "operator_confirms_preflight_receipt_digest",
            "operator_confirms_expected_source_digest",
            "operator_confirms_restore_strategy",
        ],
        "required_apply_steps": [
            "compile_candidate_dsl",
            "confirm_region_marker_scope",
            "apply_typed_operations",
            "capture_after_snapshot",
            "verify_region_marker_scope",
            "verify_idempotency_receipt",
            "write_quality_receipt",
        ],
        "restore_required": True,
        "restore_strategy": "use_preflight_snapshot_path",
        "boundary": {
            "scaffold_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
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


def _snapshot_mapping_receipt(raw: dict[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} snapshot must contain an object")
    digest = raw.get("content_digest")
    if not isinstance(digest, str):
        raise ValueError(f"{label} snapshot lacks content_digest")
    _validate_digest(digest, label=f"{label}.content_digest")
    board_alias = raw.get("board_alias")
    if not isinstance(board_alias, str):
        raise ValueError(f"{label} snapshot lacks board_alias")
    return {
        "board_alias": _validate_safe_id(board_alias, label=f"{label}.board_alias"),
        "content_digest": digest,
        "item_count": raw.get("item_count"),
        "repeatability_verified": raw.get("repeatability_verified"),
        "sanitized_references": raw.get("sanitized_references"),
    }


def load_region_apply_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="apply receipt")
    if not isinstance(raw, dict):
        raise ValueError("apply receipt must contain an object")
    if raw.get("schema_version") != "typed-region-apply-receipt.v1":
        raise ValueError("apply receipt has an unsupported schema")
    return raw


def load_region_postflight_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="postflight receipt")
    if not isinstance(raw, dict):
        raise ValueError("postflight receipt must contain an object")
    if raw.get("schema_version") != "typed-region-postflight-receipt.v1":
        raise ValueError("postflight receipt has an unsupported schema")
    return raw


def load_region_restore_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="restore receipt")
    if not isinstance(raw, dict):
        raise ValueError("restore receipt must contain an object")
    if raw.get("schema_version") != "typed-region-restore-receipt.v1":
        raise ValueError("restore receipt has an unsupported schema")
    return raw


def load_snapshot_mapping_receipt(path: Path, *, label: str = "snapshot") -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label=label)
    if not isinstance(raw, dict):
        raise ValueError(f"{label} snapshot must contain an object")
    return raw


def compile_region_postflight_receipt(
    *,
    apply_receipt: dict[str, Any],
    after_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(apply_receipt, dict):
        raise ValueError("apply receipt must contain an object")

    blocked_reasons: list[str] = []
    if apply_receipt.get("schema_version") != "typed-region-apply-receipt.v1":
        blocked_reasons.append("apply_receipt_schema_unsupported")
    apply_ready = (
        apply_receipt.get("ok") is True
        and apply_receipt.get("ready_for_postflight") is True
    )
    if not apply_ready:
        blocked_reasons.append("apply_receipt_not_ready")
    if apply_receipt.get("mutation_attempted") is not False:
        blocked_reasons.append("apply_receipt_mutation_state_invalid")
    if apply_receipt.get("live_apply_attempted") is not False:
        blocked_reasons.append("apply_receipt_live_state_invalid")

    region = apply_receipt.get("region")
    if not isinstance(region, dict):
        blocked_reasons.append("apply_receipt_region_missing")
        region = {}
    snapshot = apply_receipt.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("apply_receipt_snapshot_missing")
        snapshot = {}
    boundary = apply_receipt.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("fixture_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("apply_receipt_boundary_missing")

    normalized_after = _snapshot_mapping_receipt(after_snapshot, label="after")
    expected_alias = region.get("surface_alias")
    if normalized_after["board_alias"] != expected_alias:
        blocked_reasons.append("after_snapshot_board_alias_mismatch")
    if normalized_after.get("repeatability_verified") is not True:
        blocked_reasons.append("after_snapshot_repeatability_unverified")
    if normalized_after.get("sanitized_references") is not True:
        blocked_reasons.append("after_snapshot_references_not_sanitized")

    apply_source_receipts = apply_receipt.get("source_receipts")
    if not isinstance(apply_source_receipts, dict):
        blocked_reasons.append("apply_receipt_source_receipts_missing")
        apply_source_receipts = {}
    expected_fixture_digest = apply_source_receipts.get("fixture_operations_digest")
    observed_fixture_digest = after_snapshot.get("fixture_operations_digest")
    if not isinstance(observed_fixture_digest, str):
        blocked_reasons.append("after_snapshot_fixture_digest_missing")
    elif observed_fixture_digest != expected_fixture_digest:
        blocked_reasons.append("after_snapshot_fixture_digest_mismatch")

    idempotency = apply_receipt.get("idempotency")
    if not isinstance(idempotency, dict):
        blocked_reasons.append("apply_receipt_idempotency_missing")
        idempotency = {}
    expected_idempotency_key = idempotency.get("key")
    observed_idempotency_key = after_snapshot.get("idempotency_key")
    if not isinstance(observed_idempotency_key, str):
        blocked_reasons.append("after_snapshot_idempotency_key_missing")
    elif observed_idempotency_key != expected_idempotency_key:
        blocked_reasons.append("after_snapshot_idempotency_key_mismatch")
    idempotency_verified = after_snapshot.get("idempotency_verified") is True
    if not idempotency_verified:
        blocked_reasons.append("after_snapshot_idempotency_unverified")

    verification = {
        "fixture_operations_digest": observed_fixture_digest,
        "idempotency_key": observed_idempotency_key,
        "idempotency_verified": idempotency_verified,
    }
    source_receipts = {
        "apply_receipt_digest": _stable_digest(_without_runtime_fields(apply_receipt)),
        "after_snapshot_digest": _stable_digest(normalized_after),
    }
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-postflight-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_postflight_attempted": False,
        "ready_for_restore": ready,
        "blocked_reasons": blocked_reasons,
        "operation": apply_receipt.get("operation"),
        "region": region,
        "pre_apply_snapshot": snapshot,
        "after_snapshot": normalized_after,
        "verification": verification,
        "source_receipts": source_receipts,
        "fixture": apply_receipt.get("fixture", {}),
        "idempotency": apply_receipt.get("idempotency", {}),
        "restore_required": True,
        "restore_strategy": apply_receipt.get("restore_strategy", "use_preflight_snapshot_path"),
        "boundary": _fixture_boundary(),
        "receipt_digest": _stable_digest(
            {
                "schema_version": "typed-region-postflight-receipt.v1",
                "operation": apply_receipt.get("operation"),
                "region": region,
                "pre_apply_snapshot": snapshot,
                "after_snapshot": normalized_after,
                "verification": verification,
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


def compile_region_simulation_postflight_receipt(
    *,
    apply_simulation_receipt: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(apply_simulation_receipt, dict):
        raise ValueError("apply simulation receipt must contain an object")

    blocked_reasons: list[str] = []
    if (
        apply_simulation_receipt.get("schema_version")
        != "typed-region-apply-simulation-receipt.v1"
    ):
        blocked_reasons.append("apply_simulation_receipt_schema_unsupported")
    simulation_ready = (
        apply_simulation_receipt.get("ok") is True
        and apply_simulation_receipt.get("ready_for_postflight") is True
    )
    if not simulation_ready:
        blocked_reasons.append("apply_simulation_receipt_not_ready")
    if apply_simulation_receipt.get("mutation_attempted") is not False:
        blocked_reasons.append("apply_simulation_receipt_mutation_state_invalid")
    if apply_simulation_receipt.get("live_apply_attempted") is not False:
        blocked_reasons.append("apply_simulation_receipt_live_state_invalid")

    boundary = apply_simulation_receipt.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("fixture_only") is not True
        or boundary.get("simulation_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("apply_simulation_receipt_boundary_missing")

    region = apply_simulation_receipt.get("region")
    if not isinstance(region, dict):
        blocked_reasons.append("apply_simulation_receipt_region_missing")
        region = {}
    pre_apply_snapshot = apply_simulation_receipt.get("pre_apply_snapshot")
    if not isinstance(pre_apply_snapshot, dict):
        blocked_reasons.append("apply_simulation_receipt_pre_snapshot_missing")
        pre_apply_snapshot = {}
    after_snapshot = apply_simulation_receipt.get("after_snapshot")
    if not isinstance(after_snapshot, dict):
        blocked_reasons.append("apply_simulation_receipt_after_snapshot_missing")
        after_snapshot = {}

    verification = apply_simulation_receipt.get("verification")
    if not isinstance(verification, dict):
        blocked_reasons.append("apply_simulation_receipt_verification_missing")
        verification = {}
    if verification.get("idempotency_verified") is not True:
        blocked_reasons.append("apply_simulation_receipt_idempotency_unverified")

    source_receipts = {
        "apply_simulation_receipt_digest": _stable_digest(
            _without_runtime_fields(apply_simulation_receipt)
        ),
    }
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-postflight-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_postflight_attempted": False,
        "ready_for_restore": ready,
        "blocked_reasons": blocked_reasons,
        "operation": apply_simulation_receipt.get("operation"),
        "region": region,
        "pre_apply_snapshot": pre_apply_snapshot,
        "after_snapshot": after_snapshot,
        "verification": verification,
        "source_receipts": source_receipts,
        "fixture": {
            "operation_count": apply_simulation_receipt.get("operation_count"),
            "operations": apply_simulation_receipt.get("operations", []),
        },
        "idempotency": apply_simulation_receipt.get("idempotency", {}),
        "restore_required": True,
        "restore_strategy": apply_simulation_receipt.get(
            "restore_strategy", "use_preflight_snapshot_path"
        ),
        "boundary": _simulation_boundary(),
        "receipt_digest": _stable_digest(
            {
                "schema_version": "typed-region-postflight-receipt.v1",
                "source_kind": "typed-region-apply-simulation-receipt.v1",
                "operation": apply_simulation_receipt.get("operation"),
                "region": region,
                "pre_apply_snapshot": pre_apply_snapshot,
                "after_snapshot": after_snapshot,
                "verification": verification,
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


def compile_region_restore_receipt(
    *,
    postflight_receipt: dict[str, Any],
    restored_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(postflight_receipt, dict):
        raise ValueError("postflight receipt must contain an object")

    blocked_reasons: list[str] = []
    if postflight_receipt.get("schema_version") != "typed-region-postflight-receipt.v1":
        blocked_reasons.append("postflight_receipt_schema_unsupported")
    postflight_ready = (
        postflight_receipt.get("ok") is True
        and postflight_receipt.get("ready_for_restore") is True
    )
    if not postflight_ready:
        blocked_reasons.append("postflight_receipt_not_ready")
    if postflight_receipt.get("mutation_attempted") is not False:
        blocked_reasons.append("postflight_receipt_mutation_state_invalid")
    if postflight_receipt.get("live_postflight_attempted") is not False:
        blocked_reasons.append("postflight_receipt_live_state_invalid")
    boundary = postflight_receipt.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("fixture_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("postflight_receipt_boundary_missing")

    pre_apply_snapshot = postflight_receipt.get("pre_apply_snapshot")
    if not isinstance(pre_apply_snapshot, dict):
        blocked_reasons.append("postflight_pre_apply_snapshot_missing")
        pre_apply_snapshot = {}
    normalized_restored = _snapshot_mapping_receipt(restored_snapshot, label="restored")
    if normalized_restored.get("content_digest") != pre_apply_snapshot.get("content_digest"):
        blocked_reasons.append("restored_snapshot_digest_mismatch")
    if normalized_restored.get("board_alias") != pre_apply_snapshot.get("board_alias"):
        blocked_reasons.append("restored_snapshot_board_alias_mismatch")
    if normalized_restored.get("repeatability_verified") is not True:
        blocked_reasons.append("restored_snapshot_repeatability_unverified")
    if normalized_restored.get("sanitized_references") is not True:
        blocked_reasons.append("restored_snapshot_references_not_sanitized")

    source_receipts = {
        "postflight_receipt_digest": _receipt_digest(postflight_receipt),
        "restored_snapshot_digest": _stable_digest(normalized_restored),
    }
    postflight_source_receipts = postflight_receipt.get("source_receipts")
    if (
        isinstance(postflight_source_receipts, dict)
        and _has_simulation_boundary(postflight_receipt)
        and _is_sha256_digest(
            postflight_source_receipts.get("apply_simulation_receipt_digest")
        )
    ):
        source_receipts["apply_simulation_receipt_digest"] = (
            postflight_source_receipts["apply_simulation_receipt_digest"]
        )
    output_boundary = (
        _simulation_boundary()
        if _has_simulation_boundary(postflight_receipt)
        else _fixture_boundary()
    )
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-restore-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_restore_attempted": False,
        "ready_for_closeout": ready,
        "blocked_reasons": blocked_reasons,
        "operation": postflight_receipt.get("operation"),
        "region": postflight_receipt.get("region", {}),
        "pre_apply_snapshot": pre_apply_snapshot,
        "restored_snapshot": normalized_restored,
        "source_receipts": source_receipts,
        "boundary": output_boundary,
    }
    value["receipt_digest"] = _receipt_digest(value)
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


def _sw009_acknowledgement_template(*, accepted: bool) -> dict[str, bool]:
    return {key: accepted for key in _SW009_LIVE_APPLY_ACKNOWLEDGEMENTS}


def compile_region_sw009_live_apply_candidate_template(
    *, output_path: Path | None = None
) -> dict[str, Any]:
    template = {
        "schema_version": SW009_LIVE_APPLY_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": "sw009-live-apply-candidate-YYYYMMDD",
        "scaffold_path": "apply-scaffold.json",
        "sw003_evidence_packet_path": (
            "docs/operators/evidence/sw003-live-proof-20260709/"
            "live-gate-evidence-packet.json"
        ),
        "acknowledgements": _sw009_acknowledgement_template(accepted=False),
        "operator_notes": [
            "Use allowlisted board alias only; never include board URLs or provider IDs.",
            "Capture before snapshot before any live apply attempt.",
            "Prepare postflight and restore evidence before mutation.",
        ],
        "boundary": {
            "local_candidate_manifest_only": True,
            "does_not_execute_live_apply": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_separate_human_operator_apply": True,
        },
    }
    template["candidate_digest"] = _stable_digest(template)
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        template["output_path"] = str(destination)
        destination.write_text(
            json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        template["output_path"] = None
    return template


def load_region_sw009_live_apply_candidate(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="SW-009 live apply candidate")
    if not isinstance(raw, dict):
        raise ValueError("SW-009 live apply candidate must contain an object")
    if raw.get("schema_version") != SW009_LIVE_APPLY_CANDIDATE_SCHEMA_VERSION:
        raise ValueError("SW-009 live apply candidate has an unsupported schema")
    return raw


def _candidate_manifest_digest(candidate: dict[str, Any]) -> str:
    return _stable_digest(
        {
            key: value
            for key, value in candidate.items()
            if key not in {"candidate_digest", "output_path"}
        }
    )


def _candidate_contains_provider_reference(value: object) -> bool:
    if isinstance(value, dict):
        return any(_candidate_contains_provider_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_candidate_contains_provider_reference(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return (
            "miro.com/app/board/" in lowered
            or "https://miro.com" in lowered
            or "http://miro.com" in lowered
        )
    return False


def _candidate_path(candidate_path: Path, value: Any, *, label: str) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if "miro.com" in raw or "https://" in raw or "http://" in raw:
        raise ValueError(f"{label} must be a local path, not a provider URL")
    path = Path(raw)
    if not path.is_absolute():
        path = candidate_path.expanduser().absolute().parent / path
    resolved = path.expanduser().absolute()
    if resolved.is_symlink() or any(parent.is_symlink() for parent in resolved.parents):
        raise ValueError(f"{label} path is unsafe")
    return resolved


def compile_region_sw009_live_apply_candidate_receipt(
    *, candidate: dict[str, Any], candidate_path: Path, output_path: Path | None = None
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("SW-009 live apply candidate must contain an object")
    blocked_reasons: list[str] = []
    if candidate.get("schema_version") != SW009_LIVE_APPLY_CANDIDATE_SCHEMA_VERSION:
        blocked_reasons.append("candidate_schema_unsupported")

    candidate_id = candidate.get("candidate_id")
    if isinstance(candidate_id, str) and candidate_id.strip():
        try:
            candidate_id = _validate_safe_id(candidate_id.strip(), label="candidate_id")
        except ValueError:
            blocked_reasons.append("candidate_id_invalid")
            candidate_id = None
    else:
        blocked_reasons.append("candidate_id_missing")
        candidate_id = None

    declared_digest = candidate.get("candidate_digest")
    actual_digest = _candidate_manifest_digest(candidate)
    if declared_digest is None:
        blocked_reasons.append("candidate_digest_missing")
    elif not _is_sha256_digest(declared_digest):
        blocked_reasons.append("candidate_digest_invalid")
    elif declared_digest != actual_digest:
        blocked_reasons.append("candidate_digest_mismatch")

    if _candidate_contains_provider_reference(candidate):
        blocked_reasons.append("candidate_provider_reference_present")

    boundary = candidate.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("local_candidate_manifest_only") is not True
        or boundary.get("does_not_execute_live_apply") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
        or boundary.get("requires_separate_human_operator_apply") is not True
    ):
        blocked_reasons.append("candidate_boundary_invalid")

    try:
        scaffold_path = _candidate_path(
            candidate_path, candidate.get("scaffold_path"), label="scaffold_path"
        )
        evidence_packet_path = _candidate_path(
            candidate_path,
            candidate.get("sw003_evidence_packet_path"),
            label="sw003_evidence_packet_path",
        )
    except ValueError as exc:
        blocked_reasons.append(str(exc).replace(" ", "_"))
        scaffold_path = None
        evidence_packet_path = None

    if scaffold_path is None:
        blocked_reasons.append("candidate_scaffold_path_missing")
    if evidence_packet_path is None:
        blocked_reasons.append("candidate_sw003_evidence_packet_path_missing")

    acknowledgements = candidate.get("acknowledgements")
    if not isinstance(acknowledgements, dict):
        acknowledgements = {}
        blocked_reasons.append("candidate_acknowledgements_missing")

    scaffold: dict[str, Any] | None = None
    sw003_evidence_packet: dict[str, Any] | None = None
    if scaffold_path is not None:
        try:
            scaffold = load_region_apply_scaffold(scaffold_path)
        except ValueError as exc:
            blocked_reasons.append(f"candidate_scaffold_invalid:{exc}")
    if evidence_packet_path is not None:
        try:
            from schauwerk.operator.sw003_closeout import (
                load_sw003_live_gate_evidence_packet,
            )

            sw003_evidence_packet = load_sw003_live_gate_evidence_packet(evidence_packet_path)
        except ValueError as exc:
            blocked_reasons.append(f"candidate_sw003_evidence_packet_invalid:{exc}")

    if scaffold is not None and sw003_evidence_packet is not None:
        gate_receipt = compile_region_sw009_live_apply_gate_receipt(
            scaffold=scaffold,
            sw003_evidence_packet=sw003_evidence_packet,
            acknowledgements=acknowledgements,
        )
        blocked_reasons.extend(
            f"gate:{reason}"
            for reason in gate_receipt.get("blocked_reasons", [])
            if isinstance(reason, str)
        )
    else:
        gate_receipt = None

    ready = not blocked_reasons
    value = {
        "schema_version": SW009_LIVE_APPLY_CANDIDATE_RECEIPT_SCHEMA_VERSION,
        "ok": ready,
        "candidate_id": candidate_id,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_live_apply": ready,
        "blocked_reasons": blocked_reasons,
        "candidate_digest": actual_digest,
        "declared_candidate_digest": declared_digest,
        "paths": {
            "candidate_path": str(candidate_path.expanduser().absolute()),
            "scaffold_path": str(scaffold_path) if scaffold_path is not None else None,
            "sw003_evidence_packet_path": (
                str(evidence_packet_path) if evidence_packet_path is not None else None
            ),
        },
        "acknowledgements": _validate_sw009_live_acknowledgements(
            acknowledgements, []
        ),
        "gate_receipt": gate_receipt,
        "live_apply_gate": {
            "ready_for_live_apply": ready,
            "blocked_reasons": blocked_reasons,
            "requires_separate_human_operator_apply": True,
        },
        "boundary": {
            "local_candidate_check_only": True,
            "does_not_execute_live_apply": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_separate_human_operator_apply": True,
        },
    }
    value["receipt_digest"] = _receipt_digest(value)
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        value["output_path"] = str(destination)
        destination.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        value["output_path"] = None
    return value


def load_region_sw009_live_apply_gate_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="SW-009 live apply gate")
    if not isinstance(raw, dict):
        raise ValueError("SW-009 live apply gate receipt must contain an object")
    if raw.get("schema_version") != "typed-region-sw009-live-apply-gate-receipt.v1":
        raise ValueError("SW-009 live apply gate receipt has an unsupported schema")
    return raw


def _validate_sw003_live_gate_evidence_packet_for_sw009(
    packet: dict[str, Any], blocked_reasons: list[str]
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        blocked_reasons.append("sw003_live_gate_evidence_packet_missing")
        return {}
    if packet.get("schema_version") != "typed-region-sw003-live-gate-evidence-packet.v1":
        blocked_reasons.append("sw003_live_gate_evidence_packet_schema_unsupported")
    if packet.get("ok") is not True:
        blocked_reasons.append("sw003_live_gate_evidence_packet_not_ok")
    if packet.get("ready_for_live_acceptance_review") is not True:
        blocked_reasons.append("sw003_live_gate_evidence_packet_not_review_ready")
    if packet.get("ready_for_live_apply") is not False:
        blocked_reasons.append("sw003_live_gate_evidence_packet_must_not_enable_apply")
    if packet.get("mutation_attempted") is not False:
        blocked_reasons.append("sw003_live_gate_evidence_packet_mutation_state_invalid")
    if packet.get("live_miro_access_attempted") is not False:
        blocked_reasons.append("sw003_live_gate_evidence_packet_live_state_invalid")
    if packet.get("closes_live_sw003_gate") is not False:
        blocked_reasons.append("sw003_live_gate_evidence_packet_must_not_close_gate")
    if packet.get("creates_live_acceptance") is not False:
        blocked_reasons.append("sw003_live_gate_evidence_packet_must_not_create_acceptance")

    live_apply_gate = packet.get("live_apply_gate")
    if (
        not isinstance(live_apply_gate, dict)
        or live_apply_gate.get("ready_for_live_apply") is not False
        or live_apply_gate.get("blocked_reasons")
        != ["sw003_live_gate_evidence_packet_only"]
    ):
        blocked_reasons.append("sw003_live_gate_evidence_packet_live_apply_gate_invalid")

    boundary = packet.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("local_evidence_packet_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
        or boundary.get("does_not_close_issue_8") is not True
    ):
        blocked_reasons.append("sw003_live_gate_evidence_packet_boundary_invalid")

    source_receipts = packet.get("source_receipts")
    if not isinstance(source_receipts, dict):
        blocked_reasons.append("sw003_live_gate_evidence_packet_source_receipts_missing")
        source_receipts = {}
    for key in (
        "evidence_input_digest",
        "live_gate_evaluation_digest",
        "live_gate_status_digest",
        "live_gate_review_packet_digest",
        "requirements_digest",
    ):
        if not _is_sha256_digest(source_receipts.get(key)):
            blocked_reasons.append(f"sw003_live_gate_evidence_packet_{key}_invalid")
    evidence_packet_digest = packet.get("evidence_packet_digest")
    if not _is_sha256_digest(evidence_packet_digest):
        blocked_reasons.append("sw003_live_gate_evidence_packet_digest_invalid")
    else:
        digest_input = {
            key: value
            for key, value in packet.items()
            if key not in {"evidence_packet_digest", "output_path"}
        }
        if evidence_packet_digest != _stable_digest(digest_input):
            blocked_reasons.append("sw003_live_gate_evidence_packet_digest_mismatch")
    return source_receipts


def _validate_sw009_live_acknowledgements(
    acknowledgements: dict[str, bool], blocked_reasons: list[str]
) -> dict[str, bool]:
    if not isinstance(acknowledgements, dict):
        acknowledgements = {}
    normalized = {
        key: acknowledgements.get(key) is True
        for key in _SW009_LIVE_APPLY_ACKNOWLEDGEMENTS
    }
    for key, accepted in normalized.items():
        if not accepted:
            blocked_reasons.append(f"acknowledgement_missing:{key}")
    return normalized


def compile_region_sw009_live_apply_gate_receipt(
    *,
    scaffold: dict[str, Any],
    sw003_evidence_packet: dict[str, Any],
    acknowledgements: dict[str, bool],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(scaffold, dict):
        raise ValueError("apply scaffold must contain an object")

    blocked_reasons: list[str] = []
    if scaffold.get("schema_version") != "typed-region-apply-scaffold.v1":
        blocked_reasons.append("apply_scaffold_schema_unsupported")
    fixture_ready = scaffold.get("ready_for_fixture_apply") is True
    if scaffold.get("ok") is not True or not fixture_ready:
        blocked_reasons.append("apply_scaffold_not_ready")
    if scaffold.get("mutation_attempted") is not False:
        blocked_reasons.append("apply_scaffold_mutation_state_invalid")
    if scaffold.get("ready_for_live_apply") is not False:
        blocked_reasons.append("apply_scaffold_live_gate_state_invalid")

    region = scaffold.get("region")
    declaration: RegionDeclaration | None = None
    if not isinstance(region, dict):
        blocked_reasons.append("apply_scaffold_region_missing")
        region = {}
    else:
        try:
            declaration = parse_region_declaration({"region": region})
        except ValueError:
            blocked_reasons.append("apply_scaffold_region_invalid")

    snapshot = scaffold.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("apply_scaffold_snapshot_missing")
        snapshot = {}

    boundary = scaffold.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("scaffold_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("apply_scaffold_boundary_missing")

    scaffold_blocks = scaffold.get("blocked_reasons", [])
    if scaffold_blocks:
        blocked_reasons.extend(
            f"apply_scaffold:{reason}" for reason in scaffold_blocks if isinstance(reason, str)
        )

    if declaration is None:
        raise ValueError("apply scaffold region is required for SW-009 live apply gate")
    if declaration.mode != "managed":
        blocked_reasons.append("apply_scaffold_region_not_managed")
    snapshot_digest = snapshot.get("content_digest")
    if snapshot_digest != declaration.expected_snapshot_digest:
        blocked_reasons.append("apply_scaffold_snapshot_digest_mismatch")
    if snapshot.get("board_alias") != declaration.surface_alias:
        blocked_reasons.append("apply_scaffold_snapshot_alias_mismatch")
    if snapshot.get("repeatability_verified") is not True:
        blocked_reasons.append("apply_scaffold_snapshot_repeatability_missing")
    if snapshot.get("sanitized_references") is not True:
        blocked_reasons.append("apply_scaffold_snapshot_not_sanitized")

    sw003_source_receipts = _validate_sw003_live_gate_evidence_packet_for_sw009(
        sw003_evidence_packet, blocked_reasons
    )
    normalized_acknowledgements = _validate_sw009_live_acknowledgements(
        acknowledgements, blocked_reasons
    )

    ready = not blocked_reasons
    scaffold_digest = _stable_digest(_without_runtime_fields(scaffold))
    sw003_packet_digest = (
        sw003_evidence_packet.get("evidence_packet_digest")
        if isinstance(sw003_evidence_packet, dict)
        else None
    )
    source_receipts = {
        "apply_scaffold_digest": scaffold_digest,
        "sw003_live_gate_evidence_packet_digest": sw003_packet_digest,
        "sw003_live_gate_evidence_input_digest": sw003_source_receipts.get(
            "evidence_input_digest"
        ),
        "sw003_live_gate_review_packet_digest": sw003_source_receipts.get(
            "live_gate_review_packet_digest"
        ),
    }
    value = {
        "schema_version": "typed-region-sw009-live-apply-gate-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_live_apply": ready,
        "blocked_reasons": blocked_reasons,
        "operation": scaffold.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "acknowledgements": normalized_acknowledgements,
        "source_receipts": source_receipts,
        "verification": {
            "apply_scaffold_ready": scaffold.get("ok") is True and fixture_ready,
            "sw003_live_gate_evidence_packet_ready": (
                isinstance(sw003_evidence_packet, dict)
                and sw003_evidence_packet.get("ok") is True
                and sw003_evidence_packet.get("ready_for_live_acceptance_review") is True
            ),
            "all_acknowledgements_present": all(normalized_acknowledgements.values()),
            "snapshot_repeatability_verified": snapshot.get("repeatability_verified") is True,
            "snapshot_references_sanitized": snapshot.get("sanitized_references") is True,
        },
        "required_live_sequence": [
            "capture_before_snapshot",
            "confirm_region_marker_scope",
            "apply_typed_operations",
            "capture_after_snapshot",
            "verify_region_marker_scope",
            "verify_idempotency_receipt",
            "write_quality_receipt",
            "compile_postflight_receipt",
            "compile_restore_plan_or_restore_receipt",
        ],
        "restore_required": True,
        "restore_strategy": scaffold.get("restore_strategy", "use_preflight_snapshot_path"),
        "live_apply_gate": {
            "ready_for_live_apply": ready,
            "blocked_reasons": blocked_reasons,
            "requires_human_operator_apply": True,
            "requires_postflight_receipt": True,
            "requires_restore_plan": True,
        },
        "boundary": {
            "local_gate_only": True,
            "does_not_execute_live_apply": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_sw003_live_gate": True,
            "requires_human_operator_apply": True,
        },
    }
    value["receipt_digest"] = _receipt_digest(value)
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        value["output_path"] = str(destination)
        destination.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        value["output_path"] = None
    return value


def load_region_simulation_closeout_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="simulation closeout")
    if not isinstance(raw, dict):
        raise ValueError("simulation closeout receipt must contain an object")
    if raw.get("schema_version") != "typed-region-sw009-simulation-closeout-receipt.v1":
        raise ValueError("simulation closeout receipt has an unsupported schema")
    return raw


def compile_region_simulation_closeout_receipt(
    *,
    restore_receipt: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(restore_receipt, dict):
        raise ValueError("restore receipt must contain an object")

    blocked_reasons: list[str] = []
    if restore_receipt.get("schema_version") != "typed-region-restore-receipt.v1":
        blocked_reasons.append("restore_receipt_schema_unsupported")

    restore_ok = restore_receipt.get("ok") is True
    restore_ready_for_closeout = restore_receipt.get("ready_for_closeout") is True
    restore_ready = restore_ok and restore_ready_for_closeout
    if not restore_ok:
        blocked_reasons.append("restore_receipt_not_ok")
    if not restore_ready_for_closeout:
        blocked_reasons.append("restore_receipt_not_ready_for_closeout")
    if restore_receipt.get("mutation_attempted") is not False:
        blocked_reasons.append("restore_receipt_mutation_state_invalid")
    if restore_receipt.get("live_restore_attempted") is not False:
        blocked_reasons.append("restore_receipt_live_state_invalid")

    simulation_boundary_valid = _has_simulation_boundary(restore_receipt)
    if not simulation_boundary_valid:
        blocked_reasons.append("restore_receipt_simulation_boundary_missing")

    restore_source_receipts = restore_receipt.get("source_receipts")
    if not isinstance(restore_source_receipts, dict):
        blocked_reasons.append("restore_receipt_source_receipts_missing")
        restore_source_receipts = {}
    apply_simulation_receipt_digest = restore_source_receipts.get(
        "apply_simulation_receipt_digest"
    )
    simulation_provenance_valid = _is_sha256_digest(apply_simulation_receipt_digest)
    if not simulation_provenance_valid:
        blocked_reasons.append("restore_receipt_simulation_provenance_missing")

    pre_apply_snapshot = restore_receipt.get("pre_apply_snapshot")
    if not isinstance(pre_apply_snapshot, dict):
        blocked_reasons.append("restore_receipt_pre_apply_snapshot_missing")
        pre_apply_snapshot = {}
    restored_snapshot = restore_receipt.get("restored_snapshot")
    if not isinstance(restored_snapshot, dict):
        blocked_reasons.append("restore_receipt_restored_snapshot_missing")
        restored_snapshot = {}

    pre_board_alias = pre_apply_snapshot.get("board_alias")
    restored_board_alias = restored_snapshot.get("board_alias")
    pre_content_digest = pre_apply_snapshot.get("content_digest")
    restored_content_digest = restored_snapshot.get("content_digest")
    pre_item_count = pre_apply_snapshot.get("item_count")
    restored_item_count = restored_snapshot.get("item_count")
    item_count_matches = (
        not isinstance(pre_item_count, int)
        or restored_item_count == pre_item_count
    )
    restored_to_pre_apply_snapshot = (
        isinstance(pre_board_alias, str)
        and bool(pre_board_alias)
        and restored_board_alias == pre_board_alias
        and _is_sha256_digest(pre_content_digest)
        and restored_content_digest == pre_content_digest
        and item_count_matches
        and restored_snapshot.get("repeatability_verified") is True
        and restored_snapshot.get("sanitized_references") is True
    )
    if not restored_to_pre_apply_snapshot:
        blocked_reasons.append("restore_receipt_not_restored_to_pre_apply_snapshot")

    source_receipts = {
        "restore_receipt_digest": _receipt_digest(restore_receipt),
        "apply_simulation_receipt_digest": apply_simulation_receipt_digest,
    }
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-sw009-simulation-closeout-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_closeout_attempted": False,
        "ready_for_sw009_simulation_closeout": ready,
        "ready_for_live_apply": False,
        "closes_live_sw003_gate": False,
        "blocked_reasons": blocked_reasons,
        "operation": restore_receipt.get("operation"),
        "region": restore_receipt.get("region", {}),
        "source_receipts": source_receipts,
        "verification": {
            "restore_receipt_ok": restore_ok,
            "restore_receipt_ready_for_closeout": restore_ready_for_closeout,
            "restore_receipt_ready": restore_ready,
            "simulation_boundary_valid": simulation_boundary_valid,
            "simulation_provenance_valid": simulation_provenance_valid,
            "restored_to_pre_apply_snapshot": restored_to_pre_apply_snapshot,
        },
        "live_apply_gate": _sw009_live_apply_gate(),
        "boundary": _sw009_simulation_closeout_boundary(),
    }
    value["receipt_digest"] = _receipt_digest(value)
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

def load_region_operation_contract(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="operation contract")
    if not isinstance(raw, dict):
        raise ValueError("operation contract must contain an object")
    if raw.get("schema_version") != "typed-region-operation-contract.v1":
        raise ValueError("operation contract has an unsupported schema")
    return raw


def compile_region_operation_contract(
    *,
    scaffold: dict[str, Any],
    fixture_operations: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(scaffold, dict):
        raise ValueError("apply scaffold must contain an object")

    blocked_reasons: list[str] = []
    if scaffold.get("schema_version") != "typed-region-apply-scaffold.v1":
        blocked_reasons.append("apply_scaffold_schema_unsupported")
    fixture_ready = scaffold.get("ready_for_fixture_apply") is True
    if scaffold.get("ok") is not True or not fixture_ready:
        blocked_reasons.append("apply_scaffold_not_ready")
    if scaffold.get("ready_for_live_apply") is not False:
        blocked_reasons.append("apply_scaffold_live_gate_not_closed")
    if scaffold.get("mutation_attempted") is not False:
        blocked_reasons.append("apply_scaffold_mutation_state_invalid")

    region = scaffold.get("region")
    declaration: RegionDeclaration | None = None
    if not isinstance(region, dict):
        blocked_reasons.append("apply_scaffold_region_missing")
        region = {}
    else:
        try:
            declaration = parse_region_declaration({"region": region})
        except ValueError:
            blocked_reasons.append("apply_scaffold_region_invalid")

    snapshot = scaffold.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("apply_scaffold_snapshot_missing")
        snapshot = {}

    boundary = scaffold.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("scaffold_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("apply_scaffold_boundary_missing")

    scaffold_blocks = scaffold.get("blocked_reasons", [])
    if scaffold_blocks:
        blocked_reasons.extend(
            f"apply_scaffold:{reason}" for reason in scaffold_blocks if isinstance(reason, str)
        )

    if declaration is None:
        raise ValueError("apply scaffold region is required for operation contract")
    if declaration.mode != "managed":
        blocked_reasons.append("apply_scaffold_region_not_managed")
    snapshot_digest = snapshot.get("content_digest")
    if snapshot_digest != declaration.expected_snapshot_digest:
        blocked_reasons.append("apply_scaffold_snapshot_digest_mismatch")

    normalized_operations = _normalized_fixture_operations(
        fixture_operations, region_id=declaration.region_id
    )
    operations_digest = _stable_digest(normalized_operations)
    idempotency_key = f"{declaration.view_id}:{declaration.region_id}:{operations_digest}"
    source_receipts = {
        "apply_scaffold_digest": _stable_digest(_without_runtime_fields(scaffold)),
        "fixture_operations_digest": operations_digest,
    }
    ready = not blocked_reasons
    contract_material = {
        "schema_version": "typed-region-operation-contract.v1",
        "operation": scaffold.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "operations_digest": operations_digest,
        "source_receipts": source_receipts,
    }
    value = {
        "schema_version": "typed-region-operation-contract.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_apply_simulation": ready,
        "blocked_reasons": blocked_reasons,
        "operation": scaffold.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "operations": normalized_operations,
        "operation_count": len(normalized_operations),
        "operations_digest": operations_digest,
        "idempotency": {
            "method": "operation_contract_digest",
            "key": idempotency_key,
        },
        "simulation_required": [
            "verify_region_marker_scope",
            "verify_operation_contract_digest",
            "verify_idempotency_key",
            "emit_apply_receipt_fixture_evidence",
        ],
        "postflight_evidence_required": [
            "fixture_operations_digest",
            "idempotency_key",
            "idempotency_verified",
        ],
        "restore_required": True,
        "restore_strategy": scaffold.get("restore_strategy", "use_preflight_snapshot_path"),
        "source_receipts": source_receipts,
        "boundary": {
            "fixture_only": True,
            "simulation_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
        "contract_digest": _stable_digest(contract_material),
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



def load_region_apply_simulation_receipt(path: Path) -> dict[str, Any]:
    raw = _load_json_or_yaml(path, label="apply simulation")
    if not isinstance(raw, dict):
        raise ValueError("apply simulation receipt must contain an object")
    if raw.get("schema_version") != "typed-region-apply-simulation-receipt.v1":
        raise ValueError("apply simulation receipt has an unsupported schema")
    return raw


def compile_region_apply_simulation_receipt(
    *,
    operation_contract: dict[str, Any],
    after_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(operation_contract, dict):
        raise ValueError("operation contract must contain an object")

    blocked_reasons: list[str] = []
    if operation_contract.get("schema_version") != "typed-region-operation-contract.v1":
        blocked_reasons.append("operation_contract_schema_unsupported")
    contract_ready = (
        operation_contract.get("ok") is True
        and operation_contract.get("ready_for_apply_simulation") is True
    )
    if not contract_ready:
        blocked_reasons.append("operation_contract_not_ready")
    if operation_contract.get("mutation_attempted") is not False:
        blocked_reasons.append("operation_contract_mutation_state_invalid")
    if operation_contract.get("live_apply_attempted") is not False:
        blocked_reasons.append("operation_contract_live_state_invalid")

    region = operation_contract.get("region")
    declaration: RegionDeclaration | None = None
    if not isinstance(region, dict):
        blocked_reasons.append("operation_contract_region_missing")
        region = {}
    else:
        try:
            declaration = parse_region_declaration({"region": region})
        except ValueError:
            blocked_reasons.append("operation_contract_region_invalid")
    if declaration is None:
        raise ValueError("operation contract region is required for apply simulation")

    snapshot = operation_contract.get("snapshot")
    if not isinstance(snapshot, dict):
        blocked_reasons.append("operation_contract_snapshot_missing")
        snapshot = {}
    if snapshot.get("content_digest") != declaration.expected_snapshot_digest:
        blocked_reasons.append("operation_contract_snapshot_digest_mismatch")

    boundary = operation_contract.get("boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("fixture_only") is not True
        or boundary.get("simulation_only") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("no_provider_ids_returned") is not True
    ):
        blocked_reasons.append("operation_contract_boundary_missing")

    normalized_after = _snapshot_mapping_receipt(after_snapshot, label="after")
    if normalized_after["board_alias"] != declaration.surface_alias:
        blocked_reasons.append("after_snapshot_board_alias_mismatch")
    if normalized_after.get("repeatability_verified") is not True:
        blocked_reasons.append("after_snapshot_repeatability_unverified")
    if normalized_after.get("sanitized_references") is not True:
        blocked_reasons.append("after_snapshot_references_not_sanitized")

    expected_operations_digest = operation_contract.get("operations_digest")
    observed_operations_digest = after_snapshot.get("operation_contract_operations_digest")
    if not isinstance(expected_operations_digest, str):
        blocked_reasons.append("operation_contract_operations_digest_missing")
    elif observed_operations_digest != expected_operations_digest:
        blocked_reasons.append("after_snapshot_operations_digest_mismatch")

    expected_contract_digest = operation_contract.get("contract_digest")
    observed_contract_digest = after_snapshot.get("operation_contract_digest")
    if not isinstance(expected_contract_digest, str):
        blocked_reasons.append("operation_contract_digest_missing")
    elif observed_contract_digest != expected_contract_digest:
        blocked_reasons.append("after_snapshot_contract_digest_mismatch")

    idempotency = operation_contract.get("idempotency")
    if not isinstance(idempotency, dict):
        blocked_reasons.append("operation_contract_idempotency_missing")
        idempotency = {}
    expected_idempotency_key = idempotency.get("key")
    observed_idempotency_key = after_snapshot.get("idempotency_key")
    if not isinstance(observed_idempotency_key, str):
        blocked_reasons.append("after_snapshot_idempotency_key_missing")
    elif observed_idempotency_key != expected_idempotency_key:
        blocked_reasons.append("after_snapshot_idempotency_key_mismatch")
    idempotency_verified = after_snapshot.get("idempotency_verified") is True
    if not idempotency_verified:
        blocked_reasons.append("after_snapshot_idempotency_unverified")

    verification = {
        "operation_contract_digest": observed_contract_digest,
        "operation_contract_operations_digest": observed_operations_digest,
        "idempotency_key": observed_idempotency_key,
        "idempotency_verified": idempotency_verified,
    }
    source_receipts = {
        "operation_contract_digest": _stable_digest(
            _without_runtime_fields(operation_contract)
        ),
        "after_snapshot_digest": _stable_digest(normalized_after),
        "after_snapshot_input_digest": _stable_digest(after_snapshot),
    }
    ready = not blocked_reasons
    value = {
        "schema_version": "typed-region-apply-simulation-receipt.v1",
        "ok": ready,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "ready_for_postflight": ready,
        "blocked_reasons": blocked_reasons,
        "operation": operation_contract.get("operation"),
        "region": region,
        "pre_apply_snapshot": snapshot,
        "after_snapshot": normalized_after,
        "verification": verification,
        "operations": operation_contract.get("operations", []),
        "operation_count": operation_contract.get("operation_count"),
        "operations_digest": expected_operations_digest,
        "idempotency": idempotency,
        "postflight_required": [
            "verify_region_marker_scope",
            "verify_operation_contract_digest",
            "verify_idempotency_receipt",
            "write_quality_receipt",
        ],
        "restore_required": True,
        "restore_strategy": operation_contract.get(
            "restore_strategy", "use_preflight_snapshot_path"
        ),
        "source_receipts": source_receipts,
        "boundary": {
            "fixture_only": True,
            "simulation_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
        "receipt_digest": _stable_digest(
            {
                "schema_version": "typed-region-apply-simulation-receipt.v1",
                "operation": operation_contract.get("operation"),
                "region": region,
                "pre_apply_snapshot": snapshot,
                "after_snapshot": normalized_after,
                "verification": verification,
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
