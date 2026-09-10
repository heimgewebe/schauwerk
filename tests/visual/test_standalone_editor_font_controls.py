from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_font_controls_remain_reachable_in_focus_and_narrow_layouts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")

    hide_selector = "body.editor-focus .workspace-bar > :not(.fullscreen-toggle)"
    assert styles_css.count(hide_selector) == 1
    show_selector = "body.editor-focus .workspace-bar > .font-controls"
    assert styles_css.count(show_selector) == 1
    assert styles_css.index(hide_selector) < styles_css.index(show_selector)
    focus_controls = styles_css[
        styles_css.index(f"{show_selector} {{")
        : styles_css.index("body.editor-focus .font-controls .button")
    ]
    assert "display: inline-flex;" in focus_controls
    assert "pointer-events: auto;" in focus_controls

    assert "@media (max-width: 1024px)" in styles_css
    assert ".workspace-bar > .font-controls { order: -2; }" in styles_css
    assert ".workspace-bar > .fullscreen-toggle { order: -1; }" in styles_css

    for control_id in (
        "fontDecreaseButton",
        "fontPanelButton",
        "fontIncreaseButton",
        "fontAllButton",
        "fullscreenButton",
    ):
        assert index_html.count(f'id="{control_id}"') == 1
