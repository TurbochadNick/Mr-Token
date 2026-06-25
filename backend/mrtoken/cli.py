#!/usr/bin/env python3
"""mrtoken-transcript — transcript backend CLI entry point.

Commands:
  mrtoken-transcript ingest [file.jsonl | --all]   ingest transcript(s)
  mrtoken-transcript report [session-prefix]        show report for a session
  mrtoken-transcript list                           list all sessions
  mrtoken-transcript subagents [session-prefix]     show subagent breakdown for a session
  mrtoken-transcript fleet                          cross-session summary

Options shared by most commands:
  --db PATH    SQLite database path (default: .token-tithe/token-tithe.db)
  --rules      also run rule engine after ingest
"""
import argparse, sys

from mrtoken.ingest import connect, default_db_path

DEFAULT_DB = default_db_path()


def _open(db_path):
    """Open a DB ensuring our tables, migrations, and views exist (idempotent).

    Read commands use this so they never crash on a DB that hasn't been through
    ingest — e.g. a pilot DB created by the TypeScript `init` (events table only).
    """
    return connect(db_path)


def cmd_ingest(args):
    # auto-route a single Codex rollout to the Codex adapter (Claude path untouched)
    if getattr(args, "file", None) and not getattr(args, "backfill", False) and not args.all:
        from mrtoken.ingest_codex import _is_codex_transcript, ingest_codex_file
        if _is_codex_transcript(args.file):
            from mrtoken.ingest import connect
            import json as _json
            conn = connect(args.db)
            r = ingest_codex_file(conn, args.file)
            if args.rules and not r.get("skipped"):
                from mrtoken.rules import analyse
                tid = conn.execute("SELECT id FROM trace WHERE session_id=?",
                                   (r["session_id"],)).fetchone()[0]
                r["recommendations"] = len(analyse(conn, tid))
            print(_json.dumps({"db": args.db, "source": "codex", **r}, indent=2))
            return

    from mrtoken.ingest import main as _main
    argv = []
    if getattr(args, "backfill", False):
        argv += ["--backfill"]
    elif args.all:
        argv += ["--all"]
    elif args.file:
        argv += [args.file]
    else:
        print("mrtoken-transcript ingest: give a file, --all, or --backfill"); sys.exit(1)
    if getattr(args, "projects_root", None):
        argv += ["--projects-root", args.projects_root]
    argv += ["--db", args.db]
    if args.rules:
        argv += ["--rules"]
    _main(argv)


def cmd_report(args):
    from mrtoken.report import report, list_traces
    conn = _open(args.db)
    if args.session:
        report(conn, args.session)
    else:
        list_traces(conn)


def cmd_list(args):
    from mrtoken.report import list_traces
    list_traces(_open(args.db))


def cmd_subagents(args):
    from mrtoken.subagents import subagent_report
    subagent_report(_open(args.db), args.session or "")


def cmd_fleet(args):
    from mrtoken.fleet import fleet_summary
    fleet_summary(_open(args.db))


def cmd_export(args):
    if getattr(args, "detail", False):
        if not args.session:
            print("mrtoken-transcript export --detail: give a session prefix"); sys.exit(1)
        from mrtoken.export import export_detail
        print(export_detail(_open(args.db), args.session))
        return
    from mrtoken.export import export_report
    print(export_report(_open(args.db), args.session, redact=getattr(args, "redact", False),
                        since=getattr(args, "since", None)))


def cmd_init(args):
    from mrtoken.install import init
    sys.exit(init(project_root=args.project_root, settings_path=args.settings,
                  dry_run=args.print))


def cmd_uninstall(args):
    from mrtoken.install import uninstall
    sys.exit(uninstall(project_root=args.project_root,
                       remove_skills=not args.keep_skills))


def cmd_update(args):
    """Self-update: pull the latest into this git checkout, reinstall, re-sync hooks/skills.

    The 'auto update' path for testers — no zip to send, no manual git dance. Runs
    only on a git clone (collaborator access); silent no-op design on zip/no-git
    installs. Fast-forward only, so it never clobbers local work or a dirty tree.
    """
    import os, subprocess
    from mrtoken.update_check import _repo_root
    root = _repo_root()
    if not root:
        print("mrtoken update: this install isn't a git checkout. Re-clone the repo "
              "(git clone <url>) or grab a fresh build, then run `mrtoken-transcript init`.")
        sys.exit(1)
    print("▸ pulling latest…")
    if subprocess.run(["git", "-C", root, "pull", "--ff-only"]).returncode != 0:
        print("✗ couldn't fast-forward (local edits or diverged history). "
              "Resolve in the repo, then retry — your install is unchanged.")
        sys.exit(1)
    print("▸ reinstalling backend + re-syncing hooks/skills…")
    subprocess.run([sys.executable, "-m", "pip", "install", "-e",
                    os.path.join(root, "backend"), "-q"])
    try:
        from mrtoken.install import init
        init(emit=lambda *a, **k: None)  # idempotent: refresh global hooks/skills
    except Exception as e:
        print(f"  (hook re-sync skipped: {e})")
    # report the NEW version from a fresh interpreter (this process holds the old one)
    ver = subprocess.run([sys.executable, "-c", "import mrtoken;print(mrtoken.__version__)"],
                         capture_output=True, text=True).stdout.strip()
    print(f"✓ updated — now on v{ver or '?'}")
    sys.exit(0)


def cmd_watch(args):
    from mrtoken.watch import watch
    sys.exit(watch(args.session, interval=args.interval, once=args.once))


def cmd_handoff(args):
    from mrtoken.handoff import build_handoff
    print(build_handoff(args.db, args.session))


def cmd_migrate(args):
    from mrtoken.migrate import migrate
    sys.exit(migrate(apply=args.apply))


def cmd_why(args):
    from mrtoken.why import print_diagnosis
    print_diagnosis(_open(args.db), args.session or "")


def cmd_roi(args):
    if getattr(args, "measure", False):
        from mrtoken.roi import print_roi_measure
        print_roi_measure(_open(args.db))
    else:
        from mrtoken.roi import print_roi
        print_roi(_open(args.db), args.session)


def cmd_status(args):
    from mrtoken.status import print_status
    sys.exit(print_status(args.db, args.session))


def cmd_validate(args):
    from mrtoken.validate import validate_db, print_report
    import json
    report = validate_db(_open(args.db))
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


def cmd_corpus(args):
    from mrtoken.corpus import summarize_exports, print_corpus_report
    import json
    agg = summarize_exports(args.files)
    if getattr(args, "json", False):
        print(json.dumps(agg, indent=2))
    else:
        print_corpus_report(agg)


def cmd_explain(args):
    from mrtoken.feedback import print_explain
    print_explain(_open(args.db), args.session or "")


def cmd_feedback(args):
    from mrtoken.feedback import record_feedback, print_feedback_summary
    conn = _open(args.db)
    if getattr(args, "summary", False) or not args.session:
        print_feedback_summary(conn); return
    if not args.rule or not args.verdict:
        print("usage: mrtoken-transcript feedback <session> <rule> right|wrong|unsure [--note ...]\n"
              "   or: mrtoken-transcript feedback --summary"); sys.exit(1)
    try:
        r = record_feedback(conn, args.session, args.rule, args.verdict, getattr(args, "note", None))
    except ValueError as e:
        print(f"mrtoken feedback: {e}"); sys.exit(1)
    print(f"✓ recorded: {r['session_id'][:8]} · {r['rule']} → {r['verdict']}")


def cmd_config(args):
    from mrtoken import policy
    if getattr(args, "kill", False):
        policy.set_enabled(False); print("✓ interventions OFF (global kill switch)")
    if getattr(args, "enable", False):
        policy.set_enabled(True); print("✓ interventions enabled")
    for pair in getattr(args, "intervene", None) or []:
        if "=" not in pair:
            print(f"  skip {pair!r} — use tool=level (level: {'/'.join(policy.LEVELS)})"); continue
        tool, level = pair.split("=", 1)
        try:
            policy.set_autonomy(tool.strip(), level.strip())
            print(f"✓ {tool.strip()} → {level.strip()}")
        except ValueError as e:
            print(f"  {e}")
    s = policy.summary()
    print(f"\n  interventions: {'on' if s['enabled'] else 'OFF (kill switch)'} · "
          f"default {s['default']}")
    for t, lv in (s["tools"] or {}).items():
        print(f"    {t:10} {lv}")


def cmd_mcp(args):
    """Run the MCP stdio server (the toolbox the agent calls). Register with
    `claude mcp add mrtoken -- mrtoken-transcript mcp` or Codex [mcp_servers]."""
    from mrtoken.mcp_server import serve
    sys.exit(serve())


def cmd_statusline(args):
    from mrtoken.statusline import statusline_hud
    sys.exit(statusline_hud(getattr(args, "session", None)))


def main(argv=None):
    from mrtoken import __version__
    ap = argparse.ArgumentParser(prog="mrtoken-transcript",
        description="Local-first token observability for AI agent workflows")
    ap.add_argument("--version", action="version", version=f"mrtoken-transcript {__version__}")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite database (default: .token-tithe/token-tithe.db)")
    sub = ap.add_subparsers(dest="cmd")

    p_ingest = sub.add_parser("ingest", help="ingest Claude Code transcript(s)")
    p_ingest.add_argument("file", nargs="?", help="path to .jsonl transcript")
    p_ingest.add_argument("--all", action="store_true", help="ingest all ~/.claude/projects/**")
    p_ingest.add_argument("--backfill", action="store_true",
        help="ingest ALL local transcripts + run rules (build a corpus; idempotent)")
    p_ingest.add_argument("--projects-root", help="root to scan (default ~/.claude/projects)")
    p_ingest.add_argument("--rules", action="store_true", help="run rule engine after ingestion")
    p_ingest.add_argument("--db", dest="db_sub")  # allow --db after subcommand too

    p_report = sub.add_parser("report", help="show report for a session")
    p_report.add_argument("session", nargs="?", help="session ID prefix")
    p_report.add_argument("--db", dest="db_sub")
    p_report.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_list = sub.add_parser("list", help="list all sessions")
    p_list.add_argument("--db", dest="db_sub")
    p_list.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_sub = sub.add_parser("subagents", help="subagent ROI breakdown")
    p_sub.add_argument("session", nargs="?", help="parent session ID prefix")
    p_sub.add_argument("--db", dest="db_sub")

    p_fleet = sub.add_parser("fleet", help="cross-session summary")
    p_fleet.add_argument("--db", dest="db_sub")
    p_fleet.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_export = sub.add_parser("export",
        help="emit accurate per-session metrics as JSON (integration surface for the UI)")
    p_export.add_argument("session", nargs="?", help="session ID prefix")
    p_export.add_argument("--db", dest="db_sub")
    p_export.add_argument("--redact", action="store_true",
        help="drop project_path + title so the export is safe to share")
    p_export.add_argument("--since", help="ISO timestamp; only sessions started at/after it "
        "(incremental dashboard refresh)")
    p_export.add_argument("--detail", action="store_true",
        help="emit a per-model-call timeline for the given session (drill-down)")
    p_export.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_validate = sub.add_parser("validate",
        help="corroborate fired recommendations (precision proxy, not labels)")
    p_validate.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p_validate.add_argument("--db", dest="db_sub")
    p_validate.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_corpus = sub.add_parser("corpus",
        help="aggregate shared export JSON files (e.g. from a beta tester) into one summary")
    p_corpus.add_argument("files", nargs="+", help="one or more session_summary.v1 export JSON files")
    p_corpus.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    p_explain = sub.add_parser("explain",
        help="decode why each signal fired for a session (evidence behind the HUD)")
    p_explain.add_argument("session", nargs="?", help="session id or prefix (default: newest)")
    p_explain.add_argument("--db", dest="db_sub")
    p_explain.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_mcp = sub.add_parser("mcp",
        help="run the MCP stdio server (the agent toolbox: offload, …) — register with Claude/Codex")

    p_config = sub.add_parser("config",
        help="view/set intervention policy: per-tool autonomy (off|tell|ask|do) + kill switch")
    p_config.add_argument("--intervene", action="append", metavar="TOOL=LEVEL",
        help="set a tool's proc-engine level, e.g. offload=ask (repeatable)")
    p_config.add_argument("--kill", action="store_true", help="global kill switch: silence all interventions")
    p_config.add_argument("--enable", action="store_true", help="re-enable interventions")

    p_feedback = sub.add_parser("feedback",
        help="record a right/wrong/unsure verdict on a fired rule (real-usage precision)")
    p_feedback.add_argument("session", nargs="?", help="session id or prefix")
    p_feedback.add_argument("rule", nargs="?", help="rule name (e.g. huge_tool_output)")
    p_feedback.add_argument("verdict", nargs="?", help="right | wrong | unsure")
    p_feedback.add_argument("--note", help="optional free-text note")
    p_feedback.add_argument("--summary", action="store_true", help="show labelled precision per rule")
    p_feedback.add_argument("--db", dest="db_sub")

    p_uninstall = sub.add_parser("uninstall",
        help="remove MR Token's hooks + statusLine + skills (reverse of init)")
    p_uninstall.add_argument("--project-root", help="project root (default: auto-detect)")
    p_uninstall.add_argument("--keep-skills", action="store_true",
        help="leave the /mr-* skills installed")

    p_init = sub.add_parser("init",
        help="set up the backend in this project (DB + global Stop/HUD hooks)")
    p_init.add_argument("--project-root", help="project root (default: auto-detect)")
    p_init.add_argument("--settings",
        help="override where the Stop hook is written (default: global ~/.claude/settings.json)")
    p_init.add_argument("--dry-run", "--print", dest="print", action="store_true",
        help="dry run — show what would happen, write nothing")

    p_watch = sub.add_parser("watch", help="live in-session advice (tails the transcript)")
    p_watch.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")
    p_watch.add_argument("--interval", type=float, default=2.0, help="poll seconds (default 2)")
    p_watch.add_argument("--once", action="store_true", help="replay current transcript and exit")

    p_handoff = sub.add_parser("handoff",
        help="generate a compact handoff to continue a bloated session fresh")
    p_handoff.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")
    p_handoff.add_argument("--db", dest="db_sub")

    p_migrate = sub.add_parser("migrate-data",
        help="find scattered .token-tithe DBs and relocate non-project ones to the central store")
    p_migrate.add_argument("--apply", action="store_true",
        help="actually relocate (default: dry-run report)")

    p_why = sub.add_parser("why", help="diagnose where a session's cost went + the main fuel leak")
    p_why.add_argument("session", nargs="?", help="session ID prefix (default: newest)")
    p_why.add_argument("--db", dest="db_sub")
    p_why.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_roi = sub.add_parser("roi",
        help="estimate addressable token waste (session or fleet) — estimate, not a trial")
    p_roi.add_argument("session", nargs="?", help="session ID prefix (omit for fleet-wide)")
    p_roi.add_argument("--measure", action="store_true",
        help="fresh_handoff before/after: counterfactual projection + acted-vs-ignored cohort")
    p_roi.add_argument("--db", dest="db_sub")
    p_roi.add_argument("--codex", action="store_true", help="read the central Codex DB")

    p_status = sub.add_parser("status",
        help="one-glance snapshot of the current session + the top next action")
    p_status.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")
    p_status.add_argument("--db", dest="db_sub")

    p_sl = sub.add_parser("statusline",
        help="print one-line HUD for Claude Code's statusLine setting (no DB write)")
    p_sl.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")

    sub.add_parser("update",
        help="pull the latest release into this checkout, reinstall, re-sync hooks/skills")

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(); return
    # subcommand --db overrides global --db
    if hasattr(a, "db_sub") and a.db_sub:
        a.db = a.db_sub
    # --codex: read from the central Codex DB (where all Codex sessions aggregate)
    if getattr(a, "codex", False):
        from mrtoken.datadir import codex_db_path
        a.db = codex_db_path()

    dispatch = {"ingest": cmd_ingest, "report": cmd_report,
                "list": cmd_list, "subagents": cmd_subagents, "fleet": cmd_fleet,
                "export": cmd_export, "validate": cmd_validate, "corpus": cmd_corpus,
                "explain": cmd_explain, "feedback": cmd_feedback, "mcp": cmd_mcp,
                "config": cmd_config, "watch": cmd_watch,
                "init": cmd_init, "uninstall": cmd_uninstall,
        "handoff": cmd_handoff, "why": cmd_why, "roi": cmd_roi,
                "migrate-data": cmd_migrate, "status": cmd_status,
                "statusline": cmd_statusline, "update": cmd_update}
    dispatch[a.cmd](a)


if __name__ == "__main__":
    main()
