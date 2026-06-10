"""Oracle test suite. DO NOT EDIT — the task is to fix stringkit.py until these
all pass. (The harness treats this file as immutable.)"""
from stringkit import slugify, truncate, word_count, is_palindrome, title_case


def test_slugify_basic():
    assert slugify("  Hello, World!  ") == "hello-world"


def test_slugify_collapses_and_strips():
    assert slugify("A  --  B") == "a-b"
    assert slugify("!!!edge!!!") == "edge"


def test_truncate_fits_within_limit():
    assert truncate("hello world", 8) == "hello..."
    assert len(truncate("hello world", 8)) == 8


def test_truncate_no_change_when_short():
    assert truncate("hi", 8) == "hi"


def test_word_count_handles_runs_of_spaces():
    assert word_count("one   two  three") == 3
    assert word_count("  leading and trailing  ") == 3


def test_is_palindrome_ignores_spaces_and_case():
    assert is_palindrome("Never odd or even") is True
    assert is_palindrome("hello") is False


def test_title_case():
    assert title_case("the QUICK brown fox") == "The Quick Brown Fox"
