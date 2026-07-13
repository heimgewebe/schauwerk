---
id: generic-software-pilot
role: guide
status: active
doc_type: operator-guide
title: Generic software pilot
summary: Deterministic architecture, decision, roadmap, delivery and risk projection for declared software projects.
---

# Generic software pilot

`schauwerk pilot software` compiles a bounded JSON input into a deterministic snapshot and read-only Miro DSL. The renderer is project-neutral: project, view and source IDs come from the registry; component, decision, roadmap, work, test and risk fields use one shared contract.

The original four-column DSL remains the compatibility path:

```bash
schauwerk pilot software path/to/input.json \
  --snapshot-output build/software-snapshot.json \
  --dsl-output build/software-overview.dsl \
  --json
```

## Visual System v2 outputs

Visual System v2 adoption is opt-in. The same validated snapshot can also produce a narrative seven-frame board specification, its quality receipt and deterministic Miro DSL:

```bash
schauwerk pilot software path/to/input.json \
  --visual-spec-output build/software-visual-v2.json \
  --visual-quality-output build/software-visual-v2-quality.json \
  --visual-dsl-output build/software-visual-v2.dsl \
  --json
```

The sequence is cover, reading map, architecture, decisions, delivery, risks/tests and evidence. Long collections are visibly bounded: the board shows selected rows and an explicit omitted-item count while the full snapshot remains digest-bound. Rich tables and documents have a 900-character design-density limit. Release requires at least 90/100 and no blocker.

## Authority boundary

The referenced repository remains authoritative. The snapshot records its exact revision and the input digest, contains no credentials or personal data, and performs no provider mutation. Live GitHub state must be refreshed into a new reviewed input rather than being silently treated as current. The evidence frame states when only revisions are known and no observation timestamp is available.

## Acceptance proofs

The first non-Grabowski software-pilot proof is committed under `docs/operators/evidence/lenskit-pilot-20260710/`. It binds Lenskit revision `0ec3cf2938a6bb000a6e397a9d347ce781b9e3f2`, its architecture and roadmap contracts, merged work, required validation workflows and explicitly open risks.

The Visual System v2 adoption proof is under `docs/operators/evidence/sw019-visual-adoption-v1/`. It produces seven frames and passes the deterministic v2 quality gate with 100/100, no blocker and no warning. That score is not an aesthetic verdict and does not replace an authenticated live Miro review.
