"""Atomic, separated public and presenter packages for SW-012 Bühne."""

from __future__ import annotations

import ctypes
import errno
import os
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .model import PresentationModelError, canonical_json_bytes, load_presentation, stable_digest
from .render import (
    presenter_payload,
    public_metadata,
    render_handout_html,
    render_pdf,
    render_pptx,
    render_presenter_html,
    render_public_html,
    sha256_file,
)

PUBLIC_MANIFEST_VERSION = "schauwerk-stage-public-package.v1"
PRESENTER_MANIFEST_VERSION = "schauwerk-stage-presenter-package.v1"
_FORBIDDEN_PUBLIC_BYTES = (
    b"speaker_notes",
    b"duration_seconds",
    b"planned_duration_seconds",
)
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


def _directory_identity(path: Path) -> tuple[int, int]:
    stat = path.stat(follow_symlinks=False)
    return stat.st_dev, stat.st_ino


def _publish_directory_noreplace(source: Path, destination: Path, *, label: str) -> None:
    """Atomically publish one directory without replacing a concurrent destination."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise PresentationModelError("atomic no-replace directory publication is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return

    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise PresentationModelError(f"{label} appeared during build")
    if error_number in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
        raise PresentationModelError("atomic no-replace directory publication is unavailable")
    raise OSError(error_number, os.strerror(error_number), destination)


def _remove_published_directory(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current_identity = _directory_identity(path)
    except FileNotFoundError:
        return
    if current_identity == identity:
        shutil.rmtree(path, ignore_errors=True)


def _write_bytes(path: Path, payload: bytes, *, mode: int) -> None:
    path.write_bytes(payload)
    os.chmod(path, mode)


def _write_json(path: Path, payload: dict[str, object], *, mode: int) -> None:
    _write_bytes(path, canonical_json_bytes(payload) + b"\n", mode=mode)


def _refuse_destination(path: Path, *, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise PresentationModelError(f"{label} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise PresentationModelError(f"{label} parent is unsafe")


def _ensure_disjoint(public_dir: Path, presenter_dir: Path) -> None:
    public = public_dir.resolve(strict=False)
    presenter = presenter_dir.resolve(strict=False)
    if public == presenter or public in presenter.parents or presenter in public.parents:
        raise PresentationModelError("public and presenter destinations must be disjoint")


def _public_file_records(directory: Path) -> dict[str, dict[str, object]]:
    return {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }


def _validate_html(path: Path) -> None:
    payload = path.read_bytes().lower()
    for marker in (b"<script", b"<link", b" src=", b"http://", b"https://", b"file://"):
        if marker in payload:
            raise PresentationModelError(
                f"public HTML contains external or executable content: {path.name}"
            )


def _validate_pptx(path: Path, *, expected_slides: int) -> None:
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if any(name.startswith("ppt/notesSlides/") for name in names):
                raise PresentationModelError("public PPTX contains speaker notes")
            slide_names = {
                name
                for name in names
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            }
            if len(slide_names) != expected_slides:
                raise PresentationModelError("public PPTX slide count does not match scene order")
            for name in names:
                if name.endswith(".rels") and b'TargetMode="External"' in archive.read(name):
                    raise PresentationModelError("public PPTX contains an external relationship")
    except BadZipFile as exc:
        raise PresentationModelError("public PPTX is not a valid Open XML package") from exc


def _validate_pdf(path: Path, *, expected_pages: int) -> None:
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-2048:]:
        raise PresentationModelError("public PDF structure is invalid")
    if b"/URI" in payload or b"/EmbeddedFile" in payload:
        raise PresentationModelError("public PDF contains a link or embedded file")
    if len(re.findall(rb"/Type\s*/Page\b", payload)) != expected_pages:
        raise PresentationModelError("public PDF page count does not match scene order")


def _validate_public_package(
    directory: Path,
    *,
    speaker_notes: tuple[str, ...],
    scene_count: int,
) -> None:
    _validate_html(directory / "index.html")
    _validate_html(directory / "handout.html")
    _validate_pdf(directory / "presentation.pdf", expected_pages=scene_count)
    _validate_pptx(directory / "presentation.pptx", expected_slides=scene_count)
    payload_parts = [path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()]
    with ZipFile(directory / "presentation.pptx") as archive:
        payload_parts.extend(
            archive.read(name)
            for name in sorted(archive.namelist())
            if name.endswith((".xml", ".rels"))
        )
    payload = b"\n".join(payload_parts)
    lowered = payload.lower()
    for marker in _FORBIDDEN_PUBLIC_BYTES:
        if marker in lowered:
            raise PresentationModelError(
                "public package contains presenter-only or external content"
            )
    for note in speaker_notes:
        encoded = note.encode("utf-8")
        if encoded in payload:
            raise PresentationModelError("speaker note leaked into public package")


def _manifest_with_digest(payload: dict[str, object]) -> dict[str, object]:
    manifest = dict(payload)
    manifest["manifest_digest"] = stable_digest(payload)
    return manifest


def build_presentation_packages(
    *,
    model_path: Path,
    variant_id: str,
    public_dir: Path,
    presenter_dir: Path,
    source_root: Path,
) -> dict[str, object]:
    """Build one public and one private package from the same validated model."""

    _ensure_disjoint(public_dir, presenter_dir)
    _refuse_destination(public_dir, label="public output directory")
    _refuse_destination(presenter_dir, label="presenter output directory")
    presentation = load_presentation(model_path, source_root=source_root)
    variant = presentation.variant_by_id.get(variant_id)
    if variant is None:
        raise PresentationModelError(f"unknown presentation variant: {variant_id}")

    public_parent = public_dir.parent
    presenter_parent = presenter_dir.parent
    public_temp = Path(tempfile.mkdtemp(prefix=f".{public_dir.name}.", dir=public_parent))
    presenter_temp = Path(tempfile.mkdtemp(prefix=f".{presenter_dir.name}.", dir=presenter_parent))
    public_published: tuple[int, int] | None = None
    presenter_published: tuple[int, int] | None = None
    try:
        metadata = public_metadata(presentation, variant)
        _write_bytes(
            public_temp / "index.html",
            render_public_html(presentation, variant, metadata).encode("utf-8"),
            mode=0o644,
        )
        _write_bytes(
            public_temp / "handout.html",
            render_handout_html(presentation, variant, metadata).encode("utf-8"),
            mode=0o644,
        )
        render_pdf(public_temp / "presentation.pdf", presentation, variant, metadata)
        os.chmod(public_temp / "presentation.pdf", 0o644)
        render_pptx(public_temp / "presentation.pptx", presentation, variant, metadata)
        os.chmod(public_temp / "presentation.pptx", 0o644)

        notes = tuple(
            note
            for scene_id in variant.scene_ids
            for note in presentation.scene_by_id[scene_id].speaker_notes
        )
        _validate_public_package(
            public_temp, speaker_notes=notes, scene_count=len(variant.scene_ids)
        )
        public_manifest = _manifest_with_digest(
            {
                "schema_version": PUBLIC_MANIFEST_VERSION,
                "presentation_id": presentation.presentation_id,
                "presentation_version": presentation.version,
                "variant_id": variant.identifier,
                "source_revision": presentation.source_revision,
                "artifact_metadata": metadata,
                "entrypoint": "index.html",
                "files": _public_file_records(public_temp),
                "boundaries": {
                    "contains_speaker_notes": False,
                    "contains_timing": False,
                    "contains_private_sources": False,
                    "contains_absolute_paths": False,
                    "network_dependencies": False,
                    "provider_mutation_attempted": False,
                },
            }
        )
        _write_json(public_temp / "manifest.json", public_manifest, mode=0o644)

        presenter = presenter_payload(presentation, variant)
        _write_json(presenter_temp / "presenter.json", presenter, mode=0o600)
        _write_bytes(
            presenter_temp / "presenter.html",
            render_presenter_html(presenter).encode("utf-8"),
            mode=0o600,
        )
        presenter_manifest = _manifest_with_digest(
            {
                "schema_version": PRESENTER_MANIFEST_VERSION,
                "presentation_id": presentation.presentation_id,
                "presentation_version": presentation.version,
                "variant_id": variant.identifier,
                "source_revision": presentation.source_revision,
                "model_digest": presentation.model_digest,
                "scene_order": list(variant.scene_ids),
                "planned_duration_seconds": variant.planned_duration_seconds,
                "files": _public_file_records(presenter_temp),
                "boundaries": presenter["boundaries"],
            }
        )
        _write_json(presenter_temp / "manifest.json", presenter_manifest, mode=0o600)
        os.chmod(public_temp, 0o755)
        os.chmod(presenter_temp, 0o700)
        public_identity = _directory_identity(public_temp)
        _publish_directory_noreplace(
            public_temp,
            public_dir,
            label="public output directory",
        )
        public_published = public_identity
        presenter_identity = _directory_identity(presenter_temp)
        _publish_directory_noreplace(
            presenter_temp,
            presenter_dir,
            label="presenter output directory",
        )
        presenter_published = presenter_identity
    except BaseException:
        shutil.rmtree(public_temp, ignore_errors=True)
        shutil.rmtree(presenter_temp, ignore_errors=True)
        _remove_published_directory(public_dir, public_published)
        _remove_published_directory(presenter_dir, presenter_published)
        raise

    return {
        "schema_version": "schauwerk-stage-build-receipt.v1",
        "ok": True,
        "presentation_id": presentation.presentation_id,
        "presentation_version": presentation.version,
        "variant_id": variant.identifier,
        "source_revision": presentation.source_revision,
        "model_digest": presentation.model_digest,
        "public_manifest_digest": public_manifest["manifest_digest"],
        "presenter_manifest_digest": presenter_manifest["manifest_digest"],
        "scene_count": len(variant.scene_ids),
        "planned_duration_seconds": variant.planned_duration_seconds,
        "public_output": str(public_dir),
        "presenter_output": str(presenter_dir),
        "network_dependencies": False,
        "provider_mutation_attempted": False,
    }
