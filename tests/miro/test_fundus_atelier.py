from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

import schauwerk.surfaces.miro.fundus_atelier as atelier
from schauwerk.fundus.core import Fundus, FundusPaths
from schauwerk.fundus.model import digest_json
from schauwerk.surfaces.miro.board_registry import BoardAllowlist
from schauwerk.surfaces.miro.credentials import FileTokenStorage
from schauwerk.surfaces.miro.errors import MiroCredentialError
from schauwerk.surfaces.miro.models import MiroSettings

BOARD_URL = "https://miro.com/app/board/uXjVFundusAtelier=/"
SIMPLE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 150">'
    b'<path fill="#000" d="M10 10 H90 V140 H10 Z"/>'
    b"</svg>"
)


def result(payload: dict, *, error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=error, structuredContent=payload, content=[])


def validate_schema(name: str, document: dict) -> None:
    schema = json.loads(files("schauwerk.schemas").joinpath(name).read_text())
    Draft202012Validator(schema).validate(document)


def _fundus(tmp_path: Path) -> Fundus:
    data = tmp_path / "fundus-data"
    registry = tmp_path / "registry"
    (registry / "recipes").mkdir(parents=True)
    (registry / "families").mkdir()
    (registry / "assets").mkdir()
    (registry / "recipes" / "svg-mask-v1.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-recipe.v1",
                "id": "svg-mask-v1",
                "transform": "sanitize_svg",
                "source_role": "trace_source",
                "output": {
                    "role": "mask",
                    "filename": "mask.svg",
                    "media_type": "image/svg+xml",
                },
                "parameters": {"profile": "svg.mask.v1"},
            }
        ),
        encoding="utf-8",
    )
    (registry / "families" / "fixture.atelier.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-family.v1",
                "id": "fixture.atelier",
                "title": "Fixture Atelier",
                "tags": ["fixture", "review"],
            }
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source.svg"
    source.write_bytes(SIMPLE_SVG)
    fundus = Fundus(FundusPaths(data_root=data, registry_root=registry))
    ingest = fundus.ingest(source, origin="test-fixture", rights_status="owned")
    (registry / "assets" / "fixture.atelier.01.json").write_text(
        json.dumps(
            {
                "schema_version": "schauwerk-fundus-asset.v1",
                "id": "fixture.atelier.01",
                "family": "fixture.atelier",
                "recipe": "svg-mask-v1",
                "sources": [
                    {
                        "role": "trace_source",
                        "sha256": ingest["sha256"],
                        "media_type": "image/svg+xml",
                        "origin": "test-fixture",
                        "rights_status": "owned",
                    }
                ],
                "properties": {
                    "mirror_safe": False,
                    "rotate_safe": False,
                    "recolor_safe": True,
                    "mask_safe": True,
                    "tile_safe": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return fundus


def _settings(tmp_path: Path) -> MiroSettings:
    settings = MiroSettings(state_root=tmp_path / "miro-state")
    BoardAllowlist(settings.board_allowlist_path).add("atelier-test", BOARD_URL)
    return settings


def test_plan_is_digest_bound_and_does_not_infer_acceptance(tmp_path: Path) -> None:
    fundus = _fundus(tmp_path)
    first = atelier.build_atelier_plan(fundus, "fixture.atelier")
    second = atelier.build_atelier_plan(fundus, "fixture.atelier")

    assert first.plan_digest == second.plan_digest
    assert len(first.variants) == 1
    variant = first.variants[0]
    assert variant.asset_id == "fixture.atelier.01"
    assert variant.fundus_acceptance_state == "unreviewed"
    assert variant.output_path.read_bytes().startswith(b"<svg")
    public = first.to_dict()
    validate_schema("miro-fundus-atelier-plan.v1.schema.json", public)
    assert public["fundus_authoritative"] is True
    assert public["miro_source_of_truth"] is False
    assert public["visual_acceptance_inferred"] is False
    assert public["package_created"] is False
    assert "output_path" not in public["variants"][0]
    assert not any((fundus.root / "acceptances").rglob("*.json"))
    assert not any((fundus.root / "packages").rglob("*.json"))


def test_canvas_is_frame_based_review_surface(tmp_path: Path) -> None:
    plan = atelier.build_atelier_plan(_fundus(tmp_path), "fixture.atelier")
    canvas = atelier.render_atelier_canvas(plan)

    assert 'id="atelier-overview"' in canvas
    assert 'id="variant-01"' in canvas
    assert "Miro ist nur Arbeits- und Reviewfläche" in canvas
    assert "ENTWURF · NICHT FREIGEGEBEN" in canvas
    assert plan.plan_digest[:16] in canvas
    assert 'fill="#FFFFFF" data-title="Fundus Atelier — Überblick"' in canvas
    assert 'font-size="28" fill="#302820"' in canvas
    assert "<b>" not in canvas
    assert "<br" not in canvas
    assert "data-miro-id" not in canvas


def test_publish_uploads_exact_build_into_bound_frame_and_writes_sanitized_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fundus = _fundus(tmp_path)
    plan = atelier.build_atelier_plan(fundus, "fixture.atelier")
    settings = _settings(tmp_path)
    receipt_path = tmp_path / "atelier-receipt.json"
    calls: list[tuple[str, dict]] = []
    uploaded: list[bytes] = []
    inventories = [
        [],
        [
            {
                "id": "200",
                "type": "image",
                "parent": {"id": "11"},
                "position": {"x": 500, "y": 790},
                "geometry": {"width": 800, "height": 1200},
            }
        ],
    ]

    async def call_tool(name: str, arguments: dict):
        calls.append((name, arguments))
        if name == "board_list_items":
            return result({"data": inventories.pop(0), "has_more": False})
        if name == "canvas_create_from_svg":
            return result(
                {
                    "success": True,
                    "created_count": 8,
                    "miro_url": BOARD_URL,
                    "result_svg": (
                        '<svg xmlns="http://www.w3.org/2000/svg">'
                        '<g id="atelier-overview" data-miro-id="10">'
                        '<rect data-type="frame" />'
                        "</g>"
                        '<g id="variant-01" data-miro-id="11">'
                        '<rect data-type="frame" />'
                        "</g>"
                        "</svg>"
                    ),
                }
            )
        if name == "image_get_upload_url":
            assert "moveToWidget=11" in arguments["miro_url"]
            assert arguments["x"] == 500
            assert arguments["y"] == 790
            assert arguments["width"] == 800.0
            return result(
                {
                    "upload_url": "https://upload.example.invalid/atelier",
                    "token": "one-use-image-token",
                }
            )
        if name == "image_create":
            return result({"miro_url": f"{BOARD_URL}?moveToWidget=200"})
        raise AssertionError(name)

    @asynccontextmanager
    async def fake_live(_settings, _storage):
        yield (
            call_tool,
            {
                "canvas_create_from_svg",
                "image_get_upload_url",
                "image_create",
                "board_list_items",
            },
            object(),
        )

    async def fake_upload(_client, _url: str, _content_type: str, payload: bytes) -> bool:
        uploaded.append(payload)
        return True

    monkeypatch.setattr(atelier, "_live_mcp", fake_live)
    monkeypatch.setattr(atelier, "_upload_bytes", fake_upload)

    receipt = asyncio.run(
        atelier.publish_atelier_plan(
            settings,
            FileTokenStorage(settings.credentials_path),
            plan=plan,
            fundus=fundus,
            alias="atelier-test",
            receipt_path=receipt_path,
        )
    )

    assert receipt["success"] is True
    assert receipt["fundus_authoritative"] is True
    assert receipt["miro_source_of_truth"] is False
    assert receipt["visual_acceptance_inferred"] is False
    assert receipt["package_created"] is False
    assert receipt["variants"][0]["frame_item_id"] == "11"
    assert receipt["variants"][0]["image_item_id"] == "200"
    assert receipt["variants"][0]["parent_verified"] is True
    assert receipt["variants"][0]["geometry_verified"] is True
    assert receipt["variants"][0]["position_verified"] is True
    assert receipt["variants"][0]["render_width"] == 800.0
    assert uploaded == [plan.variants[0].output_path.read_bytes()]
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    rendered = receipt_path.read_text(encoding="utf-8")
    assert BOARD_URL not in rendered
    assert "upload.example.invalid" not in rendered
    assert "one-use-image-token" not in rendered
    validate_schema("miro-fundus-atelier-receipt.v1.schema.json", receipt)
    checked = atelier.check_atelier_receipt(receipt_path)
    assert checked["ok"] is True
    assert [name for name, _ in calls].count("canvas_create_from_svg") == 1



def test_receipt_check_rejects_structured_miro_url_with_valid_digest(
    tmp_path: Path,
) -> None:
    body = {
        "schema_version": atelier.ATELIER_RECEIPT_SCHEMA,
        "success": True,
        "board_alias": BOARD_URL,
        "board_reference_digest": "0" * 16,
        "family_id": "fixture.atelier",
        "plan_digest": "1" * 64,
        "projection_mode": "append_create_only",
        "variants": [
            {
                "asset_id": "fixture.atelier.01",
                "build_digest": "2" * 64,
                "output_sha256": "3" * 64,
                "output_role": "mask",
                "fundus_acceptance_state": "unreviewed",
                "frame_item_id": "11",
                "image_item_id": "12",
                "render_width": 800.0,
                "parent_verified": True,
                "geometry_verified": True,
                "position_verified": True,
            }
        ],
        "variant_count": 1,
        "readback": {
            "before_image_count": 0,
            "after_image_count": 1,
            "inventory_pages": 2,
            "all_created_images_present": True,
            "all_created_images_parent_verified": True,
        },
        "fundus_authoritative": True,
        "miro_source_of_truth": False,
        "visual_acceptance_inferred": False,
        "package_created": False,
        "sanitized_references": True,
    }
    document = {**body, "receipt_digest": digest_json(body)}
    receipt = tmp_path / "provider-url-receipt.json"
    receipt.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MiroCredentialError, match="unsanitized provider reference"):
        atelier.check_atelier_receipt(receipt)

def test_output_drift_fails_before_any_miro_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fundus = _fundus(tmp_path)
    plan = atelier.build_atelier_plan(fundus, "fixture.atelier")
    settings = _settings(tmp_path)
    plan.variants[0].output_path.chmod(0o600)
    plan.variants[0].output_path.write_bytes(b"drift")
    entered = False

    @asynccontextmanager
    async def fake_live(_settings, _storage):
        nonlocal entered
        entered = True
        yield None

    monkeypatch.setattr(atelier, "_live_mcp", fake_live)

    with pytest.raises(Exception, match="drifted"):
        asyncio.run(
            atelier.publish_atelier_plan(
                settings,
                FileTokenStorage(settings.credentials_path),
                plan=plan,
                fundus=fundus,
                alias="atelier-test",
                receipt_path=tmp_path / "unused.json",
            )
        )
    assert entered is False


def test_existing_receipt_path_fails_before_any_miro_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fundus = _fundus(tmp_path)
    plan = atelier.build_atelier_plan(fundus, "fixture.atelier")
    settings = _settings(tmp_path)
    receipt = tmp_path / "occupied.json"
    receipt.write_text("occupied", encoding="utf-8")
    entered = False

    @asynccontextmanager
    async def fake_live(_settings, _storage):
        nonlocal entered
        entered = True
        yield None

    monkeypatch.setattr(atelier, "_live_mcp", fake_live)

    with pytest.raises(Exception, match="already exists"):
        asyncio.run(
            atelier.publish_atelier_plan(
                settings,
                FileTokenStorage(settings.credentials_path),
                plan=plan,
                fundus=fundus,
                alias="atelier-test",
                receipt_path=receipt,
            )
        )
    assert entered is False
