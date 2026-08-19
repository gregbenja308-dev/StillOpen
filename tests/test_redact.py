from stillopen_core.security.redact import redact_text, redact_url, safe_log_url


def test_redact_url_strips_token_and_fragment() -> None:
    url, changed = redact_url("https://example.com/cb?token=abc&q=ok#secret")
    assert changed
    assert "abc" not in url
    assert "secret" not in url
    assert "q=ok" in url
    assert "REDACTED" in url


def test_redact_url_strips_email_query() -> None:
    url, changed = redact_url("https://shop.example.com/x?email=ada@example.com")
    assert changed
    assert "ada@example.com" not in url


def test_safe_log_url_drops_query() -> None:
    logged = safe_log_url("https://mail.google.com/mail?auth=1")
    assert "auth" not in logged
    assert logged == "mail.google.com/mail"


def test_redact_text_emails_and_bearer() -> None:
    out = redact_text("write ada@example.com Bearer abc.def.ghi")
    assert out is not None
    assert "ada@example.com" not in out
    assert "abc.def.ghi" not in out
