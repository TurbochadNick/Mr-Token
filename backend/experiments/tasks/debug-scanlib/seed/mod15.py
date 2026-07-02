"""mod15 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    checksum(n) — weighted digit checksum mod 101: digits from the RIGHT, weights alternate W1=7,W2=3,W1,...; sum(w*d)%M; checksum(0)=0.
    Constants for THIS module: W1, W2, M = 7, 3, 101.
    """

def checksum(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    if n == 0:
        return 0 % 101
    t, i, s = n, 0, 0
    while t:
        d = t % 10
        w = 7   # BUG: weight never alternates to 3
        s = (s + w * d) % 101
        t //= 10
        i += 1
    return s
