# Representation Delivery v1

Stand: 15. Juli 2026

## Zweck

Der Darstellungsrouter erzeugt ein deterministisches Paket aus einer normalisierten Eingabe. Representation Delivery v1 schließt die bisherige Lücke zwischen diesem Paket und dem vorhandenen Miro-Native-Executor.

Der Pfad bleibt dreistufig:

1. `visual route` erzeugt und signiert das Darstellungs­paket.
2. `visual package-check` rekonstruiert sämtliche deterministischen Artefakte ohne Providerkontakt.
3. `visual deliver` friert das geprüfte Native Bundle create-only ein und übergibt ausschließlich diese Kopie an den vorhandenen Native Executor.

## Befehle

```bash
schauwerk visual route \
  docs/operators/fixtures/operator-ecosystem-representation-v1.json \
  --output-dir /tmp/schauwerk-representation \
  --json

schauwerk visual package-check \
  /tmp/schauwerk-representation \
  --json

schauwerk visual deliver \
  operator-ecosystem \
  /tmp/schauwerk-representation \
  --output-dir /tmp/schauwerk-delivery \
  --json
```

Nach einem unterbrochenen Native-Executor-Lauf kann derselbe, unveränderte Paket- und Ausgabezustand mit `--resume` fortgesetzt werden.

## Paketprüfung

Vor jedem Providerkontakt werden erneut geprüft:

- Manifest- und Receipt-Digests;
- exakte Dateimenge;
- Größe und SHA-256 jedes Artefakts;
- normalisierte Eingabe und Routerentscheidung;
- Mermaid-, JSON-Canvas-, Miro-Board-, DSL-, Qualitäts-, Dokument- und Tabellenartefakte;
- ausführbares Native Bundle;
- Miro-Qualitätsgate von mindestens 90 Punkten ohne Blocker.

Ein Angreifer kann daher nicht nur eine Datei ändern und Manifest sowie Receipt neu berechnen. Die Laufzeit rekonstruiert die erwarteten Artefakte aus der normalisierten Eingabe und vergleicht deren Inhalt semantisch.

## Providergrenze

Das Native Bundle wird vor dem Providerkontakt bytegleich als `native-bundle.json` in den Delivery-Ordner kopiert. Der Provider erhält nur diese eingefrorene Kopie. Änderungen am ursprünglichen Paket nach dem Preflight können den ausgeführten Payload damit nicht mehr beeinflussen.

Ein lokaler Nonblocking-Lock verhindert zwei gleichzeitige Delivery-Läufe auf denselben Ausgabeordner. Der vorhandene Native Executor behält zusätzlich seine Board-, Receipt- und Resume-Sperren.

## Belege

Der Ausgabeordner enthält nach erfolgreichem Abschluss:

- `native-bundle.json`: der tatsächlich ausgeführte Payload;
- `native-execution.json`: Checkpoint und Provider-Readback des Native Executors;
- `delivery-receipt.json`: Bindung von Paket, Plan, Bundle und Native-Receipt.

Scheitert nur die Veröffentlichung des äußeren Delivery-Belegs nach erfolgreicher Provideränderung, wird der Lauf nicht als gewöhnlicher lokaler Fehler behandelt. Die Runtime fordert ausdrücklich eine Reconciliation anhand von `native-execution.json`.

## Wahrheitsgrenzen

Representation Delivery v1 behauptet nicht:

- providerweite Atomizität;
- vollständigen Rollback für alle Miro-Objekttypen;
- ästhetische Qualität ohne menschliche Sichtprüfung;
- Live-Verfügbarkeit oder Schreibberechtigung ohne den vorhandenen Capability- und OAuth-Preflight;
- REST-Autorisierung oder verwalteten Bild-Lebenszyklus.

Die Provideroperationen laufen sequenziell. `globally_atomic` bleibt deshalb immer `false`.
