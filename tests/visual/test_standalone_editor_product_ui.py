from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_product_shell_is_single_workspace_and_responsive(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert "Vom Gedanken zum Schaubild." in index_html
    assert 'class="start-layout"' in index_html
    assert 'class="import-panel"' in index_html
    assert '<details class="advanced-settings">' in index_html
    assert ">Leeres Schaubild<" in index_html

    assert index_html.count('id="workspace"') == 1
    assert index_html.count('class="editor-stage"') == 1
    assert (
        '<details class="workspace-menu workspace-tools-menu" name="workspace-menu">'
        in index_html
    )
    assert (
        '<details class="workspace-menu workspace-export-menu" name="workspace-menu">'
        in index_html
    )
    assert 'class="workspace-popover workspace-tools-popover"' in index_html
    assert 'class="workspace-popover workspace-output"' in index_html
    assert 'id="backButton"' not in index_html
    assert 'id="fullscreenButton"' not in index_html
    assert 'id="workspaceCloseButton"' in index_html
    assert 'id="projectButton"' in index_html
    assert 'data-export="png"' in index_html
    assert 'data-export="svg"' in index_html

    assert "[hidden] { display: none !important; }" in styles_css
    assert "height: 100dvh;" in styles_css
    assert ".workspace-bar {" in styles_css
    assert ".workspace-popover {" in styles_css
    assert "--workspace-bar-height: 44px;" in styles_css
    assert "--workspace-dock-height" not in styles_css
    assert "body.workspace-active.engine-legacy .editor-stage {" not in styles_css
    assert "body.editor-focus" not in styles_css
    assert ".fullscreen-toggle" not in styles_css
    assert ".workspace-bar { overflow-x: auto; }" not in styles_css
    # A :has() rule must not invalidate the legacy fallback in older Safari.
    assert "body.engine-legacy .workspace-tools-menu {\n  display: none;\n}" in styles_css
    assert "body.engine-legacy .workspace-tools-menu,\n" not in styles_css

    assert "fontControls.hidden = native;" in app_js
    assert "elements.layoutButton.hidden = native;" in app_js
    assert "pngButton.hidden = native;" in app_js
    assert 'elements.projectButton.textContent = "Canvas";' in app_js
    assert 'elements.projectButton.textContent = "Original";' in app_js
    assert 'elements.projectButton.textContent = "Quelle";' in app_js
    assert 'elements.projectButton.textContent = "Projekt";' in app_js
    assert "function setWorkspaceActive(active)" in app_js
    assert "setWorkspaceActive(true);" in app_js
    assert 'elements.workspaceCloseButton.addEventListener("click", showStart);' in app_js
    assert "toggleEditorFullscreen" not in app_js
    assert "syncWorkspaceDockHeight" not in app_js
    assert "ResizeObserver" not in app_js

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "font-size: clamp(2.85rem, 13.2vw, 4rem)" in mobile_css
    assert "min-height: 160px" in mobile_css
    assert ".workspace-bar {" in mobile_css
    assert "right: max(6px, env(safe-area-inset-right));" in mobile_css
    assert mobile_css.count(
        "100vw - max(6px, env(safe-area-inset-left))"
    ) == 2
    assert mobile_css.count(
        "- max(6px, env(safe-area-inset-right))"
    ) == 2
    assert "min-height: 42px;" in mobile_css

    dark_css = styles_css[styles_css.index("@media (prefers-color-scheme: dark)") :]
    assert ".workspace-popover { background: rgba(16, 18, 25, 0.88); }" in dark_css
    dark_status = dark_css[
        dark_css.index("body.workspace-active .status {")
        : dark_css.index(".paste-box textarea")
    ]
    assert "color: var(--ink);" in dark_status
    assert "background: var(--surface-raised);" in dark_status
    assert "border-color: var(--line-strong);" in dark_status
