# Schauwerk

Schauwerk ist die visuelle Arbeits-, Projektions- und Publikationsschicht des Heimgewebes. Es verbindet verlässliche Quellen mit kollaborativen Werkflächen, laufend prüfbaren Ansichten, Präsentationen und kontrollierten Veröffentlichungen.

> Aus Quellen werden lebende Ansichten.

## Status

**Product surface complete; integrated, durable and visually governed local v2.** Das Repository enthält die vollständigen lokalen Produktflächen bis SW-013, die providerneutralen Integrations- und Recovery-Verträge bis SW-017, das semantische Visual System v2 in SW-018, den rendererübergreifenden Darstellungsrouter in SW-019, die paketgebundene Miro-Auslieferung in SW-020 und die deterministische visuelle Vorab- und Regressionsprüfung in SW-021.

## Zielbild

```text
Repositories · GitHub · Systemkatalog · Vault · Dokumente
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

## Visual System v2

```bash
schauwerk visual system-v2 --json
schauwerk visual reference-v2 \
  --spec-output /tmp/schauwerk-v2/board-spec.json \
  --dsl-output /tmp/schauwerk-v2/board.dsl \
  --quality-output /tmp/schauwerk-v2/quality.json \
  --json
schauwerk visual review-v2 \
  ~/.local/state/schauwerk/miro/live-tests/visual-v2/live-test-receipt.json \
  review-input.json \
  --output visual-review.json \
  --json
```

Visual System v2 wählt Miro-Objekte nach ihrer Informationsfunktion, erzwingt einen vollständigen Lesepfad sowie eine eindeutige Titel-/Kernaussagen-Hierarchie und blockiert überfüllte Frames, dekorative Farbverwendung, Connector-Wirrwarr und Haftnotizen als Ersatz für fertige Fakten. Eine Freigabe benötigt mindestens 90/100 und null Blocker. Der Remote-Readback beweist die Umsetzung des Plans, nicht automatisch seine ästhetische Qualität.

Siehe `docs/visual/schauwerk-visual-system-v2.md`.

## Darstellungsrouter v1

```bash
schauwerk visual route \
  docs/operators/fixtures/operator-ecosystem-representation-v1.json \
  --output-dir /tmp/schauwerk-representation \
  --json
```

Der Router bewertet Darstellungsabsicht und Anforderungen, wählt begründet Mermaid, JSON Canvas, Miro-native, Tabelle, Dokument oder ein Hybridpaket und bindet alle erzeugten Artefakte an dieselbe normalisierte Eingabe. Mermaid liefert eine formale, diffbare Diagrammquelle; `.canvas` eine portable räumliche Komposition; Miro editierbare Präsentationsflächen. Rendererabdeckung und Nichtbehauptungen bleiben im Manifest explizit.

Siehe `docs/plans/schauwerk-representation-router-v1.md`.

## Representation Delivery v1

```bash
schauwerk visual package-check /tmp/schauwerk-representation --json
schauwerk visual deliver operator-ecosystem /tmp/schauwerk-representation --output-dir /tmp/schauwerk-delivery --json
```

`package-check` rekonstruiert alle deterministischen Artefakte und führt keinen Providerkontakt aus. `deliver` friert das geprüfte Native Bundle create-only ein, nutzt den vorhandenen Miro-Native-Executor und bindet Paket, Provider-Readback und Abschlussbeleg. Der Lauf ist sequenziell, nicht providerweit atomisch.

Siehe `docs/operators/representation-delivery-v1.md`.

## Visual Preview & Regression v1

```bash
schauwerk visual preview /tmp/schauwerk-representation \
  --output-dir /tmp/schauwerk-preview --json
schauwerk visual compare \
  /tmp/schauwerk-preview-baseline/preview.json \
  /tmp/schauwerk-preview-candidate/preview.json \
  --output /tmp/schauwerk-visual-regression.json --json
```

`preview` erzeugt ohne Providerkontakt pro Frame ein digestgebundenes SVG sowie einen lokalen HTML-Index und erkennt leere Inhalte, Textüberlauf, Clipping und erwartbare Überlappungen. `compare` meldet semantische Änderungen und blockiert neue visuelle Blocker. Die Vorschau ersetzt weder Miro-Readback noch menschliche Sichtprüfung.

Siehe `docs/operators/visual-preview-regression-v1.md`.

## Learning View

```bash
schauwerk miro learn render demos/education/peer-learning.yml --output /tmp/peer-learning.dsl --json
schauwerk miro learn apply grabowski-demo demos/education/peer-learning.yml --json
```

`render` erzeugt prüfbare Miro-DSL aus einem strukturierten Lernthema. `apply` schreibt dieselbe Ansicht auf ein allowlisted Board und gibt ein redaktiertes Receipt aus.

## Registry und Grabowski-Pilot

```bash
schauwerk registry status --json
schauwerk registry show views grabowski.operator-overview --json
schauwerk pilot grabowski \
  ../grabowski/docs/generated/operator-context.v1.json \
  --snapshot-output /tmp/grabowski-pilot/snapshot.json \
  --dsl-output /tmp/grabowski-pilot/operator-overview.dsl \
  --json
```

```bash
schauwerk pilot grabowski-operational \
  /tmp/grabowski-pilot/snapshot.json \
  /path/to/operational-observation.json \
  --snapshot-output /tmp/grabowski-operational/snapshot.json \
  --dsl-output /tmp/grabowski-operational/operator-overview.dsl \
  --json
```

Die Registry validiert Quellen, Projekte, Oberflächen, Ansichten, Regionen, Richtlinien und Publikationen samt Querverweisen. Der Grabowski-Pilot erzeugt deterministische, bereinigte statische und operationale Miro-DSL. Die operationale Ansicht trennt Vertrag, zeitgebundene Beobachtung und Ausfälle; beide Pfade führen keine Provider-Mutation aus.

## Lokales Schaufenster

```bash
schauwerk publish preview declaration.json \
  --source-package /path/to/public-package \
  --output preview.json \
  --json
schauwerk publish release declaration.json preview.json \
  --source-package /path/to/public-package \
  --store-root /path/to/local-store \
  --json
schauwerk publish status stable-slug --store-root /path/to/local-store --json
```

Das Schaufenster übernimmt nur explizit deklarierte öffentliche Quellen und Felder. Versionen sind unveränderlich; stabile Links sind digestgebunden, können ablaufen oder kontrolliert zurückgenommen werden. `serve` bindet ausschließlich an `127.0.0.1` und ist read-only. Dieser Pfad veröffentlicht nichts ins Internet und verändert weder Miro noch das Quellpaket.

Siehe `docs/publications/schaufenster-v1.md`.

## Integrierter und dauerhafter Betrieb

Die Befehle unter `schauwerk durable` arbeiten ausschließlich mit deklarierten lokalen Eingaben. Sie erzeugen normalisierte Quellenbeobachtungen, Review-Vorschläge, lokale Suchindizes, Gesundheitsbelege, Backup-Manifeste sowie gestagte Restore- und Recovery-Belege. Kein Befehl installiert Dienste, liest OAuth-Token oder mutiert Miro.

```bash
schauwerk durable adapter-catalog --json
schauwerk durable profiles --json
```

Siehe `docs/integration/source-adapters-v1.md` und `docs/operations/durable-operations-v1.md`.

## Aktueller Umsetzungsschnitt

- SW-000: Architektur und Verträge
- SW-001: direkter Miro-MCP-Client
- SW-002: read-only Miro-Snapshot
- SW-003: kontrollierter Live-Schreibnachweis abgeschlossen; bereinigte Evidence für Create, Read, Update, Idempotenz und Cleanup liegt vor
- SW-004: vollständige Registry-Verträge, Querverweisprüfung, deterministischer Digest und CLI-Inspektion
- SW-005: statische und operationale Grabowski-Operator-Projektionen mit gebundener Acceptance-Evidence für Vertrag, Hosts, Runtime, laufende Arbeit und bekannte Lücken
- SW-007: Learning-View-Renderer mit Unterrichts-, Peer-, öffentlicher und Offline-Variante
- SW-009: überprüfter Live-Executor mit Postflight, Rollback und Restore
- SW-010: lokale Regie mit getrenntem Review, Entscheidung, Apply und Restore
- SW-011: Registry-gebundene Übersicht und resiliente lokale Live-Ansichten
- SW-012: deterministische HTML-, PDF-, PowerPoint-, Handout- und Offline-Pakete mit getrennten Sprecherhinweisen und Zeitplanung
- SW-013: explizite Publication-Preview, unveränderliche lokale Versionen, digestgebundene stabile Links, Ablauf, Rücknahme und loopbackgebundene Read-only-Auslieferung
- SW-014: lokale, Registry-gebundene Quellenadapter mit sichtbaren Healthy-/Stale-/Partial-/Failed-Zuständen
- SW-015: ausschließlich vorschlagende Wartung für verwaltete Regionen; fremde Regionen und widersprüchliche Quellen werden blockiert
- SW-016: optionale lokale Suche und beleggebundene Hinweise unter strikter Sichtbarkeitsgrenze
- SW-017: lokale Betriebsprofile, Health-, Backup-, gestagte Restore-, OAuth-Rotations- und Kill-Switch-Drill-Verträge
- SW-018: semantisches Visual System v2 mit narrativer Boardarchitektur, zweckgebundener Objektwahl, messbarer Dichte und strengem Qualitätsgate
- SW-019: semantischer Darstellungsrouter mit Mermaid-, JSON-Canvas-, Miro-, Tabellen- und Dokumentausgabe sowie expliziter Rendererabdeckung
- SW-020: paketgebundene Native-Bundle-Auslieferung mit vollständiger Rekonstruktion, eingefrorenem Provider-Payload, Checkpoint, Resume und Abschlussbeleg
- SW-021: deterministische Offline-SVG-Vorschau, Auto-Size-/Überlappungsprüfung und semantischer Baselinevergleich vor Providerkontakt

Siehe `docs/roadmap.md`.
