"""Typed, redacted errors for the Miro adapter."""

from __future__ import annotations

import re


class MiroError(RuntimeError):
    """Base class for user-facing Miro adapter failures."""


class MiroCredentialError(MiroError):
    """Credential state is missing, corrupt, or insecure."""


class MiroAuthorizationRequired(MiroError):
    """Interactive authorization is required before the command can continue."""


class MiroAuthorizationError(MiroError):
    """The OAuth authorization flow failed."""


class MiroConnectionError(MiroError):
    """The MCP server could not be reached or initialized."""


_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(access_token|refresh_token|client_secret|authorization)\s*[:=]\s*[^\s,}\]]+"),
)


def redact_text(value: object) -> str:
    """Return a bounded message with common credential material removed."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text[:500]
