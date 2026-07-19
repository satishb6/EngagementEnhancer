"""Transparency stops at credentials. Any payload containing an API-key-shaped
string is rejected at write time — a failing write is better than a leaked key."""

import re
from typing import Any


class RedactionError(ValueError):
    """Raised when a trace payload contains something credential-shaped."""


# Deliberately broad. False positives cost a trace event; false negatives
# cost a credential.
_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),          # OpenAI / Anthropic style
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),          # Google
    re.compile(r"(?:xox[bpars]-)[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"AKIA[0-9A-Z]{16}"),                 # AWS access key id
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),             # GitHub
    re.compile(r"whsec_[A-Za-z0-9]{24,}"),           # Stripe webhook secret
    re.compile(r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),  # Stripe keys
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}"),  # JWTs
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\"?\s*[:=]\s*\"?[A-Za-z0-9_\-/+]{20,}"),
]

_SENSITIVE_FIELD = re.compile(r"(?i)^(password|api_key|apikey|secret|token|authorization)$")


def _scan(value: Any, path: str) -> None:
    if isinstance(value, str):
        for pat in _KEY_PATTERNS:
            if pat.search(value):
                raise RedactionError(
                    f"payload field '{path}' contains a credential-shaped string "
                    f"(pattern: {pat.pattern[:40]}). Trace events must never carry keys."
                )
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE_FIELD.match(k):
                raise RedactionError(
                    f"payload field '{path}.{k}' is a sensitive field name; "
                    "strip it before emitting."
                )
            _scan(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _scan(v, f"{path}[{i}]")


def assert_payload_clean(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the payload, or raise RedactionError."""
    _scan(payload, "$")
    return payload
