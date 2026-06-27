from pathlib import Path

from schauwerk import __version__
from schauwerk.registry_validation import validate_registry


def test_version_is_initial_release() -> None:
    assert __version__ == "0.1.0"


def test_empty_initial_registry_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    assert validate_registry(root) == {
        "projects": 0,
        "publications": 0,
        "surfaces": 0,
        "views": 0,
    }


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
