from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from schauwerk import runner
from schauwerk.fundus.core import Fundus, FundusError, FundusPaths
from schauwerk.fundus.model import canonical_json, load_json
from schauwerk.fundus.svg import (
    MAX_ATTRIBUTE_CHARS,
    MAX_PATH_CHARS,
    sanitize_svg,
)

SIMPLE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    b'<path fill="#000" d="M10 50 C20 10 80 10 90 50 C80 90 20 90 10 50 Z"/>'
    b"</svg>"
)


def _recipe() -> dict:
    return {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "svg-mask-v1",
        "transform": "sanitize_svg",
        "source_role": "trace_source",
        "output": {
            "role": "mask",
            "filename": "mask.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "svg.mask.v1"},
    }


def _family() -> dict:
    return {
        "schema_version": "schauwerk-fundus-family.v1",
        "id": "fixture.simple",
        "title": "Simple fixture family",
        "tags": ["fixture"],
    }


def _setup(tmp_path: Path) -> tuple[Fundus, Path, Path]:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    (registry / "families").mkdir()
    (registry / "recipes" / "svg-mask-v1.json").write_text(
        json.dumps(_recipe()), encoding="utf-8"
    )
    (registry / "families" / "fixture.simple.json").write_text(
        json.dumps(_family()), encoding="utf-8"
    )
    source = tmp_path / "source.svg"
    source.write_bytes(SIMPLE_SVG)
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))
    return fundus, registry, source


def _validate_instance(name: str, value: dict) -> None:
    schema_root = files("schauwerk.schemas")
    schema = json.loads(
        schema_root.joinpath(name).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(value)


def _declare_asset(registry: Path, sha256: str) -> None:
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.simple-ornament",
        "family": "fixture.simple",
        "recipe": "svg-mask-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": sha256,
                "media_type": "image/svg+xml",
                "origin": "test-fixture",
                "rights_status": "owned",
            }
        ],
        "properties": {
            "mirror_safe": True,
            "rotate_safe": True,
            "recolor_safe": True,
            "mask_safe": True,
        },
    }
    (registry / "assets" / "fixture.simple-ornament.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )


def test_fundus_walking_skeleton_is_digest_bound_and_idempotent(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    ingest = fundus.ingest(source, origin="test-fixture", rights_status="owned")
    repeated_ingest = fundus.ingest(
        source, origin="test-fixture", rights_status="owned"
    )
    assert repeated_ingest == ingest
    assert ingest["media_type"] == "image/svg+xml"
    _validate_instance("fundus-ingest.v1.schema.json", ingest)

    object_path = fundus.root / ingest["object_relpath"]
    assert object_path.read_bytes() == SIMPLE_SVG
    assert object_path.stat().st_mode & 0o777 == 0o600

    _declare_asset(registry, ingest["sha256"])
    first = fundus.build("fixture.simple-ornament")
    second = fundus.build("fixture.simple-ornament")
    assert first["build_digest"] == second["build_digest"]
    assert first["outputs"] == second["outputs"]
    build_manifest = json.loads(
        (Path(first["build_dir"]) / "build.json").read_text(encoding="utf-8")
    )
    _validate_instance("fundus-build.v1.schema.json", build_manifest)

    preview = fundus.preview(
        "fixture.simple-ornament", build_digest=first["build_digest"]
    )
    assert preview["network_dependencies"] is False
    assert preview["aesthetic_quality_established"] is False
    preview_path = Path(preview["preview_path"])
    assert preview_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    preview_manifest = json.loads(
        preview_path.with_name("preview.json").read_text(encoding="utf-8")
    )
    _validate_instance("fundus-preview.v1.schema.json", preview_manifest)

    acceptance = fundus.accept(
        "fixture.simple-ornament",
        build_digest=first["build_digest"],
        reviewer="test:fixture",
        decision="accepted",
        note="deterministic test acceptance only",
        reviewed_at="2026-08-13T10:00:00+00:00",
    )
    acceptance_manifest = json.loads(
        Path(acceptance["acceptance_path"]).read_text(encoding="utf-8")
    )
    _validate_instance(
        "fundus-acceptance.v1.schema.json", acceptance_manifest
    )
    package = fundus.package(
        "fixture.simple-ornament",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    repeated_package = fundus.package(
        "fixture.simple-ornament",
        build_digest=first["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    assert package["package_digest"] == repeated_package["package_digest"]
    assert package["consumer_runtime_dependency"] is False

    package_dir = Path(package["package_dir"])
    package_manifest_path = package_dir / "fundus-package.json"
    assert package_manifest_path.is_file()
    package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    _validate_instance("fundus-package.v1.schema.json", package_manifest)
    assert (package_dir / "SHA256SUMS").is_file()
    assert (package_dir / "assets" / "fixture-simple-ornament-mask.svg").is_file()

    doctor = fundus.doctor()
    assert doctor["ok"] is True
    assert doctor["miro_independent"] is True
    assert doctor["cross_repo_mutation_authority"] is False
    assert doctor["object_store_authoritative"] is False
    assert doctor["registry"]["families"] == ["fixture.simple"]


def test_invalid_ingest_metadata_does_not_create_state_or_object(tmp_path: Path) -> None:
    fundus, _, source = _setup(tmp_path)
    with pytest.raises(FundusError, match="origin"):
        fundus.ingest(source, origin="   ", rights_status="owned")
    assert fundus.root.exists() is False


def test_fundus_rejects_symlink_parent_paths(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    source = real / "source.svg"
    source.write_bytes(SIMPLE_SVG)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    fundus = Fundus(
        FundusPaths(
            data_root=tmp_path / "data",
            registry_root=tmp_path / "registry",
        )
    )
    with pytest.raises(FundusError, match="symlink"):
        fundus.ingest(linked / "source.svg")


def test_invalid_lifecycle_reads_do_not_create_state(tmp_path: Path) -> None:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))

    with pytest.raises(FundusError, match="not declared"):
        fundus.build("fixture.missing")
    assert data.exists() is False

    missing_digest = "0" * 64
    with pytest.raises(FundusError, match="does not exist"):
        fundus.accept(
            "fixture.missing",
            build_digest=missing_digest,
            reviewer="test:fixture",
            decision="accepted",
        )
    assert data.exists() is False

    with pytest.raises(FundusError, match="does not exist"):
        fundus.package(
            "fixture.missing",
            build_digest=missing_digest,
            acceptance_digest="1" * 64,
        )
    assert data.exists() is False


def test_fundus_rejects_conflicting_provenance_for_identical_bytes(
    tmp_path: Path,
) -> None:
    fundus, _, source = _setup(tmp_path)
    fundus.ingest(source, origin="first", rights_status="owned")
    with pytest.raises(FundusError, match="conflicting origin"):
        fundus.ingest(source, origin="second", rights_status="owned")


def test_fundus_rejects_active_external_or_overscoped_svg() -> None:
    with pytest.raises(ValueError, match="script"):
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            b"<script>alert(1)</script></svg>",
            profile="svg.mask.v1",
        )
    with pytest.raises(ValueError, match="external|active"):
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            b'<path fill="https://example.invalid/x" d="M0 0L1 1"/></svg>',
            profile="svg.mask.v1",
        )
    with pytest.raises(ValueError, match="viewBox"):
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>',
            profile="svg.mask.v1",
        )


def test_fundus_uses_dedicated_budget_for_svg_path_data() -> None:
    long_path = "M0 0 " + "L1 1 " * ((MAX_ATTRIBUTE_CHARS // 5) + 200)
    assert MAX_ATTRIBUTE_CHARS < len(long_path) < MAX_PATH_CHARS
    sanitized = sanitize_svg(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            f'<path d="{long_path}"/></svg>'
        ).encode(),
        profile="svg.mask.v1",
    )
    assert b"<path" in sanitized

    oversized_generic_attribute = "x" * (MAX_ATTRIBUTE_CHARS + 1)
    with pytest.raises(ValueError, match="attribute value"):
        sanitize_svg(
            (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                f'<path fill="{oversized_generic_attribute}" d="M0 0L1 1"/></svg>'
            ).encode(),
            profile="svg.mask.v1",
        )

    oversized_path = "M0 0 " + "L1 1 " * ((MAX_PATH_CHARS // 5) + 1)
    with pytest.raises(ValueError, match="path complexity"):
        sanitize_svg(
            (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                f'<path d="{oversized_path}"/></svg>'
            ).encode(),
            profile="svg.mask.v1",
        )


def test_fundus_rejects_symlink_source_and_tampered_object(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    symlink = tmp_path / "source-link.svg"
    symlink.symlink_to(source)
    with pytest.raises(FundusError, match="regular non-linked"):
        fundus.ingest(symlink)

    ingest = fundus.ingest(source)
    _declare_asset(registry, ingest["sha256"])
    object_path = fundus.root / ingest["object_relpath"]
    object_path.write_bytes(b"tampered")
    with pytest.raises(FundusError, match="digest mismatch"):
        fundus.build("fixture.simple-ornament")


def test_fundus_rejects_rejected_acceptance_for_package(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    ingest = fundus.ingest(source)
    _declare_asset(registry, ingest["sha256"])
    build = fundus.build("fixture.simple-ornament")
    acceptance = fundus.accept(
        "fixture.simple-ornament",
        build_digest=build["build_digest"],
        reviewer="test:fixture",
        decision="rejected",
        reviewed_at="2026-08-13T10:00:00+00:00",
    )
    with pytest.raises(FundusError, match="accepted"):
        fundus.package(
            "fixture.simple-ornament",
            build_digest=build["build_digest"],
            acceptance_digest=acceptance["acceptance_digest"],
        )


def test_fundus_packaged_schemas_are_valid_json_schemas() -> None:
    schema_root = files("schauwerk.schemas")
    for name in (
        "fundus-family.v1.schema.json",
        "fundus-asset.v1.schema.json",
        "fundus-recipe.v1.schema.json",
        "fundus-build.v1.schema.json",
        "fundus-acceptance.v1.schema.json",
        "fundus-package.v1.schema.json",
        "fundus-ingest.v1.schema.json",
        "fundus-preview.v1.schema.json",
        "fundus-image-brief.v1.schema.json",
    ):
        schema = json.loads(schema_root.joinpath(name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_fundus_rejects_traversal_dangling_links_and_state_symlink_ancestors(
    tmp_path: Path,
) -> None:
    fundus, _, source = _setup(tmp_path)

    traversed = source.parent / "nested" / ".." / source.name
    with pytest.raises(FundusError, match="traversal"):
        fundus.ingest(traversed)

    dangling = tmp_path / "dangling.svg"
    dangling.symlink_to(tmp_path / "missing.svg")
    with pytest.raises(FundusError, match="regular non-linked"):
        fundus.ingest(dangling)

    real_state_parent = tmp_path / "real-state-parent"
    real_state_parent.mkdir()
    linked_state_parent = tmp_path / "linked-state-parent"
    linked_state_parent.symlink_to(real_state_parent, target_is_directory=True)
    linked_fundus = Fundus(
        FundusPaths(
            data_root=linked_state_parent / "fundus",
            registry_root=tmp_path / "registry",
        )
    )
    with pytest.raises(FundusError, match="symlink"):
        linked_fundus.ingest(source)


def test_fundus_registry_json_is_strict_and_canonical_json_rejects_nan(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"id":"first","id":"second"}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_json(duplicate)

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_json(nonfinite)

    with pytest.raises(ValueError, match="canonical JSON"):
        canonical_json({"value": float("nan")})


def test_fundus_svg_entity_rejection_and_sanitizer_fixed_point() -> None:
    entity_svg = (
        b'<!DOCTYPE svg [<!ENTITY x "boom">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        b'<path d="M0 0L1 1"/></svg>'
    )
    with pytest.raises(ValueError, match="doctype|entities"):
        sanitize_svg(entity_svg, profile="svg.mask.v1")

    first = sanitize_svg(SIMPLE_SVG, profile="svg.mask.v1")
    second = sanitize_svg(first, profile="svg.mask.v1")
    assert second == first


def test_fundus_build_and_package_are_deterministic_across_roots(
    tmp_path: Path,
) -> None:
    outcomes: list[tuple[str, str, bytes]] = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        fundus, registry, source = _setup(root)
        ingest = fundus.ingest(source, origin="determinism", rights_status="owned")
        _declare_asset(registry, ingest["sha256"])
        build = fundus.build("fixture.simple-ornament")
        acceptance = fundus.accept(
            "fixture.simple-ornament",
            build_digest=build["build_digest"],
            reviewer="test:determinism",
            decision="accepted",
            reviewed_at="2026-08-13T12:00:00+00:00",
        )
        package = fundus.package(
            "fixture.simple-ornament",
            build_digest=build["build_digest"],
            acceptance_digest=acceptance["acceptance_digest"],
        )
        package_file = (
            Path(package["package_dir"])
            / "assets"
            / "fixture-simple-ornament-mask.svg"
        )
        outcomes.append(
            (
                build["build_digest"],
                package["package_digest"],
                package_file.read_bytes(),
            )
        )

    assert outcomes[0] == outcomes[1]


def test_runner_dispatches_fundus_doctor(tmp_path: Path, capsys) -> None:
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "recipes" / "svg-mask-v1.json").write_text(
        json.dumps(_recipe()), encoding="utf-8"
    )

    code = runner.main(
        [
            "fundus",
            "doctor",
            "--data-root",
            str(tmp_path / "data"),
            "--registry-root",
            str(registry),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["miro_independent"] is True
    assert result["registry"]["recipes"] == ["svg-mask-v1"]


def _image_brief(asset_id: str = "fixture.simple-ornament") -> dict:
    return {
        "schema_version": "schauwerk-fundus-image-brief.v1",
        "id": f"{asset_id}.generate.v1",
        "intent": "reusable_asset",
        "asset_id": asset_id,
        "family": "fixture.simple",
        "operation": "generate",
        "source_role": "trace_source",
        "desired_output_roles": ["mask"],
        "requirements": ["clear silhouette", "transparent background"],
        "forbidden": ["drop shadows", "material texture"],
        "properties": {
            "mirror_safe": False,
            "rotate_safe": False,
            "recolor_safe": True,
            "mask_safe": True,
            "tile_safe": False,
        },
        "acceptance": {
            "visual_review_required": True,
            "inheritance": "none",
        },
    }


def test_generated_ingest_requires_digest_bound_image_brief(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    with pytest.raises(FundusError, match="require a Fundus image brief"):
        fundus.ingest(
            source,
            origin="chatgpt-images:fixture",
            rights_status="owned",
        )

    brief_path = tmp_path / "image-brief.json"
    brief_path.write_text(json.dumps(_image_brief()), encoding="utf-8")
    validated = fundus.image_brief(brief_path)
    _validate_instance("fundus-image-brief.v1.schema.json", _image_brief())

    ingest = fundus.ingest(
        source,
        origin="chatgpt-images:fixture",
        rights_status="owned",
        source_mode="generated",
        image_brief_path=brief_path,
    )
    assert ingest["source_mode"] == "generated"
    assert ingest["image_brief_sha256"] == validated["image_brief_sha256"]

    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.simple-ornament",
        "family": "fixture.simple",
        "recipe": "svg-mask-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": ingest["sha256"],
                "media_type": "image/svg+xml",
                "origin": "chatgpt-images:fixture",
                "rights_status": "owned",
                "source_mode": "generated",
                "image_brief_sha256": ingest["image_brief_sha256"],
            }
        ],
        "properties": {"mask_safe": True, "recolor_safe": True},
    }
    (registry / "assets" / "fixture.simple-ornament.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    _validate_instance("fundus-asset.v1.schema.json", asset)
    build = fundus.build("fixture.simple-ornament")
    assert build["source"]["image_brief_sha256"] == ingest["image_brief_sha256"]
    acceptance = fundus.accept(
        "fixture.simple-ornament",
        build_digest=build["build_digest"],
        reviewer="test:image-brief",
        decision="accepted",
        reviewed_at="2026-08-14T06:00:00+00:00",
    )
    package = fundus.package(
        "fixture.simple-ornament",
        build_digest=build["build_digest"],
        acceptance_digest=acceptance["acceptance_digest"],
    )
    assert package["source_image_brief_sha256"] == ingest["image_brief_sha256"]


def test_generated_asset_cannot_drop_or_swap_image_brief_binding(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    brief_path = tmp_path / "image-brief.json"
    brief_path.write_text(json.dumps(_image_brief()), encoding="utf-8")
    fundus.image_brief(brief_path)
    ingest = fundus.ingest(
        source,
        origin="chatgpt-images:fixture",
        rights_status="owned",
        image_brief_path=brief_path,
    )

    missing = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.simple-ornament",
        "family": "fixture.simple",
        "recipe": "svg-mask-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": ingest["sha256"],
                "media_type": "image/svg+xml",
            }
        ],
    }
    (registry / "assets" / "fixture.simple-ornament.json").write_text(
        json.dumps(missing), encoding="utf-8"
    )
    with pytest.raises(FundusError, match="preserve ingest source_mode"):
        fundus.build("fixture.simple-ornament")

    missing["sources"][0]["source_mode"] = "generated"
    missing["sources"][0]["image_brief_sha256"] = "0" * 64
    (registry / "assets" / "fixture.simple-ornament.json").write_text(
        json.dumps(missing), encoding="utf-8"
    )
    with pytest.raises(FundusError, match="preserve ingest image brief"):
        fundus.build("fixture.simple-ornament")


def test_ingest_and_build_schemas_enforce_generative_brief_binding() -> None:
    generated_ingest = {
        "schema_version": "schauwerk-fundus-ingest.v1",
        "sha256": "1" * 64,
        "bytes": 1,
        "media_type": "image/png",
        "width": 1,
        "height": 1,
        "has_alpha": True,
        "origin": "chatgpt-images:test",
        "rights_status": "owned",
        "source_path_sha256": "2" * 64,
        "ingested_at": "2026-08-14T06:00:00+00:00",
        "object_relpath": "objects/sha256/11/" + "1" * 64,
        "provenance_claim_is_declarative": True,
        "source_mode": "generated",
    }
    with pytest.raises(ValidationError):
        _validate_instance("fundus-ingest.v1.schema.json", generated_ingest)
    generated_ingest["image_brief_sha256"] = "3" * 64
    _validate_instance("fundus-ingest.v1.schema.json", generated_ingest)

    manual_with_brief = dict(generated_ingest)
    manual_with_brief["source_mode"] = "manual"
    with pytest.raises(ValidationError):
        _validate_instance("fundus-ingest.v1.schema.json", manual_with_brief)

    legacy_ingest = dict(generated_ingest)
    legacy_ingest.pop("source_mode")
    legacy_ingest.pop("image_brief_sha256")
    _validate_instance("fundus-ingest.v1.schema.json", legacy_ingest)

    build_source = {
        "role": "trace_source",
        "sha256": "1" * 64,
        "media_type": "image/png",
        "source_mode": "edited",
    }
    build = {
        "schema_version": "schauwerk-fundus-build.v1",
        "asset_id": "fixture.asset",
        "asset_manifest_sha256": "4" * 64,
        "recipe_id": "fixture-recipe",
        "recipe_sha256": "5" * 64,
        "source": build_source,
        "toolchain": {},
        "outputs": [
            {
                "role": "raster",
                "filename": "out.png",
                "media_type": "image/png",
                "sha256": "6" * 64,
                "bytes": 1,
            }
        ],
        "build_digest": "7" * 64,
    }
    with pytest.raises(ValidationError):
        _validate_instance("fundus-build.v1.schema.json", build)
    build_source["image_brief_sha256"] = "3" * 64
    _validate_instance("fundus-build.v1.schema.json", build)


def test_edit_image_brief_rejects_orphan_object_without_ingest_receipt(
    tmp_path: Path,
) -> None:
    fundus, _, source = _setup(tmp_path)
    payload = fundus._read_source(source)
    sha256 = hashlib.sha256(payload).hexdigest()
    fundus._ensure_state()
    fundus._write_create_or_verify(fundus._object_path(sha256), payload)

    brief = _image_brief()
    brief["id"] = "fixture.simple-ornament.edit-orphan.v1"
    brief["operation"] = "edit"
    brief["input_sha256"] = sha256
    path = tmp_path / "orphan-edit-brief.json"
    path.write_text(json.dumps(brief), encoding="utf-8")
    with pytest.raises(FundusError, match="completed Fundus ingest"):
        fundus.image_brief(path)

    completed = fundus.ingest(
        source, origin="manual:completed-after-orphan", rights_status="owned"
    )
    assert completed["sha256"] == sha256
    prepared = fundus.image_brief(path)
    assert prepared["input_sha256"] == sha256


def test_agent_policy_routes_reusable_image_work_through_fundus() -> None:
    import yaml

    repo_root = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load((repo_root / "agent-policy.yaml").read_text(encoding="utf-8"))
    fundus = policy["fundus"]
    assert fundus["image_operations_contract"] == "docs/fundus/image-operations-v1.md"
    assert fundus["reusable_or_production_visuals"][
        "generated_or_edited_requires_image_brief"
    ] is True
    assert fundus["cross_repo_integration"] == {
        "owner": "grabowski",
        "schauwerk_direct_write": False,
    }
    agents = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/fundus/image-operations-v1.md" in agents


def test_legacy_generated_ingest_remains_idempotent_without_reclassification(
    tmp_path: Path,
) -> None:
    fundus, _, source = _setup(tmp_path)
    payload = fundus._read_source(source)
    sha256 = __import__("hashlib").sha256(payload).hexdigest()
    fundus._ensure_state()
    object_path = fundus._object_path(sha256)
    fundus._write_create_or_verify(object_path, payload)
    receipt = {
        "schema_version": "schauwerk-fundus-ingest.v1",
        "sha256": sha256,
        "bytes": len(payload),
        "media_type": "image/svg+xml",
        "width": 100,
        "height": 100,
        "has_alpha": False,
        "origin": "chatgpt-images:legacy",
        "rights_status": "owned",
        "source_path_sha256": "0" * 64,
        "ingested_at": "2026-08-13T00:00:00+00:00",
        "object_relpath": str(object_path.relative_to(fundus.root)),
        "provenance_claim_is_declarative": True,
    }
    fundus._write_json_create_or_verify(
        fundus.root / "receipts" / "ingest" / f"{sha256}.json", receipt
    )
    repeated = fundus.ingest(
        source, origin="chatgpt-images:legacy", rights_status="owned"
    )
    assert repeated == receipt


def test_image_brief_must_be_prepared_and_authorize_output_role(tmp_path: Path) -> None:
    fundus, registry, source = _setup(tmp_path)
    brief = _image_brief()
    brief["desired_output_roles"] = ["vector"]
    brief_path = tmp_path / "image-brief.json"
    brief_path.write_text(json.dumps(brief), encoding="utf-8")
    with pytest.raises(FundusError, match="must be prepared"):
        fundus.ingest(
            source,
            origin="chatgpt-images:fixture",
            rights_status="owned",
            image_brief_path=brief_path,
        )
    prepared = fundus.image_brief(brief_path)
    ingest = fundus.ingest(
        source,
        origin="chatgpt-images:fixture",
        rights_status="owned",
        image_brief_path=brief_path,
    )
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.simple-ornament",
        "family": "fixture.simple",
        "recipe": "svg-mask-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": ingest["sha256"],
                "media_type": "image/svg+xml",
                "source_mode": "generated",
                "image_brief_sha256": prepared["image_brief_sha256"],
            }
        ],
    }
    (registry / "assets" / "fixture.simple-ornament.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    with pytest.raises(FundusError, match="authorize the build output role"):
        fundus.build("fixture.simple-ornament")


def test_edit_image_brief_requires_exact_ingested_input_revision(tmp_path: Path) -> None:
    fundus, _, source = _setup(tmp_path)
    brief = _image_brief()
    brief["id"] = "fixture.simple-ornament.edit.v1"
    brief["operation"] = "edit"
    missing_path = tmp_path / "missing-edit-brief.json"
    missing_path.write_text(json.dumps(brief), encoding="utf-8")
    with pytest.raises(FundusError, match="input sha256"):
        fundus.image_brief(missing_path)

    base = fundus.ingest(source, origin="manual:edit-input", rights_status="owned")
    brief["input_sha256"] = base["sha256"]
    brief_path = tmp_path / "edit-brief.json"
    brief_path.write_text(json.dumps(brief), encoding="utf-8")
    prepared = fundus.image_brief(brief_path)
    assert prepared["input_sha256"] == base["sha256"]
    assert prepared["prepared"] is True
