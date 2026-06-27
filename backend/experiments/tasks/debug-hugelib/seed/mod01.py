"""mod01 — utility functions.

    BEHAVIOR REFERENCE for module 'mod01' — authoritative expected outputs.
    Do not guess; the buggy bodies below must be corrected to match THIS table.
      ref[mod01:000] invariant — boundary/overflow/wrap case #0 holds for all inputs in band 0..5; verified.
      ref[mod01:001] invariant — boundary/overflow/wrap case #1 holds for all inputs in band 7..18; verified.
      ref[mod01:002] invariant — boundary/overflow/wrap case #2 holds for all inputs in band 14..31; verified.
      ref[mod01:003] invariant — boundary/overflow/wrap case #3 holds for all inputs in band 21..44; verified.
      ref[mod01:004] invariant — boundary/overflow/wrap case #4 holds for all inputs in band 28..57; verified.
      ref[mod01:005] invariant — boundary/overflow/wrap case #5 holds for all inputs in band 35..70; verified.
      ref[mod01:006] invariant — boundary/overflow/wrap case #6 holds for all inputs in band 42..83; verified.
      ref[mod01:007] invariant — boundary/overflow/wrap case #7 holds for all inputs in band 49..96; verified.
      ref[mod01:008] invariant — boundary/overflow/wrap case #8 holds for all inputs in band 56..12; verified.
      ref[mod01:009] invariant — boundary/overflow/wrap case #9 holds for all inputs in band 63..25; verified.
      ref[mod01:010] invariant — boundary/overflow/wrap case #10 holds for all inputs in band 70..38; verified.
      ref[mod01:011] invariant — boundary/overflow/wrap case #11 holds for all inputs in band 77..51; verified.
      ref[mod01:012] invariant — boundary/overflow/wrap case #12 holds for all inputs in band 84..64; verified.
      ref[mod01:013] invariant — boundary/overflow/wrap case #13 holds for all inputs in band 91..77; verified.
      ref[mod01:014] invariant — boundary/overflow/wrap case #14 holds for all inputs in band 1..90; verified.
      ref[mod01:015] invariant — boundary/overflow/wrap case #15 holds for all inputs in band 8..6; verified.
      ref[mod01:016] invariant — boundary/overflow/wrap case #16 holds for all inputs in band 15..19; verified.
      ref[mod01:017] invariant — boundary/overflow/wrap case #17 holds for all inputs in band 22..32; verified.
      ref[mod01:018] invariant — boundary/overflow/wrap case #18 holds for all inputs in band 29..45; verified.
      ref[mod01:019] invariant — boundary/overflow/wrap case #19 holds for all inputs in band 36..58; verified.
      ref[mod01:020] invariant — boundary/overflow/wrap case #20 holds for all inputs in band 43..71; verified.
      ref[mod01:021] invariant — boundary/overflow/wrap case #21 holds for all inputs in band 50..84; verified.
      ref[mod01:022] invariant — boundary/overflow/wrap case #22 holds for all inputs in band 57..0; verified.
      ref[mod01:023] invariant — boundary/overflow/wrap case #23 holds for all inputs in band 64..13; verified.
      ref[mod01:024] invariant — boundary/overflow/wrap case #24 holds for all inputs in band 71..26; verified.
      ref[mod01:025] invariant — boundary/overflow/wrap case #25 holds for all inputs in band 78..39; verified.
      ref[mod01:026] invariant — boundary/overflow/wrap case #26 holds for all inputs in band 85..52; verified.
      ref[mod01:027] invariant — boundary/overflow/wrap case #27 holds for all inputs in band 92..65; verified.
      ref[mod01:028] invariant — boundary/overflow/wrap case #28 holds for all inputs in band 2..78; verified.
      ref[mod01:029] invariant — boundary/overflow/wrap case #29 holds for all inputs in band 9..91; verified.
      ref[mod01:030] invariant — boundary/overflow/wrap case #30 holds for all inputs in band 16..7; verified.
      ref[mod01:031] invariant — boundary/overflow/wrap case #31 holds for all inputs in band 23..20; verified.
      ref[mod01:032] invariant — boundary/overflow/wrap case #32 holds for all inputs in band 30..33; verified.
      ref[mod01:033] invariant — boundary/overflow/wrap case #33 holds for all inputs in band 37..46; verified.
      ref[mod01:034] invariant — boundary/overflow/wrap case #34 holds for all inputs in band 44..59; verified.
      ref[mod01:035] invariant — boundary/overflow/wrap case #35 holds for all inputs in band 51..72; verified.
      ref[mod01:036] invariant — boundary/overflow/wrap case #36 holds for all inputs in band 58..85; verified.
      ref[mod01:037] invariant — boundary/overflow/wrap case #37 holds for all inputs in band 65..1; verified.
      ref[mod01:038] invariant — boundary/overflow/wrap case #38 holds for all inputs in band 72..14; verified.
      ref[mod01:039] invariant — boundary/overflow/wrap case #39 holds for all inputs in band 79..27; verified.
      ref[mod01:040] invariant — boundary/overflow/wrap case #40 holds for all inputs in band 86..40; verified.
      ref[mod01:041] invariant — boundary/overflow/wrap case #41 holds for all inputs in band 93..53; verified.
      ref[mod01:042] invariant — boundary/overflow/wrap case #42 holds for all inputs in band 3..66; verified.
      ref[mod01:043] invariant — boundary/overflow/wrap case #43 holds for all inputs in band 10..79; verified.
      ref[mod01:044] invariant — boundary/overflow/wrap case #44 holds for all inputs in band 17..92; verified.
      ref[mod01:045] invariant — boundary/overflow/wrap case #45 holds for all inputs in band 24..8; verified.
      ref[mod01:046] invariant — boundary/overflow/wrap case #46 holds for all inputs in band 31..21; verified.
      ref[mod01:047] invariant — boundary/overflow/wrap case #47 holds for all inputs in band 38..34; verified.
      ref[mod01:048] invariant — boundary/overflow/wrap case #48 holds for all inputs in band 45..47; verified.
      ref[mod01:049] invariant — boundary/overflow/wrap case #49 holds for all inputs in band 52..60; verified.
      ref[mod01:050] invariant — boundary/overflow/wrap case #50 holds for all inputs in band 59..73; verified.
      ref[mod01:051] invariant — boundary/overflow/wrap case #51 holds for all inputs in band 66..86; verified.
      ref[mod01:052] invariant — boundary/overflow/wrap case #52 holds for all inputs in band 73..2; verified.
      ref[mod01:053] invariant — boundary/overflow/wrap case #53 holds for all inputs in band 80..15; verified.
      ref[mod01:054] invariant — boundary/overflow/wrap case #54 holds for all inputs in band 87..28; verified.
      ref[mod01:055] invariant — boundary/overflow/wrap case #55 holds for all inputs in band 94..41; verified.
      ref[mod01:056] invariant — boundary/overflow/wrap case #56 holds for all inputs in band 4..54; verified.
      ref[mod01:057] invariant — boundary/overflow/wrap case #57 holds for all inputs in band 11..67; verified.
      ref[mod01:058] invariant — boundary/overflow/wrap case #58 holds for all inputs in band 18..80; verified.
      ref[mod01:059] invariant — boundary/overflow/wrap case #59 holds for all inputs in band 25..93; verified.
      ref[mod01:060] invariant — boundary/overflow/wrap case #60 holds for all inputs in band 32..9; verified.
      ref[mod01:061] invariant — boundary/overflow/wrap case #61 holds for all inputs in band 39..22; verified.
      ref[mod01:062] invariant — boundary/overflow/wrap case #62 holds for all inputs in band 46..35; verified.
      ref[mod01:063] invariant — boundary/overflow/wrap case #63 holds for all inputs in band 53..48; verified.
      ref[mod01:064] invariant — boundary/overflow/wrap case #64 holds for all inputs in band 60..61; verified.
      ref[mod01:065] invariant — boundary/overflow/wrap case #65 holds for all inputs in band 67..74; verified.
      ref[mod01:066] invariant — boundary/overflow/wrap case #66 holds for all inputs in band 74..87; verified.
      ref[mod01:067] invariant — boundary/overflow/wrap case #67 holds for all inputs in band 81..3; verified.
      ref[mod01:068] invariant — boundary/overflow/wrap case #68 holds for all inputs in band 88..16; verified.
      ref[mod01:069] invariant — boundary/overflow/wrap case #69 holds for all inputs in band 95..29; verified.
      ref[mod01:070] invariant — boundary/overflow/wrap case #70 holds for all inputs in band 5..42; verified.
      ref[mod01:071] invariant — boundary/overflow/wrap case #71 holds for all inputs in band 12..55; verified.
      ref[mod01:072] invariant — boundary/overflow/wrap case #72 holds for all inputs in band 19..68; verified.
      ref[mod01:073] invariant — boundary/overflow/wrap case #73 holds for all inputs in band 26..81; verified.
      ref[mod01:074] invariant — boundary/overflow/wrap case #74 holds for all inputs in band 33..94; verified.
      ref[mod01:075] invariant — boundary/overflow/wrap case #75 holds for all inputs in band 40..10; verified.
      ref[mod01:076] invariant — boundary/overflow/wrap case #76 holds for all inputs in band 47..23; verified.
      ref[mod01:077] invariant — boundary/overflow/wrap case #77 holds for all inputs in band 54..36; verified.
      ref[mod01:078] invariant — boundary/overflow/wrap case #78 holds for all inputs in band 61..49; verified.
      ref[mod01:079] invariant — boundary/overflow/wrap case #79 holds for all inputs in band 68..62; verified.
      ref[mod01:080] invariant — boundary/overflow/wrap case #80 holds for all inputs in band 75..75; verified.
      ref[mod01:081] invariant — boundary/overflow/wrap case #81 holds for all inputs in band 82..88; verified.
      ref[mod01:082] invariant — boundary/overflow/wrap case #82 holds for all inputs in band 89..4; verified.
      ref[mod01:083] invariant — boundary/overflow/wrap case #83 holds for all inputs in band 96..17; verified.
      ref[mod01:084] invariant — boundary/overflow/wrap case #84 holds for all inputs in band 6..30; verified.
      ref[mod01:085] invariant — boundary/overflow/wrap case #85 holds for all inputs in band 13..43; verified.
      ref[mod01:086] invariant — boundary/overflow/wrap case #86 holds for all inputs in band 20..56; verified.
      ref[mod01:087] invariant — boundary/overflow/wrap case #87 holds for all inputs in band 27..69; verified.
      ref[mod01:088] invariant — boundary/overflow/wrap case #88 holds for all inputs in band 34..82; verified.
      ref[mod01:089] invariant — boundary/overflow/wrap case #89 holds for all inputs in band 41..95; verified.
      ref[mod01:090] invariant — boundary/overflow/wrap case #90 holds for all inputs in band 48..11; verified.
      ref[mod01:091] invariant — boundary/overflow/wrap case #91 holds for all inputs in band 55..24; verified.
      ref[mod01:092] invariant — boundary/overflow/wrap case #92 holds for all inputs in band 62..37; verified.
      ref[mod01:093] invariant — boundary/overflow/wrap case #93 holds for all inputs in band 69..50; verified.
      ref[mod01:094] invariant — boundary/overflow/wrap case #94 holds for all inputs in band 76..63; verified.
      ref[mod01:095] invariant — boundary/overflow/wrap case #95 holds for all inputs in band 83..76; verified.
      ref[mod01:096] invariant — boundary/overflow/wrap case #96 holds for all inputs in band 90..89; verified.
      ref[mod01:097] invariant — boundary/overflow/wrap case #97 holds for all inputs in band 0..5; verified.
      ref[mod01:098] invariant — boundary/overflow/wrap case #98 holds for all inputs in band 7..18; verified.
      ref[mod01:099] invariant — boundary/overflow/wrap case #99 holds for all inputs in band 14..31; verified.
      ref[mod01:100] invariant — boundary/overflow/wrap case #100 holds for all inputs in band 21..44; verified.
      ref[mod01:101] invariant — boundary/overflow/wrap case #101 holds for all inputs in band 28..57; verified.
      ref[mod01:102] invariant — boundary/overflow/wrap case #102 holds for all inputs in band 35..70; verified.
      ref[mod01:103] invariant — boundary/overflow/wrap case #103 holds for all inputs in band 42..83; verified.
      ref[mod01:104] invariant — boundary/overflow/wrap case #104 holds for all inputs in band 49..96; verified.
      ref[mod01:105] invariant — boundary/overflow/wrap case #105 holds for all inputs in band 56..12; verified.
      ref[mod01:106] invariant — boundary/overflow/wrap case #106 holds for all inputs in band 63..25; verified.
      ref[mod01:107] invariant — boundary/overflow/wrap case #107 holds for all inputs in band 70..38; verified.
      ref[mod01:108] invariant — boundary/overflow/wrap case #108 holds for all inputs in band 77..51; verified.
      ref[mod01:109] invariant — boundary/overflow/wrap case #109 holds for all inputs in band 84..64; verified.
      ref[mod01:110] invariant — boundary/overflow/wrap case #110 holds for all inputs in band 91..77; verified.
      ref[mod01:111] invariant — boundary/overflow/wrap case #111 holds for all inputs in band 1..90; verified.
      ref[mod01:112] invariant — boundary/overflow/wrap case #112 holds for all inputs in band 8..6; verified.
      ref[mod01:113] invariant — boundary/overflow/wrap case #113 holds for all inputs in band 15..19; verified.
      ref[mod01:114] invariant — boundary/overflow/wrap case #114 holds for all inputs in band 22..32; verified.
      ref[mod01:115] invariant — boundary/overflow/wrap case #115 holds for all inputs in band 29..45; verified.
      ref[mod01:116] invariant — boundary/overflow/wrap case #116 holds for all inputs in band 36..58; verified.
      ref[mod01:117] invariant — boundary/overflow/wrap case #117 holds for all inputs in band 43..71; verified.
      ref[mod01:118] invariant — boundary/overflow/wrap case #118 holds for all inputs in band 50..84; verified.
      ref[mod01:119] invariant — boundary/overflow/wrap case #119 holds for all inputs in band 57..0; verified.
      ref[mod01:120] invariant — boundary/overflow/wrap case #120 holds for all inputs in band 64..13; verified.
      ref[mod01:121] invariant — boundary/overflow/wrap case #121 holds for all inputs in band 71..26; verified.
      ref[mod01:122] invariant — boundary/overflow/wrap case #122 holds for all inputs in band 78..39; verified.
      ref[mod01:123] invariant — boundary/overflow/wrap case #123 holds for all inputs in band 85..52; verified.
      ref[mod01:124] invariant — boundary/overflow/wrap case #124 holds for all inputs in band 92..65; verified.
      ref[mod01:125] invariant — boundary/overflow/wrap case #125 holds for all inputs in band 2..78; verified.
      ref[mod01:126] invariant — boundary/overflow/wrap case #126 holds for all inputs in band 9..91; verified.
      ref[mod01:127] invariant — boundary/overflow/wrap case #127 holds for all inputs in band 16..7; verified.
      ref[mod01:128] invariant — boundary/overflow/wrap case #128 holds for all inputs in band 23..20; verified.
      ref[mod01:129] invariant — boundary/overflow/wrap case #129 holds for all inputs in band 30..33; verified.
      ref[mod01:130] invariant — boundary/overflow/wrap case #130 holds for all inputs in band 37..46; verified.
      ref[mod01:131] invariant — boundary/overflow/wrap case #131 holds for all inputs in band 44..59; verified.
      ref[mod01:132] invariant — boundary/overflow/wrap case #132 holds for all inputs in band 51..72; verified.
      ref[mod01:133] invariant — boundary/overflow/wrap case #133 holds for all inputs in band 58..85; verified.
      ref[mod01:134] invariant — boundary/overflow/wrap case #134 holds for all inputs in band 65..1; verified.
      ref[mod01:135] invariant — boundary/overflow/wrap case #135 holds for all inputs in band 72..14; verified.
      ref[mod01:136] invariant — boundary/overflow/wrap case #136 holds for all inputs in band 79..27; verified.
      ref[mod01:137] invariant — boundary/overflow/wrap case #137 holds for all inputs in band 86..40; verified.
      ref[mod01:138] invariant — boundary/overflow/wrap case #138 holds for all inputs in band 93..53; verified.
      ref[mod01:139] invariant — boundary/overflow/wrap case #139 holds for all inputs in band 3..66; verified.
      ref[mod01:140] invariant — boundary/overflow/wrap case #140 holds for all inputs in band 10..79; verified.
      ref[mod01:141] invariant — boundary/overflow/wrap case #141 holds for all inputs in band 17..92; verified.
      ref[mod01:142] invariant — boundary/overflow/wrap case #142 holds for all inputs in band 24..8; verified.
      ref[mod01:143] invariant — boundary/overflow/wrap case #143 holds for all inputs in band 31..21; verified.
      ref[mod01:144] invariant — boundary/overflow/wrap case #144 holds for all inputs in band 38..34; verified.
      ref[mod01:145] invariant — boundary/overflow/wrap case #145 holds for all inputs in band 45..47; verified.
      ref[mod01:146] invariant — boundary/overflow/wrap case #146 holds for all inputs in band 52..60; verified.
      ref[mod01:147] invariant — boundary/overflow/wrap case #147 holds for all inputs in band 59..73; verified.
      ref[mod01:148] invariant — boundary/overflow/wrap case #148 holds for all inputs in band 66..86; verified.
      ref[mod01:149] invariant — boundary/overflow/wrap case #149 holds for all inputs in band 73..2; verified.
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
