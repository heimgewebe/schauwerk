from __future__ import annotations

from schauwerk.surfaces.miro.client import MiroMCPClient
from schauwerk.surfaces.miro.models import MiroSettings
from schauwerk.surfaces.miro.safe_logout import safe_logout


def test_logout_removes_broken_symlinks_without_following_them(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    settings.state_root.mkdir(parents=True)
    settings.credentials_path.symlink_to(tmp_path / "missing-oauth-target")
    settings.catalogue_path.symlink_to(tmp_path / "missing-catalogue-target")
    settings.auth_health_path.symlink_to(tmp_path / "missing-auth-health-target")
    settings.auth_history_path.symlink_to(tmp_path / "missing-auth-history-target")

    outcome = safe_logout(MiroMCPClient(settings=settings))

    assert outcome == {
        "state_removed": True,
        "cache_removed": True,
        "auth_health_removed": True,
        "auth_history_removed": True,
    }
    assert not settings.credentials_path.is_symlink()
    assert not settings.catalogue_path.is_symlink()
    assert not settings.auth_health_path.is_symlink()
    assert not settings.auth_history_path.is_symlink()


def test_logout_unlinks_symlinks_but_preserves_targets(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    settings.state_root.mkdir(parents=True)
    state_target = tmp_path / "oauth-target.json"
    cache_target = tmp_path / "catalogue-target.json"
    auth_health_target = tmp_path / "auth-health-target.json"
    auth_history_target = tmp_path / "auth-history-target.json"
    state_target.write_text('{"preserve": true}\n', encoding="utf-8")
    cache_target.write_text('{"preserve": true}\n', encoding="utf-8")
    auth_health_target.write_text('{"preserve": true}\n', encoding="utf-8")
    auth_history_target.write_text('{"preserve": true}\n', encoding="utf-8")
    settings.credentials_path.symlink_to(state_target)
    settings.catalogue_path.symlink_to(cache_target)
    settings.auth_health_path.symlink_to(auth_health_target)
    settings.auth_history_path.symlink_to(auth_history_target)

    outcome = safe_logout(MiroMCPClient(settings=settings))

    assert outcome == {
        "state_removed": True,
        "cache_removed": True,
        "auth_health_removed": True,
        "auth_history_removed": True,
    }
    assert state_target.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert cache_target.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert auth_health_target.read_text(encoding="utf-8") == '{"preserve": true}\n'
    assert auth_history_target.read_text(encoding="utf-8") == '{"preserve": true}\n'


def test_logout_removes_regular_auth_receipts(tmp_path) -> None:
    settings = MiroSettings(state_root=tmp_path / "state")
    settings.state_root.mkdir(parents=True)
    settings.auth_health_path.write_text(
        '{"schema_version": "miro-auth-health.v1"}\n', encoding="utf-8"
    )
    settings.auth_history_path.write_text(
        '{"schema_version": "miro-auth-history.v1", "entries": []}\n',
        encoding="utf-8",
    )

    outcome = safe_logout(MiroMCPClient(settings=settings))

    assert outcome["auth_health_removed"] is True
    assert outcome["auth_history_removed"] is True
    assert not settings.auth_health_path.exists()
    assert not settings.auth_history_path.exists()
