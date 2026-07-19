from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import schauwerk.surfaces.miro.web_sdk_companion as companion_module
from schauwerk.runner import main
from schauwerk.surfaces.miro.web_sdk_companion import (
    ASSETS,
    MIRO_SDK_URL,
    MIRO_STATIC_SCRIPT_SOURCE,
    CompanionBuildError,
    build_companion,
    load_companion_config,
    verify_companion,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/miro-web-sdk-companion-v1.json"
ASSET_ROOT = ROOT / "src/schauwerk/web_sdk_assets"


def test_build_is_deterministic_and_read_only(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_receipt = build_companion(input_path=FIXTURE, output_dir=first)
    second_receipt = build_companion(input_path=FIXTURE, output_dir=second)

    assert first_receipt["success"] is True
    assert first_receipt["required_scopes"] == ["boards:read"]
    assert first_receipt["security"]["board_write_authority"] is False
    assert first_receipt["security"]["rest_api_authority"] is False
    assert first_receipt["security"]["remote_javascript"] is True
    assert first_receipt["security"]["remote_javascript_origins"] == [
        MIRO_STATIC_SCRIPT_SOURCE
    ]
    assert first_receipt["build_digest"] == second_receipt["build_digest"]
    assert first_receipt["file_count"] == len(ASSETS) + 3
    for name in (*ASSETS, "config.json", "_headers", "build-receipt.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_assets_use_text_content_and_only_the_official_miro_remote_script() -> None:
    javascript = "\n".join(
        (ASSET_ROOT / name).read_text() for name in ("app.js", "panel.js", "core.js")
    )

    assert "innerHTML" not in javascript
    assert "eval(" not in javascript
    assert "new Function" not in javascript
    assert "https://" not in javascript
    assert "textContent" in javascript
    assert "selection:update" in javascript
    assert "viewport.zoomTo" in javascript
    assert "canOpenPanel" in javascript
    assert "isMiroEmbedded" in javascript
    assert "parent !== scope" in javascript
    assert "info?.updatedAt" in javascript
    assert "modifiedAt" not in javascript

    for name, module_name in (("index.html", "app.js"), ("panel.html", "panel.js")):
        html = (ASSET_ROOT / name).read_text()
        assert html.count(MIRO_SDK_URL) == 1
        assert html.index(MIRO_SDK_URL) < html.index(module_name)
        assert "http://" not in html
        external_scripts = [
            line.strip()
            for line in html.splitlines()
            if "<script" in line and "https://" in line
        ]
        assert external_scripts == [f'<script src="{MIRO_SDK_URL}"></script>']


def test_bundle_headers_and_receipt_are_fail_closed(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_companion(input_path=FIXTURE, output_dir=output)
    headers = (output / "_headers").read_text()
    assert "frame-ancestors https://miro.com https://*.miro.com" in headers
    assert f"script-src 'self' {MIRO_STATIC_SCRIPT_SOURCE};" in headers
    assert "script-src 'self' https://miro.com;" not in headers
    assert "object-src 'none'" in headers

    panel = output / "panel.js"
    panel.write_text(panel.read_text() + "\n// tampered\n")
    with pytest.raises(CompanionBuildError, match="digest mismatch"):
        verify_companion(output_dir=output)


def test_invalid_or_incomplete_verified_config_is_rejected(tmp_path: Path) -> None:
    value = json.loads(FIXTURE.read_text())
    value["status"]["completed_operation_count"] = 5
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(value))
    with pytest.raises(CompanionBuildError, match="complete positive evidence"):
        load_companion_config(invalid)


def test_output_must_be_new_and_input_must_not_be_symlink(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    with pytest.raises(CompanionBuildError, match="already exists"):
        build_companion(input_path=FIXTURE, output_dir=output)

    linked = tmp_path / "linked.json"
    linked.symlink_to(FIXTURE)
    with pytest.raises(CompanionBuildError, match="unsafe"):
        load_companion_config(linked)


def test_javascript_core_contract_with_node() -> None:
    completed = subprocess.run(
        [
            "node",
            "--test",
            str(ROOT / "tests/miro/web_sdk_companion_core.test.mjs"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "SCHAUWERK_CORE_JS": str(ASSET_ROOT / "core.js")},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_companion_cli_build_and_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "bundle"
    assert (
        main(["miro", "companion", "build", str(FIXTURE), "--output-dir", str(output), "--json"])
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert built["success"] is True

    assert main(["miro", "companion", "check", str(output), "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["build_digest"] == built["build_digest"]


def test_public_and_packaged_schemas_are_identical() -> None:
    public = ROOT / "schemas/miro-web-sdk-companion.v1.schema.json"
    packaged = ROOT / "src/schauwerk/schemas/miro-web-sdk-companion.v1.schema.json"
    assert public.read_bytes() == packaged.read_bytes()
    assert hashlib.sha256(public.read_bytes()).hexdigest() == (
        "3a7ef884a244e31b09717b1dc284e5b038df207f82a1c4981d670278e40924d9"
    )

def test_failed_build_leaves_no_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "bundle"
    original = companion_module._asset

    def broken_asset(name: str) -> bytes:
        if name == "panel.js":
            raise RuntimeError("synthetic asset failure")
        return original(name)

    monkeypatch.setattr(companion_module, "_asset", broken_asset)
    with pytest.raises(RuntimeError, match="synthetic asset failure"):
        build_companion(input_path=FIXTURE, output_dir=output)

    assert not output.exists()
    assert not list(tmp_path.glob(".bundle.*"))
