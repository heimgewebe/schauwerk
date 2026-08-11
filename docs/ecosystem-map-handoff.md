---
id: schauwerk.ecosystem-map-handoff
role: reference
status: active
doc_type: reference
title: Ecosystem Map HTML Handoff
summary: Read-only Schauwerk HTML handoff for ecosystem-map and resilience artifacts owned by the Systemkatalog.
---

# Ecosystem Map HTML Handoff

Schauwerk can produce a read-only HTML handoff from an ecosystem-map artifact manifest produced by the Systemkatalog.

The handoff is intentionally conservative:

- The Systemkatalog remains the authority for criticality, failure domains, stable coupling and recovery-path semantics.
- Schauwerk verifies artifact digests before writing HTML.
- If the manifest publishes the `resilience_semantics` role, Schauwerk validates and renders it alongside the canonical Mermaid source.
- Older manifests without `resilience_semantics` remain supported; Schauwerk shows an explicit unavailable message instead of inventing fallback semantics.
- `diagram_rendered` is `false`; the HTML is not a layout authority.
- The handoff does not prove current failure, current health, recovery readiness, automatic recovery authority, merge readiness or diagram-layout correctness.

## Static command

```bash
schauwerk ecosystem render \
  /path/to/ecosystem-map-artifact-manifest.json \
  --source-root /path/to/systemkatalog \
  --output /path/to/ecosystem-map.html \
  --json
```

The Systemkatalog manifest may publish the resilience registry as a digest-bound artifact:

```json
{
  "role": "resilience_semantics",
  "path": "registry/ecosystem/resilience.v1.json",
  "sha256": "..."
}
```

The renderer preserves this split:

- **Catalog semantics:** versioned criticality, failure domains, stable relations, coupling and recovery modes.
- **Blast radius:** affected systems plus catalogued recovery modes that do or do not share the selected failure domain. A “remaining” catalog path is not a claim that the path is currently runnable.
- **Text mode:** the same essential system/domain/recovery information is present without color.
- **Reduced motion:** the HTML disables non-essential animation and transition behavior under `prefers-reduced-motion: reduce`.

## Optional time-bound trend overlay

A caller may add a separately published, source-labelled trend artifact:

```bash
schauwerk ecosystem render \
  /path/to/ecosystem-map-artifact-manifest.json \
  --source-root /path/to/systemkatalog \
  --operational-overlay /path/to/resilience-trend-export.json \
  --evaluated-at 2026-08-11T10:30:00Z \
  --output /path/to/ecosystem-map.html \
  --json
```

The overlay is deliberately not a second truth store. Its v1 envelope is:

```json
{
  "schema_version": "schauwerk-resilience-operational-overlay.v1",
  "source_id": "chronik.resilience-trend-export",
  "stale_after_seconds": 3600,
  "signals": [
    {
      "subject": "repo:example",
      "metric": "recovery_proof_age",
      "value": 12,
      "unit": "hours",
      "trend": "deteriorating",
      "authority": "infra.recovery-proof-observation",
      "observed_at": "2026-08-11T10:00:00Z",
      "coverage": "partial",
      "uncertainty": 0.2,
      "evidence_ref": "sha256:..."
    }
  ],
  "does_not_establish": [
    "current_failure",
    "current_health",
    "automatic_recovery_authority"
  ]
}
```

Allowed slow variables are `attention_age`, `terminal_projection_lag`, `recurring_failure_signatures`, `recovery_proof_age`, `temporary_resource_growth` and `closure_duration`.

Every signal carries its own authority, observation time, coverage, uncertainty and evidence reference. Freshness is evaluated at render time from `observed_at`, the explicit `--evaluated-at` instant and `stale_after_seconds`; mixed fresh/stale exports remain visibly mixed. The overlay cannot add or override static Systemkatalog semantics.

`source_id` is a required label, not cryptographic source authentication. Schauwerk therefore exposes provenance and staleness but does not claim that an arbitrary caller-supplied overlay is authentic merely because its label looks authoritative.

## Boundary

This is a publication/presentation handoff, not a replacement for the Systemkatalog, Chronik, Bureau or a runtime readback. The existing resilience collector may append source-bound observations to Chronik through its own idempotent outbox contract; Schauwerk only consumes an explicitly supplied projection artifact and never writes source truth or derives current operational truth from catalog data.
