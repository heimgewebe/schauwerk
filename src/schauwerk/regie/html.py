"""Self-contained browser assets for the local Regie interface."""

# ruff: noqa: E501

from __future__ import annotations


def render_index() -> str:
    return """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Schauwerk Regie</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip" href="#main">Zum Inhalt</a>
<header class="topbar">
  <div>
    <p class="eyebrow">Schauwerk</p>
    <h1>Regie</h1>
  </div>
  <div class="phase" id="phase" aria-live="polite">Lade …</div>
</header>
<main id="main">
  <section class="hero" aria-labelledby="review-title">
    <div>
      <p class="eyebrow">Geprüfter Änderungskontext</p>
      <h2 id="review-title">Review wird geladen</h2>
      <p id="review-summary" class="lead"></p>
    </div>
    <dl class="facts" id="review-facts"></dl>
  </section>

  <div id="alerts" aria-live="polite"></div>

  <section class="grid two" aria-labelledby="context-title">
    <article class="panel">
      <h2 id="context-title">Kontext und Anweisungen</h2>
      <div id="context-items"></div>
      <ol id="instructions" class="instructions"></ol>
    </article>
    <article class="panel">
      <h2>Quellenlage</h2>
      <div id="sources"></div>
    </article>
  </section>

  <section class="panel" aria-labelledby="operations-title">
    <div class="section-head">
      <div>
        <p class="eyebrow">Einzelentscheidung</p>
        <h2 id="operations-title">Vorgeschlagene Operationen</h2>
      </div>
      <p class="muted">Jede Operation muss freigegeben, abgelehnt oder vertagt werden.</p>
    </div>
    <div id="operations"></div>
  </section>

  <section class="grid two action-grid">
    <article class="panel" id="decision-panel">
      <p class="eyebrow">Stufe 1</p>
      <h2>Entscheidung binden</h2>
      <p>Die Auswahl erzeugt ein unveränderliches Entscheidungsreceipt, aber noch keine Providerwirkung.</p>
      <form id="decision-form">
        <label>Freigegeben durch
          <input id="approved-by" name="approved-by" autocomplete="name" required>
        </label>
        <label>Freigabereferenz
          <input id="approval-reference" name="approval-reference" placeholder="bureau:task-id" required>
        </label>
        <label>Gültigkeit in Minuten
          <input id="valid-minutes" name="valid-minutes" type="number" min="1" max="1440" value="60" required>
        </label>
        <label>Bestätigungsphrase
          <input id="decision-confirmation" name="decision-confirmation" autocomplete="off" placeholder="APPROVE_LIVE_APPLY" required>
        </label>
        <button type="submit" id="decision-button">Entscheidung speichern</button>
      </form>
      <div id="decision-receipt" class="receipt"></div>
    </article>

    <article class="panel" id="effect-panel">
      <p class="eyebrow">Stufe 2 und 3</p>
      <h2>Wirkung und Wiederherstellung</h2>
      <p>Apply und Restore sind getrennte, nochmals bestätigte Schritte.</p>
      <form id="apply-form">
        <label>Apply-Bestätigung
          <input id="apply-confirmation" autocomplete="off" placeholder="EXECUTE_LIVE_APPLY" required>
        </label>
        <button type="submit" id="apply-button">Freigegebene Operationen anwenden</button>
      </form>
      <form id="restore-form">
        <label>Restore-Bestätigung
          <input id="restore-confirmation" autocomplete="off" placeholder="RESTORE_LIVE_APPLY" required>
        </label>
        <button type="submit" id="restore-button" class="secondary">Vorherzustand wiederherstellen</button>
      </form>
      <div id="effect-receipts" class="receipt"></div>
    </article>
  </section>

  <section class="panel compact">
    <div class="section-head">
      <div>
        <p class="eyebrow">Kontrolle</p>
        <h2>Aktueller Zustand</h2>
      </div>
      <button id="refresh-button" class="secondary" type="button">Neu laden</button>
    </div>
    <pre id="state-summary" class="state-summary"></pre>
  </section>
</main>
<div id="live-message" class="sr-only" aria-live="assertive"></div>
<script src="/app.js" defer></script>
</body>
</html>
"""


STYLE_CSS = r"""
:root {
  color-scheme: light;
  --ink: #17211b;
  --muted: #536159;
  --paper: #f6f3ea;
  --surface: #fffdf8;
  --line: #c8c6bb;
  --accent: #1f5b42;
  --accent-strong: #123d2c;
  --accent-soft: #e3f1e9;
  --warn: #7d4b00;
  --warn-soft: #fff1cf;
  --danger: #8a2e2e;
  --danger-soft: #fde8e6;
  --ok: #195c3b;
  --ok-soft: #e5f5ea;
  --shadow: 0 14px 35px rgb(23 33 27 / 8%);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button, input { font: inherit; }
button {
  border: 0;
  border-radius: .55rem;
  padding: .72rem 1rem;
  background: var(--accent);
  color: white;
  font-weight: 700;
  cursor: pointer;
}
button:hover { background: var(--accent-strong); }
button:disabled { cursor: not-allowed; opacity: .48; }
button.secondary { background: transparent; color: var(--accent-strong); border: 1px solid var(--accent); }
button.secondary:hover { background: var(--accent-soft); }
input {
  width: 100%;
  margin-top: .35rem;
  border: 1px solid var(--line);
  border-radius: .5rem;
  padding: .7rem .75rem;
  background: white;
  color: var(--ink);
}
input:focus-visible, button:focus-visible, a:focus-visible {
  outline: 3px solid #2f7958;
  outline-offset: 3px;
}
label { display: block; margin: .8rem 0; font-weight: 650; }
.skip { position: fixed; left: 1rem; top: -4rem; z-index: 20; background: white; padding: .6rem; }
.skip:focus { top: 1rem; }
.topbar {
  min-height: 6rem;
  padding: 1rem clamp(1rem, 4vw, 4rem);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}
.topbar h1 { margin: 0; font-size: clamp(1.5rem, 3vw, 2.2rem); }
.eyebrow { margin: 0 0 .2rem; color: var(--accent); font-size: .78rem; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.phase { border-radius: 999px; padding: .45rem .8rem; background: var(--accent-soft); font-weight: 750; }
main { width: min(1180px, calc(100% - 2rem)); margin: 2rem auto 5rem; }
.hero, .panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: .9rem;
  box-shadow: var(--shadow);
}
.hero { display: grid; grid-template-columns: 1.6fr 1fr; gap: 2rem; padding: clamp(1.3rem, 3vw, 2.4rem); }
h2, h3 { line-height: 1.2; }
h2 { margin: .2rem 0 .65rem; }
.lead { max-width: 68ch; font-size: 1.08rem; color: var(--muted); }
.facts { margin: 0; display: grid; gap: .65rem; }
.facts div { padding-bottom: .55rem; border-bottom: 1px solid var(--line); }
.facts dt { color: var(--muted); font-size: .82rem; }
.facts dd { margin: .15rem 0 0; font-weight: 700; overflow-wrap: anywhere; }
.grid { display: grid; gap: 1rem; margin-top: 1rem; }
.grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.panel { margin-top: 1rem; padding: 1.25rem; }
.grid .panel { margin-top: 0; }
.panel.compact { padding: 1rem 1.25rem; }
.section-head { display: flex; align-items: start; justify-content: space-between; gap: 1rem; }
.muted { color: var(--muted); }
.alert { margin: 1rem 0; border-left: .35rem solid var(--warn); background: var(--warn-soft); padding: .9rem 1rem; }
.alert.danger { border-color: var(--danger); background: var(--danger-soft); }
.alert.ok { border-color: var(--ok); background: var(--ok-soft); }
.context-item { border-left: .25rem solid var(--line); padding: .4rem .75rem; margin: .7rem 0; }
.context-item.risk { border-color: var(--warn); }
.context-item strong { display: block; }
.instructions { padding-left: 1.35rem; }
.source { display: grid; grid-template-columns: 1fr auto; gap: .3rem .8rem; padding: .75rem 0; border-bottom: 1px solid var(--line); }
.source:last-child { border-bottom: 0; }
.source p { margin: .1rem 0; }
.badge { align-self: start; border-radius: 999px; padding: .25rem .6rem; font-size: .78rem; font-weight: 800; background: var(--accent-soft); }
.badge.stale, .badge.partial, .badge.unknown { background: var(--warn-soft); color: var(--warn); }
.badge.failed { background: var(--danger-soft); color: var(--danger); }
.operation { margin: 1rem 0; border: 1px solid var(--line); border-radius: .75rem; overflow: hidden; }
.operation-head { padding: 1rem; background: #f1efe7; display: flex; justify-content: space-between; gap: 1rem; }
.operation-head h3 { margin: 0; }
.diff-grid { display: grid; grid-template-columns: 1fr 1fr; }
.diff-side { min-width: 0; padding: 1rem; }
.diff-side + .diff-side { border-left: 1px solid var(--line); }
.diff-side h4 { margin: 0 0 .5rem; }
.diff-side pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: .88rem/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; }
.inline-diff { padding: 1rem; border-top: 1px solid var(--line); background: white; overflow-wrap: anywhere; }
.inline-diff del { background: var(--danger-soft); color: var(--danger); padding: .08rem .18rem; }
.inline-diff ins { background: var(--ok-soft); color: var(--ok); text-decoration: none; padding: .08rem .18rem; }
.decision-options { display: flex; flex-wrap: wrap; gap: .65rem; padding: 1rem; border-top: 1px solid var(--line); }
.decision-options label { margin: 0; display: flex; align-items: center; gap: .4rem; border: 1px solid var(--line); border-radius: 999px; padding: .35rem .65rem; font-weight: 650; }
.decision-options input { width: auto; margin: 0; }
.receipt { margin-top: 1rem; }
.receipt dl { display: grid; grid-template-columns: minmax(9rem, .55fr) 1fr; gap: .35rem .8rem; }
.receipt dt { color: var(--muted); }
.receipt dd { margin: 0; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .84rem; }
#restore-form { margin-top: 1.5rem; padding-top: 1.2rem; border-top: 1px solid var(--line); }
.state-summary { max-height: 18rem; overflow: auto; margin: .7rem 0 0; padding: .8rem; background: #18211c; color: #edf6ef; border-radius: .55rem; font-size: .8rem; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 780px) {
  .hero, .grid.two, .diff-grid { grid-template-columns: 1fr; }
  .diff-side + .diff-side { border-left: 0; border-top: 1px solid var(--line); }
  .section-head, .operation-head { display: block; }
  .phase { margin-left: 1rem; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; } }
"""


APP_JS = r"""
'use strict';
const fragmentToken = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
if (fragmentToken) {
  window.sessionStorage.setItem('schauwerk-session', fragmentToken);
  window.history.replaceState(null, '', window.location.pathname);
}
const token = window.sessionStorage.getItem('schauwerk-session') || '';
let currentState = null;

const $ = (id) => document.getElementById(id);
const text = (tag, value, className) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = value ?? '';
  return node;
};
const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

async function api(path, method='GET', body=null) {
  const options = { method, headers: { 'X-Schauwerk-Session': token } };
  if (body !== null) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function announce(message) {
  $('live-message').textContent = message;
}

function showError(message) {
  announce(message);
  $('alerts').replaceChildren(text('div', message, 'alert danger'));
}

function addFact(container, label, value) {
  const wrapper = document.createElement('div');
  wrapper.append(text('dt', label));
  wrapper.append(text('dd', value));
  container.append(wrapper);
}

function renderAlerts(state) {
  const alerts = $('alerts'); clear(alerts);
  if (state.review.stale_source_ids.length) {
    const alert = text('div', `Nicht frische Quellen: ${state.review.stale_source_ids.join(', ')}`, 'alert');
    alerts.append(alert);
  }
  if (state.controls.kill_switch_enabled) {
    alerts.append(text('div', 'Der Live-Apply-Kill-Switch ist aktiv. Apply ist gesperrt.', 'alert danger'));
  }
  if (state.controls.authorization_expired) {
    alerts.append(text('div', 'Die gebundene Autorisierung ist abgelaufen. Eine neue Review-Session ist nötig.', 'alert danger'));
  }
  if (!state.review.stale_source_ids.length && !state.controls.kill_switch_enabled) {
    alerts.append(text('div', 'Quellenprojektion und lokale Sicherheitsgrenzen sind prüfbar.', 'alert ok'));
  }
}

function renderContext(state) {
  const items = $('context-items'); clear(items);
  state.review.context.forEach((item) => {
    const node = document.createElement('div');
    node.className = `context-item ${item.state}`;
    node.append(text('strong', item.label));
    node.append(text('span', item.value));
    items.append(node);
  });
  const instructions = $('instructions'); clear(instructions);
  state.review.instructions.forEach((item) => instructions.append(text('li', item)));
}

function renderSources(state) {
  const sources = $('sources'); clear(sources);
  state.review.sources.forEach((source) => {
    const node = document.createElement('article'); node.className = 'source';
    const body = document.createElement('div');
    body.append(text('strong', source.title));
    body.append(text('p', `Revision: ${source.revision}`, 'muted'));
    body.append(text('p', `Beobachtet: ${source.observed_at} · Unsicherheit: ${source.uncertainty}`, 'muted'));
    body.append(text('p', source.citation, 'muted'));
    node.append(body);
    node.append(text('span', source.freshness, `badge ${source.freshness}`));
    sources.append(node);
  });
}

function renderInlineDiff(container, segments) {
  segments.forEach((segment, index) => {
    let node;
    if (segment.kind === 'delete') node = text('del', segment.text);
    else if (segment.kind === 'insert') node = text('ins', segment.text);
    else node = text('span', segment.text);
    container.append(node);
    if (index < segments.length - 1) container.append(document.createTextNode(' '));
  });
}

function decisionFor(operationId, state) {
  if (!state.decision) return 'defer';
  if (state.decision.approved_operation_ids.includes(operationId)) return 'approve';
  if (state.decision.rejected_operation_ids.includes(operationId)) return 'reject';
  return 'defer';
}

function renderOperations(state) {
  const operations = $('operations'); clear(operations);
  state.review.operations.forEach((operation, index) => {
    const card = document.createElement('article'); card.className = 'operation';
    const head = document.createElement('div'); head.className = 'operation-head';
    const heading = document.createElement('div');
    heading.append(text('p', `Operation ${index + 1}`, 'eyebrow'));
    heading.append(text('h3', operation.operation_id));
    heading.append(text('p', operation.semantic_summary, 'muted'));
    head.append(heading);
    head.append(text('span', operation.action, 'badge'));
    card.append(head);

    const diff = document.createElement('div'); diff.className = 'diff-grid';
    const before = document.createElement('div'); before.className = 'diff-side';
    before.append(text('h4', 'Vorher'));
    before.append(text('pre', operation.old_text));
    const after = document.createElement('div'); after.className = 'diff-side';
    after.append(text('h4', 'Nachher'));
    after.append(text('pre', operation.new_text));
    diff.append(before, after); card.append(diff);

    const inline = document.createElement('div'); inline.className = 'inline-diff';
    inline.append(text('strong', 'Änderungsdiff: '));
    renderInlineDiff(inline, operation.visual_diff); card.append(inline);

    const options = document.createElement('fieldset'); options.className = 'decision-options';
    options.setAttribute('aria-label', `Entscheidung für ${operation.operation_id}`);
    ['approve', 'reject', 'defer'].forEach((choice) => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'radio'; input.name = `decision-${operation.operation_id}`;
      input.value = choice; input.dataset.operationId = operation.operation_id;
      input.checked = decisionFor(operation.operation_id, state) === choice;
      input.disabled = state.controls.decision_immutable;
      label.append(input, document.createTextNode({approve:'Freigeben', reject:'Ablehnen', defer:'Vertagen'}[choice]));
      options.append(label);
    });
    card.append(options); operations.append(card);
  });
}

function renderReceipt(container, title, value) {
  if (!value) return;
  container.append(text('h3', title));
  const list = document.createElement('dl');
  Object.entries(value).forEach(([key, item]) => {
    list.append(text('dt', key));
    list.append(text('dd', Array.isArray(item) ? item.join(', ') : String(item)));
  });
  container.append(list);
}

function renderControls(state) {
  $('decision-button').disabled = !state.controls.can_decide;
  document.querySelectorAll('#decision-form input').forEach((node) => node.disabled = !state.controls.can_decide);
  $('apply-button').disabled = !state.controls.can_apply;
  $('apply-confirmation').disabled = !state.controls.can_apply;
  $('restore-button').disabled = !state.controls.can_restore;
  $('restore-confirmation').disabled = !state.controls.can_restore;

  const decision = $('decision-receipt'); clear(decision);
  renderReceipt(decision, 'Entscheidungsreceipt', state.decision);
  const effects = $('effect-receipts'); clear(effects);
  renderReceipt(effects, 'Apply-Receipt', state.transaction);
  renderReceipt(effects, 'Restore-Receipt', state.restore);
}

function render(state) {
  currentState = state;
  $('phase').textContent = ({review:'Review', approved:'Freigegeben', applied:'Angewendet', 'apply-failed':'Apply fehlgeschlagen', 'restore-failed':'Restore fehlgeschlagen', restored:'Wiederhergestellt'})[state.phase] || state.phase;
  $('review-title').textContent = state.review.title;
  $('review-summary').textContent = state.review.summary;
  const facts = $('review-facts'); clear(facts);
  addFact(facts, 'Zielalias', state.review.surface_alias);
  addFact(facts, 'Managed Region', state.review.region_id);
  addFact(facts, 'Erwartete Revision', state.review.expected_snapshot_digest);
  addFact(facts, 'Maximale Unsicherheit', state.review.maximum_uncertainty);
  renderAlerts(state); renderContext(state); renderSources(state); renderOperations(state); renderControls(state);
  $('state-summary').textContent = JSON.stringify({phase:state.phase, controls:state.controls, boundary:state.boundary}, null, 2);
}

async function refresh() {
  try { render(await api('/api/state')); }
  catch (error) { showError(error.message); }
}

$('decision-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const decisions = {};
  document.querySelectorAll('input[type="radio"]:checked').forEach((node) => decisions[node.dataset.operationId] = node.value);
  const payload = {
    decisions,
    approved_by: $('approved-by').value,
    approval_reference: $('approval-reference').value,
    confirmation: $('decision-confirmation').value,
    valid_minutes: Number($('valid-minutes').value),
  };
  try { await api('/api/decision', 'POST', payload); announce('Entscheidung gespeichert.'); await refresh(); }
  catch (error) { showError(error.message); }
});

$('apply-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await api('/api/apply', 'POST', {confirmation:$('apply-confirmation').value}); announce('Apply abgeschlossen.'); await refresh(); }
  catch (error) { await refresh(); showError(error.message); }
});

$('restore-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await api('/api/restore', 'POST', {confirmation:$('restore-confirmation').value}); announce('Restore abgeschlossen.'); await refresh(); }
  catch (error) { await refresh(); showError(error.message); }
});

$('refresh-button').addEventListener('click', refresh);
refresh();
"""
