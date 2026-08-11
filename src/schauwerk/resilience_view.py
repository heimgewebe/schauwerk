"""Read-only resilience projection over Systemkatalog semantics and bounded trend evidence."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

RESILIENCE_KIND = "system_catalog_resilience"
RESILIENCE_OWNER = "repo:systemkatalog"
RESILIENCE_ROLE = "canonical_stable_resilience_semantics"
OVERLAY_SCHEMA_VERSION = "schauwerk-resilience-operational-overlay.v1"
OVERLAY_METRICS = {
    "attention_age",
    "terminal_projection_lag",
    "recurring_failure_signatures",
    "recovery_proof_age",
    "temporary_resource_growth",
    "closure_duration",
}
OVERLAY_NON_CLAIMS = {
    "current_failure",
    "current_health",
    "automatic_recovery_authority",
}


class ResilienceViewError(ValueError):
    pass


def _parse_time(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ) is None:
        raise ResilienceViewError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(UTC)
    except ValueError as exc:
        raise ResilienceViewError(f"{label} must be an RFC3339 UTC timestamp") from exc


def _bounded_text(value: Any, *, label: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ResilienceViewError(f"{label} must be non-empty bounded text")
    return value


def _uncertainty(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResilienceViewError(f"{label} must be a number between 0 and 1")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized <= 1:
        raise ResilienceViewError(f"{label} must be a number between 0 and 1")
    return normalized


def _string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ResilienceViewError(f"{label} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ResilienceViewError(f"{label} must not contain duplicates")
    return list(value)


def _read_json_object(path: Path, *, label: str, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ResilienceViewError(f"{label} must be a regular non-symlink file")
        if path.stat().st_size > max_bytes:
            raise ResilienceViewError(f"{label} exceeds the size limit")
        raw = path.read_bytes()
    except OSError as exc:
        raise ResilienceViewError(f"{label} is unreadable") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResilienceViewError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ResilienceViewError(f"{label} must contain an object")
    return value


def validate_resilience_semantics(value: Mapping[str, Any]) -> dict[str, Any]:
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != RESILIENCE_KIND
        or value.get("owner") != RESILIENCE_OWNER
        or value.get("catalogRole") != RESILIENCE_ROLE
    ):
        raise ResilienceViewError("resilience semantics identity mismatch")

    criticality_classes = set(
        _string_list(value.get("criticalityClasses"), label="criticalityClasses")
    )
    coupling_classes = set(_string_list(value.get("couplingClasses"), label="couplingClasses"))
    failure_policies = set(_string_list(value.get("failurePolicies"), label="failurePolicies"))
    authority_directions = set(
        _string_list(value.get("authorityDirections"), label="authorityDirections")
    )
    independence_classes = set(
        _string_list(value.get("recoveryIndependenceClasses"), label="recoveryIndependenceClasses")
    )

    raw_domains = value.get("failureDomains")
    if not isinstance(raw_domains, list):
        raise ResilienceViewError("failureDomains must be an array")
    domains: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_domains):
        label = f"failureDomains[{index}]"
        if not isinstance(item, Mapping):
            raise ResilienceViewError(f"{label} must be an object")
        domain_id = _bounded_text(item.get("id"), label=f"{label}.id")
        _bounded_text(item.get("kind"), label=f"{label}.kind", maximum=64)
        _bounded_text(item.get("meaning"), label=f"{label}.meaning", maximum=1000)
        if domain_id in domains:
            raise ResilienceViewError(f"duplicate failure domain: {domain_id}")
        domains[domain_id] = dict(item)

    raw_modes = value.get("recoveryModes")
    if not isinstance(raw_modes, list):
        raise ResilienceViewError("recoveryModes must be an array")
    modes: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_modes):
        label = f"recoveryModes[{index}]"
        if not isinstance(item, Mapping):
            raise ResilienceViewError(f"{label} must be an object")
        mode_id = _bounded_text(item.get("id"), label=f"{label}.id")
        system = _bounded_text(item.get("system"), label=f"{label}.system")
        _bounded_text(item.get("kind"), label=f"{label}.kind", maximum=64)
        failure_domains = _string_list(item.get("failureDomains"), label=f"{label}.failureDomains")
        shared = _string_list(
            item.get("sharedFailureDomains"), label=f"{label}.sharedFailureDomains"
        )
        if any(domain not in domains for domain in failure_domains + shared):
            raise ResilienceViewError(f"{label} references an unknown failure domain")
        if not set(shared).issubset(set(failure_domains)):
            raise ResilienceViewError(f"{label}.sharedFailureDomains must be a subset")
        if item.get("independence") not in independence_classes:
            raise ResilienceViewError(f"{label}.independence is invalid")
        if mode_id in modes:
            raise ResilienceViewError(f"duplicate recovery mode: {mode_id}")
        modes[mode_id] = {**dict(item), "system": system}

    raw_systems = value.get("systems")
    if not isinstance(raw_systems, list):
        raise ResilienceViewError("systems must be an array")
    systems: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_systems):
        label = f"systems[{index}]"
        if not isinstance(item, Mapping):
            raise ResilienceViewError(f"{label} must be an object")
        system_id = _bounded_text(item.get("system"), label=f"{label}.system")
        if system_id in systems:
            raise ResilienceViewError(f"duplicate system resilience entry: {system_id}")
        if item.get("criticality") not in criticality_classes:
            raise ResilienceViewError(f"{label}.criticality is invalid")
        failure_domains = _string_list(item.get("failureDomains"), label=f"{label}.failureDomains")
        recovery_refs = _string_list(
            item.get("recoveryModeRefs"), label=f"{label}.recoveryModeRefs"
        )
        if any(domain not in domains for domain in failure_domains):
            raise ResilienceViewError(f"{label} references an unknown failure domain")
        for ref in recovery_refs:
            mode = modes.get(ref)
            if mode is None:
                raise ResilienceViewError(f"{label} references an unknown recovery mode")
            if mode["system"] != system_id:
                raise ResilienceViewError(f"{label} recovery mode belongs to another system")
        _uncertainty(item.get("uncertainty"), label=f"{label}.uncertainty")
        systems[system_id] = dict(item)

    raw_relations = value.get("relations")
    if not isinstance(raw_relations, list):
        raise ResilienceViewError("relations must be an array")
    relations: list[dict[str, Any]] = []
    for index, item in enumerate(raw_relations):
        label = f"relations[{index}]"
        if not isinstance(item, Mapping) or not isinstance(item.get("relation"), Mapping):
            raise ResilienceViewError(f"{label} must contain a relation object")
        relation = item["relation"]
        for key in ("from", "to", "type"):
            _bounded_text(relation.get(key), label=f"{label}.relation.{key}")
        if item.get("coupling") not in coupling_classes:
            raise ResilienceViewError(f"{label}.coupling is invalid")
        if item.get("failurePolicy") not in failure_policies:
            raise ResilienceViewError(f"{label}.failurePolicy is invalid")
        if item.get("authorityDirection") not in authority_directions:
            raise ResilienceViewError(f"{label}.authorityDirection is invalid")
        recovery_ref = item.get("recoveryModeRef")
        if recovery_ref is not None and recovery_ref not in modes:
            raise ResilienceViewError(f"{label} references an unknown recovery mode")
        _uncertainty(item.get("uncertainty"), label=f"{label}.uncertainty")
        relations.append(dict(item))

    return {
        "systems": systems,
        "domains": domains,
        "relations": relations,
        "modes": modes,
        "updated_at": value.get("updatedAt"),
        "does_not_establish": list(value.get("doesNotEstablish") or []),
    }


def _validate_signal(
    value: Any,
    *,
    index: int,
    known_systems: set[str],
    evaluated_at: datetime,
    stale_after: int,
) -> dict[str, Any]:
    label = f"signals[{index}]"
    if not isinstance(value, Mapping):
        raise ResilienceViewError(f"{label} must be an object")
    expected = {
        "subject",
        "metric",
        "value",
        "unit",
        "trend",
        "authority",
        "observed_at",
        "coverage",
        "uncertainty",
        "evidence_ref",
    }
    if set(value) != expected:
        raise ResilienceViewError(f"{label} has unsupported fields")
    subject = _bounded_text(value.get("subject"), label=f"{label}.subject")
    if subject != "ecosystem" and subject not in known_systems:
        raise ResilienceViewError(f"{label}.subject is not present in catalog semantics")
    metric = value.get("metric")
    if metric not in OVERLAY_METRICS:
        raise ResilienceViewError(f"{label}.metric is unsupported")
    raw_value = value.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
        raise ResilienceViewError(f"{label}.value must be bounded scalar evidence")
    if isinstance(raw_value, str):
        _bounded_text(raw_value, label=f"{label}.value", maximum=120)
    elif not math.isfinite(float(raw_value)):
        raise ResilienceViewError(f"{label}.value must be finite")
    unit = value.get("unit")
    if unit is not None:
        _bounded_text(unit, label=f"{label}.unit", maximum=32)
    trend = value.get("trend")
    if trend not in {"improving", "stable", "deteriorating", "unknown"}:
        raise ResilienceViewError(f"{label}.trend is invalid")
    authority = _bounded_text(value.get("authority"), label=f"{label}.authority", maximum=128)
    observed = _parse_time(value.get("observed_at"), label=f"{label}.observed_at")
    if int((observed - evaluated_at).total_seconds()) > 300:
        raise ResilienceViewError(f"{label}.observed_at is too far in the future")
    age_seconds = max(0, int((evaluated_at - observed).total_seconds()))
    coverage = value.get("coverage")
    if coverage not in {"full", "partial", "unknown"}:
        raise ResilienceViewError(f"{label}.coverage is invalid")
    uncertainty = _uncertainty(value.get("uncertainty"), label=f"{label}.uncertainty")
    _bounded_text(value.get("evidence_ref"), label=f"{label}.evidence_ref", maximum=512)
    return {
        **dict(value),
        "authority": authority,
        "uncertainty": uncertainty,
        "age_seconds": age_seconds,
        "state": "stale" if age_seconds > stale_after else "fresh",
    }


def load_operational_overlay(
    path: Path,
    *,
    evaluated_at: str,
    known_systems: set[str],
) -> dict[str, Any]:
    overlay = _read_json_object(path, label="operational overlay")
    expected = {
        "schema_version",
        "source_id",
        "stale_after_seconds",
        "signals",
        "does_not_establish",
    }
    if set(overlay) != expected:
        raise ResilienceViewError("operational overlay has unsupported fields")
    if overlay.get("schema_version") != OVERLAY_SCHEMA_VERSION:
        raise ResilienceViewError("operational overlay schema mismatch")
    source_id = _bounded_text(
        overlay.get("source_id"), label="operational overlay source_id", maximum=128
    )
    evaluated = _parse_time(evaluated_at, label="evaluated_at")
    stale_after = overlay.get("stale_after_seconds")
    if (
        isinstance(stale_after, bool)
        or not isinstance(stale_after, int)
        or not 60 <= stale_after <= 31_536_000
    ):
        raise ResilienceViewError("operational overlay stale_after_seconds is invalid")
    signals = overlay.get("signals")
    if not isinstance(signals, list) or len(signals) > 500:
        raise ResilienceViewError("operational overlay signals must be a bounded array")
    normalized_signals = [
        _validate_signal(
            item,
            index=index,
            known_systems=known_systems,
            evaluated_at=evaluated,
            stale_after=stale_after,
        )
        for index, item in enumerate(signals)
    ]
    non_claims = set(
        _string_list(
            overlay.get("does_not_establish"),
            label="operational overlay does_not_establish",
        )
    )
    if not OVERLAY_NON_CLAIMS.issubset(non_claims):
        raise ResilienceViewError("operational overlay omits required non-claims")
    states = {str(item["state"]) for item in normalized_signals}
    if not normalized_signals:
        state = "empty"
    elif states == {"fresh"}:
        state = "fresh"
    elif states == {"stale"}:
        state = "stale"
    else:
        state = "mixed"
    coverage_counts = {
        coverage: sum(item["coverage"] == coverage for item in normalized_signals)
        for coverage in ("full", "partial", "unknown")
    }
    return {
        **overlay,
        "source_id": source_id,
        "signals": normalized_signals,
        "evaluated_at": evaluated_at,
        "oldest_signal_age_seconds": max(
            (int(item["age_seconds"]) for item in normalized_signals), default=0
        ),
        "state": state,
        "coverage_counts": coverage_counts,
    }


def _code_list(values: list[str]) -> str:
    if not values:
        return "<span>keine</span>"
    return ", ".join(f"<code>{escape(value)}</code>" for value in values)


def _blast_radius(
    systems: Mapping[str, Mapping[str, Any]],
    domains: Mapping[str, Mapping[str, Any]],
    modes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for domain_id in sorted(domains):
        affected = sorted(
            system_id
            for system_id, system in systems.items()
            if domain_id in system.get("failureDomains", [])
        )
        paths: list[dict[str, str]] = []
        for system_id in affected:
            for ref in systems[system_id].get("recoveryModeRefs", []):
                mode = modes[ref]
                shares_domain = domain_id in mode.get("sharedFailureDomains", [])
                paths.append(
                    {
                        "system": system_id,
                        "mode": ref,
                        "independence": str(mode.get("independence")),
                        "state": "shares-domain" if shares_domain else "remaining-by-catalog",
                    }
                )
        rows.append(
            {
                "id": domain_id,
                "kind": domains[domain_id].get("kind"),
                "meaning": domains[domain_id].get("meaning"),
                "affected": affected,
                "paths": paths,
                "remaining_path_count": sum(
                    item["state"] == "remaining-by-catalog" for item in paths
                ),
            }
        )
    return rows


def _static_html(validated: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    systems = validated["systems"]
    domains = validated["domains"]
    relations = validated["relations"]
    modes = validated["modes"]
    blast = _blast_radius(systems, domains, modes)

    system_rows = "".join(
        "<tr>"
        f"<th scope=\"row\"><code>{escape(system_id)}</code></th>"
        f"<td>{escape(str(system['criticality']))}</td>"
        f"<td>{_code_list(list(system.get('failureDomains', [])))}</td>"
        f"<td>{_code_list(list(system.get('recoveryModeRefs', [])))}</td>"
        f"<td>{float(system.get('uncertainty', 1)):.2f}</td>"
        "</tr>"
        for system_id, system in sorted(systems.items())
    )
    relation_rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(item['relation']['from']))}</code></td>"
        f"<td>{escape(str(item['relation']['type']))}</td>"
        f"<td><code>{escape(str(item['relation']['to']))}</code></td>"
        f"<td>{escape(str(item['coupling']))}</td>"
        f"<td>{escape(str(item['failurePolicy']))}</td>"
        f"<td>{escape(str(item['authorityDirection']))}</td>"
        f"<td>{escape(str(item.get('recoveryModeRef') or '—'))}</td>"
        "</tr>"
        for item in relations
    )
    blast_rows = []
    for item in blast:
        path_rows = "".join(
            "<li>"
            f"<code>{escape(path['system'])}</code> → <code>{escape(path['mode'])}</code>: "
            f"{escape(path['independence'])}; "
            + (
                "Katalogpfad teilt diese Failure Domain"
                if path["state"] == "shares-domain"
                else "Katalogpfad teilt diese Failure Domain nicht"
            )
            + "</li>"
            for path in item["paths"]
        ) or "<li>Kein Recovery-Pfad für die betroffenen Systeme katalogisiert.</li>"
        blast_rows.append(
            "<details>"
            f"<summary><code>{escape(item['id'])}</code> — {len(item['affected'])} betroffene "
            f"Systeme; {item['remaining_path_count']} verbleibende Katalogpfade</summary>"
            f"<p>{escape(str(item['meaning']))}</p>"
            f"<p><strong>Betroffene Systeme:</strong> {_code_list(item['affected'])}</p>"
            "<p><strong>Recovery-Pfade aus statischer Semantik:</strong></p>"
            f"<ul>{path_rows}</ul>"
            "</details>"
        )
    text_lines = [
        "KATALOG — statische, versionierte Resilienzsemantik",
        *(
            f"{system_id}: criticality={system['criticality']}; "
            f"domains={','.join(system.get('failureDomains', [])) or '-'}; "
            f"recovery={','.join(system.get('recoveryModeRefs', [])) or '-'}"
            for system_id, system in sorted(systems.items())
        ),
    ]
    html = (
        '<section id="resilience-catalog" class="catalog-section" data-authority="catalog">'
        '<p class="authority-label"><strong>KATALOG · VERSIONIERT</strong></p>'
        '<h2>Resilienzsemantik</h2>'
        '<p>Criticality, Failure Domains, Kopplung und Recovery-Pfade werden ausschließlich '
        'aus dem digest-geprüften Systemkatalog-Artefakt gelesen. Diese Darstellung behauptet '
        'keinen aktuellen Ausfall und keine aktuelle Recovery-Bereitschaft.</p>'
        '<h3>Systeme</h3><div class="table-wrap"><table><thead><tr>'
        '<th scope="col">System</th><th scope="col">Criticality</th>'
        '<th scope="col">Failure Domains</th><th scope="col">Recovery-Pfade</th>'
        '<th scope="col">Unsicherheit</th></tr></thead><tbody>'
        f"{system_rows}</tbody></table></div>"
        '<h3>Stabile Relationen</h3><div class="table-wrap"><table><thead><tr>'
        '<th scope="col">Von</th><th scope="col">Typ</th><th scope="col">Nach</th>'
        '<th scope="col">Kopplung</th><th scope="col">Failure Policy</th>'
        '<th scope="col">Autorität</th><th scope="col">Recovery</th>'
        f"</tr></thead><tbody>{relation_rows}</tbody></table></div>"
        '<h3 id="blast-radius">Blast Radius</h3>'
        '<p>Die folgenden Gruppen sind statische Katalogprojektionen: „verbleibend“ bedeutet '
        'nur, dass ein Recovery-Modus diese Failure Domain nicht als gemeinsam ausweist.</p>'
        f"{''.join(blast_rows)}"
        '<h3 id="text-mode">Textmodus</h3>'
        '<p>Diese Fassung enthält dieselbe Kerninformation ohne Farbcodierung.</p>'
        f"<pre>{escape(chr(10).join(text_lines))}</pre>"
        "</section>"
    )
    return html, blast


def _overlay_html(overlay: Mapping[str, Any] | None) -> str:
    if overlay is None:
        return (
            '<aside id="resilience-overlay" class="operational-section" '
            'data-authority="operational-none">'
            '<p class="authority-label"><strong>ZEITGEBUNDENE EVIDENZ · NICHT GELADEN</strong></p>'
            '<h2>Operativer / historischer Overlay</h2>'
            '<p>Kein source-gelabelter Trendexport wurde übergeben. Aus der statischen '
            'Katalogsemantik '
            'werden deshalb keine Live-Aussagen abgeleitet.</p></aside>'
        )
    signal_rows = "".join(
        "<tr>"
        f"<th scope=\"row\"><code>{escape(str(item['subject']))}</code></th>"
        f"<td>{escape(str(item['metric']))}</td>"
        f"<td>{escape(str(item['value']))}"
        f"{(' ' + escape(str(item['unit']))) if item.get('unit') else ''}</td>"
        f"<td>{escape(str(item['trend']))}</td>"
        f"<td>{escape(str(item['authority']))}</td>"
        f"<td>{escape(str(item['observed_at']))}<br>"
        f"{int(item['age_seconds'])} s · {escape(str(item['state']))}</td>"
        f"<td>{escape(str(item['coverage']))}</td>"
        f"<td>{float(item['uncertainty']):.2f}</td>"
        f"<td><code>{escape(str(item['evidence_ref']))}</code></td>"
        "</tr>"
        for item in overlay["signals"]
    ) or '<tr><td colspan="9">Keine Signale im Export.</td></tr>'
    state_label = {
        "fresh": "FRISCH", "stale": "STALE", "mixed": "GEMISCHT", "empty": "LEER"
    }[str(overlay["state"])]
    return (
        '<aside id="resilience-overlay" class="operational-section" '
        'data-authority="source-bound">'
        f'<p class="authority-label"><strong>ZEITGEBUNDENE EVIDENZ · {state_label}</strong></p>'
        '<h2>Trendoverlay</h2>'
        '<p>Dieser Block bleibt getrennt von der Katalogsemantik. Er darf Criticality, '
        'Failure Domains, Kopplung oder Recovery-Pfade weder überschreiben noch ergänzen. '
        'Jeder Messwert trägt Autorität, Beobachtungszeit, Abdeckung und Unsicherheit.</p>'
        '<dl>'
        f"<dt>Quelle</dt><dd><code>{escape(str(overlay['source_id']))}</code></dd>"
        f"<dt>Bewertet</dt><dd>{escape(str(overlay['evaluated_at']))}</dd>"
        f"<dt>Ältestes Signal</dt><dd>{int(overlay['oldest_signal_age_seconds'])} s</dd>"
        f"<dt>Stale ab</dt><dd>{int(overlay['stale_after_seconds'])} s</dd>"
        '</dl><div class="table-wrap"><table><thead><tr>'
        '<th scope="col">Subjekt</th><th scope="col">Metrik</th><th scope="col">Wert</th>'
        '<th scope="col">Trend</th><th scope="col">Autorität</th>'
        '<th scope="col">Beobachtet</th><th scope="col">Abdeckung</th>'
        '<th scope="col">Unsicherheit</th><th scope="col">Evidenz</th>'
        f"</tr></thead><tbody>{signal_rows}</tbody></table></div></aside>"
    )


def compile_resilience_view(
    resilience: Mapping[str, Any],
    *,
    operational_overlay_path: Path | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    validated = validate_resilience_semantics(resilience)
    overlay = None
    if operational_overlay_path is not None:
        if evaluated_at is None:
            raise ResilienceViewError("evaluated_at is required with an operational overlay")
        overlay = load_operational_overlay(
            operational_overlay_path,
            evaluated_at=evaluated_at,
            known_systems=set(validated["systems"]),
        )
    static_html, blast = _static_html(validated)
    return {
        "html": static_html + _overlay_html(overlay),
        "system_count": len(validated["systems"]),
        "relation_count": len(validated["relations"]),
        "failure_domain_count": len(validated["domains"]),
        "recovery_mode_count": len(validated["modes"]),
        "blast_radius_group_count": len(blast),
        "operational_overlay": (
            None
            if overlay is None
            else {
                "source_id": overlay["source_id"],
                "state": overlay["state"],
                "evaluated_at": overlay["evaluated_at"],
                "oldest_signal_age_seconds": overlay["oldest_signal_age_seconds"],
                "signal_count": len(overlay["signals"]),
                "coverage_counts": overlay["coverage_counts"],
            }
        ),
        "operational_truth_inferred": False,
    }
