"""Thin classroom orchestration over existing Schauwerk education and Miro contracts.

The deterministic core deliberately stops short of pedagogical judgement. It can
prepare a classroom package and compare verified snapshots; any interpretation of
student learning remains an explicitly separate, optional layer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .durable.common import (
    DurableError,
    bind_digest,
    read_json,
    require_bound_digest,
    safe_digest,
    stable_digest,
    write_json,
)
from .education.view import LearningView, load_learning_view, render_learning_dsl
from .surfaces.miro.snapshot_model import content_digest as snapshot_content_digest

CLASSROOM_TEMPLATES: dict[str, tuple[str, ...]] = {
    "vibe-coding": (
        "Idee: Was soll unser Programm koennen?",
        "Unser Prompt: Was sagen wir der KI genau?",
        "KI-Ergebnis: Was hat die KI daraus gemacht?",
        "Test: Was funktioniert, was funktioniert nicht?",
        "Unsere Aenderung: Was verbessern wir selbst?",
        "Erkenntnis: Was haben wir ueber Coding mit KI gelernt?",
    ),
    "discover": (
        "Frage: Was wollen wir herausfinden?",
        "Vermutung: Was erwarten wir und warum?",
        "Ausprobieren: Wie pruefen wir unsere Vermutung?",
        "Beobachtung: Was ist tatsaechlich passiert?",
        "Erklaerung: Was schliessen wir daraus?",
        "Offene Frage: Was ist noch ungeklaert?",
    ),
    "group-compare": (
        "Unser Ansatz",
        "Unser wichtigster Beleg",
        "Was funktioniert gut?",
        "Wo liegen Grenzen oder Probleme?",
        "Unser Fazit fuer den Vergleich",
    ),
}

CLASSROOM_ROLES: tuple[dict[str, str], ...] = (
    {"role": "instruction", "management_mode": "managed"},
    {"role": "material", "management_mode": "read-only"},
    {"role": "group_workspace", "management_mode": "cooperative"},
    {"role": "student_output", "management_mode": "manual"},
    {"role": "synthesis", "management_mode": "suggest-only"},
    {"role": "reflection", "management_mode": "approval-required"},
    {"role": "teacher_output", "management_mode": "approval-required"},
)

_PACKAGE_SCHEMA = "schauwerk-classroom-package.v1"
_SUMMARY_SCHEMA = "schauwerk-classroom-summary.v1"
_CLOSE_SCHEMA = "schauwerk-classroom-close-receipt.v1"
_SESSION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAX_GROUPS = 12


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _quote(value: str) -> str:
    escaped = value.strip().replace("\n", "<br>").replace('"', "&quot;")
    return f'"{escaped}"'


def _line(identifier: str, kind: str, *, content: str, **attrs: object) -> str:
    parts = [identifier, kind]
    for key, value in attrs.items():
        parts.append(f"{key}={value}")
    parts.append(_quote(content))
    return " ".join(parts)


def _safe_session_id(value: str) -> str:
    normalized = value.strip().lower()
    if not _SESSION_ID.fullmatch(normalized):
        raise DurableError("classroom session id is invalid")
    return normalized


def _default_session_id(source_digest: str, group_count: int, template: str) -> str:
    material = f"{source_digest}:{group_count}:{template}".encode()
    return f"classroom-{hashlib.sha256(material).hexdigest()[:16]}"


def _validate_group_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_GROUPS:
        raise DurableError(f"classroom group_count must be between 1 and {_MAX_GROUPS}")
    return value


def _validate_template(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in CLASSROOM_TEMPLATES:
        raise DurableError(f"unknown classroom template: {value}")
    return normalized


def session_marker(session_id: str) -> str:
    return f"Schauwerk Classroom Session: {_safe_session_id(session_id)}"


def _render_workspace_dsl(
    view: LearningView,
    *,
    group_count: int,
    template: str,
    session_id: str,
) -> str:
    """Extend the existing Learning View with bounded cooperative group regions."""
    base = render_learning_dsl(view).rstrip()
    prompts = CLASSROOM_TEMPLATES[template]
    marker = session_marker(session_id)
    lines = [base]
    lines.append(
        _line(
            "classroom_session_marker",
            "TEXT",
            x=3300,
            y=-180,
            w=1900,
            size=12,
            color="#666666",
            align="center",
            content=marker,
        )
    )
    columns = min(3, group_count)
    frame_width = 760
    frame_height = 1080
    x_origin = 2400
    y_origin = 80
    x_gap = 860
    y_gap = 1180
    for index in range(1, group_count + 1):
        column = (index - 1) % columns
        row = (index - 1) // columns
        frame_id = f"classroom_group_{index}"
        x = x_origin + column * x_gap
        y = y_origin + row * y_gap
        lines.append(
            _line(
                frame_id,
                "FRAME",
                x=x,
                y=y,
                w=frame_width,
                h=frame_height,
                fill="#F7F8FA",
                content=f"Gruppe {index} · Arbeitsbereich",
            )
        )
        for prompt_index, prompt in enumerate(prompts, start=1):
            lines.append(
                _line(
                    f"g{index}_input_{prompt_index}",
                    "STICKY",
                    parent=frame_id,
                    x=frame_width // 2,
                    y=115 + (prompt_index - 1) * 150,
                    w=300,
                    color="light_yellow" if prompt_index % 2 else "light_blue",
                    content=f"<p><b>{prompt}</b></p><p>Hier arbeiten.</p>",
                )
            )
    side_x = x_origin + columns * x_gap + 100
    lines.extend(
        [
            _line(
                "classroom_synthesis",
                "FRAME",
                x=side_x,
                y=y_origin,
                w=820,
                h=760,
                fill="#F5F5F5",
                content="Synthese · Schauwerk-Vorschlag",
            ),
            _line(
                "classroom_synthesis_note",
                "TEXT",
                parent="classroom_synthesis",
                x=410,
                y=170,
                w=650,
                size=18,
                align="left",
                color="#333333",
                content=(
                    "Bleibt bis zur Auswertung leer. Schauwerk darf hier nur einen "
                    "als Vorschlag gekennzeichneten Entwurf vorbereiten."
                ),
            ),
            _line(
                "classroom_reflection",
                "FRAME",
                x=side_x,
                y=y_origin + 860,
                w=820,
                h=760,
                fill="#F5F5F5",
                content="Gemeinsame Reflexion · nach Freigabe",
            ),
            _line(
                "classroom_reflection_note",
                "TEXT",
                parent="classroom_reflection",
                x=410,
                y=170,
                w=650,
                size=18,
                align="left",
                color="#333333",
                content=view.check,
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _write_text(path: Path, text: str, *, mode: int = 0o600) -> Path:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or any(parent.is_symlink() for parent in destination.parents):
        raise DurableError("unsafe classroom output path")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = text.encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, destination)
        destination.chmod(mode)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return destination


def _package_regions(group_count: int) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = [
        {"id": "instruction", "role": "instruction", "management_mode": "managed"},
        {"id": "material", "role": "material", "management_mode": "read-only"},
    ]
    for index in range(1, group_count + 1):
        regions.append(
            {
                "id": f"group-{index}",
                "role": "group_workspace",
                "management_mode": "cooperative",
                "student_output_mode": "manual",
                "visible_marker": f"Gruppe {index} · Arbeitsbereich",
            }
        )
    regions.extend(
        [
            {
                "id": "synthesis",
                "role": "synthesis",
                "management_mode": "suggest-only",
                "visible_marker": "Synthese · Schauwerk-Vorschlag",
            },
            {
                "id": "reflection",
                "role": "reflection",
                "management_mode": "approval-required",
                "visible_marker": "Gemeinsame Reflexion · nach Freigabe",
            },
        ]
    )
    return regions


def prepare_classroom(
    *,
    input_path: Path,
    output_dir: Path,
    group_count: int = 6,
    template: str = "vibe-coding",
    session_id: str | None = None,
    predecessor_close_digest: str | None = None,
) -> dict[str, Any]:
    group_count = _validate_group_count(group_count)
    template = _validate_template(template)
    source = input_path.expanduser().absolute()
    source_bytes = source.read_bytes()
    source_digest = _sha256_bytes(source_bytes)
    resolved_session = _safe_session_id(
        session_id or _default_session_id(source_digest, group_count, template)
    )
    if predecessor_close_digest is not None:
        safe_digest(predecessor_close_digest, label="predecessor close digest")
    view = load_learning_view(source)
    dsl = _render_workspace_dsl(
        view,
        group_count=group_count,
        template=template,
        session_id=resolved_session,
    )
    dsl_digest = _sha256_bytes(dsl.encode("utf-8"))
    base = output_dir.expanduser().absolute()
    manifest_path = base / "manifest.json"
    dsl_path = base / "classroom.dsl"
    manifest: dict[str, Any] = {
        "schema_version": _PACKAGE_SCHEMA,
        "session_id": resolved_session,
        "session_marker": session_marker(resolved_session),
        "topic": view.topic,
        "audience": view.audience,
        "group_count": group_count,
        "classroom_template": template,
        "source_digest": source_digest,
        "dsl_digest": dsl_digest,
        "files": {"dsl": "classroom.dsl"},
        "roles": [dict(item) for item in CLASSROOM_ROLES],
        "regions": _package_regions(group_count),
        "epistemic_contract": {
            "observation": "machine-derived snapshot delta",
            "structural_pattern": "machine-derived counts and types only",
            "interpretation": "not generated by deterministic classroom core",
            "learning_judgement": "prohibited from board activity alone",
        },
        "provider_effects": {
            "prepare": False,
            "start": "separate explicit command",
            "read": False,
            "summarize": False,
            "close": False,
        },
        "predecessor_close_digest": predecessor_close_digest,
    }
    bind_digest(manifest, "package_digest")
    if manifest_path.exists():
        existing = load_classroom_package(base)
        if existing["package_digest"] != manifest["package_digest"]:
            raise DurableError("classroom output directory already contains a different package")
        return {**existing, "replayed": True, "output_dir": str(base)}
    if dsl_path.exists() or dsl_path.is_symlink():
        raise DurableError("classroom output directory contains an unbound DSL")
    _write_text(dsl_path, dsl)
    write_json(manifest_path, manifest)
    return {**manifest, "replayed": False, "output_dir": str(base)}


def load_classroom_package(path: Path) -> dict[str, Any]:
    base = path.expanduser().absolute()
    manifest_path = base / "manifest.json" if base.is_dir() else base
    manifest = read_json(manifest_path, label="classroom manifest")
    if manifest.get("schema_version") != _PACKAGE_SCHEMA:
        raise DurableError("classroom manifest schema is invalid")
    require_bound_digest(manifest, "package_digest", label="classroom manifest")
    dsl_name = (
        manifest.get("files", {}).get("dsl") if isinstance(manifest.get("files"), dict) else None
    )
    if dsl_name != "classroom.dsl":
        raise DurableError("classroom manifest DSL binding is invalid")
    dsl_path = manifest_path.parent / dsl_name
    if dsl_path.is_symlink() or not dsl_path.is_file():
        raise DurableError("classroom DSL is missing or unsafe")
    declared_dsl = safe_digest(manifest.get("dsl_digest"), label="classroom DSL digest")
    actual_dsl = _sha256_bytes(dsl_path.read_bytes())
    if actual_dsl != declared_dsl:
        raise DurableError("classroom DSL digest mismatch")
    return manifest


def stage_classroom_package(prepared_dir: Path, session_dir: Path) -> dict[str, Any]:
    package = load_classroom_package(prepared_dir)
    source_base = prepared_dir.expanduser().absolute()
    target_base = session_dir.expanduser().absolute()
    target_manifest = target_base / "manifest.json"
    target_dsl = target_base / "classroom.dsl"
    if target_manifest.exists():
        existing = load_classroom_package(target_base)
        if existing["package_digest"] != package["package_digest"]:
            raise DurableError("session directory is bound to a different classroom package")
        return existing
    if target_dsl.exists() or target_dsl.is_symlink():
        raise DurableError("session directory contains an unbound DSL")
    _write_text(target_dsl, (source_base / "classroom.dsl").read_text(encoding="utf-8"))
    write_json(target_manifest, package)
    return package


def load_verified_snapshot(path: Path) -> dict[str, Any]:
    value = read_json(path, label="classroom snapshot")
    if value.get("repeatability_verified") is not True or value.get("verified_reads") != 2:
        raise DurableError("classroom snapshot is not repeatability-verified")
    if value.get("sanitized_references") is not True:
        raise DurableError("classroom snapshot does not sanitize provider references")
    declared = safe_digest(value.get("content_digest"), label="classroom snapshot content digest")
    content = {
        "schema_version": value.get("schema_version"),
        "board_alias": value.get("board_alias"),
        "items": value.get("items"),
        "comments": value.get("comments"),
    }
    if not isinstance(content["items"], list) or not isinstance(content["comments"], list):
        raise DurableError("classroom snapshot items/comments are invalid")
    if snapshot_content_digest(content) != declared:
        raise DurableError("classroom snapshot content digest mismatch")
    return value


def snapshot_contains_marker(path: Path, marker: str) -> bool:
    value = load_verified_snapshot(path)
    rendered = json.dumps(value.get("items", []), ensure_ascii=False, sort_keys=True)
    return marker in rendered


def _item_map(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("items", []):
        if not isinstance(item, dict):
            raise DurableError("classroom snapshot contains a non-object item")
        ref = item.get("ref")
        if not isinstance(ref, str) or not ref:
            raise DurableError("classroom snapshot item is missing a stable ref")
        if ref in result:
            raise DurableError("classroom snapshot contains a duplicate stable ref")
        result[ref] = item
    return result


def _type_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("type", "unknown")) for item in items)
    return dict(sorted(counts.items()))


def summarize_snapshots(
    *, before_path: Path, after_path: Path, output: Path | None = None
) -> dict[str, Any]:
    before = load_verified_snapshot(before_path)
    after = load_verified_snapshot(after_path)
    if before.get("board_alias") != after.get("board_alias"):
        raise DurableError("classroom snapshots belong to different board aliases")
    before_items = _item_map(before)
    after_items = _item_map(after)
    before_refs = set(before_items)
    after_refs = set(after_items)
    added_refs = sorted(after_refs - before_refs)
    removed_refs = sorted(before_refs - after_refs)
    common_refs = sorted(before_refs & after_refs)
    changed_refs = [
        ref
        for ref in common_refs
        if stable_digest(before_items[ref]) != stable_digest(after_items[ref])
    ]
    added = [after_items[ref] for ref in added_refs]
    removed = [before_items[ref] for ref in removed_refs]
    changed = [after_items[ref] for ref in changed_refs]
    observations = [
        {"kind": "items_added", "count": len(added_refs)},
        {"kind": "items_removed", "count": len(removed_refs)},
        {"kind": "items_changed", "count": len(changed_refs)},
        {
            "kind": "comments_delta",
            "count": len(after.get("comments", [])) - len(before.get("comments", [])),
        },
    ]
    structural_patterns = {
        "added_item_types": _type_counts(added),
        "removed_item_types": _type_counts(removed),
        "changed_item_types": _type_counts(changed),
    }
    summary: dict[str, Any] = {
        "schema_version": _SUMMARY_SCHEMA,
        "board_alias": before.get("board_alias"),
        "before_content_digest": before["content_digest"],
        "after_content_digest": after["content_digest"],
        "observations": observations,
        "structural_patterns": structural_patterns,
        "changed_refs": {
            "added": added_refs,
            "removed": removed_refs,
            "changed": changed_refs,
        },
        "interpretations": [],
        "interpretation_status": "not_generated_by_deterministic_core",
        "learning_judgement": "not_established",
        "does_not_establish": [
            "individual_authorship",
            "student_identity",
            "learning_progress",
            "understanding",
            "quality_of_student_work",
            "pedagogical_causality",
        ],
    }
    bind_digest(summary, "summary_digest")
    if output is not None:
        write_json(output, summary)
    return summary


def close_classroom_session(*, session_dir: Path, final_snapshot: Path) -> dict[str, Any]:
    base = session_dir.expanduser().absolute()
    package = load_classroom_package(base)
    before = base / "started.json"
    if not before.is_file():
        raise DurableError("classroom session has no verified before snapshot")
    summary_path = base / "summary.json"
    summary = summarize_snapshots(
        before_path=before,
        after_path=final_snapshot,
        output=summary_path,
    )
    receipt: dict[str, Any] = {
        "schema_version": _CLOSE_SCHEMA,
        "session_id": package["session_id"],
        "package_digest": package["package_digest"],
        "before_content_digest": summary["before_content_digest"],
        "final_content_digest": summary["after_content_digest"],
        "summary_digest": summary["summary_digest"],
        "summary_file": "summary.json",
        "provider_mutation_attempted": False,
        "student_work_modified_by_close": False,
        "interpretation_status": summary["interpretation_status"],
    }
    bind_digest(receipt, "close_digest")
    write_json(base / "close-receipt.json", receipt)
    return receipt


def continue_classroom(
    *,
    previous_session_dir: Path,
    next_input_path: Path,
    output_dir: Path,
    group_count: int,
    template: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    close_path = previous_session_dir.expanduser().absolute() / "close-receipt.json"
    close = read_json(close_path, label="classroom close receipt")
    if close.get("schema_version") != _CLOSE_SCHEMA:
        raise DurableError("classroom close receipt schema is invalid")
    close_digest = require_bound_digest(close, "close_digest", label="classroom close receipt")
    result = prepare_classroom(
        input_path=next_input_path,
        output_dir=output_dir,
        group_count=group_count,
        template=template,
        session_id=session_id,
        predecessor_close_digest=close_digest,
    )
    return {**result, "continued_from": close_digest}
