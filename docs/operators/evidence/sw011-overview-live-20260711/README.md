# SW-011 overview and live views acceptance evidence

This directory proves the read-only overview contract with a deterministic fixture environment.

- `overview-snapshot.json` contains Registry navigation, time-bound artifact observations, one active SW-009 transaction, one Regie review and a simulated provider outage.
- `interface-contract.json` records loopback, read-only HTTP, fragment-token, CSP, fullscreen and bounded refresh properties.
- `failure-matrix.json` lists the exercised degraded and fail-closed cases.
- `acceptance-receipt.json` binds the 428-test repository validation and critical file hashes.

The snapshot remains useful while `provider.miro.live` is in the error state: projects, views, publications and local jobs remain present. No productive Miro call or mutation was performed for the fixture evidence.

Checked-in snapshot files are normally mode `0644`; the productive loader requires owner-only mode and rejects the checked-in copy directly.
