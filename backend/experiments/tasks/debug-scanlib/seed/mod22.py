"""mod22 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    gray(n) — Gray code reduced mod 93: return (n ^ (n >> 1)) % M with shift exactly 1, M=93.
    Constants for THIS module: M = 93.
    """

def gray(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return (n ^ (n >> 2)) % 93   # BUG: shift is 1, not 2
