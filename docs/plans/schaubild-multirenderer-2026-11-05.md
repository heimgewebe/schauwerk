# Schaubild 2.0 – Mehr-Renderer-Roadmap

Stand: 2026-11-05. Produkt: https://commonthing.net/schaubild/
Status: Umsetzungsplan, kein Produktivfreigabebeleg.
Autorität: Schauwerk produziert Renderer/Packages; Commonthing konsumiert einen unveränderlichen Release; Grabowski ist alleiniger Repo-/Produktions-Writer.

## Ziel

Ein Dokument, mehrere Darstellungsmöglichkeiten. Schauwerk Native bleibt als bewährter Standard bestehen. Weitere Renderer werden **parallel** angeboten, sofern sie für klar benannte Diagrammklassen nachweisbar besser sind. Unterschiedliche Layoutverfahren sind ausdrücklich keine zusätzlichen fachlichen Datenmodelle; Editoren sind wiederum von Renderern zu unterscheiden.

Das semantische Modell schauwerk-representation-input.v1 bleibt für kanonische Diagramme maßgeblich. Bei JSON Canvas bleibt das editierbare native Dokument mit seinen Geometrien maßgeblich. Vorhandene Quellen (Mermaid, draw.io/XML, JSON Canvas) sind verlustfrei zu bewahren. Kein automatischer, unbemerkter Rückschreibweg von einer Renderer-Ausgabe in die Quelldaten.

## Ist-Zustand und Grenzen (am Main 6114d1ad geprüft)

- Native SVG über Python: src/schauwerk/visual/native_diagram.py.
- Gemeinsame Eingaben: src/schauwerk/visual/representation.py und native_document.py.
- Native Viewer und Editor: native_viewer.py und standalone_editor.py.
- Native und Legacy-Kompatibilität bereits im Produkt; Undo/Redo, Viewer-Pan/Zoom, PNG/SVG/PDF vorhanden.
- Nachgewiesene Produktgrenze: knowledge_map für kanonische Representation wird im nativen API-Pfad wegen allgemeinem Same-Row-/Parallel-Routing derzeit abgelehnt.
- Native PDF wird gegenwärtig über Browser-Rasterisierung und JPEG-PDF-Kapselung ausgegeben; echte Vektortreue ist ein eigener Folgeauftrag.
- Die bestehende Render-API, Source-IDs, Digests, Undo/Redo und die Commonthing-Release-Promotion bleiben kompatibel.

## Zielarchitektur – so klein wie möglich

Eingabe -> bestehende Validierung -> kanonische Semantik oder editierbares Canvas-Dokument -> wählbare Rendering-Engine -> eigenständige Darstellung -> gemeinsame Host-Interaktionen und Ausgabe.

Jeder tatsächlich integrierte Renderer hat eine stabile ID, Version, unterstützte Intents und Formate, Interaktions-/Bearbeitungsfähigkeit, Layoutoptionen, Exportfähigkeiten und explizite Grenzen. Outputs binden exakten Source-Digest, Engine/Version/Konfiguration sowie Output-Digest. Rendererwechsel selbst ist **keine** semantische Mutation und darf keinen History-Eintrag oder Datenverlust erzeugen.

Kein generisches Plugin-Framework, keine zweiten Datenbanken, kein zweiter permanent laufender Service und kein pauschaler Frontend-Neubau für die erste Phase. Alternative Renderer dürfen zunächst offline und nur zur Evaluierung laufen. Erst nach belegtem Mehrwert wird die kleinste nötige Capability-Abstraktion in der Produkt-API gebaut.

## R01 – Referenzkorpus und reproduzierbare Qualitätsmessung (zuerst)

- Bestehende Golden Fixtures unverändert weiterverwenden: system-landscape-v1, decision-flow-v1, narrative-journey-v1.
- Schwierige Fälle ergänzen: gruppierte knowledge_map, long same-row, parallele Kanten, Selbstbeziehungen, langen deutschen Text, großen Graph, frei positioniertes JSON Canvas.
- Deterministische Eingabe- und Ausgabedigests, Renderzeit, Anzahl Knoten/Kanten/Groups, SVG-Größe und pro Engine explizite Status-/Fehlerangabe sammeln.
- Automatische Verifikationen: keine fehlenden Identitäten, keine stillen Konvertierungsverluste, valides SVG, effektive Laufzeitgrenzen und überprüfbare visuelle Ausgabedateien.
- Metriken allein sind keine visuelle Acceptance. Die Vergleichsbilder an echter Browser-Renderung ansehen.

Erstes Implementierungsartefakt: scripts/schaubild_renderer_benchmark.py mit Tests. Optional fehlende D2-/Graphviz-Binaries müssen ehrlich als unavailable erscheinen, ohne den Native-Baseline-Lauf abzubrechen. Lauf ist read-only gegenüber Repositories und darf keine Produktdateien verändern.

## R02 – Alternativen anhand derselben Eingaben vergleichen

Kandidaten in dieser Reihenfolge:
1. Schauwerk Native als deterministische Baseline.
2. D2/Dagre; zusätzlich D2/ELK und D2/TALA nur wenn installierte Ausgabe/Capabilities tatsächlich vorliegen. D2 ist eine komplette Darstellungsengine.
3. Graphviz dot (hierarchisch); optional fdp/sfdp für geeignete Netze.
4. ELK direkt als Layoutalgorithmus für Schauwerk Native **separat** bewerten, ohne voreiligen Rendererersatz.
5. Mermaid.js für originalgetreue Mermaid-Diagramme nur bei einem nachgewiesenen konkreten Vorteil.
6. Cytoscape.js für interaktive dichte Netze erst bei begründetem Bedarf.

D2/DOT-Prototypen dürfen weder Quelldaten mutieren noch undokumentierte Semantik hinzuerfinden. Gruppierungen, Richtungen, Labels, Knotenarten und stabile Source-IDs müssen lesbar erhalten bleiben. Bei fehlender Coverage ist das Ergebnis nicht produktreif, auch wenn es schöner aussieht. Jede Engine erhält dasselbe Eingabedokument.

Vergleichsdimensionen: Lesbarkeit, Kollisionen, Beziehungstreue, Gruppen, Textgüte, stabile IDs, deterministische Ausgabe, Zeit, Speicher, Zugänglichkeit, Offline-Eignung, Lizenz, Packaging, Pflegeaufwand. Realistisches visuelles A/B entscheidet, nicht Anzahl verfügbarer Engines.

## R03 – Native Qualität weiter verbessern

Die dokumentierte knowledge_map-Routinggrenze ursächlich beheben. Parallele Linien, Kanten-/Textkollisionen, langes Same-Row-Routing, Feedback, Gruppengrenzen und Layoutstabilität gezielt auf Referenzfälle prüfen. Erst nach technischem und visuellem Nachweis Admission für knowledge_map öffnen. Alternativrenderer dürfen diese Funktion vorher anbieten, sofern ihre Coverage bewiesen ist.

Schrift und Texte: gezielte echte Font-/Glyph-Browserfälle, Umbruch, Trunkierung, zugängliche Langtextanzeige. Keine endlose heuristische Sonderfallkette ohne Messbeleg.

## R04/R05 – Dünner Renderer-Adapter und erster produktiver Zweitrenderer

Erst nach R02-Evidenz einen kleinen internen Capability-Vertrag ergänzen und genau einen erfolgreichen Alternativrenderer an die vorhandene Render-API anbinden. Bestehende Native-API und native Editiergrenzen zunächst unverändert lassen. Fallabhängige Auswahl ohne stilles Fallback.

Für jedes Dokument werden nur tatsächlich unterstützte Renderer angezeigt. Native bleibt Standard; Nutzer kann bevorzugten Renderer explizit wählen. Eine bloß dargestellte Alternative bleibt read-only, sofern kein nachgewiesener Rückschreibvertrag existiert.

## R06 – UI: Auswahl und Vergleich

Im bestehenden Schaubild-Arbeitsraum kompakte Aktion „Darstellung“ mit Renderer-Auswahl. Optionale Side-by-side-Ansicht mit eigenständiger Zoom-/Pan-Möglichkeit und klaren Labels. Keine doppelte Toolleiste. Auswahl/Viewport nach Möglichkeit übernehmen, ohne Semantik zu vermischen. Zusatz-UI nur bei mindestens zwei geeigneten Engine-Varianten.

## R07 – Flüssige Bearbeitung und große Diagramme

Server-Rerender- und Frame-Wechsel-Latenz messen. Bestehenden Viewer und History erhalten, unnötigen Voll-Neuaufbau vermindern; bei Fehlern den letzten gültigen Zustand erhalten. Fokus auf Knoten, Beziehungshervorhebung, optional Mini-Übersicht und barrierefreie Mobilnavigation. Änderungen immer an autoritativer Quelle, nicht an frei konvertierten SVG-Metadaten.

## R08 – Hochwertige Exporte

Bestehende PNG/SVG/Raster-PDF-Funktionen beibehalten. Vektor-PDF in isoliertem Prototyp prüfen (Text selektierbar, skalierbare Linien, Unicode, gleiche Ansicht und Diagrammfläche). Nur bei echtem Qualitätsgewinn aktivieren, sonst ehrlicher Raster-Rückfall. Ausgabe muss exakt dem gewählten Renderer/Dokument entsprechen.

## R09 – Weitere Renderer nur bei echtem Vorteil

Weitere Engine-Varianten werden als eigene Kandidaten gegen dieselben Akzeptanzkriterien getestet. Kein Zwang, alle Diagramme überall editierbar zu machen. Stabile Datenautorisierung vor Feature-Masse.

## R10 – Release und echte Produktivabnahme

Für jedes produktive Paket: isolierte Grabowski-Lane, gezielte Tests und Risikoreview, Schauwerk-PR/Merge, veröffentlichter getesteter und digestgebundener OCI-Release, Commonthing-Release-Lock-Promotion, regulärer Reconciler und öffentlicher Live-Readback. Browser-E2E auf exaktem produktivem Build: Import, Rendererwahl, Quelle, Bearbeitung, Undo/Redo, Wechsel, SVG/PNG/PDF, lokale Wiederherstellung, Desktop/Mobil. Merge, CI und HTTP 200 allein sind kein Erfolgsbeweis.

## Acceptance und Stop-Regeln

- Für dieselbe autoritative Quelle bleibt der Inhalt semantisch identisch, unabhängig vom Renderer.
- Keine still entfernten Nodes/Edges/Groups, keine neuen ungebundenen IDs, kein stilles Reformatieren der Quelle.
- Jeder Zweitrenderer muss zumindest für eine definierte Diagrammklasse deutlich und visuell besser sein, bevor er in der UI erscheint.
- Ressourcenlimits für fremde CLIs, kontrollierte temporäre Verzeichnisse, kein automatischer Netzwerkzugriff. Extern erzeugte SVGs werden nicht direkt ungeprüft als vertrauenswürdige Einbettungen behandelt.
- Systemintegrität, Rückfallfähigkeit und die existierenden Commonthing-Produktionsgates bleiben erhalten.
- Neue wiederverwendbare grafische Assets gehen über den Schauwerk-Fundus. Temporäre Benchmark-SVGs sind keine freigegebenen Produktionsassets.
- Kein neuer Renderer oder Umbau allein wegen Technikneuheit.

## Reihenfolge und Arbeitsberechtigung

R01 -> R02 -> R04 -> R05 -> R06. R03 und R08 können in disjunkten Lanes parallel folgen, sobald R01 die Baseline geliefert hat. R07 nach Baseline-Messungen. R09 nur durch Nachfrage oder erkennbaren Nutzen. R10 jeweils pro freigegebenem produktiven Slice.

Grabowski ist alleiniger Writer/Operator. Großer Adler liest bei konkretem Befund unabhängig. Keine Cross-Repo-Schreibwirkung durch Schauwerk selbst. Status, Fehler und Ergebnisevidenz sind getrennt darzustellen.

## Dokumentation und Referenzen

- docs/plans/native-diagram-renderer-spike-v1.md
- docs/plans/standalone-diagram-editor-spike-v1.md
- docs/visual/schauwerk-visual-system-v2.md
- https://d2lang.com/tour/man (D2 CLI)
- https://d2lang.com/tour/layouts/ (D2 Layout-Engines)
- https://graphviz.org/docs/outputs/svg/ (Graphviz SVG)
