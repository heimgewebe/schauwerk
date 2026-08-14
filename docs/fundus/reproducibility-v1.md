---
id: schauwerk-fundus-reproducibility-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Reproducibility v1
summary: Read-only drift checks and temporary-state reproduction of digest-bound Fundus builds.
---

# Schauwerk Fundus Reproducibility v1

## Zweck

Ein gespeicherter Fundus-Build bindet Asset-Manifest, Recipe, Sources, Toolchain und Outputs. Reproducibility v1 beantwortet zwei getrennte Fragen:

1. **Drift:** Stimmen die heute sichtbaren Registry- und Source-Bindungen noch mit dem gespeicherten Build überein?
2. **Reproduce:** Erzeugt die aktuelle Fundus-Toolchain unter genau diesen noch gültigen Bindungen erneut dieselbe Build-Identität?

Beide Prüfungen verändern den kanonischen Fundus-State nicht.

## `drift`

`schauwerk fundus drift ASSET --build DIGEST` lädt den existierenden Build read-only und prüft mindestens:

- gespeicherter `asset_manifest_sha256` gegen das aktuelle Asset-Manifest;
- gespeicherter `recipe_sha256` gegen die aktuelle Recipe mit derselben ID;
- Vorhandensein und SHA-256 jedes gebundenen Source-Objekts;
- bei `generated` und `edited`: weiterhin gültige Ingest- und Image-Brief-Bindung.

Das Ergebnis ist ein `schauwerk-fundus-reproduction.v1`-Report mit `operation=drift`. Registry- oder Source-Abweichungen ergeben `status=drifted` und `ok=false`. Der allgemeine Schauwerk-Runner transportiert diesen semantischen Zustand im Report; `ok=false` ist daher nicht automatisch ein Prozessfehler.

Ein bereits intern beschädigter Baseline-Build — etwa ein Output mit falschem Digest — wird dagegen vor Report-Erzeugung fail-closed abgewiesen. `drift` versucht keinen Rebuild. Dadurch bleibt klar getrennt, ob der gespeicherte Beleg selbst ungültig ist, bereits die aktuelle Eingangsautorität abgewichen ist oder erst die aktuelle Toolchain andere Bytes erzeugt.

## `reproduce`

`schauwerk fundus reproduce ASSET --build DIGEST` führt zuerst denselben Drift-Preflight aus. Bei Binding-Drift wird fail-closed **nicht** reproduziert.

Bei sauberem Preflight:

1. wird ein privater temporärer Fundus-State angelegt;
2. nur die exakt gebundenen Source-Objekte sowie benötigte Ingest-/Image-Brief-Receipts werden in diesen temporären State kopiert;
3. die kanonische Registry wird nur gelesen;
4. der Build wird dort mit der aktuellen Fundus-Toolchain erneut erzeugt;
5. Build-Digest, geordnete Output-SHA-256 und Toolchain-Evidenz werden mit dem gespeicherten Build verglichen;
6. anschließend wird der Drift-Readback erneut ausgeführt, um Registry-/Source-Änderungen während der Reproduktion zu erkennen;
7. der temporäre State wird verworfen.

Nur wenn alle Vergleiche übereinstimmen, lautet der Status `reproduced` und `ok=true`.

## Statuswerte

- `clean`: Drift-Prüfung ohne Abweichung;
- `drifted`: Registry-, Source- oder Provenienzbindung stimmt nicht;
- `reproduced`: temporärer Rebuild entspricht dem gespeicherten Build;
- `reproduction_drift`: Rebuild lief, aber Build-, Output- oder Toolchain-Identität weicht ab;
- `reproduction_failed`: Rebuild konnte technisch nicht abgeschlossen werden.

## Kanonischer State

Reproducibility v1 schreibt keine neuen Builds, Previews, Acceptances oder Packages in den kanonischen Fundus-State. Die Reproduktion verwendet dafür einen separaten temporären `data_root`.

Die Registry bleibt die aktuelle semantische Autorität und wird ausschließlich read-only verwendet. Wenn die aktuelle Asset- oder Recipe-Revision nicht mehr dem gespeicherten Digest entspricht, wird dies als Drift gemeldet; Reproducibility v1 rekonstruiert keine nicht mehr vorhandene historische Registry-Revision aus Vermutungen.

## Nichtbehauptungen

Ein erfolgreicher Rebuild beweist technische Reproduzierbarkeit der gebundenen Transformation, aber **keine neue visuelle Acceptance**. Er authentifiziert weder ursprüngliche Reviewer noch historische Providerzustände und ersetzt keine Backup-/Restore-Evidenz.

Ein `reproduction_drift` beweist außerdem nicht automatisch einen Fehler der neuen Toolchain. Die Abweichung ist zunächst technische Evidenz und muss anschließend gegen beabsichtigte Recipe-/Toolchain-Änderungen bewertet werden.

## CLI

```text
schauwerk fundus drift ASSET --build BUILD_DIGEST --json
schauwerk fundus reproduce ASSET --build BUILD_DIGEST --json
```
