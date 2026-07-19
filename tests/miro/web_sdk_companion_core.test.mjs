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
  write_actions: {
    enabled: true,
    allowed: ['create_review_card'],
    require_confirmation: true,
    allow_undo: true,
    metadata_key: 'schauwerk_action',
  },
  provider_fallbacks: {
    document: 'layout_document',
    table: 'layout_grid',
    code_widget: 'layout_code_panel',
    prototype: 'ordered_frames',
  },
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

test('validates the public runtime configuration and narrow write policy', () => {
  assert.equal(core.assertCompanionConfig(config), config);
  assert.deepEqual(core.companionWritePolicy(config), config.write_actions);
  assert.deepEqual(core.providerFallbacks(config), config.provider_fallbacks);
  assert.throws(() => core.assertCompanionConfig({ ...config, panel_height: 20 }), /panel_height/);
  assert.throws(
    () => core.assertCompanionConfig({
      ...config,
      write_actions: { ...config.write_actions, require_confirmation: false },
    }),
    /confirmation/,
  );
});

test('creates action sessions only from cryptographic randomness', () => {
  assert.equal(
    core.createActionSessionId({ crypto: { randomUUID: () => '12345678-1234-4234-8234-123456789abc' } }),
    '12345678-1234-4234-8234-123456789abc',
  );
  const fallback = core.createActionSessionId({
    crypto: {
      getRandomValues: (bytes) => {
        bytes.fill(17);
        return bytes;
      },
    },
  });
  assert.match(fallback, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.throws(() => core.createActionSessionId({}), /Secure action session/);
});

test('detects Miro only inside an SDK-enabled iframe', () => {
  const topLevel = { miro: { board: {} } };
  topLevel.parent = topLevel;
  assert.equal(core.isMiroEmbedded(topLevel), false);
  assert.equal(core.isMiroEmbedded({ parent: {}, miro: { board: {} } }), true);
  assert.equal(core.isMiroEmbedded({ parent: {} }), false);
});

test('sorts and filters frames in deterministic reading order', () => {
  const frames = core.sortFrames(
    [
      { id: 'c', type: 'frame', title: 'C', x: 500, y: 100 },
      { id: 'b', type: 'frame', title: 'Beta', x: 300, y: 0 },
      { id: 'a', type: 'frame', title: 'Alpha', x: 100, y: 0 },
      { id: 'ignored', type: 'text', content: 'Ignored', x: 0, y: 0 },
    ],
    10,
  );
  assert.deepEqual(frames.map((frame) => frame.id), ['a', 'b', 'c']);
  assert.deepEqual(core.filterFrames(frames, 'alp').map((frame) => frame.id), ['a']);
});

test('summarizes labels, selection, and item types without markup', () => {
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
  assert.deepEqual(
    core.summarizeTypes([{ type: 'text' }, { type: 'shape' }, { type: 'text' }]),
    [{ type: 'text', count: 2 }, { type: 'shape', count: 1 }],
  );
});

test('builds a deterministic review card at viewport center and escapes labels', () => {
  const draft = core.buildReviewCardDraft(
    config,
    [{ id: '1', type: 'text', content: '<img src=x onerror=1>Auswahl' }],
    { x: 10, y: 20, width: 200, height: 100 },
  );
  assert.equal(draft.x, 110);
  assert.equal(draft.y, 70);
  assert.equal(draft.title, 'Schauwerk-Abnahme · verified');
  assert.ok(draft.description.includes('text: Auswahl'));
  assert.ok(!draft.description.includes('<img'));
});

test('binds undo ownership to one action session', () => {
  const metadata = core.buildActionMetadata(config, 'session-12345678');
  assert.equal(core.ownsActionMetadata(metadata, 'session-12345678'), true);
  assert.equal(core.ownsActionMetadata(metadata, 'other-session'), false);
  assert.equal(core.ownsActionMetadata({ ...metadata, action: 'delete_anything' }, 'session-12345678'), false);
});

test('clamps presentation positions and redacts long digests', () => {
  assert.equal(core.clampFrameIndex(-2, 4), 0);
  assert.equal(core.clampFrameIndex(9, 4), 3);
  assert.equal(core.shortDigest('f'.repeat(64)), `${'f'.repeat(12)}…`);
  assert.equal(core.statusTone('failed'), 'bad');
});
