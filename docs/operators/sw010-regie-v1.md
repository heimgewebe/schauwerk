---
id: sw010-regie-v1
role: contract
status: active
doc_type: operator-contract
title: SW-010 Regie v1
summary: Local source-bound review, partial approval, apply evidence and restore without terminal operation.
---

# SW-010 Regie v1

Regie is the local control surface above the SW-009 executor. It turns a reviewed proposal into independent operation decisions and keeps decision, effect and recovery in one receipt-bound context.

## Phase in plain language

Regie is a guarded review desk:

1. show why a change is proposed and which sources support it;
2. mark stale sources and uncertainty before approval;
3. show every exact text change as before, after and inline diff;
4. approve, reject or defer every operation separately;
5. bind the approved subset to a new expiring authorization and plan;
6. require a second explicit phrase before provider effect;
7. show the apply and verification receipt;
8. require a third explicit phrase for restore and show its receipt.

A review does not itself authorize provider mutation. A saved decision is immutable. Apply and restore remain separate actions.

## Security and authority boundaries

- The HTTP server binds only to `127.0.0.1` and handles one request at a time.
- The browser session token is carried in the URL fragment, never in an HTTP request or the static start page, and is retained only in tab session storage.
- Private API routes require the token and a loopback `Host` header.
- The UI uses no external JavaScript, CSS, fonts, images or network services.
- CSP, `no-store`, frame denial, MIME hardening and referrer suppression are enabled.
- Context, review, decision, bundle, authorization, plan and effect receipts are owner-only local files.
- Sources declare revision, observation time, freshness, visibility, citation and uncertainty.
- Stale sources and maximum uncertainty are derived projections, not editable labels.
- Decisions must cover every operation exactly once with `approve`, `reject` or `defer`.
- At least one operation must be approved before an effect authorization is created.
- Partial approval creates a new selected bundle, authorization and plan; rejected or deferred operations cannot leak into apply.
- Decision creation requires `APPROVE_LIVE_APPLY`.
- Apply requires `EXECUTE_LIVE_APPLY`.
- Restore requires `RESTORE_LIVE_APPLY`.
- The SW-009 kill switch and authorization expiry are checked before provider discovery.
- Apply and restore receipts are digest- and schema-validated before replay or display.
- Browser responses omit journal paths, local output paths, provider URLs and provider item identifiers.

## CLI workflow

### 1. Create an owner-only context draft

```bash
schauwerk regie context-template \
  --review-id sw010-review-YYYYMMDD \
  --title "Reviewed managed-region change" \
  --output context-draft.json \
  --json
```

Edit the summary, instructions, sources and context entries. Every context entry must cite a declared source.

### 2. Compile the source-bound context

```bash
schauwerk regie context-compile context-draft.json \
  --output context.json \
  --json
```

### 3. Compile the review bundle

```bash
schauwerk regie review \
  --context context.json \
  --gate live-gate.json \
  --bundle operation-bundle.json \
  --output review.json \
  --json
```

The review compiler checks alias, region, expected revision, operation set and all source digests. It performs no provider call.

### 4. Open Regie

```bash
schauwerk regie serve review.json
```

The browser opens a loopback URL. No terminal knowledge is required after the review bundle exists: operation decisions, apply, verification evidence and restore are available in the same interface.

## User-visible states

| Phase | Meaning | Available action |
|---|---|---|
| `review` | No immutable decision exists | decide every operation |
| `approved` | Selected bundle, authorization and plan are bound | apply while authorization is current |
| `applied` | Postflight and idempotency evidence passed | restore |
| `apply-failed` | Apply failed closed; rollback state is shown | inspect receipt and recovery requirement |
| `restored` | Before-state restoration is verified | no further mutation |

## Failure semantics

- Missing, stale or inconsistent review inputs block before the server starts.
- A changed decision cannot replace an existing decision receipt.
- Expired authorization and active kill switch block before provider discovery.
- Invalid request shape, token, host or confirmation phrase fails closed.
- Tampered stored receipts are rejected before projection.
- Provider errors are redacted and returned as bounded local error messages.
- Apply replay does not repeat provider mutation.
- Restore replay does not repeat inverse mutation.

## Acceptance boundary

Repository acceptance uses a fiktive alias and expired authorization. It exercises the full decision, simulated apply, visible postflight and restore chain with an in-memory provider. No productive Miro board is mutated and no checked-in evidence authorizes a future operation.
