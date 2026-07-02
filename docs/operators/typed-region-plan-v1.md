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

The apply scaffold accepts only a `typed-region-preflight.v1` receipt. If the preflight is not ready, the scaffold remains blocked and preserves the preflight reasons. If it is ready, the scaffold lists the live preconditions and apply steps required before a later mutation command may exist. This command also does not call Miro.
