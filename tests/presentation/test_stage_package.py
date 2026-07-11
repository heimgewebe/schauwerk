from __future__ import annotations

import json
import stat
from pathlib import Path
from zipfile import ZipFile

import pytest

from schauwerk.presentation.model import PresentationModelError
from schauwerk.presentation.package import build_presentation_packages

from .test_stage_model import write_model


def _tree_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _build(root: Path, suffix: str):
    model = write_model(root)
    public = root / f"public-{suffix}"
    presenter = root / f"presenter-{suffix}"
    receipt = build_presentation_packages(
        model_path=model,
        variant_id="fixture",
        public_dir=public,
        presenter_dir=presenter,
        source_root=root,
    )
    return receipt, public, presenter


def test_packages_are_deterministic_separated_and_offline(tmp_path: Path) -> None:
    receipt_a, public_a, presenter_a = _build(tmp_path, "a")
    receipt_b, public_b, presenter_b = _build(tmp_path, "b")

    assert _tree_bytes(public_a) == _tree_bytes(public_b)
    assert _tree_bytes(presenter_a) == _tree_bytes(presenter_b)
    assert receipt_a["public_manifest_digest"] == receipt_b["public_manifest_digest"]
    assert receipt_a["presenter_manifest_digest"] == receipt_b["presenter_manifest_digest"]

    public_payload = b"\n".join(_tree_bytes(public_a).values())
    presenter_payload = b"\n".join(_tree_bytes(presenter_a).values())
    assert b"SECRET-NOTE-ALPHA" not in public_payload
    assert b"SECRET-NOTE-BETA" not in public_payload
    assert b"SECRET-NOTE-ALPHA" in presenter_payload
    assert b"duration_seconds" in presenter_payload

    manifest = json.loads((public_a / "manifest.json").read_text(encoding="utf-8"))
    metadata = manifest["artifact_metadata"]
    assert manifest["schema_version"] == "schauwerk-stage-public-package.v1"
    assert metadata["scene_order"] == ["first", "second"]
    assert len(metadata["public_projection_sha256"]) == 64
    assert manifest["boundaries"] == {
        "contains_absolute_paths": False,
        "contains_private_sources": False,
        "contains_speaker_notes": False,
        "contains_timing": False,
        "network_dependencies": False,
        "provider_mutation_attempted": False,
    }
    for path in (public_a / "index.html", public_a / "handout.html"):
        lowered = path.read_text(encoding="utf-8").lower()
        assert "<script" not in lowered
        assert "http://" not in lowered
        assert "https://" not in lowered
        assert "file://" not in lowered
        assert "content-security-policy" in lowered
        assert "default-src 'none'" in lowered


def test_pdf_and_pptx_preserve_structure_without_notes_or_external_links(tmp_path: Path) -> None:
    _, public, _ = _build(tmp_path, "formats")
    pdf = (public / "presentation.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert b"/URI" not in pdf
    assert b"/EmbeddedFile" not in pdf

    with ZipFile(public / "presentation.pptx") as archive:
        names = archive.namelist()
        assert (
            len(
                [
                    name
                    for name in names
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ]
            )
            == 2
        )
        assert not any(name.startswith("ppt/notesSlides/") for name in names)
        assert not any(
            b'TargetMode="External"' in archive.read(name)
            for name in names
            if name.endswith(".rels")
        )
        core = archive.read("docProps/core.xml")
        assert b"public_projection_sha256=" in core
        assert b"visible_content_sha256=" in core


def test_presenter_permissions_and_destination_guards(tmp_path: Path) -> None:
    model = write_model(tmp_path)
    public = tmp_path / "public"
    presenter = tmp_path / "presenter"
    build_presentation_packages(
        model_path=model,
        variant_id="fixture",
        public_dir=public,
        presenter_dir=presenter,
        source_root=tmp_path,
    )
    assert stat.S_IMODE(presenter.stat().st_mode) == 0o700
    assert stat.S_IMODE((presenter / "presenter.json").stat().st_mode) == 0o600

    with pytest.raises(PresentationModelError, match="already exists"):
        build_presentation_packages(
            model_path=model,
            variant_id="fixture",
            public_dir=public,
            presenter_dir=tmp_path / "presenter-new",
            source_root=tmp_path,
        )
    with pytest.raises(PresentationModelError, match="disjoint"):
        build_presentation_packages(
            model_path=model,
            variant_id="fixture",
            public_dir=tmp_path / "nested",
            presenter_dir=tmp_path / "nested" / "private",
            source_root=tmp_path,
        )


def test_build_does_not_require_network(tmp_path: Path, monkeypatch) -> None:
    import socket

    model = write_model(tmp_path)

    def forbidden_socket(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    receipt = build_presentation_packages(
        model_path=model,
        variant_id="fixture",
        public_dir=tmp_path / "public-offline",
        presenter_dir=tmp_path / "presenter-offline",
        source_root=tmp_path,
    )
    assert receipt["network_dependencies"] is False


def test_overfull_scene_fails_instead_of_clipping(tmp_path: Path) -> None:
    import json

    model = write_model(tmp_path)
    data = json.loads(model.read_text(encoding="utf-8"))
    data["scenes"][0]["visible"][0]["text"] = "word " * 350
    model.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PresentationModelError, match="exceeds the deterministic PDF layout"):
        build_presentation_packages(
            model_path=model,
            variant_id="fixture",
            public_dir=tmp_path / "public-overfull",
            presenter_dir=tmp_path / "presenter-overfull",
            source_root=tmp_path,
        )
    assert not (tmp_path / "public-overfull").exists()
    assert not (tmp_path / "presenter-overfull").exists()


def test_visible_text_and_order_exist_in_html_pdf_and_pptx(tmp_path: Path) -> None:
    _, public, _ = _build(tmp_path, "visible-content")
    expected = (
        "First scene",
        "Visible statement one.",
        "Second scene",
        "Visible item A",
        "Visible item B",
    )
    html_payload = (public / "index.html").read_bytes()
    pdf_payload = (public / "presentation.pdf").read_bytes()
    with ZipFile(public / "presentation.pptx") as archive:
        pptx_payload = b"\n".join(
            archive.read(name)
            for name in sorted(archive.namelist())
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
    for payload in (html_payload, pdf_payload, pptx_payload):
        positions = [payload.index(value.encode("utf-8")) for value in expected]
        assert positions == sorted(positions)


def test_unsupported_glyph_and_overwide_token_fail_closed(tmp_path: Path) -> None:
    model = write_model(tmp_path)
    data = json.loads(model.read_text(encoding="utf-8"))
    data["scenes"][0]["title"] = "Unsupported rocket 🚀"
    model.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PresentationModelError, match="unsupported by the deterministic PDF font"):
        build_presentation_packages(
            model_path=model,
            variant_id="fixture",
            public_dir=tmp_path / "public-glyph",
            presenter_dir=tmp_path / "presenter-glyph",
            source_root=tmp_path,
        )

    model = write_model(tmp_path)
    data = json.loads(model.read_text(encoding="utf-8"))
    data["scenes"][0]["visible"][0]["text"] = "W" * 500
    model.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PresentationModelError, match="token wider"):
        build_presentation_packages(
            model_path=model,
            variant_id="fixture",
            public_dir=tmp_path / "public-token",
            presenter_dir=tmp_path / "presenter-token",
            source_root=tmp_path,
        )
