---
id: schauwerk-architecture
role: norm
status: proposed
doc_type: architecture
title: Schauwerk architecture
summary: System boundaries, components, data model, and invariants.
---

# Schauwerk architecture

## Purpose

Schauwerk is the visual work, projection, and publication layer between authoritative sources, Grabowski, collaborative surfaces, presentation outputs, and public artifacts. It manages views rather than replacing source truth.

## Core object: view

A view binds a purpose and audience to sources, a renderer, a visibility class, management rules, and freshness metadata. Content authority, interpretation, and layout authority are recorded separately.

## Components

- **core:** projects, views, sources, regions, proposals, publications, snapshots, and receipts.
- **registry:** Git-versioned declarations with stable identifiers and schema validation.
- **sources:** adapters for Git/GitHub, Lenskit, Cabinet, Vault, Leitstand, Chronik, and optional semantic services.
- **compiler:** turns source packages and templates into proposed view plans.
- **surface adapters:** Miro first; later HTML, SVG, PowerPoint, Mermaid, and Obsidian Canvas.
- **snapshot:** normalizes external surfaces into deterministic comparable state.
- **diff:** semantic, structural, visual, provenance, and visibility comparisons.
- **operator:** `plan → preflight → snapshot → apply → verify → receipt → optional restore`.
- **regie:** human review surface for proposals, sources, diffs, approvals, verification, and restore.
- **web:** project overview, live views, search, embeds, publications, and archive access.
- **publish:** sanitization and immutable publication bundles.
- **archive:** snapshots, exports, previews, retention, and restore points.
- **observability:** health, OAuth state, provider reachability, freshness, jobs, and failures.

## Region modes

- `manual`: human-owned layout and content.
- `cooperative`: shared human and agent editing.
- `suggest-only`: agent may produce proposals only.
- `approval-required`: mutations require explicit approval.
- `managed`: agent may maintain the declared region.
- `read-only`: projection from an authoritative source.
- `public-copy`: sanitized derivative for external use.

## Primary flows

### Read and compare

1. Resolve the view and its source versions.
2. Read the provider surface.
3. Normalize the surface snapshot.
4. Compare source package, registry declaration, and surface state.
5. Report freshness and drift without mutation.

### Controlled mutation

1. Compile a proposed change.
2. Check board, team, view, and region allowlists.
3. Require the expected source and surface revisions.
4. Capture a pre-change snapshot.
5. Apply typed operations.
6. Read the surface again.
7. Verify postconditions and idempotency markers.
8. Emit an audit receipt or restore the snapshot.

### Publication

1. Start from a private or shared view revision.
2. Build a publication preview.
3. remove excluded fields, secrets, and personal data.
4. Validate the target audience and policy.
5. Create an immutable publication bundle.
6. Publish a read-only surface or static export.
7. Record version, source revisions, and withdrawal metadata.

## Data ownership

- Domain content remains authoritative in source systems.
- Schauwerk owns view identity, source bindings, management policy, freshness, proposals, normalized snapshots, publications, and receipts.
- Miro owns its native collaborative layout and interaction state.
- Grabowski owns execution planning, bounded mutation, verification, and recovery orchestration.
- Leitstand may display operational state but does not mutate Schauwerk.

## Security and privacy

Visibility classes are `private`, `shared`, `classroom`, `public`, and `archived`. Private work surfaces are never exposed by filtering a public embed. Public output is a distinct sanitized artifact. OAuth material and private snapshots remain outside Git. Student and other personal data are excluded from public fixtures and outputs by default.

## Provider strategy

Miro is the first collaborative surface. The direct adapter must use OAuth 2.1 with PKCE, restrictive local credential storage, token refresh, MCP Streamable HTTP, pagination, rate-limit handling, and board/team allowlists. Productive access must not depend on a model quota.

## Deployment shape

Initial operation is local on heim-pc with a Python CLI, filesystem registry, SQLite cache/index when needed, and a loopback-bound web surface. A later persistent internal or public deployment may run on heimserver after publication and access-control gates are proven.

## Non-goals

Schauwerk does not initially implement a whiteboard engine, CRDT collaboration, general project management, chat, video calls, universal ontology, or event-level replication of every board interaction.

## Invariants

1. Every managed statement has a source or is visibly marked as interpretation.
2. Every productive mutation has an expected base revision and pre-change snapshot.
3. A second identical apply creates no duplicates.
4. Managed operations cannot touch undeclared regions.
5. Public artifacts contain no undeclared private source material.
6. Provider failure does not erase the registry, source bindings, or archive.
7. Optional semantic enrichment cannot block the core workflow.
