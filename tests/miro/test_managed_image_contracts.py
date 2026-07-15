from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from schauwerk.surfaces.miro.managed_image_runtime import (
    ManagedImageDeleteReceipt,
    ManagedImageIdentity,
    ManagedImageReplaceReceipt,
    source_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = (
    "miro-managed-image.v1.schema.json",
    "miro-managed-image-replace-receipt.v1.schema.json",
    "miro-managed-image-delete-receipt.v1.schema.json",
)


def schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def delete_evidence(item_id: str) -> dict:
    return {
        "success": True,
        "provider": "rest",
        "item_id": item_id,
        "preflight_present": True,
        "delete_status": 204,
        "postflight_absent": True,
        "reconciled_after_uncertain_delete": False,
        "sanitized_references": True,
    }


def test_public_and_packaged_managed_image_schemas_are_identical_and_valid() -> None:
    for name in SCHEMAS:
        public = ROOT / "schemas" / name
        packaged = ROOT / "src" / "schauwerk" / "schemas" / name
        assert public.read_bytes() == packaged.read_bytes()
        Draft202012Validator.check_schema(schema(name))


def test_identity_and_success_receipts_validate() -> None:
    identity = ManagedImageIdentity(
        board_alias="operator-map",
        asset_key="operator-core",
        item_id="200",
        parent_id="10",
        source_sha256=source_sha256(b"new"),
        x=1200,
        y=920,
        width=2200,
    )
    Draft202012Validator(schema(SCHEMAS[0])).validate(identity.to_document())

    replaced = ManagedImageReplaceReceipt(
        success=True,
        board_alias="operator-map",
        asset_key="operator-core",
        old_item_id="100",
        new_item_id="200",
        source_sha256=source_sha256(b"new"),
        before_count=1,
        after_count=1,
        old_item_absent=True,
        new_item_present=True,
        geometry_matches=True,
        inventory_pages=3,
        delete_receipt=delete_evidence("100"),
    )
    Draft202012Validator(schema(SCHEMAS[1])).validate(replaced.to_dict())

    deleted = ManagedImageDeleteReceipt(
        success=True,
        board_alias="operator-map",
        asset_key="operator-core",
        old_item_id="200",
        before_count=1,
        after_count=0,
        old_item_absent=True,
        inventory_pages=2,
        delete_receipt=delete_evidence("200"),
    )
    Draft202012Validator(schema(SCHEMAS[2])).validate(deleted.to_dict())


def test_failure_receipts_validate_without_claiming_atomicity() -> None:
    replace_failure = {
        "schema_version": "schauwerk-miro-managed-image-replace.v1",
        "success": False,
        "status": "manual_reconciliation_required",
        "board_alias": "operator-map",
        "asset_key": "operator-core",
        "old_item_id": "100",
        "source_sha256": source_sha256(b"new"),
        "provider_semantics": "create-verify-delete-saga",
        "globally_atomic": False,
        "manual_reconciliation_required": True,
        "error_type": "ManagedImageReconciliationRequired",
        "error": "manual reconciliation required",
        "sanitized_references": True,
    }
    Draft202012Validator(schema(SCHEMAS[1])).validate(replace_failure)

    delete_failure = {
        "schema_version": "schauwerk-miro-managed-image-delete.v1",
        "success": False,
        "status": "failed",
        "board_alias": "operator-map",
        "asset_key": "operator-core",
        "old_item_id": "100",
        "source_sha256": None,
        "provider_semantics": "single-rest-delete-with-readback",
        "globally_atomic": False,
        "manual_reconciliation_required": False,
        "error_type": "MiroCredentialError",
        "error": "separate REST credential is unavailable",
        "sanitized_references": True,
    }
    Draft202012Validator(schema(SCHEMAS[2])).validate(delete_failure)
