---
id: sw009-live-executor-v1
role: contract
status: active
doc_type: operator-contract
title: SW-009 reviewed live executor v1
summary: Digest-bound exact-text transactions for allowlisted managed Miro regions.
---

# SW-009 reviewed live executor v1

The executor is the narrow mutation boundary between reviewed Schauwerk proposals and an allowlisted Miro board. It does not accept free-form DSL and it does not create or delete board items. Version 1 permits only exact single-line text replacements that preserve a declared managed-region marker.

## Phase in plain language

The executor works like a guarded edit transaction:

1. prove which board revision is expected;
2. describe the exact old and new text inside one managed region;
3. bind that bundle to an explicit, expiring approval;
4. reserve the approval once;
5. snapshot and read the board again;
6. apply the exact replacements;
7. read and snapshot the result;
8. keep a restore path and owner-only journal.

Any mismatch stops the transaction. A failed mutation is reconstructed from the board state and rolled back. Restore also checks that nobody changed the board after the accepted transaction.

## Required boundaries

- The board is referenced only by a local allowlisted alias.
- The region mode is `managed`.
- The gate, operation bundle, authorization and expected snapshot digest are hash-bound.
- Operation drafts, bundles, authorizations, plans, journals and receipts are owner-only local files.
- Every operation preserves `schauwerk-region:<region-id>` in both old and new text.
- Replacement strings are unique, non-overlapping, single-line and free of provider URLs or DSL delimiters.
- Miro must report exactly one update, zero creates and zero deletes for each operation.
- Raw board URLs, item identifiers and provider DSL never leave the private runtime adapter.
- `layout_read` must represent every board item; any non-zero skipped count blocks apply.
- Each provider update digest must equal the locally compiled intermediate DSL state.
- One authorization digest can reserve only one transaction directory.
- The reviewed plan must exactly equal a fresh compilation from Gate, Bundle and Authorization.
- The successful transaction receipt binds the exact committed journal digest.
- The kill switch blocks new apply transactions; restore remains available from a committed receipt.

## Provider contract

Before execution, Schauwerk refreshes the live Miro tool catalogue and requires:

- `layout_read` for a full private DSL read;
- `layout_update` for one exact replacement;
- the existing verified snapshot path for before, after, rollback and restore evidence.

A cached catalogue alone is not mutation authority.

## Review workflow

### 1. Generate an editable draft

```bash
schauwerk miro region sw009-live-bundle-template region.json \
  --bundle-id sw009-live-bundle-20260711 \
  --output operation-draft.json \
  --json
```

Edit only the `old_text` and `new_text` fields. Keep the managed-region marker in both values.

### 2. Compile the reviewed bundle

```bash
schauwerk miro region sw009-live-bundle-compile operation-draft.json \
  --output operation-bundle.json \
  --json
```

The compiler validates scope and text safety, normalizes the operations and writes the digest-bound bundle.

### 3. Create the explicit authorization

```bash
schauwerk miro region sw009-live-authorization-create live-gate.json \
  --bundle operation-bundle.json \
  --authorization-id sw009-live-authorization-20260711 \
  --approved-by alex \
  --approval-reference bureau:schauwerk-useful-pilot-v1-t007 \
  --confirmation APPROVE_LIVE_APPLY \
  --valid-minutes 60 \
  --output authorization.json \
  --json
```

The confirmation phrase is deliberate friction. Authorization is single-use and valid for at most 24 hours.

### 4. Compile the no-mutation plan

```bash
schauwerk miro region sw009-live-plan live-gate.json \
  --bundle operation-bundle.json \
  --authorization authorization.json \
  --output live-plan.json \
  --json
```

### 5. Inspect the kill switch

```bash
schauwerk miro region sw009-kill-switch status --json
```

To stop new applies:

```bash
schauwerk miro region sw009-kill-switch enable \
  --reason "operator stop" \
  --json
```

Disabling requires the exact confirmation `ENABLE_LIVE_APPLY`.

### 6. Execute and restore

```bash
schauwerk miro region sw009-live-apply live-gate.json \
  --bundle operation-bundle.json \
  --authorization authorization.json \
  --plan live-plan.json \
  --output transaction-receipt.json \
  --json
```

```bash
schauwerk miro region sw009-live-restore transaction-receipt.json \
  --output restore-receipt.json \
  --json
```

`live-apply` recompiles Gate, Bundle and Authorization and requires exact equality with the reviewed owner-only plan. A stale or changed source therefore blocks before Miro.

The transaction journal always lives below the canonical Schauwerk state root. Operators cannot redirect it to create a second single-use namespace.

## Failure semantics

- Preflight mismatch consumes the single-use authorization without touching Miro.
- Provider response loss after a mutation triggers a fresh board read; actually applied operations are detected and reversed.
- A failed restore reconstructs its current state and attempts to return to the committed after-state.
- If automatic rollback cannot prove the expected digest, the receipt requires manual recovery and never claims restore readiness.
- External board drift blocks restore before the first inverse operation.

## Acceptance boundary

Deterministic tests exercise successful apply, reviewed-plan binding, complete DSL coverage, intermediate provider digests, idempotent replay, journal binding, restore, provider response loss, automatic rollback, restore recovery, snapshot and DSL drift rejection, authorization expiry, atomic reservation, path safety, capability failure and the kill switch.

No productive Miro board was mutated for repository acceptance. Implementation evidence does not authorize a future live operation; every live operation still needs its own current gate, bundle and expiring authorization.
