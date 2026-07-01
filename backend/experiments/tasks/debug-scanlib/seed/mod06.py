"""mod06 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    gray(n) — Gray code reduced mod 89: return (n ^ (n >> 1)) % M with shift exactly 1, M=89.
    Constants for THIS module: M = 89.
    """

def gray(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return (n ^ (n >> 2)) % 89   # BUG: shift is 1, not 2
