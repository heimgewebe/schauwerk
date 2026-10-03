"""Source assets for the no-build standalone diagram editor spike."""
# ruff: noqa: E501

from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <title>Schaubild</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="app-shell">
    <header class="topline">
      <a class="brand" href="#" id="homeLink" aria-label="Zur Startseite">
        <span class="brand-mark" aria-hidden="true">S</span>
        <span class="brand-copy"><strong>Schaubild</strong><small>von Schauwerk</small></span>
      </a>
      <div class="topline-meta">
        <span class="product-badge">Visueller Arbeitsraum</span>
        <span class="status" id="status" role="status" aria-live="polite">Bereit</span>
      </div>
    </header>

    <section class="start-card" id="startView">
      <div class="start-layout">
        <div class="intro">
          <p class="eyebrow">Schaubild</p>
          <h1>Vom Gedanken zum Schaubild.</h1>
          <p class="lede">Struktur rein, Schaubild auf. Öffne Mermaid, JSON Canvas, draw.io oder Schauwerk-Daten – direkt in einem Arbeitsraum.</p>
          <div class="format-strip" aria-label="Unterstützte Eingaben">
            <span>Mermaid</span>
            <span>JSON Canvas</span>
            <span>draw.io</span>
          </div>
          <button class="restore-button" id="restoreButton" type="button" hidden>
            <span class="restore-icon" aria-hidden="true">↺</span>
            Letzten lokalen Entwurf öffnen
          </button>
        </div>

        <div class="import-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-kicker">Neues Schaubild</p>
              <h2>Was möchtest du sichtbar machen?</h2>
            </div>
            <span class="shortcut-hint">⌘ / Ctrl + Enter</span>
          </div>

          <label class="paste-box" for="sourceInput">
            <span class="visually-hidden">KI-Ergebnis hier einfügen</span>
            <textarea id="sourceInput" spellcheck="false" placeholder="Mermaid, JSON Canvas, draw.io oder Schauwerk-Daten hier einfügen …"></textarea>
          </label>

          <div class="primary-actions">
            <button class="button primary" id="openPasteButton" type="button">Schaubild öffnen</button>
            <button class="button" id="fileButton" type="button">Datei wählen</button>
            <button class="button ghost" id="blankButton" type="button">Leeres Schaubild</button>
            <button class="button ghost" id="legacyFallbackButton" type="button" hidden>Im Kompatibilitätsmodus öffnen</button>
            <input id="fileInput" type="file" hidden>
          </div>

          <p class="error" id="error" role="alert" hidden></p>

          <details class="advanced-settings">
            <summary>Import &amp; Kompatibilität</summary>
            <div class="advanced-settings-body">
              <label class="font-default-control" for="fontDefaultInput">
                <span>Schriftgröße für neue Kompatibilitäts-Elemente</span>
                <span class="numeric-control">
                  <input id="fontDefaultInput" type="number" min="8" max="72" step="1" inputmode="numeric" aria-describedby="fontDefaultHint">
                  <span>px</span>
                </span>
              </label>
              <p class="field-hint" id="fontDefaultHint">Gilt nur für neu erzeugte Elemente im Kompatibilitätseditor. Bestehende Formatierungen bleiben unverändert.</p>
              <div class="advanced-utility-actions">
                <!-- SCHAUWERK_AI_HANDOFF_ACTION -->
              </div>
              <aside class="boundary-note">
                <strong>Technischer Kompatibilitätsmodus:</strong> Kanonische Schauwerk-Repräsentationen, <code>.canvas</code>/JSON Canvas
                und der semantisch importierbare draw.io-Graphpfad laufen nativ über
                <code>schauwerk-native-diagram-v1</code>. Formate, die nicht verlustarm nativ bearbeitet werden können,
                bleiben über den ausdrücklich gewählten Kompatibilitätseditor erreichbar.
              </aside>
            </div>
          </details>
        </div>
      </div>
    </section>

    <section class="workspace" id="workspace" hidden>
      <nav class="workspace-bar" aria-label="Schaubildaktionen">
        <div class="workspace-leading">
          <button class="button compact ghost icon-button" id="backButton" type="button" aria-label="Zurück zum Start">←</button>
          <div class="document-meta">
            <span class="document-kicker">Arbeitsfläche</span>
            <strong class="document-title" id="documentTitle">Schaubild</strong>
          </div>
        </div>

        <div class="font-controls" role="group" aria-label="Schriftgröße">
          <button class="button compact tool-button" id="fontDecreaseButton" type="button" aria-label="Schriftgröße der Auswahl verkleinern" title="Ausgewählte Beschriftungen verkleinern">A−</button>
          <button class="button compact tool-button" id="fontPanelButton" type="button" title="Textformatierung für die Auswahl öffnen">Text</button>
          <button class="button compact tool-button" id="fontIncreaseButton" type="button" aria-label="Schriftgröße der Auswahl vergrößern" title="Ausgewählte Beschriftungen vergrößern">A+</button>
          <button class="button compact tool-button" id="fontAllButton" type="button" title="Gesamtes Schaubild auswählen und Textformatierung öffnen">Alles</button>
        </div>

        <div class="workspace-tools">
          <button class="button compact" id="layoutButton" type="button">Ordnen</button>
          <button class="button compact" id="contentEditButton" type="button" hidden>Inhalt</button>
          <button class="button compact ghost" id="legacyEditButton" type="button" hidden>Kompatibilität</button>
          <button class="button compact ghost" id="nativeRetryButton" type="button" hidden>Neu rendern</button>
        </div>

        <div class="workspace-output">
          <button class="button compact" id="projectButton" type="button">Projekt</button>
          <button class="button compact output-button" data-export="png" type="button">PNG</button>
          <button class="button compact output-button" data-export="svg" type="button">SVG</button>
          <a class="button compact primary download-link" id="downloadLink" hidden>Datei speichern</a>
          <button class="button compact fullscreen-toggle" id="fullscreenButton" type="button" aria-pressed="false" aria-label="Vollbildmodus aktivieren" title="Fokusmodus für die Bearbeitung">Fokus</button>
        </div>
      </nav>

      <div class="editor-stage">
        <div class="editor-wrap">
          <iframe
            id="editorFrame"
            title="Schaubild bearbeiten"
            sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-popups"
            allow="clipboard-read; clipboard-write"
            referrerpolicy="no-referrer"
          ></iframe>
        </div>
      </div>
    </section>

    <dialog class="content-dialog" id="contentDialog" aria-labelledby="contentDialogTitle">
      <form method="dialog">
        <div class="content-dialog-heading">
          <div>
            <p class="panel-kicker">Inhalt bearbeiten</p>
            <h2 id="contentDialogTitle">Texte im Schaubild</h2>
          </div>
          <button class="button compact ghost" value="cancel" type="submit">Schließen</button>
        </div>
        <p class="content-dialog-copy">Titel, Zweck, Gruppen, Elemente und Verbindungen bearbeiten. Struktur, Typen und Zuordnungen bleiben unverändert.</p>
        <div class="content-fields" id="contentFields"></div>
        <div class="content-dialog-actions">
          <button class="button ghost" value="cancel" type="submit">Abbrechen</button>
          <button class="button primary" id="contentSaveButton" type="button">Übernehmen</button>
        </div>
      </form>
    </dialog>
  </main>
  <script type="module" src="app.js"></script>
</body>
</html>
"""

STYLES_CSS = r""":root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color-scheme: light;
  font-synthesis: none;
  --bg: #f3f4f8;
  --surface: #ffffff;
  --surface-raised: rgba(255, 255, 255, 0.88);
  --surface-soft: #f7f7fb;
  --ink: #161827;
  --muted: #6f7280;
  --line: #e3e4ec;
  --line-strong: #d4d6e1;
  --accent: #635bff;
  --accent-strong: #5048e5;
  --accent-soft: #efeeff;
  --danger: #a12b2b;
  --danger-soft: #fff0f0;
  --shadow-lg: 0 30px 90px rgba(35, 37, 60, 0.14);
  --shadow-md: 0 12px 38px rgba(35, 37, 60, 0.10);
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { margin: 0; min-height: 100%; }
body {
  min-height: 100vh;
  min-height: 100dvh;
  color: var(--ink);
  background:
    radial-gradient(circle at 18% 4%, rgba(99, 91, 255, 0.11), transparent 34rem),
    radial-gradient(circle at 86% 18%, rgba(64, 190, 178, 0.08), transparent 30rem),
    var(--bg);
}
button, textarea, input { font: inherit; }
button { touch-action: manipulation; }
button, a, summary { -webkit-tap-highlight-color: transparent; }

.app-shell { min-height: 100vh; min-height: 100dvh; display: flex; flex-direction: column; }
.topline {
  position: relative;
  z-index: 10;
  min-height: 64px;
  padding: 10px clamp(16px, 3vw, 36px);
  display: flex;
  align-items: center;
  gap: 20px;
  border-bottom: 1px solid rgba(212, 214, 225, 0.78);
  background: rgba(247, 248, 251, 0.78);
  backdrop-filter: blur(22px) saturate(150%);
}
.brand { display: inline-flex; align-items: center; gap: 11px; color: var(--ink); text-decoration: none; }
.brand-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(145deg, #756dff, #5147e7 62%, #4039c8);
  box-shadow: 0 9px 22px rgba(99, 91, 255, 0.26);
  font-weight: 800;
  letter-spacing: -0.04em;
}
.brand-copy { display: grid; line-height: 1.05; }
.brand-copy strong { font-size: 0.98rem; letter-spacing: -0.025em; }
.brand-copy small { margin-top: 4px; color: var(--muted); font-size: 0.68rem; font-weight: 650; letter-spacing: 0.02em; }
.topline-meta { margin-left: auto; display: flex; align-items: center; gap: 10px; min-width: 0; }
.product-badge,
.status {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 10px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.72);
  font-size: 0.78rem;
  font-weight: 680;
  white-space: nowrap;
}
.status { max-width: min(42vw, 520px); overflow: hidden; text-overflow: ellipsis; }

.start-card {
  flex: 1;
  width: min(1320px, 100%);
  margin: 0 auto;
  padding: clamp(28px, 6vw, 78px) clamp(18px, 5vw, 64px);
  display: grid;
  align-items: center;
}
.start-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.86fr) minmax(440px, 1.14fr);
  gap: clamp(36px, 7vw, 96px);
  align-items: center;
}
.intro { min-width: 0; padding: 10px 0; }
.eyebrow,
.panel-kicker,
.document-kicker {
  margin: 0;
  color: var(--accent);
  font-size: 0.74rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.105em;
}
h1 {
  max-width: 720px;
  margin: 12px 0 0;
  font-size: clamp(3rem, 6.8vw, 6.9rem);
  line-height: 0.89;
  letter-spacing: -0.068em;
  text-wrap: balance;
}
.lede {
  max-width: 650px;
  margin: 25px 0 0;
  color: var(--muted);
  font-size: clamp(1.02rem, 1.7vw, 1.28rem);
  line-height: 1.55;
}
.format-strip { margin-top: 28px; display: flex; flex-wrap: wrap; gap: 8px; }
.format-strip span {
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: #555968;
  background: rgba(255, 255, 255, 0.55);
  font-size: 0.76rem;
  font-weight: 700;
}

.import-panel {
  min-width: 0;
  padding: clamp(20px, 3vw, 32px);
  border: 1px solid rgba(212, 214, 225, 0.88);
  border-radius: 28px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(28px) saturate(135%);
}
.panel-heading { display: flex; align-items: flex-start; gap: 20px; justify-content: space-between; }
.panel-heading h2 {
  margin: 7px 0 0;
  font-size: clamp(1.35rem, 2.3vw, 1.92rem);
  line-height: 1.14;
  letter-spacing: -0.035em;
}
.shortcut-hint {
  flex: 0 0 auto;
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: 0.7rem;
  font-weight: 700;
}
.paste-box { display: block; margin-top: 20px; }
.paste-box textarea {
  width: 100%;
  min-height: 280px;
  max-height: 52vh;
  resize: vertical;
  border: 1px solid var(--line-strong);
  border-radius: 18px;
  padding: 18px;
  color: var(--ink);
  background: rgba(248, 248, 252, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  font: 0.9rem/1.58 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  outline: none;
  transition: border-color 140ms ease, box-shadow 140ms ease, background 140ms ease;
}
.paste-box textarea::placeholder { color: #9b9daa; }
.paste-box textarea:focus {
  border-color: rgba(99, 91, 255, 0.72);
  background: var(--surface);
  box-shadow: 0 0 0 4px rgba(99, 91, 255, 0.12);
}
.visually-hidden {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
.primary-actions { margin-top: 14px; display: flex; flex-wrap: wrap; align-items: center; gap: 9px; }

.button {
  min-height: 42px;
  border: 1px solid var(--line-strong);
  border-radius: 11px;
  padding: 9px 14px;
  color: #303342;
  background: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  font-weight: 710;
  letter-spacing: -0.01em;
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease, box-shadow 120ms ease;
}
.button:hover { border-color: #c4c6d3; background: #f9f9fc; transform: translateY(-1px); }
.button:active { transform: translateY(0); }
.button:disabled {
  border-color: transparent;
  color: #9b9daa;
  background: rgba(244, 245, 249, 0.72);
  cursor: default;
  transform: none;
  box-shadow: none;
  opacity: 0.72;
}
.button:focus-visible,
.restore-button:focus-visible,
.advanced-settings summary:focus-visible {
  outline: 3px solid rgba(99, 91, 255, 0.28);
  outline-offset: 2px;
}
.button.primary {
  border-color: var(--accent);
  color: #fff;
  background: linear-gradient(180deg, #7068ff, var(--accent-strong));
  box-shadow: 0 8px 20px rgba(99, 91, 255, 0.22);
}
.button.primary:hover { border-color: #4b43d8; background: linear-gradient(180deg, #675fff, #4941da); }
.button.ghost { border-color: transparent; color: var(--muted); background: transparent; }
.button.ghost:hover { border-color: var(--line); color: var(--ink); background: rgba(255, 255, 255, 0.64); }
.button.compact { min-height: 36px; padding: 7px 10px; border-radius: 9px; font-size: 0.82rem; }

.restore-button {
  margin-top: 30px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 0;
  padding: 8px 0;
  color: var(--accent-strong);
  background: transparent;
  cursor: pointer;
  font-weight: 750;
}
.restore-icon {
  width: 27px;
  height: 27px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: var(--accent-soft);
}
.error {
  margin: 14px 0 0;
  padding: 12px 14px;
  border: 1px solid #f0cccc;
  border-radius: 12px;
  color: var(--danger);
  background: var(--danger-soft);
  font-size: 0.88rem;
  line-height: 1.45;
}
.advanced-settings { margin-top: 18px; border-top: 1px solid var(--line); }
.advanced-settings summary {
  padding: 15px 2px 4px;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 750;
  list-style-position: inside;
}
.advanced-settings[open] summary { color: var(--ink); }
.advanced-settings-body { padding: 12px 2px 2px; }
.advanced-utility-actions { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }
.font-default-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  font-size: 0.82rem;
  font-weight: 700;
}
.numeric-control { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); }
.font-default-control input {
  width: 68px;
  min-height: 36px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  padding: 6px 8px;
  color: var(--ink);
  background: var(--surface);
}
.field-hint { margin: 7px 0 0; color: var(--muted); font-size: 0.75rem; line-height: 1.45; }
.boundary-note {
  margin-top: 14px;
  padding: 12px 13px;
  border-radius: 11px;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: 0.76rem;
  line-height: 1.5;
}
.boundary-note code { font-size: 0.72rem; }

.workspace { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.workspace-bar {
  position: relative;
  z-index: 5;
  min-height: 62px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--line);
  background: rgba(251, 251, 253, 0.92);
  backdrop-filter: blur(22px) saturate(145%);
}
.workspace-leading { min-width: 0; display: flex; align-items: center; gap: 9px; }
.document-meta { min-width: 0; display: grid; gap: 2px; }
.document-kicker { color: #8a8d99; font-size: 0.6rem; }
.document-title {
  min-width: 0;
  max-width: min(31vw, 440px);
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
}
.icon-button { width: 36px; padding-inline: 0 !important; font-size: 1.02rem !important; }
.font-controls {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--surface-soft);
}
.font-controls .button { min-width: 38px; border-color: transparent; background: transparent; }
.font-controls .button:hover { border-color: var(--line); background: var(--surface); }
.workspace-tools,
.workspace-output {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
}
.workspace-tools,
.workspace-output { padding-left: 10px; border-left: 1px solid var(--line); }
.output-button { min-width: 46px; color: var(--muted); }
.fullscreen-toggle { white-space: nowrap; }
.download-link { display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
.download-link[hidden] { display: none; }

.content-dialog {
  width: min(760px, calc(100vw - 28px));
  max-height: min(86vh, 860px);
  border: 1px solid var(--line-strong);
  border-radius: 20px;
  padding: 0;
  color: var(--ink);
  background: var(--surface);
  box-shadow: 0 28px 90px rgba(28, 31, 48, 0.25);
}
.content-dialog::backdrop {
  background: rgba(15, 18, 30, 0.48);
  backdrop-filter: blur(4px);
}
.content-dialog form {
  max-height: min(86vh, 860px);
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
}
.content-dialog-heading,
.content-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
}
.content-dialog-heading {
  border-bottom: 1px solid var(--line);
}
.content-dialog-heading h2 {
  margin: 5px 0 0;
  font-size: 1.35rem;
  letter-spacing: -0.03em;
}
.content-dialog-copy {
  margin: 0;
  padding: 14px 20px 0;
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.5;
}
.content-fields {
  min-height: 0;
  overflow: auto;
  padding: 16px 20px 20px;
  display: grid;
  gap: 12px;
}
.content-entry {
  min-width: 0;
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: 12px;
  display: grid;
  gap: 10px;
  background: var(--surface-soft);
}
.content-entry legend {
  max-width: 100%;
  padding: 0 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 760;
}
.content-field {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 0.74rem;
  font-weight: 720;
}
.content-field input,
.content-field textarea {
  width: 100%;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  padding: 9px 10px;
  color: var(--ink);
  background: var(--surface);
  outline: none;
  font: 0.88rem/1.45 Inter, ui-sans-serif, system-ui, sans-serif;
}
.content-field textarea {
  min-height: 86px;
  resize: vertical;
}
.content-field input:focus,
.content-field textarea:focus {
  border-color: rgba(99, 91, 255, 0.72);
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.12);
}
.content-dialog-actions {
  justify-content: flex-end;
  border-top: 1px solid var(--line);
}

.editor-stage {
  flex: 1;
  min-height: 0;
  padding: 12px;
  display: flex;
  background: linear-gradient(rgba(99, 91, 255, 0.018), rgba(99, 91, 255, 0)), #eceef4;
}
.editor-wrap {
  flex: 1;
  min-width: 0;
  min-height: 520px;
  overflow: hidden;
  border: 1px solid #d8dae4;
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--shadow-md);
}
.editor-wrap iframe { width: 100%; height: 100%; min-height: 520px; display: block; border: 0; background: #fff; }

body.editor-focus { overflow: hidden; }
body.editor-focus .app-shell { height: 100vh; height: 100dvh; min-height: 0; }
body.editor-focus .topline { display: none; }
body.editor-focus .workspace { position: relative; height: 100vh; height: 100dvh; min-height: 0; }
body.editor-focus .workspace-bar {
  position: absolute;
  z-index: 20;
  top: max(8px, env(safe-area-inset-top));
  right: max(8px, env(safe-area-inset-right));
  min-height: 0;
  width: auto;
  padding: 0;
  border: 0;
  background: transparent;
  backdrop-filter: none;
  pointer-events: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
body.editor-focus .workspace-bar > :not(.font-controls):not(.workspace-output) { display: none; }
body.editor-focus .workspace-output {
  display: flex;
  width: auto;
  padding: 0;
  border: 0;
  background: transparent;
  flex-wrap: nowrap;
  pointer-events: none;
}
body.editor-focus .workspace-output > :not(.fullscreen-toggle) { display: none; }
body.editor-focus .workspace-bar > .font-controls {
  display: inline-flex;
  padding: 3px;
  border: 1px solid rgba(133, 150, 180, 0.55);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 5px 18px rgba(0, 0, 0, 0.20);
  backdrop-filter: blur(12px);
  pointer-events: auto;
}
body.editor-focus .font-controls .button { min-height: 40px; padding-inline: 8px; }
body.editor-focus .fullscreen-toggle {
  position: relative;
  width: 40px;
  min-height: 40px;
  padding: 0;
  overflow: hidden;
  color: transparent;
  background: rgba(24, 34, 52, 0.88);
  border-color: rgba(133, 150, 180, 0.55);
  box-shadow: 0 5px 18px rgba(0, 0, 0, 0.20);
  backdrop-filter: blur(12px);
  pointer-events: auto;
}
body.editor-focus .fullscreen-toggle::after {
  content: "×";
  display: grid;
  place-items: center;
  position: absolute;
  inset: 0;
  color: #f7f9fc;
  font-size: 1.5rem;
  font-weight: 400;
  line-height: 1;
}
body.editor-focus .editor-stage {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
  padding: max(60px, calc(env(safe-area-inset-top) + 52px)) 0 0;
}
body.editor-focus .editor-wrap { min-height: 0; height: 100%; border: 0; border-radius: 0; box-shadow: none; }
body.editor-focus .editor-wrap iframe { min-height: 0; height: 100%; }

@media (max-width: 1180px) {
  .start-layout { grid-template-columns: minmax(0, 0.78fr) minmax(400px, 1.22fr); gap: 42px; }
  h1 { font-size: clamp(3rem, 7.8vw, 5.8rem); }
  .workspace-bar { grid-template-columns: minmax(0, 1fr) auto; align-items: start; }
  .workspace-leading { grid-column: 1; grid-row: 1; }
  .workspace-output { grid-column: 2; grid-row: 1; }
  .font-controls { grid-column: 1; grid-row: 2; width: fit-content; }
  .workspace-tools { grid-column: 2; grid-row: 2; }
  .workspace-tools,
  .workspace-output { border-left: 0; padding-left: 0; }
}

@media (max-width: 1024px) {
  .workspace-bar > .font-controls { order: -2; }
  .product-badge { display: none; }
}

@media (max-width: 900px) {
  .start-card { align-items: start; padding-top: 38px; padding-bottom: 38px; }
  .start-layout { grid-template-columns: minmax(0, 1fr); gap: 30px; }
  h1 { max-width: 760px; font-size: clamp(3.5rem, 12.5vw, 6.1rem); }
  .lede { max-width: 720px; }
  .format-strip { margin-top: 20px; }
  .restore-button { margin-top: 20px; }
  .import-panel { width: 100%; }
}

@media (max-width: 760px) {
  .topline { min-height: 58px; padding: 8px 12px; }
  .brand-mark { width: 34px; height: 34px; border-radius: 11px; }
  .brand-copy small { display: none; }
  .status { max-width: 42vw; border: 0; padding-inline: 0; background: transparent; font-size: 0.72rem; }
  .start-card { padding: 27px 12px 22px; }
  .start-layout { gap: 20px; }
  h1 { margin-top: 9px; font-size: clamp(2.85rem, 13.2vw, 4rem); line-height: 0.92; }
  .lede { margin-top: 14px; font-size: 0.96rem; }
  .format-strip { margin-top: 14px; gap: 6px; }
  .format-strip span { padding: 6px 8px; font-size: 0.7rem; }
  .import-panel { padding: 17px; border-radius: 21px; }
  .panel-heading { gap: 10px; }
  .shortcut-hint { display: none; }
  .paste-box textarea { min-height: 160px; max-height: 36vh; padding: 14px; border-radius: 14px; }
  .primary-actions { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .primary-actions .button { width: 100%; }
  .primary-actions .button.primary { grid-column: 1 / -1; }
  .font-default-control { align-items: flex-start; flex-direction: column; gap: 8px; }

  .workspace-bar {
    padding: 8px;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 7px 8px;
  }
  .workspace-leading {
    grid-column: 1;
    grid-row: 1;
    padding-bottom: 0;
    border-bottom: 0;
  }
  .document-kicker { display: none; }
  .document-title { max-width: 108px; }
  .font-controls {
    grid-column: 2;
    grid-row: 1;
    width: auto;
    max-width: 100%;
    flex-wrap: nowrap;
  }
  .font-controls .button { min-width: 32px; padding-inline: 7px; }
  .workspace-tools {
    grid-column: 1;
    grid-row: 2;
    align-self: center;
    justify-content: flex-start;
    flex-wrap: nowrap;
  }
  .workspace-output {
    grid-column: 2;
    grid-row: 2;
    justify-content: flex-end;
    padding-top: 0;
    flex-wrap: nowrap;
    gap: 4px;
  }
  .workspace-output .button { padding-inline: 8px; }
  .editor-stage { padding: 6px; }
  .editor-wrap { min-height: calc(100dvh - 190px); border-radius: 11px; }
  .editor-wrap iframe { min-height: calc(100dvh - 190px); }
}

@media (max-width: 420px) {
  .primary-actions { grid-template-columns: minmax(0, 1fr); }
  .primary-actions .button.primary { grid-column: auto; }
  .workspace-output { gap: 3px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}

@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #0f1118;
    --surface: #171922;
    --surface-raised: rgba(24, 26, 36, 0.92);
    --surface-soft: #20232e;
    --ink: #f0f1f7;
    --muted: #a2a6b5;
    --line: #2c2f3b;
    --line-strong: #3a3e4b;
    --accent: #8a83ff;
    --accent-strong: #746cf4;
    --accent-soft: #282549;
    --danger: #ffb4b4;
    --danger-soft: #3f2327;
    --shadow-lg: 0 30px 90px rgba(0, 0, 0, 0.34);
    --shadow-md: 0 12px 38px rgba(0, 0, 0, 0.28);
  }
  body {
    background:
      radial-gradient(circle at 18% 4%, rgba(125, 116, 255, 0.14), transparent 34rem),
      radial-gradient(circle at 86% 18%, rgba(64, 190, 178, 0.07), transparent 30rem),
      var(--bg);
  }
  .topline,
  .workspace-bar { background: rgba(16, 18, 25, 0.82); }
  .product-badge,
  .status,
  .format-strip span { background: rgba(31, 34, 45, 0.72); color: var(--muted); }
  .paste-box textarea { color: var(--ink); background: rgba(18, 20, 28, 0.82); box-shadow: none; }
  .paste-box textarea:focus { background: #161821; }
  .button { color: #e9eaf1; background: #20232e; }
  .button:hover { border-color: #4b4f5e; background: #282b37; }
  .button.ghost { color: var(--muted); background: transparent; }
  .button.ghost:hover { color: var(--ink); background: #20232e; }
  .font-controls { background: #1b1e27; }
  .font-controls .button:hover { background: #292c37; }
  .editor-stage { background: #11131a; }
  .editor-wrap { border-color: #2b2e39; background: #fff; }
  body.editor-focus .workspace-bar > .font-controls { background: rgba(24, 34, 52, 0.94); }
}
"""

CANVAS_IMPORT_JS = r"""const DRAWIO_ROOT = /^(?:<\?xml\s+version\s*=\s*(?:"1\.[01]"|'1\.[01]')(?:\s+encoding\s*=\s*(?:"[A-Za-z][A-Za-z0-9._-]*"|'[A-Za-z][A-Za-z0-9._-]*'))?(?:\s+standalone\s*=\s*(?:"(?:yes|no)"|'(?:yes|no)'))?\s*\?>\s*)?<(?:mxfile|mxGraphModel)(?=[\s/>])/;
const MERMAID_HEADER = /^(?:---[\s\S]*?---\s*)?(?:(?:%%[^\r\n]*)(?:\r?\n|$)\s*)*(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|mindmap|timeline|journey|pie|quadrantChart|requirementDiagram|gitGraph|C4(?:Context|Container|Component)|architecture-beta|radar-beta|packet-beta|venn-beta|treemap-beta|treeView-beta|ishikawa-beta|kanban|zenuml|wardley-beta|eventmodeling)\b/i;

export const READABLE_NODE_FONT_SIZE = 18;
export const READABLE_EDGE_FONT_SIZE = 16;
export const MIN_CONFIGURABLE_FONT_SIZE = 8;
export const MAX_CONFIGURABLE_FONT_SIZE = 72;
export const MIN_READABLE_SCALE = 0.65;
export const READABILITY_ZOOM_FACTOR = 1.2;
export const MAX_READABILITY_ZOOM_STEPS = 8;

export const COLLISION_SAFE_LAYOUT_CONFIG = Object.freeze({
  "elk.direction": "DOWN",
  "elk.spacing.nodeNode": "48",
  "elk.spacing.edgeNode": "28",
  "elk.spacing.edgeEdge": "18",
  "elk.spacing.edgeLabel": "10",
  "elk.layered.spacing.nodeNodeBetweenLayers": "84",
  "elk.layered.spacing.edgeNodeBetweenLayers": "32",
  "elk.layered.spacing.edgeEdgeBetweenLayers": "24",
  "elk.layered.edgeLabels.centerLabelPlacementStrategy": "SPACE_EFFICIENT_LAYER",
});

export function readabilityZoomStepCount(scale) {
  const current = Number(scale);
  if (!Number.isFinite(current) || current <= 0 || current >= MIN_READABLE_SCALE) return 0;
  return Math.min(
    MAX_READABILITY_ZOOM_STEPS,
    Math.ceil(Math.log(MIN_READABLE_SCALE / current) / Math.log(READABILITY_ZOOM_FACTOR)),
  );
}

const FULL_INPUT_FENCE = /^```(mermaid|mmd|json|jsoncanvas|json-canvas|\.?canvas|xml|drawio)?[^\S\r\n]*\r?\n([\s\S]*?)\r?\n```$/i;
const INLINE_INPUT_FENCE = /```(mermaid|mmd|json|jsoncanvas|json-canvas|\.?canvas|xml|drawio)[^\S\r\n]*\r?\n([\s\S]*?)\r?\n```/gi;

function explicitCanvasFence(label) {
  return /^(?:jsoncanvas|json-canvas|\.?canvas)$/i.test(String(label || ""));
}

function jsonCanvasNumbersRemainSafe(value) {
  const pending = [value];
  const seen = new WeakSet();
  while (pending.length > 0) {
    const item = pending.pop();
    if (typeof item === "number") {
      if (!Number.isFinite(item)) return false;
      if (Number.isInteger(item) && !Number.isSafeInteger(item)) return false;
      continue;
    }
    if (!item || typeof item !== "object") continue;
    if (seen.has(item)) continue;
    seen.add(item);
    if (Array.isArray(item)) {
      for (const child of item) pending.push(child);
      continue;
    }
    for (const child of Object.values(item)) pending.push(child);
  }
  return true;
}

function canonicalJsonNumberToken(token) {
  const match = String(token).match(
    /^(-?)(0|[1-9]\d*)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/,
  );
  if (!match) return null;
  const fraction = match[3] || "";
  const rawExponent = match[4] || "0";
  const exponentSign = rawExponent.startsWith("-") ? -1 : 1;
  const exponentDigits = rawExponent.replace(/^[+-]?0*/, "") || "0";
  if (exponentDigits.length > 6) return null;
  let exponent = exponentSign * Number(exponentDigits) - fraction.length;
  let digits = `${match[2]}${fraction}`.replace(/^0+/, "");
  const sign = match[1] === "-" ? "-" : "+";
  if (!digits) return `${sign}0`;
  const trimmedDigits = digits.replace(/0+$/, "");
  exponent += digits.length - trimmedDigits.length;
  digits = trimmedDigits;
  return `${sign}${digits}e${exponent}`;
}

function jsonCanvasNumberTokensRoundtripSafely(text) {
  let inString = false;
  let escaped = false;
  let index = 0;
  while (index < text.length) {
    const character = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      index += 1;
      continue;
    }
    if (character === '"') {
      inString = true;
      index += 1;
      continue;
    }
    if (character === "-" || (character >= "0" && character <= "9")) {
      const match = text.slice(index).match(
        /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/,
      );
      if (!match) {
        index += 1;
        continue;
      }
      const token = match[0];
      const parsed = Number(token);
      if (!Number.isFinite(parsed)) return false;
      const serialized = JSON.stringify(parsed);
      if (
        canonicalJsonNumberToken(token) === null ||
        canonicalJsonNumberToken(serialized) !== canonicalJsonNumberToken(token)
      ) {
        return false;
      }
      index += token.length;
      continue;
    }
    index += 1;
  }
  return true;
}

function jsonObjectMembersAreUnique(text) {
  let index = 0;

  const skipWhitespace = () => {
    while (index < text.length && /[\t\n\r ]/.test(text[index])) index += 1;
  };

  const parseString = () => {
    if (text[index] !== '"') return null;
    const start = index;
    index += 1;
    while (index < text.length) {
      const character = text[index];
      if (character === "\\") {
        index += 2;
        continue;
      }
      if (character === '"') {
        index += 1;
        try {
          const value = JSON.parse(text.slice(start, index));
          return typeof value === "string" ? value : null;
        } catch (_) {
          return null;
        }
      }
      if (character.charCodeAt(0) < 0x20) return null;
      index += 1;
    }
    return null;
  };

  const parseNumber = () => {
    const match = text.slice(index).match(
      /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/,
    );
    if (!match) return false;
    index += match[0].length;
    return true;
  };

  const parseLiteral = (literal) => {
    if (!text.startsWith(literal, index)) return false;
    index += literal.length;
    return true;
  };

  const parseValue = () => {
    skipWhitespace();
    const character = text[index];
    if (character === "{") return parseObject();
    if (character === "[") return parseArray();
    if (character === '"') return parseString() !== null;
    if (character === "t") return parseLiteral("true");
    if (character === "f") return parseLiteral("false");
    if (character === "n") return parseLiteral("null");
    return parseNumber();
  };

  const parseObject = () => {
    if (text[index] !== "{") return false;
    index += 1;
    skipWhitespace();
    const names = new Set();
    if (text[index] === "}") {
      index += 1;
      return true;
    }
    while (index < text.length) {
      skipWhitespace();
      const name = parseString();
      if (name === null || names.has(name)) return false;
      names.add(name);
      skipWhitespace();
      if (text[index] !== ":") return false;
      index += 1;
      if (!parseValue()) return false;
      skipWhitespace();
      if (text[index] === "}") {
        index += 1;
        return true;
      }
      if (text[index] !== ",") return false;
      index += 1;
    }
    return false;
  };

  const parseArray = () => {
    if (text[index] !== "[") return false;
    index += 1;
    skipWhitespace();
    if (text[index] === "]") {
      index += 1;
      return true;
    }
    while (index < text.length) {
      if (!parseValue()) return false;
      skipWhitespace();
      if (text[index] === "]") {
        index += 1;
        return true;
      }
      if (text[index] !== ",") return false;
      index += 1;
    }
    return false;
  };

  skipWhitespace();
  const valid = parseValue();
  skipWhitespace();
  return valid && index === text.length;
}

function detectNormalizedInput(text, options = {}) {
  if (!text) return { kind: "empty", text };
  if (DRAWIO_ROOT.test(text)) return { kind: "drawio", text };
  if (MERMAID_HEADER.test(text)) return { kind: "mermaid", text };
  if (text.startsWith("{")) {
    try {
      const uniqueMembers = jsonObjectMembersAreUnique(text);
      const value = JSON.parse(text);
      if (isSchauwerkRepresentation(value)) {
        return uniqueMembers ? { kind: "representation", text, value } : { kind: "unknown", text };
      }
      if (
        hasSupportedJsonCanvasShape(value, {
          allowExtensionOnly: Boolean(options.allowExtensionOnlyCanvas),
        })
      ) {
        if (!uniqueMembers) {
          return {
            kind: "json-canvas-rejected",
            text,
            reason: "JSON Canvas kann nicht verlustfrei geöffnet werden: doppelte Objektschlüssel sind nicht zulässig.",
          };
        }
        if (!jsonCanvasNumbersRemainSafe(value)) {
          return {
            kind: "json-canvas-rejected",
            text,
            reason: "JSON Canvas kann nicht verlustfrei geöffnet werden: Zahlen müssen im sicheren JavaScript-Zahlenbereich liegen.",
          };
        }
        if (!jsonCanvasNumberTokensRoundtripSafely(text)) {
          return {
            kind: "json-canvas-rejected",
            text,
            reason: "JSON Canvas kann nicht verlustfrei geöffnet werden: ein Zahlenliteral würde sich beim JavaScript-Roundtrip verändern.",
          };
        }
        return { kind: "json-canvas", text, value };
      }
    } catch (_) {
      return { kind: "unknown", text };
    }
  }
  return { kind: "unknown", text };
}

function normalizeInputContext(raw) {
  const text = String(raw ?? "").replace(/^\uFEFF/, "").trim();
  const fenced = text.match(FULL_INPUT_FENCE);
  if (fenced) {
    return {
      text: fenced[2].trim(),
      allowExtensionOnlyCanvas: explicitCanvasFence(fenced[1]),
    };
  }

  const recognizedFences = [...text.matchAll(INLINE_INPUT_FENCE)]
    .map((match) => {
      const candidate = match[2].trim();
      const allowExtensionOnlyCanvas = explicitCanvasFence(match[1]);
      const detected = detectNormalizedInput(candidate, { allowExtensionOnlyCanvas });
      return detected.kind === "unknown"
        ? null
        : { text: candidate, allowExtensionOnlyCanvas };
    })
    .filter(Boolean);
  if (recognizedFences.length === 1) return recognizedFences[0];
  return { text, allowExtensionOnlyCanvas: false };
}

export function normalizeInput(raw) {
  return normalizeInputContext(raw).text;
}

export function detectInput(raw, options = {}) {
  const normalized = normalizeInputContext(raw);
  return detectNormalizedInput(normalized.text, {
    allowExtensionOnlyCanvas: Boolean(
      options.allowExtensionOnlyCanvas || normalized.allowExtensionOnlyCanvas
    ),
  });
}

export function isSchauwerkRepresentation(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    value.schema_version === "schauwerk-representation-input.v1" &&
    typeof value.title === "string" &&
    typeof value.intent === "string" &&
    Array.isArray(value.nodes) &&
    Array.isArray(value.edges) &&
    Array.isArray(value.groups)
  );
}

function isCanvasNode(node) {
  if (
    !node ||
    typeof node !== "object" ||
    Array.isArray(node) ||
    typeof node.id !== "string" ||
    !node.id ||
    !["text", "file", "link", "group"].includes(node.type) ||
    !Number.isInteger(node.x) ||
    !Number.isInteger(node.y) ||
    !Number.isInteger(node.width) ||
    !Number.isInteger(node.height)
  ) return false;
  if (node.type === "text") return typeof node.text === "string";
  if (node.type === "file") return typeof node.file === "string" && Boolean(node.file);
  if (node.type === "link") return typeof node.url === "string" && Boolean(node.url);
  return true;
}

function isCanvasEdge(edge) {
  return Boolean(
    edge &&
    typeof edge === "object" &&
    !Array.isArray(edge) &&
    typeof edge.id === "string" &&
    edge.id &&
    typeof edge.fromNode === "string" &&
    edge.fromNode &&
    typeof edge.toNode === "string" &&
    edge.toNode
  );
}

function hasSupportedJsonCanvasShape(value, options = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const hasNodes = Object.prototype.hasOwnProperty.call(value, "nodes");
  const hasEdges = Object.prototype.hasOwnProperty.call(value, "edges");
  if (!hasNodes && !hasEdges) return Object.keys(value).length === 0 || Boolean(options.allowExtensionOnly);
  if (hasNodes && (!Array.isArray(value.nodes) || !value.nodes.every(isCanvasNode))) return false;
  if (hasEdges && (!Array.isArray(value.edges) || !value.edges.every(isCanvasEdge))) return false;
  return true;
}

export function isJsonCanvas(value, options = {}) {
  return hasSupportedJsonCanvasShape(value, options) && jsonCanvasNumbersRemainSafe(value);
}

export const MAX_INPUT_BYTES = 5 * 1024 * 1024;
const MAX_EXPORT_DATA_URI_CHARS = 32 * 1024 * 1024;
const MAX_PROJECT_XML_CHARS = 10 * 1024 * 1024;
const EXPORT_PREFIXES = {
  png: "data:image/png;base64,",
  svg: "data:image/svg+xml;base64,",
};

export function validateInputText(value) {
  const text = String(value ?? "");
  if (new TextEncoder().encode(text).byteLength > MAX_INPUT_BYTES) {
    throw new Error("Die Eingabe ist zu groß (maximal 5 MB).");
  }
  return text;
}

export function validateExportDataUri(value, format) {
  if (typeof value !== "string" || value.length > MAX_EXPORT_DATA_URI_CHARS) {
    throw new Error("Exportdaten sind ungültig oder zu groß.");
  }
  const prefix = EXPORT_PREFIXES[format];
  if (!prefix || !value.startsWith(prefix)) {
    throw new Error("Exportformat stimmt nicht mit der angeforderten Datei überein.");
  }
  const payload = value.slice(prefix.length);
  if (!payload || !/^[A-Za-z0-9+/]+={0,2}$/.test(payload) || payload.length % 4 !== 0) {
    throw new Error("Exportdaten sind nicht gültig base64-kodiert.");
  }
  return value;
}

export function exportDataUriToBlob(value, format) {
  const validated = validateExportDataUri(value, format);
  const prefix = EXPORT_PREFIXES[format];
  const mimeType = format === "png" ? "image/png" : format === "svg" ? "image/svg+xml" : null;
  if (!prefix || !mimeType) throw new Error("Exportformat kann nicht als Datei vorbereitet werden.");

  const binary = atob(validated.slice(prefix.length));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
}

export function validateDiagramXml(value) {
  if (typeof value !== "string" || !value || value.length > MAX_PROJECT_XML_CHARS) {
    throw new Error("Projekt-XML ist ungültig oder zu groß.");
  }
  const normalized = value.trimStart();
  if (!DRAWIO_ROOT.test(normalized)) {
    throw new Error("Projekt-XML besitzt keinen unterstützten draw.io-Wurzelknoten.");
  }
  if (/<!DOCTYPE\b/i.test(normalized)) {
    throw new Error("Projekt-XML darf keine Dokumenttyp-Deklaration enthalten.");
  }
  if (typeof DOMParser !== "function") {
    throw new Error("Projekt-XML kann in dieser Umgebung nicht sicher geprüft werden.");
  }
  const document = new DOMParser().parseFromString(normalized, "application/xml");
  if (document.getElementsByTagName("parsererror").length > 0 || document.doctype) {
    throw new Error("Projekt-XML ist nicht wohlgeformt.");
  }
  const root = document.documentElement;
  if (!root || !["mxfile", "mxGraphModel"].includes(root.localName) || root.namespaceURI) {
    throw new Error("Projekt-XML besitzt keinen unterstützten draw.io-Wurzelknoten.");
  }
  return value;
}

function xmlSafeText(value) {
  let output = "";
  for (const character of String(value ?? "")) {
    const codePoint = character.codePointAt(0);
    const allowed =
      codePoint === 0x9 ||
      codePoint === 0xa ||
      codePoint === 0xd ||
      (codePoint >= 0x20 && codePoint <= 0xd7ff) ||
      (codePoint >= 0xe000 && codePoint <= 0xfffd) ||
      (codePoint >= 0x10000 && codePoint <= 0x10ffff);
    output += allowed ? character : "\uFFFD";
  }
  return output;
}

function xmlAttr(value) {
  return xmlSafeText(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\t", "&#x9;")
    .replaceAll("\r", "&#xd;")
    .replaceAll("\n", "&#xa;");
}

function utf16CodeUnitHex(value) {
  const text = String(value);
  let encoded = "";
  for (let index = 0; index < text.length; index += 1) {
    encoded += text.charCodeAt(index).toString(16).padStart(4, "0");
  }
  return encoded;
}

function nodeId(value) { return `jc_${utf16CodeUnitHex(value)}`; }
function edgeId(value) { return `jce_${utf16CodeUnitHex(value)}`; }

function numberOr(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function stripMarkdown(value) {
  return String(value ?? "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function palette(color) {
  const presets = {
    "1": ["#f8cecc", "#b85450"],
    "2": ["#ffe6cc", "#d79b00"],
    "3": ["#fff2cc", "#d6b656"],
    "4": ["#d5e8d4", "#82b366"],
    "5": ["#d0e8f2", "#4b8f9f"],
    "6": ["#e1d5e7", "#9673a6"],
  };
  if (typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color)) return [color, color];
  return presets[String(color)] ?? ["#ffffff", "#7f8aa3"];
}

function nodeLabel(node) {
  if (node.type === "group") return String(node.label ?? "Gruppe");
  if (node.type === "link") return String(node.label ?? node.url ?? "Link");
  if (node.type === "file") return String(node.label ?? node.file ?? "Datei");
  return stripMarkdown(node.text ?? node.label ?? "Text");
}

function configuredFontSize(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= MIN_CONFIGURABLE_FONT_SIZE && parsed <= MAX_CONFIGURABLE_FONT_SIZE
    ? parsed
    : fallback;
}

function nodeStyle(node, fontSize) {
  if (node.type === "group") {
    return `swimlane;html=0;rounded=1;startSize=28;fillColor=#f5f5f5;strokeColor=#b8c1d1;fontSize=${fontSize};fontStyle=1;align=left;container=0;collapsible=0;`;
  }
  const [fill, stroke] = palette(node.color);
  const common = `whiteSpace=wrap;html=0;fillColor=${fill};strokeColor=${stroke};fontColor=#172033;fontSize=${fontSize};align=left;spacing=12;`;
  if (node.type === "file") return `shape=note;${common}`;
  if (node.type === "link") return `rounded=1;arcSize=12;${common}fontColor=#2455b5;`;
  return `rounded=1;arcSize=12;verticalAlign=top;${common}`;
}

function sidePoint(side, prefix) {
  const points = {
    left: [0, 0.5],
    right: [1, 0.5],
    top: [0.5, 0],
    bottom: [0.5, 1],
  };
  const point = points[String(side)] ?? null;
  if (!point) return "";
  return `${prefix}X=${point[0]};${prefix}Y=${point[1]};${prefix}Dx=0;${prefix}Dy=0;`;
}

function edgeStyle(edge, fontSize) {
  const endArrow = edge.toEnd === "none" ? "none" : "classic";
  const startArrow = edge.fromEnd === "arrow" ? "classic" : "none";
  return [
    `edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=0;fontSize=${fontSize};sourcePerimeterSpacing=12;targetPerimeterSpacing=12;spacing=6;labelBackgroundColor=#ffffff;`,
    `endArrow=${endArrow};endFill=1;startArrow=${startArrow};startFill=1;`,
    sidePoint(edge.fromSide, "exit"),
    sidePoint(edge.toSide, "entry"),
  ].join("");
}

function validateJsonCanvas(value) {
  if (!isJsonCanvas(value)) throw new Error("Keine gültige JSON-Canvas-Struktur.");
  const nodes = value.nodes ?? [];
  const edges = value.edges ?? [];
  const ids = new Set();
  for (const [index, node] of nodes.entries()) {
    if (!node || typeof node !== "object") throw new Error(`Knoten ${index + 1} ist ungültig.`);
    if (typeof node.id !== "string" || !node.id) throw new Error(`Knoten ${index + 1} hat keine ID.`);
    if (ids.has(node.id)) throw new Error(`Doppelte Knoten-ID: ${node.id}`);
    ids.add(node.id);
  }
  const edgeIds = new Set();
  for (const [index, edge] of edges.entries()) {
    if (!edge || typeof edge !== "object") throw new Error(`Kante ${index + 1} ist ungültig.`);
    if (!ids.has(edge.fromNode) || !ids.has(edge.toNode)) {
      throw new Error(`Kante ${index + 1} verweist auf einen unbekannten Knoten.`);
    }
    const rawId = typeof edge.id === "string" && edge.id ? edge.id : `edge_${index + 1}`;
    if (edgeIds.has(rawId)) throw new Error(`Doppelte Kanten-ID: ${rawId}`);
    edgeIds.add(rawId);
  }
  return { nodes, edges };
}

export function emptyDrawioXml() {
  return '<mxGraphModel grid="0" page="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>';
}

export function jsonCanvasToDrawioXml(source, options = {}) {
  const value = typeof source === "string" ? JSON.parse(normalizeInput(source)) : source;
  const { nodes, edges } = validateJsonCanvas(value);
  const nodeFontSize = configuredFontSize(options.nodeFontSize, READABLE_NODE_FONT_SIZE);
  const edgeFontSize = configuredFontSize(options.edgeFontSize, READABLE_EDGE_FONT_SIZE);

  const geometryNodes = nodes.filter((node) => node && typeof node === "object");
  const minX = geometryNodes.reduce((minimum, node) => Math.min(minimum, numberOr(node.x, 0)), 0);
  const minY = geometryNodes.reduce((minimum, node) => Math.min(minimum, numberOr(node.y, 0)), 0);
  const offsetX = 40 - minX;
  const offsetY = 40 - minY;
  const groups = geometryNodes.filter((node) => node.type === "group");
  const regular = geometryNodes.filter((node) => node.type !== "group");
  const cells = [];

  for (const node of [...groups, ...regular]) {
    const sourceX = numberOr(node.x, 0);
    const sourceY = numberOr(node.y, 0);
    const sourceWidth = numberOr(node.width, node.type === "group" ? 440 : 320);
    const sourceHeight = numberOr(node.height, node.type === "group" ? 300 : 140);
    const sourceRight = sourceX + sourceWidth;
    const sourceBottom = sourceY + sourceHeight;
    if (![sourceX, sourceY, sourceWidth, sourceHeight, sourceRight, sourceBottom].every(Number.isFinite)) {
      throw new Error(`Knoten ${node.id} erzeugt ungültige Geometrie.`);
    }
    const x = sourceX + offsetX;
    const y = sourceY + offsetY;
    const width = Math.max(40, sourceWidth);
    const height = Math.max(30, sourceHeight);
    const right = x + width;
    const bottom = y + height;
    if (![x, y, width, height, right, bottom].every(Number.isFinite)) {
      throw new Error(`Knoten ${node.id} erzeugt ungültige Geometrie.`);
    }
    const id = nodeId(node.id);
    const metadata = [
      `id="${xmlAttr(id)}"`,
      `label="${xmlAttr(nodeLabel(node))}"`,
      `jsonCanvasId="${xmlAttr(node.id)}"`,
      `jsonCanvasType="${xmlAttr(node.type ?? "text")}"`,
    ];
    if (node.type === "link" && typeof node.url === "string") metadata.push(`link="${xmlAttr(node.url)}"`);
    if (node.type === "file" && typeof node.file === "string") metadata.push(`jsonCanvasFile="${xmlAttr(node.file)}"`);
    cells.push(
      `<object ${metadata.join(" ")}><mxCell style="${xmlAttr(nodeStyle(node, nodeFontSize))}" vertex="1" parent="1">` +
      `<mxGeometry x="${x}" y="${y}" width="${width}" height="${height}" as="geometry"/>` +
      `</mxCell></object>`
    );
  }

  for (const [index, edge] of edges.entries()) {
    const source = nodeId(edge.fromNode);
    const target = nodeId(edge.toNode);
    const rawId = typeof edge.id === "string" && edge.id ? edge.id : `edge_${index + 1}`;
    cells.push(
      `<mxCell id="${xmlAttr(edgeId(rawId))}" value="${xmlAttr(edge.label ?? "")}" ` +
      `style="${xmlAttr(edgeStyle(edge, edgeFontSize))}" edge="1" parent="1" source="${xmlAttr(source)}" target="${xmlAttr(target)}">` +
      '<mxGeometry relative="1" as="geometry"/></mxCell>'
    );
  }

  const xml = `<mxGraphModel grid="0" page="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells.join("")}</root></mxGraphModel>`;
  if (xml.length > MAX_PROJECT_XML_CHARS) throw new Error("Konvertiertes Projekt-XML ist zu groß.");
  return xml;
}
"""

APP_JS = r"""import { COLLISION_SAFE_LAYOUT_CONFIG, MAX_CONFIGURABLE_FONT_SIZE, MAX_INPUT_BYTES, MIN_CONFIGURABLE_FONT_SIZE, READABILITY_ZOOM_FACTOR, READABLE_EDGE_FONT_SIZE, READABLE_NODE_FONT_SIZE, detectInput, emptyDrawioXml, exportDataUriToBlob, jsonCanvasToDrawioXml, readabilityZoomStepCount, validateDiagramXml, validateExportDataUri, validateInputText } from "./canvas-import.js";

const EDITOR_ORIGIN = "__SCHAUWERK_EDITOR_ORIGIN__";
const EDITOR_URL = "__SCHAUWERK_EDITOR_URL__";
const PUBLIC_BASE_PATH = "__SCHAUWERK_PUBLIC_BASE_PATH__";
const NATIVE_API_PATH = `${PUBLIC_BASE_PATH}/api/native-viewer`;
const NATIVE_IMPORT_SCHEMA = "schauwerk-native-import-request.v1";
const DRAFT_KEY = "schauwerk.standalone-editor.draft.v1";
const NATIVE_DRAFT_KEY = "schauwerk.native-schaubild.draft.v1";
const FONT_PREFERENCE_KEY = "schauwerk.standalone-editor.font-size.v1";
const PRODUCT_DEFAULT_NODE_FONT_SIZE = 24;
const PRODUCT_DEFAULT_EDGE_FONT_SIZE = 22;

const elements = {
  startView: document.querySelector("#startView"),
  workspace: document.querySelector("#workspace"),
  sourceInput: document.querySelector("#sourceInput"),
  openPasteButton: document.querySelector("#openPasteButton"),
  fileButton: document.querySelector("#fileButton"),
  fileInput: document.querySelector("#fileInput"),
  blankButton: document.querySelector("#blankButton"),
  legacyFallbackButton: document.querySelector("#legacyFallbackButton"),
  restoreButton: document.querySelector("#restoreButton"),
  error: document.querySelector("#error"),
  frame: document.querySelector("#editorFrame"),
  status: document.querySelector("#status"),
  title: document.querySelector("#documentTitle"),
  homeLink: document.querySelector("#homeLink"),
  backButton: document.querySelector("#backButton"),
  layoutButton: document.querySelector("#layoutButton"),
  contentEditButton: document.querySelector("#contentEditButton"),
  contentDialog: document.querySelector("#contentDialog"),
  contentFields: document.querySelector("#contentFields"),
  contentSaveButton: document.querySelector("#contentSaveButton"),
  legacyEditButton: document.querySelector("#legacyEditButton"),
  nativeRetryButton: document.querySelector("#nativeRetryButton"),
  projectButton: document.querySelector("#projectButton"),
  downloadLink: document.querySelector("#downloadLink"),
  fullscreenButton: document.querySelector("#fullscreenButton"),
  fontDefaultInput: document.querySelector("#fontDefaultInput"),
  fontDecreaseButton: document.querySelector("#fontDecreaseButton"),
  fontPanelButton: document.querySelector("#fontPanelButton"),
  fontIncreaseButton: document.querySelector("#fontIncreaseButton"),
  fontAllButton: document.querySelector("#fontAllButton"),
};

let pendingLoad = null;
let currentXml = null;
let currentRepresentation = null;
let currentNativeDocument = null;
let currentNativeCanvas = null;
let currentLegacyXml = null;
let pendingLegacyFallback = null;
let currentNativeUrl = null;
let activeEngine = "legacy";
let currentTitle = "Schaubild";
let pendingExport = null;
let preparedDownloadUrl = null;
let editorReady = false;
let editorFocusActive = false;
let loadIntentGeneration = 0;
let nativeLaunchTail = Promise.resolve();
let nativeSupersedeToken = "";
let nativeCanvasRenderStale = false;
let renderedNativeCanvasSnapshot = null;
let pendingInitialCollisionSafeLayout = false;
let pendingCreationDefaults = false;
let preferredNodeFontSize = PRODUCT_DEFAULT_NODE_FONT_SIZE;

function invalidateLoadIntents() {
  loadIntentGeneration += 1;
  return loadIntentGeneration;
}

function setStatus(message) { elements.status.textContent = message; }
function setError(message) {
  elements.error.textContent = message || "";
  elements.error.hidden = !message;
}

function setEngineMode(mode) {
  activeEngine = mode === "native" ? "native" : "legacy";
  const native = activeEngine === "native";
  elements.legacyEditButton.hidden = !(native && Boolean(currentLegacyXml));
  elements.contentEditButton.hidden = !(native && Boolean(currentRepresentation));
  if (
    (!native || !currentRepresentation)
    && elements.contentDialog?.open
  ) {
    elements.contentDialog.close();
  }

  const fontControls = elements.fontDecreaseButton.closest(".font-controls");
  if (fontControls instanceof HTMLElement) fontControls.hidden = native;
  for (const control of [
    elements.fontDecreaseButton,
    elements.fontPanelButton,
    elements.fontIncreaseButton,
    elements.fontAllButton,
    elements.layoutButton,
  ]) {
    control.disabled = native;
  }
  elements.layoutButton.hidden = native;

  const pngButton = document.querySelector('[data-export="png"]');
  if (pngButton instanceof HTMLButtonElement) {
    pngButton.disabled = native;
    pngButton.hidden = native;
  }

  if (native) {
    if (currentNativeCanvas) {
      elements.projectButton.textContent = "Canvas";
      elements.projectButton.title = "Aktuelle .canvas-Datei speichern";
    } else if (currentLegacyXml) {
      elements.projectButton.textContent = "Original";
      elements.projectButton.title = "Unverändertes draw.io-Original speichern";
    } else {
      elements.projectButton.textContent = "Quelle";
      elements.projectButton.title = "Kanonische Quelle speichern";
    }
  } else {
    elements.projectButton.textContent = "Projekt";
    elements.projectButton.title = "Bearbeitbares draw.io-Projekt speichern";
  }
}

function safeFilename(value) {
  const cleaned = String(value || "Schaubild")
    .trim()
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .slice(0, 80);
  return cleaned || "Schaubild";
}

function postToEditor(payload) {
  if (!elements.frame.contentWindow) return;
  elements.frame.contentWindow.postMessage(JSON.stringify(payload), EDITOR_ORIGIN);
}

function parseMessage(data) {
  if (data && typeof data === "object") return data;
  if (typeof data !== "string") return null;
  try { return JSON.parse(data); } catch (_) { return null; }
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function contentEntry(title) {
  const fieldset = document.createElement("fieldset");
  fieldset.className = "content-entry";
  const legend = document.createElement("legend");
  legend.textContent = title;
  fieldset.append(legend);
  elements.contentFields.append(fieldset);
  return fieldset;
}

function appendContentField(
  container,
  { label, value, kind, index = null, multiline = false, maximum = null },
) {
  const wrapper = document.createElement("label");
  wrapper.className = "content-field";
  const caption = document.createElement("span");
  caption.textContent = label;
  const control = document.createElement(multiline ? "textarea" : "input");
  if (!multiline) control.type = "text";
  control.value = String(value ?? "");
  control.dataset.contentKind = kind;
  if (index !== null) control.dataset.contentIndex = String(index);
  if (Number.isInteger(maximum) && maximum > 0) control.maxLength = maximum;
  wrapper.append(caption, control);
  container.append(wrapper);
  return control;
}

function renderRepresentationContentEditor(representation) {
  elements.contentFields.replaceChildren();
  const overview = contentEntry("Schaubild");
  const first = appendContentField(overview, {
    label: "Titel",
    value: representation.title,
    kind: "title",
    maximum: 160,
  });
  appendContentField(overview, {
    label: "Zweck",
    value: representation.purpose,
    kind: "purpose",
    multiline: true,
    maximum: 500,
  });

  const groups = Array.isArray(representation.groups) ? representation.groups : [];
  groups.forEach((group, index) => {
    const entry = contentEntry("Gruppe · " + String(group.id ?? index + 1));
    appendContentField(entry, {
      label: "Bezeichnung",
      value: group.label,
      kind: "group-label",
      index,
      maximum: 100,
    });
  });

  const nodes = Array.isArray(representation.nodes) ? representation.nodes : [];
  nodes.forEach((node, index) => {
    const entry = contentEntry("Element · " + String(node.id ?? index + 1));
    appendContentField(entry, {
      label: "Titel",
      value: node.label,
      kind: "node-label",
      index,
      maximum: 120,
    });
    appendContentField(entry, {
      label: "Beschreibung",
      value: node.summary,
      kind: "node-summary",
      index,
      multiline: true,
      maximum: 500,
    });
  });

  const edges = Array.isArray(representation.edges) ? representation.edges : [];
  edges.forEach((edge, index) => {
    const entry = contentEntry("Verbindung · " + String(edge.id ?? index + 1));
    appendContentField(entry, {
      label: "Beschriftung",
      value: edge.label,
      kind: "edge-label",
      index,
      maximum: 120,
    });
  });
  return first;
}

function representationFromContentEditor() {
  if (!currentRepresentation || typeof currentRepresentation !== "object") return null;
  const edited = cloneJson(currentRepresentation);
  delete edited.input_digest;
  for (const control of elements.contentFields.querySelectorAll("[data-content-kind]")) {
    if (!control || typeof control.value !== "string") continue;
    const kind = control.dataset.contentKind;
    const index = Number.parseInt(control.dataset.contentIndex || "", 10);
    if (kind === "title") edited.title = control.value;
    else if (kind === "purpose") edited.purpose = control.value;
    else if (kind === "group-label" && Array.isArray(edited.groups) && edited.groups[index]) {
      edited.groups[index].label = control.value;
    } else if (kind === "node-label" && Array.isArray(edited.nodes) && edited.nodes[index]) {
      edited.nodes[index].label = control.value;
    } else if (kind === "node-summary" && Array.isArray(edited.nodes) && edited.nodes[index]) {
      edited.nodes[index].summary = control.value;
    } else if (kind === "edge-label" && Array.isArray(edited.edges) && edited.edges[index]) {
      edited.edges[index].label = control.value;
    }
  }
  return edited;
}

function openRepresentationContentEditor() {
  if (
    activeEngine !== "native"
    || !currentRepresentation
    || typeof elements.contentDialog?.showModal !== "function"
  ) {
    setStatus("Für dieses Schaubild ist keine kanonische Inhaltsquelle verfügbar");
    return;
  }
  setError("");
  const first = renderRepresentationContentEditor(currentRepresentation);
  elements.contentDialog.showModal();
  first?.focus({ preventScroll: true });
}

async function saveRepresentationContentEditor() {
  if (!elements.contentSaveButton) return;
  const edited = representationFromContentEditor();
  if (!edited) return;
  elements.contentSaveButton.disabled = true;
  setError("");
  try {
    await launchNative(
      {
        nativeRepresentation: edited,
        sourceMetadata: {
          key: "schauwerkImportFormat",
          value: "schauwerk-representation-input.v1",
        },
      },
      { preserveActiveFrame: true, syncRepresentationTitle: true },
    );
    if (
      currentRepresentation === edited
      && editorReady
      && !nativeCanvasRenderStale
      && typeof elements.contentDialog?.close === "function"
    ) {
      elements.contentDialog.close();
    }
  } finally {
    elements.contentSaveButton.disabled = false;
  }
}

function parseFontSize(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= MIN_CONFIGURABLE_FONT_SIZE && parsed <= MAX_CONFIGURABLE_FONT_SIZE
    ? parsed
    : null;
}

function edgeFontSizeFor(nodeFontSize) {
  return Math.max(MIN_CONFIGURABLE_FONT_SIZE, nodeFontSize - (PRODUCT_DEFAULT_NODE_FONT_SIZE - PRODUCT_DEFAULT_EDGE_FONT_SIZE));
}

function readFontPreference() {
  try {
    return parseFontSize(localStorage.getItem(FONT_PREFERENCE_KEY)) ?? PRODUCT_DEFAULT_NODE_FONT_SIZE;
  } catch (_) {
    return PRODUCT_DEFAULT_NODE_FONT_SIZE;
  }
}

function storeFontPreference(value) {
  try {
    localStorage.setItem(FONT_PREFERENCE_KEY, String(value));
    return true;
  } catch (_) {
    return false;
  }
}

function applyFontPreferenceInput() {
  const parsed = parseFontSize(elements.fontDefaultInput.value);
  if (parsed === null) {
    elements.fontDefaultInput.value = String(preferredNodeFontSize);
    setStatus(`Schriftstandard: ${MIN_CONFIGURABLE_FONT_SIZE}–${MAX_CONFIGURABLE_FONT_SIZE} px`);
    return;
  }
  preferredNodeFontSize = parsed;
  const stored = storeFontPreference(parsed);
  setStatus(stored ? `Schriftstandard ${parsed} px gespeichert` : `Schriftstandard ${parsed} px · Speichern nicht möglich`);
}

function saveDraft(xml) {
  if (typeof xml !== "string" || !xml) return false;
  currentXml = xml;
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ title: currentTitle, xml, savedAt: Date.now() }));
    elements.restoreButton.hidden = false;
    return true;
  } catch (_) {
    setStatus("Bearbeitet · lokaler Speicher voll");
    return false;
  }
}

function readDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    return value && typeof value.xml === "string" ? value : null;
  } catch (_) {
    return null;
  }
}

function saveNativeDraft(representation) {
  if (!representation || typeof representation !== "object") return false;
  currentRepresentation = representation;
  try {
    localStorage.setItem(
      NATIVE_DRAFT_KEY,
      JSON.stringify({ title: currentTitle, representation, savedAt: Date.now() }),
    );
    elements.restoreButton.hidden = false;
    return true;
  } catch (_) {
    setStatus("Quelle geöffnet · lokaler Speicher voll");
    return false;
  }
}

function saveNativeCanvasDraft(nativeDocument, nativeCanvas) {
  if (
    !nativeDocument
    || nativeDocument.schema_version !== "schauwerk-native-editing-document.v1"
    || !nativeCanvas
    || typeof nativeCanvas !== "object"
    || Array.isArray(nativeCanvas)
  ) {
    return false;
  }
  try {
    localStorage.setItem(
      NATIVE_DRAFT_KEY,
      JSON.stringify({
        title: currentTitle,
        nativeDocument,
        nativeCanvas,
        savedAt: Date.now(),
      }),
    );
    elements.restoreButton.hidden = false;
    return true;
  } catch (_) {
    return false;
  }
}

function readNativeDraft() {
  try {
    const raw = localStorage.getItem(NATIVE_DRAFT_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    if (value.representation && typeof value.representation === "object") return value;
    if (
      value.nativeDocument
      && value.nativeDocument.schema_version === "schauwerk-native-editing-document.v1"
      && value.nativeCanvas
      && typeof value.nativeCanvas === "object"
      && !Array.isArray(value.nativeCanvas)
    ) {
      return value;
    }
    return null;
  } catch (_) {
    return null;
  }
}

function readLatestDraft() {
  const legacy = readDraft();
  const native = readNativeDraft();
  if (!legacy) return native ? { ...native, kind: "native" } : null;
  if (!native) return { ...legacy, kind: "legacy" };
  return Number(native.savedAt || 0) >= Number(legacy.savedAt || 0)
    ? { ...native, kind: "native" }
    : { ...legacy, kind: "legacy" };
}

function clearPreparedDownload() {
  if (preparedDownloadUrl !== null) {
    URL.revokeObjectURL(preparedDownloadUrl);
    preparedDownloadUrl = null;
  }
  elements.downloadLink.hidden = true;
  elements.downloadLink.removeAttribute("href");
  elements.downloadLink.removeAttribute("download");
  elements.downloadLink.textContent = "Datei speichern";
}

function prepareDownload(blob, filename, label) {
  clearPreparedDownload();
  preparedDownloadUrl = URL.createObjectURL(blob);
  elements.downloadLink.href = preparedDownloadUrl;
  elements.downloadLink.download = filename;
  elements.downloadLink.textContent = `${label} speichern`;
  elements.downloadLink.hidden = false;
}

function setEditorFocus(active) {
  editorFocusActive = Boolean(active);
  document.body.classList.toggle("editor-focus", editorFocusActive);
  elements.fullscreenButton.setAttribute("aria-pressed", String(editorFocusActive));
  elements.fullscreenButton.setAttribute(
    "aria-label",
    editorFocusActive ? "Vollbildmodus beenden" : "Vollbildmodus aktivieren",
  );
  elements.fullscreenButton.textContent = editorFocusActive ? "Beenden" : "Vollbild";
  elements.fullscreenButton.title = editorFocusActive
    ? "Vollbildmodus beenden"
    : "Vollbildmodus für die Bearbeitung";
}

function toggleEditorFullscreen() {
  const active = !editorFocusActive;
  setEditorFocus(active);
  setStatus(active ? "Vollbildmodus aktiv" : "Vollbildmodus beendet");
}

function showStart() {
  invalidateLoadIntents();
  setEditorFocus(false);
  if (elements.contentDialog?.open) {
    elements.contentDialog.close();
  }
  pendingLoad = null;
  pendingInitialCollisionSafeLayout = false;
  pendingCreationDefaults = false;
  pendingExport = null;
  editorReady = false;
  nativeCanvasRenderStale = false;
  renderedNativeCanvasSnapshot = null;
  currentLegacyXml = null;
  pendingLegacyFallback = null;
  elements.legacyFallbackButton.hidden = true;
  elements.nativeRetryButton.hidden = true;
  replaceEditorFrame();
  clearPreparedDownload();
  elements.workspace.hidden = true;
  elements.startView.hidden = false;
  setError("");
  setStatus(currentXml || currentRepresentation ? "Entwurf lokal gesichert" : "Bereit");
  elements.sourceInput.focus({ preventScroll: true });
}

function showWorkspace() {
  elements.startView.hidden = true;
  elements.workspace.hidden = false;
  elements.title.textContent = currentTitle;
}

function prepareInput(raw, title = "Schaubild") {
  const detected = detectInput(validateInputText(raw), {
    allowExtensionOnlyCanvas: /\.canvas$/i.test(String(title)),
  });
  currentTitle = safeFilename(title.replace(/\.(canvas|mmd|mermaid|drawio|xml|json)$/i, ""));
  currentXml = null;
  currentRepresentation = null;
  currentNativeDocument = null;
  currentNativeCanvas = null;
  currentNativeUrl = null;
  nativeCanvasRenderStale = false;
  renderedNativeCanvasSnapshot = null;
  pendingExport = null;

  if (detected.kind === "representation") {
    return {
      nativeRepresentation: detected.value,
      sourceMetadata: { key: "schauwerkImportFormat", value: "schauwerk-representation-input.v1" },
    };
  }
  if (detected.kind === "mermaid") {
    return {
      descriptor: { format: "mermaid", data: detected.text, wrap: true },
      sourceMetadata: { key: "schauwerkImportFormat", value: "mermaid" },
    };
  }
  if (detected.kind === "json-canvas") {
    return {
      nativeImport: {
        schema_version: NATIVE_IMPORT_SCHEMA,
        format: "json-canvas-1.0",
        source: detected.value,
        title: currentTitle,
      },
      nativeCanvas: detected.value,
      sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
    };
  }
  if (detected.kind === "json-canvas-rejected") {
    throw new Error(detected.reason);
  }
  if (detected.kind === "drawio") {
    const xml = validateDiagramXml(detected.text);
    return {
      nativeImport: {
        schema_version: NATIVE_IMPORT_SCHEMA,
        format: "drawio-xml",
        source: xml,
        title: currentTitle,
      },
      legacyXml: xml,
      sourceMetadata: { key: "schauwerkImportFormat", value: "drawio-xml" },
    };
  }
  if (detected.kind === "empty") {
    return { xml: emptyDrawioXml() };
  }
  throw new Error(
    "Format nicht erkannt. Unterstützt werden Schauwerk Representation, Mermaid, .canvas und draw.io/XML.",
  );
}

function replaceEditorFrame() {
  const previous = elements.frame;
  const frame = previous.cloneNode(false);
  frame.inert = false;
  frame.removeAttribute("src");
  previous.replaceWith(frame);
  elements.frame = frame;
  return frame;
}

function launch(load) {
  if (load?.nativeRepresentation || load?.nativeDocument || load?.nativeImport) {
    void launchNative(load);
    return;
  }
  launchLegacy(load);
}

function launchLegacy(load) {
  invalidateLoadIntents();
  clearPreparedDownload();
  pendingExport = null;
  pendingLoad = load;
  currentRepresentation = null;
  currentNativeDocument = null;
  currentNativeCanvas = null;
  currentLegacyXml = typeof load?.xml === "string" ? load.xml : null;
  pendingLegacyFallback = null;
  elements.legacyFallbackButton.hidden = true;
  elements.nativeRetryButton.hidden = true;
  currentNativeUrl = null;
  nativeCanvasRenderStale = false;
  renderedNativeCanvasSnapshot = null;
  setEngineMode("legacy");
  pendingInitialCollisionSafeLayout = load?.sourceMetadata?.value === "mermaid";
  const sourceFormat = load?.sourceMetadata?.value;
  pendingCreationDefaults = sourceFormat === "mermaid" || sourceFormat === "json-canvas-1.0" || load?.xml === emptyDrawioXml();
  editorReady = false;
  const frame = replaceEditorFrame();
  showWorkspace();
  setStatus("Kompatibilitätseditor wird geladen …");
  requestAnimationFrame(() => {
    if (elements.frame !== frame) return;
    frame.src = EDITOR_URL;
  });
}

function nativeTokenFromUrl(value) {
  const nativeUrl = String(value || "");
  const prefix = `${PUBLIC_BASE_PATH}/native/`;
  const suffix = "/index.html";
  if (!nativeUrl.startsWith(prefix) || !nativeUrl.endsWith(suffix)) return "";
  const token = nativeUrl.slice(prefix.length, -suffix.length);
  return /^[0-9a-f]{32}$/.test(token) ? token : "";
}

async function launchNative(load, options = {}) {
  const loadIntent = invalidateLoadIntents();
  const preserveActiveFrame = Boolean(
    options.preserveActiveFrame && editorReady && currentNativeUrl,
  );
  const activeFrame = elements.frame;
  const activeNativeUrl = currentNativeUrl;
  const activeRepresentation = currentRepresentation;
  const activeNativeDocument = currentNativeDocument;
  const activeNativeCanvas = currentNativeCanvas;
  const activeLegacyXml = currentLegacyXml;
  const requestValue = load.nativeRepresentation || load.nativeDocument || load.nativeImport;
  clearPreparedDownload();
  pendingExport = null;
  pendingLoad = null;
  pendingInitialCollisionSafeLayout = false;
  pendingCreationDefaults = false;
  currentXml = null;
  currentRepresentation = load.nativeRepresentation || null;
  currentNativeDocument = load.nativeDocument || null;
  currentNativeCanvas = load.nativeCanvas || null;
  currentLegacyXml = typeof load.legacyXml === "string" ? load.legacyXml : null;
  pendingLegacyFallback = null;
  elements.legacyFallbackButton.hidden = true;
  elements.nativeRetryButton.hidden = true;
  if (!preserveActiveFrame) {
    currentNativeUrl = null;
    nativeCanvasRenderStale = false;
  } else {
    nativeCanvasRenderStale = true;
  }
  setEngineMode("native");
  if (!preserveActiveFrame) editorReady = false;
  let frame = elements.frame;
  if (preserveActiveFrame) {
    frame.inert = true;
    frame.blur();
    setError("");
  } else {
    frame = replaceEditorFrame();
    showWorkspace();
  }
  setStatus(
    preserveActiveFrame
      ? "Änderung wird übernommen …"
      : "Schaubild wird geöffnet …",
  );

  const previousLaunch = nativeLaunchTail;
  let releaseLaunchTurn = () => {};
  let permanentRecovery = null;
  let permanentRejectionMessage = "";
  nativeLaunchTail = new Promise((resolve) => {
    releaseLaunchTurn = resolve;
  });

  try {
    await previousLaunch;
    if (loadIntent !== loadIntentGeneration) return;

    const headers = { "Content-Type": "application/json" };
    if (nativeSupersedeToken) {
      headers["X-Schauwerk-Native-Supersede"] = nativeSupersedeToken;
    }
    const response = await fetch(NATIVE_API_PATH, {
      method: "POST",
      headers,
      body: JSON.stringify(requestValue),
    });
    const result = await response.json();
    const nativeUrl = String(result?.url || "");
    const nativeToken = nativeTokenFromUrl(nativeUrl);
    if (response.ok && nativeToken) {
      nativeSupersedeToken = nativeToken;
    }
    if (loadIntent !== loadIntentGeneration) return;
    if (!response.ok) {
      const renderError = new Error(result?.error || "Nativer Renderer hat die Eingabe abgelehnt.");
      renderError.nativeStatus = response.status;
      throw renderError;
    }
    if (
      !result ||
      result.renderer !== "schauwerk-native-diagram-v1" ||
      !/^[0-9a-f]{64}$/.test(String(result.input_digest || "")) ||
      !/^[0-9a-f]{32}$/.test(nativeToken)
    ) {
      throw new Error("Native Renderantwort verletzt den Schaubild-Vertrag.");
    }
    currentNativeUrl = nativeUrl;
    nativeCanvasRenderStale = false;
    renderedNativeCanvasSnapshot = nativeCanvasSnapshot(currentNativeCanvas);
    if (options.syncRepresentationTitle && currentRepresentation?.title) {
      currentTitle = safeFilename(currentRepresentation.title);
      elements.title.textContent = currentTitle;
    }
    if (currentRepresentation) {
      if (!saveNativeDraft(currentRepresentation)) {
        setStatus("Bereit · Quelle nicht lokal speicherbar");
      }
    } else if (currentNativeDocument && currentNativeCanvas) {
      if (!saveNativeCanvasDraft(currentNativeDocument, currentNativeCanvas)) {
        setStatus("Bereit · Dokument nicht lokal speicherbar");
      }
    } else if (currentLegacyXml && !saveDraft(currentLegacyXml)) {
      setStatus("Bereit · Original nicht lokal speicherbar");
    }
    editorReady = true;
    if (preserveActiveFrame) {
      frame = replaceEditorFrame();
      showWorkspace();
    }
    frame.src = currentNativeUrl;
    setEngineMode("native");
    setStatus(
      currentNativeCanvas
        ? "Bereit · Änderungen werden lokal gesichert"
        : (
            currentLegacyXml
              ? "Bereit · Original bleibt erhalten"
              : "Bereit · Inhalt und Ansicht bearbeitbar"
          )
    );
  } catch (error) {
    if (loadIntent !== loadIntentGeneration) return;
    const nativeStatus = Number(error?.nativeStatus || 0);
    const permanentCandidateRejection = (
      preserveActiveFrame
      && !options.recoveryAttempt
      && (nativeStatus === 413 || nativeStatus === 422)
    );
    if (permanentCandidateRejection) {
      currentRepresentation = activeRepresentation;
      currentNativeDocument = activeNativeDocument;
      currentNativeCanvas = activeNativeCanvas;
      currentLegacyXml = activeLegacyXml;
      currentNativeUrl = activeNativeUrl;
      nativeCanvasRenderStale = true;
      editorReady = true;
      elements.nativeRetryButton.hidden = true;
      if (elements.frame === activeFrame) activeFrame.inert = true;
      permanentRejectionMessage = (
        error instanceof Error ? error.message : "Native Änderung wurde abgelehnt."
      );
      if (activeNativeDocument && activeNativeCanvas && activeNativeUrl) {
        permanentRecovery = {
          nativeDocument: activeNativeDocument,
          nativeCanvas: activeNativeCanvas,
          sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
        };
        setEngineMode("native");
        setError(
          permanentRejectionMessage
          + " Die abgelehnte Änderung wurde verworfen; der letzte gültige Dokumentzustand wird neu gerendert.",
        );
        setStatus(
          "Native Änderung abgelehnt · letzter gültiger Dokumentzustand wird wiederhergestellt",
        );
      } else {
        nativeCanvasRenderStale = false;
        if (elements.frame === activeFrame) {
          frame = replaceEditorFrame();
          showWorkspace();
          frame.src = activeNativeUrl;
        }
        setEngineMode("native");
        setError(
          permanentRejectionMessage
          + " Die abgelehnte Änderung wurde verworfen; der letzte gültige Dokumentzustand ist wieder aktiv.",
        );
        setStatus(
          "Native Änderung abgelehnt · letzter gültiger Dokumentzustand wiederhergestellt",
        );
        return;
      }
    } else if (preserveActiveFrame) {
      currentNativeUrl = activeNativeUrl;
      nativeCanvasRenderStale = true;
      editorReady = true;
      if (elements.frame === activeFrame) activeFrame.inert = true;
      elements.nativeRetryButton.hidden = false;
      let nativeDraftSaved = null;
      let recoveryExport = "";
      if (currentNativeDocument && currentNativeCanvas) {
        nativeDraftSaved = saveNativeCanvasDraft(
          currentNativeDocument,
          currentNativeCanvas,
        );
        recoveryExport = ".canvas-Export enthält den aktuellen Dokumentzustand";
      } else if (currentRepresentation) {
        nativeDraftSaved = saveNativeDraft(currentRepresentation);
        recoveryExport = "Quellenexport enthält den aktuellen Inhaltsstand";
      }
      const draftErrorSuffix = (
        nativeDraftSaved === true
          ? " Der aktuelle Stand wurde zusätzlich lokal als Entwurf gesichert."
          : (
              nativeDraftSaved === false
                ? " Der aktuelle Stand konnte nicht lokal als Entwurf gespeichert werden."
                : ""
            )
      );
      const draftStatusSuffix = (
        nativeDraftSaved === true
          ? " · Entwurf lokal gesichert"
          : (nativeDraftSaved === false ? " · Entwurf lokal nicht speicherbar" : "")
      );
      setError(
        (error instanceof Error ? error.message : "Native Änderung konnte nicht gerendert werden.")
        + " Bestehende Ansicht bleibt sichtbar und gesperrt; "
        + recoveryExport
        + "."
        + draftErrorSuffix
        + " Mit „Neu rendern“ erneut versuchen.",
      );
      setStatus(
        "Native Änderung nicht neu gerendert · „Neu rendern“ zum Wiederholen"
        + draftStatusSuffix,
      );
      return;
    } else {
      editorReady = false;
      currentNativeUrl = null;
      let fallbackXml = currentLegacyXml;
      if (!fallbackXml && currentNativeCanvas) {
        try {
          fallbackXml = jsonCanvasToDrawioXml(currentNativeCanvas, {
            nodeFontSize: preferredNodeFontSize,
            edgeFontSize: edgeFontSizeFor(preferredNodeFontSize),
          });
        } catch (_) {
          fallbackXml = null;
        }
      }
      currentLegacyXml = null;
      elements.workspace.hidden = true;
      elements.startView.hidden = false;
      if (fallbackXml) {
        pendingLegacyFallback = fallbackXml;
        elements.legacyFallbackButton.hidden = false;
        setError(
          (error instanceof Error ? error.message : "Nativer Import wurde abgelehnt.")
          + " Das Original wurde nicht verändert. Legacy-Bearbeitung kann ausdrücklich geöffnet werden."
        );
        setStatus("Nativer Import abgelehnt · Legacy verfügbar");
      } else {
        setError(error instanceof Error ? error.message : "Native Darstellung konnte nicht geladen werden.");
        setStatus("Native Darstellung abgelehnt");
      }
    }
  } finally {
    releaseLaunchTurn();
  }

  if (permanentRecovery) {
    await launchNative(
      permanentRecovery,
      { preserveActiveFrame: true, recoveryAttempt: true },
    );
    if (!nativeCanvasRenderStale && editorReady) {
      setError(
        permanentRejectionMessage
        + " Die abgelehnte Änderung wurde verworfen; der letzte gültige Dokumentzustand ist wieder aktiv.",
      );
      setStatus(
        "Native Änderung abgelehnt · letzter gültiger Dokumentzustand wiederhergestellt",
      );
    }
  }
}

async function retryNativeRender() {
  if (!nativeCanvasRenderStale || !editorReady || !currentNativeUrl) {
    elements.nativeRetryButton.hidden = true;
    setStatus("Keine fehlgeschlagene native Änderung zum erneuten Rendern");
    return;
  }
  let retryLoad = null;
  if (currentNativeDocument && currentNativeCanvas) {
    retryLoad = {
      nativeDocument: currentNativeDocument,
      nativeCanvas: currentNativeCanvas,
      sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
    };
  } else if (currentRepresentation) {
    retryLoad = {
      nativeRepresentation: currentRepresentation,
      sourceMetadata: {
        key: "schauwerkImportFormat",
        value: "schauwerk-representation-input.v1",
      },
    };
  }
  if (!retryLoad) {
    elements.nativeRetryButton.hidden = true;
    setStatus("Keine fehlgeschlagene native Änderung zum erneuten Rendern");
    return;
  }
  const syncRepresentationTitle = Boolean(
    retryLoad.nativeRepresentation && !retryLoad.nativeDocument
  );
  elements.nativeRetryButton.hidden = true;
  await launchNative(
    retryLoad,
    { preserveActiveFrame: true, syncRepresentationTitle },
  );
}

function loadPendingIntoEditor() {
  const base = {
    action: "load",
    autosave: 1,
    exportProtocol: true,
    title: currentTitle,
    libs: "general;flowchart",
    fit: 1,
    maxFitScale: 1,
    modified: "unsavedChanges",
    noExitBtn: 1,
  };
  postToEditor({ ...base, ...(pendingLoad || { xml: emptyDrawioXml() }) });
  pendingLoad = null;
}

function enforceReadableInitialScale(scale) {
  const steps = readabilityZoomStepCount(scale);
  for (let step = 0; step < steps; step += 1) {
    postToEditor({ action: "invokeAction", actionName: "zoomIn" });
  }
}

function requestCollisionSafeLayout() {
  postToEditor({
    action: "layout",
    layouts: [{ layout: "elkLayered", config: COLLISION_SAFE_LAYOUT_CONFIG }],
  });
}

function openPasted() {
  setError("");
  try {
    launch(prepareInput(elements.sourceInput.value, "Schaubild"));
  } catch (error) {
    setError(error instanceof Error ? error.message : "Eingabe konnte nicht geöffnet werden.");
  }
}

async function openFile(file) {
  setError("");
  if (!file) return;
  const loadIntent = invalidateLoadIntents();
  if (file.size > MAX_INPUT_BYTES) {
    setError("Die Datei ist für diesen Spike zu groß (maximal 5 MB).\n");
    return;
  }
  try {
    const text = await file.text();
    if (loadIntent !== loadIntentGeneration) return;
    launch(prepareInput(text, file.name));
  } catch (error) {
    if (loadIntent !== loadIntentGeneration) return;
    setError(error instanceof Error ? error.message : "Datei konnte nicht geöffnet werden.");
  }
}

function nativeCanvasSnapshot(canvas) {
  if (!canvas || typeof canvas !== "object" || Array.isArray(canvas)) return null;
  try {
    return JSON.stringify(canvas, (_key, value) => {
      if (value === null || typeof value !== "object" || Array.isArray(value)) return value;
      return Object.fromEntries(
        Object.keys(value).sort().map((key) => [key, value[key]]),
      );
    });
  } catch (_) {
    return null;
  }
}

function nativeCanvasDiffersFromRendered(canvas) {
  if (!canvas) return false;
  const snapshot = nativeCanvasSnapshot(canvas);
  return (
    renderedNativeCanvasSnapshot === null
    || snapshot === null
    || snapshot !== renderedNativeCanvasSnapshot
  );
}

function serializeNativeFrameSvg({ stripInputDigest = false } = {}) {
  try {
    const svg = elements.frame.contentDocument?.querySelector("#nativeDiagram");
    if (
      !svg ||
      svg.namespaceURI !== "http://www.w3.org/2000/svg" ||
      svg.localName !== "svg"
    ) {
      return null;
    }
    const clone = svg.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    if (stripInputDigest) clone.removeAttribute("data-input-digest");
    return '<?xml version="1.0" encoding="UTF-8"?>\n'
      + new XMLSerializer().serializeToString(clone)
      + "\n";
  } catch (_) {
    return null;
  }
}

async function exportNative(format) {
  if (!editorReady || (!currentRepresentation && !currentNativeDocument && !currentNativeCanvas && !currentLegacyXml) || !currentNativeUrl) {
    setStatus("Schaubild ist noch nicht bereit");
    return;
  }
  clearPreparedDownload();
  if (format === "drawio") {
    if (currentNativeCanvas) {
      const source = JSON.stringify(currentNativeCanvas, null, 2) + "\n";
      prepareDownload(
        new Blob([source], { type: "application/json;charset=utf-8" }),
        safeFilename(currentTitle) + ".canvas",
        "JSON Canvas",
      );
      setStatus("Bearbeitete .canvas-Datei bereit");
      return;
    }
    if (currentLegacyXml) {
      prepareDownload(
        new Blob([currentLegacyXml], { type: "application/xml;charset=utf-8" }),
        safeFilename(currentTitle) + ".drawio",
        "Originalprojekt",
      );
      setStatus("Unverändertes draw.io-Original bereit");
      return;
    }
    const source = JSON.stringify(currentRepresentation, null, 2) + "\n";
    prepareDownload(
      new Blob([source], { type: "application/json;charset=utf-8" }),
      safeFilename(currentTitle) + ".schauwerk.json",
      "Quelle",
    );
    setStatus("Kanonische Quelle bereit");
    return;
  }
  if (format === "png") {
    setStatus("PNG ist für dieses Schaubild noch nicht verfügbar");
    return;
  }
  if (format !== "svg") {
    setStatus("Exportformat wird nicht unterstützt");
    return;
  }
  if ((currentNativeCanvas || currentRepresentation) && nativeCanvasRenderStale) {
    setStatus(
      currentNativeCanvas
        ? "Aktuelle SVG-Ausgabe ist nach Renderfehler nicht synchron · .canvas bleibt verfügbar"
        : "Aktuelle SVG-Ausgabe ist nach Renderfehler nicht synchron · Quelle bleibt verfügbar",
    );
    return;
  }
  const liveSvg = serializeNativeFrameSvg({
    stripInputDigest: currentNativeCanvas
      ? nativeCanvasDiffersFromRendered(currentNativeCanvas)
      : true,
  });
  if (liveSvg !== null) {
    prepareDownload(
      new Blob([liveSvg], { type: "image/svg+xml;charset=utf-8" }),
      safeFilename(currentTitle) + ".svg",
      "SVG",
    );
    setStatus(
      currentNativeCanvas
        ? "SVG aus aktuellem Canvas-Dokument bereit"
        : "SVG aus aktueller nativer Darstellung bereit",
    );
    return;
  }
  if (currentNativeCanvas) {
    setStatus("Aktuelle SVG-Ausgabe konnte nicht gelesen werden");
    return;
  }
  const assetUrl = currentNativeUrl.replace(/index\.html$/, "diagram.svg");
  try {
    const response = await fetch(assetUrl, { cache: "no-store" });
    if (!response.ok) throw new Error("SVG konnte nicht gelesen werden.");
    const svg = await response.text();
    prepareDownload(
      new Blob([svg], { type: "image/svg+xml;charset=utf-8" }),
      safeFilename(currentTitle) + ".svg",
      "SVG",
    );
    setStatus("SVG bereit");
  } catch (_) {
    setStatus("SVG konnte nicht vorbereitet werden");
  }
}

function exportDiagram(format) {
  if (activeEngine === "native") {
    void exportNative(format);
    return;
  }
  if (!editorReady) {
    setStatus("Editor ist noch nicht bereit");
    return;
  }
  if (pendingExport !== null) {
    setStatus("Export läuft bereits …");
    return;
  }
  clearPreparedDownload();
  pendingExport = format;
  if (format === "drawio") {
    // The embed protocol has no XML export format. A supported SVG export
    // returns the current diagram XML alongside the image data.
    postToEditor({ action: "export", format: "svg", embedImages: false, border: 0 });
    return;
  }
  if (format === "png") {
    postToEditor({ action: "export", format: "png", scale: 3, border: 24, background: "#ffffff", size: "diagram" });
    return;
  }
  postToEditor({ action: "export", format: "svg", border: 24, background: "#ffffff", size: "diagram", embedImages: true });
}

window.addEventListener("message", (event) => {
  if (event.source !== elements.frame.contentWindow) return;
  const message = parseMessage(event.data);
  if (!message) return;

  if (event.origin === window.location.origin) {
    if (message.event === "native-document-change") {
      if (
        message.document &&
        message.document.schema_version === "schauwerk-native-editing-document.v1" &&
        message.canvas &&
        typeof message.canvas === "object"
      ) {
        currentNativeDocument = message.document;
        currentNativeCanvas = message.canvas;
        const draftSaved = saveNativeCanvasDraft(message.document, message.canvas);
        setEngineMode("native");
        setStatus(
          draftSaved
            ? "Gesichert"
            : "Änderung aktiv · lokales Speichern nicht möglich",
        );
      }
      return;
    }
    if (message.event === "native-document-rebuild") {
      if (
        message.document &&
        message.document.schema_version === "schauwerk-native-editing-document.v1" &&
        message.canvas &&
        typeof message.canvas === "object"
      ) {
        void launchNative({
          nativeDocument: message.document,
          nativeCanvas: message.canvas,
          sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
        }, { preserveActiveFrame: true });
      }
      return;
    }
    return;
  }

  if (event.origin !== EDITOR_ORIGIN) return;

  if (message.event === "configure") {
    const config = {
      defaultFonts: ["Helvetica", "Arial", "Verdana"],
      zoomFactor: READABILITY_ZOOM_FACTOR,
      enabledLibraries: ["general", "flowchart"],
    };
    if (pendingCreationDefaults) {
      Object.assign(config, {
        defaultVertexStyle: { fontSize: String(preferredNodeFontSize) },
        defaultEdgeStyle: {
          fontSize: String(edgeFontSizeFor(preferredNodeFontSize)),
          edgeStyle: "orthogonalEdgeStyle",
          rounded: "1",
          orthogonalLoop: "1",
          jettySize: "auto",
          sourcePerimeterSpacing: "12",
          targetPerimeterSpacing: "12",
          spacing: "6",
          labelBackgroundColor: "#ffffff",
        },
      });
      config.defaultVertexStyle.align = "left";
    }
    postToEditor({ action: "configure", config });
    return;
  }
  if (message.event === "init") {
    editorReady = true;
    loadPendingIntoEditor();
    return;
  }
  if (message.event === "load") {
    const shouldAutoLayout = pendingInitialCollisionSafeLayout;
    pendingInitialCollisionSafeLayout = false;
    enforceReadableInitialScale(message.scale);
    if (shouldAutoLayout) {
      requestCollisionSafeLayout();
      setStatus("Bereit · Layout wird optimiert");
    } else {
      setStatus("Bereit · Änderungen werden lokal gesichert");
    }
    return;
  }
  if (message.event === "autosave" || message.event === "save") {
    try {
      if (saveDraft(validateDiagramXml(message.xml))) {
        setStatus("Lokal gesichert");
      }
    } catch (_) {
      setStatus("Ungültigen Autosave verworfen");
    }
    return;
  }
  if (message.event === "export") {
    const wanted = pendingExport;
    if (wanted === null) return;
    pendingExport = null;

    let validatedData = null;
    let validatedXml = null;
    let filename;
    let label;
    try {
      if (wanted === "drawio") {
        if (message.format !== "svg") throw new Error("Unerwartete Exportantwort.");
        validatedXml = validateDiagramXml(message.xml);
        saveDraft(validatedXml);
        filename = `${safeFilename(currentTitle)}.drawio`;
        label = "Projekt";
      } else if (wanted === "png" || wanted === "svg") {
        if (message.format !== wanted) throw new Error("Unerwartete Exportantwort.");
        validatedData = validateExportDataUri(message.data, wanted);
        if (typeof message.xml === "string") saveDraft(validateDiagramXml(message.xml));
        filename = `${safeFilename(currentTitle)}.${wanted}`;
        label = wanted.toUpperCase();
      } else {
        throw new Error("Exportantwort ohne passende Anforderung.");
      }
    } catch (_) {
      setStatus("Unsichere oder ungültige Exportantwort verworfen");
      return;
    }

    try {
      const blob = wanted === "drawio"
        ? new Blob([validatedXml], { type: "application/xml;charset=utf-8" })
        : exportDataUriToBlob(validatedData, wanted);
      prepareDownload(blob, filename, label);
    } catch (_) {
      setStatus("Export konnte nicht zum Speichern vorbereitet werden");
      return;
    }
    setStatus(`Export bereit · „${label} speichern“ tippen`);
    return;
  }
  if (message.event === "openLink") {
    setStatus("Externe Links sind hier deaktiviert");
    return;
  }
  if (message.error) setStatus("Editor meldet einen Fehler");
});

elements.openPasteButton.addEventListener("click", openPasted);
elements.fileButton.addEventListener("click", () => elements.fileInput.click());
elements.fileInput.addEventListener("change", () => {
  const file = elements.fileInput.files?.[0] ?? null;
  elements.fileInput.value = "";
  if (file) openFile(file);
});
elements.blankButton.addEventListener("click", () => {
  currentTitle = "Schaubild";
  launch({ xml: emptyDrawioXml() });
});
elements.restoreButton.addEventListener("click", () => {
  const draft = readLatestDraft();
  if (!draft) return;
  if (draft.kind === "native") {
    currentTitle = safeFilename(draft.title || "Schaubild");
    if (draft.nativeDocument && draft.nativeCanvas) {
      launch({
        nativeDocument: draft.nativeDocument,
        nativeCanvas: draft.nativeCanvas,
        sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
      });
      return;
    }
    launch({
      nativeRepresentation: draft.representation,
      sourceMetadata: { key: "schauwerkImportFormat", value: "schauwerk-representation-input.v1" },
    });
    return;
  }
  try {
    launch(prepareInput(draft.xml, draft.title || "Schaubild"));
  } catch (error) {
    setError(error instanceof Error ? error.message : "Lokaler Entwurf konnte nicht geöffnet werden.");
  }
});
elements.legacyEditButton.addEventListener("click", () => {
  if (!currentLegacyXml) return;
  launchLegacy({ xml: currentLegacyXml });
});
elements.legacyFallbackButton.addEventListener("click", () => {
  if (!pendingLegacyFallback) return;
  const xml = pendingLegacyFallback;
  pendingLegacyFallback = null;
  elements.legacyFallbackButton.hidden = true;
  launchLegacy({ xml });
});
elements.contentEditButton.addEventListener("click", openRepresentationContentEditor);
elements.contentSaveButton.addEventListener("click", () => {
  void saveRepresentationContentEditor();
});
elements.nativeRetryButton.addEventListener("click", () => { void retryNativeRender(); });
elements.projectButton.addEventListener("click", () => exportDiagram("drawio"));
elements.fontDefaultInput.addEventListener("change", applyFontPreferenceInput);
elements.fontDecreaseButton.addEventListener("click", () => {
  if (!editorReady) return setStatus("Editor ist noch nicht bereit");
  postToEditor({ action: "invokeAction", actionName: "decreaseFontSize" });
  setStatus("Schriftgröße der Auswahl wird verkleinert");
});
elements.fontIncreaseButton.addEventListener("click", () => {
  if (!editorReady) return setStatus("Editor ist noch nicht bereit");
  postToEditor({ action: "invokeAction", actionName: "increaseFontSize" });
  setStatus("Schriftgröße der Auswahl wird vergrößert");
});
elements.fontPanelButton.addEventListener("click", () => {
  if (!editorReady) return setStatus("Editor ist noch nicht bereit");
  postToEditor({ action: "invokeAction", actionName: "format" });
  setStatus("Textformatierung für die Auswahl geöffnet");
});
elements.fontAllButton.addEventListener("click", () => {
  if (!editorReady) return setStatus("Editor ist noch nicht bereit");
  postToEditor({ action: "invokeAction", actionName: "selectAll" });
  postToEditor({ action: "invokeAction", actionName: "format" });
  setStatus("Gesamtes Schaubild ausgewählt · Schrift im Text-Panel einstellen");
});
elements.downloadLink.addEventListener("click", () => {
  if (preparedDownloadUrl !== null) setStatus("Speichern gestartet");
});
elements.fullscreenButton.addEventListener("click", toggleEditorFullscreen);

elements.layoutButton.addEventListener("click", () => {
  if (!editorReady) return;
  requestCollisionSafeLayout();
  setStatus("Layout wird berechnet …");
});
document.querySelectorAll("[data-export]").forEach((button) => {
  button.addEventListener("click", () => exportDiagram(button.dataset.export));
});
elements.backButton.addEventListener("click", showStart);
elements.homeLink.addEventListener("click", (event) => { event.preventDefault(); showStart(); });

elements.startView.addEventListener("dragover", (event) => { event.preventDefault(); });
elements.startView.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer?.files?.[0];
  if (file) openFile(file);
});

elements.sourceInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") openPasted();
});

preferredNodeFontSize = readFontPreference();
elements.fontDefaultInput.value = String(preferredNodeFontSize);

const initialQuery = new URLSearchParams(window.location.search);
if (initialQuery.get("new") === "1") {
  currentTitle = "Schaubild";
  launch({ xml: emptyDrawioXml() });
}

elements.restoreButton.hidden = !readLatestDraft();
"""

ASSETS = {
    "index.html": INDEX_HTML,
    "styles.css": STYLES_CSS,
    "canvas-import.js": CANVAS_IMPORT_JS,
    "app.js": APP_JS,
}
