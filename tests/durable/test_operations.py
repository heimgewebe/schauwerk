from __future__ import annotations

import copy
from pathlib import Path

import pytest

import schauwerk.durable.operations as durable_operations
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


def test_backup_and_restore_reject_intermediate_directory_symlink(tmp_path: Path) -> None:
    backup_root = tmp_path / "backup"
    (backup_root / "real").mkdir(parents=True)
    (backup_root / "real" / "receipt.json").write_text("{}\n")
    (backup_root / "alias").symlink_to("real", target_is_directory=True)
    declaration = {
        "schema_version": "schauwerk-backup-declaration.v1",
        "entries": [{"path": "alias/receipt.json", "retention": "long", "class": "receipt"}],
    }

    with pytest.raises(DurableError, match="no symlinks"):
        compile_backup_manifest(
            declaration, root=backup_root, created_at="2026-07-12T09:00:00Z"
        )

    source = tmp_path / "source"
    (source / "alias").mkdir(parents=True)
    (source / "alias" / "receipt.json").write_text("{}\n")
    manifest = compile_backup_manifest(
        declaration, root=source, created_at="2026-07-12T09:00:00Z"
    )
    staged = tmp_path / "staged"
    (staged / "real").mkdir(parents=True)
    (staged / "real" / "receipt.json").write_text("{}\n")
    (staged / "alias").symlink_to("real", target_is_directory=True)

    with pytest.raises(DurableError, match="no symlinks"):
        verify_staged_restore(
            manifest, staged_root=staged, verified_at="2026-07-12T09:05:00Z"
        )


def test_backup_rejects_leaf_identity_swap_during_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    target = root / "receipt.json"
    target.write_text("original\n")
    replacement = root / "replacement.json"
    replacement.write_text("replacement\n")
    original_read = durable_operations.os.read
    swapped = False

    def swapping_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        payload = original_read(descriptor, count)
        if not swapped:
            swapped = True
            replacement.replace(target)
        return payload

    monkeypatch.setattr(durable_operations.os, "read", swapping_read)
    with pytest.raises(DurableError, match="changed while it was being read"):
        compile_backup_manifest(
            {
                "schema_version": "schauwerk-backup-declaration.v1",
                "entries": [
                    {"path": "receipt.json", "retention": "standard", "class": "receipt"}
                ],
            },
            root=root,
            created_at="2026-07-12T09:00:00Z",
        )


def test_restore_rejects_leaf_identity_swap_during_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    staged = tmp_path / "staged"
    source.mkdir()
    staged.mkdir()
    for root in (source, staged):
        (root / "receipt.json").write_text("original\n")
    declaration = {
        "schema_version": "schauwerk-backup-declaration.v1",
        "entries": [
            {"path": "receipt.json", "retention": "standard", "class": "receipt"}
        ],
    }
    manifest = compile_backup_manifest(
        declaration, root=source, created_at="2026-07-12T09:00:00Z"
    )
    replacement = staged / "replacement.json"
    replacement.write_text("replacement\n")
    target = staged / "receipt.json"
    original_read = durable_operations.os.read
    swapped = False

    def swapping_read(descriptor: int, count: int) -> bytes:
        nonlocal swapped
        payload = original_read(descriptor, count)
        if not swapped:
            swapped = True
            replacement.replace(target)
        return payload

    monkeypatch.setattr(durable_operations.os, "read", swapping_read)
    with pytest.raises(DurableError, match="changed while it was being read"):
        verify_staged_restore(
            manifest, staged_root=staged, verified_at="2026-07-12T09:05:00Z"
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
