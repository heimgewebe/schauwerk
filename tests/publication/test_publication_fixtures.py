from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from schauwerk.publication.model import (
    compile_preview,
    digest_mapping,
    load_declaration,
)
from schauwerk.publication.store import (
    publication_status,
    release_publication,
    withdraw_publication,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/operators/evidence/sw013-schaufenster-20260711"
HARDENING_EVIDENCE = ROOT / "docs/operators/evidence/infrastructure-hardening-20260904"
CODEQL_TRIAGE_EVIDENCE = ROOT / "docs/operators/evidence/codeql-residual-triage-20260904"
MIRO_OAUTH_EVIDENCE = ROOT / "docs/operators/evidence/miro-oauth-refresh-hardening-20260905"
SCHAUBILD_CUTOVER_EVIDENCE = ROOT / "docs/operators/evidence/schaubild-native-cutover-20260918"
SCHAUBILD_RUNTIME_EVIDENCE = ROOT / "docs/operators/evidence/schaubild-native-runtime-20260918"
SCHAUBILD_DRAWIO_NATIVE_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-drawio-native-first-20260920"
)
SCHAUBILD_NATIVE_EDITOR_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-native-editor-20260922"
)
SCHAUBILD_NATIVE_DRAFT_RESTORE_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-native-draft-restore-20260929"
)
SCHAUBILD_PRODUCT_UI_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-product-ui-20260929"
)
SCHAUBILD_PRODUCT_UI_REVIEW_FIX_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-product-ui-review-fixes-20260930"
)
SCHAUBILD_PRODUCT_UI_FINAL_FIX_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-product-ui-final-fixes-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-json-canvas-text-fit-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-json-canvas-text-fit-final-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_ZERO_ADVANCE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-zero-advance-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_COMBINING_SPACE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-combining-space-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_FALLBACK_CARRY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-fallback-carry-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDEPENDENT_REVIEW_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-independent-review-20260930"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_WIDE_LETTERS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-wide-letters-20260930"
)
SOURCE = ROOT / "docs/operators/evidence/sw012-buehne-20260711/technical/public"


def _json(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def _tree_fingerprint(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat(follow_symlinks=False).st_mode,
            path.stat(follow_symlinks=False).st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _make_store_removable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            continue
        mode = 0o700 if path.is_dir() else 0o600
        path.chmod(mode)
    root.chmod(0o700)


def test_sw013_evidence_is_schema_valid_and_reproducible(tmp_path: Path) -> None:
    schema = json.loads(
        (ROOT / "schemas/publication-boundary.v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    declaration = load_declaration(EVIDENCE / "declaration.json")
    preview, _ = compile_preview(declaration, SOURCE)
    assert preview == _json("preview.json")
    for name in (
        "declaration.json",
        "preview.json",
        "object-manifest.json",
        "active-link.json",
        "withdrawn-link.json",
    ):
        validator.validate(_json(name))

    acceptance = _json("acceptance-receipt.json")
    assert acceptance["acceptance_digest"] == digest_mapping(acceptance, "acceptance_digest")
    for name, record in acceptance["artifacts"].items():
        payload = (EVIDENCE / name).read_bytes()
        assert len(payload) == record["bytes"]
        assert hashlib.sha256(payload).hexdigest() == record["sha256"]
    for name, expected in acceptance["source_file_sha256"].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected
    expected_implementation_files = {
        "README.md",
        "docs/architecture/schauwerk.md",
        "docs/index.md",
        "docs/operators/evidence/sw013-schaufenster-20260711/README.md",
        "docs/publications/schaufenster-v1.md",
        "docs/roadmap.md",
        "registry/publications.yaml",
        "schemas/publication-boundary.v1.schema.json",
        "src/schauwerk/cli_handlers.py",
        "src/schauwerk/cli_parser.py",
        "src/schauwerk/publication/__init__.py",
        "src/schauwerk/publication/model.py",
        "src/schauwerk/publication/server.py",
        "src/schauwerk/publication/store.py",
        "src/schauwerk/runner.py",
        "tests/publication/test_publication_boundary.py",
        "tests/publication/test_publication_cli.py",
        "tests/publication/test_publication_fixtures.py",
    }
    assert set(acceptance["implementation_file_sha256"]) == expected_implementation_files
    extension_points = {
        "README.md",
        "docs/architecture/schauwerk.md",
        "docs/index.md",
        "docs/roadmap.md",
        "src/schauwerk/cli_handlers.py",
        "src/schauwerk/cli_parser.py",
        "src/schauwerk/runner.py",
        "src/schauwerk/publication/server.py",
        "src/schauwerk/publication/store.py",
        "tests/publication/test_publication_boundary.py",
        "tests/publication/test_publication_fixtures.py",
    }
    for name, expected in acceptance["implementation_file_sha256"].items():
        assert len(expected) == 64
        assert (ROOT / name).is_file()
        if name not in extension_points:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(
        value is True
        for key, value in acceptance["checks"].items()
        if key not in {"provider_mutation_attempted", "productive_publication_attempted"}
    )
    assert acceptance["checks"]["provider_mutation_attempted"] is False
    assert acceptance["checks"]["productive_publication_attempted"] is False

    store = tmp_path / "store"
    try:
        release = release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
        assert release == _json("release-receipt.json")
        assert _json("object-manifest.json") == json.loads(
            (store / "objects/grabowski-operational-brief/1.0.0/publication.json").read_text(
                encoding="utf-8"
            )
        )
        assert _json("active-link.json") == json.loads(
            (store / "links/grabowski-brief.json").read_text(encoding="utf-8")
        )

        before_status = _tree_fingerprint(store)
        assert publication_status(store, "grabowski-brief", now="2026-07-12T00:00:00Z") == _json(
            "active-status.json"
        )
        assert publication_status(store, "grabowski-brief", now="2026-08-01T00:00:00Z") == _json(
            "expired-status.json"
        )
        assert _tree_fingerprint(store) == before_status

        withdrawal = withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest=release["link_digest"],
            reason="Acceptance lifecycle withdrawal",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
        assert withdrawal == _json("withdrawal-receipt.json")
        assert _json("withdrawn-link.json") == json.loads(
            (store / "links/grabowski-brief.json").read_text(encoding="utf-8")
        )
        before_withdrawn_status = _tree_fingerprint(store)
        assert publication_status(store, "grabowski-brief", now="2026-07-14T00:00:00Z") == _json(
            "withdrawn-status.json"
        )
        assert _tree_fingerprint(store) == before_withdrawn_status
    finally:
        _make_store_removable(store)


def test_registry_keeps_sw013_acceptance_publication_in_draft() -> None:
    registry = yaml.safe_load((ROOT / "registry/publications.yaml").read_text(encoding="utf-8"))
    publication = next(
        item
        for item in registry["publications"]
        if item["id"] == "grabowski.operator-overview.preview"
    )
    assert publication == {
        "id": "grabowski.operator-overview.preview",
        "view_id": "grabowski.operator-overview",
        "status": "draft",
        "audience": "operator",
        "artifact_path": ("docs/operators/evidence/sw013-schaufenster-20260711/declaration.json"),
        "source_revision": "2026-07-10-fixture",
        "expires_at": "2026-08-01T00:00:00Z",
    }


def test_immutable_fixture_modes_are_read_only_after_release(tmp_path: Path) -> None:
    declaration = load_declaration(EVIDENCE / "declaration.json")
    preview = _json("preview.json")
    store = tmp_path / "store"
    try:
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
        object_root = store / "objects/grabowski-operational-brief/1.0.0"
        assert stat.S_IMODE(object_root.stat().st_mode) == 0o555
        assert stat.S_IMODE((object_root / "bundle").stat().st_mode) == 0o555
        for path in object_root.rglob("*"):
            if path.is_file():
                assert stat.S_IMODE(path.stat().st_mode) == 0o444
    finally:
        _make_store_removable(store)


def test_infrastructure_hardening_acceptance_and_successor_bind_security_revisions() -> None:
    receipt = json.loads(
        (HARDENING_EVIDENCE / "acceptance-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["schema_version"] == "schauwerk-infrastructure-hardening-acceptance.v1"
    assert receipt["acceptance_digest"] == digest_mapping(receipt, "acceptance_digest")
    assert receipt["parent_evidence"] == {
        "acceptance_digest": "88628daaff65b9b7956d03204ca106dd8e2b41990cc47eab8e9923825141ba75",
        "path": "docs/operators/evidence/sw013-schaufenster-20260711/acceptance-receipt.json",
    }
    expected_files = {
        ".github/workflows/validate.yml",
        "src/schauwerk/operator/receipts.py",
        "src/schauwerk/publication/server.py",
        "src/schauwerk/publication/store.py",
        "src/schauwerk/runner.py",
        "src/schauwerk/surfaces/miro/credentials.py",
        "tests/miro/test_credentials.py",
        "tests/operator/test_regions.py",
        "tests/publication/test_publication_boundary.py",
        "tests/test_runner_output_security.py",
        "tests/test_validate_workflow_security.py",
        "tests/visual/test_standalone_editor.py",
    }
    assert set(receipt["implementation_file_sha256"]) == expected_files

    successor = json.loads((CODEQL_TRIAGE_EVIDENCE / "triage.json").read_text(encoding="utf-8"))
    assert successor["schema_version"] == "schauwerk-codeql-residual-triage.v1"
    assert successor["parent_evidence"] == {
        "acceptance_digest": receipt["acceptance_digest"],
        "file_sha256": hashlib.sha256(
            (HARDENING_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/infrastructure-hardening-20260904/acceptance-receipt.json",
    }
    successor_body = dict(successor)
    successor_digest = successor_body.pop("triage_digest")
    assert (
        hashlib.sha256(
            json.dumps(
                successor_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        == successor_digest
    )

    schaubild_successor = json.loads(
        (SCHAUBILD_CUTOVER_EVIDENCE / "acceptance-receipt.json").read_text(encoding="utf-8")
    )
    assert schaubild_successor["schema_version"] == "schauwerk-schaubild-native-cutover.v1"
    assert schaubild_successor["parent_evidence"] == {
        "acceptance_digest": receipt["acceptance_digest"],
        "file_sha256": hashlib.sha256(
            (HARDENING_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/infrastructure-hardening-20260904/acceptance-receipt.json",
        "schema_version": receipt["schema_version"],
    }
    assert schaubild_successor["evidence_digest"] == digest_mapping(
        schaubild_successor, "evidence_digest"
    )
    runtime_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "src/schauwerk/visual/standalone_editor.py",
        "tests/visual/test_standalone_editor.py",
    }
    for name, expected in schaubild_successor["source_bindings"].items():
        if name not in runtime_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected

    runtime_successor = json.loads(
        (SCHAUBILD_RUNTIME_EVIDENCE / "acceptance-receipt.json").read_text(encoding="utf-8")
    )
    assert runtime_successor["schema_version"] == "schauwerk-schaubild-native-runtime.v1"
    assert runtime_successor["parent_evidence"] == {
        "evidence_digest": schaubild_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_CUTOVER_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/schaubild-native-cutover-20260918/acceptance-receipt.json",
        "schema_version": schaubild_successor["schema_version"],
    }
    assert runtime_successor["evidence_digest"] == digest_mapping(
        runtime_successor, "evidence_digest"
    )
    editor_superseded_files = {
        "Dockerfile",
        "Makefile",
        "scripts/run_browser_smoke.py",
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "src/schauwerk/visual/native_diagram.py",
        "src/schauwerk/visual/drawio_import.py",
        "src/schauwerk/visual/json_fidelity.py",
        "src/schauwerk/visual/native_document.py",
        "src/schauwerk/visual/native_viewer.py",
        "src/schauwerk/visual/standalone_editor.py",
        "tests/visual/test_native_canvas_editor.py",
        "tests/visual/test_native_document.py",
        "tests/visual/test_drawio_import.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor.py",
    }
    drawio_native_superseded_files = {
        "Dockerfile",
        "docs/plans/standalone-diagram-editor-spike-v1.md",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "src/schauwerk/visual/standalone_editor.py",
        "tests/visual/test_standalone_editor.py",
    } | editor_superseded_files
    for name, expected in runtime_successor["source_bindings"].items():
        if name not in drawio_native_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected

    drawio_successor = json.loads(
        (SCHAUBILD_DRAWIO_NATIVE_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert drawio_successor["schema_version"] == "schauwerk-schaubild-drawio-native-first.v1"
    assert drawio_successor["parent_evidence"] == {
        "evidence_digest": runtime_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_RUNTIME_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/schaubild-native-runtime-20260918/acceptance-receipt.json",
        "schema_version": runtime_successor["schema_version"],
    }
    assert drawio_successor["evidence_digest"] == digest_mapping(
        drawio_successor, "evidence_digest"
    )
    for name, expected in drawio_successor["source_bindings"].items():
        if name not in editor_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected

    draft_restore_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    product_ui_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "src/schauwerk/visual/standalone_editor.py",
        "tests/visual/test_native_canvas_editor.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_standalone_editor.py",
    }
    product_ui_review_fix_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    final_ui_fix_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor_font_controls.py",
    }
    json_canvas_text_fit_superseded_files = {
        "Dockerfile",
        "src/schauwerk/visual/grapheme.py",
        "src/schauwerk/visual/native_diagram.py",
        "src/schauwerk/visual/native_viewer.py",
        "src/schauwerk/visual/standalone_editor.py",
        "tests/visual/test_native_diagram.py",
        "tests/visual/test_native_document.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_standalone_editor.py",
    }
    json_canvas_text_fit_final_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_zero_advance_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_combining_space_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_fallback_carry_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_independent_review_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_wide_letters_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    editor_successor = json.loads(
        (SCHAUBILD_NATIVE_EDITOR_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert editor_successor["schema_version"] == "schauwerk-schaubild-native-editor.v1"
    assert editor_successor["functional_head"] == "192ab30e80d20cabc18c542bd132d8c318905b38"
    assert editor_successor["parent_evidence"] == {
        "evidence_digest": drawio_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_DRAWIO_NATIVE_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-drawio-native-first-20260920/acceptance-receipt.json"
        ),
        "schema_version": drawio_successor["schema_version"],
    }
    assert editor_successor["evidence_digest"] == digest_mapping(
        editor_successor, "evidence_digest"
    )
    assert set(editor_successor["source_bindings"]) == editor_superseded_files
    for name, expected in editor_successor["source_bindings"].items():
        if name not in (
            draft_restore_superseded_files
            | product_ui_superseded_files
            | final_ui_fix_superseded_files
            | json_canvas_text_fit_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert editor_successor["checks"]["browser_smoke_passed_count"] == 7
    assert editor_successor["checks"]["clipped_edge_labels_do_not_block_node_drag"] is True
    assert (
        editor_successor["checks"]["json_canvas_core_geometry_requires_integer_numbers"]
        is True
    )
    assert (
        editor_successor["checks"]["failed_superseding_native_rebuild_preserves_active_bundle"]
        is True
    )
    assert (
        editor_successor["checks"][
            "native_renderer_failure_is_retryable_service_unavailable"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "exclusive_supersede_projects_global_entry_and_byte_capacity"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "shared_supersede_retains_global_entry_and_byte_capacity_charge"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["pre_acceptance_successor_binding_failure_reproduced"]
        is True
    )
    assert (
        editor_successor["checks"][
            "browser_startup_flake_cleared_by_isolated_and_official_smoke"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["empty_canvas_browser_state_republish_deterministic"]
        is True
    )
    assert (
        editor_successor["checks"]["hosted_canvas_browser_readiness_deterministic"]
        is True
    )
    assert (
        editor_successor["checks"][
            "native_svg_export_prefers_loaded_frame_after_bundle_expiry"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "hosted_viewer_waits_for_script_ready_before_state_republish"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "canvas_limit_browser_state_republish_deterministic"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "expired_native_client_lease_drops_stale_consumer_before_reacquire"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["synchronized_svg_preserves_source_digest"]
        is True
    )
    assert (
        editor_successor["checks"]["live_modified_canvas_svg_strips_stale_digest"]
        is True
    )
    assert (
        editor_successor["checks"][
            "supersede_projection_carries_through_prune_capacity"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "prune_revalidates_supersede_projection_after_foreign_repin"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["supersede_projection_reaches_post_build_prune"]
        is True
    )
    assert (
        editor_successor["checks"][
            "successful_supersede_prunes_released_projection_after_delivery"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "canonical_canvas_snapshot_ignores_object_key_order"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "embedded_canvas_source_limits_rejected_before_normalization"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_unsafe_integers_rejected_before_roundtrip"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_numeric_tokens_preserve_javascript_roundtrip_fidelity"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "direct_native_api_rejects_lossy_canvas_numeric_tokens"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "native_canvas_drag_coordinates_stay_within_document_budget"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_duplicate_members_rejected_before_authority"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_duplicate_member_keys_compare_decoded_object_locally"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "native_viewer_cli_rejects_lossy_json_before_document_authority"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "shared_json_fidelity_guards_preserve_standalone_contract"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "docker_runtime_closure_includes_shared_json_fidelity"
        ]
        is True
    )
    assert editor_successor["checks"]["ci_equivalent_validate_passed"] is True
    assert (
        editor_successor["checks"][
            "native_geometry_return_annotations_match_runtime_shapes"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["canvas_hex_colors_require_canonical_rrggbb"]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_native_primary_with_lazy_legacy_rejection_fallback"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "permanent_native_rejection_rerenders_last_live_valid_state"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "native_canvas_document_change_persists_restoreable_native_draft"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "supersede_release_assertion_waits_for_post_delivery_cleanup"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "transient_native_rebuild_candidate_persists_restoreable_draft"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["same_ip_native_consumers_release_independently"]
        is True
    )
    assert (
        editor_successor["checks"][
            "normalized_json_canvas_overflow_rejected_before_renderer_spawn"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_product_counts_rejected_before_expensive_conversion"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_product_counts_include_omitted_optional_arrays"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "terminal_supersede_history_reuses_capacity_without_raising_limit"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "undelivered_cache_hit_releases_consumer_acquisition"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["native_recovery_browser_waits_for_viewer_ready_signal"]
        is True
    )
    assert (
        editor_successor["checks"]["canvas_node_labels_clipped_to_node_bounds"] is True
    )
    assert editor_successor["checks"]["edge_operations_cancel_on_escape"] is True
    assert editor_successor["checks"]["canvas_self_loops_honor_explicit_sides"] is True
    assert (
        editor_successor["checks"]["native_rebuild_preserves_active_frame_until_success"]
        is True
    )
    assert editor_successor["checks"]["stale_canvas_svg_export_fails_closed"] is True
    assert (
        editor_successor["checks"]["document_node_bounds_ignore_clipped_label_bbox"]
        is True
    )
    assert (
        editor_successor["checks"]["failed_native_rebuild_preserves_latest_state_with_explicit_retry"]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_group_backgrounds_rejected_instead_of_silently_dropped"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_markdown_display_normalized_without_roundtrip_loss"
        ]
        is True
    )
    assert editor_successor["checks"]["drawio_xml_entity_expansion_hardened"] is True
    assert editor_successor["checks"]["drawio_xml_namespace_shape_preserved"] is True
    assert (
        editor_successor["checks"]["native_product_limits_block_mutation_before_rebuild"]
        is True
    )
    assert (
        editor_successor["checks"]["permanent_native_rebuild_rejection_restores_last_valid_state"]
        is True
    )
    assert (
        editor_successor["checks"]["extension_only_json_canvas_detected_and_preserved"]
        is True
    )
    assert (
        editor_successor["checks"][
            "extension_only_json_canvas_requires_explicit_canvas_context"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["canvas_ids_reject_xml_attribute_normalized_whitespace"]
        is True
    )
    assert (
        editor_successor["checks"][
            "non_document_live_svg_strips_canonical_input_digest"
        ]
        is True
    )
    assert (
        editor_successor["checks"][
            "json_canvas_fidelity_rejections_preserve_specific_browser_reason"
        ]
        is True
    )
    assert (
        editor_successor["checks"]["native_cutover_boundary_declares_json_canvas"]
        is True
    )

    draft_restore_successor = json.loads(
        (SCHAUBILD_NATIVE_DRAFT_RESTORE_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        draft_restore_successor["schema_version"]
        == "schauwerk-schaubild-native-draft-restore.v1"
    )
    assert (
        draft_restore_successor["functional_head"]
        == "1c2c43086c063a349637f61b580c09a29775543b"
    )
    assert draft_restore_successor["parent_evidence"] == {
        "evidence_digest": editor_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_NATIVE_EDITOR_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-native-editor-20260922/acceptance-receipt.json"
        ),
        "schema_version": editor_successor["schema_version"],
    }
    assert draft_restore_successor["evidence_digest"] == digest_mapping(
        draft_restore_successor, "evidence_digest"
    )
    assert set(draft_restore_successor["source_bindings"]) == draft_restore_superseded_files
    for name, expected in draft_restore_successor["source_bindings"].items():
        if name not in (
            product_ui_superseded_files | json_canvas_text_fit_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert draft_restore_successor["checks"] == {
        "focused_restore_tests_passed": True,
        "functional_head_independent_opus_review_passed": True,
        "historical_acceptance_left_immutable": True,
        "native_canvas_document_change_persists_restoreable_native_draft": True,
        "native_canvas_draft_restore_dispatches_document_to_native_editor": True,
        "ruff_passed": True,
        "standalone_editor_full_module_passed": True,
    }
    assert draft_restore_successor["check_evidence"] == {
        "focused_restore_tests_passed": {
            "argv_sha256": (
                "d22d40c9d980ed5ca0a10d49de65dc4f88ba9e3c10d92f9f2314561ba1f67d2f"
            ),
            "execution_kind": "source_bound_python3_pytest",
            "finalization_receipt_sha256": (
                "943a387f64490390017db033732ce56b1a737152ac9fc0a2638daf77da3caa67"
            ),
            "job_unit": "grabowski-job-dd920e2b4b11",
            "result": "succeeded",
            "source_bindings": draft_restore_successor["source_bindings"],
            "validation_head": "684f386eda27fef12ae6a5010aa78823d328f974",
        },
        "standalone_editor_full_module_passed": {
            "argv_sha256": (
                "f5edf0ee1f16c0ae60a81a93801f427fb8a34e84263b55d3ffe62d1c875885f4"
            ),
            "execution_kind": "direct_python3_pytest",
            "finalization_receipt_sha256": (
                "55b2571281463d4a423ce5468389a18a0395289df76d8d010fee984381223a2c"
            ),
            "functional_head": "1c2c43086c063a349637f61b580c09a29775543b",
            "job_unit": "grabowski-job-094eccad77a0",
            "result": "succeeded",
        },
        "ruff_passed": {
            "argv_sha256": (
                "3922639b99666924940ea6bc51c9ffcf32f887816bbb42a43dac528493266d75"
            ),
            "execution_kind": "direct_python3_ruff",
            "finalization_receipt_sha256": (
                "a9ea5c976f475f47963fd8a21edcf7c92b46b001b88d8dc44bff4b75ff25fcf6"
            ),
            "job_unit": "grabowski-job-38a669aca771",
            "result": "succeeded",
            "source_bindings": draft_restore_successor["source_bindings"],
        },
        "functional_head_independent_opus_review_passed": {
            "reviewed_head": "1c2c43086c063a349637f61b580c09a29775543b",
            "reviewed_diff_sha256": (
                "8ec87f60bd2391efd0d70e3b64ab9925201062925dcb179affa8c9c27e78ffcb"
            ),
            "role_receipt_file_sha256": (
                "c4d27dd9b8cc42cbc64b805f8de5c28525c1bc1315a4b6308e1439dff8f60177"
            ),
            "role_receipt_sha256": (
                "96c09fff09f54accaad608962c3db032c16c1b5181cc35afbc8af7a48901a41d"
            ),
            "verdict": "PASS",
        },
    }
    assert (
        "supported local browser-smoke execution; the direct pytest/Ruff jobs "
        "recorded above used the local python3 module path, while the repository "
        "browser-smoke path selected python3.11 without pytest on this host"
        in draft_restore_successor["does_not_establish"]
    )
    assert (
        "independent Opus approval of this successor evidence revision or any "
        "later head; the recorded PASS is bound only to functional_head "
        "1c2c43086c063a349637f61b580c09a29775543b"
        in draft_restore_successor["does_not_establish"]
    )

    product_ui_successor = json.loads(
        (SCHAUBILD_PRODUCT_UI_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        product_ui_successor["schema_version"]
        == "schauwerk-schaubild-product-ui.v1"
    )
    assert (
        product_ui_successor["functional_head"]
        == "f7f0cd956386bc82202fd7f9633bb0b11f68a343"
    )
    assert product_ui_successor["parent_evidence"] == {
        "evidence_digest": draft_restore_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_NATIVE_DRAFT_RESTORE_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-native-draft-restore-20260929/acceptance-receipt.json"
        ),
        "schema_version": draft_restore_successor["schema_version"],
    }
    assert product_ui_successor["evidence_digest"] == digest_mapping(
        product_ui_successor, "evidence_digest"
    )
    expected_product_ui_bindings = product_ui_superseded_files | {
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    assert set(product_ui_successor["source_bindings"]) == expected_product_ui_bindings
    for name, expected in product_ui_successor["source_bindings"].items():
        if name not in (
            product_ui_review_fix_superseded_files
            | final_ui_fix_superseded_files
            | json_canvas_text_fit_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert product_ui_successor["checks"] == {
        "historical_acceptance_left_immutable": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "desktop_start_visual_readback_passed": True,
        "mobile_start_visual_readback_passed": True,
        "desktop_native_workspace_visual_readback_passed": True,
        "mobile_native_workspace_cold_start_visual_readback_passed": True,
        "critical_diff_self_review_passed": True,
    }
    self_review_evidence = product_ui_successor["check_evidence"][
        "critical_diff_self_review_passed"
    ]
    assert self_review_evidence == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-product-ui-20260929/grabowski-self-review.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_PRODUCT_UI_EVIDENCE / "grabowski-self-review.json"
            ).read_bytes()
        ).hexdigest(),
        "review_mode": "critical_diff_review",
        "verdict": "PASS",
        "reviewed_head": "f7f0cd956386bc82202fd7f9633bb0b11f68a343",
        "reviewed_diff_sha256": (
            "1dfc35169c372161cd088ba7862d0ffc14f4a6cff13e8d46d1623f39327ecd0c"
        ),
    }
    assert (
        "independent review of the Product-UI revision"
        in product_ui_successor["does_not_establish"]
    )
    assert (
        "user visual acceptance of the Product-UI revision"
        in product_ui_successor["does_not_establish"]
    )

    product_ui_review_fix = json.loads(
        (SCHAUBILD_PRODUCT_UI_REVIEW_FIX_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        product_ui_review_fix["schema_version"]
        == "schauwerk-schaubild-product-ui-review-fixes.v1"
    )
    assert (
        product_ui_review_fix["functional_head"]
        == "13c1324ba0ed9aab75a0b5a314a620442b961f01"
    )
    assert product_ui_review_fix["parent_evidence"] == {
        "evidence_digest": product_ui_successor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_PRODUCT_UI_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/schaubild-product-ui-20260929/acceptance-receipt.json",
        "schema_version": product_ui_successor["schema_version"],
    }
    assert product_ui_review_fix["evidence_digest"] == digest_mapping(
        product_ui_review_fix, "evidence_digest"
    )
    expected_review_fix_bindings = product_ui_review_fix_superseded_files | {
        "tests/visual/test_standalone_editor_font_controls.py",
    }
    assert set(product_ui_review_fix["source_bindings"]) == expected_review_fix_bindings
    for name, expected in product_ui_review_fix["source_bindings"].items():
        if name not in (
            final_ui_fix_superseded_files | json_canvas_text_fit_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert product_ui_review_fix["checks"] == {
        "historical_product_ui_acceptance_left_immutable": True,
        "unsupported_plain_text_claim_removed": True,
        "focus_mode_exit_visible_and_clickable": True,
        "focused_tests_passed": True,
        "exact_head_browser_readback_passed": True,
        "critical_diff_self_review_passed": True,
    }
    review_fix_self_review = product_ui_review_fix["check_evidence"][
        "critical_diff_self_review_passed"
    ]
    assert review_fix_self_review == {
        "path": (
            "docs/operators/evidence/schaubild-product-ui-review-fixes-20260930/"
            "grabowski-self-review.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_PRODUCT_UI_REVIEW_FIX_EVIDENCE / "grabowski-self-review.json"
            ).read_bytes()
        ).hexdigest(),
        "review_mode": "critical_diff_review",
        "verdict": "PASS",
        "reviewed_head": "13c1324ba0ed9aab75a0b5a314a620442b961f01",
        "reviewed_diff_sha256": (
            "7d1e8f7d835a475163e25c9c290e6e849c9d29b6ed3d62e1a88d8c3e2ae0182c"
        ),
    }
    assert (
        "independent review of the review-fix revision"
        in product_ui_review_fix["does_not_establish"]
    )
    assert (
        "Codex settlement on the later final PR head"
        in product_ui_review_fix["does_not_establish"]
    )

    final_ui_fix = json.loads(
        (SCHAUBILD_PRODUCT_UI_FINAL_FIX_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        final_ui_fix["schema_version"]
        == "schauwerk-schaubild-product-ui-final-fixes.v1"
    )
    assert (
        final_ui_fix["functional_head"]
        == "903e68c7ba9ed6885578a291b8abab5634dcd78f"
    )
    assert final_ui_fix["parent_evidence"] == {
        "evidence_digest": product_ui_review_fix["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_PRODUCT_UI_REVIEW_FIX_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-product-ui-review-fixes-20260930/acceptance-receipt.json"
        ),
        "schema_version": product_ui_review_fix["schema_version"],
    }
    assert final_ui_fix["evidence_digest"] == digest_mapping(
        final_ui_fix, "evidence_digest"
    )
    assert set(final_ui_fix["source_bindings"]) == final_ui_fix_superseded_files
    for name, expected in final_ui_fix["source_bindings"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert final_ui_fix["checks"] == {
        "historical_review_fix_acceptance_left_immutable": True,
        "inactive_edit_controls_hidden_outside_hosted_editing": True,
        "hosted_edit_controls_visible_and_usable": True,
        "focus_controls_clear_of_editor_stage": True,
        "focus_mode_exit_visible_and_clickable": True,
        "supported_formats_product_copy_verified": True,
        "focused_tests_passed": True,
        "browser_smoke_passed": True,
        "final_visual_readback_passed": True,
    }
    browser_evidence = final_ui_fix["check_evidence"]["browser_smoke_passed"]
    assert browser_evidence["job_unit"] == "grabowski-job-58a3b2970edb"
    assert browser_evidence["finalization_receipt_sha256"] == (
        "4c87a25a7a9c031cd8f133378c2e28629c038cca2a879a8fb1c3212d3e5f3547"
    )
    assert browser_evidence["passed_count"] == 7
    visual_readback = final_ui_fix["check_evidence"]["final_visual_readback_passed"]
    assert visual_readback["functional_head"] == final_ui_fix["functional_head"]
    assert visual_readback["focus_contract"] == {
        "controls_max_bottom_px": 56,
        "editor_frame_top_px": 60,
        "editor_stage_padding_top_px": 60,
        "exit_returned_to_normal_workspace": True,
        "no_overlap": True,
    }
    assert visual_readback["product_copy"] == {
        "formats": ["Mermaid", "JSON Canvas", "draw.io"],
        "plain_text_advertised": False,
    }
    assert visual_readback["screenshots_sha256"] == {
        "desktop_focus": (
            "c7f7d4d45c8f77a67b62b8489d6c7d3a8cf94f2b7a63f0872a90bda3fecbb2ad"
        ),
        "desktop_start": (
            "c69b980dc49c189b0c503f91e829e51a0cfdfb483076ad3720de9c7edf10cf88"
        ),
        "desktop_workspace": (
            "de24472784cc4c2bc66b24d0191467eaff147f81a31e959c567ad7989c2129a4"
        ),
        "mobile_start": (
            "a92e386faa9e332c5bdaa5886b5b27504134e8f458fd3331f3a149fb8ed5cb2d"
        ),
        "mobile_workspace_cold_start": (
            "0ecd534e0899759bf71e5c70b9b726fb40ddef413e762410b92a5f4ced86576d"
        ),
    }
    assert (
        "user visual acceptance of the final UI-fix revision"
        in final_ui_fix["does_not_establish"]
    )
    assert (
        "Codex settlement on the later final PR head"
        in final_ui_fix["does_not_establish"]
    )

    json_canvas_text_fit = json.loads(
        (SCHAUBILD_JSON_CANVAS_TEXT_FIT_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        json_canvas_text_fit["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit.v1"
    )
    assert (
        json_canvas_text_fit["functional_head"]
        == "0a1eb7e5ca705d378fbdd1a3e86e8caf7095371c"
    )
    assert (
        json_canvas_text_fit["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit["parent_evidence"] == {
        "evidence_digest": final_ui_fix["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_PRODUCT_UI_FINAL_FIX_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-product-ui-final-fixes-20260930/acceptance-receipt.json"
        ),
        "schema_version": final_ui_fix["schema_version"],
    }
    assert json_canvas_text_fit["evidence_digest"] == digest_mapping(
        json_canvas_text_fit, "evidence_digest"
    )
    assert set(json_canvas_text_fit["source_bindings"]) == (
        json_canvas_text_fit_superseded_files
    )
    for name, expected in json_canvas_text_fit["source_bindings"].items():
        if name not in json_canvas_text_fit_final_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256(
        (SCHAUBILD_NATIVE_EDITOR_EVIDENCE / "acceptance-receipt.json").read_bytes()
    ).hexdigest() == "9cade3ab2edced27be114b8b7e773750dc33cd47d4d9fcad410a518bda832207"
    assert json_canvas_text_fit["checks"] == {
        "current_main_integrated": True,
        "historical_native_editor_receipt_restored_to_main": True,
        "collapsed_whitespace_cluster_cap_fixed": True,
        "explicit_line_breaks_preserved": True,
        "focused_whitespace_regressions_passed": True,
        "native_document_suite_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_case_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    assert json_canvas_text_fit["check_evidence"][
        "focused_whitespace_regressions_passed"
    ]["passed_count"] == 3
    assert json_canvas_text_fit["check_evidence"]["native_document_suite_passed"][
        "passed_count"
    ] == 154
    assert json_canvas_text_fit["check_evidence"]["browser_smoke_passed"][
        "passed_count"
    ] == 7
    case_readback = json_canvas_text_fit["check_evidence"][
        "exact_case_browser_readback_passed"
    ]
    assert case_readback["long_collapsible_whitespace_lines"] == [
        "abc",
        "defxxxxxx…",
    ]
    assert case_readback["single_space_equivalent_lines"] == [
        "abc",
        "defxxxxxx…",
    ]
    assert case_readback["explicit_multiline_lines"] == [
        "Zeile eins mit",
        "Text",
        "Zeile zwei",
        "bleibt sichtbar",
    ]
    assert case_readback["explicit_multiline_truncated"] is False
    assert (
        "user visual acceptance of the JSON Canvas text-fit revision"
        in json_canvas_text_fit["does_not_establish"]
    )
    assert (
        "current-head Codex settlement after the evidence commit"
        in json_canvas_text_fit["does_not_establish"]
    )

    json_canvas_text_fit_final = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_final["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-final.v1"
    )
    assert (
        json_canvas_text_fit_final["functional_head"]
        == "4f26a3a3bb5fd272aa7e20e135385c28d2f6e756"
    )
    assert (
        json_canvas_text_fit_final["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_final["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-20260930/acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit["schema_version"],
    }
    assert json_canvas_text_fit_final["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_final, "evidence_digest"
    )
    assert set(json_canvas_text_fit_final["source_bindings"]) == (
        json_canvas_text_fit_final_superseded_files
    )
    for name, expected in json_canvas_text_fit_final["source_bindings"].items():
        if name not in json_canvas_text_fit_zero_advance_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_final["checks"] == {
        "historical_text_fit_acceptance_left_immutable": True,
        "xml_forbidden_controls_normalized_before_bounded_grapheme_layout": True,
        "single_line_xml_normalization_preserves_work_cap": True,
        "latin_zwj_uses_base_letter_width": True,
        "shaping_script_zwj_width_preserved": True,
        "focused_xml_zwj_and_work_cap_tests_passed": True,
        "native_document_and_diagram_modules_passed": True,
        "ruff_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_case_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    assert json_canvas_text_fit_final["check_evidence"][
        "focused_xml_zwj_and_work_cap_tests_passed"
    ]["passed_count"] == 7
    assert json_canvas_text_fit_final["check_evidence"]["browser_smoke_passed"][
        "passed_count"
    ] == 7
    final_case_readback = json_canvas_text_fit_final["check_evidence"][
        "exact_case_browser_readback_passed"
    ]
    assert final_case_readback["xml_raw"] == {
        "lines": ["�́�́"],
        "truncated": False,
    }
    assert final_case_readback["xml_replacement"] == {
        "lines": ["�́�́"],
        "truncated": False,
    }
    assert final_case_readback["latin_zwj"]["truncated"] is False
    assert final_case_readback["shaping_script_zwj"]["truncated"] is False
    assert final_case_readback["all_text_boxes_within_node_bounds"] is True
    assert (
        "current-head Codex settlement after the later evidence commit"
        in json_canvas_text_fit_final["does_not_establish"]
    )

    json_canvas_text_fit_zero_advance = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_ZERO_ADVANCE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_zero_advance["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-zero-advance.v1"
    )
    assert (
        json_canvas_text_fit_zero_advance["functional_head"]
        == "c70431f7b88bb16246a9c51c7f45085675cdceb0"
    )
    assert (
        json_canvas_text_fit_zero_advance["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_zero_advance["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_final["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-final-20260930/acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_final["schema_version"],
    }
    assert json_canvas_text_fit_zero_advance["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_zero_advance, "evidence_digest"
    )
    assert set(json_canvas_text_fit_zero_advance["source_bindings"]) == (
        json_canvas_text_fit_zero_advance_superseded_files
    )
    for name, expected in json_canvas_text_fit_zero_advance["source_bindings"].items():
        if name not in json_canvas_text_fit_combining_space_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_zero_advance["checks"] == {
        "historical_final_text_fit_acceptance_left_immutable": True,
        "zero_advance_controls_excluded_from_geometry_probe_cap": True,
        "independent_grapheme_work_cap_preserved": True,
        "byte_work_cap_preserved": True,
        "focused_zero_advance_and_work_cap_tests_passed": True,
        "native_document_and_diagram_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_case_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    assert json_canvas_text_fit_zero_advance["check_evidence"][
        "focused_zero_advance_and_work_cap_tests_passed"
    ]["passed_count"] == 7
    assert json_canvas_text_fit_zero_advance["check_evidence"][
        "browser_smoke_passed"
    ]["passed_count"] == 7
    zero_advance_readback = json_canvas_text_fit_zero_advance["check_evidence"][
        "exact_case_browser_readback_passed"
    ]
    assert zero_advance_readback["visible_text"] == "abcdefghij"
    assert zero_advance_readback["zero_advance_control_count"] == 100
    assert zero_advance_readback["truncated"] is False
    assert zero_advance_readback["all_text_boxes_within_node_bounds"] is True
    assert (
        "current-head Codex settlement after the later evidence commit"
        in json_canvas_text_fit_zero_advance["does_not_establish"]
    )

    json_canvas_text_fit_combining_space = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_COMBINING_SPACE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_combining_space["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-combining-space.v1"
    )
    assert (
        json_canvas_text_fit_combining_space["functional_head"]
        == "fa04a9970466dec9403f814aa05139c6b2d09f63"
    )
    assert (
        json_canvas_text_fit_combining_space["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_combining_space["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_zero_advance["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_ZERO_ADVANCE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-zero-advance-20260930/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_zero_advance["schema_version"],
    }
    assert json_canvas_text_fit_combining_space["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_combining_space, "evidence_digest"
    )
    assert set(json_canvas_text_fit_combining_space["source_bindings"]) == (
        json_canvas_text_fit_combining_space_superseded_files
    )
    for name, expected in json_canvas_text_fit_combining_space[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_fallback_carry_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_combining_space["checks"] == {
        "historical_zero_advance_acceptance_left_immutable": True,
        "already_stripped_collapsible_edge_whitespace_normalized_before_grapheme_fit": True,
        "emitted_combining_mark_line_refit_to_geometry": True,
        "existing_grapheme_and_work_caps_preserved": True,
        "focused_combining_and_regression_tests_passed": True,
        "native_document_and_diagram_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_case_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    assert json_canvas_text_fit_combining_space["check_evidence"][
        "focused_combining_and_regression_tests_passed"
    ]["passed_count"] == 7
    assert json_canvas_text_fit_combining_space["check_evidence"][
        "browser_smoke_passed"
    ]["passed_count"] == 7
    combining_readback = json_canvas_text_fit_combining_space["check_evidence"][
        "exact_case_browser_readback_passed"
    ]
    assert combining_readback["source_label"] == " ́BBBB"
    assert combining_readback["rendered_label"] == "́BB…"
    assert combining_readback["truncated"] is True
    assert combining_readback["all_text_boxes_within_node_bounds"] is True
    assert (
        "current-head Codex settlement after the later evidence commit"
        in json_canvas_text_fit_combining_space["does_not_establish"]
    )

    json_canvas_text_fit_fallback_carry = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_FALLBACK_CARRY_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_fallback_carry["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-fallback-carry.v1"
    )
    assert (
        json_canvas_text_fit_fallback_carry["functional_head"]
        == "21ea3248e02f63a68b701624ad925e3fb90ac2a4"
    )
    assert (
        json_canvas_text_fit_fallback_carry["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_fallback_carry["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_combining_space["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_COMBINING_SPACE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-combining-space-20260930/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_combining_space["schema_version"],
    }
    assert json_canvas_text_fit_fallback_carry["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_fallback_carry, "evidence_digest"
    )
    assert set(json_canvas_text_fit_fallback_carry["source_bindings"]) == (
        json_canvas_text_fit_fallback_carry_superseded_files
    )
    for name, expected in json_canvas_text_fit_fallback_carry[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_independent_review_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_fallback_carry["checks"] == {
        "historical_combining_space_acceptance_left_immutable": True,
        "wide_fallback_punctuation_and_symbols_budgeted_conservatively": True,
        "fallback_width_calibration_uses_font_and_browser_measurements": True,
        "post_trim_wrapped_lines_refit_to_geometry": True,
        "internal_combining_space_carry_no_longer_silently_overflows": True,
        "existing_grapheme_and_work_caps_preserved": True,
        "focused_wide_and_carry_regressions_passed": True,
        "native_document_and_diagram_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_case_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    assert json_canvas_text_fit_fallback_carry["check_evidence"][
        "fallback_width_calibration_uses_font_and_browser_measurements"
    ]["calibrated_range_count"] == 50
    assert json_canvas_text_fit_fallback_carry["check_evidence"][
        "focused_wide_and_carry_regressions_passed"
    ]["passed_count"] == 10
    assert json_canvas_text_fit_fallback_carry["check_evidence"][
        "browser_smoke_passed"
    ]["passed_count"] == 7
    fallback_carry_readback = json_canvas_text_fit_fallback_carry["check_evidence"][
        "exact_case_browser_readback_passed"
    ]
    assert fallback_carry_readback["wide_fallback"]["rendered"] == "‰‰‰‰‰‰…"
    assert fallback_carry_readback["wide_fallback"]["truncated"] is True
    assert (
        fallback_carry_readback["wide_fallback"]["all_text_boxes_within_node_bounds"]
        is True
    )
    assert fallback_carry_readback["internal_carry"]["rendered"] == "éBBBB"
    assert fallback_carry_readback["internal_carry"]["truncated"] is False
    assert (
        fallback_carry_readback["internal_carry"]["all_text_boxes_within_node_bounds"]
        is True
    )
    assert (
        "current-head Codex settlement after the later evidence commit"
        in json_canvas_text_fit_fallback_carry["does_not_establish"]
    )

    json_canvas_text_fit_independent_review = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDEPENDENT_REVIEW_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_independent_review["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-independent-review.v1"
    )
    assert (
        json_canvas_text_fit_independent_review["functional_head"]
        == "aff9ff10032d49bf641e1726450cf9c3b51f3939"
    )
    assert (
        json_canvas_text_fit_independent_review["integrated_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_independent_review["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_fallback_carry["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_FALLBACK_CARRY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-fallback-carry-20260930/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_fallback_carry["schema_version"],
    }
    assert json_canvas_text_fit_independent_review["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_independent_review, "evidence_digest"
    )
    assert set(json_canvas_text_fit_independent_review["source_bindings"]) == (
        json_canvas_text_fit_independent_review_superseded_files
    )
    for name, expected in json_canvas_text_fit_independent_review[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_wide_letters_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    review_debt = json_canvas_text_fit_independent_review["review_debt"]
    assert review_debt["rejected_head"] == "a4ebdbf1d7757556843bc4fe62a86d79df2cbd55"
    assert review_debt["verdict"] == "REJECT_THIS_REVISION"
    assert review_debt["material_findings"] == 2
    assert review_debt["disposition"] == "remediated_in_new_functional_revision"
    assert json_canvas_text_fit_independent_review["checks"] == {
        "historical_fallback_carry_acceptance_left_immutable": True,
        "rejected_revision_not_reused_as_accepted_revision": True,
        "line_start_carry_normalized_before_width_accounting": True,
        "post_trim_early_abort_removed": True,
        "fallback_calibration_extended_to_all_measured_over_0_9em_candidates": True,
        "fallback_calibration_uses_font_and_browser_measurements": True,
        "emoji_presentation_width_contract_isolated_from_plain_fallback_calibration": True,
        "literal_xml_replacement_width_budgeted_conservatively": True,
        "existing_grapheme_and_work_caps_preserved": True,
        "focused_review_regressions_passed": True,
        "native_document_and_diagram_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_dejavu_browser_readback_passed": True,
        "visual_readback_passed": True,
    }
    calibration = json_canvas_text_fit_independent_review["check_evidence"][
        "fallback_calibration_uses_font_and_browser_measurements"
    ]
    assert calibration["calibrated_codepoint_count"] == 143
    assert calibration["calibrated_range_count"] == 83
    assert calibration["threshold_em"] == 0.9
    assert json_canvas_text_fit_independent_review["check_evidence"][
        "focused_review_regressions_passed"
    ]["passed_count"] == 11
    assert json_canvas_text_fit_independent_review["check_evidence"][
        "browser_smoke_passed"
    ]["passed_count"] == 7
    independent_readback = json_canvas_text_fit_independent_review["check_evidence"][
        "exact_dejavu_browser_readback_passed"
    ]
    assert independent_readback["forced_font"] == "DejaVu Sans Bold"
    assert independent_readback["emdash"]["rendered"] == "——————————"
    assert independent_readback["emdash"]["all_text_boxes_within_node_bounds"] is True
    assert independent_readback["internal_carry"]["rendered"] == "éBBBB"
    assert independent_readback["internal_carry"]["truncated"] is False
    assert independent_readback["internal_carry"]["all_text_boxes_within_node_bounds"] is True
    assert independent_readback["emoji_presentation"]["rendered"] == "©️"
    assert independent_readback["emoji_presentation"]["truncated"] is False
    assert (
        independent_readback["emoji_presentation"]["all_text_boxes_within_node_bounds"]
        is True
    )
    assert (
        "independent review PASS for functional head aff9ff10032d49bf641e1726450cf9c3b51f3939"
        in json_canvas_text_fit_independent_review["does_not_establish"]
    )

    json_canvas_text_fit_wide_letters = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_WIDE_LETTERS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_wide_letters["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-wide-letters.v1"
    )
    assert (
        json_canvas_text_fit_wide_letters["functional_head"]
        == "64605f7b71b4e4be1c71ead5841db5cc78821497"
    )
    assert (
        json_canvas_text_fit_wide_letters["base_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_wide_letters["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_independent_review["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDEPENDENT_REVIEW_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-independent-review-20260930/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_independent_review["schema_version"],
    }
    assert json_canvas_text_fit_wide_letters["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_wide_letters, "evidence_digest"
    )
    assert set(json_canvas_text_fit_wide_letters["source_bindings"]) == (
        json_canvas_text_fit_wide_letters_superseded_files
    )
    for name, expected in json_canvas_text_fit_wide_letters["source_bindings"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_wide_letters["checks"] == {
        "historical_independent_review_acceptance_left_immutable": True,
        "u1675_reproduced_as_prior_underbudget_case": True,
        "non_ascii_letter_floor_is_script_aware": True,
        "ascii_letter_metrics_left_unchanged": True,
        "east_asian_wide_floor_preserved_conservatively": True,
        "myanmar_and_canadian_syllabics_extremes_are_tiered": True,
        "shaping_script_zwj_uses_shaping_aware_metric": True,
        "focused_renderer_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "code_suite_excluding_successor_binding_gate_passed": True,
        "exact_u1675_dejavu_bbox_passed": True,
        "successor_full_validate_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
    }
    wide_readback = json_canvas_text_fit_wide_letters["check_evidence"][
        "exact_u1675_dejavu_bbox_passed"
    ]
    assert wide_readback["forced_font"] == "DejaVu Sans"
    assert wide_readback["rendered"] == "ᙵᙵᙵᙵᙵ…"
    assert wide_readback["truncated"] is True
    assert wide_readback["all_text_boxes_within_node_bounds"] is True
    assert wide_readback["text_bbox"]["right"] <= wide_readback["node_bbox"]["width"]
    assert wide_readback["text_bbox"]["bottom"] <= wide_readback["node_bbox"]["height"]
    assert (
        "independent review PASS for functional head 64605f7b71b4e4be1c71ead5841db5cc78821497"
        in json_canvas_text_fit_wide_letters["does_not_establish"]
    )

    oauth_successor = json.loads(
        (MIRO_OAUTH_EVIDENCE / "acceptance-receipt.json").read_text(encoding="utf-8")
    )
    assert oauth_successor["schema_version"] == "schauwerk-miro-oauth-refresh-hardening.v1"
    assert oauth_successor["parent_evidence"] == {
        "file_sha256": hashlib.sha256(
            (CODEQL_TRIAGE_EVIDENCE / "triage.json").read_bytes()
        ).hexdigest(),
        "path": "docs/operators/evidence/codeql-residual-triage-20260904/triage.json",
        "schema_version": successor["schema_version"],
        "triage_digest": successor["triage_digest"],
    }
    assert oauth_successor["evidence_digest"] == digest_mapping(
        oauth_successor, "evidence_digest"
    )
    for name, expected in oauth_successor["source_bindings"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected

    codeql_superseded_files = {
        "src/schauwerk/runner.py",
        "tests/test_runner_output_security.py",
    }
    oauth_superseded_files = {
        "src/schauwerk/surfaces/miro/credentials.py",
        "tests/miro/test_credentials.py",
    }
    for name, expected in receipt["implementation_file_sha256"].items():
        current = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if name in codeql_superseded_files:
            assert successor["source_bindings"][name] == current
        elif name in oauth_superseded_files:
            assert oauth_successor["source_bindings"][name] == current
        elif name in json_canvas_text_fit_wide_letters_superseded_files:
            assert json_canvas_text_fit_wide_letters["source_bindings"][name] == current
        elif name in json_canvas_text_fit_independent_review_superseded_files:
            assert json_canvas_text_fit_independent_review["source_bindings"][name] == current
        elif name in json_canvas_text_fit_fallback_carry_superseded_files:
            assert json_canvas_text_fit_fallback_carry["source_bindings"][name] == current
        elif name in json_canvas_text_fit_combining_space_superseded_files:
            assert json_canvas_text_fit_combining_space["source_bindings"][name] == current
        elif name in json_canvas_text_fit_zero_advance_superseded_files:
            assert json_canvas_text_fit_zero_advance["source_bindings"][name] == current
        elif name in json_canvas_text_fit_final_superseded_files:
            assert json_canvas_text_fit_final["source_bindings"][name] == current
        elif name in json_canvas_text_fit_superseded_files:
            assert json_canvas_text_fit["source_bindings"][name] == current
        elif name in final_ui_fix_superseded_files:
            assert final_ui_fix["source_bindings"][name] == current
        elif name in product_ui_review_fix_superseded_files:
            assert product_ui_review_fix["source_bindings"][name] == current
        elif name in product_ui_superseded_files:
            assert product_ui_successor["source_bindings"][name] == current
        elif name in draft_restore_superseded_files:
            assert draft_restore_successor["source_bindings"][name] == current
        elif name in editor_superseded_files:
            assert editor_successor["source_bindings"][name] == current
        else:
            assert current == expected
    assert receipt["checks"] == {
        "action_refs_sha_pinned": True,
        "credential_reads_are_observational": True,
        "dynamic_http_headers_reject_controls": True,
        "focused_security_regressions_passed": True,
        "headless_browser_smoke_preflights_runnable_runtime": True,
        "local_path_fields_reject_urls": True,
        "miro_provider_hosts_are_parsed": True,
        "productive_publication_attempted": False,
        "provider_mutation_attempted": False,
        "publication_delivery_uses_descriptor_relative_nofollow": True,
        "user_visible_cli_output_redacts_secret_keys": True,
    }
    assert "Miro live authorization" in receipt["does_not_establish"]
    assert "GitHub repository security settings" in receipt["does_not_establish"]
