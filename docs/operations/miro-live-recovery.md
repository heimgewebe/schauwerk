---
id: miro-live-recovery
role: runbook
status: active
doc_type: runbook
title: Miro live recovery
summary: Operational recovery steps for Miro OAuth, board allowlists, live tests, and cleanup limits.
---

# Miro live recovery

## Purpose

This runbook keeps Schauwerk usable when Miro live access, board allowlists, or live-test artefacts drift. It is intentionally operational: it does not change source truth, publish content, or delete remote Miro boards.

## Fast auth doctor

```bash
cd /home/alex/repos/schauwerk
.venv/bin/python -m schauwerk miro doctor --json
```

Interpretation:

- `safe_for_live_board_operations=true`: live MCP access is currently usable.
- `local_state_present=true`: local OAuth state exists, but this alone does not prove live access.
- `live_authorized=true`: the live MCP check succeeded.
- `renewal_required=true`: renew OAuth before any live board operation.
- `recommended_next_command`: next operational command for the current state.
- `last_health`: latest persisted `auth-health.json` receipt from a live check.
- `auth_history`: bounded local history of recent live auth receipts, useful for detecting expiry cadence.

Treat `miro doctor --json` as the authoritative preflight for "may I run a live board operation now?" Use `--no-live` only for offline inspection of local state and the latest cached receipt; in that mode live authorization is intentionally unknown.

The backing health receipt and bounded history are local state, not Git source truth:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/schauwerk/miro/auth-health.json
${XDG_STATE_HOME:-$HOME/.local/state}/schauwerk/miro/auth-history.json
```

## Lower-level status check

```bash
cd /home/alex/repos/schauwerk
.venv/bin/python -m schauwerk miro status --live --json
```

Interpretation:

- `live.ok=true`: live MCP access is currently usable.
- `live.renewal_required=true`: renew OAuth before any live board operation.
- `credential_error != null`: inspect local credential storage and permissions.
- `catalogue_exists=false`: rerun login/tool discovery.
- `authorized_locally=true`: local state exists; this is not a live-access guarantee.

`status --live` performs a live check but does not persist a health receipt. Run `doctor --json` when the result should become the cached operational receipt.

## Logout boundary

`schauwerk miro logout --json` clears OAuth state, cached tool catalogue, the local auth-health receipt, and auth-history. After logout, `doctor --no-live` must not continue to surface stale live authorization from an old receipt or old history.

## Renew Miro login

```bash
cd /home/alex/repos/schauwerk
.venv/bin/python -m schauwerk miro login --no-browser --manual-callback --json
```

Use the printed Miro authorization URL, authorize it in the browser, then paste the final callback URL into the terminal prompt.

After renewal, rerun:

```bash
.venv/bin/python -m schauwerk miro status --live --json
```

Proceed only when `live.ok=true`. Then persist a fresh health receipt:

```bash
.venv/bin/python -m schauwerk miro doctor --json
```

## Keepalive boundary

A user-level systemd timer should run `schauwerk miro doctor --json` periodically when a persisted health receipt is useful. It is a detection and refresh-attempt mechanism, not a guarantee that Miro will keep the grant valid forever. If the provider invalidates the grant, the timer must surface `renewal_required=true`; it must not pretend to re-consent without a person.

The timer must be non-interactive: no browser launch, no manual callback prompt, and no hidden consent flow. If renewal is required, it should record the failed state and stop there.

Recommended cadence for the local workstation is below one hour, for example `OnUnitActiveSec=45min` with a small randomized delay. The timer must use the same repository and state root as manual live work:

```text
WorkingDirectory=/home/alex/repos/schauwerk
Environment=PYTHONPATH=/home/alex/repos/schauwerk/src
Environment=XDG_STATE_HOME=/home/alex/.local/state
```

## Protect Nicole learning maps

These aliases are currently protected local allowlist entries and must not be removed during routine cleanup:

```text
nicole-lernstoff-clean-20260702
nicole-mt-zoom-20260701-211607
nicole-mt-zoom-chunked-20260701-211733
nicole-stoff-20260701
```

The likely primary Zoomlandkarte is:

```text
nicole-mt-zoom-chunked-20260701-211733
```

## Inspect local board allowlist

```bash
cd /home/alex/repos/schauwerk
.venv/bin/python -m schauwerk miro board list --json
```

The backing file is local state, not Git source truth:

```text
/home/alex/.local/state/schauwerk/miro/boards.json
```

Before manual allowlist edits, create an owner-only backup:

```bash
state=/home/alex/.local/state/schauwerk/miro
stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp "$state/boards.json" "$state/boards.before-edit-$stamp.json"
chmod 600 "$state/boards.before-edit-$stamp.json"
```

## Restore local board allowlist backup

```bash
state=/home/alex/.local/state/schauwerk/miro
cp "$state/boards.before-edit-<STAMP>.json" "$state/boards.json"
chmod 600 "$state/boards.json"
.venv/bin/python -m schauwerk miro board list --json
```

## Cleanup boundary

As of this runbook, the discovered Miro MCP tool catalogue exposes:

```text
board_create
board_list_items
board_search_boards
code_widget_delete
```

It does not expose a safe `board_delete`, `board_clear`, or generic `item_delete` primitive. Therefore Schauwerk must not claim remote board cleanup unless such a primitive is discovered and guarded by an explicit deletion plan.

Allowed cleanup without a remote delete primitive:

- remove stale local allowlist aliases;
- prune local live-test artefact records;
- keep owner-only backups before local-state edits;
- report `remote_cleanup_supported=false`.

Not allowed:

- pretending local allowlist cleanup deleted remote boards;
- destructive remote mutation through an unrelated tool;
- deleting Nicole learning-map aliases during routine cleanup.

## Zoomlandkarte live verification

When live access is healthy, verify the Zoomlandkarte renderer with:

```bash
cd /home/alex/repos/schauwerk
.venv/bin/python -m schauwerk miro learn live-test \
  demos/education/peer-learning.yml \
  --template zoomlandkarte \
  --json
```

Expected artefacts under the reported output directory:

```text
before.json
after.json
quality.json
```

Check:

- `layout.success=true`;
- `quality.ok=true` or only documented non-blocking warnings;
- `layout_read.frame_count` reflects the macro and cluster frames;
- the board visually shows overview clusters when zoomed out and detailed contents when zoomed in.

## Failure handling

If OAuth is expired, stop at renewal. Do not patch renderer code to work around authentication. Use `miro doctor --json` to prove the restored live state before a renderer or board mutation test.

If Miro live creation succeeds but quality fails, preserve `before.json`, `after.json`, `quality.json`, and create a focused layout patch.

If local allowlist state becomes wrong, restore from the latest `boards.before-edit-*.json` backup and rerun `board list`.

If remote cleanup is requested, first prove the Miro tool catalogue contains a safe board or item deletion primitive. If not, report the boundary and only clean local state.
