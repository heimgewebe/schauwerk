from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import schauwerk.surfaces.miro.companion_evidence as evidence
from schauwerk.surfaces.miro.companion_evidence import (
    CompanionEvidenceAttention,
    CompanionEvidenceError,
    capture_evidence,
    check_evidence_config,
    evidence_status,
    install_evidence_timer,
)
from schauwerk.surfaces.miro.companion_release import (
    REQUIRED_HTML_HEADERS,
    FetchResult,
    create_release_manifest,
)
from schauwerk.surfaces.miro.web_sdk_companion import build_companion

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/miro-web-sdk-companion-v1.json"
APP_ID = "3458764678000000042"


class FakeBrowser:
    def __init__(self, *, app: dict | None = None, board: dict | None = None, error=None):
        self.app = app or _app_state()
        self.board = board or _board_state()
        self.error = error
        self.calls: list[str] = []

    def __enter__(self):
        self.calls.append("enter")
        return self

    def __exit__(self, *_args):
        self.calls.append("exit")

    async def app_config_state(self, _config, _manifest):
        self.calls.append("app")
        if self.error:
            raise self.error
        return json.loads(json.dumps(self.app))

    async def in_board_state(self, _config, _manifest):
        self.calls.append("board")
        if self.error:
            raise self.error
        return json.loads(json.dumps(self.board))


def _app_state(*, disabled: str | None = None, login: bool = False) -> dict:
    scopes = []
    for name in evidence.ALL_SCOPE_NAMES:
        scopes.append(
            {
                "name": name,
                "found": True,
                "checked": name in {"boards:read", "boards:write"},
                "disabled": name == disabled,
            }
        )
    return {
        "title": "Profile settings - Miro",
        "page_path": f"/app/settings/company/team/user-profile/apps/{APP_ID}",
        "app_url": "https://example.test/miro-companion/",
        "app_label_present": True,
        "team_present": True,
        "login_present": login,
        "scopes": scopes,
    }


def _board_state() -> dict:
    return {
        "observed_location": "https://example.test/miro-companion/panel.html",
        "ready_state": "complete",
        "miro_present": True,
        "board_api_present": True,
        "dom": {
            "mode-badge": {"text": "Miro live", "hidden": False},
            "state-badge": {"text": "verified", "hidden": False},
            "error-message": {"text": "", "hidden": True},
        },
        "sdk": {
            "board_id": "board-private-id",
            "locale": "en",
            "updated_at": "2026-07-25T00:00:00Z",
            "selection_count": 0,
            "selection_types": [],
            "frame_count": 1,
            "frame_types": ["frame"],
            "first_frame_readback": {
                "id": "frame-private-id",
                "type": "frame",
                "title": "Frame",
            },
            "frame_readback_status": "verified",
            "build_digest": None,
            "receipt_status": 200,
            "methods": [
                "createShape",
                "createText",
                "get",
                "getInfo",
                "getSelection",
                "remove",
                "sync",
            ],
        },
        "sdk_error": None,
    }


def _environment(tmp_path: Path) -> tuple[Path, Path, Path]:
    bundle = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=bundle)
    manifest_path = tmp_path / "release.json"
    create_release_manifest(
        bundle_dir=bundle,
        app_url="https://example.test/miro-companion/",
        developer_app_label="Schauwerk Companion",
        output=manifest_path,
    )
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    state = tmp_path / "state"
    executable = tmp_path / "browser"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": evidence.CONFIG_SCHEMA,
                "release_manifest": str(manifest_path),
                "state_root": str(state),
                "browser": {
                    "executable": str(executable),
                    "profile": str(profile),
                    "port": 19468,
                    "startup_seconds": 3,
                },
                "provider": {
                    "app_settings_url": (
                        "https://miro.com/app/settings/company/team/user-profile/apps/" + APP_ID
                    ),
                    "board_url": "https://miro.com/app/board/private-board-reference=/",
                    "app_menu_test_id": "app-menu__item-" + APP_ID,
                    "expected_team_label": "Education team",
                },
                "evidence_lifetime_hours": 24,
                "refresh_before_hours": 6,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    return config, bundle, manifest_path


def _fetcher(bundle: Path, *, drift: str | None = None):
    def fetch(url: str, _timeout: float) -> FetchResult:
        name = url.rsplit("/", 1)[-1]
        body = (bundle / name).read_bytes()
        if name == drift:
            body += b"drift"
        suffix = Path(name).suffix
        if suffix == ".html":
            headers = {
                "content-type": "text/html; charset=utf-8",
                **{key: "; ".join(values) for key, values in REQUIRED_HTML_HEADERS.items()},
            }
        else:
            headers = {
                "content-type": {
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".json": "application/json",
                    ".svg": "image/svg+xml",
                }[suffix]
            }
        return FetchResult(
            status=200,
            requested_url=url,
            final_url=url,
            headers=headers,
            body=body,
        )

    return fetch


def _browser_factory(fake: FakeBrowser):
    return lambda _config: fake


def _set_build_digest(fake: FakeBrowser, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fake.board["sdk"]["build_digest"] = manifest["build_digest"]


def test_config_is_private_exact_and_redacted(tmp_path: Path) -> None:
    config, _bundle, _manifest = _environment(tmp_path)
    result = check_evidence_config(config)
    assert result["success"] is True
    assert "private-board-reference" not in json.dumps(result)
    value = json.loads(config.read_text(encoding="utf-8"))
    value["provider"]["app_menu_test_id"] += "x"
    config.write_text(json.dumps(value), encoding="utf-8")
    config.chmod(0o600)
    with pytest.raises(CompanionEvidenceError, match="identities do not match"):
        check_evidence_config(config)


def test_capture_creates_immutable_generation_and_live_status(tmp_path: Path) -> None:
    config, bundle, manifest = _environment(tmp_path)
    fake = FakeBrowser()
    _set_build_digest(fake, manifest)
    now = datetime.now(UTC).replace(microsecond=0)
    result = capture_evidence(
        config,
        force=True,
        now=now,
        browser_factory=_browser_factory(fake),
        fetcher=_fetcher(bundle),
    )
    assert result["status"] == "closed"
    assert result["mutation_attempted"] is False
    generation = (
        Path(json.loads(config.read_text())["state_root"]) / "generations" / result["generation_id"]
    )
    assert {path.name for path in generation.iterdir()} == {
        "app-config.json",
        "gate-status.json",
        "generation.json",
        "in-board.json",
    }
    assert all(path.stat().st_mode & 0o077 == 0 for path in generation.iterdir())
    all_text = "\n".join(path.read_text() for path in generation.iterdir())
    assert "private-board-reference" not in all_text
    assert "board-private-id" not in all_text
    assert "frame-private-id" not in all_text
    status = evidence_status(config, fetcher=_fetcher(bundle))
    assert status["status"] == "closed"
    assert status["generation_id"] == result["generation_id"]


def test_refresh_is_idempotent_until_due_and_supersession_is_explicit(tmp_path: Path) -> None:
    config, bundle, manifest = _environment(tmp_path)
    first_browser = FakeBrowser()
    _set_build_digest(first_browser, manifest)
    first_time = datetime.now(UTC).replace(microsecond=0)
    first = capture_evidence(
        config,
        force=True,
        now=first_time,
        browser_factory=_browser_factory(first_browser),
        fetcher=_fetcher(bundle),
    )

    def forbidden_factory(_config):
        raise AssertionError("browser must not start while evidence is current")

    skipped = capture_evidence(
        config,
        now=first_time + timedelta(hours=1),
        browser_factory=forbidden_factory,
        fetcher=_fetcher(bundle),
    )
    assert skipped["refresh"] == "not_due"
    second_browser = FakeBrowser()
    _set_build_digest(second_browser, manifest)
    second = capture_evidence(
        config,
        force=True,
        now=first_time + timedelta(hours=2),
        browser_factory=_browser_factory(second_browser),
        fetcher=_fetcher(bundle),
    )
    state_root = Path(json.loads(config.read_text())["state_root"])
    generation = json.loads(
        (state_root / "generations" / second["generation_id"] / "generation.json").read_text()
    )
    assert generation["supersedes_generation"] == first["generation_id"]
    assert len(list((state_root / "generations").iterdir())) == 2


def test_attention_after_current_is_active_until_new_generation_supersedes_it(
    tmp_path: Path,
) -> None:
    config_path, bundle, manifest_path = _environment(tmp_path)
    fake = FakeBrowser()
    _set_build_digest(fake, manifest_path)
    now = datetime.now(UTC).replace(microsecond=0)
    first = capture_evidence(
        config_path,
        force=True,
        now=now,
        browser_factory=_browser_factory(fake),
        fetcher=_fetcher(bundle),
    )
    config = evidence.load_evidence_config(config_path)
    manifest = evidence._load_manifest(manifest_path)
    evidence._write_attention(
        config,
        reason_code="provider_unavailable",
        message="provider readback failed",
        observed_at=now + timedelta(minutes=1),
        release_digest=manifest["release_digest"],
    )
    active = evidence_status(config_path, fetcher=_fetcher(bundle))
    assert active["attention_required"] is True
    assert active["latest_attention"]["active"] is True

    second = capture_evidence(
        config_path,
        force=True,
        now=now + timedelta(minutes=2),
        browser_factory=_browser_factory(fake),
        fetcher=_fetcher(bundle),
    )
    assert second["generation_id"] != first["generation_id"]
    resolved = evidence_status(config_path, fetcher=_fetcher(bundle))
    assert resolved["attention_required"] is False
    assert resolved["latest_attention"]["active"] is False
    assert resolved["latest_attention"]["superseded_by_generation_id"] == second["generation_id"]


def test_app_list_redirect_opens_exact_app_read_only(tmp_path: Path) -> None:
    config_path, _bundle, manifest_path = _environment(tmp_path)
    config = evidence.load_evidence_config(config_path)
    manifest = evidence._load_manifest(manifest_path)

    class RedirectReader(evidence.CdpBrowserReader):
        def __init__(self):
            self.detail_open = False
            self.open_attempts = 0
            self.clicks = 0

        async def _navigate(self, _url: str, *, wait_seconds: float = 3) -> None:
            return None

        async def _evaluate_page(self, expression: str):
            if "app-not-listed" in expression:
                self.open_attempts += 1
                if self.open_attempts < 3:
                    return {"clicked": False, "reason": "app-not-listed"}
                self.detail_open = True
                self.clicks += 1
                return {"clicked": True}
            state = _app_state()
            if not self.detail_open:
                state["page_path"] = "/app/settings/company/team/user-profile/apps"
                state["app_url"] = None
            return state

    reader = RedirectReader()
    state = __import__("asyncio").run(reader.app_config_state(config, manifest))
    assert reader.open_attempts == 3
    assert reader.clicks == 1
    assert state["app_url"] == manifest["app_url"]
    assert state["page_path"].endswith(APP_ID)


def test_board_bootstrap_and_catalog_are_polled_before_launch(tmp_path: Path) -> None:
    config_path, _bundle, manifest_path = _environment(tmp_path)
    config = evidence.load_evidence_config(config_path)
    manifest = evidence._load_manifest(manifest_path)
    raw_board = _board_state()
    raw_board["sdk"]["build_digest"] = manifest["build_digest"]

    class BoardReader(evidence.CdpBrowserReader):
        def __init__(self):
            self.ready_attempts = 0
            self.catalog_attempts = 0
            self.panel_attempts = 0

        async def _navigate(self, _url: str, *, wait_seconds: float = 3) -> None:
            return None

        async def _evaluate_page(self, expression: str):
            if "board-ready" in expression:
                self.ready_attempts += 1
                return {
                    "ready": self.ready_attempts >= 3,
                    "login_present": False,
                }
            if "launch-companion" in expression:
                return {"state": "catalog_opened"}
            if "catalog-companion" in expression:
                self.catalog_attempts += 1
                return {"state": "launched" if self.catalog_attempts >= 3 else "app_missing"}
            raise AssertionError("unexpected board expression")

        def _targets(self):
            return [
                {
                    "type": "iframe",
                    "url": manifest["app_url"] + "panel.html",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/page/panel",
                }
            ]

        async def _evaluate_target(self, _target, _expression):
            self.panel_attempts += 1
            value = json.loads(json.dumps(raw_board))
            if self.panel_attempts < 3:
                value["dom"]["mode-badge"]["text"] = "Lädt"
                value["dom"]["state-badge"]["text"] = "—"
                value["miro_present"] = False
                value["board_api_present"] = False
                value["sdk"] = None
                value["sdk_error"] = "ReferenceError: miro is not defined"
            return value

    reader = BoardReader()
    state = __import__("asyncio").run(reader.in_board_state(config, manifest))
    assert reader.ready_attempts == 3
    assert reader.catalog_attempts == 3
    assert reader.panel_attempts == 3
    assert state["sdk"]["build_digest"] == manifest["build_digest"]


def test_authenticated_unresolved_provider_ui_is_not_mislabeled_as_login(
    tmp_path: Path,
) -> None:
    config, bundle, manifest = _environment(tmp_path)
    unresolved = _app_state()
    unresolved["app_url"] = None
    unresolved["page_path"] = "/app/settings/company/team/user-profile/apps"
    fake = FakeBrowser(app=unresolved)
    _set_build_digest(fake, manifest)
    with pytest.raises(CompanionEvidenceAttention) as caught:
        capture_evidence(
            config,
            force=True,
            now=datetime(2026, 7, 25, 8, tzinfo=UTC),
            browser_factory=_browser_factory(fake),
            fetcher=_fetcher(bundle),
        )
    assert caught.value.reason_code == "provider_ui_unresolved"

    config2, bundle2, manifest2 = _environment(tmp_path / "partial-scopes")
    partial = _app_state()
    partial["scopes"][0]["found"] = False
    fake2 = FakeBrowser(app=partial)
    _set_build_digest(fake2, manifest2)
    with pytest.raises(CompanionEvidenceAttention) as partial_error:
        capture_evidence(
            config2,
            force=True,
            now=datetime(2026, 7, 25, 9, tzinfo=UTC),
            browser_factory=_browser_factory(fake2),
            fetcher=_fetcher(bundle2),
        )
    assert partial_error.value.reason_code == "provider_ui_unresolved"


def test_auth_and_scope_failures_emit_attention_without_generation(tmp_path: Path) -> None:
    config, bundle, manifest = _environment(tmp_path)
    fake = FakeBrowser(app=_app_state(login=True))
    _set_build_digest(fake, manifest)
    with pytest.raises(CompanionEvidenceAttention) as caught:
        capture_evidence(
            config,
            force=True,
            now=datetime(2026, 7, 25, 8, tzinfo=UTC),
            browser_factory=_browser_factory(fake),
            fetcher=_fetcher(bundle),
        )
    assert caught.value.reason_code == "authentication_required"
    assert caught.value.attention_path is not None
    attention = json.loads(caught.value.attention_path.read_text())
    assert attention["mutation_attempted"] is False
    state_root = Path(json.loads(config.read_text())["state_root"])
    assert not (state_root / "generations").exists()

    config2, bundle2, manifest2 = _environment(tmp_path / "disabled")
    disabled = FakeBrowser(app=_app_state(disabled="boards:write"))
    _set_build_digest(disabled, manifest2)
    with pytest.raises(CompanionEvidenceAttention) as second:
        capture_evidence(
            config2,
            force=True,
            now=datetime(2026, 7, 25, 9, tzinfo=UTC),
            browser_factory=_browser_factory(disabled),
            fetcher=_fetcher(bundle2),
        )
    assert second.value.reason_code == "provider_configuration_drift"


def test_browser_and_public_drift_emit_bounded_attention(tmp_path: Path) -> None:
    config, bundle, manifest = _environment(tmp_path)
    fake = FakeBrowser(error=CompanionEvidenceError("raw provider failure"))
    _set_build_digest(fake, manifest)
    with pytest.raises(CompanionEvidenceAttention) as caught:
        capture_evidence(
            config,
            force=True,
            now=datetime(2026, 7, 25, 8, tzinfo=UTC),
            browser_factory=_browser_factory(fake),
            fetcher=_fetcher(bundle),
        )
    assert caught.value.reason_code == "provider_readback_failed"
    assert "raw provider failure" not in caught.value.attention_path.read_text()

    config2, bundle2, _manifest2 = _environment(tmp_path / "drift")
    with pytest.raises(CompanionEvidenceAttention) as public:
        capture_evidence(
            config2,
            force=True,
            now=datetime(2026, 7, 25, 9, tzinfo=UTC),
            browser_factory=lambda _config: pytest.fail("browser must not start"),
            fetcher=_fetcher(bundle2, drift="app.js"),
        )
    assert public.value.reason_code == "public_release_drift"


def test_current_pointer_tamper_is_fail_closed(tmp_path: Path) -> None:
    config, bundle, manifest = _environment(tmp_path)
    fake = FakeBrowser()
    _set_build_digest(fake, manifest)
    capture_evidence(
        config,
        force=True,
        now=datetime.now(UTC).replace(microsecond=0),
        browser_factory=_browser_factory(fake),
        fetcher=_fetcher(bundle),
    )
    state_root = Path(json.loads(config.read_text())["state_root"])
    current = json.loads((state_root / "current.json").read_text())
    current["expires_at"] = "2099-01-01T00:00:00Z"
    (state_root / "current.json").write_text(json.dumps(current), encoding="utf-8")
    os.chmod(state_root / "current.json", 0o600)
    with pytest.raises(CompanionEvidenceError, match="receipt digest"):
        evidence_status(config, fetcher=_fetcher(bundle))


def test_cdp_command_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    class SilentWebsocket:
        async def send(self, _payload: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(60)
            raise AssertionError("unreachable")

    monkeypatch.setattr(evidence, "CDP_COMMAND_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(CompanionEvidenceError, match="browser command timed out"):
        asyncio.run(evidence._cdp_command(SilentWebsocket(), 1, "Runtime.enable"))


def test_timer_install_is_idempotent_and_contains_no_provider_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _bundle, _manifest = _environment(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(evidence.Path, "home", classmethod(lambda cls: home))
    cli = tmp_path / "schauwerk"
    cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli.chmod(0o700)
    first = install_evidence_timer(config, cli_executable=cli)
    second = install_evidence_timer(config, cli_executable=cli)
    assert sorted(first["changed_units"]) == [
        "schauwerk-companion-evidence-refresh.service",
        "schauwerk-companion-evidence-refresh.timer",
    ]
    assert second["changed_units"] == []
    service = Path(first["service_path"]).read_text()
    assert "private-board-reference" not in service
    assert APP_ID not in service
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "TimeoutStartSec=5min" in service
    assert "TimeoutStopSec=10s" in service
    assert "KillMode=control-group" in service
    assert "evidence-capture" in service
