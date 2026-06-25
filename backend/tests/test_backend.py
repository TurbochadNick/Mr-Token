import json
import os
import sqlite3
import tempfile
import unittest

from mrtoken.ingest import connect, default_db_path, ingest_file, load_prices
from mrtoken.rules import rule_huge_tool_output, rule_retry_loop


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class BackendTest(unittest.TestCase):
    def setUp(self):
        # window-inference tests must be deterministic regardless of any machine
        # override (MRTOKEN_CONTEXT_MAX env or ~/.mrtoken/config.json)
        import mrtoken.statusline as _sl
        self._saved_env = os.environ.pop("MRTOKEN_CONTEXT_MAX", None)
        self._saved_cfg = _sl._config_context_max
        _sl._config_context_max = lambda: None

    def tearDown(self):
        import mrtoken.statusline as _sl
        _sl._config_context_max = self._saved_cfg
        if self._saved_env is not None:
            os.environ["MRTOKEN_CONTEXT_MAX"] = self._saved_env

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
        from mrtoken.ingest import connect, load_prices
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
            analyse(conn, tid)  # rule engine runs on codex data without error
            # a Claude transcript must NOT sniff as codex (Claude path unaffected)
            claude = os.path.join(tmp, "claude.jsonl")
            write_jsonl(claude, [{"type": "assistant", "sessionId": "s",
                                  "message": {"id": "m", "usage": {"input_tokens": 1}}}])
            self.assertFalse(_is_codex_transcript(claude))

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
                     "total_tokens": 5200}}}},
                {"timestamp": "2026-06-24T00:00:03Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {"last_token_usage": {
                     "input_tokens": 6000, "cached_input_tokens": 5000, "output_tokens": 150,
                     "total_tokens": 6150}}}},
            ])
            db = os.path.join(tmp, "codex.db")
            on_stop.PROJECTS = os.path.join(tmp, "no-claude")  # no Claude transcript match
            on_stop.CODEX_DIRS = (os.path.join(tmp, "codex"),)
            # Codex branch writes to MRTOKEN_DB (overrides the central Codex DB);
            # point it at the temp DB so the test doesn't touch the real central store.
            orig_stdin, saved = _sys.stdin, os.environ.get("MRTOKEN_DB")
            os.environ["MRTOKEN_DB"] = db
            _sys.stdin = io.StringIO(json.dumps({"session_id": sid, "cwd": "/proj"}))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
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
            src = sqlite3.connect(db).execute(
                "SELECT source FROM trace WHERE session_id=?", (sid,)).fetchone()
            self.assertIsNotNone(src)
            self.assertEqual(src[0], "codex")  # routed to the Codex adapter

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
            n = sqlite3.connect(db).execute(
                "SELECT COUNT(*) FROM trace WHERE session_id=?", (sid,)).fetchone()[0]
            self.assertEqual(n, 1)  # and a trace landed in the cwd-resolved DB

    def test_explain_and_feedback_loop(self):
        # ROADMAP 5D.1 + 5D.2 — explain a fired signal's evidence; capture a verdict
        # and summarise labelled precision.
        from mrtoken.ingest import connect, ingest_file, load_prices
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
            p = os.path.join(tmp, "f.txt"); open(p, "w").write("a\nb\nc\n")
            rp = offload_content(path=p, stash_dir=tmp)
            self.assertEqual(rp["lines"], 3)

    def test_mcp_server_lists_and_calls_offload(self):
        # ROADMAP 6.1: the MCP server exposes + dispatches the toolbox (both agents
        # speak MCP, so this equips Claude and Codex from one server).
        import mrtoken.offload as offmod
        from mrtoken import mcp_server
        with tempfile.TemporaryDirectory() as tmp:
            orig = offmod.central_default
            offmod.central_default = lambda: tmp   # keep stash out of the real central store
            try:
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

    def test_manual_skill_installs_to_both_agents(self):
        # ROADMAP 6.3: the context-efficiency manual is a bundled skill, installed to
        # BOTH ~/.claude/skills and ~/.codex/skills (when Codex is present).
        from mrtoken.install import init, SKILLS_SRC
        self.assertTrue(os.path.isfile(os.path.join(SKILLS_SRC, "mr-context", "SKILL.md")))
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "package.json"), "w").write("{}")
            gpath = os.path.join(tmp, "global-settings.json")
            os.makedirs(os.path.join(tmp, ".codex"))            # Codex present
            codex_skills = os.path.join(tmp, ".codex", "skills")
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=codex_skills, emit=lambda *_: None)
            claude_skills = os.path.join(tmp, "skills")          # next to global-settings.json
            self.assertTrue(os.path.isfile(os.path.join(claude_skills, "mr-context", "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(codex_skills, "mr-context", "SKILL.md")))

    def test_toolbox_handoff_compact_and_toggle(self):
        # ROADMAP 6.2: handoff (real) + compact (advisory) tools, each toggleable.
        from mrtoken import toolbox
        self.assertEqual(set(toolbox.TOOL_REGISTRY), {"offload", "handoff", "compact"})

        orig_h = toolbox.build_handoff
        toolbox.build_handoff = lambda db, s: "# Handoff (stub)"
        try:
            txt, err = toolbox.call_tool("handoff", {"session": "x"})
            self.assertFalse(err)
            self.assertIn("Handoff", txt)
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
        from mrtoken.ingest import connect, ingest_file, load_prices
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

    def test_uninstall_reverses_init_preserving_other_settings(self):
        from mrtoken.install import init, uninstall, _load_settings, _already_installed
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
            init(project_root=tmp, global_settings_path=gpath,
                 codex_skills_root=os.path.join(tmp, "nocodex", "skills"), emit=lambda *_: None)
            skills = os.path.join(os.path.dirname(gpath), "skills")
            self.assertTrue(_already_installed(_load_settings(gpath)))     # Stop hook is global now
            self.assertTrue(os.path.exists(os.path.join(skills, "mr-handoff", "SKILL.md")))

            uninstall(project_root=tmp, settings_path=settings_path,
                      global_settings_path=gpath, emit=lambda *_: None)
            s, g = _load_settings(settings_path), _load_settings(gpath)
            self.assertFalse(_already_installed(g))                       # our global Stop hook gone
            cmds = [hh["command"] for e in s.get("hooks", {}).get("Stop", []) for hh in e["hooks"]]
            self.assertIn("echo keepme", cmds)                            # user's hook preserved
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])   # other settings preserved
            self.assertNotIn("statusLine", g)                            # global HUD gone
            self.assertFalse(g.get("hooks", {}).get("UserPromptSubmit"))  # global hook gone
            self.assertFalse(os.path.exists(os.path.join(skills, "mr-handoff")))  # skill removed

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

    def test_ingest_dedupes_usage_per_message_id_and_prices_opus(self):
        from mrtoken.ingest import connect, ingest_file, load_prices
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

    def test_low_activity_floor_drops_empty_and_hides_substubs(self):
        # The global Stop hook fires on every trivial desktop session. A
        # zero-model-call transcript must NOT be persisted; a sub-floor one (< 2
        # model calls) is kept but flagged low-activity and excluded from counts.
        from mrtoken.ingest import connect, ingest_file, load_prices, MIN_ACTIVITY
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
        from mrtoken.ingest import connect, ingest_file, load_prices
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

    def test_roi_measure_projection_and_cohort(self):
        # fresh_handoff before/after (ROADMAP 2.1): a long, escalating session with
        # a fresh_handoff rec yields a non-negative projected saving and a cohort.
        from mrtoken.ingest import connect, ingest_file, load_prices
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
            self.assertEqual(m["cohort"]["ignored"]["n"], 1)  # 12 calls past midpoint ≥ horizon
            with contextlib.redirect_stdout(io.StringIO()):
                print_roi_measure(conn, horizon=10)

    def test_fleet_counts_codex_sessions(self):
        # fleet must count Codex sessions (source='codex'), not just claude_code.
        from mrtoken.ingest import connect
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
        from mrtoken.ingest import main as ingest_main, connect
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
            self.assertEqual(connect(codex_db).execute(
                "SELECT source FROM trace WHERE session_id='cxbf'").fetchone()[0], "codex")
            self.assertIsNone(connect(db).execute(
                "SELECT 1 FROM trace WHERE session_id='cxbf'").fetchone())

    def test_export_since_filter_and_session_detail(self):
        # ROADMAP backlog: --since (incremental refresh) + session_detail timeline.
        from mrtoken.ingest import connect, ingest_file, load_prices
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
        from mrtoken.ingest import connect, ingest_file, load_prices
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
            self.assertIn("Build the CRM engine", md)          # title wins the Goal
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
