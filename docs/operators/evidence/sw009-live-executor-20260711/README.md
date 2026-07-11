# SW-009 reviewed live-executor acceptance evidence

This directory proves the implementation contract without mutating a productive Miro board.

- `gate-receipt.json` is a sanitized fixture gate for a non-existent local alias.
- `operation-draft.json` demonstrates the editable owner-only draft shape.
- `operation-bundle.json` is the compiled, scope-checked and digest-bound fixture bundle.
- `authorization.json` binds the fixture gate and bundle. It expired on 2026-07-11 at 00:15 UTC and is not current mutation authority.
- `live-plan.json` proves the complete no-mutation plan binding and required execution sequence.
- `provider-capabilities.json` records the sanitized live Miro MCP capability observation used during implementation.
- `failure-matrix.json` lists the exercised fail-closed and recovery cases.
- `acceptance-receipt.json` binds the 381-test validation, capability result and critical source/evidence hashes.

The checked-in fixture files are intentionally not owner-only after a normal Git checkout. Productive loaders reject such files. Real drafts, bundles, authorizations, plans, journals and receipts are written locally with mode `0600`.

Repository tests use an in-memory provider that exposes no board identifiers. They prove successful apply, canonical replay, restore, response-loss reconstruction, automatic rollback, restore recovery, external-drift rejection, expiry, atomic reservation, kill switch, effect-count validation and path safety.

This evidence establishes implementation readiness only. It does not authorize a future live operation.
