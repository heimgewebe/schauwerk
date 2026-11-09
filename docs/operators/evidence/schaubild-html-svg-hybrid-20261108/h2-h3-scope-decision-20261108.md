# Hybrid HTML/SVG – H2-/H3-Nutzwertentscheidung, 8. November 2026

**Geltungsbereich:** PR #235, revisionsgebundene Source-Digests aus `technical-proof-final-ui-followup.json`. Die Entscheidung ersetzt weder die vollständige CI noch die spätere Commonthing-Produktivabnahme.

## Nachgewiesener Nutzen

Der bereits vorhandene native Smart-Edge-Router erzeugt die einzige Kanten- und Labelgeometrie. Die optionale HTML-Ebene verwendet denselben Canvas-Transform und liest die live gerenderten SVG-Boxen statt erneut zu routen. HTML-Knoten- und Kantentext ist selektierbar und kopierbar; die Vorschau ist schreibgeschützt und über ein dauerhaft erreichbares Ansicht-Menü umschaltbar.

Der A/B-Readback (Chrome, 1120 × 850, 844 × 390, 320 × 700, hell; 844 × 390, dunkel) ist im Screenshot `visual-native-html-hybrid-20261108.jpg` gebunden. Kurven, Pfeile und Knotenlage bleiben gleich. Bei der dunklen Gruppenüberschrift ist die HTML-Darstellung sichtbar lesbarer. Die übrigen Textboxen sind in diesem Korpus weitgehend gleichwertig; eine grundsätzliche visuelle Überlegenheit wäre nicht belegt.

Technische Gegenproben: 20 Hybrid-/Chrome- und Vertragstests sowie der native 320-Pixel-Safe-Area-Browsertest bestanden lokal. Ein einzelner synthetischer Stressfall mit 104 Knoten und 208 Kanten erzeugte 3309 DOM-Elemente in Native und 3728 in der Hybridvorschau; der native Bundle-Build dauerte 1,254 Sekunden auf dem Operatorhost. Keine belastbaren p50/p95-Interaktions-, Speicher- oder Safari-Messwerte liegen vor.

## Scopeentscheidung

**H2 begrenzt:** Die gemeinsame SVG-/HTML-Koordinatenbasis, DOM-Textdarstellung, Labelposition und Smart-Routing-Nachnutzung sind vorhanden und in den genannten Browserfällen geprüft. Eine eigenständige HTML-Textgrößenmessung mit dynamischer Knotenausweitung oder zusätzlicher Routing-Engine wird nicht eingeführt, solange kein reproduzierbarer Bedarf besteht. Beschriftungskonflikte bleiben Aufgabe des bestehenden Native-Routers; ein hoher z-index ist keine geometrische Lösung.

**H3 vorerst nicht freigeben:** Der Native-Editor kann JSON-Canvas-Knoten und -Kanten bereits unter derselben History bearbeiten. Das neue HTML-Inline-Editing würde hier ohne nachgewiesenen zusätzlichen Nutzwert eine zweite Eingabeschicht und zusätzliche Undo-/Verlustpfade schaffen. Deshalb bleibt HTML opt-in und read-only. Künftige H3-Arbeit erfordert ein konkretes Problem mit Native-Editing und Tests für Edit → Undo → Redo → Reload → Export.

**H4 separat:** Der Offline-HTML-Export aus PR #236 bleibt ein eigenständiges, schreibgeschütztes Downloadformat, kein Bearbeitungsrenderer und kein zweiter Originalspeicher.

## Offene Acceptance

Physische iPad-/Safari-Bedienung, echte produktive HTTP-Downloads und Öffnen aus Dateien, größere Diagramme mit Browser-Memory-/p95-Messung und vollständige Commonthing-OCI-/Release-Lock-Abnahme sind noch offen. Sie dürfen nicht aus dieser begrenzten Chrome-A/B-Sichtung geerbt werden.

Diese Screenshots sind ausschließlich technische/visuelle Prüfevidenz, keine wiederverwendbaren Produktbilder und keine Fundus-Assets.
