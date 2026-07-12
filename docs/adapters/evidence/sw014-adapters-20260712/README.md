# SW-014 Source Adapters Evidence

This evidence verifies the local provider-neutral SW-014 source-adapter foundation.

- **Objective**: Ensure that provider observations yield strictly typed healthy, stale, partial, or failed states with deterministic payload digests.
- **Tools**: `schauwerk adapter fixture`
- **Result**: Passed. The CLI correctly generates valid observation schemas and deterministic digests for all valid statuses.

## Commands Executed

```bash
schauwerk adapter fixture --status healthy
schauwerk adapter fixture --status stale
schauwerk adapter fixture --status partial
schauwerk adapter fixture --status failed
```

All commands successfully output an `adapter-observation.v1` object passing validation.
