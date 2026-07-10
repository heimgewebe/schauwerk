from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk.pilots.grabowski import compile_grabowski_snapshot
from schauwerk.pilots.grabowski_operational import (
    _digest,
    compile_operational_snapshot,
    render_operational_dsl,
    validate_operational_snapshot,
    write_operational_pilot,
)

ROOT = Path(__file__).resolve().parents[2]


def _static_snapshot(tmp_path: Path) -> Path:
    context = tmp_path / "operator-context.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": "Bounded operator contract.",
                "capabilities": [
                    {
                        "id": "read",
                        "category": "repository",
                        "risk_class": "low",
                        "read_only": True,
                    }
                ],
                "runtime_contract": {"expected_tools": ["read"]},
                "policy_contract": {"active_profile": "observe", "mode": "observe"},
                "operating_protocol": {"name": "Operator Relay v0"},
            }
        ),
        encoding="utf-8",
    )
    snapshot = compile_grabowski_snapshot(context, repo_root=ROOT)
    path = tmp_path / "static-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def _observation() -> dict:
    observed = "2026-07-10T05:30:00Z"
    return {
        "schema_version": "grabowski-operational-observation.v1",
        "evaluated_at": "2026-07-10T05:31:00Z",
        "channels": {
            "hosts": {
                "source_id": "grabowski.fleet-observation",
                "authority": "operational",
                "observed_at": observed,
                "stale_after_seconds": 900,
                "collection_status": "ok",
                "error_code": None,
                "summary": {
                    "declared_count": 4,
                    "enabled_count": 4,
                    "reachable_count": 4,
                    "unavailable_count": 0,
                },
            },
            "runtime": {
                "source_id": "grabowski.runtime-observation",
                "authority": "operational",
                "observed_at": observed,
                "stale_after_seconds": 300,
                "collection_status": "ok",
                "error_code": None,
                "summary": {
                    "running_grabowski_units": 2,
                    "expected_tool_count": 1,
                    "policy_state": "bounded",
                    "failed_grabowski_units": 0,
                },
            },
            "work": {
                "source_id": "bureau.grabowski-work-observation",
                "authority": "operational",
                "observed_at": observed,
                "stale_after_seconds": 300,
                "collection_status": "ok",
                "error_code": None,
                "summary": {
                    "active_run_count": 1,
                    "open_pr_count": 0,
                    "ready_task_count": 1,
                    "current_task_state": "running",
                },
            },
            "gaps": {
                "source_id": "bureau.grabowski-gap-observation",
                "authority": "derived",
                "observed_at": observed,
                "stale_after_seconds": 1800,
                "collection_status": "ok",
                "error_code": None,
                "summary": {
                    "tracked_followup_count": 0,
                    "blocked_count": 0,
                    "planned_count": 0,
                    "repair_candidate_count": 0,
                },
            },
        },
    }


def _write_observation(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "observation.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_healthy_observation_is_deterministic(tmp_path: Path) -> None:
    static = _static_snapshot(tmp_path)
    observation = _write_observation(tmp_path, _observation())
    first = compile_operational_snapshot(static, observation, repo_root=ROOT)
    second = compile_operational_snapshot(static, observation, repo_root=ROOT)
    assert first == second
    assert first["overall_status"] == "healthy"
    assert first["channel_state_counts"] == {
        "healthy": 4,
        "partial": 0,
        "stale": 0,
        "unavailable": 0,
    }
    validate_operational_snapshot(first)
    dsl = render_operational_dsl(json.loads(static.read_text()), first)
    assert "Statischer Vertrag" in dsl
    assert "Beobachteter Zustand" in dsl
    assert "keine Rohlogs" in dsl
    assert 'root FRAME x=0 y=0 w=4400 h=2200 "Grabowski Operational Overview"' in dsl
    assert 'static FRAME x=-1450 y=300 w=900 h=1450 "Statischer Vertrag"' in dsl
    assert 'live FRAME x=0 y=300 w=1800 h=1450 "Beobachteter Zustand"' in dsl
    assert 'gaps FRAME x=1450 y=300 w=900 h=1450 "Lücken und Grenzen"' in dsl
    assert "Folgethemen · healthy" in dsl


def test_domain_degradation_is_partial(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["runtime"]["summary"]["failed_grabowski_units"] = 2
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
    )
    assert snapshot["channels"]["runtime"]["state"] == "partial"
    assert snapshot["overall_status"] == "degraded"


def test_stale_channel_is_explicit(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["hosts"]["observed_at"] = "2026-07-10T04:00:00Z"
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
    )
    assert snapshot["channels"]["hosts"]["state"] == "stale"
    assert snapshot["overall_status"] == "degraded"


def test_partial_and_unavailable_sources_are_preserved(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["work"]["collection_status"] = "partial"
    value["channels"]["work"]["error_code"] = "github_partial"
    value["channels"]["gaps"]["collection_status"] = "unavailable"
    value["channels"]["gaps"]["error_code"] = "bureau_unavailable"
    value["channels"]["gaps"]["summary"] = None
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
    )
    assert snapshot["channels"]["work"]["state"] == "partial"
    assert snapshot["channels"]["gaps"]["state"] == "unavailable"
    dsl = render_operational_dsl(json.loads(_static_snapshot(tmp_path).read_text()), snapshot)
    assert "Quelle nicht verfügbar" in dsl


def test_all_unavailable_marks_overall_unavailable(tmp_path: Path) -> None:
    value = _observation()
    for channel in value["channels"].values():
        channel["collection_status"] = "unavailable"
        channel["error_code"] = "source_unavailable"
        channel["summary"] = None
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
    )
    assert snapshot["overall_status"] == "unavailable"


def test_unknown_fields_and_raw_output_are_rejected(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["runtime"]["raw_output"] = "secret command output"
    with pytest.raises(ValueError, match="unsupported fields"):
        compile_operational_snapshot(
            _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
        )


def test_snapshot_digest_drift_is_rejected(tmp_path: Path) -> None:
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path),
        _write_observation(tmp_path, _observation()),
        repo_root=ROOT,
    )
    tampered = deepcopy(snapshot)
    tampered["overall_status"] = "unavailable"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_operational_snapshot(tampered)


def test_write_operational_pilot_emits_non_mutating_receipt(tmp_path: Path) -> None:
    snapshot_output = tmp_path / "out" / "snapshot.json"
    dsl_output = tmp_path / "out" / "view.dsl"
    receipt = write_operational_pilot(
        static_snapshot_path=_static_snapshot(tmp_path),
        observation_path=_write_observation(tmp_path, _observation()),
        snapshot_output=snapshot_output,
        dsl_output=dsl_output,
        repo_root=ROOT,
    )
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["overall_status"] == "healthy"
    assert snapshot_output.is_file()
    assert dsl_output.is_file()


def test_recomputed_digest_does_not_hide_invalid_channel_state(tmp_path: Path) -> None:
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path),
        _write_observation(tmp_path, _observation()),
        repo_root=ROOT,
    )
    snapshot["channels"]["runtime"]["state"] = "unavailable"
    snapshot["snapshot_digest"] = _digest(snapshot)
    with pytest.raises(ValueError, match="state mismatch"):
        validate_operational_snapshot(snapshot)


def test_recomputed_digest_does_not_hide_invalid_counts(tmp_path: Path) -> None:
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path),
        _write_observation(tmp_path, _observation()),
        repo_root=ROOT,
    )
    snapshot["channel_state_counts"] = {
        "healthy": 3,
        "partial": 1,
        "stale": 0,
        "unavailable": 0,
    }
    snapshot["snapshot_digest"] = _digest(snapshot)
    with pytest.raises(ValueError, match="counts mismatch"):
        validate_operational_snapshot(snapshot)


def test_recomputed_digest_does_not_hide_static_runtime_count_mismatch(tmp_path: Path) -> None:
    snapshot = compile_operational_snapshot(
        _static_snapshot(tmp_path),
        _write_observation(tmp_path, _observation()),
        repo_root=ROOT,
    )
    snapshot["channels"]["runtime"]["summary"]["expected_tool_count"] = 2
    snapshot["snapshot_digest"] = _digest(snapshot)
    with pytest.raises(ValueError, match="expected tool count mismatch"):
        validate_operational_snapshot(snapshot)


def test_renderer_rejects_unrelated_static_snapshot(tmp_path: Path) -> None:
    static_path = _static_snapshot(tmp_path)
    operational = compile_operational_snapshot(
        static_path,
        _write_observation(tmp_path, _observation()),
        repo_root=ROOT,
    )
    unrelated = json.loads(static_path.read_text(encoding="utf-8"))
    unrelated["summary"]["purpose"] = "Different static contract."
    from schauwerk.pilots.grabowski import _snapshot_digest

    unrelated["snapshot_digest"] = _snapshot_digest(unrelated)
    with pytest.raises(ValueError, match="different static snapshot"):
        render_operational_dsl(unrelated, operational)


def test_future_observation_is_rejected(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["hosts"]["observed_at"] = "2026-07-10T05:40:01Z"
    with pytest.raises(ValueError, match="too far in the future"):
        compile_operational_snapshot(
            _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
        )


def test_authority_mismatch_is_rejected(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["gaps"]["authority"] = "operational"
    with pytest.raises(ValueError, match="authority does not match registry"):
        compile_operational_snapshot(
            _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
        )


def test_observation_symlink_is_rejected(tmp_path: Path) -> None:
    static_path = _static_snapshot(tmp_path)
    target = _write_observation(tmp_path, _observation())
    link = tmp_path / "observation-link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="regular non-symlink"):
        compile_operational_snapshot(static_path, link, repo_root=ROOT)


def test_summary_field_order_does_not_change_snapshot_or_dsl(tmp_path: Path) -> None:
    static_path = _static_snapshot(tmp_path)
    first_value = _observation()
    first_path = tmp_path / "first-observation.json"
    first_path.write_text(json.dumps(first_value), encoding="utf-8")
    first = compile_operational_snapshot(static_path, first_path, repo_root=ROOT)
    first_dsl = render_operational_dsl(json.loads(static_path.read_text(encoding="utf-8")), first)

    second_value = _observation()
    for channel in second_value["channels"].values():
        if channel["summary"] is not None:
            channel["summary"] = dict(reversed(tuple(channel["summary"].items())))
    second_path = tmp_path / "second-observation.json"
    second_path.write_text(json.dumps(second_value), encoding="utf-8")
    second = compile_operational_snapshot(static_path, second_path, repo_root=ROOT)
    second_dsl = render_operational_dsl(json.loads(static_path.read_text(encoding="utf-8")), second)

    assert first == second
    assert first_dsl == second_dsl


def test_public_observation_schema_accepts_the_valid_fixture() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "grabowski-operational-observation.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_observation())


def test_date_only_timestamp_is_rejected(tmp_path: Path) -> None:
    value = _observation()
    value["channels"]["hosts"]["observed_at"] = "2026-07-10Z"
    with pytest.raises(ValueError, match="RFC3339 UTC timestamp"):
        compile_operational_snapshot(
            _static_snapshot(tmp_path), _write_observation(tmp_path, value), repo_root=ROOT
        )
