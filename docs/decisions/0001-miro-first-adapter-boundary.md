---
id: decision-miro-first-adapter-boundary
role: norm
status: accepted
doc_type: decision
title: Miro-first with a provider boundary
summary: Use Miro as the first collaborative surface without making it the canonical data store.
---

# Decision: Miro-first with a provider boundary

## Context

Schauwerk needs a collaborative visual surface quickly. Miro already supplies mature spatial editing, comments, presentation frames, sharing, and an MCP interface. Rebuilding these capabilities would delay the useful product.

## Decision

Miro is the first collaborative surface provider. Schauwerk owns identities, source bindings, policies, normalized snapshots, proposals, verification receipts, publications, and recovery metadata. Domain sources remain authoritative.

The adapter boundary must permit later renderers such as HTML, SVG, PowerPoint, and Obsidian Canvas. Productive Miro calls are made by a direct local client rather than requiring a model invocation.

## Consequences

- Initial value arrives without building a whiteboard engine.
- Provider-specific limitations remain isolated in `surfaces/miro`.
- Local registries and snapshots reduce lock-in.
- Layout may be collaborative while content authority remains external.
- Public outputs must be separate sanitized artifacts.

## Revisit conditions

Reconsider the decision if Miro repeatedly blocks required automation, privacy requirements exclude relevant use cases, or maintaining the adapter costs more than operating an alternative surface.
