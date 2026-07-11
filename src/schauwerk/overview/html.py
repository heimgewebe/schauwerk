"""Self-contained browser assets for overview and live views."""

# ruff: noqa: E501

from __future__ import annotations


def render_index() -> str:
    return """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Schauwerk Übersicht</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip" href="#main">Zum Inhalt</a>
<header class="topbar">
  <div>
    <p class="eyebrow">Schauwerk</p>
    <h1>Übersicht und Live-Ansichten</h1>
  </div>
  <div class="toolbar">
    <label>Anzeigeprofil
      <select id="profile-select" aria-label="Anzeigeprofil"></select>
    </label>
    <button id="fullscreen-button" type="button">Vollbild</button>
    <button id="refresh-button" type="button" class="secondary">Aktualisieren</button>
  </div>
</header>
<main id="main">
  <div id="message" aria-live="polite"></div>
  <section class="summary-grid" id="summary" data-section="summary" aria-label="Zusammenfassung"></section>

  <section class="panel" id="projects-section" data-section="projects">
    <div class="section-head"><div><p class="eyebrow">Registry</p><h2>Projekte und Views</h2></div><p id="registry-digest" class="mono muted"></p></div>
    <nav id="projects" aria-label="Projekt- und Viewnavigation"></nav>
  </section>

  <section class="panel" id="observations-section" data-section="observations">
    <div class="section-head"><div><p class="eyebrow">Zeitgebundene Fakten</p><h2>Freshness und Providerzustand</h2></div><p id="generated-at" class="muted"></p></div>
    <div id="observations" class="cards"></div>
  </section>

  <section class="grid two">
    <section class="panel" id="jobs-section" data-section="jobs">
      <p class="eyebrow">Lokale Receipts</p><h2>Aktive Vorgänge</h2><div id="jobs"></div>
    </section>
    <section class="panel" id="publications-section" data-section="publications">
      <p class="eyebrow">Artefakte</p><h2>Publikationen</h2><div id="publications"></div>
    </section>
  </section>

  <section class="panel failures" id="failures-section" data-section="failures">
    <p class="eyebrow">Diagnose</p><h2>Fehler und degradierte Zustände</h2><div id="failures"></div>
  </section>
</main>
<div class="sr-only" id="live-message" aria-live="assertive"></div>
<script src="/app.js" defer></script>
</body>
</html>
"""


STYLE_CSS = r"""
:root {
  color-scheme: light;
  --ink: #15211b;
  --muted: #5d6862;
  --paper: #f1f3ed;
  --surface: #fffefa;
  --line: #c7cec8;
  --accent: #164f39;
  --accent-soft: #dfefe6;
  --ok: #17613e;
  --ok-soft: #e2f4e8;
  --warn: #7c4d00;
  --warn-soft: #fff0cf;
  --danger: #8a2e2e;
  --danger-soft: #fae5e3;
  --unknown: #58636c;
  --unknown-soft: #e9edf0;
  --shadow: 0 12px 34px rgb(21 33 27 / 8%);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
button, select { font: inherit; }
button, select { border: 1px solid var(--accent); border-radius: .55rem; padding: .62rem .82rem; }
button { background: var(--accent); color: white; font-weight: 750; cursor: pointer; }
button.secondary, select { background: var(--surface); color: var(--accent); }
button:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid #397a5d; outline-offset: 3px; }
.skip { position: fixed; left: 1rem; top: -4rem; z-index: 10; background: white; padding: .6rem; }
.skip:focus { top: 1rem; }
.topbar { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem clamp(1rem, 3vw, 3rem); background: rgb(255 254 250 / 96%); border-bottom: 1px solid var(--line); backdrop-filter: blur(8px); }
.topbar h1 { margin: 0; font-size: clamp(1.3rem, 2.5vw, 2rem); }
.toolbar { display: flex; align-items: end; gap: .6rem; flex-wrap: wrap; }
.toolbar label { color: var(--muted); font-size: .78rem; font-weight: 750; }
.toolbar select { display: block; margin-top: .2rem; min-width: 12rem; }
main { width: min(1320px, calc(100% - 2rem)); margin: 1.5rem auto 4rem; }
.eyebrow { margin: 0 0 .2rem; color: var(--accent); font-size: .76rem; font-weight: 850; letter-spacing: .1em; text-transform: uppercase; }
h2, h3 { line-height: 1.2; }
h2 { margin: .15rem 0 .8rem; }
.muted { color: var(--muted); }
.mono { font: .78rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.summary-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .75rem; }
.summary-card, .panel, .card { background: var(--surface); border: 1px solid var(--line); border-radius: .8rem; box-shadow: var(--shadow); }
.summary-card { padding: 1rem; }
.summary-card strong { display: block; font-size: clamp(1.45rem, 3vw, 2.25rem); }
.summary-card span { color: var(--muted); font-size: .82rem; }
.panel { margin-top: 1rem; padding: 1.15rem; }
.grid { display: grid; gap: 1rem; }
.grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.grid .panel { margin-top: 1rem; }
.section-head { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
.project { margin: .75rem 0; border: 1px solid var(--line); border-radius: .7rem; overflow: hidden; }
.project-head { padding: .8rem 1rem; background: #eef1ea; display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.project-head h3 { margin: 0; }
.views { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: .65rem; padding: .8rem; }
.view { color: inherit; text-decoration: none; border: 1px solid var(--line); border-radius: .55rem; padding: .75rem; }
.view:hover { background: var(--accent-soft); }
.view strong { display: block; }
.view p { margin: .35rem 0 0; color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: .7rem; }
.card { padding: .85rem; box-shadow: none; }
.card h3 { margin: .2rem 0 .45rem; font-size: 1rem; }
.card p { margin: .2rem 0; }
.meta { color: var(--muted); font-size: .78rem; overflow-wrap: anywhere; }
.badge { display: inline-block; border-radius: 999px; padding: .2rem .55rem; background: var(--unknown-soft); color: var(--unknown); font-size: .73rem; font-weight: 850; }
.badge.ok, .badge.fresh { background: var(--ok-soft); color: var(--ok); }
.badge.degraded, .badge.warning, .badge.stale { background: var(--warn-soft); color: var(--warn); }
.badge.error, .badge.critical { background: var(--danger-soft); color: var(--danger); }
.list-item { padding: .65rem 0; border-bottom: 1px solid var(--line); }
.list-item:last-child { border-bottom: 0; }
.list-item strong { display: block; }
.failure { border-left: .35rem solid var(--danger); background: var(--danger-soft); padding: .7rem .85rem; margin: .55rem 0; }
.empty { color: var(--muted); font-style: italic; }
.notice { margin: 0 0 1rem; border-left: .35rem solid var(--warn); background: var(--warn-soft); padding: .8rem 1rem; }
.notice.ok { border-color: var(--ok); background: var(--ok-soft); }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
body.wallboard main { width: min(1800px, calc(100% - 1.5rem)); }
body.wallboard .topbar { position: static; }
body.wallboard .summary-card { padding: 1.2rem; }
body.incident .project, body.incident #publications-section { display: none !important; }
@media (max-width: 980px) { .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .topbar, .section-head { align-items: stretch; flex-direction: column; } .summary-grid, .grid.two { grid-template-columns: 1fr 1fr; } .toolbar { align-items: stretch; } }
@media (max-width: 430px) { .summary-grid, .grid.two { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
"""


APP_JS = r"""
'use strict';
const fragmentToken = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
if (fragmentToken) {
  window.sessionStorage.setItem('schauwerk-overview-session', fragmentToken);
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}
const token = window.sessionStorage.getItem('schauwerk-overview-session') || '';
let snapshot = null;
let profile = null;
let refreshTimer = null;
const $ = (id) => document.getElementById(id);
const node = (tag, value, className='') => { const result=document.createElement(tag); if(className) result.className=className; result.textContent=value ?? ''; return result; };
const clear = (target) => { while(target.firstChild) target.removeChild(target.firstChild); };

async function api(path) {
  const response = await fetch(path, {headers:{'X-Schauwerk-Session':token}, cache:'no-store'});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}
function announce(message) { $('live-message').textContent = message; }
function showMessage(message, ok=false) { const target=$('message'); clear(target); target.append(node('div', message, ok ? 'notice ok' : 'notice')); announce(message); }
function badge(value) { return node('span', value, `badge ${value}`); }
function empty(target, message) { target.append(node('p', message, 'empty')); }
function limited(items) { return items.slice(0, profile.maximum_items_per_section); }

function renderSummary() {
  const target=$('summary'); clear(target);
  const entries=[
    ['Projekte', snapshot.summary.project_count], ['Views', snapshot.summary.view_count],
    ['Aktive Vorgänge', snapshot.summary.active_job_count], ['Fehler', snapshot.summary.error_count],
    ['Veraltet', snapshot.summary.stale_count], ['Provider', snapshot.summary.provider_state],
  ];
  entries.forEach(([label,value]) => { const card=node('article','', 'summary-card'); card.append(node('strong',String(value)),node('span',label)); target.append(card); });
}
function renderProjects() {
  const target=$('projects'); clear(target);
  limited(snapshot.projects).forEach((project) => {
    const article=node('article','', 'project');
    const head=node('div','', 'project-head'); const title=node('div'); title.append(node('h3',project.title),node('span',project.project_id,'mono muted')); head.append(title,badge(project.status)); article.append(head);
    const views=node('div','', 'views');
    project.views.forEach((view) => { const card=node('a','', 'view'); card.href=`#view-${view.view_id}`; card.id=`view-${view.view_id}`; card.append(node('strong',view.title),node('p',view.purpose),node('p',`${view.surface_provider} · ${view.management_mode} · ${view.visibility}`,'meta')); views.append(card); });
    if (!project.views.length) empty(views,'Keine Views deklariert.'); article.append(views); target.append(article);
  });
  $('registry-digest').textContent=`Registry ${snapshot.registry_digest}`;
}
function renderObservations() {
  const target=$('observations'); clear(target);
  limited(snapshot.observations).forEach((item) => { const card=node('article','', 'card'); const states=node('div'); states.append(badge(item.state),document.createTextNode(' '),badge(item.freshness),document.createTextNode(' '),badge(item.severity)); card.append(states,node('h3',item.label),node('p',item.value),node('p',`Quelle: ${item.source}`,'meta'),node('p',`Beobachtet: ${item.observed_at}`,'meta')); if(item.error) card.append(node('p',item.error,'failure')); target.append(card); });
  if(!snapshot.observations.length) empty(target,'Keine Beobachtungen.'); $('generated-at').textContent=`Snapshot ${snapshot.generated_at}`;
}
function renderJobs() {
  const target=$('jobs'); clear(target);
  limited(snapshot.jobs).forEach((item) => { const row=node('article','', 'list-item'); row.append(node('strong',item.summary),badge(item.status),node('p',`${item.kind} · ${item.freshness}`,'meta'),node('p',`${item.source} · ${item.observed_at}`,'meta')); target.append(row); });
  if(!snapshot.jobs.length) empty(target,'Keine aktiven lokalen Vorgänge.');
}
function renderPublications() {
  const target=$('publications'); clear(target);
  limited(snapshot.publications).forEach((item) => { const row=node('article','', 'list-item'); row.append(node('strong',item.publication_id),badge(item.artifact_state),node('p',`${item.view_id} · ${item.audience} · ${item.status}`,'meta'),node('p',`Beobachtet: ${item.observed_at} · ${item.freshness}`,'meta')); target.append(row); });
  if(!snapshot.publications.length) empty(target,'Keine Publikationen deklariert.');
}
function renderFailures() {
  const target=$('failures'); clear(target);
  limited(snapshot.failures).forEach((item) => { const row=node('article','', 'failure'); row.append(badge(item.severity),node('strong',item.message),node('p',`${item.source} · ${item.observed_at}`,'meta')); target.append(row); });
  if(!snapshot.failures.length) empty(target,'Keine aktuellen Fehlerbelege.');
}
function applyProfile(selected) {
  profile=selected; document.body.className=profile.profile_id;
  document.querySelectorAll('[data-section]').forEach((section) => { section.hidden=!profile.visible_sections.includes(section.dataset.section); });
  if(refreshTimer) window.clearInterval(refreshTimer);
  refreshTimer=window.setInterval(refresh, profile.refresh_seconds*1000);
  const url=new URL(window.location.href); url.searchParams.set('profile',profile.profile_id); window.history.replaceState(null,'',url.pathname+url.search);
  if(profile.fullscreen) $('fullscreen-button').textContent='Vollbild aktivieren';
}
function populateProfiles() {
  const select=$('profile-select'); const requested=new URLSearchParams(window.location.search).get('profile'); clear(select);
  snapshot.display_profiles.forEach((item) => { const option=node('option',item.title); option.value=item.profile_id; select.append(option); });
  const selected=snapshot.display_profiles.find((item)=>item.profile_id===requested) || snapshot.display_profiles[0]; select.value=selected.profile_id; applyProfile(selected);
}
function render() { renderSummary(); renderProjects(); renderObservations(); renderJobs(); renderPublications(); renderFailures(); }
async function refresh() { try { const next=await api('/api/state'); const first=!snapshot; snapshot=next; if(first) populateProfiles(); else { const current=snapshot.display_profiles.find((item)=>item.profile_id===profile.profile_id); if(current) profile=current; } render(); showMessage(snapshot.summary.provider_state==='error' ? 'Provider gestört; lokale Diagnose bleibt verfügbar.' : 'Übersicht aktualisiert.', snapshot.summary.provider_state!=='error'); } catch(error) { showMessage(error.message); } }
$('profile-select').addEventListener('change',()=>{ const selected=snapshot.display_profiles.find((item)=>item.profile_id===$('profile-select').value); if(selected){ applyProfile(selected); render(); }});
$('refresh-button').addEventListener('click',refresh);
$('fullscreen-button').addEventListener('click',async()=>{ try { if(document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch(error){ showMessage(error.message); }});
refresh();
"""
