root FRAME x=0 y=0 w=3000 h=1900 "Grabowski Operator Overview"
title TEXT parent=root x=1500 y=90 w=2400 size=34 align=center "Grabowski — deterministische Operator-Projektion"
contract FRAME x=-850 y=300 w=900 h=1250 "Vertrag"
capabilities FRAME x=150 y=300 w=900 h=1250 "Fähigkeiten"
risk FRAME x=1150 y=300 w=900 h=1250 "Risiko und Grenzen"
contract_doc DOC parent=contract x=450 y=230 <<<
# Zweck

Deterministic repository contract for the Grabowski operator. Live state is returned by the grabowski_context MCP tool.

**Profil:** observe

**Policy-Modus:** observe

**Protokoll:** Operator Relay v0
>>>
category_table TABLE parent=capabilities x=450 y=300 "Capability-Kategorien" <<<
Kategorie:text | Anzahl:text
---
artifact | 3
audit | 3
browser-worker | 4
checkout-lifecycle | 4
command | 5
context | 5
deployment | 1
diagnostics | 1
filesystem | 7
fleet | 2
grip-surface | 2
gui-worker | 4
knowledge | 9
operation | 3
operations-observability | 4
privileged-execution | 1
privileged-reference | 2
process | 2
recovery | 2
remote-version-control | 3
resource | 5
secret | 5
service | 3
session | 3
task | 10
version-control | 7
>>>
risk_table TABLE parent=risk x=450 y=300 "Risikoklassen" <<<
Klasse:text | Anzahl:text
---
critical | 1
high | 18
low | 54
medium | 20
variable | 7
>>>
counts SHAPE parent=capabilities x=450 y=940 w=650 h=210 type=round_rectangle "Gesamt: 100 | read-only: 57 | effektvoll: 43 | Runtime-Tools: 100"
boundary SHAPE parent=risk x=450 y=940 w=650 h=250 type=round_rectangle "Quellsystem bleibt maßgeblich. Keine Live-Laufzeitbehauptung, keine Geheimnisse und keine Provider-Mutation. Grenzen bestätigt: 1/4."
footer TEXT parent=root x=1500 y=1740 w=2400 size=18 align=center "Snapshot d6a43fa90e1a4822 · aus deklarierter Quelle"
