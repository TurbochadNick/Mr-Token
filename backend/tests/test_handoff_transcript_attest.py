"""A caller-supplied `transcript_path` must ATTEST to the selected session before any read.

Review of 95af706: build_handoff(db, A, exact=True, transcript_path=<B's file>) labelled the
output session A while rendering session B's transcript. The path is now accepted only if
its name AND its symlink-resolved file are `<selected sid>.jsonl`, and the resolved file
lies directly in this project's transcript directory; otherwise session unavailable, and
nothing is read.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken import handoff, toolbox, watch  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

A = "aaaaaaaa-1111-4111-8111-000000000001"
B = "bbbbbbbb-2222-4222-8222-000000000002"
C = "cccccccc-3333-4333-8333-000000000003"     # recorded, but its "transcript" is a symlink


def transcript(path, cwd, prompt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(json.dumps({"type": "user", "cwd": cwd, "message": {"content": prompt}}) + "\n")
    return path


class TranscriptAttestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        self.work = os.path.realpath(os.path.join(self.tmp, "work"))
        os.makedirs(self.work)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        os.chdir(self.work)
        self.addCleanup(os.chdir, self._cwd)
        self.addCleanup(setattr, watch, "PROJECTS", self._orig)
        self.bucket = os.path.join(self.projects, self.work.replace("/", "-").replace(".", "-")
                                   .replace("_", "-"))
        self.a = transcript(os.path.join(self.bucket, f"{A}.jsonl"), self.work, "request from seat A")
        self.b = transcript(os.path.join(self.bucket, f"{B}.jsonl"), self.work, "request from seat B")
        self.db = os.path.join(self.tmp, "store.db")
        c = connect(self.db)
        for sid in (A, B, C):
            c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                      "VALUES('claude_code',?,'2026-09-25','x','x')", (sid,))
        c.commit()
        c.close()
        env = {k: v for k, v in os.environ.items()
               if k not in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID")}
        env["HOME"] = self.tmp
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch("mrtoken.handoff.default_db_path", return_value=self.db)):
            p.start()
            self.addCleanup(p.stop)
        # Record the INODE of every transcript actually read: the read may be from an open
        # file rather than a path, and an inode is what identifies the content read.
        self.reads = []
        real_scan = handoff._scan_transcript

        def recording_scan(src):
            self.reads.append(os.stat(src).st_ino if isinstance(src, str)
                              else os.fstat(src.fileno()).st_ino)
            return real_scan(src)
        s = mock.patch.object(handoff, "_scan_transcript", side_effect=recording_scan)
        s.start()
        self.addCleanup(s.stop)

    def build(self, sid, path):
        return handoff.build_handoff(self.db, sid, exact=True, transcript_path=path)

    def assert_refused(self, out):
        self.assertTrue(out.startswith("mrtoken: session unavailable"), out)
        self.assertNotIn("seat B", out)
        self.assertEqual(self.reads, [], "a transcript was read before the refusal")

    def test_mismatched_path_refuses_and_reads_nothing(self):
        self.assert_refused(self.build(A, self.b))

    def test_symlink_named_for_the_session_pointing_elsewhere_refuses(self):
        link = os.path.join(self.bucket, f"{C}.jsonl")
        os.symlink(self.b, link)
        self.assert_refused(self.build(C, link))
        # ...and through the MCP tool, which resolves C's "transcript" project-locally
        txt, err = toolbox.call_tool("handoff", {"session": C})
        self.assertFalse(err, txt)
        self.assertIn("session unavailable", txt)       # reached build_handoff, then refused
        self.assertNotIn("seat B", txt)
        self.assertNotIn("# Handoff", txt)
        self.assertEqual(self.reads, [])

    def test_correctly_named_file_outside_the_project_directory_refuses(self):
        outside = transcript(os.path.join(self.tmp, "elsewhere", f"{A}.jsonl"), self.work,
                             "request from seat B")
        self.assert_refused(self.build(A, outside))

    # Positive controls: the matching path renders, directly and through the MCP tool.
    def test_matching_path_renders(self):
        out = self.build(A, self.a)
        self.assertIn("# Handoff", out)
        self.assertIn("request from seat A", out)
        self.assertEqual(self.reads, [os.stat(self.a).st_ino])
        txt, err = toolbox.call_tool("handoff", {"session": A})
        self.assertFalse(err, txt)
        self.assertIn("request from seat A", txt)

    def test_file_swapped_between_validation_and_read_is_not_read(self):
        """Deterministic race: right after the transcript is attested, B's file is renamed
        over A's name. The read must be of what was attested (A), never of B."""
        a_inode = os.stat(self.a).st_ino
        hook = ("_open_attested_transcript" if hasattr(handoff, "_open_attested_transcript")
                else "_attested_transcript")
        real = getattr(handoff, hook)

        def attest_then_swap(path, sid):
            result = real(path, sid)
            os.replace(self.b, self.a)                # B's content now sits at A's name
            return result
        with mock.patch.object(handoff, hook, side_effect=attest_then_swap):
            out = self.build(A, self.a)
        self.assertNotIn("seat B", out)
        if out.startswith("mrtoken: session unavailable"):
            self.assertEqual(self.reads, [])
        else:
            self.assertIn("request from seat A", out)
            self.assertEqual(self.reads, [a_inode])

    # ---- review of 858245e: staleness from the OPENED inode; OSError at read or close is
    # ---- session unavailable; file, dir fd and DB connection closed on every refusal.

    def _swap_hook(self):
        return ("_open_attested_transcript" if hasattr(handoff, "_open_attested_transcript")
                else "_attested_transcript")

    def test_stale_warning_comes_from_the_opened_inode_not_the_swapped_name(self):
        import time
        from mrtoken.manifest import declare_manifest
        declare_manifest(A, {"objective": "declared objective"})
        now = time.time()
        os.utime(self.a, (now + 7200, now + 7200))   # A written 2h AFTER the declaration
        os.utime(self.b, (now - 7200, now - 7200))   # B's name-level mtime would hide it
        real = getattr(handoff, self._swap_hook())

        def open_then_swap(*a, **k):
            result = real(*a, **k)
            os.replace(self.b, self.a)
            return result
        with mock.patch.object(handoff, self._swap_hook(), side_effect=open_then_swap):
            out = self.build(A, self.a)
        self.assertIn("request from seat A", out)
        self.assertNotIn("seat B", out)
        self.assertIn("STALE manifest", out)

    def test_positive_control_fresh_manifest_is_not_stale(self):
        from mrtoken.manifest import declare_manifest
        declare_manifest(A, {"objective": "declared objective"})
        out = self.build(A, self.a)
        self.assertIn("request from seat A", out)
        self.assertNotIn("STALE manifest", out)

    def _open_fds(self):
        return set(os.listdir("/dev/fd"))

    def _refusal_with_resources_closed(self, **patches):
        conns = []
        real_connect = handoff.connect_readonly

        def recording_connect(*a, **k):
            c = real_connect(*a, **k)
            conns.append(c)
            return c
        before = self._open_fds()
        with mock.patch.object(handoff, "connect_readonly", side_effect=recording_connect):
            ctx = [mock.patch(t, **kw) for t, kw in patches.items()]
            for c in ctx:
                c.start()
            try:
                out = self.build(A, self.a)
            finally:
                for c in ctx:
                    c.stop()
        self.assertTrue(out.startswith("mrtoken: session unavailable"), out)
        self.assertNotIn("# Handoff", out)
        self.assertEqual(self._open_fds() - before, set(), "a file or dir fd was left open")
        self.assertEqual(len(conns), 1)
        with self.assertRaises(Exception):          # a closed sqlite3 connection refuses use
            conns[0].execute("SELECT 1")
        return out

    def test_oserror_while_reading_is_session_unavailable(self):
        def failing_scan(src):
            raise OSError(5, "Input/output error")
        self._refusal_with_resources_closed(
            **{"mrtoken.handoff._scan_transcript": {"side_effect": failing_scan}})

    def test_oserror_on_close_is_session_unavailable(self):
        real_close = os.close
        calls = []

        def failing_close(fd):
            calls.append(fd)
            real_close(fd)                          # really close it, then report failure
            raise OSError(9, "Bad file descriptor")
        self._refusal_with_resources_closed(**{"os.close": {"side_effect": failing_close}})
        self.assertTrue(calls, "os.close was never called on the attested path")

    def test_every_attestation_refusal_closes_the_db(self):
        link = os.path.join(self.bucket, f"{C}.jsonl")
        os.symlink(self.b, link)
        for sid, path in ((A, self.b), (C, link),
                          (A, os.path.join(self.tmp, "elsewhere", f"{A}.jsonl"))):
            with self.subTest(sid=sid, path=path):
                conns = []
                real_connect = handoff.connect_readonly
                before = self._open_fds()
                with mock.patch.object(handoff, "connect_readonly",
                                       side_effect=lambda *a, **k: conns.append(
                                           real_connect(*a, **k)) or conns[-1]):
                    out = self.build(sid, path)
                self.assertTrue(out.startswith("mrtoken: session unavailable"), out)
                self.assertEqual(self._open_fds() - before, set())
                with self.assertRaises(Exception):
                    conns[0].execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
