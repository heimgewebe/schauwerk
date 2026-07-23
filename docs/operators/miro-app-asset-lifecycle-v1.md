# Miro app asset lifecycle v1

Schauwerk treats `src/schauwerk/web_sdk_assets/app-icon-outline.svg` and `app-icon-color.svg` as the canonical Miro Developer App icon bytes. Their SHA-256 digests are pinned in `schauwerk.surfaces.miro.app_assets` and validated fail-closed before an upload or readback receipt can be constructed.

The contract requires a positive square SVG `viewBox`, a bounded allow-list of passive SVG elements, direct paint colors, no scriptable or linked content, and a monochrome outline icon. The exact bytes must end in one newline and match the pinned verified digests. No external fonts are used.

A live provider update is a separate reviewed effect. Its receipt uses `miro-app-asset-receipt.v1.schema.json` and binds the existing app ID, canonical HTTPS app URL, exactly `boards:read`, both asset digests, upload responses, and authenticated provider readback. Credentials, tokens, cookies, and browser session material must never be stored in the receipt. The app must not be recreated or uninstalled.
