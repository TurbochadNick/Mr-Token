"""python3 -m mrtoken  →  show help."""
import sys
print("MR Token — usage:")
print("  python3 -m mrtoken.ingest <file.jsonl> [--db mrtoken.db]")
print("  python3 -m mrtoken.ingest --all         [--db mrtoken.db]")
print("  python3 -m mrtoken.report [session-prefix] [--db mrtoken.db]")
print("  python3 -m mrtoken.report --list        [--db mrtoken.db]")
