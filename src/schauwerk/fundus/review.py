"""Provider-neutral, digest-bound Fundus review pages.

Review bundles are portable static artifacts for comparing exact Fundus builds.
They may use a bounded consumer fragment and local raster fixtures, but they never
create visual acceptance or production packages.
"""

# ruff: noqa: E501

from __future__ import annotations

import ctypes
import errno
import html
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .core import Fundus
from .errors import FundusError
from .media import inspect_media
from .model import (
    checked_id,
    digest_bytes,
    digest_json,
    load_json,
    validate_asset,
    validate_family,
)
from .pathio import read_regular_bytes

REVIEW_PLAN_SCHEMA = "schauwerk-fundus-review-plan.v1"
REVIEW_PLAN_SCHEMA_FILE = "fundus-review-plan.v1.schema.json"
REVIEW_BUNDLE_SCHEMA = "schauwerk-fundus-review-bundle.v1"
REVIEW_BUNDLE_SCHEMA_FILE = "fundus-review-bundle.v1.schema.json"
MAX_TEMPLATE_BYTES = 128 * 1024
MAX_CSS_BYTES = 128 * 1024
MAX_FIXTURE_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_FILE_BYTES = 32 * 1024 * 1024
MAX_REVIEW_TOTAL_BYTES = 96 * 1024 * 1024
MAX_REVIEW_VARIANTS = 256
MAX_REVIEW_FIXTURES = 64
MAX_REVIEW_FILES = 512
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_SAFE_CLASS = re.compile(r"^[A-Za-z0-9 _:-]{0,240}$")
_FIXTURE_TOKEN = re.compile(r"\{\{FIXTURE:([a-z0-9][a-z0-9._-]{0,127})\}\}")
_OUTPUT_EXTENSIONS = {
    "image/svg+xml": ".svg",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_FIXTURE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}
_ALLOWED_TAGS = {
    "article",
    "div",
    "em",
    "figcaption",
    "figure",
    "img",
    "p",
    "section",
    "span",
    "strong",
}
_ALLOWED_ATTRS = {"alt", "class", "role", "loading", "aria-label"}
_DEFAULT_TEMPLATE = (
    '<figure class="consumer-stage">'
    '<img class="consumer-asset" src="{{ASSET_URL}}" alt="{{ASSET_ID}}" loading="lazy">'
    "</figure>"
)
_BASE_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#ece9e2;color:#1b1a18}
header{position:sticky;top:0;z-index:5;padding:18px 24px;background:rgba(250,248,244,.96);border-bottom:1px solid #cfc9bd}
header h1{margin:0 0 4px;font-size:clamp(1.35rem,3vw,2.2rem)}
header p{margin:0;color:#5f5a52}
.authority-note{display:inline-block;margin-top:10px;padding:5px 9px;border:1px solid #9f988b;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.02em}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.toolbar button{font:inherit;padding:7px 11px;border:1px solid #9f988b;border-radius:999px;background:#fff;color:#1b1a18;cursor:pointer}
main{padding:24px}
.grid{display:grid;grid-template-columns:repeat(var(--columns,2),minmax(0,1fr));gap:20px;max-width:1600px;margin:auto}
.card{background:#faf8f4;border:1px solid #cfc9bd;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,.06)}
.card-head{padding:14px 16px;border-bottom:1px solid #d9d4cb}
.card-head strong{display:block}
.meta{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#6f675c;overflow-wrap:anywhere}
.review-surface{min-height:420px;padding:28px;display:grid;place-items:center;background:var(--review-bg,#fff);transition:background .15s ease}
.consumer-stage{width:min(100%,900px);min-height:320px;margin:0;display:grid;place-items:center}
.consumer-asset{display:block;max-width:100%;max-height:70vh;object-fit:contain}
body[data-bg="dark"]{--review-bg:#171717}
body[data-bg="warm"]{--review-bg:#e8dcc8}
body[data-bg="checker"]{--review-bg:repeating-conic-gradient(#ddd 0 25%,#fff 0 50%) 50%/24px 24px}
@media(max-width:850px){.grid{grid-template-columns:1fr!important}.review-surface{min-height:300px;padding:16px}header{position:static}}
""".strip()
_BASE_JS = """(()=>{const b=document.body,g=document.querySelector('.grid');document.querySelectorAll('[data-bg-choice]').forEach(x=>x.addEventListener('click',()=>b.dataset.bg=x.dataset.bgChoice));document.querySelectorAll('[data-cols]').forEach(x=>x.addEventListener('click',()=>g.style.setProperty('--columns',x.dataset.cols)));})();"""


@dataclass(frozen=True)
class ReviewVariant:
    asset_id: str
    build_digest: str
    output_role: str
    output_sha256: str
    output_bytes: int
    output_media_type: str
    output_filename: str
    output_path: Path
    acceptance_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "build_digest": self.build_digest,
            "output_role": self.output_role,
            "output_sha256": self.output_sha256,
            "output_bytes": self.output_bytes,
            "output_media_type": self.output_media_type,
            "output_filename": self.output_filename,
            "acceptance_state": self.acceptance_state,
        }


@dataclass(frozen=True)
class ReviewPlan:
    family_id: str
    family_title: str
    variants: tuple[ReviewVariant, ...]
    plan_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_PLAN_SCHEMA,
            "family_id": self.family_id,
            "family_title": self.family_title,
            "variant_count": len(self.variants),
            "variants": [variant.to_dict() for variant in self.variants],
            "plan_digest": self.plan_digest,
            "fundus_authoritative": True,
            "visual_acceptance_inferred": False,
            "package_created": False,
        }


def _acceptance_state(fundus: Fundus, asset_id: str, build_digest: str) -> str:
    root = fundus.root / "acceptances" / asset_id / build_digest
    if not root.exists():
        return "unreviewed"
    decisions: set[str] = set()
    for path in sorted(root.glob("*.json")):
        try:
            record = fundus._load_acceptance(asset_id, build_digest, path.stem)
        except FundusError:
            return "invalid"
        decision = record.get("decision")
        if decision in {"accepted", "rejected"}:
            decisions.add(decision)
    if decisions == {"accepted"}:
        return "accepted"
    if decisions == {"rejected"}:
        return "rejected"
    if decisions:
        return "mixed"
    return "unreviewed"


def build_review_plan(fundus: Fundus, family_id: str) -> ReviewPlan:
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

    variants: list[ReviewVariant] = []
    for path in sorted((fundus.paths.registry_root / "assets").glob("*.json")):
        try:
            asset = load_json(path)
            validate_asset(asset)
        except (OSError, ValueError) as exc:
            raise FundusError(str(exc)) from exc
        if asset.get("family") != family_id:
            continue
        asset_id = asset["id"]
        if len(variants) >= MAX_REVIEW_VARIANTS:
            raise FundusError("Fundus review family exceeds the variant limit")
        if path.name != f"{asset_id}.json":
            raise FundusError("asset id does not match registry filename")
        build = fundus.build(asset_id)
        outputs = build.get("outputs", [])
        if len(outputs) != 1:
            raise FundusError("Fundus Review v1 requires exactly one build output per asset")
        output = outputs[0]
        output_path = Path(build["build_dir"]) / output["filename"]
        fundus._read_build_output(Path(build["build_dir"]), output)
        variants.append(
            ReviewVariant(
                asset_id=asset_id,
                build_digest=build["build_digest"],
                output_role=output["role"],
                output_sha256=output["sha256"],
                output_bytes=output["bytes"],
                output_media_type=output["media_type"],
                output_filename=output["filename"],
                output_path=output_path,
                acceptance_state=_acceptance_state(
                    fundus,
                    asset_id,
                    build["build_digest"],
                ),
            )
        )
    if not variants:
        raise FundusError(f"Fundus family has no declared assets: {family_id}")
    body = {
        "schema_version": REVIEW_PLAN_SCHEMA,
        "family_id": family_id,
        "family_title": family["title"],
        "variants": [variant.to_dict() for variant in variants],
        "fundus_authoritative": True,
        "visual_acceptance_inferred": False,
        "package_created": False,
    }
    plan = ReviewPlan(
        family_id=family_id,
        family_title=family["title"],
        variants=tuple(variants),
        plan_digest=digest_json(body),
    )
    _validate_schema(plan.to_dict(), REVIEW_PLAN_SCHEMA_FILE, "review plan")
    return plan


class _FragmentValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.asset_sources = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_TAGS:
            raise FundusError(f"consumer template tag is forbidden: {tag}")
        for name, value in attrs:
            if name.startswith("on"):
                raise FundusError(f"consumer template attribute is forbidden: {name}")
            if name not in _ALLOWED_ATTRS and name != "src" and not name.startswith("data-"):
                raise FundusError(f"consumer template attribute is forbidden: {name}")
            if name == "class" and value is not None and _SAFE_CLASS.fullmatch(value) is None:
                raise FundusError("consumer template class attribute is unsafe")
            if name == "src":
                if tag != "img":
                    raise FundusError("consumer template src is only allowed on img")
                fixture_token = bool(value and _FIXTURE_TOKEN.fullmatch(value))
                if value != "{{ASSET_URL}}" and not fixture_token:
                    raise FundusError(
                        "consumer template src must use an asset or fixture token"
                    )
                if value == "{{ASSET_URL}}":
                    self.asset_sources += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_TAGS:
            raise FundusError(f"consumer template tag is forbidden: {tag}")


def _validate_template(template: str, fixtures: set[str]) -> None:
    if len(template.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise FundusError("consumer template exceeds the byte limit")
    if "{{ASSET_URL}}" not in template:
        raise FundusError("consumer template must reference {{ASSET_URL}}")
    parser = _FragmentValidator()
    try:
        parser.feed(template)
        parser.close()
    except FundusError:
        raise
    except (ValueError, AssertionError) as exc:
        raise FundusError("consumer template is invalid HTML") from exc
    if parser.asset_sources < 1:
        raise FundusError("consumer template must render {{ASSET_URL}} as an img source")
    tokens = set(_FIXTURE_TOKEN.findall(template))
    missing = sorted(tokens - fixtures)
    if missing:
        raise FundusError(
            "consumer template references unknown fixtures: " + ", ".join(missing)
        )
    leftover = re.findall(r"\{\{[^{}]+\}\}", template)
    allowed = {
        "{{ASSET_URL}}",
        "{{ASSET_ID}}",
        "{{BUILD_DIGEST}}",
        "{{OUTPUT_ROLE}}",
        "{{ACCEPTANCE_STATE}}",
        *{f"{{{{FIXTURE:{item}}}}}" for item in fixtures},
    }
    if set(leftover) - allowed:
        raise FundusError("consumer template contains unknown tokens")


def _checked_review_text(value: str, *, label: str, maximum: int, required: bool) -> str:
    if not isinstance(value, str):
        raise FundusError(f"{label} must be text")
    text = value.strip()
    if required and not text:
        raise FundusError(f"{label} must not be empty")
    if len(text) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise FundusError(f"{label} is invalid")
    return text


def _validate_css(css: str) -> None:
    if len(css.encode("utf-8")) > MAX_CSS_BYTES:
        raise FundusError("consumer CSS exceeds the byte limit")
    lowered = re.sub(r"\s+", "", css.lower())
    forbidden = (
        "url(",
        "@import",
        "@font-face",
        "expression(",
        "javascript:",
        "data:",
        "behavior:",
        "-moz-binding",
    )
    if any(marker in lowered for marker in forbidden):
        raise FundusError("consumer CSS contains external or executable content")


def _extension(media_type: str) -> str:
    extension = _OUTPUT_EXTENSIONS.get(media_type)
    if extension is None:
        raise FundusError(f"review bundle does not support media type: {media_type}")
    return extension


def _fixture_records(
    fixtures: Mapping[str, Path],
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    if len(fixtures) > MAX_REVIEW_FIXTURES:
        raise FundusError("review fixtures exceed the count limit")
    records: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for fixture_id, source in sorted(fixtures.items()):
        checked_id(fixture_id, label="fixture id")
        payload = read_regular_bytes(
            Path(source),
            maximum_bytes=MAX_FIXTURE_BYTES,
            label="review fixture",
        )
        try:
            info = inspect_media(payload)
        except ValueError as exc:
            raise FundusError(str(exc)) from exc
        if info.media_type not in _FIXTURE_MEDIA_TYPES:
            raise FundusError("review fixtures must be PNG, JPEG or WebP")
        filename = f"fixture-{fixture_id}{_extension(info.media_type)}"
        payloads[filename] = payload
        records.append(
            {
                "id": fixture_id,
                "file": f"fixtures/{filename}",
                "media_type": info.media_type,
                "sha256": digest_bytes(payload),
                "bytes": len(payload),
            }
        )
    return records, payloads


def _render_fragment(
    template: str,
    variant: ReviewVariant,
    asset_url: str,
    fixture_urls: Mapping[str, str],
) -> str:
    replacements = {
        "{{ASSET_URL}}": asset_url,
        "{{ASSET_ID}}": html.escape(variant.asset_id, quote=True),
        "{{BUILD_DIGEST}}": html.escape(variant.build_digest, quote=True),
        "{{OUTPUT_ROLE}}": html.escape(variant.output_role, quote=True),
        "{{ACCEPTANCE_STATE}}": html.escape(variant.acceptance_state, quote=True),
    }
    for fixture_id, url in fixture_urls.items():
        replacements[f"{{{{FIXTURE:{fixture_id}}}}}"] = url
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    if "{{" in rendered or "}}" in rendered:
        raise FundusError("consumer template token substitution is incomplete")
    return rendered


def _render_index(
    plan: ReviewPlan,
    *,
    title: str,
    description: str,
    template: str,
    asset_urls: Mapping[str, str],
    fixture_urls: Mapping[str, str],
) -> bytes:
    cards: list[str] = []
    for variant in plan.variants:
        fragment = _render_fragment(
            template,
            variant,
            asset_urls[variant.asset_id],
            fixture_urls,
        )
        cards.append(
            '<article class="card">'
            '<div class="card-head">'
            f'<strong>{html.escape(variant.asset_id)}</strong>'
            f'<div class="meta">Build {html.escape(variant.build_digest)} · '
            f'{html.escape(variant.output_role)} · '
            f'{html.escape(variant.acceptance_state)}</div>'
            "</div>"
            f'<div class="review-surface">{fragment}</div>'
            "</article>"
        )
    csp = (
        "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; "
        "connect-src 'none'; font-src 'none'; frame-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )
    document = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
        f"<title>{html.escape(title)}</title>"
        '<link rel="stylesheet" href="review.css">'
        '<script src="review.js" defer></script>'
        '</head><body data-bg="light"><header>'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(description)}</p>"
        '<div class="authority-note">REVIEW · keine Acceptance durch diese Seite</div>'
        '<div class="toolbar" aria-label="Review controls">'
        '<button type="button" data-bg-choice="light">Hell</button>'
        '<button type="button" data-bg-choice="dark">Dunkel</button>'
        '<button type="button" data-bg-choice="warm">Warm</button>'
        '<button type="button" data-bg-choice="checker">Transparenz</button>'
        '<button type="button" data-cols="1">1 Spalte</button>'
        '<button type="button" data-cols="2">2 Spalten</button>'
        '<button type="button" data-cols="3">3 Spalten</button>'
        "</div></header><main>"
        '<section class="grid" aria-label="Fundus variants">'
        + "".join(cards)
        + "</section></main></body></html>\n"
    )
    return document.encode("utf-8")


def _publish_directory_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise FundusError("atomic no-replace review publication is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FundusError("review output appeared during build")
    if error_number in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
        raise FundusError("atomic no-replace review publication is unavailable")
    raise OSError(error_number, os.strerror(error_number), destination)


def _schema(name: str) -> dict[str, Any]:
    try:
        text = (
            resources.files("schauwerk.schemas")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )
        return json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FundusError("Fundus review schema is unavailable") from exc


def _validate_schema(value: dict[str, Any], name: str, label: str) -> None:
    errors = sorted(
        Draft202012Validator(_schema(name)).iter_errors(value),
        key=lambda item: list(item.path),
    )
    if errors:
        raise FundusError(f"Fundus {label} violates its schema")


def _validate_bundle_schema(value: dict[str, Any]) -> None:
    _validate_schema(value, REVIEW_BUNDLE_SCHEMA_FILE, "review bundle")


def _file_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    paths = [
        item
        for item in root.rglob("*")
        if item.is_file() and item.name != "review.json"
    ]
    if len(paths) > MAX_REVIEW_FILES:
        raise FundusError("review bundle exceeds the file count limit")
    total_bytes = 0
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        total_bytes += len(payload)
        if total_bytes > MAX_REVIEW_TOTAL_BYTES:
            raise FundusError("review bundle exceeds the total byte limit")
        records.append(
            {
                "path": relative,
                "sha256": digest_bytes(payload),
                "bytes": len(payload),
            }
        )
    return records


def build_review_bundle(
    fundus: Fundus,
    family_id: str,
    output_dir: Path,
    *,
    title: str | None = None,
    description: str = (
        "Digestgebundener Fundus-Vergleich. Diese Seite erzeugt keine visuelle Freigabe."
    ),
    consumer_template: Path | None = None,
    consumer_css: Path | None = None,
    fixtures: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Create one portable, atomic, network-free review bundle."""

    plan = build_review_plan(fundus, family_id)
    title_text = _checked_review_text(
        title or plan.family_title,
        label="review title",
        maximum=240,
        required=True,
    )
    description_text = _checked_review_text(
        description,
        label="review description",
        maximum=1000,
        required=False,
    )

    fixture_records, fixture_payloads = _fixture_records(fixtures or {})
    fixture_ids = {item["id"] for item in fixture_records}
    if consumer_template is None:
        template = _DEFAULT_TEMPLATE
        template_mode = "default"
    else:
        template = read_regular_bytes(
            Path(consumer_template),
            maximum_bytes=MAX_TEMPLATE_BYTES,
            label="consumer template",
        ).decode("utf-8")
        template_mode = "custom"
    _validate_template(template, fixture_ids)
    template_sha256 = digest_bytes(template.encode("utf-8"))

    custom_css = ""
    if consumer_css is not None:
        custom_css = read_regular_bytes(
            Path(consumer_css),
            maximum_bytes=MAX_CSS_BYTES,
            label="consumer CSS",
        ).decode("utf-8")
        _validate_css(custom_css)
    consumer_css_sha256 = digest_bytes(custom_css.encode("utf-8"))

    destination = Path(output_dir).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FundusError("review output directory already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise FundusError("review output parent is unsafe")

    temporary: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        os.chmod(temporary, 0o755)
        (temporary / "assets").mkdir(mode=0o755)
        if fixture_payloads:
            (temporary / "fixtures").mkdir(mode=0o755)

        asset_urls: dict[str, str] = {}
        variant_records: list[dict[str, Any]] = []
        for variant in plan.variants:
            build, build_dir = fundus._load_build(
                variant.asset_id, variant.build_digest
            )
            matching_outputs = [
                output
                for output in build["outputs"]
                if output["role"] == variant.output_role
                and output["filename"] == variant.output_filename
            ]
            if len(matching_outputs) != 1:
                raise FundusError("Fundus review variant output binding disappeared")
            payload = fundus._read_build_output(build_dir, matching_outputs[0])
            if (
                len(payload) != variant.output_bytes
                or digest_bytes(payload) != variant.output_sha256
                or inspect_media(payload).media_type != variant.output_media_type
            ):
                raise FundusError(
                    "Fundus build output drifted before review bundle creation"
                )
            filename = f"{variant.asset_id}{_extension(variant.output_media_type)}"
            relative = f"assets/{filename}"
            path = temporary / relative
            path.write_bytes(payload)
            os.chmod(path, 0o644)
            asset_urls[variant.asset_id] = relative
            variant_records.append({**variant.to_dict(), "file": relative})

        fixture_urls: dict[str, str] = {}
        for record in fixture_records:
            name = Path(record["file"]).name
            path = temporary / record["file"]
            path.write_bytes(fixture_payloads[name])
            os.chmod(path, 0o644)
            fixture_urls[record["id"]] = record["file"]

        css = _BASE_CSS
        if custom_css.strip():
            css += "\n\n/* consumer */\n" + custom_css.strip()
        css += "\n"
        (temporary / "review.css").write_text(css, encoding="utf-8")
        (temporary / "review.js").write_text(_BASE_JS + "\n", encoding="utf-8")
        (temporary / "index.html").write_bytes(
            _render_index(
                plan,
                title=title_text,
                description=description_text,
                template=template,
                asset_urls=asset_urls,
                fixture_urls=fixture_urls,
            )
        )
        for name in ("review.css", "review.js", "index.html"):
            os.chmod(temporary / name, 0o644)

        files = _file_records(temporary)
        body = {
            "schema_version": REVIEW_BUNDLE_SCHEMA,
            "family_id": plan.family_id,
            "family_title": plan.family_title,
            "title": title_text,
            "description": description_text,
            "plan_digest": plan.plan_digest,
            "variant_count": len(variant_records),
            "variants": variant_records,
            "fixtures": fixture_records,
            "consumer_template_mode": template_mode,
            "consumer_template_sha256": template_sha256,
            "consumer_css_sha256": consumer_css_sha256,
            "entrypoint": "index.html",
            "files": files,
            "network_dependencies": False,
            "portable": True,
            "fundus_authoritative": True,
            "visual_acceptance_inferred": False,
            "package_created": False,
        }
        manifest = {**body, "review_digest": digest_json(body)}
        _validate_bundle_schema(manifest)
        (temporary / "review.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary / "review.json", 0o644)
        _publish_directory_noreplace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    checked = check_review_bundle(destination)
    return {**checked, "review_path": str(destination / "index.html")}


def check_review_bundle(directory: Path) -> dict[str, Any]:
    """Verify exact file set, digests and hard authority nonclaims."""

    root = Path(directory).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise FundusError("review bundle directory is missing or unsafe")
    root_stat = root.lstat()
    if root_stat.st_uid != os.geteuid() or root_stat.st_nlink < 1 or root_stat.st_mode & 0o022:
        raise FundusError("review bundle directory ownership or permissions are unsafe")
    try:
        manifest = load_json(root / "review.json", maximum_bytes=1_000_000)
    except (OSError, ValueError) as exc:
        raise FundusError(str(exc)) from exc
    _validate_bundle_schema(manifest)

    body = dict(manifest)
    declared_digest = body.pop("review_digest")
    if digest_json(body) != declared_digest:
        raise FundusError("review bundle manifest digest mismatch")

    variants = manifest["variants"]
    fixtures = manifest["fixtures"]
    file_records = manifest["files"]
    if len(variants) > MAX_REVIEW_VARIANTS:
        raise FundusError("review bundle exceeds the variant limit")
    if len(fixtures) > MAX_REVIEW_FIXTURES:
        raise FundusError("review bundle exceeds the fixture limit")
    if len(file_records) > MAX_REVIEW_FILES:
        raise FundusError("review bundle exceeds the file count limit")
    if sum(item["bytes"] for item in file_records) > MAX_REVIEW_TOTAL_BYTES:
        raise FundusError("review bundle exceeds the total byte limit")
    if manifest["variant_count"] != len(variants):
        raise FundusError("review bundle variant count mismatch")
    file_paths = [item["path"] for item in file_records]
    if len(file_paths) != len(set(file_paths)):
        raise FundusError("review bundle file paths are not unique")
    file_by_path = {item["path"]: item for item in file_records}
    if not {"index.html", "review.css", "review.js"}.issubset(file_by_path):
        raise FundusError("review bundle core files are incomplete")

    asset_ids = [item["asset_id"] for item in variants]
    variant_files = [item["file"] for item in variants]
    if len(asset_ids) != len(set(asset_ids)) or len(variant_files) != len(set(variant_files)):
        raise FundusError("review bundle variant bindings are not unique")
    for variant in variants:
        record = file_by_path.get(variant["file"])
        if (
            record is None
            or record["sha256"] != variant["output_sha256"]
            or (
                "output_bytes" in variant
                and record["bytes"] != variant["output_bytes"]
            )
        ):
            raise FundusError("review bundle variant output binding mismatch")

    fixture_ids = [item["id"] for item in fixtures]
    fixture_files = [item["file"] for item in fixtures]
    if len(fixture_ids) != len(set(fixture_ids)) or len(fixture_files) != len(set(fixture_files)):
        raise FundusError("review bundle fixture bindings are not unique")
    for fixture in fixtures:
        record = file_by_path.get(fixture["file"])
        if record is None or record["sha256"] != fixture["sha256"]:
            raise FundusError("review bundle fixture binding mismatch")

    plan_variants = [
        {key: value for key, value in variant.items() if key != "file"}
        for variant in variants
    ]
    plan_body = {
        "schema_version": REVIEW_PLAN_SCHEMA,
        "family_id": manifest["family_id"],
        "family_title": manifest["family_title"],
        "variants": plan_variants,
        "fundus_authoritative": True,
        "visual_acceptance_inferred": False,
        "package_created": False,
    }
    if digest_json(plan_body) != manifest["plan_digest"]:
        raise FundusError("review bundle plan binding mismatch")

    expected = {"review.json", *file_paths}
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_dir():
            if path.is_symlink():
                raise FundusError("review bundle contains a symlink directory")
            directory_stat = path.lstat()
            if (
                directory_stat.st_uid != os.geteuid()
                or directory_stat.st_nlink < 1
                or directory_stat.st_mode & 0o022
            ):
                raise FundusError("review bundle contains an unsafe directory")
            continue
        relative = path.relative_to(root).as_posix()
        actual.add(relative)
        stat = path.lstat()
        if path.is_symlink() or stat.st_nlink != 1 or stat.st_mode & 0o022:
            raise FundusError(f"review bundle file is unsafe: {relative}")
    if actual != expected:
        raise FundusError("review bundle file set mismatch")

    for item in manifest["files"]:
        payload = read_regular_bytes(
            root / item["path"],
            maximum_bytes=MAX_BUNDLE_FILE_BYTES,
            label=f"review bundle file {item['path']}",
            require_owner=True,
            forbidden_mode_bits=0o022,
        )
        if len(payload) != item["bytes"] or digest_bytes(payload) != item["sha256"]:
            raise FundusError(f"review bundle file drifted: {item['path']}")
    for variant in variants:
        payload = read_regular_bytes(
            root / variant["file"],
            maximum_bytes=MAX_BUNDLE_FILE_BYTES,
            label=f"review variant {variant['asset_id']}",
            require_owner=True,
            forbidden_mode_bits=0o022,
        )
        try:
            media_type = inspect_media(payload).media_type
        except ValueError as exc:
            raise FundusError("review bundle variant media is invalid") from exc
        if media_type != variant["output_media_type"]:
            raise FundusError("review bundle variant media_type drifted")
    return {**manifest, "ok": True}
