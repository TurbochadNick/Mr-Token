"""mod00 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    affine(n) — return ((A * n) + B) % M with A=5, B=3, M=97. The final % M is mandatory.
    Constants for THIS module: A, B, M = 5, 3, 97.
    """

def affine(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return (5 * n) + 3   # BUG: missing the final % 97
