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

**Implementation status:** complete. SW-002 was historically accepted against the former `Dev team`. The current productive identity was re-authorized on 2026-07-12 for the Miro `Education team`; the active boards are organized in Space `Schauwerk`. Team and Space assignment remain provider/UI facts and are not inferred from OAuth files alone.

Implement OAuth 2.1 with PKCE, restrictive credential storage, refresh, Streamable HTTP, tool discovery, health diagnostics, and team/server binding.

**Gate:** the tool catalogue is available without invoking a model.

## SW-002 — Read-only Miro snapshot

**Implementation status:** complete; owner-only board allowlisting, cursor/offset pagination, duplicate-reference detection, sanitized canonical snapshots, symlink-safe output, and a two-read content-and-pagination repeatability gate exist. Live acceptance passed against the isolated `sw002-fixture` board with 4 items, 1 comment, stable item/comment pagination, owner-only artifact mode, and no board URL leakage.

Read one allowlisted board with pagination, frames, elements, layout information, and supported comments. Normalize data into a stable snapshot.

**Gate:** two reads of an unchanged board produce the same normalized state.

## SW-003 — Isolated write proof

**Implementation status:** complete; the controlled live Miro proof verified bounded create, read, update, marker uniqueness, idempotency and cleanup. Sanitized evidence is committed under `docs/operators/evidence/sw003-live-proof-20260709/`, and Issue #8 was closed on 2026-07-09. The evidence does not itself authorize unrelated live apply operations.

Create a clearly marked test frame, create and update test elements, verify IDs and state, prove idempotency, and remove or archive only the identified test scope.

**Gate:** create, read, update, verify, and cleanup are reproducible.

## SW-004 — Registry foundation

**Implementation status:** complete; source, project, surface, view, region, policy and publication schemas are enforced in CI. Registry collections are ID-sorted, cross-reference checked, alias-unique, inspectable through `schauwerk registry`, and bound by a deterministic whole-registry digest.

Complete project, view, source, surface, publication, region, and policy contracts. Add CLI inspection and deterministic validation.

**Gate:** the full registry validates in CI and contains no provider credentials.

## SW-005 — Grabowski pilot

**Implementation status:** complete for the useful-pilot gate. `schauwerk pilot grabowski` renders the declared static operator contract. `schauwerk pilot grabowski-operational` adds bounded, expiring host, runtime, current-work and known-gap observations while keeping source authority, stale state and collection failure explicit. Deterministic acceptance evidence is committed under `docs/operators/evidence/grabowski-pilot-20260710/` and `docs/operators/evidence/grabowski-operational-20260710/`. The resilient cross-project overview is complete in SW-011. Source collection now enters through the explicit SW-014 observation contract rather than being embedded in this pilot.

Build system architecture, capabilities, hosts, runtime state, current work, and known-gap views from real sources.

**Gate:** a useful Miro view can be reconstructed from declared sources and snapshots.

## SW-006 — Second software pilot

**Implementation status:** complete; `schauwerk pilot software` validates a project-neutral input contract, binds project, view and source IDs through the registry, and renders deterministic architecture, decision, roadmap, delivery, test and risk sections without provider mutation. Lenskit/RepoBrief is the first acceptance proof under `docs/operators/evidence/lenskit-pilot-20260710/`.

Apply the model to a separate active software project with components, decisions, roadmap, pull requests, tests, and risks.

**Gate:** templates and data contracts are not Grabowski-specific.

## SW-007 — Education pilot

**Implementation status:** complete; one normalized learning source now produces teacher, projection, assignment, student and presentation HTML variants plus a deterministic offline package. Audience visibility is explicit, assignment output requires instructions, resources and a submission boundary, and high-confidence personal-data fields, email addresses and phone values are rejected before rendering. The package has no network, script or Miro dependency.

Produce teacher view, projected lesson view, assignment, student-facing view, presentation, and offline package without personal data.

**Gate:** the system works for a non-software use case.

## SW-008 — Visual grammar and templates

**Implementation status:** complete; `schauwerk-visual-grammar.v1` defines renderer-independent semantic tokens, non-colour state markers, provenance, freshness and uncertainty contracts, contrast validation and distinct software, education, roadmap, timeline, presentation and public-summary template families. Software and education pilots use the same grammar while retaining different regions and audiences.

Define semantic shapes, state markers, provenance, freshness, uncertainty, accessibility, layout rules, and templates for overview, architecture, decision, roadmap, timeline, lesson, presentation, and public summary.

**Gate:** views are recognizable as one system without becoming visually uniform.

## SW-009 — Typed operator

**Implementation status:** complete for the reviewed live-executor contract. The existing typed plan, preflight, simulation, postflight and restore chain is now joined by a digest-bound live operation draft/compiler, expiring explicit authorization, atomic single-use transaction journal, required reviewed-plan equality, fresh provider-capability check, complete DSL coverage, verified before/after snapshots, exact managed-region replacements, per-operation result digests, semantic/idempotency postflight, automatic rollback, committed-journal binding, drift-protected restore and kill switch.

The productive boundary remains operation-specific: repository acceptance did not mutate a live Miro board and does not authorize future writes. Every live execution still requires a current allowlisted alias, expected revision, managed-region marker, reviewed bundle and explicit expiring authorization.

Command graph:

- proposal path: `preflight → live-apply-gate → live-bundle-template → live-bundle-compile`;
- authority path: `live-bundle + live-gate → live-authorization-create → live-plan`;
- transaction path: `live-plan inputs → live-apply → verified transaction receipt`;
- recovery path: `transaction receipt → drift check → inverse restore → restore receipt`;
- emergency path: `kill-switch enable/status/disable`.

Version 1 deliberately supports only unique exact-text replacements that preserve a managed-region marker. It does not expose free-form DSL, item creation or item deletion.

Implement proposals, preflight, expected revisions, snapshots, typed operations, postflight reads, verification receipts, idempotency, and restore.

**Gate:** productive writes cannot touch undeclared regions or silently create duplicates.

## SW-010 — Regie

**Implementation status:** complete for the local v1 contract. Regie compiles source-bound contexts and review bundles, projects freshness and uncertainty, renders exact before/after and inline diffs, records immutable approve/reject/defer decisions per operation, derives a new selected bundle plus expiring authorization and plan, and exposes separately confirmed apply, verification receipts and restore in one serial loopback interface.

The interface uses no external assets, requires a fragment-delivered tab session token for private APIs, validates loopback hosts, omits provider identifiers and local journal paths, and revalidates stored effect receipts before display or replay. Repository acceptance uses an expired fixture authorization and an in-memory provider; no productive Miro board was mutated.

Command graph:

- context path: `context-template → context-compile`;
- review path: `context + live gate + operation bundle → review`;
- decision path: `review → immutable per-operation decision → selected bundle + authorization + plan`;
- effect path: `explicit apply → visible postflight receipt`;
- recovery path: `same review context → explicit restore → restore receipt`.

**Gate:** normal controlled changes require no terminal knowledge.

## SW-011 — Overview and live views

**Implementation status:** complete for the read-only local v1 contract. A digest-bound overview snapshot joins Registry-backed project/view navigation with time-bound artifact, publication, SW-009 transaction, Regie session and Miro health observations. Provider probes are optional and read-only; exceptions become provider error facts while all local diagnostics remain available.

The serial loopback interface exposes no mutation route, uses fragment-delivered tab session tokens, supports explicit fullscreen, and declares bounded `operator`, `wallboard` and `incident` profiles with refresh intervals from 15 to 60 seconds. Freshness, summary counts, publication expiry and provider state are recomputed during validation rather than trusted as editable labels.

Command graph:

- offline path: `Registry + local receipts + cached health → overview snapshot`;
- current health path: `overview snapshot --probe-provider`;
- live path: `overview serve → repeated validated read-only snapshots`;
- display path: `operator | wallboard | incident → bounded sections and refresh`.

**Gate:** diagnostics remain useful when Miro is unavailable.

## SW-012 — Bühne

**Implementation status:** complete for the deterministic local v1 contract. One strict, source-bound presentation model now produces ordered public HTML, PDF, PowerPoint and handout artifacts plus a separate owner-only presenter package with notes and exact timing.

Public outputs expose only visible blocks and public source metadata. Internal source labels, speaker notes and timing remain in the presenter package. HTML has no external assets or scripts; PowerPoint has no notes slides or external relationships; PDF has no links or embedded files. Technical and education fixtures rebuild byte-identically without network access.

Command graph:

- validation path: `model + source digests → strict intermediate model`;
- public path: `intermediate model → HTML + PDF + PPTX + handout + manifest`;
- presenter path: `same intermediate model → notes + timing + private manifest`;
- acceptance path: `structure checks + leakage checks + deterministic rebuild`.

**Gate:** passed by one technical and one education presentation working offline.

## SW-013 — Schaufenster

Implement publication preview, privacy checks, sanitized immutable bundles, stable links, version metadata, expiry, withdrawal, and read-only delivery.

**Implementation status:** complete for the local provider-neutral v1 boundary. A strict declaration enumerates the exact public sources, allowed fields, source-manifest binding, file set, version and lifecycle. Release recompiles the reviewed preview, writes a read-only immutable version object, updates the stable link with digest-bound compare-and-swap, derives expiry without mutation and preserves the object during withdrawal. The loopback server exposes only verified active objects through `GET` and `HEAD`; public hosting remains a separately authorized later operation.

**Gate:** passed by a declaration-bound SW-012 technical package, adversarial private/unknown visibility cases, immutable release, idempotent retry, version replacement, expiry, withdrawal, link-race preservation, rollback and loopback read-only delivery.

## SW-014 — Source adapters

**Implementation status:** complete for the local provider-neutral v1 contract. Git, GitHub, Systemkatalog, Lenskit/RepoBrief and generic declared-local adapters compile Registry-bound observations with authority, visibility, observed/expiry/evaluation times, citations, errors and deterministic digests. Healthy, stale, partial and failed states are explicit; non-healthy facts cannot appear current or authoritative, and failed collection cannot emit facts.

Real transport collectors remain separate integrations. They require their own credentials, authority, error and freshness acceptance and may not silently make optional sources prerequisites.

**Gate:** passed by deterministic healthy, stale, partial, failed, visibility and tamper fixtures.

## SW-015 — Automated maintenance

**Implementation status:** complete for the local proposal-first v1 contract. Previous and current observation sets produce digest-bound added, updated and removed fact proposals, stale/missing-source blockers and contradiction evidence. Only Registry regions with management mode `managed` are eligible; all other ownership modes fail before operations. The compiler grants no provider authority and reports `mutation_attempted=false`.

Scheduling and accepted live effects remain external. Any accepted proposal must still pass Regie and the SW-009 authorization, apply, postflight and restore chain.

**Gate:** passed by managed, read-only, stale-source and contradiction fixtures.

## SW-016 — Search and semantics

**Implementation status:** complete for the optional local v1 contract. A deterministic cited index enforces visibility at query time and exposes freshness and effective authority. Local relationship, contradiction and orphan hints carry confidence and evidence. Disabled or degraded search returns visible errors with `core_blocked=false` and has no model or network dependency.

External embeddings or semantic services are optional future adapters, not a core dependency.

**Gate:** passed by visibility-isolation, citation, disabled-service and confidence/evidence fixtures.

## SW-017 — Operations and recovery

**Implementation status:** complete for the repository-level local v1 contracts. Deterministic role profiles, declared health aggregation, secret-excluding backup manifests, staged restore verification, no-token OAuth rotation plans, kill-switch drill receipts and incident runbooks are implemented. Symlinks, traversal and secret-like backup paths fail closed.

No service was installed and no live provider or host effect was performed. Scheduled services, executed backups, live restore, live OAuth rotation, public hosting and live kill-switch drills remain target-bound acceptance operations with their own receipts.

**Gate:** passed locally for profile determinism, required/optional health, backup integrity, staged restore mismatch, path safety, rotation boundaries and drill evidence. The operational gate remains open until the target-specific live exercises are authorized and recorded.

## SW-018 — Visual System v2

**Implementation status:** complete for the deterministic repository contract and reference renderer. Visual System v2 separates the semantic board specification, the quality gate and the Miro renderer. It assigns frames, shapes, connectors, tables, documents and sticky notes by information function; requires a finite reading path, one title and thesis per frame, a semantic five-role palette, consistent frame rhythm and at least 42 percent deliberate white space. Finished facts rendered as sticky notes, unseparated evidence, connector clutter and count-rich but narratively weak boards fail closed.

The canonical seven-frame reference board contains no sticky notes. It uses a cover, reading map, object-selection matrix, information-architecture model, quality gate, before/after synthesis and evidence appendix. Local release requires at least 90/100 and no blockers. Remote Miro readback proves the plan was created; aesthetic acceptance additionally requires an actual UI review because provider geometry can be incomplete.

Command graph:

- contract path: `visual system-v2 → versioned manifest`;
- compile path: `visual reference-v2 → board spec + quality receipt + Miro DSL`;
- live path: `quality gate → fresh allowlisted board → before snapshot → layout create → after snapshot → readback conformance`;
- review path: `rendered board → separate UI inspection → bounded visual review receipt`.

**Gate:** passed by adversarial narrative, object-misuse, density, connector and digest tests plus one new Education-team reference board with remote conformance and human-visible UI review.

## SW-019 — Representation Router v1

**Implementation status:** complete for the deterministic multi-renderer package. One normalized representation input selects Mermaid, JSON Canvas, Miro-native, document and table outputs with explicit reasons, coverage and nonclaims. All artifacts are digest-bound to the same input and route plan.

**Gate:** passed by deterministic rebuild, source-ID preservation, renderer coverage, Miro quality and adversarial input tests.

## SW-020 — Representation Delivery v1

**Implementation status:** complete for package-bound delivery through the existing Miro Native Executor. The runtime recomputes every deterministic artifact, rejects extra or semantically resigned changes, freezes the exact Native Bundle before provider contact, serializes one output through a nonblocking lock and binds provider postflight to an outer delivery receipt.

Provider operations remain sequential and non-atomic. Aesthetic acceptance remains a separate UI review. REST authorization and the managed image lifecycle remain separate provider boundaries.

**Gate:** passed by package-integrity, semantic-tamper, payload-freeze, lock, output-boundary, provider-readback and reconciliation tests.

## Release levels

### Foundation
SW-000 through SW-004.

### Useful pilot
SW-005 through SW-010.

### Product surface
SW-011 through SW-013.

### Integrated and durable
SW-014 through SW-017.

### Visually governed
SW-018 through SW-020.

## Explicit non-goals for the first releases

No whiteboard engine, CRDT server, chat, video, universal ontology, general project-management suite, unreviewed automatic publication, or event-level replication of cursor and layout movements.
