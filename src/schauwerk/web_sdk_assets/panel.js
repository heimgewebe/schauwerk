import {
  assertCompanionConfig,
  buildActionMetadata,
  buildReviewCardDraft,
  clampFrameIndex,
  companionWritePolicy,
  createActionSessionId,
  filterFrames,
  isMiroEmbedded,
  itemLabel,
  ownsActionMetadata,
  providerFallbacks,
  shortDigest,
  sortFrames,
  statusTone,
  summarizeItems,
  summarizeTypes,
} from './core.js';

const nodeIds = [
  'panel-title', 'mode-badge', 'state-badge', 'quality-score', 'operation-count',
  'snapshot-digest', 'execution-digest', 'findings', 'refresh-button', 'board-summary',
  'board-id', 'inventory-total', 'inventory-types', 'selection-list', 'focus-selection',
  'frame-search', 'frame-position', 'frame-title', 'previous-frame', 'focus-frame',
  'next-frame', 'fallback-list', 'write-badge', 'write-summary', 'preview-write',
  'write-preview', 'write-preview-title', 'write-preview-description', 'write-confirm',
  'execute-write', 'undo-write', 'write-receipt', 'error-message',
];
const nodes = Object.fromEntries(nodeIds.map((id) => [id, document.getElementById(id)]));

const state = {
  config: null,
  embedded: isMiroEmbedded(globalThis),
  selection: [],
  items: [],
  frames: [],
  filteredFrames: [],
  frameIndex: 0,
  selectionHandler: null,
  writePolicy: null,
  draft: null,
  lastCreated: null,
  sessionId: null,
};

function setError(message) {
  nodes['error-message'].textContent = message;
  nodes['error-message'].hidden = false;
}

function clearError() {
  nodes['error-message'].hidden = true;
  nodes['error-message'].textContent = '';
}

function setWriteReceipt(message, tone = 'neutral') {
  nodes['write-receipt'].textContent = message;
  nodes['write-receipt'].dataset.tone = tone;
  nodes['write-receipt'].hidden = false;
}

async function loadConfig() {
  let panelData;
  if (state.embedded && globalThis.miro.board.ui?.getPanelData) {
    panelData = await globalThis.miro.board.ui.getPanelData();
  }
  const configUrl = panelData && typeof panelData.config_url === 'string'
    ? panelData.config_url
    : './config.json';
  const response = await fetch(configUrl, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Konfiguration nicht verfügbar: HTTP ${response.status}`);
  return assertCompanionConfig(await response.json());
}

function renderStatus() {
  const status = state.config.status;
  nodes['panel-title'].textContent = state.config.panel_title;
  nodes['state-badge'].textContent = status.state;
  nodes['state-badge'].dataset.tone = statusTone(status.state);
  nodes['quality-score'].textContent = status.quality_score === null ? '—' : `${status.quality_score} / 100`;
  nodes['operation-count'].textContent = `${status.completed_operation_count} / ${status.operation_count}`;
  nodes['snapshot-digest'].textContent = shortDigest(status.snapshot_digest);
  nodes['execution-digest'].textContent = shortDigest(status.execution_digest);
  nodes.findings.replaceChildren();
  const findings = status.findings.length ? status.findings : ['Keine offenen Befunde.'];
  for (const finding of findings) {
    const item = document.createElement('li');
    item.textContent = finding;
    nodes.findings.append(item);
  }
}

function renderInventory() {
  nodes['inventory-total'].textContent = `${state.items.length} Objekte`;
  nodes['inventory-types'].replaceChildren();
  for (const entry of summarizeTypes(state.items).slice(0, 12)) {
    const item = document.createElement('li');
    item.textContent = `${entry.type} · ${entry.count}`;
    nodes['inventory-types'].append(item);
  }
}

function renderSelection() {
  nodes['selection-list'].replaceChildren();
  const summarized = summarizeItems(state.selection, state.config.selection_limit);
  const values = summarized.length
    ? summarized
    : [{ type: state.embedded ? 'leer' : 'standalone', label: state.embedded ? 'Keine Boardobjekte ausgewählt.' : 'Kein Miro-Kontext.' }];
  for (const selected of values) {
    const item = document.createElement('li');
    const label = document.createElement('strong');
    label.textContent = selected.label;
    const type = document.createElement('span');
    type.className = 'muted';
    type.textContent = selected.type;
    item.append(label, type);
    nodes['selection-list'].append(item);
  }
  nodes['focus-selection'].disabled = !state.embedded || state.selection.length === 0;
}

function renderFrames() {
  state.filteredFrames = filterFrames(state.frames, nodes['frame-search'].value);
  const length = state.filteredFrames.length;
  state.frameIndex = clampFrameIndex(state.frameIndex, length);
  const frame = length > 0 ? state.filteredFrames[state.frameIndex] : null;
  nodes['frame-position'].textContent = length > 0 ? `${state.frameIndex + 1} / ${length}` : '0 / 0';
  nodes['frame-title'].textContent = frame ? itemLabel(frame) : 'Keine passenden Frames.';
  nodes['previous-frame'].disabled = !state.embedded || state.frameIndex === 0 || length === 0;
  nodes['next-frame'].disabled = !state.embedded || length === 0 || state.frameIndex >= length - 1;
  nodes['focus-frame'].disabled = !state.embedded || !frame;
}

function renderFallbacks() {
  nodes['fallback-list'].replaceChildren();
  const labels = {
    document: 'Dokument → editierbarer Layout-Text',
    table: 'Tabelle → editierbares Layout-Raster',
    code_widget: 'Code-Widget → editierbares Code-Panel',
    prototype: 'Prototyp → geordnete Frames',
  };
  for (const [kind, fallback] of Object.entries(providerFallbacks(state.config))) {
    const item = document.createElement('li');
    item.textContent = `${labels[kind]} (${fallback})`;
    nodes['fallback-list'].append(item);
  }
}

function renderWrite() {
  const enabled = state.embedded && state.writePolicy.enabled
    && state.writePolicy.allowed.includes('create_review_card');
  nodes['write-badge'].textContent = enabled ? 'Bestätigt schreiben' : 'Nur lesen';
  nodes['write-badge'].dataset.tone = enabled ? 'warn' : 'neutral';
  nodes['write-summary'].textContent = enabled
    ? 'Eine app-eigene Abnahmekarte kann nach Vorschau und Bestätigung angelegt werden. Keine automatische oder freie Boardmutation.'
    : 'Schreibaktionen sind in diesem Kontext deaktiviert.';
  nodes['preview-write'].disabled = !enabled;
  nodes['write-confirm'].disabled = !enabled || !state.draft;
  nodes['execute-write'].disabled = !enabled || !state.draft
    || (state.writePolicy.require_confirmation && !nodes['write-confirm'].checked);
  nodes['undo-write'].disabled = !enabled || !state.writePolicy.allow_undo || !state.lastCreated;
}

async function refreshBoardContext() {
  clearError();
  if (!state.embedded) {
    nodes['mode-badge'].textContent = 'Standalone';
    nodes['mode-badge'].dataset.tone = 'warn';
    nodes['board-summary'].textContent = 'Kein eingebetteter Miro-Kontext. Receipt und Qualitätsstand bleiben lesbar.';
    renderInventory(); renderSelection(); renderFrames(); renderWrite();
    return;
  }
  const board = globalThis.miro.board;
  const [info, selection, frames, items] = await Promise.all([
    board.getInfo(), board.getSelection(), board.get({ type: 'frame' }), board.get(),
  ]);
  state.selection = Array.isArray(selection) ? selection : [];
  state.frames = sortFrames(frames, state.config.max_frames);
  state.items = Array.isArray(items) ? items : [];
  nodes['mode-badge'].textContent = 'Miro live';
  nodes['mode-badge'].dataset.tone = 'good';
  const locale = typeof info?.locale === 'string' ? info.locale : 'unbekannt';
  const updatedAt = typeof info?.updatedAt === 'string' ? info.updatedAt : 'unbekannt';
  nodes['board-summary'].textContent = `Locale ${locale}; zuletzt geändert ${updatedAt}.`;
  if (state.config.show_board_id && typeof info?.id === 'string') {
    nodes['board-id'].textContent = info.id;
    nodes['board-id'].hidden = false;
  } else {
    nodes['board-id'].hidden = true;
  }
  renderInventory(); renderSelection(); renderFrames(); renderWrite();
}

async function focusItems(items) {
  if (!state.embedded || items.length === 0) return;
  await globalThis.miro.board.viewport.zoomTo(items);
}

async function initialize() {
  try {
    state.config = await loadConfig();
    state.writePolicy = companionWritePolicy(state.config);
    state.sessionId = state.writePolicy.enabled ? createActionSessionId(globalThis) : null;
    document.title = state.config.panel_title;
    renderStatus(); renderFallbacks(); renderWrite();
    await refreshBoardContext();
    if (state.embedded && globalThis.miro.board.ui?.on) {
      state.selectionHandler = (event) => {
        state.selection = Array.isArray(event?.items) ? event.items : [];
        renderSelection();
      };
      globalThis.miro.board.ui.on('selection:update', state.selectionHandler);
    }
  } catch (error) {
    setError('Schauwerk konnte den Boardkontext nicht laden.');
    console.error(error);
  }
}

nodes['refresh-button'].addEventListener('click', async () => {
  try { await refreshBoardContext(); } catch (error) { setError('Der Boardkontext konnte nicht aktualisiert werden.'); console.error(error); }
});
nodes['focus-selection'].addEventListener('click', async () => {
  try { await focusItems(state.selection); } catch (error) { setError('Die Auswahl konnte nicht fokussiert werden.'); console.error(error); }
});
nodes['frame-search'].addEventListener('input', () => { state.frameIndex = 0; renderFrames(); });
nodes['previous-frame'].addEventListener('click', () => { state.frameIndex = clampFrameIndex(state.frameIndex - 1, state.filteredFrames.length); renderFrames(); });
nodes['next-frame'].addEventListener('click', () => { state.frameIndex = clampFrameIndex(state.frameIndex + 1, state.filteredFrames.length); renderFrames(); });
nodes['focus-frame'].addEventListener('click', async () => {
  const frame = state.filteredFrames[state.frameIndex];
  try { await focusItems(frame ? [frame] : []); } catch (error) { setError('Der Frame konnte nicht fokussiert werden.'); console.error(error); }
});

nodes['preview-write'].addEventListener('click', async () => {
  try {
    clearError();
    const viewport = await globalThis.miro.board.viewport.get();
    state.draft = buildReviewCardDraft(state.config, state.selection, viewport);
    nodes['write-preview-title'].textContent = state.draft.title;
    nodes['write-preview-description'].textContent = state.draft.description.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    nodes['write-preview'].hidden = false;
    nodes['write-confirm'].checked = false;
    renderWrite();
  } catch (error) {
    setError('Die Schreibvorschau konnte nicht erstellt werden.');
    console.error(error);
  }
});

nodes['write-confirm'].addEventListener('change', renderWrite);

nodes['execute-write'].addEventListener('click', async () => {
  let card;
  try {
    clearError();
    if (!state.draft || !nodes['write-confirm'].checked) throw new Error('Write confirmation missing');
    card = await globalThis.miro.board.createCard({
      ...state.draft,
      style: { cardTheme: '#6C5CE7' },
    });
    if (!state.sessionId) throw new Error('Secure action session missing');
    const metadata = buildActionMetadata(state.config, state.sessionId);
    await card.setMetadata(state.writePolicy.metadata_key, metadata);
    const readback = await card.getMetadata(state.writePolicy.metadata_key);
    if (!ownsActionMetadata(readback, state.sessionId)) throw new Error('Metadata readback mismatch');
    state.lastCreated = { id: card.id, metadata };
    state.draft = null;
    nodes['write-preview'].hidden = true;
    nodes['write-confirm'].checked = false;
    await globalThis.miro.board.viewport.zoomTo(card);
    setWriteReceipt('PASS · Abnahmekarte angelegt und app-eigene Metadaten verifiziert.', 'good');
    await refreshBoardContext();
  } catch (error) {
    let rollbackFailed = false;
    if (card) {
      try {
        await globalThis.miro.board.remove(card);
        const rollbackReadback = await globalThis.miro.board.get({ id: card.id });
        rollbackFailed = Array.isArray(rollbackReadback) && rollbackReadback.length > 0;
      } catch (rollbackError) {
        rollbackFailed = true;
        console.error(rollbackError);
      }
    }
    state.lastCreated = null;
    setError(
      rollbackFailed
        ? 'Mutation unklar: Die Karte konnte nach dem Fehler nicht sicher zurückgerollt werden. Board manuell prüfen.'
        : 'Die bestätigte Abnahmekarte wurde nicht angelegt oder vollständig zurückgerollt.',
    );
    console.error(error);
  }
});

nodes['undo-write'].addEventListener('click', async () => {
  let removalStarted = false;
  try {
    clearError();
    if (!state.lastCreated || !state.sessionId) throw new Error('No session-owned item');
    const items = await globalThis.miro.board.get({ id: state.lastCreated.id });
    const item = Array.isArray(items) ? items[0] : null;
    if (!item) throw new Error('Created item is absent');
    const metadata = await item.getMetadata(state.writePolicy.metadata_key);
    if (!ownsActionMetadata(metadata, state.sessionId)) throw new Error('Item is not owned by this action session');
    removalStarted = true;
    await globalThis.miro.board.remove(item);
    const after = await globalThis.miro.board.get({ id: state.lastCreated.id });
    if (Array.isArray(after) && after.length) throw new Error('Removal readback failed');
    state.lastCreated = null;
    setWriteReceipt('PASS · Letzte Companion-Aktion vollständig rückgängig gemacht.', 'good');
    await refreshBoardContext();
  } catch (error) {
    setError(
      removalStarted
        ? 'Mutation unklar: Undo wurde begonnen, aber nicht eindeutig zurückgelesen. Board manuell prüfen.'
        : 'Undo wurde verweigert: Das Ziel ist nicht eindeutig dieser Companion-Sitzung zugeordnet.',
    );
    console.error(error);
  }
});

window.addEventListener('pagehide', () => {
  if (state.embedded && state.selectionHandler && globalThis.miro.board.ui?.off) {
    globalThis.miro.board.ui.off('selection:update', state.selectionHandler);
  }
});

initialize();
