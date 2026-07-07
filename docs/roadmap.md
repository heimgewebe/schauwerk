---
id: schauwerk-roadmap
role: plan
status: active
doc_type: roadmap
title: Schauwerk roadmap
summary: Phased implementation plan with gates from foundation to durable operation.
---

# Schauwerk roadmap

## Delivery principle

Every phase must produce a usable verified increment. Later integrations may not become prerequisites for earlier core workflows.

## SW-000 — Architecture and contracts

Deliver architecture, ownership boundaries, visibility model, region modes, versioned schemas, registry validation, and three pilot definitions.

**Gate:** every stored field and artifact has an authority, visibility class, and owner.

## SW-001 — Direct Miro MCP client

**Implementation status:** complete; live Miro authorization and tool discovery were accepted against the `Dev team` Miro workspace during SW-002 live acceptance.

Implement OAuth 2.1 with PKCE, restrictive credential storage, refresh, Streamable HTTP, tool discovery, health diagnostics, and team/server binding.

**Gate:** the tool catalogue is available without invoking a model.

## SW-002 — Read-only Miro snapshot

**Implementation status:** complete; owner-only board allowlisting, cursor/offset pagination, duplicate-reference detection, sanitized canonical snapshots, symlink-safe output, and a two-read content-and-pagination repeatability gate exist. Live acceptance passed against the isolated `sw002-fixture` board with 4 items, 1 comment, stable item/comment pagination, owner-only artifact mode, and no board URL leakage.

Read one allowlisted board with pagination, frames, elements, layout information, and supported comments. Normalize data into a stable snapshot.

**Gate:** two reads of an unchanged board produce the same normalized state.

## SW-003 — Isolated write proof

**Implementation status:** partial; marker planning, safe failure receipts, typed region receipt chains, a fixture-only SW-003 closeout receipt, and a local live-gate evidence evaluator exist. Live Miro closeout acceptance remains open. See `docs/operators/sw003-sw009-planhygiene.md`.

Create a clearly marked test frame, create and update test elements, verify IDs and state, prove idempotency, and remove or archive only the identified test scope.

**Gate:** create, read, update, verify, and cleanup are reproducible.

## SW-004 — Registry foundation

Complete project, view, source, surface, publication, region, and policy contracts. Add CLI inspection and deterministic validation.

**Gate:** the full registry validates in CI and contains no provider credentials.

## SW-005 — Grabowski pilot

Build system architecture, capabilities, hosts, runtime state, current work, and known-gap views from real sources.

**Gate:** a useful Miro view can be reconstructed from declared sources and snapshots.

## SW-006 — Second software pilot

Apply the model to a separate active software project with components, decisions, roadmap, pull requests, tests, and risks.

**Gate:** templates and data contracts are not Grabowski-specific.

## SW-007 — Education pilot

**Implementation status:** partial; Learning View v1 renders structured peer-facing topic files into deterministic current Miro DSL. Direct managed board updates, projected variants, assignments, exports, and offline packages remain open.

Produce teacher view, projected lesson view, assignment, student-facing view, presentation, and offline package without personal data.

**Gate:** the system works for a non-software use case.

## SW-008 — Visual grammar and templates

Define semantic shapes, state markers, provenance, freshness, uncertainty, accessibility, layout rules, and templates for overview, architecture, decision, roadmap, timeline, lesson, presentation, and public summary.

**Gate:** views are recognizable as one system without becoming visually uniform.

## SW-009 — Typed operator

**Implementation status:** partial.

Implemented:

- typed region plan, preflight, apply scaffold, and live-safe apply gating;
- fixture-only and CLI-backed apply receipts;
- fixture-only and CLI-backed operation contracts;
- fixture-only and CLI-backed apply simulation receipts;
- fixture-only and CLI-backed postflight/restore receipts.

Command graph:

- fixture apply path: `preflight → apply-scaffold → apply-receipt → postflight → restore-receipt`;
- simulation contract path: `preflight → apply-scaffold → operation-contract → apply-simulation`.

The simulation contract path now has a restore-ready postflight bridge via `simulation-postflight` and full CLI coverage through `restore-receipt`; the live typed apply path remains blocked by the SW-003 live-gate boundary.

Related blocker: SW-003 closeout proof.

Current SW-009 safety boundary: fixture and simulation paths may proceed from a ready preflight, but live typed apply stays blocked until SW-003 live-gate evidence exists.

Implement proposals, preflight, expected revisions, snapshots, typed operations, postflight reads, verification receipts, idempotency, and restore.

**Gate:** productive writes cannot touch undeclared regions or silently create duplicates.


## SW-010 — Regie

Build a local review interface for context, sources, instructions, proposed changes, semantic and visual diffs, partial approval, apply, verification, and restore.

**Gate:** normal controlled changes require no terminal knowledge.

## SW-011 — Overview and live views

Provide project navigation, freshness, active jobs, provider health, embedded surfaces, publications, errors, and fullscreen displays.

**Gate:** diagnostics remain useful when Miro is unavailable.

## SW-012 — Bühne

Generate presentation order, speaker notes, timing, target variants, PDF, PowerPoint, HTML, handout, and offline packages.

**Gate:** one technical and one education presentation work live and offline.

## SW-013 — Schaufenster

Implement publication preview, privacy checks, sanitized immutable bundles, stable links, version metadata, expiry, withdrawal, and read-only delivery.

**Gate:** no private source content appears without an explicit publication declaration.

## SW-014 — Source adapters

Add in order: Git/GitHub, Lenskit, Cabinet, Vault, Obsidian Bridge, Leitstand, Chronik, and optional semantic enrichment. Each adapter declares authority, freshness, errors, fixtures, and tests.

**Gate:** adapter failure is visible and cannot silently fabricate fresh data.

## SW-015 — Automated maintenance

Detect source changes, propose updates, maintain allowlisted regions, flag stale statements, collect open decisions, and generate focus and timeline views.

**Gate:** automation cannot mutate human-owned regions.

## SW-016 — Search and semantics

Add cross-project search, relationship suggestions, clustering, similar views, orphan detection, and contradiction hints.

**Gate:** semantic services remain optional and non-blocking.

## SW-017 — Operations and recovery

Add systemd operation, health checks, metrics, backup, retention, restore drills, OAuth rotation, kill switch, incident runbooks, and deployment profiles.

**Gate:** provider outage, token loss, and faulty bulk mutation have tested recovery paths.

## Release levels

### Foundation
SW-000 through SW-004.

### Useful pilot
SW-005 through SW-010.

### Product surface
SW-011 through SW-013.

### Integrated and durable
SW-014 through SW-017.

## Explicit non-goals for the first releases

No whiteboard engine, CRDT server, chat, video, universal ontology, general project-management suite, unreviewed automatic publication, or event-level replication of cursor and layout movements.
