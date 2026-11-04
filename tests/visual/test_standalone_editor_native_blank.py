"""Regressions for a native-first blank canvas and accessible start controls."""
from __future__ import annotations

from pathlib import Path

from schauwerk.visual.native_diagram import render_native_editing_document
from schauwerk.visual.standalone_editor import (
    _native_product_input,
    build_standalone_editor,
)


def test_blank_starts_native_canvas_and_legacy_remains_explicit(tmp_path: Path) -> None:
    output = tmp_path / "editor"
    build_standalone_editor(output)
    html = (output / "index.html").read_text(encoding="utf-8")
    js = (output / "app.js").read_text(encoding="utf-8")

    blank = js.split('elements.blankButton.addEventListener("click", () => {', 1)[1]
    blank, rest = blank.split('elements.legacyBlankButton.addEventListener("click", () => {', 1)
    assert "nativeImport:" in blank
    assert 'format: "json-canvas-1.0"' in blank
    assert "nodes: [], edges: []" in blank
    assert "emptyDrawioXml()" not in blank
    assert "launch({ xml: emptyDrawioXml() });" in rest.split(
        'elements.restoreButton.addEventListener', 1
    )[0]
    assert 'id="legacyBlankButton"' in html
    assert 'role="group" aria-label="Unterstützte Eingaben"' in html
    assert 'Schaubild-Quelle oder KI-Ergebnis hier einfügen' in html


def test_empty_json_canvas_renders_as_native_editing_document() -> None:
    doc = _native_product_input(
        {
            "schema_version": "schauwerk-native-import-request.v1",
            "format": "json-canvas-1.0",
            "source": {"nodes": [], "edges": []},
            "title": "Schaubild",
        }
    )
    assert doc["schema_version"] == "schauwerk-native-editing-document.v1"
    assert doc["nodes"] == []
    assert doc["edges"] == []
    svg = render_native_editing_document(doc)
    assert "<svg " in svg
    assert 'viewBox="0 0 1200 800"' in svg
