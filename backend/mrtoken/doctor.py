#!/usr/bin/env python3
"""MR Token install doctor.

Setup diagnostics for beta testers: command version, project DB, Claude
hooks/statusLine/skills, optional Codex hook/skills, and release tag state.
Plain `doctor` is read-only; `doctor --fix` intentionally re-runs init.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import sys

from mrtoken import __version__
from mrtoken.datadir import resolve_db_path
from mrtoken.install import (
    _already_installed,
    _codex_mcp_configured,
    _compact_hook_already_installed,
    _load_settings,
    _prompt_hook_already_installed,
)

SKILLS = ("mr-context", "mr-handoff", "mr-status", "mr-why")


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "ok": status in ("ok", "skip"), "detail": detail}


def _skill_count(root: str) -> tuple[int, list[str]]:
    missing = []
    for name in SKILLS:
        if not os.path.isfile(os.path.join(root, name, "SKILL.md")):
            missing.append(name)
    return len(SKILLS) - len(missing), missing


def _db_status(path: str) -> tuple[str, str]:
    if not os.path.exists(path):
        return "warn", f"not found at {path}; run `mrtoken-transcript init` in this project"
    try:
        conn = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
        try:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('trace','session_summary')"
            ).fetchall()}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return "fail", f"cannot read {path}: {exc}"
    if {"trace", "session_summary"}.issubset(names):
        return "ok", path
    return "warn", f"{path} exists but schema is incomplete; run `mrtoken-transcript init`"


def _redact_text(text: str, project_root: str | None = None) -> str:
    home = os.path.expanduser("~")
    if not isinstance(text, str):
        return text
    out = text
    if home:
        out = out.replace(home, "~")
    if project_root:
        out = out.replace(project_root, "<project>")
    return out


def _redacted_report(report: dict) -> dict:
    project_root = report.get("project_root", "")
    out = dict(report)
    out["project_root"] = _redact_text(out.get("project_root", ""), project_root)
    out["checks"] = [
        {**c, "detail": _redact_text(c.get("detail", ""), project_root)}
        for c in report.get("checks", [])
    ]
    return out


def check_install(project_root: str | None = None,
                  db_path: str | None = None,
                  global_settings_path: str | None = None,
                  claude_skills_root: str | None = None,
                  codex_hooks_path: str | None = None,
                  codex_config_path: str | None = None,
                  codex_skills_root: str | None = None) -> dict:
    root = os.path.abspath(project_root or os.getcwd())
    db = db_path or resolve_db_path(root)
    global_settings_path = global_settings_path or os.path.expanduser("~/.claude/settings.json")
    claude_skills_root = claude_skills_root or os.path.join(
        os.path.dirname(global_settings_path), "skills")
    codex_hooks_path = codex_hooks_path or os.path.expanduser("~/.codex/hooks.json")
    codex_home = os.path.dirname(codex_hooks_path)
    codex_config_path = codex_config_path or os.path.join(codex_home, "config.toml")
    codex_skills_root = codex_skills_root or os.path.join(codex_home, "skills")

    checks = []
    exe = shutil.which("mrtoken-transcript")
    checks.append(_check("command", "ok" if exe else "fail",
                         f"mrtoken-transcript {__version__}" + (f" at {exe}" if exe else " not on PATH")))

    db_status, db_detail = _db_status(db)
    checks.append(_check("project db", db_status, db_detail))

    settings = _load_settings(global_settings_path)
    if settings:
        checks.append(_check("claude stop hook", "ok" if _already_installed(settings) else "fail",
                             global_settings_path if _already_installed(settings)
                             else f"missing MR Token Stop hook in {global_settings_path}"))
        statusline = settings.get("statusLine")
        has_sl = "statusline" in json.dumps(statusline or "")
        checks.append(_check("claude statusline", "ok" if has_sl else "fail",
                             global_settings_path if has_sl
                             else f"missing MR Token statusLine in {global_settings_path}"))
        has_prompt = _prompt_hook_already_installed(settings)
        checks.append(_check("claude prompt hook", "ok" if has_prompt else "fail",
                             global_settings_path if has_prompt
                             else f"missing UserPromptSubmit hook in {global_settings_path}"))
        has_compact = _compact_hook_already_installed(settings)
        checks.append(_check("claude compact hook", "ok" if has_compact else "fail",
                             global_settings_path if has_compact
                             else f"missing PreCompact hook in {global_settings_path}"))
    else:
        checks.append(_check("claude settings", "fail", f"missing or unreadable {global_settings_path}"))

    count, missing = _skill_count(claude_skills_root)
    checks.append(_check("claude skills", "ok" if not missing else "fail",
                         f"{count}/{len(SKILLS)} installed at {claude_skills_root}"
                         + (f"; missing {', '.join(missing)}" if missing else "")))

    if os.path.isdir(codex_home):
        codex = _load_settings(codex_hooks_path)
        has_codex = _already_installed(codex)
        checks.append(_check("codex stop hook", "ok" if has_codex else "fail",
                             codex_hooks_path if has_codex
                             else f"missing MR Token Stop hook in {codex_hooks_path}"))
        ccount, cmissing = _skill_count(codex_skills_root)
        checks.append(_check("codex skills", "ok" if not cmissing else "fail",
                             f"{ccount}/{len(SKILLS)} installed at {codex_skills_root}"
                             + (f"; missing {', '.join(cmissing)}" if cmissing else "")))
        has_mcp = _codex_mcp_configured(codex_config_path)
        checks.append(_check("codex mcp", "ok" if has_mcp else "fail",
                             codex_config_path if has_mcp
                             else f"missing [mcp_servers.mrtoken] in {codex_config_path}"))
    else:
        checks.append(_check("codex", "skip", f"{codex_home} not present"))

    try:
        from mrtoken.update_check import release_tag_warning
        tag_gap = release_tag_warning()
    except Exception:
        tag_gap = None
    checks.append(_check("release tag", "warn" if tag_gap else "ok", tag_gap or f"v{__version__} tagged"))

    # pricing: coverage (any model billed at the default fallback?) + freshness
    try:
        from mrtoken.ingest import load_prices
        from mrtoken.pricing import uncovered_models, freshness_warning
        prices = load_prices()
        uncovered: list[tuple[str, int]] = []
        if os.path.exists(db):
            try:
                pconn = sqlite3.connect(f"file:{os.path.abspath(db)}?mode=ro", uri=True)
                try:
                    if pconn.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='model_call'").fetchone():
                        uncovered = uncovered_models(pconn, prices)
                finally:
                    pconn.close()
            except sqlite3.Error:
                uncovered = []
        parts = []
        if uncovered:
            shown = ", ".join(f"{m} ({c})" for m, c in uncovered[:5])
            parts.append(f"{len(uncovered)} model(s) billed at default: {shown}")
        fresh = freshness_warning(prices)
        if fresh:
            parts.append(fresh)
        checks.append(_check(
            "pricing", "warn" if parts else "ok",
            " · ".join(parts) if parts else f"prices.json v{prices.get('version')} — all models covered"))
    except Exception:
        pass

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    return {
        "ok": not fails,
        "version": __version__,
        "project_root": root,
        "checks": checks,
        "failures": len(fails),
        "warnings": len(warns),
    }


def print_doctor(report: dict) -> None:
    marks = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "-"}
    print(f"MR Token doctor · v{report['version']}")
    print(f"project: {report['project_root']}")
    for check in report["checks"]:
        mark = marks.get(check["status"], "?")
        print(f"  {mark} {check['name']:<20} {check['detail']}")
    if report["ok"]:
        tail = "ok"
        if report["warnings"]:
            tail += f" ({report['warnings']} warning{'s' if report['warnings'] != 1 else ''})"
        print(f"\ndoctor: {tail}")
    else:
        print(f"\ndoctor: {report['failures']} failure{'s' if report['failures'] != 1 else ''}")


def repair_install(project_root: str | None = None,
                   global_settings_path: str | None = None,
                   codex_hooks_path: str | None = None,
                   codex_config_path: str | None = None,
                   codex_skills_root: str | None = None,
                   emit=print) -> int:
    """Intentional write path behind `doctor --fix`: re-run init."""
    from mrtoken.install import init
    return init(project_root=project_root,
                global_settings_path=global_settings_path,
                codex_hooks_path=codex_hooks_path,
                codex_config_path=codex_config_path,
                codex_skills_root=codex_skills_root,
                emit=emit)


def write_bundle(report: dict, path: str) -> str:
    bundle = {
        "schema": "mrtoken.doctor.bundle.v1",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": _redact_text(sys.executable),
        "report": _redacted_report(report),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2)
        handle.write("\n")
    return path
