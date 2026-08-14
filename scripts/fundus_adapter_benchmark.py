#!/usr/bin/env python3
"""Reproducible local benchmark for Fundus raster and trace adapter decisions."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import subprocess
import tempfile
import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin, features

from schauwerk.fundus.raster import normalize_raster
from schauwerk.fundus.svg import sanitize_svg
from schauwerk.fundus.trace import (
    TRACE_PROFILE,
    normalize_vtracer_svg,
    trace_adapter_status,
    trace_profile_contract,
)

ITERATIONS = 8
TRACE_QUALITY_DELTA_LIMIT = 0.01


def _gradient_alpha_fixture() -> Image.Image:
    image = Image.new("RGBA", (320, 240), (244, 239, 226, 255))
    draw = ImageDraw.Draw(image)
    for x in range(image.width):
        draw.line(
            (x, 0, x, image.height - 1),
            fill=(20 + (x * 180 // (image.width - 1)), 30, 50, 255),
        )
    draw.ellipse(
        (45, 35, 205, 195),
        fill=(196, 153, 65, 210),
        outline=(25, 20, 18, 255),
        width=5,
    )
    draw.polygon(
        [(245, 25), (305, 120), (245, 215), (205, 120)],
        fill=(30, 80, 110, 180),
    )
    return image


def _fine_line_alpha_fixture() -> Image.Image:
    image = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index in range(9):
        y = 16 + index * 24
        draw.arc(
            (18, y - 10, 302, y + 46),
            start=188,
            end=352,
            fill=(198, 157, 71, 115 + index * 14),
            width=1 + index % 3,
        )
    for x in range(24, 297, 34):
        draw.line((x, 14, 319 - x, 225), fill=(24, 24, 28, 180), width=1)
    draw.rounded_rectangle(
        (70, 57, 250, 183),
        radius=28,
        outline=(215, 175, 82, 230),
        width=2,
    )
    return image


def _deterministic_texture_fixture() -> Image.Image:
    width, height = 320, 240
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            grain = (x * 17 + y * 29 + (x * y) % 97) % 256
            pixels.extend(
                (
                    48 + grain * 3 // 5,
                    34 + grain * 2 // 5,
                    20 + grain // 4,
                )
            )
    image = Image.frombytes("RGB", (width, height), bytes(pixels))
    draw = ImageDraw.Draw(image)
    for inset in range(18, 100, 16):
        draw.rectangle(
            (inset, inset // 2, width - inset, height - inset // 2),
            outline=(210, 174, 87),
            width=1,
        )
    return image


def _raster_fixture_images() -> dict[str, Image.Image]:
    return {
        "gradient_alpha": _gradient_alpha_fixture(),
        "fine_line_alpha": _fine_line_alpha_fixture(),
        "deterministic_texture": _deterministic_texture_fixture(),
    }


def _trace_flat_shapes_fixture() -> Image.Image:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((25, 25, 155, 155), fill=(201, 154, 64), outline=(20, 20, 20), width=4)
    draw.polygon([(175, 30), (235, 128), (175, 226), (140, 128)], fill=(40, 80, 110))
    draw.rectangle((35, 180, 120, 220), fill=(30, 30, 30))
    return image


def _trace_fine_lines_fixture() -> Image.Image:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    for index in range(12):
        inset = 12 + index * 6
        draw.arc(
            (inset, 18 + index * 4, 256 - inset, 230 - index * 3),
            start=198,
            end=342,
            fill=(30 + index * 9, 28, 25),
            width=1 + index % 2,
        )
    for offset in range(18, 239, 22):
        draw.line((18, offset, 238, 256 - offset), fill=(195, 151, 62), width=1)
    draw.ellipse((84, 84, 172, 172), outline=(24, 24, 24), width=2)
    return image


def _trace_nested_contours_fixture() -> Image.Image:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    palette = [
        (24, 24, 26),
        (201, 158, 70),
        (54, 76, 91),
        (238, 231, 213),
    ]
    for index, inset in enumerate((18, 35, 53, 72, 92)):
        draw.rounded_rectangle(
            (inset, inset, 256 - inset, 256 - inset),
            radius=18 + index * 3,
            outline=palette[index % len(palette)],
            width=3,
        )
    draw.polygon(
        [(128, 32), (220, 128), (128, 224), (36, 128)],
        outline=(33, 33, 36),
        fill=(231, 218, 188),
    )
    draw.ellipse((94, 94, 162, 162), fill=(201, 158, 70), outline=(20, 20, 20), width=3)
    return image


def _trace_fixture_images() -> dict[str, Image.Image]:
    return {
        "flat_shapes": _trace_flat_shapes_fixture(),
        "fine_lines": _trace_fine_lines_fixture(),
        "nested_contours": _trace_nested_contours_fixture(),
    }


def _canonical_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "PNG", compress_level=6)
    return output.getvalue()


def _fixture_manifest(images: dict[str, Image.Image]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, image in images.items():
        payload = _canonical_png(image)
        result[name] = {
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "canonical_png_sha256": hashlib.sha256(payload).hexdigest(),
        }
    return result


def fixture_corpus_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "raster": _fixture_manifest(_raster_fixture_images()),
        "trace": _fixture_manifest(_trace_fixture_images()),
    }


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (244, 239, 226))
    background.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
    return background


def _raster_fixtures() -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for semantic_name, image in _raster_fixture_images().items():
        info = PngImagePlugin.PngInfo()
        info.add_text("fundus-benchmark", "remove-me")
        output = BytesIO()
        image.save(output, "PNG", pnginfo=info, compress_level=6)
        result[f"{semantic_name}.png"] = output.getvalue()

        output = BytesIO()
        _flatten_for_jpeg(image).save(output, "JPEG", quality=91, subsampling=0)
        result[f"{semantic_name}.jpeg"] = output.getvalue()

        if features.check("webp"):
            output = BytesIO()
            image.save(output, "WEBP", lossless=True, quality=100)
            result[f"{semantic_name}.webp"] = output.getvalue()
    return result


def _trace_fixtures() -> dict[str, bytes]:
    return {name: _canonical_png(image) for name, image in _trace_fixture_images().items()}


def _decoded_rgba(payload: bytes) -> Image.Image:
    return Image.open(BytesIO(payload)).convert("RGBA")


def _pixel_metrics(reference: Image.Image, candidate: Image.Image) -> dict[str, float | int]:
    left = reference.convert("RGBA")
    right = candidate.convert("RGBA")
    if left.size != right.size:
        raise RuntimeError("benchmark candidate changed dimensions")
    differences = [abs(a - b) for a, b in zip(left.tobytes(), right.tobytes(), strict=True)]
    return {
        "max_channel_error": max(differences),
        "mean_channel_error": round(sum(differences) / len(differences), 6),
    }


def _imagemagick_normalize(convert: str, payload: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="schauwerk-fundus-bench-") as directory:
        root = Path(directory)
        source = root / "source"
        output = root / "output.png"
        source.write_bytes(payload)
        completed = subprocess.run(
            [convert, str(source), "-strip", f"png:{output}"],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        return output.read_bytes()


def _timed(callable_) -> tuple[bytes, list[float]]:
    outputs: list[bytes] = []
    timings: list[float] = []
    for _ in range(ITERATIONS):
        started = time.perf_counter_ns()
        output = callable_()
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
        outputs.append(output)
    if len({hashlib.sha256(item).hexdigest() for item in outputs}) != 1:
        raise RuntimeError("benchmark candidate is non-deterministic")
    return outputs[0], timings


def benchmark_raster() -> dict[str, object]:
    fixtures = _raster_fixtures()
    candidates: dict[str, object] = {}
    for name in ("pillow", "imagemagick6"):
        convert = shutil.which("convert") if name == "imagemagick6" else None
        if name == "imagemagick6" and convert is None:
            candidates[name] = {"available": False}
            continue
        fixture_results: dict[str, dict[str, object]] = {}
        all_timings: list[float] = []
        for fixture_name, payload in fixtures.items():
            reference = _decoded_rgba(payload)
            if name == "pillow":
                output, timings = _timed(
                    lambda payload=payload: normalize_raster(
                        payload,
                        profile="raster.png.rgba.v1",
                    )[0]
                )
            else:
                assert convert is not None
                output, timings = _timed(
                    lambda payload=payload: _imagemagick_normalize(convert, payload)
                )
            all_timings.extend(timings)
            metrics = _pixel_metrics(reference, _decoded_rgba(output))
            fixture_results[fixture_name] = {
                "bytes": len(output),
                "deterministic": True,
                "median_ms": round(statistics.median(timings), 3),
                "metadata_removed": b"remove-me" not in output,
                **metrics,
            }
        candidates[name] = {
            "available": True,
            "fixtures": fixture_results,
            "median_ms": round(statistics.median(all_timings), 3),
            "total_output_bytes": sum(
                int(value["bytes"]) for value in fixture_results.values()
            ),
            "pixel_exact": all(
                value["max_channel_error"] == 0 for value in fixture_results.values()
            ),
        }

    pillow = candidates["pillow"]
    imagemagick = candidates["imagemagick6"]
    selected: str | None = "pillow"
    if not pillow["pixel_exact"]:
        selected = None
    if imagemagick.get("available") and not imagemagick["pixel_exact"]:
        selected = None
    return {
        "semantic_fixtures": list(_raster_fixture_images()),
        "encoded_fixtures": list(fixtures),
        "candidates": candidates,
        "selected": selected,
    }


def _trace_candidate(payload: bytes, *, path_precision: int) -> bytes:
    import vtracer

    contract = trace_profile_contract(TRACE_PROFILE)
    raw_settings = contract.get("settings")
    if not isinstance(raw_settings, dict):
        raise RuntimeError("trace profile contract settings are invalid")
    settings = {**raw_settings, "path_precision": path_precision}
    normalized, _ = normalize_raster(payload, profile="raster.png.rgba.v1")
    raw = vtracer.convert_raw_image_to_svg(
        normalized,
        img_format="png",
        **settings,
    ).encode("utf-8")
    reference = _decoded_rgba(normalized)
    normalized = normalize_vtracer_svg(
        raw,
        expected_width=reference.width,
        expected_height=reference.height,
    )
    return sanitize_svg(normalized, profile=str(contract["sanitizer_profile"]))


def _trace_roundtrip(convert: str, svg: bytes, reference: Image.Image) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix="schauwerk-fundus-trace-bench-") as directory:
        root = Path(directory)
        source = root / "vector.svg"
        output = root / "roundtrip.png"
        source.write_bytes(svg)
        completed = subprocess.run(
            [convert, str(source), str(output)],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
        candidate = Image.open(output).convert("RGBA").resize(reference.size)
        return _pixel_metrics(reference, candidate)


def _trace_fixture_quality_equivalent(
    three: dict[str, object],
    eight: dict[str, object],
) -> bool:
    if not three.get("sanitizer_fixed_point") or not eight.get("sanitizer_fixed_point"):
        return False
    if three.get("path_count") != eight.get("path_count"):
        return False
    three_roundtrip = three.get("roundtrip")
    eight_roundtrip = eight.get("roundtrip")
    if not isinstance(three_roundtrip, dict) or not isinstance(eight_roundtrip, dict):
        return False
    return (
        three_roundtrip.get("max_channel_error") == eight_roundtrip.get("max_channel_error")
        and isinstance(three_roundtrip.get("mean_channel_error"), (int, float))
        and isinstance(eight_roundtrip.get("mean_channel_error"), (int, float))
        and abs(
            float(three_roundtrip["mean_channel_error"])
            - float(eight_roundtrip["mean_channel_error"])
        )
        <= TRACE_QUALITY_DELTA_LIMIT
    )


def benchmark_trace() -> dict[str, object]:
    status = trace_adapter_status()
    fixtures = _trace_fixtures()
    if not status["available"]:
        return {
            "adapter": status,
            "semantic_fixtures": list(fixtures),
            "selected_path_precision": None,
            "candidates": {},
        }

    convert = shutil.which("convert")
    candidates: dict[str, dict[str, object]] = {}
    for precision in (3, 8):
        fixture_results: dict[str, dict[str, object]] = {}
        all_timings: list[float] = []
        for fixture_name, payload in fixtures.items():
            reference = _decoded_rgba(payload)
            output, timings = _timed(
                lambda payload=payload, precision=precision: _trace_candidate(
                    payload,
                    path_precision=precision,
                )
            )
            all_timings.extend(timings)
            result: dict[str, object] = {
                "bytes": len(output),
                "deterministic": True,
                "median_ms": round(statistics.median(timings), 3),
                "path_count": output.count(b"<path"),
                "sanitizer_fixed_point": sanitize_svg(
                    output,
                    profile="svg.decorative.v1",
                )
                == output,
            }
            if convert is not None:
                result["roundtrip"] = _trace_roundtrip(convert, output, reference)
            fixture_results[fixture_name] = result
        candidates[str(precision)] = {
            "fixtures": fixture_results,
            "bytes": sum(int(value["bytes"]) for value in fixture_results.values()),
            "deterministic": all(
                value["deterministic"] is True for value in fixture_results.values()
            ),
            "median_ms": round(statistics.median(all_timings), 3),
            "path_count": sum(int(value["path_count"]) for value in fixture_results.values()),
            "sanitizer_fixed_point": all(
                value["sanitizer_fixed_point"] is True for value in fixture_results.values()
            ),
        }

    selected: int | None = None
    three = candidates["3"]
    eight = candidates["8"]
    three_fixtures = three["fixtures"]
    eight_fixtures = eight["fixtures"]
    corpus_equivalent = all(
        _trace_fixture_quality_equivalent(
            three_fixtures[name],
            eight_fixtures[name],
        )
        for name in fixtures
    )
    if (
        three["sanitizer_fixed_point"]
        and eight["sanitizer_fixed_point"]
        and int(three["bytes"]) < int(eight["bytes"])
        and corpus_equivalent
    ):
        selected = 3
    return {
        "adapter": status,
        "semantic_fixtures": list(fixtures),
        "candidates": candidates,
        "corpus_quality_equivalent": corpus_equivalent,
        "selected_path_precision": selected,
    }


def main() -> int:
    report = {
        "schema_version": "schauwerk-fundus-adapter-benchmark.v1",
        "iterations": ITERATIONS,
        "fixture_corpus": fixture_corpus_manifest(),
        "raster": benchmark_raster(),
        "trace": benchmark_trace(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
