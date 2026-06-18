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
                 emit=lambda *_: None)
            s = _load_settings(settings_path)
            # existing setting + existing hook preserved, ours added
            self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])
            cmds = [hh["command"] for e in s["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertIn("echo existing", cmds)
            self.assertTrue(any("on_stop.py" in c for c in cmds))
            self.assertTrue(os.path.exists(os.path.join(tmp, ".token-tithe", "token-tithe.db")))
            # the /mr-handoff skill is installed GLOBALLY (next to global settings),
            # so /mr-* works in every project, not just where init ran
            global_skills = os.path.join(os.path.dirname(global_settings_path), "skills")
            self.assertTrue(os.path.exists(
                os.path.join(global_skills, "mr-handoff", "SKILL.md")))
            self.assertFalse(os.path.exists(
                os.path.join(tmp, ".claude", "skills", "mr-handoff")))  # no longer project-local
            # per-turn HUD hook + statusLine added to global settings
            gs = _load_settings(global_settings_path)
            self.assertTrue(_prompt_hook_already_installed(gs))
            self.assertEqual(gs["statusLine"]["type"], "command")  # object form, not bare string
            self.assertIn("statusline", gs["statusLine"]["command"])

            # idempotent: second run adds nothing extra
            init(project_root=tmp, global_settings_path=global_settings_path,
                 emit=lambda *_: None)
            s2 = _load_settings(settings_path)
            cmds2 = [hh["command"] for e in s2["hooks"]["Stop"] for hh in e["hooks"]]
            self.assertEqual(len(cmds2), len(cmds))
            self.assertTrue(_already_installed(s2))
            gs2 = _load_settings(global_settings_path)
            ups2 = gs2.get("hooks", {}).get("UserPromptSubmit", [])
            self.assertEqual(len(ups2), 1)  # idempotent — not added twice

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
            init(project_root=tmp, global_settings_path=gpath, emit=lambda *_: None)
            skills = os.path.join(os.path.dirname(gpath), "skills")
            self.assertTrue(_already_installed(_load_settings(settings_path)))
            self.assertTrue(os.path.exists(os.path.join(skills, "mr-handoff", "SKILL.md")))

            uninstall(project_root=tmp, global_settings_path=gpath, emit=lambda *_: None)
            s, g = _load_settings(settings_path), _load_settings(gpath)
            self.assertFalse(_already_installed(s))                       # our Stop hook gone
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
            init(project_root=tmp, global_settings_path=gpath, emit=out.append)
            joined = "\n".join(out)
            self.assertIn("replacing your existing statusLine", joined)
            gs = _load_settings(gpath)
            self.assertIn("statusline", gs["statusLine"]["command"])  # ours installed
            # and a backup of the old settings exists to restore from
            self.assertTrue(any(f.startswith("global-settings.json.mrtoken-bak")
                                for f in os.listdir(tmp)))

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
