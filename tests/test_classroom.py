from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from schauwerk.classroom import (
    prepare_classroom,
    snapshot_contains_marker,
    summarize_snapshots,
)
from schauwerk.classroom_runner import _run_classroom, build_classroom_parser, main
from schauwerk.durable.common import DurableError
from schauwerk.surfaces.miro.snapshot_model import content_digest

LEARNING = """\
learn:
  topic: "Vibe-Coding mit Kids"
  audience: "Klasse"
  guiding_question: "Wie machen wir aus einer Idee einen testbaren KI-Code-Versuch?"
  goals:
    - "einen klaren Prompt formulieren"
    - "das Ergebnis testen"
    - "einen Fehler begruendet verbessern"
  materials:
    - "Miro"
    - "Browser"
  steps:
    - title: "Idee"
      minutes: 5
      activity: "Eine kleine Programmidee festlegen."
      output: "Idee"
    - title: "Bauen"
      minutes: 15
      activity: "Prompten, ausfuehren und testen."
      output: "erster Versuch"
    - title: "Reflektieren"
      minutes: 10
      activity: "Fehler und Verbesserung festhalten."
      output: "Erkenntnis"
  collaboration: "In Kleingruppen arbeiten und Entscheidungen begruenden."
  check: "Was mussten wir selbst beurteilen, obwohl die KI Code erzeugt hat?"
"""


def _learning(tmp_path: Path, name: str = "lesson.yml") -> Path:
    path = tmp_path / name
    path.write_text(LEARNING, encoding="utf-8")
    return path


def _snapshot(
    path: Path, alias: str, items: list[dict], comments: list[dict] | None = None
) -> Path:
    core = {
        "schema_version": 1,
        "board_alias": alias,
        "items": items,
        "comments": comments or [],
    }
    value = {
        **core,
        "content_digest": content_digest(core),
        "repeatability_verified": True,
        "verified_reads": 2,
        "sanitized_references": True,
    }
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_prepare_builds_bounded_semantic_classroom_package(tmp_path: Path) -> None:
    source = _learning(tmp_path)
    output = tmp_path / "prepared"
    result = prepare_classroom(
        input_path=source,
        output_dir=output,
        group_count=3,
        template="vibe-coding",
        session_id="vibe-kids-01",
    )

    assert result["group_count"] == 3
    assert result["classroom_template"] == "vibe-coding"
    assert result["session_marker"] == "Schauwerk Classroom Session: vibe-kids-01"
    assert (
        result["epistemic_contract"]["learning_judgement"] == "prohibited from board activity alone"
    )
    group_regions = [item for item in result["regions"] if item["role"] == "group_workspace"]
    assert len(group_regions) == 3
    assert all(item["management_mode"] == "cooperative" for item in group_regions)
    dsl = (output / "classroom.dsl").read_text(encoding="utf-8")
    assert "Gruppe 1 · Arbeitsbereich" in dsl
    assert "Gruppe 3 · Arbeitsbereich" in dsl
    assert "Synthese · Schauwerk-Vorschlag" in dsl

    replay = prepare_classroom(
        input_path=source,
        output_dir=output,
        group_count=3,
        template="vibe-coding",
        session_id="vibe-kids-01",
    )
    assert replay["replayed"] is True
    with pytest.raises(DurableError, match="different package"):
        prepare_classroom(
            input_path=source,
            output_dir=output,
            group_count=4,
            template="vibe-coding",
            session_id="vibe-kids-01",
        )


def test_summary_separates_observation_from_interpretation(tmp_path: Path) -> None:
    before = _snapshot(
        tmp_path / "before.json",
        "classroom",
        [{"ref": "a", "type": "shape", "data": {"content": "Aufgabe"}}],
    )
    after = _snapshot(
        tmp_path / "after.json",
        "classroom",
        [
            {"ref": "a", "type": "shape", "data": {"content": "Aufgabe geaendert"}},
            {"ref": "b", "type": "sticky_note", "data": {"content": "Versuch"}},
        ],
    )
    result = summarize_snapshots(before_path=before, after_path=after)

    observed = {item["kind"]: item["count"] for item in result["observations"]}
    assert observed["items_added"] == 1
    assert observed["items_changed"] == 1
    assert result["structural_patterns"]["added_item_types"] == {"sticky_note": 1}
    assert result["interpretations"] == []
    assert result["learning_judgement"] == "not_established"
    assert "learning_progress" in result["does_not_establish"]


def test_summary_rejects_tampered_snapshot_digest(tmp_path: Path) -> None:
    before = _snapshot(tmp_path / "before.json", "classroom", [])
    after = _snapshot(tmp_path / "after.json", "classroom", [])
    value = json.loads(after.read_text(encoding="utf-8"))
    value["items"].append({"ref": "x", "type": "text"})
    after.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(DurableError, match="digest mismatch"):
        summarize_snapshots(before_path=before, after_path=after)


@dataclass
class _Receipt:
    value: dict

    def to_dict(self) -> dict:
        return dict(self.value)


class _FakeMiro:
    def __init__(self) -> None:
        self.applied = False
        self.marker: str | None = None
        self.layout_calls = 0

    async def snapshot(self, *, alias: str, output_path: Path, **_kwargs) -> _Receipt:
        items: list[dict] = []
        if self.applied and self.marker:
            items.append(
                {
                    "ref": "session-marker",
                    "type": "text",
                    "data": {"content": self.marker},
                }
            )
        _snapshot(output_path, alias, items)
        value = json.loads(output_path.read_text(encoding="utf-8"))
        return _Receipt(
            {
                "board_alias": alias,
                "content_digest": value["content_digest"],
                "item_count": len(items),
                "comment_count": 0,
                "item_pages": 1,
                "comment_pages": 0,
                "repeatability_verified": True,
                "output_path": str(output_path),
                "sanitized_references": True,
                "mutation_attempted": False,
            }
        )

    async def layout_create(self, *, alias: str, dsl: str, invocation_source: str) -> _Receipt:
        assert invocation_source == "schauwerk-classroom-start-v1"
        self.layout_calls += 1
        for line in dsl.splitlines():
            if "Schauwerk Classroom Session:" in line:
                content = line.split('"', 1)[1].rsplit('"', 1)[0]
                self.marker = content
                break
        assert self.marker is not None
        self.applied = True
        return _Receipt(
            {
                "board_alias": alias,
                "created_count": 10,
                "failed_count": 0,
                "success": True,
                "message": "ok",
                "result_dsl_digest": "a" * 64,
                "mutation_attempted": True,
                "sanitized_references": True,
            }
        )


def test_start_and_close_are_snapshot_bound_and_replay_safe(tmp_path: Path) -> None:
    source = _learning(tmp_path)
    prepared = tmp_path / "prepared"
    prepare_classroom(
        input_path=source,
        output_dir=prepared,
        group_count=2,
        template="vibe-coding",
        session_id="vibe-kids-live-01",
    )
    fake = _FakeMiro()
    parser = build_classroom_parser()
    session = tmp_path / "session"
    start_args = parser.parse_args(
        [
            "start",
            "classroom",
            str(prepared),
            "--session-dir",
            str(session),
            "--no-comments",
        ]
    )
    started = _run_classroom(start_args, client=fake)
    assert started["verified"] is True
    assert fake.layout_calls == 1
    marker = fake.marker
    fake.marker = None
    with pytest.raises(DurableError, match="board marker drifted"):
        _run_classroom(start_args, client=fake)
    fake.marker = marker
    assert snapshot_contains_marker(
        session / "started.json", started["session_id"].join(["Schauwerk Classroom Session: ", ""])
    )

    replay = _run_classroom(start_args, client=fake)
    assert replay["replayed"] is True
    assert fake.layout_calls == 1

    close_args = parser.parse_args(["close", "classroom", str(session), "--no-comments"])
    closed = _run_classroom(close_args, client=fake)
    assert closed["student_work_modified_by_close"] is False
    assert closed["interpretation_status"] == "not_generated_by_deterministic_core"
    assert (session / "summary.json").is_file()
    summary = json.loads((session / "summary.json").read_text(encoding="utf-8"))
    counts = {item["kind"]: item["count"] for item in summary["observations"]}
    assert counts["items_added"] == 0
    assert counts["items_changed"] == 0


def test_console_frontdoor_runs_classroom_prepare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _learning(tmp_path)
    output = tmp_path / "prepared-cli"
    code = main(
        [
            "classroom",
            "prepare",
            str(source),
            "--output-dir",
            str(output),
            "--groups",
            "2",
            "--session-id",
            "cli-01",
            "--json",
        ]
    )
    assert code == 0
    value = json.loads(capsys.readouterr().out)
    assert value["session_id"] == "cli-01"
    assert value["provider_effects"]["prepare"] is False


def test_console_frontdoor_delegates_legacy_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["registry", "status", "--json"])
    assert code == 0
    value = json.loads(capsys.readouterr().out)
    assert value["valid"] is True
