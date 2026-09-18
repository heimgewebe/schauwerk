# Native Diagram Renderer Spike v1

Stand: 2026-09-18

## Entscheidung und Ziel

Dieser genehmigte Spike prüft einen kleinen, deterministischen, nativen SVG-Renderer als visuelle Alternative für Schauwerk-Diagramme. Er war zunächst ausschließlich **Gate 1: Renderer-Evidenz**. Nach PR #181 gilt für den draw.io-Produktpfad ein Feature-Freeze; der native Pfad erweitert diesen draw.io-Pfad nicht und ersetzt draw.io noch nicht.

Die bestehende `schauwerk-representation-input.v1`-Eingabe bleibt die semantische Autorität. Der Spike führt weder ein neues kanonisches Graphmodell noch eine zweite Semantikschicht ein. Inhalt, Gruppen, Knoten, Kanten und stabile Source-IDs werden mit `validate_representation_input` geprüft und danach nur dargestellt.

`src/schauwerk/visual/grammar.py` mit `schauwerk-visual-grammar.v1` und `docs/visual/schauwerk-visual-system-v2.md` bleiben die kanonische, rendererunabhängige Design- und Qualitätsautorität. Die renderer-lokale Knotenart- und Beziehungsdarstellung dieses Gate-1-Spikes ist ein experimentelles Rendererprofil, keine konkurrierende visuelle Grammatik. Gemeinsam genutzte semantische Rollen müssen vor jedem Cutover mit den kanonischen semantischen Tokens abgeglichen werden; dieser Spike nimmt einen solchen Cutover nicht vor. Das SVG bindet seine Gate-Evidenz deshalb als Metadatum an die geltende `GRAMMAR_SCHEMA_VERSION`.

## Abgrenzung der Gates

1. **Gate 1 – visueller Renderer:** Ein kleiner, dependency-freier Python-Pfad erzeugt deterministisches, statisches SVG. Seine Aufgabe ist ausschließlich, die Qualität einer nativen visuellen Grammatik anhand fester Fälle sichtbar zu prüfen.
2. **Visuelles Gate:** Die drei Golden Cases werden als reale SVGs betrachtet. Nur wenn die native Ausgabe sichtbar besser und als Schauwerk-Ausdruck erkennbar ist, darf eine Interaktions- oder Frameworkentscheidung folgen. Ist sie nicht sichtbar besser, stoppt der Pfad hier.
3. **Spätere Layout-Schicht:** Persistierbares Layout kann später als minimale, abgeleitete Schicht hinzukommen. Es ist nicht kanonische fachliche Wahrheit.
4. **Phase 2 – enger Interaktionsnachweis:** Nach terminal bestandenem Gate 1 werden ausschließlich Pan/Zoom, Selection und Node-Drag auf dem nativen SVG geprüft. Desktop- und iPad-Readback entscheiden danach, ob Phase 3 beziehungsweise ein Cutover überhaupt sinnvoll ist.

## Golden Cases

Gate 1 muss die vorhandenen semantischen Eingaben vollständig darstellen:

- `system-landscape-v1` für eine gruppierte Wissens- und Systemlandschaft;
- `decision-flow-v1` für einen gerichteten Entscheidungsprozess;
- `narrative-journey-v1` für eine lesbare narrative Bewegung.

### Acceptancegrenze des Spikes – Präzisierung 2026-09-15

Gate 1 bewertet **exakt diese drei festen Golden-Fälle** als Renderer-Evidenz. Schema-Gültigkeit einer zusätzlichen oder synthetischen Eingabe bedeutet in diesem Spike nicht, dass jede denkbare Geometrie desselben `intent` bereits als allgemein produktionsreif geroutet werden muss. Umgekehrt ist jede Regression, die sich in einem der drei Goldens reproduziert, weiterhin ein Gate-1-Blocker.

Für gruppierte `knowledge_map`-Eingaben ist eine allgemeine Routing-/Occupancy-Grenze bei langen Same-Row- und parallelen Relationen bekannt. Sie ist für Gate 1 als offenes Post-Gate-Härtungsthema klassifiziert, weil sie außerhalb der drei eingefrorenen Golden-Fälle liegt und der native Renderer in diesem Slice weder in Router noch Produkt oder Editor verdrahtet wird. Diese Grenze gilt ausdrücklich **nicht als behoben** und muss vor einer Generalisierung des nativen Pfads beziehungsweise einem Produkt-Cutover separat gehärtet werden. Die Klassifikation darf nicht verwendet werden, um einen entsprechenden Fehler in `system-landscape-v1` oder einem der beiden anderen Gate-1-Goldens zu akzeptieren.

Diese Präzisierung dokumentiert die vor dem finalen Merge-Gate getroffene Scope-Entscheidung; sie erweitert weder die drei Acceptance-Fälle noch schwächt sie deren technische oder visuelle Anforderungen ab.

Für Gate 1 ist Determinismus an die **exakt normalisierte Repräsentationseingabe** gebunden. `validate_representation_input` bewahrt die deklarierte Reihenfolge von Gruppen, Knoten und Kanten und bindet sie in `input_digest`; eine Permutation dieser Listen ist deshalb eine andere Source-Identität und keine alternative Serialisierung derselben digestgebundenen Eingabe. Die Renderer-Zusage lautet entsprechend: dieselbe normalisierte Eingabe erzeugt dieselben SVG-Bytes. Einzelne Reorder-Regressionstests, insbesondere für Kantenrouting, prüfen bewusst stärkere lokale Robustheit, begründen aber keine allgemeine Permutationsäquivalenz für Knoten- oder Gruppenreihenfolgen. Gate 1 führt damit weder eine neue Sortiersemantik noch eine zweite Layoutautorität ein.

Jeder Fall muss alle Source-Knoten und Source-Kanten im SVG rücklesbar materialisieren. Die Prüfung umfasst außerdem deterministische Bytes, valides SVG, Text-Escaping, gruppierte Regionen, gekrümmte Beziehungen und eine vollständig lokale, inaktive Ausgabe ohne Skripte, externe Ressourcen, Links oder Laufzeitabhängigkeit.

## Experimentelles Rendererprofil

- Gruppen werden als ruhige beschriftete Regionen dargestellt.
- Knotentypen teilen ein festes Kartenraster, unterscheiden sich aber durch Farbe, Rundung, Akzent und kleines Typzeichen.
- Beziehungen sind kubische Kurven mit leisen Pfeilspitzen statt draw.io-artiger orthogonaler Ellenbogen.
- Beziehungstypen bleiben über Farbe, Strichstärke und Strichmuster erkennbar.
- Gerichtete Prozessdiagramme dürfen ein eigenes, aus der bestehenden Semantik abgeleitetes Ranglayout verwenden; Gruppen bleiben Darstellungskontext und werden nicht zur neuen fachlichen Autorität.
- Rückkopplungen und vertikale Nebenpfade werden deterministisch getrennt geroutet, damit sie die primäre Leserichtung nicht dominieren.
- Source-IDs bleiben getrennt von sichtbaren Labels als Renderer-Metadaten erhalten.

Dieses Profil ist Gate-Evidenz, kein dauerhaft zugesagtes Designsystem.

## Visuelles Gate – Arbeitsstand 2026-09-12

Nach mehreren begrenzten Iterationen wurde ausschließlich an den beobachteten Schwächen gearbeitet: effektive Schriftgröße, Prozesskomposition, Ja-/Nein-/Feedback-Trennung und Kantenverdichtung. Ein unabhängiger Code-Review deckte zusätzlich zwei technische Risiken auf: breite Glyphen konnten bei der größeren Typografie über ihre Boxen laufen, und zwei Prozesskanten schnitten im Entscheidungsfall fremde Karten. Die Korrektur wurde anschließend auf den Prozess-Intent begrenzt: Nebenäste laufen im freien Zeilenzwischenraum, der Feedbackpfad unterhalb aller Prozessknoten, und die Breitenbegrenzung greift nur dort, wo sie für den Prozessfall benötigt wird. Systemlandschaft und Narrative behalten ihre zuvor stärkere Typografie und ihr ruhigeres Routing. Der Kandidat bleibt renderer-only; es wurde keine Interaktions- oder Frontend-Schicht geöffnet.

Ein neues blindes A/B unter identischem Viewport `1440×900` verglich genau diesen v4-Native-Kandidaten mit dem draw.io-Pfad aus Schauwerk `main` `11be2927d2d3f1fe907c0f5fda0f8e52fad0be2e`. Der Reviewer kannte die Renderer-Zuordnung nicht. Ergebnis nach Auflösung:

- `system-landscape-v1`: Native klar besser;
- `decision-flow-v1`: Native klar besser;
- `narrative-journey-v1`: Native klar besser.

Die v4-Renderer-Evidenz vor dieser reinen Dokumentationsaktualisierung ist an Manifest-SHA-256 `792e7a4f86e8aa78c25f894cb023915ede8e4e3b66375bae0e7db00bed03ed9a`, Native-Source-SHA-256 `b1007de3bb667269fbc11d296982a6aa3b644ce22a288b95b600fb16c9a24e84` und den damaligen Arbeitsdiff `958b5743f540c86d246dc897298ae740bffd391c81938c7d306e2cedf0733875` gebunden. Der Diff-Digest ist ausdrücklich keine finale Commitbindung, weil schon diese Planaktualisierung den Gesamtdiff verändert. Auf dem v4-Kandidaten bestanden 16 fokussierte Renderer-Tests sowie `make validate` mit 1.139 Tests; Ruff, Compile und Registry-Validierung waren grün.

**Gate-Urteil:** Gate 1 wurde am 16.09.2026 auf dem später gemergten PR #184 terminal abgeschlossen. Die drei akzeptierten SVG-Bytes bleiben die Referenz für Phase 2; die Interaktionsschicht darf diese Rendererbytes nicht stillschweigend zu einer neuen visuellen Revision machen.

## Phase 2 – Interaktionsnachweis, freigegeben 2026-09-16

Phase 2 ist ein **separater lokaler Native-Viewer**, kein Umbau des bestehenden draw.io-Editors. Der Slice besitzt genau vier Interaktionen:

- Pan der Gesamtansicht per Pointer-Drag sowie unmodifiziertem Rad-/Trackpad-Scrollen;
- Zoom per Schaltflächen, `Ctrl`/`Meta` + Rad-/Trackpad-Geste und Zwei-Finger-Pinch;
- Auswahl eines Knotens über Pointer oder Tastatur;
- Verschieben eines Knotens als abgeleiteter Layout-Overlay.

Pointer-Auswahl und Drag bleiben getrennt: Ein Tap/Klick selektiert nur. Erst nach mindestens 4 CSS-Pixeln Bewegung wird daraus ein Node-Drag und nur dann darf ein Layout-Offset persistiert werden. Kommt ein zweiter Pointer hinzu, darf der Zwei-Finger-Pinch auch dann starten, wenn der erste Kontakt auf einem Knoten lag; ein bereits begonnener lokaler Drag wird dafür auf seinen Start-Offset zurückgesetzt.

Die `input_digest`-Bindung ist fail-closed: Der Viewer akzeptiert am nativen SVG-Root ausschließlich einen 64-stelligen lowercase SHA-256-Digest. Fehlt er oder ist er ungültig, wird vor Bildung des `localStorage`-Schlüssels abgebrochen.

Die Schichten bleiben strikt getrennt:

1. `representation.json` ist die normalisierte, digestgebundene und im Viewer read-only behandelte Semantik.
2. `diagram.svg` ist byte-exakt der bestehende Gate-1-Rendereroutput. Diese Datei wird durch den Viewer weder umgeschrieben noch neu geroutet.
3. `layoutOverrides` enthalten ausschließlich lokale `x/y`-Offsets je stabiler `data-source-id`. Sie werden unter einem an `input_digest` gebundenen Browser-`localStorage`-Schlüssel gespeichert und besitzen keine fachliche Autorität.

Für den engen Nachweis bleibt die Kanten-Geometrie nach einem Node-Drag bewusst auf dem Gate-1-SVG eingefroren. Phase 2 implementiert **keinen zweiten JavaScript-Router**. Ob Kanten beim späteren Produktpfad live nachgeführt, nach Drag deterministisch neu gerendert oder anders modelliert werden sollen, ist gerade eine Phase-3-/Cutover-Entscheidung. Diese sichtbare Grenze darf im Readback nicht als bereits gelöst dargestellt werden.

Der Viewer benötigt keine externe Runtime und keine Netzwerkverbindung. Seine lokale Testoberfläche wird ausschließlich auf `127.0.0.1` ausgeliefert. Draw.io, Mermaid-Router, Miro-Delivery und das bekannte allgemeine `knowledge_map`-Routing bleiben unangetastet.

### Phase-2-Acceptance

Technisch müssen mindestens gelten:

- kanonisches `diagram.svg` bleibt byte-identisch zum direkten Rendereroutput;
- Source-IDs bleiben für Knoten, Kanten und Gruppen rücklesbar;
- Pan-/Zoom- und Drag-Mathematik ist unabhängig vom Browser testbar;
- gespeicherte Layout-Offsets sind begrenzt, validiert und an den exakten `input_digest` gebunden;
- keine Interaktion schreibt in `representation.json` zurück;
- die statische Vieweroberfläche fordert keine externen Ressourcen an.

Visuell/interaktiv wird separat auf Desktop und iPad geprüft:

- Pan und Zoom bleiben kontrollierbar;
- Auswahl ist eindeutig sichtbar;
- ein Knoten lässt sich ohne ungewolltes Ansichts-Pan verschieben;
- Reset entfernt nur den lokalen Layout-Overlay;
- die eingefrorenen Kanten nach einem Drag sind als Phase-2-Grenze klar erkennbar und werden für die Phase-3-Entscheidung bewertet.

Erst nach diesem Readback wird entschieden, ob Phase 3 geöffnet wird. Phase 2 selbst ist **kein Cutover** und kein Beleg für einen vollständigen eigenen Editor.

## Bewusst nicht enthalten

- Mermaid und draw.io laufen vorerst weiter über ihre bestehenden Legacy-Pfade; Phase 2 verdrahtet den nativen Renderer noch nicht in den allgemeinen Router oder ersetzt den Produkteditor.
- Es gibt keine semantische Mutation, keine neue Graphautorität und keinen Roundtrip des lokalen Layout-Overlays in die Source-Repräsentation.
- Es gibt keine CRDT-, Kollaborations- oder Mehrbenutzerfunktion.
- Es gibt keine allgemeine `knowledge_map`-Härtung.
- Es gibt noch keinen Phase-3-/Produkt-Cutover.

## Stop-Regel

Wenn die nativen Ausgaben der drei Golden Cases gegenüber den bisherigen Diagrammwegen nicht **sichtbar besser** sind, endet die Untersuchung nach Gate 1. Technische Deterministik und vollständige Source-ID-Coverage allein rechtfertigen weder einen neuen Editor noch den Ersatz von Mermaid oder draw.io.

Nach bestandenem Gate 1 ist ausschließlich der oben definierte Phase-2-Slice zulässig. Ein Voll-Editor, React/React Flow oder eine andere Frontend-Toolchain bleiben weiterhin hinter diesem zweiten Nachweis. Phase 3 darf erst nach dem Desktop-/iPad-Readback und einer expliziten Cutover-Entscheidung geöffnet werden.

## Phase 3 – Schaubild-Renderer-Cutover, entschieden 2026-09-18

Nach bestandenem Desktop-/iPadOS-Readback aus Phase 2 wird der native Renderer in der
Schaubild-Produktoberfläche zum **primären Renderer für kanonische
`schauwerk-representation-input.v1`-Eingaben**. Der Cutover ersetzt nicht das
Repräsentationsmodell und implementiert keinen zweiten Browser-Renderer.

Der integrierte, weiterhin ausschließlich an `127.0.0.1` gebundene
`standalone_editor serve`-Pfad stellt dazu einen begrenzten same-origin Render-Endpunkt
bereit. Dieser validiert die Representation serverseitig, ruft den bestehenden
`schauwerk-native-diagram-v1` über `build_native_viewer` auf und liefert anschließend
den vorhandenen lokalen Native Viewer. Die Browser-Schicht entscheidet damit nur über
Routing und Interaktion; die SVG-Geometrie bleibt Python-Renderer-Autorität.

Der Produkt-Cutover ist bewusst **nicht** identisch mit einem vollständigen nativen
Editor:

- Semantische Mutation bleibt read-only.
- Node-Drag bleibt ein digestgebundener, browserlokaler Layout-Overlay.
- Kanten werden nach Node-Drag weiterhin nicht live neu geroutet.
- Native Quelle und SVG sind exportierbar; PNG bleibt vorerst Legacy-Funktion.
- Mermaid, JSON Canvas und bestehendes draw.io/XML bleiben als explizite
  Kompatibilitätspfade über diagrams.net verfügbar; es gibt keine stille Migration.
- Ein statisch gebautes Bundle allein besitzt keinen Python-Render-Endpunkt. Der native
  Produktpfad benötigt deshalb den integrierten Loopback-`serve`-Pfad.

### Knowledge-map-Gate

Die bekannte allgemeine Long-Same-Row-/Parallel-Routinggrenze für `knowledge_map` ist
durch diesen Cutover **nicht** behoben. Deshalb wird `knowledge_map` am nativen
Produkt-Endpunkt fail-closed abgelehnt und bleibt vorerst über JSON Canvas im
Legacy-Pfad. Damit ist der Cutover für die übrigen schema-gültigen Intents möglich,
ohne die dokumentierte Routinggrenze als gelöst auszugeben.

Die Phase-2-Viewer-Manifeste dürfen weiterhin deklarieren, dass ein isolierter
Viewer-Build allein keine Phase-3-Acceptance beweist. Die Phase-3-Aussage entsteht erst
durch die zusätzliche Schaubild-Integration, deren Admission-Gate, Tests und visuellen
Readback.

