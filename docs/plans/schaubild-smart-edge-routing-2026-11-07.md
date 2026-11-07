---
id: schauwerk-schaubild-smart-edge-routing-20261107
role: plan
status: proposed
doc_type: plan
title: Schaubild – intelligente Kantenführung und direkte Kantenbearbeitung
summary: Umsetzungsplan für kollisionsfreie, geschwungene, abschaltbare Kantenführung samt lesbaren Labels und direkter Bearbeitung.
---

# Schaubild: intelligente Kantenführung und direkte Bearbeitung

Stand: 2026-11-07 · Produkt: https://commonthing.net/schaubild/  
Status: **Umsetzungsplan, keine Implementierungs- oder Produktivabnahme**.  
Priorität: P0 lesbare Kantenbeschriftungen und sichere Auswahl; P1 smartes Routing, Direktbearbeitung und Live-Parität.  
Primärer Writer/Operator: Grabowski. Schauwerk produziert Renderer und Pakete; Commonthing übernimmt ausschließlich digestgebundene Consumer-Integration durch Grabowski.

## 1. Ziel und Nutzerergebnis

Kanten sollen ohne mühsame Formularsuche per Maus, Stift und Finger auswählbar und bearbeitbar sein. Im **intelligenten Modus** verlaufen sie auf einem möglichst kurzen, gut lesbaren, weich gekrümmten und hindernisfreien Weg um fremde Knoten. Start und Ziel dürfen je nach Geometrie **links, rechts, oben oder unten** anschließen. Beschriftungen liegen in freien Bereichen, nicht unter oder auf fremden Knoten. Ein sichtbarer Schalter wechselt zwischen **Intelligent** und **Einfach**; manuelle Anschlussseiten bleiben respektiert.

Ziel ist nicht die mathematisch absolut kürzeste Kurve unabhängig von Lesbarkeit: Vorrang haben keine Knoten-/Labelkollision, eindeutige Beziehungen und stabile Linienführung; dann kurze Distanz und wenige sanfte Richtungswechsel. Auch „Einfach“ darf keine unsichtbaren Beschriftungen verursachen.

**Erfolgskriterium:** Ein Nutzer kann eine Verbindung auswählen, beschriften, Anfang und Ziel umhängen, Pfeilrichtung/Typ ändern, intelligente Führung umschalten und rückgängig machen; ein dichter Testgraph bleibt ohne verdeckte Labels und ohne fremde Knoten querende Smart-Kanten lesbar.

## 2. Ist-Zustand und Abgrenzung (Quellprüfung an Schauwerk main 85ff6756, 2026-11-07)

- `src/schauwerk/visual/native_diagram.py`: JSON Canvas nutzt `_canvas_edge_geometry` mit einer kubischen Kurve, automatischem Anschluss aus relativer Lage oder expliziten `from_side`/`to_side` und Lane-Offsets. **Fremde Knoten werden nicht als Hindernisse geprüft**. Kanten einschließlich Label werden vor gewöhnlichen Knoten gezeichnet; diese können Label verdecken.
- `src/schauwerk/resources/native_viewer/assets.py`: `liveEdgeGeometry` führt nach Node-Drag geometrisch nach, aber nicht mit einem allgemein hindernisbewussten Router. Die native Kanten-Strichbreite beträgt 2 px; es fehlt ein separates großes Pointer-Hit-Target. Auswahl, Textdialog, Verbindungserstellung und Anfang-/Ziel-Neuanbindung sind im JSON-Canvas-Dokumentmodus vorhanden, jedoch menülastig.
- `src/schauwerk/resources/standalone_editor/representation_editor.py`: strukturierte Representation-Kanten werden über Zeilen mit ID, Label, Typ, Anfang und Ziel bearbeitet; Representation-History besitzt nicht dieselbe Freigabe wie native JSON-Canvas-History.
- Für `knowledge_map`/Prozessintents existieren spezielle, teilweise dichtekollisionsfreie Router (z. B. PR #225). Diese dürfen nicht durch einen pauschalen Canvas-Router ersetzt werden. Der frühere Mehr-Renderer-Plan bleibt maßgeblich für optionale andere Engines.
- Der Source-Commit und der Commonthing-Release-Lock allein beweisen nicht, dass sämtliche Nutzerwege aktuell produktiv korrekt sind. Dieser Plan führt keinerlei Produktionsänderung aus.

## 3. Fachlicher Vertrag

### 3.1 Routingmodi und Persistenz

- **Intelligent:** obstacle-aware Kurven, intelligente Vier-Seiten-Anschlüsse, reservierte Beschriftungsflächen, Mehrfachkantenabstand und stabile Neuplanung. Für **neue** native Canvas-Dokumente bevorzugter Standard.
- **Einfach:** die bisherige vorhersehbare Kurvenführung beziehungsweise gewähltes manuelles Routing, ohne erzwungene automatische Umwege. Beschriftungslesbarkeit bleibt ein unabhängiges Muss; bei Platzmangel sichtbare Rückmeldung statt stiller Verdeckung.
- Für **bestehende** Dokumente ohne Routing-Konfiguration das bisherige Aussehen zunächst bewahren; intelligente Führung erst nach ausdrücklichem Umschalten beziehungsweise kontrollierter Migration. Keine stille Veränderung exportierter Bestandsdiagramme.
- Pro Diagramm ein klar beschrifteter, zugänglicher Modusschalter in der bestehenden Arbeitsfläche. Pro Kante: `Automatisch` oder manuelle Anschlüsse (`links|rechts|oben|unten`); später bedarfsweise manuelle Wegpunkte. Manuelle Vorgaben übersteuern nur die jeweilige Automatik, nicht die übrigen Sicherheits-/Lesbarkeitsregeln.
- Modus, Seiten und Wegpunkte gehören zu einer **validierten, exportierbaren, revisionsgebundenen Dokument-/Darstellungskonfiguration**. Für JSON Canvas nur kompatible, roundtripfähige Erweiterungen; für strukturierte Representation deren bestehende Modell-/Darstellungsschicht ausdrücklich respektieren. Keine unverifizierte neue Semantik, kein flüchtiger `localStorage` als einzige Autorität. Rendererwechsel darf keine Daten ändern. Genaues Schema erst nach Kompatibilitätsprüfung festlegen.
- Kein dauerhafter zweiter Dienst, kein neues UI-Framework und keine zweite kanonische Graph-Datenbank. SVG-Geometrie ist abgeleitet, nicht die fachliche Quelle.

### 3.2 Kanten, Anker, Labels und Z-Order

- Obstacles: alle **fremden** Knoten-Rechtecke mit angemessenem Abstand, bestehende Label-Rechtecke sowie relevante Grenzen/Ports von Gruppen. Gruppen als Container dürfen interne Beziehungen nicht generell blockieren; von außen nach innen ist ein kontrollierter Grenzübergang nötig.
- Start/Ziel: vier mögliche Seitenpaare und bei Bedarf mehrere Ports pro Seite bewerten. Eigene Start-/Zielknoten dürfen ausschließlich an ausgewählten Ports betreten/verlassen werden. Explizit fixierte Seiten respektieren, bei unlösbarer Lage kein heimlicher Seitenwechsel.
- Labels: tatsächliche Text-/Boxabmessungen bestimmen; bevorzugt auf freiem Abschnitt nahe der Kantenmitte, bei Bedarf seitlich versetzt. Keine Überdeckung durch fremde Knoten oder andere Labels. Linien dürfen nach Möglichkeit nicht unter fremden Labels durchlaufen. Labels nicht allein durch „über allen Knoten malen“ als scheinbar gelöst markieren.
- Rendering-Layer: Gruppenhintergründe hinten, Kurven unter regulären Knoten, **Labels als getrennte, darüberliegende, kollisionsgeprüfte Ebene**. Auswahl-Handles und Hit-Target darüber; Druck/SVG/PDF erhalten dieselbe sichtbare Hierarchie.
- Mehrfachverbindungen, Gegenrichtungen und Selbstkanten nutzen getrennte, deterministische Spuren. Richtungen, Pfeilspitzen, Text und Source-IDs bleiben eindeutig.
- Bei objektiv unlösbarer Enge: vorhersagbare begrenzte Fallback-Reihenfolge und explizite UI-/Prüfrückmeldung; niemals behaupten, die Darstellung sei kollisionsfrei, wenn sie es nicht ist.

### 3.3 Direkte UX und Zugänglichkeit

- Unsichtbarer separater Hit-Path mit mindestens ca. 20–24 CSS-px effektiver Zielbreite, unabhängig von Zoom; sichtbare Linienstärke bleibt unberührt. Keine unsichtbare Fläche, die Knoten oder konkurrierende Handles blockiert.
- Auswahl hebt genau eine Kante und beide Endpunkte hervor. Kompakter Inspektor für Label, Beziehungstyp, Pfeilrichtung, Seitenwahl und Routingmodus; schneller Zugriff direkt aus dem Diagramm.
- Neue Verbindung durch Ziehen vom Start zum Ziel mit Vorschau und Port-Snapping; bestehende Enden via Handle umhängen. Pointer-Cancel/Escape rollt ohne Teilmutation zurück; Pan, Zwei-Finger-Zoom und Beobachtungsmodus behalten Vorrang.
- Doppeltippen beziehungsweise gezielte Textaktion öffnet ein bedienbares Eingabefeld. Kanten sind per Tab/Enter/Escape und barrierefreien Benennungen auswählbar, löschen und bearbeiten möglich; ausreichender Fokuskontrast und Touchgrößen.
- Jede **dokumentändernde** Aktion liefert einen konsistenten Undo/Redo-Schritt. Representation-Undo/Redo darf erst mit eigenem getesteten History-Vertrag freigegeben werden. Viewport-/Hover-/Preview-Änderungen erzeugen keine History.

## 4. Routingstrategie, begrenzt und deterministisch

1. **Geometrie/Index:** Knoten-, Gruppen- und Labelrechtecke inkl. Polster normalisieren; nur betroffene Bereiche/Kanten bei Drag neu prüfen. Ein reproduzierbarer Testkorpus und exakt gebundene Eingabe/Optionen werden zuerst definiert.
2. **Ankerkandidaten:** 4×4 Seitenpaare (gegebenenfalls Ports je Seite), feste Seiten reduzieren den Suchraum. Ausgangs-/Eingangsrichtung, Länge, Nähe zu fremden Objekten, Kreuzungen und Stabilität bewerten.
3. **Freie Wege:** einfache Sichtbarkeitsgraphen um gepolsterte Rechteckkanten oder begrenztes A*/Dijkstra; als Kosten Länge plus Strafen für scharfe Knicke, unnötige Kreuzungen, dichte Spuren und Seitenwechsel. Kollisionen sind **harte** Schranken, keine weich übergewichtbaren Kosten. Deterministische Tie-Breaks nach stabiler Edge-ID und Kandidatenordnung.
4. **Kurvenglättung:** kürzesten geeigneten Polygonzug in sanfte kubische Kurven überführen; die komplette geglättete Kurve (nicht nur Stützpunkte) erneut auf Hindernisfreiheit prüfen. Bei Schnitt: Radius verringern, Zwischenpunkte anpassen oder auf sichere, weniger glatte Route zurückfallen.
5. **Labelplatzierung:** zulässige Streckenabschnitte und Freiräume gegen sämtliche Knoten/Labels prüfen; natürliche Mitte bevorzugen, andere Positionen nach Kosten wählen; Label-Reservierungen für spätere Kanten nachvollziehbar planen. Dichtefälle global begrenzt iterativ verbessern, ohne Endlosschleife.
6. **Stabilität und Live-Parität:** bestehende Route bei kleinen Bewegungen bevorzugen (Hysterese), wenn weiter gültig. Serverseitig exportierte Route und Viewer-Vorschau dürfen nicht dauerhaft auseinanderlaufen: gemeinsamer Routing-Plan als abgeleitete Geometrie oder nachgewiesene identische Rechenregeln/Golden-Fixtures. Nach Drag Abschluss mit kanonischem Render-Readback gegenprüfen.
7. **Budgets:** Knotenzahl/Kantenzahl/CPU und Worst-Case-Kandidaten begrenzen, mit frühzeitigem, offen kommuniziertem Fallback. Vor konkreten Millisekundenzielen Referenz-Hardware, dichte Fixtures, Median und p95 messen; kein unerwiesenes Performance-Versprechen.

Externe Algorithmen (ELK, D2/TALA) bleiben optionale Benchmarks gemäß Mehr-Renderer-Plan; kein Integrationszwang. Erst nach messbarem Vorteil und vollständiger Source-/Exporttreue einen anderen Router anbieten.

## 5. Umsetzung in nutzbaren, getrennt testbaren Inkrementen

| Schritt | Inhalt | Nachweis / Abschlussbedingung |
| --- | --- | --- |
| **E0 – Baseline (P0)** | Dichte Canvas-/Knowledge-Map-Fixtures, echte Bounding-Box-Kollisionstests, aktuelle Render-/Drag-/Exportdifferenzen und iPad-Hit-Tests protokollieren | Rote reproduzierbare Fälle für verdeckte Labels, Fremdknotenquerung, falsche Ports, Pointer-Hits; vorhandene Goldens bleiben erhalten |
| **E1 – Auswahl + Labelschutz (P0)** | Breiter Hit-Path, Kanten-Fokus, klare Auswahl; Labels von Kurvenebene trennen, Position geometrisch prüfen statt nur Z-Order erhöhen | Desktop/Touch/Tastatur: Auswahl erreichbar; keine verdeckte Beschriftung in festem Korpus, keine Knoten-Hit-Regression |
| **E2 – Smart-Router (P1)** | Ankerkandidaten, Hindernissuche, glatte kollisionsgeprüfte Kurven und Mehrfachspuren; zunächst JSON Canvas hinter Opt-in | Keine Fremdknotenquerungen; sinnvoll freie Links-/Rechts-/Oben-/Unten-Ports; reproduzierbare SVGs; sichere Fallbacks |
| **E3 – Toggle + Dokumentvertrag (P1)** | UI `Intelligent/Einfach`, validated persisted mode, pro-Kante `Auto/manuell`, Import-/Export-Roundtrip, Legacy-Bestandsschutz | Reload und SVG/Canvas/PDF bewahren gewählten Modus, Quellwerte, Richtungen und IDs; unveränderte Legacy-Eingaben bleiben visuell stabil |
| **E4 – Direktbearbeitung (P1)** | Inspektor, Label-Edit, Port-Handles, Verbindung ziehen/umhängen, Vorschau, Abbrechen, Undo/Redo pro Mutation | E2E: erstellen → umhängen → Label ändern → Richtung ändern → Undo/Redo → speichern → reload; Beobachtungsmodus und Pinch unverändert |
| **E5 – Live-Parität + Representation (P1)** | Gleicher Routervertrag für Live-Drag, finale Render-/Exportgeometrie; strukturierte Intents nur capability-gesteuert übernehmen, ohne Spezialrouten zu verschlechtern | Vollständig gleiche fachliche Kanten nach Drag/Render/Export; bestehende Process/Knowledge-Map-Goldens und History-Boundaries PASS |
| **E6 – Performance + visuelle Abnahme (P1)** | Große/Dichte Fälle messen, Hysterese optimieren, Desktop/iPad Safari und Chromium sowie hell/dunkel/reduced-motion visuell vergleichen | Technische Gate-Checks **und** explizite visuelle Acceptance je exact Source-/Buildrevision |
| **E7 – Auslieferung pro Slice** | Grabowski: isolierte PR, Tests, Merge, OCI-Digest, Commonthing-Release-Lock und regulärer Reconciler | Exakter live Commit/Digest + tatsächliche Schaubild-Nutzerwege öffentlich nachgewiesen; Rollback auf vorheriges Image möglich |

E1 und E2 dürfen getrennt produktiv nutzbar werden. E5 darf nicht stillschweigend die große bestehende Knowledge-Map-Engine ändern. Für E4 ist E3-Persistenz Voraussetzung. Jede Phase erhält einen kleinen PR-Scope mit klarer Regression und eigenständiger Reviewtiefe.

## 6. Testmatrix und harte Akzeptanz

**Geometrische Szenarien:** gerade Verbindung durch einen dritten Knoten; drei versetzte Hindernisse; Knoten oberhalb/unterhalb; diagonal kürzere Seitenwahl; Gruppen mit internen/externalen Kanten; 2–10 parallele und gegenläufige Kanten; Selbstkante; dichte Labels; sehr lange deutsche Bezeichnungen; mehrfache Drag-/Undo-/Redo-Folgen; extremer Zoom und Mobile-Porträt. Gegenprobe: `Intelligent` aus, explizite Seiten, Bestandsdokument ohne Option.

**Automatisiert:** Für jede Smart-Kante alle Pfadsegmente inklusive geglätteter Kurven gegen fremde Knoten-Geometrie prüfen. Für jedes Label vollständige Bounding-Box-Abstände zu Knoten und anderen Labels prüfen (nicht nur Mittelpunkte). Source-IDs, Knotenzahl, Kantenzahl, Richtungen, Typen, Export- und Rundreiseidentität sichern. Determinismus für dieselbe normalisierte Quelle + denselben Modus; gezielte stabilitätsbasierte Drag-Fälle.

**Browser-E2E:** Chromium Desktop und echtes WebKit/iPad-Safari soweit zugänglich: Fingertreffer, zwei Finger, Kontextmenü, Doppeltipp, Port-Reattach, Undo/Redo, Abbruch, Reload, lokale Entwurfsrettung, Vektor-PDF/SVG/Canvas, Fokus, kontrastreiches UI und Beobachtungsmodus. Mock-Tests sind kein Ersatz für echte Geräte-Abnahme.

**Visuell:** Kurven wirken weich ohne Schleifen/Zacken; minimaler sinnvoller Umweg; Beschriftungen ruhen in Weißräumen; keine Pfeilspitzen mitten auf einer Karte; keine überflüssigen Kantenkreuzungen. Technisch kollisionsfrei ist notwendige, nicht hinreichende ästhetische Acceptance. Prüfergebnis an exakte Revision binden.

**Stop-Regel:** Keine Aktivierung bei Datenverlust, abweichenden Editor-/Exportgeometrien, fehlenden Kanten/Labels, unbegrenzter Laufzeit oder nachgewiesenen Regressionen in bestehenden Golden-Intents. Wenn ein extrem dichtes Layout geometrisch nicht lösbar ist, sichtbaren Konfliktzustand und kleine kontrollierte Fallbackoption anbieten; keine falsche Erfolgsmeldung.

## 7. Zuständigkeit, Scope und Verweise

- Schauwerk-Quelle: `src/schauwerk/visual/native_diagram.py`, `src/schauwerk/resources/native_viewer/assets.py`, `src/schauwerk/resources/standalone_editor/representation_editor.py`, später nur zielgerichtet die zugehörigen Tests und Schemata.
- Regressionen: `tests/visual/test_native_diagram.py`, `tests/visual/test_native_canvas_editor.py`, `tests/visual/test_native_history_contract.py`, `tests/visual/test_standalone_editor_product_ui.py` sowie neue fokussierte Geometrie- und Browser-Fixtures.
- Benachbarter Plan: [Schaubild 2.0 – Mehr-Renderer-Roadmap](schaubild-multirenderer-2026-11-05.md). Frühere Native-Spike-Verträge: [Native Diagram Renderer](native-diagram-renderer-spike-v1.md) und [Standalone Editor](standalone-diagram-editor-spike-v1.md).
- Kein Cross-Repo-Write durch Schauwerk selbst. Grabowski integriert ausschließlich getestete, immutable Releases nach eigenständiger Prüfung von Commonthing-Livezustand und Sperren. Großer Adler optional unabhängig read-only; Nixer nur für NixOS.
- Die Planung erzeugt weder neue Bild-Assets noch Fundus-Packages; falls künftig wiederverwendbare dekorative Source-Master entstehen, gilt der Schauwerk-Fundus-Lifecycle.

**Nächster konkreter Arbeitsauftrag:** E0 durchführen, zwei nachgewiesene P0-Probleme als Tests fixieren, danach E1 minimalinvasiv implementieren. E2 als eigenständigen Router-Slice erst auf dieser reproduzierbaren Baseline beginnen.
