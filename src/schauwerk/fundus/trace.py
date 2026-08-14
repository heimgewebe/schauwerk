"""Optional evidence-selected raster-to-vector tracing for Fundus."""

from __future__ import annotations

import importlib.metadata
import math
import xml.etree.ElementTree as ET
from io import BytesIO

from PIL import Image

from .errors import FundusError
from .media import inspect_media
from .raster import RASTER_PROFILE, normalize_raster
from .svg import MAX_SVG_BYTES, sanitize_svg

TRACE_PROFILE = "trace.vtracer.color.v1"
TRACE_MASK_PROFILE = "trace.vtracer.alpha-mask.v1"
TRACE_PROFILES = (TRACE_PROFILE, TRACE_MASK_PROFILE)
ALPHA_MASK_THRESHOLD = 8
VTRACER_VERSION = "0.6.15"
MAX_TRACE_DIMENSION = 4096
MAX_TRACE_PIXELS = 8_000_000
MAX_RAW_TRACE_BYTES = MAX_SVG_BYTES
SUPPORTED_TRACE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}

_VTRACER_COLOR_SETTINGS = {
    "colormode": "color",
    "hierarchical": "stacked",
    "mode": "spline",
    "filter_speckle": 4,
    "color_precision": 6,
    "layer_difference": 16,
    "corner_threshold": 60,
    "length_threshold": 4.0,
    "max_iterations": 10,
    "splice_threshold": 45,
    "path_precision": 3,
}

_VTRACER_MASK_SETTINGS = {
    **_VTRACER_COLOR_SETTINGS,
    "colormode": "binary",
}


def trace_profile_contract(profile: str) -> dict[str, object]:
    """Return a copy of the deterministic adapter contract for evidence tooling."""
    if profile == TRACE_PROFILE:
        settings = _VTRACER_COLOR_SETTINGS
        sanitizer_profile = "svg.decorative.v1"
        source_channel = "color"
    elif profile == TRACE_MASK_PROFILE:
        settings = _VTRACER_MASK_SETTINGS
        sanitizer_profile = "svg.mask.v1"
        source_channel = "alpha"
    else:
        raise FundusError(f"unknown trace profile: {profile}")
    contract: dict[str, object] = {
        "profile": profile,
        "adapter": "vtracer",
        "required_version": VTRACER_VERSION,
        "settings": dict(settings),
        "sanitizer_profile": sanitizer_profile,
        "trace_source_channel": source_channel,
    }
    if profile == TRACE_MASK_PROFILE:
        contract["alpha_threshold"] = ALPHA_MASK_THRESHOLD
    return contract


def trace_adapter_status() -> dict[str, object]:
    try:
        version = importlib.metadata.version("vtracer")
    except importlib.metadata.PackageNotFoundError:
        return {
            "available": False,
            "implementation": "vtracer",
            "required_version": VTRACER_VERSION,
            "profile": TRACE_PROFILE,
            "profiles": list(TRACE_PROFILES),
        }
    return {
        "available": version == VTRACER_VERSION,
        "implementation": "vtracer",
        "version": version,
        "required_version": VTRACER_VERSION,
        "profile": TRACE_PROFILE,
        "profiles": list(TRACE_PROFILES),
    }


def _positive_dimension(value: str, *, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise FundusError(f"VTracer {label} is not numeric") from exc
    if not math.isfinite(number) or number <= 0 or number > MAX_TRACE_DIMENSION:
        raise FundusError(f"VTracer {label} is outside the Fundus trace limit")
    return number


def normalize_vtracer_svg(
    payload: bytes,
    *,
    expected_width: int,
    expected_height: int,
) -> bytes:
    """Normalize VTracer SVG dimensions before the Fundus sanitizer boundary."""
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FundusError("VTracer output contained forbidden XML declarations")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FundusError("VTracer output is not well-formed SVG") from exc
    local = root.tag.rsplit("}", 1)[-1] if isinstance(root.tag, str) else ""
    if local != "svg":
        raise FundusError("VTracer output root is not SVG")

    width_text = root.attrib.get("width")
    height_text = root.attrib.get("height")
    if width_text is None or height_text is None:
        raise FundusError("VTracer output is missing dimensions")
    width = _positive_dimension(width_text, label="width")
    height = _positive_dimension(height_text, label="height")
    if int(round(width)) != expected_width or int(round(height)) != expected_height:
        raise FundusError("VTracer output dimensions do not match the source")

    root.attrib.pop("version", None)
    root.attrib["viewBox"] = f"0 0 {width:g} {height:g}"
    return ET.tostring(root, encoding="utf-8")


def trace_raster(payload: bytes, *, profile: str) -> tuple[bytes, dict[str, object]]:
    """Trace normalized raster bytes with VTracer, then sanitize the SVG."""
    contract = trace_profile_contract(profile)

    media = inspect_media(payload)
    if media.media_type not in SUPPORTED_TRACE_MEDIA_TYPES:
        raise FundusError("VTracer requires PNG, JPEG or WebP input")
    if media.width is None or media.height is None:
        raise FundusError("trace source dimensions are required")
    if media.width > MAX_TRACE_DIMENSION or media.height > MAX_TRACE_DIMENSION:
        raise FundusError("trace source dimensions exceed the Fundus trace limit")
    if media.width * media.height > MAX_TRACE_PIXELS:
        raise FundusError("trace source pixel count exceeds the Fundus trace limit")

    try:
        version = importlib.metadata.version("vtracer")
    except importlib.metadata.PackageNotFoundError as exc:
        raise FundusError(
            "VTracer adapter is unavailable; install the optional 'schauwerk[trace]' extra"
        ) from exc
    if version != VTRACER_VERSION:
        raise FundusError(
            f"VTracer adapter requires version {VTRACER_VERSION}, found {version}"
        )

    try:
        import vtracer
    except ImportError as exc:
        raise FundusError(
            "VTracer package metadata exists but the module cannot be imported"
        ) from exc

    normalized_raster, raster_toolchain = normalize_raster(
        payload,
        profile=RASTER_PROFILE,
    )
    normalized_media = inspect_media(normalized_raster)
    if normalized_media.width != media.width or normalized_media.height != media.height:
        raise FundusError("trace raster normalization changed source dimensions")

    trace_input = normalized_raster
    settings = dict(contract["settings"])
    sanitizer_profile = str(contract["sanitizer_profile"])
    profile_toolchain: dict[str, object] = {}
    if profile == TRACE_MASK_PROFILE:
        if media.has_alpha is not True:
            raise FundusError("alpha-mask tracing requires an alpha channel")
        with Image.open(BytesIO(normalized_raster)) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            minimum, maximum = alpha.getextrema()
            if maximum < ALPHA_MASK_THRESHOLD or minimum >= ALPHA_MASK_THRESHOLD:
                raise FundusError(
                    "alpha-mask trace source has no usable foreground/background split"
                )
            binary = alpha.point(
                lambda value: 0 if value >= ALPHA_MASK_THRESHOLD else 255
            )
            rgb = Image.merge("RGB", (binary, binary, binary))
            output = BytesIO()
            rgb.save(output, format="PNG", optimize=False, compress_level=9)
            trace_input = output.getvalue()
        profile_toolchain = {
            "trace_source_channel": "alpha",
            "alpha_threshold": ALPHA_MASK_THRESHOLD,
        }

    try:
        raw_svg = vtracer.convert_raw_image_to_svg(
            trace_input,
            img_format="png",
            **settings,
        )
    except Exception as exc:  # native extension failures are normalized at this seam
        raise FundusError("VTracer failed to trace the raster source") from exc
    if not isinstance(raw_svg, str):
        raise FundusError("VTracer returned a non-text SVG result")
    raw_bytes = raw_svg.encode("utf-8")
    if len(raw_bytes) > MAX_RAW_TRACE_BYTES:
        raise FundusError("VTracer output exceeds the Fundus raw trace limit")

    normalized = normalize_vtracer_svg(
        raw_bytes,
        expected_width=media.width,
        expected_height=media.height,
    )
    sanitized = sanitize_svg(normalized, profile=sanitizer_profile)
    return sanitized, {
        "adapter": "vtracer",
        "vtracer": version,
        "trace_input_adapter": raster_toolchain["adapter"],
        "pillow": raster_toolchain["pillow"],
        "trace_profile": profile,
        "sanitizer_profile": sanitizer_profile,
        "path_precision": settings["path_precision"],
        **profile_toolchain,
    }
