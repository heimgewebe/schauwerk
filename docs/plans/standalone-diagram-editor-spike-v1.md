# Standalone Diagram Editor Spike v1

Stand: 2026-08-25

## Ziel

Dieser Spike prüft die kleinste produktnahe Lösung für einen einfachen LLM-first-Schaubildeditor, ohne einen zweiten allgemeinen Grafikeditor in Schauwerk zu bauen.

Der Nutzer soll:

1. Mermaid direkt einfügen oder eine `.mmd`-/`.mermaid`-Datei öffnen können;
2. JSON Canvas (`.canvas`) öffnen können;
3. draw.io/XML wieder öffnen können;
4. das Ergebnis visuell in nativen Diagrammobjekten bearbeiten können;
5. lokal einen Entwurf wiederherstellen können;
6. als `.drawio`, PNG oder SVG exportieren können.

## Architekturentscheidung des Spikes

Schauwerk besitzt bereits ein normalisiertes Repräsentationsmodell sowie Mermaid- und JSON-Canvas-Ausgaben. Der Spike ergänzt deshalb **keinen eigenen Renderer und kein zweites Diagrammdatenmodell**.

Die Produktschicht ist eine kleine statische Host-Anwendung. Sie nutzt den dokumentierten diagrams.net-Embed-Vertrag über ein cross-origin `iframe` und `postMessage`:

- Mermaid wird als `descriptor.format = "mermaid"` mit `wrap = true` geladen und dadurch in native editierbare draw.io-Shapes übersetzt;
- JSON Canvas wird clientseitig in ein minimales `mxGraphModel` übersetzt;
- draw.io/XML wird direkt geladen;
- Autosave-/Save-Ereignisse liefern XML an die Host-Anwendung zurück;
- PNG und SVG werden über das dokumentierte Export-Protokoll angefordert; Bildantworten werden im Host auf angefordertes Format, erwarteten `data:`-Medientyp, base64-Form und Größe begrenzt;
- `.drawio` wird aus dem `xml`-Readback eines unterstützten SVG-Exports erzeugt, weil das Embed-Protokoll kein separates `format=xml` kennt; das XML wird auf Größe und draw.io-Wurzeltyp begrenzt;
- `Aufräumen` nutzt den dokumentierten ELK-Layout-Pfad.

## Sicherheits- und Datenschutzgrenze

Der Host wird lokal ausgeliefert und bindet beim integrierten Server ausschließlich an `127.0.0.1`.

Der Spike ist **nicht vollständig offline**: Die interaktive Editor-Engine wird von `https://embed.diagrams.net` geladen. Diagramminhalte werden anschließend über Browser-`postMessage` an dieses cross-origin `iframe` übergeben. Die Host-Seite akzeptiert Nachrichten ausschließlich vom exakt gebundenen Editor-Origin und setzt eine enge Content-Security-Policy.

Daraus folgt ausdrücklich nicht:

- dass der Spike für vertrauliche Inhalte freigegeben ist;
- dass diagrams.net keine netzwerkseitigen Effekte auslöst;
- dass Self-Hosting bereits validiert ist;
- dass die aktuelle Engine dauerhaft gesetzt ist.

Der Host behandelt Exportantworten auch vom erlaubten Editor-Origin weiterhin als untrusted: unerwartete Formate, URI-Typen, Kodierungen, XML-Wurzeln und übergroße Antworten werden verworfen. Der Spike bindet sich für Bildexporte bewusst an die aktuell dokumentierte base64-Daten-URI-Form und soll bei einem zukünftigen Providerformatwechsel fail-closed reagieren.

Ein Produktionsentscheid muss Self-Hosting bzw. einen vollständig lokalen Editor-Bundle gesondert bewerten.

## JSON-Canvas-Import v1

Unterstützt werden die vier JSON-Canvas-1.0-Knotentypen:

- `text` → editierbarer Kasten;
- `link` → editierbarer Kasten mit Link-Metadatum;
- `file` → editierbarer Datei-Platzhalter;
- `group` → visuelle Gruppe/Swimlane.

Kanten behalten Quelle, Ziel, Label, Pfeilende und – soweit angegeben – Anschlussseite. Negative Canvas-Koordinaten werden lediglich gemeinsam in den positiven draw.io-Arbeitsraum verschoben; relative Positionen bleiben erhalten.

Nicht behauptet wird ein verlustfreier `.canvas → draw.io → .canvas`-Roundtrip. `.canvas` ist in diesem Produktpfad Importkompatibilität, nicht kanonische Wahrheit.

## Warum noch kein tiefer draw.io-Fork

Ein Fork würde Upstream-Updates und Browser-/Touch-/Export-/Layout-Komplexität zu eigener Wartungsarbeit machen, bevor belegt ist, dass die konfigurierbare Embed-Oberfläche den Zielnutzer nicht ausreichend vereinfacht.

Der Spike falsifiziert zuerst genau diese Prämisse.

## Start

Aus einem Source-Checkout:

```bash
PYTHONPATH=src python -m schauwerk.visual.standalone_editor serve --port 8765
```

Statisches Bundle erzeugen:

```bash
PYTHONPATH=src python -m schauwerk.visual.standalone_editor build --output-dir /tmp/schauwerk-editor
```

## Acceptance für den Spike

Automatisch:

- Bundle entsteht deterministisch nur in einem leeren, symlink-sicheren Ziel;
- Manifest benennt Netzwerkgrenze und Nichtbehauptungen;
- Mermaid-, JSON-Canvas- und draw.io-Eingänge sind in der Oberfläche vorhanden;
- JSON-Canvas-Konverter wird mit echter JavaScript-Laufzeit geprüft, sofern Node verfügbar ist;
- Repo-`make validate` bleibt grün.

Live im Browser:

- Startseite lädt lokal;
- Mermaid wird ohne manuellen Formatdialog in editierbare Shapes überführt;
- ein JSON-Canvas-Beispiel wird sichtbar und editierbar;
- Autosave liefert XML zurück;
- Projekt-, PNG- und SVG-Export funktionieren;
- `Aufräumen` läuft ohne Hostfehler;
- iPad/Safari bleibt ein eigener Produkt-Acceptance-Punkt, falls der Desktop-Spike besteht.

## Entscheidungsregel danach

**Draw.io-Hypothese bestätigt**, wenn die stark reduzierte Produktschicht die Zielaufgaben ohne relevante Draw.io-Komplexität exponiert und die Browser-/Exportpfade stabil sind.

**Excalidraw-Bake-off nötig**, wenn die Embed-Oberfläche trotz Reduktion für einfache Schaubildkorrekturen sichtbar zu komplex bleibt oder Self-Hosting/Embed-Vertrag zum strukturellen Produktproblem wird.

**Eigeneditor erst prüfen**, wenn auch eine Excalidraw-Hülle an einer produktkritischen, nicht nur ästhetischen Anforderung scheitert.
