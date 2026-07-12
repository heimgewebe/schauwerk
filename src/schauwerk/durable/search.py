"""SW-016 optional local search and deterministic semantic hints."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapters import validate_observation_set
from .common import (
    DurableError,
    bind_digest,
    bounded_text,
    parse_timestamp,
    read_json,
    require_bound_digest,
    safe_identifier,
    safe_visibility,
    stable_digest,
    visibility_allows,
)

INDEX_SCHEMA = "schauwerk-search-index.v1"
RESULT_SCHEMA = "schauwerk-search-results.v1"
SUGGESTION_SCHEMA = "schauwerk-semantic-suggestions.v1"
_TOKEN = re.compile(r"[a-z0-9äöüß][a-z0-9äöüß._-]{1,}", re.IGNORECASE)


def _tokens(value: Any) -> list[str]:
    if value is None:
        return []
    return sorted({match.group(0).casefold() for match in _TOKEN.finditer(str(value))})


def compile_search_index(
    observation_set: Mapping[str, Any],
    *,
    created_at: str,
    disabled_reason: str | None = None,
) -> dict[str, Any]:
    observations = validate_observation_set(observation_set)
    state = "disabled" if disabled_reason else "ready"
    errors = (
        [bounded_text(disabled_reason, label="disabled_reason", maximum=1000)]
        if disabled_reason
        else []
    )
    documents: list[dict[str, Any]] = []
    if state == "ready":
        for observation in observations["observations"]:
            if observation["status"] == "failed":
                continue
            citation_map = {item["id"]: item for item in observation["citations"]}
            for fact in observation["facts"]:
                citations = [citation_map[item] for item in fact["citation_ids"]]
                document = {
                    "document_id": safe_identifier(
                        f"doc.{stable_digest([observation['source']['id'], fact['key']])[:20]}",
                        label="document_id",
                    ),
                    "source_id": observation["source"]["id"],
                    "fact_key": fact["key"],
                    "value": fact["value"],
                    "visibility": fact["visibility"],
                    "source_status": observation["status"],
                    "fresh": fact["fresh"],
                    "effective_authority": fact["effective_authority"],
                    "tokens": _tokens(f"{fact['key']} {fact['value']}"),
                    "citations": citations,
                    "fact_digest": fact["fact_digest"],
                    "document_digest": "",
                }
                documents.append(bind_digest(document, "document_digest"))
    documents.sort(key=lambda item: item["document_id"])
    index = {
        "schema_version": INDEX_SCHEMA,
        "created_at": parse_timestamp(created_at, label="created_at"),
        "state": state,
        "core_blocked": False,
        "source_set_digest": observations["set_digest"],
        "documents": documents,
        "errors": errors,
        "index_digest": "",
    }
    return bind_digest(index, "index_digest")


def validate_search_index(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "created_at",
        "state",
        "core_blocked",
        "source_set_digest",
        "documents",
        "errors",
        "index_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise DurableError("search index fields are invalid")
    if value.get("schema_version") != INDEX_SCHEMA:
        raise DurableError("search index schema is unsupported")
    parse_timestamp(value.get("created_at"), label="created_at")
    state = value.get("state")
    if state not in {"ready", "disabled", "degraded"}:
        raise DurableError("search index state is invalid")
    if value.get("core_blocked") is not False:
        raise DurableError("optional search must never block core operation")
    from .common import safe_digest

    safe_digest(value.get("source_set_digest"), label="source_set_digest")
    documents = value.get("documents")
    errors = value.get("errors")
    if not isinstance(documents, list) or not isinstance(errors, list):
        raise DurableError("search index collections are invalid")
    if state == "ready" and errors:
        raise DurableError("ready search index must not carry errors")
    if state != "ready" and not errors:
        raise DurableError("non-ready search index must expose errors")
    if state == "disabled" and documents:
        raise DurableError("disabled search index must be empty")
    if [item.get("document_id") for item in documents] != sorted(
        item.get("document_id") for item in documents
    ):
        raise DurableError("search documents are not canonical")
    seen: set[str] = set()
    for item in documents:
        if not isinstance(item, Mapping) or set(item) != {
            "document_id",
            "source_id",
            "fact_key",
            "value",
            "visibility",
            "source_status",
            "fresh",
            "effective_authority",
            "tokens",
            "citations",
            "fact_digest",
            "document_digest",
        }:
            raise DurableError("search document fields are invalid")
        identifier = safe_identifier(item.get("document_id"), label="document_id")
        if identifier in seen:
            raise DurableError("search document ids are duplicated")
        seen.add(identifier)
        safe_identifier(item.get("source_id"), label="document source_id")
        safe_identifier(item.get("fact_key"), label="document fact_key")
        safe_visibility(item.get("visibility"), label="document visibility")
        if item.get("source_status") not in {"healthy", "stale", "partial"}:
            raise DurableError("document source status is invalid")
        if item.get("fresh") is not (item.get("source_status") == "healthy"):
            raise DurableError("document freshness is invalid")
        tokens = item.get("tokens")
        if not isinstance(tokens, list) or tokens != sorted(set(tokens)):
            raise DurableError("document tokens are invalid")
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise DurableError("document citations are invalid")
        safe_digest(item.get("fact_digest"), label="fact_digest")
        require_bound_digest(item, "document_digest", label="search document")
    require_bound_digest(value, "index_digest", label="search index")
    return dict(value)


def search_index(
    index_value: Mapping[str, Any],
    *,
    query: str,
    visibility: str,
    limit: int = 20,
) -> dict[str, Any]:
    index = validate_search_index(index_value)
    requested_visibility = safe_visibility(visibility, label="visibility")
    text = bounded_text(query.strip(), label="query", maximum=500)
    if not 1 <= limit <= 100:
        raise DurableError("limit must be between 1 and 100")
    query_tokens = _tokens(text)
    results: list[dict[str, Any]] = []
    if index["state"] == "ready":
        for document in index["documents"]:
            if not visibility_allows(requested_visibility, document["visibility"]):
                continue
            overlap = sorted(set(query_tokens) & set(document["tokens"]))
            substring = text.casefold() in f"{document['fact_key']} {document['value']}".casefold()
            if not overlap and not substring:
                continue
            score = min(
                100, len(overlap) * 20 + (35 if substring else 0) + (10 if document["fresh"] else 0)
            )
            results.append(
                {
                    "document_id": document["document_id"],
                    "source_id": document["source_id"],
                    "fact_key": document["fact_key"],
                    "value": document["value"],
                    "visibility": document["visibility"],
                    "fresh": document["fresh"],
                    "source_status": document["source_status"],
                    "effective_authority": document["effective_authority"],
                    "score": score,
                    "matched_tokens": overlap,
                    "citations": document["citations"],
                    "document_digest": document["document_digest"],
                }
            )
    results.sort(key=lambda item: (-item["score"], item["document_id"]))
    results = results[:limit]
    value = {
        "schema_version": RESULT_SCHEMA,
        "index_digest": index["index_digest"],
        "query": text,
        "visibility": requested_visibility,
        "state": index["state"],
        "core_blocked": False,
        "results": results,
        "errors": index["errors"],
        "result_digest": "",
    }
    return bind_digest(value, "result_digest")


def semantic_suggestions(index_value: Mapping[str, Any], *, visibility: str) -> dict[str, Any]:
    index = validate_search_index(index_value)
    requested_visibility = safe_visibility(visibility, label="visibility")
    documents = [
        item
        for item in index["documents"]
        if visibility_allows(requested_visibility, item["visibility"])
    ]
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in documents:
        by_key.setdefault(item["fact_key"], []).append(item)
    suggestions: list[dict[str, Any]] = []
    linked_ids: set[str] = set()
    for key, records in sorted(by_key.items()):
        if len(records) > 1:
            refs = sorted(item["document_id"] for item in records)
            linked_ids.update(refs)
            values = {stable_digest(item["value"]) for item in records}
            kind = "contradiction" if len(values) > 1 else "relationship"
            confidence = 95 if kind == "contradiction" else 80
            suggestions.append(
                {
                    "suggestion_id": safe_identifier(
                        f"{kind}.{stable_digest([key, refs])[:16]}", label="suggestion_id"
                    ),
                    "kind": kind,
                    "confidence": confidence,
                    "summary": (
                        f"Multiple visible sources disagree on {key}"
                        if kind == "contradiction"
                        else f"Multiple visible sources share {key}"
                    ),
                    "evidence_document_ids": refs,
                    "source_citations": sorted(
                        {
                            stable_digest(citation): citation
                            for item in records
                            for citation in item["citations"]
                        }.values(),
                        key=lambda item: item["id"],
                    ),
                }
            )
    for item in documents:
        if item["document_id"] in linked_ids:
            continue
        suggestions.append(
            {
                "suggestion_id": safe_identifier(
                    f"orphan.{stable_digest(item['document_id'])[:16]}", label="suggestion_id"
                ),
                "kind": "orphan",
                "confidence": 70,
                "summary": f"No visible peer fact shares {item['fact_key']}",
                "evidence_document_ids": [item["document_id"]],
                "source_citations": item["citations"],
            }
        )
    suggestions.sort(key=lambda item: (item["kind"], item["suggestion_id"]))
    value = {
        "schema_version": SUGGESTION_SCHEMA,
        "index_digest": index["index_digest"],
        "visibility": requested_visibility,
        "state": index["state"],
        "core_blocked": False,
        "suggestions": suggestions if index["state"] == "ready" else [],
        "errors": index["errors"],
        "suggestion_digest": "",
    }
    return bind_digest(value, "suggestion_digest")


def load_search_index(path: Path) -> dict[str, Any]:
    return validate_search_index(read_json(path, label="search index"))
