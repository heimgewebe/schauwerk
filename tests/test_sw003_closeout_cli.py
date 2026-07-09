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


def _complete_live_gate_claim() -> dict:
    return {
        "claim_closes_live_sw003_gate": True,
        "live_create_attempted": True,
        "live_create_verified": True,
        "live_create_evidence_digest": "6" * 64,
        "live_read_after_create_verified": True,
        "live_read_after_create_evidence_digest": "7" * 64,
        "live_update_verified": True,
        "live_update_evidence_digest": "8" * 64,
        "marker_scope_uniqueness_verified": True,
        "marker_scope_evidence_digest": "9" * 64,
        "idempotency_verified": True,
        "idempotency_evidence_digest": "a" * 64,
        "cleanup_attempted": True,
        "cleanup_verified": True,
        "cleanup_evidence_digest": "b" * 64,
        "provider_identifiers_sanitized": True,
        "board_scope": {
            "surface_alias": "sw003-live-proof",
            "allowlisted": True,
        },
        "board_scope_evidence_digest": "c" * 64,
    }


def test_sw003_live_gate_cli_writes_local_evaluation_without_miro_access(
    tmp_path, capsys
) -> None:
    evidence_path = tmp_path / "live-gate-evidence.json"
    output_path = tmp_path / "live-gate-evaluation.json"
    _write_json(evidence_path, _complete_live_gate_claim())

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_receipt == written
    assert stdout_receipt["schema_version"] == "typed-region-sw003-live-gate-evaluation.v1"
    assert stdout_receipt["claim_valid"] is True
    assert written["candidate_closes_live_sw003_gate"] is True
    assert written["evidence_input_digest"] == _stable_digest(_complete_live_gate_claim())
    assert len(written["requirements_digest"]) == 64
    assert len(written["evaluation_digest"]) == 64
    digest_input = {
        key: value
        for key, value in written.items()
        if key not in {"evaluation_digest", "output_path"}
    }
    assert written["evaluation_digest"] == _stable_digest(digest_input)
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["mutation_attempted"] is False
    assert written["live_miro_access_attempted"] is False
    assert written["boundary"] == {
        "local_evaluation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "does_not_close_issue_8": True,
    }


def test_sw003_live_gate_cli_does_not_echo_provider_identifiers(tmp_path, capsys) -> None:
    evidence = _complete_live_gate_claim()
    evidence["cleanup_verified"] = False
    evidence["cleanup_boundary_accepted"] = True
    evidence["cleanup_boundary_reason"] = "https://miro.com/app/board/private-id"
    evidence_path = tmp_path / "live-gate-evidence.json"
    output_path = tmp_path / "live-gate-evaluation.json"
    _write_json(evidence_path, evidence)

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    stdout = capsys.readouterr().out
    written = output_path.read_text(encoding="utf-8")
    assert "provider_identifier_present_in_live_gate_claim" in stdout
    assert "cleanup_boundary_reason_unsafe" in stdout
    assert "miro.com" not in stdout
    assert "private-id" not in stdout
    assert "miro.com" not in written
    assert "private-id" not in written
    result = json.loads(written)
    assert result["schema_version"] == "typed-region-sw003-live-gate-evaluation.v1"
    assert result["evidence_input_digest"] == _stable_digest(evidence)
    assert len(result["evaluation_digest"]) == 64


def test_sw003_live_gate_requirements_cli_writes_local_checklist(tmp_path, capsys) -> None:
    output_path = tmp_path / "live-gate-requirements.json"

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-requirements",
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    required_keys = {item["key"] for item in written["requirements"]}
    assert stdout_receipt["schema_version"] == (
        "typed-region-sw003-live-gate-requirements.v1"
    )
    assert "live_create_attempted" in required_keys
    assert "cleanup_verified_or_boundary_accepted" in required_keys
    assert stdout_receipt == written
    assert isinstance(written["requirements_digest"], str)
    assert len(written["requirements_digest"]) == 64
    assert written["mutation_attempted"] is False
    assert written["live_miro_access_attempted"] is False
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["boundary"] == {
        "local_evaluation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "does_not_close_issue_8": True,
    }


def test_sw003_live_gate_template_cli_writes_non_claim_template(tmp_path, capsys) -> None:
    output_path = tmp_path / "live-gate-template.json"

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-template",
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_receipt == written
    assert written["schema_version"] == "typed-region-sw003-live-gate-template.v1"
    assert written["template_only"] is True
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["evidence_template"]["claim_closes_live_sw003_gate"] is False
    assert written["evidence_template"]["board_scope"] == {
        "surface_alias": "",
        "allowlisted": False,
    }
    assert len(written["evidence_template_digest"]) == 64
    assert "miro.com" not in output_path.read_text(encoding="utf-8")


def test_sw003_live_gate_template_evidence_fails_closed_when_evaluated(tmp_path, capsys) -> None:
    template_path = tmp_path / "live-gate-template.json"
    evidence_path = tmp_path / "template-evidence.json"
    evaluation_path = tmp_path / "template-evaluation.json"

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-template",
            "--output",
            str(template_path),
            "--json",
        ]
    ) == 0
    template_receipt = json.loads(template_path.read_text(encoding="utf-8"))
    _write_json(evidence_path, template_receipt["evidence_template"])
    capsys.readouterr()

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(evaluation_path),
            "--json",
        ]
    )

    assert code == 0
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    assert evaluation["schema_version"] == "typed-region-sw003-live-gate-evaluation.v1"
    assert evaluation["claim_valid"] is False
    assert evaluation["candidate_closes_live_sw003_gate"] is False
    assert evaluation["closes_live_sw003_gate"] is False
    assert "live_gate_claim_not_requested" in evaluation["blocked_reasons"]
    assert "evidence_live_create_attempted_missing_or_false" in evaluation[
        "blocked_reasons"
    ]


def test_sw003_live_gate_status_cli_writes_local_status_receipt(tmp_path, capsys) -> None:
    evidence_path = tmp_path / "live-gate-evidence.json"
    evaluation_path = tmp_path / "live-gate-evaluation.json"
    status_path = tmp_path / "live-gate-status.json"
    evidence = _complete_live_gate_claim()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(evaluation_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-status",
            str(evaluation_path),
            "--output",
            str(status_path),
            "--json",
        ]
    ) == 0

    stdout_receipt = json.loads(capsys.readouterr().out)
    written = json.loads(status_path.read_text(encoding="utf-8"))
    assert stdout_receipt == written
    assert written["schema_version"] == "typed-region-sw003-live-gate-status.v1"
    assert written["ok"] is True
    assert written["ready_for_live_acceptance_review"] is True
    assert written["ready_for_live_apply"] is False
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["mutation_attempted"] is False
    assert written["live_miro_access_attempted"] is False
    assert written["live_apply_gate"] == {
        "ready_for_live_apply": False,
        "blocked_reasons": ["sw003_live_gate_status_only"],
    }
    assert "miro.com" not in status_path.read_text(encoding="utf-8")


def test_sw003_live_gate_status_cli_rejects_invalid_evaluation_schema(tmp_path, capsys) -> None:
    evaluation_path = tmp_path / "wrong-live-gate-evaluation.json"
    evaluation_path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-status",
            str(evaluation_path),
            "--json",
        ]
    )

    assert code == 2
    assert "unsupported schema" in capsys.readouterr().err


def test_sw003_live_gate_review_packet_cli_writes_local_packet(tmp_path, capsys) -> None:
    evidence_path = tmp_path / "live-gate-evidence.json"
    evaluation_path = tmp_path / "live-gate-evaluation.json"
    status_path = tmp_path / "live-gate-status.json"
    packet_path = tmp_path / "live-gate-review-packet.json"
    evidence = _complete_live_gate_claim()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(evaluation_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-status",
            str(evaluation_path),
            "--output",
            str(status_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-review-packet",
            str(status_path),
            "--output",
            str(packet_path),
            "--json",
        ]
    ) == 0

    stdout_packet = json.loads(capsys.readouterr().out)
    written = json.loads(packet_path.read_text(encoding="utf-8"))
    assert stdout_packet == written
    assert written["schema_version"] == "typed-region-sw003-live-gate-review-packet.v1"
    assert written["ok"] is True
    assert written["ready_for_live_acceptance_review"] is True
    assert written["ready_for_live_apply"] is False
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["mutation_attempted"] is False
    assert written["live_miro_access_attempted"] is False
    assert written["live_apply_gate"] == {
        "ready_for_live_apply": False,
        "blocked_reasons": ["sw003_live_gate_review_packet_only"],
    }
    assert "miro.com" not in packet_path.read_text(encoding="utf-8")


def test_sw003_live_gate_review_packet_cli_rejects_invalid_status_schema(tmp_path, capsys) -> None:
    status_path = tmp_path / "wrong-live-gate-status.json"
    status_path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-review-packet",
            str(status_path),
            "--json",
        ]
    )

    assert code == 2
    assert "unsupported schema" in capsys.readouterr().err


def test_sw003_live_gate_evidence_packet_cli_writes_local_packet(tmp_path, capsys) -> None:
    evidence_path = tmp_path / "live-gate-evidence.json"
    evaluation_path = tmp_path / "live-gate-evaluation.json"
    status_path = tmp_path / "live-gate-status.json"
    review_packet_path = tmp_path / "live-gate-review-packet.json"
    evidence_packet_path = tmp_path / "live-gate-evidence-packet.json"
    evidence = _complete_live_gate_claim()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate",
            str(evidence_path),
            "--output",
            str(evaluation_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-status",
            str(evaluation_path),
            "--output",
            str(status_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-review-packet",
            str(status_path),
            "--output",
            str(review_packet_path),
            "--json",
        ]
    ) == 0
    capsys.readouterr()

    assert runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-evidence-packet",
            str(review_packet_path),
            "--output",
            str(evidence_packet_path),
            "--json",
        ]
    ) == 0

    stdout_packet = json.loads(capsys.readouterr().out)
    written = json.loads(evidence_packet_path.read_text(encoding="utf-8"))
    assert stdout_packet == written
    assert written["schema_version"] == "typed-region-sw003-live-gate-evidence-packet.v1"
    assert written["ok"] is True
    assert written["ready_for_live_acceptance_review"] is True
    assert written["ready_for_live_apply"] is False
    assert written["closes_live_sw003_gate"] is False
    assert written["creates_live_acceptance"] is False
    assert written["mutation_attempted"] is False
    assert written["live_miro_access_attempted"] is False
    assert written["live_apply_gate"] == {
        "ready_for_live_apply": False,
        "blocked_reasons": ["sw003_live_gate_evidence_packet_only"],
    }
    assert "miro.com" not in evidence_packet_path.read_text(encoding="utf-8")


def test_sw003_live_gate_evidence_packet_cli_rejects_invalid_review_schema(
    tmp_path, capsys
) -> None:
    packet_path = tmp_path / "wrong-review-packet.json"
    packet_path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")

    code = runner.main(
        [
            "miro",
            "region",
            "sw003-live-gate-evidence-packet",
            str(packet_path),
            "--json",
        ]
    )

    assert code == 2
    assert "unsupported schema" in capsys.readouterr().err


def _ready_sw009_scaffold() -> dict:
    return {
        "schema_version": "typed-region-apply-scaffold.v1",
        "ok": True,
        "mutation_attempted": False,
        "ready_for_fixture_apply": True,
        "ready_for_live_apply": False,
        "blocked_reasons": [],
        "operation": "replace-region",
        "region": {
            "view_id": "learning:photosynthese",
            "region_id": "cluster-goals",
            "mode": "managed",
            "surface_alias": "nicole-mt-zoom-chunked-20260701-211733",
            "expected_snapshot_digest": "a" * 64,
            "expected_source_digest": "b" * 64,
            "owner": "schauwerk",
            "visibility": "classroom",
        },
        "snapshot": {
            "board_alias": "nicole-mt-zoom-chunked-20260701-211733",
            "content_digest": "a" * 64,
            "item_count": 4,
            "repeatability_verified": True,
            "sanitized_references": True,
        },
        "restore_strategy": "use_preflight_snapshot_path",
        "boundary": {
            "scaffold_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
        },
    }


def _ready_sw003_evidence_packet_for_sw009() -> dict:
    packet = {
        "schema_version": "typed-region-sw003-live-gate-evidence-packet.v1",
        "ok": True,
        "mutation_attempted": False,
        "live_miro_access_attempted": False,
        "closes_live_sw003_gate": False,
        "creates_live_acceptance": False,
        "ready_for_live_acceptance_review": True,
        "ready_for_live_apply": False,
        "source_receipts": {
            "evidence_input_digest": "c" * 64,
            "live_gate_evaluation_digest": "d" * 64,
            "live_gate_status_digest": "e" * 64,
            "live_gate_review_packet_digest": "f" * 64,
            "requirements_digest": "1" * 64,
        },
        "requirements": [],
        "requirements_digest": "1" * 64,
        "source_schema_versions": {
            "live_gate_evaluation": "typed-region-sw003-live-gate-evaluation.v1",
            "live_gate_status": "typed-region-sw003-live-gate-status.v1",
            "live_gate_review_packet": "typed-region-sw003-live-gate-review-packet.v1",
        },
        "summary": {
            "review_packet_ok": True,
            "review_packet_blocked_reasons": [],
            "status_blocked_reasons": [],
            "human_review_required": True,
        },
        "live_apply_gate": {
            "ready_for_live_apply": False,
            "blocked_reasons": ["sw003_live_gate_evidence_packet_only"],
        },
        "boundary": {
            "local_evidence_packet_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "does_not_close_issue_8": True,
        },
    }
    packet["evidence_packet_digest"] = _stable_digest(packet)
    return packet


def test_sw009_live_apply_gate_cli_writes_ready_gate(tmp_path, capsys) -> None:
    scaffold_path = tmp_path / "scaffold.json"
    sw003_packet_path = tmp_path / "sw003-evidence-packet.json"
    output_path = tmp_path / "sw009-live-gate.json"
    scaffold_path.write_text(json.dumps(_ready_sw009_scaffold()), encoding="utf-8")
    sw003_packet_path.write_text(
        json.dumps(_ready_sw003_evidence_packet_for_sw009()), encoding="utf-8"
    )

    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-gate",
            str(scaffold_path),
            "--sw003-evidence-packet",
            str(sw003_packet_path),
            "--ack-allowlisted-scope",
            "--ack-preflight-receipt-digest",
            "--ack-before-snapshot",
            "--ack-review-packet",
            "--ack-restore-strategy",
            "--ack-postflight-plan",
            "--ack-provider-redaction",
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == written
    assert result["schema_version"] == "typed-region-sw009-live-apply-gate-receipt.v1"
    assert result["ok"] is True
    assert result["ready_for_live_apply"] is True
    assert result["live_apply_attempted"] is False
    assert result["mutation_attempted"] is False
    assert result["boundary"]["does_not_execute_live_apply"] is True


def test_sw009_live_apply_gate_cli_blocks_without_acknowledgements(tmp_path, capsys) -> None:
    scaffold_path = tmp_path / "scaffold.json"
    sw003_packet_path = tmp_path / "sw003-evidence-packet.json"
    scaffold_path.write_text(json.dumps(_ready_sw009_scaffold()), encoding="utf-8")
    sw003_packet_path.write_text(
        json.dumps(_ready_sw003_evidence_packet_for_sw009()), encoding="utf-8"
    )

    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-gate",
            str(scaffold_path),
            "--sw003-evidence-packet",
            str(sw003_packet_path),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_live_apply"] is False
    assert "acknowledgement_missing:operator_confirms_provider_redaction" in result[
        "blocked_reasons"
    ]


def _ready_sw009_candidate_manifest(tmp_path) -> dict:
    scaffold_path = tmp_path / "apply-scaffold.json"
    sw003_packet_path = tmp_path / "sw003-evidence-packet.json"
    scaffold_path.write_text(json.dumps(_ready_sw009_scaffold()), encoding="utf-8")
    sw003_packet_path.write_text(
        json.dumps(_ready_sw003_evidence_packet_for_sw009()), encoding="utf-8"
    )
    candidate = {
        "schema_version": "typed-region-sw009-live-apply-candidate.v1",
        "candidate_id": "sw009-candidate-cli",
        "scaffold_path": "apply-scaffold.json",
        "sw003_evidence_packet_path": "sw003-evidence-packet.json",
        "acknowledgements": {
            "operator_confirms_allowlisted_scope": True,
            "operator_confirms_preflight_receipt_digest": True,
            "operator_confirms_before_snapshot": True,
            "operator_confirms_review_packet": True,
            "operator_confirms_restore_strategy": True,
            "operator_confirms_postflight_plan": True,
            "operator_confirms_provider_redaction": True,
        },
        "boundary": {
            "local_candidate_manifest_only": True,
            "does_not_execute_live_apply": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "requires_separate_human_operator_apply": True,
        },
    }
    candidate["candidate_digest"] = _stable_digest(candidate)
    return candidate


def test_sw009_live_apply_candidate_template_cli_writes_template(tmp_path, capsys) -> None:
    output_path = tmp_path / "candidate-template.json"
    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-candidate-template",
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == written
    assert result["schema_version"] == "typed-region-sw009-live-apply-candidate.v1"
    assert result["boundary"]["does_not_execute_live_apply"] is True
    assert set(result["acknowledgements"].values()) == {False}


def test_sw009_live_apply_candidate_check_cli_writes_ready_receipt(
    tmp_path, capsys
) -> None:
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "candidate-receipt.json"
    candidate_path.write_text(
        json.dumps(_ready_sw009_candidate_manifest(tmp_path)), encoding="utf-8"
    )

    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-candidate-check",
            str(candidate_path),
            "--output",
            str(output_path),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert result == written
    assert result["schema_version"] == (
        "typed-region-sw009-live-apply-candidate-receipt.v1"
    )
    assert result["ok"] is True
    assert result["ready_for_live_apply"] is True
    assert result["live_apply_attempted"] is False
    assert result["mutation_attempted"] is False
    assert result["gate_receipt"]["ready_for_live_apply"] is True
    assert result["boundary"]["does_not_execute_live_apply"] is True


def test_sw009_live_apply_candidate_check_cli_blocks_missing_ack(
    tmp_path, capsys
) -> None:
    candidate = _ready_sw009_candidate_manifest(tmp_path)
    candidate["acknowledgements"]["operator_confirms_postflight_plan"] = False
    candidate.pop("candidate_digest")
    candidate["candidate_digest"] = _stable_digest(candidate)
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    code = runner.main(
        [
            "miro",
            "region",
            "sw009-live-apply-candidate-check",
            str(candidate_path),
            "--json",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_live_apply"] is False
    assert "gate:acknowledgement_missing:operator_confirms_postflight_plan" in result[
        "blocked_reasons"
    ]
