"""`offload-roi` session failures follow the session contract, not a traceback.

SESSION-SELECTION.md: store unavailable exits 2, session unavailable exits 1. A missing
or ambiguous arm used to escape as an uncaught ValueError.
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


class OffloadRoiSessionErrorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {"HOME": self.tmp})
        patcher.start()
        self.addCleanup(patcher.stop)

    def store(self, *sids):
        db = os.path.join(self.tmp, f"s{len(os.listdir(self.tmp))}.db")
        c = connect(db)
        for sid in sids:
            c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                      "VALUES('codex',?,'2026-09-24','2026-09-24','2026-09-24')", (sid,))
        c.commit()
        c.close()
        return db

    def run_cli(self, *args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                cli.main(["offload-roi", *args])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_empty_store_is_session_unavailable_exit_1(self):
        code, out = self.run_cli("a", "b", "--db", self.store())
        self.assertEqual(code, 1, out)
        self.assertIn("mrtoken: session unavailable", out)
        self.assertIn("'a'", out)

    def test_missing_follow_arm_names_that_arm(self):
        code, out = self.run_cli("ign-1", "nope", "--db", self.store("ign-1"))
        self.assertEqual(code, 1, out)
        self.assertIn("mrtoken: session unavailable", out)
        self.assertIn("'nope'", out)

    def test_ambiguous_prefix_is_session_unavailable_exit_1(self):
        code, out = self.run_cli("abc", "abc-1", "--db", self.store("abc-1", "abc-2"))
        self.assertEqual(code, 1, out)
        self.assertIn("mrtoken: session unavailable", out)
        self.assertIn("ambiguous", out)

    # Positive controls: the store axis still exits 2, and a valid pair still renders.
    def test_missing_store_is_store_unavailable_exit_2(self):
        code, out = self.run_cli("a", "b", "--db", os.path.join(self.tmp, "missing.db"))
        self.assertEqual(code, 2, out)
        self.assertIn("mrtoken: store unavailable", out)

    def test_valid_pair_still_renders(self):
        code, out = self.run_cli("ign-1", "fol-1", "--db", self.store("ign-1", "fol-1"))
        self.assertEqual(code, 0, out)
        self.assertNotIn("session unavailable", out)


if __name__ == "__main__":
    unittest.main()
