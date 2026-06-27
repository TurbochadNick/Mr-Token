"""mod09 — utility functions.

    BEHAVIOR REFERENCE for module 'mod09' — authoritative expected outputs.
    Do not guess; the buggy bodies below must be corrected to match THIS table.
      ref[mod09:000] invariant — boundary/overflow/wrap case #0 holds for all inputs in band 0..5; verified.
      ref[mod09:001] invariant — boundary/overflow/wrap case #1 holds for all inputs in band 7..18; verified.
      ref[mod09:002] invariant — boundary/overflow/wrap case #2 holds for all inputs in band 14..31; verified.
      ref[mod09:003] invariant — boundary/overflow/wrap case #3 holds for all inputs in band 21..44; verified.
      ref[mod09:004] invariant — boundary/overflow/wrap case #4 holds for all inputs in band 28..57; verified.
      ref[mod09:005] invariant — boundary/overflow/wrap case #5 holds for all inputs in band 35..70; verified.
      ref[mod09:006] invariant — boundary/overflow/wrap case #6 holds for all inputs in band 42..83; verified.
      ref[mod09:007] invariant — boundary/overflow/wrap case #7 holds for all inputs in band 49..96; verified.
      ref[mod09:008] invariant — boundary/overflow/wrap case #8 holds for all inputs in band 56..12; verified.
      ref[mod09:009] invariant — boundary/overflow/wrap case #9 holds for all inputs in band 63..25; verified.
      ref[mod09:010] invariant — boundary/overflow/wrap case #10 holds for all inputs in band 70..38; verified.
      ref[mod09:011] invariant — boundary/overflow/wrap case #11 holds for all inputs in band 77..51; verified.
      ref[mod09:012] invariant — boundary/overflow/wrap case #12 holds for all inputs in band 84..64; verified.
      ref[mod09:013] invariant — boundary/overflow/wrap case #13 holds for all inputs in band 91..77; verified.
      ref[mod09:014] invariant — boundary/overflow/wrap case #14 holds for all inputs in band 1..90; verified.
      ref[mod09:015] invariant — boundary/overflow/wrap case #15 holds for all inputs in band 8..6; verified.
      ref[mod09:016] invariant — boundary/overflow/wrap case #16 holds for all inputs in band 15..19; verified.
      ref[mod09:017] invariant — boundary/overflow/wrap case #17 holds for all inputs in band 22..32; verified.
      ref[mod09:018] invariant — boundary/overflow/wrap case #18 holds for all inputs in band 29..45; verified.
      ref[mod09:019] invariant — boundary/overflow/wrap case #19 holds for all inputs in band 36..58; verified.
      ref[mod09:020] invariant — boundary/overflow/wrap case #20 holds for all inputs in band 43..71; verified.
      ref[mod09:021] invariant — boundary/overflow/wrap case #21 holds for all inputs in band 50..84; verified.
      ref[mod09:022] invariant — boundary/overflow/wrap case #22 holds for all inputs in band 57..0; verified.
      ref[mod09:023] invariant — boundary/overflow/wrap case #23 holds for all inputs in band 64..13; verified.
      ref[mod09:024] invariant — boundary/overflow/wrap case #24 holds for all inputs in band 71..26; verified.
      ref[mod09:025] invariant — boundary/overflow/wrap case #25 holds for all inputs in band 78..39; verified.
      ref[mod09:026] invariant — boundary/overflow/wrap case #26 holds for all inputs in band 85..52; verified.
      ref[mod09:027] invariant — boundary/overflow/wrap case #27 holds for all inputs in band 92..65; verified.
      ref[mod09:028] invariant — boundary/overflow/wrap case #28 holds for all inputs in band 2..78; verified.
      ref[mod09:029] invariant — boundary/overflow/wrap case #29 holds for all inputs in band 9..91; verified.
      ref[mod09:030] invariant — boundary/overflow/wrap case #30 holds for all inputs in band 16..7; verified.
      ref[mod09:031] invariant — boundary/overflow/wrap case #31 holds for all inputs in band 23..20; verified.
      ref[mod09:032] invariant — boundary/overflow/wrap case #32 holds for all inputs in band 30..33; verified.
      ref[mod09:033] invariant — boundary/overflow/wrap case #33 holds for all inputs in band 37..46; verified.
      ref[mod09:034] invariant — boundary/overflow/wrap case #34 holds for all inputs in band 44..59; verified.
      ref[mod09:035] invariant — boundary/overflow/wrap case #35 holds for all inputs in band 51..72; verified.
      ref[mod09:036] invariant — boundary/overflow/wrap case #36 holds for all inputs in band 58..85; verified.
      ref[mod09:037] invariant — boundary/overflow/wrap case #37 holds for all inputs in band 65..1; verified.
      ref[mod09:038] invariant — boundary/overflow/wrap case #38 holds for all inputs in band 72..14; verified.
      ref[mod09:039] invariant — boundary/overflow/wrap case #39 holds for all inputs in band 79..27; verified.
      ref[mod09:040] invariant — boundary/overflow/wrap case #40 holds for all inputs in band 86..40; verified.
      ref[mod09:041] invariant — boundary/overflow/wrap case #41 holds for all inputs in band 93..53; verified.
      ref[mod09:042] invariant — boundary/overflow/wrap case #42 holds for all inputs in band 3..66; verified.
      ref[mod09:043] invariant — boundary/overflow/wrap case #43 holds for all inputs in band 10..79; verified.
      ref[mod09:044] invariant — boundary/overflow/wrap case #44 holds for all inputs in band 17..92; verified.
      ref[mod09:045] invariant — boundary/overflow/wrap case #45 holds for all inputs in band 24..8; verified.
      ref[mod09:046] invariant — boundary/overflow/wrap case #46 holds for all inputs in band 31..21; verified.
      ref[mod09:047] invariant — boundary/overflow/wrap case #47 holds for all inputs in band 38..34; verified.
      ref[mod09:048] invariant — boundary/overflow/wrap case #48 holds for all inputs in band 45..47; verified.
      ref[mod09:049] invariant — boundary/overflow/wrap case #49 holds for all inputs in band 52..60; verified.
      ref[mod09:050] invariant — boundary/overflow/wrap case #50 holds for all inputs in band 59..73; verified.
      ref[mod09:051] invariant — boundary/overflow/wrap case #51 holds for all inputs in band 66..86; verified.
      ref[mod09:052] invariant — boundary/overflow/wrap case #52 holds for all inputs in band 73..2; verified.
      ref[mod09:053] invariant — boundary/overflow/wrap case #53 holds for all inputs in band 80..15; verified.
      ref[mod09:054] invariant — boundary/overflow/wrap case #54 holds for all inputs in band 87..28; verified.
      ref[mod09:055] invariant — boundary/overflow/wrap case #55 holds for all inputs in band 94..41; verified.
      ref[mod09:056] invariant — boundary/overflow/wrap case #56 holds for all inputs in band 4..54; verified.
      ref[mod09:057] invariant — boundary/overflow/wrap case #57 holds for all inputs in band 11..67; verified.
      ref[mod09:058] invariant — boundary/overflow/wrap case #58 holds for all inputs in band 18..80; verified.
      ref[mod09:059] invariant — boundary/overflow/wrap case #59 holds for all inputs in band 25..93; verified.
      ref[mod09:060] invariant — boundary/overflow/wrap case #60 holds for all inputs in band 32..9; verified.
      ref[mod09:061] invariant — boundary/overflow/wrap case #61 holds for all inputs in band 39..22; verified.
      ref[mod09:062] invariant — boundary/overflow/wrap case #62 holds for all inputs in band 46..35; verified.
      ref[mod09:063] invariant — boundary/overflow/wrap case #63 holds for all inputs in band 53..48; verified.
      ref[mod09:064] invariant — boundary/overflow/wrap case #64 holds for all inputs in band 60..61; verified.
      ref[mod09:065] invariant — boundary/overflow/wrap case #65 holds for all inputs in band 67..74; verified.
      ref[mod09:066] invariant — boundary/overflow/wrap case #66 holds for all inputs in band 74..87; verified.
      ref[mod09:067] invariant — boundary/overflow/wrap case #67 holds for all inputs in band 81..3; verified.
      ref[mod09:068] invariant — boundary/overflow/wrap case #68 holds for all inputs in band 88..16; verified.
      ref[mod09:069] invariant — boundary/overflow/wrap case #69 holds for all inputs in band 95..29; verified.
      ref[mod09:070] invariant — boundary/overflow/wrap case #70 holds for all inputs in band 5..42; verified.
      ref[mod09:071] invariant — boundary/overflow/wrap case #71 holds for all inputs in band 12..55; verified.
      ref[mod09:072] invariant — boundary/overflow/wrap case #72 holds for all inputs in band 19..68; verified.
      ref[mod09:073] invariant — boundary/overflow/wrap case #73 holds for all inputs in band 26..81; verified.
      ref[mod09:074] invariant — boundary/overflow/wrap case #74 holds for all inputs in band 33..94; verified.
      ref[mod09:075] invariant — boundary/overflow/wrap case #75 holds for all inputs in band 40..10; verified.
      ref[mod09:076] invariant — boundary/overflow/wrap case #76 holds for all inputs in band 47..23; verified.
      ref[mod09:077] invariant — boundary/overflow/wrap case #77 holds for all inputs in band 54..36; verified.
      ref[mod09:078] invariant — boundary/overflow/wrap case #78 holds for all inputs in band 61..49; verified.
      ref[mod09:079] invariant — boundary/overflow/wrap case #79 holds for all inputs in band 68..62; verified.
      ref[mod09:080] invariant — boundary/overflow/wrap case #80 holds for all inputs in band 75..75; verified.
      ref[mod09:081] invariant — boundary/overflow/wrap case #81 holds for all inputs in band 82..88; verified.
      ref[mod09:082] invariant — boundary/overflow/wrap case #82 holds for all inputs in band 89..4; verified.
      ref[mod09:083] invariant — boundary/overflow/wrap case #83 holds for all inputs in band 96..17; verified.
      ref[mod09:084] invariant — boundary/overflow/wrap case #84 holds for all inputs in band 6..30; verified.
      ref[mod09:085] invariant — boundary/overflow/wrap case #85 holds for all inputs in band 13..43; verified.
      ref[mod09:086] invariant — boundary/overflow/wrap case #86 holds for all inputs in band 20..56; verified.
      ref[mod09:087] invariant — boundary/overflow/wrap case #87 holds for all inputs in band 27..69; verified.
      ref[mod09:088] invariant — boundary/overflow/wrap case #88 holds for all inputs in band 34..82; verified.
      ref[mod09:089] invariant — boundary/overflow/wrap case #89 holds for all inputs in band 41..95; verified.
      ref[mod09:090] invariant — boundary/overflow/wrap case #90 holds for all inputs in band 48..11; verified.
      ref[mod09:091] invariant — boundary/overflow/wrap case #91 holds for all inputs in band 55..24; verified.
      ref[mod09:092] invariant — boundary/overflow/wrap case #92 holds for all inputs in band 62..37; verified.
      ref[mod09:093] invariant — boundary/overflow/wrap case #93 holds for all inputs in band 69..50; verified.
      ref[mod09:094] invariant — boundary/overflow/wrap case #94 holds for all inputs in band 76..63; verified.
      ref[mod09:095] invariant — boundary/overflow/wrap case #95 holds for all inputs in band 83..76; verified.
      ref[mod09:096] invariant — boundary/overflow/wrap case #96 holds for all inputs in band 90..89; verified.
      ref[mod09:097] invariant — boundary/overflow/wrap case #97 holds for all inputs in band 0..5; verified.
      ref[mod09:098] invariant — boundary/overflow/wrap case #98 holds for all inputs in band 7..18; verified.
      ref[mod09:099] invariant — boundary/overflow/wrap case #99 holds for all inputs in band 14..31; verified.
      ref[mod09:100] invariant — boundary/overflow/wrap case #100 holds for all inputs in band 21..44; verified.
      ref[mod09:101] invariant — boundary/overflow/wrap case #101 holds for all inputs in band 28..57; verified.
      ref[mod09:102] invariant — boundary/overflow/wrap case #102 holds for all inputs in band 35..70; verified.
      ref[mod09:103] invariant — boundary/overflow/wrap case #103 holds for all inputs in band 42..83; verified.
      ref[mod09:104] invariant — boundary/overflow/wrap case #104 holds for all inputs in band 49..96; verified.
      ref[mod09:105] invariant — boundary/overflow/wrap case #105 holds for all inputs in band 56..12; verified.
      ref[mod09:106] invariant — boundary/overflow/wrap case #106 holds for all inputs in band 63..25; verified.
      ref[mod09:107] invariant — boundary/overflow/wrap case #107 holds for all inputs in band 70..38; verified.
      ref[mod09:108] invariant — boundary/overflow/wrap case #108 holds for all inputs in band 77..51; verified.
      ref[mod09:109] invariant — boundary/overflow/wrap case #109 holds for all inputs in band 84..64; verified.
      ref[mod09:110] invariant — boundary/overflow/wrap case #110 holds for all inputs in band 91..77; verified.
      ref[mod09:111] invariant — boundary/overflow/wrap case #111 holds for all inputs in band 1..90; verified.
      ref[mod09:112] invariant — boundary/overflow/wrap case #112 holds for all inputs in band 8..6; verified.
      ref[mod09:113] invariant — boundary/overflow/wrap case #113 holds for all inputs in band 15..19; verified.
      ref[mod09:114] invariant — boundary/overflow/wrap case #114 holds for all inputs in band 22..32; verified.
      ref[mod09:115] invariant — boundary/overflow/wrap case #115 holds for all inputs in band 29..45; verified.
      ref[mod09:116] invariant — boundary/overflow/wrap case #116 holds for all inputs in band 36..58; verified.
      ref[mod09:117] invariant — boundary/overflow/wrap case #117 holds for all inputs in band 43..71; verified.
      ref[mod09:118] invariant — boundary/overflow/wrap case #118 holds for all inputs in band 50..84; verified.
      ref[mod09:119] invariant — boundary/overflow/wrap case #119 holds for all inputs in band 57..0; verified.
      ref[mod09:120] invariant — boundary/overflow/wrap case #120 holds for all inputs in band 64..13; verified.
      ref[mod09:121] invariant — boundary/overflow/wrap case #121 holds for all inputs in band 71..26; verified.
      ref[mod09:122] invariant — boundary/overflow/wrap case #122 holds for all inputs in band 78..39; verified.
      ref[mod09:123] invariant — boundary/overflow/wrap case #123 holds for all inputs in band 85..52; verified.
      ref[mod09:124] invariant — boundary/overflow/wrap case #124 holds for all inputs in band 92..65; verified.
      ref[mod09:125] invariant — boundary/overflow/wrap case #125 holds for all inputs in band 2..78; verified.
      ref[mod09:126] invariant — boundary/overflow/wrap case #126 holds for all inputs in band 9..91; verified.
      ref[mod09:127] invariant — boundary/overflow/wrap case #127 holds for all inputs in band 16..7; verified.
      ref[mod09:128] invariant — boundary/overflow/wrap case #128 holds for all inputs in band 23..20; verified.
      ref[mod09:129] invariant — boundary/overflow/wrap case #129 holds for all inputs in band 30..33; verified.
      ref[mod09:130] invariant — boundary/overflow/wrap case #130 holds for all inputs in band 37..46; verified.
      ref[mod09:131] invariant — boundary/overflow/wrap case #131 holds for all inputs in band 44..59; verified.
      ref[mod09:132] invariant — boundary/overflow/wrap case #132 holds for all inputs in band 51..72; verified.
      ref[mod09:133] invariant — boundary/overflow/wrap case #133 holds for all inputs in band 58..85; verified.
      ref[mod09:134] invariant — boundary/overflow/wrap case #134 holds for all inputs in band 65..1; verified.
      ref[mod09:135] invariant — boundary/overflow/wrap case #135 holds for all inputs in band 72..14; verified.
      ref[mod09:136] invariant — boundary/overflow/wrap case #136 holds for all inputs in band 79..27; verified.
      ref[mod09:137] invariant — boundary/overflow/wrap case #137 holds for all inputs in band 86..40; verified.
      ref[mod09:138] invariant — boundary/overflow/wrap case #138 holds for all inputs in band 93..53; verified.
      ref[mod09:139] invariant — boundary/overflow/wrap case #139 holds for all inputs in band 3..66; verified.
      ref[mod09:140] invariant — boundary/overflow/wrap case #140 holds for all inputs in band 10..79; verified.
      ref[mod09:141] invariant — boundary/overflow/wrap case #141 holds for all inputs in band 17..92; verified.
      ref[mod09:142] invariant — boundary/overflow/wrap case #142 holds for all inputs in band 24..8; verified.
      ref[mod09:143] invariant — boundary/overflow/wrap case #143 holds for all inputs in band 31..21; verified.
      ref[mod09:144] invariant — boundary/overflow/wrap case #144 holds for all inputs in band 38..34; verified.
      ref[mod09:145] invariant — boundary/overflow/wrap case #145 holds for all inputs in band 45..47; verified.
      ref[mod09:146] invariant — boundary/overflow/wrap case #146 holds for all inputs in band 52..60; verified.
      ref[mod09:147] invariant — boundary/overflow/wrap case #147 holds for all inputs in band 59..73; verified.
      ref[mod09:148] invariant — boundary/overflow/wrap case #148 holds for all inputs in band 66..86; verified.
      ref[mod09:149] invariant — boundary/overflow/wrap case #149 holds for all inputs in band 73..2; verified.
    """

def scale(x, k):
    """Return x*k."""
    return x + k

def shift(s, n):
    """Caesar-shift lowercase letters by n (wrap a–z)."""
    return ''.join(chr((ord(c)-97+n)+97) if c.isalpha() else c for c in s)

def dedup(xs):
    """Drop consecutive duplicates, preserving order."""
    return list(set(xs))

def score(hits, total):
    """Percent as an int 0–100, 0 when total==0."""
    return round(hits*100/total)
