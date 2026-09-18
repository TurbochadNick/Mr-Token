#!/usr/bin/env python3
"""Session binding must FAIL CLOSED, and trusted paths must be a DIFFERENT ENTRY POINT
from untrusted ids.

Trust is a property of the entry point, not of how a string is spelled. An earlier attempt
told them apart by filename suffix: that rejected /etc/passwd by SPELLING while still
accepting a `.jsonl` SYMLINK to a private file, and the MCP `handoff` schema says `session`
is an id while `_handoff_call` passed the raw string to `build_handoff` -> `resolve_path`,
which returns any real file. `build_handoff` returns transcript CONTENT, so that was an
exposure path, not a wrong measurement.

Every rejection test below carries a SENTINEL and a precondition, so a test cannot pass
because the fixture never reached the defect.
"""
import json
import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken import watch

SENTINEL = "SENTINEL-VICTIM-CONTENT-DO-NOT-LEAK"


def mk(projects, bucket, session, age_s=0, sentinel=False, cwd=None):
    """A transcript in `bucket`. Records a `cwd` because real transcripts always do, and
    bucket discovery matches on it — a fixture without one is not a realistic transcript."""
    d = os.path.join(projects, bucket)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{session}.jsonl")
    with open(p, "w") as fh:
        fh.write(json.dumps({"type": "user", "cwd": cwd or os.getcwd(),
                             "message": {"content":
                 SENTINEL if sentinel else "ordinary"}}) + "\n")
    if age_s:
        t = time.time() - age_s
        os.utime(p, (t, t))
    return p


class FailClosedBinding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.projects, exist_ok=True)
        os.makedirs(self.work, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        os.chdir(self.work)
        # same formula watch uses; computed inline so setUp works on BOTH arms (a setUp
        # that needs a post-fix symbol turns every pre-fix test into an ERROR and the
        # mutation comparison says nothing).
        self.bucket = os.getcwd().replace("/", "-").replace(".", "-")
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID",
                  "MRTOKEN_ALLOW_CROSS_PROJECT"):
            os.environ.pop(v, None)

    def tearDown(self):
        os.chdir(self._cwd)
        watch.PROJECTS = self._orig
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID",
                  "MRTOKEN_ALLOW_CROSS_PROJECT"):
            os.environ.pop(v, None)

    def _handoff(self, args):
        from mrtoken import toolbox
        txt, _ = toolbox.call_tool("handoff", args)
        return txt

    def _bound_transcript(self, args):
        """WHICH transcript would `handoff` actually read? None if rejected pre-dispatch.

        Asserting on returned CONTENT is vacuous: build_handoff emits a markdown summary
        and need not echo the transcript, so a leak passes a "sentinel absent" check. This
        stubs build_handoff to capture the value it is handed and resolves it the same way
        build_handoff would — testing the BINDING, which is the actual exposure.
        """
        from mrtoken import toolbox
        orig = toolbox.build_handoff
        toolbox.build_handoff = lambda db, s: "BOUND:" + repr(s)
        try:
            txt, _ = toolbox.call_tool("handoff", args)
        finally:
            toolbox.build_handoff = orig
        if not txt.startswith("BOUND:"):
            return None                      # rejected before dispatch
        val = eval(txt[len("BOUND:"):])      # the exact object build_handoff received
        bound = watch.resolve_path(val) if val else None
        # realpath BOTH sides: a relative path and an absolute one can name the same file
        # and compare unequal as strings, which made this assertion pass vacuously.
        return os.path.realpath(bound) if bound else None

    # ---- the untrusted entry point must never accept a PATH -------------------
    def test_handoff_rejects_absolute_jsonl_path(self):
        victim = mk(self.projects, "-seat-b", "victim", sentinel=True, cwd="/foreign/seat-b")
        self.assertTrue(os.path.isfile(victim))                       # precondition
        self.assertEqual(watch.resolve_path(victim), victim)          # precondition: reachable
        self.assertNotEqual(self._bound_transcript({"session": victim}),
                            os.path.realpath(victim),
                            "an absolute .jsonl path bound the victim transcript")

    def test_handoff_rejects_relative_jsonl_path(self):
        victim = mk(self.projects, "-seat-b", "victim", sentinel=True, cwd="/foreign/seat-b")
        rel = os.path.relpath(victim)
        self.assertTrue(os.path.isfile(rel))                          # precondition
        self.assertNotEqual(self._bound_transcript({"session": rel}),
                            os.path.realpath(victim),
                            "a relative .jsonl path bound the victim transcript")

    def test_handoff_rejects_jsonl_symlink_to_non_transcript(self):
        secret = os.path.join(self.tmp, "id_rsa")
        with open(secret, "w") as fh:
            fh.write(SENTINEL + "\n")
        link = os.path.join(self.tmp, "looks-like-a-transcript.jsonl")
        os.symlink(secret, link)
        self.assertTrue(os.path.isfile(link))            # precondition: passes isfile
        self.assertTrue(link.endswith(".jsonl"))         # precondition: passes a SUFFIX check
        self.assertIsNone(self._bound_transcript({"session": link}),
                          "a .jsonl symlink to a private file was bound as a transcript")

    # ---- cross-seat: pass the FOREIGN id itself -------------------------------
    def test_foreign_session_id_is_not_resolved(self):
        foreign = mk(self.projects, "-seat-b", "foreign-session", sentinel=True, cwd="/foreign/seat-b")
        mine = mk(self.projects, self.bucket, "my-session")
        # precondition: the foreign transcript really exists and IS uniquely named
        self.assertTrue(os.path.isfile(foreign))
        # PRIMARY assertion goes through `handoff`, which exists on BOTH arms, so this
        # test is a real mutation test rather than an import error pre-fix.
        self.assertNotEqual(self._bound_transcript({"session": "foreign-session"}),
                            os.path.realpath(foreign),
                            "a foreign seat's session id bound its transcript")
        if hasattr(watch, "resolve_session_local"):
            self.assertIsNone(watch.resolve_session_local("foreign-session"),
                              "a foreign seat's exact session id resolved")
            self.assertEqual(watch.resolve_session_local("my-session"), mine)  # control
        self.assertTrue(os.path.isfile(mine))

    # ---- glob metacharacters are executable syntax ----------------------------
    def test_glob_metacharacters_do_not_match(self):
        mk(self.projects, self.bucket, "real-session")
        # precondition: with one transcript present, an unescaped '*' WOULD have matched it
        self.assertEqual(len(watch.glob.glob(
            os.path.join(self.projects, self.bucket, "*.jsonl"))), 1)
        for probe in ("*", "?", "[a-z]*", "real-sessio?", "*session", "[r]eal-session"):
            # through handoff: present on both arms
            self.assertIn("no transcript in THIS project", self._handoff({"session": probe}),
                          f"glob metacharacter id {probe!r} resolved through handoff")
            if hasattr(watch, "resolve_session_local"):
                self.assertIsNone(watch.resolve_session_local(probe))
                self.assertIsNone(watch.resolve_session(probe))
        # POSITIVE CONTROL: the literal id still resolves
        if hasattr(watch, "resolve_session_local"):
            self.assertIsNotNone(watch.resolve_session_local("real-session"))

    # ---- env id resolves strictly or not at all ------------------------------
    def test_env_id_never_falls_through(self):
        mk(self.projects, self.bucket, "cwd-local")
        # precondition: cwd bucket has a transcript, so a fallthrough WOULD find one
        self.assertTrue(watch.glob.glob(os.path.join(self.projects, self.bucket, "*.jsonl")))
        for bad in ("no-such-id", "*", "?"):
            os.environ["MRTOKEN_SESSION"] = bad
            self.assertIsNone(watch.latest_transcript(),
                              f"env id {bad!r} fell through to another transcript")
        # POSITIVE CONTROL: a good env id resolves
        os.environ["MRTOKEN_SESSION"] = "cwd-local"
        self.assertIsNotNone(watch.latest_transcript())

    # ---- behaviour that survived review --------------------------------------
    def test_prefix_ambiguity_fails_closed(self):
        mk(self.projects, self.bucket, "sess-abc-one", age_s=60)
        newest = mk(self.projects, self.bucket, "sess-abc-two")
        self.assertIsNone(watch.resolve_path("sess-abc"))
        self.assertNotEqual(watch.resolve_path("sess-abc"), newest)

    def test_exact_beats_prefix(self):
        exact = mk(self.projects, self.bucket, "sess")
        mk(self.projects, self.bucket, "sess-longer")
        self.assertEqual(watch.resolve_path("sess"), exact)

    def test_stale_only_candidates_yield_not_found(self):
        from mrtoken import intervene
        mk(self.projects, self.bucket, "stale-one",
           age_s=intervene.AMBIGUOUS_SESSION_WINDOW_S + 300)
        self.assertTrue(intervene._cwd_project_transcripts(), "fixture built no candidates")
        self.assertEqual(intervene._recent_project_transcripts(), [], "fixture not stale")
        sid, calls = intervene._session_calls(None)
        self.assertIsNone(sid)
        self.assertEqual(calls, 0)

    def test_cross_project_last_resort_is_off_by_default(self):
        mk(self.projects, "-seat-b", "somewhere-else", cwd="/foreign/seat-b")
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty, exist_ok=True)
        self.assertIsNone(watch.latest_transcript(cwd=empty))
        os.environ["MRTOKEN_ALLOW_CROSS_PROJECT"] = "1"
        self.assertIsNotNone(watch.latest_transcript(cwd=empty))   # opt-in still works

    # ---- POSITIVE CONTROLS: legitimate resolution must survive ---------------
    def test_trusted_path_entry_point_still_works(self):
        """The PreCompact hook and the CLI hand over a real transcript path."""
        p = mk(self.projects, self.bucket, "hook-session")
        self.assertEqual(watch.resolve_path(p), p)
        outside = os.path.join(self.tmp, "exported.jsonl")
        with open(outside, "w") as fh:
            fh.write('{"type":"user"}\n')
        self.assertEqual(watch.resolve_path(outside), outside,
                         "a transcript exported outside the projects root was rejected")

    def test_valid_local_id_resolves_everywhere(self):
        p = mk(self.projects, self.bucket, "good-session")
        self.assertEqual(watch.resolve_path("good-session"), p)
        if hasattr(watch, "resolve_session_local"):
            self.assertEqual(watch.resolve_session_local("good-session"), p)
        os.environ["MRTOKEN_SESSION"] = "good-session"
        self.assertEqual(watch.resolve_path(None), p)


class ConfirmDisposableWriteBinding(unittest.TestCase):
    """`confirm_disposable` WRITES, so a wrong binding mutates state rather than leaking it.

    `args.get("session")` lost key presence: an explicit "" fell through `_session_calls`'
    `not session_arg` test to the one-recent-session default, and a disposal confirmation
    was persisted against a session the caller never named.

    The load-bearing assertion here is the SECOND one — that no state file was created.
    Asserting only on the returned message would pass even if the write had happened.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.projects, exist_ok=True)
        os.makedirs(self.work, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        os.chdir(self.work)
        self.bucket = os.getcwd().replace("/", "-").replace(".", "-")
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(v, None)
        self.store = os.path.join(self.tmp, "store")
        os.environ["XDG_DATA_HOME"] = self.store          # keep writes off the real store
        self.only = mk(self.projects, self.bucket, "only-recent-session")

    def tearDown(self):
        os.chdir(self._cwd)
        watch.PROJECTS = self._orig
        os.environ.pop("XDG_DATA_HOME", None)

    def _state_files(self):
        d = os.path.join(self.store, "token-tithe", "state")
        return sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []

    def _confirm(self, args):
        from mrtoken import toolbox
        txt, _ = toolbox.call_tool("confirm_disposable", args)
        return txt

    def test_explicit_empty_session_is_rejected_and_writes_nothing(self):
        # precondition: exactly one recent transcript, so the default WOULD bind it
        self.assertEqual(len(watch.glob.glob(
            os.path.join(self.projects, self.bucket, "*.jsonl"))), 1)
        self.assertEqual(self._state_files(), [], "precondition: no state yet")

        out = self._confirm({"session": ""})

        self.assertIn("invalid session id", out, "explicit empty session was not rejected")
        self.assertNotIn("recorded:", out)
        # THE ONE THAT MATTERS — the defect mutates, so absence of state is the real proof
        self.assertEqual(self._state_files(), [],
                         "an invalid explicit session wrote a disposal confirmation")

    def test_absent_key_still_uses_the_single_recent_session(self):
        """CONTROL: omitting `session` legitimately binds the one recent transcript."""
        out = self._confirm({})
        self.assertIn("recorded:", out, "the absent-key default stopped working")
        self.assertTrue(any(f.startswith("disposable-") for f in self._state_files()),
                        "no confirmation state was written for the legitimate path")

    def test_valid_explicit_local_id_binds_itself(self):
        """CONTROL: a valid explicit id records against THAT session."""
        out = self._confirm({"session": "only-recent-session"})
        self.assertIn("recorded:", out)
        self.assertIn("disposable-only-recent-session.json", self._state_files())


def mk_in_bucket(projects, bucket, session, cwd):
    """A transcript in `bucket` that RECORDS `cwd` as its own working directory."""
    d = os.path.join(projects, bucket)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{session}.jsonl")
    with open(p, "w") as fh:
        fh.write(json.dumps({"type": "user", "cwd": cwd,
                             "message": {"content": "hi"}}) + "\n")
    return p


class ProjectBucketDiscovery(unittest.TestCase):
    """The bucket must be DISCOVERED, not computed.

    Claude Code maps '_' to '-' as well as '/' and '.'. The old formula did not, so for any
    underscore path — `mr_token`, the product's own repo — it globbed a directory that does
    not exist and project-local resolution silently returned nothing. A correctly-secured
    resolver that can never resolve is a disablement, not a fix.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(self.projects, exist_ok=True)
        self._orig = watch.PROJECTS
        watch.PROJECTS = self.projects

    def tearDown(self):
        watch.PROJECTS = self._orig

    def test_underscore_project_resolves(self):
        """THE CASE THAT IS BROKEN TODAY."""
        cwd = "/Users/x/Projects/gate-pending/mr_token"
        bucket = "-Users-x-Projects-gate-pending-mr-token"      # harness maps '_' -> '-'
        mk_in_bucket(self.projects, bucket, "sess-a", cwd)
        # precondition: the computed name is NOT the real one, so this is a real test
        computed = cwd.replace("/", "-").replace(".", "-")   # inline: works on BOTH arms
        self.assertNotEqual(computed, bucket)
        self.assertFalse(os.path.isdir(os.path.join(self.projects, computed)))
        self.assertEqual(watch.project_bucket(cwd), bucket)

    def test_hyphen_project_still_resolves(self):
        """REGRESSION GUARD: paths the old formula got right must keep working."""
        cwd = "/Users/x/Projects/gate-pending/crm-engine"
        bucket = "-Users-x-Projects-gate-pending-crm-engine"
        mk_in_bucket(self.projects, bucket, "sess-b", cwd)
        # precondition: here the computed name IS correct, so this guards the fast path
        self.assertEqual(cwd.replace("/", "-").replace(".", "-"), bucket)
        self.assertEqual(watch.project_bucket(cwd), bucket)

    def test_unknown_project_is_not_found_not_a_wrong_bucket(self):
        """Degrade to NOT-FOUND, never to someone else's bucket."""
        mk_in_bucket(self.projects, "-Users-x-Projects-other",
                     "sess-c", "/Users/x/Projects/other")
        self.assertIsNone(watch.project_bucket("/Users/x/Projects/nothing_here"))

    def test_discovery_finds_a_bucket_known_to_exist(self):
        """POSITIVE CONTROL for the discovery method itself.

        An earlier enumeration probe of mine returned a false negative, so the method gets
        the same treatment: prove it finds something already known to be there, including
        when the computed name is wrong.
        """
        cwd = "/Users/x/some_project"
        bucket = "-Users-x-some-project"
        made = mk_in_bucket(self.projects, bucket, "sess-d", cwd)
        self.assertTrue(os.path.isfile(made))                       # it exists
        self.assertNotEqual(cwd.replace("/", "-").replace(".", "-"), bucket)  # computation misses it
        self.assertEqual(watch.project_bucket(cwd), bucket)          # discovery finds it

    def test_cwdless_transcript_is_never_claimed(self):
        """STRICT discovery: no fallback. A cwd-less transcript is undiscoverable, and there
        is no computed-name backstop — the computed name is not injective ('/a/b.c' and
        '/a/b-c' both give '-a-b-c'), so a fallback could hand back ANOTHER project's
        bucket; and every real transcript records a cwd (108 of 108 on a live host), so it
        protected a case that does not occur."""
        computed = "/Users/x/mystery".replace("/", "-").replace(".", "-")
        d = os.path.join(self.projects, computed)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess-e.jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "no cwd"}}) + "\n")
        self.assertIsNone(watch.project_bucket("/Users/x/mystery"))
        mk_in_bucket(self.projects, computed, "sess-f", "/Users/x/mystery")
        self.assertEqual(watch.project_bucket("/Users/x/mystery"), computed)

    def test_computed_name_collision_cannot_claim_another_project(self):
        """The collision the deleted fallback would have exposed: '.' and '-' both map to '-'."""
        self.assertEqual("/w/b.c".replace("/", "-").replace(".", "-"),
                         "/w/b-c".replace("/", "-").replace(".", "-"))
        shared = "-w-b-c"
        mk_in_bucket(self.projects, shared, "sess-b", "/w/b-c")
        self.assertIsNone(watch.project_bucket("/w/b.c"),
                          "project A was handed project B's bucket")
        self.assertEqual(watch.project_bucket("/w/b-c"), shared)


class OneResolverAllThreeTools(unittest.TestCase):
    """All three session-taking tools route through ONE project-local resolver.

    The inverse of `test_no_cross_session_leakage`: that test gives each tool its OWN id and
    checks the answers do not mix, which proves non-mixing but NOT authorisation — both
    reads succeed. These assert that a FOREIGN project's exact id is REJECTED, which is the
    property that actually matters.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        # an UNDERSCORE caller project — the case that was dead before bucket discovery
        self.work = os.path.join(self.tmp, "my_project")
        os.makedirs(self.projects, exist_ok=True); os.makedirs(self.work, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        os.chdir(self.work)
        # ground truth escaping: '/', '.' AND '_' -> '-'  (observed on disk, NOT the formula)
        self.bucket = os.getcwd().replace("/", "-").replace(".", "-").replace("_", "-")
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(v, None)
        os.environ["MRTOKEN_CONTEXT_MAX"] = "1000000"
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp, "store")
        self.mine = self._heavy(self.bucket, "my-session", os.getcwd())
        self.foreign = self._heavy("-foreign-seat", "foreign-session", "/foreign/seat")

    def tearDown(self):
        os.chdir(self._cwd); watch.PROJECTS = self._orig
        for v in ("MRTOKEN_CONTEXT_MAX", "XDG_DATA_HOME"):
            os.environ.pop(v, None)

    def _heavy(self, bucket, session, cwd):
        d = os.path.join(self.projects, bucket); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{session}.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "cwd": cwd, "message": {
                "id": "m0", "model": "claude-opus-5",
                "usage": {"input_tokens": 50_000, "cache_read_input_tokens": 900_000,
                          "cache_creation_input_tokens": 0, "output_tokens": 10}}}) + "\n")
        return p

    def _call(self, tool, args):
        from mrtoken import toolbox
        txt, _ = toolbox.call_tool(tool, args)
        return txt

    def test_underscore_cwd_resolves_its_own_exact_id(self):
        """The caller project's path contains '_' — dead before discovery."""
        self.assertIn("_", os.getcwd())                                  # precondition
        self.assertNotEqual(os.getcwd().replace("/", "-").replace(".", "-"), self.bucket)
        self.assertEqual(watch.project_bucket(), self.bucket)
        self.assertEqual(watch.resolve_session_local("my-session"), self.mine)
        out = self._call("compact", {"session": "my-session"})
        self.assertIn("HEAVY", out)
        self.assertIn("950,000", out)          # its OWN occupancy, correctly reported

    def test_foreign_exact_id_rejected_by_all_three_tools(self):
        # precondition: the foreign transcript exists and is globally unique by id
        self.assertTrue(os.path.isfile(self.foreign))
        self.assertEqual(len(watch.glob.glob(os.path.join(
            self.projects, "*", "foreign-session.jsonl"))), 1)
        for tool in ("compact", "handoff", "confirm_disposable"):
            out = self._call(tool, {"session": "foreign-session"})
            self.assertNotIn("950,000", out, f"{tool} leaked the foreign occupancy")
            self.assertNotIn("Context occupancy: HEAVY", out, f"{tool} reported foreign HEAVY")

    def test_compact_foreign_id_is_unknown_with_no_foreign_value(self):
        out = self._call("compact", {"session": "foreign-session"})
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("950,000", out)
        self.assertNotIn("95.0%", out)

    def test_absent_key_defaults_stay_inside_the_caller_project(self):
        """Omitted `session` still works — and binds THIS project, never the foreign one."""
        # compact DELIBERATELY has no absent-key default — it never guesses a session, so
        # an omitted key is UNKNOWN by design. handoff/confirm_disposable DO default, and
        # must default INSIDE this project. The three tools therefore differ here on
        # purpose; asserted per-tool rather than assumed uniform.
        self.assertIn("UNKNOWN", self._call("compact", {}))
        self.assertIn("recorded:", self._call("confirm_disposable", {}))
        self.assertEqual(watch.project_bucket(), self.bucket)
        # and the default never reaches the foreign bucket
        self.assertNotEqual(watch.resolve_session_local("foreign-session"), self.foreign)
        self.assertIsNone(watch.resolve_session_local("foreign-session"))


class OmittedKeyEnvSeam(unittest.TestCase):
    """Absent-key was the one tool-reachable route into the TRUSTED global resolver.

    `build_handoff(None, None)` -> `resolve_path(None)` -> `latest_transcript()`, which honours
    MRTOKEN_SESSION / CLAUDE_CODE_SESSION_ID through the GLOBAL resolver.

    CRITICAL: the foreign env binding is LEFT SET throughout. Popping it — which every other
    harness here did, mine included — removes the precondition and blinds the test. A control
    that clears the environment proves nothing about an environment-mediated defect.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        self.work = os.path.join(self.tmp, "caller")
        os.makedirs(self.projects, exist_ok=True); os.makedirs(self.work, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        os.chdir(self.work)
        self.bucket = os.getcwd().replace("/", "-").replace(".", "-").replace("_", "-")
        self.local = mk_in_bucket(self.projects, self.bucket, "local-session", os.getcwd())
        self.foreign = mk_in_bucket(self.projects, "-foreign-seat", "foreign-session",
                                    "/foreign/seat")

    def tearDown(self):
        os.chdir(self._cwd); watch.PROJECTS = self._orig
        os.environ.pop("MRTOKEN_SESSION", None)

    def _bound_arg(self, args):
        """The argument _handoff_call actually passes inward — that argument IS the evidence.
        Re-running a resolution myself would test my call, not the tool's."""
        from mrtoken import toolbox
        orig = toolbox.build_handoff
        toolbox.build_handoff = lambda db, s: "BOUND:" + repr(s)
        try:
            txt, _ = toolbox.call_tool("handoff", args)
        finally:
            toolbox.build_handoff = orig
        return eval(txt[len("BOUND:"):]) if txt.startswith("BOUND:") else None

    def test_omitted_key_never_binds_foreign_env_session(self):
        os.environ["MRTOKEN_SESSION"] = "foreign-session"        # LEFT BOUND
        # precondition: the foreign id IS globally resolvable, so rejection is real
        self.assertEqual(watch.resolve_session("foreign-session"), self.foreign)
        for args in ({}, {"session_absent_marker": 1}):
            bound = self._bound_arg(args)
            self.assertNotEqual(bound, self.foreign,
                                f"omitted key bound the FOREIGN transcript for {args}")
            if bound is not None:
                self.assertEqual(os.path.realpath(bound), os.path.realpath(self.local))

    def test_omitted_key_with_no_env_binds_local_newest(self):
        """CONTROL: local-newest semantics preserved when no env id is present."""
        os.environ.pop("MRTOKEN_SESSION", None)
        bound = self._bound_arg({})
        self.assertIsNotNone(bound, "the local default stopped working")
        self.assertEqual(os.path.realpath(bound), os.path.realpath(self.local))

    def test_explicit_valid_local_id_still_works(self):
        """POSITIVE CONTROL, with the foreign env still bound."""
        os.environ["MRTOKEN_SESSION"] = "foreign-session"
        bound = self._bound_arg({"session": "local-session"})
        self.assertEqual(os.path.realpath(bound), os.path.realpath(self.local))
