#!/usr/bin/env python3
"""`compact` must MEASURE, not assert. Regression suite for the hardcoded-constant defect.

Pre-fix `_compact_call` was a constant: 0 calls, 0 attribute reads, `args` unused, and an
empty inputSchema, so it told every session "Context is heavy" — including sessions it
could not even receive. Every test here fails against that implementation.

Central invariant: UNKNOWN MUST NEVER RENDER AS HEAVY. An absent measurement is not a
positive one.
"""
import json
import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mrtoken import toolbox as tb
from mrtoken import watch


def harness_bucket(cwd):
    """The bucket name Claude Code ACTUALLY produces, from ground truth observed on disk:
    it maps '/', '.' AND '_' to '-'. Deliberately not imported from the code under test —
    a fixture that derives its expected value from the production formula can only ever
    prove self-consistency, and both were wrong together."""
    out = cwd
    for ch in ("/", ".", "_"):
        out = out.replace(ch, "-")
    return out


def _write_transcript(projects, bucket, session, turns, age_s=0):
    """One transcript with provider-reported usage. `turns` = [(input, cache_read), ...].

    Each turn is emitted TWICE with the same message id to exercise the mandatory dedup —
    real transcripts repeat an assistant message up to 4x, and naive summing inflates.
    """
    d = os.path.join(projects, bucket)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{session}.jsonl")
    with open(p, "w") as fh:
        for i, (inp, cache) in enumerate(turns):
            line = json.dumps({
                "type": "assistant", "cwd": os.getcwd(),
                "message": {"id": f"msg_{i}", "model": "claude-opus-5",
                            "usage": {"input_tokens": inp,
                                      "cache_read_input_tokens": cache,
                                      "cache_creation_input_tokens": 0,
                                      "output_tokens": 10}}})
            fh.write(line + "\n")
            fh.write(line + "\n")   # duplicate: same message id
    if age_s:
        old = time.time() - age_s
        os.utime(p, (old, old))
    return p


class CompactMeasuresContext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(self.projects, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        self.work = os.path.join(self.tmp, "work"); os.makedirs(self.work, exist_ok=True)
        os.chdir(self.work)
        self.bucket = harness_bucket(os.getcwd())
        for var in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID", "MRTOKEN_CONTEXT_MAX"):
            os.environ.pop(var, None)
        os.environ["MRTOKEN_CONTEXT_MAX"] = "1000000"

    def tearDown(self):
        os.chdir(self._cwd)
        watch.PROJECTS = self._orig
        os.environ.pop("MRTOKEN_CONTEXT_MAX", None)

    # 1 — light session
    def test_light_session_is_not_heavy(self):
        _write_transcript(self.projects, self.bucket, "sess-light", [(500, 400)])
        out = tb._compact_call({"session": "sess-light"})
        self.assertIn("NOT_HEAVY", out)
        self.assertNotIn("Context occupancy: HEAVY", out)

    # 2 — heavy session
    def test_heavy_session_is_heavy(self):
        _write_transcript(self.projects, self.bucket, "sess-heavy", [(50_000, 900_000)])
        out = tb._compact_call({"session": "sess-heavy"})
        self.assertIn("HEAVY", out)
        self.assertNotIn("NOT_HEAVY", out)
        self.assertIn("/compact", out)

    # 3 — unavailable measurement
    def test_missing_transcript_is_unknown(self):
        out = tb._compact_call({"session": "no-such-session"})
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("Context occupancy: HEAVY", out)

    def test_transcript_without_usage_is_unknown_not_zero(self):
        d = os.path.join(self.projects, self.bucket)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sess-nousage.jsonl"), "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        out = tb._compact_call({"session": "sess-nousage"})
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("Context occupancy: HEAVY", out)

    # 4 — stale (defect (a) — asserted explicitly)
    def test_stale_transcript_is_unknown(self):
        _write_transcript(self.projects, self.bucket, "sess-stale",
                          [(50_000, 900_000)], age_s=tb.COMPACT_STALE_AFTER_S + 120)
        out = tb._compact_call({"session": "sess-stale"})
        self.assertIn("UNKNOWN", out)
        self.assertIn("stale", out.lower())
        # a stale HEAVY-looking session must NOT be reported heavy
        self.assertNotIn("Context occupancy: HEAVY", out)

    # 5 — hostile input
    def test_hostile_session_ids_are_rejected(self):
        victim = _write_transcript(self.projects, self.bucket, "victim", [(50_000, 900_000)])
        for bad in ("foo/../victim", "../victim", victim, "", "\x00", "a/b", 12345, None, {}):
            out = tb._compact_call({"session": bad})
            self.assertIn("UNKNOWN", out, f"hostile input not rejected: {bad!r}")
            self.assertNotIn("Context occupancy: HEAVY", out, f"traversal leaked: {bad!r}")
            self.assertNotIn("900", out, f"victim measurement leaked for {bad!r}")

    # 6 — exact binding, never the newest
    def test_explicit_session_binds_exactly_not_newest(self):
        _write_transcript(self.projects, self.bucket, "sess-old-light", [(500, 400)])
        time.sleep(0.01)
        _write_transcript(self.projects, self.bucket, "sess-new-heavy", [(50_000, 900_000)])
        # the light one is OLDER; newest-file guessing would return the heavy one
        out = tb._compact_call({"session": "sess-old-light"})
        self.assertIn("NOT_HEAVY", out)
        self.assertNotIn("Context occupancy: HEAVY", out)

    # 7 — no cross-session leakage
    def test_no_cross_session_leakage(self):
        _write_transcript(self.projects, self.bucket, "sess-aaa", [(50_000, 900_000)])
        _write_transcript(self.projects, self.bucket, "sess-bbb", [(500, 400)])
        out_a = tb._compact_call({"session": "sess-aaa"})
        out_b = tb._compact_call({"session": "sess-bbb"})
        # A is genuinely heavy, and its exact occupancy is 50,000 + 900,000
        self.assertIn("HEAVY", out_a)
        self.assertIn("950,000", out_a)
        # B is light, and NONE of A's measurement may appear in B's call
        self.assertIn("NOT_HEAVY", out_b)
        self.assertNotIn("950,000", out_b)
        self.assertIn("900", out_b_occ := out_b.split(" tok")[0])  # B's own 900 = 500+400
        self.assertNotIn("95.0%", out_b)

    # 8 — runtime discrimination (the zero/positive control)
    def test_light_and_heavy_outputs_differ(self):
        _write_transcript(self.projects, self.bucket, "sess-l", [(500, 400)])
        _write_transcript(self.projects, self.bucket, "sess-h", [(50_000, 900_000)])
        light = tb._compact_call({"session": "sess-l"})
        heavy = tb._compact_call({"session": "sess-h"})
        self.assertNotEqual(light, heavy,
                            "byte-identical output for light and heavy input is the defect")

    # 9 — MUTANT TEST: the environment-leak defect.
    # Deliberately KEEPS MRTOKEN_SESSION bound to a heavy victim. The v1 bug used
    # `args.get("session") or env`, so any falsey EXPLICIT session fell through to the
    # environment and reported the victim's occupancy as if it were the caller's.
    # This test only has power BECAUSE the env stays bound — removing it, as setUp does
    # for every other test, makes the defect structurally undetectable.
    def test_explicit_falsey_session_never_falls_back_to_env(self):
        _write_transcript(self.projects, self.bucket, "victim-heavy", [(50_000, 900_000)])
        os.environ["MRTOKEN_SESSION"] = "victim-heavy"
        try:
            # the victim really is heavy when legitimately addressed
            legit = tb._compact_call({"session": "victim-heavy"})
            self.assertIn("HEAVY", legit)
            self.assertIn("950,000", legit)
            for bad in ("", None, 0, False, {}, []):
                out = tb._compact_call({"session": bad})
                self.assertIn("UNKNOWN", out,
                              f"explicit falsey session {bad!r} did not yield UNKNOWN")
                self.assertNotIn("950,000", out,
                                 f"victim occupancy leaked for explicit session {bad!r}")
                self.assertNotIn("Context occupancy: HEAVY", out,
                                 f"invalid state reported HEAVY for session {bad!r}")
        finally:
            os.environ.pop("MRTOKEN_SESSION", None)

    # 10 — CONTROL, preserved: an ABSENT key legitimately uses the environment.
    def test_absent_session_key_still_uses_env(self):
        _write_transcript(self.projects, self.bucket, "env-light", [(500, 400)])
        os.environ["MRTOKEN_SESSION"] = "env-light"
        try:
            out = tb._compact_call({})          # key absent -> env fallback is CORRECT
            self.assertIn("NOT_HEAVY", out)
            self.assertNotIn("UNKNOWN", out)
        finally:
            os.environ.pop("MRTOKEN_SESSION", None)

    # schema must be able to receive a session at all
    def test_schema_declares_session(self):
        self.assertIn("session", tb.COMPACT_TOOL["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class CompactOverRealTransport(unittest.TestCase):
    """Drive tools/call through the ACTUAL JSON-RPC stdio server.

    Direct unit calls on `_compact_call` cannot see transport-layer defects — that is
    precisely how the `params.get("arguments") or {}` collapse escaped two reviews. These
    controls serialize to JSON, pass through mcp_server.serve, and parse the response.

    MRTOKEN_SESSION stays bound to a HEAVY victim for every case, so any fallthrough to the
    server environment shows up as the victim's occupancy in the response text.
    """

    def setUp(self):
        import io
        self.io = io
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(self.projects, exist_ok=True)
        self._orig, self._cwd = watch.PROJECTS, os.getcwd()
        watch.PROJECTS = self.projects
        self.work = os.path.join(self.tmp, "work"); os.makedirs(self.work, exist_ok=True)
        os.chdir(self.work)
        self.bucket = harness_bucket(os.getcwd())
        os.environ["MRTOKEN_CONTEXT_MAX"] = "1000000"
        _write_transcript(self.projects, self.bucket, "victim-heavy", [(50_000, 900_000)])
        os.environ["MRTOKEN_SESSION"] = "victim-heavy"   # deliberately left bound

    def tearDown(self):
        os.chdir(self._cwd)
        watch.PROJECTS = self._orig
        os.environ.pop("MRTOKEN_SESSION", None)
        os.environ.pop("MRTOKEN_CONTEXT_MAX", None)

    def _rpc(self, params):
        from mrtoken import mcp_server
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
        out = self.io.StringIO()
        mcp_server.serve(stdin=self.io.StringIO(json.dumps(req) + "\n"), stdout=out)
        for line in out.getvalue().splitlines():
            if line.strip():
                return json.loads(line)
        return {}

    def _text(self, resp):
        if "error" in resp:
            return "JSONRPC_ERROR " + str(resp["error"].get("message", ""))
        result = resp.get("result") or {}
        return "".join(b.get("text", "") for b in result.get("content", [])
                       if isinstance(b, dict))

    # control 1 — legitimate absence still uses the environment
    def test_absent_and_empty_arguments_use_env(self):
        for params in ({"name": "compact"}, {"name": "compact", "arguments": {}}):
            text = self._text(self._rpc(params))
            self.assertIn("HEAVY", text, f"env fallback broken for {params}")
            self.assertIn("950,000", text)

    # control 2 — a present falsey/non-string session is UNKNOWN, over the transport
    def test_present_invalid_session_is_unknown_over_transport(self):
        for bad in ("", None, 0, False, [], {}, 12345):
            text = self._text(self._rpc({"name": "compact", "arguments": {"session": bad}}))
            self.assertIn("UNKNOWN", text, f"session={bad!r} not UNKNOWN")
            self.assertNotIn("950,000", text, f"victim leaked for session={bad!r}")
            self.assertNotIn("Context occupancy: HEAVY", text)

    # control 3 — a present non-object `arguments` never reaches the environment
    def test_present_non_object_arguments_never_reach_env(self):
        for bad in (None, [], "", 0, False, [1, 2], "abc", 1, True):
            text = self._text(self._rpc({"name": "compact", "arguments": bad}))
            ok = text.startswith("JSONRPC_ERROR") or "UNKNOWN" in text
            self.assertTrue(ok, f"arguments={bad!r} neither errored nor UNKNOWN: {text[:80]}")
            self.assertNotIn("HEAVY", text, f"arguments={bad!r} reported HEAVY")
            self.assertNotIn("950,000", text, f"arguments={bad!r} leaked occupancy")
            self.assertNotIn("95.0%", text, f"arguments={bad!r} leaked percentage")

    # the boundary fix must protect EVERY tool, not just compact
    def test_boundary_protects_other_tools(self):
        for tool in ("handoff", "confirm_disposable", "offload"):
            resp = self._rpc({"name": tool, "arguments": [1, 2]})
            self.assertIn("error", resp, f"{tool}: non-object arguments not rejected")
            self.assertEqual(resp["error"]["code"], -32602)

    # malformed `params` itself must not collapse either
    def test_non_object_params_is_rejected(self):
        from mrtoken import mcp_server
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1, 2]}
        out = self.io.StringIO()
        mcp_server.serve(stdin=self.io.StringIO(json.dumps(req) + "\n"), stdout=out)
        resp = json.loads(out.getvalue().splitlines()[0])
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def _raw(self, req):
        """Send an arbitrary JSON-RPC request dict through the real stdio server."""
        from mrtoken import mcp_server
        out = self.io.StringIO()
        mcp_server.serve(stdin=self.io.StringIO(json.dumps(req) + "\n"), stdout=out)
        lines = [l for l in out.getvalue().splitlines() if l.strip()]
        return json.loads(lines[0]) if lines else {}

    # `params` gets the SAME presence rule as `arguments`.
    # `.get("params")` returns None for key-absent AND key-present-with-JSON-null, so
    # `is None` cannot tell them apart — the collapse, a fourth time. `null` is the
    # value that discriminates; the rest were already caught by the isinstance check.
    def test_present_falsey_params_is_rejected(self):
        for bad in (None, [], "", 0, False):
            resp = self._raw({"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                              "params": bad})
            self.assertIn("error", resp, f'params={bad!r} was not rejected')
            self.assertEqual(resp["error"]["code"], -32602, f"params={bad!r}")

    # CONTROL: an OMITTED params key is legitimate and must still work.
    def test_omitted_params_still_works(self):
        resp = self._raw({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertNotIn("error", resp)
        self.assertIn("tools", resp.get("result", {}))

    # and the same pair for tools/call
    def test_null_params_on_tools_call_is_rejected_not_absent(self):
        resp = self._raw({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": None})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
