from __future__ import annotations

from schauwerk.operator.regions import (
    compile_region_apply_scaffold,
    compile_region_operation_contract,
    parse_region_declaration,
)


def managed_region() -> dict:
    return {
        "region": {
            "view_id": "learning:photosynthese",
            "region_id": "cluster-goals",
            "mode": "managed",
            "surface_alias": "nicole-mt-zoom-chunked-20260701-211733",
            "expected_snapshot_digest": "a" * 64,
            "expected_source_digest": "b" * 64,
            "owner": "schauwerk",
            "visibility": "classroom",
        }
    }


def snapshot_receipt(alias: str, digest: str) -> dict:
    return {
        "board_alias": alias,
        "content_digest": digest,
        "item_count": 4,
        "repeatability_verified": True,
        "sanitized_references": True,
    }


def ready_apply_scaffold() -> dict:
    declaration = parse_region_declaration(managed_region())
    preflight = {
        "schema_version": "typed-region-preflight.v1",
        "ok": True,
        "ready_for_apply": True,
        "mutation_attempted": False,
        "operation": "render-update",
        "region": declaration.to_dict(),
        "snapshot": snapshot_receipt(declaration.surface_alias, "a" * 64),
        "blocked_reasons": [],
        "boundary": {"no_miro_mutation": True},
    }
    return compile_region_apply_scaffold(preflight=preflight)


def fixture_operations(region_id: str = "cluster-goals") -> list[dict[str, str]]:
    return [
        {
            "operation_id": "create-title",
            "action": "create-item",
            "region_id": region_id,
            "local_ref": "title-card",
            "payload_digest": "c" * 64,
        },
        {
            "operation_id": "update-body",
            "action": "update-item",
            "region_id": region_id,
            "local_ref": "body-card",
            "payload_digest": "d" * 64,
        },
    ]


def test_contract_ready() -> None:
    result = compile_region_operation_contract(
        scaffold=ready_apply_scaffold(), fixture_operations=fixture_operations()
    )
    assert result["schema_version"] == "typed-region-operation-contract.v1"
    assert result["ok"] is True
    assert result["mutation_attempted"] is False
