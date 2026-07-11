from __future__ import annotations

import json
import re
from pathlib import Path

from schauwerk.overview.model import validate_overview_snapshot

ROOT = Path("docs/operators/evidence/sw011-overview-live-20260711")


def read(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_fixture_snapshot_proves_provider_outage_without_local_diagnostic_loss() -> None:
    snapshot = validate_overview_snapshot(read("overview-snapshot.json"))
    assert snapshot["summary"] == {
        "project_count": 3,
        "view_count": 4,
        "active_job_count": 2,
        "error_count": 1,
        "stale_count": 0,
        "provider_state": "error",
    }
    assert {project["project_id"] for project in snapshot["projects"]} == {
        "grabowski",
        "lenskit",
        "schauwerk",
    }
    assert {job["kind"] for job in snapshot["jobs"]} == {
        "live-transaction",
        "regie-session",
    }
    regie = next(job for job in snapshot["jobs"] if job["kind"] == "regie-session")
    assert regie["status"] == "authorization-expired"
    provider = next(
        item
        for item in snapshot["observations"]
        if item["observation_id"] == "provider.miro.live"
    )
    assert provider["state"] == "error"
    assert provider["freshness"] == "error"
    assert provider["error"] == "fixture provider outage"
    assert snapshot["boundary"][
        "provider_failure_does_not_block_local_diagnostics"
    ]


def test_interface_profiles_and_failure_matrix_cover_t009_acceptance() -> None:
    interface = read("interface-contract.json")
    assert interface["bind_host"] == "127.0.0.1"
    assert interface["read_only"] is True
    assert interface["post_routes"] is False
    assert interface["fullscreen_action_explicit"] is True
    assert interface["refresh_bounds_seconds"] == [15, 3600]
    assert interface["profiles"] == {
        "operator": {"refresh_seconds": 60, "fullscreen": False},
        "wallboard": {"refresh_seconds": 30, "fullscreen": True},
        "incident": {"refresh_seconds": 15, "fullscreen": True},
    }
    matrix = read("failure-matrix.json")
    text = " ".join(matrix["cases"])
    for phrase in (
        "provider exception",
        "stale cached health",
        "future observation",
        "missing draft publications",
        "corrupt SW-009 journals",
        "tampered Regie effect receipts",
        "read-only service",
    ):
        assert phrase in text
    assert matrix["productive_provider_mutation_attempted"] is False


def test_evidence_contains_no_sensitive_runtime_reference() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.iterdir()
        if path.is_file()
    )
    patterns = (
        r"(?i)(?:/home/|/Users/|[A-Z]:\\)",
        r"(?i)https?://(?:www\.)?miro\.com|moveToWidget=",
        r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]",
        r"(?i)widget[_-]?id|item[_-]?id",
        r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b",
    )
    assert not any(re.search(pattern, text) for pattern in patterns)
