"""Build and verify the static Schauwerk Miro Web SDK companion."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ASSETS = (
    "index.html",
    "panel.html",
    "app.js",
    "panel.js",
    "core.js",
    "styles.css",
    "app-icon-outline.svg",
    "app-icon-color.svg",
)
BUILD_SCHEMA = "schauwerk-miro-web-sdk-companion-build.v1"
MIRO_SDK_URL = "https://miro.com/app/static/sdk/v2/miro.js"
MIRO_STATIC_SCRIPT_SOURCE = "https://miro.com/app/static/"
HEADERS = (
    "/*\n"
    "  Content-Security-Policy: default-src 'self'; script-src 'self' "
    f"{MIRO_STATIC_SCRIPT_SOURCE}; "
    "style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors https://miro.com "
    "https://*.miro.com\n"
    "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()\n"
    "  Referrer-Policy: no-referrer\n"
    "  X-Content-Type-Options: nosniff\n"
)


class CompanionBuildError(ValueError):
    """The companion input or output is unsafe or inconsistent."""


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _safe_file(path: Path, label: str) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise CompanionBuildError(f"{label} path is unsafe")
    if not candidate.is_file():
        raise CompanionBuildError(f"{label} must be a regular file")
    return candidate


def load_companion_config(path: str | Path) -> dict[str, Any]:
    source = _safe_file(Path(path), "configuration")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionBuildError("configuration must be UTF-8 JSON") from exc
    schema_file = resources.files("schauwerk.schemas").joinpath(
        "miro-web-sdk-companion.v1.schema.json"
    )
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        raise CompanionBuildError(f"invalid configuration at {location}: {error.message}")
    write_actions = value.get("write_actions") or {
        "enabled": False,
        "allowed": [],
        "require_confirmation": True,
        "allow_undo": False,
        "metadata_key": "schauwerk_action",
    }
    if write_actions["enabled"] and write_actions["allowed"] != ["create_review_card"]:
        raise CompanionBuildError("enabled write policy must allow exactly create_review_card")
    status = value["status"]
    if status["completed_operation_count"] > status["operation_count"]:
        raise CompanionBuildError("completed operation count exceeds operation count")
    if status["state"] == "verified" and (
        status["quality_score"] is None
        or status["quality_score"] < 1
        or status["completed_operation_count"] != status["operation_count"]
        or status["snapshot_digest"] is None
        or status["execution_digest"] is None
    ):
        raise CompanionBuildError("verified status requires complete positive evidence")
    return value


def _asset(name: str) -> bytes:
    return resources.files("schauwerk.web_sdk_assets").joinpath(name).read_bytes()


def _manifest(
    config: dict[str, Any], files: dict[str, str], *, source_config_sha256: str
) -> dict[str, Any]:
    write_actions = config.get("write_actions") or {
        "enabled": False,
        "allowed": [],
        "require_confirmation": True,
        "allow_undo": False,
        "metadata_key": "schauwerk_action",
    }
    required_scopes = ["boards:read"]
    if write_actions["enabled"]:
        required_scopes.append("boards:write")
    value: dict[str, Any] = {
        "schema_version": BUILD_SCHEMA,
        "app_name": config["app_name"],
        "entrypoint": "index.html",
        "panel": "panel.html",
        "required_scopes": required_scopes,
        "features": [
            "board_context",
            "selection_readback",
            "selection_update_event",
            "viewport_focus",
            "frame_navigation",
            "quality_receipt_summary",
            "board_inventory_summary",
            "frame_filter",
            "provider_creation_fallbacks",
            "confirmed_review_card_write",
            "session_owned_undo",
            "standalone_fallback",
        ],
        "files": dict(sorted(files.items())),
        "source_config_sha256": source_config_sha256,
        "security": {
            "remote_javascript": True,
            "remote_javascript_origins": [MIRO_STATIC_SCRIPT_SOURCE],
            "rest_api_authority": False,
            "board_write_authority": write_actions["enabled"],
            "board_write_policy": {
                "automatic_writes": False,
                "allowed_actions": write_actions["allowed"],
                "confirmation_required": write_actions["require_confirmation"],
                "session_owned_undo": write_actions["allow_undo"],
                "metadata_key": write_actions["metadata_key"],
            },
            "inline_html_rendering": False,
            "deployment_requires_https": True,
        },
        "does_not_establish": [
            "Miro developer-app registration",
            "installation into a Miro team",
            "live execution outside a registered HTTPS app",
            "REST API or MCP authorization",
            "permission for arbitrary, background, bulk, or cross-board mutations",
            "native provider item types when a declared layout fallback is used",
            "immutability or content integrity of the provider-hosted Miro Web SDK",
        ],
    }
    value["build_digest"] = _digest(_canonical(value))
    return value


def build_companion(*, input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = _safe_file(Path(input_path), "configuration")
    destination = Path(output_dir).expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise CompanionBuildError("output path is unsafe")
    if destination.exists():
        raise CompanionBuildError("output directory already exists")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise CompanionBuildError("output parent is unsafe")

    config = load_companion_config(source)
    source_digest = _digest(source.read_bytes())
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        files: dict[str, str] = {}
        for name in ASSETS:
            payload = _asset(name)
            (temporary / name).write_bytes(payload)
            files[name] = _digest(payload)
        config_payload = _canonical(config)
        (temporary / "config.json").write_bytes(config_payload)
        files["config.json"] = _digest(config_payload)
        headers = HEADERS.encode()
        (temporary / "_headers").write_bytes(headers)
        files["_headers"] = _digest(headers)
        receipt = _manifest(config, files, source_config_sha256=source_digest)
        (temporary / "build-receipt.json").write_bytes(_canonical(receipt))
        for child in temporary.iterdir():
            os.chmod(child, 0o644)
        os.chmod(temporary, 0o755)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return verify_companion(output_dir=destination)


def verify_companion(*, output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir).expanduser().absolute()
    if (
        root.is_symlink()
        or any(parent.is_symlink() for parent in root.parents)
        or not root.is_dir()
    ):
        raise CompanionBuildError("bundle directory is unsafe or missing")
    receipt_file = _safe_file(root / "build-receipt.json", "build receipt")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionBuildError("build receipt must be UTF-8 JSON") from exc
    if receipt.get("schema_version") != BUILD_SCHEMA:
        raise CompanionBuildError("unsupported build receipt")
    files = receipt.get("files")
    expected = {*ASSETS, "config.json", "_headers"}
    if not isinstance(files, dict) or set(files) != expected:
        raise CompanionBuildError("invalid file inventory")
    for name, expected_digest in files.items():
        observed = _digest(_safe_file(root / name, name).read_bytes())
        if observed != expected_digest:
            raise CompanionBuildError(f"asset digest mismatch: {name}")
    config = load_companion_config(root / "config.json")
    unsigned = dict(receipt)
    unsigned.pop("build_digest", None)
    if receipt.get("build_digest") != _digest(_canonical(unsigned)):
        raise CompanionBuildError("build digest does not match")
    allowed = {*files, "build-receipt.json"}
    unexpected = sorted(child.name for child in root.iterdir() if child.name not in allowed)
    if unexpected:
        raise CompanionBuildError(f"unexpected bundle files: {unexpected}")
    return {
        "schema_version": BUILD_SCHEMA,
        "success": True,
        "output_dir": str(root),
        "app_name": config["app_name"],
        "file_count": len(allowed),
        "build_digest": receipt["build_digest"],
        "source_config_sha256": receipt.get("source_config_sha256"),
        "required_scopes": receipt["required_scopes"],
        "features": receipt["features"],
        "security": receipt["security"],
        "does_not_establish": receipt["does_not_establish"],
    }
