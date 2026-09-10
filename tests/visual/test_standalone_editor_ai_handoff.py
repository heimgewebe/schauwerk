from __future__ import annotations

import json

from schauwerk.visual.standalone_editor import AI_HANDOFF_PROMPT, build_standalone_editor


def test_ai_handoff_guide_is_copyable_and_tool_agnostic(tmp_path) -> None:
    output_dir = tmp_path / "editor"
    build_standalone_editor(output_dir)

    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    app_js = (output_dir / "app.js").read_text(encoding="utf-8")

    assert index_html.count('id="copyAiGuideButton"') == 1
    assert "KI-Anleitung kopieren" in index_html
    assert app_js.count("const AI_HANDOFF_PROMPT = ") == 1
    assert json.dumps(AI_HANDOFF_PROMPT, ensure_ascii=False) in app_js
    assert "navigator.clipboard.writeText(AI_HANDOFF_PROMPT)" in app_js
    assert "KI-Anleitung kopiert" in app_js

    assert "Mermaid" in AI_HANDOFF_PROMPT
    assert "JSON Canvas 1.0" in AI_HANDOFF_PROMPT
    assert "`mermaid`-Codeblock" in AI_HANDOFF_PROMPT
    assert "`json`-Codeblock" in AI_HANDOFF_PROMPT
    assert "Kein Vorwort, keine Erklärung und keine zusätzliche Variante." in AI_HANDOFF_PROMPT

    # The copied contract describes only the output expected from the LLM.
    # It must not prescribe where the user pastes it or add unrelated truthfulness policy.
    assert "https://" not in AI_HANDOFF_PROMPT
    assert "commonthing.net" not in AI_HANDOFF_PROMPT
    assert "erfinde" not in AI_HANDOFF_PROMPT.casefold()
