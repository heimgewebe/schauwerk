from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk.runner import main
from schauwerk.visual.preview import (
    VisualPreviewError,
    build_visual_preview,
    compare_visual_previews,
    load_visual_preview,
)
from schauwerk.visual.representation import (
    compile_representation_package,
    load_representation_input,
    render_miro_board,
    route_representation,
)
from schauwerk.visual.system_v2 import finalize_board_spec

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-representation-v1.json"
SCHEMAS = ("visual-preview.v1.schema.json", "visual-regression.v1.schema.json")


def _package(tmp_path: Path, name: str, *, input_path: Path = FIXTURE) -> Path:
    destination = tmp_path / name
    compile_representation_package(input_path=input_path, output_dir=destination)
    return destination


def _preview(tmp_path: Path, name: str, *, package: Path) -> tuple[dict, Path]:
    destination = tmp_path / name
    receipt = build_visual_preview(package_dir=package, output_dir=destination)
    return receipt, destination


def test_preview_is_deterministic_private_and_fully_bound(tmp_path: Path) -> None:
    first_package = _package(tmp_path, "package-first")
    second_package = _package(tmp_path, "package-second")
    first_receipt, first = _preview(tmp_path, "preview-first", package=first_package)
    second_receipt, second = _preview(tmp_path, "preview-second", package=second_package)

    assert first_receipt["ok"] is True
    assert first_receipt["blocker_count"] == 0
    assert first_receipt["warning_count"] >= 1
    assert first_receipt["mutation_attempted"] is False
    assert first_receipt["preview_digest"] == second_receipt["preview_digest"]
    assert (first / "preview.json").read_bytes() == (second / "preview.json").read_bytes()
    assert (first / "index.html").read_bytes() == (second / "index.html").read_bytes()

    first_files = {item.name: item for item in first.iterdir()}
    second_files = {item.name: item for item in second.iterdir()}
    assert set(first_files) == set(second_files)
    assert set(first_files) == {
        "index.html",
        "preview.json",
        *(
            f"frame-{index:02d}-{frame_id}.svg"
            for index, frame_id in enumerate(
                (
                    "route_cover",
                    "route_map",
                    "route_architecture",
                    "route_decision",
                    "route_delivery",
                    "route_evidence",
                ),
                start=1,
            )
        ),
    }
    for name in first_files:
        assert first_files[name].read_bytes() == second_files[name].read_bytes()
        assert first_files[name].stat().st_mode & 0o077 == 0
    assert first.stat().st_mode & 0o077 == 0

    manifest = load_visual_preview(first / "preview.json")
    assert manifest["preview_digest"] == first_receipt["preview_digest"]
    assert manifest["index_sha256"]
    assert all(frame["svg_sha256"] for frame in manifest["frames"])
    html = (first / "index.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    assert "https://" not in html.lower()
    assert "http://" not in html.lower()


def test_quality_gate_blocks_the_previous_auto_sized_table_overlap_before_preview() -> None:
    model = load_representation_input(FIXTURE)
    plan = route_representation(model)
    board = render_miro_board(model, plan)
    frames = copy.deepcopy(board["frames"])
    decision = next(frame for frame in frames if frame["id"] == "route_decision")
    delivery = next(frame for frame in frames if frame["id"] == "route_delivery")
    moved = [item for item in delivery["objects"] if item["id"] in {"quality_gate", "kill_switch"}]
    delivery["objects"] = [
        item for item in delivery["objects"] if item["id"] not in {"quality_gate", "kill_switch"}
    ]
    decision["objects"].extend(moved)

    with pytest.raises(ValueError, match="object_overlap"):
        finalize_board_spec(
            title=board["title"],
            purpose=board["purpose"],
            frames=frames,
        )


def test_preview_comparison_detects_new_text_overflow(tmp_path: Path) -> None:
    baseline_package = _package(tmp_path, "baseline-package")
    _, baseline_dir = _preview(tmp_path, "baseline-preview", package=baseline_package)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["nodes"][0]["label"] = "Sehr langer visueller Knotentitel " * 3
    candidate_input = tmp_path / "candidate-input.json"
    candidate_input.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    candidate_package = _package(tmp_path, "candidate-package", input_path=candidate_input)
    _, candidate_dir = _preview(tmp_path, "candidate-preview", package=candidate_package)

    baseline = load_visual_preview(baseline_dir / "preview.json")
    candidate = load_visual_preview(candidate_dir / "preview.json")
    comparison = compare_visual_previews(baseline, candidate)

    assert candidate["blocker_count"] > baseline["blocker_count"]
    assert candidate["issue_counts"]["text_overflow"] >= 1
    assert comparison["ok"] is False
    assert comparison["regression"] is True
    assert comparison["new_blockers"]
    assert f"route_map/{raw['nodes'][0]['id']}" in comparison["changed_objects"]


def test_identical_previews_compare_without_regression(tmp_path: Path) -> None:
    package = _package(tmp_path, "package")
    _, first = _preview(tmp_path, "preview-one", package=package)
    _, second = _preview(tmp_path, "preview-two", package=package)

    comparison = compare_visual_previews(
        load_visual_preview(first / "preview.json"),
        load_visual_preview(second / "preview.json"),
    )

    assert comparison["ok"] is True
    assert comparison["regression"] is False
    assert comparison["new_blockers"] == []
    assert comparison["changed_objects"] == []
    assert comparison["moved_objects"] == []


def test_preview_rejects_tampered_or_extra_artifacts(tmp_path: Path) -> None:
    package = _package(tmp_path, "package")
    _, preview = _preview(tmp_path, "preview", package=package)
    frame = next(preview.glob("frame-*.svg"))
    frame.write_text(frame.read_text(encoding="utf-8") + "<!-- tampered -->\n", encoding="utf-8")

    with pytest.raises(VisualPreviewError, match="does not match its receipt"):
        load_visual_preview(preview / "preview.json")

    _, second = _preview(tmp_path, "preview-second", package=package)
    extra = second / "unexpected.txt"
    extra.write_text("unexpected", encoding="utf-8")
    os.chmod(extra, 0o600)
    with pytest.raises(VisualPreviewError, match="file set is not exact"):
        load_visual_preview(second / "preview.json")

    _, third = _preview(tmp_path, "preview-third", package=package)
    manifest_path = third / "preview.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frames"][0]["objects"][0]["content_digest"] = "f" * 64
    body = dict(manifest)
    body.pop("preview_digest")
    manifest["preview_digest"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(VisualPreviewError, match="digest mismatch"):
        load_visual_preview(manifest_path)


def test_preview_allows_atomic_private_child_of_system_tmp(tmp_path: Path) -> None:
    package = _package(tmp_path, "package-system-tmp")
    destination = Path("/tmp") / f"schauwerk-preview-{tmp_path.name}"
    assert not destination.exists() and not destination.is_symlink()
    try:
        receipt = build_visual_preview(package_dir=package, output_dir=destination)
        assert receipt["ok"] is True
        assert destination.stat().st_mode & 0o077 == 0
        assert load_visual_preview(destination / "preview.json")["blocker_count"] == 0
    finally:
        if destination.is_dir() and not destination.is_symlink():
            for item in destination.iterdir():
                item.unlink()
            destination.rmdir()


def test_preview_rejects_unsafe_output_paths(tmp_path: Path) -> None:
    package = _package(tmp_path, "package")
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o700)
    with pytest.raises(VisualPreviewError, match="must be absent"):
        build_visual_preview(package_dir=package, output_dir=existing)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(VisualPreviewError, match="must not contain symlinks"):
        build_visual_preview(package_dir=package, output_dir=linked / "preview")


def test_public_and_packaged_schemas_are_identical_and_validate_outputs(tmp_path: Path) -> None:
    package = _package(tmp_path, "package")
    _, first = _preview(tmp_path, "preview-one", package=package)
    _, second = _preview(tmp_path, "preview-two", package=package)
    preview = load_visual_preview(first / "preview.json")
    regression = compare_visual_previews(preview, load_visual_preview(second / "preview.json"))

    outputs = {
        "visual-preview.v1.schema.json": preview,
        "visual-regression.v1.schema.json": regression,
    }
    for name in SCHEMAS:
        public = ROOT / "schemas" / name
        packaged = ROOT / "src" / "schauwerk" / "schemas" / name
        assert public.read_bytes() == packaged.read_bytes()
        schema = json.loads(public.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert list(Draft202012Validator(schema).iter_errors(outputs[name])) == []


def test_cli_builds_and_compares_visual_previews(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = tmp_path / "package"
    assert (
        main(
            [
                "visual",
                "route",
                str(FIXTURE),
                "--output-dir",
                str(package),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    first = tmp_path / "preview-first"
    second = tmp_path / "preview-second"
    for destination in (first, second):
        assert (
            main(
                [
                    "visual",
                    "preview",
                    str(package),
                    "--output-dir",
                    str(destination),
                    "--json",
                ]
            )
            == 0
        )
        emitted = json.loads(capsys.readouterr().out)
        assert emitted["schema_version"] == "schauwerk-visual-preview.v1"
        assert emitted["ok"] is True
        assert emitted["mutation_attempted"] is False

    output = tmp_path / "regression.json"
    assert (
        main(
            [
                "visual",
                "compare",
                str(first / "preview.json"),
                str(second / "preview.json"),
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["schema_version"] == "schauwerk-visual-regression.v1"
    assert emitted["ok"] is True
    assert emitted["mutation_attempted"] is False
    assert output.is_file()
