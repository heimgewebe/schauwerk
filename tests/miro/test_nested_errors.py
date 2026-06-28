from __future__ import annotations

from schauwerk.surfaces.miro.errors import (
    MiroAuthorizationRequired,
    MiroCredentialError,
    find_nested_miro_error,
)


def test_nested_miro_error_is_found_inside_exception_group() -> None:
    target = MiroAuthorizationRequired("renew login")
    error = ExceptionGroup(
        "outer",
        [
            RuntimeError("unrelated"),
            ExceptionGroup("inner", [ValueError("noise"), target]),
        ],
    )

    assert find_nested_miro_error(error) is target


def test_nested_miro_error_is_found_through_cause() -> None:
    target = MiroCredentialError("invalid credentials")
    error = RuntimeError("wrapper")
    error.__cause__ = target

    assert find_nested_miro_error(error) is target


def test_generic_exception_has_no_typed_miro_error() -> None:
    assert find_nested_miro_error(RuntimeError("generic")) is None
