"""Executable Schauwerk command dispatcher."""

from __future__ import annotations

import json
import sys
from typing import Any

from .cli_handlers import (
    handle_board_add,
    handle_board_list,
    handle_board_remove,
    handle_doctor,
    handle_ecosystem_render,
    handle_education_offline,
    handle_education_render,
    handle_grabowski_operational_pilot,
    handle_grabowski_pilot,
    handle_inspect,
    handle_learn_apply,
    handle_learn_live_prune,
    handle_learn_live_test,
    handle_learn_render,
    handle_login,
    handle_logout,
    handle_quality,
    handle_region_apply_receipt,
    handle_region_apply_scaffold,
    handle_region_apply_simulation,
    handle_region_operation_contract,
    handle_region_plan,
    handle_region_postflight,
    handle_region_preflight,
    handle_region_restore_receipt,
    handle_region_simulation_closeout,
    handle_region_simulation_postflight,
    handle_region_sw003_closeout,
    handle_region_sw003_live_gate,
    handle_region_sw003_live_gate_evidence_packet,
    handle_region_sw003_live_gate_requirements,
    handle_region_sw003_live_gate_review_packet,
    handle_region_sw003_live_gate_status,
    handle_region_sw003_live_gate_template,
    handle_region_sw009_live_apply_candidate_check,
    handle_region_sw009_live_apply_candidate_template,
    handle_region_sw009_live_apply_gate,
    handle_registry_show,
    handle_registry_status,
    handle_snapshot,
    handle_software_pilot,
    handle_status,
    handle_tools,
    handle_visual_grammar,
)
from .cli_parser import build_parser
from .surfaces.miro.errors import MiroError, find_nested_miro_error, redact_text


def emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.provider == "ecosystem" and args.command == "render":
            result = handle_ecosystem_render(
                manifest=args.manifest,
                output=args.output,
                source_root=args.source_root,
            )
        elif args.provider == "registry" and args.command == "status":
            result = handle_registry_status()
        elif args.provider == "registry" and args.command == "show":
            result = handle_registry_show(kind=args.kind, identifier=args.identifier)
        elif args.provider == "pilot" and args.command == "grabowski":
            result = handle_grabowski_pilot(
                operator_context=args.operator_context,
                snapshot_output=args.snapshot_output,
                dsl_output=args.dsl_output,
            )
        elif args.provider == "pilot" and args.command == "grabowski-operational":
            result = handle_grabowski_operational_pilot(
                static_snapshot=args.static_snapshot,
                observation=args.observation,
                snapshot_output=args.snapshot_output,
                dsl_output=args.dsl_output,
            )
        elif args.provider == "pilot" and args.command == "software":
            result = handle_software_pilot(
                input_path=args.input,
                snapshot_output=args.snapshot_output,
                dsl_output=args.dsl_output,
            )
        elif args.provider == "education" and args.command == "render":
            result = handle_education_render(
                input_path=args.input, variant=args.variant, output=args.output
            )
        elif args.provider == "education" and args.command == "offline":
            result = handle_education_offline(
                input_path=args.input, output_dir=args.output_dir, variant=args.variant
            )
        elif args.provider == "visual" and args.command == "grammar":
            result = handle_visual_grammar(output=args.output)
        elif args.command == "status":
            result = handle_status(live=args.live)
        elif args.command == "login":
            result = handle_login(
                open_browser=not args.no_browser,
                manual_callback=args.manual_callback,
            )
        elif args.command == "tools":
            result = handle_tools()
        elif args.command == "doctor":
            result = handle_doctor(live=not args.no_live)
        elif args.command == "inspect":
            result = handle_inspect(
                query=args.query,
                owned_by_me=args.owned_by_me,
                limit=args.limit,
                max_pages=args.max_pages,
            )
        elif args.command == "board" and args.board_command == "add":
            result = handle_board_add(
                alias=args.alias, miro_url=args.miro_url, replace=args.replace
            )
        elif args.command == "board" and args.board_command == "list":
            result = handle_board_list()
        elif args.command == "board" and args.board_command == "remove":
            result = handle_board_remove(alias=args.alias)
        elif args.command == "snapshot":
            result = handle_snapshot(
                alias=args.alias,
                output=args.output,
                item_limit=args.item_limit,
                comment_limit=args.comment_limit,
                max_pages=args.max_pages,
                include_comments=not args.no_comments,
            )
        elif args.command == "quality":
            result = handle_quality(
                alias=args.alias,
                snapshot=args.snapshot,
                output=args.output,
                expected_min_connectors=args.expected_min_connectors,
                expected_min_docs=args.expected_min_docs,
                expected_min_tables=args.expected_min_tables,
            )
        elif args.command == "learn" and args.learn_command == "render":
            result = handle_learn_render(
                input_path=args.input, output=args.output, template=args.template
            )
        elif args.command == "learn" and args.learn_command == "apply":
            result = handle_learn_apply(
                input_path=args.input, alias=args.alias, template=args.template
            )
        elif args.command == "learn" and args.learn_command == "live-test":
            result = handle_learn_live_test(
                input_path=args.input,
                alias=args.alias,
                board_name=args.board_name,
                output_dir=args.output_dir,
                replace_alias=args.replace_alias,
                item_limit=args.item_limit,
                comment_limit=args.comment_limit,
                max_pages=args.max_pages,
                include_comments=not args.no_comments,
                template=args.template,
            )
        elif args.command == "learn" and args.learn_command == "live-prune":
            result = handle_learn_live_prune(keep=args.keep, dry_run=args.dry_run)
        elif args.command == "region" and args.region_command == "plan":
            result = handle_region_plan(
                input_path=args.input, operation=args.operation, output=args.output
            )
        elif args.command == "region" and args.region_command == "preflight":
            result = handle_region_preflight(
                input_path=args.input,
                snapshot=args.snapshot,
                operation=args.operation,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "apply-scaffold":
            result = handle_region_apply_scaffold(preflight=args.preflight, output=args.output)
        elif args.command == "region" and args.region_command == "apply-receipt":
            result = handle_region_apply_receipt(
                scaffold=args.scaffold, fixture=args.fixture, output=args.output
            )
        elif args.command == "region" and args.region_command == "operation-contract":
            result = handle_region_operation_contract(
                scaffold=args.scaffold, fixture=args.fixture, output=args.output
            )
        elif args.command == "region" and args.region_command == "apply-simulation":
            result = handle_region_apply_simulation(
                operation_contract=args.operation_contract,
                after_snapshot=args.after_snapshot,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "simulation-postflight":
            result = handle_region_simulation_postflight(
                apply_simulation_receipt=args.apply_simulation_receipt,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "simulation-closeout":
            result = handle_region_simulation_closeout(
                restore_receipt=args.restore_receipt,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "sw009-live-apply-gate":
            result = handle_region_sw009_live_apply_gate(
                scaffold=args.scaffold,
                sw003_evidence_packet=args.sw003_evidence_packet,
                output=args.output,
                acknowledgements={
                    "operator_confirms_allowlisted_scope": args.ack_allowlisted_scope,
                    "operator_confirms_preflight_receipt_digest": args.ack_preflight_receipt_digest,
                    "operator_confirms_before_snapshot": args.ack_before_snapshot,
                    "operator_confirms_review_packet": args.ack_review_packet,
                    "operator_confirms_restore_strategy": args.ack_restore_strategy,
                    "operator_confirms_postflight_plan": args.ack_postflight_plan,
                    "operator_confirms_provider_redaction": args.ack_provider_redaction,
                },
            )
        elif (
            args.command == "region"
            and args.region_command == "sw009-live-apply-candidate-template"
        ):
            result = handle_region_sw009_live_apply_candidate_template(
                output=args.output
            )
        elif (
            args.command == "region"
            and args.region_command == "sw009-live-apply-candidate-check"
        ):
            result = handle_region_sw009_live_apply_candidate_check(
                candidate_path=args.candidate, output=args.output
            )
        elif args.command == "region" and args.region_command == "postflight":
            result = handle_region_postflight(
                apply_receipt=args.apply_receipt,
                after_snapshot=args.after_snapshot,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "restore-receipt":
            result = handle_region_restore_receipt(
                postflight=args.postflight,
                restored_snapshot=args.restored_snapshot,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "sw003-closeout":
            result = handle_region_sw003_closeout(
                restore_receipt=args.restore_receipt,
                evidence=args.evidence,
                marker=args.marker,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "sw003-live-gate":
            result = handle_region_sw003_live_gate(
                evidence=args.evidence,
                output=args.output,
            )
        elif args.command == "region" and args.region_command == "sw003-live-gate-status":
            result = handle_region_sw003_live_gate_status(
                evaluation_receipt=args.evaluation_receipt,
                output=args.output,
            )
        elif (
            args.command == "region"
            and args.region_command == "sw003-live-gate-review-packet"
        ):
            result = handle_region_sw003_live_gate_review_packet(
                status_receipt=args.status_receipt,
                output=args.output,
            )
        elif (
            args.command == "region"
            and args.region_command == "sw003-live-gate-evidence-packet"
        ):
            result = handle_region_sw003_live_gate_evidence_packet(
                review_packet=args.review_packet,
                output=args.output,
            )
        elif (
            args.command == "region"
            and args.region_command == "sw003-live-gate-requirements"
        ):
            result = handle_region_sw003_live_gate_requirements(output=args.output)
        elif (
            args.command == "region" and args.region_command == "sw003-live-gate-template"
        ):
            result = handle_region_sw003_live_gate_template(output=args.output)
        elif args.command == "logout":
            result = handle_logout()
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        emit(result, as_json=args.json)
        return 0
    except (MiroError, ValueError) as exc:
        print(f"error: {redact_text(exc)}", file=sys.stderr)
        return 2
    except Exception as exc:
        nested = find_nested_miro_error(exc)
        if nested is not None:
            print(f"error: {redact_text(nested)}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
