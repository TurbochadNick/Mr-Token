"""A WAL store in a directory the reader cannot write is REFUSED as store unavailable.

A WAL-mode reader must create the -shm index next to the store, even to read. With a
non-writable directory, sqlite3.connect() succeeds lazily and the FIRST query fails, which
used to escape as an uncaught OperationalError. The decision (Work PoC, 2026-09-24) is to
refuse with exit 2, not to read with immutable=1: immutable ignores uncheckpointed WAL
content, and a meter showing wrong numbers is worse than a meter that refuses.
"""
import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mrtoken import cli  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402


@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory modes")
class WalReadonlyDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.dict(os.environ, {"HOME": self.tmp})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = os.path.join(self.tmp, "store")
        os.mkdir(self.dir)
        self.db = os.path.join(self.dir, "wal.db")
        c = connect(self.db)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                  "VALUES('claude_code','s-1','2026-09-24','2026-09-24','2026-09-24')")
        c.commit()
        c.close()
        self.assertEqual(os.listdir(self.dir), ["wal.db"])     # no -wal/-shm left behind

    def lock_dir(self):
        os.chmod(self.dir, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, self.dir, stat.S_IRWXU)

    def run_cli(self, *args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out):
            try:
                cli.main([*args, "--db", self.db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_why_and_list_refuse_with_store_unavailable_exit_2(self):
        self.lock_dir()
        for args in (["why"], ["why", "s-1"], ["list"], ["report"]):
            with self.subTest(args=args):
                code, out = self.run_cli(*args)
                self.assertEqual(code, 2, out)
                self.assertIn("mrtoken: store unavailable", out)
                self.assertIn("WAL", out)
        self.assertEqual(os.listdir(self.dir), ["wal.db"])     # nothing created

    # Positive control: the same store in a writable directory still renders.
    def test_writable_directory_still_renders(self):
        for args in (["why", "s-1"], ["list"]):
            with self.subTest(args=args):
                code, out = self.run_cli(*args)
                self.assertEqual(code, 0, out)
                self.assertNotIn("store unavailable", out)


if __name__ == "__main__":
    unittest.main()
