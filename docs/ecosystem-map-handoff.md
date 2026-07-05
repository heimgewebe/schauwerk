---
id: schauwerk.ecosystem-map-handoff
role: reference
status: active
doc_type: reference
title: Ecosystem Map HTML Handoff
summary: Read-only Schauwerk HTML handoff for Cabinet-owned ecosystem map artifacts.
---

# Ecosystem Map HTML Handoff

Schauwerk can produce a read-only HTML handoff from a Cabinet ecosystem-map artifact manifest.

The handoff is intentionally conservative:

- Cabinet remains the map source.
- Schauwerk verifies artifact digests before writing HTML.
- The output contains Mermaid source and provenance metadata.
- `diagram_rendered` is `false`; the HTML is not a layout authority.
- The handoff does not prove claim truth, runtime correctness, merge readiness, or diagram-layout correctness.

## Command

```bash
schauwerk ecosystem render \
  /path/to/ecosystem-map-artifact-manifest.json \
  --source-root /path/to/cabinet \
  --output /path/to/ecosystem-map.html \
  --json
```

The manifest is produced by Cabinet:

```bash
python3 scripts/write_ecosystem_map_artifact_manifest.py \
  --output rendered/ecosystem-map-artifact-manifest.json
```

## Boundary

This is a publication/presentation handoff, not a Cabinet replacement and not a Leitstand write path. Leitstand may later consume the HTML read-only with digest and freshness metadata.
