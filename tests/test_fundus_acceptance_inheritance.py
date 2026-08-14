from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk import runner
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


def _recipe_v1(recipe_id: str = "mask-v1") -> dict:
    return {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": recipe_id,
        "transform": "sanitize_svg",
        "source_role": "trace_source",
        "output": {
            "role": "mask",
            "filename": "mask.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "svg.mask.v1"},
    }


def _recipe_v3(
    recipe_id: str = "mask-v3",
    *,
    filename: str = "mask.svg",
) -> dict:
    return {
        "schema_version": "schauwerk-fundus-recipe.v3",
        "id": recipe_id,
        "operations": [
            {
                "transform": "sanitize_svg",
                "source_role": "trace_source",
                "output": {
                    "role": "mask",
                    "filename": filename,
                    "media_type": "image/svg+xml",
                },
                "parameters": {"profile": "svg.mask.v1"},
            }
        ],
        "acceptance": {
            "inheritance": "identical_sources_and_outputs_only",
        },
    }


def _recipe_v2(recipe_id: str = "mask-v2") -> dict:
    recipe = _recipe_v3(recipe_id)
    recipe["schema_version"] = "schauwerk-fundus-recipe.v2"
    recipe.pop("acceptance")
    return recipe


def _setup(tmp_path: Path) -> tuple[Fundus, Path, dict]:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    (registry / "families").mkdir()
    (registry / "families" / "fixture.inheritance.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.inheritance",
                "title": "Acceptance inheritance fixture",
                "tags": ["fixture", "inheritance"],
            }
        ),
        encoding="utf-8",
    )
    (registry / "recipes" / "mask-v1.json").write_text(
        json.dumps(_recipe_v1()), encoding="utf-8"
    )
    source = tmp_path / "source.svg"
    source.write_bytes(SIMPLE_SVG)
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))
    ingest = fundus.ingest(
        source,
        origin="fixture:inheritance",
        rights_status="owned",
        source_mode="manual",
    )
    _write_asset(registry, ingest, recipe="mask-v1")
    return fundus, registry, ingest


def _write_asset(registry: Path, ingest: dict, *, recipe: str) -> None:
    source = {
        "role": "trace_source",
        "sha256": ingest["sha256"],
        "media_type": "image/svg+xml",
        "origin": ingest.get("origin", "fixture:inheritance"),
        "rights_status": "owned",
        "source_mode": ingest.get("source_mode", "manual"),
        **(
            {"image_brief_sha256": ingest["image_brief_sha256"]}
            if "image_brief_sha256" in ingest
            else {}
        ),
    }
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.inherited",
        "family": "fixture.inheritance",
        "recipe": recipe,
        "sources": [source],
        "properties": {"mask_safe": True, "recolor_safe": True},
    }
    (registry / "assets" / "fixture.inherited.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )


def _generated_setup(
    tmp_path: Path,
    *,
    inheritance: str,
) -> tuple[Fundus, Path, dict]:
    data_root = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    (registry / "families").mkdir()
    (registry / "families" / "fixture.inheritance.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.inheritance",
                "title": "Acceptance inheritance fixture",
                "tags": ["fixture", "inheritance"],
            }
        ),
        encoding="utf-8",
    )
    (registry / "recipes" / "mask-v1.json").write_text(
        json.dumps(_recipe_v1()), encoding="utf-8"
    )
    source_path = tmp_path / "generated-source.svg"
    source_path.write_bytes(SIMPLE_SVG)
    fundus = Fundus(FundusPaths(data_root=data_root, registry_root=registry))
    brief = {
        "schema_version": "schauwerk-fundus-image-brief.v1",
        "id": "fixture.inherited.generate.v1",
        "intent": "reusable_asset",
        "asset_id": "fixture.inherited",
        "family": "fixture.inheritance",
        "operation": "generate",
        "source_role": "trace_source",
        "desired_output_roles": ["mask"],
        "requirements": ["clear silhouette"],
        "forbidden": [],
        "properties": {"mask_safe": True, "recolor_safe": True},
        "acceptance": {
            "visual_review_required": True,
            "inheritance": inheritance,
        },
    }
    brief_path = tmp_path / "image-brief.json"
    brief_path.write_text(json.dumps(brief), encoding="utf-8")
    fundus.image_brief(brief_path)
    ingest = fundus.ingest(
        source_path,
        origin="chatgpt-images:inheritance-fixture",
        rights_status="owned",
        source_mode="generated",
        image_brief_path=brief_path,
    )
    _write_asset(registry, ingest, recipe="mask-v1")
    return fundus, registry, ingest


def _direct_parent(
    fundus: Fundus,
) -> tuple[dict, dict]:
    build = fundus.build("fixture.inherited")
    acceptance = fundus.accept(
        "fixture.inherited",
        build_digest=build["build_digest"],
        reviewer="human:test-reviewer",
        decision="accepted",
        note="direct visual acceptance fixture",
        reviewed_at="2026-08-14T13:00:00+00:00",
    )
    return build, acceptance


def _candidate(
    fundus: Fundus,
    registry: Path,
    ingest: dict,
    *,
    recipe: dict | None = None,
) -> dict:
    recipe = recipe or _recipe_v3()
    (registry / "recipes" / f"{recipe['id']}.json").write_text(
        json.dumps(recipe), encoding="utf-8"
    )
    _write_asset(registry, ingest, recipe=recipe["id"])
    return fundus.build("fixture.inherited")


def test_identical_source_and_output_can_inherit_direct_acceptance_and_package(
    tmp_path: Path,
) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(fundus, registry, ingest)

    recipe = _recipe_v3()
    validate_recipe(recipe)
    _validate_instance("fundus-recipe.v3.schema.json", recipe)
    assert candidate["build_digest"] != parent_build["build_digest"]
    assert candidate["outputs"][0]["sha256"] == parent_build["outputs"][0]["sha256"]

    inherited = fundus.inherit_acceptance(
        "fixture.inherited",
        build_digest=candidate["build_digest"],
        parent_build_digest=parent_build["build_digest"],
        parent_acceptance_digest=parent_acceptance["acceptance_digest"],
        inherited_by="operator:test",
        inherited_at="2026-08-14T14:00:00+00:00",
    )
    assert inherited["schema_version"] == "schauwerk-fundus-acceptance.v2"
    assert inherited["acceptance_mode"] == "inherited"
    assert inherited["inheritance_basis"] == "identical_sources_and_outputs_only"
    assert inherited["parent_acceptance_digest"] == parent_acceptance["acceptance_digest"]
    assert inherited["inherited_by_identity_authenticated"] is False
    _validate_instance(
        "fundus-acceptance.v2.schema.json",
        json.loads(Path(inherited["acceptance_path"]).read_text(encoding="utf-8")),
    )

    package = fundus.package(
        "fixture.inherited",
        build_digest=candidate["build_digest"],
        acceptance_digest=inherited["acceptance_digest"],
    )
    assert package["consumer_runtime_dependency"] is False
    assert package["acceptance_digest"] == inherited["acceptance_digest"]


def test_generated_source_requires_bound_image_brief_inheritance_opt_in(
    tmp_path: Path,
) -> None:
    fundus, registry, ingest = _generated_setup(tmp_path, inheritance="none")
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(fundus, registry, ingest)

    with pytest.raises(
        FundusError, match="bound image brief does not permit acceptance inheritance"
    ):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=candidate["build_digest"],
            parent_build_digest=parent_build["build_digest"],
            parent_acceptance_digest=parent_acceptance["acceptance_digest"],
            inherited_by="operator:test",
        )


def test_generated_source_can_inherit_when_bound_brief_allows_it(
    tmp_path: Path,
) -> None:
    fundus, registry, ingest = _generated_setup(
        tmp_path, inheritance="deterministic_recipe_only"
    )
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(fundus, registry, ingest)

    inherited = fundus.inherit_acceptance(
        "fixture.inherited",
        build_digest=candidate["build_digest"],
        parent_build_digest=parent_build["build_digest"],
        parent_acceptance_digest=parent_acceptance["acceptance_digest"],
        inherited_by="operator:test",
        inherited_at="2026-08-14T14:00:00+00:00",
    )
    assert inherited["schema_version"] == "schauwerk-fundus-acceptance.v2"


def test_inheritance_requires_explicit_recipe_v3_policy(tmp_path: Path) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(fundus, registry, ingest, recipe=_recipe_v2())

    with pytest.raises(FundusError, match="does not permit acceptance inheritance"):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=candidate["build_digest"],
            parent_build_digest=parent_build["build_digest"],
            parent_acceptance_digest=parent_acceptance["acceptance_digest"],
            inherited_by="operator:test",
        )


def test_changed_source_revision_cannot_inherit_even_if_recipe_is_same(
    tmp_path: Path,
) -> None:
    fundus, registry, _ = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)

    changed = tmp_path / "changed.svg"
    changed.write_bytes(SIMPLE_SVG.replace(b"><path", b">\n<path"))
    changed_ingest = fundus.ingest(
        changed,
        origin="fixture:changed-revision",
        rights_status="owned",
        source_mode="manual",
    )
    candidate = _candidate(fundus, registry, changed_ingest)

    with pytest.raises(FundusError, match="source bindings differ"):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=candidate["build_digest"],
            parent_build_digest=parent_build["build_digest"],
            parent_acceptance_digest=parent_acceptance["acceptance_digest"],
            inherited_by="operator:test",
        )


def test_changed_output_identity_cannot_inherit_same_bytes(tmp_path: Path) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(
        fundus,
        registry,
        ingest,
        recipe=_recipe_v3("mask-renamed-v3", filename="renamed-mask.svg"),
    )
    assert candidate["outputs"][0]["sha256"] == parent_build["outputs"][0]["sha256"]

    with pytest.raises(FundusError, match="output bindings differ"):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=candidate["build_digest"],
            parent_build_digest=parent_build["build_digest"],
            parent_acceptance_digest=parent_acceptance["acceptance_digest"],
            inherited_by="operator:test",
        )


def test_rejected_parent_cannot_be_inherited(tmp_path: Path) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build = fundus.build("fixture.inherited")
    rejected = fundus.accept(
        "fixture.inherited",
        build_digest=parent_build["build_digest"],
        reviewer="human:test-reviewer",
        decision="rejected",
        reviewed_at="2026-08-14T13:00:00+00:00",
    )
    candidate = _candidate(fundus, registry, ingest)

    with pytest.raises(FundusError, match="directly reviewed accepted parent"):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=candidate["build_digest"],
            parent_build_digest=parent_build["build_digest"],
            parent_acceptance_digest=rejected["acceptance_digest"],
            inherited_by="operator:test",
        )


def test_inherited_acceptance_cannot_be_parent_of_another_inheritance(
    tmp_path: Path,
) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)
    first_candidate = _candidate(fundus, registry, ingest)
    first_inherited = fundus.inherit_acceptance(
        "fixture.inherited",
        build_digest=first_candidate["build_digest"],
        parent_build_digest=parent_build["build_digest"],
        parent_acceptance_digest=parent_acceptance["acceptance_digest"],
        inherited_by="operator:first",
        inherited_at="2026-08-14T14:00:00+00:00",
    )

    second_candidate = _candidate(
        fundus,
        registry,
        ingest,
        recipe=_recipe_v3("mask-v3-second"),
    )
    with pytest.raises(FundusError, match="cannot be an inheritance parent"):
        fundus.inherit_acceptance(
            "fixture.inherited",
            build_digest=second_candidate["build_digest"],
            parent_build_digest=first_candidate["build_digest"],
            parent_acceptance_digest=first_inherited["acceptance_digest"],
            inherited_by="operator:second",
        )


def test_cli_accept_inherit_uses_operator_not_reviewer(tmp_path: Path, capsys) -> None:
    fundus, registry, ingest = _setup(tmp_path)
    parent_build, parent_acceptance = _direct_parent(fundus)
    candidate = _candidate(fundus, registry, ingest)

    code = runner.main(
        [
            "fundus",
            "accept-inherit",
            "fixture.inherited",
            "--build",
            candidate["build_digest"],
            "--parent-build",
            parent_build["build_digest"],
            "--parent-acceptance",
            parent_acceptance["acceptance_digest"],
            "--inherited-by",
            "operator:cli",
            "--data-root",
            str(fundus.root),
            "--registry-root",
            str(registry),
            "--json",
        ]
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "schauwerk-fundus-acceptance.v2"
    assert result["inherited_by"] == "operator:cli"
    assert "reviewer" not in result
