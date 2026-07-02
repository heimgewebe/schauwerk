"""Dry-run typed operator plans for managed Schauwerk regions."""

from __future__ import annotations

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
