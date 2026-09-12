# Native Diagram Renderer Spike v1

Stand: 2026-09-12

## Entscheidung und Ziel

Dieser genehmigte Spike prüft einen kleinen, deterministischen, nativen SVG-Renderer als visuelle Alternative für Schauwerk-Diagramme. Er ist ausschließlich **Gate 1: Renderer-Evidenz**. Nach PR #181 gilt für den draw.io-Produktpfad ein Feature-Freeze; der Spike erweitert diesen Pfad nicht und ersetzt draw.io noch nicht.

Die bestehende `schauwerk-representation-input.v1`-Eingabe bleibt die semantische Autorität. Der Spike führt weder ein neues kanonisches Graphmodell noch eine zweite Semantikschicht ein. Inhalt, Gruppen, Knoten, Kanten und stabile Source-IDs werden mit `validate_representation_input` geprüft und danach nur dargestellt.

`src/schauwerk/visual/grammar.py` mit `schauwerk-visual-grammar.v1` und `docs/visual/schauwerk-visual-system-v2.md` bleiben die kanonische, rendererunabhängige Design- und Qualitätsautorität. Die renderer-lokale Knotenart- und Beziehungsdarstellung dieses Gate-1-Spikes ist ein experimentelles Rendererprofil, keine konkurrierende visuelle Grammatik. Gemeinsam genutzte semantische Rollen müssen vor jedem Cutover mit den kanonischen semantischen Tokens abgeglichen werden; dieser Spike nimmt einen solchen Cutover nicht vor. Das SVG bindet seine Gate-Evidenz deshalb als Metadatum an die geltende `GRAMMAR_SCHEMA_VERSION`.

## Abgrenzung der Gates

1. **Gate 1 – visueller Renderer:** Ein kleiner, dependency-freier Python-Pfad erzeugt deterministisches, statisches SVG. Seine Aufgabe ist ausschließlich, die Qualität einer nativen visuellen Grammatik anhand fester Fälle sichtbar zu prüfen.
2. **Visuelles Gate:** Die drei Golden Cases werden als reale SVGs betrachtet. Nur wenn die native Ausgabe sichtbar besser und als Schauwerk-Ausdruck erkennbar ist, darf eine Interaktions- oder Frameworkentscheidung folgen. Ist sie nicht sichtbar besser, stoppt der Pfad hier.
3. **Spätere Layout-Schicht:** Persistierbares Layout kann später als minimale, abgeleitete Schicht hinzukommen. Es ist nicht kanonische fachliche Wahrheit und gehört ausdrücklich nicht zu diesem renderer-only Slice.
4. **Spätere Interaktionsphase:** Erst nach bestandenem visuellen Gate werden Interaktionsmodell und Framework verglichen. Der iPad-Gate gehört in diese Phase, nicht in den statischen Renderer-Spike.

## Golden Cases

Gate 1 muss die vorhandenen semantischen Eingaben vollständig darstellen:

- `system-landscape-v1` für eine gruppierte Wissens- und Systemlandschaft;
- `decision-flow-v1` für einen gerichteten Entscheidungsprozess;
- `narrative-journey-v1` für eine lesbare narrative Bewegung.

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

**Gate-Urteil:** Die visuelle Hypothese ist mit den nachträglich geschlossenen Kollisions- und Überlaufrisiken erneut klar bestätigt. Vor Publikation muss der exakte finale Dirty-State noch einmal gerendert und technisch geprüft werden. Phase 2 öffnet erst operativ, wenn dieselben Renderer- und Testbytes als Commit publiziert wurden und der exakte PR-HEAD CI, Review sowie einen commitgebundenen visuellen Readback ohne Regression besteht. Bis dahin bleibt Phase 2 geschlossen.

## Bewusst nicht enthalten

- Mermaid und draw.io laufen vorerst weiter über ihre bestehenden Legacy-Pfade; dieser Spike verdrahtet den nativen Renderer nicht in Router, Paket oder Editor.
- Es gibt in diesem Slice keinen Editor, keine Mutation, keine Auswahl- oder Drag-Interaktion und keine Frameworkentscheidung.
- Es gibt keine CRDT-, Kollaborations- oder Mehrbenutzerfunktion.
- Es gibt keine Layoutautorität und keinen Roundtrip in ein persistiertes Layoutmodell.
- Es gibt keine iPad- oder Touch-Akzeptanzbehauptung.

## Stop-Regel

Wenn die nativen Ausgaben der drei Golden Cases gegenüber den bisherigen Diagrammwegen nicht **sichtbar besser** sind, endet die Untersuchung nach Gate 1. Technische Deterministik und vollständige Source-ID-Coverage allein rechtfertigen weder einen neuen Editor noch den Ersatz von Mermaid oder draw.io.

Nach einem bestandenen Gate ist die nächste zulässige Stufe ausschließlich ein separater Phase-2-Slice für Pan/Zoom, Selection und Node-Drag auf frischem `main`. Ein Voll-Editor, React/React Flow oder eine andere Frontend-Toolchain bleiben weiterhin hinter diesem zweiten Nachweis.