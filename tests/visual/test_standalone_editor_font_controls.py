from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_single_workspace_preserves_legacy_controls_and_exports(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert "body.editor-focus" not in styles_css
    assert ".fullscreen-toggle" not in styles_css
    assert 'id="fullscreenButton"' not in index_html
    assert "toggleEditorFullscreen" not in app_js

    assert "body.workspace-active .topline { display: none; }" in styles_css
    assert ".workspace-bar {" in styles_css
    assert "bottom: max(44px, calc(env(safe-area-inset-bottom) + 36px));" in styles_css
    assert ".workspace-close {" in styles_css
    close_controls = styles_css[
        styles_css.index(".workspace-close {") : styles_css.index(".workspace-close:hover")
    ]
    assert "position: fixed;" in close_controls
    assert "top: max(8px, env(safe-area-inset-top));" in close_controls
    assert "right: max(8px, env(safe-area-inset-right));" in close_controls

    assert 'document.body.classList.toggle("engine-native", native);' in app_js
    assert 'document.body.classList.toggle("engine-legacy", !native);' in app_js
    assert 'fontControls.hidden = native;' in app_js
    assert 'elements.layoutButton.hidden = native;' in app_js
    assert 'pngButton.hidden = native;' in app_js
    assert 'elements.projectButton.textContent = "Canvas";' in app_js
    assert 'elements.workspaceCloseButton.addEventListener("click", showStart);' in app_js

    assert "@media (max-width: 760px)" in styles_css
    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "left: max(8px, env(safe-area-inset-left));" in mobile_css
    assert "right: max(8px, env(safe-area-inset-right));" in mobile_css
    assert "min-height: 42px;" in mobile_css

    for control_id in (
        "fontDecreaseButton",
        "fontPanelButton",
        "fontIncreaseButton",
        "fontAllButton",
        "layoutButton",
        "projectButton",
        "workspaceCloseButton",
    ):
        assert index_html.count(f'id="{control_id}"') == 1

    assert index_html.count('data-export="png"') == 1
    assert index_html.count('data-export="svg"') == 1
