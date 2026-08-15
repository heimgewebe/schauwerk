---
id: schauwerk-fundus-image-operations-v1
role: norm
status: active
doc_type: architecture
title: Schauwerk Fundus Image Operations v1
summary: Agent-facing contract for generated and edited reusable visual source masters.
---

# Schauwerk Fundus Image Operations v1

## Regel

Eine Bildoperation wird vor ihrer Ausführung als temporäre Skizze oder als Fundus-relevante Arbeit klassifiziert. Wiederverwendbare oder produktiv vorgesehene Bilder, Ornamente, Texturen, Illustrationen, Masken und Vektorgrafiken sind Fundus-relevant.

Fundus-relevante Arbeit folgt: `Image Brief → Source Master → ingest → Asset/Recipe → Build → technische Prüfung → Preview → visuelle Acceptance → immutable Package → Grabowski-Integration`. Ein Source Master ist noch kein Produktionsasset.

## Image Brief

Vor `generate` oder generativem `edit` wird ein JSON-Dokument nach `schauwerk-fundus-image-brief.v1` festgelegt. Es bindet Asset-ID, Operation, Quellrolle, gewünschte Outputrollen, Anforderungen, Verbote, Transformationssicherheit und Acceptance-Regeln.

Beispiel:

```json
{
  "schema_version": "schauwerk-fundus-image-brief.v1",
  "id": "botanical.laurel.corner.generate.v1",
  "intent": "reusable_asset",
  "asset_id": "botanical.laurel.corner",
  "family": "botanical.laurel",
  "operation": "generate",
  "source_role": "trace_source",
  "desired_output_roles": ["mask"],
  "requirements": [
    "transparent background",
    "clear organic silhouette",
    "natural irregularity",
    "high-resolution construction master"
  ],
  "forbidden": [
    "material texture",
    "drop shadows",
    "external text",
    "hard geometric repetition"
  ],
  "properties": {
    "mask_safe": true,
    "recolor_safe": true,
    "mirror_safe": false,
    "rotate_safe": false,
    "tile_safe": false
  },
  "acceptance": {
    "visual_review_required": true,
    "inheritance": "none"
  }
}
```

`schauwerk fundus brief FILE --json` validiert, digestiert und hinterlegt den Vertrag vor der Bildoperation als immutable Brief-Receipt. Ein `edit`-Brief bindet zusätzlich über `input_sha256` die exakt bereits ingestierte Eingangsrevision.

## Ingest-Gate

Generierte und generativ bearbeitete Source-Master werden mit `source_mode=generated` beziehungsweise `source_mode=edited` ingestiert und müssen `image_brief_sha256` binden. Der Brief muss bereits durch `fundus brief` vorbereitet worden sein. Bekannte Ursprünge wie `chatgpt-images:` und `openai-images:` werden als generativ erkannt; ein widersprüchlich als manuell deklarierter Modus wird fail-closed abgewiesen.

Der Ingest speichert den Brief unveränderlich unter seinem Digest. Assetmanifest, Ingest-Receipt und Build müssen denselben Brief-Digest tragen. Build, Drift, Reproduce, Acceptance und Package prüfen die Bindung erneut. Alte, unklassifizierte V1-Quellen bleiben les- und reviewbar; deutet ihr Origin eindeutig auf `chatgpt-images`, OpenAI/ImageGen oder einen vergleichbaren generativen Pfad, dürfen sie ohne historisch tatsächlich vorbereiteten Brief weder neu akzeptiert noch packaged werden. Ein fehlender historischer Brief wird niemals nachträglich erfunden.

## Bearbeitung und Acceptance

Ein generatives Edit erzeugt eine neue Source-Revision und benötigt einen `operation=edit`-Brief mit `input_sha256` der bereits ingestierten Eingangsrevision. Eine frühere visuelle Acceptance wird nicht vererbt. Nur deterministische, ausdrücklich im Recipe-Vertrag erlaubte Transformationen dürfen eine Acceptance nach gesonderter Regel erben.

Technische Gültigkeit und ästhetische Freigabe bleiben getrennt. Kein Unit-Test behauptet gestalterische Qualität.

## Cross-Repo-Grenze

Schauwerk erzeugt ausschließlich akzeptierte immutable Packages. Grabowski integriert sie unter Autorität des Zielrepos, einschließlich Konfliktprüfung, eigener Lane, Tests und visuellem Readback.
