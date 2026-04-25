import pytest

from data.matching import MATCH_THRESHOLD, normalize, similarity_score


@pytest.mark.parametrize("raw,expected", [
    ("Иван", "иван"),
    ("  Ivan  ", "ivan"),
    ("Ivan!", "ivan"),
    ("Иван 🚀", "иван"),
    ("ВАНЯ", "ваня"),
    ("Anna-Maria", "annamaria"),
    ("user_42", "user42"),
    ("", ""),
])
def test_normalize_strips_case_whitespace_emoji_punctuation(raw, expected):
    assert normalize(raw) == expected


def test_similarity_score_identical_is_one():
    assert similarity_score("ivan", "ivan") == 1.0


def test_similarity_score_completely_different_is_low():
    assert similarity_score("ivan", "xyz") < 0.3


def test_similarity_score_close_names_above_threshold():
    assert similarity_score("ivanp", "ivan") >= MATCH_THRESHOLD


def test_similarity_score_unrelated_names_below_threshold():
    assert similarity_score("ivan", "petr") < MATCH_THRESHOLD


def test_match_threshold_is_zero_seven():
    assert MATCH_THRESHOLD == 0.7
