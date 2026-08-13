from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.svg import sanitize_svg


def _source_png() -> bytes:
    image = Image.new("RGB", (96, 72), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 62, 62), fill=(196, 153, 65), outline=(20, 20, 20), width=3)
    draw.polygon([(70, 6), (92, 36), (70, 66), (56, 36)], fill=(40, 80, 110))
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_vtracer_adapter_is_deterministic_sanitized_and_digest_bound(tmp_path: Path) -> None:
    pytest.importorskip("vtracer")
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    recipe = {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "vtracer-color-v1",
        "transform": "trace_vtracer",
        "source_role": "trace_source",
        "output": {
            "role": "vector",
            "filename": "vector.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "trace.vtracer.color.v1"},
    }
    (registry / "recipes" / "vtracer-color-v1.json").write_text(
        json.dumps(recipe), encoding="utf-8"
    )
    fundus = Fundus(FundusPaths(data_root=tmp_path / "data", registry_root=registry))
    source = tmp_path / "trace-source.png"
    source.write_bytes(_source_png())
    ingest = fundus.ingest(source, origin="adapter-test", rights_status="owned")
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.trace",
        "recipe": "vtracer-color-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": ingest["sha256"],
                "media_type": "image/png",
                "origin": "adapter-test",
                "rights_status": "owned",
            }
        ],
    }
    (registry / "assets" / "fixture.trace.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )

    first = fundus.build("fixture.trace")
    second = fundus.build("fixture.trace")
    assert first["build_digest"] == second["build_digest"]
    assert first["outputs"] == second["outputs"]
    assert first["toolchain"]["adapter"] == "vtracer"
    assert first["toolchain"]["vtracer"] == "0.6.15"
    assert first["toolchain"]["trace_input_adapter"] == "pillow"
    assert first["toolchain"]["pillow"] == "12.2.0"
    assert first["toolchain"]["path_precision"] == 3

    output = Path(first["build_dir"]) / "vector.svg"
    svg = output.read_bytes()
    assert sanitize_svg(svg, profile="svg.decorative.v1") == svg
    root = ET.fromstring(svg)
    assert root.attrib["viewBox"] == "0 0 96 72"
    assert "version" not in root.attrib
    assert svg.count(b"<path") > 0

    preview = fundus.preview("fixture.trace", build_digest=first["build_digest"])
    assert preview["network_dependencies"] is False
    acceptance = fundus.accept(
        "fixture.trace",
        build_digest=first["build_digest"],
        reviewer="test:adapter",
        decision="accepted",
        reviewed_at="2026-08-13T13:00:00+00:00",
    )
    package = fundus.package(
        "fixture.trace",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    packaged = Path(package["package_dir"]) / "assets" / "fixture-trace-vector.svg"
    assert packaged.read_bytes() == svg
