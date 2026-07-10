"""Versioned renderer-independent visual grammar for Schauwerk views."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GRAMMAR_SCHEMA_VERSION = "schauwerk-visual-grammar.v1"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


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
class SemanticToken:
    """Renderer-independent semantic styling token."""

    name: str
    role: str
    label: str
    shape: str
    symbol: str
    foreground: str
    background: str
    border: str
    text_alternative: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["contrast_ratio"] = round(contrast_ratio(self.foreground, self.background), 2)
        return value


@dataclass(frozen=True)
class StateMarker:
    """A state that remains legible without colour."""

    name: str
    label: str
    symbol: str
    foreground: str
    background: str
    border: str
    severity_rank: int
    non_colour_cues: tuple[str, ...] = ("text", "symbol")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["non_colour_cues"] = list(self.non_colour_cues)
        value["contrast_ratio"] = round(contrast_ratio(self.foreground, self.background), 2)
        return value


@dataclass(frozen=True)
class TemplateSpec:
    """Reusable visual template contract."""

    name: str
    purpose: str
    regions: tuple[str, ...]
    primitives: tuple[str, ...]
    invariants: tuple[str, ...]
    family: str = "general"
    audience: str = "mixed"
    reading_order: tuple[str, ...] = ()
    supports_offline: bool = True

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


SEMANTIC_TOKENS: tuple[SemanticToken, ...] = (
    SemanticToken(
        "orientation",
        "entry point",
        "Orientierung",
        "round_rectangle",
        "◆",
        "#FFFFFF",
        "#16324F",
        "#16324F",
        "Orientierung und Einstieg",
    ),
    SemanticToken(
        "evidence",
        "source-backed fact",
        "Beleg",
        "rectangle",
        "▣",
        "#14213D",
        "#EDF4FF",
        "#315D8A",
        "Belegte Aussage mit Quelle",
    ),
    SemanticToken(
        "decision",
        "decision or trade-off",
        "Entscheidung",
        "diamond",
        "◇",
        "#301934",
        "#F8ECFF",
        "#6B3B73",
        "Entscheidung oder Abwägung",
    ),
    SemanticToken(
        "action",
        "next action",
        "Aktion",
        "round_rectangle",
        "→",
        "#1F2933",
        "#FFF4CC",
        "#8A6512",
        "Auszuführende oder zu prüfende Aktion",
    ),
    SemanticToken(
        "risk",
        "risk or failure",
        "Risiko",
        "hexagon",
        "!",
        "#4A1010",
        "#FFE8E8",
        "#9A3030",
        "Risiko, Fehler oder Blockade",
    ),
    SemanticToken(
        "source",
        "provenance",
        "Quelle",
        "document",
        "↗",
        "#173B2D",
        "#EAF8F0",
        "#2F6B50",
        "Quelle, Revision und Beobachtungszeit",
    ),
    SemanticToken(
        "uncertainty",
        "uncertain claim",
        "Unsicherheit",
        "cloud",
        "?",
        "#3C2F12",
        "#FFF8DD",
        "#80671F",
        "Unsichere oder noch zu prüfende Aussage",
    ),
)


STATE_MARKERS: tuple[StateMarker, ...] = (
    StateMarker("healthy", "gesund", "✓", "#113D24", "#E8F7EC", "#2B6B3F", 0),
    StateMarker("partial", "teilweise", "◐", "#3C2F12", "#FFF8DD", "#80671F", 1),
    StateMarker("stale", "veraltet", "⧖", "#4A2B10", "#FFF0DF", "#985B22", 2),
    StateMarker("failed", "fehlgeschlagen", "✕", "#4A1010", "#FFE8E8", "#9A3030", 3),
    StateMarker("unavailable", "nicht verfügbar", "!", "#4A1010", "#FFE8E8", "#9A3030", 4),
    StateMarker("unknown", "unbekannt", "?", "#252B31", "#EEF1F4", "#58636E", 5),
)


PROVENANCE_CONTRACT: dict[str, Any] = {
    "required_fields": ("source_id", "revision", "observed_at", "freshness", "uncertainty"),
    "freshness_values": ("fresh", "stale", "unknown", "unavailable"),
    "uncertainty_values": ("observed", "derived", "estimated", "unknown"),
    "rules": (
        "source authority remains external to the rendered view",
        "missing observation time cannot be presented as fresh",
        "stale and unavailable states remain visible",
        "estimated or derived claims are labelled and never promoted to source facts",
    ),
}


def _template(
    *,
    name: str,
    family: str,
    purpose: str,
    regions: tuple[str, ...],
    primitives: tuple[str, ...],
    invariants: tuple[str, ...],
    audience: str,
) -> TemplateSpec:
    return TemplateSpec(
        name=name,
        family=family,
        purpose=purpose,
        regions=regions,
        primitives=primitives,
        invariants=invariants,
        audience=audience,
        reading_order=regions,
    )


def software_template() -> TemplateSpec:
    return _template(
        name="software-overview-v1",
        family="software",
        purpose="architecture, decisions, delivery, tests and risks",
        regions=("orientation", "architecture", "direction", "delivery", "risks", "sources"),
        primitives=("frame", "banner_shape", "text", "table", "doc", "connector"),
        invariants=(
            "source revision is visible",
            "decisions remain separate from current work",
            "test and risk states have text and symbol cues",
            "provider mutation is never implied",
        ),
        audience="technical operators",
    )


def education_template() -> TemplateSpec:
    return _template(
        name="learning-view-v1-rich",
        family="education",
        purpose="peer-facing explanation and projection board",
        regions=(
            "orientation",
            "concept table",
            "learning path",
            "explainer doc",
            "peer review",
            "safety footer",
        ),
        primitives=("frame", "banner_shape", "text", "table", "doc", "sticky", "connector"),
        invariants=(
            "leitfrage is visible at first glance",
            "longer explanation uses doc, not sticky notes",
            "structured comparisons use tables",
            "short learning actions may use sticky notes",
            "relations are explicit connectors",
            "privacy footer is always present",
        ),
        audience="teachers and learners",
    )


def roadmap_template() -> TemplateSpec:
    return _template(
        name="roadmap-v1",
        family="roadmap",
        purpose="sequenced outcomes, gates and dependencies",
        regions=("outcome", "now", "next", "later", "dependencies", "risks"),
        primitives=("frame", "banner_shape", "text", "card", "connector", "table"),
        invariants=(
            "outcomes precede activities",
            "dependencies use explicit connectors",
            "blocked work has a non-colour marker",
            "time horizons do not claim calendar precision without sources",
        ),
        audience="planning and delivery",
    )


def timeline_template() -> TemplateSpec:
    return _template(
        name="timeline-v1",
        family="timeline",
        purpose="dated events with source and uncertainty",
        regions=("legend", "time axis", "events", "gaps", "sources"),
        primitives=("frame", "banner_shape", "text", "card", "connector"),
        invariants=(
            "every date has a source or uncertainty label",
            "gaps remain visible",
            "sequence does not imply causality",
            "reading order is chronological",
        ),
        audience="mixed",
    )


def presentation_template() -> TemplateSpec:
    return _template(
        name="presentation-v1",
        family="presentation",
        purpose="ordered slides with separate speaker support",
        regions=("title", "question", "content", "evidence", "decision", "close"),
        primitives=("frame", "banner_shape", "text", "image", "diagram", "doc"),
        invariants=(
            "one main claim per slide",
            "speaker notes are not projected",
            "reading order is explicit",
            "offline output has no remote dependencies",
        ),
        audience="live audience",
    )


def public_summary_template() -> TemplateSpec:
    return _template(
        name="public-summary-v1",
        family="public-summary",
        purpose="sanitized immutable public explanation",
        regions=("title", "summary", "evidence", "limitations", "version"),
        primitives=("frame", "banner_shape", "text", "doc", "table"),
        invariants=(
            "only declared public fields are rendered",
            "limitations and version remain visible",
            "unknown visibility fails closed",
            "published output is read-only",
        ),
        audience="public",
    )


def zoomlandkarte_template() -> TemplateSpec:
    return _template(
        name="learning-zoomlandkarte-v1",
        family="education-map",
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
        primitives=("frame", "banner_shape", "text", "table", "doc", "sticky", "connector"),
        invariants=(
            "zoom-out shows named clusters before details",
            "zoom-in reveals dense local content inside clusters",
            "production lane separates workflow from knowledge clusters",
            "risk and source hygiene are explicit regions",
            "details stay inside their cluster frame",
            "privacy footer is always present",
        ),
        audience="teachers and learners",
    )


def learning_template() -> TemplateSpec:
    """Backward-compatible name for the education template."""
    return education_template()


def template_catalog() -> tuple[TemplateSpec, ...]:
    return (
        software_template(),
        education_template(),
        roadmap_template(),
        timeline_template(),
        presentation_template(),
        public_summary_template(),
        zoomlandkarte_template(),
    )


def template_by_family(family: str) -> TemplateSpec:
    for template in template_catalog():
        if template.family == family:
            return template
    raise KeyError(f"unknown visual template family: {family}")


def primitive_names(*, layout_only: bool = False) -> tuple[str, ...]:
    return tuple(
        primitive.name
        for primitive in MIRO_VISUAL_PRIMITIVES
        if not layout_only or primitive.layout_dsl
    )


def primitive_catalog(*, layout_only: bool = False) -> tuple[dict[str, Any], ...]:
    return tuple(
        primitive.to_dict()
        for primitive in MIRO_VISUAL_PRIMITIVES
        if not layout_only or primitive.layout_dsl
    )


def primitive_by_name(name: str) -> VisualPrimitive:
    for primitive in MIRO_VISUAL_PRIMITIVES:
        if primitive.name == name:
            return primitive
    raise KeyError(f"unknown visual primitive: {name}")


def token_by_name(name: str) -> SemanticToken:
    for token in SEMANTIC_TOKENS:
        if token.name == name:
            return token
    raise KeyError(f"unknown semantic token: {name}")


def state_marker(name: str) -> StateMarker:
    for marker in STATE_MARKERS:
        if marker.name == name:
            return marker
    raise KeyError(f"unknown visual state: {name}")


def state_label(name: str, *, detail: str | None = None) -> str:
    marker = state_marker(name)
    suffix = f" — {detail}" if detail else ""
    return f"{marker.symbol} {marker.label}{suffix}"


def _rgb(value: str) -> tuple[float, float, float]:
    if not _HEX.fullmatch(value):
        raise ValueError(f"invalid RGB colour: {value}")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def contrast_ratio(foreground: str, background: str) -> float:
    fg = _rgb(foreground)
    bg = _rgb(background)
    fg_luminance = 0.2126 * _linear(fg[0]) + 0.7152 * _linear(fg[1]) + 0.0722 * _linear(fg[2])
    bg_luminance = 0.2126 * _linear(bg[0]) + 0.7152 * _linear(bg[1]) + 0.0722 * _linear(bg[2])
    lighter = max(fg_luminance, bg_luminance)
    darker = min(fg_luminance, bg_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def html_theme_css(family: str) -> str:
    accents = {
        "software": ("#16324F", "#EDF4FF"),
        "education": ("#173B2D", "#EAF8F0"),
        "roadmap": ("#301934", "#F8ECFF"),
        "timeline": ("#4A2B10", "#FFF0DF"),
        "presentation": ("#14213D", "#EDF4FF"),
        "public-summary": ("#252B31", "#EEF1F4"),
    }
    if family not in accents:
        raise KeyError(f"unknown HTML visual family: {family}")
    accent, tint = accents[family]
    return (
        f":root{{--sw-accent:{accent};--sw-tint:{tint};--sw-text:#181818;--sw-border:#58636E}}"
        "body{font-family:system-ui,sans-serif;max-width:68rem;margin:0 auto;padding:2rem;"
        "line-height:1.5;color:var(--sw-text);background:#FFFFFF}"
        "header,footer{border-block:2px solid var(--sw-accent);padding:1rem 0}"
        "section{margin:2rem 0;padding:1rem;border-left:.35rem solid var(--sw-accent);"
        "background:var(--sw-tint)}.steps{padding-left:1.5rem}"
        ".meta{font-size:.9rem;color:#4B5563}.state{font-weight:700}"
        "a{color:var(--sw-accent);text-decoration-thickness:.12em;text-underline-offset:.18em}"
        "*:focus-visible{outline:3px solid var(--sw-accent);outline-offset:3px}"
        "@media print{body{max-width:none;padding:0}nav{display:none}}"
    )


def _visual_grammar_value() -> dict[str, Any]:
    raw = {
        "schema_version": GRAMMAR_SCHEMA_VERSION,
        "semantic_tokens": [token.to_dict() for token in SEMANTIC_TOKENS],
        "state_markers": [marker.to_dict() for marker in STATE_MARKERS],
        "provenance_contract": PROVENANCE_CONTRACT,
        "templates": [template.to_dict() for template in template_catalog()],
        "primitives": list(primitive_catalog()),
        "accessibility": {
            "minimum_normal_text_contrast": 4.5,
            "state_requires_text_and_symbol": True,
            "reading_order_required": True,
            "text_alternative_required": True,
            "colour_only_meaning_prohibited": True,
        },
    }
    # The public contract contains only JSON-native values so every renderer
    # sees the same arrays, booleans, numbers and strings.
    return json.loads(json.dumps(raw, ensure_ascii=False))


def visual_grammar_manifest() -> dict[str, Any]:
    manifest = _visual_grammar_value()
    validate_visual_grammar(manifest)
    return manifest


def validate_visual_grammar(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    value = _visual_grammar_value() if manifest is None else manifest
    if not isinstance(value, dict):
        raise ValueError("visual grammar manifest must be an object")
    if value.get("schema_version") != GRAMMAR_SCHEMA_VERSION:
        raise ValueError("unsupported visual grammar schema")
    expected_top_level = {
        "schema_version",
        "semantic_tokens",
        "state_markers",
        "provenance_contract",
        "templates",
        "primitives",
        "accessibility",
    }
    if set(value) != expected_top_level:
        raise ValueError("visual grammar top-level fields are invalid")
    tokens = value.get("semantic_tokens")
    states = value.get("state_markers")
    templates = value.get("templates")
    if (
        not isinstance(tokens, list)
        or not isinstance(states, list)
        or not isinstance(templates, list)
    ):
        raise ValueError("visual grammar catalogs are invalid")
    for label, entries in (("token", tokens), ("state", states), ("template", templates)):
        names = [entry.get("name") for entry in entries if isinstance(entry, dict)]
        if len(names) != len(entries) or len(set(names)) != len(names):
            raise ValueError(f"visual grammar {label} names are invalid")
    if [entry["name"] for entry in tokens] != [token.name for token in SEMANTIC_TOKENS]:
        raise ValueError("semantic token catalog is incomplete or reordered")
    if [entry["name"] for entry in states] != [marker.name for marker in STATE_MARKERS]:
        raise ValueError("state marker catalog is incomplete or reordered")
    token_fields = {
        "name",
        "role",
        "label",
        "shape",
        "symbol",
        "foreground",
        "background",
        "border",
        "text_alternative",
        "contrast_ratio",
    }
    state_fields = {
        "name",
        "label",
        "symbol",
        "foreground",
        "background",
        "border",
        "severity_rank",
        "non_colour_cues",
        "contrast_ratio",
    }
    template_fields = {
        "name",
        "purpose",
        "regions",
        "primitives",
        "invariants",
        "family",
        "audience",
        "reading_order",
        "supports_offline",
    }
    if any(not isinstance(entry, dict) or set(entry) != token_fields for entry in tokens):
        raise ValueError("semantic token fields are invalid")
    if any(not isinstance(entry, dict) or set(entry) != state_fields for entry in states):
        raise ValueError("state marker fields are invalid")
    if any(not isinstance(entry, dict) or set(entry) != template_fields for entry in templates):
        raise ValueError("visual template fields are invalid")
    for entry in [*tokens, *states]:
        if not isinstance(entry, dict):
            raise ValueError("visual grammar colour entry is invalid")
        foreground = entry.get("foreground")
        background = entry.get("background")
        if not isinstance(foreground, str) or not isinstance(background, str):
            raise ValueError("visual grammar colours are invalid")
        observed_contrast = contrast_ratio(foreground, background)
        if observed_contrast < 4.5:
            raise ValueError(f"visual grammar contrast is insufficient for {entry.get('name')}")
        if entry.get("contrast_ratio") != round(observed_contrast, 2):
            raise ValueError(f"visual grammar contrast receipt is invalid for {entry.get('name')}")
    for token in tokens:
        if not token.get("symbol") or not token.get("text_alternative"):
            raise ValueError("semantic token lacks non-colour meaning")
    for marker in states:
        cues = marker.get("non_colour_cues")
        if not marker.get("symbol") or not marker.get("label") or cues != ["text", "symbol"]:
            raise ValueError("state marker lacks non-colour cues")
    severity_ranks = [marker.get("severity_rank") for marker in states]
    if severity_ranks != list(range(len(states))):
        raise ValueError("state marker severity ranks are invalid")
    required_families = {
        "software",
        "education",
        "roadmap",
        "timeline",
        "presentation",
        "public-summary",
    }
    families = {template.get("family") for template in templates}
    if not required_families.issubset(families):
        raise ValueError("required visual templates are missing")
    available_primitives = set(primitive_names())
    for template in templates:
        regions = template.get("regions")
        reading_order = template.get("reading_order")
        primitives = template.get("primitives")
        invariants = template.get("invariants")
        if not regions or reading_order != regions or not invariants:
            raise ValueError(f"template reading contract is invalid: {template.get('name')}")
        if not set(primitives or []).issubset(available_primitives):
            raise ValueError(f"template primitives are invalid: {template.get('name')}")
    primitives = value.get("primitives")
    primitive_fields = {
        "name",
        "role",
        "use_for",
        "density",
        "supports_review",
        "layout_dsl",
    }
    if not isinstance(primitives, list) or any(
        not isinstance(item, dict) or set(item) != primitive_fields for item in primitives
    ):
        raise ValueError("visual primitive fields are invalid")
    if [item["name"] for item in primitives] != list(primitive_names()):
        raise ValueError("visual primitive order is invalid")
    provenance = value.get("provenance_contract")
    if not isinstance(provenance, dict) or set(provenance) != {
        "required_fields",
        "freshness_values",
        "uncertainty_values",
        "rules",
    }:
        raise ValueError("visual grammar provenance fields are invalid")
    expected_provenance = json.loads(json.dumps(PROVENANCE_CONTRACT, ensure_ascii=False))
    if provenance != expected_provenance:
        raise ValueError("visual grammar provenance contract is invalid")
    accessibility = value.get("accessibility")
    expected_accessibility = {
        "minimum_normal_text_contrast": 4.5,
        "state_requires_text_and_symbol": True,
        "reading_order_required": True,
        "text_alternative_required": True,
        "colour_only_meaning_prohibited": True,
    }
    if accessibility != expected_accessibility:
        raise ValueError("visual grammar accessibility contract is invalid")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "visual-grammar-validation-receipt.v1",
        "grammar_version": GRAMMAR_SCHEMA_VERSION,
        "token_count": len(tokens),
        "state_count": len(states),
        "template_count": len(templates),
        "minimum_contrast": round(
            min(
                contrast_ratio(item["foreground"], item["background"])
                for item in [*tokens, *states]
            ),
            2,
        ),
        "canonical_bytes": len(canonical.encode("utf-8")),
        "valid": True,
    }


def write_visual_grammar(path: Path) -> dict[str, Any]:
    """Write the canonical grammar manifest atomically and return validation evidence."""
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("visual grammar output path is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("visual grammar output path is unsafe")
    manifest = visual_grammar_manifest()
    text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise ValueError("visual grammar output could not be written") from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    receipt = validate_visual_grammar(manifest)
    receipt["output"] = str(path)
    receipt["manifest_bytes"] = len(text.encode("utf-8"))
    return receipt
