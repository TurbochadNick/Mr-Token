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
        # profile-aware live thresholds (Eco Mode): classified incrementally
        self.tool_counts: dict[str, int] = {}
        self.bash_out_total = 0
        self.bash_out_n = 0
        self.profile: str | None = None
        self.huge_threshold = HUGE_TOOL_CHARS

    def _reclassify(self) -> None:
        if sum(self.tool_counts.values()) < 4:
            return  # too little signal yet — keep defaults
        from mrtoken.profile import classify_from_counts
        from mrtoken.rules import PROFILE_THRESHOLDS, DEFAULT_THRESHOLDS
        avg = {"bash": (self.bash_out_total / self.bash_out_n) if self.bash_out_n else 0}
        profile, _conf, _sig = classify_from_counts(self.tool_counts, avg)
        prev = self.profile
        self.profile = profile
        self.huge_threshold = PROFILE_THRESHOLDS.get(
            profile, DEFAULT_THRESHOLDS)["huge_tool_chars"]
        if profile != prev:
            self.emit(f"  · profile: {profile} — thresholds calibrated "
                      f"(huge-output ≥ {self.huge_threshold//1000}k tok)")

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
            for b in (msg.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name = b.get("name")
                    self.pending_tools[b.get("id")] = name
                    key = (name or "").lower()
                    self.tool_counts[key] = self.tool_counts.get(key, 0) + 1
            self._reclassify()
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
                    if (name or "").lower() == "bash":
                        self.bash_out_total += chars
                        self.bash_out_n += 1
                    # huge output just landed (profile-aware threshold)
                    if chars >= self.huge_threshold and self._debounce("huge_tool_output"):
                        prof = f" for {self.profile} profile" if self.profile else ""
                        self.emit(f"  ⚠ {name} returned ~{chars//4:,} tok ({self.huge_threshold//1000}k "
                                  f"threshold{prof}) — write large outputs to a file, pass a summary")
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
