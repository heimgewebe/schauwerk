software_cover FRAME x=0 y=0 w=1120 h=630 fill=#F8FAFC "01 · Lenskit und RepoBrief"
software_cover_title TEXT parent=software_cover x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Lenskit und RepoBrief"
software_cover_thesis TEXT parent=software_cover x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Ein quellgebundener Überblick: System, Entscheidungen, Lieferung, Risiken und Belege."
software_purpose SHAPE parent=software_cover x=560 y=390 w=960 h=180 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Repositories deterministisch, zitierbar und mit klarer Autorität für Menschen und Agenten aufbereiten."
software_map FRAME x=1300 y=0 w=1120 h=630 fill=#F8FAFC "02 · Lesekarte"
software_map_title TEXT parent=software_map x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Lesekarte"
software_map_thesis TEXT parent=software_map x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Die Reihenfolge trennt Orientierung, Bewertung und Belege."
software_map_system SHAPE parent=software_map x=170 y=380 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "1<br>System"
software_map_decision SHAPE parent=software_map x=430 y=380 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "2<br>Entscheidungen"
software_map_delivery SHAPE parent=software_map x=690 y=380 w=180 h=120 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "3<br>Lieferung"
software_map_evidence SHAPE parent=software_map x=950 y=380 w=180 h=120 type=round_rectangle fill=#EAF8F0 border_color=#2F855A color=#173B2D font=open_sans size=18 valign=middle "4<br>Belege"
software_map_a CONNECTOR from=software_map_system to=software_map_decision shape=elbowed end_cap=arrow "begründet"
software_map_b CONNECTOR from=software_map_decision to=software_map_delivery shape=elbowed end_cap=arrow "steuert"
software_map_c CONNECTOR from=software_map_delivery to=software_map_evidence shape=elbowed end_cap=arrow "wird geprüft"
software_architecture FRAME x=2600 y=0 w=1120 h=630 fill=#F8FAFC "03 · System und Verantwortung"
software_architecture_title TEXT parent=software_architecture x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "System und Verantwortung"
software_architecture_thesis TEXT parent=software_architecture x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "4 Komponenten werden als lesbare Systembeziehungen verdichtet."
software_architecture_system SHAPE parent=software_architecture x=560 y=370 w=240 h=140 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Systemkern<br>3 von 4 Komponenten sichtbar<br>Snapshot 960df10aa9e2<br>+ 1 weitere im Snapshot"
software_component_1 SHAPE parent=software_architecture x=200 y=350 w=240 h=100 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Agent Consumption Contract<br>Definiert Autorität, Lesereihenfolge und Zitierpflichten.<br>Status: active"
software_architecture_link_1 CONNECTOR from=software_architecture_system to=software_component_1 shape=elbowed end_cap=arrow "verantwortet"
software_component_2 SHAPE parent=software_architecture x=920 y=350 w=240 h=100 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Atlas<br>Erfasst Dateisysteme über explizite Root- und Sicherheitsverträge.<br>Status: active"
software_architecture_link_2 CONNECTOR from=software_architecture_system to=software_component_2 shape=elbowed end_cap=arrow "verantwortet"
software_component_3 SHAPE parent=software_architecture x=560 y=510 w=240 h=100 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "RepoBrief<br>Erzeugt portable Repository-Bundles und Reading Packs.<br>Status: active"
software_architecture_link_3 CONNECTOR from=software_architecture_system to=software_component_3 shape=elbowed end_cap=arrow "verantwortet"
software_decisions FRAME x=3900 y=0 w=1120 h=630 fill=#F8FAFC "04 · Entscheidungen"
software_decisions_title TEXT parent=software_decisions x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Entscheidungen"
software_decisions_thesis TEXT parent=software_decisions x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "3 Entscheidungen erklären, warum die Architektur so aussieht."
software_decision_table TABLE parent=software_decisions x=390 y=410 "Entscheidungsstand" <<<
Entscheidung:text | Status:text | Wirkung:text
---
Canonical artifact remains authoritative | accepted | Reading Packs navigieren, ersetzen aber nie den…
MCP adapter remains read-only | accepted | Agentenzugriff darf keine versteckte Spiegel- o…
Snapshot creation is explicit | accepted | Frische Daten entstehen nur durch einen sichtba…
>>>
software_decision_guard SHAPE parent=software_decisions x=900 y=410 w=280 h=180 type=rhombus fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "Prüffrage<br>Ist die Wirkung jeder Entscheidung sichtbar?"
software_delivery FRAME x=5200 y=0 w=1120 h=630 fill=#F8FAFC "05 · Roadmap und laufende Arbeit"
software_delivery_title TEXT parent=software_delivery x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Roadmap und laufende Arbeit"
software_delivery_thesis TEXT parent=software_delivery x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Die geplante Folge und der aktuelle Arbeitsstand werden in einer gemeinsamen Lesefläche geprüft."
software_roadmap_step_1 SHAPE parent=software_delivery x=300 y=330 w=440 h=60 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "1 · Broader read-only adapter<br>next · Mehr Artefaktrollen werden über denselben Integritätsvertrag lesbar."
software_roadmap_step_2 SHAPE parent=software_delivery x=300 y=430 w=440 h=60 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "2 · Retrieval evaluation<br>active · Recall, Citation Range und Grounding werden messbar verbessert."
software_roadmap_link_1 CONNECTOR from=software_roadmap_step_1 to=software_roadmap_step_2 shape=elbowed end_cap=arrow "danach"
software_roadmap_step_3 SHAPE parent=software_delivery x=300 y=530 w=440 h=60 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "3 · MCP snapshot_create<br>planned · Snapshot-Erzeugung wird explizit und getrennt von Lesezugriffen ang…"
software_roadmap_link_2 CONNECTOR from=software_roadmap_step_2 to=software_roadmap_step_3 shape=elbowed end_cap=arrow "danach"
software_work TABLE parent=software_delivery x=820 y=410 "Aktuelle Arbeit" <<<
Arbeit:text | Art:text | Status:text
---
Portable refresh output root | pull-request | merged
Offene Pull Requests | repository-state | none
Test, Lint, Contracts und Merge-Validierung | validation | green
>>>
software_risk FRAME x=6500 y=0 w=1120 h=630 fill=#F8FAFC "06 · Risiken und Testsignal"
software_risk_title TEXT parent=software_risk x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Risiken und Testsignal"
software_risk_thesis TEXT parent=software_risk x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Einzelne Risiken werden als Handlungsobjekte gezeigt und direkt dem Testsignal gegenübergestellt."
software_risk_1 SHAPE parent=software_risk x=230 y=400 w=300 h=200 type=round_rectangle fill=#FFE8E8 border_color=#C53030 color=#4A1010 font=open_sans size=18 valign=middle "Metrics Snapshot & Validation ist rot<br>medium · open<br>Gegenmaßnahme: Diagnostischen Workflow getrennt untersuchen; grüne Kernvalidierung nicht überdehnen."
software_risk_2 SHAPE parent=software_risk x=550 y=400 w=300 h=200 type=round_rectangle fill=#FFE8E8 border_color=#C53030 color=#4A1010 font=open_sans size=18 valign=middle "Retrieval-Qualität bleibt messbar begrenzt<br>high · managed<br>Gegenmaßnahme: Eval-Sätze, Citation-Range-Prüfung und Grounding-Verträge weiter ausbauen.<br>+ 1 weitere im Snapshot"
software_tests SHAPE parent=software_risk x=900 y=390 w=280 h=180 type=round_rectangle fill=#EAF8F0 border_color=#2F855A color=#173B2D font=open_sans size=18 valign=middle "Tests<br>6/6 bestanden<br>required validation workflows green"
software_evidence FRAME x=7800 y=0 w=1120 h=630 fill=#F8FAFC "07 · Evidenz und Grenzen"
software_evidence_title TEXT parent=software_evidence x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Evidenz und Grenzen"
software_evidence_thesis TEXT parent=software_evidence x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Der Snapshot ist prüfbar; Aktualität und Vollständigkeit werden nicht erfunden."
software_sources DOC parent=software_evidence x=380 y=410 <<<
# Quellenbindung

- github.lenskit · Revision 0ec3cf2938a6 · heimgewebe/lenskit
- repo.lenskit · Revision 0ec3cf2938a6 · heimgewebe/lenskit

Snapshot: 960df10aa9e2c4635f9c3c102b470e71ca3e95a5fa76e30059c84f7fc184c7d0
Aktualitätsgrenze: Revisionen sind belegt; ein Beobachtungszeitpunkt wird nicht behauptet.
>>>
software_non_claims TABLE parent=software_evidence x=900 y=400 "Nicht-Ansprüche" <<<
Grenze:text
---
kein Livezustand ohne Beobachtungszeit
keine Provider-Mutation
keine Vollansicht aller Datensätze
>>>
