"""Sanitized Grabowski operator overview pilot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from schauwerk.registry_runtime import load_registry
from schauwerk.visual.miro_dsl import doc, line, table

SCHEMA_VERSION = "grabowski-pilot-snapshot.v1"


def _read_json_file(path: Path) -> tuple[dict[str, Any], str]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("operator context must be a regular non-symlink file")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("operator context exceeds the 5 MiB limit")
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("operator context is unreadable") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("operator context must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("operator context must contain an object")
    return value, hashlib.sha256(raw).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _safe_text(value: Any, *, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = " ".join(value.replace("<<<", "").replace(">>>", "").split())
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized[:maximum]


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_grabowski_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Grabowski pilot snapshot schema")
    digest = snapshot.get("snapshot_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Grabowski pilot snapshot digest is invalid")
    if digest != _snapshot_digest(snapshot):
        raise ValueError("Grabowski pilot snapshot digest mismatch")
    summary = _mapping(snapshot.get("summary"), "summary")
    categories = _mapping(snapshot.get("capability_categories"), "capability_categories")
    risks = _mapping(snapshot.get("risk_classes"), "risk_classes")
    source = _mapping(snapshot.get("source"), "source")
    boundaries = _mapping(snapshot.get("boundaries"), "boundaries")
    if snapshot.get("project_id") != "grabowski":
        raise ValueError("Grabowski pilot project_id is invalid")
    if snapshot.get("view_id") != "grabowski.operator-overview":
        raise ValueError("Grabowski pilot view_id is invalid")
    if source.get("source_id") != "grabowski.operator-context":
        raise ValueError("Grabowski pilot source_id is invalid")
    source_sha = source.get("sha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ValueError("Grabowski pilot source digest is invalid")
    try:
        int(source_sha, 16)
    except ValueError as exc:
        raise ValueError("Grabowski pilot source digest is invalid") from exc
    expected_boundaries = {
        "source_system_remains_authoritative": True,
        "contains_live_runtime_state": False,
        "contains_secret_values": False,
        "provider_mutation_attempted": False,
    }
    if dict(boundaries) != expected_boundaries:
        raise ValueError("Grabowski pilot boundaries are invalid")
    capability_count = summary.get("capability_count")
    read_only_count = summary.get("read_only_capability_count")
    effectful_count = summary.get("effectful_capability_count")
    counts = (capability_count, read_only_count, effectful_count)
    if not all(isinstance(value, int) and value >= 0 for value in counts):
        raise ValueError("Grabowski pilot capability counts are invalid")
    expected_tool_count = summary.get("expected_tool_count")
    if not isinstance(expected_tool_count, int) or expected_tool_count < 0:
        raise ValueError("Grabowski pilot expected tool count is invalid")
    for field in ("purpose", "active_profile", "policy_mode", "operating_protocol"):
        _safe_text(summary.get(field), label=f"summary.{field}")
    if read_only_count + effectful_count != capability_count:
        raise ValueError("Grabowski pilot capability counts do not add up")
    for label, values in (("category", categories), ("risk", risks)):
        if not all(isinstance(value, int) and value >= 0 for value in values.values()):
            raise ValueError(f"Grabowski pilot {label} counts are invalid")
        if sum(values.values()) != capability_count:
            raise ValueError(f"Grabowski pilot {label} counts do not add up")


def _safe_output_path(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("pilot output path is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("pilot output path is unsafe")
    return destination


def _write_text_atomic(path: Path, text: str) -> None:
    destination = _safe_output_path(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise ValueError("pilot output could not be written") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def compile_grabowski_snapshot(path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    context, source_digest = _read_json_file(path)
    if context.get("schema_version") != 1:
        raise ValueError("operator context schema_version must be 1")
    capabilities = context.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("operator context capabilities must be a non-empty list")
    if not all(isinstance(item, Mapping) for item in capabilities):
        raise ValueError("operator context capabilities must contain objects")

    registry = load_registry(repo_root)
    source = next(
        (item for item in registry["sources"] if item["id"] == "grabowski.operator-context"),
        None,
    )
    view = next(
        (item for item in registry["views"] if item["id"] == "grabowski.operator-overview"),
        None,
    )
    if source is None or view is None:
        raise ValueError("Grabowski pilot registry declarations are missing")

    categories = Counter(
        _safe_text(str(item.get("category", "unknown")), label="capability.category", maximum=80)
        for item in capabilities
    )
    risks = Counter(
        _safe_text(
            str(item.get("risk_class", "unknown")),
            label="capability.risk_class",
            maximum=80,
        )
        for item in capabilities
    )
    read_only = sum(item.get("read_only") is True for item in capabilities)
    effectful = len(capabilities) - read_only
    runtime = _mapping(context.get("runtime_contract"), "runtime_contract")
    policy = _mapping(context.get("policy_contract"), "policy_contract")
    protocol = _mapping(context.get("operating_protocol"), "operating_protocol")
    expected_tools = runtime.get("expected_tools")
    if not isinstance(expected_tools, list) or not all(
        isinstance(item, str) for item in expected_tools
    ):
        raise ValueError("operator context runtime_contract.expected_tools must be a string list")

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": "grabowski",
        "view_id": view["id"],
        "source": {
            "source_id": source["id"],
            "reference": source["reference"],
            "sha256": source_digest,
            "schema_version": context["schema_version"],
        },
        "summary": {
            "purpose": _safe_text(context.get("purpose"), label="purpose"),
            "capability_count": len(capabilities),
            "read_only_capability_count": read_only,
            "effectful_capability_count": effectful,
            "expected_tool_count": len(expected_tools),
            "active_profile": _safe_text(
                policy.get("active_profile", "unknown"), label="active_profile", maximum=80
            ),
            "policy_mode": _safe_text(
                policy.get("mode", "unknown"), label="policy_mode", maximum=80
            ),
            "operating_protocol": _safe_text(
                protocol.get("name", "unknown"), label="operating_protocol", maximum=120
            ),
        },
        "capability_categories": dict(sorted(categories.items())),
        "risk_classes": dict(sorted(risks.items())),
        "boundaries": {
            "source_system_remains_authoritative": True,
            "contains_live_runtime_state": False,
            "contains_secret_values": False,
            "provider_mutation_attempted": False,
        },
    }
    snapshot["snapshot_digest"] = _snapshot_digest(snapshot)
    return snapshot


def render_grabowski_dsl(snapshot: Mapping[str, Any]) -> str:
    validate_grabowski_snapshot(snapshot)
    summary = _mapping(snapshot.get("summary"), "summary")
    categories = _mapping(snapshot.get("capability_categories"), "capability_categories")
    risks = _mapping(snapshot.get("risk_classes"), "risk_classes")
    boundaries = _mapping(snapshot.get("boundaries"), "boundaries")
    lines = [
        line("root", "FRAME", x=0, y=0, w=3000, h=1900, content="Grabowski Operator Overview"),
        line(
            "title",
            "TEXT",
            parent="root",
            x=1500,
            y=90,
            w=2400,
            size=34,
            align="center",
            content="Grabowski — deterministische Operator-Projektion",
        ),
        line("contract", "FRAME", x=-850, y=300, w=900, h=1250, content="Vertrag"),
        line("capabilities", "FRAME", x=150, y=300, w=900, h=1250, content="Fähigkeiten"),
        line("risk", "FRAME", x=1150, y=300, w=900, h=1250, content="Risiko und Grenzen"),
        doc(
            "contract_doc",
            parent="contract",
            x=450,
            y=230,
            markdown=(
                f"# Zweck\n\n{summary['purpose']}\n\n"
                f"**Profil:** {summary['active_profile']}\n\n"
                f"**Policy-Modus:** {summary['policy_mode']}\n\n"
                f"**Protokoll:** {summary['operating_protocol']}"
            ),
        ),
        table(
            "category_table",
            parent="capabilities",
            x=450,
            y=300,
            title="Capability-Kategorien",
            columns=("Kategorie", "Anzahl"),
            rows=tuple((str(key), str(value)) for key, value in categories.items()),
        ),
        table(
            "risk_table",
            parent="risk",
            x=450,
            y=300,
            title="Risikoklassen",
            columns=("Klasse", "Anzahl"),
            rows=tuple((str(key), str(value)) for key, value in risks.items()),
        ),
        line(
            "counts",
            "SHAPE",
            parent="capabilities",
            x=450,
            y=940,
            w=650,
            h=210,
            type="round_rectangle",
            content=(
                f"Gesamt: {summary['capability_count']} | "
                f"read-only: {summary['read_only_capability_count']} | "
                f"effektvoll: {summary['effectful_capability_count']} | "
                f"Runtime-Tools: {summary['expected_tool_count']}"
            ),
        ),
        line(
            "boundary",
            "SHAPE",
            parent="risk",
            x=450,
            y=940,
            w=650,
            h=250,
            type="round_rectangle",
            content=(
                "Quellsystem bleibt maßgeblich. Keine Live-Laufzeitbehauptung, "
                "keine Geheimnisse und keine Provider-Mutation. "
                f"Grenzen bestätigt: {sum(value is True for value in boundaries.values())}/4."
            ),
        ),
        line(
            "footer",
            "TEXT",
            parent="root",
            x=1500,
            y=1740,
            w=2400,
            size=18,
            align="center",
            content=f"Snapshot {str(snapshot['snapshot_digest'])[:16]} · aus deklarierter Quelle",
        ),
    ]
    return "\n".join(lines) + "\n"


def write_grabowski_pilot(
    *,
    operator_context: Path,
    snapshot_output: Path | None,
    dsl_output: Path | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    snapshot = compile_grabowski_snapshot(operator_context, repo_root=repo_root)
    dsl = render_grabowski_dsl(snapshot)
    if snapshot_output is not None:
        _write_text_atomic(
            snapshot_output, json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        )
    if dsl_output is not None:
        _write_text_atomic(dsl_output, dsl)
    return {
        "schema_version": "grabowski-pilot-render-receipt.v1",
        "project_id": snapshot["project_id"],
        "view_id": snapshot["view_id"],
        "source_sha256": snapshot["source"]["sha256"],
        "snapshot_digest": snapshot["snapshot_digest"],
        "snapshot_output": str(snapshot_output) if snapshot_output else None,
        "dsl_output": str(dsl_output) if dsl_output else None,
        "dsl_line_count": len([value for value in dsl.splitlines() if value.strip()]),
        "provider_mutation_attempted": False,
    }
