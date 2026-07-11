from __future__ import annotations

import hashlib
import json
from pathlib import Path

from schauwerk.publication.model import compile_declaration
from schauwerk.runner import main

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/operators/evidence/sw012-buehne-20260711/technical/public"


def _declaration() -> dict:
    manifest_path = SOURCE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return compile_declaration(
        {
            "publication_id": "grabowski-operational-brief",
            "stable_slug": "grabowski-brief",
            "version": "1.0.0",
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
                "source_revision",
                "visible_content_sha256",
            ],
            "sources": [
                {
                    "id": "primary",
                    "visibility": "public",
                    "fields": ["id", "revision", "sha256"],
                }
            ],
            "lifecycle": {
                "published_at": "2026-07-11T12:00:00Z",
                "expires_at": None,
                "replaces_version": None,
                "expected_link_digest": None,
            },
        }
    )


def test_publication_cli_preview_release_status_and_withdrawal(tmp_path: Path, capsys) -> None:
    declaration = tmp_path / "declaration.json"
    preview = tmp_path / "preview.json"
    store = tmp_path / "store"
    declaration.write_text(json.dumps(_declaration()), encoding="utf-8")

    assert (
        main(
            [
                "publish",
                "preview",
                str(declaration),
                "--source-package",
                str(SOURCE),
                "--output",
                str(preview),
                "--json",
            ]
        )
        == 0
    )
    preview_result = json.loads(capsys.readouterr().out)
    assert preview_result["provider_mutation_attempted"] is False

    assert (
        main(
            [
                "publish",
                "release",
                str(declaration),
                str(preview),
                "--source-package",
                str(SOURCE),
                "--store-root",
                str(store),
                "--json",
            ]
        )
        == 0
    )
    release = json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "publish",
                "status",
                "grabowski-brief",
                "--store-root",
                str(store),
                "--at",
                "2026-07-12T00:00:00Z",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["state"] == "active"

    assert (
        main(
            [
                "publish",
                "withdraw",
                "grabowski-brief",
                "--store-root",
                str(store),
                "--expected-link-digest",
                release["link_digest"],
                "--reason",
                "CLI test",
                "--at",
                "2026-07-13T00:00:00Z",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["immutable_object_preserved"] is True


def test_publication_preview_rejects_symlinked_output_parent(
    tmp_path: Path,
    capsys,
) -> None:
    declaration = tmp_path / "declaration.json"
    declaration.write_text(json.dumps(_declaration()), encoding="utf-8")
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(foreign, target_is_directory=True)

    assert (
        main(
            [
                "publish",
                "preview",
                str(declaration),
                "--source-package",
                str(SOURCE),
                "--output",
                str(linked_parent / "preview.json"),
                "--json",
            ]
        )
        == 2
    )
    assert "output parent is unsafe" in capsys.readouterr().err
    assert not (foreign / "preview.json").exists()


def test_publication_preview_requires_existing_output_parent(
    tmp_path: Path,
    capsys,
) -> None:
    declaration = tmp_path / "declaration.json"
    declaration.write_text(json.dumps(_declaration()), encoding="utf-8")
    output = tmp_path / "missing" / "preview.json"

    assert (
        main(
            [
                "publish",
                "preview",
                str(declaration),
                "--source-package",
                str(SOURCE),
                "--output",
                str(output),
                "--json",
            ]
        )
        == 2
    )
    assert "output parent does not exist" in capsys.readouterr().err
    assert not output.exists()
