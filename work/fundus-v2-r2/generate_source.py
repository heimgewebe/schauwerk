from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

CANVAS = 2048
SUPERSAMPLE = 2
SEED = 202608161513
BRIEF_SHA256 = "1cefe982c8e2d952a994909e2b14f9f021c63ffdd8758ec8dcb424884da91809"
OUT = Path(__file__).with_name("botanical.concave-frame.corner.v2.r2.source.png")
METRICS = Path(__file__).with_name("source-master-metrics.json")


def bezier(p0, p1, p2, p3, n=160):
    points = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        points.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return points


def tangent(path, index):
    a = path[max(0, index - 2)]
    b = path[min(len(path) - 1, index + 2)]
    return math.atan2(b[1] - a[1], b[0] - a[0])


def point_at(path, t):
    index = max(0, min(len(path) - 1, round(t * (len(path) - 1))))
    return path[index], tangent(path, index)


def render(scale: float):
    rng = random.Random(SEED)
    size = CANVAS * SUPERSAMPLE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def sc(point):
        return (point[0] * SUPERSAMPLE, point[1] * SUPERSAMPLE)

    def tapered(path, start_width, end_width):
        for i in range(len(path) - 1):
            t = i / max(1, len(path) - 2)
            width = (start_width * (1 - t) + end_width * t) * SUPERSAMPLE
            draw.line([sc(path[i]), sc(path[i + 1])], fill=(0, 0, 0, 255), width=max(2, round(width)))

    def leaf(base, angle, length, width, curvature=0.0, asymmetry=0.0, lean=0.0):
        length *= scale
        width *= scale
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        left = []
        right = []
        samples = 34
        for i in range(samples + 1):
            t = i / samples
            center_bend = curvature * math.sin(math.pi * t) + lean * t * (1 - t)
            cx = base[0] + ux * length * t + nx * center_bend
            cy = base[1] + uy * length * t + ny * center_bend
            envelope = (math.sin(math.pi * t) ** 0.72) * (0.82 + 0.18 * (1 - t))
            left_half = width * 0.5 * envelope * (1.0 + asymmetry * (1 - t))
            right_half = width * 0.5 * envelope * (1.0 - asymmetry * (1 - t))
            left.append(((cx + nx * left_half) * SUPERSAMPLE, (cy + ny * left_half) * SUPERSAMPLE))
            right.append(((cx - nx * right_half) * SUPERSAMPLE, (cy - ny * right_half) * SUPERSAMPLE))
        draw.polygon(left + right[::-1], fill=(0, 0, 0, 255))
        petiole = min(26 * scale, length * 0.16)
        draw.line(
            [sc(base), sc((base[0] + ux * petiole, base[1] + uy * petiole))],
            fill=(0, 0, 0, 255),
            width=max(3, round(5.5 * SUPERSAMPLE * scale)),
        )

    def twig(base, angle, length, start_width, bend, leaf_count, outward=True):
        length *= 0.93 + 0.08 * scale
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        p0 = base
        p1 = (base[0] + ux * length * 0.32 + nx * bend, base[1] + uy * length * 0.32 + ny * bend)
        p2 = (base[0] + ux * length * 0.69 - nx * bend * 0.38, base[1] + uy * length * 0.69 - ny * bend * 0.38)
        p3 = (base[0] + ux * length, base[1] + uy * length)
        path = bezier(p0, p1, p2, p3, 48)
        tapered(path, start_width * scale, max(2.3, start_width * 0.30) * scale)
        fractions = [0.27, 0.48, 0.69][: max(0, leaf_count - 1)]
        for j, frac in enumerate(fractions):
            anchor, ta = point_at(path, frac)
            side = -1 if (j + (1 if outward else 0)) % 2 == 0 else 1
            delta = side * rng.uniform(0.72, 1.04)
            leaf(
                anchor,
                ta + delta,
                rng.uniform(108, 166) * (0.94 if not outward else 1.0),
                rng.uniform(62, 94),
                curvature=rng.uniform(-13, 13),
                asymmetry=rng.uniform(-0.18, 0.18),
                lean=rng.uniform(-9, 9),
            )
        tip, ta = point_at(path, 1.0)
        leaf(
            tip,
            ta + rng.uniform(-0.12, 0.12),
            rng.uniform(122, 178),
            rng.uniform(66, 98),
            curvature=rng.uniform(-11, 11),
            asymmetry=rng.uniform(-0.15, 0.15),
            lean=rng.uniform(-7, 7),
        )
        return path

    nexus = (452.0, 448.0)
    horizontal = bezier(nexus, (690, 370), (1165, 430), (1690, 340), 190)
    vertical = bezier(nexus, (372, 700), (435, 1160), (340, 1690), 190)
    tapered(horizontal, 23 * scale, 6.2 * scale)
    tapered(vertical, 24 * scale, 6.0 * scale)

    # A short independent interior shoot makes the common node read as grown, not joined.
    inner = bezier((456, 452), (512, 492), (548, 560), (590, 632), 52)
    tapered(inner, 11 * scale, 3.5 * scale)
    leaf((520, 510), 0.38, 126, 72, curvature=8, asymmetry=-0.12, lean=4)
    leaf((555, 565), 1.42, 112, 63, curvature=-7, asymmetry=0.11, lean=-3)
    leaf((590, 632), 0.98, 132, 70, curvature=6, asymmetry=0.05, lean=4)

    # Deliberately non-uniform attachment rhythm. Each run is independently composed.
    horizontal_t = [0.055, 0.115, 0.205, 0.292, 0.405, 0.515, 0.642, 0.746, 0.858, 0.945]
    vertical_t = [0.070, 0.158, 0.248, 0.365, 0.455, 0.585, 0.688, 0.803, 0.902, 0.967]

    for i, t in enumerate(horizontal_t):
        base, ta = point_at(horizontal, t)
        outward_angle = ta - rng.uniform(0.80, 1.13)
        outward_len = rng.uniform(150, 235) * (1.08 - 0.035 * i)
        twig(base, outward_angle, outward_len, rng.uniform(7.5, 12.5), rng.uniform(-22, 22), rng.choice([3, 4]), outward=True)
        # Inner shoots are deliberately sparse and shorter to protect the concave center.
        if i in {0, 2, 3, 5, 7, 9}:
            inward_angle = ta + rng.uniform(0.74, 1.05)
            inward_len = rng.uniform(105, 178) * (1.05 - 0.025 * i)
            twig(base, inward_angle, inward_len, rng.uniform(6.0, 9.5), rng.uniform(-15, 15), rng.choice([2, 3]), outward=False)

    for i, t in enumerate(vertical_t):
        base, ta = point_at(vertical, t)
        outward_angle = ta + rng.uniform(0.82, 1.16)
        outward_len = rng.uniform(155, 240) * (1.08 - 0.035 * i)
        twig(base, outward_angle, outward_len, rng.uniform(7.5, 12.8), rng.uniform(-24, 20), rng.choice([3, 4]), outward=True)
        if i in {0, 1, 3, 5, 6, 8}:
            inward_angle = ta - rng.uniform(0.72, 1.03)
            inward_len = rng.uniform(108, 182) * (1.05 - 0.025 * i)
            twig(base, inward_angle, inward_len, rng.uniform(6.0, 9.8), rng.uniform(-16, 16), rng.choice([2, 3]), outward=False)

    # Nexus foliage: asymmetrical, varied, and individually shaped rather than rosette-like.
    nexus_leaves = [
        (-2.44, 180, 96, -13, -0.15),
        (-1.70, 152, 78, 8, 0.10),
        (2.55, 170, 88, 12, 0.14),
        (2.02, 142, 73, -9, -0.08),
        (0.72, 154, 82, 10, 0.06),
    ]
    for angle, length, width, curve, asym in nexus_leaves:
        leaf(nexus, angle, length, width, curvature=curve, asymmetry=asym, lean=curve * 0.35)

    # A few buds only, all tied to terminal zones and intentionally irregular.
    for x, y, radius in [(720, 205, 10), (1280, 260, 8), (218, 730, 9), (250, 1280, 7), (1730, 275, 6)]:
        r = radius * scale * SUPERSAMPLE
        cx, cy = x * SUPERSAMPLE, y * SUPERSAMPLE
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 255))

    shifted = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shifted.alpha_composite(image, dest=(30 * SUPERSAMPLE, 30 * SUPERSAMPLE))
    image = shifted.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    flat = alpha.get_flattened_data()
    occupied = sum(1 for value in flat if value > 8) / (CANVAS * CANVAS)
    strong = sum(1 for value in flat if value > 127) / (CANVAS * CANVAS)
    core = alpha.crop((820, 820, 1900, 1900))
    core_flat = core.get_flattened_data()
    core_occupied = sum(1 for value in core_flat if value > 8) / (1080 * 1080)
    central_negative = 1.0 - core_occupied
    crop_safe = bool(bbox and bbox[0] >= 18 and bbox[1] >= 18 and bbox[2] <= 2030 and bbox[3] <= 2030)
    return image, {
        "scale": scale,
        "alpha_bbox": list(bbox) if bbox else None,
        "alpha_coverage_gt8": occupied,
        "alpha_coverage_gt127": strong,
        "central_core": [820, 820, 1900, 1900],
        "central_negative_space": central_negative,
        "crop_safe": crop_safe,
    }


candidates = []
chosen = None
for scale in (0.90, 1.00, 1.10, 1.20, 1.30, 1.40, 1.50, 1.60):
    image, metrics = render(scale)
    candidates.append(metrics)
    if metrics["crop_safe"] and metrics["central_negative_space"] >= 0.70 and 0.18 <= metrics["alpha_coverage_gt8"] <= 0.28:
        score = abs(metrics["alpha_coverage_gt8"] - 0.215) + abs(metrics["alpha_coverage_gt127"] - 0.20) * 0.15
        if chosen is None or score < chosen[0]:
            chosen = (score, image, metrics)

if chosen is None:
    raise SystemExit(json.dumps({"status": "no_brief_compliant_candidate", "candidates": candidates}, indent=2))

_, final_image, final_metrics = chosen
final_image.save(OUT, format="PNG", optimize=True)
payload = OUT.read_bytes()
final_metrics = {
    "schema_version": "schauwerk-fundus-source-master-metrics.v1",
    "asset_id": "botanical.concave-frame.corner.v2",
    "revision_label": "r2",
    "canvas": [CANVAS, CANVAS],
    "brief_sha256": BRIEF_SHA256,
    "generator": "chatgpt-local-organic-vector-raster-v2",
    "seed": SEED,
    **final_metrics,
    "source_sha256": hashlib.sha256(payload).hexdigest(),
    "bytes": len(payload),
    "selection_candidates": candidates,
}
METRICS.write_text(json.dumps(final_metrics, indent=2) + "\n", encoding="utf-8")
print(json.dumps(final_metrics, indent=2))
