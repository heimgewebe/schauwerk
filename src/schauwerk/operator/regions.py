"""Dry-run typed operator plans for managed Schauwerk regions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schauwerk.operator.core import (
    _ALLOWED_OPERATIONS,
    RegionDeclaration,
    _validate_digest,
    _validate_safe_id,
)
from schauwerk.operator.core import (
    load_region_declaration as load_region_declaration,
)
from schauwerk.operator.core import (
    parse_region_declaration as parse_region_declaration,
)


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
    from schauwerk.operator.receipts import load_region_preflight as _impl

    return _impl(path)


def load_region_apply_scaffold(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_apply_scaffold as _impl

    return _impl(path)


def load_fixture_operations(path: Path) -> list[dict[str, Any]]:
    from schauwerk.operator.receipts import load_fixture_operations as _impl

    return _impl(path)


def compile_region_apply_receipt(
    *,
    scaffold: dict[str, Any],
    fixture_operations: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_apply_receipt as _impl

    return _impl(
        scaffold=scaffold,
        fixture_operations=fixture_operations,
        output_path=output_path,
    )


def compile_region_apply_scaffold(
    *,
    preflight: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_apply_scaffold as _impl

    return _impl(preflight=preflight, output_path=output_path)


def load_region_apply_receipt(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_apply_receipt as _impl

    return _impl(path)


def load_region_postflight_receipt(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_postflight_receipt as _impl

    return _impl(path)


def load_region_restore_receipt(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_restore_receipt as _impl

    return _impl(path)


def load_snapshot_mapping_receipt(
    path: Path, *, label: str = "snapshot"
) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_snapshot_mapping_receipt as _impl

    return _impl(path, label=label)


def compile_region_postflight_receipt(
    *,
    apply_receipt: dict[str, Any],
    after_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_postflight_receipt as _impl

    return _impl(
        apply_receipt=apply_receipt,
        after_snapshot=after_snapshot,
        output_path=output_path,
    )


def compile_region_restore_receipt(
    *,
    postflight_receipt: dict[str, Any],
    restored_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_restore_receipt as _impl

    return _impl(
        postflight_receipt=postflight_receipt,
        restored_snapshot=restored_snapshot,
        output_path=output_path,
    )


def required_sw003_live_gate_evidence() -> list[dict[str, str]]:
    from schauwerk.operator.sw003_closeout import (
        required_sw003_live_gate_evidence as _impl,
    )

    return _impl()


def evaluate_sw003_live_gate_claim(evidence: object) -> dict[str, Any]:
    from schauwerk.operator.sw003_closeout import evaluate_sw003_live_gate_claim as _impl

    return _impl(evidence)


def load_sw003_closeout_evidence(path: Path) -> dict[str, Any]:
    from schauwerk.operator.sw003_closeout import load_sw003_closeout_evidence as _impl

    return _impl(path)


def load_sw003_closeout_receipt(path: Path) -> dict[str, Any]:
    from schauwerk.operator.sw003_closeout import load_sw003_closeout_receipt as _impl

    return _impl(path)


def compile_sw003_closeout_receipt(
    *,
    restore_receipt: dict[str, Any],
    evidence: dict[str, Any],
    marker: str,
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.sw003_closeout import compile_sw003_closeout_receipt as _impl

    return _impl(
        restore_receipt=restore_receipt,
        evidence=evidence,
        marker=marker,
        output_path=output_path,
    )


def load_region_operation_contract(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_operation_contract as _impl

    return _impl(path)


def compile_region_operation_contract(
    *,
    scaffold: dict[str, Any],
    fixture_operations: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_operation_contract as _impl

    return _impl(
        scaffold=scaffold,
        fixture_operations=fixture_operations,
        output_path=output_path,
    )


def load_region_apply_simulation_receipt(path: Path) -> dict[str, Any]:
    from schauwerk.operator.receipts import load_region_apply_simulation_receipt as _impl

    return _impl(path)


def compile_region_apply_simulation_receipt(
    *,
    operation_contract: dict[str, Any],
    after_snapshot: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    from schauwerk.operator.receipts import compile_region_apply_simulation_receipt as _impl

    return _impl(
        operation_contract=operation_contract,
        after_snapshot=after_snapshot,
        output_path=output_path,
    )
