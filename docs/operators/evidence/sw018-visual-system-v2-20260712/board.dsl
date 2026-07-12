f1_cover FRAME x=0 y=0 w=1120 h=630 fill=#F8FAFC "01 · Schauwerk Visual System v2"
f1_cover_title TEXT parent=f1_cover x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Schauwerk Visual System v2"
f1_cover_thesis TEXT parent=f1_cover x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Klarheit vor Dekoration. Bedeutung vor Objektmenge."
cover_rule SHAPE parent=f1_cover x=560 y=380 w=960 h=160 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Ein Schauwerk führt in 10 Sekunden zur Orientierung – und in wenigen Minuten zur belastbaren Einsicht."
f2_map FRAME x=1300 y=0 w=1120 h=630 fill=#F8FAFC "02 · Lesekarte"
f2_map_title TEXT parent=f2_map x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Lesekarte"
f2_map_thesis TEXT parent=f2_map x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Jeder Inhalt erhält einen sichtbaren Platz im Erkenntnisweg."
map_a SHAPE parent=f2_map x=170 y=360 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "1<br>Orientieren"
map_b SHAPE parent=f2_map x=430 y=360 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "2<br>Verstehen"
map_c SHAPE parent=f2_map x=690 y=360 w=180 h=120 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "3<br>Bewerten"
map_d SHAPE parent=f2_map x=950 y=360 w=180 h=120 type=round_rectangle fill=#EAF8F0 border_color=#2F855A color=#173B2D font=open_sans size=18 valign=middle "4<br>Belegen"
map_ab CONNECTOR from=map_a to=map_b shape=elbowed end_cap=arrow "weiter"
map_bc CONNECTOR from=map_b to=map_c shape=elbowed end_cap=arrow "prüfen"
map_cd CONNECTOR from=map_c to=map_d shape=elbowed end_cap=arrow "sichern"
f3_objects FRAME x=2600 y=0 w=1120 h=630 fill=#F8FAFC "03 · Objektwahl"
f3_objects_title TEXT parent=f3_objects x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Objektwahl"
f3_objects_thesis TEXT parent=f3_objects x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Nicht alles ist eine Haftnotiz. Die Form trägt die Bedeutung."
objects_matrix TABLE parent=f3_objects x=420 y=410 "Inhalt → Miro-Objekt" <<<
Inhalt:text | Objekt:text | Warum:text
---
Beziehung | Connector | Richtung sichtbar
Vergleich | Tabelle | Dichte ohne Kartenwand
Erklärung | Dokument | Text bleibt lesbar
Offene Idee | Haftnotiz | bewusst veränderlich
>>>
objects_guard SHAPE parent=f3_objects x=920 y=410 w=240 h=180 type=round_rectangle fill=#FFE8E8 border_color=#C53030 color=#4A1010 font=open_sans size=18 valign=middle "Blocker<br>Haftnotizen für fertige Fakten oder lange Erklärungen"
f4_architecture FRAME x=3900 y=0 w=1120 h=630 fill=#F8FAFC "04 · Informationsarchitektur"
f4_architecture_title TEXT parent=f4_architecture x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Informationsarchitektur"
f4_architecture_thesis TEXT parent=f4_architecture x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Ein Frame beantwortet eine Hauptfrage – nicht sieben Nebenfragen."
arch_a SHAPE parent=f4_architecture x=170 y=360 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Einstieg<br>Worum geht es?"
arch_b SHAPE parent=f4_architecture x=430 y=360 w=180 h=120 type=round_rectangle fill=#E6F6F8 border_color=#147D92 color=#0B3C49 font=open_sans size=18 valign=middle "Kern<br>Was gilt?"
arch_c SHAPE parent=f4_architecture x=690 y=360 w=180 h=120 type=round_rectangle fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "Synthese<br>Was folgt?"
arch_d SHAPE parent=f4_architecture x=950 y=360 w=180 h=120 type=round_rectangle fill=#EAF8F0 border_color=#2F855A color=#173B2D font=open_sans size=18 valign=middle "Evidenz<br>Woher wissen wir es?"
arch_ab CONNECTOR from=arch_a to=arch_b shape=elbowed end_cap=arrow "fokussieren"
arch_bc CONNECTOR from=arch_b to=arch_c shape=elbowed end_cap=arrow "verdichten"
arch_cd CONNECTOR from=arch_c to=arch_d shape=elbowed end_cap=arrow "belegen"
f5_quality FRAME x=5200 y=0 w=1120 h=630 fill=#F8FAFC "05 · Qualitätsgate v2"
f5_quality_title TEXT parent=f5_quality x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Qualitätsgate v2"
f5_quality_thesis TEXT parent=f5_quality x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Viele Objekte ergeben noch kein gutes Board."
quality_matrix TABLE parent=f5_quality x=420 y=410 "Freigabekriterien" <<<
Dimension:text | Muss gelten:text
---
Narration | Lesepfad vollständig
Hierarchie | Titel und Kernaussage eindeutig
Dichte | mindestens 42 % Weißraum
Semantik | Objekt und Farbe erfüllen eine Rolle
>>>
quality_decision SHAPE parent=f5_quality x=920 y=410 w=240 h=180 type=diamond fill=#FFF8DD border_color=#B7791F color=#3C2F12 font=open_sans size=18 valign=middle "Freigabe<br>≥ 90 Punkte<br>0 Blocker"
f6_example FRAME x=6500 y=0 w=1120 h=630 fill=#F8FAFC "06 · Vorher / Nachher"
f6_example_title TEXT parent=f6_example x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Vorher / Nachher"
f6_example_thesis TEXT parent=f6_example x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Der Unterschied liegt in der Ordnung, nicht im Schmuck."
example_before SHAPE parent=f6_example x=260 y=400 w=360 h=200 type=round_rectangle fill=#FFE8E8 border_color=#C53030 color=#4A1010 font=open_sans size=18 valign=middle "Vorher<br>Technisch reich<br>visuell gleichgewichtet<br>kein klarer Fokus"
example_after SHAPE parent=f6_example x=860 y=400 w=360 h=200 type=round_rectangle fill=#EAF8F0 border_color=#2F855A color=#173B2D font=open_sans size=18 valign=middle "Nachher<br>7 Rollenframes<br>klare Dramaturgie<br>semantische Objekte"
example_change CONNECTOR from=example_before to=example_after shape=elbowed end_cap=arrow "neu ordnen"
f7_evidence FRAME x=7800 y=0 w=1120 h=630 fill=#F8FAFC "07 · Evidenz und Grenzen"
f7_evidence_title TEXT parent=f7_evidence x=560 y=100 w=960 font=open_sans size=38 align=left color=#102A43 "Evidenz und Grenzen"
f7_evidence_thesis TEXT parent=f7_evidence x=560 y=200 w=960 font=open_sans size=24 align=left color=#102A43 "Gestaltung bleibt prüfbar, ohne sich als objektive Schönheit auszugeben."
evidence_sources DOC parent=f7_evidence x=380 y=410 <<<
# Forschungsbasis

Miro: Canvas, Diagramme, Präsentationen, Vorlagen, Focus Mode, Layers und Hilfecenter.

Der deterministische Plan wird vollständig geprüft; der Remote-Readback bestätigt nur die Umsetzung.
>>>
evidence_limits TABLE parent=f7_evidence x=900 y=400 "Nicht-Ansprüche" <<<
Grenze:text
---
kein universeller Geschmack
keine automatische Fremdboard-Änderung
keine Schönheit durch Objektzählung
>>>
