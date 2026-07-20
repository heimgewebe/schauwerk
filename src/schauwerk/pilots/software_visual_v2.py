"""Visual System v2 composition for validated software-pilot snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from schauwerk.visual.composer_v2 import (
    bounded_rows,
    clip_text,
    connector_object,
    document_object,
    frame,
    shape_object,
    table_object,
)
from schauwerk.visual.system_v2 import finalize_board_spec


def _source_evidence(snapshot: Mapping[str, Any]) -> str:
    sources = snapshot["sources"]
    visible = sources[:5]
    lines = [
        "# Quellenbindung",
        "",
        *[
            (
                f"- {clip_text(item['source_id'], 32)} · "
                f"Revision {item['revision'][:12]} · "
                f"{clip_text(item['reference'], 72)}"
            )
            for item in visible
        ],
    ]
    omitted = len(sources) - len(visible)
    if omitted:
        lines.append(f"- + {omitted} weitere Quellen im gebundenen Snapshot")
    lines.extend(
        [
            "",
            f"Snapshot: {snapshot['snapshot_digest']}",
            (
                "Aktualitätsgrenze: Revisionen sind belegt; "
                "ein Beobachtungszeitpunkt wird nicht behauptet."
            ),
        ]
    )
    return "\n".join(lines)


def compose_software_visual_board(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Compose one already-validated software snapshot as a narrative v2 board."""

    summary = snapshot["summary"]
    step = 1300
    frames: list[dict[str, Any]] = []

    cover = frame(
        "software_cover",
        1,
        "cover",
        summary["title"],
        "Ein quellgebundener Überblick: System, Entscheidungen, Lieferung, Risiken und Belege.",
        0,
    )
    cover["objects"].append(
        shape_object(
            "software_purpose",
            "orientation",
            80,
            300,
            960,
            180,
            clip_text(summary["purpose"], 210),
            color="structure",
        )
    )
    frames.append(cover)

    reading_map = frame(
        "software_map",
        2,
        "map",
        "Lesekarte",
        "Die Reihenfolge trennt Orientierung, Bewertung und Belege.",
        step,
    )
    reading_map["objects"].extend(
        [
            shape_object(
                "software_map_system",
                "orientation",
                80,
                320,
                180,
                120,
                "1\nSystem",
                color="structure",
            ),
            shape_object(
                "software_map_decision",
                "entity",
                340,
                320,
                180,
                120,
                "2\nEntscheidungen",
                color="structure",
            ),
            shape_object(
                "software_map_delivery",
                "decision",
                600,
                320,
                180,
                120,
                "3\nLieferung",
                color="decision",
            ),
            shape_object(
                "software_map_evidence",
                "evidence",
                860,
                320,
                180,
                120,
                "4\nBelege",
                color="evidence",
            ),
            connector_object(
                "software_map_a",
                "software_map_system",
                "software_map_decision",
                "Grund",
            ),
            connector_object(
                "software_map_b",
                "software_map_decision",
                "software_map_delivery",
                "Steuert",
            ),
            connector_object(
                "software_map_c",
                "software_map_delivery",
                "software_map_evidence",
                "Prüft",
            ),
        ]
    )
    frames.append(reading_map)

    architecture = frame(
        "software_architecture",
        3,
        "architecture",
        "System und Verantwortung",
        (
            f"{summary['component_count']} Komponenten werden als lesbare "
            "Systembeziehungen verdichtet."
        ),
        step * 2,
    )
    components = snapshot["components"]
    visible_components = components[:3]
    omitted_components = len(components) - len(visible_components)
    system_content = (
        f"Systemkern\n{len(visible_components)} von {len(components)} Komponenten sichtbar\n"
        f"Snapshot {snapshot['snapshot_digest'][:12]}"
    )
    if omitted_components:
        system_content += f"\n+ {omitted_components} weitere im Snapshot"
    architecture["objects"].append(
        shape_object(
            "software_architecture_system",
            "orientation",
            440,
            300,
            240,
            140,
            system_content,
            color="structure",
        )
    )
    component_positions = ((80, 300), (800, 300), (440, 460))
    for index, (component, (x, y)) in enumerate(
        zip(
            visible_components,
            component_positions[: len(visible_components)],
            strict=True,
        ),
        start=1,
    ):
        identifier = f"software_component_{index}"
        architecture["objects"].append(
            shape_object(
                identifier,
                "entity",
                x,
                y,
                240,
                100,
                (
                    f"{clip_text(component['title'], 36)}\n"
                    f"{clip_text(component['responsibility'], 72)}\n"
                    f"Status: {clip_text(component['status'], 24)}"
                ),
                color="structure",
            )
        )
        architecture["objects"].append(
            connector_object(
                f"software_architecture_link_{index}",
                "software_architecture_system",
                identifier,
                "verantwortet",
            )
        )
    frames.append(architecture)

    decisions = frame(
        "software_decisions",
        4,
        "decision",
        "Entscheidungen",
        f"{summary['decision_count']} Entscheidungen erklären, warum die Architektur so aussieht.",
        step * 3,
    )
    decisions["objects"].extend(
        [
            table_object(
                "software_decision_table",
                "comparison",
                80,
                300,
                620,
                220,
                "Entscheidungsstand",
                ("Entscheidung", "Status", "Wirkung"),
                bounded_rows(
                    snapshot["decisions"],
                    ("title", "status", "impact"),
                ),
            ),
            shape_object(
                "software_decision_guard",
                "decision",
                760,
                320,
                280,
                180,
                "Prüffrage\nIst die Wirkung jeder Entscheidung sichtbar?",
                color="decision",
                shape="rhombus",
            ),
        ]
    )
    frames.append(decisions)

    delivery = frame(
        "software_delivery",
        5,
        "delivery",
        "Roadmap und laufende Arbeit",
        (
            "Die geplante Folge und der aktuelle Arbeitsstand werden in einer "
            "gemeinsamen Lesefläche geprüft."
        ),
        step * 4,
    )
    roadmap = snapshot["roadmap"]
    visible_roadmap = roadmap[:3]
    omitted_roadmap = len(roadmap) - len(visible_roadmap)
    previous_identifier: str | None = None
    for index, item in enumerate(visible_roadmap, start=1):
        identifier = f"software_roadmap_step_{index}"
        content = (
            f"{index} · {clip_text(item['title'], 40)}\n"
            f"{clip_text(item['status'], 20)} · {clip_text(item['outcome'], 68)}"
        )
        if index == len(visible_roadmap) and omitted_roadmap:
            content += f"\n+ {omitted_roadmap} weitere im Snapshot"
        delivery["objects"].append(
            shape_object(
                identifier,
                "action",
                80,
                300 + (index - 1) * 100,
                440,
                60,
                content,
                color="decision",
            )
        )
        if previous_identifier is not None:
            delivery["objects"].append(
                connector_object(
                    f"software_roadmap_link_{index - 1}",
                    previous_identifier,
                    identifier,
                    "danach",
                )
            )
        previous_identifier = identifier
    delivery["objects"].append(
        table_object(
            "software_work",
            "comparison",
            600,
            300,
            440,
            220,
            "Aktuelle Arbeit",
            ("Arbeit", "Art", "Status"),
            bounded_rows(
                snapshot["work"],
                ("title", "kind", "status"),
            ),
        )
    )
    frames.append(delivery)

    tests_failed = summary["test_failed"] > 0
    risk = frame(
        "software_risk",
        6,
        "risk",
        "Risiken und Testsignal",
        (
            "Einzelne Risiken werden als Handlungsobjekte gezeigt und direkt "
            "dem Testsignal gegenübergestellt."
        ),
        step * 5,
    )
    risks = snapshot["risks"]
    visible_risks = risks[:2]
    omitted_risks = len(risks) - len(visible_risks)
    risk_positions = (80, 400)
    for index, (item, x) in enumerate(
        zip(visible_risks, risk_positions[: len(visible_risks)], strict=True),
        start=1,
    ):
        content = (
            f"{clip_text(item['title'], 46)}\n"
            f"{clip_text(item['severity'], 18)} · {clip_text(item['status'], 18)}\n"
            f"Gegenmaßnahme: {clip_text(item['mitigation'], 105)}"
        )
        if index == len(visible_risks) and omitted_risks:
            content += f"\n+ {omitted_risks} weitere im Snapshot"
        risk["objects"].append(
            shape_object(
                f"software_risk_{index}",
                "risk",
                x,
                300,
                300,
                200,
                content,
                color="risk",
            )
        )
    risk["objects"].append(
        shape_object(
            "software_tests",
            "risk" if tests_failed else "evidence",
            760,
            300,
            280,
            180,
            (
                f"Tests\n{summary['test_passed']}/{summary['test_total']} bestanden\n"
                f"{summary['test_status']}"
            ),
            color="risk" if tests_failed else "evidence",
        )
    )
    frames.append(risk)

    evidence = frame(
        "software_evidence",
        7,
        "evidence",
        "Evidenz und Grenzen",
        "Der Snapshot ist prüfbar; Aktualität und Vollständigkeit werden nicht erfunden.",
        step * 6,
    )
    evidence["objects"].extend(
        [
            document_object(
                "software_sources",
                80,
                300,
                600,
                220,
                _source_evidence(snapshot),
            ),
            table_object(
                "software_non_claims",
                "evidence",
                760,
                300,
                280,
                200,
                "Nicht-Ansprüche",
                ("Grenze",),
                (
                    ("kein Livezustand ohne Beobachtungszeit",),
                    ("keine Provider-Mutation",),
                    ("keine Vollansicht aller Datensätze",),
                ),
                color="evidence",
            ),
        ]
    )
    frames.append(evidence)

    return finalize_board_spec(
        title=f"{summary['title']} — Visual System v2",
        purpose="Narrative, source-bound software-project overview.",
        frames=frames,
    )
