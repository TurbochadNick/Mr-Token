#!/usr/bin/env python3
"""Rebuilding the views must never leave a concurrent reader with NO view.

ingest._ensure_schema runs on every writer open (every Stop-hook ingest). A bare
"DROP VIEW; CREATE VIEW" script under executescript commits the DROP on its own, so a
second connection could find neither session_summary nor session_detail in between:
"no such table" on export --detail, or on the TypeScript UI's direct session_summary
read. Deterministic, not a timing race: a trace callback on the writer fires as each
CREATE VIEW begins, and a second connection checks, at that instant, that the view is
still there. Both journal modes (the TypeScript side sets WAL on the shared store).
"""
import os
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken.ingest import _ensure_schema, connect

VIEWS = ("session_summary", "session_detail")


def visible(conn, name):
    return conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name=?", (name,)).fetchone()[0]


class ViewDdlAtomicTest(unittest.TestCase):
    def store(self, journal):
        path = os.path.join(tempfile.mkdtemp(), "s.db")
        c = connect(path)            # a current store with both views
        c.execute(f"PRAGMA journal_mode={journal}")
        c.close()
        return path

    def test_a_concurrent_reader_never_loses_a_view_during_rebuild(self):
        for journal in ("DELETE", "WAL"):
            with self.subTest(journal=journal):
                path = self.store(journal)
                writer, reader = sqlite3.connect(path), sqlite3.connect(path)
                seen = {}

                def trace(sql):
                    for v in VIEWS:
                        if sql.lstrip().startswith(f"CREATE VIEW {v}"):
                            seen[v] = visible(reader, v)
                writer.set_trace_callback(trace)
                _ensure_schema(writer)
                self.assertEqual(sorted(seen), sorted(VIEWS))       # both rebuilds were observed
                self.assertEqual(seen, {v: 1 for v in VIEWS})       # and neither ever vanished
                for v in VIEWS:                                     # and both exist afterwards
                    self.assertEqual(visible(reader, v), 1)
                    reader.execute(f"SELECT * FROM {v} LIMIT 0")
                writer.close(); reader.close()

    def test_a_failing_rebuild_rolls_back_and_re_raises(self):
        # the second CREATE fails (a syntax error, so it fails at CREATE time in every
        # SQLite); the error must propagate, the transaction must not be left open, and the
        # OLD views must survive on the writer and on another connection
        import mrtoken.ingest as ingest
        broken = "DROP VIEW IF EXISTS session_detail;\nCREATE VIEW session_detail AS SELEC 1;\n"
        for journal in ("DELETE", "WAL"):
            with self.subTest(journal=journal):
                path = self.store(journal)
                writer, reader = sqlite3.connect(path), sqlite3.connect(path)
                with unittest.mock.patch.object(ingest, "_SESSION_DETAIL_VIEW", broken):
                    with self.assertRaises(sqlite3.OperationalError):
                        _ensure_schema(writer)
                self.assertFalse(writer.in_transaction)
                for conn in (writer, reader):
                    for v in VIEWS:
                        self.assertEqual(visible(conn, v), 1, (v, conn is writer))
                writer.commit()                              # a later commit must not lose them
                self.assertEqual({v: visible(reader, v) for v in VIEWS}, {v: 1 for v in VIEWS})
                _ensure_schema(writer)                       # a subsequent valid rebuild works
                for v in VIEWS:
                    reader.execute(f"SELECT * FROM {v} LIMIT 0")
                writer.close(); reader.close()

    def test_positive_control_the_probe_can_see_a_vanished_view(self):
        # an autocommit DROP (what the old script did) IS visible to the second connection,
        # so the assertion above is not passing because the probe is blind
        for journal in ("DELETE", "WAL"):
            with self.subTest(journal=journal):
                path = self.store(journal)
                writer, reader = sqlite3.connect(path), sqlite3.connect(path)
                writer.isolation_level = None                       # autocommit, as executescript
                writer.execute("DROP VIEW session_detail")
                self.assertEqual(visible(reader, "session_detail"), 0)
                writer.close(); reader.close()


if __name__ == "__main__":
    unittest.main()
