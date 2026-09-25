#!/usr/bin/env python3
"""MR Token — continuation manifest: state DECLARED by the agent, never inferred.

Why this exists. `handoff` run against a real 830,000-token session returned 1,919 bytes
carrying ONE of the six facts a continuation actually needs (active patch identity, custody
HEAD, dirty count, held slice, reviewer corrections, reproduced defect). All six existed in
the transcript — as free prose. Mining conversational English for hashes and "NOT GO" is a
heuristic that is silently wrong the day the wording changes, so it was declined.

Instead the agent DECLARES a small structured manifest and handoff reads it verbatim.

Storage. One JSON file per session, project-local and ignored, under the store the product
already has: `<data_dir>/manifest/<session_id>.json`, where `<data_dir>` is
`datadir.resolve_data_dir()` (normally `<project>/.token-tithe/`). There is deliberately NO
global cross-project store: binding is structural (the file lives in the caller's project)
AND explicit (the manifest names its project root and session id, so a copied file is
detected).

Freshness and verification. On read, handoff compares the declared project root and session
id to the caller's (mismatch -> facts WITHHELD, mismatch named), re-hashes every artifact
that declares a sha256 (mismatch or missing file -> named), and re-reads repository HEAD and
dirty count read-only (mismatch -> named, declared vs observed). A field the agent did not
declare is rendered as a NAMED GAP, never filled by a guess or a summary.

Nothing here reads the environment for a session id, and nothing here falls back to a
newest session: the session id is whatever `build_handoff` already resolved.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from mrtoken.datadir import resolve_data_dir, locate_project_root, _norm
from mrtoken.watch import valid_session_id

SCHEMA_VERSION = 1
# How much older than the transcript's last write a manifest may be before it is flagged.
STALE_AFTER_S = 30 * 60

# The declared-state schema: field -> (kind, one-line meaning). `kind` drives rendering and
# gap detection; the meaning is what a gap line says so a reader knows what to go and get.
FIELDS: dict[str, tuple[str, str]] = {
    "objective":            ("text", "current objective"),
    "artifacts":            ("list", "active artifacts/patches (path, role, sha256)"),
    "custody":              ("custody", "repository custody (HEAD, dirty count, held changes)"),
    "decisions":            ("list", "decisions and constraints"),
    "reviewer_corrections": ("list", "reviewer corrections and their status"),
    "evidence":             ("list", "reproduced defects / latest decisive evidence"),
    "gates":                ("list", "open gates and holds"),
    "next_action":          ("text", "immediate next action"),
    "do_not_redo":          ("list", "do-not-redo evidence"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _git(repo: str, *args: str) -> str | None:
    """Read-only git query; None when git or the repo is unavailable. Never mutates."""
    try:
        out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def observe_custody(repo: str) -> dict:
    """What the repository says RIGHT NOW: HEAD and dirty count, or None for each when
    unobservable. Used only to check a declaration, never to fill one in."""
    head = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain", "-uall")
    return {"head": head.strip() if head else None,
            "dirty_count": len([l for l in status.splitlines() if l.strip()])
            if status is not None else None}


# ---- schema validation --------------------------------------------------------------
# Applied at BOTH boundaries: `declare_manifest` refuses an invalid declaration, and
# `verify_manifest` names every invalid field it finds in a hand-authored or corrupted file.
# Nothing downstream assumes a nested type without this having checked it first.

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_str_or_none(name, v, out):
    if v is not None and not isinstance(v, str):
        out[name] = f"expected string or null, got {type(v).__name__}"


def validate_fields(m: dict) -> dict[str, str]:
    """{field path: reason} for every declared-state field with an invalid shape.
    Only the FIELDS keys are checked here; binding/schema/updated_at are checked in verify."""
    bad: dict[str, str] = {}
    for key, (kind, _) in FIELDS.items():
        v = m.get(key)
        if v is None:
            continue
        if kind == "text":
            _check_str_or_none(key, v, bad)
        elif kind == "list":
            if not isinstance(v, list):
                bad[key] = f"expected list or null, got {type(v).__name__}"
                continue
            for i, item in enumerate(v):
                at = f"{key}[{i}]"
                if key == "artifacts":
                    if not isinstance(item, dict):
                        bad[at] = f"expected object {{path, role, sha256}}, got {type(item).__name__}"
                        continue
                    if not isinstance(item.get("path"), str) or not item.get("path"):
                        bad[f"{at}.path"] = "expected non-empty string"
                    _check_str_or_none(f"{at}.role", item.get("role"), bad)
                    sha = item.get("sha256")
                    if sha is not None and not (isinstance(sha, str) and _HEX64.match(sha)):
                        bad[f"{at}.sha256"] = "expected 64 lowercase hex chars or null"
                elif isinstance(item, dict):
                    if not isinstance(item.get("text"), str) or not item.get("text"):
                        bad[f"{at}.text"] = "expected non-empty string"
                    _check_str_or_none(f"{at}.status", item.get("status"), bad)
                elif not isinstance(item, str):
                    bad[at] = f"expected string or {{text, status}} object, got {type(item).__name__}"
        elif kind == "custody":
            if not isinstance(v, dict):
                bad[key] = f"expected object {{repo, head, dirty_count, held}}, got {type(v).__name__}"
                continue
            _check_str_or_none("custody.repo", v.get("repo"), bad)
            head = v.get("head")
            if head is not None and not (isinstance(head, str) and _HEX40.match(head)):
                bad["custody.head"] = "expected 40 lowercase hex chars or null"
            dc = v.get("dirty_count")
            if dc is not None and not (_is_int(dc) and dc >= 0):
                bad["custody.dirty_count"] = f"expected non-negative integer or null, got {dc!r}"
            held = v.get("held")
            if held is not None:
                if not isinstance(held, list):
                    bad["custody.held"] = f"expected list of strings or null, got {type(held).__name__}"
                else:
                    for i, h in enumerate(held):
                        if not isinstance(h, str):
                            bad[f"custody.held[{i}]"] = f"expected string, got {type(h).__name__}"
    return bad


# ---- store ----------------------------------------------------------------------------

def manifest_path(session_id: str, cwd: str | None = None) -> str | None:
    """`<data_dir>/manifest/<session_id>.json` for THIS project, or None for an unsafe id.
    The id is a single path component (same rule as transcript resolution) so it can never
    escape the manifest directory."""
    if not valid_session_id(session_id):
        return None
    return os.path.join(resolve_data_dir(cwd), "manifest", f"{session_id}.json")


def bound_project_root(cwd: str | None = None) -> str:
    return os.path.realpath(locate_project_root(cwd) or _norm(cwd))


def load_manifest(session_id: str, cwd: str | None = None) -> tuple[dict | None, str | None]:
    """(manifest, None) when a readable JSON object exists; (None, None) when there is
    genuinely no file; (None, problem) when a file EXISTS but cannot be used. Absence and
    corruption are different facts and are never collapsed into each other."""
    p = manifest_path(session_id, cwd)
    if not p:
        return None, f"INVALID session id {session_id!r}: no manifest path"
    if not os.path.exists(p):
        return None, None
    try:
        with open(p, encoding="utf-8") as fh:
            m = json.load(fh)
    except OSError as e:
        return None, f"UNREADABLE manifest at {p}: {e.strerror or e}"
    except ValueError as e:
        return None, f"CORRUPT manifest at {p}: invalid JSON ({e})"
    if not isinstance(m, dict):
        return None, f"CORRUPT manifest at {p}: top level is not a JSON object"
    return m, None


def read_manifest(session_id: str, cwd: str | None = None) -> dict | None:
    """Back-compat convenience: the manifest or None. Callers that must distinguish
    absence from corruption use `load_manifest`."""
    return load_manifest(session_id, cwd)[0]


def declare_manifest(session_id: str, fields: dict, cwd: str | None = None,
                     merge: bool = True) -> str:
    """Write (or update) the manifest for `session_id` in THIS project's store.

    `fields` holds any subset of FIELDS. With `merge`, undeclared fields keep their previous
    value; an explicit `None` clears one back to a gap. Every field is shape-validated and an
    invalid declaration is refused naming the field. Binding fields are always rewritten from
    the caller's project root and the given session id — a declaration cannot claim a
    different project."""
    p = manifest_path(session_id, cwd)
    if not p:
        raise ValueError(f"unsafe session id: {session_id!r}")
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown manifest field(s): {sorted(unknown)}")
    current, err = load_manifest(session_id, cwd) if merge else (None, None)
    if err:
        raise ValueError(f"cannot merge into existing manifest — {err}")
    body = {k: current.get(k) for k in FIELDS} if current else {k: None for k in FIELDS}
    body.update(fields)
    # Validate the COMPLETED body — incoming and retained fields alike — before any write.
    # Checking only the delta let a schema-invalid value already on disk ride through a
    # valid merge and be rewritten as if approved (rereview 2, 2026-09-17). Every invalid
    # path is named and labelled by origin; nothing is written.
    bad = validate_fields(body)
    if bad:
        def origin(path):
            top = path.split("[")[0].split(".")[0]
            return "incoming" if top in fields else "retained"
        raise ValueError("invalid manifest field(s): " + "; ".join(
            f"{k} ({origin(k)}): {v}" for k, v in sorted(bad.items())))
    m = {"schema_version": SCHEMA_VERSION, "updated_at": _now(),
         "binding": {"project_root": bound_project_root(cwd), "session_id": session_id},
         **body}
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, p)
    return p


# ---- verification ---------------------------------------------------------------------

def verify_manifest(m: dict, session_id: str, transcript_path: str | None = None,
                    cwd: str | None = None, transcript_mtime: float | None = None) -> dict:
    """Check a manifest against what can be observed. Returns
    {"bound": bool, "problems": [str], "invalid": {path: reason},
     "artifacts": [...], "custody": {...}}.

    `bound` is False on a project/session mismatch or a schema we do not understand: the
    caller must then WITHHOLD the declared facts and print only the problems. Everything
    else (invalid shape, stale, missing artifact, hash/HEAD/dirty mismatch) is surfaced
    beside the fact. Nothing below touches a nested value that `validate_fields` did not
    approve."""
    problems: list[str] = []
    bound = True

    if m.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"MISMATCH schema_version: declared {m.get('schema_version')!r}, "
                        f"this build reads {SCHEMA_VERSION}")
        bound = False
    b = m.get("binding") if isinstance(m.get("binding"), dict) else {}
    want_root = bound_project_root(cwd)
    got_root = b.get("project_root")
    if not isinstance(got_root, str) or not got_root or os.path.realpath(got_root) != want_root:
        problems.append(f"MISMATCH project: manifest declares {got_root!r}, "
                        f"caller project is {want_root!r}")
        bound = False
    if b.get("session_id") != session_id:
        problems.append(f"MISMATCH session: manifest declares {b.get('session_id')!r}, "
                        f"handoff is for {session_id!r}")
        bound = False
    if not bound:
        return {"bound": False, "problems": problems, "invalid": {}, "artifacts": [], "custody": {}}

    invalid = validate_fields(m)
    for k in sorted(invalid):
        problems.append(f"INVALID {k}: {invalid[k]}")

    # freshness: the manifest should not be much older than the session's last write
    upd = m.get("updated_at")
    upd_ts = None
    if isinstance(upd, str):
        try:
            upd_ts = datetime.fromisoformat(upd).timestamp()
        except ValueError:
            upd_ts = None
    if upd_ts is None:
        problems.append("GAP updated_at: not declared or unparseable")
    elif transcript_mtime is not None or (transcript_path and os.path.isfile(transcript_path)):
        # an mtime taken from an already-opened file wins: re-stat'ing the NAME could see a
        # different file swapped in since, and hide a required STALE warning
        written = transcript_mtime if transcript_mtime is not None else os.path.getmtime(transcript_path)
        lag = written - upd_ts
        if lag > STALE_AFTER_S:
            problems.append(f"STALE manifest: declared at {upd}, transcript last written "
                            f"{int(lag // 60)} min later — re-declare before trusting")

    # artifacts: one row per declared entry, in order; invalid entries are NAMED, never dropped
    arts_out = []
    arts = m.get("artifacts")
    if isinstance(arts, list):
        for i, a in enumerate(arts):
            at = f"artifacts[{i}]"
            entry_bad = {k: v for k, v in invalid.items() if k == at or k.startswith(at + ".")}
            if entry_bad:
                arts_out.append({"index": i, "path": a.get("path") if isinstance(a, dict) else None,
                                 "role": None, "sha256": None,
                                 "status": "INVALID " + "; ".join(
                                     f"{k}: {v}" for k, v in sorted(entry_bad.items()))})
                continue
            path, role, declared = a.get("path"), a.get("role"), a.get("sha256")
            status = "unverified (no sha256 declared)"
            if not os.path.isfile(path):
                status = "MISSING on disk"
            elif declared:
                observed = _sha256_file(path)
                status = ("verified" if observed == declared else
                          f"HASH MISMATCH: declared {declared}, observed {observed or 'unreadable'}")
            arts_out.append({"index": i, "path": path, "role": role, "sha256": declared,
                             "status": status})

    # custody: compare only VALID declared fields to a read-only observation
    c = m.get("custody")
    cust_out: dict = {}
    if isinstance(c, dict) and "custody" not in invalid:
        repo = c.get("repo") if "custody.repo" not in invalid and c.get("repo") else want_root
        obs = observe_custody(repo)
        cust_out = {"repo": repo, "declared": c, "observed": obs, "problems": []}
        head_ok = "custody.head" not in invalid
        dc_ok = "custody.dirty_count" not in invalid
        if head_ok and c.get("head") is not None and obs["head"] is not None \
                and c["head"] != obs["head"]:
            cust_out["problems"].append(
                f"HEAD MISMATCH: declared {c['head']}, observed {obs['head']}")
        if dc_ok and c.get("dirty_count") is not None and obs["dirty_count"] is not None \
                and c["dirty_count"] != obs["dirty_count"]:
            cust_out["problems"].append(
                f"DIRTY COUNT MISMATCH: declared {c['dirty_count']}, observed {obs['dirty_count']}")
        if obs["head"] is None:
            cust_out["problems"].append(f"UNVERIFIED: could not read HEAD of {repo}")
    return {"bound": True, "problems": problems, "invalid": invalid,
            "artifacts": arts_out, "custody": cust_out}


# ---- rendering ------------------------------------------------------------------------

def _item_text(item) -> str:
    if isinstance(item, dict):
        st = item.get("status")
        return item.get("text", "") + (f" — {st}" if st else "")
    return str(item)


def render_section(m: dict | None, v: dict | None, load_error: str | None = None) -> list[str]:
    """Markdown lines for the handoff. Every undeclared field is a NAMED GAP; an unusable
    file is named as corrupt/unreadable, never as absent; an invalid field is named INVALID
    and its value is not shown as if it were a fact."""
    out = ["## Declared state (continuation manifest)"]
    if load_error:
        out.append(f"- {load_error} — declared facts cannot be read; re-declare. "
                   "This is NOT an absence of declaration.")
        out.append("")
        return out
    if m is None:
        out.append("- GAP: no manifest declared for this session — the facts below were "
                   "never declared: " + "; ".join(FIELDS[k][1] for k in FIELDS))
        out.append("")
        return out
    assert v is not None
    if not v["bound"]:
        out.append("- WITHHELD: manifest is not bound to this project/session; declared "
                   "facts are not shown.")
        for p in v["problems"]:
            out.append(f"- {p}")
        out.append("")
        return out
    out.append(f"_declared {m.get('updated_at')}_")
    for p in v["problems"]:
        out.append(f"- {p}")
    invalid = v.get("invalid", {})

    for key, (kind, meaning) in FIELDS.items():
        val = m.get(key)
        if key in invalid:                      # whole field is the wrong shape
            out.append(f"- **{meaning}:** INVALID — {invalid[key]}; not shown")
            continue
        if kind == "text":
            out.append(f"- **{meaning}:** {val if val else f'GAP — {meaning} not declared'}")
        elif kind == "list":
            if not val:
                out.append(f"- **{meaning}:** GAP — not declared")
                continue
            out.append(f"- **{meaning}:**")
            if key == "artifacts":
                for a in v["artifacts"]:
                    if a["status"].startswith("INVALID"):
                        out.append(f"  - {a['status']}")
                        continue
                    sha = f" sha256 {a['sha256']}" if a.get("sha256") else ""
                    out.append(f"  - `{a['path']}` ({a.get('role') or 'role?'}){sha} — {a['status']}")
            else:
                for i, item in enumerate(val):
                    at = f"{key}[{i}]"
                    bad = {k: r for k, r in invalid.items() if k == at or k.startswith(at + ".")}
                    if bad:
                        out.append("  - INVALID " + "; ".join(f"{k}: {r}" for k, r in sorted(bad.items())))
                    else:
                        out.append(f"  - {_item_text(item)}")
        elif kind == "custody":
            if not val:
                out.append(f"- **{meaning}:** GAP — not declared")
                continue
            c = v["custody"]
            d = c.get("declared", {})
            head = d.get("head") if "custody.head" not in invalid else None
            dc = d.get("dirty_count") if "custody.dirty_count" not in invalid else None
            out.append(f"- **{meaning}:** repo `{c.get('repo')}` · HEAD "
                       f"{head if head else 'GAP — not declared'} · dirty "
                       f"{dc if dc is not None else 'GAP — not declared'}")
            for p in c.get("problems", []):
                out.append(f"  - {p}")
            held = d.get("held") if "custody.held" not in invalid else None
            if held:
                for i, h in enumerate(held):
                    if f"custody.held[{i}]" in invalid:
                        out.append(f"  - INVALID custody.held[{i}]: {invalid[f'custody.held[{i}]']}")
                    else:
                        out.append(f"  - held: {h}")
            else:
                out.append("  - held changes: GAP — not declared")
    out.append("")
    return out
