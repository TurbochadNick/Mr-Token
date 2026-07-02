#!/usr/bin/env python3
"""Generate the debug-scanlib seed — a DISPOSABLE-BLOAT fixture, the mirror image of
debug-speclib, built to reach the regime where EARLY COMPACTION WINS.

The lesson from debug-speclib: making every reference load-bearing MAXIMIZES re-read
risk (the term that kills the compaction benefit in the working model), so early reset
loses. To make early compaction *win* you need the opposite — context that is bloaty
and read EARLY but then DISPOSABLE, with a long tail of work that never needs it again:

    early compaction pays iff  reclaimable x carry-cost x turns_remaining
                               > summary + re-establish + re-read_risk

debug-scanlib maximizes the LEFT side and minimizes re-read_risk:

  * `notes/note00.md`..`noteNN.md` — a big pile of plausible "design notes / conventions"
    (~120k tokens total) that TASK.md tells the agent to read first, but which contain
    NO fix information. This is the disposable bulk: read once, never needed again.
  * `mod00.py`..`mod23.py` — each has ONE buggy function whose correct behavior is stated
    in a SMALL BEHAVIOR REFERENCE docstring in that module (a few lines). This is the
    durable, load-bearing info — but it's tiny, so re-reading it after a reset is cheap.
  * Tests are property-based + a one-way SHA-256 digest pin (no answers leak), same as
    debug-speclib, so the module docstrings really are the only source of behavior.

Result: `continue` carries the ~120k of notes through all 24 fixes (expensive every
turn); a reset arm drops the notes right after reading them and finishes from the tiny
module docstrings (cheap). That is the regime where compacting early pays off.

No args -> writes buggy seed/. `--solution <dir>` -> emits the correct version.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

INT_DOMAIN = list(range(64))
N_NOTES = 12                    # disposable "design notes" files
NOTE_LINES = 260               # ~ lines per note; N_NOTES x NOTE_LINES -> ~110k tokens total
# (~9k tokens/note: read whole in one Read, under the 2000-line limit; total bloat lands
#  continue ~130-150k peak — crosses the 100k reset threshold, stays under the 200k window.)


def _str_domain():
    out = []
    for i in range(40):
        length = 3 + (i % 6)
        s = "".join(chr(97 + ((i * 5 + j * 3) % 26)) for j in range(length))
        if i % 4 == 0:
            s = s[:1] + " " + s[1:]
        if i % 5 == 0:
            s = s + "7"
        out.append(s)
    return out


STR_DOMAIN = _str_domain()


# --- reference implementations + buggy bodies (shared with debug-speclib) -------

def _affine(A, B, M):
    return lambda n: (A * n + B) % M

def _digit_sum(b):
    def f(n):
        if n == 0:
            return 0
        t, s = n, 0
        while t:
            s += t % b
            t //= b
        return s
    return f

def _caesar(K):
    def f(s):
        return "".join(
            chr((ord(c) - 97 + K) % 26 + 97) if "a" <= c <= "z" else c for c in s
        )
    return f

def _poly(C, D, M):
    return lambda n: (n * n * n + C * n + D) % M

def _bitrev(W):
    def f(n):
        r = 0
        for i in range(W):
            r = (r << 1) | ((n >> i) & 1)
        return r
    return f

def _rollhash(P, M):
    def f(s):
        h = 0
        for i, c in enumerate(s):
            h = (h + ord(c) * pow(P, i)) % M
        return h
    return f

def _gray(M):
    return lambda n: (n ^ (n >> 1)) % M

def _checksum(W1, W2, M):
    def f(n):
        if n == 0:
            return 0 % M
        t, i, s = n, 0, 0
        while t:
            d = t % 10
            w = W1 if i % 2 == 0 else W2
            s = (s + w * d) % M
            t //= 10
            i += 1
        return s
    return f


FAMILIES = [
    dict(
        fid="affine", name="affine", arg="n", dom="int", out="int", ref=_affine,
        correct=lambda A, B, M: f"    return (({A} * n) + {B}) % {M}",
        buggy=lambda A, B, M: f"    return ({A} * n) + {B}   # BUG: missing the final % {M}",
        spec=lambda A, B, M: f"return ((A * n) + B) % M with A={A}, B={B}, M={M}. The final % M is mandatory.",
        consts=[(5, 3, 97), (7, 11, 101), (9, 5, 103)],
    ),
    dict(
        fid="digit_sum", name="digit_sum", arg="n", dom="int", out="int", ref=lambda b: _digit_sum(b),
        correct=lambda b: ("    if n == 0:\n        return 0\n"
                           f"    t, s = n, 0\n    while t:\n        s += t % {b}\n        t //= {b}\n    return s"),
        buggy=lambda b: ("    if n == 0:\n        return 0\n"
                         "    t, s = n, 0\n    while t:\n        s += t % 10\n        t //= 10   # BUG: base 10, not "
                         f"base {b}\n    return s"),
        spec=lambda b: f"sum the digits of n written in base {b} (not base 10); digit_sum(0)=0.",
        consts=[(3,), (5,), (7,)],
    ),
    dict(
        fid="caesar", name="caesar", arg="s", dom="str", out="str", ref=lambda K: _caesar(K),
        correct=lambda K: ("    return \"\".join(\n"
                           f"        chr((ord(c) - 97 + {K}) % 26 + 97) if \"a\" <= c <= \"z\" else c for c in s\n    )"),
        buggy=lambda K: ("    return \"\".join(\n"
                         f"        chr(ord(c) + {K}) if \"a\" <= c <= \"z\" else c for c in s   # BUG: no wrap mod 26\n    )"),
        spec=lambda K: f"Caesar-shift each a-z forward by {K} with wrap: chr((ord(c)-97+{K})%26+97); leave non a-z unchanged.",
        consts=[(3,), (7,), (11,)],
    ),
    dict(
        fid="poly", name="poly", arg="n", dom="int", out="int", ref=_poly,
        correct=lambda C, D, M: f"    return ((n * n * n) + ({C} * n) + {D}) % {M}",
        buggy=lambda C, D, M: f"    return ((n * n) + ({C} * n) + {D}) % {M}   # BUG: n**2, spec says n**3",
        spec=lambda C, D, M: f"return (n**3 + C*n + D) % M with C={C}, D={D}, M={M}. Leading term is n CUBED.",
        consts=[(2, 1, 97), (3, 5, 101), (5, 2, 103)],
    ),
    dict(
        fid="bitrev", name="bitrev", arg="n", dom="int", out="int", ref=lambda W: _bitrev(W),
        correct=lambda W: f"    r = 0\n    for i in range({W}):\n        r = (r << 1) | ((n >> i) & 1)\n    return r",
        buggy=lambda W: (f"    r = 0\n    for i in range({W} - 1):   # BUG: reverses {W - 1} bits, spec says {W}\n"
                         "        r = (r << 1) | ((n >> i) & 1)\n    return r"),
        spec=lambda W: f"reverse the low {W} bits of n (LSB..MSB): for i in range({W}): r=(r<<1)|((n>>i)&1). W={W}.",
        consts=[(5,), (6,), (7,)],
    ),
    dict(
        fid="rollhash", name="rollhash", arg="s", dom="str", out="int", ref=_rollhash,
        correct=lambda P, M: (f"    h = 0\n    for i, c in enumerate(s):\n        h = (h + ord(c) * pow({P}, i)) % {M}\n    return h"),
        buggy=lambda P, M: (f"    h = 0\n    for i, c in enumerate(s):\n"
                            f"        h = (h + ord(c) * pow({P}, len(s) - i)) % {M}   # BUG: exponent is i, not len(s)-i\n    return h"),
        spec=lambda P, M: f"rolling hash: h = (sum ord(s[i]) * P**i) % M, exponent is 0-based index i. P={P}, M={M}. empty->0.",
        consts=[(31, 1009), (37, 1013), (41, 1019)],
    ),
    dict(
        fid="gray", name="gray", arg="n", dom="int", out="int", ref=lambda M: _gray(M),
        correct=lambda M: f"    return (n ^ (n >> 1)) % {M}",
        buggy=lambda M: f"    return (n ^ (n >> 2)) % {M}   # BUG: shift is 1, not 2",
        spec=lambda M: f"Gray code reduced mod {M}: return (n ^ (n >> 1)) % M with shift exactly 1, M={M}.",
        consts=[(89,), (91,), (93,)],
    ),
    dict(
        fid="checksum", name="checksum", arg="n", dom="int", out="int", ref=_checksum,
        correct=lambda W1, W2, M: (f"    if n == 0:\n        return 0 % {M}\n"
                                   "    t, i, s = n, 0, 0\n    while t:\n        d = t % 10\n"
                                   f"        w = {W1} if i % 2 == 0 else {W2}\n        s = (s + w * d) % {M}\n"
                                   "        t //= 10\n        i += 1\n    return s"),
        buggy=lambda W1, W2, M: (f"    if n == 0:\n        return 0 % {M}\n"
                                 "    t, i, s = n, 0, 0\n    while t:\n        d = t % 10\n"
                                 f"        w = {W1}   # BUG: weight never alternates to {W2}\n        s = (s + w * d) % {M}\n"
                                 "        t //= 10\n        i += 1\n    return s"),
        spec=lambda W1, W2, M: f"weighted digit checksum mod {M}: digits from the RIGHT, weights alternate W1={W1},W2={W2},W1,...; sum(w*d)%M; checksum(0)=0.",
        consts=[(3, 1, 97), (7, 3, 101), (2, 5, 103)],
    ),
]


def _modules():
    mods = []
    for inst in range(3):
        for fam in FAMILIES:
            mods.append((fam, fam["consts"][inst]))
    return mods


def _module_src(mod, fam, consts, buggy):
    body = fam["buggy"](*consts) if buggy else fam["correct"](*consts)
    const_names = {
        "affine": "A, B, M", "digit_sum": "b", "caesar": "K", "poly": "C, D, M",
        "bitrev": "W", "rollhash": "P, M", "gray": "M", "checksum": "W1, W2, M",
    }[fam["fid"]]
    doc = (
        f"{mod} - single-function module.\n\n"
        f"    BEHAVIOR REFERENCE (authoritative; the test pins outputs with a one-way digest,\n"
        f"    so this docstring is the only source of the concrete behavior):\n"
        f"    {fam['name']}({fam['arg']}) — {fam['spec'](*consts)}\n"
        f"    Constants for THIS module: {const_names} = {', '.join(map(str, consts))}."
    )
    return (
        f'"""{doc}\n    """\n\n'
        f"def {fam['name']}({fam['arg']}):\n"
        f'    """See the BEHAVIOR REFERENCE at the top of this module."""\n'
        f"{body}\n"
    )


def _note_src(idx):
    """A deterministic pile of plausible 'design notes' — pure disposable filler. Contains
    NO fix information; reading it is what bloats context, and it is never needed again."""
    topics = ["naming conventions", "error-handling policy", "logging format", "module layout",
              "dependency rationale", "review checklist", "deprecation timeline", "style guide",
              "historical decisions", "testing philosophy", "release process", "glossary"]
    topic = topics[idx % len(topics)]
    lines = [f"# Design Notes vol. {idx:02d} — {topic}",
             "",
             "These notes capture background and conventions for the library. They are provided",
             "for context only and do not contain function specifications.",
             ""]
    for i in range(NOTE_LINES):
        band = (idx * 131 + i * 17) % 997
        lines.append(
            f"- note[{idx:02d}:{i:04d}] convention {band}: keep changes minimal and consistent with "
            f"prior art (band {band % 53}, log entry {band % 89}); advisory only, no behavioral "
            f"requirement for any module function."
        )
    return "\n".join(lines) + "\n"


def _digest(fam, consts, domain):
    fn = fam["ref"](*consts)
    return hashlib.sha256(repr([fn(x) for x in domain]).encode()).hexdigest()


def write(dest, buggy):
    os.makedirs(dest, exist_ok=True)
    notes_dir = os.path.join(dest, "notes")
    os.makedirs(notes_dir, exist_ok=True)
    for i in range(N_NOTES):
        with open(os.path.join(notes_dir, f"note{i:02d}.md"), "w") as fh:
            fh.write(_note_src(i))

    mods = _modules()
    for idx, (fam, consts) in enumerate(mods):
        mod = f"mod{idx:02d}"
        with open(os.path.join(dest, f"{mod}.py"), "w") as fh:
            fh.write(_module_src(mod, fam, consts, buggy))

    lines = [
        "import hashlib",
        "import random",
        "",
        "INT_DOMAIN = list(range(64))",
        f"STR_DOMAIN = {STR_DOMAIN!r}",
        "",
        "",
        "def _digest(fn, domain):",
        "    return hashlib.sha256(repr([fn(x) for x in domain]).encode()).hexdigest()",
        "",
    ]
    for idx, (fam, consts) in enumerate(mods):
        mod = f"mod{idx:02d}"
        name = fam["name"]
        domain = INT_DOMAIN if fam["dom"] == "int" else STR_DOMAIN
        domain_var = "INT_DOMAIN" if fam["dom"] == "int" else "STR_DOMAIN"
        digest = _digest(fam, consts, domain)
        seed = 2000 + idx
        lines.append(f"def test_{mod}():")
        lines.append(f"    from {mod} import {name}")
        lines.append(f"    rng = random.Random({seed})")
        lines.append(f"    for _ in range(40):")
        lines.append(f"        x = rng.choice({domain_var})")
        lines.append(f"        y = {name}(x)")
        if fam["out"] == "int":
            lines.append(f"        assert isinstance(y, int) and y >= 0")
        else:
            lines.append(f"        assert isinstance(y, str) and len(y) == len(x)")
        lines.append(f"    assert _digest({name}, {domain_var}) == {digest!r}")
        lines.append("")
    with open(os.path.join(dest, "test_scanlib.py"), "w") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--solution":
        write(sys.argv[2], buggy=False)
        print(f"wrote correct solution to {sys.argv[2]}")
    else:
        write(os.path.join(HERE, "seed"), buggy=True)
        print(f"wrote buggy seed to {os.path.join(HERE, 'seed')} "
              f"({len(_modules())} modules + {N_NOTES} disposable notes)")
