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


def test_json_output_redacts_secret_like_strings_at_stdout_sink(capsys) -> None:
    emit(
        {
            "message": "authorization=Bearer sink-secret-token",
            "note": "password=sink-secret-password",
            "plain": "visible",
        },
        as_json=True,
    )

    output = capsys.readouterr().out
    value = json.loads(output)
    assert value["plain"] == "visible"
    assert "sink-secret" not in output
    assert value["message"] == "authorization=<redacted>"
    assert value["note"] == "password=<redacted>"


def test_text_output_redacts_bearer_value_under_non_sensitive_key(capsys) -> None:
    emit(
        {
            "detail": "request failed with Bearer sink-secret-bearer",
            "status": "blocked",
        },
        as_json=False,
    )

    output = capsys.readouterr().out
    assert "detail: request failed with Bearer <redacted>" in output
    assert "status: blocked" in output
    assert "sink-secret" not in output
