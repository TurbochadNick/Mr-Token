#!/usr/bin/env python3
"""The handoff goal must reflect CURRENT work, not a session-start artifact.

Root cause, proven on a real 830k-token session: `ai-title` outranked everything, and an
ai-title never refreshes — 132 events, ONE distinct value, first == last, zero custom-title.
So the goal read "Environment validation session" ~24h and eight tasks after that was true.

Fixture shapes are taken from GROUND TRUTH observed in a real transcript (`type: "ai-title"`
with key `aiTitle`; `type: "custom-title"` with `customTitle`), not from the function here.
"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mrtoken.handoff import _scan_transcript, goal_from_scan


def write(events):
    p = os.path.join(tempfile.mkdtemp(), "s.jsonl")
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    return p


def user(text):
    return {"type": "user", "cwd": "/w", "message": {"content": text}}


def goal_of(s):
    """Call the PRODUCTION ranking. An earlier version of this helper re-implemented the
    new ranking here, so the test bypassed the code under test entirely and passed on the
    UNFIXED build — a fixture must never reimplement the thing it is checking."""
    return goal_from_scan(s)


class HandoffGoalCurrency(unittest.TestCase):
    def test_ai_title_does_not_outrank_the_later_request(self):
        """THE DEFECT: early auto-title vs a materially later substantive request."""
        p = write([user("set up the environment"),
                   {"type": "ai-title", "aiTitle": "Environment validation session"},
                   user("fix the cross-project session binding in the MCP toolbox")])
        s = _scan_transcript(p)
        # precondition via .get() so this FAILS (not errors) on the unfixed build
        self.assertEqual(s.get("ai_title") or s.get("title"),
                         "Environment validation session")
        self.assertIn("cross-project session binding", goal_of(s))
        self.assertNotIn("Environment validation", goal_of(s))

    def test_human_custom_title_still_wins(self):
        p = write([user("first thing"),
                   {"type": "custom-title", "customTitle": "Ship the auth rewrite"},
                   {"type": "ai-title", "aiTitle": "Auto generated thing"},
                   user("a much later unrelated request")])
        s = _scan_transcript(p)
        self.assertEqual(goal_of(s), "Ship the auth rewrite")

    def test_last_prompt_still_outranks_first_prompt(self):
        """REGRESSION: the existing, correct fallback order must survive."""
        p = write([user("the very first request"), user("the most recent request")])
        s = _scan_transcript(p)
        self.assertEqual(goal_of(s), "the most recent request")

    def test_ai_title_still_used_when_there_is_nothing_better(self):
        """The auto-title is a fallback, not garbage — it still beats nothing."""
        p = write([{"type": "ai-title", "aiTitle": "Only signal available"}])
        s = _scan_transcript(p)
        self.assertEqual(goal_of(s), "Only signal available")

    def test_completed_test_output_is_still_omitted(self):
        """Omission preserved: the fix must not turn the goal into a transcript summary."""
        p = write([user("do the thing"),
                   {"type": "assistant", "cwd": "/w",
                    "message": {"content": "Ran 197 tests in 1.9s\n\nOK"}},
                   user("now do the next thing")])
        s = _scan_transcript(p)
        self.assertNotIn("Ran 197 tests", goal_of(s))
        self.assertNotIn("OK", goal_of(s))
