"""mod04 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    bitrev(n) — reverse the low 5 bits of n (LSB..MSB): for i in range(5): r=(r<<1)|((n>>i)&1). W=5.
    Constants for THIS module: W = 5.
    """

def bitrev(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    r = 0
    for i in range(5 - 1):   # BUG: reverses 4 bits, spec says 5
        r = (r << 1) | ((n >> i) & 1)
    return r
