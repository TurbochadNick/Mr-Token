#!/usr/bin/env python3
"""MR Token — ROI experiment runner (scaffold).

Drives a task through one arm (continue / compact / handoff), checks the oracle,
and records exact token cost. See ../docs/ROI-EXPERIMENT.md.

WHAT WORKS NOW (no API):
    python3 runner.py tasks/debug-stringkit --check-fixture
        Copies the seed, runs the oracle, and confirms it FAILS on the buggy seed
        (and that the harness can detect immutable-file tampering). Validates the
        oracle + recorder plumbing before any agent is wired.

WHAT IS STUBBED (the next build): drive_agent() — the live-agent seam.
"""
from __future__ import annotations
import argparse, json, os, shutil, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DB = os.path.join(HERE, "results", "results.db")

RESULTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
  id            INTEGER PRIMARY KEY,
  task_id       TEXT NOT NULL,
  arm           TEXT NOT NULL,        -- continue | compact | handoff
  rep           INTEGER NOT NULL,
  model         TEXT,
  effort        TEXT,
  completed     INTEGER NOT NULL,     -- oracle passed? (the quality gate)
  total_tokens  INTEGER,              -- exact, from the agent transcript
  est_cost_usd  REAL,
  wall_clock_s  REAL,
  steps         INTEGER,
  tool_errors   INTEGER,
  reset_fired   INTEGER,              -- did the arm hit the reset point?
  peak_input_tokens INTEGER,          -- input-side tokens reached before reset (5A.2)
  crossed_threshold INTEGER,          -- did it genuinely cross reset_threshold_tokens?
  notes         TEXT,
  created_at    TEXT NOT NULL
);
"""


def load_manifest(task_dir: str) -> dict:
    with open(os.path.join(task_dir, "manifest.json")) as f:
        return json.load(f)


def prepare_workdir(task_dir: str, manifest: dict) -> str:
    work = tempfile.mkdtemp(prefix=f"mrtoken-exp-{manifest['id']}-")
    shutil.copytree(os.path.join(task_dir, manifest["seed_dir"]), work, dirs_exist_ok=True)
    return work


def run_oracle(task_dir: str, manifest: dict, work: str) -> tuple[bool, str]:
    oracle = os.path.join(task_dir, manifest["oracle"])
    seed = os.path.join(task_dir, manifest["seed_dir"])
    proc = subprocess.run(["bash", oracle, work, seed], capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def _read_prompt(task_dir: str, manifest: dict) -> str:
    with open(os.path.join(task_dir, manifest["prompt_file"])) as f:
        return f.read()


def _run_claude(prompt: str, work: str, model: str, budget_usd: float,
                resume_sid: str | None = None, max_turns: int | None = None) -> dict:
    """One headless `claude -p` invocation in `work`. Returns parsed JSON result
    ({session_id, total_cost_usd, usage, num_turns, ...})."""
    # bypassPermissions: the agent runs autonomously (edit + bash) in a throwaway
    # temp working dir, so it must not prompt. Safe because each run is sandboxed
    # to a fresh copy of the task seed.
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json",
           "--max-budget-usd", str(budget_usd), "--permission-mode", "bypassPermissions"]
    if resume_sid:
        cmd += ["--resume", resume_sid]
    if max_turns:
        cmd += ["--max-turns", str(max_turns)]
    proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=3600)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_error": (proc.stdout + proc.stderr)[:500], "_rc": proc.returncode}


def _measure(session_id: str, work: str) -> dict:
    """Exact tokens for a session via the backend transcript parser (our instrument)."""
    from mrtoken.ingest import connect, load_prices, ingest_file
    import glob, tempfile as _tf
    esc = work.replace("/", "-").replace(".", "-")
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/{esc}/{session_id}.jsonl")) \
        or glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    if not hits:
        return {"total_tokens": None, "est_cost_usd": None, "_warn": "transcript not found"}
    db = os.path.join(_tf.mkdtemp(), "m.db")
    conn = connect(db)
    r = ingest_file(conn, hits[0], load_prices())
    tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (r["session_id"],)).fetchone()[0]
    row = conn.execute("SELECT total_tokens, est_cost_usd, tool_errors FROM session_summary "
                       "WHERE trace_id=?", (tid,)).fetchone()
    return {"total_tokens": row[0], "est_cost_usd": row[1], "tool_errors": row[2]}


def _peak_carried_tokens(session_id: str, work: str):
    """PEAK per-turn carried context for a session: MAX over model calls of
    (input + cache_read + cache_write) tokens. This is the context actually held at
    the fullest single turn — the right quantity for 'did it cross the 100k window',
    NOT the cumulative SUM across turns (which balloons and crosses any threshold
    trivially). None if the transcript isn't found yet."""
    from mrtoken.ingest import connect, load_prices, ingest_file
    import glob, tempfile as _tf
    esc = work.replace("/", "-").replace(".", "-")
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/{esc}/{session_id}.jsonl")) \
        or glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    if not hits:
        return None
    db = os.path.join(_tf.mkdtemp(), "m.db")
    conn = connect(db)
    r = ingest_file(conn, hits[0], load_prices())
    tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (r["session_id"],)).fetchone()[0]
    row = conn.execute(
        "SELECT MAX(input_tokens + cache_read_input_tokens + cache_creation_input_tokens) "
        "FROM model_call WHERE trace_id=?", (tid,)).fetchone()
    return row[0] if row and row[0] is not None else None


def _drive_mock(manifest: dict, arm: str) -> dict:
    """Zero-spend control-flow validation: simulate token growth crossing the
    reset point and the per-arm intervention branch. Does not solve the task."""
    threshold = manifest.get("reset_threshold_tokens", 100000)
    phase1 = int(threshold * 1.05)              # phase 1 grows just past the reset point
    reset_fired = arm in ("compact", "handoff")
    phase2_carry = {"continue": phase1, "compact": int(phase1 * 0.5), "handoff": 2000}[arm]
    total = phase1 + phase2_carry + 8000        # + some completion work
    return {"total_tokens": total, "est_cost_usd": round(total * 3e-6, 4),
            "wall_clock_s": 0.0, "steps": 12, "tool_errors": 0,
            "reset_fired": int(reset_fired),
            "peak_input_tokens": phase1 if reset_fired else None,
            "crossed_threshold": int(reset_fired),  # mock always crosses on reset arms
            "notes": f"MOCK ({arm})"}


def drive_agent(task_dir: str, manifest: dict, work: str, arm: str,
                mock: bool = False, budget_usd: float = 5.0) -> dict:
    """Drive the test agent to complete the task in `work` under `arm`, returning
    metrics measured from the transcript. See ROI-EXPERIMENT.md.

    LIVE PATH (claude -p) is wired for `continue`; `compact`/`handoff` use the
    phased --resume/handoff approach and need the 1-run smoke test to calibrate
    phase-1 turns + validate headless compaction/resume. mock=True is zero-spend."""
    if mock:
        return _drive_mock(manifest, arm)

    model = manifest["agent"]["model"]
    prompt = _read_prompt(task_dir, manifest)

    threshold = manifest.get("reset_threshold_tokens", 100000)

    if arm == "continue":
        res = _run_claude(prompt, work, model, budget_usd)
        sid = res.get("session_id")
        m = _measure(sid, work) if sid else {"_warn": res.get("_error", "no session")}
        # confirm-pilot's whole job: did a naive continue actually cross the window?
        peak = _peak_carried_tokens(sid, work) if sid else None
        return {**m, "wall_clock_s": None, "steps": res.get("num_turns"),
                "reset_fired": 0, "peak_input_tokens": peak,
                "crossed_threshold": int(bool(peak and peak >= threshold)),
                "notes": "live:continue"}

    phase1_turns = manifest.get("handoff_phase1_turns", 8)

    if arm == "handoff":
        # Phase 1: run partway, leaving the agent's partial edits on disk in `work`.
        r1 = _run_claude(prompt, work, model, budget_usd, max_turns=phase1_turns)
        sid1 = r1.get("session_id")
        m1 = _measure(sid1, work) if sid1 else {"total_tokens": 0, "est_cost_usd": 0}
        # token-threshold reset (5A.2): record the input-side tokens phase 1 reached,
        # so we KNOW whether the reset point was genuinely crossed — not a turn guess.
        peak = _peak_carried_tokens(sid1, work) if sid1 else None
        # Generate a compact handoff from phase 1, then a FRESH session continues
        # (work dir still holds phase 1's edits, so phase 2 builds on them).
        from mrtoken.handoff import build_handoff
        handoff_md = build_handoff(None, sid1) if sid1 else ""
        seeded = (handoff_md + "\n\n--- Original task ---\n" + prompt) if handoff_md else prompt
        r2 = _run_claude(seeded, work, model, budget_usd)
        sid2 = r2.get("session_id")
        m2 = _measure(sid2, work) if sid2 else {"total_tokens": 0, "est_cost_usd": 0}
        return {
            "total_tokens": (m1.get("total_tokens") or 0) + (m2.get("total_tokens") or 0),
            "est_cost_usd": round((m1.get("est_cost_usd") or 0) + (m2.get("est_cost_usd") or 0), 6),
            "wall_clock_s": None,
            "steps": (r1.get("num_turns") or 0) + (r2.get("num_turns") or 0),
            "tool_errors": (m1.get("tool_errors") or 0) + (m2.get("tool_errors") or 0),
            "reset_fired": 1, "peak_input_tokens": peak,
            "crossed_threshold": int(bool(peak and peak >= threshold)),
            "notes": f"live:handoff (phase1={phase1_turns} turns)",
        }

    if arm == "compact":
        # REAL early compaction. The old path RESUMED the same session (`--resume`), but
        # resume RELOADS the full transcript — no context is reclaimed unless the run hits
        # Claude Code's ~200k auto-compaction window (5A finding: compact ≡ continue below
        # the window). Headless `claude -p` exposes no `/compact`. So we emulate compaction
        # the only way available: summarize phase 1, then continue in a FRESH session that
        # carries ONLY the summary (~few k) instead of the full context. Phase-1 edits
        # persist on disk in `work`, so phase 2 builds on them and re-reads small refs as
        # needed — while the reclaimed bulk (disposable context) stays dropped.
        r1 = _run_claude(prompt, work, model, budget_usd, max_turns=phase1_turns)
        sid1 = r1.get("session_id")
        m1 = _measure(sid1, work) if sid1 else {"total_tokens": 0, "est_cost_usd": 0}
        peak = _peak_carried_tokens(sid1, work) if sid1 else None
        from mrtoken.handoff import build_handoff
        summary = build_handoff(None, sid1) if sid1 else ""
        seeded = (("COMPACTED CONTEXT — the earlier session was summarized to reclaim space.\n"
                   "Continue the task using this summary; re-read files as needed.\n\n"
                   + summary + "\n\nContinue until the task is complete.")
                  if summary else "Continue until the task is complete.")
        r2 = _run_claude(seeded, work, model, budget_usd)  # fresh session, NO --resume
        sid2 = r2.get("session_id")
        m2 = _measure(sid2, work) if sid2 else {"total_tokens": 0, "est_cost_usd": 0}
        return {
            "total_tokens": (m1.get("total_tokens") or 0) + (m2.get("total_tokens") or 0),
            "est_cost_usd": round((m1.get("est_cost_usd") or 0) + (m2.get("est_cost_usd") or 0), 6),
            "wall_clock_s": None,
            "steps": (r1.get("num_turns") or 0) + (r2.get("num_turns") or 0),
            "tool_errors": (m1.get("tool_errors") or 0) + (m2.get("tool_errors") or 0),
            "reset_fired": 1, "peak_input_tokens": peak,
            "crossed_threshold": int(bool(peak and peak >= threshold)),
            "notes": f"live:compact (real reset, phase1={phase1_turns} turns)"}

    raise NotImplementedError(f"unknown arm: {arm}")


def record(db_path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(RESULTS_SCHEMA)
    cols = ("task_id", "arm", "rep", "model", "effort", "completed", "total_tokens",
            "est_cost_usd", "wall_clock_s", "steps", "tool_errors", "reset_fired",
            "peak_input_tokens", "crossed_threshold", "notes", "created_at")
    conn.execute(f"INSERT INTO run({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                 tuple(row.get(c) for c in cols))
    conn.commit(); conn.close()


def check_fixture(task_dir: str) -> int:
    """No-API plumbing check: oracle must FAIL on the buggy seed, and must reject
    a tampered immutable file. Proves the oracle + immutability guard work."""
    manifest = load_manifest(task_dir)
    print(f"fixture: {manifest['id']}  ({manifest.get('type')})")

    work = prepare_workdir(task_dir, manifest)
    try:
        ok, out = run_oracle(task_dir, manifest, work)
        if ok:
            print("  ✗ oracle PASSED on the untouched seed — the task isn't broken "
                  "to begin with (a debug task's seed must start failing)")
            return 1
        print(f"  ✓ oracle fails on seed as expected ({out.splitlines()[-1] if out else '?'})")

        # immutability guard: tamper with an immutable file, oracle must reject
        for imm in manifest.get("immutable_files", []):
            p = os.path.join(work, imm)
            if os.path.exists(p):
                with open(p, "a") as fh:
                    fh.write("\n# tampered\n")
        ok2, out2 = run_oracle(task_dir, manifest, work)
        if ok2:
            print("  ✗ oracle accepted a tampered immutable file"); return 1
        print(f"  ✓ oracle rejects tampered immutable file")
        print("  fixture plumbing OK — ready for a live agent run once drive_agent() is wired.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="runner")
    ap.add_argument("task_dir", help="path to a task fixture dir")
    ap.add_argument("--check-fixture", action="store_true",
                    help="validate oracle + plumbing without an agent (no API)")
    ap.add_argument("--arm", choices=["continue", "compact", "handoff"])
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--mock", action="store_true",
                    help="validate the full run pipeline with a fake agent (no spend)")
    ap.add_argument("--budget-usd", type=float, default=5.0,
                    help="hard per-run budget cap passed to claude -p")
    ap.add_argument("--results-db", default=RESULTS_DB)
    a = ap.parse_args(argv)

    if a.check_fixture:
        sys.exit(check_fixture(a.task_dir))

    if not a.arm:
        ap.error("give --arm (continue|compact|handoff), --check-fixture, or add --mock")

    from datetime import datetime, timezone
    manifest = load_manifest(a.task_dir)
    for rep in range(a.reps):
        work = prepare_workdir(a.task_dir, manifest)
        try:
            metrics = drive_agent(a.task_dir, manifest, work, a.arm,
                                  mock=a.mock, budget_usd=a.budget_usd)
            completed, _ = run_oracle(a.task_dir, manifest, work)
            row = {"task_id": manifest["id"], "arm": a.arm, "rep": rep,
                   "model": manifest["agent"]["model"], "effort": manifest["agent"]["effort"],
                   "completed": int(completed),
                   "created_at": datetime.now(timezone.utc).isoformat(), **metrics}
            record(a.results_db, row)
            print(f"  {a.arm} rep{rep}: completed={completed} "
                  f"tokens={metrics.get('total_tokens')} reset_fired={metrics.get('reset_fired')} "
                  f"{metrics.get('notes','')}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
