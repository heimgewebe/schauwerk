"""Tests for SW-014 adapter foundation."""

import pytest

from schauwerk.adapters.model import (
    AdapterError,
    create_observation,
    validate_observation,
)


def test_healthy_observation():
    payload = {"some": "data"}
    obs = create_observation(
        adapter_id="test_adapter",
        observed_at="2026-07-12T10:00:00Z",
        stale_after_seconds=3600,
        status="healthy",
        payload=payload,
    )
    assert obs["schema_version"] == "adapter-observation.v1"
    assert obs["status"] == "healthy"
    assert obs["error_code"] is None
    assert obs["payload"] == payload

    validated = validate_observation(obs)
    assert validated == obs


def test_stale_observation():
    obs = create_observation(
        adapter_id="test_adapter",
        observed_at="2026-07-12T10:00:00Z",
        stale_after_seconds=3600,
        status="stale",
        payload={"old": "data"},
    )
    assert obs["status"] == "stale"
    validate_observation(obs)


def test_partial_observation():
    obs = create_observation(
        adapter_id="test_adapter",
        observed_at="2026-07-12T10:00:00Z",
        stale_after_seconds=3600,
        status="partial",
        error_code="some_items_failed",
        payload={"partial": "data"},
    )
    assert obs["status"] == "partial"
    assert obs["error_code"] == "some_items_failed"
    validate_observation(obs)


def test_failed_observation():
    obs = create_observation(
        adapter_id="test_adapter",
        observed_at="2026-07-12T10:00:00Z",
        stale_after_seconds=3600,
        status="failed",
        error_code="connection_timeout",
        payload=None,
    )
    assert obs["status"] == "failed"
    assert obs["error_code"] == "connection_timeout"
    assert obs["payload"] is None
    validate_observation(obs)


def test_invalid_status_missing_error():
    with pytest.raises(AdapterError, match="error_code is required for status failed"):
        create_observation(
            adapter_id="test_adapter",
            observed_at="2026-07-12T10:00:00Z",
            stale_after_seconds=3600,
            status="failed",
            payload=None,
        )


def test_invalid_digest():
    obs = create_observation(
        adapter_id="test_adapter",
        observed_at="2026-07-12T10:00:00Z",
        stale_after_seconds=3600,
        status="healthy",
        payload={"some": "data"},
    )
    obs["payload_digest"] = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    with pytest.raises(AdapterError, match="payload_digest mismatch"):
        validate_observation(obs)
