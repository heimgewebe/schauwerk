from __future__ import annotations

import pytest

from schauwerk.visual import miro_dsl as dsl
from schauwerk.visual.grammar import learning_template, primitive_by_name, primitive_names


def test_miro_visual_grammar_v1_catalog_is_complete() -> None:
    assert primitive_names() == (
        "frame",
        "banner_shape",
        "text",
        "sticky",
        "connector",
        "doc",
        "table",
        "card",
        "code_widget",
        "image",
        "comment",
        "diagram",
        "prototype",
    )


def test_learning_template_prefers_rich_layout_primitives() -> None:
    template = learning_template()

    assert template.name == "learning-view-v1-rich"
    assert "doc" in template.primitives
    assert "table" in template.primitives
    assert "sticky" in template.primitives
    assert "longer explanation uses doc, not sticky notes" in template.invariants


def test_primitive_lookup_fails_closed() -> None:
    assert primitive_by_name("table").density == "high"
    with pytest.raises(KeyError):
        primitive_by_name("unknown")


def test_miro_dsl_helpers_emit_deterministic_lines_and_blocks() -> None:
    text = dsl.line("heading", "TEXT", x=1, y=2, content='A "quote"')
    document = dsl.doc("guide", parent="root", x=10, y=20, markdown="# Guide")
    rendered_table = dsl.table(
        "rubric",
        parent="root",
        x=30,
        y=40,
        title="Rubric",
        columns=("A", "B"),
        rows=(("x|y", "z"),),
    )

    assert text == 'heading TEXT x=1 y=2 "A &quot;quote&quot;"'
    assert document == "guide DOC parent=root x=10 y=20 <<<\n# Guide\n>>>"
    assert 'rubric TABLE parent=root x=30 y=40 "Rubric"' in rendered_table
    assert "A:text | B:text\n---\nx/y | z" in rendered_table
    assert dsl.bullets(("one", "two")) == "- one\n- two"


def test_miro_dsl_table_preserves_explicit_column_types() -> None:
    rendered_table = dsl.table(
        "rubric",
        parent="root",
        x=30,
        y=40,
        title="Rubric",
        columns=("Status:select(Done#00FF00, Blocked#FF0000)", "Updated:latest_update"),
        rows=(("Done", "today"),),
    )

    assert "Status:select(Done#00FF00, Blocked#FF0000) | Updated:latest_update" in rendered_table


def test_visual_grammar_manifest_is_versioned_accessible_and_complete() -> None:
    from schauwerk.visual.grammar import (
        GRAMMAR_SCHEMA_VERSION,
        validate_visual_grammar,
        visual_grammar_manifest,
    )

    manifest = visual_grammar_manifest()
    receipt = validate_visual_grammar(manifest)

    assert manifest["schema_version"] == GRAMMAR_SCHEMA_VERSION
    assert receipt["valid"] is True
    assert receipt["minimum_contrast"] >= 4.5
    assert {item["family"] for item in manifest["templates"]}.issuperset(
        {"software", "education", "roadmap", "timeline", "presentation", "public-summary"}
    )
    assert all(item["symbol"] and item["text_alternative"] for item in manifest["semantic_tokens"])
    assert all(item["non_colour_cues"] == ["text", "symbol"] for item in manifest["state_markers"])


def test_visual_grammar_rejects_colour_only_or_low_contrast_state() -> None:
    import copy

    from schauwerk.visual.grammar import validate_visual_grammar, visual_grammar_manifest

    manifest = copy.deepcopy(visual_grammar_manifest())
    manifest["state_markers"][0]["foreground"] = "#FFFFFF"
    manifest["state_markers"][0]["background"] = "#FFFFFF"
    with pytest.raises(ValueError, match="contrast"):
        validate_visual_grammar(manifest)

    manifest = copy.deepcopy(visual_grammar_manifest())
    manifest["state_markers"][0]["non_colour_cues"] = ["colour"]
    with pytest.raises(ValueError, match="non-colour"):
        validate_visual_grammar(manifest)


def test_software_and_education_share_grammar_without_same_template() -> None:
    from schauwerk.visual.grammar import (
        GRAMMAR_SCHEMA_VERSION,
        education_template,
        software_template,
    )

    software = software_template()
    education = education_template()
    assert GRAMMAR_SCHEMA_VERSION == "schauwerk-visual-grammar.v1"
    assert software.name != education.name
    assert software.family != education.family
    assert software.regions != education.regions
    assert "source revision is visible" in software.invariants
    assert "privacy footer is always present" in education.invariants


def test_visual_grammar_write_is_atomic_and_rejects_symlink(tmp_path) -> None:
    import json

    from schauwerk.visual.grammar import GRAMMAR_SCHEMA_VERSION, write_visual_grammar

    output = tmp_path / "grammar.json"
    receipt = write_visual_grammar(output)
    assert receipt["valid"] is True
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == GRAMMAR_SCHEMA_VERSION
    from schauwerk.visual.grammar import validate_visual_grammar

    assert validate_visual_grammar(written)["valid"] is True

    target = tmp_path / "target.json"
    target.write_text("untouched", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="output path is unsafe"):
        write_visual_grammar(link)
    assert target.read_text(encoding="utf-8") == "untouched"


def test_visual_grammar_rejects_empty_manifest_and_uses_json_native_arrays() -> None:
    from schauwerk.visual.grammar import validate_visual_grammar, visual_grammar_manifest

    manifest = visual_grammar_manifest()
    assert isinstance(manifest["templates"][0]["regions"], list)
    assert isinstance(manifest["primitives"][0]["use_for"], list)
    with pytest.raises(ValueError, match="schema"):
        validate_visual_grammar({})


def test_visual_grammar_rejects_missing_state_and_invalid_severity_order() -> None:
    import copy

    from schauwerk.visual.grammar import validate_visual_grammar, visual_grammar_manifest

    manifest = copy.deepcopy(visual_grammar_manifest())
    manifest["state_markers"] = [
        marker for marker in manifest["state_markers"] if marker["name"] != "failed"
    ]
    with pytest.raises(ValueError, match="state marker catalog"):
        validate_visual_grammar(manifest)

    manifest = copy.deepcopy(visual_grammar_manifest())
    manifest["state_markers"][0]["severity_rank"] = 99
    with pytest.raises(ValueError, match="severity ranks"):
        validate_visual_grammar(manifest)
