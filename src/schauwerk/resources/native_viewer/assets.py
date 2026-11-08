"""No-build browser assets for the Phase-2 native interaction proof."""
# ruff: noqa: E501

from __future__ import annotations

from .hybrid_preview import HYBRID_PREVIEW_CSS, HYBRID_PREVIEW_JS
from .smart_router import SMART_ROUTER_JS

INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <title>__SCHAUWERK_NATIVE_TITLE__</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="viewer-shell">
    <header class="viewer-bar">
      <div class="viewer-heading">
        <div class="viewer-title">
          <span class="eyebrow">Arbeitsfläche</span>
          <strong>__SCHAUWERK_NATIVE_TITLE__</strong>
        </div>
        <span class="status" id="status" role="status" aria-live="polite">Bereit</span>
      </div>

      <div class="controls" aria-label="Schaubild steuern">
        <div class="view-controls" role="group" aria-label="Ansicht">
          <button id="zoomOut" class="icon-control" type="button" aria-label="Verkleinern" title="Verkleinern">−</button>
          <output id="zoomValue" aria-label="Zoomstufe">100 %</output>
          <button id="zoomIn" class="icon-control" type="button" aria-label="Vergrößern" title="Vergrößern">+</button>
          <button id="fitView" type="button">Einpassen</button>
          <button id="smartRouting" class="document-only" type="button" aria-pressed="false" aria-label="Intelligente Kantenführung einschalten" hidden>Intelligente Kantenführung: Aus</button>
          <button id="hybridPreview" class="document-only" type="button" aria-pressed="false" aria-label="HTML-Vorschau einschalten (schreibgeschützt)" title="Vorschau: Text als HTML darstellen. Nur lesen; Bearbeiten ist gesperrt, bis Sie zu Native zurückkehren." hidden>HTML-Vorschau</button>
          <button id="observationMode" type="button" aria-pressed="false" aria-label="Beobachtungsmodus einschalten" title="Schaubild nur betrachten, ohne Elemente zu verändern">Beobachten</button>
          <button id="resetLayout" class="icon-control" type="button" aria-label="Positionen zurücksetzen" title="Positionen zurücksetzen">↺</button>
        </div>
        <details class="edit-controls document-only" hidden>
          <summary>Bearbeiten</summary>
          <div class="edit-menu" role="group" aria-label="Bearbeiten">
            <button id="addNode" class="document-only" type="button" aria-label="Element hinzufügen" title="Element hinzufügen" hidden>+ Element</button>
            <button id="addEdge" class="document-only" type="button" aria-label="Verbindung hinzufügen" title="Zuerst ein Element auswählen" hidden>+ Verbindung</button>
            <button id="editText" class="document-only" type="button" aria-label="Text bearbeiten" title="Zuerst ein Element oder eine Verbindung auswählen" hidden>Text</button>
            <button id="reattachSource" class="document-only" type="button" aria-label="Anfang ändern" title="Zuerst eine Verbindung auswählen" hidden>Anfang</button>
            <button id="reattachTarget" class="document-only" type="button" aria-label="Ende ändern" title="Zuerst eine Verbindung auswählen" hidden>Ende</button>
            <div id="edgePorts" class="edge-port-controls document-only" hidden>
              <label for="edgeFromPort">Anfangsseite</label>
              <select id="edgeFromPort" aria-label="Anschlussseite am Anfang">
                <option value="">Auto</option>
                <option value="left">Links</option>
                <option value="right">Rechts</option>
                <option value="top">Oben</option>
                <option value="bottom">Unten</option>
              </select>
              <label for="edgeToPort">Zielseite</label>
              <select id="edgeToPort" aria-label="Anschlussseite am Ziel">
                <option value="">Auto</option>
                <option value="left">Links</option>
                <option value="right">Rechts</option>
                <option value="top">Oben</option>
                <option value="bottom">Unten</option>
              </select>
              <label for="edgeFromEnd">Startpfeil</label>
              <select id="edgeFromEnd" aria-label="Pfeilrichtung am Anfang">
                <option value="none">Keiner</option>
                <option value="arrow">Pfeil</option>
              </select>
              <label for="edgeToEnd">Zielpfeil</label>
              <select id="edgeToEnd" aria-label="Pfeilrichtung am Ziel">
                <option value="none">Keiner</option>
                <option value="arrow">Pfeil</option>
              </select>
              <label for="edgeKind">Beziehung</label>
              <select id="edgeKind" aria-label="Beziehungstyp">
                <option value="flow">Verbindung</option>
                <option value="association">Assoziation</option>
                <option value="feedback">Rückkopplung</option>
              </select>
            </div>
            <button id="deleteSelection" class="document-only destructive-control" type="button" aria-label="Auswahl löschen" title="Zuerst ein Element oder eine Verbindung auswählen" hidden>Löschen</button>
          </div>
        </details>
      </div>
    </header>

    <section class="viewer-stage" id="nativeViewport" aria-label="Interaktives Schaubild">
      <div class="native-canvas" id="nativeCanvas">
__SCHAUWERK_NATIVE_SVG__
      </div>
    </section>

    <footer class="viewer-foot">
      <span id="selectionStatus">Keine Auswahl</span>
      <span id="interactionHint">Verschieben · Zoomen · Auswählen</span>
      <span id="authorityHint">Änderungen bleiben lokal</span>
    </footer>
  </main>

  <dialog id="textDialog" class="text-dialog">
    <form method="dialog">
      <label for="textInput">Text bearbeiten</label>
      <textarea id="textInput" rows="5"></textarea>
      <div class="dialog-actions">
        <button id="cancelText" value="cancel" type="submit">Abbrechen</button>
        <button id="saveText" class="primary-control" value="default" type="button">Übernehmen</button>
      </div>
    </form>
  </dialog>

  <script id="nativeLimits" type="application/json">__SCHAUWERK_NATIVE_LIMITS__</script>
  <script id="nativeModel" type="application/json">__SCHAUWERK_NATIVE_MODEL__</script>
  <script type="module" src="app.js"></script>
</body>
</html>
"""

STYLES_CSS = r""":root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color-scheme: light;
  color: #171927;
  background: #edf0f6;
  font-synthesis: none;
  --surface: rgba(255, 255, 255, 0.94);
  --surface-soft: #f4f5f9;
  --ink: #171927;
  --muted: #6f7280;
  --line: #dfe2ea;
  --line-strong: #cfd3df;
  --accent: #635bff;
  --accent-soft: #efeeff;
  --danger: #a93333;
  --stage: #f4f6fa;
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; }
button, output, textarea { font: inherit; }

button {
  min-width: 36px;
  min-height: 36px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  padding: 6px 10px;
  color: #343746;
  background: rgba(255, 255, 255, 0.9);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  cursor: pointer;
  touch-action: manipulation;
  transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
}
button:hover {
  border-color: #bfc3d0;
  background: #ffffff;
  transform: translateY(-1px);
}
button:active { transform: translateY(0); }
button:disabled {
  border-color: transparent;
  color: #9a9da9;
  background: transparent;
  cursor: default;
  transform: none;
  opacity: 0.5;
}
button:disabled:hover {
  border-color: transparent;
  background: transparent;
  transform: none;
}
button:focus-visible {
  outline: 3px solid rgba(99, 91, 255, 0.28);
  outline-offset: 2px;
}
.icon-control {
  width: 36px;
  padding-inline: 0;
  font-size: 1rem;
}
.primary-control {
  border-color: var(--accent);
  color: #fff;
  background: var(--accent);
}
.destructive-control { color: var(--danger); }

.viewer-shell {
  position: relative;
  height: 100vh;
  height: 100dvh;
}
.viewer-bar {
  position: absolute;
  z-index: 3;
  top: max(7px, env(safe-area-inset-top));
  left: max(7px, env(safe-area-inset-left), var(--host-safe-left, 0px));
  right: max(7px, env(safe-area-inset-right), var(--host-safe-right, 0px));
  min-height: 0;
  padding: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  border: 0;
  background: transparent;
  pointer-events: none;
}
.viewer-heading {
  min-width: 0;
  max-width: min(42vw, 460px);
  padding: 4px 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 4px 16px rgba(25, 28, 42, 0.12);
  backdrop-filter: blur(14px) saturate(140%);
  pointer-events: auto;
}
.viewer-title {
  min-width: 0;
  display: grid;
  gap: 1px;
}
.viewer-title strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.84rem;
}
.eyebrow {
  color: var(--accent);
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.status {
  min-width: 0;
  max-width: min(30vw, 360px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 8px;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: 0.68rem;
  font-weight: 680;
}
.controls {
  min-width: 0;
  max-width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
  pointer-events: auto;
}
.view-controls {
  min-width: 0;
  max-width: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--surface);
  box-shadow: 0 4px 16px rgba(25, 28, 42, 0.12);
  backdrop-filter: blur(14px) saturate(140%);
}
.controls output {
  min-width: 48px;
  text-align: center;
  color: var(--muted);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}
.view-controls button {
  border-color: transparent;
  background: transparent;
}
.view-controls button:hover {
  border-color: var(--line);
  background: #fff;
}
.view-controls button:disabled:hover {
  border-color: transparent;
  background: transparent;
}
.view-controls #observationMode[aria-pressed="true"] {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}
.edit-controls {
  position: relative;
  min-width: 0;
}
.edit-controls > summary {
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 11px;
  padding: 6px 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  list-style: none;
  color: #343746;
  background: var(--surface);
  box-shadow: 0 4px 16px rgba(25, 28, 42, 0.12);
  backdrop-filter: blur(14px) saturate(140%);
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
  user-select: none;
}
.edit-controls > summary::-webkit-details-marker { display: none; }
.edit-controls[open] > summary {
  border-color: var(--line-strong);
  background: var(--surface-soft);
}
.edit-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: max-content;
  max-width: min(
    520px,
    calc(
      100vw - max(7px, env(safe-area-inset-left), var(--host-safe-left, 0px))
      - max(7px, env(safe-area-inset-right), var(--host-safe-right, 0px))
    )
  );
  padding: 5px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 4px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 8px 26px rgba(25, 28, 42, 0.18);
  backdrop-filter: blur(14px) saturate(140%);
}
.edit-menu button {
  border-color: transparent;
  background: transparent;
}
.edit-menu button:hover {
  border-color: var(--line);
  background: #fff;
}
.edge-port-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 6px;
}
.edge-port-controls label { font-size: 0.74rem; font-weight: 650; }
.edge-port-controls select {
  min-height: 38px;
  padding: 4px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  color: var(--ink);
  background: var(--surface);
}
.view-controls #smartRouting[aria-pressed="true"] {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--accent);
}
.document-editor-hosted .viewer-title { display: none; }
.document-editor-hosted .viewer-heading {
  max-width: min(32vw, 320px);
  padding: 0;
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}
.document-editor-hosted .status { max-width: min(32vw, 320px); }

.viewer-stage {
  position: absolute;
  inset: 0;
  min-height: 0;
  overflow: hidden;
  background:
    linear-gradient(rgba(99, 91, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99, 91, 255, 0.035) 1px, transparent 1px),
    var(--stage);
  background-size: 24px 24px;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.viewer-stage.is-panning { cursor: grabbing; }
.native-canvas {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
  will-change: transform;
}
.native-diagram { display: block; max-width: none; max-height: none; }
.native-diagram [data-source-kind="node"] { cursor: grab; outline: none; }
.native-diagram [data-source-kind="node"].is-dragging { cursor: grabbing; }
.native-diagram [data-source-kind="node"].is-selected > rect {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 5px rgba(99, 91, 255, 0.52));
}
.native-diagram [data-source-kind="node"]:focus-visible > rect {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 5px rgba(99, 91, 255, 0.42));
}
.native-diagram [data-source-kind="edge"] { cursor: pointer; }
.native-diagram [data-source-kind="edge"] > path.native-edge-hit {
  fill: none;
  stroke: transparent !important;
  pointer-events: stroke;
  filter: none !important;
}
.native-diagram [data-source-kind="edge"]:focus-visible > path:not(.native-edge-hit) {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 4px rgba(99, 91, 255, 0.46));
}
.viewer-stage.is-observing .native-diagram [data-source-kind="node"],
.viewer-stage.is-observing .native-diagram [data-source-kind="edge"] { cursor: grab; }
.viewer-stage.is-observing.is-panning .native-diagram [data-source-kind="node"],
.viewer-stage.is-observing.is-panning .native-diagram [data-source-kind="edge"] { cursor: grabbing; }
.native-diagram [data-source-kind="edge"].is-selected > path:not(.native-edge-hit) {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 4px rgba(99, 91, 255, 0.46));
}
.native-diagram [data-label-conflict="true"] > rect {
  fill: #ffedd5;
  stroke: #c2410c;
  stroke-width: 1px;
}
.native-diagram [data-connection-handles] .native-connection-handle {
  fill: #fff;
  stroke: var(--accent);
  stroke-width: 2px;
  cursor: crosshair;
  pointer-events: all;
}
.native-diagram [data-connection-handles] .native-connection-create {
  fill: var(--accent-soft);
}
.native-diagram [data-connection-handles] .native-connection-preview {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2.5px;
  stroke-dasharray: 6 5;
  pointer-events: none;
}

.text-dialog {
  width: min(560px, calc(100vw - 28px));
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  padding: 18px;
  color: var(--ink);
  background: #fff;
  box-shadow: 0 24px 70px rgba(30, 32, 48, 0.22);
}
.text-dialog::backdrop { background: rgba(15, 18, 30, 0.46); backdrop-filter: blur(3px); }
.text-dialog form { display: grid; gap: 12px; }
.text-dialog label { font-weight: 760; }
.text-dialog textarea {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  padding: 10px;
  color: var(--ink);
  background: var(--surface-soft);
}
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; }

.viewer-foot {
  position: absolute;
  z-index: 3;
  left: max(7px, env(safe-area-inset-left), var(--host-safe-left, 0px));
  bottom: max(7px, env(safe-area-inset-bottom), var(--host-footer-bottom, 0px));
  min-height: 0;
  max-width: calc(
    100vw - max(7px, env(safe-area-inset-left), var(--host-safe-left, 0px))
    - max(7px, env(safe-area-inset-right), var(--host-safe-right, 0px))
  );
  padding: 6px 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 11px;
  box-shadow: 0 4px 16px rgba(25, 28, 42, 0.12);
  backdrop-filter: blur(14px) saturate(140%);
  font-size: 0.68rem;
  pointer-events: none;
}
.viewer-foot span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
  font-weight: 700;
}
.viewer-foot span:last-child { margin-left: auto; }
.document-editor-hosted .viewer-foot span:not(:first-child) { display: none; }

@media (max-width: 980px) {
  .viewer-bar { gap: 6px; }
  .viewer-heading { max-width: min(46vw, 360px); }
  .status { max-width: min(42vw, 300px); }
  .controls { gap: 4px; }
  .document-editor-hosted .viewer-heading { max-width: min(30vw, 240px); }
  .document-editor-hosted .status {
    max-width: min(30vw, 240px);
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    overflow-wrap: anywhere;
    line-height: 1.3;
  }
}
@media (max-width: 620px) {
  button { min-width: 42px; min-height: 42px; }
  .viewer-bar {
    top: max(6px, env(safe-area-inset-top));
    left: max(6px, env(safe-area-inset-left), var(--host-safe-left, 0px));
    right: max(6px, env(safe-area-inset-right), var(--host-safe-right, 0px));
    flex-wrap: wrap;
    gap: 4px;
  }
  .viewer-heading .eyebrow { display: none; }
  .viewer-heading { max-width: 34vw; }
  .status {
    max-width: 100%;
    padding-inline: 7px;
  }
  .controls { margin-left: auto; gap: 3px; }
  .view-controls { padding: 2px; gap: 2px; }
  .edit-controls > summary { min-height: 42px; padding-inline: 8px; }
  .edit-menu {
    max-width: calc(
      100vw - max(6px, env(safe-area-inset-left), var(--host-safe-left, 0px))
      - max(6px, env(safe-area-inset-right), var(--host-safe-right, 0px))
    );
  }
  .viewer-foot {
    left: max(6px, env(safe-area-inset-left), var(--host-safe-left, 0px));
    bottom: max(6px, env(safe-area-inset-bottom), var(--host-footer-bottom, 0px));
    max-width: calc(
      100vw - max(6px, env(safe-area-inset-left), var(--host-safe-left, 0px))
      - max(6px, env(safe-area-inset-right), var(--host-safe-right, 0px))
    );
  }
}
@media (max-width: 430px) {
  .document-editor-hosted .viewer-heading { max-width: min(34vw, 128px); }
  .document-editor-hosted .status { max-width: 100%; }
  .document-editor-hosted .controls output { display: none; }
  .viewer-foot span:nth-child(2),
  .viewer-foot span:last-child { display: none; }
}

@media (max-width: 360px) {
  /* A live editing instruction must not sit underneath zoom/edit controls. */
  .viewer-bar { flex-wrap: wrap; gap: 4px; }
  .controls {
    order: 0;
    width: 100%;
    margin-left: 0;
    justify-content: flex-end;
  }
  .viewer-heading,
  .document-editor-hosted .viewer-heading {
    order: 1;
    flex: 0 0 100%;
    width: 100%;
    max-width: 100%;
    margin-top: 2px;
  }
  .document-editor-hosted .status {
    width: fit-content;
    max-width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; }
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    color: #f1f2f7;
    background: #10121a;
    --surface: rgba(18, 20, 29, 0.94);
    --surface-soft: #1d202b;
    --ink: #f1f2f7;
    --muted: #a4a8b8;
    --line: #2c303d;
    --line-strong: #3b4050;
    --accent: #8a83ff;
    --accent-soft: #29264c;
    --danger: #ffabab;
    --stage: #111621;
  }
  button { color: #e9eaf2; background: #242733; }
  button:hover { border-color: #4d5262; background: #2b2f3c; }
  .view-controls button:hover,
  .edit-menu button:hover { background: #292d39; }
  .edit-controls > summary,
  .edit-menu { color: var(--ink); background: rgba(18, 20, 29, 0.94); }
  .text-dialog { color: var(--ink); background: #181b24; }
  .text-dialog textarea { color: var(--ink); background: #10131b; }
}
"""

INTERACTION_JS = r"""export const MIN_SCALE = 0.25;
export const MAX_SCALE = 4;
export const MAX_LAYOUT_OFFSET = 10000;

function finite(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function boundedOffset(value) {
  return Math.max(-MAX_LAYOUT_OFFSET, Math.min(MAX_LAYOUT_OFFSET, finite(value)));
}

export function clampScale(value) {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, finite(value, 1)));
}

export function normalizeView(value = {}) {
  const scale = finite(value.scale, 1);
  return {
    x: finite(value.x),
    y: finite(value.y),
    scale: scale > 0 ? Math.min(MAX_SCALE, scale) : MIN_SCALE,
  };
}

export function panBy(view, dx, dy) {
  const current = normalizeView(view);
  return { ...current, x: current.x + finite(dx), y: current.y + finite(dy) };
}

export function interactionScale(startScale, requestedScale, minimumScale = startScale) {
  const requested = finite(requestedScale, startScale);
  // A fitted scale below 25% is the floor for the full zoom/pinch session,
  // not a new floor to ratchet upward on every interaction.
  const floor = Math.min(MIN_SCALE, Math.max(Number.MIN_VALUE, finite(minimumScale, startScale)));
  return Math.max(floor, Math.min(MAX_SCALE, requested));
}

export function zoomAt(view, requestedScale, anchor, minimumScale = view.scale) {
  const current = normalizeView(view);
  const scale = interactionScale(current.scale, requestedScale, minimumScale);
  const anchorX = finite(anchor?.x);
  const anchorY = finite(anchor?.y);
  const diagramX = (anchorX - current.x) / current.scale;
  const diagramY = (anchorY - current.y) / current.scale;
  return {
    x: anchorX - diagramX * scale,
    y: anchorY - diagramY * scale,
    scale,
  };
}

export function screenDeltaToSvg(view, dx, dy) {
  const scale = normalizeView(view).scale;
  return { x: finite(dx) / scale, y: finite(dy) / scale };
}

export function fitView(contentWidth, contentHeight, viewportWidth, viewportHeight, padding = 28) {
  const width = Math.max(1, finite(contentWidth, 1));
  const height = Math.max(1, finite(contentHeight, 1));
  const viewportWidthValue = finite(viewportWidth, 1);
  const viewportHeightValue = finite(viewportHeight, 1);
  const uniformPadding = Math.max(0, finite(padding));
  const insetPadding = (
    padding && typeof padding === "object" && !Array.isArray(padding)
      ? {
          top: Math.max(0, finite(padding.top)),
          right: Math.max(0, finite(padding.right)),
          bottom: Math.max(0, finite(padding.bottom)),
          left: Math.max(0, finite(padding.left)),
        }
      : {
          top: uniformPadding,
          right: uniformPadding,
          bottom: uniformPadding,
          left: uniformPadding,
        }
  );
  const availableWidth = Math.max(
    1,
    viewportWidthValue - insetPadding.left - insetPadding.right,
  );
  const availableHeight = Math.max(
    1,
    viewportHeightValue - insetPadding.top - insetPadding.bottom,
  );
  const scale = Math.min(MAX_SCALE, availableWidth / width, availableHeight / height);
  return {
    x: insetPadding.left + (availableWidth - width * scale) / 2,
    y: insetPadding.top + (availableHeight - height * scale) / 2,
    scale,
  };
}

export function sanitizeOverrides(value) {
  const output = Object.create(null);
  if (!value || typeof value !== "object" || Array.isArray(value)) return output;
  for (const [sourceId, offset] of Object.entries(value).slice(0, 10000)) {
    if (!sourceId || !offset || typeof offset !== "object" || Array.isArray(offset)) continue;
    const x = Number(offset.x);
    const y = Number(offset.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    output[sourceId] = { x: boundedOffset(x), y: boundedOffset(y) };
  }
  return output;
}

export function nodeOffset(overrides, sourceId) {
  const offset = overrides?.[sourceId];
  if (!offset || typeof offset !== "object" || Array.isArray(offset)) return { x: 0, y: 0 };
  const x = Number(offset.x);
  const y = Number(offset.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return { x: 0, y: 0 };
  return { x: boundedOffset(x), y: boundedOffset(y) };
}

export function updateNodeOffset(overrides, sourceId, x, y) {
  const working = overrides && typeof overrides === "object" && !Array.isArray(overrides)
    ? overrides
    : Object.create(null);
  if (!sourceId) return working;
  working[sourceId] = { x: boundedOffset(x), y: boundedOffset(y) };
  return working;
}

function normalizedBounds(value) {
  const x = finite(value?.x);
  const y = finite(value?.y);
  const width = Math.max(1, finite(value?.width, 1));
  const height = Math.max(1, finite(value?.height, 1));
  return {
    x,
    y,
    width,
    height,
    left: x,
    right: x + width,
    top: y,
    bottom: y + height,
    cx: x + width / 2,
    cy: y + height / 2,
  };
}

function sideAnchor(bounds, side, toward) {
  if (side === "left") return { x: bounds.left, y: bounds.cy };
  if (side === "right") return { x: bounds.right, y: bounds.cy };
  if (side === "top") return { x: bounds.cx, y: bounds.top };
  if (side === "bottom") return { x: bounds.cx, y: bounds.bottom };
  const dx = toward.cx - bounds.cx;
  const dy = toward.cy - bounds.cy;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { x: bounds.right, y: bounds.cy }
      : { x: bounds.left, y: bounds.cy };
  }
  return dy >= 0
    ? { x: bounds.cx, y: bounds.bottom }
    : { x: bounds.cx, y: bounds.top };
}

function canvasAnchor(bounds, side, toward) {
  const chosen = side || (() => {
    const dx = toward.cx - bounds.cx;
    const dy = toward.cy - bounds.cy;
    if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "right" : "left";
    return dy >= 0 ? "bottom" : "top";
  })();
  if (chosen === "left") return { x: bounds.left, y: bounds.cy, vx: -1, vy: 0 };
  if (chosen === "right") return { x: bounds.right, y: bounds.cy, vx: 1, vy: 0 };
  if (chosen === "top") return { x: bounds.cx, y: bounds.top, vx: 0, vy: -1 };
  return { x: bounds.cx, y: bounds.bottom, vx: 0, vy: 1 };
}

function anchorPair(source, target) {
  const dx = target.cx - source.cx;
  const dy = target.cy - source.cy;
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? [{ x: source.right, y: source.cy }, { x: target.left, y: target.cy }, "horizontal"]
      : [{ x: source.left, y: source.cy }, { x: target.right, y: target.cy }, "horizontal"];
  }
  return dy >= 0
    ? [{ x: source.cx, y: source.bottom }, { x: target.cx, y: target.top }, "vertical"]
    : [{ x: source.cx, y: source.top }, { x: target.cx, y: target.bottom }, "vertical"];
}

function cubicPoint(start, c1, c2, end) {
  return {
    x: (start.x + 3 * c1.x + 3 * c2.x + end.x) / 8,
    y: (start.y + 3 * c1.y + 3 * c2.y + end.y) / 8,
  };
}

export function liveEdgeGeometry(sourceBounds, targetBounds, options = {}) {
  const source = normalizedBounds(sourceBounds);
  const target = normalizedBounds(targetBounds);
  const route = typeof options.route === "string" ? options.route : "standard";
  const kind = typeof options.kind === "string" ? options.kind : "flow";
  const lane = finite(options.lane);
  const canvasWidth = Math.max(1, finite(options.canvasWidth, 1));
  const canvasHeight = Math.max(1, finite(options.canvasHeight, 1));
  const selfLoop = Boolean(options.selfLoop);

  if (selfLoop && route === "canvas-self-loop") {
    const reach = 66 + Math.abs(lane);
    const fromSide = options.fromSide || null;
    const toSide = options.toSide || null;
    if (fromSide || toSide) {
      const loopAnchor = (side, fraction) => {
        const chosen = side || "right";
        if (chosen === "left") {
          return { x: source.left, y: source.y + source.height * fraction, vx: -1, vy: 0 };
        }
        if (chosen === "right") {
          return { x: source.right, y: source.y + source.height * fraction, vx: 1, vy: 0 };
        }
        if (chosen === "top") {
          return { x: source.x + source.width * fraction, y: source.top, vx: 0, vy: -1 };
        }
        return { x: source.x + source.width * fraction, y: source.bottom, vx: 0, vy: 1 };
      };
      const start = loopAnchor(fromSide, 0.35);
      const end = loopAnchor(toSide, 0.72);
      let c1 = {
        x: start.x + start.vx * reach,
        y: start.y + start.vy * reach,
      };
      let c2 = {
        x: end.x + end.vx * reach,
        y: end.y + end.vy * reach,
      };
      const sidePair = new Set([fromSide || "right", toSide || "right"]);
      if (sidePair.has("top") && sidePair.has("bottom")) {
        const outsideBias = reach + source.width / 2;
        c1 = { x: c1.x + outsideBias, y: c1.y };
        c2 = { x: c2.x + outsideBias, y: c2.y };
      } else if (sidePair.has("left") && sidePair.has("right")) {
        const outsideBias = reach + source.height / 2;
        c1 = { x: c1.x, y: c1.y - outsideBias };
        c2 = { x: c2.x, y: c2.y - outsideBias };
      }
      const label = cubicPoint(start, c1, c2, end);
      return {
        path: "M " + start.x.toFixed(1) + " " + start.y.toFixed(1)
          + " C " + c1.x.toFixed(1) + " " + c1.y.toFixed(1)
          + ", " + c2.x.toFixed(1) + " " + c2.y.toFixed(1)
          + ", " + end.x.toFixed(1) + " " + end.y.toFixed(1),
        labelX: label.x + 9 * (start.vx + end.vx),
        labelY: label.y + 9 * (start.vy + end.vy),
      };
    }
    const start = { x: source.right, y: source.y + source.height * 0.35 };
    const end = { x: source.right, y: source.y + source.height * 0.72 };
    const c1 = { x: start.x + reach, y: source.y - 18 };
    const c2 = { x: end.x + reach, y: source.bottom + 18 };
    const label = cubicPoint(start, c1, c2, end);
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: label.x + 18,
      labelY: label.y,
    };
  }

  if (selfLoop) {
    const reach = 66 + Math.min(120, Math.abs(lane));
    const start = { x: source.right, y: source.y + source.height * 0.35 };
    const end = { x: source.right, y: source.y + source.height * 0.72 };
    const controlX = Math.min(canvasWidth - 8, source.right + reach);
    const c1 = { x: controlX, y: source.y - 18 - Math.abs(lane) * 0.12 };
    const c2 = { x: controlX, y: source.bottom + 18 + Math.abs(lane) * 0.12 };
    const label = cubicPoint(start, c1, c2, end);
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: Math.min(canvasWidth - 12, label.x + 18),
      labelY: label.y,
    };
  }

  if (kind === "feedback" || route === "feedback-return") {
    const start = { x: source.cx, y: source.bottom };
    const end = { x: target.cx, y: target.bottom };
    const requestedBaseline = Math.max(source.bottom, target.bottom) + 34 + Math.abs(lane);
    const baseline = Math.max(
      Math.max(source.bottom, target.bottom) + 12,
      Math.min(canvasHeight - 12, requestedBaseline),
    );
    const bend = 24;
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${start.x.toFixed(1)} ${(start.y + bend).toFixed(1)}, ${start.x.toFixed(1)} ${baseline.toFixed(1)}, ${start.x.toFixed(1)} ${baseline.toFixed(1)} L ${end.x.toFixed(1)} ${baseline.toFixed(1)} C ${end.x.toFixed(1)} ${baseline.toFixed(1)}, ${end.x.toFixed(1)} ${(end.y + bend).toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: (start.x + end.x) / 2,
      labelY: baseline,
    };
  }

  if (route === "process-row-gutter") {
    const start = { x: source.cx, y: source.top };
    const end = { x: target.cx, y: target.top };
    const railY = Math.max(12, Math.min(source.top, target.top) - 30 - Math.abs(lane));
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${start.x.toFixed(1)} ${railY.toFixed(1)}, ${start.x.toFixed(1)} ${railY.toFixed(1)}, ${start.x.toFixed(1)} ${railY.toFixed(1)} L ${end.x.toFixed(1)} ${railY.toFixed(1)} C ${end.x.toFixed(1)} ${railY.toFixed(1)}, ${end.x.toFixed(1)} ${railY.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: (start.x + end.x) / 2,
      labelY: railY,
    };
  }

  if (route === "vertical") {
    const down = target.cy >= source.cy;
    const start = { x: source.cx, y: down ? source.bottom : source.top };
    const end = { x: target.cx, y: down ? target.top : target.bottom };
    const midY = (start.y + end.y) / 2;
    const laneX = (start.x + end.x) / 2 + lane;
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${start.x.toFixed(1)} ${midY.toFixed(1)}, ${laneX.toFixed(1)} ${midY.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: laneX + 12,
      labelY: midY,
    };
  }

  if (route === "narrative-parallel") {
    const leftToRight = target.cx >= source.cx;
    const start = { x: leftToRight ? source.right : source.left, y: source.cy };
    const end = { x: leftToRight ? target.left : target.right, y: target.cy };
    const lift = 42 + Math.abs(lane);
    const railY = Math.max(12, Math.min(source.top, target.top) - lift);
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${start.x.toFixed(1)} ${railY.toFixed(1)}, ${end.x.toFixed(1)} ${railY.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: (start.x + end.x) / 2,
      labelY: railY,
    };
  }

  if (route === "canvas-cubic") {
    const start = canvasAnchor(source, options.fromSide, target);
    const end = canvasAnchor(target, options.toSide, source);
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const distance = Math.max(42, Math.min(160, Math.hypot(dx, dy) * 0.35));
    let c1 = { x: start.x + start.vx * distance, y: start.y + start.vy * distance };
    let c2 = { x: end.x + end.vx * distance, y: end.y + end.vy * distance };
    if (lane) {
      const magnitude = Math.max(1, Math.hypot(dx, dy));
      const nx = -dy / magnitude;
      const ny = dx / magnitude;
      c1 = { x: c1.x + nx * lane, y: c1.y + ny * lane };
      c2 = { x: c2.x + nx * lane, y: c2.y + ny * lane };
    }
    const label = cubicPoint(start, c1, c2, end);
    return {
      path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      labelX: label.x,
      labelY: label.y,
    };
  }

  const explicitSides = options.fromSide || options.toSide;
  const start = explicitSides
    ? sideAnchor(source, options.fromSide, target)
    : anchorPair(source, target)[0];
  const end = explicitSides
    ? sideAnchor(target, options.toSide, source)
    : anchorPair(source, target)[1];
  const axis = Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)
    ? "horizontal"
    : "vertical";
  let c1;
  let c2;
  if (axis === "horizontal") {
    const midX = (start.x + end.x) / 2;
    c1 = { x: midX, y: start.y + lane };
    c2 = { x: midX, y: end.y + lane };
  } else {
    const midY = (start.y + end.y) / 2;
    c1 = { x: start.x + lane, y: midY };
    c2 = { x: end.x + lane, y: midY };
  }
  const label = cubicPoint(start, c1, c2, end);
  return {
    path: `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)}, ${c2.x.toFixed(1)} ${c2.y.toFixed(1)}, ${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
    labelX: label.x,
    labelY: label.y,
  };
}
"""

APP_JS = r"""import { smartEdgeGeometry } from "./smart-router.js";
import { createHybridPreview, hybridPreviewSupported } from "./hybrid-preview.js";
import {
  MAX_SCALE,
  MIN_SCALE,
  clampScale,
  fitView,
  interactionScale,
  liveEdgeGeometry,
  nodeOffset,
  panBy,
  sanitizeOverrides,
  screenDeltaToSvg,
  updateNodeOffset,
  zoomAt,
} from "./interaction.js";

const viewport = document.querySelector("#nativeViewport");
const canvas = document.querySelector("#nativeCanvas");
const svg = document.querySelector("#nativeDiagram");
const status = document.querySelector("#status");
const selectionStatus = document.querySelector("#selectionStatus");
const zoomValue = document.querySelector("#zoomValue");
const zoomIn = document.querySelector("#zoomIn");
const zoomOut = document.querySelector("#zoomOut");
const fitButton = document.querySelector("#fitView");
const resetLayout = document.querySelector("#resetLayout");
const observationButton = document.querySelector("#observationMode");
const smartRoutingButton = document.querySelector("#smartRouting");
const hybridButton = document.querySelector("#hybridPreview");
const edgePorts = document.querySelector("#edgePorts");
const edgeFromPort = document.querySelector("#edgeFromPort");
const edgeToPort = document.querySelector("#edgeToPort");
const edgeFromEnd = document.querySelector("#edgeFromEnd");
const edgeToEnd = document.querySelector("#edgeToEnd");
const edgeKind = document.querySelector("#edgeKind");
const editControls = document.querySelector(".edit-controls");
const addNodeButton = document.querySelector("#addNode");
const addEdgeButton = document.querySelector("#addEdge");
const editTextButton = document.querySelector("#editText");
const reattachSourceButton = document.querySelector("#reattachSource");
const reattachTargetButton = document.querySelector("#reattachTarget");
const deleteSelectionButton = document.querySelector("#deleteSelection");
const interactionHint = document.querySelector("#interactionHint");
const authorityHint = document.querySelector("#authorityHint");
const textDialog = document.querySelector("#textDialog");
const textInput = document.querySelector("#textInput");
const saveTextButton = document.querySelector("#saveText");
const limitsElement = document.querySelector("#nativeLimits");
const modelElement = document.querySelector("#nativeModel");

if (!(viewport instanceof HTMLElement) || !(canvas instanceof HTMLElement) || !(svg instanceof SVGSVGElement)) {
  throw new Error("Native viewer DOM contract is incomplete");
}
if (!(limitsElement instanceof HTMLScriptElement) || !(modelElement instanceof HTMLScriptElement)) {
  throw new Error("Native viewer model contract is incomplete");
}
let editingLimits;
let sourceModel;
try {
  editingLimits = JSON.parse(limitsElement.textContent || "{}");
  sourceModel = JSON.parse(modelElement.textContent || "{}");
} catch (_) {
  throw new Error("Native viewer embedded model is invalid");
}
for (const key of ["max_abs_coordinate", "max_edges", "max_groups", "max_nodes", "max_routing_pairs"]) {
  if (!Number.isInteger(editingLimits?.[key]) || editingLimits[key] < 1) {
    throw new Error("Native viewer product-limit contract is incomplete");
  }
}
if (!Array.isArray(sourceModel?.nodes) || !Array.isArray(sourceModel?.edges)) {
  throw new Error("Native viewer embedded model is incomplete");
}
const documentMode = sourceModel.schema_version === "schauwerk-native-editing-document.v1";
const embeddedNativeViewer = window.parent !== window;
const documentEditorHosted = documentMode && embeddedNativeViewer;
document.body.classList.toggle("embedded-native-viewer", embeddedNativeViewer);
document.body.classList.toggle("document-editor-hosted", documentEditorHosted);

const inputDigest = svg.dataset.inputDigest || "";
if (!/^[0-9a-f]{64}$/.test(inputDigest)) {
  throw new Error("Native viewer input digest is missing or invalid");
}
const STORAGE_KEY = `schauwerk.native-viewer.layout.v1.${inputDigest}`;
const nodes = new Map();
const baseTransforms = new Map();
const edges = new Map();
const maxLaneByPair = new Map();
const incidentEdges = new Map();
const lastRouteObstacles = new Map();
let handleLayer = null;
let connectionPreview = null;
let view = { x: 0, y: 0, scale: 1 };
let fitScaleFloor = MIN_SCALE;
let autoFitActive = true;
let overrides = documentMode ? Object.create(null) : readOverrides();
let selectedId = null;
let selectedEdgeId = null;
let edgeCreateSource = null;
let edgeReattach = null;
let textEditTarget = null;
let gesture = null;
let observationMode = false;
const activePointers = new Map();
// Restore automatic fitting after a motionless pointer sequence, never after a manual view change.
let pointerAutoFitBefore = null;
let pointerChangedView = false;
let pointerMovedNode = false;
let pointerFitPending = false;
let bulkEdgeUpdate = false;
let pendingSmartRouteGeneration = 0;
const DRAG_THRESHOLD_PX = 4;
// Preserve responsive pointer input in dense documents. Certified routes are
// recomputed by the authoritative native renderer after every completed drag.
const MAX_SYNC_SMART_DRAG_NODES = 32;
const MAX_SYNC_SMART_DRAG_EDGES = 24;
const MAX_SYNC_SMART_DRAG_INCIDENT = 8;
const EDGE_HIT_TARGET_SCREEN_PX = 24;
const BOUNDS_EPSILON = 0.01;
const VIEWPORT_FIT_PADDING = 48;
const FIT_OVERLAY_CLEARANCE = 8;
const EMBEDDED_VIEWPORT_FIT_PADDING = Object.freeze({
  top: 60,
  right: VIEWPORT_FIT_PADDING,
  bottom: 104,
  left: VIEWPORT_FIT_PADDING,
});

function setStatus(message) { status.textContent = message; }

function viewportFitPadding(minimumPadding) {
  const barRect = document.querySelector(".viewer-bar")?.getBoundingClientRect();
  const footRect = document.querySelector(".viewer-foot")?.getBoundingClientRect();
  const top = Math.max(
    minimumPadding.top,
    Math.ceil(barRect?.bottom || 0) + FIT_OVERLAY_CLEARANCE,
  );
  const bottom = Math.max(
    minimumPadding.bottom,
    Math.ceil(viewport.clientHeight - (footRect?.top ?? viewport.clientHeight))
      + FIT_OVERLAY_CLEARANCE,
  );
  // Measure the same safe-area-shifted bar used by the viewer controls.
  // A fixed 48px margin can otherwise fit nodes under a landscape notch.
  const left = Math.max(
    minimumPadding.left,
    Math.ceil(barRect?.left || 0) + FIT_OVERLAY_CLEARANCE,
  );
  const right = Math.max(
    minimumPadding.right,
    Math.ceil(viewport.clientWidth - (barRect?.right ?? viewport.clientWidth))
      + FIT_OVERLAY_CLEARANCE,
  );
  return { top, right, bottom, left };
}

function standaloneViewportFitPadding() {
  return viewportFitPadding({
    top: VIEWPORT_FIT_PADDING,
    right: VIEWPORT_FIT_PADDING,
    bottom: VIEWPORT_FIT_PADDING,
    left: VIEWPORT_FIT_PADDING,
  });
}

function syncEmbeddedHostOverlays() {
  if (!embeddedNativeViewer) return;
  try {
    const frame = window.frameElement?.getBoundingClientRect();
    const host = window.parent.document;
    if (!frame || !host.body.classList.contains("workspace-active")) return;
    const bar = host.querySelector(".workspace-bar")?.getBoundingClientRect();
    const status = host.querySelector(".topline")?.getBoundingClientRect();
    const retry = host.querySelector("#nativeRetryButton");
    const retryRect = retry && !retry.hidden ? retry.getBoundingClientRect() : null;
    if (!bar || !status || !bar.width || !status.width) return;
    const overlayTop = Math.min(
      bar.top,
      status.top,
      retryRect?.height > 0 ? retryRect.top : Infinity,
    );
    const margins = {
      "--host-safe-left": Math.ceil(Math.max(0, status.left - frame.left)),
      "--host-safe-right": Math.ceil(Math.max(0, frame.right - bar.right)),
      // Native selection must remain above both host status and action bar.
      "--host-footer-bottom": Math.ceil(Math.max(0, frame.bottom - overlayTop))
        + FIT_OVERLAY_CLEARANCE,
    };
    for (const [name, px] of Object.entries(margins)) {
      const value = px + "px";
      if (document.documentElement.style.getPropertyValue(name) !== value) {
        document.documentElement.style.setProperty(name, value);
      }
    }
  } catch (_) {
    // Cross-origin embedding cannot read the hosting overlays.
  }
}

function embeddedViewportFitPadding() {
  // The host moves its status and workspace bar for bottom safe-area insets.
  // Read actual overlay bounds instead of adding a fixed gutter on all devices.
  let bottom = EMBEDDED_VIEWPORT_FIT_PADDING.bottom;
  try {
    const frameRect = window.frameElement?.getBoundingClientRect();
    const host = window.parent.document;
    if (frameRect && host.body.classList.contains("workspace-active")) {
      for (const selector of [".topline", ".workspace-bar", "#nativeRetryButton"]) {
        const overlay = host.querySelector(selector);
        const rect = overlay?.getBoundingClientRect();
        if (rect && rect.width > 0 && rect.height > 0) {
          bottom = Math.max(
            bottom,
            Math.ceil(frameRect.bottom - rect.top) + FIT_OVERLAY_CLEARANCE,
          );
        }
      }
    }
  } catch (_) {
    // A cross-origin embed has no access to Schauwerk host overlay geometry.
  }
  return viewportFitPadding({ ...EMBEDDED_VIEWPORT_FIT_PADDING, bottom });
}

function readOverrides() {
  try {
    return sanitizeOverrides(JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"));
  } catch (_) {
    return {};
  }
}

function persistOverrides() {
  if (documentMode) return true;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeOverrides(overrides)));
    return true;
  } catch (_) {
    setStatus("Position geändert · lokales Speichern nicht möglich");
    return false;
  }
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function uniqueId(prefix, values) {
  const existing = new Set(values.map((item) => String(item.id || "")));
  let index = 1;
  while (existing.has(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}

function documentMutationWithinProductLimits(document, { addNodes = 0, addEdges = 0 } = {}) {
  const nodeCount = document.nodes.length + addNodes;
  const edgeCount = document.edges.length + addEdges;
  if (nodeCount > editingLimits.max_nodes) {
    setStatus(`Produktgrenze erreicht · maximal ${editingLimits.max_nodes} Knoten`);
    return false;
  }
  if (
    edgeCount > editingLimits.max_edges ||
    edgeCount * edgeCount > editingLimits.max_routing_pairs
  ) {
    setStatus(
      `Produktgrenze erreicht · maximal ${editingLimits.max_edges} Kanten ` +
      `und ${editingLimits.max_routing_pairs} Routing-Paare`
    );
    return false;
  }
  return true;
}

function boundedDocumentOffset(sourceId, x, y) {
  if (!documentMode) return { x, y };
  const sourceNode = sourceModel.nodes.find(
    (item) => String(item.id) === String(sourceId),
  );
  if (!sourceNode) return { x: 0, y: 0 };
  const limit = editingLimits.max_abs_coordinate;
  const baseX = Number(sourceNode.x);
  const baseY = Number(sourceNode.y);
  return {
    x: Math.max(-limit - baseX, Math.min(limit - baseX, x)),
    y: Math.max(-limit - baseY, Math.min(limit - baseY, y)),
  };
}

function setNodeOffset(sourceId, x, y) {
  const bounded = boundedDocumentOffset(sourceId, x, y);
  overrides = updateNodeOffset(overrides, sourceId, bounded.x, bounded.y);
}

function boundedDocumentState(document) {
  if (!document || document.schema_version !== "schauwerk-native-editing-document.v1") {
    return document;
  }
  const bounded = cloneJson(document);
  const limit = editingLimits.max_abs_coordinate;
  for (const node of bounded.nodes) {
    node.x = Math.max(-limit, Math.min(limit, Math.round(Number(node.x))));
    node.y = Math.max(-limit, Math.min(limit, Math.round(Number(node.y))));
  }
  return bounded;
}

function documentSnapshot() {
  if (!documentMode) return null;
  const snapshot = cloneJson(sourceModel);
  for (const node of snapshot.nodes) {
    const offset = nodeOffset(overrides, String(node.id));
    node.x = Math.round(Number(node.x) + offset.x);
    node.y = Math.round(Number(node.y) + offset.y);
  }
  return boundedDocumentState(snapshot);
}

function canvasFromDocument(document) {
  if (!document || document.schema_version !== "schauwerk-native-editing-document.v1") return null;
  const source = document.source || {};
  const canvas = cloneJson(source);
  const outputNodes = document.nodes.map((item) => {
    const node = cloneJson(item.source || {});
    node.id = String(item.id);
    node.type = String(item.type || node.type || "text");
    node.x = Math.round(Number(item.x));
    node.y = Math.round(Number(item.y));
    node.width = Math.max(1, Math.round(Number(item.width)));
    node.height = Math.max(1, Math.round(Number(item.height)));
    const label = String(item.label ?? "");
    if (node.type === "text") node.text = label;
    else if (node.type === "group") {
      if (label || Object.prototype.hasOwnProperty.call(node, "label")) node.label = label;
      else delete node.label;
    } else if (node.type === "file") node.file = label;
    else if (node.type === "link") node.url = label;
    return node;
  });
  const outputEdges = document.edges.map((item) => {
    const edge = cloneJson(item.source || {});
    edge.id = String(item.id);
    edge.fromNode = String(item.from);
    edge.toNode = String(item.to);
    const label = String(item.label ?? "");
    if (label || Object.prototype.hasOwnProperty.call(edge, "label")) edge.label = label;
    else delete edge.label;
    for (const [internal, external, defaultValue] of [
      ["from_side", "fromSide", null],
      ["to_side", "toSide", null],
      ["from_end", "fromEnd", "none"],
      ["to_end", "toEnd", "arrow"],
    ]) {
      const value = item[internal];
      const hadExternal = Object.prototype.hasOwnProperty.call(edge, external);
      if (value === null || value === undefined) delete edge[external];
      else if (value === defaultValue && !hadExternal) delete edge[external];
      else edge[external] = value;
    }
    return edge;
  });
  if (outputNodes.length || Object.prototype.hasOwnProperty.call(source, "nodes")) {
    canvas.nodes = outputNodes;
  } else {
    delete canvas.nodes;
  }
  if (outputEdges.length || Object.prototype.hasOwnProperty.call(source, "edges")) {
    canvas.edges = outputEdges;
  } else {
    delete canvas.edges;
  }
  return canvas;
}

function publishDocumentState(eventName = "native-document-change", document = documentSnapshot(), { startup = false } = {}) {
  if (observationMode || !documentEditorHosted || !document) return;
  const boundedDocument = boundedDocumentState(document);
  const canvasState = canvasFromDocument(boundedDocument);
  if (!canvasState) return;
  window.parent.postMessage(
    { event: eventName, document: boundedDocument, canvas: canvasState, ...(startup ? { startup: true } : {}) },
    window.location.origin,
  );
}

function rebuildDocument(document) {
  if (observationMode || !documentEditorHosted || !document) return;
  sourceModel = boundedDocumentState(document);
  overrides = Object.create(null);
  publishDocumentState("native-document-rebuild", sourceModel);
}

function applyView() {
  canvas.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  // Canvas zoom is a CSS transform on the wrapping DIV, not SVG viewBox
  // scaling. An SVG non-scaling stroke does not compensate this zoom.
  // Keep the pointer target 24 actual CSS pixels wide at every zoom level.
  const hitWidth = EDGE_HIT_TARGET_SCREEN_PX / view.scale;
  for (const edgeState of edges.values()) {
    edgeState.hitPath.setAttribute("stroke-width", hitWidth.toFixed(3));
  }
  zoomValue.value = `${Math.round(view.scale * 100)} %`;
  zoomValue.textContent = zoomValue.value;
  if (handleLayer && gesture?.kind !== "connection") refreshConnectionHandles();
}

function applyNodeTransform(sourceId) {
  const node = nodes.get(sourceId);
  if (!node) return;
  const offset = nodeOffset(overrides, sourceId);
  const base = baseTransforms.get(sourceId) || "";
  if (offset.x === 0 && offset.y === 0) {
    if (base) node.setAttribute("transform", base);
    else node.removeAttribute("transform");
    if (!bulkEdgeUpdate) updateIncidentEdges(sourceId);
    return;
  }
  const translated = `translate(${offset.x} ${offset.y})`;
  node.setAttribute("transform", base ? `${translated} ${base}` : translated);
  if (!bulkEdgeUpdate) updateIncidentEdges(sourceId);
}

function applyAllNodeTransforms() {
  // Reset or a new source render supersedes every prior deferred task.
  ++pendingSmartRouteGeneration;
  bulkEdgeUpdate = true;
  try {
    for (const sourceId of nodes.keys()) applyNodeTransform(sourceId);
  } finally {
    bulkEdgeUpdate = false;
  }
  const unchangedSmartCanvas = documentMode && routingMode() === "smart" &&
    [...nodes.keys()].every(sourceId => {
      const offset = nodeOffset(overrides, sourceId);
      return offset.x === 0 && offset.y === 0;
    });
  if (unchangedSmartCanvas) {
    // On initial load (and Reset), use the *already certified* source SVG.
    // Recomputing every route here would freeze dense viewers at startup.
    for (const edge of edges.values()) {
      edge.path.setAttribute("d", edge.basePath);
      edge.hitPath.setAttribute("d", edge.basePath);
      edge.naturalLabelX = edge.baseLabelX;
      edge.naturalLabelY = edge.baseLabelY;
      edge.routeBounds = null;
      resetEdgeLabel(edge);
      placeLiveEdgeConflict(edge, edge.route === "canvas-smart-conflict");
    }
  } else {
    for (const edgeId of edges.keys()) updateEdgeGeometry(edgeId);
  }
  lastRouteObstacles.clear();
  if (documentMode && routingMode() === "smart") {
    for (const node of nodeModelsAtLiveCoordinates()) {
      lastRouteObstacles.set(node.id, [
        node.x - 24, node.y - 24,
        node.x + node.width + 24, node.y + node.height + 24,
      ]);
    }
  }
  relocateLiveEdgeLabels();
}

function nodeBoundsInSvg(node) {
  const geometryElement = (
    documentMode &&
    node.dataset.sourceKind === "node"
      ? Array.from(node.children).find((child) => child instanceof SVGRectElement)
      : null
  );
  const box = (geometryElement || node).getBBox();
  const nodeMatrix = node.getCTM();
  const rootMatrix = svg.getCTM();
  if (!nodeMatrix || !rootMatrix) return null;
  let matrix;
  try {
    matrix = rootMatrix.inverse().multiply(nodeMatrix);
  } catch (_) {
    return null;
  }
  const corners = [
    [box.x, box.y],
    [box.x + box.width, box.y],
    [box.x, box.y + box.height],
    [box.x + box.width, box.y + box.height],
  ].map(([x, y]) => {
    const point = svg.createSVGPoint();
    point.x = x;
    point.y = y;
    return point.matrixTransform(matrix);
  });
  return {
    minX: Math.min(...corners.map((point) => point.x)),
    maxX: Math.max(...corners.map((point) => point.x)),
    minY: Math.min(...corners.map((point) => point.y)),
    maxY: Math.max(...corners.map((point) => point.y)),
  };
}

function mergeSvgBounds(left, right) {
  if (!left) return right;
  if (!right) return left;
  return {
    minX: Math.min(left.minX, right.minX),
    maxX: Math.max(left.maxX, right.maxX),
    minY: Math.min(left.minY, right.minY),
    maxY: Math.max(left.maxY, right.maxY),
  };
}

function incidentEdgeBoundsInSvg(sourceId) {
  let combined = null;
  for (const edgeId of incidentEdges.get(sourceId) || []) {
    const edgeState = edges.get(edgeId);
    if (!edgeState) continue;
    const pathBounds = nodeBoundsInSvg(edgeState.path);
    const labelBounds = edgeState.labelRect
      ? nodeBoundsInSvg(edgeState.labelRect)
      : null;
    combined = mergeSvgBounds(combined, pathBounds);
    combined = mergeSvgBounds(combined, labelBounds);
  }
  return combined;
}

function liveBounds(sourceId) {
  const node = nodes.get(sourceId);
  const bounds = node ? nodeBoundsInSvg(node) : null;
  if (!bounds) return null;
  return {
    x: bounds.minX,
    y: bounds.minY,
    width: bounds.maxX - bounds.minX,
    height: bounds.maxY - bounds.minY,
  };
}

function addIncidentEdge(sourceId, edgeId) {
  if (!incidentEdges.has(sourceId)) incidentEdges.set(sourceId, new Set());
  incidentEdges.get(sourceId).add(edgeId);
}

function placeLiveLabel(edgeState, x, y) {
  const transform = "translate(" +
    (x - edgeState.baseLabelX) + " " + (y - edgeState.baseLabelY) + ")";
  for (const element of edgeState.labelElements) element.setAttribute("transform", transform);
  edgeState.clipRect?.setAttribute("transform", transform);
}
function resetEdgeLabel(edgeState) {
  edgeState.naturalLabelX = edgeState.baseLabelX;
  edgeState.naturalLabelY = edgeState.baseLabelY;
  for (const element of edgeState.labelElements) element.removeAttribute("transform");
  edgeState.clipRect?.removeAttribute("transform");
}
function nodeModelsAtLiveCoordinates() {
  return sourceModel.nodes.map(node => {
    const delta = nodeOffset(overrides, String(node.id));
    return {
      id: String(node.id), type: String(node.type),
      x: Math.round(Number(node.x) + delta.x),
      y: Math.round(Number(node.y) + delta.y),
      width: Number(node.width), height: Number(node.height),
    };
  });
}
function placeLiveEdgeConflict(edgeState, conflict) {
  edgeState.element.removeAttribute("data-routing-pending");
  if (conflict) {
    edgeState.element.dataset.routingConflict = "true";
    edgeState.path.setAttribute("stroke", "#c2410c");
    edgeState.path.setAttribute("stroke-dasharray", "6 4");
  } else {
    edgeState.element.removeAttribute("data-routing-conflict");
    edgeState.path.setAttribute("stroke", edgeState.originalStroke);
    if (edgeState.originalDash) {
      edgeState.path.setAttribute("stroke-dasharray", edgeState.originalDash);
    } else edgeState.path.removeAttribute("stroke-dasharray");
  }
}
function relocateLiveEdgeLabels() {
  if (!documentMode) return;
  const padding = 8;
  const blockers = nodeModelsAtLiveCoordinates()
    .filter(node => node.type !== "group")
    .map(node => [node.x, node.y, node.x + node.width, node.y + node.height]);
  const reserved = [];
  for (const edgeState of edges.values()) {
    const box = edgeState.labelRect;
    const halfW = Number(box?.getAttribute("width") || 0) / 2;
    const halfH = Number(box?.getAttribute("height") || 0) / 2;
    if (!halfW || !halfH) continue;
    const x0 = edgeState.naturalLabelX ?? edgeState.baseLabelX;
    const y0 = edgeState.naturalLabelY ?? edgeState.baseLabelY;
    const occupied = [...blockers, ...reserved];
    const intersects = (x, y) => occupied.some(b =>
      x - halfW < b[2] + padding && x + halfW > b[0] - padding &&
      y - halfH < b[3] + padding && y + halfH > b[1] - padding
    );
    let x = x0, y = y0;
    if (intersects(x, y)) {
      const candidates = [];
      for (const [left, top, right, bottom] of occupied) {
        candidates.push([x0, top - padding - halfH], [x0, bottom + padding + halfH],
                        [left - padding - halfW, y0], [right + padding + halfW, y0]);
      }
      for (const step of [16,32,48,64,96,128,192,256,384,512]) {
        candidates.push([x0,y0-step], [x0,y0+step], [x0-step,y0], [x0+step,y0]);
      }
      if (occupied.length) {
        candidates.push(
          [x0, Math.min(...occupied.map(b => b[1])) - padding - halfH],
          [x0, Math.max(...occupied.map(b => b[3])) + padding + halfH],
          [Math.min(...occupied.map(b => b[0])) - padding - halfW, y0],
          [Math.max(...occupied.map(b => b[2])) + padding + halfW, y0]
        );
      }
      candidates.sort((a, b) => {
        const da = (a[0]-x0)**2 + (a[1]-y0)**2;
        const db = (b[0]-x0)**2 + (b[1]-y0)**2;
        return da - db || Number(a[0] !== x0) - Number(b[0] !== x0);
      });
      for (const candidate of candidates) {
        if (!intersects(candidate[0], candidate[1])) {
          x = candidate[0]; y = candidate[1]; break;
        }
      }
    }
    if (intersects(x, y)) edgeState.element.dataset.labelConflict = "true";
    else edgeState.element.removeAttribute("data-label-conflict");
    placeLiveLabel(edgeState, x, y);
    reserved.push([x - halfW, y - halfH, x + halfW, y + halfH]);
  }
}

function updateEdgeGeometry(edgeId) {
  const edgeState = edges.get(edgeId);
  if (!edgeState) return;
  const fromOffset = nodeOffset(overrides, edgeState.from);
  const toOffset = nodeOffset(overrides, edgeState.to);
  if (documentMode && routingMode() === "smart" && edgeState.from !== edgeState.to) {
    const allNodes = nodeModelsAtLiveCoordinates();
    const source = allNodes.find(node => node.id === edgeState.from);
    const target = allNodes.find(node => node.id === edgeState.to);
    if (!source || !target) return;
    const pairKey = JSON.stringify([edgeState.from, edgeState.to].sort());
    const result = smartEdgeGeometry(source, target, allNodes, {
      lane: edgeState.lane, fromSide: edgeState.fromSide, toSide: edgeState.toSide,
      maxLane: maxLaneByPair.get(pairKey) || 0,
    });
    if (result) {
      edgeState.path.setAttribute("d", result.path);
      edgeState.hitPath.setAttribute("d", result.path);
      edgeState.naturalLabelX = result.labelX;
      edgeState.naturalLabelY = result.labelY;
      const routePoints = result.points;
      edgeState.routeBounds = [
        Math.min(...routePoints.map(point => point[0])) - 24,
        Math.min(...routePoints.map(point => point[1])) - 24,
        Math.max(...routePoints.map(point => point[0])) + 24,
        Math.max(...routePoints.map(point => point[1])) + 24,
      ];
      placeLiveEdgeConflict(edgeState, false);
    } else {
      const box = svg.viewBox.baseVal;
      const fallback = liveEdgeGeometry(source, target, {
        route: "standard", lane: edgeState.lane,
        fromSide: edgeState.fromSide, toSide: edgeState.toSide,
        canvasWidth: box.width || 1, canvasHeight: box.height || 1,
      });
      edgeState.path.setAttribute("d", fallback.path);
      edgeState.hitPath.setAttribute("d", fallback.path);
      edgeState.naturalLabelX = fallback.labelX;
      edgeState.naturalLabelY = fallback.labelY;
      edgeState.routeBounds = null;
      placeLiveEdgeConflict(edgeState, true);
    }
    return;
  }
  if (
    fromOffset.x === 0 && fromOffset.y === 0 &&
    toOffset.x === 0 && toOffset.y === 0
  ) {
    edgeState.path.setAttribute("d", edgeState.basePath);
    edgeState.hitPath.setAttribute("d", edgeState.basePath);
    resetEdgeLabel(edgeState);
    if (edgeState.element.dataset.routingPending === "true") {
      placeLiveEdgeConflict(edgeState, false);
    }
    return;
  }
  const sourceBounds = liveBounds(edgeState.from);
  const targetBounds = liveBounds(edgeState.to);
  if (!sourceBounds || !targetBounds) return;
  const box = svg.viewBox.baseVal;
  const geometry = liveEdgeGeometry(sourceBounds, targetBounds, {
    route: edgeState.route,
    kind: edgeState.kind,
    lane: edgeState.lane,
    canvasWidth: box.width || svg.width.baseVal.value || 1,
    canvasHeight: box.height || svg.height.baseVal.value || 1,
    selfLoop: edgeState.from === edgeState.to,
    fromSide: edgeState.fromSide,
    toSide: edgeState.toSide,
  });
  edgeState.path.setAttribute("d", geometry.path);
  edgeState.hitPath.setAttribute("d", geometry.path);
  edgeState.naturalLabelX = geometry.labelX;
  edgeState.naturalLabelY = geometry.labelY;
  placeLiveLabel(edgeState, geometry.labelX, geometry.labelY);
  if (edgeState.element.dataset.routingPending === "true") {
    placeLiveEdgeConflict(edgeState, false);
  }
}

function finishPendingStandaloneSmartRoutes() {
  const generation = ++pendingSmartRouteGeneration;
  const pending = [...edges].filter(([_id, edge]) =>
    edge.element.dataset.routingPending === "true").map(([id]) => id);
  if (!pending.length) return;
  let index = 0;
  const rerouteNext = () => {
    if (generation !== pendingSmartRouteGeneration) return;
    if (gesture?.kind === "drag") {
      setTimeout(rerouteNext, 16);
      return;
    }
    // At most one visibility-graph search per task. The browser remains
    // responsive between chunks; failed paths retain explicit conflict state.
    updateEdgeGeometry(pending[index++]);
    if (index < pending.length) {
      setTimeout(rerouteNext, 0);
    } else {
      relocateLiveEdgeLabels();
      expandSmartCanvasToFitRoutes();
      setStatus("Intelligente Kantenführung aktualisiert");
    }
  };
  setStatus("Intelligente Kantenführung wird geprüft");
  setTimeout(rerouteNext, 0);
}
function rollbackSmartDragPreview(drag) {
  if (!drag?.previewOriginals) return false;
  // Restoring cached exact paths is bounded and avoids another visibility
  // search during pointercancel, observation-mode switches and pinch takeover.
  for (const [edgeId, original] of drag.previewOriginals) {
    const edge = edges.get(edgeId);
    if (!edge) continue;
    edge.path.setAttribute("d", original.path);
    edge.hitPath.setAttribute("d", original.hitPath);
    for (const [key, value] of [
      ["stroke", original.stroke], ["stroke-dasharray", original.dash],
    ]) {
      if (value === null) edge.path.removeAttribute(key);
      else edge.path.setAttribute(key, value);
    }
    edge.naturalLabelX = original.labelX;
    edge.naturalLabelY = original.labelY;
    edge.routeBounds = original.routeBounds;
    if (original.conflict) edge.element.dataset.routingConflict = "true";
    else edge.element.removeAttribute("data-routing-conflict");
    edge.element.removeAttribute("data-routing-pending");
  }
  const restored = nodeModelsAtLiveCoordinates()
    .find(node => node.id === drag.sourceId);
  if (restored) lastRouteObstacles.set(drag.sourceId, [
    restored.x - 24, restored.y - 24,
    restored.x + restored.width + 24, restored.y + restored.height + 24,
  ]);
  relocateLiveEdgeLabels();
  return true;
}
function rollbackDragNode(drag) {
  setNodeOffset(drag.sourceId, drag.rollbackOffset.x, drag.rollbackOffset.y);
  if (!drag.previewOriginals) {
    applyNodeTransform(drag.sourceId);
    return;
  }
  bulkEdgeUpdate = true;
  try { applyNodeTransform(drag.sourceId); } finally { bulkEdgeUpdate = false; }
  rollbackSmartDragPreview(drag);
}
function updateIncidentEdges(sourceId) {
  if (documentMode && routingMode() === "smart") {
    const liveNodes = nodeModelsAtLiveCoordinates();
    const nodeById = new Map(liveNodes.map(node => [node.id, node]));
    const node = nodeById.get(sourceId);
    const next = node ? [
      node.x - 24, node.y - 24,
      node.x + node.width + 24, node.y + node.height + 24,
    ] : null;
    const previous = lastRouteObstacles.get(sourceId);
    if (next) lastRouteObstacles.set(sourceId, next);
    const influence = previous && next ? [
      Math.min(previous[0], next[0]), Math.min(previous[1], next[1]),
      Math.max(previous[2], next[2]), Math.max(previous[3], next[3]),
    ] : null;
    const pendingDrag = gesture?.kind === "drag" && (
      liveNodes.length > MAX_SYNC_SMART_DRAG_NODES ||
      edges.size > MAX_SYNC_SMART_DRAG_EDGES ||
      (incidentEdges.get(sourceId)?.size || 0) > MAX_SYNC_SMART_DRAG_INCIDENT
    );
    // Dense drags never synchronously run 256 expensive visibility searches.
    // They show an explicitly unverified, cheap geometry preview instead.
    // Release publishes the actual document for the certified server render.
    for (const [edgeId, edge] of edges) {
      const rect = edge.routeBounds;
      const affected = edge.from === sourceId || edge.to === sourceId ||
        !rect || !influence || (
          rect[0] < influence[2] && rect[2] > influence[0] &&
          rect[1] < influence[3] && rect[3] > influence[1]
        );
      if (!affected) continue;
      if (!pendingDrag) {
        updateEdgeGeometry(edgeId);
        continue;
      }
      if (!gesture.previewOriginals) gesture.previewOriginals = new Map();
      if (!gesture.previewOriginals.has(edgeId)) gesture.previewOriginals.set(edgeId, {
        path: edge.path.getAttribute("d") || "",
        hitPath: edge.hitPath.getAttribute("d") || "",
        stroke: edge.path.getAttribute("stroke"),
        dash: edge.path.getAttribute("stroke-dasharray"),
        labelX: edge.naturalLabelX,
        labelY: edge.naturalLabelY,
        routeBounds: edge.routeBounds?.slice() || null,
        conflict: edge.element.dataset.routingConflict === "true",
      });
      if (edge.from === sourceId || edge.to === sourceId) {
        const source = nodeById.get(edge.from);
        const target = nodeById.get(edge.to);
        if (source && target) {
          const box = svg.viewBox.baseVal;
          const preview = liveEdgeGeometry(source, target, {
            route: "standard", lane: edge.lane,
            fromSide: edge.fromSide, toSide: edge.toSide,
            selfLoop: edge.from === edge.to,
            canvasWidth: box.width || 1, canvasHeight: box.height || 1,
          });
          edge.path.setAttribute("d", preview.path);
          edge.hitPath.setAttribute("d", preview.path);
          edge.naturalLabelX = preview.labelX;
          edge.naturalLabelY = preview.labelY;
        }
      }
      edge.routeBounds = null;
      edge.element.dataset.routingPending = "true";
      edge.element.removeAttribute("data-routing-conflict");
      edge.path.setAttribute("stroke", edge.originalStroke);
      edge.path.setAttribute("stroke-dasharray", "4 6");
    }
  } else {
    for (const edgeId of incidentEdges.get(sourceId) || []) updateEdgeGeometry(edgeId);
  }
  relocateLiveEdgeLabels();
  if (handleLayer) refreshConnectionHandles();
}

function expandSmartCanvasToFitRoutes() {
  // Smart routing may extend the path; even simple mode can relocate an
  // unrelated edge label outside the original document's viewBox.
  if (!documentMode) return false;
  const old = svg.viewBox.baseVal;
  if (!(old.width > 0) || !(old.height > 0)) return false;
  let minX = old.x, minY = old.y;
  let maxX = old.x + old.width, maxY = old.y + old.height;
  const include = (left, top, right, bottom) => {
    if (![left, top, right, bottom].every(Number.isFinite)) return;
    minX = Math.min(minX, left - 24);
    minY = Math.min(minY, top - 24);
    maxX = Math.max(maxX, right + 24);
    maxY = Math.max(maxY, bottom + 24);
  };
  for (const edge of edges.values()) {
    if (routingMode() === "smart") {
      if (edge.routeBounds) {
        include(...edge.routeBounds);
      } else {
        try {
          const box = edge.path.getBBox();
          include(box.x, box.y, box.x + box.width, box.y + box.height);
        } catch (_) { /* Unknown path geometry leaves the current bounds. */ }
      }
    }
    if (edge.labelRect) {
      try {
        const bounds = nodeBoundsInSvg(edge.labelRect);
        if (bounds) include(bounds.minX, bounds.minY, bounds.maxX, bounds.maxY);
      } catch (_) { /* Unmeasurable labels retain their original box. */ }
    }
  }
  // Constraint is applied before expansion, not weakened by new route bounds.
  const nextX = Math.floor(minX), nextY = Math.floor(minY);
  const newWidth = Math.ceil(maxX) - nextX;
  const newHeight = Math.ceil(maxY) - nextY;
  if (!(newWidth > 0 && newHeight > 0) ||
      newWidth > 10000000 || newHeight > 10000000) return false;
  if (nextX === old.x && nextY === old.y &&
      newWidth === old.width && newHeight === old.height) return false;
  const dx = nextX - old.x, dy = nextY - old.y;
  svg.setAttribute("viewBox", [nextX, nextY, newWidth, newHeight].join(" "));
  // Preserve one SVG unit per intrinsic pixel and maintain user's pan/zoom.
  svg.setAttribute("width", String(newWidth));
  svg.setAttribute("height", String(newHeight));
  view = {...view, x: view.x + dx * view.scale, y: view.y + dy * view.scale};
  applyView();
  return true;
}

function constrainBoundsOffset(sourceId, bounds, box) {
  let shiftX = 0;
  let shiftY = 0;
  if (bounds.minX < box.x - BOUNDS_EPSILON) shiftX = box.x - bounds.minX;
  else if (bounds.maxX > box.x + box.width + BOUNDS_EPSILON) {
    shiftX = box.x + box.width - bounds.maxX;
  }
  if (bounds.minY < box.y - BOUNDS_EPSILON) shiftY = box.y - bounds.minY;
  else if (bounds.maxY > box.y + box.height + BOUNDS_EPSILON) {
    shiftY = box.y + box.height - bounds.maxY;
  }
  if (Math.abs(shiftX) <= BOUNDS_EPSILON && Math.abs(shiftY) <= BOUNDS_EPSILON) return false;

  const current = nodeOffset(overrides, sourceId);
  setNodeOffset(sourceId, current.x + shiftX, current.y + shiftY);
  applyNodeTransform(sourceId);
  return true;
}

function constrainNodeToCanvas(sourceId) {
  const node = nodes.get(sourceId);
  if (!node) return false;
  const box = svg.viewBox.baseVal;
  if (!(box.width > 0) || !(box.height > 0)) return false;

  let nodeBounds = nodeBoundsInSvg(node);
  if (!nodeBounds) return false;
  const nodeWidth = nodeBounds.maxX - nodeBounds.minX;
  const nodeHeight = nodeBounds.maxY - nodeBounds.minY;
  if (
    nodeWidth > box.width + BOUNDS_EPSILON ||
    nodeHeight > box.height + BOUNDS_EPSILON
  ) {
    return false;
  }

  let changed = constrainBoundsOffset(sourceId, nodeBounds, box);
  if (changed) nodeBounds = nodeBoundsInSvg(node) || nodeBounds;

  const incidentBounds = incidentEdgeBoundsInSvg(sourceId);
  const combined = mergeSvgBounds(nodeBounds, incidentBounds);
  if (!combined) return changed;
  const width = combined.maxX - combined.minX;
  const height = combined.maxY - combined.minY;
  if (width > box.width + BOUNDS_EPSILON || height > box.height + BOUNDS_EPSILON) {
    const current = nodeOffset(overrides, sourceId);
    if (
      Math.abs(current.x) > BOUNDS_EPSILON ||
      Math.abs(current.y) > BOUNDS_EPSILON
    ) {
      setNodeOffset(sourceId, 0, 0);
      applyNodeTransform(sourceId);
      return true;
    }
    return changed;
  }

  return constrainBoundsOffset(sourceId, combined, box) || changed;
}

function constrainAllNodesToCanvas() {
  let changed = false;
  for (const sourceId of nodes.keys()) {
    changed = constrainNodeToCanvas(sourceId) || changed;
  }
  return changed;
}

function setDocumentControlState(
  control,
  enabled,
  enabledTitle,
  disabledTitle,
  visible = enabled,
) {
  if (!(control instanceof HTMLButtonElement)) return;
  control.hidden = !visible;
  control.disabled = !enabled;
  control.title = enabled ? enabledTitle : disabledTitle;
}

function routingMode() {
  return sourceModel?.source?.schauwerk?.edgeRouting === "smart" ? "smart" : "simple";
}
function updateRoutingControl() {
  if (!(smartRoutingButton instanceof HTMLButtonElement)) return;
  smartRoutingButton.hidden = !documentEditorHosted;
  const active = routingMode() === "smart";
  smartRoutingButton.disabled = observationMode;
  smartRoutingButton.setAttribute("aria-pressed", String(active));
  smartRoutingButton.setAttribute("aria-label",
    active ? "Intelligente Kantenführung ausschalten" : "Intelligente Kantenführung einschalten");
  smartRoutingButton.textContent = "Intelligente Kantenführung: " + (active ? "Ein" : "Aus");
}
function updateDocumentToolbarState() {
  if (!documentEditorHosted) return;
  updateRoutingControl();
  const hasNode = Boolean(selectedId && nodes.has(selectedId));
  const hasEdge = Boolean(selectedEdgeId && edges.has(selectedEdgeId));
  if (edgePorts instanceof HTMLElement) edgePorts.hidden = !hasEdge || observationMode;
  if (hasEdge) {
    const edgeModel = sourceModel.edges.find(item => String(item.id) === selectedEdgeId);
    if (edgeFromPort instanceof HTMLSelectElement) edgeFromPort.value = edgeModel?.from_side || "";
    if (edgeToPort instanceof HTMLSelectElement) edgeToPort.value = edgeModel?.to_side || "";
    if (edgeFromEnd instanceof HTMLSelectElement) edgeFromEnd.value = edgeModel?.from_end || "none";
    if (edgeToEnd instanceof HTMLSelectElement) edgeToEnd.value = edgeModel?.to_end || "arrow";
    if (edgeKind instanceof HTMLSelectElement) edgeKind.value = edgeModel?.source?.schauwerk?.kind || "flow";
  }
  setDocumentControlState(
    addNodeButton,
    true,
    "Element hinzufügen",
    "Element hinzufügen",
    true,
  );
  setDocumentControlState(
    addEdgeButton,
    hasNode,
    "Verbindung vom ausgewählten Element hinzufügen",
    "Zuerst ein Element auswählen",
  );
  setDocumentControlState(
    editTextButton,
    hasNode || hasEdge,
    "Text der Auswahl bearbeiten",
    "Zuerst ein Element oder eine Verbindung auswählen",
  );
  setDocumentControlState(
    reattachSourceButton,
    hasEdge,
    "Anfang der ausgewählten Verbindung ändern",
    "Zuerst eine Verbindung auswählen",
  );
  setDocumentControlState(
    reattachTargetButton,
    hasEdge,
    "Ende der ausgewählten Verbindung ändern",
    "Zuerst eine Verbindung auswählen",
  );
  setDocumentControlState(
    deleteSelectionButton,
    hasNode || hasEdge,
    "Auswahl löschen",
    "Zuerst ein Element oder eine Verbindung auswählen",
  );
  if (observationMode) {
    for (const button of [
      addNodeButton, addEdgeButton, editTextButton,
      reattachSourceButton, reattachTargetButton, deleteSelectionButton,
    ]) {
      if (button instanceof HTMLButtonElement) button.disabled = true;
    }
  }
  refreshConnectionHandles();
}

function selectEdge(edgeId) {
  if (selectedEdgeId && edges.has(selectedEdgeId)) {
    edges.get(selectedEdgeId).element?.classList.remove("is-selected");
    edges.get(selectedEdgeId).element?.setAttribute("aria-selected", "false");
  }
  selectedEdgeId = edgeId && edges.has(edgeId) ? edgeId : null;
  if (selectedEdgeId) {
    selectedId = null;
    for (const node of nodes.values()) {
      node.classList.remove("is-selected");
      node.setAttribute("aria-selected", "false");
    }
    const edgeState = edges.get(selectedEdgeId);
    edgeState.element?.classList.add("is-selected");
    edgeState.element?.setAttribute("aria-selected", "true");
    const label = edgeState.element?.querySelector("title")?.textContent?.trim() || selectedEdgeId;
    selectionStatus.textContent = `Verbindung: ${label || selectedEdgeId}`;
  }
  updateDocumentToolbarState();
}

function selectNode(sourceId, { focus = false } = {}) {
  if (selectedId && nodes.has(selectedId)) {
    const previous = nodes.get(selectedId);
    previous.classList.remove("is-selected");
    previous.setAttribute("aria-selected", "false");
  }
  if (selectedEdgeId && edges.has(selectedEdgeId)) {
    edges.get(selectedEdgeId).element?.classList.remove("is-selected");
    edges.get(selectedEdgeId).element?.setAttribute("aria-selected", "false");
  }
  selectedEdgeId = null;
  selectedId = sourceId && nodes.has(sourceId) ? sourceId : null;
  if (!selectedId) {
    selectionStatus.textContent = "Keine Auswahl";
    updateDocumentToolbarState();
    return;
  }
  const node = nodes.get(selectedId);
  node.classList.add("is-selected");
  node.setAttribute("aria-selected", "true");
  const label = node.querySelector("title")?.textContent?.trim() || selectedId;
  selectionStatus.textContent = `Element: ${label}`;
  updateDocumentToolbarState();
  if (focus) node.focus({ preventScroll: true });
}

function edgeFromTarget(target) {
  if (!(target instanceof Element)) return null;
  const candidate = target.closest('[data-source-kind="edge"]');
  return candidate instanceof SVGGElement && svg.contains(candidate) ? candidate : null;
}

function createHandleElement(name, x, y, label) {
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", String(x));
  circle.setAttribute("cy", String(y));
  circle.setAttribute("r", String(Math.max(5, 11 / view.scale)));
  circle.classList.add("native-connection-handle");
  circle.setAttribute("data-connection-handle", name);
  circle.setAttribute("pointer-events", "all");
  circle.setAttribute("role", "button");
  circle.setAttribute("aria-label", label);
  circle.setAttribute("aria-hidden", "true"); // Keyboard alternatives are in Bearbeiten.
  circle.setAttribute("tabindex", "-1");
  return circle;
}
function refreshConnectionHandles() {
  if (!documentEditorHosted) return;
  if (!handleLayer) {
    handleLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
    handleLayer.setAttribute("data-connection-handles", "true");
    svg.appendChild(handleLayer);
  }
  if (gesture?.kind === "connection") return;
  handleLayer.replaceChildren();
  if (observationMode) return;
  if (selectedEdgeId && edges.has(selectedEdgeId)) {
    const edgeState = edges.get(selectedEdgeId);
    const line = edgeState.path;
    try {
      const total = line.getTotalLength();
      for (const [endpoint, at] of [["from", 0], ["to", total]]) {
        const point = line.getPointAtLength(at);
        const circle = createHandleElement(
          endpoint, point.x, point.y,
          endpoint === "from" ? "Verbindungsanfang ziehen" : "Verbindungsziel ziehen"
        );
        circle.dataset.edgeId = selectedEdgeId;
        handleLayer.appendChild(circle);
      }
    } catch (_) { /* Malformed paths remain selectable through the toolbar. */ }
  } else if (selectedId && nodes.has(selectedId)) {
    const current = nodeModelsAtLiveCoordinates().find(node => node.id === selectedId);
    if (!current) return;
    const circle = createHandleElement(
      "create", current.x + current.width, current.y + current.height / 2,
      "Neue Verbindung von diesem Element ziehen"
    );
    circle.classList.add("native-connection-create");
    circle.dataset.sourceId = selectedId;
    handleLayer.appendChild(circle);
  }
}
function diagramPointAt(clientX, clientY) {
  const matrix = svg.getScreenCTM();
  if (!matrix) return null;
  try {
    const point = svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    return point.matrixTransform(matrix.inverse());
  } catch (_) { return null; }
}
function nodeAtClientPoint(clientX, clientY) {
  for (const item of document.elementsFromPoint(clientX, clientY)) {
    const node = nodeFromTarget(item);
    if (node) return node.dataset.sourceId || null;
  }
  return null;
}
function clearConnectionPreview() {
  connectionPreview?.remove();
  connectionPreview = null;
}
function beginConnectionGesture(handle, event) {
  if (!documentEditorHosted || observationMode) return false;
  const endpoint = handle.dataset.connectionHandle;
  const edgeId = handle.dataset.edgeId || null;
  const sourceId = handle.dataset.sourceId || null;
  if (!(
    (endpoint === "create" && sourceId && nodes.has(sourceId)) ||
    ((endpoint === "from" || endpoint === "to") && edgeId && edges.has(edgeId))
  )) return false;
  const x = Number(handle.getAttribute("cx"));
  const y = Number(handle.getAttribute("cy"));
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
  if (edgeId) selectEdge(edgeId);
  gesture = {
    kind: "connection", pointerId: event.pointerId,
    endpoint, edgeId, sourceId, x, y,
    startX: event.clientX, startY: event.clientY, moved: false,
  };
  setStatus(endpoint === "create"
    ? "Neue Verbindung zum Zielknoten ziehen"
    : "Verbindungsende auf einen anderen Knoten ziehen");
  return true;
}
function moveConnectionGesture(event) {
  if (!gesture || gesture.kind !== "connection" || observationMode) return;
  const dx = event.clientX - gesture.startX;
  const dy = event.clientY - gesture.startY;
  if (!gesture.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
  gesture.moved = true;
  const point = diagramPointAt(event.clientX, event.clientY);
  if (!point || !handleLayer) return;
  if (!connectionPreview) {
    connectionPreview = document.createElementNS("http://www.w3.org/2000/svg", "path");
    connectionPreview.classList.add("native-connection-preview");
    handleLayer.insertBefore(connectionPreview, handleLayer.firstChild);
  }
  const midX = (gesture.x + point.x) / 2;
  const midY = (gesture.y + point.y) / 2 - 22 / view.scale;
  connectionPreview.setAttribute("d",
    "M " + gesture.x + " " + gesture.y + " Q " + midX + " " + midY +
    " " + point.x + " " + point.y);
  const hovered = nodeAtClientPoint(event.clientX, event.clientY);
  connectionPreview.setAttribute("stroke", hovered ? "#15803d" : "#635bff");
}
function finishConnectionGesture(ended, event) {
  clearConnectionPreview();
  const destination = (
    event.type === "pointerup" && ended.moved
    ? nodeAtClientPoint(event.clientX, event.clientY) : null
  );
  gesture = null;
  if (!destination || observationMode || !documentEditorHosted) {
    refreshConnectionHandles();
    if (ended.moved) setStatus("Verbindung nicht geändert");
    return;
  }
  const snapshot = documentSnapshot();
  if (!snapshot) { refreshConnectionHandles(); return; }
  if (ended.endpoint === "create") {
    if (!documentMutationWithinProductLimits(snapshot, { addEdges: 1 })) {
      refreshConnectionHandles();
      return;
    }
    const id = uniqueId("edge_", [...snapshot.nodes, ...snapshot.edges]);
    snapshot.edges.push({
      id, from: ended.sourceId, to: destination, label: "",
      from_side: null, to_side: null, from_end: "none", to_end: "arrow",
      source: {},
    });
  } else {
    const edge = snapshot.edges.find(item => String(item.id) === ended.edgeId);
    if (!edge || edge[ended.endpoint] === destination) {
      refreshConnectionHandles();
      return;
    }
    edge[ended.endpoint] = destination;
    edge.source = cloneJson(edge.source || {});
    edge.source[ended.endpoint === "from" ? "fromNode" : "toNode"] = destination;
  }
  pointerMovedNode = true;
  rebuildDocument(snapshot);
}
function localPoint(event) {
  const rect = viewport.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function contentSize() {
  const box = svg.viewBox.baseVal;
  return { width: box.width || svg.width.baseVal.value || 1, height: box.height || svg.height.baseVal.value || 1 };
}

function fit({ announce = true } = {}) {
  syncEmbeddedHostOverlays();
  // Status text can wrap and grow the overlay bar (notably on CI/mobile).
  // Measure fit insets only after the final status is in layout.
  if (announce) setStatus("Ansicht angepasst");
  const content = contentSize();
  const fitPadding = embeddedNativeViewer
    ? embeddedViewportFitPadding()
    : standaloneViewportFitPadding();
  view = fitView(
    content.width,
    content.height,
    viewport.clientWidth,
    viewport.clientHeight,
    fitPadding,
  );
  fitScaleFloor = Math.min(MIN_SCALE, view.scale);
  autoFitActive = true;
  applyView();
}

function releasePointerAutoFitIfIdle() {
  if (activePointers.size || gesture) return;
  if (pointerAutoFitBefore && !pointerChangedView && !pointerMovedNode) {
    autoFitActive = true;
    if (pointerFitPending) fit({ announce: false });
  }
  pointerAutoFitBefore = null;
  pointerChangedView = false;
  pointerMovedNode = false;
  pointerFitPending = false;
}

function fitAfterLayoutChange() {
  syncEmbeddedHostOverlays();
  if (autoFitActive) fit({ announce: false });
  else if (activePointers.size && pointerAutoFitBefore) pointerFitPending = true;
}

function zoomBy(factor, anchor = null) {
  const point = anchor || { x: viewport.clientWidth / 2, y: viewport.clientHeight / 2 };
  const next = zoomAt(view, view.scale * factor, point, fitScaleFloor);
  if (factor < 1 && next.scale >= view.scale) return;
  if (activePointers.size) pointerChangedView = true;
  autoFitActive = false;
  view = next;
  applyView();
}

// Undo/Redo and native edits replace the embedded iframe after a successful
// server render. Carry only a user-controlled view across that transactional
// replacement: a new document or automatic fit must start with its own view.
const MANUAL_VIEW_HANDOFF_KEY = "__schauwerkNativeManualViewHandoffV1";
window.addEventListener("pagehide", () => {
  if (!documentEditorHosted || autoFitActive) return;
  try {
    const oldFrame = window.frameElement;
    const host = window.parent;
    // A failed edit may also leave an inert frame. Leaving the workspace
    // clears its active marker before removing the frame; do not hand that
    // abandoned view to another document.
    if (!oldFrame?.inert || !host.document.body.classList.contains("workspace-active") ||
        host.document.querySelector("#nativeRetryButton")?.hidden === false ||
        host.document.querySelector("#editorFrame") !== oldFrame) return;
    if (![view.x, view.y, view.scale].every(Number.isFinite) || view.scale <= 0) return;
    host[MANUAL_VIEW_HANDOFF_KEY] = {
      oldFrame,
      view: { x: view.x, y: view.y, scale: view.scale },
      expiresAt: Date.now() + 45000,
    };
  } catch (_) { /* A foreign embed cannot transfer view-only state. */ }
});

function restoreManualViewAfterNativeFrameReplacement() {
  if (!embeddedNativeViewer) return;
  try {
    const host = window.parent;
    const pending = host[MANUAL_VIEW_HANDOFF_KEY];
    if (!pending) return;
    delete host[MANUAL_VIEW_HANDOFF_KEY];
    const frame = window.frameElement;
    if (!documentEditorHosted || !frame ||
        host.document.querySelector("#editorFrame") !== frame ||
        pending.oldFrame === frame || pending.oldFrame?.isConnected ||
        !pending.oldFrame?.inert || Date.now() > pending.expiresAt) return;
    const saved = pending.view;
    if (![saved?.x, saved?.y, saved?.scale].every(Number.isFinite) ||
        saved.scale <= 0 || saved.scale > MAX_SCALE) return;
    view = { x: saved.x, y: saved.y, scale: saved.scale };
    autoFitActive = false;
    applyView();
  } catch (_) { /* Standalone or cross-origin viewers retain default fit. */ }
}

function nodeFromTarget(target) {
  if (!(target instanceof Element)) return null;
  const candidate = target.closest('[data-source-kind="node"]');
  return candidate instanceof SVGGElement && svg.contains(candidate) ? candidate : null;
}

function startPinchIfPossible() {
  const pointers = [...activePointers.values()];
  if (pointers.length !== 2) return false;
  const [first, second] = pointers;
  const dx = second.x - first.x;
  const dy = second.y - first.y;
  const distance = Math.hypot(dx, dy);
  if (distance < 1) return false;
  if (gesture?.kind === "connection") clearConnectionPreview();
  if (gesture?.kind === "drag") {
    if (gesture.moved) {
      rollbackDragNode(gesture);
      pointerMovedNode = false;
      setStatus("Verschieben abgebrochen");
    }
    nodes.get(gesture.sourceId)?.classList.remove("is-dragging");
  }
  const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
  const diagramPoint = { x: (midpoint.x - view.x) / view.scale, y: (midpoint.y - view.y) / view.scale };
  gesture = {
    kind: "pinch",
    startDistance: distance,
    startScale: view.scale,
    startMidpoint: midpoint,
    diagramPoint,
    moved: false,
  };
  viewport.classList.add("is-panning");
  return true;
}

function updatePinch() {
  if (gesture?.kind !== "pinch") return;
  const pointers = [...activePointers.values()];
  if (pointers.length !== 2) return;
  const [first, second] = pointers;
  const distance = Math.hypot(second.x - first.x, second.y - first.y);
  const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
  if (!gesture.moved
      && Math.abs(distance - gesture.startDistance) < DRAG_THRESHOLD_PX
      && Math.hypot(
        midpoint.x - gesture.startMidpoint.x,
        midpoint.y - gesture.startMidpoint.y,
      ) < DRAG_THRESHOLD_PX) return;
  gesture.moved = true;
  const scale = interactionScale(
    gesture.startScale,
    gesture.startScale * (distance / gesture.startDistance),
    fitScaleFloor,
  );
  const nextView = {
    x: midpoint.x - gesture.diagramPoint.x * scale,
    y: midpoint.y - gesture.diagramPoint.y * scale,
    scale,
  };
  if (nextView.x !== view.x || nextView.y !== view.y || nextView.scale !== view.scale) {
    pointerChangedView = true;
  }
  autoFitActive = false;
  view = nextView;
  applyView();
}

for (const node of svg.querySelectorAll('[data-source-kind="node"]')) {
  const sourceId = node.dataset.sourceId;
  if (!sourceId || nodes.has(sourceId)) continue;
  nodes.set(sourceId, node);
  baseTransforms.set(sourceId, node.getAttribute("transform") || "");
  node.setAttribute("tabindex", "0");
  node.setAttribute("role", "button");
  node.setAttribute("aria-selected", "false");
  node.addEventListener("keydown", (event) => {
    if (observationMode) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectNode(sourceId);
    }
  });
}

const edgeById = new Map(
  sourceModel.edges
    .filter((edge) => edge && typeof edge.id === "string")
    .map((edge) => [edge.id, edge]),
);
const laneStep = svg.dataset.intent === "process" ? 14 : 8;
const laneRank = new Map(
  [...edgeById.keys()].sort().map((edgeId, index) => [edgeId, ((index % 5) - 2) * laneStep]),
);
for (const edgeGroup of svg.querySelectorAll('[data-source-kind="edge"]')) {
  if (!(edgeGroup instanceof SVGGElement)) continue;
  const edgeId = edgeGroup.dataset.sourceId;
  const model = edgeId ? edgeById.get(edgeId) : null;
  const path = [...edgeGroup.children].find((child) => child instanceof SVGPathElement);
  const labelRect = [...edgeGroup.children].find((child) => child instanceof SVGRectElement);
  if (!edgeId || !model || !(path instanceof SVGPathElement) || !(labelRect instanceof SVGRectElement)) continue;
  const baseLabelX = Number(labelRect.getAttribute("x")) + Number(labelRect.getAttribute("width")) / 2;
  const baseLabelY = Number(labelRect.getAttribute("y")) + Number(labelRect.getAttribute("height")) / 2;
  if (!Number.isFinite(baseLabelX) || !Number.isFinite(baseLabelY)) continue;
  const labelElements = [...edgeGroup.children].filter(
    (child) => child instanceof SVGRectElement || child instanceof SVGTextElement,
  );
  const clipRect = edgeGroup.querySelector("clipPath > rect");
  // Viewer-only hit target: SVG/PDF output stays byte-identical.
  // Keep the enlarged target on the actual curve during live node drags.
  const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  hitPath.classList.add("native-edge-hit");
  hitPath.setAttribute("d", path.getAttribute("d") || "");
  hitPath.setAttribute("fill", "none");
  hitPath.setAttribute("stroke", "transparent");
  hitPath.setAttribute("stroke-width", String(EDGE_HIT_TARGET_SCREEN_PX / view.scale));
  hitPath.setAttribute("pointer-events", "stroke");
  hitPath.setAttribute("aria-hidden", "true");
  edgeGroup.insertBefore(hitPath, labelRect);
  edgeGroup.setAttribute("tabindex", "0");
  edgeGroup.setAttribute("role", "button");
  edgeGroup.setAttribute("aria-label", `Verbindung: ${String(model.label || edgeId)}`);
  edgeGroup.setAttribute("aria-selected", "false");
  edgeGroup.addEventListener("keydown", (event) => {
    if (observationMode) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectEdge(edgeId);
    }
  });
  edges.set(edgeId, {
    element: edgeGroup,
    from: String(model.from),
    to: String(model.to),
    kind: edgeGroup.dataset.kind || String(model.kind || "flow"),
    route: edgeGroup.dataset.route || "standard",
    lane: Number.isFinite(Number(edgeGroup.dataset.lane))
      ? Number(edgeGroup.dataset.lane)
      : (laneRank.get(edgeId) || 0),
    fromSide: model.from_side || null,
    toSide: model.to_side || null,
    path,
    hitPath,
    basePath: path.getAttribute("d") || "",
    baseLabelX,
    baseLabelY,
    naturalLabelX: baseLabelX,
    naturalLabelY: baseLabelY,
    originalStroke: edgeGroup.dataset.canonicalStroke || path.getAttribute("stroke") || "#64748b",
    originalDash: edgeGroup.dataset.canonicalDash ??
      (path.getAttribute("stroke-dasharray") || ""),
    labelElements,
    labelRect,
    clipRect: clipRect instanceof SVGRectElement ? clipRect : null,
  });
  addIncidentEdge(String(model.from), edgeId);
  addIncidentEdge(String(model.to), edgeId);
}
for (const edge of edges.values()) {
  const key = JSON.stringify([edge.from, edge.to].sort());
  maxLaneByPair.set(key, Math.max(
    maxLaneByPair.get(key) || 0, Math.abs(edge.lane)
  ));
}
applyAllNodeTransforms();

// View-only mode is session-local: it never edits source, layout overrides or drafts.
// Cancel any in-progress edit before allowing an event on the diagram to pan instead.
function setObservationMode(enabled) {
  observationMode = Boolean(enabled);
  clearConnectionPreview();
  if (gesture?.kind === "drag") {
    rollbackDragNode(gesture);
    nodes.get(gesture.sourceId)?.classList.remove("is-dragging");
  }
  for (const pointerId of activePointers.keys()) {
    try { viewport.releasePointerCapture(pointerId); } catch (_) { /* Pointer already released. */ }
  }
  activePointers.clear();
  gesture = null;
  viewport.classList.remove("is-panning");
  viewport.classList.toggle("is-observing", observationMode);
  pointerAutoFitBefore = null;
  pointerChangedView = false;
  pointerMovedNode = false;
  pointerFitPending = false;
  edgeCreateSource = null;
  edgeReattach = null;
  textEditTarget = null;
  if (textDialog instanceof HTMLDialogElement && textDialog.open) textDialog.close();
  selectNode(null);
  if (editControls instanceof HTMLDetailsElement) {
    editControls.open = false;
    editControls.hidden = observationMode || !documentEditorHosted;
  }
  if (resetLayout instanceof HTMLButtonElement) resetLayout.disabled = observationMode;
  if (observationButton instanceof HTMLButtonElement) {
    observationButton.setAttribute("aria-pressed", String(observationMode));
    observationButton.setAttribute(
      "aria-label",
      observationMode ? "Bearbeitungsmodus einschalten" : "Beobachtungsmodus einschalten",
    );
    observationButton.textContent = observationMode ? "Bearbeiten" : "Beobachten";
    observationButton.title = observationMode
      ? "Bearbeitung und Verschieben wieder erlauben"
      : "Schaubild nur betrachten, ohne Elemente zu verändern";
  }
  if (interactionHint) {
    interactionHint.textContent = observationMode
      ? "Beobachten · Scrollen · Wischen · Zoomen"
      : documentEditorHosted
        ? "Verschieben · Zoomen · Text · Elemente & Verbindungen"
        : "Verschieben · Zoomen · Auswählen";
  }
  updateDocumentToolbarState();
  setStatus(observationMode ? "Beobachtungsmodus · keine Änderungen" : "Bearbeitung wieder aktiv");
  if (documentEditorHosted && window.parent !== window) {
    window.parent.postMessage(
      { event: "native-observation-mode", enabled: observationMode },
      window.location.origin,
    );
  }
}
// Opt-in, read-only HTML/SVG preview. Native SVG stays the default; the preview
// reuses view-only mode as its mutation lock and restores the previous mode.
const hybridPreview = documentMode && hybridPreviewSupported(sourceModel)
  ? createHybridPreview({
    canvas, svg, viewport, nodes, edges,
    getModel: () => sourceModel,
    boundsInSvg: nodeBoundsInSvg,
  })
  : null;
let observationBeforeHybrid = false;
function setHybridPreview(enabled) {
  if (!hybridPreview || hybridPreview.active === Boolean(enabled)) return;
  if (enabled) {
    observationBeforeHybrid = observationMode;
    if (!observationMode) setObservationMode(true);
    if (!hybridPreview.enable()) {
      if (!observationBeforeHybrid) setObservationMode(false);
      return;
    }
  } else {
    hybridPreview.disable();
    if (!observationBeforeHybrid) setObservationMode(false);
  }
  const on = hybridPreview.active;
  if (hybridButton instanceof HTMLButtonElement) {
    hybridButton.setAttribute("aria-pressed", String(on));
    hybridButton.setAttribute("aria-label", on
      ? "Zurück zu Native (HTML-Vorschau beenden)"
      : "HTML-Vorschau einschalten (schreibgeschützt)");
    hybridButton.textContent = on ? "Zurück zu Native" : "HTML-Vorschau";
  }
  if (observationButton instanceof HTMLButtonElement) {
    observationButton.disabled = on;
    if (on) observationButton.title = "In der HTML-Vorschau gesperrt · zuerst zu Native zurückkehren";
  }
  if (interactionHint) {
    interactionHint.textContent = on
      ? "Vorschau · Scrollen · Zoomen · Doppelklick wählt Text"
      : observationMode ? "Beobachten · Scrollen · Wischen · Zoomen"
        : documentEditorHosted ? "Verschieben · Zoomen · Text · Elemente & Verbindungen"
          : "Verschieben · Zoomen · Auswählen";
  }
  if (authorityHint) {
    authorityHint.textContent = on ? "Vorschau · schreibgeschützt · Native bleibt maßgeblich" : "Änderungen bleiben lokal";
  }
  setStatus(on ? "HTML-Vorschau aktiv · schreibgeschützt" : "Zurück zu Native");
}
if (hybridButton instanceof HTMLButtonElement) {
  hybridButton.hidden = !hybridPreview;
  hybridButton.addEventListener("click", () => setHybridPreview(!hybridPreview?.active));
}
observationButton?.addEventListener("click", () => {
  if (hybridPreview?.active) {
    setStatus("In der HTML-Vorschau gesperrt · zuerst zu Native zurückkehren");
    return;
  }
  setObservationMode(!observationMode);
});
smartRoutingButton?.addEventListener("click", () => {
  if (!documentEditorHosted || observationMode) return;
  const next = routingMode() === "smart" ? "simple" : "smart";
  const snapshot = documentSnapshot();
  if (!snapshot) return;
  snapshot.source.schauwerk = { ...(snapshot.source.schauwerk || {}), edgeRouting: next };
  rebuildDocument(snapshot);
});
function changeSelectedEdgePort(property, value) {
  if (!documentEditorHosted || observationMode || !selectedEdgeId) return;
  const snapshot = documentSnapshot();
  const edge = snapshot?.edges?.find(item => String(item.id) === selectedEdgeId);
  if (!edge) return;
  if (!["", "left", "right", "top", "bottom"].includes(value)) return;
  edge[property] = value || null;
  rebuildDocument(snapshot);
}
edgeFromPort?.addEventListener("change", () => changeSelectedEdgePort("from_side", edgeFromPort.value));
edgeToPort?.addEventListener("change", () => changeSelectedEdgePort("to_side", edgeToPort.value));
function changeSelectedEdgeEnd(property, value) {
  if (!documentEditorHosted || observationMode || !selectedEdgeId ||
      !["none", "arrow"].includes(value)) return;
  const snapshot = documentSnapshot();
  const edge = snapshot?.edges?.find(item => String(item.id) === selectedEdgeId);
  if (!edge) return;
  edge[property] = value;
  rebuildDocument(snapshot);
}
function changeSelectedEdgeKind(value) {
  if (!documentEditorHosted || observationMode || !selectedEdgeId ||
      !["flow", "association", "feedback"].includes(value)) return;
  const snapshot = documentSnapshot();
  const edge = snapshot?.edges?.find(item => String(item.id) === selectedEdgeId);
  if (!edge) return;
  edge.source = cloneJson(edge.source || {});
  const extension = { ...(edge.source.schauwerk || {}) };
  if (value === "flow") delete extension.kind;
  else extension.kind = value;
  if (Object.keys(extension).length) edge.source.schauwerk = extension;
  else delete edge.source.schauwerk;
  rebuildDocument(snapshot);
}
edgeFromEnd?.addEventListener("change", () => changeSelectedEdgeEnd("from_end", edgeFromEnd.value));
edgeToEnd?.addEventListener("change", () => changeSelectedEdgeEnd("to_end", edgeToEnd.value));
edgeKind?.addEventListener("change", () => changeSelectedEdgeKind(edgeKind.value));
window.addEventListener("keydown", (event) => {
  if (!documentEditorHosted || observationMode || (!event.ctrlKey && !event.metaKey) ||
      event.altKey || event.isComposing || textDialog?.open) return;
  if (event.target instanceof Element &&
      event.target.closest('input,textarea,[contenteditable],[role="textbox"]')) return;
  const key = String(event.key || "").toLowerCase();
  const direction = key === "z"
    ? (event.shiftKey ? "redo" : "undo")
    : (key === "y" && !event.shiftKey ? "redo" : null);
  if (!direction) return;
  event.preventDefault();
  window.parent.postMessage(
    { event: "native-history-command", direction },
    window.location.origin,
  );
});

viewport.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  // The first pointer suspends fit; pure taps restore the previously active mode.
  if (activePointers.size === 0) {
    pointerAutoFitBefore = autoFitActive;
    pointerChangedView = false;
    pointerMovedNode = false;
    pointerFitPending = false;
  }
  autoFitActive = false;
  const point = localPoint(event);
  const handle = event.target instanceof Element
    ? event.target.closest("[data-connection-handle]") : null;
  const node = handle ? null : nodeFromTarget(event.target);
  const edge = node || handle ? null : edgeFromTarget(event.target);
  activePointers.set(event.pointerId, {
    ...point,
    clientX: event.clientX,
    clientY: event.clientY,
    background: node === null,
  });
  viewport.setPointerCapture(event.pointerId);
  event.preventDefault();

  if (activePointers.size === 2 && startPinchIfPossible()) {
    for (const item of nodes.values()) item.classList.remove("is-dragging");
    return;
  }
  if (activePointers.size > 1) return;

  // In observation mode *every* single-pointer gesture is view navigation,
  // even if its origin is a node or edge. Touch pinch above remains enabled.
  if (observationMode) {
    gesture = {
      kind: "pan",
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startView: { ...view },
      moved: false,
    };
    viewport.classList.add("is-panning");
    return;
  }

  if (handle instanceof SVGCircleElement && svg.contains(handle)) {
    if (beginConnectionGesture(handle, event)) return;
  }
  if (node) {
    const sourceId = node.dataset.sourceId;
    if (documentEditorHosted && edgeReattach && sourceId) {
      const document = documentSnapshot();
      const edgeItem = document.edges.find(
        (item) => String(item.id) === edgeReattach.edgeId,
      );
      if (edgeItem) {
        edgeItem[edgeReattach.endpoint] = sourceId;
        edgeItem.source = cloneJson(edgeItem.source || {});
        if (edgeReattach.endpoint === "from") edgeItem.source.fromNode = sourceId;
        else edgeItem.source.toNode = sourceId;
      }
      edgeReattach = null;
      activePointers.delete(event.pointerId);
      try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* frame rebuild */ }
      releasePointerAutoFitIfIdle();
      rebuildDocument(document);
      return;
    }
    if (documentEditorHosted && edgeCreateSource && sourceId) {
      const document = documentSnapshot();
      if (!documentMutationWithinProductLimits(document, { addEdges: 1 })) {
        edgeCreateSource = null;
        activePointers.delete(event.pointerId);
        try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* no rebuild */ }
        releasePointerAutoFitIfIdle();
        return;
      }
      const edgeId = uniqueId("edge_", [...document.nodes, ...document.edges]);
      document.edges.push({
        id: edgeId,
        from: edgeCreateSource,
        to: sourceId,
        label: "",
        from_side: null,
        to_side: null,
        from_end: "none",
        to_end: "arrow",
        source: {},
      });
      edgeCreateSource = null;
      activePointers.delete(event.pointerId);
      try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* frame rebuild */ }
      releasePointerAutoFitIfIdle();
      rebuildDocument(document);
      return;
    }
    // Deferred standalone routing pauses during a new gesture; a click
    // without movement must not abandon routes still waiting for certification.
    selectNode(sourceId);
    const startOffset = nodeOffset(overrides, sourceId);
    gesture = {
      kind: "drag",
      pointerId: event.pointerId,
      sourceId,
      startX: event.clientX,
      startY: event.clientY,
      startOffset,
      rollbackOffset: startOffset,
      moved: false,
    };
    node.classList.add("is-dragging");
    return;
  }

  if (edge) {
    selectEdge(edge.dataset.sourceId || null);
    activePointers.delete(event.pointerId);
    try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* selection only */ }
    gesture = null;
    releasePointerAutoFitIfIdle();
    return;
  }
  selectNode(null);
  gesture = {
    kind: "pan",
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startView: { ...view },
    moved: false,
  };
  viewport.classList.add("is-panning");
});

viewport.addEventListener("pointermove", (event) => {
  if (activePointers.has(event.pointerId)) {
    const point = localPoint(event);
    const prior = activePointers.get(event.pointerId);
    activePointers.set(event.pointerId, {
      ...point,
      clientX: event.clientX,
      clientY: event.clientY,
      background: prior.background,
    });
  }
  if (gesture?.kind === "pinch") {
    updatePinch();
    return;
  }
  if (!gesture || gesture.pointerId !== event.pointerId) return;
  if (gesture.kind === "connection") {
    moveConnectionGesture(event);
    return;
  }
  if (gesture.kind === "pan") {
    const dx = event.clientX - gesture.startX;
    const dy = event.clientY - gesture.startY;
    // Touch jitter during a tap is not manual viewport navigation.
    if (!gesture.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
    gesture.moved = true;
    pointerChangedView = true;
    autoFitActive = false;
    view = panBy(gesture.startView, dx, dy);
    applyView();
    return;
  }
  if (gesture.kind === "drag") {
    if (observationMode) return;
    const screenDx = event.clientX - gesture.startX;
    const screenDy = event.clientY - gesture.startY;
    if (!gesture.moved && Math.hypot(screenDx, screenDy) < DRAG_THRESHOLD_PX) return;
    gesture.moved = true;
    pointerMovedNode = true;
    const delta = screenDeltaToSvg(view, screenDx, screenDy);
    setNodeOffset(
      gesture.sourceId,
      gesture.startOffset.x + delta.x,
      gesture.startOffset.y + delta.y,
    );
    applyNodeTransform(gesture.sourceId);
    if (constrainNodeToCanvas(gesture.sourceId)) {
      gesture.startX = event.clientX;
      gesture.startY = event.clientY;
      gesture.startOffset = nodeOffset(overrides, gesture.sourceId);
    }
    // Directly moved, nonincident routes can exceed the static render viewBox.
    // Pending dense previews wait for their final certification on release.
    if (documentMode && !gesture.previewOriginals) {
      expandSmartCanvasToFitRoutes();
    }
    setStatus(gesture?.previewOriginals
      ? "Schnelle Kantenvorschau · intelligente Führung folgt nach Loslassen"
      : "Position geändert · Verbindungen angepasst");
  }
});

function finishPointer(event) {
  const endedGesture = gesture;
  activePointers.delete(event.pointerId);
  try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }

  if (endedGesture?.kind === "connection" && endedGesture.pointerId === event.pointerId) {
    finishConnectionGesture(endedGesture, event);
  } else if (endedGesture?.kind === "drag" && endedGesture.pointerId === event.pointerId) {
    nodes.get(endedGesture.sourceId)?.classList.remove("is-dragging");
    if (event.type === "pointercancel" && endedGesture.moved) {
      rollbackDragNode(endedGesture);
      pointerMovedNode = false;
      setStatus("Verschieben abgebrochen");
    } else if (endedGesture.moved) {
      if (documentEditorHosted) {
        if (endedGesture.previewOriginals) {
          // native-document-change only saves the draft. An uncertified dense
          // preview requires the hosted renderer to rebuild the saved source.
          rebuildDocument(documentSnapshot());
        } else {
          publishDocumentState();
        }
        setStatus(endedGesture.previewOriginals
          ? "Dokumentposition geändert · Kanten werden intelligent geroutet"
          : "Dokumentposition geändert · Kanten live geroutet");
      } else if (documentMode) {
        if (endedGesture.previewOriginals) {
          finishPendingStandaloneSmartRoutes();
        } else {
          setStatus("Position geändert · Dokument unverändert");
        }
      } else if (persistOverrides()) {
        setStatus("Position lokal gespeichert");
      }
    }
    gesture = null;
  } else if (endedGesture?.kind === "pan" && endedGesture.pointerId === event.pointerId) {
    gesture = null;
  } else if (endedGesture?.kind === "pinch" && activePointers.size < 2) {
    const remaining = activePointers.entries().next();
    if (!remaining.done) {
      const [pointerId, pointer] = remaining.value;
      gesture = {
        kind: "pan",
        pointerId,
        startX: pointer.clientX,
        startY: pointer.clientY,
        startView: { ...view },
        moved: false,
      };
      viewport.classList.add("is-panning");
    } else {
      gesture = null;
    }
  }
  if (!gesture) viewport.classList.remove("is-panning");
  releasePointerAutoFitIfIdle();
}
viewport.addEventListener("pointerup", finishPointer);
viewport.addEventListener("pointercancel", finishPointer);

viewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  const modeScale = event.deltaMode === WheelEvent.DOM_DELTA_LINE
    ? 24
    : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
      ? Math.max(1, viewport.clientHeight)
      : 1;
  if (event.ctrlKey || event.metaKey) {
    const factor = Math.exp(-event.deltaY * modeScale * 0.0015);
    zoomBy(factor, localPoint(event));
    return;
  }
  if (activePointers.size && (event.deltaX !== 0 || event.deltaY !== 0)) {
    pointerChangedView = true;
  }
  autoFitActive = false;
  view = panBy(view, -event.deltaX * modeScale, -event.deltaY * modeScale);
  applyView();
}, { passive: false });

function openTextEditor() {
  if (observationMode || !documentEditorHosted || !(textDialog instanceof HTMLDialogElement) || !(textInput instanceof HTMLTextAreaElement)) return;
  const document = documentSnapshot();
  const item = selectedId
    ? document.nodes.find((node) => String(node.id) === selectedId)
    : document.edges.find((edge) => String(edge.id) === selectedEdgeId);
  if (!item) return;
  textEditTarget = selectedId
    ? { kind: "node", id: selectedId }
    : { kind: "edge", id: selectedEdgeId };
  textInput.value = String(item.label ?? "");
  textDialog.showModal();
  textInput.focus();
  textInput.select();
}

function deleteSelection() {
  if (observationMode || !documentEditorHosted) return;
  const document = documentSnapshot();
  if (selectedId) {
    document.nodes = document.nodes.filter((node) => String(node.id) !== selectedId);
    document.edges = document.edges.filter(
      (edge) => String(edge.from) !== selectedId && String(edge.to) !== selectedId,
    );
  } else if (selectedEdgeId) {
    document.edges = document.edges.filter((edge) => String(edge.id) !== selectedEdgeId);
  } else {
    return;
  }
  selectedId = null;
  selectedEdgeId = null;
  rebuildDocument(document);
}

if (documentEditorHosted) {
  if (editControls instanceof HTMLElement) editControls.hidden = false;
  if (interactionHint) interactionHint.textContent = "Verschieben · Zoomen · Text · Elemente & Verbindungen";
  if (authorityHint) authorityHint.textContent = "Dokument wird lokal gesichert";
  updateDocumentToolbarState();
  addNodeButton?.addEventListener("click", () => {
    if (observationMode) return;
    const document = documentSnapshot();
    if (!documentMutationWithinProductLimits(document, { addNodes: 1 })) return;
    const id = uniqueId("node_", [...document.nodes, ...document.edges]);
    const box = svg.viewBox.baseVal;
    document.nodes.push({
      id,
      type: "text",
      x: Math.round(box.x + box.width / 2 - 130),
      y: Math.round(box.y + box.height / 2 - 70),
      width: 260,
      height: 140,
      label: "Neues Element",
      source: { id, type: "text", text: "Neues Element" },
    });
    rebuildDocument(document);
  });
  addEdgeButton?.addEventListener("click", () => {
    if (observationMode) return;
    if (!selectedId) {
      setStatus("Für eine neue Verbindung zuerst ein Element auswählen");
      return;
    }
    edgeCreateSource = selectedId;
    if (editControls instanceof HTMLDetailsElement) editControls.open = false;
    setStatus("Ziel für die neue Verbindung auswählen");
  });
  editTextButton?.addEventListener("click", openTextEditor);
  const beginReattach = (endpoint) => {
    if (observationMode) return;
    if (!selectedEdgeId) {
      setStatus("Zuerst eine Verbindung auswählen");
      return;
    }
    edgeCreateSource = null;
    edgeReattach = { edgeId: selectedEdgeId, endpoint };
    if (editControls instanceof HTMLDetailsElement) editControls.open = false;
    setStatus(
      endpoint === "from"
        ? "Neuen Anfang auswählen"
        : "Neues Ziel auswählen"
    );
  };
  reattachSourceButton?.addEventListener("click", () => beginReattach("from"));
  reattachTargetButton?.addEventListener("click", () => beginReattach("to"));
  deleteSelectionButton?.addEventListener("click", deleteSelection);
  saveTextButton?.addEventListener("click", () => {
    if (observationMode) return;
    if (!textEditTarget || !(textInput instanceof HTMLTextAreaElement)) return;
    const document = documentSnapshot();
    const collection = textEditTarget.kind === "node" ? document.nodes : document.edges;
    const item = collection.find((entry) => String(entry.id) === textEditTarget.id);
    if (!item) return;
    if (
      textEditTarget.kind === "node" &&
      ["file", "link"].includes(String(item.type)) &&
      textInput.value === ""
    ) {
      setStatus("Datei- und Linkknoten dürfen nicht leer sein");
      return;
    }
    item.label = textInput.value;
    textEditTarget = null;
    textDialog?.close();
    rebuildDocument(document);
  });
  for (const node of nodes.values()) {
    node.addEventListener("dblclick", (event) => {
      if (observationMode) return;
      event.preventDefault();
      selectNode(node.dataset.sourceId || null);
      openTextEditor();
    });
  }
  for (const edgeState of edges.values()) {
    edgeState.element?.addEventListener("dblclick", (event) => {
      if (observationMode) return;
      event.preventDefault();
      selectEdge(edgeState.element.dataset.sourceId || null);
      openTextEditor();
    });
  }
} else if (documentMode) {
  if (interactionHint) interactionHint.textContent = "Verschieben · Zoomen · Auswählen";
  if (authorityHint) authorityHint.textContent = "Bearbeiten in Schaubild";
}

zoomIn.addEventListener("click", () => zoomBy(1.2));
zoomOut.addEventListener("click", () => zoomBy(1 / 1.2));
fitButton.addEventListener("click", () => fit());
window.addEventListener("resize", fitAfterLayoutChange);
// The embedded parent layout can settle after native module initialization.
window.addEventListener("load", fitAfterLayoutChange, { once: true });
// A longer live status can grow this overlay after the previous auto-fit.
// Keep automatic clearance synchronized, without changing manual zoom or pan.
const viewerBar = document.querySelector(".viewer-bar");
if (viewerBar && typeof ResizeObserver === "function") {
  new ResizeObserver(fitAfterLayoutChange).observe(viewerBar);
}
// The absolutely positioned host retry row cannot resize the native toolbar.
// Its visibility changes must remeasure host clearance while auto-fit owns view.
if (embeddedNativeViewer && typeof MutationObserver === "function") {
  try {
    const retry = window.parent.document.querySelector("#nativeRetryButton");
    if (retry) {
      new MutationObserver(fitAfterLayoutChange).observe(
        retry, { attributes: true, attributeFilter: ["hidden"] },
      );
    }
  } catch (_) { /* cross-origin host is not observable */ }
}
resetLayout.addEventListener("click", () => {
  if (observationMode) return;
  overrides = {};
  if (!documentMode) {
    try { localStorage.removeItem(STORAGE_KEY); } catch (_) { /* no persistence */ }
  }
  applyAllNodeTransforms();
  if (documentEditorHosted) {
    publishDocumentState();
    setStatus("Positionen zurückgesetzt");
  } else if (documentMode) {
    setStatus("Positionen zurückgesetzt");
  } else {
    setStatus("Positionen zurückgesetzt");
  }
});
window.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const pendingEdgeOperation = Boolean(edgeCreateSource || edgeReattach ||
    gesture?.kind === "connection");
  if (gesture?.kind === "connection") {
    clearConnectionPreview();
    gesture = null;
    for (const pointerId of activePointers.keys()) {
      try { viewport.releasePointerCapture(pointerId); } catch (_) { /* released */ }
    }
    activePointers.clear();
    releasePointerAutoFitIfIdle();
  }
  edgeCreateSource = null;
  edgeReattach = null;
  selectNode(null);
  if (pendingEdgeOperation) setStatus("Verbindungsaktion abgebrochen");
});

const startupStatus = status.textContent;
let startupComplete = false;
function initializeViewer() {
  if (startupComplete) return;
  startupComplete = true;
  const repaired = constrainAllNodesToCanvas();
  const repairPersisted = !repaired || persistOverrides();
  fit({ announce: repairPersisted && status.textContent === startupStatus });
  restoreManualViewAfterNativeFrameReplacement();
  // A freshly rendered frame confirms its initial state; it is not a user edit.
  if (documentEditorHosted) publishDocumentState("native-document-change", documentSnapshot(), { startup: true });
}
const startupFallback = setTimeout(initializeViewer, 50);
requestAnimationFrame(() => {
  clearTimeout(startupFallback);
  initializeViewer();
});
"""

ASSETS = {
    "app.js": APP_JS,
    "interaction.js": INTERACTION_JS,
    "hybrid-preview.js": HYBRID_PREVIEW_JS,
    "smart-router.js": SMART_ROUTER_JS,
    "styles.css": STYLES_CSS + HYBRID_PREVIEW_CSS,
}
