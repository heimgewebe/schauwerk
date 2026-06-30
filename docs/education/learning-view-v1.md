---
id: learning-view-v1
role: contract
status: active
doc_type: contract
title: Learning View v1
summary: Topic-to-board source contract and rich Miro Visual Grammar renderer.
---

# Learning View v1

Learning View v1 turns a structured topic into deterministic Miro layout DSL for peer-facing explanation boards.

## Input shape

The source file is JSON or YAML and may contain either a top-level object or a `learn:` object.

Required fields: `topic`, `audience`, `guiding_question`, `goals`, `steps`.

Optional fields: `key_terms`, `materials`, `collaboration`, `check`, `author_role`, `privacy_note`.

## Rendering contract

The renderer uses `learning-view-v1-rich` from Miro Visual Grammar v1. It emits orientation, learning path, group work, structured concept support, and safety footer regions.

The output is deterministic for a given source file and no longer relies only on sticky notes:

- `FRAME` separates regions.
- `SHAPE` highlights the guiding question and privacy footer.
- `DOC` carries dense explanation guidance.
- `TABLE` carries goals and vocabulary.
- `STICKY` remains for short learning steps and quick peer notes.
- `CONNECTOR` makes learning flow and review relations explicit.

## CLI

```bash
schauwerk miro learn render demos/education/peer-learning.yml --output /tmp/peer-learning.dsl --json
schauwerk miro learn apply grabowski-demo demos/education/peer-learning.yml --json
```

## Live preflight

Before `learn apply`, run:

```bash
schauwerk miro status --live --json
```

Proceed only when `live.ok=true`. If `live.renewal_required=true`, renew the Miro login first.
