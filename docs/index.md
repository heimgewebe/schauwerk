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
5. [Education variants and offline packages](education/variants-offline.md)
6. [Visual Grammar v1](visuals/miro-visual-grammar-v1.md)
7. [Miro live recovery](operations/miro-live-recovery.md)
8. [Typed Region Plan v1](operators/typed-region-plan-v1.md)
9. [SW-009 reviewed live executor v1](operators/sw009-live-executor-v1.md)
10. [SW-010 Regie v1](operators/sw010-regie-v1.md)
11. [SW-010 Regie evidence](operators/evidence/sw010-regie-20260711/README.md)
12. [SW-011 overview and live views v1](operators/sw011-overview-live-v1.md)
13. [SW-011 overview evidence](operators/evidence/sw011-overview-live-20260711/README.md)
14. [SW-012 Bühne v1](presentations/buehne-v1.md)
15. [SW-012 Bühne evidence](operators/evidence/sw012-buehne-20260711/README.md)
16. [SW-013 Schaufenster v1](publications/schaufenster-v1.md)
17. [SW-013 Schaufenster evidence](operators/evidence/sw013-schaufenster-20260711/README.md)
18. [SW-014 source adapters v1](integration/source-adapters-v1.md)
19. [SW-015 automated maintenance v1](operations/automated-maintenance-v1.md)
20. [SW-016 search and semantics v1](search/search-semantics-v1.md)
21. [SW-017 durable operations v1](operations/durable-operations-v1.md)
22. [SW-017 incident runbooks](operations/incidents/durable-runbooks-v1.md)
23. [SW-003 / SW-009 plan hygiene](operators/sw003-sw009-planhygiene.md)
24. [SW-003 controlled live proof plan](operators/sw003-controlled-live-proof-plan.md)
25. [SW-003 live proof evidence](operators/evidence/sw003-live-proof-20260709/README.md)
26. [Registry](registry.md)
27. [Grabowski useful pilot](pilots/grabowski.md)
28. [Grabowski pilot evidence](operators/evidence/grabowski-pilot-20260710/README.md)
29. [Grabowski operational pilot](pilots/grabowski-operational.md)
30. [Grabowski operational evidence](operators/evidence/grabowski-operational-20260710/README.md)
31. [Generic software pilot](pilots/software.md)
32. [Lenskit software-pilot evidence](operators/evidence/lenskit-pilot-20260710/README.md)
33. [Education variants evidence](operators/evidence/education-variants-20260710/README.md)
34. [Visual Grammar evidence](operators/evidence/visual-grammar-20260711/README.md)
35. [SW-009 live-executor evidence](operators/evidence/sw009-live-executor-20260711/README.md)
36. [Ecosystem Map HTML Handoff](ecosystem-map-handoff.md)

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
- `schemas/presentation.v1.schema.json`
- `schemas/publication-boundary.v1.schema.json`
- `schemas/source-observation.v1.schema.json`
- `schemas/source-observation-set.v1.schema.json`
- `schemas/maintenance-proposal.v1.schema.json`
- `schemas/search-index.v1.schema.json`
- `schemas/operations-health.v1.schema.json`
- `schemas/backup-manifest.v1.schema.json`
- `registry/`

## Current status

The local product surface through SW-013 and repository-level integrated/durable v1 contracts through SW-017 are implemented. Schauwerk now normalizes declared local source observations with visible failure state, compiles proposal-only maintenance for managed regions, provides cited visibility-aware local search and produces deterministic health, backup, staged-restore, OAuth-rotation and kill-switch-drill artifacts. Productive Miro writes remain operation-specific and require the existing review, authorization, apply, postflight and restore chain. Real collectors, scheduled maintenance, installed services, public hosting, live OAuth rotation, executed backups/restores and live recovery drills remain separate target-bound effects.
