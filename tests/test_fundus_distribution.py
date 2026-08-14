from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = (
    "fundus-family.v1.schema.json",
    "fundus-asset.v1.schema.json",
    "fundus-recipe.v1.schema.json",
    "fundus-recipe.v2.schema.json",
    "fundus-recipe.v3.schema.json",
    "fundus-build.v1.schema.json",
    "fundus-build.v2.schema.json",
    "fundus-acceptance.v1.schema.json",
    "fundus-acceptance.v2.schema.json",
    "fundus-package.v1.schema.json",
    "fundus-package.v2.schema.json",
    "fundus-consumer-lock.v1.schema.json",
    "fundus-ingest.v1.schema.json",
    "fundus-preview.v1.schema.json",
    "fundus-review-plan.v1.schema.json",
    "fundus-review-bundle.v1.schema.json",
    "fundus-image-brief.v1.schema.json",
)


def _build_frontend_python() -> str:
    candidates = [sys.executable, "/usr/bin/python3", shutil.which("python3")]
    for candidate in candidates:
        if not candidate:
            continue
        probe = subprocess.run(
            [candidate, "-m", "pip", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return candidate
    raise AssertionError("no local Python with pip is available for the wheel build")


def test_fundus_wheel_contains_runtime_and_runs_without_source_tree(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    builder = _build_frontend_python()
    build = subprocess.run(
        [
            builder,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--ignore-requires-python",
            "--wheel-dir",
            str(wheel_dir),
            ".",
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = sorted(wheel_dir.glob("schauwerk-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
    assert "Pillow==12.2.0" in metadata
    assert "Provides-Extra: trace" in metadata
    assert "vtracer==0.6.15" in metadata

    runtime_root = tmp_path / "runtime"
    smoke = r"""
import json
import sys
from importlib.resources import files
from pathlib import Path

wheel = Path(sys.argv[1])
runtime_root = Path(sys.argv[2])
sys.path.insert(0, str(wheel))

from schauwerk import fundus as fundus_package
from schauwerk.fundus import Fundus, FundusPaths
from schauwerk.fundus.package_contract import verify_consumer_lock, verify_package_directory
from schauwerk.fundus.review import build_review_bundle, check_review_bundle

schemas = (
    "fundus-family.v1.schema.json",
    "fundus-asset.v1.schema.json",
    "fundus-recipe.v1.schema.json",
    "fundus-recipe.v2.schema.json",
    "fundus-recipe.v3.schema.json",
    "fundus-build.v1.schema.json",
    "fundus-build.v2.schema.json",
    "fundus-acceptance.v1.schema.json",
    "fundus-acceptance.v2.schema.json",
    "fundus-package.v1.schema.json",
    "fundus-package.v2.schema.json",
    "fundus-consumer-lock.v1.schema.json",
    "fundus-ingest.v1.schema.json",
    "fundus-preview.v1.schema.json",
    "fundus-review-plan.v1.schema.json",
    "fundus-review-bundle.v1.schema.json",
    "fundus-image-brief.v1.schema.json",
)
assert ".whl/" in fundus_package.__file__
for name in schemas:
    json.loads(files("schauwerk.schemas").joinpath(name).read_text(encoding="utf-8"))

data = runtime_root / "data"
registry = runtime_root / "registry"
(registry / "recipes").mkdir(parents=True)
(registry / "assets").mkdir()
(registry / "families").mkdir()
source = runtime_root / "source.svg"
source.write_bytes(
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<path fill="#000" d="M0 0L10 0L10 10Z"/></svg>'
)
core = Fundus(FundusPaths(data_root=data, registry_root=registry))
ingest = core.ingest(source, origin="wheel-smoke", rights_status="owned")
recipe = {
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
(registry / "recipes" / "svg-mask-v1.json").write_text(
    json.dumps(recipe), encoding="utf-8"
)
family = {
    "schema_version": "schauwerk-fundus-family.v1",
    "id": "fixture.wheel-smoke-family",
    "title": "Wheel Smoke Review",
    "tags": ["wheel", "review"],
}
(registry / "families" / "fixture.wheel-smoke-family.json").write_text(
    json.dumps(family), encoding="utf-8"
)
asset = {
    "schema_version": "schauwerk-fundus-asset.v1",
    "id": "fixture.wheel-smoke",
    "family": "fixture.wheel-smoke-family",
    "recipe": "svg-mask-v1",
    "sources": [
        {
            "role": "trace_source",
            "sha256": ingest["sha256"],
            "media_type": "image/svg+xml",
        }
    ],
}
(registry / "assets" / "fixture.wheel-smoke.json").write_text(
    json.dumps(asset), encoding="utf-8"
)
build = core.build("fixture.wheel-smoke")
preview = core.preview("fixture.wheel-smoke", build_digest=build["build_digest"])
review = build_review_bundle(
    core,
    "fixture.wheel-smoke-family",
    runtime_root / "review",
)
review_check = check_review_bundle(runtime_root / "review")
acceptance = core.accept(
    "fixture.wheel-smoke",
    build_digest=build["build_digest"],
    reviewer="smoke:wheel",
    decision="accepted",
    reviewed_at="2026-08-13T12:00:00+00:00",
)
package = core.package(
    "fixture.wheel-smoke",
    build_digest=build["build_digest"],
    acceptance_digest=acceptance["acceptance_digest"],
)
recipe_v3 = {
    "schema_version": "schauwerk-fundus-recipe.v3",
    "id": "svg-mask-v3",
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
        }
    ],
    "acceptance": {
        "inheritance": "identical_sources_and_outputs_only",
    },
}
(registry / "recipes" / "svg-mask-v3.json").write_text(
    json.dumps(recipe_v3), encoding="utf-8"
)
asset["recipe"] = "svg-mask-v3"
(registry / "assets" / "fixture.wheel-smoke.json").write_text(
    json.dumps(asset), encoding="utf-8"
)
candidate = core.build("fixture.wheel-smoke")
inherited = core.inherit_acceptance(
    "fixture.wheel-smoke",
    build_digest=candidate["build_digest"],
    parent_build_digest=build["build_digest"],
    parent_acceptance_digest=acceptance["acceptance_digest"],
    inherited_by="smoke:wheel-operator",
    inherited_at="2026-08-14T14:00:00+00:00",
)
inherited_package = core.package(
    "fixture.wheel-smoke",
    build_digest=candidate["build_digest"],
    acceptance_digest=inherited["acceptance_digest"],
)
package_check = verify_package_directory(package["package_dir"])
consumer_lock = core.consumer_lock(package["package_dir"])
consumer_check = verify_consumer_lock(consumer_lock["lock_path"], package["package_dir"])
assert preview["network_dependencies"] is False
assert review["network_dependencies"] is False
assert review["portable"] is True
assert review_check["review_digest"] == review["review_digest"]
assert package["consumer_runtime_dependency"] is False
assert package_check["package_digest"] == package["package_digest"]
assert inherited["schema_version"] == "schauwerk-fundus-acceptance.v2"
assert inherited_package["acceptance_digest"] == inherited["acceptance_digest"]
assert consumer_check["package_digest"] == package["package_digest"]
assert consumer_check["lock_digest"] == consumer_lock["lock_digest"]
print(
    json.dumps(
        {
            "schemas": len(schemas),
            "review": review["review_digest"],
            "package": package["package_digest"],
            "inherited_package": inherited_package["package_digest"],
            "consumer_lock": consumer_lock["lock_digest"],
        }
    )
)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", smoke, str(wheels[0]), str(runtime_root)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["schemas"] == len(SCHEMAS)
    assert len(receipt["review"]) == 64
    assert len(receipt["package"]) == 64
    assert len(receipt["inherited_package"]) == 64
    assert len(receipt["consumer_lock"]) == 64
