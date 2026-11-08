"""Opt-in read-only HTML/SVG hybrid preview for native JSON Canvas documents.

The preview adds a DOM layer to the existing viewer canvas. SVG keeps shapes,
curves and arrows (including the smart-edge router output); the layer shows node
text and edge-label chips. It never owns document authority, never routes and
never writes to the model.
"""
# ruff: noqa: E501

HYBRID_PREVIEW_JS = r"""// Read-only HTML overlay for native JSON Canvas documents.
// Authority: ids and text come from the validated model; geometry is read from
// the live SVG (which already contains the Smart-Edge-Router result). Foreign
// values are written with textContent / setAttribute only; never as markup.
export const HYBRID_PREVIEW_ID = "schauwerk-hybrid-html-preview.v1";
const CSS_COLOR = /^#[0-9a-fA-F]{3,8}$/;
const finite = (value, fallback) => (Number.isFinite(Number(value)) ? Number(value) : fallback);
const safeColor = (value, fallback) => (CSS_COLOR.test(String(value || "")) ? String(value) : fallback);

export function hybridPreviewSupported(model) {
  // Representation inputs (semantic intents) stay native-only in this slice.
  return Boolean(
    model &&
    model.schema_version === "schauwerk-native-editing-document.v1" &&
    model.source_format === "json-canvas-1.0" &&
    Array.isArray(model.nodes) && Array.isArray(model.edges),
  );
}

export function createHybridPreview({ canvas, svg, viewport, getModel, nodes, edges, boundsInSvg }) {
  let layer = null;
  let nodeItems = [];
  let edgeItems = [];
  let observer = null;
  let active = false;

  function textStyleOf(group, selector) {
    const text = group?.querySelector(selector);
    return {
      size: finite(text?.getAttribute("font-size"), 15),
      weight: finite(text?.getAttribute("font-weight"), 500),
      color: safeColor(text?.getAttribute("fill"), "#172033"),
    };
  }

  function lineHeightOf(group, size) {
    const ys = [...(group?.querySelectorAll("text[data-node-label]") || [])]
      .map((text) => Number(text.getAttribute("y"))).filter(Number.isFinite);
    return ys.length > 1 && ys[1] > ys[0] ? ys[1] - ys[0] : Math.round(size * 1.27);
  }

  function build() {
    const model = getModel();
    layer = document.createElement("div");
    layer.className = "hybrid-layer";
    layer.setAttribute("role", "group");
    layer.setAttribute("aria-label", "HTML-Vorschau · schreibgeschützt");
    layer.dataset.hybridPreview = HYBRID_PREVIEW_ID;
    const nodeLayer = document.createElement("div");
    nodeLayer.className = "hybrid-nodes";
    const edgeLayer = document.createElement("div");
    edgeLayer.className = "hybrid-edge-labels";
    nodeItems = [];
    edgeItems = [];
    for (const item of model.nodes) {
      const id = String(item.id);
      const group = nodes.get(id);
      if (!group) continue;
      const style = textStyleOf(group, "text[data-node-label]");
      const element = document.createElement("div");
      element.className = "hybrid-node";
      element.dataset.sourceId = id;
      element.dataset.canvasType = String(item.type || "text");
      element.style.fontSize = style.size + "px";
      element.style.lineHeight = lineHeightOf(group, style.size) + "px";
      element.style.color = style.color;
      const text = document.createElement("div");
      text.className = "hybrid-node-text";
      text.textContent = String(item.label ?? "");
      element.appendChild(text);
      nodeLayer.appendChild(element);
      nodeItems.push({ id, element, group });
    }
    for (const item of model.edges) {
      const id = String(item.id);
      const state = edges.get(id);
      const label = typeof item.label === "string" ? item.label : "";
      if (!state || !state.labelRect || label === "") continue;
      const style = textStyleOf(state.element, ":scope > text");
      const element = document.createElement("div");
      element.className = "hybrid-edge-label";
      element.dataset.sourceId = id;
      element.style.fontSize = style.size + "px";
      element.style.fontWeight = String(style.weight);
      element.style.color = style.color;
      element.style.background = safeColor(state.labelRect.getAttribute("fill"), "#f8fafc");
      element.style.borderRadius = finite(state.labelRect.getAttribute("rx"), 9) + "px";
      element.textContent = label;
      edgeLayer.appendChild(element);
      edgeItems.push({ id, element, state });
    }
    layer.append(nodeLayer, edgeLayer);
    canvas.appendChild(layer);
  }

  function place(element, bounds, sx, sy, box) {
    element.style.left = ((bounds.minX - box.x) * sx).toFixed(3) + "px";
    element.style.top = ((bounds.minY - box.y) * sy).toFixed(3) + "px";
    element.style.width = ((bounds.maxX - bounds.minX) * sx).toFixed(3) + "px";
    element.style.height = ((bounds.maxY - bounds.minY) * sy).toFixed(3) + "px";
    // Chips are one centred, ellipsised line like the native label.
    if (element.classList.contains("hybrid-edge-label")) element.style.lineHeight = element.style.height;
  }

  function refresh() {
    if (!active || !layer) return;
    const box = svg.viewBox.baseVal;
    if (!(box.width > 0) || !(box.height > 0)) return;
    // The layer shares the canvas CSS transform; only SVG user units are mapped.
    const sx = finite(svg.getAttribute("width"), box.width) / box.width;
    const sy = finite(svg.getAttribute("height"), box.height) / box.height;
    layer.style.width = finite(svg.getAttribute("width"), box.width) + "px";
    layer.style.height = finite(svg.getAttribute("height"), box.height) + "px";
    for (const item of nodeItems) {
      const rect = [...item.group.children].find((child) => child instanceof SVGRectElement);
      const bounds = rect ? boundsInSvg(item.group) : null;
      item.element.hidden = !bounds;
      if (bounds) place(item.element, bounds, sx, sy, box);
    }
    for (const item of edgeItems) {
      const rect = item.state.labelRect;
      const width = finite(rect.getAttribute("width"), 0);
      const bounds = width > 0 ? boundsInSvg(rect) : null;
      item.element.hidden = !bounds;
      if (item.state.element.dataset.labelConflict === "true") item.element.dataset.labelConflict = "true";
      else delete item.element.dataset.labelConflict;
      if (bounds) place(item.element, bounds, sx, sy, box);
    }
  }

  function selectContents(event) {
    const hit = document.elementsFromPoint(event.clientX, event.clientY)
      .find((element) => layer?.contains(element) &&
        element.matches(".hybrid-node-text, .hybrid-edge-label"));
    if (!hit) return;
    const range = document.createRange();
    range.selectNodeContents(hit);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  }

  function enable() {
    if (active) return true;
    if (!hybridPreviewSupported(getModel())) return false;
    build();
    active = true;
    canvas.classList.add("hybrid-preview-active");
    viewport.classList.add("hybrid-preview-active");
    refresh();
    observer = new MutationObserver(refresh);
    observer.observe(svg, {
      attributes: true, subtree: true,
      attributeFilter: ["transform", "x", "y", "width", "height", "viewBox"],
    });
    viewport.addEventListener("dblclick", selectContents);
    return true;
  }

  function disable() {
    if (!active) return;
    active = false;
    observer?.disconnect();
    observer = null;
    viewport.removeEventListener("dblclick", selectContents);
    if (layer && window.getSelection()?.containsNode(layer, true)) window.getSelection().removeAllRanges();
    layer?.remove();
    layer = null;
    nodeItems = [];
    edgeItems = [];
    canvas.classList.remove("hybrid-preview-active");
    viewport.classList.remove("hybrid-preview-active");
  }

  return {
    enable,
    disable,
    refresh,
    get active() { return active; },
    get layer() { return layer; },
  };
}
"""

HYBRID_PREVIEW_CSS = r"""
/* Opt-in HTML/SVG hybrid preview: read-only, native SVG stays the default. */
.hybrid-layer {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
}
.hybrid-nodes, .hybrid-edge-labels { position: absolute; inset: 0; }
.hybrid-node, .hybrid-edge-label {
  position: absolute;
  box-sizing: border-box;
  overflow: hidden;
  font-family: Inter, sans-serif;
}
.hybrid-node { padding: 13px 14px 10px; }
.hybrid-node-text {
  pointer-events: auto;
  cursor: text;
  user-select: text;
  -webkit-user-select: text;
  font-weight: 500;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.hybrid-node-text::first-line { font-weight: 700; }
.hybrid-node[data-canvas-type="group"] .hybrid-node-text { font-weight: 700; }
.hybrid-edge-label {
  display: block;
  padding: 0 8px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: auto;
  cursor: text;
  user-select: text;
  -webkit-user-select: text;
  z-index: 2;
}
.hybrid-edge-label[data-label-conflict="true"] {
  background: #ffedd5 !important;
  outline: 1px solid #c2410c;
}
.hybrid-edge-label[hidden], .hybrid-node[hidden] { display: none; }
/* The DOM layer replaces the SVG texts visually; SVG bytes stay untouched. */
.hybrid-preview-active .native-diagram [data-source-kind="node"] > text,
.hybrid-preview-active .native-diagram [data-source-kind="edge"] > rect,
.hybrid-preview-active .native-diagram [data-source-kind="edge"] > text {
  visibility: hidden;
}
.viewer-stage.hybrid-preview-active { cursor: grab; }
#hybridPreview[aria-pressed="true"] {
  border-color: var(--accent);
  background: var(--accent-soft);
}
"""
