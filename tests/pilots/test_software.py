from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from schauwerk.pilots.software import (
    compile_software_snapshot,
    render_software_dsl,
    validate_software_snapshot,
    write_software_pilot,
)

ROOT = Path(__file__).resolve().parents[2]


def software_input() -> dict:
    return {
        "schema_version": "software-pilot-input.v1",
        "project_id": "lenskit",
        "view_id": "lenskit.software-overview",
        "sources": [
            {"source_id": "github.lenskit", "revision": "a" * 40},
            {"source_id": "repo.lenskit", "revision": "a" * 40},
        ],
        "title": "Fixture Software",
        "purpose": "A generic software pilot fixture.",
        "components": [
            {
                "id": "api",
                "title": "API",
                "responsibility": "Serve bounded reads.",
                "status": "active",
            }
        ],
        "decisions": [
            {
                "id": "read-only",
                "title": "Read-only boundary",
                "status": "accepted",
                "impact": "No hidden writes.",
            }
        ],
        "roadmap": [
            {
                "id": "next",
                "title": "Next slice",
                "status": "planned",
                "outcome": "Useful increment.",
            }
        ],
        "work": [
            {"id": "pr-1", "title": "Current change", "status": "merged", "kind": "pr"}
        ],
        "tests": {"status": "green", "passed": 3, "failed": 0},
        "risks": [
            {
                "id": "stale",
                "title": "Stale snapshot",
                "severity": "medium",
                "status": "managed",
                "mitigation": "Check revision and digest.",
            }
        ],
    }


def write_input(tmp_path: Path, value: dict | None = None) -> Path:
    path = tmp_path / "software.json"
    path.write_text(json.dumps(value or software_input(), sort_keys=True), encoding="utf-8")
    return path


def test_software_pilot_is_generic_deterministic_and_sanitized(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    first = compile_software_snapshot(source, repo_root=ROOT)
    second = compile_software_snapshot(source, repo_root=ROOT)
    assert first == second
    assert first["project_id"] == "lenskit"
    assert first["summary"]["component_count"] == 1
    assert first["summary"]["test_total"] == 3
    assert first["boundaries"]["provider_mutation_attempted"] is False
    encoded = json.dumps(first)
    assert str(tmp_path) not in encoded
    assert "grabowski" not in encoded.lower()
    dsl = render_software_dsl(first, repo_root=ROOT)
    assert "Software-Projektion" in dsl
    assert "Entscheidungen und Roadmap" in dsl
    assert "Quellsystem bleibt maßgeblich" in dsl
    assert 'w=4600' in dsl.splitlines()[0]
    assert 'x=-1725' in dsl
    assert 'x=1725' in dsl


def test_software_pilot_writes_atomic_evidence(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    snapshot = tmp_path / "out" / "snapshot.json"
    dsl = tmp_path / "out" / "view.dsl"
    receipt = write_software_pilot(
        input_path=source,
        snapshot_output=snapshot,
        dsl_output=dsl,
        repo_root=ROOT,
    )
    assert snapshot.is_file()
    assert dsl.is_file()
    assert receipt["project_id"] == "lenskit"
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["dsl_line_count"] > 10


def test_software_pilot_rejects_duplicate_semantic_ids(tmp_path: Path) -> None:
    value = software_input()
    value["components"].append(dict(value["components"][0]))
    with pytest.raises(ValueError, match="duplicate id"):
        compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)


def test_software_pilot_rejects_schema_drift(tmp_path: Path) -> None:
    value = software_input()
    del value["risks"]
    with pytest.raises(ValueError, match="input is invalid"):
        compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)


def test_software_pilot_rejects_snapshot_digest_drift(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    snapshot["summary"]["component_count"] = 99
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_software_snapshot(snapshot, repo_root=ROOT)


def test_software_pilot_rejects_symlink_input_and_output(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    source_link = tmp_path / "source-link.json"
    source_link.symlink_to(source)
    with pytest.raises(ValueError, match="non-symlink"):
        compile_software_snapshot(source_link, repo_root=ROOT)

    target = tmp_path / "target.json"
    target.write_text("untouched", encoding="utf-8")
    output_link = tmp_path / "output-link.json"
    output_link.symlink_to(target)
    with pytest.raises(ValueError, match="output path is unsafe"):
        write_software_pilot(
            input_path=source,
            snapshot_output=output_link,
            dsl_output=None,
            repo_root=ROOT,
        )
    assert target.read_text(encoding="utf-8") == "untouched"


def test_software_pilot_strips_dsl_delimiters(tmp_path: Path) -> None:
    value = software_input()
    value["purpose"] = "safe >>> injected <<< purpose"
    snapshot = compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)
    assert ">>>" not in snapshot["summary"]["purpose"]
    assert "<<<" not in snapshot["summary"]["purpose"]
    render_software_dsl(snapshot, repo_root=ROOT)


def test_software_pilot_rejects_rehashed_foreign_source(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    snapshot["sources"][0]["source_id"] = "repo.schauwerk"
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    snapshot["snapshot_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="source binding"):
        validate_software_snapshot(snapshot, repo_root=ROOT)


def _rehash(snapshot: dict) -> None:
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    snapshot["snapshot_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_software_pilot_rejects_rehashed_dsl_injection(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    snapshot["components"][0]["title"] = "safe >>> injected"
    _rehash(snapshot)
    with pytest.raises(ValueError, match="not normalized"):
        render_software_dsl(snapshot, repo_root=ROOT)


def test_software_pilot_rejects_rehashed_hidden_fields(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    snapshot["provider_item_id"] = "must-not-be-carried"
    _rehash(snapshot)
    with pytest.raises(ValueError, match="fields are invalid"):
        validate_software_snapshot(snapshot, repo_root=ROOT)


def test_software_pilot_table_emitter_escapes_pipe_cells(tmp_path: Path) -> None:
    value = software_input()
    value["components"][0]["title"] = "API | Gateway"
    snapshot = compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)
    dsl = render_software_dsl(snapshot, repo_root=ROOT)
    assert "API / Gateway" in dsl
    assert "API | Gateway" not in dsl
