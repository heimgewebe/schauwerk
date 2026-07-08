---
id: typed-region-plan-v1
role: contract
status: active
doc_type: contract
title: Typed Region Plan v1
summary: Dry-run contract for future managed-region writes.
---

# Typed Region Plan v1

Typed Region Plan v1 is the first SW-009 operator slice. It does not mutate Miro. It compiles a local, auditable plan that says whether a declared region may proceed to preflight.

A future apply step must start from this kind of plan, capture a before snapshot, match the expected digest, apply only inside the declared region, verify the after snapshot, and keep a restore path.

## Input shape

Required fields:

```text
view_id
region_id
mode
surface_alias
expected_snapshot_digest
```

Optional fields:

```text
expected_source_digest
owner
visibility
```

The `surface_alias` must be a local allowlist alias, not a Miro URL or provider ID.

## Region modes

Only `managed` is ready for preflight in v1. Other modes are blocked with explicit reasons.

## CLI

```bash
schauwerk miro region plan region.yml --json
schauwerk miro region plan region.yml --operation replace-region --output /tmp/plan.json --json
```

## Receipt properties

Every plan reports:

```text
schema_version: typed-region-plan.v1
mutation_attempted: false
ready_for_preflight
required_preflight
postflight_required
restore_required
boundary.dry_run_only: true
boundary.no_miro_mutation: true
```

## Boundary

This is not an apply command. It does not create, update, delete, clear, or inspect live Miro items.

## Preflight CLI

```bash
schauwerk miro region preflight region.yml --snapshot before.json --json
```

The supplied snapshot receipt must match the declared board alias, expected digest, repeatability flag, and sanitized-reference flag. A failed check sets `ready_for_apply=false` and lists explicit `blocked_reasons`. This remains a dry-run gate and does not call Miro.

## Apply Scaffold CLI

```bash
schauwerk miro region apply-scaffold preflight.json --json
```

The apply scaffold accepts only a `typed-region-preflight.v1` receipt. If the preflight is not ready, the scaffold remains blocked and preserves the preflight reasons. If it is ready, the scaffold is fixture-ready only: `ready_for_fixture_apply=true` and `ready_for_live_apply=false`. Live apply remains blocked by `live_apply_gate.blocked_reasons=["sw003_live_gate_open"]` until a later dedicated SW-003 live proof provides complete, sanitized evidence. This command also does not call Miro.


## Simulation Postflight CLI

```bash
schauwerk miro region simulation-postflight apply-simulation.json --json
```

The simulation postflight command accepts only `typed-region-apply-simulation-receipt.v1`. It converts a verified simulation-only apply receipt into a `typed-region-postflight-receipt.v1` that remains fixture-only, simulation-only, and restore-ready. The resulting postflight receipt can feed the existing `restore-receipt` command with a restored snapshot fixture. Neither command requires or performs live Miro access.

## Simulation Closeout CLI

```bash
schauwerk miro region simulation-closeout restore.json --json
```

The simulation closeout command accepts only a restored `typed-region-restore-receipt.v1` that still carries `boundary.simulation_only=true`. This prevents a normal fixture restore from being mistaken for a completed SW-009 simulation chain. The closeout receipt reports `ready_for_sw009_simulation_closeout=true` only after the restore receipt is ready, fixture-only, simulation-only, restored to the pre-apply snapshot, and sanitized. It deliberately keeps `ready_for_live_apply=false`, reports `closes_live_sw003_gate=false`, and exposes the same SW-003 live gate block (`sw003_live_gate_open`).
