# Visual Preview & Regression v1

Stand: 15. Juli 2026

## Zweck

SW-021 ergänzt zwischen Paketprüfung und Providerkontakt einen deterministischen Offline-Beleg. Schauwerk rendert das paketgebundene Miro-Board als lokale SVG-Vorschau, prüft erwartbare Geometrieprobleme und vergleicht Kandidaten mit einer Baseline.

Der Pfad bleibt providerfrei:

1. `visual route` erzeugt das Darstellungspaket.
2. `visual package-check` rekonstruiert alle deterministischen Artefakte.
3. `visual preview` erzeugt Frame-SVGs, einen HTML-Index und `preview.json`.
4. `visual compare` meldet semantische Änderungen und neue Blocker.
5. `visual deliver` bleibt eine getrennt autorisierte Provideroperation.

## Befehle

```bash
schauwerk visual preview /tmp/schauwerk-representation \
  --output-dir /tmp/schauwerk-preview --json

schauwerk visual compare \
  /tmp/schauwerk-preview-baseline/preview.json \
  /tmp/schauwerk-preview-candidate/preview.json \
  --output /tmp/schauwerk-visual-regression.json --json
```

## Automatische Befunde

Blocker sind leere sichtbare Objekte, geschätzter Textüberlauf, Clipping, geschätzte Objektüberlappungen und fehlende Connector-Endpunkte. Warnungen kennzeichnen Provider-Auto-Sizing und mögliche Connector-Obstruktionen.

Die konservative Auto-Size-Schätzung hat im Operator-Ökosystem einen realen Fehler gefunden: Die Entscheidungstabelle wächst erwartbar von 160 auf 256 Pixel Höhe und überlagerte Prüfgate sowie Kill-Switch. Beide Knoten liegen nun in einer freien zweiten Zeile des Ausgabeframes.

## Integrität

Der owner-only und create-only erzeugte Preview-Ordner wird als exakter Dateisatz geprüft. `preview.json` bindet Paket, Board, Qualität, Frames, Objekte, Issues, HTML-Index und jedes SVG an Digests, SHA-256 und Bytezahlen. Symlinks, Hardlinks, offene Dateimodi, zusätzliche Dateien und manipulierte Artefakte führen zum Abbruch.

`visual compare` berichtet hinzugefügte, entfernte, geänderte und bewegte Objekte sowie neue und behobene Blocker-Fingerprints. Eine Regression liegt vor, wenn neue Blocker entstehen oder die Blockerzahl steigt.

## Wahrheitsgrenzen

Der Beleg behauptet keine pixelidentische Miro-Darstellung, identische Fontmetriken, vollständige Kreuzungserkennung, semantische Richtigkeit beabsichtigter Änderungen, menschliche ästhetische Abnahme oder Providerwirkung. Preview, Provider-Readback und Sichtprüfung bleiben getrennte Evidenzstufen.
