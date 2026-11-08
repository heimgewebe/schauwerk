"""Inline CSS and JavaScript of the single-file offline Canvas HTML viewer.

Both assets are embedded verbatim and bound by SHA-256 hashes in the document's
Content-Security-Policy. They are read-only: no network, storage, eval, dynamic
markup, forms or editing. All text reaches the DOM through ``textContent``.
"""
# ruff: noqa: E501

from __future__ import annotations

VIEWER_CSS = r"""
:root{color-scheme:light;--ofh-ink:#172033;--ofh-muted:#52607a;--ofh-line:#cbd5e1;--ofh-bg:#f8fafc;--ofh-accent:#1d4ed8;--ofh-hit:#c2410c}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:flex;flex-direction:column;font:16px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ofh-ink);background:var(--ofh-bg)}
.ofh-bar{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .75rem;padding:.5rem .75rem;border-bottom:1px solid var(--ofh-line);background:#fff}
.ofh-bar h1{flex:1 1 12rem;margin:0;font-size:1.05rem;font-weight:700;overflow-wrap:anywhere}
.ofh-badge{font-size:.8rem;color:var(--ofh-muted);border:1px solid var(--ofh-line);border-radius:999px;padding:.1rem .6rem;white-space:nowrap}
.ofh-tools{display:flex;gap:.35rem}
button,input{font:inherit;color:inherit}
.ofh-button{min-width:2.4rem;min-height:2.4rem;padding:.2rem .7rem;border:1px solid var(--ofh-line);border-radius:.5rem;background:#fff;cursor:pointer}
.ofh-button:hover{border-color:var(--ofh-accent)}
:focus-visible{outline:3px solid var(--ofh-accent);outline-offset:2px}
.ofh-body{flex:1 1 auto;min-height:0;display:flex}
#ofh-stage{position:relative;flex:1 1 auto;min-width:0;min-height:12rem;overflow:hidden;background:#fff;touch-action:none;cursor:grab;user-select:none;-webkit-user-select:none}
#ofh-stage.ofh-panning{cursor:grabbing}
#ofh-diagram{display:block;width:100%;height:100%}
.ofh-side{flex:0 0 21rem;display:flex;flex-direction:column;gap:.5rem;min-height:0;padding:.6rem;border-left:1px solid var(--ofh-line);background:#fff;overflow:auto}
.ofh-side .ofh-badge{white-space:normal;overflow-wrap:anywhere}
.ofh-search{display:flex;gap:.35rem}
.ofh-search input{flex:1 1 auto;min-width:0;min-height:2.4rem;padding:.2rem .6rem;border:1px solid var(--ofh-line);border-radius:.5rem}
#ofh-status{margin:0;font-size:.85rem;color:var(--ofh-muted)}
#ofh-results{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:.25rem;flex:1 1 auto;min-height:6rem;overflow:auto}
#ofh-results li[hidden]{display:none}
.ofh-item{display:block;width:100%;text-align:left;padding:.35rem .5rem;border:1px solid var(--ofh-line);border-radius:.4rem;background:#fff;cursor:pointer}
.ofh-item:hover,.ofh-item[aria-current="true"]{border-color:var(--ofh-accent);background:#eff6ff}
.ofh-kind{display:block;font-size:.72rem;letter-spacing:.04em;text-transform:uppercase;color:var(--ofh-muted)}
.ofh-text{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;overflow-wrap:anywhere;white-space:pre-wrap}
#ofh-detail{border-top:1px solid var(--ofh-line);padding-top:.5rem}
#ofh-detail h2{margin:0 0 .25rem;font-size:.9rem}
#ofh-detail-meta{margin:0;font-size:.8rem;color:var(--ofh-muted);overflow-wrap:anywhere}
#ofh-detail-text{margin:.25rem 0 0;max-height:12rem;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
.ofh-foot{padding:.3rem .75rem;border-top:1px solid var(--ofh-line);background:#fff;font-size:.75rem;color:var(--ofh-muted);overflow-wrap:anywhere}
.ofh-searching g[data-source-kind="node"]:not(.ofh-match){opacity:.22}
g[data-source-kind="node"].ofh-match>rect,g[data-source-kind="node"].ofh-focus>rect{stroke:var(--ofh-hit);stroke-width:4}
g[data-source-kind="node"].ofh-focus>rect{stroke:var(--ofh-accent);stroke-width:5}
@media (max-width:760px){
  .ofh-body{flex-direction:column}
  .ofh-side{flex:0 0 auto;max-height:45vh;border-left:0;border-top:1px solid var(--ofh-line)}
}
@media print{
  .ofh-bar .ofh-tools,.ofh-side{display:none}
  #ofh-stage{overflow:visible}
}
"""

VIEWER_JS = r"""
(function () {
  "use strict";
  var stage = document.getElementById("ofh-stage");
  var svg = document.getElementById("ofh-diagram");
  var list = document.getElementById("ofh-results");
  var search = document.getElementById("ofh-search");
  var statusLine = document.getElementById("ofh-status");
  var detailMeta = document.getElementById("ofh-detail-meta");
  var detailText = document.getElementById("ofh-detail-text");
  if (!stage || !svg || !list || !search || !statusLine) return;

  var baseParts = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
  if (baseParts.length !== 4 || baseParts.some(function (n) { return !isFinite(n); }) ||
      baseParts[2] <= 0 || baseParts[3] <= 0) {
    statusLine.textContent = "Ansicht nicht verfügbar: ungültige Zeichenfläche";
    return;
  }
  var MARGIN = 24, MIN_Z = 0.05, MAX_Z = 24;
  var view = { cx: baseParts[0] + baseParts[2] / 2, cy: baseParts[1] + baseParts[3] / 2, z: 1 };
  var NODE_KIND = "node";

  var groupsById = new Map();
  Array.prototype.forEach.call(svg.querySelectorAll("g[data-source-kind]"), function (g) {
    if (g.getAttribute("data-source-kind") === NODE_KIND) {
      groupsById.set(g.getAttribute("data-source-id"), g);
    }
  });

  function stageSize() { return { w: stage.clientWidth, h: stage.clientHeight }; }
  function fitScale(s) {
    var k = Math.min((s.w - 2 * MARGIN) / baseParts[2], (s.h - 2 * MARGIN) / baseParts[3]);
    return k > 0.0001 ? k : 0.0001;
  }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function round(v) { return Math.round(v * 10000) / 10000; }

  function apply() {
    var s = stageSize();
    if (s.w <= 0 || s.h <= 0) return;
    view.z = clamp(view.z, MIN_Z, MAX_Z);
    view.cx = clamp(view.cx, baseParts[0] - baseParts[2], baseParts[0] + 2 * baseParts[2]);
    view.cy = clamp(view.cy, baseParts[1] - baseParts[3], baseParts[1] + 2 * baseParts[3]);
    var k = fitScale(s) * view.z;
    var vw = s.w / k, vh = s.h / k;
    svg.setAttribute("viewBox", [view.cx - vw / 2, view.cy - vh / 2, vw, vh].map(round).join(" "));
  }

  function fit() {
    view.cx = baseParts[0] + baseParts[2] / 2;
    view.cy = baseParts[1] + baseParts[3] / 2;
    view.z = 1;
    apply();
  }

  function panByPixels(dx, dy) {
    var s = stageSize();
    if (s.w <= 0) return;
    var k = fitScale(s) * view.z;
    view.cx -= dx / k;
    view.cy -= dy / k;
    apply();
  }

  function zoomAt(factor, px, py) {
    var s = stageSize();
    if (s.w <= 0 || s.h <= 0) return;
    var before = fitScale(s) * view.z;
    var nextZ = clamp(view.z * factor, MIN_Z, MAX_Z);
    var after = fitScale(s) * nextZ;
    var wx = view.cx + (px - s.w / 2) / before;
    var wy = view.cy + (py - s.h / 2) / before;
    view.z = nextZ;
    view.cx = wx - (px - s.w / 2) / after;
    view.cy = wy - (py - s.h / 2) / after;
    apply();
  }

  function zoomCenter(factor) {
    var s = stageSize();
    zoomAt(factor, s.w / 2, s.h / 2);
  }

  /* ---- search index: list items carry the full text; DOM only via textContent ---- */
  var items = Array.prototype.slice.call(list.children);
  function norm(text) { return String(text).normalize("NFKC").toLocaleLowerCase(); }
  items.forEach(function (item) {
    var textElement = item.querySelector(".ofh-text");
    item._hay = norm((item.getAttribute("data-node-id") || "") + "\n" + (textElement ? textElement.textContent : ""));
  });
  var matches = items.slice();
  var current = null;

  function setStatus(text) { statusLine.textContent = text; }

  function applyFilter() {
    var query = norm(search.value.trim());
    matches = [];
    items.forEach(function (item) {
      var hit = query === "" || item._hay.indexOf(query) !== -1;
      item.hidden = !hit;
      if (hit) matches.push(item);
      var g = groupsById.get(item.getAttribute("data-node-id"));
      if (g) g.classList.toggle("ofh-match", query !== "" && hit);
    });
    svg.classList.toggle("ofh-searching", query !== "");
    setStatus(query === ""
      ? items.length + " Knoten"
      : matches.length + " von " + items.length + " Knoten gefunden");
  }

  function clearFocusMark() {
    if (current) {
      var g = groupsById.get(current.getAttribute("data-node-id"));
      if (g) g.classList.remove("ofh-focus");
      var b = current.querySelector("button");
      if (b) b.removeAttribute("aria-current");
    }
    current = null;
  }

  function nodeCenterAndSize(g) {
    var box = g.getBBox();
    var cx = box.x + box.width / 2, cy = box.y + box.height / 2;
    var w = box.width, h = box.height;
    var list2 = g.transform && g.transform.baseVal;
    if (list2 && list2.numberOfItems > 0) {
      var m = list2.consolidate().matrix;
      cx = m.a * (box.x + box.width / 2) + m.c * (box.y + box.height / 2) + m.e;
      cy = m.b * (box.x + box.width / 2) + m.d * (box.y + box.height / 2) + m.f;
      w = Math.abs(m.a) * box.width + Math.abs(m.c) * box.height;
      h = Math.abs(m.b) * box.width + Math.abs(m.d) * box.height;
    }
    return { cx: cx, cy: cy, w: Math.max(w, 1), h: Math.max(h, 1) };
  }

  function focusItem(item) {
    if (!item) return;
    clearFocusMark();
    current = item;
    var id = item.getAttribute("data-node-id");
    var g = groupsById.get(id);
    var button = item.querySelector("button");
    if (button) button.setAttribute("aria-current", "true");
    if (detailMeta) detailMeta.textContent = (item.getAttribute("data-node-type") || "") + " · " + id;
    if (detailText) detailText.textContent = item.querySelector(".ofh-text").textContent;
    if (g) {
      g.classList.add("ofh-focus");
      var s = stageSize();
      if (s.w > 0 && s.h > 0) {
        var geometry = nodeCenterAndSize(g);
        var wanted = 0.4 * Math.min(s.w / geometry.w, s.h / geometry.h);
        view.z = clamp(wanted / fitScale(s), 1, 8);
        view.cx = geometry.cx;
        view.cy = geometry.cy;
        apply();
      }
    }
    setStatus("Fokus: " + (item.querySelector(".ofh-text").textContent.slice(0, 80) || id));
  }

  function step(direction) {
    if (matches.length === 0) { setStatus("Keine Treffer"); return; }
    var index = current ? matches.indexOf(current) : -1;
    var next = index < 0
      ? (direction > 0 ? 0 : matches.length - 1)
      : (index + direction + matches.length) % matches.length;
    focusItem(matches[next]);
  }

  items.forEach(function (item) {
    var button = item.querySelector("button");
    if (button) button.addEventListener("click", function () { focusItem(item); });
  });

  search.addEventListener("input", function () {
    clearFocusMark();
    applyFilter();
  });
  search.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      step(event.shiftKey ? -1 : 1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      search.value = "";
      clearFocusMark();
      applyFilter();
      stage.focus();
    } else if (event.key === "ArrowDown") {
      var first = matches[0] && matches[0].querySelector("button");
      if (first) { event.preventDefault(); first.focus(); }
    }
  });

  /* ---- toolbar ---- */
  function bind(id, handler) {
    var element = document.getElementById(id);
    if (element) element.addEventListener("click", handler);
  }
  bind("ofh-fit", fit);
  bind("ofh-zoom-in", function () { zoomCenter(1.25); });
  bind("ofh-zoom-out", function () { zoomCenter(1 / 1.25); });
  bind("ofh-prev", function () { step(-1); });
  bind("ofh-next", function () { step(1); });

  /* ---- keyboard on the stage ---- */
  stage.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    var distance = event.shiftKey ? 240 : 80;
    var handled = true;
    switch (event.key) {
      case "ArrowLeft": panByPixels(distance, 0); break;
      case "ArrowRight": panByPixels(-distance, 0); break;
      case "ArrowUp": panByPixels(0, distance); break;
      case "ArrowDown": panByPixels(0, -distance); break;
      case "+": case "=": zoomCenter(1.25); break;
      case "-": case "_": zoomCenter(1 / 1.25); break;
      case "0": fit(); break;
      case "Escape": clearFocusMark(); break;
      default: handled = false;
    }
    if (handled) event.preventDefault();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
    var target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
    event.preventDefault();
    search.focus();
    search.select();
  });

  /* ---- pointer: drag to pan, two fingers to pinch, wheel to zoom ---- */
  var pointers = new Map();
  var gesture = null;
  function stagePoint(event) {
    var rect = stage.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }
  function gestureState() {
    var points = Array.from(pointers.values());
    if (points.length < 2) return null;
    var a = points[0], b = points[1];
    return { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
  }
  stage.addEventListener("pointerdown", function (event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    try { stage.setPointerCapture(event.pointerId); } catch (_) { /* not capturable */ }
    pointers.set(event.pointerId, stagePoint(event));
    stage.classList.add("ofh-panning");
    gesture = gestureState();
  });
  stage.addEventListener("pointermove", function (event) {
    if (!pointers.has(event.pointerId)) return;
    var previous = pointers.get(event.pointerId);
    var point = stagePoint(event);
    pointers.set(event.pointerId, point);
    if (pointers.size === 1) {
      panByPixels(point.x - previous.x, point.y - previous.y);
      return;
    }
    var next = gestureState();
    if (next && gesture) {
      zoomAt(next.dist / gesture.dist, next.mx, next.my);
      panByPixels(next.mx - gesture.mx, next.my - gesture.my);
    }
    gesture = next;
  });
  function endPointer(event) {
    pointers.delete(event.pointerId);
    gesture = gestureState();
    if (pointers.size === 0) stage.classList.remove("ofh-panning");
  }
  stage.addEventListener("pointerup", endPointer);
  stage.addEventListener("pointercancel", endPointer);
  stage.addEventListener("wheel", function (event) {
    event.preventDefault();
    var unit = event.deltaMode === 1 ? 0.05 : 0.0015;
    var point = stagePoint(event);
    zoomAt(Math.exp(-event.deltaY * unit * (event.ctrlKey ? 3 : 1)), point.x, point.y);
  }, { passive: false });

  /* ---- layout ---- */
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(function () { apply(); }).observe(stage);
  } else {
    window.addEventListener("resize", apply);
  }
  applyFilter();
  fit();
  document.documentElement.classList.add("ofh-ready");
}());
"""
