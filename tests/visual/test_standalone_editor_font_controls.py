from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_single_workspace_keeps_legacy_exports_clear_of_editor_chrome(
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

    assert "body.workspace-active .topline {" in styles_css
    assert "body.workspace-active .topline { display: none; }" not in styles_css
    assert (
        "body.workspace-active .brand,\n"
        "body.workspace-active .product-badge { display: none; }"
        in styles_css
    )
    assert "body.workspace-active .status {" in styles_css
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
    assert "function syncWorkspaceDockHeight()" in app_js
    assert "queueWorkspaceDockHeightSync();" in app_js
    assert 'new ResizeObserver(() => queueWorkspaceDockHeightSync())' in app_js

    legacy_controls = styles_css[
        styles_css.index("body.workspace-active.engine-legacy .font-controls,")
        : styles_css.index("body.workspace-active.engine-legacy .editor-stage {")
    ]
    assert (
        "body.workspace-active.engine-legacy .workspace-tools { display: none; }"
        in legacy_controls
    )
    legacy_stage = styles_css[
        styles_css.index("body.workspace-active.engine-legacy .editor-stage {")
        : styles_css.index("body.workspace-active.engine-legacy .workspace-bar,")
    ]
    assert "padding-right: max(56px, calc(env(safe-area-inset-right) + 48px));" in legacy_stage
    assert "padding-bottom: max(64px, calc(env(safe-area-inset-bottom) + 56px));" in legacy_stage
    legacy_overlay = styles_css[
        styles_css.index("body.workspace-active.engine-legacy .workspace-bar,")
        : styles_css.index("@media (max-width: 1180px)")
    ]
    assert "bottom: var(--workspace-dock-bottom);" in legacy_overlay

    assert "@media (max-width: 760px)" in styles_css
    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "left: max(8px, env(safe-area-inset-left));" in mobile_css
    assert "right: max(8px, env(safe-area-inset-right));" in mobile_css
    assert "min-height: 42px;" in mobile_css
    assert "body.workspace-active .topline," in mobile_css
    assert "body.workspace-active.engine-legacy .topline {" in mobile_css
    assert (
        "--workspace-dock-bottom: max(42px, calc(env(safe-area-inset-bottom) + 34px));"
        in mobile_css
    )
    assert "bottom: calc(" in mobile_css
    assert "var(--workspace-dock-height)" in mobile_css
    assert "var(--workspace-overlay-gap)" in mobile_css
    assert "bottom: max(104px, calc(env(safe-area-inset-bottom) + 96px));" not in mobile_css
    assert "body.workspace-active.engine-legacy .editor-stage {" in mobile_css
    assert "max-width: min(78vw, 520px);" in mobile_css

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


def test_mobile_workspace_reflows_when_download_link_changes_dock_height(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert 'id="downloadLink" hidden' in index_html
    prepare_download = app_js[
        app_js.index("function prepareDownload(")
        : app_js.index("function setWorkspaceActive(")
    ]
    assert "elements.downloadLink.hidden = false;" in prepare_download
    assert "queueWorkspaceDockHeightSync();" in prepare_download

    clear_download = app_js[
        app_js.index("function clearPreparedDownload()")
        : app_js.index("function prepareDownload(")
    ]
    assert "elements.downloadLink.hidden = true;" in clear_download
    assert "queueWorkspaceDockHeightSync();" in clear_download

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "var(--workspace-dock-height)" in mobile_css
    assert "var(--workspace-overlay-gap)" in mobile_css
    status_rule = mobile_css[
        mobile_css.index("body.workspace-active .topline,")
        : mobile_css.index("body.workspace-active .status {")
    ]
    assert "var(--workspace-dock-height)" in status_rule
    legacy_stage_rule = mobile_css[
        mobile_css.index("body.workspace-active.engine-legacy .editor-stage {")
        :
    ]
    assert "var(--workspace-dock-height)" in legacy_stage_rule
