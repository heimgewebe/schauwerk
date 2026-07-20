"""Package-bound delivery of deterministic representation bundles to Miro."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from schauwerk.surfaces.miro.native_executor import (
    required_tools,
    validate_native_bundle,
)

CHECK_SCHEMA = "schauwerk-representation-delivery-check.v1"
RECEIPT_SCHEMA = "schauwerk-representation-delivery-receipt.v1"
PACKAGE_SCHEMA = "schauwerk-representation-package.v1"
PACKAGE_RECEIPT_SCHEMA = "schauwerk-representation-receipt.v1"
NATIVE_BUNDLE_SCHEMA = "schauwerk-miro-native-bundle.v1"

_MAX_PACKAGE_FILE_BYTES = 2_000_000
_MAX_DOCUMENT_BYTES = 75_000
_MAX_TABLE_ROWS = 500
_MAX_NATIVE_OPERATIONS = 20


class RepresentationDeliveryError(ValueError):
    """The representation package or delivery state is unsafe or inconsistent."""


class NativeDeliveryClient(Protocol):
    async def native_apply(
        self,
        *,
        alias: str,
        input_path: Path,
        output_path: Path,
        resume_path: Path | None = None,
    ) -> dict[str, Any]: ...


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def render_representation_document(model: Mapping[str, Any]) -> str:
    lines = [f"# {model['title']}", "", str(model["purpose"]), "", "## Elemente", ""]
    for node in model["nodes"]:
        suffix = f" — {node['summary']}" if node["summary"] else ""
        lines.append(f"- **{node['label']}** ({node['kind']}){suffix}")
    lines.extend(["", "## Beziehungen", ""])
    for edge in model["edges"]:
        lines.append(f"- `{edge['from']}` — {edge['label']} → `{edge['to']}`")
    return "\n".join(lines) + "\n"


def render_representation_table(model: Mapping[str, Any]) -> str:
    rows = ["id\tlabel\tkind\tgroup"]
    rows.extend(
        f"{node['id']}\t{node['label']}\t{node['kind']}\t{node['group'] or ''}"
        for node in model["nodes"]
    )
    return "\n".join(rows) + "\n"


def _chunk_text(value: str, *, maximum_bytes: int, label: str) -> list[str]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return [value]
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for line in value.splitlines(keepends=True):
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > maximum_bytes:
            raise RepresentationDeliveryError(f"{label} contains a line that exceeds its limit")
        if current and current_bytes + line_bytes > maximum_bytes:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(line)
        current_bytes += line_bytes
    if current:
        chunks.append("".join(current))
    if not chunks:
        raise RepresentationDeliveryError(f"{label} cannot be split safely")
    return chunks


def _table_rows(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "cells": [
                {"columnTitle": "ID", "value": str(node["id"])},
                {"columnTitle": "Label", "value": str(node["label"])},
                {"columnTitle": "Kind", "value": str(node["kind"])},
                {"columnTitle": "Group", "value": str(node["group"] or "")},
                {"columnTitle": "Summary", "value": str(node["summary"])},
            ],
        }
        for node in model["nodes"]
    ]


def _diagram_label(value: Any, *, maximum: int = 48) -> str:
    text = " ".join(str(value).replace('"', "'").split())
    if not text:
        return "—"
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _native_flowchart_dsl(model: Mapping[str, Any]) -> str:
    """Compile the semantic graph into Miro's native flowchart DSL."""

    node_refs = {str(node["id"]): f"n{index}" for index, node in enumerate(model["nodes"], 1)}
    shape_by_kind = {
        "human": "flowchart-terminator",
        "decision": "flowchart-decision",
        "risk": "flowchart-decision",
    }
    lines = ["graphdir LR", "palette #E6F6F8 #FFF8DD #EAF8F0", ""]
    for node in model["nodes"]:
        reference = node_refs[str(node["id"])]
        shape = shape_by_kind.get(str(node["kind"]), "flowchart-process")
        palette_index = (
            1
            if node["kind"] in {"decision", "risk"}
            else 2
            if node["kind"] in {"store", "evidence"}
            else 0
        )
        lines.append(f"{reference} {_diagram_label(node['label'])} {shape} {palette_index}")
    lines.append("")
    for edge in model["edges"]:
        source = node_refs[str(edge["from"])]
        target = node_refs[str(edge["to"])]
        relation = "·".join(_diagram_label(edge["label"], maximum=32).split())
        lines.append(f"c {source} {relation or '-'} {target}")
    grouped: dict[str, list[str]] = {}
    group_titles = {str(group["id"]): str(group["label"]) for group in model.get("groups", [])}
    for node in model["nodes"]:
        group = node.get("group")
        if group:
            grouped.setdefault(str(group), []).append(node_refs[str(node["id"])])
    for index, (group_id, references) in enumerate(grouped.items(), 1):
        title = _diagram_label(group_titles.get(group_id, group_id), maximum=60)
        lines.append(f'cluster c{index} "{title}" {" ".join(references)}')
    return "\n".join(lines) + "\n"


def compile_representation_native_bundle(
    model: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    layout_dsl: str | None,
    mermaid_source: str | None,
    document_source: str | None,
) -> dict[str, Any] | None:
    """Compile only renderer artifacts that the current native executor can verify."""

    selected = set(plan["selected_formats"])
    operations: list[dict[str, Any]] = []
    if "miro_native" in selected:
        if not layout_dsl:
            raise RepresentationDeliveryError("Miro-native delivery requires layout DSL")
        if len(layout_dsl.encode("utf-8")) > 50_000:
            raise RepresentationDeliveryError("Miro layout DSL exceeds the native bundle limit")
        operations.append(
            {
                "operation_id": "representation-layout",
                "kind": "layout",
                "dsl": layout_dsl,
            }
        )

    if "mermaid" in selected:
        if not mermaid_source:
            raise RepresentationDeliveryError("Mermaid delivery requires exact source text")
        operations.append(
            {
                "operation_id": "rendered-semantic-diagram",
                "kind": "diagram",
                "title": f"{model['title']} · Gesamtmodell",
                "diagram_type": "flowchart",
                "diagram_dsl": _native_flowchart_dsl(model),
                "x": 10600,
                "y": 380,
            }
        )

    if "document" in selected:
        if not document_source:
            raise RepresentationDeliveryError("document delivery requires exact source text")
        chunks = _chunk_text(
            document_source,
            maximum_bytes=_MAX_DOCUMENT_BYTES,
            label="representation document",
        )
        for index, chunk in enumerate(chunks, start=1):
            operations.append(
                {
                    "operation_id": f"representation-document-{index}",
                    "kind": "document",
                    "content": chunk,
                    "x": 8000,
                    "y": 1000 + (index - 1) * 1600,
                }
            )

    if "table" in selected:
        rows = _table_rows(model)
        chunks = [
            rows[index : index + _MAX_TABLE_ROWS] for index in range(0, len(rows), _MAX_TABLE_ROWS)
        ]
        for index, chunk in enumerate(chunks, start=1):
            suffix = f" {index}/{len(chunks)}" if len(chunks) > 1 else ""
            operations.append(
                {
                    "operation_id": f"representation-table-{index}",
                    "kind": "table",
                    "table_title": f"{model['title']} — elements{suffix}",
                    "columns": [
                        {"column_type": "text", "column_title": "ID"},
                        {"column_type": "text", "column_title": "Label", "isTitle": True},
                        {"column_type": "text", "column_title": "Kind"},
                        {"column_type": "text", "column_title": "Group"},
                        {"column_type": "text", "column_title": "Summary"},
                    ],
                    "rows": chunk,
                    "view": {"layout": "table", "table_nesting_enabled": False},
                    "x": 8000,
                    "y": 3500 + (index - 1) * 1800,
                }
            )

    if not operations:
        return None
    if len(operations) > _MAX_NATIVE_OPERATIONS:
        raise RepresentationDeliveryError(
            "representation requires more native operations than one safe bundle permits"
        )
    input_id = str(model["id"])
    bundle_id = f"repr-{input_id[:42]}-{str(model['input_digest'])[:12]}"
    candidate = {
        "schema_version": NATIVE_BUNDLE_SCHEMA,
        "bundle_id": bundle_id,
        "operations": operations,
    }
    validate_native_bundle(candidate)
    return candidate


def _safe_root(path: Path, *, label: str) -> tuple[Path, int]:
    root = path.expanduser().absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise RepresentationDeliveryError(f"{label} path must not contain symlinks")
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise RepresentationDeliveryError(f"{label} directory is unavailable") from exc
    current = os.fstat(descriptor)
    if not stat.S_ISDIR(current.st_mode):
        os.close(descriptor)
        raise RepresentationDeliveryError(f"{label} path is not a directory")
    if current.st_uid != os.getuid() or current.st_mode & 0o077:
        os.close(descriptor)
        raise RepresentationDeliveryError(f"{label} directory must be owner-only")
    return root, descriptor


def _read_member(root_fd: int, name: str, *, label: str) -> bytes:
    if Path(name).name != name or name in {".", ".."}:
        raise RepresentationDeliveryError(f"{label} path is unsafe")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=root_fd)
    except OSError as exc:
        raise RepresentationDeliveryError(f"{label} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RepresentationDeliveryError(f"{label} is not a regular file")
        if before.st_uid != os.getuid() or before.st_nlink != 1 or before.st_mode & 0o077:
            raise RepresentationDeliveryError(f"{label} ownership is unsafe")
        if before.st_size > _MAX_PACKAGE_FILE_BYTES:
            raise RepresentationDeliveryError(f"{label} exceeds the package file limit")
        payload = bytearray()
        while len(payload) < before.st_size:
            chunk = os.read(descriptor, min(65_536, before.st_size - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RepresentationDeliveryError(f"{label} changed while being read")
        if len(payload) != before.st_size:
            raise RepresentationDeliveryError(f"{label} could not be read completely")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _json_member(root_fd: int, name: str, *, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_member(root_fd, name, label=label)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepresentationDeliveryError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RepresentationDeliveryError(f"{label} must contain a JSON object")
    return value, payload


def _artifact_map(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RepresentationDeliveryError("representation manifest artifacts are invalid")
    roles: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            raise RepresentationDeliveryError(f"manifest artifact {index} is invalid")
        required = {"role", "path", "bytes", "sha256"}
        if not required <= set(item) or set(item) - (required | {"coverage"}):
            raise RepresentationDeliveryError(f"manifest artifact {index} fields are invalid")
        role = item.get("role")
        name = item.get("path")
        if not isinstance(role, str) or not role or role in roles:
            raise RepresentationDeliveryError("manifest artifact roles must be unique")
        if not isinstance(name, str) or Path(name).name != name or name in paths:
            raise RepresentationDeliveryError("manifest artifact paths must be safe and unique")
        size = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(size, int) or size < 0 or size > _MAX_PACKAGE_FILE_BYTES:
            raise RepresentationDeliveryError("manifest artifact size is invalid")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RepresentationDeliveryError("manifest artifact digest is invalid")
        roles[role] = dict(item)
        paths.add(name)
    return roles


def _require_role(roles: Mapping[str, Mapping[str, Any]], role: str) -> str:
    try:
        value = roles[role]
    except KeyError as exc:
        raise RepresentationDeliveryError(f"representation package lacks {role}") from exc
    return str(value["path"])


def _decode_text(payload: bytes, *, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepresentationDeliveryError(f"{label} is not UTF-8") from exc


def validate_representation_package(package_dir: Path) -> dict[str, Any]:
    """Recompute all deterministic package artifacts before any provider contact."""

    from schauwerk.surfaces.miro.execution_plan import compile_miro_execution_plan

    from .representation import (
        render_json_canvas,
        render_mermaid,
        render_miro_board,
        route_representation,
        validate_representation_input,
    )
    from .system_v2 import render_board_dsl, validate_board_spec

    root, root_fd = _safe_root(package_dir, label="representation package")
    try:
        manifest, manifest_payload = _json_member(
            root_fd, "manifest.json", label="representation manifest"
        )
        receipt, _ = _json_member(root_fd, "receipt.json", label="representation receipt")
        if manifest.get("schema_version") != PACKAGE_SCHEMA:
            raise RepresentationDeliveryError("representation manifest schema is unsupported")
        if receipt.get("schema_version") != PACKAGE_RECEIPT_SCHEMA:
            raise RepresentationDeliveryError("representation receipt schema is unsupported")
        manifest_digest = manifest.get("package_digest")
        if not isinstance(manifest_digest, str) or len(manifest_digest) != 64:
            raise RepresentationDeliveryError("representation package digest is invalid")
        manifest_body = dict(manifest)
        manifest_body.pop("package_digest", None)
        if _digest(manifest_body) != manifest_digest:
            raise RepresentationDeliveryError("representation manifest digest mismatch")
        receipt_digest = receipt.get("receipt_digest")
        receipt_body = dict(receipt)
        receipt_body.pop("receipt_digest", None)
        if not isinstance(receipt_digest, str) or _digest(receipt_body) != receipt_digest:
            raise RepresentationDeliveryError("representation receipt digest mismatch")
        if receipt.get("package_digest") != manifest_digest:
            raise RepresentationDeliveryError("representation receipt package binding mismatch")
        if receipt.get("manifest_sha256") != _bytes_digest(manifest_payload):
            raise RepresentationDeliveryError("representation receipt manifest binding mismatch")

        roles = _artifact_map(manifest)
        listed_names = {str(item["path"]) for item in roles.values()}
        observed_names = set(os.listdir(root_fd))
        expected_names = listed_names | {"manifest.json", "receipt.json"}
        if observed_names != expected_names:
            raise RepresentationDeliveryError("representation package file set is not exact")
        payloads: dict[str, bytes] = {}
        for role, item in roles.items():
            payload = _read_member(root_fd, str(item["path"]), label=f"artifact {role}")
            if len(payload) != item["bytes"] or _bytes_digest(payload) != item["sha256"]:
                raise RepresentationDeliveryError(f"artifact {role} does not match its manifest")
            payloads[role] = payload
        if receipt.get("artifact_count") != len(roles) + 1:
            raise RepresentationDeliveryError("representation receipt artifact count mismatch")

        input_value = json.loads(payloads["normalized_input"])
        if not isinstance(input_value, dict):
            raise RepresentationDeliveryError("normalized representation input is invalid")
        model = validate_representation_input(input_value)
        if model != input_value:
            raise RepresentationDeliveryError("normalized representation input is not canonical")
        expected_plan = route_representation(model)
        route_plan = json.loads(payloads["route_plan"])
        if route_plan != expected_plan:
            raise RepresentationDeliveryError("representation route plan is not reproducible")
        if manifest.get("input_digest") != model["input_digest"]:
            raise RepresentationDeliveryError("representation manifest input binding mismatch")
        if manifest.get("plan_digest") != expected_plan["plan_digest"]:
            raise RepresentationDeliveryError("representation manifest plan binding mismatch")
        if receipt.get("selected_formats") != expected_plan["selected_formats"]:
            raise RepresentationDeliveryError("representation receipt format binding mismatch")

        mermaid_source: str | None = None
        if "mermaid" in expected_plan["selected_formats"]:
            mermaid_source = render_mermaid(model, expected_plan)
            if _decode_text(payloads["mermaid_source"], label="Mermaid source") != mermaid_source:
                raise RepresentationDeliveryError("Mermaid artifact is not reproducible")
        if "canvas" in expected_plan["selected_formats"]:
            canvas = json.loads(payloads["json_canvas"])
            if canvas != render_json_canvas(model, expected_plan):
                raise RepresentationDeliveryError("JSON Canvas artifact is not reproducible")

        layout_dsl: str | None = None
        quality: dict[str, Any] | None = None
        if "miro_native" in expected_plan["selected_formats"]:
            board = render_miro_board(model, expected_plan)
            emitted_board = json.loads(payloads["miro_board_spec"])
            if emitted_board != board:
                raise RepresentationDeliveryError("Miro board artifact is not reproducible")
            layout_dsl = render_board_dsl(board)
            if _decode_text(payloads["miro_layout_dsl"], label="Miro layout DSL") != layout_dsl:
                raise RepresentationDeliveryError("Miro layout DSL is not reproducible")
            quality = validate_board_spec(board)
            if json.loads(payloads["miro_quality"]) != quality:
                raise RepresentationDeliveryError("Miro quality artifact is not reproducible")
            if quality.get("ok") is not True or quality.get("score", 0) < 90:
                raise RepresentationDeliveryError("Miro quality gate is not satisfied")
            execution_plan = compile_miro_execution_plan(model, expected_plan)
            if json.loads(payloads["miro_execution_plan"]) != execution_plan:
                raise RepresentationDeliveryError("Miro execution plan is not reproducible")

        document_source: str | None = None
        if "document" in expected_plan["selected_formats"]:
            document_source = render_representation_document(model)
            if _decode_text(payloads["narrative_document"], label="document") != document_source:
                raise RepresentationDeliveryError("document artifact is not reproducible")
        if "table" in expected_plan["selected_formats"]:
            if _decode_text(
                payloads["node_table"], label="node table"
            ) != render_representation_table(model):
                raise RepresentationDeliveryError("node table artifact is not reproducible")

        expected_bundle = compile_representation_native_bundle(
            model,
            expected_plan,
            layout_dsl=layout_dsl,
            mermaid_source=mermaid_source,
            document_source=document_source,
        )
        if expected_bundle is None:
            if "miro_native_bundle" in roles:
                raise RepresentationDeliveryError("package exposes an unexpected native bundle")
            bundle = None
            bundle_path = None
        else:
            bundle_name = _require_role(roles, "miro_native_bundle")
            bundle_value = json.loads(payloads["miro_native_bundle"])
            if bundle_value != expected_bundle:
                raise RepresentationDeliveryError("native bundle is not reproducible")
            bundle = validate_native_bundle(bundle_value)
            bundle_path = root / bundle_name

        return {
            "root": root,
            "manifest": manifest,
            "receipt": receipt,
            "model": model,
            "plan": expected_plan,
            "quality": quality,
            "bundle": bundle,
            "bundle_path": bundle_path,
            "native_bundle_payload": payloads.get("miro_native_bundle"),
            "manifest_sha256": _bytes_digest(manifest_payload),
            "native_bundle_sha256": (
                roles["miro_native_bundle"]["sha256"] if bundle is not None else None
            ),
        }
    except KeyError as exc:
        raise RepresentationDeliveryError(
            f"representation package lacks artifact {exc.args[0]}"
        ) from exc
    finally:
        os.close(root_fd)


def check_representation_package(package_dir: Path) -> dict[str, Any]:
    package = validate_representation_package(package_dir)
    bundle = package["bundle"]
    return {
        "schema_version": CHECK_SCHEMA,
        "ok": True,
        "package_digest": package["manifest"]["package_digest"],
        "manifest_sha256": package["manifest_sha256"],
        "input_digest": package["model"]["input_digest"],
        "plan_digest": package["plan"]["plan_digest"],
        "selected_formats": package["plan"]["selected_formats"],
        "native_bundle_available": bundle is not None,
        "native_bundle_digest": bundle["bundle_digest"] if bundle is not None else None,
        "native_operation_count": len(bundle["operations"]) if bundle is not None else 0,
        "required_tools": list(required_tools(bundle)) if bundle is not None else [],
        "quality_score": package["quality"]["score"] if package["quality"] else None,
        "mutation_attempted": False,
        "does_not_establish": [
            "provider capability availability without a live catalogue audit",
            "permission to mutate a board",
            "provider rendering without a native execution receipt",
            "aesthetic quality without human review",
        ],
    }
