# Schauwerk Representation Router v1

## Ziel

Schauwerk soll Inhalte nicht länger direkt in eine feste Miro-Schablone pressen. Ein rendererunabhängiges Eingabemodell beschreibt Bedeutung, Beziehungen, Gruppen, Darstellungsabsicht und Anforderungen. Ein Darstellungsrouter wählt daraus begründet ein oder mehrere Zielformate.

## Darstellungsrollen

| Format | Primäre Aufgabe |
| --- | --- |
| Mermaid | formale Graphen, Abläufe, Abhängigkeiten und deterministische Diagrammquelle |
| JSON Canvas | freie räumliche Komposition, Gruppen und portable Infinite-Canvas-Ansicht |
| Miro-native | editierbare Präsentation, Navigation, Kollaboration und hybride Gesamtfläche |
| Tabelle | strukturierter Vergleich, Inventar und prüfbare Kriterien |
| Dokument | längere Erklärung, Kontext und Grenzen |

Kein Format ist die alleinige Wahrheit. Die semantische Eingabe und ihre stabilen Knoten- und Kanten-IDs sind kanonisch.

## Architektur

```text
Quellen und Fachinhalt
        |
schauwerk-representation-input.v1
        |
Darstellungsrouter mit begründeten Scores
        |
Mermaid | JSON Canvas | Miro-native | Tabelle | Dokument
        |
schauwerk-representation-package.v1
```

## Routingregeln

- formale Absichten und viele Beziehungen erhöhen Mermaid;
- freie räumliche Anordnung, Gruppen und große Knotenmengen erhöhen JSON Canvas;
- Präsentation und Kollaboration erhöhen Miro-native;
- Vergleichsabsicht und Entscheidungsinventare erhöhen Tabelle;
- narrative Absicht und längere Erklärungen erhöhen Dokument;
- gemischte Absichten erzeugen bewusst ein Hybridpaket;
- explizit angeforderte Formate bleiben möglich, müssen aber im Plan sichtbar begründet sein.

Der Router gibt Scores und menschenlesbare Gründe aus. Er behauptet weder ästhetische Qualität noch fachliche Wahrheit. Jeder Renderer akzeptiert nur einen Route-Plan, der exakt der deterministisch neu berechneten Routerentscheidung für dieselbe normalisierte Eingabe entspricht; ein bloß selbstkonsistenter, neu gehashter Fremdplan reicht nicht.

## Eingabevertrag

Der Python-Laufzeitvalidator erfüllt den öffentlichen Vertrag aus `schemas/representation-input.v1.schema.json` fail-closed und ergänzt semantische Invarianten wie eindeutige IDs und gültige Referenzen:

- erforderliche Root-Felder müssen vorhanden sein;
- unbekannte Root-, Gruppen-, Knoten-, Kanten- und Requirement-Felder werden abgelehnt statt still verworfen;
- Längenlimits gelten für den unveränderten Eingabestring, bevor Whitespace normalisiert wird;
- Requirements sind echte JSON-Booleans; Strings wie `"false"` werden nicht umgedeutet;
- Kanten benötigen einen expliziten, bekannten Relationstyp und gültige Source-/Target-IDs;
- doppelte `requested_formats` werden nicht still dedupliziert;
- öffentliche Eingaben enthalten keinen `input_digest`; der Digest wird erst nach erfolgreicher Normalisierung abgeleitet und intern separat gebunden.

## Sicherheits- und Wahrheitsgrenzen

- Mermaid wird als strikte Quelle ohne `click`-Direktiven oder ausführbaren Inhalt erzeugt.
- Die Mermaid-Zielversion ist für reproduzierbare spätere SVG-Erzeugung auf 11.16.0 festgelegt.
- Renderer-interne Mermaid-, Canvas- und Miro-IDs liegen in getrennten Namespaces; kanonische Source-IDs werden separat erhalten und können nicht mit dekorativen Objekten oder anderen Objektarten kollidieren.
- JSON Canvas verwendet das offene 1.0-Kernmodell aus Gruppen, Textknoten und Kanten. Kantenanker folgen der tatsächlichen relativen Geometrie; vertikal gestapelte Knoten werden oben/unten verbunden.
- Ausgabepfade mit Symlinks, einschließlich dangling Symlinks, werden abgelehnt.
- Paketveröffentlichung akzeptiert nur einen sicheren Parent und bindet Parent-, Staging- und gegebenenfalls bestehende Zielidentität über den Compile-Vorgang; ein zwischenzeitlich erscheinendes oder ausgetauschtes Ziel führt zum Abbruch.
- Jeder Artefaktinhalt erhält SHA-256 und Bytezahl.
- `coverage` misst ausschließlich tatsächlich im jeweiligen Renderer-Artefakt materialisierte Source-IDs. Sie ist kein Beweis für semantische oder visuelle Vollständigkeit.
- Die Miro-native Fläche ist bewusst eine lesbare Auswahl und kein Vollständigkeitsrenderer. Die Evidence-Karte nennt deshalb materialisierte Knoten und Beziehungen explizit als `Miro-Auszug X/Y`.
- Self-Loops bleiben als source-gebundene Relation materialisiert, auch wenn sie nicht als normaler Miro-Connector gezeichnet werden.
- Homogene fachliche Beziehungstypen werden als visuelles Risiko ausgewiesen, aber niemals durch erfundene Relationstypen „verbessert“ oder als Generatorfehler blockiert.
- Miro-Qualität wird weiterhin lokal als Vertrag geprüft und erst durch einen separaten Live-Readback als Providerkonformität belegt.
- Ein automatischer Vertragsscore ist kein Ästhetikurteil.

## Paketinhalt und Veröffentlichung

Ein Hybridpaket kann enthalten:

- `input.json` – normalisierte, aber weiterhin schemaexakte öffentliche Eingabe ohne abgeleitete Digest-Felder;
- `route-plan.json` – Auswahl, Scores, Gründe, Profile und Bindung an den abgeleiteten Input-Digest;
- `diagram.mmd` – Mermaid-Quelle;
- `composition.canvas` – JSON-Canvas-Datei;
- `miro-board.json` – Miro-native Board-Spezifikation;
- `miro-board.dsl` – geprüfte Layoutanweisung;
- `miro-quality.json` – lokaler Miro-Vertragsbeleg;
- `overview.md` – narrative Fassung;
- `nodes.tsv` – tabellarisches Inventar;
- `manifest.json` und `receipt.json` – Digests und Nichtbehauptungen.

Die Kompilierung erfolgt in einem benachbarten privaten Staging-Verzeichnis. Das Zielverzeichnis wird erst nach vollständiger erfolgreicher Kompilierung und erneuter Identitätsprüfung atomar veröffentlicht. Ein Renderer-, Quality- oder Pfad-Race-Fehler darf daher kein halbfertiges Paket zurücklassen, das einen sicheren Retry blockiert.

## Pilot

`docs/operators/fixtures/operator-ecosystem-representation-v1.json` beschreibt das Operator-Ökosystem als gemischten Inhalt. Erwartet wird ein Hybridpaket mit Mermaid, JSON Canvas, Miro-native, Tabelle und Dokument. Anschließend wird ausschließlich ein neues, isoliertes Miro-Nachweisboard erzeugt; bestehende Boards werden nicht verändert.
