from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from schauwerk.ecosystem_map import EcosystemMapRenderError, render_ecosystem_map_html


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_fixture(root: Path) -> Path:
    rendered = root / "rendered"
    rendered.mkdir(parents=True)
    overview = "flowchart TD\n  A[Cabinet]\n"
    registry = "flowchart TD\n  B[Registry]\n"
    (rendered / "ecosystem-map.mmd").write_text(overview, encoding="utf-8")
    (rendered / "ecosystem-registry-map.mmd").write_text(registry, encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "kind": "cabinet_ecosystem_map_artifact_manifest",
        "source": {
            "repository": "heimgewebe/cabinet",
            "commit": "a" * 40,
            "generatedAt": "2026-07-05T00:00:00Z",
        },
        "artifacts": [
            {
                "role": "readable_overview_mermaid",
                "path": "rendered/ecosystem-map.mmd",
                "bytes": len(overview.encode("utf-8")),
                "sha256": _sha(overview),
            },
            {
                "role": "generated_registry_projection_mermaid",
                "path": "rendered/ecosystem-registry-map.mmd",
                "bytes": len(registry.encode("utf-8")),
                "sha256": _sha(registry),
            },
        ],
    }
    manifest_path = rendered / "ecosystem-map-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_render_ecosystem_map_html_writes_source_handoff(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    output = tmp_path / "out" / "map.html"

    receipt = render_ecosystem_map_html(manifest_path=manifest_path, output_path=output)

    html = output.read_text(encoding="utf-8")
    assert receipt["kind"] == "schauwerk_ecosystem_map_html_handoff"
    assert receipt["mode"] == "source_html"
    assert receipt["diagram_rendered"] is False
    assert receipt["source_commit"] == "a" * 40
    assert "Cabinet commit" in html
    assert "A[Cabinet]" in html
    assert "B[Registry]" in html
    assert "read-only presentation handoff" in html


def test_render_rejects_digest_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    (tmp_path / "rendered" / "ecosystem-map.mmd").write_text("changed", encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="digest mismatch"):
        render_ecosystem_map_html(manifest_path=manifest_path, output_path=tmp_path / "map.html")


def test_render_rejects_escaping_artifact_path(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"][0]["path"] = "../secret.mmd"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="escapes source root"):
        render_ecosystem_map_html(manifest_path=manifest_path, output_path=tmp_path / "map.html")
