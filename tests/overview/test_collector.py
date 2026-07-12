from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from schauwerk.operator.live_apply import LIVE_JOURNAL_SCHEMA, _write_journal
from schauwerk.overview.collector import collect_overview
from schauwerk.overview.model import (
    manifest_digest,
    read_snapshot,
    validate_overview_snapshot,
    write_snapshot,
)

NOW = datetime(2026, 7, 11, 3, 0, tzinfo=UTC)
EVIDENCE = Path("docs/operators/evidence/sw010-regie-20260711")


class FakeMiroClient:
    def __init__(
        self,
        state_root: Path,
        *,
        cached: dict | None = None,
        live: dict | None = None,
        local_state: bool = True,
    ) -> None:
        self.settings = SimpleNamespace(state_root=state_root)
        self.cached = cached
        self.live = live or {
            "checked": True,
            "ok": True,
            "renewal_required": False,
            "server_name": "Miro MCP",
            "tool_count": 32,
        }
        self.local_state = local_state
        self.live_calls = 0

    def status(self) -> dict:
        return {"local_state_present": self.local_state}

    def cached_auth_health(self) -> dict | None:
        return self.cached

    async def live_status(self) -> dict:
        self.live_calls += 1
        return self.live


def cached_health(observed_at: str = "2026-07-11T02:50:00Z") -> dict:
    return {
        "schema_version": "miro-auth-health.v1",
        "observed_at": observed_at,
        "local_state_present": True,
        "live_authorized": True,
        "live_authorized_known": True,
        "renewal_required": False,
        "renewal_required_known": True,
        "safe_for_live_board_operations": True,
        "recommended_next_command": "Proceed with live Miro operations.",
        "live": {"checked": True, "ok": True, "renewal_required": False},
    }


def test_registry_navigation_and_every_observation_is_time_bound(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health())
    snapshot = asyncio.run(
        collect_overview(
            miro_client=client,
            repo_root=Path.cwd(),
            now=NOW,
        )
    )
    assert snapshot["summary"]["project_count"] == 3
    assert snapshot["summary"]["view_count"] == 4
    assert {project["project_id"] for project in snapshot["projects"]} == {
        "grabowski",
        "lenskit",
        "schauwerk",
    }
    schauwerk = next(
        project for project in snapshot["projects"] if project["project_id"] == "schauwerk"
    )
    assert [view["view_id"] for view in schauwerk["views"]] == ["schauwerk.delivery-status"]
    assert all(
        observation["observed_at"]
        and observation["source"]
        and observation["freshness"] in {"fresh", "stale", "error", "unknown"}
        for observation in snapshot["observations"]
    )
    assert snapshot["summary"]["provider_state"] == "ok"
    assert client.live_calls == 0
    assert validate_overview_snapshot(snapshot) == snapshot


def test_provider_outage_remains_diagnostically_useful(tmp_path: Path) -> None:
    client = FakeMiroClient(
        tmp_path / "miro",
        live={
            "checked": True,
            "ok": False,
            "renewal_required": False,
            "error": "Miro network unavailable",
        },
    )
    snapshot = asyncio.run(
        collect_overview(
            miro_client=client,
            repo_root=Path.cwd(),
            probe_provider=True,
            now=NOW,
        )
    )
    assert client.live_calls == 1
    assert snapshot["summary"]["provider_state"] == "error"
    assert snapshot["summary"]["project_count"] == 3
    assert snapshot["publications"]
    provider = next(
        item for item in snapshot["observations"] if item["observation_id"] == "provider.miro.live"
    )
    assert provider["state"] == "error"
    assert provider["freshness"] == "error"
    assert provider["error"] == "Miro network unavailable"
    assert any(
        failure["failure_id"] == "provider.miro.unavailable" for failure in snapshot["failures"]
    )
    assert snapshot["boundary"]["provider_failure_does_not_block_local_diagnostics"]


def test_stale_cached_health_is_explicit(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health("2026-07-11T02:00:00Z"))
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    provider = next(
        item for item in snapshot["observations"] if item["observation_id"] == "provider.miro.live"
    )
    assert provider["state"] == "ok"
    assert provider["freshness"] == "stale"
    assert snapshot["summary"]["stale_count"] >= 1


def test_active_transaction_and_regie_jobs_are_projected_without_paths(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "miro"
    journal_path = state_root / "transactions" / ("a" * 64) / "journal.json"
    journal = {
        "schema_version": LIVE_JOURNAL_SCHEMA,
        "transaction_id": "sw009-active-test",
        "authorization_digest": "a" * 64,
        "status": "committed",
        "surface_alias": "fixture-board",
        "region_id": "managed-summary",
        "marker": "schauwerk-region:managed-summary",
        "plan_digest": "b" * 64,
        "expected_snapshot_digest": "c" * 64,
        "before_snapshot_digest": "c" * 64,
        "before_dsl_digest": "d" * 64,
        "operations": [],
        "applied_operation_ids": [],
        "reserved_at": "2026-07-11T02:40:00Z",
        "prepared_at": "2026-07-11T02:41:00Z",
        "after_snapshot_digest": "e" * 64,
        "after_dsl_digest": "f" * 64,
        "failure": None,
        "rollback": None,
    }
    _write_journal(journal_path, journal)
    timestamp = NOW.timestamp() - 60
    journal_path.touch()
    import os

    os.utime(journal_path, (timestamp, timestamp))

    regie_dir = state_root.parent / "regie" / ("1" * 64)
    regie_dir.mkdir(parents=True)
    decision_path = regie_dir / "decision-receipt.json"
    shutil.copyfile(EVIDENCE / "decision-receipt.json", decision_path)
    decision_path.chmod(0o600)
    os.utime(decision_path, (timestamp, timestamp))

    client = FakeMiroClient(state_root, cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    jobs = {job["kind"]: job for job in snapshot["jobs"]}
    assert jobs["live-transaction"]["status"] == "committed"
    assert jobs["regie-session"]["status"] == "authorization-expired"
    assert "authorization expired" in jobs["regie-session"]["summary"]
    assert jobs["live-transaction"]["freshness"] == "fresh"
    encoded = json.dumps(snapshot)
    assert str(tmp_path) not in encoded
    assert "journal.json" not in encoded


def test_corrupt_local_job_becomes_failure_not_collection_abort(tmp_path: Path) -> None:
    state_root = tmp_path / "miro"
    journal_path = state_root / "transactions" / "broken" / "journal.json"
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text("{}", encoding="utf-8")
    journal_path.chmod(0o600)
    client = FakeMiroClient(state_root, cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    assert snapshot["projects"]
    assert any(
        failure["failure_id"].startswith("transaction.")
        and failure["failure_id"].endswith(".invalid")
        for failure in snapshot["failures"]
    )


def test_profiles_are_bounded_and_snapshot_is_owner_only(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    profiles = {profile["profile_id"]: profile for profile in snapshot["display_profiles"]}
    assert profiles["wallboard"]["fullscreen"] is True
    assert profiles["incident"]["refresh_seconds"] == 15
    assert all(15 <= profile["refresh_seconds"] <= 3600 for profile in profiles.values())
    path = write_snapshot(tmp_path / "overview.json", snapshot)
    assert path.stat().st_mode & 0o077 == 0
    assert read_snapshot(path) == snapshot


def test_snapshot_tamper_is_rejected(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    snapshot["summary"]["project_count"] = 99
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="project count mismatch"):
        validate_overview_snapshot(snapshot)


def test_provider_probe_exception_is_projected_not_raised(tmp_path: Path) -> None:
    class ExplodingClient(FakeMiroClient):
        async def live_status(self) -> dict:
            self.live_calls += 1
            raise RuntimeError("fixture provider transport failure")

    client = ExplodingClient(tmp_path / "miro")
    snapshot = asyncio.run(
        collect_overview(
            miro_client=client,
            repo_root=Path.cwd(),
            probe_provider=True,
            now=NOW,
        )
    )
    assert snapshot["projects"]
    assert snapshot["summary"]["provider_state"] == "error"
    provider = next(
        item for item in snapshot["observations"] if item["observation_id"] == "provider.miro.live"
    )
    assert provider["error"] == "fixture provider transport failure"


def test_freshness_and_provider_summary_cannot_be_relabelled(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health("2026-07-11T02:00:00Z"))
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    provider = next(
        item for item in snapshot["observations"] if item["observation_id"] == "provider.miro.live"
    )
    provider["freshness"] = "fresh"
    snapshot["summary"]["stale_count"] -= 1
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="freshness mismatch"):
        validate_overview_snapshot(snapshot)

    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    snapshot["summary"]["provider_state"] = "degraded"
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="provider state mismatch"):
        validate_overview_snapshot(snapshot)


def test_snapshot_loader_requires_owner_only_permissions(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    path = write_snapshot(tmp_path / "overview.json", snapshot)
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        read_snapshot(path)


def test_profile_publication_and_failure_contracts_are_strict(tmp_path: Path) -> None:
    client = FakeMiroClient(tmp_path / "miro", cached=cached_health())
    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    snapshot["display_profiles"][0]["visible_sections"].append("unknown-section")
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="visible_sections is invalid"):
        validate_overview_snapshot(snapshot)

    snapshot = asyncio.run(collect_overview(miro_client=client, repo_root=Path.cwd(), now=NOW))
    snapshot["publications"].append(dict(snapshot["publications"][0]))
    snapshot["summary"]["stale_count"] += int(snapshot["publications"][0]["freshness"] == "stale")
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="publication ids must be unique"):
        validate_overview_snapshot(snapshot)

    snapshot = asyncio.run(
        collect_overview(
            miro_client=FakeMiroClient(
                tmp_path / "other-miro",
                live={"checked": True, "ok": False, "error": "fixture failure"},
            ),
            repo_root=Path.cwd(),
            probe_provider=True,
            now=NOW,
        )
    )
    snapshot["failures"].append(dict(snapshot["failures"][0]))
    snapshot["summary"]["error_count"] += 1
    snapshot["snapshot_digest"] = manifest_digest(snapshot, "snapshot_digest")
    with pytest.raises(ValueError, match="failure ids must be unique"):
        validate_overview_snapshot(snapshot)
