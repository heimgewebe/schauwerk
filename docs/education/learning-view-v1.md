---
id: learning-view-v1
role: contract
status: active
doc_type: contract
title: Learning View v1
summary: Minimal topic-to-board source contract and Miro DSL renderer.
---

# Learning View v1

Learning View v1 turns a structured topic into deterministic Miro layout DSL for peer-facing explanation boards.

## Input shape

The source file is JSON or YAML and may contain either a top-level object or a `learn:` object.

Required fields: `topic`, `audience`, `guiding_question`, `goals`, `steps`.

Optional fields: `key_terms`, `materials`, `collaboration`, `check`, `author_role`, `privacy_note`.

## Rendering contract

The renderer emits current Miro `layout_create` DSL with four regions: orientation, learning path, group work, and footer. The output is deterministic for a given source file.

## CLI

```bash
schauwerk miro learn render demos/education/peer-learning.yml --output /tmp/peer-learning.dsl --json
schauwerk miro learn apply grabowski-demo demos/education/peer-learning.yml --json
```
