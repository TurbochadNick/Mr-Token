#!/usr/bin/env python3
"""MR Token beta evidence intake.

Beta testers return two JSON shapes:
- `mrtoken.session_summary.v1` from `export --redact`
- `mrtoken.doctor.bundle.v1` from `doctor --bundle`

This module combines both into a maintainer-facing summary. It stays metadata
only and does not require raw transcripts.
"""
from __future__ import annotations
import json

from mrtoken.corpus import summarize_exports

EXPORT_SCHEMA = "mrtoken.session_summary.v1"
DOCTOR_SCHEMA = "mrtoken.doctor.bundle.v1"


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except FileNotFoundError:
        raise ValueError("file not found")
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"not readable JSON ({e})")
    if not isinstance(doc, dict):
        raise ValueError("top-level JSON is not an object")
    return doc


def _summarize_doctors(docs: list[dict]) -> dict:
    out = {
        "files": len(docs),
        "ok": 0,
        "failures": 0,
        "warnings": 0,
        "versions": set(),
        "failed_checks": {},
        "warning_checks": {},
    }
    for doc in docs:
        report = doc.get("report") or {}
        if report.get("ok"):
            out["ok"] += 1
        if report.get("version"):
            out["versions"].add(report["version"])
        checks = report.get("checks") or []
        for check in checks:
            name = check.get("name") or "?"
            status = check.get("status")
            if status == "fail":
                out["failures"] += 1
                out["failed_checks"][name] = out["failed_checks"].get(name, 0) + 1
            elif status == "warn":
                out["warnings"] += 1
                out["warning_checks"][name] = out["warning_checks"].get(name, 0) + 1
    out["versions"] = sorted(out["versions"])
    return out


def summarize_beta_evidence(paths: list[str]) -> dict:
    export_paths: list[str] = []
    doctor_docs: list[dict] = []
    errors: list[dict] = []

    for path in paths:
        try:
            doc = _load_json(path)
        except ValueError as e:
            errors.append({"file": path, "reason": str(e)})
            continue
        schema = doc.get("schema")
        if schema == EXPORT_SCHEMA:
            export_paths.append(path)
        elif schema == DOCTOR_SCHEMA:
            doctor_docs.append(doc)
        else:
            errors.append({"file": path, "reason": f"unsupported schema {schema!r}"})

    exports = summarize_exports(export_paths)
    doctors = _summarize_doctors(doctor_docs)
    errors.extend(exports.pop("errors", []))

    blockers = []
    if exports["files"] < 2:
        blockers.append("need at least two redacted exports")
    if exports["sessions"] < 1:
        blockers.append("need substantive tester sessions")
    if not exports["rule_fires"]:
        blockers.append("need at least one rule fire on tester data")
    if doctors["files"] < exports["files"]:
        blockers.append("need a doctor bundle for each tester export")
    if doctors["failures"]:
        blockers.append("doctor bundle reported failed install checks")

    return {
        "schema": "mrtoken.beta_evidence.v1",
        "exports": exports,
        "doctor_bundles": doctors,
        "errors": errors,
        "automatic_gate": {
            "passed": not blockers,
            "blockers": blockers,
        },
        "manual_questions": [
            "Did the HUD change an actual session decision?",
            "Was anything confusing, noisy, or easy to ignore?",
            "Would the tester keep it installed?",
        ],
    }


def print_beta_evidence(report: dict) -> None:
    exports = report["exports"]
    doctors = report["doctor_bundles"]
    print("\nMR Token beta evidence")
    print("----------------------")
    if report["errors"]:
        for err in report["errors"]:
            print(f"skipped {err['file']}: {err['reason']}")
        print("----------------------")
    versions = ", ".join(exports["tool_versions"]) or "?"
    print(f"exports:          {exports['files']} file(s), {exports['sessions']} session(s)")
    if exports["low_activity"]:
        print(f"low activity:     {exports['low_activity']} excluded")
    print(f"tool versions:    {versions}")
    print(f"total tokens:     {exports['total_tokens']:,}")
    print(f"est cost API-eq:  ${exports['est_cost_usd']:,.2f}")
    if exports["cache_hit_ratio"] is not None:
        print(f"cache hit ratio:  {exports['cache_hit_ratio']:.1%}")
    print(f"doctor bundles:   {doctors['files']} file(s), {doctors['ok']} ok")
    if doctors["failures"]:
        failed = ", ".join(f"{k} x{v}" for k, v in sorted(doctors["failed_checks"].items()))
        print(f"doctor failures:  {failed}")
    if doctors["warnings"]:
        warned = ", ".join(f"{k} x{v}" for k, v in sorted(doctors["warning_checks"].items()))
        print(f"doctor warnings:  {warned}")
    if exports["rule_fires"]:
        print("\nrule fires:")
        order = {"high": 0, "warn": 1}
        for rule, sevs in sorted(exports["rule_fires"].items(),
                                 key=lambda kv: -sum(kv[1].values())):
            parts = ", ".join(f"{n} {sev}" for sev, n in
                              sorted(sevs.items(), key=lambda kv: order.get(kv[0], 9)))
            print(f"  {rule:22} x{sum(sevs.values()):<4} ({parts})")
    else:
        print("\nrule fires: none")

    gate = report["automatic_gate"]
    print("\nautomatic gate: " + ("passed" if gate["passed"] else "not ready"))
    for blocker in gate["blockers"]:
        print(f"  - {blocker}")
    print("manual checks still required:")
    for q in report["manual_questions"]:
        print(f"  - {q}")
    print()
