from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from schauwerk.surfaces.miro.native_executor import validate_native_bundle
from schauwerk.visual.delivery import (
    RepresentationDeliveryError,
    check_representation_package,
)
from schauwerk.visual.delivery_runtime import deliver_representation_package
from schauwerk.visual.representation import compile_representation_package

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-representation-v1.json"
CHECK_SCHEMA_PATH = ROOT / "schemas/representation-delivery-check.v1.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schemas/representation-delivery-receipt.v1.schema.json"
PACKAGED_CHECK_SCHEMA_PATH = (
    ROOT / "src/schauwerk/schemas/representation-delivery-check.v1.schema.json"
)
PACKAGED_RECEIPT_SCHEMA_PATH = (
    ROOT / "src/schauwerk/schemas/representation-delivery-receipt.v1.schema.json"
)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _compile(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    compile_representation_package(input_path=FIXTURE, output_dir=package)
    return package


class ResumeClient:
    def __init__(self) -> None:
        self.resume_path: Path | None = None

    async def native_apply(
        self,
        *,
        alias: str,
        input_path: Path,
        output_path: Path,
        resume_path: Path | None = None,
    ) -> dict[str, Any]:
        assert alias == "operator-ecosystem"
        bundle = validate_native_bundle(json.loads(input_path.read_text(encoding="utf-8")))
        self.resume_path = resume_path
        receipt = {
            "success": True,
            "execution_state": "complete",
            "bundle_digest": bundle["bundle_digest"],
            "completed_operation_count": len(bundle["operations"]),
            "postflight": {"inventory": {"items": len(bundle["operations"])}},
            "execution_digest": "b" * 64,
            "mutation_attempted": True,
        }
        _write_private_json(output_path, receipt)
        return receipt


def test_public_and_packaged_delivery_schemas_are_identical() -> None:
    assert CHECK_SCHEMA_PATH.read_bytes() == PACKAGED_CHECK_SCHEMA_PATH.read_bytes()
    assert RECEIPT_SCHEMA_PATH.read_bytes() == PACKAGED_RECEIPT_SCHEMA_PATH.read_bytes()

    for path in (CHECK_SCHEMA_PATH, RECEIPT_SCHEMA_PATH):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_delivery_check_matches_its_public_schema(tmp_path: Path) -> None:
    check = check_representation_package(_compile(tmp_path))
    schema = json.loads(CHECK_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert list(Draft202012Validator(schema).iter_errors(check)) == []


def test_delivery_receipt_matches_its_public_schema(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    output = tmp_path / "delivery"
    client = ResumeClient()

    result = asyncio.run(
        deliver_representation_package(
            alias="operator-ecosystem",
            package_dir=package,
            output_dir=output,
            client=client,
        )
    )
    persisted = json.loads((output / "delivery-receipt.json").read_text(encoding="utf-8"))
    schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert result["delivery_digest"] == persisted["delivery_digest"]
    assert list(Draft202012Validator(schema).iter_errors(persisted)) == []


def test_package_check_rejects_group_readable_artifacts(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    (package / "diagram.mmd").chmod(0o640)

    with pytest.raises(RepresentationDeliveryError, match="ownership is unsafe"):
        check_representation_package(package)


def test_delivery_resume_uses_the_same_frozen_bundle_and_checkpoint(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    output = tmp_path / "delivery"
    output.mkdir(mode=0o700)
    frozen = output / "native-bundle.json"
    checkpoint = output / "native-execution.json"
    frozen.write_bytes((package / "miro-native-bundle.json").read_bytes())
    frozen.chmod(0o600)
    bundle = validate_native_bundle(json.loads(frozen.read_text(encoding="utf-8")))
    _write_private_json(
        checkpoint,
        {
            "success": False,
            "execution_state": "in_progress",
            "bundle_digest": bundle["bundle_digest"],
        },
    )
    client = ResumeClient()

    result = asyncio.run(
        deliver_representation_package(
            alias="operator-ecosystem",
            package_dir=package,
            output_dir=output,
            client=client,
            resume=True,
        )
    )

    assert result["success"] is True
    assert result["resumed"] is True
    assert client.resume_path == checkpoint
    assert (output / "native-bundle.json").read_bytes() == (
        package / "miro-native-bundle.json"
    ).read_bytes()
