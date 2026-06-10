#!/usr/bin/env python3
"""MR Token — one-shot data migration for the scatter bug.

The old per-cwd resolution dropped `.token-tithe/` wherever an agent ran,
including non-project dirs (~, ~/Documents, ~/Downloads, ~/Music/...). This
finds every `.token-tithe/token-tithe.db`, classifies it, and relocates the
NON-PROJECT (scattered) ones into the central store, keyed by their location.

Legit per-project DBs (a `.token-tithe/` inside a real project) are the correct
default location under the new contract and are LEFT IN PLACE.

Default is a dry-run report. `--apply` moves files (never merges/overwrites: if a
central destination already exists, it is reported as a conflict and skipped, so
no data is ever lost).
"""
from __future__ import annotations
import os, shutil

from mrtoken.datadir import locate_project_root, project_key, central_default

PRUNE = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".cache",
         "site-packages", "Library"}


def find_dbs(home: str | None = None, max_depth: int = 6) -> list[dict]:
    home = os.path.abspath(home or os.path.expanduser("~"))
    central = os.path.abspath(central_default())
    base_depth = home.rstrip(os.sep).count(os.sep)
    found = []
    for dirpath, dirnames, _files in os.walk(home):
        if (dirpath.count(os.sep) - base_depth) >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in PRUNE]
        if os.path.abspath(dirpath).startswith(central):
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) == ".token-tithe":
            dirnames[:] = []  # don't descend into the data dir
            db = os.path.join(dirpath, "token-tithe.db")
            if os.path.isfile(db):
                parent = os.path.dirname(dirpath)
                is_project = locate_project_root(parent) is not None
                found.append({"db": db, "data_dir": dirpath, "parent": parent,
                              "is_project": is_project})
    return found


def _dest_for(parent: str) -> str:
    return os.path.join(central_default(), "projects", project_key(parent))


def migrate(apply: bool = False, home: str | None = None, emit=print) -> int:
    found = find_dbs(home)
    if not found:
        emit("mrtoken migrate-data: no .token-tithe databases found."); return 0

    projects = [f for f in found if f["is_project"]]
    scatter = [f for f in found if not f["is_project"]]

    emit(f"mrtoken migrate-data {'(APPLY)' if apply else '(dry-run — use --apply to relocate)'}")
    emit(f"  found {len(found)} database(s): {len(projects)} in real projects (kept), "
         f"{len(scatter)} scattered (to relocate)\n")

    for f in projects:
        emit(f"  keep   {f['data_dir']}  (inside project {f['parent']})")

    moved = conflicts = 0
    for f in scatter:
        dest_dir = _dest_for(f["parent"])
        dest_db = os.path.join(dest_dir, "token-tithe.db")
        if os.path.exists(dest_db):
            conflicts += 1
            emit(f"  CONFLICT {f['db']}  ->  {dest_db} already exists; skipped (resolve manually)")
            continue
        if not apply:
            emit(f"  move   {f['db']}  ->  {dest_db}")
            continue
        os.makedirs(dest_dir, exist_ok=True)
        for name in os.listdir(f["data_dir"]):  # move db + events.jsonl + anything else
            shutil.move(os.path.join(f["data_dir"], name), os.path.join(dest_dir, name))
        try:
            os.rmdir(f["data_dir"])  # remove the now-empty stray .token-tithe
        except OSError:
            pass
        moved += 1
        emit(f"  moved  {f['db']}  ->  {dest_db}")

    emit("")
    if apply:
        emit(f"  relocated {moved} scattered database(s); {conflicts} conflict(s) skipped.")
    else:
        emit(f"  {len(scatter)} scattered database(s) would be relocated"
             f"{f', {conflicts} conflict(s)' if conflicts else ''}. Re-run with --apply.")
    return 0
