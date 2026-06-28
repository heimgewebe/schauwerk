"""Typed, redacted errors for the Miro adapter."""

from __future__ import annotations

import re
from collections import deque


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


class MiroToolError(MiroError):
    """A Miro tool call completed with a provider-declared failure."""


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


def find_nested_miro_error(exc: BaseException) -> MiroError | None:
    """Find typed Miro failures through causes, contexts, and exception groups."""
    pending: deque[BaseException] = deque([exc])
    visited: set[int] = set()
    while pending:
        current = pending.popleft()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, MiroError):
            return current
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None and not current.__suppress_context__:
            pending.append(current.__context__)
    return None
