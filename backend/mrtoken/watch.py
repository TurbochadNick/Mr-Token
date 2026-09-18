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
  • same target re-read 3×+        → keep the first result, read ranges not files
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
# context warning is window-aware (see statusline.context_window): warn at
# CONTEXT_WARN_PCT% of the inferred window, so a 1M-context session isn't told to
# compact at 150k the way a fixed token floor would.
from mrtoken.statusline import context_window, CONTEXT_WARN_PCT
# escalating "notable" cost thresholds (USD) — emit once when each is crossed,
# instead of every fixed increment (which spams on expensive sessions)
COST_MILESTONES = [5, 25, 50, 100, 250, 500, 1000, 2000, 5000]

DEBOUNCE_S = {"huge_tool_output": 20, "retry_loop": 60, "context": 120,
              "re_read_loop": 90}  # re-reads accumulate slowly — don't spam

# COMPACTION-GATE Gate 1 (disposability): a read target untouched for at least
# this many model responses is presumed disposable (safe to drop); anything
# accessed more recently — or that tripped the re-read trigger — is load-bearing.
K_DISPOSABLE_TURNS = 5

# COMPACTION-GATE Gate 2 (runway): tools whose use means durable artifacts are
# landing — one input to the near-done proxy. Names only, never content.
WRITE_TOOLS = {"edit", "write", "multiedit", "notebookedit"}


def _load_prices():
    from mrtoken.ingest import load_prices, est_cost
    return load_prices(), est_cost


def valid_session_id(c) -> bool:
    """A session id is exactly ONE safe path component: a non-empty string, not '.'/'..',
    no separator or NUL, not absolute. Canonical copy; `intervene` imports it from here
    (intervene imports watch, so this direction is the non-circular one).

    NOTE this deliberately does NOT reject glob metacharacters. Rejecting them would break
    literal ids that legitimately contain one; instead every caller runs the identifier
    through `glob.escape`, which is the smaller semantic change. See `_one_transcript`.
    """
    return (isinstance(c, str) and c not in ("", ".", "..")
            and "/" not in c and "\\" not in c and "\x00" not in c
            and not os.path.isabs(c))


# How many leading lines of a transcript to scan for its recorded `cwd`.
_BUCKET_SCAN_LINES = 40


def _legacy_bucket_name(cwd: str) -> str:
    """The historical COMPUTED name, kept ONLY as a cheap first candidate to try — it is
    always verified against a transcript's recorded cwd before being returned, and never
    used as a fallback. It is wrong twice over: it does not map '_' to '-' as the harness
    does, and it is not injective ('/a/b.c' and '/a/b-c' collide on '-a-b-c')."""
    return cwd.replace("/", "-").replace(".", "-")


def _transcript_cwd(path: str) -> str | None:
    """The working directory a transcript records for ITSELF, or None."""
    try:
        with open(path, errors="replace") as fh:
            for _ in range(_BUCKET_SCAN_LINES):
                line = fh.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                cwd = obj.get("cwd") if isinstance(obj, dict) else None
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        return None
    return None


def project_bucket(cwd: str | None = None) -> str | None:
    """DISCOVER the transcript bucket that belongs to `cwd`, or None.

    Deliberately not a string substitution. The harness escapes project paths into
    directory names by a rule we do not own — it replaces '_' as well as '/' and '.', which
    the old formula missed, so it silently searched a bucket that does not exist and
    project-local resolution was dead for every underscore path, including this repo.

    A transcript records its own `cwd` verbatim, so matching on that is exact and carries no
    assumption about escaping. The computed name is tried first only as a fast candidate and
    is VERIFIED before it is returned. If the harness changes its escaping again this
    degrades to NOT-FOUND, never to the wrong bucket.
    """
    target = os.path.realpath(cwd or os.getcwd())
    legacy = _legacy_bucket_name(target)
    seen = set()
    for name in [legacy] + sorted(os.listdir(PROJECTS)) if os.path.isdir(PROJECTS) else [legacy]:
        if name in seen:
            continue
        seen.add(name)
        d = os.path.join(PROJECTS, name)
        if not os.path.isdir(d):
            continue
        for t in sorted(glob.glob(os.path.join(glob.escape(d), "*.jsonl")),
                        key=os.path.getmtime, reverse=True)[:3]:
            rec = _transcript_cwd(t)
            if rec and os.path.realpath(rec) == target:
                return name
    # No fallback to the computed name. It is NOT collision-free: '.' and '-' both map to
    # '-', so '/a/b.c' and '/a/b-c' compute to the SAME bucket — the fallback could hand
    # back another project's transcripts, the exact exposure this resolver exists to close.
    # And it protects nothing: every transcript on a real host records a cwd (108 of 108
    # checked), so an undiscoverable bucket means there is genuinely nothing to bind.
    return None


def _one_transcript(bucket_glob: str, sid: str) -> str | None:
    """Exactly one transcript for `sid` under `bucket_glob`, else None.

    `sid` is ALWAYS glob-escaped. Unescaped, an identifier is executable syntax: `*`,
    `?` and `[...]` are interpolated straight into the pattern, so an "id" of `*` matches
    every transcript and resolves one — neither an id nor a prefix. Exact name first, then
    prefix; MORE THAN ONE match returns None and is never broken by mtime.
    """
    esc = glob.escape(sid)
    exact = glob.glob(os.path.join(PROJECTS, bucket_glob, f"{esc}.jsonl"))
    hits = exact or glob.glob(os.path.join(PROJECTS, bucket_glob, f"{esc}*.jsonl"))
    return hits[0] if len(hits) == 1 else None


def resolve_session(sid) -> str | None:
    """TRUSTED id lookup (host/CLI): strict, but searches every project bucket.

    Uniqueness is not workspace binding — do NOT use this for a tool-caller-supplied id;
    use `resolve_session_local`.
    """
    return _one_transcript("*", sid) if valid_session_id(sid) else None


def resolve_session_local(sid, cwd: str | None = None) -> str | None:
    """UNTRUSTED entry point: resolve a TOOL-CALLER-supplied session id, project-locally.

    Searches ONLY the current project's bucket. An exactly-one-match across all projects is
    uniqueness, not caller-workspace binding: a foreign seat's exact session id would
    otherwise resolve, and `build_handoff` returns transcript CONTENT. Fails closed on an
    unsafe id, no match, or more than one match, and never accepts a filesystem path.
    """
    if not valid_session_id(sid):
        return None
    bucket = project_bucket(cwd)
    if bucket is None:                    # no bucket belongs to this cwd -> fail closed
        return None
    return _one_transcript(glob.escape(bucket), sid)


def resolve_local_default(cwd: str | None = None) -> str | None:
    """The caller-project default transcript for an UNTRUSTED caller that supplied no id.

    Absent-key was treated as the safe default everywhere, but it was the one tool-reachable
    route into the TRUSTED resolver: `build_handoff(None, None)` -> `resolve_path(None)` ->
    `latest_transcript()`, which consults MRTOKEN_SESSION / CLAUDE_CODE_SESSION_ID through the
    GLOBAL `resolve_session` and so could bind another project's transcript. An untrusted
    caller must never reach that path.

    An environment id is constrained to THIS project; with none, the newest transcript in
    this project's bucket, preserving the previous local-newest semantics.
    """
    sid = os.environ.get("MRTOKEN_SESSION") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if sid:
        return resolve_session_local(sid, cwd)
    bucket = project_bucket(cwd)
    if not bucket:
        return None
    hits = glob.glob(os.path.join(PROJECTS, glob.escape(bucket), "*.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


def latest_transcript(cwd: str | None = None) -> str | None:
    # The CURRENT session wins, even if another agent's transcript was written
    # more recently. This is the multi-agent / K2 case: newest-mtime-across-all
    # would otherwise grab a different agent's session. CLAUDE_CODE_SESSION_ID is
    # set by Claude Code for CLI commands; MRTOKEN_SESSION overrides it.
    sid = os.environ.get("MRTOKEN_SESSION") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if sid:
        # An env id that is missing, ambiguous or malformed resolves to NOTHING. Falling
        # through to cwd-newest here meant a bad id silently produced a different session.
        return resolve_session(sid)
    cwd = cwd or os.getcwd()
    bucket = project_bucket(cwd)
    candidates = glob.glob(os.path.join(PROJECTS, glob.escape(bucket), "*.jsonl")) if bucket else []
    if candidates:
        return max(candidates, key=os.path.getmtime)
    # Cross-project last resort: EXPLICITLY GATED, default OFF. On a multi-seat host
    # "newest across all projects" can select ANOTHER SEAT'S transcript.
    if os.environ.get("MRTOKEN_ALLOW_CROSS_PROJECT", "").strip().lower() not in (
            "1", "true", "yes", "on"):
        return None
    candidates = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    return max(candidates, key=os.path.getmtime) if candidates else None


def resolve_path(arg: str | None) -> str | None:
    """TRUSTED entry point — host- and CLI-supplied transcript PATHS and ids.

    Kept deliberately separate from `resolve_session_local`. Trust is a property of the
    ENTRY POINT, not of how a string is spelled: an earlier attempt to tell them apart by
    filename suffix rejected `/etc/passwd` by spelling while still accepting a `.jsonl`
    SYMLINK to a private file. Untrusted callers no longer reach this function at all.
    """
    if arg and os.path.isfile(arg):
        return arg
    if arg:
        return resolve_session(arg)
    return latest_transcript()


class LiveMonitor:
    """Stateful incremental analyzer. Feed it parsed transcript entries."""

    def __init__(self, emit=print):
        self.emit = emit
        self.prices, self.est_cost = _load_prices()
        self.model_calls = 0
        self.cum_cost = 0.0
        self._seen_msg_ids: set[str] = set()  # dedup usage per API response (msg.id)
        self._ctx_history: list[int] = []     # recent per-response context sizes (trajectory)
        self.errors_recent: list[int] = []   # 1/0 per recent model call
        self.writes_recent: list[int] = []   # 1/0 per recent call: did it edit/write?
        self.last_emit: dict[str, float] = {}
        self.last_cost_milestone = 0.0
        self.pending_tools: dict[str, str] = {}  # tool_use_id -> tool_name
        # profile-aware live thresholds (Eco Mode): classified incrementally
        self.tool_counts: dict[str, int] = {}
        self.bash_out_total = 0
        self.bash_out_n = 0
        self.profile: str | None = None
        self.huge_threshold = HUGE_TOOL_CHARS
        # structured state for statusline / snapshot consumers
        self._context_now: int = 0
        self._context_max: int = 0   # ratchets up; window is inferred from this so
                                     # ctx% never flips back after a compaction dip
        self.signals_fired: list[str] = []  # rule keys that fired, in order
        # re-read tracking — privacy-clean, mirrors the retrospective re_read_loop
        # rule: identical read input → identical hash, so we count duplicate
        # (tool, input_hash) groups live without ever storing a path.
        from mrtoken.ingest import sha as _sha
        from mrtoken.rules import READ_TOOLS, RE_READ_TRIGGER
        self._sha = _sha
        self._read_tools = READ_TOOLS
        self._re_read_trigger = RE_READ_TRIGGER
        self.pending_read_hash: dict[str, tuple[str, str]] = {}  # tool_use_id -> (tool, hash)
        self.read_groups: dict[tuple[str, str], dict] = {}       # (tool, hash) -> counters

    def _reclassify(self) -> None:
        if sum(self.tool_counts.values()) < 4:
            return  # too little signal yet — keep defaults
        from mrtoken.profile import classify_from_counts
        from mrtoken.rules import PROFILE_THRESHOLDS, DEFAULT_THRESHOLDS
        avg = {"bash": (self.bash_out_total / self.bash_out_n) if self.bash_out_n else 0}
        profile, _conf, _sig = classify_from_counts(self.tool_counts, avg)
        prev = self.profile
        # stickiness: once a session shows strong intent (edits → code, orchestration
        # → agent), don't DOWNGRADE to benchmark/research just because bash/reads later
        # dominate — that caused the mid-session profile flip the HUD showed.
        if prev in ("code", "agent") and profile in ("benchmark", "research"):
            profile = prev
        self.profile = profile
        self.huge_threshold = PROFILE_THRESHOLDS.get(
            profile, DEFAULT_THRESHOLDS)["huge_tool_chars"]
        if profile != prev:
            self.emit(f"  · profile: {profile} — thresholds calibrated "
                      f"(huge-output ≥ {self.huge_threshold//1000}k tok)")

    def _track_read(self, block: dict, key: str) -> None:
        """Count repeated reads of the same target and warn on the Nth one.
        Fires when the same read is *requested* RE_READ_TRIGGER times — the
        timeliest moment to nudge, before paying for yet another identical result.
        Wasted-token estimate uses the already-completed identical reads."""
        if key not in self._read_tools:
            return
        h = self._sha(json.dumps(block.get("input", {})))
        self.pending_read_hash[block.get("id")] = (key, h)
        g = self.read_groups.setdefault((key, h), {"req": 0, "done": 0, "out_tok": 0})
        g["req"] += 1
        # per-block recency for the disposability gate — call indices only
        # (mirrors context_block.first_seen/last_seen on the ingest side)
        g.setdefault("first_call", self.model_calls)
        g["last_call"] = self.model_calls
        if g["req"] >= self._re_read_trigger and self._debounce("re_read_loop"):
            self.signals_fired.append("re_read_loop")
            redundant = g["req"] - 1
            avg = (g["out_tok"] / g["done"]) if g["done"] else 0
            wasted = int(redundant * avg)
            wtok = f", ~{wasted:,} tok re-paid into context" if wasted else ""
            self.emit(f"  ⚠ re-read the same {key} target {g['req']}× "
                      f"({redundant} redundant{wtok}) — read once and keep the "
                      "result, or read targeted ranges instead of whole files")

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
            # Claude Code writes multiple transcript lines per API response, each
            # REPEATING the same usage. Count cost/calls/context ONCE per message
            # id, else the live HUD inflates ~2x and disagrees with `status`.
            # Tool_use blocks are split across those lines, so scan them every line.
            mid = msg.get("id")
            dedup_key = mid or o.get("uuid")  # fall back to line uuid when id absent
            new_response = dedup_key is None or dedup_key not in self._seen_msg_ids
            if dedup_key is not None and new_response:
                self._seen_msg_ids.add(dedup_key)

            if new_response:
                self.model_calls += 1
                u = msg["usage"]
                self.cum_cost += self.est_cost(self.prices, msg.get("model"), u)

                # context-size proxy: this call's whole input side ≈ current window
                window = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                          + u.get("cache_creation_input_tokens", 0))
                self._context_now = window
                self._context_max = max(self._context_max, window)
                self._ctx_history.append(window)
                self._ctx_history = self._ctx_history[-12:]  # recent trajectory
                win = context_window(self._context_max)   # sticky window (ratchets up)
                if window >= win * CONTEXT_WARN_PCT / 100 and self._debounce("context"):
                    self.signals_fired.append("context")
                    self.emit(f"  ℹ context window ~{window//1000}k tokens ({int(window/win*100)}%) — "
                              "consider /compact or a fresh session with a handoff summary")

                # cost milestones — escalating ladder, each crossed once
                crossed = [m for m in COST_MILESTONES
                           if self.last_cost_milestone < m <= self.cum_cost]
                if crossed:
                    self.last_cost_milestone = crossed[-1]
                    self.emit(f"  ℹ session est cost crossed ${crossed[-1]:,} "
                              f"(~${self.cum_cost:,.2f} API-equivalent, not a subscription bill)")

                self.errors_recent.append(0)  # one slot per response; may flip on tool_result
                if len(self.errors_recent) > RECENT_ERROR_WINDOW:
                    self.errors_recent.pop(0)
                self.writes_recent.append(0)  # flips below if this response edits/writes
                if len(self.writes_recent) > RECENT_ERROR_WINDOW:
                    self.writes_recent.pop(0)

            # register requested tools (blocks are split across the response's lines)
            for b in (msg.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    name = b.get("name")
                    self.pending_tools[b.get("id")] = name
                    key = (name or "").lower()
                    self.tool_counts[key] = self.tool_counts.get(key, 0) + 1
                    if key in WRITE_TOOLS and self.writes_recent:
                        self.writes_recent[-1] = 1
                    self._track_read(b, key)
            self._reclassify()

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
                    # a read completed — credit its output tokens to its re-read group
                    rh = self.pending_read_hash.pop(tuid, None)
                    if rh is not None:
                        g = self.read_groups.setdefault(rh, {"req": 0, "done": 0, "out_tok": 0})
                        g["done"] += 1
                        g["out_tok"] += chars // 4
                    # huge output just landed (profile-aware threshold)
                    if chars >= self.huge_threshold and self._debounce("huge_tool_output"):
                        prof = f" for {self.profile} profile" if self.profile else ""
                        self.signals_fired.append("huge_tool_output")
                        self.emit(f"  ⚠ {name} returned ~{chars//4:,} tok ({self.huge_threshold//1000}k "
                                  f"threshold{prof}) — write large outputs to a file, pass a summary")
                    # error tracking
                    if b.get("is_error"):
                        if self.errors_recent:
                            self.errors_recent[-1] = 1
                        if sum(self.errors_recent) >= RETRY_ERROR_TRIGGER and self._debounce("retry_loop"):
                            self.signals_fired.append("retry_loop")
                            self.emit(f"  ⚠ {sum(self.errors_recent)} tool errors in the last "
                                      f"{len(self.errors_recent)} turns — likely a retry loop; "
                                      "stop and re-plan or reduce context")


    def _turns_to_warn(self) -> int | None:
        """Projected responses until context reaches the warn threshold, at the
        recent growth rate — the lead-time nudge ('act before you hit the wall').
        None if too little data, not climbing, or already past the threshold."""
        hist = self._ctx_history
        if len(hist) < 4:
            return None
        cur = hist[-1]
        warn = context_window(self._context_max) * CONTEXT_WARN_PCT / 100
        if cur >= warn:
            return None  # already at/over warn — the 'context' signal covers it
        recent = hist[-6:]
        rate = (recent[-1] - recent[0]) / (len(recent) - 1)
        if rate <= 0:
            return None  # flat or shrinking — no imminent wall
        return max(1, round((warn - cur) / rate))

    def disposability(self) -> dict[str, str]:
        """Per-read-target disposability (COMPACTION-GATE Gate 1). Hash-keyed
        metadata only — never content. A completed target is load-bearing when it
        tripped the re-read trigger or was accessed within K_DISPOSABLE_TURNS
        responses; only a target untouched at least that long is disposable."""
        out: dict[str, str] = {}
        for (tool, h), g in self.read_groups.items():
            if not g.get("done"):
                continue  # never completed — nothing of it sits in context
            since = self.model_calls - g.get("last_call", self.model_calls)
            load_bearing = (g["req"] >= self._re_read_trigger
                            or since < K_DISPOSABLE_TURNS)
            out[f"{tool}:{h[:12]}"] = "load_bearing" if load_bearing else "disposable"
        return out

    def progress(self) -> dict:
        """Recent-turn progress metadata for the runway proxy (COMPACTION-GATE
        Gate 2). Error flags come from tool_result.is_error (exit status — the
        closest metadata-only stand-in for tests going red→green); writes are
        tool names only. Never content."""
        errs = self.errors_recent
        half = len(errs) // 2
        return {
            "calls": self.model_calls,
            "window": len(errs),
            "errors_first_half": sum(errs[:half]) if half else None,
            "errors_second_half": sum(errs[half:]) if half else None,
            "recent_writes": sum(self.writes_recent),
        }

    def snapshot(self) -> dict:
        """Return current monitor state (for statusline and other consumers)."""
        return {
            "model_calls": self.model_calls,
            "cum_cost": self.cum_cost,
            "profile": self.profile,
            "context_now": self._context_now,
            "context_max": self._context_max,
            "turns_to_warn": self._turns_to_warn(),
            "signals_fired": list(self.signals_fired),
            "disposability": self.disposability(),
            "progress": self.progress(),
        }


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
