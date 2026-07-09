---
id: sw003-controlled-live-proof-plan
role: runbook
status: active
doc_type: runbook
title: SW-003 controlled live proof plan
summary: Non-mutating preparation plan for the eventual controlled SW-003 live proof.
---

# SW-003 controlled live proof plan

## Purpose

This runbook prepares the eventual SW-003 live proof without performing it. It exists to prevent an operator from treating the local live-gate receipt chain as permission to mutate Miro.

The plan covers only preparation, review, and acceptance criteria. A real live run still requires explicit operator approval at execution time.

## Hard boundary

The preparation phase must not:

- create, update, delete, or move Miro objects;
- call a Miro mutation tool;
- expose board URLs, provider object IDs, or raw provider identifiers in public output;
- close Issue #8;
- set `ready_for_live_apply=true` for SW-009 or any broader typed-region apply path.

A later execution receipt may claim `closes_live_sw003_gate=true` only if the evidence contract below is complete, sanitized, and independently reviewed.

## Preflight inputs

Before any live action is considered, collect these local inputs:

| Input | Requirement |
|---|---|
| Repository state | Clean `main...origin/main` in `/home/alex/repos/schauwerk`. |
| Issue state | `heimgewebe/schauwerk#8` is open before the run. |
| Miro auth state | `schauwerk miro status --live --json` is healthy. |
| Tool catalogue | `schauwerk miro tools --json` is reviewed for the exact read, create, update, and cleanup capabilities available. |
| Board scope | A local allowlisted alias is selected; no public board URL is emitted. |
| Marker | A fresh `schauwerk-sw003-YYYYMMDDTHHMMSSZ-xxxxxx` marker is generated. |
| Evidence template | Current `sw003-live-gate-template` and `sw003-live-gate-requirements` outputs are captured. |

## Required tool catalogue decision

The live proof must not assume remote cleanup or true update support. The operator must inspect the available Miro MCP tools and record one of these decisions before mutation:

| Capability | Required decision |
|---|---|
| Create | Tool can create objects in the bounded SW-003 scope. |
| Read | Tool can read back enough object state to verify marker, type, and content digest. |
| Update | Tool can update the same marked objects rather than creating a duplicate layout. |
| Cleanup | Tool can delete/clear the marked scope, or the run explicitly accepts a cleanup boundary. |

If update support cannot distinguish same-object update from duplicate creation, the run must abort before claiming SW-003 closure.

If cleanup support is absent or unsafe, the public receipt may only proceed if an explicit cleanup boundary is accepted with the reason `live_cleanup_boundary_accepted` and the board/scope remains allowlisted for later manual cleanup.

## Controlled live sequence

The eventual live run must follow this sequence exactly:

1. Capture a before snapshot for the allowlisted alias.
2. Create a minimal SW-003 marked object set inside the bounded test scope.
3. Read back created objects and verify marker, expected count, sanitized object-type summary, and content digest.
4. Update the same marked objects.
5. Read back after update and verify that the same marked scope changed instead of duplicating.
6. Re-run the same operation or verification to prove idempotency at marker/scope level.
7. Cleanup the marked scope, or record an explicit cleanup boundary if remote cleanup is unavailable or unsafe.
8. Capture an after/cleanup snapshot or cleanup-boundary evidence.
9. Compile sanitized live-gate evidence.
10. Run the local chain:

```bash
schauwerk miro region sw003-live-gate live-gate-evidence.json --json
schauwerk miro region sw003-live-gate-status live-gate-evaluation.json --json
schauwerk miro region sw003-live-gate-review-packet live-gate-status.json --json
```

The local chain remains non-mutating. It evaluates and packages evidence after the controlled live run; it does not itself prove that the live run happened.

## Evidence contract

The public evidence object must satisfy the existing local evaluator and include only sanitized fields:

| Evidence field | Required meaning |
|---|---|
| `claim_closes_live_sw003_gate=true` | The evidence explicitly asks to close the live gate. |
| `board_scope.alias` | Local allowlist alias only. |
| `live_create_attempted=true` | Create step attempted in bounded scope. |
| `live_create_verified=true` | Created state verified after create. |
| `live_read_after_create_verified=true` | Read after create observed expected marked scope. |
| `live_update_verified=true` | Update changed the same marked scope, not a duplicate layout. |
| `marker_scope_uniqueness_verified=true` | Marker is unique in the declared board/scope. |
| `idempotency_verified=true` | Re-running did not create drift or duplicates. |
| `cleanup_verified=true` or `cleanup_boundary_accepted=true` | Cleanup completed, or explicit safe boundary accepted. |
| `provider_identifiers_sanitized=true` | Public output contains no board URLs or provider object IDs. |
| `board_scope_allowlisted=true` | Board/scope is represented by a local alias. |
| `*_evidence_digest` | Digest-only references to private/raw evidence. |

The public evidence must not contain `miro.com`, `/app/board/`, raw board IDs, raw object IDs, or direct provider URLs.

## Abort criteria

Abort before mutation if:

- Miro auth is stale or uncertain;
- tool catalogue cannot be inspected;
- no allowlisted board alias is available;
- marker generation fails validation;
- public evidence would need to expose provider IDs to be meaningful.

Abort after create/update and do not claim closure if:

- read-back cannot verify the marker scope;
- update creates duplicates instead of changing the same objects;
- idempotency cannot be proven;
- cleanup is neither verified nor explicitly boundary-accepted;
- any receipt contains provider identifiers in public fields.

## Review and closeout

A human reviewer must inspect the final review packet and the private evidence bundle before Issue #8 is closed. The review must confirm:

- all required booleans are true or cleanup boundary is explicitly accepted;
- all evidence digests are present and stable;
- the review packet remains local-only and non-mutating;
- public output is sanitized;
- SW-009 live apply is not enabled by the review packet itself.

Only after that review may a separate Issue #8 closeout action be prepared.

## Next implementation slice

The next safe code slice is a local live-proof preflight packet that records:

- current Miro tool catalogue digest;
- selected allowlisted alias digest;
- marker value;
- intended live sequence;
- abort criteria acknowledgement;
- `ready_for_live_mutation=false` until explicit operator approval is supplied outside the packet.
