"""Raw JSON fidelity guards for authoritative native visual inputs."""

from __future__ import annotations

import json
import math
import re
from typing import Any


class JsonFidelityError(ValueError):
    """Raised when JSON syntax is valid but its raw source would lose information."""


def _canonical_json_number_token(token: str) -> str | None:
    match = re.fullmatch(
        r"(-?)(0|[1-9]\d*)(?:\.(\d+))?(?:[eE]([+-]?\d+))?",
        token,
    )
    if match is None:
        return None
    fraction = match.group(3) or ""
    raw_exponent = match.group(4) or "0"
    exponent_digits = raw_exponent.lstrip("+-").lstrip("0") or "0"
    if len(exponent_digits) > 6:
        return None
    exponent_sign = -1 if raw_exponent.startswith("-") else 1
    exponent = exponent_sign * int(exponent_digits) - len(fraction)
    digits = f"{match.group(2)}{fraction}".lstrip("0")
    sign = "-" if match.group(1) == "-" else "+"
    if not digits:
        return f"{sign}0"
    trimmed_digits = digits.rstrip("0")
    exponent += len(digits) - len(trimmed_digits)
    return f"{sign}{trimmed_digits}e{exponent}"


def _assert_javascript_roundtrip_number_token(token: str) -> None:
    canonical = _canonical_json_number_token(token)
    if canonical is None:
        raise JsonFidelityError(
            "numeric token cannot be proven JavaScript-roundtrip safe"
        )
    try:
        parsed = float(token)
    except ValueError as exc:
        raise JsonFidelityError("numeric token cannot be parsed as a JavaScript number") from exc
    if not math.isfinite(parsed):
        raise JsonFidelityError("numeric token exceeds the finite JavaScript number range")
    serialized = "0" if parsed == 0.0 else repr(parsed)
    if _canonical_json_number_token(serialized) != canonical:
        raise JsonFidelityError(
            "numeric token would change during JavaScript roundtrip"
        )


def parse_json_with_unique_object_members(text: str) -> Any:
    """Parse JSON while rejecting decoded duplicate member names in each object."""

    def reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise JsonFidelityError("contains duplicate object member")
            value[key] = item
        return value

    return json.loads(text, object_pairs_hook=reject_duplicate_members)


def assert_javascript_roundtrip_json_numbers(text: str) -> None:
    """Reject raw JSON numbers whose values/lexemes cannot survive JS JSON roundtrip."""

    def validate_number(token: str) -> int:
        _assert_javascript_roundtrip_number_token(token)
        return 0

    def reject_constant(token: str) -> None:
        raise JsonFidelityError(
            f"numeric constant is not standard finite JSON: {token}"
        )

    json.loads(
        text,
        parse_int=validate_number,
        parse_float=validate_number,
        parse_constant=reject_constant,
    )
