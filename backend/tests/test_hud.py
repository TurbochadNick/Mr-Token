#!/usr/bin/env python3
"""One HUD field set and one terse line for both providers (mrtoken.hud).

What is pinned, because each was wrong before this change:
- the token figure is TOTAL expenditure, not the fresh input + output subtotal
  (the Codex HUD printed ~32k for a session whose provider total was 382k);
- no dollar figure on either provider (no billing ground truth exists);
- a field that applies but cannot be derived renders "?" and carries its reason;
  a field that does not apply is omitted, never shown as "?" or as zero;
- the limit shown is the reported window closest to binding, named by its duration,
  as % USED, labelled (every budget % on the line runs the same way);
- cache is labelled a hit rate ("cache hit"), so it is not read as consumption;
- ctx % is labelled "used", and a window that is not measured is never shown as one;
- the recommendation slot is fed only by a direct readout (context fullness);
- the "mr" prefix leads every line.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from mrtoken import hud
from mrtoken.statusline import build_statusline_text, _model_label

V = hud.attribution()  # "mr <running version>"; read, never hardcoded

CODEX_SID = "019f-hud-parity"


def codex_rollout(tmp, total_usage=True, rate_limits=True, window=1_000_000, effort="xhigh"):
    d = os.path.join(tmp, ".codex", "sessions", "2026", "09", "23")
    os.makedirs(d)
    ctx = {"model": "gpt-5.5"}
    if effort:
        ctx["effort"] = effort
    rows = [{"timestamp": "2026-09-23T00:00:00Z", "type": "session_meta",
             "payload": {"session_id": CODEX_SID, "cwd": BACKEND}},
            {"timestamp": "2026-09-23T00:00:01Z", "type": "turn_context", "payload": ctx}]
    turns = [((100_000, 90_000, 1_000), (100_000, 90_000, 1_000)),
             ((280_000, 260_000, 1_000), (380_000, 350_000, 2_000))]
    for i, ((li, lc, lo), (ti, tc, to)) in enumerate(turns):
        info = {"last_token_usage": {"input_tokens": li, "cached_input_tokens": lc,
                                     "output_tokens": lo, "total_tokens": li + lo}}
        if window:
            info["model_context_window"] = window
        if total_usage:
            info["total_token_usage"] = {"input_tokens": ti, "cached_input_tokens": tc,
                                         "output_tokens": to, "total_tokens": ti + to}
        payload = {"type": "token_count", "info": info}
        if rate_limits:
            payload["rate_limits"] = {"primary": {"used_percent": 42.0, "window_minutes": 10080,
                                                  "resets_at": 1790000000}}
        rows.append({"timestamp": f"2026-09-23T00:00:0{i + 2}Z", "type": "event_msg", "payload": payload})
    path = os.path.join(d, f"rollout-2026-09-23T00-00-00-{CODEX_SID}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    return path


def run_codex_stop_hook(tmp):
    """The real Codex HUD path: the Stop hook, HOME and store isolated in tmp."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("TOKEN_TITHE_DB", "MRTOKEN_DATA_DIR", "XDG_DATA_HOME")}
    env.update(HOME=tmp, MRTOKEN_DB=os.path.join(tmp, "codex.db"), PYTHONPATH=BACKEND)
    p = subprocess.run([sys.executable, os.path.join(BACKEND, "hooks", "on_stop.py")],
                       input=json.dumps({"session_id": CODEX_SID, "cwd": BACKEND}),
                       text=True, capture_output=True, env=env)
    if p.returncode:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout)["systemMessage"].splitlines()[0]


def claude_transcript(tmp):
    """3 API responses; response 1 is written as TWO transcript lines (same message id),
    as Claude Code does, so a non-deduplicating total would count it twice."""
    path = os.path.join(tmp, "claude.jsonl")
    lines = []
    for i in range(3):
        msg = {"id": f"msg_{i}", "model": "claude-opus-4-5", "role": "assistant",
               "usage": {"input_tokens": 1000, "cache_read_input_tokens": 50_000,
                         "cache_creation_input_tokens": 2000, "output_tokens": 500},
               "content": [{"type": "text", "text": "x"}]}
        line = {"type": "assistant", "uuid": f"u{i}", "timestamp": f"2026-09-23T00:00:0{i}Z", "message": msg}
        lines.append(line)
        if i == 1:
            lines.append(dict(line, uuid="u1b"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(l) + "\n" for l in lines)
    return path


class HudTest(unittest.TestCase):
    def test_codex_line_shows_total_expenditure_and_no_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_rollout(tmp)
            line = run_codex_stop_hook(tmp)
        # 382k = provider total_token_usage (380k in incl. cached + 2k out); the old HUD said ~32k
        # the Codex CLI already shows model + effort; the window rides on ctx (brevity: this
        # message enters the model conversation)
        self.assertEqual(line, f"{V} · ctx 28% used of 1M · ~382k tok · cache hit 92% · 7d 42% used")
        self.assertNotIn("$", line)

    def test_claude_line_total_is_deduplicated_disjoint_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            line = build_statusline_text(transcript_path=claude_transcript(tmp))
        # 3 x (1,000 + 50,000 + 2,000 + 500) = 160,500; counting the duplicate line would give 214k
        # no stdin: the window is NOT measured here, so no size and ctx % is "?" (an inferred
        # 200k would be a guess); tokens and cache are still measured from the transcript
        self.assertEqual(line, f"{V} · Opus 4.5 · effort ? · ctx ? · ~160k tok · cache hit 94%")
        self.assertNotIn("$", line)

    def test_claude_terminal_uses_stdin_window_effort_and_binding_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = claude_transcript(tmp)
            line = build_statusline_text(transcript_path=path, effort="high", plan_5h=45, plan_7d=30,
                                         model={"id": "claude-opus-5", "display_name": "Opus 5 (1M context)"},
                                         context_window_size=1_000_000)
            high = build_statusline_text(transcript_path=path, effort="high", plan_5h=45, plan_7d=30,
                                         model={"id": "claude-opus-5", "display_name": "Opus 5"},
                                         context_window_size=70_000)
        self.assertEqual(line, f"{V} · Opus 5 1M · high · ctx 5% used · ~160k tok · cache hit 94% · 5h 45% used")
        self.assertEqual(high, f"{V} · Opus 5 70k · high · ctx 75% used · ~160k tok · cache hit 94% · 5h 45% used"
                               " · ⚠ compact soon")
        self.assertEqual(high.count("⚠"), 1)  # the warning renders once, in its slot

    def test_unknown_carries_its_reason(self):
        from mrtoken.ingest_codex import codex_usage_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            usage = codex_usage_snapshot(codex_rollout(tmp, total_usage=False))
        f = hud.codex_hud_fields(usage)
        self.assertEqual(f.total_tokens.state, hud.UNKNOWN)
        self.assertEqual(f.total_tokens.reason, "provider reported no running total")
        self.assertIn("tok ?", hud.format_line(f))
        drifted = dict(usage, provider_total={"input": 100, "cached": 0, "output": 5, "total": 999})
        f = hud.codex_hud_fields(drifted)
        self.assertEqual(f.total_tokens.reason, "provider total did not reconcile (in + out != total)")

    def test_not_applicable_is_omitted_not_questioned(self):
        from mrtoken.ingest_codex import codex_usage_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            usage = codex_usage_snapshot(codex_rollout(tmp, rate_limits=False, window=None))
        line = hud.format_line(hud.codex_hud_fields(usage))
        # no window reported: no size after the model (NA, omitted, not "?");
        # no rate limit reported: no window segment (NA, not "7d 0%");
        # ctx % needs the window: it applies but is underivable, so "ctx ?"
        self.assertEqual(line, f"{V} · gpt-5.5 · xhigh · ctx ? · ~382k tok · cache hit 92%")

    def test_trailing_token_count_without_info_keeps_the_last_real_reading(self):
        # some Codex token_count events carry no info (seen on 0-7% of events in older
        # CLI versions); one at the end must not blank a session that has its numbers
        from mrtoken.ingest_codex import codex_usage_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            path = codex_rollout(tmp)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"timestamp": "2026-09-23T00:00:09Z", "type": "event_msg",
                                     "payload": {"type": "token_count", "info": None}}) + "\n")
            line = hud.format_line(hud.codex_hud_fields(codex_usage_snapshot(path)))
        self.assertEqual(line, f"{V} · gpt-5.5 1M · xhigh · ctx 28% used · ~382k tok · cache hit 92% · 7d 42% used")

    def test_limiter_is_the_most_binding_window_named_by_duration(self):
        lim = hud.binding_limiter([(300, 20), (10080, 60)], "p")
        self.assertEqual((lim.value["label"], lim.value["used_pct"], lim.alert), ("7d", 60, False))
        self.assertTrue(hud.binding_limiter([(300, 90)], "p").alert)
        self.assertEqual(hud.binding_limiter([(300, None)], "p").state, hud.NA)

    def test_recommendation_only_from_the_context_readout(self):
        f = hud.HudFields(model=hud.known("m"), ctx_pct=hud.ctx_field(40, "p"))
        self.assertEqual(hud.recommend(f).recommendation.state, hud.NA)
        f = hud.HudFields(model=hud.known("m"), ctx_pct=hud.ctx_field(90, "p"))
        self.assertEqual(hud.recommend(f).recommendation.value, "compact soon")

    def test_near_limit_is_a_warning_not_an_inline_glyph(self):
        f = hud.recommend(hud.HudFields(model=hud.known("m"), ctx_pct=hud.ctx_field(40, "p"),
                                        limiter=hud.binding_limiter([(300, 91)], "p")))
        self.assertEqual(hud.format_line(f).split(" · ")[-2:], ["5h 91% used", "⚠ 5h limit near"])

    def test_width_drop_order_keeps_attribution_tokens_limit_and_warning(self):
        f = hud.recommend(hud.HudFields(
            model=hud.known("Opus 5.5"), context_window=hud.known(1_000_000), effort=hud.known("high"),
            ctx_pct=hud.ctx_field(80, "p"), total_tokens=hud.known(2_100_000), cache_ratio=hud.known(0.94),
            limiter=hud.binding_limiter([(300, 45)], "p")))
        full = hud.format_line(f)
        self.assertEqual(full, f"{V} · Opus 5.5 1M · high · ctx 80% used · ~2.1M tok · cache hit 94% · 5h 45% used · ⚠ compact soon")
        self.assertEqual(hud.format_line(f, width=len(full)), full)
        self.assertNotIn("cache hit", hud.format_line(f, width=len(full) - 1))
        # cannot fit: cache, window size, effort, ctx % go (in that order); attribution,
        # total tokens, the limit and the warning never do
        narrow = hud.format_line(f, width=10)
        self.assertEqual(narrow, f"{V} · Opus 5.5 · ~2.1M tok · 5h 45% used · ⚠ compact soon")

    def test_attribution_leads_every_line_and_reads_the_running_version(self):
        import mrtoken
        self.assertEqual(V, f"mr {mrtoken.__version__}")
        self.assertTrue(hud.format_line(hud.HudFields()).startswith(V + " · "))
        self.assertTrue(hud.format_codex_stop(hud.HudFields()).startswith(V + " · "))

    def test_single_version_model_id_is_prettified(self):
        # the hook copy showed the raw "claude-opus-5" beside the statusLine's "Opus 5"
        self.assertEqual(_model_label("claude-opus-5"), "Opus 5")
        self.assertEqual(_model_label("claude-opus-5-20260301"), "Opus 5")  # date is not a version

    def test_claude_window_and_model_follow_a_mid_session_change(self):
        # model and window are independent selections in Claude Code (/model; 1M context);
        # each render re-reads them, so the line must follow either change
        with tempfile.TemporaryDirectory() as tmp:
            path = claude_transcript(tmp)
            render = lambda disp, size: build_statusline_text(
                transcript_path=path, effort="high", model={"id": "x", "display_name": disp},
                context_window_size=size)
            a = render("Opus 5", 200_000)
            b = render("Opus 5 (1M context)", 1_000_000)
            c = render("Sonnet 4.6", 1_000_000)
        self.assertIn("Opus 5 200k · high · ctx 26% used", a)
        self.assertIn("Opus 5 1M · high · ctx 5% used", b)
        self.assertIn("Sonnet 4.6 1M · high · ctx 5% used", c)

    def test_codex_window_and_model_follow_a_mid_session_change(self):
        from mrtoken.ingest_codex import codex_usage_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            path = codex_rollout(tmp, window=272_000)
            before = hud.format_line(hud.codex_hud_fields(codex_usage_snapshot(path)))
            with open(path, "a", encoding="utf-8") as fh:  # the user switches model mid-session
                fh.write(json.dumps({"timestamp": "2026-09-23T00:01:00Z", "type": "turn_context",
                                     "payload": {"model": "gpt-5.6-sol", "effort": "medium"}}) + "\n")
                fh.write(json.dumps({"timestamp": "2026-09-23T00:01:01Z", "type": "event_msg", "payload": {
                    "type": "token_count", "info": {
                        "model_context_window": 1_000_000,
                        "last_token_usage": {"input_tokens": 300_000, "cached_input_tokens": 280_000,
                                             "output_tokens": 1_000, "total_tokens": 301_000},
                        "total_token_usage": {"input_tokens": 680_000, "cached_input_tokens": 630_000,
                                              "output_tokens": 3_000, "total_tokens": 683_000}}}}) + "\n")
            after = hud.format_line(hud.codex_hud_fields(codex_usage_snapshot(path)))
        self.assertIn("gpt-5.5 272k · xhigh · ctx ", before)
        self.assertIn("gpt-5.6-sol 1M · med · ctx 30% used", after)


if __name__ == "__main__":
    unittest.main()
