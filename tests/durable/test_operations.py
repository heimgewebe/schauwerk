from __future__ import annotations

import copy
from pathlib import Path

import pytest

from schauwerk.durable.common import DurableError
from schauwerk.durable.operations import (
    compile_backup_manifest,
    compile_health_receipt,
    compile_kill_switch_drill,
    compile_oauth_rotation_plan,
    operation_profiles,
    validate_backup_manifest,
    verify_staged_restore,
)


def test_profiles_are_deterministic_and_not_installed() -> None:
    assert operation_profiles() == operation_profiles()
    assert operation_profiles()["installation_performed"] is False
    assert [item["id"] for item in operation_profiles()["profiles"]] == [
        "maintenance",
        "overview",
        "publication",
        "regie",
    ]


def test_health_distinguishes_degraded_from_failed_readiness() -> None:
    value = {
        "schema_version": "schauwerk-health-input.v1",
        "components": [
            {
                "id": "registry",
                "required": True,
                "state": "healthy",
                "evidence_sha256": "a" * 64,
                "detail": "registry valid",
            },
            {
                "id": "semantic",
                "required": False,
                "state": "failed",
                "evidence_sha256": "b" * 64,
                "detail": "optional service unavailable",
            },
        ],
    }
    receipt = compile_health_receipt(value, observed_at="2026-07-12T09:00:00Z")
    assert receipt["state"] == "degraded"
    assert receipt["ready"] is True

    value["components"][0]["state"] = "failed"
    receipt = compile_health_receipt(value, observed_at="2026-07-12T09:00:00Z")
    assert receipt["state"] == "failed"
    assert receipt["ready"] is False


def test_backup_manifest_and_staged_restore_are_non_mutating(tmp_path: Path) -> None:
    root = tmp_path / "source"
    staged = tmp_path / "staged"
    for base in (root, staged):
        (base / "registry").mkdir(parents=True)
        (base / "registry" / "sources.yaml").write_text("sources: []\n")
    declaration = {
        "schema_version": "schauwerk-backup-declaration.v1",
        "entries": [{"path": "registry/sources.yaml", "retention": "long", "class": "registry"}],
    }
    manifest = compile_backup_manifest(declaration, root=root, created_at="2026-07-12T09:00:00Z")
    assert validate_backup_manifest(manifest) == manifest
    assert manifest["copy_performed"] is False
    receipt = verify_staged_restore(
        manifest, staged_root=staged, verified_at="2026-07-12T09:05:00Z"
    )
    assert receipt["verified"] is True
    assert receipt["live_overwrite_performed"] is False
    assert receipt["mutation_attempted"] is False

    (staged / "registry" / "sources.yaml").write_text("changed\n")
    receipt = verify_staged_restore(
        manifest, staged_root=staged, verified_at="2026-07-12T09:06:00Z"
    )
    assert receipt["verified"] is False


def test_backup_rejects_secret_like_and_symlink_paths(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "oauth-token.json").write_text("secret")
    with pytest.raises(DurableError, match="secret-like"):
        compile_backup_manifest(
            {
                "schema_version": "schauwerk-backup-declaration.v1",
                "entries": [{"path": "oauth-token.json", "retention": "short", "class": "state"}],
            },
            root=root,
            created_at="2026-07-12T09:00:00Z",
        )

    target = root / "safe.json"
    target.write_text("safe")
    link = root / "linked.json"
    link.symlink_to(target)
    with pytest.raises(DurableError, match="regular file"):
        compile_backup_manifest(
            {
                "schema_version": "schauwerk-backup-declaration.v1",
                "entries": [{"path": "linked.json", "retention": "short", "class": "state"}],
            },
            root=root,
            created_at="2026-07-12T09:00:00Z",
        )


def test_backup_digest_detects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "receipt.json").write_text("{}\n")
    manifest = compile_backup_manifest(
        {
            "schema_version": "schauwerk-backup-declaration.v1",
            "entries": [{"path": "receipt.json", "retention": "standard", "class": "receipt"}],
        },
        root=root,
        created_at="2026-07-12T09:00:00Z",
    )
    tampered = copy.deepcopy(manifest)
    tampered["entries"][0]["bytes"] += 1
    with pytest.raises(DurableError, match="manifest_digest mismatch"):
        validate_backup_manifest(tampered)


def test_rotation_and_drill_compilers_do_not_touch_live_state() -> None:
    rotation = compile_oauth_rotation_plan(
        {
            "schema_version": "schauwerk-oauth-rotation-input.v1",
            "identity_digest": "a" * 64,
            "target_team": "Education team",
            "target_space": "Schauwerk",
            "board_aliases": ["pilot"],
            "rollback_reference": "owner-only metadata receipt",
        },
        created_at="2026-07-12T09:00:00Z",
    )
    assert rotation["token_accessed"] is False
    assert rotation["rotation_performed"] is False
    assert rotation["external_effect_required"] is True

    drill = compile_kill_switch_drill(
        {
            "schema_version": "schauwerk-kill-switch-drill-input.v1",
            "switch_before": False,
            "blocked_apply_proved": True,
            "switch_after": False,
            "before_evidence": "a" * 64,
            "blocked_evidence": "b" * 64,
            "after_evidence": "c" * 64,
        },
        created_at="2026-07-12T09:00:00Z",
    )
    assert drill["passed"] is True
    assert drill["live_switch_changed_by_compiler"] is False
