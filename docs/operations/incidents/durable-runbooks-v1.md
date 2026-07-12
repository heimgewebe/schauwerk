---
id: schauwerk-durable-runbooks-v1
role: runbook
status: active
doc_type: operations
title: Durable incident runbooks v1
summary: Bounded responses for source, provider, token and mutation incidents.
---

# Durable incident runbooks v1

## Source adapter failed

1. Preserve the failed observation and its errors.
2. Do not replace it with cached material marked fresh.
3. Keep unaffected adapters and local views available.
4. Repair the collector, then compile a new observation with a new evaluation time.

## Miro unavailable

1. Enable or confirm the SW-009 kill switch when mutation risk exists.
2. Continue with Registry, local overview, presentation and publication artifacts.
3. Record provider failure as a time-bound observation.
4. Resume writes only after live doctor, exact board identity and snapshot checks pass.

## OAuth identity lost or changed

1. Preserve owner-only identity and allowlist metadata; never copy tokens into Git.
2. Compile an OAuth rotation plan for the intended team and Space.
3. Authorize interactively.
4. Verify exact board searches and read-only snapshots.
5. Keep rollback metadata until the postflight receipt is accepted.

## Faulty managed-region mutation

1. Stop further effects with the kill switch.
2. Bind the affected transaction receipt and current snapshot.
3. Run the existing drift-protected restore path.
4. Verify the restored managed region and preserve both failure and restore receipts.
5. Do not touch manual or cooperative regions during recovery.
