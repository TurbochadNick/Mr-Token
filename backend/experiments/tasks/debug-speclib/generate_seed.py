#!/usr/bin/env python3
"""Generate the debug-speclib seed — a LOAD-BEARING context-bloat fixture.

Why this exists (vs debug-hugelib): debug-hugelib's tests hardcode the expected
outputs (`assert scale(3,4) == 12`) and all modules share the same 4 functions,
so an agent greps the test file, fixes every module, and NEVER reads a reference.
Peak context short-circuits ~45k and rarely crosses 100k.

debug-speclib removes every shortcut, so the ONLY path to a green suite is to read
each module's reference:

  1. Concrete behavior lives ONLY in the reference. The test asserts a one-way
     SHA-256 digest of each function's outputs over a fixed domain. The digest
     leaks nothing (can't be reversed or grepped), so you cannot pass by copying
     an answer out of the test — you must implement the spec correctly, and the
     spec is stated only in the module's BEHAVIOR REFERENCE docstring.
  2. Property-based. Tests sample random inputs and assert structural invariants
     (type, length preservation), then the digest pin. No literal I/O pairs.
  3. Distinct per-module logic. 8 algorithm families x 3 constant-sets = 24
     modules, interleaved so no neighbor shares a family, each with UNIQUE
     constants -> reading one reference never fixes another. Every reference is
     load-bearing, so all 24 must be read -> context reliably crosses 100k.

Reproducible: fixed output every run. No args -> writes buggy seed/. With
`--solution <dir>` -> emits the CORRECT version (to confirm the task is solvable
and the digests match).
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

INT_DOMAIN = list(range(64))
REF_LEDGER_LINES = 70           # bulk of the reference; forces a large whole-file read.
# Calibrated so a `continue` run peaks ~150-165k: crosses the 100k reset threshold but
# stays under the 200k context window, so continue COMPLETES (expensively) rather than
# auto-compacting and thrashing. That keeps the matrix a cost-at-equal-completion test
# (pre-registered rule 5A.5). At 130 lines continue peaked 226k and failed to complete.


def _str_domain():
    """Deterministic list of 40 short strings; some carry a space or digit so the
    'non-alpha unchanged' branch of the caesar family is actually exercised."""
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


# --- reference implementations (the spec, in code) + the buggy bodies ---------
# Each family: reference callable (for digest), correct body, buggy body, the
# argument name, the output kind ('int'|'str'), and a precise prose spec.

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


# (family_id, func_name, arg, kind, prop_lines, ref_callable_factory,
#  correct_body(consts), buggy_body(consts), spec_core(consts), [consts...])
FAMILIES = [
    dict(
        fid="affine", name="affine", arg="n", dom="int", out="int",
        ref=_affine,
        correct=lambda A, B, M: f"    return (({A} * n) + {B}) % {M}",
        buggy=lambda A, B, M: f"    return ({A} * n) + {B}   # BUG: missing the final % {M}",
        spec=lambda A, B, M: (
            f"Compute an affine map modulo {M}.\n"
            f"    Algorithm: return ((A * n) + B) % M with A = {A}, B = {B}, M = {M}.\n"
            f"    The final modulo by M is mandatory; the result is always in 0..{M - 1}."
        ),
        consts=[(5, 3, 97), (7, 11, 101), (9, 5, 103)],
    ),
    dict(
        fid="digit_sum", name="digit_sum", arg="n", dom="int", out="int",
        ref=lambda b: _digit_sum(b),
        correct=lambda b: (
            "    if n == 0:\n        return 0\n"
            f"    t, s = n, 0\n    while t:\n        s += t % {b}\n        t //= {b}\n    return s"
        ),
        buggy=lambda b: (
            "    if n == 0:\n        return 0\n"
            "    t, s = n, 0\n    while t:\n        s += t % 10\n        t //= 10   # BUG: base 10, not "
            f"base {b}\n    return s"
        ),
        spec=lambda b: (
            f"Sum the digits of n written in base {b} (NOT base 10).\n"
            f"    Algorithm: repeatedly add (t % {b}) and floor-divide t by {b} until t == 0.\n"
            f"    digit_sum(0) is 0. The base is {b}."
        ),
        consts=[(3,), (5,), (7,)],
    ),
    dict(
        fid="caesar", name="caesar", arg="s", dom="str", out="str",
        ref=lambda K: _caesar(K),
        correct=lambda K: (
            "    return \"\".join(\n"
            f"        chr((ord(c) - 97 + {K}) % 26 + 97) if \"a\" <= c <= \"z\" else c for c in s\n"
            "    )"
        ),
        buggy=lambda K: (
            "    return \"\".join(\n"
            f"        chr(ord(c) + {K}) if \"a\" <= c <= \"z\" else c for c in s   # BUG: no wrap mod 26\n"
            "    )"
        ),
        spec=lambda K: (
            f"Caesar-shift every lowercase letter a-z forward by {K}, wrapping within a-z.\n"
            f"    Algorithm: for each char, if it is a-z map it to chr((ord(c) - 97 + {K}) % 26 + 97);\n"
            f"    otherwise leave it unchanged. Shift amount K = {K}. Length is preserved."
        ),
        consts=[(3,), (7,), (11,)],
    ),
    dict(
        fid="poly", name="poly", arg="n", dom="int", out="int",
        ref=_poly,
        correct=lambda C, D, M: f"    return ((n * n * n) + ({C} * n) + {D}) % {M}",
        buggy=lambda C, D, M: f"    return ((n * n) + ({C} * n) + {D}) % {M}   # BUG: n**2, spec says n**3",
        spec=lambda C, D, M: (
            f"Evaluate a cubic polynomial modulo {M}.\n"
            f"    Algorithm: return (n**3 + C*n + D) % M with C = {C}, D = {D}, M = {M}.\n"
            f"    The leading term is n CUBED (n*n*n), not squared."
        ),
        consts=[(2, 1, 97), (3, 5, 101), (5, 2, 103)],
    ),
    dict(
        fid="bitrev", name="bitrev", arg="n", dom="int", out="int",
        ref=lambda W: _bitrev(W),
        correct=lambda W: (
            f"    r = 0\n    for i in range({W}):\n        r = (r << 1) | ((n >> i) & 1)\n    return r"
        ),
        buggy=lambda W: (
            f"    r = 0\n    for i in range({W} - 1):   # BUG: reverses {W - 1} bits, spec says {W}\n"
            "        r = (r << 1) | ((n >> i) & 1)\n    return r"
        ),
        spec=lambda W: (
            f"Reverse the low {W} bits of n.\n"
            f"    Algorithm: build r by shifting in bits 0..{W - 1} of n from LSB to MSB:\n"
            f"    for i in range({W}): r = (r << 1) | ((n >> i) & 1). Bit width W = {W}.\n"
            f"    Result is in 0..{(1 << W) - 1}."
        ),
        consts=[(5,), (6,), (7,)],
    ),
    dict(
        fid="rollhash", name="rollhash", arg="s", dom="str", out="int",
        ref=_rollhash,
        correct=lambda P, M: (
            f"    h = 0\n    for i, c in enumerate(s):\n        h = (h + ord(c) * pow({P}, i)) % {M}\n"
            "    return h"
        ),
        buggy=lambda P, M: (
            f"    h = 0\n    for i, c in enumerate(s):\n"
            f"        h = (h + ord(c) * pow({P}, len(s) - i)) % {M}   # BUG: exponent is i, not len(s)-i\n"
            "    return h"
        ),
        spec=lambda P, M: (
            f"Polynomial rolling hash of the string s modulo {M}.\n"
            f"    Algorithm: h = (sum over positions i of ord(s[i]) * P**i) % M, where the exponent\n"
            f"    is the 0-based index i (the first char uses P**0). P = {P}, M = {M}.\n"
            f"    Empty string hashes to 0."
        ),
        consts=[(31, 1009), (37, 1013), (41, 1019)],
    ),
    dict(
        fid="gray", name="gray", arg="n", dom="int", out="int",
        ref=lambda M: _gray(M),
        correct=lambda M: f"    return (n ^ (n >> 1)) % {M}",
        buggy=lambda M: f"    return (n ^ (n >> 2)) % {M}   # BUG: shift is 1, not 2",
        spec=lambda M: (
            f"Reflected binary Gray code of n, reduced modulo {M}.\n"
            f"    Algorithm: return (n ^ (n >> 1)) % M with a shift of exactly 1 and M = {M}."
        ),
        consts=[(89,), (91,), (93,)],
    ),
    dict(
        fid="checksum", name="checksum", arg="n", dom="int", out="int",
        ref=_checksum,
        correct=lambda W1, W2, M: (
            f"    if n == 0:\n        return 0 % {M}\n"
            "    t, i, s = n, 0, 0\n    while t:\n        d = t % 10\n"
            f"        w = {W1} if i % 2 == 0 else {W2}\n        s = (s + w * d) % {M}\n"
            "        t //= 10\n        i += 1\n    return s"
        ),
        buggy=lambda W1, W2, M: (
            f"    if n == 0:\n        return 0 % {M}\n"
            "    t, i, s = n, 0, 0\n    while t:\n        d = t % 10\n"
            f"        w = {W1}   # BUG: weight never alternates to {W2}\n        s = (s + w * d) % {M}\n"
            "        t //= 10\n        i += 1\n    return s"
        ),
        spec=lambda W1, W2, M: (
            f"Weighted digit checksum of n modulo {M}.\n"
            f"    Algorithm: read the base-10 digits of n from the RIGHT. Weight the rightmost digit\n"
            f"    by W1 = {W1}, the next by W2 = {W2}, then W1, W2, ... alternating. Sum weight*digit,\n"
            f"    then take % M with M = {M}. checksum(0) is 0."
        ),
        consts=[(3, 1, 97), (7, 3, 101), (2, 5, 103)],
    ),
]


def _ref_block(mod, fam, consts):
    name = fam["name"]
    const_names = {
        "affine": "A, B, M", "digit_sum": "b", "caesar": "K", "poly": "C, D, M",
        "bitrev": "W", "rollhash": "P, M", "gray": "M", "checksum": "W1, W2, M",
    }[fam["fid"]]
    head = [
        f"BEHAVIOR REFERENCE - module '{mod}' (function `{name}`)",
        "AUTHORITATIVE. The function body below is buggy; correct it to match THIS",
        "specification exactly. The test asserts a one-way digest of the outputs over a",
        "fixed domain, so the expected outputs appear NOWHERE in the test file - this",
        "reference is the ONLY source of the concrete behavior. Read it fully before editing.",
        "",
        f"Signature: {name}({fam['arg']})",
        f"Constants for THIS module: {const_names} = {', '.join(map(str, consts))}",
        "",
        "Specification:",
        "    " + fam["spec"](*consts).replace("\n", "\n    "),
        "",
        "Conformance ledger (each line restates an invariant the corrected function must",
        "satisfy over one input band; the property test samples across all bands):",
    ]
    ledger = []
    for i in range(REF_LEDGER_LINES):
        band_lo = (i * 7) % 97
        band_hi = (i * 13 + 5) % 97
        ledger.append(
            f"  ledger[{mod}:{i:03d}] inputs with index congruent to {i % 17} (mod 17) in band "
            f"{band_lo}..{band_hi} are fully determined by the Specification above; "
            f"no special-casing, no clamping, no early return."
        )
    return "\n    ".join(head + ledger)


def _module_src(mod, fam, consts, buggy):
    body = fam["buggy"](*consts) if buggy else fam["correct"](*consts)
    doc = _ref_block(mod, fam, consts)
    return (
        f'"""{mod} - single-function module.\n\n    {doc}\n    """\n\n'
        f"def {fam['name']}({fam['arg']}):\n"
        f'    """See the BEHAVIOR REFERENCE at the top of this module."""\n'
        f"{body}\n"
    )


def _modules():
    """24 modules: 3 constant-instances of each of the 8 families, interleaved so
    no two adjacent modules share a family."""
    mods = []
    for inst in range(3):
        for fam in FAMILIES:
            mods.append((fam, fam["consts"][inst]))
    return mods


def _digest(fam, consts, domain):
    fn = fam["ref"](*consts)
    blob = repr([fn(x) for x in domain])
    return hashlib.sha256(blob.encode()).hexdigest()


def write(dest, buggy):
    os.makedirs(dest, exist_ok=True)
    mods = _modules()
    for idx, (fam, consts) in enumerate(mods):
        mod = f"mod{idx:02d}"
        with open(os.path.join(dest, f"{mod}.py"), "w") as fh:
            fh.write(_module_src(mod, fam, consts, buggy))

    # test file: property sampling + one-way digest pin. No literal expected outputs.
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
        seed = 1000 + idx
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
    with open(os.path.join(dest, "test_speclib.py"), "w") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--solution":
        write(sys.argv[2], buggy=False)
        print(f"wrote correct solution to {sys.argv[2]}")
    else:
        write(os.path.join(HERE, "seed"), buggy=True)
        n = len(_modules())
        print(f"wrote buggy seed to {os.path.join(HERE, 'seed')} ({n} modules)")
