---
id: sw012-buehne-evidence-20260711
role: evidence
status: active
doc_type: evidence
summary: Deterministic technical and education Bühne packages built offline from one model per presentation.
---

# SW-012 Bühne acceptance evidence

## Scope

This fixture set proves the local SW-012 v1 contract without a provider connection or network dependency.

- `technical/model.json` builds a five-scene, ten-minute Grabowski operational brief.
- `education/model.json` builds a six-scene, fifty-five-minute education presentation.
- each `public/` directory contains HTML, PDF, PowerPoint, handout and a deterministic public manifest;
- each `presenter/` directory contains separate synthetic notes, timing and an internal manifest.

## Boundaries

The source artifacts are repository-local and SHA-256-bound. The technical and education public packages contain no speaker-note or timing values, internal source metadata, external assets, provider identifiers, absolute local paths or secrets. No provider mutation was attempted.

The checked-in presenter fixtures are synthetic and carry no real private source content. Runtime package generation still applies owner-only directory and file modes.

## Acceptance checks

`acceptance-receipt.json` records:

- exact model and package manifest digests;
- source revision;
- scene count and exact aggregate timing;
- byte-identical repeated builds;
- equal public scene order and visible-content digest across HTML, PDF and PowerPoint metadata;
- absence of PowerPoint notes and external relationships;
- absence of PDF links and embedded files;
- absence of executable or external HTML resources;
- explicit offline and no-mutation boundaries.
- atomic no-replace publication, foreign-destination preservation and owned-output rollback.
- white PowerPoint header text on the dark header band, checked structurally and through LibreOffice export.

The repository tests independently rebuild temporary packages and test note leakage, path safety, destination isolation, deterministic bytes and format structure.
