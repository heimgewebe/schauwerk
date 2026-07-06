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
    if scaffold.get("ok") is not True or scaffold.get("ready_for_live_apply") is not True:
        blocked_reasons.append("apply_scaffold_not_ready")
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
        "ready_for_live_apply": ready,
        "blocked_reasons": blocked_reasons,
        "operation": preflight.get("operation"),
        "region": region,
        "snapshot": snapshot,
        "required_live_preconditions": [
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
        "boundary": {
            "fixture_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
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
        "postflight_receipt_digest": _stable_digest(
            _without_runtime_fields(postflight_receipt)
        ),
        "restored_snapshot_digest": _stable_digest(normalized_restored),
    }
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
        "boundary": {
            "fixture_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
        "receipt_digest": _stable_digest(
            {
                "schema_version": "typed-region-restore-receipt.v1",
                "operation": postflight_receipt.get("operation"),
                "region": postflight_receipt.get("region", {}),
                "pre_apply_snapshot": pre_apply_snapshot,
                "restored_snapshot": normalized_restored,
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
    if scaffold.get("ok") is not True or scaffold.get("ready_for_live_apply") is not True:
        blocked_reasons.append("apply_scaffold_not_ready")
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
