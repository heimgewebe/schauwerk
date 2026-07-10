---
id: schauwerk-grabowski-pilot
role: guide
status: active
doc_type: runbook
title: Grabowski useful pilot
summary: Deterministic sanitized operator overview rendered from Grabowski's generated operator context.
---

# Grabowski useful pilot

The pilot consumes Grabowski's generated `operator-context.v1.json` as a declared derived source. It compiles a sanitized deterministic snapshot and a Miro-compatible DSL view containing capability categories, risk classes, policy mode, active profile and operating-protocol identity.

It deliberately excludes secret values, local paths, live runtime claims and provider identifiers. Rendering is local-only and never calls Miro.

```bash
schauwerk pilot grabowski \
  ../grabowski/docs/generated/operator-context.v1.json \
  --snapshot-output /tmp/grabowski-pilot/snapshot.json \
  --dsl-output /tmp/grabowski-pilot/operator-overview.dsl \
  --json
```

The committed acceptance evidence in `docs/operators/evidence/grabowski-pilot-20260710/` was generated from Grabowski `origin/main` commit `f149b944a6bf756a4a95f3aab7396c9877d20b1f`.

## Gate result

A useful Miro view can be reconstructed from declared registry sources and a digest-bound sanitized snapshot. Applying that DSL to the proposed `miro.grabowski-pilot` surface remains a separate approval-required SW-009 operation.

## Operational continuation

For time-bound host, runtime, work and gap observations, continue with [Grabowski operational pilot](grabowski-operational.md). The operational view consumes the static snapshot rather than duplicating or silently refreshing contract facts.
