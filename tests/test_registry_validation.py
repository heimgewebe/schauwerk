import shutil
from pathlib import Path

import pytest
import yaml

from schauwerk.registry_validation import RegistryValidationError, validate_registry


def _registry_copy(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "repo"
    shutil.copytree(root / "schemas", target / "schemas")
    shutil.copytree(root / "registry", target / "registry")
    return target


def test_registry_rejects_unknown_project_source(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "projects.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["projects"][0]["source_ids"].append("missing.source")
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="unknown source_id"):
        validate_registry(root)


def test_registry_rejects_duplicate_surface_alias(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "surfaces.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["surfaces"][1]["alias"] = value["surfaces"][0]["alias"]
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="duplicate aliases"):
        validate_registry(root)


def test_registry_rejects_unsorted_collection(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "projects.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["projects"].reverse()
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="sorted by id"):
        validate_registry(root)


def test_registry_rejects_source_dependency_cycle(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "sources.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in value["sources"]}
    by_id["repo.grabowski"]["depends_on"] = ["github.grabowski"]
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="dependency cycle"):
        validate_registry(root)


def test_registry_rejects_absolute_artifact_path(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "publications.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["publications"][0]["artifact_path"] = "/tmp/private.json"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="repository-relative"):
        validate_registry(root)


def test_registry_rejects_read_only_region_with_mutating_policy(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = root / "registry" / "regions.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["regions"][1]["policy_id"] = "managed-safe-default"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="requires read-only policy"):
        validate_registry(root)
