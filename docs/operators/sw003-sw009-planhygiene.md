---
id: sw003-sw009-planhygiene
role: audit
status: active
doc_type: report
title: SW-003 / SW-009 plan hygiene
summary: Audit of the open SW-003 item against main and definition of the next typed-operator apply slice.
---

# SW-003 / SW-009 plan hygiene

## Purpose

This document prevents the roadmap from drifting into two equally bad states:

1. treating SW-003 as untouched even though main already contains several Miro live-test and mutation-adjacent primitives; or
2. treating SW-003 as closed before the live create/read/update/verify/cleanup gate has dedicated, sanitized evidence.

The practical decision is conservative: keep SW-003 open, but narrow it to the missing proof. The cat may sit on the keyboard; it does not thereby become a release manager.

## Evidence basis

Observed on 2026-07-03:

- Repository state before this branch: clean `main...origin/main`.
- Tracker state: one open SW-003 item, updated 2026-06-29.
- Recent main history includes Auth Refresh `#33`, Apply Scaffold `#32`, Region Preflight `#31`, Health History `#30`, and Auth Doctor `#29`.
- Current code contains SW-003 marker planning, verified snapshots, live learning-test orchestration, layout creation receipts, and typed region plan/preflight/apply-scaffold receipts.

This audit uses current repository state and tracker metadata. It does not assume that old tracker comments are authoritative after the recent merge chain.

## Resonance and contrast check

### Reading A — the SW-003 tracker item is stale

Plausible basis: main already has allowlisted board access, live layout creation, fresh learning tests, before/after snapshots, layout-read summaries, local test records, and quality receipts. That is not a blank SW-003 field.

Consequence if accepted too early: the roadmap would claim a safety gate that has not been separately closed. That would turn a useful live-test pipeline into an implicit operator license.

### Reading B — the SW-003 tracker item is still real

Plausible basis: the SW-003 gate says create, read, update, verify, and cleanup are reproducible. The current learning live-test path proves fresh-board creation plus layout application and verification-like receipts, but it does not yet provide a dedicated SW-003 closeout receipt for marked-scope create/update/idempotency/cleanup. Current live-test output also records that remote cleanup is not attempted.

Consequence if accepted: the item remains open, but must stop pretending that the runtime wrapper is the main missing item. The missing item is now the closeout proof.

### Synthesis

Keep SW-003 open. Rewrite its meaning from broad implementation task to closeout gate:

- dedicated SW-003 receipt;
- marked test scope only;
- create/read/update/verify/idempotency evidence;
- cleanup or explicit cleanup boundary;
- no provider identifiers or board links in public output.

## SW-003 status after audit

### Belegt

- Markers are constrained to the `schauwerk-sw003-YYYYMMDDTHHMMSSZ-xxxxxx` shape.
- A create/update marker plan exists locally.
- Live board creation exists for learning live tests.
- Layout creation returns a redacted receipt with created count, failure count, result DSL digest, and mutation flag.
- Snapshot runtime performs two reads and verifies content and pagination repeatability.
- Quality receipts can combine snapshot and layout-read structure counts.
- Live-test pruning currently handles local artifact records, not remote board deletion.

### Plausibel

- The existing Learning Live Test path can serve as the fixture basis for SW-003 closeout.
- The typed region preflight/apply-scaffold chain is the right safety rail before any broader write operation.

### Spekulativ / not yet proven

- That a specific SW-003 command can update exactly the previously created marked objects rather than creating a second equivalent layout.
- That idempotency is proven at object/scope level, not only by digest or successful layout application.
- That cleanup can be implemented remotely with the currently available Miro MCP toolset.

## Branch hygiene classification

No branch deletion is performed in this slice.

### Safe cleanup candidates after manual confirmation

These local branches are directly merged into main or are patch-equivalent squash-merge remnants:

- `docs/live-acceptance-status`
- `feat/sw003-isolated-write-proof`
- `feat/sw003-runtime-wrapper`
- `feat/visual-grammar-v1`
- Patch-equivalent squash remnants with `git cherry main <branch>` returning `plus=0 minus=1`: `docs/miro-live-recovery-runbook-v1`, `feat/apply-scaffold-v1`, `feat/direct-miro-mcp-client`, `feat/education-lesson-view-v1`, `feat/learning-apply-v1`, `feat/learning-visual-v1-1`, `feat/miro-auth-doctor-v1`, `feat/miro-auth-history-v1`, `feat/miro-fresh-learning-live-test`, `feat/miro-quality-receipt-v1`, `feat/miro-zoomlandkarte-renderer-v1`, `feat/typed-operator-region-plan-v1`, `feat/typed-region-preflight-v1`, `feature-readonly-inspection`, `fix/auth-refresh-v1`, `fix/grabowski-demo-board-dsl`, `fix/miro-live-auth-health`, `fix/miro-oauth-timeout`, `fix/miro-quality-rich-item-types`, `fix/miro-read-snapshot-runtime`, `fix/miro-table-column-types`, `fix/zoomlandkarte-lint-scope-v1`, `pr-24-review`.

### Stale divergent branches, inspect before deletion

These branches have commits not patch-equivalent to main, but comparing them against main would delete or revert newer files. They should be treated as stale, not as forward candidates, until manually inspected:

- `feat/miro-live-test-cleanup-v1` — old cleanup index branch; current main already contains later operator and visual work.
- `finalize-board-v1` — old runtime/demo-board hardening branch; diff against main deletes current education/operator/visual files.
- `fix/miro-localhost-redirect` — old OAuth redirect branch; diff against main deletes newer live-test/operator files.
- `fix/threadless-miro-auth` — old browser-thread/auth branch; diff against main deletes current education/operator/visual files.

## Next SW-009 slice

Name: `SW-009B — live-safe typed apply gating`.

Goal: keep fixture and simulation receipts usable while preventing any scaffold from claiming live typed-apply readiness before SW-003 live-gate evidence exists.

Inputs:

- typed region declaration;
- ready `typed-region-preflight.v1` receipt;
- candidate DSL fixture;
- before-snapshot fixture;
- expected source digest when provided.

Outputs:

- `typed-region-apply-scaffold.v1` with:
  - `ready_for_fixture_apply=true` when local preflight is ready;
  - `ready_for_live_apply=false` while SW-003 live-gate evidence is absent;
  - `live_apply_gate.blocked_reasons=["sw003_live_gate_open"]`;
  - SW-003 live-gate evidence requirements exposed without provider identifiers.

Boundary:

- no live Miro mutation;
- no provider object identifiers;
- no live typed-apply readiness before SW-003 live acceptance;
- no board links;
- no remote cleanup claim;
- no Regie UI.

Tests:

- rejects non-ready preflight;
- rejects snapshot digest mismatch;
- rejects missing or duplicated region marker;
- writes deterministic apply receipt;
- proves re-running the fixture operation is idempotent;
- preserves restore pointer.

## SW-003 live-gate plan after fixture-only closeout

PR #45 added a fixture-only SW-003 closeout receipt. That receipt is a
precondition artifact, not live Miro acceptance. It must not close Issue #8 and
it must keep `closes_live_sw003_gate=false`.

A later live SW-003 receipt may claim `closes_live_sw003_gate=true` only when all
of the following evidence is present and public output remains sanitized:

- live create path attempted in a bounded SW-003 scope;
- created object state verified after the live create step;
- live read after create verified against the expected marked scope;
- live update verified against the same marked scope, not a duplicate layout;
- marker/scope uniqueness verified;
- idempotency verified for the same marker/scope operation;
- cleanup verified, or an explicit live cleanup boundary accepted;
- provider identifiers, board URLs, and provider object IDs absent from public
  evidence;
- board/scope represented by an allowlisted local alias.

This plan is modeled in code by a pure local live-gate evaluator. It performs no
Miro access and no mutation. Its purpose is to block premature live-gate claims
until a later dedicated live proof provides complete, sanitized evidence.


## Decision

Do not close the SW-003 tracker item from fixture-only closeout alone. The remaining closure condition is a dedicated live proof whose public receipt satisfies the live-gate evidence checklist without exposing provider identifiers.

## Epistemic gaps

- The SW-003 tracker discussion has a 2026-07-08 post-PR-51 comment explaining that fixture-only closeout and SW-009 simulation closeout are not live acceptance.
- The available Miro MCP tool catalogue must be checked before claiming remote cleanup.
- A true update operation must distinguish updating marked existing objects from adding a second marked layout.

## Risk and benefit

Benefit of this sequence: it keeps visible education/board progress connected to safety receipts instead of letting the project become a museum of handsome but ungoverned Miro artifacts.

Risk: it delays visible new features. That is acceptable because the next visible feature depends on trustworthy write boundaries.

## Next action

Keep Issue #8 open. Continue SW-009 only through fixture/simulation-safe surfaces until a controlled live SW-003 proof closes the live-gate evidence boundary. The simulation receipt chain is now restore-capable and has an explicit simulation closeout receipt without turning on live apply; keep further work on fixture/simulation-safe surfaces until SW-003 live evidence exists.
