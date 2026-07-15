import {
  assertCompanionConfig,
  clampFrameIndex,
  isMiroEmbedded,
  itemLabel,
  shortDigest,
  sortFrames,
  statusTone,
  summarizeItems,
} from './core.js';

const nodes = Object.fromEntries(
  [
    'panel-title',
    'mode-badge',
    'state-badge',
    'quality-score',
    'operation-count',
    'snapshot-digest',
    'execution-digest',
    'findings',
    'refresh-button',
    'board-summary',
    'board-id',
    'selection-list',
    'focus-selection',
    'frame-position',
    'frame-title',
    'previous-frame',
    'focus-frame',
    'next-frame',
    'error-message',
  ].map((id) => [id, document.getElementById(id)]),
);

const state = {
  config: null,
  embedded: isMiroEmbedded(globalThis),
  selection: [],
  frames: [],
  frameIndex: 0,
  selectionHandler: null,
};

function setError(message) {
  nodes['error-message'].textContent = message;
  nodes['error-message'].hidden = false;
}

function clearError() {
  nodes['error-message'].hidden = true;
  nodes['error-message'].textContent = '';
}

async function loadConfig() {
  let panelData;
  if (state.embedded && globalThis.miro.board.ui?.getPanelData) {
    panelData = await globalThis.miro.board.ui.getPanelData();
  }
  const configUrl =
    panelData && typeof panelData.config_url === 'string' ? panelData.config_url : './config.json';
  const response = await fetch(configUrl, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Konfiguration nicht verfügbar: HTTP ${response.status}`);
  return assertCompanionConfig(await response.json());
}

function renderStatus() {
  const config = state.config;
  const status = config.status;
  nodes['panel-title'].textContent = config.panel_title;
  nodes['state-badge'].textContent = status.state;
  nodes['state-badge'].dataset.tone = statusTone(status.state);
  nodes['quality-score'].textContent =
    status.quality_score === null ? '—' : `${status.quality_score} / 100`;
  nodes['operation-count'].textContent =
    `${status.completed_operation_count} / ${status.operation_count}`;
  nodes['snapshot-digest'].textContent = shortDigest(status.snapshot_digest);
  nodes['execution-digest'].textContent = shortDigest(status.execution_digest);
  nodes.findings.replaceChildren();
  if (status.findings.length === 0) {
    const item = document.createElement('li');
    item.textContent = 'Keine offenen Befunde.';
    nodes.findings.append(item);
  } else {
    for (const finding of status.findings) {
      const item = document.createElement('li');
      item.textContent = finding;
      nodes.findings.append(item);
    }
  }
}

function renderSelection() {
  nodes['selection-list'].replaceChildren();
  const summarized = summarizeItems(state.selection, state.config.selection_limit);
  if (summarized.length === 0) {
    const item = document.createElement('li');
    item.textContent = state.embedded ? 'Keine Boardobjekte ausgewählt.' : 'Standalone ohne Auswahl.';
    nodes['selection-list'].append(item);
  } else {
    for (const selected of summarized) {
      const item = document.createElement('li');
      const label = document.createElement('strong');
      label.textContent = selected.label;
      const type = document.createElement('span');
      type.className = 'muted';
      type.textContent = selected.type;
      item.append(label, type);
      nodes['selection-list'].append(item);
    }
  }
  nodes['focus-selection'].disabled = !state.embedded || state.selection.length === 0;
}

function renderFrames() {
  const length = state.frames.length;
  state.frameIndex = clampFrameIndex(state.frameIndex, length);
  const frame = length > 0 ? state.frames[state.frameIndex] : null;
  nodes['frame-position'].textContent = length > 0 ? `${state.frameIndex + 1} / ${length}` : '0 / 0';
  nodes['frame-title'].textContent = frame ? itemLabel(frame) : 'Keine Frames verfügbar.';
  nodes['previous-frame'].disabled = !state.embedded || length === 0 || state.frameIndex === 0;
  nodes['next-frame'].disabled =
    !state.embedded || length === 0 || state.frameIndex >= length - 1;
  nodes['focus-frame'].disabled = !state.embedded || !frame;
}

async function refreshBoardContext() {
  clearError();
  if (!state.embedded) {
    nodes['mode-badge'].textContent = 'Standalone';
    nodes['mode-badge'].dataset.tone = 'warn';
    nodes['board-summary'].textContent =
      'Kein eingebetteter Miro-Boardkontext verfügbar. Receipt und Qualitätsstand bleiben lesbar.';
    renderSelection();
    renderFrames();
    return;
  }
  const board = globalThis.miro.board;
  const [info, selection, frames] = await Promise.all([
    board.getInfo(),
    board.getSelection(),
    board.get({ type: 'frame' }),
  ]);
  state.selection = Array.isArray(selection) ? selection : [];
  state.frames = sortFrames(frames, state.config.max_frames);
  state.frameIndex = clampFrameIndex(state.frameIndex, state.frames.length);
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
  renderSelection();
  renderFrames();
}

async function focusItems(items) {
  if (!state.embedded || items.length === 0) return;
  await globalThis.miro.board.viewport.zoomTo(items);
}

async function initialize() {
  try {
    state.config = await loadConfig();
    document.title = state.config.panel_title;
    renderStatus();
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
  try {
    await refreshBoardContext();
  } catch (error) {
    setError('Der Boardkontext konnte nicht aktualisiert werden.');
    console.error(error);
  }
});

nodes['focus-selection'].addEventListener('click', async () => {
  try {
    await focusItems(state.selection);
  } catch (error) {
    setError('Die Auswahl konnte nicht fokussiert werden.');
    console.error(error);
  }
});

nodes['previous-frame'].addEventListener('click', () => {
  state.frameIndex = clampFrameIndex(state.frameIndex - 1, state.frames.length);
  renderFrames();
});

nodes['next-frame'].addEventListener('click', () => {
  state.frameIndex = clampFrameIndex(state.frameIndex + 1, state.frames.length);
  renderFrames();
});

nodes['focus-frame'].addEventListener('click', async () => {
  const frame = state.frames[state.frameIndex];
  try {
    await focusItems(frame ? [frame] : []);
  } catch (error) {
    setError('Der Frame konnte nicht fokussiert werden.');
    console.error(error);
  }
});

window.addEventListener('pagehide', () => {
  if (state.embedded && state.selectionHandler && globalThis.miro.board.ui?.off) {
    globalThis.miro.board.ui.off('selection:update', state.selectionHandler);
  }
});

initialize();
