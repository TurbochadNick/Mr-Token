#!/usr/bin/env python3
"""Replay real Claude transcripts through the compaction gate (5D.3 groundwork).

Feeds each transcript line through watch.LiveMonitor, then asks the gate what
it would say at end-of-transcript given pressure + context_rot. Point it at a
handoff arm's PHASE-1 transcript and the EOF is exactly the experiment's reset
point — the moment the 5A regime map measured a ~30% win (scanlib) or a ~20%
loss (speclib), so the output is a ground-truth check of Gate 1+2.

Usage:
    python3 backend/experiments/replay_gate.py <transcript.jsonl> [...]

Reads local transcripts only; prints hash-keyed metadata, never content.
Finding 2026-07-02 (see PR #19 discussion): at the real reset points, the
recency-only disposability proxy does NOT separate the regimes — scanlib and
one of two speclib phase-1 runs both classify ~all-disposable (singleton
reads, idle ~K turns). Keep this tool as the oracle for any Gate 1 redesign.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mrtoken.watch import LiveMonitor, K_DISPOSABLE_TURNS      # noqa: E402
from mrtoken.intervene import evaluate, _near_done             # noqa: E402


def replay(path: str) -> None:
    mon = LiveMonitor(emit=lambda _: None)
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                mon.feed(json.loads(ln))
            except json.JSONDecodeError:
                continue
    snap = mon.snapshot()
    disp, prog = snap["disposability"], snap["progress"]
    iv = evaluate(85, None, ["context_rot"], disposability=disp, progress=prog)

    disp_tok = lb_tok = 0
    rows = []
    for (tool, h), g in mon.read_groups.items():
        if not g.get("done"):
            continue
        since = mon.model_calls - g.get("last_call", mon.model_calls)
        lb = disp.get(f"{tool}:{h[:12]}") == "load_bearing"
        if lb:
            lb_tok += g["out_tok"]
        else:
            disp_tok += g["out_tok"]
        rows.append((g["out_tok"], g["req"], since, "LB" if lb else "DISP"))
    total = disp_tok + lb_tok
    share = disp_tok / total if total else 0

    name = os.path.basename(os.path.dirname(path)) + "/" + os.path.basename(path)[:8]
    print(f"== {name}")
    print(f"   calls={snap['model_calls']} ctx={snap['context_now'] // 1000}k "
          f"blocks={dict(Counter(disp.values()))} near_done={_near_done(prog)} "
          f"K={K_DISPOSABLE_TURNS}")
    print(f"   disposable_share={share:.0%} ({disp_tok:,}/{total:,} tok) "
          f"→ gate says: {(iv or {}).get('tool')}")
    for tok, req, since, v in sorted(rows, reverse=True)[:6]:
        print(f"     {v:4} tok={tok:>7,} req={req} since={since}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        replay(p)
