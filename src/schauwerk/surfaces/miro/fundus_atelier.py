"""Digest-bound Fundus review projections for Miro.

Fundus remains authoritative. This module only projects exact build outputs into
Miro for collaborative review and presentation. Publishing never creates a
Fundus acceptance or package.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from jsonschema import Draft202012Validator

from schauwerk.fundus.core import MAX_BUILD_OUTPUT_BYTES, Fundus, FundusPaths
from schauwerk.fundus.errors import FundusError
from schauwerk.fundus.media import inspect_media
from schauwerk.fundus.model import (
    checked_id,
    digest_json,
    load_json,
    validate_asset,
    validate_family,
)

from .board_registry import BoardAllowlist, reference_digest, validate_alias
from .credentials import FileTokenStorage
from .errors import MiroCredentialError, MiroToolError
from .inspection import checked_payload
from .managed_image_runtime import list_all_images
from .managed_image_service import (
    _live_mcp,
    _new_output,
    _upload_bytes,
    _write_new_private_json,
)
from .models import MiroSettings

ATELIER_PLAN_SCHEMA = "schauwerk-miro-fundus-atelier-plan.v1"
ATELIER_RECEIPT_SCHEMA = "schauwerk-miro-fundus-atelier-receipt.v1"
ATELIER_RECEIPT_SCHEMA_FILE = "miro-fundus-atelier-receipt.v1.schema.json"
_ITEM_ID = re.compile(r"^[0-9]{1,32}$")
_PUBLISH_MEDIA_TYPES = {"image/svg+xml", "image/png", "image/jpeg"}


@dataclass(frozen=True)
class AtelierVariant:
    asset_id: str
    build_digest: str
    output_role: str
    output_sha256: str
    output_media_type: str
    output_filename: str
    output_path: Path
    fundus_acceptance_state: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "build_digest": self.build_digest,
            "output_role": self.output_role,
            "output_sha256": self.output_sha256,
            "output_media_type": self.output_media_type,
            "output_filename": self.output_filename,
            "fundus_acceptance_state": self.fundus_acceptance_state,
            "miro_visual_acceptance_inferred": False,
        }


@dataclass(frozen=True)
class AtelierPlan:
    family_id: str
    family_title: str
    variants: tuple[AtelierVariant, ...]
    plan_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ATELIER_PLAN_SCHEMA,
            "family_id": self.family_id,
            "family_title": self.family_title,
            "variants": [item.public_dict() for item in self.variants],
            "variant_count": len(self.variants),
            "plan_digest": self.plan_digest,
            "fundus_authoritative": True,
            "miro_source_of_truth": False,
            "visual_acceptance_inferred": False,
            "package_created": False,
        }


def _acceptance_state(fundus: Fundus, asset_id: str, build_digest: str) -> str:
    root = fundus.root / "acceptances" / asset_id / build_digest
    if not root.exists():
        return "unreviewed"
    decisions: set[str] = set()
    for path in sorted(root.glob("*.json")):
        digest = path.stem
        try:
            record = fundus._load_acceptance(asset_id, build_digest, digest)
        except FundusError:
            return "invalid"
        decision = record.get("decision")
        if decision in {"accepted", "rejected"}:
            decisions.add(decision)
    if not decisions:
        return "unreviewed"
    if decisions == {"accepted"}:
        return "accepted"
    if decisions == {"rejected"}:
        return "rejected"
    return "mixed"


def build_atelier_plan(fundus: Fundus, family_id: str) -> AtelierPlan:
    """Materialize exact current Fundus builds for one asset family."""

    family_id = checked_id(family_id, label="family id")
    family_path = fundus.paths.registry_root / "families" / f"{family_id}.json"
    if not family_path.is_file():
        raise FundusError(f"Fundus family is not declared: {family_id}")
    try:
        family = load_json(family_path)
        validate_family(family)
    except (OSError, ValueError) as exc:
        raise FundusError(str(exc)) from exc
    if family.get("id") != family_id:
        raise FundusError("family id does not match registry filename")

    assets_root = fundus.paths.registry_root / "assets"
    variants: list[AtelierVariant] = []
    for path in sorted(assets_root.glob("*.json")):
        try:
            asset = load_json(path)
            validate_asset(asset)
        except (OSError, ValueError) as exc:
            raise FundusError(str(exc)) from exc
        if asset.get("family") != family_id:
            continue
        asset_id = asset["id"]
        if path.name != f"{asset_id}.json":
            raise FundusError("asset id does not match registry filename")
        build = fundus.build(asset_id)
        outputs = build.get("outputs", [])
        if len(outputs) != 1:
            raise FundusError("Fundus Atelier v1 requires exactly one build output per asset")
        output = outputs[0]
        output_path = Path(build["build_dir"]) / output["filename"]
        payload = fundus._read_private(output_path, maximum_bytes=MAX_BUILD_OUTPUT_BYTES)
        if hashlib.sha256(payload).hexdigest() != output["sha256"]:
            raise FundusError("Fundus build output drifted before Atelier planning")
        variants.append(
            AtelierVariant(
                asset_id=asset_id,
                build_digest=build["build_digest"],
                output_role=output["role"],
                output_sha256=output["sha256"],
                output_media_type=output["media_type"],
                output_filename=output["filename"],
                output_path=output_path,
                fundus_acceptance_state=_acceptance_state(
                    fundus, asset_id, build["build_digest"]
                ),
            )
        )
    if not variants:
        raise FundusError(f"Fundus family has no declared assets: {family_id}")

    body = {
        "schema_version": ATELIER_PLAN_SCHEMA,
        "family_id": family_id,
        "family_title": family["title"],
        "variants": [item.public_dict() for item in variants],
        "fundus_authoritative": True,
        "miro_source_of_truth": False,
        "visual_acceptance_inferred": False,
        "package_created": False,
    }
    return AtelierPlan(
        family_id=family_id,
        family_title=family["title"],
        variants=tuple(variants),
        plan_digest=digest_json(body),
    )


def build_atelier_plan_from_paths(
    *,
    family_id: str,
    data_root: str | Path | None = None,
    registry_root: str | Path | None = None,
) -> AtelierPlan:
    return build_atelier_plan(
        Fundus(
            FundusPaths.from_overrides(
                data_root=data_root,
                registry_root=registry_root,
            )
        ),
        family_id,
    )


def _xml(value: str) -> str:
    return html.escape(value, quote=True)


def render_atelier_canvas(plan: AtelierPlan) -> str:
    """Render a deterministic Canvas Composer review layout."""

    def line(*parts: str) -> str:
        return "".join(parts)

    overview_title = "Fundus Atelier — Überblick"
    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg">',
        line(
            '<g id="atelier-overview" transform="translate(0,0)" ',
            f'data-frame="{_xml(overview_title)}">',
        ),
        line(
            '<rect data-type="frame" x="0" y="0" width="2100" height="620" ',
            f'fill="#FFFFFF" data-title="{_xml(overview_title)}" />',
        ),
        line(
            '<text x="80" y="105" font-family="georgia" font-size="52" ',
            'font-weight="bold" fill="#D7B46A">Fundus Atelier</text>',
        ),
        line(
            '<textArea x="80" y="155" width="1880" font-family="open_sans" ',
            'font-size="28" fill="#302820">',
            _xml(plan.family_title),
            ' — Gemeinsame Sichtung und Präsentation exakter Fundus-Builds. ',
            'Miro ist nur Arbeits- und Reviewfläche; Fundus bleibt die Assetautorität.',
            '</textArea>',
        ),
        line(
            '<rect x="80" y="340" width="620" height="110" rx="22" ',
            'fill="#2A2117" stroke="#D7B46A" ',
            'data-content="KEINE FREIGABE DURCH MIRO" ',
            'data-text-color="#F7F1E7" data-font-size="24" ',
            'data-font-weight="bold" />',
        ),
        line(
            '<textArea x="80" y="485" width="1880" font-family="plex_mono" ',
            'font-size="18" fill="#6E5A3A">Plan ',
            plan.plan_digest[:16],
            ' · Kommentare und Anordnung dürfen sich ändern. Assetbytes, ',
            'Build-Digests und Acceptance bleiben Fundus-Sache.</textArea>',
        ),
        '</g>',
    ]
    frame_width = 1000
    frame_height = 1700
    gap_x = 1100
    gap_y = 1800
    start_y = 760
    for index, variant in enumerate(plan.variants):
        row, col = divmod(index, 3)
        x = col * gap_x
        y = start_y + row * gap_y
        number = index + 1
        local_id = f"variant-{number:02d}"
        frame_title = f"Variante {number:02d} — {variant.asset_id}"
        status = (
            "FUNDUS: FREIGEGEBEN"
            if variant.fundus_acceptance_state == "accepted"
            else "ENTWURF · NICHT FREIGEGEBEN"
        )
        status_fill = (
            "#23452F" if variant.fundus_acceptance_state == "accepted" else "#5A281E"
        )
        pieces.extend(
            [
                line(
                    f'<g id="{local_id}" transform="translate({x},{y})" ',
                    f'data-frame="{_xml(frame_title)}">',
                ),
                line(
                    '<rect data-type="frame" x="0" y="0" ',
                    f'width="{frame_width}" height="{frame_height}" ',
                    f'fill="#FFFFFF" data-title="{_xml(frame_title)}" />',
                ),
                line(
                    '<text x="70" y="90" font-family="georgia" font-size="42" ',
                    'font-weight="bold" fill="#17130F">',
                    f'Variante {number:02d}</text>',
                ),
                line(
                    '<rect x="610" y="48" width="320" height="70" rx="18" ',
                    f'fill="{status_fill}" stroke="none" ',
                    f'data-content="{_xml(status)}" data-text-color="#FFFFFF" ',
                    'data-font-size="18" data-font-weight="bold" />',
                ),
                line(
                    '<rect x="80" y="180" width="840" height="1220" rx="12" ',
                    'fill="#EFE5D4" stroke="#C5A66A" />',
                ),
                line(
                    '<textArea x="80" y="1440" width="840" ',
                    'font-family="plex_mono" font-size="18" fill="#302820">',
                    _xml(variant.asset_id),
                    ' · Build ',
                    variant.build_digest[:16],
                    '… · Output ',
                    _xml(variant.output_role),
                    ' · ',
                    variant.output_sha256[:16],
                    '… · Fundus-Acceptance: ',
                    _xml(variant.fundus_acceptance_state),
                    '</textArea>',
                ),
                '</g>',
            ]
        )
    pieces.append("</svg>")
    return "\n".join(pieces)

def _frame_ids(result_svg: str, expected_ids: set[str]) -> dict[str, str]:
    try:
        root = ET.fromstring(result_svg)
    except ET.ParseError as exc:
        raise MiroToolError("Miro Canvas returned invalid result SVG") from exc
    found: dict[str, str] = {}
    for element in root.iter():
        local_id = element.attrib.get("id")
        if local_id not in expected_ids:
            continue
        item_id = element.attrib.get("data-miro-id")
        if item_id is None:
            for child in element.iter():
                if child.attrib.get("data-type") == "frame":
                    item_id = child.attrib.get("data-miro-id")
                    if item_id:
                        break
        if item_id is None or _ITEM_ID.fullmatch(item_id) is None:
            raise MiroToolError("Miro Canvas did not bind an expected frame id")
        found[local_id] = item_id
    missing = expected_ids - found.keys()
    if missing:
        raise MiroToolError("Miro Canvas omitted one or more expected Atelier frames")
    return found


def _target_url(board_url: str, item_id: str) -> str:
    if _ITEM_ID.fullmatch(item_id) is None:
        raise MiroToolError("Miro Atelier frame id is invalid")
    parsed = urlsplit(board_url)
    if parsed.scheme != "https" or parsed.hostname != "miro.com":
        raise MiroCredentialError("allowlisted Miro board URL is invalid")
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode({"moveToWidget": item_id}), "")
    )


def _created_item_id(value: Any) -> str:
    payload = checked_payload(value, "image_create")
    url = payload.get("miro_url")
    if not isinstance(url, str):
        raise MiroToolError("Miro image_create returned no item URL")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise MiroToolError("Miro image_create returned an invalid item URL") from exc
    if parsed.scheme != "https" or parsed.hostname != "miro.com":
        raise MiroToolError("Miro image_create returned an unexpected item origin")
    ids = parse_qs(parsed.query, keep_blank_values=True).get("moveToWidget", [])
    if len(ids) != 1 or _ITEM_ID.fullmatch(ids[0]) is None:
        raise MiroToolError("Miro image_create returned an invalid item id")
    return ids[0]


def _load_variant_bytes(fundus: Fundus, variant: AtelierVariant) -> bytes:
    payload = fundus._read_private(
        variant.output_path,
        maximum_bytes=MAX_BUILD_OUTPUT_BYTES,
    )
    if hashlib.sha256(payload).hexdigest() != variant.output_sha256:
        raise FundusError("Fundus build output drifted before Miro upload")
    return payload


def _review_width(payload: bytes) -> float:
    try:
        media = inspect_media(payload)
    except ValueError as exc:
        raise FundusError(str(exc)) from exc
    if media.width is None or media.height is None:
        return 800.0
    scale = min(800.0 / media.width, 1200.0 / media.height)
    return round(media.width * scale, 3)


def _validate_atelier_receipt_schema(document: dict[str, Any]) -> None:
    try:
        schema = json.loads(
            resources.files("schauwerk.schemas")
            .joinpath(ATELIER_RECEIPT_SCHEMA_FILE)
            .read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MiroCredentialError("Fundus Atelier receipt schema is unavailable") from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: list(error.path),
    )
    if errors:
        raise MiroCredentialError("Fundus Atelier receipt violates its schema")


def _reject_provider_references(value: Any) -> None:
    if isinstance(value, dict):
        forbidden_keys = {"upload_url", "image_token"}.intersection(value)
        if forbidden_keys:
            raise MiroCredentialError(
                "Fundus Atelier receipt contains an unsanitized provider reference"
            )
        for nested in value.values():
            _reject_provider_references(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _reject_provider_references(nested)
        return
    if not isinstance(value, str):
        return
    try:
        parsed = urlsplit(value)
    except ValueError:
        return
    hostname = parsed.hostname
    if parsed.scheme in {"http", "https"} and isinstance(hostname, str):
        normalized = hostname.rstrip(".").lower()
        if normalized == "miro.com" or normalized.endswith(".miro.com"):
            raise MiroCredentialError(
                "Fundus Atelier receipt contains an unsanitized provider reference"
            )


def check_atelier_receipt(path: str | Path) -> dict[str, Any]:
    """Verify schema, self-digest and hard authority claims of one local receipt."""

    document = load_json(Path(path), maximum_bytes=1_000_000)
    _validate_atelier_receipt_schema(document)
    digest = document.get("receipt_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise MiroCredentialError("Fundus Atelier receipt digest is invalid")
    body = dict(document)
    body.pop("receipt_digest", None)
    if digest_json(body) != digest:
        raise MiroCredentialError("Fundus Atelier receipt content drifted")
    if document.get("schema_version") != ATELIER_RECEIPT_SCHEMA:
        raise MiroCredentialError("Fundus Atelier receipt schema is unsupported")
    if document.get("fundus_authoritative") is not True:
        raise MiroCredentialError("Fundus Atelier receipt lost Fundus authority")
    if document.get("miro_source_of_truth") is not False:
        raise MiroCredentialError("Fundus Atelier receipt grants Miro invalid authority")
    if document.get("visual_acceptance_inferred") is not False:
        raise MiroCredentialError("Fundus Atelier receipt infers visual acceptance")
    if document.get("package_created") is not False:
        raise MiroCredentialError("Fundus Atelier receipt falsely claims packaging")
    _reject_provider_references(document)
    return {**document, "ok": True}


async def publish_atelier_plan(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    plan: AtelierPlan,
    fundus: Fundus,
    alias: str,
    receipt_path: Path,
    max_pages: int = 100,
) -> dict[str, Any]:
    """Append one create-only digest-bound review projection to an allowlisted board."""

    alias = validate_alias(alias)
    board_url = BoardAllowlist(settings.board_allowlist_path).resolve(alias)
    receipt_path = _new_output(
        receipt_path,
        protected={
            settings.credentials_path.expanduser().absolute(),
            settings.catalogue_path.expanduser().absolute(),
            settings.auth_health_path.expanduser().absolute(),
            settings.auth_history_path.expanduser().absolute(),
            settings.board_allowlist_path.expanduser().absolute(),
        },
        label="Fundus Atelier receipt",
    )
    payloads: dict[str, bytes] = {}
    review_widths: dict[str, float] = {}
    for variant in plan.variants:
        if variant.output_media_type not in _PUBLISH_MEDIA_TYPES:
            raise MiroToolError(
                f"Fundus Atelier cannot upload output media type: {variant.output_media_type}"
            )
        payloads[variant.asset_id] = _load_variant_bytes(fundus, variant)
        review_widths[variant.asset_id] = _review_width(payloads[variant.asset_id])
    canvas = render_atelier_canvas(plan)
    expected_frame_keys = {
        "atelier-overview",
        *(f"variant-{index:02d}" for index in range(1, len(plan.variants) + 1)),
    }

    created: list[dict[str, Any]] = []
    async with _live_mcp(settings, storage) as (call_tool, capabilities, upload_client):
        required = {
            "canvas_create_from_svg",
            "image_get_upload_url",
            "image_create",
            "board_list_items",
        }
        missing = sorted(required - capabilities)
        if missing:
            raise MiroToolError(
                "Miro Fundus Atelier capabilities are incomplete: " + ", ".join(missing)
            )
        before_images, before_pages = await list_all_images(
            call_tool, board_url=board_url, max_pages=max_pages
        )
        canvas_result = await call_tool(
            "canvas_create_from_svg",
            {
                "miro_url": board_url,
                "svg": canvas,
                "invocation_source": "schauwerk-fundus-atelier",
                "is_repository": True,
            },
        )
        canvas_payload = checked_payload(canvas_result, "canvas_create_from_svg")
        result_svg = canvas_payload.get("result_svg")
        if not isinstance(result_svg, str) or not result_svg.strip():
            raise MiroToolError("Miro Canvas returned no result SVG")
        frames = _frame_ids(result_svg, expected_frame_keys)

        for index, variant in enumerate(plan.variants, 1):
            payload = payloads[variant.asset_id]
            frame_id = frames[f"variant-{index:02d}"]
            parent_url = _target_url(board_url, frame_id)
            upload_result = await call_tool(
                "image_get_upload_url",
                {
                    "miro_url": parent_url,
                    "content_type": variant.output_media_type,
                    "title": f"{variant.asset_id} — {variant.build_digest[:12]}",
                    "x": 500,
                    "y": 790,
                    "width": review_widths[variant.asset_id],
                    "invocation_source": "schauwerk-fundus-atelier",
                    "is_repository": True,
                },
            )
            upload_payload = checked_payload(upload_result, "image_get_upload_url")
            upload_url = upload_payload.get("upload_url")
            image_token = upload_payload.get("token")
            if not isinstance(upload_url, str) or not isinstance(image_token, str):
                raise MiroToolError("Miro image upload contract is invalid")
            await _upload_bytes(
                upload_client,
                upload_url,
                variant.output_media_type,
                payload,
            )
            image_result = await call_tool(
                "image_create",
                {
                    "miro_url": parent_url,
                    "image_token": image_token,
                    "invocation_source": "schauwerk-fundus-atelier",
                    "is_repository": True,
                },
            )
            image_id = _created_item_id(image_result)
            created.append(
                {
                    "asset_id": variant.asset_id,
                    "build_digest": variant.build_digest,
                    "output_sha256": variant.output_sha256,
                    "output_role": variant.output_role,
                    "fundus_acceptance_state": variant.fundus_acceptance_state,
                    "frame_item_id": frame_id,
                    "image_item_id": image_id,
                    "render_width": review_widths[variant.asset_id],
                }
            )

        after_images, after_pages = await list_all_images(
            call_tool, board_url=board_url, max_pages=max_pages
        )

    by_id = {str(item["id"]): item for item in after_images}
    before_ids = {str(item["id"]) for item in before_images}
    for record in created:
        image_id = record["image_item_id"]
        if image_id in before_ids:
            raise MiroToolError("Miro Atelier image id existed before publication")
        image = by_id.get(image_id)
        if image is None:
            raise MiroToolError("Miro Atelier image is absent after publication")
        parent = image.get("parent")
        if not isinstance(parent, dict) or str(parent.get("id")) != record["frame_item_id"]:
            raise MiroToolError("Miro Atelier image parent readback does not match its frame")
        geometry = image.get("geometry")
        width = geometry.get("width") if isinstance(geometry, dict) else None
        width_valid = (
            not isinstance(width, bool)
            and isinstance(width, int | float)
            and abs(float(width) - float(record["render_width"])) <= 1.0
        )
        if not width_valid:
            raise MiroToolError("Miro Atelier image width readback is invalid")
        position = image.get("position")
        x = position.get("x") if isinstance(position, dict) else None
        y = position.get("y") if isinstance(position, dict) else None
        position_valid = (
            not isinstance(x, bool)
            and not isinstance(y, bool)
            and isinstance(x, int | float)
            and isinstance(y, int | float)
            and abs(float(x) - 500.0) <= 1.0
            and abs(float(y) - 790.0) <= 1.0
        )
        if not position_valid:
            raise MiroToolError("Miro Atelier image position readback is invalid")
        record["parent_verified"] = True
        record["geometry_verified"] = True
        record["position_verified"] = True

    body = {
        "schema_version": ATELIER_RECEIPT_SCHEMA,
        "success": True,
        "board_alias": alias,
        "board_reference_digest": reference_digest(board_url),
        "family_id": plan.family_id,
        "plan_digest": plan.plan_digest,
        "projection_mode": "append_create_only",
        "variants": created,
        "variant_count": len(created),
        "readback": {
            "before_image_count": len(before_images),
            "after_image_count": len(after_images),
            "inventory_pages": before_pages + after_pages,
            "all_created_images_present": True,
            "all_created_images_parent_verified": True,
        },
        "fundus_authoritative": True,
        "miro_source_of_truth": False,
        "visual_acceptance_inferred": False,
        "package_created": False,
        "sanitized_references": True,
    }
    receipt = {**body, "receipt_digest": digest_json(body)}
    _validate_atelier_receipt_schema(receipt)
    _write_new_private_json(receipt_path, receipt, label="Fundus Atelier receipt")
    return receipt


async def publish_atelier_from_paths(
    settings: MiroSettings,
    storage: FileTokenStorage,
    *,
    family_id: str,
    alias: str,
    receipt_path: Path,
    data_root: str | Path | None = None,
    registry_root: str | Path | None = None,
    max_pages: int = 100,
) -> dict[str, Any]:
    fundus = Fundus(
        FundusPaths.from_overrides(data_root=data_root, registry_root=registry_root)
    )
    plan = build_atelier_plan(fundus, family_id)
    return await publish_atelier_plan(
        settings,
        storage,
        plan=plan,
        fundus=fundus,
        alias=alias,
        receipt_path=receipt_path,
        max_pages=max_pages,
    )
