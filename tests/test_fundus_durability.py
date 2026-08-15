from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import schauwerk.fundus.durability as durability_module
from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.durability import (
    build_durability_evidence,
    durability_status,
    fundus_inventory,
)
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.model import canonical_json


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True)
    path.chmod(0o700)
    return path


def _write_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_bytes(canonical_json(evidence) + b"\n")
    path.chmod(0o600)


def _evidence_for(root: Path, *, ref: str = "snapshot:test") -> dict:
    return build_durability_evidence(
        fundus_inventory(root),
        producer="fixture:restore-verifier",
        evidence_ref=ref,
        verified_at="2026-08-14T16:13:34+02:00",
    )


def test_inventory_and_current_evidence_are_digest_bound(tmp_path: Path) -> None:
    root = _private_dir(tmp_path / "fundus")
    nested = _private_dir(root / "objects" / "sha256" / "aa")
    (nested / ("a" * 64)).write_bytes(b"alpha")
    (root / "receipt.json").write_bytes(b"{}\n")

    inventory = fundus_inventory(root)
    assert inventory["schema_version"] == "schauwerk-fundus-inventory.v1"
    assert inventory["file_count"] == 2
    assert inventory["total_bytes"] == 8
    assert len(inventory["inventory_sha256"]) == 64

    evidence = build_durability_evidence(
        inventory,
        producer="fixture:restore-verifier",
        evidence_ref="snapshot:abc",
        verified_at="2026-08-14T16:13:34+02:00",
    )
    schema = json.loads(
        files("schauwerk.schemas")
        .joinpath("fundus-durability-evidence.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(evidence)
    evidence_path = tmp_path / "state" / "current.json"
    _write_evidence(evidence_path, evidence)

    status = durability_status(root, evidence_path=evidence_path)
    assert status["evidence_present"] is True
    assert status["evidence_valid"] is True
    assert status["current"] is True
    assert status["restore_verified_current"] is True
    assert status["inventory_sha256"] == evidence["inventory_sha256"]
    assert status["producer"] == "fixture:restore-verifier"


def test_valid_evidence_becomes_stale_after_fundus_mutation(tmp_path: Path) -> None:
    root = _private_dir(tmp_path / "fundus")
    (root / "a.bin").write_bytes(b"a")
    evidence_path = tmp_path / "state" / "current.json"
    _write_evidence(evidence_path, _evidence_for(root))

    assert durability_status(root, evidence_path=evidence_path)["current"] is True
    (root / "b.bin").write_bytes(b"b")

    status = durability_status(root, evidence_path=evidence_path)
    assert status["evidence_valid"] is True
    assert status["current"] is False
    assert status["restore_verified_current"] is False
    assert status["evidence_inventory_sha256"] != status["inventory_sha256"]


def test_tampered_evidence_is_invalid_not_merely_stale(tmp_path: Path) -> None:
    root = _private_dir(tmp_path / "fundus")
    (root / "a.bin").write_bytes(b"a")
    evidence = _evidence_for(root)
    evidence["producer"] = "fixture:tampered"
    evidence_path = tmp_path / "state" / "current.json"
    _write_evidence(evidence_path, evidence)

    status = durability_status(root, evidence_path=evidence_path)
    assert status["evidence_present"] is True
    assert status["evidence_valid"] is False
    assert status["current"] is False
    assert "digest mismatch" in status["error"]


def test_evidence_inside_fundus_root_is_rejected(tmp_path: Path) -> None:
    root = _private_dir(tmp_path / "fundus")
    (root / "a.bin").write_bytes(b"a")
    evidence_path = root / "durability.json"
    _write_evidence(evidence_path, _evidence_for(root))

    status = durability_status(root, evidence_path=evidence_path)
    assert status["evidence_valid"] is False
    assert status["current"] is False
    assert "outside" in status["error"]


def test_inventory_rejects_symlink_entries(tmp_path: Path) -> None:
    root = _private_dir(tmp_path / "fundus")
    target = tmp_path / "outside.bin"
    target.write_bytes(b"outside")
    (root / "link.bin").symlink_to(target)

    with pytest.raises(FundusError, match="symlink"):
        fundus_inventory(root)


def test_inventory_rejects_root_replacement_during_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private_dir(tmp_path / "fundus")
    (root / "a.bin").write_bytes(b"a")
    replacement = _private_dir(tmp_path / "replacement")
    (replacement / "b.bin").write_bytes(b"b")
    moved = tmp_path / "fundus-original"
    original_scandir = durability_module.os.scandir
    calls = 0

    def replace_root(directory_fd: int):
        nonlocal calls
        handle = original_scandir(directory_fd)
        calls += 1
        if calls == 1:
            root.rename(moved)
            root.symlink_to(replacement, target_is_directory=True)
        return handle

    monkeypatch.setattr(durability_module.os, "scandir", replace_root)
    with pytest.raises(FundusError, match="data root changed"):
        fundus_inventory(root)


def test_durability_status_rejects_mutation_before_currentness_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private_dir(tmp_path / "fundus")
    (root / "a.bin").write_bytes(b"a")
    evidence_path = tmp_path / "state" / "current.json"
    _write_evidence(evidence_path, _evidence_for(root))
    original_inventory = durability_module.fundus_inventory
    calls = 0

    def mutate_before_postflight(path: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "raced.bin").write_bytes(b"race")
        return original_inventory(path)

    monkeypatch.setattr(
        durability_module, "fundus_inventory", mutate_before_postflight
    )
    status = durability_status(root, evidence_path=evidence_path)
    assert status["current"] is False
    assert status["restore_verified_current"] is False
    assert "changed before" in status["error"]


def test_custom_fundus_root_ignores_implicit_default_durability_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_root = _private_dir(tmp_path / "foreign-fundus")
    (foreign_root / "foreign.bin").write_bytes(b"foreign")
    state_home = tmp_path / "state-home"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    implicit_evidence = (
        state_home / "schauwerk" / "fundus" / "durability" / "current.json"
    )
    _write_evidence(implicit_evidence, _evidence_for(foreign_root, ref="snapshot:foreign"))
    monkeypatch.setenv(
        "SCHAUWERK_FUNDUS_DURABILITY_EVIDENCE",
        str(implicit_evidence),
    )

    registry = _private_dir(tmp_path / "registry")
    _private_dir(registry / "families")
    _private_dir(registry / "recipes")
    _private_dir(registry / "assets")
    fundus = Fundus(
        FundusPaths(data_root=tmp_path / "custom-data", registry_root=registry)
    )
    fundus._ensure_state()

    doctor = fundus.doctor()
    assert doctor["ok"] is True
    assert doctor["durability"]["evidence_path"] is None
    assert doctor["durability"]["evidence_present"] is False
    assert doctor["durability"]["evidence_valid"] is None
    assert doctor["object_store_authoritative"] is False


def test_default_fundus_root_uses_implicit_default_durability_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_home = tmp_path / "data-home"
    state_home = tmp_path / "state-home"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.delenv("SCHAUWERK_FUNDUS_ROOT", raising=False)
    monkeypatch.delenv("SCHAUWERK_FUNDUS_DURABILITY_EVIDENCE", raising=False)

    registry = _private_dir(tmp_path / "registry-default")
    _private_dir(registry / "families")
    _private_dir(registry / "recipes")
    _private_dir(registry / "assets")
    fundus = Fundus(FundusPaths.from_overrides(registry_root=registry))
    fundus._ensure_state()
    evidence_path = (
        state_home / "schauwerk" / "fundus" / "durability" / "current.json"
    )
    _write_evidence(
        evidence_path,
        _evidence_for(fundus.root, ref="snapshot:default-root"),
    )

    doctor = fundus.doctor()
    assert doctor["ok"] is True
    assert doctor["durability"]["evidence_path"] == str(evidence_path)
    assert doctor["durability"]["restore_verified_current"] is True
    assert doctor["object_store_authoritative"] is True


def test_doctor_only_marks_current_restore_verified_inventory_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    _private_dir(registry)
    _private_dir(registry / "families")
    _private_dir(registry / "recipes")
    _private_dir(registry / "assets")
    evidence_path = tmp_path / "external-state" / "current.json"
    fundus = Fundus(
        FundusPaths(
            data_root=data,
            registry_root=registry,
            durability_evidence_path=evidence_path,
        )
    )
    fundus._ensure_state()
    _write_evidence(evidence_path, _evidence_for(fundus.root, ref="snapshot:doctor"))

    doctor = fundus.doctor()
    assert doctor["ok"] is True
    assert doctor["durability"]["restore_verified_current"] is True
    assert doctor["object_store_authoritative"] is True
    assert doctor["recommended_next_action"] == (
        "no durability action required for the current Fundus inventory"
    )

    (fundus.root / "objects" / "sha256" / "new.bin").write_bytes(b"new")
    stale = fundus.doctor()
    assert stale["ok"] is True
    assert stale["durability"]["evidence_valid"] is True
    assert stale["durability"]["current"] is False
    assert stale["object_store_authoritative"] is False


def test_doctor_fails_core_health_when_present_evidence_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    _private_dir(registry)
    _private_dir(registry / "families")
    _private_dir(registry / "recipes")
    _private_dir(registry / "assets")
    evidence_path = tmp_path / "external-state" / "current.json"
    fundus = Fundus(
        FundusPaths(
            data_root=data,
            registry_root=registry,
            durability_evidence_path=evidence_path,
        )
    )
    fundus._ensure_state()
    evidence = _evidence_for(fundus.root)
    evidence["receipt_digest"] = "0" * 64
    _write_evidence(evidence_path, evidence)

    doctor = fundus.doctor()
    assert doctor["ok"] is False
    assert doctor["durability"]["evidence_valid"] is False
    assert doctor["object_store_authoritative"] is False
    assert "repair invalid durability evidence" in doctor["recommended_next_action"]
