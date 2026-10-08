"""No-build browser assets for the Phase-2 native interaction proof."""
# ruff: noqa: E501

from __future__ import annotations

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
  left: max(7px, env(safe-area-inset-left));
  right: max(7px, env(safe-area-inset-right));
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
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
  pointer-events: auto;
}
.view-controls {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
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
  max-width: min(520px, calc(100vw - 14px));
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
.native-diagram [data-source-kind="edge"].is-selected > path {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 4px rgba(99, 91, 255, 0.46));
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
  left: max(7px, env(safe-area-inset-left));
  bottom: max(7px, env(safe-area-inset-bottom));
  min-height: 0;
  max-width: calc(100vw - 14px);
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
    left: max(6px, env(safe-area-inset-left));
    right: max(6px, env(safe-area-inset-right));
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
  .edit-menu { max-width: calc(100vw - 12px); }
  .viewer-foot {
    left: max(6px, env(safe-area-inset-left));
    bottom: max(6px, env(safe-area-inset-bottom));
    max-width: calc(100vw - 12px);
  }
}
@media (max-width: 430px) {
  .document-editor-hosted .viewer-heading { max-width: min(34vw, 128px); }
  .document-editor-hosted .status { max-width: 100%; }
  .document-editor-hosted .controls output { display: none; }
  .viewer-foot span:nth-child(2),
  .viewer-foot span:last-child { display: none; }
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

APP_JS = r"""import {
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
const incidentEdges = new Map();
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
const activePointers = new Map();
const DRAG_THRESHOLD_PX = 4;
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
  return {
    top,
    right: minimumPadding.right,
    bottom,
    left: minimumPadding.left,
  };
}

function standaloneViewportFitPadding() {
  return viewportFitPadding({
    top: VIEWPORT_FIT_PADDING,
    right: VIEWPORT_FIT_PADDING,
    bottom: VIEWPORT_FIT_PADDING,
    left: VIEWPORT_FIT_PADDING,
  });
}

function embeddedViewportFitPadding() {
  return viewportFitPadding(EMBEDDED_VIEWPORT_FIT_PADDING);
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

function publishDocumentState(eventName = "native-document-change", document = documentSnapshot()) {
  if (!documentEditorHosted || !document) return;
  const boundedDocument = boundedDocumentState(document);
  const canvasState = canvasFromDocument(boundedDocument);
  if (!canvasState) return;
  window.parent.postMessage(
    { event: eventName, document: boundedDocument, canvas: canvasState },
    window.location.origin,
  );
}

function rebuildDocument(document) {
  if (!documentEditorHosted || !document) return;
  sourceModel = boundedDocumentState(document);
  overrides = Object.create(null);
  publishDocumentState("native-document-rebuild", sourceModel);
}

function applyView() {
  canvas.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  zoomValue.value = `${Math.round(view.scale * 100)} %`;
  zoomValue.textContent = zoomValue.value;
}

function applyNodeTransform(sourceId) {
  const node = nodes.get(sourceId);
  if (!node) return;
  const offset = nodeOffset(overrides, sourceId);
  const base = baseTransforms.get(sourceId) || "";
  if (offset.x === 0 && offset.y === 0) {
    if (base) node.setAttribute("transform", base);
    else node.removeAttribute("transform");
    updateIncidentEdges(sourceId);
    return;
  }
  const translated = `translate(${offset.x} ${offset.y})`;
  node.setAttribute("transform", base ? `${translated} ${base}` : translated);
  updateIncidentEdges(sourceId);
}

function applyAllNodeTransforms() {
  for (const sourceId of nodes.keys()) applyNodeTransform(sourceId);
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

function resetEdgeLabel(edgeState) {
  for (const element of edgeState.labelElements) element.removeAttribute("transform");
  edgeState.clipRect?.removeAttribute("transform");
}

function updateEdgeGeometry(edgeId) {
  const edgeState = edges.get(edgeId);
  if (!edgeState) return;
  const fromOffset = nodeOffset(overrides, edgeState.from);
  const toOffset = nodeOffset(overrides, edgeState.to);
  if (
    fromOffset.x === 0 && fromOffset.y === 0 &&
    toOffset.x === 0 && toOffset.y === 0
  ) {
    edgeState.path.setAttribute("d", edgeState.basePath);
    resetEdgeLabel(edgeState);
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
  const translated = `translate(${geometry.labelX - edgeState.baseLabelX} ${geometry.labelY - edgeState.baseLabelY})`;
  for (const element of edgeState.labelElements) element.setAttribute("transform", translated);
  edgeState.clipRect?.setAttribute("transform", translated);
}

function updateIncidentEdges(sourceId) {
  for (const edgeId of incidentEdges.get(sourceId) || []) updateEdgeGeometry(edgeId);
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

function updateDocumentToolbarState() {
  if (!documentEditorHosted) return;
  const hasNode = Boolean(selectedId && nodes.has(selectedId));
  const hasEdge = Boolean(selectedEdgeId && edges.has(selectedEdgeId));
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
}

function selectEdge(edgeId) {
  if (selectedEdgeId && edges.has(selectedEdgeId)) {
    edges.get(selectedEdgeId).element?.classList.remove("is-selected");
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

function localPoint(event) {
  const rect = viewport.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function contentSize() {
  const box = svg.viewBox.baseVal;
  return { width: box.width || svg.width.baseVal.value || 1, height: box.height || svg.height.baseVal.value || 1 };
}

function fit({ announce = true } = {}) {
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

function zoomBy(factor, anchor = null) {
  const point = anchor || { x: viewport.clientWidth / 2, y: viewport.clientHeight / 2 };
  const next = zoomAt(view, view.scale * factor, point, fitScaleFloor);
  if (factor < 1 && next.scale >= view.scale) return;
  autoFitActive = false;
  view = next;
  applyView();
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
  if (gesture?.kind === "drag") {
    if (gesture.moved) {
      setNodeOffset(
        gesture.sourceId,
        gesture.rollbackOffset.x,
        gesture.rollbackOffset.y,
      );
      applyNodeTransform(gesture.sourceId);
    }
    nodes.get(gesture.sourceId)?.classList.remove("is-dragging");
  }
  const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
  const diagramPoint = { x: (midpoint.x - view.x) / view.scale, y: (midpoint.y - view.y) / view.scale };
  gesture = { kind: "pinch", startDistance: distance, startScale: view.scale, diagramPoint };
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
  const scale = interactionScale(
    gesture.startScale,
    gesture.startScale * (distance / gesture.startDistance),
    fitScaleFloor,
  );
  autoFitActive = false;
  view = {
    x: midpoint.x - gesture.diagramPoint.x * scale,
    y: midpoint.y - gesture.diagramPoint.y * scale,
    scale,
  };
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
    basePath: path.getAttribute("d") || "",
    baseLabelX,
    baseLabelY,
    labelElements,
    labelRect,
    clipRect: clipRect instanceof SVGRectElement ? clipRect : null,
  });
  addIncidentEdge(String(model.from), edgeId);
  addIncidentEdge(String(model.to), edgeId);
}
applyAllNodeTransforms();

viewport.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  const point = localPoint(event);
  const node = nodeFromTarget(event.target);
  const edge = node ? null : edgeFromTarget(event.target);
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
      rebuildDocument(document);
      return;
    }
    if (documentEditorHosted && edgeCreateSource && sourceId) {
      const document = documentSnapshot();
      if (!documentMutationWithinProductLimits(document, { addEdges: 1 })) {
        edgeCreateSource = null;
        activePointers.delete(event.pointerId);
        try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* no rebuild */ }
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
      rebuildDocument(document);
      return;
    }
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
    return;
  }
  selectNode(null);
  gesture = {
    kind: "pan",
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startView: { ...view },
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
  if (gesture.kind === "pan") {
    autoFitActive = false;
    view = panBy(gesture.startView, event.clientX - gesture.startX, event.clientY - gesture.startY);
    applyView();
    return;
  }
  if (gesture.kind === "drag") {
    const screenDx = event.clientX - gesture.startX;
    const screenDy = event.clientY - gesture.startY;
    if (!gesture.moved && Math.hypot(screenDx, screenDy) < DRAG_THRESHOLD_PX) return;
    gesture.moved = true;
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
    setStatus("Position geändert · Verbindungen angepasst");
  }
});

function finishPointer(event) {
  const endedGesture = gesture;
  activePointers.delete(event.pointerId);
  try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }

  if (endedGesture?.kind === "drag" && endedGesture.pointerId === event.pointerId) {
    nodes.get(endedGesture.sourceId)?.classList.remove("is-dragging");
    if (endedGesture.moved) {
      if (documentEditorHosted) {
        publishDocumentState();
        setStatus("Dokumentposition geändert · Kanten live geroutet");
      } else if (documentMode) {
        setStatus("Position geändert · Dokument unverändert");
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
      };
      viewport.classList.add("is-panning");
    } else {
      gesture = null;
    }
  }
  if (!gesture) viewport.classList.remove("is-panning");
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
  autoFitActive = false;
  view = panBy(view, -event.deltaX * modeScale, -event.deltaY * modeScale);
  applyView();
}, { passive: false });

function openTextEditor() {
  if (!documentEditorHosted || !(textDialog instanceof HTMLDialogElement) || !(textInput instanceof HTMLTextAreaElement)) return;
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
  if (!documentEditorHosted) return;
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
      event.preventDefault();
      selectNode(node.dataset.sourceId || null);
      openTextEditor();
    });
  }
  for (const edgeState of edges.values()) {
    edgeState.element?.addEventListener("dblclick", (event) => {
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
window.addEventListener("resize", () => {
  if (autoFitActive) fit({ announce: false });
});
resetLayout.addEventListener("click", () => {
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
  const pendingEdgeOperation = Boolean(edgeCreateSource || edgeReattach);
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
  if (documentEditorHosted) publishDocumentState();
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
    "styles.css": STYLES_CSS,
}
