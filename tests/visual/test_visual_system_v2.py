from __future__ import annotations

import copy
from pathlib import Path

import pytest

from schauwerk.visual.system_v2 import (
    BOARD_SCHEMA,
    QUALITY_SCHEMA,
    SYSTEM_SCHEMA,
    audit_board_spec,
    reference_board_spec,
    render_board_dsl,
    validate_board_spec,
    visual_system_manifest,
)


def test_manifest_is_versioned_and_semantic() -> None:
    manifest = visual_system_manifest()
    assert manifest["schema_version"] == SYSTEM_SCHEMA
    assert set(manifest["object_kinds"]) == {"connector", "doc", "shape", "sticky", "table", "text"}
    assert manifest["role_contract"]["open_input"]["kinds"] == ["sticky"]
    assert len(manifest["manifest_digest"]) == 64


def test_reference_board_passes_meaningful_gate() -> None:
    spec = reference_board_spec()
    quality = validate_board_spec(spec)
    assert spec["schema_version"] == BOARD_SCHEMA
    assert quality["schema_version"] == QUALITY_SCHEMA
    assert quality["ok"] is True
    assert quality["score"] >= 90
    assert quality["blockers"] == []
    assert quality["frame_count"] == 7
    assert quality["sticky_count"] == 0


def test_reference_renderer_uses_rich_objects_and_finite_frames() -> None:
    rendered = render_board_dsl(reference_board_spec())
    assert rendered.count(" FRAME ") == 7
    assert " TABLE" in rendered
    assert " DOC" in rendered
    assert " CONNECTOR" in rendered
    assert " STICKY" not in rendered
    assert "Klarheit vor Dekoration" in rendered


def test_rich_object_counts_do_not_hide_bad_narrative() -> None:
    spec = reference_board_spec()
    spec["reading_path"] = list(reversed(spec["reading_path"]))
    quality = audit_board_spec(spec)
    assert quality["ok"] is False
    assert any(item["code"] == "reading_path" for item in quality["blockers"])
    with pytest.raises(ValueError, match="reading_path"):
        validate_board_spec(spec)


def test_sticky_misuse_is_a_blocker_even_on_structured_board() -> None:
    spec = reference_board_spec()
    item = spec["frames"][2]["objects"][2]
    item["kind"] = "sticky"
    quality = audit_board_spec(spec)
    assert any(item["code"] == "object_misuse" for item in quality["blockers"])


def test_excessive_coverage_and_connector_clutter_fail_closed() -> None:
    spec = reference_board_spec()
    frame = spec["frames"][0]
    frame["objects"].append(
        {
            "id": "cover_extra",
            "kind": "shape",
            "role": "entity",
            "x": 60,
            "y": 60,
            "w": 1000,
            "h": 500,
            "content": "overload",
            "font_level": "body",
            "color_role": "structure",
            "shape": "round_rectangle",
        }
    )
    quality = audit_board_spec(spec)
    assert any(item["code"] == "white_space" for item in quality["blockers"])


def test_digest_and_system_binding_are_checked() -> None:
    spec = reference_board_spec()
    changed = copy.deepcopy(spec)
    changed["title"] = "changed"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_board_spec(changed)
    changed = reference_board_spec()
    changed["visual_system_digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest mismatch|different visual system"):
        validate_board_spec(changed)


def test_unsupported_provider_shape_fails_before_live_effect() -> None:
    spec = reference_board_spec()
    spec["frames"][4]["objects"][3]["shape"] = "diamond"
    quality = audit_board_spec(spec)
    assert any(item["code"] == "unsupported_shape" for item in quality["blockers"])


def test_declared_overlap_fails_even_when_object_count_is_small() -> None:
    spec = reference_board_spec()
    spec["frames"][1]["objects"][3]["x"] = 240
    quality = audit_board_spec(spec)
    assert quality["ok"] is False
    assert any(item["code"] == "object_overlap" for item in quality["blockers"])


def test_rich_objects_declare_provider_auto_sizing() -> None:
    spec = reference_board_spec()
    rich = [
        item
        for frame in spec["frames"]
        for item in frame["objects"]
        if item["kind"] in {"table", "doc"}
    ]
    assert len(rich) == 4
    assert {item["provider_geometry"] for item in rich} == {"auto_sized"}
    quality = validate_board_spec(spec)
    assert quality["provider_auto_sized_count"] == 4
    assert (
        quality["geometry_contract"]["table_doc"] == "provider_auto_sized_type_and_anchor_verified"
    )


def test_native_composition_declares_entry_path_and_semantic_grammar() -> None:
    spec = reference_board_spec()
    quality = validate_board_spec(spec)
    assert spec["composition_profile"] == "miro-native-composition.v1"
    assert spec["entry_frame"] == spec["reading_path"][0]
    assert spec["presentation_path"] == spec["reading_path"]
    assert len(quality["shape_types"]) >= 2
    assert len(quality["relation_types"]) >= 2


def test_flat_shape_wall_is_rejected() -> None:
    spec = reference_board_spec()
    for frame in spec["frames"]:
        for item in frame["objects"]:
            if item["kind"] == "shape":
                item["shape"] = "round_rectangle"
    quality = audit_board_spec(spec)
    assert any(item["code"] == "shape_grammar" for item in quality["blockers"])


def test_connector_rich_board_requires_semantic_relation_variety() -> None:
    spec = reference_board_spec()
    for frame in spec["frames"]:
        for item in frame["objects"]:
            if item["kind"] == "connector":
                item["relation_type"] = "flow"
    quality = audit_board_spec(spec)
    assert any(item["code"] == "relation_grammar" for item in quality["blockers"])


def test_renderer_encodes_relation_semantics_before_labels() -> None:
    rendered = render_board_dsl(reference_board_spec())
    assert "stroke_style=dotted" in rendered
    assert "stroke_style=dashed" in rendered
    assert "shape=curved" in rendered or "shape=straight" in rendered


def test_visual_outputs_reject_parent_symlink(tmp_path: Path) -> None:
    from schauwerk.visual.system_v2 import write_json

    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="must not contain symlinks"):
        write_json(linked / "receipt.json", {"ok": True})
