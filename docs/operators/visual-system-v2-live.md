# Visual System v2 live board

The live proof creates a fresh allowlisted Miro Education board. It never rewrites or deletes an existing board.

Preconditions:

- `schauwerk miro doctor --json` reports `safe_for_live_board_operations=true`;
- the v2 board specification passes with score at least 90 and no blockers;
- the alias is unused or explicitly replaced only in the local allowlist;
- the evidence directory is owner-only.

## Reference board

Without `--spec-input`, the command compiles and creates the canonical Visual System v2 reference board:

```bash
schauwerk miro visual-v2-live-test \
  --alias schauwerk-visual-system-v2-20260712 \
  --board-name "Schauwerk Visual System v2 – Klarheit vor Dekoration" \
  --output-dir ~/.local/state/schauwerk/miro/live-tests/schauwerk-visual-system-v2-20260712 \
  --json
```

## Caller-composed board

A real generator may provide a validated `schauwerk-visual-board.v2` specification. The live command validates the file, derives the DSL itself and applies the same local and remote gates:

```bash
schauwerk miro visual-v2-live-test \
  --alias schauwerk-software-visual-v2-lenskit-20260713-v2 \
  --board-name "Schauwerk - Lenskit Software Overview - Visual System v2" \
  --output-dir ~/.local/state/schauwerk/miro/live-tests/lenskit-visual-v2 \
  --spec-input build/software-visual-v2.json \
  --json
```

A caller-provided DSL is not accepted by this path. This prevents a reviewed specification from being replaced by unrelated layout instructions between local review and provider mutation.

## Acceptance

Acceptance requires:

- successful creation of one fresh board;
- an empty before snapshot;
- successful layout creation with no failed item;
- a repeatable after snapshot;
- exact remote frame, connector, document, table and item-count conformance;
- a local v2 score of at least 90 with no blocker;
- a separate seven-axis human visual review.

The human review covers information architecture, hierarchy, object selection, density and whitespace, palette consistency, readability and aesthetic character. It binds to the exact board digest, quality digest, sanitized board reference and remote conformance counts.

```bash
schauwerk visual review-v2 \
  ~/.local/state/schauwerk/miro/live-tests/lenskit-visual-v2/live-test-receipt.json \
  review-input.json \
  --output visual-review.json \
  --json
```

An automatic score is a contract check only. A technically conforming board may still fail the human review, as the retained table-heavy SW-019 prototype demonstrates. When an authenticated provider screenshot is unavailable, that limitation must be explicit; no private-access or unauthenticated capture may be substituted.
