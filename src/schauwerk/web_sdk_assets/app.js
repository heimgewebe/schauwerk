import { assertCompanionConfig, isMiroEmbedded } from './core.js';

const statusNode = document.querySelector('#launcher-status');
const standaloneLink = document.querySelector('#standalone-link');

async function loadConfig() {
  const response = await fetch('./config.json', { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Konfiguration nicht verfügbar: HTTP ${response.status}`);
  return assertCompanionConfig(await response.json());
}

async function openCompanionPanel(config) {
  const ui = globalThis.miro?.board?.ui;
  if (!ui) throw new Error('Miro Web SDK ist nicht verfügbar');
  if (!(await ui.canOpenPanel())) {
    await globalThis.miro.board.notifications?.showError?.('Ein anderes Miro-Panel blockiert Schauwerk.');
    return;
  }
  await ui.openPanel({
    url: './panel.html',
    height: config.panel_height,
    data: { config_url: './config.json' },
  });
}

async function initialize() {
  try {
    const config = await loadConfig();
    document.title = config.app_name;
    const ui = globalThis.miro?.board?.ui;
    if (!isMiroEmbedded(globalThis) || !ui?.on) {
      statusNode.textContent = 'Standalone-Modus: Kein eingebetteter Miro-Kontext erkannt.';
      standaloneLink.hidden = false;
      return;
    }
    ui.on('icon:click', async () => {
      try {
        await openCompanionPanel(config);
      } catch (error) {
        await globalThis.miro.board.notifications?.showError?.('Schauwerk konnte nicht geöffnet werden.');
        console.error(error);
      }
    });
    statusNode.textContent = 'Bereit. Öffne Schauwerk über das App-Symbol in Miro.';
  } catch (error) {
    statusNode.textContent = 'Die Begleitanwendung konnte nicht initialisiert werden.';
    standaloneLink.hidden = false;
    console.error(error);
  }
}

initialize();
