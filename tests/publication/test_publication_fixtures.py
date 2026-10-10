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
SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_REMEDIATION_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-review-remediation-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_UNICODE_REMEDIATION_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-unicode-remediation-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_CLAIM_INTEGRITY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-claim-integrity-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_HARDENING_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-review-hardening-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_ASCII_FALLBACK_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-ascii-fallback-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_NUMERIC_FALLBACK_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-numeric-fallback-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_SVG_WHITESPACE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-svg-whitespace-20261001"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_GEOMETRY_CAP_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-geometry-cap-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_ELLIPSIS_WIDTH_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-ellipsis-width-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDIC_ZWJ_FLOOR_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-indic-zwj-floor-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_INVARIANTS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-final-invariants-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_EMOJI_PRESENTATION_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-emoji-presentation-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_MARKDOWN_LINEAR_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-markdown-linear-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_VERTICAL_MARKER_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-json-canvas-text-fit-vertical-marker-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_SUPPLEMENTARY_SYMBOLS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-json-canvas-text-fit-supplementary-symbols-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-json-canvas-text-fit-viewer-startup-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_STATUS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-json-canvas-text-fit-viewer-startup-status-20261002"
)
SCHAUBILD_JSON_CANVAS_TEXT_FIT_PRIVATE_USE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-json-canvas-text-fit-private-use-20261002"
)
SCHAUBILD_UI_CONTROLS_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-ui-controls-20261002"
)
SCHAUBILD_UI_CONTROLS_RESIZE_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-ui-controls-resize-20261002"
)
SCHAUBILD_NATIVE_SMOKE_PIPEFAIL_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-native-smoke-pipefail-20261003"
)
SCHAUBILD_EDGE_LABEL_WIDTH_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-edge-label-width-20261003"
)
SCHAUBILD_CONTENT_EDITING_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-content-editing-20261003"
)
SCHAUBILD_CONTENT_EDITING_RECOVERY_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-content-editing-recovery-20261003"
)
SCHAUBILD_CONTENT_EDITING_FORM_SUBMIT_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-content-editing-form-submit-20261003"
)
SCHAUBILD_CONTENT_EDITING_VALID_DRAFT_RECOVERY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-content-editing-valid-draft-recovery-20261003"
)
SCHAUBILD_CONTENT_EDITING_RECOVERY_LAYOUT_RELOAD_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-content-editing-recovery-layout-reload-20261004"
)
SCHAUBILD_CONTENT_EDITING_SAVE_FEEDBACK_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-content-editing-save-feedback-20261004"
)
SCHAUBILD_CONTENT_EDITING_RECOVERY_SAVE_HARDENING_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/"
    "schaubild-content-editing-recovery-save-hardening-20261004"
)
SCHAUBILD_FOCUS_DEFAULT_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-focus-default-20261004"
)
SCHAUBILD_FOCUS_DEFAULT_REVIEW_FIX_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-focus-default-review-fixes-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_EXPORTS_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-single-workspace-exports-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_REVIEW_FIX_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-single-workspace-review-fixes-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_MOBILE_STATUS_EVIDENCE = (
    ROOT / "docs/operators/evidence/schaubild-single-workspace-mobile-status-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_WRAPPED_DOCK_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-wrapped-dock-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_DARK_STATUS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-dark-status-20261004"
)
SCHAUBILD_SINGLE_WORKSPACE_MAX_CANVAS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-max-canvas-20261005"
)
SCHAUBILD_SINGLE_WORKSPACE_FIT_CLEARANCE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-fit-clearance-20261005"
)
SCHAUBILD_SINGLE_WORKSPACE_REVIEW_CLOSURE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-review-closure-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-review-hardening-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_ZOOM_CONTINUITY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-zoom-continuity-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-fit-retry-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_POPOVER_ANCHORING_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-popover-anchoring-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_FINAL_REVIEW_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-final-review-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_FIT_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-safe-area-fit-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_TEST_CONTRACT_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-safe-area-test-contract-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_MOBILE_320_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-mobile-320-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-side-safearea-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_CI_FONT_LEGACY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-ci-font-legacy-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_INDEPENDENT_REMEDIATION_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-independent-remediation-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_LATE_REVIEW_MENUS_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-late-review-menus-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_CI_DOWNLOAD_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-ci-download-20261008"
)
SCHAUBILD_SINGLE_WORKSPACE_CI_CAPTION_SAFEAREA_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-ci-caption-safearea-final-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_MOBILE_PROMPT_WIDTH_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-ci-prompt-width-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_STATUS_AUTOFIT_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-status-autofit-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_STATUS_DRAG_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-status-drag-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_GESTURE_CANCEL_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-gesture-cancel-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_POINTER_OWNER_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-pointer-owner-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_TAP_AUTOFIT_ROLLBACK_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-tap-autofit-rollback-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_EMBEDDED_HOST_SAFEAREA_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-embedded-host-safearea-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_REVIEW_P2_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-review-p2-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_PINCH_SAVE_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-pinch-save-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_HOST_RETRY_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-host-retry-20261009"
)
SCHAUBILD_SINGLE_WORKSPACE_CI_SAVE_FONT_EVIDENCE = (
    ROOT
    / "docs/operators/evidence/schaubild-single-workspace-ci-save-font-20261010"
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
    smoke_pipefail_superseded_files = {
        "scripts/ci/smoke-native-schaubild-runtime.sh",
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
        if name not in (drawio_native_superseded_files | smoke_pipefail_superseded_files):
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
    json_canvas_text_fit_review_remediation_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_unicode_remediation_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_review_hardening_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_ascii_fallback_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_numeric_fallback_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_svg_whitespace_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_geometry_cap_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_ellipsis_width_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_indic_zwj_floor_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_final_invariants_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_emoji_presentation_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_markdown_linear_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_vertical_marker_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_supplementary_symbols_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    json_canvas_text_fit_viewer_startup_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer_browser.py",
    }
    json_canvas_text_fit_viewer_startup_status_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
    }
    json_canvas_text_fit_private_use_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    edge_label_width_superseded_files = {
        "src/schauwerk/visual/native_diagram.py",
        "tests/visual/test_native_document.py",
    }
    content_editing_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_recovery_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_form_submit_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_valid_draft_recovery_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_recovery_layout_reload_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_save_feedback_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    content_editing_recovery_save_hardening_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
    }
    ui_controls_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    ui_controls_resize_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer_browser.py",
    }
    focus_default_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
    }
    focus_default_review_fix_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_canvas_editor.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor_font_controls.py",
    }
    single_workspace_exports_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_review_fix_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_mobile_status_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_wrapped_dock_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_dark_status_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_max_canvas_superseded_files = {
        "Makefile",
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_fit_clearance_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_review_closure_superseded_files = {
        "Makefile",
        "scripts/run_browser_smoke.py",
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_browser_smoke_runner.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_native_viewer_product_ui.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_review_hardening_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_zoom_continuity_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_fit_retry_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_popover_anchoring_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_final_review_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_safe_area_fit_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_safe_area_test_contract_superseded_files = {
        "tests/visual/test_native_viewer.py",
    }
    single_workspace_mobile_320_superseded_files = {
        "Makefile",
        "scripts/run_browser_smoke.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_side_safearea_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_ci_font_legacy_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
        "tests/visual/test_standalone_editor_product_ui.py",
    }
    single_workspace_independent_remediation_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_product_ui.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
        "tests/visual/test_standalone_editor.py",
    }
    single_workspace_late_review_menus_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_ci_download_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_ci_caption_safearea_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_mobile_prompt_width_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
    }
    single_workspace_status_autofit_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_status_drag_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_gesture_cancel_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_pointer_owner_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_tap_autofit_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer_tap_autofit_browser.py",
        "Makefile",
        "scripts/run_browser_smoke.py",
    }
    single_workspace_embedded_host_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
        "tests/visual/test_standalone_editor_font_controls.py",
    }
    single_workspace_review_p2_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer_tap_autofit_browser.py",
        "tests/visual/test_standalone_editor.py",
        "tests/visual/test_standalone_editor_font_controls.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_pinch_save_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_native_viewer.py",
        "tests/visual/test_native_viewer_tap_autofit_browser.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_host_retry_superseded_files = {
        "src/schauwerk/resources/native_viewer/assets.py",
        "tests/visual/test_native_viewer_browser.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
    }
    single_workspace_ci_save_font_superseded_files = {
        "src/schauwerk/resources/standalone_editor/assets.py",
        "tests/visual/test_standalone_editor_single_workspace.py",
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
        if name in (
            single_workspace_max_canvas_superseded_files
            | single_workspace_review_closure_superseded_files
        ):
            continue
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
        if name in single_workspace_max_canvas_superseded_files:
            continue
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
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            product_ui_review_fix_superseded_files
            | final_ui_fix_superseded_files
            | json_canvas_text_fit_superseded_files
            | ui_controls_superseded_files
            | focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
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
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            final_ui_fix_superseded_files
            | json_canvas_text_fit_superseded_files
            | ui_controls_superseded_files
            | focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
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
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            json_canvas_text_fit_viewer_startup_superseded_files
            | ui_controls_superseded_files
            | focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
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
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            json_canvas_text_fit_final_superseded_files
            | smoke_pipefail_superseded_files
            | focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
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
        if name not in json_canvas_text_fit_review_remediation_superseded_files:
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

    json_canvas_text_fit_review_remediation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_REMEDIATION_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_review_remediation["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-review-remediation.v1"
    )
    assert (
        json_canvas_text_fit_review_remediation["functional_head"]
        == "bccbce5cc345784ab35d76c34f8d450652a0b87a"
    )
    assert (
        json_canvas_text_fit_review_remediation["base_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_review_remediation["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_wide_letters["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_WIDE_LETTERS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-wide-letters-20260930/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_wide_letters["schema_version"],
    }
    assert json_canvas_text_fit_review_remediation["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_review_remediation, "evidence_digest"
    )
    assert set(json_canvas_text_fit_review_remediation["source_bindings"]) == (
        json_canvas_text_fit_review_remediation_superseded_files
    )
    for name, expected in json_canvas_text_fit_review_remediation[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_unicode_remediation_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_review_remediation["checks"] == {
        "historical_wide_letter_acceptance_left_immutable": True,
        "rejected_revision_not_reused_as_accepted_revision": True,
        "generic_non_ascii_letter_baseline_restored_to_0_9em": True,
        "measured_letter_outliers_calibrated_separately": True,
        "full_bmp_letter_scan_has_no_underestimates": True,
        "u1675_remains_conservatively_truncated": True,
        "canadian_tail_measurement_disproves_hidden_overflow_claim": True,
        "shaping_script_zwj_budget_is_non_linear": True,
        "shaping_script_wide_single_letter_outliers_preserved": True,
        "fsi_source_normalized_once_per_projection": True,
        "fsi_pathological_pair_probe_is_bounded": True,
        "focused_renderer_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed_after_fresh_profile_retry": True,
        "exact_browser_geometry_and_performance_probe_passed": True,
        "successor_full_validate_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
    }
    remediation_review_debt = json_canvas_text_fit_review_remediation["review_debt"]
    assert remediation_review_debt["rejected_head"] == (
        "50b51f71862e63208e7c0f675537c2c27920f230"
    )
    assert remediation_review_debt["verdict"] == "REJECT_THIS_REVISION"
    assert remediation_review_debt["material_findings"] == 3
    assert [item["disposition"] for item in remediation_review_debt["dispositions"]] == [
        "confirmed_and_remediated",
        "not_reproduced_and_disproved_by_measurement",
        "confirmed_and_remediated",
    ]
    bmp_scan = json_canvas_text_fit_review_remediation["check_evidence"][
        "full_bmp_letter_scan"
    ]
    assert bmp_scan["sample_count"] == 48913
    assert bmp_scan["under_count"] == 0
    assert json_canvas_text_fit_review_remediation["check_evidence"][
        "successor_full_validate_passed"
    ]["passed_count"] == 1583
    remediation_browser = json_canvas_text_fit_review_remediation["check_evidence"][
        "exact_browser_geometry_and_performance_probe"
    ]
    assert remediation_browser["fsi_pair_count"] == 4000
    assert remediation_browser["cases"]["u1675"]["truncated"] is True
    assert remediation_browser["cases"]["u1675"]["inside"] is True
    assert remediation_browser["cases"]["canadian_tail_u1677"]["truncated"] is False
    assert remediation_browser["cases"]["canadian_tail_u1677"]["inside"] is True
    assert remediation_browser["cases"]["devanagari_zwj"]["inside"] is True
    assert remediation_browser["cases"]["malayalam_zwj"]["inside"] is True
    assert remediation_browser["cases"]["malayalam_wide_zwj"]["inside"] is True
    assert (
        "independent review PASS for functional head bccbce5cc345784ab35d76c34f8d450652a0b87a"
        in json_canvas_text_fit_review_remediation["does_not_establish"]
    )


    json_canvas_text_fit_unicode_remediation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_UNICODE_REMEDIATION_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_unicode_remediation["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-unicode-remediation.v1"
    )
    assert (
        json_canvas_text_fit_unicode_remediation["functional_head"]
        == "aca0edd884097741cf1ab5816c163293fef48de4"
    )
    assert (
        json_canvas_text_fit_unicode_remediation["base_main_head"]
        == "7a51dfa618a926f88ce14a96144c1bd360f203b5"
    )
    assert json_canvas_text_fit_unicode_remediation["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_review_remediation["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_REMEDIATION_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-review-remediation-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_review_remediation["schema_version"],
    }
    assert json_canvas_text_fit_unicode_remediation["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_unicode_remediation, "evidence_digest"
    )
    assert set(json_canvas_text_fit_unicode_remediation["source_bindings"]) == (
        json_canvas_text_fit_unicode_remediation_superseded_files
    )
    for name, expected in json_canvas_text_fit_unicode_remediation[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_review_hardening_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_unicode_remediation["checks"] == {
        "historical_review_remediation_acceptance_left_immutable": True,
        "rejected_revision_not_reused_as_accepted_revision": True,
        "u1677_tail_floor_removed": True,
        "full_bmp_letter_scan_has_no_underestimates": True,
        "supplementary_letter_calibration_is_range_bounded": True,
        "full_supplementary_letter_scan_has_no_underestimates": True,
        "multi_letter_shaping_zwj_fallback_is_script_calibrated": True,
        "fsi_resolver_avoids_suffix_slicing": True,
        "fsi_scaling_probe_is_bounded": True,
        "focused_renderer_modules_passed": True,
        "static_validation_passed": True,
        "browser_smoke_passed": True,
        "exact_browser_and_performance_probe_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "git_show_check_passed": True,
    }
    unicode_review_debt = json_canvas_text_fit_unicode_remediation["review_debt"]
    assert unicode_review_debt["rejected_head"] == (
        "437ec208423b6025f6e90bb360476e3548e7b860"
    )
    assert unicode_review_debt["verdict"] == "REJECT_THIS_REVISION"
    assert unicode_review_debt["material_findings"] == 4
    assert [item["disposition"] for item in unicode_review_debt["dispositions"]] == [
        "confirmed_and_remediated",
        "confirmed_and_remediated",
        "confirmed_and_remediated",
        "disproved_by_full_measurement",
    ]
    unicode_github_debt = json_canvas_text_fit_unicode_remediation["github_review_debt"]
    assert unicode_github_debt["thread_id"] == "PRRT_kwDOTGqvHc6nwDCP"
    assert unicode_github_debt["comment_id"] == 4150423149
    assert unicode_github_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    unicode_bmp = json_canvas_text_fit_unicode_remediation["check_evidence"][
        "full_bmp_letter_scan"
    ]
    assert unicode_bmp["sample_count"] == 48913
    assert unicode_bmp["under_count"] == 0
    unicode_supplementary = json_canvas_text_fit_unicode_remediation["check_evidence"][
        "full_supplementary_letter_scan"
    ]
    assert unicode_supplementary["sample_count"] == 87761
    assert unicode_supplementary["under_count"] == 0
    assert unicode_supplementary["calibrated_range_count"] == 216
    assert unicode_supplementary["ranges_sorted_nonoverlap"] is True
    assert unicode_supplementary["u1030c_estimate_em"] == 1.45
    assert unicode_supplementary["u12219_estimate_em"] == 4.05
    unicode_probe = json_canvas_text_fit_unicode_remediation["check_evidence"][
        "exact_browser_and_performance_probe"
    ]
    assert unicode_probe["under_count"] == 0
    assert unicode_probe["cases"]["u1030c"]["estimate_em"] >= (
        unicode_probe["cases"]["u1030c"]["actual_max_em"]
    )
    assert unicode_probe["cases"]["malayalam_chain"]["estimate_em"] >= (
        unicode_probe["cases"]["malayalam_chain"]["actual_max_em"]
    )
    assert unicode_probe["cases"]["myanmar_chain"]["estimate_em"] >= (
        unicode_probe["cases"]["myanmar_chain"]["actual_max_em"]
    )
    assert unicode_probe["cases"]["balinese_chain"]["estimate_em"] >= (
        unicode_probe["cases"]["balinese_chain"]["actual_max_em"]
    )
    unicode_pre_validate = json_canvas_text_fit_unicode_remediation["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert unicode_pre_validate["result"] == "expected_binding_gate_failure"
    assert unicode_pre_validate["passed_count"] == 1583
    assert unicode_pre_validate["failed_count"] == 1
    assert (
        "independent review PASS for functional head "
        "aca0edd884097741cf1ab5816c163293fef48de4"
        in json_canvas_text_fit_unicode_remediation["does_not_establish"]
    )

    json_canvas_text_fit_claim_integrity = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_CLAIM_INTEGRITY_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        json_canvas_text_fit_claim_integrity["schema_version"]
        == "schauwerk-schaubild-json-canvas-text-fit-claim-integrity.v1"
    )
    assert json_canvas_text_fit_claim_integrity["functional_head"] == (
        "aca0edd884097741cf1ab5816c163293fef48de4"
    )
    assert json_canvas_text_fit_claim_integrity["evidence_predecessor_head"] == (
        "4686cb38154e7c24b9bfb53ae23f82c9fdf79c22"
    )
    assert json_canvas_text_fit_claim_integrity["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_unicode_remediation["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_UNICODE_REMEDIATION_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-unicode-remediation-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_unicode_remediation["schema_version"],
    }
    assert json_canvas_text_fit_claim_integrity["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_claim_integrity, "evidence_digest"
    )
    for name, expected in json_canvas_text_fit_claim_integrity[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_review_hardening_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_claim_integrity["checks"] == {
        "historical_review_remediation_acceptance_left_immutable": True,
        "historical_non_linear_zwj_claim_is_explicitly_superseded": True,
        "current_multi_letter_shaping_zwj_fallback_is_intentionally_linear": True,
        "linear_fallback_applies_only_to_two_or_more_visible_letters": True,
        "current_browser_probe_remains_non_underestimating_for_bound_cases": True,
        "rejected_revision_not_reused_as_accepted_revision": True,
    }
    claim_correction = json_canvas_text_fit_claim_integrity[
        "historical_claim_correction"
    ]
    assert claim_correction["status"] == "superseded"
    assert (
        claim_correction["source_receipt"]
        == "docs/operators/evidence/"
        "schaubild-json-canvas-text-fit-review-remediation-20261001/"
        "acceptance-receipt.json"
    )
    assert "intentionally sums script-calibrated per-letter fallback floors" in (
        claim_correction["current_truth"]
    )
    assert (
        json_canvas_text_fit_claim_integrity["current_behavior"]["fallback"]
        == "sum script-calibrated per-letter fallback floors"
    )
    claim_review_debt = json_canvas_text_fit_claim_integrity["review_debt"]
    assert claim_review_debt["rejected_head"] == (
        "4686cb38154e7c24b9bfb53ae23f82c9fdf79c22"
    )
    assert claim_review_debt["verdict"] == "REJECT_THIS_REVISION"
    assert claim_review_debt["material_findings"] == 1
    assert claim_review_debt["disposition"]["status"] == (
        "confirmed_claim_integrity_defect_and_remediated_by_successor"
    )
    assert (
        "independent review PASS for the successor evidence head"
        in json_canvas_text_fit_claim_integrity["does_not_establish"]
    )

    claim_integrity_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_CLAIM_INTEGRITY_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert claim_integrity_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-claim-integrity-validation.v1"
    )
    assert claim_integrity_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-claim-integrity-20261001/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_CLAIM_INTEGRITY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert claim_integrity_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "672c2d538ab253ecf9b5117074d4c9a5a626168f3efa61c921b0e40d66fc70ad",
    }


    json_canvas_text_fit_review_hardening = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_HARDENING_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_review_hardening["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-review-hardening.v1"
    )
    assert json_canvas_text_fit_review_hardening["functional_head"] == (
        "3f3d8da49b6bb5be0c207eab9686d94a54b9fb3b"
    )
    assert json_canvas_text_fit_review_hardening["evidence_predecessor_head"] == (
        "67b19ae362e00f38d6fef98c0133cfaea426e544"
    )
    assert json_canvas_text_fit_review_hardening["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_claim_integrity["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_CLAIM_INTEGRITY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-claim-integrity-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_claim_integrity["schema_version"],
    }
    assert json_canvas_text_fit_review_hardening["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_review_hardening, "evidence_digest"
    )
    assert set(json_canvas_text_fit_review_hardening["source_bindings"]) == (
        json_canvas_text_fit_review_hardening_superseded_files
    )
    for name, expected in json_canvas_text_fit_review_hardening["source_bindings"].items():
        if name not in json_canvas_text_fit_ascii_fallback_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_review_hardening["checks"] == {
        "claim_integrity_parent_left_immutable": True,
        "fsi_budget_exhaustion_fails_closed": True,
        "fsi_projection_uses_shared_scan_budget": True,
        "publication_successor_binding_added": True,
        "rejected_revision_not_reused_as_accepted_revision": True,
        "shaping_zwj_letter_specialization_preserved": True,
        "shaping_zwj_non_letter_width_uses_canvas_calibration": True,
    }
    review_hardening_debt = json_canvas_text_fit_review_hardening["review_debt"]
    assert review_hardening_debt["rejected_head"] == (
        "67b19ae362e00f38d6fef98c0133cfaea426e544"
    )
    assert review_hardening_debt["decision_review_slot"] == "independent-gemini"
    assert review_hardening_debt["verdict"] == "REJECT_THIS_REVISION"
    assert review_hardening_debt["material_findings"] == 3
    assert [item["status"] for item in review_hardening_debt["dispositions"]] == [
        "confirmed_and_remediated_by_evidence_successor",
        "confirmed_and_remediated_in_functional_head",
        "confirmed_and_remediated_in_functional_head",
    ]
    assert (
        "independent review PASS for the successor evidence head"
        in json_canvas_text_fit_review_hardening["does_not_establish"]
    )

    review_hardening_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_HARDENING_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert review_hardening_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-review-hardening-validation.v1"
    )
    assert review_hardening_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-review-hardening-20261001/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_HARDENING_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert review_hardening_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "b0ffda1271f1bf442946fbc076e0d657d5b2775ac31b35e3669ac83ecc886c2e",
    }

    json_canvas_text_fit_ascii_fallback = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_ASCII_FALLBACK_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_ascii_fallback["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-ascii-fallback.v1"
    )
    assert json_canvas_text_fit_ascii_fallback["functional_head"] == (
        "2048da0ec97914f25c720bf34b48f6c4fa5f0d4b"
    )
    assert json_canvas_text_fit_ascii_fallback["evidence_predecessor_head"] == (
        "7ff4e028b281c545fed9045c78af71770ccf1b29"
    )
    assert json_canvas_text_fit_ascii_fallback["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_review_hardening["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_REVIEW_HARDENING_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-review-hardening-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_review_hardening["schema_version"],
    }
    assert json_canvas_text_fit_ascii_fallback["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_ascii_fallback, "evidence_digest"
    )
    assert set(json_canvas_text_fit_ascii_fallback["source_bindings"]) == (
        json_canvas_text_fit_ascii_fallback_superseded_files
    )
    for name, expected in json_canvas_text_fit_ascii_fallback["source_bindings"].items():
        if name not in json_canvas_text_fit_numeric_fallback_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_ascii_fallback["checks"] == {
        "review_hardening_parent_left_immutable": True,
        "github_ascii_operator_fallback_review_remediated": True,
        "bold_fallback_operators_calibrated_to_0_85em": True,
        "measured_ascii_default_outliers_calibrated_to_0_72em": True,
        "plus_run_reflows_before_fallback_overflow": True,
        "lowercase_run_reflows_before_fallback_overflow": True,
        "existing_unicode_and_zwj_specializations_preserved": True,
        "publication_successor_binding_added": True,
    }
    ascii_github_debt = json_canvas_text_fit_ascii_fallback["github_review_debt"]
    assert ascii_github_debt["thread_id"] == "PRRT_kwDOTGqvHc6n4v26"
    assert ascii_github_debt["comment_id"] == 4153967306
    assert ascii_github_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    ascii_scope = json_canvas_text_fit_ascii_fallback["measurement_scope"]
    assert ascii_scope["operator_measured_max_em"] <= ascii_scope["operator_floor_em"]
    assert ascii_scope["default_measured_max_em"] <= ascii_scope["default_floor_em"]
    assert (
        "universal width safety for arbitrary fonts outside the measured acceptance population"
        in json_canvas_text_fit_ascii_fallback["does_not_establish"]
    )

    ascii_fallback_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_ASCII_FALLBACK_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert ascii_fallback_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-ascii-fallback-validation.v1"
    )
    assert ascii_fallback_validation["functional_head"] == (
        "2048da0ec97914f25c720bf34b48f6c4fa5f0d4b"
    )
    assert ascii_fallback_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-ascii-fallback-20261001/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_ASCII_FALLBACK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert ascii_fallback_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "dd95ff88d8ddcb6e25bf6205c86f5b270b75b68219abc280e2c63e5784cb7c4d",
    }

    json_canvas_text_fit_numeric_fallback = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_NUMERIC_FALLBACK_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_numeric_fallback["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-numeric-fallback.v1"
    )
    assert json_canvas_text_fit_numeric_fallback["functional_head"] == (
        "901c843d0f90b1b5f213a43d50d021ce9d77b849"
    )
    assert json_canvas_text_fit_numeric_fallback["evidence_predecessor_head"] == (
        "3ece0ef7e0e87bad9f68f521226df06cebb937be"
    )
    assert json_canvas_text_fit_numeric_fallback["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_ascii_fallback["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_ASCII_FALLBACK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-ascii-fallback-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_ascii_fallback["schema_version"],
    }
    assert json_canvas_text_fit_numeric_fallback["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_numeric_fallback, "evidence_digest"
    )
    assert set(json_canvas_text_fit_numeric_fallback["source_bindings"]) == (
        json_canvas_text_fit_numeric_fallback_superseded_files
    )
    for name, expected in json_canvas_text_fit_numeric_fallback[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_svg_whitespace_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_numeric_fallback["checks"] == {
        "ascii_fallback_parent_left_immutable": True,
        "github_numeric_fallback_review_remediated": True,
        "all_non_ascii_unicode_numeric_codepoints_measured": True,
        "single_and_ten_glyph_runs_non_underestimating": True,
        "calibrated_ranges_sorted_nonoverlap": True,
        "calibrated_ranges_binary_lookup_exact": True,
        "representative_bmp_and_supplementary_numeric_regressions_passed": True,
        "renderer_modules_passed": True,
        "publication_successor_binding_added": True,
    }
    numeric_review_debt = json_canvas_text_fit_numeric_fallback["github_review_debt"]
    assert numeric_review_debt["thread_id"] == "PRRT_kwDOTGqvHc6oA3Mq"
    assert numeric_review_debt["comment_id"] == 4157252300
    assert numeric_review_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    numeric_scope = json_canvas_text_fit_numeric_fallback["measurement_scope"]
    assert numeric_scope["unicode_categories"] == ["Nd", "Nl", "No"]
    assert numeric_scope["sample_count"] == 1821
    assert numeric_scope["calibrated_range_count"] == 213
    assert numeric_scope["measured_over_base_floor_count"] == 417
    assert numeric_scope["final_under_count"] == 0
    assert numeric_scope["max_codepoint"] == "U+1242B"
    assert numeric_scope["max_measured_em"] < 4.65
    numeric_final_scan = json_canvas_text_fit_numeric_fallback["check_evidence"][
        "final_binary_browser_scan"
    ]
    assert numeric_final_scan["sample_count"] == 1821
    assert numeric_final_scan["under_count"] == 0
    assert numeric_final_scan["calibrated_range_count"] == 213
    assert numeric_final_scan["ranges_sorted_nonoverlap"] is True
    numeric_pre_validate = json_canvas_text_fit_numeric_fallback["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert numeric_pre_validate["result"] == "expected_binding_gate_failure"
    assert numeric_pre_validate["passed_count"] == 1605
    assert numeric_pre_validate["failed_count"] == 1
    assert (
        "universal width safety for arbitrary fonts outside the measured acceptance population"
        in json_canvas_text_fit_numeric_fallback["does_not_establish"]
    )

    numeric_fallback_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_NUMERIC_FALLBACK_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert numeric_fallback_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-numeric-fallback-validation.v1"
    )
    assert numeric_fallback_validation["functional_head"] == (
        "901c843d0f90b1b5f213a43d50d021ce9d77b849"
    )
    assert numeric_fallback_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-numeric-fallback-20261001/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_NUMERIC_FALLBACK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert numeric_fallback_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "210b12597ed566d6694eb941f8cc9fc35e2b456527c2d4a225efd776d129ceb4",
    }

    json_canvas_text_fit_svg_whitespace = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_SVG_WHITESPACE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_svg_whitespace["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-svg-whitespace.v1"
    )
    assert json_canvas_text_fit_svg_whitespace["functional_head"] == (
        "15432349737dfbd9c1a019e73d18ef009a7f8817"
    )
    assert json_canvas_text_fit_svg_whitespace["evidence_predecessor_head"] == (
        "91f0fef452f445015f66291f64dbf24de5c69e57"
    )
    assert json_canvas_text_fit_svg_whitespace["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_numeric_fallback["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_NUMERIC_FALLBACK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-numeric-fallback-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_numeric_fallback["schema_version"],
    }
    assert json_canvas_text_fit_svg_whitespace["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_svg_whitespace, "evidence_digest"
    )
    assert set(json_canvas_text_fit_svg_whitespace["source_bindings"]) == (
        json_canvas_text_fit_svg_whitespace_superseded_files
    )
    for name, expected in json_canvas_text_fit_svg_whitespace[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_geometry_cap_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_svg_whitespace["checks"] == {
        "numeric_fallback_parent_left_immutable": True,
        "github_svg_whitespace_review_remediated": True,
        "svg_inline_whitespace_collapsed_before_grapheme_segmentation": True,
        "whitespace_prefixed_extended_grapheme_wrap_carry_preserved": True,
        "combining_space_carry_regression_preserved": True,
        "renderer_modules_passed": True,
        "browser_smoke_passed": True,
        "exact_case_browser_readback_passed": True,
        "publication_successor_binding_added": True,
    }
    svg_whitespace_debt = json_canvas_text_fit_svg_whitespace["github_review_debt"]
    assert svg_whitespace_debt["thread_id"] == "PRRT_kwDOTGqvHc6oEOx0"
    assert svg_whitespace_debt["comment_id"] == 4158617787
    assert svg_whitespace_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    svg_whitespace_validate = json_canvas_text_fit_svg_whitespace["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert svg_whitespace_validate["result"] == "expected_binding_gate_failure"
    assert svg_whitespace_validate["passed_count"] == 1606
    assert svg_whitespace_validate["failed_count"] == 1
    svg_whitespace_browser = json_canvas_text_fit_svg_whitespace["check_evidence"][
        "exact_case_browser_readback"
    ]
    assert svg_whitespace_browser["result"] == "passed"
    assert svg_whitespace_browser["truncated"] is True
    assert svg_whitespace_browser["all_text_boxes_within_node_bounds"] is True
    assert svg_whitespace_browser["text_right_px"] < svg_whitespace_browser["node_right_px"]

    svg_whitespace_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_SVG_WHITESPACE_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert svg_whitespace_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-svg-whitespace-validation.v1"
    )
    assert svg_whitespace_validation["functional_head"] == (
        "15432349737dfbd9c1a019e73d18ef009a7f8817"
    )
    assert svg_whitespace_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-svg-whitespace-20261001/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_SVG_WHITESPACE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert svg_whitespace_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "91d2d774fd69006557c761dccad19bfa409112adc2e1dfc794851fb49d9b22b4",
    }

    json_canvas_text_fit_geometry_cap = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_GEOMETRY_CAP_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_geometry_cap["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-geometry-cap.v1"
    )
    assert json_canvas_text_fit_geometry_cap["functional_head"] == (
        "c6ded6e3ff8412fe88ced6361b2a5b92738fb634"
    )
    assert json_canvas_text_fit_geometry_cap["evidence_predecessor_head"] == (
        "e4fc308e5633f36c6a837c3d38f33fea3acb8ac8"
    )
    assert json_canvas_text_fit_geometry_cap["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_svg_whitespace["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_SVG_WHITESPACE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-svg-whitespace-20261001/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_svg_whitespace["schema_version"],
    }
    assert json_canvas_text_fit_geometry_cap["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_geometry_cap, "evidence_digest"
    )
    assert set(json_canvas_text_fit_geometry_cap["source_bindings"]) == (
        json_canvas_text_fit_geometry_cap_superseded_files
    )
    for name, expected in json_canvas_text_fit_geometry_cap["source_bindings"].items():
        if name not in json_canvas_text_fit_ellipsis_width_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_geometry_cap["checks"] == {
        "svg_whitespace_parent_left_immutable": True,
        "github_geometry_cap_review_remediated": True,
        "control_free_geometry_cap_applied_before_work_cap": True,
        "zero_advance_control_path_preserved": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "control_equivalence_probe_passed": True,
        "performance_probe_passed": True,
        "browser_readiness_flake_cleared_by_isolated_rerun": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    geometry_debt = json_canvas_text_fit_geometry_cap["github_review_debt"]
    assert geometry_debt["thread_id"] == "PRRT_kwDOTGqvHc6oFz01"
    assert geometry_debt["comment_id"] == 4159253445
    assert geometry_debt["disposition"] == "confirmed_and_remediated_in_functional_head"
    geometry_probe = json_canvas_text_fit_geometry_cap["check_evidence"][
        "control_equivalence_and_performance"
    ]
    assert geometry_probe["control_cases"] == 6
    assert geometry_probe["source_cluster_count"] == 19000
    assert geometry_probe["geometry_cluster_limit"] == 21
    assert geometry_probe["work_cluster_limit"] == 8193
    assert geometry_probe["loop_count"] == 128
    assert geometry_probe["prefix_clusters"] == 21
    assert geometry_probe["elapsed_seconds"] < 1.0
    geometry_pre_validate = json_canvas_text_fit_geometry_cap["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert geometry_pre_validate["result"] == "expected_binding_gate_failure"
    assert geometry_pre_validate["passed_count"] == 1607
    assert geometry_pre_validate["failed_count"] == 1
    geometry_browser_retry = json_canvas_text_fit_geometry_cap["check_evidence"][
        "isolated_browser_readiness_retry"
    ]
    assert geometry_browser_retry["result"] == "passed"

    geometry_cap_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_GEOMETRY_CAP_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert geometry_cap_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-geometry-cap-validation.v1"
    )
    assert geometry_cap_validation["functional_head"] == (
        "c6ded6e3ff8412fe88ced6361b2a5b92738fb634"
    )
    assert geometry_cap_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-geometry-cap-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_GEOMETRY_CAP_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert geometry_cap_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "d016758ca6e636385f52ac5a788481ac001b0192e87237a4ac201c2508970eda",
    }

    json_canvas_text_fit_ellipsis_width = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_ELLIPSIS_WIDTH_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_ellipsis_width["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-ellipsis-width.v1"
    )
    assert json_canvas_text_fit_ellipsis_width["functional_head"] == (
        "7098f102f898493e7129d297bd2495bf8d4a61cc"
    )
    assert json_canvas_text_fit_ellipsis_width["evidence_predecessor_head"] == (
        "8ef89166bdd40276d157c474fa5594fed5a64db8"
    )
    assert json_canvas_text_fit_ellipsis_width["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_geometry_cap["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_GEOMETRY_CAP_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-geometry-cap-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_geometry_cap["schema_version"],
    }
    assert json_canvas_text_fit_ellipsis_width["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_ellipsis_width, "evidence_digest"
    )
    assert set(json_canvas_text_fit_ellipsis_width["source_bindings"]) == (
        json_canvas_text_fit_ellipsis_width_superseded_files
    )
    for name, expected in json_canvas_text_fit_ellipsis_width["source_bindings"].items():
        if name not in json_canvas_text_fit_indic_zwj_floor_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_ellipsis_width["checks"] == {
        "geometry_cap_parent_left_immutable": True,
        "github_ellipsis_width_review_remediated": True,
        "existing_ellipsis_width_checked_before_retention": True,
        "oversized_ellipsis_dropped": True,
        "fitting_ellipsis_preserved": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "browser_readiness_flake_cleared_by_isolated_rerun": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    ellipsis_debt = json_canvas_text_fit_ellipsis_width["github_review_debt"]
    assert ellipsis_debt["thread_id"] == "PRRT_kwDOTGqvHc6oOOUp"
    assert ellipsis_debt["comment_id"] == 4162726312
    assert ellipsis_debt["disposition"] == "confirmed_and_remediated_in_functional_head"
    ellipsis_reproduction = json_canvas_text_fit_ellipsis_width["check_evidence"][
        "original_reproduction"
    ]
    assert ellipsis_reproduction["result"] == "confirmed_width_contract_violation"
    assert ellipsis_reproduction["ellipsis_width_px"] > ellipsis_reproduction["available_width_px"]
    ellipsis_pre_validate = json_canvas_text_fit_ellipsis_width["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert ellipsis_pre_validate["result"] == "expected_binding_gate_failure"
    assert ellipsis_pre_validate["passed_count"] == 1608
    assert ellipsis_pre_validate["failed_count"] == 1
    ellipsis_browser_retry = json_canvas_text_fit_ellipsis_width["check_evidence"][
        "isolated_browser_readiness_retry"
    ]
    assert ellipsis_browser_retry["result"] == "passed"

    ellipsis_width_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_ELLIPSIS_WIDTH_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert ellipsis_width_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-ellipsis-width-validation.v1"
    )
    assert ellipsis_width_validation["functional_head"] == (
        "7098f102f898493e7129d297bd2495bf8d4a61cc"
    )
    assert ellipsis_width_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-ellipsis-width-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_ELLIPSIS_WIDTH_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert ellipsis_width_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "7f393a43a8ad7749d5bd53bae5d33cc41f1aada1af1d447828414240edc01713",
    }

    json_canvas_text_fit_indic_zwj_floor = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDIC_ZWJ_FLOOR_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_indic_zwj_floor["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-indic-zwj-floor.v1"
    )
    assert json_canvas_text_fit_indic_zwj_floor["functional_head"] == (
        "f025693f44a37e1563775a18b834569d3f655b3a"
    )
    assert json_canvas_text_fit_indic_zwj_floor["evidence_predecessor_head"] == (
        "1b9061207515836d8de8d2fa7da4a82814b2486e"
    )
    assert json_canvas_text_fit_indic_zwj_floor["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_ellipsis_width["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_ELLIPSIS_WIDTH_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-ellipsis-width-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_ellipsis_width["schema_version"],
    }
    assert json_canvas_text_fit_indic_zwj_floor["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_indic_zwj_floor, "evidence_digest"
    )
    assert set(json_canvas_text_fit_indic_zwj_floor["source_bindings"]) == (
        json_canvas_text_fit_indic_zwj_floor_superseded_files
    )
    for name, expected in json_canvas_text_fit_indic_zwj_floor["source_bindings"].items():
        if name not in json_canvas_text_fit_final_invariants_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_indic_zwj_floor["checks"] == {
        "ellipsis_width_parent_left_immutable": True,
        "independent_review_linear_floor_finding_remediated": True,
        "independent_review_incb_expansion_rejected_against_current_ucd": True,
        "per_letter_isolated_fallback_floor_applied": True,
        "incb_snapshot_left_unchanged": True,
        "focused_indic_regressions_passed": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "diff_hygiene_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    review = json_canvas_text_fit_indic_zwj_floor["independent_review"]
    assert review["reviewed_head"] == "1b9061207515836d8de8d2fa7da4a82814b2486e"
    assert review["verdict"] == "NEEDS_CHANGE"
    assert [item["disposition"] for item in review["findings"]] == [
        "confirmed_and_remediated_in_functional_head",
        "not_applicable_current_unicode_virama_scripts",
    ]
    assert review["findings"][1]["current_virama_scripts"] == [
        "Balinese","Bengali","Devanagari","Gujarati","Javanese","Malayalam","Oriya","Telugu"
    ]
    floor_probe = json_canvas_text_fit_indic_zwj_floor["check_evidence"][
        "pre_fix_floor_probe"
    ]
    assert set(floor_probe["under_budget_scripts"]) == {
        "Bengali","Devanagari","Gujarati","Malayalam","Telugu"
    }
    assert floor_probe["gurmukhi_cluster_count"] == 2
    pre_validate = json_canvas_text_fit_indic_zwj_floor["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert pre_validate["result"] == "expected_binding_gate_failure"
    assert pre_validate["passed_count"] == 1615
    assert pre_validate["failed_count"] == 1

    indic_zwj_floor_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDIC_ZWJ_FLOOR_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert indic_zwj_floor_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-indic-zwj-floor-validation.v1"
    )
    assert indic_zwj_floor_validation["functional_head"] == (
        "f025693f44a37e1563775a18b834569d3f655b3a"
    )
    assert indic_zwj_floor_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-indic-zwj-floor-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDIC_ZWJ_FLOOR_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert indic_zwj_floor_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "d3167d937dcf8f5692bd7a59fcf6c0d12f3558194a832332cb70d47f4c4814d7",
    }

    json_canvas_text_fit_final_invariants = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_INVARIANTS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_final_invariants["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-final-invariants.v1"
    )
    assert json_canvas_text_fit_final_invariants["intermediate_functional_head"] == (
        "236c717e62e2eb3b35e0f6ba2602fd085bd96308"
    )
    assert json_canvas_text_fit_final_invariants["functional_head"] == (
        "f3213a17674d379edddc9242f0d270acae4a940e"
    )
    assert json_canvas_text_fit_final_invariants["evidence_predecessor_head"] == (
        "75474e6d82494dda219c5ebabe2c93d589db3477"
    )
    assert json_canvas_text_fit_final_invariants["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_indic_zwj_floor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_INDIC_ZWJ_FLOOR_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-indic-zwj-floor-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_indic_zwj_floor["schema_version"],
    }
    assert json_canvas_text_fit_final_invariants["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_final_invariants, "evidence_digest"
    )
    assert set(json_canvas_text_fit_final_invariants["source_bindings"]) == (
        json_canvas_text_fit_final_invariants_superseded_files
    )
    for name, expected in json_canvas_text_fit_final_invariants[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_emoji_presentation_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_final_invariants["checks"] == {
        "indic_zwj_parent_left_immutable": True,
        "github_zero_width_geometry_review_remediated": True,
        "github_bidi_projection_review_remediated": True,
        "github_combining_carry_review_remediated": True,
        "independent_single_letter_zwj_review_remediated": True,
        "github_supplementary_pictographic_review_remediated": True,
        "single_letter_shaping_zwj_uses_isolated_floor": True,
        "supplementary_pictographic_fallback_measured_and_bounded": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "diff_hygiene_passed": True,
        "browser_readiness_flake_cleared_by_isolated_rerun": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    final_github_debt = json_canvas_text_fit_final_invariants["github_review_debt"]
    assert [item["thread_id"] for item in final_github_debt] == [
        "PRRT_kwDOTGqvHc6oObs1",
        "PRRT_kwDOTGqvHc6oObz1",
        "PRRT_kwDOTGqvHc6oObz3",
        "PRRT_kwDOTGqvHc6oOw2p",
    ]
    assert all(
        item["disposition"].startswith("confirmed_and_remediated")
        for item in final_github_debt
    )
    final_independent = json_canvas_text_fit_final_invariants[
        "independent_review_debt"
    ]
    assert final_independent["reviewed_head"] == (
        "75474e6d82494dda219c5ebabe2c93d589db3477"
    )
    assert final_independent["verdict"] == "NEEDS_CHANGE"
    assert final_independent["finding"]["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    final_measurement = json_canvas_text_fit_final_invariants["measurement_scope"]
    assert final_measurement["max_measured_codepoint"] == "U+1F634"
    assert final_measurement["max_measured_em"] < (
        final_measurement["supplementary_pictographic_floor_em"]
    )
    final_pre_validate = json_canvas_text_fit_final_invariants["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert final_pre_validate["result"] == "expected_binding_gate_failure"
    assert final_pre_validate["passed_count"] == 1625
    assert final_pre_validate["failed_count"] == 1

    final_invariants_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_INVARIANTS_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert final_invariants_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-final-invariants-validation.v1"
    )
    assert final_invariants_validation["functional_head"] == (
        "f3213a17674d379edddc9242f0d270acae4a940e"
    )
    assert final_invariants_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-final-invariants-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_INVARIANTS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert final_invariants_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "6dcb8b264e85751a4cde5d176be7481ea3d370fbe59079d5b0932e7154067191",
    }

    json_canvas_text_fit_emoji_presentation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_EMOJI_PRESENTATION_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_emoji_presentation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-emoji-presentation.v1"
    )
    assert json_canvas_text_fit_emoji_presentation["functional_head"] == (
        "cb21e7ee40dbe87b0cbf999aaae989c7c8a1bf74"
    )
    assert json_canvas_text_fit_emoji_presentation["evidence_predecessor_head"] == (
        "927612360df5d11fad57426db96c7f30bc2955b0"
    )
    assert json_canvas_text_fit_emoji_presentation["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_final_invariants["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_FINAL_INVARIANTS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-final-invariants-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_final_invariants["schema_version"],
    }
    assert json_canvas_text_fit_emoji_presentation["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_emoji_presentation, "evidence_digest"
    )
    assert set(json_canvas_text_fit_emoji_presentation["source_bindings"]) == (
        json_canvas_text_fit_emoji_presentation_superseded_files
    )
    for name, expected in json_canvas_text_fit_emoji_presentation[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_markdown_linear_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_emoji_presentation["checks"] == {
        "final_invariants_parent_left_immutable": True,
        "github_emoji_presentation_review_remediated": True,
        "emoji_presentation_floor_measured_in_chromium": True,
        "supplementary_vs16_scan_bounded_all_extended_pictographic_candidates": True,
        "svg_text_measurement_matches_canvas_scan": True,
        "plain_supplementary_pictographic_floor_preserved": True,
        "keycap_and_bmp_presentation_paths_covered": True,
        "focused_regressions_passed": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "diff_hygiene_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    emoji_debt = json_canvas_text_fit_emoji_presentation["github_review_debt"]
    assert emoji_debt["thread_id"] == "PRRT_kwDOTGqvHc6oPQ8u"
    assert emoji_debt["comment_id"] == 4163159044
    assert emoji_debt["disposition"] == "confirmed_and_remediated_in_functional_head"
    emoji_measure = json_canvas_text_fit_emoji_presentation["measurement_scope"]
    assert emoji_measure["supplementary_extended_pictographic_codepoint_count"] == 2678
    assert emoji_measure["chromium_canvas_scan"]["inter_arial_sans_max_em"] < (
        emoji_measure["emoji_presentation_floor_em"]
    )
    assert emoji_measure["chromium_canvas_scan"]["dejavu_sans_max_em"] < (
        emoji_measure["emoji_presentation_floor_em"]
    )
    emoji_pre_validate = json_canvas_text_fit_emoji_presentation["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert emoji_pre_validate["result"] == "expected_binding_gate_failure"
    assert emoji_pre_validate["passed_count"] == 1628
    assert emoji_pre_validate["failed_count"] == 1

    emoji_presentation_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_EMOJI_PRESENTATION_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert emoji_presentation_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-emoji-presentation-validation.v1"
    )
    assert emoji_presentation_validation["functional_head"] == (
        "cb21e7ee40dbe87b0cbf999aaae989c7c8a1bf74"
    )
    assert emoji_presentation_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-emoji-presentation-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_EMOJI_PRESENTATION_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert emoji_presentation_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "3f78429f0adbe21cbf51d5df2093961e9ef625ef746176aea55fe31faf34fe14",
    }

    json_canvas_text_fit_markdown_linear = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_MARKDOWN_LINEAR_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_markdown_linear["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-markdown-linear.v1"
    )
    assert json_canvas_text_fit_markdown_linear["functional_head"] == (
        "e609de6bd3510111a3094e2ba0de23f4857ef489"
    )
    assert json_canvas_text_fit_markdown_linear["evidence_predecessor_head"] == (
        "c080f7c995d9aa722ef9b95b5a4fbda815351880"
    )
    assert json_canvas_text_fit_markdown_linear["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_emoji_presentation["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_EMOJI_PRESENTATION_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-emoji-presentation-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_emoji_presentation["schema_version"],
    }
    assert json_canvas_text_fit_markdown_linear["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_markdown_linear, "evidence_digest"
    )
    assert set(json_canvas_text_fit_markdown_linear["source_bindings"]) == (
        json_canvas_text_fit_markdown_linear_superseded_files
    )
    for name, expected in json_canvas_text_fit_markdown_linear[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_vertical_marker_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_markdown_linear["checks"] == {
        "emoji_presentation_parent_left_immutable": True,
        "github_markdown_regex_review_remediated": True,
        "markdown_link_parser_linearized": True,
        "legacy_markdown_link_semantics_preserved": True,
        "large_unmatched_brackets_bounded": True,
        "focused_regressions_passed": True,
        "differential_semantics_probe_passed": True,
        "performance_probe_passed": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "diff_hygiene_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    markdown_debt = json_canvas_text_fit_markdown_linear["github_review_debt"]
    assert markdown_debt["review_id"] == "PRR_kwDOTGqvHc8AAAABQTWU6w"
    assert markdown_debt["reviewed_head"] == (
        "c080f7c995d9aa722ef9b95b5a4fbda815351880"
    )
    assert markdown_debt["disposition"] == "confirmed_and_remediated_in_functional_head"
    markdown_perf = json_canvas_text_fit_markdown_linear["performance_evidence"]
    assert markdown_perf["differential_case_count"] == 12800
    assert markdown_perf["differential_mismatch_count"] == 0
    assert markdown_perf["post_fix"]["brackets_32000_seconds"] < 0.01
    markdown_pre_validate = json_canvas_text_fit_markdown_linear["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert markdown_pre_validate["result"] == "expected_binding_gate_failure"
    assert markdown_pre_validate["passed_count"] == 1634
    assert markdown_pre_validate["failed_count"] == 1

    markdown_linear_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_MARKDOWN_LINEAR_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert markdown_linear_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-markdown-linear-validation.v1"
    )
    assert markdown_linear_validation["functional_head"] == (
        "e609de6bd3510111a3094e2ba0de23f4857ef489"
    )
    assert markdown_linear_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-markdown-linear-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_MARKDOWN_LINEAR_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert markdown_linear_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "9dd6bada04ddccad5b9ae5850e63f85ed474e2afb5e7f96fc359090432cae13b",
    }

    json_canvas_text_fit_vertical_marker = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VERTICAL_MARKER_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_vertical_marker["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-vertical-marker.v1"
    )
    assert json_canvas_text_fit_vertical_marker["functional_head"] == (
        "95629e6e83c2153ab8d4ceffafcf32f8e39722eb"
    )
    assert json_canvas_text_fit_vertical_marker["evidence_predecessor_head"] == (
        "00ec7ab9b333afedf3cb1a0f5f6d761011e8d0b7"
    )
    assert json_canvas_text_fit_vertical_marker["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_markdown_linear["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_MARKDOWN_LINEAR_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-markdown-linear-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_markdown_linear["schema_version"],
    }
    assert json_canvas_text_fit_vertical_marker["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_vertical_marker, "evidence_digest"
    )
    assert set(json_canvas_text_fit_vertical_marker["source_bindings"]) == (
        json_canvas_text_fit_vertical_marker_superseded_files
    )
    for name, expected in json_canvas_text_fit_vertical_marker[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_supplementary_symbols_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_vertical_marker["checks"] == {
        "markdown_linear_parent_left_immutable": True,
        "github_vertical_marker_review_remediated": True,
        "horizontal_marker_fit_preserved": True,
        "vertical_marker_fit_uses_existing_minimum_baseline": True,
        "too_short_nodes_emit_no_clipped_marker": True,
        "normal_minimum_height_content_fit_preserved": True,
        "focused_regressions_passed": True,
        "renderer_modules_passed": True,
        "static_validation_passed": True,
        "diff_hygiene_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    vertical_debt = json_canvas_text_fit_vertical_marker["github_review_debt"]
    assert vertical_debt["thread_id"] == "PRRT_kwDOTGqvHc6oQQ8x"
    assert vertical_debt["comment_id"] == 4163573076
    assert vertical_debt["disposition"] == "confirmed_and_remediated_in_functional_head"
    vertical_geometry = json_canvas_text_fit_vertical_marker["geometry_scope"]
    assert vertical_geometry["minimum_font_size_px"] == 12
    assert vertical_geometry["minimum_first_baseline_offset_px"] == 24
    assert vertical_geometry["height_28_result"] == "truncated_without_marker"
    assert vertical_geometry["height_29_result"] == "content_line_fits_at_baseline_24"
    vertical_pre_validate = json_canvas_text_fit_vertical_marker["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert vertical_pre_validate["result"] == "expected_binding_gate_failure"
    assert vertical_pre_validate["passed_count"] == 1635
    assert vertical_pre_validate["failed_count"] == 1

    vertical_marker_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VERTICAL_MARKER_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert vertical_marker_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-vertical-marker-validation.v1"
    )
    assert vertical_marker_validation["functional_head"] == (
        "95629e6e83c2153ab8d4ceffafcf32f8e39722eb"
    )
    assert vertical_marker_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-vertical-marker-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VERTICAL_MARKER_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert vertical_marker_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "8309e21bda54e9fec49c32350dd2dc920c82585e9b566a4af8af1eb210c82bd6",
    }

    json_canvas_text_fit_supplementary_symbols = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_SUPPLEMENTARY_SYMBOLS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_supplementary_symbols["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-supplementary-symbols.v1"
    )
    assert json_canvas_text_fit_supplementary_symbols["functional_head"] == (
        "1bbaa12a488591faf5c653c1be2bcf5c4c2adfad"
    )
    assert json_canvas_text_fit_supplementary_symbols[
        "evidence_predecessor_head"
    ] == "e507a028f3291fd78a2d7aac1b8026f7432ef74c"
    assert json_canvas_text_fit_supplementary_symbols["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_vertical_marker["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VERTICAL_MARKER_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-vertical-marker-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_vertical_marker["schema_version"],
    }
    assert json_canvas_text_fit_supplementary_symbols[
        "evidence_digest"
    ] == digest_mapping(
        json_canvas_text_fit_supplementary_symbols, "evidence_digest"
    )
    assert set(json_canvas_text_fit_supplementary_symbols["source_bindings"]) == (
        json_canvas_text_fit_supplementary_symbols_superseded_files
    )
    for name, expected in json_canvas_text_fit_supplementary_symbols[
        "source_bindings"
    ].items():
        if name not in json_canvas_text_fit_private_use_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_supplementary_symbols["checks"] == {
        "vertical_marker_parent_left_immutable": True,
        "github_supplementary_symbol_review_remediated": True,
        "supplementary_so_scan_covered_all_candidates": True,
        "acceptance_font_population_measured_in_chromium": True,
        "countercheck_outliers_closed": True,
        "calibration_ranges_sorted_nonoverlap": True,
        "reviewed_domino_budgeted_conservatively": True,
        "focused_regressions_passed": True,
        "complete_supplementary_so_scan_passed": True,
        "diff_hygiene_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    supplementary_debt = json_canvas_text_fit_supplementary_symbols[
        "github_review_debt"
    ]
    assert supplementary_debt["thread_id"] == "PRRT_kwDOTGqvHc6oTWSk"
    assert supplementary_debt["comment_id"] == 4164846704
    assert supplementary_debt["reviewed_head"] == (
        "e507a028f3291fd78a2d7aac1b8026f7432ef74c"
    )
    assert supplementary_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    supplementary_measure = json_canvas_text_fit_supplementary_symbols[
        "measurement_scope"
    ]
    assert supplementary_measure["sample_count"] == 3903
    assert supplementary_measure["under_count"] == 0
    assert supplementary_measure["calibration_range_count"] == 235
    assert supplementary_measure["ranges_sorted_nonoverlap"] is True
    assert len(supplementary_measure["countercheck_outliers"]) == 4
    assert all(
        item["post_fix_estimate_em"] >= item["measured_max_em"]
        for item in supplementary_measure["countercheck_outliers"]
    )
    supplementary_pre_validate = json_canvas_text_fit_supplementary_symbols[
        "check_evidence"
    ]["pre_successor_full_validate"]
    assert supplementary_pre_validate["result"] == "expected_binding_gate_failure"
    assert supplementary_pre_validate["passed_count"] == 1644
    assert supplementary_pre_validate["failed_count"] == 1

    supplementary_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_SUPPLEMENTARY_SYMBOLS_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert supplementary_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-supplementary-symbols-validation.v1"
    )
    assert supplementary_validation["functional_head"] == (
        "1bbaa12a488591faf5c653c1be2bcf5c4c2adfad"
    )
    assert supplementary_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-supplementary-symbols-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_SUPPLEMENTARY_SYMBOLS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert supplementary_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "0a80fafeedfb4ff4ecc54eff15de2b789473830230534f022aebe877129f1081",
    }

    json_canvas_text_fit_viewer_startup = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_viewer_startup["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-viewer-startup.v1"
    )
    assert json_canvas_text_fit_viewer_startup["functional_head"] == (
        "7939d9389b3d31f84170660c39616998e5ef3574"
    )
    assert json_canvas_text_fit_viewer_startup["evidence_predecessor_head"] == (
        "5d672a3ca712e469e38439613681037126282a5c"
    )
    assert json_canvas_text_fit_viewer_startup["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_supplementary_symbols["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_SUPPLEMENTARY_SYMBOLS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-supplementary-symbols-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_supplementary_symbols["schema_version"],
    }
    assert json_canvas_text_fit_viewer_startup["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_viewer_startup, "evidence_digest"
    )
    assert set(json_canvas_text_fit_viewer_startup["source_bindings"]) == (
        json_canvas_text_fit_viewer_startup_superseded_files
    )
    for name, expected in json_canvas_text_fit_viewer_startup["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            json_canvas_text_fit_viewer_startup_status_superseded_files
            | ui_controls_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_viewer_startup["checks"] == {
        "supplementary_symbols_parent_left_immutable": True,
        "public_head_browser_baseline_passed": True,
        "startup_flake_reproduced": True,
        "test_only_yield_hardening_proved_insufficient": True,
        "viewer_startup_timer_fallback_idempotent": True,
        "prototype_repeatability_passed": True,
        "exact_functional_head_repeatability_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    startup_contract = json_canvas_text_fit_viewer_startup["startup_contract"]
    assert startup_contract == {
        "primary_scheduler": "requestAnimationFrame",
        "fallback_scheduler": "setTimeout",
        "fallback_delay_ms": 50,
        "initialization_idempotent": True,
        "preserves_storage_failure_status": True,
        "fit_runs_after_startup_repair_persistence_failure": True,
    }
    startup_pre_validate = json_canvas_text_fit_viewer_startup["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert startup_pre_validate["result"] == "expected_binding_gate_failure"
    assert startup_pre_validate["passed_count"] == 1644
    assert startup_pre_validate["failed_count"] == 1

    viewer_startup_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert viewer_startup_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-viewer-startup-validation.v1"
    )
    assert viewer_startup_validation["functional_head"] == (
        "7939d9389b3d31f84170660c39616998e5ef3574"
    )
    assert viewer_startup_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-viewer-startup-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert viewer_startup_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "77c475cc751d3a45f2bcce8fa089e1fa8d5d1e48d198dd662625347de5b30748",
    }

    json_canvas_text_fit_viewer_startup_status = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_STATUS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_viewer_startup_status["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-viewer-startup-status.v1"
    )
    assert json_canvas_text_fit_viewer_startup_status["functional_head"] == (
        "006058e014e45d80d6fa2ba9126d88502c94bfa1"
    )
    assert json_canvas_text_fit_viewer_startup_status["evidence_predecessor_head"] == (
        "7048d76db0ff49796f68f5e1fa50c1fbe3da9f02"
    )
    assert json_canvas_text_fit_viewer_startup_status["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_viewer_startup["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-viewer-startup-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_viewer_startup["schema_version"],
    }
    assert json_canvas_text_fit_viewer_startup_status["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_viewer_startup_status, "evidence_digest"
    )
    assert set(json_canvas_text_fit_viewer_startup_status["source_bindings"]) == (
        json_canvas_text_fit_viewer_startup_status_superseded_files
    )
    for name, expected in json_canvas_text_fit_viewer_startup_status[
        "source_bindings"
    ].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in ui_controls_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_viewer_startup_status["checks"] == {
        "viewer_startup_parent_left_immutable": True,
        "browser_test_remains_parent_owned_and_byte_identical": True,
        "startup_status_race_reproduced": True,
        "status_guard_preserves_later_user_messages": True,
        "startup_readiness_remains_repeatable": True,
        "product_limit_status_remains_repeatable": True,
        "browser_module_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    assert json_canvas_text_fit_viewer_startup_status["status_contract"] == {
        "startup_status_snapshot_captured_before_scheduling": True,
        "fit_always_runs": True,
        "document_publication_always_runs_when_hosted": True,
        "startup_fit_announces_only_when_status_is_unchanged": True,
        "storage_failure_status_is_not_overwritten": True,
        "later_user_status_is_not_overwritten": True,
    }
    status_pre_validate = json_canvas_text_fit_viewer_startup_status["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert status_pre_validate["result"] == "expected_binding_gate_failure"
    assert status_pre_validate["passed_count"] == 1644
    assert status_pre_validate["failed_count"] == 1

    viewer_startup_status_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_STATUS_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert viewer_startup_status_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-viewer-startup-status-validation.v1"
    )
    assert viewer_startup_status_validation["functional_head"] == (
        "006058e014e45d80d6fa2ba9126d88502c94bfa1"
    )
    assert viewer_startup_status_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-viewer-startup-status-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_STATUS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert viewer_startup_status_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "0fe14fcd7f9c9639256e61cb14f72c1ad36c226adbb3e7a0ff3daee440401715",
    }

    json_canvas_text_fit_private_use = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_PRIVATE_USE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert json_canvas_text_fit_private_use["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-private-use.v1"
    )
    assert json_canvas_text_fit_private_use["functional_head"] == (
        "ca014372ee498e0be0274b4f00106817f265c150"
    )
    assert json_canvas_text_fit_private_use["evidence_predecessor_head"] == (
        "86cecc36e7d7df74c317da5b76bb684c962c5ef4"
    )
    assert json_canvas_text_fit_private_use["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_viewer_startup_status["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_VIEWER_STARTUP_STATUS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-viewer-startup-status-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_viewer_startup_status["schema_version"],
    }
    assert json_canvas_text_fit_private_use["evidence_digest"] == digest_mapping(
        json_canvas_text_fit_private_use, "evidence_digest"
    )
    assert set(json_canvas_text_fit_private_use["source_bindings"]) == (
        json_canvas_text_fit_private_use_superseded_files
    )
    for name, expected in json_canvas_text_fit_private_use["source_bindings"].items():
        if name not in edge_label_width_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert json_canvas_text_fit_private_use["checks"] == {
        "viewer_startup_status_parent_left_immutable": True,
        "github_private_use_review_remediated": True,
        "complete_private_use_population_measured": True,
        "acceptance_font_population_measured_in_chromium": True,
        "private_use_floor_covers_measured_maximum": True,
        "focused_regressions_passed": True,
        "complete_private_use_estimator_scan_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    private_use_debt = json_canvas_text_fit_private_use["github_review_debt"]
    assert private_use_debt["thread_id"] == "PRRT_kwDOTGqvHc6oVirw"
    assert private_use_debt["comment_id"] == 4165744379
    assert private_use_debt["reviewed_head"] == (
        "86cecc36e7d7df74c317da5b76bb684c962c5ef4"
    )
    assert private_use_debt["disposition"] == (
        "confirmed_and_remediated_in_functional_head"
    )
    private_use_measure = json_canvas_text_fit_private_use["measurement_scope"]
    assert private_use_measure["sample_count"] == 137468
    assert private_use_measure["post_fix_floor_em"] == 1.4
    assert private_use_measure["post_fix_under_count"] == 0
    assert private_use_measure["measured_maximum"]["width_em"] < 1.4
    private_use_pre_validate = json_canvas_text_fit_private_use["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert private_use_pre_validate["result"] == "expected_binding_gate_failure"
    assert private_use_pre_validate["passed_count"] == 1648
    assert private_use_pre_validate["failed_count"] == 1

    private_use_validation = json.loads(
        (
            SCHAUBILD_JSON_CANVAS_TEXT_FIT_PRIVATE_USE_EVIDENCE
            / "validation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert private_use_validation["schema_version"] == (
        "schauwerk-schaubild-json-canvas-text-fit-private-use-validation.v1"
    )
    assert private_use_validation["functional_head"] == (
        "ca014372ee498e0be0274b4f00106817f265c150"
    )
    assert private_use_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-private-use-20261002/"
            "acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_PRIVATE_USE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
    }
    assert private_use_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "ee4ccf0cf301b767322176448f82b55c0c6ad38945c8edc502c7b171fdf66926",
    }

    ui_controls = json.loads(
        (SCHAUBILD_UI_CONTROLS_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        ui_controls["schema_version"]
        == "schauwerk-schaubild-ui-controls-overhaul.v1"
    )
    assert (
        ui_controls["functional_head"]
        == "42484490a4e8a7dd0e1feba96ade81b7807bc7ac"
    )
    assert ui_controls["parent_evidence"] == {
        "evidence_digest": json_canvas_text_fit_private_use["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_JSON_CANVAS_TEXT_FIT_PRIVATE_USE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-json-canvas-text-fit-private-use-20261002/"
            "acceptance-receipt.json"
        ),
        "schema_version": json_canvas_text_fit_private_use["schema_version"],
    }
    assert ui_controls["evidence_digest"] == digest_mapping(
        ui_controls, "evidence_digest"
    )
    assert set(ui_controls["source_bindings"]) == ui_controls_superseded_files
    for name, expected in ui_controls["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            ui_controls_resize_superseded_files
            | content_editing_superseded_files
            | focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert ui_controls["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "native_host_legacy_only_controls_hidden": True,
        "native_output_controls_reduced_to_supported_actions": True,
        "selection_dependent_edit_controls_stateful": True,
        "hosted_native_toolbar_compacted": True,
        "responsive_toolbar_has_no_horizontal_overflow": True,
        "focus_controls_clear_of_editor_stage": True,
        "focused_tests_passed": True,
        "exact_head_visual_readback_passed": True,
        "responsive_760_readback_passed": True,
    }
    ui_test_evidence = ui_controls["check_evidence"]["focused_tests_passed"]
    assert ui_test_evidence["functional_head"] == ui_controls["functional_head"]
    assert ui_test_evidence["job_unit"] == "grabowski-job-8dd00e04e83a"
    assert ui_test_evidence["passed_count"] == 8
    ui_visual_evidence = ui_controls["check_evidence"][
        "exact_head_visual_readback_passed"
    ]
    assert ui_visual_evidence["functional_head"] == ui_controls["functional_head"]
    assert ui_visual_evidence["job_unit"] == "grabowski-job-f343eb8e0d3a"
    assert ui_visual_evidence["normal_mode"]["no_outer_overlap"] is True
    assert ui_visual_evidence["normal_mode"]["no_horizontal_overflow"] is True
    assert ui_visual_evidence["focus_mode"]["no_outer_overlap"] is True
    assert ui_visual_evidence["focus_mode"]["no_horizontal_overflow"] is True
    assert ui_visual_evidence["focus_mode"]["outer_controls_max_bottom_px"] == 48
    assert ui_visual_evidence["focus_mode"]["editor_frame_top_px"] == 60
    assert ui_visual_evidence["screenshots_sha256"] == {
        "normal": "89a05a11b40d94ba6bf2493b06002d1e947c6909221a44897e342970249d77ee",
        "focus": "cdc7cba5d0fcb2e96cd2b71ff8c25720551674440624d53d27184db4739e3bcc",
    }
    ui_responsive_evidence = ui_controls["check_evidence"][
        "responsive_760_readback_passed"
    ]
    assert ui_responsive_evidence["functional_head"] == ui_controls["functional_head"]
    assert ui_responsive_evidence["job_unit"] == "grabowski-job-e0ea61477e37"
    assert ui_responsive_evidence["viewport_css_px"] == {"width": 760, "height": 900}
    assert ui_responsive_evidence["normal_mode"]["no_outer_overlap"] is True
    assert ui_responsive_evidence["normal_mode"]["no_horizontal_overflow"] is True
    assert ui_responsive_evidence["focus_mode"]["no_outer_overlap"] is True
    assert ui_responsive_evidence["focus_mode"]["no_horizontal_overflow"] is True
    assert ui_responsive_evidence["screenshots_sha256"] == {
        "normal": "df7417be086fbf2c20fa73f91d92605de6666eab5e40af029df41091e51f5282",
        "focus": "e97913c6e18325b42c51739f6f240687d0ac3208ea2095f8e73b607af47484e0",
    }
    assert (
        "user visual acceptance of the UI revision"
        in ui_controls["does_not_establish"]
    )
    assert (
        "runtime publication or Commonthing integration/deployment"
        in ui_controls["does_not_establish"]
    )

    ui_controls_resize = json.loads(
        (
            SCHAUBILD_UI_CONTROLS_RESIZE_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        ui_controls_resize["schema_version"]
        == "schauwerk-schaubild-ui-controls-resize.v1"
    )
    assert (
        ui_controls_resize["functional_head"]
        == "4a52b78858e646e78d5e2ad78d6f9aa8b0626505"
    )
    assert ui_controls_resize["parent_evidence"] == {
        "evidence_digest": ui_controls["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_UI_CONTROLS_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-ui-controls-20261002/acceptance-receipt.json"
        ),
        "schema_version": ui_controls["schema_version"],
    }
    assert ui_controls_resize["evidence_digest"] == digest_mapping(
        ui_controls_resize, "evidence_digest"
    )
    assert set(ui_controls_resize["source_bindings"]) == (
        ui_controls_resize_superseded_files
    )
    for name, expected in ui_controls_resize["source_bindings"].items():
        if name in (
            single_workspace_max_canvas_superseded_files
            | single_workspace_review_closure_superseded_files
        ):
            continue
        if name not in (
            focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert ui_controls_resize["checks"] == {
        "parent_acceptance_left_immutable": True,
        "fitted_view_refits_on_viewport_resize": True,
        "manual_zoom_survives_viewport_resize": True,
        "responsive_shrink_keeps_nodes_visible": True,
        "no_horizontal_overflow_after_resize": True,
        "focused_tests_passed": True,
        "exact_head_resize_readback_passed": True,
    }
    resize_tests = ui_controls_resize["check_evidence"]["focused_tests_passed"]
    assert resize_tests["functional_head"] == ui_controls_resize["functional_head"]
    assert resize_tests["job_unit"] == "grabowski-job-671055e9d93e"
    assert resize_tests["passed_count"] == 8
    resize_readback = ui_controls_resize["check_evidence"][
        "exact_head_resize_readback_passed"
    ]
    assert resize_readback["functional_head"] == ui_controls_resize["functional_head"]
    assert resize_readback["job_unit"] == "grabowski-job-cf4484a8a336"
    assert resize_readback["fitted_after_shrink_430"]["all_nodes_inside"] is True
    assert (
        resize_readback["fitted_after_shrink_430"]["auto_refit_changed_transform"]
        is True
    )
    assert resize_readback["manual_view"][
        "preserved_across_430_to_390_resize"
    ] is True
    assert resize_readback["refit_after_manual_view"]["all_nodes_inside"] is True
    assert (
        "user visual acceptance of the resize successor revision"
        in ui_controls_resize["does_not_establish"]
    )

    smoke_pipefail = json.loads(
        (
            SCHAUBILD_NATIVE_SMOKE_PIPEFAIL_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        smoke_pipefail["schema_version"]
        == "schauwerk-schaubild-native-smoke-pipefail.v1"
    )
    assert (
        smoke_pipefail["functional_head"]
        == "b064c164b7bb2fd39fd43e5349dd822f88163f7d"
    )
    assert smoke_pipefail["parent_evidence"] == {
        "evidence_digest": ui_controls_resize["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_UI_CONTROLS_RESIZE_EVIDENCE / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-ui-controls-resize-20261002/acceptance-receipt.json"
        ),
        "schema_version": ui_controls_resize["schema_version"],
    }
    assert smoke_pipefail["evidence_digest"] == digest_mapping(
        smoke_pipefail, "evidence_digest"
    )
    assert set(smoke_pipefail["source_bindings"]) == smoke_pipefail_superseded_files
    for name, expected in smoke_pipefail["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert smoke_pipefail["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "merged_main_native_image_failure_observed": True,
        "smoke_exit_23_observed_on_github_runner": True,
        "viewer_marker_has_large_trailing_response": True,
        "early_exit_pipe_removed_from_smoke": True,
        "exact_merged_main_local_image_build_passed": True,
        "exact_runtime_smoke_passed_locally": True,
        "targeted_pipe_safety_regression_passed": True,
        "patched_smoke_twenty_repetitions_passed": True,
    }
    smoke_failure = smoke_pipefail["check_evidence"][
        "merged_main_native_image_failure_observed"
    ]
    assert smoke_failure["merge_commit"] == "893b69a8316bd3967be9b633b4bbb70ebf5b8d00"
    assert smoke_failure["workflow_run_id"] == 37076760340
    assert smoke_failure["observed_exit_code"] == 23
    smoke_repeat = smoke_pipefail["check_evidence"][
        "patched_smoke_twenty_repetitions_passed"
    ]
    assert smoke_repeat["repetitions"] == 20
    assert smoke_repeat["passed"] == 20
    assert (
        "unique root-cause certainty for the single GitHub Actions exit-23 event"
        in smoke_pipefail["does_not_establish"]
    )
    assert (
        "successful workflow_dispatch publication of the final image"
        in smoke_pipefail["does_not_establish"]
    )

    edge_label_width = json.loads(
        (SCHAUBILD_EDGE_LABEL_WIDTH_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        edge_label_width["schema_version"]
        == "schauwerk-schaubild-edge-label-width.v1"
    )
    assert (
        edge_label_width["functional_head"]
        == "6bdecfd5f9abf20b6b1eb8b3eb240421450bc136"
    )
    assert edge_label_width["parent_evidence"] == {
        "evidence_digest": smoke_pipefail["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_NATIVE_SMOKE_PIPEFAIL_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-native-smoke-pipefail-20261003/acceptance-receipt.json"
        ),
        "schema_version": smoke_pipefail["schema_version"],
    }
    assert edge_label_width["evidence_digest"] == digest_mapping(
        edge_label_width, "evidence_digest"
    )
    assert set(edge_label_width["source_bindings"]) == edge_label_width_superseded_files
    for name, expected in edge_label_width["source_bindings"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert edge_label_width["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "ordinary_edge_label_reproduction_fixed": True,
        "label_box_uses_bounded_render_width_model": True,
        "existing_long_and_pathological_truncation_regressions_passed": True,
        "targeted_regressions_passed": True,
        "exact_functional_head_render_readback_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    edge_label_targeted = edge_label_width["check_evidence"]["targeted_regressions"]
    assert edge_label_targeted["functional_head"] == edge_label_width["functional_head"]
    assert edge_label_targeted["job_unit"] == "grabowski-job-c5d25a395568"
    assert edge_label_targeted["passed_count"] == 4
    assert edge_label_targeted["result"] == "passed"
    edge_label_readback = edge_label_width["check_evidence"]["exact_render_readback"]
    assert edge_label_readback == {
        "functional_head": edge_label_width["functional_head"],
        "job_unit": "grabowski-job-d5fca91300fe",
        "finalization_receipt_sha256": (
            "0137baf3d5fe7bbe2785c9b7b25048b0f4d70595a51f455d7c9329a0ce743d05"
        ),
        "label": "trägt bei zu",
        "rendered_text": "trägt bei zu",
        "title": "trägt bei zu",
        "truncated": False,
        "box_width_px": 132.0,
        "result": "passed",
    }
    edge_label_pre_validate = edge_label_width["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert edge_label_pre_validate["result"] == "expected_binding_gate_failure"
    assert edge_label_pre_validate["passed_count"] == 1650
    assert edge_label_pre_validate["failed_count"] == 1
    assert (
        "browser-level visual acceptance of the successor"
        in edge_label_width["does_not_establish"]
    )

    edge_label_width_validation = json.loads(
        (SCHAUBILD_EDGE_LABEL_WIDTH_EVIDENCE / "validation-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert edge_label_width_validation["schema_version"] == (
        "schauwerk-schaubild-edge-label-width-validation.v1"
    )
    assert edge_label_width_validation["evidence_successor_head"] == (
        "b96e7aae38185752dc6c48dec103ec7fd8413b25"
    )
    assert (
        edge_label_width_validation["functional_head"]
        == edge_label_width["functional_head"]
    )
    assert edge_label_width_validation["acceptance_receipt"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-edge-label-width-20261003/acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_EDGE_LABEL_WIDTH_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
    }
    assert edge_label_width_validation["publication_fixture"] == {
        "path": "tests/publication/test_publication_fixtures.py",
        "file_sha256": "10d852c12346ba98674c0157bdb2e34e6f7dba58a3102abe3d14e0fcc7da5491",
    }
    assert edge_label_width_validation["full_validation"] == {
        "job_unit": "grabowski-job-dfd559c9493a",
        "finalization_receipt_sha256": (
            "b424529a5269213e952679781319b3d07d6aa8af1a3dd290f54ad16b2686a003"
        ),
        "passed_count": 1651,
        "failed_count": 0,
        "result": "passed",
    }

    content_editing = json.loads(
        (SCHAUBILD_CONTENT_EDITING_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        content_editing["schema_version"]
        == "schauwerk-schaubild-content-editing.v1"
    )
    assert (
        content_editing["functional_head"]
        == "81738c302c5f77c24ceae52db9dfe31a7e0619bc"
    )
    assert content_editing["parent_evidence"] == {
        "evidence_digest": edge_label_width["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_EDGE_LABEL_WIDTH_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-edge-label-width-20261003/acceptance-receipt.json"
        ),
        "schema_version": edge_label_width["schema_version"],
    }
    assert content_editing["evidence_digest"] == digest_mapping(
        content_editing, "evidence_digest"
    )
    assert set(content_editing["source_bindings"]) == content_editing_superseded_files
    for name, expected in content_editing["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_recovery_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "canonical_representation_content_editable": True,
        "text_edit_scope_preserves_structural_semantics": True,
        "stale_input_digest_removed_before_revalidation": True,
        "edited_representation_revalidated_and_rerendered": True,
        "title_syncs_workspace_draft_and_export_basename": True,
        "representation_retry_and_stale_svg_recovery_extended": True,
        "focused_tests_passed": True,
        "relevant_regressions_passed": True,
        "managed_browser_content_roundtrip_passed": True,
        "exact_dialog_pixel_readback_passed": True,
        "responsive_760_readback_passed": True,
        "pre_successor_full_validate_failed_only_on_expected_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    content_focused = content_editing["check_evidence"]["focused_tests"]
    assert content_focused == {
        "functional_head": content_editing["functional_head"],
        "job_unit": "grabowski-job-1290a14a3985",
        "argv_sha256": (
            "efc4a4a993934e65865838fffd03a8c7147096de6054df15af81bc46122d3b73"
        ),
        "finalization_receipt_sha256": (
            "eb92f500f4519b56328ad9645f65cbdedfd98d1e089bda8b500212494b63e09c"
        ),
        "passed_count": 3,
        "result": "passed",
    }
    content_regressions = content_editing["check_evidence"]["relevant_regressions"]
    assert content_regressions["functional_head"] == content_editing["functional_head"]
    assert content_regressions["job_unit"] == "grabowski-job-4a3a86130724"
    assert content_regressions["finalization_receipt_sha256"] == (
        "8a2744e1dfe68b8de726b57bc1ad7410885087de9c7be943041872c0de2f650a"
    )
    assert content_regressions["passed_count"] == 361
    assert content_regressions["result"] == "passed"
    content_browser = content_editing["check_evidence"][
        "managed_browser_content_roundtrip"
    ]
    assert content_browser["functional_head"] == content_editing["functional_head"]
    assert content_browser["worker_id"] == "3ea44ef909d44b1facae"
    assert content_browser["snapshot_id"] == (
        "bsid2_c9a79df0a7135d7d989799bf357ac0a4914b97d79f64e2c03aed908843143cc4"
    )
    assert content_browser["audit_record_sha256"] == (
        "8104ea2de6ac902a22120ba77517daa61328ca01fec23dd2174d0ebf3e1c7a6c"
    )
    assert content_browser["result_label"] == "CONTENT EDIT TITLE PASS"
    assert content_browser["result"] == "passed"
    content_visual = content_editing["check_evidence"]["exact_dialog_pixel_readback"]
    assert content_visual["functional_head"] == content_editing["functional_head"]
    assert content_visual["job_unit"] == "grabowski-job-c5ef2bc6dbc7"
    assert content_visual["finalization_receipt_sha256"] == (
        "e6e0c07eca04f710dd52b47faf766dd8220cc276a26f80899887105a18fbdad0"
    )
    assert content_visual["viewport_css_px"] == {"width": 1024, "height": 768}
    assert content_visual["dialog"]["open"] is True
    assert content_visual["dialog"]["horizontal_overflow"] is False
    assert content_visual["fields"]["vertical_scroll_expected"] is True
    assert content_visual["page_horizontal_overflow"] is False
    assert content_visual["controls"] == 31
    assert content_visual["save_visible"] is True
    assert content_visual["close_visible"] is True
    assert content_visual["screenshot_sha256"] == (
        "a38b0897f221f096cad713394f3cf635dab1c0705f89bf2fcf5217f93a674416"
    )
    content_responsive = content_editing["check_evidence"]["responsive_760_readback"]
    assert content_responsive["functional_head"] == content_editing["functional_head"]
    assert content_responsive["job_unit"] == "grabowski-job-c5ef2bc6dbc7"
    assert content_responsive["viewport_css_px"] == {"width": 760, "height": 900}
    assert content_responsive["dialog"]["open"] is True
    assert content_responsive["dialog"]["horizontal_overflow"] is False
    assert content_responsive["fields"]["vertical_scroll_expected"] is True
    assert content_responsive["page_horizontal_overflow"] is False
    assert content_responsive["controls"] == 31
    assert content_responsive["save_visible"] is True
    assert content_responsive["close_visible"] is True
    assert content_responsive["screenshot_sha256"] == (
        "25ab49c03a51d6ff7d73bb19b782dfb0cf1e66c47f2d74f7b6eec78d61136851"
    )
    content_pre_validate = content_editing["check_evidence"]["pre_successor_full_validate"]
    assert content_pre_validate["github_workflow_run_id"] == 37143524097
    assert content_pre_validate["result"] == "expected_binding_gate_failure"
    assert content_pre_validate["passed_count"] == 1644
    assert content_pre_validate["failed_count"] == 1
    assert content_pre_validate["failing_test"] == (
        "tests/publication/test_publication_fixtures.py::"
        "test_infrastructure_hardening_acceptance_and_successor_bind_security_revisions"
    )
    assert (
        "user visual acceptance or aesthetic approval of the content editor revision"
        in content_editing["does_not_establish"]
    )
    assert (
        "Commonthing release-lock promotion or production deployment"
        in content_editing["does_not_establish"]
    )

    content_editing_recovery = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_RECOVERY_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_recovery["schema_version"]
        == "schauwerk-schaubild-content-editing-recovery.v1"
    )
    assert (
        content_editing_recovery["functional_head"]
        == "1f69cf0782be9a691db29064be8f176587c0774b"
    )
    assert content_editing_recovery["parent_evidence"] == {
        "evidence_digest": content_editing["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_CONTENT_EDITING_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-20261003/acceptance-receipt.json"
        ),
        "schema_version": content_editing["schema_version"],
    }
    assert content_editing_recovery["evidence_digest"] == digest_mapping(
        content_editing_recovery, "evidence_digest"
    )
    assert (
        set(content_editing_recovery["source_bindings"])
        == content_editing_recovery_superseded_files
    )
    for name, expected in content_editing_recovery["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_form_submit_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_recovery["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "dragged_layout_overrides_migrate_across_content_digest": True,
        "transient_recovery_draft_uses_candidate_title": True,
        "last_valid_representation_retained_across_retry": True,
        "permanent_rejection_restores_valid_draft": True,
        "representation_restore_resyncs_title": True,
        "structural_edit_scope_unchanged": True,
        "focused_recovery_tests_passed": True,
        "relevant_regressions_passed": True,
        "ruff_passed": True,
        "github_p2_findings_addressed_locally": True,
    }
    recovery_focused = content_editing_recovery["check_evidence"][
        "focused_recovery_tests"
    ]
    assert recovery_focused == {
        "functional_head": content_editing_recovery["functional_head"],
        "job_unit": "grabowski-job-0a34792fbb37",
        "argv_sha256": (
            "421d8f8717effa0504487ad279df0fff156dc08de7d2e59390bbf2ca3457268a"
        ),
        "finalization_receipt_sha256": (
            "25df003fd59a192edd0883117eb1a57451d3ca2500edf7c2d9b0ab932e21acc6"
        ),
        "passed_count": 4,
        "result": "passed",
    }
    recovery_regressions = content_editing_recovery["check_evidence"][
        "relevant_regressions"
    ]
    assert recovery_regressions["functional_head"] == content_editing_recovery[
        "functional_head"
    ]
    assert recovery_regressions["job_unit"] == "grabowski-job-f444abd9b8bb"
    assert recovery_regressions["argv_sha256"] == (
        "febde5bfb8a9555ac8e1bc665601cd354dc825992afa0f37e0e11e8c9c580545"
    )
    assert recovery_regressions["finalization_receipt_sha256"] == (
        "fc3d37d23d0242af1c62d8cc90729791ac860adc1bfb82a763387189c56ae5d3"
    )
    assert recovery_regressions["passed_count"] == 362
    assert recovery_regressions["result"] == "passed"
    recovery_review = content_editing_recovery["check_evidence"][
        "github_review_findings"
    ]
    assert recovery_review["source_head"] == (
        "46c909f55a79e7e5f5dabf9001be5004667a24db"
    )
    assert recovery_review["addressed_by_functional_head"] == (
        content_editing_recovery["functional_head"]
    )
    assert [finding["comment_id"] for finding in recovery_review["findings"]] == [
        4174293899,
        4174380757,
        4174380762,
    ]
    assert recovery_review["current_head_rereview_established"] is False
    recovery_observer = content_editing_recovery["check_evidence"][
        "independent_readback"
    ]
    assert recovery_observer["observer"] == "grosser-adler"
    assert recovery_observer["head"] == content_editing_recovery["functional_head"]
    assert recovery_observer["worktree_clean"] is True
    assert recovery_observer["untracked_present"] is False
    assert (
        "GitHub CI success on the recovery successor evidence head"
        in content_editing_recovery["does_not_establish"]
    )
    assert (
        "current-head Codex rereview settlement"
        in content_editing_recovery["does_not_establish"]
    )
    assert (
        "user visual acceptance or aesthetic approval of the recovery revision"
        in content_editing_recovery["does_not_establish"]
    )

    content_editing_form_submit = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_FORM_SUBMIT_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_form_submit["schema_version"]
        == "schauwerk-schaubild-content-editing-form-submit.v1"
    )
    assert (
        content_editing_form_submit["functional_head"]
        == "13de99b581e7fa820e1db5935674f9c881d08904"
    )
    assert content_editing_form_submit["parent_evidence"] == {
        "evidence_digest": content_editing_recovery["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_RECOVERY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-recovery-20261003/acceptance-receipt.json"
        ),
        "schema_version": content_editing_recovery["schema_version"],
    }
    assert content_editing_form_submit["evidence_digest"] == digest_mapping(
        content_editing_form_submit, "evidence_digest"
    )
    assert (
        set(content_editing_form_submit["source_bindings"])
        == content_editing_form_submit_superseded_files
    )
    for name, expected in content_editing_form_submit["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_valid_draft_recovery_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_form_submit["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "cancel_controls_are_non_submit_buttons": True,
        "form_submit_is_the_only_save_action": True,
        "implicit_form_submission_routes_to_save": True,
        "explicit_cancel_does_not_mutate_active_title": True,
        "submitted_title_rerenders_and_persists": True,
        "structural_edit_scope_unchanged": True,
        "recovery_and_layout_semantics_preserved": True,
        "focused_content_recovery_tests_passed": True,
        "relevant_regressions_passed": True,
        "browser_dom_form_contract_passed": True,
        "ruff_passed": True,
        "github_p2_finding_addressed_locally": True,
    }
    form_submit_focused = content_editing_form_submit["check_evidence"][
        "focused_content_recovery_tests"
    ]
    assert form_submit_focused == {
        "functional_head": content_editing_form_submit["functional_head"],
        "job_unit": "grabowski-job-cfecab65e86f",
        "argv_sha256": (
            "b5953f84c136f86fa89e5ac2cde0c35691dba3dd7b15e11cc792d2264ceaac91"
        ),
        "finalization_receipt_sha256": (
            "1021c97060f6c194d4cabde4c797d995e51ad379f3916d68110bd47b5c68660d"
        ),
        "passed_count": 3,
        "result": "passed",
    }
    form_submit_regressions = content_editing_form_submit["check_evidence"][
        "relevant_regressions"
    ]
    assert form_submit_regressions["functional_head"] == (
        content_editing_form_submit["functional_head"]
    )
    assert form_submit_regressions["job_unit"] == "grabowski-job-650fbbec3406"
    assert form_submit_regressions["argv_sha256"] == (
        "c0a631659d87aa204e6e066920528ae6c0a74a843f062e7aad9ee4fd82cf52e7"
    )
    assert form_submit_regressions["finalization_receipt_sha256"] == (
        "178bc6983ad081782b16b2cc205660c63c50b1efa2855124882bf5676e0f9ef3"
    )
    assert form_submit_regressions["passed_count"] == 362
    assert form_submit_regressions["result"] == "passed"
    form_submit_browser = content_editing_form_submit["check_evidence"][
        "browser_dom_form_contract"
    ]
    assert form_submit_browser["functional_head"] == (
        content_editing_form_submit["functional_head"]
    )
    assert form_submit_browser["job_unit"] == "grabowski-job-2ba8528a3c5a"
    assert form_submit_browser["argv_sha256"] == (
        "91d3ca38227df881961f1c8c56660e6dae9875ecebb315b8926cf232e76a7401"
    )
    assert form_submit_browser["finalization_receipt_sha256"] == (
        "8ca40af895093cebbfbfa1de5004d8267d700a04b204da92c709b7ec27c492f8"
    )
    assert form_submit_browser["native_render_post_count"] == 2
    assert form_submit_browser["result"] == "passed"
    form_submit_ruff = content_editing_form_submit["check_evidence"]["ruff"]
    assert form_submit_ruff["job_unit"] == "grabowski-job-26fcfe94bd6c"
    assert form_submit_ruff["argv_sha256"] == (
        "22a1ae3fc19fccb1103745ccee4d29b0ce9474af3fd43396c7b263d4f4de2220"
    )
    assert form_submit_ruff["finalization_receipt_sha256"] == (
        "edc22c46ebe1b835645d1655a848a53faf55e86345c6ac20a7785493ebfed5c8"
    )
    assert form_submit_ruff["result"] == "passed"
    form_submit_review = content_editing_form_submit["check_evidence"][
        "github_review_finding"
    ]
    assert form_submit_review["source_head"] == (
        "fbf5072ef2108f5c6637ecc906f7569cb4c963aa"
    )
    assert form_submit_review["addressed_by_functional_head"] == (
        content_editing_form_submit["functional_head"]
    )
    assert [finding["comment_id"] for finding in form_submit_review["findings"]] == [
        4174576979
    ]
    assert form_submit_review["current_head_rereview_established"] is False
    form_submit_observer = content_editing_form_submit["check_evidence"][
        "independent_readback"
    ]
    assert form_submit_observer["observer"] == "grosser-adler"
    assert (
        form_submit_observer["head"]
        == content_editing_form_submit["functional_head"]
    )
    assert form_submit_observer["worktree_clean"] is True
    assert form_submit_observer["untracked_present"] is False
    assert (
        "current-head Codex rereview settlement"
        in content_editing_form_submit["does_not_establish"]
    )
    assert (
        "user visual acceptance or aesthetic approval of the form-submit revision"
        in content_editing_form_submit["does_not_establish"]
    )

    content_editing_valid_draft_recovery = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_VALID_DRAFT_RECOVERY_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_valid_draft_recovery["schema_version"]
        == "schauwerk-schaubild-content-editing-valid-draft-recovery.v1"
    )
    assert (
        content_editing_valid_draft_recovery["functional_head"]
        == "b38786e132e15a1efa188a940f8a9fdfbf5cdbf4"
    )
    assert content_editing_valid_draft_recovery["parent_evidence"] == {
        "evidence_digest": content_editing_form_submit["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_FORM_SUBMIT_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-form-submit-20261003/acceptance-receipt.json"
        ),
        "schema_version": content_editing_form_submit["schema_version"],
    }
    assert content_editing_valid_draft_recovery["evidence_digest"] == digest_mapping(
        content_editing_valid_draft_recovery, "evidence_digest"
    )
    assert (
        set(content_editing_valid_draft_recovery["source_bindings"])
        == content_editing_valid_draft_recovery_superseded_files
    )
    for name, expected in content_editing_valid_draft_recovery["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_recovery_layout_reload_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_valid_draft_recovery["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "transient_candidate_retains_last_valid_representation": True,
        "transient_candidate_retains_last_valid_title": True,
        "invalid_recovery_restore_falls_back_once": True,
        "valid_fallback_is_revalidated_and_rerendered": True,
        "invalid_candidate_draft_replaced_by_valid_draft": True,
        "normal_successful_restore_behavior_preserved": True,
        "active_frame_retry_recovery_preserved": True,
        "layout_and_form_submit_semantics_preserved": True,
        "focused_recovery_tests_passed": True,
        "relevant_regressions_passed": True,
        "ruff_passed": True,
        "github_p2_finding_addressed_locally": True,
    }
    valid_draft_focused = content_editing_valid_draft_recovery["check_evidence"][
        "focused_recovery_tests"
    ]
    assert valid_draft_focused["job_unit"] == "grabowski-job-3d02019dc0c3"
    assert valid_draft_focused["argv_sha256"] == (
        "0141e08a56fd70d432d5aff8d47376ee8a302a5d6c0b9db7d443adba2fd34969"
    )
    assert valid_draft_focused["finalization_receipt_sha256"] == (
        "9c20360fc53feab57ecded6781985e6a49367fd0ec50398cc4d5d51e6a41a791"
    )
    assert valid_draft_focused["passed_count"] == 3
    assert valid_draft_focused["result"] == "passed"
    valid_draft_regressions = content_editing_valid_draft_recovery["check_evidence"][
        "relevant_regressions"
    ]
    assert valid_draft_regressions["job_unit"] == "grabowski-job-073cca4bb3b9"
    assert valid_draft_regressions["finalization_receipt_sha256"] == (
        "63665471935e3da3fb049cebfa4dbdfcf09422ae17f916e478dc633a0b01bf9a"
    )
    assert valid_draft_regressions["passed_count"] == 362
    assert valid_draft_regressions["result"] == "passed"
    valid_draft_review = content_editing_valid_draft_recovery["check_evidence"][
        "github_review_finding"
    ]
    assert valid_draft_review["source_head"] == (
        "8f23e87569ca0e8886b57e2c8b3e70021f8a93a9"
    )
    assert valid_draft_review["addressed_by_functional_head"] == (
        content_editing_valid_draft_recovery["functional_head"]
    )
    assert [finding["comment_id"] for finding in valid_draft_review["findings"]] == [
        4174922822
    ]
    assert valid_draft_review["current_head_rereview_established"] is False
    valid_draft_observer = content_editing_valid_draft_recovery["check_evidence"][
        "independent_readback"
    ]
    assert valid_draft_observer["observer"] == "grosser-adler"
    assert valid_draft_observer["head"] == (
        content_editing_valid_draft_recovery["functional_head"]
    )
    assert valid_draft_observer["worktree_clean"] is True
    assert valid_draft_observer["untracked_present"] is False

    content_editing_recovery_layout_reload = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_RECOVERY_LAYOUT_RELOAD_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_recovery_layout_reload["schema_version"]
        == "schauwerk-schaubild-content-editing-recovery-layout-reload.v1"
    )
    assert (
        content_editing_recovery_layout_reload["functional_head"]
        == "340f3fa77fa96e319fbdb9f1457ba2b2fe437c74"
    )
    assert content_editing_recovery_layout_reload["parent_evidence"] == {
        "evidence_digest": content_editing_valid_draft_recovery["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_VALID_DRAFT_RECOVERY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-valid-draft-recovery-20261003/"
            "acceptance-receipt.json"
        ),
        "schema_version": content_editing_valid_draft_recovery["schema_version"],
    }
    assert content_editing_recovery_layout_reload["evidence_digest"] == digest_mapping(
        content_editing_recovery_layout_reload, "evidence_digest"
    )
    assert (
        set(content_editing_recovery_layout_reload["source_bindings"])
        == content_editing_recovery_layout_reload_superseded_files
    )
    for name, expected in content_editing_recovery_layout_reload[
        "source_bindings"
    ].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_save_feedback_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_recovery_layout_reload["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "transient_recovery_draft_retains_valid_input_digest": True,
        "successful_reload_candidate_migrates_layout_from_valid_digest": True,
        "successful_reload_candidate_advances_native_input_digest": True,
        "same_session_layout_migration_preserved": True,
        "invalid_recovery_fallback_preserved": True,
        "json_canvas_recovery_contract_unchanged": True,
        "structural_edit_scope_unchanged": True,
        "focused_recovery_tests_passed": True,
        "relevant_regressions_passed": True,
        "ruff_passed": True,
        "git_diff_check_passed": True,
        "independent_p2_finding_addressed_locally": True,
    }
    recovery_layout_focused = content_editing_recovery_layout_reload[
        "check_evidence"
    ]["focused_recovery_tests"]
    assert recovery_layout_focused["job_unit"] == "grabowski-job-636e445eafa3"
    assert recovery_layout_focused["argv_sha256"] == (
        "9e76d3956c427a371fbd0306fb693eecc1a54c0188c618b9897ac0e0340c2ce7"
    )
    assert recovery_layout_focused["finalization_receipt_sha256"] == (
        "066483b8b84f2669fed06d45d381fe16d53dd922af70d58f72f8c277e1eb14c1"
    )
    assert recovery_layout_focused["passed_count"] == 5
    assert recovery_layout_focused["result"] == "passed"
    recovery_layout_regressions = content_editing_recovery_layout_reload[
        "check_evidence"
    ]["relevant_regressions"]
    assert recovery_layout_regressions["job_unit"] == "grabowski-job-4481d3468521"
    assert recovery_layout_regressions["argv_sha256"] == (
        "e6a1018f883e08bd0b0bdfd5cc7a18ea2aee61fe0c2b3c1f66cd006d04761fc5"
    )
    assert recovery_layout_regressions["finalization_receipt_sha256"] == (
        "ab7b1ed3902b28ba9a55cfba67c6a6ab0fabc6b11a951d3a3c2d7908e34150c1"
    )
    assert recovery_layout_regressions["passed_count"] == 362
    assert recovery_layout_regressions["result"] == "passed"
    recovery_layout_ruff = content_editing_recovery_layout_reload["check_evidence"][
        "ruff"
    ]
    assert recovery_layout_ruff["job_unit"] == "grabowski-job-dbe77daf6617"
    assert recovery_layout_ruff["argv_sha256"] == (
        "451517681a2225de1900b605bb560efb343589b5fd619b42b975053c64fc6b2a"
    )
    assert recovery_layout_ruff["finalization_receipt_sha256"] == (
        "c9ba81fa0a1f5864c5e1e1230b887f5f80c220b2a1d9119d601c8493d39bf908"
    )
    assert recovery_layout_ruff["result"] == "passed"
    recovery_layout_diff = content_editing_recovery_layout_reload["check_evidence"][
        "git_diff_check"
    ]
    assert recovery_layout_diff["argv_sha256"] == (
        "83179ff6b9b54026202766f61a37704b0dbf448f592a0d03818d10380194f454"
    )
    assert recovery_layout_diff["result"] == "passed"
    recovery_layout_review = content_editing_recovery_layout_reload[
        "check_evidence"
    ]["independent_review_finding"]
    assert recovery_layout_review["source_head"] == (
        "943c61a9ad2f5f3f4591ccbafdf1fb5e24499490"
    )
    assert recovery_layout_review["addressed_by_functional_head"] == (
        content_editing_recovery_layout_reload["functional_head"]
    )
    assert recovery_layout_review["job_unit"] == "grabowski-job-68519e4a85cb"
    assert recovery_layout_review["job_finalization_receipt_sha256"] == (
        "0efec4e4a78543da992f5a658a45d75fd5b586cd87ec6d0819633759c7329c84"
    )
    assert recovery_layout_review["role_receipt_sha256"] == (
        "c1194fd304641b0a7cf1aefa1311e8df27c97cf7ea75f4895d47f64cc8c5b180"
    )
    assert recovery_layout_review["finding"]["severity"] == "P2"
    assert recovery_layout_review["finding"]["path"] == (
        "src/schauwerk/resources/standalone_editor/assets.py"
    )
    assert recovery_layout_review["current_head_rereview_established"] is False
    recovery_layout_observer = content_editing_recovery_layout_reload[
        "check_evidence"
    ]["independent_readback"]
    assert recovery_layout_observer["observer"] == "grosser-adler"
    assert recovery_layout_observer["head"] == (
        content_editing_recovery_layout_reload["functional_head"]
    )
    assert recovery_layout_observer["worktree_clean"] is True
    assert recovery_layout_observer["untracked_present"] is False
    assert (
        "current-head independent rereview settlement"
        in content_editing_recovery_layout_reload["does_not_establish"]
    )

    content_editing_save_feedback = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_SAVE_FEEDBACK_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_save_feedback["schema_version"]
        == "schauwerk-schaubild-content-editing-save-feedback.v1"
    )
    assert (
        content_editing_save_feedback["functional_head"]
        == "a296fa03cc2d01c3eb90f95f8299ebe78daad9b1"
    )
    assert content_editing_save_feedback["parent_evidence"] == {
        "evidence_digest": content_editing_recovery_layout_reload["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_RECOVERY_LAYOUT_RELOAD_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-recovery-layout-reload-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": content_editing_recovery_layout_reload["schema_version"],
    }
    assert content_editing_save_feedback["evidence_digest"] == digest_mapping(
        content_editing_save_feedback, "evidence_digest"
    )
    assert (
        set(content_editing_save_feedback["source_bindings"])
        == content_editing_save_feedback_superseded_files
    )
    for name, expected in content_editing_save_feedback["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in content_editing_recovery_save_hardening_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_save_feedback["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "content_dialog_has_visible_role_alert_feedback": True,
        "server_required_content_fields_use_native_required_validation": True,
        "server_rejection_keeps_dialog_open_and_exposes_message": True,
        "transient_failure_keeps_dialog_open_and_exposes_message": True,
        "local_draft_failure_keeps_dialog_open": True,
        "local_draft_failure_preserves_unsaved_warning": True,
        "fully_persisted_save_closes_dialog": True,
        "escape_cancel_blocked_while_save_in_flight": True,
        "escape_cancel_restored_after_save": True,
        "launch_outcome_distinguishes_render_from_draft_persistence": True,
        "layout_and_recovery_semantics_preserved": True,
        "structural_edit_scope_unchanged": True,
        "focused_save_tests_passed": True,
        "relevant_regressions_passed": True,
        "ruff_passed": True,
        "git_diff_check_passed": True,
        "current_head_review_findings_addressed_locally": True,
    }
    save_feedback_focused = content_editing_save_feedback["check_evidence"][
        "focused_save_tests"
    ]
    assert save_feedback_focused["job_unit"] == "grabowski-job-a63b776701b3"
    assert save_feedback_focused["argv_sha256"] == (
        "002cc366adcc9008b3952c1de65371831d08eb4a3974c0829bd8c95674785d91"
    )
    assert save_feedback_focused["finalization_receipt_sha256"] == (
        "d8aab024dd2ad23235498b90c347d3cf77745f3154a98ceb5cbb83bac0b7d377"
    )
    assert save_feedback_focused["passed_count"] == 3
    assert save_feedback_focused["result"] == "passed"
    save_feedback_regressions = content_editing_save_feedback["check_evidence"][
        "relevant_regressions"
    ]
    assert save_feedback_regressions["job_unit"] == "grabowski-job-7b7b0dd044c0"
    assert save_feedback_regressions["argv_sha256"] == (
        "718d8d703096c2b8cc4298ccc89b8328c0cb83915bf0a50800df373a5c38aec7"
    )
    assert save_feedback_regressions["finalization_receipt_sha256"] == (
        "8ca563b698167aaa392a063752a359cc756558737d1a0e01e26791e2cf79d4fb"
    )
    assert save_feedback_regressions["result"] == "passed"
    save_feedback_ruff = content_editing_save_feedback["check_evidence"]["ruff"]
    assert save_feedback_ruff["job_unit"] == "grabowski-job-e25b30ba3932"
    assert save_feedback_ruff["argv_sha256"] == (
        "25a737880deaf478d726380c221b9eaa407f4aee0ab68c0f102be939f1f98ba7"
    )
    assert save_feedback_ruff["finalization_receipt_sha256"] == (
        "4c0c2b2e1556a9219ccf701422ad10dc7ab1a666cceab39809e61df999b9a3ca"
    )
    assert save_feedback_ruff["result"] == "passed"
    save_feedback_diff = content_editing_save_feedback["check_evidence"][
        "git_diff_check"
    ]
    assert save_feedback_diff["argv_sha256"] == (
        "1fc0f7e9a1d10b09e848b3f6cc5e99d8db617e87345068bfcc5c5752f1a6b6e7"
    )
    assert save_feedback_diff["result"] == "passed"
    save_feedback_github = content_editing_save_feedback["check_evidence"][
        "github_review_finding"
    ]
    assert save_feedback_github["source_head"] == (
        "c644ebceb125868fc7b7694dd6bb799bbcd22764"
    )
    assert save_feedback_github["addressed_by_functional_head"] == (
        content_editing_save_feedback["functional_head"]
    )
    assert save_feedback_github["review_id"] == 5403413131
    assert save_feedback_github["finding"]["comment_id"] == 4175355203
    assert save_feedback_github["finding"]["severity"] == "P2"
    assert save_feedback_github["current_head_rereview_established"] is False
    save_feedback_independent = content_editing_save_feedback["check_evidence"][
        "independent_review_findings"
    ]
    assert save_feedback_independent["source_head"] == (
        "c644ebceb125868fc7b7694dd6bb799bbcd22764"
    )
    assert save_feedback_independent["addressed_by_functional_head"] == (
        content_editing_save_feedback["functional_head"]
    )
    assert save_feedback_independent["job_unit"] == "grabowski-job-e98b85776cea"
    assert save_feedback_independent["job_finalization_receipt_sha256"] == (
        "eead9a100c912dbcb039015979dc42d4020664ccca65dbbff44ffd5bb178f33b"
    )
    assert save_feedback_independent["role_receipt_sha256"] == (
        "e30fc35a98d6b86e31488229d871bb9911e0d73635475edd23592879525d72db"
    )
    assert [finding["severity"] for finding in save_feedback_independent["findings"]] == [
        "P2",
        "P3",
    ]
    assert save_feedback_independent["current_head_rereview_established"] is False
    save_feedback_observer = content_editing_save_feedback["check_evidence"][
        "independent_readback"
    ]
    assert save_feedback_observer["observer"] == "grosser-adler"
    assert save_feedback_observer["head"] == (
        content_editing_save_feedback["functional_head"]
    )
    assert save_feedback_observer["worktree_clean"] is True
    assert save_feedback_observer["untracked_present"] is False
    assert (
        "current-head independent rereview settlement"
        in content_editing_save_feedback["does_not_establish"]
    )

    content_editing_recovery_save_hardening = json.loads(
        (
            SCHAUBILD_CONTENT_EDITING_RECOVERY_SAVE_HARDENING_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        content_editing_recovery_save_hardening["schema_version"]
        == "schauwerk-schaubild-content-editing-recovery-save-hardening.v1"
    )
    assert (
        content_editing_recovery_save_hardening["functional_head"]
        == "ae91b379f55a27ba05e6765425729eec8cd8ab3d"
    )
    assert content_editing_recovery_save_hardening["parent_evidence"] == {
        "evidence_digest": content_editing_save_feedback["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_SAVE_FEEDBACK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-save-feedback-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": content_editing_save_feedback["schema_version"],
    }
    assert content_editing_recovery_save_hardening["evidence_digest"] == digest_mapping(
        content_editing_recovery_save_hardening, "evidence_digest"
    )
    assert (
        set(content_editing_recovery_save_hardening["source_bindings"])
        == content_editing_recovery_save_hardening_superseded_files
    )
    for name, expected in content_editing_recovery_save_hardening[
        "source_bindings"
    ].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            focus_default_superseded_files
            | focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert content_editing_recovery_save_hardening["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "combined_render_and_local_draft_failure_exposes_persistence_loss": True,
        "combined_failure_launch_outcome_binds_draft_saved_false": True,
        "layout_reset_clears_stale_target_digest_overrides": True,
        "content_fields_are_inert_while_save_is_in_flight": True,
        "content_fields_are_reenabled_after_save": True,
        "content_dialog_feedback_contract_preserved": True,
        "server_validation_remains_authoritative": True,
        "layout_and_recovery_semantics_preserved": True,
        "structural_edit_scope_unchanged": True,
        "focused_hardening_tests_passed": True,
        "relevant_regressions_passed": True,
        "ruff_passed": True,
        "git_diff_check_passed": True,
        "exact_head_independent_findings_addressed_locally": True,
    }
    hardening_focused = content_editing_recovery_save_hardening["check_evidence"][
        "focused_hardening_tests"
    ]
    assert hardening_focused["job_unit"] == "grabowski-job-8b16a49c2254"
    assert hardening_focused["argv_sha256"] == (
        "d497d73d9aa272647ac05aa2bff523ca46f9ee2c249a7945560e68ddd2f1895b"
    )
    assert hardening_focused["finalization_receipt_sha256"] == (
        "daa181494fcd1ec9fc882a6805a43c2fe4515ba4ab5324b199c2cf44d75cb621"
    )
    assert hardening_focused["passed_count"] == 3
    assert hardening_focused["result"] == "passed"
    hardening_regressions = content_editing_recovery_save_hardening["check_evidence"][
        "relevant_regressions"
    ]
    assert hardening_regressions["job_unit"] == "grabowski-job-626a18625785"
    assert hardening_regressions["argv_sha256"] == (
        "56a11f0dd53d491170156730b4dd92419811e4dd1c22ef951b6655076b97f7cd"
    )
    assert hardening_regressions["finalization_receipt_sha256"] == (
        "7496a344c5428b2c0c72573d296722458ba2354dc1634beff69d4030b19efc62"
    )
    assert hardening_regressions["result"] == "passed"
    hardening_ruff = content_editing_recovery_save_hardening["check_evidence"]["ruff"]
    assert hardening_ruff["job_unit"] == "grabowski-job-03b4f886f2f4"
    assert hardening_ruff["argv_sha256"] == (
        "afba15ce35a0f9747ba46bbf213025cd2ff55e6f6642940ada8ed1cdb4a4db8b"
    )
    assert hardening_ruff["finalization_receipt_sha256"] == (
        "43ce8646b864cb062036b9ab5abe579851060ae28d6fdb7fa6af61bf1635e261"
    )
    assert hardening_ruff["result"] == "passed"
    hardening_diff = content_editing_recovery_save_hardening["check_evidence"][
        "git_diff_check"
    ]
    assert hardening_diff["argv_sha256"] == (
        "88f60d1fe46f92cfd100e440f36ce27980a18144d707a71c2b67193157b583d4"
    )
    assert hardening_diff["result"] == "passed"
    hardening_codex = content_editing_recovery_save_hardening["check_evidence"][
        "independent_codex_finding"
    ]
    assert hardening_codex["source_head"] == (
        "cda2a303824da71128b8885308726ad52df7d5af"
    )
    assert hardening_codex["addressed_by_functional_head"] == (
        content_editing_recovery_save_hardening["functional_head"]
    )
    assert hardening_codex["job_unit"] == "grabowski-job-887b30e2fed3"
    assert hardening_codex["job_finalization_receipt_sha256"] == (
        "13adf47216bccd6b54f5832ecd78f2fdc3e9ebfe5f4a115c2386d26d76a7d624"
    )
    assert hardening_codex["role_receipt_sha256"] == (
        "c27946dcf4be9dcb485b994a1a617c161165a94abf24b52500441fa3a7a52f02"
    )
    assert hardening_codex["finding"]["severity"] == "P2"
    assert hardening_codex["current_head_rereview_established"] is False
    hardening_claude = content_editing_recovery_save_hardening["check_evidence"][
        "independent_claude_findings"
    ]
    assert hardening_claude["source_head"] == (
        "cda2a303824da71128b8885308726ad52df7d5af"
    )
    assert hardening_claude["addressed_by_functional_head"] == (
        content_editing_recovery_save_hardening["functional_head"]
    )
    assert hardening_claude["job_unit"] == "grabowski-job-272917de5165"
    assert hardening_claude["job_finalization_receipt_sha256"] == (
        "c9ba78a20f9ec84e2ccb182c2116e63e1050f47d11ce7f7d4aa14dc3c72855ea"
    )
    assert hardening_claude["role_receipt_sha256"] == (
        "41b7d7578afc3bccf90021dca3e98d01adac8f7ece1266c978efaa731f60cd9f"
    )
    assert [finding["id"] for finding in hardening_claude["findings"]] == ["F1", "F2"]
    assert hardening_claude["current_head_rereview_established"] is False
    hardening_observer = content_editing_recovery_save_hardening["check_evidence"][
        "independent_readback"
    ]
    assert hardening_observer["observer"] == "grosser-adler"
    assert hardening_observer["head"] == (
        content_editing_recovery_save_hardening["functional_head"]
    )
    assert hardening_observer["worktree_clean"] is True
    assert hardening_observer["untracked_present"] is False
    assert (
        "current-head independent rereview settlement"
        in content_editing_recovery_save_hardening["does_not_establish"]
    )

    focus_default = json.loads(
        (SCHAUBILD_FOCUS_DEFAULT_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert focus_default["schema_version"] == "schauwerk-schaubild-focus-default.v1"
    assert focus_default["functional_head"] == "10436f06b8216a8930f5f0c16e2b8c7b8592e2c4"
    assert focus_default["parent_evidence"] == {
        "evidence_digest": content_editing_recovery_save_hardening["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_CONTENT_EDITING_RECOVERY_SAVE_HARDENING_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-content-editing-recovery-save-hardening-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": content_editing_recovery_save_hardening["schema_version"],
    }
    assert focus_default["evidence_digest"] == digest_mapping(
        focus_default, "evidence_digest"
    )
    assert set(focus_default["source_bindings"]) == focus_default_superseded_files
    for name, expected in focus_default["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in (
            focus_default_review_fix_superseded_files
            | single_workspace_exports_superseded_files
        ):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert focus_default["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "focus_mode_default_on_workspace_entry": True,
        "explicit_focus_exit_not_overridden_by_internal_rerender": True,
        "focus_stage_vertical_gutter_removed": True,
        "close_control_remains_visible_overlay": True,
        "hosted_native_toolbar_reserves_close_overlay_width": True,
        "exact_head_relevant_visual_regressions_passed": True,
        "exact_head_visual_readback_passed": True,
        "pre_successor_full_validate_failed_only_on_binding_gate": True,
        "publication_successor_binding_added": True,
    }
    focus_visual_regressions = focus_default["check_evidence"][
        "relevant_visual_regressions"
    ]
    assert focus_visual_regressions["functional_head"] == focus_default["functional_head"]
    assert focus_visual_regressions["task_id"] == "851799a745ac4a3e95e727ba"
    assert focus_visual_regressions["outcome_receipt_sha256"] == (
        "65260b0ab7ef09a81ee0ac8afa2fc87f103d6296c2841772d35ffa46d251ff90"
    )
    assert focus_visual_regressions["result"] == "passed"
    focus_visual_readback = focus_default["check_evidence"]["visual_readback"]
    assert focus_visual_readback["functional_head"] == focus_default["functional_head"]
    assert focus_visual_readback["task_id"] == "abd527f3698f458c80060221"
    assert focus_visual_readback["screenshot_sha256"] == (
        "877add2d3114a29df62d59c42d78c6d583922a387310ec62f4041a661ddaba58"
    )
    assert focus_visual_readback["observations"] == {
        "vertical_focus_gutter_present": False,
        "close_control_visible_top_right": True,
        "native_toolbar_visible": True,
        "workspace_uses_full_height": True,
    }
    assert focus_visual_readback["result"] == "passed"
    focus_pre_successor = focus_default["check_evidence"]["pre_successor_full_validate"]
    assert focus_pre_successor["functional_head"] == focus_default["functional_head"]
    assert focus_pre_successor["task_id"] == "b5d510f4b2b6450d92200cb7"
    assert focus_pre_successor["passed_count"] == 1653
    assert focus_pre_successor["failed_count"] == 1
    assert focus_pre_successor["failure_class"] == "expected_successor_binding_gate"
    assert (
        "user visual acceptance or aesthetic approval of this revision"
        in focus_default["does_not_establish"]
    )
    assert "independent review or reviewer settlement" in focus_default["does_not_establish"]

    focus_default_review_fix = json.loads(
        (
            SCHAUBILD_FOCUS_DEFAULT_REVIEW_FIX_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        focus_default_review_fix["schema_version"]
        == "schauwerk-schaubild-focus-default-review-fixes.v1"
    )
    assert (
        focus_default_review_fix["functional_head"]
        == "6c693670d050907856e2988e6018420aaa0d3b64"
    )
    assert focus_default_review_fix["parent_evidence"] == {
        "evidence_digest": focus_default["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_FOCUS_DEFAULT_EVIDENCE / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-focus-default-20261004/acceptance-receipt.json"
        ),
        "schema_version": focus_default["schema_version"],
    }
    assert focus_default_review_fix["evidence_digest"] == digest_mapping(
        focus_default_review_fix, "evidence_digest"
    )
    assert (
        set(focus_default_review_fix["source_bindings"])
        == focus_default_review_fix_superseded_files
    )
    for name, expected in focus_default_review_fix["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in single_workspace_exports_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert focus_default_review_fix["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "current_pr_p2_findings_reproduced_and_addressed": True,
        "canonical_embedded_native_toolbar_reserves_close_overlay_width": True,
        "legacy_focus_toolbar_kept_clear_without_top_height_gutter": True,
        "legacy_focus_hides_redundant_host_font_controls": True,
        "post_product_change_is_test_contract_only": True,
        "relevant_visual_regressions_passed": True,
        "native_canonical_browser_readback_passed": True,
        "legacy_browser_readback_passed": True,
        "exact_head_full_validate_failed_only_on_successor_binding_gate": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    review_findings = focus_default_review_fix["check_evidence"]["github_review_findings"]
    assert review_findings["pull_request"] == 201
    assert review_findings["review_id"] == 5405057099
    assert review_findings["source_head"] == "10436f06b8216a8930f5f0c16e2b8c7b8592e2c4"
    assert review_findings["addressed_by_product_fix_head"] == (
        focus_default_review_fix["product_fix_head"]
    )
    assert [finding["comment_id"] for finding in review_findings["findings"]] == [
        4176769631,
        4176769635,
    ]
    assert review_findings["current_head_rereview_established"] is False
    native_readback = focus_default_review_fix["check_evidence"][
        "native_canonical_browser_readback"
    ]
    assert native_readback["task_id"] == "e2289e8c5fe1410e93191a45"
    assert native_readback["result"] == "passed"
    assert native_readback["metrics"]["toolbar_padding_right_px"] == 58.0
    assert native_readback["metrics"]["controls_right_px"] <= (
        native_readback["metrics"]["toolbar_right_px"] - 50.0
    )
    legacy_readback = focus_default_review_fix["check_evidence"][
        "legacy_browser_readback"
    ]
    assert legacy_readback["task_id"] == "9b5ecba41cfb4dcdb9acf9d6"
    assert legacy_readback["result"] == "passed"
    assert legacy_readback["metrics"]["editor_frame_top_px"] == 0.0
    assert legacy_readback["metrics"]["editor_frame_right_px"] < (
        legacy_readback["metrics"]["close_left_px"]
    )
    assert legacy_readback["metrics"]["host_font_controls_display"] == "none"
    pre_successor = focus_default_review_fix["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert pre_successor["functional_head"] == focus_default_review_fix["functional_head"]
    assert pre_successor["task_id"] == "cff48fcadcee41efb95f5466"
    assert pre_successor["passed_count"] == 1653
    assert pre_successor["failed_count"] == 1
    assert pre_successor["failure_class"] == "expected_successor_binding_gate"
    assert (
        "current-head GitHub reviewer settlement after the two recorded P2 findings"
        in focus_default_review_fix["does_not_establish"]
    )
    assert (
        "independent review of the review-fix revision"
        in focus_default_review_fix["does_not_establish"]
    )

    single_workspace_exports = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_EXPORTS_EVIDENCE / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_exports["schema_version"]
        == "schauwerk-schaubild-single-workspace-exports.v1"
    )
    assert (
        single_workspace_exports["functional_head"]
        == "896f34348da2e15489b0155d12661bdfe01c0b5e"
    )
    assert single_workspace_exports["parent_evidence"] == {
        "evidence_digest": focus_default_review_fix["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_FOCUS_DEFAULT_REVIEW_FIX_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-focus-default-review-fixes-20261004/acceptance-receipt.json"
        ),
        "schema_version": focus_default_review_fix["schema_version"],
    }
    assert single_workspace_exports["evidence_digest"] == digest_mapping(
        single_workspace_exports, "evidence_digest"
    )
    assert (
        set(single_workspace_exports["source_bindings"])
        == single_workspace_exports_superseded_files
    )
    for name, expected in single_workspace_exports["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in single_workspace_review_fix_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_exports["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "compact_workspace_removed": True,
        "single_full_height_workspace_only": True,
        "exports_available_in_full_workspace": True,
        "close_control_is_separate_top_right_overlay": True,
        "native_export_dock_clears_bottom_status_bar": True,
        "exact_head_focused_visual_regressions_passed": True,
        "exact_head_native_browser_readback_passed": True,
        "exact_head_full_validate_failed_only_on_successor_binding_gate": True,
        "independent_observer_readback_passed": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    single_workspace_focused = single_workspace_exports["check_evidence"][
        "focused_visual_regressions"
    ]
    assert single_workspace_focused["functional_head"] == (
        single_workspace_exports["functional_head"]
    )
    assert single_workspace_focused["job_id"] == "26cbea2a092a"
    assert single_workspace_focused["passed_count"] == 128
    assert single_workspace_focused["result"] == "passed"
    single_workspace_readback = single_workspace_exports["check_evidence"][
        "native_browser_readback"
    ]
    assert single_workspace_readback["functional_head"] == (
        single_workspace_exports["functional_head"]
    )
    assert single_workspace_readback["job_id"] == "05fb9c0187ff"
    assert single_workspace_readback["screenshot_sha256"] == (
        "b7b0f2ee18730eb3d4f638b6d652f4e25d82905be24f9ab3d37f4338243d6a71"
    )
    assert single_workspace_readback["metrics"]["frame"] == {
        "x": 0,
        "y": 0,
        "width": 1366,
        "height": 1024,
        "right": 1366,
        "bottom": 1024,
    }
    assert single_workspace_readback["metrics"]["export_dock"]["bottom"] == 980
    assert single_workspace_readback["metrics"]["bottom_status_clearance_px"] == 44
    assert single_workspace_readback["metrics"]["visible_host_controls"] == [
        "Inhalt",
        "Quelle",
        "SVG",
    ]
    assert single_workspace_readback["result"] == "passed"
    single_workspace_pre_successor = single_workspace_exports["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert single_workspace_pre_successor["passed_count"] == 1653
    assert single_workspace_pre_successor["failed_count"] == 1
    assert (
        single_workspace_pre_successor["failure_class"]
        == "expected_successor_binding_gate"
    )
    single_workspace_observer = single_workspace_exports["check_evidence"][
        "independent_observer_readback"
    ]
    assert single_workspace_observer["observer"] == "grosser-adler"
    assert single_workspace_observer["functional_head"] == (
        single_workspace_exports["functional_head"]
    )
    assert single_workspace_observer["worktree_clean"] is True
    assert single_workspace_observer["untracked_present"] is False
    assert single_workspace_observer["finding_count"] == 0
    assert single_workspace_observer["result"] == "passed"
    single_workspace_diff = single_workspace_exports["check_evidence"]["git_diff_check"]
    assert single_workspace_diff["diff_sha256"] == (
        "f19ad1210e3495bc0f0302f216613454268abf6efcf41824aff1f0c2dc6fe010"
    )
    assert single_workspace_diff["result"] == "passed"
    assert (
        "independent review or reviewer settlement"
        in single_workspace_exports["does_not_establish"]
    )

    single_workspace_review_fix = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_REVIEW_FIX_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_review_fix["schema_version"]
        == "schauwerk-schaubild-single-workspace-review-fixes.v1"
    )
    assert (
        single_workspace_review_fix["functional_head"]
        == "81ae81e2b196b605aa07dbf81329147f449008da"
    )
    assert single_workspace_review_fix["parent_evidence"] == {
        "evidence_digest": single_workspace_exports["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_EXPORTS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-exports-20261004/acceptance-receipt.json"
        ),
        "schema_version": single_workspace_exports["schema_version"],
    }
    assert single_workspace_review_fix["evidence_digest"] == digest_mapping(
        single_workspace_review_fix, "evidence_digest"
    )
    assert (
        set(single_workspace_review_fix["source_bindings"])
        == single_workspace_review_fix_superseded_files
    )
    for name, expected in single_workspace_review_fix["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in single_workspace_mobile_status_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_review_fix["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "advisory_review_findings_reproduced_and_addressed": True,
        "legacy_close_overlay_clears_embedded_editor": True,
        "legacy_export_dock_clears_embedded_editor": True,
        "legacy_redundant_host_edit_controls_hidden": True,
        "workspace_status_visible_in_legacy_mode": True,
        "workspace_status_visible_in_native_mode": True,
        "native_full_height_workspace_preserved": True,
        "exact_head_focused_regressions_passed": True,
        "exact_head_legacy_browser_readback_passed": True,
        "exact_head_native_browser_readback_passed": True,
        "pre_successor_full_validate_failed_only_on_binding_gate": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    review_fix_findings = single_workspace_review_fix["check_evidence"][
        "advisory_review_findings"
    ]
    assert review_fix_findings["source_head"] == (
        "e568c49117dba012ea12116517c2d252c2ce941d"
    )
    assert review_fix_findings["addressed_by_functional_head"] == (
        single_workspace_review_fix["functional_head"]
    )
    assert review_fix_findings["structured_decision_review_valid"] is False
    assert [finding["id"] for finding in review_fix_findings["findings"]] == [
        "F1",
        "F2",
    ]
    focused = single_workspace_review_fix["check_evidence"]["focused_regressions"]
    assert focused["job_id"] == "922084aab5b3"
    assert focused["passed_count"] == 128
    assert focused["result"] == "passed"
    legacy = single_workspace_review_fix["check_evidence"]["legacy_browser_readback"]
    assert legacy["job_id"] == "2bc59770ed54"
    assert legacy["screenshot_sha256"] == (
        "323a1051018e50377f017b0793ba22b35a995aac6873e18dc003102a893d9797"
    )
    assert legacy["metrics"]["no_close_overlap"] is True
    assert legacy["metrics"]["no_dock_overlap"] is True
    assert legacy["metrics"]["status_visible"] is True
    assert legacy["metrics"]["visible_host_controls"] == ["Projekt", "PNG", "SVG"]
    assert legacy["result"] == "passed"
    native = single_workspace_review_fix["check_evidence"]["native_browser_readback"]
    assert native["job_id"] == "fc98033a9693"
    assert native["screenshot_sha256"] == (
        "c3ff0aa51429cca4a2c285199170466d71f1067074a53f709341ac4b62cdf79c"
    )
    assert native["metrics"]["frame"] == {
        "x": 0,
        "y": 0,
        "width": 1366,
        "height": 1024,
        "right": 1366,
        "bottom": 1024,
    }
    assert native["metrics"]["status_visible"] is True
    assert native["result"] == "passed"
    pre_successor = single_workspace_review_fix["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert pre_successor["passed_count"] == 1653
    assert pre_successor["failed_count"] == 1
    assert pre_successor["failure_class"] == "expected_successor_binding_gate"
    review_fix_diff = single_workspace_review_fix["check_evidence"]["git_diff_check"]
    assert review_fix_diff["diff_sha256"] == (
        "5e20f112b880cd37f13fa2dadbaf3b288ce9111b3ff0b5159098113016497415"
    )
    assert review_fix_diff["result"] == "passed"
    assert (
        "decision-bound independent reviewer settlement on the review-fix revision"
        in single_workspace_review_fix["does_not_establish"]
    )

    single_workspace_mobile_status = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_MOBILE_STATUS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_mobile_status["schema_version"]
        == "schauwerk-schaubild-single-workspace-mobile-status.v1"
    )
    assert (
        single_workspace_mobile_status["functional_head"]
        == "adc16745e90d9b0b90d96080cbf059f672092794"
    )
    assert single_workspace_mobile_status["parent_evidence"] == {
        "evidence_digest": single_workspace_review_fix["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_REVIEW_FIX_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-review-fixes-20261004/acceptance-receipt.json"
        ),
        "schema_version": single_workspace_review_fix["schema_version"],
    }
    assert single_workspace_mobile_status["evidence_digest"] == digest_mapping(
        single_workspace_mobile_status, "evidence_digest"
    )
    assert (
        set(single_workspace_mobile_status["source_bindings"])
        == single_workspace_mobile_status_superseded_files
    )
    for name, expected in single_workspace_mobile_status["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in single_workspace_wrapped_dock_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_mobile_status["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "current_head_p2_reproduced_and_addressed": True,
        "decision_bound_review_finding_reproduced_and_addressed": True,
        "mobile_status_clears_full_width_dock_native": True,
        "mobile_status_clears_full_width_dock_legacy": True,
        "native_full_height_workspace_preserved": True,
        "legacy_close_and_dock_clearances_preserved": True,
        "exact_head_focused_regressions_passed": True,
        "exact_head_mobile_native_browser_readback_passed": True,
        "exact_head_mobile_legacy_browser_readback_passed": True,
        "pre_successor_full_validate_failed_only_on_binding_gate": True,
        "independent_observer_readback_passed": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    mobile_findings = single_workspace_mobile_status["check_evidence"][
        "review_findings"
    ]
    assert mobile_findings["source_head"] == (
        "d6af3079cc393bc2e723b3eb06593dde6f9935f4"
    )
    assert mobile_findings["github_codex"]["comment_id"] == 4178041831
    assert mobile_findings["github_codex"]["severity"] == "P2"
    assert mobile_findings["decision_bound_grok"]["job_id"] == "6070e07c4fe9"
    assert mobile_findings["decision_bound_grok"]["verdict"] == "NEEDS_CHANGE"
    assert mobile_findings["decision_bound_grok"]["finding_id"] == "F1"
    assert mobile_findings["addressed_by_functional_head"] == (
        single_workspace_mobile_status["functional_head"]
    )
    mobile_focused = single_workspace_mobile_status["check_evidence"][
        "focused_regressions"
    ]
    assert mobile_focused["job_id"] == "e164df021296"
    assert mobile_focused["passed_count"] == 128
    assert mobile_focused["result"] == "passed"
    mobile_legacy = single_workspace_mobile_status["check_evidence"][
        "mobile_legacy_browser_readback"
    ]
    assert mobile_legacy["job_id"] == "c32ad1e889b1"
    assert mobile_legacy["viewport"] == {"width": 760, "height": 900}
    assert mobile_legacy["metrics"]["status_clears_dock"] is True
    assert mobile_legacy["metrics"]["frame_clears_dock"] is True
    assert mobile_legacy["metrics"]["frame_clears_close"] is True
    assert mobile_legacy["metrics"]["visible_host_controls"] == [
        "Projekt",
        "PNG",
        "SVG",
    ]
    assert mobile_legacy["screenshot_sha256"] == (
        "fb6f144cb25f09739dc20e6eece61cef86effb3e137a1b1a156fb854276529ed"
    )
    assert mobile_legacy["result"] == "passed"
    mobile_native = single_workspace_mobile_status["check_evidence"][
        "mobile_native_browser_readback"
    ]
    assert mobile_native["job_id"] == "e59161b84632"
    assert mobile_native["viewport"] == {"width": 760, "height": 900}
    assert mobile_native["metrics"]["frame"] == {
        "x": 0,
        "y": 0,
        "width": 760,
        "height": 900,
        "right": 760,
        "bottom": 900,
    }
    assert mobile_native["metrics"]["status_clears_dock"] is True
    assert mobile_native["metrics"]["visible_host_controls"] == [
        "Inhalt",
        "Quelle",
        "SVG",
    ]
    assert mobile_native["screenshot_sha256"] == (
        "00aa39eb455ed8e03ab84b1adc19a43fa503f20f86d72afcaad5ac6a4740fb77"
    )
    assert mobile_native["result"] == "passed"
    mobile_pre_successor = single_workspace_mobile_status["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert mobile_pre_successor["passed_count"] == 1653
    assert mobile_pre_successor["failed_count"] == 1
    assert (
        mobile_pre_successor["failure_class"]
        == "expected_successor_binding_gate"
    )
    mobile_observer = single_workspace_mobile_status["check_evidence"][
        "independent_observer_readback"
    ]
    assert mobile_observer["observer"] == "grosser-adler"
    assert mobile_observer["functional_head"] == (
        single_workspace_mobile_status["functional_head"]
    )
    assert mobile_observer["finding_count"] == 0
    assert mobile_observer["projection_complete"] is True
    assert mobile_observer["result"] == "passed"
    mobile_diff = single_workspace_mobile_status["check_evidence"]["git_diff_check"]
    assert mobile_diff["diff_sha256"] == (
        "cb4d60299e491b380d73a00098ed8415ce92bf9ed9c0133a300a7773332f9469"
    )
    assert mobile_diff["result"] == "passed"
    assert (
        "decision-bound independent reviewer PASS on the mobile-status successor revision"
        in single_workspace_mobile_status["does_not_establish"]
    )

    single_workspace_wrapped_dock = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_WRAPPED_DOCK_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_wrapped_dock["schema_version"]
        == "schauwerk-schaubild-single-workspace-wrapped-dock.v1"
    )
    assert (
        single_workspace_wrapped_dock["functional_head"]
        == "0fbd1e5373fd79c388b28756001de2c16b76b7a3"
    )
    assert single_workspace_wrapped_dock["parent_evidence"] == {
        "evidence_digest": single_workspace_mobile_status["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_MOBILE_STATUS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-mobile-status-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": single_workspace_mobile_status["schema_version"],
    }
    assert single_workspace_wrapped_dock["evidence_digest"] == digest_mapping(
        single_workspace_wrapped_dock, "evidence_digest"
    )
    assert (
        set(single_workspace_wrapped_dock["source_bindings"])
        == single_workspace_wrapped_dock_superseded_files
    )
    for name, expected in single_workspace_wrapped_dock["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        if name not in single_workspace_dark_status_superseded_files:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_wrapped_dock["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "current_head_review_threads_reproduced_and_addressed": True,
        "wrapped_download_state_reproduced_at_320px": True,
        "runtime_dock_height_tracks_actual_layout": True,
        "mobile_status_clears_wrapped_dock_native": True,
        "mobile_status_clears_wrapped_dock_legacy": True,
        "legacy_editor_reserves_wrapped_dock_height": True,
        "native_full_height_workspace_preserved": True,
        "exact_head_focused_regressions_passed": True,
        "exact_head_browser_readbacks_passed": True,
        "pre_successor_full_validate_failed_only_on_binding_gate": True,
        "independent_observer_readback_passed": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    wrapped_findings = single_workspace_wrapped_dock["check_evidence"]["review_findings"]
    assert wrapped_findings["source_head"] == (
        "4d49b1c925d00a7edccc0804bd9636c0af1be4b0"
    )
    assert [
        finding["comment_id"] for finding in wrapped_findings["github_codex"]
    ] == [4178041831, 4178200305]
    wrapped_reproduction = wrapped_findings["pre_fix_reproduction"]
    assert wrapped_reproduction["job_id"] == "ddc5a6b6c740"
    assert wrapped_reproduction["viewport"] == {"width": 320, "height": 740}
    assert wrapped_reproduction["dock_height_px"] == 102
    assert wrapped_reproduction["status_dock_overlap_px"] == 28
    assert wrapped_reproduction["result"] == "reproduced"
    assert wrapped_findings["addressed_by_functional_head"] == (
        single_workspace_wrapped_dock["functional_head"]
    )

    wrapped_focused = single_workspace_wrapped_dock["check_evidence"][
        "focused_regressions"
    ]
    assert wrapped_focused["functional_head"] == (
        single_workspace_wrapped_dock["functional_head"]
    )
    assert wrapped_focused["job_id"] == "dbabb954d081"
    assert wrapped_focused["passed_count"] == 130
    assert wrapped_focused["result"] == "passed"

    wrapped_browser = single_workspace_wrapped_dock["check_evidence"][
        "browser_readbacks"
    ]
    assert wrapped_browser["job_id"] == "f90025a3a24f"
    assert wrapped_browser["result"] == "passed"
    for state in ("native_320", "native_760", "legacy_320", "legacy_760"):
        assert wrapped_browser["states"][state]["status_clears_dock"] is True
        assert wrapped_browser["states"][state]["status_dock_overlap_px"] == 0
    assert wrapped_browser["states"]["native_320"]["dock"]["height"] == 102
    assert wrapped_browser["states"]["native_320"]["dock_height_css"] == "102px"
    assert wrapped_browser["states"]["native_320"]["download_label"] == "Quelle speichern"
    assert wrapped_browser["states"]["legacy_320"]["dock"]["height"] == 101
    assert wrapped_browser["states"]["legacy_320"]["dock_height_css"] == "101px"
    assert wrapped_browser["states"]["legacy_320"]["download_label"] == "Projekt speichern"
    assert wrapped_browser["states"]["legacy_320"]["frame_clears_dock"] is True
    assert wrapped_browser["states"]["legacy_320"]["frame_clears_close"] is True
    assert wrapped_browser["states"]["legacy_760"]["frame_clears_dock"] is True
    assert wrapped_browser["states"]["legacy_760"]["frame_clears_close"] is True

    wrapped_pre_successor = single_workspace_wrapped_dock["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert wrapped_pre_successor["job_id"] == "6ac8e7353627"
    assert wrapped_pre_successor["passed_count"] == 1655
    assert wrapped_pre_successor["failed_count"] == 1
    assert (
        wrapped_pre_successor["failure_class"]
        == "expected_successor_binding_gate"
    )
    wrapped_observer = single_workspace_wrapped_dock["check_evidence"][
        "independent_observer_readback"
    ]
    assert wrapped_observer["observer"] == "grosser-adler"
    assert wrapped_observer["functional_head"] == (
        single_workspace_wrapped_dock["functional_head"]
    )
    assert wrapped_observer["worktree_clean"] is True
    assert wrapped_observer["untracked_present"] is False
    assert wrapped_observer["finding_count"] == 0
    assert wrapped_observer["projection_complete"] is True
    assert wrapped_observer["result"] == "passed"
    wrapped_diff = single_workspace_wrapped_dock["check_evidence"]["git_diff_check"]
    assert wrapped_diff["base_sha"] == "4d49b1c925d00a7edccc0804bd9636c0af1be4b0"
    assert wrapped_diff["head_sha"] == (
        single_workspace_wrapped_dock["functional_head"]
    )
    assert wrapped_diff["diff_sha256"] == (
        "70b101cd60a76cf619b4345945cfa5b9f9e5415724808b8bfd3d007d0f962af8"
    )
    assert wrapped_diff["result"] == "passed"
    assert (
        "decision-bound independent reviewer PASS on the later successor-evidence head"
        in single_workspace_wrapped_dock["does_not_establish"]
    )

    single_workspace_dark_status = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_DARK_STATUS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_dark_status["schema_version"]
        == "schauwerk-schaubild-single-workspace-dark-status.v1"
    )
    assert (
        single_workspace_dark_status["functional_head"]
        == "1cefe05c2c46af180b024cb32bf2cccef10d7397"
    )
    assert single_workspace_dark_status["parent_evidence"] == {
        "evidence_digest": single_workspace_wrapped_dock["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_WRAPPED_DOCK_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-wrapped-dock-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": single_workspace_wrapped_dock["schema_version"],
    }
    assert single_workspace_dark_status["evidence_digest"] == digest_mapping(
        single_workspace_dark_status, "evidence_digest"
    )
    assert (
        set(single_workspace_dark_status["source_bindings"])
        == single_workspace_dark_status_superseded_files
    )
    for name, expected in single_workspace_dark_status["source_bindings"].items():
        if name in single_workspace_max_canvas_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_dark_status["checks"] == {
        "historical_parent_acceptance_left_immutable": True,
        "current_head_dark_mode_p2_reproduced_and_addressed": True,
        "mobile_dark_status_uses_dark_surface_native": True,
        "mobile_dark_status_uses_dark_surface_legacy": True,
        "mobile_dark_status_uses_high_contrast_text_native": True,
        "mobile_dark_status_uses_high_contrast_text_legacy": True,
        "wrapped_dock_clearance_preserved_native": True,
        "wrapped_dock_clearance_preserved_legacy": True,
        "legacy_editor_clearances_preserved": True,
        "exact_head_focused_regressions_passed": True,
        "exact_head_dark_browser_readbacks_passed": True,
        "pre_successor_full_validate_failed_only_on_binding_gate": True,
        "independent_observer_readback_passed": True,
        "git_diff_check_passed": True,
        "publication_successor_binding_added": True,
    }
    dark_finding = single_workspace_dark_status["check_evidence"]["review_finding"]
    assert dark_finding["source_head"] == "01e425933d1fd3c93d7651f23fda9ec16c4592ab"
    assert dark_finding["thread_id"] == "PRRT_kwDOTGqvHc6o1H7r"
    assert dark_finding["comment_id"] == 4178743939
    assert dark_finding["pre_fix_reproduction"]["computed_status"] == {
        "background": "rgba(255, 255, 255, 0.9)",
        "color": "rgb(162, 166, 181)",
        "border_color": "rgb(44, 47, 59)",
    }
    assert dark_finding["addressed_by_functional_head"] == (
        single_workspace_dark_status["functional_head"]
    )
    dark_focused = single_workspace_dark_status["check_evidence"][
        "focused_regressions"
    ]
    assert dark_focused["job_id"] == "84604d065ec0"
    assert dark_focused["passed_count"] == 130
    assert dark_focused["result"] == "passed"
    for key, job_id in (
        ("dark_native_browser_readback", "a14cd91ea742"),
        ("dark_legacy_browser_readback", "ec9a4f77a3d7"),
    ):
        readback = single_workspace_dark_status["check_evidence"][key]
        assert readback["job_id"] == job_id
        assert readback["computed_status"] == {
            "background": "rgba(24, 26, 36, 0.92)",
            "color": "rgb(240, 241, 247)",
            "border_color": "rgb(58, 62, 75)",
        }
        assert readback["status_dock_gap_px"] == 8
        assert readback["status_dock_overlap_px"] == 0
        assert readback["result"] == "passed"
    dark_legacy = single_workspace_dark_status["check_evidence"][
        "dark_legacy_browser_readback"
    ]
    assert dark_legacy["frame_dock_gap_px"] == 8
    assert dark_legacy["frame_close_gap_px"] == 8
    dark_pre_successor = single_workspace_dark_status["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert dark_pre_successor["job_id"] == "abfbbd741027"
    assert dark_pre_successor["passed_count"] == 1655
    assert dark_pre_successor["failed_count"] == 1
    assert (
        dark_pre_successor["failure_class"]
        == "expected_successor_binding_gate"
    )
    dark_observer = single_workspace_dark_status["check_evidence"][
        "independent_observer_readback"
    ]
    assert dark_observer["observer"] == "grosser-adler"
    assert dark_observer["functional_head"] == (
        single_workspace_dark_status["functional_head"]
    )
    assert dark_observer["worktree_clean"] is True
    assert dark_observer["untracked_present"] is False
    assert dark_observer["finding_count"] == 0
    assert dark_observer["projection_complete"] is True
    dark_diff = single_workspace_dark_status["check_evidence"]["git_diff_check"]
    assert dark_diff["base_sha"] == "01e425933d1fd3c93d7651f23fda9ec16c4592ab"
    assert dark_diff["head_sha"] == single_workspace_dark_status["functional_head"]
    assert dark_diff["diff_sha256"] == (
        "8f1a759281f778770ff89339adcb13349cf7a5d5fa60b9299ac94fd073405f12"
    )
    assert dark_diff["result"] == "passed"
    assert (
        "decision-bound independent reviewer PASS on the later successor-evidence head"
        in single_workspace_dark_status["does_not_establish"]
    )

    single_workspace_max_canvas = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_MAX_CANVAS_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_max_canvas["schema_version"]
        == "schauwerk-schaubild-single-workspace-max-canvas.v1"
    )
    assert (
        single_workspace_max_canvas["functional_head"]
        == "eea29caf4f212125e734894a479d612fe9e9ef42"
    )
    assert single_workspace_max_canvas["parent_evidence"] == {
        "evidence_digest": single_workspace_dark_status["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_DARK_STATUS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-dark-status-20261004/"
            "acceptance-receipt.json"
        ),
        "schema_version": single_workspace_dark_status["schema_version"],
    }
    assert single_workspace_max_canvas["evidence_digest"] == digest_mapping(
        single_workspace_max_canvas, "evidence_digest"
    )
    assert (
        set(single_workspace_max_canvas["source_bindings"])
        == single_workspace_max_canvas_superseded_files
    )
    for name, expected in single_workspace_max_canvas["source_bindings"].items():
        if name in (
            single_workspace_fit_clearance_superseded_files
            | single_workspace_review_closure_superseded_files
            | single_workspace_review_hardening_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert single_workspace_max_canvas["checks"]["single_workspace_only_after_open"] is True
    assert (
        single_workspace_max_canvas["checks"]["export_popover_closes_after_export_action"]
        is True
    )
    assert (
        single_workspace_max_canvas["checks"]["engine_specific_export_capabilities_preserved"]
        is True
    )
    max_focused = single_workspace_max_canvas["check_evidence"]["focused_regressions"]
    assert max_focused["job_id"] == "04d5eaa80cdb4e7585dfc800"
    assert max_focused["passed_count"] == 32
    assert max_focused["result"] == "passed"
    max_smoke = single_workspace_max_canvas["check_evidence"]["browser_smoke"]
    assert max_smoke["job_id"] == "cbb7f605fc3f4e0d9bca42d9"
    assert max_smoke["passed_count"] == 7
    assert max_smoke["result"] == "passed"
    max_visual = single_workspace_max_canvas["check_evidence"]["visual_readback"]
    assert max_visual["job_id"] == "5f176639c0064efda87292ca"
    assert max_visual["result"] == "passed"
    for state in (
        "native_desktop_light",
        "native_mobile_dark",
        "legacy_desktop_light",
        "legacy_mobile_dark",
    ):
        assert max_visual["states"][state]["export_menu_open_after_action"] is False
        assert max_visual["states"][state]["download_visible_after_action"] is True
        assert max_visual["states"][state]["result"] == "passed"
    max_pre = single_workspace_max_canvas["check_evidence"]["pre_successor_full_validate"]
    assert max_pre["job_id"] == "41156c29cdd5425581d5ba3a"
    assert max_pre["passed_count"] == 1658
    assert max_pre["failed_count"] == 1
    assert max_pre["failure_class"] == "expected_successor_binding_gate"
    max_observer = single_workspace_max_canvas["check_evidence"][
        "independent_observer_readback"
    ]
    assert max_observer["observer"] == "grosser-adler"
    assert max_observer["functional_head"] == single_workspace_max_canvas["functional_head"]
    assert max_observer["worktree_clean"] is True
    assert max_observer["untracked_present"] is False
    assert max_observer["finding_count"] == 0
    assert max_observer["result"] == "passed"
    assert single_workspace_max_canvas["check_evidence"]["git_diff_check"] == {
        "base_sha": "8ec2042d565008a171d46b84415065904748e29b",
        "head_sha": "eea29caf4f212125e734894a479d612fe9e9ef42",
        "diff_sha256": "67abebb2c17a6ccd3e73dbbe4da373737f86a6000d83b332be106df5b11690d1",
        "diff_bytes": 71784,
        "result": "passed",
    }

    single_workspace_fit_clearance = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_FIT_CLEARANCE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        single_workspace_fit_clearance["schema_version"]
        == "schauwerk-schaubild-single-workspace-fit-clearance.v1"
    )
    assert (
        single_workspace_fit_clearance["functional_head"]
        == "fc0e1844efa945adccdc1e0a92296c44a778bd8b"
    )
    assert single_workspace_fit_clearance["parent_evidence"] == {
        "evidence_digest": single_workspace_max_canvas["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_MAX_CANVAS_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-max-canvas-20261005/"
            "acceptance-receipt.json"
        ),
        "schema_version": single_workspace_max_canvas["schema_version"],
    }
    assert single_workspace_fit_clearance["evidence_digest"] == digest_mapping(
        single_workspace_fit_clearance, "evidence_digest"
    )
    assert (
        set(single_workspace_fit_clearance["source_bindings"])
        == single_workspace_fit_clearance_superseded_files
    )
    for name, expected in single_workspace_fit_clearance["source_bindings"].items():
        if name in (
            single_workspace_review_closure_superseded_files
            | single_workspace_review_hardening_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    fit_finding = single_workspace_fit_clearance["check_evidence"]["review_finding"]
    assert fit_finding["thread_id"] == "PRRT_kwDOTGqvHc6o8b6l"
    assert fit_finding["comment_id"] == 4181740632
    fit_contract = single_workspace_fit_clearance["check_evidence"]["fit_contract"]
    assert fit_contract["standalone_padding_px"] == 48
    assert fit_contract["embedded_padding_px"] == {
        "top": 60,
        "right": 48,
        "bottom": 104,
        "left": 48,
    }
    fit_focused = single_workspace_fit_clearance["check_evidence"][
        "exact_head_focused_regressions"
    ]
    assert fit_focused["job_id"] == "3f1962c08238436abf2a98f2"
    assert fit_focused["passed_count"] == 30
    assert fit_focused["result"] == "passed"
    fit_smoke = single_workspace_fit_clearance["check_evidence"][
        "exact_head_browser_smoke"
    ]
    assert fit_smoke["job_id"] == "b66b2fa8ad2c4633979458da"
    assert fit_smoke["passed_count"] == 7
    fit_visual = single_workspace_fit_clearance["check_evidence"]["visual_readback"]
    for state in ("native_desktop_light", "native_mobile_dark"):
        assert fit_visual["states"][state]["host_clearance_px"] > 8
        assert fit_visual["states"][state]["native_toolbar_clearance_px"] > 6
    fit_tablet = single_workspace_fit_clearance["check_evidence"][
        "tablet_visual_readback"
    ]
    assert fit_tablet["viewport"] == {"width": 1024, "height": 768}
    assert fit_tablet["host_clearance_px"] > 8
    assert fit_tablet["native_toolbar_clearance_px"] > 6
    fit_pre = single_workspace_fit_clearance["check_evidence"][
        "pre_successor_full_validate"
    ]
    assert fit_pre["passed_count"] == 1658
    assert fit_pre["failed_count"] == 1
    assert fit_pre["failure_class"] == "expected_successor_binding_gate"
    assert single_workspace_fit_clearance["check_evidence"]["git_diff_check"] == {
        "base_sha": "1e1be1742147a5dbb72dc82ed3c3fe75a2258844",
        "head_sha": "fc0e1844efa945adccdc1e0a92296c44a778bd8b",
        "diff_sha256": "4d8262a605f32cd7d7b1209dd946b983e5b7b3cd5078011fb8bf9832b13904f7",
        "diff_bytes": 8188,
        "result": "passed",
    }

    review_closure = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_REVIEW_CLOSURE_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert review_closure["schema_version"] == (
        "schauwerk-schaubild-single-workspace-review-closure.v1"
    )
    assert (
        review_closure["functional_head"]
        == "8fe4d77638e66178a58e7503f3db8b716557efd1"
    )
    assert review_closure["parent_evidence"] == {
        "evidence_digest": single_workspace_fit_clearance["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_FIT_CLEARANCE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-fit-clearance-20261005/"
            "acceptance-receipt.json"
        ),
        "schema_version": single_workspace_fit_clearance["schema_version"],
    }
    assert review_closure["evidence_digest"] == digest_mapping(
        review_closure, "evidence_digest"
    )
    assert (
        set(review_closure["source_bindings"])
        == single_workspace_review_closure_superseded_files
    )
    for name, expected in review_closure["source_bindings"].items():
        if name in (
            single_workspace_review_hardening_superseded_files
            | single_workspace_mobile_320_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(review_closure["checks"].values())
    review_evidence = review_closure["check_evidence"]
    pre_validate = review_evidence["pre_successor_full_validate"]
    assert pre_validate["functional_head"] == review_closure["functional_head"]
    assert pre_validate["task_id"] == "b93f619d6783470fa502dc60"
    assert pre_validate["passed_count"] == 1662
    assert pre_validate["failed_count"] == 1
    assert pre_validate["failure_class"] == "expected_successor_binding_gate"
    browser = review_evidence["browser_smoke"]
    assert browser["functional_head"] == review_closure["functional_head"]
    assert browser["task_id"] == "78b2146cf6374642b8601961"
    assert browser["passed_count"] == 13
    assert browser["failed_count"] == 0
    assert browser["result"] == "passed"
    visual = review_evidence["visual_readback"]
    readback_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_REVIEW_CLOSURE_EVIDENCE
        / "visual-readback.json"
    ).read_bytes()
    assert visual["readback_json_sha256"] == hashlib.sha256(readback_bytes).hexdigest()
    readback = json.loads(readback_bytes)
    assert readback["head"] == review_closure["functional_head"]
    assert len(readback["cases"]) == 6
    for case in ("process-status-mobile-dark", "process-status-431-dark"):
        process = readback["cases"][case]["processStatus"]
        assert process["text"] == "Ziel für die neue Verbindung auswählen"
        assert process["whiteSpace"] == "normal"
        assert process["textOverflow"] == "clip"
        assert process["scrollWidth"] <= process["clientWidth"] + 1
        assert process["scrollHeight"] <= process["clientHeight"] + 1
    drawio = readback["cases"]["drawio-export-mobile-dark"]
    assert drawio["exportClosed"] is True
    assert drawio["gap"] >= 6
    assert drawio["popover"]["x"] >= 0
    assert drawio["button"]["x"] >= 0
    for case in ("native-desktop-light", "native-tablet-light", "native-mobile-dark"):
        measured = readback["cases"][case]
        assert measured["hostClearance"] >= 8
        assert measured["nativeClearance"] >= 6
        assert measured["stage"]["width"] == measured["viewport"]["width"]
        assert measured["stage"]["height"] == measured["viewport"]["height"]
    for case in readback["cases"].values():
        assert len(case["screenshot_sha256"]) == 64
    assert visual["result"] == "passed"
    assert review_evidence["git_diff_check"]["result"] == "passed"

    review_self = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_REVIEW_CLOSURE_EVIDENCE
            / "grabowski-self-review.json"
        ).read_text(encoding="utf-8")
    )
    assert review_self["functional_head"] == review_closure["functional_head"]
    assert len(review_self["passes"]) == 5
    assert review_self["visual_readback_json_sha256"] == visual["readback_json_sha256"]

    review_hardening = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert review_hardening["schema_version"] == (
        "schauwerk-schaubild-single-workspace-review-hardening.v1"
    )
    assert review_hardening["functional_head"] == (
        "0f4384223dde8d8bf5cacc1875a8fbde5f93ce70"
    )
    assert review_hardening["parent_evidence"] == {
        "evidence_digest": review_closure["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_REVIEW_CLOSURE_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-review-closure-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": review_closure["schema_version"],
    }
    assert review_hardening["evidence_digest"] == digest_mapping(
        review_hardening, "evidence_digest"
    )
    assert set(review_hardening["source_bindings"]) == (
        single_workspace_review_hardening_superseded_files
    )
    for name, expected in review_hardening["source_bindings"].items():
        if name in (
            single_workspace_zoom_continuity_superseded_files
            | single_workspace_fit_retry_superseded_files
            | single_workspace_independent_remediation_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(review_hardening["checks"].values())
    hardening_evidence = review_hardening["check_evidence"]
    pre = hardening_evidence["pre_successor_full_validate"]
    assert pre["functional_head"] == review_hardening["functional_head"]
    assert pre["task_id"] == "19a093ab49ca425abc7c967b"
    assert pre["passed_count"] == 1667
    assert pre["failed_count"] == 1
    assert pre["failure_class"] == "expected_successor_binding_gate"
    browser = hardening_evidence["exact_head_browser_smoke"]
    assert browser["functional_head"] == review_hardening["functional_head"]
    assert browser["task_id"] == "50d7e5e805f64d4e9387b9fb"
    assert browser["passed_count"] == 18
    assert browser["failed_count"] == 0
    assert browser["result"] == "passed"
    visual_info = hardening_evidence["visual_readback"]
    visual_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE
        / "visual-readback.json"
    ).read_bytes()
    assert visual_info["readback_json_sha256"] == hashlib.sha256(
        visual_bytes
    ).hexdigest()
    visual_report = json.loads(visual_bytes)
    assert visual_report["head"] == review_hardening["functional_head"]
    assert len(visual_report["cases"]) == visual_info["case_count"] == 8
    for key in ("native-desktop-light", "native-tablet-light",
                "native-mobile-dark", "native-tall-mobile-dark"):
        case = visual_report["cases"][key]
        assert case["hostClearance"] >= 8
        assert case["nativeClearance"] >= 6
        assert case["frame"]["width"] == case["viewport"]["width"]
        assert case["stage"]["height"] == case["viewport"]["height"]
    for key in ("process-status-mobile-dark", "process-status-431-dark",
                "process-status-landscape-dark"):
        status = visual_report["cases"][key]["processStatus"]
        assert status["text"] == "Ziel für die neue Verbindung auswählen"
        assert status["whiteSpace"] == "normal"
        assert status["textOverflow"] == "clip"
        assert status["scrollWidth"] <= status["clientWidth"] + 1
        assert status["scrollHeight"] <= status["clientHeight"] + 1
    drawio = visual_report["cases"]["drawio-export-mobile-dark"]
    assert drawio["gap"] >= 6
    assert drawio["popover"]["x"] >= 0
    assert drawio["button"]["x"] >= 0
    assert drawio["exportClosed"] is True
    for case in visual_report["cases"].values():
        assert len(case["screenshot_sha256"]) == 64
    assert visual_info["result"] == "passed"
    legacy_info = hardening_evidence["legacy_readback"]
    legacy_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE
        / "legacy-visual-readback.json"
    ).read_bytes()
    assert legacy_info["readback_json_sha256"] == hashlib.sha256(
        legacy_bytes
    ).hexdigest()
    legacy_report = json.loads(legacy_bytes)
    assert legacy_report["functional_head"] == review_hardening["functional_head"]
    assert len(legacy_report["cases"]) == legacy_info["case_count"] == 1
    legacy_mobile = legacy_report["cases"]["legacy-dark-mobile"]
    assert legacy_mobile["viewport"]["height"] - legacy_mobile["bar"]["bottom"] >= 40
    assert legacy_mobile["exportGap"] >= 6
    assert len(legacy_mobile["screenshot_sha256"]) == 64
    assert legacy_info["result"] == "passed"
    assert hardening_evidence["visual_acceptance"]["decision"] == "accepted"
    assert hardening_evidence["visual_acceptance"]["functional_head"] == (
        review_hardening["functional_head"]
    )
    assert hardening_evidence["independent_observer_readback"][
        "observed_head"
    ] == review_hardening["functional_head"]
    assert hardening_evidence["independent_observer_readback"][
        "worktree_clean"
    ] is True
    assert hardening_evidence["git_diff_check"] == {
        "base_sha": "5c5759de6ff1e18bbae2f53d13a292d120c23ab2",
        "head_sha": review_hardening["functional_head"],
        "diff_sha256": "e9a0f548f108401337a65f2e8b6a9b111b56c51550e205a76def29945e3481a5",
        "diff_bytes": 14660,
        "result": "passed",
    }
    hardening_self_review = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE
            / "grabowski-self-review.json"
        ).read_text(encoding="utf-8")
    )
    assert hardening_self_review["functional_head"] == (
        review_hardening["functional_head"]
    )
    assert len(hardening_self_review["iterations"]) == 5
    assert hardening_self_review["visual_readback_json_sha256"] == (
        visual_info["readback_json_sha256"]
    )
    assert hardening_self_review["legacy_visual_readback_json_sha256"] == (
        legacy_info["readback_json_sha256"]
    )

    zoom_continuity = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_ZOOM_CONTINUITY_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert zoom_continuity["schema_version"] == (
        "schauwerk-schaubild-single-workspace-zoom-continuity.v1"
    )
    assert zoom_continuity["functional_head"] == (
        "eca81dc0ba825e4ad3477322361f376498034393"
    )
    assert zoom_continuity["parent_evidence"] == {
        "evidence_digest": review_hardening["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_REVIEW_HARDENING_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-review-hardening-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": review_hardening["schema_version"],
    }
    assert zoom_continuity["evidence_digest"] == digest_mapping(
        zoom_continuity, "evidence_digest"
    )
    assert set(zoom_continuity["source_bindings"]) == (
        single_workspace_zoom_continuity_superseded_files
    )
    for name, expected in zoom_continuity["source_bindings"].items():
        if name in single_workspace_fit_retry_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(zoom_continuity["checks"].values())
    zoom_evidence = zoom_continuity["check_evidence"]
    assert zoom_evidence["prior_current_head_independent_review"][
        "verdict"
    ] == "NEEDS_CHANGE"
    assert zoom_evidence["prior_current_head_independent_review"][
        "does_not_establish_new_head_pass"
    ] is True
    pre = zoom_evidence["pre_successor_full_validate"]
    assert pre["functional_head"] == zoom_continuity["functional_head"]
    assert pre["task_id"] == "ed292ad461274cafa9695c1d"
    assert pre["passed_count"] == 1667
    assert pre["failed_count"] == 1
    assert pre["failure_class"] == "expected_successor_binding_gate"
    browser = zoom_evidence["exact_head_browser_smoke"]
    assert browser["functional_head"] == zoom_continuity["functional_head"]
    assert browser["task_id"] == "a4893f78088046478a89c65c"
    assert browser["passed_count"] == 18
    assert browser["failed_count"] == 0
    assert browser["result"] == "passed"
    visual_info = zoom_evidence["visual_readback"]
    visual_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_ZOOM_CONTINUITY_EVIDENCE
        / "visual-readback.json"
    ).read_bytes()
    assert visual_info["readback_json_sha256"] == hashlib.sha256(
        visual_bytes
    ).hexdigest()
    readback = json.loads(visual_bytes)
    assert readback["head"] == zoom_continuity["functional_head"]
    assert len(readback["cases"]) == visual_info["case_count"] == 8
    touch = readback["cases"]["native-tall-mobile-dark"]["touchPinch"]
    assert touch == visual_info["pinch_scales"]
    assert 0 < touch["initial"] < 0.25
    assert touch["inward"] <= touch["initial"] + 1e-6
    assert touch["outward"] > touch["initial"]
    assert abs(touch["outward"] - touch["expectedOutward"]) <= 1e-6
    for case in readback["cases"].values():
        assert len(case["screenshot_sha256"]) == 64
    assert visual_info["result"] == "passed"
    assert zoom_evidence["visual_acceptance"]["result"] == "accepted"
    assert zoom_evidence["visual_acceptance"]["functional_head"] == (
        zoom_continuity["functional_head"]
    )
    assert zoom_evidence["independent_observer_readback"]["observed_head"] == (
        zoom_continuity["functional_head"]
    )
    assert zoom_evidence["independent_observer_readback"]["worktree_clean"] is True
    assert zoom_evidence["git_diff_check"] == {
        "base_sha": "eb02f981025f97e9ca27641d67c02eecc49ca16f",
        "head_sha": zoom_continuity["functional_head"],
        "diff_sha256": "c33c7aeb11e738afc90a694c54ff5276f3d55c18299dff9f750383463dd3a9f8",
        "diff_bytes": 5459,
        "result": "passed",
    }
    zoom_self_review = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_ZOOM_CONTINUITY_EVIDENCE
            / "grabowski-self-review.json"
        ).read_text(encoding="utf-8")
    )
    assert zoom_self_review["functional_head"] == (
        zoom_continuity["functional_head"]
    )
    assert len(zoom_self_review["passes"]) == 5
    assert zoom_self_review["visual_readback_json_sha256"] == (
        visual_info["readback_json_sha256"]
    )

    fit_retry = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert fit_retry["schema_version"] == (
        "schauwerk-schaubild-single-workspace-fit-retry.v1"
    )
    assert fit_retry["functional_head"] == (
        "b63fae1e6ea94e4b3a35f08a47292dbc5b74f549"
    )
    assert fit_retry["parent_evidence"] == {
        "evidence_digest": zoom_continuity["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_ZOOM_CONTINUITY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-zoom-continuity-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": zoom_continuity["schema_version"],
    }
    assert fit_retry["evidence_digest"] == digest_mapping(
        fit_retry, "evidence_digest"
    )
    assert set(fit_retry["source_bindings"]) == (
        single_workspace_fit_retry_superseded_files
    )
    for name, expected in fit_retry["source_bindings"].items():
        if name in (
            single_workspace_popover_anchoring_superseded_files
            | single_workspace_final_review_superseded_files
            | single_workspace_independent_remediation_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(fit_retry["checks"].values())
    fit_checks = fit_retry["check_evidence"]
    assert fit_checks["confirmed_ci_failure"]["observed_clearance_px"] == -7.13
    assert fit_checks["confirmed_ci_failure"][
        "retry_with_clean_chrome_profile_also_failed"
    ] is True
    growth = fit_checks["status_growth_reproduction"]
    assert growth["before_head"] == fit_retry["base_product_head"]
    assert growth["after_head"] == fit_retry["functional_head"]
    assert growth["before_native_clearance_px"] < 0
    assert growth["after_native_clearance_px"] >= 6
    assert growth["bar_height_change_px"] >= 60
    assert growth["result"] == "passed"
    review = fit_checks["prior_independent_review"]
    assert review["reviewed_head"] == fit_retry["base_product_head"]
    assert review["verdict"] == "NEEDS_CHANGE"
    assert review["does_not_prove_new_head_pass"] is True
    recovery = fit_checks["recovery_export_hit_tests"]
    assert recovery["widths"] == [390, 1366]
    assert recovery["result"] == "passed"
    pre = fit_checks["pre_successor_full_validate"]
    assert pre["functional_head"] == fit_retry["functional_head"]
    assert pre["task_id"] == "bd0aa682b31c4c76adadd4a3"
    assert pre["passed_count"] == 1667
    assert pre["failed_count"] == 1
    assert pre["failure_class"] == "expected_successor_binding_gate"
    browser = fit_checks["exact_head_browser_smoke"]
    assert browser["functional_head"] == fit_retry["functional_head"]
    assert browser["task_id"] == "3838d87b0af54d9890204cab"
    assert browser["passed_count"] == 18
    assert browser["failed_count"] == 0
    assert browser["result"] == "passed"
    visual = fit_checks["visual_readback"]
    visual_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE
        / "visual-readback.json"
    ).read_bytes()
    assert visual["readback_json_sha256"] == hashlib.sha256(
        visual_bytes
    ).hexdigest()
    readback = json.loads(visual_bytes)
    assert readback["head"] == fit_retry["functional_head"]
    assert len(readback["cases"]) == visual["case_count"] == 8
    for key in ("native-desktop-light", "native-tablet-light",
                "native-mobile-dark", "native-tall-mobile-dark"):
        case = readback["cases"][key]
        assert case["hostClearance"] >= 8
        assert case["nativeClearance"] >= 6
        assert case["frame"]["width"] == case["viewport"]["width"]
        assert case["stage"]["height"] == case["viewport"]["height"]
    drawio = readback["cases"]["drawio-export-mobile-dark"]
    assert drawio["gap"] >= 6
    assert drawio["popover"]["x"] >= 0
    assert drawio["button"]["x"] >= 0
    for case in readback["cases"].values():
        assert len(case["screenshot_sha256"]) == 64
    assert visual["result"] == "passed"
    stress = fit_checks["status_growth_readback"]
    stress_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE
        / "status-growth-readback.json"
    ).read_bytes()
    assert stress["readback_json_sha256"] == hashlib.sha256(
        stress_bytes
    ).hexdigest()
    stress_report = json.loads(stress_bytes)
    assert stress_report["head"] == fit_retry["functional_head"]
    assert len(stress_report["cases"]) == stress["case_count"] == 1
    status_growth = stress_report["cases"]["status-growth-tall-mobile"]
    assert status_growth["nativeClearance"] >= 6
    assert status_growth["fitStatus"]["barAfterBottom"] - (
        status_growth["fitStatus"]["barBeforeBottom"]
    ) >= 60
    assert status_growth["fitStatus"]["text"] == "Ansicht angepasst"
    assert stress["result"] == "passed"
    assert fit_checks["visual_acceptance"]["decision"] == "accepted"
    assert fit_checks["visual_acceptance"]["functional_head"] == (
        fit_retry["functional_head"]
    )
    assert fit_checks["independent_observer_readback"][
        "observed_head"
    ] == fit_retry["functional_head"]
    assert fit_checks["independent_observer_readback"]["worktree_clean"] is True
    assert fit_checks["git_diff_check"] == {
        "base_sha": "888415a1a812133875a02f565d831fde61acff3e",
        "head_sha": fit_retry["functional_head"],
        "diff_sha256": "a04f5d33f0e2fee02cfd228ae1015b61079e2625196fe015e117d35550a1470b",
        "diff_bytes": 4655,
        "result": "passed",
    }
    fit_self_review = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE
            / "grabowski-self-review.json"
        ).read_text(encoding="utf-8")
    )
    assert fit_self_review["functional_head"] == fit_retry["functional_head"]
    assert len(fit_self_review["passes"]) == 5
    assert fit_self_review["visual_readback_json_sha256"] == (
        visual["readback_json_sha256"]
    )
    assert fit_self_review["status_growth_readback_json_sha256"] == (
        stress["readback_json_sha256"]
    )

    popover_anchor = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_POPOVER_ANCHORING_EVIDENCE
            / "acceptance-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert popover_anchor["schema_version"] == (
        "schauwerk-schaubild-single-workspace-popover-anchoring.v1"
    )
    assert popover_anchor["functional_head"] == (
        "36d9d7c2ad50797a4bfa38e39b6f354398fe3089"
    )
    assert popover_anchor["parent_evidence"] == {
        "evidence_digest": fit_retry["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (
                SCHAUBILD_SINGLE_WORKSPACE_FIT_RETRY_EVIDENCE
                / "acceptance-receipt.json"
            ).read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-fit-retry-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": fit_retry["schema_version"],
    }
    assert popover_anchor["evidence_digest"] == digest_mapping(
        popover_anchor, "evidence_digest"
    )
    assert set(popover_anchor["source_bindings"]) == (
        single_workspace_popover_anchoring_superseded_files
    )
    for name, expected in popover_anchor["source_bindings"].items():
        if name in single_workspace_final_review_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(popover_anchor["checks"].values())
    pop_checks = popover_anchor["check_evidence"]
    prev = pop_checks["independent_review"]
    assert prev["reviewed_head"] == popover_anchor["base_product_head"]
    assert prev["verdict"] == "NEEDS_CHANGE"
    assert prev["new_head_review_required"] is True
    red = pop_checks["red_before"]
    green = pop_checks["green_after"]
    assert red["head"] == popover_anchor["base_product_head"]
    assert red["result"] == "failed"
    assert red["normal_mode_and_600px_gap_px"] == 56
    assert green["head"] == popover_anchor["functional_head"]
    assert green["mobile_390_px_gap"] == 7
    assert green["mobile_600_px_gap"] == 7
    assert green["result"] == "passed"
    full = pop_checks["pre_successor_full_validate"]
    assert full["head"] == popover_anchor["functional_head"]
    assert full["passed_count"] == 1667
    assert full["failed_count"] == 1
    assert full["failure_class"] == "expected_successor_binding_gate"
    smoke = pop_checks["functional_browser_smoke"]
    assert smoke["head"] == popover_anchor["functional_head"]
    assert smoke["passed_count"] == 18
    assert smoke["failed_count"] == 0
    assert smoke["result"] == "passed"
    readback_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_POPOVER_ANCHORING_EVIDENCE
        / "visual-readback.json"
    ).read_bytes()
    visual = pop_checks["visual_readback"]
    assert hashlib.sha256(readback_bytes).hexdigest() == visual["sha256"]
    report = json.loads(readback_bytes)
    assert report["functional_head"] == popover_anchor["functional_head"]
    assert set(report["cases"]) == {"legacy-dark-mobile", "legacy-dark-tablet"}
    for case in report["cases"].values():
        assert case["beforeCss"]["barBackdrop"] == "none"
        assert case["beforeCss"]["position"] == "fixed"
        assert 6 <= case["exportGap"] <= 14
        assert abs(case["delta"]["x"]) < 1e-6
        assert abs(case["delta"]["y"]) < 1e-6
        assert case["exportPopover"]["right"] <= case["viewport"]["width"] + 0.5
        assert case["beforeHit"] == "BUTTON"
        assert len(case["screenshot_sha256"]) == 64
    assert visual["case_count"] == 2
    assert visual["result"] == "passed"
    assert pop_checks["visual_acceptance"]["decision"] == "accepted"
    assert pop_checks["visual_acceptance"]["head"] == (
        popover_anchor["functional_head"]
    )
    assert pop_checks["observer"]["observed_head"] == (
        popover_anchor["functional_head"]
    )
    assert pop_checks["observer"]["worktree_clean"] is True
    assert pop_checks["git_diff_check"] == {
        "base_sha": "559a89a86e793863b544397d89db6f2db8643256",
        "head_sha": popover_anchor["functional_head"],
        "diff_sha256": "a6c87f9c7be42043887e468f9d29366e447af6e4752079c2405fd92da40c5867",
        "diff_bytes": 2269,
        "result": "passed",
    }
    self_review = json.loads(
        (
            SCHAUBILD_SINGLE_WORKSPACE_POPOVER_ANCHORING_EVIDENCE
            / "grabowski-self-review.json"
        ).read_text(encoding="utf-8")
    )
    assert self_review["functional_head"] == popover_anchor["functional_head"]
    assert len(self_review["passes"]) == 5
    assert self_review["visual_readback_json_sha256"] == visual["sha256"]

    final_review_path = (
        SCHAUBILD_SINGLE_WORKSPACE_FINAL_REVIEW_EVIDENCE / "acceptance-receipt.json"
    )
    final_review = json.loads(final_review_path.read_text(encoding="utf-8"))
    assert final_review["schema_version"] == (
        "schauwerk-schaubild-single-workspace-final-review.v1"
    )
    assert final_review["functional_head"] == (
        "cca926f4a8e9262e65f51b67e59bbf538519481f"
    )
    assert final_review["base_product_head"] == (
        "ea1cb09a9cb1ac79d3cfa10ede6d20e4209402c8"
    )
    assert final_review["parent_evidence"] == {
        "evidence_digest": popover_anchor["evidence_digest"],
        "file_sha256": hashlib.sha256(
            (SCHAUBILD_SINGLE_WORKSPACE_POPOVER_ANCHORING_EVIDENCE
             / "acceptance-receipt.json").read_bytes()
        ).hexdigest(),
        "path": (
            "docs/operators/evidence/schaubild-single-workspace-popover-anchoring-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": popover_anchor["schema_version"],
    }
    assert final_review["evidence_digest"] == digest_mapping(
        final_review, "evidence_digest"
    )
    assert set(final_review["source_bindings"]) == (
        single_workspace_final_review_superseded_files
    )
    for name, expected in final_review["source_bindings"].items():
        if name in (
            single_workspace_safe_area_fit_superseded_files
            | single_workspace_safe_area_test_contract_superseded_files
            | single_workspace_mobile_320_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(final_review["checks"].values())
    assert final_review["check_evidence"]["red_before"]["result"] == "failed"
    focused = final_review["check_evidence"]["focused_tests"]
    assert focused["functional_head"] == final_review["functional_head"]
    assert focused["passed_count"] == 8
    assert focused["failed_count"] == 0
    assert focused["result"] == "passed"
    pre = final_review["check_evidence"]["pre_successor_full_validate"]
    assert pre["functional_head"] == final_review["functional_head"]
    assert pre["passed_count"] == 1667
    assert pre["failed_count"] == 1
    assert pre["failure_class"] == "expected_successor_binding_gate"
    visual_binding = final_review["visual_readback"]
    readback_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_FINAL_REVIEW_EVIDENCE / "visual-readback.json"
    ).read_bytes()
    assert visual_binding["sha256"] == hashlib.sha256(readback_bytes).hexdigest()
    readback = json.loads(readback_bytes)
    assert readback["functional_head"] == final_review["functional_head"]
    assert set(readback["cases"]) == {
        "native-mobile", "legacy-mobile", "legacy-431", "legacy-tablet",
    }
    assert visual_binding["case_count"] == 4
    assert set(visual_binding["screenshot_bindings"]) == {
        name + ".png" for name in readback["cases"]
    }
    for name, case in readback["cases"].items():
        assert (case["width"], case["height"]) == {
            "native-mobile": (390, 844),
            "legacy-mobile": (390, 844),
            "legacy-431": (431, 844),
            "legacy-tablet": (600, 900),
        }[name]
        assert 6 <= case["barGap"] <= 14
        assert case["menu"]["x"] >= -0.5
        assert case["menu"]["x"] + case["menu"]["width"] <= case["width"] + 0.5
        if case["width"] <= 520:
            assert case["statusVisibility"] == "hidden"
        else:
            assert case["statusVisibility"] == "visible"
            assert case["overlap"]["width"] == 0
        if name == "native-mobile":
            assert case["nativeNodeCount"] >= 2
        png = (SCHAUBILD_SINGLE_WORKSPACE_FINAL_REVIEW_EVIDENCE / (name + ".png")).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        digest = hashlib.sha256(png).hexdigest()
        assert digest == case["screenshot_sha256"]
        assert digest == visual_binding["screenshot_bindings"][name + ".png"]["sha256"]
        assert len(png) == case["screenshot_bytes"]
        assert len(png) == visual_binding["screenshot_bindings"][name + ".png"]["bytes"]
    assert final_review["check_evidence"]["visual_acceptance"]["decision"] == "accepted"

    safe_area_receipt_path = (
        SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_FIT_EVIDENCE / "acceptance-receipt.json"
    )
    safe_area_receipt = json.loads(safe_area_receipt_path.read_text(encoding="utf-8"))
    assert safe_area_receipt["schema_version"] == (
        "schauwerk-schaubild-single-workspace-safe-area-fit.v1"
    )
    assert safe_area_receipt["functional_head"] == (
        "12c5fb4cd7c7c0ce4e83ccd250189499a4bc7bb9"
    )
    assert safe_area_receipt["base_product_head"] == (
        "4996e39ec2f7c4b21a204bf01b78ee9a21ffe4bc"
    )
    assert safe_area_receipt["parent_evidence"] == {
        "evidence_digest": final_review["evidence_digest"],
        "file_sha256": hashlib.sha256(final_review_path.read_bytes()).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-final-review-20261008/acceptance-receipt.json"
        ),
        "schema_version": final_review["schema_version"],
    }
    assert safe_area_receipt["evidence_digest"] == digest_mapping(
        safe_area_receipt, "evidence_digest"
    )
    assert set(safe_area_receipt["source_bindings"]) == (
        single_workspace_safe_area_fit_superseded_files
    )
    for name, expected in safe_area_receipt["source_bindings"].items():
        if name in (
            single_workspace_mobile_320_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(safe_area_receipt["checks"].values())
    safe_evidence = safe_area_receipt["check_evidence"]
    assert safe_evidence["review_finding"]["pre_fix_host_clearance_px"] < 0
    assert safe_evidence["red_before"]["observed_clearance_px"] < 0
    assert safe_evidence["focused_red_green"]["result"] == "passed"
    assert safe_evidence["postcommit_browser_smoke"]["functional_head"] == (
        safe_area_receipt["functional_head"]
    )
    assert safe_evidence["postcommit_browser_smoke"]["passed_count"] == 19
    assert safe_evidence["postcommit_browser_smoke"]["failed_count"] == 0
    assert safe_evidence["exact_css_viewport"]["head"] == (
        safe_area_receipt["functional_head"]
    )
    assert safe_evidence["visual_acceptance"]["decision"] == "accepted"
    visual_binding = safe_area_receipt["visual_readback"]
    readback_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_FIT_EVIDENCE / "visual-readback.json"
    ).read_bytes()
    assert hashlib.sha256(readback_bytes).hexdigest() == visual_binding["sha256"]
    safe_visual = json.loads(readback_bytes)
    assert safe_visual["schema_version"] == "schauwerk-pr203-safe-area-visual.v1"
    assert safe_visual["functional_head"] == safe_area_receipt["functional_head"]
    expected_css = {
        "mobile-390-normal8": (390, 844, 8),
        "mobile-390-safe44": (390, 844, 44),
        "mobile-431-safe44": (431, 844, 44),
    }
    assert set(safe_visual["cases"]) == set(expected_css)
    assert visual_binding["case_count"] == len(expected_css)
    assert set(visual_binding["screenshot_bindings"]) == {
        key + ".png" for key in expected_css
    }
    for name, values in safe_visual["cases"].items():
        width, height, inset = expected_css[name]
        measured = values["safe"]
        assert values["inset"] == inset
        assert (measured["width"], measured["height"]) == (width, height)
        assert abs(height - measured["barBottom"] - inset) < 1
        assert measured["hostClearance"] >= 7.5
        assert abs(measured["stageWidth"] - width) <= 1
        assert abs(measured["stageHeight"] - height) <= 1
        assert measured["scale"] <= values["normal"]["scale"] + 1e-9
        if name == "mobile-390-safe44":
            assert measured["hostBarHorizontalOverlap"] > 0
        picture = (
            SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_FIT_EVIDENCE / (name + ".png")
        ).read_bytes()
        assert picture[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        picture_digest = hashlib.sha256(picture).hexdigest()
        assert values["screenshot_sha256"] == picture_digest
        assert values["screenshot_bytes"] == len(picture)
        binding = visual_binding["screenshot_bindings"][name + ".png"]
        assert binding["sha256"] == picture_digest
        assert binding["bytes"] == len(picture)
        assert binding["viewport_css_px"] == [width, height]

    test_contract_path = (
        SCHAUBILD_SINGLE_WORKSPACE_SAFE_AREA_TEST_CONTRACT_EVIDENCE
        / "acceptance-receipt.json"
    )
    test_contract = json.loads(test_contract_path.read_text(encoding="utf-8"))
    assert test_contract["schema_version"] == (
        "schauwerk-schaubild-single-workspace-safe-area-test-contract.v1"
    )
    assert test_contract["functional_head"] == (
        "ae92461eb3d94701327151c6b6de18863c5c4e78"
    )
    assert test_contract["base_product_head"] == (
        "12c5fb4cd7c7c0ce4e83ccd250189499a4bc7bb9"
    )
    assert test_contract["parent_evidence"] == {
        "evidence_digest": safe_area_receipt["evidence_digest"],
        "file_sha256": hashlib.sha256(safe_area_receipt_path.read_bytes()).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-safe-area-fit-20261008/acceptance-receipt.json"
        ),
        "schema_version": safe_area_receipt["schema_version"],
    }
    assert test_contract["evidence_digest"] == digest_mapping(
        test_contract, "evidence_digest"
    )
    assert set(test_contract["source_bindings"]) == (
        single_workspace_safe_area_test_contract_superseded_files
    )
    for name, expected in test_contract["source_bindings"].items():
        if name in single_workspace_independent_remediation_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert test_contract["unchanged_production_source_bindings"] == (
        safe_area_receipt["source_bindings"]
    )
    for name, expected in test_contract["unchanged_production_source_bindings"].items():
        if name in (
            single_workspace_mobile_320_superseded_files
            | single_workspace_side_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(test_contract["checks"].values())
    contract_checks = test_contract["check_evidence"]
    assert contract_checks["old_static_test_failure"]["passed_count"] == 1668
    assert contract_checks["old_static_test_failure"]["failed_count"] == 1
    assert contract_checks["new_geometry_contract_test"]["result"] == "passed"
    assert contract_checks["pre_successor_source_digest_gate"]["result"] == "failed"
    inherited = contract_checks["visual_acceptance_inheritance"]
    assert inherited["decision"] == "inherited_from_parent"
    assert inherited["parent_functional_head"] == safe_area_receipt["functional_head"]
    assert inherited["parent_visual_readback_sha256"] == (
        safe_area_receipt["visual_readback"]["sha256"]
    )

    mobile_path = SCHAUBILD_SINGLE_WORKSPACE_MOBILE_320_EVIDENCE / "acceptance-receipt.json"
    mobile = json.loads(mobile_path.read_text(encoding="utf-8"))
    assert mobile["schema_version"] == "schauwerk-schaubild-single-workspace-mobile-320.v1"
    assert mobile["functional_head"] == "de0ba2e47c88d7992a429cf6d882d45d05851b69"
    assert mobile["base_product_head"] == "359588eb2132c09cef9d2aca7d45d06f52410abe"
    assert mobile["parent_evidence"] == {
        "evidence_digest": test_contract["evidence_digest"],
        "file_sha256": hashlib.sha256(test_contract_path.read_bytes()).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-safe-area-test-contract-20261008/acceptance-receipt.json"
        ),
        "schema_version": test_contract["schema_version"],
    }
    assert mobile["evidence_digest"] == digest_mapping(mobile, "evidence_digest")
    assert set(mobile["source_bindings"]) == single_workspace_mobile_320_superseded_files
    for name, expected in mobile["source_bindings"].items():
        if name in (
            single_workspace_side_safearea_superseded_files
            | single_workspace_tap_autofit_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(mobile["checks"].values())
    m_checks = mobile["check_evidence"]
    assert m_checks["red_before"]["result"] == "failed"
    assert "overlap" in m_checks["red_before"]["failure"]
    assert m_checks["targeted_green"]["result"] == "passed"
    assert m_checks["canonical_browser_smoke"]["passed_count"] == 20
    assert m_checks["canonical_browser_smoke"]["failed_count"] == 0
    assert m_checks["runner_filter_parity"]["passed_count"] == 3
    assert m_checks["pre_successor_validate"]["passed_count"] == 1669
    assert m_checks["pre_successor_validate"]["failed_count"] == 1
    assert m_checks["pre_successor_validate"]["ruff_passed"] is True
    assert m_checks["post_import_sort_lint"]["result"] == "passed"
    assert m_checks["visual_acceptance"]["decision"] == "accepted"
    m_visual = mobile["visual_readback"]
    visual_data = (
        SCHAUBILD_SINGLE_WORKSPACE_MOBILE_320_EVIDENCE / "visual-readback.json"
    ).read_bytes()
    assert hashlib.sha256(visual_data).hexdigest() == m_visual["sha256"]
    m_report = json.loads(visual_data)
    assert m_report["schema_version"] == "schauwerk-pr203-mobile-320-visual-readback.v1"
    assert m_report["functional_head"] == mobile["functional_head"]
    assert m_visual["case_count"] == 2
    assert {case["width"] for case in m_report["cases"]} == {320, 390}
    assert set(m_visual["screenshot_bindings"]) == {
        "readback-320x700.png", "readback-390x844.png",
    }
    for case in m_report["cases"]:
        width = case["width"]
        height = 700 if width == 320 else 844
        assert case["height"] == height and case["scrollWidth"] == width
        assert case["bar"]["height"] <= 54 and not case["overlap"]
        assert len(case["controls"]) == 4
        for control in case["controls"]:
            rect = control["rect"]
            assert rect["width"] >= 38 and rect["height"] >= 40
            assert rect["left"] >= -0.5 and rect["right"] <= width + 0.5
        if width == 320:
            download = next(i for i in case["controls"] if i["name"] == "download")
            assert download["ariaLabel"] == "Originalprojekt speichern"
            assert "Speichern" in download["pseudoContent"]
        shot = f"readback-{width}x{height}.png"
        png = (SCHAUBILD_SINGLE_WORKSPACE_MOBILE_320_EVIDENCE / shot).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        sha = hashlib.sha256(png).hexdigest()
        assert sha == case["screenshot_sha256"] == m_visual["screenshot_bindings"][shot]["sha256"]
        assert len(png) == case["screenshot_bytes"]
        assert len(png) == m_visual["screenshot_bindings"][shot]["bytes"]
        assert m_visual["screenshot_bindings"][shot]["viewport_css_px"] == [width, height]

    side_receipt_path = (
        SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE / "acceptance-receipt.json"
    )
    side_safearea = json.loads(side_receipt_path.read_text(encoding="utf-8"))
    assert side_safearea["schema_version"] == (
        "schauwerk-schaubild-single-workspace-side-safearea.v1"
    )
    assert side_safearea["functional_head"] == (
        "88833933230b270ffdfba60aee2b5fe0977623da"
    )
    assert side_safearea["product_css_head"] == (
        "07822fe7e71390f95a50545db778ba45d5780fd0"
    )
    assert side_safearea["parent_evidence"] == {
        "evidence_digest": mobile["evidence_digest"],
        "file_sha256": hashlib.sha256(mobile_path.read_bytes()).hexdigest(),
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-mobile-320-20261008/acceptance-receipt.json"
        ),
        "schema_version": mobile["schema_version"],
    }
    assert side_safearea["evidence_digest"] == digest_mapping(
        side_safearea, "evidence_digest"
    )
    assert set(side_safearea["source_bindings"]) == (
        single_workspace_side_safearea_superseded_files
    )
    for name, expected in side_safearea["source_bindings"].items():
        if name in (
            single_workspace_ci_font_legacy_superseded_files
            | single_workspace_independent_remediation_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(side_safearea["checks"].values())
    sc = side_safearea["check_evidence"]
    assert sc["red_side_before"]["observed_left_css_px"] < 0
    assert sc["native_prompt_green"]["passed_count"] == 5
    assert sc["native_prompt_green"]["failed_count"] == 0
    assert sc["canonical_browser_smoke"]["passed_count"] == 24
    assert sc["pre_successor_full_validate"]["passed_count"] == 1673
    assert sc["pre_successor_full_validate"]["failed_count"] == 1
    assert sc["corrected_static_css_tests"]["passed_count"] == 8
    assert sc["visual_acceptance"]["decision"] == "accepted"
    side_binding = side_safearea["visual_readbacks"]["side_safe_area"]
    assert side_binding["observed_head"] == side_safearea["product_css_head"]
    assert side_binding["case_count"] == 5
    side_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE / "visual-readback.json"
    ).read_bytes()
    assert hashlib.sha256(side_bytes).hexdigest() == side_binding["sha256"]
    side_report = json.loads(side_bytes)
    assert side_report["schema_version"] == "schauwerk-pr203-side-safearea-visual.v1"
    assert side_report["functional_head"] == side_binding["observed_head"]
    assert len(side_report["cases"]) == 5
    for case in side_report["cases"]:
        width, height = case["width"], case["height"]
        assert (width, height) in {(320, 700), (390, 844)}
        assert case["bar_inside_safe_area"] is True
        assert case["popover_inside_safe_area"] is True
        assert case["overlap"] == []
        filename = case["screenshot_file"]
        png = (SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE / filename).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        sha = hashlib.sha256(png).hexdigest()
        assert sha == case["screenshot_sha256"]
        assert sha == side_binding["screenshots"][filename]["sha256"]
        assert len(png) == case["screenshot_bytes"]
        assert len(png) == side_binding["screenshots"][filename]["bytes"]
    prompt_binding = side_safearea["visual_readbacks"]["native_process_prompt"]
    prompt_bytes = (
        SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE / "prompt-readback.json"
    ).read_bytes()
    assert hashlib.sha256(prompt_bytes).hexdigest() == prompt_binding["sha256"]
    prompt_report = json.loads(prompt_bytes)
    assert prompt_binding["case_count"] == 2
    assert prompt_report["functional_head"] == side_safearea["functional_head"]
    assert prompt_report["schema_version"] == (
        "schauwerk-pr203-native-process-status-visual.v1"
    )
    assert {case["width"] for case in prompt_report["cases"]} == {320, 390}
    for case in prompt_report["cases"]:
        metric = case["nativeProcessStatus"]
        assert metric["statusOverlap"] is False
        assert metric["scrollWidth"] <= metric["clientWidth"] + 1
        assert metric["scrollHeight"] <= metric["clientHeight"] + 1
        assert metric["text"] == "Ziel für die neue Verbindung auswählen"
        filename = f"prompt-native-{case['width']}x{case['height']}.png"
        png = (SCHAUBILD_SINGLE_WORKSPACE_SIDE_SAFEAREA_EVIDENCE / filename).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        sha = hashlib.sha256(png).hexdigest()
        assert sha == case["screenshot_sha256"]
        assert sha == prompt_binding["screenshots"][filename]["sha256"]
        assert len(png) == prompt_binding["screenshots"][filename]["bytes"]

    # A new immutable child supersedes only the three files changed after the
    # accepted side-safearea revision. The parent receipt remains untouched.
    ci_path = SCHAUBILD_SINGLE_WORKSPACE_CI_FONT_LEGACY_EVIDENCE / "acceptance-receipt.json"
    ci_font_legacy = json.loads(ci_path.read_text(encoding="utf-8"))
    assert ci_font_legacy["schema_version"] == (
        "schauwerk-schaubild-single-workspace-ci-font-legacy.v1"
    )
    assert ci_font_legacy["functional_head"] == (
        "7ddd57ca724bf775afacc819dfb10c5ccdc037b3"
    )
    assert ci_font_legacy["capture_checkout_head"] == (
        "728c737ca16c8fe0a4b87c8f05e62acdbd564b4d"
    )
    assert ci_font_legacy["parent_evidence"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-side-safearea-20261008/acceptance-receipt.json"
        ),
        "file_sha256": hashlib.sha256(side_receipt_path.read_bytes()).hexdigest(),
        "evidence_digest": side_safearea["evidence_digest"],
        "schema_version": side_safearea["schema_version"],
    }
    assert ci_font_legacy["evidence_digest"] == digest_mapping(
        ci_font_legacy, "evidence_digest"
    )
    assert set(ci_font_legacy["source_bindings"]) == (
        single_workspace_ci_font_legacy_superseded_files
    )
    for name, expected in ci_font_legacy["source_bindings"].items():
        if name in single_workspace_independent_remediation_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(ci_font_legacy["checks"].values())
    assert (
        ci_font_legacy["check_evidence"]["prior_remote_ci_red"]["failed_parameterized_cases"]
        == 5
    )
    green = ci_font_legacy["check_evidence"]["browser_green"]
    assert green["passed_count"] == 24 and green["failed_count"] == 0
    assert ci_font_legacy["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    before = ci_font_legacy["visual_readbacks"]["before"]
    after = ci_font_legacy["visual_readbacks"]["after"]
    assert before["case_count"] == after["case_count"] == 5
    expected_cases = {
        (320, 700, 0, 0), (320, 700, 44, 0), (320, 700, 0, 44),
        (390, 844, 44, 0), (390, 844, 0, 44),
    }
    for metadata, is_final in ((before, False), (after, True)):
        payload = (ROOT / metadata["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == metadata["sha256"]
        report = json.loads(payload)
        assert report["functional_head"] == (
            ci_font_legacy["functional_head"] if is_final
            else ci_font_legacy["capture_checkout_head"]
        )
        assert {
            (case["width"], case["height"],
             case["simulated_safe_inset"]["left"], case["simulated_safe_inset"]["right"])
            for case in report["cases"]
        } == expected_cases
        for case in report["cases"]:
            png = (SCHAUBILD_SINGLE_WORKSPACE_CI_FONT_LEGACY_EVIDENCE
                   / case["screenshot_file"]).read_bytes()
            assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
            assert hashlib.sha256(png).hexdigest() == case["screenshot_sha256"]
            assert len(png) == case["screenshot_bytes"]
            if not is_final:
                continue
            inset = case["simulated_safe_inset"]
            geometry = case["geometry"]
            assert geometry["short"] == '"Speichern"'
            assert geometry["aria"] == "Originalprojekt speichern"
            assert geometry["bar"]["left"] >= inset["left"] - 0.5
            assert geometry["bar"]["right"] <= case["width"] - inset["right"] + 0.5
            assert geometry["popover"]["left"] >= inset["left"] - 0.5
            assert geometry["popover"]["right"] <= case["width"] - inset["right"] + 0.5
            assert abs(geometry["stage"]["width"] - case["width"]) < 1
            assert abs(geometry["stage"]["height"] - case["height"]) < 1
            assert all(
                item["width"] >= 38 and item["height"] >= 40
                and item["left"] >= inset["left"] - 0.5
                and item["right"] <= case["width"] - inset["right"] + 0.5
                for item in geometry["controls"]
            )

    # Preserve the previous receipt's bytes and expose its invalid historical
    # screenshot provenance; only the source-matched child authorizes new source SHA.
    independent_path = (
        SCHAUBILD_SINGLE_WORKSPACE_INDEPENDENT_REMEDIATION_EVIDENCE
        / "acceptance-receipt.json"
    )
    independent_remediation = json.loads(independent_path.read_text(encoding="utf-8"))
    assert independent_remediation["schema_version"] == (
        "schauwerk-schaubild-single-workspace-independent-remediation.v1"
    )
    assert independent_remediation["functional_head"] == (
        "0ef33d9e65d04019171b7c1df848367240d2250d"
    )
    assert independent_remediation["parent_evidence"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-ci-font-legacy-20261008/acceptance-receipt.json"
        ),
        "schema_version": ci_font_legacy["schema_version"],
        "file_sha256": hashlib.sha256(ci_path.read_bytes()).hexdigest(),
        "evidence_digest": ci_font_legacy["evidence_digest"],
    }
    assert independent_remediation["evidence_digest"] == digest_mapping(
        independent_remediation, "evidence_digest"
    )
    assert set(independent_remediation["source_bindings"]) == (
        single_workspace_independent_remediation_superseded_files
    )
    for name, expected in independent_remediation["source_bindings"].items():
        if name in (
            single_workspace_late_review_menus_superseded_files
            | single_workspace_ci_download_superseded_files
            | single_workspace_review_p2_superseded_files
            | single_workspace_pinch_save_superseded_files
            | single_workspace_host_retry_superseded_files
            | single_workspace_ci_save_font_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(independent_remediation["checks"].values())
    independent_checks = independent_remediation["check_evidence"]
    assert independent_checks["prior_visual_invalid"]["review_verdict"] == "NEEDS_CHANGE"
    assert independent_checks["prior_visual_invalid"]["parent_mutation"] is False
    assert independent_checks["visual_acceptance"]["decision"] == "accepted"
    assert independent_checks["browser_smoke"]["passed_count"] == 26
    assert independent_checks["browser_smoke"]["failed_count"] == 0
    assert independent_checks["pre_successor_full_validate"] == {
        "task_id": "ee5790c0ff444717801f94db",
        "passed_count": 1674,
        "failed_count": 2,
        "failures": [
            "expected immutable historical SHA supersession",
            "obsolete Export exact DOM assertion, separately repaired at 0ef33d9",
        ],
        "full_validate_pass_claim": False,
    }
    red = independent_checks["side_fit_red"]["cases"]
    green = independent_checks["side_fit_green"]["cases"]
    assert len(red) == len(green) == 2
    assert all(
        before["clearance_left_px"] < 0 and before["clearance_right_px"] < 0
        and after["clearance_left_px"] >= 8 and after["clearance_right_px"] >= 8
        and before["viewport_css"] == after["viewport_css"]
        and before["simulated_safe_area"] == after["simulated_safe_area"]
        for before, after in zip(red, green)
    )
    independent_visual = independent_remediation["visual_readback"]
    visual_bytes = (ROOT / independent_visual["path"]).read_bytes()
    assert hashlib.sha256(visual_bytes).hexdigest() == independent_visual["sha256"]
    visual_data = json.loads(visual_bytes)
    assert visual_data["functional_head"] == independent_remediation["functional_head"]
    assert visual_data["source_bindings"] == independent_remediation["source_bindings"]
    assert visual_data["native_child_styles_sha256"] == independent_visual[
        "native_css_sha256"
    ]
    assert independent_visual["case_count"] == len(visual_data["cases"]) == 5
    assert len(independent_visual["screenshots"]) == 5
    seen_viewports = set()
    for case in visual_data["cases"]:
        filename = case["screenshot_file"]
        saved = independent_visual["screenshots"][filename]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_INDEPENDENT_REMEDIATION_EVIDENCE / filename
        ).read_bytes()
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert saved["sha256"] == case["screenshot_sha256"] == hashlib.sha256(
            png
        ).hexdigest()
        assert saved["bytes"] == case["screenshot_bytes"] == len(png)
        assert saved["viewport_css"] == [case["width"], case["height"]]
        assert saved["safe_area_simulated"] == case["simulated_safe_inset"]
        key = (
            case["width"],
            case["height"],
            case["simulated_safe_inset"]["left"],
            case["simulated_safe_inset"]["right"],
        )
        seen_viewports.add(key)
        geom = case["geometry"]
        assert geom["native_css_sha256"] == independent_visual["native_css_sha256"]
        assert geom["native_reset_text"] == "↺"
        assert geom["aria"] == "Originalprojekt speichern"
        assert geom["short"] == '"Speichern"'
        left = case["simulated_safe_inset"]["left"]
        right = case["simulated_safe_inset"]["right"]
        assert geom["bar"]["left"] >= left - 0.5
        assert geom["bar"]["right"] <= case["width"] - right + 0.5
        assert geom["popover"]["left"] >= left - 0.5
        assert geom["popover"]["right"] <= case["width"] - right + 0.5
        assert abs(geom["stage"]["width"] - case["width"]) < 1
        assert abs(geom["stage"]["height"] - case["height"]) < 1
        assert all(
            item["width"] >= 38 and item["height"] >= 40
            and item["left"] >= left - 0.5
            and item["right"] <= case["width"] - right + 0.5
            for item in geom["controls"]
        )
    assert seen_viewports == {
        (320, 700, 0, 0),
        (320, 700, 0, 44),
        (320, 700, 44, 0),
        (390, 844, 0, 44),
        (390, 844, 44, 0),
    }

    # The preceding visual acceptance is immutable; this child binds the
    # exact later source revision and only four newly superseded SHA keys.
    late_path = (
        SCHAUBILD_SINGLE_WORKSPACE_LATE_REVIEW_MENUS_EVIDENCE
        / "acceptance-receipt.json"
    )
    late_menus = json.loads(late_path.read_text(encoding="utf-8"))
    assert late_menus["schema_version"] == (
        "schauwerk-schaubild-single-workspace-late-review-menus.v1"
    )
    assert late_menus["functional_head"] == (
        "884968fcdfb9759644ec26692ac1c8f8acb04fc9"
    )
    assert late_menus["parent_evidence"] == {
        "path": (
            "docs/operators/evidence/schaubild-single-workspace-independent-"
            "remediation-20261008/acceptance-receipt.json"
        ),
        "schema_version": independent_remediation["schema_version"],
        "file_sha256": hashlib.sha256(independent_path.read_bytes()).hexdigest(),
        "evidence_digest": independent_remediation["evidence_digest"],
    }
    assert late_menus["evidence_digest"] == digest_mapping(
        late_menus, "evidence_digest"
    )
    assert set(late_menus["source_bindings"]) == (
        single_workspace_late_review_menus_superseded_files
    )
    for name, expected in late_menus["source_bindings"].items():
        if name in (
            single_workspace_ci_download_superseded_files
            | single_workspace_ci_caption_safearea_superseded_files
        ):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(late_menus["checks"].values())
    finding_ids = {item["thread_id"] for item in
                   late_menus["check_evidence"]["codex_review_findings"]}
    assert finding_ids == {
        "PRRT_kwDOTGqvHc6qjHXz",
        "PRRT_kwDOTGqvHc6qjHYA",
    }
    assert late_menus["check_evidence"]["unsupported_details_red"]["failed_cases"] == 5
    green = late_menus["check_evidence"]["focused_green"]
    assert green["native_cases"] == 6 and green["details_cases"] == 5
    browser = late_menus["check_evidence"]["browser_smoke"]
    assert browser["passed_count"] == 27 and browser["failed_count"] == 0
    assert late_menus["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    red = late_menus["check_evidence"]["native_menu_red"]["cases"]
    assert all(item["left"] < 0 for item in red) and len(red) == 2
    visual = late_menus["visual_readback"]
    assert visual["case_count"] == 3 and len(visual["screenshots"]) == 3
    content = (ROOT / visual["path"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == visual["sha256"]
    report = json.loads(content)
    assert report["functional_head"] == late_menus["functional_head"]
    assert report["schema_version"] == visual["schema_version"]
    assert len(report["cases"]) == 3
    assert {(tuple(c["viewport"]),c["safe_insets"]["left"],c["safe_insets"]["right"])
            for c in report["cases"]} == {
        ((390,844),80,64), ((320,700),64,80), ((640,720),80,80),
    }
    for case in report["cases"]:
        entry = visual["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_LATE_REVIEW_MENUS_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert len(png) == entry["size"] == case["screenshot_bytes"]
        assert hashlib.sha256(png).hexdigest() == entry["sha256"] == case[
            "screenshot_sha256"
        ]
        assert case["edit_menu_safe_left_clearance"] >= 0
        assert case["edit_menu_safe_right_clearance"] >= 0
        assert case["menu"]["left"] >= case["safe_insets"]["left"]
        assert case["menu"]["right"] <= case["viewport"][0] - case[
            "safe_insets"
        ]["right"]
    # Keep the predecessor's immutable native stylesheet digest distinct from
    # the successor's changed production stylesheet.
    assert visual["native_source_css_sha256"] == (
        "1af50ed47c7c4046b569ac53b4f322f23f71ed1057280e67dee5602f1ad8710e"
    )

    # The current mobile download caption has a new production revision; the
    # previous accepted screenshots remain immutable and do not inherit PASS.
    download_path = SCHAUBILD_SINGLE_WORKSPACE_CI_DOWNLOAD_EVIDENCE / "acceptance-receipt.json"
    ci_download = json.loads(download_path.read_text(encoding="utf-8"))
    assert ci_download["schema_version"] == (
        "schauwerk-schaubild-single-workspace-ci-download.v1"
    )
    assert ci_download["functional_head"] == (
        "3f04561d3a1376e052e075b191b92b1f9bd6900e"
    )
    assert ci_download["parent_evidence"] == {
        "path": (
            "docs/operators/evidence/"
            "schaubild-single-workspace-late-review-menus-20261008/"
            "acceptance-receipt.json"
        ),
        "schema_version": late_menus["schema_version"],
        "file_sha256": hashlib.sha256(late_path.read_bytes()).hexdigest(),
        "evidence_digest": late_menus["evidence_digest"],
    }
    assert ci_download["evidence_digest"] == digest_mapping(
        ci_download, "evidence_digest"
    )
    assert set(ci_download["source_bindings"]) == (
        single_workspace_ci_download_superseded_files
    )
    for name, expected in ci_download["source_bindings"].items():
        if name in single_workspace_ci_caption_safearea_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(ci_download["checks"].values())
    checks = ci_download["check_evidence"]
    assert checks["prior_remote_red"]["python"] == "3.12"
    assert checks["prior_remote_red"]["failed_cases"] == 5
    assert checks["prior_remote_red"]["job_id"] == 113534469036
    assert checks["local_browser_green"]["case_count"] == 27
    assert checks["local_browser_green"]["failed_count"] == 0
    assert checks["static_green"]["test_count"] == 2
    assert checks["visual_acceptance"]["decision"] == "accepted"
    final_info = ci_download["visual_readback"]
    assert final_info["case_count"] == len(final_info["screenshots"]) == 5
    final_raw = (ROOT / final_info["path"]).read_bytes()
    assert hashlib.sha256(final_raw).hexdigest() == final_info["sha256"]
    final_visual = json.loads(final_raw)
    assert final_visual["functional_head"] == ci_download["functional_head"]
    assert final_visual["schema_version"] == final_info["schema_version"]
    assert len(final_visual["cases"]) == 5
    for name, expected in final_visual["source_bindings"].items():
        if name in (single_workspace_ci_caption_safearea_superseded_files
                    | single_workspace_review_p2_superseded_files
                    | single_workspace_pinch_save_superseded_files
                    | single_workspace_host_retry_superseded_files
                    | single_workspace_ci_save_font_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert {
        (c["width"], c["height"], c["simulated_safe_inset"]["left"],
         c["simulated_safe_inset"]["right"])
        for c in final_visual["cases"]
    } == {
        (320, 700, 0, 0), (320, 700, 0, 44), (320, 700, 44, 0),
        (390, 844, 0, 44), (390, 844, 44, 0),
    }
    for case in final_visual["cases"]:
        image = final_info["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_CI_DOWNLOAD_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert len(png) == image["bytes"] == case["screenshot_bytes"]
        assert hashlib.sha256(png).hexdigest() == image["sha256"] == case[
            "screenshot_sha256"
        ]
        geometry = case["geometry"]
        assert geometry["caption_display"] == "none"
        assert geometry["download_scroll_width"] <= geometry["download_client_width"] + 1
        assert geometry["aria"] == geometry["label"] == "Originalprojekt speichern"
        assert geometry["short"] == '"Speichern"'
        left = case["simulated_safe_inset"]["left"]
        right = case["simulated_safe_inset"]["right"]
        assert geometry["bar"]["left"] >= left - 0.5
        assert geometry["bar"]["right"] <= case["width"] - right + 0.5
        assert geometry["popover"]["left"] >= left - 0.5
        assert geometry["popover"]["right"] <= case["width"] - right + 0.5
        assert abs(geometry["stage"]["width"] - case["width"]) < 1
        assert abs(geometry["stage"]["height"] - case["height"]) < 1
    assert final_info["native_css_sha256"] == visual["native_source_css_sha256"]

    # Accept only the exact final post-caption + Native safe-area revision.
    final_path = (
        SCHAUBILD_SINGLE_WORKSPACE_CI_CAPTION_SAFEAREA_EVIDENCE
        / "acceptance-receipt.json"
    )
    final = json.loads(final_path.read_text(encoding="utf-8"))
    assert final["schema_version"] == (
        "schauwerk-schaubild-single-workspace-ci-caption-safearea.v1"
    )
    assert final["functional_head"] == (
        "d6e10ec63c9999f3b21a0a313d762cba341dc14b"
    )
    assert final["parent_evidence"] == {
        "path": str(download_path.relative_to(ROOT)),
        "file_sha256": hashlib.sha256(download_path.read_bytes()).hexdigest(),
        "evidence_digest": ci_download["evidence_digest"],
        "schema_version": ci_download["schema_version"],
    }
    assert final["evidence_digest"] == digest_mapping(final, "evidence_digest")
    assert set(final["source_bindings"]) == (
        single_workspace_ci_caption_safearea_superseded_files
    )
    for name, expected in final["source_bindings"].items():
        if name in (single_workspace_status_autofit_superseded_files
                    | single_workspace_embedded_host_superseded_files
                    | single_workspace_review_p2_superseded_files
                    | single_workspace_host_retry_superseded_files
                    | single_workspace_ci_save_font_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(final["checks"].values())
    assert final["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    assert final["check_evidence"]["native_green"]["passed_count"] == 6
    assert final["check_evidence"]["prior_remote_ci_failure"]["python"] == "3.12"
    assert final["check_evidence"]["prior_remote_ci_failure"]["failed_cases"] == 5
    from schauwerk.resources.native_viewer.assets import ASSETS as current_native

    current_native_css_sha = hashlib.sha256(
        current_native["styles.css"].encode("utf-8")
    ).hexdigest()
    # Historic CDP captures are bound to their immutable original CSS revision.
    # New production CSS is checked against the new acceptance source digest.
    native_css_sha = json.loads(
        (SCHAUBILD_SINGLE_WORKSPACE_POINTER_OWNER_EVIDENCE
         / "acceptance-receipt.json").read_text(encoding="utf-8")
    )["visual_readbacks"]["drag"]["native_css_sha256"]
    assert current_native_css_sha != native_css_sha
    old_final_native_css_sha = final["visual_readbacks"]["native"]["native_styles_sha256"]
    assert old_final_native_css_sha != final_info["native_css_sha256"]
    assert native_css_sha != old_final_native_css_sha
    expected_cases = {
        "host": {
            (320, 700, 0, 0), (320, 700, 44, 0), (320, 700, 0, 44),
            (390, 844, 44, 0), (390, 844, 0, 44),
        },
        "native": {
            (320, 700, 64, 80), (390, 844, 80, 64), (640, 720, 80, 80),
        },
    }
    for kind, meta in final["visual_readbacks"].items():
        assert kind in expected_cases
        payload = (ROOT / meta["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == meta["sha256"]
        readback = json.loads(payload)
        assert readback["schema_version"] == meta["schema_version"]
        assert readback["functional_head"] == final["functional_head"]
        assert len(readback["cases"]) == meta["case_count"] == len(
            meta["screenshots"]
        )
        assert meta["native_styles_sha256"] == old_final_native_css_sha
        css_binding = (
            readback["native_child_styles_sha256"]
            if kind == "host" else readback["native_styles_sha256"]
        )
        assert css_binding == old_final_native_css_sha
        for name, sha in readback["source_bindings"].items():
            if name in (single_workspace_status_autofit_superseded_files
                        | single_workspace_embedded_host_superseded_files
                        | single_workspace_review_p2_superseded_files
                        | single_workspace_pinch_save_superseded_files
                        | single_workspace_host_retry_superseded_files
                        | single_workspace_ci_save_font_superseded_files):
                continue
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
        seen_cases = set()
        for case in readback["cases"]:
            area = (
                case["simulated_safe_inset"]
                if kind == "host" else case["safe_area"]
            )
            width, height = case["width"], case["height"]
            seen_cases.add((width, height, area["left"], area["right"]))
            entry = meta["screenshots"][case["screenshot_file"]]
            assert entry["viewport"] == [width, height]
            assert entry["safe_area"] == area
            png = (
                SCHAUBILD_SINGLE_WORKSPACE_CI_CAPTION_SAFEAREA_EVIDENCE
                / case["screenshot_file"]
            ).read_bytes()
            assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
            assert int.from_bytes(png[16:20], "big") == width
            assert int.from_bytes(png[20:24], "big") == height
            assert len(png) == entry["bytes"] == case["screenshot_bytes"]
            assert (
                hashlib.sha256(png).hexdigest()
                == entry["sha256"]
                == case["screenshot_sha256"]
            )
            geom = case["geometry"]
            assert geom["bar"]["left"] >= area["left"] - 0.5
            assert geom["bar"]["right"] <= width - area["right"] + 0.5
            assert abs(geom["stage"]["width"] - width) < 1
            assert abs(geom["stage"]["height"] - height) < 1
            if kind == "host":
                assert geom["short"] == "Speichern"
                assert geom["short_display"] == "block"
                assert geom["caption_display"] == "none"
                assert geom["aria"] == geom["label"] == "Originalprojekt speichern"
                assert geom["pseudo_content"] == "none"
                assert geom["download_scroll_width"] <= geom["download_client_width"] + 1
                assert geom["short_scroll_width"] <= geom["short_client_width"] + 1
                assert geom["popover"]["left"] >= area["left"] - 0.5
                assert geom["popover"]["right"] <= width - area["right"] + 0.5
                assert all(
                    item["left"] >= area["left"] - 0.5
                    and item["right"] <= width - area["right"] + 0.5
                    for item in geom["controls"]
                )
            else:
                assert geom["footer"]["left"] >= area["left"] - 0.5
                assert geom["footer"]["right"] <= width - area["right"] + 0.5
                assert geom["edit_menu"]["left"] >= area["left"] - 0.5
                assert geom["edit_menu"]["right"] <= width - area["right"] + 0.5
                assert all(
                    item["left"] >= area["left"] - 0.5
                    and item["right"] <= width - area["right"] + 0.5
                    for item in geom["targets"]
                )
                assert geom["selection_text_length"] >= 100
                if width == 390:
                    assert geom["view"]["height"] <= 100
        assert seen_cases == expected_cases[kind]
    # Rejected/staging screenshots are bound as historical bytes, never granted
    # the final acceptance or treated as a current source.
    unaccepted = final["check_evidence"]["before_unaccepted"]
    assert len(unaccepted) == 3
    for predecessor in unaccepted:
        raw_before = (ROOT / predecessor["path"]).read_bytes()
        assert hashlib.sha256(raw_before).hexdigest() == predecessor["file_sha256"]
        observed = json.loads(raw_before)
        assert observed["functional_head"] == predecessor["functional_head"]
        assert "not inherited" in predecessor["acceptance"]
        for case in observed["cases"]:
            image = (ROOT / predecessor["path"]).parent / case["screenshot_file"]
            assert hashlib.sha256(image.read_bytes()).hexdigest() == (
                case["screenshot_sha256"]
            )

    # The accepted d6e10ec visual package is historical, not inherited after
    # the Native hosted mobile prompt width/source changed at 1e1b1e8.
    prompt_path = (
        SCHAUBILD_SINGLE_WORKSPACE_MOBILE_PROMPT_WIDTH_EVIDENCE
        / "acceptance-receipt.json"
    )
    prompt_acceptance = json.loads(prompt_path.read_text(encoding="utf-8"))
    assert prompt_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-mobile-prompt-width.v1"
    )
    assert prompt_acceptance["functional_head"] == (
        "1e1b1e82dc7b5de16c755a97e9224b803026fc59"
    )
    assert prompt_acceptance["parent_evidence"] == {
        "path": str(final_path.relative_to(ROOT)),
        "schema_version": final["schema_version"],
        "file_sha256": hashlib.sha256(final_path.read_bytes()).hexdigest(),
        "evidence_digest": final["evidence_digest"],
    }
    assert prompt_acceptance["evidence_digest"] == digest_mapping(
        prompt_acceptance, "evidence_digest"
    )
    assert set(prompt_acceptance["source_bindings"]) == (
        single_workspace_mobile_prompt_width_superseded_files
    )
    for name, sha in prompt_acceptance["source_bindings"].items():
        if name in (single_workspace_status_autofit_superseded_files
                    | single_workspace_embedded_host_superseded_files
                    | single_workspace_review_p2_superseded_files
                    | single_workspace_pinch_save_superseded_files
                    | single_workspace_host_retry_superseded_files
                    | single_workspace_ci_save_font_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    assert all(prompt_acceptance["checks"].values())
    prompt_checks = prompt_acceptance["check_evidence"]
    assert prompt_checks["prior_local_red"]["failed_count"] == 3
    assert prompt_checks["focused_browser_green"]["passed_count"] == 11
    assert prompt_checks["focused_browser_green"]["failed_count"] == 0
    assert prompt_checks["visual_acceptance"]["decision"] == "accepted"
    prompt_expected_cases = {
        "host": {
            (320, 700, 0, 0), (320, 700, 44, 0), (320, 700, 0, 44),
            (390, 844, 44, 0), (390, 844, 0, 44),
        },
        "native": {
            (320, 700, 64, 80), (390, 844, 80, 64), (640, 720, 80, 80),
        },
        "process": {
            (320, 700, 0, 0), (320, 700, 44, 0), (320, 700, 0, 44),
        },
    }
    assert set(prompt_acceptance["visual_readbacks"]) == set(prompt_expected_cases)
    for kind, meta in prompt_acceptance["visual_readbacks"].items():
        payload = (ROOT / meta["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == meta["sha256"]
        readback = json.loads(payload)
        assert readback["schema_version"] == meta["schema_version"]
        assert readback["functional_head"] == prompt_acceptance["functional_head"]
        assert len(readback["cases"]) == meta["case_count"] == len(
            meta["screenshots"]
        )
        assert meta["native_css_sha256"] == native_css_sha
        actual_css_binding = (
            readback["native_styles_sha256"]
            if kind == "native" else readback["native_child_styles_sha256"]
        )
        assert actual_css_binding == native_css_sha
        for name, sha in readback["source_bindings"].items():
            if name in (single_workspace_status_autofit_superseded_files
                        | single_workspace_embedded_host_superseded_files
                        | single_workspace_review_p2_superseded_files
                        | single_workspace_pinch_save_superseded_files
                        | single_workspace_host_retry_superseded_files
                        | single_workspace_ci_save_font_superseded_files):
                continue
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
        covered = set()
        for case in readback["cases"]:
            area = (
                case["safe_area"] if kind == "native"
                else case["simulated_safe_inset"]
            )
            width, height = case["width"], case["height"]
            key = (width, height, area["left"], area["right"])
            assert key not in covered
            covered.add(key)
            evidence_png = (
                SCHAUBILD_SINGLE_WORKSPACE_MOBILE_PROMPT_WIDTH_EVIDENCE
                / case["screenshot_file"]
            ).read_bytes()
            bound = meta["screenshots"][case["screenshot_file"]]
            assert bound["viewport"] == [width, height]
            assert bound["safe_area"] == area
            assert evidence_png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
            assert int.from_bytes(evidence_png[16:20], "big") == width
            assert int.from_bytes(evidence_png[20:24], "big") == height
            assert len(evidence_png) == bound["bytes"] == case["screenshot_bytes"]
            assert (
                hashlib.sha256(evidence_png).hexdigest()
                == bound["sha256"] == case["screenshot_sha256"]
            )
            geom = case["geometry"]
            assert abs(geom["stage"]["width"] - width) < 1
            assert abs(geom["stage"]["height"] - height) < 1
            usable_right = width - area["right"]
            if kind == "host":
                assert geom["bar"]["left"] >= area["left"] - 0.5
                assert geom["bar"]["right"] <= usable_right + 0.5
                assert geom["popover"]["left"] >= area["left"] - 0.5
                assert geom["popover"]["right"] <= usable_right + 0.5
                assert geom["aria"] == geom["label"] == "Originalprojekt speichern"
                assert geom["short"] == "Speichern"
                assert geom["short_display"] == "block"
                assert geom["caption_display"] == "none"
                assert geom["pseudo_content"] == "none"
                assert geom["download_scroll_width"] <= geom["download_client_width"] + 1
                assert geom["short_scroll_width"] <= geom["short_client_width"] + 1
                assert all(
                    x["left"] >= area["left"] - 0.5
                    and x["right"] <= usable_right + 0.5
                    for x in geom["controls"]
                )
            elif kind == "native":
                for name in ("bar", "footer", "edit_menu"):
                    assert geom[name]["left"] >= area["left"] - 0.5
                    assert geom[name]["right"] <= usable_right + 0.5
                assert all(
                    x["left"] >= area["left"] - 0.5
                    and x["right"] <= usable_right + 0.5
                    for x in geom["targets"]
                )
                if width == 390:
                    assert geom["view"]["height"] <= 100
            else:
                assert geom["status_text"] == "Ziel für die neue Verbindung auswählen"
                assert geom["status"]["width"] >= 160
                assert geom["status"]["height"] >= 20
                assert geom["status_scroll_width"] <= geom["status_client_width"] + 1
                assert geom["status_scroll_height"] <= geom["status_client_height"] + 1
                assert geom["overlap_area"] <= 0.5
                assert geom["visibility"] == "visible"
                assert geom["host_bar"]["left"] >= area["left"] - 0.5
                assert geom["host_bar"]["right"] <= usable_right + 0.5
        assert covered == prompt_expected_cases[kind]
    # The 088269c status-autofit revision supersedes two exact source/test SHA
    # bindings without inheriting the prior prompt-width visual acceptance.
    status_path = (
        SCHAUBILD_SINGLE_WORKSPACE_STATUS_AUTOFIT_EVIDENCE
        / "acceptance-receipt.json"
    )
    status_acceptance = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-status-autofit.v1"
    )
    assert status_acceptance["functional_head"] == (
        "088269c96f8bdb63b3f7fe0ae964e5c4ddbd5394"
    )
    assert status_acceptance["parent_evidence"] == {
        "path": str(prompt_path.relative_to(ROOT)),
        "schema_version": prompt_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "evidence_digest": prompt_acceptance["evidence_digest"],
    }
    assert status_acceptance["evidence_digest"] == digest_mapping(
        status_acceptance, "evidence_digest"
    )
    assert set(status_acceptance["source_bindings"]) == (
        single_workspace_status_autofit_superseded_files
    )
    for name, expected in status_acceptance["source_bindings"].items():
        if name in single_workspace_status_drag_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(status_acceptance["checks"].values())
    assert status_acceptance["check_evidence"]["prior_local_red"]["task_id"] == (
        "e481f696f319476c9a94416b"
    )
    assert status_acceptance["check_evidence"]["focused_browser_green"]["passed_count"] == 2
    assert status_acceptance["check_evidence"]["focused_browser_green"]["failed_count"] == 0
    assert status_acceptance["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    status_meta = status_acceptance["visual_readbacks"]["status_fit"]
    assert set(status_acceptance["visual_readbacks"]) == {"status_fit"}
    status_raw = (ROOT / status_meta["path"]).read_bytes()
    assert hashlib.sha256(status_raw).hexdigest() == status_meta["sha256"]
    status_readback = json.loads(status_raw)
    assert status_readback["schema_version"] == status_meta["schema_version"]
    assert status_readback["functional_head"] == status_acceptance["functional_head"]
    assert status_readback["source_bindings"] == status_acceptance["source_bindings"]
    assert status_meta["native_css_sha256"] == native_css_sha
    assert status_readback["native_child_styles_sha256"] == native_css_sha
    assert len(status_readback["cases"]) == status_meta["case_count"] == 4
    expected_status_cases = {
        (320, 700, 0, 0), (320, 700, 44, 0),
        (390, 844, 44, 0), (390, 844, 0, 44),
    }
    covered_status_cases = set()
    for case in status_readback["cases"]:
        area = case["simulated_safe_inset"]
        width, height = case["width"], case["height"]
        key = (width, height, area["left"], area["right"])
        assert key in expected_status_cases and key not in covered_status_cases
        covered_status_cases.add(key)
        bound = status_meta["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_STATUS_AUTOFIT_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert bound["safe_area"] == area and bound["viewport"] == [width, height]
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == bound["sha256"] == case["screenshot_sha256"]
        )
        geometry = case["geometry"]
        assert geometry["status_text"].startswith("Produktgrenze erreicht")
        assert geometry["bar_after"]["bottom"] - geometry["bar_before"]["bottom"] > 1
        assert geometry["clearance_after"] >= 8
        assert geometry["status_scroll_width"] <= geometry["status_client_width"] + 1
        assert geometry["status_scroll_height"] <= geometry["status_client_height"] + 1
        assert geometry["overlap_area"] <= 0.5
        assert geometry["visibility"] == "visible"
        assert abs(geometry["stage"]["width"] - width) < 1
        assert abs(geometry["stage"]["height"] - height) < 1
        assert geometry["host_bar"]["left"] >= area["left"] - 0.5
        assert geometry["host_bar"]["right"] <= width - area["right"] + 0.5
    assert covered_status_cases == expected_status_cases
    # New 9013357 drag interaction explicitly supersedes the two source/test
    # bindings of 088269c; no visual acceptance transfers automatically.
    drag_path = (
        SCHAUBILD_SINGLE_WORKSPACE_STATUS_DRAG_EVIDENCE / "acceptance-receipt.json"
    )
    drag_acceptance = json.loads(drag_path.read_text(encoding="utf-8"))
    assert drag_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-drag-status.v1"
    )
    assert drag_acceptance["functional_head"] == (
        "901335742df80f2e6169f6e921e34b24f51d78fc"
    )
    assert drag_acceptance["parent_evidence"] == {
        "path": str(status_path.relative_to(ROOT)),
        "schema_version": status_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(status_path.read_bytes()).hexdigest(),
        "evidence_digest": status_acceptance["evidence_digest"],
    }
    assert drag_acceptance["evidence_digest"] == digest_mapping(
        drag_acceptance, "evidence_digest"
    )
    assert set(drag_acceptance["source_bindings"]) == (
        single_workspace_status_drag_superseded_files
    )
    for name, sha in drag_acceptance["source_bindings"].items():
        if name in single_workspace_gesture_cancel_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    assert all(drag_acceptance["checks"].values())
    drag_checks = drag_acceptance["check_evidence"]
    assert drag_checks["prior_local_red"]["task_id"] == "5cf36257993c46089c23a17f"
    assert drag_checks["focused_browser_green"]["passed_count"] == 3
    assert drag_checks["focused_browser_green"]["failed_count"] == 0
    assert drag_checks["visual_acceptance"]["decision"] == "accepted"
    assert set(drag_acceptance["visual_readbacks"]) == {"drag"}
    drag_meta = drag_acceptance["visual_readbacks"]["drag"]
    drag_raw = (ROOT / drag_meta["path"]).read_bytes()
    assert hashlib.sha256(drag_raw).hexdigest() == drag_meta["sha256"]
    drag_readback = json.loads(drag_raw)
    assert drag_readback["schema_version"] == drag_meta["schema_version"]
    assert drag_readback["functional_head"] == drag_acceptance["functional_head"]
    assert drag_readback["source_bindings"] == drag_acceptance["source_bindings"]
    assert drag_meta["native_css_sha256"] == native_css_sha
    assert drag_readback["native_child_styles_sha256"] == native_css_sha
    assert len(drag_readback["cases"]) == drag_meta["case_count"] == 2
    expected_drag_cases = {(390, 844, 44, 0), (390, 844, 0, 44)}
    covered_drag_cases = set()
    for case in drag_readback["cases"]:
        area = case["simulated_safe_inset"]
        width, height = case["width"], case["height"]
        key = (width, height, area["left"], area["right"])
        assert key in expected_drag_cases and key not in covered_drag_cases
        covered_drag_cases.add(key)
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_STATUS_DRAG_EVIDENCE / case["screenshot_file"]
        ).read_bytes()
        bound = drag_meta["screenshots"][case["screenshot_file"]]
        assert bound["viewport"] == [width, height]
        assert bound["safe_area"] == area
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == bound["sha256"] == case["screenshot_sha256"]
        )
        geom = case["geometry"]
        assert geom["status_text"] == "Position geändert · Verbindungen angepasst"
        assert geom["view_before"] == geom["view_during"] == geom["view_after"]
        assert geom["node_move_px"] >= 20
        assert geom["active_drag"] is True
        assert geom["bar_during"]["bottom"] - geom["bar_before"]["bottom"] >= 20
        assert geom["status_scroll_width"] <= geom["status_client_width"] + 1
        assert geom["status_scroll_height"] <= geom["status_client_height"] + 1
        assert geom["overlap_area"] <= 0.5 and geom["visibility"] == "visible"
        assert abs(geom["stage"]["width"] - width) < 1
        assert abs(geom["stage"]["height"] - height) < 1
        assert geom["host_bar"]["left"] >= area["left"] - 0.5
        assert geom["host_bar"]["right"] <= width - area["right"] + 0.5
    assert covered_drag_cases == expected_drag_cases
    # The 4fe085f gesture correction is a newly accepted revision, not an
    # inheritance of the previous status-drag visual acceptance.
    gesture_path = (
        SCHAUBILD_SINGLE_WORKSPACE_GESTURE_CANCEL_EVIDENCE
        / "acceptance-receipt.json"
    )
    gesture_acceptance = json.loads(gesture_path.read_text(encoding="utf-8"))
    assert gesture_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-gesture-cancel.v1"
    )
    assert gesture_acceptance["functional_head"] == (
        "4fe085ffc9f9d2e9635f62581c789b6b65a921df"
    )
    assert gesture_acceptance["parent_evidence"] == {
        "path": str(drag_path.relative_to(ROOT)),
        "schema_version": drag_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(drag_path.read_bytes()).hexdigest(),
        "evidence_digest": drag_acceptance["evidence_digest"],
    }
    assert gesture_acceptance["evidence_digest"] == digest_mapping(
        gesture_acceptance, "evidence_digest"
    )
    assert set(gesture_acceptance["source_bindings"]) == (
        single_workspace_gesture_cancel_superseded_files
    )
    for name, digest in gesture_acceptance["source_bindings"].items():
        if name in single_workspace_pointer_owner_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert all(gesture_acceptance["checks"].values())
    assert gesture_acceptance["check_evidence"]["prior_local_red"]["task_id"] == (
        "157f8573df4845e99b0f859a"
    )
    assert gesture_acceptance["check_evidence"]["focused_browser_green"]["passed_count"] == 3
    assert gesture_acceptance["check_evidence"]["focused_browser_green"]["failed_count"] == 0
    assert gesture_acceptance["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    assert set(gesture_acceptance["visual_readbacks"]) == {"drag"}
    gesture_meta = gesture_acceptance["visual_readbacks"]["drag"]
    gesture_raw = (ROOT / gesture_meta["path"]).read_bytes()
    assert hashlib.sha256(gesture_raw).hexdigest() == gesture_meta["sha256"]
    gesture_readback = json.loads(gesture_raw)
    assert gesture_readback["schema_version"] == gesture_meta["schema_version"]
    assert gesture_readback["functional_head"] == gesture_acceptance["functional_head"]
    assert gesture_readback["source_bindings"] == gesture_acceptance["source_bindings"]
    assert gesture_meta["native_css_sha256"] == native_css_sha
    assert gesture_readback["native_child_styles_sha256"] == native_css_sha
    assert len(gesture_readback["cases"]) == gesture_meta["case_count"] == 2
    gesture_seen = set()
    for case in gesture_readback["cases"]:
        area = case["simulated_safe_inset"]
        width, height = case["width"], case["height"]
        key = (width, height, area["left"], area["right"])
        assert key in {(390, 844, 44, 0), (390, 844, 0, 44)}
        assert key not in gesture_seen
        gesture_seen.add(key)
        bound = gesture_meta["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_GESTURE_CANCEL_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert bound["viewport"] == [width, height]
        assert bound["safe_area"] == area
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == bound["sha256"] == case["screenshot_sha256"]
        )
        geom = case["geometry"]
        assert geom["status_text"] == "Position geändert · Verbindungen angepasst"
        assert geom["view_before"] == geom["view_during"] == geom["view_after"]
        assert geom["node_move_px"] >= 20 and geom["active_drag"] is True
        assert geom["bar_during"]["bottom"] - geom["bar_before"]["bottom"] >= 20
        assert geom["status_scroll_width"] <= geom["status_client_width"] + 1
        assert geom["status_scroll_height"] <= geom["status_client_height"] + 1
        assert geom["overlap_area"] <= 0.5 and geom["visibility"] == "visible"
        assert abs(geom["stage"]["width"] - width) < 1
        assert abs(geom["stage"]["height"] - height) < 1
        assert geom["host_bar"]["left"] >= area["left"] - 0.5
        assert geom["host_bar"]["right"] <= width - area["right"] + 0.5
    assert gesture_seen == {(390, 844, 44, 0), (390, 844, 0, 44)}
    # The 50dc336 pointer-owner invariant requires independent new visual
    # acceptance; the previous gesture-cancel revision remains immutable.
    owner_path = (
        SCHAUBILD_SINGLE_WORKSPACE_POINTER_OWNER_EVIDENCE
        / "acceptance-receipt.json"
    )
    owner_acceptance = json.loads(owner_path.read_text(encoding="utf-8"))
    assert owner_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-pointer-owner.v1"
    )
    assert owner_acceptance["functional_head"] == (
        "50dc336282efbbfd3f8d86522b59c70946b28f13"
    )
    assert owner_acceptance["parent_evidence"] == {
        "path": str(gesture_path.relative_to(ROOT)),
        "schema_version": gesture_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(gesture_path.read_bytes()).hexdigest(),
        "evidence_digest": gesture_acceptance["evidence_digest"],
    }
    assert owner_acceptance["evidence_digest"] == digest_mapping(
        owner_acceptance, "evidence_digest"
    )
    assert set(owner_acceptance["source_bindings"]) == (
        single_workspace_pointer_owner_superseded_files
    )
    for name, sha in owner_acceptance["source_bindings"].items():
        if name in (single_workspace_tap_autofit_superseded_files
                    | single_workspace_embedded_host_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    assert all(owner_acceptance["checks"].values())
    assert owner_acceptance["check_evidence"]["prior_local_red"]["task_id"] == (
        "f8f11e18f2b94371a4f2b8c5"
    )
    assert owner_acceptance["check_evidence"]["focused_browser_green"]["passed_count"] == 3
    assert owner_acceptance["check_evidence"]["focused_browser_green"]["failed_count"] == 0
    assert owner_acceptance["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    assert set(owner_acceptance["visual_readbacks"]) == {"drag"}
    owner_meta = owner_acceptance["visual_readbacks"]["drag"]
    owner_raw = (ROOT / owner_meta["path"]).read_bytes()
    assert hashlib.sha256(owner_raw).hexdigest() == owner_meta["sha256"]
    owner_readback = json.loads(owner_raw)
    assert owner_readback["schema_version"] == owner_meta["schema_version"]
    assert owner_readback["functional_head"] == owner_acceptance["functional_head"]
    assert owner_readback["source_bindings"] == owner_acceptance["source_bindings"]
    assert owner_meta["native_css_sha256"] == native_css_sha
    assert owner_readback["native_child_styles_sha256"] == native_css_sha
    assert len(owner_readback["cases"]) == owner_meta["case_count"] == 2
    owner_cases = set()
    for case in owner_readback["cases"]:
        area = case["simulated_safe_inset"]
        width, height = case["width"], case["height"]
        key = (width, height, area["left"], area["right"])
        assert key in {(390, 844, 44, 0), (390, 844, 0, 44)}
        assert key not in owner_cases
        owner_cases.add(key)
        bound = owner_meta["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_POINTER_OWNER_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert bound["viewport"] == [width, height]
        assert bound["safe_area"] == area
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == bound["sha256"] == case["screenshot_sha256"]
        )
        geom = case["geometry"]
        assert geom["status_text"] == "Position geändert · Verbindungen angepasst"
        assert geom["view_before"] == geom["view_during"] == geom["view_after"]
        assert geom["node_move_px"] >= 20 and geom["active_drag"] is True
        assert geom["bar_during"]["bottom"] - geom["bar_before"]["bottom"] >= 20
        assert geom["status_scroll_width"] <= geom["status_client_width"] + 1
        assert geom["status_scroll_height"] <= geom["status_client_height"] + 1
        assert geom["overlap_area"] <= 0.5 and geom["visibility"] == "visible"
        assert abs(geom["stage"]["width"] - width) < 1
        assert abs(geom["stage"]["height"] - height) < 1
        assert geom["host_bar"]["left"] >= area["left"] - 0.5
        assert geom["host_bar"]["right"] <= width - area["right"] + 0.5
    assert owner_cases == {(390, 844, 44, 0), (390, 844, 0, 44)}
    # The Tap-only / fully-canceled-drag revision has its own visual
    # acceptance. Historical source hashes remain exact for prior revisions.
    tap_path = (
        SCHAUBILD_SINGLE_WORKSPACE_TAP_AUTOFIT_ROLLBACK_EVIDENCE
        / "acceptance-receipt.json"
    )
    tap_acceptance = json.loads(tap_path.read_text(encoding="utf-8"))
    assert tap_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-tap-autofit-rollback.v1"
    )
    assert tap_acceptance["functional_head"] == (
        "25ac38668cfa049489dc5f5715de01c2b9d7192a"
    )
    assert tap_acceptance["parent_evidence"] == {
        "path": str(owner_path.relative_to(ROOT)),
        "schema_version": owner_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest(),
        "evidence_digest": owner_acceptance["evidence_digest"],
    }
    assert tap_acceptance["evidence_digest"] == digest_mapping(
        tap_acceptance, "evidence_digest"
    )
    assert set(tap_acceptance["source_bindings"]) == (
        single_workspace_tap_autofit_superseded_files
    )
    for name, sha in tap_acceptance["source_bindings"].items():
        if name in (single_workspace_embedded_host_superseded_files
                    | single_workspace_review_p2_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    assert all(tap_acceptance["checks"].values())
    evidence = tap_acceptance["check_evidence"]
    assert evidence["tap_only_red"]["job_id"] == "9832d98768bf"
    assert evidence["canceled_drag_red"]["job_id"] == "2357a906c423"
    assert evidence["focused_green"]["passed_count"] == 1
    assert evidence["focused_green"]["failed_count"] == 0
    assert evidence["browser_smoke_green"]["passed_count"] == 28
    assert evidence["browser_smoke_green"]["failed_count"] == 0
    assert evidence["visual_acceptance"]["decision"] == "accepted"
    assert set(tap_acceptance["visual_readbacks"]) == {"tap_resize"}
    tap_meta = tap_acceptance["visual_readbacks"]["tap_resize"]
    tap_raw = (ROOT / tap_meta["path"]).read_bytes()
    assert hashlib.sha256(tap_raw).hexdigest() == tap_meta["sha256"]
    tap_readback = json.loads(tap_raw)
    assert tap_readback["schema_version"] == tap_meta["schema_version"]
    assert tap_readback["functional_head"] == tap_acceptance["functional_head"]
    assert tap_readback["source_bindings"] == tap_acceptance["source_bindings"]
    assert len(tap_readback["cases"]) == tap_meta["case_count"] == 2
    tap_seen = set()
    for case in tap_readback["cases"]:
        safe = case["simulated_safe_inset"]
        width, height = case["viewport"]
        key = (width, height, safe["left"], safe["right"])
        assert key in {(390, 844, 44, 0), (390, 844, 0, 44)}
        assert key not in tap_seen
        tap_seen.add(key)
        binding = tap_meta["screenshots"][case["screenshot_file"]]
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_TAP_AUTOFIT_ROLLBACK_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == binding["bytes"] == case["screenshot_bytes"]
        assert hashlib.sha256(png).hexdigest() == binding["sha256"] == case["screenshot_sha256"]
        assert binding["viewport"] == [width, height]
        assert binding["safe_area"] == safe
        geom = case["geometry"]
        assert (geom["width"], geom["height"]) == (width, height)
        assert geom["selected"] == "true" and not geom["documentOverflow"]
        assert geom["view"] == case["view_before"]
        assert case["view_after_tap_resize_320"] != case["view_before"]
        assert geom["topMarker"]["top"] >= geom["bar"]["bottom"] + 7.5
        assert geom["node"]["top"] >= geom["bar"]["bottom"] + 7.5
        assert not geom["statusOverflow"] or geom["statusEllipsis"]
        for control in geom["controls"]:
            bounds = control["bounds"]
            assert bounds["left"] >= safe["left"] - 0.5
            assert bounds["right"] <= width - safe["right"] + 0.5
    assert tap_seen == {(390, 844, 44, 0), (390, 844, 0, 44)}

    # New visual acceptance for embedded-host geometry; no old approval inherited.
    host_path = (SCHAUBILD_SINGLE_WORKSPACE_EMBEDDED_HOST_SAFEAREA_EVIDENCE
                 / "acceptance-receipt.json")
    host_acceptance = json.loads(host_path.read_text(encoding="utf-8"))
    assert host_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-embedded-host-safearea.v1"
    )
    assert host_acceptance["functional_head"] == (
        "271b0c988a82d23158c18721a8fb84441f25f3b4"
    )
    assert host_acceptance["parent_evidence"] == {
        "path": str(tap_path.relative_to(ROOT)),
        "schema_version": tap_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(tap_path.read_bytes()).hexdigest(),
        "evidence_digest": tap_acceptance["evidence_digest"],
    }
    assert host_acceptance["evidence_digest"] == digest_mapping(
        host_acceptance, "evidence_digest"
    )
    assert set(host_acceptance["source_bindings"]) == (
        single_workspace_embedded_host_superseded_files
    )
    for name, expected in host_acceptance["source_bindings"].items():
        if name in single_workspace_review_p2_superseded_files:
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(host_acceptance["checks"].values())
    assert host_acceptance["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    assert host_acceptance["check_evidence"]["browser_smoke_green"]["passed_count"] == 28
    assert host_acceptance["check_evidence"]["focused_green"]["passed_count"] == 5
    assert host_acceptance["check_evidence"]["capture_green"]["passed_count"] == 2
    assert set(host_acceptance["visual_readbacks"]) == {"host_safearea"}
    host_meta = host_acceptance["visual_readbacks"]["host_safearea"]
    raw_host_readback = (ROOT / host_meta["path"]).read_bytes()
    assert hashlib.sha256(raw_host_readback).hexdigest() == host_meta["sha256"]
    host_readback = json.loads(raw_host_readback)
    assert host_readback["schema_version"] == host_meta["schema_version"]
    assert host_readback["functional_head"] == host_acceptance["functional_head"]
    assert host_readback["source_bindings"] == host_acceptance["source_bindings"]
    assert len(host_readback["cases"]) == host_meta["case_count"] == 2
    host_seen = set()
    for case in host_readback["cases"]:
        area = case["safe_area"]
        width, height = case["viewport"]
        key = (width, height, area["left"], area["right"])
        assert key in {(390, 844, 44, 0), (390, 844, 0, 44)}
        assert key not in host_seen
        host_seen.add(key)
        bound = host_meta["screenshots"][case["screenshot_file"]]
        png = (SCHAUBILD_SINGLE_WORKSPACE_EMBEDDED_HOST_SAFEAREA_EVIDENCE
               / case["screenshot_file"]).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (hashlib.sha256(png).hexdigest()
                == bound["sha256"] == case["screenshot_sha256"])
        readback_file = (SCHAUBILD_SINGLE_WORKSPACE_EMBEDDED_HOST_SAFEAREA_EVIDENCE
                         / case["geometry_readback_file"])
        assert hashlib.sha256(readback_file.read_bytes()).hexdigest() == (
            case["geometry_readback_sha256"]
        )
        assert json.loads(readback_file.read_text(encoding="utf-8"))["geometry"] == case["geometry"]
        g = case["geometry"]["native"]
        assert g["bar"]["left"] >= area["left"] - 0.5
        assert g["bar"]["right"] <= width - area["right"] + 0.5
        assert g["footer"]["left"] >= area["left"] - 0.5
        assert g["footer"]["right"] <= width - area["right"] + 0.5
        assert case["native_footer_host_action_overlap_area"] <= 0.5
        for control in g["controls"]:
            assert control["rect"]["left"] >= area["left"] - 0.5
            assert control["rect"]["right"] <= width - area["right"] + 0.5
    assert host_seen == {(390, 844, 44, 0), (390, 844, 0, 44)}

    # Exact successor after the independent review's three P2 remediations:
    # old visual evidence remains bound to its own unchanged source revision.
    review_p2_path = (
        SCHAUBILD_SINGLE_WORKSPACE_REVIEW_P2_EVIDENCE
        / "acceptance-receipt.json"
    )
    review_p2_acceptance = json.loads(review_p2_path.read_text(encoding="utf-8"))
    assert review_p2_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-review-p2.v1"
    )
    assert review_p2_acceptance["functional_head"] == (
        "cb6dcc148a4f2ff3a49f2052456b94765a07598a"
    )
    assert review_p2_acceptance["parent_evidence"] == {
        "path": str(host_path.relative_to(ROOT)),
        "schema_version": host_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(host_path.read_bytes()).hexdigest(),
        "evidence_digest": host_acceptance["evidence_digest"],
    }
    assert review_p2_acceptance["evidence_digest"] == digest_mapping(
        review_p2_acceptance, "evidence_digest"
    )
    assert set(review_p2_acceptance["source_bindings"]) == (
        single_workspace_review_p2_superseded_files
    )
    for name, expected in review_p2_acceptance["source_bindings"].items():
        if name in (single_workspace_pinch_save_superseded_files
                    | single_workspace_host_retry_superseded_files
                    | single_workspace_ci_save_font_superseded_files):
            continue
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(review_p2_acceptance["checks"].values())
    review_evidence = review_p2_acceptance["check_evidence"]
    assert review_evidence["reviewer_p2"]["finding_count"] == 3
    assert review_evidence["focused_green"]["passed_count"] == 7
    assert review_evidence["focused_green"]["failed_count"] == 0
    assert review_evidence["chrome_smoke_green"]["passed_count"] == 28
    assert review_evidence["chrome_smoke_green"]["failed_count"] == 0
    assert review_evidence["visual_acceptance"]["decision"] == "accepted"
    assert set(review_p2_acceptance["visual_readbacks"]) == {"review_p2"}
    review_meta = review_p2_acceptance["visual_readbacks"]["review_p2"]
    review_raw = (ROOT / review_meta["path"]).read_bytes()
    assert hashlib.sha256(review_raw).hexdigest() == review_meta["sha256"]
    review_readback = json.loads(review_raw)
    assert review_readback["schema_version"] == review_meta["schema_version"]
    assert review_readback["functional_head"] == review_p2_acceptance["functional_head"]
    assert review_readback["source_bindings"] == review_p2_acceptance["source_bindings"]
    assert len(review_readback["cases"]) == review_meta["case_count"] == 4
    seen_review_cases = set()
    for case in review_readback["cases"]:
        area = case["safe_area"]
        width, height = case["viewport"]
        stage = case["stage"]
        key = (stage, width, height, area["left"], area["right"])
        assert key in {
            ("native", 390, 844, 44, 0), ("native", 390, 844, 0, 44),
            ("tools", 390, 844, 44, 0), ("tools", 390, 844, 0, 44),
        }
        assert key not in seen_review_cases
        seen_review_cases.add(key)
        bound = review_meta["screenshots"][case["screenshot_file"]]
        assert bound["stage"] == stage
        assert bound["safe_area"] == area
        assert bound["viewport"] == [width, height]
        png = (SCHAUBILD_SINGLE_WORKSPACE_REVIEW_P2_EVIDENCE
               / case["screenshot_file"]).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == case["screenshot_bytes"] == bound["bytes"]
        assert (hashlib.sha256(png).hexdigest()
                == case["screenshot_sha256"] == bound["sha256"])
        geo = (SCHAUBILD_SINGLE_WORKSPACE_REVIEW_P2_EVIDENCE
               / case["geometry_file"]).read_bytes()
        assert hashlib.sha256(geo).hexdigest() == case["geometry_sha256"]
        assert json.loads(geo)["geometry"] == case["geometry"]
        geometry = case["geometry"]
        host = geometry["host"]
        assert host["actionBar"]["left"] >= area["left"] - 0.5
        assert host["actionBar"]["right"] <= width - area["right"] + 0.5
        assert host["stage"]["width"] == width
        assert host["stage"]["height"] == height
        back = next(item for item in host["actions"]
                    if item["selector"] == "#workspaceCloseButton")
        assert back["text"] == "Zurück" and back["accessible"].startswith("Zurück")
        if stage == "tools":
            assert geometry["native"]["active"] is False
            tools = next(item for item in host["actions"]
                         if item["selector"] == ".workspace-tools-menu > summary")
            assert tools["text"] == "Tools" and tools["accessible"].startswith("Tools")
            assert tools["fontPx"] >= 12
            assert tools["textWidth"] <= tools["availableWidth"]
            for item in host["actions"]:
                if item["hidden"]:
                    continue
                rect = item["box"]
                assert rect["left"] >= area["left"] - 0.5
                assert rect["right"] <= width - area["right"] + 0.5
        else:
            native = geometry["native"]
            assert native["active"] is True
            assert len(native["controls"]) == 5
            footer = native["footer"]
            assert footer["left"] >= area["left"] - 0.5
            assert footer["right"] <= width - area["right"] + 0.5
            for item in native["controls"]:
                rect = item["box"]
                assert rect["left"] >= area["left"] - 0.5
                assert rect["right"] <= width - area["right"] + 0.5
            bar = host["actionBar"]
            overlap_width = max(0, min(footer["right"], bar["right"])
                                - max(footer["left"], bar["left"]))
            overlap_height = max(0, min(footer["bottom"], bar["bottom"])
                                 - max(footer["top"], bar["top"]))
            assert overlap_width * overlap_height <= 0.5
    assert len(seen_review_cases) == 4

    # New visually inspected source revision for pinch-jitter and save labeling.
    # Previous PNGs and their original revision bindings remain immutable.
    pinch_save_path = (
        SCHAUBILD_SINGLE_WORKSPACE_PINCH_SAVE_EVIDENCE / "acceptance-receipt.json"
    )
    pinch_save_acceptance = json.loads(
        pinch_save_path.read_text(encoding="utf-8")
    )
    assert pinch_save_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-pinch-save.v1"
    )
    assert pinch_save_acceptance["functional_head"] == (
        "7d906571d24cd73d788251ff529b140fa238604f"
    )
    assert pinch_save_acceptance["parent_evidence"] == {
        "path": str(review_p2_path.relative_to(ROOT)),
        "schema_version": review_p2_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(review_p2_path.read_bytes()).hexdigest(),
        "evidence_digest": review_p2_acceptance["evidence_digest"],
    }
    assert pinch_save_acceptance["evidence_digest"] == digest_mapping(
        pinch_save_acceptance, "evidence_digest"
    )
    assert set(pinch_save_acceptance["source_bindings"]) == (
        single_workspace_pinch_save_superseded_files
    )
    for path, expected in pinch_save_acceptance["source_bindings"].items():
        if path in (single_workspace_host_retry_superseded_files
                    | single_workspace_ci_save_font_superseded_files):
            continue
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert all(pinch_save_acceptance["checks"].values())
    p2_checks = pinch_save_acceptance["check_evidence"]
    assert p2_checks["independent_prior_p2"]["finding_count"] == 3
    assert p2_checks["focused_green"]["passed_count"] == 5
    assert p2_checks["focused_green"]["failed_count"] == 0
    assert p2_checks["full_chromium_green"]["passed_count"] == 28
    assert p2_checks["full_chromium_green"]["failed_count"] == 0
    assert p2_checks["visual_capture_green"]["passed_count"] == 4
    assert p2_checks["visual_acceptance"]["decision"] == "accepted"
    assert set(pinch_save_acceptance["visual_readbacks"]) == {"pinch_save"}
    pinch_meta = pinch_save_acceptance["visual_readbacks"]["pinch_save"]
    pinch_raw = (ROOT / pinch_meta["path"]).read_bytes()
    assert hashlib.sha256(pinch_raw).hexdigest() == pinch_meta["sha256"]
    pinch_readback = json.loads(pinch_raw)
    assert pinch_readback["schema_version"] == pinch_meta["schema_version"]
    assert pinch_readback["functional_head"] == pinch_save_acceptance["functional_head"]
    assert pinch_readback["source_bindings"] == pinch_save_acceptance["source_bindings"]
    assert len(pinch_readback["cases"]) == pinch_meta["case_count"] == 8
    seen_pinch_cases = set()
    for case in pinch_readback["cases"]:
        stage = case["stage"]
        width, height = case["viewport"]
        safe = case["safe_area"]
        key = (stage, width, height, safe["left"], safe["right"])
        assert key in {
            (kind, w, h, inset_left, inset_right)
            for kind in ("tools", "native")
            for w, h in ((320, 700), (390, 844))
            for inset_left, inset_right in ((44, 0), (0, 44))
        }
        assert key not in seen_pinch_cases
        seen_pinch_cases.add(key)
        binding = pinch_meta["screenshots"][case["screenshot_file"]]
        assert binding["stage"] == stage
        assert binding["viewport"] == [width, height]
        assert binding["safe_area"] == safe
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_PINCH_SAVE_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == case["screenshot_bytes"] == binding["bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == case["screenshot_sha256"] == binding["sha256"]
        )
        sidecar = (
            SCHAUBILD_SINGLE_WORKSPACE_PINCH_SAVE_EVIDENCE
            / case["geometry_file"]
        ).read_bytes()
        assert hashlib.sha256(sidecar).hexdigest() == case["geometry_sha256"]
        assert json.loads(sidecar)["geometry"] == case["geometry"]
        geom = case["geometry"]
        host = geom["host"]
        assert geom["window"] == {"width": width, "height": height}
        assert host["actionBar"]["left"] >= safe["left"] - 0.5
        assert host["actionBar"]["right"] <= width - safe["right"] + 0.5
        assert abs(host["stage"]["width"] - width) <= 1
        assert abs(host["stage"]["height"] - height) <= 1
        back = next(
            item for item in host["actions"]
            if item["selector"] == "#workspaceCloseButton"
        )
        assert back["text"] == "Zurück" and back["accessible"].startswith("Zurück")
        if stage == "tools":
            assert geom["native"]["active"] is False
            tools = next(
                item for item in host["actions"]
                if item["selector"] == ".workspace-tools-menu > summary"
            )
            save = next(
                item for item in host["actions"]
                if item["selector"] == "#downloadLink"
            )
            assert tools["text"] == "Tools"
            assert tools["accessible"].startswith("Tools")
            assert tools["spanWidth"] + 1 >= tools["textScrollWidth"]
            assert tools["fontPx"] >= 12
            assert save["text"] == "Speichern"
            assert save["accessible"].startswith("Speichern")
            assert save["spanWidth"] + 1 >= save["textScrollWidth"]
            assert not save["hidden"]
            for item in host["actions"]:
                if item["hidden"]:
                    continue
                bounds = item["box"]
                assert bounds["width"] >= 38 and bounds["height"] >= 40
                assert bounds["left"] >= safe["left"] - 0.5
                assert bounds["right"] <= width - safe["right"] + 0.5
        else:
            native = geom["native"]
            assert native["active"] is True
            assert len(native["controls"]) == 5
            footer = native["footer"]
            assert footer["left"] >= safe["left"] - 0.5
            assert footer["right"] <= width - safe["right"] + 0.5
            for item in native["controls"]:
                bounds = item["box"]
                assert bounds["left"] >= safe["left"] - 0.5
                assert bounds["right"] <= width - safe["right"] + 0.5
            bar = host["actionBar"]
            overlap_x = max(
                0, min(footer["right"], bar["right"])
                - max(footer["left"], bar["left"])
            )
            overlap_y = max(
                0, min(footer["bottom"], bar["bottom"])
                - max(footer["top"], bar["top"])
            )
            assert overlap_x * overlap_y <= 0.5
    assert len(seen_pinch_cases) == 8

    # Exact successor for 621px host-safe Native menu and 320/390px host retry.
    # Parent bytes remain immutable; the latest receipt binds three changed files.
    host_retry_path = (
        SCHAUBILD_SINGLE_WORKSPACE_HOST_RETRY_EVIDENCE / "acceptance-receipt.json"
    )
    host_retry_acceptance = json.loads(
        host_retry_path.read_text(encoding="utf-8")
    )
    assert host_retry_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-host-retry.v1"
    )
    assert host_retry_acceptance["functional_head"] == (
        "6fa626d6fc073d622131339fa97f2e7d65d390dd"
    )
    assert host_retry_acceptance["parent_evidence"] == {
        "path": str(pinch_save_path.relative_to(ROOT)),
        "schema_version": pinch_save_acceptance["schema_version"],
        "file_sha256": hashlib.sha256(pinch_save_path.read_bytes()).hexdigest(),
        "evidence_digest": pinch_save_acceptance["evidence_digest"],
    }
    assert host_retry_acceptance["evidence_digest"] == digest_mapping(
        host_retry_acceptance, "evidence_digest"
    )
    assert set(host_retry_acceptance["source_bindings"]) == (
        single_workspace_host_retry_superseded_files
    )
    for path, sha in host_retry_acceptance["source_bindings"].items():
        if path in single_workspace_ci_save_font_superseded_files:
            continue
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
    assert all(host_retry_acceptance["checks"].values())
    assert host_retry_acceptance["check_evidence"]["visual_acceptance"]["decision"] == "accepted"
    assert host_retry_acceptance["check_evidence"]["full_chromium_green"]["passed_count"] == 29
    assert host_retry_acceptance["check_evidence"]["visual_capture_green"]["case_count"] == 3
    assert set(host_retry_acceptance["visual_readbacks"]) == {"host_retry"}
    host_retry_meta = host_retry_acceptance["visual_readbacks"]["host_retry"]
    assert host_retry_meta["case_count"] == 3
    host_retry_raw = (ROOT / host_retry_meta["path"]).read_bytes()
    assert hashlib.sha256(host_retry_raw).hexdigest() == host_retry_meta["sha256"]
    host_retry_readback = json.loads(host_retry_raw)
    assert host_retry_readback["schema_version"] == host_retry_meta["schema_version"]
    assert host_retry_readback["functional_head"] == host_retry_acceptance["functional_head"]
    assert host_retry_readback["source_bindings"] == host_retry_acceptance["source_bindings"]
    assert len(host_retry_readback["cases"]) == 3
    seen_host_retry = set()
    for case in host_retry_readback["cases"]:
        width, height = case["viewport"]
        safe = case["simulated_safe_area"]
        kind = case["kind"]
        key = (kind, width, height, safe["left"], safe["right"])
        assert key in {
            ("desktop-menu", 621, 720, 80, 80),
            ("embedded-retry", 390, 844, 44, 0),
            ("embedded-retry", 320, 700, 0, 44),
        }
        assert key not in seen_host_retry
        seen_host_retry.add(key)
        shot = host_retry_meta["screenshots"][case["screenshot_file"]]
        assert shot["kind"] == kind and shot["viewport"] == [width, height]
        assert shot["safe_area"] == safe
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_HOST_RETRY_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == shot["bytes"] == case["screenshot_bytes"]
        assert hashlib.sha256(png).hexdigest() == shot["sha256"] == case["screenshot_sha256"]
        sidecar = (
            SCHAUBILD_SINGLE_WORKSPACE_HOST_RETRY_EVIDENCE
            / case["geometry_file"]
        ).read_bytes()
        assert hashlib.sha256(sidecar).hexdigest() == case["geometry_sha256"]
        assert shot["geometry_sha256"] == case["geometry_sha256"]
        assert json.loads(sidecar) == case["geometry"]
        geom = case["geometry"]
        assert geom["pass"] is True
        if kind == "desktop-menu":
            assert geom["childEnvironment"] == {"left": 0, "right": 0}
            assert geom["hostSafe"] == {"left": 80, "right": 80}
            assert geom["menu"]["left"] >= 80
            assert geom["menu"]["right"] <= width - 80
        else:
            assert geom["retry"]["width"] > 0
            assert geom["retryClearance"] >= 8
            assert geom["retry"]["top"] - geom["fittedContentBottom"] == geom["retryClearance"]
    assert len(seen_host_retry) == 3

    # The new mobile visible Save caption revision supersedes exactly two files.
    # Do not mutate the parent or the historical image acceptance.
    ci_save_path = (
        SCHAUBILD_SINGLE_WORKSPACE_CI_SAVE_FONT_EVIDENCE / "acceptance-receipt.json"
    )
    ci_save_acceptance = json.loads(ci_save_path.read_text(encoding="utf-8"))
    assert ci_save_acceptance["schema_version"] == (
        "schauwerk-schaubild-single-workspace-ci-save-font.v1"
    )
    assert ci_save_acceptance["functional_head"] == (
        "25c1b8cbdf9879f68593fbcf808579a5f34bd6f5"
    )
    assert ci_save_acceptance["parent_evidence"] == {
        "path": str(host_retry_path.relative_to(ROOT)),
        "file_sha256": hashlib.sha256(host_retry_path.read_bytes()).hexdigest(),
        "evidence_digest": host_retry_acceptance["evidence_digest"],
        "schema_version": host_retry_acceptance["schema_version"],
    }
    assert ci_save_acceptance["evidence_digest"] == digest_mapping(
        ci_save_acceptance, "evidence_digest"
    )
    assert set(ci_save_acceptance["source_bindings"]) == (
        single_workspace_ci_save_font_superseded_files
    )
    for name, expected in ci_save_acceptance["source_bindings"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert all(ci_save_acceptance["checks"].values())
    accept_evidence = ci_save_acceptance["check_evidence"]
    assert accept_evidence["prior_ci_fail"]["failed_cases"] == 5
    assert accept_evidence["focused_browser_green"]["passed_count"] == 5
    assert accept_evidence["full_chromium_green"]["passed_count"] == 29
    assert accept_evidence["visual_acceptance"]["decision"] == "accepted"
    assert set(ci_save_acceptance["visual_readbacks"]) == {"ci_save_font"}
    ci_save_meta = ci_save_acceptance["visual_readbacks"]["ci_save_font"]
    assert ci_save_meta["case_count"] == 4
    raw_ci_save = (ROOT / ci_save_meta["path"]).read_bytes()
    assert hashlib.sha256(raw_ci_save).hexdigest() == ci_save_meta["sha256"]
    ci_save_readback = json.loads(raw_ci_save)
    assert ci_save_readback["schema_version"] == ci_save_meta["schema_version"]
    assert ci_save_readback["functional_head"] == ci_save_acceptance["functional_head"]
    assert ci_save_readback["source_bindings"] == ci_save_acceptance["source_bindings"]
    assert len(ci_save_readback["cases"]) == 4
    seen_ci_save = set()
    for case in ci_save_readback["cases"]:
        width, height = case["viewport"]
        safe = case["safe_area"]
        key = (width, height, safe["left"], safe["right"])
        assert key in {
            (320, 700, 44, 0), (320, 700, 0, 44),
            (390, 844, 44, 0), (390, 844, 0, 44),
        }
        assert key not in seen_ci_save
        seen_ci_save.add(key)
        bound = ci_save_meta["screenshots"][case["screenshot_file"]]
        assert bound["viewport"] == [width, height] and bound["safe_area"] == safe
        png = (
            SCHAUBILD_SINGLE_WORKSPACE_CI_SAVE_FONT_EVIDENCE
            / case["screenshot_file"]
        ).read_bytes()
        assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
        assert int.from_bytes(png[16:20], "big") == width
        assert int.from_bytes(png[20:24], "big") == height
        assert len(png) == bound["bytes"] == case["screenshot_bytes"]
        assert (
            hashlib.sha256(png).hexdigest()
            == bound["sha256"] == case["screenshot_sha256"]
        )
        raw_geo = (
            SCHAUBILD_SINGLE_WORKSPACE_CI_SAVE_FONT_EVIDENCE
            / case["geometry_file"]
        ).read_bytes()
        assert hashlib.sha256(raw_geo).hexdigest() == case["geometry_sha256"]
        assert bound["geometry_sha256"] == case["geometry_sha256"]
        assert json.loads(raw_geo) == {"geometry": case["geometry"]}
        geo = case["geometry"]
        assert geo["pass"] and geo["shortText"] == "Speichern"
        assert geo["accessible"] == "Speichern: Originalprojekt"
        assert geo["textRoom"] >= 66 and geo["stressWidth"] >= 64
        assert geo["stressPass"] and geo["noTruncation"]
        assert geo["toolbarSafe"] and geo["controlValid"]
        assert geo["hasCanvasFullWidth"]
    assert len(seen_ci_save) == 4

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
        if name in single_workspace_ci_save_font_superseded_files:
            assert ci_save_acceptance["source_bindings"][name] == current
        elif name in single_workspace_host_retry_superseded_files:
            assert host_retry_acceptance["source_bindings"][name] == current
        elif name in single_workspace_pinch_save_superseded_files:
            assert pinch_save_acceptance["source_bindings"][name] == current
        elif name in single_workspace_review_p2_superseded_files:
            assert review_p2_acceptance["source_bindings"][name] == current
        elif name in single_workspace_embedded_host_superseded_files:
            assert host_acceptance["source_bindings"][name] == current
        elif name in single_workspace_tap_autofit_superseded_files:
            assert tap_acceptance["source_bindings"][name] == current
        elif name in single_workspace_pointer_owner_superseded_files:
            assert owner_acceptance["source_bindings"][name] == current
        elif name in single_workspace_gesture_cancel_superseded_files:
            assert gesture_acceptance["source_bindings"][name] == current
        elif name in single_workspace_status_drag_superseded_files:
            assert drag_acceptance["source_bindings"][name] == current
        elif name in single_workspace_status_autofit_superseded_files:
            assert status_acceptance["source_bindings"][name] == current
        elif name in single_workspace_mobile_prompt_width_superseded_files:
            assert prompt_acceptance["source_bindings"][name] == current
        elif name in single_workspace_ci_caption_safearea_superseded_files:
            assert final["source_bindings"][name] == current
        elif name in single_workspace_ci_download_superseded_files:
            assert ci_download["source_bindings"][name] == current
        elif name in single_workspace_late_review_menus_superseded_files:
            assert late_menus["source_bindings"][name] == current
        elif name in single_workspace_independent_remediation_superseded_files:
            assert independent_remediation["source_bindings"][name] == current
        elif name in single_workspace_ci_font_legacy_superseded_files:
            assert ci_font_legacy["source_bindings"][name] == current
        elif name in single_workspace_side_safearea_superseded_files:
            assert side_safearea["source_bindings"][name] == current
        elif name in single_workspace_mobile_320_superseded_files:
            assert mobile["source_bindings"][name] == current
        elif name in single_workspace_safe_area_test_contract_superseded_files:
            assert test_contract["source_bindings"][name] == current
        elif name in single_workspace_safe_area_fit_superseded_files:
            assert safe_area_receipt["source_bindings"][name] == current
        elif name in single_workspace_final_review_superseded_files:
            assert final_review["source_bindings"][name] == current
        elif name in single_workspace_popover_anchoring_superseded_files:
            assert popover_anchor["source_bindings"][name] == current
        elif name in single_workspace_fit_retry_superseded_files:
            assert fit_retry["source_bindings"][name] == current
        elif name in single_workspace_zoom_continuity_superseded_files:
            assert zoom_continuity["source_bindings"][name] == current
        elif name in single_workspace_review_hardening_superseded_files:
            assert review_hardening["source_bindings"][name] == current
        elif name in single_workspace_review_closure_superseded_files:
            assert review_closure["source_bindings"][name] == current
        elif name in single_workspace_fit_clearance_superseded_files:
            assert single_workspace_fit_clearance["source_bindings"][name] == current
        elif name in single_workspace_max_canvas_superseded_files:
            assert single_workspace_max_canvas["source_bindings"][name] == current
        elif name in single_workspace_dark_status_superseded_files:
            assert single_workspace_dark_status["source_bindings"][name] == current
        elif name in single_workspace_wrapped_dock_superseded_files:
            assert single_workspace_wrapped_dock["source_bindings"][name] == current
        elif name in single_workspace_mobile_status_superseded_files:
            assert single_workspace_mobile_status["source_bindings"][name] == current
        elif name in single_workspace_review_fix_superseded_files:
            assert single_workspace_review_fix["source_bindings"][name] == current
        elif name in single_workspace_exports_superseded_files:
            assert single_workspace_exports["source_bindings"][name] == current
        elif name in focus_default_review_fix_superseded_files:
            assert focus_default_review_fix["source_bindings"][name] == current
        elif name in focus_default_superseded_files:
            assert focus_default["source_bindings"][name] == current
        elif name in codeql_superseded_files:
            assert successor["source_bindings"][name] == current
        elif name in oauth_superseded_files:
            assert oauth_successor["source_bindings"][name] == current
        elif name in content_editing_recovery_save_hardening_superseded_files:
            assert content_editing_recovery_save_hardening["source_bindings"][name] == current
        elif name in content_editing_save_feedback_superseded_files:
            assert content_editing_save_feedback["source_bindings"][name] == current
        elif name in content_editing_recovery_layout_reload_superseded_files:
            assert content_editing_recovery_layout_reload["source_bindings"][name] == current
        elif name in content_editing_valid_draft_recovery_superseded_files:
            assert content_editing_valid_draft_recovery["source_bindings"][name] == current
        elif name in content_editing_form_submit_superseded_files:
            assert content_editing_form_submit["source_bindings"][name] == current
        elif name in content_editing_recovery_superseded_files:
            assert content_editing_recovery["source_bindings"][name] == current
        elif name in content_editing_superseded_files:
            assert content_editing["source_bindings"][name] == current
        elif name in smoke_pipefail_superseded_files:
            assert smoke_pipefail["source_bindings"][name] == current
        elif name in ui_controls_resize_superseded_files:
            assert ui_controls_resize["source_bindings"][name] == current
        elif name in ui_controls_superseded_files:
            assert ui_controls["source_bindings"][name] == current
        elif name in edge_label_width_superseded_files:
            assert edge_label_width["source_bindings"][name] == current
        elif name in json_canvas_text_fit_private_use_superseded_files:
            assert json_canvas_text_fit_private_use["source_bindings"][name] == current
        elif name in json_canvas_text_fit_supplementary_symbols_superseded_files:
            assert (
                json_canvas_text_fit_supplementary_symbols["source_bindings"][name]
                == current
            )
        elif name in json_canvas_text_fit_vertical_marker_superseded_files:
            assert json_canvas_text_fit_vertical_marker["source_bindings"][name] == current
        elif name in json_canvas_text_fit_markdown_linear_superseded_files:
            assert json_canvas_text_fit_markdown_linear["source_bindings"][name] == current
        elif name in json_canvas_text_fit_emoji_presentation_superseded_files:
            assert json_canvas_text_fit_emoji_presentation["source_bindings"][name] == current
        elif name in json_canvas_text_fit_final_invariants_superseded_files:
            assert json_canvas_text_fit_final_invariants["source_bindings"][name] == current
        elif name in json_canvas_text_fit_indic_zwj_floor_superseded_files:
            assert json_canvas_text_fit_indic_zwj_floor["source_bindings"][name] == current
        elif name in json_canvas_text_fit_ellipsis_width_superseded_files:
            assert json_canvas_text_fit_ellipsis_width["source_bindings"][name] == current
        elif name in json_canvas_text_fit_geometry_cap_superseded_files:
            assert json_canvas_text_fit_geometry_cap["source_bindings"][name] == current
        elif name in json_canvas_text_fit_svg_whitespace_superseded_files:
            assert json_canvas_text_fit_svg_whitespace["source_bindings"][name] == current
        elif name in json_canvas_text_fit_numeric_fallback_superseded_files:
            assert json_canvas_text_fit_numeric_fallback["source_bindings"][name] == current
        elif name in json_canvas_text_fit_ascii_fallback_superseded_files:
            assert json_canvas_text_fit_ascii_fallback["source_bindings"][name] == current
        elif name in json_canvas_text_fit_review_hardening_superseded_files:
            assert json_canvas_text_fit_review_hardening["source_bindings"][name] == current
        elif name in json_canvas_text_fit_unicode_remediation_superseded_files:
            assert json_canvas_text_fit_unicode_remediation["source_bindings"][name] == current
        elif name in json_canvas_text_fit_review_remediation_superseded_files:
            assert json_canvas_text_fit_review_remediation["source_bindings"][name] == current
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
        elif name in json_canvas_text_fit_viewer_startup_status_superseded_files:
            assert (
                json_canvas_text_fit_viewer_startup_status["source_bindings"][name]
                == current
            )
        elif name in json_canvas_text_fit_viewer_startup_superseded_files:
            assert json_canvas_text_fit_viewer_startup["source_bindings"][name] == current
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
