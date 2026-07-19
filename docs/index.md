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
7. [Visual System v2](visual/schauwerk-visual-system-v2.md)
8. [Visual System v2 live reference](operators/visual-system-v2-live.md)
9. [Representation Router v1](plans/schauwerk-representation-router-v1.md)
10. [Miro live recovery](operations/miro-live-recovery.md)
11. [Typed Region Plan v1](operators/typed-region-plan-v1.md)
12. [SW-009 reviewed live executor v1](operators/sw009-live-executor-v1.md)
13. [SW-010 Regie v1](operators/sw010-regie-v1.md)
14. [SW-010 Regie evidence](operators/evidence/sw010-regie-20260711/README.md)
15. [SW-011 overview and live views v1](operators/sw011-overview-live-v1.md)
16. [SW-011 overview evidence](operators/evidence/sw011-overview-live-20260711/README.md)
17. [SW-012 Bühne v1](presentations/buehne-v1.md)
18. [SW-012 Bühne evidence](operators/evidence/sw012-buehne-20260711/README.md)
19. [SW-013 Schaufenster v1](publications/schaufenster-v1.md)
20. [SW-013 Schaufenster evidence](operators/evidence/sw013-schaufenster-20260711/README.md)
21. [SW-014 source adapters v1](integration/source-adapters-v1.md)
22. [SW-015 automated maintenance v1](operations/automated-maintenance-v1.md)
23. [SW-016 search and semantics v1](search/search-semantics-v1.md)
24. [SW-017 durable operations v1](operations/durable-operations-v1.md)
25. [SW-017 incident runbooks](operations/incidents/durable-runbooks-v1.md)
26. [SW-003 / SW-009 plan hygiene](operators/sw003-sw009-planhygiene.md)
27. [SW-003 controlled live proof plan](operators/sw003-controlled-live-proof-plan.md)
28. [SW-003 live proof evidence](operators/evidence/sw003-live-proof-20260709/README.md)
29. [Registry](registry.md)
30. [Grabowski useful pilot](pilots/grabowski.md)
31. [Grabowski pilot evidence](operators/evidence/grabowski-pilot-20260710/README.md)
32. [Grabowski operational pilot](pilots/grabowski-operational.md)
33. [Grabowski operational evidence](operators/evidence/grabowski-operational-20260710/README.md)
34. [Generic software pilot](pilots/software.md)
35. [Lenskit software-pilot evidence](operators/evidence/lenskit-pilot-20260710/README.md)
36. [Education variants evidence](operators/evidence/education-variants-20260710/README.md)
37. [Visual Grammar evidence](operators/evidence/visual-grammar-20260711/README.md)
38. [SW-009 live-executor evidence](operators/evidence/sw009-live-executor-20260711/README.md)
39. [Ecosystem Map HTML Handoff](ecosystem-map-handoff.md)
40. [Miro capability atlas v1](operators/miro-capability-atlas-v1.md)
41. [Miro managed image lifecycle v1](operators/miro-managed-image-lifecycle-v1.md)
42. [Representation Delivery v1](operators/representation-delivery-v1.md)
43. [Visual Preview & Regression v1](operators/visual-preview-regression-v1.md)
44. [Miro Web SDK Companion v1](operators/miro-web-sdk-companion-v1.md)
45. [Miro Visual Truth v1](operators/miro-visual-truth-v1.md)
46. [Golden Compositions v1](visual/golden-compositions-v1.md)
47. [Operator-Ökosystem auf heim-pc](operators/operator-ecosystem-heim-pc-v1.md)

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
- `schemas/visual-system.v2.schema.json`
- `schemas/visual-board.v2.schema.json`
- `schemas/visual-quality.v2.schema.json`
- `schemas/visual-review.v2.schema.json`
- `schemas/representation-input.v1.schema.json`
- `schemas/miro-managed-image.v1.schema.json`
- `schemas/miro-managed-image-replace-receipt.v1.schema.json`
- `schemas/miro-managed-image-delete-receipt.v1.schema.json`
- `schemas/representation-delivery-check.v1.schema.json`
- `schemas/representation-delivery-receipt.v1.schema.json`
- `schemas/visual-preview.v1.schema.json`
- `schemas/visual-regression.v1.schema.json`
- `schemas/miro-mcp-tool-reference.v1.schema.json`
- `schemas/miro-web-sdk-companion-release.v1.schema.json`
- `schemas/miro-visual-truth-context.v1.schema.json`
- `schemas/miro-visual-truth-receipt.v1.schema.json`
- `registry/`

## Current status

The local product surface through SW-013, repository-level integrated/durable v1 contracts through SW-017, Visual System v2 in SW-018, the representation package in SW-019, package-bound Representation Delivery in SW-020 and deterministic offline visual preview/regression in SW-021 are implemented. The live-companion and visual-truth slice adds provider-reference drift reporting, a digest- and header-bound HTTPS companion release, authenticated-capture receipts and three distinct Golden Compositions. Public hosting, Miro Developer App registration, team installation and Web SDK OAuth remain explicit external gates. Productive writes remain operation-specific, sequential and non-atomic; provider rendering and human aesthetic acceptance remain separate evidence.
