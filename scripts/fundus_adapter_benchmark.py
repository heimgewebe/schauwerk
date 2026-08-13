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
    _VTRACER_SETTINGS,
    _normalize_vtracer_svg,
    trace_adapter_status,
)

ITERATIONS = 8


def _fixture() -> Image.Image:
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


def _raster_fixtures() -> dict[str, bytes]:
    image = _fixture()
    result: dict[str, bytes] = {}

    info = PngImagePlugin.PngInfo()
    info.add_text("fundus-benchmark", "remove-me")
    output = BytesIO()
    image.save(output, "PNG", pnginfo=info, compress_level=6)
    result["png"] = output.getvalue()

    output = BytesIO()
    image.convert("RGB").save(output, "JPEG", quality=91, subsampling=0)
    result["jpeg"] = output.getvalue()

    if features.check("webp"):
        output = BytesIO()
        image.save(output, "WEBP", lossless=True, quality=100)
        result["webp"] = output.getvalue()
    return result


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
        fixture_results: dict[str, object] = {}
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
    return {"fixtures": list(fixtures), "candidates": candidates, "selected": selected}


def _trace_fixture() -> bytes:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((25, 25, 155, 155), fill=(201, 154, 64), outline=(20, 20, 20), width=4)
    draw.polygon([(175, 30), (235, 128), (175, 226), (140, 128)], fill=(40, 80, 110))
    draw.rectangle((35, 180, 120, 220), fill=(30, 30, 30))
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def _trace_candidate(payload: bytes, *, path_precision: int) -> bytes:
    import vtracer

    settings = {**_VTRACER_SETTINGS, "path_precision": path_precision}
    normalized, _ = normalize_raster(payload, profile="raster.png.rgba.v1")
    raw = vtracer.convert_raw_image_to_svg(
        normalized,
        img_format="png",
        **settings,
    ).encode("utf-8")
    reference = _decoded_rgba(normalized)
    normalized = _normalize_vtracer_svg(
        raw,
        expected_width=reference.width,
        expected_height=reference.height,
    )
    return sanitize_svg(normalized, profile="svg.decorative.v1")


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


def benchmark_trace() -> dict[str, object]:
    status = trace_adapter_status()
    if not status["available"]:
        return {"adapter": status, "selected_path_precision": None, "candidates": {}}

    payload = _trace_fixture()
    reference = _decoded_rgba(payload)
    convert = shutil.which("convert")
    candidates: dict[str, object] = {}
    for precision in (3, 8):
        output, timings = _timed(
            lambda precision=precision: _trace_candidate(payload, path_precision=precision)
        )
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
        candidates[str(precision)] = result

    selected: int | None = None
    three = candidates["3"]
    eight = candidates["8"]
    three_roundtrip = three.get("roundtrip")
    eight_roundtrip = eight.get("roundtrip")
    equivalent_quality = False
    if isinstance(three_roundtrip, dict) and isinstance(eight_roundtrip, dict):
        equivalent_quality = (
            three_roundtrip["max_channel_error"] == eight_roundtrip["max_channel_error"]
            and abs(
                three_roundtrip["mean_channel_error"]
                - eight_roundtrip["mean_channel_error"]
            )
            <= 0.01
        )
    if (
        three["sanitizer_fixed_point"]
        and eight["sanitizer_fixed_point"]
        and three["path_count"] == eight["path_count"]
        and three["bytes"] < eight["bytes"]
        and equivalent_quality
    ):
        selected = 3
    return {
        "adapter": status,
        "candidates": candidates,
        "selected_path_precision": selected,
    }


def main() -> int:
    report = {
        "schema_version": "schauwerk-fundus-adapter-benchmark.v1",
        "iterations": ITERATIONS,
        "raster": benchmark_raster(),
        "trace": benchmark_trace(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
