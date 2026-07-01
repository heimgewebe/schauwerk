# ruff: noqa: E501
"""Zoomable learning-map renderer."""

from __future__ import annotations

from collections.abc import Iterable

from ..visual.miro_dsl import doc, line, table
from .view import LearningStep, LearningView


def _rows(items: Iterable[str], fallback: str) -> tuple[tuple[str, str], ...]:
    values = tuple(items) or (fallback,)
    return tuple((str(index), value) for index, value in enumerate(values, start=1))


def _step_label(step: LearningStep, index: int) -> str:
    minutes = f" ({step.minutes} min)" if step.minutes else ""
    return f"{index}. {step.title}{minutes}"


def _step_detail(step: LearningStep) -> str:
    return f"{step.activity} Ergebnis: {step.output}" if step.output else step.activity


def _cluster(identifier: str, *, x: int, y: int, title: str, subtitle: str) -> list[str]:
    title_line = line(
        f"title_{identifier}",
        "TEXT",
        parent=identifier,
        x=1900,
        y=160,
        w=3300,
        font="open_sans",
        size=30,
        align="center",
        color="#1a1a1a",
        content=f"<p><b>{title}</b></p><p>{subtitle}</p>",
    )
    frame_line = line(identifier, "FRAME", x=x, y=y, w=3800, h=3000, fill="#F4F6F8", content=title)
    return [frame_line, title_line]


def render_learning_zoomlandkarte_dsl(view: LearningView) -> str:
    step_rows = tuple(
        (_step_label(step, index), _step_detail(step))
        for index, step in enumerate(view.steps, start=1)
    )
    term_rows = tuple((term, "erklaeren / Beispiel finden") for term in view.key_terms) or (
        ("Schluesselbegriff", "im Cluster klaeren"),
    )
    material_rows = tuple((item, "Quelle pruefen") for item in view.materials) or (
        ("Board", "Arbeitsflaeche"),
        ("Notizen", "Belege sichern"),
    )

    lines = [
        line(
            "zoom_root",
            "FRAME",
            x=0,
            y=900,
            w=17600,
            h=11400,
            fill="#FFFFFF",
            content="Schauwerk Zoomlandkarte",
        ),
        line(
            "zoom_title",
            "TEXT",
            parent="zoom_root",
            x=8800,
            y=260,
            w=7600,
            font="open_sans",
            size=48,
            align="center",
            color="#111111",
            content=f"{view.topic} — Zoomlandkarte fuer {view.audience}",
        ),
        line(
            "zoom_question",
            "SHAPE",
            parent="zoom_root",
            x=8800,
            y=660,
            w=7200,
            h=160,
            type="round_rectangle",
            fill="#1a1a1a",
            color="#FFFFFF",
            font="open_sans",
            size=30,
            valign="middle",
            content=f"Leitfrage: {view.guiding_question}",
        ),
    ]

    lines.append(
        line(
            "macro_overview",
            "FRAME",
            x=-6400,
            y=-4700,
            w=5400,
            h=2400,
            fill="#EEF3FF",
            content="00 Gesamtueberblick",
        )
    )
    lines.append(
        line(
            "production_lane",
            "FRAME",
            x=-400,
            y=-4700,
            w=8200,
            h=2400,
            fill="#F2F7F2",
            content="01 Produktionsstrecke",
        )
    )
    lines.append(
        line(
            "risk_legend",
            "FRAME",
            x=7000,
            y=-4700,
            w=4200,
            h=2400,
            fill="#FFF6E8",
            content="02 Legende Risiko",
        )
    )
    lines.append(
        doc(
            "macro_doc",
            parent="macro_overview",
            x=2700,
            y=760,
            markdown=f"# {view.topic}\n\nZoom-out: Cluster.\n\nZoom-in: Details im Cluster.",
        )
    )
    lines.append(
        table(
            "macro_table",
            parent="macro_overview",
            x=2700,
            y=1550,
            title="Cluster-Legende",
            columns=("Cluster", "Funktion"),
            rows=(("A", "Orientierung"), ("B", "Lernweg"), ("C", "Sicherung")),
        )
    )
    lines.append(
        table(
            "risk_table",
            parent="risk_legend",
            x=2100,
            y=760,
            title="Legende",
            columns=("Signal", "Bedeutung"),
            rows=(("A", "zuerst"), ("B", "anwenden"), ("C", "pruefen")),
        )
    )
    prod = (
        ("prod_source", "Sichten"),
        ("prod_inventory", "Sortieren"),
        ("prod_cluster", "Clustern"),
        ("prod_deepen", "Vertiefen"),
        ("prod_teach", "Erklaeren"),
        ("prod_check", "Sichern"),
    )
    previous = None
    for index, (identifier, label_text) in enumerate(prod):
        x = 650 + index * 1180
        lines.append(
            line(
                identifier,
                "SHAPE",
                parent="production_lane",
                x=x,
                y=900,
                w=900,
                h=360,
                type="round_rectangle",
                fill="#FFFFFF",
                color="#1a1a1a",
                font="open_sans",
                size=24,
                valign="middle",
                content=label_text,
            )
        )
        if previous:
            lines.append(
                line(
                    f"e_{previous}_{identifier}",
                    "CONNECTOR",
                    **{"from": previous, "to": identifier},
                    shape="elbowed",
                    end_cap="arrow",
                    content="weiter",
                )
            )
        previous = identifier
    clusters = (
        ("cluster_goals", -7000, -1400, "A · Orientierung Ziele", "Was muss sichtbar sein?"),
        ("cluster_terms", -2500, -1400, "A · Begriffe Modelle", "Welche Woerter tragen das Thema?"),
        ("cluster_path", 2000, -1400, "B · Lernweg", "Wie wird daraus ein Ablauf?"),
        (
            "cluster_transfer",
            6500,
            -1400,
            "B · Transfer Anwendung",
            "Wie erklaeren Mitschueler das Thema?",
        ),
        ("cluster_risks", -4750, 2500, "C · Luecken Risiken", "Was fehlt oder stoert?"),
        (
            "cluster_sources",
            2000,
            2500,
            "C · Quellen Material",
            "Welche Grundlage traegt die Karte?",
        ),
    )
    for identifier, x, y, title, subtitle in clusters:
        lines.extend(_cluster(identifier, x=x, y=y, title=title, subtitle=subtitle))
    lines.append(
        doc(
            "goals_doc",
            parent="cluster_goals",
            x=1900,
            y=680,
            markdown=f"# Leitfaden\n\nLeitfrage: {view.guiding_question}\n\nRolle: {view.author_role}",
        )
    )
    lines.append(
        table(
            "goals_zoom_table",
            parent="cluster_goals",
            x=1900,
            y=1650,
            title="Ziele und Sicherung",
            columns=("Nr", "Ziel"),
            rows=_rows(view.goals, "Ziel ergaenzen"),
        )
    )
    lines.append(
        table(
            "terms_zoom_table",
            parent="cluster_terms",
            x=1900,
            y=760,
            title="Begriffe",
            columns=("Begriff", "Aufgabe"),
            rows=term_rows,
        )
    )
    lines.append(
        line(
            "terms_relation",
            "STICKY",
            parent="cluster_terms",
            x=1900,
            y=1840,
            w=720,
            color="light_blue",
            content="<p><b>Zoom-in-Auftrag</b></p><p>Begriffe mit Beispielen verbinden.</p>",
        )
    )
    lines.append(
        table(
            "path_zoom_table",
            parent="cluster_path",
            x=1900,
            y=820,
            title="Lernweg",
            columns=("Phase", "Handlung"),
            rows=step_rows,
        )
    )
    lines.append(
        line(
            "path_output",
            "STICKY",
            parent="cluster_path",
            x=1900,
            y=1900,
            w=760,
            color="light_green",
            content=f"<p><b>Sicherung</b></p><p>{view.check}</p>",
        )
    )
    lines.append(
        doc(
            "transfer_doc",
            parent="cluster_transfer",
            x=1900,
            y=760,
            markdown=f"# Erklaeren und pruefen\n\nArbeitsform: {view.collaboration}\n\nZiel: Andere koennen den Zusammenhang wiedergeben.",
        )
    )
    lines.append(
        line(
            "transfer_peer",
            "STICKY",
            parent="cluster_transfer",
            x=1900,
            y=1780,
            w=720,
            color="yellow",
            content="<p><b>Peer-Test</b></p><p>Eine Person erklaert, eine fragt nach, eine sichert die Luecke.</p>",
        )
    )
    lines.append(
        table(
            "risk_zoom_table",
            parent="cluster_risks",
            x=1900,
            y=720,
            title="Luecken und Risiken",
            columns=("Klasse", "Frage"),
            rows=(
                ("Verstaendnis", "Welche Stelle bleibt unklar?"),
                ("Material", "Welche Quelle fehlt?"),
                ("Darstellung", "Wo droht Stickerchaos?"),
                ("Schutz", view.privacy_note),
            ),
        )
    )
    lines.append(
        line(
            "risk_next",
            "STICKY",
            parent="cluster_risks",
            x=1900,
            y=1960,
            w=780,
            color="light_yellow",
            content="<p><b>Naechster Output</b></p><p>Summary, Lernkarten, Fragen, Probeerklaerung.</p>",
        )
    )
    lines.append(
        table(
            "sources_zoom_table",
            parent="cluster_sources",
            x=1900,
            y=760,
            title="Material und Quellen",
            columns=("Material", "Pruefung"),
            rows=material_rows,
        )
    )
    lines.append(
        doc(
            "sources_doc",
            parent="cluster_sources",
            x=1900,
            y=1840,
            markdown="# Quellenhygiene\n\nNur tatsaechliche Lerninhalte auf das Board. Unsichere oder nicht gelesene Quellen bleiben als Luecke markiert.",
        )
    )
    edges = (
        ("macro_doc", "goals_doc", "orientieren"),
        ("goals_zoom_table", "terms_zoom_table", "begriffe"),
        ("terms_zoom_table", "path_zoom_table", "anwenden"),
        ("path_zoom_table", "transfer_doc", "erklaeren"),
        ("transfer_doc", "risk_zoom_table", "pruefen"),
        ("risk_zoom_table", "sources_zoom_table", "belegen"),
    )
    for index, (source, target, label_text) in enumerate(edges, start=1):
        lines.append(
            line(
                f"zoom_edge_{index}",
                "CONNECTOR",
                **{"from": source, "to": target},
                shape="elbowed",
                end_cap="arrow",
                content=label_text,
            )
        )
    lines.append(
        line(
            "zoom_privacy_footer",
            "SHAPE",
            parent="zoom_root",
            x=8800,
            y=10880,
            w=7200,
            h=120,
            type="round_rectangle",
            fill="#FFFFFF",
            color="#1a1a1a",
            font="open_sans",
            size=20,
            valign="middle",
            content=view.privacy_note,
        )
    )
    return "\n".join(lines) + "\n"
