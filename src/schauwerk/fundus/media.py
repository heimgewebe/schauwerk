"""Dependency-free media inspection at the Fundus trust boundary."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass

MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_DIMENSION = 100_000
PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
JPEG_START = bytes.fromhex("ffd8")
JPEG_END = bytes.fromhex("ffd9")
VP8_SIGNATURE = bytes.fromhex("9d012a")


@dataclass(frozen=True)
class MediaInfo:
    media_type: str
    width: int | None
    height: int | None
    has_alpha: bool | None

    def to_dict(self) -> dict[str, object]:
        return {
            "media_type": self.media_type,
            "width": self.width,
            "height": self.height,
            "has_alpha": self.has_alpha,
        }


def _checked_dimensions(
    width: int | None,
    height: int | None,
) -> tuple[int | None, int | None]:
    if width is None or height is None:
        return width, height
    if not 1 <= width <= MAX_DIMENSION:
        raise ValueError("image width is outside the Fundus limit")
    if not 1 <= height <= MAX_DIMENSION:
        raise ValueError("image height is outside the Fundus limit")
    return width, height


def _svg_info(payload: bytes) -> MediaInfo:
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("SVG declarations with entities or doctypes are forbidden")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("SVG is not well-formed XML") from exc
    local = root.tag.rsplit("}", 1)[-1] if isinstance(root.tag, str) else ""
    if local != "svg":
        raise ValueError("XML input is not an SVG document")
    width = height = None
    view_box = root.attrib.get("viewBox")
    if view_box:
        try:
            numbers = [
                float(item)
                for item in view_box.replace(",", " ").split()
            ]
        except ValueError as exc:
            raise ValueError("SVG viewBox is invalid") from exc
        if len(numbers) != 4:
            raise ValueError("SVG viewBox must have four numbers")
        width = int(round(numbers[2]))
        height = int(round(numbers[3]))
        _checked_dimensions(width, height)
    return MediaInfo("image/svg+xml", width, height, True)


def _png_info(payload: bytes) -> MediaInfo:
    if len(payload) < 33:
        raise ValueError("PNG header is truncated")
    if payload[:8] != PNG_SIGNATURE or payload[12:16] != b"IHDR":
        raise ValueError("PNG header is invalid")
    width, height = struct.unpack(">II", payload[16:24])
    _checked_dimensions(width, height)
    if b"IEND" not in payload[-64:]:
        raise ValueError("PNG is truncated")
    color_type = payload[25]
    has_alpha = color_type in {4, 6} or b"tRNS" in payload
    return MediaInfo("image/png", width, height, has_alpha)


def _jpeg_info(payload: bytes) -> MediaInfo:
    if len(payload) < 4:
        raise ValueError("JPEG framing is truncated")
    if payload[:2] != JPEG_START or payload[-2:] != JPEG_END:
        raise ValueError("JPEG framing is invalid")
    offset = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset + 4 <= len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        marker = payload[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(payload):
            break
        length = int.from_bytes(payload[offset : offset + 2], "big")
        if length < 2 or offset + length > len(payload):
            raise ValueError("JPEG segment is truncated")
        if marker in sof_markers:
            if length < 7:
                raise ValueError("JPEG size segment is invalid")
            height = int.from_bytes(
                payload[offset + 3 : offset + 5],
                "big",
            )
            width = int.from_bytes(
                payload[offset + 5 : offset + 7],
                "big",
            )
            _checked_dimensions(width, height)
            return MediaInfo("image/jpeg", width, height, False)
        offset += length
    raise ValueError("JPEG dimensions were not found")


def _webp_info(payload: bytes) -> MediaInfo:
    if len(payload) < 20:
        raise ValueError("WebP framing is truncated")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        raise ValueError("WebP framing is invalid")
    declared = int.from_bytes(payload[4:8], "little") + 8
    if declared > len(payload):
        raise ValueError("WebP is truncated")
    chunk = payload[12:16]
    data = payload[20:]
    if chunk == b"VP8X" and len(data) >= 10:
        width = 1 + int.from_bytes(data[4:7], "little")
        height = 1 + int.from_bytes(data[7:10], "little")
        _checked_dimensions(width, height)
        return MediaInfo(
            "image/webp",
            width,
            height,
            bool(data[0] & 0x10),
        )
    if chunk == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
        b0, b1, b2, b3 = data[1:5]
        width = 1 + b0 + ((b1 & 0x3F) << 8)
        height = (
            1
            + ((b1 & 0xC0) >> 6)
            + (b2 << 2)
            + ((b3 & 0x0F) << 10)
        )
        _checked_dimensions(width, height)
        return MediaInfo("image/webp", width, height, None)
    if (
        chunk == b"VP8 "
        and len(data) >= 10
        and data[3:6] == VP8_SIGNATURE
    ):
        width = int.from_bytes(data[6:8], "little") & 0x3FFF
        height = int.from_bytes(data[8:10], "little") & 0x3FFF
        _checked_dimensions(width, height)
        return MediaInfo("image/webp", width, height, False)
    raise ValueError("unsupported or invalid WebP payload")


def inspect_media(payload: bytes) -> MediaInfo:
    if not payload or len(payload) > MAX_SOURCE_BYTES:
        raise ValueError(
            "source media is empty or exceeds the Fundus size limit"
        )
    stripped = payload.lstrip()
    if stripped.startswith(b"<"):
        return _svg_info(payload)
    if payload.startswith(PNG_SIGNATURE):
        return _png_info(payload)
    if payload.startswith(JPEG_START):
        return _jpeg_info(payload)
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return _webp_info(payload)
    raise ValueError("unsupported Fundus source media type")
