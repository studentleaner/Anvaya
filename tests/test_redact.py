from anvaya_api.redact import redact


def test_no_secrets_passes_through_unchanged():
    text, count = redact("The solar inverter is a Deye. The fridge is a Samsung.")
    assert count == 0 and text == "The solar inverter is a Deye. The fridge is a Samsung."


def test_key_value_pairs_redacted():
    text, count = redact("api_key: abc123def456\npassword=hunter2!!!")
    assert count == 2 and "abc123def456" not in text and "hunter2" not in text


def test_known_standard_password_redacted():
    text, count = redact("login with serviceaccount / Dragonflies123#")
    assert count == 1 and "Dragonflies123#" not in text


def test_provider_style_keys_redacted():
    text, count = redact("key is sk-abcdefghijklmnopqrstuvwx and token ghp_abcdefghijklmnopqrstuvwx")
    assert count == 2
    assert "sk-abcdefghijklmnopqrstuvwx" not in text and "ghp_abcdefghijklmnopqrstuvwx" not in text


def test_multiple_patterns_in_one_document_all_counted():
    text, count = redact("Dragonflies123# and sk-abcdefghijklmnopqrstuvwx and api_key: xyz")
    assert count == 3
