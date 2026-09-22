# Adding tests here

**Name every test file `test*.py`, and do not put tests in subdirectories of
`backend/tests/`.**

This is a requirement, not a style preference. `scripts/test-backend.sh` runs

    python -m unittest discover -s tests

with no `-p` flag, so discovery uses the default `test*.py` pattern and does not
recurse into packages that lack `__init__.py`. The script prints
**"Running complete backend/tests suite."**

A file named anything else — `check_foo.py`, `suite_bar.py` — is **silently
skipped** while that line still claims the suite was complete. So is a test in a
subdirectory. The tests do not fail; they simply never run, and the count looks
right because nobody knows what the right count is.

Verified 2026-09-21: a `check_extra_suite.py` holding three loadable tests is
skipped by the pattern — default discovery reported 1 test where `-p '*.py'`
reported 4.

## Why this is written down rather than worked around

The completeness claim in that script was true only because every file here
happened to match the pattern. Nothing required it. A guarantee resting on an
unwritten convention holds right up until someone adds a reasonably-named file,
and then it fails silently — which is the worst way for a test suite to fail.

Writing the rule down is what makes the claim true on purpose instead of by
luck. If you need a different naming scheme, change the script's `-p` pattern
and this file together — not one of them.

Identified during independent review of the 2026-09-21 discovery-scope fix.
