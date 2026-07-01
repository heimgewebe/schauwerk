"""Semantic visual grammar for richer Miro-oriented Schauwerk views."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class VisualPrimitive:
    """One available visual building block and when to use it."""

    name: str
    role: str
    use_for: tuple[str, ...]
    density: str
    supports_review: bool = False
    layout_dsl: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemplateSpec:
    """Reusable visual template contract."""

    name: str
    purpose: str
    regions: tuple[str, ...]
    primitives: tuple[str, ...]
    invariants: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MIRO_VISUAL_PRIMITIVES: tuple[VisualPrimitive, ...] = (
    VisualPrimitive(
        "frame",
        "region",
        ("chapter", "workspace", "projection boundary", "board section"),
        "macro",
    ),
    VisualPrimitive(
        "banner_shape",
        "orientation",
        ("leitfrage", "thesis", "warning", "status", "section emphasis"),
        "low",
    ),
    VisualPrimitive(
        "text",
        "label",
        ("heading", "legend", "caption", "quiet explanation"),
        "low",
    ),
    VisualPrimitive(
        "sticky",
        "short thought",
        ("question", "idea", "student note", "quick classification", "learning step"),
        "medium",
        supports_review=True,
    ),
    VisualPrimitive(
        "connector",
        "relation",
        ("cause", "sequence", "contrast", "evidence", "dependency"),
        "low",
    ),
    VisualPrimitive(
        "doc",
        "explanation",
        ("longer instruction", "source summary", "worked example", "speaker notes"),
        "high",
    ),
    VisualPrimitive(
        "table",
        "structured comparison",
        ("roles", "criteria", "vocabulary", "task status", "argument map"),
        "high",
    ),
    VisualPrimitive(
        "card",
        "action item",
        ("assignment", "todo", "review item", "handoff"),
        "medium",
        supports_review=True,
    ),
    VisualPrimitive(
        "code_widget",
        "technical evidence",
        ("command", "config", "source snippet", "repro step"),
        "high",
        layout_dsl=False,
    ),
    VisualPrimitive(
        "image",
        "visual anchor",
        ("photo", "diagram source", "map", "screenshot"),
        "medium",
        layout_dsl=False,
    ),
    VisualPrimitive(
        "comment",
        "review thread",
        ("feedback", "open question", "teacher note", "peer review"),
        "medium",
        supports_review=True,
        layout_dsl=False,
    ),
    VisualPrimitive(
        "diagram",
        "formal model",
        ("process", "flowchart", "system relation", "decision tree"),
        "medium",
        layout_dsl=False,
    ),
    VisualPrimitive(
        "prototype",
        "interactive surface",
        ("screen flow", "interactive explanation", "web mockup"),
        "high",
        layout_dsl=False,
    ),
)


def learning_template() -> TemplateSpec:
    """Return the default peer-learning visual template."""
    return TemplateSpec(
        name="learning-view-v1-rich",
        purpose="peer-facing explanation and projection board",
        regions=(
            "orientation",
            "concept table",
            "learning path",
            "explainer doc",
            "peer review",
            "safety footer",
        ),
        primitives=(
            "frame",
            "banner_shape",
            "text",
            "table",
            "doc",
            "sticky",
            "connector",
        ),
        invariants=(
            "leitfrage is visible at first glance",
            "longer explanation uses doc, not sticky notes",
            "structured comparisons use tables",
            "short learning actions may use sticky notes",
            "relations are explicit connectors",
            "privacy footer is always present",
        ),
    )


def zoomlandkarte_template() -> TemplateSpec:
    """Return the zoomable learning-map template inspired by large Miro cluster boards."""
    return TemplateSpec(
        name="learning-zoomlandkarte-v1",
        purpose="zoomable overview-to-detail map for larger learning material",
        regions=(
            "macro overview",
            "production lane",
            "priority clusters",
            "detail fields",
            "risk and gap zone",
            "source hygiene",
            "privacy footer",
        ),
        primitives=(
            "frame",
            "banner_shape",
            "text",
            "table",
            "doc",
            "sticky",
            "connector",
        ),
        invariants=(
            "zoom-out shows named clusters before details",
            "zoom-in reveals dense local content inside clusters",
            "production lane separates workflow from knowledge clusters",
            "risk and source hygiene are explicit regions",
            "details stay inside their cluster frame",
            "privacy footer is always present",
        ),
    )


def primitive_names(*, layout_only: bool = False) -> tuple[str, ...]:
    """List available primitive names for diagnostics and docs."""
    return tuple(
        primitive.name
        for primitive in MIRO_VISUAL_PRIMITIVES
        if not layout_only or primitive.layout_dsl
    )


def primitive_catalog(*, layout_only: bool = False) -> tuple[dict[str, Any], ...]:
    """Return the visual primitive catalog as JSON-compatible dictionaries."""
    return tuple(
        primitive.to_dict()
        for primitive in MIRO_VISUAL_PRIMITIVES
        if not layout_only or primitive.layout_dsl
    )


def primitive_by_name(name: str) -> VisualPrimitive:
    """Resolve one primitive by canonical name."""
    for primitive in MIRO_VISUAL_PRIMITIVES:
        if primitive.name == name:
            return primitive
    raise KeyError(f"unknown visual primitive: {name}")
