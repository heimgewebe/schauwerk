"""SW-014 local source adapters with explicit authority, freshness and failure state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..registry_runtime import load_registry, registry_digest
from .common import (
    DurableError,
    bind_digest,
    bounded_text,
    parse_timestamp,
    read_json,
    require_bound_digest,
    safe_digest,
    safe_identifier,
    safe_scalar,
    safe_visibility,
    stable_digest,
    timestamp_value,
)

CATALOG_SCHEMA = "schauwerk-adapter-catalog.v1"
INPUT_SCHEMA = "schauwerk-adapter-input.v1"
OBSERVATION_SCHEMA = "schauwerk-source-observation.v1"
SET_SCHEMA = "schauwerk-source-observation-set.v1"


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    title: str
    source_kinds: frozenset[str]
    authorities: frozenset[str]
    optional: bool = False


_ALL_KINDS = frozenset(
    {
        "git-repository",
        "github-repository",
        "generated-artifact",
        "document",
        "miro-board",
        "local-artifact",
        "runtime-observation",
    }
)
_ALL_AUTHORITIES = frozenset({"canonical", "operational", "derived"})
ADAPTERS: tuple[AdapterSpec, ...] = (
    AdapterSpec("git", "Git repository", frozenset({"git-repository"}), frozenset({"canonical"})),
    AdapterSpec(
        "github",
        "GitHub repository",
        frozenset({"github-repository"}),
        frozenset({"operational"}),
    ),
    AdapterSpec(
        "systemkatalog",
        "Systemkatalog artifact",
        frozenset({"generated-artifact", "local-artifact", "document"}),
        frozenset({"canonical", "derived"}),
    ),
    AdapterSpec(
        "repoground",
        "RepoGround repository brief bundle",
        frozenset({"generated-artifact", "local-artifact"}),
        frozenset({"derived", "operational"}),
    ),
    AdapterSpec(
        "generic", "Declared local JSON source", _ALL_KINDS, _ALL_AUTHORITIES, optional=True
    ),
)
_ADAPTERS = {item.adapter_id: item for item in ADAPTERS}
_VISIBILITY_EXPOSURE = {"private": 0, "shared": 1, "classroom": 2, "public": 3}


def adapter_catalog() -> dict[str, Any]:
    value = {
        "schema_version": CATALOG_SCHEMA,
        "adapters": [
            {
                "adapter_id": item.adapter_id,
                "title": item.title,
                "source_kinds": sorted(item.source_kinds),
                "authorities": sorted(item.authorities),
                "optional": item.optional,
                "transport": "declared-local-json",
                "failure_semantics": "visible-no-fabrication",
            }
            for item in ADAPTERS
        ],
        "catalog_digest": "",
    }
    return bind_digest(value, "catalog_digest")


def _adapter(adapter_id: Any) -> AdapterSpec:
    identifier = safe_identifier(adapter_id, label="adapter_id")
    try:
        return _ADAPTERS[identifier]
    except KeyError as exc:
        raise DurableError(f"unknown adapter: {identifier}") from exc


def _source(registry: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    for item in registry.get("sources", []):
        if item.get("id") == source_id:
            return dict(item)
    raise DurableError(f"source is not declared in the registry: {source_id}")


def _visibility_not_broader(source_visibility: str, item_visibility: str) -> bool:
    if source_visibility == "archived":
        return item_visibility in {"archived", "private"}
    if item_visibility == "archived":
        return True
    return _VISIBILITY_EXPOSURE[item_visibility] <= _VISIBILITY_EXPOSURE[source_visibility]


def _validate_citations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 128:
        raise DurableError("citations must be a bounded list")
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"id", "label", "revision", "sha256"}:
            raise DurableError(f"citations[{index}] fields are invalid")
        identifier = safe_identifier(item.get("id"), label=f"citations[{index}].id")
        if identifier in seen:
            raise DurableError("citation ids must be unique")
        seen.add(identifier)
        citations.append(
            {
                "id": identifier,
                "label": bounded_text(item.get("label"), label=f"citations[{index}].label"),
                "revision": bounded_text(
                    item.get("revision"), label=f"citations[{index}].revision", maximum=200
                ),
                "sha256": safe_digest(item.get("sha256"), label=f"citations[{index}].sha256"),
            }
        )
    return sorted(citations, key=lambda item: item["id"])


def _validate_errors(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise DurableError("errors must be a bounded list")
    return sorted({bounded_text(item, label="adapter error", maximum=1000) for item in value})


def _validate_input_facts(
    value: Any,
    *,
    source: Mapping[str, Any],
    citation_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 512:
        raise DurableError("facts must be a bounded list")
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        expected = {"key", "value", "visibility", "citation_ids"}
        if not isinstance(item, Mapping) or set(item) != expected:
            raise DurableError(f"facts[{index}] fields are invalid")
        key = safe_identifier(item.get("key"), label=f"facts[{index}].key")
        if key in seen:
            raise DurableError("fact keys must be unique within one observation")
        seen.add(key)
        visibility = safe_visibility(item.get("visibility"), label=f"facts[{index}].visibility")
        if not _visibility_not_broader(str(source["visibility"]), visibility):
            raise DurableError(f"facts[{index}] visibility is broader than its source")
        refs = item.get("citation_ids")
        if not isinstance(refs, list) or not refs:
            raise DurableError(f"facts[{index}] requires citations")
        normalized_refs = sorted(
            {safe_identifier(ref, label=f"facts[{index}].citation_id") for ref in refs}
        )
        if any(ref not in citation_ids for ref in normalized_refs):
            raise DurableError(f"facts[{index}] cites an unknown citation")
        facts.append(
            {
                "key": key,
                "value": safe_scalar(item.get("value"), label=f"facts[{index}].value"),
                "visibility": visibility,
                "citation_ids": normalized_refs,
            }
        )
    return sorted(facts, key=lambda item: item["key"])


def compile_observation(
    input_value: Mapping[str, Any],
    *,
    evaluated_at: str,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version",
        "adapter_id",
        "source_id",
        "observed_at",
        "expires_at",
        "collection_state",
        "facts",
        "citations",
        "errors",
    }
    if not isinstance(input_value, Mapping) or set(input_value) != expected:
        raise DurableError("adapter input fields are invalid")
    if input_value.get("schema_version") != INPUT_SCHEMA:
        raise DurableError("adapter input schema is unsupported")
    spec = _adapter(input_value.get("adapter_id"))
    source_id = safe_identifier(input_value.get("source_id"), label="source_id")
    loaded_registry = dict(registry) if registry is not None else load_registry()
    source = _source(loaded_registry, source_id)
    if source["kind"] not in spec.source_kinds:
        raise DurableError(
            f"adapter {spec.adapter_id} does not accept source kind {source['kind']}"
        )
    if source["authority"] not in spec.authorities:
        raise DurableError(
            f"adapter {spec.adapter_id} does not accept source authority {source['authority']}"
        )
    observed_at = parse_timestamp(input_value.get("observed_at"), label="observed_at")
    evaluated = parse_timestamp(evaluated_at, label="evaluated_at")
    collection_state = input_value.get("collection_state")
    if collection_state not in {"complete", "partial", "failed"}:
        raise DurableError("collection_state is invalid")
    expires_at = parse_timestamp(
        input_value.get("expires_at"), label="expires_at", nullable=collection_state == "failed"
    )
    if collection_state != "failed" and expires_at is None:
        raise DurableError("non-failed collection requires expires_at")
    if expires_at is not None and timestamp_value(expires_at) <= timestamp_value(observed_at):
        raise DurableError("expires_at must be after observed_at")
    citations = _validate_citations(input_value.get("citations"))
    facts = _validate_input_facts(
        input_value.get("facts"),
        source=source,
        citation_ids={item["id"] for item in citations},
    )
    errors = _validate_errors(input_value.get("errors"))
    if collection_state == "complete" and (not facts or errors):
        raise DurableError("complete collection requires facts and no errors")
    if collection_state == "partial" and (not facts or not errors):
        raise DurableError("partial collection requires facts and errors")
    if collection_state == "failed" and (
        facts or citations or not errors or expires_at is not None
    ):
        raise DurableError("failed collection requires only errors and no expiry")

    if collection_state == "failed":
        status = "failed"
    elif collection_state == "partial":
        status = "partial"
    elif timestamp_value(evaluated) >= timestamp_value(str(expires_at)):
        status = "stale"
    else:
        status = "healthy"
    current_usable = status == "healthy"
    normalized_facts: list[dict[str, Any]] = []
    for fact in facts:
        normalized = {
            **fact,
            "source_authority": source["authority"],
            "effective_authority": source["authority"] if current_usable else "derived",
            "fresh": current_usable,
            "fact_digest": "",
        }
        normalized_facts.append(bind_digest(normalized, "fact_digest"))

    observation = {
        "schema_version": OBSERVATION_SCHEMA,
        "adapter_id": spec.adapter_id,
        "optional_adapter": spec.optional,
        "source": {
            "id": source_id,
            "kind": source["kind"],
            "authority": source["authority"],
            "visibility": source["visibility"],
            "freshness": source["freshness"],
            "reference_digest": stable_digest(source["reference"]),
        },
        "observed_at": observed_at,
        "expires_at": expires_at,
        "evaluated_at": evaluated,
        "status": status,
        "current_usable": current_usable,
        "facts": normalized_facts,
        "citations": citations,
        "errors": errors,
        "registry_digest": registry_digest(loaded_registry),
        "input_digest": stable_digest(input_value),
        "mutation_attempted": False,
        "observation_digest": "",
    }
    return bind_digest(observation, "observation_digest")


def validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "adapter_id",
        "optional_adapter",
        "source",
        "observed_at",
        "expires_at",
        "evaluated_at",
        "status",
        "current_usable",
        "facts",
        "citations",
        "errors",
        "registry_digest",
        "input_digest",
        "mutation_attempted",
        "observation_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise DurableError("observation fields are invalid")
    if value.get("schema_version") != OBSERVATION_SCHEMA:
        raise DurableError("observation schema is unsupported")
    spec = _adapter(value.get("adapter_id"))
    if value.get("optional_adapter") is not spec.optional:
        raise DurableError("observation optional_adapter mismatch")
    source = value.get("source")
    if not isinstance(source, Mapping) or set(source) != {
        "id",
        "kind",
        "authority",
        "visibility",
        "freshness",
        "reference_digest",
    }:
        raise DurableError("observation source fields are invalid")
    safe_identifier(source.get("id"), label="observation source id")
    if (
        source.get("kind") not in spec.source_kinds
        or source.get("authority") not in spec.authorities
    ):
        raise DurableError("observation source is incompatible with its adapter")
    safe_visibility(source.get("visibility"), label="observation source visibility")
    bounded_text(source.get("freshness"), label="observation source freshness")
    safe_digest(source.get("reference_digest"), label="reference_digest")
    observed_at = parse_timestamp(value.get("observed_at"), label="observed_at")
    evaluated_at = parse_timestamp(value.get("evaluated_at"), label="evaluated_at")
    status = value.get("status")
    if status not in {"healthy", "stale", "partial", "failed"}:
        raise DurableError("observation status is invalid")
    expires_at = parse_timestamp(value.get("expires_at"), label="expires_at", nullable=True)
    if status == "failed" and expires_at is not None:
        raise DurableError("failed observation must not claim an expiry")
    if status != "failed" and expires_at is None:
        raise DurableError("non-failed observation requires an expiry")
    if expires_at is not None and timestamp_value(expires_at) <= timestamp_value(observed_at):
        raise DurableError("observation expiry is invalid")
    citations = _validate_citations(value.get("citations"))
    if value.get("citations") != citations:
        raise DurableError("observation citations are not canonical")
    citation_ids = {item["id"] for item in citations}
    facts_value = value.get("facts")
    if not isinstance(facts_value, list) or len(facts_value) > 512:
        raise DurableError("observation facts are invalid")
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(facts_value):
        if not isinstance(item, Mapping) or set(item) != {
            "key",
            "value",
            "visibility",
            "citation_ids",
            "source_authority",
            "effective_authority",
            "fresh",
            "fact_digest",
        }:
            raise DurableError(f"observation facts[{index}] fields are invalid")
        key = safe_identifier(item.get("key"), label=f"observation facts[{index}].key")
        if key in seen:
            raise DurableError("observation fact keys are duplicated")
        seen.add(key)
        visibility = safe_visibility(item.get("visibility"), label="fact visibility")
        if not _visibility_not_broader(str(source["visibility"]), visibility):
            raise DurableError("observation fact visibility exceeds source visibility")
        refs = item.get("citation_ids")
        if not isinstance(refs, list) or not refs or refs != sorted(set(refs)):
            raise DurableError("observation fact citations are invalid")
        if any(ref not in citation_ids for ref in refs):
            raise DurableError("observation fact cites an unknown citation")
        safe_scalar(item.get("value"), label="observation fact value")
        if item.get("source_authority") != source["authority"]:
            raise DurableError("observation fact source authority mismatch")
        expected_effective = source["authority"] if status == "healthy" else "derived"
        if item.get("effective_authority") != expected_effective:
            raise DurableError("observation fact effective authority is invalid")
        if item.get("fresh") is not (status == "healthy"):
            raise DurableError("observation fact freshness is invalid")
        require_bound_digest(item, "fact_digest", label="observation fact")
        facts.append(dict(item))
    if facts != sorted(facts, key=lambda item: item["key"]):
        raise DurableError("observation facts are not canonical")
    errors = _validate_errors(value.get("errors"))
    if value.get("errors") != errors:
        raise DurableError("observation errors are not canonical")
    if status == "healthy":
        if (
            not facts
            or errors
            or expires_at is None
            or timestamp_value(evaluated_at) >= timestamp_value(expires_at)
        ):
            raise DurableError("healthy observation invariants failed")
    elif status == "stale":
        if (
            not facts
            or errors
            or expires_at is None
            or timestamp_value(evaluated_at) < timestamp_value(expires_at)
        ):
            raise DurableError("stale observation invariants failed")
    elif status == "partial":
        if not facts or not errors:
            raise DurableError("partial observation invariants failed")
    elif facts or citations or not errors:
        raise DurableError("failed observation invariants failed")
    if value.get("current_usable") is not (status == "healthy"):
        raise DurableError("observation current_usable is invalid")
    if value.get("mutation_attempted") is not False:
        raise DurableError("adapter observation must not report mutation")
    safe_digest(value.get("registry_digest"), label="registry_digest")
    safe_digest(value.get("input_digest"), label="input_digest")
    require_bound_digest(value, "observation_digest", label="observation")
    return dict(value)


def compile_observation_file(
    input_path: Path,
    *,
    evaluated_at: str,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return compile_observation(
        read_json(input_path, label="adapter input"),
        evaluated_at=evaluated_at,
        registry=registry,
    )


def compile_observation_set(
    observations: list[Mapping[str, Any]], *, created_at: str
) -> dict[str, Any]:
    if not observations:
        raise DurableError("observation set requires at least one observation")
    normalized = [validate_observation(item) for item in observations]
    normalized.sort(key=lambda item: (item["source"]["id"], item["adapter_id"]))
    keys = [(item["source"]["id"], item["adapter_id"]) for item in normalized]
    if len(keys) != len(set(keys)):
        raise DurableError("observation set contains duplicate adapter/source pairs")
    counts = {
        status: sum(item["status"] == status for item in normalized)
        for status in ("healthy", "stale", "partial", "failed")
    }
    value = {
        "schema_version": SET_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "observations": normalized,
        "counts": counts,
        "usable_count": counts["healthy"],
        "mutation_attempted": False,
        "set_digest": "",
    }
    return bind_digest(value, "set_digest")


def validate_observation_set(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "created_at",
        "observations",
        "counts",
        "usable_count",
        "mutation_attempted",
        "set_digest",
    }:
        raise DurableError("observation set fields are invalid")
    if value.get("schema_version") != SET_SCHEMA:
        raise DurableError("observation set schema is unsupported")
    observations = value.get("observations")
    if not isinstance(observations, list):
        raise DurableError("observation set observations are invalid")
    rebuilt = compile_observation_set(observations, created_at=str(value.get("created_at")))
    if rebuilt != dict(value):
        raise DurableError("observation set is not canonical")
    return rebuilt


def load_observation(path: Path) -> dict[str, Any]:
    return validate_observation(read_json(path, label="source observation"))


def load_observation_set(path: Path) -> dict[str, Any]:
    return validate_observation_set(read_json(path, label="source observation set"))
