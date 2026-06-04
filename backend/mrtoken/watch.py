#!/usr/bin/env python3
"""MR Token — live in-session advisor.

Tails a Claude Code transcript JSONL as it's written and prints token-efficiency
advice MID-session, instead of only after it ends. No AI, no DB writes — pure
incremental analysis of the same transcript the retrospective rules use.

Usage:
    mrtoken-transcript watch [session-id-or-path] [--interval 2] [--once]

With no argument it follows the most recently modified transcript for the
current project. `--once` replays the existing transcript once and exits
(useful for testing / a quick "where am I" check).

Live signals (cheap, incremental, debounced):
  • huge tool output just landed   → offload to a file
  • tool errors clustering         → likely retry loop, stop and re-plan
  • context window getting large   → /compact or fresh handoff
  • cost milestones crossed        → informational ($ is API-equivalent estimate)
"""
from __future__ import annotations
import glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.expanduser("~/.claude/projects")

# live thresholds (default profile; live rules stay deliberately conservative)
HUGE_TOOL_CHARS = 40_000          # ~10k tok
RECENT_ERROR_WINDOW = 8           # last N model calls
RETRY_ERROR_TRIGGER = 3           # errors within window → warn
CONTEXT_WARN_TOKENS = 150_000     # current window size proxy → suggest compaction
# escalating "notable" cost thresholds (USD) — emit once when each is crossed,
# instead of every fixed increment (which spams on expensive sessions)
COST_MILESTONES = [5, 25, 50, 100, 250, 500, 1000, 2000, 5000]

DEBOUNCE_S = {"huge_tool_output": 20, "retry_loop": 60, "context": 120}


def _load_prices():
    from mrtoken.ingest import load_prices, est_cost
    return load_prices(), est_cost


def latest_transcript(cwd: str | None = None) -> str | None:
    cwd = cwd or os.getcwd()
    escaped = cwd.replace("/", "-").replace(".", "-")
    candidates = glob.glob(os.path.join(PROJECTS, escaped, "*.jsonl"))
    if not candidates:
        candidates = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def resolve_path(arg: str | None) -> str | None:
    if arg and os.path.isfile(arg):
        return arg
    if arg:  # treat as session id
        hits = glob.glob(os.path.join(PROJECTS, "*", f"{arg}*.jsonl"))
        if hits:
            return max(hits, key=os.path.getmtime)
    return latest_transcript()


class LiveMonitor:
    """Stateful incremental analyzer. Feed it parsed transcript entries."""

    def __init__(self, emit=print):
        self.emit = emit
        self.prices, self.est_cost = _load_prices()
        self.model_calls = 0
        self.cum_cost = 0.0
        self.errors_recent: list[int] = []   # 1/0 per recent model call
        self.last_emit: dict[str, float] = {}
        self.last_cost_milestone = 0.0
        self.pending_tools: dict[str, str] = {}  # tool_use_id -> tool_name

    def _debounce(self, key: str) -> bool:
        now = time.time()
        if now - self.last_emit.get(key, 0) < DEBOUNCE_S.get(key, 30):
            return False
        self.last_emit[key] = now
        return True

    def feed(self, o: dict) -> None:
        etype = o.get("type")
        msg = o.get("message") if isinstance(o.get("message"), dict) else {}

        if etype == "assistant" and "usage" in msg:
            self.model_calls += 1
            u = msg["usage"]
            self.cum_cost += self.est_cost(self.prices, msg.get("model"), u)

            # context-size proxy: this call's whole input side ≈ current window
            window = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                      + u.get("cache_creation_input_tokens", 0))
            if window >= CONTEXT_WARN_TOKENS and self._debounce("context"):
                self.emit(f"  ℹ context window ~{window//1000}k tokens — consider /compact "
                          "or a fresh session with a handoff summary")

            # cost milestones — escalating ladder, each crossed once
            crossed = [m for m in COST_MILESTONES
                       if self.last_cost_milestone < m <= self.cum_cost]
            if crossed:
                self.last_cost_milestone = crossed[-1]
                self.emit(f"  ℹ session est cost crossed ${crossed[-1]:,} "
                          f"(~${self.cum_cost:,.2f} API-equivalent, not a subscription bill)")

            # register requested tools; record one error slot per call
            had_error = False
            for b in (msg.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    self.pending_tools[b.get("id")] = b.get("name")
            self.errors_recent.append(0)  # placeholder, may flip on tool_result
            if len(self.errors_recent) > RECENT_ERROR_WINDOW:
                self.errors_recent.pop(0)

        elif etype == "user":
            content = msg.get("content") if msg else o.get("content")
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result":
                        continue
                    tuid = b.get("tool_use_id")
                    name = self.pending_tools.pop(tuid, "tool")
                    text = b.get("content", "")
                    chars = len(text) if isinstance(text, str) else len(json.dumps(text))
                    # huge output just landed
                    if chars >= HUGE_TOOL_CHARS and self._debounce("huge_tool_output"):
                        self.emit(f"  ⚠ {name} returned ~{chars//4:,} tok — write large outputs "
                                  "to a file and pass only a compact summary")
                    # error tracking
                    if b.get("is_error"):
                        if self.errors_recent:
                            self.errors_recent[-1] = 1
                        if sum(self.errors_recent) >= RETRY_ERROR_TRIGGER and self._debounce("retry_loop"):
                            self.emit(f"  ⚠ {sum(self.errors_recent)} tool errors in the last "
                                      f"{len(self.errors_recent)} turns — likely a retry loop; "
                                      "stop and re-plan or reduce context")


def _iter_new_lines(path: str, offset: int) -> tuple[list[str], int]:
    size = os.path.getsize(path)
    if size < offset:          # file truncated/rotated
        offset = 0
    with open(path, "r", encoding="utf-8") as fh:
        fh.seek(offset)
        data = fh.read()
        new_offset = fh.tell()
    lines = [ln for ln in data.split("\n") if ln.strip()]
    return lines, new_offset


def watch(arg: str | None = None, interval: float = 2.0, once: bool = False) -> int:
    path = resolve_path(arg)
    if not path:
        print("mrtoken watch: no transcript found for this project", file=sys.stderr)
        return 1

    mon = LiveMonitor()
    print(f"mrtoken watch ▸ {os.path.basename(path)}"
          + ("  (replay)" if once else f"  (every {interval:g}s, ctrl-c to stop)"))

    if once:
        lines, _ = _iter_new_lines(path, 0)
        for ln in lines:
            try:
                mon.feed(json.loads(ln))
            except json.JSONDecodeError:
                pass
        print(f"  — replayed {mon.model_calls} model calls · "
              f"est cost ~${mon.cum_cost:,.2f}")
        return 0

    offset = os.path.getsize(path)  # start at the live tail, ignore history
    try:
        while True:
            lines, offset = _iter_new_lines(path, offset)
            for ln in lines:
                try:
                    mon.feed(json.loads(ln))
                except json.JSONDecodeError:
                    pass
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nmrtoken watch ▸ stopped · {mon.model_calls} calls seen · "
              f"est cost ~${mon.cum_cost:,.2f}")
        return 0
