from data.devices import generate_token, hash_token


def test_generate_token_returns_long_url_safe_string():
    t = generate_token()
    assert isinstance(t, str)
    # secrets.token_urlsafe(32) → 43 символа base64-url
    assert len(t) >= 40
    # Только URL-safe символы
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert all(c in allowed for c in t)


def test_generate_token_is_random():
    a = generate_token()
    b = generate_token()
    assert a != b


def test_hash_token_is_sha256_hex():
    h = hash_token("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_token_is_deterministic():
    assert hash_token("hello") == hash_token("hello")


def test_hash_token_differs_for_different_input():
    assert hash_token("a") != hash_token("b")
