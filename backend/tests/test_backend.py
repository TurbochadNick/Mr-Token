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
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 200_000,
                      "output_tokens": 50},
            "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}})
        # the tool returns a huge result
        mon.feed({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 60_000}]}})
        joined = "\n".join(out)
        self.assertIn("context window", joined)
        self.assertIn("Read returned", joined)


    def test_init_installs_hook_preserves_and_is_idempotent(self):
        from mrtoken.install import init, _load_settings, _already_installed
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as h:
                h.write("{}")
            settings_dir = os.path.join(tmp, ".claude")
            os.makedirs(settings_dir)
            settings_path = os.path.join(settings_dir, "settings.local.json")
            with open(settings_path, "w") as h:
                json.dump({"permissions": {"allow": ["Bash(ls *)"]},
                           "hooks": {"Stop": [{"matcher": "", "hooks": [
                               {"type": "command", "command": "echo existing"}]}]}}, h)

            init(project_root=tmp, emit=lambda *_: None)
            s = _load_settings(settings_path)
            # existing setting + existing hook preserved, ours added
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])
            cmds = [hh["command"] for e in s["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertIn("echo existing", cmds)
            self.assertTrue(any("on_stop.py" in c for c in cmds))
            self.assertTrue(os.path.exists(os.path.join(tmp, ".token-tithe", "token-tithe.db")))

            # idempotent: second run adds nothing
            init(project_root=tmp, emit=lambda *_: None)
            s2 = _load_settings(settings_path)
            cmds2 = [hh["command"] for e in s2["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertEqual(len(cmds2), len(cmds))
            self.assertTrue(_already_installed(s2))

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


def make_trace() -> tuple[sqlite3.Connection, int]:
    conn = connect(":memory:")
    cur = conn.execute(
        "INSERT INTO trace(session_id, ingested_at) VALUES(?,?)",
        ("session-1", "2026-06-01T00:00:00Z"),
    )
    return conn, cur.lastrowid


if __name__ == "__main__":
    unittest.main()
