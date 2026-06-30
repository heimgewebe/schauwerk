---
id: miro-visual-grammar-v1
role: contract
status: active
doc_type: contract
title: Miro Visual Grammar v1
summary: Semantic primitive catalog and template rules for richer Miro boards.
---

# Miro Visual Grammar v1

Miro Visual Grammar v1 defines which visual primitive Schauwerk should choose before it emits layout DSL. The rule is semantic first: the renderer chooses the primitive that matches the job, not the item that is quickest to create.

## Primitive catalog

| Primitive | Role | Use when |
| --- | --- | --- |
| Frame | region | A board needs a bounded chapter, workspace, or projection area. |
| Banner / Shape | orientation | A leitfrage, thesis, warning, or status must be visible first. |
| Text | label | The board needs a heading, caption, or quiet explanatory label. |
| Sticky | short thought | A learner note, quick idea, or small step must stay lightweight. |
| Connector | relation | A cause, sequence, dependency, contrast, or evidence link must be explicit. |
| Doc | explanation | Longer instruction, source summary, worked example, or speaking note would overload a sticky. |
| Table | structured comparison | Roles, criteria, vocabulary, status, or argument maps need rows and columns. |
| Card | action item | A task, review item, or handoff needs ownership-like treatment. |
| Code Widget | technical evidence | Commands, config, or source snippets must remain reproducible. |
| Image | visual anchor | A screenshot, map, photo, or diagram source gives orientation faster than text. |
| Comment | review thread | Feedback or teacher notes should remain attached to an item. |
| Diagram | formal model | A flow, system relation, process, or decision tree is the object itself. |
| Prototype | interactive surface | A screen flow or clickable explanation is needed. |

## Learning View template

`learning-view-v1-rich` uses six regions: orientation, concept table, learning path, explainer doc, peer review, and safety footer.

Required invariants:

- The guiding question is visible at first glance.
- Longer explanations use `DOC`, not sticky notes.
- Structured comparisons use `TABLE`.
- Sticky notes are reserved for short learning actions.
- Relations are explicit `CONNECTOR` items.
- The privacy footer is always present.

## Current DSL boundary

The renderer may catalog primitives that the current Miro layout backend does not yet support directly. For Learning View v1, the emitted default set is deliberately conservative: `FRAME`, `SHAPE`, `TEXT`, `DOC`, `TABLE`, `STICKY`, and `CONNECTOR`.
