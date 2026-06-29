---
id: grabowski-demo-board
role: demo
status: active
doc_type: demo
title: Grabowski demo board
summary: Deterministic Miro layout plan that demonstrates Schauwerk functionality on Grabowski.
---

# Grabowski demo board

This demo board shows how Schauwerk turns Grabowski source state into a controlled visual surface.

## Board sections

1. Sources: Git/GitHub, tasks, runtime state.
2. Safety contracts: allowlist, repeatable snapshots, marker-scoped write proof.
3. Surface: Miro as operator-facing map, review layer, receipt layer.
4. Control loop: inspect -> normalize -> plan -> write -> snapshot -> compare -> publish or rollback.

## Artifact

The layout DSL is stored at `demos/grabowski-board.dsl`.

## Live write status

The board write requires a renewed Miro authorization. Local credentials exist, but live MCP access currently requests login renewal.
