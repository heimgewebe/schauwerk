"""Reviewed, transaction-like live apply for marked managed-region text replacements."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from schauwerk.operator.core import RegionDeclaration, parse_region_declaration
from schauwerk.surfaces.miro.credentials import write_json_owner_only
from schauwerk.surfaces.miro.errors import redact_text

LIVE_OPERATION_DRAFT_SCHEMA = "typed-region-live-operation-draft.v1"
LIVE_OPERATION_BUNDLE_SCHEMA = "typed-region-live-operation-bundle.v1"
LIVE_AUTHORIZATION_SCHEMA = "typed-region-live-authorization.v1"
LIVE_PLAN_SCHEMA = "typed-region-live-apply-plan.v1"
LIVE_TRANSACTION_SCHEMA = "typed-region-live-transaction-receipt.v1"
LIVE_RESTORE_SCHEMA = "typed-region-live-restore-receipt.v1"
LIVE_JOURNAL_SCHEMA = "typed-region-live-transaction-journal.v1"
KILL_SWITCH_SCHEMA = "typed-region-live-kill-switch.v1"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,80}$")
_HEX = re.compile(r"^[a-f0-9]{64}$")
_FORBIDDEN_REFERENCE = re.compile(r"(?i)(?:https?://|miro\.com|moveToWidget=)")
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TEXT_BYTES = 8 * 1024
_REQUIRED_CAPABILITIES = frozenset({"layout_read", "layout_update"})


class ManagedRegionProvider(Protocol):
    """Minimal provider boundary used by the live executor."""

    def capabilities(self) -> set[str]: ...

    async def snapshot(self, *, alias: str, output_path: Path) -> Mapping[str, Any]: ...

    async def read_dsl(self, *, alias: str) -> str: ...

    async def replace_text(
        self, *, alias: str, old_text: str, new_text: str
    ) -> Mapping[str, Any]: ...


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _receipt_digest(value: Mapping[str, Any]) -> str:
    return _stable_digest(
        {
            key: item
            for key, item in value.items()
            if key not in {"output_path", "receipt_digest", "replayed_without_mutation"}
        }
    )


def _manifest_digest(value: Mapping[str, Any], digest_key: str) -> str:
    return _stable_digest(
        {
            key: item
            for key, item in value.items()
            if key not in {digest_key, "output_path"}
        }
    )


def _safe_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value.strip()):
        raise ValueError(f"{label} has an unsafe identifier shape")
    return value.strip()


def _digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return value


def _safe_text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if not allow_empty and not value:
        raise ValueError(f"{label} must not be empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{label} must be a single line")
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{label} exceeds the 8 KiB limit")
    if _FORBIDDEN_REFERENCE.search(value):
        raise ValueError(f"{label} contains a provider or network reference")
    if '"' in value or "<<<" in value or ">>>" in value:
        raise ValueError(f"{label} contains a forbidden DSL delimiter")
    return value


def _read_json(path: Path, *, label: str, owner_only: bool = False) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError(f"{label} path is unsafe")
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} path is unsafe")
    if owner_only and metadata.st_mode & 0o077:
        raise ValueError(f"{label} must have owner-only permissions")
    if metadata.st_size > _MAX_FILE_BYTES:
        raise ValueError(f"{label} exceeds the 2 MiB limit")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    return value


def live_artifact_destination(path: Path, *, label: str) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError(f"{label} output path is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError(f"{label} output path is unsafe")
    return destination


def write_live_artifact(path: Path, value: Mapping[str, Any], *, label: str) -> Path:
    destination = live_artifact_destination(path, label=label)
    write_json_owner_only(destination, dict(value))
    return destination


def compile_live_operation_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "bundle_id",
        "surface_alias",
        "region_id",
        "expected_snapshot_digest",
        "operation",
        "marker",
        "operations",
        "boundary",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("live operation draft fields are invalid")
    if value.get("schema_version") != LIVE_OPERATION_DRAFT_SCHEMA:
        raise ValueError("live operation draft has an unsupported schema")
    bundle = {**dict(value), "schema_version": LIVE_OPERATION_BUNDLE_SCHEMA}
    bundle["bundle_digest"] = _manifest_digest(bundle, "bundle_digest")
    return validate_live_operation_bundle(bundle)


def load_live_operation_draft(path: Path) -> dict[str, Any]:
    return compile_live_operation_bundle(
        _read_json(path, label="live operation draft", owner_only=True)
    )


def load_live_operation_bundle(path: Path) -> dict[str, Any]:
    return validate_live_operation_bundle(
        _read_json(path, label="live operation bundle", owner_only=True)
    )


def validate_live_operation_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("live operation bundle must contain an object")
    expected = {
        "schema_version",
        "bundle_id",
        "surface_alias",
        "region_id",
        "expected_snapshot_digest",
        "operation",
        "marker",
        "operations",
        "boundary",
        "bundle_digest",
    }
    if set(value) != expected:
        raise ValueError("live operation bundle fields are invalid")
    if value.get("schema_version") != LIVE_OPERATION_BUNDLE_SCHEMA:
        raise ValueError("live operation bundle has an unsupported schema")
    bundle_id = _safe_id(value.get("bundle_id"), label="bundle_id")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    snapshot_digest = _digest(
        value.get("expected_snapshot_digest"), label="expected_snapshot_digest"
    )
    bundle_operation = value.get("operation")
    if bundle_operation != "render-update":
        raise ValueError("live operation bundle supports only render-update")
    marker = _safe_text(value.get("marker"), label="marker")
    expected_marker = f"schauwerk-region:{region_id}"
    if marker != expected_marker:
        raise ValueError("live operation bundle marker does not bind the region")

    raw_operations = value.get("operations")
    if not isinstance(raw_operations, Sequence) or isinstance(raw_operations, (str, bytes)):
        raise ValueError("live operation bundle operations must be a list")
    if not raw_operations or len(raw_operations) > 50:
        raise ValueError("live operation bundle must contain 1-50 operations")
    normalized: list[dict[str, str]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_operations):
        if not isinstance(raw, Mapping) or set(raw) != {
            "operation_id",
            "action",
            "region_id",
            "old_text",
            "new_text",
        }:
            raise ValueError(f"live operation bundle operations[{index}] fields are invalid")
        operation_id = _safe_id(
            raw.get("operation_id"), label=f"operations[{index}].operation_id"
        )
        if operation_id in identifiers:
            raise ValueError("live operation bundle operation ids must be unique")
        identifiers.add(operation_id)
        if raw.get("action") != "replace-text":
            raise ValueError("live operation action must be replace-text")
        operation_region = _safe_id(
            raw.get("region_id"), label=f"operations[{index}].region_id"
        )
        if operation_region != region_id:
            raise ValueError("live operation targets a different region")
        old_text = _safe_text(raw.get("old_text"), label=f"operations[{index}].old_text")
        new_text = _safe_text(raw.get("new_text"), label=f"operations[{index}].new_text")
        if old_text == new_text:
            raise ValueError("live operation old_text and new_text must differ")
        if marker not in old_text or marker not in new_text:
            raise ValueError("live operation text must preserve the managed-region marker")
        normalized.append(
            {
                "operation_id": operation_id,
                "action": "replace-text",
                "region_id": region_id,
                "old_text": old_text,
                "new_text": new_text,
            }
        )

    operation_texts: list[tuple[str, str]] = []
    for operation in normalized:
        operation_texts.extend(
            (
                (f"{operation['operation_id']}.old_text", operation["old_text"]),
                (f"{operation['operation_id']}.new_text", operation["new_text"]),
            )
        )
    for index, (left_label, left) in enumerate(operation_texts):
        for right_label, right in operation_texts[index + 1 :]:
            if left == right or left in right or right in left:
                raise ValueError(
                    f"live operation texts overlap: {left_label} and {right_label}"
                )

    boundary = value.get("boundary")
    expected_boundary = {
        "managed_region_only": True,
        "exact_text_replacement_only": True,
        "provider_references_prohibited": True,
        "review_required": True,
        "restore_required": True,
    }
    if boundary != expected_boundary:
        raise ValueError("live operation bundle boundary is invalid")
    declared = _digest(value.get("bundle_digest"), label="bundle_digest")
    actual = _manifest_digest(value, "bundle_digest")
    if declared != actual:
        raise ValueError("live operation bundle digest mismatch")
    return {
        "schema_version": LIVE_OPERATION_BUNDLE_SCHEMA,
        "bundle_id": bundle_id,
        "surface_alias": alias,
        "region_id": region_id,
        "expected_snapshot_digest": snapshot_digest,
        "operation": bundle_operation,
        "marker": marker,
        "operations": normalized,
        "boundary": expected_boundary,
        "bundle_digest": actual,
    }


def load_live_authorization(path: Path) -> dict[str, Any]:
    return validate_live_authorization(
        _read_json(path, label="live authorization", owner_only=True)
    )


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp") from exc
    return parsed.astimezone(UTC)


def validate_live_authorization(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "authorization_id",
        "gate_receipt_digest",
        "operation_bundle_digest",
        "surface_alias",
        "region_id",
        "expected_snapshot_digest",
        "approved_by",
        "approved_at",
        "expires_at",
        "approval_reference",
        "approved",
        "boundary",
        "authorization_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("live authorization fields are invalid")
    if value.get("schema_version") != LIVE_AUTHORIZATION_SCHEMA:
        raise ValueError("live authorization has an unsupported schema")
    normalized = {
        "schema_version": LIVE_AUTHORIZATION_SCHEMA,
        "authorization_id": _safe_id(value.get("authorization_id"), label="authorization_id"),
        "gate_receipt_digest": _digest(
            value.get("gate_receipt_digest"), label="gate_receipt_digest"
        ),
        "operation_bundle_digest": _digest(
            value.get("operation_bundle_digest"), label="operation_bundle_digest"
        ),
        "surface_alias": _safe_id(value.get("surface_alias"), label="surface_alias"),
        "region_id": _safe_id(value.get("region_id"), label="region_id"),
        "expected_snapshot_digest": _digest(
            value.get("expected_snapshot_digest"), label="expected_snapshot_digest"
        ),
        "approved_by": _safe_id(value.get("approved_by"), label="approved_by"),
        "approved_at": value.get("approved_at"),
        "expires_at": value.get("expires_at"),
        "approval_reference": _safe_text(
            value.get("approval_reference"), label="approval_reference"
        ),
        "approved": value.get("approved"),
        "boundary": value.get("boundary"),
        "authorization_digest": value.get("authorization_digest"),
    }
    approved_at = _parse_timestamp(normalized["approved_at"], label="approved_at")
    expires_at = _parse_timestamp(normalized["expires_at"], label="expires_at")
    if expires_at <= approved_at:
        raise ValueError("live authorization expiry must be after approval")
    if (expires_at - approved_at).total_seconds() > 86_400:
        raise ValueError("live authorization validity may not exceed 24 hours")
    if normalized["approved"] is not True:
        raise ValueError("live authorization is not approved")
    expected_boundary = {
        "single_use": True,
        "explicit_live_apply": True,
        "operation_bundle_bound": True,
        "gate_receipt_bound": True,
    }
    if normalized["boundary"] != expected_boundary:
        raise ValueError("live authorization boundary is invalid")
    declared = _digest(
        normalized["authorization_digest"], label="authorization_digest"
    )
    actual = _manifest_digest(value, "authorization_digest")
    if declared != actual:
        raise ValueError("live authorization digest mismatch")
    normalized["authorization_digest"] = actual
    return normalized


def _validate_gate_receipt(value: Mapping[str, Any]) -> tuple[dict[str, Any], RegionDeclaration]:
    if not isinstance(value, Mapping):
        raise ValueError("live apply gate receipt must contain an object")
    if value.get("schema_version") != "typed-region-sw009-live-apply-gate-receipt.v1":
        raise ValueError("live apply gate receipt has an unsupported schema")
    if value.get("ok") is not True or value.get("ready_for_live_apply") is not True:
        raise ValueError("live apply gate receipt is not ready")
    if (
        value.get("mutation_attempted") is not False
        or value.get("live_apply_attempted") is not False
    ):
        raise ValueError("live apply gate receipt mutation state is invalid")
    if value.get("blocked_reasons") != []:
        raise ValueError("live apply gate receipt contains blocked reasons")
    boundary = value.get("boundary")
    if not isinstance(boundary, Mapping) or (
        boundary.get("local_gate_only") is not True
        or boundary.get("does_not_execute_live_apply") is not True
        or boundary.get("no_miro_mutation") is not True
        or boundary.get("requires_human_operator_apply") is not True
    ):
        raise ValueError("live apply gate receipt boundary is invalid")
    receipt_digest = _digest(value.get("receipt_digest"), label="gate.receipt_digest")
    if receipt_digest != _receipt_digest(value):
        raise ValueError("live apply gate receipt digest mismatch")
    region = value.get("region")
    if not isinstance(region, dict):
        raise ValueError("live apply gate receipt region is missing")
    declaration = parse_region_declaration({"region": region})
    if declaration.mode != "managed":
        raise ValueError("live apply gate receipt region is not managed")
    snapshot = value.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("live apply gate receipt snapshot is missing")
    if snapshot.get("content_digest") != declaration.expected_snapshot_digest:
        raise ValueError("live apply gate receipt snapshot digest mismatch")
    if snapshot.get("board_alias") != declaration.surface_alias:
        raise ValueError("live apply gate receipt alias mismatch")
    return dict(value), declaration


def load_live_apply_gate(path: Path) -> dict[str, Any]:
    value = _read_json(path, label="live apply gate receipt")
    return _validate_gate_receipt(value)[0]


def compile_live_apply_plan(
    *,
    gate_receipt: Mapping[str, Any],
    operation_bundle: Mapping[str, Any],
    authorization: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    gate, declaration = _validate_gate_receipt(gate_receipt)
    bundle = validate_live_operation_bundle(operation_bundle)
    approved = validate_live_authorization(authorization)
    approved_at = _parse_timestamp(approved["approved_at"], label="approved_at")
    expires_at = _parse_timestamp(approved["expires_at"], label="expires_at")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if current < approved_at:
        raise ValueError("live authorization is not active yet")
    if current >= expires_at:
        raise ValueError("live authorization has expired")
    gate_digest = gate["receipt_digest"]
    bindings = {
        "surface_alias": declaration.surface_alias,
        "region_id": declaration.region_id,
        "expected_snapshot_digest": declaration.expected_snapshot_digest,
    }
    for key, expected in bindings.items():
        if bundle[key] != expected or approved[key] != expected:
            raise ValueError(f"live apply binding mismatch for {key}")
    if approved["gate_receipt_digest"] != gate_digest:
        raise ValueError("live authorization gate receipt binding mismatch")
    if approved["operation_bundle_digest"] != bundle["bundle_digest"]:
        raise ValueError("live authorization operation bundle binding mismatch")
    if bundle["operation"] != gate.get("operation"):
        raise ValueError("live operation bundle operation mismatch")
    plan = {
        "schema_version": LIVE_PLAN_SCHEMA,
        "ok": True,
        "ready_for_live_apply": True,
        "mutation_attempted": False,
        "live_apply_attempted": False,
        "surface_alias": declaration.surface_alias,
        "region_id": declaration.region_id,
        "operation": bundle["operation"],
        "marker": bundle["marker"],
        "expected_snapshot_digest": declaration.expected_snapshot_digest,
        "operation_count": len(bundle["operations"]),
        "operations": bundle["operations"],
        "authorization": {
            "authorization_id": approved["authorization_id"],
            "approved_by": approved["approved_by"],
            "approved_at": approved["approved_at"],
            "expires_at": approved["expires_at"],
            "approval_reference": approved["approval_reference"],
        },
        "source_receipts": {
            "gate_receipt_digest": gate_digest,
            "operation_bundle_digest": bundle["bundle_digest"],
            "authorization_digest": approved["authorization_digest"],
        },
        "required_capabilities": sorted(_REQUIRED_CAPABILITIES),
        "required_sequence": [
            "check_kill_switch",
            "reserve_single_use_authorization",
            "capture_verified_before_snapshot",
            "read_live_dsl",
            "verify_unique_managed_region_matches",
            "persist_prepared_journal",
            "apply_exact_text_replacements",
            "read_live_dsl_after_apply",
            "verify_semantics_and_idempotency",
            "capture_verified_after_snapshot",
            "persist_transaction_receipt",
        ],
        "restore_required": True,
        "boundary": {
            "managed_region_only": True,
            "exact_text_replacement_only": True,
            "reviewed_authorization_required": True,
            "provider_references_prohibited_in_inputs": True,
            "provider_identifiers_not_returned": True,
        },
    }
    plan["plan_digest"] = _stable_digest(plan)
    return plan


def validate_live_apply_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "ok",
        "ready_for_live_apply",
        "mutation_attempted",
        "live_apply_attempted",
        "surface_alias",
        "region_id",
        "operation",
        "marker",
        "expected_snapshot_digest",
        "operation_count",
        "operations",
        "authorization",
        "source_receipts",
        "required_capabilities",
        "required_sequence",
        "restore_required",
        "boundary",
        "plan_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("live apply plan fields are invalid")
    if value.get("schema_version") != LIVE_PLAN_SCHEMA:
        raise ValueError("live apply plan has an unsupported schema")
    if (
        value.get("ok") is not True
        or value.get("ready_for_live_apply") is not True
        or value.get("mutation_attempted") is not False
        or value.get("live_apply_attempted") is not False
        or value.get("restore_required") is not True
    ):
        raise ValueError("live apply plan readiness is invalid")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    operation = value.get("operation")
    if operation != "render-update":
        raise ValueError("live apply plan supports only render-update")
    marker = _safe_text(value.get("marker"), label="marker")
    expected_snapshot_digest = _digest(
        value.get("expected_snapshot_digest"), label="expected_snapshot_digest"
    )
    operations = value.get("operations")
    operation_count = value.get("operation_count")
    if (
        isinstance(operation_count, bool)
        or not isinstance(operation_count, int)
        or not isinstance(operations, list)
        or operation_count != len(operations)
    ):
        raise ValueError("live apply plan operation count is invalid")
    validation_bundle = {
        "schema_version": LIVE_OPERATION_BUNDLE_SCHEMA,
        "bundle_id": "live-plan-validation",
        "surface_alias": alias,
        "region_id": region_id,
        "expected_snapshot_digest": expected_snapshot_digest,
        "operation": operation,
        "marker": marker,
        "operations": operations,
        "boundary": {
            "managed_region_only": True,
            "exact_text_replacement_only": True,
            "provider_references_prohibited": True,
            "review_required": True,
            "restore_required": True,
        },
    }
    validation_bundle["bundle_digest"] = _manifest_digest(
        validation_bundle, "bundle_digest"
    )
    normalized_operations = validate_live_operation_bundle(validation_bundle)["operations"]

    authorization = value.get("authorization")
    expected_authorization_fields = {
        "authorization_id",
        "approved_by",
        "approved_at",
        "expires_at",
        "approval_reference",
    }
    if (
        not isinstance(authorization, Mapping)
        or set(authorization) != expected_authorization_fields
    ):
        raise ValueError("live apply plan authorization fields are invalid")
    normalized_authorization = {
        "authorization_id": _safe_id(
            authorization.get("authorization_id"), label="authorization_id"
        ),
        "approved_by": _safe_id(authorization.get("approved_by"), label="approved_by"),
        "approved_at": authorization.get("approved_at"),
        "expires_at": authorization.get("expires_at"),
        "approval_reference": _safe_text(
            authorization.get("approval_reference"), label="approval_reference"
        ),
    }
    approved_at = _parse_timestamp(
        normalized_authorization["approved_at"], label="approved_at"
    )
    expires_at = _parse_timestamp(
        normalized_authorization["expires_at"], label="expires_at"
    )
    if expires_at <= approved_at or (expires_at - approved_at).total_seconds() > 86_400:
        raise ValueError("live apply plan authorization window is invalid")

    source_receipts = value.get("source_receipts")
    if not isinstance(source_receipts, Mapping) or set(source_receipts) != {
        "gate_receipt_digest",
        "operation_bundle_digest",
        "authorization_digest",
    }:
        raise ValueError("live apply plan source receipt fields are invalid")
    normalized_sources = {
        key: _digest(source_receipts.get(key), label=key)
        for key in (
            "gate_receipt_digest",
            "operation_bundle_digest",
            "authorization_digest",
        )
    }
    required_sequence = [
        "check_kill_switch",
        "reserve_single_use_authorization",
        "capture_verified_before_snapshot",
        "read_live_dsl",
        "verify_unique_managed_region_matches",
        "persist_prepared_journal",
        "apply_exact_text_replacements",
        "read_live_dsl_after_apply",
        "verify_semantics_and_idempotency",
        "capture_verified_after_snapshot",
        "persist_transaction_receipt",
    ]
    if value.get("required_capabilities") != sorted(_REQUIRED_CAPABILITIES):
        raise ValueError("live apply plan capability contract is invalid")
    if value.get("required_sequence") != required_sequence:
        raise ValueError("live apply plan sequence is invalid")
    expected_boundary = {
        "managed_region_only": True,
        "exact_text_replacement_only": True,
        "reviewed_authorization_required": True,
        "provider_references_prohibited_in_inputs": True,
        "provider_identifiers_not_returned": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("live apply plan boundary is invalid")
    declared = _digest(value.get("plan_digest"), label="plan_digest")
    if declared != _manifest_digest(value, "plan_digest"):
        raise ValueError("live apply plan digest mismatch")
    return {
        **dict(value),
        "surface_alias": alias,
        "region_id": region_id,
        "marker": marker,
        "expected_snapshot_digest": expected_snapshot_digest,
        "operations": normalized_operations,
        "authorization": normalized_authorization,
        "source_receipts": normalized_sources,
        "plan_digest": declared,
    }


def load_live_apply_plan(path: Path) -> dict[str, Any]:
    return validate_live_apply_plan(
        _read_json(path, label="live apply plan", owner_only=True)
    )


def validate_live_transaction_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "ok",
        "mutation_attempted",
        "live_apply_attempted",
        "transaction_id",
        "surface_alias",
        "region_id",
        "operation",
        "operation_count",
        "applied_operation_ids",
        "before_snapshot_digest",
        "after_snapshot_digest",
        "before_dsl_digest",
        "after_dsl_digest",
        "semantic_verification_passed",
        "idempotency_verified",
        "postflight_verified",
        "restore_ready",
        "mutation_receipts",
        "journal_path",
        "committed_journal_digest",
        "source_receipts",
        "boundary",
        "receipt_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("live transaction receipt fields are invalid")
    if value.get("schema_version") != LIVE_TRANSACTION_SCHEMA:
        raise ValueError("live transaction receipt has an unsupported schema")
    for field in (
        "ok",
        "mutation_attempted",
        "live_apply_attempted",
        "semantic_verification_passed",
        "idempotency_verified",
        "postflight_verified",
        "restore_ready",
    ):
        if value.get(field) is not True:
            raise ValueError(f"live transaction receipt {field} is invalid")
    transaction_id = _safe_id(value.get("transaction_id"), label="transaction_id")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    operation = value.get("operation")
    if operation != "render-update":
        raise ValueError("live transaction receipt operation is invalid")
    operation_count = value.get("operation_count")
    applied_ids = value.get("applied_operation_ids")
    if (
        isinstance(operation_count, bool)
        or not isinstance(operation_count, int)
        or operation_count < 1
        or not isinstance(applied_ids, list)
        or len(applied_ids) != operation_count
        or len(set(applied_ids)) != operation_count
    ):
        raise ValueError("live transaction receipt operation counts are invalid")
    normalized_ids = [
        _safe_id(item, label=f"applied_operation_ids[{index}]")
        for index, item in enumerate(applied_ids)
    ]
    digest_fields = {
        key: _digest(value.get(key), label=key)
        for key in (
            "before_snapshot_digest",
            "after_snapshot_digest",
            "before_dsl_digest",
            "after_dsl_digest",
        )
    }
    if digest_fields["before_snapshot_digest"] == digest_fields["after_snapshot_digest"]:
        raise ValueError("live transaction receipt snapshot state did not change")
    if digest_fields["before_dsl_digest"] == digest_fields["after_dsl_digest"]:
        raise ValueError("live transaction receipt DSL state did not change")
    mutation_receipts = value.get("mutation_receipts")
    if not isinstance(mutation_receipts, list) or len(mutation_receipts) != operation_count:
        raise ValueError("live transaction mutation receipts are invalid")
    normalized_mutations = [
        _sanitized_mutation_receipt(item)
        for item in mutation_receipts
        if isinstance(item, Mapping)
    ]
    if len(normalized_mutations) != operation_count:
        raise ValueError("live transaction mutation receipts are invalid")
    journal_path = _safe_text(value.get("journal_path"), label="journal_path")
    committed_journal_digest = _digest(
        value.get("committed_journal_digest"), label="committed_journal_digest"
    )
    source_receipts = value.get("source_receipts")
    if not isinstance(source_receipts, Mapping) or set(source_receipts) != {
        "gate_receipt_digest",
        "operation_bundle_digest",
        "authorization_digest",
    }:
        raise ValueError("live transaction source receipt fields are invalid")
    normalized_sources = {
        key: _digest(source_receipts.get(key), label=key)
        for key in source_receipts
    }
    expected_boundary = {
        "managed_region_only": True,
        "exact_text_replacement_only": True,
        "provider_identifiers_not_returned": True,
        "single_use_authorization_consumed": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("live transaction receipt boundary is invalid")
    declared = _digest(value.get("receipt_digest"), label="receipt_digest")
    if declared != _receipt_digest(value):
        raise ValueError("live transaction receipt digest mismatch")
    return {
        **dict(value),
        "transaction_id": transaction_id,
        "surface_alias": alias,
        "region_id": region_id,
        "applied_operation_ids": normalized_ids,
        **digest_fields,
        "mutation_receipts": normalized_mutations,
        "journal_path": journal_path,
        "committed_journal_digest": committed_journal_digest,
        "source_receipts": normalized_sources,
        "receipt_digest": declared,
    }


def validate_live_transaction_failure_receipt(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    common_fields = {
        "schema_version",
        "ok",
        "mutation_attempted",
        "live_apply_attempted",
        "transaction_id",
        "surface_alias",
        "region_id",
        "operation_count",
        "applied_operation_ids",
        "failure",
        "rollback_attempted",
        "rollback_succeeded",
        "rollback_error",
        "restore_ready",
        "journal_path",
        "source_receipts",
        "boundary",
        "receipt_digest",
    }
    preflight_fields = common_fields
    apply_fields = common_fields | {"manual_recovery_required"}
    if not isinstance(value, Mapping) or set(value) not in {
        frozenset(preflight_fields),
        frozenset(apply_fields),
    }:
        raise ValueError("live transaction failure receipt fields are invalid")
    if value.get("schema_version") != LIVE_TRANSACTION_SCHEMA:
        raise ValueError("live transaction failure receipt has an unsupported schema")
    if value.get("ok") is not False or value.get("live_apply_attempted") is not True:
        raise ValueError("live transaction failure receipt status is invalid")
    if value.get("restore_ready") is not False:
        raise ValueError("live transaction failure receipt restore state is invalid")
    mutation_attempted = value.get("mutation_attempted")
    rollback_attempted = value.get("rollback_attempted")
    if not isinstance(mutation_attempted, bool) or not isinstance(
        rollback_attempted, bool
    ):
        raise ValueError("live transaction failure mutation state is invalid")
    if rollback_attempted is not mutation_attempted:
        raise ValueError("live transaction failure rollback state is invalid")
    transaction_id = _safe_id(value.get("transaction_id"), label="transaction_id")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    operation_count = value.get("operation_count")
    applied_ids = value.get("applied_operation_ids")
    if (
        isinstance(operation_count, bool)
        or not isinstance(operation_count, int)
        or not 1 <= operation_count <= 100
        or not isinstance(applied_ids, list)
        or len(applied_ids) > operation_count
        or len(set(applied_ids)) != len(applied_ids)
    ):
        raise ValueError("live transaction failure operation counts are invalid")
    normalized_ids = [
        _safe_id(item, label=f"applied_operation_ids[{index}]")
        for index, item in enumerate(applied_ids)
    ]
    failure = _safe_text(value.get("failure"), label="failure")
    rollback_succeeded = value.get("rollback_succeeded")
    rollback_error = value.get("rollback_error")
    is_apply_failure = set(value) == apply_fields
    if not is_apply_failure:
        if (
            mutation_attempted
            or normalized_ids
            or rollback_succeeded is not None
            or rollback_error is not None
        ):
            raise ValueError("live transaction preflight failure state is invalid")
    else:
        if not isinstance(rollback_succeeded, bool):
            raise ValueError("live transaction failure rollback result is invalid")
        if rollback_succeeded:
            if rollback_error is not None:
                raise ValueError("live transaction failure rollback error is invalid")
        else:
            rollback_error = _safe_text(rollback_error, label="rollback_error")
        manual_recovery = value.get("manual_recovery_required")
        if not isinstance(manual_recovery, bool) or manual_recovery is rollback_succeeded:
            raise ValueError("live transaction failure recovery state is invalid")
    journal_path = _safe_text(value.get("journal_path"), label="journal_path")
    source_receipts = value.get("source_receipts")
    if not isinstance(source_receipts, Mapping) or set(source_receipts) != {
        "gate_receipt_digest",
        "operation_bundle_digest",
        "authorization_digest",
    }:
        raise ValueError("live transaction failure source receipts are invalid")
    normalized_sources = {
        key: _digest(source_receipts.get(key), label=key)
        for key in source_receipts
    }
    expected_boundary = {
        "managed_region_only": True,
        "provider_identifiers_not_returned": True,
        "failed_apply_is_fail_closed": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("live transaction failure boundary is invalid")
    declared = _digest(value.get("receipt_digest"), label="receipt_digest")
    if declared != _receipt_digest(value):
        raise ValueError("live transaction failure receipt digest mismatch")
    return {
        **dict(value),
        "transaction_id": transaction_id,
        "surface_alias": alias,
        "region_id": region_id,
        "operation_count": operation_count,
        "applied_operation_ids": normalized_ids,
        "failure": failure,
        "rollback_error": rollback_error,
        "journal_path": journal_path,
        "source_receipts": normalized_sources,
        "receipt_digest": declared,
    }


def load_live_transaction_receipt(path: Path) -> dict[str, Any]:
    return validate_live_transaction_receipt(
        _read_json(path, label="live transaction receipt", owner_only=True)
    )


def validate_live_restore_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "ok",
        "mutation_attempted",
        "live_restore_attempted",
        "transaction_id",
        "surface_alias",
        "region_id",
        "restored_operation_count",
        "restored_snapshot_digest",
        "restored_dsl_digest",
        "restored_to_before_snapshot",
        "semantic_verification_passed",
        "journal_path",
        "source_receipts",
        "boundary",
        "receipt_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("live restore receipt fields are invalid")
    if value.get("schema_version") != LIVE_RESTORE_SCHEMA:
        raise ValueError("live restore receipt has an unsupported schema")
    for field in (
        "ok",
        "mutation_attempted",
        "live_restore_attempted",
        "restored_to_before_snapshot",
        "semantic_verification_passed",
    ):
        if value.get(field) is not True:
            raise ValueError(f"live restore receipt {field} is invalid")
    transaction_id = _safe_id(value.get("transaction_id"), label="transaction_id")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    restored_operation_count = value.get("restored_operation_count")
    if (
        isinstance(restored_operation_count, bool)
        or not isinstance(restored_operation_count, int)
        or restored_operation_count < 1
    ):
        raise ValueError("live restore receipt operation count is invalid")
    restored_snapshot_digest = _digest(
        value.get("restored_snapshot_digest"), label="restored_snapshot_digest"
    )
    restored_dsl_digest = _digest(
        value.get("restored_dsl_digest"), label="restored_dsl_digest"
    )
    journal_path = _safe_text(value.get("journal_path"), label="journal_path")
    source_receipts = value.get("source_receipts")
    if not isinstance(source_receipts, Mapping) or set(source_receipts) != {
        "transaction_receipt_digest",
        "journal_digest",
    }:
        raise ValueError("live restore source receipt fields are invalid")
    normalized_sources = {
        key: _digest(source_receipts.get(key), label=key)
        for key in source_receipts
    }
    expected_boundary = {
        "managed_region_only": True,
        "provider_identifiers_not_returned": True,
        "inverse_operations_only": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("live restore receipt boundary is invalid")
    declared = _digest(value.get("receipt_digest"), label="receipt_digest")
    if declared != _receipt_digest(value):
        raise ValueError("live restore receipt digest mismatch")
    return {
        **dict(value),
        "transaction_id": transaction_id,
        "surface_alias": alias,
        "region_id": region_id,
        "restored_operation_count": restored_operation_count,
        "restored_snapshot_digest": restored_snapshot_digest,
        "restored_dsl_digest": restored_dsl_digest,
        "journal_path": journal_path,
        "source_receipts": normalized_sources,
        "receipt_digest": declared,
    }


def validate_live_restore_failure_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "ok",
        "mutation_attempted",
        "live_restore_attempted",
        "transaction_id",
        "surface_alias",
        "region_id",
        "failure",
        "rollback_to_after_attempted",
        "rollback_to_after_succeeded",
        "rollback_to_after_error",
        "still_restore_ready",
        "journal_path",
        "source_receipts",
        "boundary",
        "receipt_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("live restore failure receipt fields are invalid")
    if value.get("schema_version") != LIVE_RESTORE_SCHEMA:
        raise ValueError("live restore failure receipt has an unsupported schema")
    if value.get("ok") is not False:
        raise ValueError("live restore failure receipt ok flag is invalid")
    for field in (
        "mutation_attempted",
        "live_restore_attempted",
        "rollback_to_after_attempted",
    ):
        if value.get(field) is not True:
            raise ValueError(f"live restore failure receipt {field} is invalid")
    recovery_ok = value.get("rollback_to_after_succeeded")
    still_ready = value.get("still_restore_ready")
    if not isinstance(recovery_ok, bool) or still_ready is not recovery_ok:
        raise ValueError("live restore failure recovery state is invalid")
    recovery_error = value.get("rollback_to_after_error")
    if recovery_ok:
        if recovery_error is not None:
            raise ValueError("live restore failure recovery error is invalid")
    elif not isinstance(recovery_error, str) or not recovery_error.strip():
        raise ValueError("live restore failure recovery error is invalid")
    transaction_id = _safe_id(value.get("transaction_id"), label="transaction_id")
    alias = _safe_id(value.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(value.get("region_id"), label="region_id")
    failure = _safe_text(value.get("failure"), label="failure")
    journal_path = _safe_text(value.get("journal_path"), label="journal_path")
    source_receipts = value.get("source_receipts")
    if not isinstance(source_receipts, Mapping) or set(source_receipts) != {
        "transaction_receipt_digest",
        "journal_digest",
    }:
        raise ValueError("live restore failure source receipt fields are invalid")
    normalized_sources = {
        key: _digest(source_receipts.get(key), label=key)
        for key in source_receipts
    }
    expected_boundary = {
        "managed_region_only": True,
        "provider_identifiers_not_returned": True,
        "failed_restore_is_fail_closed": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("live restore failure receipt boundary is invalid")
    declared = _digest(value.get("receipt_digest"), label="receipt_digest")
    if declared != _receipt_digest(value):
        raise ValueError("live restore failure receipt digest mismatch")
    return {
        **dict(value),
        "transaction_id": transaction_id,
        "surface_alias": alias,
        "region_id": region_id,
        "failure": failure,
        "journal_path": journal_path,
        "source_receipts": normalized_sources,
        "receipt_digest": declared,
    }


def load_live_restore_receipt(path: Path) -> dict[str, Any]:
    value = _read_json(path, label="live restore receipt", owner_only=True)
    if value.get("ok") is True:
        return validate_live_restore_receipt(value)
    return validate_live_restore_failure_receipt(value)


def kill_switch_status(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("live apply kill switch path is unsafe")
    enabled = candidate.exists()
    reason = None
    enabled_at = None
    if enabled:
        value = _read_json(candidate, label="live apply kill switch", owner_only=True)
        if value.get("schema_version") != KILL_SWITCH_SCHEMA or value.get("enabled") is not True:
            raise ValueError("live apply kill switch is invalid")
        reason = value.get("reason") if isinstance(value.get("reason"), str) else None
        enabled_at = value.get("enabled_at") if isinstance(value.get("enabled_at"), str) else None
    return {
        "schema_version": "typed-region-live-kill-switch-status.v1",
        "enabled": enabled,
        "reason": reason,
        "enabled_at": enabled_at,
        "path": str(candidate),
        "mutation_attempted": False,
    }


def enable_kill_switch(path: Path, *, reason: str, now: datetime | None = None) -> dict[str, Any]:
    text = _safe_text(reason, label="kill switch reason")
    current = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    value = {
        "schema_version": KILL_SWITCH_SCHEMA,
        "enabled": True,
        "reason": text,
        "enabled_at": current.isoformat().replace("+00:00", "Z"),
    }
    write_live_artifact(path, value, label="live apply kill switch")
    result = kill_switch_status(path)
    result["mutation_attempted"] = True
    return result


def disable_kill_switch(path: Path, *, confirmation: str) -> dict[str, Any]:
    if confirmation != "ENABLE_LIVE_APPLY":
        raise ValueError("kill switch disable confirmation is invalid")
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("live apply kill switch path is unsafe")
    if candidate.exists():
        metadata = candidate.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise ValueError("live apply kill switch path is unsafe")
        candidate.unlink()
        directory = os.open(candidate.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    result = kill_switch_status(candidate)
    result["mutation_attempted"] = True
    return result


def _snapshot_dict(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise ValueError("provider snapshot receipt is invalid")
    result = dict(value)
    _digest(result.get("content_digest"), label="provider snapshot content_digest")
    if result.get("repeatability_verified") is not True:
        raise ValueError("provider snapshot repeatability is unverified")
    if result.get("sanitized_references") is not True:
        raise ValueError("provider snapshot references are not sanitized")
    return result


def _line_for(text: str, needle: str) -> str:
    matches = [line for line in text.splitlines() if needle in line]
    if len(matches) != 1:
        raise ValueError("managed-region operation does not match exactly one DSL line")
    return matches[0]


def _verify_before_dsl(dsl: str, operations: Sequence[Mapping[str, str]], marker: str) -> None:
    for operation in operations:
        old_text = operation["old_text"]
        new_text = operation["new_text"]
        if dsl.count(old_text) != 1:
            raise ValueError(f"operation {operation['operation_id']} old text is not unique")
        if dsl.count(new_text) != 0:
            raise ValueError(f"operation {operation['operation_id']} new text already exists")
        if marker not in _line_for(dsl, old_text):
            raise ValueError(f"operation {operation['operation_id']} is outside the managed region")


def _expected_after_dsl(
    before_dsl: str, operations: Sequence[Mapping[str, str]]
) -> str:
    expected = before_dsl
    for operation in operations:
        if expected.count(operation["old_text"]) != 1:
            raise ValueError(
                f"operation {operation['operation_id']} cannot compile an exact after-state"
            )
        expected = expected.replace(
            operation["old_text"], operation["new_text"], 1
        )
    return expected


def _verify_after_dsl(dsl: str, operations: Sequence[Mapping[str, str]], marker: str) -> None:
    for operation in operations:
        old_text = operation["old_text"]
        new_text = operation["new_text"]
        if dsl.count(old_text) != 0 or dsl.count(new_text) != 1:
            raise ValueError(f"operation {operation['operation_id']} postflight mismatch")
        if marker not in _line_for(dsl, new_text):
            raise ValueError(f"operation {operation['operation_id']} lost managed-region scope")


def _verify_restored_dsl(dsl: str, operations: Sequence[Mapping[str, str]], marker: str) -> None:
    for operation in operations:
        old_text = operation["old_text"]
        new_text = operation["new_text"]
        if dsl.count(old_text) != 1 or dsl.count(new_text) != 0:
            raise ValueError(f"operation {operation['operation_id']} restore mismatch")
        if marker not in _line_for(dsl, old_text):
            raise ValueError(f"operation {operation['operation_id']} restore lost scope")


def _safe_journal_root(path: Path) -> Path:
    root = path.expanduser().absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("live transaction journal root is unsafe")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def _write_journal(path: Path, value: dict[str, Any]) -> None:
    value["journal_digest"] = _manifest_digest(value, "journal_digest")
    write_live_artifact(path, value, label="live transaction journal")


def _load_journal(path: Path) -> dict[str, Any]:
    value = _read_json(path, label="live transaction journal", owner_only=True)
    if value.get("schema_version") != LIVE_JOURNAL_SCHEMA:
        raise ValueError("live transaction journal has an unsupported schema")
    declared = _digest(value.get("journal_digest"), label="journal_digest")
    if declared != _manifest_digest(value, "journal_digest"):
        raise ValueError("live transaction journal digest mismatch")
    return value


def _sanitized_mutation_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "success",
        "created_count",
        "updated_count",
        "deleted_count",
        "result_dsl_digest",
        "sanitized_references",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("provider mutation receipt fields are invalid")
    result = dict(value)
    if result.get("success") is not True:
        raise ValueError("provider mutation did not succeed")
    if result.get("sanitized_references") is not True:
        raise ValueError("provider mutation receipt is not sanitized")
    counts: dict[str, int] = {}
    for key in ("created_count", "updated_count", "deleted_count"):
        count = result.get(key)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"provider mutation receipt {key} is invalid")
        counts[key] = count
    if counts != {"created_count": 0, "updated_count": 1, "deleted_count": 0}:
        raise ValueError("provider mutation receipt effect counts are invalid")
    result["result_dsl_digest"] = _digest(
        result.get("result_dsl_digest"), label="result_dsl_digest"
    )
    if _FORBIDDEN_REFERENCE.search(json.dumps(result, ensure_ascii=False)):
        raise ValueError("provider mutation receipt leaked a provider reference")
    return result


async def _rollback(
    *,
    provider: ManagedRegionProvider,
    alias: str,
    operations: Sequence[Mapping[str, str]],
    marker: str,
    expected_snapshot_digest: str,
    expected_dsl_digest: str,
    snapshot_path: Path,
) -> tuple[bool, str | None]:
    try:
        current_dsl = await provider.read_dsl(alias=alias)
        observed_applied: list[Mapping[str, str]] = []
        for operation in operations:
            old_count = current_dsl.count(operation["old_text"])
            new_count = current_dsl.count(operation["new_text"])
            if old_count == 1 and new_count == 0:
                continue
            if old_count == 0 and new_count == 1:
                if marker not in _line_for(current_dsl, operation["new_text"]):
                    raise ValueError("rollback observed an out-of-scope applied operation")
                observed_applied.append(operation)
                continue
            raise ValueError("rollback could not classify the current managed-region state")
        for operation in reversed(observed_applied):
            receipt = await provider.replace_text(
                alias=alias,
                old_text=operation["new_text"],
                new_text=operation["old_text"],
            )
            _sanitized_mutation_receipt(receipt)
        restored_dsl = await provider.read_dsl(alias=alias)
        _verify_restored_dsl(restored_dsl, operations, marker)
        restored_dsl_digest = hashlib.sha256(restored_dsl.encode("utf-8")).hexdigest()
        if restored_dsl_digest != expected_dsl_digest:
            raise ValueError("rollback DSL digest mismatch")
        restored_snapshot = _snapshot_dict(
            await provider.snapshot(alias=alias, output_path=snapshot_path)
        )
        if restored_snapshot["content_digest"] != expected_snapshot_digest:
            raise ValueError("rollback snapshot digest mismatch")
    except Exception as exc:  # rollback evidence must survive any provider failure
        return False, redact_text(exc)
    return True, None


def _persist_receipt(
    *,
    canonical_path: Path,
    requested_path: Path,
    value: Mapping[str, Any],
    label: str,
) -> None:
    write_live_artifact(canonical_path, value, label=label)
    if requested_path.expanduser().absolute() != canonical_path.expanduser().absolute():
        write_live_artifact(requested_path, value, label=label)


def _execution_authorization_window(
    authorization: Mapping[str, Any], *, now: datetime
) -> tuple[datetime, datetime]:
    approved_at = _parse_timestamp(authorization.get("approved_at"), label="approved_at")
    expires_at = _parse_timestamp(authorization.get("expires_at"), label="expires_at")
    if now < approved_at:
        raise ValueError("live authorization is not active yet")
    if now >= expires_at:
        raise ValueError("live authorization has expired")
    return approved_at, expires_at


async def execute_live_apply(
    *,
    plan: Mapping[str, Any],
    provider: ManagedRegionProvider,
    journal_root: Path,
    kill_switch_path: Path,
    output_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan = validate_live_apply_plan(plan)
    declared_plan_digest = plan["plan_digest"]

    authorization = plan.get("authorization")
    if not isinstance(authorization, Mapping):
        raise ValueError("live apply plan authorization is missing")
    current = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    _approved_at, authorization_expires_at = _execution_authorization_window(
        authorization, now=current
    )
    transaction_id = _safe_id(
        authorization.get("authorization_id"), label="transaction_id"
    )
    source_receipts = plan.get("source_receipts")
    if not isinstance(source_receipts, Mapping):
        raise ValueError("live apply plan source receipts are missing")
    authorization_digest = _digest(
        source_receipts.get("authorization_digest"), label="authorization_digest"
    )

    if kill_switch_status(kill_switch_path)["enabled"]:
        raise ValueError("live apply kill switch is enabled")
    capabilities = provider.capabilities()
    missing = sorted(_REQUIRED_CAPABILITIES - set(capabilities))
    if missing:
        raise ValueError(f"live provider capabilities missing: {', '.join(missing)}")

    alias = _safe_id(plan.get("surface_alias"), label="surface_alias")
    region_id = _safe_id(plan.get("region_id"), label="region_id")
    marker = _safe_text(plan.get("marker"), label="marker")
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("live apply plan operations are invalid")
    expected_snapshot_digest = _digest(
        plan.get("expected_snapshot_digest"), label="expected_snapshot_digest"
    )

    root = _safe_journal_root(journal_root)
    directory = root / authorization_digest
    if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents):
        raise ValueError("live transaction directory is unsafe")
    journal_path = directory / "journal.json"
    canonical_receipt_path = directory / "transaction-receipt.json"
    receipt_path = live_artifact_destination(
        output_path, label="live transaction receipt"
    )
    try:
        directory.mkdir(mode=0o700, exist_ok=False)
        os.chmod(directory, 0o700)
        created_directory = True
    except FileExistsError:
        created_directory = False
    if not created_directory:
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError("live transaction directory is unsafe")
        if not journal_path.exists():
            raise ValueError("live transaction reservation is incomplete or active")
        existing = _load_journal(journal_path)
        if existing.get("plan_digest") != declared_plan_digest:
            raise ValueError("authorization digest is bound to a different live plan")
        if existing.get("status") == "committed":
            existing_receipt = validate_live_transaction_receipt(
                _read_json(
                    canonical_receipt_path,
                    label="canonical live transaction receipt",
                    owner_only=True,
                )
            )
            existing_receipt["replayed_without_mutation"] = True
            return existing_receipt
        if existing.get("status") in {
            "preflight_failed",
            "rolled_back",
            "rollback_failed",
            "restored",
        }:
            raise ValueError("single-use live authorization was already consumed")
        raise ValueError("live transaction is already active")

    before_path = directory / "before.json"
    after_path = directory / "after.json"
    rollback_path = directory / "rollback.json"
    journal: dict[str, Any] = {
        "schema_version": LIVE_JOURNAL_SCHEMA,
        "transaction_id": transaction_id,
        "authorization_digest": authorization_digest,
        "status": "reserved",
        "surface_alias": alias,
        "region_id": region_id,
        "marker": marker,
        "plan_digest": declared_plan_digest,
        "expected_snapshot_digest": expected_snapshot_digest,
        "before_snapshot_digest": None,
        "before_dsl_digest": None,
        "operations": operations,
        "applied_operation_ids": [],
        "reserved_at": current.isoformat().replace("+00:00", "Z"),
        "prepared_at": None,
        "after_snapshot_digest": None,
        "after_dsl_digest": None,
        "failure": None,
        "rollback": None,
    }
    _write_journal(journal_path, journal)

    try:
        before = _snapshot_dict(await provider.snapshot(alias=alias, output_path=before_path))
        if before.get("board_alias") != alias:
            raise ValueError("live before snapshot alias mismatch")
        if before["content_digest"] != expected_snapshot_digest:
            raise ValueError("live before snapshot revision mismatch")
        before_dsl = await provider.read_dsl(alias=alias)
        _verify_before_dsl(before_dsl, operations, marker)
        before_dsl_digest = hashlib.sha256(before_dsl.encode("utf-8")).hexdigest()
    except Exception as exc:
        journal["status"] = "preflight_failed"
        journal["failure"] = redact_text(exc)
        _write_journal(journal_path, journal)
        failure = {
            "schema_version": LIVE_TRANSACTION_SCHEMA,
            "ok": False,
            "mutation_attempted": False,
            "live_apply_attempted": True,
            "transaction_id": transaction_id,
            "surface_alias": alias,
            "region_id": region_id,
            "operation_count": len(operations),
            "applied_operation_ids": [],
            "failure": redact_text(exc),
            "rollback_attempted": False,
            "rollback_succeeded": None,
            "rollback_error": None,
            "restore_ready": False,
            "journal_path": str(journal_path),
            "source_receipts": dict(source_receipts),
            "boundary": {
                "managed_region_only": True,
                "provider_identifiers_not_returned": True,
                "failed_apply_is_fail_closed": True,
            },
        }
        failure["receipt_digest"] = _receipt_digest(failure)
        _persist_receipt(
            canonical_path=canonical_receipt_path,
            requested_path=receipt_path,
            value=failure,
            label="live transaction receipt",
        )
        failure["output_path"] = str(receipt_path)
        return failure

    journal["status"] = "prepared"
    journal["before_snapshot_digest"] = before["content_digest"]
    journal["before_dsl_digest"] = before_dsl_digest
    journal["prepared_at"] = current.isoformat().replace("+00:00", "Z")
    _write_journal(journal_path, journal)

    applied_ids: list[str] = []
    mutation_receipts: list[dict[str, Any]] = []
    mutation_calls = 0
    expected_intermediate_dsl = before_dsl
    try:
        for operation in operations:
            if kill_switch_status(kill_switch_path)["enabled"]:
                raise ValueError("live apply kill switch was enabled during execution")
            operation_time = (
                current if now is not None else datetime.now(UTC).astimezone(UTC)
            )
            if operation_time >= authorization_expires_at:
                raise ValueError("live authorization expired during execution")
            mutation_calls += 1
            raw_receipt = await provider.replace_text(
                alias=alias,
                old_text=operation["old_text"],
                new_text=operation["new_text"],
            )
            receipt = _sanitized_mutation_receipt(raw_receipt)
            expected_intermediate_dsl = expected_intermediate_dsl.replace(
                operation["old_text"], operation["new_text"], 1
            )
            expected_intermediate_digest = hashlib.sha256(
                expected_intermediate_dsl.encode("utf-8")
            ).hexdigest()
            if receipt["result_dsl_digest"] != expected_intermediate_digest:
                raise ValueError(
                    f"operation {operation['operation_id']} provider DSL digest mismatch"
                )
            applied_ids.append(operation["operation_id"])
            mutation_receipts.append(receipt)
            journal["status"] = "applying"
            journal["applied_operation_ids"] = list(applied_ids)
            _write_journal(journal_path, journal)

        after_dsl = await provider.read_dsl(alias=alias)
        _verify_after_dsl(after_dsl, operations, marker)
        expected_after_dsl = _expected_after_dsl(before_dsl, operations)
        if after_dsl != expected_after_dsl:
            raise ValueError("live apply changed DSL outside the declared operations")
        after_dsl_digest = hashlib.sha256(after_dsl.encode("utf-8")).hexdigest()
        if after_dsl_digest == before_dsl_digest:
            raise ValueError("live apply did not change the managed-region DSL")
        after = _snapshot_dict(await provider.snapshot(alias=alias, output_path=after_path))
        if after.get("board_alias") != alias:
            raise ValueError("live after snapshot alias mismatch")
        if after["content_digest"] == expected_snapshot_digest:
            raise ValueError("live after snapshot did not change")
        _verify_after_dsl(after_dsl, operations, marker)
    except Exception as exc:
        rollback_ok, rollback_error = await _rollback(
            provider=provider,
            alias=alias,
            operations=operations,
            marker=marker,
            expected_snapshot_digest=expected_snapshot_digest,
            expected_dsl_digest=before_dsl_digest,
            snapshot_path=rollback_path,
        )
        journal["status"] = "rolled_back" if rollback_ok else "rollback_failed"
        journal["failure"] = redact_text(exc)
        journal["rollback"] = {"ok": rollback_ok, "error": rollback_error}
        _write_journal(journal_path, journal)
        failure = {
            "schema_version": LIVE_TRANSACTION_SCHEMA,
            "ok": False,
            "mutation_attempted": mutation_calls > 0,
            "live_apply_attempted": True,
            "transaction_id": transaction_id,
            "surface_alias": alias,
            "region_id": region_id,
            "operation_count": len(operations),
            "applied_operation_ids": applied_ids,
            "failure": redact_text(exc),
            "rollback_attempted": mutation_calls > 0,
            "rollback_succeeded": rollback_ok,
            "rollback_error": rollback_error,
            "restore_ready": False,
            "manual_recovery_required": not rollback_ok,
            "journal_path": str(journal_path),
            "source_receipts": dict(source_receipts),
            "boundary": {
                "managed_region_only": True,
                "provider_identifiers_not_returned": True,
                "failed_apply_is_fail_closed": True,
            },
        }
        failure["receipt_digest"] = _receipt_digest(failure)
        _persist_receipt(
            canonical_path=canonical_receipt_path,
            requested_path=receipt_path,
            value=failure,
            label="live transaction receipt",
        )
        failure["output_path"] = str(receipt_path)
        return failure

    journal["status"] = "committed"
    journal["after_snapshot_digest"] = after["content_digest"]
    journal["after_dsl_digest"] = after_dsl_digest
    journal["applied_operation_ids"] = list(applied_ids)
    journal["committed_at"] = current.isoformat().replace("+00:00", "Z")
    _write_journal(journal_path, journal)
    result = {
        "schema_version": LIVE_TRANSACTION_SCHEMA,
        "ok": True,
        "mutation_attempted": True,
        "live_apply_attempted": True,
        "transaction_id": transaction_id,
        "surface_alias": alias,
        "region_id": region_id,
        "operation": plan["operation"],
        "operation_count": len(operations),
        "applied_operation_ids": applied_ids,
        "before_snapshot_digest": before["content_digest"],
        "after_snapshot_digest": after["content_digest"],
        "before_dsl_digest": before_dsl_digest,
        "after_dsl_digest": after_dsl_digest,
        "semantic_verification_passed": True,
        "idempotency_verified": True,
        "postflight_verified": True,
        "restore_ready": True,
        "mutation_receipts": mutation_receipts,
        "journal_path": str(journal_path),
        "committed_journal_digest": journal["journal_digest"],
        "source_receipts": dict(source_receipts),
        "boundary": {
            "managed_region_only": True,
            "exact_text_replacement_only": True,
            "provider_identifiers_not_returned": True,
            "single_use_authorization_consumed": True,
        },
    }
    result["receipt_digest"] = _receipt_digest(result)
    result = validate_live_transaction_receipt(result)
    _persist_receipt(
        canonical_path=canonical_receipt_path,
        requested_path=receipt_path,
        value=result,
        label="live transaction receipt",
    )
    result["output_path"] = str(receipt_path)
    return result


async def _recover_restore_to_after(
    *,
    provider: ManagedRegionProvider,
    alias: str,
    operations: Sequence[Mapping[str, str]],
    marker: str,
    expected_after_digest: str,
    expected_after_dsl_digest: str,
    snapshot_path: Path,
) -> tuple[bool, str | None]:
    try:
        current_dsl = await provider.read_dsl(alias=alias)
        reverted: list[Mapping[str, str]] = []
        for operation in operations:
            old_count = current_dsl.count(operation["old_text"])
            new_count = current_dsl.count(operation["new_text"])
            if old_count == 0 and new_count == 1:
                continue
            if old_count == 1 and new_count == 0:
                if marker not in _line_for(current_dsl, operation["old_text"]):
                    raise ValueError("restore recovery observed an out-of-scope operation")
                reverted.append(operation)
                continue
            raise ValueError("restore recovery could not classify managed-region state")
        for operation in reverted:
            raw = await provider.replace_text(
                alias=alias,
                old_text=operation["old_text"],
                new_text=operation["new_text"],
            )
            _sanitized_mutation_receipt(raw)
        recovered_dsl = await provider.read_dsl(alias=alias)
        _verify_after_dsl(recovered_dsl, operations, marker)
        recovered_dsl_digest = hashlib.sha256(recovered_dsl.encode("utf-8")).hexdigest()
        if recovered_dsl_digest != expected_after_dsl_digest:
            raise ValueError("restore recovery DSL digest mismatch")
        recovered = _snapshot_dict(
            await provider.snapshot(alias=alias, output_path=snapshot_path)
        )
        if recovered["content_digest"] != expected_after_digest:
            raise ValueError("restore recovery snapshot digest mismatch")
    except Exception as exc:
        return False, redact_text(exc)
    return True, None


async def restore_live_apply(
    *,
    transaction_receipt_path: Path,
    provider: ManagedRegionProvider,
    output_path: Path,
) -> dict[str, Any]:
    transaction = validate_live_transaction_receipt(
        _read_json(
            transaction_receipt_path,
            label="live transaction receipt",
            owner_only=True,
        )
    )
    declared = transaction["receipt_digest"]
    capabilities = provider.capabilities()
    missing = sorted(_REQUIRED_CAPABILITIES - set(capabilities))
    if missing:
        raise ValueError(f"live provider capabilities missing: {', '.join(missing)}")

    journal_path = Path(str(transaction.get("journal_path", "")))
    journal = _load_journal(journal_path)
    canonical_restore_path = journal_path.parent / "restore-receipt.json"
    requested_restore_path = live_artifact_destination(
        output_path, label="live restore receipt"
    )
    if journal.get("status") == "restored":
        existing = validate_live_restore_receipt(
            _read_json(
                canonical_restore_path,
                label="canonical live restore receipt",
                owner_only=True,
            )
        )
        if existing["source_receipts"]["journal_digest"] != journal["journal_digest"]:
            raise ValueError("live restore receipt and restored journal digest mismatch")
        existing["replayed_without_mutation"] = True
        return existing
    if journal.get("status") != "committed":
        raise ValueError("live transaction journal is not committed")
    prior_failure: dict[str, Any] | None = None
    if canonical_restore_path.exists():
        prior_value = _read_json(
            canonical_restore_path,
            label="canonical live restore receipt",
            owner_only=True,
        )
        if prior_value.get("ok") is not False:
            raise ValueError("committed journal has an invalid canonical restore receipt")
        prior_failure = validate_live_restore_failure_receipt(prior_value)
    journal_digest_matches_transaction = (
        journal.get("journal_digest") == transaction.get("committed_journal_digest")
    )
    journal_digest_matches_retry = bool(
        prior_failure
        and prior_failure["still_restore_ready"] is True
        and prior_failure["transaction_id"] == transaction.get("transaction_id")
        and prior_failure["surface_alias"] == journal.get("surface_alias")
        and prior_failure["region_id"] == journal.get("region_id")
        and prior_failure["source_receipts"]["transaction_receipt_digest"] == declared
        and prior_failure["source_receipts"]["journal_digest"]
        == journal.get("journal_digest")
        and prior_failure["journal_path"] == str(journal_path)
    )
    if not (journal_digest_matches_transaction or journal_digest_matches_retry):
        raise ValueError("live transaction receipt and committed journal digest mismatch")
    if journal.get("transaction_id") != transaction.get("transaction_id"):
        raise ValueError("live transaction receipt and journal id mismatch")
    if journal.get("after_snapshot_digest") != transaction.get("after_snapshot_digest"):
        raise ValueError("live transaction receipt and journal after-state mismatch")

    alias = _safe_id(journal.get("surface_alias"), label="journal.surface_alias")
    marker = _safe_text(journal.get("marker"), label="journal.marker")
    operations = journal.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("live transaction journal operations are invalid")
    expected_after_digest = _digest(
        journal.get("after_snapshot_digest"), label="journal.after_snapshot_digest"
    )
    expected_before_digest = _digest(
        journal.get("before_snapshot_digest"), label="journal.before_snapshot_digest"
    )
    expected_after_dsl_digest = _digest(
        journal.get("after_dsl_digest"), label="journal.after_dsl_digest"
    )
    expected_before_dsl_digest = _digest(
        journal.get("before_dsl_digest"), label="journal.before_dsl_digest"
    )

    current_snapshot_path = journal_path.parent / "restore-current.json"
    current_snapshot = _snapshot_dict(
        await provider.snapshot(alias=alias, output_path=current_snapshot_path)
    )
    if current_snapshot.get("board_alias") != alias:
        raise ValueError("live restore current snapshot alias mismatch")
    if current_snapshot["content_digest"] != expected_after_digest:
        raise ValueError("live restore blocked by external board drift")
    current_dsl = await provider.read_dsl(alias=alias)
    _verify_after_dsl(current_dsl, operations, marker)
    current_dsl_digest = hashlib.sha256(current_dsl.encode("utf-8")).hexdigest()
    if current_dsl_digest != expected_after_dsl_digest:
        raise ValueError("live restore blocked by external DSL drift")

    restore_calls = 0
    try:
        for operation in reversed(operations):
            restore_calls += 1
            raw = await provider.replace_text(
                alias=alias,
                old_text=operation["new_text"],
                new_text=operation["old_text"],
            )
            _sanitized_mutation_receipt(raw)
        restored_dsl = await provider.read_dsl(alias=alias)
        _verify_restored_dsl(restored_dsl, operations, marker)
        restored_dsl_digest = hashlib.sha256(restored_dsl.encode("utf-8")).hexdigest()
        if restored_dsl_digest != expected_before_dsl_digest:
            raise ValueError("live restore DSL digest mismatch")
        restored_path = journal_path.parent / "restored.json"
        restored = _snapshot_dict(
            await provider.snapshot(alias=alias, output_path=restored_path)
        )
        if restored["content_digest"] != expected_before_digest:
            raise ValueError("live restore snapshot digest mismatch")
    except Exception as exc:
        recovery_ok, recovery_error = await _recover_restore_to_after(
            provider=provider,
            alias=alias,
            operations=operations,
            marker=marker,
            expected_after_digest=expected_after_digest,
            expected_after_dsl_digest=expected_after_dsl_digest,
            snapshot_path=journal_path.parent / "restore-recovery.json",
        )
        journal["status"] = "committed" if recovery_ok else "restore_recovery_failed"
        journal["restore_failure"] = redact_text(exc)
        journal["restore_recovery"] = {
            "ok": recovery_ok,
            "error": recovery_error,
        }
        _write_journal(journal_path, journal)
        failure = {
            "schema_version": LIVE_RESTORE_SCHEMA,
            "ok": False,
            "mutation_attempted": restore_calls > 0,
            "live_restore_attempted": True,
            "transaction_id": journal["transaction_id"],
            "surface_alias": alias,
            "region_id": journal["region_id"],
            "failure": redact_text(exc),
            "rollback_to_after_attempted": restore_calls > 0,
            "rollback_to_after_succeeded": recovery_ok,
            "rollback_to_after_error": recovery_error,
            "still_restore_ready": recovery_ok,
            "journal_path": str(journal_path),
            "source_receipts": {
                "transaction_receipt_digest": declared,
                "journal_digest": journal["journal_digest"],
            },
            "boundary": {
                "managed_region_only": True,
                "provider_identifiers_not_returned": True,
                "failed_restore_is_fail_closed": True,
            },
        }
        failure["receipt_digest"] = _receipt_digest(failure)
        _persist_receipt(
            canonical_path=canonical_restore_path,
            requested_path=requested_restore_path,
            value=failure,
            label="live restore receipt",
        )
        failure["output_path"] = str(requested_restore_path)
        return failure

    journal["status"] = "restored"
    journal["restored_snapshot_digest"] = restored["content_digest"]
    journal["restored_dsl_digest"] = hashlib.sha256(restored_dsl.encode("utf-8")).hexdigest()
    journal["restored_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    _write_journal(journal_path, journal)
    result = {
        "schema_version": LIVE_RESTORE_SCHEMA,
        "ok": True,
        "mutation_attempted": True,
        "live_restore_attempted": True,
        "transaction_id": journal["transaction_id"],
        "surface_alias": alias,
        "region_id": journal["region_id"],
        "restored_operation_count": len(operations),
        "restored_snapshot_digest": restored["content_digest"],
        "restored_dsl_digest": journal["restored_dsl_digest"],
        "restored_to_before_snapshot": True,
        "semantic_verification_passed": True,
        "journal_path": str(journal_path),
        "source_receipts": {
            "transaction_receipt_digest": declared,
            "journal_digest": journal["journal_digest"],
        },
        "boundary": {
            "managed_region_only": True,
            "provider_identifiers_not_returned": True,
            "inverse_operations_only": True,
        },
    }
    result["receipt_digest"] = _receipt_digest(result)
    result = validate_live_restore_receipt(result)
    _persist_receipt(
        canonical_path=canonical_restore_path,
        requested_path=requested_restore_path,
        value=result,
        label="live restore receipt",
    )
    result["output_path"] = str(requested_restore_path)
    return result


def write_live_apply_plan(path: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    destination = write_live_artifact(path, plan, label="live apply plan")
    result = dict(plan)
    result["output_path"] = str(destination)
    return result


def compile_live_operation_bundle_template(
    *, region: RegionDeclaration, bundle_id: str = "sw009-live-bundle-edit-me"
) -> dict[str, Any]:
    if region.mode != "managed":
        raise ValueError("live operation drafts require a managed region")
    marker = f"schauwerk-region:{region.region_id}"
    value = {
        "schema_version": LIVE_OPERATION_DRAFT_SCHEMA,
        "bundle_id": bundle_id,
        "surface_alias": region.surface_alias,
        "region_id": region.region_id,
        "expected_snapshot_digest": region.expected_snapshot_digest,
        "operation": "render-update",
        "marker": marker,
        "operations": [
            {
                "operation_id": "replace-reviewed-text",
                "action": "replace-text",
                "region_id": region.region_id,
                "old_text": f"[{marker}] OLD REVIEWED TEXT",
                "new_text": f"[{marker}] NEW REVIEWED TEXT",
            }
        ],
        "boundary": {
            "managed_region_only": True,
            "exact_text_replacement_only": True,
            "provider_references_prohibited": True,
            "review_required": True,
            "restore_required": True,
        },
    }
    return value


def compile_live_authorization(
    *,
    gate_receipt: Mapping[str, Any],
    operation_bundle: Mapping[str, Any],
    approved_by: str,
    approval_reference: str,
    confirmation: str,
    approved_at: datetime,
    expires_at: datetime,
    authorization_id: str = "sw009-live-authorization-edit-me",
) -> dict[str, Any]:
    if confirmation != "APPROVE_LIVE_APPLY":
        raise ValueError("live authorization confirmation is invalid")
    gate, declaration = _validate_gate_receipt(gate_receipt)
    bundle = validate_live_operation_bundle(operation_bundle)
    value = {
        "schema_version": LIVE_AUTHORIZATION_SCHEMA,
        "authorization_id": authorization_id,
        "gate_receipt_digest": gate["receipt_digest"],
        "operation_bundle_digest": bundle["bundle_digest"],
        "surface_alias": declaration.surface_alias,
        "region_id": declaration.region_id,
        "expected_snapshot_digest": declaration.expected_snapshot_digest,
        "approved_by": approved_by,
        "approved_at": approved_at.astimezone(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "expires_at": expires_at.astimezone(UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "approval_reference": approval_reference,
        "approved": True,
        "boundary": {
            "single_use": True,
            "explicit_live_apply": True,
            "operation_bundle_bound": True,
            "gate_receipt_bound": True,
        },
    }
    value["authorization_digest"] = _manifest_digest(value, "authorization_digest")
    return value
