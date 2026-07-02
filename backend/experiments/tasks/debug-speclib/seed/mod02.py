"""mod02 - single-function module.

    BEHAVIOR REFERENCE - module 'mod02' (function `caesar`)
    AUTHORITATIVE. The function body below is buggy; correct it to match THIS
    specification exactly. The test asserts a one-way digest of the outputs over a
    fixed domain, so the expected outputs appear NOWHERE in the test file - this
    reference is the ONLY source of the concrete behavior. Read it fully before editing.
    
    Signature: caesar(s)
    Constants for THIS module: K = 3
    
    Specification:
        Caesar-shift every lowercase letter a-z forward by 3, wrapping within a-z.
        Algorithm: for each char, if it is a-z map it to chr((ord(c) - 97 + 3) % 26 + 97);
        otherwise leave it unchanged. Shift amount K = 3. Length is preserved.
    
    Conformance ledger (each line restates an invariant the corrected function must
    satisfy over one input band; the property test samples across all bands):
      ledger[mod02:000] inputs with index congruent to 0 (mod 17) in band 0..5 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:001] inputs with index congruent to 1 (mod 17) in band 7..18 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:002] inputs with index congruent to 2 (mod 17) in band 14..31 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:003] inputs with index congruent to 3 (mod 17) in band 21..44 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:004] inputs with index congruent to 4 (mod 17) in band 28..57 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:005] inputs with index congruent to 5 (mod 17) in band 35..70 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:006] inputs with index congruent to 6 (mod 17) in band 42..83 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:007] inputs with index congruent to 7 (mod 17) in band 49..96 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:008] inputs with index congruent to 8 (mod 17) in band 56..12 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:009] inputs with index congruent to 9 (mod 17) in band 63..25 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:010] inputs with index congruent to 10 (mod 17) in band 70..38 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:011] inputs with index congruent to 11 (mod 17) in band 77..51 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:012] inputs with index congruent to 12 (mod 17) in band 84..64 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:013] inputs with index congruent to 13 (mod 17) in band 91..77 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:014] inputs with index congruent to 14 (mod 17) in band 1..90 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:015] inputs with index congruent to 15 (mod 17) in band 8..6 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:016] inputs with index congruent to 16 (mod 17) in band 15..19 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:017] inputs with index congruent to 0 (mod 17) in band 22..32 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:018] inputs with index congruent to 1 (mod 17) in band 29..45 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:019] inputs with index congruent to 2 (mod 17) in band 36..58 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:020] inputs with index congruent to 3 (mod 17) in band 43..71 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:021] inputs with index congruent to 4 (mod 17) in band 50..84 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:022] inputs with index congruent to 5 (mod 17) in band 57..0 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:023] inputs with index congruent to 6 (mod 17) in band 64..13 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:024] inputs with index congruent to 7 (mod 17) in band 71..26 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:025] inputs with index congruent to 8 (mod 17) in band 78..39 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:026] inputs with index congruent to 9 (mod 17) in band 85..52 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:027] inputs with index congruent to 10 (mod 17) in band 92..65 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:028] inputs with index congruent to 11 (mod 17) in band 2..78 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:029] inputs with index congruent to 12 (mod 17) in band 9..91 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:030] inputs with index congruent to 13 (mod 17) in band 16..7 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:031] inputs with index congruent to 14 (mod 17) in band 23..20 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:032] inputs with index congruent to 15 (mod 17) in band 30..33 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:033] inputs with index congruent to 16 (mod 17) in band 37..46 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:034] inputs with index congruent to 0 (mod 17) in band 44..59 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:035] inputs with index congruent to 1 (mod 17) in band 51..72 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:036] inputs with index congruent to 2 (mod 17) in band 58..85 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:037] inputs with index congruent to 3 (mod 17) in band 65..1 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:038] inputs with index congruent to 4 (mod 17) in band 72..14 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:039] inputs with index congruent to 5 (mod 17) in band 79..27 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:040] inputs with index congruent to 6 (mod 17) in band 86..40 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:041] inputs with index congruent to 7 (mod 17) in band 93..53 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:042] inputs with index congruent to 8 (mod 17) in band 3..66 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:043] inputs with index congruent to 9 (mod 17) in band 10..79 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:044] inputs with index congruent to 10 (mod 17) in band 17..92 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:045] inputs with index congruent to 11 (mod 17) in band 24..8 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:046] inputs with index congruent to 12 (mod 17) in band 31..21 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:047] inputs with index congruent to 13 (mod 17) in band 38..34 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:048] inputs with index congruent to 14 (mod 17) in band 45..47 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:049] inputs with index congruent to 15 (mod 17) in band 52..60 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:050] inputs with index congruent to 16 (mod 17) in band 59..73 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:051] inputs with index congruent to 0 (mod 17) in band 66..86 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:052] inputs with index congruent to 1 (mod 17) in band 73..2 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:053] inputs with index congruent to 2 (mod 17) in band 80..15 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:054] inputs with index congruent to 3 (mod 17) in band 87..28 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:055] inputs with index congruent to 4 (mod 17) in band 94..41 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:056] inputs with index congruent to 5 (mod 17) in band 4..54 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:057] inputs with index congruent to 6 (mod 17) in band 11..67 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:058] inputs with index congruent to 7 (mod 17) in band 18..80 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:059] inputs with index congruent to 8 (mod 17) in band 25..93 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:060] inputs with index congruent to 9 (mod 17) in band 32..9 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:061] inputs with index congruent to 10 (mod 17) in band 39..22 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:062] inputs with index congruent to 11 (mod 17) in band 46..35 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:063] inputs with index congruent to 12 (mod 17) in band 53..48 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:064] inputs with index congruent to 13 (mod 17) in band 60..61 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:065] inputs with index congruent to 14 (mod 17) in band 67..74 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:066] inputs with index congruent to 15 (mod 17) in band 74..87 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:067] inputs with index congruent to 16 (mod 17) in band 81..3 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:068] inputs with index congruent to 0 (mod 17) in band 88..16 are fully determined by the Specification above; no special-casing, no clamping, no early return.
      ledger[mod02:069] inputs with index congruent to 1 (mod 17) in band 95..29 are fully determined by the Specification above; no special-casing, no clamping, no early return.
    """

def caesar(s):
    """See the BEHAVIOR REFERENCE at the top of this module."""
    return "".join(
        chr(ord(c) + 3) if "a" <= c <= "z" else c for c in s   # BUG: no wrap mod 26
    )
