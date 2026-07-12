"""Validated snapshot model for registry-backed overview and live diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OVERVIEW_SCHEMA = "schauwerk-overview-snapshot.v1"
OBSERVATION_SCHEMA = "schauwerk-overview-observation.v1"
PROFILE_SCHEMA = "schauwerk-display-profile.v1"

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,100}$")
_HEX = re.compile(r"^[a-f0-9]{64}$")
_FORBIDDEN_REFERENCE = re.compile(r"(?i)(?:https?://|miro\.com|moveToWidget=)")
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TEXT_BYTES = 16 * 1024
_MAX_ITEMS = 1000
_STATES = frozenset({"ok", "degraded", "error", "unknown", "inactive"})
_FRESHNESS = frozenset({"fresh", "stale", "error", "unknown"})
_SEVERITIES = frozenset({"info", "warning", "critical"})
_PROFILE_SECTIONS = frozenset(
    {"summary", "projects", "observations", "jobs", "publications", "failures"}
)
_ARTIFACT_STATES = frozenset({"present", "missing", "expired"})
_JOB_STATES = frozenset(
    {
        "reserved",
        "prepared",
        "applying",
        "committed",
        "preflight_failed",
        "rolled_back",
        "rollback_failed",
        "restored",
        "review",
        "approved",
        "applied",
        "apply-failed",
        "restore-failed",
        "authorization-expired",
    }
)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


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


def _text(value: Any, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized.encode("utf-8")) > _MAX_TEXT_BYTES:
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


def _parsed_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)


def _derived_freshness(
    *, observed_at: str, generated_at: str, stale_after_seconds: int, error: bool
) -> str:
    if error:
        return "error"
    observed = _parsed_timestamp(observed_at)
    generated = _parsed_timestamp(generated_at)
    if observed > generated:
        return "unknown"
    return "fresh" if (generated - observed).total_seconds() <= stale_after_seconds else "stale"


def _bounded_int(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid")
    return value


def _safe_path(path: Path, *, label: str, must_exist: bool) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError(f"{label} path is unsafe")
    if must_exist:
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ValueError(f"{label} is unreadable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if metadata.st_mode & 0o077:
            raise ValueError(f"{label} must be owner-only")
        if metadata.st_size > _MAX_FILE_BYTES:
            raise ValueError(f"{label} exceeds the 8 MiB limit")
    else:
        candidate.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if any(parent.is_symlink() for parent in candidate.parents):
            raise ValueError(f"{label} path is unsafe")
    return candidate


def write_snapshot(path: Path, value: Mapping[str, Any]) -> Path:
    destination = _safe_path(path, label="overview snapshot", must_exist=False)
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
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_snapshot(path: Path) -> dict[str, Any]:
    candidate = _safe_path(path, label="overview snapshot", must_exist=True)
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("overview snapshot is unreadable") from exc
    return validate_overview_snapshot(value)


def validate_observation(value: Mapping[str, Any], *, index: int = 0) -> dict[str, Any]:
    expected = {
        "schema_version",
        "observation_id",
        "category",
        "label",
        "value",
        "state",
        "freshness",
        "severity",
        "source",
        "observed_at",
        "stale_after_seconds",
        "error",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"observations[{index}] fields are invalid")
    if value.get("schema_version") != OBSERVATION_SCHEMA:
        raise ValueError(f"observations[{index}] has an unsupported schema")
    state = value.get("state")
    freshness = value.get("freshness")
    severity = value.get("severity")
    if state not in _STATES:
        raise ValueError(f"observations[{index}].state is invalid")
    if freshness not in _FRESHNESS:
        raise ValueError(f"observations[{index}].freshness is invalid")
    if severity not in _SEVERITIES:
        raise ValueError(f"observations[{index}].severity is invalid")
    error = value.get("error")
    if error is not None:
        error = _text(error, label=f"observations[{index}].error")
    if state == "error" and not error:
        raise ValueError(f"observations[{index}] error state requires an error")
    if freshness == "error" and state != "error":
        raise ValueError(f"observations[{index}] freshness error requires error state")
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "observation_id": _safe_id(
            value.get("observation_id"), label=f"observations[{index}].observation_id"
        ),
        "category": _safe_id(value.get("category"), label=f"observations[{index}].category"),
        "label": _text(value.get("label"), label=f"observations[{index}].label"),
        "value": _text(value.get("value"), label=f"observations[{index}].value", allow_empty=True),
        "state": state,
        "freshness": freshness,
        "severity": severity,
        "source": _text(value.get("source"), label=f"observations[{index}].source"),
        "observed_at": _timestamp(
            value.get("observed_at"), label=f"observations[{index}].observed_at"
        ),
        "stale_after_seconds": _bounded_int(
            value.get("stale_after_seconds"),
            label=f"observations[{index}].stale_after_seconds",
            minimum=1,
            maximum=31_536_000,
        ),
        "error": error,
    }


def validate_profile(value: Mapping[str, Any], *, index: int = 0) -> dict[str, Any]:
    expected = {
        "schema_version",
        "profile_id",
        "title",
        "refresh_seconds",
        "fullscreen",
        "visible_sections",
        "maximum_items_per_section",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"display_profiles[{index}] fields are invalid")
    if value.get("schema_version") != PROFILE_SCHEMA:
        raise ValueError(f"display_profiles[{index}] has an unsupported schema")
    fullscreen = value.get("fullscreen")
    if not isinstance(fullscreen, bool):
        raise ValueError(f"display_profiles[{index}].fullscreen is invalid")
    sections = value.get("visible_sections")
    if (
        not isinstance(sections, list)
        or not sections
        or len(sections) > 12
        or len(set(sections)) != len(sections)
    ):
        raise ValueError(f"display_profiles[{index}].visible_sections is invalid")
    normalized_sections = [
        _safe_id(item, label=f"display_profiles[{index}].visible_sections") for item in sections
    ]
    if any(section not in _PROFILE_SECTIONS for section in normalized_sections):
        raise ValueError(f"display_profiles[{index}].visible_sections is invalid")
    return {
        "schema_version": PROFILE_SCHEMA,
        "profile_id": _safe_id(
            value.get("profile_id"), label=f"display_profiles[{index}].profile_id"
        ),
        "title": _text(value.get("title"), label=f"display_profiles[{index}].title"),
        "refresh_seconds": _bounded_int(
            value.get("refresh_seconds"),
            label=f"display_profiles[{index}].refresh_seconds",
            minimum=15,
            maximum=3600,
        ),
        "fullscreen": fullscreen,
        "visible_sections": normalized_sections,
        "maximum_items_per_section": _bounded_int(
            value.get("maximum_items_per_section"),
            label=f"display_profiles[{index}].maximum_items_per_section",
            minimum=1,
            maximum=500,
        ),
    }


def _validate_navigation(projects: Any) -> list[dict[str, Any]]:
    if not isinstance(projects, list) or len(projects) > _MAX_ITEMS:
        raise ValueError("overview projects are invalid")
    normalized: list[dict[str, Any]] = []
    project_ids: set[str] = set()
    for index, project in enumerate(projects):
        expected = {"project_id", "title", "status", "visibility", "views"}
        if not isinstance(project, Mapping) or set(project) != expected:
            raise ValueError(f"projects[{index}] fields are invalid")
        project_id = _safe_id(project.get("project_id"), label=f"projects[{index}].project_id")
        if project_id in project_ids:
            raise ValueError("overview project ids must be unique")
        project_ids.add(project_id)
        views = project.get("views")
        if not isinstance(views, list) or len(views) > _MAX_ITEMS:
            raise ValueError(f"projects[{index}].views are invalid")
        normalized_views = []
        view_ids: set[str] = set()
        for view_index, view in enumerate(views):
            expected_view = {
                "view_id",
                "title",
                "purpose",
                "visibility",
                "management_mode",
                "surface_id",
                "surface_status",
                "surface_provider",
                "audiences",
                "publication_ids",
            }
            if not isinstance(view, Mapping) or set(view) != expected_view:
                raise ValueError(f"projects[{index}].views[{view_index}] fields are invalid")
            view_id = _safe_id(
                view.get("view_id"), label=f"projects[{index}].views[{view_index}].view_id"
            )
            if view_id in view_ids:
                raise ValueError(f"projects[{index}] view ids must be unique")
            view_ids.add(view_id)
            audiences = view.get("audiences")
            publications = view.get("publication_ids")
            if not isinstance(audiences, list) or not isinstance(publications, list):
                raise ValueError(f"projects[{index}].views[{view_index}] lists are invalid")
            normalized_views.append(
                {
                    "view_id": view_id,
                    "title": _text(
                        view.get("title"), label=f"projects[{index}].views[{view_index}].title"
                    ),
                    "purpose": _text(
                        view.get("purpose"), label=f"projects[{index}].views[{view_index}].purpose"
                    ),
                    "visibility": _safe_id(
                        view.get("visibility"),
                        label=f"projects[{index}].views[{view_index}].visibility",
                    ),
                    "management_mode": _safe_id(
                        view.get("management_mode"),
                        label=f"projects[{index}].views[{view_index}].management_mode",
                    ),
                    "surface_id": _safe_id(
                        view.get("surface_id"),
                        label=f"projects[{index}].views[{view_index}].surface_id",
                    ),
                    "surface_status": _safe_id(
                        view.get("surface_status"),
                        label=f"projects[{index}].views[{view_index}].surface_status",
                    ),
                    "surface_provider": _safe_id(
                        view.get("surface_provider"),
                        label=f"projects[{index}].views[{view_index}].surface_provider",
                    ),
                    "audiences": sorted(_safe_id(item, label="audience") for item in audiences),
                    "publication_ids": sorted(
                        _safe_id(item, label="publication_id") for item in publications
                    ),
                }
            )
        normalized.append(
            {
                "project_id": project_id,
                "title": _text(project.get("title"), label=f"projects[{index}].title"),
                "status": _safe_id(project.get("status"), label=f"projects[{index}].status"),
                "visibility": _safe_id(
                    project.get("visibility"), label=f"projects[{index}].visibility"
                ),
                "views": normalized_views,
            }
        )
    return normalized


def _validate_jobs(jobs: Any) -> list[dict[str, Any]]:
    if not isinstance(jobs, list) or len(jobs) > _MAX_ITEMS:
        raise ValueError("overview jobs are invalid")
    normalized = []
    identifiers: set[str] = set()
    for index, job in enumerate(jobs):
        expected = {
            "job_id",
            "kind",
            "status",
            "summary",
            "source",
            "observed_at",
            "freshness",
            "project_id",
            "view_id",
        }
        if not isinstance(job, Mapping) or set(job) != expected:
            raise ValueError(f"jobs[{index}] fields are invalid")
        job_id = _safe_id(job.get("job_id"), label=f"jobs[{index}].job_id")
        if job_id in identifiers:
            raise ValueError("overview job ids must be unique")
        identifiers.add(job_id)
        status = job.get("status")
        if status not in _JOB_STATES:
            raise ValueError(f"jobs[{index}].status is invalid")
        freshness = job.get("freshness")
        if freshness not in _FRESHNESS:
            raise ValueError(f"jobs[{index}].freshness is invalid")
        project_id = job.get("project_id")
        view_id = job.get("view_id")
        normalized.append(
            {
                "job_id": job_id,
                "kind": _safe_id(job.get("kind"), label=f"jobs[{index}].kind"),
                "status": status,
                "summary": _text(job.get("summary"), label=f"jobs[{index}].summary"),
                "source": _text(job.get("source"), label=f"jobs[{index}].source"),
                "observed_at": _timestamp(
                    job.get("observed_at"), label=f"jobs[{index}].observed_at"
                ),
                "freshness": freshness,
                "project_id": (
                    _safe_id(project_id, label=f"jobs[{index}].project_id")
                    if project_id is not None
                    else None
                ),
                "view_id": (
                    _safe_id(view_id, label=f"jobs[{index}].view_id")
                    if view_id is not None
                    else None
                ),
            }
        )
    return normalized


def _validate_publications(publications: Any) -> list[dict[str, Any]]:
    if not isinstance(publications, list) or len(publications) > _MAX_ITEMS:
        raise ValueError("overview publications are invalid")
    normalized = []
    identifiers: set[str] = set()
    for index, item in enumerate(publications):
        expected = {
            "publication_id",
            "view_id",
            "status",
            "audience",
            "artifact_state",
            "source_revision",
            "observed_at",
            "freshness",
            "expires_at",
        }
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ValueError(f"publications[{index}] fields are invalid")
        freshness = item.get("freshness")
        if freshness not in _FRESHNESS:
            raise ValueError(f"publications[{index}].freshness is invalid")
        expires_at = item.get("expires_at")
        publication_id = _safe_id(
            item.get("publication_id"), label=f"publications[{index}].publication_id"
        )
        if publication_id in identifiers:
            raise ValueError("overview publication ids must be unique")
        identifiers.add(publication_id)
        artifact_state = _safe_id(
            item.get("artifact_state"), label=f"publications[{index}].artifact_state"
        )
        if artifact_state not in _ARTIFACT_STATES:
            raise ValueError(f"publications[{index}].artifact_state is invalid")
        normalized.append(
            {
                "publication_id": publication_id,
                "view_id": _safe_id(item.get("view_id"), label=f"publications[{index}].view_id"),
                "status": _safe_id(item.get("status"), label=f"publications[{index}].status"),
                "audience": _safe_id(item.get("audience"), label=f"publications[{index}].audience"),
                "artifact_state": artifact_state,
                "source_revision": _text(
                    item.get("source_revision"),
                    label=f"publications[{index}].source_revision",
                    allow_empty=True,
                ),
                "observed_at": _timestamp(
                    item.get("observed_at"), label=f"publications[{index}].observed_at"
                ),
                "freshness": freshness,
                "expires_at": (
                    _timestamp(expires_at, label=f"publications[{index}].expires_at")
                    if expires_at is not None
                    else None
                ),
            }
        )
    return normalized


def validate_overview_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "generated_at",
        "registry_digest",
        "projects",
        "observations",
        "jobs",
        "publications",
        "failures",
        "display_profiles",
        "summary",
        "boundary",
        "snapshot_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("overview snapshot fields are invalid")
    if value.get("schema_version") != OVERVIEW_SCHEMA:
        raise ValueError("overview snapshot has an unsupported schema")
    generated_at = _timestamp(value.get("generated_at"), label="generated_at")
    registry_digest = _digest(value.get("registry_digest"), label="registry_digest")
    projects = _validate_navigation(value.get("projects"))
    observations_raw = value.get("observations")
    if not isinstance(observations_raw, list) or len(observations_raw) > _MAX_ITEMS:
        raise ValueError("overview observations are invalid")
    observations = [
        validate_observation(item, index=index)
        for index, item in enumerate(observations_raw)
        if isinstance(item, Mapping)
    ]
    if len(observations) != len(observations_raw):
        raise ValueError("overview observations are invalid")
    observation_ids = [item["observation_id"] for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("overview observation ids must be unique")
    for observation in observations:
        expected_freshness = _derived_freshness(
            observed_at=observation["observed_at"],
            generated_at=generated_at,
            stale_after_seconds=observation["stale_after_seconds"],
            error=observation["state"] == "error",
        )
        if observation["freshness"] != expected_freshness:
            raise ValueError(
                f"overview observation {observation['observation_id']} freshness mismatch"
            )
    jobs = _validate_jobs(value.get("jobs"))
    for job in jobs:
        expected_freshness = _derived_freshness(
            observed_at=job["observed_at"],
            generated_at=generated_at,
            stale_after_seconds=3600,
            error=False,
        )
        if job["freshness"] != expected_freshness:
            raise ValueError(f"overview job {job['job_id']} freshness mismatch")
    publications = _validate_publications(value.get("publications"))
    for publication in publications:
        expires_at = publication["expires_at"]
        is_expired = bool(
            expires_at is not None
            and _parsed_timestamp(expires_at) <= _parsed_timestamp(generated_at)
        )
        if publication["artifact_state"] == "expired" and not is_expired:
            raise ValueError(
                f"overview publication {publication['publication_id']} expiry state mismatch"
            )
        if publication["artifact_state"] == "present" and is_expired:
            raise ValueError(
                f"overview publication {publication['publication_id']} expiry state mismatch"
            )
        if publication["artifact_state"] == "missing":
            expected_freshness = "error" if publication["status"] == "active" else "unknown"
        else:
            expected_freshness = _derived_freshness(
                observed_at=publication["observed_at"],
                generated_at=generated_at,
                stale_after_seconds=604800,
                error=False,
            )
            if is_expired:
                expected_freshness = "stale"
        if publication["freshness"] != expected_freshness:
            raise ValueError(
                f"overview publication {publication['publication_id']} freshness mismatch"
            )
    failures = value.get("failures")
    if not isinstance(failures, list) or len(failures) > _MAX_ITEMS:
        raise ValueError("overview failures are invalid")
    normalized_failures: list[dict[str, Any]] = []
    failure_ids: set[str] = set()
    for index, item in enumerate(failures):
        if not isinstance(item, Mapping) or set(item) != {
            "failure_id",
            "source",
            "observed_at",
            "severity",
            "message",
        }:
            raise ValueError("overview failures are invalid")
        failure_id = _safe_id(item.get("failure_id"), label=f"failures[{index}].failure_id")
        if failure_id in failure_ids:
            raise ValueError("overview failure ids must be unique")
        failure_ids.add(failure_id)
        severity = item.get("severity")
        if severity not in _SEVERITIES:
            raise ValueError(f"failures[{index}].severity is invalid")
        normalized_failures.append(
            {
                "failure_id": failure_id,
                "source": _text(item.get("source"), label=f"failures[{index}].source"),
                "observed_at": _timestamp(
                    item.get("observed_at"),
                    label=f"failures[{index}].observed_at",
                ),
                "severity": severity,
                "message": _text(item.get("message"), label=f"failures[{index}].message"),
            }
        )
    profiles_raw = value.get("display_profiles")
    if not isinstance(profiles_raw, list) or not profiles_raw or len(profiles_raw) > 20:
        raise ValueError("overview display profiles are invalid")
    profiles = [
        validate_profile(item, index=index)
        for index, item in enumerate(profiles_raw)
        if isinstance(item, Mapping)
    ]
    if len(profiles) != len(profiles_raw):
        raise ValueError("overview display profiles are invalid")
    profile_ids = [item["profile_id"] for item in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise ValueError("overview display profile ids must be unique")
    summary = value.get("summary")
    expected_summary_fields = {
        "project_count",
        "view_count",
        "active_job_count",
        "error_count",
        "stale_count",
        "provider_state",
    }
    if not isinstance(summary, Mapping) or set(summary) != expected_summary_fields:
        raise ValueError("overview summary fields are invalid")
    provider_state = summary.get("provider_state")
    if provider_state not in _STATES:
        raise ValueError("summary.provider_state is invalid")
    normalized_summary = {
        "project_count": _bounded_int(
            summary.get("project_count"),
            label="summary.project_count",
            minimum=0,
            maximum=_MAX_ITEMS,
        ),
        "view_count": _bounded_int(
            summary.get("view_count"), label="summary.view_count", minimum=0, maximum=_MAX_ITEMS
        ),
        "active_job_count": _bounded_int(
            summary.get("active_job_count"),
            label="summary.active_job_count",
            minimum=0,
            maximum=_MAX_ITEMS,
        ),
        "error_count": _bounded_int(
            summary.get("error_count"), label="summary.error_count", minimum=0, maximum=_MAX_ITEMS
        ),
        "stale_count": _bounded_int(
            summary.get("stale_count"), label="summary.stale_count", minimum=0, maximum=_MAX_ITEMS
        ),
        "provider_state": provider_state,
    }
    if normalized_summary["project_count"] != len(projects):
        raise ValueError("overview summary project count mismatch")
    if normalized_summary["view_count"] != sum(len(project["views"]) for project in projects):
        raise ValueError("overview summary view count mismatch")
    if normalized_summary["active_job_count"] != len(jobs):
        raise ValueError("overview summary active job count mismatch")
    if normalized_summary["error_count"] != len(normalized_failures):
        raise ValueError("overview summary error count mismatch")
    expected_stale = sum(item["freshness"] == "stale" for item in observations)
    expected_stale += sum(item["freshness"] == "stale" for item in publications)
    expected_stale += sum(item["freshness"] == "stale" for item in jobs)
    if normalized_summary["stale_count"] != expected_stale:
        raise ValueError("overview summary stale count mismatch")
    provider_observations = [
        item for item in observations if item["observation_id"] == "provider.miro.live"
    ]
    if len(provider_observations) != 1:
        raise ValueError("overview provider observation is missing or duplicated")
    if normalized_summary["provider_state"] != provider_observations[0]["state"]:
        raise ValueError("overview summary provider state mismatch")
    expected_boundary = {
        "read_only": True,
        "registry_is_navigation_truth": True,
        "observations_are_time_bound": True,
        "provider_failure_does_not_block_local_diagnostics": True,
        "provider_identifiers_excluded": True,
    }
    if value.get("boundary") != expected_boundary:
        raise ValueError("overview snapshot boundary is invalid")
    normalized = {
        "schema_version": OVERVIEW_SCHEMA,
        "generated_at": generated_at,
        "registry_digest": registry_digest,
        "projects": projects,
        "observations": observations,
        "jobs": jobs,
        "publications": publications,
        "failures": normalized_failures,
        "display_profiles": profiles,
        "summary": normalized_summary,
        "boundary": expected_boundary,
    }
    declared = _digest(value.get("snapshot_digest"), label="snapshot_digest")
    actual = manifest_digest(normalized, "snapshot_digest")
    if declared != actual:
        raise ValueError("overview snapshot digest mismatch")
    normalized["snapshot_digest"] = actual
    return normalized
