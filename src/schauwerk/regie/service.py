"""Stateful controller for one local Regie review session."""

from __future__ import annotations

import inspect
import threading
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schauwerk.operator.live_apply import (
    ManagedRegionProvider,
    _receipt_digest,
    execute_live_apply,
    kill_switch_status,
    load_live_restore_receipt,
    restore_live_apply,
    validate_live_transaction_failure_receipt,
    validate_live_transaction_receipt,
)
from schauwerk.surfaces.miro.errors import redact_text

from .model import (
    REGIE_STATE_SCHEMA,
    compile_decision_receipt,
    load_decision_receipt,
    read_private_json,
    validate_review_bundle,
    write_private_json,
)

ProviderFactory = Callable[[], ManagedRegionProvider | Awaitable[ManagedRegionProvider]]


def _safe_root(path: Path, *, label: str) -> Path:
    root = path.expanduser().absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError(f"{label} path is unsafe")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError(f"{label} path is unsafe")
    root.chmod(0o700)
    return root


def _timestamp_expired(value: str, *, now: datetime) -> bool:
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)
    return now >= parsed


def _decision_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_digest": value["decision_digest"],
        "decided_at": value["decided_at"],
        "approved_by": value["approved_by"],
        "approval_reference": value["approval_reference"],
        "approved_operation_ids": value["approved_operation_ids"],
        "rejected_operation_ids": value["rejected_operation_ids"],
        "deferred_operation_ids": value["deferred_operation_ids"],
        "authorization_id": value["authorization"]["authorization_id"],
        "authorization_digest": value["authorization"]["authorization_digest"],
        "authorization_expires_at": value["authorization"]["expires_at"],
        "selected_bundle_digest": value["selected_bundle"]["bundle_digest"],
        "plan_digest": value["plan"]["plan_digest"],
        "mutation_attempted": False,
    }


def _transaction_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
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
        "failure",
        "rollback_attempted",
        "rollback_succeeded",
        "rollback_error",
        "manual_recovery_required",
        "receipt_digest",
        "replayed_without_mutation",
    )
    return {key: value[key] for key in allowed if key in value}


def _load_transaction_receipt(path: Path) -> dict[str, Any]:
    value = read_private_json(path, label="Regie transaction receipt")
    if value.get("receipt_digest") != _receipt_digest(value):
        raise ValueError("Regie transaction receipt digest mismatch")
    if value.get("ok") is True:
        return validate_live_transaction_receipt(value)
    return validate_live_transaction_failure_receipt(value)


def _load_restore_receipt(path: Path) -> dict[str, Any]:
    return load_live_restore_receipt(path)


def _restore_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
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
        "failure",
        "rollback_to_after_attempted",
        "rollback_to_after_succeeded",
        "rollback_to_after_error",
        "still_restore_ready",
        "manual_recovery_required",
        "receipt_digest",
        "replayed_without_mutation",
    )
    return {key: value[key] for key in allowed if key in value}


class RegieController:
    """Own one immutable review and its decision/apply/restore receipts."""

    def __init__(
        self,
        *,
        review_bundle: Mapping[str, Any],
        state_root: Path,
        journal_root: Path,
        kill_switch_path: Path,
        provider_factory: ProviderFactory,
    ) -> None:
        self.review = validate_review_bundle(review_bundle)
        root = _safe_root(state_root, label="Regie state root")
        self.session_root = _safe_root(
            root / self.review["review_digest"], label="Regie session root"
        )
        self.journal_root = _safe_root(journal_root, label="live transaction root")
        self.kill_switch_path = kill_switch_path.expanduser().absolute()
        self.provider_factory = provider_factory
        self.decision_path = self.session_root / "decision-receipt.json"
        self.bundle_path = self.session_root / "selected-bundle.json"
        self.authorization_path = self.session_root / "authorization.json"
        self.plan_path = self.session_root / "live-plan.json"
        self.transaction_path = self.session_root / "transaction-receipt.json"
        self.restore_path = self.session_root / "restore-receipt.json"
        self._lock = threading.RLock()

    async def _provider(self) -> ManagedRegionProvider:
        provider = self.provider_factory()
        if inspect.isawaitable(provider):
            provider = await provider
        return provider

    def state(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
        with self._lock:
            decision = (
                load_decision_receipt(self.decision_path) if self.decision_path.exists() else None
            )
            transaction = (
                _load_transaction_receipt(self.transaction_path)
                if self.transaction_path.exists()
                else None
            )
            restore = (
                _load_restore_receipt(self.restore_path) if self.restore_path.exists() else None
            )
            authorization_expired = bool(
                decision
                and _timestamp_expired(decision["authorization"]["expires_at"], now=current)
            )
            kill_switch = kill_switch_status(self.kill_switch_path)
            transaction_ok = bool(transaction and transaction.get("ok") is True)
            restore_ok = bool(restore and restore.get("ok") is True)
            return {
                "schema_version": REGIE_STATE_SCHEMA,
                "review": {
                    key: self.review[key]
                    for key in (
                        "review_id",
                        "review_digest",
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
                    )
                },
                "decision": _decision_projection(decision) if decision else None,
                "transaction": (_transaction_projection(transaction) if transaction else None),
                "restore": _restore_projection(restore) if restore else None,
                "controls": {
                    "can_decide": decision is None,
                    "can_apply": bool(
                        decision
                        and not authorization_expired
                        and not transaction
                        and not kill_switch["enabled"]
                    ),
                    "can_restore": bool(
                        transaction_ok
                        and (
                            restore is None
                            or (
                                restore.get("ok") is False
                                and restore.get("still_restore_ready") is True
                            )
                        )
                    ),
                    "authorization_expired": authorization_expired,
                    "kill_switch_enabled": kill_switch["enabled"],
                    "decision_immutable": decision is not None,
                },
                "phase": (
                    "restored"
                    if restore_ok
                    else "restore-failed"
                    if restore
                    else "applied"
                    if transaction_ok
                    else "apply-failed"
                    if transaction
                    else "approved"
                    if decision
                    else "review"
                ),
                "boundary": {
                    "local_loopback_only": True,
                    "provider_identifiers_excluded": True,
                    "receipt_bound": True,
                },
            }

    def decide(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "decisions",
            "approved_by",
            "approval_reference",
            "confirmation",
            "valid_minutes",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("Regie decision request fields are invalid")
        decisions = payload.get("decisions")
        if not isinstance(decisions, Mapping):
            raise ValueError("Regie decision request decisions are invalid")
        expected_ids = {operation["operation_id"] for operation in self.review["operations"]}
        if set(decisions) != expected_ids or any(
            decision not in {"approve", "reject", "defer"} for decision in decisions.values()
        ):
            raise ValueError("Regie decisions must cover every operation exactly once")
        if payload.get("confirmation") != "APPROVE_LIVE_APPLY":
            raise ValueError("Regie live approval confirmation is invalid")
        valid_minutes = payload.get("valid_minutes")
        if (
            isinstance(valid_minutes, bool)
            or not isinstance(valid_minutes, int)
            or not 1 <= valid_minutes <= 1440
        ):
            raise ValueError("Regie authorization duration is invalid")
        with self._lock:
            if self.decision_path.exists():
                existing = load_decision_receipt(self.decision_path)
                requested = [
                    {
                        "operation_id": operation["operation_id"],
                        "decision": decisions.get(operation["operation_id"]),
                    }
                    for operation in self.review["operations"]
                ]
                approved_at = datetime.fromisoformat(
                    existing["authorization"]["approved_at"].removesuffix("Z") + "+00:00"
                ).astimezone(UTC)
                expires_at = datetime.fromisoformat(
                    existing["authorization"]["expires_at"].removesuffix("Z") + "+00:00"
                ).astimezone(UTC)
                existing_minutes = int((expires_at - approved_at).total_seconds() // 60)
                if (
                    existing["decisions"] == requested
                    and existing["approved_by"] == payload.get("approved_by")
                    and existing["approval_reference"] == payload.get("approval_reference")
                    and existing_minutes == valid_minutes
                ):
                    result = _decision_projection(existing)
                    result["replayed_without_change"] = True
                    return result
                raise ValueError("Regie decision is already immutable")
            receipt = compile_decision_receipt(
                review_bundle=self.review,
                decisions=decisions,
                approved_by=payload.get("approved_by"),
                approval_reference=payload.get("approval_reference"),
                confirmation=payload.get("confirmation"),
                valid_minutes=payload.get("valid_minutes"),
            )
            write_private_json(
                self.bundle_path,
                receipt["selected_bundle"],
                label="Regie selected bundle",
            )
            write_private_json(
                self.authorization_path,
                receipt["authorization"],
                label="Regie authorization",
            )
            write_private_json(self.plan_path, receipt["plan"], label="Regie live plan")
            write_private_json(self.decision_path, receipt, label="Regie decision receipt")
            return _decision_projection(receipt)

    async def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping) or set(payload) != {"confirmation"}:
            raise ValueError("Regie apply request fields are invalid")
        if payload.get("confirmation") != "EXECUTE_LIVE_APPLY":
            raise ValueError("Regie apply confirmation is invalid")
        with self._lock:
            decision = load_decision_receipt(self.decision_path)
            if self.restore_path.exists():
                raise ValueError("Regie transaction was already restored")
            if self.transaction_path.exists():
                existing = _load_transaction_receipt(self.transaction_path)
                result = _transaction_projection(existing)
                result["replayed_without_mutation"] = True
                return result
            if _timestamp_expired(decision["authorization"]["expires_at"], now=datetime.now(UTC)):
                raise ValueError("Regie authorization has expired")
            if kill_switch_status(self.kill_switch_path)["enabled"]:
                raise ValueError("live apply kill switch is enabled")
            provider = await self._provider()
            receipt = await execute_live_apply(
                plan=decision["plan"],
                provider=provider,
                journal_root=self.journal_root,
                kill_switch_path=self.kill_switch_path,
                output_path=self.transaction_path,
            )
            return _transaction_projection(receipt)

    async def restore(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping) or set(payload) != {"confirmation"}:
            raise ValueError("Regie restore request fields are invalid")
        if payload.get("confirmation") != "RESTORE_LIVE_APPLY":
            raise ValueError("Regie restore confirmation is invalid")
        with self._lock:
            transaction = _load_transaction_receipt(self.transaction_path)
            if transaction.get("ok") is not True:
                raise ValueError("Regie restore requires a successful transaction")
            if self.restore_path.exists():
                existing = _load_restore_receipt(self.restore_path)
                if existing.get("ok") is True:
                    result = _restore_projection(existing)
                    result["replayed_without_mutation"] = True
                    return result
                if existing.get("still_restore_ready") is not True:
                    raise ValueError("Regie restore requires manual recovery")
            provider = await self._provider()
            try:
                receipt = await restore_live_apply(
                    transaction_receipt_path=self.transaction_path,
                    provider=provider,
                    output_path=self.restore_path,
                )
            except Exception as exc:
                raise ValueError(f"Regie restore failed: {redact_text(exc)}") from exc
            return _restore_projection(receipt)
