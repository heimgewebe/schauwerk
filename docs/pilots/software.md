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

```bash
schauwerk pilot software path/to/input.json \
  --snapshot-output build/software-snapshot.json \
  --dsl-output build/software-overview.dsl \
  --json
```

## Authority boundary

The referenced repository remains authoritative. The snapshot records its exact revision and the input digest, contains no credentials or personal data, and performs no provider mutation. Live GitHub state must be refreshed into a new reviewed input rather than being silently treated as current.

## Lenskit acceptance proof

The first non-Grabowski acceptance proof is committed under `docs/operators/evidence/lenskit-pilot-20260710/`. It binds Lenskit revision `0ec3cf2938a6bb000a6e397a9d347ce781b9e3f2`, its architecture and roadmap contracts, merged work, required validation workflows and explicitly open risks.
