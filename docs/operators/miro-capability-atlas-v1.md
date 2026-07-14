---
doc_type: operator-contract
status: active
title: Miro capability atlas v1
---

# Miro capability atlas v1

## Zweck

Schauwerk behandelt Miro nicht als einen einzelnen Renderer. Die Plattform besteht aus drei getrennten Fähigkeitsflächen mit unterschiedlichen Autorisierungs- und Laufzeitgrenzen:

1. **Miro MCP** ist die operative Agentenfläche für Board-Suche, Kontextlesen, Layouts, native Diagramme, Dokumente, Datenbanktabellen, Code-Widgets, Prototypen, Bilder und Kommentare.
2. **Miro REST API** ist eine separate Anwendungsfläche für Board-Lebenszyklus, Freigaben, Mitglieder und administrative Provideroperationen. Ein MCP-OAuth-Token begründet keine REST-Autorität.
3. **Miro Web SDK** ist eine eingebettete interaktive Anwendungsfläche für Viewport, Auswahl, Panels, Modale, Echtzeitereignisse, Aufmerksamkeit, Sitzungen, Storage, Gruppen, History und eigene Board-Werkzeuge.

Der Live-MCP-Katalog ist die operative Wahrheit. Dokumentation ist eine Produktreferenz, aber kein Beleg dafür, dass ein Werkzeug im verbundenen Team, Plan oder Serverrelease verfügbar ist.

## Schauwerk-Vertrag

`schauwerk miro capabilities --json` liest den Live-Katalog und erzeugt `schauwerk-miro-capability-audit.v1`.

Der Bericht:

- gruppiert Werkzeuge nach Produktrolle;
- bewahrt unbekannte neue Providerwerkzeuge als `provider_extensions`;
- meldet verschwundene bekannte Werkzeuge;
- trennt bereits ausgeführte Laufzeitpfade von Werkzeugen, die nur im Darstellungs-Ausführungsplan inkorporiert sind;
- bewertet vollständige Fähigkeitsketten statt einzelner Toolnamen;
- hält nicht verfügbare Lebenszyklen fail-closed.

## Repräsentationsrouter

Jedes Paket mit `miro_native` enthält zusätzlich `miro-execution-plan.json`. Der Plan ergänzt die räumliche Layout-Komposition um semantisch passende native Miro-Lanes:

| Inhalt oder Anforderung | Native Miro-Lane | Verifikation |
| --- | --- | --- |
| bestehendes Board | Identität, Boardauflösung, Context Explore/Get | Ziel und Kontext vor Mutation |
| Architektur, Prozess, Sequenz, Zustand | natives Diagramm | Context Get |
| längere Erklärung | Miro-Dokument | Doc Get |
| Vergleich, Zeitplan, Wissensbaum, Prozessstatus | Datenbanktabelle mit Table-, Timeline-, Tree- oder Kanban-Ansicht | Rows und Layout-Rückgabe |
| Mermaid-Quelle | Code-Widget mit Mermaid-Syntax | Code Widget Get |
| Präsentation oder gemischtes Modell | interaktiver Tablet-Prototyp als optionale Ergänzung | Context Get |
| kollaborative Abnahme | verankerte Kommentare | Comment List |
| gerenderte Ergänzung | privater Bildupload und Image Readback | Image Data/URL |
| räumliche Grundkomposition | Layout DSL | Layout Read und Board Inventory |

Der Plan mutiert selbst kein Board. Die Ausführung erfolgt nur über typisierte, schema- und receipt-gebundene Laufzeitpfade.

## Operative Abdeckung vom 14. Juli 2026

Der verbundene Miro MCP 3.2.4 stellt 33 Werkzeuge bereit. Nach Einführung des Native Executors sind davon 26 Werkzeuge in produktiven Schauwerk-Laufzeitpfaden enthalten:

- Identität und Boardauflösung;
- Board-Inventar und Kontext;
- Layout-Vertrag, Erstellung, Readback und verwaltete Layout-Updates;
- native Diagramme;
- Dokumenterstellung und Readback;
- Tabellenerstellung, Zeilensynchronisierung, Zeilen-Readback und Ansichtswechsel;
- Code-Widget-Erstellung und Readback;
- Kommentarerstellung und Readback;
- Bild-Upload und Bild-Readback.

Damit steigt die operative Abdeckung von 36,4 auf 78,8 Prozent. Die planerische Inkorporation bleibt bei 100 Prozent.

Noch nicht operative, aber eingeplante Werkzeuge sind:

- `doc_update`;
- `table_get_latest_update_history`;
- `code_widget_list_items`;
- `code_widget_update`;
- `code_widget_delete`;
- `prototype_get_upload_url`;
- `prototype_create`.

## Nachgewiesene Providergrenze: Bilder

Der Live-MCP besitzt `image_create`, `image_get_data`, `image_get_upload_url` und `image_get_url`, aber kein `image_delete`.

Ein gezieltes `layout_read` auf ein Bild meldet das Bild als nicht unterstützten Itemtyp und liefert keine löschbare DSL-Zeile. Deshalb darf `layout_update` nicht als generischer Bild-Löschersatz behandelt werden. Atomisches Ersetzen verwalteter Bilder bleibt blockiert, bis Miro eine typisierte Löschfähigkeit bereitstellt oder eine getrennt autorisierte Providerfläche den Lebenszyklus sicher abbildet.

## Grenzen

Der Fähigkeitsatlas begründet nicht:

- eine Mutationsfreigabe;
- die Verfügbarkeit von REST- oder Web-SDK-Zugangsdaten;
- subjektive visuelle Qualität ohne Sichtprüfung;
- erfolgreiche Providerdarstellung ohne Remote-Readback;
- das sichere Löschen eines Itemtyps, der von keiner verbundenen Oberfläche typisiert gelöscht werden kann.