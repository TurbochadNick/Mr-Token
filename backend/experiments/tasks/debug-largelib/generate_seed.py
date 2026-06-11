#!/usr/bin/env python3
"""Generate the debug-largelib seed: a LARGE multi-module library with many
seeded bugs and a big pytest suite. Purpose: a task big enough that an agent
accumulates a large carried context (many files read, many fix/test turns) so we
can test the handoff wedge in the BLOATED regime (unlike pilot 1's short task).

Each function has a correct body, a buggy body, and test cases. Run with no args
to write the buggy seed/; run with `--solution <dir>` to emit the correct version
(used to verify the fixture is solvable). Reproducible: fixed output every run.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# spec: (module, name, signature, docstring, correct_body, buggy_body, [(call_expr, expected_repr)])
SPECS = [
    # ---- textkit ----
    ("textkit", "slugify", "(text)", "Lowercase, non-alnum runs to single hyphens, stripped of edge hyphens.",
     '    import re\n    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")',
     '    import re\n    return re.sub(r"[^a-z0-9]+", "-", text.lower())',
     [('slugify("  Hi, There! ")', "'hi-there'"), ('slugify("!!a!!")', "'a'")]),
    ("textkit", "truncate", "(text, limit)", "Truncate to `limit` chars incl. a trailing ellipsis when shortened.",
     '    return text if len(text) <= limit else text[:limit-3] + "..."',
     '    return text if len(text) <= limit else text[:limit] + "..."',
     [('truncate("hello world", 8)', "'hello...'"), ('len(truncate("hello world", 8))', "8")]),
    ("textkit", "word_count", "(text)", "Count whitespace-separated words; runs of spaces add nothing.",
     '    return len(text.split())',
     '    return len(text.split(" "))',
     [('word_count("a   b  c")', "3"), ('word_count("  x  ")', "1")]),
    ("textkit", "title_case", "(text)", "Capitalize each word, lowercasing the rest.",
     '    return " ".join(w.capitalize() for w in text.split())',
     '    return " ".join(w.upper() for w in text.split())',
     [('title_case("the QUICK fox")', "'The Quick Fox'")]),

    # ---- numkit ----
    ("numkit", "clamp", "(value, low, high)", "Clamp value into [low, high].",
     '    if value < low:\n        return low\n    if value > high:\n        return high\n    return value',
     '    if value < low:\n        return high\n    if value > high:\n        return low\n    return value',
     [('clamp(5, 0, 10)', "5"), ('clamp(-1, 0, 10)', "0"), ('clamp(99, 0, 10)', "10")]),
    ("numkit", "running_max", "(values)", "List of running maxima. [1,3,2] -> [1,3,3].",
     '    out, best = [], None\n    for v in values:\n        best = v if best is None or v > best else best\n        out.append(best)\n    return out',
     '    out, best = [], None\n    for v in values:\n        best = v if best is None or v < best else best\n        out.append(best)\n    return out',
     [('running_max([1,3,2,5,4])', "[1, 3, 3, 5, 5]")]),
    ("numkit", "is_prime", "(n)", "True if n is a prime greater than 1.",
     '    if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True',
     '    if n < 2:\n        return False\n    i = 2\n    while i < n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True if n != 4 else True',
     [('is_prime(7)', "True"), ('is_prime(9)', "False"), ('is_prime(2)', "True")]),
    ("numkit", "gcd", "(a, b)", "Greatest common divisor of two non-negative ints.",
     '    while b:\n        a, b = b, a % b\n    return a',
     '    while b:\n        a, b = b, a // b\n    return a',
     [('gcd(12, 18)', "6"), ('gcd(17, 5)', "1")]),

    # ---- listkit ----
    ("listkit", "chunk", "(seq, size)", "Split seq into lists of length `size` (last may be shorter).",
     '    return [seq[i:i + size] for i in range(0, len(seq), size)]',
     '    return [seq[i:i + size] for i in range(0, len(seq), size - 1)]',
     [('chunk([1,2,3,4,5], 2)', "[[1, 2], [3, 4], [5]]")]),
    ("listkit", "dedupe", "(seq)", "Remove duplicates preserving first-seen order.",
     '    seen, out = set(), []\n    for x in seq:\n        if x not in seen:\n            seen.add(x); out.append(x)\n    return out',
     '    return list(set(seq))',
     [('dedupe([1,1,2,3,3,1])', "[1, 2, 3]")]),
    ("listkit", "flatten", "(nested)", "Flatten one level. [[1,2],[3]] -> [1,2,3].",
     '    out = []\n    for g in nested:\n        out.extend(g)\n    return out',
     '    out = []\n    for g in nested:\n        out.append(g)\n    return out',
     [('flatten([[1,2],[3],[4,5]])', "[1, 2, 3, 4, 5]")]),
    ("listkit", "windows", "(seq, n)", "Sliding windows of length n. [1,2,3],2 -> [[1,2],[2,3]].",
     '    return [list(seq[i:i+n]) for i in range(0, len(seq) - n + 1)]',
     '    return [list(seq[i:i+n]) for i in range(0, len(seq))]',
     [('windows([1,2,3,4], 2)', "[[1, 2], [2, 3], [3, 4]]")]),

    # ---- dictkit ----
    ("dictkit", "invert", "(mapping)", "Swap keys and values.",
     '    return {v: k for k, v in mapping.items()}',
     '    return {k: v for k, v in mapping.items()}',
     [('invert({"a": 1, "b": 2})', "{1: 'a', 2: 'b'}")]),
    ("dictkit", "merge_sum", "(a, b)", "Merge two int-valued dicts, summing shared keys.",
     '    out = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, 0) + v\n    return out',
     '    out = dict(a)\n    for k, v in b.items():\n        out[k] = v\n    return out',
     [('merge_sum({"x": 1, "y": 2}, {"y": 3, "z": 4})', "{'x': 1, 'y': 5, 'z': 4}")]),
    ("dictkit", "group_by_len", "(words)", "Group words by length into {len: [words]}.",
     '    out = {}\n    for w in words:\n        out.setdefault(len(w), []).append(w)\n    return out',
     '    out = {}\n    for w in words:\n        out[len(w)] = [w]\n    return out',
     [('group_by_len(["a", "bb", "cc", "d"])', "{1: ['a', 'd'], 2: ['bb', 'cc']}")]),
    ("dictkit", "pick", "(mapping, keys)", "Subset of mapping for keys that exist.",
     '    return {k: mapping[k] for k in keys if k in mapping}',
     '    return {k: mapping.get(k) for k in keys}',
     [('pick({"a": 1, "b": 2}, ["a", "z"])', "{'a': 1}")]),

    # ---- seqkit ----
    ("seqkit", "rle_encode", "(seq)", "Run-length encode into [(item, count), ...].",
     '    out = []\n    for x in seq:\n        if out and out[-1][0] == x:\n            out[-1] = (x, out[-1][1] + 1)\n        else:\n            out.append((x, 1))\n    return out',
     '    return [(x, 1) for x in seq]',
     [('rle_encode("aaabb")', "[('a', 3), ('b', 2)]")]),
    ("seqkit", "rotate", "(seq, k)", "Rotate list left by k (k may exceed len).",
     '    if not seq:\n        return list(seq)\n    k %= len(seq)\n    return list(seq[k:]) + list(seq[:k])',
     '    return list(seq[k:]) + list(seq[:k])',
     [('rotate([1,2,3,4,5], 2)', "[3, 4, 5, 1, 2]"), ('rotate([1,2,3], 4)', "[2, 3, 1]")]),
    ("seqkit", "pairwise_diff", "(values)", "Consecutive differences. [1,4,9] -> [3,5].",
     '    return [values[i+1] - values[i] for i in range(len(values) - 1)]',
     '    return [values[i+1] - values[i] for i in range(len(values))]',
     [('pairwise_diff([1,4,9,16])', "[3, 5, 7]")]),
]


def render_module(module, specs, buggy):
    lines = [f'"""{module} utilities."""', ""]
    for (_m, name, sig, doc, correct, bug, _t) in specs:
        body = bug if buggy else correct
        lines += [f"def {name}{sig}:", f'    """{doc}"""', body, ""]
    return "\n".join(lines) + "\n"


def render_tests(specs):
    by_mod = {}
    for s in specs:
        by_mod.setdefault(s[0], []).append(s[1])
    lines = ['"""Oracle suite for largelib. DO NOT EDIT - fix the modules until green."""']
    for mod, names in by_mod.items():
        lines.append(f"from largelib.{mod} import {', '.join(names)}")
    lines.append("")
    for i, (mod, name, sig, doc, correct, bug, tests) in enumerate(SPECS):
        lines.append(f"def test_{mod}_{name}():")
        for call, expected in tests:
            lines.append(f"    assert {call} == {expected}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_seed(root, buggy):
    pkg = os.path.join(root, "largelib")
    os.makedirs(pkg, exist_ok=True)
    open(os.path.join(pkg, "__init__.py"), "w").write('"""largelib"""\n')
    mods = {}
    for s in SPECS:
        mods.setdefault(s[0], []).append(s)
    for mod, specs in mods.items():
        open(os.path.join(pkg, f"{mod}.py"), "w").write(render_module(mod, specs, buggy))
    open(os.path.join(root, "test_largelib.py"), "w").write(render_tests(SPECS))
    return len(SPECS), len(mods)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--solution":
        n, m = write_seed(sys.argv[2], buggy=False)
        print(f"solution written to {sys.argv[2]} ({n} funcs, {m} modules)")
    else:
        n, m = write_seed(os.path.join(HERE, "seed"), buggy=True)
        print(f"buggy seed written ({n} funcs/{n} bugs, {m} modules)")


if __name__ == "__main__":
    main()
