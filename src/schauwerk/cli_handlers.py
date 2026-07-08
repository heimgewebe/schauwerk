"""Command handlers for the Schauwerk CLI."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ecosystem_map import render_ecosystem_map_html
from .education.view import (
    learning_render_receipt,
    load_learning_view,
    render_learning_dsl,
)
from .education.zoomlandkarte import render_learning_zoomlandkarte_dsl
from .operator.receipts import _stable_digest
from .operator.regions import (
    compile_region_apply_receipt,
    compile_region_apply_scaffold,
    compile_region_apply_simulation_receipt,
    compile_region_operation_contract,
    compile_region_operation_plan,
    compile_region_postflight_receipt,
    compile_region_preflight,
    compile_region_restore_receipt,
    compile_region_simulation_closeout_receipt,
    compile_region_simulation_postflight_receipt,
    compile_sw003_closeout_receipt,
    evaluate_sw003_live_gate_claim,
    load_fixture_operations,
    load_region_apply_receipt,
    load_region_apply_scaffold,
    load_region_apply_simulation_receipt,
    load_region_declaration,
    load_region_operation_contract,
    load_region_postflight_receipt,
    load_region_preflight,
    load_region_restore_receipt,
    load_snapshot_mapping_receipt,
    load_sw003_closeout_evidence,
    required_sw003_live_gate_evidence,
)
from .surfaces.miro.board_registry import BoardAllowlist
from .surfaces.miro.client import MiroMCPClient
from .surfaces.miro.live_test_index import create_live_test_record, prune_live_tests
from .surfaces.miro.quality import write_quality_receipt_from_snapshot_file
from .visual.grammar import zoomlandkarte_template


def handle_ecosystem_render(
    *, manifest: str, output: str, source_root: str | None
) -> dict[str, Any]:
    return render_ecosystem_map_html(
        manifest_path=Path(manifest),
        output_path=Path(output),
        source_root=source_root,
    )


def handle_status(*, live: bool = False, client: MiroMCPClient | None = None) -> dict[str, Any]:
    active = client or MiroMCPClient()
    result = active.status()
    result["live"] = asyncio.run(active.live_status()) if live else {"checked": False}
    return result


def handle_login(
    *, open_browser: bool, manual_callback: bool, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    return asyncio.run(
        active.login(open_browser=open_browser, manual_callback=manual_callback)
    ).to_dict()


def handle_tools(client: MiroMCPClient | None = None) -> dict[str, Any]:
    return asyncio.run((client or MiroMCPClient()).tools()).to_dict()


def handle_doctor(*, live: bool = True, client: MiroMCPClient | None = None) -> dict[str, Any]:
    return asyncio.run((client or MiroMCPClient()).doctor(check_live=live))


def handle_inspect(
    *,
    query: str,
    owned_by_me: bool,
    limit: int,
    max_pages: int,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    report = asyncio.run(
        (client or MiroMCPClient()).inspect(
            query=query, owned_by_me=owned_by_me, limit=limit, max_pages=max_pages
        )
    )
    return report.to_dict()


def handle_board_add(
    *, alias: str, miro_url: str, replace: bool = False, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    return (client or MiroMCPClient()).board_add(alias, miro_url, replace=replace).to_dict()


def handle_board_list(client: MiroMCPClient | None = None) -> dict[str, Any]:
    boards = (client or MiroMCPClient()).board_list()
    return {"count": len(boards), "boards": [board.to_dict() for board in boards]}


def handle_board_remove(*, alias: str, client: MiroMCPClient | None = None) -> dict[str, Any]:
    return {"alias": alias, "removed": (client or MiroMCPClient()).board_remove(alias)}


def handle_snapshot(
    *,
    alias: str,
    output: str | None,
    item_limit: int,
    comment_limit: int,
    max_pages: int,
    include_comments: bool,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    receipt = asyncio.run(
        (client or MiroMCPClient()).snapshot(
            alias=alias,
            output_path=Path(output) if output else None,
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )
    )
    return receipt.to_dict()


def handle_quality(
    *,
    alias: str,
    snapshot: str,
    output: str | None,
    expected_min_connectors: int,
    expected_min_docs: int,
    expected_min_tables: int,
) -> dict[str, Any]:
    snapshot_path = Path(snapshot)
    destination = Path(output) if output else snapshot_path.with_name("quality.json")
    receipt = write_quality_receipt_from_snapshot_file(
        snapshot_path=snapshot_path,
        destination=destination,
        board_alias=alias,
        expected_min_connectors=expected_min_connectors,
        expected_min_docs=expected_min_docs,
        expected_min_tables=expected_min_tables,
    )
    return receipt.to_dict()


def handle_learn_render(
    *, input_path: str, output: str | None, template: str = "classic"
) -> dict[str, Any]:
    source = Path(input_path)
    view = load_learning_view(source)
    dsl = (
        render_learning_zoomlandkarte_dsl(view)
        if template == "zoomlandkarte"
        else render_learning_dsl(view)
    )
    destination = Path(output) if output else None
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(dsl, encoding="utf-8")
    result = learning_render_receipt(view, dsl, output_path=destination)
    if template == "zoomlandkarte":
        spec = zoomlandkarte_template()
        result["template"] = spec.name
        result["used_primitives"] = list(spec.primitives)
        result["visual_strategy"] = "zoom-out-cluster-zoom-in-detail"
    if destination is None:
        result["dsl"] = dsl
    return result


def handle_learn_apply(
    *,
    input_path: str,
    alias: str,
    template: str = "classic",
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    source = Path(input_path)
    view = load_learning_view(source)
    dsl = (
        render_learning_zoomlandkarte_dsl(view)
        if template == "zoomlandkarte"
        else render_learning_dsl(view)
    )
    receipt = asyncio.run(
        (client or MiroMCPClient()).layout_create(
            alias=alias,
            dsl=dsl,
            invocation_source=f"schauwerk-learn-apply-{template}",
        )
    ).to_dict()
    return {
        "topic": view.topic,
        "audience": view.audience,
        "step_count": len(view.steps),
        "dsl_line_count": len([line for line in dsl.splitlines() if line.strip()]),
        "template": zoomlandkarte_template().name
        if template == "zoomlandkarte"
        else "learning-view-v1-rich",
        "layout": receipt,
    }


def _default_live_test_alias() -> str:
    return datetime.now(UTC).strftime("learn-live-%Y%m%d-%H%M%S")


def handle_learn_live_test(
    *,
    input_path: str,
    alias: str | None,
    board_name: str | None,
    output_dir: str | None,
    replace_alias: bool,
    item_limit: int,
    comment_limit: int,
    max_pages: int,
    include_comments: bool,
    template: str = "classic",
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    name = alias or _default_live_test_alias()
    source = Path(input_path)
    view = load_learning_view(source)
    dsl = (
        render_learning_zoomlandkarte_dsl(view)
        if template == "zoomlandkarte"
        else render_learning_dsl(view)
    )
    base = Path(output_dir) if output_dir else active.settings.snapshots_root / "live-tests" / name
    base.mkdir(parents=True, exist_ok=True)
    template_name = (
        zoomlandkarte_template().name if template == "zoomlandkarte" else "learning-view-v1-rich"
    )
    resolved_board_name = board_name or f"Schauwerk Learning Live Test: {view.topic}"

    board = asyncio.run(
        active.board_create(
            alias=name,
            name=resolved_board_name,
            description="Fresh Schauwerk learning-view live test board.",
            replace_alias=replace_alias,
            invocation_source=f"schauwerk-learn-live-test-{template}",
        )
    ).to_dict()
    before = asyncio.run(
        active.snapshot(
            alias=name,
            output_path=base / "before.json",
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )
    ).to_dict()
    layout = asyncio.run(
        active.layout_create(
            alias=name,
            dsl=dsl,
            invocation_source=f"schauwerk-learn-live-test-{template}",
        )
    ).to_dict()
    after = asyncio.run(
        active.snapshot(
            alias=name,
            output_path=base / "after.json",
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )
    ).to_dict()
    layout_read = asyncio.run(
        active.layout_read_summary(
            alias=name, invocation_source=f"schauwerk-learn-live-test-{template}"
        )
    ).to_dict()
    after_path = Path(str(after["output_path"]))
    quality = write_quality_receipt_from_snapshot_file(
        snapshot_path=after_path,
        destination=base / "quality.json",
        board_alias=name,
        expected_min_connectors=max(5, len(view.steps) + 3)
        if template == "zoomlandkarte"
        else max(0, len(view.steps) - 1),
        expected_min_docs=3 if template == "zoomlandkarte" else 1,
        expected_min_tables=4 if template == "zoomlandkarte" else 2,
        layout_read=layout_read,
    ).to_dict()
    live_test_record = create_live_test_record(
        active.settings,
        alias=name,
        reference_digest=str(board.get("reference_digest", "")),
        topic=view.topic,
        board_name=resolved_board_name,
        output_dir=base,
    ).to_dict()
    return {
        "topic": view.topic,
        "audience": view.audience,
        "step_count": len(view.steps),
        "dsl_line_count": len([line for line in dsl.splitlines() if line.strip()]),
        "template": template_name,
        "alias": name,
        "board": board,
        "before": before,
        "layout": layout,
        "after": after,
        "layout_read": layout_read,
        "quality": quality,
        "output_dir": str(base),
        "live_test_record": live_test_record,
        "mutation_attempted": True,
        "remote_cleanup_supported": False,
        "remote_cleanup_attempted": False,
    }


def handle_learn_live_prune(
    *, keep: int, dry_run: bool, client: MiroMCPClient | None = None
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    return prune_live_tests(active.settings, keep=keep, dry_run=dry_run).to_dict()


def handle_region_sw003_closeout(
    *, restore_receipt: str, evidence: str, marker: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_restore_receipt(Path(restore_receipt))
    closeout_evidence = load_sw003_closeout_evidence(Path(evidence))
    return compile_sw003_closeout_receipt(
        restore_receipt=receipt,
        evidence=closeout_evidence,
        marker=marker,
        output_path=Path(output) if output else None,
    )


def _write_local_cli_receipt(result: dict[str, Any], output: str | None) -> dict[str, Any]:
    if output is None:
        result["output_path"] = None
        return result
    destination = Path(output).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    result["output_path"] = str(destination)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def handle_region_sw003_live_gate(*, evidence: str, output: str | None) -> dict[str, Any]:
    live_gate_evidence = load_sw003_closeout_evidence(Path(evidence))
    result = evaluate_sw003_live_gate_claim(live_gate_evidence)
    result["mutation_attempted"] = False
    result["live_miro_access_attempted"] = False
    result["closes_live_sw003_gate"] = False
    result["creates_live_acceptance"] = False
    result["boundary"] = {
        "local_evaluation_only": True,
        "no_miro_mutation": True,
        "no_provider_ids_returned": True,
        "does_not_close_issue_8": True,
    }
    return _write_local_cli_receipt(result, output)


def handle_region_sw003_live_gate_requirements(*, output: str | None) -> dict[str, Any]:
    requirements = required_sw003_live_gate_evidence()
    result = {
        "schema_version": "typed-region-sw003-live-gate-requirements.v1",
        "ok": True,
        "mutation_attempted": False,
        "live_miro_access_attempted": False,
        "closes_live_sw003_gate": False,
        "creates_live_acceptance": False,
        "requirements": requirements,
        "requirements_digest": _stable_digest(requirements),
        "boundary": {
            "local_evaluation_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "does_not_close_issue_8": True,
        },
    }
    return _write_local_cli_receipt(result, output)


def handle_region_sw003_live_gate_template(*, output: str | None) -> dict[str, Any]:
    requirements = required_sw003_live_gate_evidence()
    evidence_template = {
        "claim_closes_live_sw003_gate": False,
        "live_create_attempted": False,
        "live_create_verified": False,
        "live_create_evidence_digest": "<sha256>",
        "live_read_after_create_verified": False,
        "live_read_after_create_evidence_digest": "<sha256>",
        "live_update_verified": False,
        "live_update_evidence_digest": "<sha256>",
        "marker_scope_uniqueness_verified": False,
        "marker_scope_evidence_digest": "<sha256>",
        "idempotency_verified": False,
        "idempotency_evidence_digest": "<sha256>",
        "cleanup_attempted": False,
        "cleanup_verified": False,
        "cleanup_evidence_digest": "<sha256>",
        "cleanup_boundary_accepted": False,
        "cleanup_boundary_reason": "",
        "provider_identifiers_sanitized": False,
        "board_scope": {"surface_alias": "", "allowlisted": False},
        "board_scope_evidence_digest": "<sha256>",
    }
    result = {
        "schema_version": "typed-region-sw003-live-gate-template.v1",
        "ok": True,
        "template_only": True,
        "mutation_attempted": False,
        "live_miro_access_attempted": False,
        "closes_live_sw003_gate": False,
        "creates_live_acceptance": False,
        "requirements": requirements,
        "requirements_digest": _stable_digest(requirements),
        "evidence_template": evidence_template,
        "evidence_template_digest": _stable_digest(evidence_template),
        "notes": [
            "replace placeholder digests with real sha256 evidence digests",
            "set claim_closes_live_sw003_gate true only for real live proof evidence",
            "do not include provider board URLs or provider object identifiers",
        ],
        "boundary": {
            "local_template_only": True,
            "no_miro_mutation": True,
            "no_provider_ids_returned": True,
            "does_not_close_issue_8": True,
        },
    }
    return _write_local_cli_receipt(result, output)


def handle_logout(client: MiroMCPClient | None = None) -> dict[str, bool]:
    return (client or MiroMCPClient()).logout()


def handle_region_plan(*, input_path: str, operation: str, output: str | None) -> dict[str, Any]:
    declaration = load_region_declaration(Path(input_path))
    return compile_region_operation_plan(
        declaration=declaration,
        operation=operation,
        output_path=Path(output) if output else None,
    )


def handle_region_preflight(
    *,
    input_path: str,
    snapshot: str,
    operation: str,
    output: str | None,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active_client = client or MiroMCPClient()
    declaration = load_region_declaration(Path(input_path))
    allowlisted_aliases = {
        board.alias for board in BoardAllowlist(active_client.settings.board_allowlist_path).list()
    }
    return compile_region_preflight(
        declaration=declaration,
        allowlisted_aliases=allowlisted_aliases,
        snapshot_path=Path(snapshot),
        operation=operation,
        output_path=Path(output) if output else None,
    )


def handle_region_apply_scaffold(*, preflight: str, output: str | None) -> dict[str, Any]:
    receipt = load_region_preflight(Path(preflight))
    return compile_region_apply_scaffold(
        preflight=receipt,
        output_path=Path(output) if output else None,
    )


def handle_region_apply_receipt(
    *, scaffold: str, fixture: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_apply_scaffold(Path(scaffold))
    fixture_operations = load_fixture_operations(Path(fixture))
    return compile_region_apply_receipt(
        scaffold=receipt,
        fixture_operations=fixture_operations,
        output_path=Path(output) if output else None,
    )



def handle_region_operation_contract(
    *, scaffold: str, fixture: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_apply_scaffold(Path(scaffold))
    fixture_operations = load_fixture_operations(Path(fixture))
    return compile_region_operation_contract(
        scaffold=receipt,
        fixture_operations=fixture_operations,
        output_path=Path(output) if output else None,
    )


def handle_region_apply_simulation(
    *, operation_contract: str, after_snapshot: str, output: str | None
) -> dict[str, Any]:
    contract = load_region_operation_contract(Path(operation_contract))
    snapshot = load_snapshot_mapping_receipt(Path(after_snapshot), label="after")
    return compile_region_apply_simulation_receipt(
        operation_contract=contract,
        after_snapshot=snapshot,
        output_path=Path(output) if output else None,
    )


def handle_region_simulation_postflight(
    *, apply_simulation_receipt: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_apply_simulation_receipt(Path(apply_simulation_receipt))
    return compile_region_simulation_postflight_receipt(
        apply_simulation_receipt=receipt,
        output_path=Path(output) if output else None,
    )


def handle_region_simulation_closeout(
    *, restore_receipt: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_restore_receipt(Path(restore_receipt))
    return compile_region_simulation_closeout_receipt(
        restore_receipt=receipt,
        output_path=Path(output) if output else None,
    )


def handle_region_postflight(
    *, apply_receipt: str, after_snapshot: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_apply_receipt(Path(apply_receipt))
    snapshot = load_snapshot_mapping_receipt(Path(after_snapshot), label="after")
    return compile_region_postflight_receipt(
        apply_receipt=receipt,
        after_snapshot=snapshot,
        output_path=Path(output) if output else None,
    )


def handle_region_restore_receipt(
    *, postflight: str, restored_snapshot: str, output: str | None
) -> dict[str, Any]:
    receipt = load_region_postflight_receipt(Path(postflight))
    snapshot = load_snapshot_mapping_receipt(Path(restored_snapshot), label="restored")
    return compile_region_restore_receipt(
        postflight_receipt=receipt,
        restored_snapshot=snapshot,
        output_path=Path(output) if output else None,
    )
