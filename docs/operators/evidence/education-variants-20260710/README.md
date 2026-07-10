# Education variants and offline acceptance evidence

This evidence proves SW-007 without Miro or network access.

- `source.json` is a sanitized shared learning source.
- `package/index.html` opens the package locally.
- Separately rendered teacher, projection, assignment, student and presentation variants share one source digest.
- Only the teacher variant contains teacher notes and the answer key.
- The assignment variant contains explicit instructions, resources and a submission boundary.
- `package/manifest.json` binds a student-only offline package; teacher material is not bundled.
- `offline-receipt.json` records the package identity and confirms that Miro and network access are not required.

The package contains no personal data. It is a deterministic fixture, not a live classroom record.
