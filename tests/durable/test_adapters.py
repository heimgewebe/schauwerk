from __future__ import annotations

import copy

import pytest

from schauwerk.durable.adapters import (
    adapter_catalog,
    compile_observation,
    compile_observation_set,
    validate_observation,
    validate_observation_set,
)
from schauwerk.durable.common import DurableError

from .helpers import adapter_input, observation


def test_catalog_declares_current_local_adapters() -> None:
    value = adapter_catalog()
    assert [item["adapter_id"] for item in value["adapters"]] == [
        "git",
        "github",
        "systemkatalog",
        "lenskit",
        "generic",
    ]
    assert all(item["failure_semantics"] == "visible-no-fabrication" for item in value["adapters"])


def test_observation_states_are_explicit_and_non_fabricating() -> None:
    healthy = observation()
    stale = observation(evaluated_at="2026-07-12T11:00:00Z")
    partial = observation(collection_state="partial", errors=["one page unavailable"])
    failed = observation(collection_state="failed", errors=["source unavailable"])

    assert healthy["status"] == "healthy"
    assert healthy["current_usable"] is True
    assert healthy["facts"][0]["effective_authority"] == "canonical"

    assert stale["status"] == "stale"
    assert stale["current_usable"] is False
    assert stale["facts"][0]["fresh"] is False
    assert stale["facts"][0]["effective_authority"] == "derived"

    assert partial["status"] == "partial"
    assert partial["facts"][0]["effective_authority"] == "derived"
    assert partial["errors"] == ["one page unavailable"]

    assert failed["status"] == "failed"
    assert failed["expires_at"] is None
    assert failed["facts"] == []
    assert failed["citations"] == []
    assert failed["errors"] == ["source unavailable"]


def test_failed_input_cannot_smuggle_facts() -> None:
    value = adapter_input(collection_state="failed", errors=["offline"])
    value["citations"] = [{"id": "source", "label": "Source", "revision": "v1", "sha256": "a" * 64}]
    value["facts"] = [
        {
            "key": "revision",
            "value": "fake",
            "visibility": "private",
            "citation_ids": ["source"],
        }
    ]
    with pytest.raises(DurableError, match="failed collection"):
        compile_observation(value, evaluated_at="2026-07-12T09:00:00Z")


def test_fact_visibility_cannot_exceed_registry_source() -> None:
    value = adapter_input(
        adapter_id="systemkatalog",
        source_id="systemkatalog.ecosystem-map",
        visibility="public",
    )
    with pytest.raises(DurableError, match="broader than its source"):
        compile_observation(value, evaluated_at="2026-07-12T09:00:00Z")


def test_observation_and_set_digests_detect_tampering() -> None:
    first = observation()
    second = observation(adapter_id="git", source_id="repo.lenskit", key="revision", value="def456")
    value = compile_observation_set([second, first], created_at="2026-07-12T09:00:00Z")
    assert validate_observation_set(value) == value
    assert [item["source"]["id"] for item in value["observations"]] == [
        "repo.lenskit",
        "repo.schauwerk",
    ]

    tampered = copy.deepcopy(first)
    tampered["facts"][0]["value"] = "altered"
    with pytest.raises(DurableError, match="fact_digest mismatch"):
        validate_observation(tampered)
