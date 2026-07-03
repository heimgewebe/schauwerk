"""Dry-run typed operator plans for managed Schauwerk regions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

_ALLOWED_MODES = {
    "manual",
    "cooperative",
    "suggest-only",
    "approval-required",
    "managed",
    "read-only",
    "public-copy",
}
_ALLOWED_VISIBILITIES = {"private", "shared", "classroom", "public", "archived"}
_ALLOWED_OPERATIONS = {"render-update", "replace-region"}
_ALLOWED_FIXTURE_ACTIONS = {"create-item", "delete-item", "replace-region", "update-item"}
_FIXTURE_OPERATION_KEYS = {
    "action",
    "local_ref",
    "operation_id",
    "payload_digest",
    "region_id",
}
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,80}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{16,128}$")


@dataclass(frozen=True)
class RegionDeclaration:
    view_id: str
    region_id: str
    mode: str
    surface_alias: str
    expected_snapshot_digest: str
    expected_source_digest: str | None = None
    owner: str = "schauwerk"
    visibility: str = "private"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"region.{key} must be a non-empty string")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"region.{key} must be a non-empty string when present")
    return value.strip()


def _validate_safe_id(value: str, *, label: str) -> str:
    if not _SAFE_ID.match(value):
        raise ValueError(f"region.{label} has an unsafe identifier shape")
    return value


def _validate_digest(value: str, *, label: str) -> str:
    if not _HEX_DIGEST.match(value):
        raise ValueError(f"region.{label} must be a 16-128 char lowercase hex digest")
    return value


def parse_region_declaration(data: dict[str, Any]) -> RegionDeclaration:
    source = data.get("region", data)
    if not isinstance(source, dict):
        raise ValueError("operator input must contain a region object")

    view_id = _validate_safe_id(_required_text(source, "view_id"), label="view_id")
    region_id = _validate_safe_id(_required_text(source, "region_id"), label="region_id")
    surface_alias = _validate_safe_id(
        _required_text(source, "surface_alias"), label="surface_alias"
    )
    mode = _required_text(source, "mode")
    if mode not in _ALLOWED_MODES:
        raise ValueError(f"region.mode must be one of {sorted(_ALLOWED_MODES)}")
    visibility = _optional_text(source, "visibility") or "private"
    if visibility not in _ALLOWED_VISIBILITIES:
        raise ValueError(f"region.visibility must be one of {sorted(_ALLOWED_VISIBILITIES)}")
    expected_snapshot_digest = _validate_digest(
        _required_text(source, "expected_snapshot_digest"),
        label="expected_snapshot_digest",
    )
    expected_source_digest = _optional_text(source, "expected_source_digest")
    if expected_source_digest is not None:
        expected_source_digest = _validate_digest(
            expected_source_digest, label="expected_source_digest"
        )
    owner = _validate_safe_id(_optional_text(source, "owner") or "schauwerk", label="owner")
    return RegionDeclaration(
        view_id=view_id,
        region_id=region_id,
        mode=mode,
        surface_alias=surface_alias,
        expected_snapshot_digest=expected_snapshot_digest,
        expected_source_digest=expected_source_digest,
        owner=owner,
        visibility=visibility,
    )


def load_region_declaration(path: Path) -> RegionDeclaration:
    text = path.read_text(encoding="utf-8")
    raw = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("operator input must contain an object")
    return parse_region_declaration(raw)


def _gate(region: RegionDeclaration, operation: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if operation not in _ALLOWED_OPERATIONS:
        reasons.append("operation_not_allowed")
    if region.mode == "manual":
        reasons.append("manual_region_is_human_owned")
    elif region.mode == "suggest-only":
        reasons.append("suggest_only_region_blocks_mutation")
    elif region.mode == "read-only":
        reasons.append("read_only_region_blocks_mutation")
    elif region.mode == "public-copy":
        reasons.append("public_copy_requires_publication_flow")
    elif region.mode == "approval-required":
        reasons.append("human_approval_required")
    elif region.mode == "cooperative":
        reasons.append("cooperative_region_requires_explicit_apply_policy")
    return not reasons, reasons


def compile_region_operation_plan(
    *,
    declaration: RegionDeclaration,
    operation: str = "render-update",
    output_path: Path | None = None,
) -> dict[str, Any]:
    ready, blocked_reasons = _gate(declaration, operation)
    plan = {
        "schema_version": "typed-region-plan.v1",
        "ok": ready,
        "mutation_attempted": False,
        "operation": operation,
        "region": declaration.to_dict(),
        "ready_for_preflight": ready,
        "blocked_reasons": blocked_reasons,
        "required_preflight": [
            "resolve_view_declaration",
            "verify_board_allowlist_alias",
            "capture_before_snapshot",
            "match_expected_snapshot_digest",
            "compile_candidate_dsl",
            "confirm_region_marker_scope",
        ],
        "postflight_required": [
            "capture_after_snapshot",
            "verify_region_marker_scope",
            "verify_idempotency_receipt",
            "write_quality_receipt",
        ],
        "restore_required": True,
        "restore_strategy": "before_snapshot_required",
        "boundary": {
            "dry_run_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
    }
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        plan["output_path"] = str(destination)
    else:
        plan["output_path"] = None
    return plan


def _snapshot_receipt(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("snapshot path is unsafe")
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("snapshot receipt is unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError("snapshot receipt must contain an object")
    digest = raw.get("content_digest")
    if not isinstance(digest, str):
        raise ValueError("snapshot receipt lacks content_digest")
    _validate_digest(digest, label="snapshot.content_digest")
    board_alias = raw.get("board_alias")
    if not isinstance(board_alias, str):
        raise ValueError("snapshot receipt lacks board_alias")
    return {
        "path": str(candidate),
        "board_alias": _validate_safe_id(board_alias, label="snapshot.board_alias"),
        "content_digest": digest,
        "item_count": raw.get("item_count"),
        "repeatability_verified": raw.get("repeatability_verified"),
        "sanitized_references": raw.get("sanitized_references"),
    }


def compile_region_preflight(
    *,
    declaration: RegionDeclaration,
    allowlisted_aliases: set[str],
    snapshot_path: Path,
    operation: str = "render-update",
    output_path: Path | None = None,
) -> dict[str, Any]:
    plan = compile_region_operation_plan(declaration=declaration, operation=operation)
    snapshot = _snapshot_receipt(snapshot_path)
    blocked_reasons = list(plan["blocked_reasons"])
    alias_allowed = declaration.surface_alias in allowlisted_aliases
    if not alias_allowed:
        blocked_reasons.append("surface_alias_not_allowlisted")
    digest_matches = snapshot["content_digest"] == declaration.expected_snapshot_digest
    if not digest_matches:
        blocked_reasons.append("snapshot_digest_mismatch")
    snapshot_alias_matches = snapshot["board_alias"] == declaration.surface_alias
    if not snapshot_alias_matches:
        blocked_reasons.append("snapshot_board_alias_mismatch")
    repeatability_verified = snapshot.get("repeatability_verified") is True
    if not repeatability_verified:
        blocked_reasons.append("snapshot_repeatability_unverified")
    sanitized_references = snapshot.get("sanitized_references") is True
    if not sanitized_references:
        blocked_reasons.append("snapshot_references_not_sanitized")

    ready = not blocked_reasons
    preflight = {
        "schema_version": "typed-region-preflight.v1",
        "ok": ready,
        "mutation_attempted": False,
        "operation": operation,
        "region": declaration.to_dict(),
        "plan_ok": plan["ok"],
        "ready_for_apply": ready,
        "blocked_reasons": blocked_reasons,
        "checks": {
            "surface_alias_allowlisted": alias_allowed,
            "snapshot_digest_matches": digest_matches,
            "snapshot_board_alias_matches": snapshot_alias_matches,
            "snapshot_repeatability_verified": repeatability_verified,
            "snapshot_references_sanitized": sanitized_references,
        },
        "snapshot": snapshot,
        "required_apply": [
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
            "dry_run_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
    }
    if output_path is not None:
        destination = output_path.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        preflight["output_path"] = str(destination)
    else:
        preflight["output_path"] = None
    return preflight


def load_region_preflight(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("preflight path is unsafe")
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("preflight receipt is unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError("preflight receipt must contain an object")
    if raw.get("schema_version") != "typed-region-preflight.v1":
        raise ValueError("preflight receipt has an unsupported schema")
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
