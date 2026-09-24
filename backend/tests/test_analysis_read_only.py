#!/usr/bin/env python3
"""Analysis commands must never write the store, and must still render a store that
was never through ingest.

Invariant: the main database file is BYTE-IDENTICAL after the command, its LOGICAL
CONTENT (schema and rows, read through a fresh connection) is unchanged, and NO NEW
STORE FILE is created. SQLite may create or modify -wal and -shm sidecars when opening a
WAL database; those are the engine's artifacts of opening, not our writes. The logical
check is what makes that exception safe: a real write committed on a WAL store can sit
in the -wal sidecar with the main file still byte-identical.

Both halves are asserted, because a fix tested only against a missing path looks
correct while silently removing the benefit: a blanket read-only open passes the
missing-path fixture and refuses every store that was never through ingest. Fixture 2
(TypeScript pilot, bare SQLite file, and the real schema.sql from a67f41f with data)
constrains the design, so each of those must RENDER, not just stay unwritten.

test_invariant_check_detects_a_write is the positive control: routed through the
writer opener, the same check must report the mutation.
"""
import contextlib
import hashlib
import io
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mrtoken import cli
from mrtoken.ingest import connect

TS_SCHEMA = os.path.join(HERE, "..", "..", "src", "db", "schema.ts")
OLD_SCHEMA = os.path.join(HERE, "schema_a67f41f.sql")
SIDECARS = ("-wal", "-shm")


def _ts_pilot(path):
    # what the TypeScript `init` leaves: its own schema only, journal_mode=WAL (client.ts)
    with open(TS_SCHEMA, encoding="utf-8") as f:
        schema = re.search(r"schemaSql = `(.*?)`", f.read(), re.S).group(1)
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(schema)
    c.commit()
    c.close()


def _bare(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE _x(a)")
    c.execute("DROP TABLE _x")
    c.commit()
    c.close()


def _old_schema(path):
    with open(OLD_SCHEMA, encoding="utf-8") as f:
        schema = f.read()
    c = sqlite3.connect(path)
    c.executescript(schema)
    c.execute("INSERT INTO trace(source,session_id,ingested_at,started_at) "
              "VALUES('claude_code','s-main','now','2026-06-02')")
    c.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,cache_read_input_tokens,"
              "cache_creation_input_tokens) VALUES(1,1000,200,5000,100)")
    c.commit()
    c.close()


def _healthy(path):
    c = connect(path)
    tid = c.execute("INSERT INTO trace(source,session_id,ingested_at,started_at) "
                    "VALUES('claude_code','s-main','now','2026-09-23')").lastrowid
    c.execute("INSERT INTO model_call(trace_id,input_tokens,output_tokens,cache_read_input_tokens,"
              "cache_creation_input_tokens,est_cost_usd) VALUES(?,?,?,?,?,?)", (tid, 1000, 200, 5000, 100, 0.01))
    c.commit()
    c.close()


FIXTURES = {"missing": None, "ts_pilot": _ts_pilot, "bare": _bare,
            "old_schema": _old_schema, "healthy": _healthy}
WITH_SESSION = ("old_schema", "healthy")

# Every analysis read path that opened read-write before this fix.
SESSIONLESS = [["list"], ["subagents"], ["fleet"], ["export"], ["roi"], ["roi", "--measure"],
               ["validate"], ["explain"], ["feedback", "--summary"]]
SESSION = [["subagents", "s-"], ["export", "s-"], ["export", "--detail", "s-"], ["roi", "s-"],
           ["offload-roi", "s-", "s-"], ["explain", "s-"]]


def snapshot(path):
    """(main file sha256, logical content sha256, header pragmas, store files other than
    WAL sidecars).

    The logical dump is read through a fresh read-only connection, so it sees committed
    content still sitting in a -wal sidecar: on a WAL store a write can leave the main
    file byte-identical until checkpoint, and a file hash alone would miss it.

    user_version and application_id are durable writes that iterdump, the main file (on
    WAL, before checkpoint) and the file set ALL miss at once. Nothing in backend/ writes
    either today; they are guarded because user_version is the conventional home for a
    schema version, and this module guards the migration path that would write it."""
    d, base = os.path.dirname(path), os.path.basename(path)
    files = {f for f in os.listdir(d) if f.startswith(base) and not f.endswith(SIDECARS)}
    if not os.path.exists(path):
        return None, None, None, files
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        logical = hashlib.sha256("\n".join(ro.iterdump()).encode()).hexdigest()
        pragmas = tuple(ro.execute(f"PRAGMA {p}").fetchone()[0] for p in ("user_version", "application_id"))
    finally:
        ro.close()
    return digest, logical, pragmas, files


def run(args, path):
    out, code, crash = io.StringIO(), 0, None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            cli.main(args + ["--db", path])
    except SystemExit as exc:
        code = exc.code or 0
    except Exception as exc:  # recorded, asserted on by the caller
        crash = exc
    return code, out.getvalue(), crash


class AnalysisReadOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items()
               if k not in ("XDG_DATA_HOME", "TOKEN_TITHE_DB", "MRTOKEN_DB", "MRTOKEN_DATA_DIR")}
        env["HOME"] = self.tmp
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def store(self, fixture):
        d = tempfile.mkdtemp(dir=self.tmp)
        path = os.path.join(d, "store.db")
        if FIXTURES[fixture]:
            FIXTURES[fixture](path)
        return path

    def test_analysis_never_writes_the_store(self):
        for fixture in FIXTURES:
            for args in SESSIONLESS + SESSION:
                with self.subTest(fixture=fixture, command=" ".join(args)):
                    path = self.store(fixture)
                    before = snapshot(path)
                    run(args, path)
                    self.assertEqual(snapshot(path), before)

    def test_missing_store_is_refused_not_created(self):
        for args in SESSIONLESS + SESSION:
            with self.subTest(command=" ".join(args)):
                path = self.store("missing")
                code, out, crash = run(args, path)
                self.assertIsNone(crash)
                self.assertEqual(code, 2)
                self.assertIn("store unavailable", out)
                self.assertFalse(os.path.exists(path))

    def test_store_never_through_ingest_still_renders(self):
        for fixture in ("ts_pilot", "bare", "old_schema", "healthy"):
            for args in SESSIONLESS:
                with self.subTest(fixture=fixture, command=" ".join(args)):
                    code, out, crash = run(args, self.store(fixture))
                    self.assertIsNone(crash)
                    self.assertEqual(code, 0)
                    self.assertNotIn("upgrade required", out)

    def test_old_schema_store_renders_its_data(self):
        # sessions exist only in old_schema/healthy; on the others "session unavailable"
        # is the correct answer, so they are covered by the invariant test only
        for fixture in WITH_SESSION:
            for args in SESSION + [["list"], ["fleet"]]:
                with self.subTest(fixture=fixture, command=" ".join(args)):
                    code, out, crash = run(args, self.store(fixture))
                    self.assertIsNone(crash)
                    self.assertEqual(code, 0)
                    if args == ["fleet"]:
                        self.assertRegex(out, r"model calls\s+1\b")
                    else:
                        self.assertIn("s-main", out)

    def test_store_too_large_to_copy_is_refused_unwritten(self):
        import mrtoken.ingest as ingest
        with mock.patch.object(ingest, "ANALYSIS_COPY_LIMIT_BYTES", 1):
            for fixture, expect in (("old_schema", 2), ("healthy", 0)):  # healthy needs no copy
                with self.subTest(fixture=fixture):
                    path = self.store(fixture)
                    before = snapshot(path)
                    code, out, crash = run(["fleet"], path)
                    self.assertIsNone(crash)
                    self.assertEqual(code, expect)
                    if expect:
                        self.assertIn("too large to upgrade in memory", out)
                    self.assertEqual(snapshot(path), before)

    def test_invariant_check_detects_a_pragma_write(self):
        # user_version is a durable write invisible to the main file (WAL, no
        # checkpoint), to iterdump and to the file set, all at once
        for pragma in ("user_version", "application_id"):
            with self.subTest(pragma=pragma):
                path = self.store("ts_pilot")
                before = snapshot(path)
                c = sqlite3.connect(path)
                c.execute("PRAGMA wal_autocheckpoint=0")
                c.execute(f"PRAGMA {pragma} = 42")
                c.commit()
                self.assertNotEqual(snapshot(path), before)
                c.close()

    def test_copy_guard_counts_uncheckpointed_wal(self):
        # on WAL the main file is not the store: content in -wal is copied too
        import mrtoken.ingest as ingest
        path = self.store("ts_pilot")
        writer = sqlite3.connect(path)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.executemany("INSERT INTO events(event_name, session_id, estimated_tokens, raw_json) "
                           "VALUES(?, ?, 0, '{}')", [("PreToolUse", f"s{i}") for i in range(20_000)])
        writer.commit()
        main, wal = os.path.getsize(path), os.path.getsize(path + "-wal")
        self.assertGreater(wal, main)  # precondition: the content really is in -wal
        with mock.patch.object(ingest, "ANALYSIS_COPY_LIMIT_BYTES", main + wal // 2):
            code, out, crash = run(["fleet"], path)
        self.assertIsNone(crash)
        self.assertEqual(code, 2)
        self.assertIn("too large to upgrade in memory", out)

    def test_invariant_check_detects_a_write(self):
        with mock.patch.object(cli, "_open_for_analysis", cli._open):
            # ts_pilot is WAL: the write lands in -wal with the main file unchanged, so
            # this is also the control for the logical-content half of the snapshot
            for fixture in ("healthy", "ts_pilot"):
                with self.subTest(fixture=fixture):
                    path = self.store(fixture)
                    before = snapshot(path)
                    run(["fleet"], path)
                    self.assertNotEqual(snapshot(path), before)
            path = self.store("missing")
            run(["fleet"], path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
