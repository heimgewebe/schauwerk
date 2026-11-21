from __future__ import annotations

import json

from schauwerk.visual.representation import validate_representation_input
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

    assert "schauwerk-representation-input.v1" in AI_HANDOFF_PROMPT
    assert '"intent": "knowledge_map"' in AI_HANDOFF_PROMPT
    assert '"groups": []' in AI_HANDOFF_PROMPT
    assert "Gruppen sind optional" in AI_HANDOFF_PROMPT
    assert "Ein zentraler Leitbegriff darf ohne group stehen." in AI_HANDOFF_PROMPT
    assert '"group": "gruppe"' not in AI_HANDOFF_PROMPT
    assert "Knotenarten:" in AI_HANDOFF_PROMPT
    assert "Kantenarten:" in AI_HANDOFF_PROMPT
    assert '"requested_formats": []' in AI_HANDOFF_PROMPT
    assert "Auftrag:\n[Hier den Inhalt einfügen]" in AI_HANDOFF_PROMPT
    assert "kanonischen Schauwerk-Repräsentationsformat" not in AI_HANDOFF_PROMPT
    assert "JSON-Canvas" not in AI_HANDOFF_PROMPT
    assert len(AI_HANDOFF_PROMPT) < 1900

    example = AI_HANDOFF_PROMPT.split("```json\n", 1)[1].split("\n```", 1)[0]
    validated = validate_representation_input(json.loads(example))
    assert validated["intent"] == "knowledge_map"
    assert validated["nodes"][0]["id"] == "knoten"
    assert validated["groups"] == []
    assert validated["nodes"][0].get("group") is None

    # The copied contract describes only the output expected from the LLM.
    # It must not prescribe where the user pastes it or add unrelated truthfulness policy.
    assert "https://" not in AI_HANDOFF_PROMPT
    assert "commonthing.net" not in AI_HANDOFF_PROMPT
    assert "erfinde" not in AI_HANDOFF_PROMPT.casefold()
