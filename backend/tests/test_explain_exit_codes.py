"""`explain` follows the session contract's exit codes (SESSION-SELECTION.md).

A present store without the requested session exits 1. `print_explain` caught the
selection error, printed it and RETURNED, so `explain` exited 0 on "session unavailable".
Masked while the rules engine is off (explain is refused, exit 3), so tested with it on.
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


class ExplainExitCodesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "store.db")
        c = connect(self.db)
        c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                  "VALUES('claude_code','s-1','2026-09-25','2026-09-25','2026-09-25')")
        c.commit()
        c.close()
        for p in (mock.patch.dict(os.environ, {"HOME": self.tmp}),
                  mock.patch.object(rules, "RULES_ENABLED", True)):
            p.start()
            self.addCleanup(p.stop)

    def run_cli(self, *args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                cli.main(["explain", *args, "--db", self.db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_unavailable_session_exits_1(self):
        code, out = self.run_cli("no-such")
        self.assertEqual(code, 1, out)
        self.assertIn("mrtoken: session unavailable", out)

    # Positive controls: a recorded session still renders (exit 0); a missing store is exit 2.
    def test_recorded_session_exits_0(self):
        code, out = self.run_cli("s-1")
        self.assertEqual(code, 0, out)
        self.assertIn("selected: s-1", out)

    def test_missing_store_exits_2(self):
        self.db = os.path.join(self.tmp, "missing.db")
        code, out = self.run_cli("s-1")
        self.assertEqual(code, 2, out)
        self.assertIn("mrtoken: store unavailable", out)


if __name__ == "__main__":
    unittest.main()
