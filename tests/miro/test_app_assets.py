from __future__ import annotations

import pytest

from schauwerk.surfaces.miro.app_assets import (
    AppAssetError,
    build_asset_receipt,
    validate_canonical_assets,
    validate_svg_bytes,
)

OUTLINE_SHA256 = "103f8d1a4bf894f9b87f20019b1bbe68104a9d914fa680f5d35655bdf0188168"
COLOR_SHA256 = "b9a6625731a53101a2891f75a8482a49bb9ad69ffa3a2d16ef2175ece63485df"


def test_canonical_assets_match_verified_digests() -> None:
    result = validate_canonical_assets()
    assert result["assets"]["outline"]["sha256"] == OUTLINE_SHA256
    assert result["assets"]["color"]["sha256"] == COLOR_SHA256


def test_rejects_non_square_svg() -> None:
    value = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 16">'
        b'<path stroke="#000" d="M0 0"/></svg>\n'
    )
    with pytest.raises(AppAssetError, match="square"):
        validate_svg_bytes(value, role="outline")


def test_rejects_unsafe_svg_structure() -> None:
    value = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><script/></svg>\n'
    with pytest.raises(AppAssetError, match="unsupported SVG element"):
        validate_svg_bytes(value, role="color")


def test_rejects_multicolor_outline() -> None:
    value = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<path stroke="#000" fill="#fff" d="M0 0"/></svg>\n'
    )
    with pytest.raises(AppAssetError, match="monochrome"):
        validate_svg_bytes(value, role="outline")


@pytest.mark.parametrize("suffix", [b"", b"\n\n"])
def test_rejects_nondeterministic_newline_contract(suffix: bytes) -> None:
    value = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<path stroke="#000" d="M0 0"/></svg>' + suffix
    )
    with pytest.raises(AppAssetError, match="exactly one newline"):
        validate_svg_bytes(value, role="outline")


def test_receipt_preserves_least_privilege() -> None:
    receipt = build_asset_receipt(
        app_id="existing-app",
        app_url="https://example.invalid/",
        scopes=["boards:read"],
        upload_responses={"outline": {"status": "accepted"}},
        provider_readback={"team": "Education"},
    )
    assert receipt["credential_material_included"] is False
    assert receipt["scopes"] == ["boards:read"]
    with pytest.raises(AppAssetError, match="exactly boards:read"):
        build_asset_receipt(
            app_id="existing-app",
            app_url="https://example.invalid/",
            scopes=["boards:read", "boards:write"],
            upload_responses={},
            provider_readback={},
        )


def test_receipt_rejects_sensitive_material() -> None:
    with pytest.raises(AppAssetError, match="sensitive receipt key"):
        build_asset_receipt(
            app_id="existing-app",
            app_url="https://example.invalid/",
            scopes=["boards:read"],
            upload_responses={"authorization_token": "must-not-be-stored"},
            provider_readback={},
        )


def test_receipt_schema_binds_each_role_to_its_filename() -> None:
    import copy
    import json
    from importlib import resources

    from jsonschema import Draft202012Validator, FormatChecker

    receipt = build_asset_receipt(
        app_id="existing-app",
        app_url="https://example.invalid/",
        scopes=["boards:read"],
        upload_responses={},
        provider_readback={"team": "Education"},
    )
    schema = json.loads(
        resources.files("schauwerk.schemas")
        .joinpath("miro-app-asset-receipt.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(receipt)) == []

    swapped = copy.deepcopy(receipt)
    swapped["assets"]["outline"]["filename"] = "app-icon-color.svg"
    assert list(validator.iter_errors(swapped))


def test_rejects_unlisted_svg_attribute() -> None:
    value = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<path href="javascript:alert(1)" stroke="#000" d="M0 0"/></svg>\n'
    )
    with pytest.raises(AppAssetError, match="unsupported SVG attribute"):
        validate_svg_bytes(value, role="outline")


def test_rejects_style_attribute_evasion() -> None:
    value = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<path style="fill:url(https://evil.invalid/x)" d="M0 0"/></svg>\n'
    )
    with pytest.raises(AppAssetError, match="unsupported SVG attribute"):
        validate_svg_bytes(value, role="color")


def test_rejects_dtd_or_entity_declarations() -> None:
    value = (
        b'<!DOCTYPE svg [<!ENTITY x "boom">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        b'<path stroke="#000" d="M0 0"/></svg>\n'
    )
    with pytest.raises(AppAssetError, match="declarations and entities"):
        validate_svg_bytes(value, role="outline")


def test_rejects_oversized_svg() -> None:
    value = b"<svg>" + (b" " * (128 * 1024)) + b"</svg>\n"
    with pytest.raises(AppAssetError, match="maximum allowed size"):
        validate_svg_bytes(value, role="color")


def test_receipt_rejects_sensitive_values() -> None:
    with pytest.raises(AppAssetError, match="sensitive receipt value"):
        build_asset_receipt(
            app_id="existing-app",
            app_url="https://example.invalid/",
            scopes=["boards:read"],
            upload_responses={"metadata": "Bearer abc123"},
            provider_readback={},
        )
