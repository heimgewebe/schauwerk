from __future__ import annotations

from typing import Any

from schauwerk.durable.adapters import compile_observation, compile_observation_set


def adapter_input(
    *,
    adapter_id: str = "git",
    source_id: str = "repo.schauwerk",
    key: str = "revision",
    value: Any = "abc123",
    visibility: str = "private",
    observed_at: str = "2026-07-12T08:00:00Z",
    expires_at: str | None = "2026-07-12T10:00:00Z",
    collection_state: str = "complete",
    errors: list[str] | None = None,
) -> dict[str, Any]:
    failed = collection_state == "failed"
    return {
        "schema_version": "schauwerk-adapter-input.v1",
        "adapter_id": adapter_id,
        "source_id": source_id,
        "observed_at": observed_at,
        "expires_at": None if failed else expires_at,
        "collection_state": collection_state,
        "facts": (
            []
            if failed
            else [
                {
                    "key": key,
                    "value": value,
                    "visibility": visibility,
                    "citation_ids": ["source"],
                }
            ]
        ),
        "citations": (
            []
            if failed
            else [
                {
                    "id": "source",
                    "label": "Declared test source",
                    "revision": "fixture-v1",
                    "sha256": "a" * 64,
                }
            ]
        ),
        "errors": errors or ([] if collection_state == "complete" else ["fixture error"]),
    }


def observation(**kwargs: Any) -> dict[str, Any]:
    evaluated_at = kwargs.pop("evaluated_at", "2026-07-12T09:00:00Z")
    return compile_observation(adapter_input(**kwargs), evaluated_at=evaluated_at)


def observation_set(
    *items: dict[str, Any], created_at: str = "2026-07-12T09:00:00Z"
) -> dict[str, Any]:
    return compile_observation_set(list(items), created_at=created_at)
