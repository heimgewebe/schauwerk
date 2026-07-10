# AGENTS

## Purpose
Schauwerk is a Type B product/service repository for a visual work, projection, and publication layer. It turns authoritative sources into traceable views and controls mutations on external surfaces such as Miro.

## Read This First
1. `README.md`
2. `docs/index.md`
3. `docs/architecture/schauwerk.md`
4. `docs/roadmap.md`
5. `agent-policy.yaml`

## Canonical Sources
- `repo.meta.yaml`: repository identity and discovery contract
- `docs/architecture/schauwerk.md`: system boundaries and invariants
- `docs/roadmap.md`: implementation sequence and gates
- `schemas/`: versioned data contracts
- `registry/`: declared sources, projects, surfaces, views, regions, policies and publications

## Non-negotiable Boundaries
- Source systems remain authoritative for domain content.
- Miro is a surface provider, not the canonical store.
- Never commit OAuth tokens, board access tokens, secrets, or private board data.
- No productive surface mutation without snapshot, scope check, and verification.
- Public outputs are independent sanitized artifacts, not filtered live access to private surfaces.
- Human, cooperative, and managed regions must remain distinguishable.
- Semantic services are optional enrichments and must not block the core workflow.

## Current Scope
The repository is in useful-pilot foundation phase. Controlled Miro read/write primitives, registry inspection, Learning View rendering and deterministic pilot projections exist. Productive typed live apply, Regie, public deployment and automatic source synchronization remain gated by their roadmap contracts.

## Required Checks
Run `make validate`.

## Guarded Paths
- `schemas/`
- `registry/`
- `docs/architecture/`
- `docs/decisions/`
- `.github/workflows/`
- authentication and mutation code under `src/schauwerk/surfaces/` and `src/schauwerk/operator/`
- pilot source compilers under `src/schauwerk/pilots/`

## Forbidden Content
- OAuth credentials and refresh tokens
- Miro board access tokens
- unredacted private board snapshots
- student or other personal data in fixtures
- public artifacts derived from private content without a publication receipt
