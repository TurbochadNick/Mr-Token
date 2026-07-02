"""mod19 - single-function module.

    BEHAVIOR REFERENCE - module 'mod19' (function `poly`)
    AUTHORITATIVE. The function body below is buggy; correct it to match THIS
    specification exactly. The test asserts a one-way digest of the outputs over a
    fixed domain, so the expected outputs appear NOWHERE in the test file - this
    reference is the ONLY source of the concrete behavior. Read it fully before editing.
    
    Signature: poly(n)
    Constants for THIS module: C, D, M = 5, 2, 103
    
    Specification:
        Evaluate a cubic polynomial modulo 103.
        Algorithm: return (n**3 + C*n + D) % M with C = 5, D = 2, M = 103.
        The leading term is n CUBED (n*n*n), not squared.
    
    Conformance ledger (each line restates an invariant the corrected function must
    satisfy over one input band; the property test samples across all bands):
      ledger[mod19:000] inputs with index congruent to 0 (mod 17) in band 0..5 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:001] inputs with index congruent to 1 (mod 17) in band 7..18 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:002] inputs with index congruent to 2 (mod 17) in band 14..31 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:003] inputs with index congruent to 3 (mod 17) in band 21..44 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:004] inputs with index congruent to 4 (mod 17) in band 28..57 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:005] inputs with index congruent to 5 (mod 17) in band 35..70 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:006] inputs with index congruent to 6 (mod 17) in band 42..83 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:007] inputs with index congruent to 7 (mod 17) in band 49..96 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:008] inputs with index congruent to 8 (mod 17) in band 56..12 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:009] inputs with index congruent to 9 (mod 17) in band 63..25 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:010] inputs with index congruent to 10 (mod 17) in band 70..38 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:011] inputs with index congruent to 11 (mod 17) in band 77..51 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:012] inputs with index congruent to 12 (mod 17) in band 84..64 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:013] inputs with index congruent to 13 (mod 17) in band 91..77 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:014] inputs with index congruent to 14 (mod 17) in band 1..90 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:015] inputs with index congruent to 15 (mod 17) in band 8..6 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:016] inputs with index congruent to 16 (mod 17) in band 15..19 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:017] inputs with index congruent to 0 (mod 17) in band 22..32 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:018] inputs with index congruent to 1 (mod 17) in band 29..45 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:019] inputs with index congruent to 2 (mod 17) in band 36..58 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:020] inputs with index congruent to 3 (mod 17) in band 43..71 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:021] inputs with index congruent to 4 (mod 17) in band 50..84 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:022] inputs with index congruent to 5 (mod 17) in band 57..0 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:023] inputs with index congruent to 6 (mod 17) in band 64..13 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:024] inputs with index congruent to 7 (mod 17) in band 71..26 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:025] inputs with index congruent to 8 (mod 17) in band 78..39 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:026] inputs with index congruent to 9 (mod 17) in band 85..52 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:027] inputs with index congruent to 10 (mod 17) in band 92..65 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:028] inputs with index congruent to 11 (mod 17) in band 2..78 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:029] inputs with index congruent to 12 (mod 17) in band 9..91 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:030] inputs with index congruent to 13 (mod 17) in band 16..7 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:031] inputs with index congruent to 14 (mod 17) in band 23..20 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:032] inputs with index congruent to 15 (mod 17) in band 30..33 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:033] inputs with index congruent to 16 (mod 17) in band 37..46 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:034] inputs with index congruent to 0 (mod 17) in band 44..59 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:035] inputs with index congruent to 1 (mod 17) in band 51..72 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:036] inputs with index congruent to 2 (mod 17) in band 58..85 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:037] inputs with index congruent to 3 (mod 17) in band 65..1 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:038] inputs with index congruent to 4 (mod 17) in band 72..14 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:039] inputs with index congruent to 5 (mod 17) in band 79..27 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:040] inputs with index congruent to 6 (mod 17) in band 86..40 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:041] inputs with index congruent to 7 (mod 17) in band 93..53 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:042] inputs with index congruent to 8 (mod 17) in band 3..66 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:043] inputs with index congruent to 9 (mod 17) in band 10..79 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:044] inputs with index congruent to 10 (mod 17) in band 17..92 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:045] inputs with index congruent to 11 (mod 17) in band 24..8 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:046] inputs with index congruent to 12 (mod 17) in band 31..21 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:047] inputs with index congruent to 13 (mod 17) in band 38..34 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:048] inputs with index congruent to 14 (mod 17) in band 45..47 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:049] inputs with index congruent to 15 (mod 17) in band 52..60 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:050] inputs with index congruent to 16 (mod 17) in band 59..73 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:051] inputs with index congruent to 0 (mod 17) in band 66..86 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:052] inputs with index congruent to 1 (mod 17) in band 73..2 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:053] inputs with index congruent to 2 (mod 17) in band 80..15 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:054] inputs with index congruent to 3 (mod 17) in band 87..28 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:055] inputs with index congruent to 4 (mod 17) in band 94..41 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:056] inputs with index congruent to 5 (mod 17) in band 4..54 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:057] inputs with index congruent to 6 (mod 17) in band 11..67 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:058] inputs with index congruent to 7 (mod 17) in band 18..80 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:059] inputs with index congruent to 8 (mod 17) in band 25..93 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:060] inputs with index congruent to 9 (mod 17) in band 32..9 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:061] inputs with index congruent to 10 (mod 17) in band 39..22 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:062] inputs with index congruent to 11 (mod 17) in band 46..35 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:063] inputs with index congruent to 12 (mod 17) in band 53..48 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:064] inputs with index congruent to 13 (mod 17) in band 60..61 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:065] inputs with index congruent to 14 (mod 17) in band 67..74 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:066] inputs with index congruent to 15 (mod 17) in band 74..87 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:067] inputs with index congruent to 16 (mod 17) in band 81..3 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:068] inputs with index congruent to 0 (mod 17) in band 88..16 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod19:069] inputs with index congruent to 1 (mod 17) in band 95..29 are fully determined by the Specification above; no special-casing, no clamping, no early return.
    """

def poly(n):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return ((n * n) + (5 * n) + 2) % 103   # BUG: n**2, spec says n**3
