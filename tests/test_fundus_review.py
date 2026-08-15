from __future__ import annotations

import base64
import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.model import digest_json
from schauwerk.fundus.review import (
    build_review_bundle,
    build_review_plan,
    check_review_bundle,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+P9zWAAAAAElFTkSuQmCC"
)


def _validate_schema(name: str, value: dict) -> None:
    schema = json.loads(files("schauwerk.schemas").joinpath(name).read_text())
    Draft202012Validator(schema).validate(value)


def _fundus(tmp_path: Path) -> Fundus:
    data = tmp_path / "fundus-data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "families").mkdir()
    (registry / "assets").mkdir()
    (registry / "recipes" / "svg-mask-v1.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    (registry / "families" / "fixture.review.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.review",
                "title": "Reusable Review Fixture",
                "tags": ["fixture", "review"],
            }
        ),
        encoding="utf-8",
    )
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))
    for index, path_data in enumerate(
        (
            "M10 10 H90 V140 H10 Z",
            "M20 20 H80 V130 H20 Z",
        ),
        1,
    ):
        source = tmp_path / f"source-{index}.svg"
        source.write_text(
            (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 150">'
                f'<path fill="#000" d="{path_data}"/>'
                "</svg>"
            ),
            encoding="utf-8",
        )
        ingest = fundus.ingest(source, origin="test-fixture", rights_status="owned")
        asset_id = f"fixture.review.{index:02d}"
        (registry / "assets" / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": "schauwerk-fundus-asset.v1",
                    "id": asset_id,
                    "family": "fixture.review",
                    "recipe": "svg-mask-v1",
                    "sources": [
                        {
                            "role": "trace_source",
                            "sha256": ingest["sha256"],
                            "media_type": "image/svg+xml",
                            "origin": "test-fixture",
                            "rights_status": "owned",
                        }
                    ],
                    "properties": {
                        "mirror_safe": False,
                        "rotate_safe": False,
                        "recolor_safe": True,
                        "mask_safe": True,
                        "tile_safe": False,
                    },
                }
            ),
            encoding="utf-8",
        )
    return fundus


def test_review_plan_is_stable_schema_valid_and_does_not_infer_acceptance(
    tmp_path: Path,
) -> None:
    fundus = _fundus(tmp_path)
    first = build_review_plan(fundus, "fixture.review")
    second = build_review_plan(fundus, "fixture.review")

    assert first.plan_digest == second.plan_digest
    assert len(first.variants) == 2
    assert {item.acceptance_state for item in first.variants} == {"unreviewed"}
    public = first.to_dict()
    _validate_schema("fundus-review-plan.v1.schema.json", public)
    assert public["fundus_authoritative"] is True
    assert public["visual_acceptance_inferred"] is False
    assert public["package_created"] is False


def test_default_review_bundle_is_portable_network_free_and_create_only(
    tmp_path: Path,
) -> None:
    fundus = _fundus(tmp_path)
    output = tmp_path / "review-output"

    result = build_review_bundle(fundus, "fixture.review", output)

    assert result["ok"] is True
    assert result["consumer_template_mode"] == "default"
    assert result["variant_count"] == 2
    assert result["network_dependencies"] is False
    assert result["portable"] is True
    assert result["fundus_authoritative"] is True
    assert result["visual_acceptance_inferred"] is False
    assert result["package_created"] is False
    manifest = json.loads((output / "review.json").read_text())
    _validate_schema("fundus-review-bundle.v1.schema.json", manifest)
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "REVIEW · keine Acceptance durch diese Seite" in html
    assert "https://" not in html
    assert "http://" not in html
    assert "fixture.review.01" in html
    assert (output / "review.css").is_file()
    assert (output / "review.js").is_file()
    assert len(list((output / "assets").glob("*.svg"))) == 2
    assert check_review_bundle(output)["review_digest"] == result["review_digest"]

    with pytest.raises(FundusError, match="already exists"):
        build_review_bundle(fundus, "fixture.review", output)


def test_custom_consumer_template_binds_fixture_without_leaking_source_path(
    tmp_path: Path,
) -> None:
    fundus = _fundus(tmp_path)
    fixture = tmp_path / "sample.png"
    fixture.write_bytes(PNG_1X1)
    template = tmp_path / "consumer.html"
    template.write_text(
        (
            '<figure class="product-demo">'
            '<img class="fixture-photo" src="{{FIXTURE:sample}}" alt="Sample">'
            '<img class="product-asset" src="{{ASSET_URL}}" alt="{{ASSET_ID}}">'
            "</figure>"
        ),
        encoding="utf-8",
    )
    css = tmp_path / "consumer.css"
    css.write_text(
        (
            ".product-demo{position:relative;max-width:600px}"
            ".fixture-photo{display:block;width:100%}"
            ".product-asset{position:absolute;inset:8%;width:84%;height:84%;object-fit:contain}"
        ),
        encoding="utf-8",
    )
    output = tmp_path / "consumer-review"

    result = build_review_bundle(
        fundus,
        "fixture.review",
        output,
        title="Consumer Review",
        consumer_template=template,
        consumer_css=css,
        fixtures={"sample": fixture},
    )

    assert result["consumer_template_mode"] == "custom"
    assert len(result["fixtures"]) == 1
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "fixtures/fixture-sample.png" in html
    assert "assets/fixture.review.01.svg" in html
    manifest_text = (output / "review.json").read_text(encoding="utf-8")
    assert str(fixture) not in manifest_text
    assert str(template) not in manifest_text
    assert str(css) not in manifest_text
    assert "url(" not in (output / "review.css").read_text(encoding="utf-8")
    assert check_review_bundle(output)["ok"] is True



def test_review_requires_asset_token_as_image_source(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    template = tmp_path / "text-only-asset.html"
    template.write_text(
        '<p>{{ASSET_URL}}</p><img src="{{FIXTURE:sample}}" alt="fixture">',
        encoding="utf-8",
    )
    fixture = tmp_path / "sample.png"
    fixture.write_bytes(PNG_1X1)
    with pytest.raises(FundusError, match="must render"):
        build_review_bundle(
            fundus,
            "fixture.review",
            tmp_path / "text-only-asset-output",
            consumer_template=template,
            fixtures={"sample": fixture},
        )

def test_review_rejects_active_or_external_consumer_content(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    bad_template = tmp_path / "bad.html"
    bad_template.write_text(
        '<script>alert(1)</script><img src="{{ASSET_URL}}" alt="x">',
        encoding="utf-8",
    )
    with pytest.raises(FundusError, match="tag is forbidden"):
        build_review_bundle(
            fundus,
            "fixture.review",
            tmp_path / "bad-template-output",
            consumer_template=bad_template,
        )

    good_template = tmp_path / "good.html"
    good_template.write_text('<img src="{{ASSET_URL}}" alt="x">', encoding="utf-8")
    bad_css = tmp_path / "bad.css"
    bad_css.write_text(".x{background:url(https://example.invalid/a.png)}", encoding="utf-8")
    with pytest.raises(FundusError, match="external or executable"):
        build_review_bundle(
            fundus,
            "fixture.review",
            tmp_path / "bad-css-output",
            consumer_template=good_template,
            consumer_css=bad_css,
        )


def test_review_rejects_unknown_fixture_and_svg_fixture(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    template = tmp_path / "consumer.html"
    template.write_text(
        '<img src="{{FIXTURE:missing}}" alt="sample"><img src="{{ASSET_URL}}" alt="asset">',
        encoding="utf-8",
    )
    with pytest.raises(FundusError, match="unknown fixtures"):
        build_review_bundle(
            fundus,
            "fixture.review",
            tmp_path / "missing-fixture-output",
            consumer_template=template,
        )

    svg_fixture = tmp_path / "fixture.svg"
    svg_fixture.write_text(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<path d="M0 0H10V10H0Z"/></svg>'
        ),
        encoding="utf-8",
    )
    with pytest.raises(FundusError, match="must be PNG, JPEG or WebP"):
        build_review_bundle(
            fundus,
            "fixture.review",
            tmp_path / "svg-fixture-output",
            fixtures={"sample": svg_fixture},
        )


def test_review_check_detects_tampering_and_extra_files(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    output = tmp_path / "review"
    build_review_bundle(fundus, "fixture.review", output)
    asset = next((output / "assets").iterdir())
    asset.chmod(0o644)
    asset.write_text("drift", encoding="utf-8")
    with pytest.raises(FundusError, match="drifted"):
        check_review_bundle(output)

    output2 = tmp_path / "review-extra"
    build_review_bundle(fundus, "fixture.review", output2)
    (output2 / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(FundusError, match="file set mismatch"):
        check_review_bundle(output2)


def test_review_check_rejects_semantically_resigned_variant_and_plan(
    tmp_path: Path,
) -> None:
    fundus = _fundus(tmp_path)
    variant_output = tmp_path / "variant-output-binding"
    build_review_bundle(fundus, "fixture.review", variant_output)
    manifest_path = variant_output / "review.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variants"][0]["output_sha256"] = "f" * 64
    body = dict(manifest)
    body.pop("review_digest")
    manifest["review_digest"] = digest_json(body)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FundusError, match="variant output binding mismatch"):
        check_review_bundle(variant_output)

    plan_output = tmp_path / "plan-binding"
    build_review_bundle(fundus, "fixture.review", plan_output)
    plan_manifest_path = plan_output / "review.json"
    plan_manifest = json.loads(plan_manifest_path.read_text(encoding="utf-8"))
    plan_manifest["plan_digest"] = "e" * 64
    plan_body = dict(plan_manifest)
    plan_body.pop("review_digest")
    plan_manifest["review_digest"] = digest_json(plan_body)
    plan_manifest_path.write_text(json.dumps(plan_manifest), encoding="utf-8")
    with pytest.raises(FundusError, match="plan binding mismatch"):
        check_review_bundle(plan_output)


def test_checked_family_bundle_can_bind_direct_acceptance(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    output = tmp_path / "review-acceptance"
    bundle = build_review_bundle(fundus, "fixture.review", output)
    variant = bundle["variants"][0]
    acceptance = fundus.accept(
        variant["asset_id"],
        build_digest=variant["build_digest"],
        reviewer="test:family-review",
        decision="accepted",
        review_bundle_path=output,
    )
    assert acceptance["schema_version"] == "schauwerk-fundus-acceptance.v3"
    assert acceptance["review_evidence"]["kind"] == "family_review_bundle"
    assert acceptance["review_evidence"]["review_digest"] == bundle["review_digest"]


def test_review_bundle_revalidates_output_after_build_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fundus = _fundus(tmp_path)
    build = fundus.build("fixture.review.01")
    output_path = Path(build["build_dir"]) / build["outputs"][0]["filename"]
    original = fundus._load_build

    def substitute_after_check(asset_id: str, build_digest: str):
        loaded = original(asset_id, build_digest)
        output_path.write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">'
            b'<path d="M0 0L2 0L2 2Z"/></svg>'
        )
        return loaded

    monkeypatch.setattr(fundus, "_load_build", substitute_after_check)
    with pytest.raises(FundusError, match="build output (size|digest) mismatch"):
        build_review_bundle(fundus, "fixture.review", tmp_path / "raced-review")


def test_historical_review_bundle_without_output_bytes_remains_readable_only(
    tmp_path: Path,
) -> None:
    fundus = _fundus(tmp_path)
    output = tmp_path / "historical-review"
    build_review_bundle(fundus, "fixture.review", output)
    manifest_path = output / "review.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for variant in manifest["variants"]:
        variant.pop("output_bytes")
    plan_variants = [
        {key: value for key, value in variant.items() if key != "file"}
        for variant in manifest["variants"]
    ]
    plan_body = {
        "schema_version": "schauwerk-fundus-review-plan.v1",
        "family_id": manifest["family_id"],
        "family_title": manifest["family_title"],
        "variants": plan_variants,
        "fundus_authoritative": True,
        "visual_acceptance_inferred": False,
        "package_created": False,
    }
    manifest["plan_digest"] = digest_json(plan_body)
    body = dict(manifest)
    body.pop("review_digest")
    manifest["review_digest"] = digest_json(body)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    checked = check_review_bundle(output)
    assert checked["ok"] is True
    variant = checked["variants"][0]
    with pytest.raises(FundusError, match="does not bind every build output"):
        fundus.accept(
            variant["asset_id"],
            build_digest=variant["build_digest"],
            reviewer="test:historical-review",
            decision="accepted",
            review_bundle_path=output,
        )
