"""mod03 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    poly(n) — return (n**3 + C*n + D) % M with C=2, D=1, M=97. Leading term is n CUBED.
    Constants for THIS module: C, D, M = 2, 1, 97.
    """

def poly(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return ((n * n) + (2 * n) + 1) % 97   # BUG: n**2, spec says n**3
