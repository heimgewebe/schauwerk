"""Resilient collection from registry, local receipts and optional provider health."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from schauwerk.operator.live_apply import (
    _load_journal,
    validate_live_restore_failure_receipt,
    validate_live_restore_receipt,
    validate_live_transaction_failure_receipt,
    validate_live_transaction_receipt,
)
from schauwerk.regie.model import load_decision_receipt
from schauwerk.registry_runtime import load_registry, registry_digest, repository_root
from schauwerk.surfaces.miro.errors import redact_text

from .model import (
    OBSERVATION_SCHEMA,
    OVERVIEW_SCHEMA,
    PROFILE_SCHEMA,
    manifest_digest,
    validate_overview_snapshot,
)

_TERMINAL_TRANSACTION_STATES = frozenset(
    {"preflight_failed", "rolled_back", "restored"}
)
_ACTIVE_TRANSACTION_STATES = frozenset(
    {"reserved", "prepared", "applying", "committed", "rollback_failed"}
)


class OverviewMiroClient(Protocol):
    settings: Any

    def status(self) -> dict[str, Any]: ...

    def cached_auth_health(self) -> dict[str, Any] | None: ...

    async def live_status(self) -> dict[str, Any]: ...


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _from_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)


def _freshness(
    observed_at: datetime, *, now: datetime, stale_after_seconds: int, state: str
) -> str:
    if state == "error":
        return "error"
    if observed_at > now:
        return "unknown"
    return (
        "fresh"
        if (now - observed_at).total_seconds() <= stale_after_seconds
        else "stale"
    )


def _observation(
    *,
    observation_id: str,
    category: str,
    label: str,
    value: str,
    state: str,
    severity: str,
    source: str,
    observed_at: datetime,
    now: datetime,
    stale_after_seconds: int,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "category": category,
        "label": label,
        "value": value,
        "state": state,
        "freshness": _freshness(
            observed_at,
            now=now,
            stale_after_seconds=stale_after_seconds,
            state=state,
        ),
        "severity": severity,
        "source": source,
        "observed_at": _iso(observed_at),
        "stale_after_seconds": stale_after_seconds,
        "error": error,
    }


def _path_reference(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _journal_identifier(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) < 2
        or len(value) > 100
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_.:-" for character in value)
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _failure(
    identifier: str,
    *,
    source: str,
    observed_at: datetime,
    severity: str,
    message: str,
) -> dict[str, str]:
    return {
        "failure_id": identifier,
        "source": source,
        "observed_at": _iso(observed_at),
        "severity": severity,
        "message": redact_text(message),
    }


def _read_owner_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f"{label} is not an owner-only regular file")
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError(f"{label} exceeds the 8 MiB limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} is invalid")
    return value


def _navigation(registry: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    surfaces = {item["id"]: item for item in registry["surfaces"]}
    publications_by_view: dict[str, list[str]] = {}
    for publication in registry["publications"]:
        publications_by_view.setdefault(publication["view_id"], []).append(
            publication["id"]
        )
    views_by_project: dict[str, list[dict[str, Any]]] = {}
    for view in registry["views"]:
        surface = surfaces[view["surface_ref"]]
        views_by_project.setdefault(view["project_id"], []).append(
            {
                "view_id": view["id"],
                "title": view["title"],
                "purpose": view["purpose"],
                "visibility": view["visibility"],
                "management_mode": view["management_mode"],
                "surface_id": surface["id"],
                "surface_status": surface["status"],
                "surface_provider": surface["provider"],
                "audiences": sorted(view.get("audiences", [])),
                "publication_ids": sorted(publications_by_view.get(view["id"], [])),
            }
        )
    return [
        {
            "project_id": project["id"],
            "title": project["title"],
            "status": project["status"],
            "visibility": project["visibility"],
            "views": sorted(
                views_by_project.get(project["id"], []), key=lambda item: item["view_id"]
            ),
        }
        for project in registry["projects"]
    ]


def _artifact_observations(
    registry: dict[str, list[dict[str, Any]]],
    *,
    root: Path,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    observations: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for surface in registry["surfaces"]:
        output_path = surface.get("output_path")
        if not output_path:
            continue
        target = root / output_path
        exists = target.is_file() and not target.is_symlink()
        observed = (
            datetime.fromtimestamp(target.stat().st_mtime, tz=UTC) if exists else now
        )
        required = surface["status"] == "active"
        state = "ok" if exists else "error" if required else "inactive"
        severity = "info" if exists or not required else "warning"
        error = None if exists or not required else "Declared active artifact is missing"
        observations.append(
            _observation(
                observation_id=f"surface.{surface['id']}",
                category="surface",
                label=surface["title"],
                value="artifact present" if exists else "artifact missing",
                state=state,
                severity=severity,
                source=f"registry surface {surface['id']}",
                observed_at=observed,
                now=now,
                stale_after_seconds=604800,
                error=error,
            )
        )
        if error:
            failures.append(
                _failure(
                    f"surface.{surface['id']}.missing",
                    source=f"registry surface {surface['id']}",
                    observed_at=observed,
                    severity="warning",
                    message=error,
                )
            )
    return observations, failures


def _publication_observations(
    registry: dict[str, list[dict[str, Any]]],
    *,
    root: Path,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    publications = []
    failures: list[dict[str, str]] = []
    for publication in registry["publications"]:
        path_text = publication.get("artifact_path")
        target = root / path_text if path_text else None
        exists = bool(target and target.is_file() and not target.is_symlink())
        observed = (
            datetime.fromtimestamp(target.stat().st_mtime, tz=UTC)
            if exists and target is not None
            else now
        )
        expires_at = publication.get("expires_at")
        expired = bool(expires_at and _from_timestamp(expires_at) <= now)
        required = publication["status"] == "active"
        artifact_state = "missing" if not exists else "expired" if expired else "present"
        freshness = (
            "error"
            if not exists and required
            else "unknown"
            if not exists or observed > now
            else "stale"
            if expired or (now - observed).total_seconds() > 604800
            else "fresh"
        )
        publications.append(
            {
                "publication_id": publication["id"],
                "view_id": publication["view_id"],
                "status": publication["status"],
                "audience": publication["audience"],
                "artifact_state": artifact_state,
                "source_revision": publication.get("source_revision", ""),
                "observed_at": _iso(observed),
                "freshness": freshness,
                "expires_at": expires_at,
            }
        )
        if not exists and required:
            failures.append(
                _failure(
                    f"publication.{publication['id']}.missing",
                    source=f"registry publication {publication['id']}",
                    observed_at=observed,
                    severity="warning",
                    message="Declared publication artifact is missing",
                )
            )
    return publications, failures


def _transaction_jobs(
    transactions_root: Path, *, now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    jobs: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    if not transactions_root.exists():
        return jobs, failures
    if transactions_root.is_symlink() or not transactions_root.is_dir():
        return jobs, [
            _failure(
                "transactions.root.invalid",
                source="local SW-009 transaction root",
                observed_at=now,
                severity="critical",
                message="Transaction root is unsafe",
            )
        ]
    for directory in sorted(transactions_root.iterdir(), key=lambda item: item.name):
        journal_path = directory / "journal.json"
        if not journal_path.exists():
            continue
        try:
            journal = _load_journal(journal_path)
            transaction_id = _journal_identifier(
                journal.get("transaction_id"), label="transaction id"
            )
            region_id = _journal_identifier(
                journal.get("region_id"), label="transaction region id"
            )
            status = journal.get("status")
            if status in _TERMINAL_TRANSACTION_STATES:
                continue
            if status not in _ACTIVE_TRANSACTION_STATES:
                raise ValueError("transaction journal status is unsupported")
            observed = datetime.fromtimestamp(journal_path.stat().st_mtime, tz=UTC)
            freshness = (
                "fresh" if (now - observed).total_seconds() <= 3600 else "stale"
            )
            jobs.append(
                {
                    "job_id": f"transaction.{transaction_id}",
                    "kind": "live-transaction",
                    "status": status,
                    "summary": f"Managed region {region_id}",
                    "source": "local SW-009 transaction journal",
                    "observed_at": _iso(observed),
                    "freshness": freshness,
                    "project_id": "schauwerk",
                    "view_id": None,
                }
            )
        except Exception as exc:
            failures.append(
                _failure(
                    f"transaction.{_path_reference(directory.name)}.invalid",
                    source="local SW-009 transaction root",
                    observed_at=now,
                    severity="critical",
                    message=redact_text(exc),
                )
            )
    return jobs, failures


def _validate_transaction_file(path: Path) -> dict[str, Any]:
    value = _read_owner_json(path, label="Regie transaction receipt")
    return (
        validate_live_transaction_receipt(value)
        if value.get("ok") is True
        else validate_live_transaction_failure_receipt(value)
    )


def _validate_restore_file(path: Path) -> dict[str, Any]:
    value = _read_owner_json(path, label="Regie restore receipt")
    return (
        validate_live_restore_receipt(value)
        if value.get("ok") is True
        else validate_live_restore_failure_receipt(value)
    )


def _regie_jobs(
    regie_root: Path, *, now: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    jobs: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    if not regie_root.exists():
        return jobs, failures
    if regie_root.is_symlink() or not regie_root.is_dir():
        return jobs, [
            _failure(
                "regie.root.invalid",
                source="local Regie state root",
                observed_at=now,
                severity="critical",
                message="Regie state root is unsafe",
            )
        ]
    for directory in sorted(regie_root.iterdir(), key=lambda item: item.name):
        if not directory.is_dir() or directory.is_symlink():
            continue
        decision_path = directory / "decision-receipt.json"
        transaction_path = directory / "transaction-receipt.json"
        restore_path = directory / "restore-receipt.json"
        try:
            phase = "review"
            review_id = f"local-{_path_reference(directory.name)}"
            observed_path = directory
            if decision_path.exists():
                decision = load_decision_receipt(decision_path)
                review_id = decision["review_id"]
                authorization_expires = _from_timestamp(
                    decision["authorization"]["expires_at"]
                )
                phase = (
                    "authorization-expired"
                    if authorization_expires <= now
                    else "approved"
                )
                observed_path = decision_path
            if transaction_path.exists():
                transaction = _validate_transaction_file(transaction_path)
                phase = "applied" if transaction.get("ok") is True else "apply-failed"
                observed_path = transaction_path
            if restore_path.exists():
                restore = _validate_restore_file(restore_path)
                phase = "restored" if restore.get("ok") is True else "restore-failed"
                observed_path = restore_path
            if phase == "restored":
                continue
            observed = datetime.fromtimestamp(observed_path.stat().st_mtime, tz=UTC)
            jobs.append(
                {
                    "job_id": f"regie.{review_id}",
                    "kind": "regie-session",
                    "status": phase,
                    "summary": (
                        f"Regie review {review_id} — authorization expired"
                        if phase == "authorization-expired"
                        else f"Regie review {review_id}"
                    ),
                    "source": "local Regie receipt chain",
                    "observed_at": _iso(observed),
                    "freshness": (
                        "fresh"
                        if (now - observed).total_seconds() <= 3600
                        else "stale"
                    ),
                    "project_id": "schauwerk",
                    "view_id": "schauwerk.delivery-status",
                }
            )
        except Exception as exc:
            failures.append(
                _failure(
                    f"regie.{_path_reference(directory.name)}.invalid",
                    source="local Regie state root",
                    observed_at=now,
                    severity="critical",
                    message=redact_text(exc),
                )
            )
    return jobs, failures


def _profiles() -> list[dict[str, Any]]:
    common = ["summary", "projects", "observations", "jobs", "publications", "failures"]
    return [
        {
            "schema_version": PROFILE_SCHEMA,
            "profile_id": "operator",
            "title": "Operator overview",
            "refresh_seconds": 60,
            "fullscreen": False,
            "visible_sections": common,
            "maximum_items_per_section": 100,
        },
        {
            "schema_version": PROFILE_SCHEMA,
            "profile_id": "wallboard",
            "title": "Fullscreen wallboard",
            "refresh_seconds": 30,
            "fullscreen": True,
            "visible_sections": ["summary", "observations", "jobs", "failures"],
            "maximum_items_per_section": 40,
        },
        {
            "schema_version": PROFILE_SCHEMA,
            "profile_id": "incident",
            "title": "Incident display",
            "refresh_seconds": 15,
            "fullscreen": True,
            "visible_sections": ["summary", "observations", "jobs", "failures"],
            "maximum_items_per_section": 200,
        },
    ]


async def collect_overview(
    *,
    miro_client: OverviewMiroClient,
    repo_root: Path | None = None,
    probe_provider: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    root = (repo_root or repository_root()).resolve()
    registry = load_registry(root)
    failures: list[dict[str, str]] = []
    observations: list[dict[str, Any]] = []

    artifact_observations, artifact_failures = _artifact_observations(
        registry, root=root, now=current
    )
    observations.extend(artifact_observations)
    failures.extend(artifact_failures)
    publications, publication_failures = _publication_observations(
        registry, root=root, now=current
    )
    failures.extend(publication_failures)

    local_status = miro_client.status()
    local_state = "ok" if local_status.get("local_state_present") else "unknown"
    observations.append(
        _observation(
            observation_id="provider.miro.local",
            category="provider",
            label="Miro local authorization state",
            value=(
                "local authorization material present"
                if local_status.get("local_state_present")
                else "local authorization material absent"
            ),
            state=local_state,
            severity="info" if local_state == "ok" else "warning",
            source="local Miro client status",
            observed_at=current,
            now=current,
            stale_after_seconds=300,
        )
    )

    provider_state = "unknown"
    provider_observed = current
    provider_error: str | None = None
    provider_value = "live provider state not checked"
    if probe_provider:
        try:
            live = await miro_client.live_status()
            provider_state = "ok" if live.get("ok") is True else "error"
            provider_value = (
                f"live read-only check passed with {live.get('tool_count', 0)} tools"
                if live.get("ok") is True
                else "live read-only check failed"
            )
            provider_error = (
                None
                if live.get("ok") is True
                else redact_text(live.get("error", "provider unavailable"))
            )
        except Exception as exc:
            provider_state = "error"
            provider_value = "live read-only check failed"
            provider_error = redact_text(exc)
    else:
        try:
            cached = miro_client.cached_auth_health()
            if cached:
                provider_observed = _from_timestamp(cached["observed_at"])
                provider_state = (
                    "ok"
                    if cached.get("safe_for_live_board_operations")
                    else "error"
                )
                provider_value = (
                    "cached live authorization check passed"
                    if provider_state == "ok"
                    else "cached live authorization check failed"
                )
                if provider_state == "error":
                    provider_error = (
                        "Cached provider health is not safe for live operations"
                    )
        except Exception as exc:
            provider_state = "error"
            provider_value = "cached provider health is unreadable"
            provider_error = redact_text(exc)
    observations.append(
        _observation(
            observation_id="provider.miro.live",
            category="provider",
            label="Miro provider health",
            value=provider_value,
            state=provider_state,
            severity="critical" if provider_state == "error" else "info",
            source=(
                "live Miro read-only health check"
                if probe_provider
                else "cached Miro auth-health receipt"
            ),
            observed_at=provider_observed,
            now=current,
            stale_after_seconds=900,
            error=provider_error,
        )
    )
    if provider_error:
        failures.append(
            _failure(
                "provider.miro.unavailable",
                source="Miro provider health",
                observed_at=provider_observed,
                severity="critical",
                message=provider_error,
            )
        )

    state_root = Path(miro_client.settings.state_root)
    transaction_jobs, transaction_failures = _transaction_jobs(
        state_root / "transactions", now=current
    )
    regie_jobs, regie_failures = _regie_jobs(
        state_root.parent / "regie", now=current
    )
    jobs = transaction_jobs + regie_jobs
    failures.extend(transaction_failures)
    failures.extend(regie_failures)

    projects = _navigation(registry)
    stale_count = sum(item["freshness"] == "stale" for item in observations)
    stale_count += sum(item["freshness"] == "stale" for item in publications)
    stale_count += sum(item["freshness"] == "stale" for item in jobs)
    value = {
        "schema_version": OVERVIEW_SCHEMA,
        "generated_at": _iso(current),
        "registry_digest": registry_digest(registry),
        "projects": projects,
        "observations": sorted(observations, key=lambda item: item["observation_id"]),
        "jobs": sorted(jobs, key=lambda item: item["job_id"]),
        "publications": sorted(publications, key=lambda item: item["publication_id"]),
        "failures": sorted(failures, key=lambda item: item["failure_id"]),
        "display_profiles": _profiles(),
        "summary": {
            "project_count": len(projects),
            "view_count": sum(len(project["views"]) for project in projects),
            "active_job_count": len(jobs),
            "error_count": len(failures),
            "stale_count": stale_count,
            "provider_state": provider_state,
        },
        "boundary": {
            "read_only": True,
            "registry_is_navigation_truth": True,
            "observations_are_time_bound": True,
            "provider_failure_does_not_block_local_diagnostics": True,
            "provider_identifiers_excluded": True,
        },
    }
    value["snapshot_digest"] = manifest_digest(value, "snapshot_digest")
    return validate_overview_snapshot(value)
