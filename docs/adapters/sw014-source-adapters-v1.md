---
id: schauwerk-sw014-adapters
role: specification
status: active
doc_type: documentation
title: SW-014 Source Adapters v1
summary: Strict provider-neutral observation states for local Schauwerk tools.
---

# SW-014 Source Adapters v1

The local SW-014 adapter foundation ensures that external provider effects and data extraction fail cleanly and predictably, producing normalized Schauwerk observations. Every adapter execution outputs an `adapter-observation.v1` object with a strict state enum and deterministic payload digests.

## Core concepts

- **Healthy**: The provider returned the requested resource completely. The adapter normalized it into the expected payload structure.
- **Stale**: The provider could not be reached or timed out, but a previously verified offline payload could be returned without modification. This prevents transient network issues from destroying offline-first workflows.
- **Partial**: The provider returned some but not all of a bulk request. An explicit `error_code` marks the gap while preserving the partial payload for offline use.
- **Failed**: The provider failed completely and no stale fallback could be provided. The payload is `null` and an `error_code` is required.

## Deterministic verification

Adapter payloads must not contain arbitrary timestamp or machine-bound values. The `payload_digest` is a strict `sha256` computed over the canonical JSON byte representation of the payload.

## CLI commands

Adapters are integrated into the local Schauwerk CLI. Currently, the local fixture generator is exposed:

```bash
schauwerk adapter fixture --status healthy
schauwerk adapter fixture --status stale
schauwerk adapter fixture --status partial
schauwerk adapter fixture --status failed
```

Live provider connections remain roadmap work.
