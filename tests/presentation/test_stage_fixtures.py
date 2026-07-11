import json
from pathlib import Path

from jsonschema import Draft202012Validator

from schauwerk.presentation.model import load_presentation


def test_checked_in_technical_and_education_models_are_source_bound() -> None:
    root = Path(__file__).resolve().parents[2]
    cases = (
        ("technical", "technical", 5, 600),
        ("education", "education", 6, 3300),
    )
    for directory, variant_id, scenes, seconds in cases:
        model = load_presentation(
            root / "docs/operators/evidence/sw012-buehne-20260711" / directory / "model.json",
            source_root=root,
        )
        variant = model.variant_by_id[variant_id]
        assert len(variant.scene_ids) == scenes
        assert variant.planned_duration_seconds == seconds


def test_presentation_schema_is_valid_and_accepts_checked_in_models() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schemas/presentation.v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for directory in ("technical", "education"):
        model = json.loads(
            (
                root / "docs/operators/evidence/sw012-buehne-20260711" / directory / "model.json"
            ).read_text()
        )
        validator.validate(model)


def _tree_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_checked_in_outputs_and_receipt_match_fresh_builds(tmp_path: Path) -> None:
    from schauwerk.presentation.package import build_presentation_packages

    root = Path(__file__).resolve().parents[2]
    evidence = root / "docs/operators/evidence/sw012-buehne-20260711"
    receipt = json.loads((evidence / "acceptance-receipt.json").read_text())
    assert receipt["deterministic_repeat_build"] is True
    assert receipt["network_access_required"] is False
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["checks"]["atomic_noreplace_publication"] is True
    assert receipt["checks"]["foreign_destination_preserved_on_race"] is True
    assert receipt["checks"]["interrupted_build_rollback"] is True
    assert receipt["checks"]["partial_package_rollback"] is True
    assert receipt["checks"]["pptx_header_contrast"] is True
    assert receipt["checks"]["published_destination_identity_guard"] is True
    assert receipt["recovery"] == {
        "concurrent_empty_destination_preserved": True,
        "concurrent_nonempty_destination_preserved": True,
        "first_published_package_removed_when_second_publish_fails": True,
        "interrupt_after_first_publish_rolls_back": True,
        "publication_primitive": "linux-renameat2-RENAME_NOREPLACE",
        "replaced_published_destination_not_deleted": True,
        "unsupported_atomic_publication_fails_closed": True,
    }

    for directory in ("technical", "education"):
        fresh_public = tmp_path / f"{directory}-public"
        fresh_presenter = tmp_path / f"{directory}-presenter"
        build_presentation_packages(
            model_path=evidence / directory / "model.json",
            variant_id=directory,
            public_dir=fresh_public,
            presenter_dir=fresh_presenter,
            source_root=root,
        )
        assert _tree_bytes(fresh_public) == _tree_bytes(evidence / directory / "public")
        assert _tree_bytes(fresh_presenter) == _tree_bytes(evidence / directory / "presenter")

        public_manifest = json.loads((fresh_public / "manifest.json").read_text())
        presenter_manifest = json.loads((fresh_presenter / "manifest.json").read_text())
        fixture_receipt = receipt["fixtures"][directory]
        assert fixture_receipt["pptx_header_text_contrast_verified"] is True
        assert fixture_receipt["public_manifest_digest"] == public_manifest["manifest_digest"]
        assert fixture_receipt["presenter_manifest_digest"] == presenter_manifest["manifest_digest"]
        assert fixture_receipt["scene_order"] == public_manifest["artifact_metadata"]["scene_order"]
        assert (
            fixture_receipt["planned_duration_seconds"]
            == presenter_manifest["planned_duration_seconds"]
        )
