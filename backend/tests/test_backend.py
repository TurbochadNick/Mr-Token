import json
import os
import sqlite3
import tempfile
import unittest

from mrtoken.ingest import connect, default_db_path, ingest_file, load_prices
from mrtoken.rules import rule_huge_tool_output, rule_retry_loop


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class BackendTest(unittest.TestCase):
    def test_default_db_path_is_project_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            self.assertEqual(
                default_db_path(tmp),
                os.path.join(tmp, ".token-tithe", "token-tithe.db"),
            )

    def test_ingests_tokens_tools_and_hashes_without_raw_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, ".token-tithe", "token-tithe.db")
            transcript = os.path.join(tmp, "session-1.jsonl")
            write_jsonl(
                transcript,
                [
                    {
                        "type": "assistant",
                        "sessionId": "session-1",
                        "uuid": "assistant-1",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "cwd": tmp,
                        "message": {
                            "model": "claude-sonnet-4",
                            "usage": {
                                "input_tokens": 100,
                                "output_tokens": 20,
                                "cache_read_input_tokens": 50,
                                "cache_creation_input_tokens": 10,
                            },
                            "content": [
                                {"type": "text", "text": "plan"},
                                {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "secret.py"}},
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-06-01T00:00:01Z",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "tool-1",
                                    "content": "raw secret source should not be stored",
                                }
                            ]
                        },
                    },
                ],
            )

            conn = connect(db_path)
            result = ingest_file(conn, transcript, load_prices())

            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(result["tool_calls"], 1)
            self.assertTrue(os.path.exists(db_path))
            self.assertEqual(conn.execute("SELECT input_tokens, output_tokens FROM model_call").fetchone(), (100, 20))
            tool = conn.execute("SELECT tool_name, output_chars, output_hash FROM tool_call").fetchone()
            self.assertEqual(tool[0], "Read")
            self.assertGreater(tool[1], 0)
            self.assertIsNotNone(tool[2])
            columns = [row[1] for row in conn.execute("PRAGMA table_info(context_block)").fetchall()]
            self.assertNotIn("content", columns)

    def test_huge_tool_output_rule(self):
        conn, tid = make_trace()
        conn.execute(
            "INSERT INTO tool_call(trace_id, tool_name, output_chars, output_tokens_est) VALUES(?,?,?,?)",
            (tid, "Bash", 50_000, 12_500),
        )

        recs = rule_huge_tool_output(conn, tid)

        self.assertEqual(recs[0]["rule"], "huge_tool_output")
        self.assertEqual(recs[0]["severity"], "warn")

    def test_retry_loop_rule_uses_real_model_call_id(self):
        conn, tid = make_trace()
        model_call_ids = []
        for index in range(3):
            cur = conn.execute(
                "INSERT INTO model_call(trace_id, timestamp, input_tokens, output_tokens) VALUES(?,?,?,?)",
                (tid, f"2026-06-01T00:00:0{index}Z", 10, 1),
            )
            model_call_ids.append(cur.lastrowid)
            conn.execute(
                "INSERT INTO tool_call(trace_id, model_call_id, tool_name, is_error) VALUES(?,?,?,1)",
                (tid, cur.lastrowid, "Bash"),
            )

        recs = rule_retry_loop(conn, tid)

        self.assertEqual(recs[0]["rule"], "retry_loop")
        evidence = json.loads(recs[0]["evidence_json"])
        self.assertEqual(evidence["first_mc_id"], model_call_ids[0])


def make_trace() -> tuple[sqlite3.Connection, int]:
    conn = connect(":memory:")
    cur = conn.execute(
        "INSERT INTO trace(session_id, ingested_at) VALUES(?,?)",
        ("session-1", "2026-06-01T00:00:00Z"),
    )
    return conn, cur.lastrowid


if __name__ == "__main__":
    unittest.main()
