from __future__ import annotations

import json
from pathlib import Path

from schauwerk import runner
from schauwerk.operator.receipts import _stable_digest, _without_runtime_fields

MARKER = "schauwerk-sw003-20260629T050000Z-abc123"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _restore_receipt() -> dict:
    region = {
        "view_id": "learning:photosynthese",
        "region_id": "cluster-goals",
        "mode": "managed",
        "surface_alias": "nicole-mt-zoom-chunked-20260701-211733",
        "expected_snapshot_digest": "a" * 64,
        "expected_source_digest": "b" * 64,
        "owner": "schauwerk",
        "visibility": "classroom",
    }
    return {
        "schema_version": "typed-region-restore-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "live_restore_attempted": False,
        "ready_for_closeout": True,
        "blocked_reasons": [],
        "operation": "render-update",
        "region": region,
        "pre_apply_snapshot": {
            "board_alias": region["surface_alias"],
            "content_digest": "a" * 64,
            "item_count": 4,
            "repeatability_verified": True,
            "sanitized_references": True,
        },
        "restored_snapshot": {
            "board_alias": region["surface_alias"],
            "content_digest": "a" * 64,
            "item_count": 4,
            "repeatability_verified": True,
            "sanitized_references": True,
        },
        "source_receipts": {
            "postflight_receipt_digest": "6" * 64,
            "restored_snapshot_digest": "7" * 64,
        },
        "boundary": {
            "fixture_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
    }


def _closeout_evidence(restore_receipt: dict) -> dict:
    restore_digest = _stable_digest(_without_runtime_fields(restore_receipt))
    return {
        "restore_receipt_digest": restore_digest,
        "marker": MARKER,
        "region": {
            "region_id": restore_receipt["region"]["region_id"],
            "surface_alias": restore_receipt["region"]["surface_alias"],
        },
        "verification": {
            "create_verified": True,
            "create_evidence_digest": "1" * 64,
            "read_verified": True,
            "read_evidence_digest": "2" * 64,
            "update_verified": True,
            "update_evidence_digest": "3" * 64,
            "marker_scope_verified": True,
            "marker_scope_evidence_digest": "4" * 64,
            "idempotency_verified": True,
            "idempotency_key": "fixture-idempotency-key",
            "idempotency_evidence_digest": "5" * 64,
        },
        "cleanup": {
            "mode": "explicit-boundary",
            "remote_cleanup_supported": False,
            "remote_cleanup_attempted": False,
            "boundary_reason": "miro_remote_cleanup_unavailable",
            "restore_receipt_digest": restore_digest,
        },
    }


def test_sw003_closeout_cli_writes_bound_fixture_receipt(tmp_path, capsys) -> None:
    restore = _restore_receipt()
    restore_path = tmp_path / "restore.json"
    evidence_path = tmp_path / "closeout-evidence.json"
    output_path = tmp_path / "sw003-closeout.json"
    _write_json(restore_path, restore)
    _write_json(evidence_path, _closeout_evidence(restore))

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-closeout",
            str(restore_path),
            "--evidence",
            str(evidence_path),
            "--marker",
            MARKER,
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_receipt["schema_version"] == "typed-region-sw003-closeout-receipt.v1"
    assert written["schema_version"] == "typed-region-sw003-closeout-receipt.v1"
    assert written["ok"] is True
    assert written["closes_live_sw003_gate"] is False
    assert written["cleanup_boundary_accepted"] is True
