from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, PngImagePlugin

from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.raster import normalize_raster


def _setup(tmp_path: Path) -> tuple[Fundus, Path]:
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    recipe = {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "raster-png-v1",
        "transform": "raster_normalize",
        "source_role": "original",
        "output": {
            "role": "raster",
            "filename": "raster.png",
            "media_type": "image/png",
        },
        "parameters": {"profile": "raster.png.rgba.v1"},
    }
    (registry / "recipes" / "raster-png-v1.json").write_text(
        json.dumps(recipe), encoding="utf-8"
    )
    return Fundus(FundusPaths(data_root=tmp_path / "data", registry_root=registry)), registry


def _source_png() -> tuple[bytes, Image.Image]:
    image = Image.new("RGBA", (96, 72), (244, 239, 226, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (8, 8, 62, 62),
        fill=(196, 153, 65, 210),
        outline=(20, 20, 20, 255),
        width=3,
    )
    draw.polygon(
        [(70, 6), (92, 36), (70, 66), (56, 36)],
        fill=(40, 80, 110, 180),
    )
    info = PngImagePlugin.PngInfo()
    info.add_text("fundus-test", "strip-me")
    output = BytesIO()
    image.save(output, "PNG", pnginfo=info, compress_level=6)
    return output.getvalue(), image


def test_raster_adapter_is_pixel_exact_deterministic_and_previewable(tmp_path: Path) -> None:
    fundus, registry = _setup(tmp_path)
    payload, reference = _source_png()
    source = tmp_path / "source.png"
    source.write_bytes(payload)
    ingest = fundus.ingest(source, origin="adapter-test", rights_status="owned")
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.raster",
        "recipe": "raster-png-v1",
        "sources": [
            {
                "role": "original",
                "sha256": ingest["sha256"],
                "media_type": "image/png",
                "origin": "adapter-test",
                "rights_status": "owned",
            }
        ],
    }
    (registry / "assets" / "fixture.raster.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )

    first = fundus.build("fixture.raster")
    second = fundus.build("fixture.raster")
    assert first["build_digest"] == second["build_digest"]
    assert first["toolchain"]["adapter"] == "pillow"
    assert first["toolchain"]["raster_profile"] == "raster.png.rgba.v1"

    output = Path(first["build_dir"]) / "raster.png"
    with Image.open(output) as normalized:
        assert normalized.convert("RGBA").tobytes() == reference.tobytes()
        assert "fundus-test" not in normalized.info

    preview = fundus.preview("fixture.raster", build_digest=first["build_digest"])
    html = Path(preview["preview_path"]).read_text(encoding="utf-8")
    assert "data:image/png;base64," in html
    assert "img-src data:" in html
    assert preview["network_dependencies"] is False

    acceptance = fundus.accept(
        "fixture.raster",
        build_digest=first["build_digest"],
        reviewer="test:adapter",
        decision="accepted",
        reviewed_at="2026-08-13T13:00:00+00:00",
    )
    package = fundus.package(
        "fixture.raster",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    packaged = Path(package["package_dir"]) / "assets" / "fixture-raster-raster.png"
    assert packaged.read_bytes() == output.read_bytes()
    assert package["consumer_runtime_dependency"] is False

def test_raster_adapter_rejects_hidden_exif_orientation() -> None:
    image = Image.new("RGB", (12, 8), "white")
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, "JPEG", quality=90, exif=exif)

    with pytest.raises(FundusError, match="EXIF orientation"):
        normalize_raster(output.getvalue(), profile="raster.png.rgba.v1")
