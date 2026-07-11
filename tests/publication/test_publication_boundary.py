from __future__ import annotations

import copy
import hashlib
import http.client
import json
import os
import stat
from pathlib import Path

import pytest

from schauwerk.publication.model import (
    PublicationError,
    compile_declaration,
    compile_preview,
)
from schauwerk.publication.server import create_publication_server
from schauwerk.publication.store import (
    publication_status,
    release_publication,
    verify_object,
    withdraw_publication,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/operators/evidence/sw012-buehne-20260711/technical/public"


def _source_snapshot() -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(SOURCE.iterdir())
        if item.is_file()
    }


def _make_store_removable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            continue
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def declaration_draft(
    *,
    version: str = "1.0.0",
    replaces_version: str | None = None,
    expected_link_digest: str | None = None,
    expires_at: str | None = "2026-08-01T00:00:00Z",
    published_at: str = "2026-01-01T00:00:00Z",
) -> dict:
    manifest_path = SOURCE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "publication_id": "grabowski-operational-brief",
        "stable_slug": "grabowski-brief",
        "version": version,
        "view_id": "grabowski.operator-overview",
        "audience": "Technische Betreiber",
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_manifest_digest": manifest["manifest_digest"],
        "source_revision": manifest["source_revision"],
        "entrypoint": manifest["entrypoint"],
        "files": sorted(manifest["files"]),
        "metadata_fields": [
            "audience",
            "presentation_id",
            "presentation_version",
            "public_projection_sha256",
            "scene_order",
            "scene_order_sha256",
            "source_revision",
            "variant_id",
            "variant_title",
            "visible_content_sha256",
        ],
        "sources": [
            {
                "id": "primary",
                "visibility": "public",
                "fields": ["id", "label", "revision", "sha256"],
            }
        ],
        "lifecycle": {
            "published_at": published_at,
            "expires_at": expires_at,
            "replaces_version": replaces_version,
            "expected_link_digest": expected_link_digest,
        },
    }


def compiled_pair(**kwargs) -> tuple[dict, dict]:
    declaration = compile_declaration(declaration_draft(**kwargs))
    preview, _ = compile_preview(declaration, SOURCE)
    return declaration, preview


def test_preview_is_deterministic_and_only_contains_declared_public_fields() -> None:
    declaration, preview = compiled_pair()
    repeated, _ = compile_preview(declaration, SOURCE)
    assert repeated == preview
    assert preview["source_package"]["selected_public_sources"] == [
        {
            "id": "primary",
            "label": "Sanitisierter Grabowski-Betriebssnapshot",
            "revision": "2026-07-10-fixture",
            "sha256": "64e12f5cd3a85e44dcb27087e83b4de9fae1e94cd98adf4a044460ecd58145b9",
        }
    ]
    assert set(preview["source_package"]["selected_metadata"]) == set(
        declaration["metadata_fields"]
    )
    assert all(preview["privacy_checks"].values())
    encoded = json.dumps(preview, ensure_ascii=False)
    assert "guidance" not in encoded
    assert "speaker_notes" not in encoded


@pytest.mark.parametrize("visibility", ["private", "internal", "unknown", "PUBLIC"])
def test_declaration_rejects_every_visibility_except_explicit_public(visibility: str) -> None:
    draft = declaration_draft()
    draft["sources"][0]["visibility"] = visibility
    with pytest.raises(PublicationError, match="explicitly public"):
        compile_declaration(draft)


def test_preview_rejects_undeclared_file_source_and_changed_manifest(tmp_path: Path) -> None:
    declaration, _ = compiled_pair()
    missing_file = copy.deepcopy(declaration_draft())
    missing_file["files"].remove("presentation.pdf")
    with pytest.raises(PublicationError, match="exact source package file set"):
        compile_preview(compile_declaration(missing_file), SOURCE)

    copied = tmp_path / "source"
    copied.mkdir()
    for item in SOURCE.iterdir():
        (copied / item.name).write_bytes(item.read_bytes())
    (copied / "surprise.txt").write_text("undeclared", encoding="utf-8")
    with pytest.raises(PublicationError, match="undeclared files"):
        compile_preview(declaration, copied)

    manifest = json.loads((copied / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_metadata"]["public_sources"].append(
        {
            "id": "unexpected",
            "label": "Unexpected source",
            "revision": "1",
            "sha256": "0" * 64,
        }
    )
    manifest["manifest_digest"] = "0" * 64
    (copied / "surprise.txt").unlink()
    (copied / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PublicationError, match="digest mismatch"):
        compile_preview(declaration, copied)


def test_release_expiry_withdrawal_and_immutability_preserve_source_truth(tmp_path: Path) -> None:
    declaration, preview = compiled_pair()
    before = _source_snapshot()
    store = tmp_path / "store"
    receipt = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    assert receipt["source_truth_mutated"] is False
    assert receipt["provider_mutation_attempted"] is False
    assert receipt["immutable_object_created"] is True
    assert _source_snapshot() == before

    active = publication_status(store, "grabowski-brief", now="2026-07-12T00:00:00Z")
    assert active["state"] == "active"
    assert active["integrity"] == "verified"
    expired = publication_status(store, "grabowski-brief", now="2026-08-01T00:00:00Z")
    assert expired["state"] == "expired"

    object_root = store / "objects/grabowski-operational-brief/1.0.0"
    assert not stat.S_IMODE(object_root.stat().st_mode) & 0o222
    assert not stat.S_IMODE((object_root / "bundle").stat().st_mode) & 0o222
    for item in object_root.rglob("*"):
        if item.is_file():
            assert not stat.S_IMODE(item.stat().st_mode) & 0o222

    with pytest.raises(PublicationError, match="changed after withdrawal review"):
        withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest="0" * 64,
            reason="test",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
    withdrawal = withdraw_publication(
        store,
        "grabowski-brief",
        expected_link_digest=receipt["link_digest"],
        reason="controlled test withdrawal",
        withdrawn_at="2026-07-13T00:00:00Z",
    )
    assert withdrawal["immutable_object_preserved"] is True
    assert (
        publication_status(store, "grabowski-brief", now="2026-07-14T00:00:00Z")["state"]
        == "withdrawn"
    )
    assert (
        verify_object(store, "grabowski-operational-brief", "1.0.0")["object_digest"]
        == receipt["object_digest"]
    )
    assert _source_snapshot() == before


def test_stable_link_moves_to_review_bound_new_version_without_deleting_old_object(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    declaration_v1, preview_v1 = compiled_pair(expires_at=None)
    first = release_publication(
        declaration=declaration_v1,
        preview=preview_v1,
        source_dir=SOURCE,
        store_root=store,
    )
    declaration_v2, preview_v2 = compiled_pair(
        version="2.0.0",
        replaces_version="1.0.0",
        expected_link_digest=first["link_digest"],
        expires_at=None,
        published_at="2026-01-02T00:00:00Z",
    )
    second = release_publication(
        declaration=declaration_v2,
        preview=preview_v2,
        source_dir=SOURCE,
        store_root=store,
    )
    assert publication_status(store, "grabowski-brief")["version"] == "2.0.0"
    assert verify_object(store, "grabowski-operational-brief", "1.0.0")
    assert verify_object(store, "grabowski-operational-brief", "2.0.0")
    assert first["object_digest"] != second["object_digest"]


def test_object_tampering_is_detected(tmp_path: Path) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    target = store / "objects/grabowski-operational-brief/1.0.0/bundle/index.html"
    target.chmod(0o644)
    with pytest.raises(PublicationError, match="is writable"):
        publication_status(store, "grabowski-brief")
    target.write_text("tampered", encoding="utf-8")
    target.chmod(0o444)
    with pytest.raises(PublicationError, match="size mismatch|digest mismatch"):
        publication_status(store, "grabowski-brief")


def test_http_delivery_is_loopback_read_only_and_honours_withdrawal(tmp_path: Path) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    server = create_publication_server(store)
    child = os.fork()
    if child == 0:
        try:
            server.serve_forever()
        finally:
            os._exit(0)
    try:
        host, port = server.server_address
        assert host == "127.0.0.1"
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/p/grabowski-brief/")
        response = connection.getresponse()
        payload = response.read()
        assert response.status == 200
        assert payload == (SOURCE / "index.html").read_bytes()
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert response.getheader("X-Schauwerk-Publication-Version") == "1.0.0"

        connection.request("POST", "/p/grabowski-brief/", body=b"{}")
        response = connection.getresponse()
        response.read()
        assert response.status == 405
        assert response.getheader("Allow") == "GET, HEAD"
        assert response.getheader("Connection") == "close"

        connection.request("GET", "/p/grabowski-brief/../publication.json")
        response = connection.getresponse()
        response.read()
        assert response.status == 404

        withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest=release["link_digest"],
            reason="HTTP withdrawal test",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
        connection.request("GET", "/p/grabowski-brief/")
        response = connection.getresponse()
        response.read()
        assert response.status == 410
        connection.close()
    finally:
        try:
            os.kill(child, 15)
        except ProcessLookupError:
            pass
        os.waitpid(child, 0)
        server.server_close()


def test_declaration_compiler_normalizes_order_and_timestamp_precision() -> None:
    draft = declaration_draft()
    draft["files"] = list(reversed(draft["files"]))
    draft["metadata_fields"] = list(reversed(draft["metadata_fields"]))
    draft["sources"][0]["fields"] = list(reversed(draft["sources"][0]["fields"]))
    draft["lifecycle"]["published_at"] = "2026-07-11T12:00:00.987654Z"
    compiled = compile_declaration(draft)
    assert compiled["files"] == sorted(compiled["files"])
    assert compiled["metadata_fields"] == sorted(compiled["metadata_fields"])
    assert compiled["sources"][0]["fields"] == sorted(compiled["sources"][0]["fields"])
    assert compiled["lifecycle"]["published_at"] == "2026-07-11T12:00:00Z"


def test_preview_requires_the_exact_canonical_privacy_check_set() -> None:
    from schauwerk.publication.model import digest_mapping, validate_preview

    _, preview = compiled_pair()
    missing = copy.deepcopy(preview)
    missing["privacy_checks"].pop("provider_identifiers_absent")
    missing["preview_digest"] = digest_mapping(missing, "preview_digest")
    with pytest.raises(PublicationError, match="checks are incomplete"):
        validate_preview(missing)

    invented = copy.deepcopy(preview)
    invented["privacy_checks"]["invented_check"] = True
    invented["preview_digest"] = digest_mapping(invented, "preview_digest")
    with pytest.raises(PublicationError, match="checks are incomplete"):
        validate_preview(invented)


def test_identical_release_retry_is_idempotent(tmp_path: Path) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    first = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    second = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    assert first["immutable_object_created"] is True
    assert first["stable_link_updated"] is True
    assert second == first
    assert second["object_digest"] == first["object_digest"]
    assert second["link_digest"] == first["link_digest"]
    assert len(list((store / "receipts").glob("release-*.json"))) == 1
    versions = list((store / "objects/grabowski-operational-brief").iterdir())
    assert [item.name for item in versions] == ["1.0.0"]


def test_new_release_rolls_back_link_and_object_after_post_commit_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"

    def fail_verification(*args, **kwargs):
        raise PublicationError("simulated post-link verification failure")

    monkeypatch.setattr(store_module, "verify_object", fail_verification)
    with pytest.raises(PublicationError, match="post-link verification failure"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
    assert not (store / "links/grabowski-brief.json").exists()
    assert not (store / "objects/grabowski-operational-brief/1.0.0").exists()


def test_version_update_restores_previous_link_after_post_commit_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    store = tmp_path / "store"
    declaration_v1, preview_v1 = compiled_pair(expires_at=None)
    first = release_publication(
        declaration=declaration_v1,
        preview=preview_v1,
        source_dir=SOURCE,
        store_root=store,
    )
    declaration_v2, preview_v2 = compiled_pair(
        version="2.0.0",
        replaces_version="1.0.0",
        expected_link_digest=first["link_digest"],
        expires_at=None,
        published_at="2026-01-02T00:00:00Z",
    )
    original_verify = store_module.verify_object

    def fail_v2(root: Path, publication_id: str, version: str):
        if version == "2.0.0":
            raise PublicationError("simulated v2 verification failure")
        return original_verify(root, publication_id, version)

    monkeypatch.setattr(store_module, "verify_object", fail_v2)
    with pytest.raises(PublicationError, match="v2 verification failure"):
        release_publication(
            declaration=declaration_v2,
            preview=preview_v2,
            source_dir=SOURCE,
            store_root=store,
        )
    monkeypatch.setattr(store_module, "verify_object", original_verify)
    status = publication_status(store, "grabowski-brief")
    assert status["version"] == "1.0.0"
    assert status["link_digest"] == first["link_digest"]
    assert not (store / "objects/grabowski-operational-brief/2.0.0").exists()


def test_withdrawal_restores_active_link_when_receipt_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )

    def fail_receipt(*args, **kwargs):
        raise OSError("simulated receipt failure")

    monkeypatch.setattr(store_module, "_record_receipt", fail_receipt)
    with pytest.raises(OSError, match="receipt failure"):
        withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest=release["link_digest"],
            reason="rollback test",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
    status = publication_status(store, "grabowski-brief")
    assert status["state"] == "active"
    assert status["link_digest"] == release["link_digest"]


def test_foreign_link_appearing_during_first_release_is_preserved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    original_publish = store_module._publish_directory_noreplace

    def publish_then_create_foreign_link(source: Path, destination: Path) -> None:
        original_publish(source, destination)
        link = store / "links/grabowski-brief.json"
        link.write_text("foreign process data\n", encoding="utf-8")

    monkeypatch.setattr(
        store_module,
        "_publish_directory_noreplace",
        publish_then_create_foreign_link,
    )
    with pytest.raises(PublicationError, match="appeared after review"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
    assert (store / "links/grabowski-brief.json").read_text(encoding="utf-8") == (
        "foreign process data\n"
    )
    assert not (store / "objects/grabowski-operational-brief/1.0.0").exists()


def test_foreign_link_change_during_version_update_is_not_overwritten(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module
    from schauwerk.publication.model import digest_mapping

    store = tmp_path / "store"
    declaration_v1, preview_v1 = compiled_pair(expires_at=None)
    first = release_publication(
        declaration=declaration_v1,
        preview=preview_v1,
        source_dir=SOURCE,
        store_root=store,
    )
    declaration_v2, preview_v2 = compiled_pair(
        version="2.0.0",
        replaces_version="1.0.0",
        expected_link_digest=first["link_digest"],
        expires_at=None,
        published_at="2026-01-02T00:00:00Z",
    )
    original_publish = store_module._publish_directory_noreplace
    changed_digest: str | None = None

    def publish_then_change_link(source: Path, destination: Path) -> None:
        nonlocal changed_digest
        original_publish(source, destination)
        link_path = store / "links/grabowski-brief.json"
        link = json.loads(link_path.read_text(encoding="utf-8"))
        link["object_digest"] = "f" * 64
        link["link_digest"] = ""
        link["link_digest"] = digest_mapping(link, "link_digest")
        changed_digest = link["link_digest"]
        link_path.write_text(json.dumps(link), encoding="utf-8")

    monkeypatch.setattr(
        store_module,
        "_publish_directory_noreplace",
        publish_then_change_link,
    )
    with pytest.raises(PublicationError, match="changed after review"):
        release_publication(
            declaration=declaration_v2,
            preview=preview_v2,
            source_dir=SOURCE,
            store_root=store,
        )
    current = json.loads((store / "links/grabowski-brief.json").read_text(encoding="utf-8"))
    assert current["link_digest"] == changed_digest
    assert current["object_digest"] == "f" * 64
    assert not (store / "objects/grabowski-operational-brief/2.0.0").exists()


def test_publication_boundary_schema_validates_generated_contracts(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(
        (ROOT / "schemas/publication-boundary.v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    object_manifest = json.loads(
        (store / "objects/grabowski-operational-brief/1.0.0/publication.json").read_text(
            encoding="utf-8"
        )
    )
    stable_link = json.loads((store / "links/grabowski-brief.json").read_text(encoding="utf-8"))
    for value in (declaration, preview, object_manifest, stable_link):
        validator.validate(value)

    private_declaration = copy.deepcopy(declaration)
    private_declaration["sources"][0]["visibility"] = "private"
    assert list(validator.iter_errors(private_declaration))


def test_selected_metadata_and_compressed_pptx_content_are_privacy_scanned() -> None:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    from schauwerk.publication.model import (
        _validate_file_privacy,
        compile_preview_from_loaded,
        load_source_package,
    )

    manifest, payloads = load_source_package(SOURCE)
    manifest = copy.deepcopy(manifest)
    manifest["artifact_metadata"]["template"] = "client_" + "secret=must-not-enter-publication"
    draft = declaration_draft()
    draft["metadata_fields"].append("template")
    declaration = compile_declaration(draft)
    with pytest.raises(PublicationError, match="secret-like assignment"):
        compile_preview_from_loaded(declaration, manifest, payloads)

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "ppt/slides/slide1.xml",
            "<slide>" + "client_" + "secret=compressed-value</slide>",
        )
    with pytest.raises(PublicationError, match="secret-like assignment"):
        _validate_file_privacy("presentation.pptx", archive_buffer.getvalue())


def test_store_lock_symlink_is_rejected_without_touching_foreign_file(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    store.mkdir()
    for name in ("objects", "links", "receipts"):
        (store / name).mkdir()
    foreign = tmp_path / "foreign-lock-target"
    foreign.write_text("foreign", encoding="utf-8")
    foreign.chmod(0o644)
    (store / ".lock").symlink_to(foreign)

    with pytest.raises(PublicationError, match="lock is unsafe"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
    assert foreign.read_text(encoding="utf-8") == "foreign"
    assert stat.S_IMODE(foreign.stat().st_mode) == 0o644


def test_scheduled_publication_is_not_delivered_and_can_be_withdrawn(
    tmp_path: Path,
) -> None:
    from schauwerk.publication.store import resolve_publication_file

    declaration, preview = compiled_pair(
        published_at="2099-01-01T00:00:00Z",
        expires_at="2099-02-01T00:00:00Z",
    )
    store = tmp_path / "store"
    release = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    assert (
        publication_status(store, "grabowski-brief", now="2098-12-31T23:59:59Z")["state"]
        == "scheduled"
    )
    with pytest.raises(PublicationError, match="publication is scheduled"):
        resolve_publication_file(
            store,
            "grabowski-brief",
            None,
            now="2098-12-31T23:59:59Z",
        )
    withdrawal = withdraw_publication(
        store,
        "grabowski-brief",
        expected_link_digest=release["link_digest"],
        reason="cancel scheduled publication",
        withdrawn_at="2098-12-31T12:00:00Z",
    )
    assert withdrawal["immutable_object_preserved"] is True
    assert (
        publication_status(store, "grabowski-brief", now="2098-12-31T13:00:00Z")["state"]
        == "withdrawn"
    )


def test_http_returns_too_early_for_scheduled_publication(tmp_path: Path) -> None:
    declaration, preview = compiled_pair(
        published_at="2099-01-01T00:00:00Z",
        expires_at=None,
    )
    store = tmp_path / "store"
    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    server = create_publication_server(store)
    child = os.fork()
    if child == 0:
        try:
            server.serve_forever()
        finally:
            os._exit(0)
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/p/grabowski-brief/")
        response = connection.getresponse()
        response.read()
        assert response.status == 425
        connection.close()
    finally:
        try:
            os.kill(child, 15)
        except ProcessLookupError:
            pass
        os.waitpid(child, 0)
        server.server_close()


def test_replacement_publication_time_must_be_monotonic(tmp_path: Path) -> None:
    store = tmp_path / "store"
    declaration_v1, preview_v1 = compiled_pair(expires_at=None)
    first = release_publication(
        declaration=declaration_v1,
        preview=preview_v1,
        source_dir=SOURCE,
        store_root=store,
    )
    declaration_v2, preview_v2 = compiled_pair(
        version="2.0.0",
        replaces_version="1.0.0",
        expected_link_digest=first["link_digest"],
        expires_at=None,
        published_at="2025-12-31T23:59:59Z",
    )
    with pytest.raises(PublicationError, match="must follow the previous version"):
        release_publication(
            declaration=declaration_v2,
            preview=preview_v2,
            source_dir=SOURCE,
            store_root=store,
        )


def test_foreign_object_change_prevents_cleanup_deletion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"

    def modify_object_then_fail(*args, **kwargs):
        object_root = store / "objects/grabowski-operational-brief/1.0.0"
        object_root.chmod(0o755)
        (object_root / "foreign.txt").write_text(
            "belongs to another process",
            encoding="utf-8",
        )
        raise PublicationError("simulated link failure after foreign object change")

    monkeypatch.setattr(store_module, "_write_link_compare_and_swap", modify_object_then_fail)
    with pytest.raises(PublicationError, match="foreign object change"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
    object_root = store / "objects/grabowski-operational-brief/1.0.0"
    assert (object_root / "foreign.txt").read_text(encoding="utf-8") == (
        "belongs to another process"
    )
    _make_store_removable(store)


def test_delivery_rechecks_file_bytes_after_object_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    original_verify = store_module._verify_object_from_paths

    def verify_then_change(paths, publication_id: str, version: str):
        manifest = original_verify(paths, publication_id, version)
        target = store / "objects/grabowski-operational-brief/1.0.0/bundle/index.html"
        target.chmod(0o644)
        target.write_text("foreign replacement", encoding="utf-8")
        target.chmod(0o444)
        return manifest

    monkeypatch.setattr(store_module, "_verify_object_from_paths", verify_then_change)
    with pytest.raises(PublicationError, match="size changed during delivery"):
        store_module.resolve_publication_file(store, "grabowski-brief", None)
    _make_store_removable(store)


def test_http_root_describes_read_only_loopback_service(tmp_path: Path) -> None:
    store = tmp_path / "store"
    declaration, preview = compiled_pair(expires_at=None)
    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    server = create_publication_server(store)
    child = os.fork()
    if child == 0:
        try:
            server.serve_forever()
        finally:
            os._exit(0)
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload == {
            "schema_version": "schauwerk-publication-service.v1",
            "service": "schauwerk-publication",
            "loopback_only": True,
            "read_only": True,
            "publication_path_template": "/p/{stable_slug}/",
        }
        assert response.getheader("Cache-Control") == "no-store"
        connection.close()
    finally:
        try:
            os.kill(child, 15)
        except ProcessLookupError:
            pass
        os.waitpid(child, 0)
        server.server_close()


def test_store_root_rejects_symlinked_parent_before_any_mutation(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(foreign, target_is_directory=True)

    with pytest.raises(PublicationError, match="output parent is unsafe"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=linked_parent / "store",
        )
    assert list(foreign.iterdir()) == []


def test_existing_unrelated_directory_is_not_repurposed_as_store(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "existing"
    store.mkdir(mode=0o755)
    unrelated = store / "unrelated.txt"
    unrelated.write_text("foreign content", encoding="utf-8")
    before_mode = stat.S_IMODE(store.stat().st_mode)

    with pytest.raises(PublicationError, match="unexpected entries"):
        release_publication(
            declaration=declaration,
            preview=preview,
            source_dir=SOURCE,
            store_root=store,
        )
    assert unrelated.read_text(encoding="utf-8") == "foreign content"
    assert stat.S_IMODE(store.stat().st_mode) == before_mode
    assert {item.name for item in store.iterdir()} == {"unrelated.txt"}


def test_existing_empty_directory_can_be_initialized_as_owner_only_store(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "empty"
    store.mkdir(mode=0o755)

    release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    assert stat.S_IMODE(store.stat().st_mode) == 0o700
    assert {item.name for item in store.iterdir()} == {
        ".lock",
        "links",
        "objects",
        "receipts",
    }


def test_binary_pptx_members_and_active_pdf_objects_are_rejected() -> None:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    from schauwerk.publication.model import _validate_file_privacy

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "docProps/thumbnail.jpeg",
            b"image-prefix client_" + b"secret=hidden-thumbnail-metadata",
        )
    with pytest.raises(PublicationError, match="secret-like assignment"):
        _validate_file_privacy("presentation.pptx", archive_buffer.getvalue())

    for marker in (
        b"/JavaScript",
        b"/Launch",
        b"/OpenAction",
        b"/AcroForm",
        b"/XFA",
        b"/RichMedia",
    ):
        with pytest.raises(PublicationError, match="active action"):
            _validate_file_privacy("presentation.pdf", b"%PDF-1.3\n" + marker)


def test_delivery_holds_shared_lock_until_verified_bytes_are_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import time

    import schauwerk.publication.store as store_module

    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    ready_read, ready_write = os.pipe()
    continue_read, continue_write = os.pipe()
    original_verify = store_module._verify_object_from_paths
    parent_pid = os.getpid()

    def pause_verification(paths, publication_id, version):
        manifest = original_verify(paths, publication_id, version)
        if os.getpid() != parent_pid:
            os.write(ready_write, b"1")
            os.read(continue_read, 1)
        return manifest

    monkeypatch.setattr(store_module, "_verify_object_from_paths", pause_verification)
    child = os.fork()
    if child == 0:
        try:
            store_module.resolve_publication_file(
                store,
                "grabowski-brief",
                None,
                now="2026-07-12T00:00:00Z",
            )
        finally:
            os._exit(0)
    try:
        os.read(ready_read, 1)
        releaser = os.fork()
        if releaser == 0:
            time.sleep(0.2)
            os.write(continue_write, b"1")
            os._exit(0)
        started = time.monotonic()
        withdrawal = withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest=release["link_digest"],
            reason="lock ordering test",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
        elapsed = time.monotonic() - started
        os.waitpid(releaser, 0)
        assert withdrawal["immutable_object_preserved"] is True
        assert elapsed >= 0.15
    finally:
        for descriptor in (ready_read, ready_write, continue_read, continue_write):
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.waitpid(child, 0)


def test_concurrent_identical_releases_converge_on_one_object_link_and_receipt(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    results = tmp_path / "results"
    results.mkdir()
    start_read, start_write = os.pipe()
    children: list[int] = []
    try:
        for index in range(8):
            child = os.fork()
            if child == 0:
                try:
                    os.close(start_write)
                    os.read(start_read, 1)
                    receipt = release_publication(
                        declaration=declaration,
                        preview=preview,
                        source_dir=SOURCE,
                        store_root=store,
                    )
                    (results / f"{index}.json").write_text(
                        json.dumps(receipt, sort_keys=True),
                        encoding="utf-8",
                    )
                    os._exit(0)
                except BaseException as exc:
                    (results / f"{index}.error").write_text(repr(exc), encoding="utf-8")
                    os._exit(1)
            children.append(child)
        os.close(start_read)
        os.write(start_write, b"1" * len(children))
        os.close(start_write)
        statuses = [os.waitpid(child, 0)[1] for child in children]
        assert statuses == [0] * len(children)
        assert list(results.glob("*.error")) == []
        receipts = [
            json.loads((results / f"{index}.json").read_text(encoding="utf-8"))
            for index in range(len(children))
        ]
        assert all(receipt == receipts[0] for receipt in receipts)
        assert len(list((store / "receipts").glob("release-*.json"))) == 1
        assert len(list((store / "links").glob("*.json"))) == 1
        assert (
            verify_object(
                store,
                "grabowski-operational-brief",
                "1.0.0",
            )["object_digest"]
            == receipts[0]["object_digest"]
        )
    finally:
        for descriptor in (start_read, start_write):
            try:
                os.close(descriptor)
            except OSError:
                pass
        for child in children:
            try:
                os.waitpid(child, os.WNOHANG)
            except ChildProcessError:
                pass
        _make_store_removable(store)


def test_links_metadata_and_withdrawal_reasons_require_canonical_safe_text() -> None:
    from schauwerk.publication.model import (
        compile_preview_from_loaded,
        digest_mapping,
        load_source_package,
    )
    from schauwerk.publication.store import validate_link

    declaration, preview = compiled_pair(expires_at=None)
    link = {
        "schema_version": "schauwerk-publication-link.v1",
        "stable_slug": preview["stable_slug"],
        "publication_id": preview["publication_id"],
        "version": preview["version"],
        "object_digest": "a" * 64,
        "state": "active",
        "published_at": "2026-01-01T00:00:00.500000Z",
        "expires_at": None,
        "updated_at": "2026-01-01T00:00:00.500000Z",
        "withdrawn_at": None,
        "withdrawal_reason": None,
        "previous_link_digest": None,
        "link_digest": "",
    }
    link["link_digest"] = digest_mapping(link, "link_digest")
    with pytest.raises(PublicationError, match="timestamps are not canonical"):
        validate_link(link)

    manifest, payloads = load_source_package(SOURCE)
    manifest = copy.deepcopy(manifest)
    manifest["artifact_metadata"]["variant_title"] = "unsafe\u001btitle"
    draft = declaration_draft()
    with pytest.raises(PublicationError, match="control characters"):
        compile_preview_from_loaded(compile_declaration(draft), manifest, payloads)


def test_withdrawal_reason_control_characters_fail_before_link_mutation(
    tmp_path: Path,
) -> None:
    declaration, preview = compiled_pair(expires_at=None)
    store = tmp_path / "store"
    release = release_publication(
        declaration=declaration,
        preview=preview,
        source_dir=SOURCE,
        store_root=store,
    )
    before = (store / "links/grabowski-brief.json").read_bytes()
    with pytest.raises(PublicationError, match="control characters"):
        withdraw_publication(
            store,
            "grabowski-brief",
            expected_link_digest=release["link_digest"],
            reason="unsafe\nreason",
            withdrawn_at="2026-07-13T00:00:00Z",
        )
    assert (store / "links/grabowski-brief.json").read_bytes() == before
