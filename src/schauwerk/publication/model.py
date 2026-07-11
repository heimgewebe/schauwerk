"""Strict SW-013 publication declarations and deterministic previews."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

PUBLICATION_DECLARATION_SCHEMA = "schauwerk-publication-declaration.v1"
PUBLICATION_PREVIEW_SCHEMA = "schauwerk-publication-preview.v1"
PUBLICATION_OBJECT_SCHEMA = "schauwerk-publication-object.v1"
PUBLICATION_LINK_SCHEMA = "schauwerk-publication-link.v1"

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SENSITIVE_ASSIGNMENT = re.compile(
    rb"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s<]{4,}"
)
_PROVIDER_ASSIGNMENT = re.compile(
    rb"(?i)\b(board[_-]?id|team[_-]?id|client[_-]?id)\s*[:=]\s*[^\s<]{2,}"
)
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_FILE_BYTES = 32 * 1024 * 1024
_MAX_TOTAL_BYTES = 96 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 2048
_MAX_ARCHIVE_UNCOMPRESSED = 96 * 1024 * 1024
_ALLOWED_SOURCE_FIELDS = frozenset({"id", "label", "revision", "sha256"})
_REQUIRED_SOURCE_FIELDS = frozenset({"id", "revision", "sha256"})
_ALLOWED_METADATA_FIELDS = frozenset(
    {
        "audience",
        "presentation_id",
        "presentation_version",
        "public_projection_sha256",
        "scene_order",
        "scene_order_sha256",
        "schema_version",
        "source_revision",
        "template",
        "variant_id",
        "variant_title",
        "visible_content_sha256",
        "visual_grammar",
    }
)
_REQUIRED_METADATA_FIELDS = frozenset(
    {
        "presentation_id",
        "presentation_version",
        "public_projection_sha256",
        "source_revision",
        "visible_content_sha256",
    }
)
_REQUIRED_FALSE_BOUNDARIES = frozenset(
    {
        "contains_absolute_paths",
        "contains_private_sources",
        "contains_speaker_notes",
        "contains_timing",
        "network_dependencies",
        "provider_mutation_attempted",
    }
)
_REQUIRED_PRIVACY_CHECKS = frozenset(
    {
        "all_sources_explicitly_public",
        "exact_file_set_declared",
        "explicit_metadata_fields_only",
        "external_resources_absent",
        "private_content_boundary_false",
        "provider_identifiers_absent",
        "secret_like_assignments_absent",
        "source_files_digest_verified",
        "source_manifest_digest_bound",
        "unknown_visibility_absent",
    }
)


class PublicationError(ValueError):
    """Publication input or state violated a fail-closed contract."""


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_mapping(value: Mapping[str, Any], digest_field: str) -> str:
    return hashlib.sha256(
        canonical_bytes({key: item for key, item in value.items() if key != digest_field})
    ).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        stat = path.lstat()
    except FileNotFoundError as exc:
        raise PublicationError(f"{label} does not exist") from exc
    if path.is_symlink() or not path.is_file():
        raise PublicationError(f"{label} must be a regular non-symlink file")
    if stat.st_size > _MAX_JSON_BYTES:
        raise PublicationError(f"{label} exceeds the size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"{label} must contain an object")
    return value


def _safe_identifier(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise PublicationError(f"{label} is invalid")
    return value


def _safe_version(value: Any) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise PublicationError("version is invalid")
    return value


def _digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PublicationError(f"{label} is invalid")
    return value


def parse_timestamp(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PublicationError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PublicationError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PublicationError(f"{label} must be UTC")
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _reject_control_strings(value: Any, *, label: str) -> None:
    if isinstance(value, str):
        if any(ord(char) < 32 for char in value):
            raise PublicationError(f"{label} contains control characters")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_control_strings(key, label=label)
            _reject_control_strings(item, label=label)
        return
    if isinstance(value, list):
        for item in value:
            _reject_control_strings(item, label=label)


def _string_list(value: Any, *, label: str, maximum: int = 64) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise PublicationError(f"{label} must contain 1-{maximum} values")
    if not all(isinstance(item, str) and item for item in value):
        raise PublicationError(f"{label} values must be non-empty strings")
    if len(set(value)) != len(value):
        raise PublicationError(f"{label} values must be unique")
    return list(value)


def validate_declaration(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicationError("publication declaration must contain an object")
    expected = {
        "schema_version",
        "publication_id",
        "stable_slug",
        "version",
        "view_id",
        "audience",
        "source_manifest_sha256",
        "source_manifest_digest",
        "source_revision",
        "entrypoint",
        "files",
        "metadata_fields",
        "sources",
        "lifecycle",
        "declaration_digest",
    }
    if set(value) != expected:
        raise PublicationError("publication declaration fields are invalid")
    if value.get("schema_version") != PUBLICATION_DECLARATION_SCHEMA:
        raise PublicationError("publication declaration schema is unsupported")

    publication_id = _safe_identifier(value.get("publication_id"), label="publication_id")
    stable_slug = _safe_identifier(value.get("stable_slug"), label="stable_slug")
    version = _safe_version(value.get("version"))
    view_id = _safe_identifier(value.get("view_id"), label="view_id")
    audience = value.get("audience")
    if not isinstance(audience, str) or not 1 <= len(audience) <= 160:
        raise PublicationError("audience is invalid")
    if any(ord(char) < 32 for char in audience):
        raise PublicationError("audience contains control characters")

    source_manifest_sha256 = _digest(
        value.get("source_manifest_sha256"), label="source_manifest_sha256"
    )
    source_manifest_digest = _digest(
        value.get("source_manifest_digest"), label="source_manifest_digest"
    )
    source_revision = value.get("source_revision")
    if not isinstance(source_revision, str) or not 1 <= len(source_revision) <= 200:
        raise PublicationError("source_revision is invalid")
    _reject_control_strings(source_revision, label="source_revision")

    entrypoint = value.get("entrypoint")
    if not isinstance(entrypoint, str) or not _SAFE_FILE.fullmatch(entrypoint):
        raise PublicationError("entrypoint is invalid")
    files = sorted(_string_list(value.get("files"), label="files"))
    if not all(_SAFE_FILE.fullmatch(item) for item in files):
        raise PublicationError("files contain an unsafe name")
    if entrypoint not in files:
        raise PublicationError("entrypoint must be explicitly declared in files")

    metadata_fields = sorted(_string_list(value.get("metadata_fields"), label="metadata_fields"))
    if not set(metadata_fields) <= _ALLOWED_METADATA_FIELDS:
        raise PublicationError("metadata_fields contain an unsupported field")
    if not _REQUIRED_METADATA_FIELDS <= set(metadata_fields):
        raise PublicationError("metadata_fields omit a required provenance field")

    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= 64:
        raise PublicationError("sources must contain 1-64 declarations")
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for index, source in enumerate(raw_sources):
        if not isinstance(source, Mapping) or set(source) != {"id", "visibility", "fields"}:
            raise PublicationError(f"sources[{index}] fields are invalid")
        source_id = _safe_identifier(source.get("id"), label=f"sources[{index}].id")
        if source_id in source_ids:
            raise PublicationError("source declarations must have unique ids")
        source_ids.add(source_id)
        if source.get("visibility") != "public":
            raise PublicationError(f"sources[{index}].visibility must be explicitly public")
        fields = sorted(
            _string_list(source.get("fields"), label=f"sources[{index}].fields", maximum=8)
        )
        if not set(fields) <= _ALLOWED_SOURCE_FIELDS:
            raise PublicationError(f"sources[{index}].fields contain an unsupported field")
        if not _REQUIRED_SOURCE_FIELDS <= set(fields):
            raise PublicationError(f"sources[{index}].fields omit required provenance")
        sources.append({"id": source_id, "visibility": "public", "fields": fields})
    sources.sort(key=lambda item: item["id"])

    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != {
        "published_at",
        "expires_at",
        "replaces_version",
        "expected_link_digest",
    }:
        raise PublicationError("lifecycle fields are invalid")
    published_at = parse_timestamp(lifecycle.get("published_at"), label="published_at")
    expires_at = parse_timestamp(lifecycle.get("expires_at"), label="expires_at", nullable=True)
    if expires_at is not None and timestamp_value(expires_at) <= timestamp_value(published_at):
        raise PublicationError("expires_at must be after published_at")
    replaces_version = lifecycle.get("replaces_version")
    expected_link_digest = lifecycle.get("expected_link_digest")
    if replaces_version is None:
        if expected_link_digest is not None:
            raise PublicationError("first publication cannot expect a previous link digest")
    else:
        replaces_version = _safe_version(replaces_version)
        expected_link_digest = _digest(expected_link_digest, label="expected_link_digest")
        if replaces_version == version:
            raise PublicationError("replaces_version must differ from version")

    normalized = {
        "schema_version": PUBLICATION_DECLARATION_SCHEMA,
        "publication_id": publication_id,
        "stable_slug": stable_slug,
        "version": version,
        "view_id": view_id,
        "audience": audience,
        "source_manifest_sha256": source_manifest_sha256,
        "source_manifest_digest": source_manifest_digest,
        "source_revision": source_revision,
        "entrypoint": entrypoint,
        "files": files,
        "metadata_fields": metadata_fields,
        "sources": sources,
        "lifecycle": {
            "published_at": published_at,
            "expires_at": expires_at,
            "replaces_version": replaces_version,
            "expected_link_digest": expected_link_digest,
        },
    }
    actual = digest_mapping({**normalized, "declaration_digest": ""}, "declaration_digest")
    declared = _digest(value.get("declaration_digest"), label="declaration_digest")
    if declared != actual:
        raise PublicationError("publication declaration digest mismatch")
    normalized["declaration_digest"] = actual
    return normalized


def compile_declaration(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an author draft before binding its canonical digest."""

    value = dict(draft)
    if isinstance(value.get("files"), list):
        value["files"] = sorted(value["files"])
    if isinstance(value.get("metadata_fields"), list):
        value["metadata_fields"] = sorted(value["metadata_fields"])
    if isinstance(value.get("sources"), list):
        sources = []
        for source in value["sources"]:
            if isinstance(source, Mapping):
                normalized_source = dict(source)
                if isinstance(normalized_source.get("fields"), list):
                    normalized_source["fields"] = sorted(normalized_source["fields"])
                sources.append(normalized_source)
            else:
                sources.append(source)
        if all(
            isinstance(source, Mapping) and isinstance(source.get("id"), str) for source in sources
        ):
            sources.sort(key=lambda source: source["id"])
        value["sources"] = sources
    if isinstance(value.get("lifecycle"), Mapping):
        lifecycle = dict(value["lifecycle"])
        lifecycle["published_at"] = parse_timestamp(
            lifecycle.get("published_at"), label="published_at"
        )
        lifecycle["expires_at"] = parse_timestamp(
            lifecycle.get("expires_at"), label="expires_at", nullable=True
        )
        value["lifecycle"] = lifecycle
    value["schema_version"] = PUBLICATION_DECLARATION_SCHEMA
    value["declaration_digest"] = "0" * 64
    value["declaration_digest"] = digest_mapping(value, "declaration_digest")
    return validate_declaration(value)


def load_declaration(path: Path) -> dict[str, Any]:
    return validate_declaration(_read_json(path, label="publication declaration"))


def _validate_stage_manifest(value: Mapping[str, Any], raw: bytes) -> dict[str, Any]:
    expected = {
        "schema_version",
        "presentation_id",
        "presentation_version",
        "variant_id",
        "source_revision",
        "entrypoint",
        "files",
        "artifact_metadata",
        "boundaries",
        "manifest_digest",
    }
    if set(value) != expected:
        raise PublicationError("source public manifest fields are invalid")
    if value.get("schema_version") != "schauwerk-stage-public-package.v1":
        raise PublicationError("source package is not an SW-012 public package")
    declared_digest = _digest(value.get("manifest_digest"), label="manifest_digest")
    actual_digest = digest_mapping(value, "manifest_digest")
    if declared_digest != actual_digest:
        raise PublicationError("source public manifest digest mismatch")
    boundaries = value.get("boundaries")
    if not isinstance(boundaries, Mapping) or set(boundaries) != _REQUIRED_FALSE_BOUNDARIES:
        raise PublicationError("source package boundaries are incomplete or unknown")
    if any(boundaries[item] is not False for item in _REQUIRED_FALSE_BOUNDARIES):
        raise PublicationError("source package boundaries are not public-safe")
    artifact_metadata = value.get("artifact_metadata")
    if not isinstance(artifact_metadata, Mapping):
        raise PublicationError("source artifact metadata is invalid")
    public_sources = artifact_metadata.get("public_sources")
    if not isinstance(public_sources, list) or not public_sources:
        raise PublicationError("source package has no explicit public sources")
    files = value.get("files")
    if not isinstance(files, Mapping) or not files:
        raise PublicationError("source package file manifest is invalid")
    return {**dict(value), "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def _validate_html(name: str, payload: bytes) -> None:
    try:
        lowered = payload.decode("utf-8").lower()
    except UnicodeDecodeError as exc:
        raise PublicationError(f"{name} is not UTF-8 HTML") from exc
    forbidden = ("<script", "<link", "<iframe", "<object", "<embed", " src=", "file://")
    if any(marker in lowered for marker in forbidden):
        raise PublicationError(f"{name} contains an external or active HTML resource")
    if "http://" in lowered or "https://" in lowered:
        raise PublicationError(f"{name} contains an external URL")
    if "content-security-policy" not in lowered:
        raise PublicationError(f"{name} has no Content-Security-Policy")


def _scan_privacy(label: str, payload: bytes) -> None:
    lowered = payload.lower()
    if b"/home/" in lowered or b"file://" in lowered or b"c:\\users\\" in lowered:
        raise PublicationError(f"{label} contains an absolute local path")
    if _SENSITIVE_ASSIGNMENT.search(payload):
        raise PublicationError(f"{label} contains a secret-like assignment")
    if _PROVIDER_ASSIGNMENT.search(payload):
        raise PublicationError(f"{label} contains a provider identifier assignment")


def _validate_pptx(name: str, payload: bytes) -> None:
    from io import BytesIO

    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= _MAX_ARCHIVE_MEMBERS:
                raise PublicationError(f"{name} has an invalid ZIP member count")
            member_names = [info.filename for info in infos]
            if len(set(member_names)) != len(member_names):
                raise PublicationError(f"{name} contains duplicate ZIP members")
            uncompressed_total = 0
            for info in infos:
                member = info.filename
                path = Path(member)
                if (
                    not member
                    or "\\" in member
                    or "\x00" in member
                    or path.is_absolute()
                    or ".." in path.parts
                ):
                    raise PublicationError(f"{name} contains an unsafe ZIP member")
                if info.flag_bits & 0x1:
                    raise PublicationError(f"{name} contains an encrypted ZIP member")
                if info.file_size > _MAX_FILE_BYTES:
                    raise PublicationError(f"{name} contains an oversized ZIP member")
                uncompressed_total += info.file_size
                if uncompressed_total > _MAX_ARCHIVE_UNCOMPRESSED:
                    raise PublicationError(f"{name} exceeds the uncompressed ZIP size limit")
                lowered_member = member.lower()
                if (
                    lowered_member.startswith("ppt/notesslides/")
                    or lowered_member.startswith("ppt/notesmasters/")
                    or lowered_member.startswith("ppt/comments/")
                    or lowered_member.startswith("ppt/embeddings/")
                    or lowered_member.startswith("customxml/")
                    or lowered_member.endswith("vbaproject.bin")
                ):
                    raise PublicationError(f"{name} contains a private or active ZIP member")
                if info.is_dir():
                    continue
                member_payload = archive.read(info)
                if len(member_payload) != info.file_size:
                    raise PublicationError(f"{name} ZIP member size changed while reading")
                _scan_privacy(f"{name}:{member}", member_payload)
                if lowered_member.endswith(".rels") and b'TargetMode="External"' in member_payload:
                    raise PublicationError(f"{name} contains an external relationship")
    except BadZipFile as exc:
        raise PublicationError(f"{name} is not a valid PPTX archive") from exc


def _validate_file_privacy(name: str, payload: bytes) -> None:
    _scan_privacy(name, payload)
    if name.endswith(".html"):
        _validate_html(name, payload)
    elif name.endswith(".pdf"):
        forbidden_pdf_objects = (
            b"/URI",
            b"/EmbeddedFile",
            b"/JavaScript",
            b"/Launch",
            b"/OpenAction",
            b"/AA",
            b"/AcroForm",
            b"/XFA",
            b"/RichMedia",
            b"/FileSpec",
        )
        if any(marker in payload for marker in forbidden_pdf_objects):
            raise PublicationError(f"{name} contains a link, attachment, form, or active action")
    elif name.endswith(".pptx"):
        _validate_pptx(name, payload)


def load_source_package(source_dir: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        source_dir.lstat()
    except FileNotFoundError as exc:
        raise PublicationError("source package directory does not exist") from exc
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise PublicationError("source package must be a non-symlink directory")
    manifest_path = source_dir / "manifest.json"
    try:
        manifest_stat = manifest_path.lstat()
    except FileNotFoundError as exc:
        raise PublicationError("source public manifest is missing") from exc
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or not 0 < manifest_stat.st_size <= _MAX_JSON_BYTES
    ):
        raise PublicationError("source public manifest is missing or too large")
    raw = manifest_path.read_bytes()
    if len(raw) != manifest_stat.st_size:
        raise PublicationError("source public manifest changed while being read")
    try:
        manifest_value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationError("source public manifest is invalid") from exc
    if not isinstance(manifest_value, dict):
        raise PublicationError("source public manifest must contain an object")
    manifest = _validate_stage_manifest(manifest_value, raw)

    payloads: dict[str, bytes] = {}
    total = 0
    for name, record in manifest["files"].items():
        if not isinstance(name, str) or not _SAFE_FILE.fullmatch(name):
            raise PublicationError("source package contains an unsafe file name")
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise PublicationError(f"source file record {name} is invalid")
        expected_size = record.get("bytes")
        if not isinstance(expected_size, int) or not 0 <= expected_size <= _MAX_FILE_BYTES:
            raise PublicationError(f"source file {name} size is invalid")
        expected_digest = _digest(record.get("sha256"), label=f"files.{name}.sha256")
        path = source_dir / name
        try:
            stat = path.lstat()
        except FileNotFoundError as exc:
            raise PublicationError(f"source file {name} is missing") from exc
        if path.is_symlink() or not path.is_file():
            raise PublicationError(f"source file {name} is not a regular file")
        if stat.st_size != expected_size:
            raise PublicationError(f"source file {name} size mismatch")
        payload = path.read_bytes()
        if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_digest:
            raise PublicationError(f"source file {name} digest mismatch")
        _validate_file_privacy(name, payload)
        payloads[name] = payload
        total += len(payload)
        if total > _MAX_TOTAL_BYTES:
            raise PublicationError("source package exceeds the total size limit")
    entrypoint = manifest.get("entrypoint")
    if entrypoint not in payloads or not str(entrypoint).endswith(".html"):
        raise PublicationError("source package entrypoint is invalid")
    actual_names = {item.name for item in source_dir.iterdir() if item.name != "manifest.json"}
    if actual_names != set(payloads):
        raise PublicationError("source package contains undeclared files")
    return manifest, payloads


def compile_preview_from_loaded(
    declaration: Mapping[str, Any],
    manifest: Mapping[str, Any],
    payloads: Mapping[str, bytes],
) -> dict[str, Any]:
    declared = validate_declaration(declaration)
    if declared["source_manifest_sha256"] != manifest["manifest_sha256"]:
        raise PublicationError("declaration source manifest SHA-256 mismatch")
    if declared["source_manifest_digest"] != manifest["manifest_digest"]:
        raise PublicationError("declaration source manifest digest mismatch")
    if declared["source_revision"] != manifest["source_revision"]:
        raise PublicationError("declaration source revision mismatch")
    if declared["entrypoint"] != manifest["entrypoint"]:
        raise PublicationError("declaration entrypoint mismatch")
    if declared["files"] != sorted(manifest["files"]):
        raise PublicationError(
            "declaration must explicitly enumerate the exact source package file set"
        )

    artifact_metadata = manifest["artifact_metadata"]
    public_sources = artifact_metadata["public_sources"]
    source_by_id: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(public_sources):
        if not isinstance(source, Mapping) or set(source) != _ALLOWED_SOURCE_FIELDS:
            raise PublicationError(f"public_sources[{index}] fields are invalid")
        source_id = _safe_identifier(source.get("id"), label=f"public_sources[{index}].id")
        if source_id in source_by_id:
            raise PublicationError("source package public source ids are not unique")
        revision = source.get("revision")
        if (
            not isinstance(revision, str)
            or not 1 <= len(revision) <= 4000
            or any(ord(char) < 32 for char in revision)
        ):
            raise PublicationError(f"public source {source_id} revision is invalid")
        label = source.get("label")
        if (
            not isinstance(label, str)
            or not 1 <= len(label) <= 4000
            or any(ord(char) < 32 for char in label)
        ):
            raise PublicationError(f"public source {source_id} label is invalid")
        _digest(source.get("sha256"), label=f"public source {source_id} sha256")
        source_by_id[source_id] = source
    declared_source_ids = [item["id"] for item in declared["sources"]]
    if sorted(source_by_id) != declared_source_ids:
        raise PublicationError("declaration must explicitly enumerate the exact public source set")

    selected_sources = []
    for source_declaration in declared["sources"]:
        source = source_by_id[source_declaration["id"]]
        selected_sources.append({field: source[field] for field in source_declaration["fields"]})
    try:
        selected_metadata = {
            field: artifact_metadata[field] for field in declared["metadata_fields"]
        }
    except KeyError as exc:
        raise PublicationError(
            f"source artifact metadata omits declared field {exc.args[0]}"
        ) from exc
    _reject_control_strings(selected_metadata, label="selected publication metadata")
    _reject_control_strings(selected_sources, label="selected public sources")
    _scan_privacy(
        "selected publication metadata",
        canonical_bytes(
            {
                "metadata": selected_metadata,
                "sources": selected_sources,
            }
        ),
    )
    if selected_metadata["source_revision"] != declared["source_revision"]:
        raise PublicationError("selected metadata source revision mismatch")
    if artifact_metadata.get("audience") != declared["audience"]:
        raise PublicationError("declaration audience does not match the source package")

    file_records = {
        name: {
            "bytes": len(payloads[name]),
            "sha256": hashlib.sha256(payloads[name]).hexdigest(),
        }
        for name in declared["files"]
    }
    preview: dict[str, Any] = {
        "schema_version": PUBLICATION_PREVIEW_SCHEMA,
        "publication_id": declared["publication_id"],
        "stable_slug": declared["stable_slug"],
        "version": declared["version"],
        "view_id": declared["view_id"],
        "audience": declared["audience"],
        "entrypoint": declared["entrypoint"],
        "lifecycle": declared["lifecycle"],
        "source_package": {
            "schema_version": manifest["schema_version"],
            "manifest_sha256": manifest["manifest_sha256"],
            "manifest_digest": manifest["manifest_digest"],
            "source_revision": manifest["source_revision"],
            "selected_metadata": selected_metadata,
            "selected_public_sources": selected_sources,
        },
        "files": file_records,
        "privacy_checks": {
            "all_sources_explicitly_public": True,
            "exact_file_set_declared": True,
            "explicit_metadata_fields_only": True,
            "external_resources_absent": True,
            "private_content_boundary_false": True,
            "provider_identifiers_absent": True,
            "secret_like_assignments_absent": True,
            "source_files_digest_verified": True,
            "source_manifest_digest_bound": True,
            "unknown_visibility_absent": True,
        },
        "declaration_digest": declared["declaration_digest"],
        "preview_digest": "",
    }
    preview["preview_digest"] = digest_mapping(preview, "preview_digest")
    return validate_preview(preview)


def compile_preview(
    declaration: Mapping[str, Any], source_dir: Path
) -> tuple[dict[str, Any], dict[str, bytes]]:
    manifest, payloads = load_source_package(source_dir)
    return compile_preview_from_loaded(declaration, manifest, payloads), payloads


def validate_preview(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "publication_id",
        "stable_slug",
        "version",
        "view_id",
        "audience",
        "entrypoint",
        "lifecycle",
        "source_package",
        "files",
        "privacy_checks",
        "declaration_digest",
        "preview_digest",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PublicationError("publication preview fields are invalid")
    if value.get("schema_version") != PUBLICATION_PREVIEW_SCHEMA:
        raise PublicationError("publication preview schema is unsupported")
    _safe_identifier(value.get("publication_id"), label="publication_id")
    _safe_identifier(value.get("stable_slug"), label="stable_slug")
    version = _safe_version(value.get("version"))
    _safe_identifier(value.get("view_id"), label="view_id")
    audience = value.get("audience")
    if not isinstance(audience, str) or not 1 <= len(audience) <= 160:
        raise PublicationError("publication preview audience is invalid")
    if any(ord(char) < 32 for char in audience):
        raise PublicationError("publication preview audience contains control characters")
    entrypoint = value.get("entrypoint")
    if not isinstance(entrypoint, str) or not _SAFE_FILE.fullmatch(entrypoint):
        raise PublicationError("publication preview entrypoint is invalid")

    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != {
        "published_at",
        "expires_at",
        "replaces_version",
        "expected_link_digest",
    }:
        raise PublicationError("publication preview lifecycle is invalid")
    published_at = parse_timestamp(lifecycle.get("published_at"), label="published_at")
    expires_at = parse_timestamp(lifecycle.get("expires_at"), label="expires_at", nullable=True)
    if lifecycle.get("published_at") != published_at or lifecycle.get("expires_at") != expires_at:
        raise PublicationError("publication preview lifecycle timestamps are not canonical")
    if expires_at is not None and timestamp_value(expires_at) <= timestamp_value(published_at):
        raise PublicationError("publication preview expiry is invalid")
    replaces_version = lifecycle.get("replaces_version")
    expected_link_digest = lifecycle.get("expected_link_digest")
    if replaces_version is None:
        if expected_link_digest is not None:
            raise PublicationError("publication preview replacement binding is invalid")
    else:
        replaces_version = _safe_version(replaces_version)
        if replaces_version == version:
            raise PublicationError("publication preview cannot replace its own version")
        _digest(expected_link_digest, label="expected_link_digest")

    source_package = value.get("source_package")
    if not isinstance(source_package, Mapping) or set(source_package) != {
        "schema_version",
        "manifest_sha256",
        "manifest_digest",
        "source_revision",
        "selected_metadata",
        "selected_public_sources",
    }:
        raise PublicationError("publication preview source package is invalid")
    if source_package.get("schema_version") != "schauwerk-stage-public-package.v1":
        raise PublicationError("publication preview source package schema is unsupported")
    _digest(source_package.get("manifest_sha256"), label="manifest_sha256")
    _digest(source_package.get("manifest_digest"), label="manifest_digest")
    source_revision = source_package.get("source_revision")
    if not isinstance(source_revision, str) or not 1 <= len(source_revision) <= 200:
        raise PublicationError("publication preview source revision is invalid")
    _reject_control_strings(source_revision, label="publication preview source revision")
    selected_metadata = source_package.get("selected_metadata")
    if not isinstance(selected_metadata, Mapping):
        raise PublicationError("publication preview selected metadata is invalid")
    if not _REQUIRED_METADATA_FIELDS <= set(selected_metadata) <= _ALLOWED_METADATA_FIELDS:
        raise PublicationError("publication preview selected metadata fields are invalid")
    if selected_metadata.get("source_revision") != source_revision:
        raise PublicationError("publication preview selected metadata revision mismatch")
    if selected_metadata.get("audience", audience) != audience:
        raise PublicationError("publication preview selected audience mismatch")
    selected_sources = source_package.get("selected_public_sources")
    if not isinstance(selected_sources, list) or not selected_sources:
        raise PublicationError("publication preview selected public sources are invalid")
    source_ids: set[str] = set()
    for index, source in enumerate(selected_sources):
        if not isinstance(source, Mapping):
            raise PublicationError(f"selected_public_sources[{index}] is invalid")
        if not _REQUIRED_SOURCE_FIELDS <= set(source) <= _ALLOWED_SOURCE_FIELDS:
            raise PublicationError(f"selected_public_sources[{index}] fields are invalid")
        source_id = _safe_identifier(source.get("id"), label=f"selected_public_sources[{index}].id")
        if source_id in source_ids:
            raise PublicationError("publication preview public source ids are not unique")
        source_ids.add(source_id)
        revision = source.get("revision")
        if not isinstance(revision, str) or not revision:
            raise PublicationError(f"selected public source {source_id} revision is invalid")
        _digest(source.get("sha256"), label=f"selected public source {source_id} sha256")
        if "label" in source and (not isinstance(source["label"], str) or not source["label"]):
            raise PublicationError(f"selected public source {source_id} label is invalid")

    files = value.get("files")
    if not isinstance(files, Mapping) or not files or entrypoint not in files:
        raise PublicationError("publication preview files are invalid")
    for name, record in files.items():
        if not isinstance(name, str) or not _SAFE_FILE.fullmatch(name):
            raise PublicationError("publication preview file name is invalid")
        if not isinstance(record, Mapping) or set(record) != {"bytes", "sha256"}:
            raise PublicationError("publication preview file fields are invalid")
        if not isinstance(record["bytes"], int) or not 0 <= record["bytes"] <= _MAX_FILE_BYTES:
            raise PublicationError("publication preview file size is invalid")
        _digest(record["sha256"], label=f"files.{name}.sha256")

    checks = value.get("privacy_checks")
    if not isinstance(checks, Mapping) or set(checks) != _REQUIRED_PRIVACY_CHECKS:
        raise PublicationError("publication preview privacy checks are incomplete")
    if any(item is not True for item in checks.values()):
        raise PublicationError("publication preview privacy checks did not pass")
    _digest(value.get("declaration_digest"), label="declaration_digest")
    declared = _digest(value.get("preview_digest"), label="preview_digest")
    actual = digest_mapping(value, "preview_digest")
    if declared != actual:
        raise PublicationError("publication preview digest mismatch")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def load_preview(path: Path) -> dict[str, Any]:
    return validate_preview(_read_json(path, label="publication preview"))
