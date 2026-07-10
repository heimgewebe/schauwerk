---
id: education-variants-offline
role: guide
status: active
doc_type: operator-guide
title: Education variants and offline packages
summary: Audience-specific static learning outputs with explicit privacy and submission boundaries.
---

# Education variants and offline packages

Schauwerk can derive five static HTML variants from one learning source:

- `teacher` includes teacher notes and answer guidance.
- `projection` shows only the concise shared classroom flow.
- `assignment` requires instructions, resources and a submission boundary.
- `student` contains learning steps, materials and self-checks but no teacher-only content.
- `presentation` turns the shared flow into ordered static slides.

All variants carry the same normalized source digest. Inputs are version-bound to `education-variants-input.v1`; unknown fields and schema versions are rejected. Public or classroom-facing variants explicitly exclude teacher notes and answer guidance.

```bash
schauwerk education render lesson.json \
  --variant student \
  --output student.html \
  --json
```

## Offline package

```bash
schauwerk education offline lesson.json \
  --variant student \
  --output-dir offline-package \
  --json
```

Each package contains `index.html`, exactly one audience-specific HTML variant and `manifest.json`. Requiring one explicit variant prevents teacher notes or answer guidance from being bundled with student-facing material. The package uses only relative links and inline CSS. It contains no scripts, remote resources or Miro calls and therefore opens from a local filesystem without network access.

## Privacy boundary

Before rendering, Schauwerk rejects explicit personal-data fields, email addresses and phone-like values. This is a high-confidence structural guard, not a general-purpose name detector. Inputs must still be reviewed before classroom or public distribution. The committed acceptance fixture contains no names, grades, contact data or identifying case details.
