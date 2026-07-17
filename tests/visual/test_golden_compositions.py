from __future__ import annotations

import json
from pathlib import Path

from schauwerk.visual.preview import build_visual_preview, load_visual_preview
from schauwerk.visual.representation import (
    compile_representation_package,
    load_representation_input,
    route_representation,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = ROOT / "docs/operators/fixtures/golden"
CATALOGUE = GOLDEN_ROOT / "golden-compositions-v1.json"


def test_golden_compositions_compile_and_preview_without_blockers(tmp_path: Path) -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    assert catalogue["schema_version"] == "schauwerk-golden-compositions.v1"
    assert len(catalogue["compositions"]) == 3

    observed: dict[str, dict] = {}
    for entry in catalogue["compositions"]:
        source = GOLDEN_ROOT / entry["input"]
        package_dir = tmp_path / f"package-{entry['id']}"
        preview_dir = tmp_path / f"preview-{entry['id']}"

        model = load_representation_input(source)
        plan = route_representation(model)
        package = compile_representation_package(input_path=source, output_dir=package_dir)
        preview_receipt = build_visual_preview(
            package_dir=package_dir,
            output_dir=preview_dir,
        )
        preview = load_visual_preview(preview_dir / "preview.json")

        assert package["ok"] is True
        assert package["mutation_attempted"] is False
        assert preview_receipt["ok"] is True
        assert preview_receipt["mutation_attempted"] is False
        assert preview["blocker_count"] == 0
        assert plan["primary_format"] == entry["expected_primary_format"]
        assert entry["composition_axis"]
        assert entry["hierarchy"]
        assert entry["density"]
        assert entry["object_selection"]

        observed[entry["id"]] = {
            "intent": model["intent"],
            "primary_format": plan["primary_format"],
            "composition_axis": entry["composition_axis"],
            "hierarchy": entry["hierarchy"],
            "density": entry["density"],
            "object_selection": entry["object_selection"],
            "package_digest": package["package_digest"],
            "preview_digest": preview["preview_digest"],
        }

    assert len({item["intent"] for item in observed.values()}) == 3
    assert len({item["composition_axis"] for item in observed.values()}) == 3
    assert len({item["hierarchy"] for item in observed.values()}) == 3
    assert len({item["density"] for item in observed.values()}) == 3
    assert len({item["object_selection"] for item in observed.values()}) == 3
    assert len({item["package_digest"] for item in observed.values()}) == 3
    assert len({item["preview_digest"] for item in observed.values()}) == 3


def test_golden_catalogue_references_only_local_regular_json_files() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    referenced = []
    for entry in catalogue["compositions"]:
        source = GOLDEN_ROOT / entry["input"]
        assert source.parent == GOLDEN_ROOT
        assert source.suffix == ".json"
        assert source.is_file()
        assert not source.is_symlink()
        referenced.append(source.name)

    assert len(referenced) == len(set(referenced)) == 3
