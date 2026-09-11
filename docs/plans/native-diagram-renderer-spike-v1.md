# Native Diagram Renderer Spike v1

Stand: 2026-09-11

## Entscheidung und Ziel

Dieser genehmigte Spike prüft einen kleinen, deterministischen, nativen SVG-Renderer als visuelle Alternative für Schauwerk-Diagramme. Er ist ausschließlich **Gate 1: Renderer-Evidenz**. Nach PR #181 gilt für den draw.io-Produktpfad ein Feature-Freeze; der Spike erweitert diesen Pfad nicht und ersetzt draw.io noch nicht.

Die bestehende `schauwerk-representation-input.v1`-Eingabe bleibt die semantische Autorität. Der Spike führt weder ein neues kanonisches Graphmodell noch eine zweite Semantikschicht ein. Inhalt, Gruppen, Knoten, Kanten und stabile Source-IDs werden mit `validate_representation_input` geprüft und danach nur dargestellt.

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

## Vorläufige visuelle Grammatik

- Gruppen werden als ruhige beschriftete Regionen dargestellt.
- Knotentypen teilen ein festes Kartenraster, unterscheiden sich aber durch Farbe, Rundung, Akzent und kleines Typzeichen.
- Beziehungen sind kubische Kurven mit leisen Pfeilspitzen statt draw.io-artiger orthogonaler Ellenbogen.
- Beziehungstypen bleiben über Farbe, Strichstärke und Strichmuster erkennbar.
- Source-IDs bleiben getrennt von sichtbaren Labels als Renderer-Metadaten erhalten.

Diese Grammatik ist Gate-Evidenz, kein dauerhaft zugesagtes Designsystem.

## Bewusst nicht enthalten

- Mermaid und draw.io laufen vorerst weiter über ihre bestehenden Legacy-Pfade; dieser Spike verdrahtet den nativen Renderer nicht in Router, Paket oder Editor.
- Es gibt in diesem Slice keinen Editor, keine Mutation, keine Auswahl- oder Drag-Interaktion und keine Frameworkentscheidung.
- Es gibt keine CRDT-, Kollaborations- oder Mehrbenutzerfunktion.
- Es gibt keine Layoutautorität und keinen Roundtrip in ein persistiertes Layoutmodell.
- Es gibt keine iPad- oder Touch-Akzeptanzbehauptung.

## Stop-Regel

Wenn die nativen Ausgaben der drei Golden Cases gegenüber den bisherigen Diagrammwegen nicht **sichtbar besser** sind, endet die Untersuchung nach Gate 1. Technische Deterministik und vollständige Source-ID-Coverage allein rechtfertigen weder einen neuen Editor noch den Ersatz von Mermaid oder draw.io.
