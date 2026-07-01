"""Local lifecycle index for fresh Miro live-test boards."""

from __future__ import annotations

import json
import re
import shutil
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .board_registry import BoardAllowlist, validate_alias
from .credentials import write_json_owner_only
from .errors import MiroCredentialError
from .models import MiroSettings

_SCHEMA_VERSION = 1
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class LiveTestRecord:
    alias: str
    reference_digest: str
    topic: str
    board_name: str
    output_dir: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveTestPruneReceipt:
    keep: int
    dry_run: bool
    records_seen: int
    records_kept: int
    records_pruned: int
    aliases_to_prune: tuple[str, ...]
    aliases_pruned: tuple[str, ...]
    output_dirs_to_retire: tuple[str, ...]
    output_dirs_retired: tuple[str, ...]
    output_dirs_skipped: tuple[str, ...]
    index_updated: bool
    remote_cleanup_attempted: bool = False
    remote_cleanup_supported: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "aliases_to_prune",
            "aliases_pruned",
            "output_dirs_to_retire",
            "output_dirs_retired",
            "output_dirs_skipped",
        ):
            value[key] = list(value[key])
        return value


def live_test_index_path(settings: MiroSettings) -> Path:
    return settings.snapshots_root / "live-tests" / "index.json"


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_index_document(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"schema_version": _SCHEMA_VERSION, "records": []}
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MiroCredentialError("Live-test index path is unsafe")
    if metadata.st_mode & 0o077:
        raise MiroCredentialError("Live-test index must have mode 0600")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MiroCredentialError("Live-test index is unreadable or corrupt") from exc
    if not isinstance(document, dict):
        raise MiroCredentialError("Live-test index must contain a JSON object")
    if document.get("schema_version") != _SCHEMA_VERSION:
        raise MiroCredentialError("Live-test index has an unsupported schema version")
    if not isinstance(document.get("records"), list):
        raise MiroCredentialError("Live-test index records must be a list")
    return document


def _coerce_record(item: Any) -> LiveTestRecord | None:
    if not isinstance(item, dict):
        return None
    values: dict[str, str] = {}
    for key in ("alias", "reference_digest", "topic", "board_name", "output_dir", "created_at"):
        value = item.get(key)
        if not isinstance(value, str):
            return None
        values[key] = value
    try:
        values["alias"] = validate_alias(values["alias"])
    except ValueError:
        return None
    return LiveTestRecord(**values)


def read_live_test_records(settings: MiroSettings) -> tuple[LiveTestRecord, ...]:
    document = _read_index_document(live_test_index_path(settings))
    records = []
    for item in document["records"]:
        record = _coerce_record(item)
        if record is not None:
            records.append(record)
    return tuple(records)


def write_live_test_records(
    settings: MiroSettings, records: tuple[LiveTestRecord, ...] | list[LiveTestRecord]
) -> None:
    write_json_owner_only(
        live_test_index_path(settings),
        {
            "schema_version": _SCHEMA_VERSION,
            "records": [record.to_dict() for record in records],
        },
    )


def append_live_test_record(settings: MiroSettings, record: LiveTestRecord) -> LiveTestRecord:
    current = list(read_live_test_records(settings))
    current.append(record)
    write_live_test_records(settings, current)
    return record


def create_live_test_record(
    settings: MiroSettings,
    *,
    alias: str,
    reference_digest: str,
    topic: str,
    board_name: str,
    output_dir: Path | str,
    created_at: str | None = None,
) -> LiveTestRecord:
    return append_live_test_record(
        settings,
        LiveTestRecord(
            alias=validate_alias(alias),
            reference_digest=reference_digest,
            topic=topic,
            board_name=board_name,
            output_dir=str(output_dir),
            created_at=created_at or utc_timestamp(),
        ),
    )


def _sort_key(indexed: tuple[int, LiveTestRecord]) -> tuple[str, int]:
    index, record = indexed
    return (record.created_at, index)


def _clean_path_component(value: str) -> str:
    cleaned = _SAFE_NAME.sub("-", value.strip()).strip(".-_")
    return cleaned[:96] or "live-test"


def _retired_root(settings: MiroSettings) -> Path:
    return live_test_index_path(settings).parent / "retired"


def _planned_retire_target(settings: MiroSettings, record: LiveTestRecord) -> Path:
    source = Path(record.output_dir)
    timestamp = _clean_path_component(record.created_at.replace(":", ""))
    source_name = _clean_path_component(source.name)
    return _retired_root(settings) / f"{record.alias}-{timestamp}-{source_name}"


def _unique_target(path: Path) -> Path:
    if not path.exists() and not path.is_symlink():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.name}-{counter}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise MiroCredentialError("Could not allocate a unique retired live-test path")


def _retire_output_dir(
    settings: MiroSettings, record: LiveTestRecord, *, dry_run: bool
) -> tuple[str | None, str | None]:
    source = Path(record.output_dir)
    target = _planned_retire_target(settings, record)
    plan = f"{source} -> {target}"
    try:
        if source.is_symlink():
            return plan, f"{source}: skipped symlink"
        if not source.exists():
            return plan, f"{source}: skipped missing"
        if not source.is_dir():
            return plan, f"{source}: skipped non-directory"
        source_resolved = source.resolve(strict=False)
        live_root = live_test_index_path(settings).parent.resolve(strict=False)
        retired_resolved = _retired_root(settings).resolve(strict=False)
        if source_resolved == live_root:
            return plan, f"{source}: skipped live-tests root"
        if source_resolved == retired_resolved or source_resolved.is_relative_to(retired_resolved):
            return plan, f"{source}: skipped already retired"
        if dry_run:
            return plan, None
        target = _unique_target(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return f"{source} -> {target}", None
    except OSError as exc:
        return plan, f"{source}: skipped move error: {exc.__class__.__name__}"


def prune_live_tests(
    settings: MiroSettings, *, keep: int, dry_run: bool = False
) -> LiveTestPruneReceipt:
    if keep < 0:
        raise ValueError("keep must be non-negative")

    records = list(read_live_test_records(settings))
    ordered = sorted(enumerate(records), key=_sort_key, reverse=True)
    kept_indices = {index for index, _record in ordered[:keep]}
    kept_records = [record for _index, record in ordered[:keep]]
    pruned_records = [record for index, record in enumerate(records) if index not in kept_indices]
    kept_aliases = {record.alias for record in kept_records}
    aliases_to_prune = tuple(
        sorted({record.alias for record in pruned_records if record.alias not in kept_aliases})
    )

    output_dirs_to_retire = []
    output_dirs_retired = []
    output_dirs_skipped = []
    for record in pruned_records:
        planned, skipped = _retire_output_dir(settings, record, dry_run=dry_run)
        if planned is not None:
            output_dirs_to_retire.append(planned)
            if skipped is None and not dry_run:
                output_dirs_retired.append(planned)
        if skipped is not None:
            output_dirs_skipped.append(skipped)

    aliases_pruned: list[str] = []
    index_updated = False
    if not dry_run:
        allowlist = BoardAllowlist(settings.board_allowlist_path)
        for alias in aliases_to_prune:
            if allowlist.remove(alias):
                aliases_pruned.append(alias)
        write_live_test_records(settings, kept_records)
        index_updated = True

    return LiveTestPruneReceipt(
        keep=keep,
        dry_run=dry_run,
        records_seen=len(records),
        records_kept=len(kept_records),
        records_pruned=len(pruned_records),
        aliases_to_prune=aliases_to_prune,
        aliases_pruned=tuple(aliases_pruned),
        output_dirs_to_retire=tuple(output_dirs_to_retire),
        output_dirs_retired=tuple(output_dirs_retired),
        output_dirs_skipped=tuple(output_dirs_skipped),
        index_updated=index_updated,
    )
