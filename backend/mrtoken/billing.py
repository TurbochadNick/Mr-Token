"""Conservative billing and cumulative-token evidence from provider session records.

Only a literal ``usage.billing_mode`` of ``api`` or ``subscription`` is positive
billing evidence.  A matching mode on every recorded call classifies a session;
anything absent, mixed, or unrecognised is ``unknown``.  This does not prove an
invoice, entitlement, settlement, or dollar spend.

Claude computed cumulative token totals use the provider's published accounting
equation for input, cache read, and cache write components:
https://platform.claude.com/docs/en/build-with-claude/prompt-caching
That source supports component disjointness for token arithmetic; it does not
prove API billing, a per-session provider total, or realized cost.
"""
from __future__ import annotations

BILLING_MODES = ("api", "subscription")


def observed_billing_mode(usage: dict) -> str | None:
    value = usage.get("billing_mode")
    return value if value in BILLING_MODES else None


def reported_total_tokens(usage: dict) -> int | None:
    value = usage.get("total_tokens")
    return value if isinstance(value, int) and value >= 0 else None
