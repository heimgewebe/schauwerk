from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_product_shell_is_coherent_and_responsive(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert "Vom Gedanken zum Schaubild." in index_html
    assert 'class="start-layout"' in index_html
    assert 'class="import-panel"' in index_html
    assert '<details class="advanced-settings">' in index_html
    assert 'class="advanced-utility-actions"' in index_html
    assert "SCHAUWERK_AI_HANDOFF_ACTION" in index_html
    assert ">Leeres Schaubild<" in index_html
    assert ">Legacy leer<" not in index_html
    assert "Öffne Text," not in index_html
    assert "<span>Text</span>" not in index_html
    assert 'placeholder="Text,' not in index_html
    assert "Mermaid, JSON Canvas, draw.io oder Schauwerk-Daten" in index_html

    for class_name in (
        "workspace-tools",
        "workspace-output",
        "font-controls",
        "editor-stage",
    ):
        assert f'class="{class_name}' in index_html

    assert 'class="workspace-leading"' not in index_html
    assert 'id="backButton"' not in index_html
    assert 'id="fullscreenButton"' not in index_html
    assert 'id="workspaceCloseButton"' in index_html
    assert 'id="projectButton"' in index_html
    assert 'data-export="png"' in index_html
    assert 'data-export="svg"' in index_html

    assert "[hidden] { display: none !important; }" in styles_css
    assert "body.workspace-active .topline {" in styles_css
    assert "body.workspace-active .topline { display: none; }" not in styles_css
    assert "body.workspace-active .status {" in styles_css
    assert "body.workspace-active.engine-legacy .editor-stage {" in styles_css
    assert "body.workspace-active.engine-legacy .font-controls," in styles_css
    assert "body.editor-focus" not in styles_css
    assert ".workspace-bar { overflow-x: auto; }" not in styles_css
    assert ".workspace-tools,\n.workspace-output" in styles_css
    assert "flex-wrap: wrap;" in styles_css
    assert "position: absolute;" in styles_css
    assert "bottom: max(44px, calc(env(safe-area-inset-bottom) + 36px));" in styles_css
    assert ".workspace-close {" in styles_css
    assert "position: fixed;" in styles_css
    assert ".button:disabled {" in styles_css

    assert "fontControls.hidden = native;" in app_js
    assert "elements.layoutButton.hidden = native;" in app_js
    assert "pngButton.hidden = native;" in app_js
    assert 'elements.projectButton.textContent = "Canvas";' in app_js
    assert "function setWorkspaceActive(active)" in app_js
    assert "setWorkspaceActive(true);" in app_js
    assert 'elements.workspaceCloseButton.addEventListener("click", showStart);' in app_js
    assert "toggleEditorFullscreen" not in app_js

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "font-size: clamp(2.85rem, 13.2vw, 4rem)" in mobile_css
    assert "min-height: 160px" in mobile_css
    assert ".workspace-bar {" in mobile_css
    assert "left: max(8px, env(safe-area-inset-left));" in mobile_css
    assert "right: max(8px, env(safe-area-inset-right));" in mobile_css
    assert "max-width: none;" in mobile_css
    assert ".font-controls { max-width: 100%; flex-wrap: nowrap; }" in mobile_css
    assert ".workspace-tools,\n  .workspace-output { gap: 4px; }" in mobile_css
