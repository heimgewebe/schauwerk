from __future__ import annotations

import json
from pathlib import Path

from schauwerk.visual.native_viewer import build_native_viewer

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/system-landscape-v1.json"


def test_native_viewer_uses_product_language_and_wrapping_toolbar(tmp_path: Path) -> None:
    output = tmp_path / "viewer"
    build_native_viewer(json.loads(GOLDEN.read_text(encoding="utf-8")), output)

    html = (output / "index.html").read_text(encoding="utf-8")
    css = (output / "styles.css").read_text(encoding="utf-8")
    app = (output / "app.js").read_text(encoding="utf-8")

    assert "Native SVG · Phase 2" not in html
    assert "Arbeitsfläche" in html
    assert 'class="view-controls"' in html
    assert 'class="edit-controls document-only"' in html
    assert ">Positionen zurücksetzen<" in html
    assert 'aria-label="Element hinzufügen"' in html
    assert ">+ Element<" in html
    assert 'aria-label="Verbindung hinzufügen"' in html
    assert ">+ Verbindung<" in html
    assert 'aria-label="Text bearbeiten"' in html
    assert ">Text<" in html
    assert 'aria-label="Anfang ändern"' in html
    assert ">Anfang<" in html
    assert 'aria-label="Ende ändern"' in html
    assert ">Ende<" in html

    for control_id in (
        "zoomOut",
        "zoomIn",
        "fitView",
        "resetLayout",
        "addNode",
        "addEdge",
        "editText",
        "reattachSource",
        "reattachTarget",
        "deleteSelection",
    ):
        assert html.count(f'id="{control_id}"') == 1

    assert ".controls { overflow-x: auto;" not in css
    assert "flex-wrap: wrap;" in css
    assert "button:disabled {" in css
    assert ".document-editor-hosted .viewer-bar {" in css
    assert 'document.body.classList.toggle("document-editor-hosted", documentEditorHosted);' in app
    assert "function updateDocumentToolbarState()" in app
    assert '"Ansicht angepasst"' in app
    assert '"Positionen zurückgesetzt"' in app
    assert "Semantik unverändert" not in app
