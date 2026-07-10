root FRAME x=0 y=0 w=4400 h=2200 "Grabowski Operational Overview"
title TEXT parent=root x=2200 y=80 w=2800 size=34 align=center "Grabowski — Vertrag und beobachteter Betrieb"
static FRAME x=-1450 y=300 w=900 h=1450 "Statischer Vertrag"
live FRAME x=0 y=300 w=1800 h=1450 "Beobachteter Zustand"
gaps FRAME x=1450 y=300 w=900 h=1450 "Lücken und Grenzen"
static_doc DOC parent=static x=450 y=300 <<<
# Zweck

Deterministic repository contract for the Grabowski operator. Live state is returned by the grabowski_context MCP tool.

**Profil:** observe

**Fähigkeiten:** 100

Diese Angaben stammen aus dem versionierten Operator-Vertrag, nicht aus Livebeobachtung.
>>>
hosts_table TABLE parent=live x=420 y=300 "Hosts · partial" <<<
Merkmal:text | Wert:text
---
declared count | 4
enabled count | 4
reachable count | 3
unavailable count | 1
>>>
hosts_freshness TEXT parent=live x=420 y=730 w=720 size=16 align=center "Quelle: grabowski.fleet-observation · Alter: 45 s · Verfall: 900 s"
runtime_table TABLE parent=live x=1320 y=300 "Runtime · partial" <<<
Merkmal:text | Wert:text
---
running grabowski units | 2
expected tool count | 100
policy state | unknown
failed grabowski units | 23
>>>
runtime_freshness TEXT parent=live x=1320 y=730 w=720 size=16 align=center "Quelle: grabowski.runtime-observation · Alter: 20 s · Verfall: 300 s"
work_table TABLE parent=live x=420 y=970 "Arbeit · healthy" <<<
Merkmal:text | Wert:text
---
active run count | 0
open pr count | 1
ready task count | 1
current task state | ready
>>>
work_freshness TEXT parent=live x=420 y=1400 w=720 size=16 align=center "Quelle: bureau.grabowski-work-observation · Alter: 0 s · Verfall: 300 s"
gaps_table TABLE parent=gaps x=450 y=300 "Folgethemen · healthy" <<<
Merkmal:text | Wert:text
---
tracked followup count | 38
blocked count | 0
planned count | 37
repair candidate count | 0
>>>
boundary SHAPE parent=gaps x=450 y=1050 w=680 h=320 type=round_rectangle "Quellsysteme bleiben maßgeblich. Die Ansicht enthält nur Zustandsklassen und Summen: keine Rohlogs, Geheimnisse, Hostnamen oder Provider-Mutation."
overall SHAPE parent=root x=2200 y=1930 w=1700 h=180 type=round_rectangle "Gesamtzustand: degraded · healthy=2 · partial=2 · stale=0 · unavailable=0"
footer TEXT parent=root x=2200 y=2130 w=2800 size=16 align=center "Operational snapshot 5af25c3a17b3d3c4 · bewertet 2026-07-10T05:43:15Z"
