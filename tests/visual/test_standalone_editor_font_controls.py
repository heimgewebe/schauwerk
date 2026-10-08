from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_single_workspace_keeps_exports_and_tools_compact_without_canvas_gutters(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert 'id="fullscreenButton"' not in index_html
    assert "toggleEditorFullscreen" not in app_js
    assert "requestFullscreen" not in app_js
    assert "fullscreenchange" not in app_js

    assert (
        '<details class="workspace-menu workspace-tools-menu" name="workspace-menu">'
        in index_html
    )
    assert (
        '<details class="workspace-menu workspace-export-menu" name="workspace-menu">'
        in index_html
    )
    assert (
        '<summary class="button compact"><span class="workspace-menu-label">'
        'Werkzeuge</span></summary>'
    ) in index_html
    assert (
        '<summary class="button compact"><span class="workspace-menu-label">'
        'Export</span></summary>'
    ) in index_html
    assert index_html.index('id="workspaceCloseButton"') < index_html.index("</nav>")
    assert ">Zurück</button>" in index_html

    assert ".workspace-bar {" in styles_css
    workspace_bar = styles_css[
        styles_css.index(".workspace-bar {") : styles_css.index(".workspace-menu {")
    ]
    assert "flex-wrap: nowrap;" in workspace_bar
    assert "min-height: 44px;" in workspace_bar
    assert "max-width: calc(100vw - 16px);" in workspace_bar
    assert ".workspace-popover {" in styles_css
    assert "bottom: calc(100% + 7px);" in styles_css

    assert "body.workspace-active.engine-legacy .editor-stage {" not in styles_css
    assert "padding-right: max(56px, calc(env(safe-area-inset-right) + 48px));" not in styles_css
    assert "padding-bottom: max(64px, calc(env(safe-area-inset-bottom) + 56px));" not in styles_css
    assert "--workspace-dock-height" not in styles_css
    assert "--workspace-dock-bottom" not in styles_css
    assert "syncWorkspaceDockHeight" not in app_js
    assert "workspaceDockResizeObserver" not in app_js
    assert 'workspaceBar: document.querySelector(".workspace-bar")' not in app_js

    assert 'document.body.classList.toggle("engine-native", native);' in app_js
    assert 'document.body.classList.toggle("engine-legacy", !native);' in app_js
    assert 'fontControls.hidden = native;' in app_js
    assert 'elements.layoutButton.hidden = native;' in app_js
    assert 'pngButton.hidden = native;' in app_js
    assert 'elements.projectButton.textContent = "Canvas";' in app_js
    assert 'elements.projectButton.textContent = "Original";' in app_js
    assert 'elements.projectButton.textContent = "Quelle";' in app_js
    assert 'elements.projectButton.textContent = "Projekt";' in app_js
    assert 'elements.workspaceCloseButton.addEventListener("click", showStart);' in app_js

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "min-height: 42px;" in mobile_css
    assert mobile_css.count(
        "100vw - max(6px, env(safe-area-inset-left))"
    ) == 2
    assert mobile_css.count(
        "- max(6px, env(safe-area-inset-right))"
    ) == 2
    assert "body.workspace-active { --workspace-bar-height: 52px; }" in mobile_css
    popover_start = mobile_css.index(".workspace-popover {")
    popover_rule = mobile_css[popover_start : mobile_css.index("}", popover_start) + 1]
    assert "position: fixed;" in popover_rule
    assert "right: max(6px, env(safe-area-inset-right));" in popover_rule
    assert (
        "bottom: calc(var(--workspace-bar-bottom) + var(--workspace-bar-height) + 7px);"
        in popover_rule
    )
    assert "100vw - max(6px, env(safe-area-inset-left))" in popover_rule
    assert "- max(6px, env(safe-area-inset-right))" in popover_rule
    assert "padding: 5px;" in popover_rule

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


def test_prepared_download_stays_inside_compact_workspace_without_reflow_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert 'id="downloadLink" hidden' in index_html
    clear_download = app_js[
        app_js.index("function clearPreparedDownload()")
        : app_js.index("function prepareDownload(")
    ]
    prepare_download = app_js[
        app_js.index("function prepareDownload(")
        : app_js.index("function setWorkspaceActive(")
    ]

    assert "elements.downloadLink.hidden = true;" in clear_download
    assert "elements.downloadLink.hidden = false;" in prepare_download
    assert "elements.downloadLink.textContent = `${label} speichern`;" in prepare_download
    assert "queueWorkspaceDockHeightSync" not in clear_download
    assert "queueWorkspaceDockHeightSync" not in prepare_download
    assert "style.setProperty" not in clear_download
    assert "style.setProperty" not in prepare_download
