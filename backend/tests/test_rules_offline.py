#!/usr/bin/env python3
"""The rules engine is switched off (rules.RULES_ENABLED, backend/docs/DIRECTION-2026-09-23.md).

Pinned, each against a store that DOES hold historical rules output, and each with a
positive control (the same fixture with the gate forced on shows the content), so
"nothing shown" cannot pass because the fixture had nothing to show:
- analyse() computes and writes nothing, and leaves historical rows untouched;
- no human-facing surface shows recommendation content, new or old;
- the release gate script refuses (exit 3) without opening a store or scoring anything.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

import mrtoken.rules as rules
from mrtoken.ingest import connect

MSG = "HISTORICAL-RULE-ADVICE"  # a string only a recommendation row carries


def store_with_history(tmp):
    """A current-schema store whose one session carries historical rules output."""
    path = os.path.join(tmp, "store.db")
    c = connect(path)
    tid = c.execute("INSERT INTO trace(source,session_id,ingested_at,started_at,title) "
                    "VALUES('claude_code','s-hist','now','2026-09-01T00:00:00Z','t')").lastrowid
    for i in range(3):
        c.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens,cache_read_input_tokens,"
                  "cache_creation_input_tokens,est_cost_usd,model) VALUES(?,?,?,?,?,?,?,?)",
                  (tid, f"2026-09-01T00:00:0{i}Z", 1000, 200, 5000, 100, 0.01, "claude-sonnet-4"))
    c.execute("INSERT INTO tool_call(trace_id,tool_name,output_chars,output_tokens_est,is_error) "
              "VALUES(?,?,?,?,?)", (tid, "Read", 400_000, 100_000, 0))
    c.execute("INSERT INTO recommendation(trace_id,rule,severity,message,evidence_json,est_savings_tokens,created_at) "
              "VALUES(?,?,?,?,?,?,?)", (tid, "huge_tool_output", "high", MSG, "{}", 12_345, "now"))
    c.commit()
    c.close()
    return path, tid


def render(fn):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            fn()
        except SystemExit:
            pass
    return out.getvalue()


class RulesOfflineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path, self.tid = store_with_history(self.tmp)
        env = {k: v for k, v in os.environ.items() if k not in ("MRTOKEN_DB", "TOKEN_TITHE_DB", "MRTOKEN_DATA_DIR")}
        env["HOME"] = self.tmp
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_gate_is_off_by_default(self):
        self.assertFalse(rules.RULES_ENABLED)
        self.assertFalse(rules.advice_on())

    def test_analyse_writes_nothing_and_keeps_history(self):
        c = connect(self.path)
        before = c.execute("SELECT COUNT(*), GROUP_CONCAT(message) FROM recommendation").fetchone()
        self.assertEqual(rules.analyse(c, self.tid), [])
        self.assertEqual(c.execute("SELECT COUNT(*), GROUP_CONCAT(message) FROM recommendation").fetchone(), before)
        c.close()

    def surfaces(self):
        from mrtoken.cli import main
        from mrtoken.assist import assist_suggestion
        from mrtoken.beta_evidence import print_beta_evidence
        from mrtoken.corpus import print_corpus_report
        db = self.path

        def assist():
            c = connect(db)
            print(assist_suggestion(c, self.tid, enabled=True) or "")
            c.close()
        exports = {"errors": [], "files": 2, "tool_versions": [], "sessions": 1, "low_activity": 0,
                   "total_tokens": 1, "est_cost_usd": 0, "cache_hit_ratio": None,
                   "rule_fires": {"huge_tool_output": {"high": 1}}, "est_savings_tokens": 0}
        doctors = {"files": 2, "ok": 2, "failures": 0, "failed_checks": {}, "warnings": 0, "warning_checks": {}}
        return {
            "report": lambda: main(["report", "s-hist", "--db", db]),
            "fleet": lambda: main(["fleet", "--db", db]),
            "handoff": lambda: main(["handoff", "s-hist", "--db", db]),
            "roi": lambda: main(["roi", "s-hist", "--db", db]),
            "savings": lambda: main(["savings", "--db", db]),
            "status": lambda: main(["status", "s-hist", "--db", db]),
            "why": lambda: main(["why", "s-hist", "--db", db]),
            "assist": assist,
            "beta evidence": lambda: print_beta_evidence({"errors": [], "exports": exports, "doctor_bundles": doctors,
                                                          "automatic_gate": {"passed": True, "blockers": []},
                                                          "manual_questions": []}),
            "corpus": lambda: print_corpus_report(exports),
        }

    # what each surface prints ONLY when rules output is being shown
    MARKERS = {"report": MSG, "fleet": "huge_tool_output", "handoff": MSG, "roi": "Tactical waste",
               "savings": "addressable", "status": "feedback:", "why": "avoidable drivers",
               "assist": "assist worth it", "beta evidence": "huge_tool_output", "corpus": "huge_tool_output"}

    def test_no_surface_shows_rules_output(self):
        for name, fn in self.surfaces().items():
            with self.subTest(surface=name):
                self.assertNotIn(self.MARKERS[name], render(fn))

    def test_positive_control_the_fixture_has_content_to_hide(self):
        # with the gate forced on, every surface shows it, so the test above is not vacuous
        with mock.patch.object(rules, "RULES_ENABLED", True):
            for name, fn in self.surfaces().items():
                if name == "assist":
                    continue  # needs MRTOKEN_ASSIST plus a savings threshold; covered in test_backend
                with self.subTest(surface=name):
                    self.assertIn(self.MARKERS[name], render(fn))

    def test_beta_gate_blocker_for_no_rule_fires_is_suspended(self):
        from mrtoken.beta_evidence import summarize_beta_evidence
        with mock.patch("mrtoken.beta_evidence.summarize_exports",
                        return_value={"files": 2, "sessions": 1, "rule_fires": {}, "errors": []}), \
             mock.patch("mrtoken.beta_evidence._summarize_doctors",
                        return_value={"files": 2, "ok": 2, "failures": 0, "failed_checks": {},
                                      "warnings": 0, "warning_checks": {}, "versions": set()}):
            off = summarize_beta_evidence([])["automatic_gate"]["blockers"]
            with mock.patch.object(rules, "RULES_ENABLED", True):
                on = summarize_beta_evidence([])["automatic_gate"]["blockers"]
        blocker = "need at least one rule fire on tester data"
        self.assertNotIn(blocker, off)
        self.assertIn(blocker, on)  # re-arms with the gate

    def test_release_gate_script_refuses_without_opening_a_store(self):
        missing = os.path.join(self.tmp, "never", "created.db")
        p = subprocess.run(["bash", os.path.join(BACKEND, "..", "scripts", "check-recommendation-quality.sh"),
                            "--db", missing, "--refresh-rules"], text=True, capture_output=True,
                           env=dict(os.environ, PYTHONPATH=BACKEND))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("DIRECTION-2026-09-23.md", p.stdout)
        self.assertNotIn("proxy", p.stdout.lower())      # nothing was scored
        self.assertFalse(os.path.exists(missing))        # no store was opened or created


if __name__ == "__main__":
    unittest.main()
