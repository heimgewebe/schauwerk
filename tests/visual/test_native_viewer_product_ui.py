from __future__ import annotations

import json
from pathlib import Path

from schauwerk.visual.native_viewer import build_native_viewer

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs/operators/fixtures/golden/system-landscape-v1.json"


def test_native_viewer_uses_compact_accessible_overlay_controls(tmp_path: Path) -> None:
    output = tmp_path / "viewer"
    build_native_viewer(json.loads(GOLDEN.read_text(encoding="utf-8")), output)

    html = (output / "index.html").read_text(encoding="utf-8")
    css = (output / "styles.css").read_text(encoding="utf-8")
    app = (output / "app.js").read_text(encoding="utf-8")

    assert "Native SVG · Phase 2" not in html
    assert "Arbeitsfläche" in html
    assert 'class="view-controls"' in html
    assert '<details class="edit-controls document-only" hidden>' in html
    assert "<summary>Bearbeiten</summary>" in html
    assert 'id="resetLayout" class="icon-control"' in html
    assert 'aria-label="Positionen zurücksetzen"' in html
    assert ">↺</button>" in html
    assert ">Positionen zurücksetzen<" not in html
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

    viewer_shell = css[css.index(".viewer-shell {") : css.index(".viewer-bar {")]
    viewer_bar = css[css.index(".viewer-bar {") : css.index(".viewer-heading {")]
    viewer_stage = css[css.index(".viewer-stage {") : css.index(".viewer-stage.is-panning")]
    viewer_foot = css[css.index(".viewer-foot {") : css.index(".viewer-foot span:first-child")]

    assert "position: relative;" in viewer_shell
    assert "grid-template-rows:" not in viewer_shell
    assert "position: absolute;" in viewer_bar
    assert "background: transparent;" in viewer_bar
    assert "position: absolute;" in viewer_stage
    assert "inset: 0;" in viewer_stage
    assert "position: absolute;" in viewer_foot
    assert ".edit-menu {" in css
    assert ".embedded-native-viewer .viewer-bar {" not in css
    assert "padding-right: max(58px, calc(env(safe-area-inset-right) + 50px));" not in css
    assert "@media (max-width: 620px)" in css
    assert "button { min-width: 42px; min-height: 42px; }" in css

    assert "const embeddedNativeViewer = window.parent !== window;" in app
    assert 'document.body.classList.toggle("embedded-native-viewer", embeddedNativeViewer);' in app
    assert 'document.body.classList.toggle("document-editor-hosted", documentEditorHosted);' in app
    assert "function updateDocumentToolbarState()" in app
    assert "control.hidden = !visible;" in app
    assert "const VIEWPORT_FIT_PADDING = 48;" in app
    assert "const EMBEDDED_VIEWPORT_FIT_PADDING = Object.freeze({" in app
    assert "top: 60," in app
    assert "bottom: 104," in app
    assert (
        "embeddedNativeViewer ? EMBEDDED_VIEWPORT_FIT_PADDING : VIEWPORT_FIT_PADDING,"
        in app
    )
    assert '"Ansicht angepasst"' in app
    assert '"Positionen zurückgesetzt"' in app
    assert "Semantik unverändert" not in app
