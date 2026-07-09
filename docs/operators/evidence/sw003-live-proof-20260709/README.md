# SW-003 live proof evidence — 2026-07-09

This directory contains the public, sanitized evidence bundle for the controlled SW-003 live Miro proof.

## Boundary

- Public files contain no Miro board URLs and no provider object identifiers.
- Private raw evidence is intentionally not committed.
- The proof used a fresh allowlisted SW-003 test board alias.
- The marked SW-003 scope was cleaned up after the update/idempotency checks.
- The local review/evidence packet still keeps `ready_for_live_apply=false`; SW-009 is not opened by this evidence.

## Result

- live create: verified
- read after create: verified
- update of marked scope: verified
- marker scope uniqueness: verified
- idempotency: verified
- cleanup: verified
- public sanitization: verified

## Public file digests

| File | SHA-256 | Provider marker count |
|---|---:|---:|
| `cleanup-loop-summary.json` | `9960710f88e68e1ef4de1da21306b3004f7d690e7af35cb9e4eedd98f832fd30` | 0 |
| `live-gate-evaluation.json` | `0c323bc7096a6868b4289750d86c265602075c83420d30ab621e31a2d010da3e` | 0 |
| `live-gate-evidence-packet.json` | `201b6d8bddff9a8eae6f82660ad979ec4910076b788f7d5eb6934d5f2cda8205` | 0 |
| `live-gate-evidence.json` | `6786614299509757d61b60fd0e340ab62508785c56551d6f3cfd803dd7c87ac4` | 0 |
| `live-gate-review-packet.json` | `473218ec7b8728882ee24da593416023d97be1ca50cfbcbb1bf5fdc47741b524` | 0 |
| `live-gate-status.json` | `b1b3683290206d9d9dc22c2a081b7418add7937c3e4a3ba815cca1c67d2f9a4f` | 0 |
| `live-proof-summary.json` | `bd42b26df830fa760f0fd19ef4961d094a404b6d5450f33ebb458a8c3c4526fc` | 0 |

Sanitization check: **PASS**.
