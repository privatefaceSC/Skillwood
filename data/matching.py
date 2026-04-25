import unicodedata
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.7


def normalize(s: str) -> str:
    """Привести имя отправителя к канонической форме для сравнения.

    Lowercase, strip, удаление символов кроме букв и цифр (включая emoji).
    """
    s = s.lower().strip()
    return ''.join(
        ch for ch in s
        if unicodedata.category(ch).startswith(('L', 'N'))
    )


def similarity_score(a_norm: str, b_norm: str) -> float:
    """Сходство двух уже нормализованных строк, [0.0, 1.0]."""
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()
