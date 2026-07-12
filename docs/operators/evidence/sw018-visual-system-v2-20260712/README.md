# SW-018 Visual System v2 evidence

This directory contains deterministic, provider-neutral evidence for the Visual System v2 contract and reference renderer.

- `visual-system.json`: semantic roles, palette, hierarchy and density limits.
- `board-spec.json`: canonical seven-frame reference plan.
- `board.dsl`: generated Miro layout DSL.
- `quality-v2.json`: local semantic and narrative quality receipt.
- `compile-receipt.json`: board, quality and output binding.

The local gate is not an automatic claim of aesthetic quality. It proves that the declared design obeys the reviewed architecture, semantic-object, hierarchy, density and consistency contract. Remote creation and UI review are recorded separately because Miro readback can omit geometry.

No provider IDs, board URLs, credentials or private board contents are committed here.

- `review-input.json`: explicit seven-axis human review input.
- `visual-review-receipt.json`: board-, quality- and remote-readback-bound human review.
- `live-acceptance-receipt.json`: sanitized binding to the real Education-team board without provider IDs or URLs.

The authenticated Miro UI screenshot was not available in the isolated browser session. An unauthenticated private-access-page capture was explicitly rejected and removed. The reviewed deterministic design preview is bound to the live board by exact remote counts: seven frames, 38 items, seven connectors, three tables and one document.
