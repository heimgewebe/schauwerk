"""Generic deterministic software-project pilot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from schauwerk.registry_runtime import load_registry
from schauwerk.visual.grammar import GRAMMAR_SCHEMA_VERSION, software_template, state_label
from schauwerk.visual.miro_dsl import doc, line, table

INPUT_SCHEMA_VERSION = "software-pilot-input.v1"
SNAPSHOT_SCHEMA_VERSION = "software-pilot-snapshot.v1"
_MAX_INPUT_BYTES = 5 * 1024 * 1024


def _safe_text(value: Any, *, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = " ".join(value.replace("<<<", "").replace(">>>", "").split())
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized[:maximum]


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("software pilot input must be a regular non-symlink file")
        if path.stat().st_size > _MAX_INPUT_BYTES:
            raise ValueError("software pilot input exceeds the 5 MiB limit")
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("software pilot input is unreadable") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("software pilot input must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("software pilot input must contain an object")
    return value, hashlib.sha256(raw).hexdigest()


def _schema_path(repo_root: Path) -> Path:
    return repo_root / "schemas" / "software-pilot-input.v1.schema.json"


def _validate_input(value: Mapping[str, Any], *, repo_root: Path) -> None:
    schema_path = _schema_path(repo_root)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("software pilot input schema is unavailable") from exc
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: list(item.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "root"
        raise ValueError(f"software pilot input is invalid at {location}: {first.message}")


def _digest(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "snapshot_digest"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_output_path(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("pilot output path is unsafe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("pilot output path is unsafe")
    return destination


def _write_atomic(path: Path, text: str) -> None:
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


def _normalized_items(
    values: Sequence[Mapping[str, Any]],
    *,
    fields: tuple[str, ...],
    label: str,
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(values):
        normalized = {
            field: _safe_text(item.get(field), label=f"{label}[{index}].{field}", maximum=240)
            for field in fields
        }
        identifier = normalized[fields[0]]
        if identifier in identifiers:
            raise ValueError(f"{label} contains duplicate id {identifier}")
        identifiers.add(identifier)
        result.append(normalized)
    return sorted(result, key=lambda item: item[fields[0]])


def compile_software_snapshot(
    input_path: Path, *, repo_root: Path | None = None
) -> dict[str, Any]:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    value, source_sha256 = _read_json(input_path)
    _validate_input(value, repo_root=root)
    if value.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise ValueError("unsupported software pilot input schema")

    registry = load_registry(root)
    project_id = _safe_text(value.get("project_id"), label="project_id", maximum=120)
    view_id = _safe_text(value.get("view_id"), label="view_id", maximum=180)
    project = next((item for item in registry["projects"] if item["id"] == project_id), None)
    view = next((item for item in registry["views"] if item["id"] == view_id), None)
    if project is None or view is None:
        raise ValueError("software pilot registry declarations are missing")
    if view["project_id"] != project_id:
        raise ValueError("software pilot view does not belong to project")

    source_bindings: list[dict[str, str]] = []
    source_ids: set[str] = set()
    for index, binding in enumerate(value["sources"]):
        source_id = _safe_text(
            binding.get("source_id"), label=f"sources[{index}].source_id", maximum=180
        )
        if source_id in source_ids:
            raise ValueError(f"software pilot sources contain duplicate id {source_id}")
        source_ids.add(source_id)
        source = next((item for item in registry["sources"] if item["id"] == source_id), None)
        if source is None:
            raise ValueError("software pilot source registry declaration is missing")
        if source_id not in project["source_ids"] or source_id not in view["source_ids"]:
            raise ValueError("software pilot source is not declared by project and view")
        source_bindings.append(
            {
                "source_id": source_id,
                "reference": source["reference"],
                "revision": _safe_text(
                    binding.get("revision"), label=f"sources[{index}].revision", maximum=120
                ),
            }
        )
    source_bindings.sort(key=lambda item: item["source_id"])

    components = _normalized_items(
        value["components"], fields=("id", "title", "responsibility", "status"), label="components"
    )
    decisions = _normalized_items(
        value["decisions"], fields=("id", "title", "status", "impact"), label="decisions"
    )
    roadmap = _normalized_items(
        value["roadmap"], fields=("id", "title", "status", "outcome"), label="roadmap"
    )
    work = _normalized_items(
        value["work"], fields=("id", "title", "status", "kind"), label="work"
    )
    risks = _normalized_items(
        value["risks"], fields=("id", "title", "severity", "status", "mitigation"), label="risks"
    )
    tests = value["tests"]
    passed = int(tests["passed"])
    failed = int(tests["failed"])
    total = passed + failed

    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_id": project_id,
        "view_id": view_id,
        "input_sha256": source_sha256,
        "sources": source_bindings,
        "summary": {
            "title": _safe_text(value.get("title"), label="title", maximum=180),
            "purpose": _safe_text(value.get("purpose"), label="purpose"),
            "component_count": len(components),
            "decision_count": len(decisions),
            "roadmap_count": len(roadmap),
            "work_count": len(work),
            "risk_count": len(risks),
            "test_total": total,
            "test_passed": passed,
            "test_failed": failed,
            "test_status": _safe_text(tests.get("status"), label="tests.status", maximum=80),
        },
        "components": components,
        "decisions": decisions,
        "roadmap": roadmap,
        "work": work,
        "risks": risks,
        "boundaries": {
            "source_system_remains_authoritative": True,
            "contains_secret_values": False,
            "contains_personal_data": False,
            "provider_mutation_attempted": False,
        },
    }
    snapshot["snapshot_digest"] = _digest(snapshot)
    validate_software_snapshot(snapshot, repo_root=root)
    return snapshot


def validate_software_snapshot(
    snapshot: Mapping[str, Any], *, repo_root: Path | None = None
) -> None:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported software pilot snapshot schema")
    digest = snapshot.get("snapshot_digest")
    if not isinstance(digest, str) or len(digest) != 64 or digest != _digest(snapshot):
        raise ValueError("software pilot snapshot digest mismatch")
    expected_top_level = {
        "schema_version",
        "project_id",
        "view_id",
        "input_sha256",
        "sources",
        "summary",
        "components",
        "decisions",
        "roadmap",
        "work",
        "risks",
        "boundaries",
        "snapshot_digest",
    }
    if set(snapshot) != expected_top_level:
        raise ValueError("software pilot snapshot fields are invalid")
    registry = load_registry(root)
    project_id = snapshot.get("project_id")
    view_id = snapshot.get("view_id")
    sources_value = snapshot.get("sources")
    summary = snapshot.get("summary")
    boundaries = snapshot.get("boundaries")
    input_sha = snapshot.get("input_sha256")
    if not isinstance(sources_value, list) or not sources_value or not isinstance(summary, Mapping):
        raise ValueError("software pilot snapshot sections are invalid")
    if not isinstance(input_sha, str) or len(input_sha) != 64:
        raise ValueError("software pilot snapshot input digest is invalid")
    try:
        int(input_sha, 16)
    except ValueError as exc:
        raise ValueError("software pilot snapshot input digest is invalid") from exc
    project = next((item for item in registry["projects"] if item["id"] == project_id), None)
    view = next((item for item in registry["views"] if item["id"] == view_id), None)
    if project is None or view is None or view["project_id"] != project_id:
        raise ValueError("software pilot snapshot registry binding is invalid")
    observed_source_ids: list[str] = []
    for source_value in sources_value:
        if not isinstance(source_value, Mapping) or set(source_value) != {
            "source_id",
            "reference",
            "revision",
        }:
            raise ValueError("software pilot snapshot source binding is invalid")
        source_id = source_value.get("source_id")
        source = next((item for item in registry["sources"] if item["id"] == source_id), None)
        if source is None:
            raise ValueError("software pilot snapshot source binding is invalid")
        if source_id not in project["source_ids"] or source_id not in view["source_ids"]:
            raise ValueError("software pilot snapshot source binding is invalid")
        if source_value.get("reference") != source["reference"]:
            raise ValueError("software pilot snapshot source reference is invalid")
        revision = source_value.get("revision")
        if not isinstance(revision, str) or len(revision) not in {40, 64}:
            raise ValueError("software pilot snapshot revision is invalid")
        try:
            int(revision, 16)
        except ValueError as exc:
            raise ValueError("software pilot snapshot revision is invalid") from exc
        observed_source_ids.append(str(source_id))
    if observed_source_ids != sorted(observed_source_ids):
        raise ValueError("software pilot snapshot source order is invalid")
    if len(set(observed_source_ids)) != len(observed_source_ids):
        raise ValueError("software pilot snapshot source ids are invalid")
    expected_summary_fields = {
        "title",
        "purpose",
        "component_count",
        "decision_count",
        "roadmap_count",
        "work_count",
        "risk_count",
        "test_total",
        "test_passed",
        "test_failed",
        "test_status",
    }
    if set(summary) != expected_summary_fields:
        raise ValueError("software pilot summary fields are invalid")
    for field in ("title", "purpose", "test_status"):
        value = summary.get(field)
        if value != _safe_text(value, label=f"summary.{field}"):
            raise ValueError(f"software pilot summary.{field} is not normalized")
    expected_boundaries = {
        "source_system_remains_authoritative": True,
        "contains_secret_values": False,
        "contains_personal_data": False,
        "provider_mutation_attempted": False,
    }
    if dict(boundaries or {}) != expected_boundaries:
        raise ValueError("software pilot boundaries are invalid")
    collection_fields = {
        "components": ("id", "title", "responsibility", "status"),
        "decisions": ("id", "title", "status", "impact"),
        "roadmap": ("id", "title", "status", "outcome"),
        "work": ("id", "title", "status", "kind"),
        "risks": ("id", "title", "severity", "status", "mitigation"),
    }
    for collection, fields in collection_fields.items():
        values = snapshot.get(collection)
        if not isinstance(values, list) or not values:
            raise ValueError(f"software pilot {collection} are invalid")
        identifiers: list[str] = []
        for index, item in enumerate(values):
            if not isinstance(item, Mapping) or set(item) != set(fields):
                raise ValueError(f"software pilot {collection} fields are invalid")
            for field in fields:
                value = item.get(field)
                if value != _safe_text(
                    value, label=f"{collection}[{index}].{field}", maximum=240
                ):
                    raise ValueError(
                        f"software pilot {collection}[{index}].{field} is not normalized"
                    )
            identifiers.append(str(item["id"]))
        if identifiers != sorted(identifiers):
            raise ValueError(f"software pilot {collection} order is invalid")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"software pilot {collection} ids are invalid")
    counts = {
        "component_count": len(snapshot["components"]),
        "decision_count": len(snapshot["decisions"]),
        "roadmap_count": len(snapshot["roadmap"]),
        "work_count": len(snapshot["work"]),
        "risk_count": len(snapshot["risks"]),
    }
    if any(summary.get(key) != count for key, count in counts.items()):
        raise ValueError("software pilot summary counts are invalid")
    passed = summary.get("test_passed")
    failed = summary.get("test_failed")
    total = summary.get("test_total")
    if not all(isinstance(item, int) and item >= 0 for item in (passed, failed, total)):
        raise ValueError("software pilot test counts are invalid")
    if passed + failed != total:
        raise ValueError("software pilot test counts do not add up")


def render_software_dsl(snapshot: Mapping[str, Any], *, repo_root: Path | None = None) -> str:
    validate_software_snapshot(snapshot, repo_root=repo_root)
    summary = snapshot["summary"]
    components = snapshot["components"]
    decisions = snapshot["decisions"]
    roadmap = snapshot["roadmap"]
    work = snapshot["work"]
    risks = snapshot["risks"]
    template = software_template()
    test_state = "healthy" if summary["test_failed"] == 0 else "failed"
    lines = [
        line("root", "FRAME", x=0, y=0, w=4600, h=2300, content=summary["title"]),
        line(
            "title",
            "TEXT",
            parent="root",
            x=2300,
            y=90,
            w=4000,
            size=34,
            align="center",
            content=f"{summary['title']} — Software-Projektion",
        ),
        line("architecture", "FRAME", x=-1725, y=350, w=1050, h=1450, content="Architektur"),
        line(
            "direction",
            "FRAME",
            x=-575,
            y=350,
            w=1050,
            h=1450,
            content="Entscheidungen und Roadmap",
        ),
        line("delivery", "FRAME", x=575, y=350, w=1050, h=1450, content="Arbeit und Tests"),
        line("risk", "FRAME", x=1725, y=350, w=1050, h=1450, content="Risiken"),
        doc(
            "purpose",
            parent="architecture",
            x=525,
            y=190,
            markdown=f"# Zweck\n\n{summary['purpose']}",
        ),
        table(
            "component_table",
            parent="architecture",
            x=525,
            y=600,
            title="Komponenten",
            columns=("Komponente", "Verantwortung", "Status"),
            rows=tuple(
                (item["title"], item["responsibility"], item["status"]) for item in components
            ),
        ),
        table(
            "decision_table",
            parent="direction",
            x=525,
            y=430,
            title="Entscheidungen",
            columns=("Entscheidung", "Status", "Wirkung"),
            rows=tuple((item["title"], item["status"], item["impact"]) for item in decisions),
        ),
        table(
            "roadmap_table",
            parent="direction",
            x=525,
            y=1050,
            title="Roadmap",
            columns=("Schritt", "Status", "Ergebnis"),
            rows=tuple((item["title"], item["status"], item["outcome"]) for item in roadmap),
        ),
        table(
            "work_table",
            parent="delivery",
            x=525,
            y=500,
            title="Aktuelle Arbeit",
            columns=("Arbeit", "Art", "Status"),
            rows=tuple((item["title"], item["kind"], item["status"]) for item in work),
        ),
        line(
            "tests",
            "SHAPE",
            parent="delivery",
            x=525,
            y=1200,
            w=720,
            h=230,
            type="round_rectangle",
            content=(
                f"Tests: {summary['test_passed']}/{summary['test_total']} bestanden · "
                f"{state_label(test_state, detail=summary['test_status'])}"
            ),
        ),
        table(
            "risk_table",
            parent="risk",
            x=425,
            y=650,
            title="Offene Risiken",
            columns=("Risiko", "Schwere", "Status", "Gegenmaßnahme"),
            rows=tuple(
                (item["title"], item["severity"], item["status"], item["mitigation"])
                for item in risks
            ),
        ),
        line(
            "footer",
            "TEXT",
            parent="root",
            x=2300,
            y=2140,
            w=4000,
            size=18,
            align="center",
            content=(
                f"Snapshot {snapshot['snapshot_digest'][:16]} · {GRAMMAR_SCHEMA_VERSION} · "
                f"Template {template.name} · Quellsystem bleibt maßgeblich · "
                "keine Provider-Mutation"
            ),
        ),
    ]
    return "\n".join(lines) + "\n"


def write_software_pilot(
    *,
    input_path: Path,
    snapshot_output: Path | None,
    dsl_output: Path | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    snapshot = compile_software_snapshot(input_path, repo_root=repo_root)
    dsl = render_software_dsl(snapshot, repo_root=repo_root)
    if snapshot_output is not None:
        _write_atomic(snapshot_output, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    if dsl_output is not None:
        _write_atomic(dsl_output, dsl)
    return {
        "schema_version": "software-pilot-render-receipt.v1",
        "project_id": snapshot["project_id"],
        "view_id": snapshot["view_id"],
        "input_sha256": snapshot["input_sha256"],
        "source_count": len(snapshot["sources"]),
        "snapshot_digest": snapshot["snapshot_digest"],
        "snapshot_output": str(snapshot_output) if snapshot_output else None,
        "dsl_output": str(dsl_output) if dsl_output else None,
        "dsl_line_count": len([item for item in dsl.splitlines() if item.strip()]),
        "provider_mutation_attempted": False,
    }
