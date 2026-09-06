---
id: classroom-v1
role: contract
status: active
doc_type: operator-guide
title: Schauwerk Classroom v1
summary: Thin classroom orchestration over Learning View, verified Miro snapshots and existing management boundaries.
---

# Schauwerk Classroom v1

## Zweck

`schauwerk classroom` fasst vorhandene Schauwerk-Faehigkeiten zu einem kleinen Unterrichtszyklus zusammen. Es fuehrt kein zweites Unterrichtsdatenmodell, keine Schuelerkonten, kein Aktivitaetstracking und keine Lernfortschritts-Scores ein.

Miro bleibt die kollaborative Arbeitsflaeche. Schauwerk bindet Vorbereitung, verifizierte Snapshots, strukturelle Differenzen und lokale Abschlussbelege. Bestehende `view`-, `region`-, Education-, Miro- und Renderer-Vertraege bleiben massgeblich.

## Kommandos

```bash
schauwerk classroom prepare demos/education/vibe-coding-kids.yml \
  --groups 6 \
  --template vibe-coding \
  --session-id vibe-coding-01 \
  --output-dir /tmp/classroom-prepared \
  --json

schauwerk classroom start schauwerk-klassenraum /tmp/classroom-prepared \
  --session-dir /tmp/classroom-session \
  --json

schauwerk classroom read schauwerk-klassenraum \
  --output /tmp/classroom-current.json \
  --baseline /tmp/classroom-session/started.json \
  --json

schauwerk classroom summarize \
  /tmp/classroom-session/started.json \
  /tmp/classroom-current.json \
  --output /tmp/classroom-summary.json \
  --json

schauwerk classroom close schauwerk-klassenraum /tmp/classroom-session --json

schauwerk classroom continue \
  /tmp/classroom-session \
  next-lesson.yml \
  --groups 6 \
  --template vibe-coding \
  --session-id vibe-coding-02 \
  --output-dir /tmp/classroom-next \
  --json
```

## Sicherheitsgrenze

`prepare`, `summarize` und `continue` sind providerfrei. `read` und `close` lesen Miro nur. `start` ist die einzige Classroom-v1-Operation mit Provider-Mutation.

`start` arbeitet fail-closed:

1. vorbereitetes Paket digestgebunden laden;
2. Paket in ein privates Session-Verzeichnis binden;
3. verifizierten Vorher-Snapshot erzeugen;
4. vorhandenen Session-Marker ausschliessen;
5. vorhandene Learning-View-DSL plus Gruppenarbeitsbereiche anwenden;
6. verifizierten Nachher-Snapshot erzeugen;
7. den Session-Marker im Provider-Readback nachweisen;
8. erst dann ein `start-receipt.json` schreiben.

Ein vorhandenes gueltiges Start-Receipt wird ohne erneute Mutation wiederverwendet. Partielle Startartefakte oder ein bereits vorhandener Marker blockieren einen blinden Retry.

Classroom v1 loescht oder verschiebt keine bestehende Schuelerarbeit. Ein Providerfehler nach einer erfolgreich gestarteten Layout-Mutation kann nicht automatisch rueckgaengig gemacht werden; in diesem Fall bleibt ein `start-partial.json` als Reconciliation-Blocker. Das ist bewusst enger als eine behauptete automatische Wiederherstellung.

## Semantische Rollen

Classroom v1 verwendet nur wenige Rollen und bildet sie auf die bereits vorhandenen Management-Modi ab:

| Rolle | Management-Modus |
| --- | --- |
| `instruction` | `managed` |
| `material` | `read-only` |
| `group_workspace` | `cooperative` |
| `student_output` | `manual` |
| `synthesis` | `suggest-only` |
| `reflection` | `approval-required` |
| `teacher_output` | `approval-required` |

Es entsteht keine Universalontologie. Gruppen werden durch sichtbare, stabile Arbeitsbereichstitel markiert. Individuelle Schueleridentitaet wird nicht erfasst.

## Vorlagen

V1 liefert drei kleine Arbeitsmuster:

- `vibe-coding`: Idee → Prompt → KI-Ergebnis → Test → Aenderung → Erkenntnis;
- `discover`: Frage → Vermutung → Ausprobieren → Beobachtung → Erklaerung → offene Frage;
- `group-compare`: Ansatz → Beleg → Staerke → Grenze → Fazit.

Die Vorlagen verwenden native Miro-Objekte. Wiederverwendbare gestaltete Bildassets bleiben ein getrennter Fundus-Fall.

## Erkenntnisgrenze

Der deterministische Snapshotvergleich berichtet ausschliesslich:

- hinzugefuegte Elemente;
- entfernte Elemente;
- strukturell veraenderte Elemente;
- Typverteilungen dieser Aenderungen;
- Kommentardifferenz.

Er behauptet ausdruecklich nicht:

- individuelle Autorenschaft;
- Schueleridentitaet;
- Lernfortschritt;
- Verstaendnis;
- Qualitaet einer Schuelerleistung;
- paedagogische Kausalitaet.

`interpretations` bleibt im deterministischen Kern leer. Eine spaetere KI-Synthese ist ein separater, als Interpretation gekennzeichneter Vorschlag und darf nur ueber die vorhandenen `suggest-only`-/`approval-required`-Grenzen in eine Werkflaeche gelangen.

## V1-Akzeptanz

Repository-Akzeptanz mutiert kein produktives Miro-Board. Sie prueft deterministisch Paketbindung, Vorlagen, Snapshot-Digests, epistemische Trennung, Start-Idempotenz mit einem Fake-Provider und den unveraenderten Legacy-CLI-Pfad.

Ein echter Unterrichtspilot mit anonymen Gaesten bleibt eine getrennte Live-Akzeptanz. Erst reale Unterrichtsbeobachtungen rechtfertigen weitere Classroom-Funktionen.
