---
doc_type: operator-contract
status: active
title: Miro managed image lifecycle v1
---

# Miro managed image lifecycle v1

## Zweck

Der Vertrag ersetzt oder löscht ausschließlich Bilder, die durch eine lokale `schauwerk-miro-managed-image.v1`-Identität als von Schauwerk verwaltet ausgewiesen sind. Er schließt die fehlende MCP-Löschfähigkeit über eine separat autorisierte Miro-REST-Anwendung.

Miro bleibt eine Darstellungsfläche. Die verwaltete Identität und die lokalen Receipts sind Kontroll- und Reconciliation-Zustand, aber kein fachliches Quellsystem.

## Autoritätsgrenzen

Die Laufzeit verwendet zwei strikt getrennte Providerflächen:

| Fläche | Erlaubte Rolle |
| --- | --- |
| Miro MCP | Allowlist-Auflösung, vollständiges Bildinventar, Uploadslot, Bild-Create, Geometrie- und Anwesenheits-Readback |
| Miro REST API | Tokenkontext, exaktes Bild-GET und exaktes Bild-DELETE |

Das MCP-OAuth-Credential wird niemals für REST verwendet. Das REST-Credential liegt standardmäßig unter dem separaten Zustand `miro-rest/access-token` und wird nur aus einer owner-only Quelldatei installiert. Tokenwerte werden nicht über Argumente, Umgebungsvariablen, Statusausgaben oder Receipts transportiert.

Der REST-Doctor muss `boards:write` bestätigen, bevor eine Mutation beginnen darf.

## Verwaltete Identität

Eine Identität enthält ausschließlich:

- Boardalias;
- stabilen Asset-Schlüssel;
- aktuelle Bild-ID;
- Parent-ID;
- SHA-256 des Quellbilds;
- Position `x` und `y`;
- Breite.

Der Boardalias muss exakt mit dem CLI-Alias übereinstimmen und wird ausschließlich über die private Board-Allowlist aufgelöst. Identitätsdateien müssen regulär, owner-only, nicht verlinkt und schema-konform sein.

Schema:

`schemas/miro-managed-image.v1.schema.json`

## Replace-Saga

`managed-image replace` führt keine providerweit atomare Operation aus. Die Reihenfolge ist:

1. REST-Credential und `boards:write` prüfen.
2. Boardalias auflösen und Board-, Asset- und Ausgabelocks erwerben.
3. vollständiges MCP-Bildinventar lesen;
4. altes Bild anhand ID, Parent, Position und Breite exakt prüfen;
5. neues Bild über MCP hochladen und erstellen;
6. neues und altes Bild sowie den Inventarzuwachs exakt zurücklesen;
7. bei fehlerhaftem Neublick ausschließlich das neue Bild kompensierend über REST löschen;
8. nach erfolgreichem Staging das alte Bild über REST löschen;
9. vollständiges MCP-Inventar erneut lesen und alte Abwesenheit, neue Anwesenheit, Geometrie und stabile Anzahl beweisen;
10. neue Identität und Erfolgsreceipt owner-only veröffentlichen.

Mehrdeutige Create-, Delete-, Kompensations- oder Postflight-Ausgänge führen zu `manual_reconciliation_required`. Ein unklarer Delete-Ausgang wird über REST-GET reconciliert: Nur nachgewiesene Abwesenheit gilt als Erfolg.

Schema:

`schemas/miro-managed-image-replace-receipt.v1.schema.json`

## Delete

`managed-image delete` akzeptiert keine freie Board-URL und keine frei eingegebene Item-ID. Ziel ist ausschließlich das Bild aus einer verwalteten Identität. Vor und nach REST-DELETE wird das vollständige MCP-Inventar geprüft. Erfolg verlangt exakt einen entfernten Inventareintrag und die Abwesenheit der verwalteten Bild-ID.

Schema:

`schemas/miro-managed-image-delete-receipt.v1.schema.json`

## CLI

Lokaler REST-Zustand ohne Netzwerkzugriff:

```text
schauwerk miro rest status --json
```

Credential aus einer regulären owner-only Datei installieren:

```text
schauwerk miro rest token-install /geschuetzter/pfad/access-token --json
```

Bewusste Ersetzung eines bestehenden REST-Credentials:

```text
schauwerk miro rest token-install /geschuetzter/pfad/access-token --replace --json
```

Live-Tokenkontext und Mutationsscope prüfen:

```text
schauwerk miro rest doctor --require-write --json
```

Lokale Identität und optionales Ersatzbild prüfen:

```text
schauwerk miro managed-image check BOARDALIAS IDENTITAET.json \
  --image ERSATZ.svg --content-type image/svg+xml --json
```

Receipt-gebunden ersetzen:

```text
schauwerk miro managed-image replace BOARDALIAS IDENTITAET.json ERSATZ.svg \
  --content-type image/svg+xml \
  --title "Verwaltetes Schauwerk-Bild" \
  --receipt-output replace-receipt.json \
  --identity-output neue-identitaet.json \
  --json
```

Exakt verwaltetes Bild löschen:

```text
schauwerk miro managed-image delete BOARDALIAS IDENTITAET.json \
  --receipt-output delete-receipt.json --json
```

## Dateisicherheit

- REST-Zustandsverzeichnis: Modus `0700`;
- REST-Credential, Identität und Receipts: Modus `0600`;
- Symlinks und Hardlinks werden abgewiesen;
- Quellbild, Identität und Credential werden vor und nach dem Öffnen auf Identitätsdrift geprüft;
- Quellbilder sind auf 25 MiB begrenzt;
- erlaubte Medientypen: SVG, PNG, JPEG und WebP;
- Ausgaben sind create-only und dürfen nicht mit Credentials, Allowlist, Katalogen oder Eingaben kollidieren;
- Provider-URLs, Uploadslots, Tokenwerte sowie Nutzer- und Team-IDs erscheinen nicht in Receipts.

## Betriebszustand vom 15. Juli 2026

Der Codepfad und seine lokalen Tests sind implementiert. Der Live-MCP besitzt weiterhin kein `image_delete`. Auf dem Rechner ist noch kein separates REST-Credential eingerichtet. Deshalb sind `rest doctor --require-write`, produktives Replace und produktives Delete bis zur eigenständigen REST-App-Autorisierung fail-closed.

Ein lokaler grüner Test oder ein vorhandenes MCP-Credential begründet keinen Live-REST-Beleg.
