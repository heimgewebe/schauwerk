---
doc_type: operator-contract
status: active
title: Miro capability atlas v1
---

# Miro capability atlas v1

## Zweck

Schauwerk behandelt Miro nicht als einen einzelnen Renderer. Die Plattform besteht aus drei getrennten Fähigkeitsflächen mit unterschiedlichen Autorisierungs- und Laufzeitgrenzen:

1. **Miro MCP** ist die operative Agentenfläche für Board-Suche, Kontextlesen, Layouts, native Diagramme, Dokumente, Datenbanktabellen, Code-Widgets, Prototypen, Bilder und Kommentare.
2. **Miro REST API** ist eine separate Anwendungsfläche. Schauwerk nutzt sie ausschließlich über eine eigenständig autorisierte Anwendung für typisierte Bildoperationen; ein MCP-OAuth-Token begründet keine REST-Autorität.
3. **Miro Web SDK** ist eine eingebettete interaktive Anwendungsfläche für Viewport, Auswahl, Panels und Echtzeitereignisse.

Der Live-MCP-Katalog ist die operative Wahrheit für MCP. REST- und Web-SDK-Verfügbarkeit werden getrennt geprüft und dürfen nicht aus dem MCP-Katalog abgeleitet werden.

## Drei Evidenzschichten

`schauwerk miro capabilities --json` erzeugt `schauwerk-miro-capability-audit.v1` und trennt:

1. **beobachteter Livekatalog:** tatsächlich vom verbundenen MCP angebotene Werkzeuge;
2. **versionierte offizielle Referenz:** dokumentierte Werkzeuge mit Quellen-URL und Beobachtungsdatum;
3. **Schauwerk-Abdeckung:** produktive Adapter- und Plannerpfade.

Der Bericht enthält unter anderem:

- `reference_missing_live`: dokumentiert, aber im Livekatalog nicht vorhanden;
- `live_not_in_reference`: live vorhanden, aber nicht in der Referenz aufgeführt;
- `reference_not_integrated`: dokumentiert, aber nicht in Schauwerk integriert;
- getrennte Live-/Referenz- und Adapter-/Referenz-Prozentsätze.

Die Referenz ist diagnostisch. Sie begründet keine Providerverfügbarkeit. Am 17. Juli 2026 dokumentiert die offizielle Referenz `comment_reply`, `comment_resolve` und `prototype_read`, während der verbundene 33-Werkzeug-Livekatalog diese Werkzeuge nicht anbietet. Umgekehrt enthält der Livekatalog provider- oder rolloutbedingte Erweiterungen, die nicht aus der Referenz entfernt werden dürfen.

## Schauwerk-Vertrag

Der Audit:

- gruppiert MCP-Werkzeuge nach Produktrolle;
- bewahrt unbekannte Providerwerkzeuge als `provider_extensions`;
- meldet verschwundene bekannte Werkzeuge;
- trennt Laufzeitpfade von Planungsabdeckung;
- hält die MCP-Lane für verwaltete Bilder ohne `image_delete` weiterhin fail-closed;
- weist den kombinierten MCP/REST-Lebenszyklus separat unter `cross_surface_lanes` aus;
- trennt Adapterimplementierung, Credential-Konfiguration und live bestätigte REST-Autorisierung.

## Repräsentationsrouter

Jedes Paket mit `miro_native` enthält zusätzlich `miro-execution-plan.json`. Der Plan ergänzt die räumliche Layout-Komposition um semantisch passende native Miro-Lanes:

| Inhalt oder Anforderung | Native Miro-Lane | Verifikation |
| --- | --- | --- |
| bestehendes Board | Identität, Boardauflösung, Context Explore/Get | Ziel und Kontext vor Mutation |
| Architektur, Prozess, Sequenz, Zustand | natives Diagramm | Context Get |
| längere Erklärung | Miro-Dokument | Doc Get |
| Vergleich, Zeitplan, Wissensbaum, Prozessstatus | Datenbanktabelle | Rows und Layout-Rückgabe |
| Mermaid-Quelle | Code-Widget | Code Widget Get |
| Präsentation oder gemischtes Modell | interaktiver Prototyp | Context Get |
| kollaborative Abnahme | verankerte Kommentare | Comment List |
| gerenderte Ergänzung | privater Bildupload | Image Data/URL |
| räumliche Grundkomposition | Layout DSL | Layout Read und Board Inventory |

Der Plan mutiert selbst kein Board. Die Ausführung erfolgt nur über typisierte, schema- und receipt-gebundene Laufzeitpfade.

## Operative MCP-Abdeckung

Der verbundene Miro MCP 3.2.4 stellt 33 Werkzeuge bereit. Alle beobachteten Werkzeuge besitzen produktive Schauwerk-Laufzeit- oder Plannerpfade; `unincorporated_observed_tools` ist leer.

Diese 100-prozentige **Livekatalogabdeckung** ist keine 100-prozentige Abdeckung der offiziellen Referenz oder der gesamten Miro-Plattform. Der Live-MCP besitzt `image_create`, `image_get_data`, `image_get_upload_url` und `image_get_url`, aber kein `image_delete`.

## Verwalteter Bild-Lebenszyklus

Schauwerk ergänzt die fehlende MCP-Löschfähigkeit durch einen eng begrenzten REST-Adapter:

- Upload, Create und vollständiger Board-Readback bleiben beim MCP;
- REST darf nur das exakte Bild aus einer verwalteten Identität lesen oder löschen;
- das REST-Credential liegt getrennt vom MCP-OAuth-Zustand;
- der REST-Doctor verlangt für Mutation `boards:write`;
- der CLI-Pfad bietet keine freie URL- oder Item-ID-Löschung;
- Boardziel, Item-ID, Parent, Position, Breite und Quelldigest sind receipt-gebunden;
- Inventare werden vollständig paginiert und auf doppelte IDs, Seiten und Cursor geprüft.

Ersetzen ist eine **Create–Verify–Delete-Saga**, keine providerweit atomare Operation. Erst wird das neue Bild erstellt und exakt zurückgelesen. Danach wird das alte Bild gelöscht und seine Abwesenheit erneut über MCP bewiesen. Ein mehrdeutiger Ausgang erzwingt `manual_reconciliation_required`.

Der detaillierte Betriebsvertrag steht in `docs/operators/miro-managed-image-lifecycle-v1.md`.

## Grenzen

Der Fähigkeitsatlas begründet nicht:

- eine Mutationsfreigabe;
- Providerverfügbarkeit aus einer Dokumentationsreferenz;
- die Verfügbarkeit oder Live-Autorisierung eines REST-Credentials;
- eine providerweite atomare Bildersetzung;
- Web-SDK-App-Registrierung, Teaminstallation oder OAuth;
- subjektive visuelle Qualität ohne Sichtprüfung;
- erfolgreiche Providerdarstellung ohne Remote-Readback;
- eine Löschberechtigung für nicht verwaltete oder nicht allowlistgebundene Items.
