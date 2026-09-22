import hashlib
import io
import json
import os
import sqlite3
import subprocess
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

from mrtoken.ingest import connect as _connect, default_db_path, ingest_file, load_prices
from mrtoken.rules import rule_huge_tool_output, rule_retry_loop

_OPEN_TEST_CONNS = []


def connect(*args, **kwargs):
    conn = _connect(*args, **kwargs)
    _OPEN_TEST_CONNS.append(conn)
    return conn


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")



class BackendTest(unittest.TestCase):
    def setUp(self):
        # window-inference tests must be deterministic regardless of any machine
        # override (MRTOKEN_CONTEXT_MAX env or ~/.mrtoken/config.json)
        import mrtoken.statusline as _sl
        import mrtoken.ingest as _ing
        self._saved_env = os.environ.pop("MRTOKEN_CONTEXT_MAX", None)
        self._saved_cfg = _sl._config_context_max
        self._saved_connect = _ing.connect
        _sl._config_context_max = lambda: None
        _ing.connect = connect

    def tearDown(self):
        import mrtoken.statusline as _sl
        import mrtoken.ingest as _ing
        _sl._config_context_max = self._saved_cfg
        _ing.connect = self._saved_connect
        if self._saved_env is not None:
            os.environ["MRTOKEN_CONTEXT_MAX"] = self._saved_env
        while _OPEN_TEST_CONNS:
            conn = _OPEN_TEST_CONNS.pop()
            try:
                conn.close()
            except sqlite3.Error:
                pass

    def test_default_db_path_is_project_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            self.assertEqual(
                default_db_path(tmp),
                os.path.join(tmp, ".token-tithe", "token-tithe.db"),
            )

    def test_ingests_tokens_tools_and_hashes_without_raw_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, ".token-tithe", "token-tithe.db")
            transcript = os.path.join(tmp, "session-1.jsonl")
            write_jsonl(
                transcript,
                [
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "uuid": "assistant-1",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "cwd": tmp,
                        "message": {
                            "model": "claude-sonnet-4",
                            "usage": {
                                "input_tokens": 100,
                                "output_tokens": 20,
                                "cache_read_input_tokens": 50,
                                "cache_creation_input_tokens": 10,
                            },
                            "content": [
                                {"type": "text", "text": "plan"},
                                {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "secret.py"}},
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-06-01T00:00:01Z",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "tool-1",
                                    "content": "raw secret source should not be stored",
                                }
                            ]
                        },
                    },
                ],
            )

            conn = connect(db_path)
            result = ingest_file(conn, transcript, load_prices())

            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(result["tool_calls"], 1)
            self.assertTrue(os.path.exists(db_path))
            self.assertEqual(conn.execute("SELECT input_tokens, output_tokens FROM model_call").fetchone(), (100, 20))
            tool = conn.execute("SELECT tool_name, output_chars, output_hash FROM tool_call").fetchone()
            self.assertEqual(tool[0], "Read")
            self.assertGreater(tool[1], 0)
            self.assertIsNotNone(tool[2])
            columns = [row[1] for row in conn.execute("PRAGMA table_info(context_block)").fetchall()]
            self.assertNotIn("content", columns)

    def test_huge_tool_output_rule(self):
        conn, tid = make_trace()
        conn.execute(
            "INSERT INTO tool_call(trace_id, tool_name, output_chars, output_tokens_est) VALUES(?,?,?,?)",
            (tid, "Bash", 50_000, 12_500),
        )

        recs = rule_huge_tool_output(conn, tid)

        self.assertEqual(recs[0]["rule"], "huge_tool_output")
        self.assertEqual(recs[0]["severity"], "warn")

    def test_retry_loop_rule_uses_real_model_call_id(self):
        conn, tid = make_trace()
        model_call_ids = []
        for index in range(3):
            cur = conn.execute(
                "INSERT INTO model_call(trace_id, timestamp, input_tokens, output_tokens) VALUES(?,?,?,?)",
                (tid, f"2026-06-01T00:00:0{index}Z", 10, 1),
            )
            model_call_ids.append(cur.lastrowid)
            conn.execute(
                "INSERT INTO tool_call(trace_id, model_call_id, tool_name, is_error) VALUES(?,?,?,1)",
                (tid, cur.lastrowid, "Bash"),
            )

        recs = rule_retry_loop(conn, tid)

        self.assertEqual(recs[0]["rule"], "retry_loop")
        evidence = json.loads(recs[0]["evidence_json"])
        self.assertEqual(evidence["first_mc_id"], model_call_ids[0])


    def test_profile_classifier_and_thresholds(self):
        from mrtoken.profile import classify_profile
        from mrtoken.rules import _thresholds
        conn, tid = make_trace()
        # research-shaped: reads/searches only
        for name in ["Read", "Read", "Grep", "WebFetch"]:
            conn.execute("INSERT INTO tool_call(trace_id, tool_name, output_chars) VALUES(?,?,?)",
                         (tid, name, 1000))
        profile, conf, _ = classify_profile(conn, tid)
        self.assertEqual(profile, "research")
        conn.execute("UPDATE trace SET profile=? WHERE id=?", (profile, tid))
        thresholds, resolved = _thresholds(conn, tid)
        # research tolerates much larger tool outputs than the default
        self.assertEqual(resolved, "research")
        self.assertEqual(thresholds["huge_tool_chars"], 80_000)

    def test_session_summary_view_exposes_real_tokens(self):
        from mrtoken.export import session_summaries
        conn, tid = make_trace()
        conn.execute(
            "INSERT INTO model_call(trace_id, input_tokens, output_tokens, "
            "cache_read_input_tokens, est_cost_usd) VALUES(?,?,?,?,?)",
            (tid, 100, 50, 900, 1.25),
        )
        conn.commit()
        rows = session_summaries(conn, "session-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_tokens"], 150)
        self.assertEqual(rows[0]["cache_read_tokens"], 900)
        self.assertEqual(rows[0]["cache_hit_ratio"], 0.9)

    def test_billing_semantics_require_session_owned_positive_evidence(self):
        from mrtoken.export import session_summaries
        conn, api_tid = make_trace()
        sub_tid = conn.execute("INSERT INTO trace(source,session_id,ingested_at) VALUES(?,?,?)",
                               ("codex", "subscription-session", "now")).lastrowid
        unknown_tid = conn.execute("INSERT INTO trace(source,session_id,ingested_at) VALUES(?,?,?)",
                                   ("codex", "unknown-session", "now")).lastrowid
        no_total_tid = conn.execute("INSERT INTO trace(source,session_id,ingested_at) VALUES(?,?,?)",
                                    ("claude_code", "no-total-session", "now")).lastrowid
        for tid, mode in ((api_tid, "api"), (sub_tid, "subscription"), (unknown_tid, None)):
            conn.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,cache_read_input_tokens,"
                         "billing_mode,reported_total_tokens,est_cost_usd) VALUES(?,?,?,?,?,?,?)",
                         (tid, 10, 5, 20, mode, 35, 1.25))
        conn.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,est_cost_usd) VALUES(?,?,?,?)",
                     (no_total_tid, 10, 5, 1.25))
        conn.commit()
        rows = {row["session_id"]: row for row in session_summaries(conn)}
        self.assertEqual(rows["session-1"]["billing_mode"], "api")
        self.assertEqual(rows["session-1"]["api_est_cost_usd"], 1.25)
        self.assertEqual(rows["session-1"]["cumulative_expenditure_tokens"], 35)
        self.assertEqual(rows["session-1"]["cumulative_expenditure_provenance"], "computed-disjoint-components")
        self.assertEqual(rows["subscription-session"]["billing_mode"], "subscription")
        self.assertIsNone(rows["subscription-session"]["api_est_cost_usd"])
        self.assertEqual(rows["unknown-session"]["billing_mode"], "unknown")
        self.assertIsNone(rows["unknown-session"]["api_est_cost_usd"])
        self.assertIsNone(rows["unknown-session"]["cumulative_expenditure_tokens"])
        from mrtoken.status import status_snapshot
        self.assertEqual(status_snapshot(conn, no_total_tid)["total_tokens"], 15)
        self.assertEqual(status_snapshot(conn, no_total_tid)["total_provenance"], "computed-disjoint-components")
        self.assertIsNone(status_snapshot(conn, unknown_tid)["total_tokens"])
        from mrtoken.why import diagnose
        d = diagnose(conn, unknown_tid)
        self.assertEqual(d["shape"]["carrying cached context"], 20)
        self.assertIn("57% of observed token activity", d["headline"])

    def test_claude_computed_total_pins_every_component(self):
        from mrtoken.export import session_summaries
        components = {
            "input": 10,
            "cache read": 20,
            "cache write": 3,
            "output": 5,
        }
        for dropped, amount in components.items():
            with self.subTest(dropped=dropped):
                conn, tid = make_trace()
                conn.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,"
                             "cache_read_input_tokens,cache_creation_input_tokens) VALUES(?,?,?,?,?)",
                             (tid, components["input"], components["output"],
                              components["cache read"], components["cache write"]))
                conn.commit()
                total = session_summaries(conn, "session-1")[0]["cumulative_expenditure_tokens"]
                self.assertEqual(total, sum(components.values()))
                self.assertNotEqual(total, sum(components.values()) - amount)

    def test_report_suppresses_provenance_for_null_cumulative_total(self):
        from mrtoken.report import report
        conn = connect(":memory:")
        conn.execute("INSERT INTO trace(source,session_id,ingested_at) VALUES(?,?,?)",
                     ("claude_code", "zero-call", "now"))
        conn.commit()
        out = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(out):
            report(conn, "zero-call")
        self.assertIn("cumulative token total    UNKNOWN", out.getvalue())
        self.assertNotIn("computed-disjoint-components", out.getvalue())


    def test_repeated_context_is_cache_aware(self):
        from mrtoken.rules import rule_repeated_context
        conn, tid = make_trace()
        # a 10k-token block re-sent 4 times = 30k raw repeated tokens
        conn.execute(
            "INSERT INTO context_block(trace_id, block_type, hash, token_count, repeat_count) "
            "VALUES(?,?,?,?,?)", (tid, "system", "h1", 10_000, 4))
        # but the session is 95% cached → effective uncached waste ≈ 1.5k < floor
        conn.execute(
            "INSERT INTO model_call(trace_id, input_tokens, cache_read_input_tokens) "
            "VALUES(?,?,?)", (tid, 5_000, 95_000))
        conn.commit()
        self.assertEqual(rule_repeated_context(conn, tid), [],
                         "cached re-sends should not fire repeated_context")

    def test_validate_huge_tool_output_reads_offenders(self):
        # regression (ROADMAP 2.2): corroboration must locate the offending tool
        # call via evidence offenders[], not a (nonexistent) top-level tool_use_id,
        # else every huge_tool_output fire is wrongly scored "moot".
        from mrtoken.rules import analyse
        from mrtoken.validate import validate_db
        conn, tid = make_trace()
        cur = conn.execute("INSERT INTO model_call(trace_id, timestamp) VALUES(?,?)",
                           (tid, "2026-06-01T00:00:00Z"))
        mc0 = cur.lastrowid
        conn.execute("INSERT INTO tool_call(trace_id, model_call_id, tool_use_id, tool_name, "
                     "output_chars) VALUES(?,?,?,?,?)", (tid, mc0, "t1", "Bash", 60_000))
        for s in range(1, 11):  # 10 calls AFTER the huge output → should corroborate strong
            conn.execute("INSERT INTO model_call(trace_id, timestamp) VALUES(?,?)",
                         (tid, f"2026-06-01T00:00:{s:02d}Z"))
        conn.commit()
        analyse(conn, tid)
        rep = validate_db(conn)["rules"]["huge_tool_output"]
        self.assertEqual(rep["strong"], 1)  # the fix located the offender
        self.assertEqual(rep["moot"], 0)

    def test_step_runaway_rule_and_validate(self):
        # ROADMAP 3.1: flag extreme step counts; silent on normal sessions; corroborated.
        from mrtoken.rules import rule_step_runaway, analyse
        from mrtoken.validate import validate_db
        normal, ntid = make_trace()
        for i in range(10):
            normal.execute("INSERT INTO model_call(trace_id,timestamp) VALUES(?,?)",
                           (ntid, f"2026-06-01T00:00:{i:02d}Z"))
        self.assertEqual(rule_step_runaway(normal, ntid), [])  # well under the floor

        conn, tid = make_trace()
        for i in range(130):  # runaway step count, with early churn (errored tools)
            cur = conn.execute("INSERT INTO model_call(trace_id,timestamp) VALUES(?,?)",
                               (tid, f"2026-06-01T{i//60:02d}:{i%60:02d}:00Z"))
            if i < 6:
                conn.execute("INSERT INTO tool_call(trace_id,model_call_id,tool_name,is_error) "
                             "VALUES(?,?,?,1)", (tid, cur.lastrowid, "Bash"))
        conn.commit()
        recs = rule_step_runaway(conn, tid)
        self.assertEqual(recs[0]["rule"], "step_runaway")
        analyse(conn, tid)
        rep = validate_db(conn)["rules"].get("step_runaway")
        self.assertIsNotNone(rep)                    # wired into validate
        self.assertEqual(rep["strong"], rep["fired"])  # churn → strong

    def test_subagent_net_roi_positive_and_negative(self):
        # ROADMAP 3.2: a focused subagent reads positive net vs inline; a thrashing
        # one (returns more than it digested) reads negative.
        from mrtoken.subagents import get_subagent_data, session_net_tokens, roi_summary_line
        conn = connect(":memory:")
        def trace(sid, source, parent=None, started="2026-06-01T00:00:00Z"):
            return conn.execute(
                "INSERT INTO trace(session_id,source,parent_session_id,started_at,ingested_at) "
                "VALUES(?,?,?,?,?)", (sid, source, parent, started, started)).lastrowid
        # GOOD: subagent digests ~50k, hands back ~100 tok → large positive net
        p1 = trace("parent1", "claude_code")
        s1 = trace("sub1", "claude_code_subagent", "parent1", "2026-06-01T00:10:00Z")
        conn.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens) "
                     "VALUES(?,?,?,?)", (s1, "2026-06-01T00:10:00Z", 25000, 25000))
        conn.execute("INSERT INTO tool_call(trace_id,tool_name,output_chars,ended_at) "
                     "VALUES(?,?,?,?)", (p1, "Task", 400, "2026-06-01T00:10:01Z"))
        # THRASHING: subagent does ~500 tok of work, result is ~2000 tok → negative net
        p2 = trace("parent2", "claude_code")
        s2 = trace("sub2", "claude_code_subagent", "parent2", "2026-06-02T00:10:00Z")
        conn.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens) "
                     "VALUES(?,?,?,?)", (s2, "2026-06-02T00:10:00Z", 300, 200))
        conn.execute("INSERT INTO tool_call(trace_id,tool_name,output_chars,ended_at) "
                     "VALUES(?,?,?,?)", (p2, "Task", 8000, "2026-06-02T00:10:01Z"))
        conn.commit()

        good = get_subagent_data(conn, "parent1")
        self.assertEqual(len(good), 1)
        self.assertGreater(good[0]["net_tokens"], 0)
        self.assertGreater(session_net_tokens(good), 0)
        self.assertIn("saved", roi_summary_line(conn, "parent1"))

        bad = get_subagent_data(conn, "parent2")
        self.assertLess(bad[0]["net_tokens"], 0)
        self.assertIn("ADDED", roi_summary_line(conn, "parent2"))

    def test_context_rot_soft_hint(self):
        # ROADMAP 3.3: fires info-only when context is large AND cache efficiency
        # falls; silent on short sessions; never high.
        from mrtoken.rules import rule_context_rot
        conn, tid = make_trace()
        # 24 calls: first half heavily cached (large carry), second half cache falls
        for i in range(24):
            if i < 12:
                inp, cr = 1000, 120_000   # ratio ~0.99, peak carry 120k
            else:
                inp, cr = 100_000, 20_000  # ratio ~0.17 → big drop
            conn.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,"
                         "cache_read_input_tokens) VALUES(?,?,?,?)",
                         (tid, f"2026-06-01T00:{i:02d}:00Z", inp, cr))
        conn.commit()
        recs = rule_context_rot(conn, tid)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["rule"], "context_rot")
        self.assertEqual(recs[0]["severity"], "info")  # never high — it's a soft hint

        short, stid = make_trace()  # too few calls → silent
        for i in range(5):
            short.execute("INSERT INTO model_call(trace_id,timestamp,cache_read_input_tokens) "
                          "VALUES(?,?,?)", (stid, f"2026-06-01T00:0{i}:00Z", 120_000))
        short.commit()
        self.assertEqual(rule_context_rot(short, stid), [])

    def test_assist_suggestion_gated_by_savings_and_optin(self):
        # ROADMAP 3.4: off by default (behavior unchanged); when on, a high-waste
        # session suggests, a low-waste one stays silent. Never auto-runs.
        from mrtoken.assist import assist_suggestion, ASSIST_COST_TOKENS, ASSIST_SAVINGS_RATIO
        conn, tid = make_trace()
        big = ASSIST_SAVINGS_RATIO * ASSIST_COST_TOKENS + 1
        conn.execute("INSERT INTO recommendation(trace_id,rule,severity,message,"
                     "est_savings_tokens,created_at) VALUES(?,?,?,?,?,?)",
                     (tid, "fresh_handoff", "high", "x", big, "2026-01-01"))
        conn.commit()
        self.assertIsNone(assist_suggestion(conn, tid, enabled=False))  # default off → silent
        s = assist_suggestion(conn, tid, enabled=True)
        self.assertIsNotNone(s)
        self.assertIn("/mr-handoff", s)              # handoff-type rule → handoff assist

        low, ltid = make_trace()
        low.execute("INSERT INTO recommendation(trace_id,rule,severity,message,"
                    "est_savings_tokens,created_at) VALUES(?,?,?,?,?,?)",
                    (ltid, "re_read_loop", "info", "x", 1000, "2026-01-01"))
        low.commit()
        self.assertIsNone(assist_suggestion(low, ltid, enabled=True))  # below the gate → silent

    def test_codex_adapter_ingests_into_shared_schema(self):
        # ROADMAP 3.5: a Codex rollout ingests into the same trace/model_call/tool_call
        # schema (source='codex') and the rule engine runs; Claude path unaffected.
        from mrtoken.ingest_codex import ingest_codex_file, _is_codex_transcript
        from mrtoken.ingest import load_prices
        from mrtoken.rules import analyse
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cx1", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.5"}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "response_item",
                 "payload": {"type": "function_call", "call_id": "c1", "name": "exec_command",
                             "arguments": "{\"cmd\":\"ls\"}"}},
                {"timestamp": "2026-06-01T00:00:03Z", "type": "response_item",
                 "payload": {"type": "function_call_output", "call_id": "c1",
                             "output": "Exit code: 0\nfiles"}},
                {"timestamp": "2026-06-01T00:00:04Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 5000, "cached_input_tokens": 4000,
                     "output_tokens": 200, "reasoning_output_tokens": 50, "total_tokens": 5200}}}},
            ])
            self.assertTrue(_is_codex_transcript(codex))
            conn = connect(os.path.join(tmp, "t.db"))
            r = ingest_codex_file(conn, codex, load_prices())
            self.assertEqual((r["model_calls"], r["tool_calls"]), (1, 1))
            src, mc = conn.execute(
                "SELECT source, model_calls FROM session_summary WHERE session_id='cx1'").fetchone()
            self.assertEqual(src, "codex")
            self.assertEqual(mc, 1)
            tid = conn.execute("SELECT id FROM trace WHERE session_id='cx1'").fetchone()[0]
            inp, cr = conn.execute("SELECT input_tokens, cache_read_input_tokens "
                                   "FROM model_call WHERE trace_id=?", (tid,)).fetchone()
            self.assertEqual((inp, cr), (1000, 4000))  # fresh = 5000-4000; cached → cache_read
            # tool calls are LINKED to a model call (else retry_loop/huge_tool_output break on Codex)
            linked = conn.execute("SELECT model_call_id FROM tool_call WHERE trace_id=?",
                                  (tid,)).fetchone()
            self.assertIsNotNone(linked[0])
            analyse(conn, tid)  # rule engine runs on codex data without error
            # a Claude transcript must NOT sniff as codex (Claude path unaffected)
            claude = os.path.join(tmp, "claude.jsonl")
            write_jsonl(claude, [{"type": "assistant", "sessionId": "s",
                                  "message": {"id": "m", "usage": {"input_tokens": 1}}}])
            self.assertFalse(_is_codex_transcript(claude))

    def test_codex_provider_total_requires_input_output_reconciliation(self):
        # M3 mutation guard: a reported total is publishable only when Codex's
        # own input + output equality holds.  Do not fall back to per-turn totals.
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.ingest import load_prices
        from mrtoken.export import session_summaries
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cumulative-guard", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-terra"}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {
                     "last_token_usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                     "total_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}}},
                # The later snapshot is present but cannot be reconciled.  If the
                # equality guard is removed, this would incorrectly publish 151.
                {"timestamp": "2026-06-01T00:00:03Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {
                     "last_token_usage": {"input_tokens": 90, "output_tokens": 20, "total_tokens": 110},
                     "total_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 151}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            ingest_codex_file(conn, codex, load_prices())
            row = session_summaries(conn, "cumulative-guard")[0]
            self.assertIsNone(row["cumulative_expenditure_tokens"])
            self.assertEqual(row["cumulative_expenditure_provenance"], "unknown")

    def test_codex_reconciled_provider_total_is_not_a_computed_sum(self):
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.ingest import load_prices
        from mrtoken.export import session_summaries
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "provider-total", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-terra"}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {
                     "last_token_usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                     "total_token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            ingest_codex_file(conn, codex, load_prices())
            row = session_summaries(conn, "provider-total")[0]
            self.assertEqual(row["cumulative_expenditure_tokens"], 150)
            self.assertEqual(row["cumulative_expenditure_provenance"], "provider-reported")

    def test_codex_dedups_duplicate_token_count_and_flags_clamp(self):
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.ingest import load_prices
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            usage = {"input_tokens": 5000, "cached_input_tokens": 4000,
                     "output_tokens": 200, "reasoning_output_tokens": 50, "total_tokens": 5200}
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cxd", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-terra"}},
                # identical token_count emitted twice for one turn → must count ONCE
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": usage}}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": usage}}},
                # malformed: cached > input → fresh clamps to 0 and the anomaly is counted
                {"timestamp": "2026-06-01T00:00:03Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 100, "cached_input_tokens": 400,
                     "output_tokens": 10, "total_tokens": 110}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            r = ingest_codex_file(conn, codex, load_prices())
            self.assertEqual(r["model_calls"], 2)      # dup collapsed to 1, + the clamp row
            self.assertEqual(r["clamp_anomalies"], 1)  # cached>input surfaced, not silent
            tid = conn.execute("SELECT id FROM trace WHERE session_id='cxd'").fetchone()[0]
            rows = conn.execute("SELECT input_tokens, cache_read_input_tokens FROM model_call "
                                "WHERE trace_id=? ORDER BY timestamp", (tid,)).fetchall()
            self.assertEqual(tuple(rows[0]), (1000, 4000))  # fresh = 5000-4000
            self.assertEqual(tuple(rows[1]), (0, 400))      # clamped: max(0, 100-400)=0

    def test_reasoning_tokens_surfaced_in_session_summary(self):
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.ingest import load_prices
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cxr", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-terra"}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": 200,
                     "reasoning_output_tokens": 50, "total_tokens": 1200}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            ingest_codex_file(conn, codex, load_prices())
            rt, tot = conn.execute("SELECT reasoning_tokens, total_tokens FROM session_summary "
                                   "WHERE session_id='cxr'").fetchone()
            self.assertEqual(rt, 50)     # surfaced as an informational breakdown
            self.assertEqual(tot, 1200)  # input(1000)+output(200); reasoning NOT double-added

    def test_codex_model_call_carries_price_version(self):
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.ingest import load_prices
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cxp", "cwd": "/proj"}},
                {"timestamp": "2026-06-01T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.6-terra"}},
                {"timestamp": "2026-06-01T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            p = load_prices()
            ingest_codex_file(conn, codex, p)
            pv = conn.execute(
                "SELECT DISTINCT price_version FROM model_call mc "
                "JOIN trace t ON t.id=mc.trace_id WHERE t.session_id='cxp'").fetchone()[0]
            self.assertEqual(pv, p["version"])  # Codex rows now carry price provenance

    def test_claude_dedup_falls_back_to_uuid_when_id_missing(self):
        from mrtoken.ingest import ingest_file, load_prices
        with tempfile.TemporaryDirectory() as tmp:
            transcript = os.path.join(tmp, "s.jsonl")
            usage = {"input_tokens": 100, "output_tokens": 50}
            # two lines, NO message.id, same uuid → dedup on uuid to a single call
            write_jsonl(transcript, [
                {"type": "user", "message": {"content": "hi"}},
                {"type": "assistant", "sessionId": "s", "uuid": "u1", "cwd": tmp,
                 "message": {"model": "claude-opus-4-8", "usage": usage,
                             "content": [{"type": "text", "text": "ok"}]}},
                {"type": "assistant", "sessionId": "s", "uuid": "u1", "cwd": tmp,
                 "message": {"model": "claude-opus-4-8", "usage": usage,
                             "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                          "input": {"file_path": "/x"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result",
                             "tool_use_id": "t1", "content": "data"}]}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            r = ingest_file(conn, transcript, load_prices())
            self.assertEqual(r["model_calls"], 1)  # deduped on uuid despite missing message.id

    def test_stop_hook_ingests_codex_rollout(self):
        # Codex live integration: the SAME Stop hook, given a session with no Claude
        # transcript, finds the matching Codex rollout and ingests it (source='codex').
        import importlib.util, io, contextlib, sys as _sys, mrtoken, mrtoken.ingest
        backend = os.path.dirname(os.path.dirname(mrtoken.__file__))
        spec = importlib.util.spec_from_file_location(
            "on_stop_codex", os.path.join(backend, "hooks", "on_stop.py"))
        on_stop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(on_stop)
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = os.path.join(tmp, "codex", "2026", "06")
            os.makedirs(codex_dir)
            sid = "019efb64-cafe-7b80-8c75-deadbeef0001"
            write_jsonl(os.path.join(codex_dir, f"rollout-2026-06-24T00-00-00-{sid}.jsonl"), [
                {"timestamp": "2026-06-24T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": sid, "cwd": "/proj"}},
                {"timestamp": "2026-06-24T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.5"}},
                {"timestamp": "2026-06-24T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 200,
                     "total_tokens": 5200}, "model_context_window": 10000}}},
                {"timestamp": "2026-06-24T00:00:03Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 6000, "cached_input_tokens": 5000, "output_tokens": 150,
                     "total_tokens": 6150}, "model_context_window": 10000}}},
            ])
            db = os.path.join(tmp, "codex.db")
            on_stop.PROJECTS = os.path.join(tmp, "no-claude")  # no Claude transcript match
            on_stop.CODEX_DIRS = (os.path.join(tmp, "codex"),)
            # Codex branch writes to MRTOKEN_DB (overrides the central Codex DB);
            # point it at the temp DB so the test doesn't touch the real central store.
            orig_stdin, saved = _sys.stdin, os.environ.get("MRTOKEN_DB")
            os.environ["MRTOKEN_DB"] = db
            _sys.stdin = io.StringIO(json.dumps({"session_id": sid, "cwd": "/proj"}))
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    try:
                        on_stop.main()
                    except SystemExit:
                        pass
            finally:
                _sys.stdin = orig_stdin
                if saved is not None:
                    os.environ["MRTOKEN_DB"] = saved
                else:
                    os.environ.pop("MRTOKEN_DB", None)
            raw = sqlite3.connect(db)
            try:
                src = raw.execute(
                    "SELECT source FROM trace WHERE session_id=?", (sid,)).fetchone()
            finally:
                raw.close()
            self.assertIsNotNone(src)
            self.assertEqual(src[0], "codex")  # routed to the Codex adapter
            msg = json.loads(out.getvalue())["systemMessage"]
            self.assertIn("codex gpt-5.5", msg)
            self.assertIn("ctx 60%", msg)
            self.assertIn("~2,350 tok", msg)
            self.assertIn("cache 82%", msg)

    def test_codex_low_context_handoff_nudge_is_quiet(self):
        # Screenshot regression: a low-current-context Codex session can still be
        # long/expensive, but the hook should not print the old urgent "free up
        # your context window" handoff wall of text.
        import importlib.util, mrtoken
        backend = os.path.dirname(os.path.dirname(mrtoken.__file__))
        spec = importlib.util.spec_from_file_location(
            "on_stop_compact", os.path.join(backend, "hooks", "on_stop.py"))
        on_stop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(on_stop)

        self.assertEqual(on_stop._fmt_token_count(681_077), "681k")
        line = on_stop._compact_rec_line(
            "fresh_handoff",
            "This session has grown heavy. A fresh session with a compact handoff "
            "frees up your context window.",
            ctx_pct=28,
        )
        self.assertEqual(line, "  ·  long session: offer /mr-handoff at phase boundary")
        self.assertNotIn("context window", line)
        self.assertNotIn("grown heavy", line)

        high = on_stop._compact_rec_line("fresh_handoff", "x", ctx_pct=82)
        self.assertIn("context is pretty full", high)
        self.assertIn("want me to run /mr-handoff now?", high)

    def test_stop_hook_ingests_from_arbitrary_cwd(self):
        # ROADMAP 4.1 (regression guard): the now-global Stop hook resolves the
        # per-project DB from the session payload's cwd and ingests — the fix for
        # desktop-app sessions started in any folder. Locks it so it can't regress.
        import importlib.util, io, sys as _sys, mrtoken, mrtoken.ingest
        backend = os.path.dirname(os.path.dirname(mrtoken.__file__))
        spec = importlib.util.spec_from_file_location(
            "on_stop_test", os.path.join(backend, "hooks", "on_stop.py"))
        on_stop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(on_stop)
        with tempfile.TemporaryDirectory() as tmp:
            projects = os.path.join(tmp, "projects")
            os.makedirs(os.path.join(projects, "p"))
            sid = "sess-arb"
            write_jsonl(os.path.join(projects, "p", f"{sid}.jsonl"), [
                {"type": "assistant", "sessionId": sid, "uuid": "a1",
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "x"}]}},
                {"type": "assistant", "sessionId": sid, "uuid": "a2",
                 "message": {"id": "m2", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "y"}]}},
            ])
            db = os.path.join(tmp, "resolved.db")
            seen = {}
            def fake_default_db_path(cwd=None):
                seen["cwd"] = cwd
                return db
            on_stop.PROJECTS = projects
            orig = mrtoken.ingest.default_db_path
            mrtoken.ingest.default_db_path = fake_default_db_path
            orig_stdin = _sys.stdin
            saved_env = os.environ.pop("MRTOKEN_DB", None)  # ensure cwd-resolution path
            _sys.stdin = io.StringIO(json.dumps(
                {"session_id": sid, "cwd": "/some/arbitrary/folder"}))
            import contextlib
            try:
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        on_stop.main()
                except SystemExit:
                    pass
            finally:
                mrtoken.ingest.default_db_path = orig
                _sys.stdin = orig_stdin
                if saved_env is not None:
                    os.environ["MRTOKEN_DB"] = saved_env
            self.assertEqual(seen.get("cwd"), "/some/arbitrary/folder")  # used the payload cwd
            raw = sqlite3.connect(db)
            try:
                n = raw.execute(
                    "SELECT COUNT(*) FROM trace WHERE session_id=?", (sid,)).fetchone()[0]
            finally:
                raw.close()
            self.assertEqual(n, 1)  # and a trace landed in the cwd-resolved DB

    def test_explain_and_feedback_loop(self):
        # ROADMAP 5D.1 + 5D.2 — explain a fired signal's evidence; capture a verdict
        # and summarise labelled precision.
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.rules import analyse
        from mrtoken.feedback import (explain_session, record_feedback,
                                      feedback_summary)
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            path = os.path.join(tmp, "fb.jsonl")  # session_id derives from the filename
            write_jsonl(path, [
                {"type": "assistant", "sessionId": "fb", "uuid": "a1", "timestamp": "2026-06-01T00:00:00Z",
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 200_000}]}},
                {"type": "assistant", "sessionId": "fb", "uuid": "a2", "timestamp": "2026-06-01T00:00:01Z",
                 "message": {"id": "m2", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "ok"}]}},
            ])
            r = ingest_file(conn, path, load_prices())
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                               (r["session_id"],)).fetchone()[0]
            analyse(conn, tid)

            # explain: huge_tool_output fired, with decoded evidence
            ex = explain_session(conn, "fb")
            rules = {e["rule"] for e in ex}
            self.assertIn("huge_tool_output", rules)
            hto = next(e for e in ex if e["rule"] == "huge_tool_output")
            self.assertTrue(hto["evidence"])  # evidence decoded, not empty

            # feedback: bad verdict rejected; good one persists + summarises
            with self.assertRaises(ValueError):
                record_feedback(conn, "fb", "huge_tool_output", "maybe")
            record_feedback(conn, "fb", "huge_tool_output", "right", "real waste")
            record_feedback(conn, "fb", "huge_tool_output", "wrong")
            summ = feedback_summary(conn)["huge_tool_output"]
            self.assertEqual((summ["right"], summ["wrong"]), (1, 1))
            self.assertEqual(summ["labelled_precision"], 0.5)

    def test_offload_stashes_and_summarizes(self):
        # ROADMAP 6.1: offload writes full content to disk, returns a compact summary
        # + stash path, and keeps the bulk out of context.
        from mrtoken.offload import offload_content
        with tempfile.TemporaryDirectory() as tmp:
            big = "\n".join(f"line {i} lorem ipsum dolor" for i in range(500))
            r = offload_content(content=big, max_lines=20, stash_dir=tmp)
            self.assertEqual(r["lines"], 500)
            self.assertTrue(os.path.exists(r["stash_path"]))
            with open(r["stash_path"]) as fh:
                self.assertEqual(fh.read(), big)            # full content retrievable
            self.assertLess(len(r["summary"].splitlines()), 60)  # summary is compact
            self.assertGreater(r["est_tokens_saved"], 0)
            # query mode greps
            rq = offload_content(content="apple\nbanana\napricot", query="ap",
                                 stash_dir=tmp)
            self.assertIn("apple", rq["summary"])
            self.assertIn("apricot", rq["summary"])
            self.assertNotIn("banana", rq["summary"])
            # path mode reads a file
            p = os.path.join(tmp, "f.txt")
            with open(p, "w") as handle:
                handle.write("a\nb\nc\n")
            rp = offload_content(path=p, stash_dir=tmp)
            self.assertEqual(rp["lines"], 3)

    def test_mcp_server_lists_and_calls_offload(self):
        # ROADMAP 6.1: the MCP server exposes + dispatches the toolbox (both agents
        # speak MCP, so this equips Claude and Codex from one server).
        import mrtoken.offload as offmod
        import mrtoken.datadir as dd
        import mrtoken.savings as savings
        from mrtoken import mcp_server
        with tempfile.TemporaryDirectory() as tmp:
            orig = offmod.central_default
            dd_orig = dd.central_default
            offmod.central_default = lambda: tmp   # keep stash out of the real central store
            dd.central_default = lambda: tmp       # AND savings.record() (via toolbox._offload_call)
            try:
                # the savings path must resolve inside tmp BEFORE any tool call writes it
                self.assertTrue(savings._db_path().startswith(tmp))
                init = mcp_server.handle_request(
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18"}})
                self.assertEqual(init["result"]["serverInfo"]["name"], "mrtoken")
                self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")  # echoes client

                self.assertIsNone(mcp_server.handle_request(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}))  # notification

                tl = mcp_server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                self.assertIn("offload", [t["name"] for t in tl["result"]["tools"]])

                call = mcp_server.handle_request(
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "offload",
                                "arguments": {"content": "x\n" * 300, "max_lines": 10}}})
                res = call["result"]
                self.assertFalse(res["isError"])
                self.assertIn("kept out of context", res["content"][0]["text"])

                bad = mcp_server.handle_request(
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "nope", "arguments": {}}})
                self.assertTrue(bad["result"]["isError"])
            finally:
                offmod.central_default = orig
                dd.central_default = dd_orig

    def test_experiment_runner_groundwork(self):
        # ROADMAP 5A.1–5A.3 groundwork: the hugelib fixture's oracle plumbing works
        # (no API), and the runner's mock arms record reset + threshold fields.
        import importlib.util, io, contextlib, mrtoken
        backend = os.path.dirname(os.path.dirname(mrtoken.__file__))
        exp = os.path.join(backend, "experiments")
        spec = importlib.util.spec_from_file_location("exp_runner", os.path.join(exp, "runner.py"))
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        task = os.path.join(exp, "tasks", "debug-hugelib")
        manifest = runner.load_manifest(task)
        # reset_threshold_tokens is a per-fixture / per-study knob (89325c4 moved
        # debug-hugelib to 30k for the low-pressure arm study). This groundwork test
        # checks the plumbing, not a specific value — assert it's a positive int.
        self.assertIsInstance(manifest["reset_threshold_tokens"], int)
        self.assertGreater(manifest["reset_threshold_tokens"], 0)

        cont = runner.drive_agent(task, manifest, "/tmp/unused", "continue", mock=True)
        self.assertEqual(cont["reset_fired"], 0)
        for arm in ("handoff", "compact"):  # both wired now (compact was deferred)
            m = runner.drive_agent(task, manifest, "/tmp/unused", arm, mock=True)
            self.assertEqual(m["reset_fired"], 1)
            self.assertEqual(m["crossed_threshold"], 1)
            self.assertGreater(m["total_tokens"], 0)

        # fixture plumbing (no API): oracle fails on the buggy seed + immutability guard
        with contextlib.redirect_stdout(io.StringIO()):
            rc = runner.check_fixture(task)
        self.assertEqual(rc, 0)

    def test_manual_skill_installs_to_both_agents(self):
        # ROADMAP 6.3: the context-efficiency manual is a bundled skill, installed to
        # BOTH ~/.claude/skills and ~/.codex/skills (when Codex is present). Codex
        # also gets the shared Stop hook so live rollouts can auto-ingest.
        from mrtoken.install import (
            init, SKILLS_SRC, _load_settings, _already_installed,
            _codex_mcp_configured,
        )
        self.assertTrue(os.path.isfile(os.path.join(SKILLS_SRC, "mr-context", "SKILL.md")))
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as handle:
                handle.write("{}")
            gpath = os.path.join(tmp, "global-settings.json")
            os.makedirs(os.path.join(tmp, ".codex"))            # Codex present
            codex_skills = os.path.join(tmp, ".codex", "skills")
            codex_hooks = os.path.join(tmp, ".codex", "hooks.json")
            codex_config = os.path.join(tmp, ".codex", "config.toml")
            with open(codex_hooks, "w") as h:
                json.dump({"hooks": {"Stop": [{"hooks": [
                    {"type": "command", "command": "echo existing-codex"}]}]}}, h)
            with open(codex_config, "w") as h:
                h.write("[mcp_servers.existing]\ncommand = \"keepme\"\nargs = []\n")
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=codex_skills, codex_hooks_path=codex_hooks,
                 emit=lambda *_: None)
            claude_skills = os.path.join(tmp, "skills")          # next to global-settings.json
            self.assertTrue(os.path.isfile(os.path.join(claude_skills, "mr-context", "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(codex_skills, "mr-context", "SKILL.md")))
            ch = _load_settings(codex_hooks)
            self.assertTrue(_already_installed(ch))
            codex_cmds = [hh["command"] for e in ch["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertIn("echo existing-codex", codex_cmds)
            self.assertTrue(_codex_mcp_configured(codex_config))
            with open(codex_config, encoding="utf-8") as h:
                codex_toml = h.read()
            self.assertIn("[mcp_servers.existing]", codex_toml)

            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=codex_skills, codex_hooks_path=codex_hooks,
                 emit=lambda *_: None)
            ch2 = _load_settings(codex_hooks)
            codex_cmds2 = [hh["command"] for e in ch2["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertEqual(len(codex_cmds2), len(codex_cmds))
            with open(codex_config, encoding="utf-8") as h:
                self.assertEqual(h.read().count("[mcp_servers.mrtoken]"), 1)

    def test_intervention_policy_autonomy_and_kill_switch(self):
        # ROADMAP 6.5: per-tool autonomy (off|tell|ask|do) + global kill switch; default warn-only.
        import mrtoken.policy as policy
        with tempfile.TemporaryDirectory() as tmp:
            cfgp = os.path.join(tmp, "config.json")
            orig = policy._config_path
            policy._config_path = lambda: cfgp
            saved = os.environ.pop("MRTOKEN_INTERVENE", None)
            try:
                self.assertEqual(policy.autonomy("offload"), "tell")   # default = warn-only
                self.assertTrue(policy.kill_switch_on())
                policy.set_autonomy("offload", "ask")
                self.assertEqual(policy.autonomy("offload"), "ask")
                self.assertEqual(policy.autonomy("handoff"), "tell")   # untouched → default
                policy.set_autonomy("handoff", "off")
                self.assertEqual(policy.autonomy("handoff"), "off")
                with self.assertRaises(ValueError):
                    policy.set_autonomy("offload", "maybe")
                policy.set_enabled(False)                              # global kill switch
                self.assertEqual(policy.autonomy("offload"), "off")
                self.assertFalse(policy.kill_switch_on())
                policy.set_enabled(True)
                self.assertEqual(policy.autonomy("offload"), "ask")    # restored
                os.environ["MRTOKEN_INTERVENE"] = "off"                # env kill switch
                self.assertEqual(policy.autonomy("offload"), "off")
            finally:
                policy._config_path = orig
                os.environ.pop("MRTOKEN_INTERVENE", None)
                if saved is not None:
                    os.environ["MRTOKEN_INTERVENE"] = saved

    def test_proc_engine_fires_on_pressure_plus_junk(self):
        # ROADMAP 6.4: fire only when pressure AND reclaimable junk both trip.
        from mrtoken.intervene import evaluate
        iv = evaluate(82, None, ["huge_tool_output"])       # high ctx + big output
        self.assertIsNotNone(iv)
        self.assertEqual(iv["tool"], "offload")
        self.assertIsNotNone(evaluate(40, 2, ["re_read_loop"]))        # low turns-to-full + junk
        # COMPACTION-GATE phase 1: context_rot alone no longer leads with the drop.
        self.assertEqual(evaluate(85, None, ["context_rot"])["tool"], "offload")
        self.assertIsNone(evaluate(90, 1, ["low_cache"]))   # pressure but junk isn't reclaimable
        self.assertIsNone(evaluate(30, 20, ["huge_tool_output"]))  # junk but no pressure
        self.assertIsNone(evaluate(10, None, []))           # clean → silent

    def test_outcomes_auto_disable_a_degrading_tool(self):
        # ROADMAP 6.7: a tool whose outcomes trend negative auto-disables (policy off);
        # a healthy tool stays enabled. The "don't let it degrade me" guardrail.
        import mrtoken.policy as policy
        from mrtoken import outcomes
        with tempfile.TemporaryDirectory() as tmp:
            o_cd, p_cp = outcomes.central_default, policy._config_path
            outcomes.central_default = lambda: tmp
            policy._config_path = lambda: os.path.join(tmp, "config.json")
            saved = os.environ.pop("MRTOKEN_INTERVENE", None)
            try:
                self.assertEqual(policy.autonomy("offload"), "tell")   # default: on
                for _ in range(5):
                    outcomes.record("offload", -1)                     # consistently not helping
                self.assertTrue(outcomes.health("offload")["disable"])
                self.assertIn("offload", outcomes.enforce())
                self.assertEqual(policy.autonomy("offload"), "off")    # auto-disabled
                for _ in range(5):
                    outcomes.record("handoff", 1)                      # healthy
                self.assertNotIn("handoff", outcomes.enforce())
                self.assertEqual(policy.autonomy("handoff"), "tell")
            finally:
                outcomes.central_default = o_cd
                policy._config_path = p_cp
                if saved is not None:
                    os.environ["MRTOKEN_INTERVENE"] = saved

    def test_ask_policy_first_then_afk_escalation(self):
        # ROADMAP 6.6: first fire ASKS (propose + wait); inaction on a later turn
        # (same tool, context not improved) ESCALATES.
        import mrtoken.datadir as dd
        from mrtoken.intervene import apply_ask_policy
        with tempfile.TemporaryDirectory() as tmp:
            orig = dd.central_default
            dd.central_default = lambda: tmp
            try:
                iv1 = apply_ask_policy("s1", {"tool": "offload", "ctx_pct": 80,
                                              "level": "ask", "message": "base"})
                self.assertEqual(iv1["phase"], "ask")
                self.assertIn("Reply `go`", iv1["message"])
                iv2 = apply_ask_policy("s1", {"tool": "offload", "ctx_pct": 82,
                                              "level": "ask", "message": "base"})
                self.assertEqual(iv2["phase"], "escalate")     # AFK / inaction
                self.assertIn("STILL", iv2["message"])
                iv3 = apply_ask_policy("s1", {"tool": "handoff", "ctx_pct": 82,
                                              "level": "ask",
                                              "message": "We've done a lot. Do you want me to run `handoff` now?"})
                self.assertEqual(iv3["phase"], "ask")          # different tool → fresh ask
                self.assertIn("Do you want me to run `handoff` now?", iv3["message"])
                self.assertIn("Reply `go`", iv3["message"])
            finally:
                dd.central_default = orig

    def test_compaction_gate_context_rot_defaults_reversible(self):
        # COMPACTION-GATE phase 1: context_rot alone carries no disposable-vs-
        # load-bearing information (the 5A regime map shows a reset WINS on
        # disposable context and LOSES ~+20% on load-bearing), so the nudge must
        # not lead with the destructive drop. It routes to reversible `offload`;
        # handoff is mentioned only as an explicitly optional judgement call.
        from mrtoken.intervene import evaluate
        iv = evaluate(83, None, ["context_rot"])
        self.assertIsNotNone(iv)
        self.assertEqual(iv["tool"], "offload")             # not a lead-with-drop handoff
        self.assertIn("we've done a lot", iv["message"])
        self.assertIn("`handoff`", iv["message"])           # still surfaced as an option...
        self.assertIn("optional", iv["message"])            # ...but clearly optional
        self.assertNotIn("Do you want me to run `handoff` now?", iv["message"])
        # Disposable regime (scanlib-like): huge output under pressure → offload, unchanged.
        self.assertEqual(evaluate(85, None, ["huge_tool_output"])["tool"], "offload")
        # Load-bearing regime (speclib-like): re-paid content → offload, unchanged.
        self.assertEqual(evaluate(85, None, ["re_read_loop"])["tool"], "offload")
        self.assertEqual(evaluate(85, None, ["repeated_context"])["tool"], "offload")
        # context_rot alongside a load-bearing signal → the plain offload path.
        both = evaluate(85, None, ["context_rot", "re_read_loop"])
        self.assertEqual(both["tool"], "offload")
        self.assertNotIn("optional", both["message"])
        # Pressure with no reclaimable signal → still silent (unchanged).
        self.assertIsNone(evaluate(90, 1, ["low_cache"]))

    def test_compaction_gate_disposability_unlocks_drop(self):
        # COMPACTION-GATE phase 2 (Gate 1): a context_rot nudge may lead with the
        # destructive `handoff` ONLY when some reclaimable block is classified
        # disposable. Load-bearing, empty, or unknown (None — every caller that
        # doesn't pass the input) keeps phase 1's reversible offload + advisory.
        from mrtoken.intervene import evaluate
        disp = {"read:abc123": "disposable", "read:def456": "load_bearing"}
        iv = evaluate(85, None, ["context_rot"], disposability=disp)
        self.assertEqual(iv["tool"], "handoff")             # drop unlocked
        self.assertEqual(iv["disposability_source"], "proxy")
        # Proxy-unlocked drop reads as a QUESTION with the reversible out —
        # the proxy can't see future re-need (PR #19 finding).
        self.assertIn("Run `handoff`?", iv["message"])
        self.assertIn("`offload` instead", iv["message"])
        for blocked in ({"read:def456": "load_bearing"}, {}, None):
            iv = evaluate(85, None, ["context_rot"], disposability=blocked)
            self.assertEqual(iv["tool"], "offload")         # phase-1 behaviour
            self.assertIn("optional", iv["message"])
        # The offload routes must ignore the gate — never a blind drop.
        self.assertEqual(
            evaluate(85, None, ["re_read_loop"], disposability=disp)["tool"], "offload")
        self.assertEqual(
            evaluate(85, None, ["huge_tool_output"], disposability=disp)["tool"], "offload")

    def test_proxy_drop_never_escalates_past_tell(self):
        # PR #19 finding: the recency proxy can't tell the drop-wins regime from
        # the drop-loses one at pressure time, so a proxy-unlocked drop is capped
        # at L1 tell even when policy says ask/do. Only an EXPLICIT disposability
        # confirmation (disposable_confirmed — the future mr-context/toolbox
        # channel) may escalate. This is the line 6.8 auto-act must not cross.
        import mrtoken.datadir as dd
        import mrtoken.policy as policy
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            o_cd, p_cp = dd.central_default, policy._config_path
            dd.central_default = lambda: tmp
            policy._config_path = lambda: os.path.join(tmp, "config.json")
            saved = os.environ.pop("MRTOKEN_INTERVENE", None)
            try:
                policy.set_autonomy("handoff", "do")
                iv = intervene.decide("gx1", 85, None, ["context_rot"],
                                      disposability={"read:a": "disposable"})
                self.assertEqual(iv["tool"], "handoff")
                self.assertEqual(iv["level"], "tell")   # capped: proxy never auto-acts
                self.assertNotIn("phase", iv)           # never entered the ask policy
                self.assertNotIn("auto_act", iv)        # 6.8 executor never engaged
                iv2 = intervene.decide("gx2", 85, None, ["context_rot"],
                                       disposability={"read:a": "disposable_confirmed"})
                self.assertEqual(iv2["tool"], "handoff")
                self.assertEqual(iv2["level"], "do")    # explicit may escalate
            finally:
                dd.central_default, policy._config_path = o_cd, p_cp
                if saved is not None:
                    os.environ["MRTOKEN_INTERVENE"] = saved

    def test_autoact_l3_freemium_executor(self):
        # ROADMAP 6.8 (Zach's 2026-07-06 decision): the L3 `do` executor is a
        # freemium feature, built but DEFAULT-OFF. It EXECUTES only `handoff` at
        # do+escalate+explicit-disposability; every other tool stays advisory; a
        # metered 3-free-uses / paid-entitlement / degrade-to-manual layer sits on
        # top of the 6.8-pre safety gates enforced upstream.
        import mrtoken.autoact as autoact
        import mrtoken.datadir as dd
        import mrtoken.handoff as handoff
        import mrtoken.policy as policy
        from mrtoken import intervene, outcomes
        with tempfile.TemporaryDirectory() as tmp:
            o_cd, p_cp = dd.central_default, policy._config_path
            o_build = handoff.build_handoff
            dd.central_default = lambda: tmp
            policy._config_path = lambda: os.path.join(tmp, "config.json")
            outcomes.central_default = lambda: tmp
            handoff.build_handoff = lambda db, sid: "# Handoff — continue in a fresh session\n\n## Goal\nx"
            saved_iv = os.environ.pop("MRTOKEN_INTERVENE", None)
            saved_lic = os.environ.pop("MRTOKEN_LICENSE", None)

            def wired(tool="handoff", **kw):
                iv = {"tool": tool, "level": "do", "phase": "escalate",
                      "disposability_source": "explicit", "message": "base"}
                iv.update(kw)
                return iv
            try:
                # 1) trial: first free use EXECUTES and decrements the lifetime meter.
                self.assertEqual(autoact.free_uses_left(), 3)
                out = autoact.maybe_auto_act("s1", wired())
                self.assertTrue(out["auto_act"]["acted"])
                self.assertEqual(out["auto_act"]["reason"], "trial")
                self.assertIn("# Handoff", out["message"])       # the generated handoff
                self.assertEqual(autoact.free_uses_left(), 2)

                # 2) only handoff is wired — other do-level tools stay advisory.
                for t in ("offload", "compact", "confirm_disposable"):
                    o = autoact.maybe_auto_act("s1", wired(t))
                    self.assertNotIn("auto_act", o)
                    self.assertIn("auto-action pending", o["message"])
                self.assertEqual(autoact.free_uses_left(), 2)     # untouched by the above

                # 3) handoff before escalation (first-ask) does NOT execute.
                o = autoact.maybe_auto_act("s1", wired(phase="ask"))
                self.assertNotIn("auto_act", o)

                # 4) exhaust the free uses → degrade to manual + upsell, never hard-block,
                #    meter never goes negative.
                autoact.maybe_auto_act("s1", wired())
                autoact.maybe_auto_act("s1", wired())
                self.assertEqual(autoact.free_uses_left(), 0)
                spent = autoact.maybe_auto_act("s1", wired())
                self.assertFalse(spent["auto_act"]["acted"])
                self.assertEqual(spent["auto_act"]["reason"], "spent")
                self.assertIn("paid feature", spent["message"])
                self.assertNotIn("# Handoff", spent["message"])   # nothing auto-generated
                self.assertEqual(autoact.free_uses_left(), 0)

                # 5) paid entitlement acts even with zero free uses left (env stub).
                os.environ["MRTOKEN_LICENSE"] = "test-key"
                paid = autoact.maybe_auto_act("s1", wired())
                self.assertTrue(paid["auto_act"]["acted"])
                self.assertEqual(paid["auto_act"]["reason"], "paid")
                del os.environ["MRTOKEN_LICENSE"]

                # 6) builder failure fails closed — no free use spent (config entitlement here).
                policy._save({"entitlement": {"paid": True}})
                handoff.build_handoff = lambda db, sid: "mrtoken handoff: no transcript found"
                fail = autoact.maybe_auto_act("s1", wired())
                self.assertFalse(fail["auto_act"]["acted"])
                self.assertEqual(fail["auto_act"]["reason"], "builder_failed")
                policy._save({})   # back to default (no entitlement)

                # 7) a negative 6.7 trend auto-disables handoff BEFORE it can auto-act:
                #    with the tool off, decide() returns None (never reaches the executor).
                for _ in range(5):
                    outcomes.record("handoff", -1)
                self.assertIn("handoff", outcomes.enforce())
                self.assertEqual(policy.autonomy("handoff"), "off")
                self.assertIsNone(intervene.decide(
                    "s2", 85, None, ["context_rot"],
                    disposability={"read:a": "disposable_confirmed"}))

                # 8) DEFAULT-OFF: with no config, handoff sits at `tell`, so the
                #    explicit path never reaches `do` and nothing auto-acts.
                policy._save({})
                self.assertEqual(policy.autonomy("handoff"), "tell")
                iv = intervene.decide("s3", 85, None, ["context_rot"],
                                      disposability={"read:a": "disposable_confirmed"})
                self.assertEqual(iv["level"], "tell")
                self.assertNotIn("auto_act", iv)
            finally:
                dd.central_default, policy._config_path = o_cd, p_cp
                outcomes.central_default = o_cd
                handoff.build_handoff = o_build
                if saved_iv is not None:
                    os.environ["MRTOKEN_INTERVENE"] = saved_iv
                if saved_lic is not None:
                    os.environ["MRTOKEN_LICENSE"] = saved_lic

    def test_disposable_confirmation_channel(self):
        # The explicit disposability channel (disposable-confirmed-channel.md):
        # confirm_disposable records a session-scoped, metadata-only confirmation
        # that a FRESH read merges as `disposable_confirmed` (unlocking escalation),
        # and that goes stale by call-count OR by time (an old "yes" can't authorize
        # a later drop). Falsified proxy → only this explicit path may escalate.
        import datetime as _dt
        import mrtoken.datadir as dd
        from mrtoken import intervene, toolbox
        with tempfile.TemporaryDirectory() as tmp:
            o_cd, o_sc = dd.central_default, intervene._session_calls
            dd.central_default = lambda: tmp
            intervene._session_calls = lambda arg: ("sess-x", 20)   # stub transcript resolution
            try:
                sid, call = intervene.record_disposable_confirmation()
                self.assertEqual((sid, call), ("sess-x", 20))
                # fresh: within CONFIRM_TTL_CALLS more calls
                self.assertTrue(intervene._fresh_disposable_confirmation("sess-x", 25))
                # stale by calls
                self.assertFalse(intervene._fresh_disposable_confirmation(
                    "sess-x", 20 + intervene.CONFIRM_TTL_CALLS + 1))
                # absent session → not fresh (fail-closed: drop stays proxy-capped)
                self.assertFalse(intervene._fresh_disposable_confirmation("other", 20))
                # privacy: the record holds ONLY a call index + timestamp, no content
                with open(intervene._disposable_path("sess-x")) as fh:
                    data = json.load(fh)
                self.assertEqual(set(data), {"confirmed_at_call", "confirmed_at_ts"})
                # stale by time: an old confirmation expires even at the same turn
                old = (_dt.datetime.now(_dt.timezone.utc)
                       - _dt.timedelta(minutes=intervene.CONFIRM_TTL_MIN + 5)).isoformat()
                with open(intervene._disposable_path("sess-t"), "w") as fh:
                    json.dump({"confirmed_at_call": 20, "confirmed_at_ts": old}, fh)
                self.assertFalse(intervene._fresh_disposable_confirmation("sess-t", 21))
                # the tool is registered + toggleable like the others
                self.assertIn("confirm_disposable", toolbox.TOOL_REGISTRY)
                self.assertIn("confirm_disposable",
                              [s["name"] for s in toolbox.enabled_tool_schemas()])
            finally:
                dd.central_default, intervene._session_calls = o_cd, o_sc

    def test_confirm_disposable_refuses_ambiguous_no_arg_session(self):
        # Regression for the MCP boundary bug: with two active panes in the same
        # project, newest-mtime can be the OTHER session. No-arg confirmation must
        # fail closed and record nothing until the caller passes its session id.
        import time as _time
        import mrtoken.datadir as dd
        from mrtoken import intervene, toolbox, watch
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.realpath(os.path.join(tmp, "repo"))
            projects = os.path.join(tmp, "claude-projects")
            state = os.path.join(tmp, "state")
            os.makedirs(project, exist_ok=True)
            escaped = project.replace("/", "-").replace(".", "-")
            transcript_dir = os.path.join(projects, escaped)
            os.makedirs(transcript_dir, exist_ok=True)

            def assistant(sid, mid):
                # record a cwd: bucket discovery matches on it, and every real
                # transcript has one (108 of 108 checked on a live host)
                return {"type": "assistant", "sessionId": sid, "cwd": project, "message": {
                    "id": mid, "model": "x",
                    "usage": {"input_tokens": 10, "output_tokens": 1}}}

            a = os.path.join(transcript_dir, "sess-a.jsonl")
            b = os.path.join(transcript_dir, "sess-b.jsonl")
            write_jsonl(a, [assistant("sess-a", "a1"), assistant("sess-a", "a2")])
            write_jsonl(b, [assistant("sess-b", "b1")])
            now = _time.time()
            os.utime(a, (now - 20, now - 20))
            os.utime(b, (now, now))  # the other pane is newer

            o_cd, o_projects, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved_env = {k: os.environ.pop(k, None)
                         for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: state
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                txt, err = toolbox.call_tool("confirm_disposable", {})
                self.assertFalse(err)
                self.assertIn("multiple active sessions", txt)
                self.assertIn("session: <your session id>", txt)
                self.assertFalse(os.path.exists(intervene._disposable_path("sess-b")))

                txt2, err2 = toolbox.call_tool("confirm_disposable", {"session": "sess-a"})
                self.assertFalse(err2)
                self.assertIn("recorded", txt2)
                self.assertTrue(os.path.exists(intervene._disposable_path("sess-a")))
                self.assertFalse(os.path.exists(intervene._disposable_path("sess-b")))
            finally:
                os.chdir(o_cwd)
                dd.central_default, watch.PROJECTS = o_cd, o_projects
                for k, v in saved_env.items():
                    if v is not None:
                        os.environ[k] = v

    def test_confirm_disposable_single_session_no_arg_still_works(self):
        import time as _time
        import mrtoken.datadir as dd
        from mrtoken import intervene, toolbox, watch
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.realpath(os.path.join(tmp, "repo"))
            projects = os.path.join(tmp, "claude-projects")
            state = os.path.join(tmp, "state")
            os.makedirs(project, exist_ok=True)
            escaped = project.replace("/", "-").replace(".", "-")
            transcript_dir = os.path.join(projects, escaped)
            os.makedirs(transcript_dir, exist_ok=True)
            path = os.path.join(transcript_dir, "solo.jsonl")
            write_jsonl(path, [{"type": "assistant", "sessionId": "solo", "cwd": project, "message": {
                "id": "m1", "model": "x",
                "usage": {"input_tokens": 10, "output_tokens": 1}}}])
            now = _time.time()
            os.utime(path, (now, now))

            o_cd, o_projects, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved_env = {k: os.environ.pop(k, None)
                         for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: state
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                txt, err = toolbox.call_tool("confirm_disposable", {})
                self.assertFalse(err)
                self.assertIn("recorded", txt)
                self.assertTrue(os.path.exists(intervene._disposable_path("solo")))
            finally:
                os.chdir(o_cwd)
                dd.central_default, watch.PROJECTS = o_cd, o_projects
                for k, v in saved_env.items():
                    if v is not None:
                        os.environ[k] = v

    # ── R1.3: DISABLE passive context_rot; explicit confirmation is the handoff trigger ──
    def test_r13_explicit_confirmation_is_the_handoff_trigger(self):
        from mrtoken.intervene import evaluate
        confirmed = {"explicit:session": "disposable_confirmed"}
        # positive arm: fresh confirmation + pressure + signals=[] -> fires a handoff
        iv = evaluate(85, None, [], disposability=confirmed)
        self.assertIsNotNone(iv)
        self.assertEqual(iv["tool"], "handoff")
        self.assertEqual(iv["signals"], [])                       # no passive signal
        # negative arms
        self.assertIsNone(evaluate(85, None, [], disposability=None))          # no confirmation
        self.assertIsNone(evaluate(85, None, [], disposability={"b": "disposable"}))  # proxy alone
        self.assertIsNone(evaluate(50, None, [], disposability=confirmed))     # confirmation, no pressure
        # unrelated passive diagnostics unaffected (offload path still fires)
        self.assertEqual(evaluate(85, None, ["huge_tool_output"])["tool"], "offload")

    def test_r13_confirmation_files_sweep_and_fail_closed(self):
        import time as _time
        import mrtoken.datadir as dd
        from mrtoken import intervene, watch
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")   # _disposable_path -> <central>/state/
            os.makedirs(sd, exist_ok=True)
            o_cd = dd.central_default
            dd.central_default = lambda: central
            try:
                # (1) sweep: a stale file is deleted, a fresh one kept
                stale = os.path.join(sd, "disposable-stale.json")
                fresh = os.path.join(sd, "disposable-fresh.json")
                for f in (stale, fresh):
                    with open(f, "w") as h:
                        h.write("{}")
                old = _time.time() - (intervene.CONFIRM_TTL_MIN + 5) * 60
                os.utime(stale, (old, old))
                self.assertEqual(intervene._sweep_expired_confirmations(sd), 1)
                self.assertFalse(os.path.exists(stale))               # expired -> swept
                self.assertTrue(os.path.exists(fresh))                # valid -> kept
                # (2) fail closed: fill to the global max with fresh files
                for i in range(intervene.CONFIRM_FILES_MAX):
                    with open(os.path.join(sd, f"disposable-fill{i}.json"), "w") as h:
                        h.write("{}")
                before = len([f for f in os.listdir(sd) if f.startswith("disposable-")])
                # resolve a live session the proven way (cwd + PROJECTS), so record()
                # reaches the fail-closed guard rather than failing to resolve.
                project = os.path.realpath(os.path.join(tmp, "repo"))
                os.makedirs(project, exist_ok=True)
                projects = os.path.join(tmp, "claude-projects")
                escaped = project.replace("/", "-").replace(".", "-")
                tdir = os.path.join(projects, escaped)
                os.makedirs(tdir, exist_ok=True)
                write_jsonl(os.path.join(tdir, "solo.jsonl"), [{"type": "assistant",
                    "sessionId": "solo", "cwd": project, "message": {"id": "m1", "model": "x",
                    "usage": {"input_tokens": 10, "output_tokens": 1}}}])
                o_projects, o_cwd = watch.PROJECTS, os.getcwd()
                saved_env = {k: os.environ.pop(k, None)
                             for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
                watch.PROJECTS = projects
                os.chdir(project)
                try:
                    sid, _calls = intervene.record_disposable_confirmation()
                finally:
                    os.chdir(o_cwd)
                    watch.PROJECTS = o_projects
                    for k, v in saved_env.items():
                        if v is not None:
                            os.environ[k] = v
                self.assertIsNone(sid)                                # fail closed, not persisted
                self.assertFalse(os.path.exists(os.path.join(sd, "disposable-solo.json")))
                after = len([f for f in os.listdir(sd) if f.startswith("disposable-")])
                self.assertLessEqual(after, before)                  # no growth past the bound
            finally:
                dd.central_default = o_cd

    def test_r13_passive_context_rot_no_longer_emitted_live(self):
        from mrtoken.watch import LiveMonitor
        mon = LiveMonitor(emit=lambda _: None)
        # a large, declining cache sequence — under R1/R1.1/R1.2 this fired context_rot
        for i, cr in enumerate([135_000] * 30 + [45_000] * 30):
            mon.feed({"type": "assistant", "message": {"model": "claude-sonnet-4",
                      "usage": {"input_tokens": 5000, "cache_read_input_tokens": cr,
                                "cache_creation_input_tokens": 10000, "output_tokens": 20},
                      "content": [{"type": "text", "text": str(i)}]}})
        snap = mon.snapshot()
        self.assertNotIn("context_rot", snap["signals_fired"])    # passive signal disabled
        self.assertNotIn("_cache_hist", vars(mon))                # live machinery removed
        # unrelated diagnostics still fire: large context + a huge tool output
        mon.feed({"type": "assistant", "message": {"model": "claude-sonnet-4",
                  "usage": {"input_tokens": 5, "cache_read_input_tokens": 180_000, "output_tokens": 50},
                  "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}})
        mon.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 60_000}]}})
        sig = mon.snapshot()["signals_fired"]
        self.assertIn("context", sig)
        self.assertIn("huge_tool_output", sig)

    def test_r13_retention_counts_every_still_existing_file(self):
        # adversarial-1 correction 2: a file we cannot stat (metadata failure) or cannot
        # delete (deletion failure) STILL EXISTS and STILL COUNTS — no undercount.
        import time as _time
        from unittest import mock
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            sd = os.path.join(tmp, "state")
            os.makedirs(sd, exist_ok=True)
            meta = os.path.join(sd, "disposable-meta.json")     # fresh but stat will fail
            expd = os.path.join(sd, "disposable-expired.json")  # expired but delete will fail
            keep = os.path.join(sd, "disposable-keep.json")     # fresh, normal
            for f in (meta, expd, keep):
                with open(f, "w") as h:
                    h.write("{}")
            old = _time.time() - (intervene.CONFIRM_TTL_MIN + 5) * 60
            os.utime(expd, (old, old))
            real_mtime, real_remove = os.path.getmtime, os.remove
            def bad_mtime(path):
                if path.endswith("disposable-meta.json"):
                    raise OSError("injected metadata failure")
                return real_mtime(path)
            def bad_remove(path):
                if path.endswith("disposable-expired.json"):
                    raise OSError("injected deletion failure")
                return real_remove(path)
            with mock.patch("os.path.getmtime", side_effect=bad_mtime), \
                 mock.patch("os.remove", side_effect=bad_remove):
                remaining = intervene._sweep_expired_confirmations(sd)
            # intended assertions (a mutant that undercounts fails HERE, not on a crash):
            self.assertTrue(os.path.exists(meta), "metadata-failure file must not be deleted")
            self.assertTrue(os.path.exists(expd), "deletion-failure file must still exist")
            self.assertEqual(remaining, 3, "every still-existing file must count (no undercount)")

    def test_r13_cap_lock_fails_closed_when_contended(self):
        # adversarial-1 correction 2 (concurrent writers) via the PRIMITIVE, not a faked
        # race: while the exclusive lock is held, record() cannot enforce the bound and
        # must fail closed. flock on two separate opens conflicts even in one process.
        import fcntl
        import mrtoken.datadir as dd
        from mrtoken import intervene, watch
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            project = os.path.realpath(os.path.join(tmp, "repo"))
            os.makedirs(project, exist_ok=True)
            projects = os.path.join(tmp, "claude-projects")
            tdir = os.path.join(projects, project.replace("/", "-").replace(".", "-"))
            os.makedirs(tdir, exist_ok=True)
            write_jsonl(os.path.join(tdir, "solo.jsonl"), [{"type": "assistant",
                "sessionId": "solo", "cwd": project, "message": {"id": "m1", "model": "x",
                "usage": {"input_tokens": 10, "output_tokens": 1}}}])
            held = os.open(os.path.join(sd, ".disposable.lock"), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(held, fcntl.LOCK_EX)                    # hold the exclusive lock
            o_cd, o_projects, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved = {k: os.environ.pop(k, None) for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: central
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                sid, _c = intervene.record_disposable_confirmation()
            finally:
                os.chdir(o_cwd); dd.central_default, watch.PROJECTS = o_cd, o_projects
                fcntl.flock(held, fcntl.LOCK_UN); os.close(held)
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertIsNone(sid, "must fail closed while the cap lock is contended")
            self.assertFalse(os.path.exists(os.path.join(sd, "disposable-solo.json")))

    def test_r13_symlink_at_destination_is_refused_victim_unchanged(self):
        # adversarial-1 correction 3 + Trap 4: a pre-planted symlink at the destination
        # must be REFUSED — the outside victim's bytes must be UNCHANGED (not merely that
        # an exception was raised), and the symlink itself left untouched.
        import mrtoken.datadir as dd
        from mrtoken import intervene, watch
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            victim = os.path.join(tmp, "victim-outside-state.txt")
            with open(victim, "w") as h:
                h.write("SECRET-VICTIM-BYTES")
            os.symlink(victim, os.path.join(sd, "disposable-solo.json"))   # planted symlink at p
            project = os.path.realpath(os.path.join(tmp, "repo"))
            os.makedirs(project, exist_ok=True)
            projects = os.path.join(tmp, "claude-projects")
            tdir = os.path.join(projects, project.replace("/", "-").replace(".", "-"))
            os.makedirs(tdir, exist_ok=True)
            write_jsonl(os.path.join(tdir, "solo.jsonl"), [{"type": "assistant",
                "sessionId": "solo", "cwd": project, "message": {"id": "m1", "model": "x",
                "usage": {"input_tokens": 10, "output_tokens": 1}}}])
            o_cd, o_projects, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved = {k: os.environ.pop(k, None) for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: central
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                sid, _c = intervene.record_disposable_confirmation()
            finally:
                os.chdir(o_cwd); dd.central_default, watch.PROJECTS = o_cd, o_projects
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertIsNone(sid, "must refuse a symlink at the destination")
            with open(victim) as h:
                self.assertEqual(h.read(), "SECRET-VICTIM-BYTES")   # victim byte-unchanged
            self.assertTrue(os.path.islink(os.path.join(sd, "disposable-solo.json")))  # untouched

    def test_r13_refresh_same_session_persists(self):
        # F4 (Security) / Trap 1: record refuses on islink(p), NOT exists(p), so a
        # same-session second confirmation overwrites via temp + os.replace. A future
        # islink->exists tightening would silently kill same-session refresh; this catches it.
        import mrtoken.datadir as dd
        from mrtoken import intervene, watch
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            os.makedirs(os.path.join(central, "state"), exist_ok=True)
            project = os.path.realpath(os.path.join(tmp, "repo"))
            os.makedirs(project, exist_ok=True)
            projects = os.path.join(tmp, "cp")
            tdir = os.path.join(projects, project.replace("/", "-").replace(".", "-"))
            os.makedirs(tdir, exist_ok=True)
            write_jsonl(os.path.join(tdir, "solo.jsonl"), [{"type": "assistant", "sessionId": "solo", "cwd": project,
                "message": {"id": "m1", "model": "x", "usage": {"input_tokens": 10, "output_tokens": 1}}}])
            o_cd, o_pj, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved = {k: os.environ.pop(k, None) for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: central
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                first, _a = intervene.record_disposable_confirmation()
                second, _b = intervene.record_disposable_confirmation()   # same-session refresh
            finally:
                os.chdir(o_cwd); dd.central_default, watch.PROJECTS = o_cd, o_pj
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertEqual(first, "solo")
            self.assertEqual(second, "solo", "same-session refresh must persist (islink, not exists)")
            pth = os.path.join(central, "state", "disposable-solo.json")
            self.assertTrue(os.path.isfile(pth) and not os.path.islink(pth))

    def test_r13_rejects_traversing_or_malformed_session_id(self):
        # F2: a caller-supplied session id must be one safe basename; reject on BOTH the
        # write chokepoint (_disposable_path) and the read path (_fresh...), so no file
        # outside the store is ever written or read. No attacker required.
        import mrtoken.datadir as dd
        from mrtoken import intervene
        for bad in ("foo/../../victim", "../victim", "/etc/passwd", "", ".", "..", "a/b", "x\x00y"):
            self.assertFalse(intervene._valid_session_id(bad), repr(bad))
            with self.assertRaises(ValueError):
                intervene._disposable_path(bad)
        for good in ("solo", "404fa99f-c553-463e-9e82-b6b5faed72cf"):
            self.assertTrue(intervene._valid_session_id(good))
            self.assertTrue(intervene._disposable_path(good).endswith(f"disposable-{good}.json"))
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            os.makedirs(central, exist_ok=True)
            with open(os.path.join(central, "victim.json"), "w") as h:   # planted at traversal target
                json.dump({"confirmed_at_call": 0, "confirmed_at_ts": "2999-01-01T00:00:00+00:00"}, h)
            o_cd = dd.central_default
            dd.central_default = lambda: central
            try:
                self.assertFalse(intervene._fresh_disposable_confirmation("../victim", 0),
                                 "read path must reject a traversing id, not read outside the store")
            finally:
                dd.central_default = o_cd

    def test_r13_fails_closed_when_store_cannot_be_enumerated(self):
        # F1 (ordinary failure, NOT the hostile unenumerable-dir case which needs an excluded
        # writer): a transient OSError enumerating the store -> cannot establish the bound ->
        # _sweep returns None and record fails closed.
        from unittest import mock
        import mrtoken.datadir as dd
        from mrtoken import intervene, watch
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            with mock.patch("os.listdir", side_effect=OSError("injected enumeration failure")):
                self.assertIsNone(intervene._sweep_expired_confirmations(sd))
            project = os.path.realpath(os.path.join(tmp, "repo"))
            os.makedirs(project, exist_ok=True)
            projects = os.path.join(tmp, "cp")
            tdir = os.path.join(projects, project.replace("/", "-").replace(".", "-"))
            os.makedirs(tdir, exist_ok=True)
            write_jsonl(os.path.join(tdir, "solo.jsonl"), [{"type": "assistant", "sessionId": "solo", "cwd": project,
                "message": {"id": "m1", "model": "x", "usage": {"input_tokens": 10, "output_tokens": 1}}}])
            o_cd, o_pj, o_cwd = dd.central_default, watch.PROJECTS, os.getcwd()
            saved = {k: os.environ.pop(k, None) for k in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
            dd.central_default = lambda: central
            watch.PROJECTS = projects
            os.chdir(project)
            try:
                # inject at _count (not os.listdir) so session resolution is unaffected — a
                # genuine fail-closed, not a resolution short-circuit
                with mock.patch.object(intervene, "_count_existing_confirmations", return_value=None):
                    sid, _c = intervene.record_disposable_confirmation()
            finally:
                os.chdir(o_cwd); dd.central_default, watch.PROJECTS = o_cd, o_pj
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
            self.assertIsNone(sid, "must fail closed when the store cannot be enumerated")

    def test_r13_orphaned_temp_debris_is_bounded(self):
        # F3: an orphaned disp-tmp-* older than the TTL (debris from a failed replace+cleanup)
        # is swept, so repeated failures cannot accumulate; a fresh temp is kept.
        import time as _time
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            sd = os.path.join(tmp, "state")
            os.makedirs(sd, exist_ok=True)
            stale = os.path.join(sd, "disp-tmp-stale")
            fresh = os.path.join(sd, "disp-tmp-fresh")
            for f in (stale, fresh):
                with open(f, "w") as h:
                    h.write("x")
            old = _time.time() - (intervene.CONFIRM_TTL_MIN + 5) * 60
            os.utime(stale, (old, old))
            intervene._sweep_expired_confirmations(sd)
            self.assertFalse(os.path.exists(stale), "orphaned temp debris must be bounded")
            self.assertTrue(os.path.exists(fresh), "a fresh temp must not be swept")

    def test_r14_repeated_write_failures_cap_live_temp_debris(self):
        from unittest import mock
        import mrtoken.datadir as dd
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            o_cd = dd.central_default
            dd.central_default = lambda: central
            try:
                with mock.patch.object(intervene, "_session_calls", return_value=("solo", 1)), \
                     mock.patch("os.replace", side_effect=OSError("injected replace failure")), \
                     mock.patch("os.remove", side_effect=OSError("injected cleanup failure")):
                    results = [intervene.record_disposable_confirmation() for _ in range(69)]
                temps = [n for n in os.listdir(sd) if n.startswith("disp-tmp-")]
                self.assertTrue(all(sid is None for sid, _calls in results))
                self.assertEqual(len(temps), 1,
                                 "the first failed write must occupy the sole temp slot")
                self.assertLessEqual(len(temps), intervene.CONFIRM_FILES_MAX)
            finally:
                dd.central_default = o_cd

    def test_r14_at_cap_refreshes_existing_and_refuses_new_session(self):
        from unittest import mock
        import mrtoken.datadir as dd
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            existing = os.path.join(sd, "disposable-existing.json")
            with open(existing, "w") as h:
                h.write("{}")
            durable_max = intervene.CONFIRM_FILES_MAX - 1
            for i in range(durable_max - 1):
                with open(os.path.join(sd, f"disposable-fill{i}.json"), "w") as h:
                    h.write("{}")
            o_cd = dd.central_default
            dd.central_default = lambda: central
            resolve = lambda session: (session, 10 if session == "existing" else 11)
            try:
                with mock.patch.object(intervene, "_session_calls", side_effect=resolve):
                    refreshed, _ = intervene.record_disposable_confirmation("existing")
                    refused, _ = intervene.record_disposable_confirmation("new")
                self.assertEqual(refreshed, "existing",
                                 "an already-counted session must refresh at the cap")
                self.assertIsNone(refused, "a new session must be refused at the cap")
                self.assertFalse(os.path.exists(os.path.join(sd, "disposable-new.json")))
            finally:
                dd.central_default = o_cd

    def test_r14_mixed_population_shares_one_global_cap(self):
        from unittest import mock
        import mrtoken.datadir as dd
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            durable_max = intervene.CONFIRM_FILES_MAX - 1
            for i in range(durable_max):
                session = "existing" if i == 0 else f"fill{i}"
                with open(os.path.join(sd, f"disposable-{session}.json"), "w") as h:
                    h.write("{}")
            o_cd = dd.central_default
            dd.central_default = lambda: central
            try:
                with mock.patch.object(intervene, "_session_calls",
                                       return_value=("existing", 10)), \
                     mock.patch("os.replace", side_effect=OSError("injected replace failure")), \
                     mock.patch("os.remove", side_effect=OSError("injected cleanup failure")):
                    results = [intervene.record_disposable_confirmation("existing")
                               for _ in range(69)]
                names = os.listdir(sd)
                confirmations = sum(n.startswith("disposable-") and n.endswith(".json")
                                    for n in names)
                temps = sum(n.startswith("disp-tmp-") for n in names)
                self.assertTrue(all(sid is None for sid, _calls in results))
                self.assertEqual((confirmations, temps),
                                 (durable_max, 1))
                self.assertLessEqual(
                    confirmations + temps, intervene.CONFIRM_FILES_MAX,
                    "confirmations plus live/orphan temps must share one global 64-file cap")
            finally:
                dd.central_default = o_cd

    def test_r14_legacy_64_confirmation_state_refuses_without_growth(self):
        from unittest import mock
        import mrtoken.datadir as dd
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            central = os.path.join(tmp, "central")
            sd = os.path.join(central, "state")
            os.makedirs(sd, exist_ok=True)
            for i in range(intervene.CONFIRM_FILES_MAX):
                session = "existing" if i == 0 else f"fill{i}"
                with open(os.path.join(sd, f"disposable-{session}.json"), "w") as h:
                    h.write("{}")
            o_cd = dd.central_default
            dd.central_default = lambda: central
            try:
                with mock.patch.object(intervene, "_session_calls",
                                       return_value=("existing", 10)):
                    refused, _ = intervene.record_disposable_confirmation("existing")
                names = os.listdir(sd)
                self.assertIsNone(refused)
                self.assertEqual(sum(n.startswith("disposable-") for n in names),
                                 intervene.CONFIRM_FILES_MAX)
                self.assertFalse(any(n.startswith("disp-tmp-") for n in names),
                                 "legacy over-cap state must not grow a temp")
            finally:
                dd.central_default = o_cd

    def test_new_session_does_not_inherit_prior_transcript(self):
        # inbox:mr-token-session-state-fix-20260802 — at session start the supplied
        # transcript_path may not exist yet; the old code fell back to newest-file
        # resolution, picked up the PREVIOUS session's transcript, and its ctx%
        # poisoned this session's debounce watermark (proc-<id>.json). Fix: a
        # supplied-but-missing transcript_path resolves to "nothing to decide",
        # never another session's file.
        import mrtoken.datadir as dd
        import mrtoken.watch as watch
        from mrtoken import intervene
        with tempfile.TemporaryDirectory() as tmp:
            dd_o, rp_o = dd.central_default, watch.resolve_path
            dd.central_default = lambda: os.path.join(tmp, "central")
            calls = []
            watch.resolve_path = lambda arg: calls.append(arg)  # spy; returns None (hermetic)
            try:
                missing = os.path.join(tmp, "newsession.jsonl")  # transcript not written yet
                iv = intervene.intervention_for_session(transcript_path=missing,
                                                        session_id="newsession")
                self.assertIsNone(iv)               # nothing to decide from a missing transcript
                self.assertEqual(calls, [])          # never fell back to newest-file resolution
                self.assertFalse(os.path.exists(     # so no poisoned debounce state was written
                    intervene._state_path("newsession")))
            finally:
                dd.central_default, watch.resolve_path = dd_o, rp_o

    def test_cohort_gate(self):
        # Stage-1 staged pullback: automatic surfaces self-gate on an allowlist.
        import mrtoken.cohort as cohort
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "config.json")
            o_cfg = cohort._CONFIG
            o_env = os.environ.pop("MRTOKEN_COHORT", None)
            cohort._CONFIG = cfg
            try:
                # no allowlist (config absent, env unset) => everything in-cohort (default)
                self.assertTrue(cohort.in_cohort("/any/where"))
                self.assertTrue(cohort.in_cohort(None))
                # config allowlist => only listed roots + their subdirs
                projA = os.path.realpath(os.path.join(tmp, "projA"))
                os.makedirs(projA)
                with open(cfg, "w") as fh:
                    json.dump({"cohort": [projA]}, fh)
                self.assertTrue(cohort.in_cohort(projA))
                self.assertTrue(cohort.in_cohort(os.path.join(projA, "sub", "dir")))
                self.assertFalse(cohort.in_cohort(os.path.join(tmp, "projB")))
                self.assertFalse(cohort.in_cohort(None))   # fail-closed once allowlisted
                # env override wins over the config file
                os.environ["MRTOKEN_COHORT"] = os.path.join(tmp, "projB")
                self.assertTrue(cohort.in_cohort(os.path.join(tmp, "projB")))
                self.assertFalse(cohort.in_cohort(projA))
            finally:
                cohort._CONFIG = o_cfg
                os.environ.pop("MRTOKEN_COHORT", None)
                if o_env is not None:
                    os.environ["MRTOKEN_COHORT"] = o_env

    def test_stop_hook_free_exit_out_of_cohort(self):
        # The Stop hook must early-exit(0) for an out-of-cohort session BEFORE opening
        # any DB (connect() writes on open) — proving the gate is genuinely free.
        import io, contextlib, importlib.util, sys
        import mrtoken, mrtoken.cohort as cohort, mrtoken.ingest as ingest
        backend = os.path.dirname(os.path.dirname(mrtoken.__file__))
        spec = importlib.util.spec_from_file_location(
            "on_stop_t", os.path.join(backend, "hooks", "on_stop.py"))
        on_stop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(on_stop)
        with tempfile.TemporaryDirectory() as tmp:
            projA = os.path.realpath(os.path.join(tmp, "projA"))
            os.makedirs(projA)
            cfg = os.path.join(tmp, "config.json")
            with open(cfg, "w") as fh:
                json.dump({"cohort": [projA]}, fh)
            o_cfg, o_stdin, o_argv, o_connect = (
                cohort._CONFIG, sys.stdin, sys.argv, ingest.connect)
            o_env = os.environ.pop("MRTOKEN_COHORT", None)
            hit = {"connect": False}
            cohort._CONFIG = cfg
            ingest.connect = lambda *a, **k: (hit.__setitem__("connect", True) or o_connect(*a, **k))
            try:
                sys.argv = ["on_stop"]
                sys.stdin = io.StringIO(json.dumps(
                    {"session_id": "s1", "cwd": os.path.join(tmp, "OTHER")}))  # out of cohort
                out = io.StringIO()
                with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(out):
                    on_stop.main()
                self.assertEqual(cm.exception.code, 0)     # clean early exit
                self.assertFalse(hit["connect"])           # no DB opened (free, no write)
                self.assertEqual(out.getvalue().strip(), "")  # no token-costing output
            finally:
                cohort._CONFIG, sys.stdin, sys.argv, ingest.connect = (
                    o_cfg, o_stdin, o_argv, o_connect)
                if o_env is not None:
                    os.environ["MRTOKEN_COHORT"] = o_env

    def test_stage2_repair1_attributable_realized_row(self):
        # Repair 1: a newly written realized row joins to exactly one trace and one
        # provider; legacy (empty session_id) rows are excluded, never backfilled.
        import mrtoken.datadir as dd
        import mrtoken.savings as savings
        from mrtoken.ingest import connect, now_iso
        with tempfile.TemporaryDirectory() as tmp:
            o_cd = dd.central_default
            dd.central_default = lambda: os.path.join(tmp, "central")   # temp savings.db
            try:
                savings.record("offload", 1234, session_id="s1", source="claude",
                               rule="huge_tool_output", project_key="/proj")
                savings.record("offload", 999)   # legacy: no attribution
                attributed = savings.attributed_rows()                 # read-only
                self.assertEqual(len(attributed), 1)                    # legacy excluded
                _tool, _tok, sid, src, rule, _pk, _ts = attributed[0]
                self.assertEqual((sid, src, rule), ("s1", "claude", "huge_tool_output"))
                # joins to exactly one trace / one provider in a temp main DB
                mconn = connect(os.path.join(tmp, "main.db"))
                mconn.execute("INSERT INTO trace(source,session_id,ingested_at) VALUES(?,?,?)",
                              ("claude_code", sid, now_iso()))
                mconn.commit()
                provs = mconn.execute("SELECT DISTINCT source FROM trace WHERE session_id=?",
                                      (sid,)).fetchall()
                mconn.close()
                self.assertEqual(len(provs), 1)
            finally:
                dd.central_default = o_cd

    def test_stage2_repair2_union_no_double_count(self):
        # UNWIRED DESIGN ARTIFACT: no production caller; claims-emitting rules model never built; current rules emit no unit-id claims and recommendation persists none.
        # Repair 2: three rules firing on one block => that block counted ONCE.
        from mrtoken.ingest import connect, now_iso
        from mrtoken.measure import union_addressable_tokens
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "m.db"))
            conn.execute("INSERT INTO trace(id,source,session_id,ingested_at) VALUES(1,'claude_code','s1',?)",
                         (now_iso(),))
            conn.execute("INSERT INTO context_block(trace_id,block_type,hash,token_count) VALUES(1,'file','H',1000)")
            conn.commit()
            claims = [(1, "H", "file"), (1, "H", "file"), (1, "H", "file")]
            self.assertEqual(union_addressable_tokens(conn, claims), 1000)   # once, not 3000
            conn.execute("INSERT INTO context_block(trace_id,block_type,hash,token_count) VALUES(1,'tool','K',500)")
            conn.commit()
            self.assertEqual(union_addressable_tokens(conn, claims + [(1, "K", "tool")]), 1500)
            conn.close()

    def test_stage2_repair3_outcome_from_actuals(self):
        # Repair 3: outcome from measured model_call columns only, never est_savings.
        from mrtoken.ingest import connect, now_iso
        from mrtoken.measure import measured_task_tokens
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "m.db"))
            conn.execute("INSERT INTO trace(id,source,session_id,ingested_at) VALUES(1,'claude_code','s1',?)",
                         (now_iso(),))
            conn.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,"
                         "cache_read_input_tokens,reasoning_tokens,est_cost_usd) VALUES(1,100,50,200,10,0.5)")
            conn.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,"
                         "cache_creation_input_tokens,est_cost_usd) VALUES(1,20,5,30,0.1)")
            conn.commit()
            m = measured_task_tokens(conn, [1])
            self.assertEqual((m["input"], m["output"], m["cache"], m["reasoning"]), (120, 55, 230, 10))
            self.assertEqual(m["total_tokens"], 175)
            self.assertAlmostEqual(m["est_cost_usd"], 0.6)
            self.assertEqual(measured_task_tokens(conn, [])["total_tokens"], 0)  # empty => zeros
            conn.close()

    def test_stage2_savings_isolation(self):
        # R1/R2 regression: central_default is resolved THROUGH the module (so patching
        # isolates from the live store), and reads are read-only — reading a MISSING
        # store returns empty WITHOUT creating one.
        import mrtoken.datadir as dd
        import mrtoken.savings as savings
        with tempfile.TemporaryDirectory() as tmp:
            o = dd.central_default
            dd.central_default = lambda: os.path.join(tmp, "central")
            try:
                self.assertTrue(savings._db_path().startswith(tmp))   # redirected, not live
                savings.record("offload", 5, session_id="x", source="claude", rule="r")
                self.assertTrue(os.path.exists(os.path.join(tmp, "central", "savings.db")))
                # a read of a MISSING store returns empty and creates nothing
                dd.central_default = lambda: os.path.join(tmp, "absent")
                self.assertEqual(savings.realized(), {"total": 0, "by_tool": {}})
                self.assertEqual(savings.attributed_rows(), [])
                self.assertFalse(os.path.exists(os.path.join(tmp, "absent")))
            finally:
                dd.central_default = o

    # ── spend-governance MVP: advisory task-spend policy (spendpolicy.evaluate_spend) ──
    # Provider-neutral, hermetic: pure functions over INJECTED prices/estimates. No DB,
    # no network, no live pricing. Verifies the auditable allow/escalate/deny verdict.
    def test_spendpolicy_allow_recommends_cheapest_capable(self):
        from mrtoken.spendpolicy import evaluate_spend, ALLOW
        task = {"id": "t", "est_input_tokens": 100_000, "est_output_tokens": 20_000}
        cands = [
            {"model": "big", "capability": 3, "price": {"input": 10.0, "output": 50.0}},
            {"model": "mid", "capability": 2, "price": {"input": 3.0, "output": 15.0}},
        ]
        r = evaluate_spend(task, cands, {"min_capability": 2, "escalate_usd": 5.0, "max_task_usd": 10.0})
        self.assertEqual(r["decision"], ALLOW)
        self.assertEqual(r["recommended_model"], "mid")   # cheaper of the two capable
        # 100k*3/1e6 + 20k*15/1e6 = 0.3 + 0.3 = 0.6
        self.assertAlmostEqual(r["projected_cost_usd"], 0.6, places=6)
        self.assertTrue(r["advisory"])
        self.assertTrue(r["reasons"] and any("allow" in x for x in r["reasons"]))
        self.assertEqual([x["model"] for x in r["ranked"]], ["mid", "big"])  # cheapest first

    def test_spendpolicy_escalate_between_thresholds(self):
        from mrtoken.spendpolicy import evaluate_spend, ESCALATE
        task = {"est_input_tokens": 1_000_000, "est_output_tokens": 0}   # 1M in
        cands = [{"model": "m", "capability": 2, "price": {"input": 3.0, "output": 15.0}}]
        # cost = 3.0; escalate at 1.0, budget 10.0 -> between -> escalate
        r = evaluate_spend(task, cands, {"escalate_usd": 1.0, "max_task_usd": 10.0})
        self.assertEqual(r["decision"], ESCALATE)
        self.assertEqual(r["recommended_model"], "m")
        self.assertAlmostEqual(r["projected_cost_usd"], 3.0, places=6)

    def test_spendpolicy_deny_over_budget(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        task = {"est_input_tokens": 1_000_000, "est_output_tokens": 0}
        cands = [{"model": "m", "capability": 2, "price": {"input": 3.0, "output": 15.0}}]
        r = evaluate_spend(task, cands, {"max_task_usd": 1.0})   # 3.0 > 1.0
        self.assertEqual(r["decision"], DENY)
        self.assertEqual(r["recommended_model"], "m")            # still names the cheapest capable
        self.assertTrue(any("exceeds the per-task budget" in x for x in r["reasons"]))

    def test_spendpolicy_deny_no_capability_is_distinct_from_over_budget(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        task = {"est_input_tokens": 10, "est_output_tokens": 10}   # trivially cheap
        cands = [{"model": "weak", "capability": 1, "price": {"input": 1.0, "output": 5.0}}]
        r = evaluate_spend(task, cands, {"min_capability": 3, "max_task_usd": 100.0})
        self.assertEqual(r["decision"], DENY)
        self.assertIsNone(r["recommended_model"])                 # nothing eligible to recommend
        self.assertTrue(any("required capability" in x for x in r["reasons"]))
        self.assertFalse(any("budget" in x for x in r["reasons"]))  # not a budget denial

    def test_spendpolicy_provider_neutral_and_downgrade_note(self):
        # Arbitrary non-repo model ids + injected prices: the verdict follows the injected
        # numbers, not prices.json. A cheaper-but-ineligible option is surfaced for audit.
        from mrtoken.spendpolicy import evaluate_spend, ALLOW
        task = {"est_input_tokens": 100_000, "est_output_tokens": 100_000}
        cands = [
            {"model": "vendor-x-nano", "capability": 1, "price": {"input": 0.5, "output": 1.0}},
            {"model": "vendor-y-pro",  "capability": 3, "price": {"input": 4.0, "output": 12.0}},
        ]
        r = evaluate_spend(task, cands, {"min_capability": 2})   # no budget thresholds
        self.assertEqual(r["decision"], ALLOW)                   # no cap set -> allow
        self.assertEqual(r["recommended_model"], "vendor-y-pro")  # only eligible one
        self.assertTrue(any("was excluded: capability tier" in x for x in r["reasons"]))
        self.assertIn("estimate", r["caveat"].lower())           # honest cost caveat present

    def test_spendpolicy_bridge_uses_injected_price_table_not_live(self):
        # candidates_from_prices reuses ingest.price_for over an INJECTED table; verifies
        # the projection matches the per-million math (parallels ingest.est_cost).
        from mrtoken.ingest import load_prices
        from mrtoken.spendpolicy import candidates_from_prices, project_task_cost
        prices = load_prices()
        cands = candidates_from_prices(prices, [("claude-haiku-4-5", 1), ("claude-opus-5", 3)])
        self.assertEqual({c["model"] for c in cands},
                         {"claude-haiku-4-5", "claude-opus-5"})
        task = {"est_input_tokens": 1_000_000, "est_output_tokens": 0}
        haiku = next(c for c in cands if "haiku" in c["model"])
        # haiku input rate is 1.0/M in the injected table -> 1.0 for 1M input tokens
        self.assertAlmostEqual(project_task_cost(haiku["price"], task), 1.0, places=6)

    # ── numeric-safety regressions (independent review defect: negative/non-finite
    # numerics bypassed the budget gate — negative est -> negative cost sorts cheapest and
    # passes every cap; nan -> every '>' is False and also passes). Reject, not clamp. ──
    def test_spendpolicy_rejects_negative_token_estimate(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        # the exact reviewer repro: previously returned ALLOW at projected_cost_usd=-10.0
        r = evaluate_spend({"est_input_tokens": -1_000_000, "est_output_tokens": 0},
                           [{"model": "m", "capability": 0, "price": {"input": 10.0}}],
                           {"max_task_usd": 0.01})
        self.assertEqual(r["decision"], DENY)          # was ALLOW — bypass closed
        self.assertNotEqual(r["decision"], "allow")
        self.assertIsNone(r["projected_cost_usd"])     # never computes a negative cost
        self.assertNotIn("max_task_tokens", r["policy"])
        self.assertTrue(any("invalid input rejected" in x for x in r["reasons"]))
        self.assertTrue(any("est_input_tokens" in x for x in r["reasons"]))

    def test_spendpolicy_rejects_non_finite_estimate(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        r = evaluate_spend({"est_input_tokens": float("nan"), "est_output_tokens": 0},
                           [{"model": "m", "capability": 1, "price": {"input": 10.0}}],
                           {"max_task_usd": 0.01})
        self.assertEqual(r["decision"], DENY)          # nan would have slipped under the cap
        self.assertIsNone(r["projected_cost_usd"])

    def test_spendpolicy_rejects_negative_capability_and_price(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        r = evaluate_spend({"est_input_tokens": 100, "est_output_tokens": 100},
                           [{"model": "m", "capability": -1, "price": {"input": -10.0}}],
                           {"max_task_usd": 1.0})
        self.assertEqual(r["decision"], DENY)
        self.assertIsNone(r["recommended_model"])
        joined = " ".join(r["reasons"])
        self.assertIn("m.capability=-1", joined)
        self.assertIn("m.price.input=-10.0", joined)

    def test_spendpolicy_rejects_non_finite_budget_cap(self):
        # same-root-cause edge: a nan budget cap would make `cost > max_usd` always False
        # and bypass the deny path — reject the policy threshold too.
        from mrtoken.spendpolicy import evaluate_spend, DENY
        r = evaluate_spend({"est_input_tokens": 1_000_000, "est_output_tokens": 0},
                           [{"model": "m", "capability": 1, "price": {"input": 10.0}}],
                           {"max_task_usd": float("nan")})
        self.assertEqual(r["decision"], DENY)
        self.assertTrue(any("policy.max_task_usd" in x for x in r["reasons"]))

    def test_project_task_cost_raises_on_negative_or_non_finite(self):
        from mrtoken.spendpolicy import project_task_cost
        with self.assertRaises(ValueError):
            project_task_cost({"input": 10.0}, {"est_input_tokens": -1})
        with self.assertRaises(ValueError):
            project_task_cost({"input": float("inf")}, {"est_input_tokens": 1})
        # valid inputs still compute normally (no false positive)
        self.assertAlmostEqual(
            project_task_cost({"input": 3.0}, {"est_input_tokens": 1_000_000}), 3.0, places=6)

    # ── spend-governance dry-run harness (customer-use-case vertical proof) ──
    # Demonstrates the CTO/CFO control end-to-end over injected task/candidate/price data:
    # cap spend, compare eligible models, recommend the lower-cost suitable one, auditable
    # allow/escalate/deny. Pure — no provider/DB/config; deterministic output.
    def test_spend_demo_covers_allow_escalate_deny(self):
        from mrtoken.spend_demo import run_all
        rows = run_all()
        self.assertEqual([r["name"] for r in rows],
                         ["cheap-task-allow", "premium-required-escalate", "over-budget-deny"])
        self.assertEqual([r["decision"] for r in rows], ["allow", "escalate", "deny"])
        for r in rows:                                  # every row is a full auditable record
            self.assertTrue(r["advisory"])
            self.assertTrue(r["reasons"])
            self.assertIn("estimate", r["caveat"].lower())

    def test_spend_demo_recommends_lower_cost_suitable(self):
        from mrtoken.spend_demo import run_all
        allow, escalate, deny = run_all()
        # allow: floor=1 -> cheapest eligible is the nano tier, not the pricier capable ones
        self.assertEqual(allow["recommended_model"], "vendor-nano")
        self.assertAlmostEqual(allow["projected_cost_usd"], 0.013, places=6)
        # escalate: floor=3 forces the only eligible (premium) model; cheaper ones excluded
        self.assertEqual(escalate["recommended_model"], "vendor-max")
        self.assertTrue(any("was excluded: capability tier" in x for x in escalate["reasons"]))
        # deny: names the cheapest SUITABLE model even though it blows the budget cap
        self.assertEqual(deny["recommended_model"], "vendor-mini")
        self.assertTrue(any("exceeds the per-task budget" in x for x in deny["reasons"]))

    def test_spend_demo_render_deterministic_and_auditable(self):
        from mrtoken.spend_demo import run_all, render_decision, demo
        row = run_all()[0]
        text_a, text_b = render_decision(row), render_decision(row)
        self.assertEqual(text_a, text_b)                # byte-stable: no timestamp/randomness
        self.assertEqual(demo(), demo())                # whole demo reproducible
        self.assertIn("ALLOW", text_a)
        self.assertIn("vendor-nano", text_a)
        self.assertIn("advisory — not enforced against a live agent", text_a)
        for why in row["reasons"]:                      # every reason appears in the record
            self.assertIn(why, text_a)

    def test_spend_demo_provider_neutral_custom_scenario(self):
        # A caller-supplied scenario with novel fake vendors + injected prices: the verdict
        # follows the injected numbers, proving no dependence on prices.json / a real roster.
        from mrtoken.spend_demo import run_scenario
        scenario = {
            "name": "custom", "task": {"id": "t", "est_input_tokens": 1_000_000,
                                       "est_output_tokens": 0, "min_capability": 2},
            "candidates": [
                {"model": "acme-lite", "capability": 1, "price": {"input": 0.1, "output": 0.1}},
                {"model": "acme-heavy", "capability": 2, "price": {"input": 4.0, "output": 4.0}},
            ],
            "policy": {"min_capability": 2, "max_task_usd": 10.0},
        }
        r = run_scenario(scenario)
        self.assertEqual(r["name"], "custom")
        self.assertEqual(r["task_id"], "t")
        self.assertEqual(r["decision"], "allow")
        self.assertEqual(r["recommended_model"], "acme-heavy")   # only eligible; cheaper one excluded
        self.assertAlmostEqual(r["projected_cost_usd"], 4.0, places=6)

    # ── follow-on: optional provider-neutral policy.max_task_tokens (per-task token cap) ──
    # Absent => behaviour exactly as before. Present => caps the SUM of the four estimated
    # token fields; strictly over-cap is its own DENY, distinct from capability/$ denial.
    # Invalid caps/tokens fail closed through the same _collect_invalid/_bad_number path.
    def test_max_task_tokens_absent_preserves_behavior(self):
        from mrtoken.spendpolicy import evaluate_spend, ALLOW
        task = {"est_input_tokens": 1000, "est_output_tokens": 0, "min_capability": 1}
        cands = [{"model": "m", "capability": 1, "price": {"input": 0.001, "output": 0.0}}]
        r = evaluate_spend(task, cands, {"min_capability": 1})       # no max_task_tokens
        self.assertEqual(r["decision"], ALLOW)                       # verdict unchanged
        self.assertNotIn("max_task_tokens", r["policy"])             # normal-path shape untouched
        self.assertFalse(any("token cap" in x for x in r["reasons"]))

    def test_max_task_tokens_boundaries_under_exact_over(self):
        from mrtoken.spendpolicy import evaluate_spend, ALLOW, DENY
        task = {"est_input_tokens": 1000, "est_output_tokens": 0, "min_capability": 1}  # sum=1000
        cands = [{"model": "m", "capability": 1, "price": {"input": 0.001, "output": 0.0}}]
        r_exact = evaluate_spend(task, cands, {"min_capability": 1, "max_task_tokens": 1000})
        self.assertEqual(r_exact["decision"], ALLOW)                 # 1000 <= 1000 -> continues
        self.assertFalse(any("token cap" in x for x in r_exact["reasons"]))
        self.assertEqual(r_exact["policy"]["max_task_tokens"], 1000)  # cap-in-force echoed on ALLOW (resolved)
        r_under = evaluate_spend(task, cands, {"min_capability": 1, "max_task_tokens": 1001})
        self.assertEqual(r_under["decision"], ALLOW)                 # one-under -> continues
        r_over = evaluate_spend(task, cands, {"min_capability": 1, "max_task_tokens": 999})
        self.assertEqual(r_over["decision"], DENY)                   # one-over -> token DENY
        self.assertIsNone(r_over["recommended_model"])
        self.assertIsNone(r_over["projected_cost_usd"])
        self.assertTrue(any("per-task token cap 999" in x for x in r_over["reasons"]))
        self.assertEqual(r_over["policy"]["max_task_tokens"], 999)

    def test_max_task_tokens_fractional_cap_echo_matches_applied(self):
        # A legal FRACTIONAL cap is enforced via _float(cap) at the gate; the normal-path
        # echo must record the SAME value, not a truncated int. sum=1000 <= 1000.5 -> ALLOW
        # (decision unchanged); echoed threshold == the cap the gate actually compared against.
        from mrtoken.spendpolicy import evaluate_spend, _float, ALLOW
        cap = 1000.5
        task = {"est_input_tokens": 1000, "est_output_tokens": 0, "min_capability": 1}
        cands = [{"model": "m", "capability": 1, "price": {"input": 0.001, "output": 0.0}}]
        r = evaluate_spend(task, cands, {"min_capability": 1, "max_task_tokens": cap})
        self.assertEqual(r["decision"], ALLOW)                       # decision is what it was before
        self.assertEqual(r["policy"]["max_task_tokens"], _float(cap))  # echoed == applied threshold
        self.assertEqual(r["policy"]["max_task_tokens"], 1000.5)     # exact, not truncated...
        self.assertNotEqual(r["policy"]["max_task_tokens"], 1000)    # ...which the old _int produced

    def test_max_task_tokens_sums_all_estimated_fields(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        # every estimated token field contributes to the summed demand (250*4 = 1000 > 999)
        task = {"est_input_tokens": 250, "est_output_tokens": 250,
                "est_cache_read_tokens": 250, "est_cache_write_tokens": 250, "min_capability": 1}
        cands = [{"model": "m", "capability": 1, "price": {"input": 0.001}}]
        r = evaluate_spend(task, cands, {"min_capability": 1, "max_task_tokens": 999})
        self.assertEqual(r["decision"], DENY)
        self.assertTrue(any("estimated 1000 task tokens" in x for x in r["reasons"]))

    def test_max_task_tokens_invalid_fails_closed(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        cands = [{"model": "m", "capability": 1, "price": {"input": 0.001}}]
        base = {"est_input_tokens": 10, "min_capability": 1}
        r_neg = evaluate_spend(base, cands, {"min_capability": 1, "max_task_tokens": -1})
        self.assertEqual(r_neg["decision"], DENY)                    # negative cap
        self.assertTrue(any("invalid input rejected" in x for x in r_neg["reasons"]))
        self.assertTrue(any("policy.max_task_tokens=-1" in x for x in r_neg["reasons"]))
        self.assertFalse(any("per-task token cap" in x for x in r_neg["reasons"]))  # not the token path
        self.assertEqual(r_neg["policy"]["max_task_tokens"], -1)     # invalid-deny path echoes it too (raw)
        r_nan = evaluate_spend(base, cands, {"min_capability": 1, "max_task_tokens": float("nan")})
        self.assertEqual(r_nan["decision"], DENY)                    # non-finite cap
        self.assertTrue(any("invalid input rejected" in x for x in r_nan["reasons"]))
        # negative token estimate with a cap present -> fails closed BEFORE the token gate
        r_negtok = evaluate_spend({"est_input_tokens": -5, "min_capability": 1}, cands,
                                  {"min_capability": 1, "max_task_tokens": 100})
        self.assertEqual(r_negtok["decision"], DENY)
        self.assertTrue(any("task.est_input_tokens=-5" in x for x in r_negtok["reasons"]))

    def test_max_task_tokens_denial_visibly_distinct(self):
        from mrtoken.spendpolicy import evaluate_spend, DENY
        # (a) token-cap denial
        tok = evaluate_spend({"est_input_tokens": 1000, "min_capability": 1},
                             [{"model": "m", "capability": 3, "price": {"input": 0.001}}],
                             {"min_capability": 1, "max_task_tokens": 10})
        tok_r = " ".join(tok["reasons"])
        # (b) capability denial
        capd = evaluate_spend({"est_input_tokens": 10, "min_capability": 1},
                              [{"model": "weak", "capability": 1, "price": {"input": 0.001}}],
                              {"min_capability": 3})
        cap_r = " ".join(capd["reasons"])
        # (c) dollar-budget denial
        dol = evaluate_spend({"est_input_tokens": 1_000_000, "min_capability": 1},
                             [{"model": "m", "capability": 1, "price": {"input": 3.0}}],
                             {"min_capability": 1, "max_task_usd": 1.0})
        dol_r = " ".join(dol["reasons"])
        self.assertEqual((tok["decision"], capd["decision"], dol["decision"]), (DENY, DENY, DENY))
        # each denial's signature phrase is in its OWN reason and ABSENT from the token one
        self.assertIn("per-task token cap", tok_r)
        self.assertNotIn("per-task token cap", cap_r)
        self.assertNotIn("per-task token cap", dol_r)
        self.assertIn("required capability", cap_r)
        self.assertNotIn("required capability", tok_r)
        self.assertIn("per-task budget $", dol_r)
        self.assertNotIn("per-task budget $", tok_r)

    def test_live_monitor_classifies_block_disposability(self):
        # Gate 1's producer: a target read once and untouched for
        # K_DISPOSABLE_TURNS responses is disposable (scanlib-like); a target
        # re-read repeatedly is load-bearing (speclib-like). Hash-keyed metadata
        # only. (No transcript-replay plumbing exists yet for the 5D.3 golden
        # fixtures — this synthetic feed covers the same two regimes.)
        from mrtoken.watch import LiveMonitor, K_DISPOSABLE_TURNS

        mon = LiveMonitor(emit=lambda _: None)

        def response(i, blocks):
            mon.feed({"type": "assistant", "message": {
                "id": f"m{i}", "model": "x",
                "usage": {"input_tokens": 10, "output_tokens": 1},
                "content": blocks}})

        def read_block(tuid, target):
            return {"type": "tool_use", "id": tuid, "name": "Read",
                    "input": {"file_path": target}}

        def result(tuid):
            mon.feed({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tuid, "content": "x" * 400}]}})

        response(0, [read_block("t0", "/scan/notes.txt")])   # read once, early
        result("t0")
        for i in range(1, K_DISPOSABLE_TURNS + 1):           # re-read every turn
            response(i, [read_block(f"s{i}", "/spec/refs.md")])
            result(f"s{i}")

        d = mon.disposability()
        self.assertEqual(sorted(d.values()), ["disposable", "load_bearing"])
        self.assertTrue(all(k.startswith("read:") for k in d))
        self.assertIn("disposability", mon.snapshot())       # threaded to consumers

    def test_compaction_gate_runway_suppresses_near_done(self):
        # COMPACTION-GATE phase 3 (Gate 2): near-done suppresses the nudge
        # entirely — even under pressure, even on disposable context — because
        # with little runway the reset overhead exceeds the carry it saves.
        # No/ambiguous runway data falls back to phase-2 behaviour.
        from mrtoken.intervene import evaluate, _near_done
        disp = {"read:abc123": "disposable"}
        near = {"calls": 20, "window": 8, "errors_first_half": 3,
                "errors_second_half": 0, "recent_writes": 2}   # red→green + landing
        # Near-done: suppress everything, drop and offload nudges alike.
        self.assertIsNone(evaluate(85, None, ["context_rot"],
                                   disposability=disp, progress=near))
        self.assertIsNone(evaluate(85, None, ["huge_tool_output"], progress=near))
        # Mid-session (errors flat) + disposable → the drop stays allowed.
        flat = {"calls": 20, "window": 8, "errors_first_half": 2,
                "errors_second_half": 2, "recent_writes": 2}
        self.assertEqual(evaluate(85, None, ["context_rot"], disposability=disp,
                                  progress=flat)["tool"], "handoff")
        # No runway data → exact phase-2 behaviour.
        self.assertEqual(evaluate(85, None, ["context_rot"],
                                  disposability=disp)["tool"], "handoff")
        self.assertEqual(evaluate(85, None, ["context_rot"])["tool"], "offload")
        # The proxy demands positive evidence on EVERY axis (under-suppression
        # bias): early session, thin window, still-red late half, or no durable
        # writes each block the near-done call.
        for not_near in (
            {**near, "calls": 4},                    # too early
            {**near, "window": 4},                   # thin window
            {**near, "errors_second_half": 2},       # late half still red
            {**near, "recent_writes": 0},            # nothing durable landing
            None, {},
        ):
            self.assertFalse(_near_done(not_near))

    def test_live_monitor_progress_feeds_runway_proxy(self):
        # Gate 2's producer: errors early → green + edits landing late reads as
        # near-done; metadata only (is_error flags + tool names).
        from mrtoken.watch import LiveMonitor, RECENT_ERROR_WINDOW
        from mrtoken.intervene import _near_done

        mon = LiveMonitor(emit=lambda _: None)

        def turn(i, tool_name, is_error):
            mon.feed({"type": "assistant", "message": {
                "id": f"m{i}", "model": "x",
                "usage": {"input_tokens": 10, "output_tokens": 1},
                "content": [{"type": "tool_use", "id": f"t{i}", "name": tool_name,
                             "input": {"i": i}}]}})
            mon.feed({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": "x", "is_error": is_error}]}})

        for i in range(RECENT_ERROR_WINDOW // 2):        # first half: failing runs
            turn(i, "Bash", True)
        for i in range(RECENT_ERROR_WINDOW // 2, RECENT_ERROR_WINDOW):
            turn(i, "Edit", False)                        # second half: green + edits
        p = mon.progress()
        self.assertEqual(p["window"], RECENT_ERROR_WINDOW)
        self.assertGreater(p["errors_first_half"], p["errors_second_half"])
        self.assertGreaterEqual(p["recent_writes"], 1)
        self.assertTrue(_near_done(p))
        self.assertIn("progress", mon.snapshot())         # threaded to consumers

    def test_module_registry(self):
        # ROADMAP 7.2 (groundwork): register/toggle external token-saver modules +
        # emit an agent-registration snippet. No external code is run/trusted.
        import mrtoken.policy as policy
        from mrtoken import modules
        with tempfile.TemporaryDirectory() as tmp:
            orig = policy._config_path
            policy._config_path = lambda: os.path.join(tmp, "config.json")
            try:
                self.assertEqual(modules.list_modules(), [])
                modules.add_module("headroom", kind="mcp", command="headroom",
                                   args=["mcp"], note="compress tool outputs")
                m = modules.get_module("headroom")
                self.assertEqual((m["kind"], m["command"], m["enabled"]), ("mcp", "headroom", True))
                self.assertEqual(modules.mcp_registration("headroom"),
                                 {"command": "headroom", "args": ["mcp"]})
                modules.set_enabled("headroom", False)
                self.assertFalse(modules.get_module("headroom")["enabled"])
                with self.assertRaises(ValueError):
                    modules.add_module("bad", kind="mcp")          # mcp needs a command
                with self.assertRaises(ValueError):
                    modules.add_module("x", kind="bogus")
                # coexists with the intervention policy in the same config file
                policy.set_autonomy("offload", "ask")
                self.assertEqual(policy.autonomy("offload"), "ask")
                self.assertEqual(len(modules.list_modules()), 1)   # module survived policy write
                modules.remove_module("headroom")
                self.assertEqual(modules.list_modules(), [])
            finally:
                policy._config_path = orig

    def test_savings_realized_and_addressable(self):
        # ROADMAP 7.1: realized savings (logged tool actions) + addressable (rules found).
        import mrtoken.savings as savings
        import mrtoken.datadir as dd
        with tempfile.TemporaryDirectory() as tmp:
            orig = dd.central_default          # savings resolves central_default through the module
            dd.central_default = lambda: tmp
            try:
                self.assertEqual(savings.realized()["total"], 0)         # nothing yet
                savings.record("offload", 12000)
                savings.record("offload", 8000)
                savings.record("handoff", 0)                            # non-positive → ignored
                r = savings.realized()
                self.assertEqual(r["total"], 20000)
                self.assertEqual(r["by_tool"]["offload"]["uses"], 2)
                self.assertNotIn("handoff", r["by_tool"])
                # addressable from a DB's recommendations
                conn = connect(os.path.join(tmp, "t.db"))
                conn.execute("INSERT INTO trace(session_id,ingested_at) VALUES('s','t')")
                tid = conn.execute("SELECT id FROM trace").fetchone()[0]
                conn.execute("INSERT INTO recommendation(trace_id,rule,severity,message,"
                             "est_savings_tokens,created_at) VALUES(?,?,?,?,?,?)",
                             (tid, "huge_tool_output", "warn", "x", 50000, "t"))
                conn.commit()
                self.assertEqual(savings.addressable(conn), 50000)
            finally:
                dd.central_default = orig

    def test_addressable_labels_are_estimated_upper_bounds(self):
        import contextlib, io
        import mrtoken.datadir as dd
        import mrtoken.savings as savings
        from mrtoken import cli
        from mrtoken.corpus import print_corpus_report
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            conn.execute("INSERT INTO trace(session_id,ingested_at) VALUES('s','t')")
            tid = conn.execute("SELECT id FROM trace").fetchone()[0]
            for rule in ("one", "two"):
                conn.execute("INSERT INTO recommendation(trace_id,rule,severity,message,"
                             "est_savings_tokens,created_at) VALUES(?,?,?,?,?,?)",
                             (tid, rule, "warn", "x", 500, "t"))
            conn.commit()
            self.assertEqual(savings.addressable(conn), 1000)  # flat sum stays unchanged

            original_default = dd.central_default
            dd.central_default = lambda: tmp
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    savings.print_savings(conn)
            finally:
                dd.central_default = original_default
            label = "upper bound; recommendation estimates may overlap"
            self.assertIn("estimated", output.getvalue())
            self.assertIn(label, output.getvalue())

            corpus_output = io.StringIO()
            with contextlib.redirect_stdout(corpus_output):
                print_corpus_report({
                    "errors": [], "files": 1, "tool_versions": [], "sessions": 1,
                    "low_activity": 0, "total_tokens": 1, "est_cost_usd": 0,
                    "cache_hit_ratio": None, "rule_fires": {"one": {"warn": 2}},
                    "est_savings_tokens": 1000,
                })
            self.assertIn("estimated", corpus_output.getvalue())
            self.assertIn(label, corpus_output.getvalue())

            cli_output = io.StringIO()
            with self.assertRaises(SystemExit) as exit_info:
                with contextlib.redirect_stdout(cli_output):
                    cli.main(["--help"])
            self.assertEqual(exit_info.exception.code, 0)
            cli_help = " ".join(cli_output.getvalue().split())
            self.assertIn("estimated addressable upper bound; recommendation estimates may overlap", cli_help)

    def test_module_measure_records_savings_and_outcome(self):
        # ROADMAP 7.3: external modules get a lab-only measurement shim that
        # records realized savings/outcomes under the module name, without
        # registering or running a real agent.
        import mrtoken.savings as savings
        import mrtoken.outcomes as outcomes
        import mrtoken.datadir as dd
        from mrtoken import module_measure
        with tempfile.TemporaryDirectory() as tmp:
            s_orig, o_orig = dd.central_default, outcomes.central_default
            dd.central_default = lambda: tmp   # savings resolves through the module
            outcomes.central_default = lambda: tmp
            try:
                before = os.path.join(tmp, "before.txt")
                after = os.path.join(tmp, "after.txt")
                with open(before, "w", encoding="utf-8") as handle:
                    handle.write("noisy tool output\n" * 200)
                with open(after, "w", encoding="utf-8") as handle:
                    handle.write("compact summary\n" * 10)

                report = module_measure.measure_files(
                    "headroom", before, after, quality="pass",
                    record=True, session_id="sess-module",
                )

                self.assertEqual(report["kind"], "file_pair")
                self.assertGreater(report["tokens_saved"], 0)
                realized = savings.realized()["by_tool"]["headroom"]
                self.assertEqual(realized["tokens"], report["tokens_saved"])
                self.assertEqual(realized["uses"], 1)
                health = outcomes.health("headroom")
                self.assertEqual((health["n"], health["helped"], health["hurt"]), (1, 1, 0))

                log_path = os.path.join(tmp, "headroom.jsonl")
                with open(log_path, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"tokens_before": 1000, "tokens_after": 650}) + "\n")
                    handle.write(json.dumps({"tokens_before": 100, "tokens_after": 140}) + "\n")
                    handle.write(json.dumps({
                        "input_tokens_original": 500,
                        "input_tokens_optimized": 350,
                    }) + "\n")
                    handle.write("not-json\n")
                parsed = module_measure.measure_headroom_log("headroom", log_path)
                self.assertEqual(parsed["rows_seen"], 4)
                self.assertEqual(parsed["rows_measured"], 3)
                self.assertEqual(parsed["bad_lines"], 1)
                self.assertEqual(parsed["tokens_delta"], 460)
                self.assertEqual(parsed["tokens_saved"], 460)
            finally:
                dd.central_default = s_orig
                outcomes.central_default = o_orig

    def test_module_measure_synthetic_upstream_fixture(self):
        # The 7.3 Headroom traffic probe uses only localhost synthetic traffic:
        # client -> Headroom proxy -> this fake Anthropic upstream.
        from mrtoken import module_measure
        server, thread, port = module_measure._start_fake_anthropic_upstream()
        try:
            payload = module_measure._synthetic_anthropic_payload(chars=4096)
            raw = json.dumps(payload)
            self.assertIn("tool_result", raw)
            self.assertGreater(module_measure.estimate_tokens(raw), 900)

            result = module_measure._post_json(
                f"http://127.0.0.1:{port}/v1/messages",
                payload,
                timeout_s=2,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], 200)
            self.assertEqual(len(server.requests), 1)
            self.assertEqual(server.requests[0]["path"], "/v1/messages")
            self.assertIn("toolu_mrtoken_synthetic", server.requests[0]["body"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_codex_live_pressure_and_decide(self):
        # ROADMAP B: live ctx % from a Codex rollout + the shared decide() core fires
        # for Codex too (proc engine no longer Claude-only).
        from mrtoken.ingest_codex import codex_ctx_pct
        from mrtoken import intervene
        import mrtoken.datadir as dd, mrtoken.policy as policy
        with tempfile.TemporaryDirectory() as tmp:
            roll = os.path.join(tmp, "r.jsonl")
            write_jsonl(roll, [
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "model_context_window": 100000,
                    "last_token_usage": {"input_tokens": 85000, "cached_input_tokens": 80000,
                                         "output_tokens": 100, "total_tokens": 85100}}}},
            ])
            self.assertEqual(codex_ctx_pct(roll), 85)   # 85000/100000

            o_cd, p_cp = dd.central_default, policy._config_path
            dd.central_default = lambda: tmp
            policy._config_path = lambda: os.path.join(tmp, "config.json")
            saved = os.environ.pop("MRTOKEN_INTERVENE", None)
            try:
                iv = intervene.decide("cxs1", 85, None, ["huge_tool_output"])
                self.assertIsNotNone(iv)
                self.assertEqual(iv["tool"], "offload")
                self.assertIsNone(intervene.decide("cxs2", 20, None, ["huge_tool_output"]))  # no pressure
            finally:
                dd.central_default, policy._config_path = o_cd, p_cp
                if saved is not None:
                    os.environ["MRTOKEN_INTERVENE"] = saved

    def test_proc_engine_debounces(self):
        # ROADMAP 6.4: fire once per rising pressure band, not every turn.
        import mrtoken.datadir as dd
        from mrtoken.intervene import should_fire
        with tempfile.TemporaryDirectory() as tmp:
            orig = dd.central_default
            dd.central_default = lambda: tmp
            try:
                self.assertTrue(should_fire("s1", 72))    # first fire
                self.assertFalse(should_fire("s1", 75))   # within band → suppressed
                self.assertTrue(should_fire("s1", 85))    # climbed another band → fires
            finally:
                dd.central_default = orig

    def test_toolbox_handoff_compact_and_toggle(self):
        # ROADMAP 6.2: handoff (real) + compact (advisory) tools, each toggleable.
        from mrtoken import toolbox
        self.assertEqual(set(toolbox.TOOL_REGISTRY),
                         {"offload", "handoff", "compact", "confirm_disposable"})

        orig_h = toolbox.build_handoff
        toolbox.build_handoff = lambda db, s: "# Handoff (stub)"
        try:
            # No `session` key -> the tool now resolves the CALLER-PROJECT default itself,
            # BEFORE dispatch (passing None would drop into the trusted global resolver and
            # could bind another project). This fixture has no transcript for this project,
            # so the correct behaviour is an explicit refusal, not a dispatch.
            txt, err = toolbox.call_tool("handoff", {})
            self.assertFalse(err)
            self.assertIn("no transcript found for THIS project", txt)
            self.assertNotIn("Handoff", txt)
            # ...and the rejection itself is asserted here rather than lost:
            bad, berr = toolbox.call_tool("handoff", {"session": "no-such-session-id"})
            self.assertFalse(berr)
            self.assertIn("no transcript in THIS project", bad)
            self.assertNotIn("Handoff", bad)
        finally:
            toolbox.build_handoff = orig_h

        ctxt, cerr = toolbox.call_tool("compact", {})
        self.assertFalse(cerr)
        self.assertIn("compact", ctxt.lower())

        # toggle: disable offload → hidden from tools/list + rejected on call
        os.environ["MRTOKEN_TOOLS_OFF"] = "offload"
        try:
            names = [t["name"] for t in toolbox.enabled_tool_schemas()]
            self.assertNotIn("offload", names)
            self.assertIn("handoff", names)
            _, derr = toolbox.call_tool("offload", {"content": "x"})
            self.assertTrue(derr)
        finally:
            os.environ.pop("MRTOKEN_TOOLS_OFF", None)

        _, uerr = toolbox.call_tool("bogus", {})
        self.assertTrue(uerr)

    def test_golden_session_signals(self):
        # ROADMAP 5D.3 — golden regression: whole-session fixtures with their
        # EXPECTED fired-signal sets. Catches drift when a threshold changes.
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.rules import analyse

        def a(sid, mid, ts, text="ok", usage=None, tool=None):
            content = [{"type": "text", "text": text}]
            if tool:
                content = [{"type": "tool_use", "id": tool, "name": "Read", "input": {"file_path": "/x"}}]
            return {"type": "assistant", "sessionId": sid, "uuid": sid + mid, "timestamp": ts,
                    "message": {"id": mid, "model": "claude-opus-4-8",
                                "usage": usage or {"input_tokens": 10, "output_tokens": 5},
                                "content": content}}

        def tool_result(tuid, chars):
            return {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tuid, "content": "x" * chars}]}}

        def build_huge():  # huge tool output carried across later calls
            return [a("g1", "m1", "2026-06-01T00:00:00Z", tool="t1"),
                    tool_result("t1", 200_000),
                    a("g1", "m2", "2026-06-01T00:00:01Z"),
                    a("g1", "m3", "2026-06-01T00:00:02Z"),
                    a("g1", "m4", "2026-06-01T00:00:03Z")]

        def build_clean():  # short, well-cached → nothing should fire
            u = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 5000}
            return [a("g2", "m1", "2026-06-02T00:00:00Z", usage=u),
                    a("g2", "m2", "2026-06-02T00:00:01Z", usage=u)]

        golden = [
            {"name": "huge_output_carried", "build": build_huge, "expect_contains": {"huge_tool_output"}},
            {"name": "clean_short", "build": build_clean, "expect_exact": set()},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for g in golden:
                conn = connect(os.path.join(tmp, g["name"] + ".db"))
                path = os.path.join(tmp, g["name"] + ".jsonl")
                write_jsonl(path, g["build"]())
                r = ingest_file(conn, path, load_prices())
                tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                                   (r["session_id"],)).fetchone()[0]
                fired = {rec["rule"] for rec in analyse(conn, tid)}
                if "expect_exact" in g:
                    self.assertEqual(fired, g["expect_exact"], f"golden '{g['name']}' drift: {fired}")
                else:
                    self.assertTrue(g["expect_contains"] <= fired,
                                    f"golden '{g['name']}' missing {g['expect_contains'] - fired}")

    def test_validate_harness_corroborates(self):
        from mrtoken.validate import validate_db
        conn, tid = make_trace()
        # a genuine multi-call retry loop
        for i in range(3):
            cur = conn.execute(
                "INSERT INTO model_call(trace_id, timestamp) VALUES(?,?)",
                (tid, f"2026-06-01T00:00:0{i}Z"))
            conn.execute("INSERT INTO tool_call(trace_id, model_call_id, tool_name, is_error) "
                         "VALUES(?,?,?,1)", (tid, cur.lastrowid, "Bash"))
        from mrtoken.rules import analyse
        analyse(conn, tid)
        report = validate_db(conn)
        rl = report["rules"].get("retry_loop")
        self.assertIsNotNone(rl)
        self.assertEqual(rl["strong"], rl["fired"])  # genuine loop → strong


    def test_live_monitor_fires_signals(self):
        from mrtoken.watch import LiveMonitor
        out = []
        mon = LiveMonitor(emit=out.append)
        # an assistant turn with a huge context window
        mon.feed({"type": "assistant", "message": {
            "model": "claude-sonnet-4",
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 180_000,
                      "output_tokens": 50},
            "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}})
        # the tool returns a huge result
        mon.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 60_000}]}})
        joined = "\n".join(out)
        self.assertIn("context window", joined)
        self.assertIn("Read returned", joined)

    def test_live_monitor_snapshot_tracks_signals(self):
        from mrtoken.watch import LiveMonitor
        mon = LiveMonitor(emit=lambda _: None)
        # assistant turn with large context + huge tool output
        mon.feed({"type": "assistant", "message": {
            "model": "claude-sonnet-4",
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 180_000,
                      "output_tokens": 50},
            "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}})
        mon.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 60_000}]}})
        snap = mon.snapshot()
        self.assertGreater(snap["context_now"], 0)
        self.assertGreater(snap["cum_cost"], 0.0)
        self.assertIn("context", snap["signals_fired"])
        self.assertIn("huge_tool_output", snap["signals_fired"])


    def test_init_installs_hook_preserves_and_is_idempotent(self):
        from mrtoken.install import (init, _load_settings, _already_installed,
                                     _prompt_hook_already_installed)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            settings_dir = os.path.join(tmp, ".claude")
            os.makedirs(settings_dir)
            settings_path = os.path.join(settings_dir, "settings.local.json")
            global_settings_path = os.path.join(tmp, "global-settings.json")
            with open(settings_path, "w") as h:
                json.dump({"permissions": {"allow": ["Bash(ls *)"]},
                           "hooks": {"Stop": [{"matcher": "", "hooks": [
                               {"type": "command", "command": "echo existing"}]}]}}, h)

            init(project_root=tmp, global_settings_path=global_settings_path,
                 codex_skills_root=os.path.join(tmp, "nocodex", "skills"), emit=lambda *_: None)
            # the user's OWN project-local Stop hook + other settings preserved;
            # ours is NOT added project-local (it goes global now so it fires for
            # sessions started from any folder, e.g. the desktop app)
            s = _load_settings(settings_path)
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])
            local_cmds = [hh["command"] for e in s["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertIn("echo existing", local_cmds)
            self.assertFalse(any("on_stop.py" in c for c in local_cmds))
            self.assertTrue(os.path.exists(os.path.join(tmp, ".token-tithe", "token-tithe.db")))
            # the /mr-handoff skill is installed GLOBALLY (next to global settings),
            # so /mr-* works in every project, not just where init ran
            global_skills = os.path.join(os.path.dirname(global_settings_path), "skills")
            self.assertTrue(os.path.exists(
                os.path.join(global_skills, "mr-handoff", "SKILL.md")))
            self.assertFalse(os.path.exists(
                os.path.join(tmp, ".claude", "skills", "mr-handoff")))  # no longer project-local
            # Stop hook + per-turn HUD hook + statusLine all in GLOBAL settings
            gs = _load_settings(global_settings_path)
            self.assertTrue(_already_installed(gs))           # Stop hook is global
            self.assertTrue(_prompt_hook_already_installed(gs))
            self.assertEqual(gs["statusLine"]["type"], "command")  # object form, not bare string
            self.assertIn("statusline", gs["statusLine"]["command"])
            g_stop = [hh["command"] for e in gs["hooks"]["Stop"] for hh in e["hooks"]]

            # idempotent: second run adds nothing extra
            init(project_root=tmp, global_settings_path=global_settings_path,
                 codex_skills_root=os.path.join(tmp, "nocodex", "skills"), emit=lambda *_: None)
            gs2 = _load_settings(global_settings_path)
            g_stop2 = [hh["command"] for e in gs2["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertEqual(len(g_stop2), len(g_stop))  # Stop not duplicated
            self.assertTrue(_already_installed(gs2))
            ups2 = gs2.get("hooks", {}).get("UserPromptSubmit", [])
            self.assertEqual(len(ups2), 1)  # idempotent — not added twice

    def test_init_migrates_legacy_project_local_stop_hook_to_global(self):
        # an install from a prior version put the Stop hook project-local; re-running
        # init must move it to global and strip the local one so it can't double-fire
        from mrtoken.install import (init, hook_command, _load_settings,
                                     _already_installed)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            local = os.path.join(tmp, ".claude", "settings.local.json")
            os.makedirs(os.path.dirname(local))
            with open(local, "w") as h:  # legacy MR Token Stop hook + a user hook
                json.dump({"hooks": {"Stop": [
                    {"matcher": "", "hooks": [{"type": "command", "command": hook_command()}]},
                    {"matcher": "", "hooks": [{"type": "command", "command": "echo mine"}]},
                ]}}, h)
            gpath = os.path.join(tmp, "global-settings.json")
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=os.path.join(tmp, "nocodex", "skills"), emit=lambda *_: None)

            self.assertTrue(_already_installed(_load_settings(gpath)))   # moved to global
            s = _load_settings(local)
            cmds = [hh["command"] for e in s.get("hooks", {}).get("Stop", []) for hh in e["hooks"]]
            self.assertNotIn(hook_command(), cmds)                       # legacy ours stripped
            self.assertIn("echo mine", cmds)                             # user's hook preserved

    def test_statusline_command_source_fallback_is_runnable(self):
        # when there's no console script (installed from source, no pip), the
        # statusLine command must run the real entry, not `-m mrtoken` (help only)
        import mrtoken.install as inst
        real = inst.shutil.which
        inst.shutil.which = lambda *_a, **_k: None
        try:
            cmd = inst.statusline_command()
        finally:
            inst.shutil.which = real
        self.assertIn("-m mrtoken.cli statusline", cmd)
        self.assertNotIn("-m mrtoken statusline", cmd)  # the help-only entry
        self.assertIn("PYTHONPATH=", cmd)               # importable from any cwd

    def test_uninstall_removes_statusline_across_path_transitions(self):
        import mrtoken.install as inst
        modes = {"source": None, "console": "/tmp/mrtoken-transcript"}
        for installed, uninstalled in (("source", "console"), ("console", "source"),
                                       ("source", "source"), ("console", "console")):
            with self.subTest(installed=installed, uninstalled=uninstalled), tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, "package.json"), "w") as h:
                    h.write("{}")
                gpath = os.path.join(tmp, "global-settings.json")
                real_which = inst.shutil.which
                try:
                    inst.shutil.which = lambda _name: modes[installed]
                    command = inst.statusline_command()
                    if installed == "source":
                        self.assertIn('"', command)  # source fallback must exercise JSON escaping
                    inst.shutil.which = lambda _name: modes[uninstalled]
                    if installed != uninstalled:
                        self.assertNotEqual(command, inst.statusline_command())
                    with open(gpath, "w") as h:
                        json.dump({"statusLine": {"type": "command", "command": command,
                                                   "padding": 0}}, h)
                    inst.uninstall(
                        project_root=tmp,
                        settings_path=os.path.join(tmp, ".claude", "settings.local.json"),
                        global_settings_path=gpath,
                        codex_hooks_path=os.path.join(tmp, ".codex", "hooks.json"),
                        remove_skills=False,
                        emit=lambda *_: None,
                    )
                finally:
                    inst.shutil.which = real_which
                self.assertNotIn("statusLine", inst._load_settings(gpath))

    def test_uninstall_statusline_marker_preserves_unrecognized_values(self):
        import mrtoken.install as inst
        source = 'PYTHONPATH="/tmp/backend" /tmp/python -m mrtoken.cli statusline'
        console = "/tmp/mrtoken-transcript statusline"
        cases = (
            ("dict-source", {"type": "command", "command": source}, True),
            ("string-source", source, True),
            ("dict-console", {"type": "command", "command": console}, True),
            ("string-console", console, True),
            ("dict-without-command", {"type": "command"}, False),
            ("dict-with-int-command", {"command": 1}, False),
            ("int", 1, False),
            ("list", [], False),
            ("none", None, False),
            ("empty", "", False),
            ("missing", None, False),
            ("superstring", source + " --user-argument", False),
        )
        for label, stored, removed in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, "package.json"), "w") as h:
                    h.write("{}")
                gpath = os.path.join(tmp, "global-settings.json")
                settings = {} if label == "missing" else {"statusLine": stored}
                with open(gpath, "w") as h:
                    json.dump(settings, h)
                inst.uninstall(
                    project_root=tmp,
                    settings_path=os.path.join(tmp, ".claude", "settings.local.json"),
                    global_settings_path=gpath,
                    codex_hooks_path=os.path.join(tmp, ".codex", "hooks.json"),
                    remove_skills=False,
                    emit=lambda *_: None,
                )
                present = "statusLine" in inst._load_settings(gpath)
                expected_present = False if label == "missing" else not removed
                self.assertEqual(expected_present, present)

    def test_uninstall_reverses_init_preserving_other_settings(self):
        from mrtoken.install import (
            init, uninstall, _load_settings, _already_installed,
            _codex_mcp_configured,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            settings_path = os.path.join(tmp, ".claude", "settings.local.json")
            os.makedirs(os.path.dirname(settings_path))
            with open(settings_path, "w") as h:  # a Stop hook the user already had
                json.dump({"permissions": {"allow": ["Bash(ls *)"]},
                           "hooks": {"Stop": [{"matcher": "", "hooks": [
                               {"type": "command", "command": "echo keepme"}]}]}}, h)
            gpath = os.path.join(tmp, "global-settings.json")
            os.makedirs(os.path.join(tmp, ".codex"))
            codex_hooks = os.path.join(tmp, ".codex", "hooks.json")
            codex_config = os.path.join(tmp, ".codex", "config.toml")
            with open(codex_hooks, "w") as h:
                json.dump({"hooks": {"Stop": [{"hooks": [
                    {"type": "command", "command": "echo keep-codex"}]}]}}, h)
            with open(codex_config, "w") as h:
                h.write("[mcp_servers.keep]\ncommand = \"keep\"\nargs = []\n")
            codex_skills = os.path.join(tmp, ".codex", "skills")
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=codex_skills, codex_hooks_path=codex_hooks,
                 emit=lambda *_: None)
            skills = os.path.join(os.path.dirname(gpath), "skills")
            self.assertTrue(_already_installed(_load_settings(gpath)))     # Stop hook is global now
            self.assertTrue(os.path.exists(os.path.join(skills, "mr-handoff", "SKILL.md")))
            self.assertTrue(_already_installed(_load_settings(codex_hooks)))  # Codex hook installed
            self.assertTrue(_codex_mcp_configured(codex_config))

            uninstall(project_root=tmp, settings_path=settings_path,
                      global_settings_path=gpath, codex_hooks_path=codex_hooks,
                      emit=lambda *_: None)
            s, g = _load_settings(settings_path), _load_settings(gpath)
            self.assertFalse(_already_installed(g))                       # our global Stop hook gone
            cmds = [hh["command"] for e in s.get("hooks", {}).get("Stop", []) for hh in e["hooks"]]
            self.assertIn("echo keepme", cmds)                            # user's hook preserved
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])   # other settings preserved
            self.assertNotIn("statusLine", g)                            # global HUD gone
            self.assertFalse(g.get("hooks", {}).get("UserPromptSubmit"))  # global hook gone
            self.assertFalse(os.path.exists(os.path.join(skills, "mr-handoff")))  # skill removed
            ch = _load_settings(codex_hooks)
            codex_cmds = [hh["command"] for e in ch.get("hooks", {}).get("Stop", []) for hh in e["hooks"]]
            self.assertIn("echo keep-codex", codex_cmds)                  # user's Codex hook preserved
            self.assertFalse(any("on_stop.py" in c for c in codex_cmds))  # our Codex hook removed
            self.assertFalse(os.path.exists(os.path.join(codex_skills, "mr-context")))
            self.assertFalse(_codex_mcp_configured(codex_config))
            with open(codex_config, encoding="utf-8") as h:
                self.assertIn("[mcp_servers.keep]", h.read())             # user's MCP config preserved

    def test_init_warns_before_replacing_existing_statusline(self):
        from mrtoken.install import init, _load_settings
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            gpath = os.path.join(tmp, "global-settings.json")
            with open(gpath, "w") as h:  # user already has their own statusLine
                json.dump({"statusLine": {"type": "command", "command": "my-bar"}}, h)
            out = []
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=os.path.join(tmp, "nocodex", "skills"), emit=out.append)
            joined = "\n".join(out)
            self.assertIn("replacing your existing statusLine", joined)
            gs = _load_settings(gpath)
            self.assertIn("statusline", gs["statusLine"]["command"])  # ours installed
            # and a backup of the old settings exists to restore from
            self.assertTrue(any(f.startswith("global-settings.json.mrtoken-bak")
                                for f in os.listdir(tmp)))

    def test_doctor_reports_healthy_temp_install(self):
        from mrtoken.install import init
        import mrtoken.doctor as doctor
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            gpath = os.path.join(tmp, "global-settings.json")
            codex_home = os.path.join(tmp, ".codex")
            os.makedirs(codex_home)
            codex_hooks = os.path.join(codex_home, "hooks.json")
            codex_skills = os.path.join(codex_home, "skills")
            init(project_root=tmp, global_settings_path=gpath,
                 codex_hooks_path=codex_hooks, codex_skills_root=codex_skills,
                 emit=lambda *_: None)

            real_which = doctor.shutil.which
            doctor.shutil.which = lambda name: "/tmp/mrtoken-transcript" if name == "mrtoken-transcript" else None
            try:
                report = doctor.check_install(
                    project_root=tmp,
                    db_path=os.path.join(tmp, ".token-tithe", "token-tithe.db"),
                    global_settings_path=gpath,
                    claude_skills_root=os.path.join(tmp, "skills"),
                    codex_hooks_path=codex_hooks,
                    codex_skills_root=codex_skills,
                )
            finally:
                doctor.shutil.which = real_which

            self.assertTrue(report["ok"])
            statuses = {c["name"]: c["status"] for c in report["checks"]}
            self.assertEqual(statuses["command"], "ok")
            self.assertEqual(statuses["project db"], "ok")
            self.assertEqual(statuses["claude stop hook"], "ok")
            self.assertEqual(statuses["claude statusline"], "ok")
            self.assertEqual(statuses["claude prompt hook"], "ok")
            self.assertEqual(statuses["claude compact hook"], "ok")
            self.assertEqual(statuses["claude skills"], "ok")
            self.assertEqual(statuses["codex stop hook"], "ok")
            self.assertEqual(statuses["codex skills"], "ok")
            self.assertEqual(statuses["codex mcp"], "ok")

    def test_doctor_reports_missing_install_without_writes(self):
        import mrtoken.doctor as doctor
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, ".token-tithe", "token-tithe.db")
            settings = os.path.join(tmp, "missing-settings.json")
            real_which = doctor.shutil.which
            doctor.shutil.which = lambda name: None
            try:
                report = doctor.check_install(
                    project_root=tmp,
                    db_path=db,
                    global_settings_path=settings,
                    claude_skills_root=os.path.join(tmp, "skills"),
                    codex_hooks_path=os.path.join(tmp, "no-codex", "hooks.json"),
                )
            finally:
                doctor.shutil.which = real_which

            self.assertFalse(report["ok"])
            statuses = {c["name"]: c["status"] for c in report["checks"]}
            self.assertEqual(statuses["command"], "fail")
            self.assertEqual(statuses["project db"], "warn")
            self.assertEqual(statuses["claude settings"], "fail")
            self.assertEqual(statuses["claude skills"], "fail")
            self.assertEqual(statuses["codex"], "skip")
            self.assertFalse(os.path.exists(db))  # doctor is read-only

    def test_doctor_repair_and_bundle_are_explicit(self):
        import mrtoken.doctor as doctor
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            gpath = os.path.join(tmp, "global-settings.json")
            codex_home = os.path.join(tmp, ".codex")
            os.makedirs(codex_home)
            codex_hooks = os.path.join(codex_home, "hooks.json")
            codex_skills = os.path.join(codex_home, "skills")

            rc = doctor.repair_install(project_root=tmp, global_settings_path=gpath,
                                       codex_hooks_path=codex_hooks,
                                       codex_skills_root=codex_skills,
                                       emit=lambda *_: None)
            self.assertEqual(rc, 0)
            report = doctor.check_install(
                project_root=tmp,
                db_path=os.path.join(tmp, ".token-tithe", "token-tithe.db"),
                global_settings_path=gpath,
                claude_skills_root=os.path.join(tmp, "skills"),
                codex_hooks_path=codex_hooks,
                codex_skills_root=codex_skills,
            )
            self.assertTrue(report["ok"])

            bundle_path = os.path.join(tmp, "bundle.json")
            doctor.write_bundle(report, bundle_path)
            with open(bundle_path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["schema"], "mrtoken.doctor.bundle.v1")
            self.assertIn("report", data)
            self.assertNotIn(tmp, json.dumps(data))  # home/project path redacted when under ~ in real use

    def test_beta_note_uses_real_version_and_repo_url(self):
        from mrtoken.beta import beta_note
        from mrtoken import __version__
        note = beta_note("git@example.com:org/repo.git")
        self.assertIn(f"MR Token v{__version__}", note)
        self.assertIn("git clone git@example.com:org/repo.git mr_token", note)
        self.assertIn("mrtoken-transcript doctor", note)
        self.assertIn("mrtoken-transcript feedback", note)

    def test_update_nudge_compares_versions(self):
        from mrtoken.update_check import update_nudge
        self.assertIsNone(update_nudge("0.4.2", "v0.4.2"))     # current -> quiet
        self.assertIsNone(update_nudge("0.5.0", "v0.4.2"))     # ahead -> quiet
        self.assertIsNone(update_nudge("0.4.1", None))         # no tag known -> quiet
        nudge = update_nudge("0.4.1", "v0.4.2")                # behind -> nudge
        self.assertIsNotNone(nudge)
        self.assertIn("0.4.2", nudge)

    def test_release_tag_gap_flags_untagged_release(self):
        # ROADMAP 4.2: warn when declared version is AHEAD of the latest tag.
        from mrtoken.update_check import release_tag_gap
        w = release_tag_gap("0.4.4", "v0.4.3")                 # code ahead of tag -> warn
        self.assertIsNotNone(w)
        self.assertIn("not tagged", w)
        self.assertIsNone(release_tag_gap("0.4.3", "v0.4.3"))  # equal -> quiet
        self.assertIsNone(release_tag_gap("0.4.3", "v0.4.4"))  # behind -> quiet (nudge's job)
        self.assertIsNone(release_tag_gap("0.4.4", None))      # no tags -> quiet (no false positive)

    def test_model_label_for_hud(self):
        from mrtoken.statusline import _model_label
        # statusLine model object: terse display name -> enrich version from id
        self.assertEqual(_model_label({"id": "claude-opus-4-8", "display_name": "Opus"}), "Opus 4.8")
        # bare id string (transcript fallback), trailing date ignored
        self.assertEqual(_model_label("claude-sonnet-4-6-20250101"), "Sonnet 4.6")
        self.assertEqual(_model_label("claude-haiku-4-5"), "Haiku 4.5")
        # already-versioned display name kept as-is
        self.assertEqual(_model_label({"display_name": "Opus 4.8"}), "Opus 4.8")
        self.assertIsNone(_model_label(None))

    def test_plan_segment_5h(self):
        from mrtoken.statusline import _plan_segment
        self.assertEqual(_plan_segment(5), "5h 5%")        # low -> no flag
        self.assertEqual(_plan_segment(88), "5h 88%⚠")     # near limit -> flag
        self.assertEqual(_plan_segment(0), "5h 0%")        # 0 is shown, not dropped
        self.assertIsNone(_plan_segment(None))             # absent payload -> nothing

    def test_weekly_segment_only_when_close(self):
        from mrtoken.statusline import _weekly_segment
        self.assertIsNone(_weekly_segment(19))             # low -> hidden (no clutter)
        self.assertIsNone(_weekly_segment(79))             # just under -> hidden
        self.assertEqual(_weekly_segment(80), "7d 80%⚠")   # at threshold -> alert
        self.assertEqual(_weekly_segment(93), "7d 93%⚠")
        self.assertIsNone(_weekly_segment(None))

    def test_cli_reports_version(self):
        import io, contextlib
        from mrtoken.cli import main
        from mrtoken import __version__
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())

    def test_init_accepts_dry_run_flag(self):
        # regression: QUICKSTART says `init --dry-run`, but the flag was named
        # --print and argparse rejected --dry-run with "unrecognized arguments"
        import io, contextlib
        from mrtoken.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                # cmd_init does sys.exit(rc); code 0 = parsed + dry-ran clean
                # (an unrecognized flag would exit 2 instead)
                for flag in ("--dry-run", "--print"):
                    with self.assertRaises(SystemExit) as cm:
                        main(["init", flag, "--project-root", tmp])
                    self.assertEqual(cm.exception.code, 0)
            out = buf.getvalue()
        self.assertIn("would create DB", out)            # dry-run ran
        self.assertFalse(os.path.exists(os.path.join(tmp, ".token-tithe")))  # wrote nothing

    def test_huge_tool_output_collapses_to_one_rec(self):
        from mrtoken.rules import rule_huge_tool_output
        conn, tid = make_trace()
        for i in range(5):
            conn.execute("INSERT INTO tool_call(trace_id, tool_name, output_chars, "
                         "output_tokens_est, tool_use_id) VALUES(?,?,?,?,?)",
                         (tid, "Read", 200_000, 50_000, f"t{i}"))
        conn.commit()
        recs = rule_huge_tool_output(conn, tid)
        self.assertEqual(len(recs), 1)                 # one rec, not five
        self.assertIn("5 oversized", recs[0]["message"])

    def test_fresh_handoff_needs_trouble_not_just_size(self):
        from mrtoken.rules import rule_fresh_handoff
        conn, tid = make_trace()
        # 32 calls, input grows ~32x, cache held at 90% (no decay), NO errors:
        # pure SIZE signals -> must NOT fire (the cry-wolf the user saw)
        for i in range(32):
            inp = 1000 * (i + 1)
            conn.execute("INSERT INTO model_call(trace_id, timestamp, input_tokens, "
                         "output_tokens, cache_read_input_tokens) VALUES(?,?,?,?,?)",
                         (tid, f"2026-06-01T00:{i:02d}:00Z", inp, 100, inp * 9))
        conn.commit()
        self.assertEqual(rule_fresh_handoff(conn, tid), [])

    def test_fresh_handoff_filters_short_and_error_only_noise(self):
        from mrtoken.rules import rule_fresh_handoff

        short, stid = make_trace()
        # 18 calls with obvious cache decay + input growth used to fire, but
        # there is not enough runway left for handoff advice to be actionable.
        for i in range(18):
            inp, cr = (1_000, 9_000) if i < 9 else (20_000, 2_000)
            short.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,"
                          "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?)",
                          (stid, f"2026-06-01T00:{i:02d}:00Z", inp, cr, 0.01))
        short.commit()
        self.assertEqual(rule_fresh_handoff(short, stid), [])

        flat, ftid = make_trace()
        # A long session with late tool errors but healthy cache and flat/falling
        # late cost is a noisy "keep debugging" shape, not handoff-worthy churn.
        for i in range(44):
            cur = flat.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,"
                               "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?)",
                               (ftid, f"2026-06-01T01:{i:02d}:00Z", 10_000, 90_000,
                                0.02 if i < 22 else 0.015))
            if i >= 34:
                flat.execute("INSERT INTO tool_call(trace_id,model_call_id,tool_name,is_error) "
                             "VALUES(?,?,?,1)", (ftid, cur.lastrowid, "Bash"))
        flat.commit()
        self.assertEqual(rule_fresh_handoff(flat, ftid), [])

        rising, rtid = make_trace()
        for i in range(44):
            cur = rising.execute("INSERT INTO model_call(trace_id,timestamp,input_tokens,"
                                 "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?)",
                                 (rtid, f"2026-06-01T02:{i:02d}:00Z", 10_000, 90_000,
                                  0.02 if i < 22 else 0.04))
            if i >= 34:
                rising.execute("INSERT INTO tool_call(trace_id,model_call_id,tool_name,is_error) "
                               "VALUES(?,?,?,1)", (rtid, cur.lastrowid, "Bash"))
        rising.commit()
        recs = rule_fresh_handoff(rising, rtid)
        self.assertEqual(len(recs), 1)
        self.assertIn("late cost rose", recs[0]["message"] + recs[0]["evidence_json"])

    def test_ingest_dedupes_usage_per_message_id_and_prices_opus(self):
        from mrtoken.ingest import ingest_file, load_prices
        with tempfile.TemporaryDirectory() as tmp:
            transcript = os.path.join(tmp, "s.jsonl")
            usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 1000}
            # Claude Code writes 2 lines for ONE API response (text, then tool_use),
            # each REPEATING the same usage + same message.id -> must count once
            write_jsonl(transcript, [
                {"type": "user", "message": {"content": "hi"}},
                {"type": "assistant", "sessionId": "s", "uuid": "u1", "cwd": tmp,
                 "message": {"id": "msg_1", "model": "claude-opus-4-8", "usage": usage,
                             "content": [{"type": "text", "text": "ok"}]}},
                {"type": "assistant", "sessionId": "s", "uuid": "u2", "cwd": tmp,
                 "message": {"id": "msg_1", "model": "claude-opus-4-8", "usage": usage,
                             "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                          "input": {"file_path": "/x"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result",
                             "tool_use_id": "t1", "content": "data"}]}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            r = ingest_file(conn, transcript, load_prices())
            self.assertEqual(r["model_calls"], 1)  # one response, not two lines
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (r["session_id"],)).fetchone()[0]
            mc, inp, out, cost = conn.execute(
                "SELECT model_calls, input_tokens, output_tokens, est_cost_usd "
                "FROM session_summary WHERE trace_id=?", (tid,)).fetchone()
            self.assertEqual((mc, inp, out), (1, 100, 50))  # counted once, not doubled
            # Opus 4.8 = 5/25 in + cache_read 0.5 (was 15/75/1.5 -> 3x too high)
            self.assertAlmostEqual(cost, round(100/1e6*5 + 50/1e6*25 + 1000/1e6*0.5, 6), places=6)
            tc = conn.execute("SELECT COUNT(*) FROM tool_call WHERE trace_id=?", (tid,)).fetchone()[0]
            self.assertEqual(tc, 1)  # tool_use on the 2nd line still captured despite dedup

    def test_price_table_covers_new_model_families(self):
        # Regression: prices.json must price the current families directly, not
        # silently fall through to the Sonnet-shaped `default` row.
        from mrtoken.ingest import load_prices, price_for, est_cost
        p = load_prices()
        # Fable/Mythos must NOT resolve to default (3/15) — they are 10/50.
        self.assertEqual((price_for(p, "claude-fable-5")["input"],
                          price_for(p, "claude-fable-5")["output"]), (10.0, 50.0))
        self.assertEqual(price_for(p, "claude-mythos-5")["input"], 10.0)
        self.assertEqual(price_for(p, "claude-sonnet-5")["output"], 15.0)
        self.assertEqual(price_for(p, "claude-opus-4-8")["input"], 5.0)
        # OpenAI GPT-5.6 tiers — substring order matters: tier keys must match
        # before the generic 'gpt-5.6', or every tier would price as Terra.
        self.assertEqual(price_for(p, "gpt-5.6-sol")["output"], 30.0)
        self.assertEqual(price_for(p, "gpt-5.6-terra")["output"], 15.0)
        self.assertEqual(price_for(p, "gpt-5.6-luna")["output"], 6.0)
        self.assertEqual(price_for(p, "gpt-5.6")["input"], 2.5)   # bare -> Terra
        self.assertEqual(price_for(p, "gpt-5.5")["input"], 5.0)
        # End-to-end cost for a Terra call (fresh in + out, no cache).
        cost = est_cost(p, "gpt-5.6-terra", {
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
        self.assertAlmostEqual(cost, 2.5 + 15.0, places=6)
        # Unknown models still fall back to `default` (documented behavior).
        self.assertEqual(price_for(p, "some-unknown-model"), p["models"]["default"])

    def test_date_aware_pricing_intro_window(self):
        from mrtoken.ingest import load_prices, price_for, est_cost
        p = load_prices()
        # Sonnet 5: intro $2/$10 through 2026-08-31 (inclusive), sticker $3/$15 after.
        intro = price_for(p, "claude-sonnet-5", at="2026-07-10T00:00:00Z")
        self.assertEqual((intro["input"], intro["output"]), (2.0, 10.0))
        self.assertEqual(price_for(p, "claude-sonnet-5", at="2026-08-31T23:59:59Z")["input"], 2.0)  # boundary inclusive
        after = price_for(p, "claude-sonnet-5", at="2026-09-01")
        self.assertEqual((after["input"], after["output"]), (3.0, 15.0))
        # at=None → base/sticker: back-compat preserved for every existing caller
        self.assertEqual(price_for(p, "claude-sonnet-5")["input"], 3.0)
        # est_cost honours the window
        u = {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        self.assertAlmostEqual(est_cost(p, "claude-sonnet-5", u, at="2026-07-10T00:00:00Z"), 2.0, places=6)
        self.assertAlmostEqual(est_cost(p, "claude-sonnet-5", u, at="2026-09-01"), 3.0, places=6)
        # a model without effective windows is unaffected by `at`
        self.assertEqual(price_for(p, "claude-opus-4-8", at="2026-07-10")["input"], 5.0)

    def test_matched_price_key_and_staleness(self):
        from datetime import date, timedelta
        from mrtoken.ingest import load_prices, matched_price_key
        from mrtoken.pricing import price_staleness, freshness_warning, STALE_DAYS
        p = load_prices()
        # covered families return their key; unknown/empty return None (the coverage signal)
        self.assertEqual(matched_price_key(p, "claude-fable-5"), "claude-fable-5")
        self.assertEqual(matched_price_key(p, "gpt-5.6-terra"), "gpt-5.6-terra")
        self.assertIsNone(matched_price_key(p, "totally-made-up-model"))
        self.assertIsNone(matched_price_key(p, ""))
        # freshness is date-driven and injectable for determinism
        fresh = {"version": "2026-07-01", "models": {}}
        self.assertEqual(price_staleness(fresh, date(2026, 7, 10)), (9, False))
        self.assertIsNone(freshness_warning(fresh, date(2026, 7, 10)))
        stale_day = date(2026, 7, 1) + timedelta(days=STALE_DAYS + 5)
        age, is_stale = price_staleness(fresh, stale_day)
        self.assertTrue(is_stale)
        self.assertIsNotNone(freshness_warning(fresh, stale_day))
        # unparseable version → no signal (not a crash)
        self.assertIsNone(price_staleness({"version": "nope", "models": {}}))

    def test_uncovered_models_flags_default_priced(self):
        from mrtoken.ingest import ingest_file, load_prices, connect
        from mrtoken.pricing import uncovered_models
        with tempfile.TemporaryDirectory() as tmp:
            transcript = os.path.join(tmp, "s.jsonl")
            write_jsonl(transcript, [
                {"type": "user", "message": {"content": "hi"}},
                {"type": "assistant", "sessionId": "s", "uuid": "u1", "cwd": tmp,
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "ok"}]}},
                {"type": "assistant", "sessionId": "s", "uuid": "u2", "cwd": tmp,
                 "message": {"id": "m2", "model": "totally-made-up-9",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "ok"}]}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            ingest_file(conn, transcript, load_prices())
            models = [m for m, _ in uncovered_models(conn, load_prices())]
            self.assertIn("totally-made-up-9", models)   # priced at default → flagged
            self.assertNotIn("claude-opus-4-8", models)  # has a real row → not flagged

    def test_price_override_via_env_merges_over_base(self):
        from mrtoken.ingest import load_prices, price_for
        self.assertEqual(price_for(load_prices(), "claude-opus-4-8")["input"], 5.0)
        prev = os.environ.get("MRTOKEN_PRICES")
        try:
            os.environ["MRTOKEN_PRICES"] = json.dumps({
                "version": "override-test",
                "models": {"claude-opus-4": {"input": 99.0, "output": 199.0,
                                             "cache_read": 9.9, "cache_write": 12.0}}})
            p = load_prices()
            self.assertEqual(p["version"], "override-test")                   # version overridden
            self.assertEqual(price_for(p, "claude-opus-4-8")["input"], 99.0)  # named row overridden
            self.assertEqual(price_for(p, "claude-fable-5")["input"], 10.0)   # unnamed base rows kept
        finally:
            os.environ.pop("MRTOKEN_PRICES", None)
            if prev is not None:
                os.environ["MRTOKEN_PRICES"] = prev

    def test_malformed_price_override_falls_back_to_base(self):
        import contextlib, io
        from mrtoken.ingest import load_prices, price_for
        prev = os.environ.get("MRTOKEN_PRICES")
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # the warning is intended (loud); keep test output clean
                os.environ["MRTOKEN_PRICES"] = "{ not valid json"
                self.assertEqual(price_for(load_prices(), "claude-opus-4-8")["input"], 5.0)
                # a row missing 3 of 4 fields is skipped, base kept (no KeyError downstream)
                os.environ["MRTOKEN_PRICES"] = json.dumps({"models": {"claude-opus-4": {"input": 1.0}}})
                self.assertEqual(price_for(load_prices(), "claude-opus-4-8")["input"], 5.0)
        finally:
            os.environ.pop("MRTOKEN_PRICES", None)
            if prev is not None:
                os.environ["MRTOKEN_PRICES"] = prev

    def test_low_activity_floor_drops_empty_and_hides_substubs(self):
        # The global Stop hook fires on every trivial desktop session. A
        # zero-model-call transcript must NOT be persisted; a sub-floor one (< 2
        # model calls) is kept but flagged low-activity and excluded from counts.
        from mrtoken.ingest import ingest_file, load_prices, MIN_ACTIVITY
        import io, contextlib
        from mrtoken.fleet import fleet_summary
        self.assertEqual(MIN_ACTIVITY["model_calls"], 2)  # Zach's floor
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            prices = load_prices()

            # 0 model calls — only user lines → not persisted
            empty = os.path.join(tmp, "empty.jsonl")
            write_jsonl(empty, [{"type": "user", "message": {"content": "hi"}}])
            r0 = ingest_file(conn, empty, prices)
            self.assertTrue(r0.get("skipped"))
            self.assertIsNone(conn.execute(
                "SELECT id FROM trace WHERE session_id='empty'").fetchone())

            # 1 model call — persisted but low-activity
            tiny = os.path.join(tmp, "tiny.jsonl")
            write_jsonl(tiny, [
                {"type": "assistant", "sessionId": "tiny", "uuid": "u1",
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 5, "output_tokens": 3},
                             "content": [{"type": "text", "text": "ok"}]}},
            ])
            ingest_file(conn, tiny, prices)
            self.assertEqual(conn.execute(
                "SELECT is_low_activity FROM session_summary WHERE session_id='tiny'"
            ).fetchone()[0], 1)

            # 2 model calls — substantive
            real = os.path.join(tmp, "real.jsonl")
            write_jsonl(real, [
                {"type": "assistant", "sessionId": "real", "uuid": "a1",
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "one"}]}},
                {"type": "assistant", "sessionId": "real", "uuid": "a2",
                 "message": {"id": "m2", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "two"}]}},
            ])
            ingest_file(conn, real, prices)
            self.assertEqual(conn.execute(
                "SELECT is_low_activity FROM session_summary WHERE session_id='real'"
            ).fetchone()[0], 0)

            # fleet headline counts the substantive one, hides the stub
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fleet_summary(conn)
            out = buf.getvalue()
            self.assertIn("low-activity", out)
            sessions = conn.execute(
                "SELECT COUNT(*) FROM session_summary "
                "WHERE source='claude_code' AND is_low_activity=0").fetchone()[0]
            self.assertEqual(sessions, 1)  # only 'real'

    def test_backfill_idempotent_and_matches_single_file(self):
        # `ingest --backfill --projects-root <root>` walks the history, honors the
        # 1.1 low-activity rule, is idempotent on re-run, and a single-file ingest
        # of the same transcript yields the same trace.
        from mrtoken.ingest import main as ingest_main, connect, ingest_file, load_prices
        import io, contextlib
        def assistant(sid, mid, text):
            return {"type": "assistant", "sessionId": sid, "uuid": sid + mid,
                    "message": {"id": mid, "model": "claude-opus-4-8",
                                "usage": {"input_tokens": 10, "output_tokens": 5},
                                "content": [{"type": "text", "text": text}]}}
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "projects")
            # proj1/sess1: 2 calls (substantive)
            os.makedirs(os.path.join(root, "proj1"))
            write_jsonl(os.path.join(root, "proj1", "sess1.jsonl"),
                        [assistant("sess1", "m1", "a"), assistant("sess1", "m2", "b")])
            # proj2/sess2: 1 call (low-activity, still persisted)
            os.makedirs(os.path.join(root, "proj2"))
            write_jsonl(os.path.join(root, "proj2", "sess2.jsonl"), [assistant("sess2", "m1", "a")])
            # proj3/emptyx: 0 calls (skipped, not persisted)
            os.makedirs(os.path.join(root, "proj3"))
            write_jsonl(os.path.join(root, "proj3", "emptyx.jsonl"),
                        [{"type": "user", "message": {"content": "hi"}}])
            # a subagent transcript (depth-3)
            sub = os.path.join(root, "proj4", "parentsess", "subagents")
            os.makedirs(sub)
            write_jsonl(os.path.join(sub, "agent-1.jsonl"), [assistant("agent-1", "m1", "a")])

            db = os.path.join(tmp, "corpus.db")
            empty_codex = os.path.join(tmp, "no-codex")  # absent → codex sweep is a no-op
            def run_backfill():
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ingest_main(["--backfill", "--projects-root", root,
                                 "--codex-root", empty_codex, "--db", db])
                return json.loads(buf.getvalue())

            summary = run_backfill()
            self.assertEqual(summary["seen"], 4)      # 3 main + 1 subagent file seen
            self.assertEqual(summary["skipped"], 1)   # the empty stub
            self.assertEqual(summary["sessions"], 3)  # sess1, sess2, subagent persisted

            conn = connect(db)
            def counts():
                return (conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0],
                        conn.execute("SELECT COUNT(*) FROM model_call").fetchone()[0])
            first = counts()
            self.assertEqual(first[0], 3)  # empty not persisted

            # idempotent: a second backfill converges to identical row counts
            run_backfill()
            self.assertEqual(counts(), first)

            # single-file ingest of sess1 matches the backfilled trace
            single_db = os.path.join(tmp, "single.db")
            sconn = connect(single_db)
            ingest_file(sconn, os.path.join(root, "proj1", "sess1.jsonl"), load_prices())
            self.assertEqual(
                sconn.execute("SELECT model_calls FROM session_summary WHERE session_id='sess1'").fetchone()[0],
                conn.execute("SELECT model_calls FROM session_summary WHERE session_id='sess1'").fetchone()[0])

    def test_corpus_aggregates_exports_and_handles_bad_files(self):
        # A real v1 export round-trips through corpus intake; a malformed file is
        # reported, not crashed.
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.rules import analyse
        from mrtoken.export import export_report
        from mrtoken.corpus import summarize_exports, print_corpus_report
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            transcript = os.path.join(tmp, "real.jsonl")
            write_jsonl(transcript, [
                {"type": "assistant", "sessionId": "real", "uuid": "a1",
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 50, "output_tokens": 20,
                                       "cache_read_input_tokens": 900},
                             "content": [{"type": "text", "text": "one"}]}},
                {"type": "assistant", "sessionId": "real", "uuid": "a2",
                 "message": {"id": "m2", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 40, "output_tokens": 15},
                             "content": [{"type": "text", "text": "two"}]}},
            ])
            r = ingest_file(conn, transcript, load_prices())
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                               (r["session_id"],)).fetchone()[0]
            analyse(conn, tid)
            export_path = os.path.join(tmp, "tester.json")
            with open(export_path, "w") as fh:
                fh.write(export_report(conn, redact=True))

            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as fh:
                fh.write("{ not json")
            missing = os.path.join(tmp, "nope.json")

            agg = summarize_exports([export_path, bad, missing])
            self.assertEqual(agg["files"], 1)               # only the good one combined
            self.assertEqual(agg["sessions"], 1)
            self.assertEqual(agg["total_tokens"], 50 + 20 + 40 + 15)
            self.assertEqual(len(agg["errors"]), 2)         # bad + missing reported
            self.assertIsNotNone(agg["cache_hit_ratio"])
            # printing never raises
            with contextlib.redirect_stdout(io.StringIO()):
                print_corpus_report(agg)

            # pre-1.1 export (no is_low_activity field): bucket stubs by model_calls
            legacy = os.path.join(tmp, "legacy.json")
            with open(legacy, "w") as fh:
                json.dump({"schema": "mrtoken.session_summary.v1", "tool_version": "0.4.1",
                           "sessions": [
                               {"model_calls": 1, "total_tokens": 11},   # stub
                               {"model_calls": 1, "total_tokens": 13},   # stub
                               {"model_calls": 8, "total_tokens": 50000}],  # substantive
                           }, fh)
            lg = summarize_exports([legacy])
            self.assertEqual(lg["sessions"], 1)        # only the 8-call session
            self.assertEqual(lg["low_activity"], 2)    # the two 1-call stubs bucketed

    def test_beta_summary_combines_exports_and_doctor_bundles(self):
        from mrtoken.beta_evidence import summarize_beta_evidence, print_beta_evidence
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            export_path = os.path.join(tmp, "mrtoken-beta.json")
            with open(export_path, "w") as fh:
                json.dump({
                    "schema": "mrtoken.session_summary.v1",
                    "tool_version": "0.5.8",
                    "redacted": True,
                    "sessions": [{
                        "session_id": "s1",
                        "model_calls": 8,
                        "is_low_activity": False,
                        "total_tokens": 12_000,
                        "input_tokens": 5_000,
                        "output_tokens": 1_000,
                        "cache_read_tokens": 6_000,
                        "cache_write_tokens": 0,
                        "est_cost_usd": 0.12,
                        "recommendations": [{
                            "rule": "fresh_handoff",
                            "severity": "high",
                            "est_savings_tokens": 2_000,
                        }],
                    }],
                }, fh)
            bundle_path = os.path.join(tmp, "doctor.json")
            with open(bundle_path, "w") as fh:
                json.dump({
                    "schema": "mrtoken.doctor.bundle.v1",
                    "report": {
                        "ok": True,
                        "version": "0.5.8",
                        "checks": [{"name": "release tag", "status": "ok"}],
                    },
                }, fh)

            report = summarize_beta_evidence([export_path, bundle_path])
            self.assertEqual(report["exports"]["files"], 1)
            self.assertEqual(report["doctor_bundles"]["ok"], 1)
            self.assertEqual(report["exports"]["rule_fires"]["fresh_handoff"]["high"], 1)
            self.assertFalse(report["automatic_gate"]["passed"])  # needs a second export
            with contextlib.redirect_stdout(io.StringIO()):
                print_beta_evidence(report)

    def test_offload_roi_compares_post_anchor_sessions(self):
        from mrtoken.offload_roi import compare_offload_pair, print_offload_pair
        import io, contextlib

        conn = connect(":memory:")

        def make_session(sid: str, post_tokens: list[int], post_errors: int = 0,
                         post_huge: bool = False) -> int:
            tid = conn.execute(
                "INSERT INTO trace(session_id, source, ingested_at) VALUES(?,?,?)",
                (sid, "codex", "2026-06-01T00:00:00Z"),
            ).lastrowid
            first = conn.execute(
                "INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens,"
                "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?,?)",
                (tid, "2026-06-01T00:00:00Z", 1000, 100, 9000, 0.01),
            ).lastrowid
            conn.execute(
                "INSERT INTO tool_call(trace_id,model_call_id,tool_name,output_chars) "
                "VALUES(?,?,?,?)",
                (tid, first, "Bash", 80_000),
            )
            for i, tokens in enumerate(post_tokens, start=1):
                mid = conn.execute(
                    "INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens,"
                    "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?,?)",
                    (tid, f"2026-06-01T00:00:0{i}Z", tokens, 100, 1000, tokens / 1_000_000),
                ).lastrowid
                if i <= post_errors:
                    conn.execute(
                        "INSERT INTO tool_call(trace_id,model_call_id,tool_name,is_error,output_chars) "
                        "VALUES(?,?,?,?,?)",
                        (tid, mid, "Bash", 1, 200),
                    )
                if post_huge and i == len(post_tokens):
                    conn.execute(
                        "INSERT INTO tool_call(trace_id,model_call_id,tool_name,output_chars) "
                        "VALUES(?,?,?,?)",
                        (tid, mid, "Bash", 90_000),
                    )
            return tid

        make_session("ignore-session", [5000, 5000, 5000], post_errors=1, post_huge=True)
        make_session("follow-session", [1000, 1000, 1000], post_errors=0, post_huge=False)
        conn.commit()

        report = compare_offload_pair(
            conn, "ignore", "follow", ignore_passed=True, follow_passed=True)
        self.assertEqual(report["ignore"]["post_total_tokens"], 15_300)
        self.assertEqual(report["follow"]["post_total_tokens"], 3_300)
        self.assertEqual(report["delta"]["post_total_tokens_saved"], 12_000)
        self.assertTrue(report["directional_win"])

        unknown_quality = compare_offload_pair(conn, "ignore", "follow")
        self.assertFalse(unknown_quality["directional_win"])
        with contextlib.redirect_stdout(io.StringIO()):
            print_offload_pair(report)

        def make_prevention_session(sid: str, tokens: list[int], huge_outputs: int) -> None:
            tid = conn.execute(
                "INSERT INTO trace(session_id, source, ingested_at) VALUES(?,?,?)",
                (sid, "codex", "2026-06-01T00:10:00Z"),
            ).lastrowid
            for i, tokens_i in enumerate(tokens):
                mid = conn.execute(
                    "INSERT INTO model_call(trace_id,timestamp,input_tokens,output_tokens,"
                    "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?,?)",
                    (tid, f"2026-06-01T00:10:0{i}Z", tokens_i, 100, 0, tokens_i / 1_000_000),
                ).lastrowid
                if i < huge_outputs:
                    conn.execute(
                        "INSERT INTO tool_call(trace_id,model_call_id,tool_name,output_chars) "
                        "VALUES(?,?,?,?)",
                        (tid, mid, "Bash", 80_000),
                    )

        make_prevention_session("ignore-prevent", [20_000, 20_000], huge_outputs=2)
        make_prevention_session("follow-prevent", [2_000, 2_000], huge_outputs=0)
        conn.commit()
        prevention = compare_offload_pair(
            conn, "ignore-prevent", "follow-prevent",
            ignore_passed=True, follow_passed=True, mode="prevention")
        self.assertEqual(prevention["mode"], "prevention")
        self.assertEqual(prevention["ignore"]["session_huge_outputs"], 2)
        self.assertEqual(prevention["follow"]["session_huge_outputs"], 0)
        self.assertEqual(prevention["delta"]["session_total_tokens_saved"], 36_000)
        self.assertTrue(prevention["directional_win"])

    def test_roi_measure_projection_and_cohort(self):
        # fresh_handoff before/after (ROADMAP 2.1): a long, escalating session with
        # a fresh_handoff rec yields a non-negative projected saving and a cohort.
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.roi import roi_measure, print_roi_measure
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            rows = []
            for i in range(24):  # 24 calls; output (=> cost) escalates over time
                rows.append({"type": "assistant", "sessionId": "long", "uuid": f"u{i}",
                             "message": {"id": f"m{i}", "model": "claude-opus-4-8",
                                         "usage": {"input_tokens": 10, "output_tokens": 10 + i * 20},
                                         "content": [{"type": "text", "text": f"t{i}"}]}})
            transcript = os.path.join(tmp, "long.jsonl")
            write_jsonl(transcript, rows)
            r = ingest_file(conn, transcript, load_prices())
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                               (r["session_id"],)).fetchone()[0]
            conn.execute("INSERT INTO recommendation(trace_id,rule,severity,message,created_at) "
                         "VALUES(?,?,?,?,?)", (tid, "fresh_handoff", "high", "start fresh", "2026-01-01"))
            conn.commit()

            m = roi_measure(conn, horizon=10)
            self.assertEqual(m["projection"]["n_sessions"], 1)
            self.assertGreater(m["projection"]["projected_saving_usd"], 0)  # late burn > lean opening
            self.assertEqual(m["cohort"]["acted"]["n"] + m["cohort"]["ignored"]["n"], 1)
            self.assertEqual(m["cohort"]["ignored"]["n"], 1)  # no linked follow-on session
            with contextlib.redirect_stdout(io.StringIO()):
                print_roi_measure(conn, horizon=10)

    def test_roi_measure_cross_session_linkage(self):
        # GOALS/roi-cross-session-linkage.md: method B classifies a fired session
        # as "acted" when a separate fresh session started in the same project
        # within LINKAGE_WINDOW_MIN of its end — not by splitting one session at
        # its midpoint (which made B degenerate: fresh_handoff only fires deep).
        from mrtoken.roi import roi_measure
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))

            def add_trace(sid, project, start, end, parent=None):
                conn.execute(
                    "INSERT INTO trace(session_id,parent_session_id,project_path,"
                    "started_at,ended_at,ingested_at) VALUES(?,?,?,?,?,?)",
                    (sid, parent, project, start, end, "t"))
                return conn.execute("SELECT id FROM trace WHERE session_id=?",
                                    (sid,)).fetchone()[0]

            def add_calls(tid, hour, n=6, cost=0.1):
                for i in range(n):
                    conn.execute(
                        "INSERT INTO model_call(trace_id,timestamp,est_cost_usd) "
                        "VALUES(?,?,?)",
                        (tid, f"2026-07-01T{hour:02d}:{i:02d}:00Z", cost))

            def fire(tid):
                conn.execute(
                    "INSERT INTO recommendation(trace_id,rule,severity,message,"
                    "created_at) VALUES(?,?,?,?,?)",
                    (tid, "fresh_handoff", "high", "start fresh", "t"))

            # ACTED: ends 10:05, fresh same-project session starts 10:20 (≤30m).
            t1 = add_trace("acted1", "/p/alpha", "2026-07-01T09:00:00Z",
                           "2026-07-01T10:05:00Z")
            add_calls(t1, 9); fire(t1)
            add_trace("follow1", "/p/alpha", "2026-07-01T10:20:00Z", None)
            # IGNORED: next same-project session starts 6h later (outside window).
            t2 = add_trace("ign1", "/p/beta", "2026-07-01T09:00:00Z",
                           "2026-07-01T10:00:00Z")
            add_calls(t2, 9); fire(t2)
            add_trace("late1", "/p/beta", "2026-07-01T16:00:00Z", None)
            # IGNORED: a subagent transcript in-window must NOT count as acting.
            t3 = add_trace("ign2", "/p/gamma", "2026-07-01T09:00:00Z",
                           "2026-07-01T10:00:00Z")
            add_calls(t3, 9); fire(t3)
            add_trace("sub1", "/p/gamma", "2026-07-01T10:10:00Z", None, parent="ign2")
            conn.commit()

            m = roi_measure(conn, horizon=10)
            self.assertEqual(m["cohort"]["acted"]["n"], 1)      # non-degenerate B
            self.assertEqual(m["cohort"]["ignored"]["n"], 2)
            self.assertIsNotNone(m["cohort"]["acted"]["late_per_call_usd"])
            self.assertEqual(m["projection"]["n_sessions"], 3)  # C unchanged

    def test_fleet_counts_codex_sessions(self):
        # fleet must count Codex sessions (source='codex'), not just claude_code.
        from mrtoken.ingest_codex import ingest_codex_file
        from mrtoken.fleet import fleet_summary
        import io, contextlib, re
        with tempfile.TemporaryDirectory() as tmp:
            codex = os.path.join(tmp, "rollout-x.jsonl")
            write_jsonl(codex, [
                {"timestamp": "2026-06-24T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cxf", "cwd": "/proj"}},
                {"timestamp": "2026-06-24T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.5"}},
                {"timestamp": "2026-06-24T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 200,
                     "total_tokens": 5200}}}},
                {"timestamp": "2026-06-24T00:00:03Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 6000, "cached_input_tokens": 5000, "output_tokens": 150,
                     "total_tokens": 6150}}}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            ingest_codex_file(conn, codex)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fleet_summary(conn)
            m = re.search(r"sessions\s+(\d+)", buf.getvalue())
            self.assertIsNotNone(m)
            self.assertGreaterEqual(int(m.group(1)), 1)  # the codex session is counted

    def test_backfill_sweeps_codex_dir(self):
        # Codex-dir backfill routes ~/.codex rollouts to the CENTRAL Codex DB
        # (--codex-db), NOT the per-project Claude --db.
        from mrtoken.ingest import main as ingest_main
        import io, contextlib
        with tempfile.TemporaryDirectory() as tmp:
            claude_root = os.path.join(tmp, "claude"); os.makedirs(claude_root)  # empty Claude side
            codex_root = os.path.join(tmp, "codex", "2026", "06", "24")
            os.makedirs(codex_root)
            write_jsonl(os.path.join(codex_root, "rollout-x.jsonl"), [
                {"timestamp": "2026-06-24T00:00:00Z", "type": "session_meta",
                 "payload": {"session_id": "cxbf", "cwd": "/proj"}},
                {"timestamp": "2026-06-24T00:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.5"}},
                {"timestamp": "2026-06-24T00:00:02Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 5000, "cached_input_tokens": 4000,
                     "output_tokens": 200, "total_tokens": 5200}}}},
            ])
            db = os.path.join(tmp, "c.db")           # Claude DB
            codex_db = os.path.join(tmp, "codex.db")  # central Codex DB
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ingest_main(["--backfill", "--projects-root", claude_root,
                             "--codex-root", os.path.join(tmp, "codex"),
                             "--codex-db", codex_db, "--db", db])
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["codex_seen"], 1)
            self.assertEqual(summary["codex_sessions"], 1)
            self.assertEqual(summary["codex_db"], codex_db)
            # codex landed in the central Codex DB, not the Claude --db
            cconn = connect(codex_db)
            self.assertEqual(cconn.execute(
                "SELECT source FROM trace WHERE session_id='cxbf'").fetchone()[0], "codex")
            dconn = connect(db)
            self.assertIsNone(dconn.execute(
                "SELECT 1 FROM trace WHERE session_id='cxbf'").fetchone())

    def test_export_since_filter_and_session_detail(self):
        # ROADMAP backlog: --since (incremental refresh) + session_detail timeline.
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.export import export_report, export_detail
        def sess(sid, ts0, ts1):
            return [
                {"type": "assistant", "sessionId": sid, "uuid": sid + "1", "timestamp": ts0,
                 "message": {"id": "m1", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "a"}]}},
                {"type": "assistant", "sessionId": sid, "uuid": sid + "2", "timestamp": ts1,
                 "message": {"id": "m2", "model": "claude-opus-4-8",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "b"}]}},
            ]
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(os.path.join(tmp, "t.db"))
            old = os.path.join(tmp, "old.jsonl"); new = os.path.join(tmp, "new.jsonl")
            write_jsonl(old, sess("old", "2026-06-01T00:00:00Z", "2026-06-01T00:01:00Z"))
            write_jsonl(new, sess("new", "2026-06-20T00:00:00Z", "2026-06-20T00:01:00Z"))
            ingest_file(conn, old, load_prices())
            ingest_file(conn, new, load_prices())

            # --since keeps only the newer session
            d = json.loads(export_report(conn, since="2026-06-10T00:00:00Z"))
            sids = {s["session_id"] for s in d["sessions"]}
            self.assertEqual(sids, {"new"})

            # session_detail timeline: one row per model call, ordered
            det = json.loads(export_detail(conn, "new"))
            self.assertEqual(det["schema"], "mrtoken.session_detail.v1")
            self.assertEqual(len(det["calls"]), 2)
            self.assertEqual(det["calls"][0]["session_id"], "new")
            self.assertEqual(det["calls"][0]["timestamp"], "2026-06-20T00:00:00Z")

    def test_ingest_extracts_title_and_export_redacts(self):
        from mrtoken.ingest import ingest_file, load_prices
        from mrtoken.rules import analyse
        from mrtoken.export import export_report
        with tempfile.TemporaryDirectory() as tmp:
            transcript = os.path.join(tmp, "s.jsonl")
            write_jsonl(transcript, [
                {"type": "custom-title", "customTitle": "Secret Acme migration"},
                {"type": "user", "message": {"content": "do the thing"}},
                {"type": "assistant", "sessionId": "sx", "uuid": "a1",
                 "cwd": "/Users/alice/secret-proj",
                 "message": {"model": "claude-sonnet-4",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "ok"}]}},
            ])
            conn = connect(os.path.join(tmp, "t.db"))
            r = ingest_file(conn, transcript, load_prices())
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                               (r["session_id"],)).fetchone()[0]
            analyse(conn, tid)

            plain = json.loads(export_report(conn))["sessions"][0]
            self.assertEqual(plain["title"], "Secret Acme migration")   # ingest reads customTitle
            self.assertEqual(plain["project_path"], "/Users/alice/secret-proj")

            doc = json.loads(export_report(conn, redact=True))
            red = doc["sessions"][0]
            from mrtoken import __version__
            self.assertEqual(doc["tool_version"], __version__)  # export self-identifies
            self.assertTrue(doc["redacted"])
            self.assertIsNone(red["title"])           # work-revealing fields stripped
            self.assertIsNone(red["project_path"])
            self.assertEqual(red["model_calls"], plain["model_calls"])  # metrics kept

    def test_latest_transcript_prefers_session_over_newest(self):
        # the K2 multi-agent trap: another agent's transcript is newer, but the
        # CURRENT session (by env id) must win — not newest-mtime-across-projects
        import mrtoken.watch as w
        with tempfile.TemporaryDirectory() as tmp:
            cur_d = os.path.join(tmp, "-proj-a"); other_d = os.path.join(tmp, "-proj-b")
            os.makedirs(cur_d); os.makedirs(other_d)
            cur = os.path.join(cur_d, "aaaa1111.jsonl")
            other = os.path.join(other_d, "bbbb2222.jsonl")
            for f in (cur, other):
                with open(f, "w") as h:
                    h.write("{}\n")
            os.utime(cur, (1, 1))                      # current session OLDER
            os.utime(other, (10**9, 10**9))            # other agent NEWER
            real = w.PROJECTS
            w.PROJECTS = tmp
            os.environ["MRTOKEN_SESSION"] = "aaaa1111"
            try:
                # cwd that won't match either dir -> would fall to newest (other)
                self.assertEqual(w.latest_transcript("/no/such/cwd"), cur)
            finally:
                w.PROJECTS = real
                del os.environ["MRTOKEN_SESSION"]

    def test_context_window_config_override(self):
        # a persistent override (config or env) pins the window -> no tier-flip
        import mrtoken.statusline as sl
        saved = sl._config_context_max
        sl._config_context_max = lambda: 1_000_000
        try:
            self.assertEqual(sl.context_window(50_000), 1_000_000)   # not the 200k tier
            self.assertEqual(sl.context_window(0), 1_000_000)
        finally:
            sl._config_context_max = saved

    def test_context_window_is_sticky_within_session(self):
        # the wildness fix: window ratchets up off the session MAX, so a dip
        # (e.g. after a compaction) does NOT flip ctx% back across a tier
        from mrtoken.watch import LiveMonitor
        from mrtoken.statusline import context_window
        mon = LiveMonitor(emit=lambda _: None)
        mon.feed({"type": "assistant", "message": {"model": "claude-sonnet-4",
            "usage": {"input_tokens": 1, "cache_read_input_tokens": 250_000, "output_tokens": 1}}})
        mon.feed({"type": "assistant", "message": {"model": "claude-sonnet-4",
            "usage": {"input_tokens": 1, "cache_read_input_tokens": 50_000, "output_tokens": 1}}})  # dip
        snap = mon.snapshot()
        self.assertGreaterEqual(snap["context_max"], 250_000)            # ratcheted up
        self.assertEqual(context_window(snap["context_max"]), 1_000_000)  # stays 1M, no flip-back

    def test_context_window_inferred_from_usage(self):
        from mrtoken.statusline import context_window
        self.assertEqual(context_window(150_000), 200_000)    # fits the 200k tier
        self.assertEqual(context_window(199_999), 200_000)
        self.assertEqual(context_window(319_000), 1_000_000)  # exceeds 200k -> 1M window
        self.assertEqual(context_window(0), 200_000)
        os.environ["MRTOKEN_CONTEXT_MAX"] = "500000"          # explicit override wins
        try:
            self.assertEqual(context_window(10), 500_000)
        finally:
            del os.environ["MRTOKEN_CONTEXT_MAX"]

    def test_live_monitor_dedupes_usage_per_message_id(self):
        from mrtoken.watch import LiveMonitor
        mon = LiveMonitor(emit=lambda _: None)
        usage = {"input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}
        # two transcript lines, ONE API response (same message.id), usage repeated
        for content in ([{"type": "text", "text": "ok"}],
                        [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]):
            mon.feed({"type": "assistant", "message": {
                "id": "m1", "model": "claude-sonnet-4", "usage": usage, "content": content}})
        self.assertEqual(mon.snapshot()["model_calls"], 1)   # counted once, not twice
        self.assertGreater(mon.snapshot()["cum_cost"], 0)
        self.assertEqual(mon.tool_counts.get("read"), 1)     # tool still captured
        # a DISTINCT response counts again
        mon.feed({"type": "assistant", "message": {
            "id": "m2", "model": "claude-sonnet-4", "usage": usage, "content": []}})
        self.assertEqual(mon.snapshot()["model_calls"], 2)

    def test_live_monitor_projects_turns_to_warn(self):
        from mrtoken.watch import LiveMonitor
        # context climbing ~10k/turn from 20k->90k; 200k window -> 140k warn -> ~5 turns
        mon = LiveMonitor(emit=lambda _: None)
        for i in range(8):
            ctx = 20000 + i * 10000
            mon.feed({"type": "assistant", "message": {"id": f"m{i}", "model": "claude-sonnet-4",
                "usage": {"cache_read_input_tokens": ctx, "input_tokens": 0, "output_tokens": 1},
                "content": []}})
        ttw = mon.snapshot()["turns_to_warn"]
        self.assertIsNotNone(ttw)
        self.assertTrue(3 <= ttw <= 7, ttw)   # ~5 turns of lead time
        # a flat session has no imminent wall
        flat = LiveMonitor(emit=lambda _: None)
        for i in range(8):
            flat.feed({"type": "assistant", "message": {"id": f"f{i}", "model": "claude-sonnet-4",
                "usage": {"cache_read_input_tokens": 50000, "input_tokens": 0, "output_tokens": 1},
                "content": []}})
        self.assertIsNone(flat.snapshot()["turns_to_warn"])

    def test_live_monitor_detects_re_read_loop(self):
        from mrtoken.watch import LiveMonitor
        out = []
        mon = LiveMonitor(emit=out.append)
        # read the SAME target (identical input → identical hash) 3 times
        same_input = {"file_path": "/repo/big.py"}
        for i in range(3):
            mon.feed({"type": "assistant", "message": {
                "model": "claude-sonnet-4", "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [{"type": "tool_use", "id": f"r{i}", "name": "Read",
                             "input": same_input}]}})
            mon.feed({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"r{i}", "content": "y" * 8000}]}})
        joined = "\n".join(out)
        self.assertIn("re-read the same read target", joined)
        self.assertIn("re_read_loop", mon.snapshot()["signals_fired"])

    def test_live_monitor_distinct_reads_dont_trigger(self):
        from mrtoken.watch import LiveMonitor
        mon = LiveMonitor(emit=lambda _: None)
        # three reads of DIFFERENT targets → distinct hashes → no loop
        for i in range(3):
            mon.feed({"type": "assistant", "message": {
                "model": "claude-sonnet-4", "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [{"type": "tool_use", "id": f"d{i}", "name": "Read",
                             "input": {"file_path": f"/repo/file{i}.py"}}]}})
        self.assertNotIn("re_read_loop", mon.snapshot()["signals_fired"])

    def test_watch_is_profile_aware(self):
        from mrtoken.watch import LiveMonitor
        out = []
        mon = LiveMonitor(emit=out.append)
        # feed several read/search tool_use blocks → should classify research
        for i in range(5):
            mon.feed({"type": "assistant", "message": {
                "model": "claude-sonnet-4", "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [{"type": "tool_use", "id": f"t{i}", "name": "Read", "input": {}}]}})
        self.assertEqual(mon.profile, "research")
        self.assertEqual(mon.huge_threshold, 80_000)  # research tolerates big reads


    def test_handoff_builds_from_transcript(self):
        from mrtoken.handoff import build_handoff
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            real = os.path.join(tmp, "auth.py")
            with open(real, "w") as h:
                h.write("# real file\n")
            transcript = os.path.join(tmp, "sess-handoff.jsonl")
            write_jsonl(transcript, [
                {"type": "user", "timestamp": "2026-06-01T00:00:00Z",
                 "message": {"content": "Add OAuth login to the API"}},
                {"type": "assistant", "sessionId": "sess-handoff", "uuid": "a1",
                 "timestamp": "2026-06-01T00:00:01Z", "cwd": tmp,
                 "message": {"model": "claude-sonnet-4",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [
                                 {"type": "tool_use", "id": "t1", "name": "Write",
                                  "input": {"file_path": real}},
                                 {"type": "tool_use", "id": "t2", "name": "Edit",
                                  "input": {"file_path": "/proj/gone.py"}}]}},
                {"type": "user", "timestamp": "2026-06-01T00:00:02Z",
                 "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                          "content": "ok"}]}},
                {"type": "user", "timestamp": "2026-06-01T00:00:03Z",
                 "message": {"content": "now add refresh tokens"}},
            ])
            db = os.path.join(tmp, ".token-tithe", "token-tithe.db")
            md = build_handoff(db, transcript)
            self.assertIn("now add refresh tokens", md)   # goal = most recent request
            self.assertIn(real, md)                       # edited file that still exists
            self.assertNotIn("/proj/gone.py", md)         # stale path filtered out

    def test_handoff_prefers_title_and_filters_stale(self):
        from mrtoken.handoff import _scan_transcript, build_handoff
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            f1 = os.path.join(tmp, "first.py"); f2 = os.path.join(tmp, "second.py")
            for f in (f1, f2):
                with open(f, "w") as h:
                    h.write("x\n")
            transcript = os.path.join(tmp, "sess.jsonl")
            write_jsonl(transcript, [
                {"type": "ai-title", "aiTitle": "Build the CRM engine"},
                {"type": "user", "message": {"content": "continue harkable"}},  # stale opener
                {"type": "assistant", "sessionId": "sess", "uuid": "a1", "cwd": tmp,
                 "message": {"model": "claude-sonnet-4",
                             "usage": {"input_tokens": 1, "output_tokens": 1},
                             "content": [
                                 {"type": "tool_use", "id": "t1", "name": "Write",
                                  "input": {"file_path": f1}},
                                 {"type": "tool_use", "id": "t2", "name": "Edit",
                                  "input": {"file_path": "/gone/old.py"}},
                                 {"type": "tool_use", "id": "t3", "name": "Edit",
                                  "input": {"file_path": f2}}]}},
                {"type": "user", "message": {"content": "wire up the pipeline endpoint"}},
            ])
            db = os.path.join(tmp, ".token-tithe", "token-tithe.db")
            # recency-ordered + existence-filtered: f2 (last touched) first, no stale
            self.assertEqual(_scan_transcript(transcript)["changed_files"], [f2, f1])
            md = build_handoff(db, transcript)
            # CONTRACT CORRECTED: this is an `ai-title`, a session-START artifact that never
            # refreshes (measured: 132 events, 1 distinct value, first == last on a real
            # session). It must NOT outrank the most recent substantive request. A HUMAN
            # `custom-title` still wins — asserted in test_handoff_goal_currency.
            self.assertNotIn("Build the CRM engine", md)       # auto-title no longer wins
            self.assertIn("wire up the pipeline endpoint", md) # the CURRENT request does
            self.assertIn("wire up the pipeline endpoint", md)  # shown as "where I left off"
            self.assertNotIn("continue harkable", md)          # stale opener never surfaces
            self.assertNotIn("/gone/old.py", md)               # stale path filtered


    def test_why_names_dominant_cost_shape(self):
        from mrtoken.why import diagnose
        conn, tid = make_trace()
        # cache-read dominated session → "carrying cached context" should win
        conn.execute(
            "INSERT INTO model_call(trace_id, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens) VALUES(?,?,?,?,?,?)",
            (tid, "claude-sonnet-4", 100, 500, 500_000, 1000))
        conn.commit()
        d = diagnose(conn, tid)
        self.assertIn("carrying cached context", d["headline"])

    def test_savings_card_priority_evidence_and_provenance(self):
        from mrtoken.savings_card import build_savings_card
        card = build_savings_card([
            {"rule": "retry_loop", "message": "three errors", "evidence_json": '{"error_count": 3}'},
            {"rule": "fresh_handoff", "message": "late context growth", "evidence_json": '{"signals": ["growth"]}'},
        ])
        self.assertEqual(card["action"], "handoff/compact experiment candidate")
        self.assertEqual(card["evidence"]["details"]["signals"], ["growth"])
        self.assertIn("measured", card["provenance"])
        self.assertIn("not realized", card["provenance"]["estimated"])

    def test_savings_card_quality_gate_and_suppression(self):
        from mrtoken.savings_card import build_savings_card, render_savings_card
        recs = [{"rule": "huge_tool_output", "message": "large output", "evidence_json": "{}"},
                {"rule": "retry_loop", "message": "errors", "evidence_json": "{}"}]
        card = build_savings_card(recs)
        self.assertEqual(card["action"], "prevent next bulky output")
        self.assertIn("oracle", card["quality_gate"])
        self.assertIn("offload=off", card["suppression"])
        rendered = "\n".join(render_savings_card(card))
        self.assertIn("not now:", rendered)
        self.assertIn("never suggest this:", rendered)
        suppressed = build_savings_card(recs, suppressed=("offload",))
        self.assertEqual(suppressed["action"], "stop and re-plan")

    def test_savings_card_routing_requires_all_supplied_inputs(self):
        from mrtoken.savings_card import build_savings_card
        from mrtoken.status import status_snapshot
        from mrtoken.why import print_diagnosis
        from mrtoken import cli
        from unittest.mock import Mock, patch
        import contextlib, io
        partial = build_savings_card([], routing={"baseline": "strong", "candidate": "cheap"})
        self.assertEqual(partial["action"], "continue")
        routing = {"baseline": "strong", "candidate": "cheap", "capability_floor": 2,
                   "budget": 1.0, "oracle": "tests pass"}
        card = build_savings_card([], routing=routing)
        self.assertEqual(card["action"], "routing experiment candidate")
        self.assertIn("no provider is switched", card["provenance"]["estimated"])
        self.assertIn("savings=off", card["suppression"])
        conn, tid = make_trace()
        self.assertEqual(status_snapshot(conn, tid, routing=routing)["card"]["action"],
                         "routing experiment candidate")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_diagnosis(conn, "session-1", routing=routing)
        self.assertIn("routing experiment candidate", out.getvalue())
        args = ["why", "s1", "--baseline", "strong", "--candidate", "cheap",
                "--capability-floor", "2", "--budget", "1.00", "--oracle", "tests pass"]
        cli_routing = {"baseline": "strong", "candidate": "cheap", "capability_floor": "2",
                       "budget": "1.00", "oracle": "tests pass"}
        db = Mock()
        with patch("mrtoken.cli._open_readonly", return_value=db) as opened, \
             patch("mrtoken.why.print_diagnosis") as printed:
            cli.main(args)
        opened.assert_called_once()
        printed.assert_called_once_with(db, "s1", routing=cli_routing)
        db.close.assert_called_once()

    def test_disposable_savings_card_demo_is_hermetic_and_fails_bad_oracle(self):
        from mrtoken.disposable_demo import run
        with tempfile.TemporaryDirectory() as tmp:
            status, text = run(os.path.join(tmp, "pass"))
            self.assertEqual(status, 0)
            self.assertIn("routing experiment candidate", text)
            self.assertIn("measured session data: UNKNOWN", text)
            self.assertIn("provider/model call or switch: none", text)
            self.assertIn("confinement: PASS", text)
            failed, text = run(os.path.join(tmp, "fail"), expected_action="continue")
            self.assertEqual(failed, 1)
            self.assertIn("oracle: FAIL", text)

    def test_documented_disposable_demo_keeps_fresh_archive_clean(self):
        repo = Path(__file__).resolve().parents[2]
        command = ("PYTHONDONTWRITEBYTECODE=1 MRTOKEN_PRICES= "
                   'PYTHONPATH="$PWD/backend" python3 -m mrtoken.cli demo')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source"
            archive.mkdir()
            packed = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=repo,
                                    check=True, capture_output=True).stdout
            with tarfile.open(fileobj=io.BytesIO(packed)) as bundle:
                bundle.extractall(archive, filter="data")
            before = {path.relative_to(archive).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in archive.rglob("*") if path.is_file()}
            env = os.environ.copy()
            env.update({"HOME": str(root / "real-home"), "XDG_DATA_HOME": str(root / "real-data")})
            for key in ("MRTOKEN_DB", "TOKEN_TITHE_DB"):
                env.pop(key, None)
            completed = subprocess.run(["/bin/sh", "-c", command], cwd=archive, env=env,
                                       text=True, capture_output=True)
            after = {path.relative_to(archive).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in archive.rglob("*") if path.is_file()}
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("routing experiment candidate", completed.stdout)
        self.assertIn("oracle: PASS", completed.stdout)
        self.assertEqual(before, after)
        self.assertFalse(any("__pycache__" in path or path.endswith(".pyc") for path in after))

    def test_why_prints_one_savings_decision_card(self):
        from mrtoken.why import print_diagnosis
        import contextlib, io
        conn, tid = make_trace()
        conn.execute("INSERT INTO recommendation(trace_id,rule,severity,message,created_at) "
                     "VALUES(?,?,?,?,?)", (tid, "retry_loop", "warn", "three errors", "t"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_diagnosis(conn, "session-1")
        text = out.getvalue()
        self.assertIn("savings decision:", text)
        self.assertIn("stop and re-plan", text)
        self.assertIn("provenance: measured", text)

    def test_roi_reports_categories_and_handoff(self):
        from mrtoken.roi import roi_session
        conn, tid = make_trace()
        conn.execute("INSERT INTO model_call(trace_id, output_tokens, cache_read_input_tokens) "
                     "VALUES(?,?,?)", (tid, 100, 50_000))
        conn.execute("INSERT INTO tool_call(trace_id, tool_name, output_chars, output_tokens_est) "
                     "VALUES(?,?,?,?)", (tid, "Read", 60_000, 15_000))  # oversized
        conn.commit()
        r = roi_session(conn, tid)
        self.assertGreater(r["categories"]["oversized tool outputs (excess)"], 0)
        self.assertIsNotNone(r["handoff"])
        self.assertGreater(r["handoff"]["saving_per_future_call"], 0)


    def test_re_read_loop_detects_repeated_reads(self):
        from mrtoken.rules import rule_re_read_loop
        conn, tid = make_trace()
        # same Read (same input hash) 4 times = 3 redundant re-reads
        for _ in range(4):
            conn.execute("INSERT INTO tool_call(trace_id, tool_name, input_hash, output_tokens_est) "
                         "VALUES(?,?,?,?)", (tid, "Read", "samehash", 1000))
        # a one-off read should not count
        conn.execute("INSERT INTO tool_call(trace_id, tool_name, input_hash, output_tokens_est) "
                     "VALUES(?,?,?,?)", (tid, "Read", "otherhash", 500))
        conn.commit()
        recs = rule_re_read_loop(conn, tid)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["rule"], "re_read_loop")
        import json
        ev = json.loads(recs[0]["evidence_json"])
        self.assertEqual(ev["redundant_reads"], 3)
        self.assertEqual(ev["wasted_tokens_est"], 3000)

    def test_status_snapshot_flags_large_context(self):
        from mrtoken.status import status_snapshot
        # 180k on a 200k window = 90% full -> large
        conn, tid = make_trace()
        conn.execute("INSERT INTO model_call(trace_id, timestamp, input_tokens, output_tokens, "
                     "cache_read_input_tokens) VALUES(?,?,?,?,?)",
                     (tid, "2026-06-01T00:00:00Z", 100, 50, 180_000))
        conn.commit()
        s = status_snapshot(conn, tid)
        self.assertEqual(s["calls"], 1)
        self.assertTrue(s["context_large"])          # 180k/200k = 90% -> large

    def test_status_large_is_window_aware_on_1m(self):
        # 360k can only occur on a >200k window, so it's a ~36%-full 1M session,
        # NOT "large" — the bug that pinned 1M sessions at 99%/compact-soon
        from mrtoken.status import status_snapshot
        conn, tid = make_trace()
        conn.execute("INSERT INTO model_call(trace_id, timestamp, input_tokens, output_tokens, "
                     "cache_read_input_tokens) VALUES(?,?,?,?,?)",
                     (tid, "2026-06-01T00:00:00Z", 100, 50, 360_000))
        conn.commit()
        s = status_snapshot(conn, tid)
        self.assertFalse(s["context_large"])         # 360k/1M = 36% -> not large

    def test_status_prints_feedback_command_for_top_signal(self):
        from mrtoken.status import print_status
        from mrtoken.ingest import ingest_file
        from mrtoken.rules import analyse
        import contextlib, io
        with tempfile.TemporaryDirectory() as tmp:
            transcript = os.path.join(tmp, "fb-status.jsonl")
            write_jsonl(transcript, [
                {"type": "assistant", "sessionId": "fb-status", "uuid": "a1",
                 "message": {"id": "m1", "model": "claude-sonnet-4",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                          "input": {"file_path": "big.txt"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result",
                 "tool_use_id": "t1", "content": "x" * 200_000}]}},
                {"type": "assistant", "sessionId": "fb-status", "uuid": "a2",
                 "message": {"id": "m2", "model": "claude-sonnet-4",
                             "usage": {"input_tokens": 10, "output_tokens": 5},
                             "content": [{"type": "text", "text": "ok"}]}},
            ])
            db = os.path.join(tmp, "t.db")
            conn = connect(db)
            ingested = ingest_file(conn, transcript, load_prices())
            tid = conn.execute("SELECT id FROM trace WHERE session_id=?", (ingested["session_id"],)).fetchone()[0]
            analyse(conn, tid)
            conn.close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = print_status(db, "fb-status")
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("next: [huge_tool_output]", text)
            self.assertIn("quality gate:", text)
            self.assertIn("provenance: estimated", text)
            self.assertIn("feedback: mrtoken-transcript feedback fb-statu huge_tool_output", text)

    def test_readonly_analysis_commands_never_mutate_a_complete_codex_store(self):
        """CLI reads use mode=ro; the immutable copy proves the full render is write-free."""
        from unittest.mock import patch
        import contextlib
        from mrtoken import cli
        from mrtoken.ingest import connect_readonly

        def run_cli(args):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                try:
                    cli.main(args)
                except SystemExit as exc:
                    self.assertIn(exc.code, (None, 0), out.getvalue())
            return out.getvalue()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "XDG_DATA_HOME": os.path.join(tmp, "xdg"), "MRTOKEN_PRICES": ""
        }, clear=False):
            db = os.path.join(tmp, "codex.db")
            conn = connect(db)
            tid = conn.execute(
                "INSERT INTO trace(source,session_id,started_at,ingested_at) VALUES(?,?,?,?)",
                ("codex", "codex-readonly", "2026-06-01T00:00:00Z", "now"),
            ).lastrowid
            conn.execute("INSERT INTO model_call(trace_id,model,input_tokens,output_tokens,"
                         "cache_read_input_tokens,est_cost_usd) VALUES(?,?,?,?,?,?)",
                         (tid, "gpt-5.6-terra", 10, 5, 20, 1.25))
            conn.commit()
            conn.close()

            # Product connection: SQLite itself rejects attempted writes.
            ro = connect_readonly(db)
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("UPDATE trace SET title='must-not-write'")
            ro.close()

            # Deliberately stale persisted view: the copied store is never opened by
            # ordinary connect(), so only the read path can make this agree with code.
            stale = sqlite3.connect(db)
            stale.execute("PRAGMA journal_mode=WAL")
            stale.execute("DROP VIEW session_summary")
            stale.execute("CREATE VIEW session_summary AS SELECT t.id AS trace_id, "
                          "'api' AS billing_mode, 999 AS cumulative_expenditure_tokens, "
                          "'provider-reported' AS cumulative_expenditure_provenance, "
                          "999 AS api_est_cost_usd, 0 AS cache_hit_ratio, 0 AS tool_errors "
                          "FROM trace t")
            stale.commit()
            stale.close()
            product_outputs = {
                "why": run_cli(["why", "codex-readonly", "--db", db]),
                "status": run_cli(["status", "codex-readonly", "--db", db]),
                "report": run_cli(["report", "codex-readonly", "--db", db]),
                "savings": run_cli(["savings", "--db", db]),
            }
            self.assertIn("why is codex-re", product_outputs["why"])
            self.assertIn("mr token status · codex-re", product_outputs["status"])
            self.assertIn("usage type unknown", product_outputs["status"])
            self.assertIn("cumulative token total", product_outputs["report"])
            self.assertIn("MR Token — savings", product_outputs["savings"])
            frozen_dir = os.path.join(tmp, "immutable")
            os.mkdir(frozen_dir)
            frozen_db = os.path.join(frozen_dir, "codex.db")
            shutil.copyfile(db, frozen_db)
            before_tree = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in Path(frozen_dir).iterdir() if p.is_file()}
            opened = []

            def immutable_open(_):
                conn = connect_readonly(frozen_db, immutable=True)
                opened.append(conn)
                return conn

            with patch("mrtoken.cli.connect_readonly", side_effect=immutable_open), \
                 patch("mrtoken.status.connect_readonly", side_effect=immutable_open):
                outputs = {
                    "why": run_cli(["why", "codex-readonly", "--db", frozen_db]),
                    "status": run_cli(["status", "codex-readonly", "--db", frozen_db]),
                    "report": run_cli(["report", "codex-readonly", "--db", frozen_db]),
                    "savings": run_cli(["savings", "--db", frozen_db]),
                }
            for conn in opened:
                conn.close()
            self.assertIn("why is codex-re", outputs["why"])
            self.assertIn("mr token status · codex-re", outputs["status"])
            self.assertIn("usage type unknown", outputs["status"])
            self.assertIn("cumulative token total", outputs["report"])
            self.assertIn("MR Token — savings", outputs["savings"])
            after_tree = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in Path(frozen_dir).iterdir() if p.is_file()}
            self.assertEqual(before_tree, after_tree)

            # Positive control: ingest is intentionally write-capable, so the
            # fixture and the before/after assertion can actually observe a write.
            control_db = os.path.join(tmp, "control.db")
            shutil.copyfile(db, control_db)
            control = sqlite3.connect(control_db)
            control.execute("PRAGMA journal_mode=DELETE")
            control.close()
            control_before = hashlib.sha256(Path(control_db).read_bytes()).hexdigest()
            transcript = os.path.join(tmp, "control.jsonl")
            write_jsonl(transcript, [{"type": "assistant", "sessionId": "control", "uuid": "u1",
                                     "message": {"id": "m1", "model": "claude-sonnet-4",
                                                 "usage": {"input_tokens": 1, "output_tokens": 1},
                                                 "content": [{"type": "text", "text": "ok"}]}}])
            run_cli(["ingest", transcript, "--db", control_db])
            control_after = hashlib.sha256(Path(control_db).read_bytes()).hexdigest()
            self.assertNotEqual(control_before, control_after)

    def test_readonly_analysis_reports_upgrade_requirement_without_migration(self):
        from mrtoken import cli
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            old_db = os.path.join(tmp, "old.db")
            old = sqlite3.connect(old_db)
            old.execute("CREATE TABLE trace(id INTEGER PRIMARY KEY)")
            old.commit()
            old.close()
            before = hashlib.sha256(Path(old_db).read_bytes()).hexdigest()
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exited:
                cli.main(["report", "old", "--db", old_db])
            self.assertEqual(exited.exception.code, 2)
            self.assertIn("mrtoken: database upgrade required: missing", out.getvalue())
            self.assertEqual(before, hashlib.sha256(Path(old_db).read_bytes()).hexdigest())

    def test_readonly_analysis_reports_upgrade_requirement_for_outdated_column(self):
        """A current table missing a migrated column must fail at the read boundary."""
        from mrtoken import cli
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            old_db = os.path.join(tmp, "old-column.db")
            conn = connect(old_db)
            conn.close()
            legacy = sqlite3.connect(old_db)
            legacy.execute("DROP VIEW session_summary")
            legacy.execute("DROP VIEW session_detail")
            legacy.execute("ALTER TABLE trace DROP COLUMN title")
            legacy.commit()
            self.assertNotIn("title", {row[1] for row in legacy.execute("PRAGMA table_info(trace)")})
            legacy.close()
            before = hashlib.sha256(Path(old_db).read_bytes()).hexdigest()
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exited:
                cli.main(["report", "--db", old_db])
            self.assertEqual(exited.exception.code, 2)
            self.assertIn("mrtoken: database upgrade required", out.getvalue())
            self.assertEqual(before, hashlib.sha256(Path(old_db).read_bytes()).hexdigest())

    def test_datadir_non_project_routes_central_not_cwd(self):
        """The scatter-bug fix: a non-project cwd must NOT get a .token-tithe/."""
        from mrtoken import datadir
        import contextlib
        @contextlib.contextmanager
        def env(**kv):
            old = {k: os.environ.get(k) for k in kv}
            for k, v in kv.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            try:
                yield
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

        with tempfile.TemporaryDirectory() as nonproj, tempfile.TemporaryDirectory() as central:
            with env(MRTOKEN_DATA_DIR=None, TOKEN_TITHE_DB=None, MRTOKEN_DB=None,
                     XDG_DATA_HOME=central):
                db = datadir.resolve_db_path(nonproj)
                self.assertFalse(db.startswith(nonproj), "must not scatter into the cwd")
                self.assertTrue(db.startswith(os.path.join(central, "token-tithe", "projects")))
                self.assertIn(datadir.project_key(nonproj), db)

    def test_datadir_per_project_and_full_central_optin(self):
        from mrtoken import datadir
        import contextlib
        @contextlib.contextmanager
        def env(**kv):
            old = {k: os.environ.get(k) for k in kv}
            for k, v in kv.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            try:
                yield
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as central:
            open(os.path.join(proj, "package.json"), "w").close()  # real project
            with env(MRTOKEN_DATA_DIR=None, TOKEN_TITHE_DB=None, MRTOKEN_DB=None):
                self.assertEqual(datadir.resolve_db_path(proj),
                                 os.path.join(proj, ".token-tithe", "token-tithe.db"))
            with env(MRTOKEN_DATA_DIR=central, TOKEN_TITHE_DB=None, MRTOKEN_DB=None):
                db = datadir.resolve_db_path(proj)  # opt-in overrides per-project
                self.assertTrue(db.startswith(os.path.join(central, "projects")))
            with env(MRTOKEN_DB="/tmp/x/y.db"):
                self.assertEqual(datadir.resolve_db_path(proj), "/tmp/x/y.db")

    def test_datadir_project_key_matches_sha256_contract(self):
        from mrtoken import datadir
        import hashlib
        p = "/Users/zach/My Proj"
        expected = "my-proj-" + hashlib.sha256(p.encode()).hexdigest()[:8]
        self.assertEqual(datadir.project_key(p), expected)


def make_trace() -> tuple[sqlite3.Connection, int]:
    conn = connect(":memory:")
    cur = conn.execute(
        "INSERT INTO trace(session_id, ingested_at) VALUES(?,?)",
        ("session-1", "2026-06-01T00:00:00Z"),
    )
    return conn, cur.lastrowid


if __name__ == "__main__":
    unittest.main()
