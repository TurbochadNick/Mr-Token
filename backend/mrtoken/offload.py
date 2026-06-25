#!/usr/bin/env python3
"""MR Token — `offload`: the first toolbox tool (ROADMAP 6.1).

The single highest-leverage move against "running out of context on junk": instead
of reading a huge file/output into context, the agent calls `offload` — the full
content is written to disk and only a compact summary + a stash path come back, so
the bulk never enters (or leaves) the context window. The agent can grep/read the
stash later for specifics.

Pure stdlib; metadata-light (the stash is local, never sent anywhere). Exposed to
the agent as an MCP tool (see mcp_server.py), but the capability is a plain function
so it's testable without the transport.
"""
from __future__ import annotations
import hashlib, os

from mrtoken.datadir import central_default

DEFAULT_MAX_LINES = 40


def _stash_dir(override: str | None = None) -> str:
    return override or os.path.join(central_default(), "offload")


def offload_content(content: str | None = None, path: str | None = None,
                    query: str | None = None, max_lines: int = DEFAULT_MAX_LINES,
                    stash_dir: str | None = None) -> dict:
    """Stash large content out of context, return a compact summary + stash path.

    Give `content` (raw text) or `path` (a file to summarize instead of reading whole).
    `query` returns only matching lines (a grep); otherwise a head+tail digest.
    """
    if path:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        origin = path
    elif content is not None:
        text, origin = content, "inline content"
    else:
        raise ValueError("offload needs `content` or `path`")

    sd = _stash_dir(stash_dir)
    os.makedirs(sd, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]
    stash_path = os.path.join(sd, f"{digest}.txt")
    with open(stash_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    lines = text.splitlines()
    n, nbytes = len(lines), len(text.encode("utf-8", "replace"))
    max_lines = max(4, int(max_lines or DEFAULT_MAX_LINES))

    if query:
        hits = [f"{i + 1}: {ln}" for i, ln in enumerate(lines) if query.lower() in ln.lower()]
        shown = hits[:max_lines]
        body = "\n".join(shown) if shown else "(no matching lines)"
        more = f"  (+{len(hits) - len(shown)} more matches)" if len(hits) > len(shown) else ""
        header = f"{n:,} lines / {nbytes:,} bytes from {origin} — {len(hits)} line(s) matching {query!r}:{more}"
    elif n <= max_lines:
        body = "\n".join(lines)
        header = f"{n:,} lines / {nbytes:,} bytes from {origin}:"
    else:
        half = max_lines // 2
        head, tail = lines[:half], lines[-half:]
        omitted = n - len(head) - len(tail)
        body = "\n".join(head + [f"… ({omitted:,} lines omitted) …"] + tail)
        header = f"{n:,} lines / {nbytes:,} bytes from {origin} (head+tail; full on disk):"

    summary = header + "\n" + body
    est_tokens_saved = max(0, nbytes // 4 - len(summary) // 4)
    return {"summary": summary, "stash_path": stash_path, "lines": n, "bytes": nbytes,
            "est_tokens_saved": est_tokens_saved}


# MCP tool definition (consumed by mcp_server.py + agent clients)
OFFLOAD_TOOL = {
    "name": "offload",
    "description": (
        "Stash a large tool output or file OUT of context: writes the full content to disk and "
        "returns only a compact summary + a stash path you can grep/read later. Use this INSTEAD "
        "of reading a big file or pasting a big command output into context, so you don't run out "
        "of context. Give `content` (raw text) or `path` (a file)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "raw text to offload (e.g. a large command output)"},
            "path": {"type": "string", "description": "a file to summarize + stash instead of reading it whole"},
            "query": {"type": "string", "description": "optional: only return lines matching this (a grep)"},
            "max_lines": {"type": "integer", "description": f"max summary lines (default {DEFAULT_MAX_LINES})"},
        },
    },
}
