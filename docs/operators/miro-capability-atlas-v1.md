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

Stand 24. Juli 2026 stellt der verbundene Miro MCP 3.2.4 35 Werkzeuge bereit. Gegenüber dem zuvor beobachteten 33-Werkzeug-Katalog sind `preview_resource_poll` und `record_ui_feedback` hinzugekommen. Schauwerk behandelt diese Erweiterungen unterschiedlich:

- `preview_resource_poll` ist als optionale, ergänzende Provider-Vorschau in den Native Executor integriert;
- `record_ui_feedback` bleibt absichtlich außerhalb von Laufzeit- und Plannerwahrheit, weil ein Daumen-Rating UI-Telemetrie und keine fachliche oder operative Quelle ist.

Damit sind 34 von 35 beobachteten Werkzeugen technisch integriert. `unincorporated_observed_tools` enthält ausschließlich `record_ui_feedback`, `intentionally_unincorporated_observed_tools` benennt dieselbe bewusste Grenze und `actionable_unincorporated_observed_tools` ist leer. Die handlungsrelevante Livekatalogabdeckung beträgt damit 100 Prozent; die rohe Abdeckung über alle Werkzeuge liegt darunter, weil UI-Feedback absichtlich nicht als Systemfähigkeit vereinnahmt wird.

Diese **Livekatalogabdeckung** ist keine 100-prozentige Abdeckung der offiziellen Referenz oder der gesamten Miro-Plattform. Der Live-MCP besitzt `image_create`, `image_get_data`, `image_get_upload_url` und `image_get_url`, aber kein `image_delete`.

## Provider-Vorschau als ergänzende Evidenz

Create-Ergebnisse dürfen einen MCP-Resource-Link auf eine kurzlebige Provider-Vorschau liefern. Der Native Executor erkennt ausschließlich streng formatierte `miro-preview://create/...`-Ressourcen und fragt jede angebotene Vorschau höchstens einmal über `preview_resource_poll` ab. Das begrenzt zusätzliche Provideraufrufe und verhindert Warteschleifen im Mutationspfad.

Der Receipt speichert weder die Resource-URI noch Base64-Vorschaudaten. Er enthält ausschließlich Digest, Status und bei einer fertigen PNG- oder SVG-Vorschau MIME-Typ, Bytezahl und SHA-256. Vorschauen über 10 MiB oder ungültige Antworten werden nicht übernommen. Eine ausstehende, fehlgeschlagene oder fehlerhafte Vorschau macht eine ansonsten verifizierte Create-Operation nicht nachträglich zu einer fehlgeschlagenen Mutation.

Diese Evidenz bleibt ausdrücklich **supplemental**: Sie beweist weder den authentifizierten Nachher-Zustand des Boards noch ästhetische Qualität. `visual_acceptance.status` bleibt deshalb `pending_authenticated_provider_capture`, bis eine getrennte authentifizierte Provideraufnahme tatsächlich geprüft wurde.

## Verwalteter Bild-Lebenszyklus

Stand 24. Juli 2026 ist die separate REST-App live mit exakt `boards:read` und `boards:write` autorisiert. Der Capability-Audit prüft diese Autorität nur dann live, wenn ein getrennt gespeichertes REST-Credential vorhanden ist, und projiziert die Lane ausschließlich bei bestätigtem `boards:write` als `cross_surface`. Fehlendes Credential, fehlender Write-Scope oder ein nicht belastbar erreichbarer Tokenkontext bleiben fail-closed.

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
