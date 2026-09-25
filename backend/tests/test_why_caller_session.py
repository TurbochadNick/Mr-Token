"""`why` and `explain` with an omitted id select the CALLER's own session, never the newest.

Same rule as `handoff` (SESSION-SELECTION.md): one project store is shared by every seat
under that project root, so "newest row" can be another seat's session, and `why` would
then show that seat's id, tokens, cost and tool names. Omitted id means MRTOKEN_SESSION,
else CLAUDE_CODE_SESSION_ID, matched exactly; with neither, refuse with exit 3.
`explain` is refused while the rules engine is off, so it is tested with the engine on.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mrtoken.rules as rules  # noqa: E402
from mrtoken import cli  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

SEAT_A = "aaaaaaaa-1111-4111-8111-000000000001"   # the caller, older
SEAT_B = "bbbbbbbb-2222-4222-8222-000000000002"   # another seat, NEWEST row


class WhyCallerSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "shared.db")
        c = connect(self.db)
        for sid, started in ((SEAT_A, "2026-09-24T10:00:00Z"), (SEAT_B, "2026-09-24T11:00:00Z")):
            tid = c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                            "VALUES('claude_code',?,?,?,?)", (sid, started, started, started)).lastrowid
            c.execute("INSERT INTO model_call(trace_id,model,input_tokens,output_tokens) "
                      "VALUES(?,?,?,?)", (tid, "test-model", 2, 1))
        c.commit()
        c.close()
        env = {k: v for k, v in os.environ.items()
               if k not in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
        env["HOME"] = self.tmp
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        rules_on = mock.patch.object(rules, "RULES_ENABLED", True)
        rules_on.start()
        self.addCleanup(rules_on.stop)

    def run_cli(self, *args, env=None):
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}):
            try:
                with contextlib.redirect_stdout(out):
                    cli.main([*args, "--db", self.db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_omitted_id_selects_the_callers_session_not_the_newest(self):
        for cmd, marker in (("why", f"why is {SEAT_A[:8]}"), ("explain", f"selected: {SEAT_A[:8]}")):
            with self.subTest(cmd=cmd):
                code, out = self.run_cli(cmd, env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
                self.assertEqual(code, 0, out)
                self.assertIn(marker, out)
                self.assertIn("implicit caller session", out)
                self.assertNotIn(SEAT_B[:8], out)

    def test_mrtoken_session_overrides_the_provider_env(self):
        code, out = self.run_cli("why", env={"MRTOKEN_SESSION": SEAT_A,
                                             "CLAUDE_CODE_SESSION_ID": "cccccccc-none"})
        self.assertEqual(code, 0, out)
        self.assertIn(f"why is {SEAT_A[:8]}", out)

    def test_unknowable_caller_refuses_with_exit_3(self):
        for cmd in ("why", "explain"):
            with self.subTest(cmd=cmd):
                code, out = self.run_cli(cmd)
                self.assertEqual(code, 3, out)
                self.assertIn(f"mrtoken: {cmd} refused", out)
                self.assertIn("explicit", out)
                self.assertNotIn(SEAT_B[:8], out)

    def test_caller_session_absent_or_prefix_is_unavailable_not_newest(self):
        for caller in ("dddddddd-not-recorded", SEAT_B[:4]):
            with self.subTest(caller=caller):
                code, out = self.run_cli("why", env={"CLAUDE_CODE_SESSION_ID": caller})
                self.assertEqual(code, 1, out)
                self.assertIn("mrtoken: session unavailable", out)
                self.assertNotIn(SEAT_B[:8], out)

    # Positive controls: explicit ids are deliberate and keep working, including another seat's.
    def test_explicit_ids_still_select(self):
        for sid in (SEAT_A, SEAT_B):
            with self.subTest(sid=sid):
                code, out = self.run_cli("why", sid, env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
                self.assertEqual(code, 0, out)
                self.assertIn(f"why is {sid[:8]}", out)
                self.assertIn("explicit", out)


if __name__ == "__main__":
    unittest.main()
