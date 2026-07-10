---
id: schauwerk-grabowski-operational-pilot
role: guide
status: active
doc_type: runbook
title: Grabowski operational pilot
summary: Bounded host, runtime, work and gap observations beside the versioned Grabowski contract.
---

# Grabowski operational pilot

The operational pilot combines two deliberately different evidence classes:

- the static, versioned Grabowski operator contract;
- a time-bound observation bundle for fleet reachability, runtime health, current work and Bureau-derived follow-ups, including blocked or repair-relevant gaps.

The distinction is visible in the rendered view. Static contract facts do not become live claims, and live observations do not become source truth.

## Observation contract

`grabowski-operational-observation.v1` contains exactly four channels:

| Channel | Registry source | Authority | Typical expiry |
|---|---|---|---:|
| Hosts | `grabowski.fleet-observation` | operational | 15 minutes |
| Runtime | `grabowski.runtime-observation` | operational | 5 minutes |
| Work | `bureau.grabowski-work-observation` | operational | 5 minutes |
| Gaps | `bureau.grabowski-gap-observation` | derived | 30 minutes |

Each channel declares `observed_at`, `stale_after_seconds`, collection status and a bounded summary. Unsupported fields fail closed. An unavailable source has no summary and carries only a safe error code.

The bundle never carries host aliases, IP addresses, raw command output, task titles, PR titles, URLs, credentials or provider object identifiers. Collection remains the responsibility of Grabowski, Bureau and GitHub operator paths; Schauwerk consumes only their sanitized summaries.

## Render

```bash
schauwerk pilot grabowski-operational \
  docs/operators/evidence/grabowski-pilot-20260710/snapshot.json \
  /path/to/operational-observation.json \
  --snapshot-output /tmp/grabowski-operational/snapshot.json \
  --dsl-output /tmp/grabowski-operational/operator-overview.dsl \
  --json
```

The compiler derives per-channel states:

- `healthy`: source is fresh, complete and its bounded domain checks are healthy;
- `partial`: collection is partial or observed host/runtime/work/gap state is degraded;
- `stale`: observation age exceeds its declared expiry;
- `unavailable`: collection failed and no summary is accepted.

The overall result is `healthy`, `degraded` or `unavailable`. A single unavailable channel degrades the view; only four unavailable channels make the complete operational view unavailable.

## Acceptance evidence

The committed evidence under `docs/operators/evidence/grabowski-operational-20260710/` was built from live checks on 2026-07-10. It records only counts and state classes. It reports a degraded state because one declared host was unreachable, runtime observation was partial and known gaps existed. No Miro call or provider mutation occurred.
