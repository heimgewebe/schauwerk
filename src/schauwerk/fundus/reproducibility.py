"""Read-only drift and temporary-state reproduction checks for Fundus builds."""

from __future__ import annotations

import json
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .core import Fundus, FundusPaths
from .errors import FundusError
from .model import BUILD_SCHEMA_V2

REPRODUCTION_SCHEMA = "schauwerk-fundus-reproduction.v1"
REPRODUCTION_SCHEMA_FILE = "fundus-reproduction.v1.schema.json"


def _validate_report(report: dict[str, Any]) -> dict[str, Any]:
    schema = json.loads(
        resources.files("schauwerk.schemas")
        .joinpath(REPRODUCTION_SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )
    try:
        Draft202012Validator(schema).validate(report)
    except ValidationError as exc:
        raise FundusError(
            f"Fundus reproduction report schema validation failed: {exc.message}"
        ) from exc
    return report


def _build_sources(build: dict[str, Any]) -> list[dict[str, Any]]:
    if build.get("schema_version") == BUILD_SCHEMA_V2:
        return [dict(item) for item in build["sources"]]
    return [dict(build["source"])]


def _source_check(
    fundus: Fundus,
    asset_id: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    object_ok = True
    provenance_ok = True
    try:
        fundus._read_object(source["sha256"])
    except FundusError as exc:
        object_ok = False
        errors.append(str(exc))
    try:
        fundus._validate_source_image_brief(asset_id, source)
    except FundusError as exc:
        provenance_ok = False
        errors.append(str(exc))
    return {
        "role": source["role"],
        "sha256": source["sha256"],
        "object_ok": object_ok,
        "provenance_ok": provenance_ok,
        "error": "; ".join(errors) if errors else None,
    }


def drift_build(
    fundus: Fundus,
    asset_id: str,
    build_digest: str,
) -> dict[str, Any]:
    """Compare one stored build with current registry and source authority read-only."""
    build, _ = fundus._load_build(asset_id, build_digest)
    expected_asset_digest = build["asset_manifest_sha256"]
    expected_recipe_id = build["recipe_id"]
    expected_recipe_digest = build["recipe_sha256"]

    observed_asset_digest: str | None = None
    try:
        _, observed_asset_digest, _ = fundus._asset(asset_id)
    except FundusError:
        observed_asset_digest = None

    observed_recipe_digest: str | None = None
    try:
        _, observed_recipe_digest, _ = fundus._recipe(expected_recipe_id)
    except FundusError:
        observed_recipe_digest = None

    source_checks = [
        _source_check(fundus, asset_id, source) for source in _build_sources(build)
    ]
    asset_match = observed_asset_digest == expected_asset_digest
    recipe_match = observed_recipe_digest == expected_recipe_digest
    sources_match = all(
        item["object_ok"] and item["provenance_ok"] for item in source_checks
    )
    ok = asset_match and recipe_match and sources_match
    report = {
        "schema_version": REPRODUCTION_SCHEMA,
        "operation": "drift",
        "asset_id": asset_id,
        "build_digest": build_digest,
        "status": "clean" if ok else "drifted",
        "ok": ok,
        "asset_manifest_expected_sha256": expected_asset_digest,
        "asset_manifest_observed_sha256": observed_asset_digest,
        "asset_manifest_match": asset_match,
        "recipe_id": expected_recipe_id,
        "recipe_expected_sha256": expected_recipe_digest,
        "recipe_observed_sha256": observed_recipe_digest,
        "recipe_match": recipe_match,
        "source_checks": source_checks,
        "reproduction": None,
        "canonical_state_mutated": False,
    }
    return _validate_report(report)


def _copy_optional_receipt(
    source: Fundus,
    target: Fundus,
    relative: Path,
    *,
    maximum_bytes: int,
) -> None:
    source_path = source.root / relative
    if not source_path.exists():
        return
    payload = source._read_private(source_path, maximum_bytes=maximum_bytes)
    target._write_create_or_verify(target.root / relative, payload)


def _copy_reproduction_inputs(
    source: Fundus,
    target: Fundus,
    build: dict[str, Any],
) -> None:
    for record in _build_sources(build):
        sha256 = record["sha256"]
        target._write_create_or_verify(
            target._object_path(sha256),
            source._read_object(sha256),
        )
        _copy_optional_receipt(
            source,
            target,
            Path("receipts") / "ingest" / f"{sha256}.json",
            maximum_bytes=128_000,
        )
        brief_sha = record.get("image_brief_sha256")
        if brief_sha is not None:
            _copy_optional_receipt(
                source,
                target,
                Path("receipts") / "image-briefs" / f"{brief_sha}.json",
                maximum_bytes=256_000,
            )


def _reproduction_result(
    *,
    attempted: bool,
    build_digest: str | None,
    build_digest_match: bool | None,
    output_sha256s_match: bool | None,
    toolchain_match: bool | None,
    temporary_state_used: bool,
    error: str | None,
) -> dict[str, Any]:
    return {
        "attempted": attempted,
        "build_digest": build_digest,
        "build_digest_match": build_digest_match,
        "output_sha256s_match": output_sha256s_match,
        "toolchain_match": toolchain_match,
        "temporary_state_used": temporary_state_used,
        "error": error,
    }


def _as_reproduce_report(
    drift: dict[str, Any],
    *,
    status: str,
    ok: bool,
    reproduction: dict[str, Any],
) -> dict[str, Any]:
    report = {
        **drift,
        "operation": "reproduce",
        "status": status,
        "ok": ok,
        "reproduction": reproduction,
        "canonical_state_mutated": False,
    }
    return _validate_report(report)


def reproduce_build(
    fundus: Fundus,
    asset_id: str,
    build_digest: str,
) -> dict[str, Any]:
    """Rebuild one exact build in temporary state and compare deterministic identity."""
    preflight = drift_build(fundus, asset_id, build_digest)
    if not preflight["ok"]:
        return _as_reproduce_report(
            preflight,
            status="drifted",
            ok=False,
            reproduction=_reproduction_result(
                attempted=False,
                build_digest=None,
                build_digest_match=None,
                output_sha256s_match=None,
                toolchain_match=None,
                temporary_state_used=False,
                error="reproduction blocked by current binding drift",
            ),
        )

    baseline, _ = fundus._load_build(asset_id, build_digest)
    observed_build: dict[str, Any] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="schauwerk-fundus-reproduce-") as temporary:
            temporary_root = Path(temporary) / "fundus"
            candidate = Fundus(
                FundusPaths.from_overrides(
                    data_root=temporary_root,
                    registry_root=fundus.paths.registry_root,
                )
            )
            _copy_reproduction_inputs(fundus, candidate, baseline)
            observed_build = candidate.build(asset_id)
    except (FundusError, OSError, ValueError) as exc:
        return _as_reproduce_report(
            drift_build(fundus, asset_id, build_digest),
            status="reproduction_failed",
            ok=False,
            reproduction=_reproduction_result(
                attempted=True,
                build_digest=None,
                build_digest_match=False,
                output_sha256s_match=None,
                toolchain_match=None,
                temporary_state_used=True,
                error=str(exc),
            ),
        )

    postflight = drift_build(fundus, asset_id, build_digest)
    if not postflight["ok"]:
        return _as_reproduce_report(
            postflight,
            status="drifted",
            ok=False,
            reproduction=_reproduction_result(
                attempted=True,
                build_digest=observed_build["build_digest"],
                build_digest_match=observed_build["build_digest"] == build_digest,
                output_sha256s_match=None,
                toolchain_match=None,
                temporary_state_used=True,
                error="canonical bindings changed during reproduction",
            ),
        )

    expected_outputs = [item["sha256"] for item in baseline["outputs"]]
    observed_outputs = [item["sha256"] for item in observed_build["outputs"]]
    build_match = observed_build["build_digest"] == build_digest
    output_match = observed_outputs == expected_outputs
    toolchain_match = observed_build["toolchain"] == baseline["toolchain"]
    ok = build_match and output_match and toolchain_match
    return _as_reproduce_report(
        postflight,
        status="reproduced" if ok else "reproduction_drift",
        ok=ok,
        reproduction=_reproduction_result(
            attempted=True,
            build_digest=observed_build["build_digest"],
            build_digest_match=build_match,
            output_sha256s_match=output_match,
            toolchain_match=toolchain_match,
            temporary_state_used=True,
            error=None if ok else "reproduced build identity differs from stored build",
        ),
    )
