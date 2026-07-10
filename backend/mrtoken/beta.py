#!/usr/bin/env python3
"""MR Token beta-loop helpers."""
from __future__ import annotations

import os
import subprocess

from mrtoken import __version__
from mrtoken.update_check import _repo_root


def repo_url(root: str | None = None) -> str:
    root = root or _repo_root() or os.getcwd()
    try:
        out = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=2)
        url = out.stdout.strip()
        return url or "<repo-url>"
    except Exception:
        return "<repo-url>"


def beta_note(url: str | None = None, version: str | None = None) -> str:
    url = url or repo_url()
    version = version or __version__
    return f"""I am testing MR Token v{version}, a local-first token-efficiency HUD for Claude Code and Codex.

Install:

git clone {url} mr_token
cd mr_token
./install.sh
mrtoken-transcript doctor

Then use Claude Code or Codex normally for 3 to 5 days.

What you should see:
- Claude Code terminal: an `mr` status line with context %, estimated cost, profile, and short nudges.
- Codex: a compact Stop-hook line like `mr · codex gpt-5.6-terra · ctx 28% · ~681k tok · cache 96% · code · long session: /mr-handoff at phase boundary`.
- `/mr-status`, `/mr-why`, and `/mr-handoff` available in Claude Code sessions.

Privacy:
MR Token is local-first. It stores metadata only: token counts, cache ratios, tool names, sizes, timings, cost estimates, and which rules fired. It does not store prompts, source files, full transcripts, or secrets by default. Nothing is sent automatically.

While using it, mark useful or noisy nudges when convenient:

mrtoken-transcript feedback <session-prefix> <rule> right|wrong|unsure --note "short note"

After a few days, send back:

mrtoken-transcript export --redact > mrtoken-beta.json
mrtoken-transcript doctor --bundle

Please open both files before sending if you want to inspect exactly what is included.

Also answer these three questions:
1. Did the HUD ever change what you actually did in a session, such as compacting early, handing off, or stopping a retry loop?
2. Was anything confusing, noisy, or easy to ignore?
3. Would you keep it installed? If you turned it off, what made you?

Turn it off any time:

mrtoken-transcript uninstall"""
