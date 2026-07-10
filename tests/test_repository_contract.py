from pathlib import Path

from schauwerk import __version__
from schauwerk.registry_runtime import registry_show, registry_status
from schauwerk.registry_validation import validate_registry


def test_version_is_initial_release() -> None:
    assert __version__ == "0.1.0"


def test_seeded_registry_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    assert validate_registry(root) == {
        "policies": 2,
        "projects": 3,
        "publications": 1,
        "regions": 4,
        "sources": 12,
        "surfaces": 5,
        "views": 4,
    }


def test_registry_status_is_deterministic_and_inspectable() -> None:
    root = Path(__file__).resolve().parents[1]
    first = registry_status(root)
    second = registry_status(root)
    assert first == second
    assert first["valid"] is True
    assert first["counts"]["sources"] == 12
    assert len(first["registry_digest"]) == 64
    view = registry_show("views", "grabowski.operator-overview", root)["item"]
    assert view["project_id"] == "grabowski"


def test_canonical_docs_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "README.md",
        "AGENTS.md",
        "repo.meta.yaml",
        "docs/index.md",
        "docs/architecture/schauwerk.md",
        "docs/roadmap.md",
    ):
        assert (root / relative).is_file(), relative
