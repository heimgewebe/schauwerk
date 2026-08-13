"""Deterministic raster normalization for Fundus."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError
from PIL import __version__ as PILLOW_RUNTIME_VERSION

from .errors import FundusError
from .media import inspect_media

RASTER_PROFILE = "raster.png.rgba.v1"
PILLOW_REQUIRED_VERSION = "12.2.0"
MAX_RASTER_PIXELS = 16_000_000
MAX_RASTER_OUTPUT_BYTES = 16 * 1024 * 1024
SUPPORTED_RASTER_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}


def raster_adapter_status() -> dict[str, object]:
    return {
        "available": PILLOW_RUNTIME_VERSION == PILLOW_REQUIRED_VERSION,
        "implementation": "pillow",
        "version": PILLOW_RUNTIME_VERSION,
        "required_version": PILLOW_REQUIRED_VERSION,
        "profile": RASTER_PROFILE,
    }


def _require_pillow_version() -> None:
    if PILLOW_RUNTIME_VERSION != PILLOW_REQUIRED_VERSION:
        raise FundusError(
            "Pillow adapter requires version "
            f"{PILLOW_REQUIRED_VERSION}, found {PILLOW_RUNTIME_VERSION}"
        )


def normalize_raster(payload: bytes, *, profile: str) -> tuple[bytes, dict[str, object]]:
    """Normalize one raster source to deterministic metadata-free RGBA PNG."""
    if profile != RASTER_PROFILE:
        raise FundusError(f"unknown raster profile: {profile}")
    _require_pillow_version()

    media = inspect_media(payload)
    if media.media_type not in SUPPORTED_RASTER_MEDIA_TYPES:
        raise FundusError("raster normalization requires PNG, JPEG or WebP input")
    if media.width is None or media.height is None:
        raise FundusError("raster dimensions are required")
    if media.width * media.height > MAX_RASTER_PIXELS:
        raise FundusError("raster pixel count exceeds the Fundus normalization limit")

    try:
        with Image.open(BytesIO(payload)) as image:
            if image.width != media.width or image.height != media.height:
                raise FundusError("decoded raster dimensions do not match inspected dimensions")
            if image.width * image.height > MAX_RASTER_PIXELS:
                raise FundusError("decoded raster exceeds the Fundus normalization limit")
            if getattr(image, "n_frames", 1) != 1:
                raise FundusError("animated or multi-frame raster sources are unsupported")
            orientation = image.getexif().get(274, 1)
            if orientation not in {None, 1}:
                raise FundusError(
                    "raster EXIF orientation must be normalized before Fundus ingest"
                )
            image.load()
            normalized = image.convert("RGBA")
            output = BytesIO()
            normalized.save(
                output,
                format="PNG",
                compress_level=9,
                optimize=False,
            )
    except FundusError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise FundusError("raster decoder rejected the source media") from exc

    output_bytes = output.getvalue()
    if len(output_bytes) > MAX_RASTER_OUTPUT_BYTES:
        raise FundusError("normalized raster exceeds the Fundus output size limit")
    detected = inspect_media(output_bytes)
    if detected.media_type != "image/png":
        raise FundusError("raster normalization did not produce PNG")
    if detected.width != media.width or detected.height != media.height:
        raise FundusError("raster normalization changed dimensions")

    return output_bytes, {
        "adapter": "pillow",
        "pillow": PILLOW_RUNTIME_VERSION,
        "raster_profile": profile,
    }
