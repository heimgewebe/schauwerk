---
doc_type: operator-contract
status: active
title: Miro native executor v1
---

# Miro native executor v1

## Zweck

Der Native Executor überführt einen geprüften Schauwerk-Bundleplan in editierbare Miro-Objekte. Er bietet typisierte Providerpfade für:

- räumliche Layout-Bühnen mit Frames und Orientierungstext;
- native Diagramme;
- Miro-Dokumente einschließlich digestgebundener Find-and-replace-Aktualisierung;
- Datenbanktabellen mit Table-, Kanban-, Timeline- oder Tree-Ansicht sowie Update-Historie;
- Code-Widgets einschließlich paginiertem Inventar, Update und kontrollierter Löschung;
- statische HTML-Prototypen über kurzlebige, tokenisierte Uploadslots;
- verankerte Abnahmekommentare.

Er ist kein generischer Rohzugang zum Miro MCP. Jeder erlaubte Operationstyp besitzt ein lokales Schema, eine semantische Prüfung, eine festgelegte Werkzeugfolge und einen typisierten Readback.

## Befehle

Ein Bundle wird ohne Providerkontakt geprüft mit:

```text
schauwerk miro native check BUNDLE.json --json
```

Die Ausführung auf einem allowlisteten Board erfolgt mit:

```text
schauwerk miro native apply BOARD_ALIAS BUNDLE.json --output RECEIPT.json --json
```

Ein unterbrochener Lauf kann aus seinem hash- und boardgebundenen Zwischenbeleg fortgesetzt werden:

```text
schauwerk miro native apply BOARD_ALIAS BUNDLE.json \
  --resume RECEIPT.json --output RECEIPT.json --json
```

## Sicherheits- und Wahrheitsmodell

### Lokaler Vertrag

- Das Bundle muss `schauwerk-miro-native-bundle.v1` erfüllen.
- Zusätzliche Felder sind gesperrt.
- Operationen besitzen eindeutige IDs.
- Ziel-URLs dürfen nur auf dasselbe lokal allowlistete Board zeigen.
- Tabellen prüfen eindeutige Spalten und Zellen sowie typgebundene Werte: Select-Werte müssen existieren, Datumswerte ISO-8601-konform sein, Links absolute HTTP(S)-URLs enthalten und Personenwerte aus Miro-Nutzer-IDs bestehen.
- Kanban-Gruppierungen dürfen nur auf Select-Spalten zeigen.
- Dokumentupdates verlangen den SHA-256 des unmittelbar zuvor gelesenen Inhalts und exakten Alttext.
- Code-Widget-Updates und -Löschungen verlangen explizite `expected_before`-Felder.
- Prototyp-Screens sind relative, symlinkfreie UTF-8-Dateien unterhalb des Bundle-Verzeichnisses, je höchstens 1 MiB und an einen verpflichtenden SHA-256 gebunden. Skripte, Inline-Eventhandler sowie lokale Bild- oder Assetreferenzen ohne typisierte Image-Token-Autorität werden abgewiesen; presignierte Upload-URLs müssen öffentliche HTTPS-Ziele auf dem Standardport ohne eingebettete Zugangsdaten sein.
- Längen, Anzahlen und Koordinaten sind begrenzt.
- Bundle-, Resume- und Ausgabepfade dürfen keine Symlink-Kette enthalten; der Ausgabepfad darf weder Eingaben noch Miro-Zustandsdateien überschreiben.

### Live-Vertrag

Vor der ersten Mutation:

1. wird die verbundene Miro-Identität geprüft;
2. werden das vollständig paginierte Board-Inventar und der semantische Kontext gelesen;
3. wird der aktuelle MCP-Werkzeugkatalog geladen;
4. werden alle benötigten Werkzeuge auf Anwesenheit geprüft.

Vor jedem Werkzeugaufruf werden die Argumente gegen dessen live geliefertes Eingabeschema validiert. Nach dem Aufruf wird die Providerantwort gegen das live gelieferte Ausgabeschema geprüft.

### Readback je Lane

| Lane | Mutation | Readback |
| --- | --- | --- |
| Layout-Bühne | `layout_create` | zuvor `layout_get_dsl`, danach `layout_read` mit Item- und Skip-Zahlen |
| Diagramm | `diagram_create` | zuvor `diagram_get_dsl`, danach `context_get` |
| Dokument | `doc_create` | `doc_get`, normalisierter Inhaltsvergleich |
| Dokumentupdate | `doc_update` | vorher und nachher `doc_get`; Ausgangsdigest, exakter Ersatz und steigende Content-Version |
| Tabelle | `table_create`, optional `table_sync_rows`, `table_update_view` | vollständig paginiertes `table_list_rows`; jede eingereichte Zeile muss zellenweise vorkommen; Layout-Rückgabe |
| Tabellenhistorie | keine Mutation | `table_get_latest_update_history`; konsistente Gesamtzahl und optional exakter letzter Text |
| Code-Widget | `code_widget_create` | `code_widget_get`, exakter Code-, Sprach-, Titel-, Zeilennummern-, Breiten- und Positionsvergleich |
| Code-Widget-Inventar | keine Mutation | vollständig paginiertes `code_widget_list_items`, eindeutige Referenzen und stabiler Gesamtwert |
| Code-Widget-Update | `code_widget_update` | `code_widget_get` vor und nach der Mutation gegen `expected_before` und `set` |
| Code-Widget-Löschung | `code_widget_delete` | Vorab-Get und paginiertes Inventar; danach Zielabwesenheit und exakt um eins verringerter Bestand |
| Prototyp | HTML-PUT und `prototype_create` | SHA-256 jedes Screens, getrenntes Upload-Transportmittel ohne Miro-OAuth und danach `context_get` |
| Kommentar | `comment_create` | vollständig paginiertes `comment_list_comments`, ID- und Inhaltsreconciliation |

Nach Abschluss werden Board-Inventar und Kontext erneut gelesen.

## Checkpoints und Resume

Miro bietet keine globale Transaktion über mehrere Itemtypen. Der Executor behauptet deshalb keine Atomizität.

- Vor jeder Mutation wird ein owner-only Zwischenbeleg mit `pending_operation_id` und `pending_tool` geschrieben.
- Nach erfolgreichem Readback wird die Operation als verifiziertes Präfix gespeichert.
- Ein Resume-Beleg ist an Bundle-Digest, Board-Alias, Board-Referenz und eigene Receipt-Digest gebunden.
- Nur ein lückenloses, verifiziertes Präfix darf übersprungen werden.
- Bereits verifizierte Operationen werden nicht wiederholt.
- Kommentare werden vor einer Wiederholung über alle paginierten Kommentare auf exakt gleichen Inhalt geprüft. So wird ein Providererfolg erkannt, der vor dem lokalen Checkpoint stattgefunden hat.
- Eine unklare, bereits begonnene Nicht-Kommentar-Mutation wird nicht automatisch wiederholt, sondern verlangt manuelle Reconciliation.
- Vor dem Fortsetzen muss das aktuelle Board-Inventar mindestens alle im verifizierten Präfix erwarteten Items enthalten.
- Digest-inkonsistente, boardfremde oder strukturell widersprüchliche Belege werden abgewiesen.
- Eine nicht wartende Board-Sperre verhindert parallele Mutationen desselben Boards; eine zweite Sperre schützt denselben Receipt-Ausgabepfad auch über verschiedene Boards hinweg.

Der Resume-Vertrag beseitigt nicht jede theoretische Duplikatlücke. Für Itemtypen ohne eindeutige, providerseitig suchbare Idempotenzkennung bleibt ein Abbruch zwischen Providererfolg und Readback eine offene Grenze. Der Vor-Mutationscheckpoint macht diese Unsicherheit sichtbar; eine automatische Wiederholung darf dann nur mit typisierter Reconciliation erfolgen.

## Receipt

`schauwerk-miro-native-execution-receipt.v1` enthält:

- Bundle- und Board-Digests;
- verwendete Werkzeuge und digestierte Ein-/Ausgaben;
- verifizierte Operationen und ihre Readback-Belege;
- ursprünglichen und gegebenenfalls erneuten Preflight;
- Postflight-Inventar und Kontext;
- Pending-, Resume- und Teilmutationszustand;
- erwartete Erstellungen, Löschungen, Nettoänderung und beobachtete Board-Item-Differenz;
- für Prototypen nur Screen-Digests und Uploaderfolg, niemals Upload-URL oder Token;
- keine Board-URL und keinen Providerinhalt im Klartext.

Receipts werden atomar mit Dateimodus 0600 geschrieben. Vorhandene Elternverzeichnisse werden dabei nicht umberechtigt.

## Qualitätsprüfung nativer Objekte

Native Miro-Objekte werden nicht wie eine Sammlung einfacher Shapes bewertet:

- ein natives Diagramm trägt seine Beziehungen intern und benötigt keine zusätzlichen dekorativen Board-Connectoren;
- Dokumente, Datenbanktabellen und Providertexte werden nicht für fehlende exportierte Breite oder Höhe bestraft;
- Überlappung wird weiterhin für alle tatsächlich geometrisch beschreibbaren Objekte geprüft;
- explizit geforderte Connector-, Dokument- und Tabellenzahlen bleiben streng.

Diese Anpassung verhindert falsche Warnungen, schwächt aber keine ausdrücklich gesetzte Qualitätsanforderung ab.

## Live-Nachweis vom 14. Juli 2026

Auf einem frischen Board wurden zunächst fünf semantische Operationen ausgeführt:

1. natives Flussdiagramm;
2. Miro-Dokument;
3. Kanban-Datentabelle mit vier Zeilen;
4. Mermaid-Code-Widget;
5. Abnahmekommentar.

Der erste Prozess wurde nach vier verifizierten Operationen durch das 30-Sekunden-Limit beendet. Der Checkpoint blieb gültig. Beim Resume wurde der beim Provider bereits vorhandene Kommentar anhand seines exakten Inhalts erkannt, nicht dupliziert und anschließend zusammen mit dem Gesamtboard verifiziert.

Danach wurde über dieselbe Laufzeit eine Layout-Bühne mit einem Frame und vier Orientierungstexten ergänzt. Der endgültige doppelte Snapshot weist zehn Board-Items und einen Kommentar aus. Ein zusätzlicher Readback der Datentabelle bestätigte alle vier Zeilen samt Text- und Select-Werten.

Der native Qualitätscheck ergibt:

- Score 100 von 100;
- ein Frame;
- ein natives Diagramm;
- ein Dokument;
- eine Tabelle;
- 100 Prozent Geometrieabdeckung der dafür geeigneten Itemtypen;
- keine Überlappung;
- keine Lesbarkeitswarnung;
- keine verbleibenden Befunde.

Der maschinelle Qualitätsbeleg beweist Struktur, Typen, Geometrie und definierte Schwellen. Er beweist keine subjektive ästhetische Qualität ohne Sichtprüfung.

## Live-Nachweis vom 15. Juli 2026

Auf einem isolierten Wegwerfboard wurden die sieben zuvor nur geplanten MCP-Werkzeuge in einem receipt-gebundenen Wartungsbundle ausgeführt:

1. `doc_update` mit Digest-Preflight und steigendem Content-Version-Readback;
2. `table_get_latest_update_history` für eine stabile Row-ID;
3. vollständig gelesenes `code_widget_list_items`;
4. `code_widget_update` mit Vorbedingung und Feldvergleich;
5. `prototype_get_upload_url`, HTML-PUT ohne OAuth und `prototype_create`;
6. `code_widget_delete` mit Vorab-Inventar und nachgewiesener Zielabwesenheit.

Das Bundle enthält sechs semantische Operationen, weil die beiden Prototypwerkzeuge gemeinsam eine Lane bilden. Alle sechs Operationen wurden verifiziert. Der Executor meldet 33 live beobachtete Werkzeuge, eine Erstellung, eine Löschung und eine Nettoänderung von null; das Board-Inventar blieb entsprechend bei vier Items. Ein unabhängiger Snapshot ist wiederholbar und besitzt den Digest `91a141c4ce2728b9716935fc9a7adcb5c1115bb25b50f171a941fbd216200257`.

Der redigierte Beleg liegt unter `docs/operators/evidence/miro-native-maintenance-live-20260715.json`. Er enthält keine Board-URL, Item-ID, Upload-URL, Token oder Providerinhalte.
