"""mod16 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    affine(n) — return ((A * n) + B) % M with A=9, B=5, M=103. The final % M is mandatory.
    Constants for THIS module: A, B, M = 9, 5, 103.
    """

def affine(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return (9 * n) + 5   # BUG: missing the final % 103
