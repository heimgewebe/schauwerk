---
id: schauwerk-source-adapters-v1
role: norm
status: active
doc_type: integration
title: Source adapters v1
summary: Local, deterministic source normalization with explicit authority and failure semantics.
---

# Source adapters v1

SW-014 defines a provider-neutral boundary between declared source material and Schauwerk views. The v1 implementation reads owner-supplied local JSON only. It does not contact GitHub, Systemkatalog, RepoGround, Miro or any other provider by itself.

## Adapter catalogue

The built-in catalogue contains `git`, `github`, `systemkatalog`, `repoground` and `generic`. Every adapter accepts only compatible Registry source kinds and authorities. The Registry remains the authority for source identity, visibility, freshness policy and dependencies.

## Observation contract

`schauwerk-source-observation.v1` records:

- adapter and Registry source identity;
- source authority and visibility;
- observation, expiry and evaluation times;
- `healthy`, `stale`, `partial` or `failed` state;
- scalar facts with citations and per-fact visibility;
- visible collection errors and deterministic digests.

Only a healthy observation is `current_usable`. Stale and partial facts are preserved for diagnosis but are downgraded to derived, non-fresh material. A failed observation cannot contain facts, citations or a freshness expiry. This prevents source failure from fabricating a fresh-looking state.

## Commands

```text
schauwerk durable adapter-catalog --json
schauwerk durable adapter-collect input.json --at 2026-07-12T09:00:00Z --output observation.json --json
schauwerk durable adapter-set observation-a.json observation-b.json --created-at 2026-07-12T09:00:00Z --output set.json --json
```

## External gate

Real collectors may prepare adapter inputs, but they require their own authority, transport, credential and freshness acceptance. Adding a collector does not grant mutation authority and does not make an optional source a prerequisite.
