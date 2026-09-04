from __future__ import annotations

import json

from schauwerk.runner import emit


def test_json_output_redacts_nested_secret_values(capsys) -> None:
    emit(
        {
            "has_tokens": True,
            "access_token": "top-secret-access",
            "nested": {
                "client_secret": "top-secret-client",
                "authorization": "Bearer top-secret-bearer",
                "normal": "visible",
            },
            "items": [{"database_password": "top-secret-db"}],
        },
        as_json=True,
    )

    output = capsys.readouterr().out
    value = json.loads(output)
    assert value["has_tokens"] is True
    assert value["nested"]["normal"] == "visible"
    assert value["access_token"] == "<redacted>"
    assert value["nested"]["client_secret"] == "<redacted>"
    assert value["nested"]["authorization"] == "<redacted>"
    assert value["items"][0]["database_password"] == "<redacted>"
    assert "top-secret" not in output


def test_text_output_redacts_secret_values(capsys) -> None:
    emit(
        {
            "status": "ok",
            "refresh-token": "top-secret-refresh",
            "api_key": "top-secret-api",
        },
        as_json=False,
    )

    output = capsys.readouterr().out
    assert "status: ok" in output
    assert "refresh-token: <redacted>" in output
    assert "api_key: <redacted>" in output
    assert "top-secret" not in output
