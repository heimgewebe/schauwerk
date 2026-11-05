#!/usr/bin/env python3
"""Offline, source-bound A/B comparison for Schaubild renderers.

This is evaluation-only: it does not change the product's renderer or its
representation. External command-line renderers are optional, not dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from schauwerk.visual.native_diagram import render_native_diagram
from schauwerk.visual.representation import validate_representation_input

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "docs" / "operators" / "fixtures" / "golden"
GOLDEN_NAMES = (
    "system-landscape-v1.json",
    "decision-flow-v1.json",
    "narrative-journey-v1.json",
)
SUPPORTED_ENGINES = ("native", "graphviz-dot", "d2-dagre", "d2-elk", "d2-tala")
MAX_SVG_BYTES = 16 * 1024 * 1024
ENGINE_TIMEOUT_SECONDS = 25


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _quoted(value: Any) -> str:
    """Both DOT and D2 accept double-quoted, JSON-escaped one-line strings."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return json.dumps(text, ensure_ascii=False)


def _display_node(node: dict[str, Any]) -> str:
    label = str(node["label"])
    kind = str(node["kind"])
    summary = str(node.get("summary") or "")
    return f"{label} [{kind}]" + (f" — {summary}" if summary else "")


def _edge_label(edge: dict[str, Any]) -> str:
    return f"{edge['label']} [{edge['kind']}]"


def graphviz_source(model: dict[str, Any]) -> str:
    """Compile semantic identities/labels into DOT without changing the model."""
    lines = [
        "digraph schauwerk {",
        "  graph [rankdir=LR, compound=true, fontname=\"sans-serif\",",
        f"    label={_quoted(model['title'])}, labelloc=t];",
        "  node [shape=box, style=rounded, fontname=\"sans-serif\"];",
        "  edge [fontname=\"sans-serif\", fontsize=11];",
    ]
    grouped: dict[str | None, list[dict[str, Any]]] = {None: []}
    for group in model["groups"]:
        grouped[str(group["id"])] = []
    for node in model["nodes"]:
        grouped[str(node["group"]) if node.get("group") else None].append(node)

    def add_nodes(nodes: list[dict[str, Any]], indent: str) -> None:
        for node in nodes:
            lines.append(
                f"{indent}n_{node['id']} ["
                f"id={_quoted('sw-node-' + node['id'])}, "
                f"label={_quoted(_display_node(node))}, "
                f"tooltip={_quoted(node['id'])}];"
            )

    add_nodes(grouped[None], "  ")
    for group in model["groups"]:
        gid = str(group["id"])
        lines.extend([
            f"  subgraph cluster_g_{gid} {{",
            f"    id={_quoted('sw-group-' + gid)};",
            f"    label={_quoted(group['label'])};",
            "    style=rounded;",
        ])
        add_nodes(grouped[gid], "    ")
        lines.append("  }")

    for edge in model["edges"]:
        style = "dashed" if edge["kind"] == "feedback" else "solid"
        lines.append(
            f"  n_{edge['from']} -> n_{edge['to']} ["
            f"id={_quoted('sw-edge-' + edge['id'])}, "
            f"label={_quoted(_edge_label(edge))}, style={style}, "
            f"tooltip={_quoted(edge['id'])}];"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def d2_source(model: dict[str, Any]) -> str:
    """Simple D2 graph with stable source-derived keys; never edits the source."""
    lines = ["direction: right", f"# Source document: {model['id']}"]
    by_group: dict[str | None, list[dict[str, Any]]] = {None: []}
    node_keys: dict[str, str] = {}
    for group in model["groups"]:
        by_group[str(group["id"])] = []
    for node in model["nodes"]:
        gid = str(node["group"]) if node.get("group") else None
        by_group[gid].append(node)
        node_keys[str(node["id"])] = f"g_{gid}.n_{node['id']}" if gid else f"n_{node['id']}"
    for node in by_group[None]:
        lines.append(f"n_{node['id']}: {_quoted(_display_node(node))}")
    for group in model["groups"]:
        gid = str(group["id"])
        lines.append(f"g_{gid}: {_quoted(group['label'])} {{")
        for node in by_group[gid]:
            lines.append(f"  n_{node['id']}: {_quoted(_display_node(node))}")
        lines.append("}")
    for edge in model["edges"]:
        lines.append(
            f"{node_keys[str(edge['from'])]} -> {node_keys[str(edge['to'])]}:"
            f" {_quoted(_edge_label(edge))}"
        )
    return "\n".join(lines) + "\n"


def _id_coverage(svg: bytes, model: dict[str, Any], engine: str) -> dict[str, Any]:
    root = ET.fromstring(svg)
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("renderer returned no SVG root")
    ids = {elem.attrib.get("id", "") for elem in root.iter()}
    if engine == "native":
        found_nodes = {
            elem.attrib.get("data-source-id")
            for elem in root.iter()
            if elem.attrib.get("data-source-kind") == "node"
        }
        found_edges = {
            elem.attrib.get("data-source-id")
            for elem in root.iter()
            if elem.attrib.get("data-source-kind") == "edge"
        }
        # Native group metadata is not a universally promised shape contract.
        groups = {"status": "not_measured", "count": len(model["groups"])}
    elif engine == "graphviz-dot":
        found_nodes = {s.removeprefix("sw-node-") for s in ids if s.startswith("sw-node-")}
        found_edges = {s.removeprefix("sw-edge-") for s in ids if s.startswith("sw-edge-")}
        found_groups = {s.removeprefix("sw-group-") for s in ids if s.startswith("sw-group-")}
        groups = {
            "status": (
                "complete"
                if found_groups == {g["id"] for g in model["groups"]}
                else "incomplete"
            ),
            "found": len(found_groups),
            "count": len(model["groups"]),
        }
    else:
        # D2 encodes keys in classes rather than preserving source-edge IDs.
        # The DSL and source-map are available, but SVG identity coverage is
        # NOT established by a successful render.
        return {
            "status": "unverified",
            "reason": "D2 SVG source ID/edge mapping requires separate verification",
            "expected_nodes": len(model["nodes"]),
            "expected_edges": len(model["edges"]),
            "expected_groups": len(model["groups"]),
        }
    expected_nodes = {str(n["id"]) for n in model["nodes"]}
    expected_edges = {str(e["id"]) for e in model["edges"]}
    complete = (
        found_nodes == expected_nodes
        and found_edges == expected_edges
        and groups["status"] in ("complete", "not_measured")
    )
    return {
        "status": "complete" if complete else "incomplete",
        "nodes": {"found": len(found_nodes), "expected": len(expected_nodes)},
        "edges": {"found": len(found_edges), "expected": len(expected_edges)},
        "groups": groups,
        "missing_nodes": sorted(expected_nodes - found_nodes),
        "missing_edges": sorted(expected_edges - found_edges),
    }


def _external_render(engine: str, source: str) -> tuple[bytes, str]:
    if engine == "graphviz-dot":
        binary = shutil.which("dot")
        argv = [binary, "-Tsvg"] if binary else None
    else:
        binary = shutil.which("d2")
        layout = engine.removeprefix("d2-")
        argv = [binary, "--layout=" + layout, "-", "-"] if binary else None
    if argv is None:
        raise FileNotFoundError(f"{engine} executable unavailable")
    result = subprocess.run(
        argv, input=source.encode("utf-8"), capture_output=True,
        timeout=ENGINE_TIMEOUT_SECONDS, check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace")[-500:]
        raise RuntimeError(f"{engine} exited {result.returncode}: {detail}")
    return result.stdout, Path(binary).name


def _engine_input(model: dict[str, Any], engine: str) -> tuple[str, str]:
    if engine == "graphviz-dot":
        return graphviz_source(model), "dot"
    if engine.startswith("d2-"):
        return d2_source(model), "d2"
    return "", ""


def evaluate_case(
    input_path: Path, output: Path, engines: tuple[str, ...] = SUPPORTED_ENGINES,
) -> dict[str, Any]:
    raw = input_path.read_bytes()
    model = validate_representation_input(json.loads(raw))
    result: dict[str, Any] = {
        "case": input_path.stem,
        "source_filename": input_path.name,
        "source_sha256": _digest(raw),
        "normalized_input_digest": model["input_digest"],
        "intent": model["intent"],
        "counts": {
            "nodes": len(model["nodes"]),
            "edges": len(model["edges"]),
            "groups": len(model["groups"]),
        },
        "engines": {},
    }
    output.mkdir(parents=True, exist_ok=False)
    for engine in engines:
        record: dict[str, Any] = {"status": "not_started"}
        result["engines"][engine] = record
        begin = time.perf_counter_ns()
        try:
            if engine not in SUPPORTED_ENGINES:
                raise ValueError(f"unknown benchmark engine: {engine}")
            source, suffix = _engine_input(model, engine)
            if suffix:
                (output / f"{engine}.{suffix}").write_text(source, encoding="utf-8")
            if engine == "native":
                payload = render_native_diagram(model).encode("utf-8")
                backend = "schauwerk-native-diagram-v1"
            else:
                payload, backend = _external_render(engine, source)
            if not payload or len(payload) > MAX_SVG_BYTES:
                raise ValueError(f"invalid SVG output size: {len(payload)}")
            coverage = _id_coverage(payload, model, engine)
            (output / f"{engine}.svg").write_bytes(payload)
            record.update({
                "status": (
                    "coverage_incomplete" if coverage["status"] == "incomplete" else "ok"
                ),
                "svg_sha256": _digest(payload),
                "svg_bytes": len(payload),
                "svg_id_coverage": coverage,
                "backend": backend,
            })
        except FileNotFoundError as exc:
            record.update({"status": "unavailable", "reason": str(exc)})
        except subprocess.TimeoutExpired:
            record.update({"status": "timeout", "reason": f"exceeded {ENGINE_TIMEOUT_SECONDS}s"})
        except (ValueError, RuntimeError, ET.ParseError, OSError) as exc:
            record.update({"status": "failed", "reason": str(exc)[:600]})
        record["elapsed_ms"] = round((time.perf_counter_ns() - begin) / 1_000_000, 3)
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def run_benchmark(
    inputs: list[Path], output_dir: Path, engines: tuple[str, ...],
) -> dict[str, Any]:
    if len({str(p.resolve()) for p in inputs}) != len(inputs):
        raise ValueError("duplicate input path")
    if len({p.stem for p in inputs}) != len(inputs):
        raise ValueError("duplicate input stem")
    if not set(engines).issubset(SUPPORTED_ENGINES) or len(set(engines)) != len(engines):
        raise ValueError("unknown or duplicate engine")
    if not engines:
        raise ValueError("at least one renderer required")
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = [evaluate_case(path, output_dir / path.stem, engines) for path in inputs]
    manifest = {
        "schema_version": "schauwerk-renderer-evaluation.v1",
        "evaluation_only": True,
        "inputs": [str(path) for path in inputs],
        "requested_engines": list(engines),
        "cases": cases,
        "does_not_establish": [
            "visual_acceptance", "product_readiness", "editability_of_external_renderers",
            "safe_svg_embedding", "semantic_roundtrip_of_d2",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, action="append",
        help="One existing schauwerk-representation-input.v1 JSON file (repeatable)",
    )
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument(
        "--engines", default=",".join(SUPPORTED_ENGINES),
        help="Comma-separated engine IDs: " + ",".join(SUPPORTED_ENGINES),
    )
    parser.add_argument(
        "--require-all", action="store_true",
        help="Return nonzero if any explicitly requested backend is missing or fails",
    )
    args = parser.parse_args(argv)
    inputs = args.input or [GOLDEN_ROOT / name for name in GOLDEN_NAMES]
    engines = tuple(args.engines.split(","))
    try:
        result = run_benchmark(inputs, args.output, engines)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    failed = False
    for case in result["cases"]:
        for engine, info in case["engines"].items():
            print(
                f"{case['case']}\t{engine}\t{info['status']}\t"
                f"{info['elapsed_ms']}ms\t{info.get('svg_bytes', '-')} bytes"
            )
            if info["status"] in ("failed", "coverage_incomplete", "timeout"):
                failed = True
            if args.require_all and info["status"] != "ok":
                failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())