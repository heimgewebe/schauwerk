"""Validated operational projection for the Grabowski useful pilot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schauwerk.pilots.grabowski import (
    _write_text_atomic,
    validate_grabowski_snapshot,
)
from schauwerk.registry_runtime import load_registry
from schauwerk.visual.miro_dsl import doc, line, table

OBSERVATION_SCHEMA_VERSION = "grabowski-operational-observation.v1"
SNAPSHOT_SCHEMA_VERSION = "grabowski-operational-snapshot.v1"
RECEIPT_SCHEMA_VERSION = "grabowski-operational-render-receipt.v1"
CHANNEL_ORDER = ("hosts", "runtime", "work", "gaps")
STATUS_ORDER = {"healthy": 0, "partial": 1, "stale": 2, "unavailable": 3}
CHANNEL_SOURCES = {
    "hosts": "grabowski.fleet-observation",
    "runtime": "grabowski.runtime-observation",
    "work": "bureau.grabowski-work-observation",
    "gaps": "bureau.grabowski-gap-observation",
}
CHANNEL_AUTHORITIES = {
    "hosts": "operational",
    "runtime": "operational",
    "work": "operational",
    "gaps": "derived",
}
CHANNEL_TITLES = {
    "hosts": "Hosts",
    "runtime": "Runtime",
    "work": "Arbeit",
    "gaps": "Folgethemen",
}
SUMMARY_FIELDS = {
    "hosts": (
        "declared_count",
        "enabled_count",
        "reachable_count",
        "unavailable_count",
    ),
    "runtime": (
        "running_grabowski_units",
        "expected_tool_count",
        "policy_state",
        "failed_grabowski_units",
    ),
    "work": (
        "active_run_count",
        "open_pr_count",
        "ready_task_count",
        "current_task_state",
    ),
    "gaps": (
        "tracked_followup_count",
        "blocked_count",
        "planned_count",
        "repair_candidate_count",
    ),
}


def _read_json_object(path: Path, *, label: str, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} must be a regular non-symlink file")
        if path.stat().st_size > max_bytes:
            raise ValueError(f"{label} exceeds the size limit")
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{label} is unreadable") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    return value


def _parse_time(value: Any, *, label: str) -> datetime:
    timestamp_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z"
    if not isinstance(value, str) or re.fullmatch(timestamp_pattern, value) is None:
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC3339 UTC timestamp") from exc
    return parsed.astimezone(UTC)


def _digest(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "snapshot_digest"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonnegative_int(value: Any, *, label: str, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"{label} must be a bounded non-negative integer")
    return value


def _validate_summary(channel_id: str, summary: Any) -> dict[str, Any]:
    if not isinstance(summary, Mapping):
        raise ValueError(f"channels.{channel_id}.summary must be an object")
    if set(summary) != set(SUMMARY_FIELDS[channel_id]):
        raise ValueError(f"channels.{channel_id}.summary has unsupported fields")
    result = {key: summary[key] for key in SUMMARY_FIELDS[channel_id]}
    if channel_id == "hosts":
        for key in SUMMARY_FIELDS[channel_id]:
            result[key] = _nonnegative_int(result[key], label=f"hosts.{key}")
        if result["enabled_count"] > result["declared_count"]:
            raise ValueError("hosts.enabled_count exceeds declared_count")
        if result["reachable_count"] + result["unavailable_count"] != result["enabled_count"]:
            raise ValueError("host reachability counts must equal enabled_count")
    elif channel_id == "runtime":
        if result["policy_state"] not in {"bounded", "degraded", "unknown"}:
            raise ValueError("runtime.policy_state is invalid")
        for key in (
            "running_grabowski_units",
            "expected_tool_count",
            "failed_grabowski_units",
        ):
            result[key] = _nonnegative_int(result[key], label=f"runtime.{key}")
    elif channel_id == "work":
        if result["current_task_state"] not in {
            "none",
            "ready",
            "assigned",
            "running",
            "verifying",
            "blocked",
        }:
            raise ValueError("work.current_task_state is invalid")
        for key in ("active_run_count", "open_pr_count", "ready_task_count"):
            result[key] = _nonnegative_int(result[key], label=f"work.{key}")
    else:
        for key in SUMMARY_FIELDS[channel_id]:
            result[key] = _nonnegative_int(result[key], label=f"gaps.{key}")
        if result["blocked_count"] + result["planned_count"] > result["tracked_followup_count"]:
            raise ValueError("gap state counts exceed tracked_followup_count")
    return result


def _channel_state(
    channel_id: str,
    *,
    collection_status: str,
    age_seconds: int,
    stale_after: int,
    summary: Mapping[str, Any] | None,
) -> str:
    if collection_status == "unavailable":
        return "unavailable"
    if age_seconds > stale_after:
        return "stale"
    if collection_status == "partial":
        return "partial"
    if summary is None:
        return "unavailable"
    if channel_id == "hosts" and summary["unavailable_count"] > 0:
        return "partial"
    if channel_id == "runtime" and (
        summary["running_grabowski_units"] == 0
        or summary["policy_state"] != "bounded"
        or summary["failed_grabowski_units"] > 0
    ):
        return "partial"
    if channel_id == "work" and summary["current_task_state"] == "blocked":
        return "partial"
    if channel_id == "gaps" and (
        summary["blocked_count"] > 0 or summary["repair_candidate_count"] > 0
    ):
        return "partial"
    return "healthy"


def _overall_status(channels: Mapping[str, Mapping[str, Any]]) -> tuple[str, Counter[str]]:
    counts = Counter(str(item["state"]) for item in channels.values())
    worst = max(channels.values(), key=lambda item: STATUS_ORDER[str(item["state"])])["state"]
    overall = (
        "healthy"
        if worst == "healthy"
        else ("unavailable" if counts["unavailable"] == len(CHANNEL_ORDER) else "degraded")
    )
    return overall, counts


def _validate_hex_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _validate_normalized_channel(
    channel_id: str,
    channel: Any,
    *,
    evaluated_at: datetime,
) -> dict[str, Any]:
    if not isinstance(channel, Mapping):
        raise ValueError(f"operational snapshot channel {channel_id} must be an object")
    expected_keys = {
        "source_id",
        "authority",
        "freshness_contract",
        "observed_at",
        "age_seconds",
        "stale_after_seconds",
        "collection_status",
        "state",
        "error_code",
        "summary",
    }
    if set(channel) != expected_keys:
        raise ValueError(f"operational snapshot channel {channel_id} has unsupported fields")
    if channel.get("source_id") != CHANNEL_SOURCES[channel_id]:
        raise ValueError(f"operational snapshot channel {channel_id} source is invalid")
    if channel.get("authority") != CHANNEL_AUTHORITIES[channel_id]:
        raise ValueError(f"operational snapshot channel {channel_id} authority is invalid")
    if channel.get("freshness_contract") != "live":
        raise ValueError(f"operational snapshot channel {channel_id} freshness is invalid")
    observed_at = _parse_time(
        channel.get("observed_at"), label=f"channels.{channel_id}.observed_at"
    )
    if int((observed_at - evaluated_at).total_seconds()) > 300:
        raise ValueError(f"operational snapshot channel {channel_id} is too far in the future")
    expected_age = max(0, int((evaluated_at - observed_at).total_seconds()))
    age_seconds = _nonnegative_int(
        channel.get("age_seconds"), label=f"channels.{channel_id}.age_seconds"
    )
    if age_seconds != expected_age:
        raise ValueError(f"operational snapshot channel {channel_id} age does not match timestamps")
    stale_after = _nonnegative_int(
        channel.get("stale_after_seconds"),
        label=f"channels.{channel_id}.stale_after_seconds",
        maximum=604_800,
    )
    if stale_after < 60:
        raise ValueError(f"operational snapshot channel {channel_id} stale limit is too small")
    collection_status = channel.get("collection_status")
    if collection_status not in {"ok", "partial", "unavailable"}:
        raise ValueError(f"operational snapshot channel {channel_id} collection status is invalid")
    error_code = channel.get("error_code")
    if collection_status == "ok":
        if error_code is not None:
            raise ValueError(f"operational snapshot channel {channel_id} error must be null")
    elif not isinstance(error_code, str) or re.fullmatch(r"[a-z0-9_]{1,64}", error_code) is None:
        raise ValueError(f"operational snapshot channel {channel_id} error code is invalid")
    summary = channel.get("summary")
    if collection_status == "unavailable":
        if summary is not None:
            raise ValueError(f"operational snapshot channel {channel_id} summary must be null")
        normalized_summary = None
    else:
        normalized_summary = _validate_summary(channel_id, summary)
    expected_state = _channel_state(
        channel_id,
        collection_status=str(collection_status),
        age_seconds=age_seconds,
        stale_after=stale_after,
        summary=normalized_summary,
    )
    if channel.get("state") != expected_state:
        raise ValueError(f"operational snapshot channel {channel_id} state mismatch")
    return dict(channel)


def compile_operational_snapshot(
    static_snapshot_path: Path,
    observation_path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    static_snapshot = _read_json_object(static_snapshot_path, label="static snapshot")
    validate_grabowski_snapshot(static_snapshot)
    static_expected_tool_count = _nonnegative_int(
        static_snapshot["summary"].get("expected_tool_count"),
        label="static snapshot expected_tool_count",
    )
    observation = _read_json_object(observation_path, label="operational observation")
    if observation.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        raise ValueError("unsupported operational observation schema")
    if set(observation) != {"schema_version", "evaluated_at", "channels"}:
        raise ValueError("operational observation has unsupported fields")
    evaluated_at = _parse_time(observation.get("evaluated_at"), label="evaluated_at")
    channels = observation.get("channels")
    if not isinstance(channels, Mapping) or set(channels) != set(CHANNEL_ORDER):
        raise ValueError("operational observation must contain exactly four channels")

    registry = load_registry(repo_root)
    sources = {item["id"]: item for item in registry["sources"]}
    view = next(
        (
            item
            for item in registry["views"]
            if item["id"] == "grabowski.operator-operational-overview"
        ),
        None,
    )
    if view is None:
        raise ValueError("operational Grabowski view declaration is missing")
    required_view_sources = set(CHANNEL_SOURCES.values()) | {"grabowski.operator-context"}
    if not required_view_sources.issubset(set(view.get("source_ids", []))):
        raise ValueError("operational Grabowski view source declarations are incomplete")

    normalized: dict[str, Any] = {}
    for channel_id in CHANNEL_ORDER:
        raw = channels[channel_id]
        if not isinstance(raw, Mapping):
            raise ValueError(f"channels.{channel_id} must be an object")
        expected_keys = {
            "source_id",
            "authority",
            "observed_at",
            "stale_after_seconds",
            "collection_status",
            "error_code",
            "summary",
        }
        if set(raw) != expected_keys:
            raise ValueError(f"channels.{channel_id} has unsupported fields")
        source_id = raw.get("source_id")
        if source_id != CHANNEL_SOURCES[channel_id] or source_id not in sources:
            raise ValueError(f"channels.{channel_id}.source_id is invalid")
        source = sources[source_id]
        if source.get("freshness") != "live":
            raise ValueError(f"channels.{channel_id}.source is not declared live")
        if raw.get("authority") != source["authority"]:
            raise ValueError(f"channels.{channel_id}.authority does not match registry")
        observed_at = _parse_time(
            raw.get("observed_at"), label=f"channels.{channel_id}.observed_at"
        )
        future_seconds = int((observed_at - evaluated_at).total_seconds())
        if future_seconds > 300:
            raise ValueError(f"channels.{channel_id}.observed_at is too far in the future")
        age_seconds = max(0, int((evaluated_at - observed_at).total_seconds()))
        stale_after = _nonnegative_int(
            raw.get("stale_after_seconds"),
            label=f"channels.{channel_id}.stale_after_seconds",
            maximum=604_800,
        )
        if stale_after < 60:
            raise ValueError(f"channels.{channel_id}.stale_after_seconds is too small")
        collection_status = raw.get("collection_status")
        if collection_status not in {"ok", "partial", "unavailable"}:
            raise ValueError(f"channels.{channel_id}.collection_status is invalid")
        error_code = raw.get("error_code")
        if collection_status == "ok" and error_code is not None:
            raise ValueError(f"channels.{channel_id}.error_code must be null when status is ok")
        if collection_status != "ok":
            if (
                not isinstance(error_code, str)
                or re.fullmatch(r"[a-z0-9_]{1,64}", error_code) is None
            ):
                raise ValueError(f"channels.{channel_id}.error_code is invalid")
        summary = raw.get("summary")
        if collection_status == "unavailable":
            if summary is not None:
                raise ValueError(f"channels.{channel_id}.summary must be null when unavailable")
            normalized_summary = None
        else:
            normalized_summary = _validate_summary(channel_id, summary)
            if (
                channel_id == "runtime"
                and normalized_summary["expected_tool_count"] != static_expected_tool_count
            ):
                raise ValueError("runtime expected tool count does not match static snapshot")
        normalized[channel_id] = {
            "source_id": source_id,
            "authority": source["authority"],
            "freshness_contract": source["freshness"],
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "age_seconds": age_seconds,
            "stale_after_seconds": stale_after,
            "collection_status": collection_status,
            "state": _channel_state(
                channel_id,
                collection_status=collection_status,
                age_seconds=age_seconds,
                stale_after=stale_after,
                summary=normalized_summary,
            ),
            "error_code": error_code,
            "summary": normalized_summary,
        }

    overall, counts = _overall_status(normalized)
    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_id": "grabowski",
        "view_id": view["id"],
        "evaluated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "static_snapshot": {
            "snapshot_digest": static_snapshot["snapshot_digest"],
            "source_sha256": static_snapshot["source"]["sha256"],
            "expected_tool_count": static_expected_tool_count,
        },
        "overall_status": overall,
        "channel_state_counts": {key: counts.get(key, 0) for key in STATUS_ORDER},
        "channels": normalized,
        "boundaries": {
            "source_systems_remain_authoritative": True,
            "contains_raw_command_output": False,
            "contains_secret_values": False,
            "contains_host_identifiers": False,
            "provider_mutation_attempted": False,
        },
    }
    snapshot["snapshot_digest"] = _digest(snapshot)
    return snapshot


def validate_operational_snapshot(snapshot: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version",
        "project_id",
        "view_id",
        "evaluated_at",
        "static_snapshot",
        "overall_status",
        "channel_state_counts",
        "channels",
        "boundaries",
        "snapshot_digest",
    }
    if set(snapshot) != expected_keys:
        raise ValueError("operational snapshot has unsupported fields")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported operational snapshot schema")
    digest = _validate_hex_digest(
        snapshot.get("snapshot_digest"), label="operational snapshot digest"
    )
    if digest != _digest(snapshot):
        raise ValueError("operational snapshot digest mismatch")
    if (
        snapshot.get("project_id") != "grabowski"
        or snapshot.get("view_id") != "grabowski.operator-operational-overview"
    ):
        raise ValueError("operational snapshot identity is invalid")
    evaluated_at = _parse_time(snapshot.get("evaluated_at"), label="evaluated_at")
    static_ref = snapshot.get("static_snapshot")
    if not isinstance(static_ref, Mapping) or set(static_ref) != {
        "snapshot_digest",
        "source_sha256",
        "expected_tool_count",
    }:
        raise ValueError("operational snapshot static binding is invalid")
    _validate_hex_digest(
        static_ref.get("snapshot_digest"), label="operational static snapshot digest"
    )
    _validate_hex_digest(static_ref.get("source_sha256"), label="operational static source digest")
    static_expected_tool_count = _nonnegative_int(
        static_ref.get("expected_tool_count"), label="operational static expected_tool_count"
    )
    channels = snapshot.get("channels")
    if not isinstance(channels, Mapping) or set(channels) != set(CHANNEL_ORDER):
        raise ValueError("operational snapshot channels are invalid")
    validated_channels = {
        channel_id: _validate_normalized_channel(
            channel_id, channels[channel_id], evaluated_at=evaluated_at
        )
        for channel_id in CHANNEL_ORDER
    }
    runtime_summary = validated_channels["runtime"].get("summary")
    if (
        isinstance(runtime_summary, Mapping)
        and runtime_summary["expected_tool_count"] != static_expected_tool_count
    ):
        raise ValueError("operational runtime expected tool count mismatch")
    expected_overall, expected_counts = _overall_status(validated_channels)
    counts = snapshot.get("channel_state_counts")
    if not isinstance(counts, Mapping) or set(counts) != set(STATUS_ORDER):
        raise ValueError("operational snapshot channel counts are invalid")
    normalized_counts = {
        state: _nonnegative_int(counts[state], label=f"channel_state_counts.{state}", maximum=4)
        for state in STATUS_ORDER
    }
    if sum(normalized_counts.values()) != len(CHANNEL_ORDER):
        raise ValueError("operational snapshot channel counts do not total four")
    if normalized_counts != {state: expected_counts.get(state, 0) for state in STATUS_ORDER}:
        raise ValueError("operational snapshot channel counts mismatch")
    if snapshot.get("overall_status") != expected_overall:
        raise ValueError("operational snapshot overall status mismatch")
    boundaries = snapshot.get("boundaries")
    if boundaries != {
        "source_systems_remain_authoritative": True,
        "contains_raw_command_output": False,
        "contains_secret_values": False,
        "contains_host_identifiers": False,
        "provider_mutation_attempted": False,
    }:
        raise ValueError("operational snapshot boundaries are invalid")


def _summary_rows(channel_id: str, channel: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    summary = channel.get("summary")
    if not isinstance(summary, Mapping):
        return (("Status", "Quelle nicht verfügbar"), ("Fehler", str(channel.get("error_code"))))
    return tuple((key.replace("_", " "), str(value)) for key, value in summary.items())


def render_operational_dsl(
    static_snapshot: Mapping[str, Any], operational: Mapping[str, Any]
) -> str:
    validate_grabowski_snapshot(static_snapshot)
    validate_operational_snapshot(operational)
    expected_static = {
        "snapshot_digest": static_snapshot["snapshot_digest"],
        "source_sha256": static_snapshot["source"]["sha256"],
        "expected_tool_count": static_snapshot["summary"]["expected_tool_count"],
    }
    if operational["static_snapshot"] != expected_static:
        raise ValueError("operational snapshot is bound to a different static snapshot")
    static_summary = static_snapshot["summary"]
    channels = operational["channels"]
    lines = [
        line("root", "FRAME", x=0, y=0, w=4400, h=2200, content="Grabowski Operational Overview"),
        line(
            "title",
            "TEXT",
            parent="root",
            x=2200,
            y=80,
            w=2800,
            size=34,
            align="center",
            content="Grabowski — Vertrag und beobachteter Betrieb",
        ),
        line("static", "FRAME", x=-1450, y=300, w=900, h=1450, content="Statischer Vertrag"),
        line("live", "FRAME", x=0, y=300, w=1800, h=1450, content="Beobachteter Zustand"),
        line("gaps", "FRAME", x=1450, y=300, w=900, h=1450, content="Lücken und Grenzen"),
        doc(
            "static_doc",
            parent="static",
            x=450,
            y=300,
            markdown=(
                f"# Zweck\n\n{static_summary['purpose']}\n\n"
                f"**Profil:** {static_summary['active_profile']}\n\n"
                f"**Fähigkeiten:** {static_summary['capability_count']}\n\n"
                "Diese Angaben stammen aus dem versionierten Operator-Vertrag, "
                "nicht aus Livebeobachtung."
            ),
        ),
    ]
    positions = {
        "hosts": (420, 300),
        "runtime": (1320, 300),
        "work": (420, 970),
        "gaps": (450, 300),
    }
    for channel_id in CHANNEL_ORDER:
        channel = channels[channel_id]
        parent = "gaps" if channel_id == "gaps" else "live"
        x, y = positions[channel_id]
        lines.append(
            table(
                f"{channel_id}_table",
                parent=parent,
                x=x,
                y=y,
                title=f"{CHANNEL_TITLES[channel_id]} · {channel['state']}",
                columns=("Merkmal", "Wert"),
                rows=_summary_rows(channel_id, channel),
            )
        )
        if channel_id != "gaps":
            lines.append(
                line(
                    f"{channel_id}_freshness",
                    "TEXT",
                    parent=parent,
                    x=x,
                    y=y + 430,
                    w=720,
                    size=16,
                    align="center",
                    content=(
                        f"Quelle: {channel['source_id']} · Alter: {channel['age_seconds']} s · "
                        f"Verfall: {channel['stale_after_seconds']} s"
                    ),
                )
            )
    lines.extend(
        [
            line(
                "boundary",
                "SHAPE",
                parent="gaps",
                x=450,
                y=1050,
                w=680,
                h=320,
                type="round_rectangle",
                content=(
                    "Quellsysteme bleiben maßgeblich. Die Ansicht enthält nur "
                    "Zustandsklassen und Summen: "
                    "keine Rohlogs, Geheimnisse, Hostnamen oder Provider-Mutation."
                ),
            ),
            line(
                "overall",
                "SHAPE",
                parent="root",
                x=2200,
                y=1930,
                w=1700,
                h=180,
                type="round_rectangle",
                content=(
                    f"Gesamtzustand: {operational['overall_status']} · "
                    f"healthy={operational['channel_state_counts']['healthy']} · "
                    f"partial={operational['channel_state_counts']['partial']} · "
                    f"stale={operational['channel_state_counts']['stale']} · "
                    f"unavailable={operational['channel_state_counts']['unavailable']}"
                ),
            ),
            line(
                "footer",
                "TEXT",
                parent="root",
                x=2200,
                y=2130,
                w=2800,
                size=16,
                align="center",
                content=(
                    f"Operational snapshot {str(operational['snapshot_digest'])[:16]} · "
                    f"bewertet {operational['evaluated_at']}"
                ),
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def write_operational_pilot(
    *,
    static_snapshot_path: Path,
    observation_path: Path,
    snapshot_output: Path | None,
    dsl_output: Path | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    static_snapshot = _read_json_object(static_snapshot_path, label="static snapshot")
    operational = compile_operational_snapshot(
        static_snapshot_path, observation_path, repo_root=repo_root
    )
    dsl = render_operational_dsl(static_snapshot, operational)
    if snapshot_output is not None:
        _write_text_atomic(
            snapshot_output, json.dumps(operational, indent=2, sort_keys=True) + "\n"
        )
    if dsl_output is not None:
        _write_text_atomic(dsl_output, dsl)
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "project_id": "grabowski",
        "view_id": operational["view_id"],
        "snapshot_digest": operational["snapshot_digest"],
        "overall_status": operational["overall_status"],
        "snapshot_output": str(snapshot_output) if snapshot_output else None,
        "dsl_output": str(dsl_output) if dsl_output else None,
        "dsl_line_count": len([item for item in dsl.splitlines() if item.strip()]),
        "provider_mutation_attempted": False,
    }
