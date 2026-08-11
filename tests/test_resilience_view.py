from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from schauwerk.cli_parser import build_parser
from schauwerk.ecosystem_map import EcosystemMapRenderError, render_ecosystem_map_html
from schauwerk.resilience_view import (
    ResilienceViewError,
    compile_resilience_view,
    load_operational_overlay,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resilience() -> dict:
    return {
        "schemaVersion": 1,
        "kind": "system_catalog_resilience",
        "owner": "repo:systemkatalog",
        "catalogRole": "canonical_stable_resilience_semantics",
        "updatedAt": "2026-08-07",
        "criticalityClasses": ["foundational", "optional"],
        "couplingClasses": ["synchronous-blocking", "observational"],
        "failurePolicies": ["block", "degrade"],
        "authorityDirections": ["from-to"],
        "recoveryIndependenceClasses": ["independent", "same-failure-domain"],
        "failureDomains": [
            {
                "id": "host:shared",
                "kind": "host",
                "meaning": "Shared host failure domain.",
                "doesNotEstablish": ["current failure"],
            },
            {
                "id": "provider:backup",
                "kind": "provider",
                "meaning": "Independent backup provider.",
                "doesNotEstablish": ["current health"],
            },
        ],
        "systems": [
            {
                "system": "repo:a",
                "criticality": "foundational",
                "failureDomains": ["host:shared"],
                "recoveryModeRefs": ["restore-a"],
                "acceptedSinglePathRisks": [],
                "evidence": ["evidence:a"],
                "uncertainty": 0.1,
            },
            {
                "system": "repo:b",
                "criticality": "optional",
                "failureDomains": ["host:shared"],
                "recoveryModeRefs": [],
                "acceptedSinglePathRisks": [],
                "evidence": ["evidence:b"],
                "uncertainty": 0.2,
            },
        ],
        "relations": [
            {
                "relation": {"from": "repo:a", "to": "repo:b", "type": "provides"},
                "coupling": "synchronous-blocking",
                "failurePolicy": "block",
                "authorityDirection": "from-to",
                "recoveryModeRef": None,
                "evidence": ["evidence:relation"],
                "uncertainty": 0.15,
            }
        ],
        "recoveryModes": [
            {
                "id": "restore-a",
                "system": "repo:a",
                "kind": "restore",
                "failureDomains": ["provider:backup"],
                "independence": "independent",
                "sharedFailureDomains": [],
                "triggerClass": "primary path unavailable",
                "returnCondition": "bounded verification passes",
                "evidence": ["evidence:restore"],
                "doesNotEstablish": ["current recovery readiness"],
            }
        ],
        "doesNotEstablish": ["current failure", "current health"],
    }


def _overlay() -> dict:
    return {
        "schema_version": "schauwerk-resilience-operational-overlay.v1",
        "source_id": "chronik.resilience-trend-export",
        "stale_after_seconds": 3600,
        "signals": [
            {
                "subject": "repo:a",
                "metric": "recovery_proof_age",
                "value": 12,
                "unit": "hours",
                "trend": "deteriorating",
                "authority": "infra.recovery-proof-observation",
                "observed_at": "2026-08-11T10:00:00Z",
                "coverage": "partial",
                "uncertainty": 0.2,
                "evidence_ref": "sha256:" + "b" * 64,
            }
        ],
        "does_not_establish": [
            "current_failure",
            "current_health",
            "automatic_recovery_authority",
        ],
    }


def _write_manifest(root: Path, *, include_resilience: bool = True) -> Path:
    rendered = root / "rendered"
    registry = root / "registry" / "ecosystem"
    rendered.mkdir(parents=True)
    registry.mkdir(parents=True)
    map_text = "flowchart TD\n  A[repo:a] --> B[repo:b]\n"
    map_path = rendered / "ecosystem-registry-map.mmd"
    map_path.write_text(map_text, encoding="utf-8")
    artifacts = [
        {
            "role": "canonical_ecosystem_map_mermaid",
            "path": "rendered/ecosystem-registry-map.mmd",
            "bytes": len(map_text.encode("utf-8")),
            "sha256": _sha(map_text),
        }
    ]
    if include_resilience:
        resilience_text = json.dumps(_resilience(), sort_keys=True)
        resilience_path = registry / "resilience.v1.json"
        resilience_path.write_text(resilience_text, encoding="utf-8")
        artifacts.append(
            {
                "role": "resilience_semantics",
                "path": "registry/ecosystem/resilience.v1.json",
                "bytes": len(resilience_text.encode("utf-8")),
                "sha256": _sha(resilience_text),
            }
        )
    manifest = {
        "schemaVersion": 1,
        "kind": "system_catalog_map_artifact_manifest",
        "contractVersion": "1",
        "source": {
            "repository": "heimgewebe/systemkatalog",
            "commit": "a" * 40,
            "generatedAt": "2026-08-11T09:00:00Z",
        },
        "artifacts": artifacts,
    }
    manifest_path = rendered / "ecosystem-map-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_resilience_view_renders_catalog_semantics_and_blast_radius() -> None:
    result = compile_resilience_view(_resilience())

    html = result["html"]
    assert result["system_count"] == 2
    assert result["relation_count"] == 1
    assert result["failure_domain_count"] == 2
    assert result["recovery_mode_count"] == 1
    assert result["operational_truth_inferred"] is False
    assert 'data-authority="catalog"' in html
    assert "foundational" in html
    assert "synchronous-blocking" in html
    assert "host:shared" in html
    assert "restore-a" in html
    assert "2 betroffene Systeme; 1 verbleibende Katalogpfade" in html
    assert "Katalogpfad teilt diese Failure Domain nicht" in html
    assert "Textmodus" in html
    assert "ZEITGEBUNDENE EVIDENZ · NICHT GELADEN" in html


def test_overlay_is_time_bound_source_labelled_and_separate(tmp_path: Path) -> None:
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(_overlay()), encoding="utf-8")

    result = compile_resilience_view(
        _resilience(),
        operational_overlay_path=overlay_path,
        evaluated_at="2026-08-11T10:30:00Z",
    )

    overlay = result["operational_overlay"]
    assert overlay is not None
    assert overlay["source_id"] == "chronik.resilience-trend-export"
    assert overlay["state"] == "fresh"
    assert overlay["oldest_signal_age_seconds"] == 1800
    assert overlay["signal_count"] == 1
    html = result["html"]
    assert "ZEITGEBUNDENE EVIDENZ · FRISCH" in html
    assert "Trendoverlay" in html
    assert "recovery_proof_age" in html
    assert "deteriorating" in html
    assert "infra.recovery-proof-observation" in html
    assert "2026-08-11T10:00:00Z" in html
    assert "partial" in html
    assert "0.20" in html
    assert "Criticality, Failure Domains, Kopplung oder Recovery-Pfade" in html


def test_overlay_becomes_stale_without_changing_catalog_truth(tmp_path: Path) -> None:
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(_overlay()), encoding="utf-8")

    overlay = load_operational_overlay(
        overlay_path,
        evaluated_at="2026-08-11T12:00:01Z",
        known_systems={"repo:a", "repo:b"},
    )

    assert overlay["state"] == "stale"
    assert overlay["oldest_signal_age_seconds"] == 7201
    assert overlay["signals"][0]["state"] == "stale"


def test_overlay_rejects_attempt_to_smuggle_static_semantics(tmp_path: Path) -> None:
    overlay = deepcopy(_overlay())
    overlay["signals"][0]["criticality"] = "foundational"
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(overlay), encoding="utf-8")

    with pytest.raises(ResilienceViewError, match="unsupported fields"):
        compile_resilience_view(
            _resilience(),
            operational_overlay_path=overlay_path,
            evaluated_at="2026-08-11T10:30:00Z",
        )


def test_ecosystem_handoff_integrates_digest_bound_resilience_and_overlay(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(_overlay()), encoding="utf-8")
    output = tmp_path / "out" / "resilience.html"

    receipt = render_ecosystem_map_html(
        manifest_path=manifest_path,
        output_path=output,
        operational_overlay_path=overlay_path,
        evaluated_at="2026-08-11T10:30:00Z",
    )

    html = output.read_text(encoding="utf-8")
    assert receipt["resilience_rendered"] is True
    assert receipt["resilience_system_count"] == 2
    assert receipt["resilience_relation_count"] == 1
    assert receipt["operational_truth_inferred"] is False
    assert receipt["operational_overlay"]["state"] == "fresh"
    assert "Canonical ecosystem map Mermaid source" in html
    assert "KATALOG · VERSIONIERT" in html
    assert "ZEITGEBUNDENE EVIDENZ · FRISCH" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "Textmodus" in html


def test_ecosystem_handoff_keeps_old_manifest_compatible(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, include_resilience=False)
    output = tmp_path / "out.html"

    receipt = render_ecosystem_map_html(manifest_path=manifest_path, output_path=output)

    assert receipt["resilience_rendered"] is False
    assert "RESILIENZ NICHT VERÖFFENTLICHT" in output.read_text(encoding="utf-8")


def test_ecosystem_overlay_requires_resilience_artifact(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, include_resilience=False)
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(_overlay()), encoding="utf-8")

    with pytest.raises(EcosystemMapRenderError, match="requires the manifest"):
        render_ecosystem_map_html(
            manifest_path=manifest_path,
            output_path=tmp_path / "out.html",
            operational_overlay_path=overlay_path,
            evaluated_at="2026-08-11T10:30:00Z",
        )


def test_cli_exposes_explicit_overlay_and_evaluation_time() -> None:
    args = build_parser().parse_args(
        [
            "ecosystem",
            "render",
            "manifest.json",
            "--output",
            "out.html",
            "--operational-overlay",
            "overlay.json",
            "--evaluated-at",
            "2026-08-11T10:30:00Z",
        ]
    )

    assert args.operational_overlay == "overlay.json"
    assert args.evaluated_at == "2026-08-11T10:30:00Z"
