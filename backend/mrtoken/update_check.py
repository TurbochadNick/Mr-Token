#!/usr/bin/env python3
"""MR Token — lightweight "update available" check.

Compares the installed version to the latest release tag on the git remote and
returns a one-line nudge when behind. No license server, no telemetry: it asks
`git` (the user's own clone + auth) for tags. Throttled to once/day, bounded by a
short timeout, and SILENT on any failure (no git, offline, zip install, etc.), so
it never slows or breaks a command.
"""
from __future__ import annotations
import json, os, re, subprocess, time

from mrtoken import __version__

_CACHE = os.path.expanduser("~/.mrtoken/update-check.json")
_TTL_SECONDS = 24 * 3600
_NET_TIMEOUT = 3


def _semver(s: str) -> tuple[int, int, int] | None:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (s or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def update_nudge(local: str, latest: str | None) -> str | None:
    """Pure: a nudge string if `latest` tag is newer than `local`, else None."""
    if not latest:
        return None
    lv, rv = _semver(local), _semver(latest)
    if lv and rv and rv > lv:
        return f"↑ update available: {latest} (you have v{local}) — run `mrtoken-transcript update`"
    return None


def _repo_root() -> str | None:
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def _latest_remote_tag(root: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-remote", "--tags", "origin"],
            capture_output=True, text=True, timeout=_NET_TIMEOUT).stdout
    except Exception:
        return None
    best = None
    for line in out.splitlines():
        m = re.search(r"refs/tags/(v?\d+\.\d+\.\d+)(?:\^\{\})?$", line)
        sv = _semver(m.group(1)) if m else None
        if sv and (best is None or sv > best[0]):
            best = (sv, m.group(1))
    return best[1] if best else None


def check_for_update(now: float | None = None) -> str | None:
    """Return an 'update available' nudge if a newer release tag exists, else None.
    Network check throttled to once/day via ~/.mrtoken/update-check.json; silent
    on any failure."""
    now = now if now is not None else time.time()
    cache: dict = {}
    try:
        with open(_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}

    if now - cache.get("checked_at", 0) < _TTL_SECONDS:
        latest = cache.get("latest")
    else:
        root = _repo_root()
        latest = _latest_remote_tag(root) if root else None
        try:
            os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
            with open(_CACHE, "w", encoding="utf-8") as f:
                json.dump({"checked_at": now, "latest": latest}, f)
        except Exception:
            pass

    return update_nudge(__version__, latest)
