"""Command handlers for the Schauwerk CLI."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .durable.adapters import (
    adapter_catalog,
    compile_observation_file,
    compile_observation_set,
    load_observation,
    load_observation_set,
)
from .durable.common import read_json as read_durable_json
from .durable.common import write_json as write_durable_json
from .durable.maintenance import compile_maintenance_proposal
from .durable.operations import (
    compile_backup_manifest,
    compile_health_receipt,
    compile_kill_switch_drill,
    compile_oauth_rotation_plan,
    load_backup_manifest,
    operation_profiles,
    verify_staged_restore,
)
from .durable.search import (
    compile_search_index,
    load_search_index,
    search_index,
    semantic_suggestions,
)
from .ecosystem_map import render_ecosystem_map_html
from .education.variants import write_education_variant, write_offline_package
from .education.view import (
    learning_render_receipt,
    load_learning_view,
    render_learning_dsl,
)
from .education.zoomlandkarte import render_learning_zoomlandkarte_dsl
from .operator.live_apply import (
    compile_live_apply_plan,
    compile_live_authorization,
    compile_live_operation_bundle_template,
    disable_kill_switch,
    enable_kill_switch,
    execute_live_apply,
    kill_switch_status,
    live_artifact_destination,
    load_live_apply_gate,
    load_live_apply_plan,
    load_live_authorization,
    load_live_operation_bundle,
    load_live_operation_draft,
    load_live_transaction_receipt,
    restore_live_apply,
    write_live_apply_plan,
    write_live_artifact,
)
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
    compile_region_sw009_live_apply_candidate_receipt,
    compile_region_sw009_live_apply_candidate_template,
    compile_region_sw009_live_apply_gate_receipt,
    compile_sw003_closeout_receipt,
    compile_sw003_live_gate_evidence_packet,
    compile_sw003_live_gate_review_packet,
    compile_sw003_live_gate_status_receipt,
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
    load_region_sw009_live_apply_candidate,
    load_snapshot_mapping_receipt,
    load_sw003_closeout_evidence,
    load_sw003_live_gate_evaluation_receipt,
    load_sw003_live_gate_evidence_packet,
    load_sw003_live_gate_review_packet,
    load_sw003_live_gate_status_receipt,
    required_sw003_live_gate_evidence,
)
from .operator.sw003_closeout import LIVE_GATE_EVALUATION_SCHEMA_VERSION
from .overview.collector import collect_overview
from .overview.model import write_snapshot as write_overview_snapshot
from .overview.server import serve_overview
from .pilots.grabowski import write_grabowski_pilot
from .pilots.grabowski_operational import write_operational_pilot
from .pilots.software import write_software_pilot
from .presentation.package import build_presentation_packages
from .publication.model import compile_preview, load_declaration, load_preview
from .publication.server import serve_publications
from .publication.store import (
    publication_status,
    release_publication,
    withdraw_publication,
    write_new_json,
)
from .regie.model import (
    compile_regie_context,
    compile_review_bundle,
    load_regie_context,
    load_review_bundle,
    read_private_json,
    write_private_json,
)
from .regie.server import serve_regie
from .regie.service import RegieController
from .registry_runtime import registry_show, registry_status
from .surfaces.miro.board_registry import BoardAllowlist, reference_digest
from .surfaces.miro.capability_audit import audit_tool_catalogue
from .surfaces.miro.client import MiroMCPClient
from .surfaces.miro.companion_release import (
    CompanionReleaseError,
    check_release_manifest,
    companion_gate_status,
    create_release_manifest,
    doctor_release,
)
from .surfaces.miro.live_test_index import create_live_test_record, prune_live_tests
from .surfaces.miro.managed_image_service import check_managed_image
from .surfaces.miro.managed_region_runtime import MiroManagedRegionProvider
from .surfaces.miro.native_executor import load_native_bundle, required_tools
from .surfaces.miro.quality import write_quality_receipt_from_snapshot_file
from .surfaces.miro.rest_client import MiroRestClient
from .surfaces.miro.rest_credentials import MiroRestTokenStorage
from .surfaces.miro.visual_truth import (
    check_visual_truth_receipt,
    create_visual_truth_receipt,
    load_visual_truth_context,
)
from .surfaces.miro.web_sdk_companion import build_companion, verify_companion
from .visual.delivery import (
    NativeDeliveryClient,
    check_representation_package,
)
from .visual.delivery_runtime import deliver_representation_package
from .visual.grammar import (
    validate_visual_grammar,
    visual_grammar_manifest,
    write_visual_grammar,
    zoomlandkarte_template,
)
from .visual.preview import build_visual_preview, write_visual_regression
from .visual.representation import compile_representation_package
from .visual.system_v2 import (
    compile_visual_review,
    reference_board_spec,
    render_board_dsl,
    validate_board_spec,
    visual_system_manifest,
)
from .visual.system_v2 import (
    write_json as write_visual_json,
)
from .visual.system_v2 import (
    write_text as write_visual_text,
)


def _durable_output(
    value: dict[str, Any], *, output: str | None, digest_field: str
) -> dict[str, Any]:
    if output is None:
        return value
    destination = write_durable_json(Path(output), value)
    return {
        "schema_version": "schauwerk-durable-write-receipt.v1",
        "ok": True,
        "output": str(destination),
        "artifact_schema": value["schema_version"],
        "artifact_digest": value[digest_field],
        "artifact_write_performed": True,
        "provider_mutation_attempted": False,
    }


def handle_durable_adapter_catalog(*, output: str | None) -> dict[str, Any]:
    return _durable_output(adapter_catalog(), output=output, digest_field="catalog_digest")


def handle_durable_adapter_collect(
    *, input_path: str, evaluated_at: str, output: str
) -> dict[str, Any]:
    value = compile_observation_file(Path(input_path), evaluated_at=evaluated_at)
    return _durable_output(value, output=output, digest_field="observation_digest")


def handle_durable_adapter_set(
    *, observations: list[str], created_at: str, output: str
) -> dict[str, Any]:
    value = compile_observation_set(
        [load_observation(Path(path)) for path in observations], created_at=created_at
    )
    return _durable_output(value, output=output, digest_field="set_digest")


def handle_durable_maintenance(
    *, previous: str, current: str, region: str, created_at: str, output: str
) -> dict[str, Any]:
    value = compile_maintenance_proposal(
        load_observation_set(Path(previous)),
        load_observation_set(Path(current)),
        region_id=region,
        created_at=created_at,
    )
    return _durable_output(value, output=output, digest_field="proposal_digest")


def handle_durable_search_index(
    *, observation_set: str, created_at: str, disabled_reason: str | None, output: str
) -> dict[str, Any]:
    value = compile_search_index(
        load_observation_set(Path(observation_set)),
        created_at=created_at,
        disabled_reason=disabled_reason,
    )
    return _durable_output(value, output=output, digest_field="index_digest")


def handle_durable_search_query(
    *, index: str, query: str, visibility: str, limit: int
) -> dict[str, Any]:
    return search_index(
        load_search_index(Path(index)), query=query, visibility=visibility, limit=limit
    )


def handle_durable_search_suggest(*, index: str, visibility: str) -> dict[str, Any]:
    return semantic_suggestions(load_search_index(Path(index)), visibility=visibility)


def handle_durable_profiles(*, output: str | None) -> dict[str, Any]:
    return _durable_output(operation_profiles(), output=output, digest_field="profile_digest")


def handle_durable_health(*, input_path: str, observed_at: str, output: str) -> dict[str, Any]:
    value = compile_health_receipt(
        read_durable_json(Path(input_path), label="health input"), observed_at=observed_at
    )
    return _durable_output(value, output=output, digest_field="health_digest")


def handle_durable_backup(
    *, declaration: str, root: str, created_at: str, output: str
) -> dict[str, Any]:
    value = compile_backup_manifest(
        read_durable_json(Path(declaration), label="backup declaration"),
        root=Path(root),
        created_at=created_at,
    )
    return _durable_output(value, output=output, digest_field="manifest_digest")


def handle_durable_restore_verify(
    *, manifest: str, staged_root: str, verified_at: str, output: str
) -> dict[str, Any]:
    value = verify_staged_restore(
        load_backup_manifest(Path(manifest)),
        staged_root=Path(staged_root),
        verified_at=verified_at,
    )
    return _durable_output(value, output=output, digest_field="verification_digest")


def handle_durable_rotation_plan(
    *, input_path: str, created_at: str, output: str
) -> dict[str, Any]:
    value = compile_oauth_rotation_plan(
        read_durable_json(Path(input_path), label="OAuth rotation input"),
        created_at=created_at,
    )
    return _durable_output(value, output=output, digest_field="plan_digest")


def handle_durable_kill_switch_drill(
    *, input_path: str, created_at: str, output: str
) -> dict[str, Any]:
    value = compile_kill_switch_drill(
        read_durable_json(Path(input_path), label="kill-switch drill input"),
        created_at=created_at,
    )
    return _durable_output(value, output=output, digest_field="drill_digest")


def handle_overview_snapshot(*, output: str, probe_provider: bool) -> dict[str, Any]:
    client = MiroMCPClient()
    snapshot = asyncio.run(
        collect_overview(
            miro_client=client,
            probe_provider=probe_provider,
        )
    )
    destination = write_overview_snapshot(Path(output), snapshot)
    return {
        "schema_version": "schauwerk-overview-snapshot-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "probe_provider": probe_provider,
        "snapshot_digest": snapshot["snapshot_digest"],
        "project_count": snapshot["summary"]["project_count"],
        "view_count": snapshot["summary"]["view_count"],
        "active_job_count": snapshot["summary"]["active_job_count"],
        "error_count": snapshot["summary"]["error_count"],
        "provider_state": snapshot["summary"]["provider_state"],
        "output_path": str(destination),
    }


def handle_overview_serve(*, port: int, probe_provider: bool, open_browser: bool) -> dict[str, Any]:
    client = MiroMCPClient()

    async def snapshot_factory() -> dict[str, Any]:
        return await collect_overview(
            miro_client=client,
            probe_provider=probe_provider,
        )

    serve_overview(snapshot_factory, port=port, open_browser=open_browser)
    return {
        "schema_version": "schauwerk-overview-server-stop-receipt.v1",
        "ok": True,
        "read_only": True,
        "loopback_only": True,
        "probe_provider": probe_provider,
    }


def handle_regie_context_template(*, review_id: str, title: str, output: str) -> dict[str, Any]:
    draft = {
        "review_id": review_id,
        "title": title,
        "summary": "EDIT ME: bounded purpose of this review",
        "instructions": ["EDIT ME: review instruction"],
        "sources": [
            {
                "source_id": "edit-me-source",
                "title": "EDIT ME: source title",
                "revision": "EDIT ME",
                "observed_at": datetime.now(UTC)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "freshness": "unknown",
                "visibility": "private",
                "citation": "source:edit-me",
                "uncertainty": 1.0,
            }
        ],
        "context": [
            {
                "label": "EDIT ME: constraint",
                "value": "EDIT ME: bounded context",
                "state": "constraint",
                "source_id": "edit-me-source",
            }
        ],
    }
    destination = write_private_json(Path(output), draft, label="Regie context draft")
    return {
        "schema_version": "schauwerk-regie-context-template-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "review_id": review_id,
        "output_path": str(destination),
    }


def handle_regie_context_compile(*, draft_path: str, output: str) -> dict[str, Any]:
    draft = read_private_json(Path(draft_path), label="Regie context draft")
    context = compile_regie_context(draft)
    destination = write_private_json(Path(output), context, label="Regie context")
    return {
        "schema_version": "schauwerk-regie-context-compile-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "review_id": context["review_id"],
        "context_digest": context["context_digest"],
        "output_path": str(destination),
    }


def handle_regie_review(
    *, context_path: str, gate_path: str, bundle_path: str, output: str
) -> dict[str, Any]:
    review = compile_review_bundle(
        context=load_regie_context(Path(context_path)),
        gate_receipt=load_live_apply_gate(Path(gate_path)),
        operation_bundle=load_live_operation_bundle(Path(bundle_path)),
    )
    destination = write_private_json(Path(output), review, label="Regie review bundle")
    return {
        "schema_version": "schauwerk-regie-review-compile-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "review_id": review["review_id"],
        "review_digest": review["review_digest"],
        "operation_count": len(review["operations"]),
        "stale_source_ids": review["stale_source_ids"],
        "maximum_uncertainty": review["maximum_uncertainty"],
        "output_path": str(destination),
    }


def handle_regie_serve(*, review_bundle: str, port: int, open_browser: bool) -> dict[str, Any]:
    review = load_review_bundle(Path(review_bundle))
    client = MiroMCPClient()

    async def provider_factory() -> MiroManagedRegionProvider:
        catalogue = (await client.tools()).to_dict()
        return MiroManagedRegionProvider(client.settings, client.storage, cached_tools=catalogue)

    controller = RegieController(
        review_bundle=review,
        state_root=client.settings.state_root.parent / "regie",
        journal_root=client.settings.state_root / "transactions",
        kill_switch_path=client.settings.state_root / "LIVE_APPLY_DISABLED",
        provider_factory=provider_factory,
    )
    serve_regie(controller, port=port, open_browser=open_browser)
    return {
        "schema_version": "schauwerk-regie-server-stop-receipt.v1",
        "ok": True,
        "loopback_only": True,
        "review_digest": controller.review["review_digest"],
    }


def handle_stage_build(
    *,
    model_path: str,
    variant: str,
    public_dir: str,
    presenter_dir: str,
    source_root: str,
) -> dict[str, Any]:
    return build_presentation_packages(
        model_path=Path(model_path),
        variant_id=variant,
        public_dir=Path(public_dir),
        presenter_dir=Path(presenter_dir),
        source_root=Path(source_root),
    )


def handle_publication_preview(
    *, declaration_path: str, source_package: str, output: str
) -> dict[str, Any]:
    declaration = load_declaration(Path(declaration_path))
    preview, _ = compile_preview(declaration, Path(source_package))
    destination = write_new_json(Path(output), preview, mode=0o644)
    return {
        "schema_version": "schauwerk-publication-preview-receipt.v1",
        "ok": True,
        "publication_id": preview["publication_id"],
        "stable_slug": preview["stable_slug"],
        "version": preview["version"],
        "preview_digest": preview["preview_digest"],
        "output_path": str(destination),
        "source_truth_mutated": False,
        "provider_mutation_attempted": False,
    }


def handle_publication_release(
    *,
    declaration_path: str,
    preview_path: str,
    source_package: str,
    store_root: str,
) -> dict[str, Any]:
    return release_publication(
        declaration=load_declaration(Path(declaration_path)),
        preview=load_preview(Path(preview_path)),
        source_dir=Path(source_package),
        store_root=Path(store_root),
    )


def handle_publication_status(
    *, store_root: str, stable_slug: str, observed_at: str | None
) -> dict[str, Any]:
    return publication_status(Path(store_root), stable_slug, now=observed_at)


def handle_publication_withdraw(
    *,
    store_root: str,
    stable_slug: str,
    expected_link_digest: str,
    reason: str,
    withdrawn_at: str | None,
) -> dict[str, Any]:
    return withdraw_publication(
        Path(store_root),
        stable_slug,
        expected_link_digest=expected_link_digest,
        reason=reason,
        withdrawn_at=withdrawn_at,
    )


def handle_publication_serve(*, store_root: str, port: int, open_browser: bool) -> dict[str, Any]:
    return serve_publications(Path(store_root), port=port, open_browser=open_browser)


def handle_visual_route(*, input_path: str, output_dir: str) -> dict[str, Any]:
    return compile_representation_package(
        input_path=Path(input_path),
        output_dir=Path(output_dir),
    )


def handle_visual_package_check(*, package_dir: str) -> dict[str, Any]:
    return check_representation_package(Path(package_dir))


def handle_visual_preview(*, package_dir: str, output_dir: str) -> dict[str, Any]:
    return build_visual_preview(
        package_dir=Path(package_dir),
        output_dir=Path(output_dir),
    )


def handle_visual_compare(*, baseline: str, candidate: str, output: str) -> dict[str, Any]:
    return write_visual_regression(
        baseline_path=Path(baseline),
        candidate_path=Path(candidate),
        output=Path(output),
    )


def handle_visual_deliver(
    *,
    alias: str,
    package_dir: str,
    output_dir: str,
    resume: bool,
    client: NativeDeliveryClient | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        deliver_representation_package(
            alias=alias,
            package_dir=Path(package_dir),
            output_dir=Path(output_dir),
            client=client or MiroMCPClient(),
            resume=resume,
        )
    )


def handle_visual_grammar(*, output: str | None) -> dict[str, Any]:
    if output:
        return write_visual_grammar(Path(output))
    manifest = visual_grammar_manifest()
    return {
        "validation": validate_visual_grammar(manifest),
        "manifest": manifest,
    }


def handle_visual_system_v2(*, output: str | None) -> dict[str, Any]:
    manifest = visual_system_manifest()
    if output:
        destination = write_visual_json(Path(output), manifest)
        return {
            "schema_version": "schauwerk-visual-system-write-receipt.v2",
            "manifest_digest": manifest["manifest_digest"],
            "output": str(destination),
            "mutation_attempted": False,
        }
    return manifest


def handle_visual_reference_v2(
    *, spec_output: str | None, dsl_output: str | None, quality_output: str | None
) -> dict[str, Any]:
    spec = reference_board_spec()
    quality = validate_board_spec(spec)
    rendered = render_board_dsl(spec)
    outputs: dict[str, str] = {}
    if spec_output:
        outputs["spec"] = str(write_visual_json(Path(spec_output), spec))
    if dsl_output:
        outputs["dsl"] = str(write_visual_text(Path(dsl_output), rendered))
    if quality_output:
        outputs["quality"] = str(write_visual_json(Path(quality_output), quality))
    return {
        "schema_version": "schauwerk-visual-reference-compile.v2",
        "board_digest": spec["board_digest"],
        "quality": quality,
        "frame_count": len(spec["frames"]),
        "object_count": sum(len(frame["objects"]) for frame in spec["frames"]),
        "dsl_line_count": len([line for line in rendered.splitlines() if line.strip()]),
        "outputs": outputs,
        "mutation_attempted": False,
    }


def handle_visual_review_v2(*, live_receipt: str, review_input: str, output: str) -> dict[str, Any]:
    value = compile_visual_review(
        read_durable_json(Path(live_receipt), label="Visual System v2 live receipt"),
        read_durable_json(Path(review_input), label="Visual System v2 review input"),
    )
    destination = write_visual_json(Path(output), value)
    return {
        "schema_version": "schauwerk-visual-review-write-receipt.v2",
        "review_digest": value["review_digest"],
        "verdict": value["verdict"],
        "output": str(destination),
        "mutation_attempted": False,
    }


def handle_visual_v2_live_test(
    *,
    alias: str,
    board_name: str,
    output_dir: str | None,
    replace_alias: bool,
    reuse_existing_alias: bool,
    resume_after_layout: bool,
    item_limit: int,
    comment_limit: int,
    max_pages: int,
    include_comments: bool,
    spec_input: str | None = None,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    spec = (
        read_durable_json(Path(spec_input), label="Visual System v2 board specification")
        if spec_input
        else reference_board_spec()
    )
    quality = validate_board_spec(spec)
    rendered = render_board_dsl(spec)
    base = Path(output_dir) if output_dir else active.settings.snapshots_root / "live-tests" / alias
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_visual_json(base / "visual-system.json", visual_system_manifest())
    write_visual_json(base / "board-spec.json", spec)
    write_visual_json(base / "quality-v2.json", quality)
    write_visual_text(base / "board.dsl", rendered)

    if replace_alias and reuse_existing_alias:
        raise ValueError("replace and reuse are mutually exclusive")
    if resume_after_layout and not reuse_existing_alias:
        raise ValueError("resume after layout requires reuse existing alias")
    if reuse_existing_alias:
        allowlist = BoardAllowlist(active.settings.board_allowlist_path)
        entry = next((item for item in allowlist.list() if item.alias == alias), None)
        if entry is None:
            raise ValueError("Visual System v2 reuse requires an allowlisted alias")
        board = {
            "alias": entry.alias,
            "reference_digest": entry.reference_digest,
            "reused_existing_alias": True,
        }
    else:
        board = asyncio.run(
            active.board_create(
                alias=alias,
                name=board_name,
                description=(
                    f"Schauwerk Visual System v2 board: {spec['title']}. Purpose: {spec['purpose']}"
                ),
                replace_alias=replace_alias,
                invocation_source="schauwerk-visual-system-v2",
            )
        ).to_dict()
        board["reused_existing_alias"] = False
    write_visual_json(base / "board-binding.json", board)
    if resume_after_layout:
        before_path = base / "before.json"
        if not before_path.is_file() or before_path.is_symlink():
            raise ValueError("resume after layout requires a safe before snapshot")
        before = {
            "board_alias": alias,
            "output_path": str(before_path),
            "resumed_from_existing": True,
        }
        layout = {
            "success": True,
            "resumed_after_layout": True,
            "created_count": None,
        }
    else:
        before = asyncio.run(
            active.snapshot(
                alias=alias,
                output_path=base / "before.json",
                item_limit=item_limit,
                comment_limit=comment_limit,
                max_pages=max_pages,
                include_comments=include_comments,
            )
        ).to_dict()
        layout = asyncio.run(
            active.layout_create(
                alias=alias,
                dsl=rendered,
                invocation_source="schauwerk-visual-system-v2",
            )
        ).to_dict()
    after = asyncio.run(
        active.snapshot(
            alias=alias,
            output_path=base / "after.json",
            item_limit=item_limit,
            comment_limit=comment_limit,
            max_pages=max_pages,
            include_comments=include_comments,
        )
    ).to_dict()
    layout_read = asyncio.run(
        active.layout_read_summary(alias=alias, invocation_source="schauwerk-visual-system-v2")
    ).to_dict()
    expected = {
        "frame_count": len(spec["frames"]),
        "connector_count": sum(
            item["kind"] == "connector" for frame in spec["frames"] for item in frame["objects"]
        ),
        "doc_count": sum(
            item["kind"] == "doc" for frame in spec["frames"] for item in frame["objects"]
        ),
        "table_count": sum(
            item["kind"] == "table" for frame in spec["frames"] for item in frame["objects"]
        ),
        "remote_item_count": len(spec["frames"])
        + sum(item["kind"] != "connector" for frame in spec["frames"] for item in frame["objects"]),
    }
    snapshot_document = json.loads((base / "after.json").read_text(encoding="utf-8"))
    snapshot_items = snapshot_document.get("items")
    if not isinstance(snapshot_items, list):
        raise ValueError("Visual System v2 after snapshot has no item list")
    type_counts: dict[str, int] = {}
    for item in snapshot_items:
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            type_counts[item["type"]] = type_counts.get(item["type"], 0) + 1
    observed = {
        "frame_count": type_counts.get("frame", 0),
        "connector_count": int(layout_read.get("connector_count", 0)),
        "doc_count": type_counts.get("doc_format", 0),
        "table_count": type_counts.get("data_table_format", 0),
        "remote_item_count": len(snapshot_items),
    }
    mismatches = {
        key: {"expected_minimum": value, "observed": observed[key]}
        for key, value in expected.items()
        if observed[key] < value
    }
    if mismatches:
        raise ValueError("Visual System v2 remote readback does not conform to the compiled plan")
    remote_conformance = {
        "ok": True,
        "expected_minimums": expected,
        "observed": observed,
        "mismatches": {},
        "geometry_used_for_aesthetic_score": False,
    }
    live_test_record = create_live_test_record(
        active.settings,
        alias=alias,
        reference_digest=str(board.get("reference_digest", "")),
        topic=str(spec["title"]),
        board_name=board_name,
        output_dir=base,
    ).to_dict()
    result = {
        "schema_version": "schauwerk-visual-system-live-test.v2",
        "alias": alias,
        "board_name": board_name,
        "content_source": "provided_spec" if spec_input else "reference_board",
        "spec_input": spec_input,
        "board": board,
        "before": before,
        "layout": layout,
        "after": after,
        "layout_read": layout_read,
        "local_quality": quality,
        "remote_conformance": remote_conformance,
        "visual_acceptance": {
            "authenticated_provider_capture_required": True,
            "status": "pending_authenticated_provider_capture",
            "automatic_aesthetic_verdict": False,
        },
        "visual_review": {
            "status": "pending_separate_ui_review",
            "automatic_score_prohibited": True,
        },
        "output_dir": str(base),
        "live_test_record": live_test_record,
        "mutation_attempted": True,
        "existing_board_mutation_attempted": reuse_existing_alias,
        "partial_live_run_recovered": reuse_existing_alias,
        "resumed_after_layout": resume_after_layout,
        "remote_cleanup_supported": False,
        "remote_cleanup_attempted": False,
    }
    write_visual_json(base / "live-test-receipt.json", result)
    return result


def handle_education_render(*, input_path: str, variant: str, output: str | None) -> dict[str, Any]:
    return write_education_variant(
        input_path=Path(input_path),
        variant=variant,
        output=Path(output) if output else None,
    )


def handle_education_offline(*, input_path: str, output_dir: str, variant: str) -> dict[str, Any]:
    return write_offline_package(
        input_path=Path(input_path),
        output_dir=Path(output_dir),
        variant=variant,
    )


def handle_ecosystem_render(
    *, manifest: str, output: str, source_root: str | None
) -> dict[str, Any]:
    return render_ecosystem_map_html(
        manifest_path=Path(manifest),
        output_path=Path(output),
        source_root=source_root,
    )


def handle_registry_status() -> dict[str, Any]:
    return registry_status()


def handle_registry_show(*, kind: str, identifier: str | None) -> dict[str, Any]:
    return registry_show(kind, identifier)


def handle_grabowski_pilot(
    *, operator_context: str, snapshot_output: str | None, dsl_output: str | None
) -> dict[str, Any]:
    return write_grabowski_pilot(
        operator_context=Path(operator_context),
        snapshot_output=Path(snapshot_output) if snapshot_output else None,
        dsl_output=Path(dsl_output) if dsl_output else None,
    )


def handle_grabowski_operational_pilot(
    *,
    static_snapshot: str,
    observation: str,
    snapshot_output: str | None,
    dsl_output: str | None,
) -> dict[str, Any]:
    return write_operational_pilot(
        static_snapshot_path=Path(static_snapshot),
        observation_path=Path(observation),
        snapshot_output=Path(snapshot_output) if snapshot_output else None,
        dsl_output=Path(dsl_output) if dsl_output else None,
    )


def handle_software_pilot(
    *,
    input_path: str,
    snapshot_output: str | None,
    dsl_output: str | None,
    visual_spec_output: str | None = None,
    visual_quality_output: str | None = None,
    visual_dsl_output: str | None = None,
) -> dict[str, Any]:
    return write_software_pilot(
        input_path=Path(input_path),
        snapshot_output=Path(snapshot_output) if snapshot_output else None,
        dsl_output=Path(dsl_output) if dsl_output else None,
        visual_spec_output=Path(visual_spec_output) if visual_spec_output else None,
        visual_quality_output=(Path(visual_quality_output) if visual_quality_output else None),
        visual_dsl_output=Path(visual_dsl_output) if visual_dsl_output else None,
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


def handle_capability_audit(
    client: MiroMCPClient | None = None,
    rest_client: MiroRestClient | None = None,
) -> dict[str, Any]:
    catalogue = asyncio.run((client or MiroMCPClient()).tools()).to_dict()
    return audit_tool_catalogue(
        catalogue,
        rest_status=(rest_client or MiroRestClient()).status(),
    )


def handle_native_check(*, input_path: str) -> dict[str, Any]:
    bundle = load_native_bundle(Path(input_path))
    return {
        "schema_version": "schauwerk-miro-native-check.v1",
        "ok": True,
        "bundle_id": bundle["bundle_id"],
        "bundle_digest": bundle["bundle_digest"],
        "operation_count": len(bundle["operations"]),
        "operation_kinds": [operation["kind"] for operation in bundle["operations"]],
        "required_tools": list(required_tools(bundle)),
        "mutation_attempted": False,
    }


def handle_native_apply(
    *,
    alias: str,
    input_path: str,
    output: str,
    resume: str | None = None,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        (client or MiroMCPClient()).native_apply(
            alias=alias,
            input_path=Path(input_path),
            output_path=Path(output),
            resume_path=Path(resume) if resume else None,
        )
    )


def handle_companion_build(*, input_path: str, output_dir: str) -> dict[str, Any]:
    return build_companion(input_path=Path(input_path), output_dir=Path(output_dir))


def handle_companion_check(*, output_dir: str) -> dict[str, Any]:
    return verify_companion(output_dir=Path(output_dir))


def handle_companion_gate_status() -> dict[str, Any]:
    return companion_gate_status()


def handle_companion_release_create(
    *, bundle_dir: str, app_url: str, developer_app_label: str, output: str
) -> dict[str, Any]:
    return create_release_manifest(
        bundle_dir=Path(bundle_dir),
        app_url=app_url,
        developer_app_label=developer_app_label,
        output=Path(output),
    )


def handle_companion_release_check(
    *, manifest: str, bundle_dir: str | None = None
) -> dict[str, Any]:
    return check_release_manifest(
        manifest_path=Path(manifest),
        bundle_dir=Path(bundle_dir) if bundle_dir else None,
    )


def handle_companion_release_doctor(*, manifest: str, timeout: float) -> dict[str, Any]:
    result = doctor_release(manifest_path=Path(manifest), timeout=timeout)
    if result.get("success") is not True:
        failures = result.get("failures")
        summary = (
            "; ".join(str(item) for item in failures[:3])
            if isinstance(failures, list)
            else "unknown failure"
        )
        raise CompanionReleaseError(f"companion HTTPS doctor failed: {summary}")
    return result


def handle_visual_truth_create(
    *, snapshot: str, capture: str, context: str, output: str
) -> dict[str, Any]:
    context_value = load_visual_truth_context(Path(context))
    active = MiroMCPClient()
    board_url = BoardAllowlist(active.settings.board_allowlist_path).resolve(
        context_value["board_alias"]
    )
    return create_visual_truth_receipt(
        snapshot=Path(snapshot),
        capture=Path(capture),
        context=Path(context),
        expected_board_reference_digest=reference_digest(board_url),
        output=Path(output),
    )


def handle_visual_truth_check(*, receipt: str) -> dict[str, Any]:
    return check_visual_truth_receipt(receipt=Path(receipt))


def handle_rest_status(rest_client: MiroRestClient | None = None) -> dict[str, Any]:
    return (rest_client or MiroRestClient()).status()


def handle_rest_token_install(
    *,
    source: str,
    replace: bool = False,
    storage: MiroRestTokenStorage | None = None,
) -> dict[str, Any]:
    return (storage or MiroRestTokenStorage()).install_from_file(Path(source), replace=replace)


def handle_rest_doctor(
    *,
    require_write: bool = False,
    rest_client: MiroRestClient | None = None,
) -> dict[str, Any]:
    return asyncio.run((rest_client or MiroRestClient()).doctor(require_write=require_write))


def handle_managed_image_check(
    *,
    alias: str,
    identity: str,
    image: str | None,
    content_type: str | None,
) -> dict[str, Any]:
    return check_managed_image(
        alias=alias,
        identity_path=Path(identity),
        image_path=Path(image) if image else None,
        content_type=content_type,
    )


def handle_managed_image_replace(
    *,
    alias: str,
    identity: str,
    image: str,
    content_type: str,
    title: str,
    receipt_output: str,
    identity_output: str,
    max_pages: int,
    client: MiroMCPClient | None = None,
    rest_client: MiroRestClient | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        (client or MiroMCPClient()).managed_image_replace(
            alias=alias,
            identity_path=Path(identity),
            image_path=Path(image),
            content_type=content_type,
            title=title,
            receipt_path=Path(receipt_output),
            identity_output_path=Path(identity_output),
            rest_client=rest_client,
            max_pages=max_pages,
        )
    )


def handle_managed_image_delete(
    *,
    alias: str,
    identity: str,
    receipt_output: str,
    max_pages: int,
    client: MiroMCPClient | None = None,
    rest_client: MiroRestClient | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        (client or MiroMCPClient()).managed_image_delete(
            alias=alias,
            identity_path=Path(identity),
            receipt_path=Path(receipt_output),
            rest_client=rest_client,
            max_pages=max_pages,
        )
    )


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
    requirements = required_sw003_live_gate_evidence()
    result = evaluate_sw003_live_gate_claim(live_gate_evidence)
    result["schema_version"] = LIVE_GATE_EVALUATION_SCHEMA_VERSION
    result["evidence_input_digest"] = _stable_digest(live_gate_evidence)
    result["requirements_digest"] = _stable_digest(requirements)
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
    result["evaluation_digest"] = _stable_digest(result)
    return _write_local_cli_receipt(result, output)


def handle_region_sw003_live_gate_status(
    *, evaluation_receipt: str, output: str | None
) -> dict[str, Any]:
    receipt = load_sw003_live_gate_evaluation_receipt(Path(evaluation_receipt))
    return compile_sw003_live_gate_status_receipt(
        evaluation_receipt=receipt,
        output_path=Path(output) if output else None,
    )


def handle_region_sw003_live_gate_review_packet(
    *, status_receipt: str, output: str | None
) -> dict[str, Any]:
    receipt = load_sw003_live_gate_status_receipt(Path(status_receipt))
    return compile_sw003_live_gate_review_packet(
        status_receipt=receipt,
        output_path=Path(output) if output else None,
    )


def handle_region_sw003_live_gate_evidence_packet(
    *, review_packet: str, output: str | None
) -> dict[str, Any]:
    packet = load_sw003_live_gate_review_packet(Path(review_packet))
    return compile_sw003_live_gate_evidence_packet(
        review_packet=packet,
        output_path=Path(output) if output else None,
    )


def handle_region_sw009_live_apply_gate(
    *,
    scaffold: str,
    sw003_evidence_packet: str,
    output: str | None,
    acknowledgements: dict[str, bool],
) -> dict[str, Any]:
    scaffold_receipt = load_region_apply_scaffold(Path(scaffold))
    evidence_packet = load_sw003_live_gate_evidence_packet(Path(sw003_evidence_packet))
    return compile_region_sw009_live_apply_gate_receipt(
        scaffold=scaffold_receipt,
        sw003_evidence_packet=evidence_packet,
        acknowledgements=acknowledgements,
        output_path=Path(output) if output else None,
    )


def handle_region_sw009_live_apply_candidate_template(*, output: str | None) -> dict[str, Any]:
    return compile_region_sw009_live_apply_candidate_template(
        output_path=Path(output) if output else None
    )


def handle_region_sw009_live_apply_candidate_check(
    *, candidate_path: str, output: str | None
) -> dict[str, Any]:
    path = Path(candidate_path)
    candidate = load_region_sw009_live_apply_candidate(path)
    return compile_region_sw009_live_apply_candidate_receipt(
        candidate=candidate,
        candidate_path=path,
        output_path=Path(output) if output else None,
    )


def handle_region_sw009_live_bundle_template(
    *, input_path: str, bundle_id: str, output: str
) -> dict[str, Any]:
    region = load_region_declaration(Path(input_path))
    value = compile_live_operation_bundle_template(region=region, bundle_id=bundle_id)
    destination = write_live_artifact(Path(output), value, label="live operation draft")
    return {
        "schema_version": "typed-region-live-operation-draft-template-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "draft_schema": value["schema_version"],
        "surface_alias": region.surface_alias,
        "region_id": region.region_id,
        "output_path": str(destination),
    }


def handle_region_sw009_live_bundle_compile(*, draft_path: str, output: str) -> dict[str, Any]:
    bundle = load_live_operation_draft(Path(draft_path))
    destination = write_live_artifact(Path(output), bundle, label="live operation bundle")
    return {
        "schema_version": "typed-region-live-operation-bundle-compile-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "bundle_id": bundle["bundle_id"],
        "bundle_digest": bundle["bundle_digest"],
        "operation_count": len(bundle["operations"]),
        "output_path": str(destination),
    }


def handle_region_sw009_live_authorization_create(
    *,
    gate_path: str,
    bundle_path: str,
    authorization_id: str,
    approved_by: str,
    approval_reference: str,
    confirmation: str,
    valid_minutes: int,
    output: str,
) -> dict[str, Any]:
    if confirmation != "APPROVE_LIVE_APPLY":
        raise ValueError("live authorization confirmation is invalid")
    gate = load_live_apply_gate(Path(gate_path))
    bundle = load_live_operation_bundle(Path(bundle_path))
    approved_at = datetime.now(UTC).replace(microsecond=0)
    value = compile_live_authorization(
        gate_receipt=gate,
        operation_bundle=bundle,
        approved_by=approved_by,
        approval_reference=approval_reference,
        confirmation=confirmation,
        approved_at=approved_at,
        expires_at=approved_at + timedelta(minutes=valid_minutes),
        authorization_id=authorization_id,
    )
    destination = write_live_artifact(Path(output), value, label="live authorization")
    return {
        "schema_version": "typed-region-live-authorization-create-receipt.v1",
        "ok": True,
        "mutation_attempted": False,
        "authorization_id": value["authorization_id"],
        "authorization_digest": value["authorization_digest"],
        "expires_at": value["expires_at"],
        "output_path": str(destination),
    }


def _compile_live_plan_from_paths(
    *, gate_path: str, bundle_path: str, authorization_path: str
) -> dict[str, Any]:
    return compile_live_apply_plan(
        gate_receipt=load_live_apply_gate(Path(gate_path)),
        operation_bundle=load_live_operation_bundle(Path(bundle_path)),
        authorization=load_live_authorization(Path(authorization_path)),
    )


def handle_region_sw009_live_plan(
    *, gate_path: str, bundle_path: str, authorization_path: str, output: str
) -> dict[str, Any]:
    plan = _compile_live_plan_from_paths(
        gate_path=gate_path,
        bundle_path=bundle_path,
        authorization_path=authorization_path,
    )
    return write_live_apply_plan(Path(output), plan)


def handle_region_sw009_live_apply(
    *,
    gate_path: str,
    bundle_path: str,
    authorization_path: str,
    plan_path: str,
    output: str,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    plan = _compile_live_plan_from_paths(
        gate_path=gate_path,
        bundle_path=bundle_path,
        authorization_path=authorization_path,
    )
    reviewed_plan = load_live_apply_plan(Path(plan_path))
    if reviewed_plan != plan:
        raise ValueError("reviewed live plan no longer matches source inputs")
    kill_switch_path = active.settings.state_root / "LIVE_APPLY_DISABLED"
    if kill_switch_status(kill_switch_path)["enabled"]:
        raise ValueError("live apply kill switch is enabled")
    live_artifact_destination(Path(output), label="live transaction receipt")
    live_tools = asyncio.run(active.tools()).to_dict()
    provider = MiroManagedRegionProvider(active.settings, active.storage, cached_tools=live_tools)
    root = active.settings.state_root / "transactions"
    return asyncio.run(
        execute_live_apply(
            plan=plan,
            provider=provider,
            journal_root=root,
            kill_switch_path=kill_switch_path,
            output_path=Path(output),
        )
    )


def handle_region_sw009_live_restore(
    *,
    transaction_receipt: str,
    output: str,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    load_live_transaction_receipt(Path(transaction_receipt))
    live_artifact_destination(Path(output), label="live restore receipt")
    live_tools = asyncio.run(active.tools()).to_dict()
    provider = MiroManagedRegionProvider(active.settings, active.storage, cached_tools=live_tools)
    return asyncio.run(
        restore_live_apply(
            transaction_receipt_path=Path(transaction_receipt),
            provider=provider,
            output_path=Path(output),
        )
    )


def handle_region_sw009_kill_switch(
    *,
    action: str,
    reason: str | None,
    confirmation: str | None,
    client: MiroMCPClient | None = None,
) -> dict[str, Any]:
    active = client or MiroMCPClient()
    path = active.settings.state_root / "LIVE_APPLY_DISABLED"
    if action == "status":
        return kill_switch_status(path)
    if action == "enable":
        if not reason:
            raise ValueError("kill switch enable requires --reason")
        return enable_kill_switch(path, reason=reason)
    if action == "disable":
        return disable_kill_switch(path, confirmation=confirmation or "")
    raise ValueError("unknown kill switch action")


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
