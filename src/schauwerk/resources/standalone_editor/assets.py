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
      <a class="brand" href="#" id="homeLink" aria-label="Zur Startseite">Schaubild</a>
      <span class="status" id="status" role="status" aria-live="polite">Bereit</span>
    </header>

    <section class="start-card" id="startView">
      <div class="intro">
        <p class="eyebrow">Schaubilder aus KI-Ergebnissen</p>
        <h1>Einfügen, bearbeiten, exportieren.</h1>
        <p class="lede">Füge Mermaid oder JSON Canvas direkt ein, öffne eine Datei oder beginne leer.</p>
      </div>

      <label class="paste-box" for="sourceInput">
        <span>KI-Ergebnis hier einfügen</span>
        <textarea id="sourceInput" spellcheck="false" placeholder="Zum Beispiel:&#10;flowchart TD&#10;  A[Bindung] --> B[Exploration]"></textarea>
      </label>

      <div class="primary-actions">
        <button class="button primary" id="openPasteButton" type="button">Schaubild öffnen</button>
        <button class="button" id="fileButton" type="button">Datei öffnen</button>
        <button class="button ghost" id="blankButton" type="button">Leer beginnen</button>
        <input id="fileInput" type="file" hidden>
      </div>

      <button class="restore-button" id="restoreButton" type="button" hidden>Letzten lokalen Entwurf wiederherstellen</button>
      <p class="error" id="error" role="alert" hidden></p>

      <aside class="boundary-note">
        <strong>Spike:</strong> Die kleine Oberfläche läuft lokal. Die Editor-Engine wird in dieser Testversion noch von
        <code>embed.diagrams.net</code> geladen und benötigt daher Internet. Ein vollständig selbst gehosteter Betrieb ist
        eine getrennte Produktionsentscheidung.
      </aside>
    </section>

    <section class="workspace" id="workspace" hidden>
      <nav class="workspace-bar" aria-label="Schaubildaktionen">
        <button class="button compact ghost" id="backButton" type="button">← Start</button>
        <strong class="document-title" id="documentTitle">Schaubild</strong>
        <span class="spacer"></span>
        <button class="button compact" id="layoutButton" type="button">Aufräumen</button>
        <button class="button compact" id="projectButton" type="button">Projekt</button>
        <button class="button compact" data-export="png" type="button">PNG</button>
        <button class="button compact" data-export="svg" type="button">SVG</button>
        <a class="button compact primary download-link" id="downloadLink" hidden>Datei speichern</a>
        <button class="button compact fullscreen-toggle" id="fullscreenButton" type="button" aria-pressed="false" aria-label="Vollbildmodus aktivieren" title="Vollbildmodus für die Bearbeitung">Vollbild</button>
      </nav>
      <div class="editor-wrap">
        <iframe
          id="editorFrame"
          title="Schaubild bearbeiten"
          sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-popups"
          allow="clipboard-read; clipboard-write"
          referrerpolicy="no-referrer"
        ></iframe>
      </div>
    </section>
  </main>
  <script type="module" src="app.js"></script>
</body>
</html>
"""

STYLES_CSS = r""":root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #172033;
  background: #f4f6fa;
  font-synthesis: none;
}

* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; }
body { min-height: 100vh; }
button, textarea, input { font: inherit; }
button { touch-action: manipulation; }

.app-shell { min-height: 100vh; display: flex; flex-direction: column; }
.topline {
  min-height: 56px;
  padding: 10px clamp(16px, 3vw, 32px);
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid #dce2eb;
  background: rgba(255, 255, 255, 0.94);
}
.brand { color: #172033; text-decoration: none; font-weight: 750; letter-spacing: -0.02em; }
.status { margin-left: auto; color: #667085; font-size: 0.9rem; }

.start-card {
  width: min(880px, calc(100% - 32px));
  margin: clamp(28px, 7vh, 80px) auto;
  padding: clamp(24px, 5vw, 48px);
  border: 1px solid #dce2eb;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 20px 70px rgba(37, 53, 84, 0.08);
}
.eyebrow { margin: 0 0 10px; color: #3859c7; font-size: 0.82rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; }
h1 { margin: 0; font-size: clamp(2rem, 5vw, 3.8rem); line-height: 1.02; letter-spacing: -0.05em; }
.lede { margin: 18px 0 30px; color: #667085; font-size: 1.08rem; line-height: 1.55; }

.paste-box { display: grid; gap: 10px; font-weight: 650; }
.paste-box textarea {
  width: 100%;
  min-height: 220px;
  resize: vertical;
  border: 1px solid #cfd7e6;
  border-radius: 16px;
  padding: 16px;
  color: #172033;
  background: #fbfcff;
  font: 0.94rem/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  outline: none;
}
.paste-box textarea:focus { border-color: #5674dc; box-shadow: 0 0 0 4px rgba(86, 116, 220, 0.13); }

.primary-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.button {
  min-height: 44px;
  border: 1px solid #c9d2e3;
  border-radius: 12px;
  padding: 10px 16px;
  color: #25324a;
  background: #ffffff;
  cursor: pointer;
  font-weight: 650;
}
.button:hover { background: #f5f7fb; }
.button:focus-visible { outline: 3px solid rgba(86, 116, 220, 0.3); outline-offset: 2px; }
.button.primary { border-color: #3859c7; color: white; background: #3859c7; }
.button.primary:hover { background: #2f4fb7; }
.button.ghost { border-color: transparent; background: transparent; }
.button.compact { min-height: 36px; padding: 7px 11px; border-radius: 9px; font-size: 0.9rem; }
.download-link { display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
.download-link[hidden] { display: none; }
.restore-button {
  margin-top: 18px;
  padding: 0;
  border: 0;
  color: #3859c7;
  background: transparent;
  cursor: pointer;
  text-decoration: underline;
}
.error { margin: 18px 0 0; padding: 12px 14px; border-radius: 12px; color: #8c1d18; background: #fff0ef; }
.boundary-note { margin-top: 28px; padding: 14px 16px; border-radius: 12px; color: #536079; background: #f4f6fa; font-size: 0.86rem; line-height: 1.5; }
.boundary-note code { font-size: 0.82rem; }

.workspace { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.workspace-bar {
  min-height: 52px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid #dce2eb;
  background: #ffffff;
}
.document-title { max-width: min(36vw, 420px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spacer { flex: 1; }
.fullscreen-toggle { white-space: nowrap; }
.editor-wrap { flex: 1; min-height: 520px; background: white; }
.editor-wrap iframe { width: 100%; height: 100%; min-height: 520px; display: block; border: 0; background: white; }

body.editor-focus { overflow: hidden; }
body.editor-focus .app-shell { height: 100vh; height: 100dvh; min-height: 0; }
body.editor-focus .topline { display: none; }
body.editor-focus .workspace { position: relative; height: 100vh; height: 100dvh; min-height: 0; }
body.editor-focus .workspace-bar {
  position: absolute;
  z-index: 4;
  top: max(6px, env(safe-area-inset-top));
  right: max(6px, env(safe-area-inset-right));
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  pointer-events: none;
}
body.editor-focus .workspace-bar > :not(.fullscreen-toggle) { display: none; }
body.editor-focus .fullscreen-toggle {
  position: relative;
  width: 40px;
  min-height: 40px;
  padding: 0;
  overflow: hidden;
  color: transparent;
  background: rgba(24, 34, 52, 0.88);
  border-color: rgba(133, 150, 180, 0.55);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22);
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
body.editor-focus .editor-wrap { flex: 1 1 auto; min-height: 0; height: auto; }
body.editor-focus .editor-wrap iframe { min-height: 0; height: 100%; }
@media (max-width: 720px) {
  .start-card { width: min(100% - 20px, 880px); margin: 18px auto; padding: 22px 18px; border-radius: 18px; }
  .primary-actions .button { flex: 1 1 42%; }
  .workspace-bar { overflow-x: auto; }
  .document-title { max-width: 150px; }
  .editor-wrap, .editor-wrap iframe { min-height: calc(100vh - 109px); }
}

@media (prefers-color-scheme: dark) {
  :root { color: #e8edf7; background: #111827; }
  .topline, .start-card, .workspace-bar { background: #182234; border-color: #344056; }
  .brand, .paste-box textarea { color: #e8edf7; }
  .status, .lede { color: #aeb8ca; }
  .paste-box textarea { background: #111827; border-color: #3b475d; }
  .button { color: #e8edf7; background: #202c41; border-color: #42506a; }
  .button:hover { background: #29364d; }
  .button.primary { background: #5674dc; border-color: #5674dc; }
  .boundary-note { color: #b5bed0; background: #202c41; }
  .error { color: #ffb4ad; background: #4f2525; }
  .editor-wrap { background: #182234; }
}
"""

CANVAS_IMPORT_JS = r"""const DRAWIO_ROOT = /^(?:<\?xml\s+version\s*=\s*(?:"1\.[01]"|'1\.[01]')(?:\s+encoding\s*=\s*(?:"[A-Za-z][A-Za-z0-9._-]*"|'[A-Za-z][A-Za-z0-9._-]*'))?(?:\s+standalone\s*=\s*(?:"(?:yes|no)"|'(?:yes|no)'))?\s*\?>\s*)?<(?:mxfile|mxGraphModel)(?=[\s/>])/;
const MERMAID_HEADER = /^(?:---[\s\S]*?---\s*)?(?:(?:%%[^\r\n]*)(?:\r?\n|$)\s*)*(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|mindmap|timeline|journey|pie|quadrantChart|requirementDiagram|gitGraph|C4(?:Context|Container|Component)|architecture-beta|radar-beta|packet-beta|venn-beta|treemap-beta|treeView-beta|ishikawa-beta|kanban|zenuml|wardley-beta|eventmodeling)\b/i;

export const READABLE_NODE_FONT_SIZE = 18;
export const READABLE_EDGE_FONT_SIZE = 16;
export const MIN_READABLE_SCALE = 0.65;
export const READABILITY_ZOOM_FACTOR = 1.2;
export const MAX_READABILITY_ZOOM_STEPS = 8;

export function readabilityZoomStepCount(scale) {
  const current = Number(scale);
  if (!Number.isFinite(current) || current <= 0 || current >= MIN_READABLE_SCALE) return 0;
  return Math.min(
    MAX_READABILITY_ZOOM_STEPS,
    Math.ceil(Math.log(MIN_READABLE_SCALE / current) / Math.log(READABILITY_ZOOM_FACTOR)),
  );
}

const FULL_INPUT_FENCE = /^```(?:mermaid|mmd|json|jsoncanvas|json-canvas|\.?canvas|xml|drawio)?[^\S\r\n]*\r?\n([\s\S]*?)\r?\n```$/i;
const INLINE_INPUT_FENCE = /```(?:mermaid|mmd|json|jsoncanvas|json-canvas|\.?canvas|xml|drawio)[^\S\r\n]*\r?\n([\s\S]*?)\r?\n```/gi;

function detectNormalizedInput(text) {
  if (!text) return { kind: "empty", text };
  if (DRAWIO_ROOT.test(text)) return { kind: "drawio", text };
  if (MERMAID_HEADER.test(text)) return { kind: "mermaid", text };
  if (text.startsWith("{")) {
    try {
      const value = JSON.parse(text);
      if (isJsonCanvas(value)) return { kind: "json-canvas", text, value };
    } catch (_) {
      return { kind: "unknown", text };
    }
  }
  return { kind: "unknown", text };
}

export function normalizeInput(raw) {
  let text = String(raw ?? "").replace(/^\uFEFF/, "").trim();
  const fenced = text.match(FULL_INPUT_FENCE);
  if (fenced) return fenced[1].trim();

  const recognizedFences = [...text.matchAll(INLINE_INPUT_FENCE)]
    .map((match) => match[1].trim())
    .filter((candidate) => detectNormalizedInput(candidate).kind !== "unknown");
  if (recognizedFences.length === 1) text = recognizedFences[0];
  return text;
}

export function detectInput(raw) {
  return detectNormalizedInput(normalizeInput(raw));
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

export function isJsonCanvas(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const hasNodes = Object.prototype.hasOwnProperty.call(value, "nodes");
  const hasEdges = Object.prototype.hasOwnProperty.call(value, "edges");
  if (!hasNodes && !hasEdges) return Object.keys(value).length === 0;
  if (hasNodes && (!Array.isArray(value.nodes) || !value.nodes.every(isCanvasNode))) return false;
  if (hasEdges && (!Array.isArray(value.edges) || !value.edges.every(isCanvasEdge))) return false;
  return true;
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

function nodeStyle(node) {
  if (node.type === "group") {
    return `swimlane;html=0;rounded=1;startSize=28;fillColor=#f5f5f5;strokeColor=#b8c1d1;fontSize=${READABLE_NODE_FONT_SIZE};fontStyle=1;container=0;collapsible=0;`;
  }
  const [fill, stroke] = palette(node.color);
  const common = `whiteSpace=wrap;html=0;fillColor=${fill};strokeColor=${stroke};fontColor=#172033;fontSize=${READABLE_NODE_FONT_SIZE};spacing=12;`;
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

function edgeStyle(edge) {
  const endArrow = edge.toEnd === "none" ? "none" : "classic";
  const startArrow = edge.fromEnd === "arrow" ? "classic" : "none";
  return [
    `edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=0;fontSize=${READABLE_EDGE_FONT_SIZE};`,
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

export function jsonCanvasToDrawioXml(source) {
  const value = typeof source === "string" ? JSON.parse(normalizeInput(source)) : source;
  const { nodes, edges } = validateJsonCanvas(value);

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
      `<object ${metadata.join(" ")}><mxCell style="${xmlAttr(nodeStyle(node))}" vertex="1" parent="1">` +
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
      `style="${xmlAttr(edgeStyle(edge))}" edge="1" parent="1" source="${xmlAttr(source)}" target="${xmlAttr(target)}">` +
      '<mxGeometry relative="1" as="geometry"/></mxCell>'
    );
  }

  const xml = `<mxGraphModel grid="0" page="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells.join("")}</root></mxGraphModel>`;
  if (xml.length > MAX_PROJECT_XML_CHARS) throw new Error("Konvertiertes Projekt-XML ist zu groß.");
  return xml;
}
"""

APP_JS = r"""import { MAX_INPUT_BYTES, READABLE_EDGE_FONT_SIZE, READABLE_NODE_FONT_SIZE, detectInput, emptyDrawioXml, exportDataUriToBlob, jsonCanvasToDrawioXml, readabilityZoomStepCount, validateDiagramXml, validateExportDataUri, validateInputText } from "./canvas-import.js";

const EDITOR_ORIGIN = "__SCHAUWERK_EDITOR_ORIGIN__";
const EDITOR_URL = "__SCHAUWERK_EDITOR_URL__";
const DRAFT_KEY = "schauwerk.standalone-editor.draft.v1";

const elements = {
  startView: document.querySelector("#startView"),
  workspace: document.querySelector("#workspace"),
  sourceInput: document.querySelector("#sourceInput"),
  openPasteButton: document.querySelector("#openPasteButton"),
  fileButton: document.querySelector("#fileButton"),
  fileInput: document.querySelector("#fileInput"),
  blankButton: document.querySelector("#blankButton"),
  restoreButton: document.querySelector("#restoreButton"),
  error: document.querySelector("#error"),
  frame: document.querySelector("#editorFrame"),
  status: document.querySelector("#status"),
  title: document.querySelector("#documentTitle"),
  homeLink: document.querySelector("#homeLink"),
  backButton: document.querySelector("#backButton"),
  layoutButton: document.querySelector("#layoutButton"),
  projectButton: document.querySelector("#projectButton"),
  downloadLink: document.querySelector("#downloadLink"),
  fullscreenButton: document.querySelector("#fullscreenButton"),
};

let pendingLoad = null;
let currentXml = null;
let currentTitle = "Schaubild";
let pendingExport = null;
let preparedDownloadUrl = null;
let editorReady = false;
let editorFocusActive = false;
let loadIntentGeneration = 0;

function invalidateLoadIntents() {
  loadIntentGeneration += 1;
  return loadIntentGeneration;
}

function setStatus(message) { elements.status.textContent = message; }
function setError(message) {
  elements.error.textContent = message || "";
  elements.error.hidden = !message;
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
  pendingLoad = null;
  pendingExport = null;
  editorReady = false;
  replaceEditorFrame();
  clearPreparedDownload();
  elements.workspace.hidden = true;
  elements.startView.hidden = false;
  setError("");
  setStatus(currentXml ? "Entwurf lokal gesichert" : "Bereit");
  elements.sourceInput.focus({ preventScroll: true });
}

function showWorkspace() {
  elements.startView.hidden = true;
  elements.workspace.hidden = false;
  elements.title.textContent = currentTitle;
}

function prepareInput(raw, title = "Schaubild") {
  const detected = detectInput(validateInputText(raw));
  currentTitle = safeFilename(title.replace(/\.(canvas|mmd|mermaid|drawio|xml|json)$/i, ""));
  currentXml = null;
  pendingExport = null;

  if (detected.kind === "mermaid") {
    return {
      descriptor: { format: "mermaid", data: detected.text, wrap: true },
      sourceMetadata: { key: "schauwerkImportFormat", value: "mermaid" },
    };
  }
  if (detected.kind === "json-canvas") {
    return {
      xml: jsonCanvasToDrawioXml(detected.value),
      sourceMetadata: { key: "schauwerkImportFormat", value: "json-canvas-1.0" },
    };
  }
  if (detected.kind === "drawio") {
    return { xml: validateDiagramXml(detected.text) };
  }
  if (detected.kind === "empty") {
    return { xml: emptyDrawioXml() };
  }
  throw new Error("Format nicht erkannt. Unterstützt werden Mermaid, .canvas und draw.io/XML.");
}

function replaceEditorFrame() {
  const previous = elements.frame;
  const frame = previous.cloneNode(false);
  frame.removeAttribute("src");
  previous.replaceWith(frame);
  elements.frame = frame;
  return frame;
}

function launch(load) {
  invalidateLoadIntents();
  clearPreparedDownload();
  pendingExport = null;
  pendingLoad = load;
  editorReady = false;
  const frame = replaceEditorFrame();
  showWorkspace();
  setStatus("Editor wird geladen …");
  requestAnimationFrame(() => {
    if (elements.frame !== frame) return;
    frame.src = EDITOR_URL;
  });
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

function exportDiagram(format) {
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
  if (event.origin !== EDITOR_ORIGIN || event.source !== elements.frame.contentWindow) return;
  const message = parseMessage(event.data);
  if (!message) return;

  if (message.event === "configure") {
    postToEditor({
      action: "configure",
      config: {
        defaultFonts: ["Helvetica", "Arial", "Verdana"],
        zoomFactor: READABILITY_ZOOM_FACTOR,
        defaultVertexStyle: { fontSize: String(READABLE_NODE_FONT_SIZE) },
        defaultEdgeStyle: { fontSize: String(READABLE_EDGE_FONT_SIZE) },
        enabledLibraries: ["general", "flowchart"],
      },
    });
    return;
  }
  if (message.event === "init") {
    editorReady = true;
    loadPendingIntoEditor();
    return;
  }
  if (message.event === "load") {
    enforceReadableInitialScale(message.scale);
    setStatus("Bereit · Änderungen werden lokal gesichert");
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
    setStatus("Externe Links sind im Spike gesperrt");
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
  const draft = readDraft();
  if (!draft) return;
  currentTitle = safeFilename(draft.title || "Schaubild");
  launch({ xml: draft.xml });
});
elements.projectButton.addEventListener("click", () => exportDiagram("drawio"));
elements.downloadLink.addEventListener("click", () => {
  if (preparedDownloadUrl !== null) setStatus("Speichern gestartet");
});
elements.fullscreenButton.addEventListener("click", toggleEditorFullscreen);

elements.layoutButton.addEventListener("click", () => {
  if (!editorReady) return;
  postToEditor({
    action: "layout",
    layouts: [{ layout: "elkLayered", config: { "elk.direction": "DOWN", "elk.spacing.nodeNode": "40", "elk.layered.spacing.nodeNodeBetweenLayers": "60" } }],
  });
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

const initialQuery = new URLSearchParams(window.location.search);
if (initialQuery.get("new") === "1") {
  currentTitle = "Schaubild";
  launch({ xml: emptyDrawioXml() });
}

elements.restoreButton.hidden = !readDraft();
"""

ASSETS = {
    "index.html": INDEX_HTML,
    "styles.css": STYLES_CSS,
    "canvas-import.js": CANVAS_IMPORT_JS,
    "app.js": APP_JS,
}
