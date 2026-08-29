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
6. als `.drawio`, PNG oder SVG exportieren können;
7. die Bearbeitung über einen expliziten Vollbildmodus auf nahezu die gesamte verfügbare Viewport-Höhe erweitern können.

## Architekturentscheidung des Spikes

Schauwerk besitzt bereits ein normalisiertes Repräsentationsmodell sowie Mermaid- und JSON-Canvas-Ausgaben. Der Spike ergänzt deshalb **keinen eigenen Renderer und kein zweites Diagrammdatenmodell**.

Die Produktschicht ist eine kleine statische Host-Anwendung. Sie nutzt den dokumentierten diagrams.net-Embed-Vertrag über ein cross-origin `iframe` und `postMessage`:

- Mermaid wird als `descriptor.format = "mermaid"` mit `wrap = true` geladen und dadurch in native editierbare draw.io-Shapes übersetzt;
- JSON Canvas wird clientseitig in ein minimales `mxGraphModel` übersetzt;
- draw.io/XML wird direkt geladen;
- Autosave-/Save-Ereignisse liefern XML an die Host-Anwendung zurück;
- PNG und SVG werden über das dokumentierte Export-Protokoll angefordert; Bildantworten werden im Host auf angefordertes Format, erwarteten `data:`-Medientyp, base64-Form und Größe begrenzt;
- `.drawio` wird aus dem `xml`-Readback eines unterstützten SVG-Exports erzeugt, weil das Embed-Protokoll kein separates `format=xml` kennt; das XML wird auf Größe und draw.io-Wurzeltyp begrenzt;
- `Aufräumen` nutzt den dokumentierten ELK-Layout-Pfad;
- `Vollbild` ist bewusst ein hostseitiger Fokusmodus: Die äußere Schauwerk-Kopfzeile und Host-Aktionsleiste verschwinden bis auf den kleinen Ausstieg, und die Editorfläche nutzt mit `100dvh` den vollständigen Web-Viewport. Der Produktpfad verwendet **nicht** die Browser-Fullscreen-API. Damit bleibt das gewünschte Bearbeitungslayout unabhängig von Fullscreen-Promise-/Event-Reihenfolgen und funktioniert auch dort, wo natives Fullscreen auf iPadOS/Safari oder in eingebetteten Kontexten eingeschränkt ist.
- `← Start` beendet die aktive Editor-Generation vollständig: Pending Load/Export werden verworfen und der iframe-Browsing-Context ersetzt. Fortsetzungsautorität ist der bereits hostseitig validierte und lokal gesicherte XML-Entwurf, nicht ein versteckter alter Editor.

## Sicherheits- und Datenschutzgrenze

Der Host wird lokal ausgeliefert und bindet beim integrierten Server ausschließlich an `127.0.0.1`.

Standardmäßig ist der Editor **nicht vollständig offline**: Die interaktive Engine wird von `https://embed.diagrams.net` geladen. Diagramminhalte werden anschließend über Browser-`postMessage` an dieses cross-origin `iframe` übergeben. Die Host-Seite akzeptiert Nachrichten ausschließlich vom exakt gebundenen Editor-Origin und setzt eine enge Content-Security-Policy.

Self-Hosting des Kernpfads wurde am 25.08.2026 separat mit dem offiziellen `jgraph/drawio`-Image und demselben Embed-Vertrag auf Loopback belegt: `configure → init → load → Bearbeitung → autosave → SVG/XML-Export` funktionierte mit `offline=1&https=0`, während im Browser alle nicht-lokalen HTTP(S)-Ziele blockiert waren. Der Produktpfad kann deshalb denselben Host gegen einen eigenen draw.io-Origin binden; dafür ist kein Fork und kein zweiter Grafikeditor nötig.

Die CLI akzeptiert dazu `--editor-origin`. Der Wert wird vor jeder Bundle-Schreibwirkung fail-closed normalisiert: nur ein exakter `http(s)`-Origin ohne Credentials, Pfad, Query oder Fragment ist erlaubt; unverschlüsseltes HTTP ist ausschließlich für Loopback zulässig. Der Hostname muss in ASCII-Schreibweise vorliegen; internationale Domainnamen müssen daher bereits als Punycode angegeben werden, statt still über eine zweite IDNA-Regelwelt umgeschrieben zu werden. Browser-mehrdeutige numerische Hostformen einschließlich DNS-Namen mit rein numerischem letztem Label, IPv4-mapped IPv6, IPvFuture in Klammern und IPv6-Zonen-IDs werden abgelehnt; normale IPv6-Adressen und Default-Ports werden browsergleich kanonisiert. Ein benutzerdefinierter Origin aktiviert `offline=1`; bei Loopback-HTTP zusätzlich `https=0`. JavaScript-`targetOrigin`, eingehende `event.origin`-Prüfung und Manifest werden aus demselben normalisierten Wert erzeugt. Der integrierte `serve`-Pfad bindet zusätzlich CSP-`frame-src` exakt an diesen Origin. Ein mit `build` erzeugtes statisches Verzeichnis kann HTTP-Sicherheitsheader auf einem späteren Fremdhost nicht selbst erzwingen; der Betreiber dieses Hosts muss eine äquivalente CSP setzen.

Daraus folgt ausdrücklich nicht:

- dass ein beliebig konfigurierter Custom-Origin tatsächlich unter Kontrolle des Operators steht;
- dass das statische Bundle die draw.io-Runtime selbst enthält;
- dass ein Self-Host ohne eigene Runtime-/Netzwerkprüfung vollständig offline oder für vertrauliche Inhalte freigegeben ist;
- dass die aktuelle Engine dauerhaft gesetzt ist.

Der Host behandelt Exportantworten auch vom erlaubten Editor-Origin weiterhin als untrusted: unerwartete Formate, URI-Typen, Kodierungen, XML-Wurzeln und übergroße Antworten werden verworfen. Der Produktpfad bindet sich für Bildexporte bewusst an die aktuell dokumentierte base64-Daten-URI-Form und soll bei einem zukünftigen Providerformatwechsel fail-closed reagieren.

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

Gegen einen eigenen HTTPS-draw.io-Origin bauen oder starten:

```bash
PYTHONPATH=src python -m schauwerk.visual.standalone_editor build \
  --output-dir /tmp/schauwerk-editor \
  --editor-origin https://drawio.example.org

PYTHONPATH=src python -m schauwerk.visual.standalone_editor serve \
  --port 8765 \
  --editor-origin https://drawio.example.org
```

Für einen lokalen Test-Self-Host ist HTTP nur auf Loopback erlaubt, zum Beispiel `--editor-origin http://127.0.0.1:8878`.

## Acceptance für den Spike

Automatisch:

- Bundle entsteht deterministisch nur in einem leeren, symlink-sicheren Ziel;
- Manifest benennt den exakt gerenderten Editor-Origin, die Netzwerkgrenze und Nichtbehauptungen;
- Custom-Origin, JavaScript-`targetOrigin` und beim integrierten `serve` CSP-`frame-src` bleiben identisch gebunden; unsichere Origins scheitern vor Bundle-Schreibwirkung;
- der Vollbildschalter ist explizit und zustandsanzeigend (`aria-pressed`); sein Zustand wird ausschließlich durch den hostseitigen Fokusmodus bestimmt und hängt nicht von der Browser-Fullscreen-API ab;
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
- `Vollbild` entfernt die äußere Schauwerk-Kopfzeile und die Host-Aktionsleiste bis auf einen kleinen Ausstiegsknopf und gibt den vollständigen Web-Viewport an den Editor; erneuter Klick stellt den Normalzustand wieder her;
- der verlässliche Ausstieg ist der sichtbare Host-Knopf; ein `Escape` innerhalb des cross-origin draw.io-Iframes kann vom Host nicht abgefangen werden. Der Modus behauptet ausdrücklich nicht, Browser- oder iPadOS-Systemleisten außerhalb des Web-Viewports auszublenden;
- iPad/Safari bleibt für die tatsächlich erreichbare Viewport-Ausnutzung ein eigener Produkt-Acceptance-Punkt.

## Entscheidungsregel danach

**Draw.io-Hypothese bestätigt**, wenn die stark reduzierte Produktschicht die Zielaufgaben ohne relevante Draw.io-Komplexität exponiert und die Browser-/Exportpfade stabil sind.

**Excalidraw-Bake-off nötig**, wenn die Embed-Oberfläche trotz Reduktion für einfache Schaubildkorrekturen sichtbar zu komplex bleibt oder Self-Hosting/Embed-Vertrag zum strukturellen Produktproblem wird.

**Eigeneditor erst prüfen**, wenn auch eine Excalidraw-Hülle an einer produktkritischen, nicht nur ästhetischen Anforderung scheitert.
