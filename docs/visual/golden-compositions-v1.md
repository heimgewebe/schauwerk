# Golden Compositions v1

Stand: 17. Juli 2026

## Zweck

Die Golden Compositions sind drei absichtlich unterschiedliche Referenzkompositionen für den Schauwerk-Darstellungsrouter. Sie verhindern, dass gestalterische Qualität mit einer einzigen universellen Vorlage oder bloßen Farbvarianten verwechselt wird.

Der Katalog liegt unter `docs/operators/fixtures/golden/golden-compositions-v1.json`.

## Referenzen

| Referenz | Leitformat | Hierarchie | Dichte | Objektauswahl |
| --- | --- | --- | --- | --- |
| Systemlandschaft | JSON Canvas | Wahrheit → Steuerung → Lieferung → Beobachtung | mittel, gruppiert | Systeme, Stores, Dienste und Evidenz |
| Entscheidungsfluss | Tabelle | Signal → Prüfung → Entscheidung → Wirkung | kompakt, sequenziell | Aktionen, Entscheidungen, Risiken und Evidenz |
| Narrative Reise | Dokument | Frage → Spannung → Wahl → Bedeutung | locker, erzählerisch | Mensch, Konzepte, Risiko, Entscheidung, Handlung und Evidenz |

Die Fixtures erzwingen nur das jeweilige Leitformat. Ergänzende Formate leitet der Router aus Absicht und Anforderungen ab. Dadurch bleiben die Referenzen echte Routingbeispiele statt vollständig vorgegebener Ausgabepläne.

## Qualitätsgate

Jede Referenz muss:

- als Representation Package deterministisch kompilieren;
- ohne Providerkontakt bleiben;
- durch die bestehende Paketprüfung laufen;
- einen lokalen SVG-/HTML-Preview erzeugen;
- null visuelle Blocker besitzen;
- einen von den anderen Referenzen verschiedenen Paket- und Previewdigest erzeugen.

Warnungen wie mögliches Provider-Auto-Sizing bleiben sichtbar. Sie werden nicht als ästhetische Freigabe umgedeutet.

## Grenzen

Die Golden Compositions belegen keine universelle Stileignung, keine pixelidentische Miro-Darstellung und keine automatische ästhetische Akzeptanz. Sie sind prüfbare Ausgangspunkte für bewusst unterschiedliche Informationsformen.
