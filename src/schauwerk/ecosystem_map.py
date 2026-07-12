from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path
from typing import Any

MANIFEST_KIND = "system_catalog_map_artifact_manifest"
RENDER_KIND = "schauwerk_ecosystem_map_html_handoff"


class EcosystemMapRenderError(ValueError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EcosystemMapRenderError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EcosystemMapRenderError(f"manifest is invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise EcosystemMapRenderError("manifest root must be an object")
    identity_mismatch = (
        data.get("kind") != MANIFEST_KIND
        or data.get("schemaVersion") != 1
        or data.get("contractVersion") != "1"
    )
    if identity_mismatch:
        raise EcosystemMapRenderError("manifest kind or schema version mismatch")
    source = data.get("source")
    if not isinstance(source, dict) or source.get("repository") != "heimgewebe/systemkatalog":
        raise EcosystemMapRenderError("manifest source mismatch")
    commit = source.get("commit")
    commit_invalid = (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(ch not in "0123456789abcdef" for ch in commit)
    )
    if commit_invalid:
        raise EcosystemMapRenderError("manifest source commit must be a lowercase git SHA")
    return data


def _source_root(manifest_path: Path, source_root: str | None) -> Path:
    if source_root:
        return Path(source_root).resolve()
    directory = manifest_path.resolve().parent
    return directory.parent if directory.name == "rendered" else directory


def _artifact(manifest: dict[str, Any], role: str) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise EcosystemMapRenderError("manifest artifacts must be a list")
    for item in artifacts:
        if isinstance(item, dict) and item.get("role") == role:
            return item
    raise EcosystemMapRenderError(f"manifest lacks artifact role: {role}")


def _safe_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise EcosystemMapRenderError(f"artifact path escapes source root: {raw}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EcosystemMapRenderError(f"artifact path escapes source root: {raw}") from exc
    return resolved


def _read_artifact(root: Path, item: dict[str, Any]) -> tuple[str, str, int, str]:
    raw = item.get("path")
    digest = item.get("sha256")
    byte_count = item.get("bytes")
    if not isinstance(raw, str) or not isinstance(digest, str) or not isinstance(byte_count, int):
        raise EcosystemMapRenderError("artifact fields are incomplete")
    text = _safe_path(root, raw).read_text(encoding="utf-8")
    if len(text.encode("utf-8")) != byte_count:
        raise EcosystemMapRenderError(f"artifact byte count mismatch: {raw}")
    if _sha(text) != digest:
        raise EcosystemMapRenderError(f"artifact digest mismatch: {raw}")
    return raw, text, byte_count, digest


def _page(
    manifest: dict[str, Any],
    manifest_path: Path,
    source_root: Path,
    map_artifact: tuple[str, str, int, str],
) -> str:
    source = manifest["source"]
    map_path, map_text, map_bytes, map_sha = map_artifact
    return f'''<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Systemkatalog Ecosystem Map Handoff</title></head>
<body data-render-kind="{RENDER_KIND}" data-render-mode="source-html">
<h1>Systemkatalog Ecosystem Map Handoff</h1>
<p><strong>Boundary:</strong> read-only presentation handoff from the canonical
Systemkatalog map artifact.</p>
<dl>
<dt>System catalog commit</dt><dd>{escape(source["commit"])}</dd>
<dt>Manifest</dt><dd>{escape(str(manifest_path))}</dd>
<dt>Source root</dt><dd>{escape(str(source_root))}</dd>
</dl>
<section>
<h2>Canonical ecosystem map Mermaid source</h2>
<p>{escape(map_path)} · {map_bytes} bytes · sha256 {escape(map_sha)}</p>
<pre>{escape(map_text)}</pre>
</section>
</body></html>
'''


def render_ecosystem_map_html(
    *,
    manifest_path: Path,
    output_path: Path,
    source_root: str | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    root = _source_root(manifest_path, source_root)
    manifest = _load_manifest(manifest_path)
    map_artifact = _read_artifact(root, _artifact(manifest, "canonical_ecosystem_map_mermaid"))
    html = _page(manifest, manifest_path, root, map_artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return {
        "kind": RENDER_KIND,
        "mode": "source_html",
        "output": str(output_path),
        "output_sha256": _sha(html),
        "source_repository": manifest["source"]["repository"],
        "source_commit": manifest["source"]["commit"],
        "manifest": str(manifest_path),
        "source_root": str(root),
        "diagram_rendered": False,
    }
