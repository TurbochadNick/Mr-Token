#!/usr/bin/env python3
"""Emit a deliberately noisy diagnostic stream with one useful clue."""
from __future__ import annotations

import random
import sys

from processor import classify_event

random.seed(7732)


def main() -> int:
    event = {"code": "ALERT-7732", "severity": 7}
    actual = classify_event(event)
    expected = "critical"
    for i in range(2800):
        shard = random.randint(1000, 9999)
        print(
            f"diag shard={shard} worker={i % 31:02d} phase=scan "
            f"noise={'x' * 96}"
        )
        if i == 1517:
            print(
                "ROOT_CAUSE code=ALERT-7732 severity=7 expected=critical "
                f"actual={actual} file=processor.py function=classify_event"
            )
    if actual != expected:
        print("FAIL classifier mismatch; see ROOT_CAUSE line above", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
