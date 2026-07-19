const HEX64 = /^[0-9a-f]{64}$/;
const ACTIONS = new Set(['create_review_card']);
const FALLBACKS = Object.freeze({
  document: 'layout_document',
  table: 'layout_grid',
  code_widget: 'layout_code_panel',
  prototype: 'ordered_frames',
});

export function isMiroEmbedded(scope = globalThis) {
  return Boolean(scope && scope.parent && scope.parent !== scope && scope.miro?.board);
}

export function createActionSessionId(scope = globalThis) {
  const crypto = scope?.crypto;
  if (typeof crypto?.randomUUID === 'function') return crypto.randomUUID();
  if (typeof crypto?.getRandomValues !== 'function') {
    throw new Error('Secure action session generation is unavailable');
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function companionWritePolicy(config) {
  const value = config?.write_actions;
  if (value === undefined) {
    return {
      enabled: false,
      allowed: [],
      require_confirmation: true,
      allow_undo: false,
      metadata_key: 'schauwerk_action',
    };
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid write_actions');
  }
  if (typeof value.enabled !== 'boolean') throw new Error('Invalid write_actions.enabled');
  if (!Array.isArray(value.allowed) || value.allowed.some((action) => !ACTIONS.has(action))) {
    throw new Error('Invalid write_actions.allowed');
  }
  if (new Set(value.allowed).size !== value.allowed.length) {
    throw new Error('Duplicate write action');
  }
  if (typeof value.require_confirmation !== 'boolean') {
    throw new Error('Invalid write_actions.require_confirmation');
  }
  if (typeof value.allow_undo !== 'boolean') throw new Error('Invalid write_actions.allow_undo');
  if (
    typeof value.metadata_key !== 'string'
    || !/^[a-z][a-z0-9_]{2,63}$/.test(value.metadata_key)
  ) {
    throw new Error('Invalid write_actions.metadata_key');
  }
  if (value.enabled && !value.allowed.includes('create_review_card')) {
    throw new Error('Enabled write actions require create_review_card');
  }
  if (value.enabled && !value.require_confirmation) {
    throw new Error('Enabled write actions require confirmation');
  }
  return {
    enabled: value.enabled,
    allowed: [...value.allowed],
    require_confirmation: value.require_confirmation,
    allow_undo: value.allow_undo,
    metadata_key: value.metadata_key,
  };
}

export function providerFallbacks(config) {
  const value = config?.provider_fallbacks;
  if (value === undefined) return { ...FALLBACKS };
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid provider_fallbacks');
  }
  const keys = Object.keys(FALLBACKS);
  if (Object.keys(value).length !== keys.length) throw new Error('Incomplete provider_fallbacks');
  for (const key of keys) {
    if (value[key] !== FALLBACKS[key]) throw new Error(`Invalid provider fallback: ${key}`);
  }
  return { ...value };
}

export function assertCompanionConfig(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Companion configuration must be an object');
  }
  if (value.schema_version !== 'schauwerk-miro-web-sdk-companion.v1') {
    throw new Error('Unsupported companion schema version');
  }
  for (const key of ['app_name', 'panel_title']) {
    if (typeof value[key] !== 'string' || value[key].trim() === '') {
      throw new Error(`Invalid ${key}`);
    }
  }
  if (!Number.isInteger(value.panel_height) || value.panel_height < 240 || value.panel_height > 1200) {
    throw new Error('Invalid panel_height');
  }
  if (!Number.isInteger(value.max_frames) || value.max_frames < 1 || value.max_frames > 200) {
    throw new Error('Invalid max_frames');
  }
  if (!Number.isInteger(value.selection_limit) || value.selection_limit < 1 || value.selection_limit > 50) {
    throw new Error('Invalid selection_limit');
  }
  if (typeof value.show_board_id !== 'boolean') throw new Error('Invalid show_board_id');
  companionWritePolicy(value);
  providerFallbacks(value);
  const status = value.status;
  if (!status || typeof status !== 'object' || Array.isArray(status)) throw new Error('Invalid status');
  if (!['verified', 'degraded', 'failed', 'unknown'].includes(status.state)) {
    throw new Error('Invalid status state');
  }
  if (status.quality_score !== null && (!Number.isInteger(status.quality_score) || status.quality_score < 0 || status.quality_score > 100)) {
    throw new Error('Invalid quality score');
  }
  for (const key of ['operation_count', 'completed_operation_count']) {
    if (!Number.isInteger(status[key]) || status[key] < 0 || status[key] > 100000) {
      throw new Error(`Invalid ${key}`);
    }
  }
  if (status.completed_operation_count > status.operation_count) {
    throw new Error('Completed operation count exceeds operation count');
  }
  for (const key of ['snapshot_digest', 'execution_digest']) {
    if (status[key] !== null && (typeof status[key] !== 'string' || !HEX64.test(status[key]))) {
      throw new Error(`Invalid ${key}`);
    }
  }
  if (!Array.isArray(status.findings) || status.findings.length > 20 || status.findings.some((item) => typeof item !== 'string' || item.trim() === '')) {
    throw new Error('Invalid findings');
  }
  if (
    status.state === 'verified'
    && (
      status.quality_score === null
      || status.quality_score < 1
      || status.completed_operation_count !== status.operation_count
      || status.snapshot_digest === null
      || status.execution_digest === null
    )
  ) {
    throw new Error('Verified status requires complete positive evidence');
  }
  return value;
}

export function itemLabel(item) {
  if (!item || typeof item !== 'object') return 'Unbekanntes Objekt';
  for (const key of ['title', 'content', 'description']) {
    const candidate = item[key];
    if (typeof candidate === 'string') {
      const plain = candidate.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
      if (plain) return plain.slice(0, 80);
    }
  }
  return String(item.type || 'Objekt');
}

export function summarizeItems(items, limit) {
  if (!Array.isArray(items)) return [];
  return items.slice(0, limit).map((item) => ({
    id: typeof item?.id === 'string' ? item.id : '',
    type: typeof item?.type === 'string' ? item.type : 'unsupported',
    label: itemLabel(item),
  }));
}

export function summarizeTypes(items) {
  const counts = new Map();
  for (const item of Array.isArray(items) ? items : []) {
    const type = typeof item?.type === 'string' ? item.type : 'unsupported';
    counts.set(type, (counts.get(type) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'de'))
    .map(([type, count]) => ({ type, count }));
}

export function sortFrames(items, limit) {
  if (!Array.isArray(items)) return [];
  return [...items]
    .filter((item) => item && item.type === 'frame' && typeof item.id === 'string')
    .sort((left, right) => {
      const ly = Number.isFinite(left.y) ? left.y : 0;
      const ry = Number.isFinite(right.y) ? right.y : 0;
      if (ly !== ry) return ly - ry;
      const lx = Number.isFinite(left.x) ? left.x : 0;
      const rx = Number.isFinite(right.x) ? right.x : 0;
      if (lx !== rx) return lx - rx;
      return itemLabel(left).localeCompare(itemLabel(right), 'de');
    })
    .slice(0, limit);
}

export function filterFrames(frames, query) {
  const normalized = String(query || '').trim().toLocaleLowerCase('de');
  if (!normalized) return [...frames];
  return frames.filter((frame) => itemLabel(frame).toLocaleLowerCase('de').includes(normalized));
}

export function clampFrameIndex(index, length) {
  if (!Number.isInteger(index) || length <= 0) return 0;
  return Math.max(0, Math.min(index, length - 1));
}

export function shortDigest(value) {
  return typeof value === 'string' && HEX64.test(value) ? `${value.slice(0, 12)}…` : '—';
}

export function statusTone(state) {
  if (state === 'verified') return 'good';
  if (state === 'degraded' || state === 'unknown') return 'warn';
  return 'bad';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function buildReviewCardDraft(config, selection, viewport) {
  const centerX = Number(viewport?.x) + Number(viewport?.width) / 2;
  const centerY = Number(viewport?.y) + Number(viewport?.height) / 2;
  if (![centerX, centerY].every(Number.isFinite)) throw new Error('Invalid viewport');
  const selected = summarizeItems(selection, 5);
  const scope = selected.length
    ? selected.map((item) => `${item.type}: ${item.label}`).join(' · ')
    : 'Gesamtes Board';
  const status = config.status;
  const title = `Schauwerk-Abnahme · ${status.state}`;
  const description = [
    `<p><strong>${escapeHtml(config.panel_title)}</strong></p>`,
    `<p>Qualität: ${status.quality_score === null ? '—' : status.quality_score}/100 · Operationen: ${status.completed_operation_count}/${status.operation_count}</p>`,
    `<p>Bezug: ${escapeHtml(scope)}</p>`,
    `<p>Snapshot: ${escapeHtml(shortDigest(status.snapshot_digest))} · Ausführung: ${escapeHtml(shortDigest(status.execution_digest))}</p>`,
  ].join('');
  return { title, description, x: centerX, y: centerY, width: 360 };
}

export function buildActionMetadata(config, sessionId) {
  if (typeof sessionId !== 'string' || sessionId.length < 8 || sessionId.length > 100) {
    throw new Error('Invalid action session');
  }
  return {
    schema_version: 'schauwerk-miro-action.v1',
    action: 'create_review_card',
    session_id: sessionId,
    snapshot_digest: config.status.snapshot_digest,
    execution_digest: config.status.execution_digest,
  };
}

export function ownsActionMetadata(value, sessionId) {
  return Boolean(
    value
    && typeof value === 'object'
    && value.schema_version === 'schauwerk-miro-action.v1'
    && value.action === 'create_review_card'
    && value.session_id === sessionId
  );
}
