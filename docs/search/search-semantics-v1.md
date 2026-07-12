---
id: schauwerk-search-semantics-v1
role: norm
status: active
doc_type: search
title: Search and semantics v1
summary: Optional local cited search and deterministic suggestions constrained by visibility.
---

# Search and semantics v1

SW-016 builds a local index from validated source observations. It has no model, embedding service or network dependency.

Search results are returned only when the requested visibility scope may see the indexed fact. Each result retains source identity, freshness, effective authority, evidence citations and its digest. A public request cannot retrieve shared or private material.

The optional suggestion compiler emits:

- relationships when visible sources share a fact key and value;
- contradictions when visible sources share a fact key but disagree;
- orphans when a visible fact has no peer.

Suggestions include confidence and evidence. They remain hints, never source facts. A disabled or degraded index returns visible errors with `core_blocked=false`, so normal rendering and operation continue.

```text
schauwerk durable search-index observations.json --created-at 2026-07-12T09:20:00Z --output index.json --json
schauwerk durable search-query index.json architecture --visibility shared --json
schauwerk durable search-suggest index.json --visibility private --json
```
