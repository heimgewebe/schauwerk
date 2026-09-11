from __future__ import annotations

from pathlib import Path

from schauwerk.visual.standalone_editor import build_standalone_editor


def test_editor_defaults_to_24px_and_left_aligned_text(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)

    app_js = (output / "app.js").read_text(encoding="utf-8")
    helper_js = (output / "canvas-import.js").read_text(encoding="utf-8")

    assert "READABLE_NODE_FONT_SIZE = 18" in helper_js
    assert "READABLE_EDGE_FONT_SIZE = 16" in helper_js
    assert "const PRODUCT_DEFAULT_NODE_FONT_SIZE = 24;" in app_js
    assert "const PRODUCT_DEFAULT_EDGE_FONT_SIZE = 22;" in app_js
    assert "let preferredNodeFontSize = PRODUCT_DEFAULT_NODE_FONT_SIZE;" in app_js
    assert "?? PRODUCT_DEFAULT_NODE_FONT_SIZE" in app_js
    assert "PRODUCT_DEFAULT_NODE_FONT_SIZE - PRODUCT_DEFAULT_EDGE_FONT_SIZE" in app_js
    assert "let pendingCreationDefaults = false;" in app_js
    creation_defaults = (
        'sourceFormat === "mermaid" || sourceFormat === "json-canvas-1.0" || '
        "load?.xml === emptyDrawioXml()"
    )
    assert creation_defaults in app_js
    assert "if (pendingCreationDefaults)" in app_js
    assert 'config.defaultVertexStyle.align = "left";' in app_js
    assert "fontStyle=1;align=left;container=0" in helper_js
    assert "fontSize=${fontSize};align=left;spacing=12;" in helper_js
    assert app_js.index("if (pendingCreationDefaults)") < app_js.index(
        'config.defaultVertexStyle.align = "left";'
    )


def test_existing_drawio_and_drafts_do_not_receive_creation_defaults(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    app_js = (output / "app.js").read_text(encoding="utf-8")

    assert 'if (detected.kind === "drawio")' in app_js
    assert "return { xml: validateDiagramXml(detected.text) };" in app_js
    assert "launch({ xml: draft.xml });" in app_js
    assert "pendingCreationDefaults = false;" in app_js
    assert "if (pendingCreationDefaults)" in app_js
