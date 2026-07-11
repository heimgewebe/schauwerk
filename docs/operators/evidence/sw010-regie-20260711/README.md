# SW-010 Regie v1 acceptance evidence

This directory proves the review and control contract without productive provider mutation.

- `context.json` contains a source-bound fixture context with one deliberately stale source.
- `review-bundle.json` binds context, gate, expected revision, two typed operations and their semantic/visual diffs.
- `decision-receipt.json` approves one operation, rejects one operation and contains an authorization that expired on 2026-07-11 at 02:15 UTC.
- `interface-contract.json` records loopback, token, CSP, partial-approval and receipt-visibility boundaries.
- `failure-matrix.json` records the exercised fail-closed cases.
- `acceptance-receipt.json` binds the 407-test repository validation and critical file hashes.

Checked-in JSON files are fixtures and normally become mode `0644` after checkout. Productive Regie loaders require owner-only regular files and therefore reject the checked-in copies directly.

The evidence does not contain a Miro URL, provider item identifier, credential, local absolute path or current mutation authority.
