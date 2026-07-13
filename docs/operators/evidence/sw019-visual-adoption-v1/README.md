# SW-019 — Visual System v2 adoption proof

This evidence set applies the Visual System v2 composition path to the existing, source-bound Lenskit software-pilot input.

## Compile command

```bash
schauwerk pilot software docs/operators/evidence/lenskit-pilot-20260710/input.json \
  --visual-spec-output docs/operators/evidence/sw019-visual-adoption-v1/board-spec.json \
  --visual-quality-output docs/operators/evidence/sw019-visual-adoption-v1/quality.json \
  --visual-dsl-output docs/operators/evidence/sw019-visual-adoption-v1/board.dsl \
  --json
```

## Final composition

- board digest: `b55b1df55a82fa36749dc674015b0fb66fda88f00e860d6e180b96453e17957c`
- quality digest: `9561bdd504193a7b0bc6c48f8ed3b08a58b15d2cbc405d2640c347996e0e83c2`
- local quality: `100/100`, no blocker, no warning
- 7 narrative frames
- 42 declared objects: 16 shapes, 3 tables, 1 document and 8 connectors
- 0 sticky notes
- provider mutation attempted during compilation: `false`

The architecture frame uses connected component shapes, delivery combines a sequenced roadmap with a bounded work comparison, and risks are individual action objects. The evidence frame includes source revisions, the software snapshot digest and the explicit limit that revisions are known but no observation timestamp is claimed.

## Live acceptance

The final isolated Miro board uses alias `schauwerk-software-visual-v2-lenskit-20260713-v2` and sanitized reference digest `2da2ead75af686d1`.

- 49 layout elements created, 0 failed
- exact remote conformance: 7 frames, 3 tables, 1 document, 8 connectors and 41 remotely readable items
- remote mismatches: none
- human visual review: `PASS`
- review digest: `7f0000d5c6f4688affa39248bd93bfbc672e24cec2879900226d50d9c4af71f9`

The authenticated provider screenshot was not available. The review is therefore bound to the deterministic board-spec design surface and exact remote item-type/count conformance, not to pixel-identical Miro UI rendering.

## Rejected first iteration

The first technically valid live board is retained as a compact negative-evidence receipt. It scored 100/100 automatically and conformed remotely, but used six tables across seven frames. The separate human review marked `aesthetic_character` and `object_selection` as `FAIL` because the result remained too form-like.

- rejected board digest: `47b880b0adf8d4c39410099b4181a1eaa8c95269e6927475f913cffb9b19dd6e`
- rejected review digest: `d92deae61e77413e7ffdf8b9e5b51e3cb20b86be766318e7252cf767ed81e4c9`

This demonstrates that the automatic quality score is a contract gate, not an aesthetic verdict.

## Evidence compaction

The repository commits one board specification, its deterministic DSL and quality receipt, plus compact final and rejected live receipts. Full sanitized before/after snapshots and intermediate provider artifacts are archived outside the repository as `sw019-visual-adoption-live-raw-20260713.tar.gz`, SHA-256 `d8576b4a29fc6976f3520390caeb554c9b3f7c493cdcb0c024eea5340c54c43b`. The compact receipts contain the hash of every raw file in that archive.

## File hashes

- source input: `e1accd1617f4c6c56a1c7a47fe54f74ef7403d93831b8b81ff49599e77620f35`
- `board-spec.json`: `4cdc9f7e9f655a77f7cab33cd69f502151b15823a35064a6932ba691e58426ea`
- `quality.json`: `520c1144c2e30da1f4be1a0df0ae877eec46b835d8e3b304b5c68d88eef97cf7`
- `board.dsl`: `4cff92b19c7ff6ba73213e1c404558403d16c77310810771a912c72ec4b10d12`
- `render-receipt.json`: `899dcf4aa1a1e4eed79fc9ceb6384993822b9504e71ef265a57ff221435f997e`
- `live-acceptance-receipt.json`: `42698d66b84c4be23e08e706e32de8fe4a59fa1b7d4d305a3aa7816ecf25f6bb`
- `rejected-iteration-receipt.json`: `f1826410e01aac5750d12aae4d4dffc0616243998eb88c83b0648f41a82b2f69`

## Non-claims

This proves deterministic composition, local quality-gate acceptance, isolated provider creation, exact remote conformance and a bounded human review. It does not prove universal aesthetic quality, authenticated screenshot evidence, pixel-identical rich-object geometry or freshness beyond the recorded source revisions.
