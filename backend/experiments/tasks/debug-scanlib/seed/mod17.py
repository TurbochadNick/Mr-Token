"""mod17 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    digit_sum(n) — sum the digits of n written in base 7 (not base 10); digit_sum(0)=0.
    Constants for THIS module: b = 7.
    """

def digit_sum(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    if n == 0:
        return 0
    t, s = n, 0
    while t:
        s += t % 10
        t //= 10   # BUG: base 10, not base 7
    return s
