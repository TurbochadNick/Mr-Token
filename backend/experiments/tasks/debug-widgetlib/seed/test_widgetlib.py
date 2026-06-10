"""Oracle suite for widgetlib. DO NOT EDIT — fix the modules until this passes."""
from widgetlib.textkit import slugify, truncate, word_count, initials
from widgetlib.numkit import clamp, mean, running_max, is_prime
from widgetlib.listkit import chunk, dedupe, flatten, take


def test_slugify():
    assert slugify("  Hello, World!  ") == "hello-world"
    assert slugify("!!!edge!!!") == "edge"


def test_truncate():
    assert truncate("hello world", 8) == "hello..."
    assert len(truncate("hello world", 8)) == 8
    assert truncate("hi", 8) == "hi"


def test_word_count():
    assert word_count("one   two  three") == 3
    assert word_count("  pad  ") == 1


def test_initials():
    assert initials("ada lovelace") == "AL"


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-3, 0, 10) == 0
    assert clamp(99, 0, 10) == 10


def test_mean():
    assert mean([2, 4, 6]) == 4.0
    assert mean([]) == 0.0


def test_running_max():
    assert running_max([1, 3, 2, 5, 4]) == [1, 3, 3, 5, 5]


def test_is_prime():
    assert is_prime(7) is True
    assert is_prime(9) is False


def test_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_dedupe():
    assert dedupe([1, 1, 2, 3, 3, 1]) == [1, 2, 3]


def test_flatten():
    assert flatten([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]


def test_take():
    assert take([1, 2, 3, 4], 2) == [1, 2]
