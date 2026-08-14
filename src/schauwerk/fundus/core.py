"""Content-addressed source, build, review and package lifecycle for Fundus."""

from __future__ import annotations

import ast
import base64
import html
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import FundusError
from .media import MAX_SOURCE_BYTES, inspect_media
from .model import (
    ACCEPTANCE_SCHEMA,
    BUILD_SCHEMA,
    BUILD_SCHEMA_V2,
    IMAGE_BRIEF_SCHEMA,
    INGEST_SCHEMA,
    PACKAGE_SCHEMA,
    PACKAGE_SCHEMA_V2,
    PREVIEW_SCHEMA,
    RECIPE_SCHEMA_V2,
    canonical_json,
    checked_id,
    checked_sha256,
    digest_bytes,
    digest_json,
    load_json,
    validate_asset,
    validate_family,
    validate_image_brief,
    validate_recipe,
)
from .package_contract import (
    canonical_consumer_lock_bytes,
    consumer_lock_manifest,
    verify_package_directory,
)
from .pathio import (
    normalized_absolute,
    open_directory_chain,
    read_regular_bytes,
)
from .pathio import (
    write_create_or_verify as write_immutable_file,
)
from .raster import (
    MAX_RASTER_OUTPUT_BYTES,
    RASTER_PROFILE,
    normalize_raster,
    raster_adapter_status,
)
from .svg import sanitize_svg
from .trace import TRACE_PROFILES, trace_adapter_status, trace_raster

TOOLCHAIN_VERSION = "schauwerk-fundus-core.v1"
MAX_BUILD_OUTPUT_BYTES = MAX_RASTER_OUTPUT_BYTES
MAX_PREVIEW_RASTER_BYTES = MAX_RASTER_OUTPUT_BYTES
FORBIDDEN_IMPORT_PREFIXES = (
    "schauwerk.surfaces.miro",
    "schauwerk.operator",
)


@dataclass(frozen=True)
class FundusPaths:
    data_root: Path
    registry_root: Path

    @classmethod
    def from_overrides(
        cls,
        *,
        data_root: str | Path | None = None,
        registry_root: str | Path | None = None,
    ) -> FundusPaths:
        if data_root is None:
            explicit = os.environ.get("SCHAUWERK_FUNDUS_ROOT")
            if explicit:
                data = Path(explicit)
            else:
                xdg = os.environ.get("XDG_DATA_HOME")
                base = (
                    Path(xdg)
                    if xdg
                    else Path.home() / ".local" / "share"
                )
                data = base / "schauwerk" / "fundus"
        else:
            data = Path(data_root)
        if registry_root is None:
            explicit_registry = os.environ.get(
                "SCHAUWERK_FUNDUS_REGISTRY"
            )
            registry = (
                Path(explicit_registry)
                if explicit_registry
                else Path.cwd() / "registry" / "fundus"
            )
        else:
            registry = Path(registry_root)
        return cls(
            normalized_absolute(data, label="Fundus data root"),
            normalized_absolute(registry, label="Fundus registry root"),
        )


class Fundus:
    def __init__(self, paths: FundusPaths):
        self.paths = paths

    @property
    def root(self) -> Path:
        return self.paths.data_root

    def _ensure_private_dir(self, path: Path) -> None:
        target = normalized_absolute(path, label="Fundus state directory")
        root = normalized_absolute(self.root, label="Fundus data root")
        if target != root and root not in target.parents:
            raise FundusError("Fundus state directory escaped the configured root")
        descriptor = open_directory_chain(
            target,
            create=True,
            private_root=root,
        )
        os.close(descriptor)

    def _ensure_state(self) -> None:
        for path in (
            self.root,
            self.root / "objects" / "sha256",
            self.root / "receipts" / "ingest",
            self.root / "receipts" / "image-briefs",
            self.root / "builds",
            self.root / "previews",
            self.root / "acceptances",
            self.root / "packages",
        ):
            self._ensure_private_dir(path)

    def _write_create_or_verify(
        self,
        path: Path,
        payload: bytes,
    ) -> None:
        write_immutable_file(
            path,
            payload,
            private_root=self.root,
        )

    def _write_json_create_or_verify(
        self,
        path: Path,
        value: dict[str, Any],
    ) -> None:
        self._write_create_or_verify(
            path,
            canonical_json(value) + b"\n",
        )

    def _read_private(
        self,
        path: Path,
        *,
        maximum_bytes: int = MAX_SOURCE_BYTES + 1,
    ) -> bytes:
        return read_regular_bytes(
            path,
            maximum_bytes=maximum_bytes,
            label="Fundus artifact",
            require_owner=True,
            forbidden_mode_bits=0o077,
            private_root=self.root,
        )

    def _read_source(self, path: Path) -> bytes:
        payload = read_regular_bytes(
            path,
            maximum_bytes=MAX_SOURCE_BYTES,
            label="source",
            require_owner=True,
            forbidden_mode_bits=0o022,
        )
        if not payload:
            raise FundusError("source media is empty")
        return payload

    def _object_path(self, sha256: str) -> Path:
        checked_sha256(sha256)
        return (
            self.root
            / "objects"
            / "sha256"
            / sha256[:2]
            / sha256
        )

    def image_brief(self, path: str | Path) -> dict[str, Any]:
        brief_path = normalized_absolute(path, label="image brief path")
        try:
            value = load_json(brief_path, maximum_bytes=256_000)
            validate_image_brief(value)
        except (OSError, ValueError) as exc:
            raise FundusError(str(exc)) from exc
        if value["operation"] == "edit":
            input_sha256 = value["input_sha256"]
            self._read_object(input_sha256)
            ingest_path = (
                self.root
                / "receipts"
                / "ingest"
                / f"{input_sha256}.json"
            )
            if not ingest_path.exists():
                raise FundusError(
                    "edit input is not a completed Fundus ingest: receipt is missing"
                )
            try:
                ingest = json.loads(
                    self._read_private(ingest_path, maximum_bytes=128_000)
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise FundusError("edit input ingest receipt is invalid") from exc
            if (
                ingest.get("schema_version") != INGEST_SCHEMA
                or ingest.get("sha256") != input_sha256
            ):
                raise FundusError(
                    "edit input ingest receipt does not bind the input sha256"
                )
        brief_sha256 = digest_json(value)
        self._ensure_state()
        self._write_json_create_or_verify(
            self.root
            / "receipts"
            / "image-briefs"
            / f"{brief_sha256}.json",
            value,
        )
        return {
            "schema_version": IMAGE_BRIEF_SCHEMA,
            "id": value["id"],
            "asset_id": value["asset_id"],
            "operation": value["operation"],
            "source_role": value["source_role"],
            **(
                {"input_sha256": value["input_sha256"]}
                if "input_sha256" in value
                else {}
            ),
            "image_brief_sha256": brief_sha256,
            "prepared": True,
        }

    @staticmethod
    def _origin_source_mode(origin: str) -> str | None:
        lowered = origin.casefold()
        generated_prefixes = (
            "chatgpt-images:",
            "openai-images:",
            "image_gen:",
            "ai-generated:",
        )
        edited_prefixes = (
            "chatgpt-image-edit:",
            "openai-image-edit:",
            "ai-edited:",
        )
        if lowered.startswith(generated_prefixes):
            return "generated"
        if lowered.startswith(edited_prefixes):
            return "edited"
        return None

    def ingest(
        self,
        source_path: str | Path,
        *,
        origin: str = "unknown",
        rights_status: str = "unknown",
        source_mode: str | None = None,
        image_brief_path: str | Path | None = None,
    ) -> dict[str, Any]:
        path = normalized_absolute(source_path, label="source path")
        payload = self._read_source(path)
        media = inspect_media(payload)
        sha256 = digest_bytes(payload)

        if rights_status not in {
            "owned",
            "licensed",
            "unknown",
            "restricted",
        }:
            raise FundusError("rights_status is invalid")
        origin = origin.strip()
        if not origin or len(origin) > 200:
            raise FundusError(
                "origin must be bounded non-empty text"
            )

        object_path = self._object_path(sha256)
        receipt_path = (
            self.root
            / "receipts"
            / "ingest"
            / f"{sha256}.json"
        )
        if receipt_path.exists():
            existing = json.loads(
                self._read_private(receipt_path, maximum_bytes=64_000)
            )
            if existing.get("sha256") != sha256:
                raise FundusError(
                    "ingest receipt does not match content object"
                )
            if existing.get("origin") != origin:
                raise FundusError(
                    "identical bytes were ingested with conflicting origin"
                )
            if existing.get("rights_status") != rights_status:
                raise FundusError(
                    "identical bytes were ingested with conflicting rights_status"
                )
            if (
                source_mode is not None
                and existing.get("source_mode", "unknown") != source_mode
            ):
                raise FundusError(
                    "identical bytes were ingested with conflicting source_mode"
                )
            if image_brief_path is not None:
                brief_path = normalized_absolute(
                    image_brief_path, label="image brief path"
                )
                try:
                    existing_brief = load_json(
                        brief_path, maximum_bytes=256_000
                    )
                    validate_image_brief(existing_brief)
                except (OSError, ValueError) as exc:
                    raise FundusError(str(exc)) from exc
                if existing.get("image_brief_sha256") != digest_json(
                    existing_brief
                ):
                    raise FundusError(
                        "identical bytes were ingested with conflicting image brief"
                    )
            object_payload = self._read_object(sha256)
            if object_payload != payload:
                raise FundusError("source object content drifted")
            return existing

        brief: dict[str, Any] | None = None
        brief_sha256: str | None = None
        if image_brief_path is not None:
            brief_path = normalized_absolute(
                image_brief_path, label="image brief path"
            )
            try:
                brief = load_json(brief_path, maximum_bytes=256_000)
                validate_image_brief(brief)
            except (OSError, ValueError) as exc:
                raise FundusError(str(exc)) from exc
            brief_sha256 = digest_json(brief)
            prepared_path = (
                self.root
                / "receipts"
                / "image-briefs"
                / f"{brief_sha256}.json"
            )
            if not prepared_path.exists():
                raise FundusError(
                    "image brief must be prepared before generated or edited ingest"
                )
            prepared = json.loads(
                self._read_private(prepared_path, maximum_bytes=256_000)
            )
            if digest_json(prepared) != brief_sha256 or prepared != brief:
                raise FundusError("prepared image brief binding is invalid")

        inferred_mode = self._origin_source_mode(origin)
        if source_mode is None:
            if brief is not None:
                source_mode = (
                    "generated" if brief["operation"] == "generate" else "edited"
                )
            else:
                source_mode = inferred_mode or "unknown"
        if source_mode not in {"manual", "generated", "edited", "unknown"}:
            raise FundusError("source_mode is invalid")
        if inferred_mode is not None and source_mode != inferred_mode:
            raise FundusError(
                "source_mode conflicts with the declared generative origin"
            )
        if source_mode in {"generated", "edited"} and brief is None:
            raise FundusError(
                "generated or edited sources require a Fundus image brief"
            )
        if brief is not None:
            expected_operation = (
                "generate" if source_mode == "generated" else "edit"
            )
            if source_mode not in {"generated", "edited"}:
                raise FundusError(
                    "an image brief requires generated or edited source_mode"
                )
            if brief["operation"] != expected_operation:
                raise FundusError(
                    "image brief operation conflicts with source_mode"
                )

        self._ensure_state()
        self._write_create_or_verify(object_path, payload)
        receipt = {
            "schema_version": INGEST_SCHEMA,
            "sha256": sha256,
            "bytes": len(payload),
            **media.to_dict(),
            "origin": origin,
            "rights_status": rights_status,
            "source_mode": source_mode,
            **(
                {"image_brief_sha256": brief_sha256}
                if brief_sha256 is not None
                else {}
            ),
            "source_path_sha256": digest_bytes(
                str(path).encode("utf-8")
            ),
            "ingested_at": datetime.now(
                UTC
            ).isoformat(),
            "object_relpath": str(
                object_path.relative_to(self.root)
            ),
            "provenance_claim_is_declarative": True,
        }
        self._write_json_create_or_verify(
            receipt_path,
            receipt,
        )
        return receipt

    def _registry_manifest(
        self,
        collection: str,
        identifier: str,
    ) -> tuple[dict[str, Any], str, Path]:
        checked_id(identifier)
        path = (
            self.paths.registry_root
            / collection
            / f"{identifier}.json"
        )
        if not path.exists():
            raise FundusError(
                f"Fundus {collection[:-1]} is not declared: "
                f"{identifier}"
            )
        try:
            value = load_json(path)
        except (OSError, ValueError) as exc:
            raise FundusError(str(exc)) from exc
        return value, digest_json(value), path

    def _family(
        self,
        identifier: str,
    ) -> tuple[dict[str, Any], str, Path]:
        value, digest, path = self._registry_manifest(
            "families",
            identifier,
        )
        try:
            validate_family(value)
        except ValueError as exc:
            raise FundusError(str(exc)) from exc
        if value["id"] != identifier:
            raise FundusError(
                "family id does not match registry filename"
            )
        return value, digest, path

    def _asset(
        self,
        identifier: str,
    ) -> tuple[dict[str, Any], str, Path]:
        value, digest, path = self._registry_manifest(
            "assets",
            identifier,
        )
        try:
            validate_asset(value)
        except ValueError as exc:
            raise FundusError(str(exc)) from exc
        if value["id"] != identifier:
            raise FundusError(
                "asset id does not match registry filename"
            )
        family = value.get("family")
        if family is not None:
            self._family(family)
        return value, digest, path

    def _recipe(
        self,
        identifier: str,
    ) -> tuple[dict[str, Any], str, Path]:
        value, digest, path = self._registry_manifest(
            "recipes",
            identifier,
        )
        try:
            validate_recipe(value)
        except ValueError as exc:
            raise FundusError(str(exc)) from exc
        if value["id"] != identifier:
            raise FundusError(
                "recipe id does not match registry filename"
            )
        return value, digest, path

    def inspect(self, asset_id: str) -> dict[str, Any]:
        asset, asset_digest, path = self._asset(asset_id)
        sources = []
        for source in asset["sources"]:
            object_path = self._object_path(source["sha256"])
            sources.append(
                {
                    "role": source["role"],
                    "sha256": source["sha256"],
                    "media_type": source["media_type"],
                    "object_present": object_path.exists(),
                }
            )
        build_root = self.root / "builds" / asset_id
        builds = []
        if build_root.exists():
            builds = sorted(
                item.name
                for item in build_root.iterdir()
                if item.is_dir()
            )
        return {
            "asset_id": asset_id,
            "asset_manifest": str(path),
            "asset_manifest_sha256": asset_digest,
            "family": asset.get("family"),
            "recipe": asset["recipe"],
            "sources": sources,
            "build_digests": builds,
        }

    def _read_object(self, sha256: str) -> bytes:
        path = self._object_path(sha256)
        if not path.exists():
            raise FundusError(
                f"source object is missing: {sha256}"
            )
        payload = self._read_private(path)
        if digest_bytes(payload) != sha256:
            raise FundusError(
                "source object digest mismatch"
            )
        return payload

    def _validate_source_image_brief(
        self,
        asset_id: str,
        source: dict[str, Any],
        *,
        output_roles: list[str] | None = None,
        asset_properties: dict[str, bool] | None = None,
    ) -> None:
        asset_mode = source.get("source_mode", "unknown")
        asset_brief_sha256 = source.get("image_brief_sha256")
        ingest_path = (
            self.root
            / "receipts"
            / "ingest"
            / f"{source['sha256']}.json"
        )
        ingest: dict[str, Any] | None = None
        if ingest_path.exists():
            ingest = json.loads(
                self._read_private(ingest_path, maximum_bytes=128_000)
            )
        ingest_mode = (
            ingest.get("source_mode", "unknown")
            if ingest is not None
            else "unknown"
        )
        ingest_brief_sha256 = (
            ingest.get("image_brief_sha256")
            if ingest is not None
            else None
        )

        if ingest_mode in {"generated", "edited"}:
            if "source_mode" not in source or asset_mode != ingest_mode:
                raise FundusError(
                    "generated or edited asset source must preserve ingest source_mode"
                )
            if (
                asset_brief_sha256 is None
                or asset_brief_sha256 != ingest_brief_sha256
            ):
                raise FundusError(
                    "generated or edited asset source must preserve ingest image brief"
                )
        elif asset_mode in {"generated", "edited"}:
            if ingest is None:
                raise FundusError("source ingest receipt is missing")
            raise FundusError("asset source_mode does not match ingest receipt")
        else:
            if asset_brief_sha256 is not None:
                raise FundusError(
                    "image brief binding requires generated or edited source_mode"
                )
            return

        assert asset_brief_sha256 is not None
        checked_sha256(asset_brief_sha256, label="image brief sha256")
        brief_path = (
            self.root
            / "receipts"
            / "image-briefs"
            / f"{asset_brief_sha256}.json"
        )
        if not brief_path.exists():
            raise FundusError("bound image brief receipt is missing")
        brief = json.loads(
            self._read_private(brief_path, maximum_bytes=256_000)
        )
        try:
            validate_image_brief(brief)
        except ValueError as exc:
            raise FundusError(str(exc)) from exc
        if digest_json(brief) != asset_brief_sha256:
            raise FundusError("bound image brief digest mismatch")
        if brief["asset_id"] != asset_id:
            raise FundusError("image brief targets another asset")
        if brief["source_role"] != source["role"]:
            raise FundusError("image brief source role mismatch")
        expected_operation = (
            "generate" if asset_mode == "generated" else "edit"
        )
        if brief["operation"] != expected_operation:
            raise FundusError("image brief operation mismatch")
        if output_roles is not None and not set(output_roles).issubset(
            brief["desired_output_roles"]
        ):
            raise FundusError("image brief does not authorize the build output role")
        if asset_properties is not None:
            for key, value in asset_properties.items():
                if key in brief["properties"] and brief["properties"][key] != value:
                    raise FundusError(
                        f"asset property conflicts with image brief: {key}"
                    )

    def _apply_recipe_operation(
        self,
        payload: bytes,
        detected_media_type: str,
        operation: dict[str, Any],
    ) -> tuple[bytes, dict[str, object]]:
        transform = operation["transform"]
        profile = operation["parameters"]["profile"]
        if transform == "sanitize_svg":
            if detected_media_type != "image/svg+xml":
                raise FundusError("sanitize_svg requires an SVG source")
            return sanitize_svg(payload, profile=profile), {"svg_profile": profile}
        if transform == "raster_normalize":
            return normalize_raster(payload, profile=profile)
        if transform == "trace_vtracer":
            return trace_raster(payload, profile=profile)
        raise FundusError("unsupported Fundus transform")

    def _build_composition_v2(
        self,
        asset_id: str,
        asset: dict[str, Any],
        asset_digest: str,
        recipe: dict[str, Any],
        recipe_digest: str,
    ) -> dict[str, Any]:
        operations = recipe["operations"]
        source_by_role = {source["role"]: source for source in asset["sources"]}
        required_roles: list[str] = []
        for operation in operations:
            role = operation["source_role"]
            if role not in required_roles:
                required_roles.append(role)
        missing = [role for role in required_roles if role not in source_by_role]
        if missing:
            raise FundusError("recipe source role is absent: " + ", ".join(missing))

        prepared: dict[str, tuple[dict[str, Any], bytes, str]] = {}
        source_records: list[dict[str, Any]] = []
        for role in required_roles:
            source = source_by_role[role]
            output_roles = [
                operation["output"]["role"]
                for operation in operations
                if operation["source_role"] == role
            ]
            self._validate_source_image_brief(
                asset_id,
                source,
                output_roles=output_roles,
                asset_properties=asset.get("properties", {}),
            )
            payload = self._read_object(source["sha256"])
            detected = inspect_media(payload)
            if detected.media_type != source["media_type"]:
                raise FundusError("declared source media_type does not match bytes")
            prepared[role] = (source, payload, detected.media_type)
            source_records.append(
                {
                    "role": source["role"],
                    "sha256": source["sha256"],
                    "media_type": source["media_type"],
                    **(
                        {"source_mode": source["source_mode"]}
                        if "source_mode" in source
                        else {}
                    ),
                    **(
                        {"image_brief_sha256": source["image_brief_sha256"]}
                        if "image_brief_sha256" in source
                        else {}
                    ),
                }
            )

        output_records: list[dict[str, Any]] = []
        staged_outputs: list[tuple[str, bytes]] = []
        toolchain_operations: list[dict[str, object]] = []
        for operation in operations:
            role = operation["source_role"]
            _, payload, media_type = prepared[role]
            output_bytes, adapter_toolchain = self._apply_recipe_operation(
                payload, media_type, operation
            )
            output = operation["output"]
            if inspect_media(output_bytes).media_type != output["media_type"]:
                raise FundusError("transform output media_type does not match its recipe")
            output_records.append(
                {
                    "role": output["role"],
                    "source_role": role,
                    "filename": output["filename"],
                    "media_type": output["media_type"],
                    "sha256": digest_bytes(output_bytes),
                    "bytes": len(output_bytes),
                }
            )
            staged_outputs.append((output["filename"], output_bytes))
            toolchain_operations.append(
                {
                    "source_role": role,
                    "output_role": output["role"],
                    "output_filename": output["filename"],
                    "transform": operation["transform"],
                    **adapter_toolchain,
                }
            )

        body = {
            "schema_version": BUILD_SCHEMA_V2,
            "asset_id": asset_id,
            "asset_manifest_sha256": asset_digest,
            "recipe_id": recipe["id"],
            "recipe_sha256": recipe_digest,
            "sources": source_records,
            "toolchain": {
                "fundus_core": TOOLCHAIN_VERSION,
                "operations": toolchain_operations,
            },
            "outputs": output_records,
        }
        build_digest = digest_json(body)
        build = {**body, "build_digest": build_digest}
        build_dir = self.root / "builds" / asset_id / build_digest
        self._ensure_private_dir(build_dir)
        for filename, output_bytes in staged_outputs:
            self._write_create_or_verify(build_dir / filename, output_bytes)
        self._write_json_create_or_verify(build_dir / "build.json", build)
        return {**build, "build_dir": str(build_dir)}

    def build(self, asset_id: str) -> dict[str, Any]:
        asset, asset_digest, _ = self._asset(asset_id)
        recipe, recipe_digest, _ = self._recipe(
            asset["recipe"]
        )
        if recipe.get("schema_version") == RECIPE_SCHEMA_V2:
            return self._build_composition_v2(
                asset_id, asset, asset_digest, recipe, recipe_digest
            )
        matching = [
            source
            for source in asset["sources"]
            if source["role"] == recipe["source_role"]
        ]
        if len(matching) != 1:
            raise FundusError(
                "recipe source role is absent or ambiguous"
            )
        source = matching[0]
        self._validate_source_image_brief(
            asset_id,
            source,
            output_roles=[recipe["output"]["role"]],
            asset_properties=asset.get("properties", {}),
        )
        payload = self._read_object(source["sha256"])
        detected = inspect_media(payload)
        if detected.media_type != source["media_type"]:
            raise FundusError(
                "declared source media_type does not match bytes"
            )
        transform = recipe["transform"]
        profile = recipe["parameters"]["profile"]
        if transform == "sanitize_svg":
            if detected.media_type != "image/svg+xml":
                raise FundusError("sanitize_svg requires an SVG source")
            output_bytes = sanitize_svg(payload, profile=profile)
            adapter_toolchain: dict[str, object] = {"svg_profile": profile}
        elif transform == "raster_normalize":
            output_bytes, adapter_toolchain = normalize_raster(payload, profile=profile)
        elif transform == "trace_vtracer":
            output_bytes, adapter_toolchain = trace_raster(payload, profile=profile)
        else:
            raise FundusError("unsupported Fundus transform")

        output = recipe["output"]
        output_media = inspect_media(output_bytes)
        if output_media.media_type != output["media_type"]:
            raise FundusError("transform output media_type does not match its recipe")
        output_sha = digest_bytes(output_bytes)
        body = {
            "schema_version": BUILD_SCHEMA,
            "asset_id": asset_id,
            "asset_manifest_sha256": asset_digest,
            "recipe_id": recipe["id"],
            "recipe_sha256": recipe_digest,
            "source": {
                "role": source["role"],
                "sha256": source["sha256"],
                "media_type": source["media_type"],
                **(
                    {"source_mode": source["source_mode"]}
                    if "source_mode" in source
                    else {}
                ),
                **(
                    {"image_brief_sha256": source["image_brief_sha256"]}
                    if "image_brief_sha256" in source
                    else {}
                ),
            },
            "toolchain": {
                "fundus_core": TOOLCHAIN_VERSION,
                **adapter_toolchain,
            },
            "outputs": [
                {
                    "role": output["role"],
                    "filename": output["filename"],
                    "media_type": output["media_type"],
                    "sha256": output_sha,
                    "bytes": len(output_bytes),
                }
            ],
        }
        build_digest = digest_json(body)
        build = {
            **body,
            "build_digest": build_digest,
        }
        build_dir = (
            self.root
            / "builds"
            / asset_id
            / build_digest
        )
        self._ensure_private_dir(build_dir)
        self._write_create_or_verify(
            build_dir / output["filename"],
            output_bytes,
        )
        self._write_json_create_or_verify(
            build_dir / "build.json",
            build,
        )
        return {
            **build,
            "build_dir": str(build_dir),
        }

    def _load_build(
        self,
        asset_id: str,
        build_digest: str,
    ) -> tuple[dict[str, Any], Path]:
        checked_id(asset_id, label="asset id")
        checked_sha256(
            build_digest,
            label="build digest",
        )
        build_dir = (
            self.root
            / "builds"
            / asset_id
            / build_digest
        )
        manifest_path = build_dir / "build.json"
        if not manifest_path.exists():
            raise FundusError(
                "Fundus build does not exist"
            )
        manifest = json.loads(
            self._read_private(
                manifest_path,
                maximum_bytes=256_000,
            )
        )
        if manifest.get("build_digest") != build_digest:
            raise FundusError(
                "build manifest digest binding is invalid"
            )
        body = dict(manifest)
        body.pop("build_digest", None)
        if digest_json(body) != build_digest:
            raise FundusError(
                "build manifest content drifted"
            )
        for output in manifest.get("outputs", []):
            payload = self._read_private(
                build_dir / output["filename"],
                maximum_bytes=MAX_BUILD_OUTPUT_BYTES,
            )
            if digest_bytes(payload) != output["sha256"]:
                raise FundusError(
                    "build output digest mismatch"
                )
        return manifest, build_dir

    def preview(
        self,
        asset_id: str,
        *,
        build_digest: str | None = None,
    ) -> dict[str, Any]:
        if build_digest is None:
            build_digest = self.build(asset_id)[
                "build_digest"
            ]
        build, build_dir = self._load_build(
            asset_id,
            build_digest,
        )
        stage_items: list[str] = []
        uses_data_images = False
        for output in build["outputs"]:
            media_type = output["media_type"]
            artifact_path = build_dir / output["filename"]
            if media_type == "image/svg+xml":
                rendered = self._read_private(
                    artifact_path,
                    maximum_bytes=MAX_BUILD_OUTPUT_BYTES,
                ).decode("utf-8")
            elif media_type == "image/png":
                artifact_bytes = self._read_private(
                    artifact_path,
                    maximum_bytes=MAX_PREVIEW_RASTER_BYTES,
                )
                encoded = base64.b64encode(artifact_bytes).decode("ascii")
                rendered = (
                    '<img alt="Fundus raster preview" '
                    f'src="data:image/png;base64,{encoded}">'
                )
                uses_data_images = True
            else:
                raise FundusError("Fundus preview supports SVG and PNG outputs")
            stage_items.append(
                '<figure class="preview-item">'
                f'<div class="artifact">{rendered}</div>'
                f'<figcaption>{html.escape(output["role"])} · '
                f'<code>{html.escape(output["filename"])}</code></figcaption>'
                '</figure>'
            )
        stage_content = "".join(stage_items)
        content_security_policy = (
            "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
            if uses_data_images
            else "default-src 'none'; style-src 'unsafe-inline'"
        )

        asset_label = html.escape(asset_id)
        build_label = html.escape(build_digest)
        document = (
            '<!doctype html><html lang="en"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" '
            'content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" '
            f'content="{content_security_policy}">'
            '<title>Schauwerk Fundus Preview</title>'
            '<style>'
            'body{margin:0;background:#eee;color:#111;'
            'font-family:system-ui,sans-serif}'
            'main{max-width:900px;margin:auto;padding:32px}'
            '.stage{display:grid;place-items:center;'
            'min-height:55vh;background:white;'
            'border:1px solid #bbb}'
            '.stage svg,.stage img{max-width:80%;max-height:55vh}'
            '.preview-item{margin:0;display:grid;place-items:center;gap:8px}'
            '.artifact{display:grid;place-items:center}'
            'figcaption{text-align:center}'
            'code{overflow-wrap:anywhere}'
            '</style></head><body><main>'
            '<h1>Fundus preview</h1>'
            f'<p><strong>Asset:</strong> {asset_label}</p>'
            '<p><strong>Build:</strong> '
            f'<code>{build_label}</code></p>'
            f'<div class="stage">{stage_content}</div>'
            '</main></body></html>\n'
        ).encode()
        preview_digest = digest_bytes(document)
        preview_dir = (
            self.root
            / "previews"
            / asset_id
            / build_digest
        )
        self._ensure_private_dir(preview_dir)
        self._write_create_or_verify(
            preview_dir / "index.html",
            document,
        )
        receipt = {
            "schema_version": PREVIEW_SCHEMA,
            "asset_id": asset_id,
            "build_digest": build_digest,
            "preview_sha256": preview_digest,
            "preview_file": "index.html",
            "network_dependencies": False,
            "aesthetic_quality_established": False,
        }
        self._write_json_create_or_verify(
            preview_dir / "preview.json",
            receipt,
        )
        return {
            **receipt,
            "preview_path": str(
                preview_dir / "index.html"
            ),
        }

    def accept(
        self,
        asset_id: str,
        *,
        build_digest: str,
        reviewer: str,
        decision: str,
        note: str = "",
        reviewed_at: str | None = None,
    ) -> dict[str, Any]:
        build, _ = self._load_build(
            asset_id,
            build_digest,
        )
        if decision not in {"accepted", "rejected"}:
            raise FundusError(
                "decision must be accepted or rejected"
            )
        reviewer = reviewer.strip()
        note = note.strip()
        if not reviewer or len(reviewer) > 200:
            raise FundusError(
                "reviewer is invalid"
            )
        if len(note) > 2000:
            raise FundusError(
                "acceptance note is invalid"
            )
        body = {
            "schema_version": ACCEPTANCE_SCHEMA,
            "asset_id": asset_id,
            "build_digest": build_digest,
            "output_sha256s": [
                item["sha256"]
                for item in build["outputs"]
            ],
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": (
                reviewed_at
                or datetime.now(UTC).isoformat()
            ),
            "note": note,
            "reviewer_identity_authenticated": False,
        }
        acceptance_digest = digest_json(body)
        record = {
            **body,
            "acceptance_digest": acceptance_digest,
        }
        path = (
            self.root
            / "acceptances"
            / asset_id
            / build_digest
            / f"{acceptance_digest}.json"
        )
        self._write_json_create_or_verify(
            path,
            record,
        )
        return {
            **record,
            "acceptance_path": str(path),
        }

    def _load_acceptance(
        self,
        asset_id: str,
        build_digest: str,
        acceptance_digest: str,
    ) -> dict[str, Any]:
        checked_sha256(
            acceptance_digest,
            label="acceptance digest",
        )
        path = (
            self.root
            / "acceptances"
            / asset_id
            / build_digest
            / f"{acceptance_digest}.json"
        )
        if not path.exists():
            raise FundusError(
                "acceptance receipt does not exist"
            )
        record = json.loads(
            self._read_private(
                path,
                maximum_bytes=128_000,
            )
        )
        if record.get("acceptance_digest") != acceptance_digest:
            raise FundusError(
                "acceptance digest binding is invalid"
            )
        body = dict(record)
        body.pop("acceptance_digest", None)
        if digest_json(body) != acceptance_digest:
            raise FundusError(
                "acceptance receipt drifted"
            )
        if record.get("asset_id") != asset_id:
            raise FundusError(
                "acceptance targets another asset"
            )
        if record.get("build_digest") != build_digest:
            raise FundusError(
                "acceptance targets another build"
            )
        return record

    def package(
        self,
        asset_id: str,
        *,
        build_digest: str,
        acceptance_digest: str,
    ) -> dict[str, Any]:
        build, build_dir = self._load_build(
            asset_id,
            build_digest,
        )
        acceptance = self._load_acceptance(
            asset_id,
            build_digest,
            acceptance_digest,
        )
        build_schema = build.get("schema_version")
        source_image_briefs: list[dict[str, str]] = []
        if build_schema == BUILD_SCHEMA_V2:
            for source in build["sources"]:
                output_roles = [
                    item["role"]
                    for item in build["outputs"]
                    if item["source_role"] == source["role"]
                ]
                self._validate_source_image_brief(
                    asset_id, source, output_roles=output_roles
                )
                if "image_brief_sha256" in source:
                    source_image_briefs.append(
                        {
                            "role": source["role"],
                            "sha256": source["image_brief_sha256"],
                        }
                    )
        else:
            self._validate_source_image_brief(
                asset_id,
                build["source"],
                output_roles=[item["role"] for item in build["outputs"]],
            )
        if acceptance.get("decision") != "accepted":
            raise FundusError(
                "only an explicitly accepted build may be packaged"
            )
        files: list[dict[str, Any]] = []
        staged: list[tuple[str, bytes]] = []
        slug = asset_id.replace(".", "-").replace("_", "-")
        for output in build["outputs"]:
            payload = self._read_private(
                build_dir / output["filename"],
                maximum_bytes=MAX_BUILD_OUTPUT_BYTES,
            )
            suffix = Path(output["filename"]).suffix
            packaged_name = (
                f"{slug}-{output['role']}{suffix}"
            )
            relpath = f"assets/{packaged_name}"
            files.append(
                {
                    "path": relpath,
                    "role": output["role"],
                    **(
                        {"source_role": output["source_role"]}
                        if build_schema == BUILD_SCHEMA_V2
                        else {}
                    ),
                    "media_type": output["media_type"],
                    "sha256": digest_bytes(payload),
                    "bytes": len(payload),
                }
            )
            staged.append((relpath, payload))
        body = {
            "schema_version": (
                PACKAGE_SCHEMA_V2
                if build_schema == BUILD_SCHEMA_V2
                else PACKAGE_SCHEMA
            ),
            "asset_id": asset_id,
            "build_digest": build_digest,
            "acceptance_digest": acceptance_digest,
            "files": files,
            **(
                {"source_image_briefs": source_image_briefs}
                if build_schema == BUILD_SCHEMA_V2 and source_image_briefs
                else {}
            ),
            **(
                {
                    "source_image_brief_sha256":
                        build["source"]["image_brief_sha256"]
                }
                if build_schema != BUILD_SCHEMA_V2
                and "image_brief_sha256" in build["source"]
                else {}
            ),
            "consumer_runtime_dependency": False,
        }
        package_digest = digest_json(body)
        manifest = {
            **body,
            "package_digest": package_digest,
        }
        package_dir = (
            self.root
            / "packages"
            / asset_id
            / build_digest
            / package_digest
        )
        self._ensure_private_dir(package_dir)
        for relpath, payload in staged:
            self._write_create_or_verify(
                package_dir / relpath,
                payload,
            )
        manifest_bytes = canonical_json(manifest) + b"\n"
        self._write_create_or_verify(
            package_dir / "fundus-package.json",
            manifest_bytes,
        )
        sums = [
            f"{item['sha256']}  {item['path']}"
            for item in files
        ]
        sums.append(
            f"{digest_bytes(manifest_bytes)}  "
            "fundus-package.json"
        )
        sums_payload = (
            "\n".join(sums) + "\n"
        ).encode("utf-8")
        self._write_create_or_verify(
            package_dir / "SHA256SUMS",
            sums_payload,
        )
        return {
            **manifest,
            "package_dir": str(package_dir),
        }

    def consumer_lock(self, package_dir: str | Path) -> dict[str, Any]:
        verified = verify_package_directory(package_dir)
        lock = consumer_lock_manifest(verified)
        lock_path = (
            self.root
            / "consumer-locks"
            / lock["asset_id"]
            / lock["package_digest"]
            / f"{lock['lock_digest']}.json"
        )
        package_root = Path(verified["package_path"])
        lock_target = normalized_absolute(
            lock_path, label="Fundus consumer lock path"
        )
        if lock_target == package_root or package_root in lock_target.parents:
            raise FundusError(
                "Fundus consumer lock must not be materialized inside the package"
            )
        self._write_create_or_verify(
            lock_path,
            canonical_consumer_lock_bytes(lock),
        )
        return {**lock, "lock_path": str(lock_path)}

    def _import_seam(self) -> dict[str, Any]:
        package_dir = Path(__file__).resolve().parent
        findings: list[str] = []
        for path in sorted(package_dir.glob("*.py")):
            tree = ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            )
            for node in ast.walk(tree):
                candidates: list[str] = []
                if isinstance(node, ast.Import):
                    candidates.extend(
                        alias.name
                        for alias in node.names
                    )
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                ):
                    candidates.append(node.module)
                for name in candidates:
                    if any(
                        name.startswith(prefix)
                        for prefix in FORBIDDEN_IMPORT_PREFIXES
                    ):
                        findings.append(
                            f"{path.name}:{name}"
                        )
        return {
            "ok": not findings,
            "forbidden_imports": findings,
        }

    def doctor(self) -> dict[str, Any]:
        seam = self._import_seam()
        state: dict[str, Any] = {
            "exists": self.root.exists(),
            "safe": None,
        }
        if self.root.exists():
            linked = self.root.lstat()
            state["safe"] = bool(
                stat.S_ISDIR(linked.st_mode)
                and not stat.S_ISLNK(linked.st_mode)
                and linked.st_uid == os.geteuid()
                and not (
                    stat.S_IMODE(linked.st_mode) & 0o077
                )
            )

        families: list[str] = []
        family_root = (
            self.paths.registry_root / "families"
        )
        if family_root.exists():
            for path in sorted(
                family_root.glob("*.json")
            ):
                value = load_json(path)
                validate_family(value)
                if path.stem != value["id"]:
                    raise FundusError(
                        "family filename/id mismatch"
                    )
                families.append(value["id"])

        recipes: list[str] = []
        recipe_root = (
            self.paths.registry_root / "recipes"
        )
        if recipe_root.exists():
            for path in sorted(
                recipe_root.glob("*.json")
            ):
                value = load_json(path)
                validate_recipe(value)
                if path.stem != value["id"]:
                    raise FundusError(
                        "recipe filename/id mismatch"
                    )
                recipes.append(value["id"])

        assets: list[str] = []
        asset_root = self.paths.registry_root / "assets"
        if asset_root.exists():
            for path in sorted(
                asset_root.glob("*.json")
            ):
                value = load_json(path)
                validate_asset(value)
                if path.stem != value["id"]:
                    raise FundusError(
                        "asset filename/id mismatch"
                    )
                family = value.get("family")
                if family is not None:
                    self._family(family)
                self._recipe(value["recipe"])
                assets.append(value["id"])

        raster_status = raster_adapter_status()
        trace_status = trace_adapter_status()
        ok = (
            seam["ok"]
            and state["safe"] is not False
            and raster_status["available"] is True
        )
        return {
            "schema_version": "schauwerk-fundus-doctor.v1",
            "ok": ok,
            "miro_independent": seam["ok"],
            "import_seam": seam,
            "state": state,
            "registry": {
                "families": families,
                "recipes": recipes,
                "assets": assets,
            },
            "svg_profiles": [
                "svg.mask.v1",
                "svg.decorative.v1",
            ],
            "raster_profiles": [RASTER_PROFILE],
            "trace_profiles": list(TRACE_PROFILES),
            "image_brief_schema": IMAGE_BRIEF_SCHEMA,
            "adapters": {
                "raster": raster_status,
                "trace": trace_status,
            },
            "cross_repo_mutation_authority": False,
            "object_store_authoritative": False,
            "recommended_next_action": (
                "retain original source files until "
                "backup/restore coverage is proven"
            ),
        }
