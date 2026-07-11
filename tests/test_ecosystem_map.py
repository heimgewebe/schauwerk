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
    map_text = "flowchart TD\n  B[Systemkatalog]\n"
    (rendered / "ecosystem-registry-map.mmd").write_text(map_text, encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "kind": "system_catalog_map_artifact_manifest",
        "contractVersion": "1",
        "source": {
            "repository": "heimgewebe/systemkatalog",
            "commit": "a" * 40,
            "generatedAt": "2026-07-05T00:00:00Z",
        },
        "artifacts": [
            {
                "role": "canonical_ecosystem_map_mermaid",
                "path": "rendered/ecosystem-registry-map.mmd",
                "bytes": len(map_text.encode("utf-8")),
                "sha256": _sha(map_text),
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
    assert "System catalog commit" in html
    assert "B[Systemkatalog]" in html
    assert "Canonical ecosystem map Mermaid source" in html
    assert "read-only presentation handoff" in html


def test_render_rejects_byte_count_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"][0]["bytes"] += 1
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="byte count mismatch"):
        render_ecosystem_map_html(manifest_path=manifest_path, output_path=tmp_path / "map.html")


def test_render_rejects_digest_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    artifact_path = tmp_path / "rendered" / "ecosystem-registry-map.mmd"
    original = artifact_path.read_text(encoding="utf-8")
    artifact_path.write_text(original.replace("Systemkatalog", "Systemkatalof"), encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="digest mismatch"):
        render_ecosystem_map_html(manifest_path=manifest_path, output_path=tmp_path / "map.html")


def test_render_rejects_escaping_artifact_path(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"][0]["path"] = "../secret.mmd"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="escapes source root"):
        render_ecosystem_map_html(manifest_path=manifest_path, output_path=tmp_path / "map.html")
