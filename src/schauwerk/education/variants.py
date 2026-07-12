"""Audience-specific learning variants and deterministic offline packages."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..visual.grammar import GRAMMAR_SCHEMA_VERSION, html_theme_css, template_by_family
from .view import LearningStep, LearningView, parse_learning_view

INPUT_SCHEMA_VERSION = "education-variants-input.v1"
VARIANTS = ("teacher", "projection", "assignment", "student", "presentation")
_MAX_INPUT_BYTES = 2 * 1024 * 1024
_MAX_LIST_ITEMS = 12
_PERSONAL_KEYS = {
    "email",
    "email_address",
    "phone",
    "phone_number",
    "student_id",
    "student_name",
    "student_names",
    "learner_id",
    "learner_name",
    "learner_names",
    "grade",
    "grades",
    "mark",
    "marks",
    "personal_data",
    "date_of_birth",
    "birthdate",
    "address",
}
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ()/.-]{7,}\d)(?!\w)")
_ALLOWED_LEARNING_FIELDS = {
    "topic",
    "audience",
    "guiding_question",
    "goals",
    "key_terms",
    "materials",
    "steps",
    "phases",
    "collaboration",
    "check",
    "author_role",
    "privacy_note",
    "teacher_notes",
    "answer_key",
    "assignment",
}
_ALLOWED_STEP_FIELDS = {"title", "activity", "minutes", "duration_min", "output"}
_ALLOWED_ASSIGNMENT_FIELDS = {"instructions", "resources", "submission_boundary"}


@dataclass(frozen=True)
class AssignmentContract:
    instructions: tuple[str, ...]
    resources: tuple[str, ...]
    submission_boundary: str


@dataclass(frozen=True)
class EducationSource:
    view: LearningView
    teacher_notes: tuple[str, ...]
    answer_key: tuple[str, ...]
    assignment: AssignmentContract
    source_digest: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_text(value: Any, *, label: str, maximum: int = 1000) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    return normalized


def _text_list(value: Any, *, label: str, required: bool = False) -> tuple[str, ...]:
    if value is None:
        value = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list of strings")
    result = tuple(_safe_text(item, label=f"{label}[{index}]") for index, item in enumerate(value))
    if required and not result:
        raise ValueError(f"{label} must contain at least one entry")
    if len(result) > _MAX_LIST_ITEMS:
        raise ValueError(f"{label} exceeds {_MAX_LIST_ITEMS} entries")
    return result


def _walk_personal_data(
    value: Any,
    *,
    path: str = "root",
    depth: int = 0,
    active_container_ids: set[int] | None = None,
) -> None:
    if depth > 20:
        raise ValueError(f"education input nesting exceeds the limit at {path}")
    if active_container_ids is None:
        active_container_ids = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active_container_ids:
            raise ValueError(f"education input contains a cyclic mapping at {path}")
        active_container_ids.add(identity)
        try:
            for key, item in value.items():
                normalized_key = str(key).strip().lower().replace("-", "_")
                if normalized_key in _PERSONAL_KEYS:
                    raise ValueError(f"personal-data field is prohibited at {path}.{key}")
                _walk_personal_data(
                    item,
                    path=f"{path}.{key}",
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
        finally:
            active_container_ids.remove(identity)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        identity = id(value)
        if identity in active_container_ids:
            raise ValueError(f"education input contains a cyclic sequence at {path}")
        active_container_ids.add(identity)
        try:
            for index, item in enumerate(value):
                _walk_personal_data(
                    item,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
        finally:
            active_container_ids.remove(identity)
        return
    if isinstance(value, str):
        if _EMAIL_RE.search(value):
            raise ValueError(f"email address is prohibited at {path}")
        for candidate in _PHONE_CANDIDATE_RE.findall(value):
            digit_count = sum(character.isdigit() for character in candidate)
            if candidate.lstrip().startswith("+") or digit_count >= 9:
                raise ValueError(f"phone number is prohibited at {path}")


def _normalize_learning_view(view: LearningView) -> LearningView:
    return LearningView(
        topic=_safe_text(view.topic, label="learn.topic"),
        audience=_safe_text(view.audience, label="learn.audience"),
        guiding_question=_safe_text(view.guiding_question, label="learn.guiding_question"),
        goals=tuple(
            _safe_text(value, label=f"learn.goals[{index}]")
            for index, value in enumerate(view.goals)
        ),
        steps=tuple(
            LearningStep(
                title=_safe_text(step.title, label=f"learn.steps[{index}].title"),
                activity=_safe_text(step.activity, label=f"learn.steps[{index}].activity"),
                minutes=step.minutes,
                output=(
                    _safe_text(step.output, label=f"learn.steps[{index}].output")
                    if step.output is not None
                    else None
                ),
            )
            for index, step in enumerate(view.steps)
        ),
        key_terms=tuple(
            _safe_text(value, label=f"learn.key_terms[{index}]")
            for index, value in enumerate(view.key_terms)
        ),
        materials=tuple(
            _safe_text(value, label=f"learn.materials[{index}]")
            for index, value in enumerate(view.materials)
        ),
        collaboration=_safe_text(view.collaboration, label="learn.collaboration"),
        check=_safe_text(view.check, label="learn.check"),
        author_role=_safe_text(view.author_role, label="learn.author_role"),
        privacy_note=_safe_text(view.privacy_note, label="learn.privacy_note"),
    )


def _read_source(path: Path) -> Mapping[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("education input must be a regular non-symlink file")
        if path.stat().st_size > _MAX_INPUT_BYTES:
            raise ValueError("education input exceeds the 2 MiB limit")
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("education input is unreadable") from exc
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("education input is invalid") from exc
    if not isinstance(value, Mapping):
        raise ValueError("education input must contain an object")
    return value


def parse_education_source(value: Mapping[str, Any]) -> EducationSource:
    _walk_personal_data(value)
    if value.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError("unsupported education input schema")
    wrapper_keys = [key for key in ("learn", "lesson") if key in value]
    if len(wrapper_keys) != 1:
        raise ValueError("education input must use exactly one learning wrapper")
    wrapper_key = wrapper_keys[0]
    if set(value) != {"schema_version", wrapper_key}:
        raise ValueError("education input contains unknown outer fields")
    wrapped = value[wrapper_key]
    if not isinstance(wrapped, Mapping):
        raise ValueError("education input must contain a learning object")
    unknown_fields = set(wrapped) - _ALLOWED_LEARNING_FIELDS
    if unknown_fields:
        raise ValueError(
            "education input contains unknown learning fields: "
            + ", ".join(sorted(str(item) for item in unknown_fields))
        )
    if "steps" in wrapped and "phases" in wrapped:
        raise ValueError("education input must not declare both steps and phases")
    raw_steps = wrapped.get("steps", wrapped.get("phases", []))
    if isinstance(raw_steps, Sequence) and not isinstance(raw_steps, (str, bytes)):
        for index, raw_step in enumerate(raw_steps):
            if isinstance(raw_step, Mapping):
                unknown_step_fields = set(raw_step) - _ALLOWED_STEP_FIELDS
                if unknown_step_fields:
                    raise ValueError(
                        f"learn.steps[{index}] contains unknown fields: "
                        + ", ".join(sorted(str(item) for item in unknown_step_fields))
                    )
                if "minutes" in raw_step and "duration_min" in raw_step:
                    raise ValueError(
                        f"learn.steps[{index}] must not declare both minutes and duration_min"
                    )
    view = _normalize_learning_view(parse_learning_view(value))
    teacher_notes = _text_list(wrapped.get("teacher_notes"), label="learn.teacher_notes")
    answer_key = _text_list(wrapped.get("answer_key"), label="learn.answer_key")
    raw_assignment = wrapped.get("assignment")
    if not isinstance(raw_assignment, Mapping):
        raise ValueError("learn.assignment must be an object")
    unknown_assignment_fields = set(raw_assignment) - _ALLOWED_ASSIGNMENT_FIELDS
    if unknown_assignment_fields:
        raise ValueError(
            "learn.assignment contains unknown fields: "
            + ", ".join(sorted(str(item) for item in unknown_assignment_fields))
        )
    assignment = AssignmentContract(
        instructions=_text_list(
            raw_assignment.get("instructions"),
            label="learn.assignment.instructions",
            required=True,
        ),
        resources=_text_list(
            raw_assignment.get("resources"), label="learn.assignment.resources", required=True
        ),
        submission_boundary=_safe_text(
            raw_assignment.get("submission_boundary"),
            label="learn.assignment.submission_boundary",
        ),
    )
    normalized_payload = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "view": view.to_dict(),
        "teacher_notes": list(teacher_notes),
        "answer_key": list(answer_key),
        "assignment": {
            "instructions": list(assignment.instructions),
            "resources": list(assignment.resources),
            "submission_boundary": assignment.submission_boundary,
        },
    }
    return EducationSource(
        view=view,
        teacher_notes=teacher_notes,
        answer_key=answer_key,
        assignment=assignment,
        source_digest=_digest_bytes(_canonical_json(normalized_payload)),
    )


def load_education_source(path: Path) -> EducationSource:
    return parse_education_source(_read_source(path))


def _list_html(items: Sequence[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _steps_html(view: LearningView, *, concise: bool = False) -> str:
    entries: list[str] = []
    for index, step in enumerate(view.steps, start=1):
        duration = f" · {step.minutes} min" if step.minutes else ""
        output = (
            ""
            if concise or not step.output
            else f"<p><strong>Ergebnis:</strong> {html.escape(step.output)}</p>"
        )
        entries.append(
            "<li>"
            f"<h3>{index}. {html.escape(step.title)}{duration}</h3>"
            f"<p>{html.escape(step.activity)}</p>{output}"
            "</li>"
        )
    return '<ol class="steps">' + "".join(entries) + "</ol>"


def _section(identifier: str, title: str, body: str) -> str:
    return f'<section id="{identifier}"><h2>{html.escape(title)}</h2>{body}</section>'


def _document(*, title: str, source_digest: str, variant: str, body: str) -> str:
    template = template_by_family("education")
    style = html_theme_css(template.family)
    return (
        '<!doctype html>\n<html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{style}</style></head><body>"
        f'<header><h1>{html.escape(title)}</h1><p class="meta">Variante: {variant} · '
        f"Quelle: {source_digest[:16]} · Grammatik: {GRAMMAR_SCHEMA_VERSION} · "
        f"Template: {template.name}</p></header><main>{body}</main>"
        "<footer><p>Offline nutzbar · keine Netzwerk- oder Miro-Abhängigkeit · "
        "keine personenbezogenen Daten</p></footer></body></html>\n"
    )


def render_education_variant(source: EducationSource, variant: str) -> tuple[str, dict[str, Any]]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown education variant: {variant}")
    view = source.view
    common = [
        _section("question", "Leitfrage", f"<p>{html.escape(view.guiding_question)}</p>"),
        _section("goals", "Ziele", _list_html(view.goals)),
    ]
    privacy_section = _section(
        "privacy", "Datenschutzgrenze", f"<p>{html.escape(view.privacy_note)}</p>"
    )
    private_sections: list[str] = []
    if variant == "teacher":
        sections = [
            *common,
            _section("steps", "Lernweg", _steps_html(view)),
            _section("materials", "Material", _list_html(view.materials or ("Board", "Notizen"))),
            _section("collaboration", "Arbeitsform", f"<p>{html.escape(view.collaboration)}</p>"),
            _section("check", "Sicherung", f"<p>{html.escape(view.check)}</p>"),
            _section(
                "teacher-notes",
                "Lehrerhinweise",
                _list_html(source.teacher_notes or ("Keine zusätzlichen Hinweise.",)),
            ),
            _section(
                "answer-key",
                "Lösungshinweise",
                _list_html(source.answer_key or ("Keine Lösungshinweise hinterlegt.",)),
            ),
            privacy_section,
        ]
        included = [
            "question",
            "goals",
            "steps",
            "materials",
            "collaboration",
            "check",
            "teacher_notes",
            "answer_key",
            "privacy",
        ]
    elif variant == "projection":
        sections = [
            *common,
            _section("steps", "Ablauf", _steps_html(view, concise=True)),
            privacy_section,
        ]
        included = ["question", "goals", "steps", "privacy"]
        private_sections = ["teacher_notes", "answer_key", "submission_boundary"]
    elif variant == "assignment":
        assignment = source.assignment
        sections = [
            *common,
            _section("instructions", "Auftrag", _list_html(assignment.instructions)),
            _section("resources", "Ressourcen", _list_html(assignment.resources)),
            _section(
                "submission",
                "Abgabegrenze",
                f"<p>{html.escape(assignment.submission_boundary)}</p>",
            ),
            privacy_section,
        ]
        included = [
            "question",
            "goals",
            "instructions",
            "resources",
            "submission_boundary",
            "privacy",
        ]
        private_sections = ["teacher_notes", "answer_key"]
    elif variant == "student":
        sections = [
            *common,
            _section("steps", "Lernweg", _steps_html(view)),
            _section("materials", "Material", _list_html(view.materials or ("Board", "Notizen"))),
            _section("check", "Selbstcheck", f"<p>{html.escape(view.check)}</p>"),
            privacy_section,
        ]
        included = ["question", "goals", "steps", "materials", "check", "privacy"]
        private_sections = ["teacher_notes", "answer_key", "submission_boundary"]
    else:
        slide_sections = [
            (
                '<article class="slide"><h2>Leitfrage</h2>'
                f"<p>{html.escape(view.guiding_question)}</p></article>"
            ),
            f'<article class="slide"><h2>Ziele</h2>{_list_html(view.goals)}</article>',
        ]
        slide_sections.extend(
            (
                f'<article class="slide"><h2>{html.escape(step.title)}</h2>'
                f"<p>{html.escape(step.activity)}</p></article>"
            )
            for step in view.steps
        )
        slide_sections.append(
            f'<article class="slide"><h2>Sicherung</h2><p>{html.escape(view.check)}</p></article>'
        )
        slide_sections.append(
            '<article class="slide"><h2>Datenschutzgrenze</h2>'
            f"<p>{html.escape(view.privacy_note)}</p></article>"
        )
        sections = slide_sections
        included = ["question", "goals", "steps", "check", "privacy"]
        private_sections = ["teacher_notes", "answer_key", "submission_boundary"]

    title = f"{view.topic} — {variant}"
    document = _document(
        title=title,
        source_digest=source.source_digest,
        variant=variant,
        body="".join(sections),
    )
    if "http://" in document or "https://" in document:
        raise ValueError("education output unexpectedly contains a network dependency")
    receipt = {
        "schema_version": "education-variant-receipt.v1",
        "variant": variant,
        "source_digest": source.source_digest,
        "output_sha256": _digest_bytes(document.encode("utf-8")),
        "included_sections": included,
        "excluded_private_sections": private_sections,
        "network_dependencies": False,
        "miro_required": False,
        "personal_data_detected": False,
    }
    return document, receipt


def _safe_destination(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("education output path is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("education output path is unsafe")
    return destination


def _write_atomic(path: Path, content: str) -> None:
    destination = _safe_destination(path)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise ValueError("education output could not be written") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def write_education_variant(
    *, input_path: Path, variant: str, output: Path | None
) -> dict[str, Any]:
    source = load_education_source(input_path)
    document, receipt = render_education_variant(source, variant)
    if output is not None:
        _write_atomic(output, document)
        receipt["output"] = str(output)
    else:
        receipt["html"] = document
        receipt["output"] = None
    return receipt


def write_offline_package(*, input_path: Path, output_dir: Path, variant: str) -> dict[str, Any]:
    source = load_education_source(input_path)
    document, variant_receipt = render_education_variant(source, variant)
    destination = _safe_destination(output_dir)
    if destination.exists():
        raise ValueError("offline output directory already exists")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        filename = f"{variant}.html"
        (temporary / filename).write_text(document, encoding="utf-8")
        index = _document(
            title=f"{source.view.topic} — Offline-Paket",
            source_digest=source.source_digest,
            variant=f"offline-{variant}",
            body=(
                f'<nav><h2>Ansicht</h2><p><a href="{filename}">{html.escape(variant)}</a></p></nav>'
            ),
        )
        (temporary / "index.html").write_text(index, encoding="utf-8")
        files = {
            filename: variant_receipt["output_sha256"],
            "index.html": _digest_bytes(index.encode("utf-8")),
        }
        manifest = {
            "schema_version": "education-offline-package.v1",
            "topic": source.view.topic,
            "source_digest": source.source_digest,
            "entrypoint": "index.html",
            "variant": variant,
            "variant_file": filename,
            "included_sections": variant_receipt["included_sections"],
            "excluded_private_sections": variant_receipt["excluded_private_sections"],
            "files": dict(sorted(files.items())),
            "network_dependencies": False,
            "miro_required": False,
            "personal_data_detected": False,
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        (temporary / "manifest.json").write_text(manifest_text, encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "schema_version": "education-offline-receipt.v1",
        "source_digest": source.source_digest,
        "variant": variant,
        "output_dir": str(output_dir),
        "manifest_sha256": _digest_bytes(manifest_text.encode("utf-8")),
        "file_count": len(files) + 1,
        "network_dependencies": False,
        "miro_required": False,
        "personal_data_detected": False,
    }
