---
id: schauwerk.ecosystem-map-handoff
role: reference
status: active
doc_type: reference
title: Ecosystem Map HTML Handoff
summary: Read-only Schauwerk HTML handoff for ecosystem-map artifacts owned by the Systemkatalog.
---

# Ecosystem Map HTML Handoff

Schauwerk can produce a read-only HTML handoff from an ecosystem-map artifact manifest produced by the Systemkatalog.

The handoff is intentionally conservative:

- The Systemkatalog remains the map source.
- Schauwerk verifies artifact digests before writing HTML.
- The output contains Mermaid source and provenance metadata.
- `diagram_rendered` is `false`; the HTML is not a layout authority.
- The handoff does not prove claim truth, runtime correctness, merge readiness, or diagram-layout correctness.

## Command

```bash
schauwerk ecosystem render \
  /path/to/ecosystem-map-artifact-manifest.json \
  --source-root /path/to/systemkatalog \
  --output /path/to/ecosystem-map.html \
  --json
```

The manifest is produced by the Systemkatalog:

```bash
python3 scripts/write_ecosystem_map_artifact_manifest.py \
  --output rendered/ecosystem-map-artifact-manifest.json
```

## Boundary

This is a publication/presentation handoff, not a replacement for the Systemkatalog and not a Leitstand write path. Leitstand may later consume the HTML read-only with digest and freshness metadata.
