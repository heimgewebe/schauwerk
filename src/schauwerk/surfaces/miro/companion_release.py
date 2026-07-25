"""Receipt-bound release and HTTPS verification for the Miro Web SDK companion."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import stat
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .web_sdk_companion import MIRO_STATIC_SCRIPT_SOURCE, verify_companion

RELEASE_SCHEMA = "schauwerk-miro-web-sdk-companion-release.v1"
GATE_STATUS_SCHEMA = "schauwerk-miro-web-sdk-companion-gate-status.v1"
APP_CONFIG_READBACK_SCHEMA = "schauwerk-miro-web-sdk-app-config-readback.v1"
IN_BOARD_READBACK_SCHEMA = "schauwerk-miro-web-sdk-provider-readback.v1"
EVIDENCE_MAX_LIFETIME = timedelta(hours=48)
IN_BOARD_REQUIRED_CHECKS = frozenset(
    {
        "board_id_present",
        "build_digest_exact",
        "error_message_absent",
        "frame_readback_complete",
        "miro_live",
        "panel_public_origin",
        "read_api_available",
        "ready",
        "sdk_error_absent",
        "state_verified",
        "write_api_available",
    }
)
APP_CONFIG_REQUIRED_CHECKS = frozenset(
    {
        "app_label_present",
        "app_url_exact",
        "dashboard_authenticated",
        "in_board_readback_success",
        "no_scope_disabled",
        "scopes_exact",
        "team_present",
    }
)
RELEASE_SCHEMA_FILE = "miro-web-sdk-companion-release.v1.schema.json"
MAX_HTTP_BYTES = 8 * 1024 * 1024
DEPLOYED_FILES = (
    "index.html",
    "panel.html",
    "app.js",
    "panel.js",
    "core.js",
    "styles.css",
    "app-icon-outline.svg",
    "app-icon-color.svg",
    "config.json",
    "build-receipt.json",
)
CONTENT_TYPES = {
    ".html": ("text/html",),
    ".js": ("application/javascript", "text/javascript"),
    ".css": ("text/css",),
    ".svg": ("image/svg+xml",),
    ".json": ("application/json",),
}
REQUIRED_HTML_HEADERS = {
    "permissions-policy": ("camera=()", "microphone=()", "geolocation=()"),
    "referrer-policy": ("no-referrer",),
    "x-content-type-options": ("nosniff",),
    "content-security-policy": (
        "default-src 'self'",
        MIRO_STATIC_SCRIPT_SOURCE,
        "frame-ancestors https://miro.com https://*.miro.com",
    ),
}


class CompanionReleaseError(ValueError):
    """The companion release input, manifest, or deployed surface is invalid."""


@dataclass(frozen=True)
class FetchResult:
    status: int
    requested_url: str
    final_url: str
    headers: Mapping[str, str]
    body: bytes


Fetcher = Callable[[str, float], FetchResult]


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_regular_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise CompanionReleaseError(f"{label} path is unsafe")
    try:
        info = candidate.stat()
    except FileNotFoundError as exc:
        raise CompanionReleaseError(f"{label} is missing") from exc
    if not stat.S_ISREG(info.st_mode):
        raise CompanionReleaseError(f"{label} must be a regular file")
    if info.st_nlink != 1:
        raise CompanionReleaseError(f"{label} must not have hard links")
    return candidate


def _write_create_only(path: str | Path, payload: bytes) -> Path:
    target = Path(path).expanduser().absolute()
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise CompanionReleaseError("release output path is unsafe")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise CompanionReleaseError("release output parent is unsafe")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise CompanionReleaseError("release output already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def _normalize_app_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CompanionReleaseError("app URL must use HTTPS with a hostname")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CompanionReleaseError("app URL must not contain credentials, query, or fragment")
    if parsed.port not in (None, 443):
        raise CompanionReleaseError("app URL must use the default HTTPS port")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise CompanionReleaseError("app URL must use a public hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise CompanionReleaseError("app URL must not use a local or private IP address")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def _validate_app_label(value: str) -> str:
    label = value.strip()
    if not 3 <= len(label) <= 120 or any(character in label for character in "\r\n\t"):
        raise CompanionReleaseError("developer app label must contain 3 to 120 plain characters")
    return label


def _read_build_receipt(bundle_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(bundle_dir).expanduser().absolute()
    verify_companion(output_dir=root)
    receipt_path = _safe_regular_file(root / "build-receipt.json", "build receipt")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionReleaseError("build receipt must be UTF-8 JSON") from exc
    return root, receipt


def create_release_manifest(
    *,
    bundle_dir: str | Path,
    app_url: str,
    developer_app_label: str,
    output: str | Path,
) -> dict[str, Any]:
    root, build_receipt = _read_build_receipt(bundle_dir)
    normalized_url = _normalize_app_url(app_url)
    label = _validate_app_label(developer_app_label)

    build_files = build_receipt.get("files")
    if not isinstance(build_files, Mapping):
        raise CompanionReleaseError("build receipt file inventory is invalid")
    files: dict[str, str] = {}
    for name in DEPLOYED_FILES:
        source = _safe_regular_file(root / name, name)
        observed = _digest(source.read_bytes())
        expected = (
            build_receipt.get("build_digest")
            if name == "build-receipt.json"
            else build_files.get(name)
        )
        if name == "build-receipt.json":
            expected = observed
        if expected != observed:
            raise CompanionReleaseError(f"bundle digest mismatch: {name}")
        files[name] = observed

    manifest: dict[str, Any] = {
        "schema_version": RELEASE_SCHEMA,
        "app_url": normalized_url,
        "developer_app_label": label,
        "build_digest": build_receipt["build_digest"],
        "required_scopes": list(build_receipt["required_scopes"]),
        "files": files,
        "required_html_headers": {
            name: list(values) for name, values in REQUIRED_HTML_HEADERS.items()
        },
        "external_gates": {
            "public_https_hosting": "unknown",
            "developer_app_registered": "unknown",
            "team_installation": "unknown",
            "oauth_authorized": "unknown",
        },
        "credential_boundaries": {
            "mcp_oauth_reused": False,
            "rest_credential_included": False,
            "web_sdk_token_included": False,
        },
        "does_not_establish": [
            "public availability before HTTPS doctor success",
            "Miro Developer App registration",
            "installation into a Miro team",
            "OAuth consent or current user authorization",
            "MCP or REST authorization",
        ],
    }
    unsigned = dict(manifest)
    manifest["release_digest"] = _digest(_canonical(unsigned))
    destination = _write_create_only(output, _canonical(manifest))
    result = check_release_manifest(manifest_path=destination, bundle_dir=root)
    result["output"] = str(destination)
    return result


def _load_manifest(path: str | Path) -> dict[str, Any]:
    source = _safe_regular_file(path, "release manifest")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionReleaseError("release manifest must be UTF-8 JSON") from exc
    from importlib import resources

    schema_resource = resources.files("schauwerk.schemas").joinpath(RELEASE_SCHEMA_FILE)
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        raise CompanionReleaseError(f"invalid release manifest at {location}: {error.message}")
    unsigned = dict(value)
    observed_digest = unsigned.pop("release_digest")
    if observed_digest != _digest(_canonical(unsigned)):
        raise CompanionReleaseError("release digest does not match")
    if _normalize_app_url(value["app_url"]) != value["app_url"]:
        raise CompanionReleaseError("release app URL is not normalized")
    if _validate_app_label(value["developer_app_label"]) != value["developer_app_label"]:
        raise CompanionReleaseError("release developer-app label is not normalized")
    expected_headers = {
        name: list(tokens) for name, tokens in sorted(REQUIRED_HTML_HEADERS.items())
    }
    if value["required_html_headers"] != expected_headers:
        raise CompanionReleaseError("release security-header contract does not match")
    return value


def check_release_manifest(
    *, manifest_path: str | Path, bundle_dir: str | Path | None = None
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    if bundle_dir is not None:
        root, build_receipt = _read_build_receipt(bundle_dir)
        if build_receipt["build_digest"] != manifest["build_digest"]:
            raise CompanionReleaseError("release build digest does not match bundle")
        for name, expected in manifest["files"].items():
            observed = _digest(_safe_regular_file(root / name, name).read_bytes())
            if observed != expected:
                raise CompanionReleaseError(f"release bundle digest mismatch: {name}")
    return {
        "schema_version": RELEASE_SCHEMA,
        "success": True,
        "app_url": manifest["app_url"],
        "developer_app_label": manifest["developer_app_label"],
        "build_digest": manifest["build_digest"],
        "release_digest": manifest["release_digest"],
        "required_scopes": manifest["required_scopes"],
        "file_count": len(manifest["files"]),
        "external_gates": manifest["external_gates"],
        "credential_boundaries": manifest["credential_boundaries"],
        "does_not_establish": manifest["does_not_establish"],
    }


def _evidence_canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _parse_evidence_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise CompanionReleaseError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CompanionReleaseError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CompanionReleaseError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _load_gate_evidence(
    *,
    path: str | Path,
    label: str,
    expected_schema: str,
    required_checks: frozenset[str],
    now: datetime,
) -> tuple[dict[str, Any], str]:
    source = _safe_regular_file(path, label)
    payload = source.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionReleaseError(f"{label} must be UTF-8 JSON") from exc
    if not isinstance(value, dict) or value.get("schema_version") != expected_schema:
        raise CompanionReleaseError(f"{label} schema version does not match")
    observed_digest = value.get("receipt_digest")
    if not isinstance(observed_digest, str):
        raise CompanionReleaseError(f"{label} receipt digest is missing")
    unsigned = dict(value)
    unsigned.pop("receipt_digest")
    if observed_digest != _digest(_evidence_canonical(unsigned)):
        raise CompanionReleaseError(f"{label} receipt digest does not match")
    checks = value.get("checks")
    if (
        value.get("success") is not True
        or not isinstance(checks, Mapping)
        or not checks
        or any(result is not True for result in checks.values())
    ):
        raise CompanionReleaseError(f"{label} is not a successful complete readback")
    missing_checks = sorted(required_checks.difference(checks))
    if missing_checks:
        raise CompanionReleaseError(
            f"{label} is missing required checks: {', '.join(missing_checks)}"
        )
    observed_at = _parse_evidence_time(value.get("observed_at"), f"{label} observed_at")
    expires_at = _parse_evidence_time(value.get("expires_at"), f"{label} expires_at")
    if observed_at > expires_at:
        raise CompanionReleaseError(f"{label} expires before it was observed")
    if expires_at - observed_at > EVIDENCE_MAX_LIFETIME:
        raise CompanionReleaseError(f"{label} lifetime exceeds the allowed maximum")
    if observed_at > now + timedelta(minutes=5):
        raise CompanionReleaseError(f"{label} observation is implausibly in the future")
    if expires_at <= now:
        raise CompanionReleaseError(f"{label} has expired")
    return value, _digest(payload)


def _open_gate_status() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": GATE_STATUS_SCHEMA,
        "status": "open",
        "gates": {
            "public_https_hosting": {
                "state": "not_evidenced",
                "required_evidence": (
                    "successful live companion release doctor bound to the exact release digest"
                ),
            },
            "developer_app_registered": {
                "state": "not_evidenced",
                "required_evidence": (
                    "Miro Developer App readback bound to the exact HTTPS app URL and app label"
                ),
            },
            "team_installation": {
                "state": "not_evidenced",
                "required_evidence": "Miro team installation readback for the registered app",
            },
            "oauth_authorized": {
                "state": "not_evidenced",
                "required_evidence": (
                    "interactive Web SDK authorization and authenticated in-board readback"
                ),
            },
        },
        "credential_boundaries": {
            "mcp_oauth_is_web_sdk_authorization": False,
            "rest_credential_is_web_sdk_authorization": False,
            "web_sdk_app_identity_configured_by_repository": False,
        },
        "hosting_requirements": {
            "https": True,
            "exact_asset_digests": True,
            "custom_security_headers": True,
            "miro_frame_ancestors": True,
            "github_pages_satisfies_header_contract": False,
        },
        "next_action": (
            "provide the exact release manifest, Developer App readback and authenticated "
            "in-board readback to evaluate the live gates"
        ),
        "does_not_establish": [
            "absence of an externally created Miro Developer App",
            "absence of a deployment outside Schauwerk-managed evidence",
            "permission to reuse MCP OAuth or REST credentials",
            "provider authorization or installation state",
        ],
    }
    value["gate_digest"] = _digest(_canonical(value))
    return value


def companion_gate_status(
    *,
    manifest_path: str | Path | None = None,
    app_config_readback: str | Path | None = None,
    in_board_readback: str | Path | None = None,
    timeout: float = 10.0,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate external Web SDK gates only from explicit, fresh, bound evidence."""

    supplied = (manifest_path, app_config_readback, in_board_readback)
    if all(value is None for value in supplied):
        return _open_gate_status()
    if any(value is None for value in supplied):
        raise CompanionReleaseError(
            "gate evidence requires manifest, app-config readback and in-board readback together"
        )

    effective_now = (now or datetime.now(UTC)).astimezone(UTC)
    manifest = _load_manifest(manifest_path)
    in_board, in_board_sha256 = _load_gate_evidence(
        path=in_board_readback,
        label="in-board readback",
        expected_schema=IN_BOARD_READBACK_SCHEMA,
        required_checks=IN_BOARD_REQUIRED_CHECKS,
        now=effective_now,
    )
    app_config, app_config_sha256 = _load_gate_evidence(
        path=app_config_readback,
        label="app-config readback",
        expected_schema=APP_CONFIG_READBACK_SCHEMA,
        required_checks=APP_CONFIG_REQUIRED_CHECKS,
        now=effective_now,
    )

    binding = in_board.get("binding")
    if not isinstance(binding, Mapping):
        raise CompanionReleaseError("in-board readback binding is missing")
    expected_binding = {
        "app_url": manifest["app_url"],
        "build_digest": manifest["build_digest"],
        "developer_app_label": manifest["developer_app_label"],
        "release_digest": manifest["release_digest"],
        "required_scopes": manifest["required_scopes"],
    }
    for key, expected in expected_binding.items():
        if binding.get(key) != expected:
            raise CompanionReleaseError(f"in-board readback {key} does not match release")
    expected_panel_url = urljoin(manifest["app_url"], "panel.html")
    if in_board.get("location") != expected_panel_url:
        raise CompanionReleaseError("in-board panel origin does not match release")

    if app_config.get("app_url") != manifest["app_url"]:
        raise CompanionReleaseError("Developer App URL does not match release")
    if app_config.get("developer_app_label") != manifest["developer_app_label"]:
        raise CompanionReleaseError("Developer App label does not match release")
    if app_config.get("required_scopes") != manifest["required_scopes"]:
        raise CompanionReleaseError("Developer App required scopes do not match release")
    if app_config.get("checked_scopes") != manifest["required_scopes"]:
        raise CompanionReleaseError("Developer App checked scopes do not match release")
    if app_config.get("disabled_scopes") != []:
        raise CompanionReleaseError("Developer App reports disabled scopes")
    if app_config.get("developer_app_id_sha256") != binding.get(
        "developer_app_id_sha256"
    ):
        raise CompanionReleaseError("Developer App identity differs between readbacks")
    if app_config.get("team_label") != binding.get("team_label"):
        raise CompanionReleaseError("Miro team differs between readbacks")
    gates = app_config.get("gates")
    if gates != {
        "developer_app_registered": "verified",
        "oauth_authorized": "verified",
        "team_installation": "verified",
    }:
        raise CompanionReleaseError("Developer App gate claims are incomplete")
    board_binding = app_config.get("in_board_binding")
    if not isinstance(board_binding, Mapping):
        raise CompanionReleaseError("app-config readback lacks its in-board binding")
    if board_binding.get("artifact_sha256") != in_board_sha256:
        raise CompanionReleaseError("app-config readback is not bound to this in-board artifact")
    if board_binding.get("receipt_digest") != in_board.get("receipt_digest"):
        raise CompanionReleaseError("app-config readback is not bound to this in-board receipt")
    for key in ("build_digest", "release_digest"):
        if board_binding.get(key) != expected_binding[key]:
            raise CompanionReleaseError(f"app-config in-board {key} does not match release")

    doctor = doctor_release(
        manifest_path=manifest_path,
        timeout=timeout,
        fetcher=fetcher,
    )
    public_ok = doctor.get("success") is True
    failures = list(doctor.get("failures") or [])
    value: dict[str, Any] = {
        "schema_version": GATE_STATUS_SCHEMA,
        "status": "closed" if public_ok else "blocked",
        "gates": {
            "public_https_hosting": {
                "state": "verified" if public_ok else "blocked",
                "required_evidence": (
                    "successful live companion release doctor bound to the exact release digest"
                ),
            },
            "developer_app_registered": {
                "state": "verified",
                "required_evidence": (
                    "Miro Developer App readback bound to the exact HTTPS app URL and app label"
                ),
            },
            "team_installation": {
                "state": "verified",
                "required_evidence": "Miro team installation readback for the registered app",
            },
            "oauth_authorized": {
                "state": "verified",
                "required_evidence": (
                    "interactive Web SDK authorization and authenticated in-board readback"
                ),
            },
        },
        "release": {
            "app_url": manifest["app_url"],
            "build_digest": manifest["build_digest"],
            "developer_app_label": manifest["developer_app_label"],
            "release_digest": manifest["release_digest"],
            "required_scopes": manifest["required_scopes"],
        },
        "evidence": {
            "app_config_readback": {
                "artifact_sha256": app_config_sha256,
                "expires_at": app_config["expires_at"],
                "observed_at": app_config["observed_at"],
                "receipt_digest": app_config["receipt_digest"],
            },
            "in_board_readback": {
                "artifact_sha256": in_board_sha256,
                "expires_at": in_board["expires_at"],
                "observed_at": in_board["observed_at"],
                "receipt_digest": in_board["receipt_digest"],
            },
            "live_doctor": {
                "checked_file_count": len(doctor.get("checked_files") or []),
                "release_digest": doctor.get("release_digest"),
                "success": public_ok,
            },
        },
        "credential_boundaries": {
            "mcp_oauth_is_web_sdk_authorization": False,
            "rest_credential_is_web_sdk_authorization": False,
            "web_sdk_app_identity_configured_by_repository": False,
        },
        "hosting_requirements": {
            "https": True,
            "exact_asset_digests": True,
            "custom_security_headers": True,
            "miro_frame_ancestors": True,
            "github_pages_satisfies_header_contract": False,
        },
        "next_action": (
            "refresh the explicit provider readbacks before expiry"
            if public_ok
            else "repair the public deployment and rerun the live release doctor"
        ),
        "failures": failures,
        "does_not_establish": [
            "future provider state after the evidence expiry",
            "permission to reveal or reuse OAuth or REST tokens",
            "permission for an unreviewed board mutation",
            "subjective visual quality beyond the authenticated readback",
        ],
    }
    value["gate_digest"] = _digest(_canonical(value))
    return value


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Expose redirects as responses without fetching their targets."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _default_fetch(url: str, timeout: float) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": "schauwerk-companion-doctor/1"})
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(MAX_HTTP_BYTES + 1)
            if len(body) > MAX_HTTP_BYTES:
                raise CompanionReleaseError("deployed asset exceeds the response limit")
            headers = {key.lower(): value.strip() for key, value in response.headers.items()}
            return FetchResult(
                status=int(response.status),
                requested_url=url,
                final_url=response.geturl(),
                headers=headers,
                body=body,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_HTTP_BYTES + 1)
        if len(body) > MAX_HTTP_BYTES:
            raise CompanionReleaseError(
                "deployed error response exceeds the response limit"
            ) from exc
        headers = {key.lower(): value.strip() for key, value in exc.headers.items()}
        location = exc.headers.get("Location")
        return FetchResult(
            status=int(exc.code),
            requested_url=url,
            final_url=urljoin(url, location) if location else exc.geturl(),
            headers=headers,
            body=body,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CompanionReleaseError(f"HTTPS request failed for {url}") from exc


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return parsed.scheme, parsed.hostname or "", parsed.port or 443


def doctor_release(
    *,
    manifest_path: str | Path,
    timeout: float = 10.0,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    if not 0.1 <= timeout <= 60:
        raise CompanionReleaseError("timeout must be between 0.1 and 60 seconds")
    manifest = _load_manifest(manifest_path)
    base_url = manifest["app_url"]
    fetch = fetcher or _default_fetch
    checked: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, expected_digest in manifest["files"].items():
        target = urljoin(base_url, name)
        try:
            response = fetch(target, timeout)
        except CompanionReleaseError as exc:
            failures.append(f"{name}: {exc}")
            continue
        if response.requested_url != target:
            failures.append(f"{name}: fetcher request binding mismatch")
        if response.status != 200:
            failures.append(f"{name}: HTTP status {response.status}")
        if response.final_url != target:
            redirect_kind = (
                "cross-origin redirect"
                if _origin(response.final_url) != _origin(target)
                else "redirect"
            )
            failures.append(f"{name}: unexpected {redirect_kind}")
        observed_digest = _digest(response.body)
        if observed_digest != expected_digest:
            failures.append(f"{name}: content digest mismatch")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        expected_types = CONTENT_TYPES[Path(name).suffix]
        if content_type not in expected_types:
            failures.append(f"{name}: content type {content_type or 'missing'}")
        if name.endswith(".html"):
            for header, fragments in REQUIRED_HTML_HEADERS.items():
                observed_header = response.headers.get(header, "").lower()
                for fragment in fragments:
                    if fragment.lower() not in observed_header:
                        failures.append(f"{name}: missing {header} fragment {fragment}")
        checked.append(
            {
                "name": name,
                "url_digest": _digest(target.encode("utf-8")),
                "status": response.status,
                "content_type": content_type,
                "sha256": observed_digest,
                "bytes": len(response.body),
            }
        )
    return {
        "schema_version": "schauwerk-miro-web-sdk-companion-doctor.v1",
        "success": not failures and len(checked) == len(manifest["files"]),
        "app_origin": urlsplit(base_url)._replace(path="", query="", fragment="").geturl(),
        "release_digest": manifest["release_digest"],
        "checked_files": checked,
        "failures": failures,
        "external_gates": {
            "public_https_hosting": "verified" if not failures else "blocked",
            "developer_app_registered": "unknown",
            "team_installation": "unknown",
            "oauth_authorized": "unknown",
        },
        "does_not_establish": [
            "Miro Developer App registration",
            "installation into a Miro team",
            "OAuth consent or current user authorization",
            "continued availability after the observation",
        ],
    }
