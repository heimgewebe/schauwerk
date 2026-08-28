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
- Paketveröffentlichung akzeptiert nur einen sicheren Parent und ein anfangs nicht existentes Ziel. Nach gegebenenfalls notwendiger Parent-Erzeugung werden Parent und Staging per Directory-FD gebunden; jede selbst erzeugte Paketdatei wird mit `O_EXCL` über den gehaltenen Staging-FD geöffnet und ihr eigener Datei-FD bleibt bis zum terminalen Ergebnis gebunden. Die finale Veröffentlichung benötigt unter Linux `renameat2(RENAME_NOREPLACE)` und schlägt ohne diese No-Replace-Fähigkeit fail-closed fehl. Ein erfolgreicher Rückgabewert bindet Parent und Ziel an den letzten kontrollierten Readback nach dem Durability-`fsync`. Dieser Readback verlangt zusätzlich, dass die Menge der Artefaktnamen exakt dem Ownership-Ledger entspricht, jeder Name noch auf den gehaltenen eigenen Datei-Inode zeigt und Bytezahl sowie SHA-256 des über diesen FD gelesenen Inhalts dem beim Schreiben gebundenen Wert entsprechen. Spätere externe Namespace- oder Inhaltsänderungen nach diesem letzten kontrollierten Readback werden nicht ausgeschlossen.
- Jeder Artefaktinhalt erhält SHA-256 und Bytezahl.
- `coverage` misst ausschließlich tatsächlich im jeweiligen Renderer-Artefakt materialisierte Source-IDs. Sie ist kein Beweis für semantische oder visuelle Vollständigkeit.
- Die Miro-native Fläche ist bewusst eine lesbare Auswahl und kein Vollständigkeitsrenderer. Die Evidence-Karte nennt deshalb materialisierte Knoten und Beziehungen explizit als `Miro-Auszug X/Y`.
- Self-Loops, die für einen Miro-Auszug selektiert werden, bleiben als source-gebundene Relation materialisiert, auch wenn sie nicht als normaler Miro-Connector gezeichnet werden. Nicht selektierte Self-Loops werden wie andere im bewusst begrenzten Miro-Auszug ausgelassene Beziehungen nicht materialisiert; die Evidence-Karte weist diese Grenze über die globale materialisierte Relation-Coverage `X/Y` aus.
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

Die Kompilierung erfolgt in einem benachbarten privaten Staging-Verzeichnis, dessen Directory-FD während der gesamten Erzeugung die Schreibautorität trägt. Das Zielverzeichnis muss vor Beginn fehlen und wird erst nach vollständiger erfolgreicher Kompilierung, einer vollständigen Artefaktprüfung und einem atomaren No-Replace-Publish sichtbar. Die Datei-FDs werden deshalb les- und schreibbar mit `O_EXCL` gehalten: Vor der Veröffentlichung, unmittelbar danach und beim finalen Readback werden Namensmenge, Name→Inode-Bindung, Bytezahl und SHA-256 gegen das beim Schreiben aufgezeichnete Ownership-Ledger geprüft. Die Fehlerbereinigung löscht weder Directory- noch Dateinamen. Stattdessen bleiben die Datei-FDs aller von diesem Lauf erfolgreich mit `O_EXCL` erzeugten Artefakte bis zum terminalen Ergebnis offen; bei einem Fehler nach Artefakterzeugung wird bestmöglich ausschließlich über diese exakt gebundenen Inodes auf 0 Bytes gekürzt und synchronisiert. Eine gleichnamig substituierte Fremddatei, unbekannte Einträge oder ein ausgetauschter Directory-Name werden dadurch nicht gelöscht oder überschrieben. Fehler vor der Veröffentlichung können einen privaten `0700`-Staging-Tombstone hinterlassen; dieser belegt nicht den eigentlichen Zielnamen, sodass ein Retry auf dem Ziel möglich bleibt. Fehler nach der atomaren Veröffentlichung können dagegen einen `0700`-Tombstone direkt unter dem Zielnamen mit null Byte großen Compiler-Einträgen hinterlassen. Wegen der No-Replace-Semantik blockiert ein solcher Ziel-Tombstone einen automatischen Same-Path-Retry, bis er separat identitätsgebunden geprüft und bereinigt wurde. Fremde Einträge werden bewusst erhalten. Cleanup- und Descriptor-Close-Fehler dürfen die ursprüngliche Compile- oder Publish-Ursache nicht maskieren.

## Pilot

`docs/operators/fixtures/operator-ecosystem-representation-v1.json` beschreibt das Operator-Ökosystem als gemischten Inhalt. Erwartet wird ein Hybridpaket mit Mermaid, JSON Canvas, Miro-native, Tabelle und Dokument. Anschließend wird ausschließlich ein neues, isoliertes Miro-Nachweisboard erzeugt; bestehende Boards werden nicht verändert.
