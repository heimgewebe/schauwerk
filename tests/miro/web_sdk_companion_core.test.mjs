import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(process.env.SCHAUWERK_CORE_JS, 'utf8');
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const core = await import(moduleUrl);

const config = {
  schema_version: 'schauwerk-miro-web-sdk-companion.v1',
  app_name: 'Schauwerk',
  panel_title: 'Panel',
  panel_height: 760,
  max_frames: 50,
  selection_limit: 20,
  show_board_id: false,
  status: {
    state: 'verified',
    quality_score: 100,
    operation_count: 2,
    completed_operation_count: 2,
    snapshot_digest: 'a'.repeat(64),
    execution_digest: 'b'.repeat(64),
    findings: [],
  },
};

test('validates the public runtime configuration', () => {
  assert.equal(core.assertCompanionConfig(config), config);
  assert.throws(
    () => core.assertCompanionConfig({ ...config, panel_height: 20 }),
    /panel_height/,
  );
});


test('detects Miro only inside an SDK-enabled iframe', () => {
  const topLevel = { miro: { board: {} } };
  topLevel.parent = topLevel;
  assert.equal(core.isMiroEmbedded(topLevel), false);
  assert.equal(core.isMiroEmbedded({ parent: {}, miro: { board: {} } }), true);
  assert.equal(core.isMiroEmbedded({ parent: {} }), false);
});

test('sorts frames in a deterministic top-to-bottom reading order', () => {
  const frames = core.sortFrames(
    [
      { id: 'c', type: 'frame', title: 'C', x: 500, y: 100 },
      { id: 'b', type: 'frame', title: 'B', x: 300, y: 0 },
      { id: 'a', type: 'frame', title: 'A', x: 100, y: 0 },
      { id: 'ignored', type: 'text', content: 'Ignored', x: 0, y: 0 },
    ],
    10,
  );
  assert.deepEqual(frames.map((frame) => frame.id), ['a', 'b', 'c']);
});

test('removes markup from labels and limits selection summaries', () => {
  assert.equal(core.itemLabel({ type: 'text', content: '<p>Hallo <b>Welt</b></p>' }), 'Hallo Welt');
  assert.deepEqual(
    core.summarizeItems(
      [
        { id: '1', type: 'text', content: '<p>Erstes</p>' },
        { id: '2', type: 'shape', content: 'Zweites' },
      ],
      1,
    ),
    [{ id: '1', type: 'text', label: 'Erstes' }],
  );
});

test('clamps presentation positions and redacts long digests', () => {
  assert.equal(core.clampFrameIndex(-2, 4), 0);
  assert.equal(core.clampFrameIndex(9, 4), 3);
  assert.equal(core.shortDigest('f'.repeat(64)), `${'f'.repeat(12)}…`);
  assert.equal(core.statusTone('failed'), 'bad');
});
