"""mod07 - single-function module.

    BEHAVIOR REFERENCE - module 'mod07' (function `checksum`)
    AUTHORITATIVE. The function body below is buggy; correct it to match THIS
    specification exactly. The test asserts a one-way digest of the outputs over a
    fixed domain, so the expected outputs appear NOWHERE in the test file - this
    reference is the ONLY source of the concrete behavior. Read it fully before editing.
    
    Signature: checksum(n)
    Constants for THIS module: W1, W2, M = 3, 1, 97
    
    Specification:
        Weighted digit checksum of n modulo 97.
        Algorithm: read the base-10 digits of n from the RIGHT. Weight the rightmost digit
        by W1 = 3, the next by W2 = 1, then W1, W2, ... alternating. Sum weight*digit,
        then take % M with M = 97. checksum(0) is 0.
    
    Conformance ledger (each line restates an invariant the corrected function must
    satisfy over one input band; the property test samples across all bands):
      ledger[mod07:000] inputs with index congruent to 0 (mod 17) in band 0..5 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:001] inputs with index congruent to 1 (mod 17) in band 7..18 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:002] inputs with index congruent to 2 (mod 17) in band 14..31 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:003] inputs with index congruent to 3 (mod 17) in band 21..44 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:004] inputs with index congruent to 4 (mod 17) in band 28..57 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:005] inputs with index congruent to 5 (mod 17) in band 35..70 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:006] inputs with index congruent to 6 (mod 17) in band 42..83 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:007] inputs with index congruent to 7 (mod 17) in band 49..96 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:008] inputs with index congruent to 8 (mod 17) in band 56..12 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:009] inputs with index congruent to 9 (mod 17) in band 63..25 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:010] inputs with index congruent to 10 (mod 17) in band 70..38 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:011] inputs with index congruent to 11 (mod 17) in band 77..51 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:012] inputs with index congruent to 12 (mod 17) in band 84..64 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:013] inputs with index congruent to 13 (mod 17) in band 91..77 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:014] inputs with index congruent to 14 (mod 17) in band 1..90 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:015] inputs with index congruent to 15 (mod 17) in band 8..6 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:016] inputs with index congruent to 16 (mod 17) in band 15..19 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:017] inputs with index congruent to 0 (mod 17) in band 22..32 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:018] inputs with index congruent to 1 (mod 17) in band 29..45 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:019] inputs with index congruent to 2 (mod 17) in band 36..58 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:020] inputs with index congruent to 3 (mod 17) in band 43..71 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:021] inputs with index congruent to 4 (mod 17) in band 50..84 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:022] inputs with index congruent to 5 (mod 17) in band 57..0 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:023] inputs with index congruent to 6 (mod 17) in band 64..13 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:024] inputs with index congruent to 7 (mod 17) in band 71..26 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:025] inputs with index congruent to 8 (mod 17) in band 78..39 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:026] inputs with index congruent to 9 (mod 17) in band 85..52 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:027] inputs with index congruent to 10 (mod 17) in band 92..65 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:028] inputs with index congruent to 11 (mod 17) in band 2..78 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:029] inputs with index congruent to 12 (mod 17) in band 9..91 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:030] inputs with index congruent to 13 (mod 17) in band 16..7 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:031] inputs with index congruent to 14 (mod 17) in band 23..20 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:032] inputs with index congruent to 15 (mod 17) in band 30..33 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:033] inputs with index congruent to 16 (mod 17) in band 37..46 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:034] inputs with index congruent to 0 (mod 17) in band 44..59 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:035] inputs with index congruent to 1 (mod 17) in band 51..72 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:036] inputs with index congruent to 2 (mod 17) in band 58..85 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:037] inputs with index congruent to 3 (mod 17) in band 65..1 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:038] inputs with index congruent to 4 (mod 17) in band 72..14 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:039] inputs with index congruent to 5 (mod 17) in band 79..27 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:040] inputs with index congruent to 6 (mod 17) in band 86..40 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:041] inputs with index congruent to 7 (mod 17) in band 93..53 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:042] inputs with index congruent to 8 (mod 17) in band 3..66 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:043] inputs with index congruent to 9 (mod 17) in band 10..79 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:044] inputs with index congruent to 10 (mod 17) in band 17..92 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:045] inputs with index congruent to 11 (mod 17) in band 24..8 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:046] inputs with index congruent to 12 (mod 17) in band 31..21 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:047] inputs with index congruent to 13 (mod 17) in band 38..34 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:048] inputs with index congruent to 14 (mod 17) in band 45..47 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:049] inputs with index congruent to 15 (mod 17) in band 52..60 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:050] inputs with index congruent to 16 (mod 17) in band 59..73 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:051] inputs with index congruent to 0 (mod 17) in band 66..86 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:052] inputs with index congruent to 1 (mod 17) in band 73..2 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:053] inputs with index congruent to 2 (mod 17) in band 80..15 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:054] inputs with index congruent to 3 (mod 17) in band 87..28 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:055] inputs with index congruent to 4 (mod 17) in band 94..41 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:056] inputs with index congruent to 5 (mod 17) in band 4..54 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:057] inputs with index congruent to 6 (mod 17) in band 11..67 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:058] inputs with index congruent to 7 (mod 17) in band 18..80 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:059] inputs with index congruent to 8 (mod 17) in band 25..93 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:060] inputs with index congruent to 9 (mod 17) in band 32..9 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:061] inputs with index congruent to 10 (mod 17) in band 39..22 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:062] inputs with index congruent to 11 (mod 17) in band 46..35 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:063] inputs with index congruent to 12 (mod 17) in band 53..48 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:064] inputs with index congruent to 13 (mod 17) in band 60..61 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:065] inputs with index congruent to 14 (mod 17) in band 67..74 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:066] inputs with index congruent to 15 (mod 17) in band 74..87 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:067] inputs with index congruent to 16 (mod 17) in band 81..3 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:068] inputs with index congruent to 0 (mod 17) in band 88..16 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod07:069] inputs with index congruent to 1 (mod 17) in band 95..29 are fully determined by the Specification above; no special-casing, no clamping, no early return.
    """

def checksum(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    if n == 0:
        return 0 % 97
    t, i, s = n, 0, 0
    while t:
        d = t % 10
        w = 3   # BUG: weight never alternates to 1
        s = (s + w * d) % 97
        t //= 10
        i += 1
    return s
