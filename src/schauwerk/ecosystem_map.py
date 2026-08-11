from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path
from typing import Any

from .resilience_view import ResilienceViewError, compile_resilience_view

MANIFEST_KIND = 'system_catalog_map_artifact_manifest'
RENDER_KIND = 'schauwerk_ecosystem_map_html_handoff'


class EcosystemMapRenderError(ValueError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise EcosystemMapRenderError(f'manifest not found: {path}') from exc
    except json.JSONDecodeError as exc:
        raise EcosystemMapRenderError(f'manifest is invalid JSON: {exc.msg}') from exc
    if not isinstance(data, dict):
        raise EcosystemMapRenderError('manifest root must be an object')
    identity_mismatch = (
        data.get('kind') != MANIFEST_KIND
        or data.get('schemaVersion') != 1
        or data.get('contractVersion') != '1'
    )
    if identity_mismatch:
        raise EcosystemMapRenderError('manifest kind or schema version mismatch')
    source = data.get('source')
    if not isinstance(source, dict) or source.get('repository') != 'heimgewebe/systemkatalog':
        raise EcosystemMapRenderError('manifest source mismatch')
    commit = source.get('commit')
    commit_invalid = (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(ch not in '0123456789abcdef' for ch in commit)
    )
    if commit_invalid:
        raise EcosystemMapRenderError('manifest source commit must be a lowercase git SHA')
    return data


def _source_root(manifest_path: Path, source_root: str | None) -> Path:
    if source_root:
        return Path(source_root).resolve()
    directory = manifest_path.resolve().parent
    return directory.parent if directory.name == 'rendered' else directory


def _artifact(manifest: dict[str, Any], role: str) -> dict[str, Any]:
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, list):
        raise EcosystemMapRenderError('manifest artifacts must be a list')
    for item in artifacts:
        if isinstance(item, dict) and item.get('role') == role:
            return item
    raise EcosystemMapRenderError(f'manifest lacks artifact role: {role}')


def _artifact_optional(manifest: dict[str, Any], role: str) -> dict[str, Any] | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise EcosystemMapRenderError("manifest artifacts must be a list")
    for item in artifacts:
        if isinstance(item, dict) and item.get("role") == role:
            return item
    return None


def _safe_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or '..' in path.parts:
        raise EcosystemMapRenderError(f'artifact path escapes source root: {raw}')
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EcosystemMapRenderError(f'artifact path escapes source root: {raw}') from exc
    return resolved


def _read_artifact(root: Path, item: dict[str, Any]) -> tuple[str, str, int, str]:
    raw = item.get('path')
    digest = item.get('sha256')
    byte_count = item.get('bytes')
    if not isinstance(raw, str) or not isinstance(digest, str) or not isinstance(byte_count, int):
        raise EcosystemMapRenderError('artifact fields are incomplete')
    text = _safe_path(root, raw).read_text(encoding='utf-8')
    if len(text.encode('utf-8')) != byte_count:
        raise EcosystemMapRenderError(f'artifact byte count mismatch: {raw}')
    if _sha(text) != digest:
        raise EcosystemMapRenderError(f'artifact digest mismatch: {raw}')
    return raw, text, byte_count, digest


def _page(
    manifest: dict[str, Any],
    manifest_path: Path,
    source_root: Path,
    map_artifact: tuple[str, str, int, str],
    resilience_html: str,
) -> str:
    source = manifest["source"]
    map_path, map_text, map_bytes, map_sha = map_artifact
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Systemkatalog Ecosystem Map Handoff</title>
<style>
:root {{ font-family: system-ui, sans-serif; color-scheme: light dark; }}
body {{ max-width: 118rem; margin: 0 auto; padding: 1.5rem; line-height: 1.45; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
code {{ overflow-wrap: anywhere; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; margin-block: 1rem 2rem; }}
th, td {{ border: 1px solid currentColor; padding: .45rem; text-align: left; vertical-align: top; }}
.catalog-section {{ border-inline-start: .45rem double currentColor; padding-inline-start: 1rem; }}
.operational-section {{ border: .2rem dashed currentColor; padding: 1rem; margin-block: 2rem; }}
.authority-label {{ letter-spacing: .06em; text-transform: uppercase; }}
details {{ border-block-start: 1px solid currentColor; padding-block: .5rem; }}
summary {{ cursor: pointer; font-weight: 650; }}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: .001ms !important; animation-iteration-count: 1 !important;
    transition-duration: .001ms !important; scroll-behavior: auto !important;
  }}
}}
</style></head>
<body data-render-kind="{RENDER_KIND}" data-render-mode="source-html">
<a href="#resilience-catalog">Direkt zur Resilienzsemantik</a>
<h1>Systemkatalog Ecosystem Map Handoff</h1>
<p><strong>Boundary:</strong> read-only presentation handoff from the canonical
Systemkatalog map artifact.</p>
<dl>
<dt>System catalog commit</dt><dd>{escape(source['commit'])}</dd>
<dt>Manifest</dt><dd>{escape(str(manifest_path))}</dd>
<dt>Source root</dt><dd>{escape(str(source_root))}</dd>
</dl>
<section>
<h2>Canonical ecosystem map Mermaid source</h2>
<p>{escape(map_path)} · {map_bytes} bytes · sha256 {escape(map_sha)}</p>
<pre>{escape(map_text)}</pre>
</section>
{resilience_html}
</body></html>
"""


def render_ecosystem_map_html(
    *,
    manifest_path: Path,
    output_path: Path,
    source_root: str | None = None,
    operational_overlay_path: Path | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    root = _source_root(manifest_path, source_root)
    manifest = _load_manifest(manifest_path)
    map_artifact = _read_artifact(root, _artifact(manifest, "canonical_ecosystem_map_mermaid"))

    resilience_item = _artifact_optional(manifest, "resilience_semantics")
    resilience_view: dict[str, Any] | None = None
    resilience_sha256: str | None = None
    if resilience_item is not None:
        _, resilience_text, _, resilience_sha256 = _read_artifact(root, resilience_item)
        try:
            resilience = json.loads(resilience_text)
        except json.JSONDecodeError as exc:
            raise EcosystemMapRenderError(
                f"resilience semantics artifact is invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(resilience, dict):
            raise EcosystemMapRenderError("resilience semantics artifact root must be an object")
        try:
            resilience_view = compile_resilience_view(
                resilience,
                operational_overlay_path=operational_overlay_path,
                evaluated_at=evaluated_at,
            )
        except ResilienceViewError as exc:
            raise EcosystemMapRenderError(str(exc)) from exc
    elif operational_overlay_path is not None:
        raise EcosystemMapRenderError(
            "operational overlay requires the manifest resilience_semantics artifact"
        )

    resilience_html = (
        resilience_view["html"]
        if resilience_view is not None
        else (
            '<section id="resilience-catalog" class="catalog-section">'
            '<p class="authority-label"><strong>'
            'KATALOG · RESILIENZ NICHT VERÖFFENTLICHT</strong></p>'
            '<h2>Resilienzsemantik</h2><p>Dieses ältere Manifest enthält keine digest-geprüfte '
            'Rolle <code>resilience_semantics</code>. Schauwerk leitet daraus keine Ersatzsemantik '
            'und keine Live-Aussage ab.</p></section>'
        )
    )
    html = _page(manifest, manifest_path, root, map_artifact, resilience_html)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    receipt = {
        "kind": RENDER_KIND,
        "mode": "source_html",
        "output": str(output_path),
        "output_sha256": _sha(html),
        "source_repository": manifest["source"]["repository"],
        "source_commit": manifest["source"]["commit"],
        "manifest": str(manifest_path),
        "source_root": str(root),
        "diagram_rendered": False,
        "resilience_rendered": resilience_view is not None,
        "resilience_sha256": resilience_sha256,
        "operational_truth_inferred": False,
    }
    if resilience_view is not None:
        receipt.update(
            {
                "resilience_system_count": resilience_view["system_count"],
                "resilience_relation_count": resilience_view["relation_count"],
                "failure_domain_count": resilience_view["failure_domain_count"],
                "recovery_mode_count": resilience_view["recovery_mode_count"],
                "blast_radius_group_count": resilience_view["blast_radius_group_count"],
                "operational_overlay": resilience_view["operational_overlay"],
            }
        )
    return receipt
