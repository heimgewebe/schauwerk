from __future__ import annotations

import json
from pathlib import Path

import pytest

from schauwerk.education.variants import (
    VARIANTS,
    load_education_source,
    parse_education_source,
    render_education_variant,
    write_education_variant,
    write_offline_package,
)


def sample() -> dict:
    return {
        "schema_version": "education-variants-input.v1",
        "learn": {
            "topic": "Photosynthese",
            "audience": "Lerngruppe",
            "guiding_question": "Wie wird aus Licht Energie?",
            "goals": ["Stoffe benennen", "Ablauf erklären"],
            "key_terms": ["Chlorophyll", "Glucose"],
            "materials": ["Pflanzenblatt", "Notizkarte"],
            "steps": [
                {
                    "title": "Vorwissen",
                    "activity": "Begriffe sammeln",
                    "minutes": 5,
                },
                {
                    "title": "Modellieren",
                    "activity": "Den Stoffkreislauf skizzieren",
                    "output": "Ein beschriftetes Modell",
                },
            ],
            "collaboration": "Zu zweit erklären und gegenseitig prüfen.",
            "check": "Erkläre den Zusammenhang in drei Sätzen.",
            "teacher_notes": ["Fehlvorstellung Atmung zuerst klären."],
            "answer_key": ["Lichtenergie wird in chemische Energie überführt."],
            "assignment": {
                "instructions": ["Erstelle ein Modell.", "Begründe jeden Pfeil."],
                "resources": ["Materialblatt", "Begriffsliste"],
                "submission_boundary": (
                    "Abgabe ist ausschließlich das Modell ohne Namen oder Noten."
                ),
            },
        }
    }


def write_input(tmp_path: Path, value: dict | None = None) -> Path:
    path = tmp_path / "lesson.json"
    path.write_text(json.dumps(value or sample(), ensure_ascii=False), encoding="utf-8")
    return path


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_variants_share_source_but_enforce_visibility() -> None:
    source = parse_education_source(sample())
    rendered = {variant: render_education_variant(source, variant) for variant in VARIANTS}

    digests = {receipt["source_digest"] for _, receipt in rendered.values()}
    assert digests == {source.source_digest}
    for document, receipt in rendered.values():
        assert source.view.privacy_note in document
        assert "privacy" in receipt["included_sections"]
    teacher = rendered["teacher"][0]
    assert "Fehlvorstellung Atmung" in teacher
    assert "chemische Energie" in teacher
    for variant in ("projection", "assignment", "student", "presentation"):
        document, receipt = rendered[variant]
        assert "Fehlvorstellung Atmung" not in document
        assert "chemische Energie" not in document
        assert "teacher_notes" in receipt["excluded_private_sections"]
        assert "answer_key" in receipt["excluded_private_sections"]


def test_assignment_has_explicit_contract() -> None:
    source = parse_education_source(sample())
    document, receipt = render_education_variant(source, "assignment")
    assert "Erstelle ein Modell" in document
    assert "Materialblatt" in document
    assert "Abgabegrenze" in document
    assert "ohne Namen oder Noten" in document
    assert {"instructions", "resources", "submission_boundary"}.issubset(
        receipt["included_sections"]
    )


def test_assignment_contract_is_required() -> None:
    value = sample()
    del value["learn"]["assignment"]["submission_boundary"]
    with pytest.raises(ValueError, match="submission_boundary"):
        parse_education_source(value)


def test_offline_package_is_deterministic_and_network_free(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    receipt_a = write_offline_package(
        input_path=source, output_dir=first, variant="student"
    )
    receipt_b = write_offline_package(
        input_path=source, output_dir=second, variant="student"
    )

    assert tree_bytes(first) == tree_bytes(second)
    assert receipt_a["manifest_sha256"] == receipt_b["manifest_sha256"]
    assert receipt_a["file_count"] == 3
    assert receipt_a["variant"] == "student"
    assert receipt_a["network_dependencies"] is False
    assert receipt_a["miro_required"] is False
    assert (first / "index.html").is_file()
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["variant"] == "student"
    assert manifest["variant_file"] == "student.html"
    assert not (first / "teacher.html").exists()
    assert "teacher_notes" in manifest["excluded_private_sections"]
    for path in first.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "<script" not in text


def test_personal_data_fields_and_values_are_rejected() -> None:
    for key, value, expected in (
        ("student_name", "Erika Beispiel", "personal-data field"),
        ("comment", "Kontakt: lernende@example.org", "email address"),
        ("comment", "+49 170 12345678", "phone number"),
    ):
        data = sample()
        data["learn"][key] = value
        with pytest.raises(ValueError, match=expected):
            parse_education_source(data)


def test_html_escaping_blocks_markup_injection() -> None:
    data = sample()
    data["learn"]["topic"] = "Licht <script>alert(1)</script>"
    source = parse_education_source(data)
    document, _ = render_education_variant(source, "student")
    assert "<script>" not in document
    assert "&lt;script&gt;" in document


def test_symlink_input_and_output_are_rejected(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    source_link = tmp_path / "source-link.json"
    source_link.symlink_to(source)
    with pytest.raises(ValueError, match="non-symlink"):
        load_education_source(source_link)

    target = tmp_path / "target.html"
    target.write_text("untouched", encoding="utf-8")
    output_link = tmp_path / "output.html"
    output_link.symlink_to(target)
    with pytest.raises(ValueError, match="output path is unsafe"):
        write_education_variant(input_path=source, variant="student", output=output_link)
    assert target.read_text(encoding="utf-8") == "untouched"


def test_offline_package_refuses_existing_directory(tmp_path: Path) -> None:
    source = write_input(tmp_path)
    destination = tmp_path / "offline"
    destination.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        write_offline_package(
            input_path=source, output_dir=destination, variant="student"
        )


def test_source_digest_is_based_on_normalized_contract() -> None:
    first = sample()
    second = sample()
    second["learn"]["topic"] = "  Photosynthese  "
    second["learn"]["goals"][0] = "  Stoffe   benennen "
    first_digest = parse_education_source(first).source_digest
    second_digest = parse_education_source(second).source_digest
    assert first_digest == second_digest


def test_unknown_fields_are_rejected() -> None:
    data = sample()
    data["learn"]["hidden_export"] = "must not be silently ignored"
    with pytest.raises(ValueError, match="unknown learning fields"):
        parse_education_source(data)


def test_calendar_date_is_not_misclassified_as_phone_number() -> None:
    data = sample()
    data["learn"]["teacher_notes"].append("Besprechung am 2026-07-10 vorbereiten.")
    source = parse_education_source(data)
    assert "2026-07-10" in source.teacher_notes[-1]


def test_unknown_schema_version_is_rejected() -> None:
    data = sample()
    data["schema_version"] = "education-variants-input.v2"
    with pytest.raises(ValueError, match="unsupported education input schema"):
        parse_education_source(data)


def test_cyclic_input_is_rejected() -> None:
    data = sample()
    cycle: list[object] = []
    cycle.append(cycle)
    data["learn"]["teacher_notes"] = cycle
    with pytest.raises(ValueError, match="cyclic sequence"):
        parse_education_source(data)


def test_excessive_input_nesting_is_rejected() -> None:
    data = sample()
    nested: object = "value"
    for _ in range(25):
        nested = [nested]
    data["learn"]["teacher_notes"] = nested
    with pytest.raises(ValueError, match="nesting exceeds"):
        parse_education_source(data)


def test_education_variants_use_shared_visual_grammar() -> None:
    source = parse_education_source(sample())
    document, receipt = render_education_variant(source, "student")
    assert receipt["schema_version"] == "education-variant-receipt.v1"
    assert "grammar_version" not in receipt
    assert "template" not in receipt
    assert "schauwerk-visual-grammar.v1" in document
    assert "Template: learning-view-v1-rich" in document
    assert "--sw-accent:#173B2D" in document
