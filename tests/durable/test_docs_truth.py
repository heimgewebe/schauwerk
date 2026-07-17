from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_active_docs_match_post_sw017_local_state() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/architecture/schauwerk.md").read_text(encoding="utf-8")

    assert "**Useful-pilot foundation.**" not in readme
    assert "Productive typed live apply, Regie" not in agents
    assert "integrated/durable v1 contracts through SW-017" in agents
    assert "Visual System v2 in SW-018" in agents
    assert "former `Dev team`" in roadmap
    assert "Miro `Education team`" in roadmap
    assert "Space `Schauwerk`" in roadmap
    assert "RepoGround, Cabinet, Vault" not in architecture
    assert "RepoGround, Systemkatalog, Vault" in architecture


def test_new_contract_docs_and_schemas_are_routed() -> None:
    index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    for relative in (
        "integration/source-adapters-v1.md",
        "operations/automated-maintenance-v1.md",
        "search/search-semantics-v1.md",
        "operations/durable-operations-v1.md",
        "operations/incidents/durable-runbooks-v1.md",
        "visual/schauwerk-visual-system-v2.md",
        "operators/visual-system-v2-live.md",
    ):
        assert relative in index
        assert (ROOT / "docs" / relative).is_file()
    for name in (
        "source-observation.v1.schema.json",
        "source-observation-set.v1.schema.json",
        "maintenance-proposal.v1.schema.json",
        "search-index.v1.schema.json",
        "operations-health.v1.schema.json",
        "backup-manifest.v1.schema.json",
        "visual-system.v2.schema.json",
        "visual-board.v2.schema.json",
        "visual-quality.v2.schema.json",
        "visual-review.v2.schema.json",
    ):
        assert name in index
        assert (ROOT / "schemas" / name).is_file()
