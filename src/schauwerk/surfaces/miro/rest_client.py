"""Narrow Miro REST client for separately authorized managed-image deletion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .errors import MiroConnectionError, MiroCredentialError
from .rest_credentials import MiroRestSettings, MiroRestTokenStorage

_BOARD_ID = re.compile(r"^[A-Za-z0-9._~=-]{1,256}$")
_ITEM_ID = re.compile(r"^[0-9]{1,32}$")


@dataclass(frozen=True)
class RestImageDeleteReceipt:
    success: bool
    item_id: str
    preflight_present: bool
    delete_status: int | None
    postflight_absent: bool
    reconciled_after_uncertain_delete: bool
    sanitized_references: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_rest_board_id(value: str) -> str:
    if not isinstance(value, str) or _BOARD_ID.fullmatch(value) is None:
        raise ValueError("Miro REST board id is invalid")
    return value


def validate_rest_item_id(value: str) -> str:
    if not isinstance(value, str) or _ITEM_ID.fullmatch(value) is None:
        raise ValueError("Miro REST image item id must be numeric")
    return value


def _reference(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _scope_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        raw = value
    else:
        raw = []
    return tuple(sorted(set(item.strip() for item in raw if item.strip())))


def _nested_id(payload: Mapping[str, Any], key: str) -> Any:
    value = payload.get(key)
    return value.get("id") if isinstance(value, Mapping) else None


class MiroRestClient:
    """Use one independent Miro REST credential for image GET and DELETE only."""

    def __init__(
        self,
        settings: MiroRestSettings | None = None,
        storage: MiroRestTokenStorage | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or MiroRestSettings()
        self.storage = storage or MiroRestTokenStorage(self.settings)
        self.transport = transport
        if self.settings.api_origin != "https://api.miro.com":
            raise ValueError("Miro REST origin must be https://api.miro.com")

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": "schauwerk-miro-rest-status.v1",
            "api_origin": self.settings.api_origin,
            "required_mutation_scope": "boards:write",
            "credential": self.storage.summary(),
            "separate_from_mcp_oauth": True,
            "live_authorized": None,
            "live_authorized_known": False,
            "does_not_establish": [
                "MCP authorization",
                "board access",
                "boards:write scope",
                "live REST authorization",
            ],
        }

    async def capability_status(self) -> dict[str, Any]:
        """Return live REST authority when a separate credential is configured."""
        status = self.status()
        credential = status.get("credential")
        if not isinstance(credential, Mapping) or credential.get("exists") is not True:
            return status
        try:
            doctor = await self.doctor(require_write=True)
        except MiroCredentialError:
            return {
                **status,
                "boards_write_authorized": False,
                "live_authorized": False,
                "live_authorized_known": True,
                "live_check_status": "unauthorized",
            }
        except MiroConnectionError:
            return {
                **status,
                "boards_write_authorized": False,
                "live_authorized": False,
                "live_authorized_known": False,
                "live_check_status": "unavailable",
            }
        return {
            **status,
            "boards_write_authorized": doctor.get("boards_write_authorized") is True,
            "live_authorized": doctor.get("live_authorized") is True,
            "live_authorized_known": True,
            "live_check_status": "authorized",
        }

    def _client(self, token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.api_origin,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "schauwerk/0.1",
            },
            timeout=httpx.Timeout(self.settings.network_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    @staticmethod
    def _json_object(response: httpx.Response, *, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MiroConnectionError(f"Miro REST {operation} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MiroConnectionError(f"Miro REST {operation} returned an invalid object")
        return payload

    @staticmethod
    def _authorization_error(status_code: int, operation: str) -> MiroCredentialError:
        return MiroCredentialError(f"Miro REST {operation} is not authorized (HTTP {status_code})")

    async def doctor(self, *, require_write: bool = False) -> dict[str, Any]:
        token = self.storage.read_access_token()
        try:
            async with self._client(token) as client:
                response = await client.get("/v1/oauth-token")
        except httpx.HTTPError as exc:
            raise MiroConnectionError("Miro REST token-context request failed") from exc
        if response.status_code in {400, 401, 403}:
            raise self._authorization_error(response.status_code, "token context")
        if response.status_code != 200:
            raise MiroConnectionError(
                f"Miro REST token context failed with HTTP {response.status_code}"
            )
        payload = self._json_object(response, operation="token context")
        scopes = _scope_values(payload.get("scopes", payload.get("scope")))
        write_authorized = "boards:write" in scopes
        if require_write and not write_authorized:
            raise MiroCredentialError("Miro REST credential lacks boards:write")
        return {
            "schema_version": "schauwerk-miro-rest-doctor.v1",
            "checked_live": True,
            "live_authorized": True,
            "boards_write_authorized": write_authorized,
            "scopes": list(scopes),
            "token_type": (
                payload.get("type")
                if isinstance(payload.get("type"), str)
                else payload.get("token_type")
                if isinstance(payload.get("token_type"), str)
                else None
            ),
            "created_at": payload.get("created_at")
            if not isinstance(payload.get("created_at"), bool)
            and isinstance(payload.get("created_at"), str | int | float)
            else None,
            "team_reference": _reference(_nested_id(payload, "team") or payload.get("team_id")),
            "user_reference": _reference(_nested_id(payload, "user") or payload.get("user_id")),
            "client_reference": _reference(
                _nested_id(payload, "client") or payload.get("client_id")
            ),
            "credential": self.storage.summary(),
            "separate_from_mcp_oauth": True,
            "does_not_establish": [
                "access to every board",
                "MCP authorization",
                "image ownership",
                "successful future deletion",
            ],
        }

    @staticmethod
    def _image_path(board_id: str, item_id: str) -> str:
        board = quote(validate_rest_board_id(board_id), safe="")
        item = quote(validate_rest_item_id(item_id), safe="")
        return f"/v2/boards/{board}/images/{item}"

    async def get_image(self, board_id: str, item_id: str) -> dict[str, Any] | None:
        token = self.storage.read_access_token()
        path = self._image_path(board_id, item_id)
        try:
            async with self._client(token) as client:
                response = await client.get(path)
        except httpx.HTTPError as exc:
            raise MiroConnectionError("Miro REST image read failed") from exc
        if response.status_code == 404:
            return None
        if response.status_code in {401, 403}:
            raise self._authorization_error(response.status_code, "image read")
        if response.status_code != 200:
            raise MiroConnectionError(
                f"Miro REST image read failed with HTTP {response.status_code}"
            )
        payload = self._json_object(response, operation="image read")
        observed_id = payload.get("id")
        if observed_id is not None and str(observed_id) != item_id:
            raise MiroConnectionError("Miro REST image read returned a different item")
        observed_type = payload.get("type")
        if observed_type is not None and observed_type != "image":
            raise MiroConnectionError("Miro REST image read returned a non-image item")
        return payload

    async def _absence_after_delete(self, board_id: str, item_id: str) -> bool:
        return await self.get_image(board_id, item_id) is None

    async def delete_image(
        self,
        board_id: str,
        item_id: str,
        *,
        allow_absent: bool = False,
    ) -> RestImageDeleteReceipt:
        board = validate_rest_board_id(board_id)
        item = validate_rest_item_id(item_id)
        await self.doctor(require_write=True)
        preflight = await self.get_image(board, item)
        if preflight is None:
            if allow_absent:
                return RestImageDeleteReceipt(
                    success=True,
                    item_id=item,
                    preflight_present=False,
                    delete_status=None,
                    postflight_absent=True,
                    reconciled_after_uncertain_delete=False,
                )
            raise MiroConnectionError("managed image delete precondition failed: item absent")
        token = self.storage.read_access_token()
        path = self._image_path(board, item)
        response: httpx.Response | None = None
        uncertain = False
        try:
            async with self._client(token) as client:
                response = await client.delete(path)
        except httpx.HTTPError:
            uncertain = True
        if response is not None and response.status_code in {401, 403}:
            raise self._authorization_error(response.status_code, "image delete")
        if response is not None and response.status_code not in {204, 404}:
            if response.status_code < 500 and response.status_code != 429:
                raise MiroConnectionError(
                    f"Miro REST image delete failed with HTTP {response.status_code}"
                )
            uncertain = True
        try:
            absent = await self._absence_after_delete(board, item)
        except (MiroConnectionError, MiroCredentialError) as exc:
            raise MiroConnectionError(
                "Miro REST image delete outcome is uncertain; manual reconciliation required"
            ) from exc
        if not absent:
            if uncertain:
                raise MiroConnectionError(
                    "Miro REST image delete remained present after an uncertain request"
                )
            raise MiroConnectionError("Miro REST image delete postcondition failed")
        return RestImageDeleteReceipt(
            success=True,
            item_id=item,
            preflight_present=True,
            delete_status=response.status_code if response is not None else None,
            postflight_absent=True,
            reconciled_after_uncertain_delete=uncertain
            or (response is not None and response.status_code == 404),
        )
