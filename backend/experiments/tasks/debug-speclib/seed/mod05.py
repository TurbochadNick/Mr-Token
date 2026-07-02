"""mod05 - single-function module.

    BEHAVIOR REFERENCE - module 'mod05' (function `rollhash`)
    AUTHORITATIVE. The function body below is buggy; correct it to match THIS
    specification exactly. The test asserts a one-way digest of the outputs over a
    fixed domain, so the expected outputs appear NOWHERE in the test file - this
    reference is the ONLY source of the concrete behavior. Read it fully before editing.
    
    Signature: rollhash(s)
    Constants for THIS module: P, M = 31, 1009
    
    Specification:
        Polynomial rolling hash of the string s modulo 1009.
        Algorithm: h = (sum over positions i of ord(s[i]) * P**i) % M, where the exponent
        is the 0-based index i (the first char uses P**0). P = 31, M = 1009.
        Empty string hashes to 0.
    
    Conformance ledger (each line restates an invariant the corrected function must
    satisfy over one input band; the property test samples across all bands):
      ledger[mod05:000] inputs with index congruent to 0 (mod 17) in band 0..5 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:001] inputs with index congruent to 1 (mod 17) in band 7..18 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:002] inputs with index congruent to 2 (mod 17) in band 14..31 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:003] inputs with index congruent to 3 (mod 17) in band 21..44 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:004] inputs with index congruent to 4 (mod 17) in band 28..57 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:005] inputs with index congruent to 5 (mod 17) in band 35..70 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:006] inputs with index congruent to 6 (mod 17) in band 42..83 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:007] inputs with index congruent to 7 (mod 17) in band 49..96 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:008] inputs with index congruent to 8 (mod 17) in band 56..12 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:009] inputs with index congruent to 9 (mod 17) in band 63..25 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:010] inputs with index congruent to 10 (mod 17) in band 70..38 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:011] inputs with index congruent to 11 (mod 17) in band 77..51 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:012] inputs with index congruent to 12 (mod 17) in band 84..64 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:013] inputs with index congruent to 13 (mod 17) in band 91..77 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:014] inputs with index congruent to 14 (mod 17) in band 1..90 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:015] inputs with index congruent to 15 (mod 17) in band 8..6 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:016] inputs with index congruent to 16 (mod 17) in band 15..19 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:017] inputs with index congruent to 0 (mod 17) in band 22..32 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:018] inputs with index congruent to 1 (mod 17) in band 29..45 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:019] inputs with index congruent to 2 (mod 17) in band 36..58 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:020] inputs with index congruent to 3 (mod 17) in band 43..71 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:021] inputs with index congruent to 4 (mod 17) in band 50..84 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:022] inputs with index congruent to 5 (mod 17) in band 57..0 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:023] inputs with index congruent to 6 (mod 17) in band 64..13 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:024] inputs with index congruent to 7 (mod 17) in band 71..26 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:025] inputs with index congruent to 8 (mod 17) in band 78..39 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:026] inputs with index congruent to 9 (mod 17) in band 85..52 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:027] inputs with index congruent to 10 (mod 17) in band 92..65 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:028] inputs with index congruent to 11 (mod 17) in band 2..78 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:029] inputs with index congruent to 12 (mod 17) in band 9..91 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:030] inputs with index congruent to 13 (mod 17) in band 16..7 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:031] inputs with index congruent to 14 (mod 17) in band 23..20 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:032] inputs with index congruent to 15 (mod 17) in band 30..33 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:033] inputs with index congruent to 16 (mod 17) in band 37..46 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:034] inputs with index congruent to 0 (mod 17) in band 44..59 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:035] inputs with index congruent to 1 (mod 17) in band 51..72 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:036] inputs with index congruent to 2 (mod 17) in band 58..85 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:037] inputs with index congruent to 3 (mod 17) in band 65..1 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:038] inputs with index congruent to 4 (mod 17) in band 72..14 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:039] inputs with index congruent to 5 (mod 17) in band 79..27 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:040] inputs with index congruent to 6 (mod 17) in band 86..40 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:041] inputs with index congruent to 7 (mod 17) in band 93..53 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:042] inputs with index congruent to 8 (mod 17) in band 3..66 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:043] inputs with index congruent to 9 (mod 17) in band 10..79 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:044] inputs with index congruent to 10 (mod 17) in band 17..92 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:045] inputs with index congruent to 11 (mod 17) in band 24..8 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:046] inputs with index congruent to 12 (mod 17) in band 31..21 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:047] inputs with index congruent to 13 (mod 17) in band 38..34 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:048] inputs with index congruent to 14 (mod 17) in band 45..47 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:049] inputs with index congruent to 15 (mod 17) in band 52..60 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:050] inputs with index congruent to 16 (mod 17) in band 59..73 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:051] inputs with index congruent to 0 (mod 17) in band 66..86 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:052] inputs with index congruent to 1 (mod 17) in band 73..2 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:053] inputs with index congruent to 2 (mod 17) in band 80..15 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:054] inputs with index congruent to 3 (mod 17) in band 87..28 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:055] inputs with index congruent to 4 (mod 17) in band 94..41 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:056] inputs with index congruent to 5 (mod 17) in band 4..54 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:057] inputs with index congruent to 6 (mod 17) in band 11..67 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:058] inputs with index congruent to 7 (mod 17) in band 18..80 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:059] inputs with index congruent to 8 (mod 17) in band 25..93 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:060] inputs with index congruent to 9 (mod 17) in band 32..9 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:061] inputs with index congruent to 10 (mod 17) in band 39..22 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:062] inputs with index congruent to 11 (mod 17) in band 46..35 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:063] inputs with index congruent to 12 (mod 17) in band 53..48 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:064] inputs with index congruent to 13 (mod 17) in band 60..61 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:065] inputs with index congruent to 14 (mod 17) in band 67..74 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:066] inputs with index congruent to 15 (mod 17) in band 74..87 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:067] inputs with index congruent to 16 (mod 17) in band 81..3 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:068] inputs with index congruent to 0 (mod 17) in band 88..16 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod05:069] inputs with index congruent to 1 (mod 17) in band 95..29 are fully determined by the Specification above; no special-casing, no clamping, no early return.
    """

def rollhash(s):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    h = 0
    for i, c in enumerate(s):
        h = (h + ord(c) * pow(31, len(s) - i)) % 1009   # BUG: exponent is i, not len(s)-i
    return h
