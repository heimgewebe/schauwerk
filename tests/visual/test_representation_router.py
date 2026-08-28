from __future__ import annotations

import copy
import errno
import json
import os
import stat
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


def _assert_private_tombstones(root: Path, target_name: str = "package") -> list[Path]:
    tombstones = sorted(root.glob(f".{target_name}.tmp-*"))
    for tombstone in tombstones:
        assert tombstone.is_dir()
        assert tombstone.stat().st_mode & 0o777 == 0o700
        for entry in tombstone.iterdir():
            current = entry.lstat()
            assert stat.S_ISREG(current.st_mode)
            assert current.st_size == 0
            assert stat.S_IMODE(current.st_mode) & 0o077 == 0
    return tombstones


def _assert_scrubbed_compiler_entries(directory: Path) -> None:
    entries = list(directory.iterdir())
    assert entries
    for entry in entries:
        current = entry.lstat()
        assert stat.S_ISREG(current.st_mode)
        assert current.st_size == 0
        assert stat.S_IMODE(current.st_mode) & 0o077 == 0


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
    assert len(_assert_private_tombstones(tmp_path)) == 1

    monkeypatch.undo()
    retry = representation.compile_representation_package(
        input_path=input_path, output_dir=target
    )
    assert retry["ok"] is True
    assert target.is_dir()


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


def test_miro_self_loop_with_ordinary_relation_does_not_overlap() -> None:
    model = validate_representation_input(
        _minimal_representation(node_count=3, requested_formats=["miro_native"], self_loop=True)
    )
    board = render_miro_board(model, route_representation(model))

    assert validate_board_spec(board)["ok"] is True
    assert representation._miro_coverage(model, board)["edge_ids"] == ["e0", "e1"]
    relation_legend = next(
        item["content"]
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("id") == "route_map_relations"
    )
    assert "weitere Beziehungen" not in relation_legend


def test_miro_two_self_loops_stay_clear_of_frame_thesis() -> None:
    raw = _minimal_representation(
        node_count=3, requested_formats=["miro_native"], self_loop=True
    )
    raw["edges"][1]["from"] = "n1"
    raw["edges"][1]["to"] = "n1"
    model = validate_representation_input(raw)
    board = render_miro_board(model, route_representation(model))

    assert validate_board_spec(board)["ok"] is True
    assert representation._miro_coverage(model, board)["edge_ids"] == ["e0", "e1"]


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

    def compile_then_race(
        *, input_path: Path, output_fd: int, owned_fds: dict[str, int]
    ) -> dict[str, object]:
        receipt = original(
            input_path=input_path, output_fd=output_fd, owned_fds=owned_fds
        )
        target.mkdir(mode=0o700)
        return receipt

    monkeypatch.setattr(representation, "_compile_representation_package_into", compile_then_race)
    with pytest.raises(RepresentationError, match="target must be absent"):
        representation.compile_representation_package(input_path=input_path, output_dir=target)

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert len(_assert_private_tombstones(tmp_path)) == 1


def test_package_publish_rejects_preexisting_empty_target(tmp_path: Path) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    target.mkdir(mode=0o700)

    with pytest.raises(RepresentationError, match="target must be absent"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_package_publish_noreplace_closes_final_target_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original = representation._rename_noreplace

    def race(parent_fd: int, source_name: str, target_name: str) -> None:
        os.mkdir(target_name, 0o700, dir_fd=parent_fd)
        original(parent_fd, source_name, target_name)

    monkeypatch.setattr(representation, "_rename_noreplace", race)
    with pytest.raises(RepresentationError, match="target appeared while publishing"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert len(_assert_private_tombstones(tmp_path)) == 1


def test_package_publish_detects_parent_swap_in_final_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    old_parent = tmp_path / "old-parent"
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    original = representation._rename_noreplace

    def swap_parent_then_publish(parent_fd: int, source_name: str, target_name: str) -> None:
        parent.rename(old_parent)
        replacement.rename(parent)
        original(parent_fd, source_name, target_name)

    monkeypatch.setattr(representation, "_rename_noreplace", swap_parent_then_publish)
    with pytest.raises(RepresentationError, match="parent identity changed during publication"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert not (parent / "package").exists()
    old_target = old_parent / "package"
    assert old_target.is_dir()
    assert old_target.stat().st_mode & 0o777 == 0o700
    _assert_scrubbed_compiler_entries(old_target)
    assert _assert_private_tombstones(old_parent) == []


def test_package_staging_writes_remain_fd_bound_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    old_parent = tmp_path / "old-parent"
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    original = representation._compile_representation_package_into

    def swap_then_compile(
        *, input_path: Path, output_fd: int, owned_fds: dict[str, int]
    ) -> dict[str, object]:
        parent.rename(old_parent)
        replacement.rename(parent)
        return original(
            input_path=input_path, output_fd=output_fd, owned_fds=owned_fds
        )

    monkeypatch.setattr(representation, "_compile_representation_package_into", swap_then_compile)
    with pytest.raises(RepresentationError, match="output parent identity changed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert list(parent.iterdir()) == []
    assert not (old_parent / "package").exists()
    assert len(_assert_private_tombstones(old_parent)) == 1


def test_bound_cleanup_preserves_substituted_directory(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    staging_fd: int | None = None
    owned_fds: dict[str, int] = {}
    try:
        staging_name, staging_fd, expected = representation._create_private_staging(
            parent_fd, "package"
        )
        representation._write_text(
            staging_fd, "overview.md", "compiler-owned", owned_fds=owned_fds
        )
        moved_name = ".moved-owned-staging"
        os.rename(
            staging_name,
            moved_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        (parent / staging_name / "marker.txt").write_text("unrelated", encoding="utf-8")

        scrubbed, namespace_clean = representation._cleanup_bound_directory(
            parent_fd, staging_name, staging_fd, expected, owned_fds
        )

        assert scrubbed is True
        assert namespace_clean is False
        assert (parent / staging_name / "marker.txt").read_text() == "unrelated"
        owned = parent / moved_name / "overview.md"
        assert owned.is_file()
        assert owned.stat().st_size == 0
    finally:
        for descriptor in owned_fds.values():
            os.close(descriptor)
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(parent_fd)


def test_miro_two_loops_disclose_one_real_omission() -> None:
    raw = _minimal_representation(
        node_count=3, requested_formats=["miro_native"], self_loop=True
    )
    raw["edges"][1]["from"] = "n1"
    raw["edges"][1]["to"] = "n1"
    raw["edges"].append(
        {
            "id": "e2",
            "from": "n1",
            "to": "n2",
            "label": "später",
            "kind": "flow",
        }
    )
    model = validate_representation_input(raw)
    board = render_miro_board(model, route_representation(model))
    relation_legend = next(
        item["content"]
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("id") == "route_map_relations"
    )

    assert "+1 weitere Beziehungen" in relation_legend
    assert representation._miro_coverage(model, board)["edge_ids"] == ["e0", "e1"]


def test_private_staging_validation_never_deletes_substituted_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    original_same = representation._same_path_identity
    state: dict[str, str] = {}

    def substitute_before_validation(left: os.stat_result, right: os.stat_result) -> bool:
        if not state:
            staging_name = next(
                name for name in os.listdir(parent_fd) if name.startswith(".package.tmp-")
            )
            moved_name = ".moved-created-staging"
            os.rename(
                staging_name,
                moved_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
            state.update(staging=staging_name, moved=moved_name)
            return False
        return original_same(left, right)

    monkeypatch.setattr(
        representation, "_same_path_identity", substitute_before_validation
    )
    try:
        with pytest.raises(RepresentationError, match="staging directory is unsafe"):
            representation._create_private_staging(parent_fd, "package")
        assert (parent / state["staging"]).is_dir()
        assert (parent / state["moved"]).is_dir()
    finally:
        os.close(parent_fd)


def test_bound_cleanup_never_removes_verified_directory_name(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    staging_fd: int | None = None
    owned_fds: dict[str, int] = {}
    try:
        staging_name, staging_fd, expected = representation._create_private_staging(
            parent_fd, "package"
        )
        representation._write_text(
            staging_fd, "overview.md", "compiler-owned", owned_fds=owned_fds
        )
        scrubbed, namespace_clean = representation._cleanup_bound_directory(
            parent_fd, staging_name, staging_fd, expected, owned_fds
        )
        assert scrubbed is True
        assert namespace_clean is True
        assert (parent / staging_name).is_dir()
        assert (parent / staging_name / "overview.md").stat().st_size == 0
    finally:
        for descriptor in owned_fds.values():
            os.close(descriptor)
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(parent_fd)


def test_package_final_readback_detects_parent_swap_after_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    old_parent = tmp_path / "old-parent"
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    parent_identity = parent.stat()
    original_fsync = representation.os.fsync
    swapped = False

    def fsync_then_swap(descriptor: int) -> None:
        nonlocal swapped
        original_fsync(descriptor)
        current = os.fstat(descriptor)
        if (
            not swapped
            and current.st_dev == parent_identity.st_dev
            and current.st_ino == parent_identity.st_ino
            and target.exists()
        ):
            parent.rename(old_parent)
            replacement.rename(parent)
            swapped = True

    monkeypatch.setattr(representation.os, "fsync", fsync_then_swap)
    with pytest.raises(RepresentationError, match="final publication readback failed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert swapped is True
    assert not (parent / "package").exists()
    old_target = old_parent / "package"
    assert old_target.is_dir()
    _assert_scrubbed_compiler_entries(old_target)


def test_package_rejects_target_name_too_long_for_private_staging(tmp_path: Path) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / ("a" * 240)

    with pytest.raises(RepresentationError, match="target name is too long"):
        compile_representation_package(input_path=input_path, output_dir=target)
    assert not target.exists()


def test_miro_relation_legend_never_clips_away_omission_notice() -> None:
    model = validate_representation_input(
        _minimal_representation(
            node_count=4, requested_formats=["miro_native"], long_labels=True
        )
    )
    board = render_miro_board(model, route_representation(model))
    legend = next(
        item["content"]
        for frame in board["frames"]
        for item in frame["objects"]
        if item.get("id") == "route_map_relations"
    )

    assert legend.endswith("+1 weitere Beziehungen")
    assert len(legend) <= 220
    assert validate_board_spec(board)["ok"] is True


def test_cleanup_preserves_same_named_foreign_replacement(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    staging_fd: int | None = None
    owned_fds: dict[str, int] = {}
    try:
        staging_name, staging_fd, expected = representation._create_private_staging(
            parent_fd, "package"
        )
        representation._write_text(
            staging_fd, "overview.md", "compiler-owned", owned_fds=owned_fds
        )
        os.rename(
            "overview.md",
            "owned-overview.md",
            src_dir_fd=staging_fd,
            dst_dir_fd=staging_fd,
        )
        foreign = parent / staging_name / "overview.md"
        foreign.write_text("foreign", encoding="utf-8")

        scrubbed, namespace_clean = representation._cleanup_bound_directory(
            parent_fd, staging_name, staging_fd, expected, owned_fds
        )

        assert scrubbed is True
        assert namespace_clean is False
        assert foreign.read_text(encoding="utf-8") == "foreign"
        assert (parent / staging_name / "owned-overview.md").stat().st_size == 0
    finally:
        for descriptor in owned_fds.values():
            os.close(descriptor)
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(parent_fd)


def test_cleanup_failure_never_masks_primary_compile_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")

    def fail_input(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic input failure")

    def fail_cleanup(*_args: object, **_kwargs: object) -> tuple[bool, bool]:
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(representation, "load_representation_input", fail_input)
    monkeypatch.setattr(representation, "_cleanup_bound_directory", fail_cleanup)
    with pytest.raises(RuntimeError, match="synthetic input failure"):
        compile_representation_package(
            input_path=input_path, output_dir=tmp_path / "package"
        )


def test_private_staging_accepts_indeterminate_name_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    monkeypatch.setattr(representation.os, "fpathconf", lambda *_args: -1)

    receipt = compile_representation_package(
        input_path=input_path, output_dir=tmp_path / "package"
    )

    assert receipt["ok"] is True


def test_final_readback_permission_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    replacement = tmp_path / "replacement"
    replacement.mkdir(mode=0o700)
    old_parent = tmp_path / "old-parent"
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    parent_identity = parent.stat()
    original_fsync = representation.os.fsync
    swapped = False

    def fsync_then_swap_to_unsearchable(descriptor: int) -> None:
        nonlocal swapped
        original_fsync(descriptor)
        current = os.fstat(descriptor)
        if (
            not swapped
            and current.st_dev == parent_identity.st_dev
            and current.st_ino == parent_identity.st_ino
            and target.exists()
        ):
            parent.rename(old_parent)
            replacement.rename(parent)
            parent.chmod(0o000)
            swapped = True

    monkeypatch.setattr(representation.os, "fsync", fsync_then_swap_to_unsearchable)
    try:
        with pytest.raises(RepresentationError, match="final publication readback failed"):
            compile_representation_package(input_path=input_path, output_dir=target)
    finally:
        if parent.exists():
            parent.chmod(0o700)

    assert swapped is True
    assert not (parent / "package").exists()
    old_target = old_parent / "package"
    assert old_target.is_dir()
    _assert_scrubbed_compiler_entries(old_target)


def test_package_rejects_direct_target_enametoolong_with_typed_error(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / ("x" * 256)

    with pytest.raises(RepresentationError, match="target name is too long"):
        compile_representation_package(input_path=input_path, output_dir=target)


def test_staging_close_failure_does_not_mask_validation_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    original_close = os.close
    close_fault_injected = False

    def fail_identity(_left: os.stat_result, _right: os.stat_result) -> bool:
        return False

    def close_then_fail_once(descriptor: int) -> None:
        nonlocal close_fault_injected
        if descriptor != parent_fd and not close_fault_injected:
            close_fault_injected = True
            original_close(descriptor)
            raise OSError(errno.EIO, "synthetic close failure")
        original_close(descriptor)

    monkeypatch.setattr(representation, "_same_path_identity", fail_identity)
    monkeypatch.setattr(representation.os, "close", close_then_fail_once)
    try:
        with pytest.raises(RepresentationError, match="staging directory is unsafe"):
            representation._create_private_staging(parent_fd, "package")
    finally:
        original_close(parent_fd)

    assert close_fault_injected is True


def test_immediate_published_target_readback_oserror_scrubs_owned_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original_stat = representation.os.stat
    target_bound_reads = 0

    def fail_third_target_bound_read(
        path: object, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal target_bound_reads
        if (
            path == target.name
            and kwargs.get("dir_fd") is not None
            and kwargs.get("follow_symlinks") is False
        ):
            target_bound_reads += 1
            if target_bound_reads == 3:
                raise PermissionError(errno.EACCES, "synthetic readback denial")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(representation.os, "stat", fail_third_target_bound_read)
    with pytest.raises(RepresentationError, match="identity could not be verified"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert target_bound_reads >= 3
    assert target.is_dir()
    _assert_scrubbed_compiler_entries(target)


def test_immediate_parent_readback_oserror_scrubs_owned_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    original_snapshot = representation._safe_parent_snapshot
    snapshot_calls = 0

    def fail_post_publish_snapshot(path: Path) -> os.stat_result:
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 3:
            raise PermissionError(errno.EACCES, "synthetic parent readback denial")
        return original_snapshot(path)

    monkeypatch.setattr(representation, "_safe_parent_snapshot", fail_post_publish_snapshot)
    with pytest.raises(RepresentationError, match="parent identity changed during publication"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert snapshot_calls == 3
    assert target.is_dir()
    _assert_scrubbed_compiler_entries(target)


def test_parent_durability_failure_scrubs_target_and_blocks_same_path_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    parent_identity = parent.stat()
    original_fsync = representation.os.fsync
    fault_injected = False

    def fail_published_parent_fsync(descriptor: int) -> None:
        nonlocal fault_injected
        current = os.fstat(descriptor)
        if (
            not fault_injected
            and target.exists()
            and current.st_dev == parent_identity.st_dev
            and current.st_ino == parent_identity.st_ino
        ):
            fault_injected = True
            raise OSError(errno.EIO, "synthetic parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(representation.os, "fsync", fail_published_parent_fsync)
    with pytest.raises(RepresentationError, match="durability sync failed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert fault_injected is True
    assert target.is_dir()
    _assert_scrubbed_compiler_entries(target)

    monkeypatch.setattr(representation.os, "fsync", original_fsync)
    with pytest.raises(RepresentationError, match="target must be absent"):
        compile_representation_package(input_path=input_path, output_dir=target)


def test_cleanup_scrubs_owned_bytes_after_directory_mode_change(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    staging_fd: int | None = None
    owned_fds: dict[str, int] = {}
    try:
        staging_name, staging_fd, expected = representation._create_private_staging(
            parent_fd, "package"
        )
        representation._write_text(
            staging_fd, "overview.md", "compiler-owned", owned_fds=owned_fds
        )
        os.fchmod(staging_fd, 0o500)

        scrubbed, namespace_clean = representation._cleanup_bound_directory(
            parent_fd, staging_name, staging_fd, expected, owned_fds
        )

        assert scrubbed is True
        assert namespace_clean is False
        assert (parent / staging_name / "overview.md").stat().st_size == 0
    finally:
        for descriptor in owned_fds.values():
            representation._close_fd_quietly(descriptor)
        if staging_fd is not None:
            representation._close_fd_quietly(staging_fd)
        representation._close_fd_quietly(parent_fd)


def test_cleanup_still_scrubs_owned_bytes_if_directory_fd_is_unreadable(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    parent_fd = os.open(parent, representation._directory_open_flags())
    staging_fd: int | None = None
    owned_fds: dict[str, int] = {}
    try:
        staging_name, staging_fd, expected = representation._create_private_staging(
            parent_fd, "package"
        )
        representation._write_text(
            staging_fd, "overview.md", "compiler-owned", owned_fds=owned_fds
        )
        representation._close_fd_quietly(staging_fd)

        scrubbed, namespace_clean = representation._cleanup_bound_directory(
            parent_fd, staging_name, staging_fd, expected, owned_fds
        )

        assert scrubbed is False
        assert namespace_clean is False
        assert (parent / staging_name / "overview.md").stat().st_size == 0
        staging_fd = None
    finally:
        for descriptor in owned_fds.values():
            representation._close_fd_quietly(descriptor)
        if staging_fd is not None:
            representation._close_fd_quietly(staging_fd)
        representation._close_fd_quietly(parent_fd)


def test_publish_rejects_foreign_same_basename_artifact_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    captured_owned = tmp_path / "captured-owned-input.json"
    original_publish = representation._rename_noreplace
    foreign_payload = b"foreign-input"

    def substitute_then_publish(
        parent_fd: int, source_name: str, target_name: str
    ) -> None:
        staging_fd = os.open(
            source_name, representation._directory_open_flags(), dir_fd=parent_fd
        )
        try:
            os.rename(
                "input.json",
                captured_owned.name,
                src_dir_fd=staging_fd,
                dst_dir_fd=parent_fd,
            )
            foreign_fd = os.open(
                "input.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=staging_fd,
            )
            try:
                os.write(foreign_fd, foreign_payload)
                os.fsync(foreign_fd)
            finally:
                os.close(foreign_fd)
        finally:
            os.close(staging_fd)
        original_publish(parent_fd, source_name, target_name)

    monkeypatch.setattr(representation, "_rename_noreplace", substitute_then_publish)
    with pytest.raises(RepresentationError, match="identity could not be verified"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert target.is_dir()
    assert (target / "input.json").read_bytes() == foreign_payload
    assert captured_owned.is_file()
    assert captured_owned.stat().st_size == 0


def test_publish_rejects_same_length_in_place_artifact_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original_publish = representation._rename_noreplace
    mutated_size = 0

    def mutate_then_publish(
        parent_fd: int, source_name: str, target_name: str
    ) -> None:
        nonlocal mutated_size
        staging_fd = os.open(
            source_name, representation._directory_open_flags(), dir_fd=parent_fd
        )
        try:
            artifact_fd = os.open(
                "input.json", os.O_WRONLY | os.O_CLOEXEC, dir_fd=staging_fd
            )
            try:
                mutated_size = os.fstat(artifact_fd).st_size
                replacement = b"X" * mutated_size
                assert os.pwrite(artifact_fd, replacement, 0) == mutated_size
                os.fsync(artifact_fd)
            finally:
                os.close(artifact_fd)
        finally:
            os.close(staging_fd)
        original_publish(parent_fd, source_name, target_name)

    monkeypatch.setattr(representation, "_rename_noreplace", mutate_then_publish)
    with pytest.raises(RepresentationError, match="identity could not be verified"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert mutated_size > 0
    assert target.is_dir()
    assert (target / "input.json").stat().st_size == 0


def test_final_readback_rejects_artifact_mutation_after_parent_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = parent / "package"
    parent_identity = parent.stat()
    original_fsync = representation.os.fsync
    mutated = False

    def fsync_then_mutate_published_artifact(descriptor: int) -> None:
        nonlocal mutated
        original_fsync(descriptor)
        current = os.fstat(descriptor)
        if (
            not mutated
            and target.exists()
            and current.st_dev == parent_identity.st_dev
            and current.st_ino == parent_identity.st_ino
        ):
            package_fd = os.open(target, representation._directory_open_flags())
            try:
                artifact_fd = os.open(
                    "input.json", os.O_WRONLY | os.O_CLOEXEC, dir_fd=package_fd
                )
                try:
                    size = os.fstat(artifact_fd).st_size
                    assert os.pwrite(artifact_fd, b"Y" * size, 0) == size
                    original_fsync(artifact_fd)
                finally:
                    os.close(artifact_fd)
            finally:
                os.close(package_fd)
            mutated = True

    monkeypatch.setattr(representation.os, "fsync", fsync_then_mutate_published_artifact)
    with pytest.raises(RepresentationError, match="final publication readback failed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert mutated is True
    assert target.is_dir()
    assert (target / "input.json").stat().st_size == 0


def test_package_verifies_bound_artifacts_at_all_three_publication_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    original_verify = representation._verify_bound_artifacts
    calls = 0

    def count_verify(
        directory_fd: int, owned_fds: representation._OwnedArtifactLedger
    ) -> bool:
        nonlocal calls
        calls += 1
        return original_verify(directory_fd, owned_fds)

    monkeypatch.setattr(representation, "_verify_bound_artifacts", count_verify)
    receipt = compile_representation_package(
        input_path=input_path, output_dir=tmp_path / "package"
    )

    assert receipt["ok"] is True
    assert calls == 3

def test_final_verifier_rejects_append_during_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original_verify = representation._verify_bound_artifacts
    original_digest = representation._digest_open_fd
    verify_call = 0
    appended = False

    def count_verify(
        directory_fd: int, owned_fds: representation._OwnedArtifactLedger
    ) -> bool:
        nonlocal verify_call
        verify_call += 1
        return original_verify(directory_fd, owned_fds)

    def append_then_digest(descriptor: int, expected_size: int) -> str | None:
        nonlocal appended
        if verify_call == 3 and not appended:
            assert os.pwrite(descriptor, b"!", expected_size) == 1
            os.fsync(descriptor)
            appended = True
        return original_digest(descriptor, expected_size)

    monkeypatch.setattr(representation, "_verify_bound_artifacts", count_verify)
    monkeypatch.setattr(representation, "_digest_open_fd", append_then_digest)

    with pytest.raises(RepresentationError, match="final publication readback failed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert appended is True
    assert target.is_dir()
    assert (target / "input.json").stat().st_size == 0


def test_final_verifier_rejects_entry_added_after_initial_name_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "source.json"
    input_path.write_text(json.dumps(_minimal_representation()), encoding="utf-8")
    target = tmp_path / "package"
    original_verify = representation._verify_bound_artifacts
    original_listdir = representation.os.listdir
    verify_call = 0
    gate_listdir_call = 0
    injected = False
    foreign_payload = b"foreign-entry"

    def count_verify(
        directory_fd: int, owned_fds: representation._OwnedArtifactLedger
    ) -> bool:
        nonlocal verify_call, gate_listdir_call
        verify_call += 1
        gate_listdir_call = 0
        return original_verify(directory_fd, owned_fds)

    def listdir_then_inject(directory_fd: int) -> list[str]:
        nonlocal gate_listdir_call, injected
        names = original_listdir(directory_fd)
        if verify_call == 3:
            gate_listdir_call += 1
            if gate_listdir_call == 1 and not injected:
                foreign_fd = os.open(
                    "foreign.txt",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory_fd,
                )
                try:
                    os.write(foreign_fd, foreign_payload)
                    os.fsync(foreign_fd)
                finally:
                    os.close(foreign_fd)
                injected = True
        return names

    monkeypatch.setattr(representation, "_verify_bound_artifacts", count_verify)
    monkeypatch.setattr(representation.os, "listdir", listdir_then_inject)

    with pytest.raises(RepresentationError, match="final publication readback failed"):
        compile_representation_package(input_path=input_path, output_dir=target)

    assert injected is True
    assert target.is_dir()
    assert (target / "foreign.txt").read_bytes() == foreign_payload
    assert (target / "input.json").stat().st_size == 0
