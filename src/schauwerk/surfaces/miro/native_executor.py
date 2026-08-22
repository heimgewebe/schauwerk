"""Validated, receipt-bound execution of native Miro content bundles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import json
import math
import os
import re
import stat
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from jsonschema import Draft202012Validator

from .capability_fallbacks import (
    CANVAS_DIAGRAM_READBACK_TOOL,
    CANVAS_DIAGRAM_TOOLS,
    LEGACY_DIAGRAM_TOOLS,
    resolve_bundle_operations,
)
from .errors import MiroToolError
from .inspection import checked_payload, result_resource_links
from .layout_dsl import LayoutDslParseError, summarize_layout_dsl

NATIVE_BUNDLE_SCHEMA = "schauwerk-miro-native-bundle.v1"
NATIVE_RECEIPT_SCHEMA = "schauwerk-miro-native-execution-receipt.v1"
ToolCaller = Callable[[str, dict[str, Any]], Awaitable[Any]]
CheckpointWriter = Callable[[dict[str, Any]], None]
HtmlUploader = Callable[[str, bytes], Awaitable[None]]
_MIRO_PREVIEW_RESOURCE_RE = re.compile(r"^miro-preview://create/[A-Za-z0-9_-]{16,128}$")
_MAX_PROVIDER_PREVIEW_BYTES = 10 * 1024 * 1024
_PROVIDER_PREVIEW_MIME_TYPES = frozenset({"image/png", "image/svg+xml"})
_DIAGRAM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIAGRAM_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DIAGRAM_NODE = re.compile(
    r"^(?P<id>\S+)\s+(?P<label>.+)\s+"
    r"(?P<shape>flowchart-(?:process|decision|terminator))\s+"
    r"(?P<palette>\S+)$"
)
_DIAGRAM_CONNECTOR = re.compile(r"^c\s+(?P<src>\S+)\s+(?P<label>.+)\s+(?P<dst>\S+)$")
_DIAGRAM_CLUSTER = re.compile(
    r'^cluster\s+(?P<id>\S+)\s+(?P<title>"(?:\\.|[^"\\])*")\s+(?P<nodes>.+)$'
)
_CANVAS_ITEM_ID = re.compile(r"^[0-9]{1,32}$")
_CANVAS_DIAGRAM_WIDTH = 1600
_CANVAS_DIAGRAM_HEIGHT = 900


class NativeBundleError(ValueError):
    """The local native bundle is structurally or semantically unsafe."""


class NativeExecutionError(MiroToolError):
    """A provider operation failed after a checkpoint receipt was produced."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _diagram_reference(value: str, *, prefix: str) -> str:
    return f"sw_{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _mermaid_text(value: str) -> str:
    replacements = {
        "&": "&amp;",
        '"': "&quot;",
        "<": "&lt;",
        ">": "&gt;",
        "|": "&#124;",
        "\\": "&#92;",
    }
    return "".join(replacements.get(character, character) for character in value)


def _diagram_identifier(value: str, *, line_number: int, label: str) -> str:
    if _DIAGRAM_ID.fullmatch(value) is None or value in {
        "c",
        "cluster",
        "graphdir",
        "palette",
    }:
        raise NativeBundleError(f"diagram DSL line {line_number} has an invalid {label}")
    return value


def _diagram_label(value: str, *, line_number: int, label: str) -> str:
    if not value.strip() or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise NativeBundleError(f"diagram DSL line {line_number} has an invalid {label}")
    return value


def compile_diagram_dsl_to_mermaid(diagram_dsl: str) -> str:
    """Compile Schauwerk's current native flowchart DSL to deterministic Mermaid 10.3."""

    if not isinstance(diagram_dsl, str) or not diagram_dsl.strip():
        raise NativeBundleError("diagram DSL must be a nonempty string")
    direction: str | None = None
    palette: list[str] | None = None
    nodes: list[dict[str, Any]] = []
    connectors: list[dict[str, str]] = []
    clusters: list[dict[str, Any]] = []
    declared_ids: set[str] = set()

    for line_number, raw_line in enumerate(_normalized_text(diagram_dsl).split("\n"), 1):
        if not raw_line.strip():
            continue
        if raw_line != raw_line.strip():
            raise NativeBundleError(
                f"diagram DSL line {line_number} has leading or trailing whitespace"
            )
        if raw_line.startswith("graphdir "):
            parts = raw_line.split()
            if len(parts) != 2 or parts[1] not in {"TD", "LR"}:
                raise NativeBundleError(f"diagram DSL line {line_number} has invalid graphdir")
            if direction is not None:
                raise NativeBundleError("diagram DSL contains duplicate graphdir directives")
            direction = parts[1]
            continue
        if raw_line.startswith("palette "):
            colors = raw_line.split()[1:]
            if not colors or any(_DIAGRAM_COLOR.fullmatch(color) is None for color in colors):
                raise NativeBundleError(f"diagram DSL line {line_number} has an invalid palette")
            if palette is not None:
                raise NativeBundleError("diagram DSL contains duplicate palette directives")
            palette = colors
            continue
        if raw_line.startswith("cluster "):
            match = _DIAGRAM_CLUSTER.fullmatch(raw_line)
            if match is None:
                raise NativeBundleError(f"diagram DSL line {line_number} has an invalid cluster")
            identifier = _diagram_identifier(
                match.group("id"), line_number=line_number, label="cluster id"
            )
            if identifier in declared_ids:
                raise NativeBundleError(f"diagram DSL contains duplicate id: {identifier}")
            try:
                title = json.loads(match.group("title"))
            except json.JSONDecodeError as exc:
                raise NativeBundleError(
                    f"diagram DSL line {line_number} has an invalid cluster title"
                ) from exc
            if not isinstance(title, str):
                raise NativeBundleError(
                    f"diagram DSL line {line_number} has an invalid cluster title"
                )
            title = _diagram_label(title, line_number=line_number, label="cluster title")
            members = match.group("nodes").split()
            if not members or len(members) != len(set(members)):
                raise NativeBundleError(
                    f"diagram DSL line {line_number} has duplicate or empty cluster references"
                )
            members = [
                _diagram_identifier(member, line_number=line_number, label="cluster reference")
                for member in members
            ]
            declared_ids.add(identifier)
            clusters.append(
                {
                    "id": identifier,
                    "title": title,
                    "members": members,
                    "line_number": line_number,
                }
            )
            continue
        if raw_line.startswith("c "):
            match = _DIAGRAM_CONNECTOR.fullmatch(raw_line)
            if match is None:
                raise NativeBundleError(f"diagram DSL line {line_number} has an invalid connector")
            source = _diagram_identifier(
                match.group("src"), line_number=line_number, label="connector source"
            )
            target = _diagram_identifier(
                match.group("dst"), line_number=line_number, label="connector target"
            )
            label = _diagram_label(
                match.group("label"), line_number=line_number, label="edge label"
            )
            connectors.append(
                {
                    "source": source,
                    "target": target,
                    "label": label,
                    "line_number": str(line_number),
                }
            )
            continue

        match = _DIAGRAM_NODE.fullmatch(raw_line)
        if match is None:
            directive = raw_line.split(maxsplit=1)[0]
            raise NativeBundleError(
                f"diagram DSL line {line_number} has an unknown or invalid directive: {directive}"
            )
        identifier = _diagram_identifier(
            match.group("id"), line_number=line_number, label="node id"
        )
        if identifier in declared_ids:
            raise NativeBundleError(f"diagram DSL contains duplicate id: {identifier}")
        palette_index_text = match.group("palette")
        if not palette_index_text.isascii() or not palette_index_text.isdecimal():
            raise NativeBundleError(f"diagram DSL line {line_number} has an invalid palette index")
        palette_index = int(palette_index_text)
        declared_ids.add(identifier)
        nodes.append(
            {
                "id": identifier,
                "label": _diagram_label(
                    match.group("label"), line_number=line_number, label="node label"
                ),
                "shape": match.group("shape"),
                "palette_index": palette_index,
                "line_number": line_number,
            }
        )

    if direction is None:
        raise NativeBundleError("diagram DSL lacks a graphdir directive")
    if palette is None:
        raise NativeBundleError("diagram DSL lacks a palette directive")
    if not nodes:
        raise NativeBundleError("diagram DSL contains no nodes")

    node_by_id = {str(node["id"]): node for node in nodes}
    for node in nodes:
        if node["palette_index"] >= len(palette):
            raise NativeBundleError(
                f"diagram DSL line {node['line_number']} has an out-of-range palette index"
            )
    for connector in connectors:
        if connector["source"] not in node_by_id or connector["target"] not in node_by_id:
            raise NativeBundleError(
                f"diagram DSL line {connector['line_number']} references an unknown node"
            )
    clustered_nodes: set[str] = set()
    for cluster in clusters:
        for member in cluster["members"]:
            if member not in node_by_id:
                raise NativeBundleError(
                    f"diagram DSL line {cluster['line_number']} references an unknown node"
                )
            if member in clustered_nodes:
                raise NativeBundleError(f"diagram DSL node appears in multiple clusters: {member}")
            clustered_nodes.add(member)

    node_references = {
        identifier: _diagram_reference(identifier, prefix="node") for identifier in node_by_id
    }
    cluster_references = {
        str(cluster["id"]): _diagram_reference(str(cluster["id"]), prefix="cluster")
        for cluster in clusters
    }
    if len(set(node_references.values()) | set(cluster_references.values())) != len(
        node_references
    ) + len(cluster_references):  # pragma: no cover - SHA-256 prefix collision guard
        raise NativeBundleError("diagram DSL identifiers produced an unsafe reference collision")

    shape_templates = {
        "flowchart-process": ('["', '"]'),
        "flowchart-decision": ('{"', '"}'),
        "flowchart-terminator": ('(["', '"])'),
    }

    def node_line(identifier: str, *, indentation: str = "  ") -> str:
        node = node_by_id[identifier]
        opening, closing = shape_templates[str(node["shape"])]
        return (
            f"{indentation}{node_references[identifier]}{opening}"
            f"{_mermaid_text(str(node['label']))}{closing}"
        )

    lines = [f"flowchart {direction}"]
    for index, color in enumerate(palette):
        lines.append(f"  classDef swPalette{index} fill:{color};")
    for cluster in clusters:
        cluster_id = str(cluster["id"])
        lines.append(
            f'  subgraph {cluster_references[cluster_id]}["{_mermaid_text(str(cluster["title"]))}"]'
        )
        lines.append(f"    direction {direction}")
        lines.extend(node_line(member, indentation="    ") for member in cluster["members"])
        lines.append("  end")
    lines.extend(node_line(str(node["id"])) for node in nodes if node["id"] not in clustered_nodes)
    for connector in connectors:
        lines.append(
            f'  {node_references[connector["source"]]} -->|"'
            f'{_mermaid_text(connector["label"])}"| {node_references[connector["target"]]}'
        )
    for palette_index in range(len(palette)):
        members = [
            node_references[str(node["id"])]
            for node in nodes
            if node["palette_index"] == palette_index
        ]
        if members:
            lines.append(f"  class {','.join(members)} swPalette{palette_index};")
    return "\n".join(lines) + "\n"


def _number_text(value: Any, *, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise NativeBundleError(f"diagram {label} must be a finite number")
    return f"{float(value):g}"


def render_canvas_diagram_svg(operation: Mapping[str, Any], mermaid_source: str) -> str:
    """Wrap Mermaid source in Miro Canvas's structured editable diagram element."""

    title = operation.get("title")
    if (
        not isinstance(title, str)
        or not title.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in title)
    ):
        raise NativeBundleError("Canvas diagram title must be nonempty")
    operation_id = operation.get("operation_id")
    if not isinstance(operation_id, str):
        raise NativeBundleError("Canvas diagram operation id is invalid")
    local_id = _diagram_reference(operation_id, prefix="canvas")
    x = _number_text(operation.get("x", 0), label="x")
    y = _number_text(operation.get("y", 0), label="y")
    escaped_title = html.escape(title, quote=True)
    escaped_source = html.escape(mermaid_source, quote=False)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS_DIAGRAM_WIDTH}" '
        f'height="{_CANVAS_DIAGRAM_HEIGHT}" viewBox="{x} {y} '
        f'{_CANVAS_DIAGRAM_WIDTH} {_CANVAS_DIAGRAM_HEIGHT}">\n'
        f'  <foreignObject id="{local_id}" x="{x}" y="{y}" '
        f'width="{_CANVAS_DIAGRAM_WIDTH}" height="{_CANVAS_DIAGRAM_HEIGHT}" '
        f'data-type="diagram" data-title="{escaped_title}">{escaped_source}</foreignObject>\n'
        "</svg>\n"
    )


def _load_bundle_schema() -> dict[str, Any]:
    try:
        raw = (
            files("schauwerk.schemas")
            .joinpath("miro-native-bundle.v1.schema.json")
            .read_text(encoding="utf-8")
        )
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativeBundleError("native bundle schema is unreadable") from exc
    if not isinstance(value, dict):
        raise NativeBundleError("native bundle schema must contain an object")
    return value


def _safe_input_path(path: Path, *, label: str, owner_only: bool = False) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise NativeBundleError(f"{label} path must not contain symlinks")
    if not candidate.is_file():
        raise NativeBundleError(f"{label} path must be a regular file")
    metadata = candidate.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise NativeBundleError(f"{label} path must be a regular file")
    if owner_only and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
        raise NativeBundleError(f"{label} must be owner-only")
    return candidate


def load_native_resume_receipt(path: Path) -> dict[str, Any]:
    try:
        candidate = _safe_input_path(path, label="native resume receipt", owner_only=True)
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except NativeBundleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativeBundleError("native resume receipt is unreadable or invalid JSON") from exc
    if not isinstance(raw, dict):
        raise NativeBundleError("native resume receipt must contain a JSON object")
    return raw


def load_native_bundle(path: Path) -> dict[str, Any]:
    try:
        candidate = _safe_input_path(path, label="native bundle")
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except NativeBundleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativeBundleError("native bundle is unreadable or invalid JSON") from exc
    if not isinstance(raw, dict):
        raise NativeBundleError("native bundle must contain a JSON object")
    return validate_native_bundle(raw)


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_http_url(value: str, *, label: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NativeBundleError(f"{label} must be an absolute HTTP(S) URL")


def _validate_table_cell_value(
    *,
    column: Mapping[str, Any],
    value: Any,
) -> None:
    column_type = column["column_type"]
    title = column["column_title"]
    if column_type == "text":
        if not isinstance(value, str):
            raise NativeBundleError(f"text table column {title!r} requires a string")
        return
    if column_type == "select":
        values = value if isinstance(value, list) else [value]
        if not values or not all(_is_nonempty_string(item) for item in values):
            raise NativeBundleError(
                f"select table column {title!r} requires one or more display values"
            )
        if len(values) != len(set(values)):
            raise NativeBundleError(
                f"select table column {title!r} contains duplicate display values"
            )
        allowed = {option["displayValue"] for option in column["options"]}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise NativeBundleError(
                f"select table column {title!r} references unknown values: {', '.join(unknown)}"
            )
        return
    if column_type == "date":
        if not _is_nonempty_string(value):
            raise NativeBundleError(f"date table column {title!r} requires an ISO 8601 string")
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise NativeBundleError(
                f"date table column {title!r} requires an ISO 8601 string"
            ) from exc
        return
    if column_type == "link":
        if isinstance(value, str):
            _validate_http_url(value, label=f"link table column {title!r}")
            return
        if not isinstance(value, list) or not value:
            raise NativeBundleError(
                f"link table column {title!r} requires a URL or non-empty link list"
            )
        for link in value:
            if not isinstance(link, Mapping):
                raise NativeBundleError(
                    f"link table column {title!r} contains an invalid link object"
                )
            if set(link) - {"url", "text"} or not _is_nonempty_string(link.get("url")):
                raise NativeBundleError(
                    f"link table column {title!r} requires objects with url and optional text"
                )
            if "text" in link and not isinstance(link["text"], str):
                raise NativeBundleError(
                    f"link table column {title!r} contains an invalid link label"
                )
            _validate_http_url(link["url"], label=f"link table column {title!r}")
        return
    if column_type == "person":
        values = value if isinstance(value, list) else [value]
        if not values or not all(_is_nonempty_string(item) for item in values):
            raise NativeBundleError(
                f"person table column {title!r} requires one or more Miro user IDs"
            )
        if len(values) != len(set(values)):
            raise NativeBundleError(
                f"person table column {title!r} contains duplicate Miro user IDs"
            )
        return
    raise NativeBundleError(f"unsupported table column type: {column_type}")


def validate_native_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    schema = _load_bundle_schema()
    candidate = {key: item for key, item in value.items() if key != "bundle_digest"}
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(candidate), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        raise NativeBundleError(f"native bundle validation failed at {location}: {error.message}")
    result = json.loads(json.dumps(candidate, ensure_ascii=False))
    operations = result["operations"]
    operation_ids = [operation["operation_id"] for operation in operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise NativeBundleError("native bundle operation_id values must be unique")
    for operation in operations:
        if operation["kind"] != "table":
            continue
        columns = operation["columns"]
        column_titles = [column["column_title"] for column in columns]
        if len(column_titles) != len(set(column_titles)):
            raise NativeBundleError("table column titles must be unique")
        known_columns = set(column_titles)
        columns_by_title = {column["column_title"]: column for column in columns}
        title_columns = [column for column in columns if column.get("isTitle") is True]
        if len(title_columns) > 1:
            raise NativeBundleError("a table may declare at most one title column")
        select_columns: set[str] = set()
        for column in columns:
            column_type = column["column_type"]
            if column_type == "select":
                if not column.get("options"):
                    raise NativeBundleError("select table columns require options")
                option_values = [option["displayValue"] for option in column["options"]]
                if len(option_values) != len(set(option_values)):
                    raise NativeBundleError("select table option display values must be unique")
                select_columns.add(column["column_title"])
            elif "options" in column:
                raise NativeBundleError("only select table columns may define options")
            if column.get("isTitle") is True and column_type != "text":
                raise NativeBundleError("the table title column must be text")
        for row in operation.get("rows", []):
            cell_titles = [cell["columnTitle"] for cell in row["cells"]]
            if len(cell_titles) != len(set(cell_titles)):
                raise NativeBundleError("table row contains duplicate column cells")
            for cell in row["cells"]:
                title = cell["columnTitle"]
                if title not in known_columns:
                    raise NativeBundleError("table row references an unknown column")
                _validate_table_cell_value(
                    column=columns_by_title[title],
                    value=cell["value"],
                )
        view = operation.get("view")
        if view and view["layout"] == "kanban":
            group_by = view.get("group_by_column")
            if group_by is not None and group_by not in select_columns:
                raise NativeBundleError("kanban group_by_column must name a select column")
    result["bundle_digest"] = _digest(
        {key: item for key, item in result.items() if key != "bundle_digest"}
    )
    return result


def required_tools(bundle: Mapping[str, Any]) -> tuple[str, ...]:
    tools = {"user_who_am_i", "context_explore", "board_list_items"}
    for operation in bundle["operations"]:
        kind = operation["kind"]
        if kind == "layout":
            tools.update({"layout_get_dsl", "layout_create", "layout_read"})
        elif kind == "diagram":
            if operation.get("native_transport") == "canvas_diagram":
                tools.update(CANVAS_DIAGRAM_TOOLS)
            else:
                tools.update(LEGACY_DIAGRAM_TOOLS)
        elif kind == "document":
            tools.update({"doc_create", "doc_get"})
        elif kind == "document_update":
            tools.update({"doc_get", "doc_update"})
        elif kind == "table":
            tools.update({"table_create", "table_list_rows"})
            if operation.get("rows"):
                tools.add("table_sync_rows")
            if operation.get("view"):
                tools.add("table_update_view")
        elif kind == "table_history":
            tools.add("table_get_latest_update_history")
        elif kind == "code_widget":
            tools.update({"code_widget_create", "code_widget_get"})
        elif kind == "code_widget_inventory":
            tools.add("code_widget_list_items")
        elif kind == "code_widget_update":
            tools.update({"code_widget_get", "code_widget_update"})
        elif kind == "code_widget_delete":
            tools.update({"code_widget_get", "code_widget_list_items", "code_widget_delete"})
        elif kind == "prototype":
            tools.update({"prototype_get_upload_url", "prototype_create", "context_get"})
        elif kind == "comment":
            tools.update({"comment_create", "comment_list_comments"})
        else:  # pragma: no cover - schema validation owns this branch
            raise NativeBundleError(f"unsupported native operation kind: {kind}")
    return tuple(sorted(tools))


def _board_key(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "miro.com":
        raise NativeBundleError("Miro target URL must use https://miro.com")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[:2] != ["app", "board"] or not parts[2]:
        raise NativeBundleError("Miro target URL must identify a board")
    return parsed.scheme, parsed.netloc, parts[2]


def _target_url(board_url: str, operation: Mapping[str, Any]) -> str:
    candidate = operation.get("target_miro_url", board_url)
    if not isinstance(candidate, str):
        raise NativeBundleError("operation target_miro_url must be a string")
    if _board_key(candidate) != _board_key(board_url):
        raise NativeBundleError("operation target_miro_url is outside the allowlisted board")
    return candidate


def _validate_resume_receipt(
    value: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
    execution_operations: Sequence[Mapping[str, Any]],
    board_alias: str,
    board_url: str,
    provider_resolution_digest: str,
    provider_fallback_count: int,
) -> dict[str, Any]:
    if value.get("schema_version") != NATIVE_RECEIPT_SCHEMA:
        raise NativeBundleError("native resume receipt has an unsupported schema")
    expected_digest = value.get("execution_digest")
    content = {key: item for key, item in value.items() if key != "execution_digest"}
    if not isinstance(expected_digest, str) or expected_digest != _digest(content):
        raise NativeBundleError("native resume receipt digest is invalid")
    if value.get("success") is True or value.get("execution_state") not in {
        "in_progress",
        "failed",
    }:
        raise NativeBundleError("native resume receipt is not resumable")
    if value.get("bundle_digest") != bundle["bundle_digest"]:
        raise NativeBundleError("native resume receipt belongs to a different bundle")
    recorded_resolution = value.get("provider_resolution_digest")
    if recorded_resolution is None:
        if provider_fallback_count:
            raise NativeBundleError("legacy native resume receipt cannot enter a provider fallback")
    elif recorded_resolution != provider_resolution_digest:
        raise NativeBundleError("native resume receipt provider resolution has drifted")
    if value.get("board_alias") != board_alias:
        raise NativeBundleError("native resume receipt belongs to a different board alias")
    if value.get("board_reference_digest") != _text_digest(board_url)[:24]:
        raise NativeBundleError("native resume receipt belongs to a different board")
    preflight = value.get("preflight")
    if not isinstance(preflight, Mapping) or not isinstance(preflight.get("inventory"), Mapping):
        raise NativeBundleError("native resume receipt lacks a baseline inventory")
    baseline_count = preflight["inventory"].get("item_count")
    if isinstance(baseline_count, bool) or not isinstance(baseline_count, int):
        raise NativeBundleError("native resume receipt baseline inventory is invalid")
    if baseline_count < 0:
        raise NativeBundleError("native resume receipt baseline inventory is invalid")
    completed = value.get("completed_operations")
    calls = value.get("calls")
    if not isinstance(completed, list) or not isinstance(calls, list):
        raise NativeBundleError("native resume receipt lacks operation evidence")
    if value.get("completed_operation_count") != len(completed):
        raise NativeBundleError("native resume receipt operation count is inconsistent")
    operations = bundle["operations"]
    if len(completed) > len(operations):
        raise NativeBundleError("native resume receipt contains too many operations")
    for index, completed_operation in enumerate(completed):
        if not isinstance(completed_operation, Mapping):
            raise NativeBundleError("native resume receipt contains invalid operation evidence")
        expected = operations[index]
        if (
            completed_operation.get("operation_id") != expected["operation_id"]
            or completed_operation.get("kind") != expected["kind"]
            or completed_operation.get("verified") is not True
        ):
            raise NativeBundleError(
                "native resume receipt completed operations are not a verified bundle prefix"
            )
    for expected_index, call in enumerate(calls, start=1):
        if not isinstance(call, Mapping) or call.get("index") != expected_index:
            raise NativeBundleError("native resume receipt call sequence is invalid")
    pending_operation_id = value.get("pending_operation_id")
    pending_tool = value.get("pending_tool")
    if (pending_operation_id is None) != (pending_tool is None):
        raise NativeBundleError("native resume receipt pending state is inconsistent")
    if pending_operation_id is not None:
        if len(completed) >= len(operations):
            raise NativeBundleError("native resume receipt has pending work after completion")
        pending_operation = operations[len(completed)]
        pending_execution_operation = execution_operations[len(completed)]
        if pending_operation_id != pending_operation["operation_id"]:
            raise NativeBundleError("native resume receipt pending operation is not next")
        reconciliable_comment = (
            pending_operation["kind"] == "comment" and pending_tool == "comment_create"
        )
        reconciliable_canvas_diagram = (
            pending_operation["kind"] == "diagram"
            and pending_execution_operation.get("native_transport") == "canvas_diagram"
            and pending_tool == "canvas_create_from_svg"
        )
        if not reconciliable_comment and not reconciliable_canvas_diagram:
            raise NativeBundleError(
                "native resume receipt requires manual reconciliation for an uncertain mutation"
            )
    return json.loads(json.dumps(value, ensure_ascii=False))


def _comment_id_for_content(comments: Sequence[Any], content: str) -> str | None:
    matches: list[str] = []
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        comment_id = comment.get("id")
        messages = comment.get("messages")
        if not isinstance(comment_id, str) or not isinstance(messages, list):
            continue
        if any(
            isinstance(message, Mapping) and message.get("content") == content
            for message in messages
        ):
            matches.append(comment_id)
    if len(matches) > 1:
        raise MiroToolError("Miro comment reconciliation found duplicate exact markers")
    return matches[0] if matches else None


def _tool_map(tool_catalogue: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in tool_catalogue:
        name = item.get("name")
        input_schema = item.get("input_schema")
        output_schema = item.get("output_schema")
        if not isinstance(name, str) or not isinstance(input_schema, Mapping):
            raise NativeBundleError("live Miro tool catalogue contains an invalid entry")
        if name in result:
            raise NativeBundleError("live Miro tool catalogue contains duplicate names")
        result[name] = {
            "input_schema": dict(input_schema),
            "output_schema": dict(output_schema) if isinstance(output_schema, Mapping) else None,
        }
    return result


def _validate_instance(instance: Any, schema: Mapping[str, Any], *, label: str) -> None:
    validator = Draft202012Validator(dict(schema))
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        raise NativeBundleError(f"{label} failed schema validation at {location}: {error.message}")


def _item_url(payload: Mapping[str, Any], tool_name: str) -> str:
    value = payload.get("miro_url")
    if not isinstance(value, str) or not value:
        raise MiroToolError(f"Miro tool {tool_name} did not return an item reference")
    return value


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _canvas_svg_source_matches(value: str, expected: str) -> bool:
    normalized_value = _normalized_text(value)
    normalized_expected = _normalized_text(expected)
    return normalized_value == normalized_expected or normalized_value == "\n" + normalized_expected


def _canvas_svg_evidence(
    svg: str,
    *,
    expected_title: str,
    expected_source: str,
    local_id: str | None,
    require_item_id: bool,
) -> dict[str, Any]:
    if not svg.strip() or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", svg, re.IGNORECASE):
        raise MiroToolError("Miro Canvas returned unsafe or empty diagram SVG")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise MiroToolError("Miro Canvas returned invalid diagram SVG") from exc
    if _xml_local_name(root.tag) != "svg":
        raise MiroToolError("Miro Canvas diagram readback is not SVG")

    scope = root
    if local_id is not None:
        local_matches = [element for element in root.iter() if element.get("id") == local_id]
        if len(local_matches) != 1:
            raise MiroToolError("Miro Canvas did not bind the submitted diagram id exactly once")
        scope = local_matches[0]
    diagrams = [
        element
        for element in scope.iter()
        if _xml_local_name(element.tag) == "foreignObject" and element.get("data-type") == "diagram"
    ]
    if len(diagrams) != 1:
        if local_id is not None:
            raise MiroToolError("Miro Canvas SVG lacks exactly one structured diagram")
        diagrams = [
            element for element in diagrams if element.get("data-title") == expected_title
        ]
        if len(diagrams) != 1:
            raise MiroToolError(
                "Miro Canvas SVG does not expose the expected structured diagram exactly once"
            )
    diagram = diagrams[0]
    title_matches = diagram.get("data-title") == expected_title
    if not title_matches:
        raise MiroToolError("Miro Canvas SVG diagram title does not match")
    try:
        width = float(diagram.get("width", ""))
        height = float(diagram.get("height", ""))
    except ValueError as exc:
        raise MiroToolError("Miro Canvas SVG diagram geometry is invalid") from exc
    geometry_matches = width == _CANVAS_DIAGRAM_WIDTH and height == _CANVAS_DIAGRAM_HEIGHT
    if not geometry_matches:
        raise MiroToolError("Miro Canvas SVG diagram geometry does not match")
    source = "".join(diagram.itertext())
    source_matches = _canvas_svg_source_matches(source, expected_source)
    if not source_matches:
        raise MiroToolError("Miro Canvas SVG diagram source does not match")

    item_ids = {
        value for element in scope.iter() if (value := element.get("data-miro-id")) is not None
    }
    if any(_CANVAS_ITEM_ID.fullmatch(item_id) is None for item_id in item_ids):
        raise MiroToolError("Miro Canvas returned an invalid diagram item id")
    if require_item_id and len(item_ids) != 1:
        raise MiroToolError("Miro Canvas did not return one diagram item id")
    return {
        "svg_digest": _text_digest(svg),
        "title_matches": title_matches,
        "diagram_semantics": True,
        "geometry_matches": geometry_matches,
        "source_matches": source_matches,
        "item_id": next(iter(item_ids)) if len(item_ids) == 1 else None,
    }


def _canvas_item_url(target_url: str, item_id: str) -> str:
    if _CANVAS_ITEM_ID.fullmatch(item_id) is None:
        raise MiroToolError("Miro Canvas diagram item id is invalid")
    parsed = urlsplit(target_url)
    value = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode({"moveToWidget": item_id}), "")
    )
    if _board_key(value) != _board_key(target_url):
        raise MiroToolError("Miro Canvas diagram item reference escaped the target board")
    return value


def _context_diagram_evidence(
    payload: Mapping[str, Any], *, expected_title: str, expected_source: str
) -> dict[str, Any]:
    titles: list[str] = []
    semantic_types: list[str] = []
    contents: list[str] = []
    scalar_count = 0

    def walk(value: Any, *, key: str | None = None, depth: int = 0) -> None:
        nonlocal scalar_count
        if depth > 12 or scalar_count > 10_000:
            raise MiroToolError("Miro diagram context readback exceeds the safety limit")
        if isinstance(value, Mapping):
            direct_source_match = any(
                str(nested_key).casefold() in {"content", "text", "description", "markdown"}
                and isinstance(nested, str)
                and _normalized_text(nested) == _normalized_text(expected_source)
                for nested_key, nested in value.items()
            )
            if direct_source_match:
                titles.extend(
                    nested.strip()
                    for nested_key, nested in value.items()
                    if str(nested_key).casefold() in {"title", "data-title", "name"}
                    and isinstance(nested, str)
                    and nested.strip()
                )
            for nested_key, nested in value.items():
                walk(nested, key=str(nested_key).casefold(), depth=depth + 1)
            return
        if isinstance(value, list):
            for nested in value:
                walk(nested, key=key, depth=depth + 1)
            return
        scalar_count += 1
        if not isinstance(value, str) or not value.strip():
            return
        if key in {"type", "data-type", "kind", "diagram_type", "notation"}:
            semantic_types.append(value.strip().casefold())
        elif key in {"content", "text", "description", "markdown"}:
            contents.append(value)

    walk(payload)
    title_matches = not titles or all(title == expected_title for title in titles)
    if not title_matches:
        raise MiroToolError("Miro Canvas diagram context title conflicts with the submitted title")
    source_matches = any(
        _normalized_text(content) == _normalized_text(expected_source) for content in contents
    )
    diagram_semantics = source_matches and (
        not semantic_types
        or any(value in {"diagram", "flowchart", "mermaid"} for value in semantic_types)
    )
    if not source_matches:
        raise MiroToolError("Miro Canvas diagram context does not match submitted Mermaid content")
    if not diagram_semantics:
        raise MiroToolError("Miro Canvas diagram context lacks diagram semantics")
    return {
        "context_digest": _digest(dict(payload)),
        "title_exposed": bool(titles),
        "title_matches": title_matches,
        "diagram_semantics": diagram_semantics,
        "source_matches": source_matches,
        "content_present": bool(contents or titles),
    }


def _canvas_inventory_item_url(
    item: Mapping[str, Any], *, target_url: str
) -> tuple[str, str] | None:
    item_id = item.get("id")
    item_url = item.get("miro_url")
    if not isinstance(item_id, str) or _CANVAS_ITEM_ID.fullmatch(item_id) is None:
        return None
    if not isinstance(item_url, str):
        return None
    try:
        if _board_key(item_url) != _board_key(target_url):
            return None
    except NativeBundleError:
        return None
    parsed = urlsplit(item_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.fragment or query.get("moveToWidget") != [item_id]:
        return None
    return item_id, _canvas_item_url(target_url, item_id)


def _canvas_number_matches(value: Any, expected: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
        and not isinstance(expected, bool)
        and isinstance(expected, int | float)
        and math.isfinite(expected)
        and value == expected
    )


def _canvas_inventory_source_matches(value: Any, expected: str) -> bool:
    if not isinstance(value, str):
        return False
    return value == expected or (expected.endswith("\n") and value == expected[:-1])


def _canvas_inventory_candidate(
    items: Sequence[Any],
    *,
    operation: Mapping[str, Any],
    target_url: str,
    verified_reference_digests: set[str],
) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, Mapping) or item.get("type") != "diagram":
            continue
        data = item.get("data")
        geometry = item.get("geometry")
        position = item.get("position")
        if (
            not isinstance(data, Mapping)
            or data.get("title") != operation["title"]
            or not _canvas_inventory_source_matches(
                data.get("code"), operation["canvas_mermaid_source"]
            )
            or not isinstance(geometry, Mapping)
            or not _canvas_number_matches(geometry.get("width"), _CANVAS_DIAGRAM_WIDTH)
            or not _canvas_number_matches(geometry.get("height"), _CANVAS_DIAGRAM_HEIGHT)
            or not isinstance(position, Mapping)
            or not _canvas_number_matches(position.get("x"), operation.get("x", 0))
            or not _canvas_number_matches(position.get("y"), operation.get("y", 0))
        ):
            continue
        reference = _canvas_inventory_item_url(item, target_url=target_url)
        if reference is None:
            continue
        _item_id, item_url = reference
        if _text_digest(item_url)[:24] in verified_reference_digests:
            continue
        matches.append(
            (
                item_url,
                {
                    "item_type_matches": True,
                    "title_matches": True,
                    "source_matches": True,
                    "geometry_matches": True,
                    "position_matches": True,
                    "item_reference_verified": True,
                },
            )
        )
    if not matches:
        raise MiroToolError("uncertain Miro Canvas diagram mutation has no exact candidate")
    if len(matches) != 1:
        raise MiroToolError("uncertain Miro Canvas diagram mutation has multiple exact candidates")
    return matches[0]


def _canvas_skill_text(payload: Mapping[str, Any], *, keys: tuple[str, ...], label: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise MiroToolError(f"Miro Canvas {label} skill is empty")


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MiroToolError(f"Miro payload contains an invalid {key}")
    return value


def _list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise MiroToolError(f"Miro payload contains an invalid {key}")
    return value


def _inventory_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    key = "items" if isinstance(payload.get("items"), list) else "data"
    items = _list(payload, key)
    types: dict[str, int] = {}
    fingerprints: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise MiroToolError("Miro board inventory contains an invalid item")
        item_type = item.get("type") if isinstance(item.get("type"), str) else "unknown"
        types[item_type] = types.get(item_type, 0) + 1
        fingerprints.append(_digest(dict(item)))
    return {
        "item_count": len(items),
        "item_types": dict(sorted(types.items())),
        "inventory_digest": _digest(sorted(fingerprints)),
    }


def _value_tokens(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    tokens: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            selected: Any = None
            for key in ("displayValue", "content", "value", "email", "name", "id"):
                if key in item:
                    selected = item[key]
                    break
            item = dict(item) if selected is None else selected
        tokens.append(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return tuple(sorted(tokens))


def _expected_row_cells(
    row: Mapping[str, Any], column_types: Mapping[str, str]
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for cell in row["cells"]:
        title = cell["columnTitle"]
        if title not in column_types:
            raise NativeBundleError("table row references an unknown column")
        result[title] = _value_tokens(cell["value"])
    return result


def _returned_row_cells(
    row: Mapping[str, Any], column_types: Mapping[str, str]
) -> dict[str, tuple[str, ...]]:
    cells = row.get("cells")
    if not isinstance(cells, list):
        raise MiroToolError("Miro table readback contains an invalid row")
    result: dict[str, tuple[str, ...]] = {}
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise MiroToolError("Miro table readback contains an invalid cell")
        title = cell.get("columnTitle")
        if not isinstance(title, str) or title not in column_types:
            continue
        if isinstance(cell.get("options"), list):
            value = cell["options"]
        elif "content" in cell:
            value = cell["content"]
        else:
            raise MiroToolError("Miro table readback cell lacks content")
        result[title] = _value_tokens(value)
    return result


def _verify_submitted_rows(
    submitted: Sequence[Mapping[str, Any]],
    returned: Sequence[Any],
    columns: Sequence[Mapping[str, Any]],
) -> None:
    column_types = {column["column_title"]: column["column_type"] for column in columns}
    available: list[dict[str, tuple[str, ...]]] = []
    for row in returned:
        if not isinstance(row, Mapping):
            raise MiroToolError("Miro table readback contains an invalid row")
        available.append(_returned_row_cells(row, column_types))
    for submitted_row in submitted:
        expected = _expected_row_cells(submitted_row, column_types)
        match_index = next(
            (
                index
                for index, candidate in enumerate(available)
                if all(candidate.get(title) == value for title, value in expected.items())
            ),
            None,
        )
        if match_index is None:
            raise MiroToolError("Miro table readback does not contain a submitted row")
        available.pop(match_index)


def _context_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    items = _list(payload, "items")
    types: dict[str, int] = {}
    fingerprints: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise MiroToolError("Miro context inventory contains an invalid item")
        item_type = item.get("type") if isinstance(item.get("type"), str) else "unknown"
        types[item_type] = types.get(item_type, 0) + 1
        fingerprints.append(_digest(dict(item)))
    return {
        "item_count": len(items),
        "item_types": dict(sorted(types.items())),
        "context_digest": _digest(sorted(fingerprints)),
    }


def _base_arguments(target_url: str, extra: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "miro_url": target_url,
        "invocation_source": "schauwerk-miro-native-executor",
        "is_repository": True,
    }
    value.update({key: item for key, item in extra.items() if item is not None})
    return value


def _operation_position(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {key: operation[key] for key in ("x", "y") if key in operation}


def _expected_deleted_item_count(completed: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for operation in completed if operation.get("kind") == "code_widget_delete")


def _expected_net_item_delta(completed: Sequence[Mapping[str, Any]]) -> int:
    return _expected_created_item_count(completed) - _expected_deleted_item_count(completed)


def _verify_code_widget_fields(
    widget: Mapping[str, Any], expected: Mapping[str, Any], *, label: str
) -> None:
    for key, value in expected.items():
        returned = widget.get(key)
        if key in {"width", "x", "y"}:
            if not isinstance(returned, int | float) or abs(float(returned) - float(value)) > 0.01:
                raise MiroToolError(f"Miro code-widget {label} {key} does not match")
        elif returned != value:
            raise MiroToolError(f"Miro code-widget {label} {key} does not match")


def _widget_reference_set(items: Sequence[Any]) -> set[str]:
    references: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise MiroToolError("Miro code-widget inventory contains an invalid item")
        reference = item.get("miro_url")
        if not isinstance(reference, str) or not reference:
            raise MiroToolError("Miro code-widget inventory lacks an item reference")
        if reference in references:
            raise MiroToolError("Miro code-widget inventory contains duplicate item references")
        references.add(reference)
    return references


def _local_html_references(content: str) -> tuple[str, ...]:
    candidates: list[str] = []
    patterns = (
        r"""(?:src|href)\s*=\s*["']([^"']+)["']""",
        r"""url\(\s*["']?([^"')]+)""",
        r"""srcset\s*=\s*["']([^"']+)["']""",
    )
    for pattern in patterns:
        for match in re.findall(pattern, content, flags=re.IGNORECASE):
            values = [part.strip().split()[0] for part in match.split(",")]
            for value in values:
                lowered = value.lower()
                if not value or lowered.startswith(
                    ("http://", "https://", "data:", "#", "mailto:", "tel:")
                ):
                    continue
                candidates.append(value)
    return tuple(sorted(set(candidates)))


def _load_prototype_screens(
    operation: Mapping[str, Any], *, bundle_root: Path | None
) -> tuple[list[bytes], list[str]]:
    if bundle_root is None:
        raise NativeBundleError("prototype execution requires a bundle source directory")
    root = bundle_root.expanduser().absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise NativeBundleError("prototype bundle source directory is unsafe")
    payloads: list[bytes] = []
    digests: list[str] = []
    seen_paths: set[str] = set()
    for screen in operation["screens"]:
        relative = Path(screen["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise NativeBundleError("prototype screen paths must stay below the bundle directory")
        normalized = relative.as_posix()
        if normalized in seen_paths:
            raise NativeBundleError("prototype screen paths must be unique")
        seen_paths.add(normalized)
        candidate = _safe_input_path(root / relative, label="prototype screen")
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise NativeBundleError("prototype screen path escapes the bundle directory") from exc
        payload = candidate.read_bytes()
        if len(payload) > 1_048_576:
            raise NativeBundleError("prototype screen exceeds the 1 MiB provider limit")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != screen["sha256"]:
            raise NativeBundleError("prototype screen SHA-256 does not match the bundle")
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NativeBundleError("prototype screens must be UTF-8 HTML") from exc
        if re.search(r"<\s*script\b", content, flags=re.IGNORECASE) or re.search(
            r"\son[a-z0-9_-]+\s*=", content, flags=re.IGNORECASE
        ):
            raise NativeBundleError(
                "prototype screens must be static HTML without scripts or inline event handlers"
            )
        local_refs = _local_html_references(content)
        if local_refs:
            raise NativeBundleError(
                "prototype screen contains local asset references without image-token authority: "
                + ", ".join(local_refs[:5])
            )
        payloads.append(payload)
        digests.append(digest)
    return payloads, digests


def _layout_dsl_connector_count(value: str, *, label: str) -> int:
    if not isinstance(value, str) or not value.strip():
        raise MiroToolError(f"{label} is empty")
    try:
        return summarize_layout_dsl(value).count("CONNECTOR")
    except LayoutDslParseError as exc:
        raise MiroToolError(f"{label} contains invalid connector syntax: {exc}") from exc


@dataclass(frozen=True)
class ConnectorEvidence:
    """Operation-local connector counts derived from cumulative board readback."""

    declared_count: int
    result_dsl_count: int
    layout_read_before_count: int
    layout_read_after_count: int
    board_dsl_before_count: int
    board_dsl_after_count: int
    created_count: int

    @classmethod
    def from_live(
        cls,
        *,
        declared_count: int,
        result_dsl_count: int,
        layout_read_before_count: int,
        layout_read_after_count: int,
        board_dsl_before_count: int,
        board_dsl_after_count: int,
    ) -> ConnectorEvidence:
        values = {
            "declared_count": declared_count,
            "result_dsl_count": result_dsl_count,
            "layout_read_before_count": layout_read_before_count,
            "layout_read_after_count": layout_read_after_count,
            "board_dsl_before_count": board_dsl_before_count,
            "board_dsl_after_count": board_dsl_after_count,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MiroToolError(f"layout connector evidence has an invalid {name}")
        if layout_read_before_count != board_dsl_before_count:
            raise MiroToolError("Miro layout connector evidence is inconsistent before creation")
        if layout_read_after_count != board_dsl_after_count:
            raise MiroToolError("Miro layout connector evidence is inconsistent after creation")
        if layout_read_after_count < layout_read_before_count:
            raise MiroToolError("Miro layout connector count decreased during creation")
        if result_dsl_count != layout_read_after_count:
            raise MiroToolError(
                "Miro layout result connector count does not match the post-create board state"
            )
        created_count = layout_read_after_count - layout_read_before_count
        if created_count < declared_count:
            raise MiroToolError(
                "Miro layout readback contains fewer newly created connectors than declared"
            )
        return cls(created_count=created_count, **values)

    @classmethod
    def from_receipt(cls, value: Any) -> ConnectorEvidence:
        if not isinstance(value, Mapping) or value.get("verified") is not True:
            raise MiroToolError("layout receipt lacks verified connector evidence")
        declared = value.get("declared_count")
        result = value.get("result_dsl_count")
        if "layout_read_before_count" in value or "layout_read_after_count" in value:
            before = value.get("layout_read_before_count")
            after = value.get("layout_read_after_count")
            board_before = value.get("board_dsl_before_count")
            board_after = value.get("board_dsl_after_count")
        else:
            # v1 receipts recorded an operation-local count without cumulative baselines.
            before = 0
            after = value.get("layout_read_count")
            board_before = 0
            board_after = value.get("board_dsl_count")
        evidence = cls.from_live(
            declared_count=declared,
            result_dsl_count=result,
            layout_read_before_count=before,
            layout_read_after_count=after,
            board_dsl_before_count=board_before,
            board_dsl_after_count=board_after,
        )
        recorded_created = value.get("created_count", evidence.created_count)
        if (
            isinstance(recorded_created, bool)
            or not isinstance(recorded_created, int)
            or recorded_created != evidence.created_count
        ):
            raise MiroToolError("layout receipt has an invalid created connector count")
        return evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "declared_count": self.declared_count,
            "result_dsl_count": self.result_dsl_count,
            # Preserve the v1 cumulative post-create meanings for old readers.
            "layout_read_count": self.layout_read_after_count,
            "board_dsl_count": self.board_dsl_after_count,
            "layout_read_before_count": self.layout_read_before_count,
            "layout_read_after_count": self.layout_read_after_count,
            "board_dsl_before_count": self.board_dsl_before_count,
            "board_dsl_after_count": self.board_dsl_after_count,
            "created_count": self.created_count,
            "verified": True,
        }


def _expected_created_item_count(completed: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for operation in completed:
        kind = operation.get("kind")
        readback = operation.get("readback")
        if not isinstance(readback, Mapping):
            raise MiroToolError("native operation receipt lacks readback evidence")
        if kind == "layout":
            created_count = readback.get("created_count")
            if isinstance(created_count, bool) or not isinstance(created_count, int):
                raise MiroToolError("layout receipt lacks a valid created count")
            total += created_count
        elif kind in {"diagram", "document", "table", "code_widget", "prototype"}:
            total += 1
        elif kind not in {
            "comment",
            "document_update",
            "table_history",
            "code_widget_inventory",
            "code_widget_update",
            "code_widget_delete",
        }:
            raise MiroToolError("native operation receipt contains an unknown kind")
    return total


def _layout_receipt_connector_count(operation: Mapping[str, Any]) -> int:
    if operation.get("kind") != "layout":
        return 0
    readback = operation.get("readback")
    if not isinstance(readback, Mapping):
        raise MiroToolError("layout receipt lacks readback evidence")
    evidence = ConnectorEvidence.from_receipt(readback.get("connector_evidence"))
    created = readback.get("created_count")
    if (
        isinstance(created, bool)
        or not isinstance(created, int)
        or created < evidence.created_count
    ):
        raise MiroToolError("layout receipt connector count exceeds its created count")
    return evidence.created_count


def _expected_inventory_visible_created_item_count(
    completed: Sequence[Mapping[str, Any]],
) -> int:
    connector_count = sum(
        _layout_receipt_connector_count(operation)
        for operation in completed
        if operation.get("kind") == "layout"
    )
    return _expected_created_item_count(completed) - connector_count


def _expected_inventory_visible_net_item_delta(
    completed: Sequence[Mapping[str, Any]],
) -> int:
    return _expected_inventory_visible_created_item_count(completed) - _expected_deleted_item_count(
        completed
    )


def _connector_evidence_summary(completed: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    layouts = [operation for operation in completed if operation.get("kind") == "layout"]
    evidence = [
        ConnectorEvidence.from_receipt(operation["readback"].get("connector_evidence"))
        for operation in layouts
        if isinstance(operation.get("readback"), Mapping)
    ]
    if len(evidence) != len(layouts):
        raise MiroToolError("layout receipt lacks readback evidence")
    return {
        "layout_operation_count": len(layouts),
        "layout_read_verified_operation_count": len(evidence),
        "layout_operations_with_connectors": sum(item.created_count > 0 for item in evidence),
        "declared_connector_count": sum(item.declared_count for item in evidence),
        "provider_created_connector_count": sum(item.created_count for item in evidence),
        "board_inventory_connector_visibility": "not_assumed",
    }


def _provider_preview_summary(
    completed: Sequence[Mapping[str, Any]], *, live_poll_supported: bool
) -> dict[str, Any]:
    evidence = [
        operation["readback"]["provider_preview"]
        for operation in completed
        if isinstance(operation.get("readback"), Mapping)
        and isinstance(operation["readback"].get("provider_preview"), Mapping)
    ]
    status_counts: dict[str, int] = {}
    for item in evidence:
        status = item.get("status")
        if isinstance(status, str):
            status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "live_poll_supported": live_poll_supported,
        "create_operation_count": len(evidence),
        "resource_offered_operation_count": sum(
            item.get("resource_count", 0) > 0 for item in evidence
        ),
        "ready_operation_count": status_counts.get("ready", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "supplemental_only": True,
        "authenticated_provider_capture_still_required": True,
        "automatic_aesthetic_verdict": False,
    }


def _operation_receipt(
    operation: Mapping[str, Any],
    *,
    item_url: str | None,
    readback: Mapping[str, Any],
    call_indexes: Sequence[int],
) -> dict[str, Any]:
    return {
        "operation_id": operation["operation_id"],
        "kind": operation["kind"],
        "item_reference_digest": _text_digest(item_url)[:24] if item_url else None,
        "readback": dict(readback),
        "call_indexes": list(call_indexes),
        "verified": True,
    }


async def execute_native_bundle(
    *,
    call_tool: ToolCaller,
    tool_catalogue: Sequence[Mapping[str, Any]],
    board_alias: str,
    board_url: str,
    bundle: Mapping[str, Any],
    checkpoint: CheckpointWriter | None = None,
    resume_receipt: Mapping[str, Any] | None = None,
    bundle_root: Path | None = None,
    upload_html: HtmlUploader | None = None,
) -> dict[str, Any]:
    """Apply one validated bundle sequentially and checkpoint sanitized evidence."""

    validated = validate_native_bundle(bundle)
    schemas = _tool_map(tool_catalogue)
    provider_resolution = resolve_bundle_operations(validated["operations"], set(schemas))
    if provider_resolution["blocked_count"]:
        missing = ", ".join(provider_resolution["blocked_tools"]) or "unknown tools"
        raise NativeBundleError(f"live Miro catalogue lacks required tools: {missing}")
    execution_operations: list[dict[str, Any]] = []
    for unresolved in provider_resolution["execution_operations"]:
        operation = dict(unresolved)
        if operation.get("native_transport") == "canvas_diagram":
            for skill_tool in (
                "canvas_get_canvas_composer_skill",
                "canvas_load_format_skill",
            ):
                if schemas[skill_tool]["output_schema"] is None:
                    raise NativeBundleError(
                        f"live Miro catalogue lacks an output schema for {skill_tool}"
                    )
            mermaid_source = compile_diagram_dsl_to_mermaid(operation["diagram_dsl"])
            operation["canvas_mermaid_source"] = mermaid_source
            operation["canvas_svg"] = render_canvas_diagram_svg(operation, mermaid_source)
            operation["canvas_local_id"] = _diagram_reference(
                operation["operation_id"], prefix="canvas"
            )
        execution_operations.append(operation)
    required = required_tools({"operations": execution_operations})
    missing = sorted(set(required) - set(schemas))
    if missing:
        raise NativeBundleError(f"live Miro catalogue lacks resolved tools: {', '.join(missing)}")
    _board_key(board_url)
    resume = (
        _validate_resume_receipt(
            resume_receipt,
            bundle=validated,
            execution_operations=execution_operations,
            board_alias=board_alias,
            board_url=board_url,
            provider_resolution_digest=provider_resolution["resolution_digest"],
            provider_fallback_count=provider_resolution["fallback_count"],
        )
        if resume_receipt is not None
        else None
    )
    calls: list[dict[str, Any]] = list(resume.get("calls", [])) if resume else []
    completed: list[dict[str, Any]] = list(resume.get("completed_operations", [])) if resume else []
    preview_resources_by_call_index: dict[int, tuple[str, ...]] = {}
    original_preflight = resume.get("preflight") if resume else None
    before_inventory: dict[str, Any] | None = None
    before_context: dict[str, Any] | None = None
    after_inventory: dict[str, Any] | None = None
    after_context: dict[str, Any] | None = None
    mutation_started = bool(completed) or bool(resume and resume.get("mutation_attempted"))
    current_operation_id: str | None = None
    pending_operation_id: str | None = resume.get("pending_operation_id") if resume else None
    pending_tool: str | None = resume.get("pending_tool") if resume else None
    canvas_skill_evidence: dict[str, Any] | None = None

    async def invoke(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        schema = schemas[tool_name]
        _validate_instance(arguments, schema["input_schema"], label=f"{tool_name} input")
        result = await call_tool(tool_name, arguments)
        payload = checked_payload(result, tool_name)
        output_schema = schema.get("output_schema")
        if output_schema is not None:
            _validate_instance(payload, output_schema, label=f"{tool_name} output")
        call_index = len(calls) + 1
        preview_resources = tuple(
            sorted(
                {
                    uri
                    for uri in result_resource_links(result)
                    if _MIRO_PREVIEW_RESOURCE_RE.fullmatch(uri)
                }
            )
        )
        if preview_resources:
            preview_resources_by_call_index[call_index] = preview_resources
        calls.append(
            {
                "index": call_index,
                "tool": tool_name,
                "input_digest": _digest(arguments),
                "output_digest": _digest(payload),
                "preview_resource_count": len(preview_resources),
                "preview_resource_digests": [_text_digest(uri)[:24] for uri in preview_resources],
            }
        )
        return payload

    async def load_canvas_skills_once() -> dict[str, Any]:
        nonlocal canvas_skill_evidence
        if canvas_skill_evidence is not None:
            return canvas_skill_evidence
        metadata = {
            "invocation_source": "schauwerk-miro-native-executor",
            "is_repository": True,
        }
        composer_payload = await invoke("canvas_get_canvas_composer_skill", metadata)
        composer = _canvas_skill_text(
            composer_payload,
            keys=("skill", "canvas_composer_skill"),
            label="composer",
        )
        flowchart_payload = await invoke(
            "canvas_load_format_skill",
            {
                **metadata,
                "format_name": "diagramming",
                "notation": "flowchart",
            },
        )
        flowchart = _canvas_skill_text(
            flowchart_payload,
            keys=("skill", "format_skill"),
            label="flowchart format",
        )
        canvas_skill_evidence = {
            "composer_skill_digest": _text_digest(composer),
            "flowchart_skill_digest": _text_digest(flowchart),
            "skills_loaded": True,
            "skills_schema_validated": True,
        }
        return canvas_skill_evidence

    async def provider_preview_evidence(call_index: int) -> dict[str, Any]:
        resources = preview_resources_by_call_index.get(call_index, ())
        evidence: dict[str, Any] = {
            "resource_count": len(resources),
            "resource_digests": [_text_digest(uri)[:24] for uri in resources],
            "poll_attempted": False,
            "poll_attempt_count": 0,
            "poll_call_recorded": False,
            "supplemental_only": True,
            "authenticated_provider_capture_required": True,
            "automatic_aesthetic_verdict": False,
        }
        if not resources:
            return {**evidence, "status": "not_offered"}
        if len(resources) != 1:
            return {**evidence, "status": "ambiguous_resource_set"}
        if "preview_resource_poll" not in schemas:
            return {**evidence, "status": "poll_tool_unavailable"}
        evidence = {**evidence, "poll_attempted": True, "poll_attempt_count": 1}
        try:
            preview = await invoke(
                "preview_resource_poll",
                {
                    "preview_resource": resources[0],
                    "is_repository": True,
                    "invocation_source": "schauwerk-miro-native-executor",
                },
            )
        except Exception:
            # Supplemental evidence must never turn an otherwise verified mutation into failure.
            return {**evidence, "status": "poll_error"}
        evidence = {**evidence, "poll_call_recorded": True}
        status = preview.get("status")
        if status in {"pending", "failed"}:
            return {**evidence, "status": status}
        if status != "ready":
            return {**evidence, "status": "invalid_status"}
        mime_type = preview.get("mime_type")
        encoded = preview.get("data_base64")
        if mime_type not in _PROVIDER_PREVIEW_MIME_TYPES or not isinstance(encoded, str):
            return {**evidence, "status": "invalid_ready_payload"}
        if len(encoded) > ((_MAX_PROVIDER_PREVIEW_BYTES * 4) // 3) + 8:
            return {**evidence, "status": "preview_too_large", "mime_type": mime_type}
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError, TypeError):
            return {**evidence, "status": "invalid_ready_payload", "mime_type": mime_type}
        if len(content) > _MAX_PROVIDER_PREVIEW_BYTES:
            return {**evidence, "status": "preview_too_large", "mime_type": mime_type}
        return {
            **evidence,
            "status": "ready",
            "mime_type": mime_type,
            "byte_count": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
        }

    async def read_layout_state(
        target_url: str, *, label: str, allow_empty: bool
    ) -> dict[str, Any]:
        layout = await invoke(
            "layout_read",
            _base_arguments(target_url, {"mode": "full"}),
        )
        board_dsl = layout.get("dsl")
        if layout.get("success") is not True or not isinstance(board_dsl, str):
            raise MiroToolError(f"{label} is invalid")
        item_count = _integer(layout, "item_count")
        connector_count = _integer(layout, "connector_count")
        skipped_count = _integer(layout, "skipped_count")
        if not board_dsl.strip():
            if not allow_empty or item_count != 0 or connector_count != 0:
                raise MiroToolError(f"{label} is empty or inconsistent")
            board_dsl_connector_count = 0
        else:
            if item_count < 1:
                raise MiroToolError(f"{label} has DSL but no items")
            board_dsl_connector_count = _layout_dsl_connector_count(board_dsl, label=f"{label} DSL")
        if connector_count != board_dsl_connector_count:
            raise MiroToolError(f"{label} connector evidence is inconsistent")
        return {
            "dsl": board_dsl,
            "dsl_digest": _text_digest(board_dsl),
            "item_count": item_count,
            "connector_count": connector_count,
            "board_dsl_connector_count": board_dsl_connector_count,
            "skipped_count": skipped_count,
        }

    async def read_complete_inventory() -> tuple[dict[str, Any], list[Any]]:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        items: list[Any] = []
        reported_total: int | None = None
        page_count = 0
        while True:
            arguments: dict[str, Any] = {"limit": 1000}
            if cursor is not None:
                arguments["cursor"] = cursor
            payload = await invoke(
                "board_list_items",
                _base_arguments(board_url, arguments),
            )
            page_count += 1
            if page_count > 20:
                raise MiroToolError("Miro board inventory exceeds the 20-page safety limit")
            page = _list(payload, "data")
            total = _integer(payload, "total")
            if reported_total is None:
                reported_total = total
            elif reported_total != total:
                raise MiroToolError("Miro board inventory total changed during pagination")
            items.extend(page)
            has_more = payload.get("has_more")
            if not isinstance(has_more, bool):
                raise MiroToolError("Miro board inventory has invalid pagination state")
            next_cursor = payload.get("nextCursor")
            if not has_more:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise MiroToolError("Miro board inventory lacks a continuation cursor")
            if next_cursor in seen_cursors:
                raise MiroToolError("Miro board inventory repeated a continuation cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        if reported_total != len(items):
            raise MiroToolError("Miro board inventory pagination is incomplete")
        summary = _inventory_summary({"items": items})
        summary["page_count"] = page_count
        return summary, items

    async def read_all_table_rows(target_url: str, *, expected_count: int) -> tuple[list[Any], int]:
        rows: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        reported_total: int | None = None
        limit = max(1, min(500, expected_count or 500))
        for _page in range(20):
            arguments: dict[str, Any] = {"limit": limit}
            if cursor is not None:
                arguments["next_cursor"] = cursor
            payload = await invoke(
                "table_list_rows",
                _base_arguments(target_url, arguments),
            )
            page = _list(payload, "rows")
            total = _integer(payload, "total")
            if reported_total is None:
                reported_total = total
                if total > 10000:
                    raise MiroToolError("Miro table readback exceeds the safety limit")
            elif reported_total != total:
                raise MiroToolError("Miro table total changed during pagination")
            rows.extend(page)
            next_cursor = payload.get("cursor")
            if next_cursor is None:
                if len(rows) != total:
                    raise MiroToolError("Miro table pagination ended before the reported total")
                return rows, total
            if not isinstance(next_cursor, str) or not next_cursor:
                raise MiroToolError("Miro table pagination cursor is invalid")
            if next_cursor in seen_cursors:
                raise MiroToolError("Miro table pagination repeated a cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise MiroToolError("Miro table readback exceeds the 20-page safety limit")

    async def read_all_code_widgets(target_url: str) -> tuple[list[Any], int, int]:
        items: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        reported_total: int | None = None
        for page_count in range(1, 21):
            arguments: dict[str, Any] = {"limit": 50}
            if cursor is not None:
                arguments["cursor"] = cursor
            payload = await invoke(
                "code_widget_list_items",
                _base_arguments(target_url, arguments),
            )
            if payload.get("success") is not True:
                raise MiroToolError("Miro code-widget inventory failed")
            page = _list(payload, "items")
            total_value = payload.get("total")
            if total_value is not None:
                if (
                    isinstance(total_value, bool)
                    or not isinstance(total_value, int)
                    or total_value < 0
                ):
                    raise MiroToolError("Miro code-widget inventory total is invalid")
                if reported_total is None:
                    reported_total = total_value
                    if total_value > 1000:
                        raise MiroToolError("Miro code-widget inventory exceeds the safety limit")
                elif reported_total != total_value:
                    raise MiroToolError(
                        "Miro code-widget inventory total changed during pagination"
                    )
            items.extend(page)
            next_cursor = payload.get("cursor")
            if next_cursor is None:
                total = len(items) if reported_total is None else reported_total
                if len(items) != total:
                    raise MiroToolError("Miro code-widget pagination is incomplete")
                _widget_reference_set(items)
                return items, total, page_count
            if not isinstance(next_cursor, str) or not next_cursor:
                raise MiroToolError("Miro code-widget pagination cursor is invalid")
            if next_cursor in seen_cursors:
                raise MiroToolError("Miro code-widget pagination repeated a cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise MiroToolError("Miro code-widget inventory exceeds the 20-page safety limit")

    async def read_all_comments(target_url: str) -> list[Any]:
        comments: list[Any] = []
        offset = 0
        reported_total: int | None = None
        for _page in range(20):
            payload = await invoke(
                "comment_list_comments",
                _base_arguments(target_url, {"limit": 50, "offset": offset}),
            )
            page = _list(payload, "data")
            total = _integer(payload, "total")
            returned_offset = _integer(payload, "offset")
            returned_limit = _integer(payload, "limit")
            if returned_offset != offset or returned_limit < 1 or returned_limit > 50:
                raise MiroToolError("Miro comment pagination state is invalid")
            if reported_total is None:
                reported_total = total
                if total > 1000:
                    raise MiroToolError("Miro comment reconciliation exceeds the safety limit")
            elif reported_total != total:
                raise MiroToolError("Miro comment total changed during pagination")
            comments.extend(page)
            if len(comments) >= total:
                if len(comments) != total:
                    raise MiroToolError("Miro comment pagination returned too many entries")
                return comments
            if not page:
                raise MiroToolError("Miro comment pagination ended before the reported total")
            offset += len(page)
        raise MiroToolError("Miro comment reconciliation exceeds the 20-page safety limit")

    def build_receipt(
        *, success: bool, failed_operation_id: str | None = None, error_code: str | None = None
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema_version": NATIVE_RECEIPT_SCHEMA,
            "success": success,
            "bundle_id": validated["bundle_id"],
            "bundle_digest": validated["bundle_digest"],
            "board_alias": board_alias,
            "board_reference_digest": _text_digest(board_url)[:24],
            "required_tools": list(required),
            "live_tool_count": len(schemas),
            "provider_resolution_digest": provider_resolution["resolution_digest"],
            "provider_resolution": provider_resolution["operation_resolutions"],
            "provider_fallback_count": provider_resolution["fallback_count"],
            "operation_count": len(validated["operations"]),
            "completed_operation_count": len(completed),
            "completed_operations": list(completed),
            "failed_operation_id": failed_operation_id,
            "error_code": error_code,
            "execution_state": (
                "complete"
                if success
                else "in_progress"
                if error_code == "in_progress"
                else "failed"
            ),
            "mutation_attempted": mutation_started,
            "partial_mutation": (not success and error_code != "in_progress" and mutation_started),
            "atomic": False,
            "call_count": len(calls),
            "calls": list(calls),
            "preflight": original_preflight
            or {
                "inventory": before_inventory,
                "context": before_context,
            },
            "resume_preflight": (
                {
                    "inventory": before_inventory,
                    "context": before_context,
                }
                if resume is not None
                else None
            ),
            "resumed_from_execution_digest": (
                resume.get("execution_digest") if resume is not None else None
            ),
            "resume_completed_operation_count": (
                len(resume.get("completed_operations", [])) if resume is not None else 0
            ),
            "pending_operation_id": pending_operation_id,
            "pending_tool": pending_tool,
            "postflight": {
                "inventory": after_inventory,
                "context": after_context,
            },
            "provider_created_item_count": _expected_created_item_count(completed),
            "board_inventory_visible_created_item_count": (
                _expected_inventory_visible_created_item_count(completed)
            ),
            "connector_evidence": _connector_evidence_summary(completed),
            "provider_preview_evidence": _provider_preview_summary(
                completed, live_poll_supported="preview_resource_poll" in schemas
            ),
            "expected_created_item_count": _expected_created_item_count(completed),
            "expected_deleted_item_count": _expected_deleted_item_count(completed),
            "expected_net_item_count_delta": _expected_net_item_delta(completed),
            "expected_board_inventory_item_count_delta": (
                _expected_inventory_visible_net_item_delta(completed)
            ),
            "observed_item_count_delta": (
                after_inventory["item_count"]
                - (original_preflight or {"inventory": before_inventory})["inventory"]["item_count"]
                if after_inventory is not None
                and (original_preflight or {"inventory": before_inventory}).get("inventory")
                is not None
                else None
            ),
            "observed_board_inventory_item_count_delta": (
                after_inventory["item_count"]
                - (original_preflight or {"inventory": before_inventory})["inventory"]["item_count"]
                if after_inventory is not None
                and (original_preflight or {"inventory": before_inventory}).get("inventory")
                is not None
                else None
            ),
            "visual_acceptance": {
                "authenticated_provider_capture_required": True,
                "status": "pending_authenticated_provider_capture",
                "automatic_aesthetic_verdict": False,
            },
            "truth_boundary": {
                "provider_operations_are_sequential": True,
                "rollback_available_for_all_item_types": False,
                "receipt_contains_provider_content": False,
                "visual_quality_proven": False,
                "provider_fallbacks_are_creation_only": True,
                "provider_fallbacks_preserve_native_item_type": False,
            },
        }
        receipt["execution_digest"] = _digest(receipt)
        return receipt

    try:
        identity = await invoke("user_who_am_i", {"is_repository": True})
        identity_fields = ("org_id", "team_id", "user_id", "workspace_id")
        if any(not identity.get(field) for field in identity_fields):
            raise MiroToolError("Miro identity readback is incomplete")
        before_inventory, before_inventory_items = await read_complete_inventory()
        before_context = _context_summary(
            await invoke("context_explore", _base_arguments(board_url, {}))
        )
        if resume is not None:
            baseline_inventory = resume["preflight"]["inventory"]
            resume_item_delta = before_inventory["item_count"] - baseline_inventory["item_count"]
            expected_resume_delta = _expected_inventory_visible_net_item_delta(completed)
            if resume_item_delta < expected_resume_delta:
                raise MiroToolError(
                    "Miro board inventory does not expose the verified resume prefix"
                )
            if resume.get("pending_tool") == "canvas_create_from_svg" and resume_item_delta != (
                expected_resume_delta + 1
            ):
                raise MiroToolError(
                    "uncertain Miro Canvas diagram mutation has an unexpected inventory delta"
                )

        start_operation_index = len(completed)
        if any(
            operation.get("native_transport") == "canvas_diagram"
            for operation in execution_operations[start_operation_index:]
        ):
            await load_canvas_skills_once()
        for original_operation, operation in zip(
            validated["operations"][start_operation_index:],
            execution_operations[start_operation_index:],
            strict=True,
        ):
            current_operation_id = original_operation["operation_id"]
            start_index = len(calls) + 1
            kind = operation["kind"]
            target_url = _target_url(board_url, operation)
            item_url: str | None = None
            readback: dict[str, Any]
            preview_call_index: int | None = None

            if kind == "layout":
                contract = await invoke(
                    "layout_get_dsl",
                    {
                        "invocation_source": "schauwerk-miro-native-executor",
                        "is_repository": True,
                    },
                )
                spec = contract.get("spec")
                example = contract.get("example")
                if not isinstance(spec, str) or not spec.strip():
                    raise MiroToolError("Miro layout contract lacks a specification")
                if not isinstance(example, str) or not example.strip():
                    raise MiroToolError("Miro layout contract lacks an example")
                before_layout = await read_layout_state(
                    target_url,
                    label="Miro layout preflight readback",
                    allow_empty=True,
                )
                pending_operation_id = operation["operation_id"]
                pending_tool = "layout_create"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                created = await invoke(
                    "layout_create",
                    _base_arguments(target_url, {"dsl": operation["dsl"]}),
                )
                preview_call_index = len(calls)
                item_url = _item_url(created, "layout_create")
                failed_items = _list(created, "failed_items")
                created_count = _integer(created, "created_count")
                result_dsl = created.get("result_dsl", "")
                if created.get("success") is not True or failed_items or created_count < 1:
                    raise MiroToolError("Miro layout creation did not complete cleanly")
                if not isinstance(result_dsl, str) or not result_dsl.strip():
                    raise MiroToolError("Miro layout creation lacks result DSL")
                declared_connector_count = _layout_dsl_connector_count(
                    operation["dsl"], label="submitted Miro layout DSL"
                )
                result_connector_count = _layout_dsl_connector_count(
                    result_dsl, label="Miro layout result DSL"
                )
                if result_connector_count < declared_connector_count:
                    raise MiroToolError(
                        "Miro layout result DSL contains fewer connectors than declared"
                    )
                if created_count < declared_connector_count:
                    raise MiroToolError(
                        "Miro layout created count is below its declared connector count"
                    )
                after_layout = await read_layout_state(
                    target_url,
                    label="Miro layout post-create readback",
                    allow_empty=False,
                )
                connector_evidence = ConnectorEvidence.from_live(
                    declared_count=declared_connector_count,
                    result_dsl_count=result_connector_count,
                    layout_read_before_count=before_layout["connector_count"],
                    layout_read_after_count=after_layout["connector_count"],
                    board_dsl_before_count=before_layout["board_dsl_connector_count"],
                    board_dsl_after_count=after_layout["board_dsl_connector_count"],
                )
                if created_count < connector_evidence.created_count:
                    raise MiroToolError(
                        "Miro layout created count is below its verified connector delta"
                    )
                readback = {
                    "created_count": created_count,
                    "board_inventory_visible_created_count": (
                        created_count - connector_evidence.created_count
                    ),
                    "failed_item_count": len(failed_items),
                    "contract_digest": _digest({"spec": spec, "example": example}),
                    "result_dsl_digest": _text_digest(result_dsl),
                    "board_dsl_before_digest": before_layout["dsl_digest"],
                    "board_dsl_digest": after_layout["dsl_digest"],
                    "board_item_count_before": before_layout["item_count"],
                    "board_item_count": after_layout["item_count"],
                    "skipped_item_count_before": before_layout["skipped_count"],
                    "skipped_item_count": after_layout["skipped_count"],
                    "connector_evidence": connector_evidence.to_dict(),
                }

            elif kind == "diagram":
                if operation.get("native_transport") == "canvas_diagram":
                    if canvas_skill_evidence is None:  # pragma: no cover - preflight invariant
                        raise NativeBundleError("Miro Canvas skills were not preloaded")
                    reconcile_pending = bool(
                        resume is not None
                        and resume.get("pending_operation_id") == operation["operation_id"]
                        and resume.get("pending_tool") == "canvas_create_from_svg"
                    )
                    inventory_evidence: dict[str, Any] | None = None
                    created_evidence: dict[str, Any] | None = None
                    if reconcile_pending:
                        item_url, inventory_evidence = _canvas_inventory_candidate(
                            before_inventory_items,
                            operation=operation,
                            target_url=target_url,
                            verified_reference_digests={
                                digest
                                for completed_operation in completed
                                if isinstance(
                                    digest := completed_operation.get("item_reference_digest"), str
                                )
                            },
                        )
                    else:
                        pending_operation_id = operation["operation_id"]
                        pending_tool = "canvas_create_from_svg"
                        if checkpoint is not None:
                            checkpoint(build_receipt(success=False, error_code="in_progress"))
                        mutation_started = True
                        created = await invoke(
                            "canvas_create_from_svg",
                            _base_arguments(target_url, {"svg": operation["canvas_svg"]}),
                        )
                        preview_call_index = len(calls)
                        if created.get("success") is not True:
                            raise MiroToolError("Miro Canvas diagram creation did not succeed")
                        created_count = _integer(created, "created_count")
                        failed_items = created.get("failed_items", [])
                        if not isinstance(failed_items, list) or failed_items or created_count != 1:
                            raise MiroToolError("Miro Canvas diagram creation was not exact")
                        result_svg = created.get("result_svg")
                        if not isinstance(result_svg, str):
                            raise MiroToolError("Miro Canvas diagram creation lacks result SVG")
                        created_evidence = _canvas_svg_evidence(
                            result_svg,
                            expected_title=operation["title"],
                            expected_source=operation["canvas_mermaid_source"],
                            local_id=operation["canvas_local_id"],
                            require_item_id=True,
                        )
                        item_id = created_evidence.pop("item_id")
                        if not isinstance(item_id, str):  # pragma: no cover - evidence invariant
                            raise MiroToolError("Miro Canvas diagram item id is absent")
                        item_url = _canvas_item_url(target_url, item_id)
                    context = await invoke("context_get", _base_arguments(item_url, {}))
                    context_evidence = _context_diagram_evidence(
                        context,
                        expected_title=operation["title"],
                        expected_source=operation["canvas_mermaid_source"],
                    )
                    svg_schema_available = (
                        CANVAS_DIAGRAM_READBACK_TOOL in schemas
                        and schemas[CANVAS_DIAGRAM_READBACK_TOOL]["output_schema"] is not None
                    )
                    svg_readback_evidence: dict[str, Any] | None = None
                    if svg_schema_available:
                        svg_payload = await invoke(
                            CANVAS_DIAGRAM_READBACK_TOOL,
                            _base_arguments(item_url, {}),
                        )
                        readback_svg = svg_payload.get("svg", svg_payload.get("result_svg"))
                        if not isinstance(readback_svg, str):
                            raise MiroToolError("Miro Canvas SVG readback lacks SVG")
                        svg_readback_evidence = _canvas_svg_evidence(
                            readback_svg,
                            expected_title=operation["title"],
                            expected_source=operation["canvas_mermaid_source"],
                            local_id=None,
                            require_item_id=False,
                        )
                        svg_readback_evidence.pop("item_id", None)
                    if created_evidence is None:
                        created_evidence = (
                            dict(svg_readback_evidence)
                            if svg_readback_evidence is not None
                            else {
                                "svg_digest": None,
                                "title_matches": True,
                                "diagram_semantics": True,
                                "geometry_matches": True,
                                "source_matches": True,
                            }
                        )
                    readback = {
                        "diagram_type": operation["diagram_type"],
                        "native_transport": "canvas_diagram",
                        "mermaid_source_digest": _text_digest(operation["canvas_mermaid_source"]),
                        "submitted_svg_digest": _text_digest(operation["canvas_svg"]),
                        "created_svg": created_evidence,
                        "context": context_evidence,
                        "canvas_svg_schema_available": svg_schema_available,
                        "canvas_svg_verified": svg_readback_evidence is not None,
                        "canvas_svg_readback": svg_readback_evidence,
                        "item_reference_derived": True,
                        "inventory_reconciliation": inventory_evidence,
                        "reconciled_existing": reconcile_pending,
                        **canvas_skill_evidence,
                    }
                else:
                    contract = await invoke(
                        "diagram_get_dsl",
                        _base_arguments(target_url, {"diagram_type": operation["diagram_type"]}),
                    )
                    data = contract.get("data")
                    if contract.get("diagram_type") != operation["diagram_type"] or not isinstance(
                        data, Mapping
                    ):
                        raise MiroToolError("Miro diagram contract readback is invalid")
                    pending_operation_id = operation["operation_id"]
                    pending_tool = "diagram_create"
                    if checkpoint is not None:
                        checkpoint(build_receipt(success=False, error_code="in_progress"))
                    mutation_started = True
                    created = await invoke(
                        "diagram_create",
                        _base_arguments(
                            target_url,
                            {
                                "diagram_dsl": operation["diagram_dsl"],
                                "diagram_type": operation["diagram_type"],
                                "title": operation["title"],
                                **_operation_position(operation),
                            },
                        ),
                    )
                    preview_call_index = len(calls)
                    item_url = _item_url(created, "diagram_create")
                    context = await invoke("context_get", _base_arguments(item_url, {}))
                    content = context.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise MiroToolError("Miro diagram context readback is empty")
                    readback = {
                        "diagram_type": operation["diagram_type"],
                        "native_transport": "legacy_diagram",
                        "contract_digest": _digest(data),
                        "content_digest": _text_digest(content),
                        "content_present": True,
                    }

            elif kind == "document":
                pending_operation_id = operation["operation_id"]
                pending_tool = "doc_create"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                created = await invoke(
                    "doc_create",
                    _base_arguments(
                        target_url,
                        {
                            "content": operation["content"],
                            **_operation_position(operation),
                        },
                    ),
                )
                preview_call_index = len(calls)
                item_url = _item_url(created, "doc_create")
                document = await invoke("doc_get", _base_arguments(item_url, {}))
                content = document.get("content")
                if not isinstance(content, str):
                    raise MiroToolError("Miro document readback lacks content")
                if _normalized_text(content) != _normalized_text(operation["content"]):
                    raise MiroToolError("Miro document readback does not match submitted content")
                readback = {
                    "content_digest": _text_digest(content),
                    "content_matches": True,
                    "content_version": _integer(document, "content_version"),
                }

            elif kind == "table":
                pending_operation_id = operation["operation_id"]
                pending_tool = "table_create"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                created = await invoke(
                    "table_create",
                    _base_arguments(
                        target_url,
                        {
                            "table_title": operation["table_title"],
                            "columns": operation["columns"],
                            **_operation_position(operation),
                        },
                    ),
                )
                preview_call_index = len(calls)
                item_url = _item_url(created, "table_create")
                rows = operation.get("rows", [])
                if rows:
                    await invoke(
                        "table_sync_rows",
                        _base_arguments(item_url, {"rows": rows}),
                    )
                returned_rows, total = await read_all_table_rows(item_url, expected_count=len(rows))
                if rows and total < len(rows):
                    raise MiroToolError("Miro table readback contains fewer rows than submitted")
                _verify_submitted_rows(rows, returned_rows, operation["columns"])
                view = operation.get("view")
                applied_layout = "table"
                if view:
                    updated = await invoke(
                        "table_update_view", _base_arguments(item_url, dict(view))
                    )
                    applied_layout = updated.get("layout")
                    if applied_layout != view["layout"]:
                        raise MiroToolError("Miro table view readback does not match request")
                readback = {
                    "row_count": len(returned_rows),
                    "reported_total": total,
                    "submitted_row_count": len(rows),
                    "submitted_rows_match": True,
                    "layout": applied_layout,
                    "rows_digest": _digest(returned_rows),
                }

            elif kind == "code_widget":
                pending_operation_id = operation["operation_id"]
                pending_tool = "code_widget_create"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                created = await invoke(
                    "code_widget_create",
                    _base_arguments(
                        target_url,
                        {
                            "code": operation["code"],
                            "language": operation.get("language", "PlainText"),
                            "title": operation.get("title"),
                            "line_numbers_visible": operation.get("line_numbers_visible", True),
                            "width": operation.get("width", 800),
                            **_operation_position(operation),
                        },
                    ),
                )
                preview_call_index = len(calls)
                item_url = _item_url(created, "code_widget_create")
                widget = await invoke("code_widget_get", _base_arguments(item_url, {}))
                if widget.get("code") != operation["code"]:
                    raise MiroToolError("Miro code-widget readback does not match submitted code")
                expected_language = operation.get("language", "PlainText")
                if widget.get("language") != expected_language:
                    raise MiroToolError("Miro code-widget language readback does not match")
                expected_title = operation.get("title", "")
                if widget.get("title", "") != expected_title:
                    raise MiroToolError("Miro code-widget title readback does not match")
                expected_line_numbers = operation.get("line_numbers_visible", True)
                if widget.get("line_numbers_visible") is not expected_line_numbers:
                    raise MiroToolError("Miro code-widget line-number readback does not match")
                expected_width = float(operation.get("width", 800))
                returned_width = widget.get("width")
                if (
                    not isinstance(returned_width, int | float)
                    or abs(float(returned_width) - expected_width) > 0.01
                ):
                    raise MiroToolError("Miro code-widget width readback does not match")
                position_matches: dict[str, bool] = {}
                for axis in ("x", "y"):
                    if axis not in operation:
                        continue
                    returned = widget.get(axis)
                    expected = float(operation[axis])
                    if (
                        not isinstance(returned, int | float)
                        or abs(float(returned) - expected) > 0.01
                    ):
                        raise MiroToolError(
                            f"Miro code-widget {axis}-position readback does not match"
                        )
                    position_matches[axis] = True
                readback = {
                    "code_digest": _text_digest(operation["code"]),
                    "code_matches": True,
                    "language": expected_language,
                    "title_digest": _text_digest(expected_title),
                    "line_numbers_visible": expected_line_numbers,
                    "width": expected_width,
                    "position_matches": position_matches,
                }

            elif kind == "document_update":
                item_url = target_url
                before = await invoke("doc_get", _base_arguments(item_url, {}))
                before_content = before.get("content")
                if not isinstance(before_content, str):
                    raise MiroToolError("Miro document preflight lacks content")
                before_digest = _text_digest(_normalized_text(before_content))
                if before_digest != operation["expected_content_sha256"]:
                    raise MiroToolError("Miro document preflight digest does not match")
                occurrences = before_content.count(operation["old_content"])
                if occurrences < 1:
                    raise MiroToolError("Miro document preflight cannot find the exact old content")
                replace_all = operation.get("replace_all", False)
                expected_content = before_content.replace(
                    operation["old_content"],
                    operation["new_content"],
                    -1 if replace_all else 1,
                )
                pending_operation_id = operation["operation_id"]
                pending_tool = "doc_update"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                updated = await invoke(
                    "doc_update",
                    _base_arguments(
                        item_url,
                        {
                            "old_content": operation["old_content"],
                            "new_content": operation["new_content"],
                            "replace_all": replace_all,
                        },
                    ),
                )
                if updated.get("success") is not True:
                    raise MiroToolError("Miro document update failed")
                after = await invoke("doc_get", _base_arguments(item_url, {}))
                after_content = after.get("content")
                if not isinstance(after_content, str):
                    raise MiroToolError("Miro document update readback lacks content")
                if _normalized_text(after_content) != _normalized_text(expected_content):
                    raise MiroToolError("Miro document update readback does not match")
                before_version = _integer(before, "content_version")
                after_version = _integer(after, "content_version")
                if after_version <= before_version:
                    raise MiroToolError("Miro document content version did not advance")
                readback = {
                    "before_content_digest": before_digest,
                    "after_content_digest": _text_digest(_normalized_text(after_content)),
                    "occurrence_count": occurrences,
                    "replace_all": replace_all,
                    "before_content_version": before_version,
                    "after_content_version": after_version,
                    "content_matches": True,
                }

            elif kind == "table_history":
                item_url = target_url
                history = await invoke(
                    "table_get_latest_update_history",
                    _base_arguments(item_url, {"row_id": operation["row_id"]}),
                )
                entries = _list(history, "entries")
                total = _integer(history, "total")
                if len(entries) != total:
                    raise MiroToolError("Miro table update history total is inconsistent")
                minimum = operation.get("expected_min_entries", 0)
                if total < minimum:
                    raise MiroToolError("Miro table update history is shorter than expected")
                expected_latest = operation.get("expected_latest_text")
                latest_text: str | None = None
                if entries:
                    latest = entries[-1]
                    if not isinstance(latest, Mapping):
                        raise MiroToolError("Miro table update history contains an invalid entry")
                    raw_latest = latest.get("text")
                    if raw_latest is not None and not isinstance(raw_latest, str):
                        raise MiroToolError("Miro table update history latest text is invalid")
                    latest_text = raw_latest
                if expected_latest is not None and latest_text != expected_latest:
                    raise MiroToolError("Miro table update history latest text does not match")
                readback = {
                    "entry_count": total,
                    "entries_digest": _digest(entries),
                    "latest_text_digest": _text_digest(latest_text)
                    if latest_text is not None
                    else None,
                    "latest_text_matches": expected_latest is None
                    or latest_text == expected_latest,
                }

            elif kind == "code_widget_inventory":
                items, total, page_count = await read_all_code_widgets(target_url)
                minimum = operation.get("expected_min_count", 0)
                if total < minimum:
                    raise MiroToolError("Miro code-widget inventory is smaller than expected")
                readback = {
                    "item_count": len(items),
                    "reported_total": total,
                    "page_count": page_count,
                    "inventory_digest": _digest(sorted(_digest(dict(item)) for item in items)),
                }

            elif kind == "code_widget_update":
                item_url = target_url
                before = await invoke("code_widget_get", _base_arguments(item_url, {}))
                if before.get("success") is not True:
                    raise MiroToolError("Miro code-widget update preflight failed")
                _verify_code_widget_fields(before, operation["expected_before"], label="preflight")
                pending_operation_id = operation["operation_id"]
                pending_tool = "code_widget_update"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                updated = await invoke(
                    "code_widget_update",
                    _base_arguments(item_url, operation["set"]),
                )
                if updated.get("success") is not True:
                    raise MiroToolError("Miro code-widget update failed")
                after = await invoke("code_widget_get", _base_arguments(item_url, {}))
                if after.get("success") is not True:
                    raise MiroToolError("Miro code-widget update readback failed")
                _verify_code_widget_fields(after, operation["set"], label="readback")
                readback = {
                    "before_digest": _digest(dict(before)),
                    "after_digest": _digest(dict(after)),
                    "updated_fields": sorted(operation["set"]),
                    "fields_match": True,
                }

            elif kind == "code_widget_delete":
                item_url = target_url
                before = await invoke("code_widget_get", _base_arguments(item_url, {}))
                if before.get("success") is not True:
                    raise MiroToolError("Miro code-widget delete preflight failed")
                _verify_code_widget_fields(before, operation["expected_before"], label="preflight")
                items_before, total_before, _pages_before = await read_all_code_widgets(board_url)
                if item_url not in _widget_reference_set(items_before):
                    raise MiroToolError("Miro code-widget delete target is absent from inventory")
                pending_operation_id = operation["operation_id"]
                pending_tool = "code_widget_delete"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                deleted = await invoke("code_widget_delete", _base_arguments(item_url, {}))
                if deleted.get("success") is not True:
                    raise MiroToolError("Miro code-widget deletion failed")
                items_after, total_after, page_count = await read_all_code_widgets(board_url)
                if item_url in _widget_reference_set(items_after):
                    raise MiroToolError(
                        "Miro code-widget deletion readback still contains the target"
                    )
                if total_after != total_before - 1:
                    raise MiroToolError(
                        "Miro code-widget inventory did not decrease by exactly one"
                    )
                readback = {
                    "before_count": total_before,
                    "after_count": total_after,
                    "page_count": page_count,
                    "target_absent": True,
                    "deleted_item_digest": _digest(dict(before)),
                }

            elif kind == "prototype":
                if upload_html is None:
                    raise NativeBundleError("prototype execution requires an HTML upload transport")
                screen_payloads, screen_digests = _load_prototype_screens(
                    operation, bundle_root=bundle_root
                )
                reservation = await invoke(
                    "prototype_get_upload_url",
                    _base_arguments(target_url, {"count": len(screen_payloads)}),
                )
                slots = _list(reservation, "result")
                if len(slots) != len(screen_payloads):
                    raise MiroToolError("Miro prototype upload reservation count does not match")
                tokens: list[str] = []
                for index, (slot, payload) in enumerate(zip(slots, screen_payloads, strict=True)):
                    if not isinstance(slot, Mapping):
                        raise MiroToolError("Miro prototype upload reservation is invalid")
                    upload_url = slot.get("upload_url")
                    token = slot.get("token")
                    expires_in = slot.get("expires_in")
                    if not isinstance(upload_url, str) or not upload_url.startswith("https://"):
                        raise MiroToolError("Miro prototype upload URL is invalid")
                    if not isinstance(token, str) or not token:
                        raise MiroToolError("Miro prototype upload token is invalid")
                    if (
                        isinstance(expires_in, bool)
                        or not isinstance(expires_in, int)
                        or expires_in <= 0
                    ):
                        raise MiroToolError("Miro prototype upload expiry is invalid")
                    await upload_html(upload_url, payload)
                    calls.append(
                        {
                            "index": len(calls) + 1,
                            "tool": "prototype_html_upload",
                            "input_digest": _digest(
                                {"screen_index": index, "content_sha256": screen_digests[index]}
                            ),
                            "output_digest": _digest({"uploaded": True}),
                        }
                    )
                    tokens.append(token)
                pending_operation_id = operation["operation_id"]
                pending_tool = "prototype_create"
                if checkpoint is not None:
                    checkpoint(build_receipt(success=False, error_code="in_progress"))
                mutation_started = True
                created = await invoke(
                    "prototype_create",
                    _base_arguments(
                        target_url,
                        {
                            "html_tokens": tokens,
                            "device_type": operation.get("device_type", "desktop"),
                            "orientation": operation.get("orientation", "landscape"),
                            **_operation_position(operation),
                        },
                    ),
                )
                preview_call_index = len(calls)
                if created.get("success") is not True:
                    raise MiroToolError("Miro prototype creation failed")
                if _integer(created, "failed_image_count") != 0:
                    raise MiroToolError("Miro prototype creation reported failed images")
                item_url = _item_url(created, "prototype_create")
                context = await invoke("context_get", _base_arguments(item_url, {}))
                content = context.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise MiroToolError("Miro prototype context readback is empty")
                readback = {
                    "screen_count": len(screen_payloads),
                    "screen_digests": screen_digests,
                    "context_digest": _text_digest(content),
                    "successful_image_count": _integer(created, "successful_image_count"),
                    "failed_image_count": 0,
                    "device_type": operation.get("device_type", "desktop"),
                    "orientation": operation.get("orientation", "landscape"),
                }

            elif kind == "comment":
                reconcile_pending = bool(
                    resume is not None
                    and resume.get("pending_operation_id") == operation["operation_id"]
                    and resume.get("pending_tool") == "comment_create"
                )
                comment_id: str | None = None
                reconciled_existing = False
                if reconcile_pending:
                    comments_before = await read_all_comments(target_url)
                    comment_id = _comment_id_for_content(comments_before, operation["content"])
                    if comment_id is None:
                        raise MiroToolError(
                            "uncertain Miro comment mutation could not be reconciled"
                        )
                    reconciled_existing = True
                else:
                    pending_operation_id = operation["operation_id"]
                    pending_tool = "comment_create"
                    if checkpoint is not None:
                        checkpoint(build_receipt(success=False, error_code="in_progress"))
                    mutation_started = True
                    created = await invoke(
                        "comment_create",
                        _base_arguments(
                            target_url,
                            {
                                "content": operation["content"],
                                "x": operation["x"],
                                "y": operation["y"],
                            },
                        ),
                    )
                    comment_id = created.get("id")
                    if not isinstance(comment_id, str) or not comment_id:
                        raise MiroToolError("Miro comment creation lacks an identifier")
                comments = await read_all_comments(target_url)
                if not any(
                    isinstance(comment, Mapping) and comment.get("id") == comment_id
                    for comment in comments
                ):
                    raise MiroToolError(
                        "Miro comment readback does not contain the created comment"
                    )
                readback = {
                    "comment_reference_digest": _text_digest(comment_id)[:24],
                    "comment_present": True,
                    "content_digest": _text_digest(operation["content"]),
                    "reconciled_existing": reconciled_existing,
                }

            else:  # pragma: no cover - schema validation owns this branch
                raise NativeBundleError(f"unsupported native operation kind: {kind}")

            fallback = operation.get("provider_fallback")
            if isinstance(fallback, Mapping):
                readback = {
                    **readback,
                    "provider_mode": "fallback",
                    "fallback": fallback["fallback"],
                    "fallback_execution_kind": operation["kind"],
                    "source_operation_digest": fallback["source_operation_digest"],
                }
            else:
                readback = {**readback, "provider_mode": "native"}
            if preview_call_index is not None:
                readback = {
                    **readback,
                    "provider_preview": await provider_preview_evidence(preview_call_index),
                }
            completed.append(
                _operation_receipt(
                    original_operation,
                    item_url=item_url,
                    readback=readback,
                    call_indexes=range(start_index, len(calls) + 1),
                )
            )
            current_operation_id = None
            pending_operation_id = None
            pending_tool = None
            if checkpoint is not None:
                checkpoint(build_receipt(success=False, error_code="in_progress"))

        after_inventory, _after_inventory_items = await read_complete_inventory()
        after_context = _context_summary(
            await invoke("context_explore", _base_arguments(board_url, {}))
        )
        baseline_inventory = (original_preflight or {"inventory": before_inventory}).get(
            "inventory"
        )
        if not isinstance(baseline_inventory, Mapping):
            raise MiroToolError("native execution lacks a baseline board inventory")
        observed_delta = after_inventory["item_count"] - baseline_inventory["item_count"]
        expected_delta = _expected_inventory_visible_net_item_delta(completed)
        if observed_delta < expected_delta:
            raise MiroToolError(
                "Miro board inventory did not expose all created native items "
                "visible through inventory"
            )
        receipt = build_receipt(success=True)
        if checkpoint is not None:
            checkpoint(receipt)
        return receipt
    except Exception as exc:
        failure = build_receipt(
            success=False,
            failed_operation_id=current_operation_id,
            error_code=type(exc).__name__,
        )
        if checkpoint is not None:
            checkpoint(failure)
        if isinstance(exc, (NativeBundleError, MiroToolError)):
            raise NativeExecutionError(str(exc)) from exc
        raise
