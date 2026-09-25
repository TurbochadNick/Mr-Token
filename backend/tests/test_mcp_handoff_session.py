"""The MCP `handoff` tool renders the resolved session, exactly, with no newest fallback.

`toolbox._handoff_call` resolved a project-local transcript PATH and passed it to
`build_handoff` as its session id. build_handoff selects the database row first, and
`session_id LIKE '<path>%'` never matches, so the tool always answered "session
unavailable" once a transcript existed. It now passes the transcript's session id (matched
exactly) and the already-verified transcript path. An omitted `session` is the caller's own
session from the environment, resolved project-locally; with none, it refuses. It never
falls back to the newest transcript, which on a shared project can be another seat's.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken import toolbox, watch  # noqa: E402
from mrtoken.ingest import connect  # noqa: E402

SID = "aaaaaaaa-1111-4111-8111-000000000001"
OTHER = "bbbbbbbb-2222-4222-8222-000000000002"     # another seat, same project, NEWEST


def transcript(bucket_dir, sid, cwd, prompt):
    os.makedirs(bucket_dir, exist_ok=True)
    p = os.path.join(bucket_dir, f"{sid}.jsonl")
    with open(p, "w") as fh:
        fh.write(json.dumps({"type": "user", "cwd": cwd, "message": {"content": prompt}}) + "\n")
    return p


class McpHandoffSessionTest(unittest.TestCase):
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
        bucket = os.path.join(self.projects, self.work.replace("/", "-").replace(".", "-")
                              .replace("_", "-"))
        transcript(bucket, SID, self.work, "request from seat A")
        later = transcript(bucket, OTHER, self.work, "request from seat B")
        os.utime(later, (2e9, 2e9))                    # seat B's transcript is the newest
        self.db = os.path.join(self.tmp, "store.db")
        c = connect(self.db)
        for sid, started, calls in ((SID, "2026-09-25T10:00:00Z", 1),
                                    (SID + "-later", "2026-09-25T11:00:00Z", 3),
                                    (OTHER, "2026-09-25T12:00:00Z", 5)):
            tid = c.execute("INSERT INTO trace(source,session_id,started_at,ended_at,ingested_at) "
                            "VALUES('claude_code',?,?,?,?)", (sid, started, started, started)).lastrowid
            for _ in range(calls):
                c.execute("INSERT INTO model_call(trace_id,model,input_tokens,output_tokens) "
                          "VALUES(?,?,?,?)", (tid, "test-model", 2, 1))
        c.commit()
        c.close()
        env = {k: v for k, v in os.environ.items()
               if k not in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID", "MRTOKEN_ALLOW_CROSS_PROJECT")}
        env["HOME"] = self.tmp
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch("mrtoken.handoff.default_db_path", return_value=self.db)):
            p.start()
            self.addCleanup(p.stop)

    def call(self, args):
        txt, err = toolbox.call_tool("handoff", args)
        self.assertFalse(err)
        return txt

    def test_explicit_session_renders_that_session_exactly(self):
        txt = self.call({"session": SID})
        self.assertIn("# Handoff", txt)
        self.assertIn(f"Session {SID[:8]}", txt)
        self.assertIn("1 model calls", txt)                # not the newer SID-later row (3)
        self.assertIn("request from seat A", txt)          # the verified transcript was read
        self.assertNotIn("seat B", txt)

    def test_omitted_session_is_the_callers_env_session(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SID}):
            txt = self.call({})
        self.assertIn("# Handoff", txt)
        self.assertIn("1 model calls", txt)
        self.assertIn("request from seat A", txt)
        self.assertNotIn("seat B", txt)

    def test_omitted_session_without_caller_identity_refuses_not_newest(self):
        txt = self.call({})
        self.assertNotIn("# Handoff", txt)
        self.assertNotIn("seat B", txt)
        self.assertIn("caller's own session cannot be determined", txt)

    # Positive control: the untrusted entry point still refuses a foreign or unknown id.
    def test_unknown_id_is_still_rejected_before_dispatch(self):
        txt = self.call({"session": "no-such-session"})
        self.assertIn("no transcript in THIS project", txt)
        self.assertNotIn("# Handoff", txt)


if __name__ == "__main__":
    unittest.main()
