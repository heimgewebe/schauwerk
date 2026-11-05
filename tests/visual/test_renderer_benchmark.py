"""Executable coverage for the opt-in Schaubild A/B renderer benchmark."""
from __future__ import annotations

import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = ROOT / "scripts" / "schaubild_renderer_benchmark.py"
spec = importlib.util.spec_from_file_location("schaubild_renderer_benchmark", BENCHMARK_PATH)
assert spec is not None and spec.loader is not None
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

GOLDEN = ROOT / "docs" / "operators" / "fixtures" / "golden" / "decision-flow-v1.json"


def _model() -> dict:
    from schauwerk.visual.representation import validate_representation_input

    return validate_representation_input(json.loads(GOLDEN.read_text(encoding="utf-8")))


def test_graphviz_source_preserves_all_semantic_ids_groups_and_labels() -> None:
    model = _model()
    dot = benchmark.graphviz_source(model)
    assert dot.startswith("digraph schauwerk {")
    for group in model["groups"]:
        assert f"subgraph cluster_g_{group['id']}" in dot
        assert f'id="sw-group-{group["id"]}"' in dot
        assert benchmark._quoted(group["label"]) in dot
    for node in model["nodes"]:
        assert f"n_{node['id']} [" in dot
        assert f'id="sw-node-{node["id"]}"' in dot
        assert benchmark._quoted(benchmark._display_node(node)) in dot
    for edge in model["edges"]:
        assert f"n_{edge['from']} -> n_{edge['to']}" in dot
        assert f'id="sw-edge-{edge["id"]}"' in dot
        assert benchmark._quoted(benchmark._edge_label(edge)) in dot
    assert dot.endswith("}\n")


def test_d2_source_preserves_all_semantic_labels_and_group_references() -> None:
    model = _model()
    d2 = benchmark.d2_source(model)
    assert d2.startswith("direction: right\n")
    for group in model["groups"]:
        assert f"g_{group['id']}: " in d2
        assert benchmark._quoted(group["label"]) in d2
    for node in model["nodes"]:
        assert f"n_{node['id']}: " in d2
        assert benchmark._quoted(benchmark._display_node(node)) in d2
    for edge in model["edges"]:
        src = next(n for n in model["nodes"] if n["id"] == edge["from"])
        dst = next(n for n in model["nodes"] if n["id"] == edge["to"])
        from_key = f"g_{src['group']}.n_{src['id']}" if src["group"] else f"n_{src['id']}"
        to_key = f"g_{dst['group']}.n_{dst['id']}" if dst["group"] else f"n_{dst['id']}"
        assert f"{from_key} -> {to_key}: " in d2
        assert benchmark._quoted(benchmark._edge_label(edge)) in d2


def test_svg_coverage_detects_missing_edges_in_graphviz() -> None:
    model = _model()
    ids = [
        *(f"sw-node-{n['id']}" for n in model["nodes"]),
        *(f"sw-edge-{e['id']}" for e in model["edges"][:-1]),
        *(f"sw-group-{g['id']}" for g in model["groups"]),
    ]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        + "".join(f'<g id="{identifier}"/>' for identifier in ids)
        + "</svg>"
    ).encode()
    report = benchmark._id_coverage(svg, model, "graphviz-dot")
    assert report["status"] == "incomplete"
    assert report["missing_edges"] == [model["edges"][-1]["id"]]


def test_d2_svg_coverage_never_claims_unverified_source_identifiers() -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    report = benchmark._id_coverage(svg, _model(), "d2-dagre")
    assert report["status"] == "unverified"
    assert report["expected_edges"] == len(_model()["edges"])


def test_native_baseline_renders_valid_svg_and_binds_output(tmp_path: Path) -> None:
    result = benchmark.run_benchmark([GOLDEN], tmp_path / "ab", ("native",))
    assert result["schema_version"] == "schauwerk-renderer-evaluation.v1"
    case = result["cases"][0]
    info = case["engines"]["native"]
    assert info["status"] == "ok", info
    assert info["svg_id_coverage"]["status"] == "complete"
    svg = (tmp_path / "ab" / GOLDEN.stem / "native.svg").read_bytes()
    root = ET.fromstring(svg)
    assert root.attrib["data-renderer"] == "schauwerk-native-diagram-v1"
    assert info["svg_sha256"] == benchmark._digest(svg)
    assert case["normalized_input_digest"] == root.attrib["data-input-digest"]
    assert (tmp_path / "ab" / "manifest.json").is_file()


def test_unavailable_optional_engine_is_explicit_without_breaking_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark.shutil, "which", lambda _cmd: None)
    report = benchmark.run_benchmark(
        [GOLDEN], tmp_path / "ab", ("native", "d2-dagre", "graphviz-dot"),
    )
    row = report["cases"][0]["engines"]
    assert row["native"]["status"] == "ok"
    assert row["d2-dagre"]["status"] == "unavailable"
    assert row["graphviz-dot"]["status"] == "unavailable"
    assert (tmp_path / "ab" / GOLDEN.stem / "graphviz-dot.dot").is_file()
    assert (tmp_path / "ab" / GOLDEN.stem / "d2-dagre.d2").is_file()
    assert not (tmp_path / "ab" / GOLDEN.stem / "d2-dagre.svg").exists()


def test_d2_subprocess_is_limited_and_failure_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark.shutil, "which", lambda _cmd: "/test/d2")
    argv_seen: list[str] = []

    def fake_run(argv, **kwargs):
        argv_seen.extend(argv)
        assert kwargs["timeout"] == benchmark.ENGINE_TIMEOUT_SECONDS
        assert kwargs["check"] is False
        assert b"direction: right" in kwargs["input"]
        return SimpleNamespace(
            returncode=0, stdout=b'<svg xmlns="http://www.w3.org/2000/svg"/>', stderr=b"",
        )

    monkeypatch.setattr(benchmark.subprocess, "run", fake_run)
    report = benchmark.run_benchmark([GOLDEN], tmp_path / "ab", ("d2-elk",))
    info = report["cases"][0]["engines"]["d2-elk"]
    assert argv_seen == ["/test/d2", "--layout=elk", "-", "-"]
    assert info["status"] == "ok"
    assert info["svg_id_coverage"]["status"] == "unverified"


def test_unknown_engine_and_existing_directory_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown or duplicate"):
        benchmark.run_benchmark([GOLDEN], tmp_path / "bad", ("native", "invented"))
    output = tmp_path / "ab"
    output.mkdir()
    with pytest.raises(FileExistsError):
        benchmark.run_benchmark([GOLDEN], output, ("native",))


@pytest.mark.skipif(not shutil.which("dot"), reason="Graphviz is optional")
def test_real_graphviz_retains_ids_on_golden(tmp_path: Path) -> None:
    result = benchmark.run_benchmark([GOLDEN], tmp_path / "dot", ("graphviz-dot",))
    info = result["cases"][0]["engines"]["graphviz-dot"]
    assert info["status"] == "ok", info
    assert info["svg_id_coverage"]["status"] == "complete"
