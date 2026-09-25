"""A --db path that is not a SQLite database is "store unavailable" (exit 2), not a traceback.

sqlite3.connect() is lazy, so a non-database file first fails at the first read with
sqlite3.DatabaseError ("file is not a database"), the PARENT of the OperationalError the
first-read guard caught. It used to escape uncaught from why, list, report and handoff.
"""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mrtoken import cli  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

COMMANDS = (["why", "s-1"], ["list"], ["report"], ["handoff", "s-1"])


class NonSqliteStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {"HOME": self.tmp})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, db, args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                cli.main([*args, "--db", db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_non_sqlite_file_is_store_unavailable_exit_2(self):
        bad = os.path.join(self.tmp, "notes.db")
        Path(bad).write_text("this is not a database, just text\n" * 200)
        before = hashlib.sha256(Path(bad).read_bytes()).hexdigest()
        for args in COMMANDS:
            with self.subTest(args=args):
                code, out = self.run_cli(bad, args)
                self.assertEqual(code, 2, out)
                self.assertIn("mrtoken: store unavailable", out)
                self.assertIn("not a database", out)
        self.assertEqual(before, hashlib.sha256(Path(bad).read_bytes()).hexdigest())
        self.assertEqual(sorted(os.listdir(self.tmp)), ["notes.db"])   # no sidecars

    # Positive control: a real store at the same kind of path still renders.
    def test_real_store_still_renders(self):
        good = os.path.join(self.tmp, "good.db")
        c = connect(good)
        c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                  "VALUES('claude_code','s-1','2026-09-25','2026-09-25','2026-09-25')")
        c.commit()
        c.close()
        for args in COMMANDS:
            with self.subTest(args=args):
                code, out = self.run_cli(good, args)
                self.assertEqual(code, 0, out)
                self.assertNotIn("store unavailable", out)


if __name__ == "__main__":
    unittest.main()
