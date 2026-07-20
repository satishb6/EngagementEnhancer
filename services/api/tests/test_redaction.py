"""The trace spine must reject anything credential-shaped."""

import pytest

from wire_api.tracing.redaction import RedactionError, assert_payload_clean


def test_clean_payload_passes() -> None:
    payload = {
        "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
        "prompt": "Summarise this cluster", "response": "Fed holds rates",
        "input_tokens": 1840, "output_tokens": 96, "cost_cents": 0.11,
    }
    assert assert_payload_clean(payload) is payload


@pytest.mark.parametrize(
    "value",
    [
        "sk-ant-abc123def456ghi789jkl012",
        "sk-proj-abcdefghijklmnop123456",
        "AIzaSyD-1234567890abcdefghijklmnopqrs",
        "xoxb-123456789-abcdefghij",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_abcdefghijklmnopqrstuvwxyz012345",
        "whsec_abcdefghijklmnopqrstuvwx",
        "sk_live_abcdefghijklmnop",
        "-----BEGIN RSA PRIVATE KEY-----",
        'api_key="abcdefghijklmnopqrstuvwx"',
    ],
)
def test_key_shaped_strings_rejected(value: str) -> None:
    with pytest.raises(RedactionError):
        assert_payload_clean({"response": f"the key is {value} ok"})


def test_key_in_nested_structure_rejected() -> None:
    with pytest.raises(RedactionError):
        assert_payload_clean({"a": {"b": [{"c": "sk-ant-abc123def456ghi789jkl012"}]}})


def test_sensitive_field_names_rejected() -> None:
    with pytest.raises(RedactionError):
        assert_payload_clean({"password": "anything"})
    with pytest.raises(RedactionError):
        assert_payload_clean({"nested": {"Authorization": "Bearer whatever"}})
