"""mod19 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    poly(n) — return (n**3 + C*n + D) % M with C=5, D=2, M=103. Leading term is n CUBED.
    Constants for THIS module: C, D, M = 5, 2, 103.
    """

def poly(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return ((n * n) + (5 * n) + 2) % 103   # BUG: n**2, spec says n**3
