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
        <textarea id="sourceInput" spellcheck="false" placeholder="Zum Beispiel:\nflowchart TD\n  A[Bindung] --> B[Exploration]"></textarea>
      </label>

      <div class="primary-actions">
        <button class="button primary" id="openPasteButton" type="button">Schaubild öffnen</button>
        <button class="button" id="fileButton" type="button">Datei öffnen</button>
        <button class="button ghost" id="blankButton" type="button">Leer beginnen</button>
        <input id="fileInput" type="file" hidden accept=".canvas,.mmd,.mermaid,.drawio,.xml,.json,text/plain,application/json">
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
.editor-wrap { flex: 1; min-height: 520px; background: white; }
.editor-wrap iframe { width: 100%; height: 100%; min-height: 520px; display: block; border: 0; background: white; }

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

CANVAS_IMPORT_JS = r"""const MERMAID_HEADER = /^(?:---[\s\S]*?---\s*)?(?:(?:%%[^\r\n]*)(?:\r?\n|$)\s*)*(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|mindmap|timeline|journey|pie|quadrantChart|requirementDiagram|gitGraph|C4(?:Context|Container|Component)|architecture-beta|radar-beta|packet-beta|venn-beta|treemap-beta|treeView-beta|ishikawa-beta|kanban|zenuml|wardley-beta|eventmodeling)\b/i;

export function normalizeInput(raw) {
  let text = String(raw ?? "").replace(/^\uFEFF/, "").trim();
  const fenced = text.match(/^```(?:mermaid|mmd|json|canvas|xml|drawio)?\s*\n([\s\S]*?)\n```$/i);
  if (fenced) text = fenced[1].trim();
  return text;
}

export function detectInput(raw) {
  const text = normalizeInput(raw);
  if (!text) return { kind: "empty", text };
  if (/^<(?:mxGraphModel|mxfile)\b/i.test(text)) return { kind: "drawio", text };
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

export function isJsonCanvas(value) {
  return Boolean(value && typeof value === "object" && Array.isArray(value.nodes) && Array.isArray(value.edges));
}

const MAX_EXPORT_DATA_URI_CHARS = 32 * 1024 * 1024;
const MAX_PROJECT_XML_CHARS = 10 * 1024 * 1024;
const EXPORT_PREFIXES = {
  png: "data:image/png;base64,",
  svg: "data:image/svg+xml;base64,",
};

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

export function validateDiagramXml(value) {
  if (typeof value !== "string" || !value || value.length > MAX_PROJECT_XML_CHARS) {
    throw new Error("Projekt-XML ist ungültig oder zu groß.");
  }
  const normalized = value.trimStart();
  if (!/^(?:<\?xml[^>]*>\s*)?<(?:mxfile|mxGraphModel)\b/.test(normalized)) {
    throw new Error("Projekt-XML besitzt keinen unterstützten draw.io-Wurzelknoten.");
  }
  return value;
}

function xmlAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\n", "&#xa;");
}

function textEncoderHex(value) {
  const bytes = new TextEncoder().encode(String(value));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function nodeId(value) { return `jc_${textEncoderHex(value)}`; }
function edgeId(value) { return `jce_${textEncoderHex(value)}`; }

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
    return "swimlane;html=0;rounded=1;startSize=28;fillColor=#f5f5f5;strokeColor=#b8c1d1;fontStyle=1;container=0;collapsible=0;";
  }
  const [fill, stroke] = palette(node.color);
  const common = `whiteSpace=wrap;html=0;fillColor=${fill};strokeColor=${stroke};fontColor=#172033;spacing=12;`;
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
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=0;",
    `endArrow=${endArrow};endFill=1;startArrow=${startArrow};startFill=1;`,
    sidePoint(edge.fromSide, "exit"),
    sidePoint(edge.toSide, "entry"),
  ].join("");
}

function validateJsonCanvas(value) {
  if (!isJsonCanvas(value)) throw new Error("Keine gültige JSON-Canvas-Struktur.");
  const ids = new Set();
  for (const [index, node] of value.nodes.entries()) {
    if (!node || typeof node !== "object") throw new Error(`Knoten ${index + 1} ist ungültig.`);
    if (typeof node.id !== "string" || !node.id) throw new Error(`Knoten ${index + 1} hat keine ID.`);
    if (ids.has(node.id)) throw new Error(`Doppelte Knoten-ID: ${node.id}`);
    ids.add(node.id);
  }
  const edgeIds = new Set();
  for (const [index, edge] of value.edges.entries()) {
    if (!edge || typeof edge !== "object") throw new Error(`Kante ${index + 1} ist ungültig.`);
    if (!ids.has(edge.fromNode) || !ids.has(edge.toNode)) {
      throw new Error(`Kante ${index + 1} verweist auf einen unbekannten Knoten.`);
    }
    const rawId = typeof edge.id === "string" && edge.id ? edge.id : `edge_${index + 1}`;
    if (edgeIds.has(rawId)) throw new Error(`Doppelte Kanten-ID: ${rawId}`);
    edgeIds.add(rawId);
  }
}

export function emptyDrawioXml() {
  return '<mxGraphModel grid="0" page="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>';
}

export function jsonCanvasToDrawioXml(source) {
  const value = typeof source === "string" ? JSON.parse(normalizeInput(source)) : source;
  validateJsonCanvas(value);

  const geometryNodes = value.nodes.filter((node) => node && typeof node === "object");
  const minX = Math.min(0, ...geometryNodes.map((node) => numberOr(node.x, 0)));
  const minY = Math.min(0, ...geometryNodes.map((node) => numberOr(node.y, 0)));
  const offsetX = 40 - minX;
  const offsetY = 40 - minY;
  const groups = geometryNodes.filter((node) => node.type === "group");
  const regular = geometryNodes.filter((node) => node.type !== "group");
  const cells = [];

  for (const node of [...groups, ...regular]) {
    const x = numberOr(node.x, 0) + offsetX;
    const y = numberOr(node.y, 0) + offsetY;
    const width = Math.max(40, numberOr(node.width, node.type === "group" ? 440 : 320));
    const height = Math.max(30, numberOr(node.height, node.type === "group" ? 300 : 140));
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

  for (const [index, edge] of value.edges.entries()) {
    const source = nodeId(edge.fromNode);
    const target = nodeId(edge.toNode);
    const rawId = typeof edge.id === "string" && edge.id ? edge.id : `edge_${index + 1}`;
    cells.push(
      `<mxCell id="${xmlAttr(edgeId(rawId))}" value="${xmlAttr(edge.label ?? "")}" ` +
      `style="${xmlAttr(edgeStyle(edge))}" edge="1" parent="1" source="${xmlAttr(source)}" target="${xmlAttr(target)}">` +
      '<mxGeometry relative="1" as="geometry"/></mxCell>'
    );
  }

  return `<mxGraphModel grid="0" page="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells.join("")}</root></mxGraphModel>`;
}
"""

APP_JS = r"""import { detectInput, emptyDrawioXml, jsonCanvasToDrawioXml, validateDiagramXml, validateExportDataUri } from "./canvas-import.js";

const EDITOR_ORIGIN = "__SCHAUWERK_EDITOR_ORIGIN__";
const EDITOR_URL = "__SCHAUWERK_EDITOR_URL__";
const DRAFT_KEY = "schauwerk.standalone-editor.draft.v1";
const MAX_INPUT_BYTES = 5 * 1024 * 1024;

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
};

let pendingLoad = null;
let currentXml = null;
let currentTitle = "Schaubild";
let pendingExport = null;
let editorReady = false;

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

function downloadBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

function downloadDataUri(uri, filename) {
  const anchor = document.createElement("a");
  anchor.href = uri;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

function showStart() {
  elements.workspace.hidden = true;
  elements.startView.hidden = false;
  setError("");
  setStatus(currentXml ? "Entwurf lokal gesichert" : "Bereit");
}

function showWorkspace() {
  elements.startView.hidden = true;
  elements.workspace.hidden = false;
  elements.title.textContent = currentTitle;
}

function prepareInput(raw, title = "Schaubild") {
  const detected = detectInput(raw);
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
    return { xml: detected.text };
  }
  if (detected.kind === "empty") {
    return { xml: emptyDrawioXml() };
  }
  throw new Error("Format nicht erkannt. Unterstützt werden Mermaid, .canvas und draw.io/XML.");
}

function launch(load) {
  pendingLoad = load;
  editorReady = false;
  showWorkspace();
  setStatus("Editor wird geladen …");
  elements.frame.src = "about:blank";
  requestAnimationFrame(() => { elements.frame.src = EDITOR_URL; });
}

function loadPendingIntoEditor() {
  const base = {
    action: "load",
    autosave: 1,
    exportProtocol: true,
    title: currentTitle,
    libs: "general;flowchart",
    fit: 1,
    modified: "unsavedChanges",
    noExitBtn: 1,
  };
  postToEditor({ ...base, ...(pendingLoad || { xml: emptyDrawioXml() }) });
  pendingLoad = null;
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
  if (file.size > MAX_INPUT_BYTES) {
    setError("Die Datei ist für diesen Spike zu groß (maximal 5 MB).\n");
    return;
  }
  try {
    const text = await file.text();
    launch(prepareInput(text, file.name));
  } catch (error) {
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
    pendingExport = null;
    try {
      if (wanted === "drawio") {
        if (message.format !== "svg") throw new Error("Unerwartete Exportantwort.");
        const xml = validateDiagramXml(message.xml);
        saveDraft(xml);
        downloadBlob(
          new Blob([xml], { type: "application/xml;charset=utf-8" }),
          `${safeFilename(currentTitle)}.drawio`
        );
      } else if (wanted === "png" || wanted === "svg") {
        if (message.format !== wanted) throw new Error("Unerwartete Exportantwort.");
        const data = validateExportDataUri(message.data, wanted);
        if (typeof message.xml === "string") saveDraft(validateDiagramXml(message.xml));
        downloadDataUri(data, `${safeFilename(currentTitle)}.${wanted}`);
      } else {
        throw new Error("Exportantwort ohne passende Anforderung.");
      }
      setStatus("Export erstellt");
    } catch (_) {
      setStatus("Unsichere oder ungültige Exportantwort verworfen");
    }
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
elements.fileInput.addEventListener("change", () => openFile(elements.fileInput.files?.[0]));
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
