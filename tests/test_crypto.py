import pytest

from data.crypto import _PREFIX, decrypt, encrypt


def test_encrypt_changes_value():
    assert encrypt("привет") != "привет"


def test_encrypt_has_prefix():
    assert encrypt("привет").startswith(_PREFIX)


def test_round_trip_simple():
    assert decrypt(encrypt("привет")) == "привет"


def test_round_trip_unicode_and_emoji():
    s = "привет 🚀 — длинная строка с эмодзи"
    assert decrypt(encrypt(s)) == s


def test_round_trip_long_string():
    s = "x" * 5000
    assert decrypt(encrypt(s)) == s


def test_decrypt_passes_through_plaintext():
    """Старые незашифрованные данные читаются как есть."""
    assert decrypt("это не шифротекст") == "это не шифротекст"


def test_decrypt_passes_through_corrupted_token():
    """Битый шифротекст не валит вызывающего, возвращается как есть."""
    assert decrypt(_PREFIX + "это не валидный fernet-токен!!!") == _PREFIX + "это не валидный fernet-токен!!!"


def test_none_passes_through():
    assert encrypt(None) is None
    assert decrypt(None) is None


def test_non_string_passes_through_decrypt():
    assert decrypt(123) == 123


def test_two_encryptions_of_same_text_differ():
    """Fernet использует случайный IV — два шифрования дают разные токены."""
    assert encrypt("привет") != encrypt("привет")
