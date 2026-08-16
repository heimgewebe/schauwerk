import json
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


def _fundus_asset_path(root: Path) -> Path:
    return root / "registry" / "fundus" / "assets" / "botanical.concave-frame.corner.v1.json"


def _fundus_brief_path(root: Path) -> Path:
    return (
        root
        / "registry"
        / "fundus"
        / "briefs"
        / "botanical.concave-frame.corner.v1.generate.json"
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_registry_validates_committed_fundus_image_briefs(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    validate_registry(root)


def test_registry_allows_prepared_unbound_fundus_image_brief(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    brief = _read_json(_fundus_brief_path(root))
    brief["id"] = "botanical.future-corner.v1.generate"
    brief["asset_id"] = "botanical.future-corner.v1"
    path = root / "registry" / "fundus" / "briefs" / f"{brief['id']}.json"
    _write_json(path, brief)

    validate_registry(root)


def test_registry_rejects_missing_bound_fundus_image_brief(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    _fundus_brief_path(root).unlink()
    with pytest.raises(RegistryValidationError, match="missing committed image brief"):
        validate_registry(root)


def test_registry_rejects_malformed_fundus_image_brief_json(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    _fundus_brief_path(root).write_text(
        '{"schema_version":"schauwerk-fundus-image-brief.v1",'
        '"schema_version":"schauwerk-fundus-image-brief.v1"}\n',
        encoding="utf-8",
    )
    with pytest.raises(RegistryValidationError, match="invalid JSON manifest"):
        validate_registry(root)


def test_registry_rejects_changed_bound_fundus_brief_digest(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = _fundus_brief_path(root)
    brief = _read_json(path)
    brief["requirements"].append("Preserve the exact current source binding")
    _write_json(path, brief)
    with pytest.raises(RegistryValidationError, match="missing committed image brief"):
        validate_registry(root)


def test_registry_rejects_fundus_brief_operation_source_mode_mismatch(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = _fundus_asset_path(root)
    asset = _read_json(path)
    asset["sources"][0]["source_mode"] = "edited"
    _write_json(path, asset)
    with pytest.raises(RegistryValidationError, match="operation.*conflicts with source_mode"):
        validate_registry(root)


def test_registry_rejects_fundus_brief_source_role_mismatch(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = _fundus_asset_path(root)
    asset = _read_json(path)
    asset["sources"][0]["role"] = "reference"
    _write_json(path, asset)
    with pytest.raises(
        RegistryValidationError, match="source_role.*conflicts with bound source role"
    ):
        validate_registry(root)


def test_registry_rejects_fundus_brief_family_mismatch(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = _fundus_asset_path(root)
    asset = _read_json(path)
    asset["family"] = "hall-of-memory.stellar-frame"
    _write_json(path, asset)
    with pytest.raises(
        RegistryValidationError, match="image brief family.*conflicts with asset family"
    ):
        validate_registry(root)


def test_registry_rejects_fundus_brief_property_mismatch(tmp_path: Path) -> None:
    root = _registry_copy(tmp_path)
    path = _fundus_asset_path(root)
    asset = _read_json(path)
    asset["properties"]["mask_safe"] = False
    _write_json(path, asset)
    with pytest.raises(RegistryValidationError, match="property 'mask_safe'.*asset declares False"):
        validate_registry(root)


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
    region = next(
        item for item in value["regions"] if item["id"] == "schauwerk.delivery-status.readonly"
    )
    region["policy_id"] = "managed-safe-default"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(RegistryValidationError, match="requires read-only policy"):
        validate_registry(root)
