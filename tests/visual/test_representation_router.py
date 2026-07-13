from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from schauwerk.runner import main
from schauwerk.visual.representation import (
    RepresentationError,
    compile_representation_package,
    load_representation_input,
    render_json_canvas,
    render_mermaid,
    render_miro_board,
    route_representation,
    validate_representation_input,
)
from schauwerk.visual.system_v2 import validate_board_spec

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-representation-v1.json"


def test_operator_fixture_matches_the_public_json_schema() -> None:
    schema = json.loads((ROOT / "schemas/representation-input.v1.schema.json").read_text())
    fixture = json.loads(FIXTURE.read_text())

    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(fixture)) == []


def test_router_selects_complementary_formats_with_explicit_reasons() -> None:
    model = load_representation_input(FIXTURE)
    plan = route_representation(model)

    assert plan["primary_format"] == "miro_native"
    assert plan["selected_formats"] == [
        "miro_native",
        "canvas",
        "document",
        "table",
        "mermaid",
    ]
    assert plan["hybrid"] is True
    assert all(plan["reasons"][name] for name in plan["selected_formats"])
    assert set(plan["decisions"]) == {"canvas", "document", "mermaid", "miro_native", "table"}
    assert all("selected" in decision for decision in plan["decisions"].values())
    assert plan["does_not_establish"] == [
        "aesthetic_quality",
        "provider_rendering_without_live_readback",
        "semantic_truth_of_source_claims",
    ]


@pytest.mark.parametrize(
    ("intent", "requirements", "expected"),
    [
        ("process", {"formal_relations": True}, "mermaid"),
        ("knowledge_map", {"free_spatial_layout": True}, "canvas"),
        ("comparison", {"structured_comparison": True}, "table"),
        ("narrative", {"rich_text": True}, "document"),
        ("presentation", {"presentation": True}, "miro_native"),
    ],
)
def test_router_selects_a_primary_format_without_explicit_requests(
    intent: str, requirements: dict[str, bool], expected: str
) -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["intent"] = intent
    raw["requirements"] = requirements
    raw["requested_formats"] = []
    plan = route_representation(validate_representation_input(raw))

    assert plan["primary_format"] == expected
    assert plan["decisions"][expected]["selected"] is True
    assert any(decision["selected"] is False for decision in plan["decisions"].values())


def test_mermaid_and_json_canvas_preserve_source_ids() -> None:
    model = load_representation_input(FIXTURE)
    plan = route_representation(model)

    mermaid = render_mermaid(model, plan)
    canvas = render_json_canvas(model, plan)

    assert mermaid.startswith("%% profile: mermaid-11.16.0-strict-source.v1\n")
    assert "flowchart LR" in mermaid
    assert "subgraph group_authority" in mermaid
    assert "click " not in mermaid
    assert "<script" not in mermaid.lower()
    for node in model["nodes"]:
        assert node["id"] in mermaid
    assert 'repositories[("Repositories")]' in mermaid
    assert 'quality_gate{"Prüfgate"}' in mermaid
    assert 'kill_switch{{"Kill-Switch"}}' in mermaid

    canvas_node_ids = {node["id"] for node in canvas["nodes"]}
    source_node_ids = {node["id"] for node in model["nodes"]}
    assert source_node_ids <= canvas_node_ids
    assert any(identifier.startswith("canvas_group_") for identifier in canvas_node_ids)
    for edge in canvas["edges"]:
        assert edge["fromNode"] in source_node_ids
        assert edge["toNode"] in source_node_ids


def test_mermaid_labels_neutralize_edge_delimiters() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["edges"][0]["label"] = "setzt | Priorität"
    model = validate_representation_input(raw)
    rendered = render_mermaid(model, route_representation(model))

    assert "setzt ¦ Priorität" in rendered
    assert "|setzt | Priorität|" not in rendered


def test_miro_renderer_uses_a_distinct_six_frame_composition() -> None:
    model = load_representation_input(FIXTURE)
    plan = route_representation(model)
    board = render_miro_board(model, plan)
    quality = validate_board_spec(board)

    assert len(board["frames"]) == 6
    assert board["entry_frame"] == "route_cover"
    assert board["presentation_path"] == board["reading_path"]
    assert quality["ok"] is True
    assert quality["score"] == 100
    assert quality["warnings"] == []
    assert len(quality["shape_types"]) >= 4
    assert quality["composition_profile"] == "miro-native-composition.v1"


def test_package_is_deterministic_and_manifest_bound(tmp_path: Path) -> None:
    first = compile_representation_package(input_path=FIXTURE, output_dir=tmp_path / "first")
    second = compile_representation_package(input_path=FIXTURE, output_dir=tmp_path / "second")

    assert first == second
    assert first["ok"] is True
    assert first["mutation_attempted"] is False
    expected = {
        "input.json",
        "route-plan.json",
        "diagram.mmd",
        "composition.canvas",
        "miro-board.json",
        "miro-board.dsl",
        "miro-quality.json",
        "overview.md",
        "nodes.tsv",
        "manifest.json",
        "receipt.json",
    }
    assert {path.name for path in (tmp_path / "first").iterdir()} == expected
    assert (tmp_path / "first").stat().st_mode & 0o777 == 0o700
    for name in expected:
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()

    manifest = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert manifest["package_digest"] == first["package_digest"]
    assert manifest["identity_contract"] == (
        "stable source ids are preserved wherever an item is materialized; "
        "coverage is explicit per renderer artifact"
    )
    artifacts = {item["role"]: item for item in manifest["artifacts"]}
    assert artifacts["mermaid_source"]["coverage"]["complete_nodes"] is True
    assert artifacts["mermaid_source"]["coverage"]["complete_edges"] is True
    assert artifacts["json_canvas"]["coverage"]["complete_nodes"] is True
    assert artifacts["json_canvas"]["coverage"]["complete_edges"] is True
    assert artifacts["miro_board_spec"]["coverage"]["complete_nodes"] is True
    assert artifacts["miro_board_spec"]["coverage"]["complete_edges"] is False


def test_cli_compiles_the_same_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "package"
    assert (
        main(
            [
                "visual",
                "route",
                str(FIXTURE),
                "--output-dir",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["schema_version"] == "schauwerk-representation-receipt.v1"
    assert emitted["ok"] is True
    assert (output / "composition.canvas").is_file()


def test_unknown_edge_target_fails_closed() -> None:
    raw = json.loads(FIXTURE.read_text())
    changed = copy.deepcopy(raw)
    changed["edges"][0]["to"] = "missing"

    with pytest.raises(RepresentationError, match="unknown node"):
        validate_representation_input(changed)


def test_requested_format_must_be_a_known_string() -> None:
    raw = json.loads(FIXTURE.read_text())
    raw["requested_formats"] = [{"not": "a string"}]

    with pytest.raises(RepresentationError, match="requested_formats"):
        validate_representation_input(raw)


def test_output_path_rejects_symlink_chain(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="must not contain symlinks"):
        compile_representation_package(input_path=FIXTURE, output_dir=linked / "package")
    assert not (target / "package").exists()
