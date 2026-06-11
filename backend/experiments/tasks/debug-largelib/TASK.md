# Task: fix the failing tests in largelib

The `largelib` package has many modules (`textkit`, `numkit`, `listkit`,
`dictkit`, `seqkit`) with bugs that make its test suite fail. Fix the modules so
the entire suite passes.

Rules:
- Run the tests with `python3 -m pytest -q`.
- Fix bugs in the `largelib/` modules only.
- Do NOT edit `test_largelib.py` - the tests define the required behavior.
- You are done when `python3 -m pytest -q` reports all tests passing.

Work methodically through the failures until the whole suite is green.
