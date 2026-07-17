from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from schauwerk.pilots.software import (
    compile_software_snapshot,
    compile_software_visual_board,
    render_software_dsl,
    render_software_visual_v2_dsl,
    validate_software_snapshot,
    write_software_pilot,
)
from schauwerk.pilots.software_visual_v2 import compose_software_visual_board
from schauwerk.visual.system_v2 import audit_board_spec

ROOT = Path(__file__).resolve().parents[2]


def software_input() -> dict:
    return {
        "schema_version": "software-pilot-input.v1",
        "project_id": "repoground",
        "view_id": "repoground.software-overview",
        "sources": [
            {"source_id": "github.repoground", "revision": "a" * 40},
            {"source_id": "repo.repoground", "revision": "a" * 40},
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
        "work": [{"id": "pr-1", "title": "Current change", "status": "merged", "kind": "pr"}],
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
    assert first["project_id"] == "repoground"
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
    assert "w=4600" in dsl.splitlines()[0]
    assert "x=-1725" in dsl
    assert "x=1725" in dsl


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
    assert receipt["project_id"] == "repoground"
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["dsl_line_count"] > 10
    assert "visual_v2" not in receipt


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


def test_software_pilot_uses_shared_visual_grammar(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    rendered = render_software_dsl(snapshot, repo_root=ROOT)
    assert snapshot["schema_version"] == "software-pilot-snapshot.v1"
    assert set(snapshot["boundaries"]) == {
        "source_system_remains_authoritative",
        "contains_secret_values",
        "contains_personal_data",
        "provider_mutation_attempted",
    }
    assert "✓ gesund" in rendered
    assert "schauwerk-visual-grammar.v1" in rendered
    assert "Template software-overview-v1" in rendered


def test_software_pilot_marks_failed_tests_as_failed_not_unavailable(tmp_path: Path) -> None:
    value = software_input()
    value["tests"] = {"status": "red", "passed": 2, "failed": 1}
    snapshot = compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)

    rendered = render_software_dsl(snapshot, repo_root=ROOT)

    assert "✕ fehlgeschlagen — red" in rendered
    assert "nicht verfügbar — red" not in rendered


def test_software_visual_v2_is_deterministic_narrative_and_quality_gated(
    tmp_path: Path,
) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)

    first = compile_software_visual_board(snapshot, repo_root=ROOT)
    second = compile_software_visual_board(snapshot, repo_root=ROOT)
    quality = audit_board_spec(first)

    assert first == second
    assert first["reading_path"] == [
        "software_cover",
        "software_map",
        "software_architecture",
        "software_decisions",
        "software_delivery",
        "software_risk",
        "software_evidence",
    ]
    assert [frame["role"] for frame in first["frames"]] == [
        "cover",
        "map",
        "architecture",
        "decision",
        "delivery",
        "risk",
        "evidence",
    ]
    assert quality["ok"] is True
    assert quality["score"] >= 90
    assert quality["blockers"] == []
    assert quality["sticky_count"] == 0
    assert quality["connector_count"] >= 4
    assert (
        sum(item["kind"] == "table" for frame in first["frames"] for item in frame["objects"]) == 3
    )
    encoded = json.dumps(first, ensure_ascii=False)
    assert snapshot["snapshot_digest"] in encoded
    assert snapshot["sources"][0]["revision"][:12] in encoded
    assert "Aktualitätsgrenze" in encoded

    dsl = render_software_visual_v2_dsl(snapshot, repo_root=ROOT)
    assert "System und Verantwortung" in dsl
    assert "Evidenz und Grenzen" in dsl
    assert sum(1 for line in dsl.splitlines() if " FRAME " in line) == 7


def test_software_visual_v2_bounds_large_collections_without_hiding_omissions(
    tmp_path: Path,
) -> None:
    value = software_input()
    value["components"] = [
        {
            "id": f"component-{index:02d}",
            "title": f"Component {index}",
            "responsibility": f"Responsibility {index}",
            "status": "active",
        }
        for index in range(10)
    ]
    snapshot = compile_software_snapshot(write_input(tmp_path, value), repo_root=ROOT)

    board = compile_software_visual_board(snapshot, repo_root=ROOT)
    architecture = next(
        frame for frame in board["frames"] if frame["id"] == "software_architecture"
    )
    system = next(
        item for item in architecture["objects"] if item["id"] == "software_architecture_system"
    )
    component_shapes = [
        item for item in architecture["objects"] if item["id"].startswith("software_component_")
    ]

    assert len(component_shapes) == 3
    assert "+ 7 weitere im Snapshot" in system["content"]
    assert audit_board_spec(board)["ok"] is True


def test_software_pilot_visual_v2_outputs_are_explicit_and_digest_bound(
    tmp_path: Path,
) -> None:
    source = write_input(tmp_path)
    spec = tmp_path / "visual" / "board.json"
    quality = tmp_path / "visual" / "quality.json"
    visual_dsl = tmp_path / "visual" / "board.dsl"

    receipt = write_software_pilot(
        input_path=source,
        snapshot_output=None,
        dsl_output=None,
        visual_spec_output=spec,
        visual_quality_output=quality,
        visual_dsl_output=visual_dsl,
        repo_root=ROOT,
    )

    assert spec.is_file()
    assert quality.is_file()
    assert visual_dsl.is_file()
    assert receipt["visual_v2"]["quality_ok"] is True
    assert receipt["visual_v2"]["quality_score"] >= 90
    assert (
        receipt["visual_v2"]["board_digest"]
        == json.loads(spec.read_text(encoding="utf-8"))["board_digest"]
    )
    assert (
        receipt["visual_v2"]["quality_digest"]
        == json.loads(quality.read_text(encoding="utf-8"))["quality_digest"]
    )
    assert receipt["provider_mutation_attempted"] is False


def test_software_visual_v2_bounds_source_evidence_density(tmp_path: Path) -> None:
    snapshot = compile_software_snapshot(write_input(tmp_path), repo_root=ROOT)
    expanded = json.loads(json.dumps(snapshot))
    expanded["sources"] = [
        {
            **snapshot["sources"][index % len(snapshot["sources"])],
            "source_id": f"source-{index}-" + "x" * 80,
            "reference": "reference-" + "y" * 240,
        }
        for index in range(12)
    ]

    board = compose_software_visual_board(expanded)
    evidence = next(frame for frame in board["frames"] if frame["id"] == "software_evidence")
    source_doc = next(item for item in evidence["objects"] if item["id"] == "software_sources")

    assert "+ 7 weitere Quellen im gebundenen Snapshot" in source_doc["content"]
    assert len(source_doc["content"]) <= 900
    assert audit_board_spec(board)["ok"] is True
