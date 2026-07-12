"""Research-backed semantic and narrative visual system for Miro boards."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from . import miro_dsl as dsl

SYSTEM_SCHEMA = "schauwerk-visual-system.v2"
BOARD_SCHEMA = "schauwerk-visual-board.v2"
QUALITY_SCHEMA = "schauwerk-visual-quality.v2"
REVIEW_INPUT_SCHEMA = "schauwerk-visual-review-input.v2"
REVIEW_SCHEMA = "schauwerk-visual-review.v2"

_FRAME_ROLES = (
    "cover",
    "map",
    "object_selection",
    "architecture",
    "quality_gate",
    "example",
    "evidence",
)
_OBJECT_KINDS = {"text", "shape", "table", "doc", "sticky", "connector"}
_SUPPORTED_SHAPES = {
    "rectangle",
    "round_rectangle",
    "circle",
    "triangle",
    "rhombus",
    "hexagon",
    "octagon",
}
_FONT_SIZES = {"display": 38, "heading": 24, "body": 18, "caption": 14}
_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_REVIEW_AXES = (
    "information_architecture",
    "hierarchy",
    "object_selection",
    "density_and_whitespace",
    "palette_and_consistency",
    "readability",
    "aesthetic_character",
)

COLOR_ROLES: dict[str, dict[str, str]] = {
    "ink": {"foreground": "#102A43", "background": "#F8FAFC", "border": "#BCCCDC"},
    "structure": {"foreground": "#0B3C49", "background": "#E6F6F8", "border": "#147D92"},
    "evidence": {"foreground": "#173B2D", "background": "#EAF8F0", "border": "#2F855A"},
    "decision": {"foreground": "#3C2F12", "background": "#FFF8DD", "border": "#B7791F"},
    "risk": {"foreground": "#4A1010", "background": "#FFE8E8", "border": "#C53030"},
}

ROLE_CONTRACT: dict[str, dict[str, Any]] = {
    "title": {"kinds": ("text",), "colors": ("ink",), "fonts": ("display",)},
    "thesis": {"kinds": ("text",), "colors": ("ink", "structure"), "fonts": ("heading",)},
    "orientation": {"kinds": ("shape",), "colors": ("structure",), "fonts": ("body",)},
    "entity": {"kinds": ("shape",), "colors": ("structure", "ink"), "fonts": ("body",)},
    "comparison": {"kinds": ("table",), "colors": ("ink",), "fonts": ("body",)},
    "explanation": {"kinds": ("doc",), "colors": ("ink",), "fonts": ("body",)},
    "evidence": {"kinds": ("shape", "table", "doc"), "colors": ("evidence",), "fonts": ("body",)},
    "decision": {"kinds": ("shape",), "colors": ("decision",), "fonts": ("body",)},
    "risk": {"kinds": ("shape",), "colors": ("risk",), "fonts": ("body",)},
    "action": {"kinds": ("shape",), "colors": ("decision", "structure"), "fonts": ("body",)},
    "source": {"kinds": ("doc", "table"), "colors": ("evidence",), "fonts": ("body",)},
    "open_input": {"kinds": ("sticky",), "colors": ("decision",), "fonts": ("body",)},
    "relation": {"kinds": ("connector",), "colors": ("structure", "ink"), "fonts": ("caption",)},
    "caption": {"kinds": ("text",), "colors": ("ink",), "fonts": ("caption",)},
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def visual_system_manifest() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": SYSTEM_SCHEMA,
        "principles": [
            "information architecture before decoration",
            "one main claim per frame",
            "object type follows information function",
            "colour encodes role and is never the only cue",
            "reading path is explicit and finite",
            "evidence is accessible but visually subordinate",
            "declared design boxes are authoritative for overlap and density review",
            "Miro tables and documents are provider-auto-sized and verified by type and anchor",
            "remote readback proves conformance, not aesthetics",
        ],
        "frame_roles": list(_FRAME_ROLES),
        "object_kinds": sorted(_OBJECT_KINDS),
        "font_levels": dict(_FONT_SIZES),
        "color_roles": COLOR_ROLES,
        "role_contract": {
            name: {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in rule.items()
            }
            for name, rule in ROLE_CONTRACT.items()
        },
        "limits": {
            "min_frames": 5,
            "max_frames": 9,
            "max_objects_per_frame": 9,
            "max_stickies_per_board": 2,
            "max_connector_ratio": 0.35,
            "max_visual_coverage": 0.58,
            "max_body_characters": 220,
            "max_doc_characters": 900,
            "grid": 20,
            "frame_margin": 60,
        },
        "official_miro_references": [
            "https://miro.com/de/",
            "https://miro.com/de/templates/",
            "https://miro.com/de/capabilities/slides/",
            "https://miro.com/de/capabilities/diagrams/",
            "https://help.miro.com/hc/de",
        ],
    }
    value["manifest_digest"] = _digest(value)
    return value


def _text(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    content: str,
    *,
    font: str,
    color: str = "ink",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "text",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": content,
        "font_level": font,
        "color_role": color,
    }


def _shape(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    content: str,
    *,
    color: str,
    shape: str = "round_rectangle",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "shape",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": content,
        "font_level": "body",
        "color_role": color,
        "shape": shape,
    }


def _connector(identifier: str, source: str, target: str, label: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "connector",
        "role": "relation",
        "from": source,
        "to": target,
        "content": label,
        "font_level": "caption",
        "color_role": "structure",
    }


def _table(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    color: str = "ink",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "table",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "title": title,
        "columns": list(columns),
        "rows": [list(row) for row in rows],
        "content": " ".join([title, *columns, *(cell for row in rows for cell in row)]),
        "font_level": "body",
        "color_role": color,
        "provider_geometry": "auto_sized",
    }


def _doc(
    identifier: str,
    role: str,
    x: int,
    y: int,
    w: int,
    h: int,
    markdown: str,
    *,
    color: str = "evidence",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "doc",
        "role": role,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "content": markdown,
        "font_level": "body",
        "color_role": color,
        "provider_geometry": "auto_sized",
    }


def _frame(
    identifier: str, number: int, role: str, title: str, thesis: str, x: int
) -> dict[str, Any]:
    return {
        "id": identifier,
        "number": number,
        "role": role,
        "title": title,
        "x": x,
        "y": 0,
        "w": 1120,
        "h": 630,
        "background_role": "ink",
        "objects": [
            _text(f"{identifier}_title", "title", 80, 60, 960, 80, title, font="display"),
            _text(f"{identifier}_thesis", "thesis", 80, 160, 960, 80, thesis, font="heading"),
        ],
    }


def reference_board_spec() -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    gap = 180
    step = 1120 + gap

    cover = _frame(
        "f1_cover",
        1,
        "cover",
        "Schauwerk Visual System v2",
        "Klarheit vor Dekoration. Bedeutung vor Objektmenge.",
        0,
    )
    cover["objects"].append(
        _shape(
            "cover_rule",
            "orientation",
            80,
            300,
            960,
            160,
            (
                "Ein Schauwerk führt in 10 Sekunden zur Orientierung – "
                "und in wenigen Minuten zur belastbaren Einsicht."
            ),
            color="structure",
        )
    )
    frames.append(cover)

    map_frame = _frame(
        "f2_map",
        2,
        "map",
        "Lesekarte",
        "Jeder Inhalt erhält einen sichtbaren Platz im Erkenntnisweg.",
        step,
    )
    map_frame["objects"].extend(
        [
            _shape("map_a", "orientation", 80, 300, 180, 120, "1\nOrientieren", color="structure"),
            _shape("map_b", "entity", 340, 300, 180, 120, "2\nVerstehen", color="structure"),
            _shape("map_c", "decision", 600, 300, 180, 120, "3\nBewerten", color="decision"),
            _shape("map_d", "evidence", 860, 300, 180, 120, "4\nBelegen", color="evidence"),
            _connector("map_ab", "map_a", "map_b", "weiter"),
            _connector("map_bc", "map_b", "map_c", "prüfen"),
            _connector("map_cd", "map_c", "map_d", "sichern"),
        ]
    )
    frames.append(map_frame)

    objects = _frame(
        "f3_objects",
        3,
        "object_selection",
        "Objektwahl",
        "Nicht alles ist eine Haftnotiz. Die Form trägt die Bedeutung.",
        step * 2,
    )
    objects["objects"].extend(
        [
            _table(
                "objects_matrix",
                "comparison",
                80,
                300,
                680,
                220,
                "Inhalt → Miro-Objekt",
                ("Inhalt", "Objekt", "Warum"),
                (
                    ("Beziehung", "Connector", "Richtung sichtbar"),
                    ("Vergleich", "Tabelle", "Dichte ohne Kartenwand"),
                    ("Erklärung", "Dokument", "Text bleibt lesbar"),
                    ("Offene Idee", "Haftnotiz", "bewusst veränderlich"),
                ),
            ),
            _shape(
                "objects_guard",
                "risk",
                800,
                320,
                240,
                180,
                "Blocker\nHaftnotizen für fertige Fakten oder lange Erklärungen",
                color="risk",
            ),
        ]
    )
    frames.append(objects)

    architecture = _frame(
        "f4_architecture",
        4,
        "architecture",
        "Informationsarchitektur",
        "Ein Frame beantwortet eine Hauptfrage – nicht sieben Nebenfragen.",
        step * 3,
    )
    architecture["objects"].extend(
        [
            _shape(
                "arch_a",
                "orientation",
                80,
                300,
                180,
                120,
                "Einstieg\nWorum geht es?",
                color="structure",
            ),
            _shape("arch_b", "entity", 340, 300, 180, 120, "Kern\nWas gilt?", color="structure"),
            _shape(
                "arch_c", "decision", 600, 300, 180, 120, "Synthese\nWas folgt?", color="decision"
            ),
            _shape(
                "arch_d",
                "evidence",
                860,
                300,
                180,
                120,
                "Evidenz\nWoher wissen wir es?",
                color="evidence",
            ),
            _connector("arch_ab", "arch_a", "arch_b", "fokussieren"),
            _connector("arch_bc", "arch_b", "arch_c", "verdichten"),
            _connector("arch_cd", "arch_c", "arch_d", "belegen"),
        ]
    )
    frames.append(architecture)

    quality = _frame(
        "f5_quality",
        5,
        "quality_gate",
        "Qualitätsgate v2",
        "Viele Objekte ergeben noch kein gutes Board.",
        step * 4,
    )
    quality["objects"].extend(
        [
            _table(
                "quality_matrix",
                "comparison",
                80,
                300,
                680,
                220,
                "Freigabekriterien",
                ("Dimension", "Muss gelten"),
                (
                    ("Narration", "Lesepfad vollständig"),
                    ("Hierarchie", "Titel und Kernaussage eindeutig"),
                    ("Dichte", "mindestens 42 % Weißraum"),
                    ("Semantik", "Objekt und Farbe erfüllen eine Rolle"),
                ),
            ),
            _shape(
                "quality_decision",
                "decision",
                800,
                320,
                240,
                180,
                "Freigabe\n≥ 90 Punkte\n0 Blocker",
                color="decision",
                shape="rhombus",
            ),
        ]
    )
    frames.append(quality)

    example = _frame(
        "f6_example",
        6,
        "example",
        "Vorher / Nachher",
        "Der Unterschied liegt in der Ordnung, nicht im Schmuck.",
        step * 5,
    )
    example["objects"].extend(
        [
            _shape(
                "example_before",
                "risk",
                80,
                300,
                360,
                200,
                "Vorher\nTechnisch reich\nvisuell gleichgewichtet\nkein klarer Fokus",
                color="risk",
            ),
            _shape(
                "example_after",
                "evidence",
                680,
                300,
                360,
                200,
                "Nachher\n7 Rollenframes\nklare Dramaturgie\nsemantische Objekte",
                color="evidence",
            ),
            _connector("example_change", "example_before", "example_after", "neu ordnen"),
        ]
    )
    frames.append(example)

    evidence = _frame(
        "f7_evidence",
        7,
        "evidence",
        "Evidenz und Grenzen",
        "Gestaltung bleibt prüfbar, ohne sich als objektive Schönheit auszugeben.",
        step * 6,
    )
    evidence["objects"].extend(
        [
            _doc(
                "evidence_sources",
                "source",
                80,
                300,
                600,
                220,
                (
                    "# Forschungsbasis\n\nMiro: Canvas, Diagramme, Präsentationen, "
                    "Vorlagen, Focus Mode, Layers und Hilfecenter.\n\nDer "
                    "deterministische Plan wird vollständig geprüft; der Remote-Readback "
                    "bestätigt nur die Umsetzung."
                ),
            ),
            _table(
                "evidence_limits",
                "evidence",
                760,
                300,
                280,
                200,
                "Nicht-Ansprüche",
                ("Grenze",),
                (
                    ("kein universeller Geschmack",),
                    ("keine automatische Fremdboard-Änderung",),
                    ("keine Schönheit durch Objektzählung",),
                ),
                color="evidence",
            ),
        ]
    )
    frames.append(evidence)

    value: dict[str, Any] = {
        "schema_version": BOARD_SCHEMA,
        "title": "Schauwerk Visual System v2 – Klarheit vor Dekoration",
        "purpose": (
            "Reference board for semantic object choice, narrative hierarchy and "
            "meaningful visual quality gates."
        ),
        "reading_path": [frame["id"] for frame in frames],
        "frames": frames,
        "visual_system_digest": visual_system_manifest()["manifest_digest"],
        "remote_readback_role": "conformance_only",
    }
    value["board_digest"] = _digest(value)
    return value


def _text_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sum(_text_length(item) for item in value)
    if isinstance(value, Mapping):
        return sum(_text_length(item) for item in value.values())
    return 0


def audit_board_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def block(code: str, message: str, **evidence: Any) -> None:
        blockers.append({"code": code, "message": message, "evidence": evidence})

    def warn(code: str, message: str, **evidence: Any) -> None:
        warnings.append({"code": code, "message": message, "evidence": evidence})

    if spec.get("schema_version") != BOARD_SCHEMA:
        block("schema", "unsupported board schema")
    frames = spec.get("frames")
    if not isinstance(frames, list):
        frames = []
        block("frames", "frames must be a list")
    limits = visual_system_manifest()["limits"]
    if not limits["min_frames"] <= len(frames) <= limits["max_frames"]:
        block("frame_count", "frame count is outside the narrative range", count=len(frames))

    frame_ids = [frame.get("id") for frame in frames if isinstance(frame, Mapping)]
    reading_path = spec.get("reading_path")
    if not isinstance(reading_path, list) or reading_path != frame_ids:
        block("reading_path", "reading path must list every frame exactly once in display order")
    roles = [frame.get("role") for frame in frames if isinstance(frame, Mapping)]
    if roles and roles[0] != "cover":
        block("cover_missing", "reading path must begin with a cover frame")
    if roles and roles[-1] != "evidence":
        block("evidence_not_terminal", "evidence must be separated at the end")
    if len(set(frame_ids)) != len(frame_ids):
        block("duplicate_frame_id", "frame identifiers must be unique")

    all_object_ids: set[str] = set()
    provider_auto_sized_count = 0
    sticky_count = 0
    connector_count = 0
    non_connector_count = 0
    used_colors: set[str] = set()
    dimension_pairs: set[tuple[int, int]] = set()
    categories = {
        "architecture": 20,
        "semantics": 20,
        "hierarchy": 20,
        "density": 20,
        "consistency": 20,
    }

    for index, raw_frame in enumerate(frames):
        if not isinstance(raw_frame, Mapping):
            block("frame_type", "frame must be an object", index=index)
            continue
        raw_frame_id = raw_frame.get("id")
        frame_id = raw_frame_id if isinstance(raw_frame_id, str) else ""
        if not _SAFE_ID.fullmatch(frame_id):
            block("frame_id", "frame identifier is unsafe", frame=frame_id)
        role = raw_frame.get("role")
        if role not in _FRAME_ROLES:
            block("frame_role", "frame role is unsupported", frame=frame_id, role=role)
        width = raw_frame.get("w")
        height = raw_frame.get("h")
        if not isinstance(width, int) or not isinstance(height, int) or width < 800 or height < 450:
            block("frame_geometry", "frame geometry is invalid", frame=frame_id)
            width, height = 1, 1
        dimension_pairs.add((width, height))
        objects = raw_frame.get("objects")
        if not isinstance(objects, list):
            block("objects", "frame objects must be a list", frame=frame_id)
            continue
        if len(objects) > limits["max_objects_per_frame"]:
            block(
                "frame_overloaded",
                "frame contains too many equal-weight objects",
                frame=frame_id,
                count=len(objects),
            )
        title_objects = [
            obj for obj in objects if isinstance(obj, Mapping) and obj.get("role") == "title"
        ]
        thesis_objects = [
            obj for obj in objects if isinstance(obj, Mapping) and obj.get("role") == "thesis"
        ]
        if len(title_objects) != 1 or len(thesis_objects) != 1:
            block("hierarchy", "each frame needs exactly one title and thesis", frame=frame_id)
        coverage = 0.0
        local_ids: set[str] = set()
        connectors: list[Mapping[str, Any]] = []
        design_boxes: list[tuple[str, int, int, int, int]] = []
        for raw_object in objects:
            if not isinstance(raw_object, Mapping):
                block("object_type", "visual object must be an object", frame=frame_id)
                continue
            object_id = raw_object.get("id")
            kind = raw_object.get("kind")
            object_role = raw_object.get("role")
            color_role = raw_object.get("color_role")
            font_level = raw_object.get("font_level")
            if not isinstance(object_id, str) or not _SAFE_ID.fullmatch(object_id):
                block("object_id", "visual object identifier is unsafe", frame=frame_id)
                continue
            if object_id in all_object_ids:
                block(
                    "duplicate_object_id",
                    "visual object ids must be globally unique",
                    object=object_id,
                )
            all_object_ids.add(object_id)
            local_ids.add(object_id)
            if kind not in _OBJECT_KINDS:
                block("object_kind", "unsupported visual object kind", object=object_id, kind=kind)
                continue
            contract = ROLE_CONTRACT.get(str(object_role))
            if contract is None:
                block(
                    "object_role",
                    "unsupported semantic object role",
                    object=object_id,
                    role=object_role,
                )
            else:
                if kind not in contract["kinds"]:
                    block(
                        "object_misuse",
                        "object kind does not match information function",
                        object=object_id,
                        kind=kind,
                        role=object_role,
                    )
                if color_role not in contract["colors"]:
                    block(
                        "colour_misuse",
                        "colour role does not match semantic role",
                        object=object_id,
                        color_role=color_role,
                        role=object_role,
                    )
                if font_level not in contract["fonts"]:
                    block(
                        "font_hierarchy",
                        "font level does not match semantic role",
                        object=object_id,
                        font_level=font_level,
                        role=object_role,
                    )
            if color_role in COLOR_ROLES:
                used_colors.add(str(color_role))
            else:
                block("unknown_colour", "unknown semantic colour role", object=object_id)
            if (
                kind == "shape"
                and raw_object.get("shape", "round_rectangle") not in _SUPPORTED_SHAPES
            ):
                block(
                    "unsupported_shape",
                    "shape type is not supported by the Miro layout contract",
                    object=object_id,
                    shape=raw_object.get("shape"),
                )
            if kind in {"table", "doc"}:
                if raw_object.get("provider_geometry") != "auto_sized":
                    block(
                        "provider_geometry",
                        "rich Miro objects must declare provider-auto-sized geometry",
                        object=object_id,
                    )
                provider_auto_sized_count += 1
            elif "provider_geometry" in raw_object:
                block(
                    "provider_geometry",
                    "only rich Miro objects may declare provider-auto-sized geometry",
                    object=object_id,
                )
            if kind == "sticky":
                sticky_count += 1
            if kind == "connector":
                connector_count += 1
                connectors.append(raw_object)
                continue
            non_connector_count += 1
            x, y, w, h = (raw_object.get(key) for key in ("x", "y", "w", "h"))
            if any(not isinstance(value, int) for value in (x, y, w, h)):
                block(
                    "object_geometry", "visual object geometry must be integral", object=object_id
                )
                continue
            assert (
                isinstance(x, int)
                and isinstance(y, int)
                and isinstance(w, int)
                and isinstance(h, int)
            )
            margin = limits["frame_margin"]
            if x < margin or y < margin or x + w > width - margin or y + h > height - margin:
                block(
                    "object_margin",
                    "visual object violates the frame safety margin",
                    object=object_id,
                )
            if any(value % limits["grid"] for value in (x, y, w, h)):
                warn(
                    "off_grid",
                    "visual object is not aligned to the canonical grid",
                    object=object_id,
                )
            design_boxes.append((object_id, x, y, w, h))
            coverage += (w * h) / (width * height)
            length = _text_length(raw_object.get("content", ""))
            maximum = (
                limits["max_doc_characters"] if kind == "doc" else limits["max_body_characters"]
            )
            if length > maximum:
                block(
                    "text_density",
                    "content exceeds the object-type density limit",
                    object=object_id,
                    characters=length,
                )
        for left_index, left in enumerate(design_boxes):
            left_id, left_x, left_y, left_w, left_h = left
            for right in design_boxes[left_index + 1 :]:
                right_id, right_x, right_y, right_w, right_h = right
                overlap_w = min(left_x + left_w, right_x + right_w) - max(left_x, right_x)
                overlap_h = min(left_y + left_h, right_y + right_h) - max(left_y, right_y)
                if overlap_w > 0 and overlap_h > 0:
                    block(
                        "object_overlap",
                        "declared design boxes overlap",
                        frame=frame_id,
                        objects=sorted((left_id, right_id)),
                        overlap_area=overlap_w * overlap_h,
                    )
        for connector in connectors:
            if connector.get("from") not in local_ids or connector.get("to") not in local_ids:
                block(
                    "cross_frame_connector",
                    "connectors must stay inside one narrative frame",
                    object=connector.get("id"),
                )
        if coverage > limits["max_visual_coverage"]:
            block(
                "white_space",
                "frame leaves too little deliberate white space",
                frame=frame_id,
                coverage=round(coverage, 3),
            )
        elif coverage > 0.5:
            warn("density_high", "frame is close to the maximum visual density", frame=frame_id)

    if sticky_count > limits["max_stickies_per_board"]:
        block(
            "sticky_dominance", "too many sticky notes for a finished Schauwerk", count=sticky_count
        )
    if (
        non_connector_count
        and connector_count / non_connector_count > limits["max_connector_ratio"]
    ):
        block(
            "connector_clutter",
            "connector ratio is too high for a presentation-grade board",
            connectors=connector_count,
            visual_objects=non_connector_count,
        )
    if len(dimension_pairs) > 1:
        warn(
            "frame_size_variance",
            "frame sizes vary and weaken presentation rhythm",
            variants=len(dimension_pairs),
        )
    if len(used_colors) > len(COLOR_ROLES):
        block("palette", "palette exceeds the semantic colour system", count=len(used_colors))
    if "structure" not in used_colors or "evidence" not in used_colors:
        block("semantic_palette", "structure and evidence roles must both be visible")

    for finding in blockers:
        code = finding["code"]
        if code in {"reading_path", "cover_missing", "evidence_not_terminal", "frame_count"}:
            categories["architecture"] = max(0, categories["architecture"] - 10)
        elif code in {"object_misuse", "colour_misuse", "object_role", "sticky_dominance"}:
            categories["semantics"] = max(0, categories["semantics"] - 7)
        elif code in {"hierarchy", "font_hierarchy"}:
            categories["hierarchy"] = max(0, categories["hierarchy"] - 10)
        elif code in {
            "white_space",
            "text_density",
            "frame_overloaded",
            "connector_clutter",
            "object_overlap",
        }:
            categories["density"] = max(0, categories["density"] - 8)
        else:
            categories["consistency"] = max(0, categories["consistency"] - 5)
    for finding in warnings:
        if finding["code"] in {"density_high"}:
            categories["density"] = max(0, categories["density"] - 2)
        else:
            categories["consistency"] = max(0, categories["consistency"] - 2)

    score = sum(categories.values())
    value: dict[str, Any] = {
        "schema_version": QUALITY_SCHEMA,
        "ok": not blockers and score >= 90,
        "score": score,
        "threshold": 90,
        "category_scores": categories,
        "blockers": blockers,
        "warnings": warnings,
        "frame_count": len(frames),
        "object_count": non_connector_count + connector_count,
        "connector_count": connector_count,
        "sticky_count": sticky_count,
        "semantic_color_count": len(used_colors),
        "provider_auto_sized_count": provider_auto_sized_count,
        "geometry_contract": {
            "declared_boxes": "design_review_only",
            "text_shape_sticky": "provider_dimensions_requested",
            "table_doc": "provider_auto_sized_type_and_anchor_verified",
        },
        "board_digest": spec.get("board_digest"),
        "mutation_attempted": False,
        "remote_geometry_required": False,
    }
    value["quality_digest"] = _digest(value)
    return value


def validate_board_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    receipt = audit_board_spec(spec)
    if not receipt["ok"]:
        codes = ", ".join(item["code"] for item in receipt["blockers"]) or "score_below_threshold"
        raise ValueError(f"visual board v2 quality gate failed: {codes}")
    expected = dict(spec)
    declared = expected.pop("board_digest", None)
    if declared != _digest(expected):
        raise ValueError("visual board v2 digest mismatch")
    if spec.get("visual_system_digest") != visual_system_manifest()["manifest_digest"]:
        raise ValueError("visual board v2 is bound to a different visual system")
    return receipt


def render_board_dsl(spec: Mapping[str, Any]) -> str:
    validate_board_spec(spec)
    lines: list[str] = []
    for frame in spec["frames"]:
        frame_id = frame["id"]
        lines.append(
            dsl.line(
                frame_id,
                "FRAME",
                x=frame["x"],
                y=frame["y"],
                w=frame["w"],
                h=frame["h"],
                fill=COLOR_ROLES[frame["background_role"]]["background"],
                content=f"{frame['number']:02d} · {frame['title']}",
            )
        )
        for item in frame["objects"]:
            kind = item["kind"]
            colors = COLOR_ROLES[item["color_role"]]
            if kind == "text":
                lines.append(
                    dsl.line(
                        item["id"],
                        "TEXT",
                        parent=frame_id,
                        x=item["x"] + item["w"] // 2,
                        y=item["y"] + item["h"] // 2,
                        w=item["w"],
                        font="open_sans",
                        size=_FONT_SIZES[item["font_level"]],
                        align="left",
                        color=colors["foreground"],
                        content=item["content"],
                    )
                )
            elif kind == "shape":
                lines.append(
                    dsl.line(
                        item["id"],
                        "SHAPE",
                        parent=frame_id,
                        x=item["x"] + item["w"] // 2,
                        y=item["y"] + item["h"] // 2,
                        w=item["w"],
                        h=item["h"],
                        type=item.get("shape", "round_rectangle"),
                        fill=colors["background"],
                        border_color=colors["border"],
                        color=colors["foreground"],
                        font="open_sans",
                        size=_FONT_SIZES[item["font_level"]],
                        valign="middle",
                        content=item["content"].replace("\n", "<br>"),
                    )
                )
            elif kind == "table":
                lines.append(
                    dsl.table(
                        item["id"],
                        parent=frame_id,
                        x=item["x"] + item["w"] // 2,
                        y=item["y"] + item["h"] // 2,
                        title=item["title"],
                        columns=item["columns"],
                        rows=item["rows"],
                    )
                )
            elif kind == "doc":
                lines.append(
                    dsl.doc(
                        item["id"],
                        parent=frame_id,
                        x=item["x"] + item["w"] // 2,
                        y=item["y"] + item["h"] // 2,
                        markdown=item["content"],
                    )
                )
            elif kind == "sticky":
                lines.append(
                    dsl.line(
                        item["id"],
                        "STICKY",
                        parent=frame_id,
                        x=item["x"] + item["w"] // 2,
                        y=item["y"] + item["h"] // 2,
                        w=item["w"],
                        color="light_yellow",
                        content=item["content"],
                    )
                )
            elif kind == "connector":
                lines.append(
                    dsl.line(
                        item["id"],
                        "CONNECTOR",
                        **{"from": item["from"], "to": item["to"]},
                        shape="elbowed",
                        end_cap="arrow",
                        content=item["content"],
                    )
                )
    return "\n".join(lines) + "\n"


def _review_text(value: Any, *, label: str, maximum: int = 600) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValueError(f"{label} is invalid")
    return text


def _review_timestamp(value: Any) -> str:
    text = _review_text(value, label="reviewed_at", maximum=40)
    if not text.endswith("Z"):
        raise ValueError("reviewed_at must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("reviewed_at must be a canonical UTC timestamp") from exc
    canonical = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if text != canonical:
        raise ValueError("reviewed_at must be a canonical UTC timestamp")
    return text


def compile_visual_review(
    live_receipt: Mapping[str, Any], review_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind a human visual review to one quality-gated, remotely confirmed live board."""

    if live_receipt.get("schema_version") != "schauwerk-visual-system-live-test.v2":
        raise ValueError("visual review requires a Visual System v2 live receipt")
    local_quality = live_receipt.get("local_quality")
    remote_conformance = live_receipt.get("remote_conformance")
    if not isinstance(local_quality, Mapping) or local_quality.get("ok") is not True:
        raise ValueError("visual review requires a passing local quality receipt")
    if not isinstance(remote_conformance, Mapping) or remote_conformance.get("ok") is not True:
        raise ValueError("visual review requires passing remote conformance")
    score = local_quality.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 90 <= score <= 100:
        raise ValueError("visual review local quality score is invalid")
    quality_digest = local_quality.get("quality_digest")
    if (
        not isinstance(quality_digest, str)
        or len(quality_digest) != 64
        or any(char not in "0123456789abcdef" for char in quality_digest)
    ):
        raise ValueError("visual review local quality digest is invalid")

    expected_input_fields = {
        "schema_version",
        "reviewed_at",
        "reviewer",
        "board_digest",
        "method",
        "axes",
        "verdict",
        "non_claims",
    }
    if not isinstance(review_input, Mapping) or set(review_input) != expected_input_fields:
        raise ValueError("visual review input fields are invalid")
    if review_input.get("schema_version") != REVIEW_INPUT_SCHEMA:
        raise ValueError("visual review input schema is unsupported")
    board_digest = _review_text(review_input.get("board_digest"), label="board_digest", maximum=64)
    if len(board_digest) != 64 or any(char not in "0123456789abcdef" for char in board_digest):
        raise ValueError("board_digest is invalid")
    if board_digest != local_quality.get("board_digest"):
        raise ValueError("visual review board digest does not match the live receipt")

    method = review_input.get("method")
    expected_method_fields = {
        "design_surface",
        "provider_binding",
        "authenticated_provider_screenshot",
        "excluded_capture",
    }
    if not isinstance(method, Mapping) or set(method) != expected_method_fields:
        raise ValueError("visual review method fields are invalid")
    normalized_method = {
        key: _review_text(method.get(key), label=f"method.{key}") for key in sorted(method)
    }
    if normalized_method["authenticated_provider_screenshot"] not in {"available", "not_available"}:
        raise ValueError("authenticated provider screenshot status is invalid")
    if normalized_method["design_surface"] != "deterministic board-spec visual preview":
        raise ValueError("visual review must name the deterministic design surface")
    if (
        normalized_method["provider_binding"]
        != "exact remote item-type and connector-count conformance"
    ):
        raise ValueError("visual review provider binding is invalid")

    axes = review_input.get("axes")
    if not isinstance(axes, Mapping) or set(axes) != set(_REVIEW_AXES):
        raise ValueError("visual review axes are incomplete")
    normalized_axes: dict[str, dict[str, str]] = {}
    for axis in _REVIEW_AXES:
        raw = axes.get(axis)
        if not isinstance(raw, Mapping) or set(raw) != {"verdict", "finding"}:
            raise ValueError(f"visual review axis {axis} fields are invalid")
        verdict = _review_text(raw.get("verdict"), label=f"axes.{axis}.verdict", maximum=4)
        if verdict not in {"PASS", "FAIL"}:
            raise ValueError(f"visual review axis {axis} verdict is invalid")
        normalized_axes[axis] = {
            "verdict": verdict,
            "finding": _review_text(raw.get("finding"), label=f"axes.{axis}.finding"),
        }

    verdict = _review_text(review_input.get("verdict"), label="verdict", maximum=4)
    if verdict not in {"PASS", "FAIL"}:
        raise ValueError("visual review verdict is invalid")
    failed_axes = [axis for axis, value in normalized_axes.items() if value["verdict"] == "FAIL"]
    if verdict == "PASS" and failed_axes:
        raise ValueError("passing visual review cannot contain failed axes")
    if verdict == "FAIL" and not failed_axes:
        raise ValueError("failed visual review must identify at least one failed axis")

    non_claims = review_input.get("non_claims")
    if not isinstance(non_claims, list) or not non_claims or len(non_claims) > 12:
        raise ValueError("visual review non-claims are invalid")
    normalized_non_claims = [
        _review_text(item, label="non_claim", maximum=180) for item in non_claims
    ]
    if len(set(normalized_non_claims)) != len(normalized_non_claims):
        raise ValueError("visual review non-claims must be unique")

    board = live_receipt.get("board")
    if not isinstance(board, Mapping):
        raise ValueError("visual review live board binding is invalid")
    alias = _review_text(live_receipt.get("alias"), label="alias", maximum=96)
    reference_digest = _review_text(
        board.get("reference_digest"), label="board reference digest", maximum=64
    )
    if len(reference_digest) < 8 or any(
        char not in "0123456789abcdef" for char in reference_digest
    ):
        raise ValueError("visual review board reference digest is invalid")

    observed = remote_conformance.get("observed")
    mismatches = remote_conformance.get("mismatches")
    if not isinstance(observed, Mapping) or mismatches != {}:
        raise ValueError("visual review remote conformance is not exact")
    normalized_observed: dict[str, int] = {}
    for key in ("connector_count", "doc_count", "frame_count", "remote_item_count", "table_count"):
        value = observed.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("visual review remote counts are invalid")
        normalized_observed[key] = value

    value: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA,
        "reviewed_at": _review_timestamp(review_input.get("reviewed_at")),
        "reviewer": _review_text(review_input.get("reviewer"), label="reviewer", maximum=120),
        "board_alias": alias,
        "board_reference_digest": reference_digest,
        "board_digest": board_digest,
        "method": normalized_method,
        "axes": normalized_axes,
        "verdict": verdict,
        "failed_axes": failed_axes,
        "automatic_quality": {
            "score": score,
            "quality_digest": quality_digest,
            "automatic_aesthetic_claim": False,
        },
        "remote_conformance": {
            "observed": normalized_observed,
            "mismatches": {},
            "geometry_used_for_aesthetic_score": False,
        },
        "non_claims": normalized_non_claims,
        "source_receipts": {
            "live_receipt_digest": _digest(live_receipt),
            "quality_digest": quality_digest,
        },
        "mutation_attempted": False,
    }
    value["review_digest"] = _digest(value)
    return value


def _reject_symlink_chain(path: Path) -> None:
    candidate = path.expanduser().absolute()
    chain = [candidate]
    chain.extend(candidate.parents)
    for component in reversed(chain):
        if component.exists() and component.is_symlink():
            raise ValueError("visual-system output path must not contain symlinks")


def _write_bytes(path: Path, payload: bytes) -> Path:
    destination = path.expanduser().absolute()
    _reject_symlink_chain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_chain(destination)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return destination


def write_json(path: Path, value: Mapping[str, Any]) -> Path:
    return _write_bytes(
        path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    )


def write_text(path: Path, value: str) -> Path:
    return _write_bytes(path, value.encode("utf-8"))
