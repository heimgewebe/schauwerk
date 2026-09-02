import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

from schauwerk import __version__
from schauwerk.registry_runtime import registry_show, registry_status
from schauwerk.registry_validation import validate_registry


def test_version_is_initial_release() -> None:
    assert __version__ == "0.1.0"


def test_canonical_lint_surface_includes_python_scripts() -> None:
    root = Path(__file__).resolve().parents[1]
    lint_commands = [
        line.strip()
        for line in (root / "Makefile").read_text(encoding="utf-8").splitlines()
        if "$(PYTHON) -m ruff check " in line
    ]
    assert lint_commands == ["$(PYTHON) -m ruff check src scripts tests"]


def test_make_validation_uses_one_supported_python_toolchain(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")

    assert "PYTHON_CANDIDATES := python3 python python3.13 python3.12 python3.11" in makefile
    assert (
        "PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,$(SYSTEM_PYTHON))"
        in makefile
    )
    assert "RUFF ?=" not in makefile
    assert "PYTEST ?=" not in makefile
    assert "$(PYTHON) -m ruff check src scripts tests" in makefile
    assert "$(PYTHON) -m pytest" in makefile
    for target in ("lint", "compile-check", "registry-validate", "test"):
        assert f"{target}: python-version-check" in makefile

    make = shutil.which("make")
    assert make is not None
    supported = subprocess.run(
        [make, "--no-print-directory", "python-version-check", f"PYTHON={sys.executable}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert supported.returncode == 0, supported.stdout + supported.stderr

    unsupported_python = tmp_path / "python"
    unsupported_python.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then echo 'Python 3.10.0'; exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    unsupported_python.chmod(0o755)
    unsupported = subprocess.run(
        [
            make,
            "-f",
            str(root / "Makefile"),
            "--no-print-directory",
            "python-version-check",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path)},
    )
    assert unsupported.returncode != 0
    assert "requires Python >=3.11,<3.14" in unsupported.stdout
    assert "No supported interpreter was found on PATH" in unsupported.stdout


def test_make_prefers_active_supported_python_over_side_install(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    make = shutil.which("make")
    assert make is not None

    active_marker = tmp_path / "active-python-used"
    side_marker = tmp_path / "side-python-used"
    active_python = tmp_path / "python3"
    side_python = tmp_path / "python3.12"
    active_python.write_text(
        "#!/bin/sh\n"
        f"printf 'used\\n' >> '{active_marker}'\n"
        "if [ \"$1\" = \"--version\" ]; then echo 'Python 3.11.16'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    side_python.write_text(
        "#!/bin/sh\n"
        f"printf 'used\\n' >> '{side_marker}'\n"
        "if [ \"$1\" = \"--version\" ]; then echo 'Python 3.12.11'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    active_python.chmod(0o755)
    side_python.chmod(0o755)

    result = subprocess.run(
        [
            make,
            "-f",
            str(root / "Makefile"),
            "--no-print-directory",
            "python-version-check",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert active_marker.is_file()
    assert not side_marker.exists()


def test_make_skips_unusable_version_manager_shim(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    make = shutil.which("make")
    assert make is not None

    broken_marker = tmp_path / "broken-python-probed"
    fallback_marker = tmp_path / "fallback-python-used"
    broken_python = tmp_path / "python3.13"
    fallback_python = tmp_path / "python3.12"
    broken_python.write_text(
        "#!/bin/sh\n"
        f"printf 'probed\\n' >> '{broken_marker}'\n"
        "exit 127\n",
        encoding="utf-8",
    )
    fallback_python.write_text(
        "#!/bin/sh\n"
        f"printf 'used\\n' >> '{fallback_marker}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    broken_python.chmod(0o755)
    fallback_python.chmod(0o755)

    result = subprocess.run(
        [
            make,
            "-f",
            str(root / "Makefile"),
            "--no-print-directory",
            "python-version-check",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert broken_marker.is_file()
    assert fallback_marker.is_file()


def test_make_preserves_path_entries_with_spaces(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    make = shutil.which("make")
    assert make is not None

    bin_dir = tmp_path / "Python Runtime"
    bin_dir.mkdir()
    marker_file = tmp_path / "spaced-path-python-used"
    python = bin_dir / "python3.12"
    python.write_text(
        "#!/bin/sh\n"
        f"printf 'used\\n' >> '{marker_file}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    python.chmod(0o755)

    result = subprocess.run(
        [
            make,
            "-f",
            str(root / "Makefile"),
            "--no-print-directory",
            "python-version-check",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker_file.is_file()


def test_declared_python_support_matches_ci_matrix() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    workflow = yaml.safe_load(
        (root / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    )

    assert project["requires-python"] == ">=3.11,<3.14"
    assert workflow["jobs"]["validate"]["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
        "3.13",
    ]


def test_seeded_registry_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    assert validate_registry(root) == {
        "policies": 2,
        "projects": 3,
        "publications": 1,
        "regions": 4,
        "sources": 14,
        "surfaces": 5,
        "views": 4,
    }


def test_registry_status_is_deterministic_and_inspectable() -> None:
    root = Path(__file__).resolve().parents[1]
    first = registry_status(root)
    second = registry_status(root)
    assert first == second
    assert first["valid"] is True
    assert first["counts"]["sources"] == 14
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
        "docs/visual/schauwerk-visual-system-v2.md",
        "docs/operators/visual-system-v2-live.md",
        "schemas/visual-system.v2.schema.json",
        "schemas/visual-board.v2.schema.json",
        "schemas/visual-quality.v2.schema.json",
        "schemas/visual-review.v2.schema.json",
        "schemas/representation-input.v1.schema.json",
    ):
        assert (root / relative).is_file(), relative
