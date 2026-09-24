"""`handoff` with an omitted id selects the CALLER's own session, never the newest row.

One project store is shared by every seat nested under that project root, so "newest
permitted row" could be another seat's session, and handoff then reads THAT session's
transcript into this seat's context. Omitted id now means the caller's own session
(MRTOKEN_SESSION, else CLAUDE_CODE_SESSION_ID), matched exactly; with neither, handoff
refuses with exit 3. An explicit id is a deliberate choice and still selects any session.
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mrtoken import cli  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

SEAT_A = "aaaaaaaa-1111-4111-8111-000000000001"   # the caller, older
SEAT_B = "bbbbbbbb-2222-4222-8222-000000000002"   # another seat, NEWEST row


class HandoffCallerSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "shared.db")
        c = connect(self.db)
        for sid, started in ((SEAT_A, "2026-09-24T10:00:00Z"), (SEAT_B, "2026-09-24T11:00:00Z")):
            c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                      "VALUES('claude_code',?,?,?,?)", (sid, started, started, started))
        c.commit()
        c.close()
        env = {k: v for k, v in os.environ.items()
               if k not in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
        env["HOME"] = self.tmp            # no real transcript is ever resolvable
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args, env=None):
        out = io.StringIO()
        code = 0
        with mock.patch.dict(os.environ, env or {}):
            try:
                with contextlib.redirect_stdout(out):
                    cli.main(["handoff", *args, "--db", self.db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_omitted_id_selects_the_callers_session_not_the_newest(self):
        code, out = self.run_cli(env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
        self.assertEqual(code, 0, out)
        self.assertIn(f"Session {SEAT_A[:8]}", out)
        self.assertNotIn(SEAT_B[:8], out)
        self.assertIn("implicit caller session", out)

    def test_mrtoken_session_overrides_the_provider_env(self):
        code, out = self.run_cli(env={"MRTOKEN_SESSION": SEAT_A,
                                      "CLAUDE_CODE_SESSION_ID": "cccccccc-none"})
        self.assertEqual(code, 0, out)
        self.assertIn(f"Session {SEAT_A[:8]}", out)

    def test_unknowable_caller_refuses_with_exit_3(self):
        code, out = self.run_cli()
        self.assertEqual(code, 3, out)
        self.assertIn("mrtoken: handoff refused", out)
        self.assertIn("explicit", out)
        self.assertNotIn("# Handoff", out)
        self.assertNotIn(SEAT_B[:8], out)

    def test_caller_session_absent_from_store_is_unavailable_not_newest(self):
        code, out = self.run_cli(env={"CLAUDE_CODE_SESSION_ID": "dddddddd-not-recorded"})
        self.assertEqual(code, 1, out)
        self.assertIn("mrtoken: session unavailable", out)
        self.assertNotIn("# Handoff", out)
        self.assertNotIn(SEAT_B[:8], out)

    def test_caller_session_matches_exactly_not_by_prefix(self):
        code, out = self.run_cli(env={"CLAUDE_CODE_SESSION_ID": SEAT_B[:4]})
        self.assertEqual(code, 1, out)
        self.assertNotIn("# Handoff", out)

    def test_codex_omitted_id_uses_caller_identity_too(self):
        # the caller's Claude id does not name a Codex row: unavailable, never newest Codex
        c = connect(self.db)
        c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                  "VALUES('codex','eeeeeeee-codex','2026-09-24T12:00:00Z','x','x')")
        c.commit()
        c.close()
        with mock.patch("mrtoken.datadir.codex_db_path", return_value=self.db):
            code, out = self.run_cli("--codex", env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
        self.assertEqual(code, 1, out)
        self.assertNotIn("eeeeeeee", out.split("\n", 1)[1])

    # Positive controls: explicit ids are deliberate and keep working, including another seat's.
    def test_explicit_own_id_still_selects(self):
        code, out = self.run_cli(SEAT_A, env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
        self.assertEqual(code, 0, out)
        self.assertIn(f"Session {SEAT_A[:8]}", out)
        self.assertIn("explicit", out)

    def test_explicit_other_session_is_still_allowed(self):
        code, out = self.run_cli(SEAT_B, env={"CLAUDE_CODE_SESSION_ID": SEAT_A})
        self.assertEqual(code, 0, out)
        self.assertIn(f"Session {SEAT_B[:8]}", out)


if __name__ == "__main__":
    unittest.main()
