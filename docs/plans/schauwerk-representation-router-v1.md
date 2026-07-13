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

Der Router gibt Scores und menschenlesbare Gründe aus. Er behauptet weder ästhetische Qualität noch fachliche Wahrheit.

## Sicherheits- und Wahrheitsgrenzen

- Mermaid wird als strikte Quelle ohne `click`-Direktiven oder ausführbaren Inhalt erzeugt.
- Die Mermaid-Zielversion ist für reproduzierbare spätere SVG-Erzeugung auf 11.16.0 festgelegt.
- JSON Canvas verwendet das offene 1.0-Kernmodell aus Gruppen, Textknoten und Kanten.
- Ausgabepfade mit Symlinks werden abgelehnt.
- Jeder Artefaktinhalt erhält SHA-256 und Bytezahl.
- Miro-Qualität wird weiterhin lokal als Vertrag geprüft und erst durch einen separaten Live-Readback als Providerkonformität belegt.
- Ein automatischer Vertragsscore ist kein Ästhetikurteil.

## Paketinhalt

Ein Hybridpaket kann enthalten:

- `input.json` – normalisierte semantische Eingabe;
- `route-plan.json` – Auswahl, Scores, Gründe und Profile;
- `diagram.mmd` – Mermaid-Quelle;
- `composition.canvas` – JSON-Canvas-Datei;
- `miro-board.json` – Miro-native Board-Spezifikation;
- `miro-board.dsl` – geprüfte Layoutanweisung;
- `miro-quality.json` – lokaler Miro-Vertragsbeleg;
- `overview.md` – narrative Fassung;
- `nodes.tsv` – tabellarisches Inventar;
- `manifest.json` und `receipt.json` – Digests und Nichtbehauptungen.

## Pilot

`docs/operators/fixtures/operator-ecosystem-representation-v1.json` beschreibt das Operator-Ökosystem als gemischten Inhalt. Erwartet wird ein Hybridpaket mit Mermaid, JSON Canvas, Miro-native, Tabelle und Dokument. Anschließend wird ausschließlich ein neues, isoliertes Miro-Nachweisboard erzeugt; bestehende Boards werden nicht verändert.
