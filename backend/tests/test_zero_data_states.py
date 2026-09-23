#!/usr/bin/env python3
"""Every read-only analysis command must render, not crash, in every state the
schema permits to be absent: an empty DB, a session with zero calls, a session
with no cache reads (so no handoff carry), NULL optional columns, an orphan
subagent, and so on.

Enumerate STATES, not commands: fleet.py:59 crashed on an empty DB, and roi.py:262
crashed on every session without cache reads, and neither showed up in a sweep
of commands against populated data.

A sweep that reports zero crashes is indistinguishable from a broken sweep, so:
  - test_sweep_detects_an_injected_crash is the positive control: it makes fleet
    raise and requires the sweep to report it.
  - test_no_command_crashes_in_any_absence_state asserts how many cells actually
    reached analysis. If commands start refusing early, the floor fails instead of
    the sweep quietly becoming decorative.
"""
import contextlib
import io
import os
import sys
import tempfile
import traceback
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken import cli
from mrtoken.ingest import connect

_MC = ("INSERT INTO model_call(trace_id,model,timestamp,input_tokens,output_tokens,cache_read_input_tokens,"
       "cache_creation_input_tokens,est_cost_usd,billing_mode) VALUES(?,?,?,?,?,?,?,?,?)")


def _trace(c, source="claude_code", sid="s-main", parent=None, full=True):
    cols = "source,session_id,parent_session_id,ingested_at" + (",started_at,title,project_path" if full else "")
    vals = (source, sid, parent, "now") + (("2026-09-23T00:00:00Z", "t", "/p") if full else ())
    return c.execute(f"INSERT INTO trace({cols}) VALUES({','.join('?' * len(vals))})", vals).lastrowid


def _calls(c, tid, n=3, cr=5000, model="claude-sonnet-4"):
    for i in range(n):
        c.execute(_MC, (tid, model, f"2026-09-23T00:00:0{i}Z", 1000, 200, cr, 100, 0.01, "subscription"))


def _nulls(c):
    tid = _trace(c, full=False)
    c.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,cache_read_input_tokens,"
              "cache_creation_input_tokens) VALUES(?,?,?,?,?)", (tid, 1000, 200, 5000, 100))


def _null_tools(c):
    tid = _trace(c)
    _calls(c, tid)
    c.execute("INSERT INTO tool_call(trace_id) VALUES(?)", (tid,))


def _null_recs(c):
    tid = _trace(c)
    _calls(c, tid)
    c.execute("INSERT INTO recommendation(trace_id,rule,severity,message,created_at) VALUES(?,?,?,?,?)",
              (tid, "huge_tool_output", "high", "m", "now"))


STATES = {
    "empty": lambda c: None,
    "zero_calls": lambda c: _trace(c),
    "no_cache_reads": lambda c: _calls(c, _trace(c), cr=0),
    "minimal": lambda c: _calls(c, _trace(c)),
    "null_columns": _nulls,
    "orphan_subagent": lambda c: _calls(c, _trace(c, "claude_code_subagent", "s-sub", parent="missing")),
    "subagent_only": lambda c: _calls(c, _trace(c, "claude_code_subagent", "s-sub", parent="s-main")),
    "subagent_zero_calls": lambda c: (_calls(c, _trace(c)),
                                      _trace(c, "claude_code_subagent", "s-sub", parent="s-main")),
    "codex_only": lambda c: _calls(c, _trace(c, "codex"), cr=0, model="gpt-5.5"),
    "null_tool_fields": _null_tools,
    "null_recommendation_fields": _null_recs,
    "single_call": lambda c: _calls(c, _trace(c), n=1),
}
COMMANDS = [["fleet"], ["list"], ["report"], ["report", "s-"], ["subagents"], ["subagents", "s-"],
            ["roi"], ["roi", "s-"], ["savings"], ["status", "s-"], ["why"], ["why", "s-"],
            ["explain"], ["explain", "s-"], ["export"], ["export", "s-"], ["validate"],
            ["handoff"], ["handoff", "s-"]]
# Cells that reached analysis on 2026-09-23: 204 of 228. The other 24 are designed
# refusals (empty store; Claude-only subagents on non-Claude data). Lower this only
# after confirming a new refusal is intended.
EXERCISED_FLOOR = 204
_REFUSALS = ("unavailable", "no matching", "supports claude", "not found", "no session")


def sweep(tmp, states, commands):
    """Return (crashes {site: [cells]}, refused [cells], total cells)."""
    crashes, refused, total = {}, [], 0
    for name, build in states.items():
        db = os.path.join(tmp, name + ".db")
        c = connect(db)
        build(c)
        c.commit()
        c.close()
        for args in commands:
            total += 1
            cell = f"{name} x {' '.join(args)}"
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    cli.main(args + ["--db", db])
            except SystemExit as exc:
                if exc.code not in (0, None):
                    refused.append(cell)
            except Exception as exc:
                frame = traceback.extract_tb(exc.__traceback__)[-1]
                site = f"{type(exc).__name__}: {exc} @ {os.path.basename(frame.filename)}:{frame.lineno}"
                crashes.setdefault(site, []).append(cell)
            else:
                if any(p in out.getvalue().lower() for p in _REFUSALS):
                    refused.append(cell)
    return crashes, refused, total


class ZeroDataStatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items()
               if k not in ("XDG_DATA_HOME", "TOKEN_TITHE_DB", "MRTOKEN_DB", "MRTOKEN_DATA_DIR")}
        env["HOME"] = self.tmp
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_command_crashes_in_any_absence_state(self):
        crashes, refused, total = sweep(self.tmp, STATES, COMMANDS)
        self.assertEqual(total, len(STATES) * len(COMMANDS))
        self.assertEqual(crashes, {})
        self.assertGreaterEqual(total - len(refused), EXERCISED_FLOOR,
                                f"{len(refused)} cells refused before analysis: {refused}")

    def test_sweep_detects_an_injected_crash(self):
        def broken(conn):
            raise TypeError("injected")
        with mock.patch("mrtoken.fleet.fleet_summary", broken):
            crashes, _, _ = sweep(self.tmp, {"empty": STATES["empty"]}, [["fleet"]])
        self.assertEqual(list(crashes.values()), [["empty x fleet"]])
        # and a refusal is counted as not exercised
        _, refused, _ = sweep(self.tmp, {"empty": STATES["empty"]}, [["why"]])
        self.assertEqual(refused, ["empty x why"])


if __name__ == "__main__":
    unittest.main()
