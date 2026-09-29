from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_product_shell_is_coherent_and_responsive(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    index_html = (output / "index.html").read_text(encoding="utf-8")
    styles_css = (output / "styles.css").read_text(encoding="utf-8")

    assert "Vom Gedanken zum Schaubild." in index_html
    assert 'class="start-layout"' in index_html
    assert 'class="import-panel"' in index_html
    assert '<details class="advanced-settings">' in index_html
    assert 'class="advanced-utility-actions"' in index_html
    assert "SCHAUWERK_AI_HANDOFF_ACTION" in index_html
    assert ">Leeres Schaubild<" in index_html
    assert ">Legacy leer<" not in index_html

    for class_name in (
        "workspace-leading",
        "workspace-tools",
        "workspace-output",
        "font-controls",
        "editor-stage",
    ):
        assert f'class="{class_name}' in index_html

    assert "[hidden] { display: none !important; }" in styles_css
    assert "grid-template-columns: minmax(0, 1fr) auto auto auto;" in styles_css
    assert "@media (max-width: 1180px)" in styles_css
    assert "@media (max-width: 760px)" in styles_css
    assert ".workspace-bar { overflow-x: auto; }" not in styles_css
    assert ".workspace-tools,\n.workspace-output" in styles_css
    assert "flex-wrap: wrap;" in styles_css

    mobile_css = styles_css[
        styles_css.index("@media (max-width: 760px)") : styles_css.index(
            "@media (max-width: 420px)"
        )
    ]
    assert "font-size: clamp(2.85rem, 13.2vw, 4rem)" in mobile_css
    assert "min-height: 160px" in mobile_css
    assert ".workspace-leading {" in mobile_css
    assert "grid-column: 1;" in mobile_css
    assert ".font-controls {" in mobile_css
    assert "grid-column: 2;" in mobile_css
    assert "grid-row: 1;" in mobile_css
    assert ".workspace-tools {" in mobile_css
    assert "grid-row: 2;" in mobile_css
    assert ".workspace-output {" in mobile_css
    assert "flex-wrap: nowrap;" in mobile_css
