# Grabowski operational pilot evidence — 2026-07-10

This directory proves the first bounded operational Grabowski projection from live source observations.

## Inputs

- static contract snapshot: `../grabowski-pilot-20260710/snapshot.json`
- sanitized observation: `observation.json`
- evaluated at: `2026-07-10T05:43:15Z`

Live collection established only the following summaries:

- fleet: 4 declared and enabled hosts, 3 reachable, 1 unavailable;
- runtime: 2 Grabowski-related user units running, 100 expected tools, policy state not independently resolved, 23 failed Grabowski-related user units;
- work: no active Grabowski Bureau run, 1 open PR, 1 ready task;
- gaps: 38 non-terminal Grabowski-related Bureau follow-ups, of which 37 were planned and none blocked.

No host aliases, network addresses, raw SSH errors, service names, task identifiers, PR titles, provider URLs or credentials are committed.

## Outputs

- `snapshot.json`: deterministic `grabowski-operational-snapshot.v1`;
- `operator-overview.dsl`: Miro-compatible read-only projection;
- `render-receipt.json`: output and non-mutation receipt.

## Result

- overall status: `degraded`;
- healthy channels: 2;
- partial channels: 2;
- stale channels: 0;
- unavailable channels: 0;
- snapshot digest: `5af25c3a17b3d3c4191f0292bed848469ec27d989070c8317908b7f71f9670e2`;
- provider mutation attempted: `false`.

This evidence proves that static facts, fresh observations, partial collection, degraded domain state and source gaps can be represented without turning the projection into source truth. It does not prove continuous collection or authorize a live Miro apply.
