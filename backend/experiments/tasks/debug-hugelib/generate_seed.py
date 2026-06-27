#!/usr/bin/env python3
"""Generate the debug-hugelib seed — a task engineered to RELIABLY bloat context
past the 100k reset threshold (pilots 1–2 never crossed it; this fixes that).

Bloat mechanism = forced large reads. The suite spreads bugs across MANY modules,
and each module carries a large "BEHAVIOR REFERENCE" block in its docstring that
states the exact expected outputs. A bug is only fixable by reading that module's
reference — so the agent must Read every module (each ~5–7k tokens), and reading
all of them pulls well past 100k input-side tokens before the suite can pass.

Reproducible: fixed output every run. Run with no args to write seed/; run with
`--solution <dir>` to emit the correct version (to confirm the task is solvable).
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
N_MODULES = 16          # × functions below → enough forced reads to cross 100k
REF_LINES = 150         # padding lines per module's reference block (forces big reads)

# (name, sig, doc, correct_body, buggy_body, [(call, expected_repr)])
FUNCS = [
    ("scale", "(x, k)", "Return x*k.", "    return x * k", "    return x + k",
     [("scale(3,4)", "12"), ("scale(0,9)", "0")]),
    ("shift", "(s, n)", "Caesar-shift lowercase letters by n (wrap a–z).",
     "    return ''.join(chr((ord(c)-97+n)%26+97) if c.isalpha() else c for c in s)",
     "    return ''.join(chr((ord(c)-97+n)+97) if c.isalpha() else c for c in s)",
     [("shift('abz',1)", "'bca'"), ("shift('xy',3)", "'ab'")]),
    ("dedup", "(xs)", "Drop consecutive duplicates, preserving order.",
     "    out=[]\n    for v in xs:\n        if not out or out[-1]!=v: out.append(v)\n    return out",
     "    return list(set(xs))",
     [("dedup([1,1,2,2,1])", "[1, 2, 1]")]),
    ("score", "(hits, total)", "Percent as an int 0–100, 0 when total==0.",
     "    return 0 if total==0 else round(hits*100/total)",
     "    return round(hits*100/total)",
     [("score(1,4)", "25"), ("score(0,0)", "0")]),
]


def _ref_block(mod: str) -> str:
    # a large, deterministic reference table — the bulk the agent must read
    lines = [f"BEHAVIOR REFERENCE for module '{mod}' — authoritative expected outputs.",
             "Do not guess; the buggy bodies below must be corrected to match THIS table."]
    for i in range(REF_LINES):
        lines.append(f"  ref[{mod}:{i:03d}] invariant — boundary/overflow/wrap case #{i} "
                     f"holds for all inputs in band {i*7 % 97}..{(i*13+5) % 97}; verified.")
    return "\n    ".join(lines)


def _module_src(idx: int, buggy: bool) -> str:
    mod = f"mod{idx:02d}"
    parts = [f'"""{mod} — utility functions.\n\n    {_ref_block(mod)}\n    """', ""]
    for name, sig, doc, correct, bug in [(f[0], f[1], f[2], f[3], f[4]) for f in FUNCS]:
        body = bug if buggy else correct
        parts.append(f"def {name}{sig}:\n    \"\"\"{doc}\"\"\"\n{body}\n")
    return "\n".join(parts)


def write(dest: str, buggy: bool) -> None:
    os.makedirs(dest, exist_ok=True)
    for idx in range(N_MODULES):
        with open(os.path.join(dest, f"mod{idx:02d}.py"), "w") as fh:
            fh.write(_module_src(idx, buggy))
    # test imports each module's funcs by name; same names across modules, so the
    # test file imports per-module and references the bare names within that block.
    test = ["import pytest", ""]
    for idx in range(N_MODULES):
        mod = f"mod{idx:02d}"
        for f in FUNCS:
            name, cases = f[0], f[5]
            for call, expected in cases:
                tname = f"test_{mod}_{name}_{abs(hash(call+mod))%99999}"
                test.append(f"def {tname}():")
                test.append(f"    from {mod} import {name}")
                test.append(f"    assert repr({call}) == {expected!r}")
                test.append("")
    with open(os.path.join(dest, "test_hugelib.py"), "w") as fh:
        fh.write("\n".join(test))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--solution":
        write(sys.argv[2], buggy=False)
        print(f"wrote correct solution to {sys.argv[2]}")
    else:
        write(os.path.join(HERE, "seed"), buggy=True)
        print(f"wrote buggy seed to {os.path.join(HERE, 'seed')} "
              f"({N_MODULES} modules × {len(FUNCS)} funcs)")
