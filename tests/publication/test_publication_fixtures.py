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

    editor_successor = json.loads(
        (SCHAUBILD_NATIVE_EDITOR_EVIDENCE / "acceptance-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert editor_successor["schema_version"] == "schauwerk-schaubild-native-editor.v1"
    assert editor_successor["functional_head"] == "8a286a257f3231e28ccca1f50ac070950d8f7ce9"
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
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert editor_successor["checks"]["browser_smoke_passed_count"] == 6
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
    schaubild_superseded_files = {
        "tests/visual/test_standalone_editor.py",
    }
    for name, expected in receipt["implementation_file_sha256"].items():
        current = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if name in codeql_superseded_files:
            assert successor["source_bindings"][name] == current
        elif name in oauth_superseded_files:
            assert oauth_successor["source_bindings"][name] == current
        elif name in schaubild_superseded_files:
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
