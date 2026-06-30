"""Deterministic learning-board views."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

_MAX_ITEMS = 8
_MAX_STEPS = 6


@dataclass(frozen=True)
class LearningStep:
    title: str
    activity: str
    minutes: int | None = None
    output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningView:
    topic: str
    audience: str
    guiding_question: str
    goals: tuple[str, ...]
    steps: tuple[LearningStep, ...]
    key_terms: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    collaboration: str = "Partnerarbeit: erklaeren, nachfragen, gemeinsam sichern."
    check: str = "Exit-Frage: Was ist der wichtigste Zusammenhang?"
    author_role: str = "learner"
    privacy_note: str = "Keine Namen, Noten oder personenbezogenen Daten auf dem Board."

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["steps"] = [step.to_dict() for step in self.steps]
        return value


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"learn.{key} must be a non-empty string")
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"learn.{key} must be a non-empty string")
    return value.strip()


def _text_list(data: Mapping[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    raw = data.get(key, [])
    if required and not raw:
        raise ValueError(f"learn.{key} must contain at least one entry")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError(f"learn.{key} must be a list of strings")
    values = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"learn.{key} entries must be non-empty strings")
        values.append(item.strip())
    if required and not values:
        raise ValueError(f"learn.{key} must contain at least one entry")
    return tuple(values[:_MAX_ITEMS])


def _step(data: Mapping[str, Any], index: int) -> LearningStep:
    title = _required_text(data, "title")
    activity = _required_text(data, "activity")
    minutes = data.get("minutes", data.get("duration_min"))
    if minutes is not None:
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
            raise ValueError(f"learn.steps[{index}].minutes must be a positive integer")
    output = data.get("output")
    if output is not None and (not isinstance(output, str) or not output.strip()):
        raise ValueError(f"learn.steps[{index}].output must be a non-empty string")
    return LearningStep(title=title, activity=activity, minutes=minutes, output=output)


def _steps(data: Mapping[str, Any]) -> tuple[LearningStep, ...]:
    raw = data.get("steps", data.get("phases"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        raise ValueError("learn.steps must contain at least one step")
    steps = []
    for index, item in enumerate(raw[:_MAX_STEPS]):
        if not isinstance(item, Mapping):
            raise ValueError(f"learn.steps[{index}] must be an object")
        steps.append(_step(item, index))
    return tuple(steps)


def parse_learning_view(data: Mapping[str, Any]) -> LearningView:
    source = data.get("learn", data.get("lesson", data))
    if not isinstance(source, Mapping):
        raise ValueError("learning input must be an object")
    return LearningView(
        topic=_required_text(source, "topic"),
        audience=_required_text(source, "audience"),
        guiding_question=_required_text(source, "guiding_question"),
        goals=_text_list(source, "goals", required=True),
        key_terms=_text_list(source, "key_terms"),
        materials=_text_list(source, "materials"),
        steps=_steps(source),
        collaboration=_optional_text(
            source, "collaboration", "Partnerarbeit: erklaeren, nachfragen, gemeinsam sichern."
        ),
        check=_optional_text(source, "check", "Exit-Frage: Was ist der wichtigste Zusammenhang?"),
        author_role=_optional_text(source, "author_role", "learner"),
        privacy_note=_optional_text(
            source, "privacy_note", "Keine Namen, Noten oder personenbezogenen Daten auf dem Board."
        ),
    )


def load_learning_view(path: Path) -> LearningView:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = yaml.safe_load(text)
    if not isinstance(raw, Mapping):
        raise ValueError("learning input must contain an object")
    return parse_learning_view(raw)


def _quote(value: str) -> str:
    escaped = value.strip().replace("\n", "<br>").replace(chr(34), "&quot;")
    return chr(34) + escaped + chr(34)


def _line(
    identifier: str, kind: str, *, parent: str | None = None, content: str, **attrs: object
) -> str:
    parts = [identifier, kind]
    if parent:
        parts.append(f"parent={parent}")
    for key, value in attrs.items():
        parts.append(f"{key}={value}")
    parts.append(_quote(content))
    return " ".join(parts)


def _bullets(items: Sequence[str]) -> str:
    return "<p>" + "</p><p>".join(f"• {item}" for item in items) + "</p>"


def render_learning_dsl(view: LearningView) -> str:
    goals = _bullets(view.goals)
    terms = _bullets(view.key_terms or ("Begriffe im Gespraech sammeln",))
    materials = _bullets(view.materials or ("Board", "Notizen", "Rueckfragen"))
    step_lines = []
    step_y = 150
    for index, step in enumerate(view.steps, start=1):
        minutes = f" ({step.minutes} min)" if step.minutes else ""
        output = f"<p><b>Ergebnis:</b> {step.output}</p>" if step.output else ""
        step_content = (
            f"<p><b>{index}. {step.title}{minutes}</b></p>"
            f"<p>{step.activity}</p>{output}"
        )
        step_lines.append(
            _line(
                f"step{index}",
                "STICKY",
                parent="flow",
                x=260,
                y=step_y,
                w=270,
                color="light_blue" if index % 2 else "light_green",
                content=step_content,
            )
        )
        step_y += 125
    lines = [
        _line("root", "FRAME", x=0, y=0, w=2000, h=1300, content="Schauwerk Learning View"),
        _line(
            "title",
            "TEXT",
            parent="root",
            x=1000,
            y=80,
            w=1700,
            font="open_sans",
            size=34,
            align="center",
            color="#1a1a1a",
            content=f"{view.topic} — fuer {view.audience}",
        ),
        _line(
            "question",
            "SHAPE",
            parent="root",
            x=1000,
            y=185,
            w=1500,
            h=95,
            type="round_rectangle",
            fill="#1a1a1a",
            color="#FFFFFF",
            font="open_sans",
            size=24,
            valign="middle",
            content=f"Leitfrage: {view.guiding_question}",
        ),
        _line(
            "overview",
            "FRAME",
            x=-700,
            y=120,
            w=520,
            h=760,
            fill="#F5F5F5",
            content="1 Orientierung",
        ),
        _line("flow", "FRAME", x=-120, y=120, w=520, h=760, fill="#F5F5F5", content="2 Lernweg"),
        _line("peer", "FRAME", x=460, y=120, w=520, h=760, fill="#F5F5F5", content="3 Gruppe"),
        _line(
            "goals",
            "TEXT",
            parent="overview",
            x=260,
            y=165,
            w=420,
            font="open_sans",
            size=20,
            align="left",
            color="#333333",
            content=f"<p><b>Ziele</b></p>{goals}",
        ),
        _line(
            "terms",
            "TEXT",
            parent="overview",
            x=260,
            y=425,
            w=420,
            font="open_sans",
            size=18,
            align="left",
            color="#333333",
            content=f"<p><b>Begriffe</b></p>{terms}",
        ),
        _line(
            "materials",
            "TEXT",
            parent="overview",
            x=260,
            y=625,
            w=420,
            font="open_sans",
            size=18,
            align="left",
            color="#333333",
            content=f"<p><b>Material</b></p>{materials}",
        ),
        *step_lines,
        _line(
            "role",
            "STICKY",
            parent="peer",
            x=260,
            y=175,
            w=270,
            color="yellow",
            content=(
                f"<p><b>Rolle</b></p><p>{view.author_role}: "
                "Thema so erklaeren, dass andere mitdenken koennen.</p>"
            ),
        ),
        _line(
            "collaboration",
            "STICKY",
            parent="peer",
            x=260,
            y=365,
            w=270,
            color="light_yellow",
            content=f"<p><b>Arbeitsform</b></p><p>{view.collaboration}</p>",
        ),
        _line(
            "check",
            "STICKY",
            parent="peer",
            x=260,
            y=555,
            w=270,
            color="light_green",
            content=f"<p><b>Sicherung</b></p><p>{view.check}</p>",
        ),
        _line(
            "privacy",
            "SHAPE",
            parent="root",
            x=1000,
            y=1130,
            w=1500,
            h=80,
            type="round_rectangle",
            fill="#FFFFFF",
            border_color="#1a1a1a",
            color="#1a1a1a",
            font="open_sans",
            size=18,
            valign="middle",
            content=view.privacy_note,
        ),
        _line(
            "e1",
            "CONNECTOR",
            **{"from": "question", "to": "goals"},
            shape="elbowed",
            end_cap="arrow",
            content="verstehen",
        ),
        _line(
            "e2",
            "CONNECTOR",
            **{"from": "goals", "to": "step1"},
            shape="elbowed",
            end_cap="arrow",
            content="lernen",
        ),
        _line(
            "e3",
            "CONNECTOR",
            **{"from": f"step{len(view.steps)}", "to": "check"},
            shape="elbowed",
            end_cap="arrow",
            content="sichern",
        ),
    ]
    return "\n".join(lines) + "\n"


def learning_render_receipt(
    view: LearningView, dsl: str, *, output_path: Path | None
) -> dict[str, Any]:
    return {
        "topic": view.topic,
        "audience": view.audience,
        "step_count": len(view.steps),
        "dsl_line_count": len([line for line in dsl.splitlines() if line.strip()]),
        "output_path": str(output_path) if output_path else None,
        "privacy_note_present": bool(view.privacy_note),
    }
