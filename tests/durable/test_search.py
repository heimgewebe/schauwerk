from __future__ import annotations

from schauwerk.durable.common import bind_digest, safe_identifier, stable_digest
from schauwerk.durable.search import (
    compile_search_index,
    search_index,
    semantic_suggestions,
    validate_search_index,
)

from .helpers import observation, observation_set


def test_search_respects_visibility_and_returns_citations() -> None:
    observations = observation_set(
        observation(value="private architecture"),
        observation(
            adapter_id="systemkatalog",
            source_id="systemkatalog.ecosystem-map",
            key="system_name",
            value="shared architecture",
            visibility="shared",
        ),
    )
    index = compile_search_index(observations, created_at="2026-07-12T09:10:00Z")
    assert validate_search_index(index) == index

    private = search_index(index, query="architecture", visibility="private")
    public = search_index(index, query="architecture", visibility="public")
    shared = search_index(index, query="architecture", visibility="shared")

    assert len(private["results"]) == 2
    assert public["results"] == []
    assert len(shared["results"]) == 1
    assert shared["results"][0]["citations"][0]["id"] == "source"


def test_disabled_search_never_blocks_core() -> None:
    observations = observation_set(observation())
    index = compile_search_index(
        observations,
        created_at="2026-07-12T09:10:00Z",
        disabled_reason="semantic service intentionally disabled",
    )
    result = search_index(index, query="revision", visibility="private")
    hints = semantic_suggestions(index, visibility="private")
    assert index["state"] == "disabled"
    assert result["results"] == []
    assert hints["suggestions"] == []
    assert result["core_blocked"] is False
    assert hints["core_blocked"] is False


def test_document_identity_includes_adapter_for_same_source_fact() -> None:
    observations = observation_set(
        observation(adapter_id="git", source_id="repo.schauwerk"),
        observation(adapter_id="generic", source_id="repo.schauwerk"),
    )

    index = compile_search_index(observations, created_at="2026-07-12T09:10:00Z")

    assert validate_search_index(index) == index
    assert [item["adapter_id"] for item in index["documents"]] == ["generic", "git"]
    assert len({item["document_id"] for item in index["documents"]}) == 2
    results = search_index(index, query="revision", visibility="private")["results"]
    assert {item["adapter_id"] for item in results} == {"generic", "git"}


def test_legacy_v1_document_without_adapter_id_remains_readable() -> None:
    index = compile_search_index(
        observation_set(observation()), created_at="2026-07-12T09:10:00Z"
    )
    document = index["documents"][0]
    document.pop("adapter_id")
    document["document_id"] = safe_identifier(
        f"doc.{stable_digest([document['source_id'], document['fact_key']])[:20]}",
        label="document_id",
    )
    bind_digest(document, "document_digest")
    bind_digest(index, "index_digest")

    assert validate_search_index(index) == index
    results = search_index(index, query="revision", visibility="private")["results"]
    assert len(results) == 1
    assert "adapter_id" not in results[0]


def test_semantic_hints_have_confidence_and_evidence() -> None:
    observations = observation_set(
        observation(value="one"),
        observation(source_id="repo.repoground", value="two"),
        observation(source_id="repo.grabowski", key="unique_fact", value="alone"),
    )
    index = compile_search_index(observations, created_at="2026-07-12T09:10:00Z")
    hints = semantic_suggestions(index, visibility="private")
    kinds = {item["kind"] for item in hints["suggestions"]}
    assert {"contradiction", "orphan"} <= kinds
    assert all(0 <= item["confidence"] <= 100 for item in hints["suggestions"])
    assert all(item["evidence_document_ids"] for item in hints["suggestions"])
