---
id: schauwerk-fundus-acceptance-inheritance-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Acceptance Inheritance v1
summary: Fail-closed inheritance of direct visual acceptance only across source- and output-identical deterministic builds.
---

# Schauwerk Fundus Acceptance Inheritance v1

## Zweck

Eine neue Recipe-Revision kann technische oder deklarative Änderungen enthalten, obwohl sie für dieselben gebundenen Quellen exakt dieselben Produktionsbytes erzeugt. In diesem engen Fall darf eine bereits erteilte visuelle Acceptance vererbt werden, ohne so zu tun, als hätte ein Mensch den neuen Build erneut visuell geprüft.

Die Vererbung ist **kein Ähnlichkeitsverfahren**. Es gibt keine Pixelheuristik, keinen perceptual hash, keine KI-Bewertung und keine Toleranzschwelle.

## Explizites Opt-in

Nur `schauwerk-fundus-recipe.v3` kann Vererbung erlauben. Der Recipe-Vertrag muss enthalten:

```json
{
  "acceptance": {
    "inheritance": "identical_sources_and_outputs_only"
  }
}
```

Recipe v1 und v2 erlauben keine Acceptance-Vererbung. Recipe v3 verwendet ansonsten denselben geordneten Operationsvertrag wie Composition v2 und erzeugt weiterhin Build v2.

## Harte Vererbungsbedingungen

Eine `schauwerk-fundus-acceptance.v2` darf nur erzeugt werden, wenn alle Bedingungen gleichzeitig erfüllt sind:

- Parent und Kandidat gehören zum selben Asset;
- Parent- und Kandidaten-Build sind verschiedene digestgebundene Builds;
- die Kandidaten-Recipe ist exakt an den Build gebunden und optiert per Recipe v3 ein;
- jede `generated`- oder `edited`-Kandidatenquelle besitzt weiterhin ihren exakt gebundenen Image Brief, und dieser erlaubt `acceptance.inheritance=deterministic_recipe_only`;
- die Parent-Acceptance ist eine **direkte** `schauwerk-fundus-acceptance.v3` mit `decision=accepted` und exakter Preview-v2- oder Family-Review-Bundle-Bindung;
- die normalisierten Source-Bindungen sind exakt identisch;
- die normalisierten Output-Bindungen sind in Reihenfolge und Inhalt exakt identisch.

Die Source-Bindung umfasst mindestens Rolle, SHA-256, Medientyp sowie vorhandenen `source_mode` und `image_brief_sha256`. Damit kann eine neue Source-Revision nicht erben, selbst wenn sie zufällig dieselben sichtbaren Bytes erzeugt. Für `generated` und `edited` gilt zusätzlich ein **doppeltes Opt-in**: dieselbe gebundene Source-Revision und derselbe Image-Brief-Digest sind Pflicht, und der exakt gebundene Brief muss `deterministic_recipe_only` erlauben. `inheritance=none` im Brief bleibt autoritativ und blockiert Recipe-v3-Vererbung.

Die Output-Bindung umfasst Rolle, Source-Rolle, Dateiname, Medientyp, SHA-256 und Bytegröße. Gleiche Bildbytes unter einer anderen semantischen Rolle oder einem anderen Produktionsdateinamen reichen deshalb nicht aus.

## Acceptance v2

Acceptance v2 ist ein technischer Vererbungsbeleg, keine neue visuelle Review-Behauptung. Sie enthält unter anderem:

- Kandidaten-Build-Digest;
- Kandidaten-Recipe-Digest;
- vollständige Output-SHA-256-Liste;
- direkten Parent-Build und dessen Acceptance-v3-Digest;
- Digests der normalisierten Source- und Output-Bindungen;
- `inheritance_basis=identical_sources_and_outputs_only`;
- den Operator, der die Vererbung ausgelöst hat;
- `inherited_by_identity_authenticated=false`.

Die Felder `reviewer` und `reviewed_at` werden bewusst nicht auf den Kandidaten übertragen. Der Parent bleibt die einzige direkte visuelle Review-Autorität.

## Keine Vererbungsketten

Eine neu erzeugte Acceptance v2 darf niemals Parent einer weiteren Vererbung sein und muss direkt auf eine Acceptance v3 zurückverweisen. Historische Acceptance v1 und ältere Acceptance-v2-Receipts bleiben lesbar, sind aber kein zulässiger Ursprung für neue Vererbung oder neue Produktionspackages. Dadurch bleibt die aktuelle visuelle Ursprungsauthorität in einem Schritt prüfbar und es entsteht keine neue transitive Kette aus technischen Annahmen.

## Revalidierung und Packaging

Beim späteren Laden einer Acceptance v2 prüft Fundus erneut:

- Acceptance- und Build-Digests;
- Output-SHA-256-Bindung;
- Parent-Acceptance als direkte historische v1 oder aktuelle v3; für neue Produktionszulassung ist ausschließlich v3 samt erneut geprüfter Acceptance-zu-Review-Bindung zulässig;
- Source- und Output-Gleichheit beider Builds;
- die gespeicherten Evidence-Digests;
- den Kandidaten-Recipe-Digest.

Erst danach darf ein Build mit der geerbten Acceptance packaged werden. Package v1/v2 muss dafür nicht neu versioniert werden, weil das Package bereits den exakten `acceptance_digest` bindet.

## Nichtbehauptungen

Acceptance Inheritance v1 beweist nicht, dass eine neue Source-Revision visuell gleichwertig ist, dass zwei unterschiedliche Renderings ästhetisch äquivalent sind oder dass ein Operator die Identität des ursprünglichen Reviewers authentifiziert hat. Es ersetzt keine visuelle Acceptance bei generativer oder gestalterischer Neuinterpretation. Ein generativer Source-Master mit `inheritance=none` darf auch bei byteidentischem deterministischem Folge-Build nicht über Recipe v3 freigegeben werden.
