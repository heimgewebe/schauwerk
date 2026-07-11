from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from schauwerk.presentation.model import PresentationModelError, load_presentation


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_model(root: Path) -> Path:
    (root / "source.txt").write_text("public source\n", encoding="utf-8")
    (root / "internal.txt").write_text("internal guidance\n", encoding="utf-8")
    model = {
        "schema_version": "schauwerk-presentation.v1",
        "presentation_id": "fixture-deck",
        "version": "1.0.0",
        "title": "Fixture deck",
        "source_revision": "revision-1",
        "sources": [
            {
                "id": "primary",
                "label": "Public source",
                "revision": "r1",
                "sha256": _sha(root / "source.txt"),
                "visibility": "public",
                "artifact": "source.txt",
            },
            {
                "id": "guidance",
                "label": "Internal guidance",
                "revision": "r1",
                "sha256": _sha(root / "internal.txt"),
                "visibility": "internal",
                "artifact": "internal.txt",
            },
        ],
        "output_profiles": [
            {
                "id": "public-default",
                "visibility": "public",
                "formats": ["handout", "html", "pdf", "pptx"],
                "include_speaker_notes": False,
                "include_timing": False,
                "include_private_sources": False,
            },
            {
                "id": "presenter-default",
                "visibility": "private",
                "formats": ["html", "json"],
                "include_speaker_notes": True,
                "include_timing": True,
                "include_private_sources": True,
            },
        ],
        "variants": [
            {
                "id": "fixture",
                "audience": "Test audience",
                "title": "Fixture deck",
                "scene_ids": ["first", "second"],
                "planned_duration_seconds": 150,
                "public_profile_id": "public-default",
                "presenter_profile_id": "presenter-default",
            }
        ],
        "scenes": [
            {
                "id": "first",
                "title": "First scene",
                "visible": [
                    {
                        "kind": "paragraph",
                        "text": "Visible statement one.",
                        "items": [],
                        "source_ids": ["primary"],
                    }
                ],
                "speaker_notes": ["SECRET-NOTE-ALPHA"],
                "duration_seconds": 60,
                "source_ids": ["primary", "guidance"],
            },
            {
                "id": "second",
                "title": "Second scene",
                "visible": [
                    {
                        "kind": "bullets",
                        "text": None,
                        "items": ["Visible item A", "Visible item B"],
                        "source_ids": ["primary"],
                    }
                ],
                "speaker_notes": ["SECRET-NOTE-BETA"],
                "duration_seconds": 90,
                "source_ids": ["primary"],
            },
        ],
    }
    path = root / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    return path


def _change(path: Path, callback) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    callback(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_model_binds_sources_order_and_timing(tmp_path: Path) -> None:
    path = write_model(tmp_path)
    model = load_presentation(path, source_root=tmp_path)
    variant = model.variant_by_id["fixture"]
    assert variant.scene_ids == ("first", "second")
    assert variant.planned_duration_seconds == 150
    assert model.source_by_id["guidance"].visibility == "internal"
    assert len(model.model_digest) == 64


def test_model_rejects_unknown_fields_and_digest_drift(tmp_path: Path) -> None:
    path = write_model(tmp_path)
    _change(path, lambda data: data.update({"unexpected": True}))
    with pytest.raises(PresentationModelError, match="unknown field"):
        load_presentation(path, source_root=tmp_path)

    path = write_model(tmp_path)
    (tmp_path / "source.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(PresentationModelError, match="digest mismatch"):
        load_presentation(path, source_root=tmp_path)


def test_model_rejects_private_visible_source_and_bad_total(tmp_path: Path) -> None:
    path = write_model(tmp_path)

    def expose_internal(data):
        data["scenes"][0]["visible"][0]["source_ids"] = ["guidance"]

    _change(path, expose_internal)
    with pytest.raises(PresentationModelError, match="exposes non-public"):
        load_presentation(path, source_root=tmp_path)

    path = write_model(tmp_path)
    _change(path, lambda data: data["variants"][0].update({"planned_duration_seconds": 151}))
    with pytest.raises(PresentationModelError, match="does not match scene total"):
        load_presentation(path, source_root=tmp_path)


def test_model_rejects_network_paths_secrets_and_symlinks(tmp_path: Path) -> None:
    path = write_model(tmp_path)
    _change(path, lambda data: data["scenes"][0].update({"title": "See https://example.invalid"}))
    with pytest.raises(PresentationModelError, match="URL"):
        load_presentation(path, source_root=tmp_path)

    path = write_model(tmp_path)
    _change(path, lambda data: data["scenes"][0].update({"title": "api_key=not-allowed"}))
    with pytest.raises(PresentationModelError, match="secret-like"):
        load_presentation(path, source_root=tmp_path)

    path = write_model(tmp_path)
    target = tmp_path / "actual.txt"
    target.write_text("public source\n", encoding="utf-8")
    (tmp_path / "source.txt").unlink()
    (tmp_path / "source.txt").symlink_to(target)
    with pytest.raises(PresentationModelError, match="symlink"):
        load_presentation(path, source_root=tmp_path)


def test_presenter_profile_must_match_private_source_projection(tmp_path: Path) -> None:
    path = write_model(tmp_path)

    def exclude_private_sources(data):
        data["output_profiles"][1]["include_private_sources"] = False

    _change(path, exclude_private_sources)
    with pytest.raises(PresentationModelError, match="private sources"):
        load_presentation(path, source_root=tmp_path)
