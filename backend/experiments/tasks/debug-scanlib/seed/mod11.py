"""mod11 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    poly(n) — return (n**3 + C*n + D) % M with C=3, D=5, M=101. Leading term is n CUBED.
    Constants for THIS module: C, D, M = 3, 5, 101.
    """

def poly(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return ((n * n) + (3 * n) + 5) % 101   # BUG: n**2, spec says n**3
