#!/usr/bin/env python3
"""Continuation manifest: DECLARED state carried into the handoff, bound and verified.

Fixtures come from GROUND TRUTH, never from the code under test: the repository HEAD is read
with `git rev-parse` in the test, the dirty count is the number of files the test created, the
manifest is written BY HAND as JSON (not through `declare_manifest`), and the artifact digest
is a precomputed constant for fixed bytes. The six-facts test imports only `build_handoff`, so
it FAILS (not errors) on a build without the manifest — that is its known-negative arm.

Environment-mediated protections leave the environment BOUND: `MRTOKEN_SESSION` is set to a
foreign id and never popped inside the test that checks it is ignored.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SID = "a4782ea0-0000-4000-8000-000000000001"           # sanitized stand-in for the real case
PATCH_BYTES = b"consolidated v2 patch bytes\n"
PATCH_SHA = "19fcacae4be64bc29a90557d247514419f1540f7767e8c9a6be63ef30d7b57bf"   # shasum -a 256
OTHER_SHA = "5ba88d33c3813b380bb85fc23dba9fb68e20323acc56effdbaa6bb1c6e5d3a0e"   # of other bytes
BULK = "Ran 202 tests in 3.626s\n\nOK"                  # completed output that must NOT be hauled
LAST_REQUEST = "[from zjn-command] MR Token real field validation — personal and enterprise tracks"
STALE_TITLE = "Environment validation session"
FOREIGN = "FOREIGN-MANIFEST-SENTINEL-DO-NOT-SHOW"


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True,
                          text=True).stdout.strip()


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


class ManifestFixture(unittest.TestCase):
    """A real git repo (ground-truth HEAD, 14 dirty files), a sanitized transcript shaped like
    the 830k-token field case, and a hand-written manifest carrying all six facts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.realpath(os.path.join(self.tmp, "mr_token"))   # underscore path
        os.makedirs(self.project)
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "t@example.invalid")
        git(self.project, "config", "user.name", "t")
        with open(os.path.join(self.project, ".gitignore"), "w") as fh:
            fh.write(".token-tithe/\n")           # same convention as the product
        with open(os.path.join(self.project, "README.md"), "w") as fh:
            fh.write("x\n")
        git(self.project, "add", ".gitignore", "README.md")
        git(self.project, "commit", "-q", "-m", "base")
        self.head = git(self.project, "rev-parse", "HEAD")          # GROUND TRUTH
        for i in range(14):                                          # dirty 14, like the real case
            with open(os.path.join(self.project, f"held{i}.txt"), "w") as fh:
                fh.write("held\n")
        self.patch = os.path.join(self.tmp, "MR_TOKEN_CONSOLIDATED_V2.patch")
        with open(self.patch, "wb") as fh:
            fh.write(PATCH_BYTES)
        self.transcript = os.path.join(self.tmp, "projects", "-bucket", f"{SID}.jsonl")
        os.makedirs(os.path.dirname(self.transcript))
        write_jsonl(self.transcript, [
            {"type": "ai-title", "aiTitle": STALE_TITLE},
            {"type": "user", "cwd": self.project, "message": {"content": "start environment validation"}},
            {"type": "assistant", "sessionId": SID, "uuid": "a1", "cwd": self.project,
             "message": {"model": "claude-sonnet-4",
                         "usage": {"input_tokens": 10, "output_tokens": 5},
                         "content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                      "input": {"command": "python3 -m unittest discover -s tests -q"}}]}},
            {"type": "user", "cwd": self.project,
             "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": BULK}]}},
            {"type": "ai-title", "aiTitle": STALE_TITLE},
            {"type": "user", "cwd": self.project, "message": {"content": LAST_REQUEST}},
        ])
        self.manifest_dir = os.path.join(self.project, ".token-tithe", "manifest")
        self.db = os.path.join(self.project, ".token-tithe", "token-tithe.db")
        self._cwd = os.getcwd()
        os.chdir(self.project)
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(v, None)

    def tearDown(self):
        os.chdir(self._cwd)
        for v in ("MRTOKEN_SESSION", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(v, None)

    def full_manifest(self, **over):
        m = {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "binding": {"project_root": self.project, "session_id": SID},
            "objective": "Run the bounded real field continuation of MR Token handoff",
            "artifacts": [{"path": self.patch, "role": "consolidated V2 patch (active)",
                           "sha256": PATCH_SHA}],
            "custody": {"repo": self.project, "head": self.head, "dirty_count": 14,
                        "held": ["F1 slice 308/2: intervene.py +142/-10, test_backend.py +437/-0"]},
            "decisions": ["state is DECLARED by the agent, never inferred"],
            "reviewer_corrections": [{"text": "goal mechanism: ai-title outranked last_prompt, "
                                              "not first_prompt ranking", "status": "accepted"}],
            "evidence": ["reproduced: resolve_path(None) with MRTOKEN_SESSION=foreign bound a "
                         "foreign transcript (omitted-key env seam)"],
            "gates": ["nothing applied; no push; ownership gate open"],
            "next_action": "independent review, then rerun the field continuation in isolation",
            "do_not_redo": ["baseline 202 OK already observed on the patched lab"],
        }
        m.update(over)
        return m

    def write_manifest(self, m, where=None, sid=SID):
        d = where or self.manifest_dir
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{sid}.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(m, fh)
        return p

    def handoff(self):
        from mrtoken.handoff import build_handoff
        return build_handoff(self.db, self.transcript)

    def goal_line(self, md):
        lines = md.splitlines()
        i = lines.index("## Goal")
        return lines[i + 1]


class SixFacts(ManifestFixture):
    def test_six_facts_present_current_goal_and_no_bulk(self):
        self.write_manifest(self.full_manifest())
        md = self.handoff()
        # 1 active patch identity: the FULL 64-hex SHA-256, verified against the file on disk
        self.assertIn(PATCH_SHA, md)
        self.assertIn("— verified", md)
        # 2 custody HEAD (full 40-hex)  3 dirty count  4 held slice
        self.assertIn(self.head, md)
        self.assertIn("dirty 14", md)
        self.assertIn("308/2", md)
        # 5 reviewer corrections  6 reproduced defect
        self.assertIn("ai-title outranked last_prompt", md)
        self.assertIn("omitted-key env seam", md)
        # goal currency: the CURRENT request, not the session-start ai-title
        self.assertEqual(self.goal_line(md), LAST_REQUEST)
        self.assertNotEqual(self.goal_line(md), STALE_TITLE)
        # declared objective is carried verbatim AND is distinct from the transcript goal
        obj = "Run the bounded real field continuation of MR Token handoff"
        self.assertIn(f"- **current objective:** {obj}", md)
        self.assertNotEqual(obj, self.goal_line(md))
        # completed bulk output is still excluded
        self.assertNotIn("Ran 202 tests", md)
        # no mismatch or gap noise on a fully declared, consistent manifest
        self.assertNotIn("MISMATCH", md)
        self.assertNotIn("GAP", md)

    def test_no_manifest_is_a_named_gap_not_a_guess(self):
        self.assertFalse(os.path.exists(self.manifest_dir))            # precondition
        md = self.handoff()
        self.assertIn("GAP: no manifest declared", md)
        self.assertNotIn(self.head[:12], md)     # nothing inferred from the repo

    def test_undeclared_field_is_a_named_gap(self):
        self.write_manifest(self.full_manifest(reviewer_corrections=None, next_action=None))
        md = self.handoff()
        self.assertIn("reviewer corrections and their status:** GAP", md)
        self.assertIn("immediate next action:** GAP", md)
        self.assertIn(self.head[:12], md)        # the rest is still carried


class Mutations(ManifestFixture):
    """Each declared binding or identity is mutated in turn; each must fail closed or surface."""

    def test_session_mismatch_withholds_facts(self):
        m = self.full_manifest(binding={"project_root": self.project, "session_id": "other-sess"})
        self.write_manifest(m)                                         # filed under SID
        md = self.handoff()
        self.assertIn("WITHHELD", md)
        self.assertIn("MISMATCH session", md)
        self.assertNotIn(self.head[:12], md)
        self.assertNotIn("omitted-key env seam", md)

    def test_project_mismatch_withholds_facts(self):
        other = os.path.join(self.tmp, "other-project")
        os.makedirs(other)
        self.write_manifest(self.full_manifest(binding={"project_root": other, "session_id": SID}))
        md = self.handoff()
        self.assertIn("WITHHELD", md)
        self.assertIn("MISMATCH project", md)
        self.assertNotIn(self.head[:12], md)

    def test_head_mismatch_is_surfaced_with_both_values(self):
        wrong = "deadbeef" * 5
        self.write_manifest(self.full_manifest(
            custody={"repo": self.project, "head": wrong, "dirty_count": 14, "held": ["x"]}))
        md = self.handoff()
        self.assertIn(f"HEAD MISMATCH: declared {wrong}, observed {self.head}", md)

    def test_dirty_count_mismatch_is_surfaced(self):
        self.write_manifest(self.full_manifest(
            custody={"repo": self.project, "head": self.head, "dirty_count": 13, "held": ["x"]}))
        md = self.handoff()
        self.assertIn("DIRTY COUNT MISMATCH: declared 13, observed 14", md)

    def test_artifact_hash_mismatch_is_surfaced(self):
        self.write_manifest(self.full_manifest(
            artifacts=[{"path": self.patch, "role": "patch", "sha256": OTHER_SHA}]))
        md = self.handoff()
        self.assertIn(f"HASH MISMATCH: declared {OTHER_SHA}, observed {PATCH_SHA}", md)
        self.assertNotIn("— verified", md)

    def test_missing_artifact_is_surfaced(self):
        gone = os.path.join(self.tmp, "gone.patch")
        self.assertFalse(os.path.exists(gone))
        self.write_manifest(self.full_manifest(
            artifacts=[{"path": gone, "role": "patch", "sha256": PATCH_SHA}]))
        self.assertIn("MISSING on disk", self.handoff())

    def test_stale_manifest_is_surfaced(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
        self.write_manifest(self.full_manifest(updated_at=old))
        os.utime(self.transcript, None)                                # transcript written NOW
        md = self.handoff()
        self.assertIn("STALE manifest", md)
        self.assertIn(self.head[:12], md)        # stale is surfaced, not withheld

    def test_manifest_never_falls_back_to_a_newer_session(self):
        """A manifest for ANOTHER session in this project is not used for this one."""
        self.write_manifest(self.full_manifest(objective=FOREIGN,
                                               binding={"project_root": self.project,
                                                        "session_id": "newer-sess"}),
                            sid="newer-sess")
        md = self.handoff()
        self.assertIn("GAP: no manifest declared", md)
        self.assertNotIn(FOREIGN, md)


class ProtectionsCarried(ManifestFixture):
    """The consolidated-V2 protections, re-run against the manifest route."""

    def test_cross_project_manifest_is_not_read(self):
        foreign = os.path.join(self.tmp, "foreign-seat", ".token-tithe", "manifest")
        self.write_manifest(self.full_manifest(objective=FOREIGN), where=foreign)
        self.assertTrue(os.path.isfile(os.path.join(foreign, f"{SID}.json")))   # precondition
        md = self.handoff()
        self.assertNotIn(FOREIGN, md)
        self.assertIn("GAP: no manifest declared", md)

    def test_env_session_id_is_ignored_left_bound(self):
        os.environ["MRTOKEN_SESSION"] = "foreign-sess"                 # LEFT SET throughout
        self.write_manifest(self.full_manifest(objective=FOREIGN,
                                               binding={"project_root": self.project,
                                                        "session_id": "foreign-sess"}),
                            sid="foreign-sess")
        self.write_manifest(self.full_manifest())
        md = self.handoff()
        self.assertEqual(os.environ["MRTOKEN_SESSION"], "foreign-sess")  # still bound
        self.assertIn(self.head[:12], md)
        self.assertNotIn(FOREIGN, md)

    def test_unsafe_and_glob_ids_never_escape_or_expand(self):
        from mrtoken.manifest import manifest_path, read_manifest
        for bad in ("", ".", "..", "../x", "/abs", "a/b", "a\\b", "a\x00b"):
            self.assertIsNone(manifest_path(bad), bad)
        self.write_manifest(self.full_manifest())                      # SID.json exists
        star = manifest_path("*")
        self.assertTrue(star.endswith(os.path.join("manifest", "*.json")))
        self.assertIsNone(read_manifest("*"))                          # literal, not a glob
        self.assertIsNone(read_manifest(SID[:8]))                      # no prefix matching

    def test_underscore_project_store_is_project_local(self):
        from mrtoken.manifest import manifest_path
        self.assertIn("_", os.path.basename(self.project))             # precondition
        self.assertEqual(manifest_path(SID), os.path.join(self.manifest_dir, f"{SID}.json"))
        self.assertTrue(manifest_path(SID).startswith(self.project))


class DeclareInterface(ManifestFixture):
    def test_declare_merges_rebinds_and_rejects_unknown(self):
        from mrtoken.manifest import declare_manifest, read_manifest
        p = declare_manifest(SID, {"objective": "o1"})
        self.assertEqual(p, os.path.join(self.manifest_dir, f"{SID}.json"))
        declare_manifest(SID, {"next_action": "n1"})
        m = read_manifest(SID)
        self.assertEqual((m["objective"], m["next_action"]), ("o1", "n1"))
        self.assertEqual(m["binding"], {"project_root": self.project, "session_id": SID})
        self.assertIsNone(m["reviewer_corrections"])                   # undeclared stays a gap
        with self.assertRaises(ValueError):
            declare_manifest(SID, {"summary": "not a field"})
        with self.assertRaises(ValueError):
            declare_manifest("../x", {"objective": "o"})
        self.assertFalse(os.path.exists(os.path.join(self.project, ".token-tithe", "x.json")))

    def test_declared_manifest_verifies_clean_end_to_end(self):
        from mrtoken.manifest import declare_manifest
        declare_manifest(SID, {k: v for k, v in self.full_manifest().items()
                               if k not in ("schema_version", "updated_at", "binding")})
        md = self.handoff()
        self.assertNotIn("MISMATCH", md)
        self.assertNotIn("GAP", md)
        self.assertIn(self.head[:12], md)

    def test_cli_declare_and_show(self):
        import io, contextlib
        from mrtoken import cli
        f = os.path.join(self.tmp, "fields.json")
        with open(f, "w") as fh:
            json.dump({"objective": "cli-declared objective"}, fh)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["manifest", "declare", SID, "--json", f])
            cli.main(["manifest", "show", SID])
        out = buf.getvalue()
        self.assertIn("cli-declared objective", out)
        self.assertIn("GAP", out)                                      # the rest undeclared



class ReviewCorrections(ManifestFixture):
    """Controls for the 2026-09-17 NOT-GO. Each is written to FAIL or ERROR on the
    uncorrected candidate 7dfdf7b1 for the stated reason, and pass once corrected."""

    # blocker 1 — identity is the full digest, everywhere it is printed
    def test_full_digest_rendered_nowhere_truncated(self):
        self.write_manifest(self.full_manifest())
        md = self.handoff()
        self.assertIn(f"sha256 {PATCH_SHA} — verified", md)
        self.assertNotIn(PATCH_SHA[:16] + "…", md)

    # blocker 3 — corruption is corruption, not absence
    def test_malformed_json_is_surfaced_not_reported_as_absence(self):
        os.makedirs(self.manifest_dir, exist_ok=True)
        p = os.path.join(self.manifest_dir, f"{SID}.json")
        with open(p, "w") as fh:
            fh.write("{ this is not json")
        md = self.handoff()
        self.assertIn("CORRUPT manifest", md)
        self.assertIn(p, md)
        self.assertNotIn("no manifest declared", md)

    def test_non_object_json_is_surfaced_not_reported_as_absence(self):
        os.makedirs(self.manifest_dir, exist_ok=True)
        with open(os.path.join(self.manifest_dir, f"{SID}.json"), "w") as fh:
            fh.write("[1, 2, 3]")
        md = self.handoff()
        self.assertIn("CORRUPT manifest", md)
        self.assertIn("not a JSON object", md)
        self.assertNotIn("no manifest declared", md)

    # blocker 2 — every invalid nested shape is a NAMED problem, never a crash or a drop
    def test_numeric_sha256_is_named_invalid_not_a_crash(self):
        self.write_manifest(self.full_manifest(
            artifacts=[{"path": self.patch, "role": "patch", "sha256": 12345}]))
        md = self.handoff()                                    # uncorrected: TypeError
        self.assertIn("INVALID artifacts[0].sha256", md)
        self.assertNotIn("— verified", md)

    def test_numeric_head_is_named_invalid_not_a_crash(self):
        self.write_manifest(self.full_manifest(
            custody={"repo": self.project, "head": 12345, "dirty_count": 14, "held": ["x"]}))
        md = self.handoff()                                    # uncorrected: TypeError
        self.assertIn("INVALID custody.head", md)
        self.assertNotIn("HEAD MISMATCH", md)

    def test_nonnumeric_dirty_count_is_named_invalid_not_a_crash(self):
        self.write_manifest(self.full_manifest(
            custody={"repo": self.project, "head": self.head, "dirty_count": "fourteen",
                     "held": ["x"]}))
        md = self.handoff()                                    # uncorrected: ValueError
        self.assertIn("INVALID custody.dirty_count", md)
        self.assertIn(self.head, md)                           # valid siblings still carried

    def test_non_dict_artifact_entry_is_named_invalid_not_dropped(self):
        self.write_manifest(self.full_manifest(artifacts=["just-a-string", 42]))
        md = self.handoff()
        self.assertIn("INVALID artifacts[0]", md)
        self.assertIn("INVALID artifacts[1]", md)

    def test_wrong_top_level_shapes_are_named_invalid(self):
        self.write_manifest(self.full_manifest(objective=123, decisions="not-a-list",
                                               gates=[{"no": "text"}], custody="not-a-dict"))
        md = self.handoff()
        for field in ("INVALID objective", "INVALID decisions", "INVALID gates[0]",
                      "INVALID custody"):
            self.assertIn(field, md, field)
        self.assertNotIn(self.head, md)                        # custody invalid: nothing observed
        self.assertNotIn("HEAD MISMATCH", md)

    def test_declare_rejects_invalid_shapes_naming_the_field(self):
        from mrtoken.manifest import declare_manifest
        cases = [
            ({"artifacts": [{"path": self.patch, "sha256": 12345}]}, "artifacts[0].sha256"),
            ({"artifacts": ["str"]}, "artifacts[0]"),
            ({"custody": {"head": 12345}}, "custody.head"),
            ({"custody": {"dirty_count": "fourteen"}}, "custody.dirty_count"),
            ({"objective": 123}, "objective"),
            ({"decisions": "x"}, "decisions"),
        ]
        for fields, name in cases:
            with self.assertRaises(ValueError, msg=name) as cm:
                declare_manifest(SID, fields)
            self.assertIn(name, str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.manifest_dir, f"{SID}.json")))

    # blocker 4 — declared objective, asserted on its own and mutated
    def test_declared_objective_rendered_verbatim_and_distinct_from_goal(self):
        obj = "DECLARED-OBJECTIVE: finish the manifest correction cycle"
        self.write_manifest(self.full_manifest(objective=obj))
        md = self.handoff()
        self.assertIn(f"- **current objective:** {obj}", md)
        self.assertEqual(self.goal_line(md), LAST_REQUEST)
        self.assertNotEqual(self.goal_line(md), obj)

    def test_undeclared_objective_is_a_gap_and_not_filled_from_goal(self):
        self.write_manifest(self.full_manifest(objective=None))
        md = self.handoff()
        self.assertIn("- **current objective:** GAP", md)
        self.assertEqual(md.count(LAST_REQUEST), 1)             # only in ## Goal

    # rereview 2 — retained state is validated too; a refused merge leaves the file byte-identical
    def test_merge_over_invalid_existing_state_is_refused_and_file_unchanged(self):
        from mrtoken.manifest import declare_manifest
        p = self.write_manifest(self.full_manifest(artifacts=[42]))     # invalid RETAINED shape
        with open(p, "rb") as fh:
            before = fh.read()
        self.assertIn(b"[42]", before)                                  # precondition
        with self.assertRaises(ValueError) as cm:                       # rejected V2: no raise
            declare_manifest(SID, {"objective": "new"})                 # valid delta
        self.assertIn("artifacts[0]", str(cm.exception))
        self.assertIn("retained", str(cm.exception))
        with open(p, "rb") as fh:
            after = fh.read()
        self.assertEqual(before, after)                                 # bytes exactly unchanged
        self.assertNotIn(b"new", after)
        self.assertFalse(os.path.exists(p + ".tmp"))                    # no partial write left

    def test_merge_over_invalid_existing_state_names_both_origins(self):
        from mrtoken.manifest import declare_manifest
        self.write_manifest(self.full_manifest(custody={"repo": self.project, "head": 12345}))
        with self.assertRaises(ValueError) as cm:
            declare_manifest(SID, {"objective": 123})                   # invalid delta too
        msg = str(cm.exception)
        self.assertIn("custody.head (retained)", msg)
        self.assertIn("objective (incoming)", msg)

if __name__ == "__main__":
    unittest.main()
