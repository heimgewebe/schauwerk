---
id: schauwerk-docs-index
role: router
status: active
doc_type: index
title: Schauwerk documentation
summary: Canonical reading path for architecture, roadmap, and decisions.
---

# Schauwerk documentation

## Canonical reading path

1. [Architecture](architecture/schauwerk.md)
2. [Roadmap](roadmap.md)
3. [Miro-first boundary decision](decisions/0001-miro-first-adapter-boundary.md)
4. [Learning View v1](education/learning-view-v1.md)
5. [Miro live recovery](operations/miro-live-recovery.md)
6. [Typed Region Plan v1](operators/typed-region-plan-v1.md)
7. [SW-003 / SW-009 plan hygiene](operators/sw003-sw009-planhygiene.md)
8. [SW-003 controlled live proof plan](operators/sw003-controlled-live-proof-plan.md)
9. [Ecosystem Map HTML Handoff](ecosystem-map-handoff.md)

## Contracts

- `schemas/project.v1.schema.json`
- `schemas/view.v1.schema.json`
- `schemas/publication.v1.schema.json`
- `registry/`

## Current status

The repository is in foundation plus Miro-pilot phase. Direct Miro authorization, allowlisted snapshots, isolated layout writes, and the first Learning View renderer are implemented. SW-003 remains open for live Miro acceptance; fixture-only closeout and the local live-gate chain are in place: requirements, sanitized non-claim template, evaluation receipt, status receipt, review packet, and loaders for the versioned receipts. This chain is local-only, non-closing, does not access or mutate Miro, and keeps live apply blocked. SW-009 remains the next safety-critical apply chain and must stay fixture/simulation-safe until a controlled SW-003 live proof is accepted. Larger Regie, publication, live-maintenance, and recovery surfaces remain roadmap work.
