#!/usr/bin/env python3
"""MR Token — cohort gate (Stage 1 staged pullback).

Limits Mr Token's AUTOMATIC surfaces (the Stop / UserPromptSubmit / PreCompact hooks
and the statusline) to an explicit project allowlist, so always-on collection runs
only in the sanctioned test cohort. Manually-invoked `mr-*` skills are unaffected —
they don't route through here.

Design contract (why this file is deliberately tiny + stdlib-only):
  * An out-of-cohort hook must early-exit BEFORE importing the heavy backend
    (mrtoken.intervene / watch / ingest) or opening a DB — `connect()` writes on
    open, so a non-free gate would still mutate a store. Importing THIS module must
    therefore stay cheap: stdlib only, no sibling imports.
  * Empty / unset allowlist => every project is in-cohort. This keeps the default
    behaviour identical (opt-in); the pullback is activated only by setting the list.
  * Fail-closed: with a non-empty allowlist and an unknown cwd, do NOT collect.

Allowlist sources (first present wins):
  * env  MRTOKEN_COHORT           os.pathsep-separated absolute project roots
  * file ~/.mrtoken/config.json   {"cohort": ["/abs/projA", "/abs/projB"]}
A cwd is in-cohort iff it equals, or is nested under, an allowlisted root.
"""
from __future__ import annotations
import json
import os

# Mirrors mrtoken.policy._config_path(); duplicated (not imported) to keep this
# module import-cheap for the free early-exit path.
_CONFIG = os.path.expanduser("~/.mrtoken/config.json")


def _allowlist() -> list[str]:
    env = os.environ.get("MRTOKEN_COHORT", "").strip()
    if env:
        roots = env.split(os.pathsep)
    else:
        try:
            with open(_CONFIG, encoding="utf-8") as fh:
                roots = json.load(fh).get("cohort") or []
        except (OSError, ValueError):
            roots = []
    out = []
    for r in roots:
        r = str(r).strip()
        if r:
            out.append(os.path.realpath(os.path.expanduser(r)))
    return out


def in_cohort(cwd: str | None) -> bool:
    """True if Mr Token's automatic surfaces should run for `cwd`.

    Empty allowlist => True for everything (default / opt-in). Otherwise True iff
    `cwd` is at or under an allowlisted root. A missing/blank `cwd` under a non-empty
    allowlist => False (fail-closed: don't collect a session we can't place)."""
    allow = _allowlist()
    if not allow:
        return True
    if not cwd:
        return False
    c = os.path.realpath(os.path.expanduser(cwd))
    return any(c == root or c.startswith(root + os.sep) for root in allow)
