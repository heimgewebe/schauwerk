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
9. [SW-003 live proof evidence](operators/evidence/sw003-live-proof-20260709/README.md)
10. [Registry](registry.md)
11. [Grabowski useful pilot](pilots/grabowski.md)
12. [Grabowski pilot evidence](operators/evidence/grabowski-pilot-20260710/README.md)
13. [Grabowski operational pilot](pilots/grabowski-operational.md)
14. [Grabowski operational evidence](operators/evidence/grabowski-operational-20260710/README.md)
15. [Generic software pilot](pilots/software.md)
16. [Lenskit software-pilot evidence](operators/evidence/lenskit-pilot-20260710/README.md)
17. [Ecosystem Map HTML Handoff](ecosystem-map-handoff.md)

## Contracts

- `schemas/source.v1.schema.json`
- `schemas/project.v1.schema.json`
- `schemas/surface.v1.schema.json`
- `schemas/view.v1.schema.json`
- `schemas/region.v1.schema.json`
- `schemas/policy.v1.schema.json`
- `schemas/publication.v1.schema.json`
- `schemas/grabowski-operational-observation.v1.schema.json`
- `schemas/software-pilot-input.v1.schema.json`
- `registry/`

## Current status

The repository is in useful-pilot expansion phase. Direct Miro authorization, allowlisted snapshots, the controlled SW-003 live write proof, complete registry contracts, deterministic registry inspection, the first Learning View renderer, source-bound static and operational Grabowski projections, and a project-neutral second software pilot proven against Lenskit are implemented. SW-009 now has simulation, live-gate, and candidate-check receipts; actual productive live apply remains a separate approval-required operation with postflight, restore, and review. Education variants, Regie, publication, live maintenance, search and durable recovery surfaces remain roadmap work.
