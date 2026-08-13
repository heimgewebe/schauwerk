"""Owner-only, expiry-bound Miro Web SDK companion evidence refresh."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from websockets import connect as websocket_connect

from .companion_release import (
    APP_CONFIG_READBACK_SCHEMA,
    IN_BOARD_READBACK_SCHEMA,
    CompanionReleaseError,
    Fetcher,
    _load_manifest,
    companion_gate_status,
    doctor_release,
)

CONFIG_SCHEMA = "schauwerk-miro-companion-evidence-config.v1"
GENERATION_SCHEMA = "schauwerk-miro-companion-evidence-generation.v1"
CURRENT_SCHEMA = "schauwerk-miro-companion-evidence-current.v1"
ATTENTION_SCHEMA = "schauwerk-miro-companion-evidence-attention.v1"
TIMER_INSTALL_SCHEMA = "schauwerk-miro-companion-evidence-timer-install.v1"
MAX_CDP_BYTES = 8_000_000
ALL_SCOPE_NAMES = (
    "boards:read",
    "boards:write",
    "identity:read",
    "identity:write",
    "microphone:listen",
    "screen:record",
    "team:read",
    "team:write",
    "webcam:record",
    "auditlogs:read",
    "sessions:delete",
)


class CompanionEvidenceError(CompanionReleaseError):
    """The evidence workflow is invalid or could not complete safely."""


class CompanionEvidenceAttention(CompanionEvidenceError):
    """The provider requires operator attention; no provider mutation was attempted."""

    def __init__(self, reason_code: str, message: str, *, attention_path: Path | None = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.attention_path = attention_path


@dataclass(frozen=True)
class EvidenceConfig:
    path: Path
    manifest_path: Path
    state_root: Path
    browser_executable: Path
    browser_profile: Path
    browser_port: int
    startup_seconds: float
    app_settings_url: str
    board_url: str
    app_menu_test_id: str
    expected_team_label: str
    evidence_lifetime: timedelta
    refresh_before: timedelta


class BrowserReader(Protocol):
    def __enter__(self) -> BrowserReader: ...

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...

    async def app_config_state(
        self, config: EvidenceConfig, manifest: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def in_board_state(
        self, config: EvidenceConfig, manifest: Mapping[str, Any]
    ) -> dict[str, Any]: ...


BrowserFactory = Callable[[EvidenceConfig], AbstractContextManager[BrowserReader]]


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["receipt_digest"] = _sha256(_canonical(result))
    return result


def _unsafe_path(path: Path) -> bool:
    return path.is_symlink() or any(parent.is_symlink() for parent in path.parents)


def _safe_regular(path: str | Path, label: str, *, private: bool = False) -> Path:
    candidate = Path(path).expanduser().absolute()
    if _unsafe_path(candidate):
        raise CompanionEvidenceError(f"{label} path is unsafe")
    try:
        info = candidate.stat()
    except FileNotFoundError as exc:
        raise CompanionEvidenceError(f"{label} is missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CompanionEvidenceError(f"{label} must be one regular file")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise CompanionEvidenceError(f"{label} must be owner-only")
    return candidate


def _safe_directory(
    path: str | Path,
    label: str,
    *,
    create: bool = False,
    private: bool = False,
) -> Path:
    candidate = Path(path).expanduser().absolute()
    if _unsafe_path(candidate):
        raise CompanionEvidenceError(f"{label} path is unsafe")
    if create:
        candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        info = candidate.stat()
    except FileNotFoundError as exc:
        raise CompanionEvidenceError(f"{label} is missing") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise CompanionEvidenceError(f"{label} must be a directory")
    if private and stat.S_IMODE(info.st_mode) & 0o077:
        raise CompanionEvidenceError(f"{label} must be owner-only")
    return candidate


def _write_create_only(path: Path, payload: bytes) -> None:
    if _unsafe_path(path):
        raise CompanionEvidenceError("evidence output path is unsafe")
    _safe_directory(path.parent, "evidence output parent", create=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CompanionEvidenceError("evidence output already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _write_atomic(path: Path, payload: bytes) -> None:
    if path.is_symlink() or _unsafe_path(path.parent):
        raise CompanionEvidenceError("atomic output path is unsafe")
    _safe_directory(path.parent, "atomic output parent", create=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionEvidenceError(f"{label} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CompanionEvidenceError(f"{label} must be a JSON object")
    return value


def _validate_miro_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise CompanionEvidenceError(f"{label} must be a string")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "miro.com" or host.endswith(".miro.com")):
        raise CompanionEvidenceError(f"{label} must use HTTPS on miro.com")
    if parsed.username or parsed.password or parsed.fragment:
        raise CompanionEvidenceError(f"{label} must not contain credentials or a fragment")
    return value


def _positive_number(value: Any, label: str, *, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CompanionEvidenceError(f"{label} must be numeric")
    number = float(value)
    if not minimum <= number <= maximum:
        raise CompanionEvidenceError(f"{label} must be between {minimum} and {maximum}")
    return number


def _exact_object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CompanionEvidenceError(f"{label} must be an object")
    if set(value) != fields:
        raise CompanionEvidenceError(f"{label} fields do not match the exact contract")
    return value


def _validated_browser(value: Any) -> tuple[Path, Path, int, float]:
    browser = _exact_object(
        value,
        "browser config",
        {"executable", "profile", "port", "startup_seconds"},
    )
    executable = _safe_regular(browser["executable"], "browser executable")
    if not os.access(executable, os.X_OK):
        raise CompanionEvidenceError("browser executable is not executable")
    profile = _safe_directory(browser["profile"], "browser profile", private=True)
    port = browser["port"]
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise CompanionEvidenceError("browser port must be an integer from 1024 to 65535")
    startup = _positive_number(browser["startup_seconds"], "startup_seconds", minimum=2, maximum=60)
    return executable, profile, port, startup


def _validated_provider(value: Any) -> tuple[str, str, str, str]:
    provider = _exact_object(
        value,
        "provider config",
        {
            "app_settings_url",
            "board_url",
            "app_menu_test_id",
            "expected_team_label",
        },
    )
    app_settings_url = _validate_miro_url(provider["app_settings_url"], "app_settings_url")
    board_url = _validate_miro_url(provider["board_url"], "board_url")
    menu_id = provider["app_menu_test_id"]
    if not isinstance(menu_id, str) or not re.fullmatch(
        r"app-menu__item-[A-Za-z0-9_-]{8,120}", menu_id
    ):
        raise CompanionEvidenceError("app_menu_test_id is invalid")
    app_identifier = [part for part in urlsplit(app_settings_url).path.split("/") if part][-1]
    if not menu_id.endswith(app_identifier):
        raise CompanionEvidenceError("app settings and menu identities do not match")
    team = provider["expected_team_label"]
    if not isinstance(team, str) or not 2 <= len(team.strip()) <= 160 or "\n" in team:
        raise CompanionEvidenceError("expected_team_label is invalid")
    return app_settings_url, board_url, menu_id, team.strip()


def _validated_timing(value: Mapping[str, Any]) -> tuple[timedelta, timedelta]:
    lifetime = _positive_number(
        value["evidence_lifetime_hours"],
        "evidence_lifetime_hours",
        minimum=1,
        maximum=48,
    )
    refresh = _positive_number(
        value["refresh_before_hours"],
        "refresh_before_hours",
        minimum=0.25,
        maximum=47,
    )
    if refresh >= lifetime:
        raise CompanionEvidenceError("refresh_before_hours must be less than evidence lifetime")
    return timedelta(hours=lifetime), timedelta(hours=refresh)


def load_evidence_config(path: str | Path) -> EvidenceConfig:
    source = _safe_regular(path, "evidence config", private=True)
    value = _load_json(source, "evidence config")
    if value.get("schema_version") != CONFIG_SCHEMA:
        raise CompanionEvidenceError("evidence config schema version does not match")
    value = _exact_object(
        value,
        "evidence config",
        {
            "schema_version",
            "release_manifest",
            "state_root",
            "browser",
            "provider",
            "evidence_lifetime_hours",
            "refresh_before_hours",
        },
    )
    manifest_path = _safe_regular(value["release_manifest"], "release manifest")
    state_root = _safe_directory(
        value["state_root"], "evidence state root", create=True, private=True
    )
    executable, profile, port, startup = _validated_browser(value["browser"])
    app_url, board_url, menu_id, team = _validated_provider(value["provider"])
    lifetime, refresh = _validated_timing(value)
    return EvidenceConfig(
        path=source,
        manifest_path=manifest_path,
        state_root=state_root,
        browser_executable=executable,
        browser_profile=profile,
        browser_port=port,
        startup_seconds=startup,
        app_settings_url=app_url,
        board_url=board_url,
        app_menu_test_id=menu_id,
        expected_team_label=team,
        evidence_lifetime=lifetime,
        refresh_before=refresh,
    )


def check_evidence_config(path: str | Path) -> dict[str, Any]:
    config = load_evidence_config(path)
    manifest = _load_manifest(config.manifest_path)
    return {
        "schema_version": CONFIG_SCHEMA,
        "success": True,
        "config_sha256": _sha256(config.path.read_bytes()),
        "release_digest": manifest["release_digest"],
        "browser_executable_sha256": _sha256(config.browser_executable.read_bytes()),
        "browser_profile_sha256": _sha256(str(config.browser_profile).encode()),
        "state_root_sha256": _sha256(str(config.state_root).encode()),
        "provider_targets_sha256": _sha256(
            _canonical(
                {
                    "app_settings_url": config.app_settings_url,
                    "board_url": config.board_url,
                    "app_menu_test_id": config.app_menu_test_id,
                }
            )
        ),
        "evidence_lifetime_seconds": int(config.evidence_lifetime.total_seconds()),
        "refresh_before_seconds": int(config.refresh_before.total_seconds()),
        "does_not_establish": [
            "browser availability",
            "provider authentication",
            "Miro installation or OAuth authorization",
            "permission for provider mutation",
        ],
    }


class _CaptureLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> _CaptureLock:
        _safe_directory(self.path.parent, "capture lock parent", create=True, private=True)
        self.handle = self.path.open("a+b")
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise CompanionEvidenceError("another evidence refresh is already active") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


CDP_COMMAND_TIMEOUT_SECONDS = 15.0


async def _cdp_command(
    websocket: Any, identifier: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    async def exchange() -> dict[str, Any]:
        await websocket.send(
            json.dumps({"id": identifier, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(await websocket.recv())
            if message.get("id") != identifier:
                continue
            if message.get("error"):
                raise CompanionEvidenceError(f"browser command failed: {method}")
            return message

    try:
        return await asyncio.wait_for(exchange(), timeout=CDP_COMMAND_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise CompanionEvidenceError(f"browser command timed out: {method}") from exc


class CdpBrowserReader:
    def __init__(self, config: EvidenceConfig):
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> CdpBrowserReader:
        endpoint = f"http://127.0.0.1:{self.config.browser_port}/json/list"
        try:
            with httpx.Client(trust_env=False, timeout=1) as client:
                response = client.get(endpoint)
            if response.status_code == 200:
                raise CompanionEvidenceAttention(
                    "browser_port_in_use",
                    "the configured private browser port is already in use",
                )
        except httpx.ConnectError:
            pass
        command = [
            str(self.config.browser_executable),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={self.config.browser_port}",
            f"--user-data-dir={self.config.browser_profile}",
            "about:blank",
        ]
        self.process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.config.startup_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise CompanionEvidenceAttention(
                    "browser_start_failed", "the private evidence browser exited during startup"
                )
            try:
                if self._targets():
                    return self
            except CompanionEvidenceError:
                pass
            time.sleep(0.2)
        self.__exit__(None, None, None)
        raise CompanionEvidenceAttention(
            "browser_start_failed", "the private evidence browser did not become ready"
        )

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, 15)
                self.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, 9)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        self.process = None

    def _targets(self) -> list[dict[str, Any]]:
        url = f"http://127.0.0.1:{self.config.browser_port}/json/list"
        try:
            with httpx.Client(trust_env=False, timeout=5) as client:
                response = client.get(url)
                response.raise_for_status()
                value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CompanionEvidenceError("browser control endpoint is unavailable") from exc
        if not isinstance(value, list):
            raise CompanionEvidenceError("browser target inventory is invalid")
        return [item for item in value if isinstance(item, dict)]

    def _page_target(self) -> dict[str, Any]:
        pages = [target for target in self._targets() if target.get("type") == "page"]
        pages.sort(key=lambda target: "miro.com" not in str(target.get("url", "")))
        if not pages or not isinstance(pages[0].get("webSocketDebuggerUrl"), str):
            raise CompanionEvidenceError("browser page target is unavailable")
        return pages[0]

    async def _evaluate_target(self, target: Mapping[str, Any], expression: str) -> Any:
        socket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(socket_url, str) or not socket_url.startswith("ws://127.0.0.1:"):
            raise CompanionEvidenceError("browser target socket is not loopback-bound")
        async with websocket_connect(socket_url, max_size=MAX_CDP_BYTES) as websocket:
            await _cdp_command(websocket, 1, "Runtime.enable")
            result = await _cdp_command(
                websocket,
                2,
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True, "awaitPromise": True},
            )
        remote = result.get("result", {}).get("result", {})
        if remote.get("subtype") == "error" or "exceptionDetails" in result.get("result", {}):
            raise CompanionEvidenceError("browser page evaluation failed")
        return remote.get("value")

    async def _evaluate_page(self, expression: str) -> Any:
        return await self._evaluate_target(self._page_target(), expression)

    async def _navigate(self, url: str, *, wait_seconds: float = 3) -> None:
        target = self._page_target()
        socket_url = target["webSocketDebuggerUrl"]
        async with websocket_connect(socket_url, max_size=MAX_CDP_BYTES) as websocket:
            await _cdp_command(websocket, 1, "Page.enable")
            await _cdp_command(websocket, 2, "Page.navigate", {"url": url})
        deadline = time.monotonic() + max(wait_seconds, 2)
        while time.monotonic() < deadline:
            try:
                ready = await self._evaluate_page("document.readyState")
            except CompanionEvidenceError:
                ready = None
            if ready == "complete":
                await asyncio.sleep(1)
                return
            await asyncio.sleep(0.2)
        raise CompanionEvidenceAttention(
            "provider_unavailable", "the Miro provider page did not finish loading"
        )

    async def app_config_state(
        self, config: EvidenceConfig, manifest: Mapping[str, Any]
    ) -> dict[str, Any]:
        await self._navigate(config.app_settings_url, wait_seconds=8)
        scope_names = json.dumps(ALL_SCOPE_NAMES)
        app_label = json.dumps(manifest["developer_app_label"])
        team_label = json.dumps(config.expected_team_label)
        expression = f"""
(() => {{
  const scopeNames = {scope_names};
  const appLabel = {app_label};
  const teamLabel = {team_label};
  const bodyText = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
  const resolveInput = (label) => {{
    if (!label) return null;
    if (label.htmlFor) {{ const found = document.getElementById(label.htmlFor); if (found) return found; }}
    return label.querySelector('input') || label.parentElement?.querySelector('input') || null;
  }};
  const scopes = scopeNames.map((name) => {{
    const label = [...document.querySelectorAll('label')].find((e) => (e.innerText || '').trim() === name);
    const input = resolveInput(label);
    const checked = input ? (input.getAttribute('role') === 'checkbox' ? input.getAttribute('aria-checked') === 'true' : !!input.checked) : null;
    return {{name, found: !!label && !!input, checked, disabled: input ? !!input.disabled : null}};
  }});
  const appUrl = document.querySelector('[name="app-text-input-1"], [placeholder="https://example.com/index.html"]');
  return {{
    title: document.title,
    page_path: location.pathname,
    app_url: appUrl?.value || null,
    app_label_present: bodyText.includes(appLabel),
    team_present: bodyText.includes(teamLabel),
    login_present: !!document.querySelector('input[type="email"], input[type="password"]') || /log in|sign in/i.test(document.title),
    scopes
  }};
}})()
"""
        value = await self._evaluate_page(expression)
        if not isinstance(value, dict):
            raise CompanionEvidenceError("Developer App page returned an invalid state")
        if value.get("app_url") is None and value.get("login_present") is False:
            value = await self._open_app_detail(expression, app_label)
        return value

    async def _open_app_detail(self, state_expression: str, app_label: str) -> dict[str, Any]:
        open_expression = f"""
(() => {{
  const appLabel = {app_label};
  const row = [...document.querySelectorAll('.app-item')].find((element) => {{
    const name = element.querySelector('.app-item__app-name');
    return (name?.innerText || '').trim() === appLabel;
  }});
  if (!row) return {{clicked: false, reason: 'app-not-listed'}};
  row.scrollIntoView({{block: 'center'}});
  row.click();
  return {{clicked: true}};
}})()
"""
        deadline = time.monotonic() + 12
        opened = False
        value: dict[str, Any] = {}
        while time.monotonic() < deadline:
            if not opened:
                attempt = await self._evaluate_page(open_expression)
                opened = isinstance(attempt, dict) and attempt.get("clicked") is True
            await asyncio.sleep(0.25)
            candidate = await self._evaluate_page(state_expression)
            if not isinstance(candidate, dict):
                raise CompanionEvidenceError("Developer App page returned an invalid state")
            value = candidate
            scopes = value.get("scopes")
            complete = (
                isinstance(scopes, list)
                and len(scopes) == len(ALL_SCOPE_NAMES)
                and all(isinstance(item, dict) and item.get("found") is True for item in scopes)
            )
            if value.get("login_present") is True or (
                value.get("app_url") is not None and complete
            ):
                break
        return value

    async def _wait_for_board_ready(self, menu_id: str, catalog_id: str) -> None:
        expression = f"""
(() => {{
  /* board-ready */
  const menuId = {menu_id};
  const catalogId = {catalog_id};
  const skeleton = [...document.querySelectorAll('[data-testid]')].some((element) =>
    (element.getAttribute('data-testid') || '').includes('skeleton')
  );
  return {{
    ready: !skeleton && !!document.querySelector(
      `[data-testid="${{menuId}}"], [data-testid="${{catalogId}}"]`
    ),
    login_present: !!document.querySelector('input[type="email"], input[type="password"]')
  }};
}})()
"""
        deadline = time.monotonic() + 30
        observed: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            candidate = await self._evaluate_page(expression)
            if isinstance(candidate, dict):
                observed = candidate
                if candidate.get("login_present") is True or candidate.get("ready") is True:
                    break
            await asyncio.sleep(0.25)
        if isinstance(observed, dict) and observed.get("ready") is True:
            return
        reason = (
            "authentication_required"
            if isinstance(observed, dict) and observed.get("login_present") is True
            else "provider_unavailable"
        )
        raise CompanionEvidenceAttention(
            reason, "the authenticated Miro board did not reach a stable launcher state"
        )

    async def _launch_board_companion(self, menu_id: str, catalog_id: str) -> None:
        launch = await self._evaluate_page(
            f"""
(() => {{
  /* launch-companion */
  const menuId = {menu_id};
  const catalogId = {catalog_id};
  const existing = document.querySelector(`[data-testid="${{menuId}}"]`);
  if (existing) {{ existing.scrollIntoView({{block:'center'}}); existing.click(); return {{state:'launched'}}; }}
  const catalog = document.querySelector(`[data-testid="${{catalogId}}"]`);
  if (!catalog) return {{state:'catalog_missing'}};
  catalog.click();
  return {{state:'catalog_opened'}};
}})()
"""
        )
        if not isinstance(launch, dict):
            raise CompanionEvidenceError("Miro board launcher returned an invalid state")
        if launch.get("state") == "catalog_opened":
            launch = await self._launch_from_catalog(menu_id)
        if launch.get("state") != "launched":
            raise CompanionEvidenceAttention(
                "installation_or_authorization_required",
                "the Schauwerk Companion is not available in the authenticated board",
            )

    async def _launch_from_catalog(self, menu_id: str) -> dict[str, Any]:
        expression = f"""
(() => {{
  /* catalog-companion */
  const item = document.querySelector(`[data-testid="${{{menu_id}}}"]`);
  if (!item) return {{state:'app_missing'}};
  item.scrollIntoView({{block:'center'}});
  item.click();
  return {{state:'launched'}};
}})()
"""
        deadline = time.monotonic() + 15
        launch: dict[str, Any] = {"state": "app_missing"}
        while time.monotonic() < deadline:
            candidate = await self._evaluate_page(expression)
            if isinstance(candidate, dict):
                launch = candidate
                if candidate.get("state") == "launched":
                    break
            await asyncio.sleep(0.25)
        return launch

    async def _wait_for_panel(self, panel_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            panel = next(
                (
                    target
                    for target in self._targets()
                    if target.get("type") == "iframe"
                    and str(target.get("url", "")).startswith(panel_url)
                ),
                None,
            )
            if panel is not None:
                return panel
            await asyncio.sleep(0.3)
        raise CompanionEvidenceAttention(
            "oauth_or_installation_required",
            "the authenticated companion panel did not load",
        )

    @staticmethod
    def _panel_terminal(value: Mapping[str, Any]) -> tuple[bool, bool]:
        dom = value.get("dom") if isinstance(value.get("dom"), dict) else {}
        mode = dom.get("mode-badge") if isinstance(dom.get("mode-badge"), dict) else {}
        state = dom.get("state-badge") if isinstance(dom.get("state-badge"), dict) else {}
        error = dom.get("error-message") if isinstance(dom.get("error-message"), dict) else {}
        success = (
            mode.get("text") == "Miro live"
            and state.get("text") == "verified"
            and error.get("hidden") is True
            and value.get("sdk_error") is None
        )
        failed = error.get("hidden") is False
        return success, failed

    async def _read_panel_state(self, panel: Mapping[str, Any]) -> dict[str, Any]:
        expression = r"""
(async () => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 500);
  const ids = ['mode-badge','state-badge','error-message'];
  const dom = Object.fromEntries(ids.map((id) => {
    const element = document.getElementById(id);
    return [id, element ? {text: clean(element.textContent), hidden: !!element.hidden} : null];
  }));
  let sdk = null;
  let sdkError = null;
  try {
    const [info, selected, frames, receiptResponse] = await Promise.all([
      miro.board.getInfo(), miro.board.getSelection(), miro.board.get({type:'frame'}),
      fetch('./build-receipt.json', {cache:'no-store'})
    ]);
    const first = Array.isArray(frames) && frames.length ? frames[0] : null;
    let firstRead = null;
    if (first && typeof first.id === 'string') {
      const got = await miro.board.get({id:first.id});
      const item = Array.isArray(got) ? got[0] : got;
      firstRead = item ? {id:item.id || null, type:item.type || null, title:clean(item.title || item.content || '')} : null;
    }
    const receipt = receiptResponse.ok ? await receiptResponse.json() : null;
    const board = globalThis.miro?.board;
    const methods = [...new Set([
      ...Object.getOwnPropertyNames(board || {}),
      ...Object.getOwnPropertyNames(Object.getPrototypeOf(board) || {})
    ])].filter((name) => typeof board?.[name] === 'function').sort();
    sdk = {
      board_id: typeof info?.id === 'string' ? info.id : null,
      locale: info?.locale || null,
      updated_at: info?.updatedAt || null,
      selection_count: Array.isArray(selected) ? selected.length : null,
      selection_types: Array.isArray(selected) ? selected.map((item) => item?.type || 'unknown').sort() : null,
      frame_count: Array.isArray(frames) ? frames.length : null,
      frame_types: Array.isArray(frames) ? frames.map((item) => item?.type || 'unknown').sort() : null,
      first_frame_readback: firstRead,
      frame_readback_status: first ? (firstRead ? 'verified' : 'missing') : 'not_applicable_no_frames',
      build_digest: receipt?.build_digest || null,
      receipt_status: receiptResponse.status,
      methods
    };
  } catch (error) {
    sdkError = clean(error?.stack || error?.message || error);
  }
  return {
    observed_location: location.href.split('?')[0],
    ready_state: document.readyState,
    miro_present: !!globalThis.miro,
    board_api_present: !!globalThis.miro?.board,
    dom,
    sdk,
    sdk_error: sdkError
  };
})()
"""
        deadline = time.monotonic() + 20
        value: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            candidate = await self._evaluate_target(panel, expression)
            if not isinstance(candidate, dict):
                raise CompanionEvidenceError("companion panel returned an invalid state")
            value = candidate
            success, failed = self._panel_terminal(candidate)
            if success or failed:
                break
            await asyncio.sleep(0.25)
        if value is None:
            raise CompanionEvidenceError("companion panel returned no state")
        return value

    async def in_board_state(
        self, config: EvidenceConfig, manifest: Mapping[str, Any]
    ) -> dict[str, Any]:
        await self._navigate(config.board_url, wait_seconds=12)
        menu_id = json.dumps(config.app_menu_test_id)
        catalog_id = json.dumps("CreationBarButton--CATALOG")
        await self._wait_for_board_ready(menu_id, catalog_id)
        await self._launch_board_companion(menu_id, catalog_id)
        panel_url = urljoin(manifest["app_url"], "panel.html")
        panel = await self._wait_for_panel(panel_url)
        return await self._read_panel_state(panel)


def _browser_factory(config: EvidenceConfig) -> CdpBrowserReader:
    return CdpBrowserReader(config)


def _latest_attention(state_root: Path) -> dict[str, Any] | None:
    root = state_root / "attention"
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("*.json"), reverse=True)
    if not candidates:
        return None
    value = _load_json(_safe_regular(candidates[0], "attention receipt", private=True), "attention")
    return {
        "reason_code": value.get("reason_code"),
        "observed_at": value.get("observed_at"),
        "receipt_digest": value.get("receipt_digest"),
        "artifact_sha256": _sha256(candidates[0].read_bytes()),
    }


def _attention_projection(
    state_root: Path, current: Mapping[str, Any] | None
) -> tuple[dict[str, Any] | None, bool]:
    latest = _latest_attention(state_root)
    if latest is None:
        return None, False
    projected = dict(latest)
    if current is None:
        projected["active"] = True
        return projected, True
    try:
        attention_at = datetime.fromisoformat(
            str(latest["observed_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        current_at = datetime.fromisoformat(
            str(current["observed_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise CompanionEvidenceError("attention chronology is invalid") from exc
    active = attention_at > current_at
    projected["active"] = active
    if not active:
        projected["superseded_by_generation_id"] = current.get("generation_id")
        projected["superseded_at"] = current.get("observed_at")
    return projected, active


def _read_current(config: EvidenceConfig) -> dict[str, Any] | None:
    path = config.state_root / "current.json"
    if not path.exists():
        return None
    source = _safe_regular(path, "current evidence pointer", private=True)
    value = _load_json(source, "current evidence pointer")
    if value.get("schema_version") != CURRENT_SCHEMA:
        raise CompanionEvidenceError("current evidence pointer schema does not match")
    observed = value.get("receipt_digest")
    unsigned = dict(value)
    unsigned.pop("receipt_digest", None)
    if observed != _sha256(_canonical(unsigned)):
        raise CompanionEvidenceError("current evidence pointer receipt digest does not match")
    return value


def _generation_paths(
    config: EvidenceConfig, current: Mapping[str, Any]
) -> tuple[Path, Path, Path, Path]:
    generation_id = current.get("generation_id")
    if not isinstance(generation_id, str) or not re.fullmatch(
        r"[0-9TZ-]{16,40}-[0-9a-f]{12}", generation_id
    ):
        raise CompanionEvidenceError("current generation identity is invalid")
    root = _safe_directory(config.state_root / "generations" / generation_id, "generation")
    return (
        _safe_regular(root / "app-config.json", "app-config evidence", private=True),
        _safe_regular(root / "in-board.json", "in-board evidence", private=True),
        _safe_regular(root / "gate-status.json", "gate-status evidence", private=True),
        _safe_regular(root / "generation.json", "generation manifest", private=True),
    )


def evidence_status(
    path: str | Path, *, timeout: float = 10, fetcher: Fetcher | None = None
) -> dict[str, Any]:
    config = load_evidence_config(path)
    current = _read_current(config)
    latest_attention, attention_required = _attention_projection(config.state_root, current)
    if current is None:
        return {
            "schema_version": CURRENT_SCHEMA,
            "status": "missing",
            "attention_required": attention_required,
            "latest_attention": latest_attention,
        }
    app_path, board_path, stored_gate_path, generation_path = _generation_paths(config, current)
    generation = _load_json(generation_path, "generation manifest")
    observed = generation.get("receipt_digest")
    unsigned = dict(generation)
    unsigned.pop("receipt_digest", None)
    if generation.get("schema_version") != GENERATION_SCHEMA or observed != _sha256(
        _canonical(unsigned)
    ):
        raise CompanionEvidenceError("generation manifest receipt is invalid")
    artifact_paths = {
        "app_config": app_path,
        "in_board": board_path,
        "gate_status": stored_gate_path,
    }
    inventory = generation.get("artifacts")
    if not isinstance(inventory, dict):
        raise CompanionEvidenceError("generation artifact inventory is missing")
    for name, artifact in artifact_paths.items():
        if not isinstance(inventory.get(name), dict):
            raise CompanionEvidenceError(f"generation artifact is missing: {name}")
        if inventory[name].get("sha256") != _sha256(artifact.read_bytes()):
            raise CompanionEvidenceError(f"generation artifact digest does not match: {name}")
    live = companion_gate_status(
        manifest_path=config.manifest_path,
        app_config_readback=app_path,
        in_board_readback=board_path,
        timeout=timeout,
        fetcher=fetcher,
    )
    if current.get("generation_manifest_sha256") != _sha256(generation_path.read_bytes()):
        raise CompanionEvidenceError("current pointer generation digest does not match")
    if current.get("generation_receipt_digest") != generation.get("receipt_digest"):
        raise CompanionEvidenceError("current pointer generation receipt does not match")
    stored = _load_json(stored_gate_path, "stored gate status")
    return {
        "schema_version": CURRENT_SCHEMA,
        "status": live["status"],
        "generation_id": current["generation_id"],
        "observed_at": current["observed_at"],
        "expires_at": current["expires_at"],
        "release_digest": current["release_digest"],
        "gate_digest": live["gate_digest"],
        "stored_gate_digest": stored.get("gate_digest"),
        "current_pointer_digest": current["receipt_digest"],
        "generation_receipt_digest": generation["receipt_digest"],
        "attention_required": attention_required,
        "latest_attention": latest_attention,
        "does_not_establish": [
            "provider availability after the evidence expiry",
            "permission for interactive authorization or board mutation",
        ],
    }


def _write_attention(
    config: EvidenceConfig,
    *,
    reason_code: str,
    message: str,
    observed_at: datetime,
    release_digest: str,
) -> Path:
    value = _receipt(
        {
            "schema_version": ATTENTION_SCHEMA,
            "attention_required": True,
            "reason_code": reason_code,
            "message": message,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "release_digest": release_digest,
            "config_sha256": _sha256(config.path.read_bytes()),
            "provider_targets_sha256": _sha256(
                _canonical(
                    {
                        "app_settings_url": config.app_settings_url,
                        "board_url": config.board_url,
                        "app_menu_test_id": config.app_menu_test_id,
                    }
                )
            ),
            "mutation_attempted": False,
            "next_action": "restore the existing authenticated Miro session manually, then rerun refresh",
            "does_not_establish": [
                "permission to log in, consent, install, change scopes, or mutate a board",
                "whether credentials remain valid outside this failed observation",
            ],
        }
    )
    stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
    path = config.state_root / "attention" / f"{stamp}-{reason_code}.json"
    _write_create_only(path, _pretty(value))
    return path


def _normalize_app_state(
    raw: Mapping[str, Any], config: EvidenceConfig, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    if raw.get("login_present") is True:
        raise CompanionEvidenceAttention(
            "authentication_required", "the private Miro dashboard session requires login"
        )
    if raw.get("app_url") is None:
        raise CompanionEvidenceAttention(
            "provider_ui_unresolved",
            "the authenticated Miro dashboard did not expose the configured app details",
        )
    scopes = raw.get("scopes")
    if not isinstance(scopes, list):
        raise CompanionEvidenceError("Developer App scope readback is invalid")
    scope_inventory = {
        item.get("name"): item
        for item in scopes
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if set(scope_inventory) != set(ALL_SCOPE_NAMES) or any(
        scope_inventory[name].get("found") is not True for name in ALL_SCOPE_NAMES
    ):
        raise CompanionEvidenceAttention(
            "provider_ui_unresolved",
            "the authenticated Miro dashboard did not expose the complete scope catalogue",
        )
    checked = sorted(
        item["name"]
        for item in scopes
        if isinstance(item, dict) and item.get("found") is True and item.get("checked") is True
    )
    disabled = sorted(
        item["name"]
        for item in scopes
        if isinstance(item, dict) and item.get("found") is True and item.get("disabled") is True
    )
    expected_path = urlsplit(config.app_settings_url).path.rstrip("/")
    observed_path = str(raw.get("page_path") or "").rstrip("/")
    checks = {
        "dashboard_authenticated": raw.get("login_present") is False,
        "app_detail_path_exact": observed_path == expected_path,
        "app_label_present": raw.get("app_label_present") is True,
        "team_present": raw.get("team_present") is True,
        "app_url_exact": raw.get("app_url") == manifest["app_url"],
        "scopes_exact": checked == manifest["required_scopes"],
        "no_scope_disabled": disabled == [],
    }
    if not all(checks.values()):
        raise CompanionEvidenceAttention(
            "provider_configuration_drift",
            "the Developer App URL, identity, team, or scopes differ from the release contract",
        )
    return {"checked_scopes": checked, "disabled_scopes": disabled, "checks": checks}


def _normalize_board_state(
    raw: Mapping[str, Any], config: EvidenceConfig, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    sdk = raw.get("sdk")
    if not isinstance(sdk, dict):
        if raw.get("sdk_error"):
            raise CompanionEvidenceAttention(
                "oauth_or_sdk_authorization_required",
                "the companion panel could not access the Miro Web SDK",
            )
        raise CompanionEvidenceError("in-board SDK readback is invalid")
    methods = sdk.pop("methods", None)
    if not isinstance(methods, list) or not all(isinstance(item, str) for item in methods):
        raise CompanionEvidenceError("in-board SDK method catalogue is invalid")
    board_id = sdk.pop("board_id", None)
    first_frame = sdk.get("first_frame_readback")
    if isinstance(first_frame, dict) and isinstance(first_frame.get("id"), str):
        first_id = first_frame.pop("id")
        first_frame["id_sha256"] = _sha256(first_id.encode())
    sdk["board_id_present"] = isinstance(board_id, str) and bool(board_id)
    sdk["board_id_sha256"] = _sha256(board_id.encode()) if isinstance(board_id, str) else None
    sdk["observed_method_count"] = len(methods)
    sdk["method_catalog_sha256"] = _sha256(_canonical(sorted(methods)))
    sdk["api_methods"] = {
        name: "function" if name in methods else "undefined"
        for name in (
            "createShape",
            "createText",
            "get",
            "getInfo",
            "getSelection",
            "remove",
            "sync",
        )
    }
    dom = raw.get("dom") if isinstance(raw.get("dom"), dict) else {}
    checks = {
        "panel_public_origin": raw.get("observed_location")
        == urljoin(manifest["app_url"], "panel.html"),
        "ready": raw.get("ready_state") == "complete",
        "miro_live": isinstance(dom.get("mode-badge"), dict)
        and dom["mode-badge"].get("text") == "Miro live",
        "state_verified": isinstance(dom.get("state-badge"), dict)
        and dom["state-badge"].get("text") == "verified",
        "sdk_error_absent": raw.get("sdk_error") is None,
        "board_id_present": sdk["board_id_present"] is True,
        "build_digest_exact": sdk.get("build_digest") == manifest["build_digest"],
        "error_message_absent": isinstance(dom.get("error-message"), dict)
        and dom["error-message"].get("hidden") is True,
        "frame_readback_complete": sdk.get("frame_readback_status")
        in {"verified", "not_applicable_no_frames"},
        "read_api_available": all(
            sdk["api_methods"].get(name) == "function"
            for name in ("get", "getInfo", "getSelection")
        ),
        "write_api_available": all(
            sdk["api_methods"].get(name) == "function"
            for name in ("createShape", "createText", "remove", "sync")
        ),
    }
    if not all(checks.values()):
        raise CompanionEvidenceAttention(
            "in_board_readback_incomplete",
            "the authenticated in-board companion readback does not satisfy the release contract",
        )
    app_identifier = [part for part in urlsplit(config.app_settings_url).path.split("/") if part][
        -1
    ]
    return {
        "sdk": sdk,
        "dom": dom,
        "checks": checks,
        "app_id_sha256": _sha256(app_identifier.encode()),
    }


def capture_evidence(
    path: str | Path,
    *,
    force: bool = False,
    timeout: float = 10,
    now: datetime | None = None,
    browser_factory: BrowserFactory | None = None,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    config = load_evidence_config(path)
    manifest = _load_manifest(config.manifest_path)
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    with _CaptureLock(config.state_root / "refresh.lock"):
        current = _read_current(config)
        if not force and current is not None:
            expires = datetime.fromisoformat(str(current["expires_at"]).replace("Z", "+00:00"))
            if (
                current.get("release_digest") == manifest["release_digest"]
                and expires - observed_at > config.refresh_before
            ):
                status = evidence_status(config.path, timeout=timeout, fetcher=fetcher)
                status["refresh"] = "not_due"
                return status
        doctor = doctor_release(
            manifest_path=config.manifest_path, timeout=timeout, fetcher=fetcher
        )
        if doctor.get("success") is not True:
            attention = _write_attention(
                config,
                reason_code="public_release_drift",
                message="the public companion release no longer matches its manifest",
                observed_at=observed_at,
                release_digest=manifest["release_digest"],
            )
            raise CompanionEvidenceAttention(
                "public_release_drift",
                "public companion release drift requires operator attention",
                attention_path=attention,
            )
        factory = browser_factory or _browser_factory
        try:
            with factory(config) as browser:
                raw_app = asyncio.run(browser.app_config_state(config, manifest))
                app = _normalize_app_state(raw_app, config, manifest)
                raw_board = asyncio.run(browser.in_board_state(config, manifest))
                board = _normalize_board_state(raw_board, config, manifest)
        except CompanionEvidenceAttention as exc:
            attention = _write_attention(
                config,
                reason_code=exc.reason_code,
                message=str(exc),
                observed_at=observed_at,
                release_digest=manifest["release_digest"],
            )
            exc.attention_path = attention
            raise
        except CompanionEvidenceError as exc:
            attention = _write_attention(
                config,
                reason_code="provider_readback_failed",
                message="the read-only provider readback failed before evidence completion",
                observed_at=observed_at,
                release_digest=manifest["release_digest"],
            )
            raise CompanionEvidenceAttention(
                "provider_readback_failed",
                "the read-only provider readback requires operator attention",
                attention_path=attention,
            ) from exc
        expires_at = observed_at + config.evidence_lifetime
        timestamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
        generation_id = f"{timestamp}-{manifest['release_digest'][:12]}"
        generation_root = config.state_root / "generations" / generation_id
        if generation_root.exists():
            raise CompanionEvidenceError("evidence generation already exists")
        generation_root.mkdir(parents=True, mode=0o700)
        in_board = _receipt(
            {
                "schema_version": IN_BOARD_READBACK_SCHEMA,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                "success": True,
                "location": urljoin(manifest["app_url"], "panel.html"),
                "title": "Schauwerk Companion",
                "ready_state": "complete",
                "miro_present": True,
                "board_api_present": True,
                "dom": board["dom"],
                "sdk": board["sdk"],
                "sdk_error": None,
                "binding": {
                    "app_url": manifest["app_url"],
                    "developer_app_label": manifest["developer_app_label"],
                    "developer_app_id_sha256": board["app_id_sha256"],
                    "team_label": config.expected_team_label,
                    "required_scopes": manifest["required_scopes"],
                    "build_digest": manifest["build_digest"],
                    "release_digest": manifest["release_digest"],
                },
                "checks": board["checks"],
                "target": {
                    "type": "iframe",
                    "url_sha256": _sha256(urljoin(manifest["app_url"], "panel.html").encode()),
                },
                "does_not_establish": [
                    "future provider availability after expires_at",
                    "a board mutation or mutation approval",
                    "reuse permission for any OAuth or REST token",
                ],
            }
        )
        in_board_path = generation_root / "in-board.json"
        _write_create_only(in_board_path, _pretty(in_board))
        in_board_payload = in_board_path.read_bytes()
        app_config = _receipt(
            {
                "schema_version": APP_CONFIG_READBACK_SCHEMA,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                "success": True,
                "app_url": manifest["app_url"],
                "developer_app_label": manifest["developer_app_label"],
                "developer_app_id_sha256": board["app_id_sha256"],
                "team_label": config.expected_team_label,
                "required_scopes": manifest["required_scopes"],
                "checked_scopes": app["checked_scopes"],
                "disabled_scopes": app["disabled_scopes"],
                "dashboard": {
                    "authenticated": True,
                    "app_label_present": True,
                    "team_present": True,
                    "page_url_sha256": _sha256(config.app_settings_url.encode()),
                },
                "in_board_binding": {
                    "artifact_sha256": _sha256(in_board_payload),
                    "receipt_digest": in_board["receipt_digest"],
                    "success": True,
                    "build_digest": manifest["build_digest"],
                    "release_digest": manifest["release_digest"],
                },
                "gates": {
                    "developer_app_registered": "verified",
                    "team_installation": "verified",
                    "oauth_authorized": "verified",
                },
                "checks": {**app["checks"], "in_board_readback_success": True},
                "does_not_establish": [
                    "future provider state after expires_at",
                    "permission to reveal or reuse any token",
                    "permission for an unreviewed board mutation",
                ],
            }
        )
        app_path = generation_root / "app-config.json"
        _write_create_only(app_path, _pretty(app_config))
        gate = companion_gate_status(
            manifest_path=config.manifest_path,
            app_config_readback=app_path,
            in_board_readback=in_board_path,
            timeout=timeout,
            fetcher=fetcher,
            now=observed_at,
        )
        gate_path = generation_root / "gate-status.json"
        _write_create_only(gate_path, _pretty(gate))
        previous = current.get("generation_id") if current else None
        generation = _receipt(
            {
                "schema_version": GENERATION_SCHEMA,
                "generation_id": generation_id,
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                "release_digest": manifest["release_digest"],
                "config_sha256": _sha256(config.path.read_bytes()),
                "supersedes_generation": previous,
                "retention": "retain_all_immutable_generations",
                "mutation_attempted": False,
                "artifacts": {
                    "app_config": {
                        "file": "app-config.json",
                        "sha256": _sha256(app_path.read_bytes()),
                    },
                    "in_board": {
                        "file": "in-board.json",
                        "sha256": _sha256(in_board_path.read_bytes()),
                    },
                    "gate_status": {
                        "file": "gate-status.json",
                        "sha256": _sha256(gate_path.read_bytes()),
                    },
                },
                "does_not_establish": [
                    "future provider truth after expires_at",
                    "permission for provider mutation",
                ],
            }
        )
        generation_path = generation_root / "generation.json"
        _write_create_only(generation_path, _pretty(generation))
        current_value = _receipt(
            {
                "schema_version": CURRENT_SCHEMA,
                "generation_id": generation_id,
                "observed_at": generation["observed_at"],
                "expires_at": generation["expires_at"],
                "release_digest": manifest["release_digest"],
                "generation_receipt_digest": generation["receipt_digest"],
                "generation_manifest_sha256": _sha256(generation_path.read_bytes()),
                "previous_generation": previous,
            }
        )
        _write_atomic(config.state_root / "current.json", _pretty(current_value))
        return {
            "schema_version": GENERATION_SCHEMA,
            "status": gate["status"],
            "refresh": "completed",
            "generation_id": generation_id,
            "observed_at": generation["observed_at"],
            "expires_at": generation["expires_at"],
            "release_digest": manifest["release_digest"],
            "gate_digest": gate["gate_digest"],
            "generation_receipt_digest": generation["receipt_digest"],
            "current_pointer_digest": current_value["receipt_digest"],
            "mutation_attempted": False,
        }


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def install_evidence_timer(
    path: str | Path,
    *,
    cli_executable: str | Path | None = None,
    interval_hours: float = 6,
    randomized_delay_minutes: int = 15,
    enable: bool = False,
    replace: bool = False,
) -> dict[str, Any]:
    config = load_evidence_config(path)
    interval = _positive_number(interval_hours, "interval_hours", minimum=1, maximum=168)
    if not isinstance(randomized_delay_minutes, int) or not 0 <= randomized_delay_minutes <= 120:
        raise CompanionEvidenceError("randomized_delay_minutes must be an integer from 0 to 120")
    executable = Path(cli_executable or shutil.which("schauwerk") or "").expanduser().absolute()
    executable = _safe_regular(executable, "Schauwerk CLI")
    if not os.access(executable, os.X_OK):
        raise CompanionEvidenceError("Schauwerk CLI is not executable")
    unit_root = Path.home() / ".config/systemd/user"
    unit_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    service_path = unit_root / "schauwerk-companion-evidence-refresh.service"
    timer_path = unit_root / "schauwerk-companion-evidence-refresh.timer"
    service = f"""[Unit]\nDescription=Refresh bounded Schauwerk Miro companion evidence\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\nUMask=0077\nTimeoutStartSec=5min\nTimeoutStopSec=10s\nKillMode=control-group\nExecStart={_systemd_quote(str(executable))} miro companion evidence-capture {_systemd_quote(str(config.path))} --json\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=read-only\nReadWritePaths={_systemd_quote(str(config.state_root))} {_systemd_quote(str(config.browser_profile))}\n\n"""
    timer = f"""[Unit]\nDescription=Schedule bounded Schauwerk Miro companion evidence refresh\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec={interval:g}h\nRandomizedDelaySec={randomized_delay_minutes}min\nPersistent=true\nUnit=schauwerk-companion-evidence-refresh.service\n\n[Install]\nWantedBy=timers.target\n"""
    changed: list[str] = []
    for target, content in ((service_path, service), (timer_path, timer)):
        payload = content.encode()
        if target.exists():
            observed = _safe_regular(target, target.name, private=True).read_bytes()
            if observed == payload:
                continue
            if not replace:
                raise CompanionEvidenceError(f"{target.name} already exists with different content")
            _write_atomic(target, payload)
        else:
            _write_create_only(target, payload)
        changed.append(target.name)
    commands: list[list[str]] = []
    if enable:
        commands = [
            ["systemctl", "--user", "daemon-reload"],
            [
                "systemctl",
                "--user",
                "enable",
                "--now",
                "schauwerk-companion-evidence-refresh.timer",
            ],
        ]
        for command in commands:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
            if completed.returncode != 0:
                raise CompanionEvidenceError(f"systemd command failed: {command[-1]}")
    value = _receipt(
        {
            "schema_version": TIMER_INSTALL_SCHEMA,
            "success": True,
            "changed_units": changed,
            "enabled": enable,
            "service_path": str(service_path),
            "timer_path": str(timer_path),
            "service_sha256": _sha256(service.encode()),
            "timer_sha256": _sha256(timer.encode()),
            "config_sha256": _sha256(config.path.read_bytes()),
            "cli_sha256": _sha256(executable.read_bytes()),
            "interval_seconds": int(interval * 3600),
            "randomized_delay_seconds": randomized_delay_minutes * 60,
            "commands_sha256": _sha256(_canonical(commands)),
            "does_not_establish": [
                "future provider authentication",
                "automatic interactive reauthorization",
                "successful future timer executions",
            ],
        }
    )
    return value
