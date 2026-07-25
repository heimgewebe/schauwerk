# Miro companion evidence refresh

## Purpose

The refresh surface renews the evidence consumed by `miro companion gate-status` without
changing the Miro Developer App, its scopes, its installation, OAuth consent, or board
content. It is a bounded observation path, not an authorization robot.

A successful refresh binds four independent facts to one immutable generation:

- the exact public HTTPS companion release still matches its manifest;
- the authenticated Developer App configuration has the expected URL, team, label, and
  exact scope set;
- the installed app opens on the configured board;
- the in-board Web SDK exposes the required read and write methods and the companion reports
  the expected build and verified state.

## Private configuration

The configuration file contains provider references and browser-profile paths. Keep it in an
owner-only file such as `~/.config/schauwerk/miro-companion-evidence.json` with mode `0600`.
Do not commit it.

```json
{
  "schema_version": "schauwerk-miro-companion-evidence-config.v1",
  "release_manifest": "~/.local/state/schauwerk/evidence/companion-release.json",
  "state_root": "~/.local/state/schauwerk/companion-evidence",
  "browser": {
    "executable": "/usr/bin/brave-browser",
    "profile": "~/.config/BraveSoftware/Brave-Browser/SchauwerkEvidenceProfile",
    "port": 9468,
    "startup_seconds": 20
  },
  "provider": {
    "app_settings_url": "https://miro.com/app/settings/company/<team-id>/user-profile/apps/<app-id>/",
    "board_url": "https://miro.com/app/board/<board-reference>/",
    "app_menu_test_id": "app-menu__item-<app-id>",
    "expected_team_label": "<team-label>"
  },
  "evidence_lifetime_hours": 24,
  "refresh_before_hours": 6
}
```

Use a dedicated persistent browser profile. The profile may retain the already completed Miro
login and OAuth session, but the refresh command never enters credentials, clicks consent,
changes scopes, installs an app, or mutates a board.

## Commands

Validate path safety, permissions, provider-reference shape, browser identity, and release
binding without starting a browser:

```bash
schauwerk miro companion evidence-config-check CONFIG --json
```

Create a new generation only when the current evidence is absent or within its configured
refresh window:

```bash
schauwerk miro companion evidence-capture CONFIG --json
```

Force a fresh provider observation for an explicit operator verification:

```bash
schauwerk miro companion evidence-capture CONFIG --force --json
```

Revalidate the current immutable generation and the public deployment without opening Miro:

```bash
schauwerk miro companion evidence-status CONFIG --json
```

## State model

Each successful capture creates a private directory below `STATE_ROOT/generations/` containing:

- `app-config.json` — Developer App and installation readback;
- `in-board.json` — redacted, hash-bound Web SDK readback;
- `gate-status.json` — evaluated live gate state;
- `generation.json` — immutable artifact inventory and supersession receipt.

Files use mode `0600`, generation directories use `0700`, and `current.json` is an atomically
replaced receipt that points to the latest successful generation. Provider URLs, board
references, app identifiers, browser-profile paths, raw board IDs, and raw object IDs are not
stored in generation artifacts. Necessary identities are represented by SHA-256 bindings.

Older successful generations remain immutable. A new success names the generation it
supersedes. Failed observations never replace `current.json`.

## Attention semantics

A failed refresh writes an owner-only create-only receipt below `STATE_ROOT/attention/` and
returns a non-zero exit. Typical reason codes are:

- `public_release_drift` — deployed files, digests, headers, or HTTPS behavior differ;
- `authentication_required` — the dedicated Miro browser profile requires a login;
- `provider_ui_unresolved` — the authenticated provider UI did not expose a complete readback;
- `provider_configuration_drift` — URL, app identity, team, or scopes differ;
- `installation_or_authorization_required` — the app is unavailable on the board;
- `oauth_or_sdk_authorization_required` — the panel cannot access the Web SDK;
- `in_board_readback_incomplete` — the panel, build, API, or board readback is incomplete;
- `provider_unavailable` — the provider did not reach a stable bounded read state.

An attention receipt newer than the current successful generation is active. A later successful
generation keeps the historical receipt but marks it as superseded in `evidence-status`.

## Timer installation

Create or verify the hardened user service and timer:

```bash
schauwerk miro companion evidence-install-timer CONFIG --cli-executable /absolute/path/to/schauwerk --json
```

Enable it only after the installed CLI revision and live capture have been verified:

```bash
schauwerk miro companion evidence-install-timer CONFIG --cli-executable /absolute/path/to/schauwerk --enable --replace --json
```

The generated oneshot service uses an owner-only umask, a read-only home boundary with narrow
write exceptions for the evidence state and dedicated browser profile, `NoNewPrivileges`, and a
private temporary directory. The timer is persistent and adds a randomized delay. A normal run
returns `refresh=not_due` without opening a browser while the current generation remains outside
the refresh window.

## Recovery and boundaries

If Miro invalidates the session, log in manually with the dedicated profile and rerun a forced
capture. Do not copy cookies into repository state and do not widen the command into hidden
login or consent automation.

The refresh establishes evidence only until its recorded expiry. It does not establish future
provider availability, subjective visual quality, permission for board mutation, or permission
to reveal or reuse OAuth, REST, or browser credentials.
