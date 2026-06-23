#!/usr/bin/env python3
"""MR Token — validation-corpus intake for shared exports.

Beta testers hand us redacted `mrtoken-transcript export` JSON
(schema `mrtoken.session_summary.v1`). This aggregates one or more of those
files into a combined cost / cache / rule-fire summary so a tester's numbers
can be read alongside our own fleet — without re-deriving anything by hand.

What it CANNOT do: a precision proxy. That needs the full trace (model-call
timestamps, tool linkage) which a shared export does not carry — run
`mrtoken-transcript validate` against the source DB for that. This intake is
honest about the difference. Metadata-only; it never stores raw content.
"""
from __future__ import annotations
import json

from mrtoken.ingest import MIN_ACTIVITY

SCHEMA = "mrtoken.session_summary.v1"


def _is_low_activity(session: dict) -> bool:
    """Honor an explicit is_low_activity flag; fall back to model_calls for
    pre-1.1 exports (e.g. a 0.4.1 tester file) that predate the flag."""
    flag = session.get("is_low_activity")
    if flag is not None:
        return bool(flag)
    return (session.get("model_calls") or 0) < MIN_ACTIVITY["model_calls"]


def load_export(path: str) -> dict:
    """Parse one v1 export file. Raises ValueError with a readable reason on any
    problem (missing file, bad JSON, wrong/absent schema) so the caller can
    report-and-skip rather than crash."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise ValueError("file not found")
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"not readable JSON ({e})")
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} export (schema={doc.get('schema') if isinstance(doc, dict) else '?'})")
    if not isinstance(doc.get("sessions"), list):
        raise ValueError("missing 'sessions' array")
    return doc


def summarize_exports(paths: list[str]) -> dict:
    """Aggregate the given export files. Files that fail to load are recorded in
    `errors` and skipped; the rest are combined."""
    agg = {
        "files": 0, "errors": [], "tool_versions": set(),
        "sessions": 0, "low_activity": 0,
        "total_tokens": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "est_cost_usd": 0.0, "est_savings_tokens": 0,
        "rule_fires": {},  # rule -> {severity: count}
    }
    for path in paths:
        try:
            doc = load_export(path)
        except ValueError as e:
            agg["errors"].append({"file": path, "reason": str(e)})
            continue
        agg["files"] += 1
        if doc.get("tool_version"):
            agg["tool_versions"].add(doc["tool_version"])
        for s in doc["sessions"]:
            if _is_low_activity(s):
                agg["low_activity"] += 1
                continue  # mirror fleet: low-activity stubs don't count as sessions
            agg["sessions"] += 1
            agg["total_tokens"] += s.get("total_tokens") or 0
            agg["input_tokens"] += s.get("input_tokens") or 0
            agg["output_tokens"] += s.get("output_tokens") or 0
            agg["cache_read_tokens"] += s.get("cache_read_tokens") or 0
            agg["cache_write_tokens"] += s.get("cache_write_tokens") or 0
            agg["est_cost_usd"] += s.get("est_cost_usd") or 0.0
            for rec in s.get("recommendations") or []:
                by_sev = agg["rule_fires"].setdefault(rec.get("rule", "?"), {})
                sev = rec.get("severity", "?")
                by_sev[sev] = by_sev.get(sev, 0) + 1
                agg["est_savings_tokens"] += rec.get("est_savings_tokens") or 0

    cache_base = agg["input_tokens"] + agg["cache_read_tokens"] + agg["cache_write_tokens"]
    agg["cache_hit_ratio"] = round(agg["cache_read_tokens"] / cache_base, 4) if cache_base else None
    agg["tool_versions"] = sorted(agg["tool_versions"])
    return agg


def print_corpus_report(agg: dict) -> None:
    print(f"\n{'─'*60}")
    print("  MR Token — validation corpus  (aggregated from shared exports)")
    print(f"{'─'*60}")
    if agg["errors"]:
        for e in agg["errors"]:
            print(f"  ⚠ skipped {e['file']}: {e['reason']}")
        print(f"{'─'*60}")
    vers = ", ".join(agg["tool_versions"]) or "?"
    print(f"  files combined    {agg['files']:>12}   (tool versions: {vers})")
    print(f"  sessions          {agg['sessions']:>12,}")
    if agg["low_activity"]:
        print(f"  low-activity      {agg['low_activity']:>12,}  (excluded)")
    print(f"  total tokens      {agg['total_tokens']:>12,}")
    print(f"  est cost (API-eq) {'$'+format(agg['est_cost_usd'], ',.2f'):>12}   ⚠ not a real bill")
    if agg["cache_hit_ratio"] is not None:
        print(f"  cache hit ratio   {agg['cache_hit_ratio']:>11.1%}")
    print(f"{'─'*60}")
    if agg["rule_fires"]:
        print("  rule fires (NOT a precision proxy — run `validate` on the source DB):")
        order = {"high": 0, "warn": 1}
        for rule, sevs in sorted(agg["rule_fires"].items(),
                                 key=lambda kv: -sum(kv[1].values())):
            parts = ", ".join(f"{n} {sev}" for sev, n in
                              sorted(sevs.items(), key=lambda kv: order.get(kv[0], 9)))
            print(f"    {rule:24} ×{sum(sevs.values()):<4} ({parts})")
        if agg["est_savings_tokens"]:
            print(f"\n  est. addressable savings: ~{agg['est_savings_tokens']:,} tokens")
    else:
        print("  no recommendations in these exports")
    print(f"{'─'*60}\n")
