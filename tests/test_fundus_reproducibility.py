from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk import runner
from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.model import canonical_json
from schauwerk.fundus.reproducibility import drift_build, reproduce_build

SIMPLE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    b'<path fill="#000" d="M10 50 C20 10 80 10 90 50 C80 90 20 90 10 50 Z"/>'
    b"</svg>"
)


def _snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _validate_report(report: dict) -> None:
    schema = json.loads(
        files("schauwerk.schemas")
        .joinpath("fundus-reproduction.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(report)


def _setup(tmp_path: Path) -> tuple[Fundus, Path, dict]:
    data = tmp_path / "data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "assets").mkdir()
    (registry / "families").mkdir()
    (registry / "families" / "fixture.reproduce.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.reproduce",
                "title": "Reproduction fixture",
                "tags": ["fixture", "reproduce"],
            }
        ),
        encoding="utf-8",
    )
    recipe = {
        "schema_version": "schauwerk-fundus-recipe.v1",
        "id": "mask-v1",
        "transform": "sanitize_svg",
        "source_role": "trace_source",
        "output": {
            "role": "mask",
            "filename": "mask.svg",
            "media_type": "image/svg+xml",
        },
        "parameters": {"profile": "svg.mask.v1"},
    }
    (registry / "recipes" / "mask-v1.json").write_text(
        json.dumps(recipe), encoding="utf-8"
    )
    source = tmp_path / "source.svg"
    source.write_bytes(SIMPLE_SVG)
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))
    ingest = fundus.ingest(
        source,
        origin="fixture:reproduce",
        rights_status="owned",
        source_mode="manual",
    )
    asset = {
        "schema_version": "schauwerk-fundus-asset.v1",
        "id": "fixture.reproduce",
        "family": "fixture.reproduce",
        "recipe": "mask-v1",
        "sources": [
            {
                "role": "trace_source",
                "sha256": ingest["sha256"],
                "media_type": "image/svg+xml",
                "origin": "fixture:reproduce",
                "rights_status": "owned",
                "source_mode": "manual",
            }
        ],
        "properties": {"mask_safe": True},
    }
    (registry / "assets" / "fixture.reproduce.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    build = fundus.build("fixture.reproduce")
    return fundus, registry, build


def test_drift_clean_is_read_only_and_schema_valid(tmp_path: Path) -> None:
    fundus, _, build = _setup(tmp_path)
    before = _snapshot(fundus.root)

    report = drift_build(fundus, "fixture.reproduce", build["build_digest"])

    _validate_report(report)
    assert report["operation"] == "drift"
    assert report["status"] == "clean"
    assert report["ok"] is True
    assert report["asset_manifest_match"] is True
    assert report["recipe_match"] is True
    assert report["reproduction"] is None
    assert report["canonical_state_mutated"] is False
    assert _snapshot(fundus.root) == before


def test_reproduce_uses_temporary_state_and_leaves_canonical_state_unchanged(
    tmp_path: Path,
) -> None:
    fundus, _, build = _setup(tmp_path)
    before = _snapshot(fundus.root)

    report = reproduce_build(fundus, "fixture.reproduce", build["build_digest"])

    _validate_report(report)
    assert report["status"] == "reproduced"
    assert report["ok"] is True
    assert report["reproduction"]["attempted"] is True
    assert report["reproduction"]["temporary_state_used"] is True
    assert report["reproduction"]["build_digest_match"] is True
    assert report["reproduction"]["output_sha256s_match"] is True
    assert report["reproduction"]["toolchain_match"] is True
    assert report["canonical_state_mutated"] is False
    assert _snapshot(fundus.root) == before


def test_asset_and_recipe_registry_drift_are_reported_without_reproduction(
    tmp_path: Path,
) -> None:
    fundus, registry, build = _setup(tmp_path)
    asset_path = registry / "assets" / "fixture.reproduce.json"
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    asset["properties"]["recolor_safe"] = True
    asset_path.write_text(json.dumps(asset), encoding="utf-8")

    asset_report = reproduce_build(fundus, "fixture.reproduce", build["build_digest"])
    assert asset_report["status"] == "drifted"
    assert asset_report["asset_manifest_match"] is False
    assert asset_report["reproduction"]["attempted"] is False

    asset["properties"].pop("recolor_safe")
    asset_path.write_text(json.dumps(asset), encoding="utf-8")
    recipe_path = registry / "recipes" / "mask-v1.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["parameters"]["profile"] = "svg.decorative.v1"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    recipe_report = drift_build(fundus, "fixture.reproduce", build["build_digest"])
    assert recipe_report["status"] == "drifted"
    assert recipe_report["asset_manifest_match"] is True
    assert recipe_report["recipe_match"] is False


def test_corrupted_baseline_build_fails_closed_before_drift_report(tmp_path: Path) -> None:
    fundus, _, build = _setup(tmp_path)
    output_path = (
        fundus.root
        / "builds"
        / "fixture.reproduce"
        / build["build_digest"]
        / build["outputs"][0]["filename"]
    )
    output_path.write_bytes(output_path.read_bytes() + b"\n")

    with pytest.raises(FundusError, match="build output (size|digest) mismatch"):
        drift_build(fundus, "fixture.reproduce", build["build_digest"])


def test_source_object_drift_is_reported(tmp_path: Path) -> None:
    fundus, _, build = _setup(tmp_path)
    source_sha = build["source"]["sha256"]
    object_path = fundus._object_path(source_sha)
    object_path.write_bytes(SIMPLE_SVG + b"\n")

    report = drift_build(fundus, "fixture.reproduce", build["build_digest"])

    assert report["status"] == "drifted"
    assert report["ok"] is False
    assert report["source_checks"][0]["object_ok"] is False
    assert "digest mismatch" in report["source_checks"][0]["error"]


def test_reproduction_reports_current_toolchain_drift_without_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fundus, _, build = _setup(tmp_path)
    before = _snapshot(fundus.root)
    original_build = Fundus.build

    def changed_toolchain(self: Fundus, asset_id: str) -> dict:
        result = original_build(self, asset_id)
        result = dict(result)
        result["toolchain"] = {"fundus_core": "changed-current-toolchain"}
        return result

    monkeypatch.setattr(Fundus, "build", changed_toolchain)
    report = reproduce_build(fundus, "fixture.reproduce", build["build_digest"])

    assert report["status"] == "reproduction_drift"
    assert report["ok"] is False
    assert report["reproduction"]["build_digest_match"] is True
    assert report["reproduction"]["output_sha256s_match"] is True
    assert report["reproduction"]["toolchain_match"] is False
    assert _snapshot(fundus.root) == before


def test_cli_drift_and_reproduce_return_versioned_reports(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fundus, registry, build = _setup(tmp_path)
    common = [
        "fixture.reproduce",
        "--build",
        build["build_digest"],
        "--data-root",
        str(fundus.root),
        "--registry-root",
        str(registry),
        "--json",
    ]

    assert runner.main(["fundus", "drift", *common]) == 0
    drift = json.loads(capsys.readouterr().out)
    assert drift["schema_version"] == "schauwerk-fundus-reproduction.v1"
    assert drift["operation"] == "drift"
    assert drift["ok"] is True

    assert runner.main(["fundus", "reproduce", *common]) == 0
    reproduced = json.loads(capsys.readouterr().out)
    assert reproduced["schema_version"] == "schauwerk-fundus-reproduction.v1"
    assert reproduced["operation"] == "reproduce"
    assert reproduced["status"] == "reproduced"


@pytest.mark.parametrize("defect", ["missing", "forged", "mismatched"])
def test_drift_and_reproduce_require_valid_exact_ingest_receipt(
    tmp_path: Path, defect: str
) -> None:
    fundus, _, build = _setup(tmp_path)
    sha256 = build["source"]["sha256"]
    receipt_path = fundus.root / "receipts" / "ingest" / f"{sha256}.json"
    if defect == "missing":
        receipt_path.unlink()
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if defect == "forged":
            receipt["forged"] = True
        else:
            receipt["origin"] = "fixture:mismatched"
        receipt_path.write_bytes(canonical_json(receipt) + b"\n")

    drift = drift_build(fundus, "fixture.reproduce", build["build_digest"])
    assert drift["ok"] is False
    assert drift["source_checks"][0]["provenance_ok"] is False
    reproduction = reproduce_build(fundus, "fixture.reproduce", build["build_digest"])
    assert reproduction["ok"] is False
    assert reproduction["reproduction"]["attempted"] is False
