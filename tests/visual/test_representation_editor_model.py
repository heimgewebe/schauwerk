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
        "import {changeRepresentation as change,validateRepresentation as validate,mountRepresentationEditor as mount} from './model.mjs';\n"
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


def test_unsupported_native_knowledge_map_requires_canvas(tmp_path: Path) -> None:
    run_js(tmp_path, """
const data=JSON.parse(JSON.stringify(sample));
data.intent='knowledge_map';
assert.throws(()=>validate(data),/JSON Canvas/);
""")
