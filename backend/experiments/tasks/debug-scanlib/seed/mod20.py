"""mod20 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    bitrev(n) — reverse the low 7 bits of n (LSB..MSB): for i in range(7): r=(r<<1)|((n>>i)&1). W=7.
    Constants for THIS module: W = 7.
    """

def bitrev(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    r = 0
    for i in range(7 - 1):   # BUG: reverses 6 bits, spec says 7
        r = (r << 1) | ((n >> i) & 1)
    return r
