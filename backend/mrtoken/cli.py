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
    from mrtoken.ingest import main as _main
    argv = []
    if args.all:
        argv += ["--all"]
    elif args.file:
        argv += [args.file]
    else:
        print("mrtoken-transcript ingest: give a file or --all"); sys.exit(1)
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
    from mrtoken.export import export_report
    print(export_report(_open(args.db), args.session, redact=getattr(args, "redact", False)))


def cmd_init(args):
    from mrtoken.install import init
    sys.exit(init(project_root=args.project_root, settings_path=args.settings,
                  dry_run=args.print))


def cmd_uninstall(args):
    from mrtoken.install import uninstall
    sys.exit(uninstall(project_root=args.project_root,
                       remove_skills=not args.keep_skills))


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
    p_ingest.add_argument("--rules", action="store_true", help="run rule engine after ingestion")
    p_ingest.add_argument("--db", dest="db_sub")  # allow --db after subcommand too

    p_report = sub.add_parser("report", help="show report for a session")
    p_report.add_argument("session", nargs="?", help="session ID prefix")
    p_report.add_argument("--db", dest="db_sub")

    p_list = sub.add_parser("list", help="list all sessions")
    p_list.add_argument("--db", dest="db_sub")

    p_sub = sub.add_parser("subagents", help="subagent ROI breakdown")
    p_sub.add_argument("session", nargs="?", help="parent session ID prefix")
    p_sub.add_argument("--db", dest="db_sub")

    p_fleet = sub.add_parser("fleet", help="cross-session summary")
    p_fleet.add_argument("--db", dest="db_sub")

    p_export = sub.add_parser("export",
        help="emit accurate per-session metrics as JSON (integration surface for the UI)")
    p_export.add_argument("session", nargs="?", help="session ID prefix")
    p_export.add_argument("--db", dest="db_sub")
    p_export.add_argument("--redact", action="store_true",
        help="drop project_path + title so the export is safe to share")

    p_validate = sub.add_parser("validate",
        help="corroborate fired recommendations (precision proxy, not labels)")
    p_validate.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p_validate.add_argument("--db", dest="db_sub")

    p_uninstall = sub.add_parser("uninstall",
        help="remove MR Token's hooks + statusLine + skills (reverse of init)")
    p_uninstall.add_argument("--project-root", help="project root (default: auto-detect)")
    p_uninstall.add_argument("--keep-skills", action="store_true",
        help="leave the /mr-* skills installed")

    p_init = sub.add_parser("init",
        help="set up the backend in this project (DB + project-local Stop hook)")
    p_init.add_argument("--project-root", help="project root (default: auto-detect)")
    p_init.add_argument("--settings", help="settings file (default: <root>/.claude/settings.local.json)")
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

    p_roi = sub.add_parser("roi",
        help="estimate addressable token waste (session or fleet) — estimate, not a trial")
    p_roi.add_argument("session", nargs="?", help="session ID prefix (omit for fleet-wide)")
    p_roi.add_argument("--db", dest="db_sub")

    p_status = sub.add_parser("status",
        help="one-glance snapshot of the current session + the top next action")
    p_status.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")
    p_status.add_argument("--db", dest="db_sub")

    p_sl = sub.add_parser("statusline",
        help="print one-line HUD for Claude Code's statusLine setting (no DB write)")
    p_sl.add_argument("session", nargs="?", help="session id or transcript path (default: newest)")

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(); return
    # subcommand --db overrides global --db
    if hasattr(a, "db_sub") and a.db_sub:
        a.db = a.db_sub

    dispatch = {"ingest": cmd_ingest, "report": cmd_report,
                "list": cmd_list, "subagents": cmd_subagents, "fleet": cmd_fleet,
                "export": cmd_export, "validate": cmd_validate, "watch": cmd_watch,
                "init": cmd_init, "uninstall": cmd_uninstall,
        "handoff": cmd_handoff, "why": cmd_why, "roi": cmd_roi,
                "migrate-data": cmd_migrate, "status": cmd_status,
                "statusline": cmd_statusline}
    dispatch[a.cmd](a)


if __name__ == "__main__":
    main()
