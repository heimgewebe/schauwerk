from __future__ import annotations

import json
from pathlib import Path

import pytest

from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.model import validate_recipe


def test_recipe_contract_rejects_crossed_adapter_profiles() -> None:
    raster = {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "wrong-raster",
        "transform": "raster_normalize",
        "source_role": "original",
        "output": {
            "role": "raster",
            "filename": "raster.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "raster.png.rgba.v1"},
    }
    with pytest.raises(ValueError, match="image/png"):
        validate_recipe(raster)

    trace = {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "wrong-trace",
        "transform": "trace_vtracer",
        "source_role": "trace_source",
        "output": {
            "role": "vector",
            "filename": "vector.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "svg.decorative.v1"},
    }
    with pytest.raises(ValueError, match="trace profile"):
        validate_recipe(trace)


def test_doctor_reports_selected_adapter_profiles(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
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
    fundus = Fundus(FundusPaths(data_root=tmp_path / "data", registry_root=registry))
    result = fundus.doctor()
    assert result["ok"] is True
    assert result["raster_profiles"] == ["raster.png.rgba.v1"]
    assert result["trace_profiles"] == ["trace.vtracer.color.v1"]
    assert result["adapters"]["raster"]["implementation"] == "pillow"
    assert result["adapters"]["trace"]["required_version"] == "0.6.15"
