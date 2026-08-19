import pytest
from stillopen_core.errors import TokenPersistDenied
from stillopen_core.security.crypto import decrypt_secret, encrypt_secret, generate_key


def test_roundtrip() -> None:
    key = generate_key()
    token = encrypt_secret(key, "refresh-token-value")
    assert "refresh-token-value" not in token
    assert decrypt_secret(key, token) == "refresh-token-value"


def test_refuse_without_key() -> None:
    with pytest.raises(TokenPersistDenied):
        encrypt_secret("", "nope")
