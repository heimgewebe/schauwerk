"""Live and saved JSON Canvas smart-edge routing contract tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from schauwerk.resources.native_viewer.assets import ASSETS
from schauwerk.visual.native_canvas_smart_router import route_edge
from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.native_document import (
    NativeDocumentError,
    editing_document_to_json_canvas,
    json_canvas_to_editing_document,
    normalize_editing_document,
    validate_json_canvas,
)

SVG = "{http://www.w3.org/2000/svg}"


def canvas(*, routing: str | None = "smart", obstacle: bool = True) -> dict:
    nodes = [
        {"id": "start", "type": "text", "x": 0, "y": 0, "width": 100,
         "height": 80, "text": "Start"},
        {"id": "end", "type": "text", "x": 400, "y": 0, "width": 100,
         "height": 80, "text": "Ende"},
    ]
    if obstacle:
        nodes.append({"id": "blocker", "type": "text", "x": 200, "y": 0,
                      "width": 100, "height": 80, "text": "Hindernis"})
    source = {
        "nodes": nodes,
        "edges": [{"id": "e", "fromNode": "start", "toNode": "end",
                   "label": "Eine Beziehung", "toEnd": "arrow"}],
    }
    if routing is not None:
        source["schauwerk"] = {"edgeRouting": routing}
    return source


def render(source: dict) -> ET.Element:
    return ET.fromstring(render_native_editing_document(
        json_canvas_to_editing_document(source)
    ))


def edge_group(root: ET.Element) -> ET.Element:
    return next(g for g in root.iter(SVG + "g")
                if g.get("data-source-kind") == "edge")


def path_data(root: ET.Element) -> str:
    path = edge_group(root).find(SVG + "path")
    assert path is not None
    return str(path.get("d"))


def test_legacy_canvas_routes_are_not_migrated_silently() -> None:
    legacy = render(canvas(routing=None))
    simple = render(canvas(routing="simple"))
    smart = render(canvas(routing="smart"))
    assert legacy.get("data-edge-routing") is None
    assert simple.get("data-edge-routing") is None
    assert smart.get("data-edge-routing") == "smart"
    assert path_data(legacy) == path_data(simple)
    assert edge_group(legacy).get("data-route") != "canvas-smart"
    assert edge_group(smart).get("data-route") == "canvas-smart"
    assert path_data(smart) != path_data(simple)


def test_smart_render_avoids_blocking_node_and_keeps_label_visible() -> None:
    source = canvas()
    rendered = render(source)
    group = edge_group(rendered)
    original_nodes = source["nodes"]
    expected = route_edge(original_nodes[0], original_nodes[1], original_nodes)
    assert expected is not None
    assert path_data(rendered) == expected.path
    assert group.get("data-routing-conflict") is None
    assert group.get("data-canonical-stroke")
    label = next(r for r in group.findall(SVG + "rect")
                 if float(r.get("width", "0")) > 0)
    label_box = (
        float(label.get("x", "0")), float(label.get("y", "0")),
        float(label.get("x", "0")) + float(label.get("width", "0")),
        float(label.get("y", "0")) + float(label.get("height", "0")),
    )
    b = source["nodes"][2]
    obstacle_box = (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])
    assert not (
        label_box[0] < obstacle_box[2] and label_box[2] > obstacle_box[0]
        and label_box[1] < obstacle_box[3] and label_box[3] > obstacle_box[1]
    )


def test_manual_ports_remain_respected_through_source_roundtrip() -> None:
    source = canvas()
    source["edges"][0]["fromSide"] = "top"
    source["edges"][0]["toSide"] = "bottom"
    doc = json_canvas_to_editing_document(source)
    doc["edges"][0]["label"] = "Bearbeitet"
    refreshed = normalize_editing_document(doc)
    roundtrip = editing_document_to_json_canvas(refreshed)
    assert roundtrip["schauwerk"] == {"edgeRouting": "smart"}
    assert roundtrip["edges"][0]["fromSide"] == "top"
    assert roundtrip["edges"][0]["toSide"] == "bottom"
    result = edge_group(render(roundtrip))
    assert result.get("data-route") == "canvas-smart"
    assert result.get("data-routing-conflict") is None
    assert result.find(SVG + "title").text == "Bearbeitet"


def test_routing_mode_rejects_invalid_extension_values() -> None:
    for invalid in ("fast", None, False, 2, ["smart"], {"mode": "smart"}):
        source = canvas()
        source["schauwerk"]["edgeRouting"] = invalid
        with pytest.raises(NativeDocumentError):
            validate_json_canvas(source)
    source = canvas()
    source["schauwerk"] = "smart"
    with pytest.raises(NativeDocumentError):
        validate_json_canvas(source)


def test_unresolvable_smart_path_is_marked_as_conflict() -> None:
    source = canvas()
    source["nodes"].append({
        "id": "wall", "type": "text", "x": -200, "y": -200,
        "width": 900, "height": 500, "text": "Blockierter Bereich",
    })
    result = edge_group(render(source))
    assert result.get("data-route") == "canvas-smart-conflict"
    assert result.get("data-routing-conflict") == "true"
    path = result.find(SVG + "path")
    assert path is not None and path.get("stroke-dasharray") == "6 4"
    assert "Kein hindernisfreier Weg" in (result.find(SVG + "title").text or "")


def test_browser_router_resource_is_bundled_without_external_dependency() -> None:
    assert "smart-router.js" in ASSETS
    assert "export function smartEdgeGeometry(" in ASSETS["smart-router.js"]
    assert 'import { smartEdgeGeometry } from "./smart-router.js";' in ASSETS["app.js"]
    assert "documentSnapshot()" in ASSETS["app.js"]
    assert 'id="smartRouting"' in ASSETS["styles.css"] or 'id="smartRouting"' in __import__(
        "schauwerk.resources.native_viewer.assets",
        fromlist=["INDEX_HTML"],
    ).INDEX_HTML


def test_javascript_router_tracks_python_geometry_on_fixture(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not available for standalone JavaScript geometry check")
    script = tmp_path / "smart-router.mjs"
    script.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    a, b, blocker = canvas()["nodes"]
    runner = tmp_path / "check.mjs"
    runner.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps([a, b, blocker])};\n"
        "console.log(JSON.stringify(smartEdgeGeometry(nodes[0],nodes[1],nodes)));\n",
        encoding="utf-8",
    )
    outcome = subprocess.run([node, str(runner)], capture_output=True,
                             text=True, timeout=10, check=True)
    actual = json.loads(outcome.stdout)
    expected = route_edge(a, b, [a, b, blocker])
    assert actual is not None and expected is not None
    assert actual["fromSide"] == expected.from_side
    assert actual["toSide"] == expected.to_side
    assert actual["collisionFree"] is True
    assert actual["path"] == expected.path


def test_reciprocal_smart_rails_match_browser_router(tmp_path: Path) -> None:
    """Both geometric kernels keep opposing edge strokes independently selectable."""
    node_runtime = shutil.which("node")
    if not node_runtime:
        pytest.skip("Node.js unavailable for Python/JavaScript geometry parity")
    a = {"id": "a", "type": "text", "x": 40, "y": 80,
         "width": 220, "height": 120, "text": "Quelle"}
    b = {"id": "b", "type": "text", "x": 590, "y": 80,
         "width": 220, "height": 120, "text": "Ziel"}
    blocker = {"id": "middle", "type": "text", "x": 310, "y": 50,
               "width": 200, "height": 200, "text": "Hindernis"}
    nodes = [a, b, blocker]
    module = tmp_path / "smart-router.mjs"
    module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    check = tmp_path / "check.mjs"
    check.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps(nodes)};\n"
        'console.log(JSON.stringify([\n'
        '  smartEdgeGeometry(nodes[0], nodes[1], nodes, {lane:-9,maxLane:9}),\n'
        '  smartEdgeGeometry(nodes[1], nodes[0], nodes, {lane:9,maxLane:9}),\n'
        ']));\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [node_runtime, str(check)], capture_output=True,
        text=True, timeout=12, check=True,
    )
    js = json.loads(result.stdout)
    py = [route_edge(a, b, nodes, lane=-9, max_lane=9),
          route_edge(b, a, nodes, lane=9, max_lane=9)]
    assert all(r is not None and r.collision_free for r in py)
    assert all(r is not None and r["collisionFree"] for r in js)
    for python_route, browser_route in zip(py, js):
        assert browser_route["path"] == python_route.path
        assert browser_route["labelY"] == pytest.approx(python_route.label_y)
        assert browser_route["fromSide"] == python_route.from_side
        assert browser_route["toSide"] == python_route.to_side
    assert abs(py[0].label_y - py[1].label_y) >= 22.0


def test_relation_direction_and_type_survive_canvas_and_svg_roundtrip() -> None:
    source = canvas()
    edge = source["edges"][0]
    edge["fromEnd"] = "arrow"
    edge["toEnd"] = "none"
    edge["schauwerk"] = {"kind": "association"}
    document = json_canvas_to_editing_document(source)
    exported = editing_document_to_json_canvas(normalize_editing_document(document))
    assert exported["edges"] == source["edges"]
    assert exported["schauwerk"]["edgeRouting"] == "smart"
    rendered = edge_group(render(exported))
    assert rendered.get("data-relation-kind") == "association"
    assert rendered.get("data-route") == "canvas-smart"
    path = rendered.find(SVG + "path")
    assert path is not None
    assert path.get("marker-start", "").startswith("url(")
    assert path.get("marker-end") is None
    assert path.get("stroke-dasharray") == "3 5"

    edge["schauwerk"]["kind"] = "feedback"
    feedback = edge_group(render(source))
    assert feedback.get("data-relation-kind") == "feedback"
    assert feedback.find(SVG + "path").get("stroke-dasharray") == "10 5"


def test_relation_kind_validation_rejects_unsupported_values() -> None:
    for kind in ("unknown", [], None, 3, False):
        source = canvas()
        source["edges"][0]["schauwerk"] = {"kind": kind}
        with pytest.raises(NativeDocumentError):
            validate_json_canvas(source)
    source = canvas()
    source["edges"][0]["schauwerk"] = "association"
    with pytest.raises(NativeDocumentError):
        validate_json_canvas(source)
    source = canvas()
    source["edges"][0]["schauwerk"] = {"kind": "association", "future": "preserved"}
    normalized = validate_json_canvas(source)
    assert normalized["edges"][0]["schauwerk"]["future"] == "preserved"


def test_browser_router_rejects_endpoint_stub_penetration(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable")
    module = tmp_path / "smart-router.mjs"
    module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    a = {"id": "a", "type": "text", "x": 0, "y": 0, "width": 100, "height": 80}
    b = {"id": "b", "type": "text", "x": 10, "y": 0, "width": 100, "height": 80}
    check = tmp_path / "check.mjs"
    check.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps([a, b])};\n"
        'const sidePairs = [["right", "right"], ["left", "left"]];\n'
        'console.log(JSON.stringify(sidePairs.map(([fromSide, toSide]) => '
        'smartEdgeGeometry(nodes[0], nodes[1], nodes, {fromSide, toSide}))));\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(check)], capture_output=True, text=True, timeout=12, check=True,
    )
    assert json.loads(result.stdout) == [None, None]
    assert route_edge(a, b, [a, b], from_side="right", to_side="right") is None
    assert route_edge(a, b, [a, b], from_side="left", to_side="left") is None


def test_conflict_overlay_keeps_canonical_relation_dash_for_recovery(
    tmp_path: Path,
) -> None:
    source = canvas()
    source["nodes"].append({
        "id": "wall", "type": "text", "x": -200, "y": -200,
        "width": 900, "height": 500, "text": "Unpassierbar",
    })
    for kind, expected in (
        ("flow", ""), ("association", "3 5"), ("feedback", "10 5"),
    ):
        source["edges"][0]["schauwerk"] = {"kind": kind}
        group = edge_group(render(source))
        assert group.get("data-route") == "canvas-smart-conflict"
        assert group.get("data-canonical-dash") == expected
        path = group.find(SVG + "path")
        assert path is not None
        assert path.get("stroke-dasharray") == "6 4"

    # Exercise the real viewer recovery function with the canonical dash
    # values recorded on the SVG. This is not a rewritten JS implementation.
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for native viewer conflict recovery")
    app = ASSETS["app.js"]
    start = app.index("function placeLiveEdgeConflict(")
    end = app.index("function relocateLiveEdgeLabels(", start)
    script = tmp_path / "recover.mjs"
    script.write_text(app[start:end] + r"""
for (const dash of ["", "3 5", "10 5"]) {
  const attrs = {"stroke": "#c2410c", "stroke-dasharray": "6 4"};
  const edgeState = {
    element: {
      dataset: {routingConflict: "true"},
      removeAttribute() { delete this.dataset.routingConflict; },
    },
    path: {
      setAttribute(key, value) { attrs[key] = value; },
      removeAttribute(key) { delete attrs[key]; },
    },
    originalStroke: "#456789",
    originalDash: dash,
  };
  placeLiveEdgeConflict(edgeState, false);
  if (attrs.stroke !== "#456789" ||
      (attrs["stroke-dasharray"] || "") !== dash ||
      edgeState.element.dataset.routingConflict) {
    throw new Error("Original relationship style not restored: " + dash);
  }
}
""", encoding="utf-8")
    subprocess.run([node, str(script)], capture_output=True,
                   text=True, timeout=10, check=True)


def test_dense_drag_preview_has_bounded_work_and_lossless_cancel(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for dense live drag benchmark")
    app = ASSETS["app.js"]
    start = app.index("function rollbackSmartDragPreview(")
    end = app.index("function constrainBoundsOffset(", start)
    # Execute the exact deployed functions, not a hand-copied port.
    program = r"""
const MAX_SYNC_SMART_DRAG_NODES=32;
const MAX_SYNC_SMART_DRAG_EDGES=24;
const MAX_SYNC_SMART_DRAG_INCIDENT=8;
const documentMode=true;
let bulkEdgeUpdate=false, certifiedRoutes=0, previewRoutes=0;
const liveNodes=Array.from({length:128},(_,i)=>({
  id:"node"+i,x:i===0?9:i*10,y:0,width:90,height:70,type:"text"
}));
const nodeModelsAtLiveCoordinates=()=>liveNodes;
const routingMode=()=> "smart";
const lastRouteObstacles=new Map([["node0",[-24,-24,114,94]]]);
const svg={viewBox:{baseVal:{width:2500,height:1200}}};
const edges=new Map(), incidentEdges=new Map();
const handleLayer=null;
let relabelCalls=0;
const relocateLiveEdgeLabels=()=>{relabelCalls++};
const refreshConnectionHandles=()=>{};
const updateEdgeGeometry=()=>{certifiedRoutes++;};
const liveEdgeGeometry=(source,target)=>{
  previewRoutes++;
  return {
    path:"M "+source.x+" 0 L "+target.x+" 0",labelX:5,labelY:8
  };
};
let gesture={
  kind:"drag",sourceId:"node0",rollbackOffset:{x:0,y:0},moved:true
};
const setNodeOffset=()=>{liveNodes[0].x=0;};
const applyNodeTransform=()=>{
  if(!bulkEdgeUpdate)throw Error("Unexpected costly rollback");
};
function pathNode(){
  const attrs=new Map([
    ["d","M 0 0 L 12 10"],["stroke","#112233"],
    ["stroke-dasharray","3 5"]
  ]);
  return {
    getAttribute(k){return attrs.has(k)?attrs.get(k):null;},
    setAttribute(k,v){attrs.set(k,String(v));},
    removeAttribute(k){attrs.delete(k);}
  };
}
function elementNode(){
  return {
    dataset:{routingConflict:"true"},
    removeAttribute(k){
      if(k==="data-routing-conflict")delete this.dataset.routingConflict;
      if(k==="data-routing-pending")delete this.dataset.routingPending;
    }
  };
}
for(let i=0;i<256;i++){
  const id="edge"+i;
  edges.set(id,{
    from:"node0",to:"node"+(1+i%127),
    routeBounds:[-10,-10,170,170],
    fromSide:null,toSide:null,lane:0,
    path:pathNode(),hitPath:pathNode(),element:elementNode(),
    originalStroke:"#112233",naturalLabelX:1,naturalLabelY:2
  });
}
incidentEdges.set("node0",new Set(edges.keys()));
""" + app[start:end] + r"""
const start=performance.now();
updateIncidentEdges("node0");
updateIncidentEdges("node0");
const elapsed=performance.now()-start;
if(certifiedRoutes!==0)throw Error("Dense drag ran costly visibility searches");
if(previewRoutes!==512)throw Error("Missing cheap incident previews");
if(gesture.previewOriginals?.size!==256)
  throw Error("Incorrect drag rollback preimages");
for(const edge of edges.values()){
  if(edge.element.dataset.routingPending!=="true")
    throw Error("Uncertified edge not visibly marked as pending");
  if(!edge.path.getAttribute("d").startsWith("M 9"))
    throw Error("Preview did not follow dragged node");
}
rollbackDragNode(gesture);
for(const edge of edges.values()){
  if(edge.path.getAttribute("d")!=="M 0 0 L 12 10")
    throw Error("Cancel lost original edge");
  if(edge.element.dataset.routingPending!==undefined)
    throw Error("Cancel retained pending marker");
  if(edge.element.dataset.routingConflict!=="true")
    throw Error("Cancel discarded original routing state");
  if(edge.naturalLabelX!==1 || edge.naturalLabelY!==2)
    throw Error("Cancel lost label location");
}
if(elapsed>1200)throw Error("Dense drag preview blocked input for "+elapsed+"ms");
console.log(JSON.stringify({
  nodes:liveNodes.length,edges:edges.size,updates:2,
  certifiedRoutes,previewRoutes,elapsedMs:Math.round(elapsed),rollback:true
}));
"""
    path = tmp_path / "dense-smart-drag.mjs"
    path.write_text(program, encoding="utf-8")
    result = subprocess.run(
        [node, str(path)], capture_output=True, text=True,
        timeout=18, check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["edges"] == 256
    assert evidence["nodes"] == 128
    assert evidence["certifiedRoutes"] == 0
    assert evidence["rollback"] is True


def test_standalone_smart_deferred_routes_finish_after_drag(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for standalone routing completion")
    app = ASSETS["app.js"]
    begin = app.index("function applyAllNodeTransforms(")
    startup = app[begin:app.index("function nodeBoundsInSvg(", begin)]
    begin = app.index("function finishPendingStandaloneSmartRoutes(")
    completion = app[begin:app.index("function rollbackSmartDragPreview(", begin)]
    harness = r"""
const documentMode=true, overrides={};
const documentOffsetBudget=20000000;
let bulkEdgeUpdate=false, pendingSmartRouteGeneration=0, gesture=null;
let routed=0, status="", relabel=0;
const nodes=new Map(Array.from({length:33},(_,i)=>[
  "node"+i,{id:"node"+i,x:i*30,y:i*14,width:100,height:70}
]));
const edges=new Map();
function attrs(){
  const m=new Map([["d","M 0 0 L 30 30"]]);
  return {
    getAttribute:k=>m.get(k)||null,
    setAttribute:(k,v)=>m.set(k,String(v)),
    removeAttribute:k=>m.delete(k)
  };
}
for(let i=0;i<33;i++){
  edges.set("e"+i,{
    path:attrs(),hitPath:attrs(),basePath:"M 0 0 L 30 30",
    baseLabelX:1,baseLabelY:2,naturalLabelX:3,naturalLabelY:4,
    route:"canvas-smart",
    element:{
      dataset:{},
      removeAttribute(k){
        if(k==="data-routing-pending")delete this.dataset.routingPending;
      }
    }
  });
}
const lastRouteObstacles=new Map();
const nodeOffset=()=>({x:0,y:0});
const applyNodeTransform=()=>{};
const nodeModelsAtLiveCoordinates=()=>[...nodes.values()];
const resetEdgeLabel=()=>{};
const placeLiveEdgeConflict=e=>{
  e.element.removeAttribute("data-routing-pending");
};
const relocateLiveEdgeLabels=()=>{relabel++;};
let expanded=0;
const expandSmartCanvasToFitRoutes=()=>{expanded++;return true;};
const routingMode=()=> "smart";
const setStatus=s=>{status=s;};
const updateEdgeGeometry=id=>{
  routed++;
  const edge=edges.get(id);
  edge.element.removeAttribute("data-routing-pending");
  edge.path.setAttribute("d","M 5 5 L 10 10");
};
""" + startup + completion + r"""
applyAllNodeTransforms();
if(routed!==0)throw Error("Initial canonical routes were recomputed");
for(const edge of edges.values()){
  if(edge.path.getAttribute("d")!=="M 0 0 L 30 30")
    throw Error("Original certified SVG was lost");
  edge.element.dataset.routingPending="true";
}
gesture={kind:"drag"};
finishPendingStandaloneSmartRoutes();
await new Promise(resolve=>setTimeout(resolve,35));
if(routed!==0)throw Error("Deferred work blocked active drag");
gesture=null;
const deadline=Date.now()+2000;
while(routed<33&&Date.now()<deadline)
  await new Promise(resolve=>setTimeout(resolve,10));
if(routed!==33)throw Error("Unverified routes were not completed: "+routed);
if([...edges.values()].some(e=>e.element.dataset.routingPending==="true"))
  throw Error("Preview paths survived the final certified pass");
if(!status.includes("aktualisiert"))throw Error("Final route status absent");
console.log(JSON.stringify({
  nodes:nodes.size,edges:edges.size,certifiedAtStartup:0,
  completed:routed,unverifiedAfterRelease:0,asyncGesturePause:true,
  boundsExpanded:expanded===1
}));
"""
    path = tmp_path / "standalone-deferred.mjs"
    path.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        [node, str(path)], capture_output=True, text=True,
        timeout=15, check=True,
    )
    proof = json.loads(result.stdout)
    assert proof["certifiedAtStartup"] == 0
    assert proof["completed"] == 33
    assert proof["unverifiedAfterRelease"] == 0
    assert proof["asyncGesturePause"] is True
    assert proof["boundsExpanded"] is True


def test_nonincident_smart_detours_expand_export_viewbox_without_zoom_jump(
    tmp_path: Path,
) -> None:
    """A nonincident reroute beyond the old SVG cannot be clipped in exports."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for exact native viewer SVG bounds check")
    app = ASSETS["app.js"]
    start = app.index("function expandSmartCanvasToFitRoutes(")
    end = app.index("function constrainBoundsOffset(", start)
    program = r"""
const documentMode = true;
const routingMode = () => "smart";
const nodes = new Map();
const edges = new Map([["notIncident", {
  routeBounds: [50, -92.01, 480, 140],
  labelRect: null,
}]]);
const old = {x:-88, y:-88, width:676, height:256};
const attributes = new Map();
const svg = {
  viewBox: {baseVal: {...old}},
  setAttribute(key, value) {
    attributes.set(key, value);
    if (key === "viewBox") {
      const [x, y, width, height] = value.split(" ").map(Number);
      this.viewBox.baseVal = {x, y, width, height};
    }
  },
};
let view = {x:100, y:80, scale:2}, applyCount = 0;
const applyView = () => {applyCount++};
const nodeBoundsInSvg = () => {throw Error("no labels")};
""" + app[start:end] + r"""
const beforeX = view.x + (150 - old.x) * view.scale;
const beforeY = view.y + (0 - old.y) * view.scale;
if (!expandSmartCanvasToFitRoutes()) throw Error("Old edge still clipped");
const expanded = svg.viewBox.baseVal;
if (expanded.y > -116) throw Error("Rerouted edge not fully in export viewBox");
if (expanded.x > old.x || expanded.x + expanded.width < old.x + old.width)
  throw Error("SVG bounds lost old diagram");
const afterX = view.x + (150 - expanded.x) * view.scale;
const afterY = view.y + (0 - expanded.y) * view.scale;
if (Math.abs(afterX - beforeX) > 1e-6 ||
    Math.abs(afterY - beforeY) > 1e-6 || view.scale !== 2)
  throw Error("Expanding the SVG moved or zoomed the original diagram");
if (attributes.get("height") !== String(expanded.height))
  throw Error("Export SVG intrinsic height does not match viewBox");
if (expandSmartCanvasToFitRoutes() || applyCount !== 1)
  throw Error("Unchanged route bounds caused repeated viewport shifts");
console.log(JSON.stringify({
  expanded,view,applyCount,screenStable: true,fullyVisible: true
}));
"""
    script = tmp_path / "smart-viewbox.mjs"
    script.write_text(program, encoding="utf-8")
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True,
        timeout=12, check=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["fullyVisible"] is True
    assert evidence["screenStable"] is True
    assert evidence["applyCount"] == 1


def test_hosted_dense_drag_requests_render_and_self_loop_resets_preview(
    tmp_path: Path,
) -> None:
    """A saved deferred edit must render again; loops may never retain 4 6."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for dense hosted render event test")
    app = ASSETS["app.js"]
    start = app.index("function finishPointer(event) {")
    finish = app[start:app.index('viewport.addEventListener("pointerup"', start)]
    start = app.index("function placeLiveEdgeConflict(")
    conflict = app[start:app.index("function relocateLiveEdgeLabels(", start)]
    start = app.index("function updateEdgeGeometry(edgeId) {")
    geometry = app[start:app.index("function finishPendingStandaloneSmartRoutes(", start)]
    code = r"""
const activePointers = new Map([[7, {}]]);
const viewport = {
  releasePointerCapture() {},
  classList:{remove(){}}
};
const nodes = new Map([["loop", {classList:{remove(){}}}]]);
const documentEditorHosted = true, documentMode = true;
let gesture = {
  kind:"drag",sourceId:"loop",pointerId:7,moved:true,
  previewOriginals:new Map([["loop", {}]])
};
let pointerMovedNode=false;
const events = [];
const documentSnapshot = () => ({
  nodes:[{id:"loop",x:50,y:60}],edges:[{id:"e"}]
});
const rebuildDocument = doc => {events.push(["render",doc])};
const publishDocumentState = () => {events.push(["save"])};
const setStatus = () => {};
const releasePointerAutoFitIfIdle = () => {};
const rollbackDragNode = () => {};
""" + finish + r"""
finishPointer({type:"pointerup",pointerId:7});
if(events.length!==1 || events[0][0]!=="render" ||
   events[0][1].nodes[0].x!==50 || gesture!==null)
  throw Error("Hosted dense drag did not request native render");
gesture = {kind:"drag",sourceId:"loop",pointerId:7,moved:true};
activePointers.set(7,{});
finishPointer({type:"pointerup",pointerId:7});
if(events.length!==2 || events[1][0]!=="save")
  throw Error("Ordinary small drag regressed into a second full render");
""" + r"""
const documentModeDummy = true;
const routingMode=()=> "smart";
const svg={
  viewBox:{baseVal:{width:1000,height:600}},
  width:{baseVal:{value:1000}},
  height:{baseVal:{value:600}}
};
const overrides = {};
const nodeOffset = () => ({x:1,y:1});
const liveBounds = () => ({x:40,y:60,width:100,height:80});
const liveEdgeGeometry = () => ({
  path:"M 100 110 C 140 100 150 130 100 150",labelX:115,labelY:105
});
const placeLiveLabel=()=>{};
const path = {
  attrs:new Map([
    ["d","M 90 90 L 120 120"],
    ["stroke","#c2410c"],["stroke-dasharray","4 6"]
  ]),
  getAttribute(k){return this.attrs.get(k)||null;},
  setAttribute(k,v){this.attrs.set(k,String(v));},
  removeAttribute(k){this.attrs.delete(k);}
};
const hitPath={setAttribute(){}};
const edgeState={
  from:"loop",to:"loop",
  element:{
    dataset:{routingPending:"true"},
    removeAttribute(key){
      if(key==="data-routing-pending")delete this.dataset.routingPending;
      if(key==="data-routing-conflict")delete this.dataset.routingConflict;
    }
  },
  path,hitPath,lane:0,fromSide:null,toSide:null,
  route:"canvas-self-loop",kind:"flow",
  originalStroke:"#64748b",originalDash:""
};
const edges = new Map([["self",edgeState]]);
""" + conflict + geometry + r"""
updateEdgeGeometry("self");
if(edgeState.element.dataset.routingPending!==undefined ||
   path.getAttribute("stroke")!=="#64748b" ||
   path.getAttribute("stroke-dasharray")!==null)
  throw Error("Finalized self loop retained pending preview styling");
console.log(JSON.stringify({hostedRender:1,normalSave:1,loopRecovered:true}));
"""
    script = tmp_path / "hosted-dense-and-loop.mjs"
    script.write_text(code, encoding="utf-8")
    outcome = subprocess.run(
        [node, str(script)], capture_output=True, text=True,
        timeout=16, check=True,
    )
    result = json.loads(outcome.stdout)
    assert result == {"hostedRender": 1, "normalSave": 1, "loopRecovered": True}


def test_six_parallel_canvas_edges_have_distinct_certified_paths(
    tmp_path: Path,
) -> None:
    source = canvas(obstacle=False)
    a, b = source["nodes"]
    source["edges"] = [
        {"id": "p" + str(i), "fromNode": "start", "toNode": "end"}
        for i in range(6)
    ]
    svg = render(source)
    groups = [
        group for group in svg.iter(SVG + "g")
        if group.get("data-source-kind") == "edge"
    ]
    paths = [group.find(SVG + "path").get("d") for group in groups]
    assert len(paths) == len(set(paths)) == 6
    assert all(g.get("data-route") == "canvas-smart" for g in groups)
    lanes = [(i - 2.5) * 18.0 for i in range(6)]
    expected = [
        route_edge(a, b, [a, b], lane=lane, max_lane=45.0)
        for lane in lanes
    ]
    assert all(route is not None and route.collision_free for route in expected)
    assert paths == [route.path for route in expected]
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for browser/renderer parallel route parity")
    module = tmp_path / "parallel-router.mjs"
    module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    script = tmp_path / "parallel-check.mjs"
    script.write_text(
        'import {smartEdgeGeometry} from "./parallel-router.mjs";\n'
        f"const nodes = {json.dumps([a,b])};\n"
        f"const lanes = {json.dumps(lanes)};\n"
        'console.log(JSON.stringify(lanes.map(lane => '
        'smartEdgeGeometry(nodes[0], nodes[1], nodes, '
        '{lane, maxLane: 45})?.path ?? null)));\n',
        encoding="utf-8",
    )
    run = subprocess.run(
        [node, str(script)], capture_output=True, text=True,
        timeout=14, check=True,
    )
    assert json.loads(run.stdout) == paths


def test_reciprocal_canvas_edges_use_distinct_smart_lanes() -> None:
    source = canvas(obstacle=False)
    source["edges"] = [
        {"id": "forward", "fromNode": "start", "toNode": "end"},
        {"id": "return", "fromNode": "end", "toNode": "start"},
    ]
    smart_groups = [
        g for g in render(source).iter(SVG + "g")
        if g.get("data-source-kind") == "edge"
    ]
    assert len(smart_groups) == 2
    forward, backward = smart_groups
    assert forward.get("data-lane") == "-9.0"
    assert backward.get("data-lane") == "9.0"
    smart_paths = [g.find(SVG + "path").get("d") for g in smart_groups]
    assert len(set(smart_paths)) == 2
    assert all(g.get("data-route") == "canvas-smart" for g in smart_groups)
    first, second = source["nodes"]
    expected_forward = route_edge(
        first, second, [first, second], lane=-9.0, max_lane=9.0,
    )
    expected_backward = route_edge(
        second, first, [first, second], lane=9.0, max_lane=9.0,
    )
    assert expected_forward is not None and expected_backward is not None
    assert smart_paths == [expected_forward.path, expected_backward.path]
    # Explicitly opting out must retain the historical simple renderer logic.
    source["schauwerk"]["edgeRouting"] = "simple"
    simple = [
        g for g in render(source).iter(SVG + "g")
        if g.get("data-source-kind") == "edge"
    ]
    assert simple[0].get("data-route") != "canvas-smart"
    assert simple[1].get("data-route") != "canvas-smart"


def test_relocated_simple_edge_label_stays_within_svg_canvas(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for simple-mode label bounds regression")
    app = ASSETS["app.js"]
    assert "if (documentMode && !gesture.previewOriginals)" in app
    begin = app.index("function expandSmartCanvasToFitRoutes(")
    source = app[begin:app.index("function constrainBoundsOffset(", begin)]
    program = r"""
const documentMode=true, routingMode=()=> "simple";
const nodes=new Map();
let pathReads=0;
const edges=new Map([["labeled", {
  routeBounds:null,
  path:{getBBox(){pathReads++;throw Error("simple path not needed")}},
  labelRect:{id:"box"}
}]]);
const original={x:-88,y:-88,width:650,height:200};
const svg={
  viewBox:{baseVal:{...original}},
  setAttribute(name,value){
    if(name==="viewBox"){
      const [x,y,width,height]=value.split(" ").map(Number);
      this.viewBox.baseVal={x,y,width,height};
      return; // SVGAnimatedRect stays an object, not an attribute string.
    }
    this[name]=value;
  }
};
const nodeBoundsInSvg=()=>({
  minX:145,minY:-116,maxX:310,maxY:-88
});
let view={x:14,y:23,scale:1.5},applies=0;
const applyView=()=>{applies++};
""" + source + r"""
const before=view.y+(0-original.y)*view.scale;
if(!expandSmartCanvasToFitRoutes())
  throw Error("Simple-mode relocated label still clipped");
const box=svg.viewBox.baseVal;
if(box.y>-140 || box.y+box.height<original.y+original.height)
  throw Error("Relocated label outside expanded SVG");
if(Math.abs(view.y+(0-box.y)*view.scale-before)>1e-6)
  throw Error("Simple-label expansion shifted viewport");
if(pathReads!==0)throw Error("Simple mode scanned expensive path geometry");
if(expandSmartCanvasToFitRoutes() || applies!==1)
  throw Error("Repeated view changes without any label movement");
console.log(JSON.stringify({visible:true,unchangedPan:true,pathReads}));
"""
    script = tmp_path / "simple-label-bounds.mjs"
    script.write_text(program, encoding="utf-8")
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True,
        check=True, timeout=14,
    )
    assert json.loads(result.stdout) == {
        "visible": True, "unchangedPan": True, "pathReads": 0,
    }


@pytest.mark.parametrize(
    ("target_x", "blocker_specs"),
    [
        (400, [(110, 65, 100, 80)]),
        (600, [
            (-200, -300, 50, 600), (-200, -300, 600, 50),
            (-200, 200, 600, 50), (300, -300, 50, 315),
            (300, 60, 50, 190),
        ]),
    ],
    ids=["fixed-stub-rail-shadow", "narrow-physical-passage"],
)
def test_manual_fixed_port_stub_keeps_python_browser_geometry_parity(
    tmp_path: Path, target_x: int,
    blocker_specs: list[tuple[int, int, int, int]],
) -> None:
    """Codex-P2: a virtual rail may not erase a clear manually chosen port."""
    node_runtime = shutil.which("node")
    if not node_runtime:
        pytest.skip("Node unavailable for browser router parity")
    a = {"id": "a", "type": "text", "x": 0, "y": 0,
         "width": 100, "height": 80}
    b = {"id": "b", "type": "text", "x": target_x, "y": 0,
         "width": 100, "height": 80}
    blocks = [
        {"id": f"block-{i}", "type": "text", "x": x, "y": y,
         "width": w, "height": h}
        for i, (x, y, w, h) in enumerate(blocker_specs)
    ]
    nodes = [a, b, *blocks]
    js_module = tmp_path / "smart-router.mjs"
    js_module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    runner = tmp_path / "verify.mjs"
    runner.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps(nodes)};\n"
        'console.log(JSON.stringify(smartEdgeGeometry(nodes[0], nodes[1],'
        ' nodes, {lane:-9,maxLane:9,fromSide:"right",toSide:"left"})));\n',
        encoding="utf-8",
    )
    outcome = subprocess.run(
        [node_runtime, str(runner)], capture_output=True, text=True,
        timeout=12, check=True,
    )
    browser = json.loads(outcome.stdout)
    python = route_edge(
        a, b, nodes, lane=-9, max_lane=9,
        from_side="right", to_side="left",
    )
    assert python is not None and python.collision_free
    assert browser is not None and browser["collisionFree"]
    assert browser["path"] == python.path
    assert (browser["fromSide"], browser["toSide"]) == ("right", "left")


def _crossing_demo_nodes() -> list[dict]:
    # Recorded A/B case 3: one obstacle has two short viable corridors.
    coords = (("a", 68, -22, 105, 70), ("b", 379, 63, 105, 70),
              ("c", -44, 192, 105, 70), ("d", 374, 279, 105, 70),
              ("obstacle", 205, 115, 65, 55))
    return [
        {"id": name, "type": "text", "text": name,
         "x": x, "y": y, "width": width, "height": height}
        for name, x, y, width, height in coords
    ]


def _strict_crossings(first, second) -> int:
    def orient(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def crosses(a, b, c, d):
        return (orient(a,b,c)*orient(a,b,d)<-1e-7
                and orient(c,d,a)*orient(c,d,b)<-1e-7)
    return sum(
        crosses(a,b,c,d)
        for a,b in zip(first.points,first.points[1:])
        for c,d in zip(second.points,second.points[1:])
    )


def _poly_length(route) -> float:
    import math
    return sum(math.dist(a,b) for a,b in zip(route.points,route.points[1:]))


def test_crossing_penalty_avoids_real_crossing_without_long_detour() -> None:
    nodes = _crossing_demo_nodes()
    first = route_edge(nodes[0], nodes[3], nodes)
    baseline = route_edge(nodes[1], nodes[2], nodes)
    assert first is not None and baseline is not None
    prior = [{"from": "a", "to": "d", "points": first.points}]
    improved = route_edge(nodes[1], nodes[2], nodes, prior_routes=prior)
    assert improved is not None and improved.collision_free
    assert _strict_crossings(first, baseline) == 1
    assert _strict_crossings(first, improved) == 0
    assert _poly_length(improved) <= _poly_length(baseline) * 1.10
    assert improved.from_side == "left" and improved.to_side == "right"
    forced = route_edge(
        nodes[1],nodes[2],nodes,from_side="left",to_side="right",
        prior_routes=prior,
    )
    assert forced is not None and forced.collision_free
    assert (forced.from_side,forced.to_side) == ("left","right")
    assert _strict_crossings(first,forced) == 0

    source = {
        "nodes": nodes,
        "edges": [
            {"id": "first", "fromNode": "a", "toNode": "d",
             "label": "Erste Kante"},
            {"id": "second", "fromNode": "b", "toNode": "c",
             "label": "Zweite Kante mit längerem Text"},
        ],
        "schauwerk": {"edgeRouting": "smart"},
    }
    rendered = render(source)
    groups = [g for g in rendered.iter(SVG + "g")
              if g.get("data-source-kind") == "edge"]
    assert len(groups) == 2
    second_path = groups[1].find(SVG + "path")
    assert second_path is not None
    assert second_path.get("d") == improved.path
    for group, route in zip(groups, (first,improved)):
        seeded = group.get("data-route-points")
        assert seeded is not None
        from_svg = [
            tuple(map(float, part.split(",")))
            for part in seeded.split(";")
        ]
        assert from_svg == list(route.points)


def test_crossing_aware_javascript_parity_and_manual_ports(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable for crossing-aware JavaScript parity")
    nodes = _crossing_demo_nodes()
    source = tmp_path / "smart-router.mjs"
    source.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    probe = tmp_path / "crossing-parity.mjs"
    probe.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes = {json.dumps(nodes)};\n"
        'const first = smartEdgeGeometry(nodes[0],nodes[3],nodes);\n'
        'const priorRoutes = [{from:"a",to:"d",points:first.points}];\n'
        'const second = smartEdgeGeometry(nodes[1],nodes[2],nodes,{priorRoutes});\n'
        'const forced = smartEdgeGeometry(nodes[1],nodes[2],nodes,\n'
        '  {priorRoutes,fromSide:"left",toSide:"right"});\n'
        'console.log(JSON.stringify({first,second,forced}));\n',
        encoding="utf-8",
    )
    result = subprocess.run([node,str(probe)],capture_output=True,text=True,
                            check=True,timeout=15)
    javascript = json.loads(result.stdout)
    first = route_edge(nodes[0],nodes[3],nodes)
    assert first is not None
    prior = [{"from": "a", "to": "d", "points": first.points}]
    for key,expected in (
        ("first", first),
        ("second", route_edge(nodes[1],nodes[2],nodes,prior_routes=prior)),
        ("forced", route_edge(nodes[1],nodes[2],nodes,
                              prior_routes=prior,from_side="left",to_side="right")),
    ):
        assert expected is not None
        actual = javascript[key]
        assert actual is not None and actual["collisionFree"]
        assert actual["path"] == expected.path
        assert actual["points"] == [list(p) for p in expected.points]
        assert actual["fromSide"] == expected.from_side
        assert actual["toSide"] == expected.to_side


def test_strict_crossing_preserves_axis_aligned_cases() -> None:
    from schauwerk.visual.native_canvas_smart_router import _strict_segment_cross
    assert _strict_segment_cross((0,-5),(0,5),(-5,0),(5,0))
    assert _strict_segment_cross((-5,0),(5,0),(0,-5),(0,5))
    assert not _strict_segment_cross((0,0),(0,5),(0,5),(5,5))
    assert not _strict_segment_cross((0,0),(0,5),(1,-5),(1,5))

def test_dense_documents_bound_prior_edge_context_in_renderer_and_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from schauwerk.visual import native_diagram
    nodes = [
        {"id": f"n{i}", "type": "text", "x": (i % 4) * 195,
         "y": (i // 4) * 155, "width": 100, "height": 70, "text": f"N{i}"}
        for i in range(8)
    ]
    edges = [
        {"id": f"e{i}", "fromNode": nodes[(i * 3) % 8]["id"],
         "toNode": nodes[(i * 3 + 1 + i // 8) % 8]["id"],
         "label": f"R{i}"}
        for i in range(70)
    ]
    for i, edge in enumerate(edges):
        if edge["fromNode"] == edge["toNode"]:
            edge["toNode"] = nodes[(i * 3 + 2) % 8]["id"]
    observed: list[int] = []
    actual = native_diagram._canvas_smart_route_edge

    def capture(*args, **kwargs):
        observed.append(len(kwargs["prior_routes"]))
        return actual(*args, **kwargs)

    monkeypatch.setattr(native_diagram, "_canvas_smart_route_edge", capture)
    def render_many(number: int) -> tuple[list[int], str]:
        observed.clear()
        document = json_canvas_to_editing_document({
            "nodes": nodes, "edges": edges[:number],
            "schauwerk": {"edgeRouting": "smart"},
        })
        svg = render_native_editing_document(document)
        return observed.copy(), svg

    normal, normal_svg = render_many(64)
    dense, dense_svg = render_many(70)
    assert len(normal) == 64 and max(normal) == 12
    assert len(dense) == 70 and max(dense) == 4
    assert dense[0] == 0 and dense[10] == 4
    assert 'data-route-points="' in normal_svg
    assert 'data-route-points="' in dense_svg
    # Native editor and standalone browser must apply the same context bound.
    assert "edges.size > 64 ? -4 : -12" in ASSETS["app.js"]

def test_automatic_ports_rank_crossing_weighted_candidates_with_js_parity(
    tmp_path: Path,
) -> None:
    """A shorter crossing candidate must not beat a cheap clear port pair."""
    coords = ((506,409),(249,151),(671,5),(109,435))
    nodes = [
        {"id": f"n{i}", "type": "text", "text": f"N{i}", "x": x, "y": y,
         "width": 70, "height": 50}
        for i,(x,y) in enumerate(coords)
    ]
    first = route_edge(nodes[0],nodes[1],nodes)
    assert first is not None and first.collision_free
    previous = [{"from": "n0", "to": "n1", "points": first.points}]
    auto = route_edge(nodes[2],nodes[3],nodes,prior_routes=previous)
    forced = route_edge(
        nodes[2],nodes[3],nodes,prior_routes=previous,
        from_side="bottom",to_side="right",
    )
    assert auto is not None and forced is not None
    assert (auto.from_side,auto.to_side)==("left","top")
    assert _strict_crossings(first,auto)==0
    assert _strict_crossings(first,forced)==1
    assert (forced.from_side,forced.to_side)==("bottom","right")
    assert _poly_length(auto) < _poly_length(forced)+100

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable for crossing-weighted ports")
    module = tmp_path/"smart-router.mjs"
    module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    runner = tmp_path/"crossing-ports.mjs"
    runner.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes={json.dumps(nodes)};\n"
        'const first=smartEdgeGeometry(nodes[0],nodes[1],nodes);\n'
        'const priorRoutes=[{from:"n0",to:"n1",points:first.points}];\n'
        'console.log(JSON.stringify({\n'
        ' auto:smartEdgeGeometry(nodes[2],nodes[3],nodes,{priorRoutes}),\n'
        ' forced:smartEdgeGeometry(nodes[2],nodes[3],nodes,\n'
        '  {priorRoutes,fromSide:"bottom",toSide:"right"})\n'
        '}));\n',
        encoding="utf-8",
    )
    output=subprocess.run(
        [node,str(runner)],check=True,capture_output=True,text=True,timeout=15,
    )
    pair=json.loads(output.stdout)
    for kind,route in (("auto",auto),("forced",forced)):
        candidate=pair[kind]
        assert candidate is not None and candidate["collisionFree"]
        assert candidate["path"]==route.path
        assert candidate["points"]==[list(p) for p in route.points]
        assert (candidate["fromSide"],candidate["toSide"])==(
            route.from_side,route.to_side
        )


def test_freeform_moved_nodes_grow_svg_in_all_directions_without_pan_jump(
    tmp_path: Path,
) -> None:
    """A document extent follows real nodes without clipping or viewport drift."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for dynamic canvas extent regression")
    app = ASSETS["app.js"]
    start = app.index("function expandSmartCanvasToFitRoutes(")
    source = app[start:app.index("function constrainBoundsOffset(", start)]
    script = tmp_path / "freeform-viewbox.mjs"
    script.write_text(r"""
const documentMode=true, routingMode=()=> "simple";
const edges=new Map();
const nodes=new Map([
  ["left",{minX:-530,minY:-240,maxX:-410,maxY:-160}],
  ["right",{minX:690,minY:230,maxX:840,maxY:330}]
]);
const nodeBoundsInSvg=node=>node;
const original={x:-88,y:-88,width:650,height:200};
const svg={
  viewBox:{baseVal:{...original}},
  setAttribute(name,value){
    if(name==="viewBox"){
      const [x,y,width,height]=value.split(" ").map(Number);
      this.viewBox.baseVal={x,y,width,height};
    } else this[name]=value;
  }
};
let view={x:14,y:23,scale:1.5},applies=0;
const applyView=()=>{applies++};
""" + source + r"""
const before=[view.x+(0-original.x)*view.scale,
              view.y+(0-original.y)*view.scale];
if(!expandSmartCanvasToFitRoutes())throw Error("Freeform bounds did not grow");
const box=svg.viewBox.baseVal;
if(box.x>-554 || box.y>-264 ||
   box.x+box.width<864 || box.y+box.height<354)
  throw Error("Moved nodes still clipped: "+JSON.stringify(box));
const after=[view.x+(0-box.x)*view.scale,
             view.y+(0-box.y)*view.scale];
if(after.some((v,i)=>Math.abs(v-before[i])>1e-6))
  throw Error("Canvas expansion moved the world under the user");
if(expandSmartCanvasToFitRoutes() || applies!==1)
  throw Error("Unchanged nodes repeatedly shifted the viewport");
console.log(JSON.stringify({freeform:true,screenStable:true,box}));
""", encoding="utf-8")
    result = subprocess.run(
        [node, str(script)], capture_output=True,
        text=True, timeout=12, check=True,
    )
    value = json.loads(result.stdout)
    assert value["freeform"] and value["screenStable"]


def test_smart_open_space_reuses_soft_cubic_and_agrees_with_browser(
    tmp_path: Path,
) -> None:
    """No obstacle: simple and smart share the same cubic control geometry."""
    import re

    nodes = canvas(obstacle=False)["nodes"]
    route = route_edge(nodes[0], nodes[1], nodes, max_lane=0.0)
    assert route is not None and route.collision_free
    assert route.path.count(" C ") == 1
    assert " L " not in route.path
    source = canvas(obstacle=False)
    assert path_data(render(source)) == route.path
    simple = path_data(render(canvas(routing="simple", obstacle=False)))
    def coords(text: str) -> list[float]:
        return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]

    assert coords(route.path) == pytest.approx(coords(simple), abs=0.11)
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for JS/Python smart-cubic parity")
    module = tmp_path / "smart-router.mjs"
    module.write_text(ASSETS["smart-router.js"], encoding="utf-8")
    runner = tmp_path / "open-space.mjs"
    runner.write_text(
        'import {smartEdgeGeometry} from "./smart-router.mjs";\n'
        f"const nodes={json.dumps(nodes)};\n"
        'console.log(JSON.stringify(smartEdgeGeometry(nodes[0],nodes[1],nodes,'
        '{maxLane:0})));\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [node, str(runner)], capture_output=True,
        text=True, timeout=12, check=True,
    )
    js = json.loads(result.stdout)
    assert js["collisionFree"]
    assert js["path"] == route.path
    assert js["labelX"] == pytest.approx(route.label_x)
    assert js["labelY"] == pytest.approx(route.label_y)
