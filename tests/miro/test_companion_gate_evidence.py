from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import schauwerk.cli_handlers as cli_handlers
import schauwerk.surfaces.miro.companion_release as companion_release
from schauwerk.runner import main
from schauwerk.surfaces.miro.companion_release import (
    CompanionReleaseError,
    FetchResult,
    companion_gate_status,
    create_release_manifest,
)
from schauwerk.surfaces.miro.web_sdk_companion import (
    MIRO_STATIC_SCRIPT_SOURCE,
    build_companion,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/miro-web-sdk-companion-v1.json"
HTML_HEADERS = {
    "content-type": "text/html; charset=utf-8",
    "content-security-policy": (
        f"default-src 'self'; script-src 'self' {MIRO_STATIC_SCRIPT_SOURCE}; "
        "frame-ancestors https://miro.com https://*.miro.com"
    ),
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
}


def _bundle_and_manifest(tmp_path: Path) -> tuple[Path, Path, dict]:
    bundle = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=bundle)
    manifest_path = tmp_path / "release.json"
    create_release_manifest(
        bundle_dir=bundle,
        app_url="https://example.test/miro-companion",
        developer_app_label="Schauwerk Companion Test",
        output=manifest_path,
    )
    return bundle, manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def _receipt_digest(value: dict) -> str:
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_gate_evidence(path: Path, value: dict) -> Path:
    value["receipt_digest"] = _receipt_digest(value)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _gate_evidence(
    *,
    tmp_path: Path,
    manifest: dict,
    now: datetime,
) -> tuple[Path, Path]:
    app_id_digest = "a" * 64
    team_label = "Education team"
    in_board = {
        "schema_version": companion_release.IN_BOARD_READBACK_SCHEMA,
        "observed_at": (now - timedelta(minutes=5)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "success": True,
        "checks": {
            "board_id_present": True,
            "build_digest_exact": True,
            "error_message_absent": True,
            "frame_readback_complete": True,
            "miro_live": True,
            "panel_public_origin": True,
            "read_api_available": True,
            "ready": True,
            "sdk_error_absent": True,
            "state_verified": True,
            "write_api_available": True,
        },
        "binding": {
            "app_url": manifest["app_url"],
            "build_digest": manifest["build_digest"],
            "developer_app_id_sha256": app_id_digest,
            "developer_app_label": manifest["developer_app_label"],
            "release_digest": manifest["release_digest"],
            "required_scopes": manifest["required_scopes"],
            "team_label": team_label,
        },
        "location": manifest["app_url"] + "panel.html",
    }
    in_board_path = _write_gate_evidence(tmp_path / "in-board.json", in_board)
    in_board_payload = in_board_path.read_bytes()
    app_config = {
        "schema_version": companion_release.APP_CONFIG_READBACK_SCHEMA,
        "observed_at": (now - timedelta(minutes=4)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "success": True,
        "checks": {
            "app_label_present": True,
            "app_url_exact": True,
            "dashboard_authenticated": True,
            "in_board_readback_success": True,
            "no_scope_disabled": True,
            "scopes_exact": True,
            "team_present": True,
        },
        "app_url": manifest["app_url"],
        "developer_app_id_sha256": app_id_digest,
        "developer_app_label": manifest["developer_app_label"],
        "team_label": team_label,
        "required_scopes": manifest["required_scopes"],
        "checked_scopes": manifest["required_scopes"],
        "disabled_scopes": [],
        "gates": {
            "developer_app_registered": "verified",
            "oauth_authorized": "verified",
            "team_installation": "verified",
        },
        "in_board_binding": {
            "artifact_sha256": hashlib.sha256(in_board_payload).hexdigest(),
            "build_digest": manifest["build_digest"],
            "receipt_digest": in_board["receipt_digest"],
            "release_digest": manifest["release_digest"],
        },
    }
    app_config_path = _write_gate_evidence(tmp_path / "app-config.json", app_config)
    return app_config_path, in_board_path


def _passing_release_fetcher(bundle: Path):
    def fetch(url: str, _timeout: float) -> FetchResult:
        name = url.rsplit("/", 1)[-1]
        suffix = Path(name).suffix
        headers = (
            dict(HTML_HEADERS)
            if suffix == ".html"
            else {
                "content-type": {
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".svg": "image/svg+xml",
                }[suffix]
            }
        )
        return FetchResult(
            status=200,
            requested_url=url,
            final_url=url,
            headers=headers,
            body=(bundle / name).read_bytes(),
        )

    return fetch


def test_companion_gate_status_closes_only_with_fresh_bound_evidence(
    tmp_path: Path,
) -> None:
    bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)
    now = datetime(2026, 7, 25, 12, tzinfo=UTC)
    app_config, in_board = _gate_evidence(
        tmp_path=tmp_path, manifest=manifest, now=now
    )

    result = companion_gate_status(
        manifest_path=manifest_path,
        app_config_readback=app_config,
        in_board_readback=in_board,
        fetcher=_passing_release_fetcher(bundle),
        now=now,
    )

    assert result["status"] == "closed"
    assert all(gate["state"] == "verified" for gate in result["gates"].values())
    assert result["evidence"]["live_doctor"]["checked_file_count"] == len(
        manifest["files"]
    )
    assert result["release"]["release_digest"] == manifest["release_digest"]


def test_companion_gate_status_rejects_partial_expired_or_tampered_evidence(
    tmp_path: Path,
) -> None:
    bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)
    now = datetime(2026, 7, 25, 12, tzinfo=UTC)
    app_config, in_board = _gate_evidence(
        tmp_path=tmp_path, manifest=manifest, now=now
    )

    with pytest.raises(CompanionReleaseError, match="requires manifest"):
        companion_gate_status(manifest_path=manifest_path)

    with pytest.raises(CompanionReleaseError, match="has expired"):
        companion_gate_status(
            manifest_path=manifest_path,
            app_config_readback=app_config,
            in_board_readback=in_board,
            fetcher=_passing_release_fetcher(bundle),
            now=now + timedelta(hours=2),
        )

    underspecified = json.loads(in_board.read_text(encoding="utf-8"))
    underspecified.pop("receipt_digest")
    underspecified["checks"].pop("write_api_available")
    underspecified_path = _write_gate_evidence(
        tmp_path / "in-board-missing-check.json", underspecified
    )
    with pytest.raises(CompanionReleaseError, match="missing required checks"):
        companion_gate_status(
            manifest_path=manifest_path,
            app_config_readback=app_config,
            in_board_readback=underspecified_path,
            fetcher=_passing_release_fetcher(bundle),
            now=now,
        )

    disabled_scope = json.loads(app_config.read_text(encoding="utf-8"))
    disabled_scope.pop("receipt_digest")
    disabled_scope["disabled_scopes"] = ["boards:write"]
    disabled_scope_path = _write_gate_evidence(
        tmp_path / "app-config-disabled-scope.json", disabled_scope
    )
    with pytest.raises(CompanionReleaseError, match="reports disabled scopes"):
        companion_gate_status(
            manifest_path=manifest_path,
            app_config_readback=disabled_scope_path,
            in_board_readback=in_board,
            fetcher=_passing_release_fetcher(bundle),
            now=now,
        )

    tampered = json.loads(in_board.read_text(encoding="utf-8"))
    tampered["binding"]["app_url"] = "https://tampered.test/"
    in_board.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(CompanionReleaseError, match="receipt digest does not match"):
        companion_gate_status(
            manifest_path=manifest_path,
            app_config_readback=app_config,
            in_board_readback=in_board,
            fetcher=_passing_release_fetcher(bundle),
            now=now,
        )


def test_companion_gate_status_blocks_on_live_deployment_drift(tmp_path: Path) -> None:
    bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)
    now = datetime(2026, 7, 25, 12, tzinfo=UTC)
    app_config, in_board = _gate_evidence(
        tmp_path=tmp_path, manifest=manifest, now=now
    )
    passing = _passing_release_fetcher(bundle)

    def drifting_fetcher(url: str, timeout: float) -> FetchResult:
        result = passing(url, timeout)
        if url.endswith("app.js"):
            return FetchResult(
                status=result.status,
                requested_url=result.requested_url,
                final_url=result.final_url,
                headers=result.headers,
                body=result.body + b"drift",
            )
        return result

    result = companion_gate_status(
        manifest_path=manifest_path,
        app_config_readback=app_config,
        in_board_readback=in_board,
        fetcher=drifting_fetcher,
        now=now,
    )

    assert result["status"] == "blocked"
    assert result["gates"]["public_https_hosting"]["state"] == "blocked"
    assert result["gates"]["developer_app_registered"]["state"] == "verified"
    assert any("content digest mismatch" in failure for failure in result["failures"])


def test_companion_gate_status_cli_forwards_explicit_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "release.json"
    app_config = tmp_path / "app-config.json"
    in_board = tmp_path / "in-board.json"
    observed: dict = {}

    def fake_gate_status(**kwargs: object) -> dict:
        observed.update(kwargs)
        return {"status": "closed", "gate_digest": "a" * 64}

    monkeypatch.setattr(cli_handlers, "companion_gate_status", fake_gate_status)

    assert (
        main(
            [
                "miro",
                "companion",
                "gate-status",
                "--manifest",
                str(manifest),
                "--app-config-readback",
                str(app_config),
                "--in-board-readback",
                str(in_board),
                "--timeout",
                "7.5",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "closed"
    assert observed == {
        "manifest_path": manifest,
        "app_config_readback": app_config,
        "in_board_readback": in_board,
        "timeout": 7.5,
    }
