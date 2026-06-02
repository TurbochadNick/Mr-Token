#!/usr/bin/env python3
"""mrtoken — unified CLI entry point.

Commands:
  mrtoken ingest [file.jsonl | --all]   ingest transcript(s)
  mrtoken report [session-prefix]        show report for a session
  mrtoken list                           list all sessions
  mrtoken subagents [session-prefix]     show subagent breakdown for a session
  mrtoken fleet                          cross-session summary

Options shared by most commands:
  --db PATH    SQLite database path (default: ~/mrtoken.db)
  --rules      also run rule engine after ingest
"""
import argparse, os, sys


DEFAULT_DB = os.path.expanduser("~/mr_token/mrtoken.db")


def cmd_ingest(args):
    from mrtoken.ingest import main as _main
    argv = []
    if args.all:
        argv += ["--all"]
    elif args.file:
        argv += [args.file]
    else:
        print("mrtoken ingest: give a file or --all"); sys.exit(1)
    argv += ["--db", args.db]
    if args.rules:
        argv += ["--rules"]
    _main(argv)


def cmd_report(args):
    from mrtoken.report import report, list_traces
    import sqlite3
    conn = sqlite3.connect(args.db)
    if args.session:
        report(conn, args.session)
    else:
        list_traces(conn)


def cmd_list(args):
    from mrtoken.report import list_traces
    import sqlite3
    list_traces(sqlite3.connect(args.db))


def cmd_subagents(args):
    from mrtoken.subagents import subagent_report
    import sqlite3
    subagent_report(sqlite3.connect(args.db), args.session or "")


def cmd_fleet(args):
    from mrtoken.fleet import fleet_summary
    import sqlite3
    fleet_summary(sqlite3.connect(args.db))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mrtoken",
        description="Local-first token observability for AI agent workflows")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite database (default: ~/mrtoken.db)")
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

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(); return
    # subcommand --db overrides global --db
    if hasattr(a, "db_sub") and a.db_sub:
        a.db = a.db_sub

    dispatch = {"ingest": cmd_ingest, "report": cmd_report,
                "list": cmd_list, "subagents": cmd_subagents, "fleet": cmd_fleet}
    dispatch[a.cmd](a)


if __name__ == "__main__":
    main()
