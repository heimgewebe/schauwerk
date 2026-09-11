from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_editor_defaults_to_24px_and_left_aligned_text(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    app_js = (output / "app.js").read_text(encoding="utf-8")
    helper_js = (output / "canvas-import.js").read_text(encoding="utf-8")

    assert "const DEFAULT_EDITOR_FONT_SIZE = 24;" in app_js
    assert "let preferredNodeFontSize = DEFAULT_EDITOR_FONT_SIZE;" in app_js
    assert "?? DEFAULT_EDITOR_FONT_SIZE" in app_js
    assert "return nodeFontSize;" in app_js
    assert 'config.defaultVertexStyle.align = "left";' in app_js
    assert "fontStyle=1;align=left;container=0" in helper_js
    assert "fontSize=${fontSize};align=left;spacing=12;" in helper_js
