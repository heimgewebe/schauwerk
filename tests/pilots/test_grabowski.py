import json
from pathlib import Path

import pytest

from schauwerk.pilots.grabowski import (
    compile_grabowski_snapshot,
    render_grabowski_dsl,
    validate_grabowski_snapshot,
    write_grabowski_pilot,
)


def context() -> dict:
    return {
        "schema_version": 1,
        "purpose": "Bounded operator contract.",
        "capabilities": [
            {"id": "read", "category": "repository", "risk_class": "low", "read_only": True},
            {"id": "write", "category": "repository", "risk_class": "medium", "read_only": False},
            {"id": "status", "category": "runtime", "risk_class": "low", "read_only": True},
        ],
        "runtime_contract": {"expected_tools": ["read", "write", "status"]},
        "policy_contract": {"active_profile": "observe", "mode": "observe"},
        "operating_protocol": {"name": "Operator Relay v0"},
    }


def test_grabowski_pilot_is_deterministic_and_sanitized(tmp_path: Path) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(context(), sort_keys=True), encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    first = compile_grabowski_snapshot(source, repo_root=root)
    second = compile_grabowski_snapshot(source, repo_root=root)
    assert first == second
    assert first["summary"]["capability_count"] == 3
    assert first["summary"]["effectful_capability_count"] == 1
    assert first["boundaries"]["provider_mutation_attempted"] is False
    assert str(tmp_path) not in json.dumps(first)
    dsl = render_grabowski_dsl(first)
    assert "Grabowski Operator Overview" in dsl
    assert "Capability-Kategorien" in dsl


def test_grabowski_pilot_writes_snapshot_and_dsl(tmp_path: Path) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(context()), encoding="utf-8")
    snapshot = tmp_path / "out" / "snapshot.json"
    dsl = tmp_path / "out" / "view.dsl"
    root = Path(__file__).resolve().parents[2]
    receipt = write_grabowski_pilot(
        operator_context=source,
        snapshot_output=snapshot,
        dsl_output=dsl,
        repo_root=root,
    )
    assert snapshot.is_file()
    assert dsl.is_file()
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["dsl_line_count"] > 10


def test_grabowski_pilot_rejects_symlink(tmp_path: Path) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(context()), encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="non-symlink"):
        compile_grabowski_snapshot(link, repo_root=Path(__file__).resolve().parents[2])


def test_grabowski_pilot_rejects_digest_drift(tmp_path: Path) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(context()), encoding="utf-8")
    snapshot = compile_grabowski_snapshot(
        source, repo_root=Path(__file__).resolve().parents[2]
    )
    snapshot["summary"]["capability_count"] = 99
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_grabowski_snapshot(snapshot)
    with pytest.raises(ValueError, match="digest mismatch"):
        render_grabowski_dsl(snapshot)


def test_grabowski_pilot_rejects_symlink_output(tmp_path: Path) -> None:
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(context()), encoding="utf-8")
    target = tmp_path / "target.json"
    target.write_text("untouched", encoding="utf-8")
    link = tmp_path / "output.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="output path is unsafe"):
        write_grabowski_pilot(
            operator_context=source,
            snapshot_output=link,
            dsl_output=None,
            repo_root=Path(__file__).resolve().parents[2],
        )
    assert target.read_text(encoding="utf-8") == "untouched"


def test_grabowski_pilot_strips_dsl_delimiters(tmp_path: Path) -> None:
    value = context()
    value["purpose"] = "safe >>> injected <<< purpose"
    value["capabilities"][0]["category"] = "repo >>>\nmalicious"
    source = tmp_path / "operator-context.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    snapshot = compile_grabowski_snapshot(
        source, repo_root=Path(__file__).resolve().parents[2]
    )
    assert ">>>" not in snapshot["summary"]["purpose"]
    assert "<<<" not in snapshot["summary"]["purpose"]
    assert all(">>>" not in key for key in snapshot["capability_categories"])
    render_grabowski_dsl(snapshot)
