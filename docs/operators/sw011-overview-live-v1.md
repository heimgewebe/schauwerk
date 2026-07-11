---
id: sw011-overview-live-v1
role: contract
status: active
doc_type: operator-contract
title: SW-011 Overview and live views v1
summary: Registry-backed read-only navigation and time-bound diagnostics that remain useful during provider outages.
---

# SW-011 Overview and live views v1

The overview is a read-only local control room. It joins canonical registry navigation with time-bound observations from local artifacts, SW-009 journals, Regie receipts and optional Miro health checks. It does not create a second authoritative status database.

## Phase in plain language

The overview answers five questions:

1. Which projects and views exist?
2. Which declared artifacts and publications are present?
3. Which local transactions or Regie reviews are still active?
4. How recent is each observation and where did it come from?
5. What remains diagnosable when Miro is unavailable?

Registry data answers navigation questions. Every changing fact is a separate observation with source, observation time, freshness, severity and error state.

## Data boundaries

- Registry files remain the canonical truth for projects, views, surfaces and publications.
- File existence and modification time are observations, not registry mutations.
- SW-009 journals and Regie receipts are validated before they become active-job projections.
- Expired Regie authorizations are projected as `authorization-expired`, never as an actionable approval.
- Corrupt local receipt chains become bounded failure entries instead of aborting the entire snapshot.
- Miro health is optional and read-only. The default path uses the cached sanitized health receipt.
- `--probe-provider` performs a current read-only provider check; exceptions are converted into an error observation.
- Provider failure never removes registry navigation, publication state or local job evidence.
- Provider URLs, item identifiers, absolute local paths and credentials are excluded from snapshots and browser responses.
- Snapshots are digest-bound owner-only files with an 8 MiB input limit.
- Freshness is recomputed from `generated_at`, `observed_at` and fixed TTL rules; it cannot be relabelled by editing the JSON and recalculating only the outer digest.

## Snapshot command

```bash
schauwerk overview snapshot \
  --output overview.json \
  --json
```

This path performs no network call. To include a current read-only Miro probe:

```bash
schauwerk overview snapshot \
  --output overview.json \
  --probe-provider \
  --json
```

## Live view

```bash
schauwerk overview serve
```

The server binds only to `127.0.0.1`, is serial and exposes no mutation route. A session token is delivered through the URL fragment and retained in tab session storage. Private API reads require the token and a loopback `Host` header.

To make every refresh perform a current provider check:

```bash
schauwerk overview serve --probe-provider
```

## Display profiles

| Profile | Refresh | Fullscreen intent | Sections |
|---|---:|---|---|
| `operator` | 60 seconds | normal control room | all sections |
| `wallboard` | 30 seconds | large passive display | summary, observations, jobs, failures |
| `incident` | 15 seconds | focused incident display | summary, observations, jobs, failures |

Refresh is contractually bounded between 15 and 3600 seconds. Each profile also limits the number of rendered items per section. The browser offers an explicit Fullscreen API action; fullscreen is never forced silently.

## Freshness rules

- Observation TTL is declared per observation.
- Local jobs become stale after one hour.
- Artifact and publication files become stale after seven days.
- A timestamp later than the snapshot generation time is `unknown`, never `fresh`.
- Missing active artifacts and publications are errors.
- Missing draft publications are `unknown`, not errors.
- An expired publication must carry an expiry timestamp at or before snapshot generation.

## Failure semantics

- Provider exceptions are shown as provider errors while local diagnostics remain available.
- Invalid local transaction or Regie directories produce hashed failure references; raw directory names and paths are not exposed.
- Duplicate observation, job, publication, profile or failure identifiers invalidate the snapshot.
- Summary counts and provider state are recomputed from the detailed entries.
- The browser service accepts only `GET`; every `POST` returns `405 read-only service`.
- CSP, `no-store`, frame denial, MIME hardening and referrer suppression are enabled.

## Acceptance boundary

Repository acceptance uses a temporary fixture registry, fixed file timestamps, a fiktive active transaction, an expired Regie decision and a simulated provider outage. The resulting checked-in snapshot is deterministic and contains no current mutation authority or productive provider identifier.
