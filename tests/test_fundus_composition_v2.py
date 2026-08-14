from __future__ import annotations

import copy
import json
from importlib.resources import files
from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from schauwerk.fundus.core import Fundus, FundusError, FundusPaths
from schauwerk.fundus.model import validate_recipe

SIMPLE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    b'<path fill="#000" d="M10 50 C20 10 80 10 90 50 C80 90 20 90 10 50 Z"/>'
    b"</svg>"
)


def _validate_instance(name: str, value: dict) -> None:
    schema = json.loads(
        files("schauwerk.schemas").joinpath(name).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(value)


def _texture_png() -> bytes:
    image = Image.new("RGBA", (16, 16), (184, 139, 58, 255))
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _composition_recipe() -> dict:
    return {
        "schema_version": "schauwerk-fundus-recipe.v2",
        "id": "mask-texture-v2",
        "operations": [
            {
                "transform": "sanitize_svg",
                "source_role": "trace_source",
                "output": {
                    "role": "mask",
                    "filename": "mask.svg",
                    "media_type": "image/svg+xml",
                },
                "parameters": {"profile": "svg.mask.v1"},
            },
            {
                "transform": "raster_normalize",
                "source_role": "texture_source",
                "output": {
                    "role": "texture",
                    "filename": "texture.png",
                    "media_type": "image/png",
                },
                "parameters": {"profile": "raster.png.rgba.v1"},
            },
        ],
    }


def _image_brief() -> dict:
    return {
        "schema_version": "schauwerk-fundus-image-brief.v1",
        "id": "fixture.composed.generate.v1",
        "intent": "reusable_asset",
        "asset_id": "fixture.composed",
        "family": "fixture.composition",
        "operation": "generate",
        "source_role": "trace_source",
        "desired_output_roles": ["mask"],
        "requirements": ["clear silhouette"],
        "forbidden": ["drop shadows"],
        "properties": {"mask_safe": True, "recolor_safe": True},
        "acceptance": {
            "visual_review_required": True,
            "inheritance": "none",
        },
    }


def _setup(tmp_path: Path) -> tuple[Fundus, Path, dict, dict]:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    (registry / "families").mkdir()
    (registry / "recipes" / "mask-texture-v2.json").write_text(
        json.dumps(_composition_recipe()), encoding="utf-8"
    )
    (registry / "families" / "fixture.composition.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.composition",
                "title": "Composition fixture",
                "tags": ["fixture", "composition"],
            }
        ),
        encoding="utf-8",
    )
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))

    trace_path = tmp_path / "trace.svg"
    trace_path.write_bytes(SIMPLE_SVG)
    brief_path = tmp_path / "image-brief.json"
    brief_path.write_text(json.dumps(_image_brief()), encoding="utf-8")
    prepared_brief = fundus.image_brief(brief_path)
    trace_ingest = fundus.ingest(
        trace_path,
        origin="chatgpt-images:composition-fixture",
        rights_status="owned",
        source_mode="generated",
        image_brief_path=brief_path,
    )

    texture_path = tmp_path / "texture.png"
    texture_path.write_bytes(_texture_png())
    texture_ingest = fundus.ingest(
        texture_path,
        origin="fixture:texture",
        rights_status="owned",
        source_mode="manual",
    )
    assert trace_ingest["image_brief_sha256"] == prepared_brief["image_brief_sha256"]
    return fundus, registry, trace_ingest, texture_ingest


def _declare_asset(registry: Path, trace: dict, texture: dict) -> None:
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.composed",
        "family": "fixture.composition",
        "recipe": "mask-texture-v2",
        "sources": [
            {
                "role": "trace_source",
                "sha256": trace["sha256"],
                "media_type": "image/svg+xml",
                "origin": "chatgpt-images:composition-fixture",
                "rights_status": "owned",
                "source_mode": "generated",
                "image_brief_sha256": trace["image_brief_sha256"],
            },
            {
                "role": "texture_source",
                "sha256": texture["sha256"],
                "media_type": "image/png",
                "origin": "fixture:texture",
                "rights_status": "owned",
                "source_mode": "manual",
            },
        ],
        "properties": {"mask_safe": True, "recolor_safe": True},
    }
    (registry / "assets" / "fixture.composed.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )


def test_composition_v2_build_preview_accept_and_package_are_digest_bound(
    tmp_path: Path,
) -> None:
    fundus, registry, trace, texture = _setup(tmp_path)
    _declare_asset(registry, trace, texture)
    recipe = _composition_recipe()
    validate_recipe(recipe)
    _validate_instance("fundus-recipe.v2.schema.json", recipe)

    first = fundus.build("fixture.composed")
    second = fundus.build("fixture.composed")
    assert first["schema_version"] == "schauwerk-fundus-build.v2"
    assert first["build_digest"] == second["build_digest"]
    assert [item["role"] for item in first["sources"]] == [
        "trace_source",
        "texture_source",
    ]
    assert [(item["role"], item["source_role"]) for item in first["outputs"]] == [
        ("mask", "trace_source"),
        ("texture", "texture_source"),
    ]
    assert first["sources"][0]["image_brief_sha256"] == trace["image_brief_sha256"]
    build_manifest = json.loads(
        (Path(first["build_dir"]) / "build.json").read_text(encoding="utf-8")
    )
    _validate_instance("fundus-build.v2.schema.json", build_manifest)
    assert (Path(first["build_dir"]) / "mask.svg").is_file()
    assert (Path(first["build_dir"]) / "texture.png").is_file()

    preview = fundus.preview("fixture.composed", build_digest=first["build_digest"])
    preview_html = Path(preview["preview_path"]).read_text(encoding="utf-8")
    assert "mask.svg" in preview_html
    assert "texture.png" in preview_html
    assert "data:image/png;base64," in preview_html
    assert preview["network_dependencies"] is False

    acceptance = fundus.accept(
        "fixture.composed",
        build_digest=first["build_digest"],
        reviewer="test:composition-v2",
        decision="accepted",
        reviewed_at="2026-08-14T12:00:00+00:00",
    )
    package = fundus.package(
        "fixture.composed",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    repeated = fundus.package(
        "fixture.composed",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    assert package["schema_version"] == "schauwerk-fundus-package.v2"
    assert package["package_digest"] == repeated["package_digest"]
    assert package["source_image_briefs"] == [
        {"role": "trace_source", "sha256": trace["image_brief_sha256"]}
    ]
    assert [(item["role"], item["source_role"]) for item in package["files"]] == [
        ("mask", "trace_source"),
        ("texture", "texture_source"),
    ]
    package_manifest = json.loads(
        (Path(package["package_dir"]) / "fundus-package.json").read_text(
            encoding="utf-8"
        )
    )
    _validate_instance("fundus-package.v2.schema.json", package_manifest)
    assert package["consumer_runtime_dependency"] is False


def test_recipe_v2_rejects_duplicate_output_identity() -> None:
    recipe = _composition_recipe()
    duplicate = copy.deepcopy(recipe["operations"][1])
    duplicate["output"]["filename"] = "texture-duplicate.png"
    recipe["operations"].append(duplicate)
    with pytest.raises(ValueError, match="output role is duplicated"):
        validate_recipe(recipe)

    recipe = _composition_recipe()
    recipe["operations"][1]["output"]["filename"] = "mask.svg"
    with pytest.raises(ValueError, match="output filename is duplicated"):
        validate_recipe(recipe)


def test_composition_v2_fails_before_build_when_required_source_is_missing(
    tmp_path: Path,
) -> None:
    fundus, registry, trace, texture = _setup(tmp_path)
    _declare_asset(registry, trace, texture)
    asset_path = registry / "assets" / "fixture.composed.json"
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    asset["sources"] = [asset["sources"][0]]
    asset_path.write_text(json.dumps(asset), encoding="utf-8")

    with pytest.raises(FundusError, match="recipe source role is absent: texture_source"):
        fundus.build("fixture.composed")
    build_root = fundus.root / "builds" / "fixture.composed"
    assert not build_root.exists()


def test_composition_v2_enforces_image_brief_output_roles_per_source(
    tmp_path: Path,
) -> None:
    fundus, registry, trace, texture = _setup(tmp_path)
    _declare_asset(registry, trace, texture)
    recipe_path = registry / "recipes" / "mask-texture-v2.json"
    recipe = _composition_recipe()
    recipe["operations"][0]["output"]["role"] = "outline"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    with pytest.raises(FundusError, match="does not authorize the build output role"):
        fundus.build("fixture.composed")
