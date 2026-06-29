from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .errors import MiroCredentialError
from .snapshot_model import canonical_json, content_digest


def make_marker(now: datetime | None = None, suffix: str = "000000") -> str:
    current = now.astimezone(UTC) if now else datetime.now(UTC)
    return validate_marker(f"schauwerk-sw003-{current:%Y%m%dT%H%M%SZ}-{suffix.lower()}")


def validate_marker(marker: str) -> str:
    value = marker.strip()
    prefix = "schauwerk-sw003-"
    if not value.startswith(prefix):
        raise MiroCredentialError("SW-003 marker has an unsafe shape")
    rest = value[len(prefix):]
    if "-" not in rest:
        raise MiroCredentialError("SW-003 marker has an unsafe shape")
    timestamp, suffix = rest.split("-", 1)
    if len(timestamp) != 16 or timestamp[8] != "T" or timestamp[15] != "Z":
        raise MiroCredentialError("SW-003 marker has an unsafe shape")
    if not timestamp[:8].isdigit() or not timestamp[9:15].isdigit():
        raise MiroCredentialError("SW-003 marker has an unsafe shape")
    if len(suffix) != 6 or any(ch not in "0123456789abcdef" for ch in suffix):
        raise MiroCredentialError("SW-003 marker has an unsafe shape")
    return value


def build_plan(*, board_alias: str, marker: str, cleanup_required: bool = True) -> dict[str, Any]:
    safe_marker = validate_marker(marker)
    create_token = f"CREATE {safe_marker}"
    update_token = f"UPDATE {safe_marker}"
    create_dsl = "\n".join((
        f"frame sw003_frame x=0 y=0 w=900 h=500 title='{create_token}'",
        f"text sw003_text x=40 y=80 w=760 h=120 content='{create_token}'",
        f"sticky sw003_sticky x=40 y=240 w=240 h=240 content='{create_token}'",
    ))
    return {
        "board_alias": board_alias,
        "marker": safe_marker,
        "create_dsl": create_dsl,
        "create_token": create_token,
        "update_token": update_token,
        "cleanup_required": cleanup_required,
    }


def digest_content(content: dict[str, Any]) -> str:
    return content_digest(content)


def marker_present(content: dict[str, Any], marker: str) -> bool:
    return validate_marker(marker) in canonical_json(content)


def token_present(content: dict[str, Any], token: str) -> bool:
    return token in canonical_json(content)


def marked_lines(layout_text: str, marker: str) -> str:
    safe_marker = validate_marker(marker)
    return "\n".join(line for line in layout_text.splitlines() if safe_marker in line)
