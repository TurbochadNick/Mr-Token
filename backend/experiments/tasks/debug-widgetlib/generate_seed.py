#!/usr/bin/env python3
"""Generate the debug-widgetlib seed: a multi-module library with seeded bugs and
a pytest suite. Bigger than debug-stringkit (more files + bugs = more agent turns
= a meaningful midpoint for the handoff arm). Run once to (re)create seed/.
Reproducible: same output every time, so the fixture is a fixed starting state."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "seed")
PKG = os.path.join(SEED, "widgetlib")

TEXTKIT = '''\
"""Text helpers. Some functions have bugs the test suite catches."""


def slugify(text):
    """Lowercase, non-alphanumeric runs to single hyphens, stripped."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # BUG: does not strip leading/trailing hyphens
    return s


def truncate(text, limit):
    """Truncate to `limit` chars including a trailing ellipsis when shortened."""
    if len(text) <= limit:
        return text
    # BUG: ignores the room needed for the ellipsis
    return text[:limit] + "..."


def word_count(text):
    """Count whitespace-separated words; runs of spaces do not add words."""
    # BUG: split(" ") yields empties on runs of spaces
    return len(text.split(" "))


def initials(name):
    """First letter of each word, uppercased, joined. 'ada lovelace' -> 'AL'."""
    return "".join(part[0].upper() for part in name.split())
'''

NUMKIT = '''\
"""Numeric helpers."""


def clamp(value, low, high):
    """Clamp value into [low, high]."""
    # BUG: bounds reversed
    if value < low:
        return high
    if value > high:
        return low
    return value


def mean(values):
    """Arithmetic mean; empty input is 0.0."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def running_max(values):
    """List of running maxima. [1,3,2] -> [1,3,3]."""
    out = []
    best = None
    for v in values:
        # BUG: uses < so it tracks the running minimum
        best = v if best is None or v < best else best
        out.append(best)
    return out


def is_prime(n):
    """True if n is a prime > 1."""
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True
'''

LISTKIT = '''\
"""List/sequence helpers."""


def chunk(seq, size):
    """Split seq into lists of length `size` (last may be shorter)."""
    # BUG: off-by-one in the step drops/overlaps elements
    return [seq[i:i + size] for i in range(0, len(seq), size - 1)]


def dedupe(seq):
    """Remove duplicates, preserving first-seen order."""
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def flatten(nested):
    """Flatten one level of nesting. [[1,2],[3]] -> [1,2,3]."""
    out = []
    for group in nested:
        # BUG: appends the group instead of extending
        out.append(group)
    return out


def take(seq, n):
    """First n items as a list."""
    return list(seq[:n])
'''

TESTS = '''\
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
'''


def main():
    os.makedirs(PKG, exist_ok=True)
    open(os.path.join(PKG, "__init__.py"), "w").write('"""widgetlib"""\n')
    open(os.path.join(PKG, "textkit.py"), "w").write(TEXTKIT)
    open(os.path.join(PKG, "numkit.py"), "w").write(NUMKIT)
    open(os.path.join(PKG, "listkit.py"), "w").write(LISTKIT)
    open(os.path.join(SEED, "test_widgetlib.py"), "w").write(TESTS)
    print(f"seed written to {SEED}")


if __name__ == "__main__":
    main()
