"""Schema-complete native Schaubild editing form assets."""
# ruff: noqa: E501

from __future__ import annotations

REPRESENTATION_EDITOR_JS = r"""// No-build canonical Schaubild representation editor.
export const INTENTS = ["architecture","process","sequence","state","timeline","comparison","knowledge_map","narrative","presentation","mixed"];
// Native drawing cannot render knowledge_map; JSON Canvas is the product fallback.
const NATIVE_INTENTS = INTENTS.filter(value => value !== "knowledge_map");
export const NODE_KINDS = ["human","system","service","store","decision","risk","action","evidence","concept"];
export const EDGE_KINDS = ["authority","flow","evidence","feedback","risk","association"];
export const FORMATS = ["mermaid","canvas","miro_native","table","document"];
export const REQUIREMENTS = ["formal_relations","free_spatial_layout","presentation","collaboration","rich_text","structured_comparison","portable_offline"];
const ID_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const clone = (value) => JSON.parse(JSON.stringify(value));

function uniqueId(prefix, items) {
  const used = new Set(items.map(item => item.id));
  let number = 1;
  while (used.has(prefix + number)) number += 1;
  return prefix + number;
}
function requireItem(items, id, label) {
  const item = items.find(entry => entry.id === id);
  if (!item) throw new Error(label + ": Auswahl ist nicht mehr vorhanden.");
  return item;
}
function rename(items, id, value, label) {
  if (!ID_PATTERN.test(value)) throw new Error(label + ": Ungültige ID (a–z, 0–9, _, beginnend mit Kleinbuchstaben, maximal 64 Zeichen).");
  if (items.some(item => item.id === value && item.id !== id)) throw new Error(label + ": ID bereits vorhanden.");
  requireItem(items, id, label).id = value;
}

// Structural operations preserve dependent references and do not mutate the input.
export function changeRepresentation(source, action) {
  const next = clone(source);
  if (!Array.isArray(next.groups) || !Array.isArray(next.nodes) || !Array.isArray(next.edges)) {
    throw new Error("Die Schaubildquelle enthält keine vollständigen Listen.");
  }
  const id = String(action.id ?? "");
  const value = String(action.value ?? "");
  switch (action.type) {
    case "add-group":
      next.groups.push({id: uniqueId("group_", next.groups), label: "Neue Gruppe"});
      break;
    case "remove-group":
      requireItem(next.groups, id, "Gruppe");
      next.groups = next.groups.filter(item => item.id !== id);
      for (const node of next.nodes) if (node.group === id) delete node.group;
      break;
    case "rename-group":
      rename(next.groups, id, value, "Gruppe");
      for (const node of next.nodes) if (node.group === id) node.group = value;
      break;
    case "add-node":
      next.nodes.push({id: uniqueId("node_", next.nodes), label: "Neues Element", kind: "concept", summary: ""});
      break;
    case "remove-node":
      requireItem(next.nodes, id, "Element");
      if (next.nodes.length === 1) throw new Error("Ein Schaubild braucht mindestens ein Element.");
      next.nodes = next.nodes.filter(item => item.id !== id);
      next.edges = next.edges.filter(edge => edge.from !== id && edge.to !== id);
      break;
    case "rename-node":
      rename(next.nodes, id, value, "Element");
      for (const edge of next.edges) {
        if (edge.from === id) edge.from = value;
        if (edge.to === id) edge.to = value;
      }
      break;
    case "add-edge":
      if (!next.nodes.length) throw new Error("Zuerst ein Element hinzufügen.");
      next.edges.push({id: uniqueId("edge_", next.edges), from: next.nodes[0].id,
        to: next.nodes.length > 1 ? next.nodes[1].id : next.nodes[0].id,
        label: "Neue Verbindung", kind: "association"});
      break;
    case "remove-edge":
      requireItem(next.edges, id, "Verbindung");
      next.edges = next.edges.filter(item => item.id !== id);
      break;
    case "rename-edge":
      rename(next.edges, id, value, "Verbindung");
      break;
    default:
      throw new Error("Unbekannte Schaubildänderung.");
  }
  delete next.input_digest;
  return next;
}

export function validateRepresentation(source) {
  if (!source || source.schema_version !== "schauwerk-representation-input.v1") throw new Error("Unbekanntes Repräsentationsschema.");
  if (!ID_PATTERN.test(source.id)) throw new Error("Ungültige Schaubild-ID.");
  if (typeof source.title !== "string" || !source.title.trim() || source.title.length > 160) throw new Error("Titel muss 1–160 Zeichen enthalten.");
  if (typeof source.purpose !== "string" || !source.purpose.trim() || source.purpose.length > 500) throw new Error("Zweck muss 1–500 Zeichen enthalten.");
  if (!INTENTS.includes(source.intent)) throw new Error("Unbekannte Darstellungsabsicht.");
  if (source.intent === "knowledge_map") throw new Error("Wissenskarten bitte als JSON Canvas bearbeiten.");
  if (!Array.isArray(source.groups) || !Array.isArray(source.nodes) || !Array.isArray(source.edges) || source.nodes.length === 0) {
    throw new Error("Mindestens ein Element und vollständige Gruppen-/Verbindungslisten erforderlich.");
  }
  function ids(items, label) {
    const found = new Set();
    for (const item of items) {
      if (!ID_PATTERN.test(item.id) || found.has(item.id)) throw new Error(label + ": ungültige oder doppelte ID.");
      found.add(item.id);
    }
    return found;
  }
  const groupIds = ids(source.groups, "Gruppe");
  const nodeIds = ids(source.nodes, "Element");
  ids(source.edges, "Verbindung");
  for (const group of source.groups) {
    if (typeof group.label !== "string" || !group.label.trim() || group.label.length > 100) throw new Error("Gruppe " + group.id + ": ungültige Bezeichnung.");
  }
  for (const node of source.nodes) {
    if (typeof node.label !== "string" || !node.label.trim() || node.label.length > 120 || !NODE_KINDS.includes(node.kind)) {
      throw new Error("Element " + node.id + ": Titel oder Typ ungültig.");
    }
    if (node.summary !== undefined && (typeof node.summary !== "string" || node.summary.length > 500)) {
      throw new Error("Element " + node.id + ": Beschreibung ungültig.");
    }
    if (node.group != null && !groupIds.has(node.group)) throw new Error("Element " + node.id + ": Gruppenzuordnung fehlt.");
  }
  for (const edge of source.edges) {
    if (typeof edge.label !== "string" || !edge.label.trim() || edge.label.length > 120 || !EDGE_KINDS.includes(edge.kind)) {
      throw new Error("Verbindung " + edge.id + ": Text oder Typ ungültig.");
    }
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) throw new Error("Verbindung " + edge.id + ": Anfang oder Ziel fehlt.");
  }
  if (!source.requirements || typeof source.requirements !== "object" || Array.isArray(source.requirements)) throw new Error("Anforderungen ungültig.");
  for (const [key,value] of Object.entries(source.requirements)) {
    if (!REQUIREMENTS.includes(key) || typeof value !== "boolean") throw new Error("Anforderung " + key + " ungültig.");
  }
  if (!Array.isArray(source.requested_formats) ||
      source.requested_formats.some(value => !FORMATS.includes(value)) ||
      new Set(source.requested_formats).size !== source.requested_formats.length) throw new Error("Ausgabeformate ungültig oder doppelt.");
  const result = clone(source);
  delete result.input_digest;
  return result;
}

function el(tag, className = "", text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function section(parent, title, id) {
  const box = el("fieldset", "content-entry");
  box.append(el("legend", "", title + (id ? " · " + id : "")));
  parent.append(box);
  return box;
}
function input(parent, title, value, callback, {multiline = false, maxLength = 0, required = false} = {}) {
  const wrapper = el("label", "content-field");
  wrapper.append(el("span", "", title));
  const field = el(multiline ? "textarea" : "input");
  if (!multiline) field.type = "text";
  field.value = String(value ?? "");
  field.required = required;
  if (maxLength) field.maxLength = maxLength;
  field.addEventListener("input", () => callback(field.value));
  wrapper.append(field);
  parent.append(wrapper);
  return field;
}
function idInput(parent, value, callback, caption = "ID") {
  const wrapper = el("label", "content-field");
  wrapper.append(el("span", "", caption));
  const field = el("input");
  field.type = "text";
  field.required = true;
  field.maxLength = 64;
  field.pattern = "[a-z][a-z0-9_]*";
  field.value = value;
  field.addEventListener("change", () => callback(field.value, field));
  wrapper.append(field);
  parent.append(wrapper);
  return field;
}
function select(parent, title, current, entries, callback) {
  const wrapper = el("label", "content-field");
  wrapper.append(el("span", "", title));
  const field = el("select");
  for (const entry of entries) {
    const option = el("option", "", entry.label ?? entry.value);
    option.value = entry.value;
    option.selected = String(entry.value) === String(current ?? "");
    field.append(option);
  }
  field.addEventListener("change", () => callback(field.value));
  wrapper.append(field);
  parent.append(wrapper);
  return field;
}
function button(parent, caption, callback) {
  const control = el("button", "button compact", caption);
  control.type = "button";
  control.addEventListener("click", callback);
  parent.append(control);
}

export function remapRepresentationLayoutOverrides(overrides, nodeIdMapping) {
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) {
    throw new Error("Gespeicherte Knotenpositionen sind ungültig.");
  }
  const migrated = Object.create(null);
  for (const [originalId, currentId] of Object.entries(nodeIdMapping)) {
    if (!ID_PATTERN.test(originalId) || !ID_PATTERN.test(currentId)) {
      throw new Error("Ungültige ID bei der Positionsübernahme.");
    }
    if (Object.prototype.hasOwnProperty.call(overrides, originalId)) {
      migrated[currentId] = overrides[originalId];
    }
  }
  return migrated;
}

export function mountRepresentationEditor(container, representation) {
  let draft = clone(representation);
  const originalNodeIds = new Map(draft.nodes.map(node => [node.id, node.id]));
  delete draft.input_digest;
  draft.requirements ||= {};
  draft.requested_formats ||= [];
  let first = null;
  const feedback = el("p", "content-dialog-feedback");
  feedback.setAttribute("role", "alert");
  function feedbackText(message) { feedback.textContent = message; feedback.hidden = !message; }
  function mutate(action) {
    try {
      draft = changeRepresentation(draft, action);
      if (action.type === "remove-node") {
        for (const [original, current] of originalNodeIds) {
          if (current === action.id) originalNodeIds.delete(original);
        }
      }
      render();
    } catch (error) { feedbackText(error instanceof Error ? error.message : "Bearbeitung fehlgeschlagen."); }
  }
  function rename(type, id, value, field) {
    if (value === id) return;
    try {
      draft = changeRepresentation(draft, {type, id, value});
      if (type === "rename-node") {
        for (const [original, current] of originalNodeIds) {
          if (current === id) originalNodeIds.set(original, value);
        }
      }
      render();
    } catch (error) {
      field.value = id;
      feedbackText(error instanceof Error ? error.message : "ID ungültig.");
    }
  }
  function render() {
    const previousScroll = container.scrollTop;
    container.replaceChildren(feedback);
    feedbackText("");
    const root = section(container, "Schaubild");
    first = idInput(root, draft.id, (value, field) => {
      if (ID_PATTERN.test(value)) draft.id = value;
      else { field.value = draft.id; feedbackText("Schaubild-ID: ungültige ID."); }
    }, "Schaubild-ID");
    input(root, "Titel", draft.title, value => { draft.title = value; }, {required:true,maxLength:160});
    input(root, "Zweck", draft.purpose, value => { draft.purpose = value; }, {required:true,multiline:true,maxLength:500});
    select(root, "Darstellungsabsicht", draft.intent, NATIVE_INTENTS.map(value => ({value})), value => { draft.intent = value; });
    const requirements = section(container, "Anforderungen");
    for (const key of REQUIREMENTS) {
      const line = el("label", "content-field");
      const control = el("input");
      control.type = "checkbox";
      control.checked = Boolean(draft.requirements[key]);
      control.addEventListener("change", () => { draft.requirements[key] = control.checked; });
      line.append(control, el("span", "", key.replaceAll("_"," ")));
      requirements.append(line);
    }
    const formats = section(container, "Ausgabeformate");
    for (const key of FORMATS) {
      const line = el("label", "content-field");
      const control = el("input");
      control.type = "checkbox";
      control.checked = draft.requested_formats.includes(key);
      control.addEventListener("change", () => {
        draft.requested_formats = draft.requested_formats.filter(value => value !== key);
        if (control.checked) draft.requested_formats.push(key);
      });
      line.append(control, el("span", "", key.replaceAll("_"," ")));
      formats.append(line);
    }
    const groups = section(container, "Gruppen");
    button(groups, "+ Gruppe", () => mutate({type:"add-group"}));
    for (const group of draft.groups) {
      const row = section(groups, "Gruppe", group.id);
      idInput(row, group.id, (value,field) => rename("rename-group",group.id,value,field));
      input(row, "Bezeichnung", group.label, value => { group.label = value; }, {required:true,maxLength:100});
      button(row, "Gruppe löschen", () => mutate({type:"remove-group",id:group.id}));
    }
    const nodes = section(container, "Elemente");
    button(nodes, "+ Element", () => mutate({type:"add-node"}));
    for (const node of draft.nodes) {
      const row = section(nodes, "Element", node.id);
      idInput(row, node.id, (value,field) => rename("rename-node",node.id,value,field));
      input(row, "Titel", node.label, value => { node.label = value; }, {required:true,maxLength:120});
      select(row, "Typ", node.kind, NODE_KINDS.map(value => ({value})), value => { node.kind = value; });
      input(row, "Beschreibung", node.summary, value => { node.summary = value; }, {multiline:true,maxLength:500});
      select(row, "Gruppe", node.group ?? "", [{value:"",label:"Keine Gruppe"}].concat(
        draft.groups.map(group => ({value:group.id,label:group.label + " (" + group.id + ")"}))
      ), value => { if (value) node.group = value; else delete node.group; });
      button(row, "Element löschen", () => mutate({type:"remove-node",id:node.id}));
    }
    const edges = section(container, "Verbindungen");
    button(edges, "+ Verbindung", () => mutate({type:"add-edge"}));
    for (const edge of draft.edges) {
      const row = section(edges, "Verbindung", edge.id);
      idInput(row, edge.id, (value,field) => rename("rename-edge",edge.id,value,field));
      input(row, "Beschriftung", edge.label, value => { edge.label = value; }, {required:true,maxLength:120});
      select(row, "Typ", edge.kind, EDGE_KINDS.map(value => ({value})), value => { edge.kind = value; });
      const endpoints = draft.nodes.map(node => ({value:node.id,label:node.label + " (" + node.id + ")"}));
      select(row, "Anfang", edge.from, endpoints, value => { edge.from = value; });
      select(row, "Ziel", edge.to, endpoints, value => { edge.to = value; });
      button(row, "Verbindung löschen", () => mutate({type:"remove-edge",id:edge.id}));
    }
    container.scrollTop = previousScroll;
  }
  render();
  return {
    get first() { return first; },
    getValue() { return validateRepresentation(draft); },
    getDraft() { return clone(draft); },
    getNodeIdMapping() { return Object.fromEntries(originalNodeIds); }
  };
}
"""
