---
doc_type: operator-contract
status: active
title: Miro Fundus Atelier v1
---

# Miro Fundus Atelier v1

## Zweck

Das Fundus Atelier projiziert exakt digestgebundene Schauwerk-Fundus-Builds auf ein Miro-Board, damit Varianten gemeinsam gesichtet, kommentiert, angeordnet und präsentiert werden können. Es ist ausdrücklich keine zweite Assetverwaltung.

Die Autoritätsrichtung bleibt:

```text
Fundus Asset + Build
        │
        ▼
Miro Fundus Atelier
Review · Vergleich · Präsentation
        │
        └── keine automatische Acceptance
```

Fundus bleibt fachliche Assetautorität. Miro ist eine veränderbare Arbeits- und Reviewfläche.

## Harte Grenze

Eine Atelier-Publikation darf niemals allein durch Miro-Zustand:

- eine visuelle Acceptance erzeugen;
- eine bestehende Acceptance auf einen anderen Build übertragen;
- ein Fundus-Package erzeugen;
- Asset-, Source-, Recipe- oder Build-Digests ändern;
- Miro zum Quellsystem erklären.

Kommentare, Verschieben, Gruppieren oder Präsentieren in Miro verändern daher keinen Fundus-Build.

## Ablauf v1

1. Assetfamilie im Fundus lesen.
2. Jedes deklarierte Asset über den aktuellen Fundus-Recipe reproduzierbar bauen beziehungsweise einen vorhandenen identischen Build verifizieren.
3. Outputbytes unmittelbar vor dem Providerkontakt erneut gegen ihren SHA-256 prüfen.
4. Einen deterministischen Atelier-Plan mit eigenem Digest bilden.
5. Auf einem allowgelisteten Miro-Board einen Überblicksframe und einen Reviewframe je Asset über Canvas Composer erzeugen.
6. Die exakten lokalen Buildoutputs über `image_get_upload_url` und `image_create` in den jeweiligen Frame hochladen.
7. Das vollständige Miro-Bildinventar erneut lesen und für jedes erzeugte Bild Anwesenheit, Parent-Frame und erwartete Breite prüfen.
8. Einen owner-only, sanitisierten Receipt schreiben.

Der Receipt enthält keine Board-URL, Upload-URL oder Image-Tokens.

## Create-only-Semantik

V1 publiziert append-only auf die gewählte Reviewfläche. Es löscht oder überschreibt keine Boardobjekte. Für einen neuen Kundenslice ist deshalb ein frisches Board der bevorzugte Pfad.

Ein Fehler nach einer Provider-Mutation kann sichtbare Teilobjekte auf dem Board hinterlassen. Diese werden nicht automatisch destruktiv entfernt. Ein späterer Reconciliation-/Update-Pfad muss nur konkret gebundene Atelierobjekte anfassen.

## CLI

Plan ohne Miro-Kontakt:

```text
schauwerk miro fundus-atelier plan hall-of-memory.stellar-frame --json
```

Neue Reviewfläche anlegen und publizieren:

```text
schauwerk miro fundus-atelier publish \
  hall-of-memory.stellar-frame \
  hall-of-memory-fundus-atelier-20260814 \
  --create-board \
  --board-name "Hall of Memory – Fundus Atelier" \
  --receipt-output /geschuetzter/pfad/atelier-receipt.json \
  --json
```

Receipt prüfen:

```text
schauwerk miro fundus-atelier check /geschuetzter/pfad/atelier-receipt.json --json
```

## Providerrealität

Der Hall-of-Memory-Live-Pilot vom 14. August 2026 hat zwei Miro-Eigenheiten belegt, die der Renderer berücksichtigt:

- Frame-Hintergründe werden vom Canvas-Provider auf Weiß normalisiert; lesbarer Inhalt darf daher nicht von einer dunklen Frame-Füllung abhängen.
- HTML-artige Tags in `textArea` werden wörtlich gespeichert; der Atelier-Renderer verwendet deshalb dort ausschließlich Plaintext.

Nach der Korrektur bestätigte ein authentifizierter `canvas_read_as_svg`-Readback 35 Items ohne Skips, sechs Frames und fünf Bilder. Alle Variantenbilder blieben im jeweiligen 1000×1700-Frame bei `x=100`, `y=190`, `800×1200`; die Metadaten beginnen erst darunter. Dieser Readback ist strukturelle visuelle Evidenz, aber keine ästhetische Acceptance. Der sanitierte Livebeleg liegt unter `docs/operators/evidence/miro-fundus-atelier-live-20260814.json`.

## Acceptance

Ein im Atelier sichtbarer Status `ENTWURF · NICHT FREIGEGEBEN` bedeutet genau das: Das Asset darf gemeinsam bewertet werden, ist dadurch aber kein Produktionsasset.

Falls ein Build bereits eine belastbare Fundus-Acceptance besitzt, darf die Oberfläche diesen Fundus-Zustand anzeigen. Die Oberfläche erzeugt oder erweitert ihn nicht.

## Nicht-Ziele v1

- kein Miro-zu-Fundus-Auto-Accept;
- kein automatisches Interpretieren von Kommentaren als Freigabe;
- kein freies Editieren von Asset-Mastern in Miro;
- kein Löschen fremder oder ungebundener Boardobjekte;
- kein Cross-Repo-Write in Consumer-Repositories;
- keine ästhetische Freigabe durch technische Readbacks.

## Hall-of-Memory-Pilot

Der erste Pilot verwendet die Familie `hall-of-memory.stellar-frame`. Die fünf vorhandenen Varianten werden als Reviewkandidaten behandelt. Eine Atelier-Publikation ändert ihren Fundus-Acceptance-Status nicht und erzeugt kein Package.
