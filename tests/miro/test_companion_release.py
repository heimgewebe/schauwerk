from __future__ import annotations

import hashlib
import io
import json
import stat
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

import schauwerk.cli_handlers as cli_handlers
import schauwerk.surfaces.miro.companion_release as companion_release
from schauwerk.runner import main
from schauwerk.surfaces.miro.companion_release import (
    CompanionReleaseError,
    FetchResult,
    check_release_manifest,
    companion_gate_status,
    create_release_manifest,
    doctor_release,
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
    result = create_release_manifest(
        bundle_dir=bundle,
        app_url="https://example.test/miro-companion",
        developer_app_label="Schauwerk Companion Test",
        output=manifest_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["success"] is True
    return bundle, manifest_path, manifest


def test_release_manifest_is_create_only_private_and_keeps_external_gates_open(
    tmp_path: Path,
) -> None:
    bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)

    assert manifest["app_url"] == "https://example.test/miro-companion/"
    assert manifest["required_scopes"] == ["boards:read"]
    assert manifest["external_gates"] == {
        "public_https_hosting": "unknown",
        "developer_app_registered": "unknown",
        "team_installation": "unknown",
        "oauth_authorized": "unknown",
    }
    assert manifest["credential_boundaries"]["mcp_oauth_reused"] is False
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert check_release_manifest(manifest_path=manifest_path, bundle_dir=bundle)["success"]
    with pytest.raises(CompanionReleaseError, match="already exists"):
        create_release_manifest(
            bundle_dir=bundle,
            app_url="https://example.test/miro-companion/",
            developer_app_label="Schauwerk Companion Test",
            output=manifest_path,
        )


def test_release_manifest_rejects_insecure_or_ambiguous_urls(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=bundle)
    for url in (
        "http://example.test/app/",
        "https://user@example.test/app/",
        "https://example.test/app/?token=secret",
        "https://example.test:444/app/",
        "https://localhost/app/",
        "https://127.0.0.1/app/",
        "https://192.168.1.2/app/",
        "https://[::1]/app/",
    ):
        with pytest.raises(CompanionReleaseError):
            create_release_manifest(
                bundle_dir=bundle,
                app_url=url,
                developer_app_label="Schauwerk Companion Test",
                output=tmp_path / f"release-{len(url)}.json",
            )


def test_https_doctor_binds_content_types_headers_and_digests(tmp_path: Path) -> None:
    bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)

    def fetch(url: str, timeout: float) -> FetchResult:
        assert timeout == 5.0
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

    result = doctor_release(manifest_path=manifest_path, timeout=5.0, fetcher=fetch)
    assert result["success"] is True
    assert len(result["checked_files"]) == len(manifest["files"])
    assert result["external_gates"]["public_https_hosting"] == "verified"
    assert result["external_gates"]["developer_app_registered"] == "unknown"


def test_https_doctor_fails_closed_on_redirect_header_and_digest_drift(tmp_path: Path) -> None:
    bundle, manifest_path, _manifest = _bundle_and_manifest(tmp_path)

    def fetch(url: str, _timeout: float) -> FetchResult:
        name = url.rsplit("/", 1)[-1]
        headers = {"content-type": "application/javascript"}
        if name.endswith(".html"):
            headers = {"content-type": "text/html"}
        body = (bundle / name).read_bytes()
        if name == "app.js":
            body += b"tampered"
        return FetchResult(
            status=200,
            requested_url=url,
            final_url=("https://other.test/app.js" if name == "app.js" else url),
            headers=headers,
            body=body,
        )

    result = doctor_release(manifest_path=manifest_path, fetcher=fetch)
    assert result["success"] is False
    assert result["external_gates"]["public_https_hosting"] == "blocked"
    assert any("cross-origin redirect" in failure for failure in result["failures"])
    assert any("content digest mismatch" in failure for failure in result["failures"])
    assert any("content-security-policy" in failure for failure in result["failures"])


def test_default_fetch_does_not_follow_redirect_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class RedirectOpener:
        def open(self, request: object, timeout: float) -> object:
            assert timeout == 2.0
            url = request.full_url
            calls.append(url)
            headers = Message()
            headers["Location"] = "https://other.test/redirected.js"
            raise urllib.error.HTTPError(
                url,
                302,
                "Found",
                headers,
                io.BytesIO(b"redirect response"),
            )

    monkeypatch.setattr(
        companion_release.urllib.request,
        "build_opener",
        lambda *_handlers: RedirectOpener(),
    )

    result = companion_release._default_fetch(
        "https://example.test/app/app.js",
        2.0,
    )

    assert calls == ["https://example.test/app/app.js"]
    assert result.status == 302
    assert result.final_url == "https://other.test/redirected.js"
    assert result.body == b"redirect response"


def test_release_manifest_rejects_rewritten_security_contract(tmp_path: Path) -> None:
    _bundle, manifest_path, manifest = _bundle_and_manifest(tmp_path)
    manifest["required_html_headers"]["content-security-policy"] = ["default-src *"]
    unsigned = dict(manifest)
    unsigned.pop("release_digest")
    payload = (json.dumps(unsigned, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    manifest["release_digest"] = hashlib.sha256(payload).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CompanionReleaseError, match="security-header contract"):
        check_release_manifest(manifest_path=manifest_path)


def test_release_doctor_cli_returns_error_on_failed_remote_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _bundle, manifest_path, _manifest = _bundle_and_manifest(tmp_path)
    monkeypatch.setattr(
        cli_handlers,
        "doctor_release",
        lambda **_kwargs: {
            "success": False,
            "failures": ["index.html: unexpected redirect"],
        },
    )

    assert (
        main(
            [
                "miro",
                "companion",
                "release-doctor",
                str(manifest_path),
                "--json",
            ]
        )
        == 2
    )
    assert "companion HTTPS doctor failed" in capsys.readouterr().err


def test_public_and_packaged_release_schema_are_identical() -> None:
    public = ROOT / "schemas/miro-web-sdk-companion-release.v1.schema.json"
    packaged = ROOT / "src/schauwerk/schemas/miro-web-sdk-companion-release.v1.schema.json"
    assert public.read_bytes() == packaged.read_bytes()


def test_companion_release_cli_create_and_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=bundle)
    manifest = tmp_path / "release.json"
    assert (
        main(
            [
                "miro",
                "companion",
                "release-create",
                str(bundle),
                "--app-url",
                "https://example.test/miro-companion/",
                "--developer-app-label",
                "Schauwerk Companion Test",
                "--output",
                str(manifest),
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["external_gates"]["developer_app_registered"] == "unknown"
    assert (
        main(
            [
                "miro",
                "companion",
                "release-check",
                str(manifest),
                "--bundle-dir",
                str(bundle),
                "--json",
            ]
        )
        == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["success"] is True


def test_companion_gate_status_is_deterministic_and_cli_visible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = companion_gate_status()
    second = companion_gate_status()

    assert first == second
    assert first["status"] == "open"
    assert first["gates"]["public_https_hosting"]["state"] == "not_evidenced"
    assert first["gates"]["developer_app_registered"]["state"] == "not_evidenced"
    assert first["credential_boundaries"]["mcp_oauth_is_web_sdk_authorization"] is False
    assert first["credential_boundaries"]["rest_credential_is_web_sdk_authorization"] is False
    assert first["hosting_requirements"]["github_pages_satisfies_header_contract"] is False
    assert len(first["gate_digest"]) == 64

    assert main(["miro", "companion", "gate-status", "--json"]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == first
