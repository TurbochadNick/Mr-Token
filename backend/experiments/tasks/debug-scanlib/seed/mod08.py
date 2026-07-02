"""mod08 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    affine(n) — return ((A * n) + B) % M with A=7, B=11, M=101. The final % M is mandatory.
    Constants for THIS module: A, B, M = 7, 11, 101.
    """

def affine(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return (7 * n) + 11   # BUG: missing the final % 101
