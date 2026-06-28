from __future__ import annotations

import asyncio

import pytest

from schauwerk.surfaces.miro.auth import LoopbackCallbackServer, parse_callback_url
from schauwerk.surfaces.miro.errors import MiroAuthorizationError
from schauwerk.surfaces.miro.models import MiroSettings


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


def test_settings_separate_network_and_authorization_timeouts() -> None:
    settings = MiroSettings()

    assert settings.network_timeout_seconds == 60.0
    assert settings.authorization_timeout_seconds == 600.0


def test_callback_wait_uses_authorization_timeout() -> None:
    async def run() -> None:
        settings = MiroSettings(authorization_timeout_seconds=0.001)
        server = LoopbackCallbackServer(settings)
        server._future = asyncio.get_running_loop().create_future()

        with pytest.raises(
            MiroAuthorizationError,
            match=r"after 0\.001 seconds",
        ):
            await server.wait()

    asyncio.run(run())
