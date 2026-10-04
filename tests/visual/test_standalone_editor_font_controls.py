from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_focus_mode_maximizes_workspace_without_covering_legacy_toolbar(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")

    hide_selector = (
        "body.editor-focus .workspace-bar > :not(.font-controls):not(.workspace-output)"
    )
    assert styles_css.count(hide_selector) == 1
    output_selector = "body.editor-focus .workspace-output"
    assert styles_css.count(f"{output_selector} {{") == 1
    assert (
        "body.editor-focus .workspace-output > :not(.fullscreen-toggle) { display: none; }"
        in styles_css
    )
    output_controls = styles_css[
        styles_css.index(f"{output_selector} {{")
        : styles_css.index("body.editor-focus .workspace-output > :not(.fullscreen-toggle)")
    ]
    assert "display: flex;" in output_controls
    assert "pointer-events: none;" in output_controls
    show_selector = "body.editor-focus .workspace-bar > .font-controls"
    assert styles_css.count(show_selector) == 2
    assert styles_css.index(hide_selector) < styles_css.index(show_selector)
    focus_controls = styles_css[
        styles_css.index(f"{show_selector} {{")
        : styles_css.index("body.editor-focus .font-controls .button")
    ]
    assert "display: none;" in focus_controls
    assert "pointer-events: auto;" in focus_controls
    focus_stage_selector = "body.editor-focus .editor-stage"
    focus_stage = styles_css[
        styles_css.index(f"{focus_stage_selector} {{")
        : styles_css.index("body.editor-focus .editor-wrap {")
    ]
    assert "padding: 0;" in focus_stage
    legacy_stage_selector = "body.editor-focus.engine-legacy .editor-stage"
    assert f"{legacy_stage_selector} {{" in styles_css
    legacy_stage = styles_css[
        styles_css.index(f"{legacy_stage_selector} {{")
        : styles_css.index("body.editor-focus .editor-wrap {")
    ]
    assert (
        "padding-right: max(56px, calc(env(safe-area-inset-right) + 48px));"
        in legacy_stage
    )
    assert 'document.body.classList.toggle("engine-native", native);' in app_js
    assert 'document.body.classList.toggle("engine-legacy", !native);' in app_js
    dark_override = (
        f"{show_selector} {{ background: rgba(24, 34, 52, 0.94); }}"
    )
    assert styles_css.count(dark_override) == 1

    assert "@media (max-width: 1024px)" in styles_css
    assert ".workspace-bar > .font-controls { order: -2; }" in styles_css
    assert ".workspace-bar > .fullscreen-toggle { order: -1; }" not in styles_css

    for control_id in (
        "fontDecreaseButton",
        "fontPanelButton",
        "fontIncreaseButton",
        "fontAllButton",
        "fullscreenButton",
    ):
        assert index_html.count(f'id="{control_id}"') == 1
