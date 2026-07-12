---
id: schauwerk-durable-operations-v1
role: norm
status: active
doc_type: operations
title: Durable operations v1
summary: Local profiles, health, backup manifests, staged restore checks and recovery plans.
---

# Durable operations v1

SW-017 supplies deterministic local contracts for four roles: overview, Regie, publication and maintenance. The catalogue describes network and mutation boundaries but does not install a service.

## Health

A health receipt aggregates declared component evidence. A failed optional component does not block readiness. A failed required component does. No probe is implied by compilation.

## Backup and restore

A backup declaration lists repository-relative regular files, retention classes and artifact classes. Manifest compilation checks sizes and SHA-256 values without copying files. It rejects traversal, symlinks and secret-like paths. OAuth tokens, credentials, private keys and `.env` files are outside the contract.

Restore verification reads a separate staged tree and compares it with the manifest. It never overwrites live state. A verified receipt is evidence for a later operator-controlled restore, not the restore itself.

## OAuth and kill switch

The OAuth rotation compiler creates a no-token plan bound to an identity digest, target team, target Space, board aliases and rollback reference. Current productive identity is the Miro Education team with Space `Schauwerk`; interactive provider authorization and UI-level Space verification remain external effects.

The kill-switch drill compiler binds already collected before, blocked-apply and after evidence. It does not toggle the live switch.

## Commands

```text
schauwerk durable profiles --json
schauwerk durable health health-input.json --at 2026-07-12T09:00:00Z --output health.json --json
schauwerk durable backup-manifest backup.json --root /staged/source --created-at 2026-07-12T09:00:00Z --output manifest.json --json
schauwerk durable restore-verify manifest.json --staged-root /staged/restore --verified-at 2026-07-12T09:05:00Z --output restore.json --json
```

## External acceptance gates

Repository acceptance does not establish installed systemd units, scheduled maintenance, an executed backup, a live restore, a live OAuth rotation, public hosting or a live kill-switch drill. Those effects require target-specific authorization and receipts.
