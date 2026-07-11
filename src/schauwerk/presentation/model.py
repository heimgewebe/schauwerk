"""Strict SW-012 presentation model and source-bound validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MODEL_SCHEMA_VERSION = "schauwerk-presentation.v1"
PUBLIC_FORMATS = frozenset({"html", "pdf", "pptx", "handout"})
PRESENTER_FORMATS = frozenset({"html", "json"})
BLOCK_KINDS = frozenset({"paragraph", "bullets", "callout", "code"})
VISIBILITIES = frozenset({"public", "internal", "private"})
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9.-]{0,79}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_TEXT = (
    re.compile(r"(?:^|[\s\"'])/(?:home|Users|var|etc|tmp)/"),
    re.compile(r"\b[A-Za-z]:\\"),
    re.compile(r"\bhttps?://", re.IGNORECASE),
    re.compile(r"\bfile://", re.IGNORECASE),
    re.compile(r"\b(?:board|team|item|provider)[_-]?id\s*[:=]", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
)


class PresentationModelError(ValueError):
    """Raised when a presentation declaration violates the SW-012 contract."""


@dataclass(frozen=True)
class SourceRef:
    identifier: str
    label: str
    revision: str
    sha256: str
    visibility: str
    artifact: str


@dataclass(frozen=True)
class ContentBlock:
    kind: str
    text: str | None
    items: tuple[str, ...]
    source_ids: tuple[str, ...]

    def visible_strings(self) -> tuple[str, ...]:
        if self.kind == "bullets":
            return self.items
        return (self.text or "",)


@dataclass(frozen=True)
class Scene:
    identifier: str
    title: str
    blocks: tuple[ContentBlock, ...]
    speaker_notes: tuple[str, ...]
    duration_seconds: int
    source_ids: tuple[str, ...]

    def visible_strings(self) -> tuple[str, ...]:
        result = [self.title]
        for block in self.blocks:
            result.extend(block.visible_strings())
        return tuple(result)


@dataclass(frozen=True)
class OutputProfile:
    identifier: str
    visibility: str
    formats: tuple[str, ...]
    include_speaker_notes: bool
    include_timing: bool
    include_private_sources: bool


@dataclass(frozen=True)
class Variant:
    identifier: str
    audience: str
    title: str
    scene_ids: tuple[str, ...]
    planned_duration_seconds: int
    public_profile_id: str
    presenter_profile_id: str


@dataclass(frozen=True)
class Presentation:
    presentation_id: str
    version: str
    title: str
    source_revision: str
    sources: tuple[SourceRef, ...]
    output_profiles: tuple[OutputProfile, ...]
    variants: tuple[Variant, ...]
    scenes: tuple[Scene, ...]
    model_digest: str

    @property
    def source_by_id(self) -> dict[str, SourceRef]:
        return {item.identifier: item for item in self.sources}

    @property
    def scene_by_id(self) -> dict[str, Scene]:
        return {item.identifier: item for item in self.scenes}

    @property
    def profile_by_id(self) -> dict[str, OutputProfile]:
        return {item.identifier: item for item in self.output_profiles}

    @property
    def variant_by_id(self) -> dict[str, Variant]:
        return {item.identifier: item for item in self.variants}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def stable_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PresentationModelError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str, minimum: int = 1) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum:
        raise PresentationModelError(f"{label} must be a list with at least {minimum} item(s)")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], *, label: str) -> None:
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise PresentationModelError(f"{label} contains unknown field(s): {', '.join(unknown)}")
    if missing:
        raise PresentationModelError(f"{label} is missing field(s): {', '.join(missing)}")


def _identifier_value(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise PresentationModelError(f"{label} must be a lowercase stable identifier")
    return value


def _text(value: Any, *, label: str, maximum: int = 4000, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise PresentationModelError(f"{label} must be text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        normalized = " ".join(normalized.split())
    else:
        normalized = normalized.strip("\n")
    if not normalized or len(normalized) > maximum:
        raise PresentationModelError(f"{label} must contain 1 to {maximum} characters")
    for char in normalized:
        if ord(char) < 32 and char not in {"\n", "\t"}:
            raise PresentationModelError(f"{label} contains a control character")
    for pattern in _FORBIDDEN_TEXT:
        if pattern.search(normalized):
            raise PresentationModelError(
                f"{label} contains a URL, absolute path, provider identifier or secret-like value"
            )
    return normalized


def _string_list(
    value: Any,
    *,
    label: str,
    minimum: int = 1,
    maximum_items: int = 40,
    multiline: bool = False,
) -> tuple[str, ...]:
    values = _sequence(value, label=label, minimum=minimum)
    if len(values) > maximum_items:
        raise PresentationModelError(f"{label} has too many items")
    result = tuple(
        _text(item, label=f"{label}[{index}]", multiline=multiline)
        for index, item in enumerate(values)
    )
    if len(set(result)) != len(result):
        raise PresentationModelError(f"{label} contains duplicate values")
    return result


def _identifier_list(value: Any, *, label: str, minimum: int = 1) -> tuple[str, ...]:
    values = _sequence(value, label=label, minimum=minimum)
    result = tuple(
        _identifier_value(item, label=f"{label}[{index}]") for index, item in enumerate(values)
    )
    if len(set(result)) != len(result):
        raise PresentationModelError(f"{label} contains duplicate identifiers")
    return result


def _boolean(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise PresentationModelError(f"{label} must be boolean")
    return value


def _integer(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise PresentationModelError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _artifact_path(value: Any, *, label: str) -> str:
    text = _text(value, label=label, maximum=500)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or text in {".", ""}:
        raise PresentationModelError(f"{label} must be a repository-relative artifact path")
    return path.as_posix()


def _load_source(raw: Any, *, index: int, source_root: Path) -> SourceRef:
    item = _mapping(raw, label=f"sources[{index}]")
    _exact_keys(
        item,
        {"id", "label", "revision", "sha256", "visibility", "artifact"},
        label=f"sources[{index}]",
    )
    identifier = _identifier_value(item["id"], label=f"sources[{index}].id")
    label = _text(item["label"], label=f"sources[{index}].label", maximum=200)
    revision = _text(item["revision"], label=f"sources[{index}].revision", maximum=200)
    digest = item["sha256"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise PresentationModelError(f"sources[{index}].sha256 must be a lowercase SHA-256 digest")
    visibility = item["visibility"]
    if visibility not in VISIBILITIES:
        raise PresentationModelError(f"sources[{index}].visibility is invalid")
    artifact = _artifact_path(item["artifact"], label=f"sources[{index}].artifact")
    try:
        root = source_root.resolve(strict=True)
        candidate = source_root / artifact
        target = candidate.resolve(strict=True)
    except OSError as exc:
        raise PresentationModelError(f"source artifact is missing or unsafe: {artifact}") from exc
    if root != target and root not in target.parents:
        raise PresentationModelError(f"source artifact escapes source root: {artifact}")
    current = root
    for part in PurePosixPath(artifact).parts:
        current = current / part
        if current.is_symlink():
            raise PresentationModelError(f"source artifact uses a symlink: {artifact}")
    if not target.is_file():
        raise PresentationModelError(f"source artifact is missing or unsafe: {artifact}")
    if target.stat().st_size > 16 * 1024 * 1024:
        raise PresentationModelError(f"source artifact exceeds 16 MiB: {artifact}")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != digest:
        raise PresentationModelError(f"source artifact digest mismatch: {artifact}")
    return SourceRef(identifier, label, revision, digest, visibility, artifact)


def _load_block(raw: Any, *, scene_index: int, block_index: int) -> ContentBlock:
    label = f"scenes[{scene_index}].visible[{block_index}]"
    item = _mapping(raw, label=label)
    _exact_keys(item, {"kind", "text", "items", "source_ids"}, label=label)
    kind = item["kind"]
    if kind not in BLOCK_KINDS:
        raise PresentationModelError(f"{label}.kind is invalid")
    source_ids = _identifier_list(item["source_ids"], label=f"{label}.source_ids")
    if kind == "bullets":
        if item["text"] is not None:
            raise PresentationModelError(f"{label}.text must be null for bullets")
        items = _string_list(item["items"], label=f"{label}.items", maximum_items=12)
        text = None
    else:
        if item["items"] != []:
            raise PresentationModelError(f"{label}.items must be empty for {kind}")
        text = _text(
            item["text"],
            label=f"{label}.text",
            maximum=1800,
            multiline=kind == "code",
        )
        items = ()
    return ContentBlock(kind, text, items, source_ids)


def _load_scene(raw: Any, *, index: int) -> Scene:
    label = f"scenes[{index}]"
    item = _mapping(raw, label=label)
    _exact_keys(
        item,
        {"id", "title", "visible", "speaker_notes", "duration_seconds", "source_ids"},
        label=label,
    )
    blocks = tuple(
        _load_block(block, scene_index=index, block_index=block_index)
        for block_index, block in enumerate(_sequence(item["visible"], label=f"{label}.visible"))
    )
    return Scene(
        identifier=_identifier_value(item["id"], label=f"{label}.id"),
        title=_text(item["title"], label=f"{label}.title", maximum=180),
        blocks=blocks,
        speaker_notes=_string_list(
            item["speaker_notes"], label=f"{label}.speaker_notes", minimum=1, maximum_items=12
        ),
        duration_seconds=_integer(
            item["duration_seconds"], label=f"{label}.duration_seconds", minimum=15, maximum=3600
        ),
        source_ids=_identifier_list(item["source_ids"], label=f"{label}.source_ids"),
    )


def _load_profile(raw: Any, *, index: int) -> OutputProfile:
    label = f"output_profiles[{index}]"
    item = _mapping(raw, label=label)
    _exact_keys(
        item,
        {
            "id",
            "visibility",
            "formats",
            "include_speaker_notes",
            "include_timing",
            "include_private_sources",
        },
        label=label,
    )
    identifier = _identifier_value(item["id"], label=f"{label}.id")
    visibility = item["visibility"]
    if visibility not in {"public", "private"}:
        raise PresentationModelError(f"{label}.visibility must be public or private")
    formats = _identifier_list(item["formats"], label=f"{label}.formats")
    profile = OutputProfile(
        identifier=identifier,
        visibility=visibility,
        formats=formats,
        include_speaker_notes=_boolean(
            item["include_speaker_notes"], label=f"{label}.include_speaker_notes"
        ),
        include_timing=_boolean(item["include_timing"], label=f"{label}.include_timing"),
        include_private_sources=_boolean(
            item["include_private_sources"], label=f"{label}.include_private_sources"
        ),
    )
    if visibility == "public":
        if set(profile.formats) != PUBLIC_FORMATS:
            raise PresentationModelError(
                f"{label} must declare exactly html, pdf, pptx and handout"
            )
        if (
            profile.include_speaker_notes
            or profile.include_timing
            or profile.include_private_sources
        ):
            raise PresentationModelError(
                f"{label} public profile must exclude notes, timing and private sources"
            )
    else:
        if set(profile.formats) != PRESENTER_FORMATS:
            raise PresentationModelError(
                f"{label} presenter profile must declare exactly html and json"
            )
        if (
            not profile.include_speaker_notes
            or not profile.include_timing
            or not profile.include_private_sources
        ):
            raise PresentationModelError(
                f"{label} presenter profile must include notes, timing and private sources"
            )
    return profile


def _load_variant(raw: Any, *, index: int) -> Variant:
    label = f"variants[{index}]"
    item = _mapping(raw, label=label)
    _exact_keys(
        item,
        {
            "id",
            "audience",
            "title",
            "scene_ids",
            "planned_duration_seconds",
            "public_profile_id",
            "presenter_profile_id",
        },
        label=label,
    )
    return Variant(
        identifier=_identifier_value(item["id"], label=f"{label}.id"),
        audience=_text(item["audience"], label=f"{label}.audience", maximum=160),
        title=_text(item["title"], label=f"{label}.title", maximum=180),
        scene_ids=_identifier_list(item["scene_ids"], label=f"{label}.scene_ids", minimum=2),
        planned_duration_seconds=_integer(
            item["planned_duration_seconds"],
            label=f"{label}.planned_duration_seconds",
            minimum=30,
            maximum=24 * 60 * 60,
        ),
        public_profile_id=_identifier_value(
            item["public_profile_id"], label=f"{label}.public_profile_id"
        ),
        presenter_profile_id=_identifier_value(
            item["presenter_profile_id"], label=f"{label}.presenter_profile_id"
        ),
    )


def _unique_identifiers(values: tuple[Any, ...], *, label: str) -> None:
    identifiers = [item.identifier for item in values]
    if len(set(identifiers)) != len(identifiers):
        raise PresentationModelError(f"{label} contains duplicate identifiers")


def load_presentation(path: Path, *, source_root: Path) -> Presentation:
    """Load, validate and source-bind one presentation declaration."""

    if path.is_symlink() or not path.is_file():
        raise PresentationModelError("presentation model must be a regular file")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise PresentationModelError("presentation model exceeds 2 MiB")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PresentationModelError("presentation model is not valid UTF-8 JSON") from exc
    data = _mapping(raw, label="presentation")
    _exact_keys(
        data,
        {
            "schema_version",
            "presentation_id",
            "version",
            "title",
            "source_revision",
            "sources",
            "output_profiles",
            "variants",
            "scenes",
        },
        label="presentation",
    )
    if data["schema_version"] != MODEL_SCHEMA_VERSION:
        raise PresentationModelError(f"schema_version must be {MODEL_SCHEMA_VERSION}")
    presentation_id = _identifier_value(data["presentation_id"], label="presentation_id")
    version = data["version"]
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise PresentationModelError("version must use semantic major.minor.patch form")
    title = _text(data["title"], label="title", maximum=180)
    source_revision = _text(data["source_revision"], label="source_revision", maximum=200)
    sources = tuple(
        _load_source(item, index=index, source_root=source_root)
        for index, item in enumerate(_sequence(data["sources"], label="sources"))
    )
    profiles = tuple(
        _load_profile(item, index=index)
        for index, item in enumerate(
            _sequence(data["output_profiles"], label="output_profiles", minimum=2)
        )
    )
    variants = tuple(
        _load_variant(item, index=index)
        for index, item in enumerate(_sequence(data["variants"], label="variants"))
    )
    scenes = tuple(
        _load_scene(item, index=index)
        for index, item in enumerate(_sequence(data["scenes"], label="scenes", minimum=2))
    )
    _unique_identifiers(sources, label="sources")
    _unique_identifiers(profiles, label="output_profiles")
    _unique_identifiers(variants, label="variants")
    _unique_identifiers(scenes, label="scenes")

    source_map = {item.identifier: item for item in sources}
    profile_map = {item.identifier: item for item in profiles}
    scene_map = {item.identifier: item for item in scenes}
    used_sources: set[str] = set()
    for scene in scenes:
        unknown_scene_sources = sorted(set(scene.source_ids) - set(source_map))
        if unknown_scene_sources:
            unknown_text = ", ".join(unknown_scene_sources)
            raise PresentationModelError(
                f"scene {scene.identifier} references unknown source(s): {unknown_text}"
            )
        used_sources.update(scene.source_ids)
        visible_source_ids: set[str] = set()
        for block in scene.blocks:
            unknown = sorted(set(block.source_ids) - set(source_map))
            if unknown:
                unknown_text = ", ".join(unknown)
                raise PresentationModelError(
                    f"scene {scene.identifier} visible block references unknown source(s): "
                    f"{unknown_text}"
                )
            if not set(block.source_ids).issubset(scene.source_ids):
                raise PresentationModelError(
                    f"scene {scene.identifier} visible source is missing from scene.source_ids"
                )
            private = sorted(
                source_id
                for source_id in block.source_ids
                if source_map[source_id].visibility != "public"
            )
            if private:
                raise PresentationModelError(
                    f"scene {scene.identifier} exposes non-public source(s): {', '.join(private)}"
                )
            visible_source_ids.update(block.source_ids)
        if not visible_source_ids:
            raise PresentationModelError(f"scene {scene.identifier} has no public visible source")

    unused = sorted(set(source_map) - used_sources)
    if unused:
        raise PresentationModelError(f"unused source declaration(s): {', '.join(unused)}")

    for variant in variants:
        unknown_scenes = sorted(set(variant.scene_ids) - set(scene_map))
        if unknown_scenes:
            unknown_text = ", ".join(unknown_scenes)
            raise PresentationModelError(
                f"variant {variant.identifier} references unknown scene(s): {unknown_text}"
            )
        public_profile = profile_map.get(variant.public_profile_id)
        presenter_profile = profile_map.get(variant.presenter_profile_id)
        if public_profile is None or public_profile.visibility != "public":
            raise PresentationModelError(
                f"variant {variant.identifier} has no valid public profile"
            )
        if presenter_profile is None or presenter_profile.visibility != "private":
            raise PresentationModelError(
                f"variant {variant.identifier} has no valid presenter profile"
            )
        actual_duration = sum(scene_map[item].duration_seconds for item in variant.scene_ids)
        if actual_duration != variant.planned_duration_seconds:
            raise PresentationModelError(
                f"variant {variant.identifier} planned duration {variant.planned_duration_seconds} "
                f"does not match scene total {actual_duration}"
            )

    return Presentation(
        presentation_id=presentation_id,
        version=version,
        title=title,
        source_revision=source_revision,
        sources=sources,
        output_profiles=profiles,
        variants=variants,
        scenes=scenes,
        model_digest=stable_digest(data),
    )
