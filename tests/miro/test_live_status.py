from __future__ import annotations

import asyncio
import json
import os

import pytest

from schauwerk.surfaces.miro.client import MiroMCPClient
from schauwerk.surfaces.miro.errors import MiroCredentialError, MiroError
from schauwerk.surfaces.miro.models import MiroSettings, ToolCatalogue


def _client(tmp_path) -> MiroMCPClient:
    return MiroMCPClient(settings=MiroSettings(state_root=tmp_path / "state"))


def _catalogue() -> ToolCatalogue:
    return ToolCatalogue(
        protocol_version="2025-06-18",
        server_name="Miro MCP",
        server_version="1",
        tools=(),
    )


def test_live_status_reports_success_without_persisting_health(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path)

    async def fake_tools():
        return _catalogue()

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.live_status())

    assert result == {
        "checked": True,
        "ok": True,
        "renewal_required": False,
        "server_name": "Miro MCP",
        "tool_count": 0,
    }
    assert not client.settings.auth_health_path.exists()


def test_doctor_reports_success_and_persists_health(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path)

    async def fake_tools():
        return _catalogue()

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.doctor())

    assert result["schema_version"] == "miro-auth-doctor.v1"
    assert result["checked_live"] is True
    assert result["live_authorized"] is True
    assert result["live_authorized_known"] is True
    assert result["renewal_required"] is False
    assert result["renewal_required_known"] is True
    assert result["safe_for_live_board_operations"] is True
    assert result["local"]["auth_health_exists"] is True
    assert result["last_health"]["schema_version"] == "miro-auth-health.v1"
    assert result["last_health"]["live_authorized"] is True
    assert result["last_health"]["safe_for_live_board_operations"] is True
    assert result["last_health"]["recommended_next_command"] == "Proceed with live Miro operations."
    assert client.settings.auth_health_path.stat().st_mode & 0o077 == 0


def test_doctor_reports_renewal_required_and_persists_health(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path)

    async def fake_tools():
        raise MiroCredentialError("Miro login must be renewed")

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.doctor())

    assert result["checked_live"] is True
    assert result["live_authorized"] is False
    assert result["renewal_required"] is True
    assert result["safe_for_live_board_operations"] is False
    assert "renewed" in result["live"]["error"]
    receipt = json.loads(client.settings.auth_health_path.read_text(encoding="utf-8"))
    assert receipt["live_authorized"] is False
    assert receipt["renewal_required"] is True
    assert receipt["safe_for_live_board_operations"] is False
    assert "login" in receipt["recommended_next_command"]


def test_doctor_persists_non_credential_miro_error(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path)

    async def fake_tools():
        raise MiroError("Miro network failed")

    monkeypatch.setattr(client, "tools", fake_tools)
    result = asyncio.run(client.doctor())

    assert result["checked_live"] is True
    assert result["live_authorized"] is False
    assert result["renewal_required"] is False
    assert result["safe_for_live_board_operations"] is False
    assert result["last_health"]["live_authorized"] is False
    assert result["last_health"]["renewal_required"] is False
    assert "network" in result["live"]["error"]


def test_doctor_reports_cached_health_without_live_check(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path)

    async def fake_tools():
        return _catalogue()

    monkeypatch.setattr(client, "tools", fake_tools)
    asyncio.run(client.doctor())

    result = asyncio.run(client.doctor(check_live=False))

    assert result["schema_version"] == "miro-auth-doctor.v1"
    assert result["checked_live"] is False
    assert result["live_authorized"] is None
    assert result["live_authorized_known"] is False
    assert result["renewal_required"] is None
    assert result["renewal_required_known"] is False
    assert result["safe_for_live_board_operations"] is False
    assert result["last_health"]["live_authorized"] is True
    assert result["health_error"] is None


def test_cached_auth_health_rejects_dangling_symlink(tmp_path) -> None:
    client = _client(tmp_path)
    client.settings.state_root.mkdir(parents=True)
    client.settings.auth_health_path.symlink_to(tmp_path / "missing-health")

    with pytest.raises(MiroCredentialError, match="unsafe"):
        client.cached_auth_health()


def test_cached_auth_health_rejects_unsupported_schema(tmp_path) -> None:
    client = _client(tmp_path)
    client.settings.state_root.mkdir(parents=True)
    client.settings.auth_health_path.write_text(
        json.dumps({"schema_version": "miro-auth-health.v0"}), encoding="utf-8"
    )
    os.chmod(client.settings.auth_health_path, 0o600)

    with pytest.raises(MiroCredentialError, match="unsupported schema"):
        client.cached_auth_health()


def test_doctor_reports_cached_health_error_without_live_check(tmp_path) -> None:
    client = _client(tmp_path)
    client.settings.state_root.mkdir(parents=True)
    client.settings.auth_health_path.write_text("not-json", encoding="utf-8")
    os.chmod(client.settings.auth_health_path, 0o600)

    result = asyncio.run(client.doctor(check_live=False))

    assert result["checked_live"] is False
    assert result["last_health"] is None
    assert "unreadable" in result["health_error"]
