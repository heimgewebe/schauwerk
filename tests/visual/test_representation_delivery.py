from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from schauwerk.runner import main
from schauwerk.surfaces.miro.native_executor import validate_native_bundle
from schauwerk.visual.delivery import (
    RepresentationDeliveryError,
    _bytes_digest,
    _digest,
    check_representation_package,
)
from schauwerk.visual.delivery_runtime import (
    _delivery_lock,
    deliver_representation_package,
)
from schauwerk.visual.representation import compile_representation_package

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs/operators/fixtures/operator-ecosystem-representation-v1.json"


def _write_private_json(path: Path, value: dict[str, Any]) -> bytes:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    return payload


class SuccessfulClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.returned_execution_digest = "a" * 64

    async def native_apply(
        self,
        *,
        alias: str,
        input_path: Path,
        output_path: Path,
        resume_path: Path | None = None,
    ) -> dict[str, Any]:
        bundle_payload = input_path.read_bytes()
        bundle = validate_native_bundle(json.loads(bundle_payload))
        receipt = {
            "success": True,
            "execution_state": "complete",
            "bundle_digest": bundle["bundle_digest"],
            "completed_operation_count": len(bundle["operations"]),
            "postflight": {"inventory": {"items": len(bundle["operations"])}},
            "execution_digest": "a" * 64,
            "mutation_attempted": True,
        }
        _write_private_json(output_path, receipt)
        self.calls.append(
            {
                "alias": alias,
                "input_path": input_path,
                "input_payload": bundle_payload,
                "output_path": output_path,
                "resume_path": resume_path,
            }
        )
        return {**receipt, "execution_digest": self.returned_execution_digest}


def _compile(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    compile_representation_package(input_path=FIXTURE, output_dir=package)
    return package


def test_package_check_recomputes_all_artifacts_and_native_tools(tmp_path: Path) -> None:
    package = _compile(tmp_path)

    result = check_representation_package(package)

    assert result["ok"] is True
    assert result["native_bundle_available"] is True
    assert result["native_operation_count"] == 4
    assert result["quality_score"] == 100
    assert {
        "code_widget_create",
        "doc_create",
        "layout_create",
        "table_create",
    } <= set(result["required_tools"])
    assert result["mutation_attempted"] is False


def test_package_check_rejects_an_unlisted_file(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    (package / "unexpected.txt").write_text("not part of the package", encoding="utf-8")

    with pytest.raises(RepresentationDeliveryError, match="file set is not exact"):
        check_representation_package(package)


def test_package_check_rejects_a_changed_artifact(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    (package / "diagram.mmd").write_text("flowchart LR\n", encoding="utf-8")

    with pytest.raises(RepresentationDeliveryError, match="does not match its manifest"):
        check_representation_package(package)


def test_package_check_rejects_semantic_tampering_after_resigning(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    bundle_path = package / "miro-native-bundle.json"
    bundle = json.loads(bundle_path.read_text())
    bundle["operations"][0]["dsl"] += "\n# semantically changed"
    bundle_payload = _write_private_json(bundle_path, bundle)

    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    artifact = next(item for item in manifest["artifacts"] if item["role"] == "miro_native_bundle")
    artifact["bytes"] = len(bundle_payload)
    artifact["sha256"] = _bytes_digest(bundle_payload)
    manifest.pop("package_digest")
    manifest["package_digest"] = _digest(manifest)
    manifest_payload = _write_private_json(manifest_path, manifest)

    receipt_path = package / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["package_digest"] = manifest["package_digest"]
    receipt["manifest_sha256"] = _bytes_digest(manifest_payload)
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = _digest(receipt)
    _write_private_json(receipt_path, receipt)

    with pytest.raises(RepresentationDeliveryError, match="native bundle is not reproducible"):
        check_representation_package(package)


def test_delivery_freezes_exact_bundle_and_writes_bound_receipt(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    output = tmp_path / "delivery"
    client = SuccessfulClient()

    result = asyncio.run(
        deliver_representation_package(
            alias="operator-ecosystem",
            package_dir=package,
            output_dir=output,
            client=client,
        )
    )

    assert result["success"] is True
    assert result["provider_readback_verified"] is True
    assert result["globally_atomic"] is False
    assert result["native_operation_count"] == result["completed_operation_count"] == 4
    assert result["truth_boundary"]["provider_payload_frozen_before_provider_contact"] is True
    assert {path.name for path in output.iterdir()} == {
        "native-bundle.json",
        "native-execution.json",
        "delivery-receipt.json",
    }
    assert client.calls[0]["input_path"] == output / "native-bundle.json"
    assert client.calls[0]["input_payload"] == (package / "miro-native-bundle.json").read_bytes()
    assert client.calls[0]["resume_path"] is None
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())


def test_delivery_rejects_output_inside_package_before_mutation(tmp_path: Path) -> None:
    package = _compile(tmp_path)
    client = SuccessfulClient()

    with pytest.raises(RepresentationDeliveryError, match="outside the representation package"):
        asyncio.run(
            deliver_representation_package(
                alias="operator-ecosystem",
                package_dir=package,
                output_dir=package / "delivery",
                client=client,
            )
        )

    assert client.calls == []
    assert not (package / "delivery").exists()


def test_delivery_rejects_a_returned_result_that_differs_from_the_persisted_receipt(
    tmp_path: Path,
) -> None:
    package = _compile(tmp_path)
    output = tmp_path / "delivery"
    client = SuccessfulClient()
    client.returned_execution_digest = "c" * 64

    with pytest.raises(
        RepresentationDeliveryError,
        match="does not match its persisted receipt",
    ):
        asyncio.run(
            deliver_representation_package(
                alias="operator-ecosystem",
                package_dir=package,
                output_dir=output,
                client=client,
            )
        )

    assert not (output / "delivery-receipt.json").exists()


def test_delivery_lock_is_nonblocking(tmp_path: Path) -> None:
    destination = tmp_path / "delivery"
    destination.mkdir(mode=0o700)

    with _delivery_lock(destination):
        with pytest.raises(RepresentationDeliveryError, match="another delivery"):
            with _delivery_lock(destination):
                raise AssertionError("unreachable")
        assert (destination / "delivery.lock").is_file()
        with pytest.raises(RepresentationDeliveryError, match="another delivery"):
            with _delivery_lock(destination):
                raise AssertionError("unreachable")
    assert not (destination / "delivery.lock").exists()


def test_receipt_publication_failure_requires_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _compile(tmp_path)
    output = tmp_path / "delivery"
    client = SuccessfulClient()

    def fail_write(_path: Path, _value: dict[str, Any]) -> None:
        raise OSError("simulated local publication failure")

    monkeypatch.setattr("schauwerk.visual.delivery_runtime._write_new_json", fail_write)
    with pytest.raises(RepresentationDeliveryError, match="reconcile from native-execution"):
        asyncio.run(
            deliver_representation_package(
                alias="operator-ecosystem",
                package_dir=package,
                output_dir=output,
                client=client,
            )
        )

    assert client.calls
    assert (output / "native-bundle.json").is_file()
    assert (output / "native-execution.json").is_file()
    assert not (output / "delivery-receipt.json").exists()


def test_cli_checks_the_package_without_provider_contact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _compile(tmp_path)

    assert main(["visual", "package-check", str(package), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "schauwerk-representation-delivery-check.v1"
    assert result["native_bundle_available"] is True
