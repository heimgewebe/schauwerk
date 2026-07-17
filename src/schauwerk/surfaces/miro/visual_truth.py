"""Bind an authenticated Miro provider capture to one exact sanitized board snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .board_registry import reference_digest, validate_alias, validate_board_url
from .snapshot_model import content_digest as snapshot_content_digest

CONTEXT_SCHEMA = "schauwerk-miro-visual-truth-context.v1"
RECEIPT_SCHEMA = "schauwerk-miro-visual-truth-receipt.v1"
CONTEXT_SCHEMA_FILE = "miro-visual-truth-context.v1.schema.json"
RECEIPT_SCHEMA_FILE = "miro-visual-truth-receipt.v1.schema.json"
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_CONTEXT_BYTES = 256 * 1024
MAX_CAPTURE_BYTES = 25 * 1024 * 1024
MAX_CAPTURE_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)
REJECTED_PAGE_MARKERS = (
    "sign in",
    "log in",
    "login",
    "access denied",
    "permission denied",
    "request access",
    "page not found",
    "something went wrong",
    "error",
)


class VisualTruthError(ValueError):
    """The visual-truth input or receipt is unsafe, ambiguous, or inconsistent."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_regular_file(path: str | Path, label: str, *, max_bytes: int) -> tuple[Path, bytes]:
    candidate = Path(path).expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise VisualTruthError(f"{label} path is unsafe")
    try:
        metadata = candidate.stat()
    except FileNotFoundError as exc:
        raise VisualTruthError(f"{label} is missing") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise VisualTruthError(f"{label} must be a regular file")
    if metadata.st_nlink != 1:
        raise VisualTruthError(f"{label} must not have hard links")
    if metadata.st_size < 1 or metadata.st_size > max_bytes:
        raise VisualTruthError(f"{label} size is outside the allowed range")
    return candidate, candidate.read_bytes()


def _load_json(
    path: str | Path, label: str, *, max_bytes: int, schema_file: str | None = None
) -> tuple[Path, bytes, dict[str, Any]]:
    source, payload = _safe_regular_file(path, label, max_bytes=max_bytes)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisualTruthError(f"{label} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise VisualTruthError(f"{label} must contain a JSON object")
    if schema_file is not None:
        schema = json.loads(
            resources.files("schauwerk.schemas").joinpath(schema_file).read_text(encoding="utf-8")
        )
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
            key=lambda error: list(error.path),
        )
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.path) or "root"
            raise VisualTruthError(f"invalid {label} at {location}: {error.message}")
    return source, payload, value


def load_visual_truth_context(path: str | Path) -> dict[str, Any]:
    return _load_json(
        path,
        "capture context",
        max_bytes=MAX_CONTEXT_BYTES,
        schema_file=CONTEXT_SCHEMA_FILE,
    )[2]


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VisualTruthError("capture timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise VisualTruthError("capture timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) < 24:
        return None
    if payload[12:16] != b"IHDR":
        raise VisualTruthError("PNG capture has no IHDR header")
    return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")


def _jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\xff\xd8"):
        return None
    position = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position + 4 <= len(payload):
        if payload[position] != 0xFF:
            position += 1
            continue
        while position < len(payload) and payload[position] == 0xFF:
            position += 1
        if position >= len(payload):
            break
        marker = payload[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(payload):
            break
        length = int.from_bytes(payload[position : position + 2], "big")
        if length < 2 or position + length > len(payload):
            raise VisualTruthError("JPEG capture has an invalid segment")
        if marker in sof_markers:
            if length < 7:
                raise VisualTruthError("JPEG capture has an invalid size segment")
            height = int.from_bytes(payload[position + 3 : position + 5], "big")
            width = int.from_bytes(payload[position + 5 : position + 7], "big")
            return width, height
        position += length
    raise VisualTruthError("JPEG capture has no supported size segment")


def _webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 20 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return None
    position = 12
    while position + 8 <= len(payload):
        kind = payload[position : position + 4]
        size = int.from_bytes(payload[position + 4 : position + 8], "little")
        start = position + 8
        end = start + size
        if end > len(payload):
            raise VisualTruthError("WebP capture has an invalid chunk")
        chunk = payload[start:end]
        if kind == b"VP8X" and len(chunk) >= 10:
            width = 1 + int.from_bytes(chunk[4:7], "little")
            height = 1 + int.from_bytes(chunk[7:10], "little")
            return width, height
        if kind == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
            bits = int.from_bytes(chunk[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if kind == b"VP8 ":
            marker = chunk.find(b"\x9d\x01\x2a")
            if marker >= 0 and marker + 7 <= len(chunk):
                width = int.from_bytes(chunk[marker + 3 : marker + 5], "little") & 0x3FFF
                height = int.from_bytes(chunk[marker + 5 : marker + 7], "little") & 0x3FFF
                return width, height
        position = end + (size & 1)
    raise VisualTruthError("WebP capture has no supported size chunk")


def _image_info(payload: bytes) -> tuple[str, int, int]:
    for media_type, parser in (
        ("image/png", _png_dimensions),
        ("image/jpeg", _jpeg_dimensions),
        ("image/webp", _webp_dimensions),
    ):
        dimensions = parser(payload)
        if dimensions is not None:
            width, height = dimensions
            if not 64 <= width <= 32768 or not 64 <= height <= 32768:
                raise VisualTruthError("capture dimensions are outside the allowed range")
            return media_type, width, height
    raise VisualTruthError("capture must be PNG, JPEG, or WebP")


def _write_create_only(path: str | Path, payload: bytes) -> Path:
    target = Path(path).expanduser().absolute()
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise VisualTruthError("receipt output path is unsafe")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise VisualTruthError("receipt output parent is unsafe")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise VisualTruthError("receipt output already exists") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def create_visual_truth_receipt(
    *,
    snapshot: str | Path,
    capture: str | Path,
    context: str | Path,
    expected_board_reference_digest: str,
    output: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshot_path, snapshot_payload, snapshot_value = _load_json(
        snapshot, "snapshot", max_bytes=MAX_SNAPSHOT_BYTES
    )
    context_path, context_payload, context_value = _load_json(
        context,
        "capture context",
        max_bytes=MAX_CONTEXT_BYTES,
        schema_file=CONTEXT_SCHEMA_FILE,
    )
    capture_path, capture_payload = _safe_regular_file(
        capture, "capture", max_bytes=MAX_CAPTURE_BYTES
    )
    media_type, width, height = _image_info(capture_payload)

    alias = validate_alias(context_value["board_alias"])
    if snapshot_value.get("board_alias") != alias:
        raise VisualTruthError("capture context board alias does not match snapshot")
    content_digest = snapshot_value.get("content_digest")
    if (
        not isinstance(content_digest, str)
        or len(content_digest) != 64
        or any(character not in "0123456789abcdef" for character in content_digest)
    ):
        raise VisualTruthError("snapshot content digest is missing or invalid")
    snapshot_content = {
        "schema_version": snapshot_value.get("schema_version"),
        "board_alias": snapshot_value.get("board_alias"),
        "items": snapshot_value.get("items"),
        "comments": snapshot_value.get("comments"),
    }
    if snapshot_content["schema_version"] != 1:
        raise VisualTruthError("snapshot schema version is unsupported")
    if not isinstance(snapshot_content["items"], list) or not isinstance(
        snapshot_content["comments"], list
    ):
        raise VisualTruthError("snapshot item or comment inventory is invalid")
    if snapshot_content_digest(snapshot_content) != content_digest:
        raise VisualTruthError("snapshot content digest does not match its content")
    if context_value["board_content_digest"] != content_digest:
        raise VisualTruthError("capture context content digest does not match snapshot")
    if snapshot_value.get("repeatability_verified") is not True:
        raise VisualTruthError("snapshot is not repeatability-verified")
    if snapshot_value.get("sanitized_references") is not True:
        raise VisualTruthError("snapshot references are not sanitized")
    if snapshot_value.get("verified_reads") != 2:
        raise VisualTruthError("snapshot must be based on exactly two verified reads")
    expected_reference = expected_board_reference_digest.strip().lower()
    if len(expected_reference) != 16 or any(
        character not in "0123456789abcdef" for character in expected_reference
    ):
        raise VisualTruthError("expected board reference digest is invalid")
    if context_value["board_reference_digest"] != expected_reference:
        raise VisualTruthError("capture context does not match the allowlisted board reference")

    provider_url = validate_board_url(context_value["provider_url"])
    if reference_digest(provider_url) != expected_reference:
        raise VisualTruthError("capture context provider URL does not match its board reference")
    page_text = " ".join(context_value["visible_board_markers"]).lower()
    rejected = sorted(marker for marker in REJECTED_PAGE_MARKERS if marker in page_text)
    if rejected:
        raise VisualTruthError(f"capture markers indicate a non-board page: {rejected[0]}")
    captured_at = _parse_timestamp(context_value["captured_at"])
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if captured_at > observed_now + MAX_FUTURE_SKEW:
        raise VisualTruthError("capture timestamp is too far in the future")
    if observed_now - captured_at > MAX_CAPTURE_AGE:
        raise VisualTruthError("capture is older than the allowed visual-truth window")

    provider_origin = urlsplit(provider_url)._replace(path="", query="", fragment="").geturl()
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "board_alias": alias,
        "board_reference_digest": expected_reference,
        "board_content_digest": content_digest,
        "snapshot": {
            "sha256": _digest(snapshot_payload),
            "bytes": len(snapshot_payload),
            "repeatability_verified": True,
            "sanitized_references": True,
            "verified_reads": 2,
        },
        "capture": {
            "sha256": _digest(capture_payload),
            "bytes": len(capture_payload),
            "media_type": media_type,
            "width": width,
            "height": height,
            "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        },
        "context": {
            "sha256": _digest(context_payload),
            "bytes": len(context_payload),
            "provider_origin": provider_origin,
            "provider_url_digest": _digest(provider_url.encode("utf-8")),
            "capture_tool": context_value["capture_tool"],
            "authentication": "operator_attested_authenticated_board",
            "attestation_sha256": _digest(context_value["operator_attestation"].encode("utf-8")),
        },
        "evidence_strength": {
            "provider_surface_visible": True,
            "operator_attestation": True,
            "cryptographic_provider_attestation": False,
            "automatic_aesthetic_verdict": False,
        },
        "does_not_establish": [
            "cryptographic proof that the provider session was authenticated",
            "pixel-identical Miro rendering across devices or times",
            "aesthetic quality or semantic correctness",
            "absence of content outside the captured viewport",
            "current provider state after the capture timestamp",
        ],
    }
    unsigned = dict(receipt)
    receipt["receipt_digest"] = _digest(_canonical(unsigned))
    destination = _write_create_only(output, _canonical(receipt))
    checked = check_visual_truth_receipt(receipt=destination)
    checked.update(
        {
            "output": str(destination),
            "snapshot_path_digest": _digest(str(snapshot_path).encode("utf-8")),
            "capture_path_digest": _digest(str(capture_path).encode("utf-8")),
            "context_path_digest": _digest(str(context_path).encode("utf-8")),
        }
    )
    return checked


def check_visual_truth_receipt(*, receipt: str | Path) -> dict[str, Any]:
    source, payload, value = _load_json(
        receipt,
        "visual-truth receipt",
        max_bytes=MAX_CONTEXT_BYTES,
        schema_file=RECEIPT_SCHEMA_FILE,
    )
    unsigned = dict(value)
    observed_digest = unsigned.pop("receipt_digest")
    if observed_digest != _digest(_canonical(unsigned)):
        raise VisualTruthError("visual-truth receipt digest does not match")
    return {
        "schema_version": RECEIPT_SCHEMA,
        "success": True,
        "board_alias": value["board_alias"],
        "board_reference_digest": value["board_reference_digest"],
        "board_content_digest": value["board_content_digest"],
        "capture": value["capture"],
        "evidence_strength": value["evidence_strength"],
        "receipt_digest": value["receipt_digest"],
        "receipt_sha256": _digest(payload),
        "receipt_path": str(source),
        "does_not_establish": value["does_not_establish"],
    }
