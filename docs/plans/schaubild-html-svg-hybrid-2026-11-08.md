---
id: schauwerk-schaubild-html-svg-hybrid-20261108
role: plan
status: proposed
doc_type: plan
title: Schaubild – optionaler HTML/SVG-Hybridrenderer und interaktiver HTML-Export
summary: Revisionssicherer, messbarer HTML/SVG-Hybrid für Knoten, Kantenlabels und mobile Interaktion; Native bleibt Standard und Datenautorität.
---

# Schaubild: HTML/SVG-Hybrid und eigenständiger HTML-Export

Stand: 2026-11-08 · Produkt: https://commonthing.net/schaubild/  
**Status: Umsetzungsplan, keine Implementierung, visuelle Acceptance oder Produktivfreigabe.**  
Priorität: P1 für nachweisbare Verbesserungen der Bearbeitung und Lesbarkeit; P2 für den eigenständigen HTML-Export.  
Writer/Operator: Grabowski im Repository `heimgewebe/schauwerk`; Commonthing konsumiert nur akzeptierte, immutable Releases.

## 1. Problem, Ziel und Nichtziel

Der vorhandene Native Viewer verwendet bereits **HTML/CSS für Arbeitsfläche und Bedienung, SVG für das eigentliche Diagramm**. „HTML statt SVG“ wäre deshalb keine sinnvolle pauschale Migration. Zu untersuchen ist ein optionaler **DOM/SVG-Hybridmodus**: echte HTML-Elemente für textreiche Knoten und Kantenlabels, weiterhin SVG für geschwungene Verbindungen, Marker und geometrische Pfade.

**Gewünschter Nutzwert:** längere Texte sauber umbrechen, Text besser auswählen/bearbeiten, Tastatur- und Touchinteraktionen vereinfachen, dynamische Knoteninhalte angemessen darstellen; dabei intelligent geroutete Kanten und Labels bei Zoom, Drag, Export und Undo/Redo stabil halten. Für Weitergabe soll später optional eine **eigenständige, offline nutzbare HTML-Ansicht** entstehen.

**Nichtziele:** kein Ersatz der bewährten nativen SVG-Ausgabe; kein allgemeiner Framework-Wechsel oder zweiter Server; keine zweite Diagrammdatenbank, keine HTML-Interpretation als Dokumentautorität, keine neuen Editierfreigaben für `Representation` durch die Hintertür. Die technische Machbarkeit allein rechtfertigt noch keinen produktiven zweiten Modus.

## 2. Anschluss an bestehende Entscheidungen und laufende Arbeiten

- [Mehr-Renderer-Roadmap, 2026-11-05](schaubild-multirenderer-2026-11-05.md): ein autoritatives Dokument, mehrere ausdrücklich wählbare Darstellungen; Native Standard, Capability-Vertrag, keine stillen Quellmutationen, Vergleich vor Produktfreigabe.
- [Smart-Edge-Plan, 2026-11-07](schaubild-smart-edge-routing-2026-11-07.md): kollisionsfreies, umschaltbares Routing, vierseitige Ports, reservierte Labelräume, konstante Hit-Zielbreite, Export-/Viewer-Parität. **HTML übernimmt nicht die Routingverantwortung**.
- Relevante Änderungen aus den Edge-PRs (#231, #233) und den bestehenden History-/PDF-/D2-Arbeiten zuerst auf aktuellem `main` und aktivem Produkt-Release abgleichen. Nichts nachbauen, was dort inzwischen implementiert ist. Der Plan benennt keine dieser Arbeiten als bereits produktiv abgenommen.
- Bestehende native JSON-Canvas-Dokumentautorität und die getrennte, begrenzte Representation-Textbearbeitung behalten ihren Vertrag. `knowledge_map` und spezialisierte Auto-Layouts dürfen nur nach eigener Capability- und Regressionsprüfung übernommen werden.

## 3. Entwurf: ein Modell, zwei Projektionen

```text
Validierte Representation / autoritatives JSON Canvas
                      │
         bestehende IDs, Text, Geometrie,
         Routingmodus, Layout-Overlay, History
                      │
            Geometrie-/Layoutvertrag
                ┌─────┴──────┐
                ▼            ▼
           Native SVG    Hybrid HTML/SVG
                │            │
                └─────┬──────┘
                      ▼
        gemeinsamer Host: Auswahl, Pan/Zoom,
        Undo/Redo, Import/Export, Readback
```

### 3.1 Rendererwahl und fachliche Autorität

- Native SVG bleibt Standard. `hybrid-html-svg` ist ein eigener, zunächst **read-only** angebotener Darstellungsmodus mit ID, Version, unterstützten Dokumentklassen, Limits, Editier- und Exportfähigkeiten. Kein stilles Fallback und keine falschen Capability-Versprechen.
- Rendererwechsel verändert weder Dokumentstruktur noch Knoten-/Kanten-IDs, Text, Gruppen, Portvorgaben oder Routingmodus; er erzeugt keinen Undo-Schritt. Bewusstes Layout-Editing darf nur über bestehende autorisierte Mutations- und History-Pfade erfolgen.
- JSON Canvas: vorhandene Knotengeometrie, Kantenendpunkte und Erweiterungsfelder roundtripfähig halten. Representation: unveränderte semantische Autorität und geltende Editier-/History-Schranken. Unsupported Intent ausdrücklich melden statt „ähnlich“ zu rendern.
- Nicht erneut ein eigenes DOM-Dokumentmodell anlegen: HTML ist eine abgeleitete Projektion derselben validierten Quelle, mit stabilen `data-source-id`-Bindungen für Fokus und Inspektion.

### 3.2 Ebenen, Routing und Labels

1. **Hintergrund/Gruppen:** Gruppe und Dekoration unter allen fachlichen Objekten.
2. **SVG-Kantenebene:** geroutete Pfade, Pfeilspitzen und Kurven **hinter** den Knoten, mit den bestehenden transparenten und zoomkorrigierten Hit-Pfaden.
3. **HTML-Knotenebene:** semantische `div`-/Textinhalte, visuell frei gestaltbar; positioniert über einer gemeinsamen Weltkoordinaten-Transformation.
4. **HTML-Label-Ebene:** frei positionierte, lesbare Beschriftungen, getrennt von der SVG-Kurvenebene; erst **geometrisch kollisionsgeprüft**, dann überlagert. Ein hoher `z-index` allein kaschiert keine verdeckte/überlappende Beschriftung.
5. **Interaktionsebene:** Fokus/Handles/Portvorschau mit zugänglichen Pointer-Zielen; darf die Interaktion mit darunter liegenden Knoten nicht abfangen.

Alle Ebenen müssen dieselbe Transformationsmatrix für Pan, Zoom und Geräte-Pixelverhältnis nutzen. Keine unabhängigen CSS-Zooms mit Koordinatendrift. Kurven prüfen vollständige Bézier-Hüllen gegen Hindernisse; Ports können links, rechts, oben oder unten liegen. Selbstkanten, parallele und gegenläufige Verbindungen sowie Gruppengrenzen bleiben gesonderte Testfälle.

**Textgeometrie:** Browser misst tatsächliche HTML-Knoten- und Labelrechtecke nach Font-Readiness; Änderungen an Inhalt, Breite oder Schrift melden die Messwerte an die vorhandene Geometrie-/Routingberechnung. `ResizeObserver`/inkrementelle Invalidierung nur bei nachgewiesenem Bedarf. Auf Drag zunächst stabilen bekannten Layoutzustand behalten und danach gezielt revalidieren. Browser- und serverseitig exportierte Geometrie müssen anhand gemeinsamer Fixtures/Readbacks nachweislich übereinstimmen; bei unlösbaren Korridoren sichtbar und nachvollziehbar eskalieren.

### 3.3 Bedienung, Mobile und Barrierefreiheit

- Knoten- und Labeltext auswählen/kopieren; Inline-Edit ausschließlich für fachlich erlaubte Textfelder, mit bestehenden Validierungen und **einem** Undo/Redo-Eintrag je bestätigter Änderung.
- Drag auf Knotenkörper nicht mit Textselektion, Formularfeldern oder Touch-Scroll verwechseln. Eindeutige Editiergriffe bzw. Modusgrenzen, Pointer-Cancel/Escape ohne Teilmutation; Zwei-Finger-Pan/Zoom und Beobachtungsmodus erhalten.
- Kanten und Knoten per Tastatur erreichbar, sichtbarer Fokus, korrekte zugängliche Namen/Rollen, kontrollierte Tab-Reihenfolge. Touch-/Stift-Hit-Flächen in realen CSS-Pixeln konstant.
- Bei dynamischen Knotengrößen Layoutentscheidung explizit machen: Knoten dürfen nicht unbemerkt Nachbarn verdecken; Positionen und Kanten werden nachvollziehbar neu berechnet oder Text erhält begrenzten Innen-Scroll/Expansion.
- HTML-Effekte (Shadows, CSS-Karten, variable Schriften) sind optionales Darstellungsprofil und dürfen Lesbarkeit oder Exporttreue nicht aufbrechen.

### 3.4 Exporte und Offline-HTML

- Native SVG, PNG und Vektor-PDF bleiben weiterhin verfügbar und richtig an die Dokumentquelle gebunden. **Kein Screenshot des DOM als Ersatz für Vektor-PDF.** HTML-Text und Kanten müssen für die gewählte Darstellung mit denselben Inhalten und geometrisch akzeptabler Parität exportierbar sein; falls nicht, wird ein Export als „nicht unterstützt“ ausgewiesen.
- Separates Ergebnis `interactive-html`: für **explizit exportierte** Dokumente eine selbständige, offline funktionierende, vorzugsweise einteilige HTML-Datei (oder nachvollziehbares geschlossenes Paket), zunächst **read-only** mit Pan/Zoom, Fokus, Suche, optional Aufklappen von Text. Keine Serverabhängigkeit, externen CDNs, verdeckten Netzwerkaufrufe, fremden Schriftdownloads oder eingebetteten Geheimnisse.
- Export verwendet ausschließlich validierte, bereinigte Nutzdaten: keine Ausführung von Benutzer-HTML, `javascript:`-URLs, Eventhandlern oder aktiven SVG-Fremdinhalten. Skripte und CSP/Datei-URL-Verhalten in Chromium, Firefox und Safari prüfen; Dateigröße und Ressourcengrenzen festlegen. Nur freigegebene Inhalte exportieren; private Metadaten nicht still übertragen.
- HTML-Export ist **keine zurückimportierbare zweite Dokumentautorität**. JSON Canvas bzw. die kanonische Representation bleibt die einzige Quelle. Optional nachweisbare Source-/Renderer-/Output-Digests im Exportmanifest halten.

## 4. Entscheidungskriterien: HTML nur bei echtem Vorteil

**A/B-Vergleich auf demselben validierten Dokument, derselben Engine-Revision und demselben Testgerät:**

| Dimension | Konkreter Nachweis |
| --- | --- |
| Textqualität | Lange deutsche Namen, Absätze, Unicode, Copy/Paste, Umbruch, Knoten-Höhenänderung, keine verdeckten Labels |
| Geometrie | Keine Kanten durch fremde Knoten; Label-Boxen kollisionsfrei; Portwahl plausibel; Drag/Zoom ohne Drift |
| Interaktion | Auswahl, Edit, Abbruch, Undo/Redo, Pointer/Touch/Stift, Fokus/Screenreader; keine Regression |
| Leistung | Startzeit, p50/p95 Drag-Frame-Zeit, Speicher und DOM-Knotenanzahl mit identischem Korpus gegen Native vergleichen |
| Treue | Stabile IDs, Gruppenzuordnung, Richtungen, Kantenanzahl, Reload/Export-Readback ohne semantische Verluste |
| Betriebsaufwand | Kein neuer Service/Framework; reproduzierbares Packaging, Browserkompatibilität und einfache Rückschaltbarkeit |

Mindestens ein repräsentativer Anwendungsfall muss **visuell und im echten Nutzerweg** klar besser sein, ohne eine relevante Regression. Gemessene absolute Grenzwerte erst nach Baseline auf benannter Hardware festlegen; keine erfundene Millisekundengarantie. Bei großen Graphen kann der native SVG-Renderer deutlich effizienter sein: Rendererwahl bleibt dokumentklassenabhängig, nicht global erzwungen.

Testkorpus: Golden Systemlandschaft, Entscheidungsfluss und narrative Reise; Knowledge-Map-Same-Row/Parallel; 100+ Knoten/200+ Kanten und ein größerer Stressfall; lange Labels, RTL/Unicode, Selbstkanten, Gruppen, mehrere Knoten als Hindernisse, sehr kleiner Viewport, hoher Zoom und sehr weit ausgezoomte Ansicht. Erfolg erfordert Screenshots **und** strukturelle Browser-/Dokumentprüfungen, keine alleinige Pixelwertung.

## 5. Umsetzung in kleinen, getrennt akzeptierbaren Schritten

| Schritt | Umsetzung | Abschluss-/Stop-Bedingung |
| --- | --- | --- |
| **H0 – Baseline** | Aktuellen Main-/OCI-/Live-Stand der Renderer, Edge-Router, History und Exporte erfassen. Golden-Fixtures unverändert vergleichen. Engpass bestimmen, bevor Code entsteht. | Dokumentierte Browser- und Performance-Baseline; kein Überschreiben paralleler Arbeit |
| **H1 – Read-only-Prototyp** | Bestehenden Viewer um optionales DOM-Knoten-/Label-Layer ergänzen; SVG-Pfade und kanonische IDs weiterverwenden. Zwei schwierige Dokumente nebeneinander messen. | Gleicher Inhalt und Kantenverlauf, lesbarere Texte/Labels in mindestens einem Fall; bei fehlendem Gewinn **Stop** |
| **H2 – Gemeinsame Geometrie** | Font-/Bounding-Box-Messung, Transformationsparität, inkrementelle Routingaktualisierung, korrekte Hit-Targets und Layering. Keine zweite Routing-Engine. | Drag, Zoom, Hindernisrouting und Label-Position konsistent; keine Kollisionen in definiertem Korpus |
| **H3 – Kontrolliertes Editing** | Erst nach H1/H2 und History-Prüfung Textbearbeitung und gegebenenfalls Knotengrößenänderung für JSON Canvas integrieren. | Import → Edit → Undo → Redo → Reload → Export vollständig gleichwertig; Representation-Schranken gewahrt |
| **H4 – Interaktiver HTML-Export** | Separaten read-only Offline-Export mit begrenzten Assets und ohne Serverkontakt bauen. | Offline auf Desktop/iPad lauffähig; kein aktiver Fremdinhalt, Inhalte/IDs und Navigation geprüft |
| **H5 – UX/Performance/Accessibility** | Reale Desktop-Browser und iPad-Safari/Stift, Screenshots hell/dunkel, Tastatur, Vergrößerung; Benchmarks dichte Graphen. | Explizite visuelle Acceptance auf exakter Revision, definierte Performancebudgets, sonst Native bevorzugen |
| **H6 – Veröffentlichung** | Grabowski: isolierter PR, risikogerechte Checks, Review/Acceptance, akzeptiertes Schauwerk-OCI, Commonthing-Lock-Promotion und E2E-Readback. | Aktiver Quell-Commit und Image-Digest stimmen; produktiver echter Nutzerweg geprüft; Rollback möglich |

H1 ist bewusst nicht von H3 abhängig. H4 ist ein eigener Export-Use-Case und soll nicht als Vorwand für einen aufwendigen interaktiven Editor dienen. Die Renderer-Auswahl in der UI erst sichtbar machen, wenn H1/H2 einen überzeugenden, reproduzierbaren Nutzen und das Capability-Gate nachweisen.

## 6. Regressionen, Grenzen und Abbruchbedingungen

- Native Default, alte Dokumente, Mermaid/draw.io-Kompatibilität, D2/TALA-Read-only und Knowledge-Map-Spezialrouting unverändert; keine implizite Layoutmigration.
- Keine unterschiedlichen fachlichen Daten nach Rendererwechsel, keine doppelten History-Einträge, keine verloren gehenden lokalen Änderungen oder nichtabbrechbaren Drag-Aktionen.
- Kein Export, dessen Text, Pfeile oder Kantenlage substanziell von der sichtbaren freigegebenen Darstellung abweicht. Bis Parität steht, Exportfähigkeit pro Modus ausdrücklich begrenzen.
- Keine unkontrollierte DOM-Menge oder ständige Vollneuberechnung beim Ziehen. Performance anhand Messung reduzieren; bei großen Graphen Native als bewusst sichtbare Alternative.
- Im dichten, geometrisch unlösbaren Fall sichtbaren Konflikt anzeigen, statt `z-index`/Weglassen von Kanten als „gelöst“ auszugeben.
- Keine automatische ästhetische Acceptance; ein technisch fehlerfreier Renderer kann visuell ungeeignet sein.
- Keine neuen wiederverwendbaren Bild-/Ornament-Assets erforderlich. Sollten sie später entstehen, gilt vor Generierung der Image Brief und der vollständige Schauwerk-Fundus-Lifecycle.

## 7. Ownership und nächster Arbeitsauftrag

**Schauwerk** implementiert den Renderer und Exporte; **Commonthing** hält nur Frontdoor, Release-Lock und konsumierende Integration. **Grabowski** allein führt Repo- und Produktionsänderungen aus, in einer konfliktfreien Writer-Lane mit frischer Source-/CI-/Runtime-Prüfung. Großer Adler nur bei tatsächlicher Reviewfrage.

**Nächster Schritt:** H0 auf dem aktuellen `main` plus Produktivdigest durchführen; H1 als **kleinen separaten read-only Spike** mit einem kurzen Architekturdiagramm, zwei vorhandenen Dichte-Fixtures und revisionsgebundenen visuellen A/B-Readbacks umsetzen. Erst nach positivem H1-Befund H2/H3 autorisieren. Dieser Plan führt **keine** Bildgenerierung, Implementierung, Publication oder Produktivmutation aus.
