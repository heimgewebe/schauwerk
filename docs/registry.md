---
id: schauwerk-registry
role: contract
status: active
doc_type: reference
title: Schauwerk registry
summary: Git-versioned source, project, surface, view, region, policy and publication declarations.
---

# Schauwerk registry

The registry is the declarative control plane for what Schauwerk may read, render, manage and publish. It does not replace source-system truth and it contains no provider credentials or private board identifiers.

## Collections

- `sources`: canonical, operational and derived source declarations.
- `projects`: project identity, lifecycle and source membership.
- `surfaces`: provider-neutral preview, artifact and board targets.
- `views`: purpose-bound projections with source and audience bindings.
- `regions`: explicit managed or read-only portions of a surface.
- `policies`: mutation requirements and permitted operation classes.
- `publications`: draft or released output declarations.

Every collection is sorted by `id`, schema-validated and cross-reference checked. Surface aliases must be unique. Source dependencies, project/view source references, view/region surfaces, region policies and publication views must resolve.

## Inspect

```bash
schauwerk registry status --json
schauwerk registry show views --json
schauwerk registry show views grabowski.operator-overview --json
```

`registry status` returns counts, ordered identifiers and a deterministic digest over the complete validated registry.

## Mutation boundary

Registry declarations authorize no provider mutation by themselves. A Miro write still requires an allowlisted local board alias, a typed region plan, preflight, before snapshot, applicable policy, verification and restore evidence.
