---
id: miro-visual-grammar-v1
role: contract
status: active
doc_type: contract
title: Schauwerk Visual Grammar v1
summary: Versioned renderer-independent semantic tokens, state cues, provenance and template rules.
---

# Schauwerk Visual Grammar v1

`schauwerk-visual-grammar.v1` is the common semantic layer for Miro DSL, static HTML and later publication or presentation renderers. Renderers may look different, but they must preserve the same meaning, state and source boundaries.

The canonical machine-readable manifest is produced with:

```bash
schauwerk visual grammar --output visual-grammar.json --json
```

## Semantic tokens

| Token | Meaning | Non-colour cue |
| --- | --- | --- |
| Orientation | entry point or primary question | `◆` and text label |
| Evidence | source-backed claim | `▣` and source wording |
| Decision | decision or trade-off | `◇` and decision label |
| Action | next or review action | `→` and action wording |
| Risk | risk, failure or blockade | `!` and risk wording |
| Source | provenance and revision | `↗` and source wording |
| Uncertainty | estimated or unresolved statement | `?` and uncertainty label |

Colour is never the only carrier of meaning. Every semantic token has a label, symbol, shape and text alternative.

## State markers

`healthy`, `partial`, `stale`, `failed`, `unavailable` and `unknown` each combine:

- a visible symbol;
- an explicit text label;
- a contrast-validated foreground and background;
- a severity rank for deterministic summaries.

Normal-text contrast must be at least `4.5:1`. Stored contrast receipts are recomputed during validation rather than trusted.

## Provenance, freshness and uncertainty

Every live or source-derived fact must expose:

- `source_id`;
- `revision`;
- `observed_at`;
- `freshness`;
- `uncertainty`.

Missing observation time cannot appear fresh. Derived or estimated claims remain labelled and cannot become source facts automatically. Unavailable sources must remain visible instead of disappearing from the view.

## Template families

The grammar defines separate templates for:

- software overview;
- education;
- roadmap;
- timeline;
- presentation;
- public summary;
- zoomable education map.

Each template has its own regions, audience, reading order and invariants. This gives the system a common visual language without forcing software architecture and classroom material into the same layout.

## Primitive catalog

| Primitive | Role | Use when |
| --- | --- | --- |
| Frame | region | A bounded chapter, workspace or projection area is needed. |
| Banner / Shape | orientation | A question, thesis, warning or status must be visible first. |
| Text | label | A heading, caption or quiet explanatory label is needed. |
| Sticky | short thought | A learner note, quick idea or small step must stay lightweight. |
| Connector | relation | Cause, sequence, dependency, contrast or evidence must be explicit. |
| Doc | explanation | Longer instruction or source explanation would overload a sticky. |
| Table | structured comparison | Roles, criteria, vocabulary or status need rows and columns. |
| Card | action item | A task, review item or handoff needs action treatment. |
| Code Widget | technical evidence | Commands, configuration or source snippets must remain reproducible. |
| Image | visual anchor | A screenshot, map, photo or diagram gives faster orientation. |
| Comment | review thread | Feedback should remain attached to an item. |
| Diagram | formal model | A process, flow or decision tree is the object itself. |
| Prototype | interactive surface | A screen flow or clickable explanation is required. |

## Current renderer boundary

The Miro layout backend currently emits the conservative subset `FRAME`, `SHAPE`, `TEXT`, `DOC`, `TABLE`, `STICKY` and `CONNECTOR`. HTML education output uses the shared education theme and accessibility contract. Unsupported primitives remain declared for later adapters and cannot be silently substituted with misleading semantics.
