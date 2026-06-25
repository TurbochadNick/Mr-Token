#!/usr/bin/env python3
"""MR Token — data directory resolution (Python side of the shared contract).

This is the ONE place the Python backend decides where token-tithe.db lives. The
TypeScript CLI implements the IDENTICAL algorithm in src/utils/paths.ts. The
contract is documented in backend/docs/DATA-DIR.md — change both sides together.

Resolution (highest precedence first):
  1. explicit path argument (--db / --events)                  -> use as given
  2. env DB override: TOKEN_TITHE_DB or MRTOKEN_DB              -> use as given
  3. MRTOKEN_DATA_DIR set (full-central opt-in)                -> <it>/projects/<key>
  4. cwd is inside a real project (has .git/package.json/pyproject.toml)
                                                               -> <project>/.token-tithe  (default; privacy)
  5. cwd is NOT a project (the old scatter bug)                -> <central>/projects/<key>
                                                                  (NEVER write into cwd)

<central> default = $XDG_DATA_HOME/token-tithe, else ~/.mrtoken/data
<key>     = stable per-project slug+hash so each project keeps its own DB.
"""
from __future__ import annotations
import hashlib, os, re

MARKERS = (".git", "package.json", "pyproject.toml")


def _norm(path: str | None) -> str:
    p = os.path.abspath(path or os.getcwd())
    return p.rstrip(os.sep) or os.sep


def locate_project_root(start: str | None = None) -> str | None:
    """Nearest ancestor with a project marker, or None if cwd is not a project."""
    current = _norm(start)
    while True:
        if any(os.path.exists(os.path.join(current, m)) for m in MARKERS):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_project_root(start: str | None = None) -> str:
    """Back-compat: the project root if found, else the normalized start dir."""
    return locate_project_root(start) or _norm(start)


def project_key(path: str) -> str:
    """Stable key for a project/cwd path. MUST match the TS implementation:
    basename (lowercased, non-alnum -> '-', stripped) + '-' + sha256(abspath)[:8]."""
    abs_path = _norm(path)
    slug = re.sub(r"[^a-z0-9]+", "-", os.path.basename(abs_path).lower()).strip("-") or "root"
    digest = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def central_default() -> str:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return os.path.join(xdg, "token-tithe")
    return os.path.expanduser(os.path.join("~", ".mrtoken", "data"))


def _db_env_override() -> str | None:
    return os.environ.get("TOKEN_TITHE_DB") or os.environ.get("MRTOKEN_DB")


def codex_db_path() -> str:
    """ONE central DB for all Codex sessions. Unlike Claude (you usually live in one
    repo, so per-project is fine), Codex sessions sprawl across many working dirs —
    a per-project DB scatters them and no single `fleet` ever sees them together. So
    aggregate Codex centrally instead. (MRTOKEN_DB still overrides where set.)"""
    return os.path.join(central_default(), "codex.db")


def resolve_data_dir(cwd: str | None = None) -> str:
    """Directory holding token-tithe.db + events.jsonl for this cwd (per contract)."""
    data_dir_env = os.environ.get("MRTOKEN_DATA_DIR")
    root = locate_project_root(cwd)
    if data_dir_env:  # full-central opt-in: every project under one home, keyed
        return os.path.join(data_dir_env, "projects", project_key(root or _norm(cwd)))
    if root:  # default: per-project (keeps the local-first privacy story)
        return os.path.join(root, ".token-tithe")
    # non-project fallback: never scatter into cwd -> central default, keyed by cwd
    return os.path.join(central_default(), "projects", project_key(_norm(cwd)))


def resolve_db_path(cwd: str | None = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = _db_env_override()
    if env:
        return env
    return os.path.join(resolve_data_dir(cwd), "token-tithe.db")


def resolve_events_path(cwd: str | None = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return os.path.join(resolve_data_dir(cwd), "events.jsonl")
