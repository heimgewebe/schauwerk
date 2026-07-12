from __future__ import annotations

from schauwerk.durable.maintenance import (
    compile_maintenance_proposal,
    validate_maintenance_proposal,
)

from .helpers import observation, observation_set


def test_managed_region_receives_review_only_update_proposal() -> None:
    previous = observation_set(observation(value="old"))
    current = observation_set(observation(value="new"))
    proposal = compile_maintenance_proposal(
        previous,
        current,
        region_id="grabowski.operator-overview.managed",
        created_at="2026-07-12T09:15:00Z",
    )
    assert validate_maintenance_proposal(proposal) == proposal
    assert proposal["summary"] == {
        "operation_count": 1,
        "blocked_count": 0,
        "contradiction_count": 0,
        "ready_for_review": True,
    }
    assert proposal["operations"][0]["kind"] == "update"
    assert proposal["provider_effect_authorized"] is False
    assert proposal["mutation_attempted"] is False


def test_read_only_region_is_blocked_before_operations() -> None:
    previous = observation_set(observation(value="old"))
    current = observation_set(observation(value="new"))
    proposal = compile_maintenance_proposal(
        previous,
        current,
        region_id="schauwerk.delivery-status.readonly",
        created_at="2026-07-12T09:15:00Z",
    )
    assert proposal["operations"] == []
    assert proposal["summary"]["ready_for_review"] is False
    assert "read-only" in proposal["blocked"][0]["reason"]


def test_nonhealthy_current_source_is_blocked() -> None:
    previous = observation_set(observation(value="old"))
    current = observation_set(observation(value="new", evaluated_at="2026-07-12T11:00:00Z"))
    proposal = compile_maintenance_proposal(
        previous,
        current,
        region_id="grabowski.operator-overview.managed",
        created_at="2026-07-12T11:05:00Z",
    )
    assert proposal["operations"] == []
    assert proposal["blocked"] == [
        {"scope": "source:repo.schauwerk", "reason": "current observation is stale"}
    ]


def test_contradictory_healthy_sources_are_not_auto_proposed() -> None:
    previous = observation_set(observation(value="same"))
    current = observation_set(
        observation(value="one"),
        observation(source_id="repo.lenskit", value="two"),
    )
    proposal = compile_maintenance_proposal(
        previous,
        current,
        region_id="grabowski.operator-overview.managed",
        created_at="2026-07-12T09:15:00Z",
    )
    assert proposal["contradictions"][0]["fact_key"] == "revision"
    assert proposal["operations"] == []
    assert all(item["reason"] == "contradiction detected" for item in proposal["blocked"])
