#!/usr/bin/env python3
"""The Codex proc-engine intervention is off BY DECISION (on_stop.CODEX_INTERVENTION), not
merely starved by the rules gate.

The fixture makes a REAL reclaimable rule fire (a 50,000-char tool output: huge_tool_output)
under context pressure (85% of the window), with the rules engine forced ON, so the only
thing that can keep the intervention out of the Stop message is the switch. The positive
control flips the switch on over the same fixture and requires the intervention to appear,
so the no-intervention assertion is proven able to fail.
"""
import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

import mrtoken.datadir as dd
import mrtoken.policy as policy
import mrtoken.rules as rules

SID = "019efb64-cafe-7b80-8c75-deadbeefc0de"


def load_on_stop():
    spec = importlib.util.spec_from_file_location("on_stop_iv", os.path.join(BACKEND, "hooks", "on_stop.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_rollout(tmp):
    d = os.path.join(tmp, "codex", "2026", "09")
    os.makedirs(d)
    rows = [
        {"timestamp": "2026-09-23T00:00:00Z", "type": "session_meta", "payload": {"session_id": SID, "cwd": "/proj"}},
        {"timestamp": "2026-09-23T00:00:01Z", "type": "turn_context", "payload": {"model": "gpt-5.5", "effort": "high"}},
        {"timestamp": "2026-09-23T00:00:02Z", "type": "response_item",
         "payload": {"type": "function_call", "name": "shell", "call_id": "c1", "arguments": "{}"}},
        {"timestamp": "2026-09-23T00:00:03Z", "type": "response_item",
         "payload": {"type": "function_call_output", "call_id": "c1", "output": "x" * 50_000}},
    ]
    for i in range(3):  # several calls under pressure: 85k input of a 100k window = 85%
        rows.append({"timestamp": f"2026-09-23T00:00:1{i}Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {
                "model_context_window": 100_000,
                "last_token_usage": {"input_tokens": 85_000, "cached_input_tokens": 80_000,
                                     "output_tokens": 100, "total_tokens": 85_100},
                "total_token_usage": {"input_tokens": 85_000 * (i + 1), "cached_input_tokens": 80_000 * (i + 1),
                                      "output_tokens": 100 * (i + 1), "total_tokens": 85_100 * (i + 1)}}}})
    with open(os.path.join(d, f"rollout-2026-09-23T00-00-00-{SID}.jsonl"), "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)


def run_stop_hook(tmp, intervention: bool):
    on_stop = load_on_stop()
    on_stop.PROJECTS = os.path.join(tmp, "no-claude")
    on_stop.CODEX_DIRS = (os.path.join(tmp, "codex"),)
    on_stop.CODEX_INTERVENTION = intervention
    db = os.path.join(tmp, f"codex-{intervention}.db")
    env = {k: v for k, v in os.environ.items() if k not in ("MRTOKEN_INTERVENE", "TOKEN_TITHE_DB")}
    env.update(MRTOKEN_DB=db, HOME=tmp)
    out = io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch.object(rules, "RULES_ENABLED", True), \
         mock.patch.object(dd, "central_default", lambda: tmp), \
         mock.patch.object(policy, "_config_path", lambda: os.path.join(tmp, "config.json")), \
         mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"session_id": SID, "cwd": "/proj"}))), \
         contextlib.redirect_stdout(out):
        try:
            on_stop.main()
        except SystemExit:
            pass
    fired = [r[0] for r in sqlite3.connect(db).execute("SELECT rule FROM recommendation")]
    return json.loads(out.getvalue())["systemMessage"], fired


class CodexInterventionOffTest(unittest.TestCase):
    def test_switch_is_off_by_default(self):
        self.assertFalse(load_on_stop().CODEX_INTERVENTION)

    def test_no_intervention_even_with_rules_on_and_a_reclaimable_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_rollout(tmp)
            msg, fired = run_stop_hook(tmp, intervention=False)
        self.assertIn("huge_tool_output", fired)  # precondition: the rule REALLY fired
        self.assertNotIn("offload", msg)

    def test_positive_control_the_same_fixture_shows_the_intervention(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_rollout(tmp)
            msg, fired = run_stop_hook(tmp, intervention=True)
        self.assertIn("huge_tool_output", fired)
        self.assertIn("offload", msg)  # the intervention names the tool it recommends


if __name__ == "__main__":
    unittest.main()
