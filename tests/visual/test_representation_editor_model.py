# ruff: noqa: E501
"""Canonical diagram form model tests, run against the browser JavaScript as a module."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from schauwerk.resources.standalone_editor.representation_editor import REPRESENTATION_EDITOR_JS


def run_js(tmp_path: Path, assertions: str) -> None:
    if shutil.which("node") is None:
        pytest.skip("Node unavailable")
    (tmp_path / "model.mjs").write_text(REPRESENTATION_EDITOR_JS, encoding="utf-8")
    program = (
        "import {changeRepresentation as change,validateRepresentation as validate,mountRepresentationEditor as mount,remapRepresentationLayoutOverrides as remap} from './model.mjs';\n"
        "import assert from 'node:assert/strict';\n"
        "const sample={schema_version:'schauwerk-representation-input.v1',id:'test',"
        "title:'Schaubild',purpose:'Test',intent:'process',groups:[{id:'g',label:'Gruppe'}],"
        "nodes:[{id:'a',label:'A',kind:'concept',group:'g',summary:'Text'},"
        "{id:'b',label:'B',kind:'human'}],edges:[{id:'ab',from:'a',to:'b',label:'zu',kind:'flow'}],"
        "requirements:{formal_relations:true},requested_formats:['canvas']};\n"
        + assertions
    )
    (tmp_path / "run.mjs").write_text(program, encoding="utf-8")
    result = subprocess.run(["node", str(tmp_path / "run.mjs")], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_rename_updates_all_references(tmp_path: Path) -> None:
    run_js(tmp_path, """
let edited=change(sample,{type:'rename-group',id:'g',value:'team'});
assert.equal(edited.nodes[0].group,'team');
edited=change(edited,{type:'rename-node',id:'a',value:'start'});
assert.equal(edited.edges[0].from,'start');
assert.equal(sample.edges[0].from,'a');
edited=change(edited,{type:'rename-edge',id:'ab',value:'newedge'});
assert.equal(edited.edges[0].id,'newedge');
assert.deepEqual(validate(edited),edited);
""")


def test_add_delete_cascades_and_minimum(tmp_path: Path) -> None:
    run_js(tmp_path, """
let edited=change(sample,{type:'add-group'});
assert.equal(edited.groups[1].id,'group_1');
edited=change(edited,{type:'add-node'});
assert.equal(edited.nodes[2].id,'node_1');
edited=change(edited,{type:'add-edge'});
assert.equal(edited.edges[1].id,'edge_1');
edited=change(edited,{type:'remove-group',id:'g'});
assert.equal(edited.nodes[0].group,undefined);
edited=change(edited,{type:'remove-node',id:'a'});
assert.equal(edited.edges.length,0);
edited=change(edited,{type:'remove-node',id:'node_1'});
assert.throws(()=>change(edited,{type:'remove-node',id:'b'}),/mindestens ein Element/);
assert.deepEqual(validate(edited),edited);
""")


def test_invalid_and_duplicate_ids_and_dangling_refs(tmp_path: Path) -> None:
    run_js(tmp_path, """
assert.throws(()=>change(sample,{type:'rename-node',id:'a',value:'A#1'}),/ID/);
assert.throws(()=>change(sample,{type:'rename-node',id:'a',value:'b'}),/bereits vorhanden/);
const edited=JSON.parse(JSON.stringify(sample));
edited.edges[0].to='missing';
assert.throws(()=>validate(edited),/Anfang oder Ziel/);
edited.edges[0].to='b';
edited.nodes[0].group='missing';
assert.throws(()=>validate(edited),/Gruppenzuordnung/);
""")


def test_all_fields_and_stale_digest(tmp_path: Path) -> None:
    run_js(tmp_path, """
let edited=JSON.parse(JSON.stringify(sample));
edited.id='other_name';
edited.intent='narrative';
edited.requirements={formal_relations:false,rich_text:true};
edited.requested_formats=['canvas','mermaid','document'];
edited.nodes[1].kind='evidence';
edited.edges[0].kind='feedback';
edited.input_digest='stale';
const actual=validate(edited);
assert.equal(actual.input_digest,undefined);
assert.equal(actual.requested_formats.length,3);
edited.requested_formats=['canvas','canvas'];
assert.throws(()=>validate(edited),/doppelt/);
""")


def test_render_is_dom_only_without_injection() -> None:
    assert "innerHTML" not in REPRESENTATION_EDITOR_JS
    assert "document.createElement" in REPRESENTATION_EDITOR_JS
    assert "textContent" in REPRESENTATION_EDITOR_JS
    assert "mountRepresentationEditor" in REPRESENTATION_EDITOR_JS


def test_form_ui_all_fields_and_structural_buttons(tmp_path: Path) -> None:
    run_js(tmp_path, """
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.handlers={}; this.scrollTop=0; this.textContent=''; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=[...items]; }
  addEventListener(name,fn) { this.handlers[name]=fn; }
  setAttribute(key,value) { this[key]=value; }
  click() { this.handlers.click?.(); }
  change(value) { this.value=value; this.handlers.change?.(); }
  input(value) { this.value=value; this.handlers.input?.(); }
}
globalThis.document={createElement(tag){return new Element(tag)}};
const container=new Element('main');
const form=mount(container,sample);
assert.ok(form.first);
function descendants(root) { return [root, ...root.children.flatMap(descendants)]; }
const texts=()=>descendants(container).map(el=>el.textContent).filter(Boolean);
for (const name of ['Schaubild-ID','Darstellungsabsicht','Anforderungen','Ausgabeformate',
  'Gruppen','Elemente','Verbindungen','Beschreibung','Anfang','Ziel']) {
  assert.ok(texts().includes(name),name);
}
function button(label) { return descendants(container).find(el=>el.tagName==='button' && el.textContent===label); }
assert.ok(button('+ Gruppe'));
assert.ok(button('+ Element'));
assert.ok(button('+ Verbindung'));
button('+ Gruppe').click();
assert.equal(form.getValue().groups.length,2);
button('+ Element').click();
assert.equal(form.getValue().nodes.length,3);
button('+ Verbindung').click();
assert.equal(form.getValue().edges.length,2);
assert.ok(button('Gruppe löschen'));
button('Gruppe löschen').click();
assert.equal(form.getValue().groups.length,1);
assert.equal(form.getValue().nodes[0].group,undefined);
const titleLabel=descendants(container).find(el=>el.tagName==='label' && el.children[0]?.textContent==='Titel');
assert.ok(titleLabel);
titleLabel.children[1].input('Neuer Titel');
assert.equal(form.getValue().title,'Neuer Titel');
assert.deepEqual(form.getNodeIdMapping(),{a:'a',b:'b'});
const nodeA=descendants(container).find(el=>el.tagName==='fieldset' &&
  el.children[0]?.textContent==='Element · a');
const nodeAId=descendants(nodeA).find(el=>el.tagName==='label' &&
  el.children[0]?.textContent==='ID').children[1];
nodeAId.change('alpha');
assert.deepEqual(form.getNodeIdMapping(),{a:'alpha',b:'b'});
const nodeB=descendants(container).find(el=>el.tagName==='fieldset' &&
  el.children[0]?.textContent==='Element · b');
descendants(nodeB).find(el=>el.tagName==='button' &&
  el.textContent==='Element löschen').click();
assert.deepEqual(form.getNodeIdMapping(),{a:'alpha'});
assert.deepEqual({...remap({a:{x:27,y:41},b:{x:-8,y:3}},form.getNodeIdMapping())},
  {alpha:{x:27,y:41}});
// P2: reusing a renamed source ID must never overwrite its original offset.
const source=JSON.parse(JSON.stringify(sample));
source.nodes[0].id='node_1';
source.edges[0].from='node_1';
const reuseRoot=new Element('main');
const reuseForm=mount(reuseRoot,source);
const oldRow=descendants(reuseRoot).find(el=>el.tagName==='fieldset' &&
  el.children[0]?.textContent==='Element · node_1');
const oldId=descendants(oldRow).find(el=>el.tagName==='label' &&
  el.children[0]?.textContent==='ID').children[1];
oldId.change('alpha');
descendants(reuseRoot).find(el=>el.tagName==='button' && el.textContent==='+ Element').click();
assert.deepEqual(reuseForm.getValue().nodes.map(node=>node.id),['alpha','b','node_1']);
assert.deepEqual(reuseForm.getNodeIdMapping(),{node_1:'alpha',b:'b'});
assert.deepEqual({...remap({node_1:{x:27,y:41}},reuseForm.getNodeIdMapping())},
  {alpha:{x:27,y:41}});
// Once the native render succeeds, every node is a source node for its new digest.
reuseForm.rebaseNodeIds();
assert.deepEqual(reuseForm.getNodeIdMapping(),{alpha:'alpha',b:'b',node_1:'node_1'});
assert.deepEqual({...remap({alpha:{x:27,y:41},node_1:{x:3,y:7}},reuseForm.getNodeIdMapping())},
  {alpha:{x:27,y:41},node_1:{x:3,y:7}});
// Removing and recreating an ID is also a new node, not the removed source node.
const delRoot=new Element('main');
const delForm=mount(delRoot,source);
const delRow=descendants(delRoot).find(el=>el.tagName==='fieldset' &&
  el.children[0]?.textContent==='Element · node_1');
descendants(delRow).find(el=>el.tagName==='button' && el.textContent==='Element löschen').click();
descendants(delRoot).find(el=>el.tagName==='button' && el.textContent==='+ Element').click();
assert.deepEqual(delForm.getNodeIdMapping(),{b:'b'});
assert.deepEqual({...remap({node_1:{x:27,y:41}},delForm.getNodeIdMapping())},{});
""")


def test_structural_form_actions_restore_keyboard_focus(tmp_path: Path) -> None:
    """Deleting or adding an item must not strand keyboard users on a removed button."""
    run_js(tmp_path, """
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.handlers={}; this.scrollTop=0; this.textContent=''; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=[...items]; }
  addEventListener(name,fn) { this.handlers[name]=fn; }
  setAttribute(key,value) { this[key]=value; }
  focus() { document.activeElement=this; }
  click() { this.focus(); this.handlers.click?.(); }
}
globalThis.document={activeElement:null,createElement(tag){return new Element(tag)}};
const container=new Element('main');
const form=mount(container,sample);
function descendants(root) { return [root,...root.children.flatMap(descendants)]; }
function row(name) { return descendants(container).find(el=>el.tagName==='fieldset' &&
  el.children[0]?.textContent===name); }
function field(name,caption) {
  const label=descendants(row(name)).find(el=>el.tagName==='label' &&
    el.children[0]?.textContent===caption);
  return label.children[1];
}
function button(parent,caption) {
  return descendants(parent).find(el=>el.tagName==='button' && el.textContent===caption);
}
const groups=()=>row('Gruppen'), nodes=()=>row('Elemente'), edges=()=>row('Verbindungen');
button(groups(),'+ Gruppe').click();
assert.equal(document.activeElement,field('Gruppe · group_1','Bezeichnung'));
button(row('Gruppe · group_1'),'Gruppe löschen').click();
assert.equal(document.activeElement,button(groups(),'+ Gruppe'));
button(nodes(),'+ Element').click();
assert.equal(document.activeElement,field('Element · node_1','Titel'));
button(row('Element · node_1'),'Element löschen').click();
assert.equal(document.activeElement,button(nodes(),'+ Element'));
button(edges(),'+ Verbindung').click();
assert.equal(document.activeElement,field('Verbindung · edge_1','Beschriftung'));
button(row('Verbindung · edge_1'),'Verbindung löschen').click();
assert.equal(document.activeElement,button(edges(),'+ Verbindung'));
assert.deepEqual(form.getValue(),sample);
""")


def test_mutated_js_model_is_accepted_by_real_backend(tmp_path: Path) -> None:
    """Round-trip field edits and cascades through the backend contract."""
    import json

    from schauwerk.visual.representation import validate_representation_input

    (tmp_path / "model.mjs").write_text(REPRESENTATION_EDITOR_JS, encoding="utf-8")
    script = r"""
import {changeRepresentation as change,validateRepresentation as validate} from './model.mjs';
const start={schema_version:'schauwerk-representation-input.v1',id:'diagramm',title:'Vorher',
purpose:'Überblick',intent:'process',groups:[{id:'team',label:'Team'}],
nodes:[{id:'one',label:'Erster',kind:'human',group:'team'},
{id:'two',label:'Zweiter',kind:'system',summary:'Status'}],
edges:[{id:'link',from:'one',to:'two',label:'Beziehung',kind:'flow'}],
requirements:{formal_relations:true},requested_formats:['canvas']};
let current=change(start,{type:'rename-node',id:'one',value:'actor'});
current=change(current,{type:'rename-group',id:'team',value:'gruppe'});
current=change(current,{type:'add-node'});
current=change(current,{type:'add-edge'});
current=change(current,{type:'remove-edge',id:'link'});
current.intent='narrative';
current.nodes[1].summary='Geänderter Inhalt';
current.nodes[0].kind='evidence';
current.edges[0].kind='feedback';
current.requirements.rich_text=true;
current.requested_formats=['mermaid','canvas','document'];
console.log(JSON.stringify(validate(current)));
"""
    (tmp_path / "check.mjs").write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["node", str(tmp_path / "check.mjs")],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    backend = validate_representation_input(parsed)
    assert backend["nodes"][0]["id"] == "actor"
    assert backend["nodes"][0]["group"] == "gruppe"
    assert backend["edges"][0]["from"] == "actor"
    assert backend["edges"][0]["kind"] == "feedback"
    assert backend["requirements"]["rich_text"] is True


def test_structured_knowledge_map_native_form_validates_and_preserves_references(tmp_path: Path) -> None:
    run_js(tmp_path, """
const data=JSON.parse(JSON.stringify(sample));
data.intent='knowledge_map';
data.requirements.free_spatial_layout=true;
const normalized=validate(data);
assert.equal(normalized.intent,'knowledge_map');
assert.equal(normalized.requirements.free_spatial_layout,true);
let edited=change(normalized,{type:'rename-node',id:'a',value:'concept_new'});
edited=change(edited,{type:'add-edge'});
edited.edges[1].from='concept_new';
edited.edges[1].to='b';
const accepted=validate(edited);
assert.equal(accepted.edges[0].from,'concept_new');
assert.equal(accepted.edges[1].to,'b');
assert.equal(data.nodes[0].id,'a');
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.handlers={}; this.scrollTop=0; this.textContent=''; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=[...items]; }
  addEventListener(name,fn) { this.handlers[name]=fn; }
  setAttribute(key,value) { this[key]=value; }
}
globalThis.document={createElement(tag){return new Element(tag)}};
const container=new Element('main');
const form=mount(container,normalized);
function descendants(root) { return [root,...root.children.flatMap(descendants)]; }
const intentRow=descendants(container).find(el=>el.tagName==='label' && el.children[0]?.textContent==='Darstellungsabsicht');
const intentSelect=intentRow?.children[1];
assert.ok(intentSelect);
assert.ok(intentSelect.children.some(option=>option.value==='knowledge_map' && option.selected));
assert.equal(form.getValue().intent,'knowledge_map');
""")


def test_composed_product_bundle_exposes_complete_editor_without_extra_asset() -> None:
    """Keep the standalone four-file output compatible with existing deployments."""
    from schauwerk.visual.standalone_editor import EDITOR_ORIGIN, _render_assets

    assets = _render_assets(
        editor_origin=EDITOR_ORIGIN,
        editor_url=f"{EDITOR_ORIGIN}/",
        public_base_path="/schaubild",
    )
    assert set(assets) == {"app.js", "canvas-import.js", "index.html", "styles.css"}
    assert "mountRepresentationEditor" in assets["app.js"]
    assert 'renderRepresentationContentEditor = (representation)' in assets["app.js"]
    assert "representationFromContentEditor = ()" in assets["app.js"]
    assert "Schaubild bearbeiten</h2>" in assets["index.html"]
    assert "Struktur, Typen und Zuordnungen bleiben unverändert" not in assets["index.html"]


BROWSER_EDITOR_SMOKE_JS = r"""const until = async (condition, label, attempts = 700) => {
  for (let i=0;i<attempts;i++) {
    if (condition()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(label);
};
function row(legend) {
  return [...document.querySelectorAll("#contentFields fieldset.content-entry")]
    .find(box => box.querySelector(":scope > legend")?.textContent?.trim() === legend);
}
function field(row, caption, selector) {
  const label = [...row.querySelectorAll("label")]
    .find(element => element.querySelector(":scope > span")?.textContent?.trim() === caption);
  if (!label) throw new Error("Field missing: "+caption);
  const control = label.querySelector(selector);
  if (!control) throw new Error("Control missing: "+caption);
  return control;
}
function change(input, value, type="change") {
  input.value = value;
  input.dispatchEvent(new Event(type,{bubbles:true}));
}
function press(box, caption) {
  const button = [...box.querySelectorAll(":scope > button")]
    .find(element => element.textContent?.trim() === caption);
  if (!button) throw new Error("Button missing: "+caption);
  button.click();
}
function saved() {
  for (const key of Object.keys(localStorage)) {
    try {
      const record=JSON.parse(localStorage.getItem(key));
      if (record?.representation?.schema_version === "schauwerk-representation-input.v1"
        && record.representation.id === "e2e_demo") return record.representation;
    } catch (_) {}
  }
  return null;
}
function assertSaved(model) {
  if (!model || model.groups.length !== 2 || model.nodes.length !== 3 ||
      model.edges.length !== 2) throw new Error("Structural mutations did not autosave");
  if (!model.groups.some(group=>group.id==="team")) throw new Error("Group ID lost");
  if (!model.nodes.some(node=>node.id==="alpha" && node.group==="team")) {
    throw new Error("Renamed node/group references lost");
  }
  if (!model.nodes.some(node=>node.id==="node_1" && node.kind==="risk")) {
    throw new Error("Node creation and kind edit lost");
  }
  if (!model.edges.some(edge=>edge.id==="edge_1" &&
    edge.kind==="feedback" && edge.from==="alpha" && edge.to==="node_1")) {
      throw new Error("Edge creation, kind or reattachment lost");
  }
}
try {
  const isReload = sessionStorage.getItem("schauwerk-editor-e2e-reload") === "1";
  const isRecoveryReload = sessionStorage.getItem("schauwerk-editor-e2e-recovery") === "1";
  if (isRecoveryReload) {
    sessionStorage.removeItem("schauwerk-editor-e2e-recovery");
    const oldDigest = sessionStorage.getItem("schauwerk-editor-e2e-old-digest");
    sessionStorage.removeItem("schauwerk-editor-e2e-old-digest");
    await until(()=>!document.querySelector("#restoreButton").hidden,
      "Stored failed edit was not available after reload",1200);
    document.querySelector("#restoreButton").click();
    const frameDigest=()=>document.querySelector("#editorFrame")
      ?.contentDocument?.querySelector("#nativeDiagram")?.dataset?.inputDigest;
    await until(()=>Boolean(frameDigest()) && frameDigest() !== oldDigest,
      "Failed rename recovery did not render",1200);
    const newDigest=frameDigest();
    const positions=JSON.parse(localStorage.getItem(
      "schauwerk.native-viewer.layout.v1."+newDigest)||"{}");
    if (positions.alpha?.x!==37 || positions.alpha?.y!==19 ||
        positions.b?.x!==6 || positions.b?.y!==-13 || positions.a) {
      throw new Error("Recovered local draft lost renamed-node displacement");
    }
    assertSaved(saved());
    document.documentElement.dataset.fullEditorBrowser = "pass";
  } else if (isReload) {
    sessionStorage.removeItem("schauwerk-editor-e2e-reload");
    await until(()=>!document.querySelector("#restoreButton").hidden,"restore button missing");
    document.querySelector("#restoreButton").click();
    await until(()=>!document.querySelector("#workspace").hidden &&
      document.querySelector("#editorFrame")?.src?.includes("/native/") &&
      !document.querySelector("#contentEditButton").hidden,"restored editor not ready");
    assertSaved(saved());
    const restoredMenu=document.querySelector(".workspace-tools-menu");
    restoredMenu.open=true;
    await until(()=>document.querySelector("#contentEditButton").getBoundingClientRect().width>0,
      "Restored editing action not reachable");
    document.querySelector("#contentEditButton").click();
    await until(()=>document.querySelector("#contentDialog").open, "restored editor form missing");
    if (!row("Element · alpha") || !row("Gruppe · team")) {
      throw new Error("Restored editable structures missing");
    }
    document.documentElement.dataset.fullEditorBrowser = "pass";
  } else {
    const source = {
      schema_version:"schauwerk-representation-input.v1",id:"e2e_demo",
      title:"Diagramm",purpose:"Echte Bearbeitung",intent:"process",
      groups:[{id:"g",label:"Alte Gruppe"}],
      nodes:[{id:"a",label:"Alpha",kind:"concept",group:"g"},
             {id:"b",label:"Beta",kind:"human"}],
      edges:[{id:"ab",from:"a",to:"b",label:"Folgt",kind:"flow"}],
      requirements:{formal_relations:true},requested_formats:["canvas"]
    };
    document.querySelector("#sourceInput").value=JSON.stringify(source);
    document.querySelector("#openPasteButton").click();
    await until(()=>!document.querySelector("#workspace").hidden &&
      document.querySelector("#editorFrame")?.src?.includes("/native/") &&
      !document.querySelector("#contentEditButton").hidden,"canonical edit action not ready");
    const toolsMenu=document.querySelector(".workspace-tools-menu");
    toolsMenu.open=true;
    await until(()=>document.querySelector("#contentEditButton").getBoundingClientRect().width>0,
      "Editing action not reachable in Tools");
    document.querySelector("#contentEditButton").click();
    const dialog=document.querySelector("#contentDialog");
    await until(()=>dialog.open && row("Gruppe · g"),"canonical edit form missing");
    const frameDigest=()=>document.querySelector("#editorFrame")
      ?.contentDocument?.querySelector("#nativeDiagram")?.dataset?.inputDigest;
    await until(()=>Boolean(frameDigest()),"Native viewer old digest missing",1200);
    const oldDigest=frameDigest();
    localStorage.setItem("schauwerk.native-viewer.layout.v1."+oldDigest,
      JSON.stringify({a:{x:37,y:19},b:{x:6,y:-13}}));
    const bounds=dialog.getBoundingClientRect();
    if (bounds.left < -2 || bounds.right > innerWidth+2) {
      throw new Error("Edit dialog exceeds viewport: "+JSON.stringify({
        width:innerWidth,left:bounds.left,right:bounds.right
      }));
    }
    change(field(row("Gruppe · g"),"ID","input"),"team");
    change(field(row("Element · a"),"ID","input"),"alpha");
    press(row("Gruppen"),"+ Gruppe");
    if (document.activeElement !== field(row("Gruppe · group_1"),"Bezeichnung","input")) {
      throw new Error("New group label lost keyboard focus");
    }
    press(row("Elemente"),"+ Element");
    if (document.activeElement !== field(row("Element · node_1"),"Titel","input")) {
      throw new Error("New node title lost keyboard focus");
    }
    change(field(row("Element · node_1"),"Typ","select"),"risk");
    press(row("Verbindungen"),"+ Verbindung");
    if (document.activeElement !== field(row("Verbindung · edge_1"),"Beschriftung","input")) {
      throw new Error("New edge label lost keyboard focus");
    }
    const newEdge=row("Verbindung · edge_1");
    change(field(newEdge,"Typ","select"),"feedback");
    change(field(newEdge,"Anfang","select"),"alpha");
    change(field(newEdge,"Ziel","select"),"node_1");
    const retryMode=new URLSearchParams(location.search);
    let originalDraftSetItem = null;
    if (retryMode.has("quota")) {
      originalDraftSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key === "schauwerk.native-schaubild.draft.v1") {
          throw new DOMException("Synthetic full local storage", "QuotaExceededError");
        }
        return originalDraftSetItem.call(this, key, value);
      };
    }
    document.querySelector("#contentSaveButton").click();
    if (retryMode.has("quota")) {
      await until(() => dialog.open &&
        !document.querySelector("#contentSaveButton").disabled &&
        frameDigest() !== oldDigest,
        "Successful render with failed draft write did not leave the editor open", 1200);
      Storage.prototype.setItem = originalDraftSetItem;
      const intermediateDigest = frameDigest();
      const intermediateLayout = JSON.parse(localStorage.getItem(
        "schauwerk.native-viewer.layout.v1." + intermediateDigest) || "{}");
      if (intermediateLayout.alpha?.x !== 37 || intermediateLayout.alpha?.y !== 19) {
        throw new Error("Quota render lost initial manually moved node position");
      }
      change(field(row("Schaubild"), "Titel", "input"), "Nach Quota", "input");
      document.querySelector("#contentSaveButton").click();
      try {
        await until(() => !dialog.open && frameDigest() !== intermediateDigest,
          "Second save after quota did not update native rendering", 1200);
      } catch (error) {
        throw new Error("Quota second save state: " + JSON.stringify({
          dialogOpen: dialog.open,
          disabled: document.querySelector("#contentSaveButton").disabled,
          previousDigest: intermediateDigest, nextDigest: frameDigest(),
          savedTitle: saved()?.title,
          feedback: document.querySelector("#contentDialogFeedback")?.textContent,
          status: document.querySelector("#status")?.textContent,
          titleField: field(row("Schaubild"), "Titel", "input").value,
        }));
      }
      if (saved()?.title !== "Nach Quota") {
        throw new Error("Updated title missing after local quota recovery");
      }
    }
    if (retryMode.has("reload-recovery")) {
      await until(()=>!document.querySelector("#nativeRetryButton").hidden,
        "Recoverable render failure was not observed",1200);
      const draft = Object.keys(localStorage).map(key => {
        try { return JSON.parse(localStorage.getItem(key)); } catch (_) { return null; }
      }).find(item => item?.layoutIdMapping?.nodeIds?.a === "alpha");
      if (draft?.validInputDigest !== oldDigest) {
        throw new Error("Recovery draft lacks exact old-ID mapping");
      }
      sessionStorage.setItem("schauwerk-editor-e2e-old-digest", oldDigest);
      sessionStorage.setItem("schauwerk-editor-e2e-recovery", "1");
      location.reload();
    } else {
    if (retryMode.has("retry") || retryMode.has("reopen") ||
        retryMode.has("resubmit") || retryMode.has("reopen-resubmit")) {
      await until(()=>!document.querySelector("#nativeRetryButton").hidden,
        "Transient renderer failure did not offer retry",1200);
      if (retryMode.has("resubmit")) {
        // Same form, original source IDs: compose must NOT be applied again.
        if (!dialog.open || !row("Element · alpha")) {
          throw new Error("Original edit form did not remain open after failure");
        }
        document.querySelector("#contentSaveButton").click();
      } else {
        dialog.close("cancel");
        if (retryMode.has("reopen") || retryMode.has("reopen-resubmit")) {
          document.querySelector(".workspace-tools-menu").open=true;
          document.querySelector("#contentEditButton").click();
          await until(()=>dialog.open && row("Element · alpha"),
            "Previously renamed node not available after failed render",1200);
          // A remount starts at the pending IDs. Compose old-to-current mapping.
          change(field(row("Element · alpha"),"Titel","input"),"Neue Beschriftung");
          document.querySelector("#contentSaveButton").click();
          if (retryMode.has("reopen-resubmit")) {
            await until(()=>!document.querySelector("#nativeRetryButton").hidden
              && !document.querySelector("#contentSaveButton").disabled,
              "Second failed save did not preserve open form",1200);
            document.querySelector("#contentSaveButton").click();
          }
        } else {
          document.querySelector("#nativeRetryButton").click();
        }
      }
    }
    await until(()=>!dialog.open && saved()?.nodes.length === 3,
      "Native save did not finish",1200);
    assertSaved(saved());
    await until(()=>Boolean(frameDigest()) && frameDigest()!==oldDigest,
      "Native save did not change representation digest",1200);
    const newDigest=frameDigest();
    const positions=JSON.parse(localStorage.getItem(
      "schauwerk.native-viewer.layout.v1."+newDigest)||"{}");
    if (positions.alpha?.x!==37 || positions.alpha?.y!==19 ||
        positions.b?.x!==6 || positions.b?.y!==-13 || positions.a) {
      throw new Error("Dragged node coordinates lost on ID rename");
    }
    const button=document.querySelector("#projectButton");
    button.click();
    const dl=document.querySelector("#downloadLink");
    if (dl.hidden || !dl.download.endsWith(".schauwerk.json")) {
      throw new Error("Editable project export missing");
    }
    sessionStorage.setItem("schauwerk-editor-e2e-reload","1");
    location.reload();
    }
  }
} catch (error) {
  document.documentElement.dataset.fullEditorBrowser = "fail";
  document.documentElement.dataset.fullEditorError = String(error?.stack||error);
}
"""


@pytest.mark.parametrize(
    ("width", "height", "retry_mode"),
    [(1280, 900, ""), (768, 1024, ""), (390, 844, ""),
     (1280, 900, "retry"), (1280, 900, "reopen"),
     (1280, 900, "resubmit"), (1280, 900, "reopen-resubmit"),
     (1280, 900, "reload-recovery"), (1280, 900, "quota")],
)
def test_canonical_editor_browser_reopen_structure_and_export(
    tmp_path: Path, width: int, height: int, retry_mode: str
) -> None:
    """End-to-end local Chrome: edit, persist, export and reload a canonical diagram."""
    import os
    import shutil
    import subprocess
    import threading
    from functools import partial
    from http import HTTPStatus
    from http.server import ThreadingHTTPServer

    from schauwerk.visual.standalone_editor import _EditorRequestHandler, build_standalone_editor

    chrome = (
        os.environ.get("CHROME_BIN")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if not chrome:
        if os.environ.get("CI"):
            pytest.fail("Chrome/Chromium required for canonical editor browser test in CI")
        pytest.skip("Chrome/Chromium unavailable")

    output = tmp_path / "editor"
    build_standalone_editor(output)
    (output / "canonical-full-editor-browser.js").write_text(
        BROWSER_EDITOR_SMOKE_JS,
        encoding="utf-8",
    )
    index_path = output / "index.html"
    index = index_path.read_text(encoding="utf-8")
    assert index.count("</body>") == 1
    index_path.write_text(
        index.replace(
            "</body>",
            '<script type="module" src="canonical-full-editor-browser.js"></script></body>',
        ),
        encoding="utf-8",
    )

    class FailSecondNativeRender(_EditorRequestHandler):
        post_count = 0

        def do_POST(self) -> None:  # noqa: N802
            cls = type(self)
            if self.path == "/api/native-viewer":
                cls.post_count += 1
                if cls.post_count == 2 or (
                    retry_mode == "reopen-resubmit" and cls.post_count == 3
                ):
                    size = int(self.headers.get("Content-Length", "0"))
                    self.rfile.read(size)
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "synthetic transient native renderer interruption"},
                    )
                    return
            super().do_POST()

    handler = (
        FailSecondNativeRender if retry_mode and retry_mode != "quota"
        else _EditorRequestHandler
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(handler, directory=str(output)),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        profile = tmp_path / "chrome-profile"
        command = [
            chrome,
            "--headless=new",
            "--no-first-run",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--run-all-compositor-stages-before-draw",
            f"--window-size={width},{height}",
            "--virtual-time-budget=25000",
            f"--user-data-dir={profile}",
            "--dump-dom",
            f"http://127.0.0.1:{server.server_address[1]}/"
            + (f"?{retry_mode}=1" if retry_mode else ""),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=50)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
    assert result.returncode == 0, result.stderr[-4000:]
    if 'data-full-editor-browser="pass"' not in result.stdout:
        import html
        import re

        match = re.search(r'data-full-editor-error="([^"]*)"', result.stdout)
        if match:
            pytest.fail(html.unescape(match.group(1)))
    assert 'data-full-editor-browser="pass"' in result.stdout, (
        result.stdout[-3000:] + "\n" + result.stderr[-2500:]
    )


@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844)])
def test_native_knowledge_map_browser_roundtrip(
    tmp_path: Path, width: int, height: int,
) -> None:
    """Actual native Knowledge Map import, rename, add, save, export and reload."""
    import json
    import os
    import shutil
    import threading
    import time
    from functools import partial
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen

    from schauwerk.visual.standalone_editor import (
        _EditorRequestHandler,
        build_standalone_editor,
    )

    if os.environ.get("CI") and __import__("sys").version_info[:2] != (3, 12):
        pytest.skip("browser native Knowledge Map gate is covered in Python 3.12 CI")

    chrome = os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        if os.environ.get("CI"):
            pytest.fail("Chrome required for native Knowledge Map browser cutover in CI")
        pytest.skip("Chrome unavailable")

    ws = pytest.importorskip("websockets.sync.client")
    source = BROWSER_EDITOR_SMOKE_JS
    assert source.count('intent:"process",') == 1
    source = source.replace('intent:"process",', 'intent:"knowledge_map",', 1)
    # After the structural edit, exercise the same rendered SVG export route.
    marker = """    const button=document.querySelector("#projectButton");
    button.click();"""
    replacement = """    const svgButton=document.querySelector('[data-export="svg"]');
    if (!svgButton || svgButton.hidden) throw new Error("Native SVG export unavailable");
    svgButton.click();
    await until(() => {
      const link = document.querySelector("#downloadLink");
      return !link.hidden && link.download.endsWith(".svg");
    }, "Native Knowledge Map SVG export failed", 1200);
    const button=document.querySelector("#projectButton");
    button.click();"""
    assert source.count(marker) == 1
    source = source.replace(marker, replacement, 1)
    output = tmp_path / "editor"
    build_standalone_editor(output)
    (output / "knowledge-map-roundtrip.js").write_text(source, encoding="utf-8")
    index_path = output / "index.html"
    markup = index_path.read_text(encoding="utf-8")
    assert markup.count("</body>") == 1
    index_path.write_text(
        markup.replace(
            "</body>",
            '<script type="module" src="knowledge-map-roundtrip.js"></script></body>',
            1,
        ),
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(_EditorRequestHandler, directory=str(output)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome-profile"
    browser = subprocess.Popen(
        [
            chrome, "--headless=new", "--no-first-run", "--no-sandbox",
            "--disable-gpu", "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--remote-allow-origins=http://localhost",
            "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        page = None
        for _ in range(130):
            if browser.poll() is not None:
                pytest.fail("Chrome quit before DevTools startup")
            try:
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                    page = next(
                        (item for item in json.load(response) if item.get("type") == "page"),
                        None,
                    )
                if page:
                    break
            except (OSError, TimeoutError, ValueError, IndexError):
                pass
            time.sleep(0.12)
        assert page is not None, "Chrome CDP startup failed"
        with ws.connect(page["webSocketDebuggerUrl"], origin="http://localhost") as client:
            current_id = 0

            def cdp(method: str, params: dict | None = None) -> dict:
                nonlocal current_id
                current_id += 1
                expected = current_id
                client.send(json.dumps({
                    "id": expected, "method": method, "params": params or {},
                }))
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    payload = json.loads(client.recv(timeout=max(0.1, deadline-time.monotonic())))
                    if payload.get("id") == expected:
                        assert "error" not in payload, payload.get("error")
                        return payload.get("result", {})
                raise AssertionError(f"Chrome CDP timeout on {method}")

            cdp("Page.enable")
            cdp("Runtime.enable")
            cdp("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height,
                "deviceScaleFactor": 1, "mobile": width < 600,
            })
            cdp("Page.navigate", {
                "url": f"http://127.0.0.1:{server.server_address[1]}/",
            })
            for _ in range(240):
                response = cdp("Runtime.evaluate", {
                    "expression": (
                        "({result:document.documentElement.dataset.fullEditorBrowser||'',"
                        "error:document.documentElement.dataset.fullEditorError||'',"
                        "view:document.querySelector('#editorFrame')?.getAttribute('src')||''})"
                    ),
                    "returnByValue": True,
                })
                readback = response.get("result", {}).get("value", {})
                if readback.get("result") == "fail":
                    pytest.fail("Knowledge Map E2E: " + str(readback.get("error")))
                if readback.get("result") == "pass":
                    assert "/native/" in readback.get("view", ""), readback
                    break
                time.sleep(0.12)
            else:
                pytest.fail("Native Knowledge Map browser E2E timed out: " + str(readback))
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=6)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=6)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
