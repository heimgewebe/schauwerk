root FRAME x=0 y=0 w=4600 h=2300 "Lenskit und RepoBrief"
title TEXT parent=root x=2300 y=90 w=4000 size=34 align=center "Lenskit und RepoBrief — Software-Projektion"
architecture FRAME x=-1725 y=350 w=1050 h=1450 "Architektur"
direction FRAME x=-575 y=350 w=1050 h=1450 "Entscheidungen und Roadmap"
delivery FRAME x=575 y=350 w=1050 h=1450 "Arbeit und Tests"
risk FRAME x=1725 y=350 w=1050 h=1450 "Risiken"
purpose DOC parent=architecture x=525 y=190 <<<
# Zweck

Repositories deterministisch, zitierbar und mit klarer Autorität für Menschen und Agenten aufbereiten.
>>>
component_table TABLE parent=architecture x=525 y=600 "Komponenten" <<<
Komponente:text | Verantwortung:text | Status:text
---
Agent Consumption Contract | Definiert Autorität, Lesereihenfolge und Zitierpflichten. | active
Atlas | Erfasst Dateisysteme über explizite Root- und Sicherheitsverträge. | active
RepoBrief | Erzeugt portable Repository-Bundles und Reading Packs. | active
Retrieval und Range Resolution | Löst Suche, Spans und belegbare Textbereiche auf. | active
>>>
decision_table TABLE parent=direction x=525 y=430 "Entscheidungen" <<<
Entscheidung:text | Status:text | Wirkung:text
---
Canonical artifact remains authoritative | accepted | Reading Packs navigieren, ersetzen aber nie den kanonischen Inhalt.
MCP adapter remains read-only | accepted | Agentenzugriff darf keine versteckte Spiegel- oder Schreibschicht erzeugen.
Snapshot creation is explicit | accepted | Frische Daten entstehen nur durch einen sichtbaren Erzeugungsschritt.
>>>
roadmap_table TABLE parent=direction x=525 y=1050 "Roadmap" <<<
Schritt:text | Status:text | Ergebnis:text
---
Broader read-only adapter | next | Mehr Artefaktrollen werden über denselben Integritätsvertrag lesbar.
Retrieval evaluation | active | Recall, Citation Range und Grounding werden messbar verbessert.
MCP snapshot_create | planned | Snapshot-Erzeugung wird explizit und getrennt von Lesezugriffen angeboten.
>>>
work_table TABLE parent=delivery x=525 y=500 "Aktuelle Arbeit" <<<
Arbeit:text | Art:text | Status:text
---
Portable refresh output root | pull-request | merged
Offene Pull Requests | repository-state | none
Test, Lint, Contracts und Merge-Validierung | validation | green
>>>
tests SHAPE parent=delivery x=525 y=1200 w=720 h=230 type=round_rectangle "Tests: 6/6 bestanden · ✓ gesund — required validation workflows green"
risk_table TABLE parent=risk x=425 y=650 "Offene Risiken" <<<
Risiko:text | Schwere:text | Status:text | Gegenmaßnahme:text
---
Metrics Snapshot & Validation ist rot | medium | open | Diagnostischen Workflow getrennt untersuchen; grüne Kernvalidierung nicht überdehnen.
Retrieval-Qualität bleibt messbar begrenzt | high | managed | Eval-Sätze, Citation-Range-Prüfung und Grounding-Verträge weiter ausbauen.
Bundles können veralten | medium | managed | Snapshot-Hash, Frischezustand und explizite Erzeugung gemeinsam prüfen.
>>>
footer TEXT parent=root x=2300 y=2140 w=4000 size=18 align=center "Snapshot 960df10aa9e2c463 · schauwerk-visual-grammar.v1 · Template software-overview-v1 · Quellsystem bleibt maßgeblich · keine Provider-Mutation"
