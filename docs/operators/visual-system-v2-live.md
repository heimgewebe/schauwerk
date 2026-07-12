# Visual System v2 live reference board

The live proof creates a fresh allowlisted Miro Education board. It never rewrites or deletes an existing board.

Preconditions:

- `schauwerk miro doctor --json` reports `safe_for_live_board_operations=true`;
- the v2 reference spec passes with score at least 90 and no blockers;
- the alias is unused or explicitly replaced only in the local allowlist;
- the evidence directory is owner-only.

Command:

```bash
schauwerk miro visual-v2-live-test \
  --alias schauwerk-visual-system-v2-20260712 \
  --board-name "Schauwerk Visual System v2 – Klarheit vor Dekoration" \
  --output-dir ~/.local/state/schauwerk/miro/live-tests/schauwerk-visual-system-v2-20260712 \
  --json
```

Acceptance requires successful board creation, an empty before snapshot, successful layout creation, repeatable after snapshot, remote frame/connector/doc/table counts compatible with the compiled plan, a local v2 score of at least 90 and a separate visual screenshot review when the provider UI is available.


After the live run, compile the separate review receipt:

```bash
schauwerk visual review-v2 \
  ~/.local/state/schauwerk/miro/live-tests/schauwerk-visual-system-v2-20260712/live-test-receipt.json \
  review-input.json \
  --output visual-review.json \
  --json
```

The review input must cover information architecture, hierarchy, object selection, density and whitespace, palette consistency, readability and aesthetic character. It must name the deterministic board-spec preview and the exact remote conformance method. Automatic quality remains a contract check only.
