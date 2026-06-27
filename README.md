# Schauwerk

Schauwerk ist die visuelle Arbeits-, Projektions- und Publikationsschicht des Heimgewebes. Es verbindet verlässliche Quellen mit kollaborativen Werkflächen, laufend prüfbaren Ansichten, Präsentationen und kontrollierten Veröffentlichungen.

> Aus Quellen werden lebende Ansichten.

## Status

**Planning / foundation.** Dieses Repository enthält zunächst Architektur, Verträge, Register und das technische Grundgerüst. Es führt noch keine produktiven Miro-Mutationen aus.

## Zielbild

```text
Repositories · GitHub · Cabinet · Vault · Dokumente
                         │
                         ▼
                       Fundus
                         │
                         ▼
                  Schauwerk-Kern
         Register · Ansichten · Provenienz
                         │
                         ▼
                       Regie
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
  Miro-Werkflächen   Livebilder       Renderer
        │                │          PDF/PPTX/HTML
        └──────────── Bühne ──────────────┘
                         │
                         ▼
                    Schaufenster
```

## Grundbegriffe

- **Ansicht:** zweckgebundene Darstellung aus definierten Quellen.
- **Projektraum:** zusammengehörige Ansichten eines Projekts.
- **Werkfläche:** frei oder kooperativ bearbeitbare visuelle Fläche.
- **Regie:** Vorschlag, Diff, Freigabe, Apply, Verifikation und Restore.
- **Livebild:** automatisch aktualisierte Zustandsdarstellung.
- **Bühne:** Präsentations- und Unterrichtsfassung.
- **Schaufenster:** bereinigte externe Fassung.
- **Fundus:** Quellen, Medien, Briefings und Vorlagen.
- **Archiv:** Snapshots, Exporte und wiederherstellbare Zustände.

## Architekturprinzipien

1. Quellsysteme bleiben fachlich maßgeblich.
2. Miro ist eine Oberfläche, nicht die einzige Wahrheit.
3. Menschliche, kooperative und automatisch gepflegte Regionen sind getrennt.
4. Jede Mutation folgt `plan → snapshot → apply → verify → receipt`.
5. Öffentliche Fassungen entstehen als eigenständige, bereinigte Artefakte.
6. Der produktive Miro-Zugriff darf nicht von einem Modellkontingent abhängen.
7. Der Grundbetrieb bleibt ohne semantische Zusatzdienste funktionsfähig.

## Einstieg

1. `AGENTS.md`
2. `docs/index.md`
3. `docs/architecture/schauwerk.md`
4. `docs/roadmap.md`

## Entwicklung

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
make validate
```

## Aktueller Umsetzungsschnitt

- SW-000: Architektur und Verträge
- SW-001: direkter Miro-MCP-Client
- SW-002: read-only Miro-Snapshot
- SW-003: isolierter Schreibtest
- SW-004: Registry-Grundgerüst

Siehe `docs/roadmap.md`.
