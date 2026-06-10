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


def drive_agent(task_dir: str, manifest: dict, work: str, arm: str) -> dict:
    """SEAM (not yet wired): drive the test agent to complete the task in `work`.

    Must, for the given arm:
      1. Start a Sonnet (medium-effort, temperature 0) headless agent in `work`
         with the prompt from manifest['prompt_file'] and the usual coding tools.
      2. Track input-side context size live (reuse mrtoken.watch's logic over the
         agent's transcript) until it crosses manifest['reset_threshold_tokens'].
      3. At that reset point, apply the arm:
           continue -> do nothing, keep going
           compact  -> compact the context (built-in), keep going
           handoff  -> `mrtoken-transcript handoff`, start a FRESH agent seeded
                       with the handoff text + the original prompt, keep going
         (continue never resets; compact/handoff reset exactly once, here.)
      4. Stop at completion or manifest['max_steps'].
      5. Return exact metrics measured FROM THE TRANSCRIPT via the backend:
         {total_tokens, est_cost_usd, wall_clock_s, steps, tool_errors, reset_fired}

    Implement with the Claude Agent SDK or headless `claude -p`. Pin model/effort
    identically across arms. Enforce a hard token budget cap (abort if exceeded).
    """
    raise NotImplementedError(
        "drive_agent() is the next build step — wire the Claude Agent SDK / "
        "headless claude here (see docstring + ROI-EXPERIMENT.md harness spec).")


def record(db_path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(RESULTS_SCHEMA)
    cols = ("task_id", "arm", "rep", "model", "effort", "completed", "total_tokens",
            "est_cost_usd", "wall_clock_s", "steps", "tool_errors", "reset_fired",
            "notes", "created_at")
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
    ap.add_argument("--results-db", default=RESULTS_DB)
    a = ap.parse_args(argv)

    if a.check_fixture:
        sys.exit(check_fixture(a.task_dir))

    if not a.arm:
        ap.error("give --arm (continue|compact|handoff) or --check-fixture")

    manifest = load_manifest(a.task_dir)
    for rep in range(a.reps):
        work = prepare_workdir(a.task_dir, manifest)
        try:
            metrics = drive_agent(a.task_dir, manifest, work, a.arm)  # NotImplemented for now
            completed, _ = run_oracle(a.task_dir, manifest, work)
            record(a.results_db, {"task_id": manifest["id"], "arm": a.arm, "rep": rep,
                                  "model": manifest["agent"]["model"],
                                  "effort": manifest["agent"]["effort"],
                                  "completed": int(completed), **metrics,
                                  "created_at": "set-after-run"})
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
