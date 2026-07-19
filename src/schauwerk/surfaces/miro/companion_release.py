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
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .web_sdk_companion import MIRO_STATIC_SCRIPT_SOURCE, verify_companion

RELEASE_SCHEMA = "schauwerk-miro-web-sdk-companion-release.v1"
GATE_STATUS_SCHEMA = "schauwerk-miro-web-sdk-companion-gate-status.v1"
RELEASE_SCHEMA_FILE = "miro-web-sdk-companion-release.v1.schema.json"
MAX_HTTP_BYTES = 8 * 1024 * 1024
DEPLOYED_FILES = (
    "index.html",
    "panel.html",
    "app.js",
    "panel.js",
    "core.js",
    "styles.css",
    "config.json",
    "build-receipt.json",
)
CONTENT_TYPES = {
    ".html": ("text/html",),
    ".js": ("application/javascript", "text/javascript"),
    ".css": ("text/css",),
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


def companion_gate_status() -> dict[str, Any]:
    """Report the external Web SDK gates without inferring provider state."""

    value: dict[str, Any] = {
        "schema_version": GATE_STATUS_SCHEMA,
        "status": "open",
        "gates": {
            "public_https_hosting": {
                "state": "not_evidenced",
                "required_evidence": (
                    "successful companion release-doctor receipt bound to the exact release digest"
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
                    "interactive Web SDK app authorization and authenticated in-board readback"
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
            "select an HTTPS host that preserves the required CSP and frame headers, deploy the "
            "exact bundle, run release-doctor, then register and install the Miro Developer App"
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
