---
id: schauwerk-automated-maintenance-v1
role: norm
status: active
doc_type: operations
title: Automated maintenance v1
summary: Proposal-first comparison of source observations without provider mutation.
---

# Automated maintenance v1

SW-015 compares two validated source-observation sets and produces a deterministic review bundle. It never invokes Miro or another renderer.

The compiler detects added, changed and removed facts, missing or non-healthy current observations and contradictions between healthy sources. Automatic proposals are permitted only for Registry regions whose management mode is exactly `managed`. Manual, cooperative, suggest-only, approval-required, read-only and public-copy regions are blocked before operations are emitted.

Every bundle records source-set and Registry digests, proposed operations, blocked scopes, contradictions and an explicit authority boundary:

```text
review_required = true
provider_effect_authorized = false
mutation_attempted = false
```

```text
schauwerk durable maintenance-propose previous.json current.json \
  --region grabowski.operator-overview.managed \
  --created-at 2026-07-12T09:15:00Z \
  --output proposal.json --json
```

A later accepted proposal must still pass the existing Regie, SW-009 live-plan, authorization, apply, postflight and restore chain. No scheduler or live apply is enabled by this contract.
