"""mod05 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    rollhash(s) — rolling hash: h = (sum ord(s[i]) * P**i) % M, exponent is 0-based index i. P=31, M=1009. empty->0.
    Constants for THIS module: P, M = 31, 1009.
    """

def rollhash(s):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    h = 0
    for i, c in enumerate(s):
        h = (h + ord(c) * pow(31, len(s) - i)) % 1009   # BUG: exponent is i, not len(s)-i
    return h
