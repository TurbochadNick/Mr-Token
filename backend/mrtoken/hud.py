"""Provider-neutral HUD fields, and the one-line terminal view over them.

Every surface (the Claude statusLine, the Codex Stop-hook message, a future verbose
plain-text view) renders the SAME fields, so a surface is a formatter, not a
reimplementation. Each field carries:
  value       the number or label
  state       OK (derived), UNKNOWN (applies but not derivable here), NA (does
              not apply to this account)
  alert       whether the value is in its warning band, decided HERE, once
  provenance  where the value comes from. The terminal line drops it for width;
              a richer surface shows it. Dropping it is a rendering choice, so it
              must exist in the data.
  reason      for UNKNOWN, why it could not be derived ("provider total did not
              reconcile"). Saying what we do not know, and why, is the point.

UNKNOWN versus NA: UNKNOWN is a field a knowledgeable user would expect here that
we could not derive (terse view: "?"). NA is a field that does not exist for this
provider or account (omitted). Rendering NA as "?" implies a value that never
existed.

Every output is PLAIN TEXT: alignment and whitespace are the only structure (no
markdown, no ANSI-dependent layout), so nothing degrades into visible syntax.

The attribution block ("mr <version>") says who produced the claim and which code:
MR Token writes into surfaces it does not own, beside the harness's own text. Every
formatter leads with it and it is never trimmed for width; a multi-line view uses it
once, as the block header, not on every row.

No dollar field exists: no provider record carries billing_mode, and the price
table is unverified against any bill (backend/docs/ACCURACY-VALIDATION-2026-09-23.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

OK, UNKNOWN, NA = "ok", "unknown", "na"
PREFIX = "mr"
CONTEXT_WARN_PCT = 70        # the value statusline.py and on_stop.py already used
SHORT_WINDOW_WARN_PCT = 85   # windows under a day (e.g. 5h), as the old 5h segment warned
LONG_WINDOW_WARN_PCT = 80    # windows of a day or more (e.g. 7d), as the old weekly segment warned


@dataclass
class Field:
    value: object = None
    state: str = UNKNOWN
    provenance: str | None = None
    alert: bool = False
    reason: str | None = None
    estimate: object = None  # an UNMEASURED guess, for a view that labels it; never rendered as a value


def known(value, provenance=None, alert=False) -> Field:
    return Field(value, OK, provenance, alert)


def unknown(reason: str, estimate=None) -> Field:
    return Field(state=UNKNOWN, reason=reason, estimate=estimate)


def not_applicable() -> Field:
    return Field(state=NA)


@dataclass
class HudFields:
    # identity
    model: Field = field(default_factory=Field)
    context_window: Field = field(default_factory=Field)   # tokens; makes ctx % interpretable
    effort: Field = field(default_factory=Field)
    # consumption
    ctx_pct: Field = field(default_factory=Field)
    ctx_turns_to_warn: Field = field(default_factory=not_applicable)
    total_tokens: Field = field(default_factory=Field)     # cumulative token total
    cache_ratio: Field = field(default_factory=Field)      # cache read / input side
    # limit
    limiter: Field = field(default_factory=not_applicable)  # {"label", "used_pct", "window_minutes"}
    # context and recommendations
    profile: Field = field(default_factory=not_applicable)  # in the data; not on the terse line (Zach: redundant)
    recommendation: Field = field(default_factory=not_applicable)


# The terse line, in order. Warnings render ONCE, in the recommendation slot, never inline
# (a field still carries its alert in the data; a verbose view may show it inline).
# "tok" is TOTAL expenditure, marked "~" as an estimate. A field that cannot render
# honestly in the width comes OFF this line; it is never abbreviated into a different quantity.
TERSE_FIELDS = ("identity", "effort", "ctx", "tokens", "cache", "limiter", "recommendation")
# When the width forces fields out, they go in this order: cache (derivable), then the
# window size and effort (static within a session: once seen, known), then ctx % (changes
# constantly). NEVER dropped: the attribution block, total tokens and the limit (the two
# most-read fields), and the warning. A window omitted for width is a rendering choice;
# an UNMEASURED window is a state (UNKNOWN), and the two are never conflated.
DROP_ORDER = ("cache", "window", "effort", "ctx")
_EFFORT_SHORT = {"medium": "med"}


def recommend(f: HudFields) -> HudFields:
    """Fill the recommendation slot ONLY from direct readouts of measured state: context
    fullness, and a limit window near binding. Rules-engine verdicts are NOT fed in; they
    were shown not to discriminate (ACCURACY-VALIDATION-2026-09-23.md)."""
    notes = []
    if f.ctx_pct.state == OK and f.ctx_pct.alert:
        notes.append(("compact soon", f"context used >= {CONTEXT_WARN_PCT}% of the window"))
    if f.limiter.state == OK and f.limiter.alert:
        notes.append((f"{f.limiter.value['label']} limit near", "rate limit window near its cap"))
    f.recommendation = (known(", ".join(n for n, _ in notes), "; ".join(p for _, p in notes))
                        if notes else not_applicable())
    return f


def ctx_field(pct, provenance) -> Field:
    return known(pct, provenance, alert=pct >= CONTEXT_WARN_PCT)


def window_label(minutes: int) -> str:
    """A limit window named by its real duration: 300 -> '5h', 10080 -> '7d'."""
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def binding_limiter(windows, provenance) -> Field:
    """The reported window closest to binding (highest used %), labelled by its real
    duration. NA when the account reports none: nothing applies, which is not zero."""
    reported = [(int(m), int(p)) for m, p in windows if m and p is not None]
    if not reported:
        return not_applicable()
    minutes, pct = max(reported, key=lambda w: w[1])
    warn = LONG_WINDOW_WARN_PCT if minutes >= 1440 else SHORT_WINDOW_WARN_PCT
    return known({"label": window_label(minutes), "used_pct": pct, "window_minutes": minutes},
                 provenance, alert=pct >= warn)


def fmt_tokens(tokens) -> str:
    # moved verbatim from hooks/on_stop.py _fmt_token_count
    n = int(tokens or 0)
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M".replace(".0M", "M")
    if n >= 100_000:
        return f"{round(n / 1_000):,}k"
    if n >= 10_000:
        v = n / 1_000
        return f"{v:.1f}k".replace(".0k", "k")
    return f"{n:,}"


def _window_text(tokens: int) -> str:
    if tokens >= 1_000_000 and tokens % 1_000_000 == 0:
        return f"{tokens // 1_000_000}M"
    return fmt_tokens(tokens)


def attribution() -> str:
    """'mr <version>': who produced the line and which code. One non-droppable block.
    The version is the RUNNING code's own __version__ (with an editable install the
    dist-info is stamped at install time and can lag the tree). Unknown -> 'mr ?',
    because an unknown version is itself the answer to "is this current"."""
    try:
        from mrtoken import __version__
        return f"{PREFIX} {__version__}" if __version__ else f"{PREFIX} ?"
    except Exception:
        return f"{PREFIX} ?"


def format_line(f: HudFields, width: int | None = None) -> str:
    """Terse view: PREFIX, then TERSE_FIELDS in order, ' · '-joined. UNKNOWN renders as
    '?'; NA is omitted. If width is given and the line is longer, fields leave in
    DROP_ORDER until it fits; the prefix and recommendation are never dropped."""
    dropped: set[str] = set()

    return _render_terse(f, TERSE_FIELDS, width)


# Codex surface: the per-turn Stop message goes INTO the model conversation, so every
# character costs context tokens every turn. The Codex CLI's own line already shows
# model and effort persistently, so they are not repeated; the window rides on ctx.
CODEX_STOP_FIELDS = ("ctx_of_window", "tokens", "cache", "limiter", "recommendation")


def format_codex_stop(f: HudFields) -> str:
    return _render_terse(f, CODEX_STOP_FIELDS, None)


def _render_terse(f: HudFields, fields, width) -> str:
    dropped: set[str] = set()

    def render() -> str:
        parts = [attribution()]
        for name in fields:
            if name in dropped:
                continue
            seg = _SEGMENTS[name](f, "window" not in dropped)
            if seg:
                parts.append(seg)
        return " · ".join(parts)

    line = render()
    for name in DROP_ORDER:
        if width is None or len(line) <= width:
            break
        dropped.add(name)
        line = render()
    return line


def _identity(f, show_window):
    ident = f.model.value if f.model.state == OK else "model ?"
    if show_window and f.context_window.state == OK:
        ident += f" {_window_text(f.context_window.value)}"
    return ident


def _effort(f, _):
    if f.effort.state == OK:
        return _EFFORT_SHORT.get(f.effort.value, f.effort.value)
    return "effort ?" if f.effort.state == UNKNOWN else None


def _limiter(f, _):
    # Every budget percentage on the line is % USED (one direction, learnable once), and
    # says so: providers report used (Claude used_percentage, Codex used_percent).
    if f.limiter.state != OK:
        return None
    return f"{f.limiter.value['label']} {f.limiter.value['used_pct']}% used"


_SEGMENTS = {
    "identity": _identity,
    "effort": _effort,
    # ctx % is USED of the window, and says so: not "left until auto-compact", a different quantity
    "ctx": lambda f, _: f"ctx {f.ctx_pct.value}% used" if f.ctx_pct.state == OK else "ctx ?",
    "ctx_of_window": lambda f, _: (f"ctx {f.ctx_pct.value}% used" + (f" of {_window_text(f.context_window.value)}"
                                   if f.context_window.state == OK else "")) if f.ctx_pct.state == OK else "ctx ?",
    "tokens": lambda f, _: f"~{fmt_tokens(f.total_tokens.value)} tok" if f.total_tokens.state == OK else "tok ?",
    # a hit RATE, not consumption like the other percentages: labelled so it cannot be
    # read as one (the line states numbers; consequence lives only in the warning slot)
    "cache": lambda f, _: f"cache hit {f.cache_ratio.value:.0%}" if f.cache_ratio.state == OK else "cache hit ?",
    "limiter": _limiter,
    "profile": lambda f, _: f.profile.value if f.profile.state == OK else None,
    "recommendation": lambda f, _: f"⚠ {f.recommendation.value}" if f.recommendation.state == OK else None,
}

def codex_hud_fields(usage: dict, profile=None) -> HudFields:
    """Fields for a Codex session from its live rollout (ingest_codex.codex_usage_snapshot).
    Every consumption number comes from the provider's own record, as the Claude
    fields come from the live transcript; only the profile label comes from the store."""
    u = usage or {}
    f = HudFields()
    f.model = known(u["model"], "rollout turn_context") if u.get("model") else unknown("no model in the rollout")
    f.effort = known(u["effort"], "rollout turn_context") if u.get("effort") else unknown("no effort in the rollout")
    window = u.get("context_window")
    f.context_window = known(window, "provider-reported model_context_window") if window else not_applicable()
    if u.get("ctx_pct") is not None:
        f.ctx_pct = ctx_field(u["ctx_pct"], "latest input side / provider-reported window")
    else:
        f.ctx_pct = unknown("no context window reported" if not window else "no token count yet")
    tot = u.get("provider_total") or {}
    t, i, o = tot.get("total"), tot.get("input"), tot.get("output")
    if t is None:
        f.total_tokens = unknown("provider reported no running total")
    elif i is None or o is None or t != i + o:
        f.total_tokens = unknown("provider total did not reconcile (in + out != total)")
    else:
        f.total_tokens = known(t, "provider-reported running total (total_token_usage)")
    cached = tot.get("cached")
    if not i:
        f.cache_ratio = unknown("provider reported no input yet")
    elif cached is None:
        f.cache_ratio = unknown("provider reported no cached-input count")
    else:
        f.cache_ratio = known(cached / i, "cached / input, provider-reported running total")
    f.limiter = binding_limiter(u.get("rate_windows") or [], "provider-reported rate limit window")
    f.profile = known(profile, "session profile") if profile else not_applicable()
    return recommend(f)
