# Miro Quality Receipt v1

Status: active

## Zweck

Der Miro Quality Receipt macht Live-Test-Boards lokal prüfbar, ohne weitere Miro-Mutationen auszulösen. Er bewertet einen bereits verifizierten Snapshot und ergänzt den Learning-Live-Test um ein `quality.json`-Artefakt.

## Geprüfte Dimensionen

- Frame-Struktur
- sichtbare Überlappungen
- einfache Lesbarkeitsrisiken
- Connector-Mindestzahl
- DOC/TABLE-Wirkung
- Sticky-Dominanz

## Grenzen

Der Receipt ist eine heuristische lokale Sichtprüfung. Er ersetzt keinen visuellen Menschencheck und keine echte Miro-Rendering-API. Wenn Snapshot-Geometrie fehlt, bleibt die Überlappungsprüfung epistemisch schwach und wird als Finding sichtbar gemacht.

## Datenschutz

Findings enthalten nur Zähler, Prozentwerte und boolesche Hinweise. Item-Texte, Board-URLs und Provider-IDs werden nicht ausgegeben.

## Live-Test-Verhalten

`schauwerk miro learn live-test ...` schreibt nach dem `after.json` zusätzlich:

```text
quality.json
```

Für Learning-Views gelten derzeit diese Erwartungen:

```text
expected_min_connectors = max(0, step_count - 1)
expected_min_docs = 1
expected_min_tables = 2
```

## Operator-Lab

Operator-Lab-Run: vibe-lab: raw-vibes/operator-lab-run-20260701-schauwerk-miro-quality-receipt-v1.md
