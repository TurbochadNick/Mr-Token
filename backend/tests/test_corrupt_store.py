"""A corrupt store is "store unavailable" (exit 2) wherever the corruption surfaces.

A store with an intact schema but corrupt table pages passes the opener (it reads only
schema pages) and fails later, mid-query, in whichever module first touches a bad page.
CLI dispatch maps a DatabaseError whose PRIMARY SQLite code is SQLITE_CORRUPT (11) or
SQLITE_NOTADB (26) to store unavailable, exit 2. Every other error re-raises unchanged,
so a real code bug (bad SQL is OperationalError, SQLITE_ERROR = 1) keeps its traceback.
"""
import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mrtoken import cli  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

COMMANDS = (["why", "s-1"], ["status", "s-1"], ["handoff", "s-1"], ["list"], ["report"],
            ["fleet"], ["export"], ["roi", "s-1"], ["subagents"])


def build(path):
    c = connect(path)
    for i in range(300):
        tid = c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at,title) "
                        "VALUES('claude_code',?,?,?,?,?)",
                        (f"s-{i}", "2026-09-25", "x", "x", "t" * 200)).lastrowid
        c.execute("INSERT INTO model_call(trace_id,model,input_tokens,output_tokens) "
                  "VALUES(?,?,?,?)", (tid, "m", 2, 1))
    c.commit()
    roots = [r[0] for r in c.execute(
        "SELECT rootpage FROM sqlite_master WHERE type='table' AND name IN ('trace','model_call')")]
    page = c.execute("PRAGMA page_size").fetchone()[0]
    c.close()
    return roots, page


class CorruptStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for p in (mock.patch.dict(os.environ, {"HOME": self.tmp, "MRTOKEN_SESSION": "s-1"}),):
            p.start()
            self.addCleanup(p.stop)
        self.good = os.path.join(self.tmp, "good.db")
        roots, page = build(self.good)
        self.bad = os.path.join(self.tmp, "bad.db")
        with open(self.good, "rb") as src, open(self.bad, "wb") as dst:
            dst.write(src.read())
        with open(self.bad, "r+b") as fh:            # corrupt ONLY the two table root pages
            for root in roots:
                fh.seek((root - 1) * page)
                fh.write(b"\xff" * page)
        # precondition: the schema is still readable, so the opener passes and the failure
        # really is mid-query; and the data pages really are corrupt.
        probe = sqlite3.connect(f"file:{self.bad}?mode=ro", uri=True)
        probe.execute("SELECT name FROM sqlite_master").fetchall()
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            probe.execute("SELECT * FROM trace").fetchall()
        self.assertEqual(ctx.exception.sqlite_errorcode & 0xFF, 11)
        probe.close()

    def run_cli(self, db, args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                cli.main([*args, "--db", db])
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def test_mid_query_corruption_is_store_unavailable_exit_2(self):
        for args in COMMANDS:
            with self.subTest(args=args):
                code, out = self.run_cli(self.bad, args)
                self.assertEqual(code, 2, out)
                self.assertIn("mrtoken: store unavailable", out)
                self.assertIn("malformed", out)

    # Positive controls.
    def test_healthy_store_still_renders(self):
        for args in COMMANDS:
            with self.subTest(args=args):
                code, out = self.run_cli(self.good, args)
                self.assertNotEqual(code, 2, out)
                self.assertNotIn("store unavailable", out)

    def test_a_code_bug_keeps_its_traceback(self):
        def broken(conn, *a, **k):
            conn.execute("SELEC broken sql")            # OperationalError, SQLITE_ERROR (1)
        with mock.patch("mrtoken.fleet.fleet_summary", broken):
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                self.run_cli(self.good, ["fleet"])
        self.assertEqual(ctx.exception.sqlite_errorcode & 0xFF, 1)

    def test_other_database_errors_are_not_relabelled(self):
        def locked(conn, *a, **k):
            err = sqlite3.OperationalError("database is locked")
            err.sqlite_errorcode, err.sqlite_errorname = 5, "SQLITE_BUSY"
            raise err
        with mock.patch("mrtoken.fleet.fleet_summary", locked):
            with self.assertRaises(sqlite3.OperationalError):
                self.run_cli(self.good, ["fleet"])


if __name__ == "__main__":
    unittest.main()
