const HEX64 = /^[0-9a-f]{64}$/;

export function isMiroEmbedded(scope = globalThis) {
  return Boolean(scope && scope.parent && scope.parent !== scope && scope.miro?.board);
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
  if (typeof value.show_board_id !== 'boolean') {
    throw new Error('Invalid show_board_id');
  }
  const status = value.status;
  if (!status || typeof status !== 'object' || Array.isArray(status)) {
    throw new Error('Invalid status');
  }
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
