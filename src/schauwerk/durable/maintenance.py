"""SW-015 proposal-first maintenance for generated regions.

This module never invokes a renderer or provider. It only compares two validated
observation sets and emits a deterministic review bundle.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..registry_runtime import load_registry, registry_digest
from .adapters import validate_observation_set
from .common import (
    DurableError,
    bind_digest,
    parse_timestamp,
    read_json,
    require_bound_digest,
    safe_identifier,
    stable_digest,
)

PROPOSAL_SCHEMA = "schauwerk-maintenance-proposal.v1"
_ALLOWED_REGION_MODE = "managed"


def _region(registry: Mapping[str, Any], region_id: str) -> dict[str, Any]:
    for item in registry.get("regions", []):
        if item.get("id") == region_id:
            return dict(item)
    raise DurableError(f"region is not declared in the registry: {region_id}")


def _observations(value: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["source"]["id"]: item for item in value["observations"]}


def _fact_map(observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in observation["facts"]}


def _contradictions(current: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_key: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for observation in current["observations"]:
        if observation["status"] != "healthy":
            continue
        source_id = observation["source"]["id"]
        for fact in observation["facts"]:
            by_key.setdefault(fact["key"], []).append((source_id, fact))
    conflicts: list[dict[str, Any]] = []
    for key, records in sorted(by_key.items()):
        values = {stable_digest(record[1]["value"]) for record in records}
        if len(values) <= 1:
            continue
        conflicts.append(
            {
                "fact_key": key,
                "fact_refs": sorted(f"{source_id}:{fact['key']}" for source_id, fact in records),
                "value_digests": sorted(values),
                "reason": "healthy sources disagree",
            }
        )
    return conflicts


def compile_maintenance_proposal(
    previous_set: Mapping[str, Any],
    current_set: Mapping[str, Any],
    *,
    region_id: str,
    created_at: str,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    previous = validate_observation_set(previous_set)
    current = validate_observation_set(current_set)
    loaded_registry = dict(registry) if registry is not None else load_registry()
    region_identifier = safe_identifier(region_id, label="region_id")
    region = _region(loaded_registry, region_identifier)
    eligible = region["management_mode"] == _ALLOWED_REGION_MODE
    blocked: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    contradictions = _contradictions(current)
    contradictory_keys = {item["fact_key"] for item in contradictions}

    if not eligible:
        blocked.append(
            {
                "scope": f"region:{region_identifier}",
                "reason": f"management mode {region['management_mode']} is not automation-managed",
            }
        )
    else:
        before_by_source = _observations(previous)
        after_by_source = _observations(current)
        for source_id in sorted(set(before_by_source) | set(after_by_source)):
            before = before_by_source.get(source_id)
            after = after_by_source.get(source_id)
            if after is None:
                blocked.append(
                    {"scope": f"source:{source_id}", "reason": "current observation is missing"}
                )
                continue
            if after["status"] != "healthy":
                blocked.append(
                    {
                        "scope": f"source:{source_id}",
                        "reason": f"current observation is {after['status']}",
                    }
                )
                continue
            before_facts = _fact_map(before) if before and before["status"] == "healthy" else {}
            after_facts = _fact_map(after)
            for key in sorted(set(before_facts) | set(after_facts)):
                fact_ref = f"{source_id}:{key}"
                if key in contradictory_keys:
                    blocked.append(
                        {"scope": f"fact:{fact_ref}", "reason": "contradiction detected"}
                    )
                    continue
                old = before_facts.get(key)
                new = after_facts.get(key)
                if old is None and new is not None:
                    kind = "add"
                elif old is not None and new is None:
                    kind = "remove"
                elif (
                    old is not None and new is not None and old["fact_digest"] != new["fact_digest"]
                ):
                    kind = "update"
                else:
                    continue
                operation = {
                    "operation_id": safe_identifier(
                        f"{kind}.{stable_digest(fact_ref)[:16]}", label="operation_id"
                    ),
                    "kind": kind,
                    "fact_ref": fact_ref,
                    "before": old["value"] if old is not None else None,
                    "after": new["value"] if new is not None else None,
                    "visibility": (new or old)["visibility"],
                    "citation_ids": (new or old)["citation_ids"],
                    "reason": "declared source observation changed",
                    "operation_digest": "",
                }
                operations.append(bind_digest(operation, "operation_digest"))

    operations.sort(key=lambda item: item["operation_id"])
    blocked = sorted(
        {stable_digest(item): item for item in blocked}.values(),
        key=lambda item: (item["scope"], item["reason"]),
    )
    proposal = {
        "schema_version": PROPOSAL_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "region": {
            "id": region_identifier,
            "management_mode": region["management_mode"],
            "marker_prefix": region.get("marker_prefix"),
            "eligible": eligible,
        },
        "previous_set_digest": previous["set_digest"],
        "current_set_digest": current["set_digest"],
        "registry_digest": registry_digest(loaded_registry),
        "operations": operations,
        "blocked": blocked,
        "contradictions": contradictions,
        "summary": {
            "operation_count": len(operations),
            "blocked_count": len(blocked),
            "contradiction_count": len(contradictions),
            "ready_for_review": eligible and bool(operations) and not blocked,
        },
        "review_required": True,
        "provider_effect_authorized": False,
        "mutation_attempted": False,
        "proposal_digest": "",
    }
    return bind_digest(proposal, "proposal_digest")


def validate_maintenance_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "created_at",
        "region",
        "previous_set_digest",
        "current_set_digest",
        "registry_digest",
        "operations",
        "blocked",
        "contradictions",
        "summary",
        "review_required",
        "provider_effect_authorized",
        "mutation_attempted",
        "proposal_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise DurableError("maintenance proposal fields are invalid")
    if value.get("schema_version") != PROPOSAL_SCHEMA:
        raise DurableError("maintenance proposal schema is unsupported")
    parse_timestamp(value.get("created_at"), label="created_at")
    region = value.get("region")
    if not isinstance(region, Mapping) or set(region) != {
        "id",
        "management_mode",
        "marker_prefix",
        "eligible",
    }:
        raise DurableError("maintenance proposal region is invalid")
    safe_identifier(region.get("id"), label="region id")
    if region.get("eligible") is not (region.get("management_mode") == _ALLOWED_REGION_MODE):
        raise DurableError("maintenance proposal eligibility is invalid")
    for name in ("previous_set_digest", "current_set_digest", "registry_digest"):
        from .common import safe_digest

        safe_digest(value.get(name), label=name)
    operations = value.get("operations")
    blocked = value.get("blocked")
    contradictions = value.get("contradictions")
    if (
        not isinstance(operations, list)
        or not isinstance(blocked, list)
        or not isinstance(contradictions, list)
    ):
        raise DurableError("maintenance proposal collections are invalid")
    for operation in operations:
        if not isinstance(operation, Mapping):
            raise DurableError("maintenance operation is invalid")
        require_bound_digest(operation, "operation_digest", label="maintenance operation")
    summary = value.get("summary")
    expected_summary = {
        "operation_count": len(operations),
        "blocked_count": len(blocked),
        "contradiction_count": len(contradictions),
        "ready_for_review": bool(region["eligible"] and operations and not blocked),
    }
    if summary != expected_summary:
        raise DurableError("maintenance proposal summary is invalid")
    if (
        value.get("review_required") is not True
        or value.get("provider_effect_authorized") is not False
    ):
        raise DurableError("maintenance proposal authority boundary is invalid")
    if value.get("mutation_attempted") is not False:
        raise DurableError("maintenance proposal must not report mutation")
    require_bound_digest(value, "proposal_digest", label="maintenance proposal")
    return dict(value)


def load_maintenance_proposal(path: Path) -> dict[str, Any]:
    return validate_maintenance_proposal(read_json(path, label="maintenance proposal"))
