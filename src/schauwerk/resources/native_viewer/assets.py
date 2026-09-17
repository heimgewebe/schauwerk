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
        <span class="eyebrow">Native SVG · Phase 2</span>
        <strong>__SCHAUWERK_NATIVE_TITLE__</strong>
      </div>
      <span class="status" id="status" role="status" aria-live="polite">Semantik unverändert</span>
      <div class="controls" aria-label="Ansicht steuern">
        <button id="zoomOut" type="button" aria-label="Verkleinern">−</button>
        <output id="zoomValue" aria-label="Zoomstufe">100 %</output>
        <button id="zoomIn" type="button" aria-label="Vergrößern">+</button>
        <button id="fitView" type="button">Einpassen</button>
        <button id="resetLayout" type="button">Layout zurücksetzen</button>
      </div>
    </header>
    <section class="viewer-stage" id="nativeViewport" aria-label="Interaktives Schaubild">
      <div class="native-canvas" id="nativeCanvas">
__SCHAUWERK_NATIVE_SVG__
      </div>
    </section>
    <footer class="viewer-foot">
      <span id="selectionStatus">Kein Knoten ausgewählt</span>
      <span>Pan · Zoom · Auswahl · Knoten verschieben</span>
      <span>Layout lokal · Source read-only</span>
    </footer>
  </main>
  <script type="module" src="app.js"></script>
</body>
</html>
"""

STYLES_CSS = r""":root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #172033;
  background: #eef2f7;
  font-synthesis: none;
}
* { box-sizing: border-box; }
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; }
button, output { font: inherit; }
button {
  min-width: 42px;
  min-height: 42px;
  border: 1px solid #c8d1df;
  border-radius: 10px;
  padding: 7px 12px;
  color: #25324a;
  background: #fff;
  font-weight: 650;
  cursor: pointer;
  touch-action: manipulation;
}
button:hover { background: #f5f7fb; }
button:focus-visible { outline: 3px solid rgba(56, 89, 199, 0.32); outline-offset: 2px; }
.viewer-shell { height: 100vh; height: 100dvh; display: grid; grid-template-rows: auto 1fr auto; }
.viewer-bar {
  min-height: 64px;
  padding: max(8px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) 8px max(12px, env(safe-area-inset-left));
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid #d8e0eb;
  background: rgba(255, 255, 255, 0.96);
  z-index: 2;
}
.viewer-heading { min-width: 0; display: grid; gap: 2px; }
.viewer-heading strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eyebrow { color: #3859c7; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; }
.status { margin-left: auto; color: #667085; font-size: 0.82rem; white-space: nowrap; }
.controls { display: flex; align-items: center; gap: 6px; }
.controls output { min-width: 58px; text-align: center; color: #536079; font-variant-numeric: tabular-nums; }
.viewer-stage {
  position: relative;
  min-height: 0;
  overflow: hidden;
  background:
    linear-gradient(rgba(100, 116, 139, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(100, 116, 139, 0.06) 1px, transparent 1px),
    #f8fafc;
  background-size: 24px 24px;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.viewer-stage.is-panning { cursor: grabbing; }
.native-canvas { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
.native-diagram { display: block; max-width: none; max-height: none; }
.native-diagram [data-source-kind="node"] { cursor: grab; outline: none; }
.native-diagram [data-source-kind="node"].is-dragging { cursor: grabbing; }
.native-diagram [data-source-kind="node"].is-selected > rect {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 5px rgba(56, 89, 199, 0.55));
}
.native-diagram [data-source-kind="node"]:focus-visible > rect {
  stroke-width: 4px !important;
  filter: drop-shadow(0 0 5px rgba(56, 89, 199, 0.45));
}
.viewer-foot {
  min-height: 38px;
  padding: 7px max(12px, env(safe-area-inset-right)) max(7px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
  display: flex;
  align-items: center;
  gap: 18px;
  color: #667085;
  background: #fff;
  border-top: 1px solid #d8e0eb;
  font-size: 0.78rem;
}
.viewer-foot span:first-child { color: #344054; font-weight: 650; }
@media (max-width: 900px) {
  .viewer-bar { align-items: flex-start; flex-wrap: wrap; gap: 8px; }
  .viewer-heading { flex: 1 1 200px; }
  .status { order: 3; margin-left: 0; flex: 1 1 100%; }
  .controls { margin-left: auto; overflow-x: auto; max-width: 100%; }
  .controls button { white-space: nowrap; }
  .viewer-foot { overflow-x: auto; white-space: nowrap; }
}
@media (max-width: 620px) {
  .viewer-heading .eyebrow { display: none; }
  .controls { width: 100%; margin-left: 0; }
  .controls button { flex: 1 0 auto; }
  .viewer-foot span:nth-child(2) { display: none; }
}
@media (prefers-color-scheme: dark) {
  :root { color: #e8edf7; background: #111827; }
  .viewer-bar, .viewer-foot { background: #182234; border-color: #344056; }
  .status, .viewer-foot, .controls output { color: #aeb8ca; }
  .viewer-foot span:first-child { color: #e8edf7; }
  button { color: #e8edf7; background: #202c41; border-color: #42506a; }
  button:hover { background: #29364d; }
  .viewer-stage { background-color: #111827; }
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
  return {
    x: finite(value.x),
    y: finite(value.y),
    scale: clampScale(value.scale),
  };
}

export function panBy(view, dx, dy) {
  const current = normalizeView(view);
  return { ...current, x: current.x + finite(dx), y: current.y + finite(dy) };
}

export function zoomAt(view, requestedScale, anchor) {
  const current = normalizeView(view);
  const scale = clampScale(requestedScale);
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
  const availableWidth = Math.max(1, finite(viewportWidth, 1) - 2 * Math.max(0, finite(padding)));
  const availableHeight = Math.max(1, finite(viewportHeight, 1) - 2 * Math.max(0, finite(padding)));
  const scale = clampScale(Math.min(availableWidth / width, availableHeight / height));
  return {
    x: (finite(viewportWidth, 1) - width * scale) / 2,
    y: (finite(viewportHeight, 1) - height * scale) / 2,
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
"""

APP_JS = r"""import {
  clampScale,
  fitView,
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

if (!(viewport instanceof HTMLElement) || !(canvas instanceof HTMLElement) || !(svg instanceof SVGSVGElement)) {
  throw new Error("Native viewer DOM contract is incomplete");
}

const inputDigest = svg.dataset.inputDigest || "";
if (!/^[0-9a-f]{64}$/.test(inputDigest)) {
  throw new Error("Native viewer input digest is missing or invalid");
}
const STORAGE_KEY = `schauwerk.native-viewer.layout.v1.${inputDigest}`;
const nodes = new Map();
const baseTransforms = new Map();
let view = { x: 0, y: 0, scale: 1 };
let overrides = readOverrides();
let selectedId = null;
let gesture = null;
const activePointers = new Map();
const DRAG_THRESHOLD_PX = 4;
const BOUNDS_EPSILON = 0.01;

function setStatus(message) { status.textContent = message; }

function readOverrides() {
  try {
    return sanitizeOverrides(JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"));
  } catch (_) {
    return {};
  }
}

function persistOverrides() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeOverrides(overrides)));
    return true;
  } catch (_) {
    setStatus("Layout lokal verändert · Speichern nicht möglich · Semantik unverändert");
    return false;
  }
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
    return;
  }
  const translated = `translate(${offset.x} ${offset.y})`;
  node.setAttribute("transform", base ? `${translated} ${base}` : translated);
}

function applyAllNodeTransforms() {
  for (const sourceId of nodes.keys()) applyNodeTransform(sourceId);
}

function nodeBoundsInSvg(node) {
  const box = node.getBBox();
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

function constrainNodeToCanvas(sourceId) {
  const node = nodes.get(sourceId);
  if (!node) return false;
  const bounds = nodeBoundsInSvg(node);
  const box = svg.viewBox.baseVal;
  if (!bounds || !(box.width > 0) || !(box.height > 0)) return false;
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  if (width > box.width + BOUNDS_EPSILON || height > box.height + BOUNDS_EPSILON) return false;

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
  overrides = updateNodeOffset(overrides, sourceId, current.x + shiftX, current.y + shiftY);
  applyNodeTransform(sourceId);
  return true;
}

function constrainAllNodesToCanvas() {
  let changed = false;
  for (const sourceId of nodes.keys()) {
    changed = constrainNodeToCanvas(sourceId) || changed;
  }
  return changed;
}

function selectNode(sourceId, { focus = false } = {}) {
  if (selectedId && nodes.has(selectedId)) {
    const previous = nodes.get(selectedId);
    previous.classList.remove("is-selected");
    previous.setAttribute("aria-selected", "false");
  }
  selectedId = sourceId && nodes.has(sourceId) ? sourceId : null;
  if (!selectedId) {
    selectionStatus.textContent = "Kein Knoten ausgewählt";
    return;
  }
  const node = nodes.get(selectedId);
  node.classList.add("is-selected");
  node.setAttribute("aria-selected", "true");
  const label = node.querySelector("title")?.textContent?.trim() || selectedId;
  selectionStatus.textContent = `Auswahl: ${label}`;
  if (focus) node.focus({ preventScroll: true });
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
  const content = contentSize();
  view = fitView(content.width, content.height, viewport.clientWidth, viewport.clientHeight);
  applyView();
  if (announce) setStatus("Ansicht eingepasst · Semantik unverändert");
}

function zoomBy(factor, anchor = null) {
  const point = anchor || { x: viewport.clientWidth / 2, y: viewport.clientHeight / 2 };
  view = zoomAt(view, clampScale(view.scale * factor), point);
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
      overrides = updateNodeOffset(
        overrides,
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
  const scale = clampScale(gesture.startScale * (distance / gesture.startDistance));
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
applyAllNodeTransforms();

viewport.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" && event.button !== 0) return;
  const point = localPoint(event);
  const node = nodeFromTarget(event.target);
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
    overrides = updateNodeOffset(
      overrides,
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
    setStatus("Layout lokal verändert · Semantik unverändert");
  }
});

function finishPointer(event) {
  const endedGesture = gesture;
  activePointers.delete(event.pointerId);
  try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }

  if (endedGesture?.kind === "drag" && endedGesture.pointerId === event.pointerId) {
    nodes.get(endedGesture.sourceId)?.classList.remove("is-dragging");
    if (endedGesture.moved && persistOverrides()) {
      setStatus("Layout lokal gesichert · Semantik unverändert");
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
  view = panBy(view, -event.deltaX * modeScale, -event.deltaY * modeScale);
  applyView();
}, { passive: false });

zoomIn.addEventListener("click", () => zoomBy(1.2));
zoomOut.addEventListener("click", () => zoomBy(1 / 1.2));
fitButton.addEventListener("click", () => fit());
resetLayout.addEventListener("click", () => {
  overrides = {};
  try { localStorage.removeItem(STORAGE_KEY); } catch (_) { /* no persistence */ }
  applyAllNodeTransforms();
  setStatus("Lokales Layout zurückgesetzt · Semantik unverändert");
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") selectNode(null);
});

requestAnimationFrame(() => {
  const repaired = constrainAllNodesToCanvas();
  const repairPersisted = !repaired || persistOverrides();
  fit({ announce: repairPersisted });
});
"""

ASSETS = {
    "app.js": APP_JS,
    "interaction.js": INTERACTION_JS,
    "styles.css": STYLES_CSS,
}
