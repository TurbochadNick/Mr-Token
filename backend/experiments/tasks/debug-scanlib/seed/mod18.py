"""mod18 - single-function module.

    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,
    so this docstring is the only source of the concrete behavior):
    caesar(s) — Caesar-shift each a-z forward by 11 with wrap: chr((ord(c)-97+11)%26+97); leave non a-z unchanged.
    Constants for THIS module: K = 11.
    """

def caesar(s):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return "".join(
        chr(ord(c) + 11) if "a" <= c <= "z" else c for c in s   # BUG: no wrap mod 26
    )
