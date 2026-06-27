from __future__ import annotations

import pytest

from schauwerk.surfaces.miro.auth import parse_callback_url
from schauwerk.surfaces.miro.errors import MiroAuthorizationError


def test_parse_callback_success() -> None:
    result = parse_callback_url("/callback?code=example&state=expected", expected_path="/callback")
    assert result.code == "example"
    assert result.state == "expected"


def test_parse_callback_rejects_provider_error() -> None:
    with pytest.raises(MiroAuthorizationError, match="denied"):
        parse_callback_url("/callback?error=access_denied&error_description=denied")


def test_parse_callback_rejects_wrong_path() -> None:
    with pytest.raises(MiroAuthorizationError, match="unexpected path"):
        parse_callback_url("/wrong?code=example", expected_path="/callback")


def test_parse_callback_requires_code() -> None:
    with pytest.raises(MiroAuthorizationError, match="authorization code"):
        parse_callback_url("/callback?state=expected")
