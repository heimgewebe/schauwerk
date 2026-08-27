from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import schauwerk.visual.representation as representation
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


def _minimal_representation(
    *,
    node_count: int = 2,
    requested_formats: list[str] | None = None,
    self_loop: bool = False,
    long_labels: bool = False,
) -> dict[str, object]:
    nodes = [
        {
            "id": f"n{index}",
            "label": "L" * 120 if long_labels else f"Knoten {index}",
            "kind": "concept",
            "group": "g",
            "summary": "",
        }
        for index in range(node_count)
    ]
    edges = [
        {
            "id": f"e{index}",
            "from": f"n{index}",
            "to": f"n{index}" if self_loop and index == 0 else f"n{index + 1}",
            "label": "R" * 120 if long_labels else "führt zu",
            "kind": "flow",
        }
        for index in range(max(1 if self_loop else 0, node_count - 1))
    ]
    return {
        "schema_version": "schauwerk-representation-input.v1",
        "id": "probe",
        "title": "Probe",
        "purpose": "Generator regression probe",
        "intent": "process",
        "groups": [{"id": "g", "label": "Gruppe"}],
        "nodes": nodes,
        "edges": edges,
        "requirements": {},
        "requested_formats": requested_formats or [],
    }


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
    assert "subgraph sw_group_authority" in mermaid
    assert "click " not in mermaid
    assert "<script" not in mermaid.lower()
    for node in model["nodes"]:
        assert node["id"] in mermaid
    assert 'sw_node_repositories[("Repositories")]' in mermaid
    assert 'sw_node_quality_gate{"Prüfgate"}' in mermaid
    assert 'sw_node_kill_switch{{"Kill-Switch"}}' in mermaid
    assert "%% source-node-id: repositories" in mermaid
    assert "%% source-edge-id:" in mermaid

    canvas_node_ids = {node["id"] for node in canvas["nodes"]}
    source_node_ids = {node["id"] for node in model["nodes"]}
    assert {f"canvas_node:{identifier}" for identifier in source_node_ids} <= canvas_node_ids
    assert any(identifier.startswith("canvas_group:") for identifier in canvas_node_ids)
    for edge in canvas["edges"]:
        assert edge["id"].startswith("canvas_edge:")
        assert edge["fromNode"] in canvas_node_ids
        assert edge["toNode"] in canvas_node_ids


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
        "miro-execution-plan.json",
        "miro-board.json",
        "miro-board.dsl",
        "miro-quality.json",
        "overview.md",
        "nodes.tsv",
        "miro-native-bundle.json",
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
        "coverage, when present, measures stable source-id materialization in the "
        "emitted renderer artifact; it does not establish semantic or visual completeness"
    )
    artifacts = {item["role"]: item for item in manifest["artifacts"]}
    execution_plan = json.loads((tmp_path / "first" / "miro-execution-plan.json").read_text())
    assert execution_plan["schema_version"] == "schauwerk-miro-execution-plan.v1"
    assert artifacts["miro_execution_plan"]["sha256"]
    assert artifacts["mermaid_source"]["coverage"]["complete_nodes"] is True
    assert artifacts["mermaid_source"]["coverage"]["complete_edges"] is True
    assert artifacts["json_canvas"]["coverage"]["complete_nodes"] is True
    assert artifacts["json_canvas"]["coverage"]["complete_edges"] is True
    assert artifacts["miro_board_spec"]["coverage"]["complete_nodes"] is True
    assert artifacts["miro_board_spec"]["coverage"]["complete_edges"] is False
    assert artifacts["narrative_document"]["coverage"]["complete_nodes"] is False
    assert artifacts["narrative_document"]["coverage"]["complete_edges"] is False
    assert all(
        item["coverage"].get("coverage_kind") == "source_id_materialization"
        for item in artifacts.values()
        if "coverage" in item
    )


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

def test_runtime_validation_matches_public_schema_for_boolean_and_unknown_fields() -> None:
    raw = _minimal_representation(requested_formats=["mermaid"])
    raw["requirements"] = {"formal_relations": "false"}
    with pytest.raises(RepresentationError, match="must be a boolean"):
        validate_representation_input(raw)

    raw = _minimal_representation()
    raw["extra_root"] = True
    with pytest.raises(RepresentationError, match="unknown fields"):
        validate_representation_input(raw)

    raw = _minimal_representation()
    raw["nodes"][0]["extra_node"] = "unexpected"
    with pytest.raises(RepresentationError, match="unknown fields"):
        validate_representation_input(raw)

    normalized = validate_representation_input(_minimal_representation())
    with pytest.raises(RepresentationError, match="unknown fields"):
        validate_representation_input(normalized)
    assert route_representation(normalized)["input_digest"] == normalized["input_digest"]


def test_requested_formats_reject_duplicates_instead_of_silently_rewriting_input() -> None:
    raw = _minimal_representation(requested_formats=["canvas", "canvas"])
    with pytest.raises(RepresentationError, match="must not contain duplicates"):
        validate_representation_input(raw)


def test_renderers_reject_a_tampered_route_plan() -> None:
    model = validate_representation_input(_minimal_representation(requested_formats=["mermaid"]))
    plan = route_representation(model)
    tampered = copy.deepcopy(plan)
    tampered["primary_format"] = "canvas"

    with pytest.raises(RepresentationError, match="plan digest mismatch"):
        render_mermaid(model, tampered)


def test_mermaid_uses_renderer_local_ids_for_reserved_source_identifiers() -> None:
    raw = _minimal_representation(node_count=2, requested_formats=["mermaid"])
    raw["nodes"][0]["id"] = "end"
    raw["edges"][0]["from"] = "end"
    model = validate_representation_input(raw)
    rendered = render_mermaid(model, route_representation(model))

    assert "%% source-node-id: end" in rendered
    assert "sw_node_end" in rendered
    assert "class sw_node_end concept;" in rendered


def test_json_canvas_uses_vertical_anchors_for_same_column_edges() -> None:
    model = validate_representation_input(_minimal_representation(requested_formats=["canvas"]))
    canvas = render_json_canvas(model, route_representation(model))
    edge = canvas["edges"][0]

    assert edge["fromSide"] == "bottom"
    assert edge["toSide"] == "top"


def test_json_canvas_generated_group_ids_cannot_collide_with_source_nodes() -> None:
    raw = _minimal_representation(requested_formats=["canvas"])
    raw["groups"] = [{"id": "authority", "label": "Authority"}]
    raw["nodes"][0]["id"] = "canvas_group_authority"
    raw["nodes"][0]["group"] = "authority"
    raw["nodes"][1]["group"] = "authority"
    raw["edges"][0]["from"] = "canvas_group_authority"
    model = validate_representation_input(raw)
    canvas = render_json_canvas(model, route_representation(model))
    ids = [item["id"] for item in canvas["nodes"]]

    assert "canvas_node:canvas_group_authority" in ids
    assert "canvas_group:authority" in ids
    assert len(ids) == len(set(ids))


def test_miro_homogeneous_relations_are_a_risk_not_a_generation_blocker() -> None:
    model = validate_representation_input(
        _minimal_representation(node_count=8, requested_formats=["miro_native"])
    )
    board = render_miro_board(model, route_representation(model))
    quality = validate_board_spec(board)

    assert quality["ok"] is True
    assert not any(item["code"] == "relation_grammar" for item in quality["blockers"])
    assert any(item["code"] == "relation_grammar" for item in quality["warnings"])
    assert any(item["code"] == "relation_grammar" for item in quality["visual_risks"])
    evidence = next(
        item["content"]
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("id") == "route_evidence_card"
    )
    assert "Miro-Auszug 8/8 Knoten · 4/7 Beziehungen" in evidence


def test_miro_self_loop_and_maximum_legal_labels_do_not_crash_quality_gate() -> None:
    self_model = validate_representation_input(
        _minimal_representation(node_count=2, requested_formats=["miro_native"], self_loop=True)
    )
    self_quality = validate_board_spec(
        render_miro_board(self_model, route_representation(self_model))
    )
    assert self_quality["ok"] is True
    assert not any(
        item["code"] == "connector_label_collision" for item in self_quality["blockers"]
    )

    long_model = validate_representation_input(
        _minimal_representation(
            node_count=4, requested_formats=["miro_native"], long_labels=True
        )
    )
    long_quality = validate_board_spec(
        render_miro_board(long_model, route_representation(long_model))
    )
    assert long_quality["ok"] is True


def test_miro_coverage_cannot_be_faked_by_decorative_id_collision() -> None:
    raw = _minimal_representation(node_count=11, requested_formats=["miro_native"])
    raw["nodes"][-1]["id"] = "route_entry"
    raw["edges"][-1]["to"] = "route_entry"
    model = validate_representation_input(raw)
    board = render_miro_board(model, route_representation(model))
    coverage = representation._miro_coverage(model, board)

    assert coverage["complete_nodes"] is False
    assert "route_entry" not in coverage["node_ids"]
    evidence = next(
        item["content"]
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("id") == "route_evidence_card"
    )
    assert "Miro-Auszug 10/11 Knoten" in evidence


def test_package_failure_does_not_publish_partial_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(_minimal_representation(node_count=8, requested_formats=["miro_native"])),
        encoding="utf-8",
    )
    target = tmp_path / "package"

    def fail_render(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic renderer failure")

    monkeypatch.setattr(representation, "render_miro_board", fail_render)
    with pytest.raises(RuntimeError, match="synthetic renderer failure"):
        representation.compile_representation_package(
            input_path=input_path, output_dir=target
        )

    assert not target.exists()
    assert list(tmp_path.glob(".package.tmp-*")) == []


def test_output_path_rejects_dangling_symlink_chain(tmp_path: Path) -> None:
    linked = tmp_path / "dangling"
    linked.symlink_to(tmp_path / "missing", target_is_directory=True)

    with pytest.raises(ValueError, match="must not contain symlinks"):
        compile_representation_package(input_path=FIXTURE, output_dir=linked / "package")

def test_runtime_rejects_raw_text_that_only_fits_after_whitespace_normalization() -> None:
    raw = _minimal_representation()
    raw["title"] = "A" + (" " * 160)
    with pytest.raises(RepresentationError, match="exceeds 160 characters"):
        validate_representation_input(raw)


def test_renderer_rejects_self_consistently_rehashed_non_router_plan() -> None:
    model = validate_representation_input(_minimal_representation(requested_formats=["mermaid"]))
    plan = route_representation(model)
    tampered = copy.deepcopy(plan)
    tampered["primary_format"] = "canvas"
    body = {key: value for key, value in tampered.items() if key != "plan_digest"}
    tampered["plan_digest"] = representation._digest(body)

    with pytest.raises(RepresentationError, match="deterministic router decision"):
        render_mermaid(model, tampered)


def test_canvas_node_and_edge_namespaces_are_disjoint_for_equal_source_ids() -> None:
    raw = _minimal_representation(requested_formats=["canvas"])
    raw["nodes"][0]["id"] = "shared"
    raw["edges"][0]["id"] = "shared"
    raw["edges"][0]["from"] = "shared"
    model = validate_representation_input(raw)
    canvas = render_json_canvas(model, route_representation(model))
    node_ids = {item["id"] for item in canvas["nodes"]}
    edge_ids = {item["id"] for item in canvas["edges"]}

    assert "canvas_node:shared" in node_ids
    assert "canvas_edge:shared" in edge_ids
    assert node_ids.isdisjoint(edge_ids)
    coverage = representation._canvas_coverage(model, canvas)
    assert coverage["complete_nodes"] is True
    assert coverage["complete_edges"] is True


def test_miro_self_loop_retains_source_bound_relation_identity() -> None:
    model = validate_representation_input(
        _minimal_representation(node_count=2, requested_formats=["miro_native"], self_loop=True)
    )
    board = render_miro_board(model, route_representation(model))
    source_edge = next(
        item
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("source_kind") == "edge" and item.get("source_id") == "e0"
    )

    assert source_edge["id"] == "source_edge_e0"
    assert source_edge["relation_type"] == "flow"
    assert "↺" in source_edge["content"]
    assert representation._miro_coverage(model, board)["edge_ids"] == ["e0"]


def test_compiled_public_input_is_schema_exact_and_digest_is_externalized(tmp_path: Path) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    output_dir = tmp_path / "package"
    receipt = compile_representation_package(input_path=input_path, output_dir=output_dir)
    public_input = json.loads((output_dir / "input.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/representation-input.v1.schema.json").read_text())

    Draft202012Validator(schema).validate(public_input)
    assert "input_digest" not in public_input
    assert len(receipt["input_digest"]) == 64


def test_package_publish_rejects_world_writable_non_sticky_parent(tmp_path: Path) -> None:
    parent = tmp_path / "unsafe"
    parent.mkdir(mode=0o700)
    parent.chmod(0o777)
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")

    with pytest.raises(RepresentationError, match="output parent is unsafe"):
        compile_representation_package(input_path=input_path, output_dir=parent / "package")
    assert list(parent.iterdir()) == []


def test_package_publish_detects_target_appearing_during_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original = representation._compile_representation_package_into

    def compile_then_race(*, input_path: Path, output_dir: Path) -> dict[str, object]:
        receipt = original(input_path=input_path, output_dir=output_dir)
        target.mkdir(mode=0o700)
        return receipt

    monkeypatch.setattr(representation, "_compile_representation_package_into", compile_then_race)
    with pytest.raises(RepresentationError, match="target appeared"):
        representation.compile_representation_package(input_path=input_path, output_dir=target)

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert list(tmp_path.glob(".package.tmp-*")) == []
