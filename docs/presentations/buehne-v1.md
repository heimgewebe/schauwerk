---
id: schauwerk-buehne-v1
role: contract
status: active
doc_type: operator-guide
title: SW-012 Bühne v1
summary: One validated presentation model produces separated public and presenter packages.
---

# SW-012 Bühne v1

## Purpose

Bühne turns one declared presentation model into consistent public presentation artifacts and a separate internal presenter package. The renderer is local and performs no network or provider operation.

Public outputs:

- `index.html` — offline slideshow;
- `presentation.pdf` — one scene per landscape page;
- `presentation.pptx` — deterministic 16:9 PowerPoint;
- `handout.html` — printable public handout;
- `manifest.json` — source revision, scene order, public projection digest and file digests.

Presenter outputs:

- `presenter.html` — speaker view;
- `presenter.json` — exact notes, timing and source visibility;
- `manifest.json` — model digest, scene order, total time and file digests.

## Canonical model

The contract is `schemas/presentation.v1.schema.json`. Runtime validation is stricter than structural JSON Schema validation.

A model declares:

- stable presentation ID and semantic version;
- source revision;
- source artifacts with repository-relative path, visibility, revision and SHA-256;
- output profiles;
- audience variants with explicit scene order;
- visible scene blocks;
- separate speaker notes;
- exact per-scene and aggregate timing.

Every visible block cites at least one declared `public` source. An `internal` or `private` source may support presenter guidance, but cannot be referenced by visible content. Declared source bytes are checked against their digest before rendering.

## Security boundary

The public and presenter destinations must be disjoint. Both are rendered into temporary sibling directories and renamed only after all checks pass.

The public package rejects:

- speaker-note or timing fields;
- note text found in public bytes or uncompressed PowerPoint XML;
- external HTML assets or executable scripts; generated HTML also carries a restrictive offline CSP;
- PowerPoint external relationships or note slides;
- PDF links and embedded files;
- absolute source paths, network URLs, provider identifier assignments and secret-like values in model text.

Public artifacts contain public source labels, source revisions and digests, but no source artifact paths. The presenter package may list internal source labels and visibility, but also omits artifact paths.

Generated public directories use mode `0755` and files `0644`. Generated presenter directories use `0700` and files `0600`. Git cannot preserve owner-only read modes for checked-in fixtures, so fixture presenter content must remain synthetic and non-sensitive.

## Determinism

The public projection digest is calculated only from visible content, public source metadata, scene order and declared variant metadata. Changing notes or timing therefore does not silently change the public projection identity.

PDF generation uses invariant document metadata. PowerPoint core timestamps are fixed and the Open XML ZIP is rewritten with sorted members and fixed member timestamps. Rebuilding the same model against the same source bytes yields byte-identical files.

## Command

```bash
schauwerk stage build path/to/model.json \
  --variant technical \
  --public-dir /tmp/stage-public \
  --presenter-dir /tmp/stage-presenter \
  --source-root . \
  --json
```

Output directories must not already exist. `--source-root` is the root against which source artifacts are resolved and digest-checked.

## Failure behaviour

The command fails closed and removes temporary or partially renamed outputs when:

- the model contains missing or unknown fields;
- a source is absent, symlinked, outside the source root, oversized or digest-mismatched;
- visible content cites a non-public source;
- scene order contains unknown or duplicate IDs;
- declared total time differs from the sum of scene times;
- public and presenter destinations overlap or already exist;
- a renderer produces an invalid PDF or PowerPoint structure;
- a public artifact contains notes, timing, external relationships or executable/external HTML.

No previous destination is overwritten.

## Limits

- v1 supports text, bullet, callout and code blocks; images and video are deliberately absent.
- PDF and PowerPoint use deterministic built-in layout rather than arbitrary templates. Overfull scenes, overwide tokens and unsupported PDF glyphs fail instead of clipping or substituting content.
- The v1 PDF font boundary covers Windows-1252 text; broader Unicode requires a later embedded-font contract.
- The public HTML is keyboard-scrollable and semantically ordered, but v1 does not include a JavaScript presenter controller.
- Bühne packages artifacts; public delivery, expiry, withdrawal and stable links belong to SW-013 Schaufenster.

## Acceptance fixtures

`docs/operators/evidence/sw012-buehne-20260711/` contains:

- a technical Grabowski operational brief;
- an education presentation about children's rights;
- public HTML, PDF, PowerPoint and handout outputs;
- separated synthetic presenter packages;
- deterministic manifests and acceptance evidence.
