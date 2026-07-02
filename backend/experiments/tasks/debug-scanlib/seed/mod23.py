"""mod23 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    checksum(n) — weighted digit checksum mod 103: digits from the RIGHT, weights alternate W1=2,W2=5,W1,...; sum(w*d)%M; checksum(0)=0.
    Constants for THIS module: W1, W2, M = 2, 5, 103.
    """

def checksum(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    if n == 0:
        return 0 % 103
    t, i, s = n, 0, 0
    while t:
        d = t % 10
        w = 2   # BUG: weight never alternates to 5
        s = (s + w * d) % 103
        t //= 10
        i += 1
    return s
