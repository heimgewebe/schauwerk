# Schauwerk

Schauwerk ist die visuelle Arbeits-, Projektions- und Publikationsschicht des Heimgewebes. Es verbindet verlässliche Quellen mit kollaborativen Werkflächen, laufend prüfbaren Ansichten, Präsentationen und kontrollierten Veröffentlichungen.

> Aus Quellen werden lebende Ansichten.

## Status

**Foundation plus Miro pilot.** Dieses Repository enthält Architektur, Verträge, Register, den direkten Miro-MCP-Zugriff, allowlist-gebundene Snapshots, isolierte Schreibnachweise und einen ersten Learning-View-Renderer.

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

## Miro Live-Status

```bash
schauwerk miro status --live --json
```

`authorized_locally` zeigt nur, ob sichere lokale OAuth-Dateien vorhanden sind. `live.ok` prueft dagegen den echten Miro-MCP-Zugriff. Wenn `live.renewal_required=true` ist, muss `schauwerk miro login` erneuert werden, bevor produktive Miro-Schreibpfade wie `learn apply` laufen.

## Read-only Miro-Inspektion

```bash
schauwerk miro inspect --json
schauwerk miro inspect --query Schauwerk --owned-by-me --limit 20 --max-pages 5 --json
```

Die Inspektion prüft nur die vorhandene Identität und die Struktur der Board-Suche. Sie führt keine Board-Mutation aus und gibt keine Board-Namen, IDs, URLs oder Inhalte aus.

## Deterministischer Board-Snapshot

```bash
schauwerk miro board add sw002-fixture 'https://miro.com/app/board/...'
schauwerk miro board list --json
schauwerk miro snapshot sw002-fixture --json
```

Board-URLs werden lokal in einer Datei mit Modus `0600` persistiert; eine bestehende Alias-Zuordnung wird nur mit `--replace` geändert. Der Snapshot ersetzt Provider-IDs und URLs durch Digests, entfernt volatile Identitäts- und Zeitfelder, erkennt doppelte Referenzen, liest das Board zweimal und schreibt nur bei identischem Inhalts- und Paginationsergebnis über einen symlink-sicheren Zielpfad ein Artefakt. `--no-comments`, `--output`, `--item-limit`, `--comment-limit` und `--max-pages` begrenzen den Leseumfang.

## Learning View

```bash
schauwerk miro learn render demos/education/peer-learning.yml --output /tmp/peer-learning.dsl --json
schauwerk miro learn apply grabowski-demo demos/education/peer-learning.yml --json
```

`render` erzeugt prüfbare Miro-DSL aus einem strukturierten Lernthema. `apply` schreibt dieselbe Ansicht auf ein allowlisted Board und gibt ein redaktiertes Receipt aus.

## Aktueller Umsetzungsschnitt

- SW-000: Architektur und Verträge
- SW-001: direkter Miro-MCP-Client
- SW-002: read-only Miro-Snapshot
- SW-003: isolierter Schreibtest
- SW-004: Registry-Grundgerüst
- SW-007: erster Learning-View-Renderer für Unterrichts-/Peer-Themen

Siehe `docs/roadmap.md`.
